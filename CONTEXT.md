# 术语表（Ubiquitous Language）

> 本文件只收领域术语，不写实现细节。决议记录在各 Wayfinding 工单，不入此文件。

## 装配（Assembly）

由多个组件组成、**在位不可拆卸**（elements not removable in situ）的单元——维修/采购口径的整体。SysML 侧以 part def 层级表达（如 `case_drain_filter` = 本体 + 单向阀）；L0 intent 侧在装配展开图中以 `assemblies` 段声明。系统级模型（1# intent/SysML 实例层）允许把装配折叠为单个组件实例。

## 围框（Assembly Enclosure）

图纸语义：1.5T 长虚线框围合装配的全部成员符号——用于"组件端部不明显"的场合标界。出处初判 SAE AS1290A，待手持原件核对（挂 PENDING_STANDARD_ID）。与分组框是两套语义，图形必须可区分。

## 成员（Member）

被围框围合的组件实例。属于且仅属于一个装配；装配至少两个成员。成员命名沿用"装配id-角色"前缀约定（如 CDF-001-BODY），供读图追溯，不作为闸门依据。

## 越框端口（Boundary crossing port）

装配与外部的连接位置：管线穿越围框的位置。不单独声明，由 paths 与成员集合推导；校核规则是"管线只在成员端口处越框"。装配展开图的外部边界用 extern 边界三角表达（绘图抽象，同母线口径）。

## 分组框（Group box）

渲染器 groups 语义：走线走廊分组 / LRU 分区标注，虚线框。与装配围框无隶属关系——分组框圈成员是为布线与读图分区，不表达"不可拆卸"。

## 枢纽（Hub）

星形编码中承载 n 元汇流的中心端口或部件（如 @PRESS=PF-001.inlet）。同一枢纽的二元连接共节点，汇流语义不变。枢纽是母线这一绘图抽象的模型落点，不是部件。

## 星形编码（Star encoding）

SysML 文法只支持二元 connect，n 元汇流以枢纽为中心拆成二元连接的编码约定。母线↔星形的还原以模型头注的枢纽映射表为准。
