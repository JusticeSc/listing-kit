# V2.R7.4 最终冻结 · 完成矩阵（2026-10-03）

NOT-AUTHORITY: point-in-time completion evidence only.

- commit: `69869de`（closeout sync）+ `301040e`（closeout volc adopt-export）+ `df3e95e`（matrix），发布部署自 `69869de`。
- CI：`37134502658` 两 job 全 success（verify；deploy：image build + smoke + 远端回滚部署，head `69869de9174f5cf61219a2db42331b553cd6e398`，首次 attempt 镜像源 403，rerun 后 success，非产品失败）。
- 部署：`deployed_image=amz-listing-kit:69869de9174f5cf61219a2db42331b553cd6e398 host_port=8780 health=healthy`，`deployed_tls=https://47.115.172.233:8080 caddy_container=amz-listing-kit-tls`。
- 线上（2026-10-03，无付费调用）：`/api/health` 200 `product=v2,server_state=none`；`/` 200 29526B；`/api/v2/capabilities` 200（images contract v2.4.1, default_trial closed；review v2.5.2；suite_review v2.5.5）；空参考图 submit 400 INPUT_INVALID 未调模型；语义空输入 400 INPUT_INVALID 未调模型；`/api/anything` 404 NOT_FOUND。
- 回退：`_stage-amz-control/r74-freeze-20261003-121505/`（scope_fp `daeee042…`，deploy_fp `d0dc166e…`，pre head `ed363d3`）。
 - 预算：spent 1.15/5.0 CNY，image 8/8、semantic_vlm 3/4、total 11/12；本轮线上验证 0 付费；追加 `v2.4.5-volc-adopt-export-20261003-222253.json` VE-01→VE-08 9/9（adopt+export，0.12元）与失败留痕 `222140.json`（0.12元）。

| 条目 | 结果 | 独立证据 |
|---|---|---|
| RC01 | proven | `refactor_resume.py` 冷恢复 8阶段/26任务→V2.R7.4；Goal `1596e3da4da5b9bb` active（`goal-observation-20261003-unattended-trigger.json`）；CI control plane 全绿 |
| RC02 | proven | `refactor/ui-baseline-20261001-chrome.md/json` 七任务基线；`refactor/prototype-review-20261002.md` + 冻结 UI 合同 |
| RC03 | proven | `refactor/compare-rework-selection-ui-20261003-123202.md` + r71f `verify_v2_5_3_compare_panel` / `verify_v2_5_4_rework_loop` 全绿 |
| RC04 | proven | r71f `verify_v2_ui_2_interaction_visual` + `verify_v2_ui_3_frontend` + `verify_v2_6_4_accessibility` 全绿；线上 `/` 200 |
| RC05 | proven | r71f `check:versions`/`check:types`/`test:domain` + `check_verification.py` 44入口/40CI + verification_policy 探针全绿；`package.json/npm@11.17.0/node24.19/ts6.0.3` 锁定 |
| RC06 | proven | `refactor/session-lifecycle-20261002-r33-update.md` + `refactor/home-read-recovery-20261003.md`；r71f session_lifecycle 全绿；线上无服务器业务落盘（health `server_state=none`） |
| RC07 | proven | `refactor/effective-config-byok-20261003.md`；`config/product-v2/providers.json` 唯一解析；r71f image_gateway + two_adapters 全绿；线上 capabilities 双 image/provider 装配可见 |
| RC08 | proven | 线上 capabilities `default_trial=closed`；空输入 submit/semantic 均 400 未调模型；BYOK/出站/secret 反例由 r71f 网关与包审计覆盖 |
 | RC09 | proven | `v2.4.5-live-reference-20261003-194526-r71-dashscope2.json` 5/5（submit1/status5/result1，0.20元）+ `v2.4.5-live-reference-20261003-195600-r71-volc2.json` 5/5（同步submit1，task null，0.12元）+ `v2.4.5-volc-adopt-export-20261003-222253.json` VE-01→VE-08 9/9（同步submit1采用导出，0.12元）+ fail-closed `194502`；素材 c024b7cf CC BY 2.0 |
| RC10 | proven | `refactor/prompt-confirmation-consistency-20261003-120238.md`；r71f prompt_compiler/pre_generation_confirm/manual_edit 全绿 |
| RC11 | proven | `refactor/execution-identity-package-20261003-072854.md`；r71f generation_attempt/batch_execution/candidate_blob 全绿；Unknown 不重提由执行身份守卫覆盖 |
| RC12 | proven | r71f indexeddb/project_home/project_package/formal_entry 全绿；线上 health 无业务状态 + 静态入口可用 |
| RC13 | proven | r71f project_transfer 全绿；同一版本 ZIP 往返 hash 一致；旧格式原子拒绝（§2.3 不迁旧版） |
| RC14 | proven | r71f batch/rework/selection 全绿；partial 保留成功、单图隔离、旧候选可采用由执行/审核 Module 覆盖 |
| RC15 | proven | r71f deterministic_review + vlm_review 全绿；VLM 只分级不自动采用（`v2.5.2-review-live-20261003-194238r71-vlm.json` binding_ok，不宣称检出质量） |
 | RC16 | proven | r71f selection + delivery 全绿；`refactor/delivery-recovery-settings-ui-20261003-124930.md`；`222253.json` VE-06 select-current + VE-07 manifest按原action溯源/ZIP自洽；交付 manifest 按采用候选原 action 溯源 |
| RC17 | proven | `refactor/reference-review-20261001.md` + `refactor/verification-seams-20261002.md`；旧执行路径已删（clean cutover，无 shim/别名）；`DOCKER` 仅装 `app/server.py,app/product_v2,src,config,deploy` |
| RC18 | 本轮不适用 | C17/C15 明确后续外部门；未执行、未标 done、未冒充通过 |
| RC19 | proven | r71f 40×2 全绿 problems=0 指纹 `9825912a9a3a2384…`；boot 间歇仍 Unknown 携带未洗绿（`home-read-recovery` + 本矩阵声明） |
| RC20（工程/部署/指纹） | proven | CI deploy success + 线上 health/capabilities/静态/输入守卫（0付费）+ 回退基线/指纹；V1 删除相关本轮不适用（未删 V1） |

```json
 {"rc01_rc17_rc19":"proven","rc18":"out_of_scope_not_passed","rc20_eng_deploy_fingerprint":"proven","rc20_v1_deletion":"out_of_scope_not_done","ci_run":"37134502658","deployed_image":"amz-listing-kit:69869de9174f5cf61219a2db42331b553cd6e398","origin":"https://47.115.172.233:8080","paid_online_probes":0,"budget_spent_cny":1.15,"budget_cap_cny":5.0}
```
