# Product V2 控制面校准证据 · 2026-10-01 11:01:24 +08:00
NOT-AUTHORITY: point-in-time verification evidence only

## 观察与改动

- 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 实时读数为 `paused`；state 原写
  `active`，已校准为 `paused`，Phase 7 为 `pending`，下一任务仍是 `V2.7.3`。
- V2.7.3 固定为先做产品发起人 C17，修复并回归后再做首次使用者 C15。
- V2.7.4 改为 V1 日落前完成审计与回退基线；V2.7.5 负责删除 V1 后的完整回归、远程验证与
  最终候选冻结，禁止沿用删除前指纹。
- 走查工具包删除过时的自签名证书说明；UI2 报告改为准确描述自己的 fake 轨迹覆盖边界。
- 完成矩阵生成器补 `NOT-AUTHORITY`，机械“证据存在”不得冒充 `proven`。
- 证据采用最小可复检集；探索性与重复输出默认不入库，清理前反查 state/完成矩阵引用。

## 校验结果

- `tools/check_docs.py --no-run`：通过。
- `tools/check_project_state.py`：通过。
- `evals/probes/project_state.py`：19/19 方向符合预期。
- `evals/probes/docs_index.py`：12/12 方向符合预期。
- `tools/audit_v2_7_4_completion.py`：自动输出非权威标记；证据齐备 16/17、闭合 15/17，仍缺
  C15/C17。
- `tools/verify_v2_ui_2_interaction_visual.py --label control-calibration`：22/22，通过；0 真实
  模型调用，更新后的边界文本已实际生成。

## 前后身份

快照：`_stage-amz-control/control-calibration-20261001-105521/`。

| 文件 | 修改前 git blob | 修改后 git blob | 修改后 sha256 |
|---|---|---|---|
| `docs/product-v2-goal-and-implementation-plan.md` | `f18ed1cf8af78f10a397240a300c1d8ad9e3a943` | `67d761e330fd0908b82f3233ad66d11fb5dd80f5` | `bee7f3947f2efc6182e63a80720a8530a7ab608c174d727dceec2f0a0ae1146e` |
| `_working/amz-listing-kit-product-v2/state.md` | `24f9bb3ffb4623aeb1a205d830fd304abf75e7f8` | `797595d0521a25531cb68a49eef92ea5140d5143` | `acc4f3f8143d53cf08501e61d833fec38855c569d6348d469c9045f0ebb4e29f` |
| `_working/amz-listing-kit-product-v2/tasks/v273-walkthrough-kit.md` | `92a0ee03b89938e2d7f0777ecad07d90938f09ae` | `c5527a3cc351bba5ca6644b0add5617637954e33` | `58b10d2f7753ee8b44e6c3f3b0c775ed70de28c14ae4b6dbccc9efa99933476e` |
| `tools/verify_v2_ui_2_interaction_visual.py` | `0c1ce79b3536cec54c4352e42cb9395d37d63f80` | `be460739a1ccd698254eddb4fd4c06b49a51ccda` | `50344d6e22d60ca2b4b78d3e46e7e6f7723b08792f7fec29ea1b34b455d32dd0` |
| `tools/audit_v2_7_4_completion.py` | `a0108218ca7c16252584a533724904d67deea318` | `293d0d53c9a9ee3ab6b1c386344f7552fa8e77d6` | `24c3ea361130e4e627230aa6bf8a8a5294245f4ffcd4626ff77daec7159e5179` |

BOUNDARY: 本证据只证明控制面已校准并通过对应守卫，不替代 C15/C17，不证明 Goal 完成。
