# L0 系统意图 YAML 输入规范（v1.0 草案）

| 项目 | 内容 |
|---|---|
| 目的 | 定义工程师手工编写的受控系统意图载体，作为 L2 语义模型的确定性编译输入 |
| 输入 | 一个 `*.intent.yaml` 文件 + 一个固定修订号的 `component-catalog.json` |
| 输出 | 规范化回吐 JSON、L2 草案、审查卡、校核报告 |
| 非目标 | 不描述坐标、走线、图形样式、压力等级、阀设定值、适航结论 |
| 前置依赖 | 本规范在 `component-catalog.json` 具备第 14 章字段前不可实施 |

> 本规范定义载体与编译契约。载体的"受控"由 JSON Schema 与第 15 章校核共同保证，不依赖编写者的纪律。

## 1. 目的与定位

L0 解决一个问题：让工程师用几十行文本表达一个子系统的拓扑意图，编译器确定性地展开为完整 L2，且同一输入永远得到同一输出。

L0 不是自然语言，也不是 L2 的换行格式。三者的差别在于：

| | 自然语言描述 | L0 意图 | L2 语义模型 |
|---|---|---|---|
| 歧义处理 | 由模型推断 | 解析期报错 | 无歧义 |
| 网络 ID | 无 | 由 `@` 命名或派生 | 权威 |
| 端口 | 通常省略 | 可省略，由目录填充并留痕 | 必须完整 |
| 编写者 | 工程师 | 工程师 | 编译器，人不编辑 |
| 可重现性 | 不保证 | 逐字节保证 | 逐字节保证 |

自然语言前端可以存在，但其唯一合法产物是一份 L0 文件，由工程师审查 L0 文本本身，而不是审查模型的推理过程。

## 2. 规范用语

必须、不得表示强制要求；应表示推荐要求，偏离需记录；可表示允许选项。

## 3. 在分层事实源中的位置

```text
L0 系统意图 YAML（人工编写，本规范）
  → 规范化回吐 JSON（编译器输出，审查首屏）
  → L2 语义模型（拓扑事实源）
  → L3 编译连通图（junction 展开）
  → L4 布局
  → L5 SVG / 连接表 / 校核报告
```

L0 是意图证据，L2 是拓扑事实。工程师的修改必须回写 L0，不得直接修改 L2 及其下游产物。L0 与 L2 之间不存在 `claims` 抽取环节，追溯键是 L0 的文件名与行号。

## 4. 解析器约束

L0 的失败模式必须是响亮的。YAML 缩进错误可能解析成功但结构改变，因此解析器必须满足：

1. 采用 **YAML 1.2 core schema**。不得使用 PyYAML 默认加载器（其实现为 YAML 1.1，会将 `no`/`off`/`Y`/`N` 转为布尔，将 `0755` 按八进制读作 493，将 `22:30` 按六十进制读作 1350）。推荐 `ruamel.yaml` 的 1.2 模式。
2. **禁用锚点与别名**。出现 `&` 或 `*` 即为 `ERROR`。别名会使同一网络在两处被引用，形成看似复用实为别名陷阱的结构。
3. **禁用 tab 缩进**，禁用多文档流（`---` 分隔的第二份文档），禁用自定义标签（`!!python/`、`!Ref` 等）。
4. 所有标识符字段在 Schema 中声明为 `type: string`。件号、目录修订、实例 ID 写成裸数字即为 `ERROR`，不得静默转换。
5. 解析后必须立即输出**规范化回吐 JSON**（第 12 章），审查卡首屏展示该 JSON。缩进错位或类型异常在此处暴露。

## 5. 顶层结构

```yaml
l0_version: "1.1"
system: <系统 ID>
catalog: <catalog_id>@<catalog_revision>
maturity: concept | reviewed | released
extern: {}
parts: {}
paths: []
taps: []
relief: []
couple: []
signal: []
groups: []
unknown: []
```

`l0_version`、`system`、`catalog`、`maturity` 为必填。`catalog` 必须钉死到具体修订号，不得使用 `latest` 或省略修订。其余节可缺省，缺省视为空。

**单一平坦命名空间。** `extern` 与 `parts` 中的全部实例处于同一作用域，从系统级外部接口到设备级元件不分层。`paths` 直接连接元件端口，不经中间接口。`groups` 是渲染视图，不构成作用域。

## 6. 封闭词表

L0 的关键字集合是封闭的。出现表外键即为 `ERROR`，解析器不得尝试理解。

### 6.1 结构关键字（13 个）

```text
l0_version  system  catalog  maturity
extern  parts  paths  taps
relief  couple  signal  groups  unknown
```

拓扑平坦，无嵌套作用域，因此不存在"装配内关键字"这一类。

### 6.2 分组键

```text
id  label  members  reason
```

`reason` 取值：

```text
not_field_removable  lru  zone  vendor_supplied
```

### 6.3 外部接口类型

```text
inlet  outlet  return  suction  case_drain  vent  ambient
```

### 6.4 取压位置

```text
upstream  downstream
```

### 6.5 耦合与信号类型

```text
couple:  mechanical_shaft  power_transfer
signal:  electrical_output  electrical_excitation  remote_indication
```

### 6.6 词表扩充规则

新增关键字必须满足全部条件：现有词表确实无法表达；已积累三个以上同类工程需求；`l0_version` 次版本号递增；金样例回归全绿。单次需求一律先进 `unknown` 走人工，不得为其扩词表。

词表规模超过 40 个关键字时，L0 相对手写 JSON 已无可用性优势，应重新评估载体设计而非继续扩充。

## 7. `extern` — 外部接口

```yaml
extern:
  IN-001: inlet
  IN-002: inlet
  OUT-001: outlet
  RET-001: return
```

键为实例 ID，值取自 6.3 词表。编译器为每个外部接口生成 `kind: external_interface` 节点，并按类型确定隐含端口：`inlet` 生成 `out` 端口，`outlet`/`return`/`vent` 生成 `in` 端口，`suction`/`case_drain` 按目录规则确定。

外部接口不得出现在 `parts` 中，也不得作为 `taps` 的传感器。

## 8. `parts` — 组件实例

```yaml
parts:
  PS-001: pressure_switch
  PS-002: pressure_switch
  CV-001: check_valve
  F-001:  filter
```

键为实例 ID，值为 `component_type`，必须能在指定修订的组件目录中唯一解析。目录中不存在该类型即为 `ERROR`，编译器不得推测近似类型。

实例 ID 必须匹配 `^[A-Z]{1,4}-[0-9]{3,4}$`。同一 ID 在整个文件内唯一，包括跨装配。

## 9. `groups` — 渲染分组

拓扑是**平坦的**：从系统级外部接口直到设备级元件，全部实例处于同一命名空间，网络直接连接元件端口。L0 不提供拓扑封装层级。

装配虚线框是**图面识读需求**，不是拓扑构造。它由 `groups` 声明，只影响 L4 布局与 L5 渲染：

```yaml
groups:
  - id: LRU-001
    label: 双入口滤油与泄压组件
    members: [PS-001, PS-002, CV-001, CV-002, F-001, RV-001]
    reason: not_field_removable
```

| 键 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | 分组标识，命名空间与实例 ID 分离，不得与任何实例 ID 相同 |
| `label` | 否 | 图面标注文字 |
| `members` | 是 | 实例 ID 列表，必须已在 `parts` 中声明 |
| `reason` | 是 | `not_field_removable` / `lru` / `zone` / `vendor_supplied` |

### 9.1 分组不做的事

`groups` 严禁产生以下任何一项，违反即为 `ERROR`：

- 不生成节点，不生成端口，不生成公开端口；
- 不切分网络。跨越分组边界的网络仍是**一条**网络，不拆成"内部段 + 外部段 + 端口映射"；
- 不出现在 `paths`、`taps`、`relief`、`couple`、`signal` 的任何位置；
- 不产生 junction 或连接记录（依据现有规范 §10.7：管线穿越装配边界仅表示成员对外接口，不表示与边界连接）。

分组信息写入 L4 `layout.json` 的 `assembly_enclosures`，边界由成员包围盒派生。它不进入 L2 拓扑事实源。

### 9.2 为何不做拓扑封装

封装装配曾被引入，唯一动机是画虚线框。其代价可量化：本规范附带示例中，4 条物理上连续的油路各被公开端口切成两半，13 条网络记录里 8 条是切分产物，实际物理网络只有 5 条。

这构成三个问题：

1. **渲染需求越层进了拓扑。** 违反现有规范 §10.1"布局不得改变 L2 拓扑"——此处是布局需求反向创造了拓扑对象。
2. **连通性查询失真。** 判断 `IN-001` 与 `CV-001.inlet` 是否连通，需跨越 `NET-IN-001 → published_port → ASM-N-P-001` 三跳。压力传播、故障注入、连通性校核全部要实现穿透封装的遍历。
3. **同一物理网络有两个 ID。** 拓扑哈希、追溯、`line_type` 推导都要处理这种分裂。

分组允许重叠与嵌套（同一元件可属于多个分组），因为它只是视图。拓扑封装做不到这一点。

### 9.3 何时确实需要拓扑封装

仅当满足以下全部条件时，才应考虑真正的封装层级：内部构造对本图层无关且不需渲染；对外接口是受控接口定义的一部分；该总成在多个系统中作为整体复用。

典型例子是外购作动器或成套液压包——图上只画一个方框和几个接口。本规范 v1.1 不支持该场景，需要时应引入独立的**子系统引用**机制（引用另一个 L0 文件的接口，而非在本文件内嵌套），届时递增主版本。

不可现场拆分不是封装的理由，它只是虚线框的理由。

## 10. `paths` — 流体路径

`paths` 是 L0 的核心节。每条 path 是一个有序序列，相邻两项之间生成一个网络。路径从系统级接口直达设备级元件端口，不经任何中间接口。

```yaml
paths:
  - [IN-001, CV-001, "@MERGE"]
  - [IN-002, CV-002, "@MERGE"]
  - ["@MERGE", F-001, OUT-001]
```

### 10.1 序列项的三种形式

| 形式 | 例 | 含义 |
|---|---|---|
| 实例 ID | `CV-001`、`IN-001` | 串接该组件，进出端口由目录或 `extern` 类型填充 |
| 显式端口 | `CV-001.outlet` | 串接并指定端口 |
| 命名网络 | `"@MERGE"` | 汇合点或分支点 |

分组 ID 不是合法序列项（第 9.1 条）。

### 10.2 端口省略与目录填充

序列项写作裸实例 ID 时，编译器从目录取该类型的 `main_path` 默认进出端口对。填充结果必须写入 L2 的 `catalog_inference`，包含实例 ID、填充的端口 ID、目录修订与 L0 行号。

目录中该类型无唯一 `main_path` 端口对（例如三口以上阀、方向阀）时为 `ERROR`，必须由工程师写显式端口。编译器不得选择第一个候选。

### 10.3 命名网络 `@`

以 `@` 前缀的标识符是网络名，不是组件。同名 `@` 在多条 path 中出现即表示这些 path 在此汇合或分支：

```yaml
paths:
  - [IN-001, CV-001, "@MERGE"]     # CV-001.outlet 挂到 @MERGE
  - [IN-002, CV-002, "@MERGE"]     # CV-002.outlet 挂到 @MERGE
  - ["@MERGE", F-001, OUT-001]     # F-001.inlet 挂到 @MERGE
```

三个端口进入同一网络，L3 展开为一个 tee junction。`@` 网络名在文件内必须至少出现两次，仅出现一次即为悬空网络 `ERROR`。

YAML 中 `@` 开头的裸标量在部分实现中为保留字符，因此 `@` 项必须加引号。

### 10.4 线型推导

网络 `line_type` 由两端端口的目录 `role` 推导：两端均为 `pressure` 得 `pressure`，含 `return` 得 `return`，含 `suction` 得 `suction`。两端 role 冲突（如 `pressure` 直连 `case_drain`）为 `ERROR`。

### 10.5 禁止事项

- path 中不得出现目录 `connection_role` 为 `sensing_only` 的组件（压力开关、温度传感器等）。此类组件只能出现在 `taps`。违反即为 `ERROR`，这是 L0 相对自然语言的主要防线。
- 同一实例的同一端口不得在两条 path 中被隐含填充为不同网络。
- path 长度必须大于等于 2。

## 11. `taps`、`relief`、`couple`、`signal` — 派生关系

这四节的共同设计意图：一行同时产出连通事实与关系语义，使现有规范 §3 所要求的"两段缺一不可"在语法上不可能写漏。

### 11.1 `taps` — 取压/测量

```yaml
taps:
  - {sensor: PS-001, at: CV-001.inlet, position: upstream}
```

单行产出两项：

1. `PS-001.pressure_sense` 以 `role: sensing_branch` 挂入 `CV-001.inlet` 所在网络；
2. 一条 `instrumentation_relationships` 记录，含 `via_internal_net_id` 与 `observed_target`。

`at` 必须是显式的 `<实例>.<端口>`，不得只写实例 ID——一个组件有多个端口时测点不可推测。`at` 所指端口必须已被某条 path 纳入网络，否则为 `ERROR`（取压点不能悬空）。

传感器端口由目录的 `measurement` role 端口填充；该类型有多个测量端口时必须显式写 `sensor: PS-001.pressure_sense`。

### 11.2 `relief` — 泄放

```yaml
relief:
  - {valve: RV-001, from: F-001.outlet, to: return}
```

单行产出三项：泄放支路挂入 `from` 所在网络、`return` 侧网络、`member_relations` 中的 `relieves` 关系。

### 11.3 `couple` — 机械与功率耦合

```yaml
couple:
  - {kind: power_transfer, from: PTU-001.side_a, to: PTU-001.side_b}
  - {kind: mechanical_shaft, from: EMP-001.shaft, to: PMP-001.shaft}
```

`couple` 生成 `edge_type: power` 或 `mechanical` 的关系，**不生成流体网络**。液压系统的流体连通图与功率传递图不是同一张图：PTU 传递功率而不传递液体，若用 `paths` 表达会产生错误的流体连通。

### 11.4 `signal` — 电气输出与远传

```yaml
signal:
  - {kind: electrical_output, from: PS-001.elec_out, to: EXT-IND-001}
  - {kind: electrical_excitation, from: EXT-CMD-001, to: SOV-001.coil}
```

`signal` 生成 `edge_type: electrical` 关系，不生成流体网络。压力开关的电输出、电磁阀的线圈激励、液位计的远传指示均属此节。

### 11.5 `unknown` — 显式未知

```yaml
unknown:
  - pressure_class
  - RV-001.setting
  - operating_modes
```

`unknown` 是唯一允许承载"说不清的事"的位置。取值为受控标识符或 `<实例>.<属性>`，**不得为自由文本**。

L0 不设注释性字段、不设"备注"列。一旦允许自由文本槽，工程判断会全部迁移至该槽并被静默跳过，载体退化为自然语言。YAML 的 `#` 注释可用于说明，但编译器不读取注释，注释中的内容不进入任何产物。

`unknown` 非空时，`maturity` 必须为 `concept`，全部下游产物标记 `CONCEPT - NOT FOR DESIGN RELEASE`。

## 12. 规范化回吐 JSON

解析成功后编译器必须立即输出 `<name>.l0-normalized.json`，它是 L0 解析结果的忠实映射，不含任何派生：

```json
{
  "l0_version": "1.0",
  "source_file": "xxx.intent.yaml",
  "source_sha256": "<L0 文件字节哈希>",
  "system": "...",
  "catalog": "comac-hydraulic-components@A",
  "parts": { "CV-001": { "type": "check_valve", "l0_line": 14 } },
  "paths": [ { "seq": ["IN-001", "CV-001", "@MERGE"], "l0_line": 27 } ],
  "groups": [ { "id": "LRU-001", "members": ["CV-001"], "l0_line": 41 } ]
}
```

审查卡首屏必须展示该文件。缩进错位导致的挂错父节点、类型被静默转换、`@` 网络名被当作字符串以外的类型，均在此处可见。

每个对象携带 `l0_line`。这是 L0 到 L2 的唯一追溯键，取代原方案中的 `claims` 与 `source_claim_ids` 机制——两者之间不存在模型推断，无需人工维护声明编号，也不会出现 claim 与 JSON 漂移。

## 13. 编译输出

| 产物 | 内容 | 是否人工编辑 |
|---|---|---|
| `<name>.l0-normalized.json` | L0 忠实映射 + 行号 | 否 |
| `<name>.l2.json` | 完整 L2，含 `catalog_inference` | 否 |
| `<name>.review-card.md` | 由 L2 派生的审查表 | 否，仅确认 |
| `<name>.compile-report.json` | 校核结果、`catalog_inference` 清单、拓扑哈希 | 否 |

拓扑哈希在**规范化 JSON 与 L2** 上计算，不在 YAML 文本上计算。YAML 无公认规范化形式，不可作为哈希对象。

同一 L0 文件加同一目录修订，必须产出逐字节相同的全部产物。编译器不得包含时间戳、随机 ID 或哈希表遍历顺序依赖。

## 14. 对组件目录的字段要求

本规范依赖 `component-catalog.json` 提供以下字段。这些字段目前尚不存在，是实施 L0 的前置条件：

```json
{
  "component_type": "pressure_switch",
  "connection_role": "sensing_only",
  "ports": [
    { "id": "pressure_sense", "medium": "hydraulic", "role": "measurement",
      "flow_capability": "none", "svg_element_id": "port-pressure-sense" },
    { "id": "elec_out", "medium": "electrical", "role": "signal_out",
      "flow_capability": "none", "svg_element_id": "port-elec-out" }
  ],
  "main_path": null
}
```

| 字段 | 用途 | 缺失后果 |
|---|---|---|
| `connection_role` | `sensing_only` / `inline` / `terminal` | 10.5 的取压防线失效 |
| `main_path` | 默认进出端口对，`null` 表示不可串接 | 10.2 端口填充无法进行 |
| `ports[].role` | 线型推导与兼容性校核 | 10.4 线型推导失效 |
| `ports[].svg_element_id` | L5 端口坐标解析 | 渲染无法定位端口 |

`main_path` 为 `null` 或存在多个候选时，该类型不得出现在 `paths` 的裸实例位置。

## 15. 校核清单

### 15.1 解析期（`ERROR` 即停止，不产出任何下游文件）

1. YAML 1.2 core schema 解析通过；无 tab、无锚点别名、无多文档、无自定义标签；
2. 无表外键（第 6 章封闭词表）；
3. `l0_version`、`system`、`catalog`、`maturity` 存在，`catalog` 已钉修订号；
4. 所有 ID 匹配命名规则且全文件唯一；
5. 所有标识符字段为字符串类型，无裸数字被转换。

### 15.2 目录解析期

6. 每个 `component_type` 在指定修订目录中唯一解析；
7. 每个显式端口在目录中存在；
8. 每个裸实例位置的类型具有唯一 `main_path`；
9. 每个 `taps.sensor` 的类型 `connection_role` 为 `sensing_only`，且具有唯一 `measurement` 端口或已显式指定。

### 15.3 拓扑期

10. `paths` 中不含 `sensing_only` 组件；
11. 每个 `@` 网络名出现至少两次；
12. 每个 `taps.at` 所指端口已被某条 path 纳入网络；
13. 每个 `groups[].members` 项已在 `parts` 中声明，且分组 ID 不与任何实例 ID 冲突；
14. 分组 ID 未出现在 `paths`、`taps`、`relief`、`couple`、`signal` 中；分组未产生任何网络、端口或节点（第 9.1 条）；
15. 网络两端 `role` 兼容，`line_type` 可唯一推导；
16. 无同端口挂入多个不同网络；
17. 目录声明为必接的端口无悬空。

### 15.4 一致性期

18. L2 中每个对象可追溯到 `l0_line`；
19. 每处目录填充均记入 `catalog_inference`；
20. `unknown` 非空时 `maturity` 为 `concept`；
21. 同一输入重复编译产出逐字节相同结果。

### 15.5 失败关闭

`ERROR` 时不得产出 L2、审查卡或 SVG，只产出 `compile-report.json`。空组件列表、空网络列表不得作为成功结果。

## 16. 与现有规范的关系

| 现有文档 | 影响 |
|---|---|
| `液压原理图组件与JSON生成技术规范.md` §7 | 需补第 14 章四个字段，目录方可支撑 L0 |
| 同上 §8.2.1 | `claims` / `source_claim_ids` 机制在 L0 路径下由 `l0_line` 取代 |
| 同上 §6.2 | L0 依赖 `data-port-id` 等属性；现有 19 个组件 SVG 合规率为 0，须先整改 |
| `自然语言到L2语义JSON轻人力生成规范.md` | 自然语言前端降级为可选，其唯一合法产物是 L0 文件 |
| `L2语义系统JSON人工编辑指南.md` | L0 路径下 L2 不再人工编辑，该文档应改为审查卡指南 |

## 17. 版本控制

`l0_version` 采用 `<major>.<minor>`。次版本递增用于新增可选关键字，主版本递增用于删除或改变既有关键字语义。编译器必须拒绝主版本高于自身支持范围的 L0 文件。

任何词表变更必须先通过金样例回归。金样例集合至少包含：本规范附带示例、一个含 `couple` 的 PTU 用例、一个含 `signal` 的电磁阀用例、一个故意违反 10.5 的负样例（必须报 `ERROR`）。
