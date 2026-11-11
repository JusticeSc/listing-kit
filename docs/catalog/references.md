<!-- 拆分件：docs/INDEX.md · 登记：模板与协作参考 -->
> [文档入口](../INDEX.md) · [上一页](state-and-history.md) · [下一页](status-and-checks.md)
> 身份和权威归父文档；本页保留公开 main 原件第 83–103 行。

| 路径 | 世代 | 管辖事实 | 状态 | 说明 |
|---|---|---|---|---|
| `docs/standards-template/README.md` | 外部参考模板 | `设计草案` | `draft` | 外部课程模板原样副本；本项目按 `AGENTS.md` §Standards Mapping 适配其要求，模板自身只作参考 |
| `docs/standards-template/00-project-context.md` | 外部参考模板 | `设计草案` | `draft` | 项目身份与技术栈模板；对应权威为 `docs/product-v2-project-context.md`（已含选型记录与依赖登记） |
| `docs/standards-template/01-requirements.md` | 外部参考模板 | `设计草案` | `draft` | 活PRD与验收写法模板；对应计划§14业务合同、§6/§9任务和§10完成矩阵 |
| `docs/standards-template/02-coding-standards.md` | 外部参考模板 | `设计草案` | `draft` | 编码标准；已适配进 `AGENTS.md` 的 Coding Style；未采用 ruff，理由与替代写在项目上下文 §7 质量门槛 |
| `docs/standards-template/03-testing-standards.md` | 外部参考模板 | `设计草案` | `draft` | 测试模板；按计划§7.3/§15.3及AGENTS风险导向验证适配，不设覆盖率阈值 |
| `docs/standards-template/04-git-workflow.md` | 外部参考模板 | `设计草案` | `draft` | Git/PR模板；现有分支和CI/保护要求、获批合并方式只读AGENTS对应章节 |
| `docs/standards-template/05-cicd-standards.md` | 外部参考模板 | `设计草案` | `draft` | CI/CD 标准；Docker + GitHub Actions + SSH 部署的采纳差异与 SEL-005 映射在 `AGENTS.md` §Standards Mapping |
| `docs/standards-template/06-ai-collab-protocol.md` | 外部参考模板 | `设计草案` | `draft` | AI协作协议；选型/确认门的采纳差异只取AGENTS的Standards Mapping与Selection Gate，不再解释成每到state下一动作都等待用户确认 |
| `docs/standards-template/07-dependency-standards.md` | 外部参考模板 | `设计草案` | `draft` | 依赖与复用阶梯；已适配进 `AGENTS.md` §Selection Gate 与项目上下文 §4.2 依赖登记（版本锁定 + 许可证） |
| `docs/standards-template/PROGRESS.md` | 外部参考模板 | `设计草案` | `draft` | 状态机与决策记录模板；对应权威为 `_working/amz-listing-kit-product-v2/state.md`，决策在项目上下文 §4.1 |
| `docs/standards-template/templates/ISSUE_TEMPLATE.md` | 外部参考模板 | `设计草案` | `draft` | 内容要求已采纳到`AGENTS.md`提交/PR规则；生效条件：按当前工作流开具体Issue，不复制外部表单为第二份任务权威 |
| `docs/standards-template/templates/PR_TEMPLATE.md` | 外部参考模板 | `设计草案` | `draft` | 内容要求已采纳到`AGENTS.md`；生效条件：最小完整改动即Draft PR，用当前可用的`pr` skill组织证据，不要求另安装/启用技能 |
| `docs/standards-template/templates/TECH_SELECTION.md` | 外部参考模板 | `设计草案` | `draft` | 选型报告模板；本项目用 `AGENTS.md` 的字段清单 + 项目上下文 §4.1 决策行承载，不单独立文件 |
| `docs/standards-template/templates/ADR_TEMPLATE.md` | 外部参考模板 | `设计草案` | `draft` | ADR 模板；本项目以项目上下文 §4.1 的 SEL 行（含复访条件）代替独立 `docs/adr/` 目录 |
| `docs/agents/issue-tracker.md` | 工程技能操作参考 | `设计草案` | `draft` | 只提供GitHub/gh及可选wayfinder操作；生效条件：AGENTS当前流程需要该操作且授权允许时核对采用，不再要求用户先启用技能；不独立授权或禁止产品Issue |
| `docs/agents/triage-labels.md` | 工程技能 | `设计草案` | `draft` | 可选triage角色映射；生效条件：实际任务需要且可用的triage技能被匹配、对应远程操作已获授权时采用，不要求用户先手工启用 |
| `docs/agents/domain.md` | 工程技能 | `设计草案` | `draft` | 单上下文术语/ADR的条件参考；实际需要且创建后才采用。当前决策仍取项目上下文SEL行，不为使用技能另建目录 |
| `docs/agents/ai-coding-loop.md` | 工程技能操作参考 | `设计草案` | `draft` | 用户提供的AI协作六环之本项目适配版；按任务与风险使用，研究线索未逐项核验，不作为普适定律；AGENTS为执行规则权威，不独立授权 |

---

