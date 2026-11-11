<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/control-preparation-20261001.md -->
# 重构计划准备与控制面校准 · 2026-10-01
[返回 control-preparation-20261001.md](control-preparation-20261001.md)

# 重构计划准备与控制面校准 · 2026-10-01

NOT-AUTHORITY: point-in-time preparation evidence; not a plan, current state, Goal observation or product completion

## 本轮事实与权限

用户要求：详细实施计划落盘、控制面校准、拟创建Goal原文，下一任务不得依赖会话。用户已确认浏览器本地优先+Python网关、有限模型解耦、BYOK为主默认档受限试用、第二生图模型先评估、前端工程化及UI人体工程审计方向。

本轮没有创建或变更系统Goal，没有开始产品重构、执行UI审计、调用付费模型、上传素材、写远程Secrets、部署或Git提交/推送。实际模型与库/框架、预算/访问策略仍待对应任务门。

## 基线与校准原因

旧current state写V2.7.1 done、blockers=[]、next_action V2.7.3；用户后续报告了verify_v2_1_2间歇失败及两轮回归阻塞，且无带时间线失败样本。以用户报告为实际失败事实，不重跑来确认/否定；新state记录未闭合根因，由R1.2/R3.3承接，旧done不充当当前发布绿灯。

旧系统Goal最近实际仓库读数：01a0ca17-2179-7eb0-969a-af9c79c4d8ca，active@2026-10-01T14:22:19+08:00。本轮未重新读取系统状态，文档归档不改变生命周期；不得把它写成已经paused或complete。

修改前精确快照（工作区根相对路径）：
`_stage-amz-control/refactor-plan-2026-10-01T085723692Z/`。
旧state原始字节保存在该快照，仓库历史基线 `_working/amz-listing-kit-product-v2-baseline/state.md` 仅改本地身份/开放相位并移除历史下一动作；已完成证据与旧实际Goal读数保留。

## 本轮产物

- 唯一当前目标 `docs/product-v2-refactor-plan.md`：8阶段、26任务、逐卡输入/动作/输出/验收/失败回退、20项完成矩阵、UI场景/窗口/缩放/键盘、预算与人审门、唯一拟建Goal原文。
- context的SEL-014..017及旧选型复访：确认方向，不冒充具体库/第二模型或BYOK已实现。
- INDEX/AGENTS/README/UI合同路由切换；旧plan/state/走查任务书标历史，旧C15/C17没有被宣布通过。
- 唯一state为prepared：新Goal ID/实际读数为空，未绑定原因持久化，无active施工；R0校验后下一任务是R1.1 Goal核对/绑定。
- 控制守卫和反向探针增加prepared合法/非法情形；冷恢复入口 `tools/refactor_resume.py` 只读。

## 验证状态

首轮集成实际运行：文档静态守卫 rc=0；状态守卫 rc=0；修正后状态反向探针33向全部匹配，登记反向探针12向全部匹配，均逐字节还原；独立进程冷恢复 rc=0，读取8阶段/26任务、prepared/null Goal及R0.2卡。下面将记录完成R0.2、next切至R1.1之后的最终运行。


首次登记探针N因硬编码旧V2.5.5 current done事实退役后rc=0而失败；删除这条依赖旧任务身份/头文字的过时断言及其脚手架，不把历史任务塞回新state，不修改现有登记守卫规则。保留12条真实登记/双权威/依赖漂移负例。

首次状态探针F假设至少一阶段done而StopIteration；改为有done取done、否则首阶段构造缺证据负例。第二次AC把v2 Gate依赖搬进只接受任务引用的legacy形状，同时触发J6；修正legacy负例仅含合法任务引用，使它只因prepared身份触发J9。未放宽生产守卫，也未扩大探针允许tag集合。
## 限度
计划与准备控制完成不证明重构完成、UI改善、模型兼容、安全上线、人审通过或Goal已创建。文件本地持久化不等于已提交/CI可见；本轮没有提交权限执行，需未来精确纳入权威文件与选中证据。


