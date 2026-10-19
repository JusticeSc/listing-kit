/**
 * Product V2 domain shared contracts (types only, no runtime).
 *
 * Single source for finite JSDoc imports:
 *   JS:  `import('./type-contracts.js').Foo`
 *   storage: `import('../domain/type-contracts.js').Foo`
 *
 * Names reflect actual runtime fields (not placeholders). `unknown` appears
 * only at validation boundaries; guards narrow to these records.
 *
 * Parent-owned durable queue (confirm.js / attempt.js, integration ongoing):
 *  - ConfirmationSnapshot.execution_target is OPTIONAL to accept historical
 *    records; new clients MUST provide it (all fields whitelisted from
 *    attemptCurrentEnvironmentIdentity: provider_id/model_id/protocol/
 *    capability_version/credential_source/sync). Never fake old identity.
 *  - AttemptRecord.authorization is OPTIONAL historical
 *    {document_id,version,hash}; new clients provide it after persisting the
 *    confirmation doc. Consumed original queue is identified by exact
 *    doc id/version, not latest prompt. No shims.
 *  - Adoption staleness derives from the SELECTED candidate's ORIGINAL prompt
 *    consumed basis, not a newer rework/latest prompt alone; unchanged
 *    original source facts keep old adoption current.
 */

/** 64-char lowercase hex sha256. */
export type Sha256Hex = string;
/** ISO-8601 timestamp string (length >= 20, Date.parse-able). */
export type IsoTimestamp = string;

/** Storage document kind (mirrors DOMAIN_DOCUMENT_KINDS runtime keys/values). */
export type DomainDocumentKind =
  | "product_input"
  | "semantic_analysis"
  | "fact_slot"
  | "product_brief"
  | "suite_plan"
  | "style_spec"
  | "shot_spec"
  | "prompt_version"
  | "generation_confirm"
  | "generation_attempt"
  | "candidate"
  | "review_report"
  | "selection"
  | "suite_review"
  | "export_record"
  | "review_acknowledgement";

/** Single contract problem ({code,path,message} + optional reason_code). */
export type DomainProblem = {
  code: string;
  path: string;
  message: string;
  reason_code?: string;
};

/* ------------------------------------------------------------------ shared */

export type DimensionAxis =
  | "height" | "width" | "length" | "depth"
  | "diameter" | "weight" | "volume" | "thickness";
export type DimensionUnit =
  | "mm" | "cm" | "m" | "in" | "ft"
  | "g" | "kg" | "ml" | "l" | "oz" | "lb";
export type DimensionMeasurement = {
  object: string;
  axis: DimensionAxis;
  value: number;
  unit: DimensionUnit;
  source_basis: string;
};

export type EvidenceKind = "user" | "asset" | "model" | "rule";
export type EvidenceItem = {
  kind: EvidenceKind;
  ref: string;
  note?: string;
  observed_at?: IsoTimestamp;
};

/* ------------------------------------------------------------------- slots */

export type SlotAuthority = "core_fixed" | "category_dynamic" | "user_custom" | "derived";
export type SlotSource =
  | "user_input" | "reference_observation" | "model_inference"
  | "system_default" | "derived_rule";
export type SlotStatus =
  | "confirmed" | "proposed" | "missing" | "conflict" | "unknown" | "superseded";
export type SlotValueType = "text" | "text_list" | "number" | "boolean" | "enum" | "dimension_list";
export type SlotActor = "user" | "model" | "rule";
export type SlotAction = "propose" | "edit" | "confirm" | "mark_conflict" | "mark_unknown" | "supersede";

/** Scalar-only slot value (checkValueShape guarantees; never free objects). */
export type FactSlotValue = string | string[] | number | boolean | DimensionMeasurement[];

export type FactSlot = {
  schema_version: number;
  slot_id: string;
  label: string;
  authority: SlotAuthority;
  value_type: SlotValueType;
  source: SlotSource;
  status: SlotStatus;
  value?: FactSlotValue | null;
  confidence?: number | null;
  allow_model_proposal?: boolean;
  /** Proposal provenance: model that suggested this slot value (semantic apply path). */
  model_id?: string;
  evidence: EvidenceItem[];
  depends_on?: string[];
  enum_values?: string[];
  critical?: boolean;
};

/** Versioned slot entry consumed by brief projection. */
export type SlotEntry = { slot: FactSlot; version: number };

export type CoreSlotDefinition = {
  slot_id: string;
  label: string;
  value_type: SlotValueType;
  critical: boolean;
};

export type ActorPermissions = { user: boolean; model: boolean; rule: boolean };
export type SlotPermissions = {
  edit_value: ActorPermissions;
  confirm: ActorPermissions;
  delete: ActorPermissions;
  add: ActorPermissions;
};

export type SlotActionSpec = {
  action: SlotAction;
  actor: SlotActor;
  value?: FactSlotValue | null;
  confidence?: number;
  evidence?: EvidenceItem[];
  source?: SlotSource;
};

/* ------------------------------------------------------------------ intake */

export type ReferenceRole = "primary" | "detail" | "packaging" | "scene" | "competitor" | "other";
export type ProductReference = {
  asset_sha256: Sha256Hex;
  role: ReferenceRole;
  note?: string;
};
export type ProductInput = {
  schema_version: number;
  product_name: string;
  description?: string;
  selling_points?: string[];
  focus?: string;
  references: ProductReference[];
};

/** 文案提议目标：精确到某个已确认事实槽位的版本（版本变了提议即过期）。 */
export type CopyProposalTarget = { slot_id: string; version: number };
/** 提议请求：只针对目标槽位生成英文上图候选；不写入任何事实或规格。 */
export type CopyProposalRequest = { targets: CopyProposalTarget[]; language: "en" };
/** 候选文案：仍只是提议，必须人工确认后才可能成为 on_image_texts 条目。 */
export type CopyProposal = {
  text: string;
  source_slot_id: string;
  source_slot_version: number;
};

/** A model proposal stays source-bound and never carries confirmation authority. */
export type SemanticProposal = {
  slots: (FactSlot & { model_id?: string })[];
  summary: string;
  questions: string[];
  /** 本次请求了候选文案时才有；未请求时必须缺席，两种产出不混装。 */
  copy_proposals?: CopyProposal[];
  meta: {
    provider_id: string;
    model_id: string;
    request_id: string | null;
    reference_images_sent: boolean;
    inputs_used: string[];
  };
};
export type SemanticAnalysisSource = {
  document_id: string;
  version: number;
  fingerprint: string;
  payload: ProductInput;
};
export type SemanticAnalysisFailure = {
  family: string;
  code: string;
  message: string;
  retry_policy: string;
};
export type SemanticImageProvenance = {
  role: string;
  media_type: string;
  sha256: string;
};
export type SemanticAnalysisRecord = {
  schema_version: 1;
  action_id: string;
  source: SemanticAnalysisSource;
  provider: { provider_id: string; model_id: string; credential_source: string };
  created_at: IsoTimestamp;
  updated_at: IsoTimestamp;
  reference_images_sent: boolean;
  /** 本次实际发送的图片来源（role/media/sha256，无字节原文、无密钥）；旧记录缺席=未知，不回填。 */
  image_provenance?: SemanticImageProvenance[];
} & (
  | { state: "pending_submit"; proposal: null; error: null; disposition: "not_applied" }
  | { state: "succeeded"; proposal: SemanticProposal; error: null;
      disposition: "stored" | "stale" | "applied" }
  | { state: "failed" | "unknown"; proposal: null; error: SemanticAnalysisFailure;
      disposition: "not_applied" }
);
export type IntakeReadiness = { ready: boolean; blocking: DomainProblem[] };

/* ------------------------------------------------------------------- brief */

export type BriefBasisItem = { slot_id: string; version: number };
export type ConfirmedFact = {
  slot_id: string;
  label: string;
  value: FactSlotValue;
  source: SlotSource;
};
export type UnresolvedItem = {
  slot_id: string;
  label: string;
  status: "proposed" | "missing" | "conflict" | "unknown";
  critical: boolean;
};
export type BriefCategory = { slot_id: "product_category"; value: string };
export type ProductBrief = {
  schema_version: number;
  basis: BriefBasisItem[];
  category: BriefCategory | null;
  confirmed_facts: ConfirmedFact[];
  unresolved: UnresolvedItem[];
};
export type BriefStaleness = {
  stale: boolean;
  reasons: { slot_id: string; basis_version: number; current_version: number | null; reason: string }[];
};
export type BriefReadiness = {
  ready: boolean;
  blocking: { code: string; slot_id: string | null; status: string; message: string }[];
};

/* ------------------------------------------------------------ invalidation */

export type ChangeKind =
  | "references_changed" | "identity_fact_changed" | "fact_value_changed"
  | "style_changed" | "shot_spec_changed" | "prompt_edited" | "shot_added_or_removed";
export type InvalidationContext = {
  shotId?: string;
  shotIds?: string[];
  briefUsesSlot?: boolean;
};
export type InvalidationResult = {
  kind: string;
  scope: string;
  invalidates: string[];
  preserves: string[];
  target_shot_id: string | null;
};
export type InvalidationRule = {
  scope: string;
  invalidates: readonly string[];
  preserves: readonly string[];
};

/* ------------------------------------------------------------------- specs */

export type StyleSpec = {
  schema_version: number;
  background: string;
  lighting: string;
  color_tone: string;
  composition: string;
  avoid: string[];
  /** 共用展示决定；缺失=未决定，消费该决定的图会被阻断并让用户做一次普通选择。 */
  presentation?: Presentation;
};
export type ShotPrintIntent = "none" | "selected" | "undecided";
export type ShotLayout = "product_only" | "product_left_text_right" | "product_right_text_left";
export type OnImageTextStatus = "proposed" | "confirmed";
export type OnImageTextOrigin = "user" | "model" | "reuse";
/** 外观状态：原样保持（含已见使用痕迹）／干净展示（允许去除临时残留）／未决定。 */
export type AppearanceState = "as_shown" | "clean_display" | "undecided";
/** 内容物状态：原样保持／已倒空／不适用（不看内容物的用途）／未决定。 */
export type ContentsState = "as_shown" | "empty" | "not_applicable" | "undecided";
export type Viewpoint = "reference_visible" | "front" | "side" | "top";
/** 单图字段缺失才继承；显式 undecided 不是继承。 */
export type Presentation = {
  appearance_state?: AppearanceState;
  contents_state?: ContentsState;
  viewpoint?: Viewpoint;
};
export type ImageTextSource = { kind: "fact_slot"; document_id: string; version: number };
export type MeasurementSourceKind = "nominal" | "measured";
/** 英文映射与来源分类须人工核对；数值与物理含义仍取精确 measurement。 */
export type MeasurementBinding = DimensionMeasurement & {
  index: number;
  object_label: string;
  axis_label: string;
  source_kind: MeasurementSourceKind;
};
export type MeasurementSourceBinding = {
  indices: number[];
  measurements: DimensionMeasurement[];
  source_kind: MeasurementSourceKind;
};
/** 当前写入的文案；模型只能 proposed，人工确认后才可编译。 */
export type OnImageText = {
  text_id: string;
  text: string;
  source: ImageTextSource;
  status: OnImageTextStatus;
  origin: OnImageTextOrigin;
  measurement?: MeasurementBinding;
  measurement_source?: MeasurementSourceBinding;
};
/** 已发布 schema1 的只读形状；新命令不再写 flat 来源。 */
export type LegacyOnImageText = {
  text_id: string;
  text: string;
  source_slot_id: string;
  source_slot_version: number;
  status: OnImageTextStatus;
  origin: OnImageTextOrigin;
};
export type StoredOnImageText = OnImageText | LegacyOnImageText;
export type ShotSpec = {
  schema_version: number;
  purpose: string;
  keep: string[];
  change_allowed: string[];
  notes: string;
  /** 印字决定；只在需要该决定的角色上存在，缺失表示按该角色既有合同。 */
  print_intent?: ShotPrintIntent;
  layout?: ShotLayout;
  on_image_texts?: StoredOnImageText[];
  /** 单图展示决定覆盖；未覆盖则继承 StyleSpec.presentation。 */
  presentation?: Presentation;
  /** 未出现使用本图角色依据；空数组是明确无依据，不能回退全部原图。 */
  reference_sha256s?: Sha256Hex[];
};
export type StyleSpecField = { key: string; label: string; kind: "text" | "list" };
export type SpecDiffItem = {
  field: string;
  label: string;
  before: string | string[];
  after: string | string[];
};
export type StyleSpecSummaryItem = {
  key: string;
  label: string;
  kind: "text" | "list";
  value: string | string[];
  text: string;
};
export type ReviewChecklistItem = {
  key: string;
  label: string;
  status: string;
  detail?: string;
};
export type SuiteSpecDigest = {
  shots: { shot_id: string; purpose: string; keep: string[]; change_allowed: string[] }[];
  style_empty: boolean;
};

/* -------------------------------------------------------------- suite-plan */

export type DependencyKind = "asset_role" | "fact" | "fact_any" | "bound_fact" | "bound_dimension" | "any_of";
export type ShotDependency =
  | { kind: "asset_role"; role: string }
  | { kind: "fact"; slot_id: string }
  | { kind: "fact_any"; slot_ids: readonly string[] }
  | { kind: "bound_fact" }
  | { kind: "bound_dimension" }
  | { kind: "any_of"; of: readonly ShotDependency[] };

export type ImageRole = {
  role_id: string;
  label: string;
  purpose: string;
  custom: boolean;
};
export type ShotTemplate = {
  template_id: string;
  role_id: string;
  label: string;
  intent: string;
  required: boolean;
  order: number;
  dependencies: ShotDependency[];
};
export type SuiteRegistry = { roles: ImageRole[]; templates: ShotTemplate[] };

/** Pre-persist shot draft: shot_id is null until the plan assigns a real id. */
export type ShotDraft = {
  shot_id: string | null;
  template_id: string | null;
  role_id: string;
  label: string;
  intent: string;
  required: boolean;
  order?: number | null;
  custom: boolean;
  dependencies: readonly ShotDependency[];
  fact_slot_ids: readonly string[];
};
/** Persisted plan element (plan.shots item): validation guarantees a real shot_id. */
export type PlanShot = Omit<ShotDraft, "shot_id"> & { shot_id: string };
export type SuitePlan = { schema_version: number; shots: readonly PlanShot[] };

export type DependencyBlocking = {
  kind: DependencyKind | null;
  reason: string | null;
  missing: string[];
};
export type ShotEvaluation = {
  shot_id: string | null;
  template_id: string | null;
  satisfied: boolean;
  blocking: DependencyBlocking[];
};
export type ShotReadiness = ShotEvaluation & {
  role_id: string | null;
  ready: boolean;
  consumed_slot_ids: string[];
  missing_fact_ids: string[];
  missing_asset_roles: string[];
};
export type EvalContext = {
  facts?: { slot_id: string; status: string; value?: unknown }[];
  assets?: { role: string }[];
  bound_fact_ids?: string[];
  [key: string]: unknown;
};
export type PlanRecommendation = {
  instances: {
    template_id: string;
    role_id: string;
    role_label: string | null;
    label: string;
    intent: string;
    required: boolean;
    order: number;
    custom: boolean;
    fact_slot_ids: string[];
    satisfied: boolean;
    blocking: DependencyBlocking[];
  }[];
  satisfiable: string[];
  blocked: string[];
  required_blocked: string[];
};
export type SuitePlanSummary = {
  total: number;
  satisfiable: number;
  blocked: number;
  required_blocked: string[];
  shots: {
    shot_id: string;
    template_id: string | null;
    label: string;
    role_id: string;
    role_label: string | null;
    required: boolean;
    custom: boolean;
    satisfied: boolean;
    blocking: DependencyBlocking[];
  }[];
};
export type SuitePlanChange = { plan: SuitePlan; shot?: ShotDraft; removed?: ShotDraft; moved?: boolean };

/* ------------------------------------------------------------------ prompt */

export type ImagePromptProfile = {
  provider_id: string;
  model_id: string;
  version: number;
  protocol: string;
  size: string;
  n: number;
  prompt_extend: boolean;
  watermark: boolean;
  output_format: string;
  supports_negative_prompt_field: boolean;
  max_reference_images: number;
  reference_media_types: string[];
  min_side: number;
  max_side: number;
  min_area: number;
  max_area: number;
  min_ratio: number;
  max_ratio: number;
  max_prompt_chars: number;
};
export type PromptSectionKind = "instruction" | "literal" | "manual_edit";
export type PromptTextItem = { text: string; language: string; source_ref: string };
export type PromptSection = {
  key: string;
  label: string;
  kind: PromptSectionKind;
  text: string;
  source_refs: string[];
  items?: PromptTextItem[];
};
export type PromptWarning = { code: string; message: string; source_refs: string[] };
export type PromptBasis = {
  /** 历史记录可缺失；当前编译器每次新写入都冻结此版本。 */
  compiler_rule_version?: number;
  brief: BriefBasisItem[];
  consumed_slot_ids: string[];
  shot_signature: string | null;
  suite_version: number | null;
  style_version: number | null;
  /** 本图消费的共用风格签名；历史记录可缺失（退回 style_version 比较）。 */
  style_signature?: string | null;
  shot_spec_version: number | null;
  /** 商品资料版本：冻结引用里嵌了它；历史记录可缺失（缺失即按当前资料重新准备）。 */
  intake_version?: number | null;
  platform: { platform_id: string; version: number };
  provider: ImagePromptProfile;
  rework?: {
    directive_id: string;
    candidate_id: string;
    candidate_sha256: string;
    problems: string[];
    mode?: ReworkMode;
    problem_candidate?: ReworkProblemCandidate;
  };
};
export type CompiledPrompt = {
  schema_version: number;
  shot_id: string;
  role_id: string;
  label: string;
  language: { policy_id: string; instruction: string; on_image_text: string };
  platform: { platform_id: string; version: number; label: string };
  provider: ImagePromptProfile;
  sections: PromptSection[];
  text: string;
  source_refs: string[];
  warnings: PromptWarning[];
  basis: PromptBasis;
  rework?: {
    contract_version: string;
    directive_id: string;
    candidate_id: string;
    candidate_sha256: string;
    problems: string[];
    direction: string;
    mode?: ReworkMode;
    problem_candidate?: ReworkProblemCandidate;
  } | null;
  origin?: string;
};
export type RequestSnapshot = {
  model: string;
  size: string;
  n: number;
  prompt_extend: boolean;
  watermark: boolean;
  output_format: string;
  references: PromptReferenceSelection[];
  prompt: string;
  target: {
    provider_id: string;
    model_id: string;
    protocol: string;
    capability_version: number;
  };
};
export type PromptRecord = {
  schema_version: number;
  shot_id: string;
  role_id: string;
  label: string;
  compiled: CompiledPrompt;
  request_snapshot: RequestSnapshot;
  hash: Sha256Hex;
  basis: PromptBasis;
  origin?: string;
  edited_from?: { hash: Sha256Hex; version: number };
  edit_reason?: string;
  edited_at?: IsoTimestamp;
  invalidation?: InvalidationResult;
  reconfirmed?: boolean;
};
/** 商品来源投影不伪造冻结元数据；当前请求只使用下方完整选择。 */
export type PromptReferenceIdentity = { role: string; sha256: Sha256Hex };
export type PromptReferenceUse = "edit_source" | "product_truth" | "style_reference";
export type PromptReferenceSource = {
  kind: "candidate" | "product_input";
  document_id: string;
  version: number;
  asset_sha256: Sha256Hex;
};
export type PromptReferenceSelection = PromptReferenceIdentity & {
  uses: PromptReferenceUse[];
  sources: PromptReferenceSource[];
};
export type PromptStaleness = {
  stale: boolean;
  reasons: { field: string; stored: unknown; current: unknown; reason: string }[];
};

/* ------------------------------------------------ parent-owned (shape only) */

export type AttemptState =
  | "pending_submit" | "submitted" | "running"
  | "succeeded" | "failed" | "unknown";
export type AttemptError = {
  family: "input_rejected" | "provider_failed" | "provider_unknown" | "internal";
  code: string;
  message: string;
  retry_policy: "retryable" | "requires_review" | "fatal";
};
export type AttemptExecutionIdentity = {
  schema_version: number;
  protocol: string;
  capability_version: number;
  credential_reference: { source: string };
  /** 未声明时为异步；只有显式 true 才证明同步协议。 */
  sync?: boolean;
};
export type AttemptCurrentEnvironmentIdentity = {
  protocol: string;
  provider_id: string;
  model_id: string;
  capability_version: number;
  credential_source: string;
  configured: boolean;
  sync: boolean;
};
/** Optional historical auth binding (exact confirmation doc id/version/hash). */
export type AttemptAuthorization = {
  document_id: string;
  version: number;
  hash: Sha256Hex;
};
export type AttemptRecord = {
  schema_version: number;
  action_id: string;
  shot_id: string;
  state: AttemptState;
  prompt: { version: number; hash: Sha256Hex };
  /**
   * schema 3：完整冻结引用（身份+用途+来源，与请求快照同形状）；
   * schema ≤2 旧记录为身份形状 {role, sha256}（只读核对）。
   */
  references: (PromptReferenceIdentity & {
    uses?: PromptReferenceUse[];
    sources?: PromptReferenceSource[];
  })[];
  provider: { provider_id: string; model_id: string };
  execution_identity: AttemptExecutionIdentity;
  parameters: { size: string; n: number; prompt_extend: boolean; watermark: boolean };
  task_id: string | null;
  request_id: string | null;
  error: AttemptError | null;
  created_at: IsoTimestamp;
  updated_at: IsoTimestamp;
  change_log: { at: string; via: string; from: string | null; to: string; note: string | null }[];
  authorization?: AttemptAuthorization;
};

/** Frozen execution target inside confirmation snapshot (new clients required). */
export type ConfirmationSubmissionMode = "initial" | "failed_retry" | "rework" | "explicit_new";
export type ConfirmationExecutionTarget = {
  provider_id: string;
  model_id: string;
  protocol: string;
  capability_version: number;
  credential_source: string;
  sync: boolean;
};

/** 公共定价事实只绑定已核模型/地区/参数；凭据不进入费用或确认记录。 */
export type ImagePricing = {
  version: 1;
  kind: "official" | "test_double";
  provider_id: string;
  model_id: string;
  size: string;
  n: 1;
  output_format: string;
  currency: "CNY";
  input_image_fen: number;
  output_image_fen: number;
  verified_on: string | null;
  source_url: string | null;
  region: "cn-beijing" | "local-test";
};
export type ConfirmationCost = {
  currency: "CNY";
  upper_fen: number | null;
  pricing: ImagePricing | null;
  per_shot: { shot_id: string; input_images: number; upper_fen: number }[];
  message: string;
};
export type ConfirmationSelection = {
  selected_shot_ids: string[];
  excluded: { shot_id: string; label: string; reasons: { code: string; message: string }[] }[];
};
export type ConfirmationSnapshot = {
  schema_version: number;
  scope_shot_ids?: string[];
  /** schema 4 起必带；历史只读记录不补造所选范围或排除理由。 */
  selection?: ConfirmationSelection;
  platform: { platform_id: string; version: number };
  provider: { model_id: string; version: number };
  can_submit: boolean;
  shots: {
    shot_id: string;
    prompt_version: number | null;
    prompt_hash: string | null;
    prompt_chars?: number | null;
    /**
     * schema 3：该图新请求快照的冻结引用（身份+用途+来源）。
     * 历史1仅角色、历史2含图身份，不迁移改写或补造用途/来源。
     */
    references?: (PromptReferenceIdentity & {
      uses?: PromptReferenceUse[];
      sources?: PromptReferenceSource[];
    })[];
    blocked: string[];
  }[];
  external_summary: Record<string, unknown>;
  execution_target?: ConfirmationExecutionTarget;
  submission_mode?: ConfirmationSubmissionMode;
};
export type ConfirmationShotEntry = {
  shot_id: string;
  label: string;
  prompt_version: number | null;
  prompt_hash: Sha256Hex;
  /** 冻结引用的只读展示投影：完整身份+前缀 + 用途/来源（schema 3 起必带）；历史保留原投影。 */
  references: { role: string; sha256: Sha256Hex; sha256_prefix: string; uses?: string[];
    sources?: { kind?: string; document_id?: string; version?: number; asset_sha256?: string }[] }[];
  risks: string[];
};
export type ConfirmationRecord = {
  schema_version: number;
  confirmed_at: IsoTimestamp;
  fingerprint: { snapshot: ConfirmationSnapshot; hash: Sha256Hex };
  platform: { platform_id: string; version: number };
  provider: { model_id: string; version: number };
  total: number;
  external_summary: Record<string, unknown>;
  shots: ConfirmationShotEntry[];
  risks: { shot_id: string; code: string }[];
};

/* ------------------------------------------------------------------ review */

export type ReviewSeverity = "BLOCK" | "HIGH_RISK" | "WARNING" | "PASS" | "UNKNOWN";
export type ReviewLayer = "generation" | "candidate" | "export" | "vlm" | "suite";
export type UnknownPolicy = "hint" | "disable";
export type ReviewRule = {
  rule_id: string;
  version: number;
  layer: ReviewLayer;
  title: string;
  severity: ReviewSeverity;
  consumer: string;
  measurement: string;
  unknown_policy: UnknownPolicy;
  blocker_codes?: string[];
  applies_to?: { roles: string[] };
};
export type ReviewFinding = {
  rule_id: string;
  rule_version: number;
  layer: ReviewLayer;
  severity: ReviewSeverity;
  title: string;
  detail: string;
  measured: unknown;
  affected_shot_ids?: string[];
};
export type VlmOutcome = "checked" | "unknown";
export type VlmCheckId =
  | "product_fidelity" | "part_anomaly" | "deformity" | "clipping"
  | "garbled_text" | "goal_completion" | "prohibited_content";
export type VlmBlock = {
  outcome: VlmOutcome;
  contract_version: string;
  asset_sha256: Sha256Hex;
  candidate_id?: string;
  shot_id?: string;
  provider_id: string | null;
  model_id: string | null;
  request_id: string | null;
  checked_at: IsoTimestamp;
  latency_ms: number | null;
  summary: string;
};
export type VlmFinding = ReviewFinding;
export type ReviewReport = {
  schema_version: number;
  review_contract_version: string;
  candidate_id: string;
  shot_id: string;
  asset_sha256: Sha256Hex;
  vlm: VlmBlock | null;
  summary: Record<ReviewSeverity, number>;
  findings: ReviewFinding[];
  created_at: IsoTimestamp;
};
export type ExportReadiness = { exportable: boolean; findings: ReviewFinding[] };
export type AssetHashCheck = { ok: boolean; findings: ReviewFinding[] };

/* ---------------------------------------------------------------- candidate */

export type CandidateRecord = {
  schema_version: number;
  candidate_id: string;
  shot_id: string;
  action_id: string;
  task_id: string | null;
  sync: boolean;
  asset_sha256: Sha256Hex;
  media_type: "image/png";
  byte_size: number;
  width: number;
  height: number;
  provider: { provider_id: string | null; model_id: string | null };
  created_at: IsoTimestamp;
};
export type PngHeader = {
  width: number;
  height: number;
  bit_depth: number | null;
  color_type: number | null;
  has_transparency: boolean | null;
};
export type CandidateStoreDecision = {
  needed: boolean;
  reason: string;
  candidate?: unknown;
};

/* ---------------------------------------------------------------- selection */

export type SelectionAction = "select" | "clear";
export type SelectionState = "none" | "current" | "stale" | "cleared";
export type SelectionReviewFingerprint = {
  review_contract_version: string | null;
  report_created_at: string | null;
  candidate_id: string | null;
  asset_sha256: string | null;
  finding_count: number;
  top_rule_id: string | null;
  top_severity: string | null;
};
export type SelectionRecord = {
  schema_version: number;
  contract_version: string;
  selection_id: string;
  action: SelectionAction;
  shot_id: string;
  candidate_id: string | null;
  candidate_sha256: Sha256Hex | null;
  candidate_version: number | null;
  review_fingerprint: SelectionReviewFingerprint | null;
  created_at: IsoTimestamp;
};
export type SelectionSetEntry = {
  shot_id: string | null;
  required: boolean;
  state: SelectionState;
  selection_id: string | null;
  candidate_id: string | null;
  candidate_sha256: string | null;
  candidate_version: number | null;
  selected_at: string | null;
};
export type SelectionSet = {
  contract_version: string;
  generated_at: string | null;
  entries: SelectionSetEntry[];
  summary: {
    required_total: number;
    current: number;
    stale: number;
    missing: number;
    optional_current: number;
  };
};
export type SelectionStaleReason = {
  field: string;
  stored: unknown;
  current: unknown;
  reason: string;
};

/* -------------------------------------------------------------- suite-review */

export type SuiteVlmReason =
  | "not_run" | "no_selection" | "over_limit" | "missing_bytes"
  | "image_too_large" | "transport" | "server" | "protocol";
export type SuiteVlmOutcome = "checked" | "unknown" | "not_run";
export type SuiteVlmBlock = {
  outcome: SuiteVlmOutcome;
  contract_version: string;
  requested_shot_ids: string[];
  submitted_shot_ids: string[];
  asset_sha256_by_shot: Record<string, Sha256Hex>;
  provider_id: string | null;
  model_id: string | null;
  request_id: string | null;
  checked_at: IsoTimestamp;
  latency_ms: number | null;
  summary: string;
  reason: string | null;
};
export type SuiteVlmRun = {
  envelope?: { ok: boolean; result?: unknown; error?: unknown } | null;
  reason?: string;
  requested_shot_ids?: string[];
  submitted_shot_ids?: string[];
  asset_sha256_by_shot?: Record<string, string>;
};
export type SuiteReviewReport = {
  schema_version: number;
  contract_version: string;
  selection_fingerprint: string;
  inputs_fingerprint: string;
  vlm: SuiteVlmBlock | null;
  summary: Record<ReviewSeverity, number>;
  findings: ReviewFinding[];
  created_at: IsoTimestamp;
};

/* --------------------------------------------------------------- export-gate */

export type GateFinding = ReviewFinding & { affected_shot_ids: string[] };
export type UnknownItem = {
  target_kind: "review_report" | "suite_review";
  target_id: string;
  rule_id: string;
  shot_ids: string[];
  title: string;
  detail: string;
  asset_sha256: string | null;
  identity?: string | null;
  acknowledged?: boolean;
};
export type AcknowledgementRecord = {
  schema_version: number;
  contract_version: string;
  target_kind: string;
  target_id: string;
  rule_id: string;
  shot_ids: string[];
  acknowledged_at: IsoTimestamp;
  actor: string;
  note: string;
};
export type DeliveryGateResult = {
  contract_version: string;
  status: "blocked" | "ready";
  ready_to_export: boolean;
  findings: GateFinding[];
  blocking: GateFinding[];
  unknowns: UnknownItem[];
  unresolved_unknowns: UnknownItem[];
};
export type ExportRecordPayload = {
  schema_version: number;
  contract_version: string;
  project_id: string;
  project_name: string;
  zip_sha256: Sha256Hex;
  zip_bytes: number;
  files: { path: string; byte_size: number }[];
  included_shot_ids: string[];
  selection_fingerprint: string | null;
  inputs_fingerprint: string | null;
  gate: { status: string; findings: { rule_id: string; severity: string }[] };
  exported_at: IsoTimestamp;
};
export type DeliveryEntry = { path: string; bytes: Uint8Array };
export type DeliveryManifest = Record<string, unknown>;

/* ------------------------------------------------------------------- batch */

export type BatchShotState =
  | "blocked_no_prompt" | "ready" | "active"
  | "succeeded" | "succeeded_unstored" | "failed" | "unknown"
  | "pending_submit" | "submitted" | "running";
export type BatchNextStep = "empty" | "submit" | "compile" | "wait" | "fetch" | "review" | "retry" | "done";
export type BatchShotInfo = {
  shot_id: string;
  label: string;
  state: string;
  has_prompt: boolean;
  has_attempt: boolean;
  attempt_state: string | null;
  action_id: string | null;
  task_id: string | null;
  candidate_stored: boolean | null;
  reconcile_mode: string;
};
export type BatchState = {
  schema_version: number;
  rows: BatchShotInfo[];
  counts: {
    total: number;
    ready: number;
    active: number;
    succeeded: number;
    unstored: number;
    failed: number;
    unknown: number;
    blocked_no_prompt: number;
  };
  queue: string[];
  reconcile_queue: string[];
  fetch_queue: string[];
  review_queue: string[];
  retry_queue: string[];
  started: boolean;
  settled: boolean;
  all_succeeded: boolean;
  next_step: string;
};

/* ------------------------------------------------------------------ rework */

export type ReworkProblemId =
  | "product_fidelity" | "part_error" | "scene" | "composition"
  | "selling_point" | "text" | "style" | "platform_risk" | "other";
export type ReworkMode = "edit_candidate" | "regenerate_original";
export type ReworkProblemCandidate = {
  candidate_id: string;
  document_id: string;
  version: number;
  asset_sha256: Sha256Hex;
};
export type ReworkDirective = {
  schema_version: number;
  contract_version: string;
  directive_id: string;
  shot_id: string;
  candidate_id: string;
  candidate_sha256: Sha256Hex;
  /** schema1 历史不补造模式或来源；当前 schema2 写入必须明确给出。 */
  mode?: ReworkMode;
  problem_candidate?: ReworkProblemCandidate;
  problems: string[];
  direction: string;
  source: {
    candidate_id: string;
    asset_sha256: Sha256Hex;
    review_contract_version: string | null;
    top_rule_id: string | null;
    top_severity: string | null;
  };
  created_at: IsoTimestamp;
};

/* ----------------------------------------------------------------- compare */

export type CompareState = "pending" | "unknown" | "clean" | "unchecked";
export type CompareRow = {
  candidate_id: string;
  shot_id: string;
  asset_sha256: Sha256Hex;
  version: number | null;
  created_at: string;
  attempt_action_id: string | null;
  task_id: string | null;
  width: number | null;
  height: number | null;
  review_state: CompareState;
  pending: boolean;
  top_finding: ReviewFinding | null;
  report: ReviewReport | null;
  record: CandidateRecord;
};
export type CompareCounts = {
  total: number;
  pending: number;
  unknown: number;
  clean: number;
  unchecked: number;
};

/* ------------------------------------------------------------ config-export */

export type CredentialSourceLabel = "byok" | "default" | "test_double";
export type ShareableConfig = {
  format: string;
  format_version: number;
  exported_at: IsoTimestamp;
  schema_version: number;
  config: {
    provider: { provider_id: string; model_id: string; version: number };
    protocol: string;
    capability_version: number;
    parameters: {
      size: unknown;
      n: unknown;
      prompt_extend: unknown;
      watermark: unknown;
      max_reference_images: unknown;
    };
  };
  credentials: {
    reprovision_required: boolean;
    sources: string[];
    note: string;
  };
};

/* ------------------------------------------- storage generic (owned by UI) */

export type DomainDocumentPayload =
  | ProductInput
  | SemanticAnalysisRecord
  | FactSlot
  | ProductBrief
  | SuitePlan
  | StyleSpec
  | ShotSpec
  | PromptRecord
  | ConfirmationRecord
  | AttemptRecord
  | CandidateRecord
  | ReviewReport
  | SelectionRecord
  | SuiteReviewReport
  | ExportRecordPayload
  | AcknowledgementRecord
  | ShareableConfig
  | Record<string, unknown>;

/** Kind-to-payload map (mirrors storage PAYLOAD_SCHEMA_VERSIONS keys; preserves save/get kind relationship). */
export type DomainDocumentPayloadByKind = {
  product_input: ProductInput;
  semantic_analysis: SemanticAnalysisRecord;
  fact_slot: FactSlot;
  product_brief: ProductBrief;
  suite_plan: SuitePlan;
  style_spec: StyleSpec;
  shot_spec: ShotSpec;
  prompt_version: PromptRecord;
  generation_confirm: ConfirmationRecord;
  generation_attempt: AttemptRecord;
  candidate: CandidateRecord;
  review_report: ReviewReport;
  selection: SelectionRecord;
  suite_review: SuiteReviewReport;
  export_record: ExportRecordPayload;
  review_acknowledgement: AcknowledgementRecord;
};

/* ------------------------------------------- image gateway normalized envelope (P6) */

/**
 * Compile-time projection of the image submit/status normalized envelope.
 *
 * RUNTIME authority is the JSON Schema exported from `src/providers/v2_image.py`
 * (`ImageWire*` Pydantic models) and compiled to a standalone validator at build time;
 * `domain/image-envelope.ts` is the only browser entry that consults it. These types
 * exist so strict TS consumers can read a *validated* envelope without re-deriving the
 * shape; they carry no validation logic and must not be used as a runtime check.
 */
export type ImageWireTaskStatus =
  | "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELED" | "UNKNOWN";

/** Task projection inside the envelope (mirrors `ImageTaskResult.to_dict()`). */
export type ImageWireTask = {
  provider: { provider_id: string; model_id: string };
  task_id: string | null;
  status: ImageWireTaskStatus;
  result_count: number;
  error: string | null;
  request_id: string | null;
  unknown: boolean;
  sync: boolean;
};

/** Failure block inside the envelope; http_status/request_id/details may be absent. */
export type ImageWireError = {
  family: AttemptError["family"];
  code: string;
  message: string;
  retry_policy: AttemptError["retry_policy"];
  http_status?: number | null;
  request_id?: string | null;
  details?: Record<string, unknown> | null;
};

/** `{ok:true, task[, image_*]}` or `{ok:false, error}` — the only two envelope branches. */
export type ImageEnvelopeWire =
  | {
      ok: true;
      unknown: boolean;
      task: ImageWireTask;
      image_base64?: string | null;
      image_media_type?: string | null;
      image_sha256?: string | null;
    }
  | { ok: false; unknown: boolean; error: ImageWireError };

