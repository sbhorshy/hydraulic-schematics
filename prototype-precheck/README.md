# 输入契约前置：三形态最小原型对比报告（#4 HITL 决策材料）

同一份坏输入 `inputs/bad-mixed.intent.yaml`（7 类违规：结构手误 ×1、目录漂移、sensing_only 串主路、
main_path=null 裸实例 ×2、显式端口不存在、未声明实例、medium 兼容），三个形态各做一版最小原型，
跑同一正例对照（system-1 修正 catalog 字段副本，预期全绿放行）。

复现：`python run_all.py`（原始输出存 `results/out-*`）。

## 结果总览

| 形态 | 工件 | 行数 | 坏输入 | 正例 | 发现数 |
|---|---|---|---|---|---|
| A 独立工具 | `form-a/l0-input-contract.schema.json` + `precheck_a.py` | 61+197 | rc=1 | rc=0 | 结构 1 + 语义 7 |
| B 内置断言层 | `form-b/form_b_preflight.py`（渲染器 main() 插 3 行钩子） | 171 | rc=1 | rc=0 | 语义 7 |
| H 混合 | 复用 A 的 schema + import B 的 preflight 核心，`hybrid_precheck.py` 仅胶水 | 63 | rc=1 | rc=0 | 结构 1 + 语义 7 |

三个形态的**发现集完全等价**（语义引擎同一套规则），差异全部在架构位置与体验上。

## 维度对比

**1. 强制力（TANK-001 教训的核心）**
- A：外挂工具，忘记跑=不设防。只能靠 CI/钩子补强制。
- B：渲染器 parse 后立即断言，想绕都绕不开；报告里明示"扣留产物 layout/svg/topology.md"。
- H：与 B 同级——正式实现时渲染器调用的就是这段核心。

**2. 报错体验**
- 全部形态：逐条给 YAML 行号 + 可执行处方（"改成列出的真实端口 id"、"改写为 taps 条目"），
  首错不停一次报齐（沿用负例 expected-report 的原则）。
- 结构层（schema）只能报 JSON 指针（`$.unknown[0]`），拿不到行号——声明式契约的固有代价；
  但正是这一层抓住了"unknown 条目写成对象"这类手误。
- 注意 prototype 里混合形态曾是"形状层报错即停"，已改为两层收齐合并出口（首错不停原则优先）。

**3. 维护成本与漂移面**
- A：schema ↔ 语义脚本 ↔ 渲染器解析逻辑三方独立演进，两个漂移轴；且依赖 `jsonschema`（新增第三方依赖，
  需进 SKILL.md 依赖提示）。行数 258。
- B：断言层与渲染器同生命周期，零漂移轴；但契约以代码形式存在，编辑器提示、审查卡生成器等
  其他工具无法消费这段逻辑。行数 171。
- H：原型里 A/B 各自实现了语义（刻意隔离以便对比）。**真实落地时只有一份语义实现**（B 的
  preflight 核心被渲染器和外部 CLI 同源调用），schema 只管形状且天然稳定（intent 形状极少变）。
  漂移轴仅剩一处：schema 的必备章节列表 ↔ preflight 的骨架断言有 ~10 行重叠（可接受的双保险）。

**4. 迁移路径**
- 选 A → 把 `form-a` 两件挪进 skill scripts + 依赖声明即可，渲染器不动。
- 选 B → 把 `form_b_preflight.py` 变成渲染器 import 的模块，main() 加 3 行；无新依赖。
- 选 H → 以上两者都要，再加 60 行胶水；jsonschema 依赖照入。

## 原型的意外收获

- `bootstrap_reservoir` 在 catalog 里**没有 `connection_role` 字段**（其余 10 类都有）。
  system-1 把油箱串在 paths 中间全靠这一豁免才通过。定案时应补上该字段（terminal？inline？），
  属 catalog 修订而非预检器范围。
- 正例对照用的 system-1 是把 `catalog: @CATALOG-DOES-NOT-EXIST` 改成 `@0.1-draft` 才放行的——
  说明"catalog 字符串一致性"检查（本原型作 WARN）确实该保留。

## 建议（待你拍板）

推荐 **H 混合**：schema 冻结形状（可复用、可给编辑器/CI 吃）、preflight 核心管语义且由渲染器强制调用
（保住 TANK-001 教训里的"太晚不如不放行"），代价是一个新依赖和约 60 行胶水 + 一处可控的重叠保险。
若你想压依赖数，退而选 B（纯内置，能力损失主要在外部工具无法复用契约）；纯 A 因强制力短板不建议。

## 与地图的关系

按地图「Not yet specified」约定：本原型只做决策材料，**定案前不写正式实现**。
定案后立票的正式预检器及报告格式，依此对比结论展开。本目录不触及 skill 规范源/快照，
不影响 sync 闸门，定案后可整体删除或归档。
