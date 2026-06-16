"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type { GeoJSONCollection, NationalSummary } from "@/types";
import NationalSummaryBar from "./NationalSummaryBar";
import StateRankingList from "./StateRankingList";
import NewsFeed from "./NewsFeed";
import FilterPanel, { type ActiveFilter } from "./FilterPanel";
import TimeSlider from "./TimeSlider";

const NigeriaMap = dynamic(() => import("./NigeriaMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-slate-100 text-slate-400 text-sm">
      Loading map…
    </div>
  ),
});

interface Props {
  initialGeoJSON: GeoJSONCollection;
  summary: NationalSummary;
}

export default function Dashboard({ initialGeoJSON, summary }: Props) {
  const [activeGeoJSON, setActiveGeoJSON] = useState(initialGeoJSON);
  const [activeFilter, setActiveFilter] = useState<ActiveFilter | null>(null);
  const [dayOffset, setDayOffset] = useState(0);
  const [isForecast, setIsForecast] = useState(false);

  const handleFilterChange = useCallback(
    (geojson: GeoJSONCollection | null, filter: ActiveFilter | null) => {
      if (geojson === null) {
        setActiveGeoJSON(initialGeoJSON);
        setActiveFilter(null);
      } else {
        setActiveGeoJSON(geojson);
        setActiveFilter(filter);
        setDayOffset(0);
        setIsForecast(false);
      }
    },
    [initialGeoJSON]
  );

  const handleTimeChange = useCallback(
    (geojson: GeoJSONCollection, forecast: boolean, day: number) => {
      setActiveGeoJSON(geojson);
      setIsForecast(forecast);
      setDayOffset(day);
      setActiveFilter(null);
    },
    []
  );

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* ── Left sidebar ───────────────────────────────────────── */}
      <aside className="w-80 flex-shrink-0 flex flex-col overflow-y-auto border-r border-gray-200 bg-white">
        {/* App header */}
        <div className="px-4 pt-4 pb-3 border-b border-gray-100">
          <h1 className="text-lg font-bold text-gray-900 leading-tight">
            🇳🇬 Naija Security Forecast
          </h1>
          <p className="text-xs text-gray-400 mt-0.5">LGA-level risk index · updated daily</p>
        </div>

        {/* National summary */}
        <div className="px-4 py-3 border-b border-gray-100">
          <NationalSummaryBar summary={summary} />
        </div>

        {/* Incident type filter */}
        <div className="px-4 py-3 border-b border-gray-100">
          <FilterPanel
            activeFilter={activeFilter}
            onFilterChange={handleFilterChange}
          />
        </div>

        {/* State rankings */}
        <div className="px-4 py-3 flex-1">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            States by Risk Score
          </p>
          <StateRankingList states={summary.states} />
        </div>
      </aside>

      {/* ── Map ───────────────────────────────────────────────── */}
      <main className="flex-1 relative">
        <NigeriaMap geojson={activeGeoJSON} />

        {/* Forecast banner */}
        {isForecast && !activeFilter && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] bg-indigo-600 text-white text-xs font-bold px-3 py-1.5 rounded-full shadow-lg flex items-center gap-1.5 pointer-events-none">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            FORECAST · +{dayOffset} {Math.abs(dayOffset) === 1 ? "day" : "days"}
          </div>
        )}

        {/* Historical banner */}
        {!isForecast && dayOffset < 0 && !activeFilter && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] bg-slate-600 text-white text-xs font-bold px-3 py-1.5 rounded-full shadow-lg flex items-center gap-1.5 pointer-events-none">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-300" />
            HISTORICAL · {dayOffset} {Math.abs(dayOffset) === 1 ? "day" : "days"}
          </div>
        )}

        {/* Filter active banner */}
        {activeFilter && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-2 bg-slate-800 text-white text-xs font-semibold px-4 py-1.5 rounded-full shadow-lg pointer-events-none whitespace-nowrap">
            <span>{activeFilter.icon} {activeFilter.label}</span>
            <span className="w-px h-3 bg-white/30" />
            <span className="font-normal opacity-75">
              {activeFilter.totalIncidents.toLocaleString()} incidents · {activeFilter.lgasAffected} LGAs · {activeFilter.days}d
            </span>
          </div>
        )}

        {/* Time slider — hidden when filter active */}
        {!activeFilter && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000]">
            <TimeSlider
              todayGeoJSON={initialGeoJSON}
              baseDate={new Date()}
              onGeoJSONChange={handleTimeChange}
            />
          </div>
        )}
      </main>

      {/* ── Right sidebar ─────────────────────────────────────── */}
      <aside className="w-72 flex-shrink-0 flex flex-col border-l border-gray-200 bg-white">
        <div className="px-4 pt-4 pb-2 border-b border-gray-100">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
            Security News
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          <NewsFeed />
        </div>
      </aside>
    </div>
  );
}
