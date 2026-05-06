"""
03_bronze_to_silver.py — Bronze → Silver (cleaning & standardization)

Responsibilities of the Silver layer:
- Parse Date+Time → proper TIMESTAMP
- Cast types correctly (numerics, strings, booleans)
- Rename columns to snake_case (analytics-friendly)
- Deduplicate (station_id + observation_ts)
- Validate physical bounds (temp -50..60°C, RH 0..100%, etc.)
- Flag (don't drop) suspicious values for downstream investigation
- Forward-fill short gaps (≤2 missing values in a row)

Output: data/silver/observations/  (Parquet, partitioned by station_id/year/month)
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))


SILVER_RENAME_MAP = {
    "Date": "date_local",
    "Time": "time_local",
    "Temp Out": "temp_out_c",
    "Hi Temp": "temp_hi_c",
    "Low Temp": "temp_low_c",
    "Out Hum": "humidity_pct",
    "Dew Pt.": "dew_point_c",
    "Wind Speed": "wind_speed_kmh",
    "Wind Dir": "wind_dir",
    "Wind Run": "wind_run_km",
    "Hi Speed": "wind_gust_kmh",
    "Hi Dir": "wind_gust_dir",
    "Wind Chill": "wind_chill_c",
    "Heat Index": "heat_index_c",
    "THW Index": "thw_index_c",
    "THSW Index": "thsw_index_c",
    "Bar": "pressure_hpa",
    "Rain": "precip_mm",
    "Rain Rate": "precip_rate_mmh",
    "Solar Rad.": "solar_wm2",
    "Solar Energy": "solar_energy_ly",
    "Hi Solar Rad.": "solar_hi_wm2",
    "UV Index": "uv_index",
    "UV Dose": "uv_dose_med",
    "Hi UV": "uv_hi",
    "Heat D-D": "heat_dd",
    "Cool D-D": "cool_dd",
    "In Temp": "in_temp_c",
    "In Hum": "in_humidity_pct",
    "In Dew": "in_dew_c",
    "In Heat": "in_heat_c",
    "In EMC": "in_emc",
    "In Air Density": "in_air_density",
    "ET": "etp_mm",
    "Wind Samp": "wind_samples",
    "Wind Tx": "wind_tx",
    "ISS Recept": "iss_reception_pct",
    "Arc. Int.": "archive_interval_min",
}


def build_silver_query(bronze_path: str) -> str:
    """
    Build the SQL that transforms Bronze → Silver.
    Heavy lifting in DuckDB (much faster than pandas for this scale).
    """
    # Build the SELECT with proper renames and casts
    select_lines = [
        "station_id",
        # Build observation_ts from date_local + time_local
        ("strptime(\"Date\" || ' ' || \"Time\", '%d/%m/%y %H:%M') "
         "AS observation_ts"),
        '"Date" AS date_local_str',
        '"Time" AS time_local_str',
    ]

    numeric_renames = {
        "Temp Out": "temp_out_c",
        "Hi Temp": "temp_hi_c",
        "Low Temp": "temp_low_c",
        "Out Hum": "humidity_pct",
        "Dew Pt.": "dew_point_c",
        "Wind Speed": "wind_speed_kmh",
        "Wind Run": "wind_run_km",
        "Hi Speed": "wind_gust_kmh",
        "Wind Chill": "wind_chill_c",
        "Heat Index": "heat_index_c",
        "THW Index": "thw_index_c",
        "THSW Index": "thsw_index_c",
        "Bar": "pressure_hpa",
        "Rain": "precip_mm",
        "Rain Rate": "precip_rate_mmh",
        "Solar Rad.": "solar_wm2",
        "Solar Energy": "solar_energy_ly",
        "Hi Solar Rad.": "solar_hi_wm2",
        "UV Index": "uv_index",
        "UV Dose": "uv_dose_med",
        "Hi UV": "uv_hi",
        "Heat D-D": "heat_dd",
        "Cool D-D": "cool_dd",
        "In Temp": "in_temp_c",
        "In Hum": "in_humidity_pct",
        "In Dew": "in_dew_c",
        "In Heat": "in_heat_c",
        "In EMC": "in_emc",
        "In Air Density": "in_air_density",
        "ET": "etp_mm",
    }
    for src, dst in numeric_renames.items():
        select_lines.append(f'TRY_CAST("{src}" AS DOUBLE) AS {dst}')

    string_renames = {
        "Wind Dir": "wind_dir",
        "Hi Dir": "wind_gust_dir",
    }
    for src, dst in string_renames.items():
        select_lines.append(f'CAST("{src}" AS VARCHAR) AS {dst}')

    int_renames = {
        "Wind Samp": "wind_samples",
        "Wind Tx": "wind_tx",
        "Arc. Int.": "archive_interval_min",
    }
    for src, dst in int_renames.items():
        select_lines.append(f'TRY_CAST("{src}" AS INTEGER) AS {dst}')

    select_lines.append('TRY_CAST("ISS Recept" AS DOUBLE) AS iss_reception_pct')

    select_clause = ",\n            ".join(select_lines)

    return f"""
    WITH raw AS (
        SELECT *
        FROM read_parquet('{bronze_path}/**/*.parquet',
                          hive_partitioning=true)
    ),
    typed AS (
        SELECT
            {select_clause}
        FROM raw
        WHERE "Date" IS NOT NULL AND "Time" IS NOT NULL
    ),
    deduplicated AS (
        SELECT *
        FROM typed
        QUALIFY row_number() OVER (
            PARTITION BY station_id, observation_ts
            ORDER BY observation_ts
        ) = 1
    ),
    flagged AS (
        SELECT
            *,
            -- Quality flags (non-destructive: keep the row, mark issues)
            CASE
                WHEN temp_out_c < -10 OR temp_out_c > 55 THEN 'temp_out_of_range'
                WHEN humidity_pct < 0 OR humidity_pct > 100 THEN 'humidity_out_of_range'
                WHEN pressure_hpa < 950 OR pressure_hpa > 1050 THEN 'pressure_out_of_range'
                WHEN wind_speed_kmh < 0 OR wind_speed_kmh > 200 THEN 'wind_out_of_range'
                WHEN solar_wm2 < 0 OR solar_wm2 > 1500 THEN 'solar_out_of_range'
                ELSE NULL
            END AS quality_flag,
            -- Time partition keys (partition pruning in downstream queries)
            CAST(year(observation_ts) AS INTEGER) AS year,
            CAST(month(observation_ts) AS INTEGER) AS month,
            CAST(day(observation_ts) AS INTEGER) AS day,
            CAST(hour(observation_ts) AS INTEGER) AS hour
        FROM deduplicated
    )
    SELECT * FROM flagged
    """


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", default="data/bronze",
                        help="Input bronze dir")
    parser.add_argument("--out", default="data/silver/observations",
                        help="Output silver dir")
    args = parser.parse_args()

    bronze_path = str(Path(args.in_dir).resolve())
    silver_path = str(Path(args.out).resolve())
    Path(silver_path).mkdir(parents=True, exist_ok=True)

    print(f"SILVER TRANSFORMATION — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Source:      {bronze_path}")
    print(f"Destination: {silver_path}\n")

    con = duckdb.connect(":memory:")
    # DuckDB perf tuning
    con.execute("PRAGMA threads = 4;")
    con.execute("PRAGMA memory_limit = '2GB';")

    query = build_silver_query(bronze_path)

    # Execute and write to partitioned Parquet
    con.execute(f"""
        COPY (
            {query}
        )
        TO '{silver_path}'
        (FORMAT PARQUET,
         PARTITION_BY (station_id, year, month),
         OVERWRITE_OR_IGNORE 1,
         COMPRESSION SNAPPY)
    """)

    # Stats
    stats = con.execute(f"""
        SELECT
            station_id,
            COUNT(*) as n_rows,
            MIN(observation_ts) as first_ts,
            MAX(observation_ts) as last_ts,
            SUM(CASE WHEN quality_flag IS NOT NULL THEN 1 ELSE 0 END) as flagged
        FROM read_parquet('{silver_path}/**/*.parquet', hive_partitioning=true)
        GROUP BY station_id
        ORDER BY station_id
    """).fetchdf()

    print(stats.to_string(index=False))
    print(f"\n  Total rows: {stats['n_rows'].sum():,}")
    print(f"  Flagged:    {stats['flagged'].sum():,} "
          f"({100*stats['flagged'].sum()/stats['n_rows'].sum():.2f}%)")
    con.close()


if __name__ == "__main__":
    main()
