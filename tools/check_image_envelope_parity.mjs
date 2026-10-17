/**
 * P6/SEL-025：把一组真实/变异信封交给**生成的**归一化校验器，逐条回报接受或拒绝。
 *
 * 这是跨语言等价矩阵的 JS 一半：Python 侧（tools/verify_image_envelope_contract.py）用同一批
 * 案例调用真实 Pydantic 权威模型，两侧逐条比对，任何一条判定不同即失败。本文件不复制任何形状
 * 知识，只读生成产物。
 *
 * 用法：
 *   node tools/check_image_envelope_parity.mjs --cases <cases.json> [--out <result.json>]
 *
 * cases.json: {"cases": [{"name": "...", "value": <任意 JSON>}]}
 * 输出：{"results": [{"name": "...", "ok": true|false}]}（ok = 生成校验器接受）
 */
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const VALIDATOR = "app/product_v2/domain/generated/image-task-envelope.validate.js";

function parseArgs(argv) {
  const args = { cases: null, out: null };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--cases") args.cases = argv[++index];
    else if (argv[index] === "--out") args.out = argv[++index];
    else throw new Error("未知参数：" + argv[index]);
  }
  if (!args.cases) throw new Error("必须显式给出 --cases <cases.json>（本工具不内置任何案例形状）");
  return args;
}

const args = parseArgs(process.argv.slice(2));
const casesPath = path.resolve(ROOT, args.cases);

let mod;
try {
  mod = await import(new URL("../" + VALIDATOR, import.meta.url).href);
} catch (error) {
  throw new Error("[envelope-parity] 读不到生成的校验器 " + VALIDATOR
    + "：先跑 `npm run build:envelope`（本工具不做任何回退校验）。");
}
const validate = mod.validateImageEnvelope;
if (typeof validate !== "function") {
  throw new Error("[envelope-parity] 生成产物没有导出 validateImageEnvelope，拒绝拿别的函数顶替。");
}

const document = JSON.parse(await readFile(casesPath, "utf8"));
const cases = Array.isArray(document.cases) ? document.cases : null;
if (cases === null) throw new Error("[envelope-parity] cases.json 缺少 cases 数组。");

const results = cases.map((item) => ({
  name: String(item.name),
  /* 生成校验器只回 true/false；把 errors 丢掉是刻意的：诊断文本一律由调用方固定生成。 */
  ok: validate(item.value) === true,
}));

const payload = JSON.stringify({ results }, null, 2);
if (args.out) {
  await writeFile(path.resolve(ROOT, args.out), payload + "\n", "utf8");
} else {
  process.stdout.write(payload + "\n");
}
