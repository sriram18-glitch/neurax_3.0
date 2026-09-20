import type {
  AssumptionsPayload,
  BottleneckAnalysis,
  DatasetContract,
  MlSummary,
  RecommendationListResponse,
  RootCauseAnalysis,
  VisionInspection,
  VisionModelStatus,
  VisionTraceStage,
} from "../../types/api";
import type { GraphEdge, GraphNode } from "./EvidenceGraph";
import type { PipelineStage } from "./ProcessingPipeline";
import type { TraceStep } from "./DecisionTrace";
import type { CapabilityNode } from "./SystemStatus";

export const STAGE_ORDER = [
  "image_received",
  "validation",
  "preprocessing",
  "feature_extraction",
  "classification",
  "anomaly_analysis",
  "localization",
  "confidence",
  "decision",
  "process_link",
];

/** Merge live streamed stages with the stored trace of a completed inspection. */
export function pipelineStages(liveStages: VisionTraceStage[], inspection: VisionInspection | null): PipelineStage[] {
  const source = liveStages.length > 0 ? liveStages : (inspection?.trace ?? []);
  const byId = new Map(source.map((stage) => [stage.id, stage]));
  return STAGE_ORDER.map((id) => {
    const stage = byId.get(id);
    return {
      name: id,
      status: stage ? (stage.status === "complete" ? "complete" : "active") : "pending",
      duration_ms: stage?.duration_ms ?? null,
      metrics: stage ? { summary: stage.summary, ...stage.metrics } : null,
    };
  });
}

export function activeStageId(liveStages: VisionTraceStage[], streaming: boolean): string | null {
  if (!streaming) return null;
  const completed = new Set(liveStages.map((stage) => stage.id));
  return STAGE_ORDER.find((id) => !completed.has(id)) ?? null;
}

/** Evidence graph of a single visual inspection - every node is real output. */
export function inspectionGraph(inspection: VisionInspection): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const probability = inspection.class_probabilities[inspection.prediction.predicted_class];
  const nodes: GraphNode[] = [
    {
      id: "image",
      label: inspection.filename ?? "inspected unit",
      kind: "source",
      epistemic: "OBSERVED",
      detail: `${inspection.image_metadata.width}×${inspection.image_metadata.height} ${inspection.image_metadata.format}`,
      value: `${inspection.image_metadata.bytes} B`,
      column: 0,
    },
    {
      id: "backbone",
      label: "Frozen backbone embedding",
      kind: "stage",
      epistemic: "MODEL OUTPUT",
      detail: inspection.model.backbone ?? "pretrained visual backbone",
      value: inspection.feature_vector ? `${inspection.feature_vector.dim}-d` : null,
      column: 1,
    },
    {
      id: "classification",
      label: "Class assignment",
      kind: "stage",
      epistemic: "MODEL OUTPUT",
      detail: `calibrated probability for '${inspection.prediction.predicted_class}'`,
      value: probability !== undefined ? `${(probability * 100).toFixed(1)}%` : null,
      column: 2,
    },
    {
      id: "anomaly",
      label: "Anomaly percentile",
      kind: "signal",
      epistemic: "MODEL OUTPUT",
      detail: "Mahalanobis distance percentile vs normal reference",
      value: inspection.anomaly_score.value.toFixed(3),
      column: 2,
    },
    {
      id: "localization",
      label: "Attention region",
      kind: "signal",
      epistemic: "MODEL-DERIVED",
      detail: "class-activation map - not a ground-truth defect boundary",
      value: inspection.localization.bounding_box ? "region found" : "no region",
      column: 2,
    },
    {
      id: "confidence",
      label: "Calibrated confidence",
      kind: "stage",
      epistemic: "CALCULATED",
      detail: inspection.confidence.method,
      value: `${(inspection.confidence.value * 100).toFixed(1)}%`,
      column: 3,
    },
    {
      id: "novelty",
      label: "Novelty check",
      kind: "signal",
      epistemic: "MODEL OUTPUT",
      detail: `distance to the '${inspection.prediction.predicted_class}' known cluster`,
      value: inspection.anomaly_score.novelty_status,
      column: 3,
    },
    {
      id: "decision",
      label: `Decision: ${inspection.decision}`,
      kind: "decision",
      epistemic: "MODEL OUTPUT",
      detail: inspection.review_reason ?? "threshold rules applied to calibrated confidence and anomaly",
      value: inspection.decision,
      column: 4,
    },
    {
      id: "process",
      label: "Process context",
      kind: "source",
      epistemic: "NOT AVAILABLE",
      detail: inspection.process_link.reason,
      value: inspection.process_link.status,
      column: 0,
    },
  ];
  const edges: GraphEdge[] = [
    { from: "image", to: "backbone", label: "pixels" },
    { from: "backbone", to: "classification", label: "1280-d" },
    { from: "backbone", to: "anomaly" },
    { from: "backbone", to: "localization" },
    { from: "classification", to: "confidence", label: "temperature" },
    { from: "classification", to: "novelty" },
    { from: "confidence", to: "decision", label: "thresholds" },
    { from: "anomaly", to: "decision", label: "gate" },
    { from: "novelty", to: "decision" },
    { from: "localization", to: "decision" },
  ];
  return { nodes, edges };
}

/** Data-lineage steps for the decision trace panel. */
export function inspectionTraceSteps(inspection: VisionInspection): TraceStep[] {
  const steps: TraceStep[] = inspection.trace.map((stage) => ({
    label: stage.label ?? stage.id.replace(/_/g, " "),
    detail: `${stage.summary} (${stage.duration_ms.toFixed(1)} ms)`,
    epistemic: stage.status === "not_supported" ? "NOT AVAILABLE" : "MODEL OUTPUT",
  }));
  for (const entry of inspection.evidence) {
    steps.push({ label: "evidence", detail: entry.statement, epistemic: entry.epistemic_status.replace(/_/g, " ") });
  }
  return steps;
}

/** Root-cause factor graph: event → associated factors → ranked hypothesis. */
export function rootCauseGraph(rootCause: RootCauseAnalysis): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const top = rootCause.ranked_findings.slice(0, 3);
  const nodes: GraphNode[] = [
    {
      id: "event",
      label: `${rootCause.event.target} ${rootCause.event.direction}`,
      kind: "source",
      epistemic: "OBSERVED",
      detail: `event = ${rootCause.event.definition} · ${rootCause.event.event_rows} of ${rootCause.event.event_rows + rootCause.event.non_event_rows} rows`,
      value: `q=${rootCause.event.quantile}`,
      column: 0,
    },
    ...top.map((finding, index) => ({
      id: `factor-${index}`,
      label: finding.factor,
      kind: "signal" as const,
      epistemic: "STATISTICAL ASSOCIATION",
      detail: finding.association_status.replace(/_/g, " "),
      value: finding.evidence_score !== null ? `score ${finding.evidence_score.toFixed(1)}` : "not scored",
      column: 1,
    })),
    {
      id: "hypothesis",
      label: top[0] ? `${top[0].factor} is the leading association` : "No factor reached scoring",
      kind: "action",
      epistemic: "ADVISORY",
      detail: `${rootCause.factors_analyzed} factors analyzed · ${rootCause.drift.columns_drifted ?? 0} columns drifted · association is not causation`,
      value: top[0]?.evidence_score !== null && top[0] ? `score ${top[0].evidence_score.toFixed(1)}` : null,
      column: 2,
    },
  ];
  const edges: GraphEdge[] = top.map((finding, index) => ({
    from: "event",
    to: `factor-${index}`,
    strength: finding.evidence_score !== null ? Math.min(1, finding.evidence_score / 100) : null,
  }));
  if (top.length > 0) edges.push({ from: "factor-0", to: "hypothesis", label: "leading" });
  return { nodes, edges };
}

export function rootCauseRanked(rootCause: RootCauseAnalysis) {
  return rootCause.ranked_findings.slice(0, 8).map((finding, index) => {
    const factors: Array<{ name: string; value: number }> = [];
    const correlation = finding.evidence.correlation;
    if (correlation.available && correlation.spearman_r !== null && correlation.spearman_r !== undefined) {
      factors.push({ name: "spearman rho", value: correlation.spearman_r });
    }
    const mutual = finding.evidence.mutual_information;
    if (mutual.available && mutual.mi !== null && mutual.mi !== undefined) {
      factors.push({ name: "mutual information", value: mutual.mi });
    }
    const model = finding.evidence.model_contribution;
    if (model.available && model.importance !== null && model.importance !== undefined) {
      factors.push({ name: "model importance", value: model.importance });
    }
    return {
      id: finding.factor,
      rank: index + 1,
      label: finding.factor,
      score: finding.evidence_score ?? 0,
      detail: `${finding.association_status.replace(/_/g, " ").toLowerCase()} · ${finding.station ?? "no station mapping"}`,
      epistemic: "STATISTICAL ASSOCIATION",
      factors,
    };
  });
}

export function bottleneckRanked(bottleneck: BottleneckAnalysis) {
  return bottleneck.station_rankings.map((finding) => ({
    id: finding.station,
    rank: finding.rank,
    label: finding.station,
    score: finding.evidence_score ?? 0,
    detail: `${finding.status.replace(/_/g, " ").toLowerCase()} · ${finding.evidence_quality.label.replace(/_/g, " ").toLowerCase()} (${finding.available_components} components)`,
    epistemic: "EVIDENCE-BASED HYPOTHESIS",
    factors: Object.entries(finding.score_components)
      .filter(([, value]) => value !== null)
      .map(([name, value]) => ({ name, value: value as number })),
  }));
}

export function commandNodes(input: {
  visionStatus: VisionModelStatus | null;
  contract: DatasetContract | null;
  ml: MlSummary | null;
  rootCause: RootCauseAnalysis | null;
  bottleneck: BottleneckAnalysis | null;
  assumptions: AssumptionsPayload | null;
  recommendations: RecommendationListResponse | null;
  datasetCount: number;
}): CapabilityNode[] {
  const { visionStatus, contract, ml, rootCause, bottleneck, assumptions, recommendations, datasetCount } = input;
  const supplied = assumptions ? Object.values(assumptions.assumptions).filter((entry) => entry.value !== null).length : 0;
  if (!visionStatus) {
    return [
      {
        id: "vision",
        label: "Visual inspection",
        status: "standby",
        detail: "connecting to the vision service…",
        metric: null,
      },
      ...processNodes({ contract, ml, rootCause, bottleneck, supplied, recommendations, datasetCount }),
    ];
  }
  const visionReady = visionStatus.status === "READY";
  return [
    {
      id: "vision",
      label: "Visual inspection",
      status: visionReady ? "operational" : visionStatus.dataset_available ? "standby" : "not_available",
      detail: visionReady
        ? `${visionStatus.classes?.length ?? 0} classes · calibrated · localization model-derived`
        : "vision model not trained — open Inspection to train it",
      metric: visionReady
        ? {
            value: visionStatus.metrics ? visionStatus.metrics.accuracy * 100 : null,
            digits: 1,
            suffix: "%",
            label: "test accuracy",
          }
        : null,
    },
    ...processNodes({ contract, ml, rootCause, bottleneck, supplied, recommendations, datasetCount }),
  ];
}

function processNodes(input: {
  contract: DatasetContract | null;
  ml: MlSummary | null;
  rootCause: RootCauseAnalysis | null;
  bottleneck: BottleneckAnalysis | null;
  supplied: number;
  recommendations: RecommendationListResponse | null;
  datasetCount: number;
}): CapabilityNode[] {
  const { contract, ml, rootCause, bottleneck, supplied, recommendations, datasetCount } = input;
  return [
    {
      id: "process",
      label: "Process datasets",
      status: contract ? "operational" : datasetCount > 0 ? "available" : "not_available",
      detail: contract ? `${contract.filename} · ${contract.summary.total_rows} rows` : `${datasetCount} dataset(s) stored — none loaded`,
      metric: contract ? { value: contract.summary.stations.length, label: "stations detected" } : null,
    },
    {
      id: "models",
      label: "Process models",
      status: ml && ml.models.length > 0 ? "operational" : contract ? "available" : "not_available",
      detail: ml && ml.models.length > 0 ? `${ml.models.length} trained model(s) on model inputs` : "no process model trained",
      metric: ml && ml.models.length > 0 ? { value: ml.models.length, label: "models" } : null,
    },
    {
      id: "rootcause",
      label: "Root-cause engine",
      status: rootCause ? "operational" : contract ? "available" : "not_available",
      detail: rootCause
        ? `${rootCause.factors_analyzed} factors analyzed · drift: ${rootCause.drift.status}`
        : "association analysis not run for this session",
      metric: rootCause ? { value: rootCause.ranked_findings.length, label: "ranked findings" } : null,
    },
    {
      id: "flow",
      label: "Flow & bottleneck",
      status: bottleneck ? "operational" : contract ? "available" : "not_available",
      detail: bottleneck
        ? bottleneck.candidate_bottleneck.station
          ? `candidate: ${bottleneck.candidate_bottleneck.station}`
          : "no candidate constraint identified"
        : "flow analysis not run for this session",
      metric: bottleneck ? { value: bottleneck.stations_analyzed, label: "stations analyzed" } : null,
    },
    {
      id: "economics",
      label: "Economic model",
      status: supplied > 0 ? "operational" : "standby",
      detail: supplied > 0 ? `${supplied} user assumption(s) supplied` : "requires user-supplied assumptions — none invented",
      metric: null,
    },
    {
      id: "recommend",
      label: "Recommendations",
      status: recommendations && recommendations.count > 0 ? "operational" : contract ? "available" : "not_available",
      detail:
        recommendations && recommendations.count > 0
          ? `${recommendations.count} advisory action(s) from deterministic rules`
          : "no recommendations generated for this session",
      metric: recommendations && recommendations.count > 0 ? { value: recommendations.count, label: "actions" } : null,
    },
  ];
}