"""
04_silver_to_gold.py — Silver → Gold (star schema + analytics)

The Gold layer is what serves Power BI. It contains:

DIMENSIONS:
  - dim_station: 1 row per weather station
  - dim_date:    1 row per date (with calendar attributes + ENSO flags)

FACTS:
  - fact_observations_30min:  raw 30-min granularity (for drill-down)
  - fact_daily_summary:       aggregated daily (the main analytical table)
  - fact_monthly_summary:     aggregated monthly (fast comparisons)
  - fact_extreme_events:      detected events (heat waves, gusts, storms)

Output: data/gold/climate.duckdb (single file, Power BI-ready)
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.stations import STATIONS


def create_dim_station(con: duckdb.DuckDBPyConnection) -> None:
    """Build dim_station from STATIONS config."""
    con.execute("DROP TABLE IF EXISTS dim_station;")
    con.execute("""
        CREATE TABLE dim_station (
            station_id      VARCHAR PRIMARY KEY,
            station_name    VARCHAR,
            zone            VARCHAR,
            latitude        DOUBLE,
            longitude       DOUBLE,
            altitude_m      INTEGER
        );
    """)
    rows = [
        (s.station_id, s.name, s.zone, s.latitude, s.longitude, s.altitude_m)
        for s in STATIONS
    ]
    con.executemany("INSERT INTO dim_station VALUES (?, ?, ?, ?, ?, ?);", rows)
    n = con.execute("SELECT COUNT(*) FROM dim_station").fetchone()[0]
    print(f"  ✓ dim_station: {n} rows")


def create_dim_date(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build dim_date covering 2023-2024.
    Includes ENSO event flags so PBI can filter "El Niño period vs normal".
    """
    con.execute("DROP TABLE IF EXISTS dim_date;")
    con.execute("""
        CREATE TABLE dim_date AS
        WITH date_range AS (
            SELECT unnest(generate_series(
                DATE '2023-01-01',
                DATE '2024-12-31',
                INTERVAL 1 DAY
            )) AS date_local
        )
        SELECT
            date_local,
            CAST(strftime(date_local, '%Y%m%d') AS INTEGER) AS date_id,
            year(date_local) AS year,
            quarter(date_local) AS quarter,
            month(date_local) AS month,
            monthname(date_local) AS month_name,
            day(date_local) AS day_of_month,
            dayofweek(date_local) AS day_of_week,
            dayname(date_local) AS day_name,
            CASE WHEN dayofweek(date_local) IN (0, 6) THEN 1 ELSE 0 END AS is_weekend,
            -- Agricultural seasons (southern hemisphere)
            CASE
                WHEN month(date_local) IN (12, 1, 2) THEN 'Verano'
                WHEN month(date_local) IN (3, 4, 5)  THEN 'Otoño'
                WHEN month(date_local) IN (6, 7, 8)  THEN 'Invierno'
                ELSE 'Primavera'
            END AS season,
            -- ENSO event flags
            CASE
                WHEN date_local BETWEEN DATE '2023-03-01' AND DATE '2023-05-15'
                    THEN 'El Niño Costero (Yaku)'
                WHEN date_local BETWEEN DATE '2023-06-01' AND DATE '2024-05-31'
                    THEN 'El Niño Global'
                ELSE 'Normal'
            END AS enso_period,
            CASE
                WHEN date_local BETWEEN DATE '2023-03-01' AND DATE '2024-05-31'
                    THEN 1 ELSE 0
            END AS is_el_nino
        FROM date_range;
    """)
    n = con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
    print(f"  ✓ dim_date: {n} rows (with ENSO flags)")


def create_fact_observations(
    con: duckdb.DuckDBPyConnection,
    silver_path: str,
) -> None:
    """Load raw 30-min observations into Gold (typed, ready to query)."""
    con.execute("DROP TABLE IF EXISTS fact_observations_30min;")
    con.execute(f"""
        CREATE TABLE fact_observations_30min AS
        SELECT
            station_id,
            observation_ts,
            CAST(strftime(observation_ts, '%Y%m%d') AS INTEGER) AS date_id,
            CAST(observation_ts AS DATE) AS date_local,
            hour,
            -- Core measurements
            temp_out_c,
            humidity_pct,
            dew_point_c,
            wind_speed_kmh,
            wind_gust_kmh,
            wind_dir,
            pressure_hpa,
            precip_mm,
            solar_wm2,
            uv_index,
            etp_mm,
            heat_index_c,
            thsw_index_c,
            -- Quality
            quality_flag
        FROM read_parquet('{silver_path}/**/*.parquet', hive_partitioning=true);
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_observations_30min").fetchone()[0]
    print(f"  ✓ fact_observations_30min: {n:,} rows")


def create_fact_daily(con: duckdb.DuckDBPyConnection) -> None:
    """
    Daily summary fact table — the main analytical workhorse.
    One row per station × date with all key climate KPIs aggregated.
    """
    con.execute("DROP TABLE IF EXISTS fact_daily_summary;")
    con.execute("""
        CREATE TABLE fact_daily_summary AS
        SELECT
            station_id,
            date_local,
            CAST(strftime(date_local, '%Y%m%d') AS INTEGER) AS date_id,

            -- Temperature
            ROUND(AVG(temp_out_c), 2)        AS temp_avg_c,
            ROUND(MAX(temp_out_c), 2)        AS temp_max_c,
            ROUND(MIN(temp_out_c), 2)        AS temp_min_c,
            ROUND(MAX(temp_out_c) - MIN(temp_out_c), 2) AS temp_amplitude_c,

            -- Humidity
            ROUND(AVG(humidity_pct), 1)      AS humidity_avg_pct,
            ROUND(MIN(humidity_pct), 0)      AS humidity_min_pct,
            ROUND(MAX(humidity_pct), 0)      AS humidity_max_pct,

            -- Wind
            ROUND(AVG(wind_speed_kmh), 1)    AS wind_avg_kmh,
            ROUND(MAX(wind_gust_kmh), 1)     AS wind_gust_max_kmh,
            mode(wind_dir)                   AS wind_dominant_dir,

            -- Precipitation (cumulative for the day)
            ROUND(SUM(precip_mm), 2)         AS precip_total_mm,
            COUNT(CASE WHEN precip_mm > 0 THEN 1 END) AS rainy_intervals,

            -- Solar / UV
            ROUND(MAX(solar_wm2), 0)         AS solar_max_wm2,
            ROUND(SUM(solar_wm2) / 48, 0)    AS solar_daily_avg_wm2,
            ROUND(MAX(uv_index), 1)          AS uv_max,

            -- ETP (KEY agricultural metric: water demand)
            ROUND(SUM(etp_mm), 2)            AS etp_total_mm,

            -- Water balance (precipitation - ETP, negative = deficit)
            ROUND(SUM(precip_mm) - SUM(etp_mm), 2) AS water_balance_mm,

            -- Heat metrics
            ROUND(MAX(heat_index_c), 1)      AS heat_index_max_c,
            ROUND(MAX(thsw_index_c), 1)      AS thsw_max_c,

            -- Pressure
            ROUND(AVG(pressure_hpa), 1)      AS pressure_avg_hpa,

            -- Quality
            COUNT(*)                         AS n_observations,
            SUM(CASE WHEN quality_flag IS NOT NULL THEN 1 ELSE 0 END) AS n_flagged,

            -- Boolean flags for fast filtering in PBI
            CASE WHEN MAX(temp_out_c) > 32 THEN 1 ELSE 0 END         AS is_hot_day,
            CASE WHEN SUM(precip_mm) > 2 THEN 1 ELSE 0 END           AS is_rainy_day,
            CASE WHEN MAX(wind_gust_kmh) > 35 THEN 1 ELSE 0 END      AS is_windy_day,
            CASE WHEN MAX(uv_index) > 12 THEN 1 ELSE 0 END           AS is_uv_extreme

        FROM fact_observations_30min
        GROUP BY station_id, date_local;
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_daily_summary").fetchone()[0]
    print(f"  ✓ fact_daily_summary: {n:,} rows")


def create_fact_monthly(con: duckdb.DuckDBPyConnection) -> None:
    """Monthly aggregates — speeds up year-over-year comparisons in PBI."""
    con.execute("DROP TABLE IF EXISTS fact_monthly_summary;")
    con.execute("""
        CREATE TABLE fact_monthly_summary AS
        SELECT
            station_id,
            year(date_local)                     AS year,
            month(date_local)                    AS month,
            DATE_TRUNC('month', date_local)      AS month_start,

            ROUND(AVG(temp_avg_c), 2)            AS temp_avg_c,
            ROUND(MAX(temp_max_c), 2)            AS temp_max_c,
            ROUND(MIN(temp_min_c), 2)            AS temp_min_c,
            ROUND(AVG(humidity_avg_pct), 1)      AS humidity_avg_pct,
            ROUND(SUM(precip_total_mm), 1)       AS precip_total_mm,
            ROUND(SUM(etp_total_mm), 1)          AS etp_total_mm,
            ROUND(SUM(water_balance_mm), 1)      AS water_balance_mm,

            SUM(is_hot_day)                      AS n_hot_days,
            SUM(is_rainy_day)                    AS n_rainy_days,
            SUM(is_windy_day)                    AS n_windy_days,
            SUM(is_uv_extreme)                   AS n_uv_extreme_days,

            COUNT(*)                             AS n_days

        FROM fact_daily_summary
        GROUP BY station_id, year(date_local), month(date_local),
                 DATE_TRUNC('month', date_local);
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_monthly_summary").fetchone()[0]
    print(f"  ✓ fact_monthly_summary: {n:,} rows")


def create_fact_extreme_events(con: duckdb.DuckDBPyConnection) -> None:
    """
    Detected extreme events — for the alerts dashboard page.
    Each row is one event (heat wave, storm, etc.) with metrics.
    """
    con.execute("DROP TABLE IF EXISTS fact_extreme_events;")
    con.execute("""
        CREATE TABLE fact_extreme_events AS
        WITH events AS (
            -- Heat events: max temp > 33°C
            SELECT
                station_id,
                date_local,
                'Calor extremo'   AS event_type,
                temp_max_c        AS magnitude,
                'temp_max_c'      AS metric,
                'Temperatura máxima superó 33°C, riesgo de estrés térmico en cultivos'
                                  AS description
            FROM fact_daily_summary
            WHERE temp_max_c > 33

            UNION ALL

            -- Heavy rain: > 20mm in a day
            SELECT
                station_id,
                date_local,
                'Lluvia intensa',
                precip_total_mm,
                'precip_total_mm',
                'Precipitación >20mm/día, riesgo de inundación / pérdida de cosecha'
            FROM fact_daily_summary
            WHERE precip_total_mm > 20

            UNION ALL

            -- Strong wind: gusts > 35 km/h (typical "viento fuerte" agro alert)
            SELECT
                station_id,
                date_local,
                'Vientos fuertes',
                wind_gust_max_kmh,
                'wind_gust_max_kmh',
                'Ráfagas >35 km/h, riesgo mecánico en plantaciones'
            FROM fact_daily_summary
            WHERE wind_gust_max_kmh > 35

            UNION ALL

            -- Extreme UV: index > 12
            SELECT
                station_id,
                date_local,
                'UV extremo',
                uv_max,
                'uv_max',
                'Índice UV >12, riesgo para trabajadores en campo'
            FROM fact_daily_summary
            WHERE uv_max > 12

            UNION ALL

            -- Severe water deficit: ETP - precipitation > 7mm/day sustained
            SELECT
                station_id,
                date_local,
                'Déficit hídrico severo',
                ABS(water_balance_mm),
                'water_balance_mm',
                'Demanda de agua excede 7mm sin reposición pluvial'
            FROM fact_daily_summary
            WHERE water_balance_mm < -7
        )
        SELECT
            row_number() OVER (ORDER BY date_local, station_id, event_type) AS event_id,
            *
        FROM events;
    """)
    n = con.execute("SELECT COUNT(*) FROM fact_extreme_events").fetchone()[0]
    print(f"  ✓ fact_extreme_events: {n:,} rows")


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    """
    Convenience views for Power BI — pre-joined and ready to use.
    """
    # All daily metrics joined with dim_station and dim_date
    con.execute("""
        CREATE OR REPLACE VIEW vw_daily_climate AS
        SELECT
            f.*,
            s.station_name,
            s.zone,
            s.latitude,
            s.longitude,
            s.altitude_m,
            d.year,
            d.quarter,
            d.month,
            d.month_name,
            d.season,
            d.enso_period,
            d.is_el_nino
        FROM fact_daily_summary f
        LEFT JOIN dim_station s ON f.station_id = s.station_id
        LEFT JOIN dim_date d    ON f.date_local = d.date_local;
    """)
    print("  ✓ vw_daily_climate (joined view)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--silver", default="data/silver/observations",
                        help="Silver dir")
    parser.add_argument("--out", default="data/gold/climate.duckdb",
                        help="Output DuckDB file")
    args = parser.parse_args()

    silver_path = str(Path(args.silver).resolve())
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()  # rebuild from scratch

    print(f"GOLD BUILD — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Silver:      {silver_path}")
    print(f"Destination: {out_path}\n")

    con = duckdb.connect(str(out_path))
    con.execute("PRAGMA threads = 4;")
    con.execute("PRAGMA memory_limit = '2GB';")

    print("Building dimensions...")
    create_dim_station(con)
    create_dim_date(con)

    print("\nBuilding facts...")
    create_fact_observations(con, silver_path)
    create_fact_daily(con)
    create_fact_monthly(con)
    create_fact_extreme_events(con)

    print("\nBuilding views...")
    create_views(con)

    # Final summary
    print("\n" + "=" * 60)
    print("Gold layer summary:")
    tables = con.execute(
        "SELECT table_name, estimated_size FROM duckdb_tables() "
        "WHERE schema_name = 'main' ORDER BY table_name"
    ).fetchall()
    for t, sz in tables:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<35} {n:>10,} rows")

    con.close()

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"\n  DuckDB file: {size_mb:.1f} MB")
    print(f"  → Connect from Power BI: {out_path}")


if __name__ == "__main__":
    main()
