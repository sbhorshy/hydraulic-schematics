# Bridge 超时成本基线（2026-10-14）

研究票：[超时成本基线 #77](https://github.com/sbhorshy/hydraulic-schematics/issues/77)；所属地图：[效率改进 #76](https://github.com/sbhorshy/hydraulic-schematics/issues/76)。

本报告回答超时如何发生、哪些成果能保留，以及现有记录能否支持时间预算决策。保持 high、减少重做、限制总等待是本轮给定约束；本报告不选择新阈值、不修改策略。

## 结论与证据边界

1. 当前 first_delivery 的 300 秒是从 worker 开始计时的固定期限，覆盖预检、模型工作、清理和首次交付检查。到期停止执行循环，随后强制清理所属进程树；它不是一次可以继续原请求的暂停。清理、快照和结果持久化会继续耗时，所以不保证恰好 300 秒返回。[S1:343、378–383、411–421、547–581；S3:109–154]
2. 文件、指纹、已完成的验证材料、session ID 和脱敏事件可以保留。保留成果不等于保留或可恢复模型隐藏推理、流式请求内部状态；bridge 没有这项保证。普通修复通过恢复 session 再发送新消息，零产出恢复则有意新建 session。[S1:449–450、578–581、675–677；S6:471–481；S7:146–160]
3. 初始只读样本为 24 个真实执行结果，**没有一个启用 first_delivery**。两个有效档位为 high 的成功样本，首次观察到文件变化分别为 416.1 秒和 771.9 秒。它们属于此前配置下的任务，不是 300 秒 first_delivery 的直接复现，也不是验收通过时间。[M1、M2；样本定义见下文]
4. 上述样本提示“现有任务范围可能与统一 300 秒期限不相容”，但没有 high/low 对照、同任务重复试验或可靠的模型/工具耗时拆分，不能认定 high 导致超时，不能估计降低档位的收益。
5. 自动零产出恢复只替换 prompt 和显式事实，保留原 contract 的文件范围、tests 和已声明 first_delivery。较短提示不等于较小交付合同，仍可能重复同一预算矛盾。[S6:355–366、470–476]
6. 六个超时样本的 token 用量全部缺失。空 usage 是 unknown，不是零成本，也不足以计算超时浪费比例或节省金额。[M0；S1:673；S9:146–148]

## 调查范围、样本和版本

只读检查本仓库 `tools/zcode-bridge` 源码及已安装工具目录；未发起新 provider 请求，未终止或干预业务任务，未读取模型私有推理。报告不包含任务原文、原始日志、业务文件名、工具参数或业务内容。下列本地相对路径只供已有授权的维护者定位，不将原始运行记录上传。

安装目录记为 `$BRIDGE_INSTALL`。统计来源仅为其 `.runs/*/result.json` 与 `.teams/executions/*/result.json`，并读取对应 request 的配置字段、事件类别和计数；不递归收集工作树、测试 fixture、手工 bugcheck、测试验证子目录或 smoke-result。即使真实运行本身为环境验证，它仍属于实际调用；它不与假 CLI fixture 混算为性能复现。

本报告固定初始样本边界：`finished_at <= 2026-10-14T01:27:04.172791+00:00`，最早 created_at 为 `2026-10-12T12:05:29.343909+00:00`。共 24 个结果，其中 `.runs` 为 3 个、`.teams/executions` 为 21 个。整理报告期间出现的新结果不纳入，避免运行目录继续变化造成样本漂移。采样以本地已有结果为准，不声称覆盖所有状态目录或历史请求。[M0]

源码审查采用本次文件字节及 SHA256 固定版本（表 S）。仓库源码与已安装的所列文件逐字节相同。主工作区 tools 当时尚未纳入其 HEAD，因此不能用研究分支基点提交冒充代码版本；本分支只提交报告，不复制未提交实现。历史结果并未在本次汇总中可靠绑定每次运行的完整源码哈希，因此按**有记录的配置与字段**分组，历史实现版本标为 unknown，不能把当前默认值反填到旧结果。

| 分组 | 样本数 | 配置/版本边界 |
| --- | ---: | --- |
| 当前源码静态行为 | 不适用 | 表 S 固定字节；不是新的运行测试 |
| 真实运行，有有效 high 记录 | 3 | 2 次 requested=high，1 次 requested=inherit/effective=high；均无 first_delivery |
| 真实运行，无有效档位记录 | 21 | 不推断为 low、high 或 inherit；均无 first_delivery |
| first_delivery 实际运行复现 | 0 | 不能给出该机制的实际通过率或超时率 |
| 假 CLI/fixture 性能样本 | 0 | 未运行、不计入真实调用统计 |

## 时间与用量基线

以下总时长取 `timings.total_seconds`，不是模型生成耗时；不以 created_at 到 finished_at 的差替代 worker 指标。[M0；S1:659–664]

| 终态 | 数量 | 总时长最小/中位/最大（秒） | 有 totalTokens 的结果 |
| --- | ---: | --- | ---: |
| completed | 14 | 182.6 / 883.5 / 2533.2 | 14 |
| timed_out | 6 | 606.9 / 609.8 / 3605.6 | 0 |
| cancelled | 3 | 207.6 / 635.9 / 707.7 | 0 |
| blocked_permission | 1 | 183.1 / 183.1 / 183.1 | 0 |

六次超时中，五次为 `no_progress_timeout`，一次为 `total_timeout`；六次均保留 session ID，两次检测到文件变化。没有 first_delivery_timeout 样本。24 个结果的 validation_status 为 1 passed、23 not_run；completed 只说明执行正常结束，不能由此计算“验收通过任务”的时长分布。首次验收通过时间没有可比较的统一基线。[M0]

已知 token 合计仅覆盖 14 个 completed 结果：`totalTokens=42,452,069`，`cacheReadTokens=40,634,752`，记录的 `modelRequestCount` 合计 331。缓存读可能已包含于输入 token，不能再加到 totalTokens 上；这些数字不是费用，更不是可归因的重复浪费。其余 10 个结果用量未知，不能给出全样本成本总额。[M0；S9:146–148]

| 元数据来源 | 有效档位/要求 | 总时限 / 无事件时限 / 无产出硬时限（秒） | 首文件观察（秒） | 总时长（秒） | 结果 |
| --- | --- | --- | ---: | ---: | --- |
| M1 | high / high | 3600 / 600 / null | 771.9 | 1735.1 | completed，4 个变更文件 |
| M2 | high / inherit | 2877.0 / 600 / null | 416.1 | 2188.1 | completed，8 个变更文件；显式续接 |
| M3 | high / high | 1800 / 600 / 600 | 未观察到 | 606.9 | no_progress_timeout，零变更文件 |

三者 first_delivery 均为空。M3 记录 1562 个有效事件、32 次工具开始、零工具错误及权限拒绝；持续活动不等于实质产出。它在约 600 秒无产出时触发终止，最后约 606.9 秒落盘；这一例展示清理额外时间，但不是 first_delivery 的实测。[M3:28、59、计数字段]

M1/M2 的首文件时间是 **execution 阶段开始后的首次观察**；当前 first_delivery deadline 则从更早的 worker 起点计算。二者起点不同，而且文件观察不等于语义正确或测试通过。若把当前 300 秒固定规则施加到完全相同的执行轨迹，期限会早于两者记录的首文件；这只是反事实对照。新提示、阶段拆分或期限约定可能改变轨迹，因此不能声称已证明真实运行一定在 300 秒失败。[S1:343、398–400；S9:72、76；M1、M2]

## 各层期限和清理语义

| 层次 | 当前源码行为 | 依据 |
| --- | --- | --- |
| 总时限 | worker 启动起算；模型循环与控制端测试检查它 | S1:378、422–425、633–650 |
| 无有效事件时限 | 收到合法事件更新 last_activity；没有事件直到到期才触发 | S1:398、422–433 |
| 无实质产出时限 | 与事件活动分开；可选硬时限，默认仅告警；到点停止循环 | S1:371–372、502–504；S9:18 |
| 首次交付期限 | 有范围和 tests 的新写任务默认 180/300；plan 不启用；显式 null 可关闭 | S2:11–19；S9:61–76 |
| 首次交付检查 | 模型 completed 且清理后寻找非空新文件，运行声明的测试子集，核对源码指纹；共用原期限 | S1:589–620；S2:29–58 |
| 单个声明测试 | 有各自 timeout，且受控制端取消/总期限或 first_delivery 期限约束 | S4:113、299–325；S2:45–56 |
| 协议 RPC | 单 RPC 60 秒计时；不能直接理解为整个模型任务只有 60 秒 | S7:46、160–161 |
| Windows 清理 | 按本次启动归属识别进程，taskkill /T /F；清理未确认则保留不安全标记，阻止新写任务 | S3:109–154；S1:557–574 |

180 秒首次交付 warning 只输出控制端事件，不往正在运行的 session/send 插入消息。本报告没有发现“有核验进展自动有限延期”的当前实现；固定 deadline 并不因写文件、测试活动或子代理活动而重置。[S1:343、411–421；S9:72、76]

300 秒到期可能发生于模型请求、工具运行、清理后或测试阶段。执行循环超时没有等待一个公开阶段摘要的宽限步骤；清理用强制终止。清理失败会使终态成为 cleanup_failed，并保留 cwd 禁止重新写入的标记。这些是当前实现语义，不等于本报告建议采用的策略。[S1:418–421、547–567；S3:123–140]

## 成果与恢复成本

| 对象 | 保留/续接事实 | 不能据此承诺的能力 |
| --- | --- | --- |
| 已写文件 | 清理确认后生成 after 指纹和变更清单；不自动回滚 | 文件不一定完整、正确或通过测试；Git ignored 文件不在当前范围审计内 |
| 验证证据 | 已完成验证报告和日志存于任务目录，可作为显式反馈 | 被杀前未完成的测试不是通过；新代码状态需要重新核验 |
| Session ID | 流式安全事件更新并保存；普通修复可以 resume | 不保证被中断请求的全部内部状态已持久化；不恢复隐藏推理 |
| 公开回答 | 正常 terminal result 可保存公开 response | 硬截断可能没有最终回答或完整阶段摘要 |
| 用量 | 正常 terminal usage 可记录；部分子代理记录可标记不完整 | 中断期间的消耗不能从空 usage 推出，provider 端是否停止计费也未验证 |

依据：S1:335–338、437–450、522–543、578–581、665–675；S6:477–481；S7:161–179；S9:137–148。

普通修复继续相同工作树，追加主控 findings；模型匹配时恢复旧 session。它能复用文件、已保留会话和测试事实，但新的调用仍可能输入历史上下文、重新读取文件或复做推导。缓存可以减轻部分重复输入成本，不能把其存在等同于免费或省下全部时间。[S6:334–350、458–481；S7:146–160]

零产出恢复要求：超时、清理确认、changed_files 为空、原因属于 first_delivery_timeout/no_progress_timeout，并且没有此前实现；有明确恢复提示、符合模型与重试预算才自动执行。新 session 最多一次，第二次零产出要求重新规划。该路径只显式继承恢复提示和主控 verified facts，不自动汇总或搬运旧会话调研成果。[S2:23–26；S6:355–366、408–420、471–476]

恢复提示要求非空、最多 4000 字符且不与原文完全相同；实现并不判定语义上的任务确实变小。它复制原 contract 后仅替换 prompt，因此原文件范围、测试集和 first_delivery 条件仍保留。这是“减少重做”的设计需要处理的事实缺口，不应把减少提示长度当成阶段拆分已经完成。[S6:358–361、470–476]

## 支撑后续阈值决策的指标与缺口

当前可直接使用：实际 requested/effective effort、有无 first_delivery 及各层期限、worker 总时长、首有效事件延迟、首次文件观察、事件/工具/错误计数、cleanup_confirmed、文件指纹变化、验证状态及已知 token。它们应以阶段和合同为分组单位，分别报告真实请求与 fixture。[S1:338–350、511–516、659–674；M0]

仍需补齐或另行验证：

- 每次运行的实现哈希、模型/配置快照，以及 prompt/contract 的无内容指纹，才能区分版本变化与任务变化；不需保存私有推理。
- 首个**通过独立行为核验的阶段**的时间与证据指纹；不能由首写时间替代。
- 超时触发、取消发送、provider 停止、进程树确认结束、结果落盘的分段时间；当前总时长不能拆出这些成本。
- 中断请求的 provider 用量、子代理完整用量及其计量边界。没有这些数值时显式 unknown，不能用 0 填补。
- 跨恢复尝试汇总的首次合格交付总等待、重新执行次数、复用文件/验证事实、重复工具调用与已知/未知 token，避免只优化单次 attempt 时长。
- 保持 high 下、相同合同规模与验收条件的可比较样本，及“有核验证据才延期”的前后对照。当前 3 个有效 high 样本不足以估计分位阈值或因果收益。

这些是证据要求，不是本报告选定的实现或新期限。是否延期、何时保存公开阶段成果、何时缩小 contract，应由后续设计票决定。

## 一手来源索引与指纹

### 源码（S）

路径相对主工作区；行号以本次 SHA256 文件为准。所列已安装副本内容相同。源码未随本报告发布，以下是维护者可复核的来源标识，不是指向不存在的提交链接。

| 标识 | 路径 | SHA256 |
| --- | --- | --- |
| S1 | tools/zcode-bridge/bridge.py | ad31c330835301b49e9f6e3c66bfa757ec7785f05167872e2574b48f128c7c78 |
| S2 | tools/zcode-bridge/bridge_delivery.py | 68fcad42cf3390ff72a92d05d3d7a891636820dc12d2c3548b66d5c8b0188b8b |
| S3 | tools/zcode-bridge/bridge_transport.py | 83e93c71d52b317b3b752432bce343009c6850c06c36c3b9330a0a3752bb34b1 |
| S4 | tools/zcode-bridge/bridge_contract.py | 8f00244c7cdd32e53bfa68844f48779834c1fabe88ea699299bb0b54d76023f1 |
| S5 | tools/zcode-bridge/bridge_progress.py | c7d7251128f89e09eb262f1fce5355680ad52b06d9fabb7df554ded93399feeb |
| S6 | tools/zcode-bridge/team.py | 5ac0b888e3b73697d8c9ea81cfd205bb903ded01ee5da8abf4a58c42d4c3f66f |
| S7 | tools/zcode-bridge/protocol.cjs | d42d3faab483597032f7305d2120f44f0743f404b4188d3311253ee69d108833 |
| S8 | tools/zcode-bridge/reasoning.cjs | d5e924f77a34924983550151f42b05cb9715f300df24a825a647af6e7ae6d246 |
| S9 | tools/zcode-bridge/README.md | 7ec763b61994baca98da38ba94df95688f65d4bc473485eb7fce2d594b9f00f6 |

high 的运行时设置由 S8:11–19 调用 session/setThoughtLevel，并以 session/read 的 index profile 回读确认。报告中的有效 high 来自对应结果字段，不从任务文案推断。

### 元数据（M）

M0 为上述冻结边界内 24 个 result 的只读聚合。复核方法：仅枚举 `$BRIDGE_INSTALL/.runs/*/result.json` 与 `$BRIDGE_INSTALL/.teams/executions/*/result.json`，按 finished_at 截止筛选，以 status 分组，对 timings.total_seconds 求 min/median/max；usage.totalTokens 缺失计为 unknown。对应 request 只用于读取 resume、timeout、idle_timeout、progress_timeout 和 contract.first_delivery 等配置，不输出 prompt。

| 标识 | 安装目录内的结果路径 | SHA256 / 关键行 |
| --- | --- | --- |
| M1 | .teams/executions/task-de0b5521bfaa448f87b3fbc911de9b88/result.json | 7ee969020a58f3d67e0fdd7aef59f5d72750ac8a9fa43ca020cb6609e697d801；high :33，首文件 :42，总时长 :86 |
| M2 | .teams/executions/task-e5323fb2117642b49044225de4af0d08/result.json | 2d29dca1e737dd0b013e777ec3447c91fdf2bc5c1715c0cb6ba1909470371ec9；high :37，首文件 :46，总时长 :90 |
| M3 | .teams/executions/task-b48ab84e322e469385061ccd67cad93e/result.json | 93ecccb765ae3969c90c01d3f8755d56d8dbd13ea033afa141a3875465977464；high :19，无首文件 :28，总时长 :59，用量不完整 :72 |

原始结果、请求与事件留在本地，不随研究分支上传。报告只发布脱敏统计与源码依据；没有发布凭据、内部推理、原始提示或业务日志。
