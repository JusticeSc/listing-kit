/**
 * Product V2 Provider 感知 Prompt 编译器（V2.3.4，计划 §9.7）与 Prompt 人工编辑版本（V2.3.6，计划 §9.9）。
 *
 * 唯一权威：平台档、Provider 档、分段规则、语言策略、冲突判定、来源引用与请求快照都在本文件。
 * 三条不可协商的规则：
 *  1) 指令段统一中文；任何非中文原文必须来自输入并以「」逐字引用——没有无规则的中英混杂；
 *  2) 图中文案只印用户明确选择并确认的条目（`shot_spec.on_image_texts`），逐字使用、不翻译、
 *     不改写、不新增；印字决定角色默认「未决定」时阻断，任何角色都不把绑定事实自动印上图；
 *  3) 编译是纯函数：失败抛 CONTRACT_INVALID 并给出精确问题，不产半成品、不修改输入。
 *
 * 复用而不是重写：依赖判定用 suite-plan.js 的 evaluateShot；规格校验用 specs.js；
 * hash 复用 storage/db.js 的 WebCrypto sha256Hex，由调用方注入（与 repository 的 digest 注入同法）。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { assertReworkDirective, reworkProblemLabel } from "./rework.js";
import { checkShotDraft, consumedSlotIdsOf, evaluateShot, roleDefinition, shotSignatureOf } from "./suite-plan.js";
import {
  MEASUREMENT_SOURCE_LABEL,
  PRESENTATION_CONSUMERS,
  PRESENTATION_FIELDS,
  PRINT_DECISION_ROLES,
  SHOT_LAYOUTS,
  SHOT_PRINT_INTENTS,
  SHOT_SPEC_SCHEMA_VERSION,
  STYLE_SPEC_SCHEMA_VERSION,
  assertShotSpec,
  assertStyleSpec,
  effectivePrintIntentOf,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  formatMeasurementText,
  imageTextProblems,
  imageTextSourceOf,
  layoutLabelOf,
  presentationStateOf,
  printDecisionRoleOf,
  referenceViewpointEvidence,
} from "./specs.js";
import { invalidationsFor } from "./invalidation.js";
import {
  canonicalJson,
  isNonEmptyString,
  isPlainObject,
  isPositiveInteger,
  isSha256Hex,
  pushProblem,
} from "./shared.js";

export const PROMPT_SCHEMA_VERSION = 2;
export const LEGACY_PROMPT_SCHEMA_VERSION = 1;
export const PROMPT_COMPILER_RULE_VERSION = 3;
export const PROMPT_LANGUAGE_POLICY_ID = "zh-instruction-v1";
export const MAX_PROMPT_CHARS = 4000;

// 冻结参考图合同已独立成 frozen-reference.js（attempt 校验复用同一判据，不成环）；
// 这里原样再导出，既有导入路径保持不变。canonicalJson 的唯一出处是 shared.js。
export {
  MAX_REFERENCE_SELECTION,
  REFERENCE_USES,
  checkFrozenReferences,
} from "./frozen-reference.js";
import {
  MAX_REFERENCE_SELECTION,
  REFERENCE_USES,
  checkFrozenReferences,
} from "./frozen-reference.js";

/** 逐字条目允许的语言标签；`neutral` 用于纯数字/符号文案（例如「30」「500 ml」这类无字母内容）。 */
export const PROMPT_LITERAL_LANGUAGES = Object.freeze(["zh", "en", "mixed", "neutral"]);

/**
 * 这张图的有效印字决定与版面。选择只在规格里明确存过时才生效；没存过时：
 * 印字决定角色（信息图/尺寸/对比/成分/包装）是「未决定」，由编译器阻断并让用户做一次普通选择；
 * 其他角色（主图/场景/细节/自定义）是「不印新增文字」——它们的画面本来就不叠加文案。
 * 任何角色都不会把绑定事实自动印上图（facts_auto 已退役）。
 * @param {unknown} shotSpec
 * @param {unknown} shot
 * @returns {{intent: string, layout: string, texts: import("./type-contracts.js").OnImageText[], decision_role: boolean}}
 */
export function effectivePrinting(shotSpec, shot) {
  const spec = isPlainObject(shotSpec) ? shotSpec : {};
  return {
    intent: effectivePrintIntentOf(shotSpec, shot),
    layout: SHOT_LAYOUTS.includes(spec.layout) ? spec.layout : "product_only",
    texts: (Array.isArray(spec.on_image_texts) ? spec.on_image_texts : []).filter(isPlainObject),
    decision_role: printDecisionRoleOf(shot),
  };
}

/**
 * 这张图的有效展示决定：单图覆盖优先，其次共用默认；缺失即「未决定」。
 * `consumes` 是「问不问」的投影依据：不消费该决定的用途既不被拦截，也不产出对应正文。
 * @param {unknown} styleSpec
 * @param {unknown} shotSpec
 * @param {unknown} shot
 * @returns {{appearance_state: {state: string, source: string}, contents_state: {state: string, source: string}, viewpoint: {state: string, source: string}, consumes: {appearance_state: boolean, contents_state: boolean, viewpoint: boolean}}}
 */
export function effectivePresentation(styleSpec, shotSpec, shot) {
  const roleId = isPlainObject(shot) && typeof shot.role_id === "string" ? shot.role_id : "";
  /** @param {string} key */
  const pick = (key) => {
    const own = isPlainObject(shotSpec) && isPlainObject(shotSpec.presentation) ? shotSpec.presentation : {};
    if (Object.prototype.hasOwnProperty.call(own, key)) {
      return { state: presentationStateOf(shotSpec, key), source: "shot" };
    }
    const shared = isPlainObject(styleSpec) && isPlainObject(styleSpec.presentation) ? styleSpec.presentation : {};
    if (Object.prototype.hasOwnProperty.call(shared, key)) {
      return { state: presentationStateOf(styleSpec, key), source: "style" };
    }
    return { state: key === "viewpoint" ? "reference_visible" : "undecided", source: "none" };
  };
  const contents = pick("contents_state");
  return {
    appearance_state: pick("appearance_state"),
    contents_state: contents,
    viewpoint: pick("viewpoint"),
    consumes: {
      appearance_state: PRESENTATION_CONSUMERS.appearance_state.includes(roleId),
      contents_state: PRESENTATION_CONSUMERS.contents_state.includes(roleId)
        || ["empty", "as_shown"].includes(contents.state),
      viewpoint: true,
    },
  };
}

/** 本图消费的共用风格签名：只封印本图实际会用到的共用风格字段——
 * 四个文本字段与 avoid 全量；presentation 仅取「本图消费且未被单图覆盖」的字段。
 * 被单图覆盖的共用值变化不使本图过期（单图覆盖自身的变化由 shot_spec_version 负责）。
 * @param {unknown} styleSpec
 * @param {unknown} shotSpec
 * @param {unknown} shot
 * @returns {string}
 */
export function styleSignatureOf(styleSpec, shotSpec, shot) {
  const style = isPlainObject(styleSpec) ? styleSpec : {};
  const spec = isPlainObject(shotSpec) ? shotSpec : {};
  const own = isPlainObject(spec.presentation) ? spec.presentation : {};
  const effective = effectivePresentation(styleSpec, shotSpec, shot);
  /** @type {Record<string, string>} */
  const presentation = {};
  for (const field of PRESENTATION_FIELDS) {
    if (!effective.consumes[field.key]) continue;
    if (Object.prototype.hasOwnProperty.call(own, field.key)) continue;
    const picked = effective[field.key];
    presentation[field.key] = picked && isNonEmptyString(picked.state) ? picked.state : "undecided";
  }
  return canonicalJson({
    background: isNonEmptyString(style.background) ? style.background : "",
    lighting: isNonEmptyString(style.lighting) ? style.lighting : "",
    color_tone: isNonEmptyString(style.color_tone) ? style.color_tone : "",
    composition: isNonEmptyString(style.composition) ? style.composition : "",
    avoid: Array.isArray(style.avoid) ? style.avoid.filter((item) => isNonEmptyString(item)) : [],
    presentation: presentation,
  });
}

/**
 * 普通决定的阻断集合（#9）：印字决定与展示决定的可判定性检查，唯一权威。
 * 编译器在编译前调用它；生成前确认单也调用它，好把用户指到真正该改的地方，
 * 而不是笼统地说「还没有 Prompt」。只返回问题，不抛错、不修改输入。
 * @param {{shot: unknown, shotSpec?: unknown, styleSpec?: unknown, brief?: unknown}} input
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function decisionProblems(input = {}) {
  const shot = isPlainObject(input.shot) ? input.shot : {};
  const shotSpec = isPlainObject(input.shotSpec) ? input.shotSpec : {};
  const brief = isPlainObject(input.brief) ? input.brief : null;
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  const confirmed = new Map((brief && Array.isArray(brief.confirmed_facts) ? brief.confirmed_facts : [])
    .filter((item) => isPlainObject(item)).map((item) => [item.slot_id, item]));
  const boundIds = Array.isArray(shot.fact_slot_ids) ? shot.fact_slot_ids : [];
  const allowsText = (PLATFORM_PROFILES[input.platformId || "amazon_us"] || PLATFORM_PROFILES.amazon_us)
    .on_image_text_roles.includes(shot.role_id);
  const printing = effectivePrinting(shotSpec, shot);
  const boundCount = brief ? boundIds.filter((slotId) => confirmed.has(slotId)).length : boundIds.length;
  // 只有确实有可印内容（绑定了已确认事实）时才需要这个决定；没有可印内容时未决定不产生歧义。
  if (printing.intent === "undecided" && allowsText && boundCount > 0) {
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot_spec.print_intent",
      message: "这张图还没有决定要不要印文字：请明确选择要印的文案（或选择不印新增文字），"
        + "程序不会把绑定的 " + boundCount + " 条商品事实自动印上图。",
    });
  }
  if (printing.intent === "selected") {
    if (!allowsText) {
      problems.push({
        code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot_spec.print_intent",
        message: "该角色的图片不允许新增文字，不能选择要印的文案；请改用不印新增文字，或换成允许图上文字的角色。",
      });
    }
    // 版面与印字必须自洽：选了要印文案却用「仅商品」版面会在同一份提示词里给出互相矛盾的指令
    // （「不叠加标题或参数文字」+「图中文案」），所以这里拦下并要求用户明确选一次版面。
    const layoutValue = isPlainObject(shotSpec) && isNonEmptyString(shotSpec.layout)
      ? shotSpec.layout : "";
    if (!layoutValue) {
      problems.push({
        code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot_spec.layout",
        message: "这张图要印文案，还得先决定版面：「商品在左，文字在右」或「商品在右，文字在左」；"
          + "程序不替你默认文字放哪边。",
      });
    } else if (!TEXT_LAYOUTS.includes(layoutValue)) {
      problems.push({
        code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot_spec.layout",
        message: "要印文案的图不能选「" + layoutLabelOf(layoutValue)
          + "」版面：那样会同时要求「不出现文字」和「印出文字」。请改成商品在左或商品在右的版面。",
      });
    }
    if (printing.texts.length === 0) {
      problems.push({
        code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot_spec.on_image_texts",
        message: "选择了要印的文案，但还没有任何条目：请先选择并确认至少一条图中文字。",
      });
    }
    const basisVersions = new Map((brief && Array.isArray(brief.basis) ? brief.basis : [])
      .filter((item) => isPlainObject(item) && isNonEmptyString(item.slot_id))
      .map((item) => [item.slot_id, item.version]));
    printing.texts.forEach((item, index) => {
      const path = "$.shot_spec.on_image_texts[" + index + "]";
      const text = isNonEmptyString(item.text) ? item.text.trim() : "";
      if (!isNonEmptyString(item.text_id)) {
        problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: path + ".text_id",
          message: "图中文字缺少稳定的条目 id。" });
      }
      if (!text) {
        problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: path + ".text",
          message: "图中文字不能为空。" });
      }
      if (item.status !== "confirmed") {
        problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: path + ".status",
          message: "图中文字「" + text + "」还是待确认状态：确认后才能发送，程序不会替你确认或跳过。",
        });
      }
      const source = imageTextSourceOf(item);
      const sourceId = source?.document_id;
      if (!brief || !source || !confirmed.has(sourceId)) {
        problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: path + ".source",
          message: "图中文字「" + text + "」的来源事实没有确认值：" + String(sourceId || "（未指定）") + "。" });
      } else if (basisVersions.get(sourceId) !== source.version) {
        problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: path + ".source.version",
          message: "图中文字「" + text + "」的来源已改变；请核对后重新确认，不会悄悄替换文案。" });
      } else if (!boundIds.includes(sourceId)) {
        problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: path + ".source",
          message: "图中文字「" + text + "」的来源已不在本图绑定里，请重新绑定或移除该文案。" });
      }
      for (const problem of imageTextProblems(item, { brief, shotSpec })) {
        problems.push({ ...problem, path: path + problem.path.slice(1) });
      }
    });
  }
  // 版面与印字必须自洽，两个方向都拦：
  // - 要印文案却用「仅商品」版面（上面在 selected 分支里拦）——同一份提示词会同时要求
  //   「不叠加标题或参数文字」与「印出文字」；
  // - 没有要印的文字却用文字版面——版面正文会写「放置下方给定的文字」，而本次没有任何文案，
  //   等于让模型为不存在的文字留位置。
  const layoutValue = isPlainObject(shotSpec) && isNonEmptyString(shotSpec.layout)
    ? shotSpec.layout : "";
  if (TEXT_LAYOUTS.includes(layoutValue) && printing.intent === "none") {
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot_spec.layout",
      message: "这张图不会有图上文字，不能选「" + layoutLabelOf(layoutValue) + "」版面："
        + "正文会写「放置下方给定的文字」，而本次没有文案可放。"
        + "请改成「" + layoutLabelOf("product_only") + "」版面，或先决定并选择要印的文案。",
    });
  }
  // 展示决定：未决定且被本图消费时阻断，不默选清洁/倒空；不消费的用途不拦截。
  const presentation = effectivePresentation(input.styleSpec, shotSpec, shot);
  for (const field of PRESENTATION_FIELDS) {
    if (!presentation.consumes[field.key]) continue;
    if (presentation[field.key].state !== "undecided") continue;
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID,
      path: (presentation[field.key].source === "shot" ? "$.shot_spec.presentation." : "$.presentation.") + field.key,
      message: "这张图还要先决定「" + field.label + "」："
        + field.options.filter((item) => item.value !== "undecided")
          .map((item) => item.label).join("／")
        + "；程序不替你默认"
        + (field.key === "appearance_state" ? "清洁或保留使用痕迹" : "倒空或保留内容物") + "。",
    });
  }
  if (presentation.viewpoint.state !== "reference_visible") {
    const proof = viewpointProofOf(input, presentation.viewpoint.state);
    if (!proof.viewpoints.includes(presentation.viewpoint.state)) {
      problems.push({ code: DOMAIN_ERROR_CODES.CONTRACT_INVALID,
        path: presentation.viewpoint.source === "shot" ? "$.shot_spec.presentation.viewpoint" : "$.presentation.viewpoint",
        message: "所选视角没有本次商品依据支持；请确认相应照片、选入本图依据，或改为沿用可见视角。" });
    }
  }
  return problems;
}

/** 能承载图中文字的版面（与「只放商品」互斥）；界面与编译门共用这一份。 */
export const TEXT_LAYOUTS = Object.freeze(["product_left_text_right", "product_right_text_left"]);

/**
 * 角色 → 正向画面简报（画面概念/主体位置与大小/视角/留白/光线/清晰度）。
 * 这是「专业表达由系统承担」的落点：普通用户只需要做用途与普通选择，不需要写摄影术语。
 * 只写该用途的通用视觉方法，不声称任何商品事实，也不补造不可见结构。
 * @type {Readonly<Record<string, readonly string[]>>}
 */
export const ROLE_VISUAL_BRIEF = Object.freeze({
  main: Object.freeze([
    "画面概念：干净的商品展示图，主体是商品本身，没有干扰元素。",
    "主体：商品完整入画、居中放置，任何边角都不被裁断；四周留白均匀，商品主体占画面大部分。",
    "视角：沿用商品依据里可见的视角平视拍摄，不虚构背面、内部或未见的部件。",
    "光线：柔和均匀的布光，商品受光完整、颜色准确，投影干净不浑浊。",
  ]),
  infographic: Object.freeze([
    "画面概念：用少量标注讲清卖点的信息图，商品是主体，文字服务卖点且不遮盖商品。",
    "主体：商品完整入画、位置突出；文案区放在留白一侧，与商品之间留出干净空隙。",
    "文字层级：一行标题加若干要点，字号按层级递减、行距清晰，与背景对比充分，不压在商品细节上。",
    "排版：对齐一致、边距统一，文字水平排布，不使用旋转、变形或装饰性字体。",
  ]),
  scene: Object.freeze([
    "画面概念：商品在真实使用场景里的样子，场景说明用途但不抢商品焦点。",
    "主体：商品居中偏前、完整入画，与场景里的道具保持自然比例关系。",
    "光线与环境：符合场景的自然光线，方向明确、明暗过渡自然；背景轻微虚化以突出商品。",
    "一致性：场景与道具不出现其它品牌标识，也不与商品的材质、颜色冲突。",
  ]),
  detail: Object.freeze([
    "画面概念：近距离特写，让材质、工艺或关键部件的细节看得清。",
    "主体：特写区域占画面主要部分，边缘不切断关键结构。",
    "光线：侧向或斜上方柔和光线，突出纹理与层次，避免过曝和死黑。",
    "清晰度：焦点落在细节上，背景自然虚化。",
  ]),
  size: Object.freeze([
    "画面概念：说明尺寸的图，商品完整入画，标注指向对应部位。",
    "主体：商品居中、比例不变形，四周留出标注空间。",
    "标注：尺寸线指向对应部位；数值与单位只允许逐字使用已确认尺寸；取不到可逐字引用的数值时就不标数字，不编造数字与单位。字号可读，颜色与背景对比充分。",
    "光线：均匀柔和，避免投影盖住标注区域。",
  ]),
  comparison: Object.freeze([
    "画面概念：商品与参照物同框对比，差异一眼可见。",
    "主体：双方对齐摆放、比例真实、背景一致，不美化其中任意一方。",
    "标注：对比项逐字使用已确认文案，指向明确、不遮挡商品。",
    "光线：同一光源、同一方向，避免一侧过亮一侧过暗。",
  ]),
  ingredient: Object.freeze([
    "画面概念：呈现成分或材质构成的图，商品与成分元素清爽排布。",
    "主体：商品完整清晰，成分元素按类别分组摆放、不相互遮挡。",
    "标注：名称逐字使用已确认文案，指向明确、字号可读。",
    "光线：柔和顶光，材质质感清楚、颜色准确。",
  ]),
  packaging: Object.freeze([
    "画面概念：呈现包装形态与随附物品的图，物品摆放整齐、形态完整。",
    "主体：包装与随附物品都完整入画，彼此不遮挡，也不添加未确认的赠品。",
    "背景与光线：干净背景、柔和光线，包装表面反光控制得当，标识清晰。",
    "视角：正面或轻微俯视，让包装与内容物一眼可辨。",
  ]),
  custom: Object.freeze([
    "画面概念：按这张图的用途清晰呈现商品，画面元素服务用途。",
    "主体：商品完整入画、位置突出，四周留白干净。",
    "光线：柔和自然，颜色与材质准确。",
  ]),
});

/** 显式视角的正向正文（#9）：非默认视角通过依据门后，替换角色简报里的默认视角句，
 * 正面消费用户所选角度，不用「平视拍摄」这类默认表达与顶视/侧视互相矛盾。 */
const VIEWPOINT_SENTENCES = Object.freeze({
  front: "视角：按用户明确选择的正面视角呈现；正面可见的结构、比例与标识以本次商品依据为准，不虚构背面、内部或未见的部件。",
  side: "视角：按用户明确选择的侧面视角呈现；侧面可见的结构、比例与标识以本次商品依据为准，不虚构其它未见的角度或内部结构。",
  top: "视角：按用户明确选择的顶视视角呈现；顶面可见的结构与比例以本次商品依据为准，不虚构内部或未见的部件。",
});

/** 版面段落正文：正向描述商品与文字的分布，不靠一堆禁止来暗示排版。 */
const LAYOUT_SENTENCES = Object.freeze({
  product_only: "画面只呈现商品主体：主体完整入画、位置突出，四周保留干净留白，不叠加标题或参数文字。",
  product_left_text_right: "商品完整放在画面左侧约三分之二区域，关键部位不被裁切也不被文字遮挡；右侧保留干净留白放置下方给定的文字。",
  product_right_text_left: "商品完整放在画面右侧约三分之二区域，关键部位不被裁切也不被文字遮挡；左侧保留干净留白放置下方给定的文字。",
});

/** 语言策略的机读声明：指令中文；图中文字语言随平台。 */
export const PROMPT_LANGUAGE_POLICY = Object.freeze({
  policy_id: PROMPT_LANGUAGE_POLICY_ID,
  instruction_language: "zh",
  on_image_text_language_source: "platform",
  verbatim_only: true,
  rules: Object.freeze([
    "指令段只写中文；非中文原文必须用「」引用。",
    "图中文字逐字等于用户所选并确认的文案（来源可为已确认事实值），禁止翻译、改写或补全。",
    "所选文案的来源事实版本前进后必须重新确认，程序不静默改用新值。",
    "事实值语言与平台语言不一致时给警告，交人工决定。",
  ]),
});

/** 平台档：语言、主图硬规则、允许叠加文字的角色。 */
export const PLATFORM_PROFILES = Object.freeze({
  amazon_us: Object.freeze({
    platform_id: "amazon_us",
    version: 1,
    label: "亚马逊美国站",
    on_image_text_language: "en",
    on_image_text_roles: Object.freeze([
      "infographic", "size", "comparison", "ingredient", "packaging",
    ]),
    main_image: Object.freeze({
      background_phrase: "纯白无缝背景「RGB(255,255,255)」",
      min_occupancy_percent: 85,
    }),
    base_rules: Object.freeze([
      "整套图片不得出现水印、边框、联系方式或与商品无关的叠加元素。",
      "只能使用已确认的商品事实，不添加未确认的参数、功效或承诺。",
    ]),
  }),
});

export const IMAGE_PROFILE_VERSION_PATTERN = /^v[0-9A-Za-z._-]{1,40}$/;
export const IMAGE_SIZE_PATTERN = /^[0-9]{1,4}\*[0-9]{1,4}$/;

/**
 * 有效图像 Prompt 档（V2.R5.3）：从 capabilities.images 的 provider 能力投影出的
 * 非秘密请求 profile，平铺绑定目标身份与协议。credential_source / configured /
 * 密钥等凭据字段永不进入本档，因此也不进 basis 与请求 hash。
 *
 * 字段来源是服务端正式能力块：版本取 images.provider.capability_version，
 * 协议取 images.contract，请求参数取 images.provider.capabilities.request_profile。
 * 缺字段即拒绝（不猜参数、不兜底 model 表）。
 */
/** @type {readonly string[]} */
export const IMAGE_PROFILE_FIELDS = Object.freeze([
  "size", "n", "prompt_extend", "watermark", "output_format",
  "supports_negative_prompt_field", "max_reference_images", "reference_media_types",
  "min_side", "max_side", "min_area", "max_area", "min_ratio", "max_ratio",
  "max_prompt_chars",
]);

function isPositiveNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/** 尺寸是否落在某一档声明的边/面积/比例范围内；返回 null 表示合法。
 * @param {unknown} profile
 * @param {unknown} size
 * @returns {string | null}
 */
export function sizeScopeProblem(profile, size) {
  if (!isNonEmptyString(size) || !IMAGE_SIZE_PATTERN.test(size)) {
    return "尺寸必须是「宽*高」格式。";
  }
  const parts = size.split("*");
  const width = Number(parts[0]);
  const height = Number(parts[1]);
  if (width < profile.min_side || width > profile.max_side
      || height < profile.min_side || height > profile.max_side) {
    return "尺寸边长超出档位 " + profile.min_side + ".." + profile.max_side + "。";
  }
  if (width * height < profile.min_area || width * height > profile.max_area) {
    return "尺寸面积超出档位 " + profile.min_area + ".." + profile.max_area + "。";
  }
  const ratio = width / height;
  if (ratio < profile.min_ratio || ratio > profile.max_ratio) {
    return "尺寸长宽比超出档位 " + profile.min_ratio + ".." + profile.max_ratio + "。";
  }
  return null;
}

/** 有效 Prompt 档的形状与自洽检查；返回问题列表（空 = 合法）。
 * @param {unknown} profile
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkImagePromptProfile(profile) {
  const problems = [];
  if (!isPlainObject(profile)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "图像 Prompt 档必须是对象。");
    return problems;
  }
  if (!isNonEmptyString(profile.provider_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider_id", "图像 Prompt 档缺少 provider_id。");
  }
  if (!isNonEmptyString(profile.model_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.model_id", "图像 Prompt 档缺少 model_id。");
  }
  if (!isPositiveInteger(profile.version)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.version", "图像 Prompt 档版本必须是正整数。");
  }
  if (!isNonEmptyString(profile.protocol) || !IMAGE_PROFILE_VERSION_PATTERN.test(String(profile.protocol))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.protocol", "图像 Prompt 档协议版本不合法。");
  }
  for (const key of ["n", "max_reference_images", "min_side", "max_side",
                     "min_area", "max_area", "max_prompt_chars"]) {
    if (!isPositiveInteger(profile[key])) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "图像 Prompt 档 " + key + " 必须是正整数。");
    }
  }
  for (const key of ["min_ratio", "max_ratio"]) {
    if (!isPositiveNumber(profile[key])) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "图像 Prompt 档 " + key + " 必须是正数。");
    }
  }
  for (const key of ["prompt_extend", "watermark", "supports_negative_prompt_field"]) {
    if (typeof profile[key] !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "图像 Prompt 档 " + key + " 必须是布尔值。");
    }
  }
  if (!isNonEmptyString(profile.output_format)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.output_format",
      "图像 Prompt 档缺少输出格式。");
  }
  if (!Array.isArray(profile.reference_media_types) || profile.reference_media_types.length === 0
      || profile.reference_media_types.some((item) => !isNonEmptyString(item))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.reference_media_types",
      "图像 Prompt 档必须声明非空的参考图媒体类型。");
  }
  if (problems.length === 0) {
    if (profile.min_side > profile.max_side) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.min_side", "图像 Prompt 档边长上下限颠倒。");
    }
    if (profile.min_area > profile.max_area) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.min_area", "图像 Prompt 档面积上下限颠倒。");
    }
    if (profile.min_ratio > profile.max_ratio) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.min_ratio", "图像 Prompt 档比例上下限颠倒。");
    }
    const sizeProblem = sizeScopeProblem(profile, profile.size);
    if (sizeProblem) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.size", "默认尺寸不合法：" + sizeProblem);
    }
  }
  return problems;
}

/**
 * @param {unknown} profile
 * @returns {import("./type-contracts.js").ImagePromptProfile}
 */
export function assertImagePromptProfile(profile) {
  const problems = checkImagePromptProfile(profile);
  if (problems.length > 0) {
    invalid("图像 Prompt 档不合法：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
  return profile;
}

/**
 * 从 capabilities 的 images 块投影有效 Prompt 档（V2.R5.3）。
 * 只读版本（provider.capability_version）、协议（images.contract）与非秘密 request_profile；
 * 不取 credential_source / configured，缺字段或字段非法直接拒绝。
 * @param {unknown} images
 * @returns {import("./type-contracts.js").ImagePromptProfile}
 */
export function imagePromptProfile(images) {
  if (!isPlainObject(images)) invalid("图像能力块缺失：无法投影有效 Prompt 档。");
  const contract = images.contract;
  if (!isNonEmptyString(contract) || !IMAGE_PROFILE_VERSION_PATTERN.test(contract)) {
    invalid("图像能力块的协议版本（images.contract）缺失或不合法。");
  }
  const provider = isPlainObject(images.provider) ? images.provider : null;
  if (!provider) invalid("图像能力块缺少 provider：不能投影 Prompt 档。");
  if (!isNonEmptyString(provider.provider_id)) invalid("图像能力块缺少 provider_id。");
  if (!isNonEmptyString(provider.model_id)) invalid("图像能力块缺少 model_id。");
  if (!isPositiveInteger(provider.capability_version)) {
    invalid("图像能力块缺少有效版本（images.provider.capability_version）。");
  }
  const capabilities = isPlainObject(provider.capabilities) ? provider.capabilities : null;
  const raw = capabilities && isPlainObject(capabilities.request_profile)
    ? capabilities.request_profile : null;
  if (!raw) invalid("图像 provider 缺少 request_profile：不能猜测请求参数。");
  const profile = {
    provider_id: provider.provider_id,
    model_id: provider.model_id,
    version: provider.capability_version,
    protocol: contract,
    size: raw.size,
    n: raw.n,
    prompt_extend: raw.prompt_extend,
    watermark: raw.watermark,
    output_format: raw.output_format,
    supports_negative_prompt_field: raw.supports_negative_prompt_field,
    max_reference_images: raw.max_reference_images,
    reference_media_types: Array.isArray(raw.reference_media_types)
      ? [...raw.reference_media_types] : raw.reference_media_types,
    min_side: raw.min_side,
    max_side: raw.max_side,
    min_area: raw.min_area,
    max_area: raw.max_area,
    min_ratio: raw.min_ratio,
    max_ratio: raw.max_ratio,
    max_prompt_chars: raw.max_prompt_chars,
  };
  return assertImagePromptProfile(profile);
}

/* ------------------------------------------------------------ 基础工具 */

/**
 * @param {string} kind
 * @param {Record<string, object>} table
 * @param {string} id
 * @returns {object}
 */
function resolveProfile(kind, table, id) {
  const value = table[id];
  if (!value) invalid(kind + "档不存在：" + String(id));
  return value;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function normalizePhrase(value) {
  return String(value == null ? "" : value).normalize("NFKC").toLowerCase().replace(/\s+/g, "");
}

/** 把用户值变成安全引用：控制字符转空格、引号中和、空白归一，避免引用边界被值本身破坏。
 * @param {unknown} value
 * @returns {string}
 */
export function quoteLiteral(value) {
  const clean = String(value == null ? "" : value)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/「/g, "（").replace(/」/g, "）")
    .replace(/“/g, "（").replace(/”/g, "）")
    .replace(/‘/g, "（").replace(/’/g, "）")
    .replace(/\s+/g, " ")
    .trim();
  if (!clean) invalid("引用文本不能为空。");
  return "「" + clean + "」";
}

function hasCjk(text) {
  return /[\u3400-\u9fff]/.test(String(text));
}

function hasAsciiLetters(text) {
  return /[A-Za-z]/.test(String(text));
}

/** 文本的语言标签：zh / en / mixed；用于图中文字与平台语言的对照。 @param {unknown} text @returns {string} */
export function languageOf(text) {
  const cjk = hasCjk(text);
  const latin = hasAsciiLetters(text);
  if (cjk && latin) return "mixed";
  if (cjk) return "zh";
  if (latin) return "en";
  return "neutral";
}

/** @param {unknown} fact @returns {string[]} */
function factTexts(fact) {
  const value = fact ? fact.value : null;
  if (Array.isArray(value)) {
    return value.filter((item) => typeof item === "string" && item.trim()).map((item) => item.trim());
  }
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (typeof value === "number" && Number.isFinite(value)) return [String(value)];
  return [];
}

/**
 * @param {string} key
 * @param {string} label
 * @param {string} kind
 * @param {string} text
 * @param {string[]} sourceRefs
 * @returns {import("./type-contracts.js").PromptSection}
 */
function section(key, label, kind, text, sourceRefs) {
  return Object.freeze({
    key: key,
    label: label,
    kind: kind,
    text: text,
    source_refs: Object.freeze([...new Set(sourceRefs)]),
  });
}

/**
 * @param {string} key
 * @param {string} label
 * @param {string} text
 * @param {import("./type-contracts.js").PromptTextItem[]} items
 * @param {string[]} sourceRefs
 * @returns {import("./type-contracts.js").PromptSection}
 */
function literalSection(key, label, text, items, sourceRefs) {
  return Object.freeze({
    key: key,
    label: label,
    kind: "literal",
    text: text,
    items: Object.freeze(items.map((item) => Object.freeze({ ...item }))),
    source_refs: Object.freeze([...new Set(sourceRefs)]),
  });
}

/**
 * @param {unknown} sections
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
function sectionProblems(sections) {
  const problems = [];
  if (!Array.isArray(sections) || sections.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.sections", "编译结果至少要有段落。");
    return problems;
  }
  sections.forEach((item, index) => {
    const path = "$.sections[" + index + "]";
    if (!isPlainObject(item)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "段落必须是对象。");
      return;
    }
    if (!isNonEmptyString(item.key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".key", "段落缺少 key。");
    }
    if (item.kind !== "instruction" && item.kind !== "literal" && item.kind !== "manual_edit") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".kind", "未知段落类型。");
    }
    if (!isNonEmptyString(item.text)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".text", "段落文本不能为空。");
    }
    if (!Array.isArray(item.source_refs) || item.source_refs.length === 0
        || item.source_refs.some((ref) => !isNonEmptyString(ref))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_refs",
        "每个段落必须至少有一个可追溯来源。");
    }
  });
  return problems;
}

/**
 * @param {unknown} sections
 * @returns {string[]}
 */
export function promptSourceRefs(sections) {
  const refs = [];
  for (const item of Array.isArray(sections) ? sections : []) {
    for (const ref of item && Array.isArray(item.source_refs) ? item.source_refs : []) {
      if (!refs.includes(ref)) refs.push(ref);
    }
  }
  return refs;
}

/** 去掉引用片段后剩下的裸文本；语言与泄漏检查共用这一份。 @param {unknown} text @returns {string} */
export function stripQuotedSpans(text) {
  return String(text == null ? "" : text)
    .replace(/「[^」]*」/g, " ")
    .replace(/『[^』]*』/g, " ")
    .replace(/“[^”]*”/g, " ")
    .replace(/‘[^’]*’/g, " ");
}

/** 语言检查：指令段不得出现未引用的英文；文中文字必须是逐字引用的字符串。 @param {unknown} sections @returns {import("./type-contracts.js").DomainProblem[]} */
export function checkPromptLanguage(sections) {
  const problems = [];
  for (const item of Array.isArray(sections) ? sections : []) {
    const path = "$.sections[" + String(item && item.key) + "]";
    if (!isPlainObject(item)) continue;
    if (item.kind === "instruction" || item.kind === "manual_edit") {
      const bare = stripQuotedSpans(item.text)
        .replace(/[0-9]/g, "")
        .replace(/[\s\u3000!-/:-@\[-`{-~。，、；：！？…—－（）《》【】·]/g, "");
      const runs = bare.match(/[A-Za-z]+/g) || [];
      if (runs.length > 0) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
          "指令段出现未引用的非中文内容：" + runs.join("、") + "；请用「」逐字引用。");
      }
    }
    if (item.kind === "literal") {
      const items = Array.isArray(item.items) ? item.items : [];
      if (items.length === 0) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "文字段没有逐字条目。");
      }
      for (const entry of items) {
        if (!isPlainObject(entry) || !/^「[^」]+」$/.test(String(entry.text || ""))) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
            "文中文字必须逐字放在「」里。");
          continue;
        }
        if (!PROMPT_LITERAL_LANGUAGES.includes(entry.language)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "文字条目缺少语言标签。");
        }
        if (!isNonEmptyString(entry.source_ref)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "文字条目缺少来源。");
        }
      }
    }
  }
  return problems;
}

/* ------------------------------------------------------ 冲突、泄漏与逐字 */

/** keep / change_allowed 与公共风格 avoid 的确定性冲突判定。 @param {unknown} shotSpec @param {unknown} styleSpec @returns {import("./type-contracts.js").DomainProblem[]} */
export function checkSpecConflicts(shotSpec, styleSpec) {
  const problems = [];
  const avoid = new Set((styleSpec.avoid || []).map(normalizePhrase));
  const change = new Set((shotSpec.change_allowed || []).map(normalizePhrase));
  for (const item of shotSpec.keep || []) {
    const key = normalizePhrase(item);
    if (avoid.has(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_spec.keep",
        "保持项与避免项冲突：" + item + "。");
    }
    if (change.has(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_spec.keep",
        "保持项与允许变化项冲突：" + item + "。");
    }
  }
  return problems;
}

/**
 * 未确认事实泄漏：conflict 值在任何位置出现都阻断（冲突必须先解决）；
 * 其余未确认状态只检查引用之外的裸文本——引用内容来自用户自己的输入，不算模型偷写事实。
 * @param {unknown} sections
 * @param {unknown} contextFacts
 * @param {{includeQuoted?: boolean}} [options]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkPromptLeaks(sections, contextFacts, options = {}) {
  const problems = [];
  const joined = (Array.isArray(sections) ? sections : [])
    .map((item) => (item && item.text) || "").join("\n");
  const full = normalizePhrase(joined);
  const bare = normalizePhrase(stripQuotedSpans(joined));
  for (const fact of Array.isArray(contextFacts) ? contextFacts : []) {
    if (!isPlainObject(fact) || fact.status === "confirmed") continue;
    for (const value of factTexts(fact)) {
      const phrase = normalizePhrase(value);
      if (phrase.length < 3) continue;
      const hit = (fact.status === "conflict" || options.includeQuoted === true)
        ? full.includes(phrase) : bare.includes(phrase);
      if (hit) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.sections",
          "未确认的「" + String(fact.slot_id) + "」值出现在提示词：" + value + "。");
      }
    }
  }
  return problems;
}

/** 图中文字必须与它声明的来源一致：所选文案对 `shot_spec.on_image_texts`（确认状态+原文），
 * 旧路径对已确认事实的逐字值；语言标签与内容一致。
 * @param {unknown} sections
 * @param {unknown} brief
 * @param {unknown} [shotSpec]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkLiteralVerbatim(sections, brief, shotSpec) {
  const problems = [];
  const confirmed = new Map(
    ((brief && brief.confirmed_facts) || [])
      .filter((item) => isPlainObject(item))
      .map((item) => [item.slot_id, item]));
  const selected = new Map(
    (isPlainObject(shotSpec) && Array.isArray(shotSpec.on_image_texts) ? shotSpec.on_image_texts : [])
      .filter((item) => isPlainObject(item) && isNonEmptyString(item.text_id))
      .map((item) => [item.text_id, item]));
  for (const item of Array.isArray(sections) ? sections : []) {
    if (!isPlainObject(item) || item.kind !== "literal") continue;
    for (const entry of Array.isArray(item.items) ? item.items : []) {
      const sourceRef = String(entry.source_ref || "");
      const inner = String(entry.text || "").replace(/^「/, "").replace(/」$/, "");
      if (sourceRef.startsWith("shot_spec.on_image_text:")) {
        const textId = sourceRef.slice("shot_spec.on_image_text:".length);
        const chosen = selected.get(textId);
        if (!chosen || chosen.status !== "confirmed" || String(chosen.text).trim() !== inner) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
            "$.sections[" + item.key + "]",
            "图中文字与所选条目不一致或尚未确认：" + entry.text);
          continue;
        }
        problems.push(...imageTextProblems(chosen, { brief, shotSpec }));
      } else {
        const slotId = sourceRef.replace(/^product_brief\.fact:/, "");
        const fact = confirmed.get(slotId);
        if (!fact || !factTexts(fact).includes(inner)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
            "$.sections[" + item.key + "]", "图中文字不是已确认事实的逐字值：" + entry.text);
          continue;
        }
      }
      const language = languageOf(inner);
      if (language !== "neutral" && entry.language !== language) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          "$.sections[" + item.key + "]", "文字条目的语言标签与内容不一致：" + entry.text);
      }
    }
  }
  return problems;
}

/* ------------------------------------------------------------ 编译器 */

/**
 * @param {unknown} input
 * @param {{platform_id: string, version: number}} platform
 * @param {import("./type-contracts.js").ImagePromptProfile} provider
 * @returns {import("./type-contracts.js").PromptBasis}
 */
export function promptBasisOf(input, platform, provider) {
  const versions = isPlainObject(input.versions) ? input.versions : {};
  const positive = (value) => (Number.isInteger(value) && value > 0 ? value : null);
  const shot = isPlainObject(input.shot) ? input.shot : null;
  const brief = isPlainObject(input.brief) ? input.brief : {};
  const confirmedIds = (Array.isArray(brief.confirmed_facts) ? brief.confirmed_facts : [])
    .filter((item) => isPlainObject(item) && isNonEmptyString(item.slot_id))
    .map((item) => item.slot_id);
  const consumed = shot ? consumedSlotIdsOf(shot, confirmedIds) : [];
  // 所选图中文案的来源事实也在这张图的消费范围内：来源版本前进时这张图必须过期。
  const printing = effectivePrinting(input.shotSpec, shot);
  const selectedSources = (printing.intent === "selected" ? printing.texts : [])
    .map(item => imageTextSourceOf(item)?.document_id).filter(isNonEmptyString);
  for (const slotId of selectedSources) {
    if (!consumed.includes(slotId)) consumed.push(slotId);
  }
  const viewpoint = effectivePresentation(input.styleSpec, input.shotSpec, shot).viewpoint.state;
  if (viewpoint !== "reference_visible") {
    const truthShas = (Array.isArray(input.references) ? input.references : [])
      .filter(item => Array.isArray(item.uses) && item.uses.includes("product_truth")).map(item => item.sha256);
    const relevant = (Array.isArray(input.slotEntries) ? input.slotEntries : []).filter(entry =>
      isPlainObject(entry) && isPlainObject(entry.slot)
      && (Array.isArray(entry.slot.value) ? entry.slot.value : [entry.slot.value]).includes(viewpoint));
    for (const proof of referenceViewpointEvidence(relevant, truthShas).slots) {
      if (!consumed.includes(proof.slot_id)) consumed.push(proof.slot_id);
    }
  }
  const consumedSet = new Set(consumed);
  // V2.R6.2：只冻结这张图实际消费的槽位版本，无关槽位变化不再使这张图的 Prompt 过期。
  const consumedBasis = (Array.isArray(brief.basis) ? brief.basis : [])
    .filter((item) => isPlainObject(item) && consumedSet.has(item.slot_id))
    .map((item) => ({ slot_id: item.slot_id, version: item.version }));
  return {
    compiler_rule_version: PROMPT_COMPILER_RULE_VERSION,
    brief: consumedBasis,
    consumed_slot_ids: consumed,
    // 这张图自己的确定性签名（与整份套图文档版本无关）；改别的图不让这张图过期。
    shot_signature: shot ? shotSignatureOf(shot) : null,
    suite_version: positive(versions.suite_version),
    style_version: positive(versions.style_version),
    style_signature: styleSignatureOf(input.styleSpec, input.shotSpec, shot),
    shot_spec_version: positive(versions.shot_spec_version),
    // 商品资料版本：冻结引用里嵌了它（sources[].version），提交门按完整元数据全等比较；
    // 依据里冻结同一版本，确认单才能用同一条判据如实报「商品资料已前进」。
    intake_version: positive(versions.intake_version),
    platform: { platform_id: platform.platform_id, version: platform.version },
    // 冻结完整有效档（含目标、协议、能力边界与请求参数）；凭据字段从不进入本档。
    provider: { ...provider },
    ...(isPlainObject(input.rework) ? {
      rework: {
        directive_id: input.rework.directive_id,
        candidate_id: input.rework.candidate_id,
        candidate_sha256: input.rework.candidate_sha256,
        problems: [...(Array.isArray(input.rework.problems) ? input.rework.problems : [])],
        mode: input.rework.mode,
        // 原改进方向随血缘冻结：人工编辑/重新确认要凭它授权返工指令段的逐字引用，
        // 不能依赖会随新版本失据的旧全文自证。
        direction: isNonEmptyString(input.rework.direction) ? input.rework.direction : "",
        problem_candidate: { ...input.rework.problem_candidate },
      },
    } : {}),
  };
}

/** 本次实际消费的商品原照 SHA 集合（与决定门同一判据：用途含 product_truth 且来源为商品输入）。 */
function activeTruthShas(references) {
  return (Array.isArray(references) ? references : [])
    .filter((item) => isPlainObject(item) && Array.isArray(item.uses) && item.uses.includes("product_truth")
      && Array.isArray(item.sources)
      && item.sources.some((source) => isPlainObject(source) && source.kind === "product_input"))
    .map((item) => item.sha256);
}

/** 所选非默认视角的参考图证据（决定门与正文来源共用这一份过滤）。 */
function viewpointProofOf(input, state) {
  const relevant = (isPlainObject(input) && Array.isArray(input.slotEntries) ? input.slotEntries : [])
    .filter((entry) => isPlainObject(entry) && isPlainObject(entry.slot)
      && (Array.isArray(entry.slot.value) ? entry.slot.value : [entry.slot.value]).includes(state));
  return referenceViewpointEvidence(relevant, activeTruthShas(isPlainObject(input) ? input.references : null));
}

/** 实际输入图序的职责正文（设计 §13.6/§13.14.5）：图号与用途只由最终冻结数组与明确模式推导，
 * 同字节双职责合并成同一条（不重复编号、不虚构图号）；数组形状不完整时不产半真正文。
 * 编辑模式只把候选当待修对象（不是商品事实权威），原照重生成不声称收到历史候选。
 * @param {unknown} references
 * @param {unknown} rework
 * @returns {{text: string, refs: string[], edit_source: boolean, mode: string | null} | null}
 */
function referenceInputsOf(references, rework) {
  if (!Array.isArray(references) || references.length === 0) return null;
  const items = references.map((item) => (isPlainObject(item) && isSha256Hex(item.sha256)
    && Array.isArray(item.uses) && item.uses.length > 0 ? { uses: item.uses } : null));
  if (items.some((item) => item === null)) return null;
  const indicesOf = (use) => {
    const list = [];
    items.forEach((item, index) => { if (item.uses.includes(use)) list.push(index); });
    return list;
  };
  const edits = indicesOf("edit_source");
  const products = indicesOf("product_truth");
  const styles = indicesOf("style_reference");
  const label = (list) => list.map((index) => "图" + (index + 1)).join("、");
  const dual = edits.filter((index) => products.includes(index));
  const editOnly = edits.filter((index) => !dual.includes(index));
  const productOnly = products.filter((index) => !dual.includes(index));
  const lines = ["输入依据（按实际发送顺序）："];
  if (dual.length > 0) {
    lines.push(label(dual)
      + "是本次要修改的问题候选，同时作为商品原照依据（同一张图片字节）：当前构图来自它，"
      + "商品的外形、比例、材质与标识也以它为准。");
  }
  if (editOnly.length > 0) {
    lines.push(label(editOnly)
      + "是本次要修改的问题候选，只提供当前画面构图，不是商品事实权威；商品外形一律以商品原照为准。");
  }
  if (productOnly.length > 0) {
    lines.push(label(productOnly) + "是商品原照，提供真实商品的外形、比例、材质、颜色与标识依据。");
  }
  if (styles.length > 0) {
    lines.push(label(styles) + "只作为风格参考（视觉语言），不作本商品的外观依据。");
  }
  const mode = isPlainObject(rework)
    && (rework.mode === "edit_candidate" || rework.mode === "regenerate_original") ? rework.mode : null;
  if (mode === "edit_candidate") {
    lines.push("本次按编辑候选处理：只针对返工要求指出的问题调整，其余满意的部分尽量保留；"
      + "输出仍是一张新的完整图片，不承诺未修改区域的像素完全不变。");
  } else if (mode === "regenerate_original") {
    lines.push("本次按商品原照重新生成完整目标，不发送历史候选图；问题候选只作为问题记录，不作为本次模型输入。");
  }
  const refs = ["intake.references"];
  if (mode === "edit_candidate" && isNonEmptyString(rework.candidate_id)) {
    refs.push("candidate:" + rework.candidate_id);
  }
  if (isPlainObject(rework) && isNonEmptyString(rework.directive_id)) {
    refs.push("rework:" + rework.directive_id);
  }
  return { text: lines.join(""), refs: refs, edit_source: edits.length > 0, mode: mode };
}

/**
 * @param {unknown} input
 * @returns {import("./type-contracts.js").CompiledPrompt}
 */
export function compilePrompt(input) {
  if (!isPlainObject(input)) invalid("Prompt 编译输入必须是对象。");
  const brief = input.brief;
  if (!isPlainObject(brief) || !Array.isArray(brief.confirmed_facts) || !Array.isArray(brief.basis)) {
    invalid("Prompt 编译需要合法的 ProductBrief（含 basis 与 confirmed_facts）。");
  }
  const shot = input.shot;
  if (!isPlainObject(shot)) invalid("Prompt 编译需要一张 Shot。");
  const problems = [];
  problems.push(...checkShotDraft(shot));
  const platform = resolveProfile("平台", PLATFORM_PROFILES, input.platformId || "amazon_us");
  const profileProblems = checkImagePromptProfile(input.providerProfile);
  if (profileProblems.length > 0) {
    invalid("Prompt 编译缺少有效 Provider 档：" + profileProblems[0].message,
      { problems: profileProblems.slice(0, 3) });
  }
  const provider = input.providerProfile;
  const styleSpec = input.styleSpec ? assertStyleSpec(input.styleSpec) : emptyStyleSpec();
  const shotSpec = input.shotSpec ? assertShotSpec(input.shotSpec) : emptyShotSpecFromShot(shot);
  problems.push(...checkSpecConflicts(shotSpec, styleSpec));
  // 返工指令（V2.5.4）：只允许作用于本图，且必须已经通过领域校验。
  const rework = isPlainObject(input.rework) ? assertReworkDirective(input.rework) : null;
  if (rework && rework.shot_id !== shot.shot_id) {
    invalid("返工指令属于另一张图，不能用于编译这张图的 Prompt。");
  }
  const context = isPlainObject(input.context) ? input.context : {};
  const dependency = evaluateShot(shot, context);
  for (const item of dependency.blocking) {
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot.dependencies",
      message: "这张图的依据还没有满足：" + (item.reason || "未知原因") + "。",
    });
  }
  const confirmed = new Map(
    brief.confirmed_facts.filter((item) => isPlainObject(item)).map((item) => [item.slot_id, item]));
  const boundIds = Array.isArray(shot.fact_slot_ids) ? shot.fact_slot_ids : [];
  for (const slotId of boundIds) {
    if (!confirmed.has(slotId)) {
      problems.push({
        code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot.fact_slot_ids",
        message: "绑定的商品事实「" + slotId + "」还没有确认值，不能进入提示词。",
      });
    }
  }
  if (problems.length > 0) {
    invalid("Prompt 编译未通过：" + problems[0].message
      + (problems.length > 1 ? "（共 " + problems.length + " 项）" : ""),
      { problems: problems.slice(0, 6) });
  }

  const role = roleDefinition(shot.role_id) || {};
  const roleLabel = isNonEmptyString(shot.label) ? shot.label : (role.label || shot.role_id);
  const shotRef = "suite_plan.shot:" + shot.shot_id;
  const platformRef = "platform:" + platform.platform_id + "@" + platform.version;
  const providerRef = "provider:" + provider.model_id + "@" + provider.version;
  const warnings = [];
  const sections = [];
  const boundFacts = boundIds.map((slotId) => confirmed.get(slotId)).filter(Boolean);
  const allowsText = platform.on_image_text_roles.includes(shot.role_id);
  const isMain = shot.role_id === "main";
  const printing = effectivePrinting(shotSpec, shot);
  problems.push(...decisionProblems({
    shot: shot, shotSpec: shotSpec, styleSpec: styleSpec, brief: brief,
    platformId: input.platformId,
    references: input.references, slotEntries: input.slotEntries,
  }));
  if (problems.length > 0) {
    invalid("Prompt 编译未通过：" + problems[0].message
      + (problems.length > 1 ? "（共 " + problems.length + " 项）" : ""),
      { problems: problems.slice(0, 6) });
  }
  const presentation = effectivePresentation(styleSpec, shotSpec, shot);
  // 输入图职责（#9/设计§13.6、§13.14.5）：实际图号与用途只从最终冻结数组与明确模式推导；
  // 编辑模式下商品外观权威只在商品原照，候选只提供待改的当前画面，不能被读成外观依据。
  const referenceInputs = referenceInputsOf(input.references, rework);
  const fidelityLead = referenceInputs && referenceInputs.edit_source
    ? "以本次输入中的商品原照为唯一外观依据"
    : "以提供的商品参考图为唯一外观依据";
  let fidelity = fidelityLead + "：保持商品的轮廓、比例、颜色、材质、标识与现有部件不变；不要添加、删除、复制、换色或重新设计商品特征。";
  // 展示决定（#9）：把「干净展示／原样保持、倒空／保留内容物」写成正向的表面状态陈述；
  // 选择干净展示时才给出去污例外，避免与「保持商品不变」互相矛盾。
  const presentationRefs = [];
  const presentationLines = [];
  if (presentation.consumes.appearance_state) {
    presentationRefs.push(presentation.appearance_state.source === "shot"
      ? "shot_spec.presentation.appearance_state" : "style_spec.presentation.appearance_state");
    presentationLines.push(presentation.appearance_state.state === "clean_display"
      ? "商品按干净展示状态呈现：允许去掉临时使用痕迹（水渍、指纹、残留），但材质、结构、标识与颜色仍与商品依据一致。"
      : "商品按商品依据里的原样状态呈现：可见的使用痕迹也照原样保留，不做清洁或去污。");
  }
  if (presentation.consumes.contents_state) {
    presentationRefs.push(presentation.contents_state.source === "shot"
      ? "shot_spec.presentation.contents_state" : "style_spec.presentation.contents_state");
    if (presentation.contents_state.state === "empty") {
      presentationLines.push("内容物为空：内腔与瓶口干净、无残留，也不添加资料里没有的内容物。");
    } else if (presentation.contents_state.state === "as_shown") {
      presentationLines.push("内容物保持原样：保留商品依据里可见的内容物，不倒空也不添加。");
    } else {
      presentationRefs.pop();
    }
  }
  if (presentationLines.length > 0) {
    fidelity += presentationLines.join("");
  }
  if (allowsText && boundFacts.length > 0) {
    fidelity += "图中如需出现文字，只能逐字使用后面列出的已确认文案。";
  } else if (!allowsText) {
    fidelity += "不要在图片上叠加文字、参数、徽标或水印。";
  }
  sections.push(section("product_fidelity", "商品一致性", "instruction", fidelity,
    ["intake.references", shotRef, shotRef + ".role", platformRef].concat(presentationRefs)));

  const styleLines = [];
  const styleRefs = [];
  const background = isNonEmptyString(styleSpec.background) ? styleSpec.background : null;
  if (isMain) {
    styleLines.push("主图背景" + platform.main_image.background_phrase);
    styleRefs.push(platformRef);
    if (background && !/(纯白|白色|white)/i.test(background)) {
      styleRefs.push("style_spec.background");
      warnings.push({
        code: "STYLE_OVERRIDDEN_BY_PLATFORM",
        message: "公共风格背景「" + background + "」被主图平台规则覆盖为纯白背景。",
        source_refs: ["style_spec.background", platformRef],
      });
    } else if (background) {
      styleRefs.push("style_spec.background");
    }
  } else if (background) {
    styleLines.push("背景" + quoteLiteral(background));
    styleRefs.push("style_spec.background");
  }
  for (const [key, label] of [["lighting", "光线"], ["color_tone", "色调"], ["composition", "构图"]]) {
    if (isNonEmptyString(styleSpec[key])) {
      styleLines.push(label + quoteLiteral(styleSpec[key]));
      styleRefs.push("style_spec." + key);
    }
  }
  if (styleLines.length > 0) {
    sections.push(section("style_shared", "公共风格", "instruction",
      "公共风格（整套一致）：" + styleLines.join("；") + "。", styleRefs));
  }

  // 画面简报（#9）：专业表达由系统承担 —— 用用途（角色）给出正向画面概念、主体位置与大小、
  // 视角、留白与光线，普通用户不需要写摄影术语；不带任何未确认的商品事实。
  // 显式正/侧/顶视通过依据门后必须真正改正文：替换角色简报里的默认视角句（否则顶视仍会被
  // 读成「平视拍摄」），并把决定与证据槽写进来源；没显式选择时默认行为不变。
  const roleBrief = ROLE_VISUAL_BRIEF[shot.role_id] || ROLE_VISUAL_BRIEF.custom;
  const viewpointSentence = presentation.viewpoint.state !== "reference_visible"
    ? VIEWPOINT_SENTENCES[presentation.viewpoint.state] || "" : "";
  const briefLines = viewpointSentence
    ? roleBrief.filter((line) => !line.startsWith("视角：")).concat(viewpointSentence)
    : [...roleBrief];
  const briefRefs = [shotRef + ".role", shotRef];
  if (viewpointSentence) {
    briefRefs.push(presentation.viewpoint.source === "shot"
      ? "shot_spec.presentation.viewpoint" : "style_spec.presentation.viewpoint");
    for (const proof of viewpointProofOf(input, presentation.viewpoint.state).slots) {
      briefRefs.push("product_brief.fact:" + proof.slot_id);
    }
  }
  sections.push(section("visual_brief", "画面简报", "instruction", briefLines.join(""), briefRefs));

  const taskLines = ["本图任务" + quoteLiteral(roleLabel)
    + "，目的" + quoteLiteral(shotSpec.purpose || shot.intent || role.purpose || roleLabel) + "。"];
  const taskRefs = [shotRef, "shot_spec.purpose"];
  if (shotSpec.keep.length > 0) {
    taskLines.push("必须保持：" + shotSpec.keep.map(quoteLiteral).join("、") + "。");
    taskRefs.push("shot_spec.keep");
  }
  if (shotSpec.change_allowed.length > 0) {
    taskLines.push("允许变化：" + shotSpec.change_allowed.map(quoteLiteral).join("、") + "。");
    taskRefs.push("shot_spec.change_allowed");
  }
  if (isNonEmptyString(shotSpec.notes)) {
    taskLines.push("补充说明：" + quoteLiteral(shotSpec.notes) + "。");
    taskRefs.push("shot_spec.notes");
  }
  sections.push(section("shot_task", "本图任务", "instruction", taskLines.join(""), taskRefs));

  // 输入依据段（#9/设计§13.6）：有实际冻结数组时才排段，写明每张输入图的职责与本次模式；
  // 没有参考数组的调用方正文不变（不凭空声称收到或没收到候选）。来源只随实际发送内容走：
  // 编辑模式指到固定候选，原照重生成不把候选写进来源。
  if (referenceInputs) {
    sections.push(section("reference_inputs", "输入依据", "instruction", referenceInputs.text, referenceInputs.refs));
  }

  // 版面：只有用户真的选过版面、或明确选择了要印的文案时才排段；
  // 未决定版面的普通图正文不变（不靠程序补一个版面）。
  const layoutExplicit = isPlainObject(input.shotSpec) && isNonEmptyString(input.shotSpec.layout);
  if (layoutExplicit || printing.intent === "selected") {
    sections.push(section("shot_layout", "版面", "instruction",
      "本图版面：" + LAYOUT_SENTENCES[printing.layout],
      ["shot_spec.layout", shotRef]));
  }

  if (rework) {
    // 用户方向按「逐字引用」处理：括号内允许任意语言，语言策略仍然成立。
    const problemText = rework.problems.map(reworkProblemLabel).join("、");
    const reworkLines = ["本次返工要求（只改这张图，其它段落保持不变）："];
    if (problemText) reworkLines.push("这次的问题属于" + quoteLiteral(problemText) + "；");
    if (rework.direction) reworkLines.push("改进方向" + quoteLiteral(rework.direction) + "；");
    reworkLines.push("不要重复出现上一条候选里已经被指出的同类问题。");
    sections.push(section("rework_directive", "本次返工要求", "instruction", reworkLines.join(""),
      ["rework:" + rework.directive_id, "candidate:" + rework.candidate_id, shotRef]));
  }

  const textItems = [];
  const textRefs = [];
  // V2.6.17：只有「允许图中文字」的角色才会排出文字段落 —— 无文字角色（场景图/细节图等）
  // 报「图中将逐字保留原文」是误报。
  // #9：图中文案只来自用户明确选择的条目；facts_auto（自动印绑定事实）已退役，
  // 任何角色都不自动上图，印字决定角色默认「未决定」并由上面的门阻断。
  const languageRisks = new Map();
  if (printing.intent === "selected") {
    for (const item of printing.texts) {
      const text = String(item.text).trim();
      const language = languageOf(text);
      const sourceRef = "shot_spec.on_image_text:" + item.text_id;
      textItems.push({ text: quoteLiteral(text), language: language, source_ref: sourceRef });
      textRefs.push(sourceRef);
      if (language !== platform.on_image_text_language) {
        languageRisks.set(item.text_id, 1);
      }
    }
    for (const textId of languageRisks.keys()) {
      warnings.push({
        code: "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE",
        message: "所选图中文字「" + textId + "」不是 " + platform.on_image_text_language
          + "，图中将逐字保留原文，请人工确认是否使用。",
        source_refs: ["shot_spec.on_image_text:" + textId, platformRef],
      });
    }
  } else if (printing.intent === "none" && allowsText && boundFacts.length > 0) {
    // 「不印」只在印字决定角色上是用户选择（其他角色默认不叠加文案，不冒充用户选择）；
    // 主图另有 MAIN_IMAGE_FACTS_IGNORED，不在这里重复。
    warnings.push({
      code: "ON_IMAGE_TEXT_NONE_FACTS_SKIPPED",
      message: "这张图选择不印新增文字：绑定的 " + boundFacts.length + " 条商品事实不会出现在画面上。",
      source_refs: ["shot_spec.print_intent"].concat(boundFacts.map((fact) => "product_brief.fact:" + fact.slot_id)),
    });
  }
  if (allowsText && textItems.length > 0) {
    const header = "图中文字（只允许逐字使用以下已确认文案，不翻译、不改写、不新增；文字语言应为"
      + quoteLiteral(platform.on_image_text_language) + "）：\n";
    sections.push(literalSection("on_image_text", "图中文字",
      header + textItems.map((item) => "- " + item.text).join("\n"), textItems, textRefs));
  } else if (isMain && boundFacts.length > 0) {
    warnings.push({
      code: "MAIN_IMAGE_FACTS_IGNORED",
      message: "主图不得叠加文字，绑定的 " + boundFacts.length + " 条事实不会出现在画面上。",
      source_refs: boundFacts.map((fact) => "product_brief.fact:" + fact.slot_id).concat([platformRef]),
    });
  }

  const platformLines = ["平台规则" + quoteLiteral(platform.label) + "："];
  if (isMain) {
    platformLines.push("主图必须使用" + platform.main_image.background_phrase
      + "，商品主体至少占画面 " + platform.main_image.min_occupancy_percent
      + "%，不得出现文字、水印或边框。");
  }
  platformLines.push(...platform.base_rules);
  sections.push(section("platform_rules", "平台规则", "instruction",
    platformLines.join(""), [platformRef]));

  sections.push(section("provider_contract", "输出规格", "instruction",
    "输出规格：一张" + quoteLiteral(provider.size) + "的" + quoteLiteral(provider.output_format)
      + "格式高清商品图，不添加水印。",
    [providerRef]));

  const avoidList = [
    ...styleSpec.avoid,
    "水印", "文字错乱或文字变形",
    "商品变形、多出部件或与参考图不符的颜色和标识",
  ];
  if (!allowsText) avoidList.push("任何叠加文字、参数徽标或边框");
  sections.push(section("negative_constraints", "必须避免", "instruction",
    "必须避免：" + avoidList.map(quoteLiteral).join("、") + "。",
    ["style_spec.avoid", platformRef, providerRef, "shot_spec.keep"]));

  const text = sections.map((item) => item.text).join("\n\n");
  const compiled = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: shot.shot_id,
    role_id: shot.role_id,
    label: roleLabel,
    language: {
      policy_id: PROMPT_LANGUAGE_POLICY_ID,
      instruction: "zh",
      on_image_text: platform.on_image_text_language,
    },
    platform: { platform_id: platform.platform_id, version: platform.version, label: platform.label },
    provider: { ...provider },
    sections: sections,
    text: text,
    source_refs: promptSourceRefs(sections),
    warnings: warnings,
    basis: promptBasisOf(input, platform, provider),
    rework: rework ? Object.freeze({
      contract_version: rework.contract_version,
      directive_id: rework.directive_id,
      candidate_id: rework.candidate_id,
      candidate_sha256: rework.candidate_sha256,
      problems: rework.problems,
      direction: rework.direction,
    }) : null,
  };
  const selfCheck = [
    ...checkCompiledPrompt(compiled),
    ...checkLiteralVerbatim(sections, brief, shotSpec),
    ...checkPromptLeaks(sections, context.facts),
  ];
  if (text.length > provider.max_prompt_chars) {
    selfCheck.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.text",
      message: "提示词长度 " + text.length + " 超过 Provider 上限 " + provider.max_prompt_chars + "。",
    });
  }
  if (selfCheck.length > 0) {
    invalid("Prompt 编译自检未通过：" + selfCheck[0].message, { problems: selfCheck.slice(0, 6) });
  }
  return compiled;
}

/* --------------------------------------------------- 自检、快照与版本记录 */

/**
 * 本图商品依据的唯一选择规则；不设容量、不拼接候选、不改上传顺序。
 * 显式空集合不回退；未知/已删除的选择必须由用户修正。
 * @param {unknown} shot
 * @param {unknown} references
 * @param {{shotSpec?: unknown}} [options]
 * @returns {import("./type-contracts.js").PromptReferenceIdentity[]}
 */
export function productReferencesForShot(shot, references, options = {}) {
  const bySha = new Map();
  for (const item of Array.isArray(references) ? references : []) {
    const sha = isPlainObject(item) ? item.sha256 || item.asset_sha256 : null;
    if (!isPlainObject(item) || !isNonEmptyString(item.role) || !isSha256Hex(sha)) {
      invalid("商品参考图必须有明确角色与完整资产哈希。");
    }
    if (!bySha.has(sha)) bySha.set(sha, { role: item.role, sha256: sha });
  }
  const spec = isPlainObject(options.shotSpec) ? options.shotSpec : {};
  if (Object.prototype.hasOwnProperty.call(spec, "reference_sha256s")) {
    if (!Array.isArray(spec.reference_sha256s)) invalid("本图参考选择必须是有序列表。");
    const selected = [];
    const seen = new Set();
    for (const sha of spec.reference_sha256s) {
      if (!isSha256Hex(sha) || seen.has(sha) || !bySha.has(sha)) {
        invalid("本图选中的商品依据已不存在、重复或身份不合法；请重新选择本图依据。");
      }
      seen.add(sha);
      selected.push(bySha.get(sha));
    }
    return selected;
  }
  const roles = new Set();
  const collect = (requirement) => {
    if (!isPlainObject(requirement)) return;
    if (requirement.kind === "asset_role" && isNonEmptyString(requirement.role)) {
      roles.add(requirement.role);
    } else if (requirement.kind === "any_of" && Array.isArray(requirement.of)) {
      for (const nested of requirement.of) collect(nested);
    }
  };
  for (const requirement of isPlainObject(shot) && Array.isArray(shot.dependencies) ? shot.dependencies : []) {
    collect(requirement);
  }
  const all = [...bySha.values()];
  const selected = all.filter(item => roles.has(item.role));
  return selected.length ? selected : all.filter(item => item.role === "primary");
}

/**
 * 依赖求值的素材投影：确认单与提交门必须用同一判据——
 * 只把本次请求里真正作为商品依据外发的图交给 evaluateShot：商品原照（product_truth）
 * 与竞品/风格参考（style_reference）按其冻结角色计数；编辑源候选（edit_source）是
 * 待修对象，不冒充商品依据。竞品图按 style_reference 用途发送，不能因为用途名丢掉
 * 「对比图需要 competitor 角色」的依赖。
 * @param {unknown} references 冻结引用选择（selectReferences 的输出或其子集）
 * @returns {{role: unknown, sha256: unknown}[]}
 */
export function dependencyAssetsOf(references) {
  return (Array.isArray(references) ? references : [])
    .filter((item) => isPlainObject(item) && Array.isArray(item.uses)
      && (item.uses.includes("product_truth") || item.uses.includes("style_reference")))
    .map((item) => ({ role: item.role, sha256: item.sha256 }));
}

/**
 * 新请求唯一规范化入口：商品依据按所选顺序，编辑源在首位；同字节合并职责与来源。
 * @param {unknown} shot
 * @param {unknown} references
 * @param {{maxReferences?: number, intakeVersion?: number, shotSpec?: unknown, rework?: unknown}} [options]
 * @returns {import("./type-contracts.js").PromptReferenceSelection[]}
 */
export function selectReferences(shot, references, options = {}) {
  const limit = options.maxReferences === undefined ? MAX_REFERENCE_SELECTION : options.maxReferences;
  if (!isPositiveInteger(limit) || !isPositiveInteger(options.intakeVersion)) {
    invalid("冻结参考图需要有效容量和已保存的商品资料版本，不会猜测来源版本。");
  }
  /** @type {import("./type-contracts.js").PromptReferenceSelection[]} */
  const picked = [];
  const rework = isPlainObject(options.rework) ? options.rework : null;
  if (rework) {
    if (rework.schema_version !== undefined && rework.schema_version !== 2) {
      invalid("返工指令版本不认识：" + String(rework.schema_version) + "；只接受当前 schema 2。");
    }
    if (rework.mode !== undefined && !["edit_candidate", "regenerate_original"].includes(rework.mode)) {
      invalid("返工模式不认识：" + String(rework.mode) + "；不从历史记录猜测模式。");
    }
    // 历史 basis.rework（无 mode）只读：保持既有请求图序，不插入候选编辑源；
    // 新命令必须声明 mode，由写入端（requestSnapshotOf/buildPromptRecord）强制，选择器不猜测。
    if (rework.mode === "edit_candidate") {
      const candidate = rework.problem_candidate;
      if (!isPlainObject(candidate) || !isPlainObject(shot) || candidate.document_id !== shot.shot_id
          || candidate.candidate_id !== rework.candidate_id || !isPositiveInteger(candidate.version)
          || !isSha256Hex(candidate.asset_sha256) || candidate.asset_sha256 !== rework.candidate_sha256) {
        invalid("编辑源必须是本图固定的问题候选及其确切文档版本、原图字节。");
      }
      picked.push({ role: "other", sha256: candidate.asset_sha256, uses: ["edit_source"],
        sources: [{ kind: "candidate", document_id: candidate.document_id,
          version: candidate.version, asset_sha256: candidate.asset_sha256 }] });
    }
  }
  for (const item of productReferencesForShot(shot, references, { shotSpec: options.shotSpec })) {
    /** @type {import("./type-contracts.js").PromptReferenceUse} */
    const use = item.role === "competitor" ? "style_reference" : "product_truth";
    /** @type {import("./type-contracts.js").PromptReferenceSource} */
    const source = { kind: "product_input", document_id: "intake",
      version: options.intakeVersion, asset_sha256: item.sha256 };
    const existing = picked.find(entry => entry.sha256 === item.sha256);
    if (existing) {
      if (!existing.uses.includes(use)) existing.uses.push(use);
      existing.sources.push(source);
    } else {
      picked.push({ role: item.role, sha256: item.sha256, uses: [use], sources: [source] });
    }
  }
  const problems = checkFrozenReferences(picked, { maxReferences: limit });
  if (problems.length) {
    // 显式空选（reference_sha256s=[]）是用户明确的本图依据决定：冻结结果就是空，
    // 由编译/消费门按「缺商品原照依据」阻断，不在这里冒充容量错误、也不回退默认原图。
    const declared = options.shotSpec;
    const explicitEmpty = picked.length === 0 && isPlainObject(declared)
      && Object.prototype.hasOwnProperty.call(declared, "reference_sha256s")
      && Array.isArray(declared.reference_sha256s) && declared.reference_sha256s.length === 0;
    if (explicitEmpty) return picked;
    invalid(problems[0].message, { problems });
  }
  if (!picked.some(item => item.uses.includes("product_truth"))) {
    invalid("这张图缺少商品原照依据；候选、竞品和风格参考不能单独证明商品。");
  }
  return picked;
}

/**
 * @param {unknown} compiled
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkCompiledPrompt(compiled) {
  const problems = [];
  if (!isPlainObject(compiled)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "编译结果必须是对象。");
    return problems;
  }
  if (compiled.rework !== undefined && compiled.rework !== null) {
    const rework = compiled.rework;
    if (!isPlainObject(rework) || !isNonEmptyString(rework.contract_version)
        || !isNonEmptyString(rework.directive_id) || !isNonEmptyString(rework.candidate_id)
        || !isSha256Hex(rework.candidate_sha256)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.rework",
        "返工块必须绑定指令与候选身份。");
    } else {
      // 人工全文只保留一个 manual_edit 段，不自动追加系统返工指令；
      // 历史返工身份仍须校验，不能把段落形状要求套到人工文本上。
      if (compiled.origin !== "manual_edit"
          && !(Array.isArray(compiled.sections) ? compiled.sections : [])
            .some((item) => item && item.key === "rework_directive")) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.rework",
          "带返工块的系统编译结果必须有返工要求段落。");
      }
      // 返工块与来源引用必须指向同一条指令与同一条候选。
      const refs = Array.isArray(compiled.source_refs) ? compiled.source_refs : [];
      if (refs.indexOf("rework:" + rework.directive_id) === -1
          || refs.indexOf("candidate:" + rework.candidate_id) === -1) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.rework",
          "返工块必须与来源引用一致（rework:<id> 与 candidate:<id>）。");
      }
    }
  }
  problems.push(...sectionProblems(compiled.sections));
  if (compiled.origin !== "manual_edit") {
    problems.push(...checkPromptLanguage(compiled.sections));
  }
  const expectedText = (Array.isArray(compiled.sections) ? compiled.sections : [])
    .map((item) => item.text).join("\n\n");
  if (compiled.text !== expectedText) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "text 必须等于 sections 的确定性拼接。");
  }
  const expectedRefs = promptSourceRefs(compiled.sections);
  if (canonicalJson(compiled.source_refs || []) !== canonicalJson(expectedRefs)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source_refs",
      "source_refs 必须等于各段落来源的并集。");
  }
  return problems;
}

/**
 * @param {unknown} compiled
 * @returns {import("./type-contracts.js").CompiledPrompt}
 */
export function assertCompiledPrompt(compiled) {
  const problems = checkCompiledPrompt(compiled);
  if (problems.length > 0) {
    invalid("编译结果不合法：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
  return compiled;
}

/**
 * 快照与冻结档一致性检查：build/checkPromptRecord 与 requestSnapshotOf 共用。
 * 只比较请求相关字段与目标身份，不比较任何凭据字段；返回问题列表。
 * @param {unknown} profile
 * @param {unknown} snapshot
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
function checkSnapshotAgainstProfile(profile, snapshot) {
  const problems = [];
  if (!isPlainObject(snapshot)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot", "请求快照必须是对象。");
    return problems;
  }
  if (!isPlainObject(profile)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.compiled.provider",
      "编译结果缺少冻结的 Provider 档。");
    return problems;
  }
  const expect = (key, expected) => {
    if (snapshot[key] !== expected) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot." + key,
        "请求快照的 " + key + " 必须等于冻结档的 " + String(expected) + "。");
    }
  };
  expect("model", profile.model_id);
  expect("size", profile.size);
  expect("n", profile.n);
  expect("prompt_extend", profile.prompt_extend);
  expect("watermark", profile.watermark);
  expect("output_format", profile.output_format);
  const target = isPlainObject(snapshot.target) ? snapshot.target : null;
  const expectedTarget = isPositiveInteger(profile.version)
    ? { provider_id: profile.provider_id, model_id: profile.model_id,
        protocol: profile.protocol, capability_version: profile.version } : null;
  if (!target || !expectedTarget
      || canonicalJson(target) !== canonicalJson(expectedTarget)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot.target",
      "请求快照的 target 必须等于冻结档的目标身份（协议/目标/模型/能力版本）。");
  }
  const refs = Array.isArray(snapshot.references) ? snapshot.references : null;
  if (!refs) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot.references",
      "请求快照缺少参考图数组。");
  } else {
    // 数量上下限由 requestSnapshotOf 与确认单（REFERENCE_COUNT_INVALID）负责；
    // 这里只核对每条参考图的身份形状，避免同一件事被两处不同码重复判定。
    refs.forEach((item, index) => {
      if (!isPlainObject(item) || !isNonEmptyString(item.role) || !isSha256Hex(item.sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          "$.request_snapshot.references[" + index + "]", "参考图必须带 role 与 sha256。");
      }
    });
  }
  return problems;
}

/** 参考图顺序与返工模式的一致性检查（写入端与记录检查共用；只返回问题，不抛错）。
 * @param {unknown} references
 * @param {unknown} rework
 * @param {unknown} [shotId]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function referenceModeProblems(references, rework, shotId = null) {
  const problems = [];
  const items = Array.isArray(references) ? references : [];
  const usesOf = (item) => (isPlainObject(item) && Array.isArray(item.uses) ? item.uses : []);
  const edits = items.filter((item) => usesOf(item).includes("edit_source"));
  if (!items.some((item) => usesOf(item).includes("product_truth"))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
      "新请求必须含商品原照依据，不能只发送候选或风格参考。");
  }
  if (!isPlainObject(rework)) {
    if (edits.length) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "没有明确编辑模式的新请求不能发送候选编辑源。");
    }
    return problems;
  }
  if (rework.mode === "regenerate_original") {
    if (edits.length) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "原照重生成不能发送历史候选图。");
    }
    return problems;
  }
  if (rework.mode !== "edit_candidate") {
    if (edits.length) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "返工模式未声明；请重新准备并核对真实模型来源。");
    }
    return problems;
  }
  const problem = rework.problem_candidate;
  const first = items[0];
  if (!isPlainObject(problem) || !isNonEmptyString(shotId) || problem.document_id !== shotId
      || edits.length !== 1 || first !== edits[0]
      || !isSha256Hex(first.sha256) || first.sha256 !== problem.asset_sha256
      || !(Array.isArray(first.sources) && first.sources.some((source) => isPlainObject(source)
        && source.kind === "candidate" && source.document_id === problem.document_id
        && source.version === problem.version && source.asset_sha256 === problem.asset_sha256))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
      "候选编辑的第一张图必须是本图固定问题候选的确切版本及原字节。");
  }
  return problems;
}

/** 新请求的实际图序必须与明确模式相符；历史只读记录不经过这个新写入门。 */
function assertReferenceMode(references, rework, shotId) {
  const problems = referenceModeProblems(references, rework, shotId);
  if (problems.length > 0) invalid(problems[0].message, { problems });
}

/** 请求快照：只包含真实会发送的参数与参考图身份，不含图片字节；prompt 必须逐字等于编译文本。
 * @param {unknown} compiled
 * @param {{references?: unknown}} [options]
 * @returns {import("./type-contracts.js").RequestSnapshot}
 */
export function requestSnapshotOf(compiled, options = {}) {
  assertCompiledPrompt(compiled);
  const profile = assertImagePromptProfile(compiled.provider);
  const refs = Array.isArray(options.references) ? options.references : [];
  const problems = checkFrozenReferences(refs, { maxReferences: profile.max_reference_images });
  if (problems.length) invalid(problems[0].message, { problems });
  // basis.rework 是冻结模式权威（compiled.rework 只带合同字段、不带 mode）。
  const lineage = (compiled.basis && isPlainObject(compiled.basis.rework))
    ? compiled.basis.rework : (compiled.rework || null);
  assertReferenceMode(refs, lineage, compiled.shot_id);
  const references = refs.map(item => ({
    role: item.role, sha256: item.sha256, uses: [...item.uses],
    sources: item.sources.map(source => ({ ...source })),
  }));
  const sizeProblem = sizeScopeProblem(profile, profile.size);
  if (sizeProblem) invalid("冻结档位的默认尺寸不合法：" + sizeProblem);
  return {
    model: profile.model_id,
    size: profile.size,
    n: profile.n,
    prompt_extend: profile.prompt_extend,
    watermark: profile.watermark,
    output_format: profile.output_format,
    references: references,
    prompt: compiled.text,
    target: {
      provider_id: profile.provider_id,
      model_id: profile.model_id,
      protocol: profile.protocol,
      capability_version: profile.version,
    },
  };
}

/** hash 复用注入的 sha256Hex（WebCrypto）；本层不写第二种散列。
 * @param {unknown} snapshot
 * @param {{digest?: unknown}} [options]
 * @returns {Promise<import("./type-contracts.js").Sha256Hex>}
 */
export async function promptHash(snapshot, options = {}) {
  const digest = options.digest;
  if (typeof digest !== "function") {
    invalid("Prompt hash 需要注入 digest（复用 sha256Hex），不在本层另写散列。");
  }
  const bytes = new TextEncoder().encode(canonicalJson(snapshot));
  const hex = await digest(bytes);
  if (typeof hex !== "string" || !/^[0-9a-f]{64}$/.test(hex)) {
    invalid("digest 必须返回 64 位十六进制 sha256。");
  }
  return hex;
}

/**
 * @param {{compiled?: unknown, snapshot?: unknown, hash?: unknown}} [args]
 * @returns {import("./type-contracts.js").PromptRecord}
 */
export function buildPromptRecord({ compiled, snapshot, hash } = {}) {
  assertCompiledPrompt(compiled);
  const snapshotProblems = checkSnapshotAgainstProfile(compiled.provider, snapshot);
  if (snapshotProblems.length > 0) {
    invalid(snapshotProblems[0].message, { problems: snapshotProblems.slice(0, 3) });
  }
  if (!isPlainObject(snapshot) || snapshot.prompt !== compiled.text) {
    invalid("请求快照的 prompt 必须与编译文本逐字一致。");
  }
  if (typeof hash !== "string" || !/^[0-9a-f]{64}$/.test(hash)) {
    invalid("Prompt 记录缺少有效 hash。");
  }
  const frozenProblems = checkFrozenReferences(snapshot.references, {
    maxReferences: compiled.provider.max_reference_images,
  });
  if (frozenProblems.length) invalid(frozenProblems[0].message, { problems: frozenProblems });
  if (compiled.basis?.compiler_rule_version !== PROMPT_COMPILER_RULE_VERSION) {
    invalid("新 Prompt 必须由当前编译规则产生；历史原记录只能读取，不能冒充新写入。");
  }
  const lineage = (compiled.basis && isPlainObject(compiled.basis.rework))
    ? compiled.basis.rework : (compiled.rework || null);
  assertReferenceMode(snapshot.references, lineage, compiled.shot_id);
  return {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: compiled.shot_id,
    role_id: compiled.role_id,
    label: compiled.label,
    compiled: {
      sections: compiled.sections,
      text: compiled.text,
      source_refs: compiled.source_refs,
      warnings: compiled.warnings,
      language: compiled.language,
      platform: compiled.platform,
      provider: compiled.provider,
      ...(compiled.rework ? { rework: compiled.rework } : {}),
    },
    request_snapshot: snapshot,
    hash: hash,
    basis: compiled.basis,
  };
}

/** 版本记录形状（存储层写入前使用）。 @param {unknown} record @returns {import("./type-contracts.js").DomainProblem[]} */
export function checkPromptRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "Prompt 记录必须是对象。");
    return problems;
  }
  if (![LEGACY_PROMPT_SCHEMA_VERSION, PROMPT_SCHEMA_VERSION].includes(record.schema_version)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "Prompt 记录版本不认识：" + String(record.schema_version));
  }
  if (!isNonEmptyString(record.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id", "记录缺少 shot_id。");
  }
  problems.push(...checkCompiledPrompt(record.compiled));
  problems.push(...checkImagePromptProfile(record.compiled && record.compiled.provider));
  problems.push(...checkSnapshotAgainstProfile(
    record.compiled && record.compiled.provider, record.request_snapshot));
  if (record.schema_version === PROMPT_SCHEMA_VERSION) {
    const frozen = checkFrozenReferences(record.request_snapshot?.references, {
      maxReferences: record.compiled?.provider?.max_reference_images,
    });
    problems.push(...frozen);
    if (frozen.length === 0) {
      const basis = isPlainObject(record.basis) ? record.basis : null;
      const lineage = basis && isPlainObject(basis.rework) ? basis.rework
        : (isPlainObject(record.compiled) && isPlainObject(record.compiled.rework)
          ? record.compiled.rework : null);
      problems.push(...referenceModeProblems(record.request_snapshot.references, lineage, record.shot_id));
    }
  }
  if (!isPlainObject(record.request_snapshot)
      || record.request_snapshot.prompt !== (record.compiled && record.compiled.text)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot",
      "快照 prompt 必须与编译文本逐字一致。");
  }
  if (typeof record.hash !== "string" || !/^[0-9a-f]{64}$/.test(record.hash)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.hash", "记录缺少有效 hash。");
  }
  if (!isPlainObject(record.basis)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.basis", "记录缺少编译依据。");
  }
  if (record.origin === "manual_edit") {
    if (!isPlainObject(record.edited_from) || !isSha256Hex(record.edited_from.hash)
        || !Number.isInteger(record.edited_from.version) || record.edited_from.version < 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.edited_from",
        "人工编辑版本必须记录被编辑的版本号与 hash。");
    }
    if (!isNonEmptyString(record.edit_reason)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.edit_reason",
        "人工编辑版本必须记录编辑原因。");
    }
    if (typeof record.edited_at !== "string" || Number.isNaN(Date.parse(record.edited_at))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.edited_at",
        "人工编辑版本必须记录 ISO 时间戳。");
    }
    if ((record.compiled || {}).origin !== "manual_edit") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.compiled.origin",
        "人工编辑版本的 compiled.origin 必须是 manual_edit。");
    }
    if (!isPlainObject(record.invalidation) || record.invalidation.scope !== "shot"
        || record.invalidation.target_shot_id !== record.shot_id) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.invalidation",
        "人工编辑必须记录只影响目标 Shot 的失效投影。");
    }
  }
  return problems;
}

/* ------------------------------------------------------ 人工编辑（V2.3.6） */

export const MANUAL_EDIT_WARNING_CODES = Object.freeze({
  LANGUAGE_RULE: "MANUAL_EDIT_LANGUAGE_RULE",
});

/** 人工编辑的机读阻断原因：只有语言策略降级为提示，其余仍然阻断。 */
export const MANUAL_EDIT_REASON_CODES = Object.freeze({
  UNKNOWN_QUOTE: "MANUAL_EDIT_UNKNOWN_QUOTE",
  PLATFORM_TEXT_RULE: "MANUAL_EDIT_PLATFORM_TEXT_RULE",
});

export const MANUAL_EDIT_REASON_MAX = 200;

const CONTROL_CHAR_PATTERN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const QUOTE_PATTERN = /「[^」]*」/g;

function trimQuotes(value) {
  return String(value == null ? "" : value).replace(/^「/, "").replace(/」$/, "");
}

/** 人工编辑的硬阻断：空文本、控制字符、超长、与当前版本逐字相同。 @param {unknown} text @param {{maxChars?: number, baseText?: string}} [options] @returns {import("./type-contracts.js").DomainProblem[]} */
export function checkEditText(text, options = {}) {
  const problems = [];
  if (typeof text !== "string" || text.trim().length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text", "编辑后的提示词不能为空。");
    return problems;
  }
  if (CONTROL_CHAR_PATTERN.test(text)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text", "提示词不能包含控制字符。");
  }
  const maxChars = Number.isInteger(options.maxChars) ? options.maxChars : MAX_PROMPT_CHARS;
  if (text.length > maxChars) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "提示词长度 " + text.length + " 超过 Provider 上限 " + maxChars + "。");
  }
  if (typeof options.baseText === "string" && text === options.baseText) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "编辑后的文本与当前版本逐字相同，不需要新版本。");
  }
  return problems;
}

/** 图中文案的规范文本：测量条目只按绑定重算（唯一构造在 specs.js），其余取存储原文。
 * 绑定非法或重算失败时退回存储原文（该条目由 imageTextProblems 报告，本处不抛错）。
 * @param {unknown} item
 * @returns {string}
 */
function canonicalImageTextOf(item) {
  if (!isPlainObject(item)) return "";
  if (isPlainObject(item.measurement)) {
    try {
      return String(formatMeasurementText(item.measurement, { includeSource: true }) || "").trim();
    } catch (error) {
      return isNonEmptyString(item.text) ? String(item.text).trim() : "";
    }
  }
  if (isPlainObject(item.measurement_source)) {
    const kind = item.measurement_source.source_kind;
    return isNonEmptyString(kind) && isNonEmptyString(MEASUREMENT_SOURCE_LABEL[kind])
      ? MEASUREMENT_SOURCE_LABEL[kind] : "";
  }
  return isNonEmptyString(item.text) ? String(item.text).trim() : "";
}

/**
 * 人工编辑规则：只有语言策略降级为提示；未授权引用与平台文字白名单仍然阻断。
 * 被编辑文本里已经存在的引用视为已授权（编译器产物或用户输入的产物），新增引用必须来自
 * 已确认事实值，或本图当前已确认且通过复核的图中文案（shotSpec 给出时）。
 * 返工派生的版本另认一份冻结授权：`base.basis.rework` 带明确当前模式时，血缘里的原问题标签
 * 与原改进方向是操作指令引用，逐字相等即放行；这不放宽旧全文、旧事实或无模式历史。
 * @param {{text?: unknown, base?: unknown, brief?: unknown, platform?: unknown, shotSpec?: unknown}} [args]
 * @returns {{problems: import("./type-contracts.js").DomainProblem[], warnings: import("./type-contracts.js").PromptWarning[]}}
 */
export function checkManualEditRules({ text, base, brief, platform = null, shotSpec = null } = {}) {
  const problems = [];
  const warnings = [];
  const baseText = (base && base.compiled && base.compiled.text) || "";
  const allowedQuotes = new Set(
    (String(baseText).match(QUOTE_PATTERN) || []).map((quote) => normalizePhrase(trimQuotes(quote))));
  // 重新确认走调用方给的当前冻结平台（basis.platform）；人工编辑沿用被编辑版本的旧平台。不猜注册表。
  const currentRegistry = isPlainObject(platform) && Array.isArray(platform.on_image_text_roles)
    ? platform
    : (isPlainObject(platform) && isNonEmptyString(platform.platform_id)
      ? PLATFORM_PROFILES[platform.platform_id] || null
      : null);
  const registry = currentRegistry
    || (base && base.compiled && base.compiled.platform
      ? PLATFORM_PROFILES[base.compiled.platform.platform_id] || null : null);
  // 平台背景短语是系统文本自带的表达，永远授权。它在正文里以「纯白无缝背景「RGB(255,255,255)」」
  // 这类形态出现：整句与句中内层引用都会命中引用正则，逐个形态都要认，不能只比整句。
  const backgroundPhrases = new Set();
  if (registry) {
    const backgroundText = String(registry.main_image.background_phrase);
    const forms = [backgroundText].concat((backgroundText.match(QUOTE_PATTERN) || []).map((quote) => trimQuotes(quote)));
    for (const form of forms) {
      const phrase = normalizePhrase(form);
      if (phrase !== "") backgroundPhrases.add(phrase);
    }
  }
  const roleId = (base && base.role_id) || null;
  const textAllowed = registry ? registry.on_image_text_roles.includes(roleId) : true;
  const confirmed = new Set();
  for (const fact of (brief && Array.isArray(brief.confirmed_facts) ? brief.confirmed_facts : [])) {
    for (const value of factTexts(fact)) confirmed.add(normalizePhrase(value));
  }
  // 本图当前已确认且通过复核的图中文案（含测量重算文本）同样可作为「」引用来源；
  // 未确认、来源变动或复核不过的条目不放行。
  const imageTexts = new Set();
  for (const item of (isPlainObject(shotSpec) && Array.isArray(shotSpec.on_image_texts)
    ? shotSpec.on_image_texts : [])) {
    if (!isPlainObject(item) || item.status !== "confirmed") continue;
    if (imageTextProblems(item, { brief, shotSpec }).length > 0) continue;
    const canonical = canonicalImageTextOf(item);
    if (isNonEmptyString(canonical)) imageTexts.add(normalizePhrase(canonical));
  }
  // 返工操作指令的引用来源（#9 真实前置修复）：记录带着**明确当前模式**的冻结返工血缘时，
  // 血缘里的原问题标签与原改进方向是允许出现的指令「」引用——它们不是商品事实、也不同于新增
  // 印字，不能被当成「新引用未确认」拒绝。只认血缘里已有的逐字文本：不泛化接受旧全文、
  // 旧事实，无 mode 的历史记录不授权；其它新引用仍走原有确认门。
  const lineage = isPlainObject(base) && isPlainObject(base.basis) && isPlainObject(base.basis.rework)
    ? base.basis.rework : null;
  const reworkQuotes = new Set();
  if (lineage && (lineage.mode === "edit_candidate" || lineage.mode === "regenerate_original")) {
    const labels = (Array.isArray(lineage.problems) ? lineage.problems : [])
      .filter((id) => isNonEmptyString(id)).map((id) => reworkProblemLabel(id));
    for (const label of labels) reworkQuotes.add(normalizePhrase(label));
    // 编译器的返工段把多个分类并成一条逐字引用（「商品失真、构图」），并成形也要同样授权。
    if (labels.length > 0) reworkQuotes.add(normalizePhrase(labels.join("、")));
    if (isNonEmptyString(lineage.direction)) reworkQuotes.add(normalizePhrase(lineage.direction));
  }
  for (const quote of String(text == null ? "" : text).match(QUOTE_PATTERN) || []) {
    const phrase = normalizePhrase(trimQuotes(quote));
    if (backgroundPhrases.has(phrase) || allowedQuotes.has(phrase)) continue;
    // 返工指令逐字引用：是操作指令，不算新增印字，也不触发平台文字白名单。
    if (reworkQuotes.has(phrase)) continue;
    if (confirmed.has(phrase) || imageTexts.has(phrase)) {
      if (!textAllowed) {
        problems.push({
          code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.text",
          reason_code: MANUAL_EDIT_REASON_CODES.PLATFORM_TEXT_RULE,
          message: "这张图（" + String(roleId) + "）按平台规则不能新增叠加文案：" + quote + "。",
        });
      }
      continue;
    }
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.text",
      reason_code: MANUAL_EDIT_REASON_CODES.UNKNOWN_QUOTE,
      message: "新引用不是任何已确认事实值或本图已确认的图中文案：" + quote
        + "；先到「商品理解」或图中文案处确认它，或改成不引用的表述。",
    });
  }
  for (const problem of checkPromptLanguage([{
    key: "manual_edit", label: "人工编辑全文", kind: "manual_edit", text: text,
    source_refs: ["manual_edit"],
  }])) {
    warnings.push({ code: MANUAL_EDIT_WARNING_CODES.LANGUAGE_RULE, message: problem.message });
  }
  return { problems: problems, warnings: warnings };
}

/** 人工编辑版本：全文直接生效，hash 覆盖真实请求快照；目标身份取调用方给的当前冻结档（不静默沿用旧依据）。
 * 调用方不给 basis 时退化为逐字继承被编辑版本的旧依据（旧行为）；给出当前 basis 时 compiled.provider /
 * platform/language 必须与当前一致，否则确认单按 PROVIDER_MISMATCH/PLATFORM_MISMATCH 拒绝。人工文本逐字保留，不重排版。
 * @param {{base?: unknown, baseVersion?: unknown, text?: unknown, reason?: unknown, editedAt?: unknown, context?: unknown, digest?: unknown, basis?: unknown, references?: unknown, currentCompiled?: unknown}} [args]
 * @returns {Promise<import("./type-contracts.js").PromptRecord>}
 */
export async function buildEditedPromptRecord({ base, baseVersion, text, reason, editedAt, context, digest, basis = null,
                                                references = null, currentCompiled = null } = {}) {
  const baseProblems = checkPromptRecord(base);
  if (baseProblems.length > 0) {
    invalid("被编辑的 Prompt 记录不合法：" + baseProblems[0].message, { problems: baseProblems.slice(0, 3) });
  }
  if (!Number.isInteger(baseVersion) || baseVersion < 1) {
    invalid("人工编辑需要被编辑版本的版本号（来自文档仓库）。");
  }
  const activeBasis = isPlainObject(basis) ? basis : base.basis;
  const frozenProvider = isPlainObject(activeBasis) && isPlainObject(activeBasis.provider)
    ? activeBasis.provider : base.compiled.provider;
  const maxChars = isPositiveInteger(frozenProvider && frozenProvider.max_prompt_chars)
    ? frozenProvider.max_prompt_chars : MAX_PROMPT_CHARS;
  const textProblems = checkEditText(text, { maxChars: maxChars, baseText: base.compiled.text });
  if (textProblems.length > 0) {
    invalid("人工编辑未通过：" + textProblems[0].message, { problems: textProblems });
  }
  if (!isNonEmptyString(reason) || reason.trim().length > MANUAL_EDIT_REASON_MAX) {
    invalid("人工编辑必须填写不超过 " + MANUAL_EDIT_REASON_MAX + " 字的编辑原因。");
  }
  if (typeof editedAt !== "string" || Number.isNaN(Date.parse(editedAt))) {
    invalid("人工编辑需要 ISO 时间戳。");
  }
  const sourceRefs = [...new Set([...(base.compiled.source_refs || []), "prompt_edit:" + base.hash])];
  const sections = [Object.freeze({
    key: "manual_edit",
    label: "人工编辑全文",
    kind: "manual_edit",
    text: text,
    source_refs: Object.freeze([...sourceRefs]),
  })];
  const leaks = checkPromptLeaks(sections, (context || {}).facts, { includeQuoted: true });
  if (leaks.length > 0) {
    invalid("人工编辑未通过：" + leaks[0].message, { problems: leaks.slice(0, 3) });
  }
  // 引用授权基准：调用方给出当前编译产物时按「现行表达」判（只保留当前事实/文案/现行系统文本
  // 仍逐字支持的引用，已失据的旧引用不随新版本进入；与 reconfirm 同一口径）；否则沿用被编辑版本旧文本。
  // 编译产物是文本形状（text 在顶层），规则基准要的是记录形状（compiled.text / role_id）：
  // 合并成记录基准——现行文本与平台取当前编译，被编辑身份仍取 base，不能把编译产物直接当记录。
  const ruleBase = isPlainObject(currentCompiled) && isNonEmptyString(currentCompiled.text)
    ? { ...base, compiled: currentCompiled } : null;
  const rules = checkManualEditRules({ text: text, base: ruleBase || base, brief: (context || {}).brief,
    shotSpec: (context || {}).shotSpec });
  if (rules.problems.length > 0) {
    invalid("人工编辑未通过：" + rules.problems[0].message, {
      problems: rules.problems.slice(0, 3),
      reason_code: rules.problems[0].reason_code || null,
    });
  }
  // 目标身份：调用方给出当前 basis 时用当前冻结档（与 reconfirm 一致），否则沿用被编辑版本的旧依据。
  // 人工文本逐字保留（text/sections/source_refs 不重排版），只更新 provider/platform/language/basis。
  const hasCurrentBasis = isPlainObject(activeBasis) && isPlainObject(activeBasis.platform)
    && isPlainObject(activeBasis.provider);
  const editRegistry = hasCurrentBasis && isNonEmptyString(activeBasis.platform.platform_id)
    ? PLATFORM_PROFILES[activeBasis.platform.platform_id] || null : null;
  const editProvider = hasCurrentBasis ? assertImagePromptProfile(activeBasis.provider) : null;
  const compiled = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: base.shot_id,
    role_id: base.role_id,
    label: base.label,
    origin: "manual_edit",
    language: hasCurrentBasis
      ? { ...(base.compiled.language || {}),
          ...(editRegistry ? { on_image_text: editRegistry.on_image_text_language } : {}) }
      : { ...(base.compiled.language || {}) },
    platform: hasCurrentBasis
      ? { platform_id: activeBasis.platform.platform_id, version: activeBasis.platform.version,
          label: editRegistry ? editRegistry.label
            : (activeBasis.platform.label || activeBasis.platform.platform_id) }
      : { ...(base.compiled.platform || {}) },
    provider: hasCurrentBasis ? { ...editProvider } : { ...(base.compiled.provider || {}) },
    sections: sections,
    text: text,
    source_refs: sourceRefs,
    warnings: rules.warnings,
    basis: hasCurrentBasis ? activeBasis : base.basis,
  };
  const problems = checkCompiledPrompt(compiled);
  if (problems.length > 0) {
    invalid("人工编辑记录自检未通过：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
  const frozenReferences = Array.isArray(references)
    ? references : ((base.request_snapshot && base.request_snapshot.references) || []);
  const snapshot = requestSnapshotOf(compiled, {
    references: frozenReferences,
  });
  const hash = await promptHash(snapshot, { digest: digest });
  const record = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: base.shot_id,
    role_id: base.role_id,
    label: base.label,
    origin: "manual_edit",
    edited_from: { version: baseVersion, hash: base.hash },
    edit_reason: reason.trim(),
    edited_at: editedAt,
    invalidation: invalidationsFor("prompt_edited", { shotId: base.shot_id }),
    compiled: compiled,
    request_snapshot: snapshot,
    hash: hash,
    basis: compiled.basis,
  };
  const recordProblems = checkPromptRecord(record);
  if (recordProblems.length > 0) {
    invalid("人工编辑记录不合法：" + recordProblems[0].message, { problems: recordProblems.slice(0, 3) });
  }
  return record;
}

/**
 * 人工文本重新确认（V2.R6.2）：这张图实际消费的依据变了、但人工文本仍然适用时，
 * 由人显式确认，生成一个**逐字保留原文本**的新人工版本，把依据更新到当前 basis。
 *
 * 与 buildEditedPromptRecord 的区别：编辑要求文本必须变化；重新确认要求文本必须**逐字不变**
 * （要改文本请走编辑）。不静默覆盖历史：新版本 edited_from 指向被确认的版本，旧版本仍在。
 * basis 由调用方给出（用 promptBasisOf 按当前 shot/brief/versions 计算），保证新记录不过期。
 * @param {{base?: unknown, baseVersion?: unknown, reason?: unknown, at?: unknown, basis?: unknown, references?: unknown, context?: unknown, digest?: unknown, currentCompiled?: unknown}} [args]
 * @returns {Promise<import("./type-contracts.js").PromptRecord>}
 */
export async function reconfirmEditedPrompt({ base, baseVersion, reason, at, basis,
                                              references = null, context = {}, digest,
                                              currentCompiled = null } = {}) {
  const baseProblems = checkPromptRecord(base);
  if (baseProblems.length > 0) {
    invalid("被重新确认的 Prompt 记录不合法：" + baseProblems[0].message, { problems: baseProblems.slice(0, 3) });
  }
  if (!Number.isInteger(baseVersion) || baseVersion < 1) {
    invalid("重新确认需要被确认版本的版本号（来自文档仓库）。");
  }
  if (!isPlainObject(basis) || !isPlainObject(basis.platform) || !isPlainObject(basis.provider)) {
    invalid("重新确认需要当前编译依据（含 platform 与 provider），不静默沿用旧依据。");
  }
  const text = base.compiled.text;
  const frozenProvider = basis.provider;
  const maxChars = isPositiveInteger(frozenProvider && frozenProvider.max_prompt_chars)
    ? frozenProvider.max_prompt_chars : MAX_PROMPT_CHARS;
  const textProblems = checkEditText(text, { maxChars: maxChars });
  if (textProblems.length > 0) {
    invalid("重新确认未通过：" + textProblems[0].message, { problems: textProblems });
  }
  if (!isNonEmptyString(reason) || reason.trim().length > MANUAL_EDIT_REASON_MAX) {
    invalid("重新确认必须填写不超过 " + MANUAL_EDIT_REASON_MAX + " 字的确认原因。");
  }
  if (typeof at !== "string" || Number.isNaN(Date.parse(at))) {
    invalid("重新确认需要 ISO 时间戳（at）。");
  }
  const sourceRefs = [...new Set([...(base.compiled.source_refs || []), "prompt_reconfirm:" + base.hash])];
  const sections = [Object.freeze({
    key: "manual_edit",
    label: "人工编辑全文",
    kind: "manual_edit",
    text: text,
    source_refs: Object.freeze([...sourceRefs]),
  })];
  const leaks = checkPromptLeaks(sections, (context || {}).facts, { includeQuoted: true });
  if (leaks.length > 0) {
    invalid("重新确认未通过：" + leaks[0].message, { problems: leaks.slice(0, 3) });
  }
  // 硬事实门：旧人工文本里的「」引用不能靠「文本没变」自证——必须仍被当前已确认事实逐字
  // 支撑，否则显式重新确认等于给已失效断言盖新时间戳。调用方给出当前编译产物
  // （currentCompiled）时，用它做规则基准：旧文本里已有、但当前编译/当前事实里都不再逐字
  // 出现的引用视为过期断言，直接拒绝，不自动改写人工文本。edited_from 仍保留原始人工记录。
  // 同样按记录形状合并：现行文本/平台取当前编译，被编辑身份仍取 base。
  const ruleBase = isPlainObject(currentCompiled) && isNonEmptyString(currentCompiled.text)
    ? { ...base, compiled: currentCompiled } : null;
  const currentRegistry = (isPlainObject(basis.platform) && isNonEmptyString(basis.platform.platform_id)
    ? PLATFORM_PROFILES[basis.platform.platform_id] || null : null);
  const rules = checkManualEditRules({ text: text, base: ruleBase || base, brief: (context || {}).brief,
    shotSpec: (context || {}).shotSpec,
    platform: currentRegistry || basis.platform });
  if (rules.problems.length > 0) {
    invalid("重新确认未通过：" + rules.problems[0].message, {
      problems: rules.problems.slice(0, 3),
      reason_code: rules.problems[0].reason_code || null,
    });
  }
  // 重新确认的目标身份 = 调用方给的**当前**冻结档（basis.provider 已是 imagePromptProfile
  // 验证过的有效档）；compiled.provider/platform 必须与 basis 一致，否则 requestSnapshotOf
  // 仍指向旧模型，确认单按 PROVIDER_MISMATCH 拒绝。人工文本逐字保留，不重排版。
  const currentProvider = assertImagePromptProfile(basis.provider);
  const currentPlatform = {
    platform_id: basis.platform.platform_id,
    version: basis.platform.version,
    label: currentRegistry ? currentRegistry.label : (basis.platform.label || basis.platform.platform_id),
  };
  // 语言块：instruction 仍是 zh（人工文本逐字保留，不重排版）；图中文字语言跟当前平台档，
  // 不沿用旧记录（旧平台语言若已变更，沿用会让 language 与 platform 自相矛盾）。
  const currentLanguage = {
    ...(base.compiled.language || {}),
    ...(currentRegistry ? { on_image_text: currentRegistry.on_image_text_language } : {}),
  };
  const compiled = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: base.shot_id,
    role_id: base.role_id,
    label: base.label,
    origin: "manual_edit",
    language: currentLanguage,
    platform: currentPlatform,
    provider: { ...currentProvider },
    sections: sections,
    text: text,
    source_refs: sourceRefs,
    warnings: rules.warnings,
    basis: basis,
  };
  const compiledProblems = checkCompiledPrompt(compiled);
  if (compiledProblems.length > 0) {
    invalid("重新确认记录自检未通过：" + compiledProblems[0].message, { problems: compiledProblems.slice(0, 3) });
  }
  const refs = Array.isArray(references)
    ? references
    : (base.request_snapshot && Array.isArray(base.request_snapshot.references)
      ? base.request_snapshot.references : []);
  const snapshot = requestSnapshotOf(compiled, { references: refs });
  const hash = await promptHash(snapshot, { digest: digest });
  const record = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: base.shot_id,
    role_id: base.role_id,
    label: base.label,
    origin: "manual_edit",
    edited_from: { version: baseVersion, hash: base.hash },
    edit_reason: reason.trim(),
    edited_at: at,
    invalidation: invalidationsFor("prompt_edited", { shotId: base.shot_id }),
    compiled: compiled,
    request_snapshot: snapshot,
    hash: hash,
    basis: basis,
    reconfirmed: true,
  };
  const recordProblems = checkPromptRecord(record);
  if (recordProblems.length > 0) {
    invalid("重新确认记录不合法：" + recordProblems[0].message, { problems: recordProblems.slice(0, 3) });
  }
  return record;
}

/**
 * 丢弃人工覆盖的落点（V2.R6.2）：返回历史里最新一条「系统编译」版本（非人工编辑），
 * 供调用方恢复或作为重新编译的基准；没有系统版本时返回 null（只能重新编译，不静默沿用人工文本）。
 * history = [{version, record}] 或 [{version, payload}]（payload 即记录）。
 * @param {unknown} history
 * @returns {{version: number | null, record: import("./type-contracts.js").PromptRecord} | null}
 */
export function latestSystemPromptVersion(history) {
  const list = (Array.isArray(history) ? history : [])
    .map((item) => {
      if (!isPlainObject(item)) return null;
      const record = isPlainObject(item.record) ? item.record
        : (isPlainObject(item.payload) ? item.payload : item);
      const version = Number.isInteger(item.version) ? item.version
        : (Number.isInteger(record && record.prompt_version) ? record.prompt_version : null);
      return isPlainObject(record) ? { version: version, record: record } : null;
    })
    .filter((item) => item !== null && item.record.origin !== "manual_edit"
      && typeof item.record.hash === "string")
    .sort((left, right) => (left.version === null ? -1 : left.version)
      - (right.version === null ? -1 : right.version));
  return list.length ? list[list.length - 1] : null;
}

/** 丢弃人工覆盖：返回可恢复的系统版本（或 null 表示必须重新编译），不修改任何记录。
 * @param {unknown} record
 * @param {unknown} history
 * @returns {{discarded_version: unknown, discarded_hash: unknown, target: {version: unknown, hash: unknown, record: unknown} | null, requires_recompile: boolean}}
 */
export function discardManualEdit(record, history) {
  if (!isPlainObject(record) || record.origin !== "manual_edit") {
    invalid("只有人工编辑版本才有可丢弃的覆盖；系统编译版本无需丢弃。");
  }
  const target = latestSystemPromptVersion(history);
  return Object.freeze({
    discarded_version: record.edited_from ? record.edited_from.version : null,
    discarded_hash: record.edited_from ? record.edited_from.hash : null,
    target: target ? { version: target.version, hash: target.record.hash,
      record: target.record } : null,
    requires_recompile: target === null,
  });
}

/**
 * 过期机检：只核对这张图**实际消费**的依据——它消费的槽位版本、它自己的 shot 签名、
 * 风格/单图规格版本、平台档与完整 Provider 档。任何一处变化即过期。
 *
 * 两条边界（V2.R6.2）：
 *  - 无关槽位变化不再使这张图过期：记录里 frozen 的 `consumed_slot_ids` 之外的槽位不参与比较；
 *    没有该字段的历史记录退化为「按记录的 brief 逐条比较」（历史证据照旧）。
 *  - 整份套图文档版本不再参与比较：改用这张图自己的 `shot_signature`（改别的图不影响本图）；
 *    历史记录若只有 `suite_version`，仍按版本比较。
 *
 * Provider 比较不再只看 numeric version：目标（provider_id/model_id）、协议与请求相关
 * 能力边界/参数任一不同都判过期；当前档缺字段也判过期。凭据字段（credential_source /
 * configured / 密钥引用）不在比较集合内，因此纯凭据轮换不使 Prompt 过期。
 * @param {unknown} record
 * @param {unknown} [current]
 * @returns {import("./type-contracts.js").PromptStaleness}
 */
export function promptStaleness(record, current = {}) {
  const reasons = [];
  const basis = isPlainObject(record) && isPlainObject(record.basis) ? record.basis : null;
  if (!basis) {
    return { stale: true, reasons: [{ field: "basis", stored: null, current: null, reason: "记录缺少编译依据。" }] };
  }
  const consumed = Array.isArray(basis.consumed_slot_ids) ? new Set(basis.consumed_slot_ids) : null;
  const storedAll = (basis.brief || []).map((item) => [item.slot_id, item.version]);
  const storedBasis = new Map(consumed
    ? storedAll.filter(([slotId]) => consumed.has(slotId)) : storedAll);
  const currentBasis = new Map((current.briefBasis || []).map((item) => [item.slot_id, item.version]));
  for (const [slotId, version] of storedBasis) {
    if (!currentBasis.has(slotId)) {
      reasons.push({ field: "brief." + slotId, stored: version, current: null, reason: "槽位已不存在" });
    } else if (currentBasis.get(slotId) !== version) {
      reasons.push({ field: "brief." + slotId, stored: version, current: currentBasis.get(slotId), reason: "槽位版本已前进" });
    }
  }
  // 只有历史记录（没有 consumed_slot_ids）才把「出现新槽位」当过期；精确记录只认已消费槽位。
  if (!consumed) {
    for (const [slotId, version] of currentBasis) {
      if (!storedBasis.has(slotId)) {
        reasons.push({ field: "brief." + slotId, stored: null, current: version, reason: "出现新槽位" });
      }
    }
  }
  // 这张图自己的签名优先（改别的图不使本图过期）；历史记录或未提供签名的调用方退回版本比较。
  const hasSignature = basis.shot_signature !== undefined && basis.shot_signature !== null;
  const callerProvidesSignature = Object.prototype.hasOwnProperty.call(current, "shot_signature");
  const useSignature = hasSignature && callerProvidesSignature;
  if (useSignature) {
    const nowSignature = current.shot_signature === undefined ? null : current.shot_signature;
    if (basis.shot_signature !== nowSignature) {
      reasons.push({ field: "shot_signature", stored: "signed", current: nowSignature ? "signed" : null,
        reason: "这张图自己的定义已变化" });
    }
  }
  // 编译器规则版本：调用方给出当前版本时，记录必须冻结同一版本；历史记录缺少冻结版本即待准备。
  if (Object.prototype.hasOwnProperty.call(current, "compiler_rule_version")) {
    const storedRule = Number.isInteger(basis.compiler_rule_version) ? basis.compiler_rule_version : null;
    const nowRule = Number.isInteger(current.compiler_rule_version) ? current.compiler_rule_version : null;
    if (storedRule !== nowRule) {
      reasons.push({ field: "compiler_rule_version", stored: storedRule, current: nowRule,
        reason: "编译器规则版本不同；系统稿需按当前规则准备，人工全文由人确认。" });
    }
  }
  // 商品资料版本：冻结引用里嵌了它（sources[].version），提交门按完整元数据全等比较。
  // 确认单必须用同一条判据，否则会出现「确认单说可提交 → 提交被拒」的分裂（真实缺陷）。
  if (Object.prototype.hasOwnProperty.call(current, "intake_version")) {
    const storedIntake = Number.isInteger(basis.intake_version) ? basis.intake_version : null;
    const nowIntake = Number.isInteger(current.intake_version) ? current.intake_version : null;
    if (storedIntake !== nowIntake) {
      reasons.push({ field: "intake_version", stored: storedIntake, current: nowIntake,
        reason: storedIntake === null
          ? "记录没有冻结商品资料版本；系统稿需按当前商品资料重新准备。"
          : "商品资料版本已前进；系统稿需按当前商品资料重新准备并确认。" });
    }
  }
  // 共用风格：记录冻结了本图消费的风格签名且调用方也能给出时按签名比较——只被单图覆盖的
  // 共用字段变化不使本图过期；否则退回 style_version 版本比较。
  const useStyleSignature = isNonEmptyString(basis.style_signature)
    && Object.prototype.hasOwnProperty.call(current, "style_signature");
  if (useStyleSignature) {
    const nowStyle = current.style_signature === undefined ? null : current.style_signature;
    if (basis.style_signature !== nowStyle) {
      reasons.push({ field: "style_signature", stored: "signed", current: nowStyle ? "signed" : null,
        reason: "本图消费的共用风格已变化" });
    }
  }
  const versionKeys = [];
  if (!useSignature) versionKeys.push("suite_version");
  if (!useStyleSignature) versionKeys.push("style_version");
  versionKeys.push("shot_spec_version");
  for (const key of versionKeys) {
    const stored = basis[key] === undefined ? null : basis[key];
    const now = current[key] === undefined ? null : current[key];
    if (stored !== now) {
      reasons.push({ field: key, stored: stored, current: now, reason: "版本已前进" });
    }
  }
  const platformVersion = isPlainObject(current.platform) ? current.platform.version : null;
  if ((basis.platform || {}).version !== platformVersion) {
    reasons.push({ field: "platform", stored: (basis.platform || {}).version ?? null, current: platformVersion, reason: "平台档版本前进" });
  }
  reasons.push(...providerStaleReasons(basis.provider, current.provider));
  return { stale: reasons.length > 0, reasons: reasons };
}

/** Provider 档的过期原因：目标 / 协议 / 版本 / 请求参数与能力边界任一不同或缺失即过期。
 * @param {unknown} storedProvider
 * @param {unknown} currentProvider
 * @returns {{field: string, stored: unknown, current: unknown, reason: string}[]}
 */
function providerStaleReasons(storedProvider, currentProvider) {
  const reasons = [];
  const stored = isPlainObject(storedProvider) ? storedProvider : null;
  const now = isPlainObject(currentProvider) ? currentProvider : null;
  if (!stored) {
    return [{ field: "provider", stored: null, current: now, reason: "记录缺少 Provider 档。" }];
  }
  if (!now) {
    return [{ field: "provider", stored: stored.version ?? null, current: null, reason: "当前 Provider 档缺失。" }];
  }
  const fields = ["provider_id", "model_id", "version", "protocol", ...IMAGE_PROFILE_FIELDS];
  const missing = fields.filter((key) => stored[key] === undefined || now[key] === undefined);
  if (missing.length > 0) {
    return [{
      field: "provider", stored: stored.version ?? null, current: now.version ?? null,
      reason: "Provider 档字段不完整：" + missing.join("、"),
    }];
  }
  const before = {};
  const after = {};
  for (const key of fields) {
    before[key] = stored[key];
    after[key] = now[key];
  }
  if (canonicalJson(before) !== canonicalJson(after)) {
    return [{
      field: "provider", stored: stored.version ?? null, current: now.version ?? null,
      reason: "Provider 档目标或请求参数变化",
    }];
  }
  return reasons;
}
