<!-- 拆分件 product-v2-refactor-plan.md · 第37/42片 · billing-preservation-history · main 行1293–1314 · 源 11902b32651f4690f7367624377dcde6652e0a97 -->
> 导航：父页 [product-v2-refactor-plan.md](product-v2-refactor-plan.md) · 36 [上一片](product-v2-refactor-plan.36-authorization-preparation.md) · 38 [下一片](product-v2-refactor-plan.38-audit-recovery-authority.md)
> 本片逐字节保存 main 原件「§17.12.4–17.12.6 历史费用、恢复与补图」，不重写、不摘要；完整计划须按父页目录顺序与注册表规则拼接后阅读。
> 续接标记：无（本片首尾都不跨越 Markdown 围栏，正文与 main 原件逐字节相同）。
#### 17.12.4 价格、凭据与启动时仍须核实的事实

- **现有图像模型已复核官方ID/北京价格**：百炼[qwen-image-3.0](https://help.aliyun.com/zh/model-studio/qwen-image-3-0)的1K/2K输入每张0.02元、单输出0.18元，产品1–3张实际输入时预留 `0.18 + 0.02×实际输入张数`（最高0.24元）；超3张拒绝，不用截断计价。火山[官方列表](https://www.volcengine.com/docs/ark/model-list)明确 `doubao-seedream-5-0-flash-260915`，[官方价格](https://www.volcengine.com/docs/ark/model-pricing)输入免费、输出0.12元，单输出预留0.12元。火山定价页直接抽取不全时本次经只读reader代理读取官方原页；来源与获取方式保存在准备证据，不冒充已核订单/结算。
- **理解/复核额度不是强制调用**：`qwen-vl-max`在本次官方价格/视觉模型列表及旧独立页中未重新核到精确可用ID与现价；不据此断言已下线，也不静默换型。旧0.23元等预留保留历史，但不能充当新的收费上界；在精确ID/现价可核前不发该模型的商品看图/单图/整套复核。主流程先用既有纯人工路径，可选能力的必要最终补证仍按原验收保留，不能因此签全通过。
- **文字理解若实际需要**：[DeepSeek官方北京页](https://docs.bailian.console.aliyun.com/zh/model-studio/deepseek-v4-1-flash)忙时输入2元/百万、输出8元/百万，最大输入1000000；现有Adapter默认输出5000且可被有效配置改变。若实际有效输出上限≤5000且协议确实约束全部计费输出，则保守预留2.04元；更小上界必须证明本次完整请求token上限，不能把旧1231-token实耗或0.05元经验值当未来最大值。有效参数或计费输出边界不明时不调用；金额门会使“最多4次”无法全部用完，这是正确停止，不追加钱或先花再算。
- **现有安全通道**：本地仅核到DASHSCOPE_API_KEY/ARK_API_KEY环境项存在，未记录值/长度/hash、未验证有效性或账户余额；默认试用开关仍未设置、fail-closed。首批保持closed且不外发；收费阶段仅在获准进程按既有通道启用，不改公共默认策略。GitHub Secrets沿用现有DASHSCOPE_API_KEY、VOLCENGINE_API_KEY→ARK_API_KEY，不读取Secret值、不新增渠道。调用前核实际有效profile/目标/凭据来源，错误不通过换key/模型绕过。
- **本机与发布前置**：本次离线解释器/锁定包可加载，Node/npm/TypeScript匹配既有锁定版本；只证明运行工具就绪，不证明页面/产品行为。只读GitHub API已核main strict保护、现有两项required CI、enforce_admins及禁止force-push；0强制人工审批不等于已经独立审查。现有远端容器/TLS/本版本恢复仍在发布时实际核，不提前部署或把旧健康读数当本版就绪。

#### 17.12.5 恢复与保全

唯一冷恢复为`uv run --locked python tools/refactor_resume.py`，先服从当前state及§17.13。下述原origin/profile是需要实际运行时的恢复身份，不是命令成功即开产品的指令：只有用户明确恢复并且具体工作需要时，才用既有本机入口及原隔离profile，保持`http://127.0.0.1:57704`身份，Chrome显式无头且核原生命令行，不操作日常profile/桌面。§17.11.2已经成立的准备不重做，原项目真实包优先复用，不能以docs.json冒充可恢复项目包；明确恢复也不重置或重新激活已用授权。

预算激活与收费动作前复核已有action/Unknown和同账差量，逐笔预留后才外发；恢复不会重置平台已花/未结算/调用数。原结果晚到仍按原归属保全。配置模型/回退/压缩/advisor保持不变，不以准备文档证明行为纠偏长期有效。准备原字节、授权/素材/工具/保护观察及有限检查证据在 `_stage-amz-control/formal-development-preparation-20261015T123438Z/verification.json`；恢复源文件只从其中before快照取，不丢原失败/账本/用户数据，不启动后重复七profile抓取。

#### 17.12.6 单次尺寸补图授权（2026-10-16）

两平台各8次已实际用尽、原项目四张已采用而尺寸图仍有灰细框后，用户在明确说明次数门与费用的选择中回答 **“允许火山再补1张”**。同Goal `15a42a4b52b70942`；授权记录时间2026-10-16T00:08:20.484Z，唯一差量ID `bearing-size-ark-oneoff-20261016T000820484Z`。这不是重新激活各3元，也不清零历史或批次。

仅把本次火山生图上限8→9，百炼仍8；金额上限各3元、累计16元/image52/semantic18/total70、每次n=1均不变。本次只准原bearing-main尺寸图，沿当前商品原照与已核对的公称尺寸全文明确选择原照重生成，费用上界0.12元；先在原账预留，累计安全上界11.08→11.20元，保守累计image35+17=52。该明确追加只覆盖这一张，不自动挪用或合并其它余量。

失败/Unknown仍占次数和预留，不自动重试；第9张若仍不合格，停止新增生图并保全原字节与准确前沿。五图质量、两包恢复、工程准出及受保护发布标准不变，不因追加授权将四图或带框尺寸图冒充合格成品。

