// Product V2 渐进 TypeScript 迁移的最小 ESM 编译/新鲜度闸门（计划 §9 V2.R7.5）。
//
// 唯一权威是 `app/product_v2/domain/*.ts`；同目录同名 `.js` 是**生成的浏览器产物**
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

const sources = parsed.fileNames.filter((file) =>
  file.endsWith(".ts") && !file.endsWith(".d.ts"));
if (!sources.length) {
  throw new Error("jsconfig.json 没有登记任何已迁移的 TS Module（.ts，排除 .d.ts）。");
}

let stale = false;
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
  if (check) {
    let current;
    try {
      current = await readFile(output, "utf8");
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    if (current !== content) {
      console.error("Stale generated ESM: " + path.relative(root, output)
        + "; run npm run build:frontend.");
      stale = true;
    }
  } else {
    await writeFile(output, content, "utf8");
  }
  console.log((check ? "CHECK " : "EMIT ") + relative);
}
if (stale) process.exit(1);
