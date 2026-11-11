# Product V2 交互与视觉契约（V2.UI.2）

> CONTROL-STATUS: draft · AUTHORITY: ui-interaction-contract（产品发起人走查确认前为设计草案；确认后转 current 并补入 INDEX 路由）
> 本文件只定义“用户看到什么、能做什么、什么状态下能做什么、操作后系统如何反馈”，以及支撑它的表现层基线。
> 业务对象、来源/权限、用途依赖、动作后置和验收由 `docs/product-v2-refactor-plan.md` §14 唯一规定；实现职责见 `docs/product-v2-project-context.md` §5.1。
> 2026-10-04正式开发前修订的设计正文为§1–8，§9–10保留历史研究/原型。2026-10-05用户已触发工程Goal，执行边界取计划§2.1/§16及state；本草案仍不冒充已实现或真人走查签署。
> 尚未实现、未获产品发起人真实页面走查，不据文本或工程自审转current。设计范围确认、工程验证和最终真人门按§8分层，旧G2不证明新交互已验收。

正文按视图与职责拆分；各部分按原顺序保留设计正文和历史记录。

## 内容

- [01 目的、业务对象、全局规则与信息架构](product-v2-ui-contract.01-object-rules-and-navigation.md) —— §1–3：边界、对象、全局规则和六入口导航
- [02 项目入口、工作台、资料与理解](product-v2-ui-contract.02-project-input-and-understanding.md) —— §4.1–4.4：项目首页、外壳、资料和事实确认
- [03 图片方案与生成](product-v2-ui-contract.03-plan-and-generation.md) —— §4.5–4.6：图片任务、发送摘要、确认和恢复
- [04 审核返工与交付](product-v2-ui-contract.04-review-and-delivery.md) —— §4.7–4.8：候选比较、人工采用、返工和导出
- [05 模型设置与渐进披露](product-v2-ui-contract.05-settings-and-disclosure.md) —— §4.9–4.10：用途配置、凭据、配置变化和信息层级
- [06 表现层、验收、生效与历史](product-v2-ui-contract.06-visual-acceptance-and-history.md) —— §5–10：视觉基线、代表状态、上位契约、走查和历史
