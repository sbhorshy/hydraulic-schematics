# #63 步骤二：mirror_policy 接入渲染与实际几何校验

日期：2026-10-12 ｜ 工作目录：`.scratch/glm-followup-20261012/mirror` ｜ 用例先写，Bash 权限缺失，由 Codex 实跑验证。

## 结论

镜像策略（步骤一的 `mirror_policy.py`）已接入渲染、几何读取与整图校核；**生产 catalog 仍未启用任何镜像条目**（两种泵仅作为临时 catalog 副本在测试中登记），1# seed 布局未改，无 UI 改动。用户条件解禁依据 `../mirror-decision.json`（逐组件登记、保留端口身份、记录镜像操作）。

## Review 修复（../mirror-contract-review.log 37 项中唯一失败）

- `test_mirror_policy.MirrorTransformChainTest._chain`：`scale(-1,1)scale(1)` 缺分隔空格——夹具改为条件拼接（空串不带空格，非空段后补一空格），helper 返回约定与"无镜像空串"未动，无镜像链仍与现网逐字节一致。
- 措辞："逐组件工程解禁签认" → "逐组件镜像许可登记"（模块头注与 `check_mirror` 报文各一处）：登记是用户已签条件政策下的许可记录，不伪造逐只工程签名、不提升 provisional。
- `test_catalog_pumps_are_not_enabled_yet`：改为目录条目**临时副本显式删除许可字段**的负例，不再断言生产 catalog 现状，后续合法登记上线不会把测试写死。

## 接入点（先读调用点，未扫历史资料）

1. **render_l0_sheet.py**
   - `Sheet.place()` 逐实例以 intent 类型 + 实际解析资产调用 `check_mirror`（替换原"已禁用 mirror"硬拒），拒绝未登记/旧资产/非法轴；归零缩放端口坐标先 `mirror_point`、锚向 `mirror_anchor`，再沿用原旋转/平移；端口 key(inst,pid) 与 role/medium/flow 不换。
   - `symbols()` 仅对获准镜像插入 `mirror_svg_transform` 于 rotate 之后、scale(k) 之前；非镜像变换串与 markup 逐字节不变（含 `mirror_attr` 仅在镜像时输出）。
   - 实例 `<g>` 记录 `data-mirror` 与 `data-mirror-input-anchor="nodes.<inst>.mirror"`；renderer stdout 与追溯清单（`1#系统原理图-topology.md` 新增"镜像操作披露"节）披露镜像状态并明示不提升成熟度。
   - main 的 symbol_contract 阶段并入 `mirror_contract` 审计，违法走既有 `write_contract_failure` 出口（退出码 1，不出图）；`place()` 的 ValueError 以 `sys.exit(str)` 干净失败。
2. **sheet_geometry.py**
   - `load_geometry(root, layout, resolve_symbol, mirror_axes=None)`：默认仍拒绝一切反射；传入逐实例已校验许可时，要求 layout 轴与许可轴一致、实际 SVG 矩阵与声明姿态（旋转/等比缩放/非零 viewBox 原点/平移，`declared_instance_matrix`，容差 0.01 仅吸收 %g 序列化舍入）相符。缺失镜像、错误轴（含"声明 y 实际反射 x"的点名报文）、未声明负矩阵、非许可下的非均匀/非正交/退化均入 `issues`（经 `check_endpoints` 成为 V3 硬 FAIL，非 not_checked）。无镜像路径行为不变。
3. **validate_sheet.py**
   - contract 阶段调 `mirror_contract`（endpoint_usage 新函数，渲染/校核共用），违法硬失败，concept 不豁免；`load_geometry` 传入许可；原 180 行后旧端口坐标循环同步 `mirror_point`/`mirror_anchor`，消除新旧两套口径。
4. **assembly_checks.py / assembly_layout.py**
   - `render_enclosures(..., mirror_axes=None)` 透传许可给 `load_geometry`，正确量测获准镜像成员；renderer 调用点已跟随。
   - R17 `source_node` 仍不自动镜像，但参照节点请求 `mirror` 时**显式拒绝**（不再静默丢弃、不换端口）。
5. **依赖清单**
   - `validate_driver.SCRIPTS`、`test_entrypoints.make_render_workspace` 复制清单补 `mirror_policy.py`；`proofreading_evidence.build_snapshot` 的 tool 指纹为 `tool_dir/*.py` 通配（排除 test_/selftest），`sheet_version` 冻结按 `tool:*` 跟随，无需改清单。

## 测试

- 新增 `scripts/test_mirror_render.py`（已注册 `selftest.L0_SUITES`）：
  - 单元：两泵真实符号 x/y×四旋转端口/锚独立推导对账；非零 viewBox（20 10 80 40）+0.5 缩放含手算字面量；symbols() 变换串全串断言与端口身份元数据不交换；未登记/非法值/错轴/失效登记（改资产字节）拒绝；`load_geometry` 许可放行/默认拒绝/未声明反射/轴不符/姿态漂移/声明缺反射/无镜像回归。
  - CLI（真实子进程）：临时 catalog 按实际 SVG/hash 签入两泵；小基准图 EDP `mirror=y` rot0 正例——左右主口位置/锚向保持（suction 570,530、pressure_out 650,530），validate 0 fail，manifest 披露；无镜像输出与生产 catalog 渲染逐字节一致；未登记/非法值/失效登记三负例 contract 级退出 1 不出图；成品 SVG 被改成错误反射轴或未声明反射时 validator 明确 V3 FAIL。
- `selftest.L0_SUITES` 原 24 模块全保留，追加 `test_mirror_policy`、`test_mirror_render`；SKILL.md、selftest.py、selftest_runner.py、tests/scheduler/test_selftest_runner.py 头注的"仅 24"绝对数全部改为"以 L0_SUITES 注册表为准"。

## 待 Codex 实跑

1. `python -m unittest -v test_mirror_policy`（37 项应全绿）
2. `python -m unittest -v test_mirror_render`
3. `python .agents/skills/hydraulic-schematic/scripts/selftest.py`（F 组现 26 套件）
4. 回归重点：`test_entrypoints`、`test_port_geometry`、`test_assemblies`、`test_assembly_layout`、`test_driver`

## 未做 / 下一步

- 生产 catalog 登记与 1# seed 应用（下一步单独评估"登记与试图"）；UI 未动；驱动器处方表未加镜像条目（镜像违法在渲染/contract 阶段即失败，不进收敛轮次）。
