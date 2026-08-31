# 液压原理图组件与 JSON 生成技术规范

| 项目 | 内容 |
|---|---|
| 文档编号 | COMAC-HYD-SCH-SPEC-001 |
| 版本 | 2.1-draft |
| 状态 | 项目工作基线 |
| 适用目录 | `D:\File\COMAC\组件库\已标注` |
| 适用对象 | SVG 组件库、组件目录、液压系统 JSON、原理图生成器、校核器、CATIA 数据适配器 |

> 本规范用于建立可重复、可追溯、失败关闭的液压原理图生成链路。它不替代企业批准的设计规范、标准图册、适航要求或工程签署。未完成工程审查的输出必须标记为 `CONCEPT - NOT FOR DESIGN RELEASE`。

## 目录

1. [目的](#1-目的)
2. [规范用语](#2-规范用语)
3. [总体原则与事实源](#3-总体原则与事实源)
4. [文件与目录约定](#4-文件与目录约定)
5. [命名规则](#5-命名规则)
6. [SVG 组件标准](#6-svg-组件标准)
7. [组件目录标准](#7-组件目录标准)
8. [液压系统 JSON 标准](#8-液压系统-json-标准)
9. [端口与连接语义](#9-端口与连接语义)
10. [布局与渲染标准](#10-布局与渲染标准)
11. [校核与失败行为](#11-校核与失败行为)
12. [CATIA 数据接入标准](#12-catia-数据接入标准)
13. [输出包与追溯](#13-输出包与追溯)
14. [验收准则](#14-验收准则)
15. [变更控制](#15-变更控制)
16. [现有样例迁移要求](#16-现有样例迁移要求)

## 1. 目的

本规范统一以下接口：

- SVG 符号如何声明组件身份和端口锚点；
- 组件目录如何定义液压语义、允许状态和 SVG 映射；
- 系统 JSON 如何定义实例、三通、连接、流向、介质和来源；
- 生成器如何完成布局、坐标变换、布线和输出追溯；
- 校核器如何阻断缺失、冲突、歧义和读取失败；
- CATIA 数据如何经过抽取、归一化和人工确认后进入系统模型。

完成标准：任一组件、端口、连接和输出图元均可从生成结果追溯到唯一输入定义。

## 2. 规范用语

- **必须**：违反即产生 `ERROR`，禁止生成正式原理图。
- **应**：违反产生 `WARNING`；允许生成概念图，但必须在报告中披露。
- **可**：可选能力，不影响最低合规性。
- **事实源**：某类信息唯一允许被维护的权威文件。
- **派生产物**：必须由事实源重新生成，不允许作为反向修改事实源的依据。
- **失败关闭**：读取、映射或校核不确定时停止并报告，不输出貌似成功的空图或缺项图。

## 3. 总体原则与事实源

### 3.1 分层事实源

| 信息 | 唯一事实源 | 派生产物 |
|---|---|---|
| 组件类型、端口、内部状态、符号映射 | `component-catalog.json` | SVG 端口检查结果、组件表 |
| 工程师系统意图 | `system-description.md` 与审查结论 | 语义声明、审查卡、L2 草案 |
| 已确认系统实例、连接、仪表关系、工作模式 | `hydraulic-system.json` | 原理图、连接表、状态矩阵 |
| CATIA 原始读取证据 | `catia-snapshot.json` | 映射候选、差异报告 |
| 图形布局约束 | 工程师批准的 `layout-rules.json` | AI 布局候选 |
| 图形布局结果 | 校核通过的 `layout.json` | SVG、Draw.io、PDF |
| 生成身份与证据 | `render-manifest.json` | 交付包摘要 |

### 3.2 强制原则

1. 系统 JSON 必须表达液压拓扑，不得只表达像素坐标。
2. SVG 必须表达符号外观和端口锚点，不得私自定义系统连接事实。
3. 生成器必须确定性处理相同输入；相同版本、配置和输入哈希必须得到相同拓扑结果。
4. 数值必须同时包含值、单位和来源；不允许静默补单位。
5. 未知值必须显式表示为 `unknown` 或省略可选字段；不允许把非法值转换为 `false`、`0` 或空集合。
6. 自动校核通过仅表示模型与当前规则一致，不表示飞机级工程正确或获得设计批准。
7. 组件方向、位置和走线属于布局决策；AI 必须在 `layout-rules.json` 约束内生成候选方案，确定性程序必须执行坐标变换、布线和校核。
8. 工程师负责批准布局规则和例外，不负责逐个指定普通组件的方向和坐标。
9. 工程师可使用自然语言描述系统；AI 只能把原文和受控目录规则编译为可审查草案，未确认的语义必须显式标为待决，不能静默补全。

## 4. 文件与目录约定

推荐结构：

```text
hydraulic-schematic-library/
├── component-catalog.json
├── hydraulic-system.json
├── inputs/
│   └── system-description.md
├── reviews/
│   └── connectivity-review-card.md
├── layout-rules.json
├── layout.json
├── symbols/
│   ├── priority-valve.svg
│   ├── bootstrap-reservoir.svg
│   └── hydro-pneumatic-accumulator.svg
├── schemas/
│   ├── component-catalog.schema.json
│   └── hydraulic-system.schema.json
├── outputs/
│   ├── schematic.svg
│   ├── schematic.drawio
│   ├── connectivity.csv
│   ├── validation-report.json
│   └── render-manifest.json
└── snapshots/
    └── catia-snapshot.json
```

要求：

- JSON、CSV、XML 和 SVG 必须使用 UTF-8。
- 文件名应使用小写字母、数字和连字符；不得依靠本机绝对路径完成组件引用。
- 正式交付的 SVG 必须自包含；允许另行生成使用外部 SVG 引用的调试版本。
- 中间文件和输出文件不得覆盖组件库事实源。

## 5. 命名规则

### 5.1 类型与实例

| 对象 | 格式 | 示例 |
|---|---|---|
| 组件类型 | 小写蛇形命名 | `priority_valve` |
| 目录端口 ID | 小写蛇形命名 | `high_pressure_in` |
| SVG 元素 ID | `port-` + 连字符命名 | `port-high-pressure-in` |
| 组件实例 ID | 大写前缀 + 三位流水号 | `PV-001` |
| 连接 ID | `C-` + 三位流水号 | `C-001` |
| 三通 ID | `J-` + 三位流水号 | `J-001` |
| 系统 ID | 项目约定的稳定 ID | `HYD-A` |

### 5.2 稳定性

- ID 必须在重排版、重命名显示标题和重复生成后保持稳定。
- 显示名称可修改，稳定 ID 不得随显示名称变化。
- 删除的已发布 ID 不得重新分配给不同对象。
- 组件类型、端口 ID 和枚举值必须区分大小写并按本规范校验。

## 6. SVG 组件标准

### 6.1 根元素

每个组件 SVG 必须：

- 包含 `viewBox`；
- 具有唯一的根级 `data-component-type`；
- 使用可编辑矢量图元；
- 保持未旋转的目录基准方向；
- 不包含重复 `id`；
- 不将红色端口圆点作为正式图形的一部分；端口辅助标记应可由样式隐藏。

推荐根元素：

```xml
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 324 180"
     data-component-type="priority_valve"
     data-symbol-version="1.0">
```

### 6.2 端口组

所有可连接端口必须放在唯一的 `connection-points` 组内（示例与 6.3.1 模板同款：红点 r=2 仅作辅助标记，不随正式图出图）：

```xml
<g id="connection-points" fill="#ff0000">
  <circle id="port-high-pressure-in"
          cx="0" cy="63" r="2"
          data-port-id="high_pressure_in"
          data-medium="hydraulic"
          data-port-role="pressure"
          data-flow-capability="in"
          data-anchor-direction="left" />
</g>
```

每个端口必须包含：

- 唯一 `id`；
- 与组件目录一致的 `data-port-id`；
- `cx`、`cy` 本地坐标；
- `data-medium`；
- `data-port-role`；
- `data-flow-capability`；
- `data-anchor-direction`。

### 6.3 端口枚举

允许的 `data-medium`：

```text
hydraulic
pneumatic
electrical
mechanical
```

液压端口的基础 `data-port-role`：

```text
pressure
return
suction
case_drain
work
pilot_pressure
pilot_drain
measurement
service
```

允许的 `data-flow-capability`：

```text
in
out
bidirectional
none
```

允许的 `data-anchor-direction`：

```text
left
right
up
down
```

### 6.3.1 符号模板

新建组件 SVG 必须由本模板起稿。模板本身即合规最小件，逐项替换尖括号内容。

同一模板以可解析、可复制的物理文件维护在组件库规范源下：`已标注/_template.svg`（占位符写作 `{{...}}`，本节条文修订时须同步改它；`check_symbol.py --all` 跳过 `_` 前缀基础设施件，本模板自身也应通过 `check_symbol.py _template.svg` 校核）。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"
     width="80" height="80"
     data-component-type="<目录中的 component_type>"
     data-symbol-version="1.0"
     data-symbol-form="stroke_geometry"
     data-symbol-status="<draft | provisional | annotated>"
     data-symbol-source-ref="<标准页条款号，或 NONE_NO_STANDARD_PAGE_SUPPLIED>">

  <!-- 依据：<符号几何来源。实测坐标、标准页条款、或"由通用符号族构造"。>
       未确认项：<逐条列出，不得省略。> -->

  <g id="symbol" fill="none" stroke="#000000" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round">
    <!-- 符号几何。只用 line / circle / rect / path 描边，不用填充轮廓。 -->
  </g>

  <g id="connection-points" fill="#ff0000">
    <circle id="port-<端口名>" cx="0" cy="40" r="2"
            data-port-id="<目录 ports[].id>" data-medium="hydraulic"
            data-port-role="pressure" data-flow-capability="in"
            data-anchor-direction="left"/>
  </g>
</svg>
```

### 6.3.2 模板的强制约束

以下五条是既有实践中已出错、而 6.1 至 6.3 未能拦住的，故明文规定。

**一、几何必须是描边，不得是填充轮廓。** `data-symbol-form` 只允许 `stroke_geometry`。potrace 一类工具描摹位图产生的 `fill="#000000" stroke="none"` 路径不得入库：其"端口坐标"是轮廓点而非几何端点，偏差为半个线宽；线宽由轮廓形状隐含决定，无法响应 10.7 要求的 `1.5T` 装配边界线宽；符号内部机构无法从轮廓可靠反推。既有描摹件必须按 6.5 链路重绘，不得原样标注端口后入库。

**二、`width`/`height` 数值必须与 `viewBox` 后两位一致，且不带单位。** 禁止 `width="80.000000pt"` 配 `viewBox="0 0 80 81"` 这类 pt/px 混用——渲染器按 `viewBox` 取端口坐标、按 `width` 缩放符号，两者比例不一致时端口与图形分离。Inkscape 另存前须在文档属性中将显示单位与缩放设为 px、1:1，并选 Plain SVG。

**三、端口坐标必须落在 `viewBox` 边界上，不得在内部。** 端口是接线点，布局器自该点起始正交走线；坐标在图形内部时走线穿过符号本体。符号本体与 `viewBox` 边界之间须留出引线段。

**四、`data-symbol-status` 非 `annotated` 者一律不得用于正式出图。** 取值含义：`draft` 几何未完成；`provisional` 几何完成但无标准页依据（构造自通用符号族）；`annotated` 几何与端口均已核对标准页。渲染器必须在图签栏列出全部非 `annotated` 符号的数量与实例名。

**五、无标准页依据时，不得为求图面完整而编造符号内部机构。** 缺依据者按此处理：只取通用符号族的最小特征（如泵取"圆加排出三角"）；不得补充需工程判断才能确定的细节（两位阀的通断格需知失电位，变量泵斜箭头需知是否变量）；全部省略与构造写入根元素注释的"未确认项"，并在对应 L0 文件的 `unknown` 中登记。

违反第五条的后果是具体的：符号把"我不知道"渲染成"我知道且是这样"，而读图人无法区分二者。

### 6.3.3 镜像与旋转

`allow_mirror` 为 `true` 的符号被镜像后，端口的 `data-anchor-direction` 必须同步取反（`left` ↔ `right`，`up` ↔ `down`）。否则布局器的出线方向与实际端口位置相反，走线会越过端口再折回，在图上留下会被读作支路的多余线头。

带方向语义的符号一律 `allow_mirror: false`：单向阀、泵、溢流阀的符号本身指示允许通流方向，镜像即反转该方向。滤类符号无方向语义，可镜像，但镜像后进出口互换，与流向箭头并列时读图人会先信符号朝向，故优先用重排位置而非镜像来适配走线。

### 6.4 SVG 完成标准

一个 SVG 组件完成的条件：

1. XML 可解析；
2. 所有 ID 唯一；
3. `data-component-type` 能在组件目录中唯一解析；
4. 组件目录中的每个端口恰好映射到一个 SVG 端口；
5. SVG 不存在组件目录未声明的正式端口；
6. 端口坐标落在 `viewBox` 内；
7. 隐藏端口标记后符号仍保持完整可读；
8. `data-symbol-form` 为 `stroke_geometry`，`symbol` 组内无 `fill` 非 `none` 的轮廓路径（实心箭头、三角等指示性图元除外，须显式 `stroke="none"`）；
9. `width`、`height` 无单位后缀，数值等于 `viewBox` 的第三、四项；
10. 每个端口坐标落在 `viewBox` 的边界线上（`cx` 为 0 或宽度，或 `cy` 为 0 或高度）；
11. `data-symbol-status` 为 `annotated`，且 `data-symbol-source-ref` 已指向具体标准页条款，不为 `NONE_NO_STANDARD_PAGE_SUPPLIED`；
12. 根元素注释的"未确认项"为空，或其每一项均已在引用该符号的 L0 文件 `unknown` 中登记。

第 8 至 12 条可机器校核，应纳入组件入库门禁。第 11 条为正式出图的充分必要条件：不满足时符号仍可参与草图渲染，但渲染器必须按 6.3.2 第四条在图签栏披露。

### 6.5 DWG 转 SVG 与语义补全

DWG 仅提供图形几何，不提供可用于自动组装的液压语义。组件入库必须采用以下受控链路：

```text
DWG → DXF → Plain SVG → 端口语义标注 SVG → 组件目录映射与校核
```

- 转换前应清除图框、尺寸、无关图层和外部参照；转换后应确认单位、比例、线型、文字和块引用的显示结果。
- 正式组件 SVG 应使用可编辑矢量图元和稳定 `viewBox`；不得以位图替代符号几何。
- 转换后的 SVG 必须人工或按受控规则补齐本章规定的 `data-component-type`、唯一端口 ID、端口介质、角色、流向能力和锚点方向。
- 不得从 DWG 几何邻近、文字位置或图层名称自动断言入口、出口或内部通路；无法确认时必须标为 `unknown` 并停止正式入库。
- 批量转换结果只能作为待校核初稿；复杂块、填充、字体和外部参照必须逐项复核。

## 7. 组件目录标准

`component-catalog.json` 是组件类型、端口和符号映射的唯一事实源。最小结构：

```json
{
  "schema_version": "2.0",
  "catalog_id": "comac-hydraulic-components",
  "catalog_revision": "A",
  "components": [
    {
      "component_type": "priority_valve",
      "display_name": "优先阀",
      "symbol": {
        "asset": "symbols/priority-valve.svg",
        "symbol_version": "1.0"
      },
      "ports": [
        {
          "id": "high_pressure_in",
          "svg_element_id": "port-high-pressure-in",
          "medium": "hydraulic",
          "role": "pressure",
          "flow_capability": "in"
        },
        {
          "id": "low_pressure_out",
          "svg_element_id": "port-low-pressure-out",
          "medium": "hydraulic",
          "role": "pressure",
          "flow_capability": "out"
        }
      ],
      "allowed_states": ["normal", "failed"]
    }
  ]
}
```

要求：

- 每个 `component_type` 必须唯一。
- 每个组件内的端口 `id` 和 `svg_element_id` 必须分别唯一。
- `medium`、`role` 和 `flow_capability` 必须与 SVG 标注一致。
- 阀内部通路、正常位和失效位应在组件目录或单独规则库中定义，不得从符号外形临时猜测。
- 组件目录修订必须进入生成身份和输出清单。

### 7.1 总成、功能模块与附件

组件库采用两层建模，避免在系统图阶段由 AI 自由拼装未经批准的附件组合：

- **系统层组件**：对外暴露系统端口和系统功能，例如 `filter_assembly`、`hydro_pneumatic_accumulator`。
- **受控总成模板**：定义总成内部成员及固定内部关系，例如 `return_filter_with_bypass`、`duplex_filter`。模板必须在组件目录或经版本控制的规则库中维护。

油滤及类似总成的附件满足下列任一条件时，必须作为模板内独立子组件建模：存在独立外部管路连接；改变液压拓扑或工作状态；需独立选型、维护、更换或进入 BOM；需单独进行逻辑或安全校核。其余仅影响结构、外观或不可独立维护的元素应保留在总成符号内部。

AI 只可选择已批准的总成模板、连接其外部端口并执行校核；不得自行决定旁通阀、压差指示器、切换阀等附件的组合方式。没有匹配模板时必须报告并等待补充模板或明确连接定义。

## 8. 液压系统 JSON 标准

### 8.1 顶层结构

```json
{
  "schema_version": "1.0",
  "model_kind": "hydraulic_connectivity_graph",
  "system_id": "HYD-DEMO-001",
  "revision": "A",
  "maturity": "concept",
  "catalog": {
    "catalog_id": "comac-hydraulic-components",
    "catalog_revision": "A"
  },
  "default_units": {
    "pressure": "MPa",
    "flow": "L/min"
  },
  "nodes": [],
  "connections": [],
  "assumptions": [],
  "provenance": []
}
```

### 8.2 装配组件

装配必须作为 `nodes` 中 `kind: "component"` 的封装复合组件表达，不得使用独立的顶层 `assemblies` 集合。其成员、内部网络、仪表关系和公开端口都必须位于装配对象内；外部网络只允许连接公开端口。

```json
{
  "id": "ASM-001",
  "kind": "component",
  "component_type": "return_filter_assembly",
  "members": [
    { "id": "F-001", "component_type": "filter" },
    { "id": "BPV-001", "component_type": "bypass_valve" },
    { "id": "DPI-001", "component_type": "differential_pressure_indicator" }
  ],
  "internal_nets": [],
  "instrumentation_relationships": [],
  "published_ports": [],
  "members_removable_in_situ": false,
  "boundary_style": "assembly_enclosure"
}
```

- `members` 是装配本地成员；成员不得作为顶层 `nodes` 重复出现，外部 `nets` 不得直接引用成员 ID。
- `internal_nets` 只表达本地成员端口的流体连通；`instrumentation_relationships` 用“传感器端口 → 内部网络 → 被观测成员端口与位置”表达测量语义。
- `published_ports` 的每个端口必须映射到唯一 `internal_net_id`，并作为该装配唯一允许的外部液压接口。
- 装配组件不得保存 `x`、`y`、宽高、虚线节距或路径等布局信息。
- 公开端口的名称、介质和映射规则必须来自组件目录或受控总成模板；AI 不得为未定义装配自行发明端口。
- `members_removable_in_situ: false` 仅表示成员不可单独现场拆分，不得自动推断整个装配的可更换性。

### 8.2.1 自然语言生成与关系追溯

工程师可以提供自然语言 `system-description.md`。生成器必须先把输入拆解为带稳定 ID 的 `claims`，再依据组件目录编译为 L2 草案；不得直接从自然语言生成 SVG 或绕过语义校核。

```json
{
  "generation": {
    "mode": "natural_language_to_l2_draft",
    "source_document": "system-description.md",
    "review_status": "generated_draft_pending_review",
    "claims": [
      { "id": "CLM-010", "source_text": "压力开关测量单向阀入口侧压力。", "classification": "explicit" }
    ]
  }
}
```

- 每个生成的节点、网络、仪表关系和功能关系必须包含 `source_claim_ids`，以便从 JSON 反查原文或目录推断。
- 压力开关等仪表的 `sensing_branch` 仅表示端口与网络相通；必须另以 `instrumentation_relationships` 说明其测量的成员端口和上游/下游位置。
- 当描述无法区分串联、取压、汇合、机械耦合或图形相邻时，生成器必须产生审查问题和 `needs_engineering_decision`，不得任意选择其中一种关系。
- 审查界面应呈现组件表、网络表、仪表关系表、功能关系表和待决项；工程师应确认表项或用自然语言修正，而不是手工维护每个 JSON `attachment`。

### 8.3 节点

允许的节点类型：

```text
component
junction
external_interface
```

组件节点必须包含：

```json
{
  "id": "PV-001",
  "kind": "component",
  "component_type": "priority_valve",
  "catalog_revision": "A",
  "system_id": "HYD-A",
  "source_ref": "CATIA:INSTANCE-UUID-OR-REQ-ID"
}
```

三通节点必须显式建模；管路视觉交叉不得自动解释为连通：

```json
{
  "id": "J-001",
  "kind": "junction",
  "junction_type": "tee"
}
```

### 8.4 连接

每条连接必须包含：

- 唯一 `id`；
- `medium`；
- `line_type`；
- 两个端点；
- `flow_direction`；
- 可追溯来源或推导状态。

示例：

```json
{
  "id": "C-001",
  "medium": "hydraulic",
  "line_type": "pressure",
  "endpoints": [
    { "node_id": "R-001", "port_id": "reservoir_out" },
    { "node_id": "PV-001", "port_id": "high_pressure_in" }
  ],
  "flow_direction": "endpoint_0_to_endpoint_1",
  "evidence": {
    "status": "explicit",
    "source_ref": "CATIA:ROUTE-UUID"
  }
}
```

数值参数必须使用结构化量值：

```json
{
  "value": 21,
  "unit": "MPa",
  "source_ref": "SYS-REQ-023"
}
```

### 8.5 枚举和空值

允许的 `flow_direction`：

```text
endpoint_0_to_endpoint_1
endpoint_1_to_endpoint_0
bidirectional
none
unknown
```

允许的基础 `line_type`：

```text
pressure
return
suction
case_drain
pilot_pressure
pilot_drain
pneumatic_charge
service
```

`suction` 用于油箱至泵吸入口的吸油管线；它是连接语义，不是独立组件。无法从显式端口或已确认系统定义判断吸油属性时，不得由渲染器猜测为 `suction`。

- `unknown` 必须触发至少一个 `WARNING`；若影响关键拓扑或工作模式，必须升级为 `ERROR`。
- 关键字段不得使用空字符串表示未知。
- 布尔字段仅接受 JSON 原生 `true` 或 `false`。
- 枚举值必须严格匹配，不进行大小写或近似文本纠正。

## 9. 端口与连接语义

### 9.1 引用完整性

每个组件端点必须满足：

```text
node_id 存在
→ node.kind = component
→ component_type 存在于组件目录
→ port_id 存在于该 component_type
→ svg_element_id 在 SVG 中存在且唯一
```

三通节点可省略 `port_id`；其他节点必须按其 schema 提供端口。

### 9.2 兼容性

生成器必须校核：

- 两端介质一致；
- 流向能力兼容；
- 压力、回油、吸油、壳体泄油和先导管路满足规则库；
- 不同压力等级不存在无隔离混接；
- 气动充气端口不得连接液压端口；
- 空间交叉只有在引用同一显式三通节点时才表示连通。

### 9.3 连接置信度

允许的证据状态：

| 状态 | 含义 | 是否可进入正式图 |
|---|---|---:|
| `explicit` | CATIA、需求或人工连接表显式给出 | 是 |
| `confirmed` | 候选连接已经人工确认 | 是 |
| `candidate` | 由端口位置、方向和类型匹配得到 | 否 |
| `proposed` | 仅由几何邻近或模型推断得到 | 否 |
| `rejected` | 已确认不连接 | 否 |

正式图中出现 `candidate` 或 `proposed` 连接必须产生 `ERROR`。

## 10. 布局与渲染标准

### 10.1 AI 布局决策边界

AI 布局规划器负责在工程师批准的规则内决定：

- 组件在画布中的相对区域；
- 组件实例的旋转方向；
- 允许时的镜像方向；
- 主流路方向和支路展开方向；
- 标签位置、管路通道和跨页建议；
- 多个可行方案之间的布局优选。

AI 不得通过旋转或镜像改变：

- 组件实例 ID；
- 端口 ID；
- 端口介质、角色和流向能力；
- 元件内部通路；
- 系统连接拓扑；
- 工作模式和工程结论。

布局决策必须写入独立的 `layout.json`，不得写回 `hydraulic-system.json`。同一拓扑可对应多个布局候选。

### 10.2 布局规则

工程师通过 `layout-rules.json` 定义 AI 的自由边界，而不是逐个放置组件。最小结构：

```json
{
  "schema_version": "1.0",
  "coordinate_system": {
    "x_positive": "right",
    "y_positive": "down",
    "angle_positive": "clockwise",
    "angle_unit": "deg"
  },
  "allowed_rotations_deg": [0, 90, 180, 270],
  "default_allow_mirror": false,
  "hard_constraints": {
    "orthogonal_connections": true,
    "forbid_component_overlap": true,
    "forbid_label_overlap": true,
    "forbid_nonconnecting_line_crossings": true,
    "preserve_topology": true,
    "keep_inside_canvas": true
  },
  "soft_constraints": {
    "prefer_main_flow": "left_to_right",
    "minimize_crossings": true,
    "minimize_total_line_length": true,
    "minimize_bends": true,
    "prefer_labels_horizontal": true
  }
}
```

规则分为：

- **硬约束**：违反即产生 `ERROR`，候选布局不得交付；
- **软约束**：用于候选方案评分和优选，违反不会改变工程拓扑；
- **实例例外**：仅用于必须固定方向、禁止旋转或指定区域的特殊组件。

组件目录可声明：

```json
{
  "component_type": "priority_valve",
  "layout_capabilities": {
    "allowed_rotations_deg": [0, 90, 180, 270],
    "allow_mirror": false,
    "preferred_orientation_deg": 0
  }
}
```

镜像与旋转必须分开管理。镜像可能改变符号手性或阅读含义，只有组件目录明确 `allow_mirror: true` 时 AI 才可选择镜像。

### 10.3 AI 布局结果

AI 选择的候选方案必须结构化输出：

```json
{
  "schema_version": "1.0",
  "layout_id": "LAYOUT-001",
  "candidate_rank": 1,
  "rule_set_id": "LAYOUT-RULES-001",
  "instances": [
    {
      "node_id": "PV-001",
      "x": 420,
      "y": 260,
      "rotation_deg": 90,
      "mirror_x": false,
      "mirror_y": false,
      "rotation_origin": "viewbox_center"
    }
  ],
  "routing_hints": [],
  "score": {
    "crossings": 0,
    "total_line_length": 860,
    "bend_count": 6
  }
}
```

AI 应优先生成多个满足硬约束的候选，再依据软约束评分选择排名最高的方案。工程师可锁定特殊组件或否决布局，但普通情况下无需逐个指定方向。

### 10.4 坐标和方向变换

生成器必须从 SVG 本地端口坐标计算画布坐标：

```text
本地端口坐标
→ 缩放
→ 旋转或镜像
→ 实例平移
→ 画布全局坐标
```

坐标不得通过人工阅读图片后写入连接路径。

SVG 中的 `data-anchor-direction` 表示目录基准方向。组件实例旋转后，确定性渲染器必须同时转换端口坐标和锚点方向。例如顺时针旋转 90°：

```text
right → down
down  → left
left  → up
up    → right
```

旋转完成后必须重新计算组件包围盒、端口全局坐标、标签区域和连接路径。文本标签默认保持水平，除非布局规则明确允许随组件旋转。

### 10.5 布线

- 管路应使用正交走线。
- 三通必须显示实心节点。
- 默认禁止非连通交叉；仅在 `layout-rules.json` 经过批准地允许例外时，才可使用本规范 10.6.3 的跨线表达。
- 布局优化不得改变连接拓扑。
- 自动布局失败时必须报告，不得删除连接以消除拥挤。
- AI 可提出走线通道和方向偏好；确定性布线器必须生成最终路径并验证其与端口锚点匹配。

### 10.6 管线语义和非连通交叉

#### 10.6.1 吸油管线

吸油管定义为：**从油箱吸油口（或油箱内吸油过滤器入口）起，至液压泵吸入口止的全部流道及其连接部件。** 因此，串联在该路径中的防火墙关断活门（FSOV）、吸油过滤器、软管、接头等不终止 `suction` 语义；连接部件上游与下游的管段均必须编译为 `line_type: suction`。例如 `TANK.suction_out → FSOV → EDP.suction` 是一条完整吸油路径，`FSOV.outlet → EDP.suction` 仍是吸油管，不得降级为普通低压线或其他线型。

当连接 `line_type` 为 `suction` 时，渲染器必须以企业批准的吸油管线符号绘制：**连续的 `1.0T` 基础管线，加沿路径周期性重复的五根短斜杠组**。参考金样例中的基础管线不是虚线；禁止用 `stroke-dasharray`、点线或断续线替代。每组必须完整包含五根平行斜杠，不得输出一至四根的残缺组。

`S` 是根据输出比例选择的图纸样式参数（`layout.style.suction_marker_S`），不得写入系统意图 JSON。斜杠几何必须仅由 `S` 推导，不得各自硬编码：

- 单根斜杠相对基线的总高度：`2S`；
- 斜杠与管线基线的锐角：`60°`；
- 同组相邻斜杠中心间距：`1.25S`；
- 相邻斜杠组中心节距：`12.5S`；
- 管段端点到斜杠组最外缘的净空：`4S`；
- 每组斜杠数：固定为 `5`。

当前图纸批准值为 `S=8`，由此得到总高度 `16`、组内间距 `10`、组中心节距 `100`、端部净空 `32`。水平与竖直管段必须使用同一斜杠组随管段方向整体旋转后的几何，不得改变端点、流向或连接拓扑。斜杠与基础管线同为 `1.0T`，且必须随整图缩放；禁止使用 `vector-effect: non-scaling-stroke`。

端部净空 `4S` 只施加在完整吸油路径的真正起止端（油箱吸油口/油箱内吸油过滤器入口与液压泵吸入口）以及管线折角处。FSOV 等串联连接部件的端口边界不是吸油路径终端，不得重新施加 `4S`、重置斜杠组相位或使其下游管段因长度不足而失去吸油标记。

长路径应按可用长度确定性增减斜杠组数量。元件端口到符号轮廓、拐角、三通、跨线桥附近及不足以容纳一组完整斜杠的短段允许不画标记，不构成降级；其他足够长的吸油路径若没有任何完整斜杠组，必须产生 `WARNING`，不得静默退化成普通低压实线。

斜杠组应作为独立图元叠加在连续基线上，不得参与拓扑、交叉或三通判定。布局后必须机器校核：① `.ln-suction` 不含 `stroke-dasharray`；② 每个标记组恰有五根斜杠；③ 斜杠不与元件、文字、三通、跨线桥、图例、图签或装配分组边界重合；④ 同一几何组不得重复叠画；⑤ 实际高度、角度和组内间距与 `S` 派生值一致；⑥ 图例声明的 `S` 与布局参数一致。

#### 10.6.2 管线方向箭头

正式原理图不得由渲染器在管线上叠加流向箭头，不得生成 `.arw` 图元或 `arrows` 图层。路径在系统意图与内部编译层仍保持有向，用于端口能力校核、线型推导和仿真；取消箭头只改变图面表达，不改变拓扑方向。

本条仅约束渲染器新增的管线箭头。组件符号内部的泵排油三角形、单向阀方向特征、油箱运动箭头等属于受控符号几何，必须保留；不得因取消管线箭头而搜索删除符号内部的方向图形。

#### 10.6.3 跨线桥

跨线桥只表示图面相交而系统不连通，不得生成 `junction`、端口或连接记录。渲染器必须按以下顺序判断：

1. 两段线共享同一显式 `junction` 节点时，绘制实心连接点；
2. 两段线不共享拓扑端点时，优先重布线消除交叉；
3. 仅在规则允许且重布线失败时，在其中一条线上绘制跨线拱桥，另一条线保持连续；
4. 跨线拱桥的选择规则必须确定性，例如按连接优先级、线型和稳定 ID 排序。

跨线桥必须仅出现在 `layout.json` 和输出 SVG 中，不能反向修改系统 JSON。

### 10.7 装配虚线边界

`assembly_enclosure` 是 `component_type: "assembly"` 的装配组件图形。它用于边界内成员不可单独现场拆分、且连接符号本身不能清晰表达组件边界的情形。生成器必须先布局成员，再计算成员包围盒并加统一留白后生成虚线矩形；不得把该矩形做成固定尺寸 SVG 组件。

- 虚线边界绘制在成员和管线的底层，不得形成连接点或跨线桥。
- 边界的线宽应为 `1.5T`，其中 `T` 是经批准的图纸基准线宽；虚线节距和留白属于渲染样式参数。
- 管线穿越装配边界仅表示成员对外接口，不表示与边界连接。
- 装配框不得遮挡成员、标签、端口或管线；成员集合变化后必须重新计算边界。

### 10.8 输出追溯

每条语义连接必须在 SVG 中具有唯一追溯组：

```xml
<g id="connection-C-001"
   data-connection-id="C-001"
   data-medium="hydraulic"
   data-line-type="pressure">
  <path d="..." />
</g>
```

每个组件实例必须具有：

```xml
<g id="component-PV-001"
   data-node-id="PV-001"
   data-component-type="priority_valve"
   data-rotation-deg="90"
   data-layout-id="LAYOUT-001">
```

允许一条语义连接包含多个路径段，但所有路径段必须位于同一追溯组内。禁止无法映射到系统 JSON 的匿名正式管路。

### 10.9 输出形态

生成器应至少产生：

- 自包含、可编辑的 `schematic.svg`；
- `connectivity.csv`；
- `validation-report.json`；
- `render-manifest.json`。

可选产生：

- `schematic.drawio`；
- PDF；
- 工作模式流路高亮图；
- 元件表和状态矩阵。

### 10.10 渲染闭环（Loop Engineering）

**首次渲染结果是候选件，不是成品。** 生成器必须把渲染产物送回校核，凭证据而非模型自述判定完成。

参考 `fireworks-tech-graph` 的 Loop Engineering 设计理念，本规范采用其五条原则，并按液压原理图的失效模式重新定义各环节的检查项。

```text
L0 意图
  → 目录解析
  → L2 拓扑编译
  → L4 布局
  → SVG 构建
  → 结构校核（确定性）
  → PNG 回读（感知）
  → 定点修正
  → 已验证的 SVG + 校核报告
```

#### 10.10.1 五条原则

**一、评估而非断言。** 完成状态必须由校核器与渲染证据支撑，不得由生成者声称"图看起来正确"。渲染器必须输出机器可读的 `validation-report.json`，其中每一项判定附带被检对象的坐标或 ID。

**二、确定性检查在先。** XML 结构、端口引用完整性、悬空端口、线型可推导性、网络两端角色兼容性、符号 `data-symbol-status`，全部在视觉判断之前完成。这些检查不需要看图，也不允许跳过。

**三、感知校核在后。** 导出 PNG 回读，检查确定性检查看不见的缺陷：标签互相压盖、走线穿越符号本体、管线越过端口后折返、虚线分组框压住标签、图例遮挡内容、内容被画布边缘裁切。**语法正确不等于图面正确**——这一点在液压原理图上比在一般框图上更严重，因为多余的线头会被读成一条支路。

**四、定点修正。** 每轮只改被诊断出的那几个坐标、标签位置或走廊宽度，改完重跑校核与渲染。不得借修正之机重排全图，否则无法判断是修好了还是换了一批缺陷。

**五、有界收敛。** 感知校核默认最多两轮定点修正。两轮未收敛说明是布局策略问题而非坐标问题，应停止修正、报告未收敛项、请工程师决策。此约束防止无界自编辑。

#### 10.10.2 液压原理图的感知校核项

以下各项确定性检查无法覆盖，必须回读 PNG 判断。括号内为已实际发生过的缺陷。

1. 走线是否穿越符号本体（端口坐标在 `viewBox` 内部时必然发生）；
2. 管线是否越过端口再折返，留下会被读作支路的线头（镜像件的锚点方向未同步取反时发生）；
3. 三通实心点是否画在了母线端点（端点是拐角不是节点，实心点会被读成第三条支路）；
4. 元件标签之间、标签与分组虚线框之间、标签与管线之间是否压盖；
5. 边界接口的说明文字是否被画布边缘裁切；
6. 图例与图签栏是否遮挡图形内容；
7. 符号缩放后内部机构是否仍可辨（非等比缩放会使符号变形）；
8. 流向箭头指向与符号本身的进出口朝向是否一致。

#### 10.10.3 状态报告

渲染完成后必须报告两项状态，缺一不可：

```text
validation: passed | failed
visual_review: passed | failed | skipped (无图像读取能力)
```

运行环境无图像读取能力时，必须显式报 `skipped`，**不得猜测或声称已完成视觉校核**。

`validation` 为 `failed` 时不得进入感知校核——结构错误下的图面判断没有意义。

#### 10.10.4 与失败关闭的关系

本节的闭环不放宽 11.3 的失败关闭规则。`ERROR` 仍然不产出 SVG。闭环处理的是 `WARN` 与感知缺陷：这些不阻止出图，但必须在图签栏披露，并在校核报告中逐条列出。

悬空端口是二者的边界情形：它不阻止渲染，但渲染器必须在图上标红、在图签栏计数、在报告中列名。**静默画出一个未接线的端口，是原理图最严重的失效模式**——读图人无法与"已接好"区分。

## 11. 校核与失败行为

### 11.1 校核级别

| 等级 | 行为 |
|---|---|
| `ERROR` | 停止正式生成；允许生成明确标记的诊断预览 |
| `WARNING` | 允许生成概念图；必须写入报告 |
| `INFO` | 记录优化建议或非阻断信息 |

### 11.2 强制校核

生成前必须完成：

1. JSON Schema 校核；
2. 组件类型和目录版本解析；
3. SVG XML、唯一 ID 和端口坐标校核；
4. 节点、端口、三通和连接引用完整性校核；
5. 介质、角色、流向和压力等级兼容性校核；
6. 悬空必接端口和重复连接校核；
7. 工作模式和元件状态枚举校核；
8. 输出组件、连接和输入模型的一一追溯校核；
9. 标签重叠、元件遮挡、越界和不可辨识交叉的图形校核；
10. 输出清单、输入哈希和生成身份校核。
11. AI 布局是否满足全部硬约束；
12. 旋转后的端口坐标、锚点方向和连接出口方向是否一致；
13. 组件旋转是否属于组件目录允许集合；
14. 镜像是否得到组件目录明确许可；
15. 不同布局候选是否保持相同拓扑哈希。
16. 装配组件的成员引用完整性、层级不重叠性和维护语义校核；
17. 每条 `line_type` 均属于允许枚举，`suction` 连接均采用对应受控渲染样式；
18. 非连通线段交叉均已消除，或存在经批准的跨线桥例外且未产生虚假连接；
19. 每个 `assembly_enclosure` 均由其成员包围盒派生，未遮挡成员、端口、标签或管线。

### 11.3 失败关闭规则

出现以下情况必须停止正式生成：

- 组件目录或系统 JSON 无法解析；
- 关键组件类型未知；
- 端口缺失、重复或存在多个匹配候选；
- CATIA 读取异常或装配树不完整；
- 模型未保存、版本未知或输入哈希无法确定；
- 关键单位、阀状态或流向缺失；
- 连接介质冲突；
- 渲染器未输出系统 JSON 中的全部连接；
- AI 布局违反硬约束或使用不允许的旋转、镜像；
- 旋转后端口坐标、锚点方向或包围盒无法确定；
- 校核器异常退出。

失败报告必须包含阶段、对象 ID、异常上下文和非零状态。空组件列表、空连接列表或空原理图不得作为成功结果。

## 12. CATIA 数据接入标准

CATIA 接入采用：

```text
DISCOVER
→ EXTRACT
→ NORMALIZE
→ MAP
→ REVIEW
→ WAIT_FOR_APPROVAL
→ VALIDATE
→ RENDER
```

### 12.1 CATIA 快照

`catia-snapshot.json` 应包含：

- CATIA 版本和连接方式；
- 文档、保存状态和修订；
- Product 树和稳定实例标识；
- 自定义属性和 Knowledgeware 参数；
- Publication、端口基准和 Routing 对象；
- 提取时间、运行 ID、输入哈希和诊断信息。

### 12.2 语义映射

优先读取显式标注：

```text
HYD_COMPONENT_ID
HYD_COMPONENT_TYPE
HYD_SYSTEM_ID
HYD_PORT_*
HYD_LINE_ID
HYD_LINE_TYPE
HYD_FROM_PORT
HYD_TO_PORT
```

- CATIA 提供组件、端口、管路和空间事实。
- 外部组件目录解释阀内部通路、正常位、失效位、设定值和工作模式。
- 端口位置、方向和类型匹配只能产生 `candidate`。
- 纯几何邻近推断只能产生 `proposed`。
- 未经人工确认的连接不得进入正式系统 JSON。

## 13. 输出包与追溯

`render-manifest.json` 必须记录：

```json
{
  "schema_version": "1.0",
  "run_id": "UUID",
  "generated_at_utc": "2026-08-07T12:00:00Z",
  "generator_version": "0.1.0",
  "system_model_sha256": "...",
  "component_catalog_sha256": "...",
  "catalog_revision": "A",
  "maturity": "concept",
  "validation_status": "passed_with_warnings",
  "outputs": []
}
```

输出包必须能够回答：

- 使用了哪份系统模型；
- 使用了哪个组件目录版本；
- 哪个生成器版本生成；
- 哪些规则通过、警告或失败；
- 每个组件和连接在图中的对应元素；
- 输出是否允许用于设计放行。

## 14. 验收准则

最低验收条件：

1. 相同输入重复生成的拓扑和追溯结果一致；
2. 组件目录中的所有 SVG 均通过唯一 ID 和端口映射校核；
3. 系统 JSON 中每个组件、端口和连接均能唯一解析；
4. 每条连接均在 SVG 中具有 `data-connection-id`；
5. 图中不存在无 JSON 来源的正式管路；
6. 故意注入的重复 ID、错误端口、介质冲突和遗漏连接均被阻断；
7. 未确认连接不会进入正式图；
8. 生成结果通过视觉检查，无标签重叠、元件遮挡和连接歧义；
9. 输出包含运行 ID、输入哈希、目录版本和完整校核报告；
10. 未经工程审批的输出带有 `CONCEPT - NOT FOR DESIGN RELEASE` 标识。
11. 至少对 0°、90°、180°、270° 组件方向完成端口坐标和方向变换测试；
12. AI 生成的多个布局候选均保持相同连接拓扑，最终方案满足全部硬约束。
13. 吸油线、非连通跨线和装配虚线边界均有金样例；跨线桥不产生额外连接或三通。
14. 总成模板、装配成员关系和不可现场拆分语义均可从 JSON 与组件目录追溯。

建议建立以下金样例：

- 油箱—泵—过滤器基本供压回路；
- 优先阀—自增压油箱闭环；
- 带蓄压器液压支路和气动充气支路的混合介质回路；
- 压力口误接气动口；
- 重复 SVG ID；
- JSON 引用不存在端口；
- 三通缺失而管路仅发生视觉交叉；
- 油箱至泵吸入口的吸油管线；
- 不连通的跨线桥，以及与实心三通的对照；
- 带不可现场拆分装配虚线边界的油滤总成；
- JSON 连接存在但渲染输出遗漏。

## 15. 变更控制

- Schema 破坏性变更必须提升主版本号。
- 新增可选字段可提升次版本号。
- 组件端口 ID 变更必须提供迁移映射；已发布 ID 不得静默改义。
- 组件目录、规则库和生成器版本必须分别记录。
- 修改规范时必须同步更新 JSON Schema、金样例和校核测试。
- 规范变更只有在全部金样例通过并完成人工图形复核后才能成为新工作基线。

## 16. 现有样例迁移要求

针对 `D:\File\COMAC\组件库\已标注` 当前样例，进入自动生成器前必须完成：

1. 将系统 JSON 的端口 ID 与组件目录端口 ID 统一；
2. 将优先阀端口重命名为组件自身语义，例如 `high_pressure_in`、`low_pressure_out`；
3. 将蓄压器重复的 `port-pressure-in` 拆分为唯一的液压端口和气动端口 ID；
4. 将充气阀气路端口统一为 `accumulator_gas_out` 或经组件目录明确映射；
5. 新建 `component-catalog.json`，集中保存 SVG、组件类型和端口映射；
6. 由生成器读取 JSON 和 SVG 端口坐标，不再在组合图中人工写入连接坐标；
7. 为每个输出组件和连接添加 `data-node-id`、`data-connection-id`；
8. 确保系统 JSON 的全部连接均被渲染并逐项追溯；
9. 同时输出自包含交付 SVG 和可外链调试 SVG；
10. 在完成上述迁移和校核前，将现有组合图保持为“概念连接与布局测试”。
