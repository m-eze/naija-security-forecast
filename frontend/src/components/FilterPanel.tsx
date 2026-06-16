"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import type { GeoJSONCollection } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

export interface ActiveFilter {
  id: string;
  label: string;
  icon: string;
  days: number;
  totalIncidents: number;
  lgasAffected: number;
}

interface FilterDef {
  id: string;
  label: string;
  icon: string;
}

const LOOKBACK = [
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
  { value: 365, label: "1yr" },
  { value: 1825, label: "5yr" },
];

interface Props {
  activeFilter: ActiveFilter | null;
  onFilterChange: (geojson: GeoJSONCollection | null, filter: ActiveFilter | null) => void;
}

export default function FilterPanel({ activeFilter, onFilterChange }: Props) {
  const [filters, setFilters] = useState<FilterDef[]>([]);
  const [days, setDays] = useState(365);
  const [loading, setLoading] = useState(false);
  const cacheRef = useRef<Map<string, GeoJSONCollection>>(new Map());

  useEffect(() => {
    fetch(`${BASE}/incidents/filters`)
      .then((r) => r.json())
      .then(setFilters)
      .catch(console.error);
  }, []);

  const fetchFilter = useCallback(
    async (filterId: string, lookback: number, def: FilterDef) => {
      const cacheKey = `${filterId}:${lookback}`;
      if (cacheRef.current.has(cacheKey)) {
        const cached = cacheRef.current.get(cacheKey)!;
        const meta = (cached as GeoJSONCollection & { metadata: Record<string, unknown> }).metadata as Record<string, unknown>;
        onFilterChange(cached, {
          id: filterId,
          label: def.label,
          icon: def.icon,
          days: lookback,
          totalIncidents: (meta.total_matching_incidents as number) ?? 0,
          lgasAffected: (meta.lgas_with_incidents as number) ?? 0,
        });
        return;
      }
      setLoading(true);
      try {
        const res = await fetch(
          `${BASE}/incidents/geojson?filter=${filterId}&days=${lookback}`
        );
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        cacheRef.current.set(cacheKey, data);
        const meta = data.metadata as Record<string, unknown>;
        onFilterChange(data, {
          id: filterId,
          label: def.label,
          icon: def.icon,
          days: lookback,
          totalIncidents: (meta.total_matching_incidents as number) ?? 0,
          lgasAffected: (meta.lgas_with_incidents as number) ?? 0,
        });
      } catch (e) {
        console.error("Filter fetch failed:", e);
      } finally {
        setLoading(false);
      }
    },
    [onFilterChange]
  );

  const handleSelect = (def: FilterDef) => {
    if (activeFilter?.id === def.id) {
      onFilterChange(null, null);
    } else {
      fetchFilter(def.id, days, def);
    }
  };

  const handleDays = (newDays: number) => {
    setDays(newDays);
    if (activeFilter) {
      const def = filters.find((f) => f.id === activeFilter.id);
      if (def) fetchFilter(def.id, newDays, def);
    }
  };

  return (
    <div className="space-y-3">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
          Filter by Incident Type
        </p>
        {activeFilter && (
          <button
            onClick={() => onFilterChange(null, null)}
            className="text-[10px] text-gray-400 hover:text-gray-600 flex items-center gap-0.5 transition-colors"
          >
            <span>✕</span> Clear
          </button>
        )}
      </div>

      {/* Active filter stats */}
      {activeFilter && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-base">{activeFilter.icon}</span>
            <div>
              <p className="text-xs font-semibold text-slate-700">{activeFilter.label}</p>
              <p className="text-[10px] text-slate-400">
                {activeFilter.totalIncidents > 0
                  ? `${activeFilter.totalIncidents.toLocaleString()} incidents · ${activeFilter.lgasAffected} LGAs`
                  : "No data — sync ACLED first"}
              </p>
            </div>
          </div>
          {loading && (
            <span className="w-3 h-3 rounded-full border-2 border-slate-300 border-t-slate-600 animate-spin" />
          )}
        </div>
      )}

      {/* Filter chip grid */}
      {filters.length === 0 ? (
        <div className="grid grid-cols-2 gap-1.5">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-9 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-1.5">
          {filters.map((f) => {
            const isActive = activeFilter?.id === f.id;
            return (
              <button
                key={f.id}
                onClick={() => handleSelect(f)}
                disabled={loading && activeFilter?.id !== f.id}
                className={`
                  flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-left
                  text-xs font-medium border transition-all duration-150
                  disabled:opacity-40 disabled:cursor-not-allowed
                  ${
                    isActive
                      ? "bg-slate-800 text-white border-slate-800 shadow-sm"
                      : "bg-white text-gray-600 border-gray-200 hover:border-slate-400 hover:bg-slate-50 hover:text-slate-800"
                  }
                `}
              >
                <span className="text-sm leading-none">{f.icon}</span>
                <span className="leading-tight">{f.label}</span>
                {isActive && loading && (
                  <span className="ml-auto w-2.5 h-2.5 rounded-full border border-white/40 border-t-white animate-spin" />
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Lookback selector */}
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] text-gray-400 uppercase tracking-wide shrink-0">Period</span>
        <div className="flex gap-1 flex-1">
          {LOOKBACK.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleDays(opt.value)}
              className={`flex-1 text-[10px] py-1 rounded border font-medium transition-colors ${
                days === opt.value
                  ? "bg-slate-700 text-white border-slate-700"
                  : "text-gray-500 border-gray-200 hover:border-gray-400 hover:text-gray-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* No data hint */}
      {!activeFilter && filters.length > 0 && (
        <p className="text-[10px] text-gray-300 leading-snug">
          Select a type to overlay incident density on the map.
        </p>
      )}
    </div>
  );
}
