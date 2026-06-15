"""
Seed the lgas table from Nigeria admin level-2 GeoJSON (GADM 4.1).

Source: https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_NGA_2.json
GADM is a freely available academic dataset of administrative boundaries.

Usage:
    # Auto-download GADM and seed
    python scripts/seed_lgas.py

    # Use a local GeoJSON file (GADM or any source with NAME_1/NAME_2 fields)
    python scripts/seed_lgas.py --input /path/to/nigeria_lgas.geojson

    # Dry run — parse only, no DB writes
    python scripts/seed_lgas.py --dry-run
"""
import argparse
import json
import logging
import re
import sys
import tempfile
from pathlib import Path

import httpx
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_NGA_2.json"

# After camelCase splitting, apply these final overrides
STATE_OVERRIDES = {
    "Federal Capital Territory": "FCT",
}


def split_camel(name: str) -> str:
    """'AbaNorth' → 'Aba North', 'LagosIsland' → 'Lagos Island'."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip()


def download_geojson(url: str, dest: Path) -> None:
    logger.info("Downloading Nigeria LGA boundaries from GADM ...")
    logger.info("  URL: %s", url)
    logger.info("  This may take a minute — file is ~30 MB")

    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:.0f}% ({downloaded // 1024 // 1024} MB)", end="", flush=True)
    print()
    logger.info("Download complete: %s (%.1f MB)", dest, dest.stat().st_size / 1024 / 1024)


def parse_features(geojson_path: Path) -> list[dict]:
    logger.info("Parsing GeoJSON ...")
    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    logger.info("Found %d features", len(features))
    return features


def normalise_state(raw: str) -> str:
    fixed = split_camel(raw.strip())
    return STATE_OVERRIDES.get(fixed, fixed)


def build_rows(features: list[dict]) -> list[dict]:
    rows = []
    skipped = 0

    for feat in features:
        props = feat.get("properties", {})
        geom = feat.get("geometry")

        name = split_camel((props.get("NAME_2") or "").strip())
        state = normalise_state(props.get("NAME_1") or "")
        lga_code = (props.get("GID_2") or "").strip() or None

        if not name or not state:
            logger.warning("Skipping feature with missing name/state: %s", props)
            skipped += 1
            continue

        if not geom:
            logger.warning("Skipping '%s, %s' — no geometry", name, state)
            skipped += 1
            continue

        # Serialise geometry back to JSON string for ST_GeomFromGeoJSON
        geom_json = json.dumps(geom)

        rows.append({
            "name": name,
            "state": state,
            "lga_code": lga_code,
            "geom_json": geom_json,
        })

    logger.info("Parsed %d valid rows, skipped %d", len(rows), skipped)
    return rows


UPSERT_SQL = """
INSERT INTO lgas (id, name, state, lga_code, geometry, centroid, created_at, updated_at)
VALUES %s
ON CONFLICT (lga_code) DO UPDATE SET
    name       = EXCLUDED.name,
    state      = EXCLUDED.state,
    geometry   = EXCLUDED.geometry,
    centroid   = EXCLUDED.centroid,
    updated_at = NOW()
"""

ROW_TEMPLATE = """(
    gen_random_uuid(),
    %s, %s, %s,
    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
    ST_Centroid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
    NOW(), NOW()
)"""


def seed_db(rows: list[dict], sync_url: str) -> None:
    # psycopg2 needs a standard postgresql:// URL (not +psycopg2 dialect prefix)
    db_url = sync_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    BATCH = 100
    total_upserted = 0

    try:
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            values = [
                (
                    r["name"],
                    r["state"],
                    r["lga_code"],
                    r["geom_json"],
                    r["geom_json"],  # used twice: geometry + centroid
                )
                for r in batch
            ]
            execute_values(cur, UPSERT_SQL, values, template=ROW_TEMPLATE, page_size=BATCH)
            total_upserted += len(batch)
            logger.info(
                "  Upserted %d / %d LGAs ...", total_upserted, len(rows)
            )

        conn.commit()
        logger.info("Done. %d LGAs upserted.", total_upserted)

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def verify_db(sync_url: str) -> None:
    db_url = sync_url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT state, COUNT(*) FROM lgas GROUP BY state ORDER BY state;")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print("\n=== LGA counts by state ===")
    total = 0
    for state, count in rows:
        print(f"  {state:<25} {count}")
        total += count
    print(f"  {'TOTAL':<25} {total}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Nigeria LGA boundaries")
    parser.add_argument("--input", "-i", help="Path to local GeoJSON file (skips download)")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    args = parser.parse_args()

    if args.input:
        geojson_path = Path(args.input)
        if not geojson_path.exists():
            logger.error("File not found: %s", geojson_path)
            sys.exit(1)
        tmp_dir = None
    else:
        tmp_dir = tempfile.mkdtemp(prefix="naija_lga_")
        geojson_path = Path(tmp_dir) / "gadm41_NGA_2.json"
        download_geojson(GADM_URL, geojson_path)

    try:
        features = parse_features(geojson_path)
        rows = build_rows(features)

        if args.dry_run:
            logger.info("Dry run — no DB writes. Sample rows:")
            for r in rows[:5]:
                print(f"  {r['name']}, {r['state']} ({r['lga_code']})")
            return

        logger.info("Seeding database ...")
        seed_db(rows, settings.SYNC_DATABASE_URL)
        verify_db(settings.SYNC_DATABASE_URL)

    finally:
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
