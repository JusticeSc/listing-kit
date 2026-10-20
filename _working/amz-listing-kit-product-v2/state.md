# Product V2 定向重构执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state
> 只保存产品门、权限、进度、证据、阻塞/未知与恢复动作；产品终点/正式任务依赖在计划，具体问题在GitHub Issue，工作流在AGENTS，不扩成第二套工单明细表。
> prepared 是未绑定新 Goal 的本地准备态,不是系统 paused。旧读数与完成记录只见 superseded 基线。
## 当前恢复边界

- **2026-10-20 用户「即刻停止当前工作，做好收尾准备」——已停工。** 停工时点：PR#21 复核修复已推送（`f5e1e17`）但**未合并**、已转回 Draft；用户先前选定的「先花额度刷新两张 stale 图」**未执行：0 次真实调用、0 元新增**（账本仍 4/12 图、0/4 辅助、0.56/5 元）；收工时 `f5e1e17` 的 CI 运行 `39352437953` 仍 `in_progress`；收尾提交 `4321ed0` 又触发一次新运行。两者的结论都没有被观察，**都不得当作通过**。清理已核对：两个后台任务取消、`5516` 无 LISTENING、无遗留记录 host/Chrome、5 个临时 profile 删除。两张图在真实项目里仍是 `stale`（缺 #9 印字决定 → Prompt 不能编译），批次18五图/两包不成立。恢复需用户明确 resume；恢复点与最短路径见 `_stage-amz-control/b18-optional-figures-20261020/closeout-stop-20261020.md`。
- **2026-10-20 第16批键盘闭环＋缩放仅得「等价视口」证据（原生 zoom 仍未验）、第17批冻结两轮回归全绿（均零收费；批次18仍不完整）。** ①`tools/rehearse_v273_walkthrough.py` 新增缩放/键盘段：CDP `Emulation.setDeviceMetricsOverride`（1.25×→CSS 1152×720、2×→720×450，`devicePixelRatio` 逐阶段复核）＋`Page.captureScreenshot`（`page.screenshot()` 会按 context viewport 重置 emulation，实测把布局打回 1440，故缩放截图改走 CDP），物理宽仍 1440。**这只证明「缩放等价视口」而不是 Chrome 原生 zoom（CDP 无原生 zoom 入口），合同要求的「实际浏览器缩放」仍算未验，不据此关闭该验收项。**四段 `scroll==client`；每段关键操作（`#analyze-run`/`#suite-seed`/`#stage-next-make`/`#confirm-action`/`#deliver-export`/`#suite-review-run`）滚入视口后中心点命中自己；交付门禁四行 `data-selection-state=current` 且行宽不被裁掉；200% 下从文档头 Tab 10 步到 `#deliver-export`（每步可见/有轮廓/在视口内/命中自己），Enter 导出包与鼠标导出**逐图身份（文件名/sha/字节）相同**，两个包各自都必须覆盖门禁已采用集合。实跑 `evals/product-v2/v273-rehearsal-20261020-091407.{json,md}`（29 张截图、报告含完整 probe JSON、0 console/page/http 错误）。②Codex 复核在 PR#21 提 4×P1＋1×P2，全部已改：原生 zoom 口径（改为如实标注未验）、中途 Tab 停靠点被遮挡只查末步→逐步查 `in_view`/`hit_self`、两个包只互相比→各自对照门禁已采用集合、报告把 probe JSON 截断→完整输出、缩放段只量宽度→每段关键操作可见且可命中。③第17批冻结门：`verify_v2_7_1_regression.py --rounds 2 --stamp 20261020-v271-frozen-6e692a4c` 在 main `6e692a4c`（tracked clean）实跑 **2 轮×50 条命令全 rc=0、两轮指纹一致 `290ee1bddc2b3a6b`**，证据 `evals/product-v2/v2.7.1-regression-20261020-v271-frozen-6e692a4c-final.{json,txt}`（只改 tools/，产品源码身份不变）。④仍未闭合：原生浏览器 zoom 验收；同商品五用途中**卖点信息图/细节图**为 `stale` 采用（用户已选先花额度刷新这两张；本轮停在收尾，未执行）；批次18线上真实五图/两包与不同旧 image 同源恢复。额度 4/12 图、0/4 辅助、0.56/5 元。
- **2026-10-19 第18批晋升（受保护合并＋既有 HTTPS 发布）完成，但批次本身未验收。** PR #19 以 merge commit `689c6b08b8ebb937eb4af457b912d4d874ecd6ab` 合并，并沿既有可信 HTTPS 事务发布到 finalize，未触发回滚。**计划第18批的后置条件（线上真实五图/两包/独立导入刷新、不同旧 image＋对应旧包的同 origin 恢复）本轮零付费未执行，B1–B7 亦未验收——晋升不等于批次验收，不得据此关闭第18批或 B7。** head `9bd2b9d1e7663039a37189b6e16caff0cc400af6` 的 PR CI run `39275366557` 三作业 success，两项 required 上下文在该 head 均 SUCCESS；合并时保护为 `enforce_admins=true`、require-PR、`strict=true`，未绕过。main push run `39277855632`：`verify` 按设计 skip，容器作业 success——建镜像、容器冒烟、事务自测、失败类、远程部署、静态资源/页面主链验收、清理前指纹核对、finalize 全 success，回滚 skip。发布身份：`commit=689c6b08…`、镜像 `sha256:cb3857eb813046216036c64a2622c26cab5d31e2eafeacbc99aa125ed4cae89a`（tag `amz-listing-kit:689c6b08…`）、`runtime_sha256=48002dc42f05…`、`public_configuration_sha256=652b1201…`、Caddyfile `e375655d…`、`default_trial=closed`、71 个受服资产；产物 `release-evidence-689c6b08…` 已下载到 `release-evidence/`。**本人独立线上核对**：首页 `5174a01b→992316a7`（12471→11469B）、`entry.js` `1bef8eab→1fef0209`（2501→2563B）、`styles.css` `73d6948d→60d8421a`（23212→23867B），两个 vite 辅助模块字节未变；`uv run --locked python tools/release_transaction_probe.py --page-smoke --base https://47.115.172.233:8080` 实跑 **12/12 rc=0**（含页面启动无工程诊断、项目新建刷新持久、包下载导入独立身份、零 console/page/网络错误）。证据 `_stage-amz-control/batch18-promotion-20261019/{pr19-merge-receipt.json,ci-39275366557.json,main-run-39277855632.json,release-evidence/,live-before-merge.json,live-before-merge-index.html,live-after-deploy.json,live-page-smoke-after-deploy.out,pr19-release-verification.json}`。真实出图品质、C15/C17 真人门与 B1–B7 仍**未**验收；本轮零付费调用；机器块 `next_action_task` 仍为 `V2.R5.1`（active），晋升不改变计划任务指针；18 批不追加，且按未完成保留。
- **2026-10-19 修复轮（PR#19）：CI 红灯定位为验证器口径落后于 B4，修复后 run `39270011225` 三个作业全 success（部署步骤按 PR 事件 skip，未部署）。** 原红灯 run `39260212352` 实际失败在 `V2.4.4-03/99`——B4 后制作区一次只渲染正看图、确认摘要默认「单张（跟随正在查看的图）」，旧断言仍按四张全集读候选行与摘要，不是产品回归。修复清单与逐条 rc 见 `_stage-amz-control/batch18-promotion-20261019/{ci-fix-round-20261019.json,ci-39270011225.json}`；提交 `8eaecc6` 已推送，run 证据含「Control plane and Product V2 = success（10 步全过）」。同轮把 V2.7.3 正式走查脚本迁移到当前产品、退役失去消费者的 `tools/repro_r51_*.py` 四条（字节封存 `retired-r51-repros-20261019T141454Z.zip`，sha256 `a0f77dfb…`），并消除两处自证风险：2_2_2 为既有系统提示断言补说明注释（实测出站 body 确有 role=system；该断言本就存在于 d0462ea，工作树草稿曾删掉、提交前恢复），packet08 VLM 短语逐字对齐域层来源 `domain/review.js`。
- **独立复核判定走查的 VLM 判据 incorrect，已按「用户可见优先」修复并整批替换走查证据（第二轮，未推送）。** `RehearsalMigrationReview` 指出：VLM 步骤唯一判据是 IndexedDB 谓词、屏幕结果从未断言，且当时证据的 `after_version=1/outcome=null` 与同次截图「VLM 已检查」矛盾。现改为主行文本「VLM 已检查」→ 比较面板 `[data-compare-vlm=checked]` → 库报告只作辅助；并补：整套检查入口 `count==1`+聚焦断言（V2.6.11 历史红灯就是它）、交付包 manifest 声明 sha256/byte_size 与实际字节逐条相等、390px 断言无横向溢出、四张 `attempt_states` 必须全 `succeeded`、确认后按产品口径断言「必须确认的槽位 3 / 3 已确认」并如实记录剩余 5 项非必填、**返工后显式选新候选再采用并核对交付包里就是那张返工候选**。复跑还修掉走查自身两处错判（首页盲打字被重渲染吞键→fill+点击；行上 `data-review-vlm` 不是 VLM 结果）。旧证据 `v273-rehearsal-20261019-221928` 23 文件已从仓库删除，由 `v273-rehearsal-20261019-230004` 取代；新实跑 rc=0（截图 21 张、导出 43,970B、采用返工候选 `act-4b101d07…`、零 console/page/http 错误）。差异与已知未覆盖面见 `review-round2-20261019.json`。第二个独立复核 `VerifyIntegrityReview`（验证器判据）判定 correct、无阻断：8 个验证器没有任何 check id 消失（只新增 `V2.4.4-03a`），V2.2.2 系统提示断言确认为真实出站 body；四条 MINOR 已全部处理——`-03a` 改为先切第二张再读摘要（否则分不开「跟随正看图」与「固定第一张」）、`2_2_3` 的 `-02` 增断言 `model_id` 非空且主行剔除 `.copy-proposals`、文档 §4.6 改「未选数量，原因见发送摘要」、`5_4` 注释与新判据对齐；复跑 `4_4` 15/15、`2_2_3` 26/26、`5_4` 30/30 全 rc=0。口径更正：2_2_2 那两条断言在 `d0462ea` 就已存在，本次提交的净效果只是补说明注释（工作树草稿曾删掉、提交前恢复）。当时下一动作：提交并推送本轮（含证据替换）到 `feat/complete-product-20261018`，跟同分支 CI 到绿，再走独立审查与两项 required 检查、受保护合并、既有 HTTPS 发布。（已完成，见本页首条晋升记录。）
- **追加批次上限18不变，第16–17批已把真实成品路径走出两段，当时前沿是PR19准入与受保护发布（已完成，见本页首条晋升记录）。** 用户明确批准13–18；原12批、第13批恢复范围失败及第14批Node4处失败均保留。第15批修复后类型/两构建/Node280、正式确认及人工编辑路径、原CI失败的理解界面检查均本地通过，单次POST硬上限与真实返工预览/取消已实测。第16批完成主图两模式真实闭环与两包往返；第17批按用户两项普通回答完成场景/尺寸重做、编译器修复与五图交付包重出。当时下一步：处置PR `#19`（head `9aedd308…`）的Control plane红灯`V2.2.3-22`，再走独立审查、两项required检查、受保护合并、既有HTTPS发布与线上/同源恢复。（已全部完成：`V2.2.3-22` 在 `d0462ea` 修复、B4 口径在 `8eaecc6` 修复、双审 MINOR 在 `9bd2b9d` 处理；PR #19 于 2026-10-19 合并为 `689c6b08` 并发布，见本页首条。同源恢复仍未做。）原生Goal `15ab22bf3386b9cf` active、原文不变；18批仍不完整即停，不自动追加。
- **B11三次submit按保守上界补记，不再重提。** `evals/product-v2/v2.4.5-live-reference-20261019-180800-b11-main-regenerate-ark-01.json` 的 `status=failed / image_submit_requests=3` 证明浏览器提交次数与单次预留不符；未取得可签收候选及逐笔上游受理/结算证据，不据同步超时断言供应商失败或免费。`boundary`仍是成功模板，与失败状态矛盾，不能引用作闭环证明。账本槽`b5-batch8-main-regenerate-ark-01`按3次保守计数、总上界`3×0.12=0.36元`保留，非`3×0.36元`；新lane占3/12图、0/4辅助、0.36/5元。原始失败与补记均保留，具体脚本路径和准入缺口见本次审计。
- **#9零收费切片已按保护规则阶段合并，完整产品仍未完成。** PR [#18](https://github.com/JusticeSc/listing-kit/pull/18)最终head `0ae7df59ff8e41e776195169ce8814f2699db45b`的两项required检查SUCCESS，实际保护未绕过；说明修正已提交，2026-10-18T14:29:26Z以merge commit `72c33df03514eaedd6f3e6efdf57236f26ada9f6`合并。旧受审代码head `3dc0018689dad39fb81294a9c76c99c97dc15e8f`及双审证据仍见`_stage-amz-control/complete-product-authorization-20261018T114240Z/pr18-review-closeout.json`；本轮最终准入/真实合并见`_stage-amz-control/full-product-start-20261018T140710Z/pr18-{merge-admission,merge-receipt,merged-main-run}.json`。**main push run `39136220536` 已实际核对：run 与「Docker image, smoke test, and main deploy」作业均 success，四个真实步骤（部署 → 静态/主链验收 → 清理前指纹核对 → finalize）全部 success**，证据 `_stage-amz-control/full-product-start-20261018T140710Z/pr18-main-release.json`（artifact `12139927165`）。同一次 push 的「Control plane and Product V2」作业是 skipped，因此这次发布不能当作控制面 32 项验证器的远程通过证据；发布身份见 `_stage-amz-control/main-merge-release-20261019/{release.json,image.txt,runtime-fingerprint.json}`（image `sha256:2d5495bf…`、runtime `6849e1cb…`，只描述 72c33df 这一次发布）。不关闭#9或代签像素、#8与完整产品。
- **原生Goal工具已实际可用，完整产品Goal已真实active。** 本轮直接get返回`No active goal.`，随后真实创建并读回`15ab22bf3386b9cf` active；观察见`evals/product-v2/refactor/goal-observation-full-product-20261018T140710Z.json`。#9作用域`15aacf5fbdd7001f`最后保存active及旧完整Goal`15a42a4b52b70942` paused只保留历史，没有将当前不存在的旧Goal伪结清或伪恢复。本轮原文唯一在计划§2.1，旧原文/状态已按原字节快照保留。
- **第16批真实成品路径已走出第一段（真实调用2次，0.42元保守占额）。** 原项目`17b6b29f`内明确原照重画先得1张真实图（action `act-bb447d3f…`、Prompt v15、候选v4，主体宽度占比63.5%未达编译进去的85%平台规则），据此做一次候选编辑（`act-02f23935…`、Prompt v16、候选v5，占比~85%、刻字NSK/608Z/INDONESIA与原照一致、纯白背景、无增造部件），在正式页明确采用（选择v2 `act-bb9d9700…`）。实际下载交付包8.37MB（主图字节等于采用候选）与项目包30.82MB；把项目包导入独立新origin后，257文档按kind|文档|版本|payload摘要全部逐一相等、21资产元数据相等、新增0、被采用主图Blob字节重算sha相同。发闸为自有宿主每次启动只放行一条预留形状请求，两次外发已逐条记录（只有prompt/参数/图片身份，无密钥/签名）。证据`resume-extension-20261019T105641Z/{b16-real-vertical.json,b16-actual-outbound.json,b16-bindings.json,b16-import-restore.json,packages/,b16-*-adopted.png}`。
- **两项普通决定已由用户回答并落地（第17批，真实调用4次，0.82元保守占额）。** 用户答：场景图「只保留商品与中性背景」、尺寸图「不标数字」。据此：场景图重做两次，第一次仍被模型自造机械旁件（拒绝），第二次得到中性背景+完整刻字的候选`act-46bd1c08…`（sha `1655f53c…`）并采用；尺寸图三次返工——前两次即使正文明确禁止仍被模型画出自造引线与乱码文字（拒绝），第三次在编译器修复后得到无线条/无文字候选`act-d2f33b43…`（sha `5e0f06af…`）并采用。
- **编译器缺陷已修复并留业务合同测试。** 尺寸图印字决定为「不印」时，旧简报仍写「标注指向对应部位」，等于邀请模型自造引线；现改为选`size_no_annotation`简报并留`SIZE_ANNOTATION_SKIPPED_PRINT_NONE`提醒（`app/product_v2/domain/prompt.js`），场景图简报也不再要求道具、只在有依据时才有物件。合同测试`prompt-expression-contract.test.mjs` P23b覆盖正反两面；`check:types`/两构建/`npm run test:domain` 281项全过。修复后的实际出站正文已逐字核对（无任何标注措辞）。
- **五图交付包与项目包已重出，独立空origin导入往返相等。** 交付包`packages/真实闭环-·-参考图-交付包-20261019-1305.zip`（门禁通过、5张、逐图sha与manifest一致）；项目包`…-20261019-1307.zip`(316文档/26资产)导入`http://127.0.0.1:5506`（导入前indexedDB为空、宿主拒绝任何provider调用）后316/26相等、刷新仍在；再从导入origin导出`…-1313.zip`与原件逐文档身份/版本/字节相等、26资产sha相同、无新增文档。**两项可选图（卖点信息图、细节图）采用处于「已过期」且在manifest中如实标`stale`**：其候选消费的是旧Prompt版本，刷新采用无法清除；重生成会耗尽最后2次授权生图，未做，如实保留。
- **该批一次本地守卫拒绝被如实记录，不冒充供应商失败。** 尺寸图第二次编辑的形状未登记在自有宿主预留清单，宿主在出站前拒绝，产品界面显示`provider_unknown / INTERNAL_ERROR`且trace行数/mtime证明无任何POST；登记该预留形状后按产品明确「新建 action（放弃核对）」重新提交才真正外发。证据`resume-extension-20261019T105641Z/{b16-actual-outbound.json,batch-17-evidence.json,packages/}`。
  （机器块`phase_progress.4`保持active、`V2.R5.1`由blocked转active，移除已获明确追加授权的旧批次阻塞；B11 Unknown/未签收、费用和其余验收缺口仍保留。）
- **第6批恢复纠偏与实际消费者结果（均零收费）。** 此前`consumer-cutover-20261019/verification.json`的“Confirmation2、包MIN3已闭合”已被真实历史包推翻：导出器自己的90/9包曾被MIN3拒绝；真实bearing包的人工全文返工被系统段落形状误拒，已有Confirmation2仅身份引用又被新用途/来源要求误拒。现新Confirmation/Snapshot写3、历史1/2只读，新Attempt3/既有身份2可读、包最低2；人工全文不强加系统段落但仍核返工身份/来源。写者/读者/类型/预约/包同组迁移，新动作不消费旧授权。正式页面90/9下载导入刷新及真实232文档/19Blob重开刷新逐条/原字节不变。最后整理后类型/两构建/Node277项、语义11项、独立profile项目迁移11项、文案采用9项、理解界面26项及设置/图像来源/BYOK/旧task38项均退出0；四组合Transport22项另有直接来源解码证据。精确命令/文件/边界见本批证据入口，非像素或最终发布验收。
- **行尾收口。**此前规范化和17个候选样本的CR0观察保留。本批发布清单另发现attempt.ts的1256处CRLF及5份当次生成报告的CRLF，均只转LF，源文本/JSON payload不变；原字节、SHA与等价结果见`_stage-amz-control/b1-b3-vertical-20261019/eol-publication.json`。提交前已实际核对这6个文件index/working tree均LF及生效attributes，不从旧样本外推全库。
- **失败和验证资格保留。** 历史`verify_v2_3_6`导航hidden超时、旧临时profile六个Blob不可读原因未明，不用后来绿灯签根治；原26项及诊断见`_stage-amz-control/copy-adoption-contract-20261019/`与第5批证据。第5批比较夹具补齐schema3元数据后的两轮绿见`evals/product-v2/v2.7.1-regression-20261019-121022-final.json`；其后消费者已改，不计最终B6。第6批H10补canonicalJson import后的结果及旧9145宿主max2排除继续保留；4acfc92仅证明当时B1–B3工程，后续工作台与B11另有结果。此前“额度未激活、零新收费、当前9167宿主”只属该时点，不能覆盖本页当前边界或推断当前服务仍运行。
- **5712px个案已有同原件可逆因果资产，最终人因矩阵尚未完成。** 用停工时归档UI原字节及真实bearing232/19包在1440×1000复放，实测5720px（不改写旧5712读数，也不臆断8px差值）；根因是两类英文语言警告去空格后形成长串，文本绘制越过正常元素边界。只修`.prompt-warning`仍5720，只修`.confirm-risk`剩5523，两处均换行后1440；撤销恢复5720。11段警告原文不变，root/body overflow仍visible，无zoom/transform，图片未裁。当前CSS已有两处换行规则，按未变前提复用；证据`_stage-amz-control/b1-b3-vertical-20261019/overflow/causality.json`及Before/After。归档UI临时宿主/标签页及提取源码已清理，原包/原像素不动；不能以此代签当前四段最终尺寸/缩放交互。

**交接阅读边界**：以上当前边界是门/权限/唯一下一动作，审计原始复现与双审指针见同一审计JSON；不另建执行状态。执行包按计划§17.2–17.5，问题验收分别在#8/#9/#7/#10；下方历史资产只在当前包引用时定向读，不从旧P0–P8/批数/停工叙述恢复施工。此前交接加固见`_stage-amz-control/handoff-hardening-20261018T132906Z/verification.json`；其中指定Mimo override被拒，实际为默认scout冷读，不是指定弱模型验收。真实启动快照见`_stage-amz-control/full-product-start-20261018T140710Z/verification.json`。

- **2026-10-16停工、2026-10-17独立main基线及随后工具不可用均为历史范围。** 本轮用户明确开始且原生完整产品Goal已真实绑定，不再用旧停工/工具错误阻断获批动作。旧Goal paused观察仍保留在`evals/product-v2/refactor/goal-observation-stop-20261016.json`，不改写为本轮Goal状态；main及PR #13–#16工程资产照旧复用，不从零重做。
- **此前2026-10-15也曾停工，随后有过正式恢复，但已被上面的2026-10-16新停工取代。**旧观察 `evals/product-v2/refactor/goal-observation-stop-20261015.json` 和旧过早closeout不代表当前许可/完成。原七项目、失败与恢复材料仍在 `_stage-amz-control/next-version-b5-20261015/reconciliation.json`、`stop-closeout.json`，不重抓、不重生、不清零。
- **2026-10-18较早阶段仅审计与规划的边界已被上方最新用户恢复决定取代。** 审计证据仍见`evals/product-v2/refactor/status-audit-20261018.md`及`_stage-amz-control/status-audit-20261018/verification.json`；保留其当时事实，不把旧“本轮不恢复”当当前用户意图，也不把最新授权写成原生Goal已恢复。
- **（历史快照，已被本页首条晋升记录取代；以下为 2026-10-19 修复轮当时的读数。）本次实时源码/PR/线上身份已分别核对（当时复核：PR#19 head 已由 `9aedd308e6925ec7880c853bc064fa5fbf335c19` 推进到 `d0462ea3743ead8303cdb86ae99c5234f0c27fd0`；该 head 的 run `39260212352` Control plane 失败于 `V2.4.4-03/99`，`V2.2.3-22` 已在 d0462ea 内修复，见本页首条）。** 分支`feat/complete-product-20261018`及PR [#19](https://github.com/JusticeSc/listing-kit/pull/19) head均为`9aedd308e6925ec7880c853bc064fa5fbf335c19`，PR为OPEN Draft、BLOCKED；run `39228244927`的Control plane失败于`V2.2.3-22`事实卡片渐进披露检查，Docker作业skipped，没有以重跑掩盖。main仍为#18 merge `72c33df03514eaedd6f3e6efdf57236f26ada9f6`；只读SSH实际容器image ID为`sha256:2d5495bf705278f367468cf0cc36345b68d1e3cc7115ef6bf9927cff07cb16e6`、running/healthy，可信HTTPS health通过，无previous应用容器且发布journal不存在。main上次run `39136220536`成功只证阶段发布，不证明#19或完整产品已上线。保护仍要求两项CI、strict及enforce_admins；当时PR19无GitHub review记录。#7/#8/#9/#10仍OPEN。未提交规约/工具/状态改动与本地过程材料保留，不整包暂存、清理或外发。**当时读数之后：#19 已以 `689c6b08` 合并、main run `39277855632` 部署到 finalize，当前线上镜像 `sha256:cb3857eb…`、`runtime_sha256=48002dc4…`（见本页首条）。**
- **独立main基线已用5/10批；本次既有main流水线完成发布，非新产品施工批。**main push run`39090266442`成功，真实deploy→HTTPS页面验收→候选/线上指纹比较→finalize均成功；artifact`12122467000`已下载至`_stage-amz-control/status-audit-20261018/release-evidence/`。线上镜像`amz-listing-kit:f9b5b4e7e535ba40c1ff89f08e23d6b91d22dbb4`，image ID`sha256:4774d0c7d2d5d215e1d5d3f9235994114905abad3f8117965040374280067429`，实际容器healthy、可信HTTPS health通过、无previous容器、真实`~/.config/amz-listing-kit/deploy-transaction.env`不存在。runtime仍`a1e73bdc3454a994213fe59b9ae5ea5c3034da20573bca9f2072f040e79d8de1`，与上次相同；这是镜像身份更新，不是功能新增。旧run`39045865774`及入库`evals/product-v2/refactor/baseline-release-20261017T154245Z/`继续证明旧`2c4a33a`事件。main push不因纯文档而跳过发布，旧“#16不部署”和检查`release-transaction.state`的说法均已纠正。C15保持open；用户亲验保留为强信号，C17正式签署范围与最终版本绑定仍须单独核对，不代签。
- 历史停工启动快照为`fix/byok-receipt-20261009`、`48bb3c1e2f3751a984170a01361a2fba5f6e4ae4`加当时WIP，不再作为当前main身份。下一版WIP已另行封存，保留原用户材料/五图/两包及证据，不因main审计而重生/重抓或整包恢复；当时main仍六入口和既有返工合同，不能把WIP能力当已上线（2026-10-19 PR #19 合并后 main 已推进，见本页首条）。
- **第5批时点的历史读数（不是当前计数）：当时5/12已占用，本地行为已验证、独立复核前业务整批未验收。** 前四组为初始来源/规格合同实现验证、文案提议请求修复验证、采用链修复验证、规格OCC恢复修复验证；第5组为审计后owner/编译消费者及实际页面预览一致性的同组修复验证。理由及证据见审计JSON与第5批`verification.json`。旧7/10、独立main5/10及#9原交付范围保留，不冒充本轮余量；未提交不等于未占用。后续按实际完整批次追加，不按文件/调用拆批；最终同候选两轮合计一批。第12批仍未完整交付即停并交接，不自动追加、不降低验收。
- **金额和激活次数不增加。** 原授权仅一次激活；历史52图/11.20元保守基线和B11的3次/0.36元Unknown上界保留。第16批已在同账预留1次Qwen原照重画、0.20元（1输入×0.02＋1输出×0.18，官方北京价本次直接核对），尚未因此视为已提交或结算。当前占额4/12图、0/4辅助、0.56/5元，最多余8图/4辅助/4.44元，累计安全上界11.76/21元。只取`current_control_15ab22bf3386b9cf`及对应逐笔/累计上限，根spent等数字只属历史。失败/Unknown不释放，不再激活，素材仍为获准用户原件。
- 原停工WIP的单向owner、候选报告、精确返工等成果保留原版本证明，不能自动外推main已包含全部下一版能力。main现有owner在本次实际代码评估中按真实差量复用，不从旧清单重建；连续事实更新/草稿保护的本地历史证明仍见`evals/product-v2/manual-mug-assist/auto-preparation-fix-20261010.md`。
- **V1活运行链及旧专属消费者已在main基线清退，不再安排重复清退。**FastAPI/Uvicorn、Vite单产物、lit-html、共享信封结构及验证治理取当前代码/锁/CI；历史用户原件、许可、失败/账本和恢复材料保留。旧收尾“V1未动”、README“只是分支候选”及冷恢复任务卡P0→P1旧指令已更正；不是恢复旧产品或删除历史。
- **剩余前沿是发送安全和当前产品差量，不是再次治理基线。** B1–B3及B4已有实现与局部真实页面证据，先保留；本次批准后最早离线闭合所选范围、实际摘要/费用上界、预算预留及POST次数一致，并处置PR19现有CI红灯，再补新程序稿/真实两模式与必要人因。最后消费者修改后仍须同候选完整两轮、独立审查、受保护发布及同origin恢复。旧owner/BYOK/秘密/五图/两包按未变前提复用，不重建、不为新日期重买证明。
- **不再等待重复原图，不把截图当所有事实。**原用户2026-10-15T07:31:58.079Z已明确“1按截图开打”，原PNG sha `90de3c617d1379532ac303fd992994b976d956f43e4c434a8e3aac474a5e06f5`与商品JPEG sha `4c4ed76c61c959ace082f8f3698f1b10bf0e1c942c2b1e524b1e62086d4df1e1`已保全、同57704原库已实际重开。截图只证INDONESIA/608Z/NSK及可见外观，不能证轴承钢/608ZZ/真实量测或不可见结构；尺寸槽v3另取NSK608官方公称d8/D22/B7mm，不冒称用户实测。qwen-vl-max精确ID/现价仍未重新核到，不新增其收费理解/复核、不静默换型；人工路径不因此阻断。
- **历史临时运行资源已释放。**付费观察host `bearing-real-wire-20261015`已停止、临时 `_working/_bearing_real_wire.py`已删除；之后同57704默认closed普通host亦已停止。两个历史独立无头Chrome均已原生关闭，实际进程及57704监听为空，见 `real-wire/resource-closeout.json`（相对上述stage目录）。原profile/用户原件保留；只有当时新建的独立故障副本profile在核对进程消失后删除。本轮另启的代表数据基线host/隔离无头profile以新启动stage证据单独记录，不冒称当前没有运行资源。
- **五张不同用途原像素合格且均已正式采用。**主图v3、信息图v7、场景v1、细节v2、尺寸v5；最后火山第9次尺寸原照补图 action `act-04a84b645ec44047b550ef18740e1241`，原PNG sha `ffa3ed2449e02cfec93fee828e0fc58bda056149354520bd53528fc3acc4d40e`，四行官方公称参数与not measured正确、无额外灰框/箭头/乱码。见 `real-wire/five-adopted-pixel-proof.json`。信息图右侧留白未达内部40px偏好但商品未裁断，保留布局偏差，不声称每条指令完美遵循；此前所有错误原字节及费用均保留。
- **旧两包原字节本次已重新校验，恢复证明保留原版本范围。** 原件实际在相邻主工作树`../amz-listing-kit/_stage-amz-control/formal-resume-20261015T125651Z/real-wire/`，不是本隔离工作树中的同名相对目录。`bearing-main-final.delivery.zip` 8739956B/sha `6839e91313089edc354443a1d55a74177054b703f21a26ccc2708ea1b0695a3e`；`bearing-main-final.project.zip` 28098549B/sha `5dd5b7d27d198b788b2aad5dacf193af5dd4e636b0f493bdc407478084717591`；本次原生完整哈希、CRC及交付五图hash均与原证明一致。历史`package-recovery-proof.json`记录独立空profile导入刷新232文档/19Blob全等、再导出仅新增export_record；这不是本次重跑恢复或当前版本采用重新签收，AI仍not_run。
- **报告采用硬门实际负例已留存，故障副本不可充当正式项目。**只在独立导入副本删除一条历史Qwen候选报告，再点实际“采用当前候选”，正式事务拒绝“精确来源版本缺失”，旧采用记录完整不变，见 `real-wire/report-loss-adoption-proof.json`。刷新补建本地报告后，该历史候选被一次技术性采用且正确标为已过期v2；等待文案误用未过期形式而超时，并非产品故障。未生成技术QA交付包；用户停工后不再继续该路径。原profile五合格采用及此前两组恢复包未受故障操作影响。
- **程序稿品质仍缺直接证明，旧图不作废。** 尺寸专家稿原出站在相邻主工作树上述`real-wire/formal-bearing-ark-size-expert-09/outbound.json`，不代签自动增强。5712px旧读数保留；后来同原件5720→1440→5720可逆因果证明见本页L17所指资产，不再写“根因尚未定位”，也不据此签当前四段完整人因。实际缩放/长内容关键操作及当前程序稿→请求→原像素→采用仍按#8/#9补证。

原长篇时点叙事保留于 `_stage-amz-control/next-version-design-20261012/baseline/before/_working/amz-listing-kit-product-v2/state.md`（SHA256 `af524be0793d16a41d7eb843fe85fef9bfe4b61bccc59d42d1a36d6c1e8dc9cb`）；本次启动前完整机器字节见新启动快照。下方是按计划§7.5重判后的当前机器块，旧证据与历史unknowns保留，不另建当前状态。

```yaml
state_schema: amz-project-state/v2
task_id: amz-listing-kit-product-v2-refactor
status: paused
goal_binding: required
goal_id: "15ab22bf3386b9cf"
goal_pending_reason: null
goal_binding_evidence: evals/product-v2/refactor/goal-observation-stop-20261020T012741Z.json
system_goal_observed_status: paused
system_goal_observed_at: '2026-10-20T01:28:24.826000Z'
plan_ref: docs/product-v2-refactor-plan.md
latest_audit: _stage-amz-control/status-audit-20261019T103737Z/observations.json
phase_progress:
  '0':
    status: done
    evidence:
    - evals/product-v2/refactor/control-preparation-20261001.md
  '1':
    status: done
    evidence:
    - evals/product-v2/refactor/development-cutover-20261001-143954.md
    - evals/product-v2/refactor/goal-session-confirmation-20261001-125600.md
    - evals/product-v2/refactor/baseline-and-boot-20261001-133400.md
    - evals/product-v2/refactor/recovery-and-r13-20261001-143134.md
    - evals/product-v2/refactor/goal-recovery-20261002.md
  '2':
    status: done
    evidence:
    - evals/product-v2/refactor/ui-baseline-20261001-chrome.md
    - evals/product-v2/refactor/reference-review-20261001.md
    - evals/product-v2/refactor/prototype-review-20261002.md
    - evals/product-v2/refactor/goal-recovery-20261002.md
  '3':
    status: done
    evidence:
    - evals/product-v2/refactor/session-lifecycle-20261002-r33-update.md
    - evals/product-v2/refactor/home-read-recovery-20261003.md
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-025221-home-read-recovery-shutdown.json
  '4':
    status: blocked
    evidence:
    - evals/product-v2/refactor/effective-config-byok-20261003.md
    - evals/product-v2/refactor/execution-identity-package-20261003-072854.md
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/refactor/formal-start-20261005.md
    - evals/product-v2/refactor/next-version-b1b3-20261015.json
    - _stage-amz-control/b4-workbench-20261019/budget-activation.json
    - _stage-amz-control/b5-batch8-20261019/b10-zero-fee-longitudinal-20261019.json
    - _stage-amz-control/b5-batch8-20261019/b11-send-attempt-20261019.json
    - _stage-amz-control/b5-batch8-20261019/b12-final-closeout-20261019.json
  '5':
    status: pending
    evidence:
    - evals/product-v2/refactor/generation-module-20261003-084705.md
    - evals/product-v2/refactor/two-image-adapters-20261003-094600.md
    - evals/product-v2/refactor/prompt-confirmation-consistency-20261003-120238.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-154254.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/four-mode-proof.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/workspace-focus-proof.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/five-adopted-pixel-proof.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/package-recovery-proof.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/report-loss-adoption-proof.json
  '6':
    status: pending
    evidence:
    - evals/product-v2/refactor/intake-suite-ui-20261003-122229.md
    - evals/product-v2/refactor/compare-rework-selection-ui-20261003-123202.md
    - evals/product-v2/refactor/delivery-recovery-settings-ui-20261003-124930.md
    - evals/product-v2/refactor/storage-contract-review-20261003.md
    - evals/product-v2/refactor/product-design-audit-20261004.md
    - evals/product-v2/refactor/design-convergence-20261004.md
    - evals/product-v2/refactor/specification-consolidation-20261004.md
  '7':
    status: pending
    evidence:
    - evals/product-v2/refactor/completion-matrix-20261003-r74.md
    - evals/product-v2/refactor/completion-matrix-20261003-r74.json
task_progress:
  V2.R0.1:
    status: done
    evidence:
    - docs/product-v2-refactor-plan.md
    - docs/INDEX.md
    - docs/product-v2-project-context.md
    - _working/amz-listing-kit-product-v2-baseline/state.md
  V2.R0.2:
    status: done
    evidence:
    - evals/product-v2/refactor/control-preparation-20261001.md
    - tools/check_project_state.py
    - tools/refactor_resume.py
    - evals/probes/project_state.py
    - evals/probes/docs_index.py
  V2.R1.1:
    status: done
    evidence:
    - evals/product-v2/refactor/goal-binding-20261001-094520.md
    - evals/product-v2/refactor/goal-session-observation-20261001-121220.json
    - evals/product-v2/refactor/goal-session-confirmation-20261001-125600.md
    - evals/product-v2/refactor/goal-observation-20261002.json
    - evals/product-v2/refactor/goal-recovery-20261002.md
    - evals/product-v2/refactor/goal-observation-20261003-unattended-trigger.json
    - evals/product-v2/refactor/goal-observation-20261005-formal-start.json
  V2.R1.2:
    status: done
    evidence:
    - evals/product-v2/refactor/baseline-and-boot-20261001-095710.md
    - evals/product-v2/refactor/work-audit-20261001-103825.md
    - evals/product-v2/refactor/baseline-and-boot-20261001-133400.md
    - evals/product-v2/refactor/recovery-and-r13-20261001-143134.md
    - evals/product-v2/refactor/development-cutover-20261001-143954.md
  V2.R1.3:
    status: done
    evidence:
    - evals/product-v2/refactor/work-audit-20261001-103825.md
    - evals/product-v2/refactor/baseline-and-boot-20261001-133400.md
    - evals/product-v2/refactor/recovery-and-r13-20261001-143134.md
    - evals/product-v2/refactor/r13-smoke-20261001-143134.json
  V2.R2.1:
    status: done
    evidence:
    - evals/product-v2/refactor/ui-baseline-20261001-chrome.md
    - evals/product-v2/refactor/ui-baseline-20261001-chrome.json
    - evals/product-v2/refactor/background-automation-20261001.md
    - evals/product-v2/refactor/headless-export-20261001.json
    - evals/product-v2/refactor/headless-matrix-20261001.json
    - evals/product-v2/refactor/headless-package-integrity-20261001.json
  V2.R2.2:
    status: done
    evidence:
    - evals/product-v2/refactor/prototype-review-20261002.md
    - evals/product-v2/refactor/prototype-smoke-20261002.json
    - evals/product-v2/refactor/prototype-observations-20261002.json
    - evals/product-v2/refactor/goal-recovery-20261002.md
  V2.R2.3:
    status: done
    evidence:
    - evals/product-v2/refactor/reference-review-20261001.md
  V2.R3.1:
    status: done
    evidence:
    - evals/product-v2/refactor/frontend-selection-20261002.md
    - evals/product-v2/refactor/frontend-approval-20261002.json
    - package.json
    - package-lock.json
    - docs/product-v2-project-context.md
  V2.R3.2:
    status: done
    evidence:
    - evals/product-v2/refactor/verification-seams-20261002.md
    - evals/product-v2/v2.2.1-product-contracts-20261002-144142.txt
    - evals/product-v2/v2.1.3-project-package-20261002-144152.txt
    - evals/product-v2/v2.5.1-deterministic-review-20261002-144206-r32-seams.txt
    - evals/product-v2/v2.5.1-deterministic-review-20261002-144206-r32-seams.json
    - config/product-v2/verification.json
    - evals/product-v2/node/_gen.mjs
  V2.R3.3:
    status: done
    evidence:
    - evals/product-v2/refactor/session-lifecycle-20261002-r33-update.md
    - evals/product-v2/v2.3.3-session-lifecycle-20261002-231308-run2.json
    - evals/product-v2/v2.3.3-session-lifecycle-20261002-231354-run3.json
    - app/product_v2/session.ts  # P4第2阶段已删生成兄弟.js；源文件才是当前权威身份
    - tools/verify_v2_3_3_session_lifecycle.py
    - evals/product-v2/refactor/home-read-recovery-20261003.json
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-025221-home-read-recovery-shutdown.json
    - evals/product-v2/v2.1.4-formal-entry-20261003-024816-home-read-recovery.json
    - evals/product-v2/v2.1.2-project-home-20261003-024837-home-read-recovery.json
    - evals/product-v2/refactor/home-diagnostic-smoke-20261003.json
  V2.R4.1:
    status: done
    evidence:
    - evals/product-v2/refactor/image-candidate-review-20261002.md
    - evals/product-v2/refactor/image-candidate-review-20261002-seedream.md
    - evals/product-v2/refactor/model-preflight-20261003.txt
  V2.R4.2:
    status: done
    evidence:
    - evals/product-v2/refactor/work-audit-20261003.md
    - evals/product-v2/refactor/model-preflight-20261003.txt
    - evals/product-v2/refactor/owner-decisions-20261003-index-volcengine.json
    - evals/product-v2/v2.4.5-live-reference-20261003-145223-r42-dashscope-run5.json
    - evals/product-v2/v2.4.5-live-reference-20261003-145223-r42-dashscope-run5.txt
    - evals/product-v2/v2.4.5-live-reference-20261003-145223.png
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.txt
    - evals/product-v2/v2.4.5-live-reference-20261003-154157.png
    - evals/product-v2/v2.4.5-live-reference-20261003-154037-r42-volcengine-run2.json
    - evals/product-v2/v2.4.5-live-reference-20261003-153732-r42-volcengine-run1.json
    - src/providers/v2_volcengine_image.py
    - tools/verify_v2_4_5_live_reference.py
    - _working/amz-listing-kit-product-v2/budget-ledger.json
  V2.R4.3:
    status: done
    evidence:
    - evals/product-v2/refactor/effective-config-byok-20261003.md
    - evals/product-v2/refactor/config-and-credential-20261005.md
    - evals/product-v2/v2.4.1-image-gateway-20261005-141712.txt
    - evals/product-v2/v2.2.2-semantic-provider-20261005-141538.txt
    - evals/product-v2/v2.5.1-deterministic-review-20261005-142343.txt
    - evals/product-v2/v2.5.2-vlm-review-20261005-142259.txt
    - evals/product-v2/v2.5.5-suite-review-20261005-141348.txt
    - evals/product-v2/v2.ui.3-frontend-20261005-150315.txt
    - evals/product-v2/v2.ui.3-frontend-20261005-150341-final.txt
    - src/providers/v2_credentials.py
    - src/providers/v2_outbound.py
    - app/product_v2_server.py
    - src/providers/v2_registry.py
    - .github/workflows/ci-cd.yml
    - .env.example
  V2.R4.4:
    status: done
    evidence:
    - evals/product-v2/refactor/execution-identity-package-20261003-072854.md
    - evals/product-v2/v2.4.2-generation-attempt-20261003-072854-r44-identity.json
    - evals/product-v2/v2.4.2-generation-attempt-20261003-072854-r44-identity.txt
    - evals/product-v2/v2.4.1-image-gateway-20261003-072955-r44-identity.txt
    - evals/product-v2/v2.1.3-project-package-20261003-073227-r44-identity.txt
    - evals/product-v2/v2.4.2-generation-attempt-20261003-084647.json
    - evals/product-v2/v2.4.2-generation-attempt-20261003-084647.txt
    - evals/product-v2/v2.4.3-batch-suite-20261003-084705.json
    - evals/product-v2/v2.4.3-batch-suite-20261003-084705.txt
    - evals/product-v2/refactor/execution-identity-package-20261005.md
    - evals/product-v2/v2.4.2-generation-attempt-20261005-184623.json
    - evals/product-v2/v2.4.2-generation-attempt-20261005-184623.txt
    - evals/product-v2/v2.4.1-image-gateway-20261005-184700.json
    - evals/product-v2/v2.4.1-image-gateway-20261005-184700.txt
    - evals/product-v2/v2.1.3-project-package-20261005-184649.json
    - evals/product-v2/v2.1.3-project-package-20261005-184649.txt
    - evals/product-v2/refactor/next-version-start-20261013T040950Z.json
    - evals/product-v2/refactor/next-version-b1b3-20261015.json
    - evals/product-v2/v2.5.4-rework-loop-20261015-074537fixer-shared2.json
    - evals/product-v2/v2.6.3-transfer-20261015-074943-b1b3-native-reload.json
    - evals/product-v2/refactor/b1-b3-consumer-closure-20261019.json
    - evals/product-v2/v2.6.3-transfer-20261019-133339-b3-integrated-confirm3.json
    - evals/product-v2/refactor/b3-semantic-lifecycle.json
  V2.R5.1:
    status: blocked
    evidence:
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/remaining-pixel-review.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/five-adopted-pixel-proof.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/package-recovery-proof.json
    - _stage-amz-control/formal-resume-20261015T125651Z/real-wire/report-loss-adoption-proof.json
    - evals/product-v2/refactor/goal-observation-stop-20261016.json
    - evals/product-v2/refactor/final-delivery-20261007.md
    - evals/product-v2/refactor/goal-observation-final-delivery-20261007.json
    - evals/product-v2/refactor/generation-module-20261003-084705.md
    - app/product_v2/generation.ts
    - app/product_v2/workspace.js
    - evals/product-v2/v2.4.2-generation-attempt-20261003-084647.json
    - evals/product-v2/v2.4.3-batch-suite-20261003-084705.json
    - evals/product-v2/v2.4.4-candidate-blob-20261003-085109.json
    - evals/product-v2/refactor/generation-module-20261005-formal.md
    - evals/product-v2/refactor/r51-packet-05-reserve-fence-20261006.json
    - evals/product-v2/refactor/r51-packet-06-delivery-scope-20261007.json
    - evals/product-v2/v2.r51p04-input-owner-20261006-163934.json
    - evals/product-v2/v2.r51p04-input-owner-20261006-163934.txt
    - evals/product-v2/v2.r51p05-reserve-twotab-20261006-165748.json
    - evals/product-v2/v2.r51p05-reserve-twotab-20261006-165748.txt
    - evals/product-v2/v2.r51p06-adopt-deliver-20261006-170325.json
    - evals/product-v2/v2.r51p06-adopt-deliver-20261006-170325.txt
    - evals/product-v2/v2.r51ga-group-a-20261006-170716.json
    - evals/product-v2/v2.r51ga-group-a-20261006-170716.txt
    - evals/product-v2/refactor/r51-page-evidence-20261007.md
    - evals/product-v2/refactor/r51-packet-07-views-20261007.md
    - evals/product-v2/refactor/packet11-convergence-20261008.md
    - evals/product-v2/refactor/asset-continuation-20261008.md
    - evals/product-v2/v2.7.1-regression-20261008-p11close2-final.txt
    - evals/product-v2/v2.7.1-regression-20261008-p11close2-final.json
    - evals/product-v2/v2.ui.2-interaction-visual-20261008-015527fix6.json
    - evals/product-v2/v2.4.2-generation-attempt-20261008-014820-fix3.json
    - evals/product-v2/v2.3.5-pre-generation-confirm-20261008-005056-diag6.json
    - evals/product-v2/v2.5.3-compare-panel-20261008-005703diag1.json
    - evals/product-v2/v2.4.3-batch-suite-20261008-005618-diag1.json
    - evals/product-v2/v2.4.4-candidate-blob-20261008-005644-diag1.json
    - tools/v2_verify_shared.py
    - tools/verify_v2_ui_2_interaction_visual.py
    - tools/verify_v2_4_2_generation_attempt.py
    - evals/product-v2/refactor/next-version-b1b3-20261015.json
    - evals/product-v2/refactor/next-version-b4-20261015.json
    - evals/product-v2/refactor/next-version-b5-20261015.json
  V2.R5.2:
    status: pending
    evidence:
    - evals/product-v2/refactor/two-image-adapters-20261003-094600.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-094235.json
    - evals/product-v2/PRODUCT-V2-R5.2-batch-20261003-094246.png
    - evals/product-v2/PRODUCT-V2-R5.2-refresh-20261003-094249.png
    - src/providers/v2_volcengine_image.py
    - src/providers/v2_image.py
    - src/providers/v2_registry.py
    - src/providers/v2_outbound.py
    - app/product_v2/domain/attempt.js
    - app/product_v2/domain/candidate.js
    - app/product_v2/generation.js
    - config/product-v2/providers.json
    - config/product-v2/verification.json
    - .github/workflows/ci-cd.yml
    - .env.example
    - evals/product-v2/harness/attempt-contract.js
    - evals/product-v2/node/attempt-contract.test.mjs
    - tools/verify_v2_r5_2_two_adapters.py
    - evals/product-v2/v2.4.3-batch-suite-20261003-105401-r52-diagnosis.json
    - evals/product-v2/v2.4.3-batch-suite-20261003-105608-r52-helper-fix.json
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-105608.json
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-154254.json
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.txt
    - evals/product-v2/v2.4.5-live-reference-20261003-154157.png
  V2.R5.3:
    status: pending
    evidence:
    - evals/product-v2/refactor/r53-gateway-smoke-20261003.json
    - evals/product-v2/refactor/model-preflight-20261003.txt
    - evals/product-v2/refactor/prompt-confirmation-consistency-20261003-120238.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-120238.json
  V2.R6.1:
    status: pending
    evidence:
    - evals/product-v2/refactor/intake-suite-ui-20261003-122229.md
    - evals/product-v2/v2.2.3-intake-understanding-20261003-121735.txt
    - evals/product-v2/v2.3.2-suite-editor-20261003-121756.txt
    - evals/product-v2/v2.3.3-spec-versions-20261003-121811.txt
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-121827.json
    - evals/product-v2/v2.3.4-prompt-compiler-20261003-121845.txt
    - evals/product-v2/v2.3.5-pre-generation-confirm-20261003-122120.txt
    - evals/product-v2/v2.3.6-prompt-manual-edit-20261003-122145.txt
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-122229.json
    - evals/product-v2/refactor/generation-module-20261005-formal.md
  V2.R6.2:
    status: pending
    evidence:
    - evals/product-v2/refactor/compare-rework-selection-ui-20261003-123202.md
    - evals/product-v2/v2.5.1-deterministic-review-20261003-122935.txt
    - evals/product-v2/v2.5.2-vlm-review-20261003-122952.txt
    - evals/product-v2/v2.5.3-compare-panel-20261003-123008.txt
    - evals/product-v2/v2.5.4-rework-loop-20261003-123054.txt
    - evals/product-v2/v2.5.5-suite-review-20261003-123125.txt
    - evals/product-v2/v2.6.1-selection-20261003-123145.txt
    - evals/product-v2/v2.6.4-a11y-20261003-123202.txt
    - evals/product-v2/refactor/generation-module-20261005-formal.md
  V2.R6.3:
    status: pending
    evidence:
    - evals/product-v2/refactor/delivery-recovery-settings-ui-20261003-124930.md
    - evals/product-v2/v2.6.2-delivery-20261003-124831.txt
    - evals/product-v2/v2.6.3-transfer-20261003-124930.txt
    - evals/product-v2/v2.6.4-a11y-20261003-123202.txt
    - evals/product-v2/refactor/product-design-audit-20261004.md
    - evals/product-v2/refactor/design-convergence-20261004.md
    - evals/product-v2/refactor/specification-consolidation-20261004.md
    - evals/product-v2/refactor/development-preparation-20261004.md
    - evals/product-v2/refactor/goal-start-blocked-20261005.json
    - evals/product-v2/refactor/generation-module-20261005-formal.md
  V2.R6.4:
    status: done
    evidence:
    - evals/product-v2/refactor/storage-contract-review-20261003.md
    - evals/product-v2/refactor/work-audit-20261003.md
    - evals/product-v2/refactor/storage-measurements-20261003.json
    - evals/product-v2/refactor/home-read-recovery-20261003.md
    - evals/product-v2/refactor/owner-decisions-20261003-index-volcengine.json
    - evals/product-v2/refactor/native-index-verification-20261003.json
    - evals/product-v2/v2.1.1-indexeddb-20261003-032509-native-latest-index.json
    - evals/product-v2/v2.1.3-project-package-20261003-032510-native-latest-index.json
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-032515-native-latest-index.json
    - evals/product-v2/v2.1.4-formal-entry-20261003-032824-native-latest-index.json
  V2.R7.1:
    status: pending
    evidence:
    - evals/product-v2/refactor/full-verification-20261003-r71.md
    - evals/product-v2/v2.7.1-regression-20261003-r71f-final.txt
    - evals/product-v2/v2.7.1-regression-20261003-r71f-final.json
    - evals/product-v2/v2.2.2-semantic-provider-20261003-194132-r71-semlive.json
    - evals/product-v2/v2.5.2-review-live-20261003-194238r71-vlm.json
    - evals/product-v2/v2.4.5-live-reference-20261003-194526-r71-dashscope2.json
    - evals/product-v2/v2.4.5-live-reference-20261003-195600-r71-volc2.json
    - evals/product-v2/v2.4.5-live-reference-20261003-194502-r71-dashscope.json
    - _working/amz-listing-kit-product-v2/budget-ledger.json
  V2.R7.2:
    status: pending
    evidence: []
  V2.R7.3:
    status: pending
    evidence: []
  V2.R7.4:
     status: pending
     evidence:
     - evals/product-v2/refactor/completion-matrix-20261003-r74.md
     - evals/product-v2/refactor/completion-matrix-20261003-r74.json
     - evals/product-v2/v2.4.5-volc-adopt-export-20261003-222253.json
     - evals/product-v2/v2.4.5-volc-adopt-export-20261003-222140.json
     - tools/verify_v2_volc_adopt_export.py
     - config/product-v2/verification.json
  V2.R7.5:
    status: pending
    evidence:
    - evals/product-v2/refactor/generation-module-20261005-formal.md
    - app/product_v2/domain/attempt.ts
    - app/product_v2/domain/config-export.ts
    - tools/build_product_v2_ts.mjs
next_action_task: V2.R5.1
blockers:
- "V2.R5.1_用户2026-10-20「即刻停止当前工作，做好收尾准备」：恢复需用户明确 resume，并先核 state／_stage-amz-control/b18-optional-figures-20261020/closeout-stop-20261020.md／实时仓库；批次18五图两包与模式B证据仍未闭合"
unknowns:
  - current_20261019_Goal_15ab22bf3386b9cf_active_user_explicit_approved_six_additional_batches_continue13to18_first_two_zero_fee_original_budget_and_scope_preserved_R51_active_batch13_send_scope_exclusions_cost_reservation_POST_frontier_approval_stage_resume_extension_20261019T105641Z_no_new_provider_submit
  - historical_20261019_batch12of12_stop_obeyed_then_audit_and_explicit_user_extension_granted_no_reset_B11_three_browser_submits_cny0p36_preserved_no_signed_results_no_retry_remaining_program_pixels_dual_mode_five_current_adoptions_two_rounds_release_C15_C17
  - current_20261016_actual_Github_issues_7_engineering_workflow_8_real_content_UI_9_program_Prompt_created_and_remote_readback_verified_only_issue_write_and_recovery_handoff_authorized_no_product_Goal_resume_PR_commit_push_paid_or_deploy_no_local_issue_progress_copy
  - current_20261016_withdraw_whole_criteria1_to6_claim_program_creative_prompt_and_criterion4_full_UX_unproven_expert_full_text_success_not_program_quality_independent_import_QA_copy_page_scrollWidth5712_at1440x1000_root_cause_unlocated_follow_latest_audit_reuse_five_adopted_images_and_exact_232docs19Blobs_packages
  - same_bearing_main_five_qualified_adoptions_and_actual_final_delivery_project_ZIPs_now_proven_232_original_document_versions_19_Blob_bytes_exact_after_independent_import_reload_reexport_follow_package_recovery_proof_not_original_four_adopted_snapshot
  - historical_20261015_ledger_lane_spent2_and_total_reserved6_46_were_stale_reconciled_to_lane_safety_upper4_20_cumulative8_46_no_unknown_or_reservation_released_counts18_new_plus17_legacy35_of36_gate_remaining1_follow_reconciliation_json
  - formal_resume_same_Goal_now_user_stopped_paused_20261016_Bailian8_Ark9_new_semantic0_image_conservative52_of52_safety_upper11_20_not_invoice_batches6_and7_finished_seven_of_ten_occupied_no_reset_no_automatic_paid_or_engineering_resume
  - current_optional_qwen_vl_max_paid_vision_review_exact_ID_and_official_price_not_reverified_no_stale_0_23_fallback_no_silent_model_change_manual_offline_path_not_blocked_follow_ledger_preparation_price_readiness
  - bearing_screenshot_already_user_authorized_20261015_073158_original_bytes_preserved_608Z_NSK_INDONESIA_visible_material_grade_and_unseen_geometry_unconfirmed_dimensions_slot_v3_official_NSK608_nominal_d8_D22_B7mm_not_user_measured_never_claim_physical_measurement_follow_plan17_12_2
  - next_version_15a42a4b52b70942_formally_started_plan17_original_RC19_final_two_rounds_and_assisted_BYOK_structural_cleanup_gaps_carried_to_final_R71_R73_R74_not_waived_not_direct_blocked_to_done
  - next_version_legacy_spent_calls_fields_8_image_5_semantic_do_not_include_all_later_lanes_conservative_upper_bound_including_planned_or_unsettled_reservations_17_image_10_semantic_not_actual_spent_count_reconcile_before_any_paid_call_old_records_unchanged
  - historical_r74_closeout_volc_adopt_export_222253_pass_spent_1_15_of_5_image_8_of_8_matrix_CI_37136575625_deploy_24a3561_origin_https_47_115_172_233_8080_paid_online_probes_0_evidence_completion-matrix-20261003-r74_not_current_completion
  - historical_r71_regression_r71f_semlive_vlm_dashscope194526_volc195600_spent_0_91_of_5_evidence_full-verification-20261003-r71_not_current_G6_or_design_proof
  - historical_boot_and_formal_entry_without_contemporaneous_queue_trace_not_all_uniquely_attributed_current_same_origin_module_refusal_mechanism_and_fix_proved_offline_follow_next_version_design_baseline_RC19_original_final_two_rounds_pending
  - sync_image_protocol_links_result_bytes_to_single_submit_envelope_no_task_id_bytes_missing_after_refresh_requires_explicit_new_action_or_manual_review_implementation_covered_by_browser_E2E_and_node_A19
  - node_domain_suite_C09_frozen_identity_fixture_aligned_browser_and_node_R52-01_waiver_removed_verified_by_PRODUCT-V2-R5.2-offline-e2e-20261003-120238_follow_V2.R5.3
  - native_latest_index_production_path_measured_same_fixture_history_assets_OCC_and_roundtrip_verified_heap_sampling_lower_bound_cold_open_not_claimed_faster_pressure_download_not_verified_follow_V2.R6.4
  - UI3_save_state_wiring_restored_and_later_pass_exists_without_before_after_code_hash_attribution_follow_V2.R3.3_and_V2.R7.1
  - public_default_paid_profile_online_closed_default_trial_closed_no_key_no_upstream_verified_by_capabilities_and_400_probes_follow_V2.R4.3_V2.R7.4
  - vlm_detection_quality_uncalibrated_do_not_infer_accuracy_from_contract_pass
  - historical_triggered_unattended_Goal_binding_retained_current_20261004_goal_get_No_active_goal_not_new_binding_or_lifecycle_change_follow_plan_2_and_plan_13
  - design_20261004_draft_text_sketches_only_no_product_code_model_calls_commits_or_deployment_R61_R62_old_evidence_not_new_UI_acceptance_follow_design_convergence_20261004
  - product_choices_confirmed_existing_models_plus_own_key_AI_review_on_demand_and_export_allowed_without_AI_deterministic_reports_hard_checks_selection_and_integrity_still_required_follow_plan_13_14
  - specification_20261004_plan14_business_contract_UI_draft_and_context_responsibility_map_written_only_no_product_code_model_calls_or_release_no_new_Goal_follow_specification_consolidation_20261004
  - historical_20261004_semantic_text_and_reference_metadata_only_reference_images_sent_false_new_vision_implementation_and_real_substep_now_follow_generation-module-20261005-formal_full_assisted_task_still_pending
  - vision_20261005_exact_one_checked_httpx2_UI_call_qwen_vl_max_real_JPEG_2239735_full_sha_saved_12_proposed_unconfirmed_analysis_source_snapshot_current_record_v3_succeeded_applied_not_complete_assisted_task_no_native_vision_project_ZIP_follow_generation-module-20261005-formal
  - vision_20261005_offline_guard_patched_wrong_httpx_default_SDK_httpx2_dummy_key_401_counter_zero_invalid_count_one_and_retain_0_23_unknown_billing_live_success_0_23_also_retained_total_reserved_1_61_image8_semantic5_total13_follow_budget-ledger
  - optional_AI_policy_requires_separating_suite_not_run_from_model_unknown_preserve_current_deterministic_reports_and_real_submission_unknown_no_auto_retry_follow_plan_14_8
  - historical_done_proofs_keep_original_scope_section14_new_acceptance_not_reassessed_recheck_affected_existing_tasks_when_implementation_authorized_no_new_task_table_follow_plan_14_10
  - implementation_batches_and_risk_based_minimal_verification_written_plan15_only_no_product_work_no_new_tasks_or_status_changes_resume_R63_requires_scope_and_actual_Goal_check
  - development_preparation_20261004_plan_r7_goal_draft_16_3_not_created_existing_binding_and_done_historical_only_reassess_affected_tasks_once_on_real_start_follow_plan_7_5_16_2
  - next_round_delivery_live_supplement_and_CI_protected_agent_merge_choices_confirmed_in_ask_preparation_does_not_execute_or_reset_budget_follow_plan_16_1
  - dependency_R62_now_R53_no_wait_for_R61_vision_completion_shared_config_existing_consumers_R43_new_vision_consumer_R61_final_G6_RC07_unchanged_scope_follow_plan_6_15
  - historical_pre_packet10_release_previous_cleanup_gap_implemented_by_current_release_transaction_but_real_Docker_HTTPS_container_page_and_same_origin_data_recovery_still_unproven_follow_latest_audit_and_R74
  - startup_20261005_user_said_start_goal_runtime_unknown_tool_goal_and_xd_goal_get_goal_create_goal_not_mounted_no_current_system_read_no_creation_no_product_work_evidence_goal-start-blocked-20261005_json_historical_binding_unchanged
  - formal_start_20261005_goal_tool_restored_user_manual_goal_active_1599c9600ae01cb7_draft_exact_match_historical_missing_tool_block_resolved_no_duplicate_creation_follow_formal-start-20261005_json
  - r43_done_20261005_settings_consumers_closed_existing_purposes_formal_entry_browser_matrix_green_verifier_only_changes_no_product_semantics_node_10_failures_preexisting_R62_harness_not_this_round_follow_config-and-credential-20261005
  - historical_formal_start_20261005_affected_acceptance_reopened_R43_R44_R53_R61_R62_R63_R71_R74_and_dependency_status_R51_R52_keep_valid_proof_no_rebuild_initial_Phase4_active_next_R43_same_version_ZIP_baseline_was_required_and_completed_before_product_write
  - formal_development_20261005_human_main_scene_once_confirm_rework_original_selection_preserved_no_AI_native_delivery_and_project_ZIP_44_documents_4_assets_byte_equal_first_TS_attempt_config_export_strict_green_other_TS_and_consumers_pending_not_final_R51_R61_R62_R63_R75_acceptance_follow_generation-module-20261005-formal
  - semantic_original_snapshot_and_same_project_late_source_change_guard_offline_UI_proven_old_request_old_source_v2_current_input_v3_stale_disposition_no_product_name_fact_applied_no_page_errors_follow_analysis-snapshot-after2_json_live_quality_and_full_assisted_task_are_separate
  - caller_strict_App_slice_zero_own_diagnostics_workspace_slice_integration_pending_session_metadata_rename_source_fix_not_yet_compiled_or_smoked_no_R75_done_follow_generation-module-20261005-formal
  - vision_preflight_transient_create_disabled_no_original_UI_phase_trace_later_green_not_root_cause_or_RC19_closure_follow_vision-ui-transient-startup-disabled_json_and_plan_7_6
  - combined_refactor_20261006_user_requests_complete_current_Goal_and_structural_refactor_plan15_4_original_Goal_unchanged_active_native_rebound_no_new_dependencies_budget_V1_sunset_or_permission_expansion
  - combined_refactor_baseline_483_source_control_files_exact_snapshot_stage_combined_refactor_2026_10_05T18_44_47_076Z_existing_project_source_native_import_open_export_2364581_bytes_no_page_errors_required_main_selection_gate_currently_blocked_do_not_claim_full_delivery_green
  - user_stop_20261006_two_continuation_agents_cancelled_nine_registered_local_services_including_headless_browser_stopped_worktree_preserved_no_goal_completion_commit_or_deployment_follow_latest_audit_stop_section
  - historical_20261006_suiteReports_create_open_failure_and_half_TS_emit_consumers_resolved_by_group_A_later_15_source_check_and_create_draft_reload_smoke_not_current_boot_root_cause_or_full_task_acceptance_follow_audit-current-state-20261007
  - combined_verification_shared_helpers_and_isolated_root_guards_gateway_probe_partially_migrated_no_final_regression_source_pins_aliases_and_live_single_submit_consumers_require_completion_before_any_live_call
  - combined_release_actual_runtime_source_image_ID_and_Caddy_hash_gate_moved_before_finalize_and_into_rollback_condition_but_latest_workflow_not_revalidated_Docker_transaction_and_previous_version_page_recovery_unproven_no_release_acceptance
  - detailed_refactor_design_20261006_target_only_owner_Interfaces_atomic_authorization_OCC_snapshot_dedup_tests_history_and_original_task_work_packages_written_no_product_edits_or_task_status_changes_no_current_goal_read_tool_available_user_stop_remains_follow_docs_product_v2_refactor_design
  - lower_model_preparation_20261006_design_r2_section10_frozen_reservation_action_preservation_lifecycle_report_ZIP_emit_release_algorithms_section11_11_internal_packets_atomic_group_A_01_03_section12_start_text_only_no_product_edits_runtime_browser_model_git_deploy_or_status_change_user_stop_R51_unchanged_follow_lower-model-preparation-20261006
  - historical_packet11_earlier_closeout_20261007_bind_zero_port_race_fix_and_individual_passes_retained_later_4_3_diag4_pass_supersedes_unverified_note_4_4_boot_after_bind_zero_and_check06_still_failed_3_5_six_reds_5_3_15_weak_oracle_settings_three_empty_proofs_and_final_two_rounds_unclosed_follow_audit-current-state-20261007
  - historical_planning_only_stop_20261007_later_superseded_by_user_explicit_full_delivery_resume_and_native_product_Goal_159d03ed410f9ff9_not_planning_Goal_binding_follow_goal-observation-final-delivery-20261007
  - historical_structural_residual_reviewAccess_setters_description_current_source_has_removed_these_do_not_repeat_owner_migration_remaining_rework_view_compile_save_confirm_sequence_to_close_under_original_structure_gate_follow_design_11_6
  - historical_R51_packet11_carried_failures_from_20261007_4_4_3_5_5_3_packet08_and_release_proof_gaps_later_convergence_has_scope_limited_passes_not_current_all_red_or_final_closure_follow_latest_audit
  - historical_delivery_batches_0_of_10_was_binding_baseline_only_implementation_and_work_regression_since_then_not_counted_accurate_used_batches_unreconciled_do_not_reset_or_infer_ten_remaining_follow_latest_audit_and_plan_stop_conditions
  - current_V1_engineering_cleanup_authorized_after_G6_types_coverage_consumer_cutover_code_and_current_format_data_recovery_R73_before_final_R71_two_rounds_not_dependent_on_unperformed_independent_human_R72
  - current_paid_increment_max_3_CNY_5_image_calls_1_image_each_2_combined_semantic_VLM_retained_baseline_image8_semantic5_total13_reserved1_61_global5_ledger_caps_image13_semantic7_total20_no_automatic_paid_calls
  - current_20261008_p11_convergence_closed_carried_reds_3_5_4_3_4_4_5_3_15_packet08_empty_proofs_four_dangling_port_refs_4_2_stale_base_and_ui2_17_boot_derive_project_write_product_fix_settings_subscribe_saves_draft_only_reload_zero_write_two_round_offline_regression_green_identical_fingerprint_follow_R51_next_packet
  - historical_20261008_harness_v2_6_2_load_stall_without_contemporaneous_socket_trace_not_uniquely_attributed_current_loopback_module_refusal_controlled_fix_20261013_does_not_make_historical_retry_or_original_final_acceptance_valid
  - current_local_env_http_proxy_127_0_0_1_7897_masked_dead_local_port_as_empty_body_502_verifiers_now_set_loopback_no_proxy_so_dead_port_surfaces_URLError_10061_not_proxy_502
  - current_4_2_restart_rebinds_same_port_and_asserts_readback_because_indexeddb_is_origin_scoped_browser_keepalive_instance_identity_not_observable_from_page_python_side_direct_probe_uses_fresh_connection_so_server_statelessness_premise_holds
  - current_20261008_p11_convergence_committed_three_slices_6b37145_keepalive_8d0320d_settings_draft_and_candidate_halt_22db254_verifiers_and_ci_then_control_plane_evidence_snapshots_pushed_origin_branch_draft_PR_4_to_main_merge_only_after_full_acceptance
  - current_20261008_user_instruction_no_local_docker_container_page_and_release_failure_classes_must_be_proven_by_remote_CD_github_actions_ubuntu_runner_local_daemon_absent_static_docker_closure_is_not_build_proof
  - current_20261008_PR4_first_remote_CI_red_13_J6_evidence_pointers_to_gitignored_evals_run_logs_R43_R44_local_guard_green_because_worktree_holds_them_fix_force_added_13_files_and_check_project_state_evidence_ok_now_warns_on_exists_but_untracked_do_not_regress
  - historical_20261008_linux_reds_4_3_04_ui3_08_35_07_have_bounded_state_wait_changes_and_later_green_4_4_05_added_diagnostics_then_green_not_independent_causal_fix_all_boot_or_timing_mechanisms_do_not_infer_closed_follow_latest_audit
  - current_20261008_CD_release_page_smoke_10_10_artifact_upload_release_json_runtime_fingerprint_json_image_txt_caddy_sha_main_runs_37723870895_success_pr_merged_03_29_23Z_follow_release_evidence
  - current_20261008_image_id_7602147e_runtime_sha256_591f2b83_caddy_sha256_e375655d_public_sha256_75243031_recorded_from_artifact_local_download_follow_evict_existing_v2_release
  - historical_20261008_run_37725600616_6a69b04_4_2_browser_interrupt_92d88c1_added_failed_details_diagnostic_not_product_causal_fix_run_37726671328_success_artifact11528238313_image31cc5ec6_runtime591f2b83_not_proof_of_later_c31213a
  - historical_two_reds_then_green_does_not_prove_context_speed_or_exclude_product_defect_4_4_05_and_3_5_diagnostic_history_keep_original_scope_no_root_cause_claim_follow_latest_audit
  - current_20261008_audit_4_2_99_observed_Locator_click_TimeoutError_runs_37727901657_37728436213_c31213a_catches_AssertionError_only_expect_to_click_race_unclosed_self_reconciled_succeeded_cause_is_inference_not_observed_local_green_not_remote_fix_proof
  - current_20261008_remote_runs_37729035340_c31213a_and_37729804595_132884d_completed_cancelled_deploy_job_zero_steps_latest_confirmed_successful_release_37726671328_92d88c1_image31cc5ec6_runtime591f2b83_live_health_ok_default_trial_closed_no_new_container_identity_read
  - current_20261008_audit_prior_todo_16_of_16_was_stop_cleanup_not_acceptance_remaining_formal_tasks_pending_preserved_C15_C17_unperformed_no_product_Goal_completion
  - current_20261008_release_probe_three_self_reds_fixed_with_mechanism_proofs_st_live_export_stale_focus_st_09_unsafe_port_st_recovery_reopen_autoproject_local_page_smoke_10_10_offline_rollback_13_13_docker_selftest_still_needs_remote_CI_validation
  - current_20261008_zoom_keyboard_evidence_real_page_zoom_125_200_layout_1152_720_no_css_zoom_1440_1366_390_key_controls_enabled_in_viewport_unoccluded_390_nav_row_scrolls_550_345_keyboard_only_tab_enter_delivery_export_30KB_sha256_cb4bceff_and_project_package_simulated_headless_isolated_profile_not_C15_C17_not_remote_https_geometry
  - current_20261008_v2_4_3_04_ci_red_state_wait_true_then_independent_sample_plan_review_with_3_of_4_succeeded_same_file_green_previous_run_zero_diff_between_runs_two_async_postconditions_sampled_separately_atomic_wait_batch_settled_plus_state_timeline_added_judgement_not_relaxed_product_side_derive_race_unconfirmed_no_rerun_for_green
  - current_20261008_local_only_offline_rollback_OR_01_unicode_decode_0xfb_once_not_reproduced_HEAD_copy_and_modified_version_13_13_treated_as_windows_bash_child_output_transient_no_mechanism_claim_no_code_masking_linux_runner_later_13_13_confirms_local_only
  - current_20261008_third_batch_ci_37758524774_4847ed9_both_jobs_success_control_plane_all_pass_including_V2_4_3_04_atomic_sampling_and_V2_1_2_10_v1_route_docker_job_build_smoke_selftest_32_32_offline_rollback_13_13_real_two_version_images_isolated_ca_tls_real_container_origin_ui_project_package_import_cross_version_rollback_same_origin_data_preserved_deploy_steps_skipped_on_pull_request_live_release_still_pending_main_push
  - current_20261008_v1_sunset_r73_inventory_product_v1_has_no_unique_purpose_v2_covers_all_but_local_folder_workspace_and_its_http_api_superseded_by_sel014_sel018_pre_v1_m_series_layer_has_v2_uncovered_purposes_local_renderers_cutout_slot_registry_data_policy_review_checklist_pilot_registry_eval_dataset_m7_workbench_no_v1_data_on_disk_no_v1_to_v2_migration_by_design_five_deletion_blockers_verify_v2_1_2_project_home_V2_1_2_10_app_server_v1_branch_check_project_state_J5_J6_superseded_v1_state_evidence_check_docs_run_py_docs_cards_and_registry_schema_gen_slot_cards_plan_section_2_3_wording_vs_16_1_follow_refactor_v1-sunset_baseline_before_any_deletion
  - current_20261008_two_ci_infra_download_timeouts_same_class_different_steps_run_37760499569_docker_build_pillow_30s_and_run_37762306228_host_uv_sync_httpcore2_mirror_tuna_retries_exhausted_not_product_regression_same_tree_passed_previous_round_fix_by_class_workflow_env_UV_HTTP_TIMEOUT_300_UV_HTTP_RETRIES_5_plus_dockerfile_env_index_lock_and_product_untouched_var_names_verified_by_uv_parse_error_if_same_class_recurs_report_as_infrastructure_not_rerun_for_green
  - current_20261008_v1_sunset_baseline_captured_stage_amz_control_v1_sunset_20261008T100045Z_head_8a9e3bd_tree_d6a937c5_tracked_3282_manifest_digest_a6269682_representative_project_zip_sha256_4007b9b1_62_members_55_documents_6_assets_import_verified_real_file_input_and_real_open_click_idb_55_docs_6_assets_revision_8_screenshot_86196277_simulated_not_c15_c17
  - audit_after_stop_20261008_system_goal_get_active_same_159d03ed410f9ff9_user_stop_remains_next_R51_blocked_not_system_paused_observations_in_latest_audit
  - audit_after_stop_20261008_main_0572b5c_run37764592110_success_docker_selftest32_32_offline13_13_live_PS10_10_fingerprint_image_ce90236c_runtime44f2e9b9_files85_finalize_rc0_previous_cleaned_not_final_Goal_completion
  - audit_after_stop_20261008_Github_main_protected_false_rules_empty_PR5_reviews_empty_reviewDecision_empty_no_independent_review_or_enforced_protection_claim
  - CORRECTED_20261009_Github_main_protection_now_ENABLED_gh_api_repos_JusticeSc_listing-kit_branches_main_protection_strict_true_required_contexts_Control-plane-and-Product-V2_plus_Docker-image-smoke-and-main-deploy_required_approving_review_count_0_enforce_admins_true_allow_force_pushes_false_restrictions_null_supersedes_prior_20261008_protected_false_line_agent_can_PR_merge_via_CI_no_human_review_required
  - current_20261009_user_full_authorization_three_asks_overspend_absorbed_raise_count_caps_and_commit_PR_CI_deploy_ledger_count_cap_now_image16_semvlm8_total24_absorbed_overspend_image14_reserved_delivery-closeout-20261009_0_64_new_reserved_total_3_8_of_5_0_money_headroom_1_84_supplement_authorization_history_updated_goal_159d03ed410f9ff9
  - current_20261009_goal_tool_get_reported_paused_then_resume_restored_active_same_goal_159d03ed410f9ff9_no_new_goal_created
  - current_20261009_rc19_bounded_capture_started_working_probe_rc19_capture_py_60_rounds_each_4_4_and_v2_1_2_first_real_failure_persists_native_boot_diagnosis_and_stops_no_600_run_pass_rate_no_green_streak_closes_rc19_per_design_11_6_2
  - audit_after_stop_20261008_r73_WIP15faa65_local_only_114_deleted_3_modified_9_snapshot_additions_add_A_breached_precise_promotion_main_branch_specific_baseline_paths_absent_blob_zip4007b9b1_manifesta6269682_verified
  - audit_after_stop_20261008_r73_data_probe_checks_identity_counts_asset_hashes_project_ZIP_only_no_document_payload_adoption_current_rework_or_delivery_ZIP_do_not_claim_full_R73_acceptance
  - current_20261017_baseline_candidate_a278044_PR13_CI_39035149699_success_verify_docker_smoke_selftest_green_v2fingerprint_a1e73bdc_old_reds_retained_both_reviews_integrated_no_merge_no_deploy
  - current_20261017_tip77c84aa_state_auth_only_CI39036915488_rerun_infra_httpx403_pending_v23507_closed_by_causal_doc_dev_residues_cleaned_walkthrough_packet08_prototype_deleted_doc_gaps_fixed_pending_push
  - current_20261017_baseline_finalized_main_9c835dc_PR13_PR14_merged_deploy_acceptance12of12_fingerprint_a1e73bdc_equal_finalize_done_previous_cleaned_CRLF_rollback_rebuild_lesson_git_archive_plus_attributes_zero_new_paid_calls
  - current_20261018_baseline_closeout_main_2c4a33a_CI39045865774_success_autodeploy_acceptance12of12_fingerprint_a1e73bdc_equal_finalize_previous_cleaned_evidence_stage_baseline_release_20261017T154245Z_artifact12105698120_human_gates_C15_C17_user_confirmed_pass_no_new_paid_calls
updated_at: '2026-10-20T01:28:24.826000Z'
```
