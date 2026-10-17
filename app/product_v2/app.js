// @ts-check
/**
 * Product V2 项目首页（V2.1.2）：
 * 空白启动、本机项目列表、新建/打开/重命名/复制/删除。
 *
 * 页面只通过 storage repository 访问 IndexedDB；localStorage 里只有当前项目指针。
 * 这里不提供示例商品、不预填数据、不读服务器最近项目。
 * 首页动态子树（项目行/能力诊断）由 lit-html 模板渲染；静态容器、命令与就绪语义不变。
 */

import {
  CAPABILITY_GAPS,
  exportProjectPackage,
  importProjectPackage,
  probeBrowserCapabilities,
} from "./storage/index.js";
import { createSession } from "./session.js";
import { createWorkspace } from "./workspace.js";
import { createModelSettings } from "./model-settings.js";
import { html, nothing, render } from "lit-html";
import { repeat } from "lit-html/directives/repeat.js";

/**
 * 首页行内模式：idle 常态 / rename 改名中 / delete 删除确认中；projectId 指向目标行（无目标为 null）。
 * @typedef {{mode: "idle" | "rename" | "delete", projectId: string | null}} RowMode
 */
/**
 * 能力缺口码：直接取自探针词表本身（storage/errors.js 的 CapabilityGap 未导出，不跨文件硬依赖）。
 * @typedef {typeof CAPABILITY_GAPS[keyof typeof CAPABILITY_GAPS]} CapabilityGapCode
 */
/**
 * 能力探针里本页真正消费的最小形状（缺口列表 + 来源）。
 * @typedef {{gaps: CapabilityGapCode[], origin: string}} CapabilityProbeView
 */
/**
 * 导出清单里本页真正消费的最小形状（文件名时间戳）。
 * @typedef {{exported_at?: string}} ExportManifest
 */
/**
 * 首页必需节点的静态前置条件：index.html 里这些 ID 是固定标签，缺失即页面结构损坏。
 * 与 model-settings.ts 同模式：加载时按标签断言一次并抛错，不在每次访问处零散判空。
 * @template {HTMLElement} T
 * @param {string} id 元素 id
 * @param {new () => T} ctor 期望的 DOM 构造器
 * @returns {T}
 */
function requiredElement(id, ctor) {
  const node = document.getElementById(id);
  if (!(node instanceof ctor)) throw new Error("缺少必需的界面节点：" + id);
  return node;
}
/**
 * 未知错误的 message（缺失或非字符串时返回 null，兜底文案由调用方决定）。
 * @param {unknown} error 捕获的未知错误
 * @returns {string | null}
 */
function errorMessage(error) {
  if (error && typeof error === "object" && "message" in error
      && typeof error.message === "string" && error.message) {
    return error.message;
  }
  return null;
}
/**
 * 首页 DOM 句柄集合：只保留模板挂载锚点与真实命令/输入控件；
 * 错误/状态/空库/重试行全部是 homeNotices/bootMount 模板的内投影，不再散列句柄。
 * 必需节点由 requiredElement 在模块加载时断言（缺失即抛错），故这里不再可空。
 * @typedef {object} HomeElements
 * @property {HTMLElement} bootMount 启动区挂载点
 * @property {HTMLElement} capabilityNotice 能力缺口诊断区
 * @property {HTMLElement} homeNotices 首页通知区挂载点
 * @property {HTMLElement} homeView 首页区
 * @property {HTMLElement} projectView 工作台区
 * @property {HTMLFormElement} createForm 新建表单
 * @property {HTMLInputElement} nameInput 新项目名称输入
 * @property {HTMLButtonElement} createSubmit 新建提交按钮
 * @property {HTMLButtonElement} importTrigger 导入触发按钮
 * @property {HTMLInputElement} importFile 导入文件选择
 * @property {HTMLUListElement} projectList 项目列表
 * @property {HTMLButtonElement} backHome 返回列表按钮
 * @property {HTMLHeadingElement} projectTitle 项目标题
 * @property {HTMLSpanElement} projectState 项目状态徽标
 * @property {HTMLElement} projectCreated 创建时间
 * @property {HTMLElement} projectUpdated 更新时间
 */
const modelSettings = createModelSettings();

/** @type {Record<string, string>} 项目状态 → 中文标签（未知状态透传原文，不在这里收窄） */
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

/** @type {Record<string, string>} 存储错误码 → 用户文案（仅覆盖已知码，未知走 message/兜底） */
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

/** @type {HomeElements} 首页静态锚点（容器本身不动；内容由模板 render 进去） */
const elements = {
  // 每个 ID 在 index.html 里是固定标签；requiredElement 在模块加载时断言存在并按标签收窄。
  bootMount: requiredElement("boot-mount", HTMLElement),
  capabilityNotice: requiredElement("capability-notice", HTMLElement),
  homeNotices: requiredElement("home-notices", HTMLElement),
  homeView: requiredElement("home-view", HTMLElement),
  projectView: requiredElement("project-view", HTMLElement),
  createForm: requiredElement("create-form", HTMLFormElement),
  nameInput: requiredElement("new-project-name", HTMLInputElement),
  createSubmit: requiredElement("create-project", HTMLButtonElement),
  importTrigger: requiredElement("import-trigger", HTMLButtonElement),
  importFile: requiredElement("import-file", HTMLInputElement),
  projectList: requiredElement("project-list", HTMLUListElement),
  backHome: requiredElement("back-home", HTMLButtonElement),
  projectTitle: requiredElement("project-title", HTMLHeadingElement),
  projectState: requiredElement("project-state", HTMLSpanElement),
  projectCreated: requiredElement("project-created", HTMLElement),
  projectUpdated: requiredElement("project-updated", HTMLElement),
};

/** @type {import("./session.js").Session | null} 会话句柄（boot 前 null；boot 成功后就绪，失败保持 null 并投影 bootError） */
let session = null;
/** @type {import("./storage/validate.js").ProjectRepository | null} 就绪仓库（boot 成功后赋值；各使用点已判空） */
let repository = null;
/** @type {import("./storage/validate.js").StoredProjectRecord[]} 当前列表帧（已验证记录；整帧替换，不原地改） */
let projects = [];
/** @type {string | null} 当前打开项目 ID（未打开为 null；权威在 IndexedDB 指针，内存仅镜像） */
let currentProjectId = null;
/** @type {RowMode} 行内模式（进入/取消走 enter/cancel 收尾走 reset） */
let rowMode = { mode: "idle", projectId: null };
/** @type {Map<string, string>} 改名草稿（project_id → 输入值；refresh 重渲染不丢用户已输入） */
const renameDrafts = new Map();
/** @type {number} 列表读取代次（过期响应丢弃，只渲染最新代） */
let projectListGeneration = 0;
/** @type {Promise<void> | null} 完整应用启动只允许一轮在途；Session 只拥有存储/工作区启动。 */
let bootPromise = null;

/**
 * ISO 时间 → 本地 "YYYY-MM-DD HH:mm"；非法输入原样返回（不抛错，由调用方展示原文）。
 * @param {string} iso ISO 时间字符串
 * @returns {string} 本地时间或原文
 */
function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
/** @type {(value: number) => string} 两位补零（调用方只传 getFullYear/getMonth 等数字） */
  const pad = (value) => String(value).padStart(2, "0");
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate())
    + " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
}

/**
 * @param {string} state 项目状态（词表外透传原文）
 * @returns {string} 中文标签，未知状态返回原文
 */
function stateLabel(state) {
  return STATE_LABELS[state] || state;
}

/**
 * 未知错误 → 用户可读文案：先按稳定 code 查词表，再取 message；都不满足用固定兜底。
 * @param {unknown} error 捕获的未知错误（StorageError / Error / 其他）
 * @returns {string} 界面文案（字面量与 ERROR_MESSAGES/兜底一致，不新增文案）
 */
function describeError(error) {
  if (error && typeof error === "object") {
    if ("code" in error && typeof error.code === "string" && ERROR_MESSAGES[error.code]) {
      return ERROR_MESSAGES[error.code];
    }
    const message = errorMessage(error);
    if (message) return message;
  }
  return "操作没有完成，请重试。";
}

/**
 * 首页通知投影状态：空串 = 不投影该行（模板渲染 nothing + hidden），非空 = 投影文案。
 * reading=true 时投影“正在读取…”；readError 非空时投影错误+重试行。
 * @typedef {object} HomeNotices
 * @property {string} homeError 首页错误
 * @property {string} homeStatus 首页状态
 * @property {string} readError 列表读取错误
 * @property {boolean} reading 列表读取中
 * @property {string} bootError 启动错误
 * @property {boolean} bootPending 启动中横幅
 * @property {boolean} bootRetry 可重试启动
 * @property {CapabilityGapCode | null} diagGap 能力缺口（首个）
 * @property {string} diagOrigin 探针来源
 */
/** @type {HomeNotices} */
const notices = { homeError: "", homeStatus: "", readError: "", reading: false, bootError: "", bootPending: true, bootRetry: false, diagGap: null, diagOrigin: "" };

/** @type {string} 全局保存状态文案（空串 = 不投影；工作区写入包装的唯一投影源） */
let saveState = "";

/**
 * 启动区模板：错误/重试/横幅由 notices 驱动；验证器读 #boot-error/#boot-retry-row/#boot-pending。
 * @returns {unknown}
 */
function bootTemplate() {
  return html`
    <p id="boot-error" class="error" role="alert" ?hidden=${!notices.bootError}>${notices.bootError}</p>
    <p id="boot-retry-row" ?hidden=${!notices.bootRetry}><button id="boot-retry" type="button" @click=${() => { void boot(); }}>重试启动</button></p>
    <p id="boot-pending" class="meta" role="status" ?hidden=${!notices.bootPending}>正在启动本地项目库…</p>`;
}

/**
 * 首页通知区模板：错误/状态/读取中/读取错误+重试/空库全部由 notices+projects 驱动；
 * 验证器读 #home-error/#home-status/#home-read-status/#home-read-error/#home-read-retry-row/#home-read-retry/#empty-state。
 * @returns {unknown}
 */
function homeNoticesTemplate() {
  const empty = projects.length === 0 && !notices.reading;
  return html`
    <p id="home-error" class="error" role="alert" ?hidden=${!notices.homeError}>${notices.homeError}</p>
    <p id="home-status" class="status" role="status" ?hidden=${!notices.homeStatus}>${notices.homeStatus}</p>
    <p id="home-read-status" class="meta" role="status" ?hidden=${!notices.reading}>正在读取本机项目…</p>
    <p id="home-read-error" class="error" role="alert" ?hidden=${!notices.readError}>${notices.readError}</p>
    <p id="home-read-retry-row" ?hidden=${!notices.readError}><button id="home-read-retry" type="button" @click=${() => { void refresh(); }}>重试读取项目</button></p>
    <p id="empty-state" class="empty" ?hidden=${!empty}>这台浏览器还没有项目。填写名称后点“新建项目”开始。</p>`;
}

/** @returns {void} 启动区重渲染 */
function renderBoot() {
  render(bootTemplate(), elements.bootMount);
}

/** @returns {void} 首页通知区重渲染 */
function renderNotices() {
  render(homeNoticesTemplate(), elements.homeNotices);
}

/** @returns {void} 保存状态重渲染（空串不投影） */
function renderSaveState() {
  const node = document.getElementById("save-state");
  if (node) render(saveState ? html`${saveState}` : nothing, node);
}

/**
 * 能力缺口 → 界面投影（V2.UI.1）。
 * 每条都点名真实缺口与可执行动作；不得把 WebCrypto 缺失写成 IndexedDB 不支持。
 * 正常可用时不渲染任何工程诊断。
 */
/** @type {Record<CapabilityGapCode, {code: string, title: string, detail: string, action: string}>} 能力缺口 → 诊断文案（六缺口全覆盖，与探针词表一一对应） */
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

/**
 * 首个缺口 → 界面投影；无缺口时清空诊断（正常可用不渲染工程信息）。
 * 模板拥有 #capability-notice 的子树（含重试按钮 @click）；容器本身仍是静态节点。
 * @param {CapabilityProbeView} capabilities 探针结果（本页只消费 gaps/origin）
 * @returns {void}
 */
function renderCapabilityDiagnosis(capabilities) {
  setNotice({
    diagGap: capabilities.gaps.length > 0 ? capabilities.gaps[0] : null,
    diagOrigin: capabilities.origin || "",
  });
}

/**
 * 能力诊断模板：首个缺口 + 来源；无缺口渲染 nothing 且容器 hidden。
 * 模板拥有 #capability-notice 的子树（含重试按钮 @click）；容器本身仍是静态节点。
 * @returns {unknown}
 */
function diagnosisTemplate() {
  const gap = notices.diagGap;
  if (!gap) return nothing;
  const diagnosis = CAPABILITY_DIAGNOSES[gap];
  return html`
    <p class="diag-title" data-role="diag-title">${diagnosis.title}</p>
    <p class="diag-detail" data-role="diag-detail">${diagnosis.detail}</p>
    <p class="diag-meta">当前来源：<code data-role="diag-origin">${notices.diagOrigin || "（未知）"}</code></p>
    <p class="diag-action" data-role="diag-action">${diagnosis.action}</p>
    <button type="button" data-role="diag-retry" @click=${() => { void boot(); }}>重新检测</button>
  `;
}

/** @returns {void} 能力诊断重渲染（显隐与 dataset 由模板状态派生） */
function renderDiagnosis() {
  const notice = elements.capabilityNotice;
  const gap = notices.diagGap;
  render(diagnosisTemplate(), notice);
  notice.hidden = !gap;
  if (gap) {
    notice.dataset.errorCode = CAPABILITY_DIAGNOSES[gap].code;
    notice.dataset.errorGap = gap;
  } else {
    delete notice.dataset.errorCode;
    delete notice.dataset.errorGap;
  }
}

/**
 * @returns {void}
 */
function clearCapabilityDiagnosis() {
  setNotice({ diagGap: null, diagOrigin: "" });
}

/**
 * 首页控件禁用/解锁：解锁即“完整恢复完成”（验证器以 data-ready 判早解锁窗口）。
 * @param {boolean} blocked true 禁用并清除 ready，false 解锁并置 ready=1
 * @returns {void}
 */
function setHomeControlsBlocked(blocked) {
  elements.createSubmit.disabled = blocked;
  elements.nameInput.disabled = blocked;
  elements.importTrigger.disabled = blocked;
  // R3.3：解锁即"完整恢复完成"；验证器用 data-ready 判断是否存在早解锁窗口。
  elements.createSubmit.dataset.ready = blocked ? "" : "1";
}

/**
 * @param {import("./storage/validate.js").StoredProjectRecord} project 已验证的项目记录（name 参与文件名清洗）
 * @param {ExportManifest} manifest 导出清单的最小形状（exported_at 缺省用当前时间）
 * @returns {string} 安全文件名（60 字符截断，无路径分隔符）
 */
function packageFileName(project, manifest) {
  const safe = project.name.replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "project";
  const stamp = (manifest.exported_at || new Date().toISOString())
    .replace(/[-:]/g, "").replace("T", "-").slice(0, 13);
  return safe + "-" + stamp + ".zip";
}

/**
 * 回首页视图（会话关闭/打开由 session 统一管理，这里只投影视图显隐）。
 * @returns {void}
 */
function showHome() {
  // 会话动作（关闭/打开）由 session 统一管理；这里只投影视图与首页列表。
  elements.homeView.hidden = false;
  elements.projectView.hidden = true;
}

/** UI.3：全局保存状态。工作台所有写入都走同一个 repository，这里单点投影到 #save-state。 */
/**
 * @param {import("./storage/validate.js").ProjectRepository} repo 已就绪仓库（documents.save / assets.put 被包装以投影保存状态，不改写入语义）
 * @returns {void}
 */
function instrumentSaveState(repo) {
/** @type {(text: string) => void} 保存状态投影（状态+模板渲染；节点缺失时跳过，不抛错） */
  const mark = (text) => { saveState = text; renderSaveState(); };
/** @type {() => string} */
  const stamp = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });
/**
 * 方法包装：非函数跳过；成功标版本+时间，失败标错并原样上抛（不吞错，不改写入语义）。
 * holder 是 repo.documents / repo.assets（成员全是方法），按 Record<string, unknown> 读取后收窄。
 * @param {Record<string, unknown>} holder 方法持有者
 * @param {string} key 方法名（"save" / "put"）
 * @returns {void}
 */
  const wrap = (holder, key) => {
    const method = holder[key];
    if (typeof method !== "function") return;
    const original = method.bind(holder);
    holder[key] = async (/** @type {unknown[]} */ ...args) => {
      try {
        const result = await original(...args);
        const version = result && typeof result.version === "number"
          ? " · 版本 " + result.version
          : "";
        mark("已保存" + version + " · " + stamp());
        return result;
      } catch (error) {
        mark("保存失败：" + (errorMessage(error) || "未知错误")
          + "（没有丢失输入，可重试）");
        throw error;
      }
    };
  };
  wrap(repo.documents, "save");
  wrap(repo.assets, "put");
}

/**
 * @returns {void}
 */
function resetSaveState() {
  saveState = "";
  renderSaveState();
}

/**
 * @param {import("./storage/validate.js").StoredProjectRecord} project 已验证的项目记录（恢复/打开后的完整记录）
 * @returns {void}
 */
function showProject(project) {
  renderProjectHeader(project);
  elements.homeView.hidden = true;
  elements.projectView.hidden = false;
  // R3.3：视图可见 = 工作区已完整装载；验证器以此区分"仅切视图"与"可交互"。
  elements.projectView.dataset.ready = "1";
}

/**
 * 工作台头模板投影：标题/状态/时间由记录驱动渲染；视图显隐仍是生命周期切换。
 * @param {import("./storage/validate.js").StoredProjectRecord} project 已验证的项目记录
 * @returns {void}
 */
function renderProjectHeader(project) {
  render(html`${project.name}`, elements.projectTitle);
  render(html`${stateLabel(project.state)}`, elements.projectState);
  render(html`${formatTime(project.created_at)}`, elements.projectCreated);
  render(html`${formatTime(project.updated_at)}`, elements.projectUpdated);
}

/**
 * 退出行内模式并丢弃改名草稿（新建/复制/删除/导入/改名收尾用；取消走 cancelRowMode 以回焦）。
 * @returns {void}
 */
function resetRowMode() {
  rowMode = { mode: "idle", projectId: null };
  renameDrafts.clear();
}

/**
 * 项目行模板：模板拥有 #project-list 子树，行身份按 project_id keyed；
 * async 刷新只更新文本/行集合，不换行、不丢改名草稿、不抢焦点。
 * @param {import("./storage/validate.js").StoredProjectRecord} project 已验证的项目记录（列表项投影，不改记录）
 * @returns {unknown} 行模板（改名/删除模式就地替换名称与动作区）
 */
function projectRow(project) {
  const projectId = project.project_id;
  const renaming = rowMode.mode === "rename" && rowMode.projectId === projectId;
  const deleting = rowMode.mode === "delete" && rowMode.projectId === projectId;
  return html`
    <li class="project-row${projectId === currentProjectId ? " is-current" : ""}" data-project-id=${projectId}>
      <div class="row-main">
        <span class="badge" data-role="state">${stateLabel(project.state)}</span>
        ${renaming
          ? html`<input class="rename-input" aria-label="新名称" maxlength="120" data-project-id=${projectId}
              .value=${renameDrafts.get(projectId) ?? project.name}
              @input=${(/** @type {Event} */ event) => {
                if (event.target instanceof HTMLInputElement) renameDrafts.set(projectId, event.target.value);
              }}>`
          : html`<span class="name" data-role="name">${project.name}</span>`}
        <span class="meta" data-role="updated">更新于 ${formatTime(project.updated_at)}</span>
      </div>
      <div class="row-actions" data-role="actions">
        ${renaming
          ? html`
            <button type="button" data-action="rename-save" class="primary"
              @click=${() => {
                void handleRename(projectId, renameDrafts.get(projectId) ?? project.name);
              }}>保存</button>
            <button type="button" data-action="cancel"
              @click=${() => cancelRowMode(projectId, "rename")}>取消</button>`
          : deleting
            ? html`
              <span class="meta">确认删除这个项目？</span>
              <button type="button" data-action="delete-confirm" class="danger"
                @click=${() => { void handleDelete(projectId); }}>确认删除</button>
              <button type="button" data-action="cancel"
                @click=${() => cancelRowMode(projectId, "delete")}>取消</button>`
            : html`
              <button type="button" data-action="open" class="primary"
                @click=${() => { void handleOpen(projectId); }}>打开</button>
              <button type="button" data-action="rename"
                @click=${() => enterRename(project)}>重命名</button>
              <button type="button" data-action="duplicate"
                @click=${() => { void handleDuplicate(projectId); }}>复制</button>
              <button type="button" data-action="export"
                @click=${() => { void handleExport(projectId); }}>导出项目包</button>
              <button type="button" data-action="delete" class="danger"
                @click=${() => enterDelete(projectId)}>删除</button>`}
      </div>
    </li>`;
}

/**
 * 进入改名模式：已有草稿保留（refresh 重渲染不丢），否则用当前名播种；渲染后聚焦输入框。
 * @param {import("./storage/validate.js").StoredProjectRecord} project 已验证的项目记录
 * @returns {void}
 */
function enterRename(project) {
  if (!renameDrafts.has(project.project_id)) renameDrafts.set(project.project_id, project.name);
  rowMode = { mode: "rename", projectId: project.project_id };
  renderList();
  focusRowControl(project.project_id, ".rename-input");
}

/**
 * 进入删除确认模式；渲染后不抢焦点（确认/取消都在行内 Tab 序）。
 * @param {string} projectId 项目 ID
 * @returns {void}
 */
function enterDelete(projectId) {
  rowMode = { mode: "delete", projectId };
  renderList();
}

/**
 * 取消行内模式并把焦点还给触发按钮（改名/删除）；草稿丢弃。
 * @param {string} projectId 项目 ID
 * @param {"rename" | "delete"} trigger 触发模式
 * @returns {void}
 */
function cancelRowMode(projectId, trigger) {
  resetRowMode();
  renderList();
  focusRowControl(projectId, 'button[data-action="' + trigger + '"]');
}

/**
 * 行内控件聚焦（按 dataset 找行，不拼 ID 选择器）。
 * @param {string} projectId 项目 ID
 * @param {string} selector 行内选择器
 * @returns {void}
 */
function focusRowControl(projectId, selector) {
  for (const row of elements.projectList.children) {
    if (!(row instanceof HTMLElement) || row.dataset.projectId !== projectId) continue;
    const control = row.querySelector(selector);
    if (control instanceof HTMLElement) control.focus();
    return;
  }
}

/**
 * @param {import("./storage/validate.js").StoredProjectRecord[]} [nextProjects] 下一帧列表（缺省沿用当前 projects，不做校验，来源已验证）
 * @returns {void}
 */
function renderList(nextProjects = projects) {
  projects = nextProjects;
  render(
    repeat(projects, (project) => project.project_id, (project) => projectRow(project)),
    elements.projectList,
  );
  renderNotices();
}

/**
 * @param {{required?: boolean}} [options] required=true 时读失败继续上抛（boot 用），否则仅投影错误+重试入口
 * @returns {Promise<void>}
 */
async function refresh({ required = false } = {}) {
  const generation = ++projectListGeneration;
  elements.projectList.setAttribute("aria-busy", "true");
  setNotice({ reading: true, readError: "" });
  try {
    const repo = repository;
    if (!repo) throw new Error("本地数据库还在初始化，请稍候再操作。");
    const nextProjects = await repo.projects.list();
    if (generation === projectListGeneration) renderList(nextProjects);
  } catch (error) {
    if (generation === projectListGeneration) {
      setNotice({ readError: describeError(error) });
    }
    if (required) throw error;
  } finally {
    if (generation === projectListGeneration) {
      elements.projectList.setAttribute("aria-busy", "false");
      setNotice({ reading: false });
    }
  }
}

/**
 * 合并更新通知状态并重渲染全部通知模板（启动区 + 首页区 + 能力诊断）。
 * @param {Partial<HomeNotices>} patch 状态增量
 * @returns {void}
 */
function setNotice(patch) {
  Object.assign(notices, patch);
  renderBoot();
  renderNotices();
  renderDiagnosis();
}

/**
 * @param {string} name 新项目名（空串由 repository 校验拒绝，不在这里预校验）
 * @returns {Promise<import("./storage/validate.js").StoredProjectRecord | null>} 新建记录，失败返回 null（错误已投影，不抛）
 */
async function handleCreate(name) {
  setNotice({ homeError: "" });
  if (!session || !session.repository) {
    setNotice({ homeError: "本地数据库还在初始化，请稍候再操作。" });
    return null;
  }
  try {
    const project = await session.repository.projects.create({ name });
    elements.nameInput.value = "";
    resetRowMode();
    // R3.3：新建即打开——与 handleOpen 走同一条"完整恢复完成后才切视图"的路径。
    const opened = await session.openProject(project);
    currentProjectId = opened.project_id;
    showProject(opened);
    resetSaveState();
    await refresh();
    return project;
  } catch (error) {
    setNotice({ homeError: describeError(error) });
    await refresh();
    return null;
  }
}

/**
 * 打开项目：与新建走同一条“完整恢复完成后才切视图”路径（看到工作台与可交互同一时刻）。
 * @param {string} projectId 项目 ID
 * @returns {Promise<void>}
 */
async function handleOpen(projectId) {
  setNotice({ homeError: "" });
  if (!session || !session.repository) {
    setNotice({ homeError: "本地数据库还在初始化，请稍候再操作。" });
    return;
  }
  try {
    const project = await session.repository.projects.get(projectId);
    if (!project) throw new Error("项目不存在或已被删除。");
    // openProject 依次：保存旧项目草稿 → 推进会话代 → 写指针 → 完整恢复工作区。
    // 恢复完成后才切视图，"看到工作台"与"可以交互"是同一时刻。
    const opened = await session.openProject(project);
    currentProjectId = opened.project_id;
    showProject(opened);
    resetSaveState();
    renderList();
  } catch (error) {
    setNotice({ homeError: describeError(error) });
  }
}

/**
 * 改名后同步当前项目身份：命中当前打开项时更新会话元数据（不推进代次、不重开工作区）。
 * @param {string} projectId 项目 ID
 * @param {string} name 新名称（空串/超长由 repository 校验拒绝）
 * @returns {Promise<void>}
 */
async function handleRename(projectId, name) {
  setNotice({ homeError: "" });
  const repo = repository;
  if (!repo) {
    setNotice({ homeError: "本地数据库还在初始化，请稍候再操作。" });
    return;
  }
  try {
    const project = await repo.projects.get(projectId);
    if (!project) throw new Error("项目不存在或已被删除。");
    const updated = await repo.projects.rename(projectId, name, {
      expectedRevision: project.revision,
    });
    resetRowMode();
    await refresh();
    if (currentProjectId === projectId) {
      showProject(updated);
      // 会话仍指向同一项目：只更新身份元数据，不推进代次、不重开工作区。
      const active = session;
      if (active) active.updateProjectMetadata(updated);
    }
  } catch (error) {
    // 失败保留改名模式与草稿：refresh 重渲染不丢用户输入，焦点回到输入框以便修正。
    renameDrafts.set(projectId, name);
    rowMode = { mode: "rename", projectId };
    await refresh();
    setNotice({ homeError: describeError(error) });
    focusRowControl(projectId, ".rename-input");
  }
}

/**
 * @param {string} projectId 项目 ID
 * @returns {Promise<void>} 复制后整帧刷新；失败投影错误，不抛
 */
async function handleDuplicate(projectId) {
  setNotice({ homeError: "" });
  const repo = repository;
  if (!repo) {
    setNotice({ homeError: "本地数据库还在初始化，请稍候再操作。" });
    return;
  }
  try {
    await repo.projects.duplicate(projectId);
    resetRowMode();
    await refresh();
  } catch (error) {
    setNotice({ homeError: describeError(error) });
  }
}

/**
 * 删除项目：命中当前打开项时关会话并回首页。
 * @param {string} projectId 项目 ID
 * @returns {Promise<void>}
 */
async function handleDelete(projectId) {
  setNotice({ homeError: "" });
  const repo = repository;
  if (!repo) {
    setNotice({ homeError: "本地数据库还在初始化，请稍候再操作。" });
    return;
  }
  try {
    await repo.projects.remove(projectId);
    if (currentProjectId === projectId) {
      currentProjectId = null;
      if (session) void session.closeProject();
      showHome();
    }
    resetRowMode();
    await refresh();
  } catch (error) {
    setNotice({ homeError: describeError(error) });
  }
}

/**
 * 导出项目包并触发浏览器下载（Blob URL，10 秒后释放）；失败投影错误，不写库。
 * @param {string} projectId 项目 ID
 * @returns {Promise<void>}
 */
async function handleExport(projectId) {
  setNotice({ homeError: "", homeStatus: "" });
  const repo = repository;
  if (!repo) {
    setNotice({ homeError: "本地数据库还在初始化，请稍候再操作。" });
    return;
  }
  try {
    const project = await repo.projects.get(projectId);
    if (!project) throw new Error("项目不存在或已被删除。");
    const { bytes, manifest } = await exportProjectPackage(repo, projectId);
    // zip 字节来自 buildZip 的独立 ArrayBuffer；TS 6 的 BlobPart 只接受 ArrayBufferView<ArrayBuffer>。
    const blob = new Blob([/** @type {BlobPart} */ (bytes)], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = packageFileName(project, manifest);
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    setNotice({ homeStatus: "已导出项目包：" + anchor.download + "（含完整历史，可在别的浏览器导入）" });
  } catch (error) {
    setNotice({ homeError: describeError(error) });
  }
}

/**
 * 导入项目包（先 staging 后单事务提交；同 id 已存在则分配新 id，不覆盖）。
 * 凭据仅标签页内存，不进 IndexedDB/Git/日志。
 * @param {File | null | undefined} file 用户选择的 .zip（null/undefined 直接返回，不报错）
 * @returns {Promise<void>}
 */
async function handleImport(file) {
  setNotice({ homeError: "", homeStatus: "" });
  if (!file) return;
  if (!session || !session.db || !repository) {
    elements.importFile.value = "";
    setNotice({ homeError: "本地数据库还在初始化，请稍候再导入。" });
    return;
  }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const result = await importProjectPackage(session.db, bytes);
    resetRowMode();
    await refresh();
    setNotice({ homeStatus: result.id_assigned
      ? "已导入「" + result.project.name + "」（同 id 项目已存在，已作为新项目导入）"
      : "已导入「" + result.project.name + "」" });
  } catch (error) {
    setNotice({ homeError: describeError(error) });
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
  const target = event.target;
  const file = target instanceof HTMLInputElement && target.files ? target.files[0] : undefined;
  handleImport(file);
});

elements.backHome.addEventListener("click", () => {
  showHome();
  void refresh();
});


/**
 * R3.3：ready = 完整恢复完成。首页控件默认禁用（HTML），boot 全程保持禁用，
 * 直到数据库打开、指针恢复、工作区装载、首页列表都结束才解锁；
 * boot 失败时保持禁用并给出错误 + 重试入口，不再出现"控件可用但背后没有仓库"的窗口。
 */
/**
 * R3.3 就绪门：数据库打开、指针恢复、工作区装载、首页列表全部完成后才解锁控件；
 * 失败保持禁用+错误+重试，不留假可用窗口。模型设置凭据仅标签页内存，不落盘。
 * @returns {Promise<void>} 始终 resolve（失败投影到 bootError，不上抛）
 */
async function bootstrap() {
  setHomeControlsBlocked(true);
  setNotice({ bootRetry: false, bootPending: true, bootError: "" });

  try {
    const capabilities = await probeBrowserCapabilities();
    renderCapabilityDiagnosis(capabilities);
    const blocked = capabilities.gaps.length > 0;

    if (!session) {
      session = createSession({
        createWorkspace: options => createWorkspace({ ...options, modelSettings }),
        onProjectChanged(project) {
          if (project && currentProjectId === project.project_id) showProject(project);
          if (currentProjectId) void refresh();
        },
      });
    }
    const active = session;
    const restored = await active.boot();
    // R3.3 验证探针：只暴露当前会话代与项目 ID，不暴露仓库/DOM 写能力。
    /** @type {Window & typeof globalThis & {__v2SessionProbe?: unknown}} */ (window).__v2SessionProbe = {
      get generation() { return active.generation; },
      get projectId() { return active.currentProject ? active.currentProject.project_id : null; },
      get phase() { return active.phase; },
    };
    const ready = active.repository;
    if (!ready) throw new Error("会话启动完成但没有可用的项目仓库。");
    repository = ready;
    // UI.3 全局保存状态：R3.3 重构时漏接——恢复 boot 成功后的单点投影接线。
    instrumentSaveState(ready);
    await refresh({ required: true });
    setNotice({ bootPending: false });
    if (blocked) {
      setHomeControlsBlocked(true);
      if (restored.project) await active.closeProject();
      showHome();
      return;
    }
    if (restored.project) {
      currentProjectId = restored.project.project_id;
      showProject(restored.project);
      resetSaveState();
    } else {
      showHome();
    }
    setHomeControlsBlocked(false);
  } catch (error) {
    setNotice({ bootPending: false, readError: "", bootRetry: true, bootError: describeError(error) });
    setHomeControlsBlocked(true);
  }
}

/** @returns {Promise<void>} 共享完整启动轮次，完成后允许明确重试。 */
function boot() {
  if (bootPromise) return bootPromise;
  bootPromise = bootstrap().finally(() => { bootPromise = null; });
  return bootPromise;
}

// Bootstrap fallback transfer: #boot-mount 的静态启动三节点只覆盖 app 未加载的窗口；
// 一旦装配成功，模板接管同一挂载点（无残留无重复 id），后续状态走 notices 渲染。
elements.bootMount.replaceChildren();
renderBoot();
renderNotices();
renderDiagnosis();
renderSaveState();
boot();
void modelSettings.refresh();
