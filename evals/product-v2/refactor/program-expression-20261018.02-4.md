<!-- 拆分件 02/05 · 父文档 evals/product-v2/refactor/program-expression-20261018.md -->
# 4. 仍然缺什么（不得当成已解决）
[返回 program-expression-20261018.md](program-expression-20261018.md)

## 4. 仍然缺什么（不得当成已解决）

1. **英文文案来源**。本轮印字只能逐字取自已确认事实值，所以对英文站点仍会触发 `ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE` 警告（信息图新稿的 `new_warnings` 里就有）。要真正落到英文，需要「AI 提议 + 人工确认」生成新文案、或用户在事实槽里先确认英文原文——两者都还没做。
2. **单图展示覆盖的界面入口**。域层的 `shot_spec.presentation` 覆盖与继承已经实现并有回归（P14），但页面上只有整套共用的那两组控件；因此确认单的修复文案已改成「整套共用」，不再承诺一个界面上不存在的单独覆盖入口。
3. **视角（viewpoint）未开放**。设计里的 `viewpoint` 字段没有实现：本轮统一固定为「沿用商品依据里可见的视角，不虚构背面/内部/未见部件」，因为「可支持某视角的商品依据」还没有可核验的数据模型。已在设计 §13.4 记明实施状态。
4. **像素质量**。本证据只证明提示词与请求消费；模型是否给出足够好的图，属于工单第 6 条，需要另一次真实调用与人工看图，本轮不涉及。
5. **页面级 E2E**。`visual_brief` 与普通选择已经进入域编译，但「用户在页面上点选 → 页面显示 → 提交给模型」的整段证据要等 UI 切片合入后补（同一工单第 3 条）→ **本次已补，见 §6.2**。
6. **「来源一致」只到版本级**。域层校验的是「这条文案指向的槽位 + 版本与依据一致」，不校验文案字面是否等于该事实值（设计允许「用户自己写的文案」这一扩展点，P03 就是这个形态）。页面当前只能从事实值逐字生成候选，所以正常使用不受影响；但**导入或手工改过的项目数据可以带一条与来源事实不一致的文案**，编译门看不出来。等「AI 提议 + 人工确认」落地时这条要一起收口（要么限定字面必须来自事实值/元素，要么显式标记为用户自撰）。
7. **尺寸数值还不能逐字上图**。结构化尺寸（`dimension_list`）既不在印字候选里，`factTexts` 也不会把它当文本印出（否则就是 `[object Object]`），所以尺寸图目前拿不到任何可引用的数值。本轮已把尺寸用途的画面简报改成不邀请编造（「数值与单位只允许逐字使用已确认尺寸；取不到可逐字引用的数值时就不标数字，不编造数字与单位」），但**「尺寸标注」这个能力本身仍未实现**：要么给结构化尺寸一个可逐字上图的表示（如 `12 cm`），要么在用户绑了尺寸却无可印数值时给出明确提示。属下一步产品决定，本轮只保证提示词不因此自相矛盾。

---

## 5. 复现方式（零收费）

```bash
cd amz-listing-kit-issue9-expression
npm run build:frontend-node                      # 只编译 TS → build/frontend-node
# 真实项目包解包（Windows 自带 tar 可解 zip）
tar -xf _stage-amz-control/asset-continuation-20261008T054352Z/data/manual-project.zip \
    -C _stage-amz-control/issue9-expression-20261018T080410Z/real-project
node _stage-amz-control/issue9-expression-20261018T080410Z/program-expression-before-after.mjs
npm run test:domain                              # 域套件（含 P 系列：印字/版面决定）
```

对照脚本只做三件事：读真实项目文档 → 调域层 `buildProductBrief` / `emptyShotSpecFromShot` / `compilePrompt` → 打印并写出 JSON 证据。**未调用任何模型、未写入任何存储、未联网**。项目记录里的 `fake-qwen-image` 档不是产品档，本次使用同型号的有效图像档（数值取现有测试夹具），已在 JSON 的 `provider_profile_note` 注明。

---

## 6. 验证证据（本轮，零收费）

| 类别 | 内容 | 结果 |
|---|---|---|
| 域/前端单测 | `node --test evals/product-v2/node/*.test.mjs`（含 P 系列印字/版面/展示决定与 P18/P19 两个新门） | 254 / 254 通过 |
| 类型与构建 | `npm run check:types`、`npm run build:frontend`、`npm run build:frontend-node` | 全通过（无 emit 错误） |
| Python 页面验证器（本地、替身 provider） | 见 §6.1 | 见 §6.1 |
| 页面 E2E（普通输入 → 决定 → 预览 → 提交替身） | `_stage-amz-control/issue9-expression-20261018T080410Z/issue9-ui-e2e/` | 见 §6.2 |

### 6.1 Python 验证器（最终构建，全部本地、替身 provider、零付费）

**18/18 退出码 0**。`postbrief-*.log` 保存较早的尺寸简报措辞修正轮（3_4 / 3_5 / 3_6 于17:52–17:53，其余15条于17:59–18:03）；独立审查再补两处门后，全部18条于18:22–18:30串行复核，最终构建依据是同目录`gatefix-*.log`（见§6.3），不能把较早轮次代称最后修改后的证据。逐条日志见`_stage-amz-control/issue9-expression-20261018T080410Z/verifier-rerun/`。

| 验证器 | 结果 | 验证器 | 结果 |
|---|---|---|---|
| `verify_v2_3_4_prompt_compiler.py` | 15/15 全过 | `verify_v2_5_3_compare_panel.py` | 15/15 全过（+ 回归） |
| `verify_v2_3_5_pre_generation_confirm.py` | 12/12 全过 | `verify_v2_5_4_rework_loop.py` | 15/15 全过（+ 回归） |
| `verify_v2_3_6_prompt_manual_edit.py` | 12/12 全过 | `verify_v2_6_1_selection.py` | 18/18 全过（+ 回归） |
| `verify_v2_4_2_generation_attempt.py` | 27 项全 PASS | `verify_v2_6_4_accessibility.py` | 18/18 全过（axe 0 违规） |
| `verify_v2_4_3_batch_execution.py` | 15/15 全 PASS | `verify_v2_packet08_settings_vision.py` | 38/38 全过 |
| `verify_v2_4_4_candidate_blob.py` | 14/14 全 PASS | `verify_v2_r5_2_two_adapters.py` | passed，`failed_ids: []` |
| `verify_v2_5_1_deterministic_review.py` | 7/7 全 PASS | `verify_v2_ui_2_interaction_visual.py` | 全 PASS（UI2-07…22 + 边界） |
| `verify_v2_5_2_vlm_review.py` | 全 PASS（含 R01–R21 回归） | `verify_v2_ui_3_frontend.py` | 15/15 全过 |
| `repro_r51_confirm.py` | 6/6 PASS | `rehearse_v273_walkthrough.py` | 走通（截图 24 张、交付包 manifest=True） |

3_4 / 3_5 / 3_6 三条与表达直接相关的验证器已把「自动印全部事实」的旧口径换成「用户所选条目 + 元素粒度」，其余验证器在编译前补做普通决定（`v2_verify_shared.decide_for_compile`）。两处口径变化都写在下述检查名里，任何回退都会变红：

- **V2.3.4-05**：`literal_items == [「304不锈钢内胆」,「12小时保温」]` 且每条 ref 指向 `shot_spec.on_image_text:t_signature_features_<i>`。
- **V2.3.5-15 / -16**：语言风险按所选条目（`t_signature_features_1/_2`）各一条、零重复；消息含「所选图中文字」「请人工确认」。
- 3_5 的页内重算探针本轮补上 `brief / styleSpec / shotSpecsById`（与产品 `prompts.ts` 交给 `buildConfirmationSheet` 的输入同一构造），因此确认单断言现在覆盖决定类阻断与消息，而不是只覆盖表层提示。

未跑的验证器：`verify_v2_4_5_live_reference.py`、`verify_v2_volc_adopt_export.py`（需 `--live` + 真实密钥，付费）、`run_remote_real_e2e.py`（需远程部署），本轮均未运行，不作为通过证据（仅 `py_compile` 语法通过）。

