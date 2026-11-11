<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/audit-current-state-20261007.md -->
# 既有工作审计、当前状态与后续规划建议
[返回 audit-current-state-20261007.md](audit-current-state-20261007.md)

# 既有工作审计、当前状态与后续规划建议

> NOT-AUTHORITY：2026-10-07 仓库/运行时审计与规划建议。不是施工启动、正式进度表、系统 Goal 读数或工程完成声明。正式任务/验收仍取 `docs/product-v2-refactor-plan.md`，当前进度仍取 `_working/amz-listing-kit-product-v2/state.md`。本轮不改产品、计划、state，不创建/修改 Goal，不调用真实模型，不提交/推送/开 PR/合并/部署。

## 1. 结论

项目已从半迁移、项目打开异常推进到可运行的业务 owner 与四视图实现；不能再按旧记忆的 main、63 个未提交文件或 `suiteReports is not defined` 恢复。**当前处于 R5.1 / 包11未闭合，不是待重新设计/从头开发，也不是可发布成品。**主要问题是产品变化后的验证消费者未同步、若干绿灯不具备所宣称的证明力、启动间歇仍未闭合，以及最终 CI/容器/发布证据缺失。

本轮当前实跑只证明启动/新建/草稿保存/刷新恢复与静态产物一致，不能证明完整生成交付、间歇根治或真实模型质量。运行观察见 [checks](audit-current-state-20261007-checks.json)，页面截图见 [workbench](audit-current-state-20261007-workbench.png)。

## 2. 当前状态（本次观察）

| 项目 | 实际结果 | 解释 |
|---|---|---|
| 分支 / HEAD | `feat/v2-r51-packet-05` / `e7ce5c5` | 最新提交为批次取回提示与 4_4 重写，提交信息明确未验证 |
| 审计前工作区 | 只有 tracked `state.md` 修改：新增一行收尾说明 | 不再有旧记忆中63个未提交文件；这一行是用户既有变更，保留 |
| 持久进度 | Phase 0–4 done，Phase 5 active，Phase 6–7 pending；next=`V2.R5.1` | R5.2/R5.3/R6.1–3/R7.1/R7.4/R7.5仍 pending；R6.4 done；R7.2/R7.3为本轮外部门，不应冒充完成 |
| 冷恢复 | exit 0，8阶段/27任务，输出 R5.1 active | Goal正文 sha256=`6677a6803003f0894dd522bdd7102b53ca30c866532ff48fdc79e4b148d7c495`；脚本不查询系统 Goal |
| 类型 / 产物一致性 | `check:types`、`check:generated` 均 exit 0，15个TS源纳入产物检查 | 比旧时点9个产物的记录更新；不等于全产品验收 |
| 正式入口 | `uv run --locked python app/server.py --check` exit 0，45/45 | 真实本地HTTP、注入fake上游；不证明真实供应商或UI全链 |
| 页面 smoke | 新建→工作台→保存商品草稿→刷新，值恢复；IDB有1项目、1条product_input v1、0资产 | Chrome无头、隔离origin；118请求均本地GET，无失败HTTP及page error；无模型动作 |
| PR / CI | `gh pr status`无当前分支PR；当前分支`gh run list`返回`[]` | workflow仅PR-to-main、main push和手动触发，功能分支push不是CI验收 |
| 本轮发布 / 线上版本 | 没有本轮发布证据；没有观察线上实际运行版本 | 旧发布和旧完成矩阵不能说明这一HEAD已上线 |
| 系统 Goal | 本会话未观察：当前工具清单没有Goal接口 | state的active与绑定ID只属持久历史观察，不声明系统当前active/paused/completed |

页面审计中曾等待错误的 `#product-name` 选择器而超时；观察后确认真实工作台已打开，随后保存/刷新/IDB操作通过。此为审计选择器错误，不作为产品失败；已写入checks边界。

预算取当前账本：生图8/8已满，semantic/VLM合计5/6，总13/14；已记支出1.15元，保守累计占用含未结算1.61元，上限5元。**不是理解和复核各余一次，而是合计最多余一次；金额余额不能解除次数门。**本轮审计不使用剩余额度。

## 3. 之前工作哪些可以保留

1. 输入、Prompt、生成、采用、交付已有各自业务 owner；工作台通过 `project-inputs/prompts/generation/selection-adoption/review-delivery` 和四视图装配，当前代码见 `app/product_v2/workspace.js:26-34`。这是实际实现，不只是目标设计。文件变小不单独作为职责正确的证明。
2. 默认进入生成会自动本地准备系统Prompt，一次摘要确认提交，不再要求用户逐图编译再找批次按钮。人工文本、原动作身份、Unknown不自动重提仍为必须保留的合同，见计划 `:436-441,866-879`。
3. 按需AI复核已实现；不运行不折叠为Unknown，不自动阻断人工采用。单图原动作版本匹配、facts传输形状、采用后重绘已有修复与离线证据，见 `packet08-adoption-ai-20261007T130000Z.md:10-65,75-88`。
4. 未复核可导出、逐图与整套AI状态分开、真实Unknown需知悉、候选字节缺失仍被硬门拦已有fake页面/ZIP证据，见 `packet08-delivery-manifest-20261007.md:8-34`。这些证据证明交付语义，不证明真图忠实度或真人易用性。
5. 4_3最新独立验证确已通过：`v2.4.3-batch-suite-20261007-202416-diag4.json` status=passed，无failed checks。`0d681a5`修了停止状态持续可见与验证替身场景登记；不能继续引用更早收尾段说4_3尚未复跑。
6. 发布事务脚本已保留previous直到finalize必要重验成功；rollback/exit1/exit3/exit4的当前静态门一致。`--offline-rollback`实际跑了事务脚本，但docker/curl为stage替身，不能称真实Docker回退。边界见 `packet10-release-rollback-20261007T173500.md:20,91-104`；真实selftest已接CI，尚无当前运行结果。
7. 旧生图/图文live证据不因时间旧或前端移文件自动作废。按计划 `:930-934` 对上游能力、协议、输入、路径和运行前提逐项映射：未变部分复用，变更消费者以当前离线行为补齐；确有受影响真实能力缺口才保持未证并申请必要专项授权，不重复付费洗绿。

## 4. 审计发现与风险

### 4.1 验收可靠性（硬发现）

**P1：packet08设置验证存在空证和固定成功。**

- `tools/verify_v2_packet08_settings_vision.py:47,148-154,250-254`：PROBE_KEY只定义并用于事后扫描，没有实际填入设置或随业务动作发送；设置仅打开后Escape。因此P08-02不能证明BYOK秘密隔离。响应只截前4000字符、IDB只截前6000字符（`:228-245`），也没有实际下载ZIP检查。合法请求级key本来应出现在指定出站头，不能把“请求头没有key”当成功接线与秘密安全。
- `:173-188`：所谓无key用例的参考图只给role/media_type/sha256，没有data_base64；报VISION_BYTES_REQUIRED只能证明缺图片字节被拒，不证明缺凭据被拒。
- `:258-268`：P08-04a直接return `"probe-ok"`，再比较这一常量，没有构造或导入旧ZIP。此绿灯不能证明旧格式拒绝。

以上是证明缺陷，不直接等于产品泄密/接受旧包；必须修正已有入口的真实前置与后置，不能沿用12/12概括这些要求已经成立。

**P1：比较导航的期望来自被测按钮本身。**`tools/verify_v2_5_3_compare_panel.py:459-480`读取dataset.targetShot，再断言跳到它，只能证明按钮执行其声明，不证明正确选中下一待处理图。应以明确夹具中独立确定的下一目标验证循环顺序/问题优先/无待处理边界，不能把同一函数结果或UI投影互相回声当业务证明。

**P2：发布truth-table自检不能证明其名称宣称的布尔语义。**`.github/workflows/ci-cd.yml:409-420`主要检查条件字符串含token；`:418`搜索整个workflow，其中自身Python断言已包含 `recoverable=true.*GITHUB_OUTPUT`，会自匹配，不能证明只有exit1才设置true。且检查位于finalize之后，仅main push运行（`:390-393`），不是PR发布前门。当前真正rollback条件`:441`静态正确；需要替换/删除脆弱自证检查并由已有失败场景证明exit1回退、exit4人工处理，不扩大为新门禁平台。

**P2：selftest页面目标与容器目标不同。**`tools/release_transaction_probe.py:450-456,537-550`确有不同Docker image ID与实际服务marker/回退断言；但`:569-580`的ST-LIVE页面链另起 `v2_test_server`，不是被测容器origin。它可证明页面验收助手正例，不能证明该镜像工作台可保存/重开。真实容器页面与HTTPS发布页面仍须独立实证；不可把本地替身页面算成容器主链。

