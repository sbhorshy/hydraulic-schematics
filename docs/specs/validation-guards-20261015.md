# 图纸漏检补强：#83–#87 实施与验收

来源：2026-10-15 的 1# 系统 SysML 修改、出图、回读及 FSOV-001.command 红圈问题。

五票由 to-tickets 工作流建立，均可独立验收，无原生阻塞依赖。通过 Windows zcode-bridge 执行候选补丁，控制端进行独立回归、代码复核及规范源整合。

## 工单与行为

| 工单 | 新增或补强的行为 |
|---|---|
| [#83](https://github.com/sbhorshy/hydraulic-schematics/issues/83) | V11 检查最终根 SVG 的严格 H/V，不再把 0.1–0.5 单位斜线当作正交；生成器保留真实端点和短折点。 |
| [#84](https://github.com/sbhorshy/hydraulic-schematics/issues/84) | V16 覆盖未连接端口；孤立红圈、隐藏引线和本体接触缺口不能成为通过证据。明确 body_tap 接触可通过，裁剪/未知几何不伪称测量完成。 |
| [#85](https://github.com/sbhorshy/hydraulic-schematics/issues/85) | V17 从输入拓扑推导跨多个连接段的吸油链，校核实际管线和外引线类别/宽度；局部两侧同时画错也会被发现。 |
| [#86](https://github.com/sbhorshy/hydraulic-schematics/issues/86) | V10 比较声明网络与可见管网的环秩，阻断未声明的小闭环，保留真实输入闭环、母线树和共享短桩。 |
| [#87](https://github.com/sbhorshy/hydraulic-schematics/issues/87) | 为内部标识提供显式正向文字声明；渲染只补偿文字方向，V12 从最终字形检查旋转/镜像及源枢轴位置。 |

## 验收依据

- 修改前完整自检：30 个套件、584 个 unittest 用例通过。
- 独立复现旧缺口：0.3 单位斜线的 V11 仍为 pass；把未接泵轴端口移到空白角落后，旧 V16 仍为 pass。
- 修改后新增反例通过真实渲染/校验 CLI 验证，不以辅助函数返回值代替图面行为。
- 保留原有数值构图预算、图像版本绑定和独立回读制度；本次未放宽零交叉预算或将旧图升格为已交付。

- 最终完整自检：35 个套件、614 个 unittest 用例；全部通过。

库结构检查通过（既有接通位 QD 的端口组豁免仍按原登记披露，未扩大豁免）。完整自检覆盖 skill 的 A–F 组，不含另立的编辑器/repository 测试。

## 复核修正

- 新 taps 测试夹具补齐 externs 空映射；未放宽生产代码断言。
- 旧“合法四通”测试用三个端点绕出了未声明环；改为四个端点的真实四通树，保留 V4/V10/V14 通过断言。原错误构型由新增闭环负例覆盖。
- 直接接触本体的感测口遇到裁剪/滤镜时保持未校核；不能只因未裁剪轮廓经过该点就当成可见接触。
- 正向标识覆盖根级 text；未声明文本保持既有旋转行为。
- 直接本体锚改用浏览器原生描画命中，新增矩形/折线真接触与虚拟对角弦反例，避免误报和漏报。
- 缺少显示证据时不把环秩计算升级为已测得的可见闭环。
- 透明本体的原测试保留像素/原生接触断言，结果由未校核加强为明确失败；已测得不存在的接触不再伪装成测量缺失。

## 执行与变更保护

执行使用当前工作区内容的隔离 worktree 快照；整合前逐文件核对主工作区仍与启动时 SHA-256 相同，只复制本次 18 个变化文件。用户原有修改保留。

隔离候选提交：`5d2b82b79e2308deed21f3b76db1add5fb3c7af2`（本地）。原始项目图像和 SysML 拓扑未在本次检查功能实施中改写。

桥接运行曾出现调查阶段无代码产出、以及写入完成后复查超时。相应执行状态保留为取消/超时，未改写为 completed；已落盘候选先经控制端独立专项验收，再整合并运行完整自检。#86 首次回归发现旧夹具中的真实闭环，修正夹具后复测通过。

## 本地证据

- `.scratch/validation-guards-20261015/tickets.json`：工单编号与正文。
- `.scratch/validation-guards-20261015/baseline-gaps.json`：旧版漏检复现。
- `.scratch/validation-guards-20261015/baseline-selftest.json`：修改前完整基线。
- `.scratch/validation-guards-20261015/release-selftest.json`、`release-selftest.log`、`release-suite-logs/`：最终完整验收。
- `.scratch/validation-guards-20261015/integration.json`：整合文件与前后内容哈希。
- Windows bridge `.runs/` 中保存原生执行状态、权限事件、用量与独立测试报告。

| 阶段 | bridge task id |
|---|---|
| #83 初次调查（取消） | task-cb62fc3ae2794255911dc7960d587f28 |
| #83 初次阶段 A（超时） | task-1e720d8fc1cd493dbb2e8868a92fd029 |
| #83 阶段 A 补丁执行 | task-f579d507fbfa4fec8f2414770d74d967 |
| #83 阶段 B（写入后超时，控制端续验） | task-d96ec377c65843eca6e66b2ea2003016 |
| #84（写入后超时，控制端续验） | task-ed33504594464c02927f666d59f21971 |
| #85 | task-ced286c339f04eefa47fa85b45cf3843 |
| #86 | task-11af89b6af3841c79a9e5ddaa7f19406 |
| #87 | task-3029e6debe9c49ae9c091e0d30182ef9 |

## 复跑

```bash
python3 -B .agents/skills/hydraulic-schematic/scripts/check_library.py
python3 -B .agents/skills/hydraulic-schematic/scripts/selftest.py --jobs 4
```

## 发布补记（2026-10-15）

已推送至 GitHub `main`，提交 [197c531](https://github.com/sbhorshy/hydraulic-schematics/commit/197c531ba0bc42acf7e712763c84a4574743e094)；#83–#88 均已核对为 CLOSED。发布基于远端最新源码树，只移植这六票实现，保留远端现有实验模块取舍。

发布版本完整验证：skill 33 套件 / 416 用例，repository 59 用例，scheduler 25 用例，合计 500 项全部通过。与上文 623 项本地快照的差别是远端未纳入三个实验性 SysML 转换套件（207 用例）；没有删除正式源码树的必需测试。新增六个套件也已补入仓库级注册清单检查。

现用项目为适配硬避障，仅调整 EMP/CDF/ACC 标签位置与 RET 母线 x=970→980；组件位置、端口和拓扑不变。原单桥断言以及 B3≤1.447、B4≥16、B5≥43 未放宽，实测 B3=1.312、B4=18、B5=44。原 CV 标签 B7 净距残差继续披露，不视为整图签认。

发布记录：`.scratch/routing-boundaries-20261015/publication.json`；完整报告与日志使用同目录 `publish-*` 文件。按远端仓库内容规则，批次验收记录保留本地，发布维护源码、测试和必要输入。
