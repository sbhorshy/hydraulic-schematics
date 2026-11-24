# #113 出图前门禁挡住的缺陷样本如何进入受控回读证据链？

一次性研究分支 `research/issue113-preflight-evidence`，基于 `391200a`（当前 HEAD/main）。**不合并、不开 PR、不改 main、不改/关/评论 GitHub issue、不改 assignee**。本分支只放研究文档与小型探针；生成物在被忽略的 `.artifacts/issue113/`。

## 0. 三问的有限答案

1. **不改官方校核链的实验路径**：允许「受控 post-render 注入入口」（A）、「不触发硬门禁的合法目标位搜索」（B）、「明确的出图前阻断披露」（D）；**不允许**把「按新 intent 临时登记跳线」（C）当作不改链路径。C 只能作为一次性分支上**显式声明改过登记表**的旁证实验，不能充当官方链仲裁，也不能进 main。判据四条与禁用清单见 §2；「接住」判据见 §4。
2. **V17 吸油语义的出图前阻断归 `agent`（文字诊断交接），不归 `disclose`、不归 `recheck`**；阻断事实本身必须随附披露（rc、ValueError 端点表、无 SVG），但披露是附加元数据，不改变 `agent` 档。#110 的「V17 标记几何 = local、语义变异 = agent」原样保留，不静默反转。改档条件见 §3.2。
3. **需要一次性分支上的 harness**；由做实验的 agent/工程师维护并随 HEAD 刷新，工单 owner 复核「接住」；官方脚本与生产登记表由官方链维护者管，任何改生产登记的提案另立决策。建议把 #107（route 交接由谁接）作为下一步毕业票；见 §5。

## 1. 已核对的来源与事实（proven）

### 1.1 工单原文（primary source）

| 来源 | 与本票直接相关的原文要点 |
|---|---|
| [#113](https://github.com/sbhorshy/hydraulic-schematics/issues/113) 正文 | 三条例外：V2 仅能渲染后手改 SVG（9 组布局探针 7 组被硬路由门禁挡住）；V17 吸油语义在 `render_l0_sheet.py:204-205` 抛 `ValueError`、出图前无 SVG；V8/V20 的 intent 改动使 byte-bound bridge registration 失效并带出 V19。要求决定四条路径、四门槛、V17 分档、harness/接住。 |
| [#98](https://github.com/sbhorshy/hydraulic-schematics/issues/98) Notes | 「对照实验使用相同输入、种子与运行环境，沿用现有几何规则判断图面效果」；决策以实测和样图对照为准。 |
| [#102 决议三](https://github.com/sbhorshy/hydraulic-schematics/issues/102#issuecomment-7108887937) | 四门槛原文：「目标对象 / 锚点稳定、偏差可度量、范围能被 `sheet_diff._scope` 接受、成败由官方链判定」。档定义：`local`=结构化定向邻域、`route`=带范围 `action=inspect`（`requires_diagnosis=true`、`executable=false`）、`agent`=只有文字、`disclose`=输入事实/同状态/低信号提示、`recheck`=V4/V14 证据不完整导致的未校核；「未入样的缺陷一律交 agent」；失败优先、不随状态漂移。 |
| [#110 决议](https://github.com/sbhorshy/hydraulic-schematics/issues/110#issuecomment-7120281879) | V17 只有「斜杠组 4 根 vs 5 根」可渲染样本归 local；**「吸油语义变异仍交 agent：出图前抛 `ValueError`、无 SVG」**。V8/V20 伴生 V19 来自 intent 重 dump 后 byte-bound 登记失效，是注入副作用；本批无 disclose/recheck，V4/V14 `not_checked` 伴生行才属 recheck。门禁三例外另立本票。 |

### 1.2 规范源代码事实（行号对应 391200a）

- 预检在布局之前强制：`render_l0_sheet.py:1408-1416` 调 `preflight.preflight(...)`，`not rep['ok']` 即 emit 并 `sys.exit(1)`；`1432` 才构造 `Sheet`。
- V17 语义阻断：`render_l0_sheet.py:198-205`，`infer_suction_network(intent, catalog)` 的 `errors` 直接 `raise ValueError`；发生在 `s.place()`/`s.wire()` 与任何 SVG 写出（`1566-1574`）之前。
- 硬路由门禁：`render_l0_sheet.py:522-556` 先穷举候选，失败后 `RO.escape_point`/`edge_lanes`/角点兜底（`540-554`），仍无解才 `raise RO.failure(anchor, rejected)`；`1448-1456` 捕获 `RoutingError`，删除旧 PNG/回读/浏览器证据，写 `routing-error.json`，`SystemExit`，SVG 不会写出。它是「不画出非法线」的门禁，不是评分折中。
- 跳转桥登记：`bridge_allowance.py:38-49` 生产表按 intent 字节 SHA-256 绑定；`83-119` `resolve_policy(..., registry=None)` 的 `registry=` 明确标注仅供测试；`122-147` **生产入口 `check_bridge_policy(layout, intent_path)` 无 registry 参数**，禁止布局自带数字预算键，hash 不符 fail-closed。`validate_sheet.py:618-623` 捕获 `ValueError` 后置 `allowance=0`，`659-662` 出 V19 fail，绝不静默按 0 通过。`validation.md:238-248` 记载 #23 放行范围只到「登记预算 N 处经验证跳线」，桥画法仍由 V4/V14 判定。
- 官方链与差分前提：`validation.md:5-11, 51-60, 326-367`；`sheet_diff` scope 合法只证明标识合法，compare 仍受 PNG/浏览器/字体/交付状态约束。

### 1.3 本分支探针的实测（`evidence/probe-paths.json`）

脚本 `research/issue113/probe_paths.py` 只复制 1# 输入到忽略目录，调用未改动的规范源脚本；记录 Python 3.10.12、HEAD、四个脚本 SHA-256。

| 探针 | 官方链结果 | 判读 |
|---|---|---|
| `post-render-v2` | render 0 → 手改最终 SVG（横段穿 PRV-001）→ rasterize 0 → validate 1；fail = V2/V3/V14/V19；V2 原文「管线穿越 PF-001 本体 99.80 单位，段 (690.0,320.0)->(1400.0,320.0)」 | 后两环确实由官方链仲裁；伴生 fail 可逐条分辨。注入产物不是官方渲染器画出的。 |
| `gate-pass-acc`（ACC-001 `y` 840→780） | render 0、SVG 写出、rasterize 0、validate 1；唯一 fail：V19「交叉 3 处超出放行预算 1」 | 过门禁 ≠ 得到 V2；得到的是交叉预算伴生问题。 |
| `gate-pass-prv`（PRV-002 `y` 730→790） | render 0、SVG 写出、validate 0（fail 0） | 过门禁且合法，正好说明目标缺陷未复现。 |
| `v17-semantics` | `paths.append([TANK-001.suction_out, USER-001.pressure_in])` → render rc=1、`ValueError: … Suction network reaches an incompatible nontransparent terminal …`；`svg_written=false`、`routing-error.json=false` | 不是路由门禁，是更早的语义门禁；没有报告、PNG、几何可判。 |
| `bridge-binding` | 基线 fail 0；仅给 intent 追加注释使 SHA `8acc1abe…` → `2ee8f4be…`；validate rc=1、V19「跳线登记已失效…fail-closed」 | 字节绑定是 fail-closed；临时登记只能改生产登记内容，属于改链。 |
| `registry_seam` | `check_bridge_policy_signature=(layout, intent_path)`、`resolve_policy_signature=(policy_id, intent_sha256, registry=None)`、生产 id 仅 `current-1-verified-single-bridge-20261012` | 测试接缝不能从生产入口注入。 |

与 #110 的 `evidence/route-gate-probe.json`（7/9 blocked）、`evidence/v17-semantics-blocked.json`、`evidence/scope-check.json`（九 scope accepted）一致；那些证据来自 `research/issue110-unseen-defects@b77e770`，本分支不合并。

## 2. 四条路径的逐项证据与裁决

四门槛简写：①同一输入/种子/环境 ②目标稳定、偏差可度量 ③`sheet_diff._scope` 接受 ④官方链判定。

| 路径 | 支持证据 | 反对证据 / 限制 | 门槛 | 裁决 |
|---|---|---|---|---|
| **A 受控 post-render 注入入口** | 本分支 `post-render-v2`：输入字节与脚本 SHA 固定；官方 rasterize+validate 给出 V2 量化 fail；#110 九案均过门槛、九 scope accepted | 最终 SVG 由人工/脚本注入，不是官方渲染器产物；V2 案带 V3/V14/V19；A 无法构造语义阻断的「图面证据」 | ②③④成立；①对「注入变量之外」成立（基线同源）。必须声明注入前后几何 | **允许**，条件是注入清单 + 官方链后两环仲裁 + 伴生 fail 归因；不得称为官方渲染输出 |
| **B 不触发硬门禁的合法目标位** | 两个探针 render 0 且出图；#110 探针中另外两例也过门禁；完全不改脚本 | 本分支两例一个只出 V19 交叉预算、一个 fail 0；7/9 扰动被 `RO.failure` 挡住；合法路由器按设计不画穿体线，#99「输入侧无可渲染 V2 样本」仍成立 | ①成立；②③对所得缺陷成立；④只判实际得到的缺陷，**不判被门禁挡住的目标** | **允许做搜索**，但不能替代 V2/V17 样本；找到新目标须重新过四门槛 |
| **C 按新 intent 临时登记跳线** | `resolve_policy` 有测试 registry 接缝；理论上可给新 intent 重新登记 allowance=1 | 生产入口无 registry 参数；生产表是官方链一部分，改表/猴补丁即改链；byte 绑定 fail-closed 是设计意图；放行只授权经验证跳线数，不授权路由门禁或语义门禁；会吞掉 V19 伴生证据；对 V17 无效 | ④不成立（链已改）；①的输入一致性也被重新登记破坏 | **禁止作为「不改链」路径**；仅允许在一次性分支显式登记、标注「改过登记表、非官方链仲裁」，不得进 main、不得据此消除 V19 |
| **D 明确「出图前阻断」披露** | V17 probe 有 rc/stderr/无 SVG；#102 中 disclose 覆盖「输入事实」；记录无需改链 | 没有 validation-report、没有几何/PNG/拓扑覆盖；无法判目标 fail；scope 无从生成；不能把阻断当成已回读 | ①②③不成立，④不成立 | **允许且必须作为附加披露**，但不能单独构成回读证据或改变分档 |

### 2.1 四门槛的可执行判据

1. **同一输入/种子/环境**：保留 1# intent/layout/catalog/符号的原始字节 SHA-256；intent 侧实验须提交精确 diff，并与同环境重跑的基线对照；记录官方脚本 SHA-256、Python、Chrome/字体版本。不能把「重 dump 后旧哈希」当成同一输入。
2. **官方链仲裁**：`render_l0_sheet.py → rasterize_sheet.py → validate_sheet.py` 原样调用；保存三条命令 rc、stdout/stderr、`validation-report.json` 的 `fail_count`/逐项 `detail`/`topology.coverage_status`/`geometry.issues`/`delivery`。目标 fail 必须来自报告，不由实验者手写结论。
3. **伴生 fail 可分辨**：每个注入带 before/after 几何或字节 diff；与基线按 check ID + detail 对比，逐条标注目标 / 伴生 / 未校核。已实测伴生：V2 案 V3/V14/V19；ACC 过门禁案交叉预算 V19；intent 改动案 byte-bound V19。两类 V19 不可混为一条。
4. **不静默绕过 preflight 语义**：`preflight`、contract/mirror、路由门禁、吸油语义 ValueError、桥登记 fail-closed 全部保持启用；post-render 注入显式披露「该 SVG 不是官方渲染器产物」，不得删除 `routing-error.json` 或回读证据来伪装成功；scope accepted 不冒充 diff compare 通过或 `delivery.ready`。

**禁止**：改生产脚本/门禁/登记表以换绿；把测试 registry 接缝接到生产入口；手写 SVG 后声称官方链判了语义；删除或压制伴生 fail；把 pre-render 阻断改标 disclose/recheck/local 以逃避 agent 交接；把本分支并入 main。

## 3. V17 出图前阻断的分档

### 3.1 当前档：agent + 强制披露

- `agent`：#102 定义「只有文字」，且「未入样的缺陷一律交 agent」；#110 明确 V17 **语义变异仍交 agent**。本票不推翻。交接物须带完整 `ValueError` 端点表、被追加的 path、rc=1、`svg_written=false`、`routing_error_written=false`、脚本 SHA 与复现命令；由接收 agent 做规则/输入诊断，不给自动 scope。
- 随附 `disclose`：仅描述「输入事实」——例如「该 intent 声明了吸油到非透明压力端的连接；官方渲染器在出图前拒绝，故无图可回读」。它说明为什么没有证据，不声称缺陷已判定或不需修。
- 不是 `recheck`：`recheck` 专指已有官方报告中 V4/V14 证据不完整导致的 `not_checked`（#110 也这么说）。V17 阻断发生在报告生成之前，没有 V4/V14 行可恢复。
- 不是 `local`：四门槛的④失败——官方链没有对目标给出 fail；`render_l0_sheet.py:204-205` 的 ValueError 不是验证报告判定。
- 不改变 #110 已回填的 V17 标记几何 local 档；两者是不同样本、不同缺陷。

### 3.2 改档的精确条件（必须全部满足，且需新决策）

1. 同一语义冲突有**官方未改脚本可渲染**的样本：render 0 且 SVG/PNG/报告齐备；或官方链新增了明确定义的「语义阻断诊断输出」，且该输出由官方脚本生成、纳入版本绑定。
2. 该样本过 #102 四门槛，目标 V17 fail 可度量，伴生 fail 可分辨；`sheet_diff` 前提满足后才谈差分。
3. 有明确授权的决策评论/工单**显式 supersede #110 的 V17 语义例外**；实验本身不自动改档。
4. 若只是出现 V4/V14 `not_checked` 伴生行，则**那一行**按 `recheck`；若调查证明该声明本就是输入事实、不需修，才按 `disclose`。两者都不改目标语义缺陷的 `agent` 档。

## 4. 一次性分支 harness 与「接住」

### 4.1 是否需要与谁维护

需要。理由：#110 的样本生成已有一次性 harness，但三条例外没有统一入口；复跑需要固定脚本版本、产物哈希和伴生归因，散落在聊天里不可复现。**维护者 = 提出/运行实验的 agent 或工程师**，在一次性分支上随 HEAD 刷新；**接收/复核者 = 工单 owner（sbhorshy）或下一张认领的 agent**。官方 skill 脚本与 `bridge_allowance.py` 生产登记表的维护者不属于本实验；任何改生产表的提案须单独决策。本票不把 #107 未定的 route 执行者问题顺手定掉。

### 4.2 建议文件布局（本分支只实现了探针；其余是规格草案）

```
research/issue113/
  README.md                 # 本文件：决策、证据指针
  probe_paths.py            # 只读可行性探针（已实现）
  evidence/probe-paths.json # 探针输出（已实现）
  injections/<case>/edit.json   # 草案：注入清单
  registry/<policy-id>.json     # 草案：仅改链旁证实验，标 non-official
```
`edit.json` 草案字段：`case_id`、`base_input_sha256`、`scope`、`edit_kind=post-render-svg|layout|intent`、`before/after`、`target_check`、`expected_companions`、`commands`、`script_sha256`。

### 4.3 命令

```bash
# 工作树（不要动当前 checkout）
git -C /root/orca/workspaces/组件库/v2-v7-v8 \
  worktree add -b research/issue113-preflight-evidence .scratch/issue113/wt HEAD
cd /root/orca/workspaces/组件库/v2-v7-v8/.scratch/issue113/wt

python3 research/issue113/probe_paths.py        # 重跑全部五个小探针
# 单案官方链（workdir 是复制出的沙箱，不是 1#系统原理图/ 源目录）
python3 .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py <workdir>
python3 .agents/skills/hydraulic-schematic/scripts/rasterize_sheet.py \
  <workdir>/1#系统原理图.svg -o <workdir>/sheet-readback.png
python3 .agents/skills/hydraulic-schematic/scripts/validate_sheet.py <workdir>
# #110 的原始探针/注入样本（另一分支，不合并）
git show b77e770:research/issue110/README.md
git show b77e770:research/issue110/probe_v17_semantics.py
```

### 4.4 「接住」验收清单（证据请求被受理的最小集合）

- [ ] 请求有稳定 ID、目标检查号、对象/锚点、edit spec 与预期伴生；不是「看看这张图」。
- [ ] 沙箱输入清单与 SHA-256、脚本 SHA-256、Python/Chrome/字体环境已记录；与基线同源关系明确。
- [ ] 三条官方命令的 rc 与原始输出保存；validate 报告在场；未改任何生产脚本/门禁/登记表。
- [ ] 目标 fail 的 check ID + detail 来自报告；伴生 fail 逐条归因；未校核/警告单列。
- [ ] 若为出图前阻断：原始 ValueError/rc、无 SVG、无报告的证据齐备，档写 `agent`，披露行只写输入事实；不伪造 SVG 或报告。
- [ ] 若为几何样本：scope 由 `sheet_diff._scope` 验证并保存归一化结果；明确标注 accepted ≠ compare 通过。
- [ ] 有具名 owner 与复核者；第三条命令重跑得到同一 fail ID 集合。
- [ ] 接收方给出下一步（规则/输入诊断、修法候选，或两轮后的未收敛项 + 工程师决策请求）。**只有把请求转成可执行的下一步或显式未收敛，才算接住；留一段文字不算。**

## 5. 已证明 vs 建议（严格分开）

**已证明（proven，证据在本分支或 #110 分支）**
- A 能产生由官方 validate 仲裁的量化样本；B 的两个过门禁目标未复现目标缺陷；C 的生产入口无 registry 注入且字节漂移 fail-closed；D 无报告可仲裁（§1.3）。
- #110 对 V17 语义变异的 `agent` 档与 V2 仅 post-render 的例外均保留，本票未推翻。
- 九 scope accepted 只证明标识合法，不是 diff compare / 交付通过。

**建议（recommendation，待授权决策）**
- 采用 §2 的路径裁决与 §2.1 四条判据；正式确定「post-render 注入」为一种受控证据类型，但永不称为官方渲染产物。
- 采用 §3.2 的改档条件；在此之前不改 #110 去向表。
- 把 #107「route 去向：带范围的诊断交接由谁接、什么算接住了？」从地图雾项毕业：本票给出的是**出图前阻断证据**的接住清单，#107 仍需决定 route 执行者/是否 P3 算一轮/差分范围；可引用本清单作为输入而非结论。
- 另立（本票不建）两个后续：①受控 post-render 注入清单的标准化与归档位置；②V17 吸油语义阻断的官方可渲染诊断路径（若要做，必须先让官方链能判定语义，而不是手改 SVG）。
- #103「从零出图的前置阻塞」仍与本票相关但不在范围内：本票只证明现有 1# 输入上的门禁行为，不解除从零出图门禁。

## 6. 事实边界 / caveat

- 本分支探针基于 391200a 的 1# 派生输入；跨 HEAD、跨系统、跨字体环境需重跑，旧证据失效。
- V2 的 post-render 注入直接复用 #110 的确定性编辑；它同时产生 V3/V14/V19，不是单一缺陷样本。
- 两类 V19 不同：交叉预算超限（过门禁的 ACC 探针）与 intent 字节绑定失效（intent 重 dump / 注释探针）；都按 #23 fail-closed，不能互相替代。
- #102 原型提到的「21 张」已更正为 20 张改动图 + 1 张基线；本票沿用更正后的口径。
- `routing-error.json` 只属于 `RoutingError` 路径；V17 语义 `ValueError` 不写它。两者都是出图前阻断，但机制不同，披露时不要混用。
- 本票不写 GitHub issue、不改地图、不开 PR；回填 #102 去向表和地图需由有授权的用户执行。
