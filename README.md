# hydraulic-schematics · 液压原理图生成与校对

本仓库提供液压概念图绘制 skill、描边符号库和校验工具链。根据意图定义与布局配置生成 SVG、PNG、追溯清单和校验报告，并检查端口、连线、线宽、文字和图面边界。

**输出成熟度上限为 concept。** 自动校验与感知回读分别记录；工程放行需要人工签认。未知连接和 provisional/draft 符号按输入事实披露。

## 仓库与分发范围

`main` 保留维护所需的源码、测试、示例输入和必要说明。生成图纸、运行日志、回读裁剪及批次验收材料不放在主分支。

| 路径 | 用途 |
|---|---|
| [`.agents/skills/hydraulic-schematic/`](.agents/skills/hydraulic-schematic/SKILL.md) | 可独立分发的完整 skill：工作流、规则、脚本、符号库及自检夹具 |
| [`1#系统原理图/`](<1%23系统原理图/README.md>) | 当前示例输入、布局、目录、符号与兼容入口 |
| `editor-proto/` | 编辑器原型：拖拽、旋转、受控镜像及校验反馈 |
| [`tests/`](tests/repository/README.md) | 仓库集成测试、调度器测试及具名历史回归夹具 |
| [`docs/`](docs/规格与需求.md) | 规格、维护约定及归档索引 |
| [`research/`](research/README.md) | 仍被规范或许可引用的必要依据 |

分发 skill 时复制完整 `.agents/skills/hydraulic-schematic/`，包含其 `assets/fixtures` 和自检脚本。仓库外层集成测试与项目工作区不是 skill 的隐藏依赖。

历史示例图、审查记录及冻结证据可从 [归档索引](docs/archive.md) 查看。清理前的完整 Git 快照保留在 `archive-main-before-cleanup-20261013`，无需把归档内容复制回 `main`。

## 环境准备

下面的命令在 **WSL/Linux 的仓库根目录**执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install ruamel.yaml kiwisolver Pillow jsonschema
```

完整出图、浏览器几何校验与回读需要可被工具发现的 Chrome/Chromium，以及覆盖中文的字体。前端行为测试需要 Node.js。`jsonschema` 可选，缺失时部分形状预检降级为提示；建议按上面命令安装。

## 首次生成 1# 示例

每次新建一个输出目录，避免覆盖已有手调布局。`.artifacts/` 已被 Git 忽略。

```bash
mkdir -p .artifacts
schematic_workdir=$(mktemp -d "$PWD/.artifacts/one-system.XXXXXX")
cp '1#系统原理图/1#系统.intent.yaml' \
   '1#系统原理图/1#系统.layout.json' \
   '1#系统原理图/1#系统组件.json' \
   '1#系统原理图/component-catalog.json' "$schematic_workdir/"
cp -R '1#系统原理图/symbols' "$schematic_workdir/symbols"

python3 .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py "$schematic_workdir"
python3 .agents/skills/hydraulic-schematic/scripts/rasterize_sheet.py \
  "$schematic_workdir/1#系统原理图.svg" -o "$schematic_workdir/sheet-readback.png"
python3 .agents/skills/hydraulic-schematic/scripts/validate_sheet.py "$schematic_workdir"
```

查看输出目录中的图纸和 `validation-report.json`。自动检查通过不等于完成回读；局部与整图复核尚未记录时，`delivery.ready` 仍为 `false`。回读操作、错误处理与有界收敛流程见 [skill 工作流](.agents/skills/hydraulic-schematic/SKILL.md)。

编辑刚生成的图纸，在同一个终端中运行：

```bash
python3 editor-proto/server.py --workdir "$schematic_workdir" --port 8763
```

浏览器打开 `http://127.0.0.1:8763/`。原型将手调写回该输出目录的布局并重渲染、校验；违规结果会保留并显示反馈。编辑器仍处于原型范围，产品定位和工程成熟度以对应工单为准。

## 验证与其他入口

```bash
# 符号库结构校验
python3 .agents/skills/hydraulic-schematic/scripts/check_library.py
# skill 自包含回归
python3 .agents/skills/hydraulic-schematic/scripts/selftest.py
# 仓库集成回归，需 Node.js 运行前端行为测试
python3 -m unittest discover -s tests/repository -v
# 调度器与自检 CLI 回归
python3 -m unittest discover -s tests/scheduler -v
```

符号入库门禁、布局生成/优化、SysML 相关入口及其支持范围，以 [SKILL.md](.agents/skills/hydraulic-schematic/SKILL.md) 和各脚本的 `--help` 为准。当前输入需符合显式坐标与端口契约；不支持的类型或连接不得通过猜测补齐。

规范来源：[符号规则](.agents/skills/hydraulic-schematic/references/symbol-library.md)、[绘图规则](.agents/skills/hydraulic-schematic/references/rendering-rules.md)、[校验规则](.agents/skills/hydraulic-schematic/references/validation.md)。仓库内容取舍见 [维护约定](docs/agents/repository-content.md)。

工单与未完成事项由 [GitHub Issues](https://github.com/sbhorshy/hydraulic-schematics/issues) 跟踪。历史验收记录不代替当前版本的检查结果或工程签认。
