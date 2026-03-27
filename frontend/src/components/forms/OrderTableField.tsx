import { useFieldArray, useWatch, type Control, type UseFormRegister, type UseFormSetValue } from "react-hook-form";
import type { OptimizationRequest } from "../../types/api";

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
  onLoadSample,
  sampleMessage,
}: {
  control: Control<OptimizationRequest>;
  register: UseFormRegister<OptimizationRequest>;
  setValue: UseFormSetValue<OptimizationRequest>;
  spbuOptions: Array<Record<string, unknown>>;
  depotSelected: boolean;
  onLoadSample?: () => void;
  sampleMessage?: string | null;
}) {
  const { fields, append, remove } = useFieldArray({
    control,
    name: "orders",
  });
  const watchedOrders = useWatch({
    control,
    name: "orders",
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-ink">Order Harian</h3>
          <p className="text-sm text-slate-500">Input kebutuhan BBM per SPBU.</p>
        </div>
        <div className="flex gap-3">
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
      <div className="table-shell">
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
              return (
                <tr key={field.id}>
                  <td><input className="input" {...register(`orders.${index}.order_id`)} /></td>
                  <td>
                    <select className="input" {...register(`orders.${index}.spbu_id`)}>
                      <option value="">
                        {depotSelected ? "Pilih SPBU" : "Pilih depot terlebih dahulu"}
                      </option>
                      {spbuOptions.map((item) => (
                        <option key={String(item.spbu_id)} value={String(item.spbu_id)}>
                          {String(item.name)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select className="input" {...register(`orders.${index}.product_type`)}>
                      {productOptions.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td><input type="number" step="0.1" className="input" {...register(`orders.${index}.demand_kl`, { valueAsNumber: true })} /></td>
                  <td>
                    <input
                      type="number"
                      min="0"
                      step="5"
                      className="input"
                      {...register(`orders.${index}.service_time_minutes`, { valueAsNumber: true })}
                    />
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
                      className="input"
                      placeholder={isPriority ? "HH:MM" : "Checklist priority"}
                      disabled={!isPriority}
                      {...register(`orders.${index}.eta`)}
                    />
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
      {sampleMessage ? <p className="text-sm text-sky-700">{sampleMessage}</p> : null}
    </div>
  );
}
