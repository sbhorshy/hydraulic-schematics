# 蓄压器液端与气侧同步（#46）

活动项目的 intent、显式布局和新图已对齐用户签认的三条 SysML 连接。本票采用**显式布局覆写**，保留现有系统和全部其他节点位置。默认规则引擎尚不能布置这个新支路，须带项目 `--layout-seed`；独立 engine probe 的“未布元件 ACC/ACV/PG”日志保留，不假称自动布局已支持。

| 签认模型 | L0 与新图 |
|---|---|
| SysML `connect PRV-002 to ACC-001.hydraulic_port`（行 294） | `paths[14] = [PRV-002.outlet, ACC-001.hydraulic_port]`，取已登记下游口，去掉原 @MANIFOLD 挂接 |
| SysML `ACC-001.gas_port to PG-001.pressure_sense`（行 329） | `taps[0]`：sensor=PG.pressure_sense，at=ACC.gas_port |
| SysML `PG-001.pressure_sense to ACV-001.accumulator_gas`（行 330） | `taps[1]`：sensor=ACV.accumulator_gas，at=PG.pressure_sense |

气側用链式 taps，符合当前 E-TAP 两端必须为已声明实例/真实端口的契约，未把 pneumatic 端口塞进 hydraulic paths。PG 仍只有一个物理 `pressure_sense` 口；两条模型边在该口汇接，新图显示同一气侧节点，不虚构贯通压力表的第二口。ACV 的 `charge_port` 开放、按既有 unknown 披露充气源未建模；旋转只改变装位，不换端口身份或提高成熟度。

ACC/PG/ACV 移到 PRV-002 右下方，PG 转 90°、ACV 转 180°，端口位置从各自 SVG 实读。气側/液侧与旧回油走廊的冲突通过项目水平候选走廊 y=890 → 1010 消除；图例、图签、其他节点和所有预算阈值保持原值。ACC 标签使用 above 槽、lift=19，使真实文字墨迹净空达到 6 px 门槛。

[局部新图](branch-readback.png)显示液端从 PRV 下游引出，气端到 PG 的唯一测压口，再接 ACV 气侧。该查看记录不是工程/感知签认，`delivery.ready=false`。

## 同源前后复验

使用同一套最终 driver/renderer/validator，分别运行 #49 合入后的旧项目输入与本次新输入；不是拿旧输出直接比较新校核器。完整 argv、退出码见 [runs.json](runs.json)，图像/报告 SHA-256、逐条失败、B1–B7、三条模型边、三件标签实际墨迹盒及变化线段见 [comparison.json](comparison.json)。完整工作目录持久保存于 `.scratch/ready-work/issue-46-evidence/workdirs/{before,after}/`。

- 旧链：13 FAIL / 9 WARN；新链：**6 FAIL / 9 WARN**。新增结构化硬失败集合为空；去掉原气側的折返、穿体、重复线及错误网络连接七条失败。
- 剩余六条是原压力/壳体网络误接（V10 三条、V14 两条）与原 B1 交叉一处（V19），无一归为通过。B1 仍为 1；B2/B3/B4 通过，B5/B6/B7 保留原有未达项，没有新增预算状态越界。实际数值在比较 JSON 中，不把它们都说成未变化。
- 新支路三条实际连线无 V2/V3/V10/V13/V14 新失败。与已画共享端口共线的警告如实保留，未豁免不同网络短接。
- 六行相关标签全部有浏览器墨迹测量，文本检查无未测项、无相关碰撞或小于 6 px 的净空告警；报告给出的是 6 px 已验证下界（检查器会剪枝远距离图元），不伪造精确最小距离。
- SVG 几何变化仅五条输入边：新增液端边、两条气側边，以及同一 PRV 下游到油箱的配套路由和油箱回油绕行。其他边的点串相同，差异逐条保存在比较 JSON。
- 新 driver 完成 preflight、seed、渲染、1:1 PNG、校核与 128 对象 / 62 局部回读；exit 1，感知与工程签认保持 pending。

TDD 在已授权的公开 CLI/SVG/PNG/report 接缝进行：先复现三条签认边缺失，再以实际文字净空 5.4 px 红例把检查收紧。最终 `test_accumulator_branch.py` 通过（含全图失败集合差分、B1 不劣化、三件标签净空、PG 单物理口）；现由 `tests/repository/` 入口显式执行。`check_library` 通过，既有 QD whitelist 不掩盖另票全库符号门禁的红项。本票未重跑全量 selftest；根代理整合后统一运行。

## 差异与范围

SysML 系统 29 parts / 40 connects（定义内部另 19 connects），项目 L0 仍为 23 parts。ECO-001、CV-001、ACC-002、QD-001/002/003 六件缺口未被静默删除；ECO/连接位 QD 资产端口事实和 EMP overflow 仍待[类型登记与引擎补齐](https://github.com/sbhorshy/hydraulic-schematics/issues/45)。本票不实现 SysML 转换器，不猜缺失端口。

SysML 仅更新“intent 尚待同步”的过时注释，connect 拓扑未改。规范源 `l0-current` 回归夹具与旧 skill-chain-e2e 继续保留原冻结输入（仍有其已披露红面），不是本次同步后的交付图；后续[冻结态重钉](https://github.com/sbhorshy/hydraulic-schematics/issues/47)负责它们的版本迁移。

复现（仓库根目录）：

```bash
python tests/repository/test_accumulator_branch.py
python .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent '1#系统原理图/1#系统.intent.yaml' \
  --catalog '1#系统原理图/component-catalog.json' \
  --layout-seed '1#系统原理图/1#系统.layout.json' \
  --workdir /tmp/accumulator-46-fresh
```

复现入口补记：本批最终自检可移植性修复把仓库专属集成用例移至 `tests/repository/`，不再计入独立 skill 自检；上面的原始运行证据仍按其受测版本解释。
