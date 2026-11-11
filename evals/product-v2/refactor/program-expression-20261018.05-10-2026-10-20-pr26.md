<!-- 拆分件 05/05 · 父文档 evals/product-v2/refactor/program-expression-20261018.md -->
# 10. 2026-10-20 规则版本按印字决定取值（PR26 审查后续修复；原审查非阻断）
[返回 program-expression-20261018.md](program-expression-20261018.md)

## 10. 2026-10-20 规则版本按印字决定取值（PR26 审查后续修复；原审查非阻断）

原始独立审查 `PR26Review`（范围 `9793845..0bafc82`，只读）原文见 `_stage-amz-control/self-reform-20261020T144442Z/original-review.txt`（31 行，sha256 `19f28f2034b4c6c42c1e0d2cc8b6bbf594cdf5f88135bcffd274e2f6637a7121`；工具返回另存 `original-review-tool-result.json`，公开读回见 PR #26 评论）。原结论为 `overall_correctness: correct`、无阻断缺陷，两项发现均为 P3；本节旧稿把 `PROr26Review` 错名、把范围错归 PR #18、把原 P3 升格为 P1/blocking、“无稿可写/永远 consumed_sources_changed”无据因果，均已撤回。旧错误字节保留在 `_stage-amz-control/self-reform-20261020T144442Z/before.zip`（`program-expression-20261018.md` sha256 `60c9f49aeca2df5625dd995eb838289a32e9b40859f589dc0e98e0f451a0242a`）。

原 finding 1（P3，confidence 0.85）：Node 侧 G12 规则版本断言（`prompt-contract.test.mjs:618-626` 的 `compiler_rule_version`、`historicalMain`、`historicalInfo`、`compilerBumped` 及 `buildPromptRecord` 拒绝）未镜像到浏览器 harness 与生成器源；`_gen.mjs` 经 `pureRewrite` 从 harness 重生成会删掉这些断言，`verify_v2_3_4_prompt_compiler.py` 因读 harness 而不覆盖该规则。原 finding 2（P3，confidence 0.8）：`promptCompilerRuleVersionOf` 只按 `roleId === "infographic"` 取规则 4，印字信息图（`print_intent="selected"`，正文与规则 3 逐字相同）仍被判 `compiler_rule_version` 过期（`PROMPT_STALE`/`consumed_sources_changed`），重备后正文不变。原审查同时核实：`checkPromptRecord` 不按规则拒读旧记录、双返工模式与引用顺序、`discard`+OCC append-only、G12 无字 `infoSpec` 两副本一致；另有一条非阻断观察（`emptyShotSpecFromShot` 默认印字 purpose/keep/change 与 none 混排，属工作流/页面更新风险，无夹具证明默认路径）。

后续 `e38ab61`（超出原审查范围，原审查不覆盖后续代码）把规则改为 `(roleId === "infographic" && intent === "none") ? 4 : 3`，并把有效印字决定冻结进 `basis.print_intent`，让写入门（`buildPromptRecord`）按同一判据复核；历史记录缺该字段时按旧规则 3 解释，仍可读取导入，但用旧规则冒充新写入会被拒。`prompts.ts` 与 `repository.js` 的当前依据投影改按实时 `effectivePrinting(...).intent` 取规则，不再只看用途。这样修的是原 finding 2 指出的真实 selected 过期问题（印字信息图正文逐字未变却被判过期、被迫无意义重备），主图与印字信息图的既有成品因此不作废；“不印字组合写入永远失败”是本节旧稿自己的无据推断，已撤回，不归于原审查。

回归放在既有套件里，不在源码文本上断言：`G12`（浏览器版）与 `evals/product-v2/node/prompt-contract.test.mjs` 的 Node 副本都覆盖四条——主图规则保持 3、印字信息图规则保持 3 且不过期、规则 3 的旧信息图记录可读但按当前规则过期、旧规则编译结果不得冒充新写入。原 finding 1 指出只写 Node 侧的断言会被 `_gen.mjs` 从 harness 重生成时删掉，同一批断言因此补进 `harness/prompt-contract.js`。已观察事实：该生成器在本分支执行到 `brief C28` 锚点处抛 `brief C28 边界失败`（本切片未修，两个副本暂时各自维护、内容一致）；“与本节改动无关”是未证归因，已收紧——本切片未做该失败与本改动的隔离对照，不声称已证无关。

本轮证据（本地、替身 provider、零付费）：

- `npm run test:domain` → 292 项全过、rc=0；`tools/verify_v2_3_4_prompt_compiler.py` → 15 条全过、rc=0（`evals/product-v2/v2.3.4-prompt-compiler-20261020-204412.txt`）；`verify_v2_3_5_pre_generation_confirm.py` 13/13、`verify_v2_3_6_prompt_manual_edit.py` 13/13，均 rc=0。
- 浏览器契约读的是构建产物 `dist/product-v2`，改完源码必须先 `npm run build:frontend` 再跑浏览器验证器。已观察事实：本轮验证器第一次跑红，重建产物后通过；现有汇总没有提供从首红到重建的逐条因果对照，不能据此断言“第一次跑红就是旧 dist 原因、不是产品 bug”，也不拿后续绿灯洗掉首次红的证据。
- 提交 `e38ab61` 之后按要求重做两轮全回归：`verify_v2_7_1_regression.py --rounds 2 --stamp final_v2` → 50 条命令 × 2 轮全绿、指纹一致 `290ee1bddc2b3a6b`、源码身份 `e38ab6149aa8`（证据 `evals/product-v2/v2.7.1-regression-final_v2-final.txt`）。

- 推送后 CI [run 39428551617](https://github.com/JusticeSc/listing-kit/actions/runs/39428551617) 在 `68bcade` 上三项检查全 pass（分类、控制面+Product V2 13m16s、镜像与冒烟，PR 不部署）；PR #26 仍是 Draft。

仍未证：本修复不改变「是否真的把文案画进像素」，真实出图品质依旧未验收。页面已有印字决定（`ui/input-view.ts` 的 `printDecisionTemplate` 提供 `none`/`selected` 单选）；新增的 `basis.print_intent` 只是有效决定的冻结依据，不另设二次人工确认。本次代码回归不代签该交互的最终人因验收。本切片零真实外呼；两个 Adapter × 两模式的真实四组合已有 2026-10-15 真实证据（相邻主工作树 `_stage-amz-control/formal-resume-20261015T125651Z/real-wire/four-mode-proof.json`：`volcengine-ark` edit/regenerate 与 `dashscope-qwen-image` edit/regenerate 各一例 succeeded，本树 state 机器块 L127 同样登记该路径），在 provider/model/协议/能力/凭据条件未变时按原范围复用，不要求为本切片重买证明。

纠正记录：本节于 2026-10-20T15:01:26Z 纠正（真实 UTC）；此前 `review-fix.json` 的 `2026-10-20T20:50:00Z` 观察时点已撤回，不再作为可信观察。
