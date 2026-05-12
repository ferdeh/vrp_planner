import {
  useFieldArray,
  useWatch,
  type Control,
  type FieldErrors,
  type UseFormRegister,
  type UseFormSetValue,
} from "react-hook-form";
import type { OptimizationRequest, SpbuData } from "../../types/api";

const productOptions = [
  { value: "PERTALITE", label: "Pertalite" },
  { value: "PERTAMAX", label: "Pertamax" },
  { value: "PERTAMAX_TURBO", label: "Pertamax Turbo" },
  { value: "PERTAMAX_GREEN", label: "Pertamax Green" },
  { value: "BIO_SOLAR", label: "Bio Solar" },
  { value: "DEXLITE", label: "Dexlite" },
  { value: "PERTAMINA_DEX", label: "Pertamina Dex" },
] as const;

export function OrderTableField({
  control,
  register,
  setValue,
  spbuOptions,
  depotSelected,
  onLoadImport,
  onLoadSample,
  sampleMessage,
  sampleMessageTone = "info",
  errors,
}: {
  control: Control<OptimizationRequest>;
  register: UseFormRegister<OptimizationRequest>;
  setValue: UseFormSetValue<OptimizationRequest>;
  spbuOptions: SpbuData[];
  depotSelected: boolean;
  onLoadImport?: () => void;
  onLoadSample?: () => void;
  sampleMessage?: string | null;
  sampleMessageTone?: "info" | "error";
  errors?: FieldErrors<OptimizationRequest>["orders"];
}) {
  const { fields, append, remove } = useFieldArray({
    control,
    name: "orders",
  });
  const watchedOrders = useWatch({
    control,
    name: "orders",
  });
  const tableHasError = Boolean(errors?.message);
  const messageClass = sampleMessageTone === "error" ? "error-text" : "text-sm text-sky-700";
  const getInputClass = (hasError: boolean) => (hasError ? "input input-error" : "input");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-ink">Order Harian</h3>
          <p className="text-sm text-slate-500">Input kebutuhan BBM per SPBU.</p>
        </div>
        <div className="flex gap-3">
          {onLoadImport ? (
            <button type="button" className="btn-secondary" onClick={onLoadImport}>
              Load Import Data
            </button>
          ) : null}
          {onLoadSample ? (
            <button type="button" className="btn-secondary" onClick={onLoadSample}>
              Load Sample Data
            </button>
          ) : null}
          <button
            type="button"
            className="btn-secondary"
            onClick={() =>
              append({
                order_id: "",
                spbu_id: "",
                product_type: "PERTALITE",
                demand_kl: 8,
                priority: false,
                eta: "",
                service_time_minutes: 30,
                time_window_start: "08:00",
                time_window_end: "17:00",
              })
            }
          >
            Tambah Order
          </button>
        </div>
      </div>
      <div className={`table-shell ${tableHasError ? "section-error" : ""}`}>
        <table>
          <thead>
            <tr>
              <th>Order ID</th>
              <th>SPBU</th>
              <th>Produk</th>
              <th>Demand KL</th>
              <th>Service Time</th>
              <th>Priority</th>
              <th>ETA</th>
              <th>Aksi</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((field, index) => {
              const isPriority = Boolean(watchedOrders?.[index]?.priority);
              const rowError = Array.isArray(errors) ? errors[index] : undefined;
              return (
                <tr key={field.id}>
                  <td>
                    <input
                      className={getInputClass(Boolean(rowError?.order_id))}
                      {...register(`orders.${index}.order_id`)}
                    />
                    {rowError?.order_id?.message ? <p className="mt-2 error-text">{rowError.order_id.message}</p> : null}
                  </td>
                  <td>
                    <select className={getInputClass(Boolean(rowError?.spbu_id))} {...register(`orders.${index}.spbu_id`)}>
                      <option value="">
                        {depotSelected ? "Pilih SPBU" : "Pilih depot terlebih dahulu"}
                      </option>
                      {spbuOptions.map((item) => (
                        <option key={String(item.spbu_id)} value={String(item.spbu_id)}>
                          {String(item.name)}
                        </option>
                      ))}
                    </select>
                    {rowError?.spbu_id?.message ? <p className="mt-2 error-text">{rowError.spbu_id.message}</p> : null}
                  </td>
                  <td>
                    <select className={getInputClass(Boolean(rowError?.product_type))} {...register(`orders.${index}.product_type`)}>
                      {productOptions.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    {rowError?.product_type?.message ? <p className="mt-2 error-text">{rowError.product_type.message}</p> : null}
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.1"
                      className={getInputClass(Boolean(rowError?.demand_kl))}
                      {...register(`orders.${index}.demand_kl`, { valueAsNumber: true })}
                    />
                    {rowError?.demand_kl?.message ? <p className="mt-2 error-text">{rowError.demand_kl.message}</p> : null}
                  </td>
                  <td>
                    <input
                      type="number"
                      min="0"
                      step="5"
                      className={getInputClass(Boolean(rowError?.service_time_minutes))}
                      {...register(`orders.${index}.service_time_minutes`, { valueAsNumber: true })}
                    />
                    {rowError?.service_time_minutes?.message ? (
                      <p className="mt-2 error-text">{rowError.service_time_minutes.message}</p>
                    ) : null}
                  </td>
                  <td className="text-center">
                    <input
                      type="checkbox"
                      className="h-5 w-5 accent-sky-600"
                      aria-label={`Priority order ${index + 1}`}
                      {...register(`orders.${index}.priority`, {
                        onChange: (event) => {
                          if (!event.target.checked) {
                            setValue(`orders.${index}.eta`, "", { shouldDirty: true, shouldValidate: true });
                          }
                        },
                      })}
                    />
                  </td>
                  <td>
                    <input
                      className={getInputClass(Boolean(rowError?.eta))}
                      placeholder={isPriority ? "HH:MM" : "Checklist priority"}
                      disabled={!isPriority}
                      {...register(`orders.${index}.eta`)}
                    />
                    {rowError?.eta?.message ? <p className="mt-2 error-text">{rowError.eta.message}</p> : null}
                  </td>
                  <td>
                    <button type="button" className="text-sm font-semibold text-rose-600" onClick={() => remove(index)}>
                      Hapus
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-sm text-slate-500">
        Opsi SPBU diambil dari master data node `SPBU` dan difilter berdasarkan depot yang dipilih. Waktu service default adalah 30 menit. ETA hanya aktif untuk order yang ditandai priority.
      </p>
      {errors?.message ? <p className="error-text">{errors.message}</p> : null}
      {sampleMessage ? <p className={messageClass}>{sampleMessage}</p> : null}
    </div>
  );
}
