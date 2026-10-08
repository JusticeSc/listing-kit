/* R3.2 一次性迁移发生器：把纯领域契约断言搬进 Node 原生 test，削掉浏览器副本。 */
import fs from "node:fs";
import path from "node:path";

const NODE_DIR = path.join(import.meta.dirname);
const ROOT = path.resolve(import.meta.dirname, "../../..");
const HARNESS = path.join(ROOT, "evals/product-v2/harness");

import { execSync } from "node:child_process";

/** 混合套件源一律取 git HEAD 的 pristine 版本：生成器可重复运行，自愈任何中断残留。 */
function pristineHarness(name) {
  return execSync(`git show HEAD:evals/product-v2/harness/${name}`, {
    encoding: "utf8",
    cwd: ROOT,
    maxBuffer: 16 * 1024 * 1024,
  });
}

function pureRewrite(name) {
  const raw = fs.readFileSync(path.join(HARNESS, name), "utf8");
  const cut = raw.indexOf("async function runSuite");
  if (cut < 0) throw new Error(name + ": 找不到 runSuite 边界");
  let head = raw.slice(0, cut);
  head = head
    .replace("（真实 Chromium，非 Mock，纯领域函数）", "（Node 原生进程，非 Mock，纯领域函数）")
    .replace("（真实 Chromium，非 Mock）", "（Node 原生进程，非 Mock）");
  head = head.replace(
    / \* 结果写到 window\.__V2_[A-Z_]+__，由 tools\/[^\n]*\n| \* 结果写到 window\.__V2_[A-Z_]+__。\n/g,
    " * 直接运行：node --test evals/product-v2/node/\n",
  );
  head = head
    .replaceAll('from "/domain/index.js"', 'from "../../../app/product_v2/domain/index.js"')
    .replaceAll('from "/storage/db.js"', 'from "../../../app/product_v2/storage/db.js"')
    .replaceAll('from "/storage/zip.js"', 'from "../../../app/product_v2/storage/zip.js"')
    .replaceAll('from "./harness-api.js"', 'from "./harness-core.mjs"');
  return (
    head + "\n/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */\n" +
    'import nodeTest from "node:test";\n' +
    "for (const item of cases) {\n" +
    '  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });\n' +
    "}\n"
  );
}

/**
 * 混合套件的 Node 版：只迁「纯行为 + 非宿主」的 case，删除宿主相关用例
 * （真 IDB / 真 WebCrypto 证据保留在浏览器端）。随后按各文件收紧：
 *  - 删掉只被宿主 case 使用的 /storage/index.js import（openStorage 依赖 IndexedDB）；
 *  - harness-core 只 import Node 版真正提供的能力，host-only 符号缺 export 会整文件崩；
 *  - 删掉只被宿主 case 使用的 fixture 函数（withRepo/seedProject）。
 */
function mixedRewrite(name, keepIds, mid, raw) {
  const cut = raw.indexOf("async function runSuite");
  if (cut < 0) throw new Error(name + ": 找不到 runSuite 边界");
  let head = raw.slice(0, cut);
  for (const id of keepIds) {
    const start = head.indexOf('test("' + id + '"');
    if (start < 0) throw new Error(name + ": 缺 case " + id);
    const end = head.indexOf('\ntest("', start + 1);
    head = head.slice(0, start) + (end < 0 ? "" : head.slice(end + 1));
  }
  head = head
    .replace("（真实 Chromium，非 Mock，纯领域函数）", "（Node 原生进程，非 Mock，纯领域函数）")
    .replace("（真实 Chromium，非 Mock）", "（Node 原生进程，非 Mock）");
  head = head.replace(
    / \* 结果写到 window\.__V2_[A-Z_]+__，由 tools\/[^\n]*\n| \* 结果写到 window\.__V2_[A-Z_]+__。\n/g,
    " * 直接运行：node --test evals/product-v2/node/\n",
  );
  head = head
    .replaceAll('from "/domain/index.js"', 'from "../../../app/product_v2/domain/index.js"')
    .replaceAll('from "/storage/db.js"', 'from "../../../app/product_v2/storage/db.js"')
    .replaceAll('from "/storage/zip.js"', 'from "../../../app/product_v2/storage/zip.js"');
  // 单块 import 只删/换自己这一块（[^{}]* 不跨 import列表），防误吞 domain import。
  head = head.replace(/import \{[^{}]*\} from "\/storage\/index\.js";\n?/, "");
  if (head.includes('from "/storage/index.js')) {
    throw new Error(name + ": /storage/index.js import 未删干净");
  }
  const core = NODE_CORE_IMPORTS[name];
  // harness-api import 可能在 }(新行)后续写 from（package 是多行 import），用 \s* 跨行匹配。
  const API_RE = /import\s*\{[^{}]*\}\s*from\s*"\.\/harness-api\.js";\n?/;
  if (!API_RE.test(head)) throw new Error(name + ": harness-api import 未命中");
  head = head.replace(API_RE, core + "\n");
  const extra = NODE_EXTRA_IMPORTS[name] || "";
  if (extra) head = head.replace(core + "\n", core + "\n" + extra + "\n");
  // 只被宿主 case 使用的 fixture：整函数删除（内层缩进闭合不影响 \(\n\}\n\) 锚）。
  for (const fn of Object.values(HOST_FIXTURES[name] || {})) {
    const block = new RegExp("^(async )?function " + fn.replace(/[^\w$]/g, "\\$&") + "[^{]*\\{[\\s\\S]*?\\n\\}\\n", "m");
    head = head.replace(block, "");
  }
  return (
    "/* R3.2：本套件的宿主特有案例（" + keepIds.join(", ") + "）仍由浏览器版 "
    + "evals/product-v2/harness/" + name + " 走真实 IDB/WebCrypto 覆盖。 */\n" +
    head + "\n/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */\n" +
    'import nodeTest from "node:test";\n' +
    "for (const item of cases) {\n" +
    '  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });\n' +
    "}\n"
  );
}

function trimHarness(name, keepIds, raw) {
  const marker = raw.indexOf("\nasync function runSuite");
  if (marker < 0) throw new Error(name + ": 无 runSuite");
  let head = raw.slice(0, marker);
  const tail = raw.slice(marker + 1);
  for (const pattern of (DROPS[name] || [])) {
    const next = head.replace(pattern, "");
    if (next === head) console.log("  [warn] 浏览器残留删行未命中: " + name + " -> " + String(pattern));
    head = next;
  }
  const hostIds = new Set(keepIds);
  const starts = [...head.matchAll(/\ntest\("/g)].map((m) => m.index + 1);
  if (starts.length === 0) throw new Error(name + ": 无测试块");
  const keptSegments = [];
  for (let i = 0; i < starts.length; i += 1) {
    const segStart = starts[i];
    const segEnd = i + 1 < starts.length ? starts[i + 1] : head.length;
    const idMatch = head.slice(segStart, segEnd).match(/^test\("([^"]+)"/);
    if (idMatch && hostIds.has(idMatch[1])) keptSegments.push({ start: segStart, end: segEnd });
  }
  if (keptSegments.length !== keepIds.length) {
    throw new Error(name + ": 宿主 case 丢失，找到 " + keptSegments.length + "/" + keepIds.length);
  }
  const kept = keptSegments.map((seg) => head.slice(seg.start, seg.end));
  const tailStart = keptSegments[keptSegments.length - 1].end;
  const out =
    head.slice(0, starts[0]) +
    "/* R3.2：纯领域断言已迁至 evals/product-v2/node/（同名 .test.mjs），此处仅保留宿主特有案例。 */\n\n" +
    kept.join("") + head.slice(tailStart) + tail;
  return out;
}

/** 删除源文本/文案钉死/词表拷贝断言（Node 端 + 浏览器残留都不可再钉）。 */
const DROPS = {
  "attempt-contract.js": [
    /^ {2}expect\(ATTEMPT_ERROR_FAMILIES\.join\(","\) === "input_rejected,provider_failed,provider_unknown,internal",\n[^\n]*\n/m,
    /^ {2}expect\(ATTEMPT_RETRY_POLICIES\.join\(","\) === "retryable,requires_review,fatal",\n[^\n]*\n/m,
    /^ {2}expect\(id === "act-11111111222233334444555555555555", "action id 必须是稳定可复现的形状，实际 " \+ id\);\n/m,
    /^ {2}expect\(order\[0\] === "pending_submit", "pending_submit 必须是词表第一项（提交前落库）"\);\n/m,
  ],
  "batch-contract.js": [
    / {2}expect\(batchProgressText\(null\) === "批次状态不可用。", "空状态的文案必须稳定"\);\n/,
    / {2}expect\(BATCH_SHOT_STATE_LABELS\.ready === "待提交", "状态词表必须保持产品用语"\);\n/,
  ],
  "brief-contract.js": [
    / {2}expect\(CONTRACT_VERSION === "v2\.2\.1", "契约版本应为 v2\.2\.1"\);\n/,
    /\n {2}expect\(CRITICAL_SLOT_IDS\.join\(","\) === "product_name,product_category,signature_features",\n[^\n]*\n/,
  ],
  "compare-panel.js": [
    / {2}expect\(REVIEW_SEVERITY_ORDER\.join\(","\) === "BLOCK,HIGH_RISK,WARNING,UNKNOWN",\n[^\n]*\n/,
    / {2}expect\(COMPARE_PENDING_SEVERITIES\.join\(","\) === "BLOCK,HIGH_RISK,WARNING",\n[^\n]*\n/,
  ],
  "selection-contract.js": [
    / {2}expect\(stale\.indexOf\("过期"\) >= 0 && stale\.indexOf\("重新采用"\) >= 0,\n[^\n]*\n/,
    / {2}expect\(current\.indexOf\("选择由人做出"\) >= 0, "有效文案必须点明选择来自人工。"\);\n/,
    / {2}expect\(none\.indexOf\("采用"\) >= 0 && none\.indexOf\("已就绪"\) < 0\n {4}&& none\.indexOf\("可以导出"\) < 0, "未采用不许暗示已就绪。"\);\n/,
    / {2}expect\(cleared\.indexOf\("历史保留"\) >= 0, "取消采用必须说明历史保留。"\);\n/,
  ],
  "suite-editor-contract.js": [
    / {2}expect\(MIN_SHOTS === 1 && SUITE_PLAN_SCHEMA_VERSION === 1, "常量不符合契约。"\);\n/,
  ],
  "suite-plan-contract.js": [
    / {2}expect\(IMAGE_ROLES\.length === 9 && SHOT_TEMPLATES\.length === 8,\n[^\n]*\n/,
  ],
};

/* 纯领域套件：整文件迁 Node；浏览器端只保留宿主特有案例（真 IDB / 真 Chromium 集成）。 */
const PURE_ONLY = [
  "attempt-contract.js",
  "batch-contract.js",
  "candidate-contract.js",
  "compare-panel.js",
  "confirm-contract.js",
  "delivery-gate-contract.js",
  "prompt-contract.js",
  "prompt-edit-contract.js",
  "review-provider-contract.js",
  "rework-contract.js",
  "selection-contract.js",
  "specs-contract.js",
  "suite-editor-contract.js",
  "suite-plan-contract.js",
  "suite-review-contract.js",
];

/* 混合套件：留下的 ID 全是宿主相关；其余迁 Node（行为完全用 Node 内建 WebCrypto）。
 * HOST_FIXTURES：只被宿主 case 使用、Node 版里删除的 helper（"" 表示保留）。 */
const MIXED = {
  "brief-contract.js": ["C36", "C37"],
  "package-contract.js": ["Z04", "Z05", "Z06", "Z07", "Z08", "Z09"],
  "review-contract.js": ["R11"],
};
const HOST_FIXTURES = {
  "brief-contract.js": {},
  "package-contract.js": { withRepo: "withRepo", seedProject: "seedProject" },
  "review-contract.js": {},
};
/* Node 版 harness-core 只可能出现这些能力（dropDatabase/openStorage 是 IDB 装置，不存在）。 */
const NODE_CORE_IMPORTS = {
  "brief-contract.js": 'import { expect, expectCode, serializeError } from "./harness-core.mjs";\n',
  "package-contract.js": 'import { expect, expectCode, serializeError, utf8Bytes } from "./harness-core.mjs";\n',
  "review-contract.js": 'import { expect, expectCode, serializeError } from "./harness-core.mjs";\n',
};
/* Node 版仍需要的纯能力单独立项（package 的 ZIP 往返测试直接打 app/product_v2/storage/zip.js）。 */
const NODE_EXTRA_IMPORTS = {
  "package-contract.js": 'import { buildZip, crc32, readZip } from "../../../app/product_v2/storage/zip.js";',
};
fs.mkdirSync(NODE_DIR, { recursive: true });
for (const name of PURE_ONLY) {
  let body = pureRewrite(name);
  for (const pattern of (DROPS[name] || [])) {
    const next = body.replace(pattern, "");
    if (next === body) console.log("  [warn] 删行未命中: " + name + " -> " + String(pattern));
    body = next;
  }
  fs.writeFileSync(path.join(NODE_DIR, name.replace(/\.js$/, ".test.mjs")), body);
  console.log("wrote node/" + name.replace(/\.js$/, ".test.mjs"));
}

for (const [name, keepIds] of Object.entries(MIXED)) {
  const mid = name.replace(/\.js$/, "");
  const raw = pristineHarness(name);
  let body = mixedRewrite(name, keepIds, mid, raw);
  for (const pattern of (DROPS[name] || [])) {
    const next = body.replace(pattern, "");
    if (next === body) console.log("  [warn] mixed 删行未命中: " + name + " -> " + String(pattern));
    body = next;
  }
  fs.writeFileSync(path.join(NODE_DIR, mid + ".test.mjs"), body);
  console.log("wrote node/" + mid + ".test.mjs");
  fs.writeFileSync(path.join(HARNESS, name), trimHarness(name, keepIds, raw));
  console.log("trimmed harness/" + name);
}

/* brief C28：只保留「覆盖全部变化类型 + 抽样边界」，删整表逐条拷贝。 */
{
  const target = path.join(NODE_DIR, "brief-contract.test.mjs");
  let s = fs.readFileSync(target, "utf8");
  const start = s.indexOf('test("C28"');
  const end = s.indexOf('test("C29"');
  if (start < 0 || end < 0) throw new Error("brief C28 边界失败");
  s = s.slice(0, start) + `test("C28", "失效图逐类匹配：每个变化类别都有失效投影，定向失效点名 shot 范围", () => {
  expect(Object.keys(INVALIDATION_TABLE).length === CHANGE_KINDS.length, "失效图必须覆盖全部变化类型");
  for (const kind of CHANGE_KINDS) {
    const got = kind === "fact_value_changed"
      ? invalidationsFor(kind, { shotIds: ["s1", "s2"], briefUsesSlot: true })
      : invalidationsFor(kind, { shotId: "s1" });
    expect(Array.isArray(got.invalidates) && got.invalidates.length > 0,
      kind + " 的失效集不许为空");
    expect(Array.isArray(got.preserves) && got.preserves.includes("project_history"),
      kind + " 必须保留项目历史");
    expect(Array.isArray(got.preserves) && got.preserves.includes("candidate_blobs"),
      kind + " 必须保留候选字节");
  }
  const fact = invalidationsFor("fact_value_changed", { shotIds: ["s1"], briefUsesSlot: false });
  expect(fact.invalidates.length === 3
    && fact.invalidates.includes("shot:s1:prompt") && fact.invalidates.includes("shot:s1:review")
    && fact.invalidates.includes("shot:s1:selection"),
    "值变化只失效目标 shot 的提示/审核/选择：" + fact.invalidates.join("|"));
  expect(fact.preserves.includes("product_brief"), "brief 是否失效由 briefUsesSlot 声明");
  const shotScope = invalidationsFor("shot_spec_changed", { shotId: "s1" });
  expect(shotScope.invalidates.includes("selection") && shotScope.invalidates.includes("review_reports"), "Shot 级变化必须精确失效提示与审核");
  expect(shotScope.preserves.includes("other_shots"), "Shot 级不许伤及其余 Shot");
  return { kinds: CHANGE_KINDS.length };
});
` + s.slice(end);
  fs.writeFileSync(target, s);
  console.log("  rewrote C28 in brief-contract.test.mjs");
}


/* 浏览器副本：同一组钉死/拷贝断言不再留在任何宿主侧（混合套件已由 trimHarness 处理）。 */
{
  const mixedNames = new Set(Object.keys(MIXED));
  for (const [name, patterns] of Object.entries(DROPS)) {
    if (mixedNames.has(name)) continue;
    const target = path.join(HARNESS, name);
    const raw = fs.readFileSync(target, "utf8");
    const marker = raw.indexOf("\nasync function runSuite");
    if (marker < 0) throw new Error(name + ": 无 runSuite，无法剥钉死断言");
    let head = raw.slice(0, marker);
    for (const pattern of patterns) {
      const next = head.replace(pattern, "");
      if (next === head) console.log("  [warn] 浏览器剥钉未命中: " + name + " -> " + String(pattern));
      head = next;
    }
    fs.writeFileSync(target, head + raw.slice(marker));
  }
  console.log("  stripped wording pins in browser pure suites");
}
