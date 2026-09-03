# 符号库与标注规范

## 库的位置（单源纪律）

组件库**只有一处**：本 skill 的 `assets/component-library/` 即**唯一规范源**——描边符号 SVG 与 `component-catalog.json` 都在这里，标注与目录修订直接发生在这里（单源化，#20/#21 定案；旧「工作区规范源→skill 快照」两处库教义随规范源归档作废，镜像工具 `sync_snapshot.py` 一同退役）。

渲染端符号解析顺序（与 SKILL.md Phase 2 同口径）：

1. **工作目录相对**——工作目录内同名文件优先（本地覆盖，传统复制纪律仍然成立）；
2. **catalog 同目录锚定**——catalog 在哪，库就在哪；不带本地 catalog 时即锚定 skill 自带库，工作目录**不再需要** `symbols/` 拷贝。

原快照闸门的端口回退检测（油箱事件：符号编辑丢失 `connection-points`）由库结构校验器承接：改动符号或 catalog 后先跑 `python scripts/check_library.py`（0 过 / 1 断；L1 合法 XML / L2 端口组与 id 唯一 / L3 catalog↔symbol 交叉硬档），再跑 selftest——详见 SKILL.md「随附资产与单源纪律」。

目录 JSON 里 `symbol.asset` 登记的是**库内文件名**（如 `check-valve.svg`），按文件名在活动库根下定位；归档时代的仓库根相对路径（`组件库/…`、`已标注/…`）已随 0.4-draft 回登记清账。绘图的语义数据以 catalog 各字段为准。

## 目录 JSON（component-catalog.json）

组件类型的单一事实来源。关键字段：`catalog_id`、`catalog_revision`、`status`、`components[]`（含 `component_type` / `connection_role` / `symbol.asset` / `symbol.symbol_status` / `ports[]`）、`drawing_blockers`。

- **只有带 `connection-points` 的符号可直接绘图**；未标注草稿不得直接用。
- `status: draft_not_frozen` 时钉号不可复现；intent 里的 `catalog:` 只能引用已冻结修订号，否则在 intent 注明。

## connection-points 标注格式

**新建/重绘符号一律复制库内 `_template.svg` 起稿**——它是技术规范 §6.3.1 的可拷贝实现（占位符 `{{...}}`），自带模板强制约束（描边几何、width/height 与 viewBox 一致且无单位、端口落在 viewBox 边界、status/source-ref 根属性、"依据/未确认项"注释）。每个符号 SVG 根元素给出 `viewBox`，体内恰好一个 `<g id="connection-points">`，每个端口一个 `<circle>`：

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 100"
     data-symbol-form="stroke_geometry" data-symbol-status="provisional">
  <g id="symbol" fill="none" stroke="#000000" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round"> ...描边图形... </g>
  <g id="connection-points" fill="#ff0000">
    <circle id="port-hydraulic" cx="30" cy="0" r="2"
            data-port-id="hydraulic_port"
            data-anchor-direction="up"
            data-port-role="pressure"
            data-medium="hydraulic"
            data-flow-capability="in"/>
  </g>
</svg>
```

属性语义（与 catalog `ports[].*` 一一对应）：

| 属性 | 取值示例 | 说明 |
|---|---|---|
| `data-port-id` | `inlet` / `outlet` / `gas_port` | 语义端口名，全网唯一引用键 |
| `data-anchor-direction` | `up/down/left/right` | 连线接入方向 |
| `data-port-role` | `pressure/return/suction/gas/...` | 功能角色 → 决定线型 |
| `data-medium` | `hydraulic/pneumatic/electrical/mechanical` | 介质 → 决定线类 |
| `data-flow-capability` | `in/out/bidirectional/none` | 流向能力（枚举以 catalog `enums` 为准） |

## 标注新符号的步骤

1. 复制库内 `_template.svg` 起稿（技术规范 §6.3.1 模板），命名 `<name>-stroke.svg`（中文类型可用中文名）；统一黑描边、无填充，`stroke-width=2` 为基准。
2. 确认 `viewBox` 收紧到图形实际包围盒——原点允许非 `(0,0)`（如油箱 `"20 10 218 564"`）。
3. 按 API 添加 `connection-points`：cx/cy 用 viewBox 用户坐标写在引线上。
4. 更新 `component-catalog.json`：该组件的 `symbol.asset` 指向新文件，`symbol_status: annotated`，`ports[]` 逐条补齐（`id` / `svg_element_id` / `medium` / `role` / `flow_capability` / `anchor_direction`）。
5. 端口契约变化属于目录修订——递增 `catalog_revision` 并在 status 里记录冻结与否。

## 方框本体基准

凡**本体为方框**的组件——单方框信封阀、多联位信封阀、方框仪表（开关/变送器）、方框接头本体——方框基准一律 **80×80**（允差 0.5，与 `_template.svg` 默认画布同源）：

| 类别 | 根属性 `data-envelope-class` | 方框规则 |
|---|---|---|
| 单方框本体（Single Envelope Valve 等） | `single` | 恰一个 **80×80** 描边闭合方框；弹簧/电机/感温包/接线盒等附件画在方框**外**，尺寸不设基准 |
| 多联位信封阀（multi） | `multi` | 每格各 **80×80**，分隔线落在 80 的整数倍（N 位合计宽 N×80） |

- **豁免**（本体非方框，省略该属性，门禁不校核）：accumulator（圆角矩形）、球式 check-valve / check-valve-spring、air-charging-valve（弓形）、quick-disconnect-coupling 配对件与原始件、pressure-gauge（圆表盘）、bootstrap 油箱。油滤的**菱形框**不是方框，同样不适用本基准。**hydraulic_user 用户名框**也豁免——它是长方形名容器（120×60 起步），尺寸随名字排版伸缩，不是信封本体。
- 信封方框是"描边闭合正方"：`fill=none`、非虚线、path 以 Z 收尾/rect/polygon。虚线框是先导回路或装配界线，不算信封。
- **附件方框**（感温包、接线盒等，含用户确认的"共边正方形"约定件）不设基准，但边长须 **< 60**（基准的 3/4），否则视为第二本体，C13 拦截。
- 门禁 **C13**（符号入库门禁 `check_symbol.py`：技术规范 6.4 第 1–12 条 + C13 方框基准）按上述判据校核：`single` 须恰有一个本体级方框（边≥60 中恰一个 80×80）；`multi` 逐格校核。该脚本暂随工作区携带，规范源归位挂账 [#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31)。
- catalog 对应字段 `symbol.envelope_class`，与根属性保持一致。

## 通用用户框（hydraulic_user）

`hydraulic-user.svg` 是"名框"符号：长方形 + 名槽文本（`data-name-slot`）+ 左右双油口（压力进口 `pressure_in` / 回油出口 `return_out`）。用户名**不在符号文件里写死**——L0 渲染器按 layout `labels` 把实例名填进框内（多行以槽位基线为中心上下展开），并省略该实例的框外标签，名字不画两遍。新增用户不需要新符号：intent `parts` 直接写 `<inst>: hydraulic_user`，layout 给节点（建议 120×60 原比例，长名字适当加宽）与标签即可。名框不受 §方框本体基准 80×80 约束（见上豁免）。

## 读端口坐标的正确姿势

渲染端读端口时必须处理 viewBox 原点偏移与缩放（照抄参考实现的 `read_symbol()`）：

```python
vb = [float(v) for v in root.get('viewBox').replace(',', ' ').split()]
# cx,cy 是 viewBox 用户坐标; 放置时: 画布坐标 = 放置点 + (用户坐标 - vb[0:2]) * scale
```

不在渲染器里硬编码任何端口坐标——符号改版后硬编码即静默失真。
