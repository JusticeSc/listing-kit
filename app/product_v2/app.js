/**
 * Product V2 项目首页（V2.1.2）：
 * 空白启动、本机项目列表、新建/打开/重命名/复制/删除。
 *
 * 页面只通过 storage repository 访问 IndexedDB；localStorage 里只有当前项目指针。
 * 这里不提供示例商品、不预填数据、不读服务器最近项目。
 */

import {
  CAPABILITY_GAPS,
  openStorage,
  exportProjectPackage,
  importProjectPackage,
  probeBrowserCapabilities,
} from "./storage/index.js";
import { createWorkspace } from "./workspace.js";

const STATE_LABELS = {
  EMPTY: "空白",
  INTAKE_READY: "资料已保存",
  UNDERSTANDING_REVIEW: "待确认理解",
  PLAN_REVIEW: "待确认套图",
  READY_TO_GENERATE: "可生成",
  GENERATING: "生成中",
  REVIEWING: "审核中",
  READY_TO_EXPORT: "可导出",
  EXPORTED: "已导出",
};

const ERROR_MESSAGES = {
  SCHEMA_TOO_NEW: "本机数据库版本高于当前页面代码，请用较新的页面打开，不要降级覆盖。",
  UNSUPPORTED_BROWSER: "当前浏览器不支持本地项目存储（IndexedDB），请改用现代桌面浏览器。",
  SECURE_CONTEXT_REQUIRED: "当前来源不是安全上下文（HTTP），浏览器禁用了 WebCrypto；请改用 HTTPS 正式入口。",
  CRYPTO_UNAVAILABLE: "当前浏览器缺少所需的 WebCrypto 能力，请升级到当前稳定版桌面 Chrome 或 Edge。",
  INDEXEDDB_UNAVAILABLE: "当前浏览器没有可用的 IndexedDB，请改用当前稳定版桌面 Chrome 或 Edge。",
  DATABASE_OPEN_FAILED: "本机项目数据库打不开，请检查浏览器存储设置后重试。",
  TRANSACTION_UNAVAILABLE: "本机项目数据库无法完成读写事务，请检查浏览器存储设置后重试。",
  QUOTA_EXCEEDED: "本机存储空间不足。请先复制或备份项目，再清理浏览器数据。",
  PACKAGE_INVALID: "这个文件不是有效的项目包（可能已损坏或被改动过），没有导入任何数据。",
  PACKAGE_UNSUPPORTED_VERSION: "项目包版本高于当前页面支持的版本，请用较新版本打开。",
  PACKAGE_HASH_MISMATCH: "项目包内容与清单不一致（哈希校验失败），没有导入任何数据。",
  PACKAGE_TOO_LARGE: "项目包过大，超出当前浏览器处理上限。",
};

const elements = {
  bootError: document.getElementById("boot-error"),
  capabilityNotice: document.getElementById("capability-notice"),
  homeError: document.getElementById("home-error"),
  homeView: document.getElementById("home-view"),
  projectView: document.getElementById("project-view"),
  createForm: document.getElementById("create-form"),
  nameInput: document.getElementById("new-project-name"),
  createSubmit: document.getElementById("create-project"),
  importTrigger: document.getElementById("import-trigger"),
  importFile: document.getElementById("import-file"),
  projectList: document.getElementById("project-list"),
  emptyState: document.getElementById("empty-state"),
  homeStatus: document.getElementById("home-status"),
  rowTemplate: document.getElementById("project-row-template"),
  backHome: document.getElementById("back-home"),
  projectTitle: document.getElementById("project-title"),
  projectState: document.getElementById("project-state"),
  projectCreated: document.getElementById("project-created"),
  projectUpdated: document.getElementById("project-updated"),
};

let repository = null;
let database = null;
let workspace = null;
let projects = [];
let currentProjectId = null;
let rowMode = { mode: "idle", projectId: null };

function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (value) => String(value).padStart(2, "0");
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate())
    + " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
}

function stateLabel(state) {
  return STATE_LABELS[state] || state;
}

function describeError(error) {
  if (error && error.code && ERROR_MESSAGES[error.code]) return ERROR_MESSAGES[error.code];
  if (error && error.message) return error.message;
  return "操作没有完成，请重试。";
}

function showError(element, message) {
  element.textContent = message;
  element.hidden = false;
}

function clearError(element) {
  element.textContent = "";
  element.hidden = true;
}

function showStatus(message) {
  elements.homeStatus.textContent = message;
  elements.homeStatus.hidden = false;
}

function clearStatus() {
  elements.homeStatus.textContent = "";
  elements.homeStatus.hidden = true;
}

/**
 * 能力缺口 → 界面投影（V2.UI.1）。
 * 每条都点名真实缺口与可执行动作；不得把 WebCrypto 缺失写成 IndexedDB 不支持。
 * 正常可用时不渲染任何工程诊断。
 */
const CAPABILITY_DIAGNOSES = Object.freeze({
  [CAPABILITY_GAPS.SECURE_CONTEXT]: {
    code: "SECURE_CONTEXT_REQUIRED",
    title: "当前来源不是安全上下文（HTTP）",
    detail: "浏览器在非安全来源禁用 WebCrypto：crypto.randomUUID 与 crypto.subtle 不可用，"
      + "因此无法新建项目、导入项目包或计算内容哈希。IndexedDB 本身可用，这不是 IndexedDB 缺失。",
    action: "请改用部署者提供的 HTTPS 正式入口；本机开发可用 http://127.0.0.1 或 http://localhost。",
  },
  [CAPABILITY_GAPS.INDEXEDDB]: {
    code: "INDEXEDDB_UNAVAILABLE",
    title: "当前浏览器没有 IndexedDB",
    detail: "项目保存在浏览器本地的 IndexedDB 里，这个浏览器没有暴露该能力。",
    action: "请改用当前稳定版桌面 Chrome 或 Edge 打开。",
  },
  [CAPABILITY_GAPS.DATABASE_OPEN]: {
    code: "DATABASE_OPEN_FAILED",
    title: "本机项目数据库打不开",
    detail: "浏览器拒绝打开或升级本机项目数据库；常见原因是本站存储被禁用、无痕模式限制或数据损坏。",
    action: "允许本站使用存储后点“重新检测”；仍然失败就换一个浏览器配置文件再试。",
  },
  [CAPABILITY_GAPS.RANDOM_UUID]: {
    code: "CRYPTO_UNAVAILABLE",
    title: "当前浏览器缺少 crypto.randomUUID",
    detail: "生成项目与记录 ID 需要 WebCrypto 随机 UUID，这个浏览器没有提供。",
    action: "请升级到当前稳定版桌面 Chrome 或 Edge。",
  },
  [CAPABILITY_GAPS.WEBCRYPTO]: {
    code: "CRYPTO_UNAVAILABLE",
    title: "当前浏览器缺少 crypto.subtle",
    detail: "计算内容哈希（SHA-256）需要 WebCrypto，这个浏览器没有提供。",
    action: "请升级到当前稳定版桌面 Chrome 或 Edge。",
  },
  [CAPABILITY_GAPS.TRANSACTION]: {
    code: "TRANSACTION_UNAVAILABLE",
    title: "本机项目数据库无法完成读写事务",
    detail: "数据库能打开，但一次最小读写事务没有成功；存储可能被浏览器限制或处于只读状态。",
    action: "检查浏览器存储设置后点“重新检测”。",
  },
});

function renderCapabilityDiagnosis(capabilities) {
  const notice = elements.capabilityNotice;
  const gap = capabilities.gaps.length > 0 ? capabilities.gaps[0] : null;
  if (!gap) {
    clearCapabilityDiagnosis();
    return;
  }
  const diagnosis = CAPABILITY_DIAGNOSES[gap];
  notice.hidden = false;
  notice.dataset.errorCode = diagnosis.code;
  notice.dataset.errorGap = gap;
  notice.querySelector('[data-role="diag-title"]').textContent = diagnosis.title;
  notice.querySelector('[data-role="diag-detail"]').textContent = diagnosis.detail;
  notice.querySelector('[data-role="diag-origin"]').textContent = capabilities.origin || "（未知）";
  notice.querySelector('[data-role="diag-action"]').textContent = diagnosis.action;
}

function clearCapabilityDiagnosis() {
  const notice = elements.capabilityNotice;
  notice.hidden = true;
  delete notice.dataset.errorCode;
  delete notice.dataset.errorGap;
  for (const role of ["diag-title", "diag-detail", "diag-origin", "diag-action"]) {
    notice.querySelector('[data-role="' + role + '"]').textContent = "";
  }
}

function setHomeControlsBlocked(blocked) {
  elements.createSubmit.disabled = blocked;
  elements.nameInput.disabled = blocked;
  elements.importTrigger.disabled = blocked;
}

function packageFileName(project, manifest) {
  const safe = project.name.replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "project";
  const stamp = (manifest.exported_at || new Date().toISOString())
    .replace(/[-:]/g, "").replace("T", "-").slice(0, 13);
  return safe + "-" + stamp + ".zip";
}

function showHome() {
  if (workspace) workspace.close();
  if (repository) void refresh();
  elements.homeView.hidden = false;
  elements.projectView.hidden = true;
}

/** UI.3：全局保存状态。工作台所有写入都走同一个 repository，这里单点投影到 #save-state。 */
function instrumentSaveState(repo) {
  const node = document.getElementById("save-state");
  const mark = (text) => { if (node) node.textContent = text; };
  const stamp = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const wrap = (holder, key) => {
    if (!holder || typeof holder[key] !== "function") return;
    const original = holder[key].bind(holder);
    holder[key] = async (...args) => {
      try {
        const result = await original(...args);
        const version = result && typeof result.version === "number"
          ? " · 版本 " + result.version
          : "";
        mark("已保存" + version + " · " + stamp());
        return result;
      } catch (error) {
        mark("保存失败：" + ((error && error.message) || "未知错误")
          + "（没有丢失输入，可重试）");
        throw error;
      }
    };
  };
  wrap(repo.documents, "save");
  wrap(repo.assets, "put");
}

function resetSaveState() {
  const node = document.getElementById("save-state");
  if (node) node.textContent = "";
}

function showProject(project) {
  elements.homeView.hidden = true;
  elements.projectView.hidden = false;
  elements.projectTitle.textContent = project.name;
  elements.projectState.textContent = stateLabel(project.state);
  elements.projectCreated.textContent = formatTime(project.created_at);
  elements.projectUpdated.textContent = formatTime(project.updated_at);
}

function buildRow(project) {
  const row = elements.rowTemplate.content.firstElementChild.cloneNode(true);
  row.dataset.projectId = project.project_id;
  row.classList.toggle("is-current", project.project_id === currentProjectId);
  row.querySelector('[data-role="state"]').textContent = stateLabel(project.state);
  row.querySelector('[data-role="updated"]').textContent = "更新于 " + formatTime(project.updated_at);

  const main = row.querySelector(".row-main");
  const actions = row.querySelector('[data-role="actions"]');
  const nameNode = row.querySelector('[data-role="name"]');

  if (rowMode.mode === "rename" && rowMode.projectId === project.project_id) {
    const input = document.createElement("input");
    input.className = "rename-input";
    input.value = project.name;
    input.maxLength = 120;
    input.setAttribute("aria-label", "新名称");
    main.replaceChild(input, nameNode);
    actions.replaceChildren();
    const save = document.createElement("button");
    save.type = "button";
    save.dataset.action = "rename-save";
    save.textContent = "保存";
    save.className = "primary";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.dataset.action = "cancel";
    cancel.textContent = "取消";
    actions.append(save, cancel);
    queueMicrotask(() => input.focus());
  } else if (rowMode.mode === "delete" && rowMode.projectId === project.project_id) {
    nameNode.textContent = project.name;
    actions.replaceChildren();
    const prompt = document.createElement("span");
    prompt.className = "meta";
    prompt.textContent = "确认删除这个项目？";
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.dataset.action = "delete-confirm";
    confirm.className = "danger";
    confirm.textContent = "确认删除";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.dataset.action = "cancel";
    cancel.textContent = "取消";
    actions.append(prompt, confirm, cancel);
  } else {
    nameNode.textContent = project.name;
  }
  return row;
}

function renderList() {
  elements.projectList.replaceChildren();
  for (const project of projects) {
    elements.projectList.append(buildRow(project));
  }
  const isEmpty = projects.length === 0;
  elements.emptyState.hidden = !isEmpty;
}

async function refresh() {
  projects = await repository.projects.list();
  renderList();
}

async function handleCreate(name) {
  clearError(elements.homeError);
  if (!repository) {
    showError(elements.homeError, "本地数据库还在初始化，请稍候再操作。");
    return null;
  }
  try {
    const project = await repository.projects.create({ name });
    elements.nameInput.value = "";
    await refresh();
    rowMode = { mode: "idle", projectId: null };
    return project;
  } catch (error) {
    showError(elements.homeError, describeError(error));
    return null;
  }
}

async function handleOpen(projectId) {
  clearError(elements.homeError);
  try {
    await repository.pointer.set(projectId);
    currentProjectId = projectId;
    const project = await repository.projects.get(projectId);
    showProject(project);
    resetSaveState();
    renderList();
    if (workspace) await workspace.open(project);
  } catch (error) {
    showError(elements.homeError, describeError(error));
  }
}

async function handleRename(projectId, name) {
  clearError(elements.homeError);
  try {
    const project = await repository.projects.get(projectId);
    const updated = await repository.projects.rename(projectId, name, {
      expectedRevision: project.revision,
    });
    rowMode = { mode: "idle", projectId: null };
    await refresh();
    if (currentProjectId === projectId) {
      showProject(updated);
      if (workspace) workspace.setProject(updated);
    }
  } catch (error) {
    rowMode = { mode: "idle", projectId: null };
    await refresh();
    showError(elements.homeError, describeError(error));
  }
}

async function handleDuplicate(projectId) {
  clearError(elements.homeError);
  try {
    await repository.projects.duplicate(projectId);
    rowMode = { mode: "idle", projectId: null };
    await refresh();
  } catch (error) {
    showError(elements.homeError, describeError(error));
  }
}

async function handleDelete(projectId) {
  clearError(elements.homeError);
  try {
    await repository.projects.remove(projectId);
    if (currentProjectId === projectId) {
      currentProjectId = null;
      showHome();
    }
    rowMode = { mode: "idle", projectId: null };
    await refresh();
  } catch (error) {
    showError(elements.homeError, describeError(error));
  }
}

async function handleExport(projectId) {
  clearError(elements.homeError);
  clearStatus();
  try {
    const project = await repository.projects.get(projectId);
    const { bytes, manifest } = await exportProjectPackage(repository, projectId);
    const blob = new Blob([bytes], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = packageFileName(project, manifest);
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    showStatus("已导出项目包：" + anchor.download + "（含完整历史，可在别的浏览器导入）");
  } catch (error) {
    showError(elements.homeError, describeError(error));
  }
}

async function handleImport(file) {
  clearError(elements.homeError);
  clearStatus();
  if (!file) return;
  if (!database || !repository) {
    elements.importFile.value = "";
    showError(elements.homeError, "本地数据库还在初始化，请稍候再导入。");
    return;
  }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const result = await importProjectPackage(database, bytes);
    rowMode = { mode: "idle", projectId: null };
    await refresh();
    showStatus(
      (result.id_assigned
        ? "已导入「" + result.project.name + "」（同 id 项目已存在，已作为新项目导入）"
        : "已导入「" + result.project.name + "」")
      + (Array.isArray(result.migrations_applied) && result.migrations_applied.length
        ? " · 已升级：" + result.migrations_applied.join("；")
        : ""),
    );
  } catch (error) {
    showError(elements.homeError, describeError(error));
  } finally {
    elements.importFile.value = "";
  }
}

elements.createForm.addEventListener("submit", (event) => {
  event.preventDefault();
  handleCreate(elements.nameInput.value);
});

elements.importTrigger.addEventListener("click", () => {
  elements.importFile.click();
});

elements.importFile.addEventListener("change", (event) => {
  const file = event.target.files && event.target.files[0];
  handleImport(file);
});

elements.projectList.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const row = button.closest(".project-row");
  if (!row) return;
  const projectId = row.dataset.projectId;
  const action = button.dataset.action;
  if (action === "open") handleOpen(projectId);
  else if (action === "rename") { rowMode = { mode: "rename", projectId }; renderList(); }
  else if (action === "rename-save") {
    const input = row.querySelector(".rename-input");
    handleRename(projectId, input ? input.value : "");
  } else if (action === "duplicate") handleDuplicate(projectId);
  else if (action === "export") handleExport(projectId);
  else if (action === "delete") { rowMode = { mode: "delete", projectId }; renderList(); }
  else if (action === "delete-confirm") handleDelete(projectId);
  else if (action === "cancel") { rowMode = { mode: "idle", projectId: null }; renderList(); }
});

elements.backHome.addEventListener("click", () => {
  showHome();
});

elements.capabilityNotice.querySelector('[data-role="diag-retry"]').addEventListener("click", () => {
  void boot();
});

async function boot() {
  setHomeControlsBlocked(true);
  if (workspace) {
    workspace.close();
    workspace = null;
  }
  if (database) {
    try {
      database.close();
    } catch (error) {
      // 旧连接已经不可用；重新打开即可。
    }
    database = null;
  }
  repository = null;
  clearError(elements.homeError);
  clearError(elements.bootError);

  const capabilities = await probeBrowserCapabilities();
  renderCapabilityDiagnosis(capabilities);
  const blocked = capabilities.gaps.length > 0;
  setHomeControlsBlocked(blocked);

  try {
    const opened = await openStorage();
    repository = opened.repository;
    instrumentSaveState(repository);
    database = opened.db;
    workspace = createWorkspace({
      repository,
      onProjectChanged(project) {
        if (project && currentProjectId === project.project_id) showProject(project);
        if (currentProjectId) void refresh();
      },
    });
    const current = await repository.pointer.get();
    currentProjectId = current ? current.project_id : null;
    await refresh();
    if (blocked) {
      showHome();
      return;
    }
    if (current) {
      showProject(current);
      resetSaveState();
      await workspace.open(current);
    } else {
      showHome();
    }
  } catch (error) {
    setHomeControlsBlocked(false);
    showError(elements.bootError, describeError(error));
  }
}

boot();
