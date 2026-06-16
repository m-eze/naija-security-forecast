"use client";

import { useState } from "react";
import useSWR from "swr";
import type { PaginatedNews } from "@/types";
import { fetcher } from "@/lib/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001/api";

const SENTIMENT_ICON: Record<string, string> = {
  negative: "🔴",
  neutral: "🟡",
  positive: "🟢",
};

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return "< 1h ago";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

interface Props {
  state?: string;
}

export default function NewsFeed({ state }: Props) {
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), page_size: "10", security_only: "true" });
  if (state) params.set("state", state);

  const { data, error, isLoading } = useSWR<PaginatedNews>(
    `${BASE}/news?${params}`,
    fetcher,
    { refreshInterval: 300_000 }
  );

  if (error) return <p className="text-sm text-red-500 p-4">Failed to load news.</p>;
  if (isLoading) return <p className="text-sm text-gray-400 p-4 animate-pulse">Loading news…</p>;
  if (!data?.items.length) return <p className="text-sm text-gray-400 p-4">No security news found.</p>;

  const totalPages = Math.ceil((data.total || 0) / 10);

  return (
    <div className="space-y-2">
      {data.items.map((article) => (
        <a
          key={article.id}
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block bg-white hover:bg-gray-50 rounded-lg p-3 border border-gray-100 transition-colors"
        >
          <div className="flex items-start gap-2">
            <span className="text-sm mt-0.5">
              {SENTIMENT_ICON[article.sentiment_label] ?? "🟡"}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800 leading-snug line-clamp-2">
                {article.headline}
              </p>
              <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                <span className="font-medium text-gray-500">{article.source}</span>
                {article.extracted_state && (
                  <span className="bg-gray-100 rounded px-1">{article.extracted_state}</span>
                )}
                <span>{timeAgo(article.published_at)}</span>
              </div>
            </div>
          </div>
        </a>
      ))}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="text-sm text-blue-600 disabled:text-gray-300 hover:underline"
          >
            ← Prev
          </button>
          <span className="text-xs text-gray-400">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="text-sm text-blue-600 disabled:text-gray-300 hover:underline"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
