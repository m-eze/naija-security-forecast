"use client";

import useSWR from "swr";
import type { RiskScoreDetail } from "@/types";
import { fetcher } from "@/lib/api";
import RiskBadge from "./RiskBadge";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

interface Props {
  lgaId: string;
  lgaName: string;
  state: string;
  onClose: () => void;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const color =
    value > 74 ? "bg-red-500" : value > 49 ? "bg-orange-500" : value > 24 ? "bg-yellow-400" : "bg-green-500";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-600 mb-0.5">
        <span>{label}</span>
        <span className="font-medium">{value.toFixed(1)}</span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default function LGADetailPanel({ lgaId, lgaName, state, onClose }: Props) {
  const { data, isLoading, error } = useSWR<RiskScoreDetail>(
    `${BASE}/risk/lga/${lgaId}`,
    fetcher
  );

  return (
    <div className="absolute bottom-4 left-4 z-[1000] w-72 bg-white rounded-xl shadow-2xl border border-gray-200 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-100">
        <div>
          <h3 className="font-semibold text-gray-800 text-sm">{lgaName} LGA</h3>
          <p className="text-xs text-gray-400">{state} State</p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
          ×
        </button>
      </div>

      <div className="p-4">
        {isLoading && <p className="text-sm text-gray-400 animate-pulse">Loading…</p>}
        {error && <p className="text-sm text-red-400">Could not load details.</p>}

        {data && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <RiskBadge level={data.level} score={data.score} />
              <span className="text-xs text-gray-400">{data.score_date}</span>
            </div>

            <div className="space-y-2">
              <ScoreBar label="Frequency" value={data.incident_frequency_score} />
              <ScoreBar label="Trend" value={data.incident_trend_score} />
              <ScoreBar label="News sentiment" value={data.news_sentiment_score} />
            </div>

            {data.components && (
              <>
                <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
                  <div className="bg-gray-50 rounded p-2">
                    <div className="font-semibold text-gray-800 text-base">
                      {data.components.incident_count_90d}
                    </div>
                    incidents (90d)
                  </div>
                  <div className="bg-gray-50 rounded p-2">
                    <div className="font-semibold text-gray-800 text-base">
                      {data.components.fatalities_90d}
                    </div>
                    fatalities (90d)
                  </div>
                </div>

                {data.components.dominant_event_types.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-400 mb-1">Common event types</p>
                    <div className="flex flex-wrap gap-1">
                      {data.components.dominant_event_types.slice(0, 3).map((t) => (
                        <span key={t} className="bg-gray-100 text-gray-600 rounded px-1.5 py-0.5 text-xs">
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="text-xs text-gray-500">
                  Trend:{" "}
                  <span className="font-medium capitalize">{data.components.trend_direction}</span>
                  {data.components.trend_ratio != null && (
                    <> · {data.components.trend_ratio.toFixed(2)}×</>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
