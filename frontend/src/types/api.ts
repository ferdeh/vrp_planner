export type SolutionStatus =
  | "processing"
  | "feasible"
  | "infeasible"
  | "partial"
  | "preprocessing_failed"
  | "timeout"
  | "error";
export type AnalysisLevel = "level_1" | "level_2";
export type AnalysisStatus = "processing" | "completed" | "error";
export type PrimaryObjective = "minimize_depot_operation" | "minimize_truck_count";

export interface OrderInput {
  order_id: string;
  spbu_id: string;
  spbu_name?: string | null;
  product_type: string;
  demand_kl: number;
  priority: boolean;
  eta?: string | null;
  service_time_minutes: number;
  time_window_start: string;
  time_window_end: string;
}

export interface TruckCompartment {
  compartment_id: string;
  capacity_kl: number;
}

export interface DepotData {
  depot_id: string;
  name: string;
  lat: number;
  lng: number;
  time_window_start: string;
  time_window_end: string;
  gate_limit?: number | null;
}

export interface SpbuData {
  spbu_id: string;
  name: string;
  lat: number;
  lng: number;
  time_window_start: string;
  time_window_end: string;
  truck_category?: number | null;
  allowed_truck_types?: string[];
  supply_depot_ids?: string[];
}

export interface TruckInput {
  truck_id: string;
  no_polisi?: string | null;
  truck_type: string;
  truck_category?: number | null;
  capacity_kl: number;
  start_depot_id: string;
  end_depot_id: string;
  shift_start: string;
  shift_end: string;
  compatible_product_types: string[];
  compartments: TruckCompartment[];
  status?: string | null;
  not_available_from?: string | null;
  not_available_to?: string | null;
}

export interface TruckMasterData {
  truck_id: string;
  no_polisi?: string | null;
  truck_type: string;
  truck_category?: number | null;
  capacity_kl: number;
  depot_id: string;
  shift_start: string;
  shift_end: string;
  compatible_product_types: string[];
  compartments: TruckCompartment[];
  is_available: boolean;
  status?: string | null;
  not_available_from?: string | null;
  not_available_to?: string | null;
}

export interface MasterNetworkNode {
  node_id: string;
  node_code: string;
  node_name: string;
  node_type: string;
  lat: number;
  lng: number;
  layout_x?: number | null;
  layout_y?: number | null;
  truck_category?: number | null;
  is_active: boolean;
  supply_depot_ids: string[];
}

export interface MasterEffectiveEdge {
  from_node_id: string;
  to_node_id: string;
  distance_km?: number | null;
  max_velocity_kmh?: number | null;
  source?: string | null;
  road_category?: string | null;
}

export interface OptimizationConfig {
  primary_objective: PrimaryObjective;
  allow_unserved_fallback: boolean;
  minimize_truck_count: boolean;
  minimize_distance: boolean;
  minimize_time: boolean;
  minimize_depot_operation_time: boolean;
  objective_priority: string[];
  hard_constraints: {
    capacity_limit: boolean;
    time_window: boolean;
    priority_eta: boolean;
    truck_category: boolean;
    no_split_order: boolean;
    depot_operation_window: boolean;
    max_route_duration: boolean;
    max_vehicle_working_time: boolean;
    max_total_distance_per_vehicle: boolean;
  };
  soft_constraints: {
    allow_unserved_orders: boolean;
    allow_overtime: boolean;
    capacity_limit: boolean;
    time_window: boolean;
    priority_eta: boolean;
    truck_category: boolean;
    depot_operation_window: boolean;
    max_route_duration: boolean;
    max_vehicle_working_time: boolean;
    max_total_distance_per_vehicle: boolean;
  };
  penalties: {
    unserved_order_penalty: number;
    late_arrival_penalty_per_minute: number;
    priority_eta_penalty_per_minute: number;
    overtime_penalty_per_minute: number;
    depot_operation_window_penalty_per_minute: number;
    capacity_violation_penalty: number;
    activation_cost_vehicle: number;
    distance_weight: number;
    time_weight: number;
    depot_operation_time_weight: number;
  };
  solver_options: {
    max_solver_seconds: number;
    first_solution_strategy: string;
    local_search_metaheuristic: string;
  };
  max_route_duration_minutes: number | null;
  max_vehicle_working_time_minutes: number | null;
  max_total_distance_per_vehicle_km: number | null;
  max_lateness_minutes: number | null;
}

export interface OptimizationRequest {
  dispatch_date: string;
  depot_id: string;
  depot_service_time_minutes: number;
  orders: OrderInput[];
  available_trucks: TruckInput[];
  optimization_config: OptimizationConfig;
}

export interface SystemSettingsResponse {
  id: string;
  default_optimization_config: OptimizationConfig;
  ui_preferences: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SystemSettingsPayload {
  default_optimization_config: OptimizationConfig;
  ui_preferences: Record<string, unknown>;
}

export interface RepositoryVersionItem {
  key: string;
  title: string;
  repo_name: string;
  branch: string | null;
  commit_hash: string | null;
  short_commit_hash: string | null;
  commit_message: string | null;
  committed_at: string | null;
  dirty: boolean;
  available: boolean;
  source: "git" | "env" | "unavailable";
  error: string | null;
}

export interface RepositoryVersionResponse {
  generated_at: string;
  repositories: RepositoryVersionItem[];
}

export interface TruckTypeSummary {
  truck_type: string;
  active_count: number;
  total_capacity_kl: number;
}

export interface CostBreakdown {
  activation_cost_total: number;
  distance_cost_total: number;
  time_cost_total: number;
  depot_operation_cost_total: number;
  late_arrival_penalty_total: number;
  priority_eta_penalty_total: number;
  overtime_penalty_total: number;
  max_total_distance_penalty_total: number;
  unserved_penalty_total: number;
  depot_operation_window_penalty_total: number;
  total_penalty_cost: number;
  total_cost: number;
}

export interface RouteStopResponse {
  sequence: number;
  order_id: string;
  parent_order_id: string;
  spbu_id: string;
  stop_kind: "delivery" | "depot_reload" | "depot_wait";
  trip_sequence: number;
  spbu_name?: string | null;
  travel_path?: string | null;
  segment_max_velocity_kmh?: string | null;
  travel_distance_km?: number | null;
  travel_time_minutes?: number | null;
  eta: string;
  etd: string;
  delivered_volume: number;
  arrival_status: string;
}

export interface RouteDetailResponse {
  truck_id: string;
  no_polisi?: string | null;
  origin_name?: string | null;
  origin_service_start?: string | null;
  origin_etd?: string | null;
  depot_service_time_minutes: number;
  depot_gate_limit?: number | null;
  return_eta?: string | null;
  return_path?: string | null;
  return_segment_max_velocity_kmh?: string | null;
  return_distance_km?: number | null;
  return_travel_time_minutes?: number | null;
  truck_type: string;
  capacity_kl: number;
  total_load: number;
  utilization_percent: number;
  route_distance: number;
  route_time: number;
  stop_count: number;
  trip_count: number;
  stops: RouteStopResponse[];
}

export interface UnservedOrderDetail {
  order_id: string;
  parent_order_id: string;
  spbu_id: string;
  demand_kl: number;
  reason: string;
  constraint_details: string[];
}

export interface PreprocessingNote {
  code: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface OptimizationResultResponse {
  scenario_id: string;
  status: SolutionStatus;
  message: string;
  total_orders: number;
  total_demand: number;
  total_delivered_demand: number;
  total_unserved_orders: number;
  active_truck_count: number;
  active_truck_type_summary: TruckTypeSummary[];
  total_distance: number;
  total_time: number;
  total_cost: number;
  total_penalty: number;
  cost_breakdown: CostBreakdown;
  total_depot_operation_time_minutes: number;
  depot_operation_start?: string | null;
  depot_operation_end?: string | null;
  solver_runtime_seconds: number;
  objective_config: OptimizationConfig;
  route_details: RouteDetailResponse[];
  unserved_orders: UnservedOrderDetail[];
  preprocessing_notes: PreprocessingNote[];
}

export interface OptimizationJobResponse {
  scenario_id: string;
  status: SolutionStatus;
  message: string;
  created_at: string;
}

export interface ScenarioListItem {
  scenario_id: string;
  dispatch_date: string;
  depot_id: string;
  status: SolutionStatus;
  total_demand: number;
  total_delivered_demand: number;
  active_truck_count: number;
  total_cost: number;
  total_distance: number;
  total_time: number;
  created_at: string;
}

export interface ScenarioQueryResponse {
  items: ScenarioListItem[];
  summary: {
    total_scenarios: number;
    feasible_scenarios: number;
    average_active_trucks: number;
  };
}

export interface ScenarioDetailResponse extends OptimizationResultResponse {
  dispatch_date: string;
  depot_id: string;
  depot_service_time_minutes: number;
  input_orders: OrderInput[];
  input_trucks: TruckInput[];
  created_at: string;
}

export interface ScenarioAnalysisExperimentResult {
  experiment_id: string;
  title: string;
  summary: string;
  scenario_status: SolutionStatus;
  solver_status: string;
  assignment_found: boolean;
  total_unserved_orders: number;
  total_cost: number;
  solver_runtime_seconds: number;
  changed_assumptions: string[];
}

export interface ScenarioAnalysisProblematicOrder {
  order_id: string;
  spbu_id: string;
  priority: boolean;
  eta?: string | null;
  heuristic_score: number;
  experimental_score: number;
  total_score: number;
  reasons: string[];
}

export interface ScenarioAnalysisReport {
  root_cause_summary: string;
  solver_status_explained: string;
  key_findings: string[];
  recommended_actions: string[];
  problematic_orders: ScenarioAnalysisProblematicOrder[];
  experiment_results: ScenarioAnalysisExperimentResult[];
}

export interface ScenarioAnalysisCreateRequest {
  level: AnalysisLevel;
}

export interface ScenarioAnalysisJobResponse {
  analysis_id: string;
  scenario_id: string;
  level: AnalysisLevel;
  status: AnalysisStatus;
  message: string;
  created_at: string;
}

export interface ScenarioAnalysisListItem {
  analysis_id: string;
  scenario_id: string;
  level: AnalysisLevel;
  status: AnalysisStatus;
  message: string;
  created_at: string;
  updated_at: string;
}

export interface ScenarioAnalysisQueryResponse {
  items: ScenarioAnalysisListItem[];
}

export interface ScenarioAnalysisOverviewItem {
  analysis_id: string;
  scenario_id: string;
  dispatch_date: string;
  depot_id: string;
  scenario_status: SolutionStatus;
  level: AnalysisLevel;
  status: AnalysisStatus;
  message: string;
  created_at: string;
  updated_at: string;
}

export interface ScenarioAnalysisOverviewResponse {
  items: ScenarioAnalysisOverviewItem[];
}

export interface ScenarioAnalysisDetailResponse {
  analysis_id: string;
  scenario_id: string;
  level: AnalysisLevel;
  status: AnalysisStatus;
  message: string;
  report?: ScenarioAnalysisReport | null;
  created_at: string;
  updated_at: string;
}

export interface MasterDataListResponse {
  items: Array<Record<string, unknown>>;
}
