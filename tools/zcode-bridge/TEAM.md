# 多 agent 协同：主控、实现者与独立审核

本版本提供可恢复的任务调度与交接，供当前 Codex 主控调用。GLM 经 bridge 实施；主控或其只读专家检查固定候选，再提交结构化裁决。程序执行测试和串行集成，默认一个写者。它不会自行启动另一个 Codex 客户端、修改模型配置、推送代码或更新 GitHub 工单。

## 起步

1. 复制 `team.example.json`，填入真实 repo、明确基线、任务范围、依赖与实际测试命令。保留原工作区的未提交修改；工作树从指定 Git commit 创建，不自动带入脏文件。
2. 主控核对已有工单的决定与前置条件。未满足的外部依赖填在任务的 `external_blocks` 中；程序不把开放票自动判为已解决。
3. 启动并查看审核包：

```bash
bash ask-zcode.sh team start --plan team.example.json
bash ask-zcode.sh team observe team-xxxxxxxx
```

返回包括 `run_id`、`revision`、每项任务状态、`next_decisions`、审核包路径、集成分支和完整状态文件路径。状态回复不重复回传全部提示词、历史和长日志。

后台调度器按依赖派发。独立任务 B 可以在候选 A 测试/审核期间实施；依赖 A 的任务必须等 A 集成通过才启动。每项任务和每次集成试跑都有独立 worktree，主工作区不切分支、不 reset、不 stash。

`observe` 也会读取执行器的即时进展告警，放入 `next_decisions`，不为每秒变化的计时递增计划 revision。主控可据此判断继续等待、取消单个 bridge 执行或拆小任务；告警本身不改变依赖关系或批准候选。

## 审核与定向修复

当状态为 `awaiting_review`，打开 `review_packet` 与其中的 patch、候选源码和验收条件。审核者读取固定提交；测试结果位于任务的 `validation.report_file`。没有测试的任务明确记录 `not_run`，仍需要主控裁决，不冒充测试通过。

通过的裁决示例，保存为 `decision.json`：

```json
{
  "action": "approve",
  "task_id": "cli-fix",
  "candidate_commit": "从 observe 取得的完整提交哈希",
  "reviewer": "Codex-independent-review",
  "summary": "检查了具体触发条件、兼容行为和测试证据，无未解决发现。"
}
```

```bash
bash ask-zcode.sh team decide team-xxxxxxxx --revision 12 --decision-file decision.json
```

`revision` 是刚观察到的状态版本。状态过期时重新 observe；若候选提交未变，可以重新提交已有裁决，无需为了版本号变化重做审核。候选源码被修改时旧批准会被拒绝。`reviewer` 是审计标签；实际是否完成独立语义审核由主控负责，工具不会把填写这个字段当成独立 agent 已运行的证明。

发现具体问题时使用 `action: "revise"`，保留 task_id/candidate_commit/reviewer/summary，并增加 `findings: ["具体问题与复现依据"]`。程序保留原修改范围，附上上次实际验证报告和每项测试最多 12 KB 的日志尾部，在实际模型匹配时续接原 session。新一轮重新冻结、测试、审核；累计差异始终相对初始任务基线审计，避免重试把越界改动藏进新基线。

初次执行后默认最多两轮修复。耗尽后由主控重新拆分/规划；模型不会无限自我修复。`approve` 不能抹去失败测试或集成失败。

其他主控裁决：

| action | 用途与必填内容 |
| --- | --- |
| `resolve_block` | `task_id`、现有 `block`、`evidence`；由主控提供前置条件已满足的证据 |
| `retry` | 已失败的执行/检查，需 `task_id`、`summary` 说明诊断；同样消耗修复预算 |
| `retry_checks` | 未改动候选的测试环境故障，需 `task_id`、`summary`；只重跑控制端检查，不重新调用模型，重试同样有次数上限 |
| `retry_integration` | 未改动的已审核候选，需 `task_id`、`summary`；适用于测试环境等暂时故障。代码需要改时使用 revise |

批准和上述裁决由主控在已有授权范围内执行，不要求每一步让用户点确认。涉及未决工程事实、改变需求或新增授权时，主控先解决对应问题。

## 集成与交付

批准后，程序把候选相对初始任务基线的累计差异应用到当前集成版本的独立试跑工作树，运行 `integration_tests`。只有源码未变且检查通过（或明确未配置检查）才推进 `refs/heads/zcode-team/<run_id>`；冲突和失败保留现场。原分支、原工作区、远端及工单不自动改变。

完成后，主控检查该集成分支与证据，再根据具体任务的发布授权执行合入/同步/推送。代码、测试、图纸工程签认分开报告。依赖 `integrated` 表示其代码在批次集成分支中已接受，不表示相关 GitHub 票已经关闭。

## 模型与预算

默认预期模型为 `GLM-5.3-Flash`，从 CLI 事件的实际模型字段核验；缺字段或不匹配则失败，保留候选现场，不静默换模型。单任务也可显式要求：

```bash
bash ask-zcode.sh run '任务' --cwd /mnt/d/project --expected-model GLM-5.3-Flash
```

模型选择发生在现有 ZCode 配置/会话中，以上选项是核验要求，不负责替你修改全局设置。旧 session 的模型不符合预期时，应新建符合要求的执行会话。

`deadline_seconds` 限制整个批次，包括等待审核的时间；到期按取消流程清理。`task_timeout` 和 `idle_timeout` 限制各次模型执行，测试有各自 timeout。`executor_token_limit` 是**按已结束调用的 provider 用量限制后续派发**：在途调用可能超出，不能当精确硬 token 上限。主控/独立专家的外部用量记为 unknown，不虚构完整团队账单；费用由主控按实际账单另外核算。

计划新增 `progress_warning`（默认 120 秒）与 `progress_timeout`（默认 null，仅告警）。与 idle timer 不同，v3.4 按实质产出计时：范围内新的文件指纹、未重复的测试/构建结果或完成的子代理结果才续期。TodoWrite、读取、普通 shell、空写入和心跳不续期。测试结果按命令摘要/源码指纹/退出码去重，失败测试也可作为一次证据；工具完成不等于验证通过。详见 README。新计划的 `contract.tool_policy` 默认 development，通过每个任务自己的 app-server 客户端开放 Bash 和网页工具。GLM 可以自测；控制端仍独立验证。Agent/Task 默认开放受约束的只读子代理（2 并发、1 层、每任务 8 次、每子代理 12 轮），写入派发仍由 TEAM 管理，动态 workflow 保持关闭。子用量计入父任务与 TEAM 预算；子代理失败或取消导致用量不完整时，有 token 上限的计划停止新增派发。旧计划省略 policy 时保持 code-local；可显式选择 code-local 收紧权限。worktree 不构成 OS 沙箱，详见 README 的执行权限边界。

`executor_tokens` 仅表示已入账的已知用量；`executor_usage_complete` 和 `unknown_execution_count` 披露中断后缺失的 provider 用量。旧账本无法完整回溯时标记不完整，未知数量可为 null；不能把数值 0 解释为实际没有消耗。主控/专家的用量仍不在这个执行器统计中。

达到 token 派发上限时现有工作可完成，但不再启动新模型请求。主控检查成果与剩余任务，取消/结束旧批次后用明确预算和基线准备新计划，不直接改状态文件绕过限制。

## 并发与隔离

- 默认 `max_writers: 1`。最多两个在途候选容量；审核积压时停止派发。
- 声明相同 `resources` 或有潜在重叠的允许写路径的任务，等待前一个任务集成。`resources` 用于表达“端口语义”“catalog”等无法从文件名可靠推断的共享决定，主控负责正确填写。
- 每个批次一次运行一项控制端检查或集成检查。浏览器测试应自选独立端口/profile，目录隔离不能自动隔离外部服务。
- 两个写者须同时设置 `max_writers: 2` 和 `experimental_parallel: true`。Windows 本地夹具验证了分工作树/独立会话/重启不重派；真实 GLM 多实例的共享记忆、provider 限流及性能尚不由这些夹具保证，仍属实验选项。
- 仓库认领位于 Git common directory，跨 state-dir 和父子 cwd 生效；同仓库同时只接受一个活动批次。更新后的普通 bridge 入口也会登记执行占用，并拒绝绕过团队认领的调用；反过来，已有普通执行未结束时也不能启动团队。已经启动的旧版进程、外部编辑器和直接 shell 操作不受此机制控制，所以各检查还会核对源码指纹。
- worktree 与路径审计都不是操作系统沙箱。Git ignored 文件不在当前 bridge 快照覆盖内；全局 ZCode 配置、用户记忆和仓库级 refs 仍需主控协调。

## 状态与恢复

```text
planned / blocked → ready → running → checking → awaiting_review
                                              ↘ needs_changes → 新 attempt
awaiting_review → accepted → integrating → integrated
                             ↘ integration_failed
```

另外记录 failed、cancelled、批次 cancelling/completed，以及 preparing/freezing 等 Git 操作过渡态。进程清理不确定时不释放仓库认领。

```bash
bash ask-zcode.sh team cancel team-xxxxxxxx
bash ask-zcode.sh team observe team-xxxxxxxx
# 调度器异常退出后，从已保存执行 ID 恢复，不另派一个相同任务
bash ask-zcode.sh team resume team-xxxxxxxx
```

运行期间的 bridge 任务可由状态中的 bridge_task 找到。其执行状态目录为 `.teams/executions/`；需要恢复失联执行器时，使用相应 `--state-dir` 调用原 bridge 的 recover，再由主控提交 retry。

Git 操作中断、来源漂移或外部变更可能需要主控检查保留现场；程序不会为自动恢复而抹掉冲突文件。集成分支使用预期旧提交的条件更新。取消不会删除工作树或部分改动，主控确认不再需要后可用 Git 正常清理。

默认账本位于工具目录 `.teams/`，可用 `ZCODE_TEAM_STATE_DIR` 或 `team --state-dir <path>` 指定。该目录和工作树必须能被 Windows 访问，使用共享挂载路径；不要把普通 bridge 的 state-dir 直接设成源码根目录。协同工作树可以位于 `.teams/` 下，其源码仍完整参与当前快照覆盖范围内的校验。`state.json` 是持久状态，`events.jsonl` 是审计记录；操作通过 Interface 完成，不手改账本。

v3.1 快照优化保持原有清单与摘要语义，继续完整哈希文件，并保留关键交接点校验。测试准备复用已冻结候选的预期指纹，测试进程启动前仍会重新核验。更新不会重启已有执行器或调度器；新进程加载新代码，已经运行的进程在退出前仍使用其已加载版本。

## 验证

```bash
python3 -m unittest discover -s tests -v
# 无模型调用：真实 Windows 双执行器、调度器中断/恢复和集成
python3 tests/team_smoke.py /mnt/d/new-team-fixture-output
# 一次真实 Flash 实现、测试、确定性样例审核与集成；使用现有登录
python3 tests/team_smoke.py /mnt/d/new-team-live-output --live
```

真实样例中的审核由脚本检查精确内容，不宣称它替代生产代码的独立语义审核。输出目录必须是新目录。

新计划冻结 `contract.allow_subagents: true`；显式 false 可关闭。旧计划缺省值不自动升级。子代理适配绑定 ZCode bundle SHA256，详见 README；并非 OS 沙箱或公开稳定的原生配置项。

## 大范围任务的进度探测

v3.5 将执行中的文件探测放入独立辅助进程，避免扫描阻塞工具/完成事件和取消请求。文件范围为大量明确路径时不再做二次通配符遍历；扫描结束后冷却，自适应降低频率，最多一个在途。辅助进程由所属 bridge 任务清理与 recover 管理，不能绕过仓库认领。`probe_seconds` 可以与执行重叠，诊断主循环开销应同时查看 `probe_control_seconds`。

复杂实现任务仍应先约定最小可运行交付和一个专项测试，再扩展其余语义；扫描修复不保证模型首个文件的响应时间。独立 session 的 TEAM 写入仍统一排队，不自动抢占其他批次。

## v3.6 首次交付与零产出恢复

新计划冻结任务的 reasoning_effort 默认值（development 统一为 high）和 first_delivery（有明确写入范围与声明测试时默认180/300秒）。显式值优先；first_delivery:null 关闭该门禁。旧计划缺省字段不自动迁移。首次交付的目标是让一次调用结束一个可运行阶段，再由控制端执行选定行为检查；详见 README 和 team.staged.example.json。

零产出恢复只适用于 confirmed cleanup、changed_files=[] 且因 first_delivery_timeout 或 no_progress_timeout 停止的执行。若任务预先声明 recovery_prompt，可在修复预算内自动恢复一次；recovery_context 可提供最多4000字的已核实事实。新调用不传 resume，用 recovery_prompt 替换完整旧 prompt，仅补充事实、文件边界、验收和测试约束。它不会回放旧的冗长设计上下文，也不会自动生成或猜测更小的业务目标。程序校验非空、长度及不重复原提示；语义上是否真正缩小由主控负责。

没有预设更小目标时停止，主控可提交：

```json
{
  "action": "retry",
  "task_id": "core-slice",
  "summary": "无代码改动且达到首次交付期限，收敛为已确认的核心路径",
  "recovery_prompt": "填写本轮更小的可运行目标和明确输入输出，不包含后续扩展",
  "recovery_context": "填写已核实的接口、路径和现有基线；不填猜测"
}
```

第二次零产出失败必须重新规划，不能继续重复 retry；自动恢复也消耗原 max_repairs、总时限和用量预算。用量不完整且计划有 token 上限时，既有准入保护仍会阻止新调用。已有本轮实现或候选的测试/审核修复继续使用原会话，即使某次修复没有新增文件变化也不误转成零产出重开；首次交付检查失败会保留文件、报告和测试日志，交回主控诊断。

恢复到更小目标不代表原任务全部完成：原始测试、累计修改范围和独立审核仍保留。主控必须审核原任务验收条件，不能只凭首次交付通过批准整个功能。单任务 CLI 不进行隐藏的自动重派；上述一次性自动恢复由 TEAM 管理。
