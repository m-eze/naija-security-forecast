"use client";

import { useEffect, useState, useCallback } from "react";
import type { GeoJSONCollection } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

interface FilterDef {
  id: string;
  label: string;
  icon: string;
}

const LOOKBACK_OPTIONS = [
  { value: 30, label: "30 days" },
  { value: 90, label: "90 days" },
  { value: 365, label: "1 year" },
  { value: 1825, label: "5 years" },
];

interface Props {
  onFilterChange: (geojson: GeoJSONCollection | null, meta: FilterMeta | null) => void;
}

export interface FilterMeta {
  filterId: string;
  label: string;
  days: number;
  totalIncidents: number;
  lgasWithIncidents: number;
}

export default function IncidentTypeFilter({ onFilterChange }: Props) {
  const [filters, setFilters] = useState<FilterDef[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [days, setDays] = useState(365);
  const [loading, setLoading] = useState(false);

  // Load filter definitions once
  useEffect(() => {
    fetch(`${BASE}/incidents/filters`)
      .then((r) => r.json())
      .then(setFilters)
      .catch(console.error);
  }, []);

  const fetchFilter = useCallback(
    async (filterId: string, lookback: number) => {
      setLoading(true);
      try {
        const res = await fetch(
          `${BASE}/incidents/geojson?filter=${filterId}&days=${lookback}`
        );
        if (!res.ok) throw new Error(`${res.status}`);
        const data: GeoJSONCollection & { metadata: Record<string, unknown> } =
          await res.json();
        const meta = data.metadata as Record<string, unknown>;
        onFilterChange(data, {
          filterId,
          label: meta.filter_label as string,
          days: lookback,
          totalIncidents: (meta.total_matching_incidents as number) ?? 0,
          lgasWithIncidents: (meta.lgas_with_incidents as number) ?? 0,
        });
      } catch (e) {
        console.error("Filter fetch failed:", e);
      } finally {
        setLoading(false);
      }
    },
    [onFilterChange]
  );

  const handleSelect = (id: string) => {
    if (activeId === id) {
      // Deselect → restore composite
      setActiveId(null);
      onFilterChange(null, null);
    } else {
      setActiveId(id);
      fetchFilter(id, days);
    }
  };

  const handleDaysChange = (newDays: number) => {
    setDays(newDays);
    if (activeId) fetchFilter(activeId, newDays);
  };

  return (
    <div className="space-y-2">
      {/* Filter chips */}
      <div className="flex flex-wrap gap-1.5">
        {filters.map((f) => (
          <button
            key={f.id}
            onClick={() => handleSelect(f.id)}
            className={`
              inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium
              border transition-all duration-150 whitespace-nowrap
              ${
                activeId === f.id
                  ? "bg-slate-800 text-white border-slate-800 shadow-sm"
                  : "bg-white text-gray-600 border-gray-200 hover:border-slate-400 hover:text-slate-700"
              }
            `}
          >
            <span>{f.icon}</span>
            <span>{f.label}</span>
          </button>
        ))}
      </div>

      {/* Lookback selector — only visible when a filter is active */}
      {activeId && (
        <div className="flex items-center gap-1.5 pt-1">
          {loading && (
            <span className="text-[10px] text-gray-400 animate-pulse mr-1">Loading…</span>
          )}
          <span className="text-[10px] text-gray-400 uppercase tracking-wide">Period:</span>
          {LOOKBACK_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleDaysChange(opt.value)}
              className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                days === opt.value
                  ? "bg-slate-700 text-white border-slate-700"
                  : "text-gray-500 border-gray-200 hover:border-gray-400"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
