## Summary

**批次 8–17 工程差量：普通决定消费链、发送前成本门、两模式真实纵向、五图两包往返。** 承接已合并 #18，不重建已交付基线，不关闭完整产品工单。Refs #9, #8, #7, #10。

本批把 #9/#8 的差量推到「真实成品路径走完」：原项目 `17b6b29f` 内原照重画 + 候选编辑各 1 张真实采用（2 次真实调用，0.42 元上界），用户两项普通回答后的场景/尺寸重做（4 次真实调用，0.82 元上界），交付包/项目包在实际页面下载、独立空 profile 导入、再导出往返。

- 批 8–14：普通决定/单图覆盖/确认文案/精确 measurement 绑定进入唯一编译链；两模式（候选编辑 / 原照重生成）复用 generation owner 的准备-确认-当前性-OCC 预约-提交-观察；新 Prompt2 / Confirmation3 / Snapshot3 / Attempt3 同组切换，实存 Confirmation1/2 与身份完整 Attempt2 只读原形，新动作不消费旧授权；语义文案响应与事实/文案请求生命周期收回现有所有者。
- 批 15：**发送前成本门**——逐图费用上界与官方定价依据进确认面，缺定价不放行生成；人工全文须明确处置；事实卡片判据修正（见下）。
- 批 16–17：真实成品路径两段 + 编译器缺陷修复（「不标数字」时不再邀请自造引线），留业务合同测试 `prompt-expression-contract.test.mjs` P23b。

### 判据修正：CI 红灯 V2.2.3-22（原 head `9aedd30`）

`tools/verify_v2_2_3_intake_understanding.py` 删掉了**面板级**断言 `"product_input" in panel_main or "fake-deepseek" in panel_main`。这不是放宽自证：探针实测（[evidence.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/ci22-panel-assertion-20261019/evidence.json) + `probe-panel.out`）显示，删 keys 的可见文本里只剩两条**设计上就要人读**的模型身份行（`#analyze-gate`「将发给 fake-deepseek-v4.1-flash…」、`#analyze-result` 分析记录），而全部工程标识（`标识 …· 版本 … · 来源引用 … product_input:intake@v2`）都在 closed `<details>` 里。逐行断言完整保留：主行不得含 slot_id / `版本 v` / sha256 / 12+ hex，且标识必须出现在该卡技术详情。

### 2026-10-19 修复轮：`d0462ea` 的 Control plane 红灯 `V2.4.4-03/99`

run `39260212352`（head `d0462ea3743e`）失败于 `V2.4.4-03 就绪：首批摘要范围=未提交全集（4 张）…` 与 `V2.4.4-99 浏览器闭环在完成前中断`。根因不是产品回归，是验证器口径停在 B4 之前：B4 起制作区一次只渲染「正看着的那张图」，确认摘要默认是**单张（跟随正在查看的图）**，要发四张必须先显式切到批量范围。据此修复：

- `verify_v2_4_4_candidate_blob.py`：读候选行前先 `select_make_shot`（用户真实路径），并把「默认=单张 + 范围行如实列未选图」固化为新断言 `V2.4.4-03a`，四张全集走显式批量（与 `verify_v2_4_3` 的 -03a/-03 同口径）。
- `verify_v2_6_1_selection.py`：比较面板左栏设计是「常驻单图 + 下拉」，参考图判据改为「下拉选项顺序 == 该候选原任务冻结的参考图顺序，且常驻图 ∈ 该集合」；旧断言要求一次铺满 `li`，在编辑来源模式的候选（2 张参考图）上会错位。
- `verify_v2_2_2_semantic_provider.py`：为既有的系统提示断言补说明注释——独立复核确认该断言读的确实是真实出站 body（`role=system` 含身份回显与 60 字符规则）；本轮工作树草稿曾把这组断言删掉，提交前已恢复，因此提交的净效果是注释，不是「新增断言」。
- `verify_v2_packet08_adoption_ai.py`：VLM 三态短语逐字对齐域层唯一来源 `app/product_v2/domain/review.js:1157-1158`（未检查/未完成/已检查），不用近义短语族。
- `verify_v2_3_5_pre_generation_confirm.py` / `verify_v2_5_4_rework_loop.py` / `verify_v2_r5_2_two_adapters.py`：单张范围判据不许退化成摘要自证（读不到「正在查看的图」标记直接失败、发送行必须逐字等于正看图）；返工合同版本期望值改回验证器自带字面量（产品模块值只做一致性交叉核对）；UI 行断言改为逐图切过去读该图执行区。
- `docs/product-v2-ui-contract.md` §4.6：摘要范围条款按 B4 的明确范围行改写（单张跟随正看图 / 多张勾选待发送范围），文档、产品与验证器同口径。

### V2.7.3 走查脚本迁移 + R5.1 页面夹具退役

`tools/rehearse_v273_walkthrough.py` 从旧四段/旧选择模型迁移到当前产品（真实阶段导航、范围行、整套检查门、导出下载、390px），迁移后一次实跑：截图 21 张、`本次范围 1 张（未选 3）` → 切批量 4 张全部 `succeeded`、返工候选 1→2、整套检查阻断 0、导出 43,970B（manifest 声明的 sha256/byte_size 与实际字节逐条相等、4 张图）、零 console/page/http 错误、390px 无横向溢出。它接替已失去消费者的 `tools/repro_r51_*.py` 四条页面夹具，后者退役：字节封存 `retired-r51-repros-20261019T141454Z.zip`（sha256 `a0f77dfb…`），`git grep repro_r51` 仅命中历史报告与封存快照，无 CI/脚本/文档入口消费者。

### 独立复核后的修复轮：走查判据改为「用户可见优先」

独立复核（`RehearsalMigrationReview`）判定迁移后的 VLM 步骤 `incorrect`：唯一判据是 IndexedDB 谓词，屏幕上的结果从未被断言，且当时提交的走查证据里 `vlm_review` 读数为 `after_version=1/outcome=null`，与同一次运行截图里的「VLM 已检查」矛盾。据此修复并整批替换证据：

- VLM 步骤改为**先断言用户可见结果**：本图执行区主行出现「VLM 已检查」→ 比较面板 `[data-compare-vlm=checked]` → 库里的报告只作辅助核对；`review_report` 只在有 `vlm` 的行里取最新（旧实现会把确定性报告 `vlm=null` 当成复核结果）。
- 整套检查跳转按钮不再「有就点、没有也过」：断言 `count==1`、文案含「整套检查」、点击后 `#suite-review-run` 聚焦——V2.6.11 的历史红灯正是这条入口缺失。
- 交付包解包逐条比对 manifest 声明 `sha256`/`byte_size` 与实际字节，`broken` 非空即失败（旧实现只留一个恒真的 `has_manifest`）。
- 390px 四阶段断言无横向溢出；批量提交后断言四张 `attempt_states` 全为 `succeeded`（`wait_terminal` 也接受 failed/unknown）。
- 事实确认后按产品自己的口径断言「必须确认的槽位 X / Y 已确认」，剩余非必填槽位（本次 5 项）如实入证，不假装全填。
- **返工后显式选新候选再采用**，并断言交付包里就是那张返工候选（`images/shot_main_clean-act-4b101d07….png`）——旧走查采用的一直是原始候选，返工→采用→交付这段没有真正走过。
- 复跑暴露并修掉了走查自身的两个错误判据：首页盲打字被 lit 重渲染吞键（改为 fill + 点「新建项目」）；把行上的 `data-review-vlm` 当 VLM 结果（该属性属确定性报告视图，outcome 在比较面板披露区）。
- 旧批次证据已从仓库删除（`v273-rehearsal-20261019-221928` 23 个文件），由 `v273-rehearsal-20261019-230004` 取代；逐条差异见 `review-round2-20261019.json`。

### 第二个独立复核（验证器判据）：无阻断，四条 MINOR 已处理

`VerifyIntegrityReview` 复核了 8 个验证器的改动：**没有任何 check id 被删**（`d0462ea→8eaecc6` 逐文件比对 lost=[]，只新增 `V2.4.4-03a`），V2.2.2 的系统提示断言确认为真实出站 body；给出的四条 MINOR 全部处理：

- `V2.4.4-03a` 之前只看第一张图，分不开「跟随正看图」与「固定第一张」——改为先切到第二张再读摘要（`viewed == [shot_ids[1]]` 且单张范围就是它），随后切回第一张供 `-04/-05` 读行投影；
- `V2.2.3-22` 的模型 id 判据在能力缺 `model_id` 时会静默空转，且主行文本包含按设计带 provider/model 的文案提议行——`-02` 增断言 `model_id` 非空字符串，主行克隆剔除 `.copy-proposals`；
- 文档 §4.6 的「未选数量与原因」改为「未选数量，并指明实发与排除原因见发送摘要」（产品行为如此）；
- `verify_v2_5_4` 的注释改为与新判据一致（按登记字面量判、产品模块值只做交叉核对）。

复跑：`verify_v2_4_4` 15/15 rc=0、`verify_v2_2_3` 26/26 rc=0、`verify_v2_5_4` 30/30 rc=0（日志见 `batch18-promotion-20261019/final{3,4}-*.out`）。

### 退役

`tools/verify_v2_volc_adopt_export.py` 读取历史 spent 摘要并硬编码旧 5 元/8 图门，不能继续充当当前收费入口，随账本控制块退役；源字节封存 `_stage-amz-control/resume-extension-20261019T105641Z/retired-paid-cli-before.zip`，理由进 `docs/product-v2-refactor-plan.md`。

## Evidence

本批完整范围与逐批证据（含截图、请求字节、包往返）：

- 晋级/排除清单与门输出：[batch18-promotion-20261019/promotion.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/promotion.json)、[gates/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/gates)
- 真实成品路径（16–17 批）：[resume-extension-20261019T105641Z/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/resume-extension-20261019T105641Z)（`b16-real-vertical.json`、`b16-actual-outbound.json`、`batch-17-evidence.json`、采用图 PNG）
- 消费方迁移/新旧合同切换：[contract-consumer-fix-20261019/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/contract-consumer-fix-20261019)、[copy-adoption-contract-20261019/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/copy-adoption-contract-20261019)、[consumer-cutover-20261019/](https://github.com/JusticeSc/listing-kit/tree/feat/complete-product-20261018/_stage-amz-control/consumer-cutover-20261019)
- 修复轮证据与逐条 rc：[ci-fix-round-20261019.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/ci-fix-round-20261019.json)、[CI 失败原始日志](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/ci-39260212352-failed.log)
- V2.7.3 走查（复核修复后实跑，21 张截图）：[v273-rehearsal-20261019-230004.md](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/evals/product-v2/v273-rehearsal-20261019-230004.md)、[json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/evals/product-v2/v273-rehearsal-20261019-230004.json)、逐条差异 [review-round2-20261019.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_stage-amz-control/batch18-promotion-20261019/review-round2-20261019.json)
- 理解界面 CI 对齐（本机 26 项全过）：[evals/product-v2/v2.2.3-intake-understanding-20261019-211559.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/evals/product-v2/v2.2.3-intake-understanding-20261019-211559.json)
- 回归与逐笔账：[v2.7.1-regression-20261019-121022-final.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/evals/product-v2/v2.7.1-regression-20261019-121022-final.json)、[_working/.../budget-ledger.json](https://github.com/JusticeSc/listing-kit/blob/feat/complete-product-20261018/_working/amz-listing-kit-product-v2/budget-ledger.json)

本机门（实际退出码，输出在 `gates/`）：`npm run check:types` rc=0；`npm run build:frontend` rc=0；`npm run test:domain` 281 项 rc=0；`tools/check_docs.py --no-run` rc=0；`tools/check_project_state.py` rc=0。

本轮定向门（实际退出码，日志在 `batch18-promotion-20261019/{ci-fix-round-20261019.json,review-round2-20261019.json,final*.out}`）：`verify_v2_4_4` 15 项 rc=0（复核后复跑）、`verify_v2_6_1` 23 项 rc=0、`verify_v2_2_2` 11 项 rc=0、`verify_v2_2_3` 26 项 rc=0（复核后复跑）、`verify_v2_3_5` 18 项 rc=0、`verify_v2_5_4` 30 项 rc=0（复核后复跑）、`verify_v2_packet08_adoption_ai` 11 项 rc=0、`verify_v2_r5_2_two_adapters` `status=passed` rc=0、`rehearse_v273_walkthrough` rc=0（复核修复后重跑）；`npm run check:types` / `npm run build:frontend` / `npm run test:domain` rc=0；文档与状态守卫 rc=0；同 head 的 PR CI run `39270011225` 三作业 success（部署步骤按 PR 事件 skip）。

提交内容的晋级规则：产品/工具/测试/配置/治理的已跟踪改动 + 批次证据目录（含探针脚本与截图）入库；`chrome-profile/`、`_stage-amz-control` 根目录临时输出、>20MB 的交付/项目包 ZIP（逐图字节与 manifest 已另行入库）不入库，清单见 `promotion.json`。

## Not yet verified（未证范围）

- **真实像素品质**：五图由人工采用，但 C17 独立真人签字不在本轮，自动化不代签。
- **线上/同源恢复**：合并后执行——受保护 CI 发布至既有 HTTPS origin、线上真实项目查看/采用/五图/两包下载、独立导入刷新、实际不同旧 image 同源恢复及其旧包可用；本 PR 尚未合并，故上述均未发生。
- **最终冻结两轮**：`verify_v2_7_1_regression.py --rounds 2` 须在最终候选上重跑（早于最后消费者的两轮不用于放行）。
- 5712px 历史文本溢出个案：已有同原件可逆机制复现（复放 5720px，8px 差值未归因），不代签最终工作台尺寸/原生缩放矩阵。
- 内部预演（走查）**仍未覆盖**：刷新/重开恢复、项目包导入导出与再导入、比较面板左栏一次一图、单个必填图未采用的逐图交付门、Unknown 人工确认门、390px 下的点击交互、整套 AI 复核与复核失败/Unknown 路径。预演是 fake 通道、零模型调用，不构成 C15/C17 人工证据；`confirm_slots` 仍会留下非必填槽位（本次 5 项），走查只断言关键槽位已确认。

## Merge Danger

- **Door：One-way for new payload writes.** 新客户端保留旧记录原字节；旧客户端显式拒绝新 payload，不提供降级或迁移服务。代码/image 可沿既有事务回退，但必须同时保留对应旧版本项目包及新版本数据，不能用旧客户端覆盖新历史。
- **新增行为：成本门。** 缺官方定价/费用上界不确定时生成按钮保持不可用（新的显式阻断，不是静默跳过）。
- **Blast radius：** Prompt/规格/引用与成本摘要、摘要授权/OCC 预约、项目包读写（Confirmation3/Snapshot3/Attempt3）、相关界面与语义辅助消费者。服务端仍无业务项目持久化；默认试用 closed，BYOK 请求/标签页内存；无新模型、依赖、凭据渠道或发布平台。
- 本 PR 不绕过保护，不直推 main，不以局部证据准入合并。
