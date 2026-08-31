# #13 校核驱动器 收敛演练存档（2026-08-31）

`validate_driver.py` 的四组验收运行，工作区为沙箱副本（规范源零改动），
临时 workdir 已清理，仅存结构化收敛报告。复现命令：

```bash
cd 1#系统原理图/proto/frozen
# 基线：干净链一轮收敛（引擎规则+守门，fail 0，warn 6=B3 存量超限披露）
python validate_driver.py --workdir driver-run-base
# 演练 A：传感对误入 paths（E-MED×2）→ 处方 P1 降级 taps → 轮 1 收敛
python validate_driver.py --workdir driver-run-A --inject a
# 演练 B：种子布局 ACC-001 y+170（V2 穿框 94 单位）→ 处方 P3 引擎重推
#          + --optimize → 轮 2 收敛（B3 1.447 全 pass，丁画像；P3 爬坡 ~15min）
python validate_driver.py --workdir driver-run-B --inject b \
    --layout-seed "1#系统丁.layout.json" --rounds 2
# 演练 C：terminal 串入 path 中段（E-TERM）→ 处方表无机械修法，
#          残差上报退出 2，渲染一行未启动（fail-closed）
python validate_driver.py --workdir driver-run-C --inject c
# 演练 B2（#14 换策略后回归）：同演练 B 注入，P3 已是首改进+浅拷贝+抛光帽
#          ——端到端 91.6s（策略更换前 940.9s），轮 2 fail 0
python validate_driver.py --workdir driver-run-B2 --inject b \
    --layout-seed "1#系统丁.layout.json" --rounds 2
# 演练 D（#12 定案门禁回归）：模板侧种子错（蓄压器 @分配→@用户供压）→
#          preflight 对账双向抓出（intent 无背书＋清单无落地）→ 残差退出 2
python validate_driver.py --workdir driver-run-D --inject d
```

## #12 定案后（2026-08-31 串联组合落码）

- `topology_confirm.audit()`：三向对账唯一实现，确认单 CLI 与 preflight 共用；
- `preflight.template_findings()`：对账差异=ERROR；签认按 maturity 分级
  （concept 未签认=WARN 披露，其余=ERROR 拦截），状态记录在模板 `签认:` 区；
- 渲染器钩子（proto_render/render）与驱动器沙箱均已启用模板门禁；
  演练 D 即该门禁的端到端拦截证据；基线（门禁激活）轮 1 收敛 5.3s。

要点：

- 收敛判据 = validation passed（fail 0）；WARN 沿披露通道随报告走。
- 卫生不变量：每轮渲染后强制重出 sheet-readback.png（-w 1680 = viewBox 宽，
  像素 1:1）——#19 两次踩坑的教训固化为驱动器步骤，故 V16 命中即真缺陷。
- 处方表 fail-closed：P1（纯传感链降级 taps）只动「恰两 token、双方显式
  端口、medium 均非液压」的 path；P3（引擎重推 + --optimize）只对
  V2/V13/V19(B1) 几何硬缺陷；其余 findings 一律残差上报不烧轮次。
- 引擎参照布局（--ref）只承载 labels 等呈现文案，坐标一律由规则重推。
