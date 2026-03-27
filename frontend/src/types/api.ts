export type SolutionStatus = "feasible" | "infeasible" | "partial" | "error";

export interface OrderInput {
  order_id: string;
  spbu_id: string;
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

export interface TruckInput {
  truck_id: string;
  no_polisi?: string | null;
  truck_type: string;
  truck_category?: number | null;
  capacity_kl: number;
  fixed_cost: number;
  variable_cost_per_km: number;
  variable_cost_per_minute: number;
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
  fixed_cost: number;
  variable_cost_per_km: number;
  variable_cost_per_minute: number;
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

export interface OptimizationConfig {
  minimize_truck_count: boolean;
  minimize_distance: boolean;
  minimize_time: boolean;
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
    fixed_cost_vehicle: number;
    distance_weight: number;
    time_weight: number;
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

export interface TruckTypeSummary {
  truck_type: string;
  active_count: number;
  total_capacity_kl: number;
}

export interface RouteStopResponse {
  sequence: number;
  order_id: string;
  parent_order_id: string;
  spbu_id: string;
  stop_kind: "delivery" | "depot_reload";
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
  total_depot_operation_time_minutes: number;
  depot_operation_start?: string | null;
  depot_operation_end?: string | null;
  solver_runtime_seconds: number;
  objective_config: OptimizationConfig;
  route_details: RouteDetailResponse[];
  unserved_orders: UnservedOrderDetail[];
  preprocessing_notes: PreprocessingNote[];
}

export interface ScenarioListItem {
  scenario_id: string;
  dispatch_date: string;
  depot_id: string;
  status: SolutionStatus;
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

export interface MasterDataListResponse {
  items: Array<Record<string, unknown>>;
}
