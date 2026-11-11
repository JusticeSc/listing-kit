<!-- 拆分件：验证、交付、目录与安全 -->
> [README.md](README.md) · CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 原文第 160–261 行 · [前片](README.startup.md)

## 验证当前实现

以下入口分别验证正式服务、浏览器存储、项目首页、项目包和领域合同；浏览器验证首次先执行 `uv run playwright install chromium`：

```powershell
uv run python app\server.py --check
uv run python tools\verify_v2_1_1_indexeddb.py
uv run python tools\verify_v2_1_2_project_home.py
uv run python tools\verify_v2_1_3_project_package.py
uv run python tools\verify_v2_1_4_formal_entry.py
uv run python tools\verify_v2_2_1_product_contracts.py
uv run python tools\verify_v2_2_2_semantic_provider.py
uv run python tools\verify_v2_2_3_intake_understanding.py
uv run python tools\verify_v2_2_4_category_generality.py
uv run python tools\verify_v2_3_1_suite_registry.py
uv run python tools\verify_v2_3_2_suite_editor.py
uv run python tools\verify_v2_3_3_spec_versions.py
uv run python tools\verify_v2_3_4_prompt_compiler.py
uv run python tools\verify_v2_3_5_pre_generation_confirm.py
uv run python tools\verify_v2_3_6_prompt_manual_edit.py
uv run python tools\verify_v2_3_7_copy_adoption_chain.py
uv run --locked python -m pytest tests/gateway tests/dev -q
uv run python tools\verify_v2_4_2_generation_attempt.py
uv run python tools\verify_v2_4_3_batch_execution.py
uv run python tools\verify_v2_4_4_candidate_blob.py
uv run python tools\verify_v2_5_1_deterministic_review.py
uv run python tools\verify_v2_5_2_vlm_review.py
uv run python tools\verify_v2_5_3_compare_panel.py
uv run python tools\verify_v2_5_4_rework_loop.py
uv run python tools\verify_v2_6_1_selection.py
uv run python tools\verify_v2_ui_2_interaction_visual.py
```

远程 HTTPS 正式入口与浏览器能力诊断单独验证（需要能访问 `https://47.115.172.233:8080`
与明文负例 `http://47.115.172.233:8780`，因此不进 CI，部署后按需运行）：

```powershell
uv run python tools\verify_v2_ui_1_remote_entry.py
```

`verify_v2_2_2_semantic_provider.py` 默认只做离线回放（真实 ChatOpenAI + 假传输），不联网；
加 `--live` 才会做计划 §12.2 允许的最小真实调用（正例 1 次 + 无效密钥 401 负例 1 次），
需要已在服务器环境里配置 `DASHSCOPE_API_KEY`。
 `verify_v2_2_4_category_generality.py` 默认只跑离线检查（C1 输入驱动、C5 无常量泄漏）；
加 `--live` 才会做四类商品的真实语义调用（每类最多 1 次、不重试），同样需要 `DASHSCOPE_API_KEY`。

文档、状态和控制面守卫必须串行执行：

```powershell
uv run python tools\check_docs.py --no-run
uv run python tools\check_project_state.py
uv run python evals\probes\project_state.py
```

`--no-run` 只检查文档结构与登记关系，不证明 README 中的命令已执行。产品完成声明还需要浏览器、
IndexedDB、API、真实 Provider 和首次使用者证据，具体门槛由产品计划定义。

## CI/CD

  `.github/workflows/ci-cd.yml` 在 PR 与手动触发执行控制面守卫、当前 Product V2 浏览器验证、Docker 构建、
  容器健康检查和发布事务自检（真实一次性容器，`tools/release_transaction_probe.py --selftest`，缺 Docker/构建/
  Playwright 按 exit 2 报 missing_prereq，不伪造绿）。`main` push 不重跑已绿分支头的全量验证，只做 Docker 构建、
  容器健康检查和发布事务自检。本机不承担正式容器运行。只有 `main` push 会部署：
  Actions 使用仓库中的 `SSH_HOST`、`SSH_USER`、`SSH_PRIVATE_KEY`，把最小 Product V2 构建上下文传到远程
  服务器，由远程 Docker 构建以 Git SHA 标记的镜像并按 `deploy/release-transaction.sh` 做完整发布事务
  （previous 与 TLS 配置备份保留到容器健康、外部 HTTPS、静态资源/页面主链全部验收结束；全部通过才清理，
  含 finalize 的健康 + HTTPS + 静态重验证；重验证失败 exit 1 走回退到上一已知可用状态并核对实际可用性，
  收尾失败 exit 4 需人工清理且绝不自动回滚；回退失败报 `unrecovered_failed_release` exit 3）。
  PR 不部署。服务器可选将运行时变量放在 `$HOME/.config/amz-listing-kit/app.env`。

这套流程存在不等于已经部署成功；是否真实上线必须以对应的 GitHub Actions run 和目标机
`GET /api/health` 为证据。

## 已退役入口（P1 随 main 基线退出仓库）

V1（Product V1 文件夹工作空间）与旧离线 Mock 回归分支已删除，不再提供
`--legacy-v1` / `--offline-fixture` / `--project` 参数；旧能力不可回退启动。
唯一可执行产品是 Product V2（`python app/server.py --check` / `--open`）。
旧设计与完成轨迹仍登记为 `superseded`；需要追溯时从 `docs/INDEX.md` 进入、
按 Git 历史查旧代码，不把固定七坑位、服务器工作空间或抠图路线带回 Product V2。

## 代码地图

```text
app/server.py                    正式启动入口；默认 V2
app/product_v2_server.py         V2 无状态 HTTP 装配：静态、能力、文字/商品图文理解、生图、单图/整套复核
 app/product_v2/                  V2 页面、IndexedDB、会话/设置/理解/生成 Module；已迁 TS 唯一手工源，浏览器产物由 npm run build:frontend 进 dist/product-v2，Node 消费树由 build:frontend-node 进 build/frontend-node
 app/product_v2/domain/           领域合同；归一化图像信封的结构权威是 src/providers/v2_image.py，浏览器唯一入口 domain/image-envelope.ts，生成校验器在 domain/generated/（构建期产物，不手改）
src/providers/                   有限语义/图文/生图/复核 Adapter、共享 langchain 图文传输、registry/credentials/errors/outbound；出站白名单 aliyuncs.com + volces.com
config/product-v2/               provider 注册表与选择环境变量；当前实现依赖它，是否已提交以 git status 为准
tools/                           自检、契约验证和控制面守卫
evals/product-v2/                时点证据，不是当前状态或规范
docs/INDEX.md                    文档身份与读写路由
```

## 配置与安全边界

- 当前默认服务绑定 `127.0.0.1`；是否经内网穿透暴露由运行者决定。
- Product V2 服务端没有账户、租户、数据库或用户项目索引。
- `DASHSCOPE_API_KEY`、`SEMANTIC_MODEL`、`IMAGE_MODEL` 等只从服务端环境变量读取。
- 浏览器站点数据被清理或 origin 改变时，只能通过此前导出的项目 ZIP 恢复。
- 本文件描述的是当前工作树里经过验证入口检查的实现；工作树中的新文件是否已被 Git 提交，以 `git status` 为准。
