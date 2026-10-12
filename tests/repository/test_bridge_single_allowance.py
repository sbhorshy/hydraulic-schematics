"""#23 单跳线许可(allowance=1)的端到端闸门:真实 1# 原料临时副本。

复现 ../bridge-second-review.json 的两个事实,不 mock registry/validator:
  - 落盘候选(2.4:EMP-001 mirror=y、CDF-001 (730,430) rot270、@CASE x=700
    + 第二轮间距微调六处,bridge_policy=current-1-verified-single-bridge-
    20261012):真实 renderer 生成 1 处合规桥,B1 raw=1 / pass / allowance=1
    / verified=1,fail0,且 B3≤1.447、B4≥16、B5≥43 满足 #23 原到站口径;
  - 同候选仅改 PF-001.y 254→354(临时副本,正式 seed 不动):真实 renderer
    自动生成 2 处合规桥,V4/V14 无失败,唯一失败 V19(B1 交叉 2 > 放行 1),
    verified_bridges=2——许可 1 时第二处桥必须拒绝。
政策来自生产登记表,内容绑定 intent 字节(副本未改 intent,SHA 与登记
一致,见 test_bridge_registration.py 的字节对账)。
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from repository_context import REPO, SKILL

POLICY_ID = 'current-1-verified-single-bridge-20261012'
SHEET = REPO / '1#系统原理图'
PROJECT_FILES = ('1#系统.intent.yaml', '1#系统.layout.json',
                 '1#系统组件.json', 'component-catalog.json')


def budget_item(report, budget_id):
    return next(item for item in report['composition_budget']['items']
                if item['id'] == budget_id)


def b1_item(report):
    return budget_item(report, 'B1')


class SingleBridgeAllowance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='bridge-single-')
        cls.addClassCleanup(cls.tmp.cleanup)

    def candidate(self, name):
        work = Path(self.tmp.name) / name
        work.mkdir()
        for filename in PROJECT_FILES:
            shutil.copy2(SHEET / filename, work / filename)
        shutil.copytree(SHEET / 'symbols', work / 'symbols')
        return work

    def run_chain(self, work):
        for script in ('render_l0_sheet.py', 'validate_sheet.py'):
            done = subprocess.run(
                [sys.executable, str(SKILL / 'scripts' / script), str(work)],
                cwd=work, capture_output=True, text=True, timeout=300)
            self.assertEqual(done.returncode, 0, script + done.stdout + done.stderr)
        return json.loads(
            (work / 'validation-report.json').read_text(encoding='utf-8'))

    def test_registered_candidate_passes_with_exactly_one_verified_bridge(self):
        # 原候选(生产 1# 当前落盘字节):单桥在登记放行内,整链 fail0。
        work = self.candidate('candidate')
        report = self.run_chain(work)
        self.assertEqual(report['fail_count'], 0, report['checks'])
        b1 = b1_item(report)
        self.assertEqual(b1['measured'], 1)
        self.assertEqual(b1['status'], 'pass')
        self.assertEqual(b1['policy'], POLICY_ID)
        self.assertEqual(b1['allowance'], 1)
        self.assertEqual(b1['verified_bridges'], 1)
        # EMP 镜像真实过闸渲染,不是拓扑错配冒充
        svg = (work / '1#系统原理图.svg').read_text(encoding='utf-8')
        self.assertIn('data-mirror="y"', svg)
        # #23 原到站口径(docs/specs/ready-tickets-20261009-review.md:30,
        # #22 决议原值 1.447/16/43):候选须不劣于 fail0/B3≤1.447/B4≥16/
        # B5≥43。2.4 间距候选实测 1.281/18/44;近期残差图(B3 10/B5 24 档)
        # 不满足——这些断言保证旧不合格布局无法借本测试变绿,也不能以
        # 残差图替代原始基线关票。
        self.assertLessEqual(budget_item(report, 'B3')['measured']['max'],
                             1.447)
        self.assertGreaterEqual(budget_item(report, 'B4')['measured'], 16)
        self.assertGreaterEqual(budget_item(report, 'B5')['measured'], 43)

    def test_second_verified_bridge_exceeds_allowance_one(self):
        # 仅 PF-001.y 254→354:两处桥各自合规(V4/V14 无失败),拒绝只来自
        # B1 预算——证明"许可 1 下第二处桥拒绝"这一特例,而不是靠
        # 其他 topology 错配遮盖。
        work = self.candidate('second')
        layout_path = work / '1#系统.layout.json'
        layout = json.loads(layout_path.read_text(encoding='utf-8'))
        self.assertEqual(layout['nodes']['PF-001']['y'], 254)
        layout['nodes']['PF-001']['y'] = 354
        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2),
                               encoding='utf-8')
        done = subprocess.run(
            [sys.executable, str(SKILL / 'scripts' / 'render_l0_sheet.py'), str(work)],
            cwd=work, capture_output=True, text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        checked = subprocess.run(
            [sys.executable, str(SKILL / 'scripts' / 'validate_sheet.py'), str(work)],
            cwd=work, capture_output=True, text=True, timeout=300)
        report = json.loads((work / 'validation-report.json').read_text(encoding='utf-8'))
        self.assertEqual(checked.returncode, 1)  # 唯一失败族 V19(B1 超预算)
        failures = [c for c in report['checks'] if c['result'] == 'fail']
        self.assertTrue(failures, report['checks'])
        self.assertFalse([c for c in failures if c['id'] in ('V4', 'V14')],
                         failures)  # 两处桥都合规,失败与桥画法无关
        self.assertEqual({c['id'] for c in failures}, {'V19'}, failures)
        self.assertTrue(all('放行' in c['detail'] for c in failures), failures)
        b1 = b1_item(report)
        self.assertEqual(b1['measured'], 2)
        self.assertEqual(b1['status'], 'fail')
        self.assertEqual(b1['policy'], POLICY_ID)
        self.assertEqual(b1['allowance'], 1)
        self.assertEqual(b1['verified_bridges'], 2)
        self.assertIn('交叉 2 处 > 放行 1 处', b1['detail'])


if __name__ == '__main__':
    unittest.main()
