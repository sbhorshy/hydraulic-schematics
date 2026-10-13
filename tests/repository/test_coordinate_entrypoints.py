"""Repository entrypoints use the canonical root-coordinate contract."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.agents/skills/hydraulic-schematic/scripts'))
from test_entrypoints import make_render_workspace, SKILL


class CoordinateEntrypoints(unittest.TestCase):
    def test_project_wrappers_honor_an_explicit_workspace_and_current_gates(self):
        with tempfile.TemporaryDirectory(prefix='project-entry-contract-') as directory:
            root=Path(directory);work=make_render_workspace(root,SKILL/'assets/fixtures/l0-small-seed')
            fake=root/'repo';project=fake/'1#系统原理图';project.mkdir(parents=True)
            library=fake/'.agents/skills/hydraulic-schematic';library.parent.mkdir(parents=True);library.symlink_to(SKILL,target_is_directory=True)
            for name in ('render.py','validate_sheet.py'):
                target=project/name;shutil.copy2(ROOT/'1#系统原理图'/name,target)
                run=subprocess.run([sys.executable,str(target),str(work)],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertTrue((work/'1#系统原理图.svg').is_file())
            self.assertTrue((work/'validation-report.json').is_file())
            self.assertFalse((project/'1#系统原理图.svg').exists())

    def test_retired_cdf_generators_fail_before_touching_the_working_inputs(self):
        with tempfile.TemporaryDirectory(prefix='retired-cdf-entry-') as directory:
            for relative in ('1#系统原理图/build_render.py',
                             '1#系统原理图/CDF-001装配图/render_l0_sheet.py',
                             '1#系统原理图/CDF-001装配图/validate_sheet.py',
                             '1#系统原理图/CDF-001装配图/auto_space.py'):
                with self.subTest(entry=relative):
                    copied=Path(directory)/'entry.py';shutil.copy2(ROOT/relative,copied)
                    run=subprocess.run([sys.executable,str(copied)],cwd=directory,capture_output=True,text=True)
                    self.assertNotEqual(run.returncode,0)
                    self.assertIn('规范源',run.stdout+run.stderr)


if __name__=='__main__':unittest.main()
