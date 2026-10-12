# -*- coding: utf-8 -*-
"""镜像策略与坐标契约(#63:条件解禁——逐组件登记允许镜像)。

#63 定案:条件解禁——逐组件登记允许镜像,保留端口身份并记录镜像操作。
本模块固化策略与坐标契约,渲染(render_l0_sheet)/校核(validate_sheet 的
contract 阶段)与几何读取(sheet_geometry 许可姿态校验)单源复用。登记是
用户已签条件政策下的许可记录,不是逐只工程签认,不提升 provisional/draft
成熟度。生产启用现状(#63 登记,2026-10-12):仅 engine_driven_pump 与
electric_motor_driven_pump 两类已登记,规范源 catalog 与 1# 工作目录
catalog 各自按真实符号字节登记 axes=['x','y'](两目录符号仅行尾 CRLF
不同,摘要各自绑定、不共用);其余所有类型默认仍禁止镜像。

布局节点 mirror 值域(严格类型,0 不是 False):
  缺省 / None / False / 'none' -> 不镜像(与既有布局完全兼容,不要求登记)
  'x' -> 左右翻转(归一盒坐标 x -> W-x,left/right 锚互换)
  'y' -> 上下翻转(y -> H-y,up/down 锚互换)
  True / 数字 / 其他字符串或容器一律拒绝。

变换次序:先在已归零并缩放的本地盒([0,W]x[0,H])内镜像,再做既有
0/90/180/270 旋转与平移;端口 id/svg_element_id/medium/role/
flow_capability/anchor_direction 等身份字段一律不交换、不重命名,
仅位置与锚向随镜像变换(锚向与坐标必须同步,同 place() 的旋转纪律)。

镜像许可三道闸(全部满足才放行,缺一即 ValueError):
  1. component.mirror_safe is True         逐组件镜像许可登记
  2. component.layout.allow_mirror is True 目录布局层许可
  3. component.mirror_registration 与当前资产/端口契约绑定:
     axes 为非空列表且只含 'x'/'y',请求轴必须在列;asset_sha256 等于
     当前符号文件字节摘要;ports_sha256 等于当前目录端口契约摘要。
     符号文件或端口契约一改,旧登记即失效,必须按新状态重新登记。

渲染接入点(symbols() 既有变换链,字符串序;镜像段插在 rotate 之后、
scale(k) 之前,应用序恰为"归零缩放盒内先镜像,再旋转平移"):
  translate(x,y) translate(comp) rotate(rot) <mirror_svg_transform>
  scale(k) translate(-vx,-vy)
无镜像时插入空串,既有输出逐字节不变。旋转补偿表不必改:镜像把盒
映射回自身,镜像后再旋转的占位足迹与只旋转时相同。
接入现状(#63 步骤二):sheet_geometry.load_geometry 以可选"逐实例已
校验许可"放行获准反射(det=-1),并要求轴/旋转/缩放/平移与实际 SVG
矩阵相符,缺失镜像、错误轴/旋转、未声明负矩阵一律入 issues;镜像操作
由实例组 data-mirror 属性与追溯清单记录,本层只裁决。
"""
import hashlib
import json
import math
import os

__all__ = ['check_mirror', 'port_contract_digest', 'mirror_point',
           'mirror_anchor', 'mirror_svg_transform']

MIRROR_AXES = ('x', 'y')
ANCHOR_DIRECTIONS = ('left', 'right', 'up', 'down')
# 端口契约摘要取键口径(#63 固定,只取存在者;'port_kind' 为键名本体)
PORT_CONTRACT_FIELDS = ('id', 'svg_element_id', 'medium', 'role',
                        'flow_capability', 'anchor_direction', 'port_kind')

_ANCHOR_X = {'left': 'right', 'right': 'left', 'up': 'up', 'down': 'down'}
_ANCHOR_Y = {'left': 'left', 'right': 'right', 'up': 'down', 'down': 'up'}
_HEX64 = frozenset('0123456789abcdef')


def _where(node, component):
    bits = []
    if isinstance(node, dict):
        symbol = node.get('symbol')
        if isinstance(symbol, str) and symbol:
            bits.append('symbol=%s' % symbol)
    if isinstance(component, dict):
        ctype = component.get('component_type')
        if isinstance(ctype, str) and ctype:
            bits.append('type=%s' % ctype)
    return 'mirror[%s]' % (', '.join(bits) if bits else '未知节点')


def _mirror_axis(value, where):
    """布局节点 mirror 原值 -> None/'x'/'y';判等一律用恒等或字符串,
    0 不因 == False 被当成 False。"""
    if value is None or value is False:
        return None
    if isinstance(value, str):
        if value == 'none':
            return None
        if value in MIRROR_AXES:
            return value
    raise ValueError(
        "%s: 不支持的 mirror=%r;允许缺省/None/False/'none'/'x'/'y',"
        'True、数字与其他字符串/容器一律拒绝(0 不是 False)'
        % (where, value))


def _resolved_axis(value, where):
    """几何函数的 axis 只收 check_mirror 的解析结果(None/'x'/'y')。"""
    if value is None:
        return None
    if isinstance(value, str) and value in MIRROR_AXES:
        return value
    raise ValueError(
        "%s: axis 只允许 None/'x'/'y'(此处应传 check_mirror 的解析结果,"
        "原始 'none' 等值须先经 check_mirror 归一),实际 %r"
        % (where, value))


def _finite(value, name, where, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('%s: %s 必须为有限数,实际 %r(%s)'
                         % (where, name, value, type(value).__name__))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('%s: %s 必须为有限数,实际 %r' % (where, name, value))
    if positive and number <= 0.0:
        raise ValueError('%s: %s 必须为正数,实际 %r' % (where, name, value))
    return number


def _sha256_file(path, where):
    if isinstance(path, bool) or not isinstance(path, (str, os.PathLike)):
        raise ValueError('%s: asset_path 必须为符号文件路径(str/PathLike),'
                         '实际 %r' % (where, path))
    digest = hashlib.sha256()
    try:
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
    except OSError as error:
        raise ValueError('%s: 无法读取镜像登记绑定的符号文件 %s:%s'
                         % (where, path, error))
    return digest.hexdigest()


def _hex_digest_field(registration, key, where):
    value = registration.get(key)
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in _HEX64 for char in value)):
        raise ValueError('%s: mirror_registration.%s 必须为 64 位小写十六进制'
                         '摘要,实际 %r' % (where, key, value))
    return value


def port_contract_digest(component_type, ports):
    """目录端口契约摘要(#63 固定口径,登记与校验共用,勿另起实现)。

    payload = {'component_type': 类型, 'ports': 按 id 排序的端口字典列表};
    每口仅取 PORT_CONTRACT_FIELDS 中存在的键;json.dumps(
    ensure_ascii=False, sort_keys=True, separators=(',',':')) 后取
    UTF-8 编码的 SHA-256。
    """
    if not isinstance(component_type, str) or not component_type:
        raise ValueError('port_contract_digest: component_type 必须为非空'
                         ' str,实际 %r' % (component_type,))
    if not isinstance(ports, (list, tuple)):
        raise ValueError('%s: ports 必须为列表,实际 %s'
                         % (component_type, type(ports).__name__))
    entries, seen = [], set()
    for index, port in enumerate(ports):
        if not isinstance(port, dict):
            raise ValueError('%s: ports[%d] 必须为 dict,实际 %s'
                             % (component_type, index, type(port).__name__))
        pid = port.get('id')
        if not isinstance(pid, str) or not pid:
            raise ValueError('%s: ports[%d].id 必须为非空 str'
                             % (component_type, index))
        if pid in seen:
            raise ValueError('%s: 端口 id 重复:%s' % (component_type, pid))
        seen.add(pid)
        entries.append({key: port[key]
                        for key in PORT_CONTRACT_FIELDS if key in port})
    entries.sort(key=lambda entry: entry['id'])
    payload = {'component_type': component_type, 'ports': entries}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def mirror_point(x, y, width, height, axis):
    """归一盒坐标点镜像:'x' 反射 x->W-x,'y' 反射 y->H-y,其余轴不动。"""
    where = 'mirror_point'
    xf = _finite(x, 'x', where)
    yf = _finite(y, 'y', where)
    wf = _finite(width, 'width', where, positive=True)
    hf = _finite(height, 'height', where, positive=True)
    axis = _resolved_axis(axis, where)
    if axis == 'x':
        return (wf - xf, yf)
    if axis == 'y':
        return (xf, hf - yf)
    return (xf, yf)


def mirror_anchor(anchor, axis):
    """锚向镜像:'x' 互换 left/right,'y' 互换 up/down,axis=None 原样。"""
    where = 'mirror_anchor'
    if not isinstance(anchor, str) or anchor not in ANCHOR_DIRECTIONS:
        raise ValueError('%s: anchor 只允许 %s,实际 %r'
                         % (where, '/'.join(ANCHOR_DIRECTIONS), anchor))
    axis = _resolved_axis(axis, where)
    if axis == 'x':
        return _ANCHOR_X[anchor]
    if axis == 'y':
        return _ANCHOR_Y[anchor]
    return anchor


def mirror_svg_transform(width, height, axis):
    """镜像 SVG 变换串:插在实例链 rotate(...) 之后、scale(k) 之前。

    无镜像返回空串(既有链逐字节不变);'x' -> 'translate(W,0) scale(-1,1)',
    'y' -> 'translate(0,H) scale(1,-1)'。数字格式与渲染器一致(%g)。
    只做镜像,不重复实现旋转;尺寸校验不因无镜像而豁免。
    """
    where = 'mirror_svg_transform'
    wf = _finite(width, 'width', where, positive=True)
    hf = _finite(height, 'height', where, positive=True)
    axis = _resolved_axis(axis, where)
    if axis == 'x':
        return 'translate(%g,0) scale(-1,1)' % wf
    if axis == 'y':
        return 'translate(0,%g) scale(1,-1)' % hf
    return ''


def check_mirror(node, component, asset_path):
    """裁决布局节点的镜像请求,返回 None(不镜像)或 'x'/'y'。

    非镜像请求不要求任何登记,既有布局完全兼容;镜像请求须同时过
    mirror_safe / layout.allow_mirror / mirror_registration 三道闸,
    登记与当前符号文件字节及目录端口契约绑定,资产或端口一改即失效。
    任何拒绝都抛带定位信息(component_type/符号/原因)的 ValueError。
    """
    if not isinstance(node, dict):
        raise ValueError('check_mirror: node 必须为布局节点 dict,实际 %s'
                         % type(node).__name__)
    where = _where(node, component)
    axis = _mirror_axis(node.get('mirror'), where)
    if axis is None:
        return None

    if not isinstance(component, dict):
        raise ValueError('%s: 请求 mirror=%r,但目录条目不是 dict(%s)'
                         % (where, axis, type(component).__name__))
    ctype = component.get('component_type')
    if not isinstance(ctype, str) or not ctype:
        raise ValueError('%s: 请求 mirror=%r,但目录条目缺少有效'
                         ' component_type' % (where, axis))
    if component.get('mirror_safe') is not True:
        raise ValueError('%s: mirror=%r 要求目录 mirror_safe=true'
                         '(逐组件镜像许可登记),该组件未获许可' % (where, axis))
    layout = component.get('layout')
    if not isinstance(layout, dict) or layout.get('allow_mirror') is not True:
        raise ValueError('%s: mirror=%r 要求目录 layout.allow_mirror=true,'
                         '该组件布局层未允许镜像' % (where, axis))
    registration = component.get('mirror_registration')
    if not isinstance(registration, dict):
        raise ValueError('%s: mirror=%r 缺少有效的 mirror_registration 登记,'
                         '未登记不得镜像' % (where, axis))
    axes = registration.get('axes')
    if not isinstance(axes, list) or not axes:
        raise ValueError("%s: mirror_registration.axes 必须为非空列表(只允许"
                         "'x'/'y'),实际 %r" % (where, axes))
    for item in axes:
        if not isinstance(item, str) or item not in MIRROR_AXES:
            raise ValueError("%s: mirror_registration.axes 含非法轴 %r"
                             "(只允许 'x'/'y')" % (where, item))
    if len(set(axes)) != len(axes):
        raise ValueError('%s: mirror_registration.axes 存在重复项:%r'
                         % (where, axes))
    if axis not in axes:
        raise ValueError('%s: 镜像轴 %r 未在登记 axes=%r 内获批准'
                         % (where, axis, axes))

    registered_asset = _hex_digest_field(registration, 'asset_sha256', where)
    registered_ports = _hex_digest_field(registration, 'ports_sha256', where)
    current_asset = _sha256_file(asset_path, where)
    if registered_asset != current_asset:
        raise ValueError(
            '%s: 镜像登记已失效——符号文件 %s 当前 sha256=%s,与登记 %s 不符;'
            '符号变更后必须按新资产重新登记'
            % (where, asset_path, current_asset, registered_asset))
    current_ports = port_contract_digest(ctype, component.get('ports'))
    if registered_ports != current_ports:
        raise ValueError(
            '%s: 镜像登记已失效——目录端口契约当前摘要 %s,与登记 %s 不符;'
            '端口契约变更后必须重新登记'
            % (where, current_ports, registered_ports))
    return axis
