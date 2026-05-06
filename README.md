# Climate Lakehouse PE 🌦️

Modern lakehouse architecture for climate analytics in Peruvian agroindustry. Synthetic dataset replicating real climate patterns of northern Peru's agroexport corridor (Piura/Lambayeque region) — including the 2023 El Niño Costero (Yaku) and the 2023-24 Global El Niño event.

> **Inspired by a real-world modernization case:** transforming a legacy process based on daily TXT exports + Excel macros into a modern ELT pipeline (DuckDB + Parquet + medallion architecture + ML forecasting).

![Architecture](docs/architecture.svg)

---

## 🎯 What this project demonstrates

| Capability | Implementation |
|---|---|
| **Data Engineering** | ELT pipeline with medallion architecture (Bronze / Silver / Gold) |
| **Modern data stack** | DuckDB + Parquet + Python — no cloud cost, full lakehouse experience |
| **Dimensional modeling** | Kimball star schema (2 dimensions, 4 fact tables) |
| **Advanced DAX** | 39 measures with Time Intelligence, anomaly detection, prescriptive analytics |
| **Tool mastery** | Tabular Editor 2 (C# scripted measure deployment), DAX Studio, Bravo |
| **ML forecasting** | Prophet (Meta) — 30-day forecast with 80% confidence bands |
| **Data storytelling** | 5 dashboard pages with progressive narrative arc |
| **Domain knowledge** | Agroindustrial language: ETP, water balance, irrigation recommendations |

---

## 📊 Dashboard

5 pages telling the climate story of Peru's northern agroexport corridor:

| Page | Story | Key visuals |
|---|---|---|
| **1. Overview** | Snapshot of regional climate | KPIs, choropleth map, time series |
| **2. El Niño 2023-24** | Yaku impact and Global Niño anomalies | YoY rainfall, monthly heatmap, top events |
| **3. Water Management** | ETP vs precipitation balance — irrigation needs | Water balance heatmap, prescriptive recommendation |
| **4. Climate Alerts** | Detected extreme events (heat, rain, wind, UV) | KPIs by event type, treemap, monthly distribution |
| **5. Forecast** | 30-day forecast (Prophet) for temperature and ETP | Time series with confidence bands, detail table |

### Screenshots

![Overview](docs/screenshots/01_overview.png)
*Page 1 — Regional climate overview*

![El Niño](docs/screenshots/02_el_nino.png)
*Page 2 — Documented impact of Yaku and Global Niño*

![Water Management](docs/screenshots/03_water.png)
*Page 3 — Water balance with prescriptive recommendation*

![Alerts](docs/screenshots/04_alerts.png)
*Page 4 — Automated extreme event detection system*

![Forecast](docs/screenshots/05_forecast.png)
*Page 5 — Forecast with Prophet (Meta)*

---

## 🏗️ Architecture

### Medallion data flow

```
4 Stations         Bronze              Silver              Gold (DuckDB)
(Davis V.Pro 2)    (raw Parquet)       (cleaned Parquet)   (star schema)
    TXT       →    partitioned    →    typed, validated  →  dim_*, fact_*
                   by station/         deduplicated         relational model
                   year/month
                                                                ↓
                                                          Power BI (ODBC)
                                                          Prophet → fact_forecast
```

### Tech stack

- **Python 3.11+** — pipeline orchestration
- **DuckDB** — embedded analytical engine (no server needed)
- **Apache Parquet** — columnar storage with Snappy compression
- **Prophet** — time-series forecasting (Meta)
- **Power BI Desktop** — dashboards (DuckDB ODBC connection)
- **Tabular Editor 2** — programmatic DAX deployment
- **DAX Studio + Bravo** — query optimization and model analysis

---

## 📁 Project structure

```
climate-lakehouse-pe/
├── README.md                   ← This document
├── LICENSE                     ← MIT
├── requirements.txt            ← Python dependencies
├── .gitignore
│
├── src/
│   ├── 01_generate_synthetic.py     ← Synthetic data generator
│   ├── 02_ingest_to_bronze.py       ← TXT → Parquet (Bronze)
│   ├── 03_bronze_to_silver.py       ← Cleaning (Silver)
│   ├── 04_silver_to_gold.py         ← Star schema (Gold)
│   ├── 05_forecasting.py            ← Prophet forecasting
│   └── utils/
│       ├── stations.py              ← 4 station configs
│       ├── climate_patterns.py      ← Seasonality, El Niño, noise
│       └── meteorology.py           ← Penman-Monteith, dew point, etc.
│
├── data/
│   ├── raw/                    ← 4 TXT files (Davis Vantage Pro 2 schema)
│   ├── bronze/                 ← Raw Parquet, partitioned
│   ├── silver/                 ← Clean Parquet
│   └── gold/
│       └── climate.duckdb      ← Final analytical DB
│
├── powerbi/
│   ├── ClimateLakehousePE.pbix      ← Dashboard (5 pages)
│   ├── dax_measures.cs              ← Tabular Editor C# script (39 measures)
│   └── climate_theme.json           ← Custom Power BI theme
│
├── sql/                        ← Standalone SQL queries (DuckDB)
│
└── docs/
    ├── architecture.svg
    ├── dashboard_spec.md       ← Visual specification of the 5 pages
    └── screenshots/
        ├── 01_overview.png
        ├── 02_el_nino.png
        ├── 03_water.png
        ├── 04_alerts.png
        └── 05_forecast.png
```

---

## 🚀 Quickstart

### Requirements

- Python 3.11+
- Power BI Desktop (Windows)
- DuckDB ODBC Driver — [download](https://duckdb.org/docs/installation/?version=stable&environment=odbc)

### Install dependencies

```bash
git clone https://github.com/szkad/climate-lakehouse-pe.git
cd climate-lakehouse-pe
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt
```

### Run the pipeline

```bash
python src/01_generate_synthetic.py    # ~7 sec, generates 140K records
python src/02_ingest_to_bronze.py      # TXT → Parquet
python src/03_bronze_to_silver.py      # Clean
python src/04_silver_to_gold.py        # Build star schema
python src/05_forecasting.py           # Train Prophet, write fact_forecast
```

This generates `data/gold/climate.duckdb` (~25 MB) ready for Power BI consumption.

### Open the dashboard

```
1. Open powerbi/ClimateLakehousePE.pbix in Power BI Desktop
2. If prompted to refresh data: confirm and update the ODBC connection
   to point to your local data/gold/climate.duckdb
3. Done.
```

---

## 🔬 The synthetic dataset

### Why synthetic?

The project is inspired by real experience with Davis Vantage Pro 2 weather stations in northern Peruvian agroindustry, but **all data is 100% synthetic and publishable**. No confidential information from any company is exposed.

### What's realistic about it

The generator implements:

- **Annual seasonality** — austral summer/winter cycles
- **Diurnal cycle** — 14:00 peak temperature, 05:00 minimum
- **Inter-station differentiation** — coast vs valleys vs pre-Andean
- **El Niño Costero 2023 (Yaku)** — heavy rainfall episode March-May 2023
- **Global El Niño 2023-24** — temperature anomalies for 12 months
- **Storm episodes** — concentrated torrential bursts during Niño events
- **Wind events** — 5-7 strong gust episodes per year per station
- **AR(1) noise** — realistic autocorrelated weather variability
- **Missing data** — ~0.3% NaN simulating real station glitches

### Variables (39 columns, Davis Vantage Pro 2 schema)

Primary measurements:
`temp_out_c`, `humidity_pct`, `wind_speed_kmh`, `wind_dir`, `pressure_hpa`, `precip_mm`, `solar_wm2`, `uv_index`

Derived using **real meteorological formulas:**
- `dew_point_c` — Magnus-Tetens formula
- `heat_index_c` — NWS Rothfusz regression
- `wind_chill_c` — NWS official formula
- `thsw_index_c` — apparent temperature with solar component
- `etp_mm` — **FAO-56 Penman-Monteith** (key irrigation metric)
- `air_density` — ideal gas law with vapor correction

This is industry-standard meteorology, not random numbers.

---

## 🎨 Design choices

### Why DuckDB + Parquet?

DuckDB is the most exciting development in modern analytics: full SQL OLAP power without a server. It reads and writes Parquet natively, integrates with Python, and connects to BI tools via ODBC. **Perfect for projects where deploying a cloud warehouse would be overkill.**

### Why a synthetic dataset and not Kaggle?

Two reasons:
1. **Differentiation** — anyone can use a Kaggle dataset; few can design realistic ones for a specific domain.
2. **Domain expertise** — designing a generator that captures el-Niño patterns, ETP physics, and Davis Vantage Pro 2 schema demonstrates understanding of the agricultural meteorology domain.

### Why include forecasting?

Most BI projects are descriptive (what happened?). Top-tier BI projects are predictive (what will happen?) and prescriptive (what should we do?). This project includes all three:

- Pages 1, 2, 4 → **Descriptive**
- Page 5 → **Predictive** (Prophet forecast)
- Page 3 → **Prescriptive** (irrigation recommendation)

---

## 📈 Sample insights from the dashboard

- **The water balance is structurally negative** in northern Peru's coast: ETP exceeds precipitation in 92 of the 96 station-months in the period (~96% of the time).
- **El Niño Costero 2023 multiplied rainfall by 70x** in some areas (e.g., March 2023 in Pre-Andean zone: 293mm vs ~4mm normal).
- **The Pre-Andean zone receives the most extreme impact** from coastal El Niño events, consistent with documented behavior of foothills amplifying coastal rains.
- **The forecast for next 30 days predicts ETP > 7 mm/day** at all stations, indicating sustained intensive irrigation requirements.

---

## 🛠️ Technical highlights

### Tabular Editor + C# for DAX deployment

Instead of clicking each measure manually in Power BI Desktop, the entire 39-measure model is deployed via a C# script in Tabular Editor:

```csharp
M("Δ Temp vs AA",
  "[Temp Promedio] - [Temp Promedio AA]",
  "+0.0 °C;-0.0 °C;0",
  "03 Time Intelligence",
  "Difference vs same period last year");
```

This is industry-standard practice for BI teams managing many measures.

### Prescriptive measure example

The "Irrigation Recommendation" measure goes beyond descriptive analytics:

```dax
Recomendación de Riego =
VAR Balance = [Balance Hídrico]
VAR Days = [Días con Datos]
VAR DailyBalance = DIVIDE(Balance, Days)
RETURN
SWITCH(
    TRUE(),
    DailyBalance > 0,    "✅ No irrigation needed",
    DailyBalance > -3,   "🟡 Light irrigation recommended",
    DailyBalance > -6,   "🟠 Moderate irrigation needed",
    "🔴 Critical intensive irrigation"
)
```

---

## 📝 License

MIT — see [LICENSE](LICENSE)

## 👤 Author

**Alexis Zapata** — BI Analyst | Sullana, Peru
- GitHub: [@szkad](https://github.com/szkad)
- Background: 5+ years in northern Peru agroindustry
- Stack: Power BI, DAX, SQL, Python, DuckDB, Parquet, Power Query
- Certifications: Google Advanced Data Analytics (April 2026)

---

## 🙏 Acknowledgments

- **Davis Instruments** for the Vantage Pro 2 data schema reference
- **Meta AI** for open-sourcing Prophet
- **DuckDB Labs** for democratizing analytical engines
- **The FAO** for documentation of the Penman-Monteith equation
