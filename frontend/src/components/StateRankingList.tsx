"use client";

import type { StateBreakdown } from "@/types";
import { scoreColor, levelFromScore, RISK_TEXT } from "@/lib/risk";

interface Props {
  states: StateBreakdown[];
  onSelectState?: (state: string) => void;
}

export default function StateRankingList({ states, onSelectState }: Props) {
  const sorted = [...states].sort((a, b) => b.avg_score - a.avg_score).slice(0, 15);

  return (
    <div className="space-y-1">
      {sorted.map((s, i) => {
        const level = levelFromScore(s.avg_score);
        return (
          <button
            key={s.state}
            onClick={() => onSelectState?.(s.state)}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-50 text-left transition-colors"
          >
            <span className="text-xs text-gray-400 w-5 text-right shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-1">
                <span className="text-sm font-medium text-gray-800 truncate">{s.state}</span>
                <span className={`text-xs font-bold shrink-0 ${RISK_TEXT[level]}`}>
                  {s.avg_score.toFixed(0)}
                </span>
              </div>
              <div className="h-1 bg-gray-100 rounded-full mt-1 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, s.avg_score)}%`,
                    backgroundColor: scoreColor(s.avg_score),
                  }}
                />
              </div>
            </div>
            {s.severe > 0 && (
              <span className="text-xs bg-red-100 text-red-600 rounded px-1 shrink-0">
                {s.severe} ⚠
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
