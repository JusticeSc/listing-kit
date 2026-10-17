// 静态外壳默认禁用业务控件；只有 app 的完整启动能解锁。
// 保持这一边界独立于工作区依赖，依赖加载失败时仍能显示并明确重试。
import("./app.js").catch(error => {
  // app 未加载：静态三节点都在 boot-mount（index.html），消息来自 entry 外壳文案。
  const pending = document.getElementById("boot-pending");
  const message = document.getElementById("boot-error");
  const retryRow = document.getElementById("boot-retry-row");
  // #boot-retry 在静态期只有原生重载；模板接管后由 lit 重新渲染自身的重试按钮。
  const retry = document.getElementById("boot-retry");
  if (pending) pending.hidden = true;
  if (message) {
    message.textContent = `应用模块未能加载，请重新加载重试。${error instanceof Error ? error.message : "未知加载错误"}`;
    message.hidden = false;
  }
  if (retryRow) retryRow.hidden = false;
  retry?.addEventListener("click", () => window.location.reload(), { once: true });
});
