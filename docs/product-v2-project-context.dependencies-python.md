<!-- 拆分件：Python 依赖与开发环境 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 138–173 行 · [前片](product-v2-project-context.selection-019-025.md) · [后片](product-v2-project-context.dependencies-frontend-core.md)

### 4.2 依赖与 vendor 登记

`tools/check_docs.py` 双向核对 Python 的 pyproject/uv.lock、前端开发期根 package.json/package-lock.json
及 vendor 登记。每类依赖只有一份 manifest/lock 权威；新增/移除必须同步对应登记，不放开任意 npm 包。

依赖权威从 `requirements.txt` 迁移到 `pyproject.toml` + `uv.lock`（SEL-000 修订，2026-09-30；
删除 requirements 文件、守卫改读锁文件、CI 与 README 同步；证据见
`evals/product-v2/dependency-authority-migration-20260930.txt`）。

<!-- dependency-registry:begin -->
| 包 | 版本 | 许可 | 用途 | 引入决策 | 移除成本 |
|---|---|---|---|---|---|
| langchain-core | 1.6.6 | MIT | 语义调用与结构化输出原语 | SEL-003/007 引入（2026-09-30） | 中：换回直连要重写适配器 |
| langchain-openai | 1.6.6 | MIT | ChatOpenAI 指向百炼兼容端点 | SEL-003 引入 | 中 |
| fastapi | 0.143.3 | MIT | 正式HTTP路由/装配 | SEL-022；替换旧stdlib HTTP，无fallback | 小：随网关模块 |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI服务器生命周期/静态策略 | SEL-022；同上 | 小 |
| pillow | 12.3.0 | MIT-CMU | dev组：离线图像夹具和验证，不进生产运行依赖 | V1来源保留到开发验证；正式V2仅转发/校验协议字节 | 中：开发验证消费者 |
| pydantic | 2.13.5 | MIT | 语义契约模型（SEL-006 直接声明） | SEL-006；P1 由传递提升为直接依赖 | 小 |
| pyyaml | 6.0.3 | MIT | dev组：控制面YAML守卫，不进生产运行依赖 | 原配置消费者已清退，保留当前开发守卫 | 小：开发守卫 |
| requests | 2.34.2 | Apache-2.0 | V2 图像网关 HTTP 客户端 | SEL-010；V2 语义改经 langchain-openai（SEL-003） | 小：集中在 V2 网关与 `tools/` |
| playwright | 1.63.0 | Apache-2.0 | dev 组：浏览器合同验证 | SEL-005 CI 引入 | 小：dev 组 |
| pytest | 9.1.1 | MIT | dev组：网关合同与自检矩阵 | SEL-024；仅发现tests，不进生产镜像 | 小：dev组 |
| openai | 3.20.0 | Apache-2.0 | 兼容客户端（langchain-openai 传递依赖） | SEL-003 链路传递引入 | 小：随 langchain-openai 传递 |
<!-- dependency-registry:end -->

CI 浏览器验证依赖来自 pyproject 的 dev 组（`playwright==1.63.0`，Apache-2.0），不进入生产镜像。
GitHub Actions 复用官方 actions/checkout@v6、actions/setup-python@v6（SEL-005）；前端复用
官方 [setup-node v6.4.0](https://github.com/actions/setup-node/tree/v6.4.0)，固定 commit
`48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e`（MIT，已核 LICENSE/API tag；SEL-021）。
Node 从根 engines 读精确版本，CI 安装同 engines 的 npm 后 npm ci 禁 scripts；禁自动缓存。
开发期标准类型检查与Vite构建按SEL-021/023；不引入产品Node运行时或认证框架。uv sync --locked 与 uv run 继续执行Python/浏览器验证。

 前端开发期版本合同：Node `24.19.0`、npm `11.17.0`，来源为本机已安装工具；根 manifest/lock 锁定，
 R3.2 CI 已声明接线；Node 仅用于开发期检查/编译/验证，Python 与静态 ESM 是产品运行时。安装只允许已批准包，使用
 直接开发依赖为typescript、vite和ajv（ajv 仅构建期 codegen，不进浏览器运行图）；lit-html为受锁生产运行依赖（生产只消费构建后本地ESM）。

