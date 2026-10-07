# 包10第二片证据：workflow rollback 条件 + Docker 实际闭包

- 时间：2026-10-07T09:18:43Z（UTC）
- 范围：只改 `.github/workflows/ci-cd.yml`（新增 1 个 CI 自检 step）；`Dockerfile`、`.dockerignore` 经核对无需改动；不碰 `deploy/**`、`tools/**`、`evals/product-v2/node/**`、`app/**`、`src/**`。
- 依据：设计 §10.8、计划 §7.7（发布事务四步 deploy/acceptance/fingerprint/finalize + rollback，finalize exit 1 可恢复 / exit 4 人工清理 / rollback 失败 exit 3）。

## 1. workflow rollback 条件（可执行、可复核）

改动：`ci-cd.yml` 新增 step `Check rollback truth table (executable, auditable)`（位于 finalize 之后、upload 之前、rollback 之前，仅 main push 跑）。

真值表（与脚本头注释一致，step 内注释原文）：

| 失败点 | finalize 码 | 动作 | previous |
|---|---|---|---|
| deploy/acceptance/fingerprint 任一失败 | — | rollback | 恢复上一可用 |
| finalize 重验证失败（容器/HTTPS/静态） | 1 | rollback（`recoverable=true`） | 保留并恢复 |
| finalize 收尾失败（删 previous/备份/事务失败或无开放事务） | 4 | 人工清理 | 绝不自动回滚 |
| 回退本身失败 | 3 | 报 unrecovered_failed_release | 保留 journal 精确故障 |
| 全部通过 | 0 | finalize 清理 | 此时才删 previous/备份 |

为何可执行可复核：该 step 自己就是一段 Python 断言，每次 main push 在 CI 里真跑，断言四件事——
1. rollback 门 `if:` 覆盖 `release_deploy/release_acceptance/release_fingerprint/release_finalize + recoverable` 四类；
2. finalize 只在 exit 1 时写 `recoverable=true`，exit 4 永不进 rollback 门；
3. build→smoke 之间无 `docker rm`（无提前清理）；
4. `docker rm --force` 只存在于脚本 `cmd_finalize()`（且 deploy 段无）。

本地真跑：`truth-table check PASS`（rc=0，见 §3）。

危险顺序核对结论：当前 CI/deployment **无“先删 previous”危险顺序**——previous 唯一删除点是脚本 `cmd_finalize()` 成功路径（line ~765 `docker rm --force "${PREVIOUS}"`），deploy 段经断言确认无 `docker rm --force`；workflow 里唯一的 `docker rm` 是 smoke 容器的 `always()` 清理（一次性 `amz-listing-kit-smoke`，非 previous）。故未改动 deploy 逻辑，只加了 executable 的条件自检。现有保护（分支保护/PR 审查）未动用、未绕过。

## 2. Docker 实际闭包

`docker build` 不可用：本机只有 Docker CLI（v29.4.2），daemon 未运行（`docker info` 报 `failed to connect to the docker API ... The system cannot find the file specified`；`docker build` 同错）。**未声称“已构建通过”**，以下为静态闭包核对 + 如实声明限制。

核对方法（无新依赖，手写 Docker `.dockerignore` 语义最小模拟：最后匹配 wins、`!` 取反、`**` 跨目录、目录规则覆盖其下文件；`git ls-files` 1837 跟踪文件全量过筛）：

- 镜像内文件 148 个；运行时必需 31 项（`app/server.py`、`app/product_v2_server.py`、`src/console.py`、`src/providers/__init__ + v2_registry/credentials/outbound/errors/semantic/image/review/suite_review/langchain_chat` + 注册表登记的全部 11 个 adapter 模块 + `config/product-v2/providers.json` + 前端入口 `index.html/entry.js/app.js/styles.css/storage/index.js` + `deploy/caddy/Caddyfile` + `deploy/release-transaction.sh` + `pyproject.toml/uv.lock/Dockerfile`）**零缺失**。
- 排除确认：全部 `.ts`（含 `domain/type-contracts.d.ts`）被 `app/product_v2/**/*.ts` 排除；`src/product_prompt.py`、`app/product_v1_server.py` 等 V1/旧栈被首条 `**` 排除；`config/product-v2/verification.json` 被单条排除（运行时零引用：app+src 全库 grep 无 `verification.json` 引用）。前端 `.js` 53 个全在镜像内。
- 浏览器运行时 import 闭包：语句级 `import ... from './x.js'` 全库扫描零悬空；364 处 `type-contracts.js` 引用经逐行确认**全部在 JSDoc 注释内**（零运行时效应，另有 `node --check`/健康自检旁证）。
- 真跑旁证（本地离线，不连 daemon）：`uv run app/server.py --check` 45/45 通过（rc=0），证明被纳入文件的正式入口自检绿。

限制声明：以上只证明“该进的文件都进了、不该进的都没进、JS import 无悬空”，**不证明镜像可构建、可启动**；`docker build` 与容器 health 仍需在有 daemon 的 Linux CI/部署环境验证（CI 里 `Build immutable image + Smoke-test` 原位保留，本片未动）。

Dockerfile/`.dockerignore` 改动：无。Dockerfile 的目录 COPY + `.dockerignore` 白名单已与 workflow 远程上下文 `tar` 列表（Dockerfile/.dockerignore/pyproject/uv.lock/app/src/config/deploy）对齐；闭包核对未发现缺项，故不改文件，避免无谓 churn。

## 3. 真跑输出（退出码）

- `node --check app/product_v2/workspace.js`：rc=0
- `npm run build:frontend`：rc=0（EMIT 3 个 ui 视图；跑后 `git status app/` 干净，无脏产物）
- `npm run check:types`（`tsc --noEmit`）：rc=0
- `npm run check:generated`（`--check`）：rc=0
- `node --test evals/product-v2/node/*.test.mjs`：227/227 pass，rc=0
- `uv run --locked python tools/check_project_state.py`：全过，rc=0
- `uv run --locked python tools/check_docs.py --no-run`：全过，rc=0
- `uv run --locked python app/server.py --check`：45/45 通过，rc=0
- 新增 truth-table 断言本地复跑：`truth-table check PASS`，rc=0
- `docker build`：daemon 不可用，未跑（见 §2 限制声明；CLI `docker buildx version` 正常，daemon 连接失败原文已贴）
- workflow YAML：`yaml.safe_load` ok（改前改后各一次）；中间一次编辑曾误删 rollback `if:` 门，已恢复并经 diff 确认与基线一致（仅 +40 行新增 step）

## 4. 未决项

1. 真实 `docker build + smoke` 需在有 daemon 的 Linux CI 环境看结果（本机 Windows 无 daemon，如实未跑）。
2. 真实两版本回退（不同 image ID + marker）属 sibling `P10ReleaseRollback` 的 release-script/probe 范围，本片只保证 workflow 门条件与之同义，不做跨片断言。
3. C17/C15 真人验收、V1 日落均不在本片范围。
