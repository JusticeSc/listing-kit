/**
 * #9 对照脚本：用真实项目的普通输入，对比
 *  (1) 原程序编译稿（项目里已保存的 prompt_version.compiled.text，逐字）
 *  (2) 新编译路径在「用户做完普通选择」后的编译稿
 * 不调用模型、不写存储，只读 + 纯函数编译；写出 evals/product-v2/refactor/program-expression-20261018.json。
 *
 * 前置：本副本先 `npm run build:frontend-node`；真实项目包解包（Windows 自带 tar 可解 zip）：
 *   tar -xf _stage-amz-control/asset-continuation-20261008T054352Z/data/manual-project.zip \
 *       -C _stage-amz-control/issue9-expression-20261018T080410Z/real-project
 * 运行：node _stage-amz-control/issue9-expression-20261018T080410Z/program-expression-before-after.mjs
 *       [documents 目录] [shotId]   （默认 real-project/documents + 全部图）
 */
import fs from "node:fs";
import path from "node:path";

const REPO = path.resolve(import.meta.dirname, "../..");
const REAL = process.argv[2] && !fs.existsSync(process.argv[2])
  ? path.join(REPO, "_stage-amz-control/issue9-expression-20261018T080410Z/real-project/documents")
  : path.resolve(process.argv[2] || path.join(REPO, "_stage-amz-control/issue9-expression-20261018T080410Z/real-project/documents"));
const load = (name) => JSON.parse(fs.readFileSync(path.join(REAL, name), "utf8"));
const NEW = path.join(REPO, "build/frontend-node/app/product_v2/domain/index.js");
const domain = await import("file:///" + NEW.replace(/\\/g, "/"));

const intake = load("0037.json").payload;
const plan = load("0053.json").payload;
const slotFiles = ["0006", "0007", "0008", "0009", "0010", "0011", "0012", "0013", "0014", "0015", "0016", "0017", "0018"];
const latest = new Map();
for (const file of slotFiles) {
  const doc = load(file + ".json");
  const prev = latest.get(doc.document_id);
  if (!prev || prev.version < doc.version) latest.set(doc.document_id, doc);
}
const slotEntries = [...latest.values()].map((doc) => ({ slot: doc.payload, version: doc.version }));
const brief = domain.buildProductBrief(slotEntries);
const assets = (intake.references || []).map((ref) => ({ role: ref.role, sha256: ref.asset_sha256 }));
const context = { assets: assets, facts: latest.size ? [...latest.values()].map((d) => d.payload) : [] };
/** 与项目记录同型号的有效图像档（数值取当前测试夹具，项目记录里的 fake 档不是产品档）。 */
const provider = {
  provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0", version: 3, protocol: "v2.4.1",
  size: "1344*1344", n: 1, prompt_extend: false, watermark: false, output_format: "png",
  supports_negative_prompt_field: false, max_reference_images: 3, reference_media_types: ["image/png", "image/jpeg"],
  min_side: 384, max_side: 2048, min_area: 512 * 512, max_area: 2048 * 2048,
  min_ratio: 1 / 8, max_ratio: 8, max_prompt_chars: 4000,
};
const target = process.argv[3] || "all";
const styleSpec = {
  schema_version: 1, background: "", lighting: "", color_tone: "", composition: "", avoid: [],
  // 普通选择：玻璃储物罐 → 干净展示、内容物为空（用户明确选择，不是程序默认）
  presentation: { appearance_state: "clean_display", contents_state: "empty" },
};
const shotSpecs = {
  shot_main_clean: { layout: "product_only" },
  shot_infographic_benefits: {
    // 用户在页面上勾选「必须保持的商品特征」：列表按元素各印一条（与界面规则一致）。
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: ["HONEY 浮雕", "蜂窝纹理", "透明罐身"].map((text, index) => ({
      text_id: "t_signature_features_" + (index + 1), text: text,
      source_slot_id: "signature_features", source_slot_version: 2,
      status: "confirmed", origin: "user",
    })),
  },
  shot_scene_lifestyle: { layout: "product_only" },
  shot_detail_material: { layout: "product_only" },
};
const oldFiles = { shot_infographic_benefits: "0039.json", shot_main_clean: "0040.json", shot_scene_lifestyle: "0042.json", shot_detail_material: "0038.json" };

const records = [];
for (const shot of plan.shots) {
  if (target !== "all" && shot.shot_id !== target) continue;
  const spec = domain.emptyShotSpecFromShot(shot);
  const over = shotSpecs[shot.shot_id] || {};
  for (const [key, value] of Object.entries(over)) if (value !== undefined) spec[key] = value;
  const compiled = domain.compilePrompt({
    brief, shot, styleSpec, shotSpec: spec, context, providerProfile: provider,
    versions: { suite_version: 1, style_version: 1, shot_spec_version: 1 },
  });
  const oldDocument = oldFiles[shot.shot_id] ? load(oldFiles[shot.shot_id]) : null;
  const oldDoc = oldDocument ? oldDocument.payload : null;
  records.push({
    shot_id: shot.shot_id, role_id: shot.role_id, label: shot.label,
    old_record: oldDoc ? { document_version: oldDocument.version, text: oldDoc.compiled.text, sections: oldDoc.compiled.sections.map((item) => item.key), warnings: oldDoc.compiled.warnings.map((item) => item.code) } : null,
    new_choices: { shot_spec: spec, style_presentation: styleSpec.presentation },
    new_text: compiled.text,
    new_sections: compiled.sections.map((item) => item.key),
    new_warnings: compiled.warnings.map((item) => item.code),
  });
  console.log("\n=============== " + shot.shot_id + " (" + shot.role_id + ")");
  if (oldDoc) console.log("--- 原程序编译稿（项目内记录 v" + oldDocument.version + "，逐字）\n" + oldDoc.compiled.text);
  console.log("--- 新编译稿（含用户普通选择）\n" + compiled.text);
  console.log("--- 新段落顺序:", compiled.sections.map((item) => item.key).join(", "));
  console.log("--- 新警告:", JSON.stringify(compiled.warnings.map((item) => item.code)));
}
if (target === "all") {
  const out = {
    schema_version: 1,
    source_project_zip: "_stage-amz-control/asset-continuation-20261008T054352Z/data/manual-project.zip",
    source_documents: { intake: "0037.json", suite_plan: "0053.json", prompt_versions: oldFiles },
    ordinary_input: intake,
    confirmed_facts: brief.confirmed_facts,
    provider_profile_note: "项目记录里的 fake-qwen-image 档不是产品档；本次用同型号的有效档（数值取测试夹具）",
    shots: records,
  };
  fs.writeFileSync(path.join(REPO, "evals/product-v2/refactor/program-expression-20261018.json"),
    JSON.stringify(out, null, 2) + "\n");
  console.log("\nwritten evals/product-v2/refactor/program-expression-20261018.json");
}
