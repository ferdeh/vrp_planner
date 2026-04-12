import { useQuery } from "@tanstack/react-query";
import { AppLayout } from "../components/layout/AppLayout";
import { PageHeader } from "../components/layout/PageHeader";
import { getRepositoryVersions } from "../services/api";
import type { RepositoryVersionItem } from "../types/api";

type VersionCardDescriptor = {
  label: string;
  repository: RepositoryVersionItem;
};

type VersionSectionDescriptor = {
  title: string;
  repoName: string;
  cards: VersionCardDescriptor[];
};

function formatVersionDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
    .format(new Date(value))
    .replace(":", ".");
}

function statusLabel(item: RepositoryVersionItem) {
  if (!item.available) return "UNAVAILABLE";
  return item.dirty ? "DIRTY" : "CLEAN";
}

function statusClass(item: RepositoryVersionItem) {
  if (!item.available) return "border-slate-300 bg-slate-100 text-slate-600";
  return item.dirty
    ? "border-amber-200 bg-amber-50 text-petroblue"
    : "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function RepositoryVersionCard({ label, repository }: VersionCardDescriptor) {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(247,245,241,0.92)_100%)] p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.34em] text-slate-500">{label}</p>
          <p className="mt-5 text-4xl font-extrabold tracking-[-0.04em] text-ink">
            {repository.short_commit_hash ?? "-"}
          </p>
        </div>
        <span
          className={`inline-flex rounded-full border px-4 py-2 text-xs font-semibold tracking-[0.28em] ${statusClass(repository)}`}
        >
          {statusLabel(repository)}
        </span>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <div>
          <p className="text-[13px] font-semibold text-ink">Branch</p>
          <p className="mt-3 text-lg text-slate-500">{repository.branch ?? "-"}</p>
        </div>
        <div>
          <p className="text-[13px] font-semibold text-ink">Updated</p>
          <p className="mt-3 text-lg text-slate-500">{formatVersionDate(repository.committed_at)}</p>
        </div>
      </div>

      <div className="mt-8">
        <p className="text-[13px] font-semibold text-ink">Commit</p>
        <p className="mt-3 break-words text-lg leading-8 text-slate-500">
          {repository.commit_message ?? repository.error ?? "Metadata git belum tersedia."}
        </p>
      </div>
    </section>
  );
}

function buildSections(repositories: RepositoryVersionItem[]): VersionSectionDescriptor[] {
  const plannerRepository =
    repositories.find((item) => item.key === "vrp_planner") ??
    ({
      key: "vrp_planner",
      title: "VRP Planner",
      repo_name: "vrp_planner",
      branch: null,
      commit_hash: null,
      short_commit_hash: null,
      commit_message: null,
      committed_at: null,
      dirty: false,
      available: false,
      source: "unavailable",
      error: "Metadata vrp_planner belum tersedia.",
    } satisfies RepositoryVersionItem);
  const infraRepository =
    repositories.find((item) => item.key === "vrp_infa") ??
    ({
      key: "vrp_infa",
      title: "VRP Infra",
      repo_name: "vrp_infa",
      branch: null,
      commit_hash: null,
      short_commit_hash: null,
      commit_message: null,
      committed_at: null,
      dirty: false,
      available: false,
      source: "unavailable",
      error: "Metadata vrp_infa belum tersedia.",
    } satisfies RepositoryVersionItem);

  return [
    {
      title: "VRP Planner",
      repoName: plannerRepository.repo_name,
      cards: [
        { label: "Frontend", repository: plannerRepository },
        { label: "Backend", repository: plannerRepository },
      ],
    },
    {
      title: "VRP Infra",
      repoName: infraRepository.repo_name,
      cards: [{ label: "Infrastructure", repository: infraRepository }],
    },
  ];
}

export function VersionPage() {
  const versionQuery = useQuery({
    queryKey: ["repository-versions"],
    queryFn: getRepositoryVersions,
  });

  const sections = buildSections(versionQuery.data?.repositories ?? []);

  return (
    <AppLayout>
      <PageHeader
        title="Version Git"
        description="Versi ini diambil dari workspace atau metadata build yang sedang dipakai app untuk menjelaskan commit yang sedang live."
        action={
          <button
            type="button"
            className="btn-secondary"
            onClick={() => versionQuery.refetch()}
            disabled={versionQuery.isFetching}
          >
            {versionQuery.isFetching ? "Memuat..." : "Refresh Version"}
          </button>
        }
      />

      {versionQuery.isError ? (
        <section className="panel">
          <div className="panel-body">
            <p className="text-sm leading-7 text-rose-600">
              Gagal memuat metadata git dari backend.
            </p>
          </div>
        </section>
      ) : null}

      <div className="space-y-6">
        {sections.map((section) => (
          <section key={section.title} className="panel">
            <div className="panel-body space-y-6">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.34em] text-slate-500">Repository</p>
                <h2 className="mt-4 text-4xl font-extrabold tracking-[-0.04em] text-ink">{section.title}</h2>
                <p className="mt-4 text-lg text-slate-500">{section.repoName}</p>
              </div>

              <div className="grid gap-6">
                {section.cards.map((card) => (
                  <RepositoryVersionCard
                    key={`${section.title}-${card.label}`}
                    label={card.label}
                    repository={card.repository}
                  />
                ))}
              </div>
            </div>
          </section>
        ))}
      </div>
    </AppLayout>
  );
}
