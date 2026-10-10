# 当前 1# 到站验收：固定端口顺序阻断零交叉目标

**#23 的“当前 1# 到站 fail 0 / B1=0”验收仍未完成。** 本目录记录可复核的约束阻断证据，不是通过的验收 seed 或交付图。现有用户布局、13/6 条残差、历史像素等价证据保持原样。

## 从当前输入提取的事实

`check_rotation_obstruction.py` 只读活动项目 intent、catalog、seed 实际选用的 SVG；[证书](rotation-certificate.json)记录它们的 SHA-256、路径锚、真实端口与所有 16 种允许旋转组合。

| 端口/网络 | EDP-001 | EMP-001 |
|---|---|---|
| suction / SUCTION | (0,40)，朝左 | (0,40)，朝左 |
| pressure_out / PRESSURE | (80,40)，朝右 | (80,40)，朝右 |
| case_drain / CASE | (40,80)，朝下 | (40,80)，朝下 |

两只实际 SVG 的 viewBox 都为 `0 0 80 80`。按 SVG 的 y 向下坐标顺时针读，三个端口的循环顺序均为 **CASE → SUCTION → PRESSURE → CASE**。任意平移、允许的 0/90/180/270° 旋转和正等比缩放，只会改变起点/角度，不会反转循环顺序。镜像和按朝向换口受当前渲染规范禁止。

当前 intent 明确给出三条相互独立的共有连接通路：

- SUCTION：`EDP.suction — FSOV — TANK.suction_out — EMP.suction`（paths[1]、paths[0]）；FSOV 在这条选取通路上只增加一个度为 2 的串联点，目录 main_path 已记录。
- PRESSURE：`EDP.pressure_out — @PRESS — EMP.pressure_out`（paths[2]、paths[3]）。
- CASE：`EDP.case_drain — @CASE — EMP.case_drain`（paths[29]、paths[30]）。

这不是说泵内部三个液口彼此连通。证明中把每只泵的不可穿越符号区域收缩成一个**辅助顶点**，只用于保存三个外接端口的周向顺序；不会向 intent 增加内部液压连通。如果原图能在平面上不穿体、不误接、不交叉地布线，那么这个辅助子图也必须有保留端口顺序的平面嵌入。

## 可独立核算的旋转系统证书

选取上述三条泵间通路，去掉其他支路、收缩每条通路上的度 2 点，得到两顶点三平行边的 theta 图（也就是细分前的 K2,3）。**抽象 K2,3 本身是平面图；受当前两端相同端口循环顺序约束的嵌入不是。**

记六条半边为 `(泵, 网络)`。`α` 沿同网络边到另一只泵，`σ` 在该泵按已测顺时针端口顺序取下一条半边。沿面边界执行 `σ∘α`，当前得到唯一循环：

```
EDP:CASE → EMP:SUCTION → EDP:PRESSURE
→ EMP:CASE → EDP:SUCTION → EMP:PRESSURE → EDP:CASE
```

因此 `V=2、E=3、F=1`，`V−E+F=0`；连通平面嵌入要求 Euler 值为 2，即此图必须有 **3 个面**。允许的 16 种旋转组合都保留同一循环顺序，面遍历结果全部仍为 1。增加画幅、移动母线/节点、增加走廊或折点都不能改变该不变量；方向箭头也不能绕过无向子图的必要条件。

独立复核采用已安装的 NetworkX 3.3 `PlanarEmbedding.set_data/check_structure`：扩展 K2,3 的普通抽象图检查为 planar=true，而把两泵按真实端口顺序登记后的检查报 Euler 公式不成立。仅作为证明校验的**不允许执行的反向顺序对照**得到 3 面并通过；没有镜像任何 SVG、没有更换端口。[NetworkX 官方实现](https://networkx.org/documentation/stable/_modules/networkx/algorithms/planarity.html#PlanarEmbedding.check_structure)同样通过半边面遍历与 Euler 公式检查固定周向顺序的嵌入。

这一证书证明：在当前三条共有连接通路、真实端口顺序、禁止镜像/换口、禁止穿体/误接且 B1 恒为 0 的共同约束下，至少一处有效非连通交叉无法消除。把它伪装成相接的 T 点会触发 V10/V14；跨线桥仍计入 B1，不能作为“零交叉”豁免。证书不声称当前六条失败已是最小残差，也不阻止改善 B3/B4/B5；它证明单靠被授权的布局调整无法同时达到所要求的 fail 0 和 B1=0。

[独立 Spec 复核](independent-spec-review.md)另外从实际 intent/selected SVG 提取端口，使用 NetworkX 自身的面遍历（未复用本脚本的六半边遍历）得到细分图 V=5/E=6/F=1、Euler=0；[独立数据](independent-fixed-rotation.json)同时保存反向环序的对照与资产哈希，两份结论一致。

因此停止无依据的布局搜索，保留 #23 到站条目未完成，交由工程定义/约束决策处理。未修改拓扑、端口、符号、镜像禁令、预算、成熟度或历史冻结结果；未生成或签认一份虚假的合格到站图。

## 复现

```bash
python research/ready-work-20261009/arrival-23/check_rotation_obstruction.py \
  -o /tmp/arrival-23-rotation-certificate.json
```

主证书只依赖现有 ruamel.yaml 和 Python 标准库；可选 NetworkX 提供第二种实现的独立检查，缺少它会明确记录 `not_executed`，不会把未跑的检查标为通过。修改相关输入路径或资产后必须重新提取；脚本会断言原三条通路仍存在，不能把旧证书无条件套到新模型上。
