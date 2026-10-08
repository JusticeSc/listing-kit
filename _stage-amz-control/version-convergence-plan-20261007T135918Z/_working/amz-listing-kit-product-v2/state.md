# Product V2 定向重构执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state
> 只保存进度、证据、阻塞/未知与下一动作；目标和任务定义只在 `docs/product-v2-refactor-plan.md`。
> prepared 是未绑定新 Goal 的本地准备态，不是系统 paused。旧读数与完成记录只见 superseded 基线。
> 2026-10-06用户明确指令“按照计划开发吧”，解除前述停工门并恢复V2.R5.1受限施工。恢复核对：Goal原文仍计划§2.1 sha6677a6803003f0894dd522bdd7102b53ca30c866532ff48fdc79e4b148d7c495；state守卫与文档守卫通过；预算image8/8已满不新增、semantic/VLM5/6、总13/14、预留1.61/5元；事前快照_resume-r51-2026-10-06T03-51-56-463Z；S0基线check:types与check:generated均红、suiteReports等未声明仍被引用。按§15/设计§11从组A开始，不另立任务。组A包01-03已闭合：产物集合/owner消费者/恢复生命周期迁移完成，check:types零诊断、check:generated 9/9、node 226/226、页面repro与V2.1.4正式入口通过；证据evals/product-v2/refactor/r51-group-a-20261006.json；仍V2.R5.1 active，下一包按设计§11.2包04起。
2026-10-07包07（按任务拆视图）闭合：四个视图落地（`ui/delivery-view.ts` e4b35c7、`ui/input-view.ts` 5d2997f、`ui/generation-view.ts` 53fb17d、`ui/compare-view.ts` 04e3398；workspace.js 5686→1598行，含 ea541e7 死代码清扫），视图只持DOM/订阅/命令，装配与生命周期留workspace；每切片真跑闸门（node --check/build/check:types/check:generated/node单测227）与页面级证据（`repro_r51_p04_inputs`/`p05_reserve`/`p06_adopt` 各6/6、`verify_v2_6_2_delivery` 12/13与改动前基线逐字节同结果、`verify_v2_2_3`/`verify_v2_3_2` 全过），证据 r51-packet-07-views-20261007.md。既有验证器缺陷(5_5 static_url/3_5基线即挂/5_3 缺shared属性)非本包引入，归包09。下一包：设计§11.2包08（图文/可选AI与设置闭环）。真跑修好的验证器还发现四项既有产品侧红（非包07引入，已用包07前基线 bbf3509 + 同版本脚本逐条对照）：3_5/3_6/3_4 走查中 `#prompt-editor` 在 suite-seed→generate 后不可见（3_5 静默挂住）、5_3-15 `#compare-jump` 点击后不落 first_shot、5_5-04/09 整套AI复核 POST 400（请求侧 `suiteRequest` 在已采用集合为空时仍外发，服务端 `images` 最小1张校验正确，拒绝形状 input_rejected/INPUT_INVALID）。这些归包08/产品侧，修前不当成通过、不重跑洗绿。包07 验证网修复见 commit 7d995ce。
2026-10-07包08首片（设置三用途有效配置贯通 + semantic 看图档真实图片字节/来源）闭合：commit 3961d24（15 文件，已 push）。`config/product-v2/providers.json` 新增 test-only 替身 `fake-vision-semantic`（role=semantic / adapter=`v2_fake_vision_semantic` / reference_images:true，仅在显式注入接缝的 provider_choices 出现），`src/providers/v2_fake_vision_semantic.py` 补 `capabilities().configured=true`（此前面板误报缺凭据），`v2_registry.py` 接线，新验证器 `tools/verify_v2_packet08_settings_vision.py` 12/12 PASS exit 0；证据 evals/product-v2/refactor/packet08-settings-semantic-20261007T032916Z.md(+.json)。真跑要点：替身实收 exactly 1 张真实图片 `sha256=7af577c6699c88fb4d28c4ea992237dd9dbd17026beec0b37b2ac18351d34419`（==上传原图，byte_size=3126），页面 gate/result 与之一致，`semantic_analysis` 记录 `reference_images_sent=true`+provenance sha 且不含 data_base64；秘密探针 key 在 DOM/响应/IndexedDB/console/请求头/磁盘 grep 全部无命中；旧格式包导入拒绝且不伪造迁移；七闸门全绿（node --check、build:frontend、check:types、check:generated、node --test 227/227、check_project_state、check_docs --no-run）。`#analyze-run` 后 slot-list 超时根因判定为验证器等待/阶段面板选择缺陷（点击有效、替身已收图），非产品缺陷，未改产品凑绿。受阻如实标注：真图文理解消费者（R6.1 后续批次）、R5.2 第二 Adapter、R5.3 Prompt·确认·能力一致均未解除，本片只走 fake 替身正式接缝，无真实上游、无付费调用。下一片：包08 其余三项（adoption 显式单图AI、delivery 显式整套AI+manifest/ack、旧调用/复制schema同包删除）。
2026-10-07包08第二片（adoption 显式单图AI按需）闭合：commit f199726、f50ec77（已 push）。产品修复三项：D1 `selection-adoption` 复核请求来源链改为「从后往前找与候选身份一致的 succeeded Attempt」（此前同 action_id 多版本链误命中 pending_submit → 显式复核零外发）；D2 `confirmedFacts` 收窄为 `{label,value}`（此前超出 schema → 服务端 `input_rejected/INPUT_INVALID` 400）；D3 adoption changed 时补刷 `generationView.renderAttempts()`（修 5_2 未复核行不重绘）。语义落地：`reviewStatusOf` 投影 not_reviewed/reviewed/unknown，未发起显示「未复核(未运行)」且不阻断人工采用、不进风险 ack 门；生成/查看/切换/采用均不触发复核，只在用户显式点击时外发。验证：新验证器 `tools/verify_v2_packet08_adoption_ai.py` 11/11 PASS exit 0；回归 `verify_v2_5_2_vlm_review` 19/19 exit 0；`verify_v2_5_5_suite_review` 由主代理独立重跑（label main-verify）**全绿 exit 0**——更正本文件上一段：5_5 的 -04/-09 不是既有失败，而是 D2 那个真实产品缺陷（facts 契约导致 400 空 images），已在本片修复；七闸门全绿（含 node --test 227/227、check_project_state、check_docs --no-run）。仍红且判为既有产品缺陷、未修（超本片边界）：`verify_v2_5_4_*` 双击返工后 `#rework-panel` 仍 visible（根因：`submitRework` 把 Prompt 版本 v2 当作 `generation_confirm/rework:shot` 的 expectedVersion 传，当前为 0 → REVISION_CONFLICT；包07 前基线同样复现，非包07/08 引入）。仍未定性：3_4/3_6 `#prompt-editor` 在 suite-seed→generate 后不可见、5_3-15 `#compare-jump` 点击后不落 first_shot。
2026-10-07包08残余红清理轮（主代理接管子代理作业）：验证网缺陷 3_5「零输出挂住」根因=缺 `threading.Thread(target=server.serve_forever, daemon=True).start()`（`create_product_v2_server` 只建不启动），异常又被 `finally: server.shutdown()` 永久阻塞吞掉；`faulthandler.dump_traceback_later` 定位在 socketserver.py:255 shutdown ← 脚本 610 行，已修（与 3_6:447 同形），全库同类审计无其它缺口。3_4/3_6/5_3 由子代理只改到达路径，主代理按 check-ID 集合与断言条数复核（11/11、13/13、16/16、18/18，集合完全相同）确认未删检查未放宽，唯一例外是 V2.5.3-15 期望由「绝对第一张」改为「按钮承诺的 targetShot」（收窄待按 nextPendingShotId 合同恢复确定性）。产品改动：`ui/compare-view`(showAttemptError 返工 unknown 如实提示)+`ui/generation-view`(确认后 deriveState)+`workspace.js` 接线 → `verify_v2_5_4_rework_loop` 转绿。主代理自跑 3_4/3_6/5_3/5_4 EXIT=0，七闸门全 0（node --test 227/227）。仍未决：3_5 第二次确认步的最终根因已钉死=**产品语义就是禁用这次确认**（确认单投影"本次明确发送 0 张"，4 张图已在 -07 成功提交过，按"已有成功不自动重提"保护不再外发；与 3_6-12"如实停在未确认态"同一合同），故 `V2.3.5-10` 的"再确认写 v2 append-only"在该走查路径上是**过期场景**，需重新设计"本次确有可发送任务"的路径（本轮不猜语义、不改期望凑绿）；该步已改为有界等到可用+显式期望（快速失败、原因明确）。`-09` 由写死 `version == 2` 改为相对前进 `>= 2`（自动准备+显式重准备会让同图前进多次，实测 shot_main_clean 到 v3）。V2.5.3-15 收紧待做（按 nextPendingShotId 合同算具体落点）。证据 evals/product-v2/refactor/packet08-residual-reds-20261007.md；清理 tools/probe_p08_residual_reds.py 与 23 个 _working_p08_*.log。
2026-10-07包08第四片 + 包09两片（子代理作业，主代理复核并提交/推送）：包08第四片 `2d06858` 删 generation 侧单图复核回调环残留（`candidateReviewRequest`/`reviewRunner` setter+builder、`workspace.js` 占位补线、测试替身 3 处），删前全库引用搜索确认仅命中已死路径（复核唯一入口仍为 adoption），闸门全绿且六验证器绿（settings_vision 12/12、adoption_ai 11/11、delivery_ai 16/16、vlm_review 19/19、suite_review 全绿、6_2 delivery 全绿）。包09第一片 `c4a09c4` 验证器迁移：删 5 组文案/计数钉死断言（如 `checks.length === 7`、`REVIEW_SEVERITIES.length === 5`、凭据词表 join、进度文案子串），换 10 组行为断言（相对顺序/兜底/越权拒绝等），保留 4 类不可替代守卫（`tools/**` 零改动），node --test 用例数 227→227 不变，七闸门 0。包09第二片 `c8095cd` 历史材料归档与 INDEX 分类：66 份受管 md 分为现役 6/生成 8/草案 19/历史 32，INDEX 65 行引用零断链，**零搬迁**（现役文档仍有效引用 7 组历史/草案路径，物理归档须另立任务先消引用），七闸门 0。下一步：包10（release 脚本/probe 两 image 版本回退证据、workflow rollback 条件 + Docker 实际闭包）→ 包11（两轮完整离线回归、范围匹配 RC 矩阵与既有环境发布、R7.5/R5.1 状态收口）。
2026-10-07包11首片（两轮完整离线回归 34 项 ×2 串行）：真绿 22 / 已知过期 1（3_5 -10）/ flake 1（4_2 r1 红 r2 绿）/ 真红 10（1_1、4_1-23、4_3、4_4、5_1、6_1、6_4、r5_2、ui_2、ui_3），证据 `evals/product-v2/refactor/packet11-regression-rounds-20261007T101243Z.md`；两轮 p11r1/p11r2 快照提交 `f16f3c1`，逐项修复提交 `fa5b34a`。

2026-10-07包11第二片续（用户第二次要求收尾）：**4_3 已转绿并提交 `0d681a5`**——产品修复：`runBatch` 结束不再把 batchState 置 null，保留 active=false 快照使 ui-contract §3「已停止新增」状态持续可见（实测修复前 `#batch-progress` 从未出现停止提示，被随后 renderAttempts 文案覆盖）；`pollActiveAttempts` 改用 live 快照，核对语义不变。验证器修复三处：`MarkerImageProvider.submit` 未把场景写入 `mode["tasks"]`（status() 只读该表）使"按标记决定失败"永远退化成成功（-05/-06/-07/-08 不可达）；`-09` 停止提示元素由 `#attempt-status` 改为合同渲染点 `#batch-progress`；三处 shared 符号 `PNG_bytes`→`png_bytes`；`wait_states` 超时改为报真实观测。实跑 rc=0（15/15，`v2.4.3-batch-suite-20261007-202416-diag4.json`），check:types/check:generated/node 227 全绿。
**4_4 未闭合（明确未验证）**：已按实测形状重写——首批摘要范围=未提交全集（4 张，ui-contract §4.6「默认是未提交的图」；产品无"单图摘要开关"），逐图场景改为 add_shots 新图（新图是当时唯一未提交图，摘要天然 1 张）；配额/整套批次同法；-08 改为 2 张剩余图的真批次。产品修复一处：候选取回失败原因此前只对配额记录 `fetchBlocked`，其它失败原因被丢弃 → 新增 `BatchRunState.fetchNotice` 并在 renderBatch 提示区展示（ui-contract §2.6 失败要说明发生了什么/下一步），成功保存即清空。**未跑出绿**：取回失败场景实测"只失败一次"会被批次自动重试掩盖（progress 已成功 5/待提交 0），已改为"解除前持续失败"；末次运行在 check06 点击前批次仍 active（按钮禁用）已加 `wait_batch_idle`，但**这些改动都没有得到一次 rc=0 的完整运行**。
**环境级瞬态（已刻画，未定根因）**：Windows 回环上偶发**同源**模块请求 `net::ERR_CONNECTION_REFUSED`（实测 7 次运行 4 次命中；留证 URL 如 `http://127.0.0.1:<port>/domain/brief.js`，端口即页面自身 origin，事后裸连接可达 → 服务器仍监听），导致 workspace 初始化失败、`#new-project-name` 保持 disabled。排除项：40 并发裸连接（queue=5）、12 次全新加载、强制端口复用 10 次、CPU 争用 ×2（queue=5/128）**均无法复现**。产品自检 `app/product_v2_server.py` 已有同现象注释（"连续起停回环端口时极少数连接在读响应时被重置"）并只做一次连接级重试。处置：4_4 新增 `load_page()` 启动门 + 一次记录式重试（`ui.boot_retries` 入证据）；根因仍未知，按计划记为环境阻断而非产品缺陷。
**已落盘**：`0d681a5`（4_3 转绿，已实测）、`e7ce5c5`（4_4 重写 + 取回失败提示，**未验证**）已推送 `origin/feat/v2-r51-packet-05`；工作区干净（`git status --short` 空），临时探针已删除。本轮未部署、未开 PR、未跑两轮完整回归。
**恢复点**：`uv run --locked python tools/verify_v2_4_4_candidate_blob.py`（先看 boot_retries/check06 hint 断言）；随后 3_5 的 `-03/-05/-06/-07/-08/-11` 与 5_3 `-15`，再跑两轮 34 项完整回归。
2026-10-07包11第二片（用户要求收尾，进行中未闭合）：逐项修复与机制钉死，证据 `evals/product-v2/refactor/packet11-fix-reds-20261007T184000Z.md`（含 §7 新增机制）。**已实跑转绿**：5_1、4_1、1_1、ui_2、ui_3（`fa5b34a`，全部 rc=0）；`6_1`/`6_4`（rc=0，证据 `v2.6.1-selection-20261007-193953final.json` / `v2.6.4-a11y-20261007-194101-final.json`）；`r5_2`（rc=0，`PRODUCT-V2-R5.2-offline-e2e-20261007-190944.json`；`R53-E03` 旧期望"全部旧 Prompt 过期"与 plan §439/§870、ui-contract:39/167-176 的"自动准备+历史保留"相反，已按契约重写为"新版本按新依据+旧版本逐字保留+零外呼+不自动重提"）。**控制面缺口已修**：packet08 三件套此前未登记导致 CI `check_verification` 红，现登记 `category=browser, ci=true` 并接入 CI verify job（`check_verification` PASS 50 入口/44 CI 模式、`verification_policy` PASS 14 组），其机器证据按 `.gitignore` 精确忽略。**基础设施根因已刻画并修**：Windows 下 `free_port()` 的 TOCTOU 端口抢占（探针 `_working/_probe_port_race.py` 实测"同端口可被第二个服务器静默绑定成功"）是 `ERR_CONNECTION_REFUSED` / `gate=unavailable(Error)` / boot 卡死类假红的成因；22 个验证器已改为**产品服务器绑定 0 号端口并从 `server.server_address[1]` 读回**（仅 1_4/2_3 的子进程端口保留 `free_port()` 并加注释）。**未闭合（明确未验证）**：4_3（已修 `-09` 停止用例"不能走消费门"机制与阶段导航，未复跑）、4_4（已修 prep 阶段导航与批次语义重写，未复跑）、3_5（子代理改到一半：`-03/-05/-06/-07/-08/-11` 仍红；已钉死机制=进入 generate 阶段自动准备使"4 张缺 Prompt 被阻断"期望过期、`CONFIRM_PROBE` 的 sheet 口径≠UI 意图口径，应改断 UI DOM）、5_3 `-15` 收紧未实施；**两轮完整回归在以上修复后未重跑**，故包11 尚未闭合、不得声称通过。非浏览器十门在收尾时全绿（node --check/check:types/check:generated/test:domain 227、check_docs、check_project_state、project_state 64 向、docs_index 15 向、check_verification、verification_policy），26 个被改验证器全部 `py_compile` 通过。**恢复点**：先跑 4_3/4_4/3_5 单跑复验（串行，避免端口抢占），再按 `packet11-regression-rounds-20261007T101243Z.md` §2 清单跑两轮 34 项，最后 RC 矩阵与既有环境发布。
2026-10-07包10两片闭合（子代理作业，主代理复核并提交/推送）：第一片 `df66fb0` 发布事务失败路径回退证据：新增 `tools/release_transaction_probe.py --offline-rollback`（真实脚本 + 最小 stage 执行器）OR-00~OR-07 8/8 PASS，`deploy→finalize 晚期失败(exit 1，previous/journal/备份保留)→rollback(exit 1)` 回到旧版本；两版本指纹确实不同（old `sha256:842efd18…` / new `sha256:fdb8ff08…`，marker b→a）；stale finalize exit 4；静态审计确认现有流程**无**"healthy 前提前删 previous"缺口（`rm previous` 仅在 finalize 全验收后，脏恢复点 deploy 直接 exit 1）；附 `.gitattributes` `*.sh eol=lf` 修工作树 CRLF 阻断（blob 本就 LF，未入 commit）。第二片 `92efb32` 在 `ci-cd.yml` 新增 `Check rollback truth table` step（每次 main push 真跑 Python 断言：回滚门覆盖 4 类失败、exit 4 永不进门、previous 只由 finalize 删、build→smoke 无 `docker rm`）；Docker 闭包为**静态核对**（本机无 docker daemon，如实声明未声称构建通过）：1837 跟踪文件中镜像内 148、运行时必需 31 项零缺失、`.ts`/V1/`verification.json` 正确排除、前端语句级 import 零悬空。两片七闸门全 0。**未决**：真实 `docker build`+smoke、真实容器/TLS/HTTPS 回退须在 Linux CI/获批环境跑（精确阻断，非绿灯替代）；浏览器数据恢复（同 origin ZIP 导入/Blob/历史）须另证，不以容器回滚冒充（§7.4）。

```yaml
state_schema: amz-project-state/v2
task_id: amz-listing-kit-product-v2-refactor
status: active
goal_binding: required
goal_id: "1599c9600ae01cb7"
goal_pending_reason: null
goal_binding_evidence: evals/product-v2/refactor/goal-observation-20261006-combined-refactor.json
system_goal_observed_status: active
system_goal_observed_at: '2026-10-05T18:44:51.649Z'
plan_ref: docs/product-v2-refactor-plan.md
latest_audit: evals/product-v2/refactor/generation-module-20261005-formal.md
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
    status: done
    evidence:
    - evals/product-v2/refactor/effective-config-byok-20261003.md
    - evals/product-v2/refactor/execution-identity-package-20261003-072854.md
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/refactor/formal-start-20261005.json
  '5':
    status: active
    evidence:
    - evals/product-v2/refactor/generation-module-20261003-084705.md
    - evals/product-v2/refactor/two-image-adapters-20261003-094600.md
    - evals/product-v2/refactor/prompt-confirmation-consistency-20261003-120238.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-154254.json
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
    - app/product_v2/session.js
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
  V2.R5.1:
    status: active
    evidence:
    - evals/product-v2/refactor/generation-module-20261003-084705.md
    - app/product_v2/generation.js
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
blockers: []
unknowns:
  - historical_r74_closeout_volc_adopt_export_222253_pass_spent_1_15_of_5_image_8_of_8_matrix_CI_37136575625_deploy_24a3561_origin_https_47_115_172_233_8080_paid_online_probes_0_evidence_completion-matrix-20261003-r74_not_current_completion
  - historical_r71_regression_r71f_semlive_vlm_dashscope194526_volc195600_spent_0_91_of_5_evidence_full-verification-20261003-r71_not_current_G6_or_design_proof
  - historical_boot_and_formal_entry_intermittent_trigger_unproven_controlled_home_read_failure_and_readiness_windows_fixed_diagnostics_now_capture_stage_UI_and_independent_DB_follow_V2.R1.2_V2.R3.3_V2.R7.1_RC19
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
  - release_rollback_gap_previous_container_removed_before_HTTPS_page_acceptance_not_fixed_in_preparation_R74_must_implement_plan_7_7
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
  - combined_workspace_last_actual_create_open_failed_suiteReports_is_not_defined_project_saved_in_IDB_but_view_hidden_new_strict_prompts_authorization_selection_adoption_review_delivery_TS_sources_not_compiled_or_integrated_no_current_runtime_pass_claim
  - combined_verification_shared_helpers_and_isolated_root_guards_gateway_probe_partially_migrated_no_final_regression_source_pins_aliases_and_live_single_submit_consumers_require_completion_before_any_live_call
  - combined_release_actual_runtime_source_image_ID_and_Caddy_hash_gate_moved_before_finalize_and_into_rollback_condition_but_latest_workflow_not_revalidated_Docker_transaction_and_previous_version_page_recovery_unproven_no_release_acceptance
  - detailed_refactor_design_20261006_target_only_owner_Interfaces_atomic_authorization_OCC_snapshot_dedup_tests_history_and_original_task_work_packages_written_no_product_edits_or_task_status_changes_no_current_goal_read_tool_available_user_stop_remains_follow_docs_product_v2_refactor_design
  - lower_model_preparation_20261006_design_r2_section10_frozen_reservation_action_preservation_lifecycle_report_ZIP_emit_release_algorithms_section11_11_internal_packets_atomic_group_A_01_03_section12_start_text_only_no_product_edits_runtime_browser_model_git_deploy_or_status_change_user_stop_R51_unchanged_follow_lower-model-preparation-20261006
  - packet11_second_slice_closeout_20261007_user_stop_verified_green_5_1_4_1_1_1_ui_2_ui_3_6_1_6_4_r5_2_and_control_plane_verification_registry_fix_and_22_verifier_bind_zero_port_TOCTOU_infra_fix_but_4_3_4_4_3_5_and_5_3_15_unverified_after_edits_two_round_full_regression_not_rerun_so_packet11_not_closed_no_acceptance_claim_evidence_packet11-fix-reds-20261007T184000Z
updated_at: '2026-10-07T19:55:00+08:00'
```
