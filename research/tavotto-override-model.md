# Tavotto 架构深拆：override 模式与可借清单

> 研究票：[Tavotto 架构深拆：override 模式与可借清单](https://github.com/sbhorshy/hydraulic-schematics/issues/56) · 地图：[图面编制功能引入](https://github.com/sbhorshy/hydraulic-schematics/issues/54)
> 日期：2026-09-29 · 方法：源码直读（gh api 逐文件取 `Tavotto/Tavotto@HEAD`）+ ADR 直读 + 姊妹票 [编制层技术形态扫描](https://github.com/sbhorshy/hydraulic-schematics/issues/57) 结论衔接
> 姊妹票文档：`research/svg-editing-ecosystem-scan.md`（分支 `research/svg-editing-ecosystem-scan`）

## 0. 结论摘要

1. Tavotto 的核心不是「编辑器」，而是**一份 override 记录模型 + 全量列表语义**：人工编辑以 `{gid, prop, value, identity?}` 存档，**永远不碰脚本**；重放、undo、烙基线全是这一个模型的推论。该模型与本仓「intent=语义源 / layout=视觉层」分层天然同构，**可整体平移**。
2. 对本仓最有价值的五条工程纪律：**编辑器不重实现渲染**（一切视觉变化走服务端重渲染）、**全量列表语义=免费 undo**、**单一闸门判据双端共用**（MCP 与导出对话框同一把尺）、**写回语义真源=仅限用户亲手发起的事务**（自动路径结构性禁入）、**烙基线**解决「上游会变 × 手调要留」的矛盾。
3. 姊妹票两处初判需修正/细化：MCP 工具面实为 **11 个**（README 口径 9 个）；「预检规则单源 JSON 双端共享」精确说是**规则数据单源 JSON（`profiles/publication.json`）+ 判定引擎 Python 单实现 + TS 侧仅实时性子集**，并非两套完整引擎。

---

## 1. override 数据模型拆解

### 1.1 记录形与全量列表语义（`src/tavotto/engine/overrides.py`，4122 行）

模块 docstring 原文（翻译要点）：

- 文档每次发来**全量** override 列表 `[{gid, prop, value}…]`；
- worker 维护每张图两张表：`applied {(gid,prop): 请求值}` 与 `originals {(gid,prop): 原生值}`（`FigState`，L105–156）；
- **新列表缺少上次已应用的 (gid,prop) → 用 originals 恢复原值**——这就是 undo：没有独立的 undo 栈，撤销=从列表里删条目；
- 首次修改某 (gid,prop) 时先记录原值。

推论（工程含义）：前端**无状态**（不记「应用了什么」，只持当前全集）；重放幂等；冲突策略=后写赢（列表顺序无关，全集即状态）。

### 1.2 gid：位置式稳定寻址（`engine/manifest.py`）

- `instrument(state)`：build 后走一次 Figure artist 树，**按确定性树序**赋 gid（`axes_0.title` / `axes_0.lines_j` / `fig.texts_0`…），登记进 `FigState.index`；
- `build_manifest(state)`：每次渲染后读元素当前属性值与 bbox（**figure 分数坐标、y 轴向下 top-origin**），产出发给前端的 manifest——前端拿到的是「有什么可编辑 + 现值 + 包围盒」，不做任何对象发现；
- 坐标约定单点转换：前端一律说 figure 分数坐标，worker 在 overrides.py 内换成各 artist 自己的坐标系。**协议里只有一种坐标语言，转换只在一处做。**

### 1.3 ADR 0083《override 的目标身份》——位置式 gid 的翻车与最小修补（2026-09-25 Accepted）

事故（QA SCI-03-B1，高）：用户把曲线 alpha 改成洋红 → 之后脚本里重排/插入/删除曲线 → 同一 gid 指向另一条曲线 → 旧 override **静默落到错误对象**且 warnings 为空；更糟的是「写回的一次性重放」与「几何/像素门比对」用的是同一把位置尺，两边错得一模一样也放行。4/4 变体复现。

裁决（值得整条抄走的取舍）：

- **不建对象身份系统**，gid 仍是唯一寻址；只给每条 patch 加可选 `identity` 字段=「写这条编辑那一刻，该 gid 的目标身份」；
- 重放时与 gid **此刻**指向对象的身份比对：对上→应用；对不上→**该 patch 当作不在列表里**（已应用的照常还原），报 warning「编辑的对象已找不到（脚本结构可能已改动，未应用）」；
- 旧文档不带 identity → 按位置匹配（向后兼容）；带了但为空/非法 → **同样不应用，不许退回位置匹配**；
- 会话快照同步携带身份（`applied_identity`），native 屏障 rebase 按「身份+值」重放。

### 1.4 烙基线（baked baseline，`engine/bakedbaseline.py`）——上游会变 × 手调要留的解法

- 「更新原图」（脚本重跑出新图）时，把累积 override **烙进文件**作为新基线；
- 数据形状：`{stem: {"versions": [{"ts", "patches", "patch_hash"?, "files"?}…]}}`，末位=当前基线；历史两种旧形状只在读取端兼容；
- 模块纪律：纯标准库、不知道 Flask/项目概念，根目录与注册表由调用方显式递入；`app.py` 的 `load_baked`/`append_baked` 只是薄包装。

### 1.5 落盘纪律（ADR 0023《文档落盘权威》2026-08-29 Accepted）

- 起点状态有**九份各自手写的原子写**，行为互不一致（「另存为」甚至无 tmp 直接盖写）→ 收敛为 `engine/atomicio.py` **唯一实现**：tmp（同目录）→ flush → fsync 文件 → `os.replace` → fsync 目录 → 失败清 tmp；
- NaN/Infinity 在**序列化那一步**拒绝（`allow_nan=False`），读回再闸一道 `non_finite_on_disk`；
- schema 判据一份（`engine/documents.py`），更高版本 → `schema_too_new` 不「尽力打开」；**前端同一套判据在 `web/src/types/document.ts` + `web/src/lib/migrate.ts`——新增 schema 版本必须两侧同改**；
- 修订号=内容 hash，不掺 mtime。

### 1.6 ADR 0094《脚本写回》（2026-09-26 Proposed）——「永远不改用户脚本」的例外怎样设计

原则：为兼容/让图画出来而**未经用户要求**绝不碰脚本；写回脚本是**另一类动作**——用户亲手发起、看过逐行 diff、显式确认的**导出**，输出目标恰好是脚本文件。

结构性判据（每条都是实现里的门，不是文案）：

- 唯一入口：桌面/本地浏览器里用户点「写回脚本…」→ 预览 → 勾选确认 → 「修改脚本」；**样式跟随、规范修图、AI 刷新、MCP/Codex 插件、`tavotto run`、启动迁移一律不得调用提交端点**；
- 写前双备份，写后一键恢复；写进去的是**带明显标记、整段删除即恢复原样**的代码块（不是散落全文的修改）；
- 写回事务用**像素门**验证（ADR 0049 写回像素验证：verify 比对「热态 vs 重放」，不过一个字不改——先例 ADR 0080 规范修图事务）。

### 1.7 文档与排版的存放（ADR 0096《⌘S 保存到项目》+ ADR 0094 §一）

- 画布文档=`tavottofile/*.json`（schema 3），每面板一份 `overrides` 列表；布局版本在 `tavottofile/versions/`；烙基线在 `<data_dir>/…/baked_overrides/<项目id>.json`；
- 排版可「绑定」项目内文件：绑定关系 `{projectId, name, file, revision, dirty}` 存**本机 localStorage**、**不进文档**（文档跟 git 走到别的电脑，不该带着这台机器的绑定）。

---

## 2. 三端架构与协议

| 端 | 载体 | 与内核关系 |
|---|---|---|
| Python 引擎（worker 子进程） | `src/tavotto/engine/`（Flask 父进程 + worker 协议 v1，ADR 0003/0004） | **唯一渲染权威**：build、instrument、build_manifest、apply overrides、导出全在这 |
| Web/桌面前端 | `web/`（TS）+ Tauri 壳（ADR 0002，`src-tauri/`） | 只做交互与呈现；一切视觉变化=发全量 override 列表 → worker 重渲染 → 新 manifest 回来。**前端从不自己算图**（拖拽性能另设 probe，ADR 0075/0077） |
| MCP / Codex 插件 | `codex-plugin/mcp/tavotto_mcp/`（stdio server，ADR 0005/0006） | 与前端共用同一 worker 与同一 preflight 判据（`summarize()`）；UI_TOOLS 两个工具直接驱动桌面窗口 |

交接协议：`tavotto open`（`tavotto_open_figure`）把图递到桌面窗口，agent 与人看同一份会话状态（`session_state`）；`tavotto run`（ADR 0021/0099）包装用户现有 python 命令、附加到进程内新建的 figure，屏障离开时存快照、下个屏障按「身份+值」rebase（ADR 0083 的会话快照语义）。

---

## 3. preflight 分级实现（`engine/preflight.py`，1091 行）

- 入口 `run(spec, profile) -> list[issue]`；`summarize(issues)` 按等级分桶计数，**blocking = 存在任一 error**；docstring 明言「MCP 与导出对话框都用它做『能不能导出』的判据」——**同一把尺两处用，判据不双轨**。
- 四级：`error / warn / not_verifiable / suggestion`（`profiles_mod.SEVERITIES`）；每条检查的等级不是硬编码，而是 `severity_of(profile, check_id)` **按出版配置逐条映射**（同一检查在不同出版档位下可以是不同等级）。
- 检查面：页面（`_check_page`）、面板状态、栅格（dpi）、**字体（glyph 覆盖率实测 `_canvas_coverage`，含 CJK 回退链）**、坐标轴、几何重叠（`_check_geometry` 面板矩形相交）、文字溢出（`element_overflow`）、裁剪、缺 manifest。
- 规则数据单源：`src/tavotto/profiles/publication.json`（出版档位=数据）；判定引擎 Python 一份；`web/src/lib/preflight.ts` 存在但只承担编辑器内**实时反馈子集**——不是两套完整引擎。
- 「suggestion」级自带免责设计：如拟合线判定只凭标签特征，注释写明「判错也不阻断」。

## 4. MCP 工具面全清单（`codex-plugin/mcp/tavotto_mcp/server.py`，1702 行）

11 个工具（README 口径 9 个，实数以此为准）：

| 工具 | 语义 |
|---|---|
| `tavotto_open_figure` | 把图递到桌面窗口（UI 直连） |
| `tavotto_apply_overrides` | 应用 override 集（UI 直连；全量列表语义） |
| `tavotto_normalize_figure` | 规范化点属性修改（agent 的「小步改」入口） |
| `tavotto_preflight` | 跑预检，返回 `summarize()` 分级结果 |
| `tavotto_verify_replay` | 重放核验：比对热态 vs 重放（写回事务的 verify 段同一把尺） |
| `tavotto_export` | 导出（被 blocking 判据扣留） |
| `tavotto_session_state` / `tavotto_close_session` / `tavotto_health` / `tavotto_refresh_project` / `tavotto_managed` | 会话与工程管理 |

agent 桥纪律（ADR 0094 + `docs/rules/backend/ai-agent-bridge.md`）：修改前快照、只回滚这一版、之后又变过就 409——**agent 永远拿不到绕过闸门的写路径**。

---

## 5. 可借清单与平移映射（→ 本仓「SVG + layout.json + 7 道闸门」）

| # | Tavotto 模式 | 本仓对应 | 借法 | 喂哪张票 |
|---|---|---|---|---|
| 1 | override 记录 `{gid, prop, value, identity?}` | layout 层元素（nodes/labels/lanes/legend/title_block 的坐标与文本字段） | 手调=记录流，写回目标二选一（直改 layout vs 叠加文件）交给 [手调改动写回层定案] | #58 |
| 2 | **全量列表语义**（缺键=还原） | 叠加文件（若选 b 方案）同语义：`layout.overrides.json` 每次全量下发 | undo 免费获得；重放幂等；编辑器无状态 | #58 |
| 3 | 烙基线 `{versions:[{ts,patches,patch_hash}]}` | 重渲染/引擎升级后，手调基线重烙 + `patch_hash` 校验 | 解决「引擎规则式解会变 × 手调要保留」；与 catalog `draft_not_frozen` 钉号披露口径兼容（烙基线=显式接受新钉号的一次签认动作） | #58 |
| 4 | ADR 0083 身份核对 | 本仓 node id 是**语义稳定 id**（ACC-001…），主体无此问题；但 labels/lanes 等派生元素若按位置索引须补稳定键或 identity | 平移时把「元素清单」分级：语义 id 元素免核，位置式元素强制 identity | #58 |
| 5 | **编辑器不重实现渲染**（前端只发 delta，worker 重渲染回 manifest） | 编辑器只提交坐标/文本 delta → 服务端重跑 `render_l0_sheet.py` → 新 SVG + 新 manifest 回前端 | 架构铁律：不把渲染规则（线型推导/标签避让）复刻进 TS，杜绝双实现漂移——姊妹票「自研轻量静态页」形态由此成立且成本可控 | #57/#60 |
| 6 | preflight 单一判据双端共用（`summarize`） | validate_sheet 的 V/B 检查在**编辑器侧栏与导出链用同一实现**（编辑器侧栏=调 validate 的子集端口，不重写检查） | 防「编辑器看着绿、导出链红」的双轨漂移 | #59 |
| 7 | 出版档位=数据（`publication.json`）+ 逐条 `severity_of(profile, check_id)` | B1–B7/V1–V19 严重度映射成数据，concept 档=一份 profile 文件 | 未来调预算不用改检查代码 | #59 |
| 8 | 0094 写回事务边界（唯一入口/双备份/标记块/像素门/自动路径结构性禁入） | **编辑器永不写 intent**；若未来要「把布局经验落回 intent」另立用户亲手发起的导出事务 | 直接抄进防旁路口径：MCP/自动链只拿 apply+preflight，拿不到绕闸写路径 | #59 |
| 9 | `atomicio` 唯一落盘权威 + 内容 hash 修订号 | layout 写回只有一份写盘实现；`revision_log`/`title_block` 手调计数用内容 hash | 落盘纪律 | #58/#59 |
| 10 | MCP 工具面（apply/normalize/preflight/verify_replay/export） | agent 交互环（若入范围）按此四件套设计：改（apply/normalize）→ 查（preflight）→ 验（verify_replay=重渲染后 diff）→ 出（export 过全闸门） | ZCode+skill 已是 agent 侧载体，工具面收敛为 skill 参数即可 | 范围票 #55 的 d 档 |
| 11 | 坐标语言单点转换（前端只说一种坐标） | 编辑器与 layout 契约间只说「layout 用户坐标」，80×80 基准/EDGE_MARGIN 换算只做一次 | 渲染端契约已要求不硬编码端口坐标，编辑器沿用同纪律 | #60 |

## 6. 不可借清单

| 部分 | 为什么不可借 |
|---|---|
| artist 桥全家（`manifest.py` instrument、`axestraversal/tickmodel/legendmodel/pathgeom/spinemodel/colorbarmodel`、worker 协议的 artist 语义） | 深绑 matplotlib artist 树；本仓视觉权威是自渲染 SVG，无 artist 可遍历 |
| Tauri 桌面壳（`src-tauri/`、ADR 0002/0076） | 本仓无桌面分发需求；web 静态页 + 本地起服务已覆盖（姊妹票甲形态） |
| 文档 schema 3 多画布/排版模型（ADR 0001） | 服务「页面编排拼版」档；该档未入推荐范围 |
| AI assistant 改脚本链（`ai_agents/ai_bridge/ai_providers/ai_history`） | 本仓 agent 侧就是 ZCode + hydraulic-schematic skill，不必自建 agent 运行时 |
| **任何源码级复用** | AGPL-3.0 传染；本票产出只到「模式与纪律」层，实现零拷贝（地图 Out of scope 已封） |

## 7. 对姊妹票初判的坐实与修正

- ✅ 坐实：override 叠加模式（1.1/1.4）、verify_replay 与写回闸门同尺（1.6/§4）、preflight 分级与扣留导出（§3）、「两路（GUI/MCP）共用同一写回层」——Tavotto 的前端与 MCP 确实共用同一 worker 与同一 preflight 判据。
- ✏️ 修正 1：MCP 工具面 **11 个**（README 宣传 9 个）。
- ✏️ 修正 2：「预检规则单源 JSON 双端共享」应精确为：**规则数据**单源 JSON + 判定引擎 Python 单实现 + TS 侧仅实时反馈子集。对 #59 的启示反而更强：本仓应做到「连实时子集都不另写第二份实现，直接调 validate 的 Python 入口」。
- ✏️ 修正 3（事实澄清，姊妹票同款）：本票不涉及成品 SVG 寻址；Tavotto 的可寻址性建在渲染时 instrument 出的 manifest 上——对本仓的对应物是「渲染器顺手产出元素清单（id/bbox/现值）」，渲染器已具备该信息，缺的只是导出成 manifest 供编辑器消费。

## 8. 风险与开放问题

1. **重渲染回路延迟**：Tavotto 用同一进程内 worker 换取秒级反馈；本仓走 `render_l0_sheet.py` 子进程重渲染，1# 图实测全链 72.9s（skill 链）中渲染仅一部分，但拖拽中的**连续反馈**不能每次全链重跑——需要「编辑器本地近似预览 + 松手/落盘时服务端真渲染」的两级反馈设计（Tavotto ADR 0022 复杂度感知预览同款问题）。→ #60 原型要实测。
2. **叠加层 vs 直改 layout 的取舍证据**：Tavotto 的叠加层成立的隐含前提是「上游产物会重算」（脚本重跑）。本仓 layout 本就是人工维护的显式坐标层（无「自动重算」语义，§13 R1 规则式解发生在引擎内部），直改 layout 的论据比 Tavotto 场景强；烙基线机制只在「引擎升级重出图」时有价值。→ #58 据此权衡。
3. **AGPL 邻接**：若未来编制层 web 页开源且与 Tavotto 代码同库分发，注意许可边界；当前「只借模式」立场无风险。
4. `tavotto run` 的进程附加/屏障 rebase 模式对本仓无对应场景（本仓不「附加」用户进程），仅作背景。

## 9. 证据索引

- 源码（`Tavotto/Tavotto@HEAD`，经 gh api 直取）：
  - `src/tavotto/engine/overrides.py`（4122 行；模块 docstring 全量列表语义、`FigState` L105–156、文本/箭头/刻度各 prop 处理器）
  - `src/tavotto/engine/manifest.py`（instrument/build_manifest docstring）
  - `src/tavotto/engine/preflight.py`（1091 行；`summarize` L1044、`severity_of` 调用 L173）
  - `src/tavotto/engine/bakedbaseline.py` / `originalspec.py` / `documents.py`（模块 docstring）
  - `src/tavotto/profiles/publication.json` + `web/src/lib/preflight.ts`（规则数据单源/双端分工）
  - `codex-plugin/mcp/tavotto_mcp/server.py`（1702 行；`UI_TOOLS` L1302、11 工具名）
- ADR（`docs/adr/`）：0002/0003/0005/0006/0021/0022/0023/0028/0049/0080/0083/0094/0096（正文已读：0023/0083/0094/0096）
- 上游定位（README/产品口径）：属性级编辑、不创建新内容；研究性注释元素（research furniture）为唯一可新增物。
