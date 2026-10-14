# 仓库内容取舍规则

main 是**维护源码树**：只保留让技能可运行、可回归、可接手的必要内容。

## 进 main

- 源码：`.agents/skills/hydraulic-schematic/`（整目录字节一致，分发取完整目录）、
  `editor-proto/`、项目薄入口。
- 测试：`tests/`（repository / scheduler / fixtures）。断言与测试输入不可因清理
  或重构删减；唯一允许的基线迁移方式是具名 fixture（见下）。
- 必要输入：项目 intent/layout/catalog/组件JSON/symbols 等被测试与生成链直接
  消费的文件。
- 必要说明：README、`docs/` 维护文档、仍被规范/许可引用的依据（现 3 份，
  见 `research/README.md`）。

## 不进 main

- 运行产物：生成 SVG/PNG、validation-report、拓扑清单、回读裁剪、快照、
  验收截图与日志 → 被忽略的 `.artifacts/`、`.scratch/` 或仓库外目录。
- 批次证据与历史验收材料 → 归档标签（见 `docs/archive.md`），不在 main 复制副本。
- 本地票镜像 → 工单唯一权威在 GitHub Issues。

## 历史回归 oracle 的收编方式

需要长期保留的旧产出必须作为**具名 test fixture** 迁入 `tests/fixtures/`，
并在同目录 README 记录来源标签、原路径与用途（先例：
`tests/fixtures/accumulator-baseline.json`）。不允许以"顺手留着"的目录文件
充当回归基线。

## 纪律

- 不能用清理删除断言、放宽阈值或移除测试输入；缺依赖时测试必须失败，
  不许 skip 冒充通过。
- 新增内容入库前先问：它被谁消费？没有消费者（测试/生成链/规范引用）的
  产物不进 main。
