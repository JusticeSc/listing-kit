/**
 * 输入视图（设计 §10.1 的第一个视图）：资料 → 商品理解 → 方案 三区的渲染与就地状态。
 *
 * 边界（设计 §10.1）：这里只持 DOM、展开/编辑与交互状态，以及自己创建的节点；不写库、
 * 不发网络、不重算业务判定。资料/事实/方案/风格/单图规格的唯一所有者是 project-inputs，
 * 本视图只经它的命令与投影读写；真正落库/派生/跨视图刷新都经 deps 回到工作区。
 *
 * 渲染（Issue #10 P5）：每个分区内部一律由 lit-html 声明式渲染——静态 id/class 保留在模板里，
 * 不再在重绘前 querySelector 抓取/回填，也不再逐节点 createElement；列表用 keyed repeat，
 * 受用户编辑的控件用 live 绑定，因此重绘不重建节点、不打断光标与 details 展开态。
 * 未保存的编辑态统一进本视图唯一的 UI 草稿状态（按 project/shot/slot 键，见 ViewDraft），
 * 外部（落库/另一个标签页/模型结论）更新只在“用户没改过”时被采纳，不静默覆盖未保存文本。
 * 引用图字节与 object URL 生命周期也归本视图（renderReferences/dispose），工作区不再持有。
 *
 * 本文件是唯一手工维护实现；浏览器只消费 Vite 构建产物。
 */
import { html, nothing, render as renderLit, type TemplateResult } from "lit-html";
import { live } from "lit-html/directives/live.js";
import { ref } from "lit-html/directives/ref.js";
import { repeat } from "lit-html/directives/repeat.js";
import {
  DIMENSION_AXES,
  DIMENSION_UNITS,
  FACT_SLOT_SCHEMA_VERSION,
  MAX_DIMENSIONS,
  MAX_ON_IMAGE_TEXTS,
  MAX_REFERENCES,
  PRODUCT_INPUT_SCHEMA_VERSION,
  REFERENCE_ROLES,
  REFERENCE_VIEWPOINTS,
  SHOT_LAYOUTS,
  SHOT_TEMPLATES,
  SLOT_VALUE_TYPES,
  TEXT_LAYOUTS,
  addCustomShotToPlan,
  addShotFromTemplate,
  canAddSlot,
  canConfirmSlot,
  canDeleteSlot,
  canEditValue,
  checkFactSlot,
  copyShot,
  coreSlotDefinition,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  formatMeasurementText,
  imageTextSourceOf,
  intakeReadiness,
  isPlainObject,
  layoutLabelOf,
  moveShot,
  MEASUREMENT_SOURCE_KINDS,
  MEASUREMENT_SOURCE_LABEL,
  PRESENTATION_CONSUMERS,
  PRESENTATION_FIELDS,
  presentationHasOwn,
  presentationStateOf,
  printDecisionRoleOf,
  printIntentLabelOf,
  recommendPlan,
  referenceViewpointEvidence,
  removeShot,
  seedSuitePlan,
  setShotFactBindings,
  shotReadiness,
  specChangeProjection,
  styleSpecDiff,
  suitePlanSummary,
  suiteSpecDigest,
} from "../domain/index.js";
import {
  AUTHORITY_TEXT,
  EVIDENCE_TEXT,
  ROLE_TEXT,
  STATUS_TEXT,
  describeBlocking,
  errorMessageOf,
  formatValue,
  reviewRankOf,
  splitLines,
} from "./dom.js";
import type { ActionSnapshot } from "../session.js";
import type { EffectiveCapabilities } from "../model-settings.js";
import type {
  CompleteProductInput,
  InputSlotEntry,
  InputsModule,
  LastAnalyze,
} from "../project-inputs.js";
import type {
  BriefReadiness,
  DependencyBlocking,
  DimensionAxis,
  DimensionMeasurement,
  DimensionUnit,
  DomainProblem,
  FactSlot,
  FactSlotValue,
  MeasurementBinding,
  MeasurementSourceKind,
  PlanRecommendation,
  ReferenceRole,
  ShotSpec,
  SlotActionSpec,
  SlotValueType,
  StyleSpec,
  SuitePlan,
  SuitePlanSummary,
} from "../domain/type-contracts.js";

/** 套图命令的统一出口签名：领域纯函数返回新计划与附加字段，落库与版本推进归 inputs。 */
type SuiteOpRunner = () => { plan: SuitePlan } & Record<string, unknown>;

/**
 * 本视图负责的分区宿主锚点（与 index.html 的静态 id 一一对应，只在绑定期解析一次）。
 * 解析出的宿主内部此后只由 lit 渲染：传入的句柄本身不再被读写，避免两套写手撞车；
 * 锚点可以是宿主本身，也可以是宿主内的静态元素（用 closest 归一）。
 */
export type InputElements = {
  /** 资料卡宿主锚点（index.html #intake-card）。 */
  intakeAnchor: HTMLElement;
  /** 确认事实卡宿主锚点（#analyze-card）。 */
  analyzeAnchor: HTMLElement;
  /** 事实槽位卡宿主锚点（#slots-card）。 */
  slotsAnchor: HTMLElement;
  /** 图片任务卡宿主锚点（#suite-card）。 */
  suiteAnchor: HTMLElement;
  /** 风格与单图规格宿主锚点（#specs-section）。 */
  specsAnchor: HTMLElement;
  /** 参考图卡宿主锚点（#references-card）。 */
  refsAnchor: HTMLElement;
};

/** 参考图读侧 AssetRepository 子集（工作区注入 repository.assets.get；视图只读字节）。 */
export type ReferenceAssetReader =
  (projectId: string, sha256: string) => Promise<unknown>;

/**
 * 窄依赖：输入面唯一所有者的命令/投影 + 工作区级收尾与跨视图刷新。
 * 不注入整个工作区；需要工作区状态的都经只读回调读取。
 */
export type InputViewDeps = {
  inputs: InputsModule;
  beginAction(): ActionSnapshot;
  currentProjectId(): string | null;
  capabilities(): EffectiveCapabilities | null;
  /** deriveAndApplyState 之后的工作区局部投影：商品理解阻断清单。 */
  understandingBlocking(): BriefReadiness["blocking"];
  deriveState(): Promise<void>;
  /** 工作区全量渲染（本视图渲染只是其中一步，供资料/槽位命令收尾复用）。 */
  renderWorkspace(): void;
  /** 生成/确认/尝试三个分区的同轮刷新（不属于本视图）。 */
  renderGenerationSections(): void;
  renderHeader(): void;
  refreshStageShell(): void;
  /** 阶段切换（含可选焦点交接）；外壳归工作区。 */
  selectStage(stageId: string, options?: { focusHeading?: boolean }): void;
  reportError(error: unknown): void;
  /** 参考图字节读（repository.assets.get）；object URL 生命周期归本视图。 */
  readAsset: ReferenceAssetReader;
  /** 槽位标识与状态词的中文投影；与提示词、确认单分区共用同一实现。 */
  localizeSlotTerms(message: unknown): string;
  /** 套图依据缺口的连接文本；与提示词分区共用同一实现。 */
  suiteBlockingText(blocking: DependencyBlocking[] | null | undefined): string;
};

export type InputView = {
  /** 资料/理解/方案分区投影；宿主与事件由视图自行装配。 */
  render(): void;
  renderIntake(): void;
  renderAnalyze(): void;
  /** 未保存资料草稿的唯一读侧，供输入 owner 消费。 */
  draftInputPayload(): CompleteProductInput;
  resetViewState(): void;
  saveIntakeNow(): Promise<boolean>;
  prepareManualFacts(): Promise<void>;
};

/** 资料表单草稿：字符串原样保留用户输入（trim 只发生在落库 payload 上）。 */
type IntakeDraft = { product_name: string; description: string; selling_points: string; focus: string };
/** 风格表单草稿（同资料：原文进草稿，payload 再规范化）。展示决定空串=未选（不预选、不写值）。 */
type StyleDraft = { background: string; lighting: string; color_tone: string; composition: string; avoid: string;
  appearance_state: string; contents_state: string };
/** 新增槽位表单草稿。 */
type SlotAddDraft = { id: string; label: string; type: string; value: string; allowModel: boolean };
/** 单条测量草稿（select/input 的原字符串，读取时再按词表收窄）。 */
type DimensionDraft = { object: string; axis: string; value: string; unit: string; source_basis: string };
/** 槽位编辑态草稿：同一时刻只开一个编辑器（interaction 决定归属）。 */
type SlotEditorDraft = {
  slotId: string; mode: string; text: string; dimensions: DimensionDraft[];
};
/** 单图事实绑定草稿：baseline 是上次从计划采纳的值，用于判断用户是否改过。 */
type BindingDraft = { values: string[]; baseline: string[] };
/** 勾选过的图中文案：记用户勾选当时看到的逐字值（列表按元素）与来源版本，保存时按这份写。
 *  origin 记这条文案的来路：用户从事实值勾选=user；采用 AI 候选文案=model（保存时逐字写入，不改写）。 */
type SelectedText = { slot_id: string; texts: string[]; version: number; origin?: "user" | "model" };
/** 单条测量的绑定草稿：raw 五元是勾选当时从来源值逐字抄的快照（绝不手填数字），
 * 标签与来源分类是人工逐项确认的映射。保存时快照与标签一起写入 measurement。
 * 轴向/单位/分类在人工确认前是空串，保持草稿可表达「还没填完」，由保存门与预览统一收口。 */
type MeasurementPick = {
  slot_id: string; version: number; index: number;
  object: string; axis: DimensionAxis | ""; value: number; unit: DimensionUnit | ""; source_basis: string;
  object_label: string; axis_label: string; source_kind: MeasurementSourceKind | "";
};
/** 分组来源标签草稿：覆盖的测量项必须全部同一来源分类（逐项确认过）；快照逐项抄来源值。 */
type MeasurementGroupPick = {
  slot_id: string; version: number; indices: number[];
  measurements: DimensionMeasurement[]; source_kind: MeasurementSourceKind;
};

/** 草稿 → 领域绑定：四类人工映射齐全且属于领域词表时才构成合法 MeasurementBinding。
 * 合法性只在这里判断一次（对照 domain 的同一组常量），调用方拿到的是已收窄的类型。 */
function measurementBindingOf(pick: MeasurementPick): MeasurementBinding | null {
  if (!MEASUREMENT_SOURCE_KINDS.includes(pick.source_kind)) return null;
  if (!(DIMENSION_AXES as readonly string[]).includes(pick.axis)) return null;
  if (!(DIMENSION_UNITS as readonly string[]).includes(pick.unit)) return null;
  return {
    object: pick.object, axis: pick.axis as DimensionAxis, value: pick.value,
    unit: pick.unit as DimensionUnit, source_basis: pick.source_basis,
    index: pick.index, object_label: pick.object_label, axis_label: pick.axis_label,
    source_kind: pick.source_kind as MeasurementSourceKind,
  };
}
/** 单图规格草稿（原文）+ 采纳基线。印字决定与版面空串=未选；selected 存勾选当时的槽位/逐字值/版本。
 * 视角：空串=沿用可见视角（不写单图覆盖）；显式 front/side/top 才写覆盖。
 * 参考选择：null=沿用角色默认；数组=明确选择（空数组=明确不选）。基线存同一形状用于判脏。
 * 测量绑定：measurements 存逐项确认的绑定（含来源快照与英文标签映射），
 * groups 存分组来源标签；两者都按槽位+版本+索引键，保存时与 selected 合流成 on_image_texts。 */
type ShotRefsDraft = { mode: "inherit" | "none" | "select"; shas: string[] };
type ShotSpecDraft = {
  purpose: string; keep: string; change_allowed: string;
  print_intent: string; layout: string; selected: SelectedText[];
  measurements: MeasurementPick[]; groups: MeasurementGroupPick[];
  viewpoint: string; refs: ShotRefsDraft;
  baseline: { purpose: string; keep: string; change_allowed: string;
    print_intent: string; layout: string; selected: SelectedText[];
    measurements: MeasurementPick[]; groups: MeasurementGroupPick[];
    viewpoint: string; refs: ShotRefsDraft };
};
/** 候选文案行：展示用的只读摘要（提议正文在 semantic_analysis 记录里）；stale 由来源版本复核得出。 */
type CopyRowDraft = {
  slot_id: string; version: number; text: string;
  provider: string; model: string | null; requestedAt: string;
};
/** 错误文案按分区持有：渲染是唯一写 DOM 的一侧，命令侧只改状态。 */
type RegionKey = "refs" | "intake" | "analyze" | "slots" | "suite" | "style" | "specs";

/** 视图唯一的 UI 草稿状态；scope 变化（切/关项目）整体归零。 */
type ViewDraft = {
  scope: string | null;
  intake: IntakeDraft;
  intakeBaseline: IntakeDraft;
  style: StyleDraft;
  styleBaseline: StyleDraft;
  slotAdd: SlotAddDraft;
  slotAddStatus: string;
  slot: SlotEditorDraft | null;
  bindings: Record<string, BindingDraft>;
  shotSpecs: Record<string, ShotSpecDraft>;
  /** 候选文案行（按 slot_id 键）：只读展示，不进保存 payload；采用=人工逐条写入规格草稿。 */
  copyRows: Record<string, CopyRowDraft[]>;
  customShot: { label: string; intent: string };
  customShotStatus: string;
  customPanelOpen: boolean;
  templateId: string;
  styleStatus: string;
  conflictPicks: Record<string, "mine" | "theirs">;
  errors: Record<RegionKey, string>;
};

/** 参考图行的只读呈现：字节与 object URL 都由本视图持有。 */
type ReferenceRow = {
  index: number;
  role: string;
  url: string | null;
  name: string;
  info: string;
  sha256: string;
};

const AXIS_LABELS: Record<string, string> = {
  height: "高度", width: "宽度", length: "长度", depth: "深度",
  diameter: "直径", weight: "重量", volume: "容量", thickness: "厚度",
};

const SLOT_ADD_TYPES: readonly { value: string; label: string }[] = Object.freeze([
  { value: "text", label: "文本" },
  { value: "text_list", label: "文本列表（一行一条）" },
  { value: "number", label: "数字" },
  { value: "boolean", label: "是 / 否" },
]);

function createDraft(scope: string | null): ViewDraft {
  return {
    scope,
    intake: { product_name: "", description: "", selling_points: "", focus: "" },
    intakeBaseline: { product_name: "", description: "", selling_points: "", focus: "" },
    style: { background: "", lighting: "", color_tone: "", composition: "", avoid: "", appearance_state: "", contents_state: "" },
    styleBaseline: { background: "", lighting: "", color_tone: "", composition: "", avoid: "", appearance_state: "", contents_state: "" },
    slotAdd: { id: "", label: "", type: "text", value: "", allowModel: false },
    slotAddStatus: "",
    slot: null,
    bindings: {}, shotSpecs: {},
    copyRows: {},
    customShot: { label: "", intent: "" }, customShotStatus: "",
    customPanelOpen: false,
    templateId: SHOT_TEMPLATES[0] ? SHOT_TEMPLATES[0].template_id : "",
    styleStatus: "",
    conflictPicks: {},
    errors: { refs: "", intake: "", analyze: "", slots: "", suite: "", style: "", specs: "" },
  };
}
function intakeDraftFrom(stored: CompleteProductInput | null | undefined): IntakeDraft {
  return {
    product_name: (stored && stored.product_name) || "",
    description: (stored && stored.description) || "",
    selling_points: stored?.selling_points.join("\n") || "",
    focus: (stored && stored.focus) || "",
  };
}
function styleDraftFrom(spec: StyleSpec): StyleDraft {
  // 存过的值进草稿供选中回填；没存过保持空串，界面显示「还没决定」而不预选。
  const appearance = presentationStateOf(spec, "appearance_state");
  const contents = presentationStateOf(spec, "contents_state");
  return {
    background: spec.background || "",
    lighting: spec.lighting || "",
    color_tone: spec.color_tone || "",
    composition: spec.composition || "",
    avoid: Array.isArray(spec.avoid) ? spec.avoid.join("\n") : "",
    appearance_state: appearance === "undecided" ? "" : String(appearance),
    contents_state: contents === "undecided" ? "" : String(contents),
  };
}
function equalIntake(left: IntakeDraft, right: IntakeDraft): boolean {
  return left.product_name === right.product_name && left.description === right.description
    && left.selling_points === right.selling_points && left.focus === right.focus;
}
function equalStyle(left: StyleDraft, right: StyleDraft): boolean {
  return left.background === right.background && left.lighting === right.lighting
    && left.color_tone === right.color_tone && left.composition === right.composition
    && left.avoid === right.avoid
    && left.appearance_state === right.appearance_state && left.contents_state === right.contents_state;
}
/** 勾选文案的同一性：槽位、逐字值（含元素顺序）、来源版本三者都要一致才算没改。 */
function selectedTextsKey(items: SelectedText[]): string {
  return items.map((item) => item.slot_id + "\u0000" + item.version + "\u0000" + item.texts.join("\u0002"))
    .join("\u0001");
}
/** 测量绑定的同一性：槽位/版本/索引/快照五元/标签映射/来源分类全一致才算没改。 */
function measurementPicksKey(items: MeasurementPick[]): string {
  return items.map((item) => [item.slot_id, item.version, item.index, item.object, item.axis,
    String(item.value), item.unit, item.source_basis,
    item.object_label, item.axis_label, item.source_kind].join("\u0000")).join("\u0001");
}
/** 分组标签的同一性：槽位/版本/索引集/快照/来源分类全一致才算没改。 */
function measurementGroupsKey(items: MeasurementGroupPick[]): string {
  return items.map((item) => [item.slot_id, item.version, item.indices.join(","),
    item.measurements.map((row) => [row.object, row.axis, String(row.value),
      row.unit, row.source_basis].join("\u0002")).join("\u0003"),
    item.source_kind].join("\u0000")).join("\u0001");
}
function refsDraftKey(refs: ShotRefsDraft): string {
  return refs.mode + "\u0000" + refs.shas.join("\u0002");
}
function equalShotSpec(left: ShotSpecDraft["baseline"], right: ShotSpecDraft["baseline"]): boolean {
  return left.purpose === right.purpose && left.keep === right.keep
    && left.change_allowed === right.change_allowed
    && left.print_intent === right.print_intent && left.layout === right.layout
    && left.viewpoint === right.viewpoint
    && refsDraftKey(left.refs) === refsDraftKey(right.refs)
    && selectedTextsKey(left.selected) === selectedTextsKey(right.selected)
    && measurementPicksKey(left.measurements) === measurementPicksKey(right.measurements)
    && measurementGroupsKey(left.groups) === measurementGroupsKey(right.groups);
}
function refsDraftFrom(spec: ShotSpec): ShotRefsDraft {
  // reference_sha256s 缺失=沿用角色默认；显式 []=明确不选；非空=显式勾选（顺序即用户所选）。
  if (!Object.prototype.hasOwnProperty.call(spec, "reference_sha256s")) {
    return { mode: "inherit", shas: [] };
  }
  const stored = Array.isArray(spec.reference_sha256s) ? spec.reference_sha256s : [];
  if (stored.length === 0) return { mode: "none", shas: [] };
  return { mode: "select", shas: [...stored] };
}
function shotSpecDraftFrom(spec: ShotSpec): ShotSpecDraft {
  // print_intent "undecided" 与缺失都表示未决定：草稿归一为空串，界面不预选；
  // 所选文案回填的是「用户当初确认过的那一版」（逐字值 + 来源版本），
  // 不按当前事实重取——来源前进时要让用户重新勾选确认，而不是静默换值。
  // 来源形状走 domain 唯一读口 imageTextSourceOf：V1 flat 与 V2 对象都理解，不在视图里复刻形状判断。
  const printIntent = typeof spec.print_intent === "string" && spec.print_intent !== "undecided" ? spec.print_intent : "";
  const selected: SelectedText[] = [];
  const measurements: MeasurementPick[] = [];
  const groups: MeasurementGroupPick[] = [];
  if (Array.isArray(spec.on_image_texts)) {
    for (const item of spec.on_image_texts) {
      if (!isPlainObject(item)) continue;
      const record = item as { text?: unknown; measurement?: unknown; measurement_source?: unknown };
      const source = imageTextSourceOf(item);
      if (!source || typeof record.text !== "string") continue;
      // 带测量绑定的条目回填绑定草稿（快照+标签映射原样回填，不按当前事实重取）；
      // 无绑定条目走 plain 文案通道。同一槽位的多条 plain 在草稿里合成一项。
      if (isPlainObject(record.measurement)) {
        const binding = record.measurement as Record<string, unknown>;
        if (typeof binding.index === "number" && typeof binding.value === "number") {
          // 读取时按领域词表收窄（只回填合法值；非法值不冒充已确认映射）。
          measurements.push({
            slot_id: source.document_id, version: source.version, index: binding.index,
            object: typeof binding.object === "string" ? binding.object : "",
            axis: typeof binding.axis === "string"
              && (DIMENSION_AXES as readonly string[]).includes(binding.axis)
              ? binding.axis as DimensionAxis : "",
            value: binding.value,
            unit: typeof binding.unit === "string"
              && (DIMENSION_UNITS as readonly string[]).includes(binding.unit)
              ? binding.unit as DimensionUnit : "",
            source_basis: typeof binding.source_basis === "string" ? binding.source_basis : "",
            object_label: typeof binding.object_label === "string" ? binding.object_label : "",
            axis_label: typeof binding.axis_label === "string" ? binding.axis_label : "",
            source_kind: typeof binding.source_kind === "string"
              && MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)
              ? binding.source_kind as MeasurementSourceKind : "",
          });
          continue;
        }
      }
      if (isPlainObject(record.measurement_source)) {
        const binding = record.measurement_source as Record<string, unknown>;
        const kind = typeof binding.source_kind === "string"
          && MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)
          ? binding.source_kind as MeasurementSourceKind : null;
        if (kind && Array.isArray(binding.indices) && Array.isArray(binding.measurements)) {
          groups.push({
            slot_id: source.document_id, version: source.version,
            indices: (binding.indices as unknown[]).filter(
              (entry): entry is number => typeof entry === "number"),
            measurements: (binding.measurements as unknown[]).filter(isPlainObject)
              .map((row) => ({ ...(row as object) }) as DimensionMeasurement),
            source_kind: kind,
          });
          continue;
        }
      }
      const existing = selected.find((entry) => entry.slot_id === source.document_id
        && entry.version === source.version);
      if (existing) {
        existing.texts.push(record.text);
      } else {
        selected.push({
          slot_id: source.document_id, texts: [record.text],
          version: source.version,
          // 来源记回草稿：采用 AI 候选的条目再次保存时不降级成 user。
          origin: (item as { origin?: unknown }).origin === "model" ? "model" : "user",
        });
      }
    }
  }
  // 视角：只有单图自有显式 front/side/top 才回填为覆盖；缺失或 reference_visible 都归一为空串
  // （=沿用可见视角，不写覆盖）。显式 undecided 是阻断态，草稿同样置空并由保存时重写。
  const ownViewpoint = presentationHasOwn(spec, "viewpoint")
    && isPlainObject(spec.presentation)
    && typeof (spec.presentation as { viewpoint?: unknown }).viewpoint === "string"
    ? String((spec.presentation as { viewpoint: string }).viewpoint) : "";
  const viewpoint = ownViewpoint === "front" || ownViewpoint === "side" || ownViewpoint === "top"
    ? ownViewpoint : "";
  const refs = refsDraftFrom(spec);
  const baseline = {
    purpose: spec.purpose || "",
    keep: Array.isArray(spec.keep) ? spec.keep.join("\n") : "",
    change_allowed: Array.isArray(spec.change_allowed) ? spec.change_allowed.join("\n") : "",
    print_intent: printIntent,
    layout: typeof spec.layout === "string" ? spec.layout : "",
    selected: selected,
    measurements: measurements,
    groups: groups,
    viewpoint: viewpoint,
    refs: refs,
  };
  return { ...baseline, selected: [...selected],
    measurements: measurements.map((item) => ({ ...item })),
    groups: groups.map((item) => ({ ...item, indices: [...item.indices],
      measurements: item.measurements.map((row) => ({ ...row })) })),
    refs: { mode: refs.mode, shas: [...refs.shas] },
    baseline: { ...baseline, selected: [...selected],
      measurements: measurements.map((item) => ({ ...item })),
      groups: groups.map((item) => ({ ...item, indices: [...item.indices],
        measurements: item.measurements.map((row) => ({ ...row })) })),
      refs: { mode: refs.mode, shas: [...refs.shas] } } };
}
function measurementToDraft(measurement: DimensionMeasurement | Record<string, unknown>): DimensionDraft {
  const fields = measurement as Record<string, unknown>;
  const text = (key: string): string => (fields[key] === null || fields[key] === undefined ? "" : String(fields[key]));
  return { object: text("object"), axis: text("axis"), value: text("value"), unit: text("unit"), source_basis: text("source_basis") };
}
function storedAssetShape(value: unknown): {
  blob: Blob | null; originalName: string; mediaType: string; byteSize: number | null;
  width: number | null; height: number | null;
} {
  const record = isPlainObject(value) ? value as Record<string, unknown> : {};
  const blob = record.blob instanceof Blob ? record.blob : null;
  return {
    blob,
    originalName: typeof record.original_name === "string" ? record.original_name : "",
    mediaType: typeof record.media_type === "string" ? record.media_type : "",
    byteSize: typeof record.byte_size === "number" ? record.byte_size : null,
    width: typeof record.width === "number" ? record.width : null,
    height: typeof record.height === "number" ? record.height : null,
  };
}

/**
 * 输入视图工厂。
 * @param args.elements 分区锚点（只在绑定期解析宿主一次）
 * @param args.deps 窄依赖：输入面所有者命令/投影 + 工作区收尾回调
 */
export function createInputView(
  { elements, deps }: { elements: InputElements; deps: InputViewDeps },
): InputView {
  /** 视图唯一的 UI 草稿状态（资料/风格/槽位/绑定/规格/新增表单/冲突选择）。 */
  let draft: ViewDraft = createDraft(null);
  /** 最近一次分析摘要、未写入的提案问题、结果未知的待确认标记。 */
  let lastAnalyze: LastAnalyze = null;
  let analyzeRequiresConfirmation = false;
  let analyzeProblems: string[] = [];
  let analyzeErrorText = "";
  /** 槽位列表展开态（只属于本视图）。 */
  let showAll = false;
  /** 分区宿主：首次 render 解析一次，之后只由 lit 渲染。 */
  let refsHost: HTMLElement | null = null;
  let intakeHost: HTMLElement | null = null;
  let analyzeHost: HTMLElement | null = null;
  let slotsHost: HTMLElement | null = null;
  let suiteHost: HTMLElement | null = null;
  let specsHost: HTMLElement | null = null;
  let bound = false;
  /** 参考图：行投影、object URL 集合与重叠渲染失效标记。 */
  let referenceRows: ReferenceRow[] = [];
  let referenceUrls: string[] = [];
  let referenceToken = 0;
  /** 模板里 ref 出来的文件选择控件（点击“添加参考图…”时转发）。 */
  let fileInputNode: HTMLInputElement | null = null;

  // 依赖别名：搬过来的实现保持原调用写法，装配面只经上面的窄接口进出。
  const inputs = deps.inputs;
  const beginAction = deps.beginAction;
  const deriveAndApplyState = deps.deriveState;
  const renderAll = deps.renderWorkspace;
  const refreshStageShell = deps.refreshStageShell;
  const selectStage = deps.selectStage;
  const handleInternalError = deps.reportError;
  const localizeSlotTerms = deps.localizeSlotTerms;
  const suiteBlockingText = deps.suiteBlockingText;

  /* ------------------------------------------------------------ 宿主与状态 */

  /**
   * 宿主解析：六个分区各自的静态卡/区就是 lit 的渲染容器；容器内部因此不再有第二个写手。
   * 缺锚点即装配错误：宁可显式失败，也不静默回退到旧的逐节点构造。
   */
  function resolveHosts(): void {
    if (bound) return;
    const hostOf = (anchor: HTMLElement, selector: string, label: string): HTMLElement => {
      const host = anchor && typeof anchor.closest === "function" ? anchor.closest(selector) : null;
      if (!host) throw new Error("输入视图缺少 " + label + " 宿主（" + selector + "）。");
      return host as HTMLElement;
    };
    refsHost = hostOf(elements.refsAnchor, ".card", "参考图");
    intakeHost = hostOf(elements.intakeAnchor, ".card", "资料");
    analyzeHost = hostOf(elements.analyzeAnchor, ".card", "确认事实");
    slotsHost = hostOf(elements.slotsAnchor, ".card", "事实槽位");
    suiteHost = hostOf(elements.suiteAnchor, ".card", "图片任务");
    specsHost = hostOf(elements.specsAnchor, "section", "风格与规格");
    bound = true;
  }


  /** 项目作用域：切/关项目一律丢弃草稿与引用图资源，避免跨项目串写。 */
  function ensureScope(): void {
    const pid = deps.currentProjectId();
    if (draft.scope === pid) return;
    dispose();
    draft = createDraft(pid);
  }

  /** 关闭/切项目：引用图 object URL 与在途渲染一起失效。 */
  function dispose(): void {
    referenceToken += 1;
    for (const url of referenceUrls) URL.revokeObjectURL(url);
    referenceUrls = [];
    referenceRows = [];
    fileInputNode = null;
  }

  /** 外部更新只在用户没有改过该草稿时被采纳：不静默覆盖未保存文本。 */
  function syncDrafts(): void {
    const storedIntake = intakeDraftFrom(inputs.intakeSnapshot());
    if (equalIntake(draft.intake, draft.intakeBaseline)) {
      draft.intake = storedIntake;
      draft.intakeBaseline = { ...storedIntake };
    } else if (equalIntake(draft.intake, storedIntake)) {
      draft.intakeBaseline = { ...storedIntake };
    }
    const storedStyle = styleDraftFrom(inputs.styleSpec());
    if (equalStyle(draft.style, draft.styleBaseline)) {
      draft.style = storedStyle;
      draft.styleBaseline = { ...storedStyle };
    } else if (equalStyle(draft.style, storedStyle)) {
      draft.styleBaseline = { ...storedStyle };
    }
    if (!SHOT_TEMPLATES.some((template) => template.template_id === draft.templateId)) {
      draft.templateId = SHOT_TEMPLATES[0] ? SHOT_TEMPLATES[0].template_id : "";
    }
  }

  /** 套图相关草稿（绑定/单图规格）按 shot 键随计划同步；未编辑过的草稿跟随计划变化。 */
  function syncShotDrafts(): void {
    const plan = inputs.suitePlan();
    if (!plan) {
      draft.bindings = {};
      return;
    }
    for (const shot of plan.shots) {
      const shotId = shot.shot_id;
      const planned = Array.isArray(shot.fact_slot_ids) ? [...shot.fact_slot_ids] : [];
      const binding = draft.bindings[shotId];
      if (!binding) {
        draft.bindings[shotId] = { values: [...planned], baseline: [...planned] };
      } else if (binding.values.join("\u0000") === binding.baseline.join("\u0000")) {
        draft.bindings[shotId] = { values: [...planned], baseline: [...planned] };
      } else if (binding.values.join("\u0000") === planned.join("\u0000")) {
        binding.baseline = [...planned];
      }

      const entry = inputs.shotSpecEntry(shotId);
      const spec = entry ? entry.spec : emptyShotSpecFromShot(shot);
      const stored = shotSpecDraftFrom(spec);
      const existing = draft.shotSpecs[shotId];
      if (!existing) {
        draft.shotSpecs[shotId] = stored;
      } else if (equalShotSpec(existing, existing.baseline)) {
        draft.shotSpecs[shotId] = stored;
      } else if (equalShotSpec(existing, stored)) {
        draft.shotSpecs[shotId] = { ...existing, baseline: { ...stored.baseline } };
      }
    }
  }

  /* ------------------------------------------------------------ 资料分区 */

  /** 未保存草稿判据：资料草稿与采纳基线不一致即“正在编辑”。 */
  function intakeDirty(): boolean {
    return !equalIntake(draft.intake, draft.intakeBaseline);
  }

  function draftStatusText(): string {
    const conflictState = inputs.conflict();
    const storedVersion = inputs.draftVersion();
    const storedName = inputs.intakeSnapshot().product_name;
    if (conflictState) {
      // R3.3 双标签陈旧编辑：就地报冲突，不静默胜出。文档历史是 append-only。
      if (conflictState.merged === true) {
        return "另一个标签页已保存版本 v" + conflictState.version
          + "：你的输入已按本地优先自动合并为新版本；请核对内容后再次保存确认。";
      }
      if (Array.isArray(conflictState.unresolved) && conflictState.unresolved.length > 0) {
        return "另一个标签页已保存版本 v" + conflictState.version
          + "：有 " + conflictState.unresolved.length + " 项需要你逐项解决，请在冲突编辑器里处理。";
      }
      return "检测到另一个标签页已保存版本 v" + conflictState.version
        + "：你正在编辑的内容没有覆盖它；再次保存会追加为新版本。";
    }
    if (intakeDirty()) return "正在编辑…";
    return storedVersion
      ? "草稿已保存 · 版本 " + storedVersion + (storedName ? "" : "（尚未填写商品名称）")
      : "还没有保存过草稿。";
  }

  /**
   * 冲突编辑器（R3.3）：只读所有者的未解决项；选择与保存都留在本视图草稿里，
   * 落库/合并由 owner 负责。引用图冲突按 asset_sha256 自动合并，这里只列文案字段。
   */
  function conflictEditorTemplate(
    conflictState: { version: number },
    unresolved: { field: string; mine: unknown; theirs: unknown }[],
  ): TemplateResult {
    return html`
      <div class="conflict-editor" role="group" aria-label="双标签编辑冲突，需要人工逐项解决">
        <p class="meta">另一个标签页已保存版本 v${conflictState.version}：以下字段两边都改了，请逐项选择保留哪一边。</p>
        ${unresolved.map((item) => {
          const pick = draft.conflictPicks[item.field] === "theirs" ? "theirs" : "mine";
          return html`
            <div class="conflict-row" data-field=${item.field}>
              <p class="name">字段：${item.field}</p>
              <p class="meta">对方 v${conflictState.version}：${String(item.theirs === "" ? "（空）" : item.theirs)}</p>
              <p class="meta">我的：${String(item.mine === "" ? "（空）" : item.mine)}</p>
              <button type="button" aria-pressed=${pick === "mine" ? "true" : "false"}
                @click=${() => { draft.conflictPicks[item.field] = "mine"; renderIntakeCard(); }}>保留我的</button>
              <button type="button" aria-pressed=${pick === "theirs" ? "true" : "false"}
                @click=${() => { draft.conflictPicks[item.field] = "theirs"; renderIntakeCard(); }}>用对方的</button>
            </div>
          `;
        })}
        <button type="button" class="primary" @click=${() => void handleResolveConflict(unresolved)}>按我的选择保存为新版本</button>
        <button type="button" @click=${() => { draft.conflictPicks = {}; renderIntakeCard(); }}>稍后处理</button>
      </div>
    `;
  }

  async function handleResolveConflict(
    unresolved: { field: string; mine: unknown; theirs: unknown }[],
  ): Promise<void> {
    const resolved: Record<string, "mine" | "theirs"> = {};
    for (const item of unresolved) {
      resolved[item.field] = draft.conflictPicks[item.field] === "theirs" ? "theirs" : "mine";
    }
    try {
      const ok = await inputs.resolveConflict(resolved);
      if (!ok) return;
      draft.conflictPicks = {};
      // 解决后屏幕就该显示落库后的版本：未保存的本地编辑已被本次选择吸收。
      draft.intake = intakeDraftFrom(inputs.intakeSnapshot());
      draft.intakeBaseline = { ...draft.intake };
      renderIntakeCard();
    } catch (error) {
      failRegion("intake", errorMessageOf(error, "冲突解决没有保存，请重试。"));
    }
  }

  function intakeCardTemplate(): TemplateResult {
    const conflictState = inputs.conflict();
    const unresolved = conflictState && Array.isArray(conflictState.unresolved)
      ? conflictState.unresolved : [];
    return html`
      <div class="card-head">
        <h4 id="intake-title">商品资料</h4>
        <p class="meta">只有你填写的内容进这里；模型推断写在“商品理解”，不覆盖这里。</p>
      </div>
      <div class="field">
        <label for="intake-name">商品名称（必填）</label>
        <input id="intake-name" maxlength="120" autocomplete="off"
          .value=${live(draft.intake.product_name)} @input=${intakeInput("product_name")}>
      </div>
      <div class="field">
        <label for="intake-description">商品介绍</label>
        <textarea id="intake-description" rows="4" maxlength="2000"
          .value=${live(draft.intake.description)} @input=${intakeInput("description")}></textarea>
      </div>
      <div class="field">
        <label for="intake-selling-points">卖点（一行一条）</label>
        <textarea id="intake-selling-points" rows="4"
          .value=${live(draft.intake.selling_points)} @input=${intakeInput("selling_points")}></textarea>
      </div>
      <div class="field">
        <label for="intake-focus">本次重点</label>
        <input id="intake-focus" maxlength="500" autocomplete="off"
          .value=${live(draft.intake.focus)} @input=${intakeInput("focus")}>
      </div>
      <div class="toolbar">
        <button id="intake-save" type="button" @click=${() => void handleSaveIntake()}>保存草稿</button>
        <span id="intake-draft" class="meta" role="status">${draftStatusText()}</span>
      </div>
      ${conflictState && unresolved.length
        ? conflictEditorTemplate(conflictState, unresolved) : nothing}
      <p id="intake-error" class="error" role="alert" ?hidden=${!draft.errors.intake}>${draft.errors.intake}</p>
    `;
  }

  function intakeInput(key: keyof IntakeDraft): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement | HTMLTextAreaElement;
      draft.intake[key] = node.value;
      scheduleDraftSave();
    };
  }

  function renderIntakeCard(): void {
    ensureScope();
    if (!intakeHost) return;
    renderLit(intakeCardTemplate(), intakeHost);
  }

  function renderIntake(): void {
    syncDrafts();
    renderIntakeCard();
  }

  function scheduleDraftSave(): void {
    inputs.scheduleDraftSave();
    renderIntakeCard();
    renderAnalyzeCard();
  }

  function saveIntakeNow(): Promise<boolean> {
    return inputs.saveIntakeNow().then((ok) => deriveAndApplyState().then(() => ok));
  }

  /* ------------------------------------------------------------ 理解分区 */

  function gateProblems(): DomainProblem[] {
    return intakeReadiness(draftInputPayload()).blocking;
  }

  function seesImages(provider: unknown): boolean {
    const caps = isPlainObject(provider) && isPlainObject(provider.capabilities) ? provider.capabilities : {};
    return caps.vision === true || caps.supports_images === true;
  }

  /**
   * 分析失败的可见摘要：人话在前，分类与重试策略是网关信封在前端的投影（§9.10），
   * 与落库记录同源，不在渲染层重算。结果未知时追加「可能已计费、不会自动重试」，
   * 不把未知说成失败，也不让用户以为系统会自己重发。
   */
  function describeAnalyzeFailure(error: unknown, unknown: unknown): string {
    const parts = [String(errorMessageOf(error, "分析失败"))];
    const info = isPlainObject(error) ? error : {};
    parts.push("分类：" + String(info.family || "internal")
      + " / " + String(info.code || "INTERNAL_ERROR"));
    if (info.retry_policy) parts.push("重试策略：" + String(info.retry_policy));
    if (unknown) {
      parts.push("结果未知：这次请求可能已经产生结果。系统不会自动重试，请确认后再手动点击“重新分析”。");
    }
    return parts.join(" ");
  }

  function analyzeCardTemplate(): TemplateResult {
    const problems = gateProblems();
    const ready = problems.length === 0;
    const provider = deps.capabilities()?.provider;
    const vision = seesImages(provider);
    const imageCount = Math.min(inputs.references().length, 3);
    const blocked = inputs.isAnalysisRunning() || !ready || !provider || provider.configured === false;
    const gate = inputs.isAnalysisRunning() ? "理解中；不会自动重试…"
      : !ready ? "还缺：" + describeBlocking(problems, localizeSlotTerms)
        : !provider || provider.configured === false
          ? "此用途缺少有效模型或凭据；请打开模型设置。人工填写不受影响。"
          : "将发给 " + provider.model_id + "：当前名称、介绍、卖点与重点，"
            + (vision ? imageCount + " 张实际图片（按列表顺序，主图优先，最多 3 张）"
              : "仅参考图元数据，不发送图片字节")
            + "。供应商按实际调用计费；不能据元数据宣称已经看图。";
    const result = lastAnalyze
      ? "最近一次分析：" + lastAnalyze.slots + " 个提案，写入 " + lastAnalyze.applied + " 个槽位 · "
        + lastAnalyze.provider + (lastAnalyze.model ? "（" + lastAnalyze.model + "）" : "")
        + " · 原资料 v" + lastAnalyze.sourceVersion
        + (lastAnalyze.referenceImagesSent
          ? " · 已发送实际图片" + ((lastAnalyze.imageProvenance || []).length
            ? "（" + lastAnalyze.imageProvenance.map((item) => item.role + "/" + item.sha256.slice(0, 12) + "…").join("、") + "）"
            : "")
          : " · 未发送图片字节")
        + " · " + lastAnalyze.at + (lastAnalyze.summary ? " · " + lastAnalyze.summary : "")
      : null;
    const errorVisible = analyzeProblems.length > 0 || analyzeErrorText.length > 0;
    return html`
      <div class="card-head">
        <h4 id="analyze-title">确认商品事实</h4>
        <p class="meta">可以直接人工填写。AI 理解只提出待确认的建议，不自动确认事实；仅在你明确点击时外发资料。</p>
      </div>
      <div class="toolbar">
        <button id="manual-facts" class="primary" type="button" @click=${() => void handleManualFacts()}>自己填写商品事实</button>
        <button id="analyze-run" type="button" ?disabled=${blocked}
          @click=${() => void runAnalyze()}>${(lastAnalyze ? "再次" : "") + (vision ? "图文理解" : "仅文字理解") + "（可选）"}</button>
        <button id="analyze-new-after-unknown" type="button" ?hidden=${!analyzeRequiresConfirmation}
          ?disabled=${blocked} @click=${() => void runAnalyze({ allowNewAfterUnknown: true })}>另发新分析（可能重复计费）</button>
        <span id="analyze-gate" class="meta" role="status">${gate}</span>
      </div>
      <p id="analyze-result" class="status" role="status" ?hidden=${!result}>${result || ""}</p>
      <p id="analyze-error" class="error" role="alert" ?hidden=${!errorVisible}>${analyzeProblems.length
        ? html`<span>部分提案没有写入：</span><ul class="inline-list">${analyzeProblems.map((item) => html`<li>${item}</li>`)}</ul>`
        : analyzeErrorText}</p>
    `;
  }

  function renderAnalyzeCard(): void {
    ensureScope();
    if (!analyzeHost) return;
    renderLit(analyzeCardTemplate(), analyzeHost);
  }

  function renderAnalyze(): void {
    renderAnalyzeCard();
  }

  let manualFactsPreparing = false;
  async function prepareManualFacts(): Promise<void> {
    if (!deps.currentProjectId() || manualFactsPreparing) return;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    manualFactsPreparing = true;
    try {
      await inputs.ensureCoreSlots();
      if (!action.alive()) return;
      await deriveAndApplyState();
      renderSlotsCard();
      refreshStageShell();
    } catch (error) {
      if (action.alive()) handleInternalError(error);
    } finally { manualFactsPreparing = false; }
  }

  async function runAnalyze({ allowNewAfterUnknown = false }: { allowNewAfterUnknown?: boolean } = {}): Promise<void> {
    const action = beginAction();
    analyzeProblems = [];
    analyzeErrorText = "";
    analyzeRequiresConfirmation = false;
    const pending = inputs.runAnalysis({ allowNewAfterUnknown });
    renderAnalyzeCard();
    try {
      const outcome = await pending;
      if (!action.alive()) return;
      if (outcome.kind === "requires_confirmation") {
        analyzeRequiresConfirmation = true;
        analyzeErrorText = "原分析结果仍未知，可能已经计费。不会自动重提；只有明确选择“另发新分析”才会再次发送，可能重复计费。";
      } else if (outcome.kind === "not_sent" || outcome.kind === "apply_failed") {
        analyzeErrorText = outcome.message;
      } else if (outcome.kind === "failed" || outcome.kind === "unknown") {
        analyzeRequiresConfirmation = outcome.kind === "unknown";
        analyzeErrorText = describeAnalyzeFailure(outcome.error, outcome.kind === "unknown");
      } else if (outcome.kind === "stale") {
        analyzeErrorText = "提案已保留在原资料 v" + outcome.record.source.version
          + " 的分析记录中；当前资料已变化，没有写入当前事实。";
      } else if (outcome.kind === "applied") {
        const { proposal, applied, record } = outcome;
        analyzeProblems = applied.problems;
        lastAnalyze = {
          at: new Date(record.updated_at).toLocaleString("zh-CN", { hour12: false }),
          provider: proposal.meta.provider_id, model: proposal.meta.model_id,
          slots: proposal.slots.length, applied: applied.applied, summary: proposal.summary,
          sourceVersion: record.source.version, referenceImagesSent: record.reference_images_sent,
          imageProvenance: [...(record.image_provenance || [])],
        };
        if (proposal.questions.length) analyzeProblems.push("模型提出的问题：" + proposal.questions.join(" / "));
      }
      renderAnalyzeCard();
    } catch (error) {
      if (action.alive()) handleInternalError(error);
    } finally {
      if (action.alive()) {
        try { await deriveAndApplyState(); }
        catch (error) { handleInternalError(error); }
        renderAll();
      }
    }
  }

  /* ------------------------------------------------------------ 事实槽位 */

  function dependencyCountOf(slotId: string): number {
    let count = 0;
    for (const entry of inputs.slotEntries()) {
      if ((entry.slot.depends_on || []).includes(slotId)) count += 1;
    }
    return count;
  }

  /** 某个 slot_id 的中文名（找不到就退回原样）；依赖与来源引用用它去掉工程感。 */
  function slotLabelOfId(slotId: string): string {
    for (const entry of inputs.slotEntries()) {
      if (entry.slot && entry.slot.slot_id === slotId) return entry.slot.label || slotId;
    }
    return slotId;
  }

  /** 主行只放人话：来源档 + 置信（「必须确认」已经是徽标，不再重复一次）。 */
  function slotMetaText(entry: InputSlotEntry): string {
    const slot = entry.slot;
    const parts = [(AUTHORITY_TEXT as Record<string, string>)[slot.authority] || slot.authority];
    if (slot.confidence !== null && slot.confidence !== undefined) {
      parts.push("置信 " + Number(slot.confidence).toFixed(2));
    }
    return parts.join(" · ");
  }

  /**
   * 事实卡的工程标识（V2.6.16）：slot_id、版本、依赖、证据来源引用（字段名 / 资产哈希 /
   * 模型 id）一律进折叠的技术详情，主行只留人能判断的信息；追溯链不减，只是换了位置。
   */
  function slotTechLines(entry: InputSlotEntry): string[] {
    const slot = entry.slot;
    const lines = ["标识 " + slot.slot_id, "版本 v" + entry.version];
    if (slot.depends_on && slot.depends_on.length) {
      lines.push("依赖 " + slot.depends_on.map((id) => slotLabelOfId(id)).join("、"));
    }
    const refs = (Array.isArray(slot.evidence) ? slot.evidence : [])
      .map((item) => (item && item.ref ? String(item.ref) : ""))
      .filter((ref) => ref !== "");
    if (refs.length) lines.push("来源引用 " + refs.join("、"));
    return lines;
  }

  /** 建议值来自模型提案证据（note 里的 JSON）；解析失败即视为没有建议。 */
  function suggestedValue(slot: FactSlot): unknown {
    for (const item of slot.evidence || []) {
      if (item && item.ref === "model_proposal" && typeof item.note === "string") {
        try {
          return JSON.parse(item.note);
        } catch (error) {
          return null;
        }
      }
    }
    return null;
  }

  /** 打开编辑器时把当前值/建议播种进草稿（同一 slot 同一 mode 不重复播种）。 */
  function openSlotEditor(entry: InputSlotEntry, mode: string): void {
    const slot = entry.slot;
    if (draft.slot && draft.slot.slotId === slot.slot_id && draft.slot.mode === mode) return;
    const suggestion = suggestedValue(slot);
    if (slot.value_type === "dimension_list") {
      const initial = Array.isArray(slot.value) ? slot.value
        : (Array.isArray(suggestion) ? suggestion : []);
      const measurements = (initial.length ? initial : [{}]).slice(0, MAX_DIMENSIONS)
        .map((item) => measurementToDraft(item as Record<string, unknown>));
      draft.slot = { slotId: slot.slot_id, mode, text: "", dimensions: measurements };
      return;
    }
    let text = "";
    if (slot.value_type === "text_list") {
      const initial = Array.isArray(slot.value) ? slot.value : (Array.isArray(suggestion) ? suggestion : []);
      text = initial.join("\n");
    } else if (slot.value_type === "boolean") {
      text = String(slot.value === true || (slot.value === null && suggestion === true));
    } else if (slot.value_type === "enum") {
      text = typeof slot.value === "string" ? slot.value
        : (typeof suggestion === "string" ? suggestion : "");
    } else {
      text = slot.value !== null && slot.value !== undefined ? String(slot.value)
        : (suggestion !== null && suggestion !== undefined ? String(suggestion) : "");
    }
    draft.slot = { slotId: slot.slot_id, mode, text, dimensions: [] };
  }

  function closeSlotEditor(): void {
    draft.slot = null;
  }

  /** 编辑器值只从草稿读取：不再回读 DOM，重绘因此不会丢用户输入。 */
  function readSlotEditorValue(slot: FactSlot): FactSlotValue {
    const editor = draft.slot;
    if (!editor) throw new Error("编辑器已关闭，请重新打开。");
    if (slot.value_type === "dimension_list") {
      const values: DimensionMeasurement[] = editor.dimensions.map((row) => ({
        object: row.object.trim(),
        axis: row.axis.trim() as DimensionAxis,
        value: Number(row.value),
        unit: row.unit.trim() as DimensionUnit,
        source_basis: row.source_basis.trim(),
      }));
      if (!values.length) throw new Error("至少填写一条已确认的测量。");
      return values;
    }
    const raw = editor.text;
    if (slot.value_type === "text_list") {
      const items = splitLines(raw);
      if (!items.length) throw new Error("文本列表至少要有一条。");
      return items;
    }
    if (slot.value_type === "number") {
      const text = String(raw).trim();
      if (!text) throw new Error("请填写数字。");
      const value = Number(text);
      if (!Number.isFinite(value)) throw new Error("请填写合法的数字。");
      return value;
    }
    if (slot.value_type === "boolean") return raw === "true";
    const text = String(raw).trim();
    if (!text) throw new Error("值不能为空。");
    return text;
  }

  /** 事实卡工程标识：折叠的技术详情（结构与 dom.techDetails 一致，但由模板稳定持有）。 */
  function techDetailsTemplate(lines: string[]): TemplateResult | typeof nothing {
    if (!lines.length) return nothing;
    return html`<details class="tech-details"><summary>技术详情</summary>
      <p class="meta tech-body">${lines.join(" · ")}</p></details>`;
  }

  function evidenceTemplate(slot: FactSlot): TemplateResult | typeof nothing {
    const items = Array.isArray(slot.evidence) ? slot.evidence : [];
    if (!items.length) return nothing;
    return html`<ul class="evidence">${items.map((item) => html`<li class="meta">${item.note
      ? ((EVIDENCE_TEXT as Record<string, string>)[item.kind] || item.kind) + "：" + item.note
      : ((EVIDENCE_TEXT as Record<string, string>)[item.kind] || item.kind)}</li>`)}</ul>`;
  }

  function dimensionRowTemplate(index: number): TemplateResult {
    const editor = draft.slot;
    const row = editor ? editor.dimensions[index] : { object: "", axis: "", value: "", unit: "", source_basis: "" };
    const set = (key: keyof DimensionDraft) => (event: Event) => {
      const node = event.currentTarget as HTMLInputElement | HTMLSelectElement;
      if (!draft.slot || !draft.slot.dimensions[index]) return;
      draft.slot.dimensions[index][key] = node.value;
    };
    return html`
      <fieldset class="dimension-row">
        <legend>已确认的测量（不猜数字）</legend>
        <label>测量对象
          <input type="text" data-dimension-field="object" .value=${live(row.object)} @input=${set("object")}></label>
        <label>轴向
          <select data-dimension-field="axis" @change=${set("axis")}>
            <option value="" .selected=${row.axis === ""}>请选择</option>
            ${DIMENSION_AXES.map((value) => html`<option value=${value}
              .selected=${value === row.axis}>${AXIS_LABELS[value] || value}</option>`)}
          </select></label>
        <label>数值
          <input type="number" step="any" min="0" data-dimension-field="value"
            .value=${live(row.value)} @input=${set("value")}></label>
        <label>单位
          <select data-dimension-field="unit" @change=${set("unit")}>
            <option value="" .selected=${row.unit === ""}>请选择</option>
            ${DIMENSION_UNITS.map((value) => html`<option value=${value}
              .selected=${value === row.unit}>${AXIS_LABELS[value] || value}</option>`)}
          </select></label>
        <label>来源依据
          <input type="text" data-dimension-field="source_basis"
            .value=${live(row.source_basis)} @input=${set("source_basis")}></label>
        <button type="button" @click=${() => {
          if (!draft.slot) return;
          draft.slot.dimensions.splice(index, 1);
          renderSlotsCard();
        }}>删除这条测量</button>
      </fieldset>
    `;
  }

  function dimensionEditorTemplate(): TemplateResult {
    const rows = draft.slot ? draft.slot.dimensions : [];
    return html`
      <div class="dimension-editor" id="slot-editor-value" data-role="value">
        <div class="dimension-rows">
          ${repeat(rows, (row, index) => index, (row, index) => dimensionRowTemplate(index))}
        </div>
        <button type="button" ?disabled=${rows.length >= MAX_DIMENSIONS} @click=${() => {
          if (!draft.slot || draft.slot.dimensions.length >= MAX_DIMENSIONS) return;
          draft.slot.dimensions.push({ object: "", axis: "", value: "", unit: "", source_basis: "" });
          renderSlotsCard();
        }}>添加测量</button>
      </div>
    `;
  }

  function slotEditorTemplate(entry: InputSlotEntry, mode: string): TemplateResult {
    const slot = entry.slot;
    const editor = draft.slot;
    const value = editor ? editor.text : "";
    const control = (): TemplateResult | typeof nothing => {
      if (slot.value_type === "dimension_list") return dimensionEditorTemplate();
      if (slot.value_type === "text_list") {
        return html`<textarea id="slot-editor-value" data-role="value" rows="3"
          .value=${live(value)} @input=${slotEditorInput}></textarea>`;
      }
      if (slot.value_type === "boolean") {
        return html`<select id="slot-editor-value" data-role="value" @change=${slotEditorInput}>
          <option value="true" .selected=${value === "true"}>是</option>
          <option value="false" .selected=${value !== "true"}>否</option></select>`;
      }
      if (slot.value_type === "enum") {
        return html`<select id="slot-editor-value" data-role="value" @change=${slotEditorInput}>${(slot.enum_values || []).map((item) =>
          html`<option value=${item} .selected=${item === value}>${item}</option>`)}</select>`;
      }
      return html`<input id="slot-editor-value" data-role="value"
        type=${slot.value_type === "number" ? "number" : "text"}
        step=${slot.value_type === "number" ? "any" : nothing}
        .value=${live(value)} @input=${slotEditorInput}>`;
    };
    return html`
      <div class="slot-editor">
        <div class="field">
          <label for="slot-editor-value">${mode === "confirm" ? "给出裁决值后确认" : "修改后的值"}</label>
          ${control()}
        </div>
        <div class="toolbar">
          <button class="primary" type="button" @click=${() => submitSlotEditor(entry, mode)}>
            ${mode === "confirm" ? "确认" : "保存"}</button>
          <button type="button" @click=${() => { closeSlotEditor(); renderSlotsCard(); }}>取消</button>
        </div>
      </div>
    `;
  }

  function slotEditorInput(event: Event): void {
    const node = event.currentTarget as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
    if (draft.slot) draft.slot.text = node.value;
  }

  function submitSlotEditor(entry: InputSlotEntry, mode: string): void {
    let value: FactSlotValue;
    try {
      value = readSlotEditorValue(entry.slot);
    } catch (error) {
      failRegion("slots", errorMessageOf(error, "值不合法。"));
      return;
    }
    draft.errors.slots = "";
    void handleSlotAction(entry, mode === "confirm"
      ? { action: "confirm", actor: "user", value, source: "user_input" }
      : { action: "edit", actor: "user", value, source: "user_input" });
  }

  function slotActionsTemplate(entry: InputSlotEntry): TemplateResult {
    const slot = entry.slot;
    const editing = Boolean(draft.slot && draft.slot.slotId === slot.slot_id && draft.slot.mode === "edit");
    const direct = slot.status === "proposed";
    return html`
      <div class="slot-actions">
        ${canConfirmSlot(slot, "user") ? html`<button class="primary" type="button"
          @click=${() => {
            if (direct) {
              void handleSlotAction(entry, { action: "confirm", actor: "user" });
            } else {
              openSlotEditor(entry, "confirm");
              renderSlotsCard();
            }
          }}>${direct ? "确认" : "填值并确认"}</button>` : nothing}
        ${canEditValue(slot, "user") ? html`<button type="button" @click=${() => {
          if (editing) closeSlotEditor();
          else openSlotEditor(entry, "edit");
          renderSlotsCard();
        }}>${editing ? "取消修改" : "修改"}</button>` : nothing}
        ${slot.status !== "unknown" && slot.status !== "superseded" ? html`<button type="button"
          @click=${() => void handleSlotAction(entry, { action: "mark_unknown", actor: "user" })}>标记未知</button>` : nothing}
        ${canDeleteSlot(slot, { dependencyCount: dependencyCountOf(slot.slot_id) })
          ? html`<button class="danger" type="button"
            @click=${() => void handleSlotAction(entry, { action: "supersede", actor: "user" })}>删除（保留历史）</button>` : nothing}
      </div>
    `;
  }

  /** 该槽位是否可提议英文上图候选：已确认的文本/文本列表，且有可改写的中文值。 */
  function copyEligible(entry: InputSlotEntry): boolean {
    const slot = entry.slot;
    if (slot.status !== "confirmed") return false;
    if (slot.value_type === "text") {
      return typeof slot.value === "string" && slot.value.trim().length > 0;
    }
    if (slot.value_type === "text_list") {
      return Array.isArray(slot.value) && slot.value.length > 0
        && slot.value.every((item) => typeof item === "string" && item.trim().length > 0);
    }
    return false;
  }

  /**
   * 候选文案区（设计 §13.4.4）：明确点击才外发；提议只是提议，采用=人工把该条英文
   * 写进规格草稿的勾选（仍要保存规格才生效）。来源版本移动后提议标 stale，不可采用。
   */
  function copyProposalTemplate(entry: InputSlotEntry): TemplateResult | typeof nothing {
    if (!copyEligible(entry) && !(draft.copyRows[entry.slot.slot_id] || []).length) return nothing;
    const slot = entry.slot;
    const rows = draft.copyRows[slot.slot_id] || [];
    const running = inputs.isCopyRunning();
    return html`
      <div class="copy-proposals">
        <button type="button" id=${"slot-copy-" + slot.slot_id} ?disabled=${running}
          @click=${() => void handleRunCopy([slot.slot_id])}>提议英文上图候选</button>
        ${rows.map((row, index) => {
          const stale = row.version !== entry.version;
          return html`<div class="copy-row" id=${"slot-copy-result-" + slot.slot_id + "-" + index}>
            <span class="copy-text">${row.text}</span>
            <span class="meta">来源 v${row.version} · ${row.provider}${row.model ? "（" + row.model + "）" : ""}</span>
            ${stale ? html`<span class="meta" id=${"slot-copy-stale-" + slot.slot_id + "-" + index}
              >来源已变化：这条提议已过期，请重新提议。</span>` : nothing}
            <button type="button" id=${"slot-copy-adopt-" + slot.slot_id + "-" + index}
              ?disabled=${stale} @click=${() => adoptCopyRow(slot.slot_id, index)}>采用这条</button>
          </div>`;
        })}
      </div>
    `;
  }

  /**
   * 采用一条候选文案：人工把该条英文写进「所有单图规格草稿」的待选（不直接落库）。
   * 用户仍要在规格区看到该条、勾选并保存规格后才生效；保存走同一 on_image_texts 通道。
   */
  function adoptCopyRow(slotId: string, index: number): void {
    const rows = draft.copyRows[slotId] || [];
    const row = rows[index];
    if (!row) return;
    const entry = inputs.slotEntries().find((item) => item.slot.slot_id === slotId);
    if (!entry || entry.slot.status !== "confirmed" || entry.version !== row.version) return;
    // 采用即人工确认该条英文对应当前确认值：写入各单图草稿的勾选时仍记来源版本，
    // 保存时编译门按同一版本门复核。
    for (const shotId of Object.keys(draft.shotSpecs)) {
      const spec = draft.shotSpecs[shotId];
      if (!spec) continue;
      const existing = spec.selected.find((item) => item.slot_id === slotId && item.version === row.version);
      if (existing) {
        if (!existing.texts.includes(row.text)) existing.texts.push(row.text);
        existing.origin = "model";
      } else {
        // 采用的是模型写的英文候选：来源记 model，保存后交付/恢复都能看出这条不是用户原文。
        spec.selected.push({ slot_id: slotId, texts: [row.text], version: row.version, origin: "model" });
      }
    }
    renderSpecsCard();
  }

  async function handleRunCopy(slotIds: string[]): Promise<void> {
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.slots = "";
    renderSlotsCard();
    const targets = slotIds
      .map((slotId) => inputs.slotEntries().find((item) => item.slot.slot_id === slotId))
      .filter((item): item is InputSlotEntry => Boolean(item) && copyEligible(item as InputSlotEntry))
      .map((item) => ({ slot_id: item.slot.slot_id, version: item.version }));
    if (targets.length === 0) {
      failRegion("slots", "没有可提议的目标：只有已确认的文本类事实才能提议英文上图候选。");
      return;
    }
    try {
      const outcome = await inputs.runCopyProposals(targets);
      if (!action.alive()) return;
      if (outcome.kind === "proposed") {
        for (const proposal of outcome.proposals) {
          const rows = draft.copyRows[proposal.source_slot_id] || [];
          draft.copyRows[proposal.source_slot_id] = [...rows, {
            slot_id: proposal.source_slot_id, version: proposal.source_slot_version,
            text: proposal.text, provider: proposal.provider,
            model: proposal.model, requestedAt: proposal.requestedAt,
          }];
        }
      } else if (outcome.kind === "not_sent" || outcome.kind === "failed" || outcome.kind === "unknown") {
        const message = outcome.kind === "not_sent" ? outcome.message : outcome.error.message;
        failRegion("slots", message);
        return;
      } else if (outcome.kind === "stale") {
        failRegion("slots", "目标事实已变化；旧提议没有展示，请核对后重新提议。");
        return;
      }
      renderSlotsCard();
    } catch (error) {
      if (action.alive()) {
        failRegion("slots", errorMessageOf(error, "提议没有完成，请重试。"));
      }
    }
  }

  function slotRowTemplate(entry: InputSlotEntry): TemplateResult {
    const slot = entry.slot;
    const status = slot.status;
    const valueText = formatValue(slot);
    const emptyHint = status === "conflict"
      ? "模型提案与已确认值不一致；请给出裁决值。"
      : status === "unknown" ? "已标记为未知；需要时再补值确认。"
        : status === "superseded" ? "已移除（历史版本保留）。" : "还没有值。";
    const editing = draft.slot && draft.slot.slotId === slot.slot_id;
    return html`
      <li class="slot-row" data-status=${status} data-slot-id=${slot.slot_id}
        data-critical=${slot.critical === true ? "1" : "0"}>
        <div class="slot-head">
          <span class="badge is-${status}">${(STATUS_TEXT as Record<string, string>)[status] || status}</span>
          <span class="name">${slot.label}</span>
          ${slot.critical === true ? html`<span class="badge is-critical">必须确认</span>` : nothing}
          <span class="meta">${slotMetaText(entry)}</span>
        </div>
        ${valueText
          ? html`<div class="slot-value">${valueText}</div>`
          : html`<div class="slot-value is-empty">${emptyHint}</div>`}
        ${evidenceTemplate(slot)}
        ${editing ? slotEditorTemplate(entry, draft.slot ? draft.slot.mode : "edit") : nothing}
        ${slotActionsTemplate(entry)}
        ${copyProposalTemplate(entry)}
        ${techDetailsTemplate(slotTechLines(entry))}
      </li>
    `;
  }

  function slotsCardTemplate(): TemplateResult {
    const entries = inputs.slotEntries();
    const understandingBlocking = deps.understandingBlocking();
    const critical = entries.filter((entry) => entry.slot.critical === true);
    const confirmedCritical = critical.filter((entry) => entry.slot.status === "confirmed");
    const open = entries.filter(
      (entry) => entry.slot.status !== "confirmed" && entry.slot.status !== "superseded");
    const progress = entries.length
      ? "必须确认的槽位 " + confirmedCritical.length + " / " + critical.length + " 已确认 · 待处理 "
        + open.length + " 项 · 共 " + entries.length + " 项"
        + (understandingBlocking.length
          ? " · 还缺：" + describeBlocking(understandingBlocking, localizeSlotTerms) : "")
      : "还没有槽位。";
    const list = (showAll ? entries : open).slice();
    list.sort((left, right) => {
      const byRank = reviewRankOf(left) - reviewRankOf(right);
      if (byRank !== 0) return byRank;
      return left.slot.slot_id.localeCompare(right.slot.slot_id);
    });
    const copy = inputs.copyState();
    const copyStatus = copy.last.length > 0
      ? "最近一次提议：" + copy.last.length + " 条候选（" + copy.last[0].provider + "）。"
        + (copy.problems.length > 0 ? copy.problems.join("；") : "")
      : (copy.problems.length > 0 ? copy.problems.join("；") : "");
    const eligibleAll = entries.filter(copyEligible).slice(0, 4).map((entry) => entry.slot.slot_id);
    return html`
      <div class="card-head">
        <h4 id="slots-title">事实槽位</h4>
        <p class="meta">模型只能提议；确认、修改、标未知与移除都由你决定，历史版本保留。</p>
      </div>
      <div class="toolbar">
        <span id="slots-progress" class="meta" role="status">${progress}</span>
        <button id="slots-toggle" type="button" aria-expanded=${showAll ? "true" : "false"}
          @click=${() => toggleAllSlots()}>${showAll ? "只看待处理项" : "显示全部事实"}</button>
        <button id="copy-run-all" type="button" ?disabled=${inputs.isCopyRunning() || eligibleAll.length === 0}
          @click=${() => void handleRunCopy(eligibleAll)}>为已确认文本一次提议候选</button>
      </div>
      <p id="copy-status" class="status" role="status" ?hidden=${!copyStatus}>${copyStatus}</p>
      <p id="copy-error" class="error" role="alert" ?hidden=${!copy.error}>${copy.error}</p>
      <p id="slots-empty" class="empty" ?hidden=${entries.length > 0}>正在准备核心事实输入；不需要调用模型。</p>
      <ul id="slot-list" class="slot-list">
        ${repeat(list, (entry) => entry.slot.slot_id, (entry) => slotRowTemplate(entry))}
      </ul>
      <details id="slot-add" class="sub-panel">
        <summary>新增自定义槽位</summary>
        <div class="field">
          <label for="slot-add-id">槽位标识（小写字母开头，2-48 位）</label>
          <input id="slot-add-id" maxlength="48" placeholder="battery_life" autocomplete="off"
            .value=${live(draft.slotAdd.id)} @input=${(event: Event) => {
              draft.slotAdd.id = (event.currentTarget as HTMLInputElement).value;
            }}>
        </div>
        <div class="field">
          <label for="slot-add-label">显示名称</label>
          <input id="slot-add-label" maxlength="60" placeholder="电池续航" autocomplete="off"
            .value=${live(draft.slotAdd.label)} @input=${(event: Event) => {
              draft.slotAdd.label = (event.currentTarget as HTMLInputElement).value;
            }}>
        </div>
        <div class="field">
          <label for="slot-add-type">值类型</label>
          <select id="slot-add-type" @change=${(event: Event) => {
            draft.slotAdd.type = (event.currentTarget as HTMLSelectElement).value;
          }}>${SLOT_ADD_TYPES.map((item) =>
            html`<option value=${item.value} .selected=${item.value === draft.slotAdd.type}>${item.label}</option>`)}</select>
        </div>
        <div class="field">
          <label for="slot-add-value">值</label>
          <textarea id="slot-add-value" rows="2" .value=${live(draft.slotAdd.value)} @input=${(event: Event) => {
            draft.slotAdd.value = (event.currentTarget as HTMLTextAreaElement).value;
          }}></textarea>
        </div>
        <label class="check"><input id="slot-add-allow-model" type="checkbox"
          .checked=${live(draft.slotAdd.allowModel)} @change=${(event: Event) => {
            draft.slotAdd.allowModel = (event.currentTarget as HTMLInputElement).checked;
          }}> 允许模型之后对这个槽位提议</label>
        <div class="toolbar">
          <button id="slot-add-save" type="button" @click=${() => void handleAddSlot()}>新增槽位</button>
          <span id="slot-add-status" class="meta" role="status">${draft.slotAddStatus}</span>
        </div>
      </details>
      <p id="slots-error" class="error" role="alert" ?hidden=${!draft.errors.slots}>${draft.errors.slots}</p>
    `;
  }

  function renderSlotsCard(): void {
    ensureScope();
    if (!slotsHost) return;
    renderLit(slotsCardTemplate(), slotsHost);
  }


  async function handleSlotAction(entry: InputSlotEntry, spec: SlotActionSpec): Promise<void> {
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.slots = "";
    renderSlotsCard();
    try {
      await inputs.slotAction(entry.slot.slot_id, spec);
      if (!action.alive()) return;
      closeSlotEditor();
      await deriveAndApplyState();
      renderAll();
    } catch (error) {
      if (action.alive()) {
        failRegion("slots", errorMessageOf(error, "这个动作没有完成。"));
      }
    }
  }

  async function handleAddSlot(): Promise<void> {
    draft.errors.slots = "";
    draft.slotAddStatus = "";
    renderSlotsCard();
    const slotId = draft.slotAdd.id.trim().toLowerCase();
    const label = draft.slotAdd.label.trim();
    const rawType = draft.slotAdd.type;
    const rawValue = draft.slotAdd.value;
    if (!(SLOT_VALUE_TYPES as readonly string[]).includes(rawType)) {
      failRegion("slots", "值类型不在支持列表内。");
      return;
    }
    const valueType = rawType as SlotValueType;
    let value: FactSlotValue;
    try {
      if (valueType === "text_list") {
        value = splitLines(rawValue);
        if (!value.length) throw new Error("文本列表至少要有一条。");
      } else if (valueType === "number") {
        value = Number(String(rawValue).trim());
        if (!Number.isFinite(value)) throw new Error("请填写合法的数字。");
      } else if (valueType === "boolean") {
        const text = String(rawValue).trim().toLowerCase();
        value = text === "是" || text === "true" || text === "1";
      } else {
        value = String(rawValue).trim();
        if (!value) throw new Error("值不能为空。");
      }
    } catch (error) {
      failRegion("slots", errorMessageOf(error, "值不合法。"));
      return;
    }
    const candidate: FactSlot = {
      schema_version: FACT_SLOT_SCHEMA_VERSION,
      slot_id: slotId,
      label,
      authority: "user_custom",
      value_type: valueType,
      value,
      source: "user_input",
      status: "confirmed",
      confidence: null,
      evidence: [{ kind: "user", ref: "user_input" }],
      depends_on: [],
      critical: false,
      allow_model_proposal: draft.slotAdd.allowModel,
    };
    const problems = checkFactSlot(candidate);
    if (problems.length) {
      failRegion("slots", problems.map((item) => item.message).join("；"));
      return;
    }
    if (!canAddSlot(candidate, "user", { existingSlots: inputs.slotEntries().map((item) => item.slot) })) {
      failRegion("slots", "槽位标识已存在，或这个槽位不允许新增。");
      return;
    }
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    try {
      await inputs.addCustomSlot(candidate);
      if (!action.alive()) return;
      draft.slotAdd.id = "";
      draft.slotAdd.label = "";
      draft.slotAdd.value = "";
      draft.slotAdd.allowModel = false;
      draft.slotAddStatus = "已新增 " + candidate.slot_id;
      await deriveAndApplyState();
      renderAll();
    } catch (error) {
      if (action.alive()) {
        failRegion("slots", errorMessageOf(error, "新增槽位失败。"));
      }
    }
  }

  /* ------------------------------------------------------------ 图片任务 */

  function templateHintText(recommendation: PlanRecommendation): string {
    const instance = recommendation.instances
      .find((item) => item.template_id === draft.templateId);
    if (!instance) return "";
    return instance.satisfied
      ? "该模板依据已满足。"
      : "该模板暂时缺依据：" + suiteBlockingText(instance.blocking);
  }

  function bindingValuesOf(shotId: string, planned: string[]): string[] {
    const binding = draft.bindings[shotId];
    if (!binding) {
      draft.bindings[shotId] = { values: [...planned], baseline: [...planned] };
      return draft.bindings[shotId].values;
    }
    return binding.values;
  }

  function shotRowTemplate(
    item: SuitePlanSummary["shots"][number], index: number, plan: SuitePlan, total: number,
  ): TemplateResult | typeof nothing {
    const shotId = item.shot_id;
    if (typeof shotId !== "string") return nothing;
    const planned = plan.shots.find((shot) => shot.shot_id === shotId);
    if (!planned) return nothing;
    const readiness = shotReadiness(planned, inputs.suiteContext());
    const slotById = new Map(inputs.slotEntries().map((entry) => [entry.slot.slot_id, entry.slot]));
    const values = bindingValuesOf(shotId, Array.isArray(planned.fact_slot_ids) ? planned.fact_slot_ids : []);
    const confirmedEntries = inputs.slotEntries().filter((entry) => entry.slot.status === "confirmed");
    const roleText = item.role_label || item.role_id;
    return html`
      <li class="shot-row" data-shot-id=${shotId} data-blocked=${String(!item.satisfied)}>
        <div class="shot-head">
          <span class="badge">${String(index + 1)}</span>
          <span class="name">${item.label}</span>
          ${!item.custom && roleText && !String(item.label).startsWith(roleText)
            ? html`<span class="meta">${roleText}</span>` : nothing}
          <span class="badge ${item.required ? "is-critical" : ""}">${item.required ? "必需" : (item.custom ? "自定义" : "可选")}</span>
        </div>
        <p class="meta">${item.satisfied ? "依据已满足。" : "暂时缺依据：" + suiteBlockingText(item.blocking)}</p>
        ${readiness.missing_fact_ids.length || readiness.missing_asset_roles.length
          ? html`<div class="shot-fixes">${readiness.missing_fact_ids.map((slotId) => {
            const definition = coreSlotDefinition(slotId);
            return html`<button type="button" @click=${() => {
              showAll = true;
              openSlotEditor(requiredSlotEntry(slotId), "edit");
              if (!definition && !slotById.has(slotId)) {
                draft.slotAdd.id = slotId;
                draft.slotAdd.label = slotId;
              }
              selectStage("understand");
              renderSlotsCard();
            }}>填写／确认：${(slotById.get(slotId)?.label) || (definition?.label) || slotId}</button>`;
          })}${readiness.missing_asset_roles.map((role) => html`<button type="button"
            @click=${() => selectStage("intake")}>补参考图：${(ROLE_TEXT as Record<string, string>)[role] || role}</button>`)}
          </div>` : nothing}
        <details class="shot-bindings">
          <summary>绑定这张图使用的已确认事实</summary>
          ${confirmedEntries.map((entry) => html`<label class="choice">
            <input type="checkbox" value=${entry.slot.slot_id}
              .checked=${live(values.includes(entry.slot.slot_id))} @change=${(event: Event) => {
                const node = event.currentTarget as HTMLInputElement;
                const binding = draft.bindings[shotId];
                if (!binding) return;
                binding.values = node.checked
                  ? [...binding.values, node.value]
                  : binding.values.filter((id) => id !== node.value);
              }}>${entry.slot.label}</label>`)}
          ${confirmedEntries.length === 0
            ? html`<p class="meta">先确认需要使用的事实；不从未确认提案猜文案或尺寸。</p>` : nothing}
          <button type="button" ?disabled=${confirmedEntries.length === 0}
            @click=${() => void applyShotBindings(shotId, plan)}>保存本图事实绑定</button>
        </details>
        <div class="shot-actions">
          <button type="button" ?disabled=${index === 0}
            @click=${() => void handleSuiteOp(() => moveShot(plan, shotId, -1))}>上移</button>
          <button type="button" ?disabled=${index === total - 1}
            @click=${() => void handleSuiteOp(() => moveShot(plan, shotId, 1))}>下移</button>
          <button type="button" @click=${() => void handleSuiteOp(() => copyShot(plan, shotId))}>复制</button>
          <button class="danger" type="button"
            @click=${() => void handleSuiteOp(() => removeShot(plan, shotId))}>删除</button>
        </div>
      </li>
    `;
  }

  /** 缺依据槽位可能还没落到事实表里：用占位 entry 打开编辑器，用户可在同屏补值。 */
  function requiredSlotEntry(slotId: string): InputSlotEntry {
    for (const entry of inputs.slotEntries()) {
      if (entry.slot.slot_id === slotId) return entry;
    }
    const definition = coreSlotDefinition(slotId);
    return {
      version: 0,
      slot: {
        schema_version: FACT_SLOT_SCHEMA_VERSION,
        slot_id: slotId,
        label: (definition && definition.label) || slotId,
        authority: "user_custom",
        value_type: (definition && definition.value_type) || "text",
        value: null,
        source: "user_input",
        status: "missing",
        confidence: null,
        evidence: [],
        depends_on: [],
        critical: false,
        allow_model_proposal: true,
      },
    };
  }

  async function applyShotBindings(shotId: string, plan: SuitePlan): Promise<void> {
    const binding = draft.bindings[shotId];
    const ids = binding ? [...binding.values] : [];
    await handleSuiteOp(() => setShotFactBindings(plan, shotId, ids));
  }

  function suiteCardTemplate(): TemplateResult {
    const recommendation = recommendPlan(inputs.suiteContext());
    const plan = inputs.suitePlan();
    const summary = plan ? (suitePlanSummary(plan, inputs.suiteContext()) as SuitePlanSummary) : null;
    const status = summary
      ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张"
        + (summary.blocked ? "；" + summary.blocked + " 张缺依据" : "")
      : "还没有套图方案。";
    return html`
      <div class="card-head">
        <h4 id="suite-title">图片任务</h4>
        <p class="meta">至少保留一张必需图；每张图显示依据是否已满足。</p>
      </div>
      <p id="suite-locked" class="empty" hidden>完成商品理解（关键事实全部确认）后才能编辑套图规划。</p>
      <div id="suite-editor">
        <div class="toolbar">
          <button id="suite-seed" class="primary" type="button" @click=${() => void seedSuite()}>生成推荐方案</button>
          <label class="visually-hidden" for="suite-template">图片模板</label>
          <select id="suite-template" @change=${(event: Event) => {
            draft.templateId = (event.currentTarget as HTMLSelectElement).value;
            renderSuiteCard();
          }}>${SHOT_TEMPLATES.map((template) =>
            html`<option value=${template.template_id}
              .selected=${template.template_id === draft.templateId}>${template.label}</option>`)}</select>
          <button id="suite-add-template" type="button" @click=${() => void addTemplateShot()}>添加模板图</button>
        </div>
        <p id="suite-template-hint" class="meta">${templateHintText(recommendation)}</p>
        <div class="toolbar secondary">
          <button id="suite-custom-toggle" type="button"
            aria-expanded=${draft.customPanelOpen ? "true" : "false"}
            @click=${() => toggleCustomPanel()}>添加自定义图</button>
          <span id="suite-status" class="meta" role="status">${status}</span>
        </div>
        <div id="suite-custom-panel" class="sub-panel" ?hidden=${!draft.customPanelOpen}>
          <div class="field">
            <label for="suite-custom-label">名称（必填）</label>
            <input id="suite-custom-label" maxlength="60" autocomplete="off" placeholder="例如：赠品特写"
              .value=${live(draft.customShot.label)} @input=${(event: Event) => {
                draft.customShot.label = (event.currentTarget as HTMLInputElement).value;
              }}>
          </div>
          <div class="field">
            <label for="suite-custom-intent">用途（可选）</label>
            <input id="suite-custom-intent" maxlength="200" autocomplete="off"
              .value=${live(draft.customShot.intent)} @input=${(event: Event) => {
                draft.customShot.intent = (event.currentTarget as HTMLInputElement).value;
              }}>
          </div>
          <div class="toolbar">
            <button id="suite-custom-save" type="button" @click=${() => void handleSuiteAddCustom()}>添加</button>
            <span id="suite-custom-status" class="meta" role="status">${draft.customShotStatus}</span>
          </div>
        </div>
        <p id="suite-empty" class="empty" ?hidden=${Boolean(summary)}>还没有套图方案：点“生成推荐方案”，或从模板 / 自定义添加。</p>
        <ol id="shot-list" class="shot-list">${summary && plan
          ? repeat(summary.shots, (item, index) => String(item.shot_id || ("shot-" + index)),
            (item, index) => shotRowTemplate(item, index, plan, summary.shots.length))
          : nothing}</ol>
      </div>
      <p id="suite-error" class="error" role="alert" ?hidden=${!draft.errors.suite}>${draft.errors.suite}</p>
    `;
  }

  function renderSuiteCard(): void {
    ensureScope();
    if (!suiteHost) return;
    renderLit(suiteCardTemplate(), suiteHost);
  }


  /**
   * 套图命令的统一出口：领域纯函数只产生新计划，落库与版本推进归 inputs.applySuiteOp。
   */
  async function handleSuiteOp(run: () => unknown): Promise<boolean> {
    if (!deps.currentProjectId()) return false;
    draft.errors.suite = "";
    renderSuiteCard();
    try {
      const ok = await inputs.applySuiteOp(run as unknown as SuiteOpRunner);
      if (!ok) return false;
      syncShotDrafts();
      renderSuiteCard();
      renderSpecsCard();
      deps.renderGenerationSections();
      await deriveAndApplyState();
      return true;
    } catch (error) {
      const action = beginAction();
      if (action.alive()) {
        failRegion("suite", errorMessageOf(error, "操作没有完成，请重试。"));
      }
      return false;
    }
  }

  async function handleSuiteAddCustom(): Promise<void> {
    const label = draft.customShot.label.trim();
    const intent = draft.customShot.intent.trim();
    const plan = inputs.suitePlan();
    if (!plan) return;
    const ok = await handleSuiteOp(() => addCustomShotToPlan(plan, { label, intent }));
    if (ok) {
      draft.customShot.label = "";
      draft.customShot.intent = "";
      draft.customShotStatus = "已添加。";
      renderSuiteCard();
    }
  }

  /* ------------------------------------------------------------ 风格与规格 */

  function stylePayloadFromDraft(): StyleSpec {
    const next: StyleSpec = {
      ...emptyStyleSpec(),
      background: draft.style.background.trim(),
      lighting: draft.style.lighting.trim(),
      color_tone: draft.style.color_tone.trim(),
      composition: draft.style.composition.trim(),
      avoid: splitLines(draft.style.avoid),
    };
    // 只写用户明确选中的键；没选中的键保持缺失（=未决定），不写 "undecided" 占位。
    const appearance = draft.style.appearance_state.trim();
    const contents = draft.style.contents_state.trim();
    const appearanceOk = appearance === "as_shown" || appearance === "clean_display";
    const contentsOk = contents === "as_shown" || contents === "empty" || contents === "not_applicable";
    if (appearanceOk || contentsOk) {
      next.presentation = {
        ...(appearanceOk ? { appearance_state: appearance as "as_shown" | "clean_display" } : {}),
        ...(contentsOk ? { contents_state: contents as "as_shown" | "empty" | "not_applicable" } : {}),
      };
    }
    return next;
  }
  /* ---------------- 普通决定（#9）：展示/印字/版面 —— 判断与词表归 domain/specs.js，界面只读 */

  /** 是否至少一张图消费该展示决定键（不消费则不问、不显示）。 */
  function presentationKeyAsked(plan: SuitePlan, key: string): boolean {
    if (!isPlainObject(PRESENTATION_CONSUMERS) || !(key in PRESENTATION_CONSUMERS)) return false;
    const consumers = PRESENTATION_CONSUMERS[key as keyof typeof PRESENTATION_CONSUMERS];
    if (!Array.isArray(consumers)) return false;
    return plan.shots.some((shot) => (consumers as readonly string[]).includes(shot.role_id));
  }

  /**
   * 可印候选：只取已确认且绑到这张图的事实，并把值拆成能逐字上图的最小单元。
   * 文本列表按元素各印一行（旧程序也是这样逐条印的），标量按整值；结构化尺寸这类
   * 还不是图上文字的表示形式，先不提供候选而不是印出「[object Object]」。
   */
  function printableCandidatesOf(shotId: string): {
    entry: InputSlotEntry; texts: string[] }[] {
    const plan = inputs.suitePlan();
    const shot = plan ? plan.shots.find((item) => item.shot_id === shotId) : null;
    const bound = new Set(Array.isArray(shot?.fact_slot_ids) ? shot.fact_slot_ids : []);
    const candidates: { entry: InputSlotEntry; texts: string[] }[] = [];
    for (const entry of inputs.slotEntries()) {
      if (entry.slot.status !== "confirmed" || !bound.has(entry.slot.slot_id)) continue;
      const value: unknown = entry.slot.value;
      let texts: string[] = [];
      if (Array.isArray(value)) {
        texts = value.filter((item) => typeof item === "string" && item.trim().length > 0)
          .map((item) => String(item).trim());
      } else if (typeof value === "string" && value.trim().length > 0) {
        texts = [value.trim()];
      } else if (typeof value === "number" && Number.isFinite(value)) {
        texts = [String(value)];
      }
      if (texts.length === 0) continue;
      candidates.push({ entry: entry, texts: texts });
    }
    return candidates;
  }

  /**
   * 可绑定的结构化尺寸：只取已确认、绑到这张图、值是 dimension_list 的事实，
   * 逐项展开（索引即该版本的稳定位置）。不枚举全局事实，不猜标签与来源分类。
   */
  function measurableCandidatesOf(shotId: string): {
    entry: InputSlotEntry; index: number; measurement: DimensionMeasurement }[] {
    const plan = inputs.suitePlan();
    const shot = plan ? plan.shots.find((item) => item.shot_id === shotId) : null;
    const bound = new Set(Array.isArray(shot?.fact_slot_ids) ? shot.fact_slot_ids : []);
    const candidates: {
      entry: InputSlotEntry; index: number; measurement: DimensionMeasurement }[] = [];
    for (const entry of inputs.slotEntries()) {
      if (entry.slot.status !== "confirmed" || !bound.has(entry.slot.slot_id)) continue;
      if (entry.slot.value_type !== "dimension_list" || !Array.isArray(entry.slot.value)) continue;
      (entry.slot.value as DimensionMeasurement[]).forEach((row, index) => {
        if (!isPlainObject(row)) return;
        candidates.push({ entry: entry, index: index, measurement: row });
      });
    }
    return candidates;
  }

  /**
   * 保存 payload：逐字写用户勾选当时看到的值与版本，不按当前事实重写
   * （来源前进时由编译门要求重新确认）。列表值按元素各成一条。
   * 新写入一律用对象 source（schema2）；不写 flat 来源字段。元素粒度与 text_id 方案与 #18 一致。
   * 测量条目：原文由绑定经 formatMeasurementText 唯一构造逐字生成（不是手填文本），
   * 快照/标签/来源分类随条目保存；缺标签或缺分类的绑定不写入（保存前由界面拦下）。
   * 分组标签：原文为统一来源标签（Nominal/Measured），绑定所选测量项快照。
   */
  function onImageTextsFromDraft(spec: ShotSpecDraft): ShotSpec["on_image_texts"] {
    const items: ShotSpec["on_image_texts"] = [];
    let index = 0;
    for (const item of spec.selected) {
      for (const text of item.texts) {
        index += 1;
        items.push({
          // 稳定条目 id：同一选择重复保存不变（序号按勾选顺序重算）。
          text_id: "t_" + item.slot_id + "_" + String(index),
          text: text,
          source: { kind: "fact_slot", document_id: item.slot_id, version: item.version },
          status: "confirmed",
          // 采用的 AI 候选文案按 model 记来源：这是唯一能区分「模型写的英文」与「用户原文」的地方。
          origin: item.origin === "model" ? "model" : "user",
        });
      }
    }
    for (const pick of spec.measurements) {
      const binding = measurementBindingOf(pick);
      const canonical = binding ? formatMeasurementText(binding) : null;
      if (!binding || !canonical) continue;
      index += 1;
      items.push({
        text_id: "t_" + pick.slot_id + "_" + String(index),
        text: canonical,
        source: { kind: "fact_slot", document_id: pick.slot_id, version: pick.version },
        status: "confirmed",
        origin: "user",
        measurement: binding,
      });
    }
    for (const group of spec.groups) {
      const label = group.source_kind === "nominal" || group.source_kind === "measured"
        ? MEASUREMENT_SOURCE_LABEL[group.source_kind] : "";
      if (!label || group.indices.length === 0
        || group.measurements.length !== group.indices.length) continue;
      index += 1;
      items.push({
        text_id: "t_" + group.slot_id + "_" + String(index),
        text: label,
        source: { kind: "fact_slot", document_id: group.slot_id, version: group.version },
        status: "confirmed",
        origin: "user",
        measurement_source: {
          indices: [...group.indices],
          measurements: group.measurements.map((row) => ({ ...row })),
          source_kind: group.source_kind as "nominal" | "measured",
        },
      });
    }
    return items;
  }
  /** 印字决定 + 候选文案 + 版面（仅印字决定角色）：未决定时不预选任何值。 */
  function printDecisionTemplate(shotId: string, spec: ShotSpecDraft): TemplateResult {
    const candidates = printableCandidatesOf(shotId);
    const decided = spec.print_intent === "none" || spec.print_intent === "selected";
    const showTexts = spec.print_intent === "selected";
    const wanted = new Map(spec.selected.map((item) => [item.slot_id, item]));
    // max4 按条目计：plain 文案条数 + 测量绑定条数 + 分组标签条数。
    const selectedCount = spec.selected.reduce((total, item) => total + item.texts.length, 0)
      + spec.measurements.length + spec.groups.length;
    const layouts: readonly string[] = SHOT_LAYOUTS;
    // 已勾选但来源槽位已经不在这张图的绑定里的条目：界面上必须仍然可见、可移除，
    // 否则用户看不见「还在印的文案」，编译门也只会给出一条指不到控件的消息。
    const boundSlotIds = new Set(candidates.map((item) => item.entry.slot.slot_id));
    const orphans = spec.selected.filter((item) => !boundSlotIds.has(item.slot_id));
    const textWillPrint = spec.print_intent === "selected"
      && (spec.selected.length > 0 || spec.measurements.length > 0 || spec.groups.length > 0);
    const layoutNeedsText = TEXT_LAYOUTS.includes(spec.layout) && !textWillPrint;
    return html`
      <div class="field" id=${"spec-print-" + shotId} role="radiogroup" aria-label="要不要在图上印文字">
        <span class="label">要不要在图上印文字</span>
        <label class="choice"><input type="radio" name=${"spec-print-" + shotId}
          id=${"spec-print-none-" + shotId} value="none"
          .checked=${live(spec.print_intent === "none")}
          @change=${shotDecisionInput(shotId, "print_intent", "none")}>${printIntentLabelOf("none")}</label>
        <label class="choice"><input type="radio" name=${"spec-print-" + shotId}
          id=${"spec-print-selected-" + shotId} value="selected"
          .checked=${live(spec.print_intent === "selected")}
          @change=${shotDecisionInput(shotId, "print_intent", "selected")}>${printIntentLabelOf("selected")}</label>
        ${decided ? nothing : html`<p class="meta" id=${"spec-print-undecided-" + shotId}>还没决定：选一个，保存后才生效。</p>`}
      </div>
      ${showTexts ? html`
        <div class="field" id=${"spec-texts-" + shotId}>
          <span class="label">所选文案（逐字印上图，最多 ${MAX_ON_IMAGE_TEXTS} 条）</span>
          ${candidates.map(({ entry, texts }) => {
            const captured: SelectedText | undefined = wanted.get(entry.slot.slot_id);
            const currentText = texts.join("；");
            // 两种情况必须分开说：来源版本前进（旧版，需按新值重新确认）与
            // 采用了 AI 候选文案（同一版本、文案就是模型写的那条；重勾会把英文换成事实原文）。
            const advanced: SelectedText | null = captured && captured.version !== entry.version
              ? captured : null;
            const adopted: SelectedText | null = captured && captured.version === entry.version
              && captured.texts.join("；") !== currentText ? captured : null;
            return html`<label class="choice">
              <input type="checkbox" id=${"spec-text-" + shotId + "-" + entry.slot.slot_id}
                value=${entry.slot.slot_id}
                .checked=${live(Boolean(captured))}
                ?disabled=${!captured && selectedCount + texts.length > MAX_ON_IMAGE_TEXTS}
                @change=${shotTextToggle(shotId, entry)}>
              <span>${entry.slot.label}：${currentText}</span>
              ${advanced ? html`<span class="meta" id=${"spec-text-advanced-" + shotId + "-" + entry.slot.slot_id}
                >已选的是旧版「${advanced.texts.join("；")}」（v${advanced.version}），
                当前事实已是 v${entry.version}：重新勾选这条即按新值重新确认。</span>` : nothing}
              ${adopted ? html`<span class="meta" id=${"spec-text-adopted-" + shotId + "-" + entry.slot.slot_id}
                >已采用候选文案「${adopted.texts.join("；")}」（来源 v${adopted.version}）：保存后按这条逐字印上图；
                勾掉即不印这条。</span>` : nothing}
            </label>`;
          })}
          ${orphans.map((item) => html`<label class="choice">
            <input type="checkbox" id=${"spec-text-orphan-" + shotId + "-" + item.slot_id}
              value=${item.slot_id} .checked=${live(true)}
              @change=${shotOrphanToggle(shotId, item.slot_id)}>
            <span>${slotLabelOfId(item.slot_id)}：${item.texts.join("；")}</span>
            <span class="meta" id=${"spec-text-unbound-" + shotId + "-" + item.slot_id}
              >来源已不在这张图的绑定里：勾掉即移除这条文案，或先把它重新绑定到这张图（编译会拦下未解除的条目）。</span>
          </label>`)}
          ${candidates.length === 0 && orphans.length === 0
            ? html`<p class="meta">这张图还没有绑定可印的已确认事实：先去「图片任务」里绑定；文字类事实才能上图。</p>` : nothing}
        </div>
        ${measurementBindingTemplate(shotId, spec, selectedCount)}` : nothing}
      <div class="field" id=${"spec-layout-" + shotId} role="radiogroup" aria-label="版面">
        <span class="label">版面</span>
        ${layouts.map((layout) => html`<label class="choice"><input type="radio"
          name=${"spec-layout-" + shotId} id=${"spec-layout-" + shotId + "-" + layout} value=${layout}
          .checked=${live(spec.layout === layout)}
          @change=${shotDecisionInput(shotId, "layout", layout)}>${layoutLabelOf(layout)}</label>`)}
        ${layoutNeedsText
          ? html`<p class="meta" id=${"spec-layout-needs-text-" + shotId}
            >选了文字版面，但这张图现在没有要印的文案：编译会被拦，请改成「${layoutLabelOf("product_only")}」，
            或回到上面勾选要印的文案。</p>` : nothing}
        ${spec.layout ? nothing : html`<p class="meta">还没决定：选一个版面，保存后才生效。</p>`}
      </div>
    `;
  }

  /**
   * 结构化尺寸绑定（设计 §13.13.1/§13.14.4）：每项=勾选该版本该索引的测量 +
   * 人工填写英文对象/轴向标签 + 人工对照 source_basis 确认来源分类。
   * 数字/单位/对象/轴向/source_basis 只从来源值抄快照展示，界面不提供手填数字的控件；
   * 上图原文由 formatMeasurementText 唯一构造预览，保存写同一构造的逐字结果。
   * 分组标签：同一事实内已选绑定全同分类时可加一条统一标签（Nominal/Measured 各占一条 max4 名额）。
   */
  function measurementBindingTemplate(
    shotId: string, spec: ShotSpecDraft, selectedCount: number,
  ): TemplateResult {
    const rows = measurableCandidatesOf(shotId);
    const pickKey = (slotId: string, version: number, index: number): string =>
      slotId + "\u0000" + version + "\u0000" + index;
    const picks = new Map(spec.measurements.map((item) => [pickKey(item.slot_id, item.version, item.index), item]));
    const stalePicks = spec.measurements.filter((item) => {
      const entry = inputs.slotEntries().find((row) => row.slot.slot_id === item.slot_id);
      if (!entry || entry.slot.status !== "confirmed" || entry.version !== item.version) return true;
      const list = Array.isArray(entry.slot.value) ? entry.slot.value : [];
      const current = list[item.index] as DimensionMeasurement | undefined;
      return !current || !isPlainObject(current)
        || current.object !== item.object || current.axis !== item.axis
        || current.value !== item.value || current.unit !== item.unit
        || current.source_basis !== item.source_basis;
    });
    return html`
      <div class="field" id=${"spec-measurements-" + shotId}>
        <span class="label">尺寸标注（逐项绑定已确认的结构化尺寸，每项各占一条文案名额）</span>
        ${rows.map(({ entry, index, measurement }) => {
          const key = pickKey(entry.slot.slot_id, entry.version, index);
          const pick = picks.get(key);
          const rowId = "spec-measure-" + shotId + "-" + entry.slot.slot_id + "-" + index;
          const binding = pick ? measurementBindingOf(pick) : null;
          const preview = binding ? formatMeasurementText(binding) : null;
          const capped = !pick && selectedCount >= MAX_ON_IMAGE_TEXTS;
          return html`<fieldset class="measurement-row" id=${rowId}>
            <legend>${entry.slot.label} · 第 ${index + 1} 项（来源 v${entry.version}）</legend>
            <p class="meta">来源值：${measurement.object} / ${measurement.axis} /
              ${String(measurement.value)} ${measurement.unit}（依据：${measurement.source_basis}）</p>
            <label class="choice"><input type="checkbox" id=${rowId + "-pick"}
              .checked=${live(Boolean(pick))} ?disabled=${capped}
              @change=${measurementPickToggle(shotId, entry, index)}>
              标注这一项</label>
            ${pick ? html`
              <label>对象英文标签（人工确认）<input type="text" id=${rowId + "-object"}
                maxlength="60" .value=${live(pick.object_label)}
                @input=${measurementPickInput(shotId, pick, "object_label")}></label>
              <label>轴向英文标签（人工确认，必填）<input type="text" id=${rowId + "-axis"}
                maxlength="60" .value=${live(pick.axis_label)}
                @input=${measurementPickInput(shotId, pick, "axis_label")}></label>
              <div role="radiogroup" aria-label="来源分类（对照上面来源依据确认）">
                <span class="label">来源分类（对照上面来源依据确认，必选）</span>
                <label class="choice"><input type="radio" name=${rowId + "-kind"}
                  id=${rowId + "-nominal"} value="nominal"
                  .checked=${live(pick.source_kind === "nominal")}
                  @change=${measurementPickInput(shotId, pick, "source_kind")}>公称（Nominal）</label>
                <label class="choice"><input type="radio" name=${rowId + "-kind"}
                  id=${rowId + "-measured"} value="measured"
                  .checked=${live(pick.source_kind === "measured")}
                  @change=${measurementPickInput(shotId, pick, "source_kind")}>实测（Measured）</label>
              </div>
              ${preview ? html`<p class="meta" id=${rowId + "-preview"}>上图原文：${preview}</p>`
                : html`<p class="meta" id=${rowId + "-preview"}
                  >标签/分类还没填完：补齐后才能保存这条（不会用半成品保存）。</p>`}` : nothing}
          </fieldset>`;
        })}
        ${rows.length === 0 ? html`<p class="meta">这张图没有绑定已确认的结构化尺寸：
          尺寸图先去「图片任务」里绑定尺寸事实。</p>` : nothing}
        ${stalePicks.map((item) => html`<p class="meta"
          id=${"spec-measure-stale-" + shotId + "-" + item.slot_id + "-" + item.index}
          >「${slotLabelOfId(item.slot_id)}」第 ${item.index + 1} 项的来源已变化（绑定的是 v${item.version}）：
          请取消该绑定后按新值重新确认；保存时会拦下过期绑定。</p>`)}
        ${measurementGroupTemplate(shotId, spec, selectedCount)}
      </div>
    `;
  }

  /**
   * 分组来源标签：同一事实内「已选且分类一致」的绑定可共用一条统一标签。
   * 混合来源不提供统一标签（须逐项标注）；分组快照在勾选时从来源值逐项抄写。
   */
  function measurementGroupTemplate(
    shotId: string, spec: ShotSpecDraft, selectedCount: number,
  ): TemplateResult | typeof nothing {
    const bySlot = new Map<string, MeasurementPick[]>();
    for (const pick of spec.measurements) {
      const list = bySlot.get(pick.slot_id) || [];
      list.push(pick);
      bySlot.set(pick.slot_id, list);
    }
    const options: { slot_id: string; version: number; kind: MeasurementSourceKind; picks: MeasurementPick[] }[] = [];
    for (const [slotId, list] of bySlot) {
      const kinds = new Set(list.map((item) => item.source_kind));
      if (kinds.size !== 1) continue;
      const kind = list[0].source_kind;
      if (kind !== "nominal" && kind !== "measured") continue;
      const versions = new Set(list.map((item) => item.version));
      if (versions.size !== 1) continue;
      // 统一标签只在各项绑定都确认完整时提供：半成品不能借分组绕开逐项确认。
      if (!list.every((item) => measurementBindingOf(item) !== null)) continue;
      options.push({ slot_id: slotId, version: list[0].version, kind, picks: list });
    }
    if (options.length === 0) return nothing;
    return html`
      <div class="field" id=${"spec-measure-groups-" + shotId}>
        <span class="label">统一来源标签（可选：所选测量全同分类时可加一条，各占一条文案名额）</span>
        ${options.map((option) => {
          const rowId = "spec-group-" + shotId + "-" + option.slot_id;
          const existing = spec.groups.find((item) => item.slot_id === option.slot_id
            && item.version === option.version);
          const capped = !existing && selectedCount >= MAX_ON_IMAGE_TEXTS;
          const label = MEASUREMENT_SOURCE_LABEL[option.kind];
          return html`<label class="choice"><input type="checkbox" id=${rowId}
            .checked=${live(Boolean(existing))} ?disabled=${capped}
            @change=${measurementGroupToggle(shotId, option)}>${slotLabelOfId(option.slot_id)}：
            ${option.picks.length} 项全为${option.kind === "measured" ? "实测" : "公称"}，
            加一条统一标签「${label}」</label>`;
        })}
      </div>
    `;
  }

  function measurementPickToggle(
    shotId: string, entry: InputSlotEntry, index: number,
  ): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      const list = Array.isArray(entry.slot.value) ? entry.slot.value : [];
      const current = list[index] as DimensionMeasurement | undefined;
      if (node.checked) {
        // 勾选=按当前确认值抄快照：数字/单位/对象/轴向/依据逐字抄，不手填；
        // 标签与分类留空，必须人工逐项确认后才能保存。
        if (!current || !isPlainObject(current) || typeof current.value !== "number") return;
        if (spec.measurements.some((item) => item.slot_id === entry.slot.slot_id
          && item.version === entry.version && item.index === index)) return;
        spec.measurements.push({
          slot_id: entry.slot.slot_id, version: entry.version, index,
          object: typeof current.object === "string" ? current.object : "",
          axis: typeof current.axis === "string" ? current.axis : "",
          value: current.value, unit: typeof current.unit === "string" ? current.unit : "",
          source_basis: typeof current.source_basis === "string" ? current.source_basis : "",
          object_label: "", axis_label: "", source_kind: "",
        });
      } else {
        spec.measurements = spec.measurements.filter((item) => !(item.slot_id === entry.slot.slot_id
          && item.version === entry.version && item.index === index));
        // 取消某项绑定后，覆盖它的分组标签一并失效（分组快照不再与所选一致）。
        spec.groups = spec.groups.filter((item) => item.slot_id !== entry.slot.slot_id
          || item.version !== entry.version);
      }
      renderSpecsCard();
    };
  }

  function measurementPickInput(
    shotId: string, pick: MeasurementPick, key: "object_label" | "axis_label" | "source_kind",
  ): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      const live = spec.measurements.find((item) => item.slot_id === pick.slot_id
        && item.version === pick.version && item.index === pick.index);
      if (!live) return;
      if (key === "source_kind") {
        live.source_kind = node.value === "nominal" || node.value === "measured" ? node.value : "";
      } else {
        live[key] = node.value;
      }
      // 来源分类变化后，已有分组标签可能不再「全同分类」：失效的分组直接移除，
      // 用户确认新的分类组合后可重新勾选统一标签。
      if (key === "source_kind") {
        spec.groups = spec.groups.filter((item) => {
          if (item.slot_id !== live.slot_id || item.version !== live.version) return true;
          const kinds = new Set(spec.measurements
            .filter((row) => row.slot_id === item.slot_id && row.version === item.version)
            .map((row) => row.source_kind));
          return kinds.size === 1 && kinds.has(item.source_kind);
        });
        renderSpecsCard();
      }
    };
  }

  function measurementGroupToggle(
    shotId: string, option: { slot_id: string; version: number; kind: MeasurementSourceKind; picks: MeasurementPick[] },
  ): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      if (node.checked) {
        if (spec.groups.some((item) => item.slot_id === option.slot_id
          && item.version === option.version)) return;
        // 分组快照=各绑定当时的来源快照（逐项抄，不按当前事实重取）；
        // 索引排序，保证同一选择重复保存的快照顺序一致。
        const ordered = [...option.picks].sort((left, right) => left.index - right.index);
        const measurements: DimensionMeasurement[] = [];
        for (const item of ordered) {
          const binding = measurementBindingOf(item);
          if (!binding) return;  // 选项只收完整绑定；这里再兜一次，不吞半成品。
          measurements.push({
            object: binding.object, axis: binding.axis, value: binding.value,
            unit: binding.unit, source_basis: binding.source_basis,
          });
        }
        spec.groups.push({
          slot_id: option.slot_id, version: option.version,
          indices: ordered.map((item) => item.index),
          measurements: measurements,
          source_kind: option.kind,
        });
      } else {
        spec.groups = spec.groups.filter((item) => !(item.slot_id === option.slot_id
          && item.version === option.version));
      }
      renderSpecsCard();
    };
  }

  function shotDecisionInput(shotId: string, key: "print_intent" | "layout", value: string): (event: Event) => void {
    return () => {
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      spec[key] = value;
      renderSpecsCard();
    };
  }

  /** 移除一条「来源已解绑」的文案：勾掉即从草稿里删掉该槽位的全部条目。 */
  function shotOrphanToggle(shotId: string, slotId: string): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec || node.checked) return;
      spec.selected = spec.selected.filter((item) => item.slot_id !== slotId);
      renderSpecsCard();
    };
  }

  function shotTextToggle(shotId: string, entry: InputSlotEntry): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      if (node.checked) {
        if (!spec.selected.some((item) => item.slot_id === entry.slot.slot_id)) {
          // 记下用户此刻看到的逐字值（列表按元素）与来源版本：保存写的是这一版，不是「保存那一刻的当前值」。
          const value: unknown = entry.slot.value;
          const texts = Array.isArray(value)
            ? value.filter((item) => typeof item === "string" && item.trim().length > 0)
              .map((item) => String(item).trim())
            : (typeof value === "string" || typeof value === "number" ? [String(value).trim()] : []);
          if (texts.length === 0) return;
          spec.selected.push({
            slot_id: entry.slot.slot_id, texts: texts, version: entry.version, origin: "user",
          });
        }
      } else {
        spec.selected = spec.selected.filter((item) => item.slot_id !== entry.slot.slot_id);
      }
      renderSpecsCard();
    };
  }



  /**
   * 单图视角覆盖（设计 §13.4.2）：选项走 PRESENTATION_FIELDS 的 viewpoint 定义，不另写词表。
   * 空串=沿用可见视角（不写覆盖）；显式 front/side/top 才在保存时写单图覆盖。
   * 共用区不渲染视角控件（共用默认恒为沿用可见视角）。
   */
  function shotViewpointTemplate(shotId: string, spec: ShotSpecDraft): TemplateResult {
    const field = PRESENTATION_FIELDS.find((item) => item.key === "viewpoint");
    const options = field ? field.options : [];
    return html`
      <div class="field" id=${"spec-presentation-viewpoint-" + shotId}
        role="radiogroup" aria-label="本图视角">
        <span class="label">本图视角</span>
        ${options.map((option) => {
          const selected = option.value === "reference_visible" ? spec.viewpoint === "" : spec.viewpoint === option.value;
          return html`<label class="choice"><input type="radio"
            name=${"spec-viewpoint-" + shotId} id=${"spec-viewpoint-" + option.value + "-" + shotId}
            value=${option.value} .checked=${live(selected)}
            @change=${shotViewpointInput(shotId, option.value)}>${option.label}
            <span class="meta">${option.hint}</span></label>`;
        })}
        ${spec.viewpoint ? html`<p class="meta">已选单图视角覆盖：需要有能看到该角度的参考图依据（在参考图行确认），
          否则编译会被拦下；改回「沿用照片里能看到的角度」即删除本图覆盖。</p>` : nothing}
      </div>
    `;
  }

  function shotViewpointInput(shotId: string, value: string): (event: Event) => void {
    return () => {
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      // reference_visible = 不写覆盖（草稿归一为空串）；显式视角才记覆盖值。
      spec.viewpoint = value === "reference_visible" ? "" : value;
      renderSpecsCard();
    };
  }

  /**
   * 单图参考选择（设计 §13.6.2）：用户明确本图消费哪几张照片。
   * inherit=沿用角色默认；none=明确不选（编译阻断该图）；select=显式勾选（顺序=勾选顺序）。
   * 说明文本只描述「这张图用哪几张照片」，不出现角色/用途术语。
   */
  function shotReferencesTemplate(shotId: string, spec: ShotSpecDraft): TemplateResult {
    const references = inputs.references();
    const liveShas = new Set(references.map((item) => item.asset_sha256));
    const stale = spec.refs.mode === "select" ? spec.refs.shas.filter((sha) => !liveShas.has(sha)) : [];
    return html`
      <div class="field" id=${"spec-references-" + shotId}>
        <span class="label">本图用的照片</span>
        <label class="choice"><input type="radio" name=${"spec-refs-" + shotId}
          id=${"spec-refs-inherit-" + shotId} value="inherit"
          .checked=${live(spec.refs.mode === "inherit")}
          @change=${shotRefsModeInput(shotId, "inherit")}>沿用默认照片</label>
        <label class="choice"><input type="radio" name=${"spec-refs-" + shotId}
          id=${"spec-refs-none-" + shotId} value="none"
          .checked=${live(spec.refs.mode === "none")}
          @change=${shotRefsModeInput(shotId, "none")}>明确不选（这张图暂不做）</label>
        <label class="choice"><input type="radio" name=${"spec-refs-" + shotId}
          id=${"spec-refs-select-" + shotId} value="select"
          .checked=${live(spec.refs.mode === "select")}
          @change=${shotRefsModeInput(shotId, "select")}>显式勾选需要的照片</label>
        ${spec.refs.mode === "select" ? html`
          <div class="choice-list">
            ${references.map((item, index) => {
              const id = "spec-ref-" + item.asset_sha256.slice(0, 12) + "-" + shotId;
              const checked = spec.refs.shas.includes(item.asset_sha256);
              return html`<label class="choice"><input type="checkbox" id=${id}
                value=${item.asset_sha256} .checked=${live(checked)}
                @change=${shotRefsToggle(shotId, item.asset_sha256)}>第 ${index + 1} 张照片</label>`;
            })}
            ${references.length === 0 ? html`<p class="meta">还没有参考图：先去资料区添加照片。</p>` : nothing}
          </div>` : nothing}
        ${spec.refs.mode === "none" ? html`<p class="meta" id=${"spec-refs-note-" + shotId}
          >已明确不选任何照片：保存后这张图会被拦下，直到重新选择照片。</p>` : nothing}
        ${stale.length > 0 ? html`<p class="meta" id=${"spec-refs-note-" + shotId}
          >选中的 ${stale.length} 张照片已不在项目内：请重新勾选，保存时会复核。</p>` : nothing}
      </div>
    `;
  }

  function shotRefsModeInput(shotId: string, mode: "inherit" | "none" | "select"): (event: Event) => void {
    return () => {
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      spec.refs.mode = mode;
      if (mode !== "select") spec.refs.shas = [];
      renderSpecsCard();
    };
  }

  function shotRefsToggle(shotId: string, sha256: string): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec || spec.refs.mode !== "select") return;
      spec.refs.shas = node.checked
        ? [...spec.refs.shas, sha256]
        : spec.refs.shas.filter((sha) => sha !== sha256);
      renderSpecsCard();
    };
  }

  function shotSpecCardTemplate(
    item: { shot_id: string | null; label: string; checklist: { sections: { label: string; items: string[] }[] } },
    index: number, plan: SuitePlan,
  ): TemplateResult | typeof nothing {
    const shotId = item.shot_id;
    const shot = plan.shots[index];
    if (typeof shotId !== "string" || !shot) return nothing;
    const entry = inputs.shotSpecEntry(shotId);
    const spec = draft.shotSpecs[shotId] || shotSpecDraftFrom(entry ? entry.spec : emptyShotSpecFromShot(shot));
    return html`
      <div class="shot-spec" data-shot-id=${shotId}>
        <div class="shot-spec-head">
          <span class="name">${(index + 1) + ". " + item.label}</span>
          <span class="meta">${entry ? "规格 v" + entry.version : "默认（未保存）"}</span>
        </div>
        <div class="field">
          <label for=${"spec-purpose-" + shotId}>目的</label>
          <input id=${"spec-purpose-" + shotId} maxlength="200" .value=${live(spec.purpose)}
            @input=${shotSpecInput(shotId, "purpose")}>
        </div>
        <div class="field">
          <label for=${"spec-keep-" + shotId}>必须保持（一行一条）</label>
          <textarea id=${"spec-keep-" + shotId} rows="2" .value=${live(spec.keep)}
            @input=${shotSpecInput(shotId, "keep")}></textarea>
        </div>
        <div class="field">
          <label for=${"spec-change-" + shotId}>允许变化（一行一条）</label>
          <textarea id=${"spec-change-" + shotId} rows="2" .value=${live(spec.change_allowed)}
            @input=${shotSpecInput(shotId, "change_allowed")}></textarea>
        </div>
        ${printDecisionRoleOf(shot) ? printDecisionTemplate(shotId, spec) : nothing}
        ${shotViewpointTemplate(shotId, spec)}
        ${shotReferencesTemplate(shotId, spec)}
        <div class="toolbar">
          <button type="button" @click=${() => void handleSaveShotSpec(shotId)}>保存</button>
          <button type="button" ?disabled=${!entry || entry.version <= 1}
            @click=${() => void handleRestoreShotSpec(shotId)}>恢复上一版本</button>
        </div>
        <details class="slot-detail">
          <summary>审核清单</summary>
          <ul class="checklist">${item.checklist.sections.filter((section) => section.items.length > 0)
            .map((section) => html`<li><strong>${section.label}：</strong><span
              class="meta">${section.items.join("；")}</span></li>`)}</ul>
        </details>
      </div>
    `;
  }

  function shotSpecInput(
    shotId: string, key: "purpose" | "keep" | "change_allowed",
  ): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement | HTMLTextAreaElement;
      const spec = draft.shotSpecs[shotId];
      if (!spec) return;
      spec[key] = node.value;
    };
  }

  function specsCardTemplate(): TemplateResult {
    const plan = inputs.suitePlan();
    const ready = Boolean(plan);
    const version = inputs.styleVersion();
    const projection = plan
      ? specChangeProjection("style_changed", { shotCount: plan.shots.length }) : null;
    const digest = plan
      ? suiteSpecDigest(plan, { styleSpec: inputs.styleSpec(), shotSpecsById: inputs.shotSpecsById() })
      : null;
    return html`
      <h4 id="specs-title" class="visually-hidden">风格与单图规格</h4>
      <p id="specs-locked" class="empty" ?hidden=${ready}>完成商品理解并生成套图方案后，才能编辑风格与规格。</p>
      <div id="specs-editor" ?hidden=${!ready}>
        <h5 class="sub-title">公共风格（全部图片）</h5>
        <div class="field">
          <label for="style-background">背景风格</label>
          <input id="style-background" maxlength="200" autocomplete="off" .value=${live(draft.style.background)}
            @input=${styleInput("background")}>
        </div>
        <div class="field">
          <label for="style-lighting">光线</label>
          <input id="style-lighting" maxlength="200" autocomplete="off" .value=${live(draft.style.lighting)}
            @input=${styleInput("lighting")}>
        </div>
        <div class="field">
          <label for="style-color-tone">色调</label>
          <input id="style-color-tone" maxlength="200" autocomplete="off" .value=${live(draft.style.color_tone)}
            @input=${styleInput("color_tone")}>
        </div>
        <div class="field">
          <label for="style-composition">构图约定</label>
          <input id="style-composition" maxlength="200" autocomplete="off" .value=${live(draft.style.composition)}
            @input=${styleInput("composition")}>
        </div>
        <div class="field">
          <label for="style-avoid">避免出现（一行一条）</label>
          <textarea id="style-avoid" rows="2" .value=${live(draft.style.avoid)}
            @input=${styleInput("avoid")}></textarea>
        </div>
        ${plan ? stylePresentationTemplate(plan) : nothing}
        <div class="toolbar">
          <button id="style-save" class="primary" type="button" @click=${() => void handleSaveStyle()}>保存风格</button>
          <button id="style-restore" type="button" ?disabled=${version <= 1}
            @click=${() => void handleRestoreStyle()}>恢复上一版本</button>
          <span id="style-version" class="meta" role="status">${version > 0 ? "版本 v" + version : "尚未保存"}</span>
        </div>
        <p id="style-effect" class="meta">${projection
          ? "保存后影响：" + projection.affects_text + "；失效：" + projection.invalidates_text
            + "；保留：" + projection.preserves_text + "。" : ""}</p>
        <p id="style-status" class="status" role="status" ?hidden=${!draft.styleStatus}>${draft.styleStatus}</p>
        <p id="style-error" class="error" role="alert" ?hidden=${!draft.errors.style}>${draft.errors.style}</p>
        <h5 class="sub-title">单图规格与审核清单</h5>
        <p id="shot-specs-empty" class="empty" ?hidden=${Boolean(plan && plan.shots.length > 0)}>套图方案里还没有图片。</p>
        <div id="shot-spec-list">${digest && plan
          ? repeat(digest.shots, (item, index) => String(item.shot_id || ("spec-" + index)),
            (item, index) => shotSpecCardTemplate(item, index, plan))
          : nothing}</div>
      </div>
      <p id="specs-error" class="error" role="alert" ?hidden=${!draft.errors.specs}>${draft.errors.specs}</p>
    `;
  }
  /** 共用展示决定：选项 label/hint 直接读 PRESENTATION_FIELDS，不另写词表；未选不预选。 */
  function stylePresentationTemplate(plan: SuitePlan): TemplateResult {
    return html`
      <div class="field" id="style-presentation">
        <span class="label">展示决定（全部图片共用）</span>
        ${PRESENTATION_FIELDS.filter((field) => presentationKeyAsked(plan, field.key))
          .map((field) => {
            const key = field.key === "appearance_state" || field.key === "contents_state" ? field.key : null;
            if (!key) return nothing;
            const current = draft.style[key];
            return html`
            <div class="field" id=${"style-presentation-" + key}
              role="radiogroup" aria-label=${field.label}>
              <span class="label">${field.label}</span>
              ${field.options.filter((option) => option.value !== "undecided").map((option) => html`
                <label class="choice"><input type="radio" name=${"style-" + key}
                  id=${"style-" + key + "-" + option.value} value=${option.value}
                  .checked=${live(current === option.value)}
                  @change=${styleDecisionInput(key)}>${option.label}
                  <span class="meta">${option.hint}</span></label>`)}
              ${current ? nothing
                : html`<p class="meta">还没决定：选一个，保存风格后才生效。</p>`}
            </div>`;
          })}
      </div>
    `;
  }

  function styleDecisionInput(key: "appearance_state" | "contents_state"): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement;
      draft.style[key] = node.value;
      renderSpecsCard();
    };
  }


  function styleInput(key: keyof StyleDraft): (event: Event) => void {
    return (event: Event) => {
      const node = event.currentTarget as HTMLInputElement | HTMLTextAreaElement;
      draft.style[key] = node.value;
    };
  }

  function renderSpecsCard(): void {
    ensureScope();
    if (!specsHost) return;
    renderLit(specsCardTemplate(), specsHost);
  }


  async function handleSaveStyle(): Promise<void> {
    const plan = inputs.suitePlan();
    if (!deps.currentProjectId() || !plan) return;
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.style = "";
    draft.styleStatus = "";
    renderSpecsCard();
    try {
      const next = stylePayloadFromDraft();
      const before = inputs.styleSpec();
      const diffs = styleSpecDiff(before, next);
      await inputs.saveStyle(next);
      if (!action.alive()) return;
      renderSpecsCard();
      deps.renderGenerationSections();
      await deriveAndApplyState();
      if (!action.alive()) return;
      draft.styleStatus = "已保存 v" + inputs.styleVersion()
        + (diffs.length > 0
          ? "（改动：" + diffs.map((item) => item.label).join("、") + "）"
          : "（没有字段变化）");
      renderSpecsCard();
    } catch (error) {
      if (action.alive()) {
        failRegion("style", errorMessageOf(error, "保存没有完成，请重试。"));
      }
    }
  }

  async function handleRestoreStyle(): Promise<void> {
    if (!deps.currentProjectId() || inputs.styleVersion() <= 1) return;
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.style = "";
    renderSpecsCard();
    try {
      const before = inputs.styleVersion();
      const restoredVersion = await inputs.restoreStyle();
      if (!action.alive()) return;
      renderSpecsCard();
      deps.renderGenerationSections();
      await deriveAndApplyState();
      if (!action.alive()) return;
      draft.styleStatus = restoredVersion > 0
        ? "已恢复上一版本的内容（v" + before + " → v" + restoredVersion + "）。"
        : "已恢复上一版本的内容。";
      renderSpecsCard();
    } catch (error) {
      if (action.alive()) {
        failRegion("style", errorMessageOf(error, "恢复没有完成，请重试。"));
      }
    }
  }

  /**
   * 测量绑定保存门：逐项复核「标签/分类已确认」与「快照仍等于来源当前值」。
   * 任一失败即抛错（保存中止、草稿保留）；错误指到具体槽位与项序号。
   */
  function assertMeasurementDraftsCurrent(shotId: string, spec: ShotSpecDraft): void {
    void shotId;
    for (const pick of spec.measurements) {
      const where = "「" + slotLabelOfId(pick.slot_id) + "」第 " + (pick.index + 1) + " 项";
      if (pick.axis_label.trim().length === 0) {
        throw new Error(where + "的轴向英文标签还没填：补齐后才能保存。");
      }
      if (pick.source_kind !== "nominal" && pick.source_kind !== "measured") {
        throw new Error(where + "的来源分类还没确认：对照来源依据选择公称或实测后才能保存。");
      }
      const entry = inputs.slotEntries().find((row) => row.slot.slot_id === pick.slot_id);
      const list = entry && Array.isArray(entry.slot.value) ? entry.slot.value : [];
      const current = list[pick.index] as DimensionMeasurement | undefined;
      if (!entry || entry.slot.status !== "confirmed" || entry.version !== pick.version
        || !current || !isPlainObject(current)
        || current.object !== pick.object || current.axis !== pick.axis
        || current.value !== pick.value || current.unit !== pick.unit
        || current.source_basis !== pick.source_basis) {
        throw new Error(where + "的来源已变化（绑定的是 v" + pick.version + "）：请取消后按新值重新确认。");
      }
    }
    for (const group of spec.groups) {
      const where = "「" + slotLabelOfId(group.slot_id) + "」统一标签";
      const covered = spec.measurements.filter((item) => item.slot_id === group.slot_id
        && item.version === group.version);
      const kinds = new Set(covered.map((item) => item.source_kind));
      if (kinds.size !== 1 || !kinds.has(group.source_kind)) {
        throw new Error(where + "已失效（所选测量不再全同分类）：请重新勾选统一标签。");
      }
      const entry = inputs.slotEntries().find((row) => row.slot.slot_id === group.slot_id);
      const list = entry && Array.isArray(entry.slot.value) ? entry.slot.value : [];
      if (!entry || entry.slot.status !== "confirmed" || entry.version !== group.version) {
        throw new Error(where + "的来源已变化（绑定的是 v" + group.version + "）：请重新确认。");
      }
      for (let position = 0; position < group.indices.length; position += 1) {
        const current = list[group.indices[position]] as DimensionMeasurement | undefined;
        const frozen = group.measurements[position];
        if (!current || !frozen || current.object !== frozen.object || current.axis !== frozen.axis
          || current.value !== frozen.value || current.unit !== frozen.unit
          || current.source_basis !== frozen.source_basis) {
          throw new Error(where + "的来源已变化：请重新确认分组。");
        }
      }
    }
  }

  async function handleSaveShotSpec(shotId: string): Promise<void> {
    if (!deps.currentProjectId()) return;
    const spec = draft.shotSpecs[shotId];
    if (!spec) return;
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.specs = "";
    renderSpecsCard();
    try {
      // 新字段与旧字段一次性保存：选了就带上，没选的不写键（不写 "none"/"undecided" 占位，不静默丢已选字段）。
      const entry = inputs.shotSpecEntry(shotId);
      const currentPresentation = entry && isPlainObject(entry.spec.presentation)
        ? { ...(entry.spec.presentation as Record<string, unknown>) } : {};
      const changes: Partial<ShotSpec> = {
        purpose: spec.purpose.trim(),
        keep: splitLines(spec.keep),
        change_allowed: splitLines(spec.change_allowed),
      };
      if (spec.print_intent === "none" || spec.print_intent === "selected") {
        changes.print_intent = spec.print_intent;
      }
      if (spec.layout === "product_only" || spec.layout === "product_left_text_right"
        || spec.layout === "product_right_text_left") changes.layout = spec.layout;
      if (spec.print_intent === "selected") {
        // 测量绑定完整性门：缺轴向标签/缺来源分类/来源过期/快照不一致的绑定不落库，
        // 留在草稿并指到具体条目；绝不静默丢弃半成品绑定。
        assertMeasurementDraftsCurrent(shotId, spec);
        changes.on_image_texts = onImageTextsFromDraft(spec);
      } else if (spec.print_intent === "none") {
        changes.on_image_texts = [];
      }
      // 视角单图覆盖：显式 front/side/top 才写；沿用可见视角=删除该键（回到共用安全默认），
      // 不持久化 "reference_visible" 覆盖。其它已存覆盖键（外观/内容物）原样保留。
      if (spec.viewpoint === "front" || spec.viewpoint === "side" || spec.viewpoint === "top") {
        currentPresentation.viewpoint = spec.viewpoint;
        changes.presentation = currentPresentation as ShotSpec["presentation"];
      } else if ("viewpoint" in currentPresentation) {
        delete currentPresentation.viewpoint;
        changes.presentation = (Object.keys(currentPresentation).length > 0
          ? currentPresentation : undefined) as ShotSpec["presentation"];
      }
      // 参考选择：inherit=删除键（沿用角色默认）；none=显式 []；select=用户所选顺序。
      // 显式选择的 SHA 必须仍在当前项目内，否则留在草稿并报错，不落库、不清空用户勾选。
      const liveShas = new Set(inputs.references().map((item) => item.asset_sha256));
      if (spec.refs.mode === "inherit") {
        if (entry && Object.prototype.hasOwnProperty.call(entry.spec, "reference_sha256s")) {
          changes.reference_sha256s = undefined as unknown as ShotSpec["reference_sha256s"];
          // saveShotSpec 是浅合并：显式删键需要先读后写完整对象，这里走 setShotReferences(null)。
        }
      } else if (spec.refs.mode === "none") {
        changes.reference_sha256s = [];
      } else {
        const missing = spec.refs.shas.filter((sha) => !liveShas.has(sha));
        if (missing.length > 0) {
          throw new Error("选中的 " + missing.length + " 张参考图已不在项目内：请重新勾选本图依据。");
        }
        changes.reference_sha256s = [...spec.refs.shas];
      }
      if (spec.refs.mode === "inherit" && entry
        && Object.prototype.hasOwnProperty.call(entry.spec, "reference_sha256s")) {
        await inputs.setShotReferences(shotId, null);
        const { reference_sha256s: _dropped, ...rest } = changes;
        void _dropped;
        await inputs.saveShotSpec(shotId, rest);
      } else if (spec.refs.mode === "inherit") {
        const { reference_sha256s: _dropped, ...rest } = changes;
        void _dropped;
        await inputs.saveShotSpec(shotId, rest);
      } else {
        await inputs.saveShotSpec(shotId, changes);
      }
      if (!action.alive()) return;
      renderSpecsCard();
      deps.renderGenerationSections();
      await deriveAndApplyState();
    } catch (error) {
      if (action.alive()) {
        // 编译门/owner 的视角/参考/文案报错必须留在规格区可见，不吞掉。
        failRegion("specs", errorMessageOf(error, "保存没有完成，请重试。"));
      }
    }
  }

  async function handleRestoreShotSpec(shotId: string): Promise<void> {
    if (!deps.currentProjectId()) return;
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.specs = "";
    renderSpecsCard();
    try {
      await inputs.restoreShotSpec(shotId);
      if (!action.alive()) return;
      renderSpecsCard();
      deps.renderGenerationSections();
      await deriveAndApplyState();
    } catch (error) {
      if (action.alive()) {
        failRegion("specs", errorMessageOf(error, "恢复没有完成，请重试。"));
      }
    }
  }

  /* ------------------------------------------------------------ 参考图 */

  /**
   * 参考图行：先异步取齐资产，最后一次提交；重叠调用只保留最后一次，
   * 上次的 object URL 在同一提交点统一撤销（行节点因此始终是同一份投影）。
   */
  async function renderReferences(): Promise<void> {
    const pid = deps.currentProjectId();
    if (!pid) return;
    const token = ++referenceToken;
    const entries = inputs.references();
    const created: string[] = [];
    const rows: ReferenceRow[] = [];
    try {
      for (const [index, entry] of entries.entries()) {
        const asset = storedAssetShape(await deps.readAsset(pid, entry.asset_sha256));
        if (token !== referenceToken) {
          for (const url of created) URL.revokeObjectURL(url);
          return;
        }
        const url = asset.blob ? URL.createObjectURL(asset.blob) : null;
        if (url) created.push(url);
        const info = asset.blob
          ? [asset.mediaType, (asset.byteSize === null ? "?" : asset.byteSize) + " 字节",
            (asset.width && asset.height ? asset.width + "×" + asset.height : "尺寸未知")].join(" · ")
          : "资产记录缺失";
        rows.push({
          index,
          role: entry.role,
          url,
          name: asset.originalName || ("参考图 " + (index + 1)),
          info,
          sha256: entry.asset_sha256,
        });
      }
    } catch (error) {
      if (token === referenceToken) {
        for (const url of created) URL.revokeObjectURL(url);
        failRegion("refs", errorMessageOf(error, "参考图读取没有完成，请重试。"));
      }
      return;
    }
    if (token !== referenceToken) {
      for (const url of created) URL.revokeObjectURL(url);
      return;
    }
    for (const url of referenceUrls) URL.revokeObjectURL(url);
    referenceUrls = created;
    referenceRows = rows;
    renderReferencesCard();
  }

  /** 某张参考图当前已确认的可支持视角：只读 domain 唯一判据，不在视图里复刻规则。 */
  function supportedViewpointsOf(sha256: string): string[] {
    const proof = referenceViewpointEvidence(inputs.slotEntries(), [sha256]);
    return proof.viewpoints;
  }

  /**
   * 每张照片的视角支持确认（设计 §13.4.2）：普通措辞，不要求摄影术语。
   * 勾选=人确认这张照片能看到该角度；经 inputs.setViewpointSupport 写 reference_observation FactSlot。
   */
  function viewpointSupportTemplate(row: ReferenceRow): TemplateResult | typeof nothing {
    if (!row.url) return nothing;
    const supported = supportedViewpointsOf(row.sha256);
    const labels: Record<string, string> = { front: "能看到正面", side: "能看到侧面", top: "能看到顶面" };
    return html`
      <div class="ref-viewpoints" id=${"ref-viewpoint-" + row.index}>
        <span class="label">这张照片能看到的角度（确认后才能作为视角依据）</span>
        ${(REFERENCE_VIEWPOINTS as readonly string[]).map((viewpoint) => html`
          <label class="choice"><input type="checkbox"
            id=${"ref-viewpoint-" + row.index + "-" + viewpoint} value=${viewpoint}
            .checked=${live(supported.includes(viewpoint))}
            @change=${(event: Event) => void handleViewpointSupport(
              row.sha256, viewpoint, (event.currentTarget as HTMLInputElement).checked)}>
            ${labels[viewpoint] || viewpoint}</label>`)}
      </div>
    `;
  }

  async function handleViewpointSupport(sha256: string, viewpoint: string, checked: boolean): Promise<void> {
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.refs = "";
    renderReferencesCard();
    try {
      const current = supportedViewpointsOf(sha256);
      const next = checked
        ? [...new Set([...current, viewpoint])]
        : current.filter((item) => item !== viewpoint);
      await inputs.setViewpointSupport(next, [sha256]);
      if (!action.alive()) return;
      renderAll();
    } catch (error) {
      if (action.alive()) {
        failRegion("refs", errorMessageOf(error, "视角确认没有保存，请重试。"));
      }
    }
  }

  function referenceRowTemplate(row: ReferenceRow): TemplateResult {
    return html`
      <li class="ref-row" data-sha=${row.sha256}>
        <div class="ref-thumb">${row.url
          ? html`<img src=${row.url} alt=${row.name || "参考图"} loading="lazy">`
          : html`<span class="meta">资产缺失</span>`}</div>
        <div class="ref-main">
          <span class="name">${row.name}</span>
          <span class="meta">${row.info}</span>
          ${viewpointSupportTemplate(row)}
          <details class="tech-details"><summary>技术详情</summary>
            <p class="meta tech-body">${"sha256 " + row.sha256.slice(0, 12) + "…"}</p></details>
        </div>
        <div class="ref-actions">
          <select aria-label="参考图角色" @change=${(event: Event) => {
            void handleRoleChange(row.index, (event.currentTarget as HTMLSelectElement).value as ReferenceRole);
          }}>${REFERENCE_ROLES.map((role) => html`<option value=${role}
            .selected=${role === row.role}>${(ROLE_TEXT as Record<string, string>)[role] || role}</option>`)}</select>
          <button class="danger" type="button" @click=${() => void handleRemoveReference(row.index)}>删除</button>
        </div>
      </li>
    `;
  }

  function referencesCardTemplate(): TemplateResult {
    const entries = inputs.references();
    return html`
      <div class="card-head">
        <h4 id="refs-title">参考图</h4>
        <p class="meta">至少一张“商品主图（primary）”；内容相同的图不会重复登记；最多 ${MAX_REFERENCES} 张。</p>
      </div>
      <div class="toolbar">
        <button id="ref-add" type="button" @click=${() => fileInputNode?.click()}>添加参考图…</button>
        <input id="ref-file" type="file" accept="image/*" multiple hidden
          @change=${(event: Event) => void handleReferenceFiles(event)}
          ${ref((node) => { if (node) fileInputNode = node as HTMLInputElement; })}>
        <span id="ref-count" class="meta">${entries.length ? entries.length + " / " + MAX_REFERENCES + " 张" : ""}</span>
      </div>
      <p id="ref-error" class="error" role="alert" ?hidden=${!draft.errors.refs}>${draft.errors.refs}</p>
      <p id="ref-empty" class="empty" ?hidden=${entries.length > 0}>还没有参考图。</p>
      <ul id="ref-list" class="ref-list">${repeat(referenceRows,
        (row) => row.sha256, (row) => referenceRowTemplate(row))}</ul>
    `;
  }

  function renderReferencesCard(): void {
    if (!refsHost) return;
    renderLit(referencesCardTemplate(), refsHost);
  }

  async function handleRoleChange(index: number, role: ReferenceRole): Promise<void> {
    const action = beginAction();
    draft.errors.refs = "";
    renderReferencesCard();
    await inputs.setReferenceRole(index, role);
    if (!action.alive()) return;
    renderAll();
  }

  async function handleRemoveReference(index: number): Promise<void> {
    const action = beginAction();
    draft.errors.refs = "";
    renderReferencesCard();
    await inputs.removeReference(index);
    if (!action.alive()) return;
    renderAll();
  }

  async function handleReferenceFiles(event: Event): Promise<void> {
    const node = event.currentTarget as HTMLInputElement;
    const files = [...(node.files || [])];
    node.value = "";
    if (!files.length) return;
    const action = beginAction();
    if (!action.projectId) return;
    draft.errors.refs = "";
    renderReferencesCard();
    const added = await inputs.addReferences(files, (kind, file) => {
      if (!action.alive()) return;
      if (kind === "too_many") draft.errors.refs = "参考图最多 " + MAX_REFERENCES + " 张，多出的文件没有加入。";
      else if (kind === "too_large") draft.errors.refs = "“" + file.name + "”超过单张参考图上限 10MB，已跳过；请压缩后再上传。";
      else if (kind === "unreadable") draft.errors.refs = "“" + file.name + "”不是可读取的图片，已跳过。";
      else draft.errors.refs = "“" + file.name + "”与已有参考图内容相同，已跳过。";
      renderReferencesCard();
    });
    if (added && action.alive()) renderAll();
  }

  /* ------------------------------------------------------------ 命令与入口 */

  function renderRegion(region: RegionKey): void {
    if (region === "refs") { renderReferencesCard(); return; }
    if (region === "intake") { renderIntakeCard(); return; }
    if (region === "analyze") { renderAnalyzeCard(); return; }
    if (region === "slots") { renderSlotsCard(); return; }
    if (region === "suite") { renderSuiteCard(); return; }
    renderSpecsCard();
  }

  /** 命令侧报错：只改状态，由渲染落到对应分区（错误文案不自动消失）。 */
  function failRegion(region: RegionKey, message: string): void {
    draft.errors[region] = message;
    renderRegion(region);
  }

  /** 资料/理解/方案三区同轮渲染；顺序与原 renderAll 的分区调用一致。 */
  function render(): void {
    resolveHosts();
    ensureScope();
    void renderReferences().catch(handleInternalError);
    syncDrafts();
    syncShotDrafts();
    renderIntakeCard();
    renderAnalyzeCard();
    renderSlotsCard();
    renderSuiteCard();
    renderSpecsCard();
  }

  /** 重开项目时的就地状态归零：草稿、交互态与引用图资源一起回收。 */
  function resetViewState(): void {
    dispose();
    draft = createDraft(null);
    lastAnalyze = null;
    analyzeProblems = [];
    analyzeErrorText = "";
    analyzeRequiresConfirmation = false;
    showAll = false;
  }

  /** 资料表单「保存」：落库 → 派生 → 只刷新理解区与页眉（保留原 bind 的刷新面）。 */
  async function handleSaveIntake(): Promise<void> {
    try {
      await saveIntakeNow();
      await deriveAndApplyState();
      renderAnalyzeCard();
      deps.renderHeader();
    } catch (error) {
      handleInternalError(error);
    }
  }

  /** 「人工填写事实」：先落库资料，再准备核心槽位，最后停靠理解阶段。 */
  async function handleManualFacts(): Promise<void> {
    const action = beginAction();
    try {
      await saveIntakeNow();
      if (!action.alive()) return;
      await prepareManualFacts();
      if (action.alive()) selectStage("understand", { focusHeading: true });
    } catch (error) { if (action.alive()) handleInternalError(error); }
  }

  /** 槽位列表展开/收起（只切本视图的局部状态）。 */
  function toggleAllSlots(): void {
    showAll = !showAll;
    renderSlotsCard();
  }

  /** 按推荐模板种子建计划；落库与派生由 applySuiteOp 与工作区负责。 */
  function seedSuite(): Promise<boolean> {
    return handleSuiteOp(() => seedSuitePlan(inputs.suiteContext()));
  }

  /** 从下拉模板追加一张图（计划不存在时空操作，与原 bind 一致）。 */
  function addTemplateShot(): Promise<boolean> {
    const plan = inputs.suitePlan();
    if (!plan) return Promise.resolve(false);
    return handleSuiteOp(() => addShotFromTemplate(
      plan, draft.templateId, { context: inputs.suiteContext() }));
  }


  /** 自定义图面板的展开态属于本视图。 */
  function toggleCustomPanel(): void {
    draft.customPanelOpen = !draft.customPanelOpen;
    renderSuiteCard();
  }

  /** 未保存资料草稿的唯一读侧（trim 与一行一条的拆分只在 payload 边界发生）。 */
  function draftInputPayload(): CompleteProductInput {
    return {
      schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
      product_name: draft.intake.product_name.trim(),
      description: draft.intake.description.trim(),
      selling_points: splitLines(draft.intake.selling_points),
      focus: draft.intake.focus.trim(),
      references: inputs.references().map((item) => ({ ...item })),
    };
  }

  return {
    render,
    renderIntake,
    renderAnalyze,
    draftInputPayload,
    resetViewState,
    saveIntakeNow,
    prepareManualFacts,
  };
}
