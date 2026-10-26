export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8001";

const TOKEN_KEY = "sirep.token";
const ORG_KEY = "sirep.org";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function getOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ORG_KEY);
}

export function setOrgId(id: string): void {
  window.localStorage.setItem(ORG_KEY, id);
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(ORG_KEY);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const org = getOrgId();
  if (org) headers.set("X-Organization-Id", org);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.error?.message ?? `Error ${response.status}`;
    throw new ApiError(message, response.status, data?.error?.code);
  }
  return data as T;
}

export async function downloadExport(analysisId: string, fmt: "json" | "markdown"): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const org = getOrgId();
  if (org) headers.set("X-Organization-Id", org);
  const response = await fetch(`${API_BASE}/api/v1/analyses/${analysisId}/export?fmt=${fmt}`, {
    method: "POST",
    headers,
  });
  if (!response.ok) throw new ApiError(`Error al exportar (${response.status})`, response.status);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `report-${analysisId}.${fmt === "json" ? "json" : "md"}`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export type User = { id: string; email: string; display_name: string; created_at: string };
export type Session = { token: string; expires_at: string; user: User };
export type Organization = { id: string; name: string; slug: string; role: string; created_at: string };
export type Project = {
  id: string;
  organization_id: string;
  name: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};
export function deleteProject(projectId: string): Promise<Project> {
  return api<Project>(`/api/v1/projects/${projectId}`, { method: "DELETE" });
}

export type Artifact = {
  id: string;
  project_id: string;
  kind: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  detected_mime: string;
  declared_mime: string | null;
  validation_state: string;
  retention_policy: string;
  created_at: string;
};
export type Job = {
  id: string;
  project_id: string;
  artifact_id: string;
  status: string;
  phase: string | null;
  progress_completed: number;
  progress_total: number;
  error_code: string | null;
  error_message: string | null;
  result_summary: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};
export type Finding = {
  id: string;
  analysis_id: string;
  category: string;
  severity: string;
  language: string | null;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  symbol: string | null;
  evidence_level: string;
  detection_method: string;
  tool: string;
  tool_version: string | null;
  snippet: string | null;
  message: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};
export type AnalysisSummary = {
  job: Job;
  finding_count: number;
  findings_by_severity: Record<string, number>;
  findings_by_category: Record<string, number>;
  node_count: number;
  edge_count: number;
  dependency_count: number;
  languages: string[];
  files_analyzed: number;
  progress_formula: string;
};
export type GraphNode = {
  id: string;
  node_type: string;
  label: string;
  path: string | null;
  language: string | null;
  evidence_level: string;
  detection_method: string;
  metadata: Record<string, unknown> | null;
};
export type GraphEdge = {
  id: string;
  source_node_id: string;
  target_node_id: string | null;
  target_ref: string | null;
  edge_type: string;
  evidence_level: string;
  detection_method: string;
  metadata: Record<string, unknown> | null;
};
export type Dependency = {
  id: string;
  ecosystem: string;
  name: string;
  version: string | null;
  source_file: string;
  evidence_level: string;
};
export type ArchitectureGraph = {
  analysis_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  dependencies: Dependency[];
  node_count: number;
  edge_count: number;
  dependency_count: number;
  confirmed_edge_count: number;
  inferred_edge_count: number;
  node_type_counts?: Record<string, number>;
  edge_type_counts?: Record<string, number>;
};
export type NodeDetail = {
  node: GraphNode;
  outgoing_edges: GraphEdge[];
  incoming_edges: GraphEdge[];
  neighbors: GraphNode[];
};

export type ChangeFile = {
  id: string;
  path: string;
  change_type: "ADDED" | "MODIFIED" | "DELETED";
  base_sha256: string | null;
  new_sha256: string | null;
  applied_sha256: string | null;
  unified_diff: string | null;
  created_at: string;
};

export type ChangeApproval = {
  id: string;
  change_set_id: string;
  user_id: string;
  decision: string;
  comment: string | null;
  created_at: string;
};

export type ChangeSet = {
  id: string;
  analysis_id: string;
  project_id: string;
  status: string;
  workspace_path: string;
  base_artifact_sha256: string | null;
  reason: string;
  produced_by_rule: string;
  reversible: boolean;
  external_effects: string | null;
  validation_result: Record<string, unknown> | null;
  associated_tests: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  approved_by: string | null;
  approved_at: string | null;
  applied_at: string | null;
  validated_at: string | null;
  rolled_back_at: string | null;
};

export type ChangeSetDetail = ChangeSet & {
  files: ChangeFile[];
  approvals: ChangeApproval[];
};

export type FileEditInput = { path: string; new_content: string | null };

export function listChangeSets(analysisId: string): Promise<ChangeSet[]> {
  return api<ChangeSet[]>(`/api/v1/analyses/${analysisId}/change-sets`);
}

export function getChangeSet(changeSetId: string): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`/api/v1/change-sets/${changeSetId}`);
}

export function createChangeSet(
  analysisId: string,
  payload: { reason: string; produced_by_rule: string; edits: FileEditInput[] },
): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`/api/v1/analyses/${analysisId}/change-sets`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function approveChangeSet(
  changeSetId: string,
  decision: "approved" | "rejected",
  comment?: string,
): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`/api/v1/change-sets/${changeSetId}/approve`, {
    method: "POST",
    body: JSON.stringify({ decision, comment: comment ?? null }),
  });
}

export function applyChangeSet(changeSetId: string): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`/api/v1/change-sets/${changeSetId}/apply`, { method: "POST" });
}

export function validateChangeSet(changeSetId: string): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`/api/v1/change-sets/${changeSetId}/validate`, { method: "POST" });
}

export function rollbackChangeSet(changeSetId: string): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`/api/v1/change-sets/${changeSetId}/rollback`, { method: "POST" });
}

export type GenerationFileVerification = {
  path: string;
  language: string;
  change_type: string | null;
  syntax_checked: boolean;
  syntax_ok: boolean | null;
  additions: number;
  deletions: number;
  note: string | null;
};

export type Generation = {
  change_set: ChangeSetDetail;
  verification: GenerationFileVerification[];
  summary: string | null;
  notes: string | null;
  model: string;
  mode: string;
  usage: Record<string, unknown> | null;
  latency_ms: number;
  limitations: string[];
};

export function createGeneration(
  analysisId: string,
  payload: {
    instruction: string;
    target_path?: string | null;
    mode: "feature" | "repair";
    ai_consent: boolean;
  },
): Promise<Generation> {
  return api<Generation>(`/api/v1/analyses/${analysisId}/generations`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type MigrationOperation = {
  kind: string;
  language: string;
  file_path: string;
  line: number;
  snippet: string;
  evidence_level: string;
  detection_method: string;
  model: string | null;
  detail: string | null;
};

export type CompatibilityAssessment = {
  operation_kind: string;
  category: string;
  source_provider: string;
  source_api: string;
  target_provider: string;
  target_endpoint: string;
  target_model: string;
  protocol_compatibility: string;
  functional_equivalence: string;
  criteria: Record<string, string>;
  notes: string[];
};

export type MigrationChange = {
  id: string;
  change_ref: string;
  kind: string;
  path: string | null;
  action: string;
  description: string;
  diff: string | null;
  reversible: boolean;
  rule_id: string | null;
};

export type MigrationPlan = {
  id: string;
  project_id: string;
  analysis_id: string;
  source_provider: string;
  target_provider: string;
  status: string;
  target_base_url: string | null;
  target_model: string | null;
  operation_count: number;
  matrix_summary: Record<string, number> | null;
  verified_at: string | null;
  created_by: string;
  created_at: string;
};

export type MigrationPlanDetail = MigrationPlan & {
  plan: {
    operations?: MigrationOperation[];
    compatibility_matrix?: CompatibilityAssessment[];
    changes?: MigrationChange[];
    proposed_tests?: string[];
    limitations?: string[];
    sources?: { name: string; url: string; verified_at: string; notes?: string }[];
  } | null;
  limitations: string[] | null;
  sources: { name: string; url: string; verified_at: string }[] | null;
  changes: MigrationChange[];
};

export function createMigrationPlan(projectId: string, analysisId: string): Promise<MigrationPlanDetail> {
  return api<MigrationPlanDetail>(`/api/v1/projects/${projectId}/migrations`, {
    method: "POST",
    body: JSON.stringify({ analysis_id: analysisId }),
  });
}

export function listMigrationPlans(projectId: string): Promise<MigrationPlan[]> {
  return api<MigrationPlan[]>(`/api/v1/projects/${projectId}/migrations`);
}

export function getMigrationPlan(migrationId: string): Promise<MigrationPlanDetail> {
  return api<MigrationPlanDetail>(`/api/v1/migrations/${migrationId}`);
}

export type BinarySection = {
  name: string;
  size: number;
  offset: number | null;
  entropy: number | null;
};

export type BinaryFacts = {
  path: string;
  size_bytes: number;
  sha256: string;
  sha1: string;
  md5: string;
  format: string;
  architecture: string | null;
  bits: number | null;
  file_type: string | null;
  entry_point: number | null;
  sections: BinarySection[];
  imported_symbols: string[];
  exported_symbols: string[];
  linked_libraries: string[];
  strings_sample: string[];
  signatures: string[];
  runtime_indicators: string[];
  debug_info_present: boolean | null;
  embedded?: {
    name: string;
    format: string;
    size: number;
    major?: number;
    machine?: number;
    version?: string;
    limit?: number;
  }[];
  limitations: string[];
};

export type BinaryAnalysis = {
  id: string;
  artifact_id: string;
  project_id: string;
  format: string;
  architecture: string | null;
  bits: number | null;
  file_type: string | null;
  size_bytes: number;
  sha256: string;
  created_at: string;
  facts: BinaryFacts;
};

export function uploadBinary(projectId: string, file: File): Promise<Artifact> {
  const form = new FormData();
  form.append("file", file);
  return api<Artifact>(`/api/v1/projects/${projectId}/binaries`, {
    method: "POST",
    body: form,
  });
}

export function analyzeBinary(projectId: string, artifactId: string): Promise<BinaryAnalysis> {
  return api<BinaryAnalysis>(`/api/v1/projects/${projectId}/binary-analyses`, {
    method: "POST",
    body: JSON.stringify({ artifact_id: artifactId }),
  });
}

export function listBinaryAnalyses(projectId: string): Promise<BinaryAnalysis[]> {
  return api<BinaryAnalysis[]>(`/api/v1/projects/${projectId}/binary-analyses`);
}

export type QuotaItem = {
  used: number;
  limit: number;
  percent: number | null;
};

export type Usage = {
  organization_id: string;
  projects: number;
  artifacts: number;
  storage_bytes: number;
  findings: number;
  active_jobs: number;
  jobs_by_status: Record<string, number>;
  usage_totals: Record<string, number>;
  quotas: Record<string, QuotaItem>;
};

export type Metrics = {
  organization_id: string;
  generated_at: string;
  jobs_total: number;
  jobs_by_status: Record<string, number>;
  jobs_finished: number;
  jobs_failed_or_cancelled: number;
  avg_duration_seconds: number | null;
  durations_observed: number;
};

export function getUsage(): Promise<Usage> {
  return api<Usage>("/api/v1/observability/usage");
}

export function getMetrics(): Promise<Metrics> {
  return api<Metrics>("/api/v1/observability/metrics");
}

export type ValidationRequirement = {
  id: string;
  title: string;
  description: string;
  source_document: string | null;
  source_section: string | null;
  source_page: number | null;
  acceptance_criteria: string[];
  checks: { id: string; type: string; criterion?: string; target?: string; required?: boolean }[];
  dependencies: string[];
  related_files: string[];
  updated_at: string;
};

export type ValidationEvidence = {
  id: string;
  requirement_id: string;
  check_id: string;
  check_type: string;
  criterion: string | null;
  target: string | null;
  status: string;
  passed: boolean;
  exit_code: number | null;
  duration_ms: number | null;
  command: string | null;
  output: string | null;
  limitations: string[];
};

export type ValidationResult = {
  id: string;
  requirement_id: string;
  status: string;
  checks_total: number;
  checks_passed: number;
  checks_failed: number;
  checks_skipped: number;
  criteria_met: { criterion: string; met: boolean }[];
  limitations: string[];
  created_at: string;
  evidence: ValidationEvidence[];
};

export type ValidationRun = {
  id: string;
  scope: string;
  status: string;
  code_hash: string | null;
  environment: string | null;
  summary: Record<string, number> | null;
  requested_by: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  limitations: string[];
  results: ValidationResult[];
};

export type ValidationRunSummary = Omit<ValidationRun, "results">;

export type ConformanceItem = {
  id: string;
  title: string;
  source_section: string | null;
  status: string;
  checks_total: number;
  checks_passed: number;
  checks_failed: number;
  checks_skipped: number;
  validated_at: string | null;
  run_id: string | null;
};

export type ConformanceReport = {
  total: number;
  verified: number;
  failed: number;
  partial: number;
  blocked: number;
  not_run: number;
  conformance_ratio: number;
  items: ConformanceItem[];
};

export function listValidationRequirements(): Promise<ValidationRequirement[]> {
  return api<ValidationRequirement[]>("/api/v1/validation/requirements");
}

export function getConformanceReport(): Promise<ConformanceReport> {
  return api<ConformanceReport>("/api/v1/validation/report");
}

export function listValidationRuns(): Promise<ValidationRunSummary[]> {
  return api<ValidationRunSummary[]>("/api/v1/validation/runs");
}

export function getValidationRun(runId: string): Promise<ValidationRun> {
  return api<ValidationRun>(`/api/v1/validation/runs/${runId}`);
}

export function runValidation(requirementIds?: string[]): Promise<ValidationRun> {
  return api<ValidationRun>("/api/v1/validation/run", {
    method: "POST",
    body: JSON.stringify({ requirement_ids: requirementIds ?? null }),
  });
}
