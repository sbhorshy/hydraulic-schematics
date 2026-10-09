# Issue tracker: GitHub

本仓库工单和规格使用 GitHub Issues：`sbhorshy/hydraulic-schematics`。使用 `gh` CLI；可从 Git remote 核对仓库，跨目录执行时显式传 `--repo sbhorshy/hydraulic-schematics`。

## 日常操作

- 创建：`gh issue create --repo sbhorshy/hydraulic-schematics --title "标题" --body-file <正文文件>`。
- 读取：`gh issue view <编号> --repo sbhorshy/hydraulic-schematics --json number,title,body,labels,comments`。
- 列表：`gh issue list --repo sbhorshy/hydraulic-schematics --state open --json number,title,labels`；按需要增加标签和状态筛选。
- 标签：`gh issue edit <编号> --repo sbhorshy/hydraulic-schematics --add-label <标签>` 或 `--remove-label <标签>`；分拣角色以 `docs/agents/triage-labels.md` 为准。
- 评论：获授权后使用 `gh issue comment <编号> --repo sbhorshy/hydraulic-schematics --body-file <正文文件>`。
- 关闭：获授权后使用 `gh issue close <编号> --repo sbhorshy/hydraulic-schematics`。

多行正文写入 UTF-8 文件后通过 `--body-file` 传入，保留实际换行；需要调用 API 时使用 JSON 请求文件。旧版 gh 缺少某个子命令时，使用其 `gh api` 等价操作，无需仅为命令差异更换 tracker。

## 发布与读取

技能要求“publish to the issue tracker”时，在上述仓库创建 issue；本地 `.scratch/` 用于草稿和临时资料。技能要求读取相关工单时，读取正文与评论。

来源是现有 issue 时，遵循相应技能将新票挂为其子票；来源只是对话时，不推断父票。创建子票本身不授权关闭或重写父票。

## Wayfinding 与依赖

- 地图使用 `wayfinder:map`，子票继续使用既有 `wayfinder:research`、`wayfinder:prototype`、`wayfinder:grilling`、`wayfinder:task` 类型标签；这些标签不替代分拣角色。
- GitHub 的 database id 可由 `gh api repos/sbhorshy/hydraulic-schematics/issues/<编号> --jq .id` 取得，它不同于 issue 编号和 node_id。
- 子票关系：向 `repos/sbhorshy/hydraulic-schematics/issues/<父票编号>/sub_issues` 发 POST，正文使用数值 `sub_issue_id`。平台不支持时，在子票正文写 `Part of #<父票编号>`；只在任务授权范围内更新父票清单。
- 阻塞关系优先用原生 dependencies：向 `repos/sbhorshy/hydraulic-schematics/issues/<被阻塞票编号>/dependencies/blocked_by` 发 POST，正文使用阻塞票的数值 `issue_id`。平台不支持时，在被阻塞票正文写真实编号的 `Blocked by`。
- 工作前沿为所有阻塞票均已完成、且尚未被认领的票；原生 `issue_dependencies_summary.blocked_by` 表示仍开放的阻塞数量。文本依赖须逐一读取状态。
- `ready-for-agent` 表示规格可供代理执行，不表示依赖已经满足；开始实施前仍检查阻塞关系。

## Pull requests as a triage surface

**PRs as a request surface: no.**
