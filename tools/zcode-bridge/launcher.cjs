// Load the bundled CLI in this process. The prompt stays out of the Windows
// command line, which also avoids its 32K length limit. No on-disk upstream edits.
// Constrained delegation uses a hash-pinned, in-process subagent port adapter.
const fs = require('node:fs');
const requestPath = process.argv[2];
const request = JSON.parse(fs.readFileSync(requestPath, 'utf8'));
if (request.version !== 1 || !Array.isArray(request.argv)) {
  throw new Error('Invalid bridge launch request');
}
const owner = {
  pid: process.pid, request: requestPath, token: request.token,
  startedAt: new Date().toISOString(),
};
fs.writeFileSync(request.ownerFile, JSON.stringify(owner), {flag: 'wx'});
if (request.development) {
  require('./protocol.cjs').run(request).catch(() => {
    // Do not expose arbitrary server error payloads or provider details.
    process.stderr.write('Bridge development protocol failed\n');
    process.exitCode = 1;
  });
} else {
  process.argv = [process.execPath, request.cli, ...request.argv];
  require(request.cli);
}
