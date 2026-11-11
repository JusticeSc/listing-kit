<!-- 拆分件：启动、模型设置与运行链 -->
> [README.md](README.md) · CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 原文第 64–159 行 · [前片](README.behavior.md) · [后片](README.validation-and-delivery.md)

## 启动

环境要求：Python 3.13、uv 0.9+、现代桌面浏览器；依赖权威是 `pyproject.toml` + `uv.lock`。

前端构建（SEL-023，2026-10-17 用户确认）用仓库根 `package.json` + `package-lock.json` 锁定的
TypeScript 6.0.3 + Vite 8.3.4（Node 24.19.0 / npm 11.17.0），只在开发与 CI 使用，不进产品运行时。
唯一生产静态目录是 `dist/product-v2/`（`npm run build:frontend` 产出，可从锁重建）；
`app/product_v2/` 下每个已迁移 Module 只有一份手工维护的源码：`.ts` 是权威，
正式入口对 `.ts` / `.d.ts` 一律 404、只服务 `dist/product-v2`，Docker 最终镜像只带构建产物，
生产运行时没有编译器、Node 或第二份源码。

界面模板使用受锁的lit-html 3.3.3，随Vite构建为本地静态ESM；许可随产物
`lit-html.LICENSE.txt`提供，不从CDN下载，也没有第二份全局store。输入、生成、比较、交付视图
分别持有自己的临时草稿；持久业务状态仍归既有owner。owner-local `subscribe`由工作区统一装配，
项目关闭/切换时回收草稿及预览URL，不用重绘前抓取DOM来恢复编辑内容。

先安装锁定的 Python 依赖，再生成协议校验器及构建前端；全程不需要模型 key：

```bash
uv sync --locked
npm ci --ignore-scripts
npm run build:envelope      # 由 ImageWire* 模型重建 Schema + standalone 校验器
npm run check:types         # 严格类型检查；实际覆盖由 tsconfig.json include 决定
npm run build:frontend      # 标准 Vite 构建 dist/product-v2
npm run check:envelope      # 真实网关 + Python↔JS 同拒；必须先有生产静态产物
npm run build:frontend-node # 标准 tsc emit 的 Node 测试消费树
npm run test:domain         # 领域行为的 node 原生测试
uv run --locked python app/server.py --check
uv run --locked python app/server.py
```

`--check`仅做正式入口轻量检查（真实TCP健康与唯一静态产物）；完整离线合同在下方验证入口，不装进生产镜像。缺少`dist/product-v2`时启动明确失败，不回退服务源码目录。`--open`会打开系统默认浏览器，自动化验证不使用该选项。

默认地址为 `http://127.0.0.1:8780/`。若需要让内网或穿透工具访问，可显式设置监听地址；暴露范围和访问控制由运行者负责：

```powershell
uv run python app\server.py --host 0.0.0.0 --port 8780
```

当前实现依赖浏览器原生IndexedDB、`crypto.randomUUID`与WebCrypto SHA-256；本轮工程验证范围是稳定版桌面Chrome（计划§2.4），旧Edge记录仅历史，不冒充本轮通过。localhost是浏览器认可的开发安全上下文，远程正式入口必须是HTTPS：
本仓库的部署把 TLS 终止在 Caddy 容器（`deploy/caddy/Caddyfile`，Let's Encrypt IP 证书 shortlived
profile 自动续期），应用容器仍只提供无状态 HTTP，当前试用入口是 `https://47.115.172.233:8080/`。
直接打开明文 `http://<IP>:8780` 时，Chrome/Edge 会保留 IndexedDB 但禁用 WebCrypto；页面会精确说明
“缺的是安全上下文 / WebCrypto”并禁用新建与导入，不会把缺口误报成 IndexedDB 不支持（证据见
`evals/product-v2/v2.ui.1-remote-entry-*-final.*`）。

模型设置按用途选择注册表的有限目录，自己的 key 只在当前标签页内存中使用，不开放任意模型 ID 或目标地址。
理解可选 `dashscope-semantic`（`deepseek-v4.1-flash`，只发送文字及参考图元数据，明确未看图）或
`dashscope-vision`（`qwen-vl-max`，发送实际图片字节）。看图支持 1–3 张 PNG/JPEG、单张 ≤4MiB；
网关按 base64 载荷读取后校验字节上限和完整 SHA256，输出仍是待人工确认的提议，不自动成为事实。
图像双 Adapter 为 `dashscope-qwen-image`（`qwen-image-3.0`，异步）和 `volcengine-ark`
（`doubao-seedream-5-0-flash-260915`，同步一步到终态、无 task 链）。单图及整套复核共用
`dashscope-review`（`qwen-vl-max`），只由用户明确发起，不随生成、比较或采用自动调用。
缺可用凭据时返回分类错误，不伪造结果；显式离线验证才使用测试替身。

候选与图片字节由 generation 保存，本地确定性报告由 selection-adoption 补齐；
已有当前报告在刷新／重开时不重复写版本。报告写入失败会显示原因，保留候选与原采用；
再次明确采用或重新打开项目可重建本地报告，不会因此自动调用 AI。

凭据口径（V2.R4.3）：部署密钥受默认档开关 `AMZ_V2_DEFAULT_TRIAL` 约束，未设置或 `closed/off/0/false`
时不会把部署密钥传入模型；无独立 BYOK 的有效调用请求返回 503 PROVIDER_NOT_CONFIGURED，
capabilities 给出 `credential_source` 与 `default_trial` 状态；显式 `open/on/1/true` 才沿用部署密钥。
三用途 BYOK 分别通过 `X-AMZ-Listing-Key-Semantic`、`X-AMZ-Listing-Key-Image`、
`X-AMZ-Listing-Key-Review` 请求头使用，应用后清空输入框，不落盘、不回显、不进项目包。
部署侧 DashScope 使用 `DASHSCOPE_API_KEY`，火山使用 `ARK_API_KEY`；默认档开关不限制独立 BYOK。
出站统一走白名单（`v2_outbound.py`：`aliyuncs.com` + `volces.com` 后缀），非白名单、
私网与非 https 目标在传输前被拒绝。

HTTP连接/协议解析由Uvicorn/h11承担；FastAPI路由保留逐用途正文上限、JSON合同和脱敏错误，未知提交结果不自动重试。异常正文与断连的实际边界由`tests/gateway`真实TCP合同验证，不依赖旧手写HTTP解析器或静态自检文案。

## 实际运行链

```text
app/server.py
  → app/product_v2_server.py
      ├─ GET /、/index.html、静态资源
      ├─ GET /api/health
      ├─ GET /api/v2/capabilities            provider 能力与 analyze 请求字段
      ├─ POST /api/v2/semantic/analyze       一次无状态分析；分类错误 + unknown 标记
      ├─ POST /api/v2/images/submit          单次登记与提交；按协议返回 task 或同步字节
      ├─ POST /api/v2/images/status          按原目标/task 查询异步状态
      ├─ POST /api/v2/images/result          按原目标/task 取回 PNG 字节
      ├─ POST /api/v2/review/candidate       显式单图 AI 复核
      └─ POST /api/v2/review/suite           显式整套 AI 复核

浏览器 app/product_v2/app.js
  → session.js / model-settings.js / semantic-analysis.js / generation.js（各自 TS 源编译产物；会话、内存凭据、理解动作及生成顺序）
  → workspace.js（任务与领域投影、发起业务动作）
  → storage/repository.js
      ├─ IndexedDB：项目、对象、Blob、版本（generation_attempt 版本链 append-only）
      └─ localStorage：当前项目 ID
```

页面不会读取服务器文件夹，也没有 `directory`、workspace 或 recent-workspaces 参数。项目导入先在内存中校验，
成功后才写入浏览器数据库；同 ID 项目会作为新项目导入，不覆盖既有项目。

