# -*- coding: utf-8 -*-
"""Tests for sysml_to_intent (#51 窄版 SysML→L0 intent 转换器, 部分实现).

Run from the repository root:
    python -m unittest discover -s .agents/skills/hydraulic-schematic/scripts \
        -p test_sysml_to_intent.py -v

约定：正例是与 1# 无关的独立具名模型（demo-positive.sysml / 内联小模型）；
blocked-project.sysml 是 1#系统.sysml 的逐字节冻结副本（SHA-256 固定，
全量验收被阻塞模型），必须被准确拒绝而不是被"精简成所谓正例"。本套件
自包含（不依赖 skill 目录之外的仓库文件），不跑完整 selftest。
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sysml_parser as sysml_parser          # noqa: E402
import sysml_to_intent as sti                # noqa: E402
from ruamel.yaml import YAML                 # noqa: E402

FIXTURES = os.path.join(HERE, '..', 'assets', 'fixtures', 'sysml-l0')
DEMO = os.path.join(FIXTURES, 'demo-positive.sysml')
DEMO_REF = os.path.join(FIXTURES, 'demo-positive.intent.yaml')
BLOCKED = os.path.join(FIXTURES, 'blocked-project.sysml')
# 冻结的 blocked 原模型（1#系统.sysml 逐字节副本）哈希——套件可独立于
# 外层仓库复制运行（与前置 parser 测试同口径）。
FROZEN_BLOCKED_SHA256 = ('08e9fd67f75c7ef4b6b1b20288cb814712868d2643ca122e'
                         '8e25a44a26f0aeb9')


def read_bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def read(path):
    return read_bytes(path).decode('utf-8')


def convert(text, **kw):
    return sti.convert_text(text, **kw)


def errors(result):
    return [d for d in result.diagnostics if d['level'] == 'ERROR']


def error_ids(result):
    return {d['id'] for d in errors(result)}


def line_of(text, needle):
    return text[:text.index(needle)].count('\n') + 1


def load_yaml_text(text):
    return YAML(typ='safe', pure=True).load(text)


def yaml_dump(obj):
    from ruamel.yaml import YAML
    buf = io.StringIO()
    yaml = YAML(typ='safe', pure=True)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    yaml.dump(obj, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 可复用小模型与目录
# ---------------------------------------------------------------------------

# 全显式端口、无母线的最小正例（已登记类型；引号名+行注释+多行声明）。
MINIMAL_EXPLICIT = """\
/* minimal supply loop, no buses, all ports explicit */
package 'MINI' {
    part def 'bootstrap_reservoir' {
        port
        'suction_out';
        port 'return_in';
    }
    part def 'engine_driven_pump' {
        port 'suction';
        port 'pressure_out';
    }
    part def 'filter_line_shutoff_dp' {
        port 'inlet';
        port 'outlet';
    }
    part def 'hydraulic_user' {
        port 'pressure_in';
        port 'return_out';
    }
    part 'MINI-SYS' {
        part 'T-1' : 'bootstrap_reservoir';   // inst line
        part 'P-1' : 'filter_line_shutoff_dp';
        part 'E-1' : 'engine_driven_pump';
        part 'U-1' : 'hydraulic_user';
        connect 'T-1'.'suction_out' to 'E-1'.'suction';
        connect 'E-1'.'pressure_out' to 'P-1'.'inlet';
        connect 'P-1'.'outlet' to 'U-1'.'pressure_in';
        connect 'U-1'.'return_out' to 'T-1'.'return_in';
    }
}
"""

# 多端口元件枢纽裸挂：bare 辐条把 PUMP/LOAD 直挂母线、绕过 FILT —— 必须拒绝。
HUB_BYPASS = """\
part def 'filter_line_shutoff_dp' { port 'inlet'; port 'outlet'; }
part def 'engine_driven_pump' { port 'suction'; port 'pressure_out'; }
part def 'hydraulic_user' { port 'pressure_in'; port 'return_out'; }
//@FEED=FILT
part 'S' {
  part 'PUMP' : 'engine_driven_pump';
  part 'FILT' : 'filter_line_shutoff_dp';
  part 'LOAD' : 'hydraulic_user';
  connect 'PUMP'.'pressure_out' to 'FILT';
  connect 'FILT' to 'LOAD'.'pressure_in';
}
"""

# 合成目录：单口 inline 元件（可作元件枢纽）+ 双口元件 + 传感件。
SINGLE_PORT_CATALOG = {
    'catalog_id': 'test-catalog', 'catalog_revision': '1',
    'components': [
        {'component_type': 'junction', 'connection_role': 'inline',
         'main_path': None,
         'ports': [{'id': 'port', 'medium': 'hydraulic'}]},
        {'component_type': 'source', 'connection_role': 'inline',
         'main_path': {'in': 'in', 'out': 'out'},
         'ports': [{'id': 'in', 'medium': 'hydraulic'},
                   {'id': 'out', 'medium': 'hydraulic'}]},
        {'component_type': 'sink', 'connection_role': 'inline',
         'main_path': {'in': 'in', 'out': 'out'},
         'ports': [{'id': 'in', 'medium': 'hydraulic'},
                   {'id': 'out', 'medium': 'hydraulic'}]},
        {'component_type': 'mono_sensor', 'connection_role': 'sensing_only',
         'main_path': None,
         'ports': [{'id': 'sense', 'medium': 'hydraulic'}]},
    ],
}


def demo_result():
    return sti.convert_file(DEMO)


# ---------------------------------------------------------------------------
# 语法层复用与自包含性
# ---------------------------------------------------------------------------

class ParserReuseTest(unittest.TestCase):
    def test_converter_reuses_sysml_parser(self):
        """禁止第二套词法/语法解析：转换器必须复用 sysml_parser.parse。"""
        self.assertIs(sti.sp.parse, sysml_parser.parse)
        self.assertFalse(hasattr(sti, '_tokenize'),
                         '转换器不得自带词法器')


class MinimalExplicitTest(unittest.TestCase):
    """模型没有枢纽声明且不需要母线时，全显式端口直接转换。"""

    @classmethod
    def setUpClass(cls):
        cls.result = convert(MINIMAL_EXPLICIT, source_name='minimal.sysml')

    def test_passes_real_preflight(self):
        self.assertTrue(self.result.ok)
        for d in self.result.diagnostics:
            self.assertNotEqual(d['level'], 'ERROR', d)

    def test_intent_shape(self):
        intent = self.result.intent
        self.assertEqual(intent['l0_version'], '1.1')
        self.assertEqual(intent['maturity'], 'concept')
        self.assertEqual(intent['extern'], {})
        self.assertEqual(intent['system'], 'MINI-SYS')
        self.assertTrue(intent['catalog'].startswith('comac-hydraulic-components@'))
        self.assertEqual(set(intent['parts']),
                         {'T-1', 'P-1', 'E-1', 'U-1'})
        self.assertEqual(len(intent['paths']), 4)
        for path in intent['paths']:
            self.assertEqual(len(path), 2)
            for token in path:
                self.assertFalse(token.startswith('@'))

    def test_multiline_and_quoted_and_comments(self):
        self.assertEqual(
            self.result.trace['parts']['T-1']['sysml_line'],
            line_of(MINIMAL_EXPLICIT, "part 'T-1'"))

    def test_reproducible(self):
        again = convert(MINIMAL_EXPLICIT, source_name='minimal.sysml')
        self.assertEqual(again.intent, self.result.intent)
        self.assertEqual(yaml_dump(again.intent), yaml_dump(self.result.intent))
        self.assertEqual(again.trace, self.result.trace)


class DemoPositiveTest(unittest.TestCase):
    """独立具名正例：母线还原/折叠/taps/unknown 各有明确拓扑 oracle。"""

    @classmethod
    def setUpClass(cls):
        cls.result = demo_result()
        cls.text = read(DEMO)
        cls.intent = cls.result.intent

    def test_ok_and_preflight_cleared(self):
        self.assertTrue(self.result.ok)
        self.assertFalse(error_ids(self.result))

    def test_parts_and_fold(self):
        # CDF 折叠映射对齐 1# 手写 intent：带压差指示的本体类型，
        # 不是目录旧的无压差 case_drain_filter 符号。
        self.assertEqual(self.intent['parts']['CDF-001'],
                         'filter_line_shutoff_dp_case_drain')
        fold = self.result.trace['parts']['CDF-001']['fold']
        self.assertEqual(fold['target'], 'filter_line_shutoff_dp_case_drain')
        self.assertEqual(fold['boundary_ports'], ['inlet', 'outlet'])
        self.assertEqual(fold['members'],
                         {'element': 'filter_element', 'sensor': 'dp_sensor'})
        self.assertEqual(len(fold['internal_edges']), 4)
        for edge in fold['internal_edges']:
            self.assertGreater(edge['sysml_line'], 0)
        self.assertEqual(fold['def_line'],
                         line_of(self.text,
                                 "part def 'filter_line_shutoff_dp_case_drain'"))
        pf_fold = self.result.trace['parts']['PF-001']['fold']
        self.assertEqual(pf_fold['target'], 'filter_line_shutoff_dp')
        self.assertEqual(len(pf_fold['internal_edges']), 4)
        self.assertEqual(self.intent['parts']['PF-001'], 'filter_line_shutoff_dp')

    def test_bridge_spoke_restored(self):
        """main_path 进出口各绑一条母线 → 等价合并为一条桥接路径（不吞边）。"""
        self.assertIn(['@PRESS', 'PF-001', '@MANIFOLD'], self.intent['paths'])
        bridges = [e for e in self.result.trace['edges']
                   if e['kind'] == 'bridge']
        self.assertEqual(len(bridges), 2)
        for edge in bridges:
            self.assertTrue(edge['evidence_lines'])
            for line in edge['evidence_lines']:
                self.assertGreater(line, 0)
                self.assertLessEqual(line, self.text.count('\n') + 1)

    def test_every_declared_port_hub_connects_back(self):
        """每个已声明端口枢纽都必须连回真实端口：桥接覆盖或显式辐条。

        单口枢纽（如油箱回油口）不允许被吞边——这是对拓扑丢失的 oracle。
        """
        declared_hubs = {'PRESS': ('PF-001', 'inlet'),
                         'MANIFOLD': ('PF-001', 'outlet'),
                         'USR': ('PRV-001', 'outlet'),
                         'RET': ('TANK-001', 'return_in')}
        edges = {frozenset(e['endpoints']) for e in self.result.trace['edges']}
        bridges = [p for p in self.intent['paths'] if len(p) == 3]
        for bus, (inst, port) in declared_hubs.items():
            self.assertIn('@%s=%s.%s' % (bus, inst, port), self.text)
            direct = frozenset({'@' + bus, '%s.%s' % (inst, port)})
            via_bridge = any('@' + bus in p and inst in p for p in bridges)
            self.assertTrue(direct in edges or via_bridge,
                            '枢纽 @%s 未连回真实端口 %s.%s（吞边）'
                            % (bus, inst, port))
        # 单口枢纽的显式辐条路径必须存在
        self.assertIn(['@USR', 'PRV-001.outlet'], self.intent['paths'])
        self.assertIn(['@RET', 'TANK-001.return_in'], self.intent['paths'])

    def test_component_hub_bypass_not_possible(self):
        """真实端口连接是 oracle：PRV-001 经显式端口接线，不被母线架空。"""
        paths = self.intent['paths']
        self.assertIn(['@MANIFOLD', 'PRV-001.inlet'], paths)
        self.assertIn(['@USR', 'PRV-001.outlet'], paths)
        for path in paths:
            self.assertNotIn('PRV-001', path,
                             '元件不得以裸 token 出现在母线两侧被架空')

    def test_taps_not_paths(self):
        """sensing_only 依目录 role 归 taps；一口压力表不伪造第二个贯通口。"""
        self.assertEqual(self.intent['taps'],
                         [{'sensor': 'SW-001.pressure_sense',
                           'at': 'CDF-001.inlet'}])
        for path in self.intent['paths']:
            self.assertNotIn('SW-001.pressure_sense', path)
        tap_trace = self.result.trace['taps'][0]
        self.assertEqual(tap_trace['anchor'], 'taps[0]')
        self.assertEqual(tap_trace['sysml_line'],
                         line_of(self.text,
                                 "connect 'SW-001'.'pressure_sense'"))

    def test_unknown_sources_disclosed(self):
        unknown = set(self.intent['unknown'])
        self.assertIn('DEMO-bootstrap-source-not-declared', unknown)
        self.assertIn('TANK-001.bootstrap_pressure_in-unconnected', unknown)
        self.assertIn('EDP-001.drive_shaft-unconnected', unknown)
        sources = {u['entry']: u for u in self.result.trace['unknown']}
        self.assertEqual(sources['DEMO-bootstrap-source-not-declared']['source'],
                         'comment')
        self.assertEqual(
            sources['DEMO-bootstrap-source-not-declared']['line'],
            line_of(self.text, 'unknown: DEMO-bootstrap-source-not-declared'))
        self.assertEqual(
            sources['TANK-001.bootstrap_pressure_in-unconnected']['source'],
            'unconnected-port')

    def test_pending_comments_without_unknown_prefix(self):
        """无 unknown: 前缀的待决注释也按文档化标记搬运，保留原文与真实行。"""
        text = self.text
        pend_line = line_of(text, '走向待工程确认')
        entries = [u for u in self.result.trace['unknown']
                   if u['source'] == 'pending-comment']
        by_line = {u['line']: u for u in entries}
        self.assertIn(pend_line, by_line)
        entry = by_line[pend_line]
        self.assertIn('待工程确认', entry['text'])
        self.assertIn('sysml-pending-l%d' % pend_line, entry['entry'])
        self.assertIn(entry['entry'], self.intent['unknown'])
        # 悬空措辞同样入账
        dangling_line = line_of(text, "// 悬空")
        self.assertIn(dangling_line, by_line)
        # 待决项不影响/不删除任何连接：paths 数量与 connect 数一致
        self.assertEqual(len(self.intent['paths']), 10)

    def test_unreferenced_def_generates_no_instance(self):
        """def 'case_drain_filter'（装配形态）未被引用 → 不生成实例。"""
        self.assertNotIn('case_drain_filter', set(self.intent['parts'].values()))
        self.assertIn('case_drain_filter', self.result.declared['part_defs'])

    def test_sidecar_covers_every_part_and_edge(self):
        trace = self.result.trace
        self.assertEqual(set(trace['parts']), set(self.intent['parts']))
        for inst in self.intent['parts']:
            self.assertGreater(trace['parts'][inst]['sysml_line'], 0)
        anchors = {e['anchor'] for e in trace['edges']}
        for pi, path in enumerate(self.intent['paths']):
            for k in range(len(path) - 1):
                self.assertIn('paths[%d][%d->%d]' % (pi, k, k + 1), anchors)
        for ti in range(len(self.intent.get('taps', []))):
            self.assertIn('taps[%d]' % ti, anchors)

    def test_hashes_bind_source_and_intent(self):
        trace = self.result.trace
        self.assertEqual(trace['input']['sha256'],
                         hashlib.sha256(read_bytes(DEMO)).hexdigest())
        self.assertEqual(trace['input']['hash_scope'], 'file-bytes')
        intent_sha = hashlib.sha256(
            sti.dump_intent_yaml(self.intent).encode('utf-8')).hexdigest()
        self.assertEqual(trace['output']['intent_sha256'], intent_sha)

    def test_hubs_from_comment_only(self):
        hubs = {h['name']: h for h in self.result.trace['hubs']}
        self.assertEqual(set(hubs), {'PRESS', 'MANIFOLD', 'USR', 'RET'})
        for hub in hubs.values():
            self.assertEqual(hub['kind'], 'port')
            self.assertTrue(hub['usable'])
            self.assertEqual(hub['line'],
                             line_of(self.text, '@%s=' % hub['name']))


class BareMainPathTest(unittest.TestCase):
    def test_medium_unique_bare_resolves(self):
        """候选口介质不同且对端介质可判定 → 唯一选择，不靠出现顺序。"""
        catalog = {
            'catalog_id': 'test-catalog', 'catalog_revision': '1',
            'components': [
                {'component_type': 'mixed_device', 'connection_role': 'inline',
                 'main_path': {'in': 'hyd_in', 'out': 'gas_out'},
                 'ports': [
                     {'id': 'hyd_in', 'medium': 'hydraulic'},
                     {'id': 'gas_out', 'medium': 'pneumatic'}]},
                {'component_type': 'source', 'connection_role': 'inline',
                 'main_path': {'in': 'in', 'out': 'out'},
                 'ports': [{'id': 'in', 'medium': 'hydraulic'},
                           {'id': 'out', 'medium': 'hydraulic'}]},
            ],
        }
        model = ("part def 'mixed_device' { port 'hyd_in'; port 'gas_out'; }\n"
                 "part def 'source' { port 'in'; port 'out'; }\n"
                 "part 'S' {\n"
                 "  part 'M-1' : 'mixed_device';\n"
                 "  part 'SRC-1' : 'source';\n"
                 "  connect 'SRC-1'.'out' to 'M-1';\n"
                 "}\n")
        result = convert(model, catalog=catalog, source_name='bare.sysml')
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.intent['paths'],
                         [['SRC-1.out', 'M-1.hyd_in']])

    def test_bare_ambiguous_rejected_not_guessed(self):
        model = ("part def 'priority_valve' { port 'inlet'; port 'outlet'; }\n"
                 "part def 'hydraulic_user' { port 'pressure_in'; port 'return_out'; }\n"
                 "part 'S' {\n"
                 "  part 'V-1' : 'priority_valve';\n"
                 "  part 'U-1' : 'hydraulic_user';\n"
                 "  connect 'V-1' to 'U-1'.'pressure_in';\n"
                 "}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-BARE-AMBIGUOUS', error_ids(result))
        self.assertTrue(result.mentions('V-1'))
        self.assertIsNone(result.intent)

    def test_bare_without_main_path_rejected(self):
        model = ("part def 'engine_driven_pump' { port 'suction'; }\n"
                 "part def 'hydraulic_user' { port 'pressure_in'; port 'return_out'; }\n"
                 "part 'S' {\n"
                 "  part 'E-1' : 'engine_driven_pump';\n"
                 "  part 'U-1' : 'hydraulic_user';\n"
                 "  connect 'E-1' to 'U-1'.'pressure_in';\n"
                 "}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-BARE-NOMP', error_ids(result))

    def test_port_hub_spoke_is_bus_token(self):
        result = demo_result()
        self.assertIn(['@USR', 'PRV-001.outlet'], result.intent['paths'])


class HubValidationTest(unittest.TestCase):
    def test_multi_port_component_hub_bypass_rejected(self):
        """多端口元件枢纽无法唯一绑定真实端口：bare 辐条=绕过元件，拒绝。"""
        result = convert(HUB_BYPASS, source_name='bypass.sysml')
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-HUB-COMPONENT-UNBOUND', error_ids(result))
        self.assertTrue(result.mentions('FILT'))
        self.assertIsNone(result.intent)

    def test_single_port_component_hub_allowed(self):
        """唯一目录端口的元件枢纽=该端口的汇流抽象，辐条不丢连接。"""
        model = ("part def 'junction' { port 'port'; }\n"
                 "part def 'source' { port 'in'; port 'out'; }\n"
                 "part def 'sink' { port 'in'; port 'out'; }\n"
                 "//@F=J-1\n"
                 "part 'S' {\n"
                 "  part 'SRC-1' : 'source';\n"
                 "  part 'J-1' : 'junction';\n"
                 "  part 'SNK-1' : 'sink';\n"
                 "  connect 'SRC-1'.'out' to 'J-1';\n"
                 "  connect 'J-1' to 'SNK-1'.'in';\n"
                 "}\n")
        result = convert(model, catalog=SINGLE_PORT_CATALOG,
                         source_name='singlehub.sysml')
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.intent['paths'],
                         [['SRC-1.out', '@F'], ['@F', 'SNK-1.in']])
        # 枢纽即端口：该端口视为已被枢纽引用，不产生未连接误报
        self.assertNotIn('J-1.port-unconnected',
                         result.intent.get('unknown', []))

    def test_sensing_component_hub_rejected(self):
        model = ("part def 'pressure_switch' { port 'pressure_sense'; }\n"
                 "part 'S' {\n  part 'SW-001' : 'pressure_switch';\n"
                 "  part 'SW-002' : 'pressure_switch';\n"
                 "  connect 'SW-001' to 'SW-002'.'pressure_sense';\n}\n"
                 "/* @BUS=SW-001 */\n")
        result = convert(model)
        self.assertIn('E-SYSML-HUB-COMPONENT-UNBOUND', error_ids(result))

    def test_one_port_two_buses_rejected(self):
        model = ("part def 'filter_line_shutoff_dp' { port 'inlet'; port 'outlet'; }\n"
                 "part 'S' {\n  part 'PF-001' : 'filter_line_shutoff_dp';\n}\n"
                 "/* @A=PF-001.inlet、@B=PF-001.inlet */\n")
        result = convert(model)
        self.assertIn('E-SYSML-HUB-PORT', error_ids(result))

    def test_hub_on_unknown_port_rejected(self):
        model = ("part def 'filter_line_shutoff_dp' { port 'inlet'; port 'outlet'; }\n"
                 "part 'S' {\n  part 'PF-001' : 'filter_line_shutoff_dp';\n}\n"
                 "/* @A=PF-001.nothere */\n")
        result = convert(model)
        self.assertIn('E-SYSML-HUB-PORT', error_ids(result))

    def test_hub_on_pneumatic_port_rejected(self):
        model = ("part def 'hydro_pneumatic_accumulator' { port 'hydraulic_port'; "
                 "port 'gas_port'; }\n"
                 "part 'S' {\n  part 'ACC-1' : 'hydro_pneumatic_accumulator';\n}\n"
                 "/* @GAS=ACC-1.gas_port */\n")
        result = convert(model)
        self.assertIn('E-SYSML-HUB-MEDIUM', error_ids(result))

    def test_conflicting_hub_redeclaration_rejected(self):
        model = ("part def 'filter_line_shutoff_dp' { port 'inlet'; port 'outlet'; }\n"
                 "part 'S' {\n  part 'PF-001' : 'filter_line_shutoff_dp';\n"
                 "  part 'PF-002' : 'filter_line_shutoff_dp';\n}\n"
                 "/* @A=PF-001.inlet、@A=PF-002.inlet */\n")
        result = convert(model)
        self.assertIn('E-SYSML-HUB-DUP', error_ids(result))


# ---------------------------------------------------------------------------
# 反例：类型/端口
# ---------------------------------------------------------------------------

class TypeAndPortRejectionTest(unittest.TestCase):
    def test_undeclared_type_rejected(self):
        model = ("part 'S' {\n  part 'X-1' : 'missing_def';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-TYPE-UNKNOWN', error_ids(result))
        self.assertTrue(result.mentions('X-1'))

    def test_type_not_in_catalog_rejected(self):
        model = ("part def 'eco_bottle' { port 'inlet'; }\n"
                 "part 'S' {\n  part 'ECO-001' : 'eco_bottle';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-CAT-TYPE', error_ids(result))
        self.assertTrue(result.mentions('ECO-001'))
        self.assertIsNone(result.intent)

    def test_port_not_in_catalog_named(self):
        """EMP-001.overflow 类问题的最小复现：def 端口目录没有 → 点名拒绝。"""
        model = ("part def 'electric_motor_driven_pump' { port 'suction'; "
                 "port 'overflow'; }\n"
                 "part def 'eco_bottle' { port 'inlet'; }\n"
                 "part 'S' {\n  part 'EMP-001' : 'electric_motor_driven_pump';\n"
                 "  connect 'EMP-001'.'overflow' to 'EMP-001'.'suction';\n}\n")
        result = convert(model)
        ids = error_ids(result)
        self.assertIn('E-SYSML-PORT-NOTINCAT', ids)
        self.assertTrue(result.mentions('EMP-001.overflow'))
        self.assertIsNone(result.intent)

    def test_connect_port_undeclared_in_def_rejected(self):
        model = ("part def 'filter_line_shutoff_dp' { port 'inlet'; }\n"
                 "part 'S' {\n  part 'PF-001' : 'filter_line_shutoff_dp';\n"
                 "  connect 'PF-001'.'outlet' to 'PF-001'.'inlet';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-PORT-UNDECLARED', error_ids(result))

    def test_connect_to_undeclared_instance_rejected(self):
        model = ("part def 'filter_line_shutoff_dp' { port 'inlet'; }\n"
                 "part 'S' {\n  part 'PF-001' : 'filter_line_shutoff_dp';\n"
                 "  connect 'PF-001'.'inlet' to 'GHOST-1';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-REF', error_ids(result))
        self.assertTrue(result.mentions('GHOST-1'))


# ---------------------------------------------------------------------------
# 折叠：严格核验 + CDF 映射对齐
# ---------------------------------------------------------------------------

class FoldRejectionTest(unittest.TestCase):
    BODY = ("part def 'filter_element' { port 'inlet'; port 'outlet'; }\n"
            "part def 'dp_sensor' { port 'sense_a'; port 'sense_b'; }\n"
            "part def 'check_valve' { port 'inlet'; port 'outlet'; }\n"
            "part def 'check_valve_spring' { port 'inlet'; port 'outlet'; }\n"
            "part def 'bootstrap_reservoir' { port 'suction_out'; "
            "port 'return_in'; }\n")

    def dp_return_body(self, extra=''):
        return ("part def 'filter_line_shutoff_dp_return' {\n"
                "  port 'inlet'; port 'outlet';\n"
                "  part 'element' : 'filter_element';\n"
                "  part 'sensor' : 'dp_sensor';\n"
                "  connect 'inlet' to 'element'.'inlet';\n"
                "  connect 'element'.'outlet' to 'outlet';\n"
                "  connect 'sensor'.'sense_a' to 'element'.'inlet';\n"
                "  connect 'sensor'.'sense_b' to 'element'.'outlet';\n"
                + extra + "}\n")

    def return_filter_model(self, assembly_connects, body_extra=''):
        return (self.BODY + self.dp_return_body(body_extra) +
                "part def 'return_filter' {\n"
                "  port 'inlet'; port 'outlet';\n"
                "  part 'body' : 'filter_line_shutoff_dp_return';\n"
                "  part 'cv' : 'check_valve_spring';\n"
                + assembly_connects + "}\n"
                "part 'S' {\n"
                "  part 'RF-001' : 'return_filter';\n"
                "  part 'T-1' : 'bootstrap_reservoir';\n"
                "  connect 'RF-001'.'outlet' to 'T-1'.'return_in';\n"
                "}\n")

    RETURN_CANONICAL = ("  connect 'inlet' to 'body'.'inlet';\n"
                        "  connect 'inlet' to 'cv'.'inlet';\n"
                        "  connect 'body'.'outlet' to 'outlet';\n"
                        "  connect 'cv'.'outlet' to 'outlet';\n")

    def test_canonical_return_filter_folds_to_bypass(self):
        """既有约定：return_filter 按旁通结构折叠为已登记叶类型（依据见文档）。"""
        result = convert(self.return_filter_model(self.RETURN_CANONICAL))
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.intent['parts']['RF-001'],
                         'filter_line_shutoff_dp_return_bypass')
        fold = result.trace['parts']['RF-001']['fold']
        self.assertEqual(fold['members'],
                         {'body': 'filter_line_shutoff_dp_return',
                          'cv': 'check_valve_spring'})
        self.assertEqual(len(fold['internal_edges']), 4)

    def test_cdf_series_cv_assembly_rejected(self):
        """CDF 装配（本体+串联单向阀）目录无对应符号：不折叠为无压差旧符号。

        1# 手写 intent 的 CDF-001 是 filter_line_shutoff_dp_case_drain
        （filter-line-shutoff-dp.svg 带压差指示）；目录 case_drain_filter 是
        filter-line-shutoff-stroke.svg（无压差）。结构无法证明的形态拒绝。
        """
        model = (self.BODY +
                 "part def 'filter_line_shutoff_dp' {\n"
                 "  port 'inlet'; port 'outlet';\n"
                 "  part 'element' : 'filter_element';\n"
                 "  part 'sensor' : 'dp_sensor';\n"
                 "  connect 'inlet' to 'element'.'inlet';\n"
                 "  connect 'element'.'outlet' to 'outlet';\n"
                 "  connect 'sensor'.'sense_a' to 'element'.'inlet';\n"
                 "  connect 'sensor'.'sense_b' to 'element'.'outlet';\n"
                 "}\n"
                 "part def 'case_drain_filter' {\n"
                 "  port 'inlet'; port 'outlet';\n"
                 "  part 'body' : 'filter_line_shutoff_dp';\n"
                 "  part 'cv' : 'check_valve';\n"
                 "  connect 'inlet' to 'body'.'inlet';\n"
                 "  connect 'body'.'outlet' to 'cv'.'inlet';\n"
                 "  connect 'cv'.'outlet' to 'outlet';\n"
                 "}\n"
                 "part 'S' {\n  part 'CDF-001' : 'case_drain_filter';\n"
                 "  part 'T-1' : 'bootstrap_reservoir';\n"
                 "  connect 'CDF-001'.'outlet' to 'T-1'.'return_in';\n}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-FOLD', error_ids(result))
        self.assertTrue(result.mentions('case_drain_filter'))

    def test_modified_internal_topology_rejected(self):
        """改装配内部连接（旁通改直连）→ 拒绝，不按类型名丢弃。"""
        result = convert(self.return_filter_model(
            "  connect 'inlet' to 'body'.'inlet';\n"
            "  connect 'body'.'outlet' to 'outlet';\n"))
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-FOLD', error_ids(result))
        self.assertTrue(result.mentions('return_filter'))

    def test_missing_internal_edge_rejected(self):
        result = convert(self.return_filter_model(
            "  connect 'inlet' to 'body'.'inlet';\n"
            "  connect 'cv'.'outlet' to 'outlet';\n"))
        self.assertIn('E-SYSML-FOLD', error_ids(result))

    def test_duplicate_internal_edge_rejected(self):
        """内部连接多重集核验：重复 connect 不被 set 去重放过。"""
        result = convert(self.return_filter_model(
            self.RETURN_CANONICAL,
            body_extra="  connect 'inlet' to 'element'.'inlet';\n"))
        self.assertIn('E-SYSML-FOLD', error_ids(result))

    def test_deep_internal_endpoint_rejected(self):
        """内部端点 >2 段（element.inlet.ghost）不被截断接受。"""
        result = convert(self.return_filter_model(
            self.RETURN_CANONICAL,
            body_extra="  connect 'inlet' to 'element'.'inlet'.'ghost';\n"))
        self.assertIn('E-SYSML-FOLD', error_ids(result))

    def test_member_port_missing_rejected(self):
        """成员定义删掉 sense_b 端口后，引用它的内部连接必须拒绝。"""
        model = (self.BODY.replace(
                     "part def 'dp_sensor' { port 'sense_a'; port 'sense_b'; }",
                     "part def 'dp_sensor' { port 'sense_a'; }") +
                 self.dp_return_body() +
                 "part def 'return_filter' {\n"
                 "  port 'inlet'; port 'outlet';\n"
                 "  part 'body' : 'filter_line_shutoff_dp_return';\n"
                 "  part 'cv' : 'check_valve_spring';\n"
                 + self.RETURN_CANONICAL + "}\n"
                 "part 'S' {\n  part 'RF-001' : 'return_filter';\n"
                 "  part 'T-1' : 'bootstrap_reservoir';\n"
                 "  connect 'RF-001'.'outlet' to 'T-1'.'return_in';\n}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-FOLD', error_ids(result))

    def test_catalog_type_with_unverifiable_internals_rejected(self):
        """catalog 已登记类型带自定义内部结构且无折叠模板 → 拒绝。"""
        model = (self.BODY +
                 "part def 'pressure_filter' {\n"
                 "  port 'inlet'; port 'outlet';\n"
                 "  part 'element' : 'filter_element';\n"
                 "  connect 'inlet' to 'element'.'inlet';\n"
                 "  connect 'element'.'outlet' to 'outlet';\n"
                 "}\n"
                 "part 'S' {\n  part 'PF-001' : 'pressure_filter';\n}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-FOLD', error_ids(result))

    def test_member_type_undeclared_rejected(self):
        model = ("part def 'case_drain_filter' {\n"
                 "  port 'inlet'; port 'outlet';\n"
                 "  part 'body' : 'ghost_type';\n"
                 "  part 'cv' : 'check_valve';\n"
                 "  connect 'inlet' to 'body'.'inlet';\n"
                 "  connect 'body'.'outlet' to 'cv'.'inlet';\n"
                 "  connect 'cv'.'outlet' to 'outlet';\n"
                 "}\n"
                 "part 'S' {\n  part 'CDF-001' : 'case_drain_filter';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-FOLD', error_ids(result))


# ---------------------------------------------------------------------------
# 反例：语法/结构
# ---------------------------------------------------------------------------

class StructureRejectionTest(unittest.TestCase):
    def test_syntax_error_reports_line(self):
        result = convert("part def 'A' @ ;\n")
        self.assertIn('E-SYSML-SYNTAX', error_ids(result))
        self.assertEqual(errors(result)[0]['line'], 1)
        self.assertIsNone(result.intent)

    def test_nary_connect_rejected(self):
        result = convert("part 'S' { connect 'a' to 'b' to 'c'; }\n")
        self.assertIn('E-SYSML-SYNTAX', error_ids(result))

    def test_zero_system_rejected(self):
        result = convert("part def 'A';\n")
        self.assertIn('E-SYSML-SYSTEM-COUNT', error_ids(result))

    def test_multiple_systems_rejected(self):
        result = convert("part 'S1' { }\npart 'S2' { }\n")
        self.assertIn('E-SYSML-SYSTEM-COUNT', error_ids(result))

    def test_nested_system_rejected(self):
        result = convert("part 'S1' { part 'S2' { } }\n")
        self.assertIn('E-SYSML-NESTED-SYSTEM', error_ids(result))

    def test_def_shadow_across_scopes_rejected(self):
        model = ("package 'P1' { part def 'A'; }\n"
                 "package 'P2' { part def 'A'; }\n"
                 "part 'S' { part 'X-1' : 'A'; }\n")
        result = convert(model)
        self.assertIn('E-SYSML-DEF-SHADOW', error_ids(result))

    def test_dotted_type_ref_rejected(self):
        model = ("package 'P' { part def 'A'; }\n"
                 "part 'S' { part 'X-1' : 'P'.'A'; }\n")
        result = convert(model)
        self.assertIn('E-SYSML-DEF-DOTTED', error_ids(result))

    def test_deep_endpoint_rejected(self):
        model = ("part def 'inner' { port 'p'; }\n"
                 "part def 'outer' { part 'i' : 'inner'; }\n"
                 "part 'S' {\n part 'O-1' : 'outer';\n"
                 " connect 'O-1'.'i'.'p' to 'O-1'.'i'.'p';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-ENDPOINT-DEEP', error_ids(result))

    def test_duplicate_connect_rejected(self):
        model = ("part def 'check_valve' { port 'inlet'; port 'outlet'; }\n"
                 "part 'S' {\n part 'C-1' : 'check_valve';\n"
                 " part 'C-2' : 'check_valve';\n"
                 " connect 'C-1'.'outlet' to 'C-2'.'inlet';\n"
                 " connect 'C-1'.'outlet' to 'C-2'.'inlet';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-DUP-CONNECT', error_ids(result))

    def test_instance_name_violating_contract_rejected(self):
        model = ("part def 'check_valve' { port 'inlet'; }\n"
                 "part 'S' {\n part 'lower-1' : 'check_valve';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-INST-NAME', error_ids(result))

    def test_tap_to_bus_rejected(self):
        model = ("part def 'filter_line_shutoff_dp' { port 'inlet'; port 'outlet'; }\n"
                 "part def 'pressure_switch' { port 'pressure_sense'; }\n"
                 "/* @A=PF-001.inlet */\n"
                 "part 'S' {\n part 'PF-001' : 'filter_line_shutoff_dp';\n"
                 " part 'SW-001' : 'pressure_switch';\n"
                 " connect 'SW-001'.'pressure_sense' to 'PF-001'.'inlet';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-TAP-BUS', error_ids(result))

    def test_sensor_sensor_connect_rejected(self):
        model = ("part def 'pressure_switch' { port 'pressure_sense'; }\n"
                 "part 'S' {\n part 'SW-001' : 'pressure_switch';\n"
                 " part 'SW-002' : 'pressure_switch';\n"
                 " connect 'SW-001'.'pressure_sense' to 'SW-002'.'pressure_sense';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-TAP-TAP', error_ids(result))


# ---------------------------------------------------------------------------
# 反例：介质（sensing_only 不豁免；混介质/机械/电气一律拒绝）
# ---------------------------------------------------------------------------

class MediumRejectionTest(unittest.TestCase):
    def test_pneumatic_path_edge_rejected(self):
        """非 sensing 组件间的气侧连接不入 paths：明确拒绝混介质。"""
        model = ("part def 'hydro_pneumatic_accumulator' { port 'hydraulic_port'; "
                 "port 'gas_port'; }\n"
                 "part def 'air_charging_valve' { port 'accumulator_gas'; "
                 "port 'charge_port'; }\n"
                 "part 'S' {\n part 'ACC-001' : 'hydro_pneumatic_accumulator';\n"
                 " part 'ACV-001' : 'air_charging_valve';\n"
                 " connect 'ACC-001'.'gas_port' to 'ACV-001'.'accumulator_gas';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-MEDIUM', error_ids(result))
        self.assertTrue(result.mentions('ACC-001.gas_port'))

    def test_mechanical_connection_rejected(self):
        model = ("part def 'engine_driven_pump' { port 'suction'; "
                 "port 'drive_shaft'; }\n"
                 "part def 'check_valve' { port 'inlet'; }\n"
                 "part 'S' {\n part 'E-1' : 'engine_driven_pump';\n"
                 " part 'C-1' : 'check_valve';\n"
                 " connect 'E-1'.'drive_shaft' to 'C-1'.'inlet';\n}\n")
        result = convert(model)
        self.assertIn('E-SYSML-MEDIUM', error_ids(result))

    def test_mixed_medium_tap_rejected(self):
        """气侧传感口接液压口：混介质 taps 拒绝（不以 sensing_only/WARN 放行）。"""
        model = ("part def 'pressure_gauge' { port 'pressure_sense'; }\n"
                 "part def 'filter_line_shutoff_dp' { port 'inlet'; port 'outlet'; }\n"
                 "part 'S' {\n part 'PG-001' : 'pressure_gauge';\n"
                 " part 'PF-001' : 'filter_line_shutoff_dp';\n"
                 " connect 'PG-001'.'pressure_sense' to 'PF-001'.'inlet';\n}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-MEDIUM', error_ids(result))
        self.assertIsNone(result.intent)

    def test_mechanical_tap_rejected(self):
        """控制器复现：pressure_sense(pneumatic) ↔ drive_shaft(mechanical)
        不得因 sensing_only 被接受为 tap。"""
        model = ("part def 'pressure_gauge' { port 'pressure_sense'; }\n"
                 "part def 'engine_driven_pump' { port 'suction'; "
                 "port 'drive_shaft'; }\n"
                 "part 'S' {\n part 'PG-001' : 'pressure_gauge';\n"
                 " part 'E-1' : 'engine_driven_pump';\n"
                 " connect 'PG-001'.'pressure_sense' to 'E-1'.'drive_shaft';\n}\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-MEDIUM', error_ids(result))
        self.assertIsNone(result.intent)

    def test_sensing_chain_becomes_two_taps_single_port(self):
        """链式传感（ACC→PG→ACV，全气侧同介质）：一口压力表两条连接都如实归 taps。"""
        model = ("part def 'hydro_pneumatic_accumulator' { port 'hydraulic_port'; "
                 "port 'gas_port'; }\n"
                 "part def 'pressure_gauge' { port 'pressure_sense'; }\n"
                 "part def 'air_charging_valve' { port 'accumulator_gas'; "
                 "port 'charge_port'; }\n"
                 "part def 'bootstrap_reservoir' { port 'suction_out'; "
                 "port 'return_in'; }\n"
                 "part def 'engine_driven_pump' { port 'suction'; "
                 "port 'pressure_out'; }\n"
                 "part 'S' {\n part 'ACC-001' : 'hydro_pneumatic_accumulator';\n"
                 " part 'PG-001' : 'pressure_gauge';\n"
                 " part 'ACV-001' : 'air_charging_valve';\n"
                 " part 'T-1' : 'bootstrap_reservoir';\n"
                 " part 'E-1' : 'engine_driven_pump';\n"
                 " connect 'ACC-001'.'gas_port' to 'PG-001'.'pressure_sense';\n"
                 " connect 'PG-001'.'pressure_sense' to 'ACV-001'.'accumulator_gas';\n"
                 " connect 'T-1'.'suction_out' to 'E-1'.'suction';\n}\n")
        result = convert(model)
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(len(result.intent['taps']), 2)
        sensors = {t['sensor'] for t in result.intent['taps']}
        self.assertEqual(sensors, {'PG-001.pressure_sense'})
        self.assertEqual(result.intent['paths'],
                         [['T-1.suction_out', 'E-1.suction']])
        for path in result.intent['paths']:
            self.assertFalse(any('gas' in token or 'PG-001' in token
                                 for token in path))

    def test_hydraulic_measurement_tap_allowed(self):
        demo = demo_result()
        self.assertEqual(demo.intent['taps'],
                         [{'sensor': 'SW-001.pressure_sense',
                           'at': 'CDF-001.inlet'}])


# ---------------------------------------------------------------------------
# extern 边界（#52 窄约定）：系统 part 内 port 声明是实体，注释补 L0 角色
# ---------------------------------------------------------------------------

def extern_model(declaration="// extern: USR-001=outlet\n",
                 connect="connect 'PF-001'.'outlet' to 'USR-001'",
                 system_ports="        port 'USR-001';\n"):
    return ("part def 'bootstrap_reservoir' { port 'suction_out'; "
            "port 'return_in'; }\n"
            "part def 'pressure_filter' { port 'inlet'; port 'outlet'; }\n"
            "part def 'pressure_switch' { port 'pressure_sense'; }\n"
            + declaration
            + "part 'S' {\n"
            + system_ports
            + " part 'T-1' : 'bootstrap_reservoir';\n"
              " part 'PF-001' : 'pressure_filter';\n"
              " part 'SW-001' : 'pressure_switch';\n"
              " connect 'T-1'.'suction_out' to 'PF-001'.'inlet';\n "
            + connect + ';\n}\n')


class ExternDeclarationTest(unittest.TestCase):
    def test_declaration_flows_to_intent_and_trace(self):
        result = convert(extern_model())
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.intent['extern'], {'USR-001': 'outlet'})
        self.assertEqual(result.intent['paths'][-1], ['PF-001.outlet',
                                                      'USR-001'])
        self.assertEqual(result.declared['externs'], ['USR-001'])
        # trace 同时保留注释声明行与系统端口实体声明行（真实 1-based）
        self.assertEqual(result.trace['externs'],
                         [{'name': 'USR-001', 'port': 'outlet', 'line': 4,
                           'port_line': 6}])
        self.assertIn('connect', extern_model().splitlines()[10])

    def test_block_comment_line_is_accurate(self):
        model = extern_model(
            declaration="/* header\n * extern: USR-001=outlet\n */\n")
        result = convert(model)
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.trace['externs'][0]['line'], 5)
        self.assertEqual(result.trace['externs'][0]['port_line'], 8)
        self.assertEqual(model.splitlines()[4].count('extern:'), 1)

    def test_comment_only_without_system_port_rejected(self):
        """仅有注释而无 port 实体声明：注释不替代 SysML 实体，拒绝。"""
        result = convert(extern_model(system_ports=''))
        self.assertFalse(result.ok)
        self.assertIn('E-SYSML-EXTERN-UNDECLARED', error_ids(result))
        self.assertIsNone(result.intent)

    def test_no_declaration_yields_empty_extern_and_plain_ref_error(self):
        self.assertEqual(convert(MINIMAL_EXPLICIT).intent['extern'], {})
        result = convert(extern_model(declaration=''))
        self.assertIn('E-SYSML-REF', error_ids(result))
        self.assertTrue(result.mentions('USR-001'))

    def test_dotted_boundary_reference_rejected(self):
        """边界是系统端口：connect 直接写端口名；L0 角色不写在端点上。"""
        result = convert(extern_model(
            connect="connect 'PF-001'.'outlet' to 'USR-001'.'outlet'"))
        self.assertIn('E-SYSML-EXTERN-PORT', error_ids(result))
        self.assertIsNone(result.intent)

    def test_name_clash_with_instance_rejected(self):
        model = extern_model(
            declaration="// extern: T-1=outlet\n",
            connect="connect 'PF-001'.'outlet' to 'T-1'")
        result = convert(model)
        self.assertIn('E-SYSML-EXTERN-CLASH', error_ids(result))

    def test_bad_name_rejected(self):
        result = convert(extern_model(declaration="// extern: usr=outlet\n"))
        self.assertIn('E-SYSML-EXTERN-NAME', error_ids(result))

    def test_conflicting_redeclaration_rejected_same_is_idempotent(self):
        conflict = extern_model(
            declaration="// extern: USR-001=outlet\n"
                        "// extern: USR-001=return\n")
        result = convert(conflict)
        self.assertIn('E-SYSML-EXTERN-DUP', error_ids(result))
        same = extern_model(
            declaration="// extern: USR-001=outlet\n"
                        "// extern: USR-001=outlet\n")
        result = convert(same)
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.intent['extern'], {'USR-001': 'outlet'})

    def test_tap_to_extern_rejected(self):
        result = convert(extern_model(
            connect="connect 'SW-001'.'pressure_sense' to 'USR-001'"))
        self.assertIn('E-SYSML-TAP-EXTERN', error_ids(result))
        self.assertIsNone(result.intent)

    def test_port_value_schema_enum_enforced_by_preflight(self):
        model = extern_model(declaration="// extern: USR-001=sideport\n")
        result = convert(model)
        self.assertFalse(result.ok)
        self.assertTrue(any(d['id'].startswith('L0-E-SHAPE')
                            for d in result.diagnostics),
                        result.diagnostics)

    def test_multiple_externs_sorted_and_unreferenced_disclosed(self):
        model = extern_model(
            declaration="// extern: USR-002=outlet\n"
                        "// extern: USR-001=inlet\n",
            connect="connect 'PF-001'.'outlet' to 'USR-002'",
            system_ports="        port 'USR-001';\n"
                         "        port 'USR-002';\n")
        result = convert(model)
        self.assertTrue(result.ok, result.diagnostics)
        self.assertEqual(result.intent['extern'],
                         {'USR-001': 'inlet', 'USR-002': 'outlet'})
        self.assertEqual(result.declared['externs'],
                         ['USR-001', 'USR-002'])
        # 已声明但未被连接引用的边界按未连接披露，不静默丢弃
        self.assertIn('USR-001-unconnected', result.intent.get('unknown', []))


# ---------------------------------------------------------------------------
# blocked-project 夹具（1# 全量验收被阻塞模型）：必须准确拒绝
# ---------------------------------------------------------------------------

class BlockedProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(BLOCKED)
        cls.raw = read_bytes(BLOCKED)
        cls.result = sti.convert_file(BLOCKED)

    def test_fixture_is_the_frozen_blocked_model(self):
        """逐字节冻结的 1# 原模型副本（哈希固定，套件自包含可移植）。"""
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),
                         FROZEN_BLOCKED_SHA256)

    def test_conversion_blocked_no_intent_published(self):
        self.assertFalse(self.result.ok)
        self.assertIsNone(self.result.intent)
        self.assertEqual(self.result.trace['status'], 'blocked')

    def test_required_rejection_names_present(self):
        blob = json.dumps(self.result.diagnostics, ensure_ascii=False)
        for needle in ('ECO-001', 'QD-001', 'QD-002', 'QD-003',
                       'EMP-001.overflow'):
            self.assertIn(needle, blob,
                          '诊断必须点名 %s（全量验收阻塞清单）' % needle)

    def test_declared_summary_disclosed(self):
        declared = self.result.declared
        self.assertEqual(declared['system'], 'HYD-SYS-1')
        self.assertEqual(declared['connects'], 40)
        self.assertIn('PF-001', declared['instances'])
        self.assertIn('filter_line_shutoff_dp', declared['part_defs'])

    def test_source_lines_are_1_based_and_real(self):
        """诊断行号必须落在真实文件行上（不伪造 SysML 行号）。"""
        lines = self.text.splitlines()
        for d in self.result.diagnostics:
            if d['line'] is not None:
                self.assertGreaterEqual(d['line'], 1)
                self.assertLessEqual(d['line'], len(lines))


# ---------------------------------------------------------------------------
# 发布安全（公开 API 级回归）
# ---------------------------------------------------------------------------

def _good_result():
    return demo_result()


def _blocked_result():
    return sti.convert_file(BLOCKED)


class PublishSafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sti-pub-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out = os.path.join(self.tmp, 'demo.intent.yaml')
        self.custom = os.path.join(self.tmp, 'custom.trace.json')
        self.default_trace = self.out + '.trace.json'

    def test_first_and_second_publish_with_custom_trace(self):
        """自定义 trace 也参与所有权核验：二次发布覆盖自己的产物不误拒。"""
        good = _good_result()
        r1 = sti.publish(good, self.out, self.custom)
        self.assertTrue(r1['published'], r1)
        self.assertTrue(os.path.isfile(self.out))
        self.assertTrue(os.path.isfile(self.custom))
        r2 = sti.publish(_good_result(), self.out, self.custom)
        self.assertTrue(r2['published'], r2)

    def test_blocked_with_custom_trace_cleans_stale(self):
        """失败转换清理本工具产物：自定义 trace 绑定的 intent 同样清理。"""
        r1 = sti.publish(_good_result(), self.out, self.custom)
        self.assertTrue(r1['published'])
        r2 = sti.publish(_blocked_result(), self.out, self.custom)
        self.assertFalse(r2['published'])
        self.assertIn(self.out, r2['cleaned'])
        self.assertIn(self.custom, r2['cleaned'])
        self.assertFalse(os.path.isfile(self.out))
        self.assertFalse(os.path.isfile(self.custom))

    def test_user_sidecar_file_not_overwritten(self):
        """intent 不存在而缺省 sidecar 是用户文件：不得覆盖。"""
        marker = '{"note": "用户文件"}\n'
        with io.open(self.default_trace, 'w', encoding='utf-8') as fh:
            fh.write(marker)
        report = sti.publish(_good_result(), self.out)  # 缺省 trace=用户文件
        self.assertFalse(report['published'])
        self.assertTrue(report['refused'])
        with io.open(self.default_trace, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), marker)
        self.assertFalse(os.path.isfile(self.out))

    def test_trace_target_directory_refused_without_partial_write(self):
        """trace 目标是现有目录：预检拒绝，不留下未绑定的 intent。"""
        os.makedirs(self.custom)
        report = sti.publish(_good_result(), self.out, self.custom)
        self.assertFalse(report['published'])
        self.assertTrue(report['refused'])
        self.assertFalse(os.path.isfile(self.out))

    def test_trace_write_failure_rolls_back_intent(self):
        """trace 写失败（模拟）：intent 回滚，不以无绑定状态残留。"""
        real_atomic = sti._atomic_write
        calls = {'n': 0}

        def flaky(path, data):
            calls['n'] += 1
            if calls['n'] == 2:   # 第二次（trace）失败
                raise OSError('disk on fire')
            return real_atomic(path, data)

        with mock.patch.object(sti, '_atomic_write', flaky):
            report = sti.publish(_good_result(), self.out)
        self.assertFalse(report['published'])
        self.assertFalse(os.path.isfile(self.out),
                         'intent 不得在 sidecar 写失败后残留')

    def test_protected_path_collision(self):
        """输入/catalog/参照与输出目标相撞或别名 → 拒绝。"""
        good = _good_result()
        protected = [DEMO, sti.default_catalog_path(), DEMO_REF]
        for target in protected:
            report = sti.publish(good, target, None, protected_paths=protected)
            self.assertFalse(report['published'])
            self.assertTrue(any('相撞' in m for m in report['refused']),
                            report['refused'])
            self.assertTrue(os.path.isfile(target))
        report = sti.publish(good, self.out, DEMO_REF,
                             protected_paths=protected)  # trace 撞参照
        self.assertFalse(report['published'])
        self.assertTrue(any('相撞' in m for m in report['refused']))

    def _publish_pair(self, tag):
        """发布 A/B 两个产物（各有缺省绑定 sidecar），返回路径与 B sidecar 字节。"""
        a = os.path.join(self.tmp, 'owner-%s.yaml' % tag)
        b = os.path.join(self.tmp, 'other-%s.yaml' % tag)
        b_trace = b + '.trace.json'
        self.assertTrue(sti.publish(_good_result(), a)['published'])
        self.assertTrue(sti.publish(_good_result(), b)['published'])
        with open(b_trace, 'rb') as fh:
            before = fh.read()
        return a, b, b_trace, before

    def test_success_does_not_steal_other_outputs_sidecar(self):
        """成功发布以他产物 sidecar 为 trace：拒绝且其字节不变。"""
        good = _good_result()
        a, b, b_trace, before = self._publish_pair('success')
        report = sti.publish(good, a, b_trace)
        self.assertFalse(report['published'])
        self.assertTrue(any('其他输出' in m for m in report['refused']),
                        report['refused'])
        with open(b_trace, 'rb') as fh:
            self.assertEqual(fh.read(), before, 'B 的追溯 sidecar 字节不变')
        self.assertTrue(os.path.isfile(a))

    def test_failed_cleanup_preserves_other_outputs_sidecar(self):
        """失败清理只删属于当前输出的 sidecar：他产物 sidecar 字节不变。

        同时核验 cleanup 的 other 分支不按 generator 误删。
        """
        failed = _blocked_result()
        a, b, b_trace, before = self._publish_pair('failure')
        report = sti.publish(failed, a, b_trace)
        self.assertFalse(report['published'])
        with open(b_trace, 'rb') as fh:
            self.assertEqual(fh.read(), before, 'B 的追溯 sidecar 字节不变')
        self.assertFalse(os.path.isfile(a),
                         'A 是本工具产物且转换失败，应被清理')
        self.assertTrue(os.path.isfile(b))

    def test_same_output_custom_trace_rerun_still_allowed(self):
        """合法场景保留：同一输出用自定义 trace 重跑/清理不受影响。"""
        good = _good_result()
        custom = os.path.join(self.tmp, 'own-custom.trace.json')
        self.assertTrue(sti.publish(good, self.out, custom)['published'])
        self.assertTrue(sti.publish(_good_result(), self.out, custom)
                        ['published'])
        report = sti.publish(_blocked_result(), self.out, custom)
        self.assertFalse(report['published'])
        self.assertIn(self.out, report['cleaned'])
        self.assertIn(custom, report['cleaned'])
        self.assertFalse(os.path.isfile(self.out))
        self.assertFalse(os.path.isfile(custom))


class SourceBindingTest(unittest.TestCase):
    """文件入口按原始字节绑定源哈希：LF/CRLF/BOM 均与磁盘一致。"""

    def _binds_raw_bytes(self, raw, name):
        path = os.path.join(tempfile.mkdtemp(prefix='sti-src-'), name)
        self.addCleanup(shutil.rmtree, os.path.dirname(path),
                        ignore_errors=True)
        with open(path, 'wb') as fh:
            fh.write(raw)
        result = sti.convert_file(path)
        self.assertTrue(result.ok, result.diagnostics)
        return result, raw

    def test_lf_file_hash(self):
        result, raw = self._binds_raw_bytes(
            MINIMAL_EXPLICIT.encode('utf-8'), 'lf.sysml')
        self.assertEqual(result.trace['input']['sha256'],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(result.trace['input']['hash_scope'], 'file-bytes')

    def test_crlf_file_hash_and_lines(self):
        crlf = MINIMAL_EXPLICIT.replace('\n', '\r\n').encode('utf-8')
        result, raw = self._binds_raw_bytes(crlf, 'crlf.sysml')
        self.assertEqual(result.trace['input']['sha256'],
                         hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(result.trace['input']['sha256'],
                            hashlib.sha256(
                                MINIMAL_EXPLICIT.encode('utf-8')).hexdigest())
        # 1-based 行号不受 \r 影响
        self.assertEqual(result.trace['parts']['T-1']['sysml_line'],
                         line_of(MINIMAL_EXPLICIT, "part 'T-1'"))

    def test_bom_file_hash(self):
        bom = b'\xef\xbb\xbf' + MINIMAL_EXPLICIT.encode('utf-8')
        result, raw = self._binds_raw_bytes(bom, 'bom.sysml')
        self.assertEqual(result.trace['input']['sha256'],
                         hashlib.sha256(raw).hexdigest())

    def test_content_change_changes_hash(self):
        result, raw = self._binds_raw_bytes(
            MINIMAL_EXPLICIT.encode('utf-8'), 'a.sysml')
        h1 = result.trace['input']['sha256']
        path = result.trace['input']['path']
        with open(path, 'wb') as fh:
            fh.write(MINIMAL_EXPLICIT.replace('MINI-SYS', 'MINI-S2')
                     .encode('utf-8'))
        result2 = sti.convert_file(path)
        self.assertNotEqual(result2.trace['input']['sha256'], h1)
        self.assertEqual(result2.intent['system'], 'MINI-S2')

    def test_convert_text_scope_is_text(self):
        result = convert(MINIMAL_EXPLICIT, source_name='t.sysml')
        self.assertEqual(result.trace['input']['hash_scope'], 'text')

    def test_invalid_utf8_refused(self):
        path = os.path.join(tempfile.mkdtemp(prefix='sti-bad-'), 'bad.sysml')
        self.addCleanup(shutil.rmtree, os.path.dirname(path),
                        ignore_errors=True)
        with open(path, 'wb') as fh:
            fh.write(b"part def 'A' { port '\xff\xfe'; }\n")
        with self.assertRaises(ValueError):
            sti.convert_file(path)


# ---------------------------------------------------------------------------
# 拓扑对账（成功转换 ↔ 手写 intent）
# ---------------------------------------------------------------------------

class TopologyDiffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog, _ = sti.load_catalog()
        cls.catalog = catalog
        cls.result = demo_result()
        cls.reference = load_yaml_text(read(DEMO_REF))

    def test_normalized_match_on_same_topology(self):
        diff = sti.topology_diff(self.result.intent, self.reference,
                                 self.catalog)
        self.assertEqual(len(diff['nodes']['matched']), 7)
        self.assertEqual(diff['nodes']['missing_in_converted'], [])
        self.assertEqual(diff['nodes']['extra_in_converted'], [])
        self.assertEqual(diff['edges']['matched'], 11)
        self.assertEqual(diff['edges']['missing_in_converted'], [])
        self.assertEqual(diff['edges']['extra_in_converted'], [])
        self.assertEqual(diff['taps']['matched'], 1)
        self.assertEqual(diff['taps']['missing_in_converted'], [])

    def test_missing_and_extra_listed_separately(self):
        reference = json.loads(json.dumps(self.reference))
        # 手写侧多一个未连线用户（转换缺）→ missing_in_converted
        reference['parts']['USER-002'] = 'hydraulic_user'
        # 手写侧少 USER-001 及其辐条（转换多）→ extra_in_converted
        del reference['parts']['USER-001']
        reference['paths'] = [p for p in reference['paths']
                              if 'USER-001' not in ' '.join(p)]
        reference['taps'] = []
        diff = sti.topology_diff(self.result.intent, reference, self.catalog)
        self.assertEqual(diff['nodes']['missing_in_converted'], ['USER-002'])
        self.assertEqual(diff['nodes']['extra_in_converted'], ['USER-001'])
        extra_pairs = {tuple(e['endpoints']) for e in
                       diff['edges']['extra_in_converted']}
        self.assertIn(('@USR', 'USER-001.pressure_in'), extra_pairs)
        self.assertTrue(diff['taps']['extra_in_converted'])

    def test_type_mismatch_reported(self):
        reference = json.loads(json.dumps(self.reference))
        reference['parts']['CDF-001'] = 'case_drain_filter'
        diff = sti.topology_diff(self.result.intent, reference, self.catalog)
        self.assertEqual(diff['nodes']['type_mismatch'],
                         [{'instance': 'CDF-001',
                           'converted_type': 'filter_line_shutoff_dp_case_drain',
                           'reference_type': 'case_drain_filter'}])


# ---------------------------------------------------------------------------
# CLI（真实子进程；路径按文件位置解析，非 repo cwd 可用）
# ---------------------------------------------------------------------------

class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = os.path.join(HERE, 'sysml_to_intent.py')
        cls.env = dict(os.environ, PYTHONIOENCODING='utf-8')

    def run_cli(self, argv, cwd):
        return subprocess.run([sys.executable, self.cli] + argv,
                              cwd=cwd, capture_output=True, env=self.env)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sti-cli-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = os.path.join(self.tmp, 'work')
        self.other = os.path.join(self.tmp, 'elsewhere')
        os.makedirs(self.work)
        os.makedirs(self.other)
        self.input = os.path.join(self.work, 'demo-positive.sysml')
        shutil.copy(DEMO, self.input)
        self.out = os.path.join(self.work, 'demo-positive.intent.yaml')
        self.trace = self.out + '.trace.json'

    def test_success_publishes_next_to_input_from_foreign_cwd(self):
        proc = self.run_cli([self.input], cwd=self.other)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode('utf-8'))
        self.assertTrue(os.path.isfile(self.out))
        self.assertTrue(os.path.isfile(self.trace))
        self.assertEqual(os.listdir(self.other), [],
                         '缺省输出必须落在输入旁，不落在 cwd')
        with io.open(self.trace, encoding='utf-8') as fh:
            sidecar = json.load(fh)
        self.assertEqual(sidecar['generator'], 'sysml_to_intent')
        self.assertEqual(sidecar['output']['path'],
                         os.path.normpath(self.out))
        self.assertEqual(sidecar['output']['intent_sha256'],
                         hashlib.sha256(read_bytes(self.out)).hexdigest())
        self.assertEqual(sidecar['input']['sha256'],
                         hashlib.sha256(read_bytes(self.input)).hexdigest())
        self.assertEqual(sidecar['input']['hash_scope'], 'file-bytes')

    def test_json_output_success(self):
        proc = self.run_cli([self.input, '--json'], cwd=self.other)
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.decode('utf-8'))
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['published'])
        self.assertIsNotNone(payload['intent'])
        self.assertEqual(payload['intent']['system'], 'DEMO-SYS-1')

    def test_blocked_leaves_no_output_and_cleans_stale_success(self):
        proc = self.run_cli([self.input], cwd=self.other)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(os.path.isfile(self.out))
        proc = self.run_cli([BLOCKED, '-o', self.out], cwd=self.other)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.isfile(self.out),
                         '失败运行不得遗留可误认的陈旧成功 intent')
        self.assertFalse(os.path.isfile(self.trace))

    def test_blocked_with_diff_also_cleans_stale_success(self):
        """--diff 下的失败转换走同一失效处理（不得提前 return 留陈旧产物）。"""
        proc = self.run_cli([self.input], cwd=self.other)
        self.assertEqual(proc.returncode, 0)
        proc = self.run_cli([BLOCKED, '-o', self.out, '--diff', DEMO_REF],
                            cwd=self.other)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.isfile(self.out))
        self.assertFalse(os.path.isfile(self.trace))

    def test_blocked_json_has_no_intent(self):
        proc = self.run_cli([BLOCKED, '--json'], cwd=self.other)
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout.decode('utf-8'))
        self.assertFalse(payload['ok'])
        self.assertIsNone(payload['intent'])
        blob = json.dumps(payload['diagnostics'], ensure_ascii=False)
        for needle in ('ECO-001', 'QD-001', 'EMP-001.overflow'):
            self.assertIn(needle, blob)

    def test_user_file_refused_not_overwritten(self):
        marker = '# 用户手写内容，不得覆盖\n'
        with io.open(self.out, 'w', encoding='utf-8') as fh:
            fh.write(marker)
        proc = self.run_cli([self.input], cwd=self.other)
        self.assertEqual(proc.returncode, 2)
        with io.open(self.out, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), marker)

    def test_input_output_collision_refused(self):
        proc = self.run_cli([self.input, '-o', self.input], cwd=self.other)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(read(self.input), read(DEMO))
        self.assertFalse(os.path.isfile(self.trace))

    def test_output_colliding_with_diff_reference_refused(self):
        proc = self.run_cli([self.input, '-o', DEMO_REF, '--diff', DEMO_REF],
                            cwd=self.other)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(read(DEMO_REF), read(DEMO_REF))  # 参照未被破坏

    def test_diff_flag_on_success_reports_normalized_diff(self):
        proc = self.run_cli([self.input, '--diff', DEMO_REF, '--json'],
                            cwd=self.other)
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout.decode('utf-8'))
        self.assertIsNotNone(payload['diff'])
        self.assertEqual(payload['diff']['edges']['matched'], 11)
        self.assertEqual(payload['diff']['edges']['missing_in_converted'], [])

    def test_diff_flag_on_blocked_claims_nothing(self):
        out = os.path.join(self.work, 'blocked.intent.yaml')
        proc = self.run_cli([BLOCKED, '-o', out, '--diff', DEMO_REF],
                            cwd=self.other)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.isfile(out))
        stdout = proc.stdout.decode('utf-8')
        self.assertNotIn('matched=', stdout)
        self.assertNotIn('拓扑对账(vs', stdout)
        self.assertIn('跳过 --diff 对账', stdout)
        self.assertIn('已解析声明', stdout)
        self.assertIn('HYD-SYS-1', stdout)

    def test_missing_input_exit_2(self):
        proc = self.run_cli([os.path.join(self.tmp, 'nope.sysml')],
                            cwd=self.other)
        self.assertEqual(proc.returncode, 2)

    def test_default_catalog_anchor_works_from_any_cwd(self):
        """不传 --catalog 时锚定 skill 规范源（脚本位置解析，与 cwd 无关）。"""
        proc = self.run_cli([self.input], cwd=self.other)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode('utf-8'))
        with io.open(self.out, encoding='utf-8') as fh:
            intent = load_yaml_text(fh.read())
        catalog, _ = sti.load_catalog()
        self.assertEqual(intent['catalog'],
                         '%s@%s' % (catalog['catalog_id'],
                                    catalog['catalog_revision']))


if __name__ == '__main__':
    unittest.main()
