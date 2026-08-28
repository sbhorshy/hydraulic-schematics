# -*- coding: utf-8 -*-
"""混合形态原型：A 管形状、B 管语义。

分工：
  - 结构契约复用方案 A 的 l0-input-contract.schema.json（同一份声明式工件，
    编辑器补全/CI/任何工具都能吃）；
  - 语义核心直接 import 方案 B 的 preflight()（渲染器内置层以函数边界暴露，
    渲染器自身在 main() 里调的也是它）——语义只有一份实现，不会漂移。

接法（若是正式实现）: 渲染器 main() 先 import 混合入口做 schema 预检（或
预编译契约），再跑自家 preflight；独立 CLI 场景则两者都由本脚本代跑。
退出码: 0 过 / 1 有 ERROR。
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'form-a'))
sys.path.insert(0, os.path.join(HERE, '..', 'form-b'))

SCHEMA = os.path.join(HERE, '..', 'form-a', 'l0-input-contract.schema.json')
CATALOG = os.path.normpath(os.path.join(
    HERE, '..', '..', '.agents', 'skills', 'hydraulic-schematic',
    'assets', 'component-library', 'component-catalog.json'))


def main():
    import jsonschema
    from form_b_preflight import preflight, load_yaml, emit_preflight_failure

    src = os.path.abspath([a for a in sys.argv[1:] if not a.startswith('--')][0])
    intent, text = load_yaml(src)

    # —— 形状：声明式契约管 ——
    schema = json.load(io.open(SCHEMA, encoding='utf-8'))
    errs = sorted(jsonschema.Draft7Validator(schema).iter_errors(intent),
                  key=lambda e: list(e.absolute_path))
    print('[hybrid] 形状层（schema.json 复用 form-a）: %s'
          % ('%d 项结构违规' % len(errs) if errs else 'OK'))

    # —— 语义：渲染器内置核心管（与渲染器同源，一份实现两处调用）——
    rep = preflight(intent, json.load(io.open(CATALOG, encoding='utf-8')), text)
    print('[hybrid] 语义层（preflight 复用 form-b 核心）: %s' % rep['status'])

    # 两层收齐才合并出口，不在形状层提前停手（首错不停原则）
    rc = 0
    for e in errs:
        print('  %-14s %-5s %-28s %s\n               处方: 按 rendering-rules intent 章节修正形状'
              % ('E-SCH', 'ERROR', e.json_path, e.message))
        rc = 1
    if not rep['ok']:
        emit_preflight_failure(rep)
        rc = 1
    elif rep['findings']:
        for f in rep['findings']:
            print('  %s WARN %s | %s' % (f['id'], f['object'], f['message']))
    return rc


if __name__ == '__main__':
    sys.exit(main())
