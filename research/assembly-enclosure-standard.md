# 调研：装配 Enclosure 标准条文与在库标准素材盘点

> 票：wayfinder research，GitHub issue #34「装配 Enclosure 标准条文与在库标准素材盘点」（地图 #33）。
> 调研日期：2026-09-06。全部结论基于仓库实读（文件 + 行号）与用户提供两张标准页截图；外部核对仅用于出处初判并注明。
> 本文只做调研产出，不改规范源代码，不 git 提交。图形参数的 TBD 项统一留给 grilling 票 #37。

截图口径（本文引用为「条文页」「示例页」）：

- **示例页**（image-1a5e9ff3…png）：滤本体（菱形）+ 压差指示器（上方圆叉两竖管）+ 弹簧单向阀，外围一圈虚线方框，进口侧左端有一枚实心流向箭头。
- **条文页**（image-ad89de53…png）：长虚线矩形，右上角标注 **1.5T**；正文 "Enclosure for an Assembly — Enclosure for an assembly, used to border a group of symbols where the component extremity is not obvious by the connecting symbology. Elements are not removable in situ."

---

## 问题 1：能否定位 "Enclosure for an Assembly" 的条款号/出处

### 1.1 在库标准素材盘点（穷尽式）

| # | 素材 | 位置 | 与 Enclosure 的关系 |
|---|---|---|---|
| 1 | `data-symbol-source-ref="PENDING_STANDARD_ID:clause-6.1.6"` | `.agents/skills/hydraulic-schematic/assets/component-library/filter-line-shutoff-dp.svg:7`、`filter-line-shutoff-stroke.svg:7`（另有 3 处工作区拷贝：`1#系统原理图/symbols/`、`1#系统原理图/proto/frozen/symbols/`） | 在库**唯一的标准页锚点**，且只锚了"带压差指示的油滤截止阀构型"；`PENDING_STANDARD_ID` 是占位符——**标准件名/编号本身从未登记** |
| 2 | catalog note「draft;带压差指示的油滤截止阀(无标准页 clause-6.1.6 构型)」 | skill `assets/component-library/component-catalog.json:656`；`1#系统原理图/component-catalog.json:673` | 同上，clause-6.1.6 仅指滤符号构型，与 Enclosure 无涉 |
| 3 | intent unknown 挂账 `filter-line-shutoff-dp-standard-page-pending` | `1#系统原理图/1#系统.intent.yaml:114`、`proto/frozen/拓扑确认单-1#.md:125`、skill `assets/examples/` 范例 | 证明"标准页依据缺失走挂账披露"是在库既定纪律，Enclosure 可沿用同一机制 |
| 4 | **archive 技术规范 §10.7「装配虚线边界」** | `archive/已标注/液压原理图组件与JSON生成技术规范.md:785-792` | 在库对 Enclosure 语义的**唯一完整条文**（详见 1.2） |
| 5 | archive 技术规范 §8.2「装配组件」 | 同上文件 `:402-429` | `members_removable_in_situ: false`「仅表示成员不可单独现场拆分」（`:429`）——与条文页 "Elements are not removable in situ" **逐义对应**，是条文语义的在库先行翻译 |
| 6 | archive 技术规范 `:267` | potrace 描摹填充件「无法响应 10.7 要求的 1.5T 装配边界线宽」 | 1.5T 数字在库的另一处独立佐证 |
| 7 | archive 技术规范 `:1040-1054`（完成标准/回归样例清单） | 「带不可现场拆分装配虚线边界的油滤总成」 | 基准样例口径里就有一张装配围框图 |
| 8 | 渲染器实现「分组虚线框(技术规范 10.7)」 | skill `scripts/render_l0_sheet.py:803`；CSS `.grp { stroke-dasharray: 8 5; }` + `'gb': 1.5 * T`（`:1066-1067`、`:1108`）；1# 工作区 `render.py` 系副本（CDF 副本 `:806`、`:1069-1070`、`:1111`） | §10.7 的**活实现**：1.5T 线宽 + 长虚线矩形已落地，注释直接引「技术规范 10.7」 |
| 9 | drawing_blockers「无法满足装配边界 1.5T 线宽要求(§10.7)」 | `1#系统原理图/component-catalog.json:1018`（proto/frozen 同） | 工作区 catalog 对 §10.7 的运行时引用 |
| 10 | rendering-rules.md B6「分组虚线框内边距 ≥14 px」 | `.agents/skills/hydraulic-schematic/references/rendering-rules.md:57` | 现行 skill 规范里与围框图形相关的唯一数值条款 |
| 11 | symbol-library.md「虚线框是先导回路或装配界线，不算信封」 | `.agents/skills/hydraulic-schematic/references/symbol-library.md:71` | 现行 skill 规范里「装配界线」一词的唯一出处，一笔带过无参数 |
| 12 | 负例 `negative-group-in-path` | skill `assets/examples/negative-group-in-path.*`；expected-report notes（`:33`）「把虚线框当作可连接对象」是错误思维 | 围框非拓扑对象的在库防线 |

**全仓 `grep -i enclosure` 零命中**（含 md/json/py/yaml/svg）——"Enclosure" 条文原文不在库内；skill 现行 catalog（0.4-draft，22 类型）也没有 assembly/enclosure 组件类型或构件（archive §8.2 的装配组件语义属旧 L2 路线，未迁入现行 intent/layout 数据模型）。

### 1.2 条款号核对的结论

- **在库素材不能给出 "Enclosure for an Assembly" 的条款号。** 唯一被登记的标准页条款号是 clause-6.1.6（滤符号构型），且载体是 `PENDING_STANDARD_ID` 占位符——标准文件名/编号本身就处于「待定」状态。条文页截图同样不带编号，故无从在库内对号。
- **出处外部初判：SAE AS1290A《Graphic Symbols for Aircraft Hydraulic and Pneumatic Systems》**。网络可见的该标准片段与条文页逐词吻合（"1.5 T ENCLOSURE FOR AN ASSEMBLY. USED TO BORDER A GROUP OF SYMBOLS WHERE … ELEMENTS ARE NOT REMOVABLE IN SITU"），且该标准同时定义了另一变体 "…MANIFOLD … WHICH ARE REMOVABLE IN SITU"（可现场拆分的集成块围框）——正好解释条文页为何要强调 not removable in situ。此为外部佐证（置信中），须与用户手持标准页原件核对后才可写死，属 #37 决策。
- **条款号若定，登记方式照在库惯例**：改 `data-symbol-source-ref` 占位符（如 `SAE-AS1290A:clause-<N>`）+ catalog note + intent unknown 撤账，机制现成（素材 #1/#2/#3）。

### 1.3 结论与置信度

- **结论：不能定位条款号**——在库无 Enclosure 条文原文与编号；出处初判 SAE AS1290A（待 #37 与手持原件核对）；在库对该语义的全部规范承载 = archive §10.7/§8.2 + 渲染器 `.grp` 实现 + B6/负例防线，且单源化迁移时 §10.7 条文**未迁入** skill references（rendering-rules.md 现无此条文，属欠账，由本票附录草稿补位）。
- **置信度：高**（「在库不可定位」是穷尽式 grep 结论；「出处=AS1290A」置信中，外部网页佐证非正式文本）。

---

## 问题 2：条文页长虚线框 vs 示例页链式框——同一语义吗，以哪个为准

### 2.1 图上观察

- 条文页：矩形四边为**长虚线**（长划为主、间距均匀），右上角 1.5T。这是定义页的基准图形。
- 示例页：外围框在截图分辨率下观感近**点划/链式线**（长划间夹短划或点）。
- 外部线型背景（供 #37 参考）：ISO 1219-1 口径「同尺寸短划 = 泄油/先导」「**短划+长划混合 = 围框/集成块线**」（LunchBox Sessions）；SAE AS1290A 则区分两种围框线样（assembly 不可拆 1.5T / manifold 可拆另一线样）。

### 2.2 在库其他装配边界约定盘点（并存多套，需收口）

| 约定 | 位置 | 语义 | 与装配围框的区分 |
|---|---|---|---|
| `groups:` 分组虚线框（`.grp`） | intent `groups`（rendering-rules.md:14「布 lane 用分组」）→ render_l0_sheet.py:803-830、CSS `:1066-1067` | **布局抽象**，非部件非拓扑对象 | 实现上直接引用「技术规范 10.7」，1.5T + dasharray 8 5——**当前实现把布 lane 分组与装配围框画成同一个东西** |
| `data-zone` 分区框 | rendering-rules.md:40 | 回路分区（GREEN CIRCUIT 等） | 独立属性承载，语义不同 |
| 信封方框（`data-envelope-class`） | symbol-library.md:60-75，明文「信封方框…非虚线…**虚线框是先导回路或装配界线，不算信封**」（`:71`） | 符号本体（阀/仪表方框） | 线型（实线闭合正方）+ 尺寸基准 80×80 |
| `SIG_SW` 1.2T 虚线信号线 | rendering-rules.md:27 | 指挥/状态信号 | 与装配围框同为虚线，**仅靠线宽 1.2T vs 1.5T 区分** |
| 已裁决先例：自拟 case_drain 虚线撤除 | render_l0_sheet.py:1044-1045「它是我编的非标准约定，**且与 10.7 的装配虚线边界在图上无法区分**」 | 虚线语义占用纪律 | 在库已确认：非标准虚线约定不得与装配围框混用 |
| 负例防线：框不可连接 | negative-group-in-path.expected-report.json:33 | 围框/分组框不是拓扑对象 | 拓扑语义防线 |

### 2.3 rendering-rules.md「10.7 装配虚线边界」提法核实

`rendering-rules.md` 内**没有**「10.7」「装配虚线边界」字样（grep 证据：该文件对「装配/虚线」的命中仅为 SIG_SW 行、B6 行与 extern 注释）。「10.7」实际活在三处：archive 技术规范 §10.7 原文（唯一完整条文）、`render_l0_sheet.py:803/:1045` 代码注释、`1#系统原理图/component-catalog.json:1018` drawing_blockers。**即：单源化（#20/#21）后 §10.7 条文未迁入 skill references，现行规范源缺 Assembly Enclosure 条文**——票 #34 补文即补此欠账。

### 2.4 结论与置信度

- **结论：两图是同一语义（装配围框 Enclosure for an Assembly），以条文页为准**——1.5T 长虚线矩形。理由：①条文页是定义页，示例页是该语义的应用图；②示例内容（滤+压差指示器+弹簧单向阀）是不可现场拆分总成，恰为 "not removable in situ" 的 assembly 语义，不可能落在 AS1290A 的 manifold（可拆）变体上；③在库 §10.7 只定义一种装配虚线边界（1.5T）。示例页的链式观感最可能是印刷/扫描分辨率伪影，**是否标准原件另用短长划混合线样列为 #37 与原件核对项**；在库实现（dasharray 8 5）节距属样式参数（§10.7 明文「虚线节距和留白属于渲染样式参数」），不因之改变。
- **在库无第二种装配边界约定**：groups/zone/信封/信号虚线各司其职且已有区分手段；真正的缺口是「布 lane 分组框」与「装配围框」在实现上同形同参，是否拆分为两个概念（布局分组 vs 装配语义）由 #37 裁决。
- **置信度：中高**（同语义判断有三重依据；链式观感的成因解释无法仅凭截图定谳）。

---

## 问题 3：示例图进口侧流向箭头——标准要求还是示例巧合

### 3.1 V18 原文与上下文（skill `scripts/validate_sheet.py:467-475`）

```python
# ---------- V18 禁止渲染器叠加管线流向箭头 ----------
# 仅禁止 renderer-owned .arw / arrows layer。组件符号内部的泵箭头、
# 单向阀三角形、油箱运动箭头属于受控符号几何,不得删除。
pipeline_arrows = [e for e in root.iter() if e.get('class') == 'arw']
arrow_layers = [e for e in root.iter() if e.get('id') == 'arrows']
if pipeline_arrows or arrow_layers:
    F.append(('V18', '管线方向箭头未取消: arw=%d arrows-layer=%d' ...))
```

判定范围**仅两个渲染器自有标记**：`class="arw"` 的独立箭头 path 与 `id="arrows"` 的整层；符号内部几何（泵箭头、单向阀三角形、油箱运动箭头 `TANK-001__motion-arrow-up`）明确豁免。

### 3.2 证据链

1. **V18 的前史**：`archive/已标注/docs/superpowers/plans/2026-08-10-pipeline-arrows-suction-s.md`——管线箭头层（`.arw`/`arrows` layer）是渲染器早年**自拟**的约定，该计划将其拆除（"Remove renderer-added pipeline flow arrows while preserving component-internal directional symbols"），V18 是防回潮回归闸门。即 V18 不是标准条文的转录，而是「不自拟非标准图元」纪律的执行器。
2. **现行产物零箭头且校核全绿**：`1#系统原理图/CDF-001装配图/case_drain_filter装配图.svg` 与 `1#系统原理图/1#系统原理图.svg` 的 `marker-end` 计数均为 0；CDF `validation-report.json` V18 证据 `pipeline_arrows: 0, arrow_layers: 0`，fail 0。
3. **在库存在另一条合法的流向表达通道**：rendering-rules.md:31「流体边带 `marker-end="url(#ah)"` 箭头，机械边不带」——SysML 链路渲染器在用（`render_aircraft_schematic.py:333` 及多处），L0 链路渲染器未实现（grep 无 marker-end）。**边线 marker-end 与独立箭头层是两种机制，V18 只禁后者。**
4. **条文本身不含箭头要求**：条文页（Enclosure 定义）只字未提流向箭头；示例页的箭头画在进口管线上、指向装配体，属 application example 的流向图解，与吸油斜杠组、图解标签同类——是「示例怎么画」，不是「条文要求画」。
5. **内容冗余性佐证**：流向方向已由 path 顺序（intent paths 的端点次序）、单向阀三角朝向等受控几何承载；再叠一层渲染器箭头属重复编码，且正是当年被拆除的自拟物。

### 3.3 结论与置信度

- **结论：进口侧流向箭头是示例巧合（应用图解），不是 Enclosure 条文或任何在库条文的要求；维持 V18，不开「边界流向指示例外」。** 未来若装配图确需边界流向指示，合法路径是既有受控机制（边线 `marker-end`，与 rendering-rules.md:31 对齐）或符号内几何+图签披露，**而不是**恢复独立 `.arw`/`arrows` 层；是否需要该能力列为 #37 开放项，默认不做。
- **置信度：中高**——「条文无箭头要求」是直接图证；「标准全文是否在别处另有流向箭头条款」未核 AS1290A 正式文本（版权获取受限），不影响维持 V18 的判断。

---

## 附录：rendering-rules.md「Assembly Enclosure」条文草稿

> 拟插入位置：`references/rendering-rules.md`「走线与布置」节之后、「数值构图预算」节之前（或独立成节）。文风按该文件现行条目式写法。**所有 TBD 项待 grilling 票 #37 定**；本节为草稿，是否收录、如何收录由主会话决议。

```markdown
## 装配围框（Assembly Enclosure）

> 出处：标准条文页（措辞与 SAE AS1290A "Enclosure for an Assembly" 一致；
> 标准件名与条款号未登记，沿用 PENDING_STANDARD_ID 挂账，待 #37 定）。
> 语义承接：archive 技术规范 §10.7/§8.2（规范源归档后条文未迁移，本节补位）。

围框用于 border 一组符号：当连接符号本身不足以表达组件边界时使用；
围框内成员不可单独现场拆分（not removable in situ）。
围框是绘图抽象：不是部件、不是拓扑对象，不得作为 path 端点连接
（负例 negative-group-in-path 防线）。

- 生成：先布局成员，再取成员包围盒加统一留白生成矩形；不做成固定尺寸
  SVG 组件；成员集合变化后必须重算。
- 线宽：**1.5T**（T 为经批准的图纸基准线宽）。
- 线型：长虚线。节距属渲染样式参数（现行实现 `stroke-dasharray: 8 5`）。
  [TBD-1：条文页长虚线样 vs 示例页链式观感，与标准原件核对后定；#37]
- 层级：画在成员与管线底层；不得形成连接点、三通或跨线桥。
- 越框规则：管线穿越围框仅表示成员对外接口，不表示与围框连接；
  管线/引线几何不因穿越而改变（线宽仍按压力等级编码，V16 口径）。
- 净空：围框内边距 ≥14 px（B6 同口径）；不得遮挡成员、标签、端口或管线，
  标签净空按 B7。
- 与分组框的关系：现行 `groups:` 分组虚线框与装配围框同形同参。
  [TBD-2：布局分组与装配围框是否拆为两个语义/两种图形，#37]
- 标注：[TBD-3：围框标签文字/位置/装配编号标注方式，#37]
- 流向指示：围框不引入渲染器流向箭头（V18 维持，见调研
  research/assembly-enclosure-standard.md 问题 3）。
  [TBD-4：如工程确认需要边界流向指示，走边线 marker-end 机制并图签披露，#37]
- 校核：成员封闭性走 V8（框内不得圈入非成员）；条文本落地后 V 系列新增
  围框线宽 1.5T 判定。[TBD-5：是否增设专项检查项，#37]
```

---

## 外部核对来源（仅用于出处初判，非正式文本依据）

- [SAE AS1290A 页面（SAE International）](https://www.sae.org/standards/as1290a-graphic-symbols-aircraft-hydraulic-pneumatic-systems)
- [SAE AS1290A 可见片段（Scribd）](https://www.scribd.com/document/626823918/SAE-as-1290A-Hydro-Symbols) —— 含 "1.5 T ENCLOSURE FOR AN ASSEMBLY … NOT REMOVABLE IN SITU" 与 manifold 可拆变体
- [Basic Elements of Schematic Symbols（LunchBox Sessions）](https://www.lunchboxsessions.com/materials/hydraulic-schematic-symbols/basic-elements-of-schematic-symbols-lesson) —— ISO 1219-1 线型口径（短+长划混合 = 围框/集成块线）
- [ANSI Y32.10 Fluid Power Symbols（Advanced Fluid Power 转载 PDF）](https://advancedfluidpowerinc.com/wp-content/uploads/2016/03/Fluid_Power_Symbols.pdf) —— 围框语义同源表述
