"""A copied skill exposes working public tools and importable registered tests."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
SKILL=REPO/'.agents/skills/hydraulic-schematic'


class StandaloneSkill(unittest.TestCase):
    def test_copied_skill_discovers_its_tests_and_runs_preflight(self):
        with tempfile.TemporaryDirectory(prefix='standalone-skill-') as directory:
            package=Path(directory)/'skill'
            shutil.copytree(SKILL,package,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            # Use the selftest's public suite manifest, not unrelated historical
            # examples. Import its actual registered suites through unittest.
            manifest=subprocess.run([sys.executable,str(package/'scripts/selftest.py'),'--list-suites'],
                cwd=directory,capture_output=True,text=True)
            self.assertEqual(manifest.returncode,0,manifest.stdout+manifest.stderr)
            selection=json.loads(manifest.stdout)
            self.assertEqual(selection['scope'],'standalone-skill')
            discover=subprocess.run([sys.executable,'-c',
                'import unittest,sys; loader=unittest.TestLoader(); '
                'suite=loader.loadTestsFromNames(sys.argv[1:]); '
                'print("discovered",suite.countTestCases()); '
                'print("\\n".join(loader.errors)); '
                'sys.exit(1 if loader.errors or not suite.countTestCases() else 0)',*selection['suites']],
                cwd=package/'scripts',capture_output=True,text=True)
            self.assertEqual(discover.returncode,0,discover.stdout+discover.stderr)
            result=subprocess.run([sys.executable,str(package/'scripts/preflight.py'),
                str(package/'assets/fixtures/l0-small-seed/1#系统.intent.yaml'),'--json'],
                cwd=directory,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
