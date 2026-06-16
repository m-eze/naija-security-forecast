import type { RiskLevel } from "@/types";

export const RISK_COLORS: Record<RiskLevel, string> = {
  LOW: "#22c55e",
  MODERATE: "#eab308",
  HIGH: "#f97316",
  SEVERE: "#ef4444",
};

export const RISK_BG: Record<RiskLevel, string> = {
  LOW: "bg-green-500",
  MODERATE: "bg-yellow-500",
  HIGH: "bg-orange-500",
  SEVERE: "bg-red-500",
};

export const RISK_TEXT: Record<RiskLevel, string> = {
  LOW: "text-green-600",
  MODERATE: "text-yellow-600",
  HIGH: "text-orange-600",
  SEVERE: "text-red-600",
};

export function levelFromScore(score: number): RiskLevel {
  if (score < 25) return "LOW";
  if (score < 50) return "MODERATE";
  if (score < 75) return "HIGH";
  return "SEVERE";
}

export function scoreColor(score: number | null): string {
  if (score === null) return "#94a3b8";
  return RISK_COLORS[levelFromScore(score)];
}
