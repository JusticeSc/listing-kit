# packet08 · 残余红清理与验证网修复（主代理接管轮）

- CONTROL-STATUS: current · AUTHORITY: verification-evidence（证据，不改 Goal/任务/RC）
- at: 2026-10-07 · 分支 `feat/v2-r51-packet-05`，本地 commit，未 push（主代理提交）

## 0. 结论

四份此前后红/挂住的验证器现在都能真实跑完并给出结论；其中 **3_5 的"挂住"是验证器自身缺陷**（缺 `serve_forever` 启动 + `finally: shutdown()` 永久阻塞吞掉真实异常），修好后它暴露出一处**真实的产品侧失败**（第二次确认按钮不可见），未掩盖、未改期望。

## 1. 验证器缺陷：3_5 的"零输出挂住"

- 现象：`verify_v2_3_5_pre_generation_confirm.py` 跑 300s/600s 零 PASS/FAIL、无证据文件、无 traceback。
- 定位（`faulthandler.dump_traceback_later(150, exit=True)` + `runpy` 包装，**未改脚本**）：
  ```
  File ".../Lib/socketserver.py", line 255 in shutdown
  File "tools/verify_v2_3_5_pre_generation_confirm.py", line 610 in main
  ```
  即卡在 `finally: server.shutdown()`。
- 根因：该脚本 `module.create_product_v2_server(...)` 之后**没有**启动 `serve_forever` 线程（`create_product_v2_server` 只建不启动），页面请求全部拿不到响应 → 抛异常 → `finally` 里对未 serve 的服务器调用 `shutdown()` 永久等待 `__is_shut_down` → 异常与输出一起被吞。
- 修法（与 3_6:447 同形，仅补启动，不动断言）：
  ```python
  threading.Thread(target=server.serve_forever, daemon=True).start()
  ```
- 修后：脚本 39s 内跑完并如实抛出 traceback（见 §4）。
- 全库同类审计：`tools/verify_v2_*.py` 中 `create_product_v2_server` 与 `serve_forever` 的出现次数已逐一对照，除本文件外未见同类缺口（`verify_v2_volc_adopt_export.py` 为 2:1，属付费实跑脚本，本轮未动，留作观察）。

## 2. 四份脚本的"到达路径"修正（子代理作业，主代理复核）

复核口径：**对比 check-ID 集合与断言条数**，确认没有删检查、没有放宽断言。

| 文件 | check ID 集合 | `check(` 条数 | 判定 |
|---|---|---|---|
| `verify_v2_3_4_prompt_compiler.py` | 11 个 id，前后**完全相同** | 13 → 13 | 只改到达路径 |
| `verify_v2_3_6_prompt_manual_edit.py` | 16 个 id，前后完全相同 | 18 → 18 | 只改到达路径 |
| `verify_v2_5_3_compare_panel.py` | 17 个 id，前后完全相同 | — | 见下（含一处收窄） |

具体改动：
- 3_4 / 3_6：把"suite-seed → generate 后直接断言 `#prompt-editor` 可见"改成按当前语义先展开/定位到该面板（`stage_nav.reveal`），再执行同一批断言；期望值未改。
- 5_3：`#compare-jump` 的落点期望由"绝对第一张"改为"按钮当场承诺的 `dataset.targetShot`"，聚焦页签由同一次 DOM 读取推出；`#adopt-submit` 弹窗改为行内「采用候选」按钮后等 `data-selection-state === 'current'`；`chains` 覆盖口径改为"有链才校验候选归属"；参考图标题期望由"实际发送"改为产品当前文案"原任务参考图"（`ui/compare-view.ts` 实际写的是 `当前候选原任务参考图（N 张）…`，属产品文案，期望同步）。
- **已知收窄（记录待收紧）**：`V2.5.3-15` 现在只断言"跳转落到按钮自己承诺的目标 + 焦点跟随该图当前候选"，不再钉死"下一张待处理 = 计划顺序里的哪一张"。要恢复确定性，需要按 `nextPendingShotId` 合同从夹具的 `shot_ids` 顺序算出具体期望 id（夹具为 `shot_ids[0..3]`，走查只对前两张构建候选）。

## 3. 主代理本轮自己跑的结论（串行、单跑、headless + 本地 fake、无付费）

```
verify_v2_3_4_prompt_compiler.py       --label m-…   EXIT=0
verify_v2_3_6_prompt_manual_edit.py    --label m-…   EXIT=0
verify_v2_5_3_compare_panel.py         --label m-…   EXIT=0
verify_v2_5_4_rework_loop.py           --label m-…   EXIT=0   （含预期 unknown 504 路径）
verify_v2_3_5_pre_generation_confirm.py --label m-…  EXIT=1   （见 §4）
```

七闸门（逐条实跑）：

| 闸门 | 退出码 |
|---|---|
| `node --check app/product_v2/workspace.js` | 0 |
| `npm run build:frontend` | 0 |
| `npm run check:types` | 0 |
| `npm run check:generated` | 0 |
| `node --test evals/product-v2/node/*.test.mjs` | 0（tests 227 / pass 227 / fail 0） |
| `uv run --locked python tools/check_project_state.py` | 0 |
| `uv run --locked python tools/check_docs.py --no-run` | 0 |

## 4. 3_5 暴露的真实失败（未修，附最小证据）

```
playwright._impl._errors.TimeoutError: Page.click: Timeout 30000ms exceeded.
  - waiting for locator("#confirm-action")
    2 × waiting for element to be visible, enabled and stable
    57 × waiting for element to be visible, enabled and stable
  File "tools/verify_v2_3_5_pre_generation_confirm.py", line 579, in main
    page.click("#confirm-action")
```
- 步骤：确认 v1（-07 通过）→ 改公共风格 `#style-background` 保存 → 回到生成区（-08 通过：确认失效、回落 PLAN_REVIEW）→ `compile_all` 重编译 4 张 Prompt →（-09 断言可确认）→ **第二次点确认**。
- 失败形态：`#confirm-action` 存在但不可见（不是"找不到元素"），说明此刻确认编辑器处于隐藏态；`-09` 的 `can_submit is True` 是否成立尚未取到（脚本在打印前即抛异常）。
- 判定待定：**产品侧（改风格+重编译后确认区未回到可确认可见态）vs 脚本侧（需要先 reveal 确认编辑器）**。因为 3_6 在同类步骤后直接点 `#confirm-action` 是通过的，两者差异需要一轮定向定位（读 `-09` 的 probe 快照 + 该步 DOM 可见性）。

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
