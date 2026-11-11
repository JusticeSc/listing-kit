<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/work-audit-20261003.md -->
# 之前工作审计（2026-10-03）
[返回 work-audit-20261003.md](work-audit-20261003.md)

NOT-AUTHORITY: point-in-time evidence only. Not a second plan, execution state, or Product V2 completion claim.

# 之前工作审计（2026-10-03）

## 1. 结论与边界

项目已经完成重构准备、基线/权限审计、UI 任务审计与原型、前端验证分层及会话切片，处于 Phase 4，而非记忆中的 prepared。现有实现可启动并保存/恢复本地项目，但不具备当前 Goal 的完成条件，不能进入人审、V1 日落或发布。

本轮只审计、执行离线本地检查、更新计划/状态/证据。0 次真实模型调用，0 次私有素材上传，未新增依赖、提交/推送、部署或删除 V1。浏览器仅独立临时 profile 的 Chrome headless；本轮本地草稿 smoke 不代替完整任务、双标签、所有视口、真实模型或 C17/C15。

权威仍是：计划 `docs/product-v2-refactor-plan.md`；项目边界 `docs/product-v2-project-context.md`；进度 `_working/amz-listing-kit-product-v2/state.md`。本报告中的状态是本轮时点快照；后续推进策略只在计划 §8.1，不在报告建立另一套任务。

## 2. 本轮直接观察

- 系统 Goal 首次 get 为 paused；按会话上级恢复规则 resume 后为 active。结构化 Goal 返回原生 ID `1595e928a065b786`，与历史绑定一致；展示归一后的正文与计划 §2.1 完全一致，正文 SHA256 为 `e5a10fd4b69cdde75c510e96dd309ed2e724690f1ca5f49ef2ef78ecb938080f`。没有创建、完成或改写 Goal。观察原始对象见 [goal-observation-20261003-audit.json](goal-observation-20261003-audit.json)。仓库不再仅依赖 10-02 的观测。
- 审计前冷恢复输出：8 阶段、26 任务，Phase 0–3 done，Phase 4 active，next=R4.2；R4.1、R6.4 也标 done。任务计数不表示产品完成百分比。
- 审计前工作树：`main...origin/main`，staged 0、unstaged 55、untracked 28，tracked diff 为 55 files +1994/-2358。新计划、session.js、package/lock、验证登记、Node 领域用例等尚未提交。详见 [work-audit-20261003-worktree.txt](work-audit-20261003-worktree.txt)。不能据分支与 origin 同步声称当前工作已进入 CI/线上。
- 本轮新鲜检查：文档守卫（非 --no-run，真跑 7 命令）、状态守卫、冷恢复通过；正式入口 --check 为 38/38；锁定版本检查、当前类型范围通过；Node 领域行为 223/223；验证分类 43 入口/39 CI 模式通过；14 组分类反向探针按标签拒绝。没有执行完整产品回归两轮。
- 实际正式入口 `app/server.py --port 18783`，Chrome 154.0.8037.93 headless：空白首页→新建隔离项目→填写商品资料→保存草稿→刷新。真实 IndexedDB 的 projects/documents/assets 前后逐对象相等，商品名称/介绍恢复，零 console/page error。健康返回 `product=v2, server_state=none`。截图、前后记录及选定代码/配置指纹见 [work-audit-20261003-runtime.json](work-audit-20261003-runtime.json)、[首页](audit-20261003-home.webp)、[草稿恢复](audit-20261003-draft.webp)。临时浏览器和服务已关闭。
- 自动化首次错误地等 `body[data-ready]` 超时；实际 marker 位于 `#create-project`/`#project-view`，检查后工作流通过。这是审计脚本的错误查询，不是新的产品 boot 失败。

## 3. 已完成工作：保留什么、不能推断什么

| 工作 | 已有直接证据与结论 | 限制 |
|---|---|---|
| R0/R1 控制与基线 | 权威链/恢复守卫已建立；R1.2 当前格式两份 ZIP 基线存在，可读，含候选/历史；开发态不兼容旧版本已经用户明确批准 | 不将“旧包要求取消”说成旧数据恢复；原 boot 缺陷仍 Unknown |
| R2 UI 审计/研究/原型 | 七任务基线、问题到原型/验收映射、设计态交互合同与上游许可研究有工件 | 原型与 fake 图片不是最终真实商品可用性或 C17/C15；设置/T7 仍待正式实现 |
| R3.1/R3.2 工具与验证分层 | TS 6.0.3/Node 24.19.0/npm 11.17.0 锁定；223 Node 用例；宿主行为留真实浏览器；分类登记与 CI 配置已接线 | `jsconfig.json:12–15` 仅 errors.js/invalidation.js。零诊断不是整个 domain、session、workspace 的类型通过；本轮没有当前提交的远程 CI 运行 |
| R3.3 会话切片 | session.js 管理 boot/open/close/generation；动作冻结项目归属；历史 11 项 run2/run3 覆盖 ready 延迟、A/B、陈旧编辑和重开 | 历史报告无精确代码字节 hash，不直接当当前最终证据；消除 ready 窗口不证明原间歇故障根治 |
| R4.1 候选评估 | OpenAI/Gemini/Seedream 与 qwen 的能力/协议/费用/条款比较可读，明确区分文档声明与实测 | 无第二模型选择批准、无 PoC 授权、无真实图片质量/费用证据；Seedream flash 精确 ID、价格、地区条款仍未知 |
| R6.4 存储复访 | 报告记录现实规模及 2000 版单链合成压力，保守建议“不改”，未改 schema | 只有叙述报告，缺原始测量/代码指纹、正式打开全链和实际内存峰值；不能独立复核，完成状态需回退至 pending |

对应历史来源：[基线 cutover](development-cutover-20261001-143954.md)、[原型](prototype-review-20261002.md)、[验证分层](verification-seams-20261002.md)、[会话](session-lifecycle-20261002-r33-update.md)、[模型评估](image-candidate-review-20261002.md)、[Seedream 补充](image-candidate-review-20261002-seedream.md)、[存储报告](storage-contract-review-20261003.md)。原材料存在证明可以继续，不证明最终版本已经完成。

## 4. 主要问题与处置归属

### A1 · 发布阻断：交付 manifest 归因错误（R6.3 / RC16）

`app/product_v2/workspace.js:6144–6158` 已取得采用候选原 action 的 Attempt，但仍通过 `promptRecordOf(shot.shot_id)` 获取当前 Prompt，写入 `prompt_version/hash`。采用旧候选且当前 Prompt 已前进时，交付图片与所述生成来源不一致。`domain/attempt.js` 已冻结原请求的 Prompt version/hash；无需新增 provenance store。交付验证未覆盖该归因反例。

要求：选择旧候选、改当前 Prompt 后实际导出 ZIP，manifest 必须等于候选原 Attempt 的冻结身份，且图片 hash/无关 Shot 不变；缺原身份明确拒绝，不猜当前头。本轮不修产品，保留 blocker。state 旧 RC18 引用校正为 RC16；当前 RC18 专指 C17/C15。

