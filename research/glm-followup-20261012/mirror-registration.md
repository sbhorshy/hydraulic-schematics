# #63 步骤三：两泵生产登记（规范源 + 1# 工作目录）

日期：2026-10-12 ｜ 工作目录：`.scratch/glm-followup-20261012/mirror` ｜ 只 Read/Edit/Write，未执行 Python/git，由 Codex 实跑验证。

## 结论

`engine_driven_pump` 与 `electric_motor_driven_pump` 两类组件按 #63 条件解禁政策完成生产登记：两份 catalog（规范源 `.agents/skills/hydraulic-schematic/assets/component-library/component-catalog.json` 与 `1#系统原理图/component-catalog.json`）各自加 `mirror_safe: true`、`layout.allow_mirror: true`、`mirror_registration`（axes `['x','y']`，摘要绑定各自符号真实原始字节与端口契约）。**不改 SVG、不改端口契约、不提升 provisional、不动 UI、不动 1# seed、不动跳线。**

政策与事实依据（登记 note 在 catalog 内逐字引用）：

- 用户政策 `../mirror-decision.json`（2026-10-12）：条件解禁——逐组件登记允许镜像，保留端口身份并记录镜像操作。登记是**政策许可记录，不是逐组件工程签认**，`symbol_status` 维持 provisional 不因镜像提升。
- 源事实 `../mirror-source-facts.json`：两泵符号无内部文字；整体反射后泵压力三角仍指向 `pressure_out`；四端口 id/role/medium/flow_capability 身份全保留（EDP `drive_shaft` 机械口、EMP `elec_power` 电气口均不得冒充 `case_drain` 溢流口）。

## 登记清单（原始 hash 逐字取自 ../mirror-source-facts.json）

| 组件 | 目录 | 资产 | asset_sha256 | ports_sha256 |
|---|---|---|---|---|
| engine_driven_pump | 规范源 | `edp-provisional-stroke.svg` | `c65046221c863ebb68bc449b0c14622451ff32698738895670651cfe639e66fb` | `678bb3e4ba438225032b874721f1850175a5d8950eaed6cc18c39f7ada46a7df` |
| engine_driven_pump | 1# | `symbols/edp-provisional-stroke.svg` | `134414e3efa5adfc73e55ed39c30bae9433c1e7767b502e9b789860f5512c07b` | `678bb3e4ba438225032b874721f1850175a5d8950eaed6cc18c39f7ada46a7df` |
| electric_motor_driven_pump | 规范源 | `emp-provisional-stroke.svg` | `abd66309a9f86fb68c1095796fef516b799ce5eb78205854cd1add3b8ac7756b` | `fed45b70d01d3d6e5baf09340c89f533a29db9e000f366be931c7a2e14abcb60` |
| electric_motor_driven_pump | 1# | `symbols/emp-provisional-stroke.svg` | `e12e5fb728ce2763ab1071c80639d155460e858b70b5ed674c1e7d8e61670e34` | `fed45b70d01d3d6e5baf09340c89f533a29db9e000f366be931c7a2e14abcb60` |

### 原始 hash 差异（不弱化绑定）

- 两目录的同名符号资产内容仅**行尾 CRLF** 不同（`project_canonical_equal_after_crlf_normalization: true`），原始字节摘要因此不同；两份登记**各自绑定本目录文件的真实 rawhash**，不共用、不归一化——一侧复制另一侧的 hash 会在 `check_mirror` 的资产闸上暴露（校验按当前文件实读字节重算）。
- 两目录两泵的 ports 数组逐字一致（diff 验证），故 ports_sha256 相同；`port_contract_digest` 只取 id/svg_element_id/medium/role/flow_capability/anchor_direction/port_kind 七键，两泵端口均无 port_kind/role_note 参与摘要。
- 两 catalog 既有其他差异（`catalog_revision` 0.7-draft vs 0.3-draft、资产路径 `symbols/` 前缀、两泵 symbol.note 文案）与本登记无关，未改动。

## 文档与头注同步

- `scripts/mirror_policy.py` 头注：删去"生产 catalog 目前没有任何启用条目"，改为生产启用现状（仅两泵、两目录各自绑定真实字节、其余默认禁止）。
- `references/rendering-rules.md`：6.3.3 装位旋转条目的"不得镜像"改为 #63 条件解禁口径（三道闸、端口身份不变、data-mirror 追溯、当前登记范围、R17/自动布局不产出镜像）；"局部回路 + 水平镜像"条目补注这是 SysML 链路整图 `<image>` 翻转技法，与逐组件登记镜像互不相干。
- `SKILL.md` Phase 2：补 L0 镜像默认禁止/三道闸/当前登记范围/SysML 整图翻转不经此闸。

## 测试

- `scripts/test_mirror_policy.py`
  - `test_catalog_pumps_are_not_enabled_yet` → `test_explicitly_unregistered_entry_rejects_mirror`（临时副本显式剥离许可字段，负例意图不变，不再以"未启用"命名）。
  - 新增 `ProductionRegistrationTest`：仅两泵带 `mirror_safe`；两泵以真实 catalog 条目 + 真实库内资产过 `check_mirror` x/y；其余全部类型默认拒绝。摘要不写字面量——`check_mirror` 按当前文件字节对账，登记漂移即失败。skill 内自足，随便携拷贝运行。
- `scripts/test_mirror_render.py`
  - 模块头注改为"临时 catalog/条目副本上构造或剥离登记，不写生产文件；生产现状由仓库级测试断言"。
  - 新增 `_unregistered()` 助手；`test_place_rejects_unregistered_production_entry` → `test_place_rejects_explicitly_unregistered_entry`；`test_cli_contract_failure_without_registration` → `test_cli_contract_failure_on_explicitly_unregistered_catalog`（原写回生产 catalog 期待拒绝——登记后会翻转成通过，改为显式剥离两泵许可字段的临时目录，负例意图保留）。
- 新增 `tests/repository/test_mirror_registration.py`（仓库级，不随 skill 分发）：两目录各自 only-two-pumps 清单断言、两泵以**各自目录的真实符号文件**过 `check_mirror` x/y（共用 hash 在此暴露）、其余类型默认拒绝。`tests/repository/README.md` 目录说明同步。

## 待 Codex 实跑

1. `python -m unittest -v test_mirror_policy`（含新 ProductionRegistrationTest；摘要与文件字节不符会在此失败——hash 值逐字取自事实文件，本机未执行哈希）
2. `python -m unittest -v test_mirror_render`
3. `python -m unittest discover -s tests/repository -v`（含新 test_mirror_registration）
4. `python .agents/skills/hydraulic-schematic/scripts/check_library.py`（catalog 已改，L1–L3 须仍绿）
5. `python .agents/skills/hydraulic-schematic/scripts/selftest.py`（F 组）

## 未做 / 下一步

- 1# seed 布局未应用任何 mirror；UI/编辑器未动；跳线未动；provisional/draft 成熟度未提升；驱动器处方表未加镜像条目（镜像违法在渲染/contract 阶段即失败）。
- "试图"（在 1# 系统图上实际应用镜像的评估）与后续组件的逐个登记，另步单独评估，不在本步范围。
