// Compatibility adapter for one audited ZCode bundle. The installed upstream
// file is unchanged; constraints are added while loading this task's process.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const {createHash} = require('node:crypto');
const CLI_SHA256 = 'b816e38656e70fb585fe2ab1ea010da89cda928dac1ccb5d83255fd18796da6e';
const START = 'function DCn(e){';
const END = 'return u}function ICn(e,t,n){';

function constrainSource(source, expectedHash = CLI_SHA256) {
  if (createHash('sha256').update(source).digest('hex') !== expectedHash ||
      source.split(START).length !== 2 || source.split(END).length !== 2) {
    throw new Error('Unsupported ZCode bundle for constrained subagents');
  }
  const policy = JSON.stringify(path.join(__dirname, 'subagent-policy.cjs'));
  return source.replace(START, `${START}return require(${policy}).createPort(e,function(e){`)
    .replace(END, 'return u});}function ICn(e,t,n){');
}

if (require.main === module) {
  const cli = path.resolve(process.argv[2]);
  const source = constrainSource(fs.readFileSync(cli, 'utf8'));
  process.argv = [process.execPath, cli, ...process.argv.slice(3)];
  const loaded = new Module(cli, module);
  loaded.filename = cli;
  loaded.paths = Module._nodeModulePaths(path.dirname(cli));
  loaded._compile(source, cli);
}
module.exports = {constrainSource, CLI_SHA256};
