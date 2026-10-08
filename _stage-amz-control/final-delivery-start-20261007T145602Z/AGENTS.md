# Repository Guidelines

> CONTROL-STATUS: current · AUTHORITY: agent-rules
> 本文件是仓库工作规则的唯一权威。目标与完成判据看 `docs/product-v2-refactor-plan.md`；
> 项目边界与技术栈看 `docs/product-v2-project-context.md`；当前进度看
> `_working/amz-listing-kit-product-v2/state.md`。进入项目按 `docs/INDEX.md` 的路由顺序读，不复制正文。

当前 state 的 `prepared` 仅表示真正未观察到/未经用户确认 Goal 的准备态（绑定语义与证据合同以计划 §2.2 为准，不复制到此）：下一动作按计划做 R1.1 当前 Goal 重读核对与会话绑定；会话绑定完成前不开始产品施工。用户已确认当前 Goal 后，离线本地实现已获授权；付费模型调用、私有上传、提交/推送、部署、V1 日落、新依赖选型仍各自单独设门。
`uv run --locked python tools/refactor_resume.py` 只读输出持久恢复路由；不使用聊天或内存 todo 代替 state。
产品工程Goal原文与启动编制来源只读计划§2.1/§16；当前有限收口入口为计划§15.6及详细设计§11.5。真实绑定、停止门和恢复点取state，不据历史active、规划Goal或文档pass施工/发布。任务验收变化按§7.5一次核对，缺陷准出按§7.6，发布/数据回退按§7.4/§7.7；本文件不复制合同。

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
| `01-requirements.md` | Product V2 计划（§14业务合同、§6/§9任务与验收、§10完成矩阵） | 不另起PRD或第二份进度表 |
| `PROGRESS.md` | `_working/amz-listing-kit-product-v2/state.md` + 项目上下文 §4.1 | state 只存进度/证据/下一动作；决策（含被拒方案与复访条件）在 §4.1，故障在证据文件 |
| `02-coding-standards.md` | 本文件 Coding Style | 未采用 ruff（无格式化工具链，理由在项目上下文 §7）；命名/注释/错误处理/提交前自检按本文件 |
| `03-testing-standards.md` | 本文件 Testing Guidelines + 计划§7.3/§15.3 | 用例AAA/Given-When-Then；不靠重跑关闭缺陷，准出统一按§7.6；不设覆盖率阈值 |
| `04-git-workflow.md` | 本文件 Commit & Pull Request Guidelines + GitHub分支/PR | `<类型>/<短描述>`分支；CI/审查/保护满足后按该节授权方式合并main |
| `05-cicd-standards.md` | `.github/workflows/ci-cd.yml`、`Dockerfile`、README 部署说明（SEL-005） | CI 校验控制面、浏览器合同和镜像；`main` 传最小构建上下文，由远程 Docker 构建、健康检查并失败回滚 |
| `06-ai-collab-protocol.md` | ②.5 选型门 = 本文件 §Selection Gate（机器可查）；确认门 = 推进到 state 唯一下一动作后等用户确认；故障反哺 = 证据写 `evals/` + 守卫固化 | 建仓/Secrets/PR/CI/CD 已落地；业务确认仍由 state 唯一下一动作控制 |
| `07-dependency-standards.md` | §Selection Gate（复用阶梯、选型四问、禁止自造清单）+ 项目上下文 §4.2（版本锁定、许可证、移除成本） | 漏洞扫描周期未启用，见未采纳清单 |
| `templates/TECH_SELECTION.md` | §Selection Gate 的报告字段（约束/已有能力/候选/权衡/推荐/被拒/复访条件/PoC 判定） | 不单独立文件 |
| `templates/ADR_TEMPLATE.md` | 项目上下文 §4.1 的 SEL 行（含被拒方案与复访条件） | 不建 `docs/adr/` |
| `templates/ISSUE_TEMPLATE.md` | 未启用（产品任务仍以计划任务卡验收为准；工程技能 Issue 流程见 `docs/agents/issue-tracker.md`） | 复访：启用 GitHub Issue 做产品排期时 |
| `templates/PR_TEMPLATE.md` | 暂不复制模板；PR 的最小内容与门禁见本文件 Commit & Pull Request Guidelines | 复访：多人协作需要结构化表单时 |

**未采纳清单**（模板有、本项目明确不做；每项带复访条件）：

| 未采纳 | 理由 | 复访条件 |
|---|---|---|
| `standards/` 物理目录 | 与计划/state/context 形成双权威（SEL-004） | 需要对外交付独立规范包 |
| ruff / 格式化工具链 | 无构建步骤；引入需先过选型门（项目上下文 §7） | 引入第一个格式化/lint 工具 |
| 覆盖率阈值（≥80%） | 判据是“证据能判红”而非行覆盖率（项目上下文 §7） | 引入覆盖率工具并立 SEL 决策 |
| 依赖漏洞扫描周期（`07` §6） | 依赖少而锁定，尚无扫描工具 | 新增依赖或准备对外交付时执行并记录 |
| Issue 编号分支 | 产品任务权威在 Product V2 计划/state，另建 Issue 会重复任务状态；工程技能 Issue 只做技能驱动的议题/规格载体（见 `docs/agents/issue-tracker.md`） | 出现第二位协作者或需要公开排期 |

## Build, Test, and Development Commands

```bash
uv run --locked python app/server.py                  # 启动产品（默认 8780，Product V2）
uv run --locked python app/server.py --check          # 正式入口自检
uv run --locked python app/server.py --legacy-v1      # 旧 V1 回归入口
uv run --locked python tools/check_docs.py            # 文档守卫
uv run --locked python tools/check_project_state.py   # 状态守卫
uv run --locked python evals/probes/project_state.py  # 反向探针
```

浏览器证据用 `uv run --locked python tools/verify_<task>.py`（首次先 `uv run --locked playwright install chromium`）。**守卫/探针串行跑**；受测root隔离设计见 `docs/product-v2-refactor-design.md` §7，不得临时改写真实current state或让全库证据并写制造产品假红。Docker 构建、容器健康检查和远程部署由
`.github/workflows/ci-cd.yml` 执行，本机不是正式容器宿主。

## Coding Style & Naming Conventions

Python 3.13；`snake_case` 变量与函数，模块用短小写名；注释与界面文案用中文，标识符与文件名保持
ASCII。前端运行时是原生 ESM、无打包器；已迁 TS Module 按 SEL-021 编译为同目录 JS，浏览器不加载 TS。DOM 只做投影，业务状态一律走 `storage/` 的 repository 接口。
换行服从 `.gitattributes`（`.py`/`.js`/`.md` 为 LF，`.bat` 为 CRLF）。Python 依赖由
`pyproject.toml` + `uv.lock` 管理（uv add）；前端开发依赖由根 `package.json` + `package-lock.json`
管理（已批准包、精确版本、禁安装 scripts）。TS strict、逐文件 JSDoc/checkJs、编译产物一致性与 Node 原生行为验证按 SEL-021，
不把 node --check 当类型门；工具版本、实际覆盖和登记只见项目上下文 §4.2/§7、`jsconfig.json`。

类用 `PascalCase`，常量用 `UPPER_SNAKE`，私有实现加 `_` 前缀；命名必须表达意图，禁止 `tmp_final`
这类无法审查的名字。函数按业务决策和变化原因组织，不按行数机械拆分；注释只写“为什么与权衡”，
不复述代码；禁止裸 `except: pass`，外部输入必须校验且错误信息可定位。

### Proactive Refactor Review

非平凡改动必须主动审查本次依赖闭包，不等用户点名；详细处理与准出见 `docs/product-v2-refactor-design.md` §6–9。
- 找出可变状态和规则的唯一所有者；检查UI是否仍拼保存/授权/外发顺序、跨Module可变context、回调环和过宽Interface。迁入完整业务命令，不只移函数。
- 真重复先确认语义一致再合并；薄wrapper、pass-through、旧alias/re-export及失效注释在全部消费者迁移的同包删除，不建立兼容双路径。
- 检查浏览器实际加载的JS、唯一手写TS、实际emit/新鲜度集合及类型消费者；compiler program读到不是产物一致，语法通过不是功能通过。
- 编辑/采用首次写入expectedVersion为0，不能用null关闭OCC；单页Set不证明跨标签授权消费原子性，冻结旧快照不证明当前性。
- 测试固定源码/命名/文案/纯转发回声即删除，不重钉；共享真实前置与稳定业务Interface，原有消费者行为/事务/Unknown/秘密/字节反例不得丢。
- 旧源码、当前产物、历史证据、失败/费用/许可和用户原件分别处理；不以全部归档/清库/V1删除代替治理。有权限的旧实现同包清除，未知或用户材料不得擅删。
- 包结束记录实际合并/删除/保留的理由及最小行为证明；不得用文件数、代码行数、测试数或设计文档存在作为重构准出。

### Low-model Implementation Entry

执行前定向读计划§15.6与设计§11.5、§10及§9.1。先核对用户明确恢复和真实产品Goal，不把独立规划Goal或已完成准备当施工许可；已完成组A/owner/视图不重做。原§11.2是职责索引，按state前沿及当前差量推进，每个对象迁全部读写/restore/通知消费者并同包删除旧实现、setter/alias/双轨。事务/action保全/生命周期/报告ZIP/emit/发布仍沿冻结算法；遇新架构/schema/权限/预算或规格冲突停止对应动作并精确升级，不自行替代、降级或配置/切换模型。

## Testing Guidelines

每个任务交付「用户可观察行为 + 数据合同 + 验证证据」。证据写进 `evals/`，首行 `NOT-AUTHORITY`，
并写清证明了什么、不证明什么。浏览器断言必须同时检查 console/network 与 IndexedDB 后置条件，
只查 DOM 不算通过。真实模型调用只用于适配器最小探针和完成证据；超时是 `UNKNOWN`，已知 task ID
先核对，无 task ID 不自动重提。新增守卫必须附一次能判红的反向探针。
验证器新生成的 Product V2 报告默认是被 `.gitignore` 排除的本地过程材料；只有被 state、当前完成矩阵
或任务验收选中的最小集合，才按计划§7.1用 `git add -f -- <精确路径>` 提升。完成矩阵不得读取未跟踪
报告；禁止 `git add -A` 或整目录强制纳入。
改动 state 的阶段/任务状态或计划依赖表后，提交前必须重跑 `evals/probes/project_state.py`：
该探针以实时 state 为基线构造反向对照，进度推进会让旧构造连带误报或退化成空操作
（2026-10-01实例：CI连续4红，历史失败来源保留在原任务证据，不按失效章节号恢复）。

用例按 AAA / Given-When-Then 写，一个用例只测一件事，必须有真断言而不是 `assert x is not None`；
偶发失败必须根治，不靠“重跑一次”掩盖（常见根因：时间、随机数、用例顺序、网络、共享状态）。
验证按风险选择，连贯批次结束实际运行改变路径；默认不新增验证入口、接线/mock回声或文案/源码形状断言。新增永久用例须抓具体消费者行为、边界、权限或状态转换；最小检查、扩大条件及最终两轮回归只读计划§15.3，不把每层验证变成每批全跑清单。

## Commit & Pull Request Guidelines

提交信息用 `feat(v2): …`、`docs(control): …`、`evidence(vX.Y.Z): …` 前缀，正文写任务 ID 与证据路径；
一次提交只做一件事。提交前跑文档守卫与状态守卫，红了先修再走。功能分支推送后创建 PR；说明必须写
结果、验证证据、已知边界和回退方式，CI及现有审查/分支保护满足后才合并 `main`。默认人工合并；本轮已正式启动，代理合并权限取计划§16.1且仅覆盖本轮相关PR，不绕过保护、不强推。`main`的CD自动部署Docker镜像，
不在 PR 阶段部署。改权威文档前先留快照到 `_stage-amz-control/<用途>-<时间戳>/`，并把前后哈希写进证据。

## Security & Configuration Tips

当前无状态网关支持理解、生图、单图/整套复核的请求级 BYOK 头；三用途设置与准确实现边界见 README/context，目标在计划§14.7。
默认key永不下发、不发送到用户自定义目标；BYOK仅经批准的当前标签页内存/HTTPS请求路径，不进IndexedDB、localStorage、Git、项目包、日志、错误或诊断。
持久保存key需另行授权；方案确认或现有图像头不代表其他用途已实现，当前调用准入按计划§16.1及账本逐项核对。服务器不保存用户项目状态；
IndexedDB 是项目权威，localStorage 只放当前项目指针和无秘密界面偏好。

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

必须先交「选型报告」的情形：Python 新增运行时依赖（用 `uv add` 落进 `pyproject.toml` + `uv.lock`）或新增 ≥100 行通用
基础设施；浏览器新增 >5 KiB 通用能力文件或引入 vendor 库；任何属于「基础设施」而不是「业务语义」
的模块。

报告字段：约束 / 已有能力 / 候选 / 权衡 / 推荐 / 被拒方案 / **复访条件与移除成本** / PoC 判定；结论写进
`docs/product-v2-project-context.md` §4.1，实现前经用户确认。业务语义（槽位权限、失效传播、
交付门禁）自研是标准答案，不受此限。

登记即门禁：Python manifest/lock、前端开发期根 manifest/lock 与项目上下文 §4.2 逐包一致，
vendor 与登记逐一对应；产品目录只保留 ESM 身份，不建第二份依赖权威。少改一处 `tools/check_docs.py` 报红。
<!-- reuse-first:end -->

## Agent skills

### Issue tracker

Issues live as GitHub issues (`gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles map 1:1 to default label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (root `GLOSSARY.md` + `docs/adr/` when created); project decisions currently as SEL rows in project context §4.1. See `docs/agents/domain.md`.
