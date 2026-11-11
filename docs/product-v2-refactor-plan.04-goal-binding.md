<!-- 拆分件 product-v2-refactor-plan.md · 第04/42片 · goal-binding · main 行62–85 · 源 11902b32651f4690f7367624377dcde6652e0a97 -->
> 导航：父页 [product-v2-refactor-plan.md](product-v2-refactor-plan.md) · 03 [上一片](product-v2-refactor-plan.03-goal-controls.md) · 05 [下一片](product-v2-refactor-plan.05-decisions-invariants.md)
> 本片逐字节保存 main 原件「§2.2–2.4 绑定、权限与开发态边界」，不重写、不摘要；完整计划须按父页目录顺序与注册表规则拼接后阅读。
> 续接标记：无（本片首尾都不跨越 Markdown 围栏，正文与 main 原件逐字节相同）。
### 2.2 状态与权限
- `required`：已持工具真实返回的 Goal 标识（原样 UUID 或 16 位十六进制原生 handle），当前 v2 必须同时保存观察证据并逐字核对 ID；不能把原生 handle 补造成 UUID。`optional`：仅用于未观察到/未经确认的准备窗口。`session`：接口确实未返回 ID 时的会话观察绑定，`goal_id` 必须为 null；不得在接口已返回 ID 后继续谎称缺 ID。
- 观察证据：`goal_binding_evidence` 指向仓库内 JSON（schema `amz-goal-observation/v1`，`source: goal-tool`，`authorization: user_confirmed_current_goal`，非空 `user_confirmation`，`plan_ref` 与 state 一致）。required 的 `goal_id` 与 state 相等且 `id_unavailable: false`；session 则为 `goal_id: null`、`id_unavailable: true`。读数/时刻与 state 一致，新会话/恢复必须重读真实 Goal。旧观察保留为历史，不据此声称本会话已查询。
- JSON 保留 `observed_objective` 原始展示体，state 不复制 objective；与 §2.1 比对只剥离行首 `▏`/`│` 边框、明确的 `[13;28;13;0;0;1_`/`[13;28;13;1;0;1_` 展示码及布局空白，不剥普通标点和正文。`objective_sha256` 校验此处产品原文。规划Goal不得替换产品绑定，规划完成不完成产品Goal；独立规划授权见§15.6。
- `prepared`：计划与控制面已准备；当前 Goal 尚未完成会话绑定。`goal_id` 和 system 读数为空时原因非空，不存在 active 施工任务/阶段；已完成会话绑定的 state 不再称 prepared。本地把旧记录归档为 superseded 不修改系统旧 Goal；旧 Goal 的历史生命周期证据原样保留，不谎称旧 Goal 已暂停/完成。
- 新施工须核对最新实际系统读数；历史active/paused及绑定证据不是本会话执行许可。已绑定工程记录可把next_action保留在依赖已done的blocked前沿，但blockers须有以该任务ID＋`_`开头的非空具体原因；冷恢复只允许核对/解除阻塞，不执行受限施工。prepared只允许pending下一动作。工具返回No active goal或目标为独立规划时，保存实际观察并阻断产品施工，保留产品历史绑定，不伪造其暂停/完成。用户另行明确恢复后按§16.2处理真实产品Goal与绑定，不能把规划确认当成创建/施工/付费/发布许可。

### 2.3 用户明确修订：开发态 clean cutover

用户原话（2026-10-01）：“不用考虑历史兼容性，现在仍在开发阶段，允许你做激进的设计。”

本修订取消旧版本项目包、记录 schema、缺执行身份的 legacy 记录迁移与历史工件恢复要求，包括此前 R1.2/G1 的真实旧包门和 RC13 的跨版本迁移部分；不是将缺失工件标成已恢复。用户恢复后的当前 Goal 已纳入该边界，旧 objective/观察仍保留于历史证据，不伪造系统目标更新。

允许按真实任务重做 UI/Module/Interface/记录格式，切换时迁移所有当前调用方并删除被替代路径，不为旧版本保留 shim/别名或额外迁移层。schema 破坏性变更可采用新开发库/新格式，旧格式明确拒绝且不部分写入；不静默删除现有浏览器数据。

同一版本内的候选/Prompt/人工选择历史、跨设置已提交任务的冻结身份、刷新/重开/服务重启恢复、双标签冲突、单图隔离、ZIP哈希、安全及无服务器项目持久化仍是产品功能，不能以“激进设计”豁免。付费调用、私有上传、新依赖选型、部署、提交推送及 V1 日落专批不变。

### 2.4 恢复后的验证范围与 G2 解释

用户重新设置的当前 Goal 仅要求桌面 Chrome；本轮 Chrome 无头、隔离配置和后台操作限制不变，不再把 Edge 专项作为本 Goal 的验收门。旧 Edge 记录保持历史身份。

G2 要求七条任务的审计结论齐备，包括明确记录未实现能力及其责任任务，不要求先完成 R4/R6 的设置产品能力。R2.1 已记录 T7/G01 缺口，R2.2 已冻结已实现高风险原型的可测交互；设置交互仍须由 R4.3/R6.3 闭合，RC07/RC08/RC10 与最终人审不因此豁免。原型报告末尾“G2 递延至设置能力解决、next R4.1”是旧时点建议，不覆盖当前 state 的 R3.1 断点；本解释不把 T7 标为通过，不降低最终矩阵。


