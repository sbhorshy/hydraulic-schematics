# L2 语义系统 JSON 人工编辑指南

| 项目 | 内容 |
|---|---|
| 适用对象 | 液压系统工程师、组件库维护人员、原理图审查人员 |
| 工程师输入 | 自然语言 `system-description.md`；不要求手工编写 JSON |
| 已确认事实源 | 经审查确认的 L2 JSON；草案 JSON 仅用于概念讨论 |
| 当前实例版本 | `2.0-draft-encapsulated-assembly` |
| 输出边界 | 概念模型；不构成工程放行或适航批准 |

> L2 回答四件事：系统中有什么对象、每个对象属于什么组件类型、端口属于哪个管网、仪表具体测量哪个端口位置。它不保存三通坐标、管线路径、组件位置、虚线框尺寸或 SVG 路径。

## 1. L2 在整体链路中的位置

```text
L1  component-catalog.json
    组件类型、允许端口、SVG、内部功能与状态
          ↓
L2  hydraulic-system.json                 ← 自然语言生成、工程师审查后确认的系统事实源
    节点、封装装配、管网、仪表关系和端口归属
          ↓ 编译器
L3  compiled-topology.json
    自动派生的 junction 与 C-xxx 连接
          ↓ 布局器
L4  layout.json
    组件位置、旋转、走线、虚线装配边界
          ↓ 渲染器
L5  schematic.svg / connectivity.csv / validation-report.json
```

主流程中，工程师编辑自然语言描述并审查自动生成的关系表，而不是手工维护 L2。L2 的直接编辑只作为受控例外；任何修改都必须回写为自然语言变更或审查结论后重新生成。L3、L4、L5 必须重新生成，修改派生产物不能反向改变 L2。

## 2. L2 的顶层结构

```json
{
  "schema_version": "2.0-draft-net",
  "model_kind": "hydraulic_semantic_model",
  "system_id": "EXAMPLE-NET-ASSEMBLY-001",
  "maturity": "generated_draft_pending_review",
  "generation": {},
  "nodes": [],
  "nets": []
}
```

| 字段 | 人工是否编辑 | 用途 |
|---|---:|---|
| `schema_version` | 仅按批准的 schema 修改 | 防止不同解析器混用 |
| `model_kind` | 否 | 固定为 `hydraulic_semantic_model` |
| `system_id` | 创建系统时填写，之后保持稳定 | 全局追溯 ID |
| `maturity` | 是 | 表示概念、评审或已批准成熟度 |
| `generation` | 否，自动生成 | 原始描述、来源声明、目录推断和审查状态 |
| `nodes` | 是 | 系统对象清单 |
| `nets` | 是 | 管网及端口归属；L2 的核心 |

## 3. 节点：人工声明系统中有什么

### 3.1 普通组件

组件类型和端口名称必须来自 L1 组件目录；不得根据 SVG 外观自行命名端口。

```json
{
  "id": "F-001",
  "kind": "component",
  "component_type": "filter"
}
```

常用 `kind`：

| `kind` | 用途 | 示例 |
|---|---|---|
| `component` | 具有已知组件类型的系统对象 | `F-001`、`RV-001` |
| `external_interface` | 系统边界的入口、出口或回油接口 | `IN-001`、`RET-001` |

`junction` 不应在 L2 中人工维护；它由编译器依据 `nets` 的连接度在 L3 派生。

### 3.2 装配组件

装配是 `kind: "component"` 的封装复合组件。它记录本地成员、内部网络、仪表关系和公开端口；虚线边界由 L4 自动生成。外部系统只连接公开端口，不能直接连接本地成员。

```json
{
  "id": "ASM-001",
  "kind": "component",
  "component_type": "filter_pressure_relief_assembly",
  "members": [
    { "id": "PS-001", "component_type": "pressure_switch" },
    { "id": "F-001", "component_type": "filter" }
  ],
  "internal_nets": [],
  "instrumentation_relationships": [],
  "published_ports": [],
  "members_removable_in_situ": false,
  "boundary_style": "assembly_enclosure"
}
```

编辑规则：

- `members` 是装配本地成员；不得在顶层 `nodes` 中重复声明，也不得直接被外部 `nets` 引用。
- `internal_nets` 表示本地成员之间的真实流体连通；`instrumentation_relationships` 表示测量目标，不得用图形相邻或泛化的成员关系代替。
- `published_ports` 必须把每个外部端口映射到唯一 `internal_net_id`；外部 `nets` 只可连接 `ASM-001.<published_port>`。
- 不填写 `x`、`y`、宽高、虚线间距和路径；这些属于 L4。
- `members_removable_in_situ` 未确认时不得默认为 `false`，应使用已批准 schema 中的未知值表达方式或停留在概念阶段。

## 4. 管网：人工声明哪些端口处于同一压力/回油节点

一个 `net` 表示同一介质、同一管路语义下的一组端口归属。人工只需将端口加入 `attachments`，不需手工建立每一对设备之间的连接。

```json
{
  "id": "NET-P-001",
  "medium": "hydraulic",
  "line_type": "pressure",
  "attachments": [
    { "node_id": "IN-001", "port_id": "out", "role": "source" },
    { "node_id": "PS-001", "port_id": "pressure_sense", "role": "sensing_branch" },
    { "node_id": "F-001", "port_id": "inlet", "role": "main_path" }
  ]
}
```

### 4.1 人工填写的字段

| 字段 | 含义 | 编辑要求 |
|---|---|---|
| `id` | 稳定管网 ID | 建议 `NET-P-001`、`NET-R-001`；发布后不重用 |
| `medium` | 介质 | 必须与全部端口兼容，例如 `hydraulic` |
| `line_type` | 管路语义 | 例如 `pressure`、`return`、`suction` |
| `attachments[].node_id` | 设备或接口实例 | 必须存在于 `nodes` |
| `attachments[].port_id` | 该实例的端口 | 必须存在于 L1 的 `component_type` |
| `attachments[].role` | 该端口在管网中的功能 | 用于布局、审查和规则校核 |
| `review_flags` | 需要人工处理的风险 | 不得因存在警告而静默删除 |

### 4.2 `role` 的最小词汇

| `role` | 含义 | 典型对象 |
|---|---|---|
| `source` | 向管网供压或供油 | 泵出口、外部压力入口 |
| `main_path` | 主油路继续传递 | 过滤器入口/出口、阀主通道 |
| `sensing_branch` | 只取压或测量，不承载主流量 | 压力开关、压力表 |
| `parallel_branch` | 与主油路并联的功能支路 | 蓄压器 |
| `relief_branch` | 过压泄放支路 | 溢流阀压力入口 |
| `consumer_interface` | 向下游系统输出 | 外部出口 |
| `return_interface` | 回油系统边界 | 回油接口 |

新增 `role` 不是普通编辑动作；必须先更新 schema、规则库和金样例。

### 4.3 多设备管网的人工编辑方式

不要这样做：为五个设备手工写十条两两连接。

应这样做：创建一个 `NET-P-001`，为每个设备端口增加一条 `attachment`。编译器再生成 `J-xxx` 和 `C-xxx`。

多源管网、不同压力等级混接、多个泄放路径或未定义工作模式必须写入 `review_flags`。在这些问题完成确认前，模型只能产生概念输出。

## 5. 推荐轻人力生成与审查步骤

1. 写一段系统描述：边界、组件、主油路、测量/控制关系和已知未知项。
2. AI 从受控组件目录匹配类型和端口，生成带 `source_claim_ids` 的 L2 草案。
3. 审查自动生成的组件表、网络表、仪表关系表和待决项；不直接逐项编辑 JSON。
4. 用“确认/修改/未知”处理每项待决关系；修改使用自然语言，例如“PS-002 改测过滤器出口”。
5. 重新生成草案、差异表和校核报告；未决项保留 `needs_engineering_decision`。
6. 仅在 L2 校核通过且审查状态为已确认后生成 L3、L4、L5，并审查管网成员清单和图形。

## 6. 编辑后最小检查清单

- [ ] JSON 可解析，ID 无重复。
- [ ] 每个 `attachment.node_id` 都存在于 `nodes`。
- [ ] 每个 `attachment.port_id` 都存在于组件目录对应的组件类型。
- [ ] 每个必接端口恰好属于一个 `net`；未接端口必须显式记录原因。
- [ ] 每个 `net` 的 `medium`、`line_type` 和成员端口兼容。
- [ ] 每个装配成员都存在，且没有同层重复归属。
- [ ] 多源、混压、未知工作模式和未确认连接已写入 `review_flags`。
- [ ] L3 中每个 `J-xxx`、`C-xxx` 均能追溯到一个 `NET-xxx`。
- [ ] L4 的虚线装配框成员集合与 L2 的 `members` 完全一致。

## 7. 不应人工编辑的文件或字段

| 对象 | 原因 |
|---|---|
| `compiled-topology.json` 的 `J-xxx`、`C-xxx` | 必须从 L2 `nets` 派生 |
| `layout.json` 的组件坐标和走线 | 是布局候选，不是系统事实 |
| SVG 的路径、箭头、三通和虚线框 | 是渲染产物 |
| L1 组件目录已有端口 ID | 端口语义变更需走目录和 schema 变更控制 |
| 未确认的介质、端口角色或工作模式 | 必须保留未知/待审状态，不得猜测 |
| `generation.claims`、`source_claim_ids` | 由生成器维护，用于从 JSON 回溯原始描述 |

## 8. 本目录实例的阅读顺序

1. 阅读 [自然语言到L2语义JSON轻人力生成规范.md](自然语言到L2语义JSON轻人力生成规范.md)。
2. 阅读 [test-two-inlet-pressure-switch-filter-relief.system-description.md](test-two-inlet-pressure-switch-filter-relief.system-description.md)。
3. 审查 [test-two-inlet-pressure-switch-filter-relief.review-card.md](test-two-inlet-pressure-switch-filter-relief.review-card.md)。
4. 对照 [test-two-inlet-pressure-switch-filter-relief.json](test-two-inlet-pressure-switch-filter-relief.json) 查看自动展开的 L2 关系。
5. 对照 [test-two-inlet-pressure-switch-filter-relief.svg](test-two-inlet-pressure-switch-filter-relief.svg) 审查最终图形。

> `2.0-draft-encapsulated-assembly` 是当前用于验证“封装装配 + 管网优先 + 显式仪表关系”的草案实例。进入正式工程使用前，必须把 `generation`、`source_claim_ids`、`nets`、`instrumentation_relationships`、`published_ports` 和派生规则纳入 JSON Schema、校核器和金样例，并经工程师审批。
