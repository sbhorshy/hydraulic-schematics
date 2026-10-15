# SysML → L0 转换与校核链路（#51/#52 窄版，部分实现）

> 状态：**局部实现 / 实验入口**。#51 转换器与 #52 校核链路入口是各自的
> 可独立部分，不是全量 SysML 链路。**独立夹具已验证**（demo-positive、
> l0-small-seed.sysml 全链），但 #51/#52 的完整验收（含真实 1# 模型转换）
> 仍保持**阻塞、到站未满足**：完整 1# 模型比手写 intent 多出 ECO/接通位
> QD/刹车支路，ECO 与接通位 QD 尚无目录类型、EMP overflow 不存在——该模型
> 必须被**准确拒绝**（见 §8 blocked 夹具），而不是删节点/假造目录/拿手写
> intent 冒充转换。本链路只覆盖下述窄文法，不与整机 SysML 模板
> （`render_aircraft_schematic.py`，飞机整机旧模板）混称通用 SysML 支持。
> 本文档冻结 CLI 与公开 API 形态；改动需同步修订本文件并在测试中固化。

## 1. 定位与分层

```
SysML 文本 ──▶ sysml_parser.parse（语法层，唯一来源，禁止第二套解析）
          └─▶ sysml_to_intent（#51：拓扑转换 + 母线还原 + 折叠 + taps + extern
                                + 真实同源 preflight + 行号追溯 sidecar）
                    ├─▶ L0 intent.yaml（+ <output>.trace.json）   [直接 CLI]
                    └─▶ validate_sysml（#52 薄入口：转换 → validate_driver
                          子进程 → SVG → PNG → 校核 → 追溯链合并
                          <workdir>/sysml-trace.json）
```

- 语法层零重复：词法/语法一律复用 `scripts/sysml_parser.py`（44 项独立测试）。
- 语义层零重复：发布前跑 `scripts/preflight.py` 的 `preflight()`（与渲染器/CLI
  同一函数）。任何 ERROR → 不发布 intent、不遗留可误认的陈旧成功输出。
- 校核零重复：#52 入口不复制任何布局/渲染/校验规则——preflight 门禁、
  布局（种子或引擎）、渲染、几何/像素校核、有界收敛与模板门禁全部由现有
  `validate_driver.py` 子进程同一实现完成。
- 复用 `topology_reconciliation.declared_topology` 的 main_path 展开语义做对账。

## 2. CLI（冻结）

### 2.1 转换器（#51）

```bash
python scripts/sysml_to_intent.py IN.sysml [-o OUT.intent.yaml]
                                           [--catalog CATALOG.json]
                                           [--trace TRACE.json]
                                           [--diff REF.intent.yaml]
                                           [--json]
```

| 项 | 约定 |
|---|---|
| `-o` 缺省 | 输入同目录 `<stem>.intent.yaml`（按输入文件位置解析，与 cwd 无关） |
| `--trace` 缺省 | `<output>.trace.json`；sidecar 绑定源文件字节/intent 的 SHA-256 |
| `--catalog` 缺省 | 锚定 skill 规范源 `assets/component-library/component-catalog.json` |
| `--diff` | 对**成功转换**与手写 intent 做拓扑对账；差异只披露不拦截 |
| 退出码 | `0` 转换并发布成功；`1` 转换被诊断拦截（**含 --diff 时同样**不发布并清理本工具陈旧成功输出，不宣称与手写 intent 一致）；`2` 用法/IO/发布安全拒绝 |

发布安全：输入、catalog、`--diff` 参照与输出 intent/trace 目标相撞或别名一律
拒绝；任一目标为现有目录拒绝；已存在但无法核验为本文工具产物的文件拒绝覆盖
（intent 所有权按**调用指定的 trace 或缺省 sidecar** 的 generator 标记 +
intent 哈希双通道核验）；既有 trace 目标还须**绑定当前输出**（sidecar 的
`output.path` 一致）——本工具生成但归属其他输出的 sidecar 视为别家产物，
保持字节不变并明确拒绝（"本工具曾生成"≠"属于本次输出"，清理的 other 分支
同此核验）；trace 写失败回滚 intent（恢复旧字节或删除新写），不留无 sidecar
绑定的 intent；失败运行只清理能被哈希绑定核验为**当前输出**所有的
intent+sidecar，绝不删除用户无关文件。

### 2.2 校核链路入口（#52）

```bash
python scripts/validate_sysml.py --sysml IN.sysml [--catalog CATALOG.json]
        [--layout-seed SEED.json] [--workdir DIR] [--rounds N] [--ref R.json]
        [--optimize] [--keep] [--max-evals N] [--max-steps N]
        [--max-seconds S] [--polish-steps N] [--readback-w W] [--json]
python scripts/validate_sysml.py --verify WORKDIR   # 核验既有追溯链
```

| 项 | 约定 |
|---|---|
| `--sysml` | 唯一转换来源；不要求用户先手工生成 intent |
| `--catalog` | 转换与驱动器**同用一份**；缺省锚定 skill 规范源。选定目录由驱动器随沙箱复制为工作区 `component-catalog.json` 快照，追溯核验按该快照重转换并核对 canonical SHA（见下"核验"） |
| `--layout-seed` | 原样转发驱动器（本地符号实读与来源登记由驱动器完成） |
| `--workdir` | 独立工作目录；缺省新建临时目录。先过与驱动器同源的隔离检查（skill 源树、其祖先与 symlink 别名拒绝） |
| `--ref` | 原样转发 `validate_driver.py`（`none`/`-` 为"无参照"特殊值，大小写不敏感）；有效 ref 路径是**本轮输入**，纳入输入重叠保护（见下"运行语义"） |
| 预算/轮次/`--optimize`/`--keep`/`--readback-w` | 原样转发 `validate_driver.py`，语义不变 |
| 退出码 | `0` 交付证据齐备；`1` 轮次耗尽；`2` 转换被拦或 preflight 残差（`--json` 的 `stage` 区分 `conversion`/`driver`；转换失败发生在**任何布局/渲染前**）；`3` 工具链故障——含**驱动器返回 0/4 但追溯链核验不成立**（降为 3，顶层 `ok=False`、`delivery.ready=False`，结构化原因入报告与 stderr）；`4` 校核零失败**且追溯链 current** 但交付证据未齐备（如感知签认缺，`delivery.ready` 保持 false）；`5` 用法/IO/路径安全拒绝（含 argparse 用法错误、**输入与工作目录重叠**）。`--verify` 模式独立计码：`0` 链 current / `1` 链不成立 |

运行语义：

- **转换失败先于一切布局/渲染**：诊断结构化（id/level/line/object/message）
  一次报齐；受管工作区中上一轮的 SVG/PNG/报告按驱动器失效清单清理（只
  unlink 固定产物名，绝不递归、绝不触碰输入与 skill 源），旧成功产物不得
  冒充本轮结果；并写 `status=conversion_blocked` 的 `sysml-trace.json`。
- **输入先于一切清理/写入受保护**：SysML/catalog/布局 seed/**--ref**/受控
  模板与工作目录重叠（realpath，含 symlink 别名；例如把 seed 或 ref 指向的
  参照放进受管工作区再 `--keep` 复用）即路径安全拒绝（退出码 5，输入字节
  不动）——不依赖驱动器晚一步的输入快照；独立输出子目录不包含输入的正常
  用法不受影响。
- **模板门禁不绕过**：受控清单模板从 **SysML 源同目录**发现（唯一
  `*受控模板.yaml`），随转换 intent 进入驱动器输入暂存目录，再随沙箱复制
  启用 preflight 门禁——与用户把 intent 放源目录的强度相同；签认等治理
  字段按模板内容生效，不由文件名推断成已签认。
- **独立 workdir 纪律不变**：转换 intent 只落临时暂存目录（输入，非产物），
  本轮产物只在驱动器工作区；工作区未被驱动器接管时（如沙箱建立失败）不向
  用户目录写链报告。
- **主流程内执行并采纳追溯核验**（不只独立 `--verify`）：每轮驱动器结束后
  立即核验链并写进 `sysml-trace.json` 的 `verification` 字段；驱动器 0/4
  但链不成立时本轮不得按成功报告（见退出码 3）；驱动器自身失败码（1/2/3）
  原样保留；顶层 `ok` = 驱动器 0/4 **且**链 current（`conversion.ok` 单独
  保留转换结论）。

## 3. 公开 API（冻结）

```python
convert_text(text, catalog=None, source_name=None, source_sha256=None)
    -> ConversionResult                       # 纯转换，不写文件
convert_file(sysml_path, catalog_path=None) -> ConversionResult
publish(result, output_path, trace_path=None, protected_paths=()) -> dict
topology_diff(converted_intent, reference_intent, catalog) -> dict
```

- `ConversionResult.ok=True` 当且仅当转换无 ERROR 且真实 preflight 无 ERROR；
  此时 `result.intent` 可发布；否则 `intent=None`，诊断（`id/level/line/object/
  message`，`line` 为 SysML 1-based 行号）与已解析声明（`declared`）披露在
  `result.diagnostics / result.declared / result.trace`。
- **源哈希口径**：`convert_file` 按**源文件原始字节**计算（LF/CRLF/BOM 均与
  磁盘一致，`trace.input.hash_scope='file-bytes'`，utf-8-sig 解码供 parser，
  1-based 行号不受影响；非 UTF-8 明确报错）；`convert_text` 缺省对 text 参数
  哈希（`hash_scope='text'`，换行规范化后的文本，不冒称源文件哈希），也可显式
  传 `source_sha256`。
- 失败转换不得调用 `topology_diff` 宣称一致。
- `topology_diff` 归一化口径：节点按 instance→type 比较；边/taps 按**无向端点
  对多重集**比较（方向差异不构成差异）；裸实例端口按 `declared_topology` 同一
  main_path 语义展开；母线 token 原样比较；缺失（reference 有转换无）与新增
  （转换有 reference 无）分列，附 intent 锚点。
- `validate_sysml`（#52）公开函数：`resolve_workdir(raw)`（隔离判定+独立
  临时目录）、`invalidate_stale_products(workdir)`（受管工作区固定产物名失效，
  外来 `sysml-trace.json` 保持字节不变）、`stage_driver_inputs(result,
  staging, template_src)`、`build_trace_report(...)`、`verify_chain(workdir,
  report)`、`write_trace_report(workdir, report)`（generator 标记所有权，
  拒绝覆盖非本工具产物）。

## 4. 窄文法与转换范围

接受 `sysml_parser` 窄文法全集：`package`、`part def`（`{}` 或 `;`）、typed
instance part（`part N : T;`）、系统 part（`part N { ... }`）、`port N;`、二元
`connect a[.b] to c[.d];`；引号名（含 `//`、`/*` 字面）、行/块注释、多行声明。
以下一律**明确失败**（诊断点名 + 行号），不做部分转换：

- 语法错误、n 元 connect、未闭合结构、同作用域重复声明（parser 拦）；
- 0 或 ≥2 个 system part、系统内嵌套 system、成员非 typed 实例；
- part def 名称**跨作用域重复**（遮蔽歧义，同名不同 scope 也不放行）；
- 实例名不符 intent 契约（须大写字母开头）、点分类型引用；
- 类型未声明 / 不在目录（如 eco_bottle、接通位 quick_disconnect_coupling）；
- def 声明端口 ∉ catalog 该类型端口清单（如 EMP-001.overflow）；
- 连接端点深入组件内部（>2 段）、引用未声明实例、端口未在类型 def 声明；
- 自环连接、同端点对重复连接；
- extern 边界声明或使用违规（§6 窄约定）：`E-SYSML-EXTERN-NAME`（名字不符
  intent 契约）、`E-SYSML-EXTERN-DUP`（同名冲突角色）、`E-SYSML-EXTERN-CLASH`
  （边界与实例同名）、`E-SYSML-EXTERN-UNDECLARED`（**仅有注释而无系统端口
  实体声明**）、`E-SYSML-EXTERN-PORT`（connect 给边界带 `.端口` 后缀——
  边界是系统端口，直接写端口名）、`E-SYSML-TAP-EXTERN`（taps 锚定边界
  终点）；角色值不符合 L0 契约 schema 枚举由同源 preflight 拦截。

系统实例与 part def 内部成员严格分离：只有 system part 的 typed 子成员生成
intent parts；**未引用的 def 不生成实例**；def 内部连接只作折叠证据。

## 5. 母线还原（枢纽约定）

- 声明来源：**仅输入注释**中的 `@大写名=实例` 或 `@大写名=实例.端口`（块注释内
  按注释内换行折算真实行号）。不写死任何 1# 实例映射；模型没有枢纽声明且
  全显式端口时直接转换。`#53` 的自动检测不在本批。
- **端口枢纽（`@X=I.p`）**：端口须在目录且 medium=hydraulic；一口不得绑两条
  母线。**每个已声明端口枢纽都必须连回真实端口**：
  - 唯一的等价合并——实例 main_path 的进/出两口各绑一条母线、且只经母线接线
    时，补回 `[bus(in), I, bus(out)]` 一条三 token 桥接路径，同时表达两口
    （**不吞边**；证据 = 枢纽声明行 + def 行，sidecar `kind=bridge`）；
  - 其余一律补一条显式辐条路径 `[@X, I.p]`（sidecar `kind=spoke`，证据 =
    枢纽声明行 + 实例行）。单口枢纽（如油箱回油口）因此不会被吞边。
- **元件枢纽（`@X=I`）**：仅当目录类型**恰好一个**非 sensing_only 的
  hydraulic 端口时可用（枢纽=该端口的汇流抽象，唯一绑定，等价端口不报
  未连接）；多端口/传感元件枢纽**无法唯一绑定真实端口，一律 ERROR 拒绝**
  （`E-SYSML-HUB-COMPONENT-UNBOUND`）——裸辐条会把其他元件直挂母线、绕过
  本元件，unknown 不用于放行丢失的连接。
- 母线-母线连接（端口枢纽↔端口枢纽、↔唯一端口元件枢纽）两端都是真实母线
  锚点，无向连接语义忠实，放行。
- **裸 inline 的 main_path**：SysML connect 的 `to` 不是液流方向。裸实例仅在
  main_path 端口可由**对端介质**等已声明约束唯一确定时转换；否则
  `E-SYSML-BARE-AMBIGUOUS` 点名拒绝，不按出现顺序猜。无 main_path 的裸实例
  （`E-SYSML-BARE-NOMP`）同拒。

## 6. 折叠、taps 与 unknown（冻结映射）

**折叠模板**（`FOLD_TEMPLATES`；核验=成员名/类型/边界口/端点段数/成员端口
存在性/内部连接**多重集**，不去重不截断，任一偏差即 `E-SYSML-FOLD`；带内部
结构的成员类型递归核验）：

| part def 名 | 折叠目标（目录叶类型） | 约定结构 |
|---|---|---|
| `filter_line_shutoff_dp` / `_return` / `_case_drain` | 同名（恒等核验） | 本体 = element(filter_element)+sensor(dp_sensor)，4 条内部连接（主流 2 + 传感跨接 2） |
| `return_filter` | `filter_line_shutoff_dp_return_bypass` | body(回油本体)+cv(check_valve_spring) 并联旁通，4 条 |

**CDF 映射依据（披露）**：1# 手写 intent 的 CDF-001 =
`filter_line_shutoff_dp_case_drain`（符号 filter-line-shutoff-dp.svg，带压差
指示）；目录旧叶类型 `case_drain_filter` 是无压差符号（filter-line-shutoff-
stroke.svg），且"本体+串联单向阀"装配形态**目录无对应符号**——该形态拒绝
折叠（结构无法证明的不代表支持），CDF 直用本体类型（恒等复合核验）。
catalog 已登记类型携带无模板可核的内部结构同样拒绝。

**taps / paths 分类**（P1 语义，依 catalog role/medium）：

- `connection_role=sensing_only` 的实例，其连接一律归 taps（`{sensor, at}`），
  不入 paths；一口传感件的多条连接各归一条 tap（一口压力表不伪造第二个贯通口）。
- **介质越界不豁免**：taps 两端介质必须**同质**且属 {hydraulic, pneumatic}；
  机械/电气端口参与 tap、或混介质 tap 一律 `E-SYSML-MEDIUM` ERROR（不存在
  "跨介质 WARN 放行"口径）。paths 内出现非 hydraulic 端口同样 ERROR
  （电气/机械/气侧连接与混介质不支持；不得伪造贯通口）。
- taps 两端须是实例端口，锚母线拒绝（气侧母线 taps 约定未决，§8）。

**unknown 披露**（进 intent `unknown`，来源+真实行号记 sidecar；绝不借
unknown 删除真实连线）：

- 注释中的 `unknown: <slug>` 标记原样收录；
- **文档化待决标记**：注释行含 `待工程确认 / 待确认 / 待定 / 待同步 /
  去向未声明 / 未声明 / 悬空 / 未建模` 之一时，按待决项搬运
  （intent 条目 `sysml-pending-l<行>:<原文摘录>`，sidecar 记
  `source=pending-comment` + 原文 + 真实行）；与 `unknown:` 同行的以结构化
  slug 为准不重复记；
- 目录端口未被任何连接/枢纽引用 → `<I>.<p>-unconnected`
  （`kind=body_tap` 的本体感测口除外）；元件枢纽的唯一端口视为已被枢纽
  引用，不误报。

**extern 边界（#52 窄约定，原生边界写法）**：边界在本仓库有既定写法——
系统 part 内 `port 'NAME';` 是 **SysML 实体声明**，connect 直接引用该端口
（`connect 'X'.'out' to 'NAME';`，不带 `.端口` 后缀）；注释行
`extern: NAME=PORT` 只**补充 L0 边界角色**（PORT 是该边界进 intent
`extern` 映射的端口标签，取值受 L0 契约 schema 枚举 inlet/outlet/return
约束）。二者缺一不可：**仅有注释而无对应系统端口声明一律
`E-SYSML-EXTERN-UNDECLARED` 拒绝**（注释不替代 SysML 实体）；系统端口在
而注释缺失时按普通实例解析照常报 `E-SYSML-REF`（L0 边界语义不默认成立，
绝不从文件名/布局推断）。转换核对被引用边界确有系统端口实体、角色值合法；
sidecar 逐边界保留**注释声明行与系统端口声明行**两个真实 1-based 行号。
未被任何连接引用的已声明边界按未连接项披露（`<NAME>-unconnected`，
source=unconnected-extern），不静默丢弃。taps 锚定边界拒绝；taps 两端
均须实例端口。

**固定字段**：`maturity: concept`；`extern` 仅由上述显式声明产生（缺省
`{}`）；`catalog: <catalog_id>@<catalog_revision>`（实读目录）；
`l0_version: '1.1'`；`system`: 系统 part 名。输出 YAML 键排序、确定性，
可复现（同输入重跑逐字节一致）。

## 7. 证据边界与追溯 sidecar

`<output>.trace.json`（`generator=sysml_to_intent`，schema_version 2）：

- 绑定：`input.{path,sha256,hash_scope}`、`output.{path,intent_sha256}`、
  `catalog.sha256`。hash_scope 区分 `file-bytes`（文件入口，源文件原始字节）
  与 `text`（纯接口入口，text 参数），不把规范化文本哈希冒称源文件哈希。
- 每个**输出 part**（`parts.<I>`：SysML 实例行、类型、def 行、折叠证据）与
  每条**输出边**（`paths[i][k->k+1]` / `taps[i]` 既有 intent 锚点格式：来源
  connect 行；bridge/spoke 边另附 `evidence_lines` 与还原说明）都有条目；
  extern 声明逐条带名字、角色端口、**注释声明行与系统端口声明行**
  （`externs`）；未知项逐条带来源（comment / pending-comment /
  unconnected-port / unconnected-extern）与行号。
- 行号全部来自 parser AST 或注释内精确折算，**不伪造 SysML 行号**；转换失败
  时的 `declared`（包/def/实例/extern/连接清单）与诊断一并披露在 trace 与
  `--json` 出口。

**链路合并追溯报告（#52 `<workdir>/sysml-trace.json`，generator=
`validate_sysml`）**——把三方证据绑成一条可验证链：

```
SysML 源（sha256, hash_scope=file-bytes, declared 行号清单/extern 声明行）
  → 转换 intent（intent_sha256 + intent_yaml 内嵌 + hubs/parts/edges/taps/
    unknown 的 intent 锚点 + sysml_line）
  → 驱动器轮次（final_intent_sha256、处方台账、convergence/validation 报告
    哈希与 artifacts 指纹、delivery 状态）
  → SVG 拓扑 manifest（svg/manifest sha256 + manifest_matches_final_intent）
```

- 当前映射口径（如实披露）：SVG 元件携带 **intent 锚点**（`data-node` /
  `data-port` / `data-edge` / `data-input-anchor`），**不携带
  `data-sysml-line`**；源行映射只存在于本报告与转换 sidecar，且只绑定其
  登记 `intent_sha256` 的转换产物——**源行映射关联到图的前提是转换
  `intent_sha256` 与驱动器实际输入 `final_intent_sha256` 同一**；处方
  （P1）改写沙箱输入时该前提不成立，链判 invalidated（不是仅披露后仍
  current）。
- manifest 对账复用 `declared_topology`：节点 id→type、边锚点+端点、extern
  清单三方比对，任何不符记入 `manifest_mismatch` 且
  `manifest_matches_final_intent=false`。
- **核验（`verification` 字段，主流程每轮执行并采纳；`--verify WORKDIR`
  独立复跑同一判定）必须全部成立才判 current**：
  1. 必需记录/字段/状态齐备（source/template/conversion/driver/sheet，
     conversion status=converted 且含 intent 哈希/正文、catalog、
     hubs/externs/parts/edges/taps/unknown 全套源行映射）；
  2. 源文件在登记路径且哈希一致；
  3. **确定性重转换**（复用纯转换接口，不重实现规则）按**工作区 catalog
     快照**重放（先核对其 canonical SHA 与登记 `conversion.catalog.sha256`
     一致；快照缺失/不可读/哈希不符或回退缺省目录均不成立），逐项复现登记的
     intent 哈希/正文、declared、catalog 哈希与全部映射清单——登记记录
     不得张冠李戴到别的模型或别的转换结果上；
  4. 转换 intent_sha256 == 驱动器实际输入 final_intent_sha256（硬性等号；
     处方改写输入即不成立）；
  5. manifest 每个节点/边/边界都有对应源行映射记录且端点一致，转换边/tap
     反向也须落在 manifest（缺映射不能通过）。桥接/裸实例边的源行记录保留
     intent 原始 token，manifest 是 `declared_topology` 的 main_path 展开
     表示——比对前按同一位置语义（首端点=main_path 出口、末端点=入口，
     仅展开裸实例 token）规范化；规范化不改源行记录，端点被改仍必报；
  6. SVG/manifest/校验报告与登记哈希一致，校验报告按 `proofreading_
     evidence` 口径 current。**后处理改过已验证 SVG/报告的，旧链不得自称
     current**（`--verify` 退出码 1 + 结构化 reasons）。
- 报告落盘仅限驱动器受管工作区；同名外来文件保持字节不变并明确拒绝覆盖。

## 8. blocked 夹具与未决问题

**blocked-project.sysml**（`assets/fixtures/sysml-l0/`）是 `1#系统原理图/
1#系统.sysml` 的逐字节冻结副本（SHA-256
`08e9fd67f75c7ef4b6b1b20288cb814712868d2643ca122e8e25a44a26f0aeb9`，测试固化，
不依赖外层仓库文件），代表**全量验收被阻塞模型**：转换必须失败，诊断至少
点名 ECO-001、QD-001..003（目录无类型）、EMP-001.overflow（目录无此端口）；
当前版本另如实报告：`@USR=PRV-001` 元件枢纽无法唯一绑定（priority_valve 两
口）、FSOV-001/PRV-002 裸口方向歧义、FSOV-001.command 未登记、CDF
装配+串联单向阀形态无折叠模板。不得制造"精简 1# 正例"；正例是
`demo-positive.sysml`（独立具名测试模型，配套手写参照
`demo-positive.intent.yaml` 供 `--diff`/`topology_diff` 对账，端口枢纽
@PRESS/@MANIFOLD/@USR/@RET 以真实端口连接为 oracle）与
`l0-small-seed.sysml`（#52 校核链路正例：独立具名模型，原生边界写法——
系统 part 内 `port 'USR-001';` 实体声明 + 注释 `extern: USR-001=outlet`
补 L0 角色，拓扑对应 l0-small-seed 夹具，布局 seed 直接复用
`assets/fixtures/l0-small-seed/1#系统.layout.json`，真实走转换→preflight→
`validate_driver`→SVG→PNG→校核→追溯链合并；控制端 WSL 环境实测自动
fail 0 / exit 4，缺感知签认时 `delivery.ready=false`）。

未决（实现前不得静默放行）：

1. 裸 inline 在介质不可判别时的方向（同介质双候选）——如 1# 的 FSOV/PRV-002；
2. 气侧母线 / 电气/机械连接的 intent 表达（当前 paths 仅 hydraulic，
   taps 限 {hydraulic, pneumatic} 同质）；taps 锚定母线/边界；
3. `#53` 母线自动检测；折叠模板的结构化登记（当前冻结于代码 + 本文 §6）；
4. ECO/接通位 QD/EMP overflow/FSOV command 等类型与端口的目录登记（归目录
   流程，不在转换器内假造）；CDF"本体+串联单向阀"装配形态如需支持，须先
   登记目录符号并在此扩展折叠约定；
5. 传感链中段为 inline 元件的链式 taps 表达（当前每条 sensing 连接独立成
   tap，与手写 #46 链式写法在锚点归一化后语义等价但条目不同，对账披露）；
6. extern 声明目前仅支持 {inlet, outlet, return} 枚举内的单端口边界（L0 契约
   schema 口径）；多端口/带介质约束的边界约定未决。

## 9. 测试

```bash
python -m unittest discover -s .agents/skills/hydraulic-schematic/scripts \
        -p test_sysml_to_intent.py -v     # 转换器（自包含可移植）
python -m unittest discover -s .agents/skills/hydraulic-schematic/scripts \
        -p test_sysml_parser.py -v        # 语法层
python -m unittest discover -s .agents/skills/hydraulic-schematic/scripts \
        -p test_validate_sysml.py -v      # #52 链路接入（正例全链含真实
                                          # 渲染/PNG，约 1–2 分钟；需
                                          # Chrome/栅格化依赖齐备的宿主）
python .agents/skills/hydraulic-schematic/scripts/check_library.py   # 库门禁
```

三个 SysML 专项已登记进 `selftest.py` 的 `L0_SUITES`（F 组逐套件独立进程），
随完整 selftest 执行；打包依赖包含 `sysml_parser`（转换器与 #52 入口共同
import，随 skill scripts 分发）。用例数以各套件实际为准，不在文档写死。

覆盖：最小正例过真实 preflight；母线还原（桥接等价合并 + 每枢纽连回真实
端口的辐条）/折叠/taps/extern 拓扑 oracle；unknown、待决注释与 1-based
行号；反例（未知类型/端口、语法错误、引号/注释、多行、重复/遮蔽、n 元、
歧义裸口、修改装配内部连接、内部连接重复/深端点/成员端口缺失、元件枢纽
绕过、介质不支持含机械 tap 与混介质 tap、taps 锚母线、extern 名/角色/
冲突/带点引用/tap 锚定/**仅注释无系统端口声明**/schema 枚举）；CDF 折叠
映射对齐；blocked 夹具（冻结哈希）拒绝清单；发布安全（自定义 trace 所有
权、用户 sidecar 保护、目录目标预检、trace 写失败回滚、--diff 失败同路径
清理、protected 相撞）；源哈希绑定（LF/CRLF/BOM/内容变更）；cwd 无关
CLI；对账归一化与缺失/新增分列。#52 另覆盖：正例真实全链（无签认 =
严格 exit 4、`delivery.ready=false`、自动 fail 0；不接受工具故障冒充正例
通过）、追溯链完整性（合并他模型转换、篡改源行/记录、缺记录、catalog
哈希错、处方改输入均 invalidated；`--verify` current/invalidated）、
转换先于渲染拒绝、受管工作区旧产物失效、模板随源目录进沙箱启用门禁
（顶层 ok=False）、输入/工作目录重叠保护（受管目录内 seed、源目录别名）、
路径保护（skill 树/祖先/symlink 别名）、输入不可改性、用法退出码、驱动
器失败/链不成立时顶层 ok 采纳逻辑（控制流桩）。不在此跑完整 selftest。
