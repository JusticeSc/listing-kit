# Issue #9 状态（草稿，等全部绿灯后发布）

> 目标：普通输入 + 程序协调的正向视觉简报；不遍历事实自动印字；生成前把表达写清楚。
> 分支：`feat/9-program-expression-20261018` → Draft PR [#18](https://github.com/JusticeSc/listing-kit/pull/18)（已推送，等待 CI 与人工审阅；未合并）

## 已实现

1. **画面简报（`ROLE_VISUAL_BRIEF` → 编译段 `visual_brief`）**
   按用途（main/infographic/scene/detail/size/comparison/ingredient/packaging/custom）给出正向画面概念、主体位置与大小、视角、留白、光线/清晰度；来源只引用 `suite_plan.shot:*`，不把未确认信息写成画面设定。段落位置：`product_fidelity` → `style_shared` → `visual_brief` → `shot_task` → …
2. **展示决定（用户普通选择，程序不默认）**
   `style_spec.presentation.appearance_state/contents_state`；未决定且被该用途消费时编译阻断并给出可操作消息；选定后写进 `product_fidelity`（干净展示才给去污例外）。
3. **印字决定（只印所选，粒度=能逐字上图的最小单元）**
   `shot_spec.print_intent/on_image_texts/layout`：不遍历事实自动印字；`selected` 只印用户勾选且已确认、来源当前、且来源仍在这张图绑定里的文案。候选按最小单元给：文本列表**按元素各成一条**（保存后逐条带来源引用），标量整值，结构化尺寸（`dimension_list`）不出候选（页面提示「文字类事实才能上图」），因此不会把 `[object Object]` 这类不是图上文字的字符串写进提示词；上限仍每图 4 条（按条目计）。来源被解绑时条目在界面上仍然可见（「来源已不在这张图的绑定里」行）、勾掉即移除，编译被拦而不是继续印。
4. **版面与印字两个方向都自洽**：要印文案必须选文字版面；选了文字版面也必须真的有文案（不印文字、或非印字角色下没有可逐字印出的事实值 → 拦下并给出改法）。界面在这两种状态下都有就地提示，避免用户对着红字猜。
5. **表达对照证据**：`evals/product-v2/refactor/program-expression-20261018.{md,json}`（真实项目的原程序编译稿 vs 新编译稿逐字对照 + 验证证据 + 独立审查收口）。

## 验证

- `node --test evals/product-v2/node/*.test.mjs`（域/前端套件，含 P 系列印字/版面/展示决定与 P18/P19 两个新门）：**254 / 254 通过**。
- `npm run check:types`、`npm run build:frontend`、`npm run build:frontend-node`、`npm run check:versions`、`tools/check_docs.py --no-run`、`tools/check_verification.py`、`tools/check_project_state.py`：全过（退出码 0）。
- Python 页面验证器（本地、替身 provider、零付费）：**18/18 退出码 0，全部跑在最终构建上**（补完两处新门后 18 条于 18:22–18:30 全部串行重跑；逐条日志 `_stage-amz-control/issue9-expression-20261018T080410Z/verifier-rerun/gatefix-*.log`，此前一轮 `postbrief-*.log`）。3_4 15/15、3_5 12/12、3_6 12/12、4_2 27 项 PASS、4_3 15/15、4_4 14/14、5_1 7/7、5_2 全 PASS（含 R01–R21 回归）、5_3 15/15、5_4 15/15、6_1 18/18、6_4 18/18、packet08 38/38、r5_2 passed、ui_2 全 PASS、ui_3 15/15、r51 6/6、演练走通。编译前统一补做普通决定；3_4 / 3_5 / 3_6 的旧「自动印全部事实」口径已按元素粒度更新（V2.3.4-05、V2.3.5-15/-16），**任何回退都会变红**。3_5 的页内重算探针本轮补上 `brief / styleSpec / shotSpecsById`（与产品 `prompts.ts` 同一构造），确认单断言因此覆盖决定类阻断与消息。
- **页面 E2E**（普通输入 → 普通选择 → 预览 → 提交替身 provider，CDP 抓真实出站请求体）：**41/41 通过，退出码 0**（`finished_at=2026-10-18T10:33:08Z`）。证据：`_stage-amz-control/issue9-expression-20261018T080410Z/issue9-ui-e2e/`（`result.json` 逐项 + 7 张截图）。含两个新门：不印文字却留文字版面（页面提示 + 阻断 + 改回「只放商品」恢复）、来源解绑后条目仍可见/可移除且编译被拦。
- **独立审查**：对整个工作树差异（41 改 + 4 新增，2022 增 / 161 删）做过一次只读复查（全部 `app/product_v2/**` 差异、`tools/**` 与 `evals/product-v2/{harness,node}` 的每一条被删行、新契约测试、证据 JSON/日志、E2E `result.json`）：无阻断级问题；22 条验证器的迁移只加必要决定、17 处删除均为等价或更强的新断言；两处同类自相矛盾路径已按上表收口并补 P18/P19 回归。审查明确未覆盖：未重跑测试、未渲染编译稿、未看像素。
- 未跑（不作为通过证据）：`verify_v2_4_5_live_reference.py`、`verify_v2_volc_adopt_export.py`（需 `--live` + 真实密钥，付费）、`run_remote_real_e2e.py`（需远程部署）。

## 未包含 / 仍缺

- 英文文案来源（AI 提议 + 人工确认）未做；印字仍会触发 `ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE`。像素层面「印字是否真的出现、是否落在留白区」不可验（替身只回固定 PNG），需真实模型 + 人工看图，属工单第 6 条。
- **尺寸数值还不能逐字上图**：结构化尺寸既不在候选里，也不会被当文本印出，所以尺寸图拿不到可引用数值。本轮已把尺寸用途的画面简报改成不邀请编造数字，但「尺寸标注」能力本身仍未实现（给结构化尺寸一个可逐字上图的表示，或绑了尺寸却无可印数值时明确提示）。
- **「来源一致」只到版本级**：编译门校验文案的来源槽位（已确认 + 仍在本图绑定里）+ 版本，不校验字面是否等于事实值（用户自撰文案是设计允许的扩展点，P03 即该形态）。页面只能从事实值逐字生成候选，所以正常使用不受影响；导入/手改过的项目数据可能带不一致文案。
- `viewpoint` 未开放（设计 §13.4 已记实施状态）；单图 `presentation` 覆盖只有域层与测试，页面暂无入口（确认单文案已改为「整套共用」）。
- 返工/重提路径本轮未覆盖。

## 交付状态

已按授权提交并推送 4 个提交、创建 Draft PR [#18](https://github.com/JusticeSc/listing-kit/pull/18)（`isDraft=true`，base `main`，169 个文件 / +7840 −161）。CI 已触发（`Classify changed paths` 通过；`Control plane and Product V2` 见 PR checks）。**未合并、未部署、无真实模型调用**；像素品质与真人验收仍在本轮之外。
