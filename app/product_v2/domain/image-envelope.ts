/**
 * 归一化图像信封的唯一浏览器入口（P6 / SEL-025）。
 *
 * 结构权威是 `src/providers/v2_image.py` 的 `ImageWire*` Pydantic 模型：构建期由
 * `tools/export_image_envelope_schema.py` 导出 JSON Schema，再由
 * `tools/generate_image_envelope_validator.mjs` 用 Ajv 生成 standalone ESM 校验器。
 * 两个产物都在 `domain/generated/`（生成物，不手改）。本模块只做两件事：
 *
 *   1) 把生成校验器收口成一个类型守卫——浏览器里不存在第二份形状/词表校验；
 *   2) 固定「结构不合契约」的诊断口径：调用方一律用固定文案，绝不回显载荷字段。
 *
 * 明确不属于本模块：状态词到 Attempt 状态的映射、sync 与 task_id 的耦合、Unknown 与
 * 不重提策略、冻结执行身份与核对判据（仍在 `domain/attempt.ts`）；Blob/OCC 校验在存储层。
 */
import { validateImageEnvelope as validateGenerated } from "./generated/image-task-envelope.validate.js";
import type { ImageEnvelopeWire } from "./type-contracts.js";

/** 结构守卫：true 表示这就是网关的归一化信封（成功支或失败支），字段值可按 wire 类型读。 */
export function validateImageEnvelope(value: unknown): value is ImageEnvelopeWire {
  return validateGenerated(value) === true;
}
