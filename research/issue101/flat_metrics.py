# -*- coding: utf-8 -*-
"""#101 一次性：把六项候选指标摘要压成 {标量名: 数值}，便于比较离散度与挑对比对（不进 main）。"""


def flat(m):
    jg = m['m6']['junction_gap']
    jb = m['m6']['junction_bend']
    br = [x['other_gap'] for x in m['m6']['bridges'] if x['other_gap'] is not None]
    return dict(
        m1_max=m['m1']['max'], m1_sum=m['m1']['sum'],
        m2_rev=m['m2']['reversals'], m2_back=m['m2']['backward_frac_max'],
        m3_max=m['m3']['gap_max'], m3_mean=m['m3']['gap_mean'],
        m3_far=len(m['m3']['far']), m3_amb=len(m['m3']['ambiguous']),
        m4_n=m['m4']['count'], m4_len=m['m4']['length'], m4_main=m['m4']['main_count'],
        m5_min=m['m5']['min'], m5_short=len(m['m5']['short']), m5_mis=len(m['m5']['misaligned']),
        m6_jg=None if jg is None else jg['d'], m6_jb=None if jb is None else jb['d'],
        m6_br=min(br) if br else None, m6_n=m['m6']['junctions'])


def status_sig(panel):
    """B1–B7 等价类签名：各项状态 + B7 违限数（基线 B7 本来就是 over/1）。"""
    return tuple((k, v['status'], (v['measured'] or {}).get('violations') if k == 'B7' else None)
                 for k, v in sorted(panel.items()))
