# L0 → L2 展开对照：双入口滤油与泄压回路

| 项目 | 内容 |
|---|---|
| L0 输入 | `test-two-inlet-pressure-switch-filter-relief.intent.yaml`（35 行有效内容，实测） |
| 对照基准 | `test-two-inlet-pressure-switch-filter-relief.json`（171 行，封装装配方案） |
| 目的 | 验证平坦拓扑覆盖同一系统，并量化封装装配的代价 |
| 状态 | **人工推导，编译器未实现**。本文档是编译器的行为规格，不是运行结果 |

## 1. 结论

同一物理系统，两种建模：

| | 封装装配方案（既有 L2） | 平坦方案（L0 v1.1） |
|---|---|---|
| 物理网络 | 5 条，但记为 9 条 | **5 条** |
| 网络记录总数 | **13**（5 内部 + 4 系统 + 4 端口映射） | **5** |
| 被切分的油路 | 4 条各切两半 | 0 |
| 连通性查询跳数 | 3 跳（网络→公开端口→内部网络） | 1 跳 |
| 虚线框来源 | L2 拓扑对象 `ASM-001` | L4 渲染分组 `LRU-001` |

装配当初被引入的唯一动机是画虚线框。改为渲染分组后，虚线框照画，8 条网络记录消失。

## 2. 网络展开（平坦）

L0 的 3 条 path + 2 条 tap + 1 条 relief，展开为 5 条网络、14 个挂点。

| 网络 | 挂点 | L0 来源 |
|---|---|---|
| `N-P-001` | `IN-001.out`/source、`CV-001.inlet`/main_path、`PS-001.pressure_sense`/sensing_branch | 第 27 行 + 第 32 行 |
| `N-P-002` | `IN-002.out`/source、`CV-002.inlet`/main_path、`PS-002.pressure_sense`/sensing_branch | 第 28 行 + 第 33 行 |
| `N-P-003` | `CV-001.outlet`/source、`CV-002.outlet`/source、`F-001.inlet`/main_path | 第 27、28、29 行经 `@MERGE` |
| `N-P-004` | `F-001.outlet`/main_path、`OUT-001.in`/consumer、`RV-001.pressure_in`/relief_branch | 第 29 行 + 第 36 行 |
| `N-R-001` | `RV-001.return_out`/source、`RET-001.in`/return | 第 36 行 `to: RET-001` |

对比既有 L2：`NET-IN-001` 与 `ASM-N-P-001` 合并为 `N-P-001`，`NET-OUT-001` 与 `ASM-N-P-004` 合并为 `N-P-004`，其余同理。`published_ports` 及其 4 条 `maps_to` 整节消失。

## 3. 来源分类

| 来源 | 数量 | 内容 |
|---|---|---|
| `L0-显式` | 16 | `extern` 4、`parts` 6、path 3、tap 2、relief 1 |
| `L0-派生` | 5 | 5 条网络的 ID 与 `line_type` |
| `目录填充` | 11 | 端口 ID（见 5.1） |
| `编译器标记` | 1 | `parallel_sources` 检测 |
| `渲染分组` | 1 | `LRU-001` → L4 `assembly_enclosures` |

平坦化使目录填充从 14 处降至 11 处——原本 4 个公开端口的映射不再需要推导。

## 4. 关系派生

| L2 对象 | L0 来源 | 说明 |
|---|---|---|
| `SENSE-PS-001` / `SENSE-PS-002` | `taps` 两行 | 与网络挂点同源，一行产两物 |
| `blocks_reverse_flow` ×2 | 目录 `check_valve` 功能模板 | 类型固有功能，不需 L0 声明 |
| `relieves` (RV-001 → F-001) | `relief` 一行 | 与 `N-P-004`/`N-R-001` 挂点同源 |
| `parallel_sources` 标记 | 编译器检测 | 同网络两个 source、上游均为单向阀 |

`published_ports`、`members`、`internal_nets`、`members_removable_in_situ`、`boundary_style` 五类对象在平坦方案中不存在。

## 5. 遗留问题

### 5.1 目录填充占派生总量四分之一

11 处填充全部是端口 ID。编译器正确性高度依赖目录质量，而目录当前不存在。`main_path` 定义错误会静默产出错误拓扑且不报错——L0 层面完全合法。

对策：`catalog_inference` 清单必须整段进入审查卡，不可折叠。工程师审的不只是拓扑，还包括"编译器替我填了哪 11 个端口"。

### 5.2 装配类型缺口已消失

既有 L2 的 `ASM-001.component_type` 是 `dual_inlet_check_valve_filter_pressure_relief_assembly`。上一版推导文档把它列为"L0 无来源的缺口"，并提出要么引入受控总成模板、要么允许匿名装配。

平坦化后这个问题不存在：没有装配节点，就不需要装配类型。`LRU-001` 只有 `label`（图面文字）和 `reason`（分组依据），不是 `component_type`，不需目录条目，不参与类型解析。

### 5.3 `claims` 机制被消除

既有 L2 有 8 条 `claims` 和遍布各对象的 `source_claim_ids`，L0 路径下全部由 `l0_line` 取代：

| 既有 | L0 路径 | 差别 |
|---|---|---|
| `CLM-003` "每个压力开关测量对应单向阀入口侧压力" | `l0_line: 32` | 不需抽取，不会漂移 |
| `INF-001` "pressure_switch 目录角色为 sensing_only" | 校核 15.2 第 9 条 | 从事后声明变为解析期强制 |

原方案中 `INF-001` 是一条需工程师审查的推断；L0 路径下它是一条无法违反的语法约束。

### 5.4 何时仍需真正的封装

外购作动器、成套液压包这类"图上只画一个方框和几个接口、内部构造本图不关心"的对象，确实需要接口抽象。但那应做成**子系统引用**（引用另一个 L0 文件的接口定义），不是在本文件内嵌套装配。L0 v1.1 不支持，需要时递增主版本。

判据：内部是否需要在本图渲染。需要渲染就是分组，不需要渲染才是封装。不可现场拆分与此无关——它只决定要不要画虚线框。

## 6. 行数对照

| | 行数 | 说明 |
|---|---|---|
| 自然语言描述 | 1 段 + 4 条约束 | 歧义须模型消解，不可重现 |
| **L0 意图（平坦）** | **35 行有效（实测）** | 受控词表，解析期报错，可重现 |
| L2（平坦，估算） | 约 110 行 | 编译产物 |
| L2（封装，既有） | 171 行 | 其中约 60 行是切分开销 |

35 行里 14 行是 `extern` 与 `parts` 的实例声明、5 行是 `groups`、5 行是 `unknown`。实例清单不可压缩也不应压缩。真正被消除的是关系的冗余表达：6 行（3 path + 2 tap + 1 relief）表达了 5 条网络、14 个挂点、2 条仪表关系、3 条功能关系。

L0 的价值不在压缩比。同抽象层次的 JSON 约 30 行，与 35 行 YAML 差别不大。价值在三点：`taps` 使取压关系不可能写漏一半；`sensing_only` 校核使压力开关不可能被串联；`l0_line` 使追溯不需维护声明编号。这三点与格式无关，与抽象层次和封闭词表有关。

## 7. 下一步

1. 补 `component-catalog.json` 的 5 个组件（`check_valve`、`filter`、`relief_valve`、`pressure_switch`、外部接口），含 L0 规范第 14 章四个字段；
2. 实现解析器与校核 15.1–15.3，先只产出规范化 JSON，不产出 L2；
3. 实现编译器，以本文档第 2 节为行为规格；
4. 既有 `test-two-inlet-...json` 作为历史封装方案样例保留，不作为比对基准——两者拓扑等价但网络 ID 不同；
5. 补齐金样例：PTU `couple` 用例、电磁阀 `signal` 用例、把压力开关写进 `paths` 的负样例（必须报 `ERROR`）、把分组 ID 写进 `paths` 的负样例（必须报 `ERROR`）。
