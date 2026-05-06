"""
02_ingest_to_bronze.py — Raw TXT → Parquet (Bronze layer)

Reads raw Davis Vantage Pro 2 TXT exports from data/raw/ and writes
them as Parquet to data/bronze/, partitioned by station/year/month.

This script preserves the data AS-IS (no cleaning), which is the core
principle of a Bronze layer in medallion architecture: raw, immutable,
auditable.

Why Parquet?
- 8-10x smaller than TXT (columnar compression)
- Native types (no string parsing on every read)
- Predicate pushdown (queries skip irrelevant partitions)
- Native to the modern data stack (DuckDB, Spark, BigQuery, etc.)
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.stations import STATIONS


# Schema of the Davis TXT export (39 columns + station_id added)
RAW_COLUMNS = [
    "Date", "Time", "Temp Out", "Hi Temp", "Low Temp", "Out Hum",
    "Dew Pt.", "Wind Speed", "Wind Dir", "Wind Run", "Hi Speed", "Hi Dir",
    "Wind Chill", "Heat Index", "THW Index", "THSW Index", "Bar", "Rain",
    "Rain Rate", "Solar Rad.", "Solar Energy", "Hi Solar Rad.", "UV Index",
    "UV Dose", "Hi UV", "Heat D-D", "Cool D-D", "In Temp", "In Hum",
    "In Dew", "In Heat", "In EMC", "In Air Density", "ET", "Wind Samp",
    "Wind Tx", "ISS Recept", "Arc. Int."
]


def read_davis_txt(path: Path, station_id: str) -> pd.DataFrame:
    """
    Read a Davis Vantage Pro 2 export file.

    Format:
        Line 1: Station name
        Line 2: English headers
        Line 3: Spanish friendly headers (skip)
        Lines 4+: Data, tab-separated, NaN as '---'
    """
    df = pd.read_csv(
        path,
        sep="\t",
        skiprows=[0, 2],     # skip station name + Spanish header
        na_values="---",
        encoding="utf-8",
    )

    # Add lineage columns
    df["station_id"] = station_id
    df["ingestion_ts"] = pd.Timestamp.utcnow()
    df["source_file"] = path.name

    return df


def write_bronze_partitioned(
    df: pd.DataFrame,
    out_dir: Path,
    station_id: str,
) -> int:
    """
    Write to Parquet partitioned by year/month.
    Returns number of partitions written.
    """
    # Build a proper datetime column for partitioning
    df["_dt"] = pd.to_datetime(
        df["Date"] + " " + df["Time"],
        format="%d/%m/%y %H:%M",
        errors="coerce",
    )
    df["year"] = df["_dt"].dt.year.astype("int32")
    df["month"] = df["_dt"].dt.month.astype("int32")
    df = df.drop(columns=["_dt"])

    # Convert object columns to string for Parquet
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype("string")

    table = pa.Table.from_pandas(df, preserve_index=False)

    pq.write_to_dataset(
        table,
        root_path=str(out_dir),
        partition_cols=["station_id", "year", "month"],
        compression="snappy",
        existing_data_behavior="overwrite_or_ignore",
    )

    return df.groupby(["year", "month"]).ngroups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_dir", default="data/raw",
                        help="Input dir with TXT files")
    parser.add_argument("--out", default="data/bronze",
                        help="Output dir for Parquet")
    args = parser.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"BRONZE INGESTION — {datetime.now().isoformat(timespec='seconds')}")
    print(f"Source:      {in_dir.resolve()}")
    print(f"Destination: {out_dir.resolve()}\n")

    total_rows = 0
    total_files = 0

    for station in STATIONS:
        txt_path = in_dir / f"{station.station_id}.txt"
        if not txt_path.exists():
            print(f"  ⚠ {station.station_id}: TXT not found, skipping")
            continue

        df = read_davis_txt(txt_path, station.station_id)
        n_partitions = write_bronze_partitioned(df, out_dir, station.station_id)

        print(f"  ✓ {station.station_id}: {len(df):,} rows → "
              f"{n_partitions} partitions")
        total_rows += len(df)
        total_files += 1

    print(f"\n  Total: {total_files} stations, {total_rows:,} rows")

    # Report compression
    txt_size = sum((in_dir / f"{s.station_id}.txt").stat().st_size
                   for s in STATIONS
                   if (in_dir / f"{s.station_id}.txt").exists())
    parquet_size = sum(
        f.stat().st_size for f in out_dir.rglob("*.parquet")
    )
    print(f"\n  TXT total:     {txt_size/1024/1024:.1f} MB")
    print(f"  Parquet total: {parquet_size/1024/1024:.1f} MB")
    print(f"  Compression:   {txt_size/parquet_size:.1f}x")


if __name__ == "__main__":
    main()
