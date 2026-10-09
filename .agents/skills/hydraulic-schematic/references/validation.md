# 校验闭环

三层，逐层通过才交付。前两层是确定性门禁（不看图只算），第三层是感知校核。

## 1. 渲染器结构自检（退出码门禁）

渲染器末尾自检：输入定义里的每条 connect 都有对应画出边；每个实例化 part 都有对应节点。任一缺失 → 打印缺项清单、退出码 1、不产出成品。这是第一道闸，任何改动后先跑渲染脚本本身。

## 2. 几何校核 `validate_sheet.py`

模板：skill `scripts/validate_sheet.py` 即规范源（单源化，#20 定案；工作区历史副本不再是规范源）。#21 起首选免复制运行：`python <skill>/scripts/validate_sheet.py <workdir>`，报告落 `<workdir>/validation-report.json`。

- 只算几何不动图：线段穿越元件矩形检测（`seg_rect_hit`）、orphan 节点、net 连通性等。
- 产出 `validation-report.json`，每项判定附坐标或 ID（检查项编号 V1, V2, ...），供人工复核与回归对比。
- 对 intent/layout/svg 三件套互相核对：intent 中每条 path 有边可对，图上无边多画。
- 脚本按 HERE 相对路径找输入（同级 svg/layout、上级 intent/catalog）——就地/复制运行时先改这几个常量（历史复制纪律兼容；首选上一条的免复制工作目录参数）。
- 退出码 1 = validation: failed。
- `validation`、`checks`、`fail_count`、`warn_count` 保留原含义：已执行检查的结果。完整覆盖读 `coverage`：`pass`、`fail`、`warn`、`not_checked`、`not_applicable`；后两者必须带原因，零失败可以同时存在未校核项。
- 自动测量完成状态读 `phases.automated`；感知状态读 `phases.perceptual`。独立几何 CLI 允许在缺 PNG 或可选测量能力时返回 0 并披露 `not_checked`，交付以 `delivery.ready` 为准。
- 同模式可写专项测试（如 `scripts/test_suction_markers.py` 验吸油路径标记传播）。

负例（故意画错的样例，用于确认校验逻辑能报红）随 skill 附带：`assets/examples/negative-*.intent.yaml` + 对应 `.expected-report.json`。改校验逻辑时先跑它们确认能红。

### V2/V3 实际接管几何（#64）

`sheet_geometry.load_geometry(svg_root, layout, resolve_symbol)` 是供校核复用的边界：
使用最终 SVG 的实例及祖先累积变换、实际采用的符号文件端口与 viewBox，返回
`nodes[实例].{matrix,footprint,ports}`、`pipes[].points` 和 `issues`。端口记录
`position`、已旋转的单位 `direction`、`anchor_direction`、`role`、`medium`。
所有结果和报告定位采用 **root SVG 用户坐标**，包含 `sheet` 的画布偏移；不能再加一次
`canvas_shift_x`。`footprint` 是变换后的符号 viewBox 足迹，不是未旋转的 layout 占位框，
也不声称测量了轮廓墨迹。`walk`/`transform`/`multiply`/`point` 可用于同坐标系的后续校核。

V3 按输入 `paths` 相邻连接的声明端口（裸实例只按目录 `main_path` 展开）及 `taps`
两端逐口检查实际管段端点、首末段的外向锚向及管线自身折返。连接锚点格式为
`paths[i][k->k+1]` 或 `taps[i]`；失败包含组件、端口、定位、实测误差/管段。
端点的欧氏距离容差固定为 **0.1 用户单位**，仅覆盖 SVG 坐标保留一位小数产生的
最大约 0.071 单位误差，报告同时记录该值和原因。2 单位断口、反向接管和 6 单位折返
均阻断通过。此检查不代替逐边拓扑对账：错误连接仍使用相同端口集合的情况由后续对账检查负责。

V2 对归一化后的整条管段裁切求交；端点仅接近某个边界坐标不构成豁免。
仅真实首末端口的接管段、沿该端口向外锚向，允许离开其自身符号足迹；不豁免其他本体
或路线中间段。旋转、缩放、非零 viewBox 原点及最终 SVG 的额外平移均共用归一化结果。
不支持的变换或管线构造明确报错，不能记作通过；当前管线几何支持 `line`/`polyline`，
曲线路径接管尚不支持。报告 `geometry` 暴露本轮归一化证据；几何通过仍不代表感知回读完成。

专项回归：`python -m unittest test_port_geometry`（在 `scripts/` 运行），已纳入 `selftest.py`。

## 3. 感知回读（PNG）

1. 用 `python <skill>/scripts/rasterize_sheet.py <svg> -o <workdir>/sheet-readback.png` 光栅化；自动选择本机 Inkscape 或 Chrome，并核对 PNG 与 viewBox 的 1:1 尺寸。驱动器每轮自动执行。
2. 逐分区读图确认：符号未变形、镜像正确、走线无穿越、标签/端口点对位、图签图例齐全。
3. 回读发现的每个疑点要修正后重新光栅化再回读；一次都跳过不得——validate_sheet 明确规定"无回读图的校核项记为未校核，不静默放过"。
4. 先运行 `python <skill>/scripts/proofreading_evidence.py verify <workdir>` 核实报告与图像版本。读完当前图后用 `record-review <workdir> --reviewer <姓名> --decision confirmed --note <实际检查内容>` 记录明确结论；有疑点使用 `questioned`。随后重新运行校核，使报告显示本轮签认状态。

输入、布局、实际采用的 catalog/符号、脚本和依赖版本、SVG、PNG 均按 SHA-256 绑定。PNG 旁的 `.evidence.json` 记录光栅化来源；报告旁的 `.sha256` 校验报告内容。回读记录绑定产物指纹和自动校核证据。修改或替换任一产物后先重新渲染、光栅化、校核；旧回读显示 `invalidated`。内容未变可复用回读，但每次驱动仍执行正式校核。导出 PNG 只生成证据，感知状态仍为 `pending`。

局部图或版本差分消费者通过 `proofreading_evidence.verify_report(workdir)` 核实版本，要求 `status=current` 且 `png.status=pass` 后读取图像。新增测量检查在自身 evidence 记录中提供 `coverage_status` 和 `coverage_detail`；未实现或测量不可用时填 `not_checked`。实际失败始终覆盖显式通过状态。

## 4. 有界收敛：修正最多两轮

发现缺陷 → 修图 → 重跑全链路（自检 → 几何 → 回读）记为一轮定点修正，修正**最多两轮**：

- 每轮只修上一轮列出的缺陷，不夹带改布局方案、换符号之类的动作——那是在造新的缺陷源，等于重新出图。
- 两轮后 `validation-report.json` 仍未全绿或回读仍有疑点：**停手**。产出"未收敛项清单"，每项附
  检查项编号、坐标或 ID、两轮间的观察对比，交工程师决策；不得开第三轮盲改。
- 未收敛即未交付：带未收敛项宣告完成视同违反不变式第 4 条（此约束同规范 §10.10.4 与上游 SKILL.md）。

## 5. 缺陷→修法处方对照表

只收已实际发生过的失效模式；新缺陷先走完一轮"观察→定位→修法验证"，确认有效后再补进本表。

| 缺陷 | 在哪层暴露 | 修法处方 |
|---|---|---|
| 走线穿符号本体 | validate_sheet 穿越检测（seg_rect_hit）+ 回读 | 在元件矩形外缘 ≥12px 的走廊里加 H/V 折返段绕行；不改符号尺寸、不压盒距、不画斜线 |
| 管线越端口折返留线头 | 回读放大端口区；几何上路径末点 ≠ 端口坐标 | 最后一段沿进入方向以端口坐标为终点直落；需反向进入时先到端口外 ≥10px 处折返，仍以端口为末点——禁止越过端口再回头 |
| 三通点画在拐角 | 回读（实心点落在折角处） | 主线保持一条直段穿过汇/分点，支线垂直落到该直段上；实心节点取直段上的交点——拐角只是折返，永不是节点 |
| 标签/分组框互压 | 回读逐分区比对 | 先平移标签到净空位（距线 6–8px，与所指示件对齐）；挪不开才给文字垫白底框；都不行说明布局过密，回头扩 lane 间距，不缩字号了事 |
| 图例遮内容 | 回读全图边带 | 加高画布、图例/图签整体下移到内容带下方并留 ≥20px 隔离带；挤压内容坐标给图例腾地方是禁止项 |
| 镜像锚点未取反 | 回读镜像侧符号方向颠倒 | 盒子左缘与 `<image>` transform 必须成对改：左缘用 `LOCAL_W − bx − bw` 让出宽度，同时加 `transform="translate(2ax+bw 0) scale(-1 1)"` |

## 交付判据

- 渲染脚本退出码 0；
- `validation-report.json` 全绿；
- 最新一版 PNG 已人工级回读且记录在哪张图上校了什么。

驱动器 `converged=true` 保留“已执行检查零失败”的兼容含义；完整自动测量查看 `automated_validation.status`，交付查看 `delivery.ready`。必检项未校核或感知未签认时退出码为 4（证据未齐备）；0 仅表示完整证据通过，1/2/3 继续表示几何残差、输入残差、工具故障。

三者齐备才宣告完成；修图必须重跑全链路（自检 → 几何 → 回读），且总轮数受「有界收敛」两轮上限约束——
两轮后仍不收敛的，交付物是未收敛项清单与工程师决策请求，不是图。

### V10：输入追溯与可见连接对账

规范 L0 渲染器自动生成 `1#系统原理图-topology.json` 与同名 `.md`。
JSON 的 `nodes`、`ports`、`edges`、`buses`、`externs` 和 `fragments` 给出输入锚点与 SVG ID；
`unknown` 原样披露，不生成连接。节点为 `parts.INSTANCE`，端口为该节点经目录类型
派生的 `parts.INSTANCE.ports.PORT`（同时保留 `catalog_anchor`），外部口为
`extern.NAME`。逻辑边锚点为 `paths[i][k->k+1]` 或 `taps[i]`。
母线是路径中 `@NAME` 的合并绘图抽象，锚点 `buses.NAME` 的 `input_anchors`
列出全部来源；它不声称 intent 有额外的 buses 定义。

裸实例作为一条边的起点展开 `main_path.out`，终点展开 `main_path.in`；
路径中间实例的入、出口属于两条不同边，不穿过组件内部合并网络。
母线主干不计额外逻辑边；桥弧和连续折线拆段保留原边锚点。
端口复用非可视 `<metadata>`，坐标仍为局部符号坐标，配合实际实例变换读取。
所有归一化报告坐标为 **root_svg_user_units**，已经包含 canvas shift。

`topology_reconciliation.declared_topology(intent, catalog)` 返回输入清单；
`reconcile_topology(root, geometry, intent, catalog, layout, browser_evidence=None)`
返回相同清单并附加 `expected_edges`、`actual_edges`、`segments`、`vertices`、
`networks`、`bridges`、`findings` 和 `coverage_status`。
完整结果保存在 `validation-report.json.topology`。消费者可使用：

- `actual_edges`：`anchor`、实际 `endpoints`、`svg_ids`、端部 `positions`、`segments` 索引。
- `segments`：`start/end` 根 SVG 坐标、`a/b` 顶点索引、`svg_id`、输入 `anchor`、`bridge`。
- `vertices`：`position`、实际 `terminals`、`degree`。
- `networks`：整个可见网络的 `terminals`、关联输入 `anchors` 与 `segments`。
- `bridges`：实际弧的 `position`、两端 `endpoints`、`svg_id` 和 `anchor`。

`data-edge` 只关联输入与绘图片段，不能证明连接成立。V10 从可见线段、桥弧及
目录端口位置重新建立几何邻接，检查每组的连续性、真实端口/母线归属，以及
整图是否把两个独立输入网络意外接在一起。0.1 SVG 单位容差仅补偿渲染小数舍入。
重叠共享主干不增逻辑边；同一条边自身重复、未知额外管线、缺失/重复/无法解析
的节点、端口和边锚点分别报告。桥弧必须有真实连续端点；交叉处的点/桥语义由 V4
进一步校核，V10 不将图例桥弧当成系统管线。

可见性使用本轮 `browser_evidence.collect` 的计算后 CSS、实际变换及透明度。
隐藏/无描边的线不能贡献实际连接；没有浏览器测量、遇到无法处理的裁剪/遮罩/
滤镜或端口 CSS 变换时，V10 明确 `not_checked`。追溯文件也纳入内容指纹，
篡改后旧校核失效。PNG 与感知签认仍是独立证据，V10 通过不代替回读。

### 实际显示线宽证据（#68）

`V15`/`V16` 从一次 Chrome 测量取得最终 CSS、完整变换及实际端点接触；
支持 line、polyline 以及 M/L/H/V（含相对命令、多子路径）的引线。
校核按符号源端口和源中定义的完整外接引线范围独立取样，不相信 `pl-*` 类名，
因此 CSS 覆盖、补偿遗漏或空白引线中途改回本体线宽均可定位。
源中的嵌套等比缩放由渲染器补偿，引线按所属管网取宽；本体与内部机构样式保持原约定。
位置容差 0.1 SVG 单位沿用一位小数输出口径，线宽误差限 0.02 SVG 单位。
边界接触使用浏览器原生描边/填充命中（含实际线帽范围），不使用任意半径内有墨迹作通过依据。

`browser_evidence.collect(svg_path, output=None, timeout=30)` 对单个 SVG 批量测量所有可见图元、
文字和 tspan，缓存 `browser-evidence.json`。记录含 SVG/采集器/Chrome 版本指纹和内容完整性摘要，
并纳入校核报告的产物快照；修改 SVG、采集器或证据后不能复用旧结论。
每个元素的 `matrix`、`bbox`、`client_bbox`、`characters` 均映射到根 SVG 用户坐标，
`local_bbox` 保留 [x,y,width,height]；根坐标包围盒为 [x0,y0,x1,y1]。
`visible` 综合最终 visibility、祖先 display/opacity 及非绘制定义容器；
描边/填充是否有墨迹还须检查 `style` 中 stroke/fill 与各自 opacity。
字体完成加载后一次取得文字度量，相关检查复用该份证据。

缺 Chrome、不能解析的引线、use、裁剪/遮罩/滤镜及未获得独立本体接触证据的对象，
在 V16 `unchecked` 中报告组件、端口和位置，覆盖状态为 `not_checked`。
这些测量证明自动校核完成，不替代 PNG 人工感知签认。
回归通过真实 Chrome 的 1×/2× PNG 检查引线/管网 1:1、本体/压力引线约 1:2；
采用累计灰度墨量，显式容许抗锯齿差异（比例误差 0.12/0.15）。
