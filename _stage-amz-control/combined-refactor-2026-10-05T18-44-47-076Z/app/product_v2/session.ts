/**
 * Product V2 会话 Module（V2.R3.3）：boot / DB / pointer / restore / close 的唯一入口。
 *
 * 状态机：idle → booting → ready | failed。ready 表示"完整恢复已完成"（数据库打开、
 * 指针读取、工作区装载都结束），在这之前界面不可交互——不是"控件先解锁、恢复在
 * 后台继续"。boot 失败也给出明确失败态（界面停在禁用 + 错误 + 重试），不再留
 * "空白首页、点新建无响应"的假可用窗口。
 *
 * 每次会话动作（boot / openProject / closeProject）都推进 generation。动作开始时
 * 用 beginAction() 冻结 { generation, projectId }：
 *  - 冻结后的仓库写一律使用冻结的 projectId——旧回调可以把自己项目的记录写完整
 *    （含已发出的上游任务与已生成的候选；关闭/停止不承诺取消上游），但绝不写进
 *    之后打开的另一个项目；
 *  - 界面投影一律先问 alive()——旧回调不得重置视图、不得抢占焦点、不得覆盖
 *    新项目的渲染状态。
 *
 * 本模块不持有业务状态，也不做 DOM 投影；界面判定（ready/失败/重试）由调用方
 * 按 boot() 的结果与 phase 投影。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `session.js`
 * 由 `npm run build:frontend` 从本文件生成，浏览器只消费生成的 `.js`。
 */

import { openStorage } from "./storage/index.js";
import type { ProjectRepository, StoredProjectRecord } from "./storage/validate.js";

/** 会话阶段：idle → booting → ready | failed。 */
export type SessionPhase = "idle" | "booting" | "ready" | "failed";

export const SESSION_PHASES: Readonly<Record<SessionPhase, SessionPhase>> = Object.freeze({
  idle: "idle",
  booting: "booting",
  ready: "ready",
  failed: "failed",
});

/** 会话动作的冻结代次快照：alive() 判定旧回调是否还属于当前项目/代次。 */
export type ActionSnapshot = {
  readonly generation: number;
  readonly projectId: string | null;
  alive(): boolean;
};

/** boot() 的恢复结果：指针指向的项目，无则为 null。 */
export type SessionBootResult = {
  readonly project: StoredProjectRecord | null;
};

/** 项目变更通知：会话透传给工作区工厂，由调用方装配。 */
export type ProjectChangeListener = (project: StoredProjectRecord | null) => void;

/** 工作区句柄：会话管理打开/关闭与当前项目元数据，不感知工作区内部业务状态。 */
export type WorkspaceHandle = {
  open(project: StoredProjectRecord): Promise<void>;
  close(): Promise<void>;
  isOpen(): boolean;
  setProject(project: StoredProjectRecord): void;
};

/**
 * 工作区工厂：会话提供 repository / session / onProjectChanged。
 * 其余依赖（如 modelSettings）由调用方在外层装配后再透传，本模块不经手。
 */
export type WorkspaceFactory = (options: {
  readonly repository: ProjectRepository;
  readonly session: Session;
  readonly onProjectChanged: ProjectChangeListener | null;
}) => WorkspaceHandle;

/**
 * createSession 的输入：createWorkspace 是必需的（缺失时运行时抛错），
 * onProjectChanged 可选。保持可选 + 运行时守卫，与迁移前 JS 调用方逐字一致。
 */
export type CreateSessionOptions = {
  readonly createWorkspace?: WorkspaceFactory;
  readonly onProjectChanged?: ProjectChangeListener | null;
};

/** 会话公共接口：app/workspace 消费者只依赖这些成员做类型检查。 */
export type Session = {
  readonly phase: SessionPhase;
  readonly generation: number;
  readonly repository: ProjectRepository | null;
  readonly db: IDBDatabase | null;
  readonly currentProject: StoredProjectRecord | null;
  beginAction(): ActionSnapshot;
  boot(): Promise<SessionBootResult>;
  openProject(projectRecord: StoredProjectRecord): Promise<StoredProjectRecord>;
  closeProject(): Promise<void>;
  updateProjectMetadata(project: StoredProjectRecord): void;
};

export function createSession({ createWorkspace, onProjectChanged = null }: CreateSessionOptions = {}): Session {
  if (typeof createWorkspace !== "function") {
    throw new Error("createSession 需要 createWorkspace 工厂。");
  }
  const buildWorkspace: WorkspaceFactory = createWorkspace;

  let db: IDBDatabase | null = null;
  let repository: ProjectRepository | null = null;
  let workspace: WorkspaceHandle | null = null;
  let generation = 0;
  let currentProject: StoredProjectRecord | null = null;
  let phase: SessionPhase = SESSION_PHASES.idle;
  let bootPromise: Promise<SessionBootResult> | null = null;

  function beginAction(): ActionSnapshot {
    const snapshot: { generation: number; projectId: string | null } = {
      generation,
      projectId: currentProject ? currentProject.project_id : null,
    };
    return {
      generation: snapshot.generation,
      projectId: snapshot.projectId,
      alive: (): boolean => snapshot.generation === generation
        && snapshot.projectId === (currentProject ? currentProject.project_id : null),
    };
  }

  async function boot(): Promise<SessionBootResult> {
    if (bootPromise) return bootPromise;
    bootPromise = (async (): Promise<SessionBootResult> => {
      phase = SESSION_PHASES.booting;
      generation += 1;
      if (workspace) {
        await workspace.close();
        workspace = null;
      }
      if (db) {
        try {
          db.close();
        } catch {
          // 旧连接已经不可用；重新打开即可。
        }
        db = null;
      }
      repository = null;
      currentProject = null;

      const opened = await openStorage();
      db = opened.db;
      repository = opened.repository;
      workspace = buildWorkspace({ repository, session: api, onProjectChanged });
      const current = await repository.pointer.get();
      if (current) {
        currentProject = current;
        await workspace.open(current);
      }
      phase = SESSION_PHASES.ready;
      return { project: current };
    })();
    try {
      return await bootPromise;
    } catch (error) {
      phase = SESSION_PHASES.failed;
      throw error;
    } finally {
      bootPromise = null;
    }
  }

  async function openProject(projectRecord: StoredProjectRecord): Promise<StoredProjectRecord> {
    if (!repository) {
      throw new Error("会话未就绪，不能打开项目。");
    }
    if (!workspace) {
      // 与 !repository 同属"会话未就绪"：boot 成功时两者同时建立，
      // 只有 boot 中途失败才可能到这里，仍按未就绪报错，不抛 TypeError。
      throw new Error("会话未就绪，不能打开项目。");
    }
    if (workspace.isOpen()) {
      // 先把旧项目的草稿保存落库（旧 generation 仍有效），再换会话；
      // 之后 generation 推进，旧项目的一切回调都不再驱动界面。
      await workspace.close();
    }
    generation += 1;
    await repository.pointer.set(projectRecord.project_id);
    currentProject = projectRecord;
    await workspace.open(projectRecord);
    return projectRecord;
  }

  async function closeProject(): Promise<void> {
    if (workspace && workspace.isOpen()) {
      await workspace.close();
    }
    generation += 1;
    currentProject = null;
  }

  function updateProjectMetadata(projectRecord: StoredProjectRecord): void {
    if (!workspace || !currentProject || currentProject.project_id !== projectRecord.project_id) {
      throw new Error("不能更新非当前项目的会话元数据。");
    }
    // 改名不切换项目或推进 generation；正在执行的动作仍属于原会话。
    currentProject = projectRecord;
    workspace.setProject(projectRecord);
  }

  const api: Session = {
    get phase(): SessionPhase {
      return phase;
    },
    get generation(): number {
      return generation;
    },
    get repository(): ProjectRepository | null {
      return repository;
    },
    get db(): IDBDatabase | null {
      return db;
    },
    get currentProject(): StoredProjectRecord | null {
      return currentProject;
    },
    beginAction,
    boot,
    openProject,
    closeProject,
    updateProjectMetadata,
  };
  return api;
}
