# 当前 L0 入口回归

这是 2026-10-08 工作区 23 部件概念输入的自包含副本，供入口兼容回归使用。
`parts`、`paths`、`taps` 与原输入相同；只同步到随 skill 打包的目录版本，
将布局中的旧符号引用换成目录规范名，并补上 `CV-002` 标签。运行时只依赖
本 skill 的 `assets/component-library/`，不依赖工作区其他目录或旧符号别名。

`test_entrypoints.py` 检查：预检放行、无参照布局可生成 23 个节点和默认标签、
规则布局能渲染；所附 seed 也能渲染，但仍须报告既有 V2（气侧引线穿本体）
及 V17（吸油标记压住旋转阀）失败。这个样例不是几何合格金样。

运行：`python scripts/test_entrypoints.py`。测试复制模板后执行，不覆盖 fixture。

几何通过的小型 seed 另见 `../l0-small-seed/`。PNG 和实际感知回读属于独立验收，
Python 几何测试不得将 `visual_review: pending` 改成通过。
