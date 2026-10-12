# #31 状态报告（第一轮评审返工后 · 部分完成）

> 状态：**partial**。本报告对应第一轮 Codex 评审返工；测试尚未执行
> （ZCode 本轮无 Bash 执行权限，由 Codex 按下述命令跑完再定论），
> **不声称全绿**。

## 本轮修复（对照第一轮评审意见）

1. **坏 catalog fail-closed（评审实测漏点）**：`{}` 与
   `{"components": []}` 曾返回 exit 0/WARN——`load_catalog` 把它们折叠
   成空映射，C4/C5 端口对账静默消失（证据：
   `31-first-review-invalid-catalog.json`）。现 `check_symbol.py` 的
   `load_catalog` 改为结构校验 + 抛 `CatalogError`，`main` 拦截后退出码
   1，逐条给出可定位的 `[ERROR]`：
   - 文件缺失 / 不可读（含路径是目录）/ 非 UTF-8 / 非法 JSON；
   - 顶层非 JSON 对象；缺 `components` 键；`components` 非列表或为空列表；
   - 条目非对象；`component_type` 缺失 / 空白 / 重复；
   - `ports` 缺失或非列表；port 条目非对象、缺非空 `id`、`id` 重复。

   只做结构校验，未新增任何水力语义；合法 catalog 下未登记类型的存量
   符号仍按 C3 WARN（symbol severity 规则不变）。
2. **`--all` 与显式文件互斥**：原先 `--all` 分支静默丢弃显式文件
   （`--all missing.svg` 不会检查 missing.svg）。现为 argparse 用法
   错误：退出码 2 + usage/互斥提示，显式文件不可能被吞。
3. **文档**：SKILL.md「改动符号/catalog 后先跑它…pre-push 已接本工具」
   歧义已修——明确 pre-push 接的是 `check_library.py`，#31 未改钩子；
   check_symbol.py 全量扫描不在 pre-push 内，维持既有披露口径手动/CI
   运行。两处门禁描述（SKILL.md、symbol-library.md）补齐「catalog
   缺失或畸形一律 fail-closed」。迁移事实保持一句话粒度，公共文档无
   硬编码 worktree 路径。
4. **回归测试**：新增 `test_check_symbol_cli.py`（真实子进程调用 CLI）。

## 变更文件（issue-31 worktree）

- `.agents/skills/hydraulic-schematic/scripts/check_symbol.py`
  （catalog fail-closed + `--all` 互斥）
- `.agents/skills/hydraulic-schematic/scripts/test_check_symbol_cli.py`（新增）
- `.agents/skills/hydraulic-schematic/SKILL.md`（pre-push 歧义、fail-closed 口径）
- `.agents/skills/hydraulic-schematic/references/symbol-library.md`（fail-closed 口径）

## 待执行测试（Codex 执行，本轮未跑）

```
python .agents/skills/hydraulic-schematic/scripts/test_check_symbol_cli.py -v
```

回归锚点：

- 坏 catalog 12 例 + 缺失 + 不可读（目录）→ 全部 exit 1 + `[ERROR]`，
  无 WARN 放行（含评审的 empty-object / empty-components 两例）；
- 合法 catalog 下未登记类型 → C3 WARN、exit 0（存量符号口径不变）；
- 真实 catalog + check-valve.svg 沙箱 → exit 0（正控，门禁未过度拦截）；
- `--all missing.svg` → exit 2（显式文件不得被静默吞掉）；
- 默认库全量 → exit 1，ERROR 恰为 fsov-provisional-stroke.svg 与
  quick-disconnect-coupling.svg 两件既有挂账，且 fsov 的
  「C4 目录声明的端口在 SVG 中缺失: main_upper」与
  「C5 SVG 存在目录未声明的端口」两行在场——catalog 真实加载并参与
  端口对账的指纹（空 catalog 时这两行会消失、换成 C3 WARN）。

## #31 真实状态（不称全绿）

- 归位与门禁契约：已落地（skill scripts 自锚定、任意 cwd、fail-closed
  含坏 catalog、`--all` 互斥、pre-push 说明消歧）。
- 「22 只存量符号全量绿跑」验收项：**未完成**。fsov-provisional-
  stroke.svg（端口与 catalog `main_upper/main_lower` 双向失配，待工程
  处置）与接通位 quick-disconnect-coupling.svg（无端口组/无类型标注/
  尺寸带 mm 单位，B-2 挂 #22）仍是 ERROR；全量退出码 1 是当前基线，
  非本轮引入，也不以 WARN/跳过/白名单冒充通过。
