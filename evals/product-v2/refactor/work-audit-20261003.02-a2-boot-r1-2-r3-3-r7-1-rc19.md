<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/work-audit-20261003.md -->
# A2 · 发布阻断：原 boot 间歇问题未闭合（R1.2/R3.3 → R7.1 / RC19）
[返回 work-audit-20261003.md](work-audit-20261003.md)

### A2 · 发布阻断：原 boot 间歇问题未闭合（R1.2/R3.3 → R7.1 / RC19）

另有明确历史失败样本：`_working/v214-rerun-20261003-001612.log:38–44`，重开后等待项目列表 count=1，在 5000ms 内持续得到 0；失败位于验证器 Python 第 371 行，不是日志第 371 行。已原样保存在 [formal-entry-reopen-failure-20261003.log](formal-entry-reopen-failure-20261003.log)。没有阶段时间线，根因仍未证；不能断言它与旧 verify_v2_1_2 的失败相同，也不能断言只是测试时序。

本轮未重跑该失败来确认或掩盖它。后续需 boot/指针读取/workspace.open/首页刷新轨迹、可控延迟与失败前后消费者证据，RC19 闭合前不得进入人审/发布。

### A3 · 外部准入阻断：R4.2 尚无授权；评估文字存在执行环

第二模型、素材、地区、凭据通道、调用数/总金额上限及停止规则未批准。Seedream 补充 §4 写 R4.2 等 R4.3 BYOK 页面，而正式依赖表是 R4.3 等 R4.2，形成执行环。

计划已澄清：R4.2 使用获批的隔离本地环境变量 PoC 通道，不等正式产品 BYOK；R4.3 才交付内存 BYOK 和安全出站。该澄清不授权任何调用，不扩大默认付费档，不自动采用推荐或 fallback 型号。R4.2 记录 blocked。

### A4 · 完成证据不足：R6.4 状态过早

`storage-contract-review-20261003.md:35–54` 提供若干 API 时间，但 `:90–91` 也明确是本机/合成样本；没有原始工件或正式打开全链峰值测量。manifest 的 document_bytes/asset_bytes 只是包内容字节，不是实际内存峰值。

报告 :62 把“算 currentVersion 需要读全链”视为 OCC 必需，论证过强：OCC 需要事务内正确取得最新版本，不等于必须物化全历史。此处不构成优化授权；先补测，再决定维持现状。旧“不改”结论保留为待复核，不否定报告数字，也不标通过。R6.4 回到 pending，依赖 G3 已满足，作为等待 R4.2 批准期间唯一可执行的下一任务。

### A5 · UI 保存状态修复证据范围

UI3 `004346` 原始结果 17/18，UI3-08 的 save_state 为空；`004616` 为 18/18。当前 `app.js:535–536` 明确恢复了 R3.3 漏接的 `instrumentSaveState(repository)` 调用，存在针对症状的修复机制，因此不能武断称纯重跑 flake。

但这两份产物没有绑定前后代码 hash，修复归因仍应补充；不能将该恢复接线或后一次绿色升级为原 boot 根治。失败保留，不覆盖、不为确认它额外重跑。

### A6 · 工程与证据成熟度

- 类型范围仍只有两个文件；生成执行、审核选择尚未 cutover 成对应业务 Module，仍在 workspace 中编排。不是靠改文件数量、迁框架或仅搬代码解决。
- 当前模型仍 env-only 的 DashScope；没有正式 BYOK、第二真实图片 Adapter 或跨设置冻结执行身份的完整闭环。不能把 fake 三用途条目算第二供应商。
- R3.2/R3.3 历史通过未绑定准确版本指纹；本轮已保存选定当前代码/配置 hash，但不会把当前 hash 补写成历史执行 hash。
- 大批修改、原始报告及当前基线尚未成为可检出的提交基线。获得提交授权后，只提升 state/验收选中的必要原材料，禁止全目录强制纳入；提交/CI/线上均保留独立证据门。

## 5. RC01–RC20 的证据分类（不是最终完成矩阵）

`proven` 只用于本轮直接成立且范围匹配的项；`indirect` 表示只有历史/部分/设计证据；`missing` 表示必要证据未取得；`contradicted` 表示当前代码或产物反驳条件。

| 条目 | 时点分类 | 证据/缺口 |
|---|---|---|
| RC01 | proven（本地会话） | 新鲜 Goal ID/正文核对、当前权威路由与冷恢复；不代表已提交可冷检出 |
| RC02 | proven（审计/冻结设计） | 七任务历史基线、原型、冻结判据；不代表最终 UI 改善完成 |
| RC03 | indirect | 图片对比原型存在，正式 R6.2 尚未交付 |
| RC04 | indirect | 历史 headless 视口/axe/键盘材料，最终版本全合同与真人未证 |
| RC05 | indirect | 本轮锁/类型范围/223行为/分类反例通过；全受影响 Module 类型与当前远程 CI 未证 |
| RC06 | indirect | 历史会话11项两轮，本轮仅本地草稿恢复 smoke |
| RC07 | missing | 统一有效配置/两个正式 Adapter 未交付 |
| RC08 | missing | BYOK、默认档限制、危险目标/secret 正反例未交付 |
| RC09 | missing | 第二实际模型核心参考图链及授权缺失 |
| RC10 | indirect | 现 qwen Prompt 合同有基线，两模型能力/请求一致未证 |
| RC11 | indirect | 已知/无 task Unknown 基线有证，跨设置原目标核对未证 |
| RC12 | indirect | 本轮单浏览器本地恢复+入口无状态；双浏览器/服务重启/磁盘范围最终复验未证 |
| RC13 | indirect | 同版本包历史往返可读，新身份合同及最终完整 hash/拒绝反例未证 |
| RC14 | indirect | partial/局部返工/旧采用有历史基线，最终 Module/UI 版本未证 |
| RC15 | indirect | VLM/报告合同基线，不等于检出质量校准或最终身份绑定 |
| RC16 | contradicted | 当前 manifest 误读 Prompt；缺归因反例 |
| RC17 | indirect | 参考采纳/许可有材料，旧生成/审核执行路径未清除 |
| RC18 | missing | 最终 C17/C15 均未完成 |
| RC19 | missing | 原 boot 根因/覆盖机制与重开失败未闭合，无最终全回归两轮 |
| RC20 | missing | V1 专批、删后最终回归/指纹及对应环境未取得 |

## 6. 本轮状态校准与恢复点

- 保留 Phase 0–3 done、Phase 4 active；不重置已获支持的任务，也不标产品完成。
- R4.2 pending→blocked：缺真实 PoC 准入授权，证据引用本审计；其他后置任务不越过其 Gate。
- R6.4 done→pending：缺原始测量和峰值/正式打开覆盖，原报告保留，附本审计说明。
- 唯一 next_action=R6.4；完成补测后按计划返回 R4.2 准入核对，而非擅自真调用。
- 更新 live Goal 观察指针、latest_audit、RC16 blocker 和正式入口失败未知项；保存真实更新时间。
- 规划详见计划 §8.1；不改变 §2.1 Goal 原文、§6 依赖、C17/C15 顺序或外部权限。

权威改前快照：`_stage-amz-control/work-audit-20261003-2026-10-02T17-55-22-190Z/`。前后 SHA256 见 [权威校准证据](work-audit-20261003-authority.json)；不以差异行数代替行为验证。

## 7. 修订后验证

串行执行 `check_docs.py`（真跑7命令）→ `check_project_state.py` → `evals/probes/project_state.py`
→ `refactor_resume.py`，结果全部通过。状态探针62向全部与预期一致，并逐字节恢复 state；
冷恢复确认 active / required 原生 Goal ID / 新观察证据，唯一下一动作 `V2.R6.4`，
任务卡定位计划第450行。记录见 [work-audit-20261003-control.json](work-audit-20261003-control.json)。
这证明审计后的计划/状态可恢复且控制反例有效，不证明 R6.4 补测、真实 PoC、
原 boot 根治、完整产品回归、人审或部署已经完成。
