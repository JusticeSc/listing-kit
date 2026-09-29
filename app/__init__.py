# -*- coding: utf-8 -*-
"""完整演示产品的本地入口（Phase 2 起）。

`app/` 是**正式入口**，不是一次性原型：Phase 2 离线走查用的页面，与 Phase 3 之后
接真实状态的页面是同一套（计划 §6.11.2 的裁定）。离线只读模式由
`app/server.py --offline-fixture <商品包目录>` 打开，数据源在 `app/offline.py`。

这一层遵守的硬规矩与 `demo/` 一致：逐商品身份只在**调用时**经 `demo/core/packages.py`
解析；这里不出现任何商品名、不按路径 glob 逐商品数据。
"""
