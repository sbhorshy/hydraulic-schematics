# -*- coding: utf-8 -*-
"""#4 原型对比跑批器：三形态 × 坏/正两输入，收齐退出码与完整输出。"""
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')
FORMS = [
    ('A', '独立契约+轻量语义脚本', ['form-a', 'precheck_a.py']),
    ('B', '渲染器内置前置断言层', ['form-b', 'form_b_preflight.py']),
    ('H', '混合: A 管形状 + B 管语义', ['form-hybrid', 'hybrid_precheck.py']),
]
INPUTS = [('bad-mixed.intent.yaml', '预期拦截'),
          ('good-system1.intent.yaml', '预期放行')]


def main():
    os.makedirs(RESULTS, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    print('%-3s %-30s %-28s %-5s %s' % ('形', '形态', '输入', '退出码', '判定'))
    print('-' * 86)
    for fkey, fname, script in FORMS:
        for src, expect in INPUTS:
            r = subprocess.run([sys.executable, os.path.join(HERE, *script),
                                os.path.join(HERE, 'inputs', src)],
                               capture_output=True, env=env, cwd=HERE)
            out = (r.stdout or b'').decode('utf-8', 'replace') \
                + (r.stderr or b'').decode('utf-8', 'replace')
            tag = os.path.splitext(script[1])[0]
            with io.open(os.path.join(RESULTS, 'out-%s-%s.txt' % (fkey, src.split('.')[0])),
                         'w', encoding='utf-8') as f:
                f.write(out)
            hit = (r.returncode == 1) if expect == '预期拦截' else (r.returncode == 0)
            print('%-3s %-30s %-28s %-5d %s'
                  % (fkey, fname, src, r.returncode,
                     '✓ 符合预期' if hit else '✗ 不符合预期!'))
    print('\n原始输出已存 results/（坏输入人工可读报告，供报错体验对比）')


if __name__ == '__main__':
    main()
