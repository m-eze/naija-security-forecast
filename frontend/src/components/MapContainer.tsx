"use client";

import dynamic from "next/dynamic";
import { useCallback, useState } from "react";
import type { GeoJSONCollection } from "@/types";
import TimeSlider from "./TimeSlider";
import IncidentTypeFilter, { type FilterMeta } from "./IncidentTypeFilter";

const NigeriaMap = dynamic(() => import("./NigeriaMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-slate-100 text-slate-400 text-sm">
      Loading map…
    </div>
  ),
});

interface Props {
  geojson: GeoJSONCollection;
}

export default function MapContainer({ geojson: initialGeoJSON }: Props) {
  const [activeGeoJSON, setActiveGeoJSON] = useState<GeoJSONCollection>(initialGeoJSON);
  const [isForecast, setIsForecast] = useState(false);
  const [dayOffset, setDayOffset] = useState(0);
  const [filterMeta, setFilterMeta] = useState<FilterMeta | null>(null);

  const handleTimeChange = useCallback(
    (newGeoJSON: GeoJSONCollection, forecast: boolean, day: number) => {
      setActiveGeoJSON(newGeoJSON);
      setIsForecast(forecast);
      setDayOffset(day);
    },
    []
  );

  const handleFilterChange = useCallback(
    (newGeoJSON: GeoJSONCollection | null, meta: FilterMeta | null) => {
      if (newGeoJSON === null) {
        // Filter cleared — restore today's composite
        setActiveGeoJSON(initialGeoJSON);
        setIsForecast(false);
        setDayOffset(0);
        setFilterMeta(null);
      } else {
        setActiveGeoJSON(newGeoJSON);
        setIsForecast(false);
        setDayOffset(0);
        setFilterMeta(meta);
      }
    },
    [initialGeoJSON]
  );

  const filterActive = filterMeta !== null;

  return (
    <div className="relative w-full h-full">
      <NigeriaMap geojson={activeGeoJSON} />

      {/* Forecast badge */}
      {isForecast && !filterActive && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-indigo-600 text-white text-xs font-bold px-3 py-1 rounded-full shadow-lg flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
          FORECAST · +{dayOffset} {dayOffset === 1 ? "day" : "days"}
        </div>
      )}

      {/* Active filter banner */}
      {filterActive && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-slate-800 text-white text-xs font-semibold px-4 py-1.5 rounded-full shadow-lg flex items-center gap-2 whitespace-nowrap">
          <span>{filterMeta!.label}</span>
          <span className="opacity-50">·</span>
          <span className="opacity-75">{filterMeta!.totalIncidents} incidents · {filterMeta!.lgasWithIncidents} LGAs · {filterMeta!.days}d</span>
        </div>
      )}

      {/* Bottom controls — filter replaces slider when active */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000]">
        {filterActive ? (
          <div className="bg-white border border-gray-200 rounded-xl shadow-lg px-5 py-3 min-w-[340px]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Filter by Incident Type
              </span>
              <span className="text-[10px] text-gray-400 italic">
                Click a filter again to deselect
              </span>
            </div>
            <IncidentTypeFilter onFilterChange={handleFilterChange} />
          </div>
        ) : (
          <div className="flex flex-col gap-2 items-center">
            <div className="bg-white border border-gray-200 rounded-xl shadow-lg px-5 py-3 min-w-[340px]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Filter by Incident Type
                </span>
              </div>
              <IncidentTypeFilter onFilterChange={handleFilterChange} />
            </div>
            <TimeSlider
              todayGeoJSON={initialGeoJSON}
              baseDate={new Date()}
              onGeoJSONChange={handleTimeChange}
            />
          </div>
        )}
      </div>
    </div>
  );
}
