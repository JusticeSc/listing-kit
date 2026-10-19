/**
 * 冻结参考图合同（V2.3.4 引入；schema 3 Attempt 消费同一判据，计划 §13.8）。
 *
 * 唯一权威：参考图用途词表、单图参考上限与冻结引用机检都在本文件。
 * 独立成模块是为了让 attempt 校验复用同一判据而不与 prompt.js 形成循环依赖
 * （prompt.js 依赖本模块并原样再导出，既有导入路径不变）。
 * 本层是纯函数：不调用模型、不写存储、不发请求。
 */

import { DOMAIN_ERROR_CODES } from "./errors.js";
import {
  canonicalJson,
  isNonEmptyString,
  isPlainObject,
  isPositiveInteger,
  isSha256Hex,
  pushProblem,
} from "./shared.js";

export const REFERENCE_USES = Object.freeze(["edit_source", "product_truth", "style_reference"]);

export const MAX_REFERENCE_SELECTION = 3;

export function checkFrozenReferences(references, options = {}) {
  const problems = [];
  if (!Array.isArray(references)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references", "冻结参考图必须是列表。");
    return problems;
  }
  const limit = options.maxReferences === undefined ? MAX_REFERENCE_SELECTION : options.maxReferences;
  if (!isPositiveInteger(limit) || references.length < 1 || references.length > limit) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
      "实际参考图必须是 1.." + limit + " 张；编辑源占一张，请明确减选本图依据，不会自动裁图。");
  }
  const seen = new Set();
  references.forEach((item, index) => {
    const path = "$.references[" + index + "]";
    if (!isPlainObject(item) || !isNonEmptyString(item.role) || !isSha256Hex(item.sha256)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "冻结引用缺少角色或完整资产哈希。");
      return;
    }
    if (Object.keys(item).some(key => !["role", "sha256", "uses", "sources"].includes(key))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "冻结引用含有不支持的字段。");
    }
    if (seen.has(item.sha256)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "同一资产必须合并用途，不能重复外发。");
    }
    seen.add(item.sha256);
    const uses = Array.isArray(item.uses) ? item.uses : [];
    if (!uses.length || new Set(uses).size !== uses.length
        || uses.some(use => !REFERENCE_USES.includes(use))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".uses", "引用用途缺失、重复或不认识。");
    }
    const sources = Array.isArray(item.sources) ? item.sources : [];
    if (!sources.length || new Set(sources.map(source => canonicalJson(source))).size !== sources.length) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".sources", "引用必须有明确且不重复的原文档来源。");
    }
    for (const source of sources) {
      if (!isPlainObject(source) || !["candidate", "product_input"].includes(source.kind)
          || !isNonEmptyString(source.document_id) || !isPositiveInteger(source.version)
          || source.asset_sha256 !== item.sha256
          || Object.keys(source).some(key => !["kind", "document_id", "version", "asset_sha256"].includes(key))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".sources",
          "引用来源的文档、版本和资产必须与实际字节一致，且不能含有额外字段。");
      }
    }
    const candidate = sources.some(source => isPlainObject(source) && source.kind === "candidate");
    const product = sources.some(source => isPlainObject(source) && source.kind === "product_input");
    if (candidate !== uses.includes("edit_source")
        || (uses.includes("product_truth") || uses.includes("style_reference")) && !product) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "引用用途与原文档来源不相符。");
    }
  });
  return problems;
}
