# WSL → Windows ZCode bridge v3.6

保留 Windows ZCode 的现有登录与模型配置，由 WSL 派发、观察、取消和验证任务。标准库实现，无需安装 Python 依赖。新版不固定模型；实际用量以返回为准。

新增多 agent 协同入口：`bash ask-zcode.sh team start --plan team.example.json`。默认单写者，提供依赖、独立工作树、固定候选审核、串行测试/集成和重启恢复；使用方式见 [TEAM.md](TEAM.md)。原单任务调用继续可用；仓库有活动团队认领时，普通调用会被拒绝，以免绕过认领。

## 原调用方式继续可用

```bash
bash /mnt/c/Users/24270/zcode-bridge/ask-zcode.sh \
  '只修改指定文件，说明改动' --cwd /mnt/d/your-project --mode edit
```

stdout 始终只返回一个最终 JSON，保留 `sessionId`、`response`、`usage`；stderr 实时输出经过筛选的 JSON 事件。新增的 `status` 和退出码区分完成、受阻、中断与失败。`completed` 仅表示执行器正常返回且未触发桥接检查，**验证结论以 `validation_status` 为准**。

默认总时限 3600 秒、无有效事件时限 600 秒；用 `--timeout` 和 `--idle-timeout` 调整。合法的流式活动会更新最后活动时间，即使其内容不对外展示。两种时限不能传零、负数、NaN 或 Inf。

无产出监控与工具活动分开：默认 **120 秒没有新的实质产出就告警**；`--progress-timeout` 可设置硬停止期限，默认仍为 null，仅告警。TodoWrite、Read/Glob/Grep、网页读取、流量、普通 shell 查询、空写入不续期。只有范围内新的文件内容指纹、可识别且未重复的测试/构建结果，以及完成的子代理结果续期。

v3.5 的执行中进度扫描由独立、只读的辅助进程完成，事件消费线程只发起和轮询结果，最多一个扫描在途。精确文件名使用集合匹配，真正的 glob 每次构造时只编译一次，避免数百路径反复冲刷 fnmatch 缓存。每次仍对覆盖文件计算内容哈希，范围匹配与最终验收语义不变。

冷却时间从扫描**完成后**计算：通常至少 5 秒，并按扫描耗时适当增加（上限 60 秒，同时受任务的产出期限约束）；短告警/停止阈值会缩短基础间隔。单次辅助扫描最多 30 秒，超时清理自己的进程组。任务完成或取消时先停止扫描进程，worker 异常退出后 recover 也检查其归属再清理。最终验收仍执行完整快照，进度探测不代替验收。

纯读取和待办不触发扫描。mtime 变化、空写入、回到已见过的文件状态不算新产出；竞态读取失败不续期。扫描期间新发生的写入和测试结果会留给后续扫描处理，不能因为一次旧扫描完成就被丢掉。`probe_seconds` 在 process 模式下是辅助扫描累计墙钟时间，可能与模型/工具执行重叠；`probe_control_seconds` 才是发起与轮询占用主循环的时间。`probe_inflight`、`probe_timeouts`、`probe_abandoned` 用于观察在途、超时和终止时放弃的扫描。

测试/构建识别采用保守规则：直接调用 python -m unittest/pytest、pytest、node --test、常见包管理器 test/build、go/cargo/dotnet test/build 等；要求原生命令退出码。复合 shell、管道、缺失参数/退出码的结果不推断为测试证据。去重键为规范化命令摘要、当前范围内文件指纹、退出码；同一源码上的相同退出结果只续期一次。非零退出码可作为 TDD 的失败证据，但不会使 `validation_status` 变为通过；控制端测试仍独立执行。为了保留测试退出码，应单独运行测试命令，避免 `测试命令 | tail` 等管道遮蔽失败。

`progress` 分别报告工具完成、命令完成、文件产出、测试结果及 `seconds_without_output`；`seconds_without_tool_completion` 仅表示工具活动，不再决定停止。阶段可为 `tool_running`、`tool_input`、`model_output`、`model_streaming` 或 `waiting_model`。只记录模型流量的帧数和字节数，不记录推理或工具输入正文。活跃工具和持续流量不会延长无产出期限；长测试需配置合适的期限。已启动的旧 worker 不会热更新，新 worker 使用新规则。

```bash
bash ask-zcode.sh run '已定义的局部修改' --cwd /mnt/d/your-project \
  --progress-warning 120 --progress-timeout 300
```

## 先检查能力

```bash
bash ask-zcode.sh doctor
```

不调用模型、不读取凭据，只检查安装文件、Windows 互操作命令、CLI 协议能力标记，并记录 CLI SHA256。实际进程启动与运行时结果仍是最终依据。

新任务默认使用 `tool_policy: "development"`：通过原生 `app-server` 协议运行，bridge 为本任务提供一次性 permission client。GLM 可以使用 Read/Edit/Write/Glob/Grep、Bash、WebFetch/WebSearch、TodoWrite，以及受约束的 Agent/Task，直接完成修改、构建、测试与调试。`requires_shell: true` 在 development 的 edit/build 模式下可执行；plan 仍不授予执行批准。不会切换 yolo，也不修改用户或项目的永久授权配置。

收到审批请求时，仅对当前会话、上述工具、非 critical 风险授予一次性权限；其他会话、未知工具和 critical 请求拒绝。已登记子代理仅可获得只读工具授权，其他子代理请求拒绝。ZCode 原有直接拒绝规则继续生效。此处是对**送达客户端的审批请求**的处理，原生自动批准调用仍由 ZCode 决定。

Bash 运行在 Windows 主机上，worktree 不是操作系统沙箱。`allowed_files` 是任务约定和事后 diff 校验，不能限制 shell 的系统访问；发布、推送、部署、凭据访问等限制由任务提示约定，不能当作系统强制隔离。Bash timeout 单位为毫秒。网页工具已开放，但站点连通性、TLS、提供商支持仍可能导致调用失败。

新 development 任务默认 `allow_subagents: true`。GLM 可通过原生 Agent（Task 为兼容别名）自行派生 Explore 或 general-purpose 子代理，用于调查和审查。两种 profile 都在启动入口收紧为 Read/Glob/Grep/WebFetch/WebSearch，移除 Bash、写入、Skill、MCP 和再次派生能力；原生 RespondToCoordinator 只用于向父任务返回结果。子代理使用 plan 限制并继承父模型。最多 2 个同时运行、仅 1 层；每个 bridge 任务最多 8 次派生，每个子代理最多 12 轮。后台请求转为前台等待，父任务拿到全部子结果后才完成。写入委派仍需控制端登记 TEAM 任务，动态 workflow 保持关闭。控制端保留独立测试、审核及集成。

这些约束依赖 `subagent-runtime.cjs` 对**指定 SHA256 的 ZCode bundle**在本次进程内加载时添加的入口包装，涉及原生非公开接口。磁盘上的 ZCode 程序不变；升级后 hash 不匹配将拒绝启用子代理，需要重新审计适配，不能自动放宽。设置任务 `allow_subagents: false` 可继续使用普通 development 模式。

子代理生命周期写入脱敏事件，token 分别记录并汇入父任务 `usage`，TEAM 对汇总值记账。有子代理时无法完整聚合的请求次数字段不输出。取消、失败或缺失子用量时 `usage_complete` 为 false，已知 token 仅是下界；设置了 TEAM token 上限且用量不完整时，不再派发新任务。token 上限属于任务间准入预算，不是调用中精确硬截断；时间限制和取消会终止整个执行进程树。

需要旧行为时显式使用 `--tool-policy code-local`，禁用 Bash/WebFetch/WebSearch/Agent/Task。`cli-default` 仍走旧 headless 路径，仅移除 bridge 黑名单，并不补齐授权客户端。既有任务记录和 TEAM 计划未填写 policy/allow_subagents 时保留旧策略；新 TEAM 计划在创建时冻结 development 与 allow_subagents 默认值。

## 任务级思考强度与阶段交付

新 development 任务统一默认 `reasoning_effort: "high"`，包括实现与 plan 模式。可用 `--reasoning-effort low|high|max|inherit` 或任务 JSON 同名字段指定；inherit 沿用该会话的选择。bridge 先查询 ZCode 公布的档位，通过 session/setThoughtLevel 设置，再 session/read 回读确认；不支持或不一致时，在派发提示前失败，不静默退回高档。设置写入该 session 的运行配置，不修改 provider 或全局模型配置。结果记录 requested_reasoning_effort 与 reasoning_effort。旧任务未声明该字段时继续 inherit。

新任务如果声明了非空 allowed_files 和 tests，默认启用 first_delivery：180 秒告警、300 秒交回主控。可以显式设置 null 关闭，或定义更合适的目标文件、测试子集和时限：

```json
"first_delivery": {
  "files": ["src/example.py"],
  "test_ids": ["example-unit"],
  "warning_seconds": 180,
  "timeout_seconds": 300
}
```

该机制要求**一个调用只交付一个可运行阶段**。期限从 worker 开始计时，覆盖模型调用、进程清理和首次交付检查；代码写入、TodoWrite、心跳、普通测试结果都不重置它。模型结束且执行器清理后，控制端要求目标文件出现非空的新内容，并执行选定的已声明行为测试；通过且源码指纹不变才记录 first_delivery.status=passed。它不在生成途中猜测代码语义。空文件直接拒绝，TODO/pass 骨架要由真正调用公开行为的断言拒绝，测试有效性和完整需求仍需独立审核。

首次交付检查本身就是授权执行这些声明测试的入口，不需要额外 --run-tests。若仅检查了 tests 的子集，validation_status 为 partial；检查覆盖全部 tests 时为 passed。再指定 --run-tests 时，只运行尚未执行的测试，不重复已通过的检查。没有声明测试的纯提示调用不自动启用此门禁，因为无法证明其有效交付。已通过验证的 feedback 确认回合不要求再制造一次代码修改。

`progress.first_artifact_observed_at` 与 time_to_first_artifact_seconds 记录首次观察到文件变化的时间；first_delivery.seconds 是独立行为检查通过前的总时长，两者不可混称。首次交付告警区分模型/工具活动与控制端测试阶段。此版本不向正在运行的 session/send 强插催促消息。

通过 [team.staged.example.json](team.staged.example.json) 把核心行为、边界扩展拆为有依赖的独立任务；每步都冻结候选、测试、审核后再进入下一步。不要在第一步 prompt 里同时堆入全部后续实现目标。

## 结构化任务和测试闭环

复制并修改 [task.example.json](task.example.json)，路径相对 `--cwd`，只用 `/`，不允许绝对路径或 `..`。`allowed_files` 是必填 glob 数组，空数组表示不允许修改；`forbidden_files` 优先拒绝。`acceptance` 是交给实现者的验收文字，不能代替实际检查。

```bash
# 实现后立即由 WSL 控制端执行 task.json 中预先指定的测试
bash ask-zcode.sh run --task-file task.json --cwd /mnt/d/your-project --run-tests

# 只实现，之后再运行已经声明的测试
bash ask-zcode.sh run --task-file task.json --cwd /mnt/d/your-project
bash ask-zcode.sh verify task-xxxxxxxx

# 自动装入原会话 ID、原修改范围和绑定源版本的测试报告，发起一轮修复
bash ask-zcode.sh feedback task-xxxxxxxx
```

测试只执行任务定义中的 argv，不使用 shell 字符串，不执行模型临时建议的命令。`--run-tests` 或 `verify` 是控制端执行这些命令的明确入口；测试有独立时限并清理自己的 POSIX 进程组。请在已获授权的控制环境中调用。

测试报告区分 passed、failed、timed_out、not_run、source_changed；记录命令、退出码、时长和日志。报告绑定实现后的源文件指纹；运行测试期间源文件变化时不宣称通过。`feedback` 只接受本工具的报告，附上每项测试至多 12 KB 的日志尾部，并在启动前再次校验源指纹。它只启动一轮，不自动无限重试；是否再次运行测试沿用原任务的 `--run-tests`。

`--prompt-file` 支持纯文本任务；`--task-file` 支持 JSON 任务。提示词经共享文件传到 Windows，在 Node 进程内设置 CLI argv，不塞入 Windows OS 命令行，支持长文本、中文和字面量 `$()` 等字符。

## 会话续接

```bash
bash ask-zcode.sh run '修复上述问题，范围不变' \
  --cwd /mnt/d/your-project --resume sess_xxxxx
```

使用明确 session ID，不自动选择目录中最近会话。同一修复链可续接；契约改变、上下文过长或旧记忆冲突时开新会话。桥接会拒绝返回另一个 session ID 的异常结果。续接是否节省时间和用量需由实际指标判断。

## 异步、状态与取消

```bash
bash ask-zcode.sh submit --task-file task.json --cwd /mnt/d/your-project --run-tests
bash ask-zcode.sh status task-xxxxxxxx
bash ask-zcode.sh wait task-xxxxxxxx --timeout 60
bash ask-zcode.sh cancel task-xxxxxxxx
bash ask-zcode.sh wait task-xxxxxxxx --timeout 30
```

`submit` 返回 task ID，后台 worker 持续写状态；`wait` 的时限只限制等待，不取消任务。`cancel` 是取消请求，完成状态需用 `wait/status` 确认。

Windows 取消按本次唯一启动请求和原始进程命令行确认归属，再用 taskkill 清理该进程树；不会按程序名批量杀 ZCode。若清理失败或 worker 意外消失，同一 cwd 保留活动标记，拒绝新写任务。先执行：

```bash
bash ask-zcode.sh recover task-xxxxxxxx
```

恢复操作只确认并清理原任务进程，不自动重派、不删除已有部分修改。恢复后检查改动，再用原 session ID 开新任务。

同一状态目录下，同一规范化 cwd 通过锁互斥；Windows 挂载路径按大小写不敏感处理。使用不同工作目录不等于底层全局记忆/配置完全隔离；本版不增加并发调度。多个调用方必须共用状态目录才能互斥。

## 结果与记录

默认记录在工具目录 `.runs/<task-id>/`，可用环境变量 `ZCODE_BRIDGE_STATE_DIR` 或放在命令前的 `--state-dir /shared/path` 指定。Windows 启动需访问此目录；建议用 `/mnt/c` 或 `/mnt/d` 的共享目录。

- `state.json`：状态、worker 身份、session ID、活动时间及计数。
- `events.jsonl`：白名单事件，只含阶段、工具名称/ID、权限决定、测试状态等。模型私有 reasoning、消息历史、原始工具参数/结果和原始 stderr 不写入事件文件。
- `result.json`：最终公开回答、实现/验证状态、文件变更与越界清单、阻塞原因、用量、时长、进程退出码和清理确认。
- `before.json`、`after.json`：启动前与实现后文件指纹；保留开工时已有脏文件为比较基线，不自动回滚用户内容。
- `verification.json`、`test-*.log` / `verify-*/`：控制端实际测试证据。测试日志属于显式反馈材料，可能包含测试输出；反馈前可审阅。
- `request.json`、`launch.json`：本次任务及启动输入；含任务文本，作为本地任务记录保存，不包含 bridge 自行读取的凭据。

范围检查在 Git 目录覆盖 tracked 和未忽略的 untracked 文件，在非 Git 目录覆盖普通文件和符号链接；排除 `.git` 和桥接状态目录，不跟随符号链接。**Git ignored 文件不在范围覆盖内**，结果会披露 `scope_coverage`。检测属于事后审计，不是写入沙箱；发现越界后保留文件和证据，返回非零退出码。

时长含首事件延迟、执行、测试及总时长；计数含工具开始/错误、权限拒绝和事件数。usage 保留 provider 的数值字段，包括缓存读 token；不能把累计输入 token 直接当作账单金额。当前没有可靠的模型/网络/工具时间拆分，不据此声称总体提速倍数。

`usage_complete` 表示是否收到可用的 provider 总 token 数；被中断的调用可能为 false。工具错误另记录脱敏 `error_code`（如 not_found、permission_denied、invalid_input），不保存错误全文、凭据或内部推理。快照按目录批次并行读取，并以不跟随符号链接的文件描述符访问；每次仍重新计算全部覆盖文件的 SHA256，不使用仅凭修改时间的内容缓存。

| 退出码 | 含义 |
| --- | --- |
| 0 | 执行正常结束；另看 validation_status；status 查询和取消请求也可返回 0 |
| 1 | 执行失败/缺失或无效终态 |
| 2 | 参数/状态错误，或 wait 尚未结束 |
| 3 | 修改范围越界 |
| 4 | 权限阻塞 |
| 5 | 需要补充信息 |
| 6 | 验证失败 |
| 7 | 进程清理未确认 |
| 8 | 显式要求的模型不匹配或无法核验 |
| 124 | 总时限或无事件时限到期 |
| 130 | 已取消 |

## 安装路径与验证

默认使用 `D:\Program Files\ZCode\ZCode.exe` 及其 `resources/glm/zcode.cjs`。可通过 `ZCODE_BRIDGE_EXE`、`ZCODE_BRIDGE_CLI`、`ZCODE_BRIDGE_PROVIDER` 设置对应的 **WSL 路径**。provider 配置只传递给原 CLI，bridge 不解析它。ZCode 更新后应重跑 doctor 和传输验证。

```bash
python3 -m unittest discover -s tests -v
# 真实 Windows 进程传输测试，夹具不调用模型；输出目录必须不存在
python3 tests/windows_smoke.py /mnt/d/your-test-output
```

Windows 程序在某些 Codex 沙箱中会报 vsock 错误，此时需按运行环境规定批准沙箱外执行；工具本身不会绕过外层权限。
