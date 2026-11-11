<!-- 拆分件 03/05 · 父文档 evals/product-v2/refactor/program-expression-20261018.md -->
# 6.2 页面 E2E（普通输入 → 普通选择 → 预览 → 提交替身 provider）
[返回 program-expression-20261018.md](program-expression-20261018.md)

### 6.2 页面 E2E（普通输入 → 普通选择 → 预览 → 提交替身 provider）

- 脚本：`_stage-amz-control/issue9-expression-20261018T080410Z/verify_issue9_ui_e2e.py`；证据：同目录 `issue9-ui-e2e/result.json` + 7 张截图（含新增的 `6a-layout-needs-text.png`、`6b-orphan-unbound.png`）。
- 结果：**43/43 通过，退出码 0**（`result.json` 的 `finished_at` = 2026-10-18T10:48:06Z；41 条原检查逐条未改，另加 E3/E4 两条把「实际出站请求」与「页面冻结记录」逐项对齐：**E3** 比 `size/n/prompt_extend/watermark/output_format/model_id/target`（期望值只读记录里的 `request_snapshot`，请求未携带的 `negative_prompt` 如实报 absent）；**E4** 比 `references` 的长度、按序 `role/media_type`，并把 `data_base64` **解码后**重算 `sha256`，同时等于请求自带字段、记录 sha256 与夹具 `PRIMARY_SHA256`；headless Chromium 打开正式 `dist` 页面，全部通过真实控件点击完成，不直接写库；商品图按 sha256 取 primary 资产）。期望值的来源分两种：角色画面简报句与`ROLE_VISUAL_BRIEF`、逐字文案都从页面 `/domain/index.js` 与 `fact_slot` 现值现场重算；**版面句与「本图版面」段名是脚本里的硬编码副本**（改动版面措辞时脚本要同步，改动本身不会被脚本发现，由域套件 P06/P16/P18 负责）。
- 覆盖：未决定时不预选（风格两组、印字、版面）；`presentation` 决定写进 `style_spec` 且 `product_fidelity` 出现状态句；「选了印字但缺版面 / 版面选了只放商品 / 选了文字版面却没有文案」三种语义门在正式页面上被拦并给出可操作文案（后两种还各有一处就地提示）；`on_image_texts` 按元素逐条保存（3 条 `t_signature_features_1..3`，逐字等于事实元素，来源同槽位同版本）；事实 v2→v3 后出现旧版提示、不重勾保存仍是旧版旧值、编译被拦「来源已不是当初确认的版本」、重勾后按新版 `v3` 确认（顶格 4 条保存成功）；**来源解绑后条目仍可见（`spec-text-orphan-…` 行，内容照旧）、编译被拦「来源事实已经不在这张图的绑定里」、勾掉即移除、重新绑定后恢复**；尺寸事实确认后套图变 5 张（含尺寸图），尺寸槽不出现在候选里（`#spec-text-…-size_dimensions` 不存在）、只剩尺寸绑定时 0 候选并给出「文字类事实才能上图」提示；预览逐字包含各用途画面简报句与 `product_fidelity` 段、主图无「本图版面」段；CDP 抓包 5 张图（含尺寸图）请求体与页面编译产物逐字相等且提交后全部 `succeeded`；零 console/page error。
- 诚实边界：替身 provider 只回固定 PNG，**印字是否真的出现在像素里、位置是否落在留白区不可验**（需真实模型 + 人工看图，属第 6 条）；返工/重提路径本轮未覆盖。

### 6.3 独立审查与收口

由独立于实现的审查者对**整个工作树差异**（41 个已改文件 + 4 个新增路径，2022 增 / 161 删）做只读复查，覆盖全部 `app/product_v2/**` 差异、`tools/**` 与 `evals/product-v2/{harness,node}` 的**每一条被删行**、新契约测试、证据 JSON/日志与 E2E `result.json`。其结论：无阻断级问题；逐字文案的元素粒度在保存/重载/编译/过期判定四段一致；22 条验证器的迁移只是「编译前补做必要决定」，17 处删除都是等价或更强的新断言（无 `try/except`、无放宽 `in`、无丢掉精确比较）；来源引用都指向真实字段；模板插值没有 XSS 面；报告里的证据与 JSON/日志逐条对得上。同时报出两处**同类自相矛盾**的漏网路径（我这轮的不变量只做了一个方向）：

1. **不印文字却留文字版面**：`print_intent="none"` + 「商品在左，文字在右」时仍会排出「右侧保留干净留白放置下方给定的文字」，而同一份记录里没有任何文案——两跳内可复现（先选版面，再改印字决定）。已按 fail-closed 补门：文字版面只有在「这张图确实会印文字」时才允许（`selected` 且有条目；非印字决定角色下还要求用途允许文字且绑定了可逐字印出的事实值），消息点明版面名与改法（`$.shot_spec.layout`）。
2. **来源解绑后仍在印**：已保存的 `on_image_texts` 若来源槽位被解绑，会从界面候选里消失却继续被印（编译门当时只校验来源已确认 + 版本一致）。两头收口：编译门要求「来源槽位必须在这张图的绑定里」；界面上把这类条目渲染成可见的「来源已不在这张图的绑定里」行，勾掉即移除；版面组也加了即时提示（选了文字版面但没有文案）。

补了永久回归 `P18`（两个方向 + 尺寸图导入态）与 `P19`（解绑后阻断、换绑定不得静默改来源），并把 `P17` 里一条恒真的弱断言改成「不印字必须有 `ON_IMAGE_TEXT_NONE_FACTS_SKIPPED`、不得有语言风险」。按审查者的两处文档 nit 修正本报告（§1 不再把尺寸图算进 `0053.json`；§6.2 说明版面句在 E2E 脚本里是硬编码副本）。审查明确未覆盖：未重跑任何测试、未渲染编译稿、未看像素。**审查时点与后续差量**：该次审查看的是提交 `57017ef`/`3977bed`/`bcd987e` 的工作树差异（`app/**`、`tools/**`、`evals/product-v2/{node,harness}` 到 `3977bed` 为止，之后**再未改动**——`git log -1 -- app/` = `57017ef`，`git log -1 -- tools/` = `3977bed`）；其后新增的只有证据文件与 E2E 脚本的 `E3/E4` 两条比对（`d046df0`，测试装置不在审查范围）和文档说明，均为本代理自查，未再经独立审查。

改门后重跑全部 18 条 Python 验证器（18:22–18:30，逐条 `gatefix-*.log`）与页面 E2E，见 §6.1 / §6.2。

### 6.5 补充：CI 其余验证器本机复核

本切片改动公共编译链与 input-view，故把 CI `verify` 作业里**另外 16 条**未在 §6.1 覆盖的验证器也在本机跑了一遍（`uv run --locked python tools/<name>.py`，逐条日志 `_stage-amz-control/issue9-expression-20261018T080410Z/verifier-rerun/ci-<name>.log`）：`2_1_1` `2_1_2` `2_1_3` `2_1_4` `2_2_1` `2_2_2` `2_2_3` `2_3_1` `2_3_2` `2_3_3-session-lifecycle` `2_3_3-spec-versions` `2_5_5` `2_6_2` `2_6_3` `packet08-adoption-ai` `packet08-delivery-ai`。**16/16 退出码 0**（本机 Windows + 无头 Chromium，替身 provider）。加上 §6.1 的 18 条，CI `verify` 列举的 32 条验证器本机全绿；CI 自身结果仍以 PR #18 的 check 为准。

### 6.6 交付前复核（本分支门，非其他工作树）

- 复核对象是 **PR 分支 `feat/9-program-expression-20261018` 自己的工作树**（`amz-listing-kit-issue9-expression`），不是修隔离用例时用的旧工作树。
- 本分支 CI PR 作业的前端门逐条重跑：`check:versions`、`build:envelope`、`check:types`、`build:frontend`、`check:envelope`、`build:frontend-node`、`test:domain` —— **7/7 退出码 0**（`verifier-rerun/ci-frontend-gates.log`；域套件 tests 254 / pass 254 / fail 0）。跑完工作树无源码改动（生成的 envelope 产物与提交一致）。
- 口径提醒：本分支 `package.json` **没有** `check:generated` 脚本（那是另一工作树/分支的脚本）；本分支的生成物新鲜度门是 `check:envelope`（含 `ENVELOPE-CODEGEN-REPRODUCIBLE` 与 199 案例跨语言等价），已 rc=0。

### 6.4 交付

已推送到`feat/9-program-expression-20261018`并创建 Draft PR **#18**（`https://github.com/JusticeSc/listing-kit/pull/18`）。截至受审固定版本`3dc0018689dad39fb81294a9c76c99c97dc15e8f`，实际8提交、186文件 / +9146 −161，`isDraft=true`、base `main`；PR正文含真实差量验证、审查范围、未证范围和Issue #9关联。[CI run 39121148778](https://github.com/JusticeSc/listing-kit/actions/runs/39121148778)三项检查均SUCCESS，实际部署/finalize步骤skipped。该统计只描述固定受审版本，不包含后续说明修订。**未合并、未部署、无真实模型调用。**

---

