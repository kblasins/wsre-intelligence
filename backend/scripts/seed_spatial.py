"""Seed spatial data — Tasks 3 and 4.

Task 3: Seed MODON Riyadh 1st Industrial City as default saved site for admin user.
Task 4: Seed 4 additional regulatory zones:
  - MODON 2nd Industrial City
  - MODON 3rd Industrial City
  - KAFD Special Economic Zone
  - Makkah / Madinah Non-Muslim Restricted Zones

Run: python scripts/seed_spatial.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from app.core.database import AsyncSessionFactory
from app.core.logging import configure_logging
from sqlalchemy import text

log = structlog.get_logger(__name__)


def _box_wkt(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> str:
    """MULTIPOLYGON WKT bounding box for insertion via ST_GeomFromText."""
    return (
        f"MULTIPOLYGON((("
        f"{lon_min} {lat_min}, {lon_max} {lat_min}, "
        f"{lon_max} {lat_max}, {lon_min} {lat_max}, "
        f"{lon_min} {lat_min}"
        f")))"
    )


# ── Regulatory zone definitions ────────────────────────────────────────────────

# Coordinates are approximate bounding boxes derived from public sources:
# MODON industrial cities: modon.gov.sa zone maps
# KAFD: kafd.com.sa site boundary
# Makkah/Madinah: Ministry of Islamic Affairs non-Muslim restriction perimeters

REGULATORY_ZONES = [
    {
        "zone_type": "modon_industrial",
        "name_en": "MODON Riyadh 2nd Industrial City",
        "name_ar": "مدينة الرياض الصناعية الثانية",
        # Southern Riyadh, Kharj Road / Ring Road 3 area
        "bbox": (46.7400, 24.5800, 46.8100, 24.6350),
        "source": "modon.gov.sa zone reference (approximate)",
        "source_citation": "المدينة الصناعية الثانية — موقع هيئة المدن الصناعية",
        "rules": {
            "permitted_uses": ["manufacturing", "logistics", "light_industry", "warehousing"],
            "min_plot_sqm": 2500,
            "max_height_m": 18,
            "setback_m": 5,
            "operator": "MODON",
        },
    },
    {
        "zone_type": "modon_industrial",
        "name_en": "MODON Riyadh 3rd Industrial City",
        "name_ar": "مدينة الرياض الصناعية الثالثة",
        # Northern Riyadh, Sudair direction near King Salman Road
        "bbox": (46.6200, 24.8400, 46.7200, 24.9200),
        "source": "modon.gov.sa zone reference (approximate)",
        "source_citation": "المدينة الصناعية الثالثة — موقع هيئة المدن الصناعية",
        "rules": {
            "permitted_uses": ["manufacturing", "logistics", "heavy_industry", "warehousing"],
            "min_plot_sqm": 5000,
            "max_height_m": 24,
            "setback_m": 8,
            "operator": "MODON",
        },
    },
    {
        "zone_type": "sez",
        "name_en": "KAFD Special Economic Zone",
        "name_ar": "منطقة مركز الملك عبدالله المالي الاقتصادية الخاصة",
        # King Fahd Road / King Salman Branch Road, northern Riyadh
        "bbox": (46.6350, 24.7620, 46.6720, 24.7960),
        "source": "KAFD.com.sa / Royal Decree M/23 (2023) SEZ designation",
        "source_citation": "King Abdullah Financial District designated as SEZ",
        "rules": {
            "zone_class": "SEZ",
            "tax_incentives": ["0% corporate tax 50yr", "100% foreign ownership", "no customs duty"],
            "permitted_uses": ["financial_services", "tech", "office", "retail", "hospitality"],
            "regulator": "KAFD Development Authority",
            "foreign_ownership": "100%",
            "note": "Non-residential real estate permitted with foreign ownership up to 49% via listed entities",
        },
    },
    {
        "zone_type": "restricted_non_muslim",
        "name_en": "Makkah Non-Muslim Restricted Zone",
        "name_ar": "منطقة مكة المكرمة المحظورة على غير المسلمين",
        # Makkah city perimeter restriction zone (approximate)
        "bbox": (39.7500, 21.3200, 39.9200, 21.5100),
        "source": "Royal Decree: non-Muslim entry restriction / CMA real estate investment rules",
        "source_citation": "non-Muslims are prohibited from entering the city of Makkah",
        "rules": {
            "restriction": "non_muslim_entry_prohibited",
            "real_estate_note": "Foreign non-Muslim investors may not hold direct title; REIT units permitted",
            "applicable_regulation": "CMA allows up to 49% foreign ownership in listed REITs holding Makkah assets",
        },
    },
    {
        "zone_type": "restricted_non_muslim",
        "name_en": "Madinah Non-Muslim Restricted Zone",
        "name_ar": "منطقة المدينة المنورة المحظورة على غير المسلمين",
        # Madinah city restriction zone (approximate)
        "bbox": (39.5400, 24.4000, 39.7400, 24.5500),
        "source": "Royal Decree: non-Muslim entry restriction / CMA real estate investment rules",
        "source_citation": "non-Muslims are prohibited from entering the city of Madinah",
        "rules": {
            "restriction": "non_muslim_entry_prohibited",
            "real_estate_note": "Same CMA 49% cap applies as Makkah for listed REITs",
        },
    },
]


async def seed_regulatory_zones(session) -> int:
    """Insert regulatory zones that don't already exist."""
    count = 0
    for zone in REGULATORY_ZONES:
        existing = await session.execute(
            text("SELECT id FROM regulatory_zones WHERE name_en = :n"),
            {"n": zone["name_en"]},
        )
        if existing.scalar():
            log.info("zone_already_exists", name=zone["name_en"])
            continue

        lon_min, lat_min, lon_max, lat_max = zone["bbox"]
        wkt = _box_wkt(lon_min, lat_min, lon_max, lat_max)

        import json
        await session.execute(
            text("""
                INSERT INTO regulatory_zones
                  (zone_type, name_en, name_ar, polygon, rules, source, source_citation, last_verified_at, created_at)
                VALUES
                  (:zone_type, :name_en, :name_ar,
                   ST_Multi(ST_GeomFromText(:wkt, 4326)),
                   :rules, :source, :source_citation, NOW(), NOW())
            """),
            {
                "zone_type": zone["zone_type"],
                "name_en": zone["name_en"],
                "name_ar": zone.get("name_ar"),
                "wkt": wkt,
                "rules": json.dumps(zone["rules"]),
                "source": zone["source"],
                "source_citation": zone.get("source_citation"),
            },
        )
        log.info("zone_inserted", name=zone["name_en"])
        count += 1
    return count


async def seed_modon1_saved_site(session, user_id: str) -> bool:
    """Seed MODON Riyadh 1st Industrial City as a saved site for the admin user."""
    existing = await session.execute(
        text("SELECT id FROM saved_sites WHERE name = 'MODON Riyadh 1st Industrial City'")
    )
    if existing.scalar():
        log.info("saved_site_already_exists")
        return False

    # Pull the polygon from the existing regulatory zone as the site geometry
    rz = await session.execute(
        text(
            "SELECT ST_AsText(polygon) FROM regulatory_zones "
            "WHERE name_en = 'MODON Riyadh 1st Industrial City' LIMIT 1"
        )
    )
    rz_row = rz.fetchone()

    if rz_row:
        # Use the regulatory zone's polygon, flattened to a general geometry
        geom_expr = "ST_GeomFromText(:wkt, 4326)"
        geom_val = rz_row[0]
    else:
        # Fallback: approximate bbox from known coordinates
        wkt = _box_wkt(46.7480, 24.6980, 46.7970, 24.7300)
        geom_expr = "ST_GeomFromText(:wkt, 4326)"
        geom_val = wkt

    await session.execute(
        text(f"""
            INSERT INTO saved_sites (user_id, name, description, geometry, asset_class, notes, created_at, updated_at)
            VALUES (:user_id, 'MODON Riyadh 1st Industrial City',
                    'MODON-administered industrial city SW of Riyadh. Priority tracking zone.',
                    {geom_expr}, 'industrial', 'Default seed site — bounding polygon is approximate.', NOW(), NOW())
        """),
        {"user_id": user_id, "wkt": geom_val},
    )
    log.info("saved_site_inserted", name="MODON Riyadh 1st Industrial City")
    return True


async def main() -> None:
    async with AsyncSessionFactory() as session:
        # Task 4: regulatory zones
        zone_count = await seed_regulatory_zones(session)

        # Task 3: saved site — use admin user
        user_row = await session.execute(
            text("SELECT id FROM users WHERE is_superuser = true LIMIT 1")
        )
        user_id = user_row.scalar()
        if not user_id:
            log.error("no_superuser_found")
            return

        site_inserted = await seed_modon1_saved_site(session, str(user_id))

        await session.commit()

    print(f"Regulatory zones inserted: {zone_count}")
    print(f"Saved site inserted: {site_inserted}")
    print("Done.")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
