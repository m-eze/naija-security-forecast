"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { GeoJSONCollection, NationalSummary, NewsPin, NewsPinsResponse } from "@/types";
import NationalSummaryBar from "./NationalSummaryBar";
import StateRankingList from "./StateRankingList";
import NewsFeed from "./NewsFeed";
import FilterPanel, { type ActiveFilter } from "./FilterPanel";
import TimeSlider from "./TimeSlider";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

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

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function Dashboard({ initialGeoJSON, summary }: Props) {
  const [activeGeoJSON, setActiveGeoJSON] = useState(initialGeoJSON);
  const [activeFilter, setActiveFilter] = useState<ActiveFilter | null>(null);
  const [dayOffset, setDayOffset] = useState(0);
  const [isForecast, setIsForecast] = useState(false);
  const [showNewsPins, setShowNewsPins] = useState(false);
  const [newsPins, setNewsPins] = useState<NewsPin[]>([]);

  // News sync state
  const [latestArticleAt, setLatestArticleAt] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const syncResultTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Increment to force NewsFeed re-mount after a sync
  const [feedKey, setFeedKey] = useState(0);

  // Fetch news status on mount
  useEffect(() => {
    fetch(`${BASE}/news/status`)
      .then((r) => r.json())
      .then((d) => setLatestArticleAt(d.latest_article_at))
      .catch(() => {});
  }, []);

  const handleResync = useCallback(async () => {
    if (syncing) return;
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await fetch(`${BASE}/news/sync`, { method: "POST" });
      if (!res.ok) throw new Error(`${res.status}`);
      const d = await res.json();
      const msg = `+${d.security_relevant} security · ${d.scraped} scraped`;
      setSyncResult(msg);
      setLatestArticleAt(new Date().toISOString());
      setFeedKey((k) => k + 1);
      // Refresh pins if shown
      if (showNewsPins) {
        fetch(`${BASE}/news/pins?days=7`)
          .then((r) => r.json())
          .then((pd: NewsPinsResponse) => setNewsPins(pd.pins))
          .catch(() => {});
      }
    } catch {
      setSyncResult("Sync failed");
    } finally {
      setSyncing(false);
      if (syncResultTimer.current) clearTimeout(syncResultTimer.current);
      syncResultTimer.current = setTimeout(() => setSyncResult(null), 4000);
    }
  }, [syncing, showNewsPins]);

  // Fetch pins when toggled on; clear when toggled off
  useEffect(() => {
    if (!showNewsPins) {
      setNewsPins([]);
      return;
    }
    fetch(`${BASE}/news/pins?days=7`)
      .then((r) => r.json())
      .then((d: NewsPinsResponse) => setNewsPins(d.pins))
      .catch(console.error);
  }, [showNewsPins]);

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
        <NigeriaMap geojson={activeGeoJSON} newsPins={newsPins} />

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

        {/* News pins toggle */}
        <div className="absolute bottom-4 left-4 z-[1000]">
          <button
            onClick={() => setShowNewsPins((v) => !v)}
            className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full shadow-lg border transition-colors ${
              showNewsPins
                ? "bg-slate-800 text-white border-slate-800"
                : "bg-white text-slate-600 border-gray-200 hover:bg-gray-50"
            }`}
          >
            <span className="flex items-center gap-0.5">
              <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
              <span className="w-2 h-2 rounded-full bg-yellow-400 inline-block" />
              <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
            </span>
            News pins
            {showNewsPins && newsPins.length > 0 && (
              <span className="bg-white/20 rounded-full px-1">{newsPins.length}</span>
            )}
          </button>
        </div>

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
        {/* Header with resync */}
        <div className="px-4 pt-4 pb-2 border-b border-gray-100">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              Security News
            </h2>
            <button
              onClick={handleResync}
              disabled={syncing}
              title="Re-scrape all RSS feeds"
              className={`flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded-md transition-colors ${
                syncing
                  ? "text-gray-300 cursor-not-allowed"
                  : "text-indigo-500 hover:bg-indigo-50 hover:text-indigo-700"
              }`}
            >
              <svg
                className={`w-3 h-3 ${syncing ? "animate-spin" : ""}`}
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <path d="M13.5 2.5A7 7 0 1 0 14 8" />
                <polyline points="14 2 14 6 10 6" />
              </svg>
              {syncing ? "Syncing…" : "Resync"}
            </button>
          </div>

          {/* Last updated / result line */}
          <div className="mt-0.5 h-4 flex items-center">
            {syncResult ? (
              <p className="text-[10px] text-green-600 font-medium">{syncResult}</p>
            ) : latestArticleAt ? (
              <p className="text-[10px] text-gray-400">
                Updated {timeAgo(latestArticleAt)}
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          <NewsFeed key={feedKey} />
        </div>
      </aside>
    </div>
  );
}
