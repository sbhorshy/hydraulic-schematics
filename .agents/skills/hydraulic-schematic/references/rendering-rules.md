# 渲染规则

## 输入定义（二选一，勿混用）

**SysML 链路**（整机）：`.sysml` v2 文本。解析 `part`（实例化层次：如 `greenCircuit:HydraulicCircuit`）与 `connect a.b to c.d` 语句；记录每条语句的行号用于追溯。平台/概念级简化允许存在，但必须披露（见追溯清单"简化说明"）。

**L0 链路**（分系统）：`intent.yaml` 章节：

```yaml
l0_version / system / catalog / maturity
extern:      # 系统边界(地面接头等必然开口)
parts:       # id: component_type —— 只收目录内类型
paths:       # 连接; 目录外类型不得出现(L0 规范)
groups:      # 布 lane 用分组
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
- 符号经 `<image>` 引用并按盒缩放，href 相对**活动库根**（工作区库写作 `已标注/xxx.svg`；用 skill 快照时相对其 `assets/component-library/`）；目录外或未标注符号画干净描边框图（box+标注），在图签栏披露。
- 分区框 `<rect data-zone>` + 分区标题（如 GREEN CIRCUIT / 绿系统）。
- 标签中英双行（`油箱\nReservoir`），中文主名；字体 fallback `"Microsoft YaHei","Noto Sans CJK SC",sans-serif`。
- 图签栏（title block）必含：来源文件、范围、成熟度及免责声明（`成熟度: concept 概念图,非工程放行图`）；图例框列全各类线型。

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
