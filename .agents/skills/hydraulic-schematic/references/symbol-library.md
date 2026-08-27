# 符号库与标注规范

## 库的两种位置

| 位置 | 角色 | 判定 |
|---|---|---|
| `<工作区>/已标注/`（含 `component-catalog.json`） | **规范源**：标注、目录修订都发生在这里 | 工作区存在即优先 |
| 本 skill `assets/component-library/` | 自包含快照，供 skill 被带到其他工作区时使用 | 仅当工作区没有库 |

符号/目录/脚本快照的刷新统一走 `scripts/sync_snapshot.py`（含端口回退闸门，用法见 SKILL.md「随附资产与快照同步」）——仓库里做完修订后跑 `--apply` 即可。

目录 JSON 里 `symbol.asset` 的路径相对仓库根（如 `组件库/Check Valve.svg` 指未标注草稿、`已标注/*-stroke.svg` 指已标注符号）。在 skill 快照里这些路径不解析——**按文件名在活动库根下定位**即可，绘图的语义数据以 catalog 各字段为准。

## 目录 JSON（component-catalog.json）

组件类型的单一事实来源。关键字段：`catalog_id`、`catalog_revision`、`status`、`components[]`（含 `component_type` / `connection_role` / `symbol.asset` / `symbol.symbol_status` / `ports[]`）、`drawing_blockers`。

- **只有带 `connection-points` 的符号可直接绘图**；未标注草稿不得直接用。
- `status: draft_not_frozen` 时钉号不可复现；intent 里的 `catalog:` 只能引用已冻结修订号，否则在 intent 注明。

## connection-points 标注格式

每个符号 SVG 根元素给出 `viewBox`，体内恰好一个 `<g id="connection-points">`，每个端口一个 `<circle>`：

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 100">
  <g id="body"> ...描边图形(path/rect/circle/polyline...)... </g>
  <g id="connection-points">
    <circle id="port-hydraulic"
            data-port-id="hydraulic_port"
            data-anchor-direction="down"
            data-port-role="pressure"
            data-medium="hydraulic"
            cx="30" cy="100" r="4"/>
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

## 标注新符号的步骤

1. 从根目录或 draft 草稿复制到 `已标注/`，命名 `<name>-stroke.svg`（中文类型可用中文名），统一黑描边、无填充。
2. 确认 `viewBox` 收紧到图形实际包围盒——原点允许非 `(0,0)`（如油箱 `"20 10 218 564"`）。
3. 按 API 添加 `connection-points`：cx/cy 用 viewBox 用户坐标写在引线上。
4. 更新 `component-catalog.json`：该组件的 `symbol.asset` 指向新文件，`symbol_status: annotated`，`ports[]` 逐条补齐（`id` / `svg_element_id` / `medium` / `role` / `flow_capability` / `anchor_direction`）。
5. 端口契约变化属于目录修订——递增 `catalog_revision` 并在 status 里记录冻结与否。

## 读端口坐标的正确姿势

渲染端读端口时必须处理 viewBox 原点偏移与缩放（照抄参考实现的 `read_symbol()`）：

```python
vb = [float(v) for v in root.get('viewBox').replace(',', ' ').split()]
# cx,cy 是 viewBox 用户坐标; 放置时: 画布坐标 = 放置点 + (用户坐标 - vb[0:2]) * scale
```

不在渲染器里硬编码任何端口坐标——符号改版后硬编码即静默失真。
