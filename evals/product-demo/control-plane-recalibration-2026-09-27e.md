# v1.22 控制面校准与第三版实施重基线（2026-09-27）

> EVIDENCE-SNAPSHOT: control-plane-audit · NOT-AUTHORITY  
> 本文件只记录本次观察、裁定依据和验证读数。产品目标、架构、任务与依赖只以
> `docs/product-demo-goal-and-implementation-plan.md` 为准；当前进度只以
> `_working/amz-listing-kit-product-demo/state.md` 为准。

## 1. 触发与结论

产品发起人要求重新审视此前设计。复核空白态、方案态、审核态、前端代码、Mock service、v1.21
合同与 D2.R1d 自审后，结论为：D2.R1d/e 并非“还需润色”，而是第二次把工程测试台误认成产品。
最早断点在 `ProductInput → ProductBrief → PlanDraft / PromptPreview` 的因果链缺失；CSS、按钮措辞和
浏览器轨迹都在其后。

本轮没有修改 §2 Goal objective。Aster 仍是最终受控验收夹具；第三版新增两商品对照，仅用于跑红
固定输出和商品泄漏，不构成跨品类质量证明。

## 2. 直接证据

| 编号 | 合同要求 | 当前实现 | 用户后果 | 裁定 |
|---|---|---|---|---|
| E1 | 当前阶段主导；未来阶段不以大片空态出现 | `styles.css` 固定 `18rem / canvas / 23rem` 三栏；空白态仍出现候选、核对与交付 | 用户一开始就要理解尚不存在的对象 | D2.R1d 渐进式声明未落地 |
| E2 | 普通路径只处理具体异常 | `renderFactReview` 对每张图渲染完整 F1–F8，并以全部通过作为选择门 | 运营被迫扮演检查表标注员 | 人机责任分配违约 |
| E3 | 商品资料产生 1..N 张推荐方案 | `createRecommendedPlan` 不使用名称、参考图和卖点推导 Shot，直接 `SHOT_DEFINITIONS.map` | “推荐”是固定剧本 | 产品核心能力被 Mock 掉 |
| E4 | Prompt 由当前商品事实、卖点、平台、Style 和 Shot 编译 | `PRODUCT_LOCK`、negative prompt、四个 scene 全是 Aster 保温杯常量 | 换商品仍得到保温杯语义 | 输入没有驱动输出 |
| E5 | 自审应发现合同→实现偏差 | D2.R1d 自审声明“没有永久三栏、普通路径不打表”，浏览器证据与代码相反 | 自审绿灯无法证明产品正确 | 验收缺少反向探针 |

相关位置：

- `docs/product-demo-goal-and-implementation-plan.md` v1.21 §4.7.7–§4.7.8；
- `app/static/styles.css` `.workbench`；
- `app/static/workbench.js::renderFactReview`；
- `app/static/mock-service.js` 的 `FACTS`、`PRODUCT_LOCK`、`SHOT_DEFINITIONS`、
  `createRecommendedPlan`；
- `evals/product-demo/d2-r1e/blank-state-2026-09-27.png`、`loop-plan-2026-09-27.png`、
  `loop-review-2026-09-27.png`。

## 3. 根因，而非表面症状

1. **把状态机可跑通当成业务模型成立。** 浏览器脚本验证按钮和状态，没有验证输入变化是否造成合理输出变化。
2. **夹具泄漏为领域模型。** Aster facts、Shot 和 Prompt 从样例数据上移成全局常量。
3. **Mock 边界画错。** 本应只替代模型执行、等待、付费和写盘，却连商品理解、方案推荐和 Prompt 增强一起替代成固定答案。
4. **内部控制对象侵占用户界面。** 为证明事实核对存在，把 F1–F8 直接交给运营执行。
5. **自审只有正向覆盖，没有反向可证伪性。** “页面存在、轨迹通过”无法抓住永久三栏、固定四图或 Aster 泄漏。

## 4. 控制面处置

- 产品计划升为 v1.22，增加 §1.20、§4.7.9、D2.R1g/h/i 与 §6.11.3B；详细实施计划只在该文件维护。
- D2.R1d/e/f 在 current state 标为 `superseded`；历史产物不删除、不改写。
- 新主链：`D2.R1 → D2.R1g → D2.R1h → D2.R1i → D2.R2 → D2.R3`。
- 三份机器契约仅把 `plan_version` 从 v1.21 同步到 v1.22，合同语义不改。
- 系统 Goal 于 2026-09-27T23:31:17+08:00 最后一次直读为 `paused`；state 同步为 `paused`，Phase 2 为
  `blocked`，唯一恢复后动作是 `D2.R1g`。本轮不擅自恢复系统 Goal。

## 5. 外部快照与哈希

修改前快照：
`E:\workbuddy_workspace\2026-09-20-16-38-19\_stage-amz-control\recalibration-v122-20260927-2322\`

| 文件 | 修改前 SHA-256 | 修改后 SHA-256 |
|---|---|---|
| 产品计划 | `6771F6EA3F0F9C735ECF9C267AF72673B8EB5321CEADEA78CAD6BE41F99DF0EA` | `6418B537315095AA0D159B30B0E05BC6EBE94017AD9169758F46907FE9B87D39` |
| docs/INDEX.md | `9725634EA9ACE1446F02DE13A74F88A2883870D893B7640849C0938339E7553B` | `C38C5EA252BC76BAF808324EC0063747A70695A4ACD0A6B0A1D364A0091708CA` |
| current state | `1EBDEE5912C2A535C83AEFDC46A1C531AD87DA519C8B79178E4DE7789A6AFCDB` | `F2B90E074C880F1E51736BBF6BFF40015DC36FB3A7AF8F623F2E258503C98C44` |
| authority_matrix.json | `201DB50AC2C32554301DA9DB55245949112A1CD93B42ADE6E964B92A03421E70` | `D7EE15D55818FED9C85F816ADAC376D7C58434A97A7A6B0853ACF4E5BDA25EA3` |
| state_vocabulary.json | `0C288BB4456DD078CCB747E49C51D281EE1E1CDFA9063E20ED67A11F125A71BF` | `EFFA095A65B1F2BF5C8F93E35DB1367FBAE0CFD65B71F436FE512FCC7ECCF0D6` |
| processing_contracts.json | `B38076674A6CADEADEE4F63056B2F143393509CBDF08215747B9F242F15C3EBB` | `94988E913C64B6B00840FF79D9BCA81D1B2E779A6CF1E8C78BE667AE0E40013D` |

## 6. 验证读数

| 验证 | 新鲜读数 | 能证明 | 不能证明 |
|---|---|---|---|
| `tools/check_project_state.py` | 退出码 0，J0–J10 全过 | state 可解析、ID/依赖/证据/next action/生命周期镜像一致 | 新计划业务正确或系统 Goal 已恢复 |
| `tools/check_docs.py --no-run` | 退出码 0；31/31 文档登记一致 | 权威路由唯一、登记双向一致 | 文档命令可执行 |
| `tools/check_docs.py` | 退出码 0；真实执行 11 条去重命令，1 条付费形式自动加 `--dry-run` | 文档中的安全命令当前可执行，数字/登记一致 | 付费模型真实效果或第三版产品成立 |
| `demo/contract/contract_tools.py --check` | 退出码 0；13 合同、27 权威项和状态词汇与 v1.22 对齐 | 机器契约未随计划版本静默漂移 | FE3 新业务合同已实现 |
| `demo/contract/contract_tools.py --self-test` | 退出码 0；18/18 变异被正确抓住 | 合同守卫具备既定反向能力 | FE3-00 新增五类产品反向探针已完成 |
| `evals/probes/project_state.py` | 退出码 0；19/19 正反向符合预期并逐字节恢复 state | J0–J10 守卫不是恒绿，探针无残留 | 系统 Goal 工具状态会被仓库脚本自动读取 |

所有检查均为 2026-09-27 本轮修改后的读数。它们只证明控制面内部一致和既有守卫有效，不能把
`D2.R1g/h/i` 写成已完成。

## 7. 尚未证明

- D2.R1g 尚未执行，因果 schema、两商品黄金输出、线框和视觉稿仍未产出；
- D2.R1h 尚未执行，当前正式入口仍是被否定的 v1.21 页面；
- 系统 Goal 仍为 paused，正式开发尚未恢复；
- 产品发起人和首次未参与者都尚未走查第三版；
- 本轮零模型调用，不能增加任何 qwen-image-3.0 能力声明。
