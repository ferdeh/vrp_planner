const allSteps = [
  "Building VRP Model",
  "Generating Initial Solution",
  "Validating Initial Solution",
  "Refining with OR-Tools",
  "Final Validation",
  "Completed",
];

export function SolverProgressTimeline({
  hybrid,
  activeStep,
}: {
  hybrid: boolean;
  activeStep: number;
}) {
  const steps = hybrid ? allSteps : [allSteps[0], allSteps[3], allSteps[4], allSteps[5]];

  return (
    <section className="panel">
      <div className="panel-body">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-sky-600">Progress</p>
        <div className="mt-5 grid gap-3">
          {steps.map((step, index) => {
            const active = index <= activeStep;
            return (
              <div
                key={step}
                className={`flex items-center gap-4 rounded-[22px] border px-4 py-3 ${
                  active ? "border-sky-200 bg-sky-50 text-sky-900" : "border-slate-200 bg-white text-slate-500"
                }`}
              >
                <div className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${
                  active ? "bg-sky-600 text-white" : "bg-slate-100 text-slate-500"
                }`}>
                  {index + 1}
                </div>
                <span className="text-sm font-medium">{step}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
