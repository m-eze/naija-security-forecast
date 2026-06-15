"""
Run the risk score engine manually and print a report.

Usage:
    python scripts/run_scorer.py                    # score all LGAs
    python scripts/run_scorer.py --report           # also print top-20 hotspots
    python scripts/run_scorer.py --state Lagos      # report for one state
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from app.core.database import AsyncSessionLocal
from app.services.scorer import calculate_all_scores


LEVEL_ICON = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "SEVERE": "🔴"}


async def run(state_filter: str | None, print_report: bool) -> None:
    async with AsyncSessionLocal() as db:
        summary = await calculate_all_scores(db)

        print("\n=== Risk Score Summary ===")
        for k, v in summary.items():
            if k != "distribution":
                print(f"  {k}: {v}")
        print("\n  Score distribution:")
        for level, count in summary["distribution"].items():
            icon = LEVEL_ICON[level]
            print(f"    {icon} {level:<10} {count} LGAs")

        if print_report or state_filter:
            from sqlalchemy import text
            where = "WHERE r.is_forecast = false AND r.score_date = CURRENT_DATE"
            params: dict = {}
            if state_filter:
                where += " AND l.state ILIKE :state"
                params["state"] = f"%{state_filter}%"

            sql = text(f"""
                SELECT
                    l.name, l.state, r.score, r.level,
                    r.incident_frequency_score  AS freq,
                    r.incident_trend_score      AS trend,
                    r.news_sentiment_score      AS news,
                    r.components->>'incident_count_90d'  AS incidents_90d,
                    r.components->>'trend_direction'     AS trend_dir,
                    r.components->>'news_articles_7d'    AS news_articles
                FROM risk_scores r
                JOIN lgas l ON l.id = r.lga_id
                {where}
                ORDER BY r.score DESC
                LIMIT 25
            """)
            result = await db.execute(sql, params)
            rows = result.fetchall()

            header = "State" if not state_filter else state_filter.title()
            print(f"\n{'─'*90}")
            print(f"  Top hotspots — {header}")
            print(f"{'─'*90}")
            print(f"  {'LGA':<22} {'State':<14} {'Score':>6} {'Level':<10} "
                  f"{'Freq':>6} {'Trend':>6} {'News':>6}  {'Incidents':>9}  {'Direction':<12}")
            print(f"  {'─'*22} {'─'*14} {'─'*6} {'─'*10} "
                  f"{'─'*6} {'─'*6} {'─'*6}  {'─'*9}  {'─'*12}")
            for row in rows:
                icon = LEVEL_ICON.get(row.level, "⚪")
                print(
                    f"  {row.name:<22} {row.state:<14} {row.score:>6.1f} "
                    f"{icon} {row.level:<8} "
                    f"{row.freq:>6.1f} {row.trend:>6.1f} {row.news:>6.1f}  "
                    f"{(row.incidents_90d or '0'):>9}  {(row.trend_dir or 'unknown'):<12}"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="Print top-25 hotspots")
    parser.add_argument("--state", help="Filter report by state")
    args = parser.parse_args()

    asyncio.run(run(state_filter=args.state, print_report=args.report))
