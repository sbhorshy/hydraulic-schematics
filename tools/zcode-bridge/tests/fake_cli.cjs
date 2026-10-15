// Windows transport fixture. Does not load the ZCode CLI or contact a provider.
// Static capability markers used ONLY for CLI integration tests:
// stream-json createHeadlessSessionObserver resolveResumeSession --resume
// No permission client configured for createHeadlessPermissionBroker
// --disallowed-tools
// interaction/requestPermission session/create session/subscribe session/send
// toolAllowlist ZCodeProtocolNdjsonConnection
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const args = process.argv.slice(2);
const value = name => args[args.indexOf(name) + 1];
const prompt = value('-p');
const sid = args.includes('--resume') ? value('--resume') : prompt.startsWith('TEAM_FIXTURE:') ? 'sess_fixture_' + process.pid : 'sess_windows_fixture';
const emit = (type, fields = {}) => console.log(JSON.stringify({type, sessionId: sid, ...fields}));
emit('session.created', {payload: {}});
emit('session.updated', {payload: {modelId: 'fixture-model', providerId: 'fixture-provider'}});
emit('model.streaming', {payload: {kind: 'reasoning_delta', delta: 'PRIVATE_WINDOWS_SENTINEL'}});
if (prompt.startsWith('TEAM_NO_OUTPUT')) {
  setInterval(() => emit('model.streaming', {payload: {kind:'text_delta',delta:'fixture heartbeat'}}), 100);
} else if (prompt.startsWith('TEAM_FIXTURE:')) {
  const filename = prompt.split('\n', 1)[0].slice('TEAM_FIXTURE:'.length);
  fs.writeFileSync(path.join(value('--cwd'), filename), 'BRIDGE_TEAM_OK\n');
  setTimeout(() => emit('result', {response: 'fixture file written', usage: {totalTokens: 0}, projection: {status: 'idle'}}), 1500);
} else if (prompt.startsWith('hang') || prompt.startsWith('orphan')) {
  const child = cp.spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {stdio: 'ignore'});
  fs.writeFileSync(path.join(value('--cwd'), 'child.pid'), String(child.pid));
  emit('tool.updated', {payload: {kind: 'started', toolName: 'Read', toolCallId: 'fixture'}});
  if (prompt.startsWith('hang')) {
    setInterval(() => {}, 1000);
  } else {
    child.unref();
    emit('result', {response: 'created owned child', projection: {status: 'idle'}});
  }
} else {
    emit('result', {response: JSON.stringify({length: prompt.length, unicode: prompt.includes('中文'),
                   literal: prompt.includes("$(DO_NOT_EXECUTE)`'\""), argvMode: value('--mode'),
                   disallowedTools: args.includes('--disallowed-tools') ? value('--disallowed-tools') : null}),
                 usage: {modelRequestCount: 0}, projection: {status: 'idle'}});
}
