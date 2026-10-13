# -*- coding: utf-8 -*-
"""check_symbol.py CLI 回归(#31 第一轮评审返工)。

全部走真实子进程调用(与人工/CI 口径一致),覆盖三件事:

- 坏 catalog fail-closed:缺失/不可读/非法 JSON/顶层或 components
  结构不符/components 为空/component_type 空白或重复/ports 非列表/
  端口 id 重复,一律退出码 1 + [ERROR],不得降级为 WARN 放行——
  第一轮评审实测:`{}` 与 `{"components": []}` 曾以 exit 0/WARN
  放过,端口对账 C4/C5 静默消失(见 31-first-review-invalid-catalog.json)。
- --all 与显式文件互斥:同时给出是 argparse 用法错误(退出码 2),
  显式文件不得被静默丢弃。
- 未改动的默认库基线:仍只有两件已知 ERROR(fsov-provisional-stroke.svg
  端口双向失配、quick-disconnect-coupling.svg 无端口组),fsov 的
  C4/C5 失配行必须在场,证明 catalog 真的加载并参与了对账;
  合法 catalog 下未登记类型仍按 C3 WARN(存量符号口径不变)。

只断言门禁自身的结构行为,不新增水力语义。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CHECK_SYMBOL = os.path.join(HERE, 'check_symbol.py')
LIB = os.path.join(os.path.dirname(HERE), 'assets', 'component-library')
REAL_CATALOG = os.path.join(LIB, 'component-catalog.json')
CHECK_VALVE = os.path.join(LIB, 'check-valve.svg')


def run_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    return subprocess.run(
        [sys.executable, CHECK_SYMBOL] + [str(a) for a in args],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=env, timeout=60)


def write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


class BadCatalogFailClosedTest(unittest.TestCase):
    """坏 catalog 必须整门禁拦下,不许 WARN 放行后静默关闭 C4/C5。"""

    # (名称, catalog 文件内容, [ERROR] 行应含的关键词)
    CASES = [
        ('empty-object', '{}', "缺 'components' 键"),
        ('empty-components', '{"components": []}', '为空列表'),
        ('invalid-json', '{"components": [ {oops', '不是合法 JSON'),
        ('top-level-list', '[{"component_type": "x", "ports": []}]',
         '顶层须为 JSON 对象'),
        ('components-not-list', '{"components": {"x": 1}}',
         "'components' 须为列表"),
        ('entry-not-object', '{"components": ["x"]}', '须为对象'),
        ('blank-type',
         '{"components": [{"component_type": "  ", "ports": []}]}',
         'component_type 缺失或空白'),
        ('duplicate-type',
         '{"components": ['
         '{"component_type": "dup_type", "ports": [{"id": "a"}]}, '
         '{"component_type": "dup_type", "ports": [{"id": "b"}]}]}',
         '重复登记'),
        ('ports-not-list',
         '{"components": [{"component_type": "x", "ports": {"id": "a"}}]}',
         "'ports' 须为列表"),
        ('ports-missing',
         '{"components": [{"component_type": "x"}]}',
         "'ports' 须为列表"),
        ('blank-port-id',
         '{"components": [{"component_type": "x", "ports": [{"id": "  "}]}]}',
         '缺非空 id'),
        ('duplicate-port-id',
         '{"components": [{"component_type": "x", '
         '"ports": [{"id": "a"}, {"id": "a"}]}]}',
         '端口 id='),
    ]

    def test_malformed_catalogs_exit_1_with_error(self):
        # 复刻评审实测口径:合法 check-valve.svg + 坏 --catalog。
        for name, content, expect in self.CASES:
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as tmp:
                    cat = os.path.join(tmp, 'bad-catalog.json')
                    write(cat, content)
                    r = run_cli(CHECK_VALVE, '--catalog', cat)
                self.assertEqual(r.returncode, 1, name)
                self.assertIn('[ERROR]', r.stdout)
                self.assertIn(expect, r.stdout)
                # 修复前的漏点:空目录曾按 WARN 放行、exit 0。
                self.assertNotIn('[WARN ]', r.stdout)
                self.assertNotIn('不在目录中', r.stdout)

    def test_missing_catalog_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run_cli(CHECK_VALVE, '--catalog',
                        os.path.join(tmp, 'no-such-catalog.json'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('catalog 不存在', r.stdout)

    def test_unreadable_catalog_exits_1(self):
        # 路径是目录:存在但不可读,同拦。
        with tempfile.TemporaryDirectory() as tmp:
            r = run_cli(CHECK_VALVE, '--catalog', tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn('catalog 不可读', r.stdout)


class SeverityRulesPreservedTest(unittest.TestCase):
    """合法 catalog 下,未登记类型仍按 C3 WARN——fail-closed 只拦
    坏 catalog,不改变存量符号的 WARN 口径。"""

    def test_valid_catalog_unknown_type_warns_not_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            cat = os.path.join(tmp, 'mini-catalog.json')
            write(cat, json.dumps({'components': [
                {'component_type': 'unrelated_type',
                 'ports': [{'id': 'a'}]}]}))
            r = run_cli(CHECK_VALVE, '--catalog', cat)
        self.assertEqual(r.returncode, 0)
        self.assertIn('C3 data-component-type=check_valve 不在目录中',
                      r.stdout)
        self.assertNotIn('[ERROR]', r.stdout)

    def test_sandbox_real_catalog_clean_symbol_exits_zero(self):
        # 正控:真实 catalog + 已登记符号,门禁活着且不过度拦截。
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(REAL_CATALOG, os.path.join(tmp,
                                                   'component-catalog.json'))
            shutil.copy(CHECK_VALVE, os.path.join(tmp, 'check-valve.svg'))
            r = run_cli('--lib', tmp)
        self.assertEqual(r.returncode, 0)
        self.assertIn('check-valve.svg', r.stdout)
        self.assertNotIn('[ERROR]', r.stdout)


class AllFlagConflictTest(unittest.TestCase):
    """--all 与显式文件互斥:显式文件(哪怕不存在)不得被静默丢弃。"""

    def test_all_with_missing_file_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run_cli('--all', os.path.join(tmp, 'missing.svg'))
        self.assertEqual(r.returncode, 2)      # argparse 用法错误
        self.assertIn('usage:', r.stderr)
        self.assertIn('互斥', r.stderr)
        # 不得装作跑完了扫描(exit 0 / 汇总行都不许出现)。
        self.assertNotIn('个文件', r.stdout)

    def test_all_with_existing_file_is_usage_error(self):
        r = run_cli('--all', CHECK_VALVE)
        self.assertEqual(r.returncode, 2)
        self.assertIn('互斥', r.stderr)


class DefaultLibraryBaselineTest(unittest.TestCase):
    """未改动的默认库:退出码 1,ERROR 恰为两件已知挂账,且 fsov 的
    C4/C5 端口失配在场(catalog 真实加载的回归指纹)。"""

    def test_baseline_two_known_errors_with_catalog_crosscheck(self):
        r = run_cli()
        self.assertEqual(r.returncode, 1)
        err_files = {ln.split('] ', 1)[1].strip()
                     for ln in r.stdout.splitlines()
                     if ln.startswith('[ERROR] ')}
        self.assertEqual(
            err_files,
            {'fsov-provisional-stroke.svg', 'quick-disconnect-coupling.svg'})
        # catalog 参与对账的直接证据(空 catalog 时这两行会消失,
        # 换成 C3 不在目录中 WARN)。
        self.assertIn('C4 目录声明的端口在 SVG 中缺失: main_upper',
                      r.stdout)
        self.assertIn('C5 SVG 存在目录未声明的端口', r.stdout)


if __name__ == '__main__':
    unittest.main()
