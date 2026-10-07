# V2.R1.2 故障承接与可回退基线 · 20261001-095710Z

NOT-AUTHORITY: point-in-time evidence; not a plan, current state, or product completion

## 本卡回答什么

R1.2卡要求：记录两处已修UI问题与后续boot失败的时间/条件/证明范围；核查已有轨迹缺口和readiness窗口；设计可控延迟/失败注入，不为确认失败而重复运行；保存旧包和含历史候选代表项目并核对hash与版本。调查完成不等于缺陷修复，发布被阻断语义保留给R3.3/G3。

## 1. 用户报告的持久记录（不重跑证实）

- 报告原文（计划§1.3逐字）：“provider能力投影刷新修复、critical槽位排序修复及断言补全已做；后续V2.7.1被 `verify_v2_1_2_project_home.py` 间歇失败阻塞，带时间线失败样本未取得。”
- 两处“已修”在脏工作树中可直接核对（本轮未提交，仅做基线记录）：
  1. 能力投影刷新：`app/product_v2/workspace.js` `loadWorkspace`尾部把`renderAnalyze()`改为`renderAll()`（worktree diff，注释写明capabilities是渲染输入、初次打开会留陈旧文案）。对应R1.2未知项外，R3.3/R5路径的消费者判据待闭合。
  2. critical排序：同文件新增`reviewRankOf`（未收尾critical排2，conflict/unknown保持0/1，missing及之后后移），`data-critical`打到`.slot-row`，`tools/verify_v2_2_3_intake_understanding.py`同步`review_rank`+`critical_first`判据（worktree diff全文已读）。
- 历史提交中未找到与这两处对应的已提交commit（`git log -S critical/投影/capabilities`仅命中旧功能提交），故“已做”当前仅存在于未提交工作树；回退基线必须同时覆盖已提交HEAD与该脏差，这是本报告§4的hash做法。

## 2. V2.7.1 boot失败：时间/条件/证明范围（git内证据，不重跑）

- 失败样本：`9dc6559:evals/product-v2/v2.7.1-regression-20261001-061430-final.{txt,json}`（两文件均已提交入库，可`git show`复现）。
  - 时间：2026-10-01 06:14:30Z回归；第1轮`verify_v2_1_2_project_home` rc=1耗时7.7s，第2轮同命令rc=0耗时7.0s；`verify_v2_4_1_image_gateway`第1轮106.3s vs 第2轮23.0s（满载负载差异的旁证）。
  - 失败点：`verify_v2_1_2_project_home.py:208`旧判据`expect(#project-view).to_be_visible(timeout=5000)`；aria快照停在首页（banner+空项目表单+空列表），`#project-view`保持`hidden`。
  - 条件：满载机器首轮；该版本尚无boot轨迹探针，失败输出只有playwright断言+aria快照，无法区分“模块没加载 / 卡在probe或openStorage / refresh完成但showProject没跑”。带时间线失败样本=未取得（与用户报告一致）。
- 已有处置（`9dc6559`，未闭合根因）：
  - 判据改为先等`#create-project`解锁30s再断言`#project-view`15s（当前worktree `verify_v2_1_2_project_home.py:281-282`仍是该形状）；
  - 全绿基线：`ec9ac01:evals/product-v2/v2.7.1-regression-20261001-0633-final.txt` 32命令×2轮全绿、指纹`cdb92954c5d4ec42`两轮一致（已提交，可复现）。
- 本轮新增但未提交的诊断能力（worktree diff已读，不算已验证修复）：`BOOT_TRAIL_SCRIPT`（init script起MutationObserver记`disabled`/`hidden`+error/reject）、`BOOT_STAGE_SNAPSHOT`（trail/readyState/控件属性/行数/资源耗时）、失败落盘diagnostics。判读规则写进证据本身。
- Scout只读结论（`agent://YearningSilverfish`转录，未执行）：ready语义三轨并存（DOM解锁/视图可见/无显式ready标志）；`probeBrowserCapabilities`先开库+探针事务再`openStorage`二次开库；`onblocked`空实现（旧版本连接持有时永久停在controls disabled）；`workspace.close()`未await可踩新项目；无BroadcastChannel/storage事件；`boot()`无重入保护。旧计划`product-v2-goal-and-implementation-plan.md:1379`“boot()完成才解锁”的前提与当前代码不符，R1.2把它标为待纠正，不沿用。
- Root cause：保持未知。绿样本（0633双轮一致）只证明结果重复，不证明flake根治；后续用户报告的间歇失败仍开放。发布阻断语义：确认有缺陷时发布被阻断；R3.3必须闭合readiness修复及消费者轨迹后才能G3（本卡只承接，不闭合）。

## 3. 已有轨迹缺口与readiness窗口核对

| 缺口 | 现状 | 后续判据归属 |
|---|---|---|
| 失败时无boot时间线 | 061430样本无trail；worktree新增trail但未提交未验证 | R3.3：受控延迟下trail必须能区分boot未跑/卡住/视图没切 |
| ready定义错位 | 解锁（create-project enabled）发生在openStorage后、refresh/showProject前；旧断言把它当boot完成 | R3.3：冻结显式ready语义，旧前提纠正 |
| onblocked永久停 | `db.js` onblocked空实现 | R3.3：旧连接持有版本的可见失败+恢复动作 |
| close/open竞态 | close未await、无generation检查 | R3.3：打开A/B/关闭/慢响应后置条件 |
| 双标签静默追加 | 无广播、多数save不传expectedVersion | R3.3：陈旧编辑可见冲突 |
| boot重入 | 重试按钮`void boot()`可并发 | R3.3：重入保护或串行化证据 |

## 4. 可回退基线（hash，含脏工作树）

记录时刻：2026-10-01T09:57:10Z。HEAD=`ed363d3`；以下sha256为当时工作树字节（含未提交修改），恢复时以`git stash`/`git diff`+本表核对，不依赖记忆。

| 路径 | sha256（工作树） | 说明 |
|---|---|---|
| `app/product_v2/workspace.js` | `9101172bb106c00a1c7f9829e1b294a3168d73559a438467c8f5d8e52298aa0c` | 含两处未提交UI修复 |
| `app/product_v2/storage/package.js` | `b0722141752080608abf1c69e1626a5fde0b2d020b2036d83fc68b4a658b8915` | 包格式2解析/校验 |
| `app/product_v2/storage/package-migrations.js` | `073d069e1a2c4348e6f45c63eb4a2085dd23b2b4a8115accb5ed9c6b9a46916a` | 格式1→2+记录级迁移 |
| `app/product_v2/storage/transfer.js` | `02b6cbdd4d6ca095b9c74bbdd1921f1892202adcddd6156b8c580cc98f40fe29` | 跨浏览器导入 |
| `app/product_v2/storage/repository.js` | `c18f3095d6647f64d07474769e46f615e7fd0441118c9fd0799b0584119f5656` | 唯一读写入口（482行现状） |
| `app/product_v2/storage/db.js` | `e9499bcbc93fc3485ef73940ca8ab7e740918336d50a3253a5942c3c873c4fce` | onblocked空实现现状 |
| `tools/verify_v2_1_2_project_home.py` | `01e04faf938f3bc92fc349f70f77c3a9a2012aa597ed9f96a310aaac36dc1a39` | 含trail/diagnostics未提交部分 |
| `tools/verify_v2_2_3_intake_understanding.py` | `b9af31e1cbf5c1dbf0e4f6eae229d7d687527871f5763019897032f7e34dbba4` | 含review_rank未提交部分 |
| `tools/verify_v2_1_3_project_package.py` | `22005e1da132176d33d744cdf97d6de2b50b78d78ca05befdd200420ad2cb5bb` | 包往返判据（已提交态） |

脏文件清单（`git status`当时）：14个M（AGENTS/README/state/v273任务书/workspace/INDEX/旧plan/context/UI合同/两探针/状态守卫/两验证器）+5个未跟踪（`_stage-amz-control/goal-resume-20261001-142140/`、baseline state、`docs/product-v2-refactor-plan.md`、`evals/product-v2/refactor/`、`tools/refactor_resume.py`）。回退=`git stash -u`保留本报告，或按上表逐文件`git diff`核对后`git checkout --`。

旧包/代表项目基线：
- 迁移链现状：`PACKAGE_FORMAT_VERSION=2`，`MIN_SUPPORTED=1`（`package.js:35-37`）；`PACKAGE_MIGRATIONS`逐级+1、缺中间步骤拒绝（`package-migrations.js:91-126`）；记录级只丢弃旧合同结论并重建（`RECORD_MIGRATIONS`，`MIGRATION_CONTRACT_VERSION=v2.6.3`，review合同镜像`v2.5.2`）。
- 跨浏览器闭环证据（已提交）：`78983aa`（格式2+迁移链+P01–P07契约与双浏览器往返，修启动期导入崩溃/schema镜像漂移/版本未改写）；harness `evals/product-v2/harness/project-package-contract.js/html`、`package-contract.js/html`；`tools/verify_v2_6_3_project_transfer.py`。
- 本轮未生成新ZIP（无ZIP fixture在库；`*.zip`全库无命中）。旧包hash基线以git内已提交证据为准，不伪造新包hash；R4.4/R6.3做ZIP往返hash对照时以`verify_v2_1_3`/`verify_v2_6_3`实时产物为准。

## 5. 可控延迟/失败注入设计（未执行，只设计）

沿用scout指出的现成测试缝（均只读核对，未运行）：
- `tools/v2_test_server.py`：复用正式handler+`/harness/*`+fake-semantic；`provider_factory`可替换、`_resolve_static`可包装加延迟——首选故障注入点。
- `context.add_init_script(BOOT_TRAIL_SCRIPT)`：worktree已有，R3.3可直接复用为延迟探针载体。
- `page.route`延迟静态资源/接口、`launch_persistent_context`保双浏览器隔离、`server.provider_factory`换fake错误分类。
- 调查判据（R3.3执行时必须满足，否则不闭合）：延迟Xms下trail仍能定位最早失效层；旧回调不写新项目；双标签陈旧编辑可见冲突；绿样本≥2轮且trail一致才算通过，不以单轮绿闭合。

## 6. 验收对照

- 基线可恢复：HEAD+脏差hash+git内失败/全绿样本均可`git show`复现；回退路径明确。proven（记录层）。
- 缺陷发布阻断：root cause未知已明示，R3.3/G3门保持。proven（语义层）。
- 调查≠修复：本卡只承接+设计判据，未改产品代码、未跑浏览器、未调模型。proven（边界层）。
- 不开始C15：无。proven。
