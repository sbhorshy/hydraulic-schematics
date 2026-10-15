// Restrictions added around the native subagent port. No provider/broker bypass.
const {randomUUID} = require('node:crypto');
const READ_TOOLS = Object.freeze(['Read', 'Glob', 'Grep', 'WebFetch', 'WebSearch']);
const DENIED_TOOLS = Object.freeze(['Bash', 'Write', 'Edit', 'ApplyPatch', 'Agent', 'Task', 'Skill']);
const LIMITS = Object.freeze({concurrency: 2, calls: 8, turns: 12});
const profiles = ['Explore', 'general-purpose'].map(name => Object.freeze({
  name, source: 'bridge', description: 'Read-only investigation and code review',
  tools: [...READ_TOOLS], disallowedTools: [...DENIED_TOOLS],
  permissionMode: 'plan', maxTurns: LIMITS.turns, injectAgentsMd: false,
  systemPrompt: 'Investigate or review the assigned question. Read-only tools only. Return concise findings with file references. Do not modify files, execute commands, delegate, or read agent conversation transcripts. Request a TEAM writing task if changes are needed.',
}));

function createPort(options, factory, notify = params => process.stdout.write(JSON.stringify({method: 'bridge/subagent', params}) + '\n')) {
  const active = new Map(), queue = [];
  let calls = 0;
  const emit = (record, phase, extra = {}) => notify({phase, callId: record.id,
    parentSessionId: record.request.sessionId, parentToolCallId: record.request.parentToolCallId,
    childSessionId: record.childSessionId, ...extra});
  const native = factory({...options, profiles, autoBackgroundMs: undefined,
    getAgentDefinitions: () => ({activeAgents: profiles}),
    getAllowedTools: () => [...READ_TOOLS],
    runExploreAgent: async (request, opts) => {
      const record = [...active.values()].find(r => r.request.parentToolCallId === request.traceContext?.attributes?.parentToolCallId);
      if (!record) throw new Error('Unregistered bridge subagent');
      record.childSessionId = request.sessionId;
      const profile = profiles.find(p => p.name === request.agentType);
      if (!profile) throw new Error('Unsupported bridge subagent profile');
      emit(record, 'started', {allowedTools: [...READ_TOOLS], depth: 1});
      return options.runExploreAgent({...request, profile, systemPrompt: profile.systemPrompt,
        allowedTools: [...READ_TOOLS], disallowedTools: [...DENIED_TOOLS],
        permissionMode: 'plan', maxTurns: LIMITS.turns}, opts);
    },
  });

  function drain() {
    while (active.size < LIMITS.concurrency && queue.length) {
      const record = queue.shift();
      record.opts?.signal?.removeEventListener('abort', record.onAbort);
      if (record.opts?.signal?.aborted) { record.reject(new Error('Subagent cancelled while queued')); continue; }
      active.set(record.id, record);
      Promise.resolve().then(() => native.run({...record.request, runInBackground: false}, record.opts))
        .then(result => {
          emit(record, 'completed', {usage: numericUsage(result.usage),
            usageComplete: Number.isSafeInteger(result.usage?.totalTokens)});
          record.resolve(result);
        }, error => {
          emit(record, 'failed', {usageComplete: false});
          record.reject(error);
        }).finally(() => { active.delete(record.id); drain(); });
    }
  }
  function launch(request, opts) {
    if (opts?.signal?.aborted) return Promise.reject(new Error('Subagent cancelled'));
    if (!profiles.some(p => p.name.toLowerCase() === request.agentType?.toLowerCase())) {
      return Promise.reject(new Error('Use Explore or general-purpose for read-only work; writing requires TEAM'));
    }
    if (calls >= LIMITS.calls) return Promise.reject(new Error('Bridge subagent call budget exhausted (8 per task)'));
    calls++;
    return new Promise((resolve, reject) => {
      const record = {id: randomUUID(), request: {...request,
        agentType: profiles.find(p => p.name.toLowerCase() === request.agentType.toLowerCase()).name},
        opts, resolve, reject};
      record.onAbort = () => {
        const index = queue.indexOf(record);
        if (index >= 0) { queue.splice(index, 1); emit(record, 'cancelled', {usageComplete: true, usage: {totalTokens: 0}}); reject(new Error('Subagent cancelled while queued')); }
      };
      opts?.signal?.addEventListener('abort', record.onAbort, {once: true});
      queue.push(record);
      emit(record, 'queued');
      drain();
    });
  }
  return {...native, launch, run: launch, start: launch,
    backgroundTask: async () => { throw new Error('Bridge subagents must finish in the foreground'); },
    sendMessage: async () => { throw new Error('Use a new Agent call within the task budget'); }};
}

function numericUsage(raw) {
  const out = {};
  for (const key of ['inputTokens','outputTokens','totalTokens','cacheReadTokens','cacheWriteTokens','reasoningTokens']) {
    if (Number.isSafeInteger(raw?.[key]) && raw[key] >= 0) out[key] = raw[key];
  }
  return out;
}
module.exports = {createPort, READ_TOOLS, DENIED_TOOLS, LIMITS, numericUsage};
