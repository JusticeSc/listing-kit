/**
 * Product V2 项目首页（V2.1.2）：
 * 空白启动、本机项目列表、新建/打开/重命名/复制/删除。
 *
 * 页面只通过 storage repository 访问 IndexedDB；localStorage 里只有当前项目指针。
 * 这里不提供示例商品、不预填数据、不读服务器最近项目。
 */

import { openStorage, exportProjectPackage, importProjectPackage } from "./storage/index.js";

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
  QUOTA_EXCEEDED: "本机存储空间不足。请先复制或备份项目，再清理浏览器数据。",
  PACKAGE_INVALID: "这个文件不是有效的项目包（可能已损坏或被改动过），没有导入任何数据。",
  PACKAGE_UNSUPPORTED_VERSION: "项目包版本高于当前页面支持的版本，请用较新版本打开。",
  PACKAGE_HASH_MISMATCH: "项目包内容与清单不一致（哈希校验失败），没有导入任何数据。",
  PACKAGE_TOO_LARGE: "项目包过大，超出当前浏览器处理上限。",
};

const elements = {
  bootError: document.getElementById("boot-error"),
  homeError: document.getElementById("home-error"),
  homeView: document.getElementById("home-view"),
  projectView: document.getElementById("project-view"),
  createForm: document.getElementById("create-form"),
  nameInput: document.getElementById("new-project-name"),
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

function packageFileName(project, manifest) {
  const safe = project.name.replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "project";
  const stamp = (manifest.exported_at || new Date().toISOString())
    .replace(/[-:]/g, "").replace("T", "-").slice(0, 13);
  return safe + "-" + stamp + ".zip";
}

function showHome() {
  elements.homeView.hidden = false;
  elements.projectView.hidden = true;
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
    renderList();
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
    if (currentProjectId === projectId) showProject(updated);
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
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const result = await importProjectPackage(database, bytes);
    rowMode = { mode: "idle", projectId: null };
    await refresh();
    showStatus(
      result.id_assigned
        ? "已导入「" + result.project.name + "」（同 id 项目已存在，已作为新项目导入）"
        : "已导入「" + result.project.name + "」",
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

async function boot() {
  try {
    const opened = await openStorage();
    repository = opened.repository;
    database = opened.db;
    const current = await repository.pointer.get();
    currentProjectId = current ? current.project_id : null;
    await refresh();
    if (current) showProject(current);
    else showHome();
  } catch (error) {
    showError(elements.bootError, describeError(error));
  }
}

boot();
