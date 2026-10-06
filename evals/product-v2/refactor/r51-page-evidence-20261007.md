# V2.R5.1 收尾：页面证据闭合（包04/05/06/组A）

> NOT-AUTHORITY: point-in-time evidence。目标/任务看产品计划，当前恢复点只看 state；本文不宣布 Goal、R7.5、图文能力或发布完成。

## 页面repro证据（独立Chrome无头临时profile，离线fake，不花钱）

- 包04输入owner：`evals/product-v2/v2.r51p04-input-owner-20261006-163934.json/txt` — 6/6 PASS
  - R51P04-01 事实槽位确认保存（9槽位，3/3必需确认，待处理0项）
  - R51P04-02 推荐方案生成shot行（6张）
  - R51P04-03 刷新后输入owner恢复一致（fact_slot/suite_plan/intake版本一致）
  - R51P04-04 无模型外呼（离线fake，0个/api/v2/ POST）
  - R51P05-05 零console错误
  - R51P04-06 尺寸缺位只锁尺寸图（size_dimensions blocked=true，主图/其余false）
  - 脚本：`tools/repro_r51_p04_inputs.py`（evaluate驱动确认，含dimension_list填值分支）
- 包05预占双标签：`evals/product-v2/v2.r51p05-reserve-twotab-20261006-165748.json/txt` — 6/6 PASS
  - R51P05-01 单主图授权就绪；R51P05-02 双标签同授权只一个submit POST（posts=1）
  - R51P05-03 后到预约不另建action（两页attempt链同action，pending→submitted→succeeded一致）
  - R51P05-04 败方页结论明确无崩溃；R51P05-05 Unknown无自动重提（submit仍单POST）
  - R51P05-06 零console错误
  - 脚本：`tools/repro_r51_p05_reserve.py`
- 包06采用交付：`evals/product-v2/v2.r51p06-adopt-deliver-20261006-170325.json/txt` — 6/6 PASS
  - R51P06-01 单主图生成成功（fake）；R51P06-02 A页采用成功（selection v1 select）
  - R51P06-03 双标签采用不双写（B页按钮已禁用，单记录不覆盖）
  - R51P06-04 项目包导出非空（43747 bytes，单快照往返物）
  - R51P06-05 交付门禁文案明确（选择完整性/链完整性/报告当前性/字节hash通过，整套报告缺项可定位）
  - R51P06-06 零console错误
  - 脚本：`tools/repro_r51_p06_adopt.py`
- 组A输入确认：`evals/product-v2/v2.r51ga-group-a-20261006-170716.json/txt` — 6/6 PASS
  - R51GA-01 推荐方案4张shot行；R51GA-02 4张Prompt编译保存
  - R51GA-03 确认按钮可用；R51GA-04 确认授权落库（generation_confirm v1）
  - R51GA-05 确认/生成无错误；R51GA-06 零console错误
  - 脚本：`tools/repro_r51_confirm.py`（原打印脚本升级为断言+证据落盘，含console/网络捕获）
- 组A正式入口：`evals/product-v2/v2.1.4-formal-entry-20261006-154907.json/txt` — 12/12 PASS（既有证据，未重跑）

## 同步检查（本轮实跑）

- `npm run check:types`：通过（tsc --noEmit零诊断）
- `npm run build:frontend` + `npm run check:generated`：通过（TS→JS emit一致）
- `node --test evals/product-v2/node/*.test.mjs`：227/227通过
  - 注：`node --test <目录>`写法在本机解析为模块名会失败，须用glob到`*.test.mjs`
- `tools/check_project_state.py` + `tools/check_docs.py`：全过
- 预算：无新增付费调用（image 8/8已满，semantic/VLM 5/6，总13/14，预留1.61/5元）；全部fake离线

## 剩余缺口（非本轮）

- R5.2第二真实Adapter、R5.3能力Prompt、R6.x图文/UI、R7.1最终两轮、R7.4发布、真人C15/C17均未动
- fake图64px过不了交付长边1000px门：包06证的是“拒收文案明确”，不证交付成功
- 本报告只闭合R5.1页面证据缺口；R5.1任务状态变更以state为准
