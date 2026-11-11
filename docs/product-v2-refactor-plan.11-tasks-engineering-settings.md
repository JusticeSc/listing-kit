<!-- 拆分件 product-v2-refactor-plan.md · 第11/42片 · tasks-engineering-settings · main 行369–424 · 源 11902b32651f4690f7367624377dcde6652e0a97 -->
> 导航：父页 [product-v2-refactor-plan.md](product-v2-refactor-plan.md) · 10 [上一片](product-v2-refactor-plan.10-tasks-control-audit.md) · 12 [下一片](product-v2-refactor-plan.12-tasks-generation.md)
> 本片逐字节保存 main 原件「§9 R3–R4 工程、配置与项目包任务」，不重写、不摘要；完整计划须按父页目录顺序与注册表规则拼接后阅读。
> 续接标记：无（本片首尾都不跨越 Markdown 围栏，正文与 main 原件逐字节相同）。
### V2.R3.1 · 前端工程选型

输入：G2产物、package.json原生ESM、现有Node/Python/CI/Docker策略、SEL-000。
动作：评估锁定开发依赖、JSDoc+checkJs、Node原生测试；工具必须真实PoC/许可/维护/依赖成本登记。只有原型与首切片证明手工DOM成本持续，才评估框架；构建与框架独立选型。批准后同步context及依赖登记守卫，不放开未经审查任意npm。
输出：`refactor/frontend-selection-<timestamp>.md`、SEL更新、工具版本/命令合同。
验收：类型检查不是node --check；无全仓TS强迁移；生产构建/静态路径若变化同步Docker/CI，不留两套交付物。
失败：保留原ESM运行；不装新runtime依赖先行。

### V2.R3.2 · 验证分层与CI接线

输入：工具批准与原domain/harness/verifier/CI。
动作：把纯行为验证移至直接JS；保留浏览器IDB/WebCrypto/DOM消费者轨迹；捕获正式网关装配；删除源文本/注释/复制/纯转发测试；新增验证器分类和缺接线反向对照。明确 `verify_v2_2_3` 与真实/人工入口分类。Node/开发依赖锁定，类型新改范围必须零诊断且记录旧基线迁移方式，最终受影响modules全检查。
输出：运行入口/锁/CI/分类登记；`refactor/verification-seams-<timestamp>.md`。
验收：改变业务边界可判红；分类漏项能判红；host特有行为仍真实覆盖；不以减少测试总数冒充效率改善。
失败：改验证形状不放宽语义；旧实现文本测试删除，不改钉新符号。

### V2.R3.3 · 项目会话/启动/OCC

输入：R1.2缺陷链、app/workspace/repository与新验证Seam。
动作：会话Module管理boot/DB/pointer/restore/close；准备在完整恢复前不可交互；每动作冻结project identity/session generation，旧回调不能写新项目或重置视图。编辑传观察版本并就地报冲突，追加观察保留合法串行；关闭/abort不承诺取消上游。
输出：会话Implementation、全部消费者cutover、`refactor/session-lifecycle-<timestamp>.md`。
验收：可控延迟复现旧ready窗口并修后通过；打开A/B/关闭/慢响应、双标签编辑、IDB错误均有后置条件；boot未知根因不因绿样本宣称已解。
失败：保留同版本数据/候选，按切片回退；库格式可按 §2.3 重设但不静默删除用户数据；未闭合readiness消费者判据不进G3。

### V2.R4.1 · 候选与默认档策略

输入：商品参考图/编辑需求、当前模型能力、primary供应商文档与价格/地区/数据政策。
动作：至少两个可行候选与当前qwen比对参考图忠实度、编辑、文字/尺寸/格式、同步/异步/TTL、auth/费用/许可、地区可达；文档声明与实测分开。推荐一个及被拒/复访条件；同时提出默认档访问范围/消费上限和BYOK出站策略。
输出：`refactor/image-candidate-review-<timestamp>.md`；用户确认前不把某模型写已选。
验收：不能以模型名字列表替评估；不是聊天接口兼容即生图兼容；无合格候选报告关键缺口并继续UI工程可达任务。
失败：不任意假选、不无限搜索，改变目标需要用户决定。

### V2.R4.2 · 获批限额PoC

输入：候选评估、用户选择、合法凭据、素材授权、具体调用数/金额上限、地区及停止规则。触发后准确模型为大陆火山引擎 doubao-seedream-5-0-flash-260915，不自行换型；合计新增付费≤5元，付费总次数自限最多12次（生图≤8次每次1张，语义/VLM合计≤4次），先到即停。PoC 可使用隔离本地进程的环境变量凭据通道，经授权只向获批官方目标外发，不进聊天/证据/日志；不依赖尚未实现的 R4.3 产品 BYOK 页面，也不把 PoC 通道当正式 BYOK 交付。
动作：仅完成选择必要的最少真请求，核查参考图/编辑与状态/下载/费用。超时有task先核对，无task保留Unknown并停止新提交；任何追加预算需授权，不自动重试。
输出：`refactor/image-selection-poc-<timestamp>.md`，请求摘要/供应商task/候选hash/成本和限制；context中真实选择。
验收：被选第二模型能履行产品核心图像输入用途；若只能纯文本生图则不能假装等价，范围变化需批准。
失败：余额/地区/凭据/授权缺失保持blocked并记录，不把fake当真通过。

### V2.R4.3 · 配置/BYOK/出站策略

输入：已选协议、G3、现registry/env/Adapter及默认档closed策略。离线前置为G3/R4.1，不等待R4.2付费PoC；核对已有 `VOLCENGINE_API_KEY→ARK_API_KEY` 接线及实际注入条件，不重做已成立接线、不读Secret明文。
动作：统一有效配置、用途/能力/协议/参数/目标与凭据分离；正式设置草稿/应用和内存key贯通现有文字理解、生图、单图/整套复核，能力投影与执行消费同结果。支持新增图文消费者复用同边界，但其业务合同/实际接线由R6.1图文批次实现，不以未消费占位声明可用。默认key绑定受信目标，BYOK不持久化；危险headers/私网/metadata/重定向按已有策略拒绝，失败closed，不删除白名单。
输出：配置/凭据Seam、现有用途正式消费者及设置入口、`refactor/config-and-credential-<timestamp>.md`。
验收：页面选择确实进入现有用途请求，查看/应用设置零外呼；缺key/错误key/危险目标、秘密回显/导出及原身份恢复有范围匹配证据。商品图文理解未接通时不展示可用；R6.1及最终G6/RC07必须补齐真实消费者与新能力证据，不把R4.3基础闭环当全用途完成。
失败：停默认公开档，保留用户项目；未授权不写远程secret。

### V2.R4.4 · 同版本执行身份/项目包合同

输入：现Attempt/Prompt/basis/ZIP/schema与新有效配置。
动作：冻结非secret协议/目标/模型/能力版本/credential reference；旧task按原身份核对，不为无身份旧qwen补造legacy映射。当前信封与payload先完整验证再单事务写入；新payload/真实references所有读写/冻结/报告/导出消费者同组迁移，已保留的同信封旧payload按设计§13.8严格分支读且原字节不重写。未支持的旧信封/身份/未知版本仍按§2.3整包拒绝，不把历史读取扩成万能格式兼容。配置导出不含secret。
输出：当前执行身份/包校验与fixtures、`refactor/execution-identity-package-<timestamp>.md`。
验收：换设置后已提交task不走新目标，同task不同target不串；同版本包对象/hash/候选保持；缺原key明确可恢复，密钥轮换不使无关Prompt过期。
失败：拒绝不支持包不部分写入，恢复备份而非降级覆库。

