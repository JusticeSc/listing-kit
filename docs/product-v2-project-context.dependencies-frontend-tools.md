<!-- 拆分件：前端依赖：工具与运行库 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 200–225 行 · [前片](product-v2-project-context.dependencies-frontend-core.md) · [后片](product-v2-project-context.vendor-and-module-map.md)

<!-- 续接：前端依赖表从前片 @rolldown/pluginutils 后继续；本标记、续接标题与重复表头在重组时移除。 -->
### 4.2 依赖与 vendor 登记（续：前端工具与运行库）

| 包 | 版本 | 许可 | 用途 | 引入决策 | 移除成本 |
|---|---|---|---|---|---|
| detect-libc | 2.1.2 | Apache-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| fdir | 6.5.0 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| fsevents | 2.3.3 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-android-arm64 | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-darwin-arm64 | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-darwin-x64 | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-freebsd-x64 | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-linux-arm-gnueabihf | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-linux-arm64-gnu | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-linux-arm64-musl | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-linux-x64-gnu | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-linux-x64-musl | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-win32-arm64-msvc | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lightningcss-win32-x64-msvc | 1.33.0 | MPL-2.0 | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| lit-html | 3.3.3 | BSD-3-Clause | 声明式视图模板；构建为本地静态ESM，无CDN/第二store | SEL-023（2026-10-17 用户确认）；发布许可随public/lit-html.LICENSE.txt | 中：迁走模板后删除依赖/锁条目/许可；不保留手工DOM fallback |
| nanoid | 3.3.20 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| picocolors | 1.1.1 | ISC | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| picomatch | 4.0.7 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| postcss | 8.5.30 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| rolldown | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| source-map-js | 1.2.2 | BSD-3-Clause | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| tinyglobby | 0.2.17 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| typescript | 6.0.3 | Apache-2.0 | dev-only strict TS + Node 树标准 tsc emit（SEL-021/023） | SEL-021；用户 2026-10-17 再次确认 SEL-023 批准 | 小：dev 依赖/锁条目/配置/CI 一步删除 |
| vite | 8.3.4 | MIT | dev-only 单一生产静态构建 dist/product-v2（SEL-023） | SEL-023（2026-10-17 用户确认）；dev-only，生产无 Node/编译器 | 小：删除构建配置与 dev 依赖/锁条目，恢复已提交生成 JS 服务 |
<!-- frontend-dependency-registry:end -->
