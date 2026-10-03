# V2.R4.2 / V2.R5.2 火山真实链收尾笔记（2026-10-03）

> CONTROL-STATUS: superseded · R4.2/R5.2 已完成并写入 current state；此笔记保留本轮事实与证据指针，不据此执行。

## 本轮发生了什么

1. `tools/verify_v2_4_5_live_reference.py` 扩展 `--image-provider`（默认 dashscope-image，`volcengine-ark` 走同步链），
   按键名选择 ARK_API_KEY / DASHSCOPE_API_KEY，同步/异步分支各自的 01/02/03/04 断言与 boundary/标题文案。
2. 先决修复（src/providers/v2_volcengine_image.py）：
   - `_as_transport(None)` 之前返回裸函数 `_requests_transport`，直接探测时 `AttributeError: 'function' object has no attribute 'request'`；
     run1 在产品路径表现为网关 500（上游未发生调用，0 费用）。已改为 `_FunctionTransport(_requests_transport)`，与 dashscope 同模式。
3. 付费记录（_working/amz-listing-kit-product-v2/budget-ledger.json，本期合计 4 次生图 / ¥0.56）：
   - dashscope qwen-image run5 单次 ¥0.2（既有证据 145223）。
   - volcengine flash：直接 API 探测 1 次（¥0.12，无证据文件，shell 输出）；
     run2 产品路径 submit succeeded 但验证器在同步终态下死等 `submitted` 属性（¥0.12，154037）；
     run3 全绿 5/5（¥0.12，154157：`evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json`，
     已提交 1344×1344 png 1,700,436 B，task_id=null、status 零外呼、sha 双边一致）。
   - run1（153732）0 费用：500 发生在上游调用之前。
4. 验证器时序适配：同步协议一步到 succeeded，没有 `submitted` 中间态；`wait_state` 改为按 provider 等终态（run2 失败根因）。
5. 离线回归：`tools/verify_v2_r5_2_two_adapters.py` passed（154254）、`tools/verify_v2_5_2_vlm_review.py` 全 PASS；CI 已有 ARK_API_KEY 映射。
6. state 更新：V2.R4.2 / V2.R5.2 done；Phase 4/5/6 done（复用各自已存在的 gate 证据文件）；Phase 7 active；next_action_task=V2.R7.1；
   blockers 清空（无依赖未满足的任务）。check_project_state / check_docs / refactor_resume 全过。

## 预算状态

- 已花 ¥0.56 / ¥5.00；生图 4/8、语义 0/4；剩余授权充足但 R7.1 只按"必要验收"最小化再调用。
