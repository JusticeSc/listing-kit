# 百炼账号欠费导致真实模型调用暂停（2026-09-28 23:52）

> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY
> 本文件是执行证据快照，不是目标、范围或计划的正文；正文只在 docs/product-demo-goal-and-implementation-plan.md。

- 事实：`tools/run_c11_second_product.py` 为第二件商品（跑步鞋，真实照片 sku-b-shoes.jpg）调用真实语义模型时，
  `analyze_product` 返回 HTTP 400，`provider_code=Arrearage`（百炼账号欠费/余额不足）。
- 证据：provider `dashscope-qwen-semantic`、model `qwen3.7-plus`、request_id `31b2c89a-ab49-9dfb-982d-50e7ac8ab126`、
  response_sha256 `e2af915e132c1dd125ed054eb08790b00e040c919f976ef1569ebc5145b34b7a`。
- 影响：任何新的真实模型调用（语义与图片）都会失败。已完成的历史证据不受影响：
  run-05 全闭环（真实出图 4/4、单张返工、选择、导出）在欠费前已完成并落盘。
- 不做什么：不用 Mock、历史候选或本地贴图替代真实调用，不因此降低完成标准。
- 恢复条件：账号余额恢复后，重跑 `tools/run_c11_second_product.py`（换新工作空间目录）与 D4.4 首次陌生人走查。
- 相关：第二件商品的结构对比证据已有 D1.6（毛衣 vs 腕表，均为外部真实照片）；
  本文件记录的是“再用真实模型复跑一遍”的尝试被外部计费状态拒绝。
