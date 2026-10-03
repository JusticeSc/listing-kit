# R3.2 verification-seams · NOT-AUTHORITY（时点证据/实现记录）

> CONTROL-STATUS: supporting · AUTHORITY: point-in-time-implementation
> 本文件只记录 R3.2 的实现形状与时点证据指针；目标与完成判据在 `docs/product-v2-refactor-plan.md` §V2.R3.2，
> 进度权威在 `_working/amz-listing-kit-product-v2/state.md`。命令证据正文见引用文件，不复抄。

## 输入与动作

按任务卡把验证切成三层，全部在当前断点上而不是重写历史证据：

- 纯行为领域断言 → Node 原生直跑：`evals/product-v2/node/*.test.mjs`（发生器
  `evals/product-v2/node/_gen.mjs`，`npm run test:domain`），223/223。
- 宿主特有行为（真 IDB / 真 WebCrypto / DOM 消费者轨迹）→ 保留浏览器版
  `evals/product-v2/harness/`：brief 只留 C36/C37，package 只留 Z04..Z09（Z01..Z03 纯 ZIP
  往返进 Node），review 只留 R11；其余 15 个纯领域套件的浏览器副本只剥源文本/文案钉死断言，
  用例条数不动，已有 `verify_v2_*` 驱动继续全绿。
- 分类登记：`config/product-v2/verification.json`（`npm:test:domain` category=domain ci=true；
  三个混合验证器仍 `verify_v2_*` 浏览器入口）；CI 接线见 `.github/workflows/ci-cd.yml` 的
  npm trio（check:versions / check:types / test:domain）+ 浏览器契约段。
- 网关装配捕获：`evals/probes/verification_policy.py` 14 组反例全部按标签拒绝，
  `tools/check_verification.py` 42 入口 / 38 CI 模式全过。
- 发生器自愈：混合套件源取 `git HEAD` pristine（`pristineHarness`），可重复运行；
  纯套件 Node 输出与浏览器同一批断言（A13 词表拷贝等 17 处已删，行为检查保留）。

## 输出证据（2026-10-02 时点）

- Node：`npm run test:domain` → tests 223 / pass 223 / fail 0（当前时间戳运行）。
- 浏览器 brief：`evals/product-v2/v2.2.1-product-contracts-20261002-144142.txt`
  （V2.2.1-00..05 全过，用例 2 条：C36/C37）。
- 浏览器 package：`evals/product-v2/v2.1.3-project-package-20261002-144152.txt`
  （V2.1.3-00..07 全过，用例 6 条：Z04..Z09 + 界面导出/导入/回滚）。
- 浏览器 review：`evals/product-v2/v2.5.1-deterministic-review-20261002-144206-r32-seams.txt`（+.json/+.png）
  （V2.5.1-00..06 全过；R11 宿主案例 + 回归套件 + 工作台走查）。
- 分类反例：`uv run --locked python evals/probes/verification_policy.py` → VPC01..VPC14 全按标签拒绝；
  `uv run --locked python tools/check_verification.py` → 全过。
- 锁与类型：`npm run check:versions`（Node 24.19.0 / npm 11.17.0 / TS 6.0.3）、
  `npm run check:types`（jsconfig 渐进范围零诊断）同轮全过。

## 验收对照（任务卡原文，不改写）

- 改变业务边界可判红：失效图抽样边界（C28 重写：逐类匹配 + briefUsesSlot/shotIds 定向范围）、
  行投影/摘要关键计数保留；反向探针仍在浏览器侧真实执行（C37、Z05/Z06/Z08、R11）。
- 分类漏项能判红：verification_policy 14 组覆盖缺登记/缺 CI/受限接线/重复/人审误分类/幽灵条目，
  全部真实拒绝对应标签。
- host 特有行为仍真实覆盖：C36 真 IDB 落库链、Z04..Z09 真导入事务、R11 真 WebCrypto 复算，
  均在 Chromium headless 真跑。
- 不以减少测试总数冒充效率改善：浏览器纯套件用例条数不变（只删钉死断言），纯行为在 Node
  全量同批断言；总数不减，重复跑分层。

## 未闭合与风险

- 纯浏览器副本仍与 Node 同批断言并行跑（有意的消费者轨迹双覆盖，非静默重复）。
- 本文件不证明语义正确，只证明分层接线与时点通过；业务语义仍按 R3.3..R7.x 任务卡推进。
