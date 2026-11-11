<!-- 拆分件 03/03 · 父文档 evals/product-v2/refactor/packet11-regression-rounds-20261007T101243Z.md -->
# 4. 不能闭合的项与原因（共 12 项：10 真红 + 1 已知过期 + 1 flake 未定）
[返回 packet11-regression-rounds-20261007T101243Z.md](packet11-regression-rounds-20261007T101243Z.md)

## 4. 不能闭合的项与原因（共 12 项：10 真红 + 1 已知过期 + 1 flake 未定）

- A. 1_1（产品缺陷，真红）：`tools/verify_v2_1_1_indexeddb.py` 自带 `StaticHandler.roots` 只放行
  `/storage/`、`/vendor/`、`/harness/`，但 `app/product_v2/storage/repository.js` 自 R5.1 packet 05
 （e90b196）起 `import … from "../domain/index.js"`，浏览器经 `/domain/index.js` 取 domain 时 404，
  `storage-contract.js` 模块加载失败、`__V2_STORAGE_RESULTS__` 永不落定，两轮 120s 超时。
  最小证据：`_working/p11regression/logs/v11.r1.log` 尾 `TimeoutError`；
  独立复现探针确认 `/domain/index.js → 404`、`storage/index.js → 200`（同目录日志说明）。
  修法方向（二选一）：验证器静态服加 `/domain/` 路由，或 harness 导入改相对路径；
  属下一片的修动作，本片只定性不定修。
- B. 4_1 `-23`（脚本期望过期，真红）：其余 32 项全 PASS，仅磁盘不变量 FAIL。
  `added` 全是 `src/providers/__pycache__/*.pyc`（CPython 在独立运行根内 import 产品包时生成），
  非业务落盘。断言把"解释器副产物"当"业务写盘"，在当前运行方式下恒红。
  最小证据：`evals/product-v2/v2.4.1-image-gateway-20261007-175646-p11r1.txt` 的 `-23` 行
  （r2 同文件 `-p11r2` 一致）。
- C. 4_3 / 4_4（脚本缺陷，真红）：`from v2_verify_shared import (png_bytes, load_server_module,
  free_port, run_entry, read_suite, compile_all,)` 未引入 `start_static_server`，
  却在 `main` 直接调用裸名 `start_static_server()`（4_3:278、4_4:333；4_2 同位置用的是
  `shared.start_static_server()` 故不中招）。`NameError` 在第一扇区即中断，零检查执行。
  最小证据：`_working/p11regression/logs/v243.r1.log`、`v244.r1.log` 全文 8 行。
- D. 5_1（脚本缺陷，真红）：`main` 第 96 行调用裸名 `current_review_contract()`，
  但 `from v2_verify_shared import` 清单无此名（函数在 shared 第 42 行存在，
  且 5_3 用 `shared.current_review_contract()` 正常）。`NameError` 即时中断，零检查执行。
  最小证据：`_working/p11regression/logs/v251.r1.log` 全文 6 行。
- E. 6_1（脚本期望过期，真红）：`check_static_guards` 用 `html.index('<section id="adopt-panel"')`
  做源码存在性断言，当前 workspace 主链 HTML 已无该 section（采用面板结构迁移），
  `ValueError: substring not found` 在浏览器启动前即崩，零检查执行。
  最小证据：`_working/p11regression/logs/v261.r1.log` 全文 6 行。
- F. 6_4（脚本缺陷，真红）：第 160 行 `shared.fake_suite.FakeSuiteReviewProvider`，
  但 `v2_verify_shared` 无 `fake_suite` 属性（`FakeSuiteReviewProvider` 位于
  `src/providers/v2_fake_suite_review.py`）。`AttributeError` 中断，零检查执行。
  最小证据：`_working/p11regression/logs/v264.r1.log`（前有 2 项 PASS，后接 Traceback）。
- G. r5_2（产品缺陷，真红）：离线 E2E 在生成阶段 `expect(#prompt-editor).to_be_visible()`
  失败（实际 `hidden`）。aria 快照显示页面停在"生成前确认缺失或已过期：先回到「生成前确认」
  重新确认"，4 张图按钮均为 disabled——`#prompt-editor` 按产品逻辑收起，脚本仍按旧可见性假设断言。
  最小证据：`_working/p11regression/logs/r52.r1.log`（r2 逐字一致，`r52.r2.log`）。
  需按 §7.6 做机制↔现象对应（确认过期链 vs 脚本导航缺失），本片只定性不定修。
- H. ui_2（脚本缺陷，真红）：`run_workbench_checks` 用裸名 `v251.free_port()`，
  但文件内无 `import … as v251`（只有 `shared` 相关导入）。`NameError` 即时中断。
  最小证据：`_working/p11regression/logs/ui2.r1.log` 全文 11 行。
- I. ui_3（脚本缺陷，真红）：`main` 用裸名 `start_server("127.0.0.1", port)`，
  但文件内无此名（`shared.start_product_server` 存在）。`NameError` 即时中断。
  最小证据：`_working/p11regression/logs/ui3.r1.log` 全文 8 行。
- J. 3_5（已知过期，不计新回归但不能闭合）：见§3。两轮同错（60s 等待 `#confirm-action`
  enabled 超时），与任务书点名的 `-10` 过期一致；未改断言、未重跑。
- K. 4_2（flake，一轮红一轮绿，不能计绿）：r1 在 `-99/-15` FAIL（浏览器闭环中断 +
  console/page error 门连带红），r2 全 PASS。两轮原始输出对照见§5。
  按"约 2–5% flake 要刻画不要掩盖"，本片判 flake，不计入通过，需第三只眼看 r1 的 `-99`
  中断是否与 r5_2-G 同源（确认过期链）——留给修片，不在本片下结论。

## 5. flake 原始输出对照（4_2：r1 红 / r2 绿，未放宽断言）

- r1（红）：`evals/product-v2/v2.4.2-generation-attempt-20261007-175656-p11r1.json/.txt`，
  `- [FAIL] V2.4.2-99 浏览器闭环在完成前中断` +
  `- [FAIL] V2.4.2-15 零意外 console error / page error`，其余 28 项 PASS，`status: failed`。
- r2（绿）：`evals/product-v2/v2.4.2-generation-attempt-20261007-180806-p11r2.json/.txt(+.png)`，
  全部 31 项 PASS（含 `-19/-19b/-20/-21` 身份冻结链），`status: passed`。
- 对照说明：同一脚本、同一默认参数、同一串行条件，仅时间戳与 `--label` 不同；
  r1 的 `-99` 是"完成前中断"（异常冒泡），`-15` 是其连带门（中断本身产生 console/page 噪音），
  不是两个独立产品失败。r2 全绿证明产品链可走通，r1 中断的触发机制未定位——判基础设施 flake，
  不洗绿、不计通过。

## 6. 七闸门（逐条命令 + 退出码；产品文件本片零改动，闸门仅作基线留证）

| # | 命令 | 退出码 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 0 |
| 2 | `npm run build:frontend` | 0 |
| 3 | `npm run check:types` | 0 |
| 4 | `npm run check:generated` | 0 |
| 5 | `node --test evals/product-v2/node/*.test.mjs`（227 pass / 0 fail） | 0 |
| 6 | `uv run --locked python tools/check_project_state.py` | 0 |
| 7 | `uv run --locked python tools/check_docs.py --no-run` | 0 |

另：`uv run --locked python tools/check_verification.py`（非七闸门，附带）= 1，
`[FAIL] VCLASS_MISSING 未分类入口：tools/verify_v2_packet08_{adoption_ai,delivery_ai,settings_vision}.py`
—— packet08 三件套在 `config/product-v2/verification.json` 无登记。属控制面缺口，
与本轮 34 项结论无关，抛给下一片（登记或排除二选一），本片不修。

## 7. 每项一句话结论

- 1_1：真红——静态服缺 `/domain/` 路由，harness 模块 404，套件永不落定（产品侧修）。
- 1_2 / 1_3 / 1_4：真绿，两轮全过。
- 2_1 / 2_2 / 2_3：真绿，两轮全过。
- 2_4：真绿（离线 C1+C5；C2–C4 按设计 SKIP，需 `--live` 不属本轮）。
- 3_1 / 3_2 / 3_3-lc / 3_3-sv / 3_4：真绿，两轮全过。
- 3_5：已知过期（`-10`），两轮同错，非新回归但不能闭合。
- 3_6：真绿，两轮全过。
- 4_1：真红——32/33 PASS，仅 `-23` 把 `__pycache__` 当业务落盘（脚本期望过期）。
- 4_2：flake——r1 红（-99 中断连带 -15）/ r2 全绿，不计通过，需定位中断机制。
- 4_3 / 4_4：真红——`start_static_server` 裸名未导入，零检查执行（脚本缺陷）。
- 5_1：真红——`current_review_contract` 裸名未导入，零检查执行（脚本缺陷）。
- 5_2 / 5_3 / 5_4 / 5_5：真绿，两轮全过（5_3 的已知 `-15` 本轮 PASS）。
- 6_1：真红——静态守卫找已不存在的 `<section id="adopt-panel"`（脚本期望过期）。
- 6_2 / 6_3：真绿，两轮全过。
- 6_4：真红——`shared.fake_suite` 属性不存在（脚本缺陷）。
- r5_2：真红——`#prompt-editor` hidden 与脚本可见性假设冲突（确认过期链，需 §7.6 对应）。
- ui_2：真红——`v251` 裸名未定义（脚本缺陷）。
- ui_3：真红——`start_server` 裸名未定义（脚本缺陷）。
- packet08 三件套：真绿，两轮 12/11/16 全过（证据文件名被覆盖，以各轮日志尾行为准）。

## 8. 复核指引（给下一片，不在本片执行）

- 原始日志：`_working/p11regression/logs/`（不提交，复核时本地看）。
- 各验证器自带证据路径见§2 总表；失败中断型的"无证据文件"本身就是结论的一部分
  （中断在落盘前），对应日志已留最小 Traceback。
- 不得重跑洗绿：§4 每项的 RC 与 Traceback 是定性依据；修完后按包 11 第二片规程重跑两轮，
  本文件结论不追改。
