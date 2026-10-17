/**
 * P6/SEL-025：把导出的唯一信封 JSON Schema 编译成浏览器可消费的 standalone ESM 校验器。
 *
 * 只用 Ajv 8.20.0 的构建期 codegen：
 *   - 无 $data、无 formats、无远程 schema 拉取、无浏览器运行时 Ajv、无动态 eval/Function；
 *   - 生成物必须自包含：Ajv 在某些关键字下会插入 `require("ajv/dist/runtime/...")`，
 *     那在浏览器 ESM 里是运行期炸弹。生成后当场自检这条不变量，不做“应该没问题”假设；
 *   - `--schema` 必须显式给出且必须存在：缺文件即报错退出，不合成、不回退到内置形状。
 *
 * 用法：
 *   node tools/generate_image_envelope_validator.mjs --schema <schema.json> --out <out.js>
 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv from "ajv";
import standaloneCode from "ajv/dist/standalone/index.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SCHEMA = "app/product_v2/domain/generated/image-task-envelope.schema.json";
const DEFAULT_OUT = "app/product_v2/domain/generated/image-task-envelope.validate.js";
/* 生成模块的导出名：与 domain/image-envelope.ts 的导入名一一对应，改名必须同时改两边。 */
const EXPORT_NAME = "validateImageEnvelope";
const BANNER = [
  "// 生成物，不要手改：来自 tools/export_image_envelope_schema.py 导出的 JSON Schema，",
  "// 由 tools/generate_image_envelope_validator.mjs 用 Ajv standalone codegen 编译。",
  "// 结构权威是 src/providers/v2_image.py 的 ImageWire* 模型；改形状请改模型并重跑 codegen。",
  "",
].join("\n");

function parseArgs(argv) {
  const args = { schema: null, out: null };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--schema") args.schema = argv[++index];
    else if (flag === "--out") args.out = argv[++index];
    else throw new Error("未知参数：" + flag);
  }
  if (!args.schema) args.schema = DEFAULT_SCHEMA;
  if (!args.out) args.out = DEFAULT_OUT;
  return args;
}

const args = parseArgs(process.argv.slice(2));
const schemaPath = path.resolve(ROOT, args.schema);
const outPath = path.resolve(ROOT, args.out);

let raw;
try {
  raw = await readFile(schemaPath, "utf8");
} catch (error) {
  throw new Error("[envelope-codegen] 读不到信封 schema：" + args.schema
    + "（先跑 tools/export_image_envelope_schema.py，本步骤不做任何回退合成）");
}
const schema = JSON.parse(raw);
if (!schema || typeof schema !== "object" || typeof schema.$id !== "string") {
  throw new Error("[envelope-codegen] schema 缺少 $id，无法生成具名校验器。");
}

const ajv = new Ajv({
  schemas: [schema],
  code: { source: true, esm: true },
  strict: true,
  allErrors: false,
  /* 结构契约里没有 $data；显式关掉而不是依赖默认值，避免以后被当成能力打开。 */
  $data: false,
});
const moduleCode = standaloneCode(ajv, { [EXPORT_NAME]: schema.$id });

/* 自包含不变量：出现 CommonJS/动态 require 就说明 schema 用到了需要 runtime helper 的关键字
 * （minLength/maxLength/format/uniqueItems 等），浏览器 ESM 消费不了。宁可构建期炸掉。 */
const runtimeRequire = moduleCode.match(/(^|[^.\w])require\s*\(/);
if (runtimeRequire) {
  throw new Error("[envelope-codegen] 生成物含 require(...)，浏览器 ESM 不能消费；"
    + "检查 schema 是否引入了 minLength/maxLength/format/uniqueItems 等需要运行期 helper 的关键字。");
}
if (!moduleCode.includes(`export const ${EXPORT_NAME}`)) {
  throw new Error("[envelope-codegen] 生成物没有导出 " + EXPORT_NAME + "，拒绝写出。");
}

await mkdir(path.dirname(outPath), { recursive: true });
await writeFile(outPath, BANNER + moduleCode + "\n", "utf8");
console.log(`[envelope-codegen] ${path.relative(ROOT, outPath).split(path.sep).join("/")} · `
  + `export=${EXPORT_NAME} · bytes=${Buffer.byteLength(moduleCode)}`);
