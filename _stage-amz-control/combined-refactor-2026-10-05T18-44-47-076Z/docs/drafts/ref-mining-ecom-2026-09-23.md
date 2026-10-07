# 参考范例挖掘记录（三个 ecom 库 → Product V1 任务卡）

> CONTROL-STATUS: superseded · AUTHORITY: none  
> **采纳内容已进入完整演示产品计划；本文件只保存来源，不再发布任务卡、能力结论或判据。**
>
> 历史状态：设计草案。它的作用是把"当时从哪读到、据此改了什么"留下来，不是长期权威。
>
> **它不作判据。** 这里的每一条都只是**假设与结构的来源**：平台阈值、供应商能力、
> 计费单位一律以实施当日官方资料与低成本探针复核为准。这条不是我加的规矩 ——
> 计划 P2.1 的任务卡里已经写着「能力未知视为不支持；实施当日以 provider 官方资料 /
> 低成本探针复核，不沿用范例库声明」。本文件不得越过它。

---

## 0. 读了什么（证据边界）

| 库 | 本地路径 | 体量 | 读了什么 |
|---|---|---|---|
| `ecommerce-skills-main` | `E:\gitee_repository\vison\ecommerce-skills-main` | 373 文件 / 12.7 MB | `shared/scripts/{gen.mjs,batch.mjs,run_loop.mjs,check_listing.py}`、`shared/references/{provider-cli.md,platform-specs.md}`、`skills/platform-compliance/skill.md`、`scripts/run-evals.mjs`、`evals/flat-lay/cases.json`、`shared/scripts/lib/tasks.json` |
| `ecommerce-image-suite-main` | `E:\gitee_repository\vison\ecommerce-image-suite-main` | 151 文件 / 221 MB | `SKILL.md`（一级/二级标题与流程段）、`references/dynamic-prompt-architecture.md`、`references/` 目录清单 |
| `ecom-details-image-main` | `E:\gitee_repository\vison\ecom-details-image-main` | 119 文件 / 104 MB | `README.md` 与 `.claude/skills/ecom-details-image/`（`SKILL.md`、`references/templates/01-hero-image.json`、`04-detail-macro.json`） |

**边界（重要）**：三个库都只是**本机的一份副本**。我没有核对上游 git 远端与提交号，
所以下面所有引用都是「**这份副本在 2026-09-23 是这样写的**」，不是「上游现在是这样」。
另外这三个库是**面向单个操作员的技能库**（每个技能一个动作、由 Agent 读 `skill.md` 现编），
而我方要做的是**2–5 人内部生产工具**（状态、权限、预算、审计）。这个差别决定了下面大部分
"不采纳"的理由 —— 它们的优化目标是"一次生成好看"，我方的优化目标是"二十个 SKU 可重复、可追责"。

---

## 1. 结论摘要

- **采纳 6 条**（都是**结构或边界**层面，不涉及照抄数值）：§2.1 熔断位置在派发之前、
  §2.2「无幂等键、无取消」作能力表反例、§2.3 两种崩溃点作必须覆盖的探针场景、
  §3.1 四条候选规则、§3.3「合规化 ≠ 修图」、§4.1 槽位变体与类目配置的字段形状。
- **只作记录**（不改任何决定，留作对照）：§2.4 范例的重试语义、§2.5 数据流向、
  §2.6 静态单价表、§3.4 加规则会连带改人工清单、§3.5 范例的 golden case 是回归网、
  §5.1 数据集分层与我方同构。
- **待复核**（实施当日自己验）：§3.2 的「纯白底」判法，以及 §6 末行那一串数值。
- **不采纳 4 条**：见 §6。其中 §6.1（自动闭环改 prompt 重跑）是**最重要的不采纳** —— 理由见 §4.3。

---

## 2. 对 Phase 2（外部调用安全层）

### 2.1 范例的成本熔断在"派发之前"，这条形状是对的 —— 采纳

**来源**：`ecommerce-skills-main/shared/scripts/batch.mjs`（并发池回调开头）

```js
if (halted) return { sku: row.sku, status: 'skipped-budget' }
if (budget && spent + unit > budget) {
  if (!halted) { halted = true; console.log(`\n⛔ 预估成本触及熔断线 ${budget}，停止派发新任务`) }
  return { sku: row.sku, status: 'skipped-budget' }
}
spent += unit
```

**事实**：它在**调用生成器之前**判预算，超了就整批停止派发（`halted`）。不是"发完了发现超了"。

**判断**：采纳这个形状，写进 P2.5（预算硬门）：**硬门的位置在派发之前**。
理由是它决定"最多超一笔"还是"最多超一批"。这条对 Checkpoint C7 的"每任务成本上限"是前置条件
—— 上限只有在"派发前拦得住"时才有意义。

**它改哪张卡**：P2.5 预算硬门（补一句"门在派发之前，超限的动作不提交"）。

### 2.2 范例的 provider 层没有幂等键，也没有取消 —— 采纳（作为反例登记）

**来源**：`shared/references/provider-cli.md` 全文。

**事实**：它登记的能力只有：认证（`dlazy login` / `DLAZY_API_KEY`）、后端选路
（`--provider` > `PROVIDER` 环境变量 > 第一个配了 key 的 > `dlazy`）、可用性探测（`gen.mjs --doctor`）、
估价（`--dry-run` 不调用不计费）、异步（`--no-wait` 返回 `task: { generateId, status }`，
再用 `dlazy status <generateId> --wait` 轮询）、重试（429/5xx 指数退避）、错误码表。
**没有**提交幂等键，**没有**取消指令。

**判断**：采纳为 P2.1 能力表的**反例证据**：

1. `action_id` 只能由我方生成（业务身份 + 请求哈希），provider 侧只回一个它自己的 `generateId`；
   两边的关系是我方账本里的一个字段，不能反过来指望 provider 认我们的 id。
2. `cancel` 必须按"**能力未知视为不支持**"登记 —— 这意味着**预算控制不能依赖取消**，
   只能在提交前拦（与 §2.1 同一条结论，互为例证）。
3. 重试与"提交是否已经发生"无关：重试就是再提交一次。这就把 P2.4（Unknown 核对）的必要性
   钉死了 —— 见 §2.4。

**它改哪张卡**：P2.1 能力契约、P2.3 动作身份（把"provider 不认我方 id、不提供取消"写作已知起点）。

### 2.3 范例的断点续跑按"产物存在"记，分不清"没做"和"做了没拿到" —— 采纳（作为要堵的洞）

**来源**：`batch.mjs` 的 `.batch-state.json` 与 `--resume`

```js
const state = o.resume && existsSync(statePath) ? JSON.parse(...) : { done: {} }
...
queue = queue.filter((r) => !state.done[r.sku])      // 跳过"已完成"的 sku
...
if (r.code === 0) { state.done[row.sku] = { files, at: ... } }   // 只在生成器退出码 0 时写
```

**事实**：续跑的依据是"这个 sku 在状态文件里算完成"。写 `done` 的条件是生成器**整体退出码为 0**。

**判断**：这留下两个洞，而且都很具体：

1. **提交成功、下载/落盘失败** → 退出码非 0 → 没记 `done` → 重跑会**再提交一次**；
   远端那一张可能已经做了、已经计费。
2. **进程在"生成成功"与"写状态文件"之间崩溃** → 状态文件里没有 → 重跑会重复提交。

两者都无法用"再跑一次"补救，因为**动作身份丢了**。这正是 P2.3（动作身份与账本）与
P2.4（Unknown 核对）存在的理由，也是"Timeout is not failure"落地的位置：
超时/中断先转 Unknown，核对原动作身份之后再决定重试或补偿。

**它改哪张卡**：P2.3、P2.4（把上面两种崩溃点写成必须覆盖的探针场景）。

### 2.4 范例的重试是"直接重试"，不是"先核对" —— 不采纳，但要写清为什么

**来源**：`batch.mjs` 的重试循环

```js
for (let attempt = 0; attempt <= o.retries; attempt++) {
  const r = await run(process.execPath, args)
  if (r.code === 0) { ... }
  if (attempt < o.retries) { const wait = 2 ** attempt * 1500; await new Promise(...) }
}
```

**事实**：失败即重试（默认 2 次，指数退避），重试前不查"上一次到底提交没提交"。

**判断**：不采纳这条语义。对**技术失败**（连接被拒、本地文件读不到）直接重试是安全的；
对**远端超时**（可能已经受理）直接重试就是"可能重复计费"。我方要区分这两类：
只有"确定没提交"才允许直接重试，断言不了就转 Unknown 并核对。
（范例的 `--no-wait` + `status <generateId>` 恰好说明**核对手段是存在的**，
它只是没被用在重试路径上。）

### 2.5 数据流向写明了，但"留存/删除"没人承诺 —— 记录

**来源**：`provider-cli.md` 第三节

> 调用 dLazy 时：提示词与参数发往 `api.dlazy.com`；传入的本地图片会上传到 `files.dlazy.com`
> 供模型读取；产出 URL 同样托管在 `files.dlazy.com`。

**事实**：数据**流向**写得很清楚（提示词 + 原图 + 产物都在供应商侧），
但**没有**任何留存时长或删除承诺。

**判断**：这正好说明我方 P1.2 数据政策里那两个字段（`retention`、`expires_at`）
**不是可以照抄的装饰**：它们是要向供应商问清楚、并由人签字确认的东西。
范例把"上传到对方服务器"当成了基础设施说明；我方必须把它当成一个**授权事项**。

### 2.6 范例的「成本」自始至终是一张静态单价表，没有「实付」这个概念 —— 记录

**来源**：`shared/scripts/gen.mjs`（`--dry-run` 与返回结构）+ `shared/scripts/lib/tasks.json`

```json
"_credits": { "gpt-image-2": 60, "seedream-5.0": 30, "seedream-5.0-pro": 45, "banana-pro": 25, "claude-sonnet-5": 3 }
```

```js
if (o.dryRun) { ... console.log({ ..., estimatedCredits: credits || null }) }
const out = await withRetry(() => provider.run(req), o.retries)   // 重试只按 HTTP 状态判：429 / 5xx
```

**事实**：`estimatedCredits` 是按**模型名**查表的静态值，不是供应商回执；重试的判断依据是 HTTP 状态码。

**判断**：这说明「拿预估当账本」在范例里不是疏忽，而是它的设计 —— 它整个成本体系里**没有"实付"这一列**。
对单个操作员"心里有个数"够了；对「后 15 个任务不得突破已批准上限」这种**可审计**的要求不够。
所以 §2.1 那两列表（预留 / 实付）不是把范例的做法加一列，而是补上一个范例里不存在的对象。

---

## 3. 对 Phase 5（确定性检查）

### 3.1 范例的可机检集合比我方现有多四条 —— 采纳为候选

**来源**：`skills/platform-compliance/skill.md` 的真实输出段 + `shared/references/platform-specs.md`。

范例的检查项（实测输出）：分辨率 / 画面比例 / 纯白背景 / 主体占比 / **透明通道** / **边框** /
文件格式 / 文件体积 / **色彩模式** / 文字·水印·拼图（明确标注"像素层判不了，交给视觉模型或人工"）。

我方 `src/validators.py` 的 `KNOWN_RULES` 现有 9 条：`white_bg_purity` / `product_fill` /
`has_text_block` / `edge_clean` / `text_present` / `aspect_ratio` / `long_side_px` /
`file_size` / `filename_has_upc`。

**逐条比对后的候选缺口（我方现在没有的）**：

| 候选规则 | 范例的判法 | 为什么它可能是真缺口 |
|---|---|---|
| 交付图不得带 alpha | `allow_alpha`：读 `im.mode` / `transparency` | 范例说"**透明 PNG：Amazon 会把透明像素转成黑色**"。我方 `src/intake.py:has_alpha()` 只把它当"已是抠好的图"的提示，**没有任何一条校验把"交付图不得带 alpha"当门** |
| 色彩模式 | 判 RGB vs CMYK | CMYK JPEG 是典型的上传即拒；我方不读色彩模式 |
| 最长边上限 | `max_long_side`（下限之外还有上限） | 我方只有下限 `long_side_px` |
| 体积上限 | `max_bytes`（我方有 `file_size`，需确认口径一致） | 已经有了，列为"确认口径"而非新增 |

**判断**：**采纳为 P5.1 的开工前候选清单**，不直接落地。理由见 §3.4（加规则会连带改人工清单），
而且平台的真实阈值必须在实施当日复核。

### 3.2 "纯白底"的判法是一处必须定口径的地方 —— 待复核

**来源**：`platform-specs.md` 字段表与"容易踩的点"

（字段）`bg_tolerance`：判定"纯白"允许的单通道偏差；`bg_coverage`：**边缘一圈**需要有多大比例落在容差内。
（踩坑）"**白底不等于看起来是白的**：棚拍的浅灰墙（约 RGB 208）肉眼像白，机检直接判不合格。"

**对比我方**：`check_white_bg()` 取**四条边带**（`band=0.04`），判据是"落在 `WHITE_MIN` 以上的像素比例 ≥ 0.995"。

**判断**：两者不是同一个判据（环带取法不同、容差定义不同、阈值不同），会在边界图上给出**不同结论**。
这不是"谁抄谁"的问题，是**我方必须自己定一个口径并写清理由**，否则同一张图在两个工具里结论相反时，
运营不知道信谁。待复核点是：Amazon 官方对主图背景的表述到底怎么写的。

### 3.3 自动修复的边界必须写死：合规化 ≠ 修图 —— 采纳

**来源**：`platform-compliance/skill.md`

> **自动修复的边界**：`--fix` 只做几何与色彩层面的合规化，它不会替你修图。
> 如果原图本身是糊的、崩的、带水印的，修完还是糊的崩的带水印的。

**判断**：采纳这条**边界表述**，写进 Phase 6 的单图返工设计。它对抗的是一种很自然的诱惑：
把"改尺寸、压白底、补分辨率"当成"问题解决了"。我方现在的单图返工必须区分：

- **合规化**（几何/色彩层面，确定性、免费、可重复）；
- **重生成**（要模型、要钱、要重新过检查）；
- **换素材**（回到收件环节）。

三者若混在一个按钮里，"返工后达标"就说不清是哪一种达标 —— 而这正是 §9 完成证据矩阵里
"关键事实错误为 0"最容易被糊过去的地方。

**它改哪张卡**：Phase 6 的返工相关任务（补一句返工类型必须分开记）。

### 3.4 加规则会连带改人工清单（有代码证据）—— 记录

**来源**：我方 `src/review_contract.py:check_references()`

```python
missing = sorted(set(known_rules) - rules_used - excluded)
if missing:
    problems.append(f"src/validators.py 里这些规则既没有清单项、也没写排除理由：{missing}")
```

**判断**：这意味着 §3.1 那几条候选规则**不能"只加代码"** —— 加了就一定会在 P1.3 的清单守卫上变红，
必须同时给出人工清单项或写明排除理由。这是设计意图（"新加校验忘了配人工清单"要有东西响），
所以 P5.1 的开工前口径里要把这条依赖写明，免得到时候把红灯当成守卫坏了。

### 3.5 范例的 golden case 不是验收判据，是回归网 —— 记录（我方的对照见 §5）

**来源**：`ecommerce-skills-main/evals/flat-lay/cases.json`

```json
{ "id": "knit-sweater-on-model", "prompt": "...", "images": ["docs/flat-lay/garment-flatlay.jpg", "..."],
  "expect": ["麻花织法保留", "落肩版型保留", "姿势与背景照抄参考图"] }
```

`_note` 自己写着："golden case：**改了 prompt 模板之后跑一遍，确认没把原来能出的效果改坏**。
加 `--live` 才会真生成。"

**事实**：它叫 golden case，实际语义是**回归**（别改坏），不是"验收判据"；
`expect` 是自然语言，**没有断言**去机检它（`run-evals.mjs` 只做 L1 结构检查 + L2 用
`check_listing` 客观校验和 `detect-task` 主观打分）。

**判断**：记录这个差别 —— 我方 P1.5 的标签是**结构化**的（`verdict` + `failed_items`），
而且要绑输入哈希与 FactsVersion。**不采纳**"把期望写成一句自然语言就算判据"。

---

## 4. 对 Phase 4（单槽位影子实验）

### 4.1 槽位模板的字段形状可作 P4.1 的形态候选 —— 采纳

**来源**：`ecom-details-image-main/.claude/skills/ecom-details-image/references/templates/01-hero-image.json`

字段（节选）：`id` / `name` / `keywords` / `trigger_phrases` /
`prompt_template{type, subject, background, lighting, composition, quality}` /
`defaults` / **`variants`（每个变体只写 `overrides`）** / **`category_tips`（按品类）/ `examples`（3 条成稿）/
`anti_ai_tips` / `supports_image_reference`。

**判断**：两个字段形状值得采纳进 P4.1 的槽位计划：

1. **`variants` = `defaults` + `overrides`**：同一槽位的风格变体不改槽位身份，只覆盖字段。
   这正是"可配置的图片槽位计划、不把'七张'写死"的实现形态 —— 变体是**参数**，不是新槽位。
2. **`category_tips`**：按品类给取向提示。与我方"色板随类目走"（`config/catalog/<类目>.yaml`）同构，
   但内容是**风格取向**而非颜色 —— 说明类目级配置有两类：不可变的品牌/色板，和可调的取向。
   P1.4 登记品类时可以把这两类分开。

**不采纳的部分**：`examples` 里把设备写死（见 §6.2）；`trigger_phrases`（那是给 Agent 做意图路由的，
我方是固定槽位表，不需要）。

### 4.2 最重要的反面证据：范例把"动态 prompt 更好"当结论，没有任何对照 —— 采纳（作为我方对照实验的理由）

**来源**：`ecommerce-image-suite-main/references/dynamic-prompt-architecture.md`

> **固定模板架构的缺陷**：所有商品用同一套 Prompt / 文案内容固定 / 无法根据商品特点动态调整 /
> 无法利用分析出的卖点
>
> **核心原则**：1. 基于商品真实特征生成：不是套模板，而是理解商品后创作

**事实**：这份文档是**设计论证**：它列了固定模板的 4 条"缺陷"，然后给出新架构。
通篇**没有**任何对照实验、没有分母、没有"换了以后哪一项指标变好了"。

**判断**：这恰好是我方 Phase 4 存在的理由，而且是**最有价值的一条挖掘结论**：
参考库把一个**假设**（"理解商品后创作会更好"）写成了结论。对我方来说它不是结论而是**待检验命题**：

- 影子实验必须有**成对证据**（同输入、确定性路线 vs 生成路线），
- 判据不能是"看起来更聪明"，只能是任务卡里写的那些（关键事实错误、人工返工率、单任务成本/时间），
- 赚不回净收益就保留确定性路线 —— 这是 Goal 里已经写死的降级条件。

**它改哪张卡**：P4.1/P4.2（把"参考库只有设计论证、无对照"记为影子实验必须自己补的那一块）。

### 4.3 自动闭环（生成→质检→改 prompt→重跑）两处都不可采纳 —— 不采纳

**来源**：`ecommerce-skills-main/shared/scripts/run_loop.mjs`

> `run_loop.mjs` —— 生成 → 质检 → 自动改 prompt → 重跑，直到达标或到轮次上限。
> `--max-rounds <n>` 最多重跑几轮，默认 3；`--accept <等级>` 达标线：低风险（默认）。

实现要点：每轮真调用一次 `gen.mjs`（付费），然后调 `check_listing.py` 做客观合规、
再调 `detect-task`（`claude-sonnet-5`，一次 3 credits）做主观质检，
把质检报告"第 4 节"里的**英文修正句**抠出来追加到 prompt 上，进入下一轮。

**两处不采纳，都有具体后果**：

1. **成本账失真。** `batch.mjs` 里每个 sku 只在派发前记**一次** `unit`：

   ```js
   spent += unit          // 每行只加一次
   const genArgs = ... (o.loop ? 'run_loop.mjs' : 'gen.mjs')
   ```

   而 `run_loop` 最多跑 3 轮，每轮一次生成 **加** 一次质检调用。
   按它自己的 `tasks.json`（`gpt-image-2: 60`、`claude-sonnet-5: 3`），
   单 sku 实际可达 `3×60 + 3×3 = 189` credits，而 `estimatedCredits` 报 60 —— **低报约 3 倍**，
   而熔断线是拿这个数判的。结论：**"预估累计"不能当账本**；我方 P2.5 必须记
   预留（派发前）与实付（每次调用后）两条数，且每轮重跑都要各记一笔。
2. **责任错位。** 自动闭环的"达标"是 **VLM 的风险等级 + 像素合规**，不是商品事实。
   它可以用"追加提示词"让风险分降下来，而图上的商品可能已经和资料不一致了。
   计划 §7.3 已经写着"不用加提示词覆盖状态/权限类问题"；这条正是那句话的反面教材。

**它改哪张卡**：P2.5（预留/实付双账，重跑逐笔记）、P4.2（失败模式治理：把"靠加提示词把分刷绿"
列为一个要防的失败模式）。

---

## 5. 对 Phase 1（P1.5 数据集）—— 与我方已落地项的对照

### 5.1 分层是对的，绑定我方更强 —— 记录（不改）

**来源**：`scripts/run-evals.mjs`

- **L1 结构与可执行性（无需任何 key，CI 默认跑）**：frontmatter 合法、正文不超 500 行、
  相对链接都指得到、文档里的命令真能跑、**golden case 的素材必须真实存在**。
- **L2 真实生成打分（需要 key，加 `--live`）**。

**判断**：与我方已有的分层同构 —— `tools/regress_all.py`（离线、无模型调用）
vs `--fresh`（真跑、花一次调用）；`tools/check_dataset_ready.py` 也做到了"素材不在就报红、
且不必等到花钱那一刻"。**不需要改。**

值得记下的一处差别（我方更强，勿回退）：

| 维度 | 范例 `evals/*/cases.json` | 我方 `evals/product-v1/dataset/` |
|---|---|---|
| 期望 | `expect: ["麻花织法保留", …]` 自然语言，无断言 | `verdict` + `failed_items` 结构化，进覆盖统计 |
| 素材绑定 | 路径 | 路径 + `sha256` |
| 事实版本 | 无 | `facts_version`（加载时现场算出来核对） |
| 标签责任人 | 无 | `labelers` 登记；没登记就不进统计 |
| 版本 | 无（就地改文件） | `gcv1-<内容哈希>`；就地改会被发现 |

---

## 6. 明确不采纳

1. **自动闭环改 prompt 重跑**（`run_loop.mjs` 的形态）：理由见 §4.3（成本低报 + 责任错位）。
   我方允许的是"单图返工由**人**发起、并且分开记返工类型"（见 §3.3）。
2. **把设备与相机参数写进 prompt**：`04-detail-macro.json` 的 `examples` 里有
   `Canon EOS R5 100mm f/2.8`、`Sony A7R V 90mm macro, focus stacking` 这类词。
   它们对生成模型是噪声、对验收是不可归因的变量；影子实验要回答"净收益"，
   就该把这类无法归因的写法排除在对照之外。
3. **把范例的平台规则表当权威照抄**：`platform-specs.md` 自己也写着"平台规则会变，
   以各平台最新官方文档为准"。我方的 `validators.KNOWN_RULES` 是判据的**唯一**权威，
   照抄一份进来就多一份会各自漂的正文（与 `config/brand.json` 那次"两边各存一份同值颜色"同型）。
4. **把"看起来更聪明"当净收益证据**：见 §4.2。

**待复核（实施当日自己验，不沿用这里的数）**：Amazon 主图的纯白底要求与容差、
主体占比下限（范例写 ≥85%）、长边区间（1000–1600）、体积上限（10 MB）、
"透明 PNG 会被转成黑"这条说法、以及计费单位表（60 / 30 / 25 / 5 / 3 credits）。

---

## 7. 落地动作

| 动作 | 落在哪 | 状态 |
|---|---|---|
| 挖掘记录本身 | 本文件 | 已写（2026-09-23） |
| 任务卡引用本文件作为对照证据来源 | `docs/product-v1-goal-and-implementation-plan.md`「P1–P8 任务执行卡」开头 | 已写 |
| 成本门在派发之前、预留/实付双账 | P2.5 任务卡 | 开工时按任务卡口径落地（Phase 1 未过门，不进 Phase 2） |
| 能力表把"无幂等键 / 无取消"写作已知起点 | P2.1、P2.3 | 同上 |
| 两条崩溃点（提交成功未落盘 / 落盘前崩溃）作探针场景 | P2.3、P2.4 | 同上 |
| 候选规则：交付图不得带 alpha、色彩模式、最长边上限 | P5.1 开工前口径 | 待 P5.1 开工 |
| 返工类型必须分开记（合规化 / 重生成 / 换素材） | Phase 6 返工任务 | 待该阶段 |
| 槽位变体用 `defaults + overrides`、类目配置分"品牌/色板"与"取向" | P4.1、P1.4 登记品类时 | 待该阶段 |

**这份文件不证明任何一条已经实现**：它只说明"这些结论是从哪读到的、据此要改哪张卡"。
按 §0 的边界，所有数值与能力仍需实施当日复核。
