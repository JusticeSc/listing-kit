// P4 唯一标准构建配置（SEL-023，用户 2026-10-17 已确认）：Vite 8.3.4 dev-only，
// 产出唯一生产静态目录 dist/product-v2（正式 Python 静态入口只服务它，缺产物明确失败，
// 无源码回退、无 Node 运行时、无 CDN、无运行时编译器）。
//
// root 即产品源码目录 app/product_v2：index.html 是浏览器唯一入口；手工/生成混合源在
// 迁移完成前以实际文件为准（删除生成 .js 后由 .ts 直接进入模块图）。
// publicDir 常规 Vite public/：发布自检 marker（release-marker.txt）由发布事务写入
// app/product_v2/public/，随构建原样拷贝进 dist，不落任何手写产物清单。
//
// rollupOptions.output.preserveModules：探针/正式验证消费者在真实页面上按稳定绝对路径
// 动态 import（/domain/index.js、/storage/index.js、/storage/db.js、/generation.js 等，
// 见 tools/verify_v2_*.py 的 page.evaluate）；preserveModules 让 dist 保留与源码一致的
// 相对路径（.ts→.js），动态 import 继续命中正式构建产物而非源码——不新增任何
// 测试专属生产 shim。模块身份（单一实例、共享 chunk 语义）由标准打包器保证。
//
// manifest: true 写 dist/product-v2/.vite/manifest.json：发布指纹/资源枚举消费该清单
// 加全部 dist 字节（父侧 release probe 已迁动态枚举），不再钉首页与两条固定脚本。
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// 合同浏览器入口（evals/product-v2/harness/*.js 与 tools/verify_*.py 的 page.evaluate）
// 按稳定绝对路径 /domain/index.js、/storage/index.js、/storage/db.js、/storage/zip.js
// import 具名成员；Rollup 的逐 chunk export 裁剪只保留产品图需要的绑定，会把这些
// barrel 的对外面撕掉（2026-10-17 实证 `/storage/index.js` 丢 STORAGE_SCHEMA_VERSION
// 直接让 harness 套件在模块解析层全红）。把它们登记为 rollup 入口：
// 入口模块的对外签名不再被树摇（preserveEntrySignatures 'strict' 语义），
// dist 里这四个路径继续保留完整 export 表面，契约消费面不再是“碰巧没被摇掉”。
const contractEntries = {};
for (const name of ["domain/index", "storage/index", "storage/schema", "storage/db", "storage/zip"]) {
  contractEntries[name] = fileURLToPath(
    new URL("./app/product_v2/" + name + ".js", import.meta.url));
}
for (const name of ["generation", "domain/attempt"]) {
  contractEntries[name] = fileURLToPath(
    new URL("./app/product_v2/" + name + ".ts", import.meta.url));
}
contractEntries.main = fileURLToPath(new URL("./app/product_v2/index.html", import.meta.url));

export default defineConfig({
  root: "app/product_v2",
  base: "./",
  publicDir: "public",
  build: {
    outDir: "../../dist/product-v2",
    emptyOutDir: true,
    manifest: true,
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      input: contractEntries,
      preserveEntrySignatures: "strict",
      output: {
        preserveModules: true,
        entryFileNames: "[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "[name][extname]",
      },
    },
    assetsDir: "",
  },
});
