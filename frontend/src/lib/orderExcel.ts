import * as XLSX from "xlsx";
import type { OrderInput, ScenarioDetailResponse } from "../types/api";

const ORDER_IMPORT_TYPE = "vrp-planner-order-import";

export type ImportedOrderRow = Omit<OrderInput, "spbu_id"> & {
  spbu_id?: string;
  spbu_name?: string | null;
};

export type ParsedOrderImport = {
  dispatchDate?: string;
  depotName?: string;
  depotCode?: string;
  orders: ImportedOrderRow[];
};

type SheetRow = Record<string, unknown>;

const columnAliases = {
  scenarioId: ["Scenario ID", "scenario_id"],
  dispatchDate: ["Dispatch Date", "dispatch_date"],
  depotName: ["Depot Name", "depot_name"],
  depotCode: ["Depot Code", "depot_id"],
  orderId: ["Order ID", "order_id"],
  spbuName: ["SPBU Name", "spbu_name"],
  spbuCode: ["SPBU Code", "spbu_id"],
  productType: ["Product Type", "product_type"],
  demandKl: ["Demand KL", "demand_kl"],
  priority: ["Priority", "priority"],
  eta: ["ETA", "eta"],
  serviceTimeMinutes: ["Service Time Minutes", "service_time_minutes"],
  timeWindowStart: ["Time Window Start", "time_window_start"],
  timeWindowEnd: ["Time Window End", "time_window_end"],
} as const;

export function normalizeImportKey(value: string | null | undefined) {
  return String(value ?? "")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

export function importNamesMatch(left: string | null | undefined, right: string | null | undefined) {
  const normalizedLeft = normalizeImportKey(left);
  const normalizedRight = normalizeImportKey(right);
  if (!normalizedLeft || !normalizedRight) {
    return false;
  }
  return (
    normalizedLeft === normalizedRight
    || normalizedLeft.endsWith(` ${normalizedRight}`)
    || normalizedRight.endsWith(` ${normalizedLeft}`)
  );
}

function readField(row: SheetRow, aliases: readonly string[], fallback = "") {
  for (const alias of aliases) {
    const value = row[alias];
    if (value !== null && value !== undefined && String(value).trim() !== "") {
      return String(value).trim();
    }
  }
  return fallback;
}

function readNumberField(row: SheetRow, aliases: readonly string[], fallback: number) {
  const value = Number(readField(row, aliases));
  return Number.isFinite(value) ? value : fallback;
}

function readBooleanField(row: SheetRow, aliases: readonly string[]) {
  const value = readField(row, aliases);
  if (!value) {
    return false;
  }
  return ["true", "1", "yes", "y", "priority"].includes(value.toLowerCase());
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rowsToImport(rows: SheetRow[]): ParsedOrderImport {
  if (!rows.length) {
    throw new Error("File import tidak berisi data orders.");
  }

  const firstRow = rows[0];
  const orders = rows.map((row, index) => {
    const orderId = readField(row, columnAliases.orderId);
    const spbuName = readField(row, columnAliases.spbuName);
    const spbuCode = readField(row, columnAliases.spbuCode);
    const productType = readField(row, columnAliases.productType);
    const demandKl = readNumberField(row, columnAliases.demandKl, Number.NaN);

    if (!orderId || !productType || !Number.isFinite(demandKl) || demandKl <= 0) {
      throw new Error(`Order baris ${index + 1} wajib memiliki Order ID, Product Type, dan Demand KL.`);
    }
    if (!spbuName && !spbuCode) {
      throw new Error(`Order baris ${index + 1} wajib memiliki SPBU Name.`);
    }

    const priority = readBooleanField(row, columnAliases.priority);
    return {
      order_id: orderId,
      spbu_id: spbuCode || undefined,
      spbu_name: spbuName || null,
      product_type: productType,
      demand_kl: demandKl,
      priority,
      eta: priority ? readField(row, columnAliases.eta) : "",
      service_time_minutes: readNumberField(row, columnAliases.serviceTimeMinutes, 30),
      time_window_start: readField(row, columnAliases.timeWindowStart, "08:00"),
      time_window_end: readField(row, columnAliases.timeWindowEnd, "17:00"),
    };
  });

  return {
    dispatchDate: readField(firstRow, columnAliases.dispatchDate) || undefined,
    depotName: readField(firstRow, columnAliases.depotName) || undefined,
    depotCode: readField(firstRow, columnAliases.depotCode) || undefined,
    orders,
  };
}

function parseLegacyJson(payload: unknown): ParsedOrderImport {
  const sourceOrders = Array.isArray(payload)
    ? payload
    : isRecord(payload) && Array.isArray(payload.orders)
      ? payload.orders
      : null;

  if (!sourceOrders?.length) {
    throw new Error("File import tidak berisi data orders.");
  }

  const orders = sourceOrders.map((item, index) => {
    if (!isRecord(item)) {
      throw new Error(`Order baris ${index + 1} tidak valid.`);
    }

    const priority = readBooleanField(item, columnAliases.priority);
    return {
      order_id: readField(item, columnAliases.orderId),
      spbu_id: readField(item, columnAliases.spbuCode) || undefined,
      spbu_name: readField(item, columnAliases.spbuName) || null,
      product_type: readField(item, columnAliases.productType),
      demand_kl: readNumberField(item, columnAliases.demandKl, Number.NaN),
      priority,
      eta: priority ? readField(item, columnAliases.eta) : "",
      service_time_minutes: readNumberField(item, columnAliases.serviceTimeMinutes, 30),
      time_window_start: readField(item, columnAliases.timeWindowStart, "08:00"),
      time_window_end: readField(item, columnAliases.timeWindowEnd, "17:00"),
    };
  });

  return {
    dispatchDate: isRecord(payload) ? readField(payload, columnAliases.dispatchDate) || undefined : undefined,
    depotName: isRecord(payload) ? readField(payload, columnAliases.depotName) || undefined : undefined,
    depotCode: isRecord(payload) ? readField(payload, columnAliases.depotCode) || undefined : undefined,
    orders,
  };
}

export async function parseOrderImportFile(file: File): Promise<ParsedOrderImport> {
  if (file.name.toLowerCase().endsWith(".json")) {
    return parseLegacyJson(JSON.parse(await file.text()) as unknown);
  }

  const workbook = XLSX.read(await file.arrayBuffer(), { type: "array" });
  const sheetName = workbook.SheetNames[0];
  if (!sheetName) {
    throw new Error("Workbook tidak memiliki sheet order.");
  }

  const rows = XLSX.utils.sheet_to_json<SheetRow>(workbook.Sheets[sheetName], {
    defval: "",
  });
  return rowsToImport(rows);
}

export function downloadOrderWorkbook(detail: ScenarioDetailResponse, depotName: string) {
  const rows = detail.input_orders.map((order) => ({
    "Scenario ID": detail.scenario_id,
    "Dispatch Date": detail.dispatch_date,
    "Depot Name": depotName,
    "Depot Code": detail.depot_id,
    "Order ID": order.order_id,
    "SPBU Name": order.spbu_name || order.spbu_id,
    "SPBU Code": order.spbu_id,
    "Product Type": order.product_type,
    "Demand KL": order.demand_kl,
    Priority: order.priority ? "TRUE" : "FALSE",
    ETA: order.eta ?? "",
    "Service Time Minutes": order.service_time_minutes,
    "Time Window Start": order.time_window_start,
    "Time Window End": order.time_window_end,
  }));

  const worksheet = XLSX.utils.json_to_sheet(rows);
  worksheet["!cols"] = [
    { wch: 38 },
    { wch: 14 },
    { wch: 24 },
    { wch: 14 },
    { wch: 22 },
    { wch: 24 },
    { wch: 14 },
    { wch: 20 },
    { wch: 12 },
    { wch: 10 },
    { wch: 10 },
    { wch: 20 },
    { wch: 18 },
    { wch: 18 },
  ];

  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, "Orders");
  XLSX.writeFile(workbook, `orders-${detail.dispatch_date}-${detail.scenario_id.slice(0, 8)}.xlsx`, {
    bookType: "xlsx",
  });
}
