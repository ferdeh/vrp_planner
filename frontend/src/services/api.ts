import axios from "axios";
import type {
  DepotData,
  MasterDataListResponse,
  OptimizationRequest,
  OptimizationResultResponse,
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

  if (typeof window === "undefined") {
    return "http://localhost:8080";
  }

  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8080`;
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

export async function optimize(payload: OptimizationRequest) {
  const { data } = await api.post<OptimizationResultResponse>("/api/v1/optimize", payload);
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
  const { data } = await api.get<ScenarioDetailResponse>(`/api/v1/scenarios/${scenarioId}`);
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

export async function listAvailableTrucks(params: { depotId: string; dispatchDate: string }) {
  const { data } = await api.get<MasterDataListResponse>("/api/v1/master-data/trucks", {
    params: { depot_id: params.depotId, dispatch_date: params.dispatchDate },
  });
  return data.items as unknown as TruckMasterData[];
}
