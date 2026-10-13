"""符号入库门禁 CLI 回归（#31 规范源归位）：公共边界 = 真实命令行。

单源/锚定：规范源脚本随 skill `scripts/` 携带，默认库与 catalog 从脚本
自身位置解析（<skill>/assets/component-library），任意 cwd 调用结果一致；
脱离该布局的孤立副本必须 fail-closed，不得空转放过。

全量基线钉扎：当前库有两件已知缺陷符号——旧 fsov 临时件（端口与 catalog
失配）与接通位快卸接头（无端口组/无类型/尺寸带 mm 单位）——门禁必须如实
报 ERROR 且退出码 1。本测试钉住该红基线；缺陷转正时更新此处的期望即是
验收动作，不得为绿灯隐藏/跳过真实错误，WARN 也不得记作工程签认。
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
GATE = SKILL / 'scripts' / 'check_symbol.py'
LIB = SKILL / 'assets' / 'component-library'

CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
                 PYTHONDONTWRITEBYTECODE='1')


def run_gate(arguments, cwd):
    # 子进程强制 UTF-8 输出并显式按 UTF-8 解码，避免宿主代码页干扰中文报文断言。
    result = subprocess.run([sys.executable, str(GATE), *map(str, arguments)],
                            cwd=str(cwd), capture_output=True, timeout=120,
                            env=CHILD_ENV)
    out = (result.stdout or b'').decode('utf-8', 'replace')
    out += (result.stderr or b'').decode('utf-8', 'replace')
    return result.returncode, out


class SymbolGateCLI(unittest.TestCase):
    def test_explicit_symbol_from_arbitrary_cwd_passes(self):
        good = LIB / 'accumulator.svg'
        with tempfile.TemporaryDirectory(prefix='symbol-gate-cwd-') as d:
            rc, out = run_gate([good], cwd=d)          # cwd 与脚本/库位置无关
            self.assertEqual(rc, 0, out)
            self.assertIn('[PASS ] accumulator.svg', out)
            self.assertIn('1 个文件, 0 个有 ERROR, 1 个可正式出图', out)
            rc, out = run_gate(['accumulator.svg'], cwd=str(LIB))  # 相对路径按 cwd 解析
            self.assertEqual(rc, 0, out)
            self.assertIn('[PASS ] accumulator.svg', out)

    def test_full_library_scan_reports_known_defects_and_exit_1(self):
        rc, out = run_gate(['--all'], cwd=tempfile.gettempdir())
        self.assertEqual(rc, 1, out)
        self.assertIn('---- 22 个文件, 2 个有 ERROR, 2 个可正式出图 ----', out)
        self.assertIn('[ERROR] fsov-provisional-stroke.svg', out)
        self.assertIn('C4 目录声明的端口在 SVG 中缺失: main_lower', out)
        self.assertIn('C4 目录声明的端口在 SVG 中缺失: main_upper', out)
        self.assertIn('C5 SVG 存在目录未声明的端口: command', out)
        self.assertIn('[ERROR] quick-disconnect-coupling.svg', out)
        self.assertIn('C3 缺 data-component-type', out)
        self.assertIn('C8 data-symbol-form=None', out)
        self.assertIn('C4 缺 connection-points 组', out)
        self.assertIn('C9 width 带单位 "mm"', out)
        self.assertIn('C9 height 带单位 "mm"', out)

    def test_missing_explicit_file_fails_closed_without_traceback(self):
        with tempfile.TemporaryDirectory(prefix='symbol-gate-miss-') as d:
            rc, out = run_gate([Path(d) / 'nope.svg'], cwd=d)
        self.assertEqual(rc, 1, out)
        self.assertIn('nope.svg', out)
        self.assertIn('文件不存在', out)
        self.assertNotIn('Traceback', out)

    def test_unanchored_copy_fails_closed_when_library_missing(self):
        # 孤立副本按自身位置找 <脚本目录>/../assets/component-library，
        # 缺失必须以退出码 1 拒绝，不得按 0 文件空转放行。
        with tempfile.TemporaryDirectory(prefix='symbol-gate-solo-') as d:
            solo = Path(d) / 'check_symbol.py'
            solo.write_text(GATE.read_text(encoding='utf-8'), encoding='utf-8')
            result = subprocess.run([sys.executable, str(solo)],
                                    cwd=d, capture_output=True, timeout=60,
                                    env=CHILD_ENV)
        out = (result.stdout or b'').decode('utf-8', 'replace')
        out += (result.stderr or b'').decode('utf-8', 'replace')
        self.assertEqual(result.returncode, 1, out)
        self.assertIn('库目录不存在', out)

    def test_lib_sandbox_override_scans_only_that_library(self):
        with tempfile.TemporaryDirectory(prefix='symbol-gate-lib-') as d:
            lib = Path(d) / 'lib'
            lib.mkdir()
            (lib / 'accumulator.svg').write_bytes((LIB / 'accumulator.svg').read_bytes())
            (lib / 'component-catalog.json').write_bytes(
                (LIB / 'component-catalog.json').read_bytes())
            rc, out = run_gate(['--lib', lib], cwd=d)
        self.assertEqual(rc, 0, out)
        self.assertIn('1 个文件, 0 个有 ERROR, 1 个可正式出图', out)
        self.assertNotIn('[ERROR]', out)

    def test_empty_lib_directory_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix='symbol-gate-empty-') as d:
            lib = Path(d) / 'empty-lib'
            lib.mkdir()
            rc, out = run_gate(['--lib', lib], cwd=d)
        self.assertEqual(rc, 1, out)
        self.assertIn('无可检 SVG', out)


if __name__ == '__main__':
    unittest.main()
