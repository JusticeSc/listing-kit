// Product V2 渐进 TypeScript 迁移的最小 ESM 编译/新鲜度闸门（计划 §9 V2.R7.5，设计 §10.7）。
//
// 批准范围是 `app/product_v2/**/*.ts` 内全部实际 TS 源码（排除 `.d.ts`、node_modules/vendor）；
// 同目录同名 `.js` 是**生成的浏览器产物**
// （浏览器直接消费该 `.js`，import 说明符保持 `.js`）。不引入打包器、TS 运行时加载器或
// 第二份依赖锁；只在已锁定的根开发依赖 typescript 上做「类型检查 + 单文件转译」。
//
// 用法：
//   node tools/build_product_v2_ts.mjs           # 类型检查并写出每个 TS 的 .js
//   node tools/build_product_v2_ts.mjs --check   # 只校验产物与 TS 源一致（CI 用，不写文件）
//
// 配置、类型检查范围与产物路径都取自 jsconfig.json；检查命令通过不代表未纳入的文件有类型保障。
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
if (args.some((arg) => arg !== "--check")) {
  throw new Error("Usage: node tools/build_product_v2_ts.mjs [--check]");
}
const check = args.includes("--check");
const headerNote = "run `npm run build:frontend`";
const configPath = path.join(root, "jsconfig.json");

const loaded = ts.readConfigFile(configPath, ts.sys.readFile);
if (loaded.error) {
  throw new Error(ts.flattenDiagnosticMessageText(loaded.error.messageText, "\n"));
}
const parsed = ts.parseJsonConfigFileContent(loaded.config, ts.sys, root);
if (parsed.errors.length) {
  console.error(ts.formatDiagnostics(parsed.errors, {
    getCanonicalFileName: (file) => file,
    getCurrentDirectory: () => root,
    getNewLine: () => "\n",
  }));
  process.exit(1);
}
// 先做一次整个程序（含 // @ts-check 的 JS 与已迁 TS）的严格检查：转译本身不报类型错误。
// 01包规则：产物集合取自 compiler program 实际 TS（批准范围过滤+稳定排序），
// 不仅用 parsed.fileNames（会漏掉传递 import 的 prompts/authorization/selection-adoption/review-delivery）。
// 两阶段：内存收齐全部转译输出及诊断，全部通过后才写/比对；失败不半写半留。
const program = ts.createProgram(parsed.fileNames, parsed.options);
const diagnostics = [...parsed.errors, ...ts.getPreEmitDiagnostics(program)];
if (diagnostics.length) {
  console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: (file) => file,
    getCurrentDirectory: () => root,
    getNewLine: () => "\n",
  }));
  process.exit(1);
}
const programSources = program.getSourceFiles()
  .map((file) => file.fileName)
  .filter((file) => file.endsWith(".ts") && !file.endsWith(".d.ts"))
  .filter((file) => {
    const relative = path.relative(root, file).replaceAll(path.sep, "/");
    return relative.startsWith("app/product_v2/")
      && !relative.includes("/vendor/")
      && !relative.includes("node_modules");
  })
  .sort();
const sources = programSources;
if (!sources.length) {
  throw new Error("compiler program 内没有批准范围的 TS Module（app/product_v2/**/*.ts，排除 .d.ts/vendor）。");
}
/** @type {{file: string, relative: string, output: string, content: string}[]} */
const pending = [];
for (const file of sources) {
  const source = await readFile(file, "utf8");
  const result = ts.transpileModule(source, {
    fileName: file,
    reportDiagnostics: true,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      verbatimModuleSyntax: true,
      newLine: ts.NewLineKind.LineFeed,
    },
  });
  if (result.diagnostics?.length) {
    console.error(ts.formatDiagnostics(result.diagnostics, {
      getCanonicalFileName: (f) => f,
      getCurrentDirectory: () => root,
      getNewLine: () => "\n",
    }));
    process.exit(1);
  }
  const output = file.slice(0, -3) + ".js";
  const relative = path.relative(root, file).replaceAll(path.sep, "/");
  const content = "// Generated from " + relative + "; edit the TS source and "
    + headerNote + ".\n" + result.outputText;
  pending.push({ file, relative, output, content });
}
pending.sort((left, right) => left.relative.localeCompare(right.relative));
let stale = false;
for (const item of pending) {
  if (check) {
    let current;
    try {
      current = await readFile(item.output, "utf8");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    if (current !== item.content) {
      console.error("Stale generated ESM: " + path.relative(root, item.output)
        + "; run npm run build:frontend.");
      stale = true;
    }
  } else {
    await writeFile(item.output, item.content, "utf8");
  }
  console.log((check ? "CHECK " : "EMIT ") + item.relative);
}
if (stale) process.exit(1);
