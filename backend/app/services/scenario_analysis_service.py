"""Scenario analysis pipeline and inference engine."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from ortools.constraint_solver import routing_enums_pb2
from sqlalchemy.orm import Session

from app.models import schemas
from app.repositories.scenario_analysis_repository import ScenarioAnalysisRepository
from app.repositories.scenario_repository import ScenarioRepository
from app.services.preprocessing_service import PreprocessingService
from app.services.result_service import ResultService
from app.solver.ortools_solver import OrToolsSolver
from app.utils.time_utils import hhmm_to_minutes


@dataclass
class _ExperimentRun:
    summary: schemas.ScenarioAnalysisExperimentResult
    result: schemas.OptimizationResultResponse | None


class ScenarioAnalysisService:
    """Create and execute scenario analysis jobs."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.analysis_repository = ScenarioAnalysisRepository(db)
        self.scenario_repository = ScenarioRepository(db)
        self.result_service = ResultService()
        self.preprocessing_service = PreprocessingService(
            master_data_client=self.result_service.master_data_client,
            network_client=self.result_service.network_client,
        )
        self.solver = OrToolsSolver()

    def create_job(
        self,
        scenario_id: UUID | str,
        payload: schemas.ScenarioAnalysisCreateRequest,
    ) -> schemas.ScenarioAnalysisJobResponse:
        scenario = self.scenario_repository.get_scenario(scenario_id)
        if scenario is None:
            raise ValueError(f"Scenario {scenario_id} not found.")
        if scenario.result is None:
            raise ValueError("Scenario result is not available yet.")
        row = self.analysis_repository.create_analysis(scenario.id, payload.level)
        return self._to_job_response(row)

    def process_job(self, analysis_id: UUID | str) -> None:
        row = self.analysis_repository.get_analysis(analysis_id)
        if row is None:
            raise ValueError(f"Scenario analysis {analysis_id} not found.")

        scenario = self.scenario_repository.get_scenario(row.scenario_id)
        if scenario is None or scenario.result is None or scenario.optimization_config is None:
            self.analysis_repository.save_error(row, "Scenario result is not available for analysis.")
            return

        try:
            if row.level == "level_1":
                report = self._build_level_one_report(scenario)
            else:
                report = self._build_level_two_report(scenario)
            self.analysis_repository.save_completed(row, report, "Scenario analysis completed.")
        except Exception as exc:
            self.analysis_repository.save_error(row, str(exc))

    def list_analysis_jobs(self, scenario_id: UUID | str) -> schemas.ScenarioAnalysisQueryResponse:
        return self.analysis_repository.list_for_scenario(scenario_id)

    def list_all_analysis_jobs(self) -> schemas.ScenarioAnalysisOverviewResponse:
        return self.analysis_repository.list_all()

    def get_analysis_detail(
        self,
        scenario_id: UUID | str,
        analysis_id: UUID | str,
    ) -> schemas.ScenarioAnalysisDetailResponse:
        row = self.analysis_repository.get_analysis(analysis_id, scenario_id=scenario_id)
        if row is None:
            raise ValueError(f"Scenario analysis {analysis_id} not found.")
        report = (
            schemas.ScenarioAnalysisReport.model_validate(row.report_json)
            if row.report_json
            else None
        )
        return schemas.ScenarioAnalysisDetailResponse(
            analysis_id=UUID(row.id),
            scenario_id=UUID(row.scenario_id),
            level=row.level,
            status=row.status,
            message=row.message,
            report=report,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_job_response(self, row) -> schemas.ScenarioAnalysisJobResponse:
        return schemas.ScenarioAnalysisJobResponse(
            analysis_id=UUID(row.id),
            scenario_id=UUID(row.scenario_id),
            level=row.level,
            status=row.status,
            message=row.message,
            created_at=row.created_at,
        )

    def _load_snapshot(self, scenario) -> tuple[schemas.OptimizationRequest, schemas.OptimizationConfig]:
        payload = schemas.OptimizationRequest.model_validate(scenario.raw_request)
        config = schemas.OptimizationConfig.model_validate(scenario.optimization_config.config_snapshot)
        return payload, config

    def _fetch_time_by_spbu(self, payload: schemas.OptimizationRequest) -> dict[str, int]:
        spbu_ids = sorted({item.spbu_id for item in payload.orders})
        if not spbu_ids:
            return {}
        matrix = self.result_service.network_client.get_time_matrix(payload.depot_id, spbu_ids)
        depot_row = matrix.matrix[0] if matrix.matrix else []
        return {
            spbu_id: depot_row[index + 1]
            for index, spbu_id in enumerate(spbu_ids)
            if index + 1 < len(depot_row)
        }

    def _payload_with_orders(
        self,
        payload: schemas.OptimizationRequest,
        orders: list[schemas.OrderInput],
    ) -> schemas.OptimizationRequest:
        return payload.model_copy(update={"orders": orders}, deep=True)

    def _spbu_label(self, payload: schemas.OptimizationRequest, spbu_id: str) -> str:
        for order in payload.orders:
            if order.spbu_id == spbu_id and order.spbu_name:
                return order.spbu_name
        return spbu_id

    def _run_experiment(
        self,
        scenario_id: UUID | str,
        payload: schemas.OptimizationRequest,
        config: schemas.OptimizationConfig,
        experiment_id: str,
        title: str,
        changed_assumptions: list[str],
    ) -> _ExperimentRun:
        try:
            payload = payload.model_copy(update={"optimization_config": config}, deep=True)
            problem = self.preprocessing_service.preprocess(payload, config)
            solver_output = self.solver.solve(problem)
            response = self.result_service.build_response(scenario_id, problem, solver_output)
            status = response.status
            total_unserved_orders = response.total_unserved_orders
            message = response.message
            assignment_found = solver_output.assignment is not None
            runtime_seconds = response.solver_runtime_seconds
            summary = schemas.ScenarioAnalysisExperimentResult(
                experiment_id=experiment_id,
                title=title,
                summary=message,
                scenario_status=status,
                solver_status=self._solver_status_name(solver_output.search_status),
                assignment_found=assignment_found,
                total_unserved_orders=total_unserved_orders,
                total_cost=response.total_cost,
                solver_runtime_seconds=runtime_seconds,
                changed_assumptions=changed_assumptions,
            )
            return _ExperimentRun(summary=summary, result=response)
        except Exception as exc:
            summary = schemas.ScenarioAnalysisExperimentResult(
                experiment_id=experiment_id,
                title=title,
                summary=str(exc),
                scenario_status="error",
                solver_status="EXPERIMENT_ERROR",
                assignment_found=False,
                total_unserved_orders=len(payload.orders),
                total_cost=0,
                solver_runtime_seconds=0,
                changed_assumptions=changed_assumptions,
            )
            return _ExperimentRun(summary=summary, result=None)

    def _build_level_one_report(self, scenario) -> schemas.ScenarioAnalysisReport:
        payload, config = self._load_snapshot(scenario)
        time_by_spbu = self._fetch_time_by_spbu(payload)
        preprocessing_failure = self._is_preprocessing_failure(scenario)
        dominant_unserved_reason = self._dominant_unserved_reason(scenario)
        problematic_orders = self._rank_problematic_orders(
            payload=payload,
            config=config,
            unserved_parent_order_ids={item.parent_order_id for item in scenario.result.unserved_orders},
            time_by_spbu=time_by_spbu,
            experiment_results={},
        )
        priority_orders = [item for item in payload.orders if item.priority]
        priority_by_spbu = Counter(item.spbu_id for item in priority_orders)
        key_findings = []
        if priority_orders:
            key_findings.append(
                f"Ada {len(priority_orders)} order priority tersebar di {len(priority_by_spbu)} SPBU."
            )
        if priority_by_spbu:
            busiest_spbu, busiest_count = priority_by_spbu.most_common(1)[0]
            key_findings.append(
                f"Cluster priority terpadat berada di {self._spbu_label(payload, busiest_spbu)} dengan {busiest_count} order priority."
            )
        if scenario.result.status == "timeout":
            key_findings.append(
                "Solver tidak menghasilkan assignment sama sekali, sehingga seluruh order tampil sebagai unserved pada hasil base scenario."
            )
        elif preprocessing_failure:
            key_findings.append(
                "Tidak ada shipment yang lolos preprocessing, sehingga solver OR-Tools tidak sempat mencoba assignment apa pun."
            )
        elif scenario.result.total_unserved_orders:
            key_findings.append(
                f"Hasil existing scenario masih menyisakan {scenario.result.total_unserved_orders} order unserved."
            )
        if preprocessing_failure and dominant_unserved_reason:
            key_findings.append(
                f"Alasan preassigned unserved yang dominan: {dominant_unserved_reason}"
            )

        root_cause_summary = self._infer_level_one_root_cause(
            scenario_status=scenario.result.status,
            config=config,
            priority_count=len(priority_orders),
            problematic_orders=problematic_orders,
            preprocessing_failure=preprocessing_failure,
            dominant_unserved_reason=dominant_unserved_reason,
        )
        solver_status_explained = self._explain_solver_status(
            scenario.result.status,
            config,
            preprocessing_failure=preprocessing_failure,
            dominant_unserved_reason=dominant_unserved_reason,
        )
        recommended_actions = self._recommend_actions(
            scenario_status=scenario.result.status,
            config=config,
            experiment_runs=[],
            preprocessing_failure=preprocessing_failure,
            dominant_unserved_reason=dominant_unserved_reason,
        )
        return schemas.ScenarioAnalysisReport(
            root_cause_summary=root_cause_summary,
            solver_status_explained=solver_status_explained,
            key_findings=key_findings,
            recommended_actions=recommended_actions,
            problematic_orders=problematic_orders,
            experiment_results=[],
        )

    def _build_level_two_report(self, scenario) -> schemas.ScenarioAnalysisReport:
        payload, config = self._load_snapshot(scenario)
        level_one = self._build_level_one_report(scenario)
        experiment_runs: list[_ExperimentRun] = []
        preprocessing_failure = self._is_preprocessing_failure(scenario)
        dominant_unserved_reason = self._dominant_unserved_reason(scenario)

        extended_timeout_seconds = min(max(config.solver_options.max_solver_seconds * 2, 90), 120)
        extended_timeout_config = config.model_copy(
            update={
                "solver_options": config.solver_options.model_copy(
                    update={"max_solver_seconds": extended_timeout_seconds}
                )
            },
            deep=True,
        )
        experiment_runs.append(
            self._run_experiment(
                scenario.id,
                payload,
                extended_timeout_config,
                "extended_timeout",
                "Extended Timeout",
                [f"Timeout solver dinaikkan menjadi {extended_timeout_seconds} detik."],
            )
        )

        priority_orders = [item for item in payload.orders if item.priority]
        if priority_orders:
            experiment_runs.append(
                self._run_experiment(
                    scenario.id,
                    self._payload_with_orders(payload, priority_orders),
                    config,
                    "priority_only",
                    "Priority Only",
                    ["Hanya order priority yang disolve."],
                )
            )

        if config.hard_constraints.priority_eta or config.soft_constraints.priority_eta:
            priority_eta_disabled = config.model_copy(
                update={
                    "hard_constraints": config.hard_constraints.model_copy(
                        update={"priority_eta": False}
                    ),
                    "soft_constraints": config.soft_constraints.model_copy(
                        update={"priority_eta": False}
                    ),
                },
                deep=True,
            )
            experiment_runs.append(
                self._run_experiment(
                    scenario.id,
                    payload,
                    priority_eta_disabled,
                    "priority_eta_disabled",
                    "Priority ETA Disabled",
                    ["Rule SPBU Priority hard dan soft dimatikan untuk diagnosis."],
                )
            )

        if not config.soft_constraints.allow_unserved_orders:
            allow_unserved_config = config.model_copy(
                update={
                    "soft_constraints": config.soft_constraints.model_copy(
                        update={"allow_unserved_orders": True}
                    )
                },
                deep=True,
            )
            experiment_runs.append(
                self._run_experiment(
                    scenario.id,
                    payload,
                    allow_unserved_config,
                    "allow_unserved_on",
                    "Allow Unserved On",
                    ["Allow unserved diaktifkan untuk melihat subset order yang paling sulit."],
                )
            )

        experiment_map = {item.summary.experiment_id: item for item in experiment_runs}
        time_by_spbu = self._fetch_time_by_spbu(payload)
        problematic_orders = self._rank_problematic_orders(
            payload=payload,
            config=config,
            unserved_parent_order_ids={item.parent_order_id for item in scenario.result.unserved_orders},
            time_by_spbu=time_by_spbu,
            experiment_results=experiment_map,
        )
        key_findings = list(level_one.key_findings)
        key_findings.extend(self._build_experiment_findings(experiment_map))
        return schemas.ScenarioAnalysisReport(
            root_cause_summary=self._infer_level_two_root_cause(
                scenario_status=scenario.result.status,
                config=config,
                experiment_results=experiment_map,
                preprocessing_failure=preprocessing_failure,
                dominant_unserved_reason=dominant_unserved_reason,
            ),
            solver_status_explained=self._explain_solver_status(
                scenario.result.status,
                config,
                preprocessing_failure=preprocessing_failure,
                dominant_unserved_reason=dominant_unserved_reason,
            ),
            key_findings=key_findings,
            recommended_actions=self._recommend_actions(
                scenario_status=scenario.result.status,
                config=config,
                experiment_runs=experiment_runs,
                preprocessing_failure=preprocessing_failure,
                dominant_unserved_reason=dominant_unserved_reason,
            ),
            problematic_orders=problematic_orders,
            experiment_results=[item.summary for item in experiment_runs],
        )

    def _infer_level_one_root_cause(
        self,
        scenario_status: schemas.SolutionStatus,
        config: schemas.OptimizationConfig,
        priority_count: int,
        problematic_orders: list[schemas.ScenarioAnalysisProblematicOrder],
        *,
        preprocessing_failure: bool = False,
        dominant_unserved_reason: str | None = None,
    ) -> str:
        if scenario_status == "timeout":
            if config.soft_constraints.priority_eta and priority_count:
                return (
                    "Search utama kemungkinan macet pada kombinasi order priority yang tetap wajib dilayani, "
                    "ditambah time window hard dan distribusi SPBU yang tersebar."
                )
            if config.hard_constraints.time_window:
                return (
                    "Solver berhenti di batas waktu saat mencoba memenuhi time window hard pada banyak order dan rute multi-trip."
                )
            return "Solver berhenti di batas waktu sebelum menemukan assignment feasible."
        if scenario_status == "infeasible":
            return "Kombinasi hard constraint pada scenario ini tidak memiliki solusi feasible menurut solver."
        if scenario_status == "preprocessing_failed" or preprocessing_failure:
            if dominant_unserved_reason:
                return (
                    "Scenario gagal di preprocessing sehingga seluruh order ditandai unserved "
                    f"sebelum solver berjalan. Penyebab dominannya: {dominant_unserved_reason}"
                )
            return (
                "Scenario gagal di preprocessing sehingga tidak ada shipment feasible yang bisa diberikan ke solver."
            )
        if scenario_status == "partial":
            if preprocessing_failure:
                if dominant_unserved_reason:
                    return (
                        "Scenario lama ini efektif gagal di preprocessing karena seluruh order sudah ditandai unserved "
                        f"sebelum solver berjalan. Penyebab dominannya: {dominant_unserved_reason}"
                    )
                return (
                    "Scenario lama ini efektif gagal di preprocessing karena seluruh order sudah ditandai unserved "
                    "sehingga tidak ada shipment feasible yang bisa diberikan ke solver."
                )
            return "Scenario masih feasible, tetapi ada subset order yang secara biaya atau constraint lebih sulit untuk dilayani."
        if problematic_orders:
            return "Scenario feasible, namun ada order yang secara heuristik paling menekan kapasitas search dan layout rute."
        return "Scenario feasible tanpa indikasi bottleneck besar dari hasil existing run."

    def _infer_level_two_root_cause(
        self,
        scenario_status: schemas.SolutionStatus,
        config: schemas.OptimizationConfig,
        experiment_results: dict[str, _ExperimentRun],
        *,
        preprocessing_failure: bool = False,
        dominant_unserved_reason: str | None = None,
    ) -> str:
        extended = experiment_results.get("extended_timeout")
        priority_only = experiment_results.get("priority_only")
        priority_eta_disabled = experiment_results.get("priority_eta_disabled")
        allow_unserved = experiment_results.get("allow_unserved_on")

        if scenario_status == "timeout":
            if (
                priority_eta_disabled
                and priority_eta_disabled.summary.scenario_status in {"feasible", "partial"}
            ):
                return (
                    "Timeout base scenario terutama dipicu oleh rule SPBU Priority. "
                    "Saat priority ETA dimatikan untuk diagnosis, solver langsung menemukan solusi."
                )
            if priority_only and priority_only.summary.scenario_status == "timeout":
                return (
                    "Bahkan subset order priority saja sudah membuat solver timeout, sehingga cluster priority adalah sumber kemacetan search utama."
                )
            if extended and extended.summary.scenario_status in {"feasible", "partial"}:
                return (
                    "Batas waktu solver adalah pemicu utama. Saat timeout diperpanjang, solver berhasil menemukan solusi."
                )
            if extended and extended.summary.scenario_status == "timeout":
                return (
                    "Timeout bukan sekadar kekurangan 30 detik. Model tetap sulit dijelajahi bahkan setelah timeout diperpanjang."
                )
        if scenario_status in {"infeasible", "timeout"} and allow_unserved and allow_unserved.summary.scenario_status == "partial":
            return "Ada subset order kecil yang memblokir skenario penuh. Saat allow unserved diaktifkan, solver bisa menyelesaikan sisanya."
        return self._infer_level_one_root_cause(
            scenario_status=scenario_status,
            config=config,
            priority_count=0,
            problematic_orders=[],
            preprocessing_failure=preprocessing_failure,
            dominant_unserved_reason=dominant_unserved_reason,
        )

    def _explain_solver_status(
        self,
        scenario_status: schemas.SolutionStatus,
        config: schemas.OptimizationConfig,
        *,
        preprocessing_failure: bool = False,
        dominant_unserved_reason: str | None = None,
    ) -> str:
        if scenario_status == "timeout":
            return (
                f"Solver mencapai batas {config.solver_options.max_solver_seconds} detik tanpa menghasilkan assignment feasible. "
                "Status ini berbeda dari infeasible: model belum terbukti mustahil, tetapi search berhenti lebih dulu."
            )
        if scenario_status == "infeasible":
            return "Solver mengembalikan infeasible, artinya kombinasi hard constraint tidak dapat dipenuhi pada model yang dibangun."
        if scenario_status == "preprocessing_failed" or preprocessing_failure:
            if dominant_unserved_reason:
                return (
                    "Status preprocessing failed berarti solver belum sempat membangun assignment karena "
                    "seluruh order gugur di preprocessing. "
                    f"Alasan dominannya: {dominant_unserved_reason}"
                )
            return (
                "Status preprocessing failed berarti solver belum sempat membangun assignment karena "
                "seluruh order gugur di preprocessing."
            )
        if scenario_status == "partial":
            if preprocessing_failure:
                if dominant_unserved_reason:
                    return (
                        "Status partial pada scenario lama ini sebenarnya menunjukkan kegagalan preprocessing, "
                        "bukan partial route dari solver. "
                        f"Alasan dominannya: {dominant_unserved_reason}"
                    )
                return (
                    "Status partial pada scenario lama ini sebenarnya menunjukkan kegagalan preprocessing, "
                    "bukan partial route dari solver."
                )
            return "Solver menemukan solusi, tetapi sebagian order tetap unserved atau dijatuhkan sesuai konfigurasi penalty."
        if scenario_status == "feasible":
            return "Solver menemukan solusi yang melayani seluruh order sesuai aturan aktif."
        return "Status scenario tidak termasuk jalur hasil solver standar."

    def _build_experiment_findings(
        self,
        experiment_results: dict[str, _ExperimentRun],
    ) -> list[str]:
        findings: list[str] = []
        extended = experiment_results.get("extended_timeout")
        if extended:
            findings.append(
                "Extended timeout menghasilkan status "
                f"{extended.summary.scenario_status} dalam {extended.summary.solver_runtime_seconds} detik "
                f"dengan total cost {round(extended.summary.total_cost, 2)}."
            )
        priority_only = experiment_results.get("priority_only")
        if priority_only:
            findings.append(
                "Priority-only menghasilkan status "
                f"{priority_only.summary.scenario_status} dengan {priority_only.summary.total_unserved_orders} unserved "
                f"dan total cost {round(priority_only.summary.total_cost, 2)}."
            )
        priority_eta_disabled = experiment_results.get("priority_eta_disabled")
        if priority_eta_disabled:
            findings.append(
                "Saat priority ETA dimatikan, hasil diagnosis menjadi "
                f"{priority_eta_disabled.summary.scenario_status} dengan total cost {round(priority_eta_disabled.summary.total_cost, 2)}."
            )
        allow_unserved = experiment_results.get("allow_unserved_on")
        if allow_unserved:
            findings.append(
                "Saat allow unserved diaktifkan, diagnosis menghasilkan "
                f"{allow_unserved.summary.total_unserved_orders} order unserved dengan total cost {round(allow_unserved.summary.total_cost, 2)}."
            )
        return findings

    def _recommend_actions(
        self,
        scenario_status: schemas.SolutionStatus,
        config: schemas.OptimizationConfig,
        experiment_runs: list[_ExperimentRun],
        *,
        preprocessing_failure: bool = False,
        dominant_unserved_reason: str | None = None,
    ) -> list[str]:
        recommendations: list[str] = []
        experiment_map = {item.summary.experiment_id: item for item in experiment_runs}
        if preprocessing_failure:
            if dominant_unserved_reason == "No truck matches SPBU truck category policy.":
                recommendations.append(
                    "Samakan kategori armada dengan batas truck category SPBU, atau nonaktifkan hard truck category bila aturan akses memang boleh dilonggarkan."
                )
            recommendations.append(
                "Periksa preprocessing notes dan alasan unserved per order, karena bottleneck terjadi sebelum solver OR-Tools mulai search."
            )
        if scenario_status == "timeout":
            recommendations.append(
                f"Pertimbangkan menaikkan timeout solver di atas {config.solver_options.max_solver_seconds} detik untuk scenario dengan cluster priority padat."
            )
        if (
            experiment_map.get("priority_eta_disabled")
            and experiment_map["priority_eta_disabled"].summary.scenario_status in {"feasible", "partial"}
        ):
            recommendations.append(
                "Evaluasi kembali apakah seluruh order priority benar-benar harus mandatory, atau cukup dijaga dengan penalty keterlambatan."
            )
        if (
            experiment_map.get("allow_unserved_on")
            and experiment_map["allow_unserved_on"].summary.scenario_status == "partial"
        ):
            recommendations.append(
                "Aktifkan allow unserved untuk operasi harian bila bisnis menerima sebagian order dijatuhkan dengan penalty."
            )
        if config.hard_constraints.time_window:
            recommendations.append(
                "Review time window hard pada SPBU dengan travel time jauh atau cluster priority tinggi."
            )
        if not recommendations:
            recommendations.append("Gunakan level 2 analysis untuk eksperimen diagnosis yang lebih kuat.")
        return recommendations

    def _is_preprocessing_failure(self, scenario) -> bool:
        result = scenario.result
        if result is None or result.status not in {"partial", "preprocessing_failed"}:
            return False
        if result.total_delivered_demand != 0 or result.active_truck_count != 0:
            return False
        if "No feasible shipments remained after preprocessing." in (result.message or ""):
            return True
        preprocessing_codes = {
            item.get("code")
            for item in (result.preprocessing_notes or [])
            if isinstance(item, dict)
        }
        return "NO_FEASIBLE_SHIPMENTS" in preprocessing_codes

    def _dominant_unserved_reason(self, scenario) -> str | None:
        result = scenario.result
        if result is None or not result.unserved_orders:
            return None
        counts = Counter(item.reason for item in result.unserved_orders if item.reason)
        if not counts:
            return None
        return counts.most_common(1)[0][0]

    def _rank_problematic_orders(
        self,
        payload: schemas.OptimizationRequest,
        config: schemas.OptimizationConfig,
        unserved_parent_order_ids: set[str],
        time_by_spbu: dict[str, int],
        experiment_results: dict[str, _ExperimentRun],
    ) -> list[schemas.ScenarioAnalysisProblematicOrder]:
        earliest_shift_start = min((hhmm_to_minutes(item.shift_start) or 0 for item in payload.available_trucks), default=0)
        earliest_departure = earliest_shift_start + payload.depot_service_time_minutes
        priority_cluster_by_spbu = Counter(item.spbu_id for item in payload.orders if item.priority)
        total_cluster_by_spbu = Counter(item.spbu_id for item in payload.orders)
        experiment_unserved: set[str] = set()
        experiment_lateness: dict[str, int] = {}

        for experiment_id, experiment_run in experiment_results.items():
            result = experiment_run.result
            if result is None:
                continue
            experiment_unserved.update(item.parent_order_id for item in result.unserved_orders)
            if experiment_id == "priority_eta_disabled":
                arrival_map = self._extract_arrivals(result)
                for order in payload.orders:
                    if not order.priority or not order.eta:
                        continue
                    arrival = arrival_map.get(order.order_id)
                    if arrival is None:
                        continue
                    lateness = max(0, arrival - (hhmm_to_minutes(order.eta) or arrival))
                    if lateness > 0:
                        experiment_lateness[order.order_id] = max(
                            experiment_lateness.get(order.order_id, 0),
                            lateness,
                        )

        ranked: list[schemas.ScenarioAnalysisProblematicOrder] = []
        for order in payload.orders:
            heuristic_score = 0.0
            experimental_score = 0.0
            reasons: list[str] = []
            travel_time = time_by_spbu.get(order.spbu_id)
            if order.order_id in unserved_parent_order_ids:
                heuristic_score += 20
                reasons.append("Order muncul sebagai unserved pada hasil scenario saat ini.")
            if order.priority:
                heuristic_score += 35
                reasons.append("Order priority ikut menekan search karena tetap wajib dilayani pada rule saat ini.")
            if travel_time is not None:
                if travel_time >= 120:
                    heuristic_score += 20
                    reasons.append(f"Travel time direct dari depot ke SPBU sekitar {travel_time} menit.")
                elif travel_time >= 90:
                    heuristic_score += 10
                    reasons.append(f"Travel time direct dari depot ke SPBU sekitar {travel_time} menit.")
            if order.priority and order.eta:
                eta_minutes = hhmm_to_minutes(order.eta)
                if eta_minutes is not None and travel_time is not None:
                    slack = eta_minutes - (earliest_departure + travel_time)
                    if slack < 0:
                        heuristic_score += 40
                        reasons.append(
                            f"ETA {order.eta} lebih cepat dari earliest direct arrival sekitar {max(0, earliest_departure + travel_time)} menit dispatch."
                        )
                    elif slack < 30:
                        heuristic_score += 25
                        reasons.append(f"ETA {order.eta} sangat ketat terhadap travel time direct.")
                    elif slack < 60:
                        heuristic_score += 15
                        reasons.append(f"ETA {order.eta} cukup ketat terhadap travel time direct.")
            priority_cluster_size = priority_cluster_by_spbu.get(order.spbu_id, 0)
            spbu_label = order.spbu_name or order.spbu_id
            if priority_cluster_size > 1:
                heuristic_score += 12 + ((priority_cluster_size - 2) * 4)
                reasons.append(
                    f"{spbu_label} memiliki {priority_cluster_size} order priority yang saling berebut slot rute."
                )
            total_cluster_size = total_cluster_by_spbu.get(order.spbu_id, 0)
            if total_cluster_size > 2:
                heuristic_score += 6
                reasons.append(f"{spbu_label} memiliki cluster order padat ({total_cluster_size} order).")
            if order.order_id in experiment_unserved:
                experimental_score += 25
                reasons.append("Pada eksperimen diagnosis, order ini tetap muncul dalam subset yang sulit dilayani.")
            if order.order_id in experiment_lateness:
                lateness = experiment_lateness[order.order_id]
                experimental_score += min(70, lateness / 4)
                reasons.append(
                    f"Pada eksperimen pembanding, order ini baru bisa tiba {lateness} menit setelah ETA target."
                )
            total_score = round(heuristic_score + experimental_score, 2)
            ranked.append(
                schemas.ScenarioAnalysisProblematicOrder(
                    order_id=order.order_id,
                    spbu_id=order.spbu_id,
                    priority=order.priority,
                    eta=order.eta,
                    heuristic_score=round(heuristic_score, 2),
                    experimental_score=round(experimental_score, 2),
                    total_score=total_score,
                    reasons=list(dict.fromkeys(reasons)),
                )
            )
        ranked.sort(key=lambda item: (-item.total_score, item.order_id))
        return ranked[:10]

    def _solver_status_name(self, search_status: int) -> str:
        enum_type = routing_enums_pb2.RoutingSearchStatus
        name_fn = getattr(enum_type, "Name", None)
        if callable(name_fn):
            try:
                return name_fn(search_status)
            except Exception:
                pass

        descriptor = getattr(enum_type, "DESCRIPTOR", None)
        if descriptor is not None:
            try:
                return descriptor.EnumValueName(int(search_status))
            except Exception:
                pass

        return str(search_status)

    def _extract_arrivals(self, result: schemas.OptimizationResultResponse) -> dict[str, int]:
        arrivals: dict[str, int] = {}
        for route in result.route_details:
            for stop in route.stops:
                if stop.stop_kind != "delivery":
                    continue
                eta_minutes = hhmm_to_minutes(stop.eta)
                if eta_minutes is None:
                    continue
                current = arrivals.get(stop.parent_order_id)
                if current is None or eta_minutes < current:
                    arrivals[stop.parent_order_id] = eta_minutes
        return arrivals
