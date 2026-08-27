# 校验闭环

三层，逐层通过才交付。前两层是确定性门禁（不看图只算），第三层是感知校核。

## 1. 渲染器结构自检（退出码门禁）

渲染器末尾自检：输入定义里的每条 connect 都有对应画出边；每个实例化 part 都有对应节点。任一缺失 → 打印缺项清单、退出码 1、不产出成品。这是第一道闸，任何改动后先跑渲染脚本本身。

## 2. 几何校核 `validate_sheet.py`

模板：skill `scripts/validate_sheet.py`（原位在仓库 `已标注/1#系统原理图/`，以那里为规范源）。

- 只算几何不动图：线段穿越元件矩形检测（`seg_rect_hit`）、orphan 节点、net 连通性等。
- 产出 `validation-report.json`，每项判定附坐标或 ID（检查项编号 V1, V2, ...），供人工复核与回归对比。
- 对 intent/layout/svg 三件套互相核对：intent 中每条 path 有边可对，图上无边多画。
- 脚本按 HERE 相对路径找输入（同级 svg/layout、上级 intent/catalog）——复制到工作目录后先改这几个常量再运行。
- 退出码 1 = validation: failed。
- 同模式可写专项测试（如 `scripts/test_suction_markers.py` 验吸油路径标记传播）。

负例（故意画错的样例，用于确认校验逻辑能报红）随 skill 附带：`assets/examples/negative-*.intent.yaml` + 对应 `.expected-report.json`。改校验逻辑时先跑它们确认能红。

## 3. 感知回读（PNG）

1. 用 Chrome headless 或 Inkscape 把 SVG 光栅化为 PNG。
2. 逐分区读图确认：符号未变形、镜像正确、走线无穿越、标签/端口点对位、图签图例齐全。
3. 回读发现的每个疑点要修正后重新光栅化再回读；一次都跳过不得——validate_sheet 明确规定"无回读图的校核项记为未校核，不静默放过"。

## 交付判据

- 渲染脚本退出码 0；
- `validation-report.json` 全绿；
- 最新一版 PNG 已人工级回读且记录在哪张图上校了什么。

三者齐备才宣告完成；修图必须重跑全链路（自检 → 几何 → 回读）。
