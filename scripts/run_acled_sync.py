"""
One-shot script to run the ACLED sync manually.

Usage:
    python scripts/run_acled_sync.py              # incremental
    python scripts/run_acled_sync.py --full       # resync from 2010
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from app.core.database import AsyncSessionLocal
from app.services.acled_sync import run_acled_sync


async def main(full_resync: bool) -> None:
    async with AsyncSessionLocal() as db:
        summary = await run_acled_sync(db, full_resync=full_resync)

    print("\n=== ACLED Sync Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Full resync from 2010")
    args = parser.parse_args()
    asyncio.run(main(full_resync=args.full))
