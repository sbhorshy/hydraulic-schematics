"""Two small real CLI calls: edit + controller test, then explicit session feedback."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from bridge_contract import atomic_json


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cwd = output / 'workspace'
    cwd.mkdir()
    store = bridge.Store(output / 'state')
    req = {'cwd': str(cwd), 'mode': 'edit', 'resume': None, 'timeout': 180,
           'idle_timeout': 90, 'run_tests': True, 'contract': {
               'version': 1,
               'prompt': '这是 bridge 的最小集成测试。用 Write 创建当前目录 answer.txt，精确写入 BRIDGE_V2_OK 和一个换行。只改这一个文件，不读其他目录，不写记忆，不调用 Bash、Python、子代理或任何其他执行器。控制端会测试。完成后简短说明。',
               'allowed_files': ['answer.txt'], 'forbidden_files': [],
               'tests': [{'id': 'exact-content', 'argv': [sys.executable, '-c',
                          "from pathlib import Path; assert Path('answer.txt').read_text() == 'BRIDGE_V2_OK\\n'; print('exact content passed')"],
                          'timeout': 10}]}}
    tid = store.create(req)
    result = bridge.worker(store, tid)
    assert result['status'] == 'completed' and result['validation_status'] == 'passed', result
    followup = bridge.feedback_request(store, tid)
    resumed = store.create(followup)
    second = bridge.worker(store, resumed)
    assert second['status'] == 'completed' and second['validation_status'] == 'passed', second
    assert second['sessionId'] == result['sessionId'], second
    summary = {'passed': 2, 'session_id': result['sessionId'], 'first_task': tid, 'feedback_task': resumed,
               'verification': [result['validation_status'], second['validation_status']],
               'usage': [result['usage'], second['usage']], 'source_files': ['answer.txt']}
    atomic_json(output / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
