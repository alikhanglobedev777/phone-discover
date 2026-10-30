export type FinderInput = {
  budget_pkr: string; city: string; condition: string; pta_status: string;
  pta_verification: string; brand: string; priorities: string[];
  ram_min: string; storage_min: string; strict_budget: boolean;
};

export function buildFinderRequest(filters: FinderInput) {
  const request: Record<string, unknown> = {
    message: "Recommend phones for my selected preferences",
    strict_budget: filters.strict_budget,
    max_results: 5,
  };
  for (const key of ["city", "condition", "pta_status", "pta_verification", "brand"] as const) {
    if (filters[key].trim()) request[key] = filters[key].trim();
  }
  for (const key of ["budget_pkr", "ram_min", "storage_min"] as const) {
    if (filters[key].trim()) request[key] = filters[key].trim();
  }
  if (filters.priorities.length) request.priorities = filters.priorities;
  return request;
}
