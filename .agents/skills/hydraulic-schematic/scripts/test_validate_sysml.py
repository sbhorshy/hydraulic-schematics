# -*- coding: utf-8 -*-
"""Tests for validate_sysml (#52 窄版 SysML→L0 校核链路薄入口).

Run from the repository root:
    python -m unittest discover -s .agents/skills/hydraulic-schematic/scripts \
        -p test_validate_sysml.py -v

覆盖：正例（l0-small-seed.sysml + l0-small-seed 布局 seed）真实走
转换 → preflight → validate_driver → SVG → PNG → 校核 → 追溯链，
自动校验状态与 delivery 口径如实断言（本机无 Chrome 时局部回读/显示测量
按宿主事实记 fail/not_checked，不桩掉链路）；显式 catalog 全链正例
（快照重放与 canonical SHA 核对，审查项1）；追溯链（源哈希+connect 行号
→ intent 哈希+锚点 → SVG 拓扑 manifest）自洽且可核验、防后处理冒充；
桥接边映射的规范化比对（边界隔离单测，审查项3，非出图证明）；
blocked 1# 冻结模型在任何布局/渲染前被拒绝并失效旧产物；模板门禁随源
目录进入暂存不被绕过；路径保护（skill 源树/祖先/symlink 别名，含
--ref 参照输入）与输入不可改性；既有 intent 入口兼容由 test_driver
套件继续覆盖。

Windows 无特权环境用目录联接（junction）表达 symlink 别名——resolve 后
同一判定；POSIX 走 os.symlink。
"""

import argparse
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sysml_to_intent as sti          # noqa: E402
import topology_reconciliation as tr   # noqa: E402
import validate_driver as vd           # noqa: E402
import validate_sysml as vs            # noqa: E402

SKILL = Path(HERE).resolve().parent
FIXTURES = SKILL / 'assets' / 'fixtures' / 'sysml-l0'
POSITIVE_SYSML = FIXTURES / 'l0-small-seed.sysml'
OTHER_MODEL = FIXTURES / 'demo-positive.sysml'
SEED = SKILL / 'assets' / 'fixtures' / 'l0-small-seed' / '1#系统.layout.json'
BLOCKED = FIXTURES / 'blocked-project.sysml'
CANONICAL_CATALOG = SKILL / 'assets' / 'component-library' / \
    'component-catalog.json'
MANIFEST_JSON = '1#系统原理图-topology.json'
# 冻结的 blocked 原模型（1#系统.sysml 逐字节副本）哈希——与
# test_sysml_to_intent 同口径，套件独立于外层仓库文件。
FROZEN_BLOCKED_SHA256 = ('08e9fd67f75c7ef4b6b1b20288cb814712868d2643ca122e8'
                         'e25a44a26f0aeb9')

VALIDATE_SYSML = Path(HERE) / 'validate_sysml.py'
CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
                 PYTHONDONTWRITEBYTECODE='1')

# 独立 oracle（从模型文本直读，不借转换器推导）：l0-small-seed.sysml 的
# 节点/边界/连接与 assets/fixtures/l0-small-seed/1#系统.intent.yaml 对齐。
ORACLE_NODES = {
    'TANK-001': 'bootstrap_reservoir',
    'EDP-001': 'engine_driven_pump',
    'PF-001': 'pressure_filter',
}
ORACLE_EDGES = [
    {'TANK-001.suction_out', 'EDP-001.suction'},
    {'EDP-001.pressure_out', 'PF-001.inlet'},
    {'PF-001.outlet', 'USR-001'},
]
ORACLE_EXTERN = {'USR-001': 'outlet'}


def read_bytes(path):
    return Path(path).read_bytes()


def make_directory_alias(link, target):
    """symlink 别名：POSIX 用 symlink；Windows 无特权环境用目录联接
    （resolve 后同一判定，保护语义一致）。"""
    if os.name == 'nt':
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(str(target), str(link))


def run_cli(arguments, cwd):
    return subprocess.run(
        [sys.executable, str(VALIDATE_SYSML), *map(str, arguments)],
        cwd=str(cwd), capture_output=True, text=True, encoding='utf-8',
        errors='replace', env=CHILD_ENV, timeout=600)


class BaseTemp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='validate-sysml-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class PositiveChainTest(BaseTemp):
    """正例真实全链：转换→preflight→驱动器→SVG→PNG→校核→追溯链。
    一次昂贵运行，类内所有断言共用其工作区。"""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix='validate-sysml-positive-'))
        cls.workdir = cls.root / 'run'
        cls.foreign_cwd = cls.root / 'elsewhere'
        cls.foreign_cwd.mkdir()
        cls.source_before = read_bytes(POSITIVE_SYSML)
        cls.seed_before = read_bytes(SEED)
        cls.result = run_cli(
            ['--sysml', POSITIVE_SYSML, '--layout-seed', SEED,
             '--workdir', cls.workdir, '--json'], cls.foreign_cwd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def load_chain(self):
        return json.loads(
            (self.workdir / 'sysml-trace.json').read_text(encoding='utf-8'))

    def load_convergence(self):
        return json.loads(
            (self.workdir / 'convergence-report.json').read_text(encoding='utf-8'))

    def test_exit_and_delivery_match_tool_failure(self):
        """正例必须真实走完自动链：无签认 = exit 4，不接受 3 工具故障冒充
        正例通过（缺 Chrome 等宿主缺须暴露为失败，见工具故障负例）。"""
        self.assertEqual(self.result.returncode, 4,
                         self.result.stdout + self.result.stderr)
        summary = json.loads(self.result.stdout)
        self.assertEqual(summary['stage'], 'driver')
        self.assertTrue(summary['ok'])
        self.assertEqual(summary['verification']['status'], 'current')
        report = self.load_convergence()
        self.assertTrue(report['converged'])
        self.assertIsNone(report.get('tool_failure'))
        self.assertEqual(report['rounds'][0]['fail_count'], 0)
        delivery = report['delivery']
        # 缺感知签认/局部回读项：交付证据不齐备，ready 保持 false
        self.assertFalse(delivery['ready'])
        self.assertIn('PERCEPTUAL', delivery['blocking_checks'])
        self.assertIn('READBACK_ITEMS', delivery['blocking_checks'])
        self.assertFalse(summary['delivery']['ready'])

    def test_products_exist_and_png_binds_svg(self):
        for name in (vd.SVG_NAME, vd.READBACK, 'validation-report.json',
                     'validation-report.json.sha256', MANIFEST_JSON,
                     '1#系统原理图-topology.md', 'sysml-trace.json'):
            self.assertTrue((self.workdir / name).is_file(), name)
        receipt = json.loads(
            (self.workdir / (vd.READBACK + '.evidence.json'))
            .read_text(encoding='utf-8'))
        import hashlib
        svg_digest = hashlib.sha256(
            (self.workdir / vd.SVG_NAME).read_bytes()).hexdigest()
        self.assertEqual(receipt['svg_sha256'], svg_digest)

    def test_trace_chain_binds_source_intent_manifest(self):
        chain = self.load_chain()
        self.assertEqual(chain['generator'], vs.GENERATOR)
        self.assertEqual(chain['status'], 'driver_completed')
        # 源：哈希口径与实际文件一致（file-bytes）
        import hashlib
        self.assertEqual(chain['source']['hash_scope'], 'file-bytes')
        self.assertEqual(chain['source']['sha256'],
                         hashlib.sha256(read_bytes(POSITIVE_SYSML)).hexdigest())
        # 转换：链内嵌 intent_yaml 的哈希 == 登记 intent_sha256
        conversion = chain['conversion']
        self.assertEqual(
            hashlib.sha256(conversion['intent_yaml'].encode('utf-8')).hexdigest(),
            conversion['intent_sha256'])
        # 驱动器：最终沙箱 intent 哈希登记且本轮未被处方修改
        self.assertEqual(chain['driver']['final_intent_sha256'],
                         conversion['intent_sha256'])
        self.assertFalse(chain['driver']['input_modified_by_prescription'])
        # SVG/manifest：登记哈希与当前文件一致
        for key in ('svg', 'topology_manifest'):
            record = chain['sheet'][key]
            self.assertEqual(
                hashlib.sha256(
                    (self.workdir / record['name']).read_bytes()).hexdigest(),
                record['sha256'])
        self.assertTrue(chain['sheet']['manifest_matches_final_intent'])
        # 校验报告登记哈希与 artifacts 绑定 intent 一致
        entry = chain['driver']['validation_report']
        self.assertEqual(entry['sha256'], hashlib.sha256(
            (self.workdir / 'validation-report.json').read_bytes()).hexdigest())
        self.assertEqual(entry['bound_intent_sha256'],
                         conversion['intent_sha256'])

    def test_source_line_anchors_point_at_connect_lines(self):
        chain = self.load_chain()
        source_lines = read_bytes(POSITIVE_SYSML).decode('utf-8').splitlines()
        manifest = json.loads(
            (self.workdir / MANIFEST_JSON).read_text(encoding='utf-8'))
        manifest_anchors = {e['anchor']: tuple(e['endpoints'])
                            for e in manifest['edges']}
        edges = chain['conversion']['edges']
        self.assertEqual(len(edges), len(ORACLE_EDGES))
        for edge in edges:
            line = edge['sysml_line']
            self.assertTrue(1 <= line <= len(source_lines))
            self.assertIn('connect', source_lines[line - 1])
            self.assertIn(edge['anchor'], manifest_anchors)
            self.assertEqual(frozenset(edge['endpoints']),
                             frozenset(manifest_anchors[edge['anchor']]))

    def test_nodes_edges_extern_match_independent_oracle(self):
        manifest = json.loads(
            (self.workdir / MANIFEST_JSON).read_text(encoding='utf-8'))
        self.assertEqual({n['id']: n['type'] for n in manifest['nodes']},
                         ORACLE_NODES)
        edge_pairs = [set(e['endpoints']) for e in manifest['edges']
                      if e['kind'] == 'path']
        self.assertEqual(sorted(map(sorted, edge_pairs)),
                         sorted(map(sorted, ORACLE_EDGES)))
        self.assertEqual([e['id'] for e in manifest['externs']],
                         sorted(ORACLE_EXTERN))
        # extern 声明必须来自输入（原生边界写法），转换 intent 的 extern 一致
        from ruamel.yaml import YAML
        import io
        with io.open(self.workdir / vd.INTENT_NAME, encoding='utf-8') as fh:
            final_intent = YAML(typ='safe', pure=True).load(fh)
        self.assertEqual(final_intent.get('extern'), ORACLE_EXTERN)

    def test_extern_record_binds_comment_and_port_declaration_lines(self):
        chain = self.load_chain()
        record = chain['conversion']['externs'][0]
        source_lines = read_bytes(POSITIVE_SYSML).decode('utf-8').splitlines()
        self.assertEqual(record['name'], 'USR-001')
        self.assertEqual(record['port'], 'outlet')
        self.assertIn('extern:', source_lines[record['line'] - 1])
        self.assertIn("port 'USR-001'",
                      source_lines[record['port_line'] - 1])

    # ---- 追溯链伪通过回归（审核 findings #1）：合并/篡改/缺记录都必须
    # invalidated，不得 partial-record 冒充 current。----

    def _forged(self, mutate):
        chain = self.load_chain()
        mutate(chain)
        return chain

    def test_merged_conversion_of_other_model_rejected(self):
        """把另一个合法模型的转换结果与已验证工作区合并：intent 哈希不同一，
        链必须不成立（不能只披露 flag 后仍 current）。"""
        other = sti.convert_file(str(OTHER_MODEL))
        self.assertTrue(other.ok, other.diagnostics)
        merged = vs.build_trace_report(
            other, str(self.workdir), 4,
            argparse.Namespace(layout_seed=str(SEED), catalog=None,
                               sysml=str(OTHER_MODEL)),
            None, self.load_convergence())
        verdict = vs.verify_chain(str(self.workdir), merged)
        self.assertEqual(verdict['status'], 'invalidated')
        self.assertTrue(any('intent_sha256' in r for r in verdict['reasons']),
                        verdict['reasons'])

    def test_tampered_source_line_mapping_rejected(self):
        def bump_sysml_line(chain):
            chain['conversion']['edges'][0]['sysml_line'] += 1
        verdict = vs.verify_chain(str(self.workdir), self._forged(
            bump_sysml_line))
        self.assertEqual(verdict['status'], 'invalidated')
        self.assertTrue(any('源行映射 edges' in r for r in verdict['reasons']),
                        verdict['reasons'])

    def test_missing_or_gutted_records_rejected(self):
        cases = {
            '删 source': lambda c: c.pop('source'),
            '删 sheet': lambda c: c.pop('sheet'),
            '删 conversion.edges 字段': lambda c:
                c['conversion'].pop('edges'),
            '清空 conversion.edges': lambda c:
                c['conversion'].__setitem__('edges', []),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                verdict = vs.verify_chain(str(self.workdir),
                                          self._forged(mutate))
                self.assertEqual(verdict['status'], 'invalidated')
                self.assertTrue(verdict['reasons'], label)

    def test_catalog_hash_tamper_rejected(self):
        def rehash_catalog(chain):
            chain['conversion']['catalog']['sha256'] = '0' * 64
        verdict = vs.verify_chain(str(self.workdir), self._forged(
            rehash_catalog))
        self.assertEqual(verdict['status'], 'invalidated')
        self.assertTrue(any('catalog' in r for r in verdict['reasons']),
                        verdict['reasons'])

    def test_prescription_modified_input_is_not_current(self):
        """处方改写了输入：源行映射对本轮图不成立——不能仅披露后仍 current。"""
        def flag_prescription(chain):
            chain['driver']['input_modified_by_prescription'] = True
        verdict = vs.verify_chain(str(self.workdir), self._forged(
            flag_prescription))
        self.assertEqual(verdict['status'], 'invalidated')
        self.assertTrue(any('处方' in r for r in verdict['reasons']),
                        verdict['reasons'])

    def test_verify_current_then_tamper_detected_then_restored(self):
        chain = self.load_chain()
        self.assertEqual(vs.verify_chain(str(self.workdir), chain)['status'],
                         'current')
        svg = self.workdir / vd.SVG_NAME
        original = svg.read_bytes()
        try:
            svg.write_bytes(original + b'<!-- post-processing -->\n')
            verdict = vs.verify_chain(str(self.workdir), chain)
            self.assertEqual(verdict['status'], 'invalidated')
            self.assertTrue(any('已变更' in r for r in verdict['reasons']))
        finally:
            svg.write_bytes(original)
        self.assertEqual(vs.verify_chain(str(self.workdir), chain)['status'],
                         'current')

    def test_verify_cli_exit_codes(self):
        ok = run_cli(['--verify', self.workdir], self.foreign_cwd)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(json.loads(ok.stdout)['status'], 'current')
        svg = self.workdir / vd.SVG_NAME
        original = svg.read_bytes()
        try:
            svg.write_bytes(original + b'<!-- x -->\n')
            bad = run_cli(['--verify', self.workdir], self.foreign_cwd)
            self.assertEqual(bad.returncode, 1)
        finally:
            svg.write_bytes(original)

    def test_inputs_untouched_and_no_intent_published_next_to_source(self):
        self.assertEqual(read_bytes(POSITIVE_SYSML), self.source_before)
        self.assertEqual(read_bytes(SEED), self.seed_before)
        self.assertEqual(sorted(p.name for p in FIXTURES.iterdir()),
                         sorted(['blocked-project.sysml', 'demo-positive.sysml',
                                 'demo-positive.intent.yaml',
                                 'l0-small-seed.sysml']))

    def test_run_from_foreign_cwd_without_dev_paths(self):
        # 运行本身即从 root/elsewhere 发起（cwd 与 skill 无关），此处复核
        # stdout 为纯 JSON 且 workdir 记录的是当轮产物目录。
        summary = json.loads(self.result.stdout)
        self.assertEqual(summary['workdir'], str(self.workdir))
        self.assertTrue((Path(summary['trace'])).is_file())


class ExplicitCatalogChainTest(BaseTemp):
    """真实 CLI 显式 catalog 正例（审查项1回归）：选定目录必须贯穿转换/
    驱动器/确定性重放。规范目录副本仅把 catalog_revision 改为 audit——
    登记 conversion.catalog 不含 path，链核验必须用**工作区目录快照**重放
    并核对 canonical SHA；回退缺省目录会把合法显式目录链误判为"重转换
    不符/catalog 哈希不符"（原 exit3 复现），调包快照则必须失效。"""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix='validate-sysml-catalog-'))
        cls.workdir = cls.root / 'run'
        catalog = json.loads(
            read_bytes(CANONICAL_CATALOG).decode('utf-8'))
        catalog['catalog_revision'] = 'audit'
        cls.audit_catalog = cls.root / 'component-catalog.audit.json'
        cls.audit_catalog.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        cls.audit_sha = sti.catalog_canonical_sha256(catalog)
        cls.default_sha = sti.catalog_canonical_sha256(json.loads(
            read_bytes(CANONICAL_CATALOG).decode('utf-8')))
        cls.result = run_cli(
            ['--sysml', POSITIVE_SYSML, '--catalog', cls.audit_catalog,
             '--layout-seed', SEED, '--workdir', cls.workdir, '--json'],
            cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def load_chain(self):
        return json.loads(
            (self.workdir / 'sysml-trace.json').read_text(encoding='utf-8'))

    def test_explicit_catalog_chain_is_current_not_misrejected(self):
        """显式 catalog 全链：无感知签认 → exit 4 / ok=True / 链 current，
        驱动器真实收敛 fail0；不得降级 3 冒充工具故障。"""
        self.assertEqual(self.result.returncode, 4,
                         self.result.stdout + self.result.stderr)
        summary = json.loads(self.result.stdout)
        self.assertTrue(summary['ok'])
        self.assertEqual(summary['verification']['status'], 'current')
        report = json.loads((self.workdir / 'convergence-report.json')
                            .read_text(encoding='utf-8'))
        self.assertTrue(report['converged'])
        self.assertEqual(report['rounds'][0]['fail_count'], 0)

    def test_registered_catalog_is_the_selected_snapshot(self):
        conv = self.load_chain()['conversion']['catalog']
        self.assertEqual(conv['catalog_revision'], 'audit')
        self.assertEqual(conv['sha256'], self.audit_sha)
        self.assertNotEqual(conv['sha256'], self.default_sha)
        # 转换产物 intent 绑定选定目录（id@revision），不是缺省规范源
        self.assertIn('@audit', self.load_chain()['conversion']['intent_yaml'])
        # 工作区快照就是选定目录的落地副本
        snapshot = json.loads(
            (self.workdir / vd.CATALOG).read_text(encoding='utf-8'))
        self.assertEqual(snapshot['catalog_revision'], 'audit')

    def test_snapshot_swap_invalidates_and_restore_recovers(self):
        ok = run_cli(['--verify', self.workdir], self.root)
        self.assertEqual(ok.returncode, 0)
        snapshot = self.workdir / vd.CATALOG
        original = read_bytes(snapshot)
        try:
            swapped = json.loads(original.decode('utf-8'))
            swapped['catalog_revision'] = 'post-hoc'
            snapshot.write_text(
                json.dumps(swapped, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8')
            bad = run_cli(['--verify', self.workdir], self.root)
            self.assertEqual(bad.returncode, 1)
            verdict = json.loads(bad.stdout)
            self.assertEqual(verdict['status'], 'invalidated')
            self.assertTrue(any('catalog' in r for r in verdict['reasons']),
                            verdict['reasons'])
        finally:
            snapshot.write_bytes(original)
        self.assertEqual(
            run_cli(['--verify', self.workdir], self.root).returncode, 0)


class BridgeMappingIsolationTest(BaseTemp):
    """审查项3映射回归（数据/校验器边界隔离）：桥接边的源行记录保留
    intent 原始 token（裸 PF-001），manifest 按 declared_topology 的
    main_path 语义展开为真实端口（PF-001.inlet/outlet）——映射比对必须
    规范化后等价（合法桥接正例），真实端点被改必报（负例）。

    边界披露：本类只运行纯转换与 declared_topology 投影加校验器映射
    判定，不含布局/SVG/几何/驱动器，**不构成真实图纸全链证明**；真实链
    正例由 PositiveChainTest（缺省目录）与 ExplicitCatalogChainTest
    （显式目录）承担。"""

    @classmethod
    def setUpClass(cls):
        cls.result = sti.convert_file(str(OTHER_MODEL))
        cls.catalog, _ = sti.load_catalog()
        cls.manifest_edges = tr.declared_topology(
            cls.result.intent, cls.catalog)['edges']
        cls.conv_edges = {e['anchor']: e
                          for e in cls.result.trace['edges']
                          if isinstance(e, dict)}
        cls.conv_taps = {t['anchor']: t for t in cls.result.trace['taps']}

    def record_for(self, edge):
        return self.conv_taps.get(edge['anchor']) \
            if edge['kind'] == 'tap' else self.conv_edges.get(edge['anchor'])

    def test_bridge_fixture_has_bare_token_records(self):
        bridges = [e for e in self.result.trace['edges']
                   if e.get('kind') == 'bridge']
        self.assertEqual([e['anchor'] for e in bridges],
                         ['paths[7][0->1]', 'paths[7][1->2]'])
        # 源行记录保留 intent 原始表示（裸实例），manifest 是展开表示
        self.assertEqual(bridges[0]['endpoints'], ['@PRESS', 'PF-001'])
        self.assertEqual(bridges[1]['endpoints'], ['PF-001', '@MANIFOLD'])
        by_anchor = {e['anchor']: e for e in self.manifest_edges}
        self.assertEqual(by_anchor['paths[7][0->1]']['endpoints'],
                         ['@PRESS', 'PF-001.inlet'])
        self.assertEqual(by_anchor['paths[7][1->2]']['endpoints'],
                         ['PF-001.outlet', '@MANIFOLD'])

    def test_legal_bridge_mapping_matches_after_normalization(self):
        """原缺陷回归：paths[7] 两段桥接（以及全部其他边）在规范化后
        一一对应，不得再报"缺对应源行映射记录或端点不符"。"""
        bad = [e['anchor'] for e in self.manifest_edges
               if not vs._edge_mapping_matches(
                   self.record_for(e), e, self.result.trace, self.catalog)]
        self.assertEqual(bad, [], bad)

    def test_normalization_does_not_rewrite_records(self):
        record = self.conv_edges['paths[7][0->1]']
        edge = next(e for e in self.manifest_edges
                    if e['anchor'] == 'paths[7][0->1]')
        vs._edge_mapping_matches(record, edge, self.result.trace,
                                 self.catalog)
        self.assertEqual(record['endpoints'], ['@PRESS', 'PF-001'])

    def test_tampered_real_endpoints_rejected(self):
        by_anchor = {e['anchor']: e for e in self.manifest_edges}
        cases = {
            '入口改出口': ('paths[7][0->1]', ['@PRESS', 'PF-001.outlet']),
            '指向他实例': ('paths[7][0->1]', ['@PRESS', 'PRV-001.inlet']),
            '吞掉桥接半边': ('paths[7][0->1]', ['@PRESS', '@MANIFOLD']),
            '第二段端点被改': ('paths[7][1->2]', ['PF-001.inlet', '@MANIFOLD']),
        }
        for label, (anchor, endpoints) in cases.items():
            with self.subTest(label=label):
                forged = dict(by_anchor[anchor], endpoints=endpoints)
                self.assertFalse(vs._edge_mapping_matches(
                    self.conv_edges[anchor], forged, self.result.trace,
                    self.catalog))

    def test_missing_record_still_rejected(self):
        edge = next(e for e in self.manifest_edges
                    if e['anchor'] == 'paths[7][1->2]')
        self.assertFalse(vs._edge_mapping_matches(
            None, edge, self.result.trace, self.catalog))

    def test_tap_mapping_stays_direct_comparison(self):
        """tap 端点两侧同为原始 token：保持直接比对，不引入展开语义。"""
        self.assertEqual(self.conv_taps['taps[0]']['sensor'],
                         'SW-001.pressure_sense')
        edge = next(e for e in self.manifest_edges
                    if e['anchor'] == 'taps[0]')
        self.assertEqual(edge['endpoints'],
                         ['SW-001.pressure_sense', 'CDF-001.inlet'])
        self.assertTrue(vs._edge_mapping_matches(
            self.conv_taps['taps[0]'], edge, self.result.trace,
            self.catalog))
        forged = dict(edge, endpoints=['SW-001.pressure_sense',
                                       'CDF-001.outlet'])
        self.assertFalse(vs._edge_mapping_matches(
            self.conv_taps['taps[0]'], forged, self.result.trace,
            self.catalog))


class BlockedModelTest(BaseTemp):
    """真实 1# 冻结模型：必须准确拒绝，且在任何布局/渲染前退出。"""

    def test_frozen_hash_is_the_blocked_model(self):
        import hashlib
        self.assertEqual(
            hashlib.sha256(read_bytes(BLOCKED)).hexdigest(),
            FROZEN_BLOCKED_SHA256)

    def test_conversion_blocked_before_any_layout_or_render(self):
        workdir = self.tmp / 'fresh-run'
        result = run_cli(['--sysml', BLOCKED, '--workdir', workdir, '--json'],
                         self.tmp)
        self.assertEqual(result.returncode, 2)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['stage'], 'conversion')
        self.assertIsNone(summary['intent'])
        diagnostics = json.dumps(summary['diagnostics'], ensure_ascii=False)
        for needle in ('ECO-001', 'QD-001', 'QD-002', 'QD-003',
                       'EMP-001.overflow'):
            self.assertIn(needle, diagnostics)
        # 未传 workdir 以外的新目录未被创建；无任何布局/渲染产物
        self.assertFalse(workdir.exists())

    def test_blocked_on_managed_workdir_invalidates_stale_success(self):
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        (workdir / vd.SVG_NAME).write_text('<svg stale/>', encoding='utf-8')
        (workdir / MANIFEST_JSON).write_text('{}', encoding='utf-8')
        (workdir / 'convergence-report.json').write_text('{"converged": true}',
                                                         encoding='utf-8')
        result = run_cli(['--sysml', BLOCKED, '--workdir', workdir, '--json'],
                         self.tmp)
        self.assertEqual(result.returncode, 2)
        self.assertIn(vd.SVG_NAME, result.stdout)
        self.assertFalse((workdir / vd.SVG_NAME).exists())
        self.assertFalse((workdir / MANIFEST_JSON).exists())
        self.assertFalse((workdir / 'convergence-report.json').exists())
        report = json.loads((workdir / 'sysml-trace.json')
                            .read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'conversion_blocked')
        self.assertEqual(sorted(report['cleaned_stale_products']),
                         sorted(['1#系统原理图.svg', MANIFEST_JSON,
                                 'convergence-report.json']))


class OwnershipAndStaleTest(BaseTemp):
    """sysml-trace.json 所有权：只清/只覆盖本工具产物。"""

    def test_foreign_trace_file_preserved_and_report_refused(self):
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        foreign = workdir / 'sysml-trace.json'
        foreign.write_text('{"someone": "else"}', encoding='utf-8')
        result = run_cli(['--sysml', BLOCKED, '--workdir', workdir, '--json'],
                         self.tmp)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(read_bytes(foreign), b'{"someone": "else"}')

    def test_unmanaged_workdir_is_never_touched(self):
        workdir = self.tmp / 'plain'
        workdir.mkdir()
        stale = workdir / vd.SVG_NAME
        stale.write_text('<svg user-region/>', encoding='utf-8')
        result = run_cli(['--sysml', BLOCKED, '--workdir', workdir, '--json'],
                         self.tmp)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(read_bytes(stale), b'<svg user-region/>')
        self.assertFalse((workdir / 'sysml-trace.json').exists())


class TemplateGateTest(BaseTemp):
    """受控模板从 SysML 源同目录随行，不因临时暂存绕过模板门禁。"""

    def test_template_travels_and_gate_blocks_with_e_recon(self):
        source_dir = self.tmp / 'src'
        source_dir.mkdir()
        shutil.copy2(POSITIVE_SYSML, source_dir / POSITIVE_SYSML.name)
        template = source_dir / '1#清单受控模板.yaml'
        template.write_text('行: []\n', encoding='utf-8')
        workdir = self.tmp / 'run'
        result = run_cli(['--sysml', source_dir / POSITIVE_SYSML.name,
                          '--layout-seed', SEED, '--workdir', workdir,
                          '--json'], self.tmp)
        self.assertEqual(result.returncode, 2)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['stage'], 'driver')
        # 顶层 ok 必须反映本轮整体结果：driver 失败（门禁拦截）不得 ok=True
        self.assertFalse(summary['ok'])
        self.assertFalse((summary.get('delivery') or {}).get('ready'))
        # 模板随沙箱复制，门禁以模板内容生效（空背书 → E-RECON 拦截）
        sandbox_template = workdir / template.name
        self.assertEqual(read_bytes(sandbox_template), read_bytes(template))
        report = json.loads((workdir / 'convergence-report.json')
                            .read_text(encoding='utf-8'))
        residuals = json.dumps(report.get('residuals'), ensure_ascii=False)
        self.assertIn('E-RECON', residuals)
        self.assertFalse((workdir / vd.SVG_NAME).exists())
        chain = json.loads((workdir / 'sysml-trace.json')
                           .read_text(encoding='utf-8'))
        self.assertTrue(chain['template']['discovered'])
        import hashlib
        self.assertEqual(chain['template']['sha256'],
                         hashlib.sha256(read_bytes(template)).hexdigest())
        self.assertNotEqual(chain['status'], 'driver_completed')
        self.assertEqual(chain['verification']['status'], 'invalidated')


class PathProtectionTest(BaseTemp):
    """skill 源目录树、祖先与 symlink 别名一律拒绝；输入文件不可改性。"""

    def test_workdir_inside_skill_tree_refused_without_creation(self):
        targets = [SKILL, SKILL / 'scripts' / 'sysml-run-trial',
                   SKILL / 'assets', SKILL.parent]
        for target in targets:
            with self.subTest(target=str(target)):
                result = run_cli(['--sysml', POSITIVE_SYSML,
                                  '--workdir', target], self.tmp)
                self.assertEqual(result.returncode, 5)
        # 拒绝发生在任何写入之前：skill 树内不留运行目录
        self.assertFalse((SKILL / 'scripts' / 'sysml-run-trial').exists())

    def test_workdir_through_alias_into_skill_refused(self):
        alias = self.tmp / 'skill-alias'
        make_directory_alias(alias, SKILL)
        result = run_cli(['--sysml', POSITIVE_SYSML,
                          '--workdir', alias / 'run-trial'], self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertFalse((alias / 'run-trial').exists())

    def test_source_parent_as_workdir_refuses_rebuild_and_keeps_input(self):
        source_dir = self.tmp / 'src'
        source_dir.mkdir()
        sysml = source_dir / POSITIVE_SYSML.name
        shutil.copy2(POSITIVE_SYSML, sysml)
        result = run_cli(['--sysml', sysml, '--workdir', source_dir],
                         self.tmp)
        # 输入位于工作目录内：在任何清理前路径安全拒绝，输入字节不动
        self.assertEqual(result.returncode, 5)
        self.assertEqual(read_bytes(sysml),
                         read_bytes(POSITIVE_SYSML))
        self.assertFalse((source_dir / 'sysml-trace.json').exists())


class InputProtectionTest(BaseTemp):
    """输入先于一切清理/写入受保护：与工作目录重叠（含 symlink 别名）即
    路径安全拒绝，输入字节不动；不依赖驱动器晚一步的输入快照。"""

    def test_seed_inside_managed_workdir_refused_and_kept(self):
        """审核复现场景：受管目录 + 目录内 seed + --keep —— 不得删 seed。"""
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        seed_copy = workdir / '1#系统.layout.json'
        shutil.copy2(SEED, seed_copy)
        result = run_cli(['--sysml', POSITIVE_SYSML, '--layout-seed', seed_copy,
                          '--workdir', workdir, '--keep', '--json'], self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertEqual(read_bytes(seed_copy), read_bytes(SEED))
        self.assertFalse((workdir / 'sysml-trace.json').exists())
        self.assertFalse((workdir / vd.SVG_NAME).exists())
        self.assertIn('realpath', result.stderr)

    def test_ref_inside_managed_workdir_refused_and_kept(self):
        """审核复现场景（审查项2）：--ref 指向受管工作区内的
        1#系统.layout.json —— 原实现在输入保护清单遗漏 ref，preclear 按
        上一轮产物失效清单删掉 ref 后驱动器 exit 2、参照丢失。现在 ref 与
        其他输入同受保护：任何清理前拒绝（exit 5），字节不动。"""
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        ref_copy = workdir / '1#系统.layout.json'
        shutil.copy2(SEED, ref_copy)
        result = run_cli(['--sysml', POSITIVE_SYSML, '--layout-seed', SEED,
                          '--ref', ref_copy, '--workdir', workdir, '--keep',
                          '--json'], self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertEqual(read_bytes(ref_copy), read_bytes(SEED))
        self.assertFalse((workdir / 'sysml-trace.json').exists())
        self.assertFalse((workdir / vd.SVG_NAME).exists())
        self.assertFalse((workdir / 'convergence-report.json').exists())
        self.assertIn('realpath', result.stderr)

    def test_ref_through_alias_into_workdir_refused(self):
        """ref 经 symlink/联接别名指向工作区内同一文件：realpath 判定同样
        拒绝，别名路径与目标字节都不动。"""
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        ref_copy = workdir / '1#系统.layout.json'
        shutil.copy2(SEED, ref_copy)
        alias = self.tmp / 'ref-alias'
        make_directory_alias(alias, workdir)
        result = run_cli(['--sysml', POSITIVE_SYSML,
                          '--ref', alias / '1#系统.layout.json',
                          '--workdir', workdir, '--keep'], self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertEqual(read_bytes(ref_copy), read_bytes(SEED))

    def test_ref_none_and_dash_special_values_are_not_paths(self):
        """none/- 是"无参照"特殊值（与 validate_driver 同口径，大小写
        不敏感）：不做文件存在检查、不入保护清单，流程照常走到转换拦截
        （blocked 模型 exit 2 而非用法拒绝 5）。"""
        for special, workdir_name in (('none', 'run-none'), ('-', 'run-dash'),
                                      ('NONE', 'run-upper')):
            result = run_cli(['--sysml', BLOCKED, '--ref', special,
                              '--workdir', self.tmp / workdir_name, '--json'],
                             self.tmp)
            self.assertEqual(result.returncode, 2, special)
            summary = json.loads(result.stdout)
            self.assertEqual(summary['stage'], 'conversion')

    def test_missing_ref_file_is_usage_rejection(self):
        result = run_cli(['--sysml', POSITIVE_SYSML,
                          '--ref', self.tmp / 'no-such-ref.json'], self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertIn('--ref', result.stderr)

    def test_ref_input_path_semantics(self):
        self.assertIsNone(vs.ref_input_path(None))
        self.assertIsNone(vs.ref_input_path(''))
        for special in ('none', 'NONE', 'None', '-'):
            self.assertIsNone(vs.ref_input_path(special))
        self.assertEqual(vs.ref_input_path('r.json'), 'r.json')

    def test_protected_paths_include_valid_ref(self):
        ref = self.tmp / 'ref.json'
        ref.write_text('{}', encoding='utf-8')
        args = argparse.Namespace(sysml=str(POSITIVE_SYSML), catalog=None,
                                  layout_seed=None, ref=str(ref))
        protected = vs.protected_input_paths(args, None)
        self.assertIn(vs._realpath(ref), protected)
        args = argparse.Namespace(sysml=str(POSITIVE_SYSML), catalog=None,
                                  layout_seed=None, ref='none')
        self.assertNotIn(vs._realpath(ref),
                         vs.protected_input_paths(args, None))

    def test_sysml_inside_managed_workdir_refused_and_kept(self):
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        sysml_copy = workdir / POSITIVE_SYSML.name
        shutil.copy2(POSITIVE_SYSML, sysml_copy)
        result = run_cli(['--sysml', sysml_copy, '--workdir', workdir,
                          '--keep'], self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertEqual(read_bytes(sysml_copy), read_bytes(POSITIVE_SYSML))
        self.assertFalse((workdir / 'sysml-trace.json').exists())

    def test_source_dir_alias_as_workdir_refused(self):
        source_dir = self.tmp / 'src'
        source_dir.mkdir()
        sysml_copy = source_dir / POSITIVE_SYSML.name
        shutil.copy2(POSITIVE_SYSML, sysml_copy)
        alias = self.tmp / 'src-alias'
        make_directory_alias(alias, source_dir)
        result = run_cli(['--sysml', sysml_copy, '--workdir', alias],
                         self.tmp)
        self.assertEqual(result.returncode, 5)
        self.assertEqual(read_bytes(sysml_copy), read_bytes(POSITIVE_SYSML))
        self.assertFalse((alias / 'sysml-trace.json').exists())


class ToolFailureControlTest(BaseTemp):
    """控制流桩（全链真实性由 PositiveChainTest 保证）：
    顶层 ok 与退出码采纳逻辑。"""

    def invoke(self, workdir, driver_exit, verdict):
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        report_payload = json.dumps(
            {'converged': True,
             'delivery': {'ready': False, 'blocking_checks': ['PERCEPTUAL']}})

        def fake_driver(staged_intent, wd, args):
            # 桩驱动器像真实实现一样写出当轮 convergence-report（主入口的
            # 失效清理会先删旧报告，预置文件不构成“上一轮产物”）。
            (Path(wd) / 'convergence-report.json').write_text(
                report_payload, encoding='utf-8')
            return driver_exit

        argv = ['--sysml', str(POSITIVE_SYSML),
                '--workdir', str(workdir), '--json']
        with patch.object(vs, 'run_driver', side_effect=fake_driver), \
                patch.object(vs, 'verify_chain', return_value=verdict):
            code = vs.main(argv)
        return code, json.loads(self._stdout.getvalue())

    def setUp(self):
        super().setUp()
        self._stdout = io.StringIO()
        self._redirect = contextlib.redirect_stdout(self._stdout)
        self._redirect.__enter__()
        self.addCleanup(self._redirect.__exit__, None, None, None)

    def test_driver_tool_failure_keeps_code_and_ok_false(self):
        workdir = self.tmp / 'run3'
        code, summary = self.invoke(
            workdir, 3, {'status': 'invalidated', 'reasons': ['stubbed']})
        self.assertEqual(code, 3)
        self.assertFalse(summary['ok'])
        self.assertFalse((summary.get('delivery') or {}).get('ready'))

    def test_driver_success_with_invalid_chain_is_not_ok(self):
        """驱动器即使返回 0，追溯链不成立也不得 ok=True / ready=True。"""
        workdir = self.tmp / 'run0'
        code, summary = self.invoke(
            workdir, 0, {'status': 'invalidated',
                         'reasons': ['追溯链不成立: stubbed']})
        self.assertEqual(code, 3)
        self.assertFalse(summary['ok'])
        self.assertFalse((summary.get('delivery') or {}).get('ready'))
        self.assertEqual(summary['verification']['status'], 'invalidated')

    def test_driver_incomplete_delivery_with_current_chain_is_exit4(self):
        workdir = self.tmp / 'run4'
        code, summary = self.invoke(
            workdir, 4, {'status': 'current', 'reasons': []})
        self.assertEqual(code, 4)
        self.assertTrue(summary['ok'])
        self.assertFalse(summary['delivery']['ready'])


class UsageTest(BaseTemp):
    def setUp(self):
        super().setUp()
        self.workdir = self.tmp / 'run'

    def invoke(self, *arguments):
        return run_cli(['--sysml', POSITIVE_SYSML, *arguments], self.tmp)

    def test_missing_sysml_file(self):
        result = run_cli(['--sysml', self.tmp / 'no-such.sysml',
                          '--workdir', self.workdir], self.tmp)
        self.assertEqual(result.returncode, 5)

    def test_missing_catalog(self):
        result = self.invoke('--catalog', self.tmp / 'no-cat.json',
                             '--workdir', self.workdir)
        self.assertEqual(result.returncode, 5)

    def test_missing_layout_seed(self):
        result = self.invoke('--layout-seed', self.tmp / 'no-seed.json',
                             '--workdir', self.workdir)
        self.assertEqual(result.returncode, 5)

    def test_workdir_is_existing_file(self):
        occupied = self.tmp / 'occupied'
        occupied.write_text('user file', encoding='utf-8')
        result = self.invoke('--workdir', occupied)
        self.assertEqual(result.returncode, 5)

    def test_missing_sysml_flag(self):
        result = run_cli(['--workdir', self.workdir], self.tmp)
        self.assertEqual(result.returncode, 5)

    def test_unknown_flag(self):
        result = run_cli(['--sysml', POSITIVE_SYSML, '--frobnicate'],
                         self.tmp)
        self.assertEqual(result.returncode, 5)


class ThinEntryUnitTests(BaseTemp):
    """控制流单测（桩 result 对象；全链真实性由 PositiveChainTest 保证）。"""

    @staticmethod
    def fake_result(intent_yaml, source='/tmp/x.sysml'):
        import types
        trace = {'input': {'path': source, 'sha256': 'a' * 64,
                           'hash_scope': 'file-bytes'},
                 'output': {'intent_sha256': 'b' * 64, 'yaml': intent_yaml},
                 'catalog': {'path': None}, 'status': 'converted'}
        return types.SimpleNamespace(trace=trace, source_name=source,
                                     declared={}, intent=None)

    def test_stage_inputs_writes_intent_and_template(self):
        staging = self.tmp / 'stage'
        template = self.tmp / '清单受控模板.yaml'
        template.write_text('行: []\n', encoding='utf-8')
        result = self.fake_result('parts: {}\npaths: []\n')
        staged = vs.stage_driver_inputs(result, staging, template)
        self.assertEqual(staged, staging / vd.INTENT_NAME)
        self.assertEqual(read_bytes(staged), b'parts: {}\npaths: []\n')
        self.assertEqual(read_bytes(staging / template.name),
                         read_bytes(template))

    def test_stage_inputs_without_template(self):
        staging = self.tmp / 'stage'
        result = self.fake_result('parts: {}\n')
        staged = vs.stage_driver_inputs(result, staging, None)
        self.assertTrue(staged.is_file())
        self.assertEqual(list(p.name for p in staging.iterdir()),
                         [vd.INTENT_NAME])

    def test_write_trace_report_ownership(self):
        workdir = self.tmp
        foreign = workdir / 'sysml-trace.json'
        foreign.write_text('{"user": true}', encoding='utf-8')
        with self.assertRaises(vs.UsageError):
            vs.write_trace_report(workdir, {'generator': vs.GENERATOR})
        ours = workdir / 'sysml-trace.json'
        ours.write_text(json.dumps({'generator': vs.GENERATOR}),
                        encoding='utf-8')
        path = vs.write_trace_report(workdir, {'generator': vs.GENERATOR,
                                               'v': 2})
        self.assertEqual(json.loads(read_bytes(path).decode('utf-8'))['v'], 2)

    def test_owned_trace_recognition(self):
        path = self.tmp / 'sysml-trace.json'
        path.write_text('{"generator": "validate_sysml"}', encoding='utf-8')
        self.assertTrue(vs.owned_trace(path))
        path.write_text('{"generator": "other"}', encoding='utf-8')
        self.assertFalse(vs.owned_trace(path))
        path.write_text('not json', encoding='utf-8')
        self.assertFalse(vs.owned_trace(path))

    def test_invalidate_removes_owned_and_generated_only(self):
        workdir = self.tmp / 'managed'
        workdir.mkdir()
        (workdir / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        stale = [workdir / vd.SVG_NAME, workdir / vd.READBACK,
                 workdir / 'validation-report.json',
                 workdir / MANIFEST_JSON]
        for path in stale:
            path.write_text('stale', encoding='utf-8')
        (workdir / 'sysml-trace.json').write_text(
            json.dumps({'generator': vs.GENERATOR}), encoding='utf-8')
        (workdir / 'user-notes.txt').write_text('keep me', encoding='utf-8')
        removed = vs.invalidate_stale_products(workdir)
        self.assertIn(vd.SVG_NAME, removed)
        self.assertFalse(any(p.exists() for p in stale))
        self.assertFalse((workdir / 'sysml-trace.json').exists())
        self.assertEqual((workdir / 'user-notes.txt').read_text(),
                         'keep me')
        self.assertTrue((workdir / vd.MANAGED_FILES).is_file())

    def test_invalidate_skips_unmanaged_and_foreign_trace(self):
        workdir = self.tmp / 'plain'
        workdir.mkdir()
        stale = workdir / vd.SVG_NAME
        stale.write_text('stale', encoding='utf-8')
        self.assertEqual(vs.invalidate_stale_products(workdir), [])
        self.assertTrue(stale.exists())
        managed = self.tmp / 'managed'
        managed.mkdir()
        (managed / vd.MANAGED_FILES).write_text('[]', encoding='utf-8')
        foreign = managed / 'sysml-trace.json'
        foreign.write_text('{"x": 1}', encoding='utf-8')
        self.assertEqual(vs.invalidate_stale_products(managed), [])
        self.assertEqual(read_bytes(foreign), b'{"x": 1}')


if __name__ == '__main__':
    unittest.main()
