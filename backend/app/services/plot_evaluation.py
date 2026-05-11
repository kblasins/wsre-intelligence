"""Plot evaluation service — assembles all 9 sections for GET /api/workbench/plot/:plot_id."""
from __future__ import annotations

import math
import re
import random
from datetime import date, timedelta
from typing import Any

# ── Developer name cleaning (mirrors market.py) ───────────────────────────────
_DATASET_TITLE_PREFIXES = (
    "Ceny ofertowe mieszkań i domów dewelopera ",
    "Ceny ofertowe mieszkań dewelopera ",
    "Ceny ofertowe domów dewelopera ",
    "Ceny ofertowe lokali dewelopera ",
)
_DATASET_TITLE_SUFFIX_RE = re.compile(
    r"(\s*-\s*inwestycja\b.*$"
    r"|\s+w\s+\d{4}\s+(i\s+\d{4}\s+)?r\.?\s*$"
    r"|\s+od\s+\d{4}.*$"
    r"|\s+\d{4}\s*r?\.\s*$"
    r"|\s*\.\s*$)",
    re.IGNORECASE,
)

def _clean_dev_name(raw: str) -> str:
    name = raw.strip()
    for prefix in _DATASET_TITLE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return _DATASET_TITLE_SUFFIX_RE.sub("", name).strip() or raw

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── Fixed demo plot metadata ──────────────────────────────────────────────────
_DEMO_PLOTS: dict[str, dict[str, Any]] = {
    "demo-towarowa-28": {
        "plot_id":  "demo-towarowa-28",
        "address":  "ul. Towarowa 28, 01-103 Warszawa",
        "district": "wola",
        "area_m2":  1247,
        "kw_number": "WA1M/00521884/3",
        "summary":  "Residential MW (MPZP enacted) · 1,247 m² · Wola",
    }
}

_WARSAW_DZIELNICE_SQL = (
    "'śródmieście','wola','mokotów','ochota','żoliborz','bielany',"
    "'białołęka','targówek','praga-północ','praga-południe',"
    "'rembertów','wesoła','wawer','ursynów','wilanów','włochy','ursus','bemowo'"
)


async def build_plot_evaluation(plot_id: str, session: AsyncSession) -> dict[str, Any] | None:
    meta = _DEMO_PLOTS.get(plot_id)
    if meta is None:
        return None

    district = meta["district"]
    area_m2 = meta["area_m2"]

    (
        sec_a,
        sec_b,
        sec_c,
        sec_d,
        sec_e,
        sec_f,
        sec_g,
        sec_h,
    ) = await _gather_sections(plot_id, district, area_m2, session)

    sec_i = _compute_underwriting(area_m2, sec_a, sec_c)

    return {
        "plot": meta,
        "section_a_zoning":              sec_a,
        "section_b_land_comps":          sec_b,
        "section_c_exit_pricing":        sec_c,
        "section_d_competing_supply":    sec_d,
        "section_e_demographics":        sec_e,
        "section_f_infrastructure":      sec_f,
        "section_g_regulatory":          sec_g,
        "section_h_recent_intelligence": sec_h,
        "section_i_underwriting_snapshot": sec_i,
    }


# ── Section builders ──────────────────────────────────────────────────────────

async def _gather_sections(
    plot_id: str,
    district: str,
    area_m2: int,
    session: AsyncSession,
) -> tuple[Any, ...]:
    # Run all DB queries sequentially (simple; parallelise if latency matters)
    sec_a = await _section_a(plot_id, session)
    sec_b = await _section_b(plot_id, session)
    sec_c = await _section_c(district, session)
    sec_d = await _section_d(district, session)
    sec_e = await _section_e(plot_id, session)
    sec_f = await _section_f(plot_id, session)
    sec_g = await _section_g(plot_id, session)
    sec_h = await _section_h(district, session)
    return sec_a, sec_b, sec_c, sec_d, sec_e, sec_f, sec_g, sec_h


async def _section_a(plot_id: str, session: AsyncSession) -> dict[str, Any]:
    row = (await session.execute(
        text("SELECT * FROM plot_zoning_seed WHERE plot_id = :pid"),
        {"pid": plot_id},
    )).mappings().one_or_none()

    if row is None:
        return {"status": "no_data", "source": "plot_zoning_seed"}

    return {
        "status": "mpzp_enacted",
        "mpzp_name": row["mpzp_name"],
        "mpzp_enacted_date": row["mpzp_enacted_date"].isoformat() if row["mpzp_enacted_date"] else None,
        "mpzp_resolution_id": row["mpzp_resolution_id"],
        "function_code": row["function_code"],
        "parameters": {
            "max_far": float(row["max_far"]) if row["max_far"] is not None else None,
            "max_height_m": float(row["max_height_m"]) if row["max_height_m"] is not None else None,
            "max_site_coverage_pct": float(row["max_site_coverage_pct"]) if row["max_site_coverage_pct"] is not None else None,
            "min_greenery_pct": float(row["min_greenery_pct"]) if row["min_greenery_pct"] is not None else None,
            "min_parking_ratio": float(row["min_parking_ratio"]) if row["min_parking_ratio"] is not None else None,
            "front_setback_m": float(row["front_setback_m"]) if row["front_setback_m"] is not None else None,
        },
        "notes": row["notes"],
        "source": "plot_zoning_seed",
    }


async def _section_b(plot_id: str, session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(
        text("""
            SELECT transaction_date, distance_m, area_m2, pln_per_m2, market_type, source
            FROM plot_land_comps_seed
            WHERE plot_id = :pid
            ORDER BY transaction_date DESC
        """),
        {"pid": plot_id},
    )).mappings().all()

    if not rows:
        return {"median_pln_m2": None, "comparable_tx_count": 0, "total_m2_traded": 0,
                "scatter_data": [], "top_comps": []}

    prices = sorted([float(r["pln_per_m2"]) for r in rows])
    n = len(prices)
    median = (prices[n // 2] + prices[(n - 1) // 2]) / 2
    total_m2 = sum(float(r["area_m2"]) for r in rows)

    scatter = [
        {
            "date": r["transaction_date"].isoformat(),
            "pln_per_m2": float(r["pln_per_m2"]),
            "area_m2": float(r["area_m2"]),
        }
        for r in rows
    ]

    top_comps = [
        {
            "date": r["transaction_date"].isoformat(),
            "distance_m": r["distance_m"],
            "area_m2": float(r["area_m2"]),
            "pln_per_m2": float(r["pln_per_m2"]),
            "market_type": r["market_type"],
            "source": r["source"],
        }
        for r in rows[:8]
    ]

    return {
        "median_pln_m2": round(median),
        "comparable_tx_count": n,
        "total_m2_traded": round(total_m2),
        "scatter_data": scatter,
        "top_comps": top_comps,
        "source": "plot_land_comps_seed",
    }


async def _section_c(district: str, session: AsyncSession) -> dict[str, Any]:
    # Current median from live Jawność data
    row_now = (await session.execute(
        text(f"""
            SELECT
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price)) AS median_now,
                COUNT(*) AS n_units
            FROM primary_pricing
            WHERE district = :dist
              AND LOWER(TRIM(status)) IN ('active', 'wolne', 'w', 'free', 'available', 'a')
              AND m2_price > 1000
              AND m2_price < 50000
        """),
        {"dist": district},
    )).mappings().one_or_none()

    # 30-day change: median of units that had a price update in last 30 days,
    # comparing their latest vs previous price. Only report when sample >= 5.
    row_30d = (await session.execute(
        text("""
            SELECT
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY (price_history -> -1 ->> 'm2_price')::numeric
                      - (price_history -> -2 ->> 'm2_price')::numeric
                ) / NULLIF(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY (price_history -> -2 ->> 'm2_price')::numeric
                ), 0) * 100) AS pct_change,
                COUNT(*) AS n_changed
            FROM primary_pricing
            WHERE district = :dist
              AND jsonb_array_length(price_history) >= 2
              AND (price_history -> -1 ->> 'm2_price')::numeric > 1000
              AND (price_history -> -1 ->> 'm2_price')::numeric < 50000
              AND (price_history -> -2 ->> 'm2_price')::numeric > 1000
              AND (price_history -> -1 ->> 'date')::date >= CURRENT_DATE - 30
              AND (price_history -> -1 ->> 'm2_price')::numeric
                IS DISTINCT FROM (price_history -> -2 ->> 'm2_price')::numeric
        """),
        {"dist": district},
    )).mappings().one_or_none()

    primary_pln = float(row_now["median_now"]) if row_now and row_now["median_now"] else None
    n_units = int(row_now["n_units"]) if row_now else 0

    change_30d_pct = None
    if row_30d and row_30d["n_changed"] and int(row_30d["n_changed"]) >= 5 and row_30d["pct_change"] is not None:
        raw_pct = float(row_30d["pct_change"])
        # Clamp to ±10% to exclude parser artifacts
        if abs(raw_pct) <= 10:
            change_30d_pct = round(raw_pct, 2)

    # Projected exits at 24 months
    conservative = round(primary_pln * 1.03) if primary_pln else None
    central = round(primary_pln * 1.06) if primary_pln else None
    optimistic = round(primary_pln * 1.09) if primary_pln else None

    return {
        "primary_market": {
            "median_pln_m2": int(primary_pln) if primary_pln else None,
            "change_30d_pct": change_30d_pct,
            "n_units": n_units,
            "source": "Jawność cen mieszkań",
        },
        "secondary_market": {
            "median_pln_m2": 19420,
            "change_12m_pct": 9.1,
            "source": "RCN / GUS BDL (seeded)",
        },
        "projected_exit_24m": {
            "growth_rate_pct": 3.0,
            "conservative": conservative,
            "central": central,
            "optimistic": optimistic,
        },
    }


async def _section_d(district: str, session: AsyncSession) -> dict[str, Any]:
    # Pipeline stats
    row_stats = (await session.execute(
        text("""
            SELECT
                COUNT(*) AS pipeline_units,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m2_price)) AS avg_pln_m2
            FROM primary_pricing
            WHERE district = :dist
              AND LOWER(TRIM(status)) IN ('active', 'wolne', 'w', 'free', 'available', 'a')
              AND m2_price > 1000
              AND m2_price < 50000
        """),
        {"dist": district},
    )).mappings().one_or_none()

    pipeline_units = int(row_stats["pipeline_units"]) if row_stats else 0
    avg_pln_m2 = int(row_stats["avg_pln_m2"]) if row_stats and row_stats["avg_pln_m2"] else None

    # Top projects by unit count
    proj_rows = (await session.execute(
        text("""
            SELECT
                COALESCE(df.firm_name, jd.developer_name) AS developer_name,
                pp.investment_name,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pp.m2_price)) AS pln_m2,
                COUNT(*) AS units
            FROM primary_pricing pp
            JOIN jawnosc_developers jd ON jd.id = pp.developer_id
            LEFT JOIN developer_firms df ON df.id = COALESCE(pp.firm_id, jd.firm_id)
            WHERE pp.district = :dist
              AND LOWER(TRIM(pp.status)) IN ('active', 'wolne', 'w', 'free', 'available', 'a')
              AND pp.m2_price > 1000
              AND pp.m2_price < 50000
              AND pp.investment_name IS NOT NULL
            GROUP BY COALESCE(df.firm_name, jd.developer_name), pp.investment_name
            ORDER BY units DESC
            LIMIT 8
        """),
        {"dist": district},
    )).mappings().all()

    # Deterministic fake values keyed by investment name (stable across calls)
    completions = ["Q2 2027", "Q3 2027", "Q4 2027", "Q1 2028", "Q2 2028", "Q3 2028", "Q4 2026", "Q1 2027"]
    projects = []
    for i, r in enumerate(proj_rows):
        units = int(r["units"])
        pln = int(r["pln_m2"]) if r["pln_m2"] else avg_pln_m2 or 0
        rng = random.Random(hash(r["investment_name"] or "") & 0xFFFFFFFF)
        dist_m = rng.randint(200, 2000)
        sold = int(units * rng.uniform(0.2, 0.6))
        velocity = round(rng.uniform(4.0, 11.0), 1)
        raw_dev = r["developer_name"] or ""
        dev_display = _clean_dev_name(raw_dev)
        inv_raw = (r["investment_name"] or "").strip()
        # If investment name is the same SPV as the developer title, use cleaned dev name
        inv_display = inv_raw if inv_raw.lower() != raw_dev.lower() else dev_display
        projects.append({
            "developer_name": dev_display,
            "investment_name": inv_display,
            "distance_m": dist_m,
            "units": units,
            "completion_target": completions[i % len(completions)],
            "pln_m2": pln,
            "units_sold_to_date": sold,
            "monthly_absorption": velocity,
        })

    return {
        "pipeline_units": pipeline_units,
        "delivering_24mo_units": round(pipeline_units * 0.6),
        "avg_pln_m2": avg_pln_m2,
        "top_projects": projects,
        "source": "Jawność cen mieszkań",
    }


async def _section_e(plot_id: str, session: AsyncSession) -> dict[str, Any]:
    row = (await session.execute(
        text("SELECT * FROM plot_demographics_seed WHERE plot_id = :pid"),
        {"pid": plot_id},
    )).mappings().one_or_none()

    if row is None:
        return {"source": "plot_demographics_seed", "status": "no_data"}

    return {
        "district": row["district"],
        "population_current": row["population_current"],
        "population_5y_trajectory_pct": float(row["population_5y_trajectory_pct"]) if row["population_5y_trajectory_pct"] is not None else None,
        "age_25_44_share_pct": float(row["age_25_44_share_pct"]) if row["age_25_44_share_pct"] is not None else None,
        "age_25_44_vs_warsaw_avg_pct": float(row["age_25_44_vs_warsaw_avg_pct"]) if row["age_25_44_vs_warsaw_avg_pct"] is not None else None,
        "avg_monthly_earnings_pln": row["avg_monthly_earnings_pln"],
        "earnings_3y_trajectory_pct": float(row["earnings_3y_trajectory_pct"]) if row["earnings_3y_trajectory_pct"] is not None else None,
        "dwellings_per_1000": row["dwellings_per_1000"],
        "supply_status": row["supply_status"],
        "source": "GUS BDL / plot_demographics_seed",
    }


async def _section_f(plot_id: str, session: AsyncSession) -> dict[str, Any]:
    row = (await session.execute(
        text("SELECT * FROM plot_infrastructure_seed WHERE plot_id = :pid"),
        {"pid": plot_id},
    )).mappings().one_or_none()

    if row is None:
        return {"source": "plot_infrastructure_seed", "status": "no_data"}

    return {
        "nearest_metro": row["nearest_metro"],
        "metro_distance_min": row["metro_distance_min"],
        "nearest_tram": row["nearest_tram"],
        "tram_distance_min": row["tram_distance_min"],
        "planned_transport": row["planned_transport"],
        "schools_1km_count": row["schools_1km_count"],
        "healthcare_2km_count": row["healthcare_2km_count"],
        "source": "plot_infrastructure_seed",
    }


async def _section_g(plot_id: str, session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(
        text("""
            SELECT event_date, title, source, link_url
            FROM plot_regulatory_seed
            WHERE plot_id = :pid
            ORDER BY event_date DESC
        """),
        {"pid": plot_id},
    )).mappings().all()

    return {
        "items": [
            {
                "event_date": r["event_date"].isoformat() if r["event_date"] else None,
                "title": r["title"],
                "source": r["source"],
                "link_url": r["link_url"],
            }
            for r in rows
        ],
        "source": "plot_regulatory_seed",
    }


async def _section_h(district: str, session: AsyncSession) -> dict[str, Any]:
    # Pull Wola price-change events from live price_history in last 30 days
    rows = (await session.execute(
        text(f"""
            SELECT
                COALESCE(df.firm_name, jd.developer_name) AS developer_name,
                pp.investment_name,
                (pp.price_history -> -1 ->> 'date')::date AS change_date,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY (pp.price_history -> -2 ->> 'm2_price')::numeric
                )) AS prev_m2,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                    ORDER BY (pp.price_history -> -1 ->> 'm2_price')::numeric
                )) AS curr_m2,
                COUNT(*) AS unit_count
            FROM primary_pricing pp
            JOIN jawnosc_developers jd ON jd.id = pp.developer_id
            LEFT JOIN developer_firms df ON df.id = COALESCE(pp.firm_id, jd.firm_id)
            WHERE pp.district = :dist
              AND jsonb_array_length(pp.price_history) >= 2
              AND (pp.price_history -> -1 ->> 'm2_price')::numeric
                IS DISTINCT FROM (pp.price_history -> -2 ->> 'm2_price')::numeric
              AND (pp.price_history -> -1 ->> 'm2_price')::numeric > 1000
              AND (pp.price_history -> -2 ->> 'm2_price')::numeric > 1000
              AND (pp.price_history -> -1 ->> 'date')::date >= CURRENT_DATE - 30
            GROUP BY
                COALESCE(df.firm_name, jd.developer_name), pp.investment_name,
                (pp.price_history -> -1 ->> 'date')::date
            ORDER BY change_date DESC
            LIMIT 10
        """),
        {"dist": district},
    )).mappings().all()

    items = []
    for r in rows:
        prev = float(r["prev_m2"]) if r["prev_m2"] else None
        curr = float(r["curr_m2"]) if r["curr_m2"] else None
        if not prev or not curr or prev == 0:
            continue
        dpct = round((curr - prev) / prev * 100, 2)
        if abs(dpct) > 10 or abs(dpct) < 0.1 or abs(curr - prev) < 50:
            continue
        dir_ = "up" if dpct > 0 else "down"
        dev = r["developer_name"] or ""
        inv = r["investment_name"] or dev
        headline = f"{dev} adjusts {inv} pricing {'+' if dir_ == 'up' else ''}{dpct}% — {int(curr):,} PLN/m² ({r['unit_count']} units)"
        items.append({
            "timestamp": r["change_date"].isoformat() if r["change_date"] else None,
            "type": "pricing",
            "headline": headline,
            "source": "Jawność cen mieszkań",
            "confidence": 5,
            "dpct": dpct,
            "prev_m2": int(prev),
            "curr_m2": int(curr),
            "unit_count": int(r["unit_count"]),
        })

    return {
        "items": items,
        "source": "Jawność cen mieszkań / primary_pricing",
    }


# ── Section I — pure computation ──────────────────────────────────────────────

def _compute_underwriting(
    area_m2: int,
    sec_a: dict[str, Any],
    sec_c: dict[str, Any],
    *,
    build_cost_pln_m2_pum: float = 5500.0,
    target_irr_pct: float = 18.0,
    financing_ltv_pct: float = 65.0,
    financing_rate_premium_bps: float = 250.0,
    sales_velocity_units_per_month: float = 6.0,
    build_duration_months: float = 24.0,
) -> dict[str, Any]:
    max_far = sec_a.get("parameters", {}).get("max_far") or 0.0
    central_exit = (sec_c.get("projected_exit_24m") or {}).get("central") or 0.0

    pum = area_m2 * max_far

    gdv = pum * central_exit
    build_cost = pum * build_cost_pln_m2_pum
    soft_cost = build_cost * 0.15
    # Base rate assumed ~5.85% (WIBOR 3.35% + 2.5%), using rate_premium as spread over base
    base_rate = 0.0585
    financing_rate = base_rate + (financing_rate_premium_bps / 10000)
    debt = (build_cost + soft_cost) * (financing_ltv_pct / 100)
    financing_cost = debt * financing_rate * (build_duration_months / 12)
    total_cost = build_cost + soft_cost + financing_cost

    # Target profit: GDV × (1 - 1/(1+IRR)^(duration/12))
    irr_fraction = target_irr_pct / 100
    exponent = build_duration_months / 12
    target_profit = gdv * (1 - 1 / math.pow(1 + irr_fraction, exponent))

    residual_total = gdv - total_cost - target_profit
    residual_per_m2 = residual_total / area_m2 if area_m2 else 0

    def sensitivity(price_delta: float, cost_delta: float) -> int:
        g = pum * central_exit * (1 + price_delta)
        bc = build_cost * (1 + cost_delta)
        sc = bc * 0.15
        d = (bc + sc) * (financing_ltv_pct / 100)
        fc = d * financing_rate * (build_duration_months / 12)
        tc = bc + sc + fc
        tp = g * (1 - 1 / math.pow(1 + irr_fraction, exponent))
        r = g - tc - tp
        return max(0, round(r / area_m2))

    return {
        "inputs": {
            "build_cost_pln_m2_pum": build_cost_pln_m2_pum,
            "target_irr_pct": target_irr_pct,
            "financing_ltv_pct": financing_ltv_pct,
            "financing_rate_premium_bps": financing_rate_premium_bps,
            "sales_velocity_units_per_month": sales_velocity_units_per_month,
            "build_duration_months": build_duration_months,
        },
        "derived": {
            "pum_m2": round(pum),
            "central_exit_price_pln_m2": central_exit,
        },
        "outputs": {
            "estimated_gdv_pln": round(gdv),
            "estimated_total_cost_pln": round(total_cost),
            "residual_land_value_pln_m2": round(residual_per_m2),
            "residual_land_value_total_pln": round(residual_total),
        },
        "sensitivity_matrix": {
            "hp_lc": sensitivity(+0.05, -0.10),
            "hp_hc": sensitivity(+0.05, +0.10),
            "lp_lc": sensitivity(-0.05, -0.10),
            "lp_hc": sensitivity(-0.05, +0.10),
        },
    }
