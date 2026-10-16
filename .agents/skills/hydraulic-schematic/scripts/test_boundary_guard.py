"""Legacy-layout migration must not silently apply 1# boundary terminals (#91)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import proto_optimize as O
from test_entrypoints import SKILL

MIGRATE = str(SKILL / 'scripts/migrate_layout.py')


def legacy(with_terminals):
    layout = {
        'canvas': {'width': 1680, 'height': 1390}, 'canvas_shift_x': 30,
        'nodes': {'RF': {'x': 1200, 'y': 1012, 'w': 100, 'h': 194, 'rot': 180}},
        'buses': {'USERR': {'kind': 'v', 'x': 1646}},
        'externs': {'END': {'x': 1480, 'y': 300, 'anchor': 'left', 'label': 'END'}},
        'lanes': [890], 'vlanes': [20, 290],
        'legend': {'x': 380, 'y': 1020, 'w': 540, 'h': 290},
        'title_block': {'x': 40, 'y': 1330, 'w': 1600, 'h': 56},
    }
    if with_terminals:
        layout['boundary_terminals'] = [[1480, 300]]
    return layout


class MigrateBoundaryGuard(unittest.TestCase):
    def migrate(self, layout, *flags):
        directory = tempfile.TemporaryDirectory(prefix='boundary-guard-')
        self.addCleanup(directory.cleanup)
        source = Path(directory.name) / 'old.layout.json'
        target = Path(directory.name) / 'root.layout.json'
        source.write_text(json.dumps(layout))
        run = subprocess.run([sys.executable, MIGRATE, str(source), '-o', str(target), *flags],
                             capture_output=True, text=True)
        return run, target

    def test_missing_terminals_warn_on_stderr_and_name_the_1_hash_default(self):
        run, target = self.migrate(legacy(with_terminals=False))
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('boundary_terminals', run.stderr)
        self.assertIn('1#', run.stderr)
        migrated = json.loads(target.read_text())
        self.assertEqual(migrated['boundary_terminals'][0], [1510.0, 300.0])
        self.assertTrue(any('boundary_terminals' in line for line in migrated['revision_log']),
                        '回退到 1# 缺省必须写入 revision_log 以便追溯')

    def test_strict_mode_rejects_missing_terminals_and_writes_nothing(self):
        run, target = self.migrate(legacy(with_terminals=False), '--strict-boundary')
        self.assertEqual(run.returncode, 1)
        self.assertIn('boundary_terminals', run.stderr)
        self.assertFalse(target.exists())

    def test_declared_terminals_stay_silent_even_in_strict_mode(self):
        for flags in ((), ('--strict-boundary',)):
            run, target = self.migrate(legacy(with_terminals=True), *flags)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertNotIn('boundary_terminals', run.stderr)
            self.assertEqual(json.loads(target.read_text())['boundary_terminals'], [[1510.0, 300.0]])


class OptimizerDocstring(unittest.TestCase):
    def test_docstring_no_longer_claims_a_1_hash_default(self):
        # 代码里缺省已是空（无豁免），文档字符串必须与之一致。
        self.assertNotIn('缺省值为 1# 系统实测知识', O.__doc__)
        self.assertIn('缺省无豁免', O.__doc__)


if __name__ == '__main__':
    unittest.main()
