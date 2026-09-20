/**
 * Backend response types (Phases 3–9).
 * These mirror the FastAPI schemas exactly; no values are invented here.
 */

export type CoverageStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "REQUIRES_ASSUMPTIONS"
  | "NOT_SUPPORTED"
  | string;

export interface StageStatus {
  id: string;
  label: string;
  status: "pending" | "complete" | "failed" | "skipped" | string;
  detail: string | null;
  duration_s: number | null;
}

export interface PipelineInfo {
  status: string | null;
  stages: StageStatus[];
  error: ApiError | null;
}

export interface MlInfo {
  status: string | null;
  models_trained: number;
  anomaly_status: string | null;
  vision_status: string | null;
  error: ApiError | null;
}

export interface VisionRequirements {
  [capability: string]: { label: string; needs: string; minimum: string };
}

export interface VisionBlock {
  status: string;
  available: boolean;
  images_found: number;
  supported_capabilities: string[];
  reason: string | null;
  requirements?: VisionRequirements;
  profile?: unknown;
  image_samples?: string[];
}

export interface ColumnDetail {
  name: string;
  dtype: string;
  role: string;
  station: string | null;
  metric: string | null;
  nulls: number;
  unique: number;
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  std?: number | null;
  samples?: unknown[];
}

export interface TableProfile {
  name: string;
  source_file: string;
  rows: number;
  columns: number;
  numeric_columns: number;
  categorical_columns: number;
  datetime_columns: number;
  null_cells: number;
  null_rate: number;
  duplicate_rows: number | null;
  constant_columns: string[];
  stations: Record<string, Record<string, string[]>>;
  role_counts: Record<string, number>;
  columns_detail: ColumnDetail[];
  warnings: string[];
}

export interface DatasetContract {
  dataset_id: string;
  filename: string;
  format: string;
  size_bytes: number;
  sha256: string;
  status: string;
  ingested_at: string;
  summary: {
    tables: number;
    total_rows: number;
    primary_table: string | null;
    primary_rows: number;
    primary_columns: number;
    stations: string[];
    station_metrics: Record<string, string[]>;
  };
  capabilities: Record<string, boolean>;
  vision: VisionBlock;
  provenance: { data_origin: string; labels: string[]; note: string };
  tables: TableProfile[];
  warnings: string[];
  skipped_files: string[];
  pipeline?: PipelineInfo;
  ml?: MlInfo;
}

export interface DatasetListItem {
  dataset_id: string;
  filename: string | null;
  status: string;
  ingested_at: string | null;
  rows: number | null;
}

export interface ApiError {
  error: boolean;
  code: string;
  message: string;
  detail: string | null;
}

export interface CoverageModule {
  status: CoverageStatus;
  reason: string;
}

export interface Coverage {
  dataset_id: string;
  modules: Record<string, CoverageModule>;
  summary: Record<string, number>;
  legend: Record<string, string>;
}

export interface StationMetricBlock {
  available: boolean;
  mean?: number;
  max?: number;
  min?: number;
  samples?: number;
  reason?: string;
}

export interface StationEntry {
  station_id: string;
  sources: Record<string, string[]>;
  utilization: StationMetricBlock;
  queue_wait: StationMetricBlock;
  wip_storage: StationMetricBlock;
  cycle_time: StationMetricBlock;
  throughput: StationMetricBlock;
  capacity: StationMetricBlock & { note?: string };
  response_stats: StationMetricBlock & { note?: string };
  data_coverage?: { available_metrics: number; tracked_metrics: number; fraction: number };
  warnings?: string[];
}

export interface StationMetricsTable {
  table: string | null;
  station_count: number;
  metric_labels: Record<string, string>;
  stations: StationEntry[];
  dataset_level: {
    output_columns: string[];
    stats: Record<string, unknown> | { available: false; reason: string };
    note: string | null;
  };
  note: string | null;
}

export interface ModelInputSummary {
  name: string;
  status: string;
  origin: string;
  rows: number;
  rows_original: number;
  predictors: string[];
  input_factors: string[];
  responses: string[];
  dropped_missing_response_rows: number;
  dropped_constant_predictors: string[];
  dropped_non_numeric_predictors: string[];
  imputed_cells: Record<string, number>;
  notes: string[];
  split: {
    name: string;
    rows: number;
    seed: number;
    strategy: string | null;
    rationale: string | null;
    group_key: string | null;
    counts: Record<string, number>;
    fallback: boolean;
    status: string;
    reason: string | null;
  } | null;
}

export interface Analysis {
  dataset_id: string;
  filename: string;
  status: string;
  error: ApiError | null;
  generated_at: string;
  processing: { seed: number; configuration: Record<string, unknown>; versions: Record<string, string> };
  stages: StageStatus[];
  total_duration_s: number;
  coverage: Coverage;
  tables: Array<{
    name: string;
    rows: number;
    columns: number;
    role_counts: Record<string, number>;
    stations: string[];
    warnings: string[];
  }>;
  cleaning: { dataset_id: string; tables: Array<Record<string, unknown>> };
  features: {
    dataset_id?: string;
    derived_features: Array<{
      name: string;
      table: string;
      source_columns: string[];
      calculation: string;
      description: string;
      unit: string;
    }>;
    skipped_candidates: Array<{ feature: string; reason: string }>;
  };
  model_inputs: ModelInputSummary[];
  rejected_model_inputs: Array<Record<string, unknown>>;
  splits: { dataset_id?: string; seed?: number; model_input_splits: unknown[]; table_splits: unknown[] };
  station_metrics: { dataset_id?: string; tables: StationMetricsTable[] };
  note?: string;
  artifacts?: Record<string, unknown>;
}

export interface MlModelSummary {
  input: string;
  target: string;
  target_type: string;
  target_info: Record<string, unknown>;
  model_id: string;
  model_type: string;
  status: string;
  candidates: Array<{ model: string; status: string; validation_primary?: Record<string, number | null> }>;
  validation_metrics: Record<string, unknown>;
  test_metrics: Record<string, unknown>;
  baseline: { model: string; test_metrics: Record<string, unknown> | null };
  feature_importance: {
    method: string | null;
    label: string;
    top_features: Array<{ feature: string; importance: number; direction: string | null }>;
  };
  anomaly: {
    status: string;
    method?: string;
    detector_kind?: string;
    features?: string[];
    summary?: Record<string, number>;
    top_examples?: unknown[];
    reason?: string;
  };
  training_seconds: number;
  artifact: { model_id: string; directory: string; files: string[] };
}

export interface MlSummary {
  dataset_id: string;
  status: string;
  error?: ApiError | null;
  models: MlModelSummary[];
  skipped_inputs: Array<Record<string, unknown>>;
  anomaly?: {
    status: string;
    method?: string;
    detector_kind?: string;
    features?: string[];
    summary?: Record<string, number>;
    reason?: string;
    top_examples?: Array<Record<string, unknown>>;
  };
  vision: { status: string; reason: string };
  total_training_seconds?: number;
}

export interface RootCauseSignal {
  available: boolean;
  reason?: string;
  [key: string]: unknown;
}

export interface RootCauseFinding {
  rank: number;
  factor: string;
  station: string | null;
  evidence: {
    correlation: RootCauseSignal & { spearman_r?: number; pearson_r?: number; n?: number };
    mutual_information: RootCauseSignal & { mi?: number; mi_permutation_baseline?: number };
    group_difference: RootCauseSignal & {
      event_mean?: number;
      non_event_mean?: number;
      standardized_effect?: number;
    };
    temporal: RootCauseSignal & { factor_shift_precedes_event_onset?: boolean | null };
    anomaly: RootCauseSignal & { enrichment?: number; event_rate_in_anomalies?: number };
    model_contribution: {
      available: boolean;
      importance?: number | null;
      max_importance?: number | null;
      method?: string | null;
      label?: string;
      reason?: string | null;
    };
  };
  evidence_score: number | null;
  score_status: string;
  score_components: Record<string, number | null>;
  score_weights: Record<string, number> | null;
  score_formula: string;
  association_status: string;
  epistemic_status: string;
  explanation: string;
  source_columns: string[];
  limitations: string[];
}

export interface DriftColumn {
  column: string;
  rows: number;
  baseline_mean: number;
  baseline_std: number;
  peak_ewma_z: number;
  peak_position: number;
  change_position: number;
  drift_detected: boolean;
  direction: string;
}

export interface DriftResult {
  status: string;
  reason?: string;
  order_column?: string;
  method?: string;
  configuration?: Record<string, number>;
  columns_analyzed?: number;
  columns_drifted?: number;
  columns?: DriftColumn[];
  note?: string;
}

export interface RootCauseAnalysis {
  dataset_id: string;
  analysis_id: string;
  status: string;
  target: { target: string; input: string; mode: string; rows: number; rows_with_target: number; model_id?: string | null };
  event: { target: string; direction: string; quantile: number; threshold: number; definition: string; event_rows: number; non_event_rows: number };
  generated_at: string;
  engine_version: string;
  factors_analyzed: number;
  ranked_findings: RootCauseFinding[];
  station_ranking: Array<{
    station: string;
    factors: number;
    best_score: number | null;
    best_factor: string | null;
    ranked_factors: Array<{ factor: string; score: number | null; rank: number }>;
  }>;
  drift: DriftResult;
  epistemic_summary: Record<string, string>;
  limitations: string[];
  total_duration_s: number;
}

export interface BottleneckFinding {
  station: string;
  rank: number;
  status: string;
  evidence_score: number | null;
  score_status: string;
  score_components: Record<string, number | null>;
  score_weights: Record<string, number> | null;
  score_formula: string;
  available_components: number;
  consistency: number | null;
  evidence_quality: { label: string; reason: string };
  utilization: StationMetricBlock;
  queue: StationMetricBlock;
  cycle_time: StationMetricBlock;
  throughput: StationMetricBlock;
  capacity: StationMetricBlock;
  anomaly_evidence: { available: boolean; rates: Record<string, { rows: number; anomalous_rows: number; anomaly_rate: number; file: string }>; note: string };
  drift_evidence: Array<{ column: string; metric: string; peak_ewma_z: number; direction: string; change_position: number }>;
  root_cause_evidence: { best_score: number | null; best_factor: string | null; factors: Array<{ factor: string; score: number | null }> } | null;
  unavailable_metrics: string[];
  impact: {
    status: string;
    reason?: string;
    observed?: Record<string, { output_column: string; constrained_mean: number; unconstrained_mean: number; difference: number; relative_difference: number | null; constrained_rows: number; unconstrained_rows: number; constrained_definition: string }>;
    epistemic_status?: string;
    note?: string;
    limitations?: string[];
  } | null;
  assumptions: string[];
  limitations: string[];
  epistemic_status: string;
}

export interface FlowGraph {
  status: string;
  reason?: string;
  rationale?: string;
  nodes: Array<{ station: string; position?: number; rank?: number | null; metrics: Record<string, unknown> }>;
  edges: Array<{ from: string; to: string }>;
  stations_outside_sequence?: string[];
  note?: string;
}

export interface BottleneckAnalysis {
  dataset_id: string;
  analysis_id: string;
  status: string;
  generated_at: string;
  engine_version: string;
  stations_analyzed: number;
  station_rankings: BottleneckFinding[];
  candidate_bottleneck: {
    station: string | null;
    evidence_score: number | null;
    evidence_quality: { label: string; reason: string } | null;
    status: string;
    why: string[];
    unavailable_metrics: string[];
  };
  flow: {
    graph: FlowGraph;
    blocking_starvation: Record<string, { status: string; reason: string }>;
  };
  what_if_inputs: {
    station: string | null;
    current_utilization: StationMetricBlock | null;
    current_queue: StationMetricBlock | null;
    current_cycle_time: StationMetricBlock | null;
    observed_impact: BottleneckFinding["impact"];
    potential_interventions: string[];
    expected_effect: string;
    note: string;
  };
  epistemic_summary: Record<string, string>;
  limitations: string[];
  total_duration_s: number;
}

export interface AssumptionEntry {
  value: number | null;
  unit: string;
  source: string;
  provided_at: string | null;
  notes: string | null;
}

export interface AssumptionsPayload {
  dataset_id: string;
  currency: { value: string | null; source: string };
  assumptions: Record<string, AssumptionEntry>;
  updated_at: string | null;
  note: string;
}

export interface EconomicsBlock {
  status: string;
  value: number | null;
  missing_inputs: string[];
  formula: string;
  inputs: Record<string, unknown>;
  epistemic_status: string;
}

export interface BaselinePayload {
  dataset_id: string;
  generated_at: string;
  bottleneck_analysis_id: string | null;
  bottleneck_station: string | null;
  throughput_source: string | null;
  currency: string | null;
  baseline: {
    currency: string | null;
    throughput_per_hour: { value: number | null; epistemic_status: string; source: string };
    units_per_day: EconomicsBlock;
    daily_contribution: EconomicsBlock;
    monthly_contribution: EconomicsBlock;
    note: string;
  };
  availability: { bottleneck_available: boolean; throughput_available: boolean; assumptions_supplied: string[] };
  epistemic_status: string;
  limitations: string[];
}

export interface ScenarioPayload {
  dataset_id: string;
  scenario_id: string;
  generated_at: string;
  bottleneck: { analysis_id: string | null; station: string | null; evidence_quality: { label: string } | null; status: string | null };
  scenario_type: string;
  parameter_changes: Record<string, unknown>;
  baseline: {
    throughput_per_hour: number | null;
    throughput_source: string | null;
    units_per_day: number | null;
    utilization: number | null;
    queue: number | null;
    cycle_time: number | null;
    epistemic_status: string;
    economics: BaselinePayload["baseline"];
  };
  scenario: { metrics: Record<string, { baseline: number; scenario: number; epistemic_status: string }>; units_per_day: number | null; epistemic_status: string };
  economic_output: {
    units_per_day_delta: EconomicsBlock;
    daily_contribution_delta: EconomicsBlock;
    monthly_contribution_delta: EconomicsBlock;
    cost_blocks: Record<string, EconomicsBlock>;
    net_daily_impact: EconomicsBlock & { cost_total?: number; cost_blocks_included?: string[]; cost_blocks_missing?: string[]; note?: string };
    epistemic_status: string;
  };
  simulation_method: string | null;
  assumptions_snapshot: AssumptionsPayload;
  warnings: string[];
  limitations: string[];
  epistemic_status: string;
  sensitivity?: {
    scenario_type: string;
    parameter: string;
    points: Array<{ parameter_value: number; units_per_day_delta?: number | null; daily_contribution_delta?: number | null; net_daily_impact?: number | null; status: string; reason?: string }>;
    epistemic_status: string;
  };
}

export interface Recommendation {
  recommendation_id: string;
  dataset_id: string;
  analysis_id: string | null;
  action_type: string;
  title: string;
  target: string;
  station: string | null;
  priority: number | null;
  priority_components: {
    score: number;
    components: Record<string, number>;
    weights: Record<string, number>;
    formula: string;
  } | null;
  evidence_quality: string;
  why: string;
  evidence: Array<{
    statement: string;
    detail: string;
    source_artifact: string;
    epistemic_status: string;
    value: number | string | null;
  }>;
  assumptions: Array<Record<string, unknown>>;
  simulated_effect: Record<string, unknown> | null;
  economic_effect: Record<string, unknown> | null;
  limitations: string[];
  epistemic_status: string;
  data_requirement: boolean;
  source_artifacts: string[];
  generated_at: string;
  engine_version: string;
  rank: number;
}

export interface DecisionSummary {
  dataset_id: string;
  generated_at: string;
  engine_version: string;
  situation: Record<string, string | number | null>;
  quality_status: string;
  process_status: Record<string, unknown>;
  bottleneck_status: Record<string, string | null>;
  throughput_status: Record<string, unknown>;
  economic_status: Record<string, unknown>;
  recommendations: string[];
  data_gaps: Array<{ gap: string; action_type: string; why: string }>;
  assumptions: Array<{ field: string; value: number | null; unit: string; source: string }>;
  limitations: string[];
  epistemic_status: string;
}

export interface RecommendationRun {
  dataset_id: string;
  status: string;
  generated_at: string;
  engine_version: string;
  rule_trace: Array<Record<string, unknown>>;
  duplicates_removed: string[];
  recommendation_count: number;
  recommendations: Recommendation[];
  decision_summary: DecisionSummary;
  source_artifacts: string[];
  total_duration_s: number;
}

export interface RecommendationListResponse {
  dataset_id: string;
  recommendations: Array<{
    recommendation_id: string;
    action_type: string;
    title: string;
    target: string;
    station: string | null;
    priority: number | null;
    evidence_quality: string;
    rank: number;
    generated_at: string;
  }>;
  count: number;
  decision_summary: DecisionSummary | null;
}

// ---------------------------------------------------------------------------
// Phase 12 - vision inspection
// ---------------------------------------------------------------------------

export interface VisionThresholds {
  pass_confidence: number;
  defect_confidence: number;
  anomaly_review_percentile: number;
  note?: string;
}

export interface VisionMetrics {
  accuracy: number;
  f1_weighted: number;
  val_accuracy: number;
  false_accept_rate: number | null;
  false_reject_rate: number | null;
  review_rate: number;
  decisions: { PASS: number; DEFECT: number; REVIEW: number };
  decision_matrix?: Array<{ actual: string; counts: Record<string, number> }>;
  decision_matrix_columns?: string[];
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  confusion_matrix: number[][];
}

export interface VisionModelStatus {
  status: "READY" | "NOT_TRAINED";
  model_available: boolean;
  reason?: string;
  classes?: string[];
  normal_class?: string;
  metrics?: VisionMetrics;
  thresholds?: VisionThresholds;
  temperature?: number;
  metadata?: {
    backbone?: { name: string; pretrained: string; frozen: boolean; embedding_dim: number };
    images?: { total_available: number; train: number; validation: number; test: number };
    split?: { strategy: string; seed: number };
    trained_at?: string;
    timings?: { embedding_seconds?: number; total_seconds?: number };
    localization?: string;
    calibration?: string;
  };
  dataset_dir?: string;
  dataset_available?: boolean;
  requirements?: { needs: string; minimum: string };
}

export interface VisionTraceStage {
  id: string;
  label?: string;
  status: string;
  started_at: string;
  duration_ms: number;
  summary: string;
  metrics: Record<string, unknown>;
}

export interface VisionInspection {
  inspection_id: string;
  filename: string | null;
  generated_at: string;
  image_metadata: { width: number; height: number; mode: string; format: string; bytes: number };
  preprocessing: { resize: string; normalization: string; preprocessed_png_base64?: string; note?: string };
  prediction: { predicted_class: string; is_normal: boolean };
  feature_vector?: { dim: number; values: number[]; note?: string };
  class_distances?: Record<string, number>;
  feature_space_point?: number[] | null;
  class_probabilities: Record<string, number>;
  confidence: {
    value: number;
    raw_probability?: number;
    level: string;
    method: string;
    calibration_status?: string;
    calibration_method?: string;
    model_version?: string | null;
    limitations: string;
  };
  anomaly_score: {
    value: number;
    novelty_score: number;
    novelty_status: string;
    method: string;
    note: string;
  };
  localization: {
    type: string;
    method: string;
    ground_truth: boolean;
    bounding_box: { x: number; y: number; width: number; height: number; coordinates: string; type: string } | null;
    heatmap_png_base64?: string;
    note: string;
  };
  decision: "PASS" | "DEFECT" | "REVIEW";
  decision_reason?: string;
  review_reason: string | null;
  review_reasons?: string[];
  human_review?: {
    action: string;
    action_label: string;
    decision: string;
    at: string;
    note: string | null;
    ai_decision_preserved: string;
  } | null;
  evidence: Array<{ statement: string; source: string; epistemic_status: string }>;
  process_link: { status: string; reason: string; available_metadata: string[] };
  model: { backbone?: string; trained_at?: string; classes: string[] };
  limitations: string[];
  trace: VisionTraceStage[];
}

export interface VisionInspectionSummary {
  inspection_id: string;
  filename: string | null;
  decision: string;
  predicted_class: string;
  confidence: number;
  anomaly_score: number;
  novelty_status: string;
  generated_at: string;
}

// ---------------------------------------------------------------------------
// V2 - production stream, investigations, feature space, process timeline
// ---------------------------------------------------------------------------

export interface StreamFrame {
  class_folder: string;
  filename: string;
}

export interface StreamSummary {
  inspection_id: string;
  filename: string | null;
  class_folder: string;
  decision: string;
  predicted_class: string;
  confidence: number;
  novelty_status: string;
  at: string;
}

export interface StreamStatus {
  label: string;
  note: string;
  station_id: string;
  dataset_available: boolean;
  dataset_error: string | null;
  running: boolean;
  speed: number;
  speeds: number[];
  cursor: number;
  frame_number: number;
  total_frames: number;
  processed: number;
  remaining: number;
  session_started_at: string | null;
  source: StreamSourceInfo | null;
  next_frame: StreamFrame | null;
  class_plan: {
    order: string;
    counts: Record<string, number>;
    normal_class: string;
    total_frames: number;
  } | null;
  last_summary: StreamSummary | null;
  history: StreamSummary[];
  decision_counts: Record<string, number>;
}

export interface StreamNextResponse {
  inspection: VisionInspection | null;
  exhausted: boolean;
  status: StreamStatus;
}

export interface InvestigationStage {
  id: string;
  label: string;
  status: "COMPLETE" | "REVIEW" | "DATA_GAP" | "AWAITING_INPUT" | "FAILED" | "PARTIAL";
  summary: string;
  detail: string | null;
  epistemic: string;
  payload: Record<string, unknown> | null;
  duration_ms: number | null;
  required_inputs?: string[];
  available_inputs?: string[];
}

export interface InvestigationEvent {
  at: string;
  type: string;
  message: string;
  epistemic: string;
  investigation_id: string;
  inspection_id: string | null;
}

export interface InvestigationSummary {
  investigation_id: string;
  inspection_id: string | null;
  source_id: string | null;
  dataset_id: string | null;
  generated_at: string;
  status: string;
  decision: string;
  predicted_class: string | null;
  confidence: number | null;
  filename: string | null;
  stage_summary: { complete: number; data_gap: number; awaiting_input: number; failed: number; partial: number };
  top_action: string | null;
}

export interface InvestigationRecord extends InvestigationSummary {
  station_id: string | null;
  anomaly_score: number | null;
  novelty_status: string | null;
  review_reason: string | null;
  stages: InvestigationStage[];
  total_duration_s: number;
  limitations: string[];
  events: InvestigationEvent[];
}

export interface FeatureSpacePayload {
  status: "AVAILABLE" | "NOT_TRAINED" | "NOT_AVAILABLE";
  reason?: string;
  method?: string;
  components?: number;
  explained_variance_ratio?: number[];
  sampling?: string;
  clouds: Record<string, number[][]>;
  counts?: Record<string, number>;
}

export interface ProcessTimeline {
  dataset_id: string;
  status: "AVAILABLE" | "NOT_AVAILABLE";
  reason?: string;
  table?: string;
  bins?: number;
  order_basis?: string;
  series: Array<{
    station: string;
    metric: string;
    unit: string;
    column: string;
    values: number[];
  }>;
  drift_markers: Array<{ column: string; bin: number; direction: string; peak_ewma_z: number; epistemic: string }>;
  event_markers: Array<{ bin: number; label: string }>;
  event_definition: { target: string; direction: string; threshold: number; definition: string; epistemic: string } | null;
  note?: string;
  limitations?: string[];
}

// ---------------------------------------------------------------------------
// V2.1 - batch/dataset inspection and the human review queue
// ---------------------------------------------------------------------------

export interface BatchImage {
  original_name: string;
  size_bytes: number;
  class_folder: string | null;
  sha256: string | null;
  status: "valid" | "invalid" | "unsupported" | "duplicate";
  reason: string | null;
  width: number | null;
  height: number | null;
  format: string | null;
  inspection_id?: string | null;
}

export interface BatchSummary {
  total: number;
  valid: number;
  invalid: number;
  unsupported: number;
  duplicates: number;
  classes: string[];
  class_counts: Record<string, number>;
  labels_available: boolean;
  labels_note: string;
  class_balance: string;
  localization_annotations: string;
  localization_note: string;
  process_join: string;
  process_join_note: string;
}

export interface BatchQuality {
  basis: string;
  tp: number;
  tn: number;
  fp: number;
  fn: number;
  false_accept_rate: number | null;
  false_reject_rate: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  review_rate: number | null;
  note: string;
}

export interface BatchResult {
  index: number;
  inspection_id: string;
  filename: string | null;
  class_folder: string | null;
  ground_truth: string | null;
  decision: string;
  confidence: number;
  raw_probability?: number | null;
  anomaly_score: number;
  novelty_score: number;
  novelty_status: string;
  localization: boolean;
  review_reason: string | null;
  review_reasons: string[];
}

export interface BatchRecord {
  batch_id: string;
  created_at: string;
  status: "validated" | "inspecting" | "complete" | "failed";
  source: string;
  summary: BatchSummary;
  images: BatchImage[];
  progress: { inspected: number; total: number };
  decisions: { PASS: number; DEFECT: number; REVIEW: number };
  review_queue: number;
  quality: BatchQuality | null;
  results: BatchResult[];
  avg_confidence: number | null;
  duration_s?: number;
  note: string;
}

export type SourceType = "SINGLE_IMAGE" | "IMAGE_SET" | "FOLDER_DATASET" | "BUILT_IN_DEMO";

export interface InspectionSource extends BatchRecord {
  source_id: string;
  source_type: SourceType;
  type_label: string;
  display_name: string;
  demo_note?: string;
  stream?: { cursor: number; processed: number; running: boolean; history: unknown[] };
}

export interface SourceSummary {
  source_id: string;
  source_type: SourceType;
  type_label: string;
  display_name: string;
  created_at: string | null;
  status: string;
  summary: BatchSummary | null;
  progress: { inspected: number; total: number } | null;
  decisions: { PASS: number; DEFECT: number; REVIEW: number } | null;
  review_queue: number | null;
  stream: { cursor: number; processed: number; running: boolean } | null;
}

export interface StreamSourceInfo {
  source_id: string;
  source_type: SourceType;
  type_label: string;
  display_name: string;
  image_count: number;
  total: number;
  labels_available: boolean;
}

export interface BatchSummaryListItem {
  batch_id: string;
  created_at: string | null;
  status: string;
  summary: BatchSummary | null;
  progress: { inspected: number; total: number } | null;
  decisions: { PASS: number; DEFECT: number; REVIEW: number } | null;
  review_queue: number | null;
}

export interface ReviewQueueItem {
  inspection_id: string;
  source_id: string | null;
  filename: string | null;
  generated_at: string;
  predicted_class: string | null;
  confidence: number | null;
  anomaly_score: number | null;
  novelty_score: number | null;
  novelty_status: string | null;
  localization: boolean;
  review_reason: string | null;
  review_reasons: string[];
  human_review: VisionInspection["human_review"];
}

export interface ReviewStats {
  total: number;
  auto_resolved: number;
  human_reviewed: number;
  pending_review: number;
  auto_resolved_rate: number | null;
  human_review_rate: number | null;
  pending_review_rate: number | null;
  distribution: { PASS: number; DEFECT: number; REVIEW: number };
  distribution_rates: { PASS: number; DEFECT: number; REVIEW: number };
  avg_confidence: number | null;
  note: string;
}

export interface HumanReviewResponse {
  inspection_id: string;
  human_review: VisionInspection["human_review"];
  ai_decision: string | null;
  ai_confidence: number | null;
  note: string;
}
