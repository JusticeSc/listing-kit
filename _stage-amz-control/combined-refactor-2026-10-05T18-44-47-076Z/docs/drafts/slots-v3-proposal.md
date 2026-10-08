# slots v3 提案：把「一维类型表」扩成「类型 × 输入 × 变体」

> CONTROL-STATUS: superseded · AUTHORITY: none  
>
> ## ⚠️ 已被取代 —— 当前规范只看 `docs/product-demo-goal-and-implementation-plan.md`
>
> 本文件 §3.1 把"参考图进模型"写成了与**确定性通路并列**的一个缺口，**这个方向是错的**。
> 正确的架构是：**生成是主路，确定性合成只保留一个例外（位置 1 白底主图）**。
> §1（输入轴 14 槽位）与 §2（输出轴 6 族约 20 类）仍然有效，被 v4 继承；
> §3（关键机制缺口）与 §6（落地顺序）已被 v4 重写。
> 保留本文件只为留下输入轴/输出轴的取证记录 —— **实施时以 v4 为准**。

> **状态：草案，未进控制面。** 本文件不覆盖 `config/slots.yaml`。
> 按本项目纪律（每个字段必须有消费它的代码位置），下表中每个字段都标了**当前消费方**或**待建消费方**；
> 待建消费方的字段不许先落进 `slots.yaml`，否则就是第四个 `text_style`。

参考库出处缩写：**A** = `ecommerce-skills-main`（26 技能库）· **B** = `ecommerce-image-suite-main`（9 类型 8 步）· **C** = `ecom-details-image-main`（25 模板库）

---

## 0. 诊断：为什么现在的表「只能出 7 张」

`config/slots.yaml` 是**一维表**：7 行 = 7 个输出类型，每行的 `needs` 是一个**布尔门**（有就做，没有就跳过）。

三个库的表都是**二维或三维**：

| 库 | 表 | 维度 | 形态 |
|---|---|---|---|
| B | `TYPE_IMAGE_SLOT`（`generate.py:363-373`） | **类型 × 输入图** | `{"white_bg": 0, "material": 1, ...}` —— 类型**决定读第几张输入图** |
| B | `TYPE_NAMES_ZH` + `--types` | 类型 × 平台 × 模板套 | 9 类型可任意子集，`--template-set 1-6` + `--per-type-templates` 按格覆盖 |
| C | `references/templates/*.json` | 类型 × 变体 × 品类 | 25 模板 × 3-4 变体 × 5 品类建议 |
| A | `brand.yaml`（`brand-schema.md`） | 配置段 × **声明谁读它** | 6 段（brand/model/photography/layout/forbid/compliance），每段列出读它的技能；"不相干的段落不会进 prompt" |
| A | `fission-pattern` §3「套图配方」 | 类型 × **镜位清单** | 固定 5 镜位，三段式 prompt：段1/段2 整套**逐字复用**，段3 每张变 |

**我的表少了两维：输入槽位维、变体维。** 所以「加一张图」在我这套里没有位置——它只能表现为"某格的 `needs` 多一项"。

---

## 1. 输入轴（新文件 `config/inputs.yaml`）

**收束规则**：每个槽位声明 `kind`（image/text/config/enum）、`required`、以及**它去哪一格**。库 B 的做法是把"去哪一格"放在**类型侧**（`TYPE_IMAGE_SLOT`），库 A 的做法是放在**顺序侧**（`--images` 顺序即 image 1/2/3，`gen.mjs:69`）。本项目采用**槽位 id 显式引用**（取两库之长：既不靠位置也不靠约定）。

| 槽位 id | 是什么 | 必填 | 三库出处 | 现状 |
|---|---|---|---|---|
| `ref_front` | 商品正面参考图 | **是** | B `input_image_type=flat_lay`（①单张正面平铺）；B `TYPE_IMAGE_SLOT` 7 个类型取 index 0；A `--images` 第 1 张 | ✅ = 现在的 `front` |
| `ref_back` | 背面参考图 | 否 | B `flat_lay_front_back`（②，**最佳**）；B 材质图**自动改用** index 1（`TYPE_IMAGE_SLOT["material"]=1`） | ❌ 无 |
| `ref_detail` | 细节面参考图 | 否 | B Step B：`--product-images front,back,detail`（3 张） | ≈ 现在的 `closeup`（但语义是"另一个面"而非"放大"） |
| `ref_model` | 模特参考图（锁脸） | 否 | A `--model-image`；A `brand.model.reference: assets/model/face-a.jpg`（"锁脸：会作为额外参考图传入"）；B `--model-image`（"会嵌入强制指令，要求严格复刻参考图中的人物外貌"） | ❌ 无 |
| `ref_pose` | 姿势参考图 | 否 | A `flat-lay --images 服装平铺图 姿势参考图` —— **这是它的第 2 张输入，不是文案** | ❌ 无 |
| `ref_competitor` | 竞品图 | 否 | ⚠️ **三库皆无此输入**（见 §4）。C `09-before-after` 是自家前后对比；A fission-pattern #5 是"尺寸对比物" | ✅ 现在有 `competitor` |
| `copy_points` | 卖点文案 | 否（可由图推出） | B `selling_points[]`（含 `visual_keywords`，**必须英文**，供放大镜气泡用）；A `item-selling-point`"卖点"；C `Copy Lines` | ✅ = 现在的 `bullets` |
| `copy_specs` | 规格/尺寸参数 | 否 | B 可选输入"规格参数"；C `13-size-spec` 的 `{size_annotations}` + `{usage_steps}` | ✅ = 现在的 `specs` |
| `copy_scenes` | 目标场景 | 否 | B `target_scenes` + `target_scene_envs`——**Agent 必须动态生成，禁止硬编码**（`_scene_to_env()` 只是兜底） | ❌ 无（现在是 `catalog.bg_prompt_hints` 写死 3 条） |
| `copy_audience` | 目标受众 | 否 | B `target_audience`（"用于推断模特性别/年龄"，`_model_desc` 消费） | ❌ 无 |
| `lock_brand` | 品牌/视觉锁 | 否 | A `brand.yaml` 6 段；C `Campaign Style Lock` **10 必填字段**（视觉方向/色板/冷暖调/字体/背景/光线/布局/图标/产品呈现/禁止漂移项） | ≈ 现在的 `brand.json`，但缺"锁"语义 |
| `enum_platform` | 目标平台 | **是** | A `--platform amazon` + `platform-specs.md`（6 平台 × 10 字段**机检**）；B 6 平台 → 尺寸 + `lang` | ≈ 现在的 `site: US`（**只有一个值**） |
| `enum_template` | 视觉风格模板 | 否 | B `--template-set 1-6` + `--per-type-templates key_features:2,material:3`；C 25 模板 × variants | ❌ 无 |
| `list_skus` | 商品清单（批量轴） | 否 | A `batch-image --input skus.csv --concurrency 4 --max-credits 3000 --resume --contact-sheet` | ❌ 无（已知缺口） |

**用户没列到的 7 条**：`ref_back` / `ref_model` / `ref_pose` / `copy_scenes` / `copy_audience` / `enum_template` / `list_skus`。

### 命名与解析（沿用现有约定）
- 路径**相对商品包所在目录**解析（本项目现有约定，三库为"相对运行目录"，B 还专门要 `cp` 到 `{output_dir}/` 规避临时目录失效——`SKILL.md` 的「图片预处理」节）。
- 素材门槛（B `fission-pattern` §2 硬性约束）：**20KB~15MB / >400×400 / jpg·jpeg·png·webp**。本项目现在用的是 **最长边 ≥1000px**（库 A `platform-specs.md` 的 amazon 行），更严 —— 保留本项目的，因为它对应平台机检，不是模型容忍度。

---

## 2. 输出轴（`slots.yaml` 由 7 行扩为「族 → 类型」）

**分组依据来自库 C**：它不用"枚举"而用**三套序列**（视觉驱动 / 痛点驱动 / 情感价值，`SKILL.md`「商品图序列模板」），**顺序本身是决策**。库 A `fission-pattern` 同理：5 镜位是固定配方，不是可选清单。

| 族 | 类型 | 三库对应 | 本项目现状 | 缺口 |
|---|---|---|---|---|
| **主图族** | 白底主图 | B `white_bg` / C `01-hero-image` / A `item-change-background` | ✅ 位置 1 `compose_white` | — |
| | 平铺图 | C `03-flat-lay` / A `flat-lay`(平铺→上身) | ❌ | 缺（家居类目未必需要） |
| **信息族** | 核心卖点图（图标化） | B `key_features`（4 种展示样式） / A `item-selling-point` / C `11-infographic` | ✅ 位置 2 `flat_overlay` | 缺"按卖点类型选样式"（B §「核心卖点图展示样式选择」4 种） |
| | 单品深挖卖点图 | B `selling_pt` | ✅ 位置 2 部分覆盖 | — |
| | 尺寸/规格图 | C `13-size-spec`（尺寸 + **使用步骤**） / B 图3 | ✅ 位置 3 `flat_overlay`+`annotation` | 缺 `usage_steps` 这个输入 |
| | 参数表 / 详情版式 | B `ecommerce_detail`（英雄图 + 参数表 + 6 格卡片 + 多颜色） | ❌ | 缺 |
| **实拍族** | 细节/材质微距 | B `material` / C `04-detail-macro` / A `clothing-detail` | ✅ 位置 5 `closeup_crop` | — |
| | 场景展示 | B `lifestyle` / C `02-lifestyle-scene` | ✅ 位置 4 `gen_bg_paste` | — |
| | 模特展示 | B `model` / C `08-model-showcase` / A `flat-lay`·`wear-everything` | ❌ | **缺，且需要 `ref_model` + `gen_with_ref`** |
| | 穿戴/试穿 | C `16-try-on-virtual` / A `wear-everything` | ❌ | 缺 |
| | 隐形模特 / 立体 | C `18-ghost-mannequin` / A `to-3d` | ❌ | 缺 |
| **结构族** | 三角度 / 多角度 | B `three_angle_view`（**单图时自动插入**）/ C `19-multi-angle-grid` | ❌ | 缺（B 的触发条件是 `len(images)==1`，且插在 `multi_scene` **之前**） |
| | 多场景拼图 | B `multi_scene` / A `fission-pattern` | ❌ | 缺（需要 `copy_scenes`） |
| | 前后对比 | C `09-before-after`（clinical/cinematic/simple 3 变体） | ❌ | 缺 |
| | 竞品并排 | ⚠️ **三库无**（见 §4） | ✅ 位置 7 `compare_side` | 本项目独有 |
| | 组合/套装 | C `14-multi-product` / A `image-fusion`(最多 8 张单品) | ❌ | 缺 |
| | 拆解/爆炸图 | C `17-exploded-view` | ❌ | 缺 |
| | 包装/内容物 | C `10-packaging` | ✅ 位置 6 `contents_compose` | — |
| **营销族** | 海报 / Banner | C `05-poster-banner` | ❌ | 缺 |
| | 社媒 / UGC | C `06-social-media`·`07-ugc-style`（含 `anti_ai_tips`） / A `ugc-testimonial`·`clothing-grass-planting` | ❌ | 缺 |
| | A/B 变体组 | A `listing-optimizer`（"多组对照主图 + 每组的差异假设 + 复盘模板"） | ❌ | 缺 |
| | 多语言本地化 | A `cross-border-localize`（多语言文案 + 尺码换算表 + 区域合规标识） | ❌ | 缺 |
| **动态族** | 视频 | A `main-image-video`·`product-video-ad`·`ugc-testimonial` / B 第八步 | ❌ | 缺 |
| | 质检报告 | A `detect-task`·`platform-compliance` | ≈ 现在的 `validators.py`（但只检像素规格，不检"AI 味"） | 差一层 |

**收束后：6 族 / 约 20 类。** 现在覆盖 6 类（位置 1-7 里去重后），缺口约 14 类。

---

## 3. 关键机制缺口（这三条决定"能不能扩"）

### 3.1 `gen_with_ref`：参考图进模型这条路，我一条都没建

| | 保真机制 | 出处 | 输出面 |
|---|---|---|---|
| **本项目** | 主体**从不进模型**，像素确定性贴入 | 不变量 A/B | 被锁在"能确定性合成的构图" |
| B | `PRODUCT_REF_LOCK` 常量（`generate.py:408-415`）注入每个 prompt + `--product-images` | "You MUST use the reference image as the EXACT basis… You may ONLY change: background scene, camera angle, lighting, model pose." | 无限 |
| C | `--image` 传参考产品图（"比文字描述更有效"） | `SKILL.md`「Prompt 精简原则」 | 无限 |
| A | `fission-pattern` 三段式：段1 商品保真**逐字相同** | §3「一致性的关键」 | 无限 |

**结论**：三库所有"出人像 / 出场景 / 出拼图"的能力都建立在"参考图进模型"上。我的判据（**画面里有没有事实成分**）本身比三库锐利，但被我用成了"全项目只有一格能调模型"——正确导出应是**按格判**：

```
这一格的画面里有什么？
├─ 只有环境/氛围/光（无人持有事实）      → 纯生成            ← 位置 4（已有）
├─ 商品本体（可抠图，是事实）             → 确定性合成        ← 位置 1/2/3/5/6/7（已有）
└─ 商品 + 模特/手/使用动作（事实之外有人形）→ 参考图进模型    ← 缺这条路
```

第三条今天无解，所以"模特展示 / 穿戴 / 多场景拼图"整族出不来。

### 3.2 「锁定资产」：三库都有，我没有

- B：内置模特库 **45 个**（`assets/models.json`）→ 选定即 `model_image_path`；或 AI 生成后**两阶段确认→锁定**，再用它出其余 6 种（`SKILL.md` 4.5）。**这就是库 B 的"同源"机制**：锁一张参考图，全批复用。
- A：`brand.model.reference` 锁脸；`gen.mjs` 自动把它"并进 `--images`"。
- 我：`subject.png` 只有一份（结构上更强），但**没有"锁定一张非主体资产"的概念**。

追加一条与同源并列的机制：**`lock_*` 槽位的产物必须落进 run 目录并记 sha256**，复用判据同 `subject_sha256`。

### 3.3 按格覆盖（`--per-type-*`）

B：`--per-type-templates key_features:2,material:3`（覆盖全局 `--template-set`）。
我：完全没有"同一批内按格覆盖参数"的能力——`--text-mode` 是全局开关。

---

## 4. 三库没有、只有我有的（不许伪装成有出处）

| 我的设计 | 三库的最接近物 | 差在哪 |
|---|---|---|
| **竞品图作为输入** | C `09-before-after`（自家前后）、C `14-multi-product`（自家套装）、A fission-pattern #5（尺寸参照物） | 三库的"对比"全是**自家内容的并置**或**版式**，没有"把别人的图当输入"。这是本项目独有的输入槽位，理由是合规（`brand.forbidden_on_image` 禁竞品品牌名）。**出处只能写"用户需求"，不能写三库。** |
| **主体像素结构性不进模型** | B/C/A 都是"进模型 + 强约束 + 事后质检" | 这是本项目**更强**的一条，不是缺口。保留。 |
| **`mandatory: true` 平台强制项** | A `platform-specs.md` 的 `pure_white_bg` 等是**机检规则**，不是"不可关闭的开关" | 语义不同：三库是"事后校验"，我是"事前禁止关闭"。保留（但可合并到平台档位表）。 |
| **E0 签字（6 条人工项）** | A `detect-task` 的视觉模型质检（8 项判定 + 风险等级）；B Step 0 前置闸 | 三库**用模型判**，我用**人签**。我的理由（"硬写启发式检测器产出的是不可靠的告警"）成立；但 A 的 `detect-task` 是一条更贵的替代路径，值得作为可选层。 |

---

## 5. 待建消费方清单（按项目纪律，先建消费方再进表）

| 新字段 | 消费方（待建） |
|---|---|
| `use: {ref_front: subject}` | `assets.resolve` 改为按槽位 id 查表（替代 `needs` 字符串） |
| `ref_model` / `ref_pose` / `copy_scenes` / `copy_audience` | `intake.run_e0`（素材门槛）+ `gen_with_ref` 的 prompt 组装 |
| `enum_template`（+ 按格覆盖） | `orchestrator._slot_plan`（把模板并入 `ctx`） |
| `family` | `gen_slot_cards.py`（分族出卡）+ `orchestrator` 的"族内顺序" |
| `enum_platform` 扩展为规则表 | `validators.py`（现在硬编码 amazon 口径）+ `schema.py` |
| `list_skus` | `orchestrator` 外层的批量驱动（**新对象**，见缺口） |

---

## 6. 建议的落地顺序

1. **`gen_with_ref` + `ref_model`**（解锁"模特/穿戴/拼图"整族）——唯一的"能力型"改动。
2. **输入表独立 + `use` 映射**（把一维表变二维）——数据改动，不新增调用。
3. **平台档位表**（`site: US` → 6 平台 × 10 字段）——纯数据，立刻可机检。
4. **`enum_template` + 按格覆盖**（风格变体）——纯数据 + 一个 `ctx` 键。
5. 批量轴（`list_skus`）——需要新对象，最后做。
