## Summary

**批次 8–17 工程差量：普通决定消费链、发送前成本门、两模式真实纵向、五图两包往返。** 承接已合并 #18，不重建已交付基线，不关闭完整产品工单。Refs #9, #8, #7, #10。

本批把 #9/#8 的差量推到「真实成品路径走完」：原项目 `17b6b29f` 内原照重画 + 候选编辑各 1 张真实采用（2 次真实调用，0.42 元上界），用户两项普通回答后的场景/尺寸重做（4 次真实调用，0.82 元上界），交付包/项目包在实际页面下载、独立空 profile 导入、再导出往返。

- 批 8–14：普通决定/单图覆盖/确认文案/精确 measurement 绑定进入唯一编译链；两模式（候选编辑 / 原照重生成）复用 generation owner 的准备-确认-当前性-OCC 预约-提交-观察；新 Prompt2 / Confirmation3 / Snapshot3 / Attempt3 同组切换，实存 Confirmation1/2 与身份完整 Attempt2 只读原形，新动作不消费旧授权；语义文案响应与事实/文案请求生命周期收回现有所有者。
- 批 15：**发送前成本门**——逐图费用上界与官方定价依据进确认面，缺定价不放行生成；人工全文须明确处置；事实卡片判据修正（见下）。
- 批 16–17：真实成品路径两段 + 编译器缺陷修复（「不标数字」时不再邀请自造引线），留业务合同测试 `prompt-expression-contract.test.mjs` P23b。

### 判据修正：CI 红灯 V2.2.3-22（原 head `9aedd30`）

`tools/verify_v2_2_3_intake_understanding.py` 删掉了**面板级**断言 `"product_input" in panel_main or "fake-deepseek" in panel_main`。这不是放宽自证：探针实测（[evidence.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/ci22-panel-assertion-20261019/evidence.json) + `probe-panel.out`）显示，删 keys 的可见文本里只剩两条**设计上就要人读**的模型身份行（`#analyze-gate`「将发给 fake-deepseek-v4.1-flash…」、`#analyze-result` 分析记录），而全部工程标识（`标识 …· 版本 … · 来源引用 … product_input:intake@v2`）都在 closed `<details>` 里。逐行断言完整保留：主行不得含 slot_id / `版本 v` / sha256 / 12+ hex，且标识必须出现在该卡技术详情。

### 退役

`tools/verify_v2_volc_adopt_export.py` 读取历史 spent 摘要并硬编码旧 5 元/8 图门，不能继续充当当前收费入口，随账本控制块退役；源字节封存 `_stage-amz-control/resume-extension-20261019T105641Z/retired-paid-cli-before.zip`，理由进 `docs/product-v2-refactor-plan.md`。

## Evidence

本批完整范围与逐批证据（含截图、请求字节、包往返）：

- 晋级/排除清单与门输出：[batch18-promotion-20261019/promotion.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/promotion.json)、[gates/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/gates)
- 真实成品路径（16–17 批）：[resume-extension-20261019T105641Z/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/resume-extension-20261019T105641Z)（`b16-real-vertical.json`、`b16-actual-outbound.json`、`batch-17-evidence.json`、采用图 PNG）
- 消费方迁移/新旧合同切换：[contract-consumer-fix-20261019/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/contract-consumer-fix-20261019)、[copy-adoption-contract-20261019/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/copy-adoption-contract-20261019)、[consumer-cutover-20261019/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/consumer-cutover-20261019)
- 理解界面 CI 对齐（本机 26 项全过）：[evals/product-v2/v2.2.3-intake-understanding-20261019-211559.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/evals/product-v2/v2.2.3-intake-understanding-20261019-211559.json)
- 回归与逐笔账：[v2.7.1-regression-20261019-121022-final.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/evals/product-v2/v2.7.1-regression-20261019-121022-final.json)、[_working/.../budget-ledger.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_working/amz-listing-kit-product-v2/budget-ledger.json)

本机门（实际退出码，输出在 `gates/`）：`npm run check:types` rc=0；`npm run build:frontend` rc=0；`npm run test:domain` 281 项 rc=0；`tools/check_docs.py --no-run` rc=0；`tools/check_project_state.py` rc=0。

提交内容的晋级规则：产品/工具/测试/配置/治理的已跟踪改动 + 批次证据目录（含探针脚本与截图）入库；`chrome-profile/`、`_stage-amz-control` 根目录临时输出、>20MB 的交付/项目包 ZIP（逐图字节与 manifest 已另行入库）不入库，清单见 `promotion.json`。

## Not yet verified（未证范围）

- **真实像素品质**：五图由人工采用，但 C17 独立真人签字不在本轮，自动化不代签。
- **线上/同源恢复**：合并后执行——受保护 CI 发布至既有 HTTPS origin、线上真实项目查看/采用/五图/两包下载、独立导入刷新、实际不同旧 image 同源恢复及其旧包可用；本 PR 尚未合并，故上述均未发生。
- **最终冻结两轮**：`verify_v2_7_1_regression.py --rounds 2` 须在最终候选上重跑（早于最后消费者的两轮不用于放行）。
- 5712px 历史文本溢出个案：已有同原件可逆机制复现（复放 5720px，8px 差值未归因），不代签最终工作台尺寸/原生缩放矩阵。

## Merge Danger

- **Door：One-way for new payload writes.** 新客户端保留旧记录原字节；旧客户端显式拒绝新 payload，不提供降级或迁移服务。代码/image 可沿既有事务回退，但必须同时保留对应旧版本项目包及新版本数据，不能用旧客户端覆盖新历史。
- **新增行为：成本门。** 缺官方定价/费用上界不确定时生成按钮保持不可用（新的显式阻断，不是静默跳过）。
- **Blast radius：** Prompt/规格/引用与成本摘要、摘要授权/OCC 预约、项目包读写（Confirmation3/Snapshot3/Attempt3）、相关界面与语义辅助消费者。服务端仍无业务项目持久化；默认试用 closed，BYOK 请求/标签页内存；无新模型、依赖、凭据渠道或发布平台。
- 本 PR 不绕过保护，不直推 main，不以局部证据准入合并。
