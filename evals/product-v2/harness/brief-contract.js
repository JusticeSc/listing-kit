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

/* R3.2：纯领域断言已迁至 evals/product-v2/node/（同名 .test.mjs），此处仅保留宿主特有案例。 */

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
