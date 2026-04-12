import { Navigate, Route, Routes } from "react-router-dom";
import { ScenarioAnalysisPage } from "../pages/ScenarioAnalysisPage";
import { DashboardPage } from "../pages/DashboardPage";
import { NewOptimizationPage } from "../pages/NewOptimizationPage";
import { ScenarioComparePage } from "../pages/ScenarioComparePage";
import { ScenarioDetailPage } from "../pages/ScenarioDetailPage";
import { ScenariosPage } from "../pages/ScenariosPage";
import { SettingsPage } from "../pages/SettingsPage";
import { UserGuidePage } from "../pages/UserGuidePage";
import { VersionPage } from "../pages/VersionPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/new-optimization" element={<NewOptimizationPage />} />
      <Route path="/scenarios" element={<ScenariosPage />} />
      <Route path="/scenario-analysis" element={<ScenarioAnalysisPage />} />
      <Route path="/scenarios/compare" element={<ScenarioComparePage />} />
      <Route path="/scenarios/:scenarioId" element={<ScenarioDetailPage />} />
      <Route path="/user-guide" element={<UserGuidePage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/version" element={<VersionPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
