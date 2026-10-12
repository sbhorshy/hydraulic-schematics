# #63/#23 编辑器与跳线审核修复（2026-10-12 第二轮：六点复审）

范围：按用户复审清单逐点修复，不重新设计。GLM 写实现，Codex 实跑验收。
反例与日志：`../editor-permission-review.json`、`../probe-editor-permission.py`、
`../editor-tests-first.log`、`../bridge-single-tests-first.log`。

## 1 严重：写前授权绕过（YAML 口径分裂）

**根因（真实复现）**：`server._mirror_permission_issues` 用 PyYAML `safe_load`
（YAML 1.1）解析 intent，而 canonical 链（preflight/render）用 ruamel YAML 1.2。
合法未加引号实例 ID `ON` 被 PyYAML 解析成 bool `True`，`intent['parts']` 的键
因此是 `True` 而不是 `'ON'`；`mirror_contract` 对不在 `intent['parts']` 的实例
`continue` 跳过——`ON` 的未登记镜像过闸写盘，随后 render（ruamel，`ON` 是
字符串、在 parts 内）才报 contract 失败。同场景 `EDP-001`（非 1.1 拼写）则
正确 permission 拒绝且文件不变，证明分歧只在解析口径。

**修复（editor-proto/server.py）**：
- `_mirror_permission_issues` 改用 `render_l0_sheet.load_yaml`（ruamel
  YAML 1.2，与随后的渲染**同一函数同一口径**），不引入第三种解析；
- 新增 `selected` 参数：本次操作节点缺失于 `intent.parts` 或实例类型未在
  目录登记，直接产出 issue 在写盘前拒绝——不再依赖 `mirror_contract` 对
  缺失实例的 continue 跳过（intent 非 dict/parts 非映射也 fail-closed）；
- `_connection_counts`（连线提示）同改 canonical 加载：ON 拼写实例不再被
  PyYAML 强转后计成 0 连线。

**回归（tests/repository/test_editor_mirror.py，快速用例仅 stub `_run`，
加载/登记/原子写入全真）**：
- `test_yaml11_bool_spelling_ids_cannot_bypass_permission`：ON/OFF/No 三种
  1.1 布尔拼写，未登记 + 混合移动（dx=30）→ stage=permission，layout 字节、
  `layout_version`、`revision_log` 长度均不变；
- `test_yaml11_bool_spelling_id_registered_mirror_still_works`：登记在案时
  拼写 ID 照常 mirror=y 落盘（修复不误拒合法未加引号 ID）；
- `test_node_missing_from_intent_parts_rejects_before_write`（missing intent
  node 反例）与 `test_instance_type_missing_from_catalog_rejects_before_write`。

## 2 apply_delta mirror 请求类型边界（不只 HTTP Handler）

- 函数入口与 Handler 统一为 `not isinstance(mirror, str) or mirror not in
  ('none','x','y')`：None（缺省）=保持姿态；False/0/True/1.5/容器/'z' 无写入
  拒绝（stage=delta / request）——不靠 truthiness；
- `_node_mirror_axis` 不再把存量 `mirror:false` 当 none：值域外声明整事务
  拒绝（stage=delta），杜绝"移动/'none' 请求把非法值 pop 掉"的洗白路径；
  合法 `'none'`（移除镜像）继续允许，mirror_policy 读侧的存量兼容口径未动
  （编辑器是唯一写路径，写侧从严即闭环）。

**回归**：`test_function_entry_rejects_non_string_mirror_requests`（False/0/
True/1.5/list/dict/'z' 直调 apply_delta，字节不变）、
`test_current_layout_illegal_mirror_false_is_rejected_not_laundered`
（mirror:false 存量 + None/'none'/'x' 三种触碰都拒、字节不动）、HTTP 层
bad 元组补 False 与 dict。

## 3 V19 evidence 与 B1 item 同口径（#23）

`validate_sheet.py`：新增单值 `b1_verified_disclosed = b1_verified_count
if covered else 0`，B1 item 与 V19 evidence 两处出口共用——不再出现
"B1 item 置 0、V19 仍挂未过滤计数 1"的分裂。假接点/虚线桥/unknown marker
（covered=False）时两处都为 0；`measured`/`crossings` 仍保留真实原始计数，
判定预算（allowance/gaps 逻辑）未动。

**回归（test_bridge_allowance.py）**：新增 `v19()`/`assert_same_verified_
disclosure()`，覆盖 covered 正例（verified 1/2）与三个 not-covered 负例
（假 dot、unknown marker、虚线桥 → 双出口 0）。
`tests/repository/test_bridge_single_allowance.py` 两用例均 covered=True，
断言值不受影响。

## 4 UI 时限与 busy（editor-proto/index.html）

- `api(path, opts, timeoutMs)` 分离口径：GET（/api/sheet、/api/layout）保持
  5s 快速失败；POST /api/delta 用 `DELTA_TIMEOUT_MS = 300000*3 + 20000`——
  服务端 `_run` 各阶段 300s（render/rasterize/validate 至多 3×300s）+ 启动
  /IO 余量，客户端时限晚于服务端自身超时，"链路超时"由服务端 JSON 如实
  回答，客户端不抢先 abort 成未知态（本机实链 ~13s，挂载盘更慢；不是把
  5 改 10）；
- busy 状态：请求在途时状态行明示、四个操作按钮 disabled、`startDrag`/
  `postDelta` 忽略新拖拽与重复提交（连点/双击）、keydown `ev.repeat` 不连发；
- 超时/断连：`refreshAfterUnknown()` 重读 /api/sheet 按当前盘面换帧，读取
  失败则明示"状态未知"；banner 明确"是否已写盘未知（不声称回滚）"，绝不
  声称已回退/未写盘。

## 5 setSide 拒绝分级 + M 键守卫（index.html + server.py）

- `stateText(d)` 分级：permission/delta/request=未写盘；render=已落盘但
  渲染/链路失败（server 端 render 失败响应现在附带 `layout_meta`，版本/
  日志如实更新）；server=落盘状态未知；ok+passed=完整通过；ok+!passed=
  已落盘校核未全过。不再一律"未过闸（无成品，手调已落盘）"；
- `showRejection(res)`：permission/delta/request/busy 显示实际
  `res.error`（render_stderr 仅作后备），红绿点/layout 版本/revision_log/
  issues 列表保持上一成功态，画布不换帧——拒绝不冒充任何落盘结果；
- M 键循环 none→x→y→none：输入框/TEXTAREA/下拉/contenteditable 焦点、任意
  修饰键（**含 Shift**）、`ev.repeat` 均不触发；R 键同守卫（原版 R 完全
  裸奔，焦点在栅格下拉时按 r 会直接旋转）。无新增导出。

## 6 repo 测试 setup 修复（../editor-tests-first.log、../bridge-single-tests-first.log）

- `test_editor_mirror.py`/`test_bridge_single_allowance.py`：setUpClass 里
  `cls.addCleanup(...)`（实例方法误用）→ `cls.addClassCleanup(...)`；
- `make_render_workspace` 自建 `root/'run'`：三处调用改传已存在的 tmp 根
  （原 `Path(tmp)/'run'` 造成不存在的 `run/run` 父路径），公共 helper 未动；
- setUpClass 的 rasterize 命令补 SVG 位置参数（与 `server._run` 同形
  `<svg> -o <png>`），且 `rasterize_sheet.py` 不在工作区拷贝清单内，改用
  skill 规范源脚本路径；真实链与断言保持（validate/rc==0 等断言未放松）。
- setUp 增恢复 intent/catalog 基线字节（新增的反例测试会改写它们）。

## Codex 实跑清单（本轮验收，全绿前不冻结）

```
python -m unittest -v tests.repository.test_editor_mirror tests.repository.test_bridge_single_allowance
python -m unittest -v tests.repository.test_editor_rotation tests.repository.test_mirror_registration
python .agents/skills/hydraulic-schematic/scripts/test_mirror_render.py
python .agents/skills/hydraulic-schematic/scripts/test_bridge_allowance.py
python .agents/skills/hydraulic-schematic/scripts/selftest.py      # F 组全套
python .agents/skills/hydraulic-schematic/scripts/check_library.py
# 1# 候选完整验收（冻结来源前）：
python .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py "1#系统原理图"
python .agents/skills/hydraulic-schematic/scripts/validate_sheet.py "1#系统原理图"
```

浏览器侧（4/5 点）由人工或 Codex 浏览器会话实跑核对：镜像 POST 期间按钮
禁用与 busy 文案、>5s 链路不再被客户端 5s 放弃、超时后画布按盘面刷新或
明示未知、permission 拒绝显示服务器 error 且不更新成功态、M 在 Shift/输入
焦点/长按重复下不触发。不以 mock 立即返回冒充浏览器通过。
