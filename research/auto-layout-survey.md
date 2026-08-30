# 布局自动化方法调研：母线式正交原理图的选型输入

> 对应票：布局自动化方法调研：母线式正交原理图的选型输入（[#16](https://github.com/sbhorshy/hydraulic-schematics/issues/16)），父图：复杂拓扑端到端工具化——Wayfinding 地图（[#10](https://github.com/sbhorshy/hydraulic-schematics/issues/10)）。
> 性质：纯调研，**只调研不定案**。产出作为后续「布局机制选型原型」票的输入。
> 日期：2026-08-31。

---

## 0. 问题约束（管线现状，选型的边界条件）

先明确任何方案都要满足的硬边界，来自对 `1#系统原理图/` 现状（render.py / validate_sheet.py / 1#系统.layout.json / rendering-rules.md）的阅读：

1. **布局的输出物是三组绝对坐标**：`nodes`（每实例 x/y/w/h/rot）、`buses`（竖直母线 x）、`lanes`/`vlanes`（水平/垂直走廊），落进 `<name>.layout.json`。render.py 的 `route()` **已经内置**给定端点后的正交走线择优（直连仅共线、单折、双折、走廊组合候选，代价 = 穿元件 > 叠线 > 压字 > 交叉 > 长度 > 折返）。因此**自动布局要解的是"放节点、定母线 x、给走廊"，不是"画线"**——除非连 route() 一起替换。
2. **方向惯例是领域先验而非通用美学**：油箱置左、压力向上/向右、回油向下、吸油走廊独立、用户边界在右缘、母线竖直。这些写在 rendering-rules 与 layout 注释里，必须能被方案显式表达（硬约束或高权重规则），而不是指望算法自己涌现。
3. **质量有客观度量**：B1–B7 构图预算（交叉恒 0、折返 ≤3/全图 ≤40、绕行比 ≤1.5、最短段 ≥8px、盒净距 ≥40px、走廊、标签净空）已在 validate_sheet.py 实装。任何候选布局可直接跑面板打分——这是选型原型的现成对标器。
4. **规模很小**：14 受控实例 + 2 边界 + 4 母线 + 2 taps、21 条边。性能不是约束，**语义表达力与落地成本才是**。1# 图 layout 四轮返工（revision_log 1.0→2.3）的痛点是"每次返工都是人肉解一个多变量空间布局谜题"。

---

## 1. 各方向方法概述

### 方向 A：分层式（Sugiyama 类）

**A1. ELK（Eclipse Layout Kernel）layered 算法。**
Sugiyama 框架的工业级实现：分层 → 减交叉 → 坐标分配 → 边路由四阶段，边路由可选 ORTHOGONAL/POLYLINE/SPLINES，与放置联合决定坐标（[官方 layered 参考](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html)、[ELK 论文 arXiv 2311.00533](https://arxiv.org/pdf/2311.00533)，后者指出其以端口为显式边锚点、140+ 布局选项）。可定制点对本问题关键：`layerConstraint` 钉死节点所在层（[参考](https://eclipse.dev/elk/reference/options/org-eclipse-elk-layered-layering-layerConstraint.html)）、`positionChoiceConstraint` 钉死层内位置（[参考](https://eclipse.dev/elk/reference/options/org-eclipse-elk-layered-crossingMinimization-positionChoiceConstraint.html)）、`portConstraints` 的 FIXED_SIDE/FIXED_ORDER/FIXED_RATIO/FIXED_POS 精确钉端口（[参考](https://eclipse.dev/elk/reference/options/org-eclipse-elk-portConstraints.html)）、以及从既有坐标反推约束的 interactive 模式（[ELK 博客](https://eclipse.dev/elk/blog/posts/2023/23-01-09-constraining-the-model.html)）。**但没有"母线"这一原生概念**：竖直汇流条只能建模为细长节点或折叠边，"多条支路在不同 y 接同一 x"不是它的第一类 citizen；折返数、绕行比这类构图预算也不在其代价函数里。实现落地：ELK 是 Java 库，Python 管线要走 elkjs（官方 JS 移植，[GitHub kieler/elkjs](https://github.com/kieler/elkjs)）+ Node 子进程桥，输入输出都是 JSON 图。

**A2. Graphviz/dot。**
分层布局的开销最低选项（pip `graphviz` + 系统二进制），`rank=same`/`constraint=false` 可控行，但其正交路由 `splines=ortho` 的能力边界对本案是硬伤：**不支持端口（ports）**（Graphviz 维护者在[官方 GitLab issue #1415](https://gitlab.com/graphviz/graphviz/-/issues/1415) 确认 "Ortho does not handle ports"，[官方论坛同确认](https://forum.graphviz.org/t/regarding-graphvizs-orthogonal-edge-routing/1889)）、dot 下边标签失效、边集中禁用，且 ortho 下可能产生重叠。社区的可行套路是用不可见节点 + `group` 属性伪造正交对齐（[论坛方案](https://forum.graphviz.org/t/graph-with-orthogonal-edges/2362)）——本质是绕过路由器手工摆布。ELK 官方还提供了 dot 算法的重实现以替代（[ELK graphviz-dot 参考](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-graphviz-dot.html)）。

**A3. 先例：Weave——netlist 到原理图的分层转换（2025，arXiv）。**
把网表转 LTspice 原理图的完整开源管线：信号网交给 elkjs layered **联合完成放置与正交布线**，特殊结构（反馈、分压、供电角落）不进主图而由"放置模式"直接摆，全部坐标对齐 16 单位网格，最后做**往返连通性机器验证**（重新解析出图与输入网表逐网比对）。自述局限：深级联被拉成长链、密集多引脚模块失败率高、未报告交叉/折返等美观指标（[论文 HTML 全文](https://arxiv.org/html/2607.03835v1)）。它证明了"分层引擎 + 领域模式 + 验证闭环"组合在原理图生成上是可发表的工程路线，且供电轨/地**不画成线而用旗标**的取舍与本案"母线画线"相反，值得对照。

### 方向 B：EDA / 电力单线图 / 线束领域

**B1. 变电站单线图（one-line diagram）自动生成——与本案同构度最高。**
母线式图（水平/竖直汇流条 + 间隔挂接）的自动布局在电力调度可视化里有成熟先例：[Substation One-Line Diagram Automatic Generation and Visualization（arXiv 1903.09495）](https://arxiv.org/abs/1903.09495)用**规则式分层启发式**（非力导向非约束求解）：① 按电压等级划区域；② DFS 识别母线接线方式（双母线分段、一个半断路器等 10 余种模式）并定位母线，母线长度 = 所挂支路宽度之和取上下较大者；③ 支路（间隔）按 role 定朝向——发电机支路朝下、变压器置中"避免交叉与重叠"、其余默认朝上，按节点数与子支路宽度分配间距；④ 子支路递归。在真实省级电网 799 座变电站上全部生成、95% 以上良好。**这套"role→朝向、母线=承重结构、间距=所挂支路宽度"的处方与本案方向惯例（油箱置左/压力向上/回油向下、母线 x 决定走廊）几乎一一对应。**

**B2. VLSI 单行布线（Single-Row Routing, SRR）——母线分支通道分配的理论框架。**
SRR 研究终端固定在一根轴上、走线在上下两个"街道"（street）的水平轨道（track）里完成的布线问题，核心度量是上下街拥塞与**折返（dogleg/bend）数**，最小折返 SRR 已有专门研究（[IEEE: On minimum-bend single row routing](https://ieeexplore.ieee.org/iel2/640/5935/00230022.pdf)、[术语图示：单行轴/上下街/轨道](https://www.researchgate.net/figure/Terminologies-in-the-single-row-routing-problem_fig1_257797430)），问题本身 NP-complete（[综述性引用](https://www.ukm.my/jsm/pdf_files/SM-PDF-43-8-2014/19%20Ser%20Lee%20Loh.pdf)）。把每条竖直母线看作单行轴、分支接入看作上下街轨道分配，可为 render.py 的 lanes/vlanes 走廊值提供**有理论出处的自动分配法**，且其折返度量与 B2 同源。

**B3. 线束（wire harness）领域。**
检索到的自动化集中在**物理制造图**：3D 布线→自动展平成 2D formboard（[学术：三维线束自动展平](https://www.researchgate.net/publication/259266510_Automatic_flattening_of_three-dimensional_wiring_harnesses_for_manufacturing)；[商业：Zuken E3.formboard 打包算法](https://www.zuken.com/en/product/e3series/wire-harness-design-and-manufacturing-ecosystem/)、[Siemens Capital 展平](https://www.siemens.com/en-us/products/designcenter/cad-software/electronic-electrical-cad/wire-harness-design/)），以及平面线束布局优化框架（[Optimization Framework for Cable Harness Layouts in Planar Interconnected Systems（索引页）](https://ouci.dntb.gov.ua/en/works/7AYYmak7/)）。**未找到线束领域"原理图 lane/channel 分配"的可靠公开来源**——该方向可借鉴的是展平/打包的思路，与本案图面布局关系较远。

**B4. 液压领域直接文献。**
最接近的一篇是 ASME J. Mech. Des. 2025 的 [Automated Layout Design of Hydraulic Components With Constraints on Flow Channels](https://asmedigitalcollection.asme.org/mechanicaldesign/article/147/5/051701/1206705/Automated-Layout-Design-of-Hydraulic-Components)（Zhu, Wang, Zhang 等，147 卷 5 期 051701）。原文站 403、摘要不可得；从引用它的后续工作（平面线束布局优化、起落架舱管路图式设计语言）看，其"布局"偏**物理封装/流道约束**而非 2D 原理图图面。**"液压原理图 2D 图面自动布局"的直接可靠文献：未找到。** 商业液压 CAD（HyDraw、HydroSym 等）只宣传自动 BOM/端口表，未见公开的布局算法资料。这反过来说明：本案最可行的知识来源是同构域（B1/B2）迁移，而非现成液压方案。

### 方向 C：约束求解 / 声明式布局

**C1. Cassowary/Kiwi（kiwisolver）。**
Cassowary 是增量单纯形线性约束解算器，Apple Auto Layout / GTK 的底层（[GTK 博客：Constraint layouts](https://blogs.gnome.org/gtk/2019/07/02/constraint-layouts/)）；Kiwi 是其高效 C++ 重实现（比原版快 10–500 倍，[nucleic/kiwi](https://github.com/nucleic/kiwi)），**kiwisolver 即其官方 Python 绑定，是 matplotlib 的依赖、pip 即装**（[文档](https://kiwisolver.readthedocs.io/)、[PyPI](https://pypi.org/project/kiwisolver/)）。线性等式/不等式 + 强度分级（required/strong/weak）恰好能表达：母线 x 固定（required 等式）、同组元件 y 相等（元件分行）、盒间距 ≥40px（B5 直译）、走廊偏移 ≥12px（B6 直译）、方向惯例作弱约束偏好（"油箱尽量靠左"）。**表达不了**：交叉数、折返数、绕行比这类非线性的图面拓扑量——布线仍要交给现有 route() 或另行处理。

**C2. WebCola / Adaptagrams。**
Adaptagrams 的 libcola 是"应力主化 + 分离/对齐约束"的 C++ 约束布局库（[官网](https://www.adaptagrams.org/)、[libcola 文档](https://www.adaptagrams.org/documentation/libcola.html)、[GitHub](https://github.com/mjwybrow/adaptagrams)）；WebCola 是其浏览器版（[cola.js](https://ialab.it.monash.edu/webcola/)），并有高层约束 DSL SetCoLa（[GitHub uwdata/setcola](https://github.com/uwdata/setcola)）；Adaptagrams 另含拓扑保持的正交 connector 路由。约束表达力好（分离、对齐、分组边界都有第一类支持），且学术上有工程图约束布局的先例（[Interactive, Constraint-based Layout of Engineering Diagrams](https://www.researchgate.net/publication/220053960_Interactive_Constraint-based_Layout_of_Engineering_Diagrams)）。**短板在落地：无维护的 Python 绑定**——要么 Node 桥跑 WebCola，要么自己包 C++，均高于 kiwisolver 的成本。

### 方向 D：元启发搜索（构图度量当目标函数）

**D1. Davidson–Harel 模拟退火——"美学即能量函数"的经典先例。**
[Drawing Graphs Nicely Using Simulated Annealing（ACM TOG 1996）](https://dl.acm.org/doi/pdf/10.1145/234535.234538)明确指出"应用退火最重要的一步是定义能量（代价）函数"，其代价项为：节点分布 + 边长均匀 + **边交叉数** + 边点分离的加权组合；igraph 等主流库已内建实现（[layout_with_dh 文档](https://igraph.org/r/html/1.3.5/layout_with_dh.html)，并直言其能量函数"难以对不同图参数化"——提醒权重工程是真实成本）。这与"把 B1–B7 当惩罚函数"的设想同构：交叉（B1）、折返（B2）、绕行比（B3）、盒距（B5）全部是逐布局可算的确定性函数，validate_sheet.py 里已有现成实现可复用为 cost。

**D2. VLSI 布局的模拟退火——行式布局寻优的工程先例。**
TimberWolf 用 SA 做标准单元行式布局并成为学术 EDA 的标杆（[The TimberWolf Placement and Routing Package](https://www.researchgate.net/publication/2981545_The_Timber_Wolf_Placement_and_Routing_Package)、[Semantic Scholar 条目](https://www.semanticscholar.org/paper/The-TimberWolf-placement-and-routing-package-Sechen-Sangiovanni-Vincentelli/6be68c9a463f03b3e865086680d01b00d08d956e)），后续分层行式版本做到当时超大规模电路的最优（[Sun & Sechen](https://www.semanticscholar.org/paper/6be68c9a463f03b3e865086680d01b00d08d956e) 系列工作）。其"单元进行 + 线长/拥塞代价 + 邻域移动"模式与"元件分行 + B1–B7 代价 + 挪位/换行/母线微调邻域"高度可比。另有保持心智图的 SA 变体文献（[ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0020025511002799)）支持"初版手工图当退火起点"的做法——即**不必从零寻优，可以从现 2.3 版 layout 热启动**。

---

## 2. 对比矩阵（方法 × 三维度）

实现成本指在**本 Python 管线**的落地难度；衔接点均以"最终写 layout.json 绝对坐标、render.py 尽量不动、validate_sheet.py 作验收"为基准。

| 方法 | 实现成本（Python 管线） | 对方向惯例与母线语义的表达力 | 与 render.py 管线的衔接点 |
|---|---|---|---|
| **A1 ELK layered**（elkjs Node 桥） | 中：Node 子进程 + JSON 图转换器；无 pip 原生绑定 | 中弱：端口/层/层内位置可钉（FIXED_POS 等），但**母线非原生概念**（细长节点或折叠边模拟）；方向惯例只能靠 direction+约束近似；折返/绕行比不在其代价内 | 输出 JSON 坐标→转写 layout.json 的 nodes（母线/走廊需从其边路由反推）；route() 可整体弃用（它自带正交路由）或仅取其节点坐标；B2/B3 有超预算风险，需多轮重跑调参 |
| **A2 Graphviz dot** | 低：pip + 系统二进制 | 弱：`splines=ortho` **不支持端口**、边标签失效（官方确认）；方向惯例靠不可见节点 hack，母线无从表达 | 只能当基线对照：出 dot 再解析坐标；正交质量不达标时 route() 要全部接手 |
| **A3 Weave 式组合**（分层引擎+领域模式+往返验证） | 中高：等于 A1 加模式层与验证器 | 中：主图交引擎，母线支路/吸油走廊可作"放置模式"绕开引擎；连通性有机器证书（本案等价物：拓扑追溯一致 + B1–B7 面板） | 同 A1；其"模式绕开引擎直摆"恰是 render.py 现状（route 走廊）的升级版，衔接自然 |
| **B1 单线图规则式分层（自研处方）** | 中低：纯 Python 规则引擎；规则可直接翻译 rendering-rules 方向惯例与 layout 注释里的既有经验 | **最强**：母线是一等公民（x 承重、长度=所挂支路宽度）；role→朝向/行位就是方向惯例本身（油箱行/泵行/用户缘）；交叉规避写进排列规则 | 直接产出 nodes+buses+lanes/vlanes 三组坐标写 layout.json；route() 原样保留做走线；validate_sheet.py 验收——**零管线改动** |
| **B2 SRR 通道分配（借框架，不引库）** | 中：只借其"轴+街道+轨道"模型与折返度量自实现 | 强（针对母线分支）：每条母线的上下支路轨道分配、折返最小化与 B2 同源；但只解"接母线的走廊"，不解全局放置 | 产 lanes/vlanes 建议值供 route() 消费（现有机制直接吃这两个数组）；节点放置需与其他方法组合 |
| **C1 kiwisolver（Cassowary/Kiwi）** | 低：pip 即装（matplotlib 同源依赖），约束式声明代码量小 | 中：线性结构约束全可表达（母线 x 固定、分行、B5 盒距、B6 走廊、方向惯例作弱约束偏好）；**非线性图面量（交叉/折返/绕行）不在模型内** | 解出节点 x/y 绝对坐标写 layout.json；布线交现有 route()；B1–B7 由 validate_sheet 验收，不满足再回补约束——**零管线改动** |
| **C2 WebCola / Adaptagrams** | 中高：JS/C++ 无维护 Python 绑定，需 Node 桥或自封装 | 中强：分离/对齐/分组约束第一类支持；正交路由（Adaptagrams topology）存在但与本案走廊惯例（lanes/vlanes）不对口 | 需自建桥输出坐标；其余同 C1。绑定成本是其主要门槛 |
| **D1/D2 元启发 SA（B1–B7 为能量函数）** | 中：纯 Python 自实现；cost 直接复用 validate_sheet 的度量代码；邻域/降温设计是主要工作量 | **最强（以验收口径论）**：方向惯例编码为硬约束（不可行动作），B1–B7 原样当目标——优化目标与验收标准零错位 | 输出坐标写 layout.json；与任何"结构合法解"的生成器（规则式/约束式）组合成"生成+微调"两段；可从现 2.3 手工图热启动（心智图保持先例） |

---

## 3. 落地建议排序（供「布局机制选型原型」票参考，不定案）

**结论：建议后续原型票做两条路线的 A/B 对标，元启发作叠加层而非独立路线。**

**路线 1（首选）：母线驱动的规则式分层，自研（B1 处方 + B2 通道模型）。**
- 理由：变电站单线图与本案同构度最高（竖直/水平汇流条 + role 定朝向 + 母线承重），其"规则式分层启发"在 799 站真实电网规模上验证过 95%+ 良好（[arXiv 1903.09495](https://arxiv.org/abs/1903.09495)）；方向惯例与母线语义被表达为**规则本身**而非软偏好，这是所有通用图布局库都给不了的；纯 Python、零新增依赖、不动 render.py 的 route()——实现成本与管线风险都最低；B1–B7 中可规则化的项（交叉恒 0 靠排列、折返靠 SRR 式走廊分配、盒距靠行距常量）在生成端就内置。
- 风险：规则工程量与泛化性——1# 拓扑模式要人工归约为"行/朝向/走廊"处方，新拓扑模式（如未来 PTU、系统溢流阀入图）可能触发规则缺口；产出质量强依赖处方质量，需要 2–3 轮迭代。
- 判据建议：以 1# 系统为基准重跑，B1–B7 实测对标现 2.3 手工图（B3 油箱回油线绕行比 2.373 那类存量超限是否被解掉是亮点观察点）。

**路线 2（次选/互补）：kiwisolver 声明式约束 + 现有 route() + B1–B7 校核闭环。**
- 理由：kiwisolver 是 matplotlib 同源依赖、pip 即装、API 极小（[文档](https://kiwisolver.readthedocs.io/)），是全部候选里**实现成本下限最低**的；"母线 x 固定、元件分行、B5/B6 间距"恰好全是线性约束，方向惯例可作弱约束分级表达；与现有 route() 天然分工——解算器管放、route() 管线；不满足处回补约束即可迭代。
- 风险：交叉/折返/绕行比是非线性图面量，解算器不管——B1（交叉恒 0）只能靠约束布局间接保证（分行+走廊隔离），若 route() 评分最优解仍交叉，需要叠一层走廊重排；弱约束权重调节有试错成本。
- 与路线 1 的关系：两者产出物完全同形（layout.json），可同票对比、甚至混搭（规则式定拓扑行位、约束式微调坐标）。

**叠加层（两路线共享）：SA 以 B1–B7 为能量函数做局部寻优（D1/D2）。**
- 理由：Davidson–Harel 先例证明"美学度量进能量函数"可行（[ACM TOG 1996](https://dl.acm.org/doi/pdf/10.1145/234535.234538)），本案 B1–B7 已有确定性测量代码，cost 实现近乎零成本；TimberWolf 先例（[Semantic Scholar](https://www.semanticscholar.org/paper/The-TimberWolf-placement-and-routing-package-Sechen-Sangiovanni-Vincentelli/6be68c9a463f03b3e865086680d01b00d08d956e)）与 14 节点的小规模说明退火在这个量级完全可行；现 2.3 手工图可当热启动解。
- 风险与定位：能量函数权重工程量真实存在（igraph 文档直言 DH 函数难参数化）；不建议作独立路线从零寻优——方向惯例用硬约束编码后搜索空间已很小，规则式/约束式的结构化解更可解释、更可控。它真正的归属是地图上「布局器与构图预算的闭环」那条未立票事项——**本次调研确实为其提供了可行路径证据，但该票仍应等选型原型出结论后再立**。

**不建议作为正式方案：**
- Graphviz dot：`splines=ortho` 不支持端口是官方确认的硬边界（[issue #1415](https://gitlab.com/graphviz/graphviz/-/issues/1415)），与"端口 role 定线型、锚点必须精确"的核心需求正面冲突，只配当对照基线。
- WebCola/Adaptagrams：约束表达力不差，但无维护 Python 绑定，桥接成本高于 kiwisolver 且后者已覆盖本案所需约束类型；保持观察即可。

**给选型原型票的建议度量**：B1–B7 实测面板（validate_sheet 现成）+ 返工轮数（对照 revision_log 1.0→2.3 的四轮）+ 新增依赖数 + 规则/约束代码量；外加"新拓扑模式下规则是否要重写"的泛化性检查单。

---

## 4. 来源汇总

- ELK layered 官方参考：https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html
- ELK 论文（arXiv 2311.00533）：https://arxiv.org/pdf/2311.00533
- ELK layerConstraint：https://eclipse.dev/elk/reference/options/org-eclipse-elk-layered-layering-layerConstraint.html
- ELK positionChoiceConstraint：https://eclipse.dev/elk/reference/options/org-eclipse-elk-layered-crossingMinimization-positionChoiceConstraint.html
- ELK PortConstraints：https://eclipse.dev/elk/reference/options/org-eclipse-elk-portConstraints.html
- ELK 约束模型博客：https://eclipse.dev/elk/blog/posts/2023/23-01-09-constraining-the-model.html
- elkjs：https://github.com/kieler/elkjs
- ELK dot 重实现：https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-graphviz-dot.html
- Graphviz ortho 不支持端口（官方 issue #1415）：https://gitlab.com/graphviz/graphviz/-/issues/1415
- Graphviz 论坛：ortho 与端口：https://forum.graphviz.org/t/regarding-graphvizs-orthogonal-edge-routing/1889
- Graphviz 论坛：不可见节点+group 伪造正交：https://forum.graphviz.org/t/graph-with-orthogonal-edges/2362
- Weave：Verified Netlist-to-Schematic Conversion via Layered Graph Layout：https://arxiv.org/html/2607.03835v1
- 变电站单线图自动生成（arXiv 1903.09495）：https://arxiv.org/abs/1903.09495
- 最小折返单行布线（IEEE）：https://ieeexplore.ieee.org/iel2/640/5935/00230022.pdf
- 单行布线术语图示：https://www.researchgate.net/figure/Terminologies-in-the-single-row-routing-problem_fig1_257797430
- 单行布线 NP-complete 引述：https://www.ukm.my/jsm/pdf_files/SM-PDF-43-8-2014/19%20Ser%20Lee%20Loh.pdf
- 三维线束自动展平：https://www.researchgate.net/publication/259266510_Automatic_flattening_of_three-dimensional_wiring_harnesses_for_manufacturing
- Zuken E3.formboard（线束打包算法）：https://www.zuken.com/en/product/e3series/wire-harness-design-and-manufacturing-ecosystem/
- Siemens 线束展平：https://www.siemens.com/en-us/products/designcenter/cad-software/electronic-electrical-cad/wire-harness-design/
- 平面线束布局优化框架（索引）：https://ouci.dntb.gov.ua/en/works/7AYYmak7/
- ASME 液压元件约束自动布局（原文付费墙，403 未读到摘要）：https://asmedigitalcollection.asme.org/mechanicaldesign/article/147/5/051701/1206705/Automated-Layout-Design-of-Hydraulic-Components
- GTK 博客：Cassowary 约束布局：https://blogs.gnome.org/gtk/2019/07/02/constraint-layouts/
- Kiwi（C++ Cassowary）：https://github.com/nucleic/kiwi
- kiwisolver（Python 绑定）：https://kiwisolver.readthedocs.io/ ｜ https://pypi.org/project/kiwisolver/
- Adaptagrams：https://www.adaptagrams.org/ ｜ libcola：https://www.adaptagrams.org/documentation/libcola.html ｜ GitHub：https://github.com/mjwybrow/adaptagrams
- WebCola：https://ialab.it.monash.edu/webcola/ ｜ SetCoLa：https://github.com/uwdata/setcola
- 工程图约束布局论文：https://www.researchgate.net/publication/220053960_Interactive_Constraint-based_Layout_of_Engineering_Diagrams
- Davidson & Harel 1996（ACM TOG）：https://dl.acm.org/doi/pdf/10.1145/234535.234538
- igraph layout_with_dh 文档：https://igraph.org/r/html/1.3.5/layout_with_dh.html
- TimberWolf：https://www.researchgate.net/publication/2981545_The_Timber_Wolf_Placement_and_Routing_Package ｜ https://www.semanticscholar.org/paper/The-TimberWolf-placement-and-routing-package-Sechen-Sangiovanni-Vincentelli/6be68c9a463f03b3e865086680d01b00d08d956e
- 心智图保持 SA：https://www.sciencedirect.com/science/article/abs/pii/S0020025511002799

**未找到可靠来源的断言（如实声明）**：
- "液压原理图 2D 图面自动布局"的直接公开文献——未找到（最接近的 ASME 论文偏物理封装/流道，且摘要不可得）。
- 线束领域"原理图 lane/channel 分配"的可靠公开方法——未找到（现有的是物理展平/打包）。
