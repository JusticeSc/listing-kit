import { createMockService, mockContract } from "./mock-service.js";

/**
 * UI 只认识这份服务合同。Phase 3 把 adapter 换成本地 API 时，页面动作和返回状态不变。
 */
export function createWorkbenchService({ mode = "mock", latency = 90, scenario = "normal" } = {}) {
  if (mode !== "mock") {
    throw new Error(`当前切片只提供 mock adapter，收到 mode=${mode}`);
  }
  const adapter = createMockService({ latency, scenario });
  for (const method of mockContract.requiredMethods) {
    if (typeof adapter[method] !== "function") {
      throw new Error(`service contract 缺少方法：${method}`);
    }
  }
  return adapter;
}

export { mockContract };
