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
 */

import { openStorage } from "./storage/index.js";

export const SESSION_PHASES = Object.freeze({
  idle: "idle",
  booting: "booting",
  ready: "ready",
  failed: "failed",
});

export function createSession({ createWorkspace, onProjectChanged = null } = {}) {
  if (typeof createWorkspace !== "function") {
    throw new Error("createSession 需要 createWorkspace 工厂。");
  }

  let db = null;
  let repository = null;
  let workspace = null;
  let generation = 0;
  let currentProject = null;
  let phase = SESSION_PHASES.idle;
  let bootPromise = null;

  function beginAction() {
    const snapshot = {
      generation,
      projectId: currentProject ? currentProject.project_id : null,
    };
    return {
      generation: snapshot.generation,
      projectId: snapshot.projectId,
      alive: () => snapshot.generation === generation
        && snapshot.projectId === (currentProject ? currentProject.project_id : null),
    };
  }

  async function boot() {
    if (bootPromise) return bootPromise;
    bootPromise = (async () => {
      phase = SESSION_PHASES.booting;
      generation += 1;
      if (workspace) {
        await workspace.close();
        workspace = null;
      }
      if (db) {
        try {
          db.close();
        } catch (_ignored) {
          // 旧连接已经不可用；重新打开即可。
        }
        db = null;
      }
      repository = null;
      currentProject = null;

      const opened = await openStorage();
      db = opened.db;
      repository = opened.repository;
      workspace = createWorkspace({ repository, session: api, onProjectChanged });
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

  async function openProject(projectRecord) {
    if (!repository) {
      throw new Error("会话未就绪，不能打开项目。");
    }
    if (workspace && workspace.isOpen()) {
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

  async function closeProject() {
    if (workspace && workspace.isOpen()) {
      await workspace.close();
    }
    generation += 1;
    currentProject = null;
  }

  const api = {
    get phase() {
      return phase;
    },
    get generation() {
      return generation;
    },
    get repository() {
      return repository;
    },
    get db() {
      return db;
    },
    get currentProject() {
      return currentProject;
    },
    beginAction,
    boot,
    openProject,
    closeProject,
  };
  return api;
}
