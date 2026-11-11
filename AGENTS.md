# Repository Guidelines

> CONTROL-STATUS: current · AUTHORITY: agent-rules
> 本文件是仓库工作规则的唯一权威。目标与完成判据看 `docs/product-v2-refactor-plan.md`；
> 项目边界与技术栈看 `docs/product-v2-project-context.md`；当前进度看
> `_working/amz-listing-kit-product-v2/state.md`。进入项目按 `docs/INDEX.md` 的路由顺序读，不复制正文。

权限按操作分别核对：当前用户指令与 state 的停止／恢复边界优先；旧 Goal 绑定及历史恢复门仅作证据，不作为新重构前提。产品实施按当次授权推进；收费调用、远程写入和发布分别核对授权。
`uv run --locked python tools/refactor_resume.py`只读输出持久恢复路由；不使用聊天或内存todo代替state。换会话先按`docs/INDEX.md`§1读取当前入口，不从旧任务卡直接开工。
旧产品 Goal 的观察正文保存在计划§2.1；当前方向和权限以 state 与最新用户指令为准。旧 Goal 实时状态未知，不伪造读数；历史任务、授权和设计只按其适用范围读取。

本页与以下四份规则分片共同构成本仓库工作规则。**开始任何任务前，必须按顺序完整阅读全部四份规则分片；不得只读本导航或按任务跳过规则。**原有权限、停止／恢复及验收要求继续生效。各主题标题保留在本页，供完整阅读后的定向复查。

## 规则分片（必须完整阅读）

- [意图、执行纪律与目录](AGENTS.intent-and-execution.md)
- [规范映射、命令与编码](AGENTS.standards-and-development.md)
- [重构、实施承接与测试](AGENTS.refactor-and-testing.md)
- [交付、安全、选型与技能](AGENTS.delivery-and-security.md)

## 意图理解与帮助方式

理解本轮意图、选择帮助方式并保持独立判断。见 [意图、执行纪律与目录](AGENTS.intent-and-execution.md)。

## 软件工程执行纪律

确定工程任务的目的、证据、字节与完成边界。见 [意图、执行纪律与目录](AGENTS.intent-and-execution.md)。

## Project Structure & Module Organization

定位产品、配置、工具、证据和状态的所属目录。见 [意图、执行纪律与目录](AGENTS.intent-and-execution.md)。

## Standards Mapping (standards-template)

查看模板采纳映射、未采纳项及复访条件。见 [规范映射、命令与编码](AGENTS.standards-and-development.md)。

## Build, Test, and Development Commands

查启动、守卫和浏览器验证入口及串行要求。见 [规范映射、命令与编码](AGENTS.standards-and-development.md)。

## Coding Style & Naming Conventions

查命名、源码与产物、依赖、注释和错误处理规则。见 [规范映射、命令与编码](AGENTS.standards-and-development.md)。

### Proactive Refactor Review

检查所有权、消费者、重复实现和原件保留。见 [重构、实施承接与测试](AGENTS.refactor-and-testing.md)。

### Low-model Implementation Entry

从当前入口承接已授权的最小完整用户结果。见 [重构、实施承接与测试](AGENTS.refactor-and-testing.md)。

## Testing Guidelines

按风险选择证据、复用测试并保留失败。见 [重构、实施承接与测试](AGENTS.refactor-and-testing.md)。

## Commit & Pull Request Guidelines

查 Issue、分支、提交、PR、独立审查和发布关闭要求。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

## Security & Configuration Tips

查凭据、浏览器持久化与服务器状态边界。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

## Selection Gate (Reuse-first)

先复用再选型，查报告、依赖与 vendor 登记门。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

## Agent skills

定位工程协作与方法参考的规则。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

### Issue tracker

查看 Issue 的职责与操作参考入口。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

### Triage labels

查看五类角色与默认标签的对应入口。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

### Domain docs

查看领域文档与 SEL 决策的归属入口。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

### Skill使用与成品质量

查六环方法、受控自举、界面与 Prompt 成品要求。见 [交付、安全、选型与技能](AGENTS.delivery-and-security.md)。

