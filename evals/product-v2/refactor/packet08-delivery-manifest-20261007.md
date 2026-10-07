# packet08 第三片：delivery 显式整套 AI + manifest/ack（页面真跑）

> 时间 2026-10-07；fake：`FakeSuiteReviewProvider`（holder 切换 ok/unknown，经 `suite_factory` 注入）+ 本地 fake 图像/语义；0 真实模型调用，0 付费。
> 规约：计划 §14.8（未做 AI 可导出但清单如实 not_reviewed；not_run≠Unknown；硬门保留）、design §4.3（一致快照/版本 fence，工作台不组 manifest）。

## 产品改动（本片 2 个 TS + 生成 JS）

1. `app/product_v2/review-delivery.ts`（+ 生成 `review-delivery.js`）
   - 确认记录 ID 口径：删除本地影子 `acknowledgementId()`（`kind|target|rule|shots` 直拼），改用领域唯一 `acknowledgementDocumentIdOf()`（`unknownIdentityOf` → `ack-<sanitized>`）。
     根因：adoption 侧 `acknowledge()` 用 `ack-…` 落库，owner 侧 `exportDelivery/commitDeliveryRecord` 用直拼 ID 去 `ref()` 精确版本 → unknown 确认后门禁内存态已过、但导出一致快照 `ref("review_acknowledgement", …)` 抛"交付精确来源缺失"，`download_delivery` 120s 无下载。门禁与导出各读各的投影是设计内分叉，但 ID 口径必须同一。
   - 逐图 `ai_review` 口径：manifest `images[].ai_review` 与 checks `per_shot[].ai_review` 从误用的整套投影 `suiteReviewStatusOf()` 改为单图投影 `reviewStatusOf()`（整套级仍用 `suiteReviewStatusOf`）。此前逐图状态恒等于整套状态，不符合"真实检查状态"。
2. `app/product_v2/ui/compare-view.ts`（+ 生成 `compare-view.js`；指派内既有已诊断缺陷）
   - `submitRework`：`expectedVersion` 从 Prompt 版本改为所见返工确认头 `generation.reworkEntry(shotId)?.version || 0`（确认记录与 Prompt 是两条版本链；误传 Prompt 版本（当前 v2/v3）→ `generation_confirm/rework:shot` REVISION_CONFLICT、面板不关）。文案变量同步改名 `promptVersion`，仍显示 Prompt 版本。

## 真跑结论

- 新验证器 `tools/verify_v2_packet08_delivery_ai.py` **16/16 PASS**（`packet08-delivery-manifest-probe5`）：
  P08D-01a 零外发 / 01b 明说未做 AI / 01c 门禁通过 / 01d 可导出且清单整套+逐图全 not_reviewed；
  02a 显式 AI exactly 1 次外发 / 02b 报告 checked / 02c 清单 reviewed；
  03a 真实失败 unknown / 03b 未确认 BLOCK / 03c 确认后通过 / 03d 确认后可导出且清单 unknown；
  04 真硬门缺口（删候选字节）仍被拦、无新 export_record；
  05a 工作台不组 manifest / 05b 视图不组 / 05c 唯一组装点在 owner；
  06 零意外错误（unknown 场景那次 504 是期望内真实失败，已按 URL 子串过滤，不算噪音）。
- 回归（串行单跑）：`verify_v2_6_2_delivery` 全绿；`verify_v2_5_5_suite_review` 全绿；`verify_v2_5_2_vlm_review` 全绿；
  `verify_v2_5_4_rework_loop` 19/20，唯一红 `V2.5.4-17`（detail `state=unknown, task_id=null, attempts=4, requests=1, row=unknown, error=""`——状态/身份/隔离全对，仅界面提示串为空）。
  归属：**既有失败**。本片未碰返工提示链（`generation-view` 的 `showAttemptError` 路径）；断言要的"没有任务编号"文案在当前树只存在于 `generation-view` 的核对/取回分支，返工 unknown 提交走 `performSubmitAttempt` 成功返回不经过那些分支。`submitRework` 的 expectedVersion 修是断言期望行为本身（面板关闭已由 V2.5.4-08/12/13/15 同轮证明），不是凑绿。
- 七门：`node --check workspace.js` 0；`build:frontend` 0；`check:types` 0；`check:generated` 0；`node --test node/*.test.mjs` 227/227；
  `check_project_state.py` 0；`check_docs.py --no-run` 0。

## 原始捕获（`packet08-delivery-manifest-probe5.json`）

- 未做 AI 的 manifest：整套 `{"status":"not_reviewed","reason":"not_run"}`；4 张逐图全 `not_reviewed`，且 `prompt_version=1` 均为原 action 冻结值（B01 provenance 由 V2.6.2-04 同轮覆盖）。
- 显式 AI 后：整套 `{"status":"reviewed","reason":null}`，逐图仍 `not_reviewed`（单图 AI 与整套 AI 是两个独立按需动作——符合三分开；此前逐图恒等于整套是 bug，已修）。
- suite calls：AI 前 0，显式 AI 后 exactly 1；unknown 场景报告 `vlm.outcome=unknown`（fake `timeout_after_send` 真实失败，不伪造 PASS）。

## 受阻/未做

- `V2.5.4-17` error 文案空：需另起小片沿 `performSubmitAttempt → submitRework` 的 unknown 返回链补提示（不能改断言凑绿）；本片不扩范围。
- 未做：V2.R6.3 整项 done（设置/恢复另片）、state 更新（主代理收口时统一写）。
