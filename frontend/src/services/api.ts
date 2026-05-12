import axios from "axios";
import type {
  AnalysisLevel,
  ClusterMetricsResponse,
  DepotData,
  MasterEffectiveEdge,
  MasterNetworkNode,
  OptimizationJobResponse,
  MasterDataListResponse,
  OptimizationRequest,
  RepositoryVersionResponse,
  SolverJobResponse,
  SolverSettings,
  SolverSettingsResponse,
  ScenarioAnalysisCreateRequest,
  ScenarioAnalysisDetailResponse,
  ScenarioAnalysisJobResponse,
  ScenarioAnalysisOverviewResponse,
  ScenarioAnalysisQueryResponse,
  ScenarioDetailResponse,
  ScenarioQueryResponse,
  TruckMasterData,
  SystemSettingsPayload,
  SystemSettingsResponse,
} from "../types/api";

function resolveApiBaseUrl() {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  return "";
}

const baseURL = resolveApiBaseUrl();

export const api = axios.create({
  baseURL,
});

export async function getSettings() {
  const { data } = await api.get<SystemSettingsResponse>("/api/v1/settings");
  return data;
}

export async function updateSettings(payload: SystemSettingsPayload) {
  const { data } = await api.put<SystemSettingsResponse>("/api/v1/settings", payload);
  return data;
}

export async function getRepositoryVersions() {
  const { data } = await api.get<RepositoryVersionResponse>("/api/v1/version");
  return data;
}

export async function downloadSolverGuidePdf() {
  const { data } = await api.get<Blob>("/api/v1/user-guide/solver-guide.pdf", {
    responseType: "blob",
  });
  return data;
}

export async function optimize(payload: OptimizationRequest) {
  const { data } = await api.post<OptimizationJobResponse>("/api/v1/optimize", payload);
  return data;
}

export async function getSolverSettings() {
  const { data } = await api.get<SolverSettingsResponse>("/api/vrp/solver-settings");
  return data;
}

export async function updateSolverSettings(payload: SolverSettings) {
  const { data } = await api.put<SolverSettingsResponse>("/api/vrp/solver-settings", payload);
  return data;
}

export async function solveVrp(payload: OptimizationRequest) {
  const { data } = await api.post<SolverJobResponse>("/api/vrp/solve", payload);
  return data;
}

export async function listScenarios() {
  const { data } = await api.get<ScenarioQueryResponse>("/api/v1/scenarios");
  return data;
}

export async function deleteScenarios(scenarioIds: string[]) {
  const { data } = await api.delete<{ deleted_count: number }>("/api/v1/scenarios", {
    data: { scenario_ids: scenarioIds },
  });
  return data;
}

export async function getScenario(scenarioId: string) {
  const { data } = await api.get<ScenarioDetailResponse>(`/api/v1/scenarios/${scenarioId}`, {
    params: { include_route_stops: false },
  });
  return data;
}

export async function getScenarioRoutes(scenarioId: string) {
  const { data } = await api.get<ScenarioDetailResponse["route_details"]>(`/api/v1/scenarios/${scenarioId}/routes`);
  return data;
}

export async function getClusterMetrics(scenarioId: string) {
  const { data } = await api.get<ClusterMetricsResponse>("/api/vrp/cluster-metrics", {
    params: { scenario_id: scenarioId },
  });
  return data;
}

export async function createScenarioAnalysis(scenarioId: string, level: AnalysisLevel) {
  const payload: ScenarioAnalysisCreateRequest = { level };
  const { data } = await api.post<ScenarioAnalysisJobResponse>(`/api/v1/scenarios/${scenarioId}/analysis`, payload);
  return data;
}

export async function listScenarioAnalyses(scenarioId: string) {
  const { data } = await api.get<ScenarioAnalysisQueryResponse>(`/api/v1/scenarios/${scenarioId}/analysis`);
  return data;
}

export async function listAllScenarioAnalyses() {
  const { data } = await api.get<ScenarioAnalysisOverviewResponse>("/api/v1/scenarios/analysis/jobs");
  return data;
}

export async function getScenarioAnalysis(scenarioId: string, analysisId: string) {
  const { data } = await api.get<ScenarioAnalysisDetailResponse>(
    `/api/v1/scenarios/${scenarioId}/analysis/${analysisId}`,
  );
  return data;
}

export async function listSpbu(depotId?: string) {
  const { data } = await api.get<MasterDataListResponse>("/api/v1/master-data/spbu", {
    params: depotId ? { depot_id: depotId } : undefined,
  });
  return data.items;
}

export async function listDepots() {
  const { data } = await api.get<MasterDataListResponse>("/api/v1/master-data/depots");
  return data.items as unknown as DepotData[];
}

export async function listNetworkNodes(nodeIds?: string[]) {
  const { data } = await api.get<MasterDataListResponse>("/api/v1/master-data/nodes", {
    params: nodeIds?.length ? { node_ids: nodeIds.join(",") } : undefined,
  });
  return data.items as unknown as MasterNetworkNode[];
}

export async function listEffectiveEdges(nodeIds?: string[]) {
  const { data } = await api.get<MasterDataListResponse>("/api/v1/master-data/effective-edges", {
    params: nodeIds?.length ? { node_ids: nodeIds.join(",") } : undefined,
  });
  return data.items as unknown as MasterEffectiveEdge[];
}

export async function listAvailableTrucks(params: { depotId: string; dispatchDate: string }) {
  const { data } = await api.get<MasterDataListResponse>("/api/v1/master-data/trucks", {
    params: { depot_id: params.depotId, dispatch_date: params.dispatchDate },
  });
  return data.items as unknown as TruckMasterData[];
}
