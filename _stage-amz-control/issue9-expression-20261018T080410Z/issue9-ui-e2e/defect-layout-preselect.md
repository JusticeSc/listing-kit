# 缺陷报告：信息图版面「未决定」时被预选并落库（Issue #9 切片）

> 状态更新（2026-10-18）：**已由新语义解决**。Main 落地了「版面不再有程序默认」：
> `emptyShotSpecFromShot` 对印字角色不再写 `layout` 键（未决定=缺键，不是空串值；
> `ShotSpec.layout` 本来就是可选），保存路径只在用户点选三个真实版面之一时才写键，
> 编译 `layoutExplicit` 只认明确存过的值。Main 用重建后 dist 的 `/domain/index.js`
> 亲验：`emptyShotSpecFromShot({role_id:"infographic"})` →
> `{"print_intent":"undecided","on_image_texts":[]}`（无 layout 键），main 角色亦无印字键。
> 本文件保留原始定位记录；回归验证见 `verify_issue9_ui_e2e.py` 的 A2b（期望绿）与
> C0a/C0b/C0c 新编译门断言。

---

以下为原始报告（旧构建下的实证，已失效，仅保留定位链）：

## 现象（真实页面实证）

1. 新建项目 → 手工确认事实 → 生成推荐方案 → 展开「公共风格与单图规格」，
   **不碰任何版面 radio**，此时 DOM 里
   `#spec-layout-shot_infographic_benefits-product_only` 的 `checked` 已为 `true`
   （其余两个为 `false`），「还没决定」提示不显示。
2. 同样不碰任何版面 radio，直接点该图的「保存」，落库的 `shot_spec` payload 为：
   ```json
   {"print_intent": "undecided", "layout": "product_only", "on_image_texts": []}
   ```
   即用户从未做过的版面决定被以 `product_only` 写进版本历史。
3. 该 `layout` 值会进一步进入编译：`compilePrompt` 里
   `layoutExplicit = isNonEmptyString(input.shotSpec.layout)` 为真，
   于是排出 `shot_layout` 段「本图版面：画面只呈现商品主体……不叠加标题或参数文字。」
   ——用户没决定过，却得到一份声称版面的编译稿。

## 根因链（源码位置）

1. `app/product_v2/domain/specs.js` 的 `emptyShotSpecFromShot` 给印字决定角色
   预填 `spec.layout = "product_only"`（与 `print_intent = "undecided"` 同处一支）。
2. `app/product_v2/ui/input-view.ts` 的 `shotSpecDraftFrom` 只把 `print_intent`
   的 `"undecided"` 归一为空串（不预选），`layout` 却原样回填：
   `layout: typeof spec.layout === "string" ? spec.layout : ""`，
   于是草稿 `layout = "product_only"`，模板 `.checked=${live(spec.layout === layout)}`
   把「只放商品」点亮。
3. `handleSaveShotSpec` 的注释声称「没选的不写键」，但草稿里 `layout` 已是
   `"product_only"`（与用户亲选无法区分），`changes.layout` 被带上；即使不带，
   `project-inputs.ts` 的 `saveShotSpec` 用 `{...emptyShotSpecFromShot(shot), ...changes}`
   合并，`base.layout = "product_only"` 同样会落库。
4. `app/product_v2/domain/prompt.js` 的 `decisionProblems` 只在
   `print_intent === "selected"` 时检查 `layout`，`print_intent` 未决定/
   `none` 时 `layout` 缺失与 `product_only` 都不阻断——所以落库的默认值
   不会被编译门发现，直接排段。

## 为什么没造成错误外发（影响边界）

- `print_intent` 未决定时编译门仍阻断（`$.shot_spec.print_intent`），确认单
  `DECISION_REQUIRED` 正常出现，所以本缺陷不会让「没做印字决定」的图发出。
- 但它破坏了两条可验证的契约：
  a) 界面「未决定时不预选」；
  b) 「只有用户决定才出现对应段落」——`shot_layout` 段在用户未决定时出现。

## 最小复现（真实页面，零模型调用）

1. 新建项目，上传任意参考图，填写商品名/描述/卖点，点「自己填写商品事实」。
2. 确认 `product_name`、`product_category`、`signature_features`（任意值），
   其余标记未知，推进到方案，点「生成推荐方案」。
3. 展开「公共风格与单图规格」，不断言、直接读：
   `document.getElementById("spec-layout-shot_infographic_benefits-product_only").checked`
   === `true`（期望 `false`）。
4. 直接点信息图卡片的「保存」，读 IndexedDB `shot_spec/shot_infographic_benefits`
   最新版本：`payload.layout === "product_only"`（期望键缺失）。

## 建议修复方向（供实现者参考，不在本任务内执行）

- `emptyShotSpecFromShot` 对印字决定角色不要预填 `layout`（或预填一个
  UI/编译都识别为「未决定」的哨兵）；`shotSpecDraftFrom` 对缺失/哨兵归一为空串。
- `saveShotSpec` 合并时，未明确选择的 `layout` 不写键；`compilePrompt` 的
  `layoutExplicit` 只认用户明确存过的值。
- 补一个域测试：未决定 `layout` + `print_intent=none/undecided` 时
  `shot_layout` 段不出现；页面测试断言三组 radio 初始全不选。

## 本验证脚本的处理（新语义下已更新）

- A2b 恢复为回归验证：版面 radio 不预选，期望绿。
- 新增 C0a/C0b/C0c：selected+未选版面保存成功但不写 layout 键；缺 layout 编译阻断
  （消息含「还得先决定版面」）；layout=只放商品+selected 编译阻断
  （消息含「不能选『只放商品』版面」）。三条均为正式页面点击实证。
- 新增 D4：主图（无版面决定）正文不含「本图版面」段。
- 新编译门消息原文（页面实证，2026-10-18）：
  - 缺 layout：`这张图要印文案，还得先决定版面：「商品在左，文字在右」或「商品在右，`
    `文字在左」；程序不替你默认文字放哪边。`
  - 错 layout：`要印文案的图不能选「只放商品」版面：那样会同时要求「不出现文字」和`
    `「印出文字」。请改成商品在左或商品在右的版面。`
