"use client";

import type { RiskLevel } from "@/types";
import { RISK_BG } from "@/lib/risk";

interface Props {
  level: RiskLevel;
  score?: number;
  size?: "sm" | "md";
}

export default function RiskBadge({ level, score, size = "md" }: Props) {
  const pad = size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-sm";
  return (
    <span className={`inline-flex items-center gap-1 rounded font-semibold text-white ${RISK_BG[level]} ${pad}`}>
      {level}
      {score !== undefined && <span className="opacity-80">· {score.toFixed(0)}</span>}
    </span>
  );
}
