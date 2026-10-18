关联 Issue：[#9 普通输入 + 程序协调的正向视觉简报](https://github.com/JusticeSc/listing-kit/issues/9)（本 PR 只完成 #9 的**零收费程序表达差量**，不关闭 Issue：像素品质与真实模型验收不在本轮范围内，见下「未证范围」。）

# PR 正文

（正文 = `_stage-amz-control/issue9-expression-20261018T080410Z/issue9-status-draft.md` 同源副本，此处公开给 PR。）

## 已实现

1. **画面简报（`ROLE_VISUAL_BRIEF` → 编译段 `visual_brief`）**
   按用途（main/infographic/scene/detail/size/comparison/ingredient/packaging/custom）给出正向画面概念、主体位置与大小、视角、留白、光线/清晰度；来源只引用 `suite_plan.shot:*`，不把未确认信息写成画面设定。段落位置：`product_fidelity` → `style_shared` → `visual_brief` → `shot_task` → …
2. **展示决定（用户普通选择，程序不默认）**
   `style_spec.presentation.appearance_state/contents_state`；未决定且被该用途消费时编译阻断并给出可操作消息；选定后写进 `product_fidelity`（干净展示才给去污例外）。
3. **印字决定（只印所选，粒度=能逐字上图的最小单元）**
   `shot_spec.print_intent/on_image_texts/layout`：不遍历事实自动印字；`selected` 只印用户勾选且已确认、来源当前、且来源仍在这张图绑定里的文案。候选按最小单元给：文本列表**按元素各成一条**（保存后逐条带来源引用），标量整值，结构化尺寸（`dimension_list`）不出候选（页面提示「文字类事实才能上图」），因此不会把 `[object Object]` 这类不是图上文字的字符串写进提示词；上限仍每图 4 条（按条目计）。来源被解绑时条目在界面上仍然可见（「来源已不在这张图的绑定里」行）、勾掉即移除，编译被拦而不是继续印。
4. **版面与印字两个方向都自洽**：要印文案必须选文字版面；选了文字版面也必须真的有文案（不印文字、或非印字角色下没有可逐字印出的事实值 → 拦下并给出改法）。界面在这两种状态下都有就地提示，避免用户对着红字猜。
5. **表达对照证据**：`evals/product-v2/refactor/program-expression-20261018.{md,json}`（真实项目的原程序编译稿 vs 新编译稿逐字对照 + 验证证据 + 独立审查收口）。

## 真实差量验证证据

| 项目 | 结果 |
|---|---|
| `npm run check:types` | 退出码 0 |
| `npm run build:frontend` | 退出码 0（vite build 成功） |
| `npm run test:domain`（含 P01–P19） | 退出码 0，254 / 254 通过 |
| 18 条 Python 页面验证器（本地、替身 provider、零付费） | 18 / 18 退出码 0（逐条日志 `_stage-amz-control/issue9-expression-20261018T080410Z/verifier-rerun/gatefix-*.log`） |
| 页面 E2E（正式页面真实点击 → 预览 → 提交替身 → CDP 抓包） | 41 / 41 退出码 0（`issue9-ui-e2e/result.json`，`finished_at=2026-10-18T10:33:08Z`，7 张截图） |
| 对照脚本（真实项目原稿 vs 新稿，零网络零模型） | `program-expression-before-after.mjs` 可重跑，JSON 存全部逐字文本 |

差量对照要点：同一批普通输入与原程序产物下，原稿只有任务句 + 保持/允许变化 + 平台规则 + 一堆禁止；新稿在用户做完少量普通选择后，把画面概念、主体位置与大小、视角/留白/光线、干净展示状态、版面与逐字文案（各带精确来源引用）写成正向可执行句子。四张图新稿 560–692 字符（原稿 351–449），新增内容全是正向表达，负向段落未增加。

正文一致性：E2E 用 CDP 抓真实出站请求体，与页面编译产物、冻结记录逐字相等（含参数与参考图身份/顺序），提交后 5 张图全部 `succeeded`。

## 独立审查

对整个工作树差异（41 改 + 4 新增，2022 增 / 161 删）做过只读复查（全部 `app/product_v2/**` 差异、`tools/**` 与 `evals/product-v2/{harness,node}` 的每一条被删行、新契约测试、证据 JSON/日志、E2E `result.json`）：无阻断级问题；22 条验证器的迁移只加必要决定、17 处删除均为等价或更强的新断言；两处同类自相矛盾路径（不印文字却留文字版面、来源解绑后仍在印）已按上表收口并补 P18/P19 回归、重跑全部验证器与 E2E。审查明确未覆盖：未重跑测试、未渲染编译稿、未看像素。

## 未证范围（不得当成已验收）

- **真实出图品质未验收**：替身 provider 只回固定 PNG，像素层面「印字是否真的出现、位置是否落在留白区」不可验，需真实模型 + 人工看图，属工单第 6 条。
- 英文文案来源（AI 提议 + 人工确认）未做；印字仍会触发 `ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE`。
- 尺寸数值还不能逐字上图：结构化尺寸不出候选也不会被当文本印出；本轮只保证尺寸用途的提示词不邀请编造数字，「尺寸标注」能力仍未实现。
- 「来源一致」只到版本级：编译门校验来源槽位（已确认 + 仍在本图绑定里）+ 版本，不校验字面是否等于事实值（用户自撰文案是设计允许的扩展点）。
- `viewpoint` 未开放（设计 §13.4 已记实施状态）；单图 `presentation` 覆盖只有域层与测试，页面暂无入口。
- 未跑：`verify_v2_4_5_live_reference.py`、`verify_v2_volc_adopt_export.py`（需 `--live` + 真实密钥，付费）、`run_remote_real_e2e.py`（需远程部署）。
- 返工/重提路径本轮未覆盖。

## 未包含

不合并、不直推 main、不部署、不调用真实模型/供应商，不改变原完整产品终点；V1 清退、C15/C17 真人验收等仍按原计划独立进行。
