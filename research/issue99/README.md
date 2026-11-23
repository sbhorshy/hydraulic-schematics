# 按失败项定向寻优原型（[按失败项定向布局优化：减少无效搜索并保留已通过指标](https://github.com/sbhorshy/hydraulic-schematics/issues/99)）

一次性原型，**不合并到 main**。回答的问题是：布局寻优是否应按当前失败项挑目标、只搜索会影响它的局部邻域。

- `../../.agents/skills/hydraulic-schematic/scripts/proto_issue99_targeted.py`：从 `validate_sheet` finding 取目标与邻域的纯逻辑；复用 `proto_optimize` 的评估器和动作集。
- `../../.agents/skills/hydraulic-schematic/scripts/proto_issue99_report.py`：从 `.artifacts/issue99/final/results.json` 生成单文件对照页。
- `results.json`：三组实测（1# 原图、FSOV 旋转 90°、RF 旋转 0°）的原始指标、停止原因与驱动器基线。
- `targeted-optimizer-prototype.html`：可双击打开的决策原型，内嵌最终图面、实测数据和状态演练。单文件，无服务端依赖。

复现时从仓库根目录准备三组工作目录（见 `1#系统原理图/README.md`），再运行 `python3 .artifacts/issue99/final_run.py`；产物只写 `.artifacts/`。快速评估器绑定项目 `symbols/`，并把 90°/270° 元件的宽高换算后再量 B5/V2，否则与官方报告不对账。

实测摘要：B1 注入定向策略 29 次评估清零、原预算 200 次仍 fail；V13 注入两者都未清零；正常图定向策略零寻优，原预算新增 V10/V19。驱动器第 2 轮因规则引擎未布 ACC-001/ACV-001/PG-001 而中断，`--optimize` 第 1 轮即中断。决定待[按失败项定向布局优化：减少无效搜索并保留已通过指标](https://github.com/sbhorshy/hydraulic-schematics/issues/99)的 HITL 回复，未落到规范源。
