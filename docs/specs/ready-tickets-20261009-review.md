# 后续工单双轴审查

原始审查固定区间 `f3a00952...48d6f640`；后续修复统一由同一代理在独立分支完成，再由另一代理合入最终受测代码。下文保留两轴结论，各自计数不互相抵消。原文中的工作目录路径是审查时的位置，相关归档副本见本批证据目录。

## Standards

审查范围：`f3a00952...48d6f640` 的完整变更；规范以 skill 的 `SKILL.md`、`references/` 为准，结合 AGENTS/领域约定。历史大体量机器日志仅核验关键证据与声明；未重跑全量测试。

**硬性规范违反（2 项）**

1. **[P2] 可选形状检查缺席时，非法装配被预检放行。** `.agents/skills/hydraulic-schematic/scripts/preflight.py:149–158` 把装配形状完全交给 schema（`continue  # shape errors are reported by schema`），语义层没有核对 label 与最少成员数。仓库支持 `jsonschema` 缺失时仅 WARN；在该受支持环境中，用当前装配夹具删除 label 或只留一个成员，均返回 `ok=true / cleared_for_layout / products_withheld=[]`。这违反 `references/validation.md`「装配检查（#39）」的“label、成员数量…由 preflight 拦截（concept 同样 ERROR）”，以及 `CONTEXT.md` 的“装配至少两个成员”。应在语义层保证这些装配不变式，或让装配所需形状检查不可用时明确阻断。

2. **[P3] 坐标系声明缺失时被静默补义。** `.agents/skills/hydraulic-schematic/scripts/layout_contract.py:37` 使用 `layout.get('coordinate_system','root_svg_user_units')`，当前 seed 删除此键仍被接受，正常入口会按根坐标解释。`references/rendering-rules.md`「L0 坐标契约（#23）」要求布局声明 `coordinate_system`，且“不静默猜测坐标系”。应要求该字段存在且等于受支持值，缺失时给迁移提示。

**Smell baseline（判断性启发）**：未发现值得单列的新增 smell；兼容薄入口符合单源纪律，不据 Middle Man 启发判错。

定向复现：`formal-review-standards-evidence/reproduce.py`；结果见同目录 `reproduce.log`。未修改源码、合并或发布；既有已披露图纸残差与未签认状态不重复计为本次规范发现。


处置：两项均修复。装配不变式独立于可选 schema 执行；坐标声明显式必需。明确的 `--declare-root` 修复保留原坐标，未知声明在正常与旧 SHIFT 迁移分支都拒绝。原始反例与修复后针对性验收保留，[最终独立验收](ready-tickets-20261009-evidence/final-fix-independent-review.md)。仓库专有测试与可分发技能测试边界亦已修复。

## Spec

# Spec 审查

审查固定差异：`f3a00952fd5d13fffe85db4740c00fd064d60918...48d6f640ed60e63c8bca734dc04e4cf2bf8c3323`。范围：#23/#39/#42/#44/#46/#49/#62；依据原工单正文、评论、#22/#35/#37/#38 等既定口径及本批规格。七票发布前快照与原始快照全文一致。

**1 条发现：#23 验收仍为部分完成（关闭工单前须保留缺口）。**

规格原文：**“到站链全量回归：fail 0、B 面板不劣于到站水平（B3 ≤1.447、B4/B5 不压线）”**（`docs/specs/ready-tickets-20261009.md:33`）。#22 决议明确到站链是 1# 输入端到端，原结果 fail 0、B3=1.447、B4=16、B5=43。

现有 `../issue-23-evidence/final-comparison.json` 的 1# `l0-current` 实测为 **13→13 FAIL，B5=24 / over**；活动项目对等比较仍为 **6→6 FAIL**。small、assembly、rotation 的零失败正例证明各自行为，不是原 1# 到站链复现。因此当前证明了迁移不回归，尚未证明票面这一项已完成。摘要保存于 `../formal-review-spec-evidence/acceptance-summary.json`。这些是已披露的既存残差，不归因为本次坐标修改，也不要求本批擅自展开 #47；应保持 #23 此验收项未勾选，待具备当前 1# 到站证据再闭环。后续 selftest 全绿本身不等价于此项通过。

其余未发现可确认的需求遗漏、范围扩张或实现错误。核对了装配语义/围框/单行布局、旋转路由及同角预算矩阵、蓄压器三边拓扑、油箱退役与坐标迁移接缝。#44 的 94 文件同源历史证明复用已明确披露，不视为本次环境等价或新跑全量证明。

本审查只读实现与相关证据，未重跑全量测试。整合全量回归与人工工程/感知签认仍是独立门禁；没有用历史日志宣称最终交付通过。


处置：该项没有宣称修复。后续对当前实际端口与输入进行了独立旋转系统验证，确认禁镜像与零交叉约束同时阻断当前 1# 到站目标。实现已发布，#23 保持开放；[证明](../../research/ready-work-20261009/arrival-23/README.md)。

总计：Standards 2 项发现、0 项未解决，最严重 P2 已修复；Spec 1 项发现、1 项未完成，为 #23 到站验收。自动测试与图纸工程签认分别记录。
