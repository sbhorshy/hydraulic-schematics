"""Project symbol-gate entrypoints delegate to the canonical skill script (#31)."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SKILL=ROOT/'.agents/skills/hydraulic-schematic'
ENTRY=ROOT/'1#系统原理图'/'check_symbol.py'
LIB=SKILL/'assets/component-library'

CHILD_ENV=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1',
               PYTHONDONTWRITEBYTECODE='1')


def run_entry(arguments,cwd):
    # 子进程强制 UTF-8 输出并显式按 UTF-8 解码，避免宿主代码页干扰中文报文断言。
    r=subprocess.run([sys.executable,str(ENTRY),*map(str,arguments)],
        cwd=str(cwd),capture_output=True,timeout=120,env=CHILD_ENV)
    out=(r.stdout or b'').decode('utf-8','replace')+(r.stderr or b'').decode('utf-8','replace')
    return r.returncode,out


class SymbolGateEntry(unittest.TestCase):
    def test_project_entry_passes_explicit_symbol_from_any_cwd(self):
        with tempfile.TemporaryDirectory(prefix='symbol-entry-') as d:
            rc,out=run_entry([LIB/'accumulator.svg'],cwd=d)
            self.assertEqual(rc,0,out)
            self.assertIn('[PASS ] accumulator.svg',out)

    def test_project_entry_default_scan_hits_skill_library_red_baseline(self):
        # 无位置参数：由规范源全量扫 skill 自带库。当前基线为红（两件已知
        # 缺陷符号），必须如实退出码 1——薄入口不得给出第二套结果。
        with tempfile.TemporaryDirectory(prefix='symbol-entry-all-') as d:
            rc,out=run_entry([],cwd=d)
            self.assertEqual(rc,1,out)
            self.assertIn('---- 22 个文件, 2 个有 ERROR, 2 个可正式出图 ----',out)
            self.assertIn('[ERROR] quick-disconnect-coupling.svg',out)
            self.assertIn('[ERROR] fsov-provisional-stroke.svg',out)

    def test_project_entry_warns_without_certifying_pending_check_valve(self):
        # check-valve.svg 流向仍 PENDING 工程确认：门禁以退出码 0 放行但只给
        # WARN 披露，不得输出 PASS（WARN 不构成工程签认）。
        with tempfile.TemporaryDirectory(prefix='symbol-entry-warn-') as d:
            rc,out=run_entry([LIB/'check-valve.svg'],cwd=d)
            self.assertEqual(rc,0,out)
            self.assertIn('[WARN ] check-valve.svg',out)
            self.assertIn('C12 注释含未确认项',out)
            self.assertNotIn('[PASS ]',out)

    def test_relocated_entry_resolves_skill_by_relative_layout(self):
        # 与 test_coordinate_entrypoints 同款假仓库：入口按自身相对布局
        # （../.agents/skills/...）解析规范源，不依赖真实仓库根。
        with tempfile.TemporaryDirectory(prefix='symbol-entry-fake-') as d:
            root=Path(d);fake=root/'repo';project=fake/'1#系统原理图';project.mkdir(parents=True)
            library=fake/'.agents/skills/hydraulic-schematic';library.parent.mkdir(parents=True)
            library.symlink_to(SKILL,target_is_directory=True)
            target=project/'check_symbol.py'
            target.write_text(ENTRY.read_text(encoding='utf-8'),encoding='utf-8')
            result=subprocess.run([sys.executable,str(target),
                str(library/'assets/component-library/accumulator.svg')],
                cwd=str(root),capture_output=True,timeout=120,env=CHILD_ENV)
            out=(result.stdout or b'').decode('utf-8','replace')+(result.stderr or b'').decode('utf-8','replace')
            self.assertEqual(result.returncode,0,out)
            self.assertIn('[PASS ] accumulator.svg',out)


if __name__=='__main__':unittest.main()
