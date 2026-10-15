"""Windows launch and ownership-checked process-tree cancellation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from bridge_contract import BridgeError, atomic_json

ROOT = Path(__file__).resolve().parent
CODE_LOCAL_DISALLOWED = ('Bash', 'WebFetch', 'WebSearch', 'Agent', 'Task')


def cli_arguments(request, cwd):
    argv = ['--cwd', cwd, '--mode', request['mode'], '--output-format', 'stream-json', '-p', request['prompt']]
    if request.get('resume'):
        argv += ['--resume', request['resume']]
    policy = request.get('tool_policy', request.get('contract', {}).get('tool_policy', 'code-local'))
    if policy not in ('code-local', 'cli-default', 'development'):
        raise BridgeError('Unknown tool policy')
    if policy == 'code-local':
        argv += ['--disallowed-tools', ','.join(CODE_LOCAL_DISALLOWED)]
    return argv


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def ps_command(script):
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    return ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]


def windows_path(path):
    return subprocess.check_output(['wslpath', '-w', str(Path(path).resolve())],
                                   text=True, timeout=15).strip()


class WindowsBackend:
    def __init__(self):
        self.exe = Path(os.environ.get('ZCODE_BRIDGE_EXE', '/mnt/d/Program Files/ZCode/ZCode.exe'))
        self.cli = Path(os.environ.get('ZCODE_BRIDGE_CLI', '/mnt/d/Program Files/ZCode/resources/glm/zcode.cjs'))
        self.provider = Path(os.environ.get('ZCODE_BRIDGE_PROVIDER', '/mnt/d/Program Files/ZCode/resources/config/provider/zcode-builtin.json'))

    def doctor(self):
        checks = {name: path.is_file() for name, path in
                  [('executable', self.exe), ('cli', self.cli), ('provider_config_exists', self.provider),
                   ('launcher', ROOT / 'launcher.cjs')]}
        checks['powershell_on_path'] = shutil.which('powershell.exe') is not None
        checks['wslpath_on_path'] = shutil.which('wslpath') is not None
        source = self.cli.read_text(encoding='utf-8') if checks['cli'] else ''
        stream = 'stream-json' in source and 'createHeadlessSessionObserver' in source
        resume = 'resolveResumeSession' in source and '--resume' in source
        deny = 'No permission client configured for' in source and 'createHeadlessPermissionBroker' in source
        checks.update(stream_json=stream, resume=resume, known_headless_broker=deny,
                      tool_filter='--disallowed-tools' in source,
                      development_protocol=all(marker in source for marker in (
                          'interaction/requestPermission', 'session/create', 'session/subscribe',
                          'session/send', 'toolAllowlist', 'ZCodeProtocolNdjsonConnection')),
                      protocol_client=(ROOT / 'protocol.cjs').is_file())
        return {'ready': all(checks.values()), 'checks': checks, 'bridge_version': '3.6',
                'cli_sha256': hashlib.sha256(source.encode()).hexdigest() if source else None,
                'capabilities': {'read_edit_write': 'mode-dependent; runtime refusal remains authoritative',
                                 'shell': 'development profile: host execution',
                                 'permission_client': 'development profile: task-scoped app-server client',
                                 'os_sandbox': False,
                                 'session_reasoning_effort': 'runtime-verified; low/high/max/inherit',
                                 'first_delivery_checks': True,
                                 'constrained_subagents': hashlib.sha256(source.encode()).hexdigest() == 'b816e38656e70fb585fe2ab1ea010da89cda928dac1ccb5d83255fd18796da6e' and all((ROOT / name).is_file() for name in ('subagent-runtime.cjs', 'subagent-policy.cjs')),
                                 'test_executor': 'controller', 'stream_json': stream, 'resume': resume},
                'probe': 'static only; no provider call or credentials read',
                'guidance': 'development enables Bash and web tools; code-local retains the restricted headless path. Controller tests remain authoritative.'}

    def launch(self, request, directory):
        directory = Path(directory)
        win_request = windows_path(directory / 'launch.json')
        win_launcher = windows_path(ROOT / 'launcher.cjs')
        argv = cli_arguments(request, windows_path(request['cwd']))
        launch = {'version': 1, 'token': request['task_id'], 'cli': windows_path(self.cli),
                  'argv': argv, 'ownerFile': windows_path(directory / 'windows-owner.json')}
        if request.get('tool_policy', request.get('contract', {}).get('tool_policy', 'code-local')) == 'development':
            launch['development'] = {'cwd': windows_path(request['cwd']), 'mode': request['mode'],
                                     'resume': request.get('resume'), 'prompt': request['prompt'],
                                     'allowSubagents': request.get('allow_subagents', request.get('contract', {}).get('allow_subagents', False)),
                                     'reasoningEffort': request.get('reasoning_effort', request.get('contract', {}).get('reasoning_effort', 'inherit')),
                                     'expectedModel': request.get('expected_model')}
        atomic_json(directory / 'launch.json', launch)
        script = '\n'.join([
            "$ErrorActionPreference = 'Stop'",
            '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8',
            "$env:ELECTRON_RUN_AS_NODE = '1'",
            '$env:ZCODE_BUILTIN_PROVIDER_CONFIG_FILE = ' + ps_quote(windows_path(self.provider)),
            '& ' + ps_quote(windows_path(self.exe)) + ' ' + ps_quote(win_launcher) + ' ' + ps_quote(win_request),
            'exit $LASTEXITCODE',
        ])
        command = ps_command(script)
        # Persist the original OS command identity; process.argv inside Node can
        # change without changing Win32_Process.CommandLine.
        atomic_json(directory / 'transport.json', {'request': win_request, 'launcher': win_launcher,
                    'executable': windows_path(self.exe), 'powershell_encoded': command[-1],
                    'owner_file': launch['ownerFile'], 'token': request['task_id']})
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)

    def cleanup(self, process, directory):
        """Stop this launch only, also if Node has not yet written its PID record."""
        meta = json.loads((Path(directory) / 'transport.json').read_text())
        # Stop a still-starting PowerShell parent and all its descendants first.
        # Exact encoded command + per-run request path prevents PID reuse errors.
        script = '\n'.join([
            "$ErrorActionPreference = 'Stop'",
            '$encoded = ' + ps_quote(meta['powershell_encoded']),
            '$request = ' + ps_quote(meta['request']),
            '$launcher = ' + ps_quote(meta['launcher']),
            '$exe = ' + ps_quote(meta['executable']),
            '$ownerFile = ' + ps_quote(meta['owner_file']),
            '$token = ' + ps_quote(meta['token']),
            '$parents = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "powershell.exe" -and $_.CommandLine -and $_.CommandLine.Contains($encoded) })',
            'foreach ($owned in $parents) { & taskkill.exe /PID $owned.ProcessId /T /F > $null 2>&1 }',
            '$children = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $exe -and $_.CommandLine -and $_.CommandLine.Contains($request) -and $_.CommandLine.Contains($launcher) })',
            'foreach ($owned in $children) { & taskkill.exe /PID $owned.ProcessId /T /F > $null 2>&1 }',
            # A CLI can exit before its child. Win32 retains ParentProcessId;
            # inspect that ancestry too, rejecting a reused root PID.
            'if (Test-Path -LiteralPath $ownerFile) {',
            '  $record = Get-Content -Raw -Encoding UTF8 -LiteralPath $ownerFile | ConvertFrom-Json',
            '  if ($record.token -ne $token -or $record.request -ne $request) { exit 1 }',
            '  $all = @(Get-CimInstance Win32_Process)',
            '  $rootNow = @($all | Where-Object { $_.ProcessId -eq $record.pid })',
            '  if ($rootNow.Count -gt 0 -and -not ($rootNow[0].ExecutablePath -eq $exe -and $rootNow[0].CommandLine.Contains($request))) { exit 1 }',
            '  $cutoff = ([DateTime]::Parse($record.startedAt)).ToUniversalTime().AddSeconds(-5)',
            '  $ids = New-Object "System.Collections.Generic.HashSet[uint32]"',
            '  [void]$ids.Add([uint32]$record.pid)',
            '  do { $added = $false; foreach ($item in $all) { if ($ids.Contains([uint32]$item.ParentProcessId) -and $item.CreationDate.ToUniversalTime() -ge $cutoff -and $ids.Add([uint32]$item.ProcessId)) { $added = $true } } } while ($added)',
            '  foreach ($item in $all) { if ($item.ProcessId -ne $record.pid -and $ids.Contains([uint32]$item.ProcessId)) {',
            '    $now = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $item.ProcessId)',
            '    if ($now -and $now.CreationDate -eq $item.CreationDate) { & taskkill.exe /PID $now.ProcessId /T /F > $null 2>&1 }',
            '    $still = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $item.ProcessId)',
            '    if ($still -and $still.CreationDate -eq $item.CreationDate) { exit 1 }',
            '  } }',
            '}',
            '$left = @(Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq "powershell.exe" -and $_.CommandLine -and $_.CommandLine.Contains($encoded)) -or ($_.ExecutablePath -eq $exe -and $_.CommandLine -and $_.CommandLine.Contains($request) -and $_.CommandLine.Contains($launcher)) })',
            'if ($left.Count -gt 0) { exit 1 }; exit 0',
        ])
        try:
            result = subprocess.run(ps_command(script), capture_output=True, timeout=25)
            if process is not None:
                process.wait(timeout=10)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
