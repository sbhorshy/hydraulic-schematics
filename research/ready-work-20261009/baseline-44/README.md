# 基线摸底与收口提交（2026-10-10）

结论：本次收口的是**有明确残差的可追溯基线**，不是全链合格金样。源码输入已由 `f3a00952fd5d13fffe85db4740c00fd064d60918` 捕获；本目录所在提交补齐摸底证据。后续票从这两个提交的后继开工，不能沿用旧 README 的“fail 0”作为当前验收。

## 版本与证据边界

- 规范源起点 `f93bd98c93dc8e496d88af8c3edb69fa5e1de740`，本轮运行 HEAD `e911038`；原工作树不清理、不覆盖。
- [原工作输入清单](../source-snapshot.json) 的 44 文件逐一重新计算 SHA-256，全部匹配。它们含项目、CDF、编辑器与历史产物；随捕获提交保留红项，不能因入 git 升格为通过证据。
- [provenance.json](provenance.json) 记录规范源全部 94 个跟踪文件的 SHA-256（全部与旧证明版本一致）、与全量 selftest 证明版本逐文件相等性及本机环境。源文件、资源、夹具的相等性允许复用旧回归证明，**不代表本轮重新运行 selftest**。
- 全量证明来自 [final-selftest.json](../../../docs/specs/schematic-proofreading-evidence/final-selftest.json) 及[完整日志](../../../docs/specs/schematic-proofreading-evidence/final-selftest.log)：`a903a04b8a86530c505f7de6108eeb46f09c4fa3`，exit 0，226 tests、A–F 六组通过，810.524 秒。覆盖 SysML 金样、库结构门禁、L0 正负预检、引擎烟测、模板门禁及专项入口/预算/驱动/路由/PNG 测试。旧环境只保存 `/usr/bin/python`，未保存依赖/浏览器/OS 版本；故**环境等价未证明**，本轮新跑只为下表给出的范围提供当前环境证据。后续源码变更须重跑其适用回归。

## 本轮红绿面

所有命令、退出码见 [runs.json](runs.json)，控制台日志与新 convergence/validation 报告同目录。每条 driver 用独立工作目录；运行时临时目录完整副本持久保存于 `.scratch/ready-work/issue-44-evidence/workdirs/`。driver 不加 optimize，尊重既有 seed；引擎另以独立诊断 probe 验证，不伪称 seed 途径执行过引擎。

| 范围 | 结果 | 已执行 / 未执行 |
|---|---|---|
| canonical check_library | 绿，exit 0 | L1–L3 硬档；包含既有 QD whitelist 披露，不等同 C1–C13 全库门禁 |
| 项目 intent + 项目 catalog + 项目 seed | 红，exit 3 | preflight 过，seed 加载；render 因 TANK 缺 body_sense_tap 失败；PNG、几何校核、感知签认未执行 |
| 项目独立 engine probe | 绿，exit 0 | 23 nodes / 6 buses；只证明现有 23 部件可布局，不证明 SysML 新增六件可布局或图纸可交付 |
| 历史 skill-chain-e2e + 当前规范源 | 红，exit 2 | preflight 在 QDP/QDR 的 inlet 拦截；layout/engine、render、PNG、validate 均未执行 |
| 历史独立 engine probe | 绿，exit 0 | 22 nodes / 6 buses；此 probe 未经过 preflight，仅用于根因诊断，不能把当前未复现 UNSAT 当成旧 e2e 全链绿 |
| canonical l0-current + 自带 seed | 红，exit 1 | preflight、seed、render、1:1 PNG、validate、局部回读均执行；13 FAIL / 9 WARN，134 对象 / 62 局部图；perceptual_review pending，delivery 不通过 |
| 全库符号 C1–C13 | 红，exit 1；22 件 / 2 ERROR / 2 可正式出图 | 独立复制既有 check_symbol.py + 当前 canonical catalog，对全库组件 SVG 执行；完整结果见 symbol-gate.log，不能用 active 子集替代 |

注意：失败驱动器摘要中的 `fail 0` 是未执行校核时的空计数，不是项目几何通过。没有人为感知签认，未修改 maturity、白名单或预算阈值。

## 根因 → 后续工单

| 实测或静态事实 | 归因与交付边界 | 承接工单 |
|---|---|---|
| 项目实际 TANK 符号没有目录声明的 body_sense_tap | 项目布局/目录仍选旧油箱，规范源新油箱已有该口；需要迁移真实几何，不能只改文件名 | [旧油箱符号退役](https://github.com/sbhorshy/hydraulic-schematics/issues/49)；生成器回写风险由[build_catalog 重构与双册对齐](https://github.com/sbhorshy/hydraulic-schematics/issues/48)承接 |
| 旧 e2e 使用 QDP/QDR.inlet | QD 侧别兑现后历史输入契约失效；不得靠跳过 preflight 声称全链绿 | [selftest D 红修复与 skill-chain-e2e 冻结态重钉](https://github.com/sbhorshy/hydraulic-schematics/issues/47)；[QD 禁吻约束与朝向规则](https://github.com/sbhorshy/hydraulic-schematics/issues/50) |
| selftest D 的当前规范源证明为 PASS；项目 23 件 engine probe 也通过 | 旧“check_valve_refuel 未登记导致 D 红”不再适用于这个版本；不能因此推断 29 件 SysML 已支持 | [FOOTPRINT 新类型登记与引擎补齐](https://github.com/sbhorshy/hydraulic-schematics/issues/45)核对剩余真实类型/端口；冻结金样仍归上述重钉票 |
| canonical-current 气侧 V3/V2/V13 + V10/V14 连通错误 | 旧气侧布局回折、穿 ACV 本体，ACC 液端与气侧串接口径尚未同步 | [蓄压器移挂与气侧链串接落 intent](https://github.com/sbhorshy/hydraulic-schematics/issues/46)；新正确输入之后余下冻结布局由重钉票承接 |
| canonical-current V10/V14：@CASE 与 @PRESS 等不同网络几何误接，V19/B1 交叉 1 > 0 | 当前真实几何残差；不是 validator 误报，不放宽预算。13 条逐项原文见 validation-report | [selftest D 红修复与 skill-chain-e2e 冻结态重钉](https://github.com/sbhorshy/hydraulic-schematics/issues/47)，保留[逐边追溯](https://github.com/sbhorshy/hydraulic-schematics/issues/65)及[真实连通关系校核](https://github.com/sbhorshy/hydraulic-schematics/issues/66)已落实的门禁 |
| 票面所指压差油滤相关资产（当前 v4.3 / 100×158）与 f93 已测规范源相同；新 canonical 流水线已经重新渲染校核 | “v4.2 未重跑”不能单独解释所有当前红项；项目由于 TANK 故障尚未走到该层，明确未校核 | 油箱退役后再跑项目链；残差逐项归入气侧同步/冻结重钉，不据旧 PNG 宣布通过 |
| 全库 C1–C13 的旧 FSOV 目录不符、连接位 QD 无端口组 | check_library 的白名单通过不足以解除入库门禁红；全库 22 件两 ERROR 不能改称 active 18 通过 | [check_symbol.py 入库门禁规范源归位进 skill](https://github.com/sbhorshy/hydraulic-schematics/issues/31)，QD 资产事实不足另归类型登记票 |
| build_catalog.py 含 D:/File/COMAC 硬编码写路径、旧油箱回写 | 静态检查，未原位执行；避免改写原工作输入 | [build_catalog 重构与双册对齐](https://github.com/sbhorshy/hydraulic-schematics/issues/48) |

SysML 静态对账：29 个系统 part、40 条系统 connect、19 条定义内部 connect；L0 只有 23 parts。额外六件是 ECO-001、CV-001、ACC-002、QD-001/002/003。现有 23 件绿引擎不能替代这些缺口；ECO/连接位 QD 的资产与实际端口定义不足，EMP overflow 不能猜。后续[转换器窄版](https://github.com/sbhorshy/hydraulic-schematics/issues/51)、[转换产物全链复现](https://github.com/sbhorshy/hydraulic-schematics/issues/52)、[枢纽泛化](https://github.com/sbhorshy/hydraulic-schematics/issues/53)仍受真实依赖阻塞。

## 复现

在本报告提交的 checkout 内运行（`RUN` 取新的独立目录，切勿指向规范源或历史输入目录）：

```bash
SKILL="$PWD/.agents/skills/hydraulic-schematic"
PROJECT="$PWD/1#系统原理图"
RUN=$(mktemp -d)
python "$SKILL/scripts/check_library.py"
python "$SKILL/scripts/validate_driver.py" --intent "$PROJECT/1#系统.intent.yaml" --catalog "$PROJECT/component-catalog.json" --layout-seed "$PROJECT/1#系统.layout.json" --workdir "$RUN/project"
python "$SKILL/scripts/layout_engine.py" "$PROJECT/1#系统.intent.yaml" "$PROJECT/component-catalog.json" "$PROJECT/1#系统.layout.json" -o "$RUN/project-engine.layout.json"
python "$SKILL/scripts/validate_driver.py" --intent "$PROJECT/skill-chain-e2e/1#系统.intent.yaml" --layout-seed "$PROJECT/skill-chain-e2e/1#系统.layout.json" --workdir "$RUN/historical-e2e"
python "$SKILL/scripts/validate_driver.py" --intent "$SKILL/assets/fixtures/l0-current/1#系统.intent.yaml" --layout-seed "$SKILL/assets/fixtures/l0-current/1#系统.layout.json" --workdir "$RUN/canonical-current"
# 可选择重新运行全量回归；本审计未把此命令算作新跑。
python "$SKILL/scripts/selftest.py"
```

逐命令检查返回码，红链按日志中断于对应阶段；不要使用 `set -e` 将整份摸底在第一红链处静默截断。全库 C1–C13 命令与历史 engine 诊断的完整 argv 也保存在 runs.json。历史引擎 probe 即使成功，也不消除其输入已被 preflight 判无效这一事实。
