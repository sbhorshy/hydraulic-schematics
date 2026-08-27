# 自然语言到 L2 语义 JSON 轻人力生成规范（草案）

| 项目 | 内容 |
|---|---|
| 目的 | 让工程师用系统描述和少量审查结论替代逐项编写 `nodes`、`nets`、端口和仪表关系 |
| 输入 | 工程师的自然语言系统描述、受控组件目录、受控总成模板、已批准布局规则 |
| 输出 | 可追溯的 L2 草案 JSON、审查卡、校核报告；批准后再生成原理图 |
| 非目标 | AI 不自行批准未知阀位、流向、压力等级、部件内部通路或适航结论 |

> 这是一套生成和审查契约，不是已经实现的自然语言生成器。正式使用前，必须实现 Schema、组件目录、语义提取器、校核器和金样例。

## 1. 目标工作方式

工程师不再手工编辑 JSON，也不需逐项指定连接端口、三通、坐标或走线；工程师只做两件事：

1. 用自然语言说明系统意图；可直接口述记录，也可写入一个 Markdown 文本。
2. 审查系统生成的**连接关系表**和**待确认问题**，对每项选择“确认、修改、未知”。

```text
自然语言描述
  → AI 提取带来源编号的语义声明
  → 受控组件目录匹配端口和功能模板
  → 确定性编译器展开 L2 JSON
  → 校核器 + 审查卡
  → 工程师只确认差异与风险
  → 已确认 L2 → L3/L4/L5 原理图
```

工程师的原始描述是**需求/意图证据**；经审查确认的 L2 JSON 才是系统拓扑事实源。AI 生成的草案必须标为 `generated_draft_pending_review`，不得直接进入工程放行。

## 2. 工程师只需表达的内容

描述可以是普通句子，不要求记忆 JSON 名称。对一个可生成的子系统，至少应说明以下五类事实；每类可以一句话：

| 类别 | 工程师自然语言需要表达什么 | 示例 |
|---|---|---|
| 边界 | 从哪里来、到哪里去、是否回油/吸油 | “两个外部压力入口，一个压力出口和一个回油口。” |
| 组件 | 有哪些已知组件或总成 | “总成内有两个压力开关、两个单向阀、过滤器和溢流阀。” |
| 主油路 | 经过、分支、汇合、回到何处 | “两个入口各过一个单向阀后汇合，汇合后经滤器到出口。” |
| 测量/控制 | 测谁、控谁、泄到哪里 | “每个压力开关测量对应单向阀入口侧压力；过滤器出口经溢流阀泄至回油。” |
| 不确定项 | 未知或需要选择的状态/规格 | “单向阀开启方向待确认。” |

“在压力开关后有单向阀”并不足以确定物理关系：压力开关通常是取压元件，而不是主油路串联元件。若没有说明测点，生成器必须把它列为待确认，而不能静默串联或自行选择测点。

## 3. 关系必须分为四种，不能混写

| 关系 | JSON 的权威表示 | 例子 | 不表示什么 |
|---|---|---|---|
| 物理流体连通 | `nets` / `internal_nets[].attachments` | `CV-001.inlet` 属于 `ASM-N-P-001` | 不是“CV-001 一定允许流动” |
| 仪表测量 | `instrumentation_relationships` | `PS-001.pressure_sense` 经 `ASM-N-P-001` 测量 `CV-001.inlet` 上游压力 | 不是主油流串联关系 |
| 功能行为 | `member_relations` 或组件目录内部功能 | `CV-001` 阻断反向流；`RV-001` 泄放 | 不是几何连线 |
| 封装与接口 | `members`、`published_ports` | 外部只连 `ASM-001.inlet_1`；内部才连 `CV-001.inlet` | 虚线框不是管路节点 |

例如，压力开关与单向阀的完整、无歧义表达必须同时存在以下两段：

```json
{
  "id": "ASM-N-P-001",
  "attachments": [
    { "member_id": "PS-001", "port_id": "pressure_sense", "role": "sensing_branch" },
    { "member_id": "CV-001", "port_id": "inlet", "role": "main_path" }
  ]
}
```

```json
{
  "id": "SENSE-PS-001",
  "kind": "pressure_sensing",
  "sensor": { "member_id": "PS-001", "port_id": "pressure_sense" },
  "via_internal_net_id": "ASM-N-P-001",
  "observed_target": {
    "kind": "member_port",
    "member_id": "CV-001",
    "port_id": "inlet",
    "position": "upstream"
  }
}
```

第一段说明“两个端口相通”；第二段说明“压力开关为何接在这里、测量什么位置”。两段缺一不可。

## 4. AI 的受控推断边界

AI 可做的自动工作：

- 将“入口、出口、回油、经过、分支、汇合、测量、泄放”等词抽取为语义声明；
- 从组件目录选择已批准的 `component_type`、端口 ID、端口介质和已知内部功能；
- 为同类实例生成稳定 ID，例如 `PS-001`、`CV-001`；
- 将“两个单向阀后汇合”展开为两个入口网络和一个汇合网络；
- 根据组件目录把压力开关归类为 `sensing_branch`，而非串联主油路；
- 自动生成布局候选、走线和虚线装配边界，但不得改变拓扑。

AI 不可自行决定的事实，以及必须生成审查问题的情况：

- 组件类型、端口、阀正常位、单向阀允许方向或内部通路在组件目录中不存在；
- “后面”“旁边”“连接”无法判定为串联、取压、机械耦合或仅图形相邻；
- 多源压力网络缺少隔离方式或工作模式；
- 压力等级、介质、单位、泄放去向、回油去向未知；
- 一个仪表可能测量多个候选测点；
- 用户描述与受控组件目录的端口能力冲突。

此时草案可生成用于讨论，但必须携带 `review_flags` 和 `review_status: "needs_engineering_decision"`；校核器禁止把它提升为已确认 L2。

## 5. 机器可审查的生成合同

生成器应在草案 JSON 顶层写入下列非拓扑追溯信息。该信息由 AI 自动写入，工程师不手填：

```json
{
  "generation": {
    "mode": "natural_language_to_l2_draft",
    "source_document": "system-description.md",
    "review_status": "generated_draft_pending_review",
    "claims": [
      {
        "id": "CLM-010",
        "source_text": "每个压力开关测量对应单向阀入口侧压力。",
        "classification": "explicit"
      },
      {
        "id": "INF-020",
        "source_text": "pressure_switch 的目录角色为 sensing_only，故不进入主油路。",
        "classification": "catalog_inference",
        "catalog_ref": "pressure_switch@<catalog_revision>"
      }
    ]
  }
}
```

`nodes`、`nets`、`internal_nets`、`instrumentation_relationships` 和 `member_relations` 中的每一个生成对象应具有 `source_claim_ids`。这样审查者能从任意 JSON 关系反查到原句或目录推断，而无需阅读模型推理过程。

## 6. 工程师面对的唯一审查界面：审查卡

审查卡由 JSON 自动派生，工程师不直接改 JSON。每行都必须包含来源编号、影响对象和处理动作。

| 审查区 | 工程师看到的内容 | 工程师动作 |
|---|---|---|
| 组件表 | 实例 ID、组件类型、来自哪句话 | 确认/改名/删除 |
| 主油路表 | `入口 → 单向阀 → 汇合 → 过滤器 → 出口` | 确认/改连接说明 |
| 仪表关系表 | `PS-001` 测量 `CV-001.inlet` 上游压力 | 确认/换测点/未知 |
| 功能关系表 | 单向阀阻断反流、溢流阀泄放 | 确认/改功能或状态 |
| 待决项 | 未知方向、未定义工作模式、目录无匹配端口 | 填写答案或保持概念状态 |

如果所有关系均来自明确原句或已批准目录模板，审查仅需确认整张表；不是逐个编辑十几条 `attachment`。任何修改仍以自然语言反馈即可，例如：“PS-002 改为测量过滤器出口压力”。生成器必须重新生成 JSON、差异表和图，不允许直接在旧 JSON 局部涂改。

## 7. 示例：双入口、双压力开关、双单向阀总成

输入文件见 [test-two-inlet-pressure-switch-filter-relief.system-description.md](test-two-inlet-pressure-switch-filter-relief.system-description.md)。其中工程师只需给出如下描述：

> 两个外部压力入口进入一个不可现场拆分的总成。每个入口设置一个压力开关，用于测量对应单向阀入口侧压力；每个入口经过对应的单向阀后汇合。汇合油路经滤器到压力出口；滤器出口设溢流阀，溢流阀回油至回油接口。

生成器应自动得到：

```text
IN-001 → ASM.inlet_1 → [PS-001 sensing CV-001.inlet] + CV-001
IN-002 → ASM.inlet_2 → [PS-002 sensing CV-002.inlet] + CV-002
CV-001.outlet + CV-002.outlet → F-001.inlet
F-001.outlet → OUT-001，并分支至 RV-001.pressure_in → RET-001
```

对应草案见 [test-two-inlet-pressure-switch-filter-relief.json](test-two-inlet-pressure-switch-filter-relief.json)，审查卡见 [test-two-inlet-pressure-switch-filter-relief.review-card.md](test-two-inlet-pressure-switch-filter-relief.review-card.md)。

## 8. 推荐 MVP 实现顺序

1. 完成 L1 组件目录：每个受支持组件必须有端口、介质、主流/测量能力、允许方向和功能模板。
2. 将自然语言切分为 `claims`，每条声明保留原文和位置。
3. 先只支持“串联、分支、汇合、回油、泄放、取压、装配、外部接口”八类关系。
4. 使用确定性规则把已确认声明编译为 `nets`、`instrumentation_relationships` 和 `published_ports`；AI 不直接写 SVG 路径。
5. 生成审查卡和差异表；只允许工程师确认或用自然语言纠正。
6. Schema 和校核通过后生成 L3/L4/L5；任何 `needs_engineering_decision` 均停止在概念输出。

MVP 的验收不是“画出了图”，而是同一段描述和同一组件目录能稳定产生相同的关系表、JSON 拓扑哈希、审查问题和 SVG 追溯 ID。
