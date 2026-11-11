<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/packet08-stale-callers-20261007T084634Z.md -->
# R5（保留）：视图对 domain 纯函数的直接 import（reviewIsCurrent/reviewSummaryText/selectionSummaryText/suiteReviewSummaryText/compareRows/...）
[返回 packet08-stale-callers-20261007T084634Z.md](packet08-stale-callers-20261007T084634Z.md)

### R5（保留）：视图对 domain 纯函数的直接 import（`reviewIsCurrent/reviewSummaryText/selectionSummaryText/suiteReviewSummaryText/compareRows/...`）
- 活引用：compare-view / generation-view / delivery-view 广泛用于渲染（详见正文 grep 小节）。
- 不删原因：设计 §2.1 明确"各业务 Module → 现有 domain 纯规则"是合法依赖方向；视图读的是无状态纯函数，不是第二份报告/选择状态。真正的报告状态唯一在 adoption 内存 + IDB，manifest 唯一组装点在 review-delivery（本片验证器 P08D-05a/05b/05c 已断言）。

### R6（保留）：`type-contracts.d.ts` 全量类型（含 `SemanticImageProvenance` 等包08新增）
- 核查：`SemanticImageProvenance` / `image_provenance` / `reference_images_sent` 在 `src/providers/*.py` 是服务端 Pydantic 独立声明（服务端权威），前端 d.ts 是浏览器侧同形声明——但两者分属前后端契约层，无共享导入、无运行时重复判定；且 d.ts 类型被各 owner 广泛 import，不存在零消费者条目。
- 不删原因：无零消费者类型；跨语言同形 ≠ 可删复制（删任一侧都会断编译/断网关）。

### R7（保留）：`generation.ts:101 ReviewReportEntry` / `session.ts:38` 与 `generation.ts:92` 的双 `ActionSnapshot`
- `ReviewReportEntry`：`workspace.js:96` 有 `@typedef import`（类型引用），虽无值层使用，但删除会触 `workspace.js` typedef 悬挂；且它是无运行时成本的类型别名，不构成"两份报告状态"（真实状态在 adoption Map）。
- 双 `ActionSnapshot`：`session.ts` 版被四视图 `import type ... from "../session.js"` 消费；`generation.ts` 版被 prompts/selection/review-delivery 三 owner 消费。同形但各有活消费者，统一需改三 owner 的 import 源——属跨包重构且触公开类型面，本片"只删零消费者"口径下不动。
- 不删原因：有活消费者；合并它们是真实重构（非删除），超出本片验收口径。如后续包要合，应单独立项并全量重验类型面。

### R8（保留）：`acknowledgementDocumentIdOf` vs 已删的本地 `acknowledgementId`
- 本片前（007356c）已删本地影子 `acknowledgementId()` 并统一到领域唯一 `acknowledgementDocumentIdOf`；全库搜索确认无残留 `acknowledgementId(`（不含 `...DocumentIdOf` 前缀）调用。
- 无新增删除；单一来源已成立（adoption 落库 + delivery ref 同一 ID 口径）。

## 2. 行为不变证据

### 七闸门（逐条命令+退出码）
1. `node --check app/product_v2/workspace.js` → exit=0（G1）。
2. `npm run build:frontend` → exit=0（G2；EMIT 全部视图，含重生成的 `generation.js`）。
3. `npm run check:types` → exit=0（G3；`tsc --noEmit -p jsconfig.json` 无输出）。
4. `npm run check:generated` → exit=0（G4；全部 CHECK 行通过）。
5. `node --test evals/product-v2/node/*.test.mjs` → 227/227 pass，exit=0（G5）。
6. `uv run --locked python tools/check_project_state.py` → 全过 exit=0（G6）。
7. `uv run --locked python tools/check_docs.py --no-run` → 全过 exit=0（G7）。

### 六验证器（串行单跑，一次一个）
- `tools/verify_v2_packet08_settings_vision.py` → RESULT PASS 12/12，exit=0（fake：`fake-vision-semantic` test-only 替身，实收 1 张真实图片字节；Windows selector 10038 为验证器宿主层面的已知噪音，不影响结论）。
- `tools/verify_v2_packet08_adoption_ai.py` → RESULT PASS 11/11，exit=0（fake review 路径；含 unknown 演练的预期 504）。
- `tools/verify_v2_packet08_delivery_ai.py` → RESULT PASS 16/16，exit=0（含 P08D-05a/05b/05c 三权断言：工作台不组 manifest、视图不组 manifest/ZIP、唯一组装点在 review-delivery）。
- `tools/verify_v2_5_2_vlm_review.py` → 19/19 PASS（尾行 `V2.5.2-19 零意外`），exit=0。
- `tools/verify_v2_5_5_suite_review.py` → 全绿 exit=0（正式入口自检 45/45；截图 2 张）。
- `tools/verify_v2_6_2_delivery.py` → 全绿 exit=0（V2.6.2-11 正式入口自检全过；截图 6 张）。
- 本轮六验证器**无红**：指派中提到的"已知 3_5 的 -10 与 5_3 的 -15 既有过期场景"分属 `verify_v2_3_5*` / `verify_v2_5_3*`，不在本片要求串行的六验证器之列，故本片无"红了先判"项。

### 无真实模型调用/无付费
- 六验证器全部走本地 fake provider（settings-vision 用 `fake-vision-semantic`；adoption/delivery/VLM/suite/v2.6.2 用各自 fake review/semantic 双轨）；无 `AMZ_V2_DEFAULT_TRIAL=open`，无上游外发，无预算账本变动。

## 3. 改动清单（只 add 本片文件，不 add `_stage-amz-control/**`，不 push）
- M `app/product_v2/generation.ts`（-11/+2 行净值：删 dep 字段×2、setter 声明×2、functionDeps 项、builder 变量+注释、返回对象 setter×2、收窄 1 个 type import）
- M `app/product_v2/generation.js`（构建生成，-6/+1）
- M `app/product_v2/workspace.js`（-9：占位 dep + 三补线中的两条全删 + 注释；`setReviewFlightReader/setReviewAccess` 保留）
- M `evals/product-v2/node/generation-isolation.test.mjs`（两处测试替身去 `candidateReviewRequest`，render 回调原样保留）
- M `tools/verify_v2_r5_2_two_adapters.py`（L222 测试替身去 `candidateReviewRequest`）
- A `evals/product-v2/refactor/packet08-stale-callers-20261007T084634Z.md`（本证据）

## 4. 受阻项
- 无。本片无新增阻塞；R5.2/R5.3 依赖门未动（`verify_v2_r5_2_two_adapters.py` 仅删测试替身字段，未改断言）。
