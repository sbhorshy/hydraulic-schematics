# 渲染规则

## 输入定义（二选一，勿混用）

**SysML 链路**（整机）：`.sysml` v2 文本。解析 `part`（实例化层次：如 `greenCircuit:HydraulicCircuit`）与 `connect a.b to c.d` 语句；记录每条语句的行号用于追溯。平台/概念级简化允许存在，但必须披露（见追溯清单"简化说明"）。

**L0 链路**（分系统）：`intent.yaml` 章节：

```yaml
l0_version / system / catalog / maturity
extern:      # 系统边界(地面接头等必然开口)
parts:       # id: component_type —— 只收目录内类型
paths:       # 连接; 目录外类型不得出现(L0 规范)
groups:      # 布 lane 用分组(布局抽象, 1.0T 退后线宽)
assemblies:  # 装配声明(可选段): label 必填、members≥2; 驱动装配围框
unknown:     # 数量/接法存疑, 显式列出, 不代为编造
```

再加一份 `<name>.layout.json` 给显式坐标：`canvas`、`style`、`nodes`、`buses`、`labels`、`lanes`、`legend`、`title_block` 等——**不做自动布局**。

## 视觉常量（两链路共用）

| 常量 | 值 | 含义 |
|---|---|---|
| `HIGH_SW` | 3.0 | 高压供压线 |
| `LOW_SW` | 1.2 | 回油线 |
| `MED_SW` | 1.4 | 吸油/供油线 |
| `SIG_SW` | 1.2 | 指挥/状态信号（虚线） |
| `MECH_SW` | 1.4 | 机械（轴功率）线 |
| `PORT_R` / `JUNC_R` | 5 / 4.5 | 端口点 / 三通节点半径 |

线型由端口 role + medium 推导（class：`hi/med/lo/mech/sig`）；流体边带 `marker-end="url(#ah)"` 箭头，机械边不带。吸油语义从油箱口到泵 suction 口跨串联组件传播。

## 走线与布置

- 全部正交走线（H/V 折返），紧凑写法 `M x y H x V y ...`。
- 实心三通节点只画在真实汇/分点，不画折角。
- 对称系统用"局部回路 + 水平镜像"：镜像关于局部中线，盒子须 `LOCAL_W - bx - bw` 让出宽度；符号 `<image>` 用 `transform="translate(2ax+bw,0) scale(-1,1)"` 翻转。
- 符号经 `<image>` 引用并按盒缩放，href 相对**活动库根**——解析顺序：工作目录相对（本地覆盖）优先，否则锚定 catalog 同目录（单源化后即 skill `assets/component-library/`，工作目录无需库拷贝）；目录外或未标注符号画干净描边框图（box+标注），在图签栏披露。
- 用户（用油设备）一律用 `hydraulic_user` 通用符号：**矩形框+框内用户名**，左=压力入口（`pressure_in`）、右=回油出口（`return_out`），inline 串接。用户名不写在符号文件里——符号带 `data-name-slot` 文本槽，L0 渲染器把实例标签写入框内，并自动省略该实例的框外标签（名字不画两遍）。SysML/image 链路暂无此机制，须为该实例另存命名符号文件并披露。
- 分区框 `<rect data-zone>` + 分区标题（如 GREEN CIRCUIT / 绿系统）。
- 标签中英双行（`油箱\nReservoir`），中文主名；字体 fallback `"Microsoft YaHei","Noto Sans CJK SC",sans-serif`。
- 图签栏（title block）必含：来源文件、范围、成熟度及免责声明（`成熟度: concept 概念图,非工程放行图`）；图例框列全各类线型。

## 装配围框（Assembly Enclosure）

> 出处：标准条文 "Enclosure for an Assembly — used to border a group of symbols
> where the component extremity is not obvious by the connecting symbology.
> Elements are not removable in situ."（措辞与 SAE AS1290A 一致；**条款号待手持
> 原件核对**，沿用 PENDING_STANDARD_ID 挂账口径）。语义承接 archive 技术规范
> §10.7（装配虚线边界，单源化迁移欠账由本节补位）与 §8.2（`members_removable_in_situ:
> false`）。调研底稿：仓库 `research/assembly-enclosure-standard.md`（#34）。

- **语义**：围框是一组在位不可拆卸组件（装配，intent `assemblies` 段）的边界标示；
  围框是绘图抽象——不是部件、不是拓扑对象，不得作为 path 端点连接
  （负例 `negative-group-in-path` 防线同一口径）。
- **生成**：先布局成员，取**成员画出足迹（含其标签文字范围）**的包围盒加统一内距
  （≥14 px，B6 同口径）生成矩形；不做成固定尺寸符号；成员集合变化后重算。
  画在管线层之下，越框处管线压框线。
- **线宽与线型**：**1.5T 长虚线**（节距属渲染样式参数，基准 `dasharray: 8 5`）。
  条文页长虚线为基准图形；示例页链式观感不采信（印刷伪影或 manifold 可拆变体），
  原件核对若推翻，属样式参数级修订，不动线宽。
- **越框规则**：管线穿越围框仅表示成员对外接口，不表示与围框连接；管线/引线
  几何不因穿越改变（线宽仍按压力等级编码，V16 口径），穿越点必须落在成员端口。
- **标注**：装配名（`assemblies.<id>.label`，如"CDF-001 壳体回油滤装配"）画
  框外上方左对齐，与分组框标签同位同规格（框顶 - pad - 标签间距，grp-lbl 字号）。
- **与分组框的关系（拆分定档）**：`groups:` 分组框是**布局抽象**（布 lane/LRU 分区），
  降为 **1.0T**、节距不变——围框 1.5T 承载标准语义，分组框视觉退后，线宽即语义等级；
  两者数据源天然分离（intent `groups` vs `assemblies`），图上不得再同形同参。
- **流向指示**：围框不引入渲染器流向箭头（V18 维持：仅禁渲染器属 `.arw`/arrows 层，
  符号内运动箭头属受控几何）。边界流向指示默认不做；工程确认需要时走既有
  "边线 `marker-end`"机制（SysML 链路口径）另立票，不恢复独立箭头层。
- **校核口径（实现落闸门适配票）**：① 成员封闭性——围框圈入非成员即 FAIL
  （V8 扩展到 assemblies）；② 围框线宽 ≠1.5T 即 FAIL；③ 管线越框点不在成员
  端口即 FAIL；④ path 引用装配 id 即 preflight ERROR；⑤ V18 维持。

## 数值构图预算（concept 档 v1）

以两张已人工验证成品图实测打底定档（整机 SysML 图 / 1# 系统 L0 图，
实测脚本见仓库 `prototype-precheck/calibrate_profile.py`）。单一 profile 适用于概念图与放行前评审图；
评审档未来收紧时再拆（见地图迷雾区）。超限即构图不合格：修布局（扩 lane、挪分组），不是改度量口径。

| # | 指标 | 预算 | 两图实测 | 校核 |
|---|---|---|---|---|
| B1 | 线线交叉 | **恒为 0**，无桥接豁免——难避免优先改道 | 0 / 0 | 几何校核交叉计数 |
| B2 | 折返次数 | 单条走线 **≤3** 且全图 **≤40** | 整机 31 次(max3) / 1# 图 20 次(max4¹) | 同上 |
| B3 | 绕行比（路线长 ÷ 直角曼哈顿距） | 一般走线 **≤1.5**；经边界走廊进出边界端子的走线 **≤4 且须在追溯清单披露** | 除 1# 图两条油箱侧通道线(≈1.6/≈4.0¹)外全部 1.0 | 同上 |
| B4 | 最短走线段 | **≥8 px** | 10 / 15 | 直接可测 |
| B5 | 节点盒最小净距 | **≥40 px**（轴向或对角） | 52 / 52 | layout/SVG 盒间计算 |
| B6 | 容器走廊 | 分组虚线框内边距 **≥14 px**；走线绕过元件的避让走廊 **≥12 px** | group_padding=14；避让惯例 ≈12 | validate_sheet 容差外扩即可检 |
| B7 | 标签净空 | 文字边缘距最近线段/元件轮廓 **≥6 px**（配对处方：先平移到 6–8px 净空位，挪不开才垫白底框） | 主流布局满足；V12 压字即违反本条 | 回读 + 文本包围盒 |

三通实心节点只画在直段上的真实汇/分点、永不在折角（沿既有规则，量化归入几何校核）。

¹ 1# 系统图为存量历史版本：一处单条 4 折返与两条油箱侧大绕行超出本预算。存量版本按"下版改图收敛或显式披露"处理，新出图一律受本表约束。

## 追溯数据属性（生成 SVG 必带）

| 属性 | 放在哪 |
|---|---|
| `data-node="<side>.<key>"` | 元件 image/g |
| `data-port="<side>.<key>.<port_id>"` | 每个 `<circle class="port">` |
| `data-edge` + `data-sysml-line`(或 intent 锚点) | 每条连线 path |
| `data-zone` | 分区框 |

## 追溯清单

`<name>_topology.md` 两张表：

1. **连接(边)映射**：来源行号｜SysML/intent 语句｜图上的边｜实例数。
2. **节点(part)映射**：来源行号｜part 声明｜图上元件｜符号形式。

文末"简化说明"逐条披露概念级抽象（未建模的回油、边界聚合口、镜像布局约定等）。清单由渲染器在运行末尾自动生成，不手写。

## 结构自检（渲染器内置）

渲染完成前自检：每条输入 connect 有对应画出边、每个实例 part 有对应节点；任一缺失打印缺项并以退出码 1 结束，不输出成品。
