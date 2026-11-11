<!-- 拆分件：规范映射、命令与编码 -->
> [AGENTS.md](AGENTS.md) · CONTROL-STATUS: current · AUTHORITY: agent-rules
> 原文第 46–104 行 · [前片](AGENTS.intent-and-execution.md) · [后片](AGENTS.refactor-and-testing.md)

## Standards Mapping (standards-template)

`docs/standards-template/` 是外部课程模板的原样副本（身份见 `docs/INDEX.md`）；**本表是它的采纳判定**。
模板会被整目录重新同步（07 就是后加的一份），所以规则是：**模板里出现一份新文件，本表就必须有
一行落点，否则 `tools/check_docs.py` 报红**。采纳方式是落进既有权威（SEL-004，不另建 `standards/`
平行目录）：产品终点与正式依赖只在计划，具体问题及验收在GitHub Issue，产品门/权限/恢复入口在state，选型与依赖在项目上下文§4。按职责链接，不复制工单明细状态。

| 模板 | 本项目落点 | 适配差异 |
|---|---|---|
| `README.md` | 本表；进入项目的读取顺序以 `docs/INDEX.md` §1 为准 | 不复制 `standards/` 目录（未采纳清单） |
| `00-project-context.md` | `docs/product-v2-project-context.md`（§3.3 运行取值、§4.1 选型、§4.2 依赖、§5 目录地图、§7 质量门槛） | Docker、GitHub Actions 与 SSH 取值由 SEL-005 固定 |
| `01-requirements.md` | Product V2计划（终点、边界、正式依赖/准出）+ GitHub Issue（具体问题、设计与验收） | 工单关联原任务，不复制完整Goal或另起PRD |
| `PROGRESS.md` | GitHub Issue/PR + `_working/amz-listing-kit-product-v2/state.md` | Issue管理具体工作；state保留产品门、权限、恢复指针和证据，不再建立本地工单明细副本 |
| `02-coding-standards.md` | 本文件 Coding Style | 未采用 ruff（无格式化工具链，理由在项目上下文 §7）；命名/注释/错误处理/提交前自检按本文件 |
| `03-testing-standards.md` | 本文件 Testing Guidelines + 计划§7.3/§15.3 | 用例AAA/Given-When-Then；不靠重跑关闭缺陷，准出统一按§7.6；不设覆盖率阈值 |
| `04-git-workflow.md` | 本文件 Commit & Pull Request Guidelines + GitHub Issue/分支/PR | 一个可验收问题对应可审查改动；最小完整改动即开Draft PR，不积压整轮本地WIP |
| `05-cicd-standards.md` | `.github/workflows/ci-cd.yml`、Dockerfile及本文件提交/PR规则 | PR持续检查并留审查证据；main按保护和既有发布事务部署；流程配置不等于本版通过 |
| `06-ai-collab-protocol.md` | 本文件Agent skills与提交/PR规则；产品权限只取state及当次授权 | 确认门适配为缺权限/需用户决定的重大取舍先停对应动作；已获授权内匹配skill并产出结果、主动推进，不逐任务等待确认 |
| `07-dependency-standards.md` | §Selection Gate（复用阶梯、选型四问、禁止自造清单）+ 项目上下文 §4.2（版本锁定、许可证、移除成本） | 漏洞扫描周期未启用，见未采纳清单 |
| `templates/TECH_SELECTION.md` | §Selection Gate 的报告字段（约束/已有能力/候选/权衡/推荐/被拒/复访条件/PoC 判定） | 不单独立文件 |
| `templates/ADR_TEMPLATE.md` | 项目上下文 §4.1 的 SEL 行（含被拒方案与复访条件） | 不建 `docs/adr/` |
| `templates/ISSUE_TEMPLATE.md` | 内容要求采纳到本文件提交/PR规则；GitHub Issue为具体问题载体 | CLI参考见`docs/agents/issue-tracker.md`，不以避免双权威为由停用产品Issue |
| `templates/PR_TEMPLATE.md` | 内容要求采纳到本文件提交/PR规则；正文用可用的`pr` skill | 不复制表单文件；前后证据、已知边界、合并风险及回退必须可审查 |

**未采纳清单**（模板有、本项目明确不做；每项带复访条件）：

| 未采纳 | 理由 | 复访条件 |
|---|---|---|
| `standards/` 物理目录 | 与计划/state/context 形成双权威（SEL-004） | 需要对外交付独立规范包 |
| ruff / 格式化工具链 | 无构建步骤；引入需先过选型门（项目上下文 §7） | 引入第一个格式化/lint 工具 |
| 覆盖率阈值（≥80%） | 判据是“证据能判红”而非行覆盖率（项目上下文 §7） | 引入覆盖率工具并立 SEL 决策 |
| 依赖漏洞扫描周期（`07` §6） | 依赖少而锁定，尚无扫描工具 | 新增依赖或准备对外交付时执行并记录 |
| 并行本地工单系统 | 与GitHub Issue重复维护具体问题状态；state只承接产品门/权限/恢复指针 | 确有离线协作需求且明确同步归属时再评估 |

## Build, Test, and Development Commands

```bash
uv run --locked python app/server.py                  # 启动产品（默认 8780，Product V2）
uv run --locked python app/server.py --check          # 正式入口自检
uv run --locked python tools/check_docs.py            # 文档守卫
uv run --locked python tools/check_project_state.py   # 状态守卫
uv run --locked python evals/probes/project_state.py  # 反向探针
```

浏览器证据用 `uv run --locked python tools/verify_<task>.py`（首次先 `uv run --locked playwright install chromium`）。**守卫/探针串行跑**；受测root隔离设计见 `docs/product-v2-refactor-design.md` §7，不得临时改写真实current state或让全库证据并写制造产品假红。Docker 构建、容器健康检查和远程部署由
`.github/workflows/ci-cd.yml` 执行，本机不是正式容器宿主。

## Coding Style & Naming Conventions

Python 3.13；`snake_case` 变量与函数，模块用短小写名；注释与界面文案用中文，标识符与文件名保持
ASCII。前端源码通过标准Vite构建到唯一`dist/product-v2`，正式Python入口只服务该目录；类型检查读`tsconfig.json`。视图按SEL-023使用lit-html投影，草稿由对应视图持有，业务状态由既有owner经`storage/` repository维护。
换行服从 `.gitattributes`（`.py`/`.js`/`.md` 为 LF，`.bat` 为 CRLF）。Python 依赖由
`pyproject.toml` + `uv.lock` 管理（uv add）；前端开发依赖由根 `package.json` + `package-lock.json`
管理（已批准包、精确版本、禁安装scripts）。TS strict与逐文件JSDoc/checkJs覆盖看`tsconfig.json`；构建与依赖决策看项目上下文§4.2/§7、SEL-021/023，不把node --check当类型门。

受管人读文档逐份不得超过 10,000 字节；覆盖被 Git 跟踪和未忽略的新文件，范围及检查入口见 `docs/INDEX.md`。按职责拆分或在核实恢复条件后退役，不设冻结或体积豁免；结构化机器数据按自身合同管理。

类用 `PascalCase`，常量用 `UPPER_SNAKE`，私有实现加 `_` 前缀；命名必须表达意图，禁止 `tmp_final`
这类无法审查的名字。函数按业务决策和变化原因组织，不按行数机械拆分；注释只写“为什么与权衡”，
不复述代码；禁止裸 `except: pass`，外部输入必须校验且错误信息可定位。

