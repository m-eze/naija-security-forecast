import { api } from "@/lib/api";
import type { GeoJSONCollection, NationalSummary } from "@/types";
import Dashboard from "@/components/Dashboard";

export const revalidate = 300;

async function getData(): Promise<{ geojson: GeoJSONCollection; summary: NationalSummary }> {
  try {
    const [geojson, summary] = await Promise.all([
      api.riskGeoJSON(true),
      api.riskSummary(),
    ]);
    return { geojson, summary };
  } catch {
    return {
      geojson: { type: "FeatureCollection", features: [] },
      summary: {
        score_date: new Date().toISOString().slice(0, 10),
        total_lgas: 0,
        distribution: { SEVERE: 0, HIGH: 0, MODERATE: 0, LOW: 0 },
        states: [],
        total_incidents_90d: 0,
        total_fatalities_90d: 0,
        security_news_7d: 0,
      },
    };
  }
}

export default async function HomePage() {
  const { geojson, summary } = await getData();
  return <Dashboard initialGeoJSON={geojson} summary={summary} />;
}
