import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const manifest = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const compiler = JSON.parse(await readFile(new URL("../node_modules/typescript/package.json", import.meta.url), "utf8"));
const npmVersion = process.env.npm_config_user_agent?.match(/^npm\/([\d.]+)(?:\s|$)/)?.[1];
assert.ok(npmVersion, "请通过 npm run check:versions 运行，以核对真正执行脚本的 npm");
assert.equal(process.versions.node, manifest.engines.node, "Node 与 manifest 精确版本不符");
assert.equal(npmVersion, manifest.engines.npm, "npm 与 manifest 精确版本不符");
assert.equal(manifest.packageManager, `npm@${npmVersion}`, "packageManager 与实际 npm 不符");
assert.equal(compiler.version, manifest.devDependencies.typescript, "本地检查器与锁定版本不符");
console.log(`[PASS] FRONTEND-VERSIONS Node ${process.versions.node} / npm ${npmVersion} / TypeScript ${compiler.version}`);
