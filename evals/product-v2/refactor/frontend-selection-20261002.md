NOT-AUTHORITY: point-in-time V2.R3.1 selection and PoC evidence; not final type coverage, CI wiring, UI/framework completion, or release acceptance.

# V2.R3.1 · 前端工程选型（2026-10-02）

## 1. 约束、现状与已有能力

当前产品是 `app/product_v2/package.json` 声明的原生 ESM；该文件只含 private/type，无 scripts 或依赖。Python 仍由 pyproject/uv.lock 管理，Docker 直接 COPY 产品静态资源，无产品构建。新依赖单独获批后，本轮已在仓库根安装一个检查器并锁定；只增加 errors/invalidation 的 JSDoc，不改变其运行语句。

本机已有 Node v24.19.0/npm 11.17.0，Node 原生 test/assert/crypto 可用；tsc/bun 不在 PATH。全局 npm 包只有 pi-coding-agent/corepack/npm，未发现可直接运行的 TypeScript 编译器。Node 不是类型检查器：执行 JS 或剥离 TS 语法都不等于 checkJs。

体量快照：domain 21 文件约 8181 行，storage 13 文件约 2105 行，workspace.js 6151 行。domain 尚无系统性的 JSDoc 类型声明，启用 checkJs 后需要分模块补合同，不是零成本开关。行数只说明调查范围，不单独证明应换框架。

复用阶梯结论：复用原生 ESM → 配置 JSDoc/checkJs → 集成一个 dev-only 检查器；直接行为验证复用 Node 标准库；浏览器特有行为复用现有真浏览器 harness；本阶段不引入构建或框架。

## 2. 候选与批准结论

### 类型检查：推荐 typescript@6.0.3 + JSDoc/checkJs

- 标准库/已有依赖：Node 能运行领域 ESM，但不检查类型；缺一个检查器。
- 维护：Microsoft TypeScript 官方发布与文档持续维护，6.0.3 有 npm 正式版本，不选 nightly 或不锁定 latest。
- 许可：Apache-2.0。
- 安全/体积：npm 元数据没有 dependencies/optionalDependencies，纯 JS 检查器，无传递安装依赖；unpackedSize 24,346,827 字节。上游开发依赖不是消费者安装依赖。未进行独立漏洞扫描，不宣称无 CVE。
- 只做 allowJs/checkJs/noEmit，不迁移产品文件扩展名，不改变生产交付物。
- 移除成本：删除根 devDependency、锁文件条目与检查配置/命令；JSDoc 可保留为合同文档。

主源：[6.0.3 registry](https://registry.npmjs.org/typescript/6.0.3)、[官方 releases](https://github.com/microsoft/TypeScript/releases)、[checkJs](https://www.typescriptlang.org/tsconfig/checkJs.html)、[JSDoc](https://www.typescriptlang.org/docs/handbook/jsdoc-supported-types.html)、[LICENSE](https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt)。

锁定来源：tarball `https://registry.npmjs.org/typescript/-/typescript-6.0.3.tgz`；shasum `90251dc007916e972786cb94d74d15b185577d21`；integrity `sha512-y2TvuxSZPDyQakkFRPZHKFm+KKVqIisdg9/CZwm9ftvKXLP8NRWj38/ODjNbr43SsoXqNuAisEf1GdCxqWcdBw==`。

比较：5.9.3（Apache-2.0、23,625,066 字节、同样无安装依赖）也是可行旧版，但主集成核对发现 6.0.3 保持相同低依赖路线，故不无依据地停在 5.9。7.x 原生平台包矩阵目前无本项目收益证据，不作为默认。全仓 TS 迁移会扩大变更面，本阶段不采用；如后续 checkJs 真有不可表达且被故障证明的问题再复访。

### 行为验证：推荐 Node 原生 node:test/node:assert

Node 已安装，标准库 test runner 稳定，不需新增第三方包。许可随 Node 的 MIT 分发；第三方测试框架目前没有额外需求依据。移除成本为测试入口/文件，不影响产品运行。

主源：[Node test runner](https://nodejs.org/api/test.html)、[assert](https://nodejs.org/api/assert.html)。Node 版本与 npm 工具版本应锁进 CI/本机合同，不能默认 ubuntu runner 恰好预装正确版本。

### 构建与框架：独立决策，当前均不引入

保留现有静态 ESM 交付最小化变更。构建不是禁区，但需真实收益证据，并在采用时 clean cutover 到唯一产物，同步 CI/Docker/静态路径；不能同时维护两套交付物。框架也不是禁区，但应先通过业务 Module 收敛和首个纵向切片衡量手工 DOM 成本，不能用单文件行数或原型截图直接推导 React/Vue。原型解决的是隔离环境中的交互验证，不是正式产品缺陷已修。

## 3. 实际 PoC 与证据范围

纯领域 PoC：`frontend-poc-20261002/domain-smoke.test.mjs` 调真实 selection/attempt/candidate/invalidation/prompt 模块，不经 HTTP 或浏览器，不复制业务实现。

主集成实际执行：

```text
node --test evals/product-v2/refactor/frontend-poc-20261002/domain-smoke.test.mjs
6 tests / 6 pass / 0 fail，最新复核 duration 167.2484ms
node evals/product-v2/refactor/frontend-poc-20261002/checkjs/sample.mjs
poc-invalidation: shot shot-main
```

覆盖：采用后的 current/stale/clear 转移、跨图选择拒绝、submit/query 与终态/Unknown 转移、PNG 头解析及损坏输入、Shot 局部失效范围、缺 digest 的编译合同拒绝。直接行为 PoC 与 strict 类型正负例是两类证据，不证明全领域回归、真实 IDB/WebCrypto、产品 UI 或模型质量。

用户已在 ask 选择“批准开发期检查器”（证据 `frontend-approval-20261002.json`）。实际安装 typescript 6.0.3（1 包，禁 scripts），本地编译器输出 Version 6.0.3。初次宽范围 checkJs 暴露既有默认参数推断诊断，不把红基线当绿；R3.1 改为真实 errors/invalidation Module 的 strict PoC：零诊断、实际 JS 行为通过；独立 negative.mjs 把 Shot ID 误传 number，编译器退出码 2、TS2322，证明类型门能判红。R3.2 须记录旧诊断基线并完成渐进迁移，不把 PoC 的小范围等同全仓覆盖。

## 4. 已批准的锁定与交付方案

推荐仓库根开发工具 package.json + package-lock.json，根 node_modules 仅用于检查器；产品 `app/product_v2/package.json` 仍只定义运行时 ESM。这是单一前端开发依赖权威，不再在产品目录另建依赖锁。根开发文件默认被 `.dockerignore` 排除，且正式静态根在 app/product_v2，避免编译器被 COPY 到生产镜像或通过产品静态路由暴露。

若改在 app/product_v2 安装，现有 `.dockerignore` 的 `!app/product_v2/**` 会把 node_modules 一并放行；dev-only 标签不会自动阻止 Docker COPY。故不采用该安装位置。后续 R3.2 必须验证锁文件/登记一致、生产路径隔离与 CI 缺接线反向对照，不仅写配置。

已执行的安装与类型 PoC：

```text
# 仓库根，唯一新增开发期检查器
npm.cmd install --save-dev --save-exact typescript@6.0.3 --ignore-scripts
node node_modules/typescript/bin/tsc --noEmit -p evals/product-v2/refactor/frontend-poc-20261002/checkjs/jsconfig.json
node node_modules/typescript/bin/tsc --allowJs --checkJs --strict --noEmit --target ES2022 --module NodeNext --moduleResolution NodeNext evals/product-v2/refactor/frontend-poc-20261002/checkjs/negative.mjs
```

R3.1 接受时间：2026-10-02T03:08:13.511Z。守卫核对 Python/前端/vendor 全过；docs_index 15 向含未批准 npm 包负例全部符合判据且还原字节一致。首次探针曾因新增用例钉住不匹配的诊断文案而失败；修为真正的未批准包反例，不重新钉文案/具体默认版本。后续 R3.2 必须完成验证分类与 CI 缺接线反例，当前 verify_v2_2_3 尚未接入。

## 5. 未完成与下一批准门

- 检查器与路线已获批准，PoC 通过正例且拒绝类型负例；根 manifest/lock 与 SEL-021 已落盘。实际安装使用本机 npm 配置的 npmmirror HTTPS 来源，锁定 integrity 与 npm 官方元数据一致；未修改用户全局 registry。
- 全模块诊断迁移、CI 接线和验证分类尚未完成，归 R3.2；框架保持观察项，不把原型当正式 UI 修复。
- R3.2 迁移前已冻结真实 21 文件领域图及 SHA256；严格编译退出 2、1278 条既有诊断，证据 `frontend-type-baseline-20261002.json`。类型 PoC 的零诊断不掩盖该旧基线；后续新增/修改范围必须零诊断。
- 未付费、私有上传、提交推送、部署或删除 V1；依赖安装仅限用户单独批准的 typescript 6.0.3。
