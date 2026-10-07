# 包09第一片：验证器/测试迁移——源码扫描式与 mock 回声式断言

- 时间：2026-10-07（文件名时间戳为准）
- 范围：只碰 `evals/product-v2/node/**`（12 个 `.test.mjs`）；`tools/**` 无改动（逐个判定后全部保留，理由见表 §2）。
- 基线 → 改后：`node --test evals/product-v2/node/*.test.mjs` 均为 **227 tests / 227 pass / 0 fail**（用例数不变：删的是用例内断言行，不是整用例；§4 对照）。

## 1. 逐项表（文件:行号 = 改前行号；分类：删/换/保留）

| # | 文件:行号 | 断言原文（要点） | 能抓到什么 bug | 分类 | 处理 | 理由 / 新断言实跑 |
|---|---|---|---|---|---|---|
| 1 | attempt-contract.test.mjs:403-407 | `for state of Object.keys(ATTEMPT_STATES): attemptStateLabel 非空` | 几乎抓不到：label 缺失只影响展示词，且 `isAttemptState` 已在 `checkAttemptRecord`（A01/A12）覆盖非法状态拒绝 | 换 | 替换为 `attemptStateLabel("no_such_state")==="未知状态"`（非法输入兜底不抛错——UI 渲染路径的真实行为）；实跑 A13 ✔ |
| 2 | attempt-contract.test.mjs:415 (`order[0]==="pending_submit"`) | 首键必须是 pending_submit | 无：JS 对象键序与提交前落库行为无关；A01 已断言新建 state | 删 | 删除；A01/A07 行为覆盖保留 |
| 3 | attempt-contract.test.mjs:541-551 (A18 头 7 行) | `ATTEMPT_RECONCILE_MODES.blocked_environment==="blocked_environment"`；`ATTEMPT_CREDENTIAL_SOURCES.join()===…`；`ATTEMPT_PROTOCOL_PATTERN.test(…)` 两行 | 抓不到行为 bug：常量自比（实现改名后测试与实现同改即绿）；真正的漂移阻断由 A15（5 向漂移表）覆盖 | 换 | 头 7 行换成 `attemptReconcileMode({终态})==="none"`（终态不需核对的真实模式分支）；协议/来源非法输入仍由 A14（`operator_giveaway` 拒）覆盖；实跑 A18 ✔ |
| 4 | brief-contract.test.mjs:108-113 (C01) | `CORE_SLOT_IDS.length===CORE_SLOT_REGISTRY.length`；`DOMAIN_DOCUMENT_KINDS.fact_slot==="fact_slot"` | 抓不到：派生常量自一致；跨层 key 一致性是 TS 类型职责 | 换 | C01 改为越权行为断言（未登记 `model_invented_core` 自称 core_fixed 被拒）+ 保留冻结断言；`DOMAIN_DOCUMENT_KINDS` import 删除；实跑 C01 ✔ |
| 5 | candidate-contract.test.mjs:214-215 (C09 尾) | `batchProgressText(partial).includes("待保存候选 1")` | 抓不到行为：文案拷贝；计数/队列/下一步三 davran 已在同用例前 6 个断言覆盖 | 删 | 删除该 1 行；其余 C09 不动；实跑 C09 ✔ |
| 6 | compare-panel.test.mjs:133-140 (CP-04) | `compareSeverityRank===0/3/length` 四行逐值钉死 | 半拷贝：数值秩是内部表示；顺序语义（BLOCK 最先、UNKNOWN 先于 PASS、PASS≈无发现）才是行为 | 换 | 改为相对顺序断言（`<` / `===` 比较，不钉具体数字）；`REVIEW_SEVERITY_ORDER` 仍被使用（运算语义），import 保留；实跑 CP-04 ✔ |
| 7 | config-export.test.mjs:148-149 (X03 尾) | `CONFIG_CREDENTIAL_SOURCES===["byok","default","test_double"]` | 抓不到：词表自比；非法来源拒绝已由 `checkShareableConfig` 对 credentials.sources 的校验覆盖（X03 前半） | 删 | 删除该 1 行；实跑 X03 ✔ |
| 8 | prompt-contract.test.mjs:179-181 (G01) | `compiled.text.includes("纯白无缝背景「RGB…」")` 等三行逐字包含 | 拷贝实现常量（`domain/prompt.js:54,657,772` 同文）；平台规则缺失的真实回归由 `checkCompiledPrompt` 自检 + G02 来源可解析覆盖 | 换 | 换成 `checkCompiledPrompt(compiled).length===0` + `sections 有 platform_rules 段`（结构存在性，非逐字）；实跑 G01 ✔ |
| 9 | review-contract.test.mjs:413 (R13 尾) | `REVIEW_SEVERITIES.length===5` | 计数钉死：增删严重度即红，但合法演进；R01 已用必需规则集 + 注册表零问题覆盖纪律 | 删 | 删除该 1 行，import 同删；实跑 R13 ✔ |
| 10 | review-provider-contract.test.mjs:111 (R14) | `checks.length===7` | 计数钉死：新增 check（合法演进）即红 | 换 | 换成 `checks.length>0` + 逐条映射纪律保留（新增 check 自动纳入）；实跑 R14 ✔（当前 7） |
| 11 | rework-contract.test.mjs:385/388 (RW-09) | `summary含"商品失真"/"文字"`；`reworkProblemLabel("scene")==="场景"` | 中文标签拷贝；标签缺失的真实影响（摘要是否带问题信息）由方向/采纳否定断言覆盖；未知 id 行为保留 | 删/换 | 删 2 行中文标签断言，保留 `mystery` 原样返回（未知输入不发明标签的真实行为）；标题同步；实跑 RW-09 ✔ |
| 12 | selection-contract.test.mjs:331/334 (SL-13) | `new Set(4文案).size===4`；`selectionSetText含"0/1"` | 四文案互异是展示措辞，改一句文案即红；过期可感知的真实行为是同记录切 stale 投影摘要变化 | 换 | 换成 `current!==stale`（同记录切投影）+ 保留进度断言；实跑 SL-13 ✔ |
| 13 | selection-contract.test.mjs:378-384 (SL-16) | `SELECTION_ACTIONS长度/成员`；`SELECTION_STATES每态有文案`；`文案表无多余键` | 词表自比三连；动作非法输入拒绝由 SL-03/SL-05 覆盖；状态兜底是真实渲染行为 | 换 | SL-16 缩为 `selectionStateLabel("mystery")==="未知状态"`（兜底行为）；SL-06 保留 `SELECTION_STATE_TEXT.stale` 同表引用（跨模块一致性，非自比）；实跑 SL-16 ✔ |
| 14 | suite-plan-contract.test.mjs:109/114-116 (R01/R02) | `DEPENDENCY_KINDS.length===6`；`REFERENCE_ROLES===json([...6项])` | 计数/全量拷贝钉死；谓词增删、角色增删的合法演进即红；真实纪律由 `validateSuiteRegistry` 零问题 + R10 反向探针（每条守卫变红）覆盖 | 换 | R01 删计数行（保留 `dependency_kinds` 与常量一致 + schema_version）；R02 删全量 json 比对，改为逐模板角色∈词表 + competitor 被依赖（新增角色自动纳入）；实跑 R01/R02 ✔ |
| 15 | suite-dependency-scope.test.mjs:21-25 | 两个用例各断言单一 severity（PASS/BLOCK），无行为对偶 | 弱断言：只回声 fixture 自身返回值，未证明“可选未选不挡、被选即挡”的条件翻转 | 换 | 第一用例内追加对偶断言（同规则 `candidate-size` 落盘即 BLOCK）：PASS→BLOCK 翻转在同一测试内成立；实跑 2/2 ✔ |
| 16 | suite-editor-contract.test.mjs | `MIN_SHOTS===1 && SUITE_PLAN_SCHEMA_VERSION===1`（_gen DROPS 已删，当前文件无此行） | — | 保留（无需动） | _gen.mjs DROPS 已在生成期删除，当前 node 文件已无该断言；确认无残留 |
| 17 | generation-isolation.test.mjs | `globalThis.fetch` 桩 + `requests.filter…task_id`；`saved.filter(project-B).length===0` | **不是 mock 回声**：fetch 桩是副作用计数器（HTTP 外发次数/身份），断言的是“旧项目回调不写新项目记录、不发错 task”的可观察行为（设计 §7.2 反例：A→B→A 返回） | 保留 | 在报告写清为何不可替代（替换会丢失跨项目污染判据）；未改动 |
| 18 | `tools/**`（verify_v2_*.py 等）源码扫描嫌疑 | `verify_v2_2_3` 读 workflow/Dockerfile 文本（19/20：tar 列表含 src/config、Dockerfile 含 COPY/CMD）；其余 verify_* 读页面文本/IDB/HTTP | **契约守卫，不可替代**：19/20 验证的是“发布闭包真实包含运行时依赖”（设计 §10.8 生产闭包；文字检查 Dockerfile/tar 不足证闭包——但本项恰是其守卫下限：连声明都没有则必错；真实包含性另由 release probe 的两 image 构建证）。页面文本断言（"还缺"/"相同"/"不会自动重试"）是用户可见门禁文案在真实 Chromium DOM 中的存在性，非源码 grep | 保留 | 不改 `tools/**`；本片 tools 零改动。若后片要迁，需先有真实 tar/镜像构建证据承接，不可直删 |
| 19 | `tools/check_docs.py` 等控制守卫的源码/文档文本扫描 | README/TOOLS/INDEX 一致性、goal 围栏解析 | 控制守卫（设计 §7.1“控制守卫：既有受测 root 反向探针”；§11.2 包09 明确“隔离反向 root”保留） | 保留 | 不碰 |

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
