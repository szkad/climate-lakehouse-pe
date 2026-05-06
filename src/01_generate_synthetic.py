"""
01_generate_synthetic.py — Synthetic weather data generator

Generates realistic 30-min interval weather data for the Climate
Lakehouse PE project. Replicates the 39-column schema of Davis Vantage
Pro 2 weather stations.

Output: TXT files (one per station) in data/raw/ — these simulate
the daily TXT exports that real weather station software generates.

Usage:
    python src/01_generate_synthetic.py [--days N] [--out PATH]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# Make utils importable when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.stations import STATIONS, StationConfig
from utils.climate_patterns import (
    seasonal_temperature, seasonal_humidity, precipitation_series,
    solar_radiation, wind_series
)
from utils.meteorology import (
    dew_point_c, heat_index_c, wind_chill_c, thw_index_c, thsw_index_c,
    air_density_kg_m3, degree_days, etp_penman_monteith_30min
)


# Davis Vantage Pro 2 — 39 column schema (exact replica)
DAVIS_COLUMNS = [
    "Date", "Time", "Temp Out", "Hi Temp", "Low Temp", "Out Hum",
    "Dew Pt.", "Wind Speed", "Wind Dir", "Wind Run", "Hi Speed", "Hi Dir",
    "Wind Chill", "Heat Index", "THW Index", "THSW Index", "Bar", "Rain",
    "Rain Rate", "Solar Rad.", "Solar Energy", "Hi Solar Rad.", "UV Index",
    "UV Dose", "Hi UV", "Heat D-D", "Cool D-D", "In Temp", "In Hum",
    "In Dew", "In Heat", "In EMC", "In Air Density", "ET", "Wind Samp",
    "Wind Tx", "ISS Recept", "Arc. Int."
]


def generate_station_data(
    station: StationConfig,
    start_date: datetime,
    end_date: datetime,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate full 39-column dataset for one station."""

    rng = np.random.default_rng(seed + hash(station.station_id) % 10000)

    # Build 30-min timestamp index
    timestamps = pd.date_range(start=start_date, end=end_date, freq="30min")
    n = len(timestamps)
    print(f"  {station.station_id}: generating {n:,} records "
          f"({start_date.date()} → {end_date.date()})")

    # ─── PRIMARY VARIABLES ───────────────────────────────────────────
    temp_out = seasonal_temperature(timestamps, station, rng)
    humidity = seasonal_humidity(timestamps, station, temp_out, rng)
    precip = precipitation_series(timestamps, station, rng)
    solar = solar_radiation(timestamps, station, humidity, precip, rng)
    wind_speed, wind_dir, hi_speed, hi_dir = wind_series(timestamps, station, rng)

    # Pressure: baseline + small noise + weather-system variation
    pressure = (station.pressure_baseline
                + rng.normal(0, 1.5, n)
                + 3.0 * np.sin(np.arange(n) * 2 * np.pi / (48 * 7)))  # weekly cycle

    # Indoor conditions (more stable than outdoor)
    in_temp = (station.temp_annual_mean
               + 0.3 * (temp_out - station.temp_annual_mean)
               + rng.normal(0, 0.5, n))
    in_humidity = np.clip(humidity * 0.7 + 15 + rng.normal(0, 1.5, n), 25, 80)

    # ─── DERIVED VARIABLES (real meteorological formulas) ────────────
    dew_pt = dew_point_c(temp_out, humidity)
    in_dew = dew_point_c(in_temp, in_humidity)
    heat_idx = heat_index_c(temp_out, humidity)
    in_heat = heat_index_c(in_temp, in_humidity)
    wind_chl = wind_chill_c(temp_out, wind_speed)
    thw = thw_index_c(temp_out, humidity, wind_speed)
    thsw = thsw_index_c(temp_out, humidity, wind_speed, solar)
    air_dens = air_density_kg_m3(temp_out, pressure, humidity)

    # Hi/Low Temp: rolling 30-min observed window (with small spread)
    hi_temp = temp_out + rng.uniform(0.0, 0.3, n)
    low_temp = temp_out - rng.uniform(0.0, 0.3, n)

    # Wind Run (km accumulated in interval): speed * 0.5 hours
    wind_run = wind_speed * 0.5

    # Solar derived
    # Energy: integral over 30-min interval (Ly = langley)
    # 1 W/m² over 30min ≈ 0.043 Ly
    solar_energy = solar * 0.043
    hi_solar = solar + rng.uniform(0, 30, n) * (solar > 0)

    # UV index from solar (rough approximation: peak ~12 at strong sun)
    uv_index = np.clip(solar / 90, 0, 14)
    uv_dose = uv_index * 0.06  # MED units approximation
    hi_uv = uv_index + rng.uniform(0, 0.5, n) * (uv_index > 0)

    # Rain rate (mm/hr): if precip>0 in this 30min, rate = precip*2
    rain_rate = precip * 2

    # Degree days (per 30-min step)
    heat_dd = degree_days(temp_out, base_c=18.0, mode="heat")
    cool_dd = degree_days(temp_out, base_c=18.0, mode="cool")

    # Indoor EMC (Equilibrium Moisture Content) — wood moisture %
    # Simplified: function of in_humidity
    in_emc = 0.05 * in_humidity + rng.normal(0, 0.3, n)

    # ─── ETP (the agroindustrial gold metric) ────────────────────────
    etp = etp_penman_monteith_30min(
        temp_out, humidity, wind_speed, solar, pressure, station.altitude_m
    )

    # ─── METADATA columns (typical Davis station outputs) ────────────
    wind_samp = rng.integers(680, 720, n)
    wind_tx = np.ones(n, dtype=int)
    iss_recept = rng.uniform(98, 100, n).round(1)
    arc_int = np.full(n, 30, dtype=int)

    # ─── ASSEMBLE DATAFRAME ──────────────────────────────────────────
    df = pd.DataFrame({
        "Date": timestamps.strftime("%d/%m/%y"),
        "Time": timestamps.strftime("%H:%M"),
        "Temp Out": temp_out.round(1),
        "Hi Temp": hi_temp.round(1),
        "Low Temp": low_temp.round(1),
        "Out Hum": humidity.round(0).astype(int),
        "Dew Pt.": dew_pt.round(1),
        "Wind Speed": wind_speed.round(1),
        "Wind Dir": wind_dir,
        "Wind Run": wind_run.round(2),
        "Hi Speed": hi_speed.round(1),
        "Hi Dir": hi_dir,
        "Wind Chill": wind_chl.round(1),
        "Heat Index": heat_idx.round(1),
        "THW Index": thw.round(1),
        "THSW Index": thsw.round(1),
        "Bar": pressure.round(1),
        "Rain": precip.round(2),
        "Rain Rate": rain_rate.round(2),
        "Solar Rad.": solar.round(0).astype(int),
        "Solar Energy": solar_energy.round(2),
        "Hi Solar Rad.": hi_solar.round(0).astype(int),
        "UV Index": uv_index.round(1),
        "UV Dose": uv_dose.round(2),
        "Hi UV": hi_uv.round(1),
        "Heat D-D": heat_dd.round(3),
        "Cool D-D": cool_dd.round(3),
        "In Temp": in_temp.round(1),
        "In Hum": in_humidity.round(0).astype(int),
        "In Dew": in_dew.round(1),
        "In Heat": in_heat.round(1),
        "In EMC": in_emc.round(2),
        "In Air Density": air_dens.round(4),
        "ET": etp.round(3),
        "Wind Samp": wind_samp,
        "Wind Tx": wind_tx,
        "ISS Recept": iss_recept,
        "Arc. Int.": arc_int,
    })

    # Inject missing data (~0.3%) - realistic for weather stations
    n_missing = int(n * 0.003)
    miss_idx = rng.choice(n, n_missing, replace=False)
    for col in ["Temp Out", "Out Hum", "Wind Speed", "Solar Rad."]:
        sub_idx = rng.choice(miss_idx, len(miss_idx) // 4, replace=False)
        df.loc[sub_idx, col] = np.nan

    return df


def write_davis_txt(df: pd.DataFrame, station: StationConfig, path: Path) -> None:
    """
    Write data in Davis Vantage Pro 2 TXT format:
    - Line 1: station name (header)
    - Line 2: column headers (English)
    - Line 3: column subheaders (Spanish friendly names)
    - Lines 4+: data
    Tab-separated.
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{station.name}\n")
        f.write("\t".join(DAVIS_COLUMNS) + "\n")
        # Spanish subheader (matches real export)
        spanish_sub = [
            "Fecha", "Hora", "T° Out", "Hi Temp", "Low Temp", "Humedad",
            "Dew Pt.", "Vel. Viento (km/h)", "Wind Dir", "Wind Run",
            "Hi Speed", "Hi Dir", "Wind Chill", "Heat Index", "THW Index",
            "THSW Index", "Bar (hPa)", "Precipitacion (mm)", "Rain Rate",
            "Solar Rad. (W/m2)", "Solar Energy", "Hi Solar Rad.",
            "Radiacion UV", "UV Dose", "Hi UV", "Heat D-D", "Cool D-D",
            "In Temp", "In Hum", "In Dew", "In Heat", "In EMC",
            "In Air Density", "ETP (mm)", "Wind Samp", "Wind Tx",
            "ISS Recept", "Arc. Int."
        ]
        f.write("\t".join(spanish_sub) + "\n")
        df.to_csv(f, sep="\t", index=False, header=False, na_rep="---")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01",
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2024-12-31",
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=None,
                        help="Override: generate only N days from start")
    parser.add_argument("--out", default="data/raw",
                        help="Output directory")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stations", default="all",
                        help="Comma-separated station IDs, or 'all'")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    if args.days is not None:
        end = start + timedelta(days=args.days)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Filter stations
    if args.stations == "all":
        stations = STATIONS
    else:
        wanted = set(args.stations.split(","))
        stations = [s for s in STATIONS if s.station_id in wanted]

    print(f"Generating data for {len(stations)} station(s) "
          f"from {start.date()} to {end.date()}")
    print(f"Output dir: {out_dir.resolve()}\n")

    for station in stations:
        df = generate_station_data(station, start, end, seed=args.seed)
        out_path = out_dir / f"{station.station_id}.txt"
        write_davis_txt(df, station, out_path)
        size_mb = out_path.stat().st_size / 1024 / 1024
        print(f"  → {out_path.name} ({size_mb:.1f} MB, {len(df):,} rows)\n")

    print("Done.")


if __name__ == "__main__":
    main()
