<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/packet09-verifier-migration-20261007T130000Z.md -->
# 1. 逐项表（文件:行号 = 改前行号；分类：删/换/保留）（续）
[返回 packet09-verifier-migration-20261007T130000Z.md](packet09-verifier-migration-20261007T130000Z.md)

附：`_gen.mjs` 的 DROPS（attempt join/batch 文案/compare join/selection 文案四行/suite-editor 常量/suite-plan 9&8）是**生成期已删的历史删除记录**，不是当前 node 文件的断言；本轮确认当前 20 个 node 文件已无 DROPS 所列残留（逐 pattern 复核），故不对 `_gen.mjs` 本体做改动（改它不改变任何当前行为，且它是历史迁移发生器）。

## 2. tools/** 为何零改动

本片允许范围是 `tools/**` + `evals/product-v2/node/**`。逐个判定后，`tools/**` 里找到的两类文本读取（#18、#19）都属于设计 §7.1 明确保留的“控制守卫 / 产物一致性类”契约守卫：删掉即丢失真实覆盖（构建闭包声明、文档-实现一致性），且没有同等行为断言可接管。按任务卡要求“看起来像源码扫描但实际是不可替代的契约守卫 → 保留并写清理由”，故 `tools/**` 本片零改动（`git diff --stat` 无 tools 项）。

## 3. 七闸门（逐条命令+退出码）

| # | 命令 | 退出码 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 0（`GATE1_OK`） |
| 2 | `npm run build:frontend` | 0（EMIT 5 个 ui/*.ts→.js，含 compare/delivery/dom/generation/input） |
| 3 | `npm run check:types` | 0（`tsc --noEmit` 无输出） |
| 4 | `npm run check:generated` | 0（CHECK 5 个 ui 文件） |
| 5 | `node --test evals/product-v2/node/*.test.mjs` | 0（227/227 pass，见 §4） |
| 6 | `uv run --locked python tools/check_project_state.py` | 0（`结果：全过`） |
| 7 | `uv run --locked python tools/check_docs.py --no-run` | 0（`结果：全过`；--no-run 未验证命令执行，仅文档一致性） |

## 4. node 用例数前后对照

| 文件 | 改前 | 改后 | 说明 |
|---|---|---|---|
| attempt-contract | 19 | 19 | A13/A18 用例内断言替换，用例数不变 |
| brief-contract | 35 | 35 | C01 用例内替换 |
| candidate-contract | 10 | 10 | C09 删 1 行文案断言 |
| compare-panel | 15 | 15 | CP-04 相对顺序替换 |
| config-export | 3 | 3 | X03 删 1 行 |
| confirm-contract | 12 | 12 | 未动 |
| delivery-gate-contract | 6 | 6 | 未动 |
| generation-isolation | 2 | 2 | 保留未动 |
| package-contract | 3 | 3 | 未动 |
| prompt-contract | 12 | 12 | G01 替换 |
| prompt-edit-contract | 12 | 12 | 未动 |
| review-contract | 12 | 12 | R13 删 1 行 |
| review-provider-contract | 8 | 8 | R14 替换（仍为 8，不钉 7） |
| rework-contract | 15 | 15 | RW-09 删 2 行中文标签断言 |
| selection-contract | 18 | 18 | SL-13/SL-16 替换 |
| specs-contract | 12 | 12 | 未动 |
| suite-dependency-scope | 2 | 2 | 第一用例追加对偶断言（用例数不变，断言增强） |
| suite-editor-contract | 12 | 12 | 未动（残留已在生成期删） |
| suite-plan-contract | 13 | 13 | R01/R02 替换 |
| suite-review-contract | 6 | 6 | 未动 |
| **合计** | **227 / pass 227 / fail 0** | **227 / pass 227 / fail 0** | 少了 0 个用例；少了 15 组词表/文案/计数钉死断言行，新增/替换 10 组行为断言行；行为覆盖无丢失（每删必有接管，见 §1“接管”列：A01/A07/A14/A15、C02、G02、自检、R01/R10、SL-03/05/06） |

## 5. 未做项

1. `tools/**` 零改动（理由见 §2）：verify_* 的 tar/Dockerfile/页面文本守卫与 check_* 控制守卫保留。
2. `_gen.mjs` 本体未改：DROPS 是历史生成记录，当前 node 文件无残留；改它无行为变化。
3. 未删除任何整用例：包09 设计要求“没有行为内容就不补新永久测试”，本片只删/换用例内断言行。
4. 未跑浏览器验证器：本片改动全在 Node 原生 domain 断言层，无页面/IDB/HTTP 行为变更；`node --test` 即对应验证。
