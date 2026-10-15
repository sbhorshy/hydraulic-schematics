# 项目符号副本

组件库唯一规范源为 `.agents/skills/hydraulic-schematic/assets/component-library/`。本目录供带本地目录的项目驱动器解析使用，不是第二套规范源。

2026-10-10，[旧油箱符号退役](https://github.com/sbhorshy/hydraulic-schematics/issues/49)：活动目录删除旧描摹油箱，`bootstrap-type-reservoir.svg` 是规范源同名文件的逐字节受管副本（draft，非正式签认件）。更新时从规范源复制，并重跑项目完整驱动器；不得在此单独修改端口。

迁移保持 TANK-001 的 x=60、y=276、218×564 足迹。旧 viewBox 原点 (20,10)，新原点 (0,0)；同一外部压力口的局部 x 从 172 变 155，因此新全局 x=215，不能继续用旧全局 x=232。回油/吸油口归一化坐标分别为 (0,410)/(218,410)，保持不变；新本体感测口 (50,564)。走线由 renderer 按当前 SVG 端口重新生成，不复用旧折点或历史 PNG。
