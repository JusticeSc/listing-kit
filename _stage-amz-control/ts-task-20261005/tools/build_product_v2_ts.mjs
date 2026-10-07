import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// TS is authoritative; checked-in JS is a generated browser artifact.
// --check verifies the same artifacts in CI without mutating the checkout.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
if (args.some(arg => arg !== "--check")) throw new Error("Usage: node tools/build_product_v2_ts.mjs [--check]");
const check = args.includes("--check");
const configPath = path.join(root, "jsconfig.json");
const loaded = ts.readConfigFile(configPath, ts.sys.readFile);
if (loaded.error) throw new Error(ts.flattenDiagnosticMessageText(loaded.error.messageText, "\n"));
const parsed = ts.parseJsonConfigFileContent(loaded.config, ts.sys, root);
const program = ts.createProgram(parsed.fileNames, parsed.options);
const diagnostics = [...parsed.errors, ...ts.getPreEmitDiagnostics(program)];
if (diagnostics.length) {
  console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: file => file,
    getCurrentDirectory: () => root,
    getNewLine: () => "\n",
  }));
  process.exit(1);
}
const sources = parsed.fileNames.filter(file => file.endsWith(".ts") && !file.endsWith(".d.ts"));
if (!sources.length) throw new Error("No migrated TS Module is registered in jsconfig.json.");
let stale = false;
for (const file of sources) {
  const source = await readFile(file, "utf8");
  const result = ts.transpileModule(source, {
    fileName: file,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      verbatimModuleSyntax: true,
      newLine: ts.NewLineKind.LineFeed,
    },
    reportDiagnostics: true,
  });
  if (result.diagnostics?.length) throw new Error(ts.formatDiagnostics(result.diagnostics, {
    getCanonicalFileName: file => file,
    getCurrentDirectory: () => root,
    getNewLine: () => "\n",
  }));
  const output = file.slice(0, -3) + ".js";
  const relative = path.relative(root, file).replaceAll(path.sep, "/");
  const content = "// Generated from " + relative + "; edit the TS source and run npm run build:frontend.\n" + result.outputText;
  if (check) {
    let current;
    try { current = await readFile(output, "utf8"); }
    catch (error) { if (error.code !== "ENOENT") throw error; }
    if (current !== content) {
      console.error("Stale generated ESM: " + path.relative(root, output) + "; run npm run build:frontend.");
      stale = true;
    }
  } else {
    await writeFile(output, content, "utf8");
  }
  console.log((check ? "CHECK " : "EMIT ") + relative);
}
if (stale) process.exit(1);
