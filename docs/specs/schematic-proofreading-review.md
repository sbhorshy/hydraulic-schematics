# 绘图后校对增强 · 双轴评审

以下保留修复前的两个独立评审轴，引用代码位置对应冻结版本 `ff212000df32c8f7ef3c281f004a0904cf29f6c9`。所有项已由同一修复分支处理，再由其他代理独立复验；最终运行时代码为 `a903a04b8a86530c505f7de6108eeb46f09c4fa3`。

复现 JSON 是隔离测试的历史证据，其中模拟签认仅用于验证门禁，不是正式图纸签认。回归输入、CLI 用例与修复代码均随技能发布。[气侧宽度](schematic-proofreading-evidence/before-gas-width.json)、[虚线引线](schematic-proofreading-evidence/before-dashed-lead.json)、[过粗本体](schematic-proofreading-evidence/before-fat-body.json)、[百分比异常](schematic-proofreading-evidence/before-percentage-stroke.log)及[故意损坏图像对照](schematic-proofreading-evidence/before-lead-body-comparison.png)保留了修复前的观察。

## Standards

Reviewed all 38 changed files in `e9b6be85...ff212000df32c8f7ef3c281f004a0904cf29f6c9`, against the listed repository standards and full Fowler baseline. Implementation remained read-only; pending fixes are not credited.

1. **P1 — Required local review disappears with its manifest.** [proofreading_evidence.py:175](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/scripts/proofreading_evidence.py#L175) infers “not required” from absence; line 186 then ignores the recorded READBACK_ITEMS requirement. This violates [SKILL.md:15](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/SKILL.md#L15) and [validation.md:305](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/references/validation.md#L305). In an isolated fixture with simulated whole-sheet approval, deleting only the manifest makes 17 unviewed items disappear and `delivery.ready=true`, including after copied-validator revalidation. Persist the requirement independently of that file. [Reproduction](schematic-proofreading-evidence/before-deleted-readback.json).

2. **P1 — Transparent paint counts as actual connectivity.** [topology_reconciliation.py:109](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/scripts/topology_reconciliation.py#L109), [stroke_checks.py:22](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/scripts/stroke_checks.py#L22), and browser body-contact eligibility special-case transparent black. `rgba(255,0,0,0)` removes pipe ink but V10/V15/V16 pass and automation reports complete, contrary to [validation.md:128](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/references/validation.md#L128). Parse effective color alpha; disclose unknown paint. [Frozen-head recheck](schematic-proofreading-evidence/before-transparent-pipe.json).

3. **P1 — Actual selected symbol is not fingerprinted.** [proofreading_evidence.py:76](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/scripts/proofreading_evidence.py#L76) resolves paths differently from `endpoint_usage.resolve_symbol`. Accepted `symbols\edp-provisional-stroke.svg` loads the catalog asset but records `sha256=null`; editing that asset leaves verification current. This breaches [SKILL.md:48](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/SKILL.md#L48) and [validation.md:56](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/references/validation.md#L56). Reuse the actual resolver and reject unbound assets. [Reproduction](schematic-proofreading-evidence/before-symbol-binding.json).

4. **P2 — Traceability Markdown omits required structure/counts.** [topology_reconciliation.py:53](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/scripts/topology_reconciliation.py#L53) emits one mixed table without instance counts. [SKILL.md:80](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/SKILL.md#L80) and [rendering-rules.md:108](https://github.com/sbhorshy/hydraulic-schematics/blob/ff212000df32c8f7ef3c281f004a0904cf29f6c9/.agents/skills/hydraulic-schematic/references/rendering-rules.md#L108) require node/edge mapping tables with source/count information. Split those tables, retaining auxiliary port/bus mappings; existing anchors themselves are present.

5. **Heuristic — Duplicated Code.** Neutral paint decoding and asset resolution are copied across the hunks above and `endpoint_usage.py:186`, `junction_semantics.py:80`, `text_checks.py:98`; divergence caused findings 2–3. Share neutral parsing/resolution, preserving different dot, frame, red-marker and lead policies. This is a design judgement, not an undocumented style mandate.

Total: **4 documented breaches + 1 linked heuristic; highest severity P1.** Known gas-lead/orphan-paragraph fixes remain outside this frozen HEAD.

## Spec

Reviewed `e9b6be8...ff21200` against `docs/specs/schematic-proofreading.md`; read-only review plus isolated real CLI/Chrome PNG probes. Seven findings; no unrequested scope identified. Script paths below are relative to `.agents/skills/hydraulic-schematic/scripts/`.

1. **P1 — Transparent connections receive a visible-graph pass.** #65, spec:36: “从可见 SVG 几何及已校核端口建立实际连接关系”. `topology_reconciliation.py:109` and `stroke_checks.py:22` exclude only literal transparent black. `rgba(255,0,0,0)` pipes/leads remain counted and measured: V10/V15/V16 pass despite absent PNG ink. Decode effective paint alpha consistently; unsupported paint must remain unchecked. Evidence: `review-standards-transparent-pipe/result.json`, `root-alpha-lead-probe/root-finding.json`.

2. **P1 — Deleting local-review evidence unlocks delivery.** #71, spec:129: “存在未完成的必检项时，完整驱动器不能宣告交付通过”. `proofreading_evidence.py:175–189` treats a missing manifest as legacy optional use even after READBACK_ITEMS was required. The retained probe changes `delivery.ready` false→true by deleting it. Preserve the requirement independently. Evidence: `ticket-09-missing-manifest-probe/run/root-finding.json`.

3. **P1 — Actual Windows-style symbol paths escape version binding.** #71, spec:127: “实际使用的目录/符号…具有内容指纹或等价版本标识”. `proofreading_evidence.py:76–79` does not share `endpoint_usage.py:14–18` resolution. A selected backslash-path asset gets a null hash; editing that actual asset leaves verification current. Reuse actual resolution. Evidence: `review-standards-symbol-path/result.json`.

4. **P2 — Gas leads are omitted.** #68, spec:79: “外接引线跟随所在管网”. `stroke_checks.py:120` skips nonhydraulic ports; PG-001’s connected sense lead at 12px still passes V15/V16. Include all connected media and both tap ends. Evidence: `root-gas-lead-probe/root-finding.json`.

5. **P2 — Dashed leads are certified continuous.** #68, spec:81: “结合相接管线类别、端口身份及符号边界核对线宽连续性”. `stroke_checks.py:153–176` uses complete geometric spans without computed dash evidence. PF-001 inlet `2px 12px` dashes produce a visible gap yet exit0/V16 pass. Validate continuous painted coverage.

6. **P2 — Body/mechanism widths are never checked.** #68, spec:79: “阀体轮廓和内部机构保持各自规定线宽”. `stroke_checks.py:88–97` checks only network classes; later checks only external leads. Changing PF-001’s body/internal strokes to 12px leaves exit0/V15/V16 pass and an unreadable black body. Measure role-specific body widths.

7. **P2 — Valid percentage stroke crashes instead of disclosing unsupported measurement.** #68, spec:84: “不支持的 SVG 构造…明确列为未校核并说明对象”. `topology_reconciliation.py:110` calls `float('0.2%')`; validator exits with a traceback and no report. Parse supported units or emit localized `not_checked`.

New-probe evidence: `spec-extra-probes/{dashed-lead,fat-body,percentage-stroke}/run/`; the first two include fresh PNGs/reports, the third `probe.log`. `review-spec-probes.py` reproduces the first two; `spec-extra-probes/lead-body-comparison.png` was visually inspected.

**Spec total: 7. Worst within this axis: P1 invisible connections certified as measured topology.**

## 整改验收

| 问题 | 整改 | 独立复验 |
|---|---|---|
| 透明管网、引线和本体接触 | 共享中性描画解析，处理实际 alpha；未知描画明确未校核 | 透明线不再贡献连通或引线证据，真实 PNG 负例失败 |
| 删除局部清单绕过 | 新校核固定要求 READBACK_ITEMS，不以文件存在决定义务 | 删除清单、再次校核均保持阻断 |
| Windows 符号路径漏绑 | 与实际读取共用路径解析，拒绝未绑定的必需符号及旧坏冻结包 | 改动实际符号立即失效，旧包不可比较 |
| 气侧漏检 | 从实际相接网络取宽，覆盖 taps 两端 | 4 个气侧口均 1T，12px 负例失败 |
| 虚线引线空档 | 按规定连续描画检查，不能仅凭完整几何段通过 | 虚线负例 V16 失败 |
| 本体/机构过粗与基本图元漏测 | 按 1.5T 测量常见图元；补偿源内等比缩放 | 圆、椭圆、矩形、多边形 12px 均失败，等比缩放正例通过；不支持变换明确未校核 |
| 百分比描边异常 | 无法量化的单位输出对象、位置和原因 | 正常生成报告，V10/V15/V16 明确未校核 |
| 追溯表格式 | 连接与节点分表，逻辑边实例数与绘图片段分开 | CLI 输出满足要求，辅助端口/母线映射与 unknown 保留 |

复验与不可变提交 `8dfc23b` 绑定；其树与集成运行时 `a903a04b8a86530c505f7de6108eeb46f09c4fa3` 完全一致。[Standards 独立复验记录](schematic-proofreading-evidence/standards-fixed.json)。

Standards：4 项规范违例和 1 项关联启发式观察，最高 P1，均已处理。Spec：7 项，最高 P1，均已处理。两个轴分别报告，不合并排序。
