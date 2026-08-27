# hydraulic-schematic 能力抬升 —— Wayfinding 地图

<!-- labels: wayfinder:map -->

## Destination

`.agents/skills/hydraulic-schematic/` 补齐参照 fireworks-tech-graph 分析出的五项机制缺口：
出图质量有**量化构图预算**可判、输入定义在**布局前即被机器校验**（fail-closed）、
校验闭环带**轮数上限与修法处方**、技能自带**金样回归自测试**、文档写明**冲突次序与运行纪律**。
五者全部定型（决策关闭 + 实现路径清晰）即为抵达—— implementations 可随后另行执行。

## Notes

- 领域：航空液压系统原理图绘制工作流（见该 skill 的 SKILL.md 四条不变式，任何决议不得违反）。
- 参考系：上游 fireworks-tech-graph 的机制名——composition-quality-contract（数值构图契约）、
  validate before layout（语义预检）、two focused correction passes（有界收敛）、tests/ 套件（金样回归）、rule precedence。
- 本仓库为 git 仓库（`origin` = github.com 私有库 hydraulic-schematics），tracker 用本地 markdown：
  工单在本目录 `T0xx-*.md`，阻塞用正文 `Blocked-by` 约定；认领即填 `Assignee`。
  `.gitattributes` 已禁用换行转换以保字节一致性。
- 同步工具 sync_snapshot.py 已存在：任何触及 assets/scripts 的决议须注明"同步时快照刷新由其闸门接管"。
- 工作语言中文；引用工单一律用名称不用裸编号。

## Decisions so far

<!-- 每关闭一张票在此追加一行：[工单名称](链接) —— 一句话结论 -->

## Not yet specified

- 把「构图预算定档」产出的数值接进几何校核输出**度量面板**（穿越/折返/绕行比实测值）——等阈值冻结后才可立票。
- 「输入契约前置」定型后的正式**预检器实现**及其报告格式——形态二选一未决，不可提前切票。
- 若源图纸侧修复了油箱方言漂移，为 L0 链路补第二批金样——依赖外部动作，先不入列。
- 是否需要一个 doctor 类体检工具（引用文件存在性/frontmatter 完整性巡检）——价值待前几项落地后再议。

## Out of scope

- GIF 动效、interactive HTML 导出、12 风格体系：演示图谱域外能力，引入会稀释液压焦点。
- 修复 `已标注/1#系统原理图` 的符号方言漂移与陈旧存档本身：那是另一个工程（其修复反倒是本图外部的输入），本图只消费其结果。
