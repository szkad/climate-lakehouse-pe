"""
05_forecasting.py — Time-series forecasting with Prophet

Generates 30-day forecasts for two key climate variables per station:
  1. Daily mean temperature
  2. Daily total ETP (water demand)

Using Meta's Prophet — robust to seasonality, missing data, and outliers.
Includes uncertainty intervals (yhat_lower / yhat_upper) for risk-aware
decision making in Power BI.

Output: writes fact_forecast table back into climate.duckdb,
ready for Power BI consumption.

Usage:
    python src/05_forecasting.py
    python src/05_forecasting.py --horizon 60   # forecast 60 days ahead
"""

import argparse
import sys
import warnings
from pathlib import Path
from datetime import datetime

import duckdb
import pandas as pd

# Prophet is loud at import time; silence INFO logs
import logging
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=FutureWarning)

from prophet import Prophet


# Variables to forecast: (column_in_daily_table, friendly_name)
FORECAST_TARGETS = [
    ("temp_avg_c",    "temperatura_media"),
    ("etp_total_mm",  "etp_diaria"),
]


def fit_prophet(history: pd.DataFrame) -> Prophet:
    """
    Fit a Prophet model with sensible defaults for daily climate data.

    - yearly_seasonality: critical for climate (austral summer/winter)
    - weekly_seasonality: disabled (climate doesn't care about weekdays)
    - daily_seasonality:  disabled (we feed daily aggregates)
    - changepoint_prior_scale: relaxed to allow El Niño regime shifts
    - interval_width: 0.80 = 80% confidence interval (typical in forecasting)
    """
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        interval_width=0.80,
    )
    model.fit(history)
    return model


def forecast_one_series(
    history: pd.DataFrame,
    horizon_days: int,
) -> pd.DataFrame:
    """
    Train Prophet and produce forecast.

    Input:
        history: DataFrame with columns ['ds', 'y']
                 ds = date (datetime)
                 y  = target value (numeric)
    Returns:
        DataFrame with ['ds', 'yhat', 'yhat_lower', 'yhat_upper']
        for the FUTURE horizon only (no in-sample predictions).
    """
    model = fit_prophet(history)
    future = model.make_future_dataframe(periods=horizon_days, freq="D")
    forecast = model.predict(future)

    last_history_date = history["ds"].max()
    future_only = forecast[forecast["ds"] > last_history_date].copy()
    return future_only[["ds", "yhat", "yhat_lower", "yhat_upper"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/gold/climate.duckdb",
                        help="Path to climate.duckdb")
    parser.add_argument("--horizon", type=int, default=30,
                        help="Forecast horizon in days (default: 30)")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"ERROR: {db_path} does not exist. Run 04_silver_to_gold.py first.")
        sys.exit(1)

    print(f"FORECASTING — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Database:    {db_path}")
    print(f"Horizon:     {args.horizon} days\n")

    con = duckdb.connect(str(db_path))

    # Load history
    print("Loading history from fact_daily_summary...")
    history = con.execute("""
        SELECT
            station_id,
            date_local AS ds,
            temp_avg_c,
            etp_total_mm
        FROM fact_daily_summary
        ORDER BY station_id, date_local;
    """).fetchdf()
    history["ds"] = pd.to_datetime(history["ds"])

    stations = sorted(history["station_id"].unique())
    print(f"  Loaded {len(history):,} rows for {len(stations)} stations\n")

    all_forecasts = []

    for station in stations:
        sta_hist = history[history["station_id"] == station]
        print(f"Forecasting for {station} ({len(sta_hist)} historical days)")

        for col, target_name in FORECAST_TARGETS:
            series = sta_hist[["ds", col]].rename(columns={col: "y"}).dropna()
            try:
                fc = forecast_one_series(series, args.horizon)
                fc["station_id"] = station
                fc["target"] = target_name
                fc = fc.rename(columns={
                    "ds": "forecast_date",
                    "yhat": "forecast_value",
                    "yhat_lower": "forecast_lower_80",
                    "yhat_upper": "forecast_upper_80",
                })
                fc["model_run_ts"] = pd.Timestamp.utcnow()
                fc["model_name"] = "Prophet 1.x"
                all_forecasts.append(fc)
                print(f"  ✓ {target_name}: {len(fc)} forecasted days "
                      f"(value range: {fc['forecast_value'].min():.2f} – "
                      f"{fc['forecast_value'].max():.2f})")
            except Exception as e:
                print(f"  ✗ {target_name}: failed ({e})")

    if not all_forecasts:
        print("\nNo forecasts produced. Aborting.")
        con.close()
        sys.exit(1)

    forecast_df = pd.concat(all_forecasts, ignore_index=True)
    forecast_df = forecast_df[[
        "station_id", "forecast_date", "target",
        "forecast_value", "forecast_lower_80", "forecast_upper_80",
        "model_name", "model_run_ts",
    ]]

    # Persist back into DuckDB
    print(f"\nWriting fact_forecast ({len(forecast_df):,} rows) to {db_path}...")
    con.execute("DROP TABLE IF EXISTS fact_forecast;")
    con.register("df_forecast", forecast_df)
    con.execute("""
        CREATE TABLE fact_forecast AS
        SELECT
            station_id,
            CAST(forecast_date AS DATE) AS forecast_date,
            target,
            CAST(forecast_value AS DOUBLE)      AS forecast_value,
            CAST(forecast_lower_80 AS DOUBLE)   AS forecast_lower_80,
            CAST(forecast_upper_80 AS DOUBLE)   AS forecast_upper_80,
            model_name,
            CAST(model_run_ts AS TIMESTAMP)     AS model_run_ts
        FROM df_forecast;
    """)

    # Validation summary
    summary = con.execute("""
        SELECT
            station_id,
            target,
            COUNT(*) AS n_days,
            ROUND(AVG(forecast_value), 2)         AS avg_forecast,
            ROUND(MIN(forecast_lower_80), 2)      AS min_lower,
            ROUND(MAX(forecast_upper_80), 2)      AS max_upper
        FROM fact_forecast
        GROUP BY station_id, target
        ORDER BY station_id, target;
    """).fetchdf()
    print("\nForecast summary:")
    print(summary.to_string(index=False))

    con.close()
    print("\n✅ Done. fact_forecast is ready for Power BI.")


if __name__ == "__main__":
    main()
