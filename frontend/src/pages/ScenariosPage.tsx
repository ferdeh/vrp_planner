import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { ScenariosTable } from "../components/tables/ScenariosTable";
import { deleteScenarios, listScenarios } from "../services/api";

export function ScenariosPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const scenariosQuery = useQuery({
    queryKey: ["scenarios"],
    queryFn: listScenarios,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: 2000,
    refetchIntervalInBackground: true,
  });
  const deleteMutation = useMutation({
    mutationFn: deleteScenarios,
    onSuccess: async (result) => {
      setActionMessage(`${result.deleted_count} scenario berhasil dihapus.`);
      setSelectedScenarioIds([]);
      await queryClient.invalidateQueries({ queryKey: ["scenarios"] });
    },
    onError: () => {
      setActionMessage("Delete scenario gagal dijalankan.");
    },
  });

  const handleCompare = () => {
    if (selectedScenarioIds.length > 4) {
      setActionMessage("Compare dibatasi maksimum 4 scenario.");
      return;
    }
    navigate(`/scenarios/compare?ids=${selectedScenarioIds.join(",")}`);
  };

  return (
    <AppLayout>
      <PageHeader
        title="Scenario List"
        description="Daftar seluruh hasil optimisasi yang pernah dijalankan."
        action={
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              className="btn-secondary"
              disabled={selectedScenarioIds.length < 2}
              onClick={handleCompare}
            >
              Compare
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={selectedScenarioIds.length < 1 || deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(selectedScenarioIds)}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </button>
            <Link className="btn-primary" to="/new-optimization">
              Optimisasi Baru
            </Link>
          </div>
        }
      />

      <section className="panel">
        <div className="panel-body space-y-4">
          {actionMessage ? (
            <div className="rounded-[20px] border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
              {actionMessage}
            </div>
          ) : null}
          {scenariosQuery.isLoading ? (
            <p className="text-sm text-slate-500">Memuat daftar scenario...</p>
          ) : (
            <ScenariosTable
              items={scenariosQuery.data?.items ?? []}
              selectedIds={selectedScenarioIds}
              onSelectionChange={(ids) => {
                setSelectedScenarioIds(ids);
                setActionMessage(null);
              }}
            />
          )}
        </div>
      </section>
    </AppLayout>
  );
}
