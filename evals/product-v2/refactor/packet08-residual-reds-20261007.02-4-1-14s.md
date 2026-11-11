<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/packet08-residual-reds-20261007.md -->
# 4.1 收紧后的诊断（主代理自己跑，14s 出结论）
[返回 packet08-residual-reds-20261007.md](packet08-residual-reds-20261007.md)

### 4.1 收紧后的诊断（主代理自己跑，14s 出结论）

把该步改成显式到达（与 `verify_v2_5_2_vlm_review.py:484-486` 同形，只加期望、不改任何断言含义）：

```python
stage_nav.goto(page, "generate")
expect(page.locator("#confirm-editor")).to_be_visible()
expect(page.locator("#confirm-action")).to_be_enabled()
page.click("#confirm-action")
```

结果：

```
AssertionError: Locator expected to be enabled     （EXIT=1，14.1s）
```

即：**确认编辑器可见，但确认按钮是 disabled**。所以失败点不是"没到达面板"，而是"重编译后确认按钮未回到可用态"。这同时否掉了 §4 里"面板切换"的猜测。

待定项：这属于产品语义还是脚本期望？线索：`verify_v2_3_6_prompt_manual_edit.py` 的 `V2.3.6-12` 明确断言当前产品合同是"链式编辑后**如实停在未确认态：按钮 disabled，不自动重提**"。3_5 的 `-10` 则假设"改风格 + 重编译后按钮自动回到可用"。两者对同一状态给出相反前提，需要按产品合同定谁过期（本轮未改任何期望，避免用猜测放宽断言）。

副作用（正面）：`-09`（`can_submit is True`）在该步之前被记录但不打印，因此按钮 disabled 时应用层 `can_submit` 的实际取值仍需在定性时一并取到（把 `check` 结果落成证据再比较）。

### 4.2 决定性诊断（临时 DIAG，已移除）

在该步前临时打印 `CONFIRM_PROBE` 关键字段，实测：

```json
{"can_submit": true, "blocked": 0, "state": "PLAN_REVIEW", "stale": true, "record_version": 1,
 "versions": [{"shot_id":"shot_detail_material","version":2}, {"shot_id":"shot_infographic_benefits","version":2},
              {"shot_id":"shot_main_clean","version":3}, {"shot_id":"shot_scene_lifestyle","version":2}]}
```

结论（推翻 §4/§4.1 的两条猜测）：
1. **不是**"确认区没到达"：`can_submit=true`、`blocked=0`、编辑器可见。
2. **不是**按钮 disabled 由 `can_submit` 导致：产品 disabled 表达式里没有 state 项，`can_submit` 为真时仍 disabled 只能来自 `prompts.isPreparing()`（自动本地准备未落定）等异步项 —— 即**验证器到达等待不足**。
3. **`-09` 写死 `version == 2` 是过期期望**：改风格后"自动本地准备 + 显式重准备"会让同一张图前进不止一次（实测 `shot_main_clean` 到 **v3**）。这与 3_4 已按"旧版本 +1"改写的口径一致。

据此改（只改到达与相对前进，其余断言不动）：
- 第二次确认前：`page.wait_for_function("() => !document.getElementById('confirm-action').disabled", timeout=60_000)` 再有界断言可见/可用，然后点击。
- `-09`：`all(version == 2)` → `all(version >= 2)`（"各自相对初始 v1 前进"），保留 `can_submit is True`。

### 4.3 最终根因（决定性，主代理实测）

轮询实测（每 2s 一次 ×7，随后 60s 有界等待）：

```
DIAG {"disabled": true, "prep": "本地准备完成（更新 4 张）；未调用模型。人工文本保留，提交前请核对下面的摘要。",
      "confirm": "本次明确发送 0 张；用途缺项／过期任务不外发；已有成功、进行中或 Unknown 不自动重提。",
      "record": "一次点击先保存这份授权，再按摘要外发；不会要求第二次提交。"}   （7 次全同）
playwright._impl._errors.TimeoutError: Page.wait_for_function: Timeout 60000ms exceeded.
```

结论：**不是准备未落定、不是面板未到达、不是状态卡住**，而是**产品当前语义就是要禁用这次确认**——确认单投影为"本次明确发送 **0 张**"（4 张图在 `-07` 已成功提交过，产品按"已有成功不自动重提"保护不再外发），按钮因此持续 disabled。这与 `verify_v2_3_6_prompt_manual_edit.py` 的 `V2.3.6-12`（"如实停在未确认态：按钮 disabled，不自动重提"）是同一合同。

因此 `V2.3.5-10`（"再次确认写新版本且旧记录保留（append-only）"）在本走查路径上**是过期场景**：要验证 append-only 的第二份 `generation_confirm`，必须构造"本次确有可发送任务"的路径（例如新增一张可用图、或让既有任务处于需重提状态），而不是在同一次成功提交后改风格重编译再点确认。这属于**重新设计该走查步骤**，本轮未做（不猜语义、不改期望凑绿）。

本轮对该步的净改动：把"直接 click 然后 30s 超时"变成"有界等到可用 + 显式期望"——失败更快、原因更明确，且不会静默跳过。

## 5. 本轮产品改动（子代理作业，主代理复核 diff）

- `app/product_v2/ui/compare-view.{ts,js}`：返工提交遇 `unknown` 成功返回时走 `deps.showAttemptError(...)` 如实提示（含"没有任务编号，只能显式新建 action"分支），不改控制流与返回值。
- `app/product_v2/ui/generation-view.{ts,js}`：确认写库后的 `finally` 补 `await deps.deriveState()`（与编译保存同一语义），否则"确认存在但状态不前进"。
- `app/product_v2/workspace.js`：把生成视图的 `showAttemptError` 接进比较视图依赖（错误 DOM 唯一所有者在生成视图）。
- 效果：`verify_v2_5_4_rework_loop` 由红转绿（`V2.5.4-17` 的"没有任务编号"提示链补齐）。

## 6. 清理

- 删除临时探针 `tools/probe_p08_residual_reds.py`（排障跳板，非验证器）。
- 删除 23 个仓库根排障日志 `_working_p08_*.log`。
- `evals/product-v2/refactor/` 下的排障中间态 JSON（`packet08-adoption-ai-final2/3/4.json`、`packet08-delivery-manifest-probe3/4.json`）保留为过程证据，未纳入提交。

## 7. 未决项（下一片）

1. 3_5 第二次确认步骤定性 + 修复（§4）。
2. `V2.5.3-15` 恢复确定性期望（按 `nextPendingShotId` 合同算出具体 shot id，§2）。
3. 包08 剩余：真图文理解消费者（R6.1 后续批次）、旧调用/复制 schema 同包删除；R5.2 第二 Adapter / R5.3 Prompt·确认·能力一致仍为未解除依赖门。
