# #9 表达力证据：真实项目的「原程序编译稿」与「新编译稿」对照

日期：2026-10-18（UTC）
目标工单：amz-listing-kit GitHub Issue #9（普通输入 + 程序视觉简报）
证据文件：`evals/product-v2/refactor/program-expression-20261018.json`（机器可读，含全部逐字文本）
来源项目包：`_stage-amz-control/asset-continuation-20261008T054352Z/data/manual-project.zip`（真实项目，含普通输入、事实槽、含原程序编译稿的记录、资产）

一句话结论：原程序对同一批普通输入只会输出「任务 + 保持/允许变化 + 平台规则 + 一堆禁止」，画面概念、主体位置与大小、视角、留白、光线、文字层级、外观状态全部由模型自己猜；新编译路径在用户做完少量普通选择后，把上述每一项写成正向、可执行、且不冒充事实的句子。**本证据只覆盖提示词编译与请求消费（零收费），不证明像素质量**（那属于工单第 6 条，另证）。

---

## 1. 代表性任务与普通输入（逐字）

普通输入（项目记录 `documents/0037.json`，`product_brief` v2，逐字）：

```text
商品名：透明玻璃蜂蜜罐样例
描述：参考图可见玻璃罐、HONEY 浮雕和蜂窝纹；旧化金属色盖。不声称容量、尺寸或密封性能。素材：Cindy Shebley / CC BY 2.0，Commons 31009798197。
卖点：罐身 HONEY 浮雕 / 蜂窝纹理 / 透明罐身
参考图：primary = c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461
```

确认事实（事实槽当前版本）：`product_category=玻璃储物罐`、`product_name=透明玻璃蜂蜜罐样例`、`signature_features=[HONEY 浮雕, 蜂窝纹理, 透明罐身]`、`key_material=透明玻璃罐身，金属色盖`；`size_*`、`brand`、`color_summary`、`package_contents` 均为 missing（未确认）。

整套图（`documents/0053.json`）：主图·干净背景 / 卖点信息图 / 场景图·使用中 / 细节图·材质工艺。（带尺寸图的 5 张项目在页面 E2E 里另建，见 §6.2。）

用户在本轮的**普通选择**（不提任何摄影术语）：整套「干净展示」+ 内容物为空；信息图印字 = 从已确认文案里勾选「必须保持的商品特征」（列表按元素各一条：`HONEY 浮雕` / `蜂窝纹理` / `透明罐身`）；版面 = 商品在左、文字在右。

---

## 2. 原程序编译稿的具体表达不足（逐条引用原句）

对照记录：主图 `0038`/`0040`（v1 与 v2）、信息图 `0039`、场景 `0042`、细节 `0038`（见 JSON 的 `old_record.text`）。

1. **没有画面概念**。场景图全文与画面有关的只有任务句「把商品放进符合用途的真实场景，场景不改变商品外观」——场景是什么、道具、光线方向、景深、主体与道具比例，全部没有。用户要得到可用场景图，只能自己写风格（该项目 `style_version` 记录里也没有可依赖的公共风格）。
2. **主体位置、大小、留白、视角没有任何表达**。主图唯一的大小约束来自平台规则「商品主体至少占画面 85%」，位置/留白/视角空白；细节图只有「允许变化：对焦、景别与光线」，却没有说清景别、光线方向或焦点落点。
3. **文字是自动全印，且没有排版表达**。信息图把 3 条卖点事实值逐条写成「图中文字」，**用户从没做过「要不要印字、印哪几条」的决定**；文字区位置、层级、字号、对齐、与商品的关系一个字都没有（真实项目采用的信息图上就出现过留白不足的偏差）。
   ```text
   图中文字（只允许逐字使用以下已确认文案，不翻译、不改写、不新增；文字语言应为「en」）：
   - 「HONEY 浮雕」
   - 「蜂窝纹理」
   - 「透明罐身」
   ```
   新路径的差别不在「印几条」，而在**这是用户明确选的那几条**（界面按「可逐字上图的最小单元」给候选：文本列表按元素各一条，标量整值，结构化尺寸不出候选），以及选择了要印字之后必须同时选一个能承载文字的版面。
4. **外观状态与内容物没有决定**。商品是容器类（玻璃罐），原程序既不说「保持使用痕迹」也不说「干净展示」，也不说内容物留空——「保持商品不变」与「干净的商品图」之间的冲突留给模型随机处理。
5. **负向堆砌代替正向表达**。全文的「必须避免：水印、文字错乱或文字变形、商品变形…」只能排除坏结果，不能告诉模型好结果长什么样；缺的正是正向的「文字清晰、层级分明、不遮挡商品」这类句子。

---

## 3. 新编译稿（同一批输入 + 上述普通选择）

段落顺序（新）：`product_fidelity, [style_shared,] visual_brief, shot_task, [shot_layout,] [on_image_text,] platform_rules, provider_contract, negative_constraints`。

新增/变化的三处（其余段落逐字保留原行为）：

- **product_fidelity** 追加状态句（由用户普通选择驱动，非程序默认）：
  ```text
  商品按干净展示状态呈现：允许去掉临时使用痕迹（水渍、指纹、残留），但材质、结构、标识与颜色仍与商品依据一致。
  内容物为空：内腔与瓶口干净、无残留，也不添加资料里没有的内容物。
  ```
- **visual_brief（画面简报）**：按用途给出正向画面概念、主体位置与大小、视角、留白、光线、清晰度；来源只引用 `suite_plan.shot:<id>`，不引用任何事实槽，因此不会把未确认信息写成画面设定。例（场景图）：
  ```text
  画面概念：商品在真实使用场景里的样子，场景说明用途但不抢商品焦点。主体：商品居中偏前、完整入画，与场景里的道具保持自然比例关系。光线与环境：符合场景的自然光线，方向明确、明暗过渡自然；背景轻微虚化以突出商品。一致性：场景与道具不出现其它品牌标识，也不与商品的材质、颜色冲突。
  ```
- **shot_layout / on_image_text**：只有用户明确做过决定才出现。本次信息图由用户勾选「必须保持的商品特征」（3 条元素各成一条）并选定「商品在左，文字在右」版面，正文里三条文案逐条带来源引用（`shot_spec.on_image_text:t_signature_features_1..3`），版面写明「商品完整放在画面左侧约三分之二区域…右侧保留干净留白放置下方给定的文字」，而不是把事实值当作程序默认印上去。

逐字全文见 JSON 的 `shots[].new_text`；四张图的新稿长度 560–692 字符（原稿 351–449），新增内容全部是正向表达，负向段落未增加。注意 JSON 里的新稿都带 `shot_layout` 段，因为对照脚本按「用户明确选了版面」写（未选版面时普通图正文不变）。

---

## 3.1 实施中发现并修掉的一处自相矛盾（版面与印字）

新路径第一版允许「只印所选文案」与「只放商品」版面同时存在，编译出的提示词在同一份文本里同时要求：

```text
本图版面：画面只呈现商品主体：主体完整入画、位置突出，四周保留干净留白，不叠加标题或参数文字。
图中文字（只允许逐字使用以下已确认文案，不翻译、不改写、不新增；文字语言应为「en」）：
- 「304不锈钢内胆」
```

而「只放商品」还是版面控件的默认值（用户不点也会写进规格），也就是说：用户选了「要印文案」但没碰版面，就会拿到一份互相矛盾的提示词。

修法（fail-closed，不静默替用户选）：
1. 印字角色的版面默认值从 `product_only` 改为未决定（不再预填）；界面不预选，未选就不写 `layout` 键、正文不排「版面」段。
2. 编译门新增两条：选了「只印所选文案」而版面缺失 → 阻断（消息「这张图要印文案，还得先决定版面…」）；版面选「只放商品」→ 阻断（消息点明「那样会同时要求『不出现文字』和『印出文字』」）。审核清单也只在真正选了版面后才列「版面」行。

因此本报告 §3 里信息图那一稿用的是用户明确选的「商品在左，文字在右」版面。

---

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

**18/18 退出码 0**，全部跑在含本条改动（含尺寸简报措辞修正）的最终构建上：3_4 / 3_5 / 3_6 于 17:52–17:53 重跑，其余 15 条于 17:59–18:03 串行重跑；逐条日志见 `_stage-amz-control/issue9-expression-20261018T080410Z/verifier-rerun/`（`postbrief-*.log`）。

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

### 6.2 页面 E2E（普通输入 → 普通选择 → 预览 → 提交替身 provider）

- 脚本：`_stage-amz-control/issue9-expression-20261018T080410Z/verify_issue9_ui_e2e.py`；证据：同目录 `issue9-ui-e2e/result.json` + 7 张截图（含新增的 `6a-layout-needs-text.png`、`6b-orphan-unbound.png`）。
- 结果：**43/43 通过，退出码 0**（`result.json` 的 `finished_at` = 2026-10-18T10:48:06Z；41 条原检查逐条未改，另加 E3/E4 两条把「实际出站请求」与「页面冻结记录」逐项对齐：**E3** 比 `size/n/prompt_extend/watermark/output_format/model_id/target`（期望值只读记录里的 `request_snapshot`，请求未携带的 `negative_prompt` 如实报 absent）；**E4** 比 `references` 的长度、按序 `role/media_type`，并把 `data_base64` **解码后**重算 `sha256`，同时等于请求自带字段、记录 sha256 与夹具 `PRIMARY_SHA256`；headless Chromium 打开正式 `dist` 页面，全部通过真实控件点击完成，不直接写库；商品图按 sha256 取 primary 资产）。期望值的来源分两种：角色画面简报句与`ROLE_VISUAL_BRIEF`、逐字文案都从页面 `/domain/index.js` 与 `fact_slot` 现值现场重算；**版面句与「本图版面」段名是脚本里的硬编码副本**（改动版面措辞时脚本要同步，改动本身不会被脚本发现，由域套件 P06/P16/P18 负责）。
- 覆盖：未决定时不预选（风格两组、印字、版面）；`presentation` 决定写进 `style_spec` 且 `product_fidelity` 出现状态句；「选了印字但缺版面 / 版面选了只放商品 / 选了文字版面却没有文案」三种语义门在正式页面上被拦并给出可操作文案（后两种还各有一处就地提示）；`on_image_texts` 按元素逐条保存（3 条 `t_signature_features_1..3`，逐字等于事实元素，来源同槽位同版本）；事实 v2→v3 后出现旧版提示、不重勾保存仍是旧版旧值、编译被拦「来源已不是当初确认的版本」、重勾后按新版 `v3` 确认（顶格 4 条保存成功）；**来源解绑后条目仍可见（`spec-text-orphan-…` 行，内容照旧）、编译被拦「来源事实已经不在这张图的绑定里」、勾掉即移除、重新绑定后恢复**；尺寸事实确认后套图变 5 张（含尺寸图），尺寸槽不出现在候选里（`#spec-text-…-size_dimensions` 不存在）、只剩尺寸绑定时 0 候选并给出「文字类事实才能上图」提示；预览逐字包含各用途画面简报句与 `product_fidelity` 段、主图无「本图版面」段；CDP 抓包 5 张图（含尺寸图）请求体与页面编译产物逐字相等且提交后全部 `succeeded`；零 console/page error。
- 诚实边界：替身 provider 只回固定 PNG，**印字是否真的出现在像素里、位置是否落在留白区不可验**（需真实模型 + 人工看图，属第 6 条）；返工/重提路径本轮未覆盖。

### 6.3 独立审查与收口

由独立于实现的审查者对**整个工作树差异**（41 个已改文件 + 4 个新增路径，2022 增 / 161 删）做只读复查，覆盖全部 `app/product_v2/**` 差异、`tools/**` 与 `evals/product-v2/{harness,node}` 的**每一条被删行**、新契约测试、证据 JSON/日志与 E2E `result.json`。其结论：无阻断级问题；逐字文案的元素粒度在保存/重载/编译/过期判定四段一致；22 条验证器的迁移只是「编译前补做必要决定」，17 处删除都是等价或更强的新断言（无 `try/except`、无放宽 `in`、无丢掉精确比较）；来源引用都指向真实字段；模板插值没有 XSS 面；报告里的证据与 JSON/日志逐条对得上。同时报出两处**同类自相矛盾**的漏网路径（我这轮的不变量只做了一个方向）：

1. **不印文字却留文字版面**：`print_intent="none"` + 「商品在左，文字在右」时仍会排出「右侧保留干净留白放置下方给定的文字」，而同一份记录里没有任何文案——两跳内可复现（先选版面，再改印字决定）。已按 fail-closed 补门：文字版面只有在「这张图确实会印文字」时才允许（`selected` 且有条目；非印字决定角色下还要求用途允许文字且绑定了可逐字印出的事实值），消息点明版面名与改法（`$.shot_spec.layout`）。
2. **来源解绑后仍在印**：已保存的 `on_image_texts` 若来源槽位被解绑，会从界面候选里消失却继续被印（编译门当时只校验来源已确认 + 版本一致）。两头收口：编译门要求「来源槽位必须在这张图的绑定里」；界面上把这类条目渲染成可见的「来源已不在这张图的绑定里」行，勾掉即移除；版面组也加了即时提示（选了文字版面但没有文案）。

补了永久回归 `P18`（两个方向 + 尺寸图导入态）与 `P19`（解绑后阻断、换绑定不得静默改来源），并把 `P17` 里一条恒真的弱断言改成「不印字必须有 `ON_IMAGE_TEXT_NONE_FACTS_SKIPPED`、不得有语言风险」。按审查者的两处文档 nit 修正本报告（§1 不再把尺寸图算进 `0053.json`；§6.2 说明版面句在 E2E 脚本里是硬编码副本）。审查明确未覆盖：未重跑任何测试、未渲染编译稿、未看像素。

改门后重跑全部 18 条 Python 验证器（18:22–18:30，逐条 `gatefix-*.log`）与页面 E2E，见 §6.1 / §6.2。

### 6.5 补充：CI 其余验证器本机复核

本切片改动公共编译链与 input-view，故把 CI `verify` 作业里**另外 16 条**未在 §6.1 覆盖的验证器也在本机跑了一遍（`uv run --locked python tools/<name>.py`，逐条日志 `_stage-amz-control/issue9-expression-20261018T080410Z/verifier-rerun/ci-<name>.log`）：`2_1_1` `2_1_2` `2_1_3` `2_1_4` `2_2_1` `2_2_2` `2_2_3` `2_3_1` `2_3_2` `2_3_3-session-lifecycle` `2_3_3-spec-versions` `2_5_5` `2_6_2` `2_6_3` `packet08-adoption-ai` `packet08-delivery-ai`。**16/16 退出码 0**（本机 Windows + 无头 Chromium，替身 provider）。加上 §6.1 的 18 条，CI `verify` 列举的 32 条验证器本机全绿；CI 自身结果仍以 PR #18 的 check 为准。

### 6.6 交付前复核（本分支门，非其他工作树）

- 复核对象是 **PR 分支 `feat/9-program-expression-20261018` 自己的工作树**（`amz-listing-kit-issue9-expression`），不是修隔离用例时用的旧工作树。
- 本分支 CI PR 作业的前端门逐条重跑：`check:versions`、`build:envelope`、`check:types`、`build:frontend`、`check:envelope`、`build:frontend-node`、`test:domain` —— **7/7 退出码 0**（`verifier-rerun/ci-frontend-gates.log`；域套件 tests 254 / pass 254 / fail 0）。跑完工作树无源码改动（生成的 envelope 产物与提交一致）。
- 口径提醒：本分支 `package.json` **没有** `check:generated` 脚本（那是另一工作树/分支的脚本）；本分支的生成物新鲜度门是 `check:envelope`（含 `ENVELOPE-CODEGEN-REPRODUCIBLE` 与 199 案例跨语言等价），已 rc=0。

### 6.4 交付

以 4 个提交推送到 `feat/9-program-expression-20261018`，Draft PR **#18**（`https://github.com/JusticeSc/listing-kit/pull/18`，`isDraft=true`，base `main`，169 文件 / +7840 −161）；PR 正文含真实差量验证、独立审查收口、未证范围与 Issue #9 关联。CI：`Classify changed paths` 通过，`Control plane and Product V2` 见 PR checks。**未合并、未部署、无真实模型调用。**

---

## 7. 本轮改动的产品行为边界

- 候选文案按「能逐字上图的最小单元」给：文本列表按元素各一条（保存后逐条带来源引用）、标量整值、结构化尺寸（`dimension_list`）不出候选（页面上提示「文字类事实才能上图」），因此不会再把 `[object Object]` 这类不是图上文字的字符串印进提示词。
- 上限仍是每图 4 条（按条目计，域层 `MAX_ON_IMAGE_TEXTS` 与界面同一常量）。
- 版面与印字两个方向都自洽：要印文案必须选文字版面；选了文字版面也必须真的有文案（不印文字、或非印字角色下没有可逐字印出的事实值 → 拦下并给出改法）。界面上这两种状态都有就地提示。
- 所选文案的来源槽位必须仍在这张图的绑定里；来源被解绑时条目在界面上仍然可见、可移除，编译被拦而不是继续印用户已经移出这张图的依据。
