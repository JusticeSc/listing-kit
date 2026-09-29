# Repository Guidelines

> CONTROL-STATUS: current · AUTHORITY: agent-rules
> 本文件是仓库工作规则的唯一权威。目标与完成判据看 `docs/product-v2-goal-and-implementation-plan.md`；
> 项目边界与技术栈看 `docs/product-v2-project-context.md`；当前进度看
> `_working/amz-listing-kit-product-v2/state.md`。进入项目按 `docs/INDEX.md` 的路由顺序读，不复制正文。

## Project Structure & Module Organization

- `app/` — 产品入口与前端：`server.py`（默认 Product V2 无状态入口，8780）、`product_v2_server.py`、
  `product_v2/`（`app.js`、`styles.css`、`storage/` IndexedDB、`domain/` 槽位与简报契约）。
- `src/` — Python 侧实现：`providers/` 模型适配器、规则与验证模块。
- `config/` — `product-v1/`、`product-v2/providers.json`、`slots.yaml`。
- `tools/` — 守卫与验证入口；`evals/` — 时点证据（带 `NOT-AUTHORITY`）；`docs/` — INDEX、计划、
  项目上下文；`_working/` — 唯一执行状态。

## Standards Mapping (standards-template)

`docs/standards-template/` 是外部课程模板的原样副本（身份见 `docs/INDEX.md`）；**本表是它的采纳判定**。
模板会被整目录重新同步（07 就是后加的一份），所以规则是：**模板里出现一份新文件，本表就必须有
一行落点，否则 `tools/check_docs.py` 报红**。采纳方式是落进既有权威（SEL-004，不另建 `standards/`
平行目录）：需求只在计划、进度只在 state、决策只在项目上下文 §4.1、依赖只在项目上下文 §4.2。

| 模板 | 本项目落点 | 适配差异 |
|---|---|---|
| `README.md` | 本表；进入项目的读取顺序以 `docs/INDEX.md` §1 为准 | 不复制 `standards/` 目录（未采纳清单） |
| `00-project-context.md` | `docs/product-v2-project-context.md`（§3.3 运行取值、§4.1 选型、§4.2 依赖、§5 目录地图、§7 质量门槛） | Docker、GitHub Actions 与 SSH 取值由 SEL-005 固定 |
| `01-requirements.md` | Product V2 计划（§3 产品合同、§10.1 任务表、§11 证据矩阵） | 需求以任务卡呈现（含验收条件），不另起 PRD |
| `PROGRESS.md` | `_working/amz-listing-kit-product-v2/state.md` + 项目上下文 §4.1 | state 只存进度/证据/下一动作；决策（含被拒方案与复访条件）在 §4.1，故障在证据文件 |
| `02-coding-standards.md` | 本文件 Coding Style | 未采用 ruff（无格式化工具链，理由在项目上下文 §7）；命名/注释/错误处理/提交前自检按本文件 |
| `03-testing-standards.md` | 本文件 Testing Guidelines + 计划 §12 | 用例 AAA/Given-When-Then；偶发失败必须根治；不设覆盖率阈值 |
| `04-git-workflow.md` | 本文件 Commit & Pull Request Guidelines + GitHub 分支/PR | 分支命名 `<类型>/<短描述>`；PR 先过 `.github/workflows/ci-cd.yml` 再人工合并 `main` |
| `05-cicd-standards.md` | `.github/workflows/ci-cd.yml`、`Dockerfile`、README 部署说明（SEL-005） | CI 校验控制面、浏览器合同和镜像；`main` 传最小构建上下文，由远程 Docker 构建、健康检查并失败回滚 |
| `06-ai-collab-protocol.md` | ②.5 选型门 = 本文件 §Selection Gate（机器可查）；确认门 = 推进到 state 唯一下一动作后等用户确认；故障反哺 = 证据写 `evals/` + 守卫固化 | 建仓/Secrets/PR/CI/CD 已落地；业务确认仍由 state 唯一下一动作控制 |
| `07-dependency-standards.md` | §Selection Gate（复用阶梯、选型四问、禁止自造清单）+ 项目上下文 §4.2（版本锁定、许可证、移除成本） | 漏洞扫描周期未启用，见未采纳清单 |
| `templates/TECH_SELECTION.md` | §Selection Gate 的报告字段（约束/已有能力/候选/权衡/推荐/被拒/复访条件/PoC 判定） | 不单独立文件 |
| `templates/ADR_TEMPLATE.md` | 项目上下文 §4.1 的 SEL 行（含被拒方案与复访条件） | 不建 `docs/adr/` |
| `templates/ISSUE_TEMPLATE.md` | 未启用（无 Issue 流程）；任务以计划任务卡的验收条件为准 | 复访：启用 GitHub Issue 时 |
| `templates/PR_TEMPLATE.md` | 暂不复制模板；PR 的最小内容与门禁见本文件 Commit & Pull Request Guidelines | 复访：多人协作需要结构化表单时 |

**未采纳清单**（模板有、本项目明确不做；每项带复访条件）：

| 未采纳 | 理由 | 复访条件 |
|---|---|---|
| `standards/` 物理目录 | 与计划/state/context 形成双权威（SEL-004） | 需要对外交付独立规范包 |
| ruff / 格式化工具链 | 无构建步骤；引入需先过选型门（项目上下文 §7） | 引入第一个格式化/lint 工具 |
| 覆盖率阈值（≥80%） | 判据是“证据能判红”而非行覆盖率（项目上下文 §7） | 引入覆盖率工具并立 SEL 决策 |
| 依赖漏洞扫描周期（`07` §6） | 依赖少而锁定，尚无扫描工具 | 新增依赖或准备对外交付时执行并记录 |
| Issue 编号分支 | 当前任务权威在 Product V2 计划/state，另建 Issue 会重复任务状态 | 出现第二位协作者或需要公开排期 |

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
反向探针，而探针会临时改写 state，并行会踩出假红。Docker 构建、容器健康检查和远程部署由
`.github/workflows/ci-cd.yml` 执行，本机不是正式容器宿主。

## Coding Style & Naming Conventions

Python 3.13；`snake_case` 变量与函数，模块用短小写名；注释与界面文案用中文，标识符与文件名保持
ASCII。前端是原生 ESM，**无构建步骤**；DOM 只做投影，业务状态一律走 `storage/` 的 repository 接口。
换行服从 `.gitattributes`（`.py`/`.js`/`.md` 为 LF，`.bat` 为 CRLF）。依赖只由 `requirements.txt`
锁版本，不建 `pyproject.toml`。

类用 `PascalCase`，常量用 `UPPER_SNAKE`，私有实现加 `_` 前缀；命名必须表达意图，禁止 `tmp_final`
这类无法审查的名字。一个函数只做一件事（超过约 40 行优先拆分）；注释只写“为什么与权衡”，
不复述代码；禁止裸 `except: pass`，外部输入必须校验且错误信息可定位。

## Testing Guidelines

每个任务交付「用户可观察行为 + 数据合同 + 验证证据」。证据写进 `evals/`，首行 `NOT-AUTHORITY`，
并写清证明了什么、不证明什么。浏览器断言必须同时检查 console/network 与 IndexedDB 后置条件，
只查 DOM 不算通过。真实模型调用只用于适配器最小探针和完成证据；超时是 `UNKNOWN`，已知 task ID
先核对，无 task ID 不自动重提。新增守卫必须附一次能判红的反向探针。

用例按 AAA / Given-When-Then 写，一个用例只测一件事，必须有真断言而不是 `assert x is not None`；
偶发失败必须根治，不靠“重跑一次”掩盖（常见根因：时间、随机数、用例顺序、网络、共享状态）。

## Commit & Pull Request Guidelines

提交信息用 `feat(v2): …`、`docs(control): …`、`evidence(vX.Y.Z): …` 前缀，正文写任务 ID 与证据路径；
一次提交只做一件事。提交前跑文档守卫与状态守卫，红了先修再走。功能分支推送后创建 PR；说明必须写
结果、验证证据、已知边界和回退方式，CI 全绿后才人工合并 `main`。`main` 的 CD 自动部署 Docker 镜像，
不在 PR 阶段部署。改权威文档前先留快照到 `_stage-amz-control/<用途>-<时间戳>/`，并把前后哈希写进证据。

## Security & Configuration Tips

密钥只从服务器环境变量读取（`DASHSCOPE_API_KEY`、`SEMANTIC_MODEL`、`IMAGE_MODEL`），不进浏览器、
Git、项目包、日志与证据。服务器不保存用户项目状态；浏览器 IndexedDB 是业务状态的权威，
`localStorage` 只放当前项目指针。

## Selection Gate (Reuse-first)

<!-- reuse-first:begin -->
任何非平凡能力，先按这个顺序找一遍，再决定动手：**复用 > 配置 > 集成 > 扩展 > 自研**。

**选型四问**（写报告前先答，答不上就不许引入）：① 标准库/已有依赖够不够；② 维护是否活跃
（近 12 个月有提交与响应）；③ 许可证是否兼容（MIT/BSD/Apache 2.0 直接用，GPL/AGPL/未知必须
用户确认）；④ 体积与安全代价（传递依赖、已知 CVE、是否原生编译）。四问的答案写进报告，
与本仓库依赖登记（版本锁定 + 许可证）互相印证。

**禁止自造清单**（基础设施一律先复用，不许手写）：日期时间与时区、UUID、JSON/YAML/CSV 解析、
HTTP 客户端、重试与退避、限流、缓存、定时调度、任务队列、事件总线、连接池、参数校验、序列化、
配置管理、日志框架、CLI 解析、密码哈希与加密、JWT、鉴权、ORM/数据库驱动封装。

必须先交「选型报告」的情形：Python 新增运行时依赖（改 `requirements.txt`）或新增 ≥100 行通用
基础设施；浏览器新增 >5 KiB 通用能力文件或引入 vendor 库；任何属于「基础设施」而不是「业务语义」
的模块。

报告字段：约束 / 已有能力 / 候选 / 权衡 / 推荐 / 被拒方案 / **复访条件与移除成本** / PoC 判定；结论写进
`docs/product-v2-project-context.md` §4.1，实现前经用户确认。业务语义（槽位权限、失效传播、
交付门禁）自研是标准答案，不受此限。

登记即门禁：`requirements.txt` 与项目上下文 §4.2 的依赖登记表逐包一致，`app/product_v2/vendor/`
与 vendor 登记表逐一对应；少改一处 `tools/check_docs.py` 报红。
<!-- reuse-first:end -->
