// Conservative classification, not a shell parser or a test-pass assertion.
const {createHash} = require('node:crypto');
function identify(command) {
  if (typeof command !== 'string' || command.length > 8192 || /[|;&<>`$()\r\n]/.test(command)) return null;
  const tokens = command.match(/"[^"\n]*"|'[^'\n]*'|[^\s"']+/g) || [];
  if (tokens.join(' ').replace(/\s/g, '') !== command.replace(/\s/g, '')) return null;
  const argv = tokens.map(t => /^['"]/.test(t) ? t.slice(1, -1) : t);
  const exe = (argv[0] || '').split(/[\\/]/).pop().toLowerCase().replace(/\.exe$/, '');
  let category;
  if (/^python(?:\d+(?:\.\d+)*)?$/.test(exe) && argv[1] === '-m' && ['unittest', 'pytest'].includes(argv[2])) category = 'test';
  else if (['pytest', 'pytest-3'].includes(exe) || exe === 'node' && argv[1] === '--test') category = 'test';
  else if (['npm', 'pnpm', 'yarn', 'bun'].includes(exe)) {
    const verb = argv[1] === 'run' ? argv[2] : argv[1];
    if (['test', 'vitest', 'jest'].includes(verb)) category = 'test';
    if (['build', 'compile'].includes(verb)) category = 'build';
  } else if (['go', 'cargo', 'dotnet'].includes(exe)) {
    if (argv[1] === 'test') category = 'test';
    if (['build', 'check'].includes(argv[1])) category = 'build';
  }
  return category ? {category, id: createHash('sha256').update(JSON.stringify(argv)).digest('hex')} : null;
}
function outcome(result, identity) {
  const cmd = result?.perf?.detail?.command;
  if (!cmd || !Number.isSafeInteger(cmd.exitCode) || !['completed', 'failed'].includes(cmd.status) || cmd.timedOut) return undefined;
  return {category: identity?.category || 'other', ...(identity ? {id: identity.id} : {}),
    exit_code: cmd.exitCode, status: cmd.status};
}
module.exports = {identify, outcome};
