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

### B4/B5/B6：实际走线与足迹预算（#70）

`layout_clearance.py` 复用 `sheet_geometry` 的最终根 SVG 足迹以及 V10 的可见
线段/顶点/输入锚点。坐标已包含 canvas shift，不再从 layout 的 w/h 或 rot 重建。
预算保持 B4 ≥8、B5 ≥40、B6 分组内距 ≥14 / 避让走廊 ≥12 SVG 单位；
超限仍为 V19 警告，原有 V2 穿体等硬失败不受影响。

- B4 在同一逻辑输入边内合并共线连续存储段；不同 SVG line/polyline 的相接
  不自动成为折点。端口、实际分支、真转角、反向折返和桥弧端部保留为语义边界。
  `runs` 与 `nearest_run` 给出锚点、两端、实际长度、SVG ID 和图顶点索引。
- B5 按实际变换后的源符号 viewBox 足迹求矩形间欧氏净距；90°/270°、缩放、
  非零 viewBox 原点及最终实例移动均通过共享几何处理。`nearest` 保留组件对、
  足迹、最短距离两侧定位点及 `deficit`。
- B6 对可见直线段和规范半圆跨线桥测距。半圆距离使用浏览器实测弧方向与范围，
  不用弦线代替弧。仅正确沿锚向离开自身已声明端口的连续直线段可豁免自身接入
  走廊；其余折段仍检查该组件。`nearest_corridor` 与 `corridors.violations`
  定位输入连接、障碍组件、线段/桥 ID、两侧最近点、实际距离和差额。
- 分组框增加非可视 `data-group` 身份；`nearest_group` 和 `groups` 对照本轮浏览器
  实际框与归一化成员足迹测内距。配置里的 `group_padding` 不作为实测值。
  没有分组时 `B6.group_padding` 为不适用；缺框、隐藏框或无法测量时明确未校核。

`B6.avoid_corridor` 提供独立覆盖证据、实测对数、终端豁免理由及未测对象；完整
  自动校核不再把该项一概视为缺失。无浏览器证据或遇到不支持的实际几何时仍
  `not_checked`，不会以部分最小值代替完整通过。预算面板保留原有字段，新增
  定位详情；`not_measured` 只列本轮实际尚未完成的项目。

### 悬空红圈实际显示（#67）

V5 复用同一份浏览器证据检查每个输入定义的悬空红圈，覆盖样式表、祖先
`display`/透明度及最终 `visibility`，并检查描边/填充确有非零的红色描画。
浏览器测得的接点坐标继续采用根 SVG 坐标和原 0.2 单位容差；旋转及画布平移不改变端口清单。
报告的 `marker_display` 给出逐端口可见性、颜色、透明度、描边宽度、位置及结果。
红色以已解析 RGB 的红通道大于绿/蓝通道两倍判定；不支持的颜色、绘制服务或裁剪/遮罩/滤镜
明确列入 `unchecked`。缺少实际测量时 V5 为 `not_checked`，已确定的漏圈、计数、图签或契约错误仍然失败。

V6/V7/V8 使用相同的实际足迹约定：V6 将实际组件足迹和可见管线范围与根 SVG
viewBox 对账，报告对象及各边超出量；V7 对照本轮图例/图签矩形，V8 对照实际
分组矩形检查非成员。所有坐标均为根 SVG 坐标，既不重复加 shift，也不从布局
重造未旋转框。V7 管线压框仍沿原先 >8 单位口径；确定隐藏或无有效轮廓的已声明
分组框触发定位到分组的 V8 失败，B6 内距保持未校核，单独填充不能代替框线。无有效描画的图例/图签矩形
不作为可见遮挡物。实际框缺失、无法解析描画、非正交变换或裁剪/遮罩/滤镜，
以及尚未量化的局部桥弧压框，明确标为未校核。文字自身范围仍由文字测量检查负责，
不以组件/管线边界检查替代文字回读。

### V4/V14：真实三通、交叉与桥弧（#66）

`junction_semantics.check_junctions(topology, browser)` 返回结构化 findings 与
V4/V14 覆盖证据。`input_networks` 从声明端口和母线归并导出网络身份；
`intersection_events` 从实际管段的方向、位置与输入锚点识别真实分支、非连通交叉
和错误的端部/T 形接触。三通圆点自身的属性、母线 x 坐标均不能证明连接合法。
坐标为根 SVG 用户单位，位置容差沿用 0.1 的序列化舍入口径。

- 同一输入网络的三向/四向汇合需要一个实际可见、有效填色的实心点；普通二度
  拐角、直线中段和偏离接点的位置不能放点。不同网络的交叉放点仍是失败，不能
  把缺桥问题消成通过。图例与符号内部的点、桥示例不参与系统管网校核。
- 点的位置、填色、透明度以及祖先显示效果来自共享浏览器证据。空心、透明、
  白色或 CSS 隐藏的点不能计作已画；不支持的绘制服务、裁剪/遮罩/滤镜明确未校核。
- 非连通交叉须有居中、连续、具有有效描边的水平跨越桥。桥两端必须抵达实际
  相邻管段，桥下不能保留原直线；桥不能割断真实汇合。桥错位、缺失、无实际交叉、
  错误归属、透明/白色/虚断描边分别定位报告。
- 删除桥弧留下的面对断口仅用于发现待诊断交叉，不会补画连接或令 V10 通过。
  桥弧 `data-edge` 不能改变它实际接上的管段归属。

规范渲染器依据输入网络与走线路径自动生成母线和共享干线三通点（包括离开母线的
吸油分叉），并保留 `data-edges` 来源锚点。真正同网四向交点会由实际直线几何
生成拓扑顶点，供 B4 保留真实分支边界；圆点不能为不同网络制造拓扑顶点。

报告 V4/V14 evidence 保留 `junctions`、`crossings`、`bridged`、`unbridged` 计数，
并增加 `events`、`expected_junctions`、`markers`、`bridges`、`unchecked`。
事件含 `position`、`input_anchors`、`networks`、`directions`；失败附涉及连接与
实际位置。上游拓扑尚未对账或显示能力不足时不能宣告完整覆盖，已确定的错误仍失败。


B1 的既定“非连通交叉恒为 0、跨线桥不豁免”政策保持不变；计数复用已核对的
实际交叉事件。因此桥画法正确可以 V14 通过，同时 B1/V19 仍报告交叉预算失败。
面对断口只用于诊断缺桥，不会被当作已经画出的完整走线或制造 B1 通过证据。

候选优化器的 B1 同样使用渲染器拆桥前的非连通交点数，绝不因桥留出空隙而计零。
候选评估只使用输入与走线几何，不启动浏览器；其余搜索指标与阈值不改，最终完整
SVG/显示校核仍为权威。真实优化器 CLI 的单次种子评估与最终桥图 B1 有回归对账。

### 实际文字、容器与净空（#69）

V12/B7 复用同一次 Chrome 采集。原生字符基点、锚定和旋转配合 Canvas 实际字形度量，
产生 `ink_quads`/`ink_bbox`；原生 `bbox` 仍保留为布局框。两者分开，避免把字体行框的留白误判为多行文字重叠。
所有文字、图元轮廓、吸油斜杠和定位坐标使用根 SVG 用户单位；V17 不再使用估算文字框。

V12 检查文字与管线/图元/其他文字的实际重叠、越出画布及自身容器；B7 按原 6 单位规则报告净空不足，
concept 档净空不足记 V19 WARN，实际压字/越界记 V12 FAIL。直线和矩形边精确测量，曲线轮廓采样间距不超过 0.25 单位，
阈值比较仅留 0.001 单位的浏览器浮点误差量。`text_geometry` 保存文字、实际框、字体、归属、容器和净空记录；
每个 finding 给出冲突对象、距离/差额或越界量。B7 在构图预算与覆盖清单中反映实际测量状态。

用户文本槽和符号内部文字按实例及最近结构容器归属；圆形容器使用真实圆边界。
同一标签的行距属于排版，仍检查实际文字相互重叠，外部 6 单位净空不套在同一多行标签的行间。
独立标签进入其他符号内部会报冲突。图例、图签和边界标签均纳入；图签默认三行且仍为 11px，
边界标签移到三角外 6 单位以上净空的位置，不通过缩小字号通过校核。

PNG 自动导出优先采用与测量一致的 Chrome。PNG receipt、浏览器缓存与产物版本绑定安装字体的内容指纹及本地 CSS 资源；
字体或字体文件变化会刷新缓存并使旧证据失效。PNG 与当前测量的后端、版本或字体版本不匹配时，文字项明确未校核。
缺 Chrome、无可用字形度量、垂直/RTL 字形、textLength 调整、嵌套的不同字形变换及未解析的裁剪/遮罩/滤镜均披露为未校核，
不以估算值补成通过。Fontconfig 不可用时不复用文字测量缓存；无法匹配 PNG 字体版本时保留未校核状态。


文字完整性独立于空间碰撞：按 layout 声明的组件/边界标签、实际符号源的内部文字/用户名槽及图签元数据建立必需文字清单。
缺失、内容不符、CSS 隐藏、透明或没有可见字形描画的必需文字触发 V12；无实际范围的项保持 B7 未校核，不能以观测到零条文字作为通过。
组件标签使用 `data-label-for="INSTANCE"`，边界标签使用 `data-label-for="@EXTERN_ID"`；槽内文字沿实际 `inst-INSTANCE` 归属。
`text_geometry.texts[].owner` 为 `symbol:INSTANCE`、`label:INSTANCE`、`label:@EXTERN_ID`、`title`、`legend` 或独立 DOM key，供局部回读与差分归属复用。


气侧引线与其他外接引线按实际相接管网取宽：`sense` 为 1.0T。介质为 pneumatic
不构成线宽豁免。渲染器记录 taps 的 sensor/at 两端归属，已有主网归属保留；
校核器仍会明确报告不兼容的相接线宽。V15 同时检查已测外接引线是否在规定线宽内，
V16 检查与相接管网及本体边界的连续性。未接端口不编造网络，本体与指针等内部机构保持原规定线宽。
### 本轮 PNG 的局部回读清单（#72）

完整驱动器在最后一轮校核后生成 `readback.html` 和 `readback-manifest.json`，
自动校核有残差时同样生成。一次最终 PNG 导出后，Pillow 只解码一次并批量裁图，
不为每个端口启动渲染器；输出对象数、裁图数及耗时。已有 SVG/PNG 可独立运行：

```bash
python <skill>/scripts/readback_review.py generate <workdir>
python <skill>/scripts/readback_review.py verify <workdir>
```

仅使用已通过版本验证的报告与 PNG。清单覆盖全部声明端口、外部接口、系统接点/
交叉/桥弧、所有元件全貌（包含复杂符号）以及自动失败、警告和未校核疑点。
端口上下文包含已测得的引线/本体边界；相邻小区域合并后仍逐对象记录覆盖关系，
大型元件全貌作为独立上下文。未取得几何或目标位于图外时明确保留未覆盖记录。
无可靠局部定位的疑点指向全图，不编造坐标。默认局部为 4× 最近邻 PNG 像素；
可用 `--scale 1..8` 调整。页面是静态审阅报告，局部链接会高亮全图对应 ROI，
不是交互编辑器；像素嵌入页面，外部同名文件替换不会悄悄替换页面中的已绑定图像。

每项默认为 `unviewed`。看过相应局部后，显式记录对象 ID、结论、审阅人及备注：

```bash
python <skill>/scripts/readback_review.py record-item <workdir> port:PRV-001.inlet \
  --decision questioned --reviewer "Reviewer" --note "接点线宽需确认"
```

结论支持 `confirmed` / `questioned` / `unviewed`，可显式列出多个对象 ID；没有
自动“全部确认”。记录绑定当前输入/图像/自动证据、裁图内容及清单，更新后仍能
重校核而不形成指纹循环。`READBACK_ITEMS` 与 `PERCEPTUAL` 同属独立审阅状态，
不参与稳定自动校核签名。清单、任一实际裁图或静态页面被替换后拒绝沿用有效确认。

逐项记录保存在 `readback-items-review.json` 的版本历史；图像位于
`readback/<绑定版本>/`。同一内容版本重新生成或驱动器 `--keep` 重跑会保留显式
结论；源内容改变则新清单默认未查看。需要保留审阅历史时使用驱动器既有 `--keep`。

局部生成不写入整图感知签认；看过整图也不自动确认所有局部。二者分别显示于
`phases.perceptual` / `phases.local_readback`。有当前清单时，任何未查看、存疑、
未覆盖或失效项都会通过 `READBACK_ITEMS` 阻断完整交付；没有清单的独立旧用法
仍遵循原整图签认契约。自动几何失败仍保留原失败出口，局部图供定位，不替代修复。

### 版本影响与图像差分（#73）

`sheet_diff.py` 通过独立 CLI 先冻结完整证据，再比较两个版本。冻结目录保留原始
SVG、PNG、校核报告、目录/实际符号及运行脚本内容，同时复制本地 CSS URL 字体资源；
后续编辑规范源或工作目录不会改写历史版本。源记录必须先通过 `verify_report`
的 current 和 PNG pass 门禁。冻结版本的 current 表示快照字节与原记录一致，
不是重新执行旧工具。每次比较输出独立 `before/`、`after/` 快照，禁止覆盖已有结果。

```bash
python <skill>/scripts/sheet_diff.py freeze <旧工作目录> --output <旧版快照目录>
python <skill>/scripts/sheet_diff.py verify <旧版快照目录>
python <skill>/scripts/sheet_diff.py compare <旧版快照目录> <当前工作目录> \
  --scope <scope.json> --output <独立差分目录>
```

范围文件示例见 `assets/examples/change-scope-local.json` 与 `change-scope-global.json`。
`nodes` 使用实例 ID，`edges` 使用 `paths[i][k->k+1]`、`taps[i]` 或 `buses.NAME`。
`include_adjacent_edges: true` 只展开直接连接目标节点的输入边，不扩展整个网络或其他节点；
母线变化须单独声明。`global: true` 明确授权全图呈现变化，但不会自动授权换口。
所有范围须有说明 `note`，不接受矩形忽略区或用户绘制的大面积 mask。

默认要求声明连接、实际连通网、节点/端口契约及追溯锚点保持一致。
即使意外换口位于目标节点或相邻边内，也会报告 `unexpected_topology`。
确有意图改变拓扑时，须把该边显式列入 `edges`，并逐条给出
`topology_changes: {"paths[1][0->1]": {"before": ["EDP-001.pressure_out", "PF-001.inlet"],
"after": ["EDP-001.pressure_out", "PF-001.outlet"]}}`。两个端点组必须同时与各版
输入定义和实际连接一致；范围许可不能掩盖与输入不符的接管。

差分直接读取两版已核实的 PNG。局部许可像素来自两版允许对象的实际描画并集，
不使用对象占位矩形或空间膨胀；对象自身的独立变化仍逐项对账，所以旁边对象的变化
即使落在许可墨迹内也不能被吞掉。每版本最多一次批量范围栅格化，与对象数量无关；
全局比较或无像素变化时无需补充栅格化。原始 PNG 不重新生成。
默认每通道容差为 8/255，`--pixel-threshold` 可设为 0–16；低于容差的非零变化数仍披露。
局部范围重绘前要求历史安装字体内容版本仍可用，本地字体从冻结副本重定位；
字体环境不一致、未知 paint/use/滤镜等范围描画、画布/viewBox 或 PNG 尺寸不能可靠对齐时，
明确输出 `not_comparable` 和原因，不输出“无差异”。全局 PNG 比较不需要重绘旧字体。

输出 `change-report.json`、可读的 `change-report.md` 和 `diff-overlay.png`。
报告包含变化节点/连接、前后对象坐标、输入/实际拓扑差异、授权与越域项、像素连通区域、
容差、全图比较范围和实际耗时/栅格化次数。黄色为范围内变化，红色为范围外变化。
比较退出码：0 范围内，1 有越域或未授权拓扑变化，2 不可比/证据失效。
差分通过不替代两版完整校核，也不签认感知回读；报告保留各版校核/交付状态。

完整驱动器可在本轮正式校核后追加差分：

```bash
python <skill>/scripts/validate_driver.py --intent <intent.yaml> --layout-seed <layout.json> \
  --workdir <独立工作目录> --compare-against <已冻结的旧版目录> \
  --change-scope <scope.json> --comparison-output <新的独立差分目录>
```

驱动器基准必须冻结且与本轮工作目录分离；省略 `--comparison-output` 时新建独立临时目录。
`convergence-report.json.change_comparison` 指向结果；差分越域使交付阻断（退出 1），
不可比则保留未齐备状态（退出 4），已有输入/几何/工具失败继续保留。差分通过仍不消除
PERCEPTUAL 等独立交付阻断项。可复现的 CLI 正反例位于 `test_sheet_diff.py`：
引线修复、旋转与关联走线、目标范围内错口、另一元件变化、字体替换、画布不可比、
源锚点丢失、PNG 篡改和字体资源失效。
