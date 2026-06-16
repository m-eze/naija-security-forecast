import type {
  RiskMapResponse,
  NationalSummary,
  RiskScoreDetail,
  PaginatedNews,
  GeoJSONCollection,
} from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  }
  const res = await fetch(url.toString(), { next: { revalidate: 300 } });
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

export const api = {
  riskMap: () => get<RiskMapResponse>("/risk/map"),
  riskSummary: () => get<NationalSummary>("/risk/summary"),
  riskLga: (lgaId: string) => get<RiskScoreDetail>(`/risk/lga/${lgaId}`),
  riskGeoJSON: (simplified?: boolean) =>
    get<GeoJSONCollection>("/risk/geojson", simplified ? { simplified: "true" } : undefined),
  news: (page = 1, state?: string) =>
    get<PaginatedNews>("/news", {
      page: String(page),
      page_size: "20",
      security_only: "true",
      ...(state ? { state } : {}),
    }),
};

export function fetcher<T>(url: string): Promise<T> {
  return fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });
}
