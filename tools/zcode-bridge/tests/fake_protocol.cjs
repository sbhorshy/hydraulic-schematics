// Native app-server wire fixture; never contacts a provider.
const readline = require('node:readline');
const fs = require('node:fs');
const cp = require('node:child_process');
const path = require('node:path');
const assert = require('node:assert/strict');
let sessionId = 'sess_protocol_fixture', scenario, cwd;
let effort = 'high';
const snapshot = () => ({session:{sessionId,model:{modelId:'fixture-model',providerId:'fixture-provider'}},
  settings:{thoughtLevel:{current:effort,available:['low','high','max'].map(value=>({value}))}}});
const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
const event = (type, payload) => emit({method: 'session/event', params: {type, sessionId, payload}});
const requests = new Map();
function ask(id, params, expected) {
  requests.set(id, expected);
  emit({id, method: 'interaction/requestPermission', params});
}
readline.createInterface({input: process.stdin}).on('line', line => {
  const m = JSON.parse(line);
  if (!m.method) {
    assert.equal(m.result.decision, requests.get(m.id));
    requests.delete(m.id);
    if (!requests.size) {
      event('model.streaming', {kind:'tool_call', toolName:'Bash', toolCallId:'test-call',
        input:{command:'node --test private-test-name.cjs'}, delta:''});
      event('tool.updated', {kind:'scheduled', toolName:'Bash', toolCallId:'test-call', inputOmitted:true, inputRef:'model_stream'});
      event('tool.updated', {kind: 'started', toolName: 'Bash', toolCallId: 'test-call'});
      event('tool.updated', {kind: 'result', toolCallId: 'test-call', result: {success: true,
        perf:{detail:{command:{exitCode:1,status:'failed'}}}}});
      event('turn.completed', {response: 'fixture permissions verified', usage: {totalTokens: 0}});
    }
    return;
  }
  if (m.method === 'session/create' || m.method === 'session/resume') {
    assert.deepEqual(m.params.toolAllowlist.sort(), ['Read','Edit','Write','Glob','Grep','Bash','WebFetch','WebSearch','TodoWrite'].sort());
    assert.equal(m.params.dynamicWorkflowEnabled, false);
    assert.equal(m.params.offPeakToolEnabled, false);
    sessionId = m.params.sessionId || sessionId;
    cwd = m.params.workspace.workspacePath;
    emit({id: m.id, result: snapshot()});
  } else if (m.method === 'session/setThoughtLevel') {
    assert.equal(m.params.persistAsWorkspaceLastUsed,false);
    if (path.basename(cwd) !== 'effort-ignored') effort = m.params.thoughtLevel;
    emit({id:m.id,result:snapshot()});
  } else if (m.method === 'session/read') {
    emit({id:m.id,result:snapshot()});
  } else if (m.method === 'session/send') {
    if (process.env.BRIDGE_FIXTURE_SEND_MARKER) fs.writeFileSync(process.env.BRIDGE_FIXTURE_SEND_MARKER,'sent');
    scenario = m.params.content;
    emit({id: m.id, result: {accepted: true}});
    event('model.streaming', {kind: 'reasoning_delta', delta: 'PRIVATE_PROTOCOL_SENTINEL'});
    if (scenario.startsWith('hang')) {
      const child = cp.spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {stdio: 'ignore'});
      fs.writeFileSync(path.join(cwd, 'child.pid'), String(child.pid));
      event('tool.updated', {kind: 'started', toolName: 'Bash', toolCallId: 'test-call'});
      setInterval(() => {}, 1000);
      return;
    }
    const base = {sessionId, riskLevel: 'medium', toolName: 'Bash'};
    for (const [id, changes, expected] of [
      ['shell', {}, 'allow'], ['web', {toolName: 'WebFetch'}, 'allow'],
      ['search', {toolName: 'WebSearch'}, 'allow'], ['critical', {riskLevel: 'critical'}, 'deny'],
      ['agent', {toolName: 'Agent'}, 'deny'], ['other-session', {sessionId: 'wrong'}, 'deny'],
      ['child', {origin: {kind: 'subagent'}}, 'deny'], ['unknown', {toolName: 'Unknown'}, 'deny'],
    ]) if (!scenario.startsWith('allow_only') || expected === 'allow') ask(id, {...base, ...changes}, expected);
  } else {
    emit({id: m.id, result: {}});
  }
});
