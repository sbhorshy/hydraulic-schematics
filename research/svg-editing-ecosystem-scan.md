# 编制层技术形态扫描：SVG 编辑生态与 agent 环先例

- 票：[编制层技术形态扫描：SVG 编辑生态与 agent 环先例](https://github.com/sbhorshy/hydraulic-schematics/issues/57)
- 母图：[「编制层」定档决策书](https://github.com/sbhorshy/hydraulic-schematics/issues/54)
- 日期：2026-09-29
- 性质：wayfinder 研究产物，只做候选清单与初判，**不做定档**。写回层形态（layout 直改 / overrides 叠加 / patch 合并）、编制档位（微调已出图 / 从零画新图 / 页面编排 / agent 交互环）均留给后续签认票。

---

## 0. 结论速览

**三形态排序初判：**

| 排序 | 形态 | 一句话初判 |
|---|---|---|
| 1 | **自研轻量静态页（原生 SVG 事件 + 1~2 个微库）** | 本仓 SVG 已自带稳定 id + data-* 寻址体系，拖拽→写回 layout 坐标的链路最短，无第三方数据模型，与 skill 链耦合最低；是唯一同时满足「SVG 是唯一视觉真源」与「只写坐标不生成语义」的形态。 |
| 2 | **纯 MCP 交互环（人看图提意见、agent 改 JSON）** | 成本最低、可立刻起步（现链 validate 闭环的延长线），但自然语言精调坐标效率低；它与形态甲不是互斥而是互补——Tavotto 已证明「人在画布拖」与「agent 经 MCP 写」可共用同一写回层。 |
| 3 | **嵌图编辑框架（JointJS / maxgraph / drawio embed / Excalidraw）** | 全部强制自带数据模型且自建渲染（Excalidraw 连保真描边都做不到），引入即产生第三份并行真源，需写双向同步器，与「SVG 是唯一视觉真源」直接冲突；否决，仅当「从零画新图」档位被签入范围时重评 maxgraph 一类。 |

**推荐路径（供定档票参考，非本票决议）：丙先行 → 甲为终态，乙否决。**

---

## 1. 本仓输入盘点（研究的落地锚点）

扫描前先确认编辑器要操作的「物料」实际长什么样，避免对着想象中的 SVG 做适配度判断。

### 1.1 渲染成品 SVG 的可寻址性

以 `1#系统原理图/1#系统原理图.svg`（viewBox 0 0 1680 1390）实测：

- **稳定 id**：顶层分组 `sheet / groups / lines / suction-markers / bridges / junctions / externs / symbols`；符号实例形如 `<g id="PRV-001__check-valve-upper" data-component-type="check_valve" data-status="identified" data-confirmation="user" data-geometry-source="..." data-flow-permitted="..." data-allow-mirror="false" transform="translate(155 27) scale(0.9)">`。
- **data-\* 属性谱系**（实测计数）：`data-network-id`(15)、`data-status`(14)、`data-component-type`(12)、`data-name-slot`(8)、`data-interface-port`(6)、`data-geometry-source`(4)、`data-flow-permitted`(4)、`data-confirmation`(4)、`data-allow-mirror`(4)、`data-from-junction`/`data-to-junction`(2/2)。
- **术语澄清（重要，实现时别踩）**：票面提到的 `connection-points` 是**符号库源 SVG**（`.agents/skills/hydraulic-schematic/assets/component-library/` 一层）的属性——渲染引擎从它实读端口坐标（SKILL.md 不变式 3）。**成品 SVG 里没有 `connection-points` 字面量**，成品图的可寻址性靠 `id` + `data-*`。编辑器实现时不要到成品里找 connection-points。
- **坐标换算要点**：`sheet` 组带 `translate(30,0)`（对应 layout 的 `canvas_shift_x`，见 [#23 坐标契约显式化](https://github.com/sbhorshy/hydraulic-schematics/issues/23) 待删项）；符号 g 内部还有 `scale / rotate / mirror`。因此**拖拽位移必须经 `getScreenCTM().inverse()` 换算**，且写回时只许改符号 g 的 translate 分量（即 layout `nodes.{id}.x/y`），不可碰符号内部变换分量。

### 1.2 写回目标层

`1#系统.layout.json` 实测结构：`nodes: { "TANK-001": {x, y, symbol, w, h}, ... }`（23 个节点）、`labels`（标签文案）、`label_pos`（标签方位枚举）、`canvas`、`canvas_shift_x`、`lanes`/`vlanes`、`legend`、`title_block` 等。人拖节点盒/标签对应的写回字段就是 `nodes.{id}.x/y` 与 `label_pos`/标签偏移；走线（`lines` 分组的 polyline points）由布局引擎按节点坐标推导，**直接改走线顶点会脱离 layout 层表达**——这是「微调已出图」档内走线编辑的深层难点（见 §6 风险）。

### 1.3 与不变式的关系

SKILL.md 四条不变式中，编制层直接相关的是「确定性优先：布局坐标显式给定，不做自动布局」与「渲染引擎单源」。三形态中任何一条都不得把布局求解器带回编辑器——人的拖拽是**对规则结果的覆盖**，不是布局求解（母图 Out of scope 已明示）。

### 1.4 编制层在渲染链中的插入位置

```
intent.yaml（语义源，只读）
   │ 渲染引擎（规则式布局，端口坐标从符号库 connection-points 实读）
   ▼
layout.json（显式坐标层 ←―― 编制层唯一写回目标）
   │ 渲染
   ▼
成品 SVG（带 id + data-* 的视觉投影 ←―― 编制层唯一视觉界面）
   │ validate + 7 道闸门（B1–B7 / V1–V19）
   ▼
出图/交付
```

要点：编制层**横跨两层但只写一层**——视觉上贴着成品 SVG 交互，数据上只落 layout（或其叠加层）；intent 层对编辑器完全只读，agent 侧工具面同样不得触碰 intent。这张图同时说明为什么「SVG 是唯一视觉真源」在本链是自然事实而非额外约束：成品 SVG 本来就是渲染的末端产物，编辑器没有必要再造一个平行渲染器。

---

## 2. 候选 A：SVG 交互基座（pan/zoom + 节点级拖拽 + 坐标换算）

适配判据有四条：① 保真渲染**既有** SVG（不要求重画）；② 提供节点级拖拽事件；③ 屏幕坐标→SVG 用户坐标换算可靠（viewBox + pan/zoom + 嵌套 transform 全算对）；④ 不注入与 data-* 语义冲突的结构。

### 2.1 候选总表

| 候选 | 角色 | 保真渲染既有 SVG | 节点级拖拽 | 坐标换算 | 数据模型侵入 | 维护状态 | 适配度 |
|---|---|---|---|---|---|---|---|
| [svg-pan-zoom](https://github.com/bumbu/svg-pan-zoom)（原 ariutta） | pan/zoom | 可，但会往 SVG 里插入自己的 `<g>` 容器并施加 viewport transform | 无（只管视口） | 提供 getPan/getZoom，仍需 getScreenCTM 配合 | 中（改 DOM 结构） | **停更**：末版 v3.6.1（2018），有已知安全问题未修（[Drupal webform 升级工单](https://www.drupal.org/project/webform/issues/3511438)为证） | **C，不建议新采用** |
| [panzoom（anvaka）](https://github.com/anvaka/panzoom) | pan/zoom | 好：在宿主元素上施加 transform，不重组 SVG 内部 | 无（可配合别的拖拽） | transform 状态可读，换算仍走标准 API | 低 | 活跃 | **A-（pan/zoom 基座首选）** |
| d3-zoom + d3-drag | pan/zoom + 拖拽 | 好：zoom 绑在宿主、drag 绑在节点，互不打架 | **一等公民**（subject/dx/dy） | `d3.pointer(event, container)` 内部即做 `getScreenCTM().inverse()`，缩放/平移下拖拽天然正确 | 低 | 活跃，D3 生态久经考验 | **A（拖拽+缩放一体首选）** |
| [interact.js](https://interactjs.io/) | 拖拽/吸附/resize | 可（HTML+SVG 双支持，pointer events） | 一等公民 | 需自行换算 | 低 | 活跃 | B+（若要吸附对齐功能再看） |
| 原生 Pointer Events + getScreenCTM | 拖拽（零依赖） | 最好（什么都不注入） | 自己绑 pointerdown/move/up | `svgPoint.matrixTransform(svg.getScreenCTM().inverse())` 一个函数 | 零 | Web 标准 | **A-（若只做节点/标签拖拽，无需任何库）** |

### 2.2 关键事实展开

1. **svg-pan-zoom 的 DOM 注入问题**：它在 SVG 里 append 一个包裹 `<g>` 并把全部内容挪进去施加 transform（社区文档与分析文均有记载）。对本仓无害但恼人：编辑器按 id 查询节点仍有效，但任何「按原始 DOM 序列化回写」的旁路想法会拿到被改写的结构。加上 2018 年起停更，**没有理由为它接受这两项成本**。
2. **坐标换算的标准姿势**（各路线通用，写进实现票即可）：
   ```js
   // 屏幕/客户坐标 → SVG 用户坐标（自动吃掉 viewBox、pan、zoom、嵌套 transform）
   const pt = svg.createSVGPoint();           // 或 new DOMPoint()
   pt.x = e.clientX; pt.y = e.clientY;
   const user = pt.matrixTransform(svg.getScreenCTM().inverse());
   ```
   位移拖拽用 delta 而非绝对值，缩放任何档位下行为一致。**这一点直接化解 canvas_shift_x 类偏移带来的手拼坐标风险**（[#23 坐标契约显式化](https://github.com/sbhorshy/hydraulic-schematics/issues/23) 落地后同样适用）。
3. **d3-drag 的 subject 机制**正好对应「拖的是 layout 节点而不是 SVG 元素」：subject 返回 `{x: node.x, y: node.y}`，drag 结束回调里拿到的就是用户坐标下的新位置，一次换算、直接可写。
4. **不要把 pan/zoom 和拖拽搅在一个库里硬凑**：d3-zoom 绑宿主 svg、d3-drag 绑节点 g 的组合是成熟模式（地图/谱系图大量在用）；anvaka/panzoom + 原生 pointer 亦可。两者都满足「SVG 内容零改动」。

### 2.3 逐库适配/不适配备注

- **svg-pan-zoom**：适合的场景是「只读查看一张外来 SVG」——但它连这个场景都被停更状态拖累（2018 年后无 release，安全修复滞后）。对本仓唯一的差异化能力（旋转视图）我们也用不上（图签要求正置）。**结论：排除。**
- **anvaka/panzoom**：`transform` 打在宿主上，wheel 缩放以光标为锚点、支持触摸双指；`panzoom(el, { beforeWheel })` 可做「Ctrl+滚轮才缩放」的工程软件习惯。适合作为只读浏览态的视口层；编辑态与 d3-drag 或原生 pointer 共存无冲突（不同元素分层绑定）。**结论：pan/zoom 首选之一。**
- **d3-zoom + d3-drag 组合**：d3-zoom 管宿主视口（filter 可排除节点上的起手事件），d3-drag 管节点；`drag.subject()` 直接挂 layout 坐标，`event.subject` 在拖拽全程携带起始偏移，天然实现「按住符号本体拖、坐标按 layout 网格吸附」。D3 只按需引 d3-zoom/d3-drag/d3-selection 三个子模块，无全家桶问题。**结论：编辑态首选。**
- **interact.js**：pointer events 统一鼠标/触摸/笔，自带 snap grid、restrict、resize、dropzone。本仓首版用不到 resize/dropzone；若后续「页面编排」档位签入（面板拖放排版），其 snap/dropzone 价值才凸显。**结论：备选，挂起。**
- **原生 Pointer Events**：`setPointerCapture` + `getScreenCTM().inverse()`，约 60 行可写完拖拽原语。若最终只需要「节点盒 + 标签拖拽」两种手势，这是依赖最少的方案；换 d3-drag 的动机是 subject/吸附这些现成轮子。**结论：与 d3-drag 二选一，实现票上比一次即可。**

### 2.4 hit-testing 与选中态（基座之上、编辑器之内的薄层）

- 本仓 SVG 分层清晰（`symbols/lines/junctions/bridges/...` 各一组），选中态用 CSS 类高亮（描边加粗/加焦点框）即可，无需改几何；`pointer-events` 按组开关可做到「只点得中节点盒、管线不挡手势」——Tavotto 的 hit-test 按绘制几何而非包围盒，本仓符号是描边几何，`getBoundingClientRect` 包围盒在密集图区会互相遮蔽，应优先利用 `data-component-type` 组的 g 元素级命中。
- 多选/框选、对齐参考线等属于「页面编排」档位能力，首版（微调档）不做，但选中态的单选/shift 多选应一开始就定好事件协议，避免后续返工。

### 2.5 小结

「保真渲染既有 SVG + 节点级拖拽 + 坐标换算」这个组合在原生 SVG + 微库路线上是**充分解**，且都是零/低侵入。交互基座不构成引入重型框架的理由。

---

## 3. 候选 B：图编辑框架（自带数据模型的一揽子方案）

判据：能否反向吃下已渲染 SVG（或从 layout.json 低成本生成其模型）而不产生第三份真源；视觉能否保真。

### 3.1 候选总表

| 候选 | 自带数据模型 | 吃既有 SVG | 视觉保真 | 许可/成本 | 适配度 |
|---|---|---|---|---|---|
| [JointJS](https://docs.jointjs.com/) / Rappid(JointJS+) | 强制：`dia.Graph`/`dia.Cell` MVVC，`graph.toJSON()/fromJSON()` 序列化 | **不能导入任意 SVG**；只能把符号重写为 cell markup/attrs，或把 SVG 以 `svg` 属性嵌进 cell | 自渲染，符号库需逐个重写 | 核心 MPL；Rappid 商业收费 | **C：形态冲突** |
| [maxGraph](https://github.com/maxGraph/maxGraph)（mxGraph/drawio 内核后继） | 强制：`GraphDataModel`（cells/geometry/styles）+ XML codec | 需把 layout 翻译成 mxGraphModel、编辑后再反向翻译 | 自渲染，样式体系外来 | Apache 系，活跃 | **C-：双模型漂移** |
| [drawio embed 模式](https://www.drawio.com/docs/reference/embed-mode/) | drawio XML（iframe 外部不可见其内部） | 通过 postMessage `init/load/save/export/exit` 传 XML | **编辑器 UI 完全外来**，风格/交互与产品无关 | 依赖官方站点 embed=1（或自部署 drawio） | **C-：真源外移** |
| [Excalidraw 嵌入](https://www.npmjs.com/package/@excalidraw/excalidraw)（React 组件） | 强制：plain-object `ExcalidrawElement` 数组（`initialData/onChange/updateScene`） | 不吃任意 SVG（`exportToSvg` 是**导出**方向） | **rough.js 手绘风 canvas 渲染，描边工程图保真不可达** | 开源，React 绑定 | **D：视觉保真直接不可行** |

### 3.2 共同的结构性问题

1. **都是「模型→视图」架构，本仓是「视图即真源快照、坐标层才是可写真源」**。嵌入任何一家都意味着出现第三份模型（框架模型），要写 layout.json ⇄ 框架模型的双向同步器——同步器本身是新的漂移源和 bug 源，且每加一种编辑能力都要同步器跟着长。
2. **视觉保真各有硬伤**：JointJS 要把描边符号库逐个重写为 cell markup（等于把 component-catalog 翻译一遍并长期双维护）；Excalidraw 的 rough.js 手绘风与工程描边图根本 incompatible；drawio embed 干脆换了一套完全外来的编辑器 UI，且写回的是 drawio XML，坐标提取还要再过一层。
3. **与 7 道闸门的关系**：框架编辑路径产出的数据不经过渲染链，闸门形同虚设；除非编辑器被严格限定为「只改坐标字段」（那框架剩下的价值就只有交互组件，为一个拖拽引入全家桶不值）。
4. 这与 Tavotto 评估结论同构：Tavotto 深绑 matplotlib 不可直接复用，可借的是**模式**而非代码；同理 JointJS/maxgraph 的「模式」我们已经用 JSON 链实现了，借不到增量。

### 3.3 逐框架展开

- **JointJS**：官方能力面里没有「导入任意 SVG 变成可编辑图」这一项——JSON 序列化（`graph.toJSON()/fromJSON()`）是 cell 模型层的往返，v4 迁移期社区里连自家 JSON 都有兼容坑。把本仓 22+ 类描边符号逐个改写为 `dia.Element` markup/attrs 等于把 component-catalog 翻译成第二符号库并永久双维护；Rappid（JointJS+）的吸附/对齐/Inspector 好用但要商业许可。买到的（拖拽/连线/历史）§2 全有平替。**排除。**
- **maxGraph**：作为 drawio 内核后继，模型是 `GraphDataModel`（cells/geometry/styles），持久化是 XML codec（与 mxGraphModel 有兼容性边界）。「layout.json → mxGraphModel → 编辑 → 反向提取坐标」要写两个方向的翻译器，且 maxGraph 自述格式与 mxGraph 不完全兼容——翻译器之外再叠一层版本兼容税。TypeScript 原生是它的加分项，但我们不缺 TS。**排除，留档「从零画新图」翻案条件。**
- **drawio embed**：`embed=1` + postMessage（init/load/save/export/exit，proto=json）协议本身干净，MediaWiki/Storage 等集成案例成熟；但 embed 模式官方只支持 diagrams.net 站点（或自部署），编辑器 UI 与本仓产品毫无关系，写回是 drawio XML。相当于「把坐标真源寄存到别人家，再定期取回翻译」。**排除。**
- **Excalidraw**：React 组件 + plain-object element 数组（`initialData/onChange/updateScene`）确实极易与 JSON 链对接，`onChange` 直出坐标——如果视觉要求是手绘风白板，它是四家里集成成本最低的。但本仓是工程描边图（线宽分级、正交走线、CJK 标签排版、图签图例），rough.js 渲染与出图要求 incompatible，`exportToSvg` 是导出方向且产物风格同样不对。**排除，且为四家中唯一「能力匹配、视觉不匹配」的——若未来做构思草图（brainstorm）辅助场景可再想起它。**

### 3.4 小结

图编辑框架与「SVG 是唯一视觉真源、只需写回坐标」**结构性冲突**。唯一可能的翻案条件：母图若签入「从零画新图」档位（编辑器要承担构图而不只是微调），maxgraph 一类可重新进入评估——但那是另一个问题域，且按母图默认约束（concept 上限、agent 为主）概率不高。

---

## 4. 候选 C：agent 交互环先例（人指问题 → agent/工具改结构化数据）

### 4.1 先例清单

| 先例 | 范式 | 对本仓的可借鉴点 |
|---|---|---|
| **[Tavotto](https://github.com/Tavotto/Tavotto)**（matplotlib 图表可视化编辑器，AGPL-3.0，母图点名参考） | ① **Override 叠加**：每个改动单独存为 override，重放（replay）到脚本新跑的结果上，源文件永不碰；undo/版本/导出重渲染全建立在同一机制上。② **MCP 工具面 9 工具**：打开图表、应用 override、normalize（只改用户点名属性）、预检、导出、**验证 replay**、刷新、健康检查、关闭会话。③ **预检规则单源 JSON**：Python 引擎与 TS 前端共用一份 publication.json，杜绝两副本漂移。④ **写回动作**：显式「写回原文件」时从头重跑脚本验证一致。 | **同域最强参考**。override 叠加模式 = 本仓「overrides 层 vs layout 直改」之争的现成答案样例；MCP 工具面粒度（normalize 只改点名属性 ≈ 我们「只写坐标不生成语义」）；预检规则双端单源 ≈ validate_sheet.py 作为编辑器实时校验后端。 |
| **Mermaid 预览类 MCP server**（[mermaid-preview-mcp](https://mcp.so)、Claude Mermaid MCP server 的 `mermaid_preview` 工具等） | agent 生成/改图 → 渲染并**在浏览器开预览** → 人看后给文字反馈 → agent 继续 | 「纯 MCP 环」的最小可行形态：本仓加一个「开 SVG 预览 + 人文字反馈」工具几乎是 validate 闭环的延长线，1~2 天级成本。 |
| **[mcp_excalidraw](https://github.com/yctimlin/mcp_excalidraw)**（MCP server + Claude Code skill） | agent 经工具编程式改 Excalidraw 场景数据，**实时同步**到浏览器画布，人可在同一画布上接着手动拖 | 「agent 写数据、人在真图上接着改」**双向环**的现成实现——证明形态甲与形态丙可共享同一份场景数据与同一块画布。 |
| **[Excalidraw+ 官方 MCP](https://plus.excalidraw.com/docs/mcp/tools)** | `create_diagram` 从语义 nodes/edges/groups 构图，带 label 度量与连线绑定 | 提示「语义→图」方向的 MCP 工具长什么样；本仓 intent→layout 链已是更强版本，仅作对照。 |
| **[drawio-mcp-server](https://npm.io/package/drawio-mcp-server)** 等 | 对 drawio XML 做 CRUD | XML 中介模式，绕开本仓 JSON 链，参考价值低；列出仅为完备。 |
| **CVAT / Label Studio（model-in-the-loop 标注平台）** | 模型出 **pre-annotation** → 人只做**校对/修正** → 结构化 JSON 导出；CVAT 有显式 **review stages（annotation→validation→acceptance）** | 角色映射极其干净：agent 规则布局=pre-annotation，人拖拽微调=correction，写回 layout.json=structured export，7 道闸门=review stages。「机器起草、人修正、结构化落盘、过门放行」是被标注行业验证过的成熟分工。 |
| **v0 / bolt.new / Claude artifacts 预览反馈环**（商业先例） | 分屏预览 + 人给视觉反馈（点击/圈选/文字）→ agent 改结构化源码 → 预览即时刷新 | 交互范式的商业验证；同时提示「agent 为主、人做指正」的产品形态。 |
| **[WebMCP](https://webmachinelearning.github.io/webmcp/)（W3C Web ML CG 草案，2026-02-27 Draft Community Group Report）** | 网页向**访问它的** agent 暴露具名、类型化的工具（非 W3C 标准，CG 草案阶段） | 远期兼容点：若落地，形态甲的静态编制页可原地成为 agent 工具面（页面即 MCP server），形态甲与丙的融合从「自建」变「标准」。**现在不押注，只留接口卫生。** |

### 4.2 范式提炼

所有先例收敛到同一个骨架，本仓可以直接套：

```
[结构化真源] --机器起草/规则渲染--> [视觉产物] --人指问题(拖拽或文字)-->
[结构化修改(override/patch/直改)] --过校核闸门--> [真源更新] --> 重渲染
```

三条铁律（Tavotto 与标注平台共同印证）：
1. **人只改结构化数据的投影，不直接改产物**（改 override/坐标/标注，不改渲染出的图本身）；
2. **机器起草、人修正**的分工（不让人从零画，正如不让 agent 拍脑袋定坐标）；
3. **写回必须过同一套校核**（CVAT 的 acceptance、Tavotto 的 replay 验证 ≈ 本仓 7 道闸门，导出走全闸门）。

### 4.3 双向环操作序列（甲丙合一时的人机时序）

把 Tavotto 与 mcp_excalidraw 的交互拼起来，本仓编制层的完整时序大致是：

```
1. agent 渲染出图（现有 skill 链）→ 2. 人打开编制页（本地服务托管渲染 SVG）
3a. 人直接拖：pointer 事件 → getScreenCTM 换算 → 坐标 diff 暂存（未落盘）
3b. 人发指令：文字/框选圈注 → MCP 工具 → agent 产坐标 patch（白名单字段）
4. 两条路径汇入同一写回层（layout 直改或 overrides 叠加，待定档）
5. 实时校验面：validate_sheet.py 后端跑 → 级别内联回显（Block/Warn/Info）
6. 导出：全 7 道闸门照跑 → 通过才允许落盘/出正式图
```

值得注意的两点：① 3a/3b 产出**同一种中间表示**（坐标 diff/patch）是甲丙合流的关键设计约束——如果两条路各自记一份状态，就退化成双真源；② 第 5 步的校验规则必须与闸门同一份定义（Tavotto 规则单源双端模式），否则编辑器里绿、导出时红，信任立即破产。

### 4.5 对本仓 MCP 工具面的具体启示（对照 Tavotto 9 工具）

按 Tavotto 的工具面粒度映射到本仓，可企及的工具清单（仅供后续立票，本票不设计）：

| Tavotto 工具 | 本仓对应物 | 备注 |
|---|---|---|
| health check | `render --check` / selftest 轻量探针 | 会话起手自检 |
| 打开图表 | `open_sheet`：返回 SVG 预览 URL + layout 摘要 | 人侧浏览器打开 |
| 应用 override | `apply_patch`：白名单字段坐标 patch（nodes.x/y、label_pos…） | **normalize 式窄接口** |
| normalize（只改点名属性） | `nudge`：点名节点 id + 目标坐标/偏移 | 拒绝开放式改图 |
| 预检 | `validate`：跑 validate_sheet.py 返回分级发现 | 与闸门同源 |
| 导出 | `export`：全 7 道闸门通过才产出 | 防绕闸旁路 |
| 验证 replay | `verify`：写回后重渲染并 diff 一致性 | 叠加模式的关键兜底 |
| 刷新/关闭会话 | `reload` / `close` | 多图工作区预留 |

两条设计红线从先例里直接读出：**路径/字段授权模型**（Tavotto：模型建议的路径不算授权——对应本仓：patch 里的字段不在白名单即拒）与**诚实边界**（Tavotto：normalize 满足不了约束就停下来说明——对应本仓：patch 违反构图预算/校核时返回分级失败原因，不静默降级）。

### 4.6 先例之间的反面教材

- **drawio 系 MCP 工具面**提醒我们：把「编辑器私有格式」（drawio XML）当工具面数据，agent 的每次操作都要过一层格式翻译，且翻译层外无校核。本仓工具面必须直接说 layout.json 的方言，不引入中间格式。
- **maaker-ai/excalidraw-mcp 一类「生成器型」server**（25+ 图型从提示词直出）与本票问题域相反——它们解决「从零生成」，不解决「对既有产出做受控修正」；列入清单仅为防止后续检索时混淆两类工具。

---

## 5. 三形态对比与排序初判

### 5.1 对比表

| 维度 | 甲：自研轻量静态页 | 乙：嵌图编辑框架 | 丙：纯 MCP 交互环 |
|---|---|---|---|
| 一次成本 | 中低：单 HTML + 1~2 个 ES module（d3-drag 或原生 pointer），编辑器只做「加载 SVG+layout → 拖拽 → 产出坐标 diff」 | 高：模型翻译器（layout⇄框架模型）+ 符号库重译 + 同步器长期维护 | **最低**：MCP 工具（开预览/收反馈/改 JSON）+ 现有 validate 闭环，1~2 天级 |
| 持续成本 | 走线编辑、undo、吸附等功能按需长 | 同步器随两边演化持续付税 | 低，但每次精调都烧 agent 往返 |
| 视觉真源 | **SVG 原样即视觉真源**，编辑器是它的交互皮 | 框架自渲染，SVG 降级为导出物 | SVG 原样即视觉真源 |
| 只写坐标、不生成语义 | 天然满足：写回字段白名单（nodes.x/y、label_pos…） | 要靠纪律在框架模型里拦，堤坝筑在别人院里 | agent 改 JSON 有生成语义风险，需工具面收窄（Tavotto normalize 式「只改点名属性」） |
| 与 skill 链耦合 | 最低：layout.json 仍是唯一可写坐标层；导出走全闸门 | 最差：第三真源 + 绕闸诱惑 | 低：直接复用渲染/校核脚本 |
| 人的精度控制 | **最强**：像素级拖拽 | 强 | 弱：自然语言描述坐标低效 |
| agent 协同 | 可叠加（WebMCP/MCP 工具面后续加） | 框架各有 MCP 生态但都是别人的模型 | **原生最强** |
| 风险主项 | 走线（polyline）编辑复杂度；undo/历史自研 | 双模型漂移；视觉保真不可达（Excalidraw 直接否） | 精调效率；agent 写坏 JSON（靠闸门兜底） |

### 5.2 档位 × 形态适配矩阵（对母图四档逐一检验）

| 母图档位 | 甲·静态页 | 乙·嵌框架 | 丙·MCP 环 | 备注 |
|---|---|---|---|---|
| 微调已出图 | **强适配**（首版即可覆盖：拖节点盒/标签、改 label_pos） | 不适配（为拖拽引全家桶） | 适配（文字级微调：挪 20px 类指令） | 母图 Notes 点名痛点即此档 |
| 从零画新图 | 弱（缺构图手势：加节点/连线） | 相对最优（但视觉保真仍硬伤） | 适配（agent 出初稿+人迭代） | 若签入此档，乙翻案条件在此；且与「不做自动布局」不变式需重新对齐 |
| 页面编排 | 中（多图工作区自己搭，interact.js snap 有用） | 中（面板排版是框架强项） | 弱（排版要手调） | interact.js 备选在此档启用 |
| agent 交互环 | 中强（叠加 MCP 工具面后同 3a/3b 双路） | 弱（agent 面对的是框架私有模型） | **强适配**（原生就是 agent 环） | 丙的主场；甲补上拖拽精度 |

矩阵显示：**没有任何单一档位让乙胜出**；甲在主档（微调）最强且向其余档位延展性好；丙在 agent 环档位不可替代。

### 5.3 排序依据

**第 1 名·形态甲**：只有它同时满足两条硬约束——「SVG 是唯一视觉真源」（编辑器对 SVG 零重组，见 §2 全部候选零/低侵入）与「只写坐标不生成语义」（写回字段白名单落在自家 layout 层）。且 §2 证明交互基座是**已解决的问题**（d3-drag/原生 pointer + getScreenCTM），剩下的都是可控的量（白名单 diff 写回、undo 栈）。风险主项（走线编辑）可以通过档位切分：先做节点盒/标签拖拽（覆盖母图 Notes 里点名的「手改 layout.json 坐标」痛点），走线编辑单独立票。

**第 2 名·形态丙**：成本最低、可当天起步，且是形态甲的天然前置——先用 MCP 环验证「人指问题→agent 改坐标」的写回层设计与闸门互动（Tavotto 的 MCP 工具面 + override replay 是照抄级参考），把写回层形态（layout 直改 vs overrides 叠加）试出手感，再上静态页时写回层已定。缺点独立看是硬伤：像素级精调靠嘴说不可持续——所以它排第 2 是作为**阶段与组件**，不是终点。

**第 3 名·形态乙**：三个候选全部触发「第三真源 + 双向同步器」，视觉保真各有硬伤且 Excalidraw 直接不可达；引入它买到的交互能力（拖拽/吸附/连线）在 §2 的微库路线里都是现成的。**否决**；保留唯一翻案条件：若「从零画新图」档位被签入母图范围，重评 maxgraph 一类（届时问题域已变成构图，不再是本票的「微调已出图」）。

### 5.4 形态甲最小实现骨架（数据流与模块切分，供实现票起步）

```
editor/
  index.html          # 单页壳：视口层 + 属性面板 + 校验回显条
  editor.mjs          # 主控：加载 SVG + layout.json，装配交互
  viewport.mjs        # pan/zoom（d3-zoom 或 anvaka/panzoom，二选一）
  drag.mjs            # 节点/标签拖拽（d3-drag 或原生 pointer）
  diff.mjs            # 拖拽结果 → 白名单坐标 diff（nodes.x/y、label_pos、标签偏移）
  writeback.mjs       # diff → layout 直改或 overrides 叠加（等定档）；本地服务写盘
  check.mjs           # 调 validate_sheet.py → 内联回显 Warn/Block
```

数据流只有一条：**SVG 是渲染投影，layout.json 是坐标真源，编辑器内存里只存在「未应用的 diff」一种临时状态**；任何时刻刷新页面 = 回到真源状态（或真源+已应用 overrides），不存在编辑器私有的第二份全量模型。这条纪律同时消灭了「双真源漂移」和「保存格式」两个问题——保存动作就是「把 diff 交给写回层」，而不是「序列化编辑器状态」。

实现要点清单（写给实现票）：
- 坐标换算一律 `getScreenCTM().inverse()`，禁止手拼 canvas_shift_x/sheet 平移常量（#23 兼容性）；
- 拖拽 subject 挂 layout 坐标（`{x: nodes[id].x, y: nodes[id].y}`），落下时只写白名单字段，diff 里携带 `_gate: pending` 状态；
- 符号 g 只改 translate 分量；mirror/scale/rotate 分量锁定并在 UI 上以锁形图标示意；
- 每次落 diff 即触发 validate 后端（防抖 300ms 级），Block 级发现直接拒绝落盘；
- 金样/selftest 关系：编辑器不进 skill 主链、不碰 frozen 原型，导出动作复用渲染脚本全链跑闸门。

### 5.5 与母图待签项的衔接（不越权定档）

- 写回层形态（layout 直改 / overrides 叠加 / patch）：本票证据倾向 **Tavotto 式 overrides 叠加**（不改 layout.json 本体、replay 可验证、可整体丢弃），但该决策必须先与 [#23 坐标契约显式化：drawable 矩形 + EDGE_MARGIN，删 canvas_shift_x](https://github.com/sbhorshy/hydraulic-schematics/issues/23) 兼容（SVG 里的 `sheet translate(30,0)` 就是 canvas_shift_x 的投影，叠加层坐标系定义要等 #23 定稿）——留给定档票。
- 编辑器与 7 道闸门互动：validate_sheet.py 可作编辑器实时校验 CLI 后端；规则单源双端共享（Tavotto publication.json 模式）值得立票明确。
- 交付形态归属（进 skill 还是独立 `editor/` 目录、CI 托管还是本地服务）：形态甲/丙都倾向「独立目录 + 本地起服务」，与 MCP 工具面可合并为一个本地进程——待定档后立票。

---

## 6. 风险与开放问题

1. **走线编辑是硬骨头**：polyline points 由布局引擎从节点坐标推导，直接拖顶点会脱离 layout 层表达。选项：a) 只允许「整根走线平移 lane/偏移量」（写回 lanes 层参数）；b) 引入 override 级顶点覆盖（Tavotto 模式）；c) 首版不做走线拖拽。**倾向 c→a→b 渐进**，立票再议。
2. **符号内部变换的写回边界**：符号 g 带 `scale/rotate/mirror`（`data-allow-mirror` 可镜像），编辑器只能改 translate 分量；mirror 翻转下的坐标语义（x 是左缘还是镜像后位置）需在写回层定案时一并明确。
3. **#23 依赖**：canvas_shift_x 删除后 SVG sheet 平移消失/变更，编辑器坐标换算若手拼常量会静默错位——实现票必须规定「一律走 getScreenCTM().inverse()，禁止手拼偏移常量」。
4. **undo/历史/多会话**：静态页自研 undo 栈是纯增量成本；若采用 overrides 叠加则 undo 近乎免费（丢最后一条 override），这是叠加模式的又一加分项。
5. **托管与文件读写**：GitHub Pages 托管的静态页写不回本地文件（File System Access API 仅 Chromium + 仍需用户授权）；本地起服务（编辑器与 MCP 工具面同进程）是目前最顺的工程形态，也顺便解决「浏览器直接吃仓库文件」的路径问题。
6. **agent 写坏 JSON 的兜底**：形态丙里 agent 改 JSON 必须过 validate + 7 闸门；工具面应做成 Tavotto normalize 式窄接口（只收点名属性的白名单 patch），不做开放式「帮我改图」工具。
7. **WebMCP 不押注**：草案阶段（非标准），只在实现票里留一条「页面工具命名空间按其形态预留」的接口卫生要求，不做任何提前适配。
8. **许可注意**：若未来真要参考/接触 Tavotto 代码，其 AGPL-3.0 意味着**只借模式不借代码**（母图 Out of scope 已定：不碰其代码）——本票所有借鉴均为模式级。
9. **intent 只读边界在 UI 上的呈现**（母图 Not yet specified 项）：编辑器把 intent 当只读真源，但端口角色/介质/主名等语义信息在选中态如何展示、误改如何拦截（编辑器根本没有 intent 的写路径，天然拦截），属性面板的信息分级需实现票定义。
10. **maturity/签认状态的显示口径**（母图 Not yet specified 项）：concept 未签认=WARN 披露放行，`data-status`/`data-flow-permitted`/`data-confirmation` 已随 SVG 渲染带出，编辑器回显这些字段即可与规格口径一致；禁止编辑器提供任何「升档」动作（工程放行图 Out of scope）。
11. **并行编辑冲突**：layout.json 是仓库文件，人拖完落盘的同时 agent（或另一会话）可能也在改——写回层应做「读-校-写」原子小事务 + 冲突时拒绝并要求重渲染，不做三方合并（patch 合并形态若被选，则复杂度上移到写回层，属定档票权衡项）。
12. **金样与回归**：编辑器产出的写回改动会让 layout.json 偏离规则引擎的「自然输出」，validate/金样比对可能出现预期内 diff——需要口径：金样锁定的是闸门通过性还是坐标逐字节一致？这直接影响 overrides 叠加是否可行（叠加 = 永久偏离自然输出），**必须与 selftest 口径票联动**。
13. **安全面**：本地服务若开 HTTP 端口，参照 Tavotto 的教训做目录白名单 + 一次性 nonce + 仅绑定 localhost；不得让编辑器页面获得任意文件读写。

---

## 7. 附：检索来源备忘

- 交互基座：svg-pan-zoom（[GitHub](https://github.com/bumbu/svg-pan-zoom)）、anvaka/panzoom（[官网](https://anvaka.github.io/panzoom/)）、d3-drag/getScreenCTM 惯用法（[示例文](https://javascript.plainenglish.io/how-to-implement-drag-and-drop-from-react-to-svg-d3-16700f01470c)、[Schematex changelog](https://schematex.js.org)）、interact.js、npm trends 对比
- 框架：JointJS（[JSON 导入导出](https://docs.jointjs.com/learn/features/export-import/json)、[Graph API](https://docs.jointjs.com/api/dia/Graph)、[React 互操作·模型层](https://docs.jointjs.com/react/jointjs-interop/working-with-models)）、maxGraph（[GitHub](https://github.com/maxGraph/maxGraph)、[文档](https://maxgraph.github.io/)）、drawio（[Embed mode 官方文档](https://www.drawio.com/docs/reference/embed-mode/)、[drawio-github 集成实例](https://github.com/jgraph/drawio-github/blob/main/CLAUDE.md)）、Excalidraw（[npm @excalidraw/excalidraw](https://www.npmjs.com/package/@excalidraw/excalidraw)）
- agent 环：Tavotto（[GitHub](https://github.com/Tavotto/Tavotto)，README/文档抓取）、mermaid-preview 类 MCP（mcp.so / lobehub 收录）、[mcp_excalidraw](https://github.com/yctimlin/mcp_excalidraw)、[Excalidraw+ MCP Tools](https://plus.excalidraw.com/docs/mcp/tools)、[drawio-mcp-server](https://npm.io/package/drawio-mcp-server)、CVAT（[cvat.ai](https://www.cvat.ai)）/Label Studio model-in-the-loop 文档、v0/bolt.new 对比文（[ones.com](https://ones.com)、[Cadence blog](https://cadence.withremote.ai)）、[WebMCP 草案](https://webmachinelearning.github.io/webmcp/)
- 本仓实测：`1#系统原理图/1#系统原理图.svg`（data-* 谱系、sheet 平移、符号 transform）、`1#系统原理图/1#系统.layout.json`（nodes/labels/label_pos 写回字段）、`.agents/skills/hydraulic-schematic/SKILL.md`（不变式 3 与 connection-points 术语澄清）

## 8. 逐项回答票面四问（一句话收口）

1. **SVG 交互基座**：pan/zoom 与拖拽各选一个微库（d3-zoom+d3-drag 或 anvaka/panzoom+原生 pointer）即为充分解；svg-pan-zoom 停更排除；坐标换算统一走 `getScreenCTM().inverse()`。
2. **图编辑框架**：四家全部强制自带数据模型、自建渲染，与「SVG 是唯一视觉真源」结构性冲突（Excalidraw 连视觉保真都不可达）——否决，翻案条件仅为「从零画新图」档被签入。
3. **agent 交互环先例**：Tavotto（override 叠加 + 9 工具 MCP 面 + 预检规则单源）为同域最强参考；CVAT/Label Studio 的「pre-annotation→人修正→结构化导出→review stages」提供分工范式；mcp_excalidraw 证明 agent 写数据与人在真图上改可共享同一份场景。
4. **形态初判**：甲（自研静态页）> 丙（纯 MCP 环，先行起步）> 乙（嵌框架，否决）；推荐「丙先行、甲终态、乙否决」，写回层形态与 #23 的兼容性留给定档票。
