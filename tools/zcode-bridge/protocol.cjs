// Task-scoped client for ZCode's native app-server permission protocol.
// This is a host executor, not an OS sandbox. Never persists permission grants.
const {spawn} = require('node:child_process');
const path = require('node:path');
const {READ_TOOLS, numericUsage} = require('./subagent-policy.cjs');
const {identify, outcome} = require('./command-evidence.cjs');
const {configureReasoning} = require('./reasoning.cjs');

const DEVELOPMENT_TOOLS = ['Read', 'Edit', 'Write', 'Glob', 'Grep', 'Bash',
  'WebFetch', 'WebSearch', 'TodoWrite'];

function permissionDecision(params, sessionId, mode, children = new Set(), allowSubagents = false) {
  const childRead = params.origin?.kind === 'subagent' && children.has(params.origin.childSessionId)
    && READ_TOOLS.includes(params.toolName);
  const allowed = params.sessionId === sessionId && (!params.origin || childRead) && (mode !== 'plan' || childRead)
    && (DEVELOPMENT_TOOLS.includes(params.toolName) || (!params.origin && allowSubagents && ['Agent','Task'].includes(params.toolName)))
    && ['low', 'medium', 'high'].includes(params.riskLevel);
  return {decision: allowed ? 'allow' : 'deny',
    reason: allowed ? 'Bridge task development permission (once)' : 'Outside bridge development permissions'};
}

async function run(request) {
  const config = request.development;
  if (!config || !['edit', 'build', 'plan'].includes(config.mode)) throw new Error('Invalid development request');
  const entry = config.allowSubagents ? [path.join(__dirname, 'subagent-runtime.cjs'), request.cli] : [request.cli];
  const child = spawn(process.execPath, [...entry, 'app-server', '--stdio', '--cwd', config.cwd],
    {stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true});
  const pending = new Map();
  const subagents = new Map(), childSessions = new Set();
  const commandIdentities = new Map();
  let sequence = 0, sessionId, buffer = '', completed = false, eventCount = 0;
  let resolveTurn, rejectTurn;
  const turn = new Promise((resolve, reject) => { resolveTurn = resolve; rejectTurn = reject; });
  // Attach immediately: transport can fail before startup requests finish.
  turn.catch(() => {});
  const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
  const send = value => child.stdin.write(JSON.stringify(value) + '\n');
  function fail(error) {
    for (const value of pending.values()) { clearTimeout(value.timer); value.reject(error); }
    pending.clear();
    rejectTurn(error);
  }
  function rpc(method, params) {
    const id = `bridge-${++sequence}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Protocol timeout: ${method}`)); }, 60000);
      pending.set(id, {resolve, reject, timer});
      send({id, method, params});
    });
  }
  child.on('error', fail);
  child.stdin.on('error', fail);
  child.stderr.on('data', data => process.stderr.write(data));
  child.on('exit', code => {
    if (!completed) fail(new Error(`Protocol process exited before completion (${code})`));
  });
  function event(raw) {
    if (!raw || raw.sessionId !== sessionId) return;
    eventCount++;
    if (raw.type === 'model.streaming') {
      const p = raw.payload || {};
      if (p.kind === 'tool_call' && p.toolName === 'Bash' && typeof p.input?.command === 'string') {
        commandIdentities.set(p.toolCallId, identify(p.input.command));
      }
      emit({type: 'transport.heartbeat', payload: {
        phase: typeof p.kind === 'string' && p.kind.startsWith('tool_input') ? 'tool_input' : p.kind === 'text_delta' ? 'model_output' : 'model_streaming',
        bytes: typeof p.delta === 'string' ? Buffer.byteLength(p.delta) : 0}});
    }
    // No reasoning, message bodies, or arbitrary tool input/output is forwarded.
    if (['session.created', 'session.resumed', 'session.updated', 'turn.started',
      'turn.completed', 'turn.failed', 'tool.updated', 'permission.requested', 'permission.resolved'].includes(raw.type)) {
      const p = raw.payload || {};
      if (raw.type === 'tool.updated' && p.kind === 'scheduled' && p.toolName === 'Bash' && typeof p.input?.command === 'string') {
        commandIdentities.set(p.toolCallId, identify(p.input?.command));
      }
      let payload = {};
      for (const key of ['kind', 'toolName', 'toolCallId', 'decision', 'modelId', 'providerId', 'childSessionId', 'agentId']) {
        if (typeof p[key] === 'string') payload[key] = p[key];
      }
      if (raw.type === 'tool.updated' && p.kind === 'result') {
        payload.result = {success: p.result?.success !== false && p.result?.isError !== true && !p.result?.error};
        payload.command = outcome(p.result, commandIdentities.get(p.toolCallId));
        commandIdentities.delete(p.toolCallId);
      }
      if (raw.type === 'tool.updated' && p.kind === 'error') {
        commandIdentities.delete(p.toolCallId);
        const message = typeof p.error?.message === 'string' ? p.error.message.toLowerCase() : '';
        const category = ['no permission client configured', 'permission denied', 'timeout', 'timed out',
          'econnreset', 'fetch failed', 'enotfound', 'enoent', 'invalid argument'].find(key => message.includes(key));
        payload.error = {message: category || 'Tool execution failed'};
      }
      emit({type: raw.type, sessionId, payload});
    }
    if (raw.type === 'turn.completed' || raw.type === 'turn.failed') resolveTurn(raw);
  }
  function receive(message) {
    if (message.id !== undefined && !message.method) {
      const waiter = pending.get(message.id);
      if (waiter) {
        clearTimeout(waiter.timer); pending.delete(message.id);
        if (message.error) waiter.reject(new Error(`Protocol request failed: ${message.error.code}`));
        else waiter.resolve(message.result);
      }
    } else if (message.id !== undefined) {
      if (message.method === 'interaction/requestPermission') {
        const decision = permissionDecision(message.params || {}, sessionId, config.mode, childSessions, config.allowSubagents);
        send({id: message.id, result: decision});
        emit({type: 'permission.resolved', sessionId,
          payload: {toolName: message.params?.toolName, decision: decision.decision}});
      } else {
        send({id: message.id, error: {code: -32601, message: 'Unsupported bridge interaction'}});
      }
    } else if (message.method === 'bridge/subagent' && config.allowSubagents) {
      const p = message.params;
      if (p?.parentSessionId !== sessionId || typeof p.callId !== 'string' ||
          !['queued', 'started', 'completed', 'failed', 'cancelled'].includes(p.phase)) return;
      subagents.set(p.callId, {...subagents.get(p.callId), ...p});
      if (p.childSessionId) {
        if (p.phase === 'started') childSessions.add(p.childSessionId);
        else if (['completed', 'failed', 'cancelled'].includes(p.phase)) childSessions.delete(p.childSessionId);
      }
      emit({type: 'subagent.' + p.phase, sessionId, payload: {
        callId: p.callId, childSessionId: p.childSessionId, parentToolCallId: p.parentToolCallId,
        usage: numericUsage(p.usage), usageComplete: p.usageComplete}});
    } else if (message.method === 'session/event') {
      event(message.params);
    }
  }
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', chunk => {
    try {
      buffer += chunk;
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
        if (Buffer.byteLength(line) > 8 * 1024 * 1024) throw new Error('Oversized protocol message');
        if (line.trim()) receive(JSON.parse(line));
      }
      if (Buffer.byteLength(buffer) > 8 * 1024 * 1024) throw new Error('Oversized protocol message');
    } catch (error) { fail(error); }
  });
  try {
    const workspace = {workspacePath: config.cwd, workspaceKey: config.cwd};
    const common = {workspace, toolAllowlist: [...DEVELOPMENT_TOOLS, ...(config.allowSubagents ? ['Agent', 'Task'] : [])],
      dynamicWorkflowEnabled: false, offPeakToolEnabled: false};
    let snapshot = config.resume
      ? await rpc('session/resume', {...common, sessionId: config.resume})
      : await rpc('session/create', {...common, mode: config.mode, titleGenerationEnabled: false});
    sessionId = snapshot.session.sessionId;
    if (config.resume && sessionId !== config.resume) throw new Error('Unexpected resumed session');
    if (config.resume) await rpc('session/setMode', {sessionId, mode: config.mode});
    const model = snapshot.session.model;
    emit({type: 'session.updated', sessionId, payload: model || {}});
    if (config.expectedModel && model?.modelId !== config.expectedModel) throw new Error('Unexpected model');
    snapshot = await configureReasoning(rpc, snapshot, config.reasoningEffort, emit);
    if (snapshot.session.sessionId !== sessionId || snapshot.session.model?.modelId !== model?.modelId || snapshot.session.model?.providerId !== model?.providerId) {
      throw new Error('Session/model changed while configuring reasoning');
    }
    await rpc('session/subscribe', {sessionId, deliveryKind: 'desktop-continuous'});
    await rpc('session/send', {sessionId, content: config.prompt});
    const terminal = await turn;
    const usage = {...terminal.payload?.usage};
    const childUsage = {}, rows = [...subagents.values()];
    for (const row of rows) for (const [key, value] of Object.entries(numericUsage(row.usage))) {
      childUsage[key] = (childUsage[key] || 0) + value;
      usage[key] = (usage[key] || 0) + value;
    }
    const childUsageComplete = rows.every(r => r.usageComplete === true);
    // Child output reliably reports tokens, but not all parent usage counters.
    // Omit counters that cannot yet be aggregated instead of labeling them total.
    if (rows.length) for (const key of ['modelRequestCount', 'webFetchRequests', 'webSearchRequests']) delete usage[key];
    const unfinished = rows.some(r => !['completed', 'failed', 'cancelled'].includes(r.phase));
    if (unfinished) throw new Error('Subagents have not settled');
    emit({type: 'result', sessionId, turnId: terminal.turnId,
      response: terminal.payload?.response || '', usage: usage || {}, eventCount,
      usageComplete: Number.isSafeInteger(terminal.payload?.usage?.totalTokens) && childUsageComplete,
      subagents: {calls: rows.length, completed: rows.filter(r => r.phase === 'completed').length,
        failed: rows.filter(r => r.phase === 'failed').length, usage: childUsage, usage_complete: childUsageComplete},
      projection: {status: terminal.type === 'turn.failed' ? 'error' : 'idle'}});
    completed = true;
    await rpc('session/close', {sessionId});
  } finally {
    child.stdin.end();
    // The Python controller owns and verifies termination of this whole tree.
    for (const value of pending.values()) clearTimeout(value.timer);
  }
}

module.exports = {run, permissionDecision, DEVELOPMENT_TOOLS};
