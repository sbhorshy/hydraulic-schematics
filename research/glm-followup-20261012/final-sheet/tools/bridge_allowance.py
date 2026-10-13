# -*- coding: utf-8 -*-
"""跳线（跨线桥）许可登记（#23 定案：仅内容绑定的当前 1# 放行 1 处经验证跳线）。

#23 用户定案(2026-10-12)：B1 默认仍恒为 0；仅"当前 1# 系统 intent"允许
最多 1 处经验证跳线，其余交叉仍禁止，其他图纸默认 0，B2–B7 不变。
放行不改变实测口径——measured 仍是真实交叉数；经验证跳线逐点取自
V4/V14 的浏览器几何证据（junction_semantics.check_junctions），本模块
只裁决"最多几处"，不复核桥的画法。非平面性下界证据（K3,3 细分证书 +
NetworkX 复核）见仓库 research/glm-followup-20261012/whole-graph-planarity.md，
登记只固化许可，不复核该论证。

许可三道闸（与 #63 镜像登记同构；显式申请但任一闸不过即 ValueError
硬失败，绝不静默当作 0）：
  1. 布局显式选择：layout.bridge_policy 必须是非空字符串且为登记过的
     政策 id。未声明 = 未申请，allowance 默认 0（不要求登记，与既有
     布局完全兼容）；声明了未登记 id 或类型不对 -> 硬失败。
  2. 内容精确绑定：政策按 intent 文件字节 SHA-256 放行，不按文件名/
     标题。intent 内容一改，旧登记即失效（fail-closed），必须按新
     内容重新登记；错 hash 硬失败。
  3. 预算只能来自登记：maximum_verified_bridges 只写在生产登记表
     （本模块 PRODUCTION_BRIDGE_POLICIES，源为用户明示决定），布局
     不得携带任何数字形式的跳线/交叉预算键（出现即硬失败）。

测试注入边界：resolve_policy 暴露 registry= 仅供测试构造临时登记表；
生产入口 check_bridge_policy 不接受 registry 参数，validate_sheet 的
B1 放行只能来自生产登记表。
"""
import hashlib
import os

__all__ = ['PRODUCTION_BRIDGE_POLICIES', 'FORBIDDEN_LAYOUT_KEYS',
           'check_bridge_policy', 'resolve_policy']

# 生产登记表（#23，2026-10-12）。raw_sha256 由 Codex 对当前
# 1#系统原理图/1#系统.intent.yaml 实算填入（bridge-input-binding.json），
# tests/repository/test_bridge_registration.py 以真实文件字节对账，
# intent 漂移未重登记即失败。
PRODUCTION_BRIDGE_POLICIES = {
    'current-1-verified-single-bridge-20261012': {
        'intent_path': '1#系统原理图/1#系统.intent.yaml',
        'intent_sha256':
            '8acc1abe4d3959a8496e82ff03d80117ff88d6364a9e135d489af7915c59d888',
        'maximum_verified_bridges': 1,
        'decision': '#23 用户定案 2026-10-12：当前 1# 允许最多 1 处经验证跳线，'
                    '其余交叉仍禁止',
        'evidence': 'research/glm-followup-20261012/whole-graph-planarity.md'
                    '（K3,3 非平面证书：零交叉不可能，至少一处跨越表示）',
    },
}

# 布局端禁止出现的数字预算键（任何值，包括 null）。放行数只能来自
# 登记表，布局写数字即视为自行扩预算，硬失败。
FORBIDDEN_LAYOUT_KEYS = ('bridge_allowance', 'bridge_budget',
                         'b1_allowance', 'b1_budget',
                         'crossing_allowance', 'crossing_budget')

_HEX64 = frozenset('0123456789abcdef')


def _file_sha256(path, where):
    if isinstance(path, bool) or not isinstance(path, (str, os.PathLike)):
        raise ValueError('%s: intent_path 必须为文件路径(str/PathLike),'
                         '实际 %r' % (where, path))
    digest = hashlib.sha256()
    try:
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
    except OSError as error:
        raise ValueError('%s: 无法读取跳线许可绑定的 intent 文件 %s:%s'
                         % (where, path, error))
    return digest.hexdigest()


def _hex_digest(value, where):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in _HEX64 for char in value)):
        raise ValueError('%s: intent_sha256 必须为 64 位小写十六进制摘要,'
                         '实际 %r' % (where, value))
    return value


def resolve_policy(policy_id, intent_sha256, registry=None):
    """按登记表裁决政策申请，返回登记条目副本；policy_id 为 None 返回 None。

    纯函数接缝：registry 仅限测试传入自定义登记表；生产路径用默认
    PRODUCTION_BRIDGE_POLICIES（check_bridge_policy 不透传 registry，
    预算无法经生产接口注入）。未知 id、非法摘要或内容绑定不符一律
    ValueError（fail-closed，不得静默当作 0 放行）。
    """
    where = 'bridge_policy[%r]' % (policy_id,)
    if registry is None:
        registry = PRODUCTION_BRIDGE_POLICIES
    if not isinstance(registry, dict) or not registry:
        raise ValueError('%s: 登记表必须为非空 dict,实际 %s'
                         % (where, type(registry).__name__))
    if policy_id is None:
        return None
    if not isinstance(policy_id, str) or not policy_id:
        raise ValueError('%s: 必须为非空字符串的政策 id;未声明 bridge_policy'
                         ' 才是"未申请"(allowance 0),不要用空值冒充' % where)
    entry = registry.get(policy_id)
    if not isinstance(entry, dict):
        raise ValueError('%s: 未登记的跳线政策 id;可用登记:%s。跳线许可只能'
                         '引用登记政策,布局不得自行放宽'
                         % (where, ' '.join(sorted(registry))))
    allowance = entry.get('maximum_verified_bridges')
    if (isinstance(allowance, bool) or not isinstance(allowance, int)
            or allowance < 0):
        raise ValueError('%s: 登记表 maximum_verified_bridges 必须为非负'
                         '整数,实际 %r' % (where, allowance))
    registered = _hex_digest(entry.get('intent_sha256'), where + '.intent_sha256')
    current = _hex_digest(intent_sha256, where)
    if registered != current:
        raise ValueError(
            '%s: 跳线登记已失效——intent 当前 sha256=%s,与登记 %s 不符;'
            'intent 内容变更后必须按新内容重新登记(fail-closed)'
            % (where, current, registered))
    return dict(entry)


def check_bridge_policy(layout, intent_path):
    """生产入口：裁决布局的跳线政策申请（validate_sheet B1 段专用）。

    layout 未声明 bridge_policy -> {'policy_id': None, 'allowance': 0}
    （默认未申请，不读 intent、不报错）；声明则三道闸全过才返回
    {'policy_id', 'allowance', 'intent_sha256', 'decision', 'evidence'}。
    任何拒绝抛带政策 id/键名/原因的 ValueError，由调用方转为硬失败，
    不得静默降为 0。预算只能来自生产登记表，本函数无 registry 参数。
    """
    where = 'check_bridge_policy'
    if not isinstance(layout, dict):
        raise ValueError('%s: layout 必须为 dict,实际 %s'
                         % (where, type(layout).__name__))
    injected = [key for key in FORBIDDEN_LAYOUT_KEYS if key in layout]
    if injected:
        raise ValueError('%s: 布局不得携带数字跳线/交叉预算键 %s——放行数量'
                         '只能来自 bridge_allowance 登记表,布局写数字即'
                         '自行扩预算' % (where, ' '.join(sorted(injected))))
    policy_id = layout.get('bridge_policy')
    if policy_id is None:
        return {'policy_id': None, 'allowance': 0}
    entry = resolve_policy(policy_id, _file_sha256(intent_path, where))
    return {'policy_id': policy_id,
            'allowance': entry['maximum_verified_bridges'],
            'intent_sha256': entry['intent_sha256'],
            'decision': entry['decision'], 'evidence': entry['evidence']}
