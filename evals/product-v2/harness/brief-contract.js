/**
 * V2.2.1 领域契约测试：在真实 Chromium 里跑 FactSlot / ProductInput / ProductBrief / 失效图。
 *
 * 正向：词表、注册表、权限矩阵、状态转换、投影、就绪门。
 * 反向（故意让守卫变红）：非法值形状、模型确认、无值确认、依赖成环、
 * 跳过失效范围、brief 与事实不一致——每一条都必须被抓住。
 *
 * 结果写到 window.__V2_BRIEF_RESULTS__，由 tools/verify_v2_2_1_product_contracts.py 读取。
 */

import {
  CHANGE_KINDS,
  CONTRACT_VERSION,
  CORE_SLOT_IDS,
  CORE_SLOT_REGISTRY,
  CRITICAL_SLOT_IDS,
  DOMAIN_DOCUMENT_KINDS,
  DOMAIN_ERROR_CODES,
  INVALIDATION_TABLE,
  SLOT_AUTHORITIES,
  SLOT_SOURCES,
  SLOT_STATUSES,
  SLOT_VALUE_TYPES,
  applySlotAction,
  briefIsStale,
  briefProblemsAgainstSlots,
  briefReadiness,
  buildProductBrief,
  canAddSlot,
  canConfirmSlot,
  canDeleteSlot,
  canEditValue,
  checkFactSlot,
  checkProductBrief,
  checkProductInput,
  checkSlotSet,
  emptyProductInput,
  intakeReadiness,
  invalidationsFor,
  slotPermissions,
} from "/domain/index.js";

import { STORAGE_ERROR_CODES, assertJsonSafePayload, openStorage } from "/storage/index.js";
import { dropDatabase, expect, expectCode, newDbName, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const SHA = (char) => char.repeat(64);

function coreSlot(slotId, overrides = {}) {
  const definition = CORE_SLOT_REGISTRY.find((item) => item.slot_id === slotId);
  expect(Boolean(definition), "测试只用注册表里的核心槽位：" + slotId);
  return {
    schema_version: 1,
    slot_id: slotId,
    label: definition.label,
    authority: "core_fixed",
    value_type: definition.value_type,
    critical: definition.critical,
    value: null,
    source: "user_input",
    status: "missing",
    confidence: null,
    evidence: [],
    depends_on: [],
    ...overrides,
  };
}

function dynamicSlot(slotId, overrides = {}) {
  return {
    schema_version: 1,
    slot_id: slotId,
    label: slotId,
    authority: "category_dynamic",
    value_type: "text",
    critical: false,
    value: null,
    source: "model_inference",
    status: "unknown",
    confidence: null,
    evidence: [],
    depends_on: [],
    ...overrides,
  };
}

function confirmed(slot, value, source = "user_input") {
  return { ...slot, value, source, status: "confirmed", confidence: null,
    evidence: [{ kind: "user", ref: "test-fixture" }] };
}

function codes(problems) {
  return problems.map((item) => item.code);
}

function paths(problems) {
  return problems.map((item) => item.path);
}

/* ---------- 词表与注册表 ---------- */

test("C01", "词表与核心注册表冻结：权限与状态的取值域不由界面定义", () => {
  expect(CONTRACT_VERSION === "v2.2.1", "契约版本应为 v2.2.1");
  for (const list of [SLOT_AUTHORITIES, SLOT_SOURCES, SLOT_STATUSES, SLOT_VALUE_TYPES, CHANGE_KINDS]) {
    expect(Object.isFrozen(list), "词表必须冻结");
  }
  expect(CORE_SLOT_IDS.length === CORE_SLOT_REGISTRY.length, "注册表 id 数量一致");
  expect(CRITICAL_SLOT_IDS.join(",") === "product_name,product_category,signature_features",
    "关键槽位应是名称/品类/保持特征，实际 " + CRITICAL_SLOT_IDS.join(","));
  expect(DOMAIN_DOCUMENT_KINDS.fact_slot === "fact_slot", "文档种类与存储层一致");
  return { core_slots: CORE_SLOT_IDS.length, critical: CRITICAL_SLOT_IDS.length };
});

test("C02", "核心槽位必须与注册表一致；未登记的自称 core_fixed 被拒", () => {
  const legal = coreSlot("product_name", { status: "proposed", value: "保温杯", confidence: 0.6, source: "model_inference" });
  expect(checkFactSlot(legal).length === 0, "合法核心槽位应通过：" + JSON.stringify(checkFactSlot(legal)));
  const wrongType = coreSlot("signature_features", { value_type: "text", status: "missing" });
  expect(codes(checkFactSlot(wrongType)).includes(DOMAIN_ERROR_CODES.CONTRACT_INVALID), "类型不符应被拒");
  const wrongCritical = coreSlot("brand", { critical: true, status: "missing" });
  expect(codes(checkFactSlot(wrongCritical)).includes(DOMAIN_ERROR_CODES.CONTRACT_INVALID), "critical 不符应被拒");
  const fakeCore = dynamicSlot("model_invented_core", { authority: "core_fixed", status: "missing" });
  expect(codes(checkFactSlot(fakeCore)).includes(DOMAIN_ERROR_CODES.CONTRACT_INVALID), "未登记核心槽位应被拒");
  return { blocked: 3 };
});

/* ---------- ProductInput ---------- */

test("C03", "商品资料正例：名称 + primary 参考图 → 资料就绪", () => {
  const input = emptyProductInput();
  input.product_name = "蓝色保温杯";
  input.description = "真空保温，容量 500ml";
  input.selling_points = ["保温 12 小时", "单手开盖"];
  input.focus = "秋季主图";
  input.references = [{ asset_sha256: SHA("a"), role: "primary" }];
  const problems = checkProductInput(input);
  expect(problems.length === 0, "合法资料应通过：" + JSON.stringify(problems));
  expect(intakeReadiness(input).ready === true, "资料应就绪");
  return { name: input.product_name };
});

test("C04", "资料缺失被精确定位：名称、参考图、primary 三种", () => {
  const noName = emptyProductInput();
  noName.references = [{ asset_sha256: SHA("a"), role: "primary" }];
  expect(paths(checkProductInput(noName)).includes("$.product_name"), "缺名称应指向 product_name");

  const noRefs = emptyProductInput();
  noRefs.product_name = "蓝色保温杯";
  expect(intakeReadiness(noRefs).ready === false, "无参考图不应就绪");
  expect(paths(checkProductInput(noRefs)).includes("$.references"), "缺参考图应指向 references");

  const noPrimary = emptyProductInput();
  noPrimary.product_name = "蓝色保温杯";
  noPrimary.references = [{ asset_sha256: SHA("b"), role: "detail" }];
  expect(paths(checkProductInput(noPrimary)).includes("$.references"), "无 primary 应被拒");
  return { blocked: 3 };
});

test("C05", "参考图判据：sha 形状、重复登记、角色闭集", () => {
  const base = emptyProductInput();
  base.product_name = "蓝色保温杯";
  const badSha = { ...base, references: [{ asset_sha256: "not-a-hash", role: "primary" }] };
  expect(checkProductInput(badSha).length > 0, "非法 sha 应被拒");
  const duplicate = { ...base, references: [
    { asset_sha256: SHA("a"), role: "primary" },
    { asset_sha256: SHA("a"), role: "detail" },
  ] };
  expect(checkProductInput(duplicate).length > 0, "重复资产应被拒");
  const badRole = { ...base, references: [{ asset_sha256: SHA("a"), role: "hero" }] };
  expect(checkProductInput(badRole).length > 0, "未知角色应被拒");
  return { blocked: 3 };
});

test("C06", "长度上限：超长名称与超量卖点被拒", () => {
  const longName = emptyProductInput();
  longName.product_name = "长".repeat(121);
  longName.references = [{ asset_sha256: SHA("a"), role: "primary" }];
  expect(checkProductInput(longName).length > 0, "超长名称应被拒");

  const manyPoints = emptyProductInput();
  manyPoints.product_name = "蓝色保温杯";
  manyPoints.references = [{ asset_sha256: SHA("a"), role: "primary" }];
  manyPoints.selling_points = Array.from({ length: 21 }, (_item, index) => "卖点 " + index);
  expect(checkProductInput(manyPoints).length > 0, "超量卖点应被拒");
  return { blocked: 2 };
});

/* ---------- FactSlot 形状 ---------- */

test("C07", "FactSlot 正例：人工确认的核心槽位通过全部判据", () => {
  const slot = confirmed(coreSlot("product_name"), "蓝色保温杯");
  expect(checkFactSlot(slot).length === 0, "合法槽位应通过：" + JSON.stringify(checkFactSlot(slot)));
  return { slot_id: slot.slot_id };
});

test("C08", "词表外取值被拒：authority / source / status / value_type", () => {
  const variants = [
    coreSlot("product_name", { authority: "magic", status: "missing" }),
    coreSlot("product_name", { source: "guess", status: "missing" }),
    coreSlot("product_name", { status: "maybe" }),
    coreSlot("product_name", { value_type: "rich_text", status: "missing" }),
  ];
  for (const variant of variants) {
    expect(codes(checkFactSlot(variant)).includes(DOMAIN_ERROR_CODES.CONTRACT_INVALID),
      "非法取值应被拒：" + JSON.stringify(variant));
  }
  return { blocked: variants.length };
});

test("C09", "置信规则：只有 model_inference 能带 confidence，且必须在 0..1", () => {
  const proposed = coreSlot("product_name", { status: "proposed", value: "保温杯", source: "model_inference", confidence: 0.7 });
  expect(checkFactSlot(proposed).length === 0, "模型提案带置信应通过");
  const human = confirmed(coreSlot("product_name"), "蓝色保温杯");
  const withConfidence = { ...human, confidence: 0.9 };
  expect(checkFactSlot(withConfidence).length > 0, "人工来源不应带置信");
  const outOfRange = { ...proposed, confidence: 1.5 };
  expect(checkFactSlot(outOfRange).length > 0, "越界置信应被拒");
  return { blocked: 2 };
});

test("C10", "值形状判据覆盖五种类型", () => {
  const bad = [
    coreSlot("product_name", { status: "confirmed", value: "   " }),
    coreSlot("signature_features", { status: "confirmed", value: [] }),
    coreSlot("signature_features", { status: "confirmed", value: [""] }),
    dynamicSlot("weight_grams", { value_type: "number", status: "confirmed", value: "500" }),
    dynamicSlot("has_gift_box", { value_type: "boolean", status: "confirmed", value: 1 }),
    dynamicSlot("season", { value_type: "enum", status: "confirmed", value: "autumn" }),
    dynamicSlot("season", { value_type: "enum", status: "confirmed", value: "winter", enum_values: ["summer", "autumn"] }),
  ];
  for (const variant of bad) {
    expect(checkFactSlot(variant).length > 0, "坏值形状应被拒：" + JSON.stringify(variant));
  }
  const goodEnum = dynamicSlot("season", { value_type: "enum", status: "confirmed", value: "autumn", source: "user_input", enum_values: ["summer", "autumn"] });
  expect(checkFactSlot(goodEnum).length === 0, "合法 enum 应通过");
  return { blocked: bad.length };
});

test("C11", "状态与值一一对应：该有值的有值，不该有的没有", () => {
  const inconsistent = [
    coreSlot("product_name", { status: "confirmed", value: null }),
    coreSlot("product_name", { status: "missing", value: "保温杯" }),
    coreSlot("product_name", { status: "unknown", value: "保温杯" }),
    dynamicSlot("season", { status: "conflict", value: "autumn", evidence: [{ kind: "user", ref: "a" }, { kind: "model", ref: "b" }] }),
    dynamicSlot("season", { status: "conflict", value: null, evidence: [{ kind: "user", ref: "a" }] }),
  ];
  for (const variant of inconsistent) {
    expect(checkFactSlot(variant).length > 0, "状态与值不一致应被拒：" + JSON.stringify(variant));
  }
  return { blocked: inconsistent.length };
});

test("C12", "proposed 只能来自模型；人工确认模型提案必须保留置信读数", () => {
  const badProposed = dynamicSlot("season", { status: "proposed", value: "autumn", source: "user_input" });
  expect(checkFactSlot(badProposed).length > 0, "人工来源的 proposed 应被拒");
  const confirmedWithoutConfidence = dynamicSlot("season", { status: "confirmed", value: "autumn", source: "model_inference", confidence: null });
  expect(checkFactSlot(confirmedWithoutConfidence).length > 0, "确认模型提案却没留置信应被拒");
  const confirmedWithConfidence = dynamicSlot("season", { status: "confirmed", value: "autumn", source: "model_inference", confidence: 0.4 });
  expect(checkFactSlot(confirmedWithConfidence).length === 0, "带置信的人工确认应通过");
  return { blocked: 2 };
});

test("C13", "派生槽位：来源必须是规则，且必须声明依赖", () => {
  const wrongSource = dynamicSlot("keyword_line", { authority: "derived", status: "confirmed", value: "保温 12 小时", source: "user_input", depends_on: ["product_name"] });
  expect(checkFactSlot(wrongSource).length > 0, "派生槽位非规则来源应被拒");
  const noDeps = dynamicSlot("keyword_line", { authority: "derived", status: "confirmed", value: "保温 12 小时", source: "derived_rule", depends_on: [] });
  expect(checkFactSlot(noDeps).length > 0, "派生槽位无依赖应被拒");
  const legal = dynamicSlot("keyword_line", { authority: "derived", status: "confirmed", value: "保温 12 小时", source: "derived_rule", depends_on: ["product_name"] });
  expect(checkFactSlot(legal).length === 0, "合法派生槽位应通过");
  return { blocked: 2 };
});

test("C14", "自定义槽位：确认值只能来自用户或参考图观察", () => {
  const fromModel = dynamicSlot("gift_note", { authority: "user_custom", status: "confirmed", value: "送切片刀", source: "model_inference", confidence: 0.8 });
  expect(checkFactSlot(fromModel).length > 0, "自定义槽位用模型来源应被拒");
  const fromUser = dynamicSlot("gift_note", { authority: "user_custom", status: "confirmed", value: "送切片刀", source: "user_input" });
  expect(checkFactSlot(fromUser).length === 0, "自定义槽位用户确认应通过");
  return { blocked: 1 };
});

test("C15", "槽位集合判据：重复 id、悬空依赖、自环、两节点环", () => {
  const a = dynamicSlot("season", { status: "missing" });
  const b = dynamicSlot("season", { status: "missing" });
  expect(checkSlotSet([a, b]).length > 0, "重复 slot_id 应被拒");
  const dangling = dynamicSlot("season", { depends_on: ["not_there"], status: "missing" });
  expect(checkSlotSet([dangling]).length > 0, "悬空依赖应被拒");
  const selfLoop = dynamicSlot("season", { depends_on: ["season"], status: "missing" });
  expect(codes(checkSlotSet([selfLoop])).includes(DOMAIN_ERROR_CODES.CONTRACT_DEPENDENCY_CYCLE), "自环应报环");
  const x = dynamicSlot("cycle_x", { depends_on: ["cycle_y"], status: "missing" });
  const y = dynamicSlot("cycle_y", { depends_on: ["cycle_x"], status: "missing" });
  expect(codes(checkSlotSet([x, y])).includes(DOMAIN_ERROR_CODES.CONTRACT_DEPENDENCY_CYCLE), "两节点环应报环");
  return { blocked: 4 };
});

/* ---------- 权限矩阵 ---------- */

test("C16", "权限矩阵逐格：谁能改值由 authority 决定", () => {
  const core = coreSlot("product_name", { status: "missing" });
  const dynamic = dynamicSlot("season", { status: "missing" });
  const custom = dynamicSlot("gift_note", { authority: "user_custom", status: "missing" });
  const customOpen = dynamicSlot("gift_note", { authority: "user_custom", status: "missing", allow_model_proposal: true });
  const derived = dynamicSlot("keyword_line", { authority: "derived", status: "missing", source: "derived_rule", depends_on: ["product_name"] });
  expect(canEditValue(core, "user") && canEditValue(core, "model") && !canEditValue(core, "rule"), "核心：用户与模型可写，规则不可写");
  expect(canEditValue(dynamic, "user") && canEditValue(dynamic, "model") && !canEditValue(dynamic, "rule"), "动态：用户与模型可写");
  expect(canEditValue(custom, "user") && !canEditValue(custom, "model") && !canEditValue(custom, "rule"), "自定义：模型默认不能写");
  expect(canEditValue(customOpen, "model"), "自定义槽位显式放开后模型可提案");
  expect(!canEditValue(derived, "user") && !canEditValue(derived, "model") && canEditValue(derived, "rule"), "派生：只有规则可写");
  const permissions = slotPermissions(derived);
  expect(permissions.confirm.user === false && permissions.confirm.rule === true, "派生槽位由规则确认");
  expect(permissions.confirm.model === false, "任何情况下模型都不能确认");
  return { checked: 5 };
});

test("C17", "增删权限：核心不可删、动态有依赖不可删、自定义自由、模型只能加动态", () => {
  const core = coreSlot("brand", { status: "missing" });
  const dynamic = dynamicSlot("season", { status: "missing" });
  const custom = dynamicSlot("gift_note", { authority: "user_custom", status: "missing" });
  const derived = dynamicSlot("keyword_line", { authority: "derived", status: "missing", source: "derived_rule", depends_on: ["product_name"] });
  expect(!canDeleteSlot(core), "核心不可删");
  expect(canDeleteSlot(dynamic, { dependencyCount: 0 }) && !canDeleteSlot(dynamic, { dependencyCount: 1 }), "动态：无依赖可删、有依赖不可删");
  expect(canDeleteSlot(custom, { dependencyCount: 3 }), "自定义不受依赖限制");
  expect(!canDeleteSlot(derived), "派生不可删");

  expect(!canAddSlot(coreSlot("product_name", { status: "missing" }), "user"), "用户不能新增核心槽位");
  expect(canAddSlot(dynamicSlot("season", { status: "missing" }), "user"), "用户可新增动态槽位");
  expect(canAddSlot(dynamicSlot("season", { status: "missing" }), "model"), "模型可提议新动态槽位");
  expect(!canAddSlot(custom, "model"), "模型不能新增自定义槽位");
  expect(!canAddSlot(dynamicSlot("season", { status: "missing" }), "user", { existingSlots: [dynamicSlot("season", { status: "missing" })] }), "重复 id 不能再加");
  return { checked: 9 };
});

test("C18", "模型不能确认事实：propose 可以，confirm 必须被拒", () => {
  const proposed = dynamicSlot("season", { status: "proposed", value: "autumn", source: "model_inference", confidence: 0.7 });
  expectCode(() => applySlotAction(proposed, { action: "confirm", actor: "model" }),
    DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "模型确认应被拒");
  expect(!canConfirmSlot(proposed, "model") && canConfirmSlot(proposed, "user"), "确认权只在用户");
  return { blocked: 1 };
});

/* ---------- 状态转换 ---------- */

test("C19", "模型提案：proposed + 置信 + 证据，一律不许自动变 confirmed", () => {
  const slot = coreSlot("product_category", { status: "missing" });
  const next = applySlotAction(slot, {
    action: "propose", actor: "model", value: "保温杯", confidence: 0.66,
    evidence: [{ kind: "asset", ref: SHA("a") }],
  });
  expect(next.status === "proposed" && next.source === "model_inference", "结果应是 proposed/model_inference");
  expect(next.confidence === 0.66, "置信应原样保留");
  expect(next.evidence.length === 1 && next.evidence[0].kind === "asset", "证据应保留");
  expect(slot.status === "missing" && slot.value === null, "入参槽位不得被修改");
  return { status: next.status };
});

test("C20", "模型提案与已确认值不同 → 冲突（不得静默覆盖人工事实）", () => {
  const slot = confirmed(coreSlot("product_category"), "保温杯");
  const next = applySlotAction(slot, {
    action: "propose", actor: "model", value: "马克杯", confidence: 0.8,
  });
  expect(next.status === "conflict", "应变成 conflict，实际 " + next.status);
  expect(next.value === null, "冲突时不许留下单方值");
  expect(next.evidence.length >= 2, "冲突必须留下两条证据");
  const notes = next.evidence.map((item) => item.note).join("|");
  expect(notes.includes("保温杯") && notes.includes("马克杯"), "两条证据要能看到争议双方");
  return { evidence: next.evidence.length };
});

test("C21", "模型提案与已确认值相同 → 保持 confirmed，只留证据", () => {
  const slot = confirmed(coreSlot("product_category"), "保温杯");
  const next = applySlotAction(slot, {
    action: "propose", actor: "model", value: "保温杯", confidence: 0.9,
    evidence: [{ kind: "model", ref: "second-opinion" }],
  });
  expect(next.status === "confirmed" && next.value === "保温杯", "状态与值都不应变化");
  expect(next.evidence.some((item) => item.ref === "second-opinion"), "证据应追加");
  return { status: next.status };
});

test("C22", "用户编辑：值变为人工事实，模型置信被清除", () => {
  const proposed = dynamicSlot("season", { status: "proposed", value: "autumn", source: "model_inference", confidence: 0.7 });
  const next = applySlotAction(proposed, { action: "edit", actor: "user", value: "秋季上新" });
  expect(next.status === "confirmed" && next.source === "user_input", "应变为人工确认");
  expect(next.confidence === null, "人工事实不再携带模型置信");
  return { value: next.value };
});

test("C23", "冲突确认必须带裁决值；无值确认被拒", () => {
  const conflict = dynamicSlot("season", {
    status: "conflict", value: null,
    evidence: [{ kind: "user", ref: "confirmed_value", note: "autumn" }, { kind: "model", ref: "model_proposal", note: "winter" }],
  });
  expectCode(() => applySlotAction(conflict, { action: "confirm", actor: "user" }),
    DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "无裁决值的确认应被拒");
  const resolved = applySlotAction(conflict, { action: "confirm", actor: "user", value: "autumn" });
  expect(resolved.status === "confirmed" && resolved.value === "autumn", "带裁决值应确认成功");
  return { resolved: resolved.value };
});

test("C24", "派生槽位：用户不能直接改值，规则确认合法", () => {
  const derived = dynamicSlot("keyword_line", { authority: "derived", status: "missing", source: "derived_rule", depends_on: ["product_name"] });
  expectCode(() => applySlotAction(derived, { action: "edit", actor: "user", value: "保温 12 小时" }),
    DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "用户直接改派生值应被拒");
  const next = applySlotAction(derived, { action: "confirm", actor: "rule", value: "保温 12 小时" });
  expect(next.status === "confirmed" && next.source === "derived_rule", "规则确认应成功且来源正确");
  return { value: next.value };
});

test("C25", "supersede 是终态：不能再提案、无值确认被拒", () => {
  const slot = confirmed(coreSlot("brand"), "旧品牌");
  const retired = applySlotAction(slot, { action: "supersede", actor: "user" });
  expect(retired.status === "superseded", "应转为 superseded");
  expectCode(() => applySlotAction(retired, { action: "supersede", actor: "user" }),
    DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "重复 supersede 应被拒");
  expectCode(() => applySlotAction(retired, { action: "confirm", actor: "user" }),
    DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "无值重新确认应被拒");
  expectCode(() => applySlotAction(retired, { action: "propose", actor: "model", value: "新品牌", confidence: 0.5 }),
    DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "对 superseded 提案应被拒");
  return { blocked: 3 };
});

test("C26", "标记冲突：证据不足被拒，两条证据成立且清空单方值", () => {
  const slot = confirmed(dynamicSlot("season"), "autumn");
  expectCode(() => applySlotAction(slot, { action: "mark_conflict", actor: "user", evidence: [{ kind: "user", ref: "only-one" }] }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "单条证据应被拒");
  const next = applySlotAction(slot, { action: "mark_conflict", actor: "user", evidence: [
    { kind: "user", ref: "a", note: "autumn" }, { kind: "asset", ref: SHA("c"), note: "winter" },
  ] });
  expect(next.status === "conflict" && next.value === null, "应转为冲突且无单方值");
  return { evidence: next.evidence.length };
});

test("C27", "标记未知：清空值并保留槽位（Unknown 不许当成失败或成功）", () => {
  const proposed = dynamicSlot("season", { status: "proposed", value: "autumn", source: "model_inference", confidence: 0.5 });
  const next = applySlotAction(proposed, { action: "mark_unknown", actor: "user" });
  expect(next.status === "unknown" && next.value === null, "应转为 unknown 且无值");
  return { status: next.status };
});

/* ---------- 失效图 ---------- */

test("C28", "失效图逐类匹配：失效集与保留集都必须完全一致", () => {
  const expected = {
    references_changed: {
      invalidates: ["product_brief", "suite_plan", "prompt_versions", "review_reports", "selection"],
      preserves: ["project_history", "candidate_blobs", "source_assets"],
    },
    identity_fact_changed: {
      invalidates: ["product_brief", "suite_plan", "prompt_versions", "review_reports", "selection"],
      preserves: ["project_history", "candidate_blobs", "source_assets"],
    },
    style_changed: {
      invalidates: ["prompt_versions", "review_reports", "suite_consistency_report"],
      preserves: ["project_history", "candidate_blobs", "product_brief", "suite_plan", "source_assets"],
    },
    shot_spec_changed: {
      invalidates: ["prompt_versions", "review_reports", "selection"],
      preserves: ["project_history", "candidate_blobs", "product_brief", "suite_plan", "other_shots", "source_assets"],
    },
    prompt_edited: {
      invalidates: ["prompt_versions", "review_reports", "selection"],
      preserves: ["project_history", "candidate_blobs", "product_brief", "suite_plan", "shot_spec", "other_shots"],
    },
    shot_added_or_removed: {
      invalidates: ["suite_plan_revision", "selection_completeness", "suite_consistency_report"],
      preserves: ["project_history", "candidate_blobs", "existing_shot_history", "source_assets"],
    },
  };
  expect(Object.keys(INVALIDATION_TABLE).length === CHANGE_KINDS.length, "失效图必须覆盖全部变化类型");
  for (const [kind, want] of Object.entries(expected)) {
    const got = invalidationsFor(kind, { shotId: "s1" });
    expect(JSON.stringify(got.invalidates.sort()) === JSON.stringify([...want.invalidates].sort()),
      kind + " 失效集不符：" + JSON.stringify(got.invalidates));
    expect(JSON.stringify(got.preserves.sort()) === JSON.stringify([...want.preserves].sort()),
      kind + " 保留集不符：" + JSON.stringify(got.preserves));
  }
  for (const kind of CHANGE_KINDS) {
    const got = invalidationsFor(kind, { shotId: "s1", shotIds: ["s2"], briefUsesSlot: true });
    expect(got.preserves.includes("project_history") && got.preserves.includes("candidate_blobs"),
      kind + " 必须保留历史与 Blob");
  }
  return { kinds: CHANGE_KINDS.length };
});

test("C29", "定向失效：只失效引用该事实的 Shot，其余 Shot 必须保留", () => {
  const result = invalidationsFor("fact_value_changed", { shotIds: ["s2"], briefUsesSlot: true });
  expect(result.scope === "targeted", "应是定向失效");
  expect(result.invalidates.includes("product_brief"), "brief 引用了该事实时必须失效");
  expect(result.invalidates.includes("shot:s2:prompt") && result.invalidates.includes("shot:s2:review")
    && result.invalidates.includes("shot:s2:selection"), "目标 Shot 下游必须失效");
  expect(!result.invalidates.some((item) => item.includes("s1")), "无关 Shot 不得被打包失效");
  expect(result.preserves.includes("unreferenced_shots"), "未引用该事实的 Shot 必须保留");

  const notInBrief = invalidationsFor("fact_value_changed", { shotIds: [], briefUsesSlot: false });
  expect(notInBrief.invalidates.length === 0, "没有引用方时不应凭空失效");
  return { invalidates: result.invalidates.length };
});

test("C30", "Shot 级失效必须带 shotId：没有目标就无法限制影响范围", () => {
  expectCode(() => invalidationsFor("shot_spec_changed", {}),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺 shotId 应被拒");
  expectCode(() => invalidationsFor("prompt_edited", {}),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺 shotId 应被拒");
  expectCode(() => invalidationsFor("not_a_change", { shotId: "s1" }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未知变化类型应被拒");
  return { blocked: 3 };
});

/* ---------- ProductBrief 投影与就绪门 ---------- */

test("C31", "投影：已确认的进事实、未决的进待处理，basis 记录精确版本", () => {
  const name = confirmed(coreSlot("product_name"), "蓝色保温杯");
  const category = confirmed(coreSlot("product_category"), "保温杯");
  const material = dynamicSlot("key_material_detail", {
    status: "proposed", value: "304 不锈钢", source: "model_inference", confidence: 0.5,
  });
  const brief = buildProductBrief([
    { slot: name, version: 1 },
    { slot: category, version: 2 },
    { slot: material, version: 1 },
  ]);
  expect(checkProductBrief(brief).length === 0, "投影结果必须合法：" + JSON.stringify(checkProductBrief(brief)));
  expect(brief.confirmed_facts.length === 2 && brief.unresolved.length === 1, "事实/待处理分区错误");
  expect(brief.category && brief.category.value === "保温杯", "类别应从 product_category 提取");
  const basisForName = brief.basis.find((item) => item.slot_id === "product_category");
  expect(basisForName.version === 2, "basis 必须记录真实版本");
  return { basis: brief.basis.length };
});

test("C32", "brief 反向探针：引用不在 basis、重复状态、错误类别来源都被拒", () => {
  const base = {
    schema_version: 1,
    basis: [{ slot_id: "product_name", version: 1 }],
    category: null,
    confirmed_facts: [{ slot_id: "product_name", label: "商品名称", value: "蓝色保温杯", source: "user_input" }],
    unresolved: [],
  };
  expect(checkProductBrief(base).length === 0, "基线 brief 应合法");
  const notInBasis = { ...base, confirmed_facts: [{ slot_id: "brand", label: "品牌", value: "Acme", source: "user_input" }] };
  expect(checkProductBrief(notInBasis).length > 0, "引用不在 basis 的事实应被拒");
  const bothStates = { ...base, unresolved: [{ slot_id: "product_name", label: "商品名称", status: "conflict", critical: true }] };
  expect(checkProductBrief(bothStates).length > 0, "同一槽位既确认又待处理应被拒");
  const wrongCategory = { ...base, category: { slot_id: "season", value: "autumn" } };
  expect(checkProductBrief(wrongCategory).length > 0, "类别来源错误应被拒");
  const badStatus = { ...base, unresolved: [{ slot_id: "brand", label: "品牌", status: "confirmed", critical: false }] };
  expect(checkProductBrief(badStatus).length > 0, "unresolved 不允许 confirmed 状态");
  return { blocked: 4 };
});

test("C33", "brief 与当前事实对照：版本落后、值被改、待处理已确认三类都报", () => {
  const name = confirmed(coreSlot("product_name"), "蓝色保温杯");
  const brief = buildProductBrief([{ slot: name, version: 1 }]);

  const staleProblems = briefProblemsAgainstSlots(brief, [{ slot: name, version: 2 }]);
  expect(staleProblems.some((item) => item.message.includes("已过期")), "版本落后应报过期");

  const changed = confirmed(coreSlot("product_name"), "红色保温杯");
  const changedProblems = briefProblemsAgainstSlots(brief, [{ slot: changed, version: 1 }]);
  expect(changedProblems.some((item) => item.message.includes("不一致")), "值被改应报不一致");

  const stillOpen = buildProductBrief([
    { slot: name, version: 1 },
    { slot: dynamicSlot("season", { status: "proposed", value: "autumn", source: "model_inference", confidence: 0.5 }), version: 1 },
  ]);
  const nowConfirmed = confirmed(dynamicSlot("season"), "autumn");
  const resolvedProblems = briefProblemsAgainstSlots(stillOpen, [
    { slot: name, version: 1 },
    { slot: nowConfirmed, version: 2 },
  ]);
  expect(resolvedProblems.some((item) => item.message.includes("不该继续留在待处理")), "已解决的槽位不该留在待处理");
  return { problem_kinds: 3 };
});

test("C34", "过期是版本事实，不是界面判断：briefIsStale 给出可读原因", () => {
  const category = confirmed(coreSlot("product_category"), "保温杯");
  const brief = buildProductBrief([{ slot: category, version: 3 }]);
  const fresh = briefIsStale(brief, [{ slot: category, version: 3 }]);
  expect(fresh.stale === false, "版本一致不应报过期");
  const stale = briefIsStale(brief, [{ slot: category, version: 4 }]);
  expect(stale.stale === true, "版本前进应报过期");
  expect(stale.reasons[0].basis_version === 3 && stale.reasons[0].current_version === 4, "原因要能定位到版本");
  const missingSlot = briefIsStale(brief, []);
  expect(missingSlot.stale === true && missingSlot.reasons[0].current_version === null, "槽位消失也要报过期");
  return { reasons: stale.reasons.length };
});

test("C35", "就绪门：关键槽位未确认或没有任何事实时不许进入计划", () => {
  const name = confirmed(coreSlot("product_name"), "蓝色保温杯");
  const openCategory = coreSlot("product_category", { status: "missing" });
  const notReady = briefReadiness(buildProductBrief([
    { slot: name, version: 1 },
    { slot: openCategory, version: 1 },
  ]));
  expect(notReady.ready === false, "关键槽位缺失不应就绪");
  expect(notReady.blocking.some((item) => item.slot_id === "product_category" && item.code === "CRITICAL_SLOT_UNRESOLVED"),
    "阻塞项要指出关键槽位");

  const empty = briefReadiness(buildProductBrief([]));
  expect(empty.ready === false && empty.blocking.some((item) => item.code === "NO_CONFIRMED_FACTS"),
    "没有任何事实不应就绪");

  const ready = briefReadiness(buildProductBrief([
    { slot: name, version: 1 },
    { slot: confirmed(coreSlot("product_category"), "保温杯"), version: 1 },
    { slot: confirmed(coreSlot("signature_features"), ["无品牌标识", "哑光深蓝"]), version: 1 },
    { slot: dynamicSlot("season", { status: "proposed", value: "autumn", source: "model_inference", confidence: 0.4 }), version: 1 },
  ]));
  expect(ready.ready === true, "关键项齐了、只剩非关键待办时应就绪：" + JSON.stringify(ready.blocking));
  return { blocked: 2 };
});

/* ---------- 与存储层的集成 ---------- */

test("C36", "落库集成：资料/槽位/理解都是版本化文档；槽位升级后 brief 过期且历史保留", async () => {
  const name = newDbName("amz-v2-brief");
  const opened = await openStorage({ name });
  try {
    const repository = opened.repository;
    const project = await repository.projects.create({ name: "契约集成" });

    const input = emptyProductInput();
    input.product_name = "蓝色保温杯";
    input.references = [{ asset_sha256: SHA("d"), role: "primary" }];
    const inputRecord = await repository.documents.save(project.project_id, {
      kind: DOMAIN_DOCUMENT_KINDS.product_input, documentId: "intake", payload: input,
    });
    expect(inputRecord.version === 1, "资料应是第 1 版");

    const nameSlot = confirmed(coreSlot("product_name"), "蓝色保温杯");
    const categorySlot = confirmed(coreSlot("product_category"), "保温杯");
    const nameRecord = await repository.documents.save(project.project_id, {
      kind: DOMAIN_DOCUMENT_KINDS.fact_slot, documentId: "product_name", payload: nameSlot,
    });
    const categoryRecord = await repository.documents.save(project.project_id, {
      kind: DOMAIN_DOCUMENT_KINDS.fact_slot, documentId: "product_category", payload: categorySlot,
    });

    const brief = buildProductBrief([
      { slot: nameSlot, version: nameRecord.version },
      { slot: categorySlot, version: categoryRecord.version },
    ]);
    const briefRecord = await repository.documents.save(project.project_id, {
      kind: DOMAIN_DOCUMENT_KINDS.product_brief, documentId: "brief", payload: brief,
    });
    const reloaded = await repository.documents.getLatest(
      project.project_id, DOMAIN_DOCUMENT_KINDS.product_brief, "brief");
    expect(reloaded.version === briefRecord.version
      && reloaded.payload.confirmed_facts.length === 2, "理解应能按版本读回");

    // 上游变化：品类值被用户改写 → 槽位新版本 → 理解过期
    const editedCategory = applySlotAction(categorySlot, { action: "edit", actor: "user", value: "真空保温杯" });
    const categoryV2 = await repository.documents.save(project.project_id, {
      kind: DOMAIN_DOCUMENT_KINDS.fact_slot, documentId: "product_category", payload: editedCategory,
    });
    expect(categoryV2.version === 2, "第二次写入应是第 2 版");
    const stale = briefIsStale(brief, [
      { slot: nameSlot, version: nameRecord.version },
      { slot: editedCategory, version: categoryV2.version },
    ]);
    expect(stale.stale === true && stale.reasons[0].current_version === 2, "理解必须被判定为过期");
    const compare = briefProblemsAgainstSlots(brief, [
      { slot: nameSlot, version: nameRecord.version },
      { slot: editedCategory, version: categoryV2.version },
    ]);
    expect(compare.length > 0, "对照当前事实应报出不一致");

    const versions = await repository.documents.listVersions(
      project.project_id, DOMAIN_DOCUMENT_KINDS.fact_slot, "product_category");
    expect(versions.length === 2, "旧版本必须保留");
    expect(versions.some((item) => item.version === 1 && item.payload.value === "保温杯"), "第 1 版内容仍可读");
    const allDocs = await repository.documents.listAll(project.project_id);
    expect(allDocs.length === 5, "总共 5 个文档版本（资料 1 + 名称 1 + 品类 2 + 理解 1），实际 " + allDocs.length);
    return { documents: allDocs.length, stale_reasons: stale.reasons.length };
  } finally {
    opened.close();
    await dropDatabase(name);
  }
});

test("C37", "领域对象必须是可 JSON 往返的纯数据：Blob / 函数混入一律被拒", () => {
  const slot = confirmed(coreSlot("product_name"), "蓝色保温杯");
  assertJsonSafePayload(slot);
  expectCode(() => assertJsonSafePayload({ ...slot, blob: new Blob(["x"]) }),
    STORAGE_ERROR_CODES.SCHEMA_INVALID, "Blob 应被存储层拒绝");
  expectCode(() => assertJsonSafePayload({ ...slot, fn: () => 1 }),
    STORAGE_ERROR_CODES.SCHEMA_INVALID, "函数应被存储层拒绝");
  return { blocked: 2 };
});

/* ---------- 运行器 ---------- */

function render(results) {
  const target = document.getElementById("results");
  if (!target) return;
  target.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.2.1-product-contracts",
    status: "running",
    started_at: new Date().toISOString(),
    cases: [],
  };
  window.__V2_BRIEF_RESULTS__ = results;
  localStorage.clear();
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      const detail = await item.run();
      results.cases.push({
        id: item.id, title: item.title, ok: true,
        detail: detail === undefined ? null : detail,
        ms: Math.round(performance.now() - startedAt),
      });
    } catch (error) {
      results.cases.push({
        id: item.id, title: item.title, ok: false,
        error: serializeError(error),
        ms: Math.round(performance.now() - startedAt),
      });
    }
  }
  const failed = results.cases.filter((item) => !item.ok);
  results.status = failed.length === 0 ? "passed" : "failed";
  results.failed_ids = failed.map((item) => item.id);
  results.finished_at = new Date().toISOString();
  render(results);
}

const params = new URLSearchParams(location.search);
if (params.get("suite") !== "0") {
  runSuite().catch((error) => {
    window.__V2_BRIEF_RESULTS__ = {
      suite: "v2.2.1-product-contracts",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_BRIEF_RESULTS__);
  });
} else {
  window.__V2_BRIEF_RESULTS__ = { suite: "v2.2.1-product-contracts", status: "skipped", cases: [] };
}
