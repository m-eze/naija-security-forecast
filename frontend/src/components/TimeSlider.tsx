"use client";

import { useCallback, useEffect, useState } from "react";
import type { GeoJSONCollection } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

const DAYS = [-3, -2, -1, 0, 1, 2, 3];
const TODAY_IDX = DAYS.indexOf(0); // 3

function addDays(base: Date, n: number): string {
  const d = new Date(base);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function formatDay(offset: number): string {
  if (offset === 0) return "Today";
  if (offset > 0) return `+${offset}`;
  return `${offset}`;
}

interface Props {
  todayGeoJSON: GeoJSONCollection;
  baseDate: Date;
  onGeoJSONChange: (geojson: GeoJSONCollection, isForecast: boolean, dayOffset: number) => void;
}

export default function TimeSlider({ todayGeoJSON, baseDate, onGeoJSONChange }: Props) {
  const [sliderIdx, setSliderIdx] = useState(TODAY_IDX);
  const [loading, setLoading] = useState(false);
  const [cache, setCache] = useState<Map<number, GeoJSONCollection>>(
    new Map([[0, todayGeoJSON]])
  );

  const dayOffset = DAYS[sliderIdx];
  const isHistorical = dayOffset < 0;
  const isForecastDay = dayOffset > 0;

  const fetchDay = useCallback(
    async (offset: number) => {
      if (cache.has(offset)) {
        onGeoJSONChange(cache.get(offset)!, offset > 0, offset);
        return;
      }
      setLoading(true);
      try {
        const dateStr = addDays(baseDate, offset);
        const res = await fetch(`${BASE}/risk/geojson?score_date=${dateStr}&simplified=true`);
        if (!res.ok) throw new Error(`${res.status}`);
        const data: GeoJSONCollection = await res.json();
        setCache((prev) => new Map(prev).set(offset, data));
        onGeoJSONChange(data, offset > 0, offset);
      } catch (e) {
        console.error("Failed to fetch day:", e);
      } finally {
        setLoading(false);
      }
    },
    [cache, baseDate, onGeoJSONChange]
  );

  useEffect(() => {
    fetchDay(dayOffset);
  }, [sliderIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pre-fetch flanking days in background
  useEffect(() => {
    const timer = setTimeout(() => {
      [-3, -1, 1, 3].forEach((d) => {
        if (!cache.has(d)) fetchDay(d);
      });
    }, 1500);
    return () => clearTimeout(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const targetDate = addDays(baseDate, dayOffset);

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-lg px-5 py-3 flex flex-col gap-2 min-w-[340px]">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {isHistorical ? "Historical Risk" : isForecastDay ? "Risk Forecast" : "Current Risk"}
          </span>
          {isForecastDay && (
            <span className="text-[10px] bg-indigo-100 text-indigo-600 font-semibold px-1.5 py-0.5 rounded">
              FORECAST
            </span>
          )}
          {isHistorical && (
            <span className="text-[10px] bg-slate-100 text-slate-500 font-semibold px-1.5 py-0.5 rounded">
              HISTORICAL
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {loading && <span className="text-[10px] text-gray-400 animate-pulse">Loading…</span>}
          <span className="text-xs font-medium text-gray-700 tabular-nums">{targetDate}</span>
        </div>
      </div>

      {/* Slider — static two-tone track: slate (past) | indigo (future) */}
      <div className="relative">
        <input
          type="range"
          min={0}
          max={DAYS.length - 1}
          value={sliderIdx}
          onChange={(e) => setSliderIdx(Number(e.target.value))}
          className="w-full h-1.5 appearance-none rounded-full outline-none cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none
            [&::-webkit-slider-thumb]:w-4
            [&::-webkit-slider-thumb]:h-4
            [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-slate-700
            [&::-webkit-slider-thumb]:shadow-md
            [&::-webkit-slider-thumb]:cursor-pointer
            [&::-moz-range-thumb]:w-4
            [&::-moz-range-thumb]:h-4
            [&::-moz-range-thumb]:rounded-full
            [&::-moz-range-thumb]:bg-slate-700
            [&::-moz-range-thumb]:border-0"
          style={{
            background:
              "linear-gradient(to right, #cbd5e1 0%, #cbd5e1 50%, #a5b4fc 50%, #a5b4fc 100%)",
          }}
        />
        {/* Centre hairline marks "Today" */}
        <div className="absolute top-0 left-1/2 -translate-x-px w-px h-1.5 bg-white/80 pointer-events-none" />
      </div>

      {/* Tick labels */}
      <div className="flex justify-between text-[10px] -mt-1 px-0.5">
        {DAYS.map((d, i) => (
          <button
            key={d}
            onClick={() => setSliderIdx(i)}
            className={`transition-colors ${
              i === sliderIdx
                ? d < 0
                  ? "text-slate-700 font-semibold"
                  : d > 0
                  ? "text-indigo-600 font-semibold"
                  : "text-gray-900 font-semibold"
                : d < 0
                ? "text-slate-400 hover:text-slate-600"
                : d > 0
                ? "text-gray-400 hover:text-indigo-600"
                : "text-gray-400 hover:text-gray-700"
            }`}
          >
            {formatDay(d)}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-gray-300 -mt-1">
        <span>← past</span>
        <span>future →</span>
      </div>

      {/* Contextual footnote */}
      {isForecastDay && (
        <p className="text-[10px] text-gray-400 border-t border-gray-100 pt-2">
          Forecast based on incident trend velocity, news sentiment decay, and historical patterns.
        </p>
      )}
      {isHistorical && (
        <p className="text-[10px] text-gray-400 border-t border-gray-100 pt-2">
          Historical estimate back-projected from today&apos;s trend signals.
        </p>
      )}
    </div>
  );
}
