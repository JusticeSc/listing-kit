# Repository Guidelines

> CONTROL-STATUS: current · AUTHORITY: agent-rules
> 本文件是仓库工作规则的唯一权威。目标与完成判据看 `docs/product-v2-goal-and-implementation-plan.md`；
> 项目边界与技术栈看 `docs/product-v2-project-context.md`；当前进度看
> `_working/amz-listing-kit-product-v2/state.md`。进入项目按 `docs/INDEX.md` 的路由顺序读，不复制正文。

## Project Structure & Module Organization

## Standards Mapping (standards-template)

`docs/standards-template/` 是外部课程模板的原样副本（只作参考，权威状态见 `docs/INDEX.md`）。
本项目**采纳它的要求**，但结论落在既有权威里，不另建 `standards/` 平行目录——一物一处：
需求只在计划、进度只在 state、决策只在项目上下文 §4.1、依赖只在项目上下文 §4.2。

| 模板 | 本项目落点 | 适配差异 |
|---|---|---|
| 00-project-context | `docs/product-v2-project-context.md`（§3.3 运行取值、§4.1 决策、§4.2 依赖） | 部署/CI 占位符写“无”，理由见 SEL-005 |
| 01-requirements | Product V2 计划（§3 产品合同、§10.1 任务表、§11 证据矩阵） | 需求以任务卡呈现（等价用户故事 + AC），不另起 PRD |
| PROGRESS | `_working/amz-listing-kit-product-v2/state.md` + 项目上下文 §4.1 | state 只存进度/证据/下一动作；决策与已知坑写在 §4.1 与证据文件 |
| 02-coding-standards | 本文件 Coding Style | 未采用 ruff（无格式化工具链），理由在项目上下文 §7 |
| 03-testing-standards | 本文件 Testing Guidelines + 计划 §12 | 不设覆盖率阈值：判据是“证据能判红”，不是行覆盖率 |
| 04-git-workflow | 本文件 Commit & Pull Request Guidelines | 无远端与 PR 流程；分支/提交纪律 + 守卫替代 |
| 05-cicd-standards | 不适用（SEL-005） | 无 CI/CD、无 Docker、无服务器部署；门禁由 `tools/` 守卫承担 |
| 06-ai-collab-protocol | 本文件 + state 的唯一下一动作 | 六步确认门映射为：§Selection Gate + 用户确认 + 守卫全绿 |
| 07-dependency-standards | §Selection Gate + 项目上下文 §4.2 | 复用阶梯、禁止自造清单、版本锁定与许可证登记 |
| templates/* | 选型报告字段并入 §Selection Gate；ISSUE/PR 模板未启用 | 重大选型用项目上下文 §4.1 的 SEL 行代替 `docs/adr/` |

- `app/` — 产品入口与前端：`server.py`（默认 Product V2 无状态入口，8780）、`product_v2_server.py`、
  `product_v2/`（`app.js`、`styles.css`、`storage/` IndexedDB、`domain/` 槽位与简报契约）。
- `src/` — Python 侧实现：`providers/` 模型适配器、规则与验证模块。
- `config/` — `product-v1/`、`product-v2/providers.json`、`slots.yaml`。
- `tools/` — 守卫与验证入口；`evals/` — 时点证据（带 `NOT-AUTHORITY`）；`docs/` — INDEX、计划、
  项目上下文；`_working/` — 唯一执行状态。

## Build, Test, and Development Commands

```bash
python app/server.py                 # 启动产品（默认 8780，Product V2）
python app/server.py --check         # 正式入口自检
python app/server.py --legacy-v1     # 旧 V1 回归入口
uv run --no-project --with-requirements requirements.txt python tools/check_docs.py        # 文档守卫
uv run --no-project --with-requirements requirements.txt python tools/check_project_state.py  # 状态守卫
uv run --no-project --with-requirements requirements.txt python evals/probes/project_state.py # 反向探针
```

浏览器证据用 `--with playwright python tools/verify_<task>.py`。**守卫串行跑**：文档守卫会调用
反向探针，而探针会临时改写 state，并行会踩出假红。

## Coding Style & Naming Conventions

Python 3.13；`snake_case` 变量与函数，模块用短小写名；注释与界面文案用中文，标识符与文件名保持
ASCII。前端是原生 ESM，**无构建步骤**；DOM 只做投影，业务状态一律走 `storage/` 的 repository 接口。
换行服从 `.gitattributes`（`.py`/`.js`/`.md` 为 LF，`.bat` 为 CRLF）。依赖只由 `requirements.txt`
锁版本，不建 `pyproject.toml`。

## Testing Guidelines

每个任务交付「用户可观察行为 + 数据合同 + 验证证据」。证据写进 `evals/`，首行 `NOT-AUTHORITY`，
并写清证明了什么、不证明什么。浏览器断言必须同时检查 console/network 与 IndexedDB 后置条件，
只查 DOM 不算通过。真实模型调用只用于适配器最小探针和完成证据；超时是 `UNKNOWN`，已知 task ID
先核对，无 task ID 不自动重提。新增守卫必须附一次能判红的反向探针。

## Commit & Pull Request Guidelines

提交信息用 `feat(v2): …`、`docs(control): …`、`evidence(vX.Y.Z): …` 前缀，正文写任务 ID 与证据路径；
一次提交只做一件事。提交前跑文档守卫与状态守卫，红了先修再走。本仓库没有 PR/CI 流程：完成一个任务
就更新 state 的 `task_progress` 与 `next_action`。改权威文档前先留快照到
`_stage-amz-control/<用途>-<时间戳>/`，并把前后哈希写进证据。

## Security & Configuration Tips

密钥只从服务器环境变量读取（`DASHSCOPE_API_KEY`、`SEMANTIC_MODEL`、`IMAGE_MODEL`），不进浏览器、
Git、项目包、日志与证据。服务器不保存用户项目状态；浏览器 IndexedDB 是业务状态的权威，
`localStorage` 只放当前项目指针。

## Selection Gate (Reuse-first)

<!-- reuse-first:begin -->
任何非平凡能力，先按这个顺序找一遍，再决定动手：**复用 > 配置 > 集成 > 扩展 > 自研**。

必须先交「选型报告」的情形：Python 新增运行时依赖（改 `requirements.txt`）或新增 ≥100 行通用
基础设施；浏览器新增 >5 KiB 通用能力文件或引入 vendor 库；任何属于「基础设施」而不是「业务语义」
的模块。

报告字段：约束 / 已有能力 / 候选 / 取舍 / 推荐 / 被拒方案 / **复访条件与移除成本**；结论写进
`docs/product-v2-project-context.md` §4.1，实现前经用户确认。业务语义（槽位权限、失效传播、
交付门禁）自研是标准答案，不受此限。

登记即门禁：`requirements.txt` 与项目上下文 §4.2 的依赖登记表逐包一致，`app/product_v2/vendor/`
与 vendor 登记表逐一对应；少改一处 `tools/check_docs.py` 报红。
<!-- reuse-first:end -->
