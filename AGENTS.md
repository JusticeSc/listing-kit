# Repository Guidelines

> CONTROL-STATUS: current · AUTHORITY: agent-rules
> 本文件是仓库工作规则的唯一权威。目标与完成判据看 `docs/product-v2-refactor-plan.md`；
> 项目边界与技术栈看 `docs/product-v2-project-context.md`；当前进度看
> `_working/amz-listing-kit-product-v2/state.md`。进入项目按 `docs/INDEX.md` 的路由顺序读，不复制正文。

权限按操作分别核对：当前用户指令与state的停止/恢复边界先于历史启动记录；`prepared`时按计划§2.2完成绑定，产品实施前核对真实Goal及计划§2.1/§17的最新修订。用户仅授权维护规约时，只修改规约与恢复记录、运行相应守卫，不恢复产品、收费调用或GitHub远程写入。
`uv run --locked python tools/refactor_resume.py`只读输出持久恢复路由；不使用聊天或内存todo代替state。换会话先按`docs/INDEX.md`§1读取当前入口，不从旧任务卡直接开工。
产品Goal的原生观察正文只取计划§2.1；执行同时读取§17.13用户纠偏，规格取设计§13。旧§16/§15.6及设计§11.5仅按未决证据定向承接；规则、Goal或最新用户要求实质冲突时先修正/明确冲突，不能选旧条文继续施工或伪称原生Goal已更新。

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

非平凡改动由开发者主动审查实际依赖闭包并给出取舍，不等用户教方法或挑删除清单。以用户结果和维护成本选择复用、收口或删除；已成立的结构按未变前提复用，不因“全面改造”重写全仓。详细设计与准出见 `docs/product-v2-refactor-design.md` §6–9、§13；当前跨切片要求见Issue #10。
- 找出可变状态和规则的唯一所有者；检查UI是否仍拼保存/授权/外发顺序、跨Module可变context、回调环和过宽Interface。迁入完整业务命令，不只移函数。
- 真重复先确认语义一致再合并；薄wrapper、pass-through、旧alias/re-export及失效注释在全部消费者迁移的同包删除，不建立兼容双路径。
- 检查浏览器实际加载的JS、唯一手写TS、实际emit/新鲜度集合及类型消费者；compiler program读到不是产物一致，语法通过不是功能通过。
- 编辑/采用首次写入expectedVersion为0，不能用null关闭OCC；单页Set不证明跨标签授权消费原子性，冻结旧快照不证明当前性。
- 测试通过稳定业务Interface保护行为；必要性、删留和本次运行集合统一按下方Testing Guidelines，不让重构迫使无关测试机械改写。
- 旧源码、当前产物、历史证据、失败/费用/许可和用户原件分别处理；不以全部归档/清库/V1删除代替治理。有权限的旧实现同包清除，未知或用户材料不得擅删。
- 包结束记录实际合并/删除/保留的理由及最小行为证明；不得用文件数、代码行数、测试数或设计文档存在作为重构准出。

### Low-model Implementation Entry

软件工程取舍是开发者责任：先应用任务分析、深Module/单一所有权、成熟实现复用和风险匹配验证，再说明关键取舍与实际结果；只向用户升级产品选择、事实、权限或重大不可逆风险。现行规则未贯彻不能一概归因于上下文，也不能把用户的启发直接升级为普适规则。

用户要求产品实施且state允许时，按INDEX恢复并先应用计划§17.13，再读设计§13及受影响旧合同。已有owner、人工稿保护、五图原件与原生恢复证据按未变前提复用；修复新暴露的设计/交互缺口，不重跑已完成批次。当前格式自身的记录/Blob恢复必须可靠，不新增旧版本/schema/项目包迁移兼容；原件归档不等于维护旧运行链。超过授权的总体架构/模型/不可逆数据或费用变更再精确升级。

## Testing Guidelines

每个任务交付与请求相符的结果和范围匹配的证据。浏览器验证按变更选择：布局/焦点观察真实表面和交互；持久化核IndexedDB/Blob；外发核实际请求；跨边界主链才联合核后置。纯文案或布局修改不强制重跑数据库/模型/导出，DOM也不能替代本应证明的存储或外发。
真实模型只用于缺失或受改动影响的真实能力/品质证明，不用于调试可离线定位的问题。超时是 `UNKNOWN`，已知task先核对，无task不自动重提。新增必要守卫应有能抓具体错误的反例，优先纳入现有入口，不逐条新建探针。
必要证据写入 `evals/`，首行 `NOT-AUTHORITY`，说明证明范围；已有证据前提未受影响就复用，不为每次小改另起报告。
验证器新生成的 Product V2 报告默认是被 `.gitignore` 排除的本地过程材料；只有被 state、当前完成矩阵
或任务验收选中的最小集合，才按计划§7.1用 `git add -f -- <精确路径>` 提升。完成矩阵不得读取未跟踪
报告；禁止 `git add -A` 或整目录强制纳入。
改动 state 的阶段/任务状态或计划依赖表后，提交前必须重跑 `evals/probes/project_state.py`：
该探针以实时 state 为基线构造反向对照，进度推进会让旧构造连带误报或退化成空操作
（2026-10-01实例：CI连续4红，历史失败来源保留在原任务证据，不按失效章节号恢复）。

必要测试保护明确的用户结果或合理的高代价风险，有独立错误判据，并以适当边界提供可信反馈；能说明防什么错、损失、判错方式与不可替代性即可，不另建打分/登记平台。
- **保留与复用**：稳定、可重复且有意义的现有行为用例默认保留；“长期没改”是信号，不是充分条件。无新影响就不重新审计/重写整套用例。
- **删除与合并**：删无业务理由的源码/私有调用/旧DOM/普通措辞/纯转发回声断言，不重新钉到新实现。准确印字、协议、安全与可达性等真实合同仍须验证。同前提/同边界/同判据才合并；不同事务、浏览器或外发风险不因名称相同误删。
- **层级与时点**：永久回归、一次性smoke、本次运行集合分开；规则走小范围行为，事务/序列化/Adapter走对应真实消费者，浏览器行为走页面，少量全链检验连接。不把所有动作永久测试化；保留测试不等于每次全跑。
- **失败与完成**：用AAA/Given-When-Then表达行为并断言结果，替身回声、非空或不抛异常不足。red先定位并保留；无新事实/修改/诊断假设不重跑到绿。人因和成品品质由相应真实观察判断，不能靠堆断言代签。
局部改变只运行受影响的现有门并实际smoke；扩大条件和既定最终两轮见计划§15.3。具体清理证据/验收归Issue #7，不按用例数、覆盖率或报告数声明产品改善。

## Commit & Pull Request Guidelines

1. **问题先行**：产品实施及GitHub协作授权成立后，先读取或创建对应Issue，写清用户问题/现象、目标行为、可观察验收、范围外事项、依赖/权限门及现有证据。已有Issue直接更新，不为每个微小修改重复建单。权限不足只停对应远程写入；规约维护不自动授权建单、推送或部署。`gh`操作参考`docs/agents/issue-tracker.md`。
2. **可审查改变**：分支用`<类型>/<Issue号>-<短描述>`；提交正文关联Issue和原任务ID。一个提交只做一个自包含改变，必要读写消费者同组切换；无关重构另分。形成最小完整改动就推送并开Draft PR，持续更新，不等整轮本地工作做完才开放审查。
3. **PR证据**：说明结果、Before/After、实际执行的验证、未证/失败、影响范围及回退方式；界面必须有真实内容的画面/关键操作证据，Prompt必须有程序编译产物及来源，人工全文不能替代程序能力。审查材料只用获准素材和脱敏产物，不整目录外发原项目/原图/秘密。
4. **独立审查**：可用`code-review`及独立审查上下文检查确切改动，处理意见后再确认。CI绿和零强制审批不等于已审查；代理审查不冒称真人C15/C17，普通工程/设计问题也不转交用户代做。
5. **持续验证**：每个PR运行现有适用CI，保留确切commit与运行链接及必要失败证据；本地只跑受影响验证，最终两轮留给冻结候选。失败需定位并修正，不能用重跑绿替代解释。截图、自动测试、原像素各证明其范围。
6. **交付关闭**：满足CI/审查/实时保护后才按授权合并main；CD只在既有main流程发布。用户问题所需的后置真正成立才关闭Issue；线上交付问题须附当前镜像/HTTPS/实际路径/恢复证据，PR合并或容器healthy本身不算关闭依据。不要对尚待线上验证的Issue使用会提前自动关闭的关联语句。
提交前运行文档/状态守卫；红了先修。合并/发布权限取真实Goal、计划§17及state，不直推main/强推/绕保护。改权威文档前保留精确快照及前后hash；CLI调用本身不充当业务完成证据。

## Security & Configuration Tips

当前无状态网关支持理解、生图、单图/整套复核的请求级 BYOK 头；三用途设置与准确实现边界见 README/context，目标在计划§14.7。
默认key永不下发、不发送到用户自定义目标；BYOK仅经批准的当前标签页内存/HTTPS请求路径，不进IndexedDB、localStorage、Git、项目包、日志、错误或诊断。
持久保存key需另行授权；方案确认或现有图像头不代表其他用途已验收，当前调用准入按真实Goal§2.1/计划§17和当前账本lane逐项核对。服务器不保存用户项目状态；
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

产品问题与工程议题统一使用GitHub Issue；流程唯一取本文件Commit & Pull Request Guidelines，`docs/agents/issue-tracker.md`仅提供按权限使用的CLI/技能操作参考。

### Triage labels

Five canonical roles map 1:1 to default label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (root `GLOSSARY.md` + `docs/adr/` when created); project decisions currently as SEL rows in project context §4.1. See `docs/agents/domain.md`.

### Skill使用与成品质量

- 承接新类型任务时先读匹配skill，再使用其方法产出结果：界面/人因用`ui-ux-pro-max`与必要`prototype`；结构用`codebase-design`；规则/上下文用`writing-for-agents`；缺陷用`diagnosing-bugs`；改动用`code-review`独立审查，PR用`pr`组织证据，完成前用`completion-evidence`核对边界。只读skill或复述原则不算产出，不无差别叠加全套skill。
- 界面先定义用户要完成的动作、对象、反馈与恢复，再实现；普通流程不要求理解内部版本/task/hash或专业Prompt。视觉层级、默认值、认知负担和真实长内容下的布局与功能正确同等验收；明显问题不能等C15/C17才处理。
- Prompt先建立协调的视觉简报（用途、构图、光线/质感、配色、排版/准确文案及参考保真），再施加事实与安全边界；用程序实际编译的样稿证明普通输入的消费，手工专家稿/HTTP成功/旧成功图不证明新编译器品质。
- 反思落到现有Issue的明确问题、必要修改与修后证据；不以再写一份总结或新增守卫替代产品修正。只让用户决定不可替代的产品取舍、事实与权限，不让用户教工具、写工单或指挥每个工程步骤。
