import { useFieldArray, type Control, type UseFormRegister } from "react-hook-form";
import type { OptimizationRequest } from "../../types/api";

export function TruckTableField({
  control,
  register,
  onSyncTrucks,
  syncDisabled,
  syncLoading,
  syncMessage,
  syncMessageTone = "info",
  errorMessage,
}: {
  control: Control<OptimizationRequest>;
  register: UseFormRegister<OptimizationRequest>;
  onSyncTrucks: () => void;
  syncDisabled: boolean;
  syncLoading: boolean;
  syncMessage?: string | null;
  syncMessageTone?: "info" | "error";
  errorMessage?: string;
}) {
  const { fields } = useFieldArray({
    control,
    name: "available_trucks",
  });
  const tableHasError = Boolean(errorMessage);
  const messageClass = syncMessageTone === "error" ? "error-text" : "text-sm text-amber-700";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-ink">Armada Tersedia</h3>
          <p className="text-sm text-slate-500">Truck yang boleh dipakai pada dispatch hari ini.</p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={onSyncTrucks}
          disabled={syncDisabled || syncLoading}
        >
          {syncLoading ? "Sync Truck..." : "Sync Truck"}
        </button>
      </div>
      <div className={`table-shell ${tableHasError ? "section-error" : ""}`}>
        <table>
          <thead>
            <tr>
              <th>No Polisi</th>
              <th>Tipe</th>
              <th>Kapasitas</th>
              <th>Not Available From</th>
              <th>Not Available To</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((field, index) => (
              <tr key={field.id}>
                <td>
                  <input type="hidden" {...register(`available_trucks.${index}.truck_id`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.no_polisi`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.truck_type`)} />
                  <input
                    type="hidden"
                    {...register(`available_trucks.${index}.truck_category`, {
                      setValueAs: (value: string | number | null | undefined) => {
                        if (value === null || value === undefined || value === "") {
                          return null;
                        }
                        const parsed = Number(value);
                        return Number.isFinite(parsed) ? parsed : null;
                      },
                    })}
                  />
                  <input type="hidden" {...register(`available_trucks.${index}.capacity_kl`, { valueAsNumber: true })} />
                  <input
                    type="hidden" {...register(`available_trucks.${index}.start_depot_id`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.end_depot_id`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.shift_start`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.shift_end`)} />
                  <input
                    type="hidden"
                    {...register(`available_trucks.${index}.compatible_product_types`, {
                      setValueAs: (value: string | string[]) =>
                        Array.isArray(value)
                          ? value
                        : value.split(",").map((item) => item.trim()).filter(Boolean),
                    })}
                  />
                  <input
                    type="hidden"
                    defaultValue={JSON.stringify(field.compartments ?? [])}
                    {...register(`available_trucks.${index}.compartments`, {
                      setValueAs: (value: string | Array<{ compartment_id: string; capacity_kl: number }>) => {
                        if (Array.isArray(value)) return value;
                        try {
                          return JSON.parse(value ?? "[]");
                        } catch {
                          return [];
                        }
                      },
                    })}
                  />
                  <input type="hidden" {...register(`available_trucks.${index}.status`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.not_available_from`)} />
                  <input type="hidden" {...register(`available_trucks.${index}.not_available_to`)} />
                  <span className="text-sm font-medium text-ink">{field.no_polisi || "-"}</span>
                </td>
                <td><span className="text-sm text-slate-700">{field.truck_type || "-"}</span></td>
                <td>
                  <span className="text-sm text-slate-700">
                    {field.capacity_kl ?? "-"}
                    {Array.isArray(field.compartments) && field.compartments.length
                      ? ` KL / ${field.compartments.length} compartment`
                      : ""}
                  </span>
                </td>
                <td><span className="text-sm text-slate-700">{field.not_available_from || "-"}</span></td>
                <td><span className="text-sm text-slate-700">{field.not_available_to || "-"}</span></td>
                <td><span className="text-sm text-slate-700">{field.status || "-"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-slate-500">
        Tombol sync truck akan mengambil unit truck yang available dari depot terpilih. Perhitungan cost solver memakai
        activation cost, distance weight, dan time weight dari setting internal app.
      </p>
      {errorMessage ? <p className="error-text">{errorMessage}</p> : null}
      {syncMessage ? <p className={messageClass}>{syncMessage}</p> : null}
    </div>
  );
}
