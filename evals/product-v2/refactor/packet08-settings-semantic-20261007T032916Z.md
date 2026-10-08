# packet08 · 设置三用途「有效配置」贯通到实际请求（语义/看图首片）

- CONTROL-STATUS: current · AUTHORITY: verification-evidence（证据，不改变 Goal/任务/RC）
- at: 2026-10-07T03:29:16Z · 分支本地，未 push
- 范围：`V2.R6.3` 设置批次首片——三用途有效配置可见/可改、BYOK 作用域、页面所示=实际请求、旧包拒绝。
  不含：semantic 图文消费者（R6.1 后续）、第二 Adapter（R5.2）、Prompt/确认/能力一致（R5.3）。

## 0. 结论

**做成了（首片贯通，离线 headless 真路径 12/12 绿）**；依赖门（R5.2/R5.3）内的项如实标受阻，未假装通过。

## 1. 改前/改后

### 改后（本片新增/修改）

| 文件 | 改动 |
|---|---|
| `config/product-v2/providers.json` | 新增 test-only 替身条目 `fake-vision-semantic`（role=semantic, adapter=`v2_fake_vision_semantic`, `reference_images:true`, `test_double:true`）。**仅测试替身声明**，正式目录中 fake 只在显式注入接缝出现（`provider_choices(active_ids=...)`）。 |
| `src/providers/v2_fake_vision_semantic.py` | `capabilities()` 补 `configured: true`；此前缺该键导致 `_effective_summary` 落到 `provider.configured` 默认并让面板/理解区显示「缺少有效模型或凭据」。另修复一次误伤的类头（已恢复为正确实现）。 |
| `tools/verify_v2_packet08_settings_vision.py` | 无头 capabilities 直调探针（不带头，命中注入接缝）；等待 gate 渲染完成再断言；点击 `#analyze-run` 前先切回 `intake` 面板、观察槽位后切回 `understand`/`intake` 读结果；断言文案对齐接缝语义。 |

连带工作区改动（本轮之前已在，非本片）：`app/product_v2/{model-settings,project-inputs,semantic-analysis}.{ts,js}`、`app/product_v2/ui/input-view.{ts,js}`、`app/product_v2/domain/type-contracts.d.ts`、`src/providers/v2_registry.py`。

### 关键 diff 摘要

```
config/product-v2/providers.json | 19 +++++++++++++++++++
src/providers/v2_registry.py     |  8 ++++++++
（本片 verifier 与 fake 见上表）
```

## 2. 根因：`#analyze-run` 后 slot-list 30s 超时属于哪一类？

**判定：脚本/等待缺陷（验证器），不是产品缺陷。**

- 最小复现（无阶段切换直点）：
  - `#analyze-run` 在 `intake` 面板可见且可用（`is_visible=True disabled=False`），点击成功 `CLICK-OK`；
  - 断言 `#slot-list .slot-row:not([hidden])` 却超时——日志显示 `locator resolved to 10 elements`，但 `.slot-row` 只是 `hidden` 属性在 **li 自身**由 `data-status` 决定，主因是当时活动面板是 `understand` 之外/切换竞态与隐藏面板；改判为「先 `goto(intake)` 点、再 `goto(understand)` 观察」后即通过。
  - 即：点击本身有效（`vision.calls` 记录到 exactly 1 张真实图片字节，见 §3 P08-03a），失败只在验证器等待条件/阶段面板选择上。
- 因此按你的分类 **修验证器**，未改产品去凑绿。

## 3. 真跑证据（命令 + 退出码 + 关键输出）

### 3.1 packet08 验证器（headless Chrome + 本地 fake，无付费）

```
$ uv run --locked python tools/verify_v2_packet08_settings_vision.py --label packet08-settings-semantic-final
[PASS] P08-01a 能力投影露出 fake-vision 看图档（注入接缝无头直调即保留实例）
[PASS] P08-01b 设置面板三用途有效配置行可见（含缺 key 提示语）
[PASS] P08-01c 面板文案声明密钥仅标签页内存/请求级（非 secret）
[PASS] P08-01d 注入看图档后理解区声明将发送实际图片（页面所示配置）
[PASS] P08-04b 页面分析按钮可用（注入替身已配置，不锁人工主链）
[PASS] P08-04c 无 key 的看图请求体被网关拒绝（VISION_BYTES_REQUIRED，不调用模型）
[PASS] P08-03pre 点击分析前页面仍声明将发送实际图片（与看图档一致）
[PASS] P08-03a 看图替身收到 exactly 1 张真实图片字节（非空 + sha 与上传原图一致）
[PASS] P08-03b 页面所示配置与实际请求一致（模型行 + 已发送图片行含 role/sha 前缀）
[PASS] P08-03c 分析记录写真实图片来源（role/media/sha256，无字节原文）
[PASS] P08-02 探针 key 不出现在 DOM/响应/库快照/日志/请求头记录
[PASS] P08-04a 旧格式包导入拒绝（包格式版本边界仍为当前 v2，不做迁移）
evidence: evals/product-v2/refactor/packet08-settings-semantic-final.json
screenshot: C:\Users\31368\AppData\Local\Temp\amz-p08-7pf4f07u\p08-vision.png
RESULT PASS 12/12
退出码：0
```

**P08-03a/b/c 原始捕获（来自证据 JSON `captures`）**

```json
"analyze_result": "最近一次分析：4 个提案，写入 4 个槽位 · fake-vision-semantic（fake-qwen-vl-max） · 原资料 v2 · 已发送实际图片（primary/7af577c6699c…） · 2026/10/7 11:28:08 · 假看图 Provider 提案：已收到实际图片字节，仅用于有效配置贯通验证。",
"gate_text": "将发给 fake-qwen-vl-max：当前名称、介绍、卖点与重点，1 张实际图片（按列表顺序，主图优先，最多 3 张）。供应商按实际调用计费；不能据元数据宣称已经看图。",
"vision_calls": [
  {"scenario":"ok","product_name":"P08 看图贯通","vision_images":1,
   "images":[{"role":"primary","media_type":"image/png",
              "sha256":"7af577c6699c88fb4d28c4ea992237dd9dbd17026beec0b37b2ac18351d34419",
              "byte_size":3126}]}
],
"reference_sha256": "7af577c6699c88fb4d28c4ea992237dd9dbd17026beec0b37b2ac18351d34419"
```

- P08-03a：替身实收 1 张真实图片字节，`sha256` 与上传原图**完全一致**，`byte_size=3126>0`。
- P08-03b：页面所示（gate + result）与实际请求一致——`fake-qwen-vl-max`、`已发送实际图片`、`primary/7af577c6699c…`（sha 前缀）。
- P08-03c：`semantic_analysis` 记录写 `reference_images_sent=true` + `image_provenance[0].sha256==ref_sha`，且不含 `data_base64`。

**页面所示配置 = 实际请求配置**（capabilities 捕获）

```json
"capabilities": {"provider_id":"fake-vision-semantic","model_id":"fake-qwen-vl-max",
 "configured":true,"credential_source":"test_double","vision":true,"reference_images":true,
 "choices":["dashscope-semantic","dashscope-vision","fake-vision-semantic"]}
```

### 3.2 P08-02 秘密搜索（DOM 文本 / 外发请求 / 导出包 / 控制台日志）

探针 key 明文：`pk-p08-probe-key-0001`（固定测试值，仅存在于验证器源码定义处）。

```
$ uv run --locked python tools/verify_v2_packet08_settings_vision.py --label packet08-settings-semantic-final
[PASS] P08-02 探针 key 不出现在 DOM/响应/库快照/日志/请求头记录
证据 JSON: "secret_hits": []
```

退出码 0。扫描面：`document.documentElement.innerText`、`/api/v2/capabilities` 响应体、IndexedDB `documents` 全量快照、浏览器 console、全部 `/api/v2/*` 请求头记录。

磁盘补充搜索（`.gitignore` 生效域内无明文）：

```
$ grep(pk-p08-probe-key-0001) over app/ src/ config/ evals/
No matches found
```

### 3.3 P08-04a 旧格式包导入）

- `P08-04a`：包格式版本边界仍为当前 v2，旧 `format_version` 包被拒绝，不伪造迁移、不静默降级（验证器断言 + `storage/package.js` 契约 + `node --test` 227 项中的包契约用例）。
- `P08-04b/04c`：无 key 看图被拒且替身零外呼；请求体缺字节时网关回 `VISION_BYTES_REQUIRED`，不调用模型。

## 4. 七闸门（逐条命令 + 退出码）

| # | 命令 | 结果 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 退出码 0（GATE1-OK） |
| 2 | `npm run build:frontend` | 退出码 0（EMIT … input-view.ts 等） |
| 3 | `npm run check:types` | 退出码 0（`tsc --noEmit -p jsconfig.json`） |
| 4 | `npm run check:generated` | 退出码 0（CHECK … 各 .ts 生成一致性） |
| 5 | `node --test evals/product-v2/node/*.test.mjs` | 退出码 0（tests 227 / pass 227 / fail 0） |
| 6 | `uv run --locked python tools/check_project_state.py` | 退出码 0（结果：全过） |
| 7 | `uv run --locked python tools/check_docs.py --no-run` | 退出码 0（结果：全过；--no-run 仅证明文档一致，不代表命令真跑） |

## 5. 未做项与原因（受阻，最小证据）

- **semantic 图文消费者（真图文理解产品路径）**：属 R6.1 后续，本片只做设置贯通；未建新消费者、未改 semantic 请求装配语义。
- **第二 Adapter（R5.2）/ Prompt·确认·能力一致（R5.3）**：依赖门未解除，本片只用 fake 替身走正式配置/路由接缝，不接真实上游。
- 未真实付费调用：本片全部离线 headless + 本地 fake，无外呼供应商。

## 6. 证据清单

- 本文件：`evals/product-v2/refactor/packet08-settings-semantic-20261007T032916Z.md`
- 机器证据：`evals/product-v2/refactor/packet08-settings-semantic-final.json`（12/12 PASS，含原始捕获）
- 截图：`%TEMP%\amz-p08-7pf4f07u\p08-vision.png`（临时目录，随进程回收）
