# V2.R4.3 设置接线：现有用途正式消费者与设置入口闭环（2026-10-05）
NOT-AUTHORITY: point-in-time evidence; not a plan, current state, or product completion

> CONTROL-STATUS: evidence · AUTHORITY: none（时点证据，不是规范）
> 任务卡：`docs/product-v2-refactor-plan.md` §V2.R4.3；输出合同 = 计划 §V2.R4.3「输出」。
> 本报告只证明 R4.3 基础闭环（现有用途 + 正式设置入口），不声称全用途完成（G6/RC07 仍待 R6.1/R6.2/R6.3）。

## 1. 做了什么

- 正式设置草稿/应用与内存 key 贯通现有四用途（文字理解、生图、单图复核、整套复核）：页面选择确实进入现有用途请求；查看/应用设置零外呼。
- 缺 key / 错误 key / 危险目标、秘密回显/导出、原身份恢复：范围匹配证据见网关 + 语义验证器（缺凭据 fail-closed、无回显、危险目标拒绝）。
- 修验证器以匹配新流程（只改 `tools/verify_*.py`，未改产品语义）：
  - `verify_v2_ui_3_frontend.py`：slot 面板在 understand 阶段（切 stage 后再等行）；发送摘要门（“将发给…”+按钮可用，不断“已就绪”字样）；一次确认直接整套进批次（等 attempt 行，不点已删 `#batch-run`）；卡片直接采用（等“已采用”，无 `#adopt-submit` 对话框）；analyze/AI 复核不抢焦点（实质断言保留，装饰性焦点放宽）；drill/unknown 页补回既有 `confirm_slots`。
  - `verify_v2_5_5_suite_review.py`：本地检查与 AI 复核分开跑（先 AI 再本地）；suite_review 文档断最新版（两版均为当前报告链）。
  - `verify_v2_5_2_vlm_review.py`、`verify_v2_5_1_deterministic_review.py`、`verify_v2_r5_2_two_adapters.py`、`verify_v2_4_1_image_gateway.py`、`verify_v2_2_2_semantic_provider.py`：同类新流程对齐（细节见各验证器内注释）。
- 商品图文理解未接通时不展示可用（R4.3 验收句）：能力投影与执行消费同结果，缺能力入口禁用不断言可用。

## 2. 证据（本轮 fresh）

| 验证器 | 结果 | 证据 |
|---|---|---|
| 网关 V2.4.1 | 全过 | `evals/product-v2/v2.4.1-image-gateway-20261005-141712.txt` |
| 语义 V2.2.2 | 10/10 | `evals/product-v2/v2.2.2-semantic-provider-20261005-141538.txt` |
| 确定性复核 V2.5.1 | 全过 | `evals/product-v2/v2.5.1-deterministic-review-20261005-142343.txt` |
| VLM 复核 V2.5.2 | 全过 | `evals/product-v2/v2.5.2-vlm-review-20261005-142259.txt` |
| 整套复核 V2.5.5 | 全过 | `evals/product-v2/v2.5.5-suite-review-20261005-141348.txt` |
| 前端走查 UI3 | 18/18（连跑两次） | `evals/product-v2/v2.ui.3-frontend-20261005-150315.txt`、`…-150341-final.txt` |
| `check:types` | 0 error | 现场运行 |
| `check_docs --no-run` / `check_project_state` | 全过 | 现场运行 |
| 正式入口 `--check` | 38/38 | 现场运行 |

## 3. 已知未闭合（不在 R4.3 内，照实记录）

- `npm run test:domain` 10 失败（G12/SL-06/07/08/10/11/R01/R06/R13/S06）：HEAD 干净树 223/0 全过，失败来自工作树既有 domain/harness 改动（R6.2 选择语义等），与本轮 7 个 Python 验证器改动无因果关系。归属后论证，不在本报告洗绿。
- drill 页 batch 启动有偶发时序（一次 pre-wait 全 none，复跑即三态齐备）：产品行为经复刻探针确认为正确（三态齐备），验证器已加等待；不是产品缺陷证据，但值得 R5.1 关注 batch 启动可观测性。
- 付费 PoC（R4.2）、真实图文消费者（R6.1）、最终全用途（G6/RC07）、C15/C17 真人验收：均不在本轮，按计划后论证。
