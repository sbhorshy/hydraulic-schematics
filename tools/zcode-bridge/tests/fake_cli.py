"""Local deterministic executor; never calls a model or reads credentials."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

req = json.loads(Path(sys.argv[1]).read_text())
scenario = req['contract']['prompt']
sid = req.get('resume') or 'sess_fixture'


def emit(kind, **fields):
    print(json.dumps({'type': kind, 'sessionId': sid, **fields}), flush=True)


if scenario == 'empty':
    raise SystemExit(0)
if scenario == 'invalid':
    print('secret-raw-invalid-output', flush=True)
    raise SystemExit(0)
if scenario == 'stderr_deny':
    print('No permission client configured for Bash SECRET_STDERR', file=sys.stderr, flush=True)
    time.sleep(30)
emit('session.created', payload={'secret': 'private-session-data'})
if scenario != 'no_model':
    emit('session.updated', payload={'modelId': 'fixture-model', 'providerId': 'fixture-provider'})
effort = req.get('reasoning_effort', req['contract'].get('reasoning_effort'))
if effort:
    emit('reasoning.selected', payload={'requested':effort,'effective':effort})
emit('model.streaming', payload={'kind': 'reasoning_delta', 'delta': 'PRIVATE_REASONING_SENTINEL'})
emit('tool.updated', payload={'kind': 'started', 'toolName': 'Read', 'toolCallId': 'tool_1',
                             'input': {'secret': 'PRIVATE_TOOL_SENTINEL'}})
if scenario == 'tool_progress':
    for i in range(20):
        emit('tool.updated', payload={'kind': 'started', 'toolName': 'Write', 'toolCallId': 'pulse_' + str(i)})
        time.sleep(.12)
        Path(req['cwd'], 'allowed.txt').write_text('version ' + str(i))
        emit('tool.updated', payload={'kind': 'result', 'toolName': 'Write', 'toolCallId': 'pulse_' + str(i)})
if scenario in ('todo_loop', 'read_loop', 'noop_write_loop', 'shell_loop', 'repeated_test_loop'):
    tool = {'todo_loop': 'TodoWrite', 'read_loop': 'Read', 'noop_write_loop': 'Write',
            'shell_loop': 'Bash', 'repeated_test_loop': 'Bash'}[scenario]
    while True:
        emit('tool.updated', payload={'kind': 'started', 'toolName': tool, 'toolCallId': 'loop'})
        if tool == 'Write':
            Path(req['cwd'], 'allowed.txt').write_text('unchanged')
        fields = {'kind': 'result', 'toolCallId': 'loop', 'result': {'success': True}}
        if tool == 'Bash':
            fields['command'] = {'category': 'test' if scenario == 'repeated_test_loop' else 'other',
                                 'id': 'a' * 64, 'exit_code': 1 if scenario == 'repeated_test_loop' else 0,
                                 'status': 'failed' if scenario == 'repeated_test_loop' else 'completed'}
        emit('tool.updated', payload=fields)
        time.sleep(.08)
if scenario == 'error_loop':
    while True:
        emit('tool.updated', payload={'kind': 'started', 'toolName': 'Read', 'toolCallId': 'err'})
        emit('tool.updated', payload={'kind': 'error', 'toolCallId': 'err', 'error': {'message': 'ENOENT PRIVATE_PATH_SECRET'}})
        time.sleep(.05)
if scenario == 'deny':
    emit('permission.resolved', payload={'decision': 'deny', 'toolName': 'Bash',
                                         'reason': 'No permission client configured; SECRET'})
    time.sleep(30)
if scenario == 'failturn':
    emit('turn.failed', payload={'error': 'PRIVATE_EXCEPTION_SENTINEL'})
    raise SystemExit(0)
if scenario in ('hang', 'heartbeat', 'child'):
    if scenario == 'child':
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        Path(req['cwd'], 'child.pid').write_text(str(child.pid))
    while True:
        if scenario == 'heartbeat':
            emit('model.streaming', payload={'kind': 'reasoning_delta', 'delta': 'PRIVATE_REASONING_SENTINEL'})
        time.sleep(.08)
if scenario in ('edit', 'forbidden'):
    Path(req['cwd'], 'allowed.txt' if scenario == 'edit' else 'baseline.txt').write_text('new content')
if scenario in ('delivery_code', 'delivery_empty', 'delivery_stub'):
    Path(req['cwd'], 'allowed.txt').write_text({'delivery_code':'def value(): return 42\n',
        'delivery_empty':'','delivery_stub':'def value(): pass\n'}[scenario])
if scenario == 'symlink':
    Path(req['cwd'], 'link').symlink_to('/tmp')
if scenario == 'delay':
    time.sleep(.4)
emit('tool.updated', payload={'kind': 'result', 'toolName': 'Read', 'toolCallId': 'tool_1',
                             'result': {'output': 'PRIVATE_OUTPUT_SENTINEL'}})
response = 'NEED-CLARIFICATION: specify input' if scenario == 'clarify' else 'done'
emit('result', response=response, usage={'inputTokens': 100, 'cacheReadTokens': 80,
     'modelRequestCount': 1, 'secret': 'PRIVATE_USAGE_SENTINEL'},
     projection={'status': 'idle', 'turnCount': 1, 'contextUsed': 100, 'contextWindow': 200000,
                 'private': 'PRIVATE_PROJECTION_SENTINEL'})
if scenario == 'duplicate':
    emit('result', response='duplicate')
raise SystemExit(9 if scenario == 'nonzero' else 0)
