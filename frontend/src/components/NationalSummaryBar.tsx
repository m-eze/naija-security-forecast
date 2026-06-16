"use client";

import type { NationalSummary } from "@/types";

interface Props {
  summary: NationalSummary;
}

export default function NationalSummaryBar({ summary }: Props) {
  const dist = summary.distribution;
  const total = summary.total_lgas || 1;
  const bars = [
    { label: "SEVERE", count: dist.SEVERE, color: "bg-red-500" },
    { label: "HIGH", count: dist.HIGH, color: "bg-orange-500" },
    { label: "MODERATE", count: dist.MODERATE, color: "bg-yellow-400" },
    { label: "LOW", count: dist.LOW, color: "bg-green-500" },
  ];

  return (
    <div className="bg-white rounded-xl shadow p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-700 text-sm uppercase tracking-wide">National Overview</h2>
        <span className="text-xs text-gray-400">{summary.score_date}</span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
        {bars.map(({ label, count, color }) =>
          count > 0 ? (
            <div
              key={label}
              className={`${color} transition-all`}
              style={{ width: `${(count / total) * 100}%` }}
              title={`${label}: ${count} LGAs`}
            />
          ) : null
        )}
        {/* Fill remaining with low color if none scored */}
        {total === 0 && <div className="bg-gray-200 flex-1" />}
      </div>
      <div className="grid grid-cols-4 gap-2 text-center">
        {bars.map(({ label, count }) => (
          <div key={label}>
            <div className="text-lg font-bold text-gray-800">{count}</div>
            <div className="text-xs font-medium text-gray-500">{label}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs text-center border-t border-gray-100 pt-2">
        <div>
          <div className="font-semibold text-gray-800">{summary.total_lgas}</div>
          <div className="text-gray-400">LGAs scored</div>
        </div>
        <div>
          <div className="font-semibold text-gray-800">{summary.total_incidents_90d}</div>
          <div className="text-gray-400">incidents 90d</div>
        </div>
        <div>
          <div className="font-semibold text-gray-800">{summary.security_news_7d}</div>
          <div className="text-gray-400">news 7d</div>
        </div>
      </div>
    </div>
  );
}
