# 归档索引

main 只保留维护所需源码/测试/输入/说明；运行产物与历史批次资料由归档标签留存，
不在 main 留副本。

- **归档标签**：[`archive-main-before-cleanup-20261013`](https://github.com/sbhorshy/hydraulic-schematics/tree/archive-main-before-cleanup-20261013)
  （提交 `e9cc0fc`，2026-10-13 清理前 main 的完整快照，只增不改）。
- **取回方式**：`git checkout archive-main-before-cleanup-20261013 -- <旧路径>`
  到独立工作区；或直接浏览标签内文件。归档不是工作分支，不要在其上开发。

## 2026-10-13 清理移出的内容（按原路径在标签下可查）

| 类别 | 原路径 |
|---|---|
| 历史批次 research | `research/glm-followup-20261012/`（`whole-graph-planarity.*` 除外，仍在 main）、`research/glm-followup-20261013/`、`research/glm-rotation-guides-20261013/`、`research/glm-tickets-20261012/`、`research/ready-work-20261009/`（accumulator 基线已具名迁移为 `tests/fixtures/accumulator-baseline.json`）、`research/spec-materials.md` |
| 验收/审查/evidence | `docs/specs/ready-tickets-20261009-acceptance.md`、`docs/specs/ready-tickets-20261009-review.md`、`docs/specs/ready-tickets-20261009-evidence/`、`docs/specs/schematic-proofreading-acceptance.md`、`docs/specs/schematic-proofreading-review.md`、`docs/specs/schematic-proofreading-evidence/` |
| 1# 原型与历史产物 | `1#系统原理图/proto/`、已生成 SVG/PNG/拓扑清单/validation-report/回读裁剪/快照（`symbols/` 符号库保留）、`1#系统原理图/现状基线-v2.3.md` |
| 退役原型 | `prototype-precheck/` |
| 本地票镜像 | `issues/`（工单唯一权威在 GitHub Issues） |

## 仍引用归档的指针

- `.agents/skills/hydraulic-schematic/assets/component-library/component-catalog.json`
  的镜像解禁登记 note 引用 `research/glm-followup-20261012/mirror-registration.md`——
  该文件在归档标签下按原路径解析。
- skill `references/rendering-rules.md` 对 `prototype-precheck/calibrate_profile.py`
  实测脚本的引用同样在标签下解析。

## 纪律

日志、验收截图、逐文件清单等新产物放被忽略的 `.artifacts/`（或仓库外目录），
**不写回本文件、不回填 main**；历史资料只在标签里，不在 main 复制副本。
