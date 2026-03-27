import { useQuery } from "@tanstack/react-query";
import { listDepots, listSpbu } from "../services/api";

export function useSpbuOptions(depotId?: string) {
  return useQuery({
    queryKey: ["spbu-options", depotId],
    queryFn: () => listSpbu(depotId),
    enabled: Boolean(depotId),
    staleTime: 60_000,
  });
}

export function useDepotOptions() {
  return useQuery({
    queryKey: ["depot-options"],
    queryFn: listDepots,
    staleTime: 60_000,
  });
}
