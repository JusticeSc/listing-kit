<!-- 拆分件：前端依赖：类型、生成器与平台包 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 174–199 行 · [前片](product-v2-project-context.dependencies-python.md) · [后片](product-v2-project-context.dependencies-frontend-tools.md)

<!-- 续接：本片承接 4.2 的前端依赖登记；本标记与续接标题在重组时移除。 -->
### 4.2 依赖与 vendor 登记（续：前端依赖）

<!-- frontend-dependency-registry:begin -->
| 包 | 版本 | 许可 | 用途 | 引入决策 | 移除成本 |
|---|---|---|---|---|---|
 | @types/trusted-types | 2.0.7 | MIT | lit-html传递类型依赖；仅编译，不进浏览器运行图 | SEL-023（2026-10-17 用户确认） | 小：随lit-html移除 |
| ajv | 8.20.0 | MIT | 构建期 standalone ESM codegen（SEL-025）；不进浏览器运行图 | SEL-025（2026-10-17 用户确认） | 小：dev 依赖/锁条目/生成器一步删除 |
 | fast-deep-equal | 3.1.3 | MIT | ajv/SEL-025 传递依赖（dev-only，不进生产） | SEL-025（2026-10-17 用户确认） | 小：dev-only 锁条目，随 ajv 移除同步消失 |
 | fast-uri | 3.1.8 | BSD-3-Clause | ajv/SEL-025 传递依赖（dev-only，不进生产） | SEL-025（2026-10-17 用户确认） | 小：dev-only 锁条目，随 ajv 移除同步消失 |
 | json-schema-traverse | 1.0.0 | MIT | ajv/SEL-025 传递依赖（dev-only，不进生产） | SEL-025（2026-10-17 用户确认） | 小：dev-only 锁条目，随 ajv 移除同步消失 |
 | require-from-string | 2.0.2 | MIT | ajv/SEL-025 传递依赖（dev-only，不进生产） | SEL-025（2026-10-17 用户确认） | 小：dev-only 锁条目，随 ajv 移除同步消失 |
| @oxc-project/types | 0.154.0 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-android-arm-eabi | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-android-arm64 | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-darwin-arm64 | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-darwin-x64 | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-freebsd-x64 | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-arm-gnueabihf | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-arm64-gnu | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-arm64-musl | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-ppc64-gnu | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-s390x-gnu | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-x64-gnu | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-linux-x64-musl | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-openharmony-arm64 | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-win32-arm64-msvc | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/binding-win32-x64-msvc | 1.2.14 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |
| @rolldown/pluginutils | 1.0.1 | MIT | vite/SEL-023 传递依赖（dev-only，不进生产） | SEL-023（2026-10-17 用户确认） | 小：dev-only 锁条目，随 vite 移除同步消失 |

<!-- 续接：前端依赖表在 product-v2-project-context.dependencies-frontend-tools.md 从 detect-libc 接续；此标记在重组时移除。 -->
