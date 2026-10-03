NOT-AUTHORITY: point-in-time evidence; not a plan, current state, or product completion

# 开发态范围修订与 G1 验收 · 20261001-143954Z

## 用户明确授权与未授权项

用户原话：“不用考虑历史兼容性，现在仍在开发阶段，允许你做激进的设计。”

此后旧版本/schema/包迁移与真实旧工件恢复移出本轮验收，不是将缺失历史包标成已找回，也不是把它推迟为发布硬门。产品计划 §2.3 记录授权，R1.2/G1/R4.4/R6.4/RC13 相应改为当前版本的数据合同。context SEL-018 记录 clean cutover 及复访条件，SEL-016 不再把现有 Module/布局视为必须保留。

同版本候选/Prompt/人工选择历史、已提交任务的冻结身份和跨设置恢复、Unknown 不重提、刷新/重开/双标签冲突、局部失效及 ZIP哈希仍保留。允许重做结构/记录格式，不静默删除用户浏览器数据。付费模型、私有上传、新依赖选型、提交/推送、部署、V1日落仍单独设门。

§2.1 系统 Goal 原文/观察指纹保持原样；工具无 objective 更新操作。本轮没有创建/替换 Goal，不宣称系统正文已经改写。最终验收使用显式用户修订后的计划，而非暗中豁免或把缺口标 proven。

## 同版本基线独立字节核查（本轮实际执行）

两份已保存的格式2代表项目 ZIP，SHA256 与此前生成报告完全一致；testzip 均通过；逐资产 byte_size/SHA256 全匹配：

| 包 | SHA256 | 文档/资产 | 当前历史覆盖 |
|---|---|---|---|
| `packages/r12-baseline-project-a-format2-50docs.zip` | `d8421b567d9499cee7adfc5d1042bd2e6bcb557891f513441ab0722320a4a52d` | 50/5 | 4候选、12 Attempt版本、4选择、4 Prompt |
| `packages/r12-baseline-project-b-history-60docs.zip` | `09ed48fea444ba241211763092b3a8df169f707800e12fea89f46608e2b13fc0` | 60/6 | 5候选、15 Attempt版本、5选择、5 Prompt；main候选版本[1,2] |

原始核查输出另存 `development-cutover-20261001-143954.json`。这是本轮 ZIP/资产恢复材料核查，不是新 UI 导入证明。此前同代码的真实 UI 导入→跨浏览器逐文档/hash→返工→再导出证明见 `baseline-and-boot-20261001-133400.md` §4.1 及关联 V2.6.3 原始报告；后继最终版本必须重新证明当前版本往返，不能沿用本轮旧指纹。

## G1 对照

- Goal：已完成 R1.1 session 观察与用户确认；本轮重读/恢复 active，旧 ID 不承担新 objective。
- 失败承接：095710/133400 两份 boot 基线覆盖用户报告、失败样本、已知延迟/404时间线及后续判据；root cause仍未知，不宣布修复。R3.3/G3及发布门继续阻断未闭合 readiness。
- 代码可回退：103825 工作树 patch/文件快照 + 133400 哈希 + 本轮改动前权威文档/state精确快照。没有清理用户脏树。
- 当前格式数据代表基线：两份保存 ZIP 本轮核查通过，含双候选/返工历史。真实旧包缺失不再为门，缺失报告保留历史事实。
- 审计与权限：R1.3 记录层独立验收及当前四 fake/8素材 smoke 见 `recovery-and-r13-20261001-143134.md` 与 raw JSON。权限初值仍未批准，不提前做真实调用。

按修订后的验收，R1.2/G1 可以结项；不是产品缺陷已修复，也不是 R2.1 审计完成。推进 next 至 R2.1，先记录页面行为再选择激进原型，不提前改产品掩盖 baseline。

## 修改前快照

目录：`_stage-amz-control/development-cutover-20261001-143954/`。

| 路径 | 修改前SHA256 |
|---|---|
| `docs/product-v2-refactor-plan.md` | `642236956440b70e4fa1f08a2b594d5bb4ee2ccaf468d26e257dcf843c861071` |
| `docs/product-v2-project-context.md` | `6dd71a27a3c181f1b4405dae18350f461a98a38273c91507c7a6926e91652738` |
| `_working/amz-listing-kit-product-v2/state.md` | `5d55947498d3545c412affdb157c5cb40bc6d4ec9064560a62c66a5f5fed7d2b` |

历史报告不改写；README 实现描述与 UI合同的项目迁移（跨浏览器搬移）措辞保留，当前实现尚未进行 schema cutover。现有迁移代码/验证暂时保持可运行，仅在替换其产品路径的实施切片中整体移除，不在控制面修订时机械删功能。
