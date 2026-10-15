const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {createPort, READ_TOOLS, LIMITS} = require('../subagent-policy.cjs');
const {constrainSource} = require('../subagent-runtime.cjs');
const {permissionDecision} = require('../protocol.cjs');

async function main() {
  const events = [], gates = [];
  let running = 0, maxRunning = 0;
  const port = createPort({
    autoBackgroundMs: 1,
    runExploreAgent: async (r, opts) => {
      assert.deepEqual(r.allowedTools, READ_TOOLS);
      assert.equal(r.permissionMode, 'plan');
      assert.equal(r.maxTurns, LIMITS.turns);
      assert.equal(r.profile.skills, undefined);
      assert.equal(r.profile.mcpServers, undefined);
      assert.ok(r.disallowedTools.includes('Agent') && r.disallowedTools.includes('Bash'));
      running++; maxRunning = Math.max(running, maxRunning);
      try {
        await new Promise((resolve, reject) => {
          gates.push(resolve);
          opts?.signal?.addEventListener('abort', () => reject(new Error('cancelled')), {once: true});
        });
        return {usage: {totalTokens: 7, inputTokens: 5, outputTokens: 2, secret: 'PRIVATE'}};
      } finally { running--; }
    },
  }, options => {
    assert.equal(options.autoBackgroundMs, undefined);
    assert.deepEqual(options.getAllowedTools(), READ_TOOLS);
    for (const p of options.getAgentDefinitions().activeAgents) assert.deepEqual(p.tools, READ_TOOLS);
    return {run: (request, opts) => {
      assert.equal(request.runInBackground, false);
      return options.runExploreAgent({sessionId: 'child_' + request.parentToolCallId,
        agentType: request.agentType, prompt: request.prompt,
        traceContext: {attributes: {parentToolCallId: request.parentToolCallId}},
        allowedTools: ['*'], permissionMode: 'bypassPermissions', profile: {skills: ['unsafe']}}, opts);
    }};
  }, event => events.push(event));
  const request = i => ({sessionId: 'root', parentToolCallId: 'call_' + i, agentType: 'Explore',
    prompt: 'same prompt', runInBackground: true});
  const jobs = [0, 1, 2].map(i => port.launch(request(i)));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(running, 2);
  gates.shift()();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(running, 2);
  while (gates.length) gates.shift()();
  await Promise.all(jobs);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(maxRunning, 2);
  assert.equal(events.filter(e => e.phase === 'started').length, 3);
  assert.equal(new Set(events.filter(e => e.phase === 'started').map(e => e.childSessionId)).size, 3);
  assert.equal(events.filter(e => e.phase === 'completed').reduce((sum,e) => sum + e.usage.totalTokens, 0), 21);
  assert.ok(!JSON.stringify(events).includes('PRIVATE'));

  const a = new AbortController(), b = new AbortController(), queued = new AbortController();
  const cancelJobs = [port.launch(request(3), {signal:a.signal}), port.launch(request(4), {signal:b.signal}),
    port.launch(request(5), {signal:queued.signal})];
  const settled = Promise.allSettled(cancelJobs);
  await new Promise(resolve => setImmediate(resolve));
  queued.abort(); a.abort(); b.abort();
  assert.ok((await settled).every(r => r.status === 'rejected'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(running, 0);
  assert.ok(events.some(e => e.phase === 'cancelled' && e.usage.totalTokens === 0));
  assert.ok(events.some(e => e.phase === 'failed' && !e.usageComplete));
  await assert.rejects(port.launch({...request(6), agentType:'custom-writer'}));
  for (const i of [6, 7]) {
    const p = port.launch(request(i));
    await new Promise(resolve => setImmediate(resolve));
    while(gates.length) gates.shift()();
    await p;
  }
  await assert.rejects(port.launch(request(8)), /budget exhausted/);
  await assert.rejects(port.backgroundTask('a'));

  const origin = {kind:'subagent',childSessionId:'child'};
  assert.equal(permissionDecision({sessionId:'root',toolName:'Agent',riskLevel:'low'},'root','edit',new Set(),true).decision,'allow');
  assert.equal(permissionDecision({sessionId:'root',origin,toolName:'WebFetch',riskLevel:'medium'},'root','edit',new Set(['child'])).decision,'allow');
  for (const toolName of ['Bash','Write','Agent','Task']) assert.equal(permissionDecision({sessionId:'root',origin,toolName,riskLevel:'low'},'root','edit',new Set(['child'])).decision,'deny');
  assert.equal(permissionDecision({sessionId:'root',origin,toolName:'Read',riskLevel:'low'},'root','edit').decision,'deny');
  const fixture = 'function DCn(e){let u={};return u}function ICn(e,t,n){}';
  const hash = createHash('sha256').update(fixture).digest('hex');
  assert.ok(constrainSource(fixture,hash).includes('.createPort(e,function(e){'));
  assert.throws(() => constrainSource(fixture), /Unsupported/);
  assert.throws(() => constrainSource(fixture+fixture,createHash('sha256').update(fixture+fixture).digest('hex')));
  new Function(constrainSource(fixture,hash));
  console.log('subagent policy tests passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
