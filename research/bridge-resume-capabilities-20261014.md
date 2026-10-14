# ZCode 取消、续接与上下文缓存的能力边界

研究票：[恢复能力边界：ZCode 取消、续接与上下文缓存能保留什么？](https://github.com/sbhorshy/hydraulic-schematics/issues/78)，地图 [zcode-bridge：减少超时重做与 token 消耗的决策地图](https://github.com/sbhorshy/hydraulic-schematics/issues/76)。读取日期：2026-10-14。方法：当前安装包与 bridge 静态源码、一手官方文档；没有调用模型、读取或导出原始会话、凭据和私有推理。本文描述数据类型及控制语义，不包含会话内容。

**结论：现有 resume 能重建已持久化的会话历史，不能证明能从被截断的模型生成位置继续。当前 bridge 取消采用强制进程树终止；ZCode 内部已有请求停止接口，但尚未由 bridge 接入和验收。上下文缓存减少重复输入处理，不是语义或执行检查点。**

以下“已证实”限于源码或官方文档直接支持；“未知”表示未实测或未找到契约保证；“提议”是后续设计可选项，不替用户选择恢复策略。用户要求的 reasoning effort=high 保持不变；本研究不建议通过降低推理等级换取速度。

## 一、取消与续接分别保留什么

| 操作 | 已证实的行为 | 不能据此保证的内容 |
| --- | --- | --- |
| bridge `cancel` | worker 活跃时写 `cancel.request`；主循环观察后退出执行阶段，最终进入清理。返回 `cancel_requested` 不是已停止。[B1] | 请求返回时已停止写入；所有用量已返回；最后一段会话已落盘 |
| bridge 超时 | 总时限、空闲/无产出等停止条件进入终止与清理路径；Windows 后端使用 `taskkill.exe /T /F`。[B1][B2] | 优雅停止、自动保存完当前工具结果、自动生成交接摘要 |
| bridge `recover` | 与 `cancel` 共用处理函数；失联 worker 的恢复用于确认所属进程清理并解除不安全状态，不会自动恢复模型工作。[B1] | “recover”命令等同恢复会话或继续任务 |
| ZCode `session/stop` | `stopSession` 处理器向活动请求的 AbortController 发取消；若目标 active，尝试改为 paused。另有后台任务取消入口。[Z1] | 工具执行到安全边界才停；请求结束时所有副作用已完成；最后用量完整 |
| 同 session `--resume` | 读取持久 session、消息和 parts，重建历史；恢复已存的文本、推理类型片段、工具结果及相关状态；读取 todo/目标，并按分支/压缩边界选取有效历史。[Z2] | 恢复尚未接收或尚未持久化的输出；恢复服务端隐藏计算状态；完整历史全部仍在活动上下文 |
| 恢复时遇到未完成工具 | 已完成/已出错工具恢复各自结果；其他状态补为 interrupted 的失败结果，并增加中断工具计数。[Z2] | 自动从工具内部上次执行位置继续，或保证重新调用没有重复副作用 |
| 新 session | 创建新的对话上下文，旧工作区已写文件不会因新会话而自动消失；可通过显式输入交接已核验产物。[B1][Z2] | 自动继承旧会话全部决定、失败尝试、待办或运行位置 |

源码中特别值得保留的边界：

- resume 需要可读取的 session store；找不到、已归档或读取异常等情形不能视为可恢复。[Z2]
- 恢复过程有压缩时间线恢复、读取状态重建与计数，也会**丢弃持久的待处理 steer 输入**。因此“上次排队的信息必定会被执行”不成立。[Z2]
- 实际文件状态与会话历史是两类状态。强杀前可能已写文件但未保存工具成功结果；也可能只保存了工具调用意图。恢复前必须查文件摘要/差异，而不能仅根据消息判断是否需要重做。[B1][B2][Z2，综合推断]
- `feedback_request` 已将测试证据绑定 `source_digest`，要求源码未变且有 session，再创建带显式 resume 的后续任务；这是一条“证据与源版本对齐”的现有路径，不是任意中断都能直接走的自动恢复。[B3]

## 二、优雅停止和检查点：有什么、缺什么

**已存在的底层能力。** 安装源码有 `session/stop`、后台任务取消；headless CLI 注册 SIGINT/SIGTERM 等关停处理，先 abort，再在有限清理期限内关闭应用和相关资源。[Z1][Z3] 这说明可以研究“先请求停止、给清理窗口、必要时强杀”的接入，而非断言底层完全没有停止能力。

**当前 bridge 的实际能力。** Windows 清理直接选择本次任务所属进程并 `/T /F`；没有先调用上述 ZCode 协议停止入口、等待安全边界或请求保存摘要的流程。清理确认失败会记录 `cleanup_failed`，维持 cwd 不安全标记以阻止新任务。[B1][B2]

**未知。** 本次未验证 bridge 现有 headless 启动方式能否获得稳定可调用的 `session/stop` 通道、Windows 信号能否可靠到达预期处理器，以及 abort 后最后消息/工具状态落盘、子进程退出、最终 usage 返回的时序。因此不能把“源码存在处理器”升级为“可安全恢复的产品保证”。

**检查点的边界。** 源码包含 session 持久化、compaction 恢复、checkpoint/rewind 事件及工作流 journal 等机制；仅据名称不能把它们当成整个模型请求、所有工具与外部副作用的原子检查点。[Z2][Z4] 本次没有找到 bridge 暴露的“完成当前工具后暂停并确认已持久化”契约，也没有验证停止后工作流节点复用的适用范围。此能力应记为**尚未证明**，不能描述为绝对不存在。

**提议，供后续方案评估。** 软停止须至少给出请求已接受、活动执行已结束、持久状态可读、进程/子进程已退出或受控、用量完整性这几项确认；若有限窗口内无法确认，仍需明确强杀及部分状态。延期只能由可核验新产出触发且受总等待上限约束，不应因为“正在思考”或一般工具活动无限续期。

## 三、历史推理、缓存与计量不能混为一件事

**官方能力。** Z.AI 的 Preserved Thinking 让历史 assistant 推理块进入后续请求；文档要求完整、原序、未经改写的历史 `reasoning_content`，Coding Plan 与普通 API 的默认设置不同。[W1] 这是历史内容作为新请求输入的连续性，不是服务端保留了上一次尚未完成的生成执行位置。

**本地事实。** ZCode 的 `assistantReasoningFromParts` 会读取已存的 reasoning 类型 parts 并附上 provider metadata，供历史重建使用。[Z2] 这证明该类型有恢复路径；没有实测每个 endpoint/模型在中断边界下保存和回传的完整性，也未验证部署实际路由及默认配置。**不得为补全中断状态而要求导出、重写或人工拼接原始私有推理。** 恢复交接可以只包含任务事实、文件/产物版本、验收结果和未决问题。

**官方缓存语义。** Z.AI 缓存为隐式重复内容识别，响应可提供 `usage.prompt_tokens_details.cached_tokens`；格式变化、内容改变和缓存过期会影响命中。文档未给出可依赖的固定缓存寿命或命中 SLA。[W2] 因而同 session resume 不保证命中，新 session 重复相同输入也不等于必然零命中。

**费用边界。** 缓存输入仍收费；定价页分别列普通输入、缓存输入、缓存存储和输出单价。“缓存存储限时免费”不等于缓存读取免费；缓存指南的示例折扣不是所有模型的固定价格。[W2][W3] 本次未核对该安装的计费账户/套餐/路由，不用公开普通 API 价格推算它的实际账单。

若实际提供商的计量定义和价格已确认，可按每次请求估算：

```text
输入未命中 = 输入总量 − 缓存命中量
费用 = 输入未命中 × 普通输入单价
     + 缓存命中量 × 缓存输入单价
     + 输出量 × 输出单价
     + 适用的存储/其他费用
```

不能对已有 `inputTokens` 再加一次 `cacheReadTokens` 当作总输入。ZCode 的兼容适配器将 `prompt_tokens` 作为 total、`cached_tokens` 作为 cacheRead，并计算 noCache 差值。[Z5] 其他路由必须核对自身定义。

| 可观察对象 | 当前证据 | 使用限制 |
| --- | --- | --- |
| provider 返回的 token/缓存量 | CLI/bridge 有 `inputTokens`、`cacheReadTokens` 等字段，bridge 仅保留白名单数值。[B4][Z5] | 返回量不证明每一次中断请求都计入；不可据缺失字段判断零费用 |
| 历史与当前缓存命中 | ZCode 有请求与累计 cache hit 统计类型、恢复时重建累计信息的路径。[Z2][Z5] | 累计命中率不等于下一次命中概率；此统计未作为新的 bridge 对外保证验收 |
| 取消时用量 | bridge 对缺少最终 totalTokens、子代理用量不完整等情形标记 `usage_complete=false`。[B4] | 已知用量只是下界，不应当作可靠余额；服务端是否继续计算/如何结算未知 |
| 会话恢复完整性 | `messageCount`、`partCount`、`appliedMessageCount`、`interruptedToolCount` 等计数可从底层恢复结果观察。[Z2] | 计数不能证明语义完整，更不能证明模型未完成的思考被恢复 |

## 四、支持恢复决策的最小信息

以下是**候选设计输入**，不是当前 bridge 已具备的完整恢复协议：

1. 任务 ID、attempt、session ID、工作区/基线提交、目标/契约版本、明确保持 high 的执行参数。
2. 停止原因与阶段、最后可核验产出时刻、清理确认、已知用量及完整性标志；不要只记“超时”。
3. 当前文件摘要/差异、已接受产物、测试命令与对应源码版本、成功/失败结果及证据路径。
4. 可能尚未完成的工具及外部副作用类别；复核实际状态后再决定重放，避免重复写入或重复发布。
5. 短交接摘要：已确认决定、已尝试且失败的方法、未决问题、下一步验收目标。摘要不用复述私有推理。

同 session 可以减少重新探索，但旧假设也可能与已变更代码冲突；新 session 可以避免陈旧上下文，却需要显式交接。选择应基于上述状态，不能单由 session 是否存在或缓存命中率决定。独立任务才并行，恢复任务不得与尚未确认停止的同工作区写者同时执行。

## 五、证据版本与复核索引

报告基线为 `origin/main` 的 `e9cc0fc4afe406c0c5fed845aaeb86870748ab96`。该提交不包含当前本机 `tools/zcode-bridge`，所以此处用本地路径、函数锚点、行号和 SHA-256 标识被读对象，不伪造仓库永久源码链接。主目录 bridge 两个被读文件与安装副本逐字哈希一致；未提交源码或会话数据库。

| 源文件 | SHA-256 |
| --- | --- |
| `/mnt/d/Program Files/ZCode/resources/glm/zcode.cjs` | `31965ce1d5d4a808ef156784f67996de42ccab335591d2386a61ea8f6f506a54` |
| `tools/zcode-bridge/bridge.py` / 安装副本 | `ad31c330835301b49e9f6e3c66bfa757ec7785f05167872e2574b48f128c7c78` |
| `tools/zcode-bridge/bridge_transport.py` / 安装副本 | `83e93c71d52b317b3b752432bce343009c6850c06c36c3b9330a0a3752bb34b1` |

安装副本目录为 `/mnt/c/Users/24270/zcode-bridge`；主目录为 `/mnt/d/file/comac/组件库`。bundle 包含 `0.16.9` 的资源缓存版本字符串，但本次未独立核验产品发布版本，**以文件哈希锁定源码**。bundle 单行很长，行号之外优先按函数名/事件名定位。

| 编号 | 复核位置 | 支持范围 |
| --- | --- | --- |
| B1 | `bridge.py`：`_worker` 取消/超时检查约 408—425 行及 finally 清理约 547—575 行；`cancel_or_recover` 799 行 | 停止请求、强清理调用、不安全状态与 recover 语义 |
| B2 | `bridge_transport.py`：`WindowsBackend.cleanup` 109 行；`cli_arguments` 中 resume 19 行 | 所属进程识别、`taskkill /T /F`、显式续接参数 |
| B3 | `bridge.py`：`feedback_request` 766 行 | 测试证据与源码摘要绑定，后续任务续接 |
| B4 | `bridge.py`：`USAGE_KEYS` 30 行、结果过滤 192—207 行、用量汇总约 664—674 行 | 脱敏指标及不完整用量处理 |
| Z1 | bundle 15449 行：`stopSession` / `wci`、`pauseActiveGoalForSessionStop` / `rhc`、`cancelBackgroundTask` / `kci` | 底层协议取消与目标暂停 |
| Z2 | bundle 14662 行：`resumeFromStore` / `Ajo`；2224—2229 行：`hydrateMessageHistoryFromSession` / `nve`、`assistantReasoningFromParts` / `bla`；15449 行 `activateSessionForResume` / `DFn` | 持久历史重建、未完成工具标记、分支压缩、pending steer 丢弃与 session 不存在路径 |
| Z3 | bundle 6 行：`registerCliShutdownHandlers` / `iZe`、`runCliCleanupWithTimeout`；15549 行 headless 调用该处理器 | 信号 abort 和有时限的清理；未验证 Windows 实际投递 |
| Z4 | bundle 75 行事件 schema（checkpoint/rewind）；15432 行 workflow journal/resume 路径 | 仅证明存在相关机制，不证明运行原子检查点 |
| Z5 | bundle 2092 行兼容 usage 映射；72—75 行缓存统计 schema；14662 行累计缓存统计重建 | 输入总量与 cacheRead 的区分、计数观察路径 |
| W1 | Z.AI [Thinking Mode](https://docs.z.ai/guides/capabilities/thinking-mode)，Preserved Thinking | 官方历史内容回传条件；页面未标发布日期，读取 2026-10-14 |
| W2 | Z.AI [Context Caching](https://docs.z.ai/guides/capabilities/cache)，Important Notes / Billing Information | 自动缓存、过期、可观察字段与收费；页面未标发布日期，读取 2026-10-14 |
| W3 | Z.AI [Pricing](https://docs.z.ai/guides/overview/pricing) | 区分输入、缓存输入、存储及输出价格；页面未标发布日期，读取 2026-10-14 |

## 六、仍需验证的边界

- 不调用付费 provider 的前提下，本轮只能确认源码路径；无法测出强杀时最后多少内容已落盘、服务端取消是否及时、续接实际命中率及费用。
- 底层停止 API 的 bridge 可达性、软停止后的持久化/进程回收/usage 返回时序，需要专门的接入和故障测试，不能依赖接口名称推断。
- 可先用无模型的假执行器验证“已写文件但未回传结果”“取消后用量未知”“清理失败禁止接管”“重复交接不重复副作用”。真实 endpoint 行为仍需后续单独获授权验证。
- 未证明任何恢复模式可以保留未完成的隐藏计算、自动避免全部重做或保证命中缓存；因此后续恢复预算必须容纳重新推理与状态复核。
