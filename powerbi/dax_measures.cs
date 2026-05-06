// =============================================================================
// Climate Lakehouse PE — DAX Measures injector
// Run this script in Tabular Editor 2/3 (Advanced Scripting tab → F5)
// All measures land in the 'fact_daily_summary' table, organized in folders.
// =============================================================================

var t = Model.Tables["fact_daily_summary"];

// Helper: create or replace a measure
Action<string, string, string, string, string> M = (name, expression, format, folder, description) => {
    var existing = t.Measures.FirstOrDefault(meas => meas.Name == name);
    if (existing != null) existing.Delete();
    var newM = t.AddMeasure(name, expression);
    newM.FormatString = format;
    newM.DisplayFolder = folder;
    newM.Description = description;
};

// ─── 01. KPIs CORE ────────────────────────────────────────────────────────
M("Temp Promedio",
  "AVERAGE(fact_daily_summary[temp_avg_c])",
  "0.0 \"°C\"",
  "01 KPIs Core",
  "Temperatura promedio diaria del rango filtrado");

M("Temp Máxima",
  "MAX(fact_daily_summary[temp_max_c])",
  "0.0 \"°C\"",
  "01 KPIs Core",
  "Temperatura máxima absoluta del rango filtrado");

M("Temp Mínima",
  "MIN(fact_daily_summary[temp_min_c])",
  "0.0 \"°C\"",
  "01 KPIs Core",
  "Temperatura mínima absoluta del rango filtrado");

M("Humedad Promedio",
  "AVERAGE(fact_daily_summary[humidity_avg_pct])",
  "0.0 \"%\"",
  "01 KPIs Core",
  "Humedad relativa promedio");

M("Precipitación Acumulada",
  "SUM(fact_daily_summary[precip_total_mm])",
  "#,0.0 \"mm\"",
  "01 KPIs Core",
  "Precipitación acumulada total en el rango filtrado");

M("ETP Acumulada",
  "SUM(fact_daily_summary[etp_total_mm])",
  "#,0.0 \"mm\"",
  "01 KPIs Core",
  "Evapotranspiración de referencia acumulada (demanda hídrica)");

M("Balance Hídrico",
  "SUM(fact_daily_summary[water_balance_mm])",
  "#,0.0 \"mm\"",
  "01 KPIs Core",
  "Precipitación menos ETP. Negativo = déficit, positivo = superávit");

M("Días con Datos",
  "COUNTROWS(fact_daily_summary)",
  "#,0",
  "01 KPIs Core",
  "Número de días con observaciones en el rango filtrado");

// ─── 02. EVENTOS EXTREMOS ─────────────────────────────────────────────────
M("Días con Calor Extremo",
  "SUM(fact_daily_summary[is_hot_day])",
  "#,0",
  "02 Eventos Extremos",
  "Días con temperatura máxima > 32°C");

M("Días Lluviosos",
  "SUM(fact_daily_summary[is_rainy_day])",
  "#,0",
  "02 Eventos Extremos",
  "Días con precipitación acumulada > 2mm");

M("Días con Vientos Fuertes",
  "SUM(fact_daily_summary[is_windy_day])",
  "#,0",
  "02 Eventos Extremos",
  "Días con ráfagas máximas > 35 km/h");

M("Días con UV Crítico",
  "SUM(fact_daily_summary[is_uv_extreme])",
  "#,0",
  "02 Eventos Extremos",
  "Días con índice UV máximo > 12");

M("% Días con Calor Extremo",
  "DIVIDE([Días con Calor Extremo], [Días con Datos])",
  "0.0 %",
  "02 Eventos Extremos",
  "Proporción de días con calor extremo en el rango");

// ─── 03. TIME INTELLIGENCE ────────────────────────────────────────────────
M("Temp Promedio AA",
  "CALCULATE([Temp Promedio], SAMEPERIODLASTYEAR(dim_date[date_local]))",
  "0.0 \"°C\"",
  "03 Time Intelligence",
  "Temperatura promedio del mismo período del año anterior");

M("Δ Temp vs AA",
  "[Temp Promedio] - [Temp Promedio AA]",
  "+0.0 \"°C\";-0.0 \"°C\";0",
  "03 Time Intelligence",
  "Diferencia de temperatura vs año anterior (positivo = más caliente)");

M("Δ Temp vs AA %",
  "DIVIDE([Δ Temp vs AA], [Temp Promedio AA])",
  "+0.0 %;-0.0 %;0",
  "03 Time Intelligence",
  "Variación porcentual de temperatura vs año anterior");

M("Precip Acum AA",
  "CALCULATE([Precipitación Acumulada], SAMEPERIODLASTYEAR(dim_date[date_local]))",
  "#,0.0 \"mm\"",
  "03 Time Intelligence",
  "Precipitación acumulada del mismo período del año anterior");

M("Multiplicador Lluvia vs AA",
  "DIVIDE([Precipitación Acumulada], [Precip Acum AA])",
  "0.0 \"x\"",
  "03 Time Intelligence",
  "Cuántas veces llovió más vs año anterior (útil para narrar Niño)");

M("Temp YTD",
  "CALCULATE([Temp Promedio], DATESYTD(dim_date[date_local]))",
  "0.0 \"°C\"",
  "03 Time Intelligence",
  "Temperatura promedio acumulada del año en curso");

M("Precip YTD",
  "CALCULATE([Precipitación Acumulada], DATESYTD(dim_date[date_local]))",
  "#,0.0 \"mm\"",
  "03 Time Intelligence",
  "Precipitación acumulada del año en curso");

M("ETP YTD",
  "CALCULATE([ETP Acumulada], DATESYTD(dim_date[date_local]))",
  "#,0.0 \"mm\"",
  "03 Time Intelligence",
  "Evapotranspiración acumulada del año en curso");

// ─── 04. ANÁLISIS NIÑO / CLIMA ────────────────────────────────────────────
M("Lluvia en Período Niño",
  @"CALCULATE(
        [Precipitación Acumulada],
        dim_date[is_el_nino] = 1
    )",
  "#,0.0 \"mm\"",
  "04 Análisis Niño",
  "Lluvia acumulada solo durante períodos de El Niño");

M("Lluvia en Período Normal",
  @"CALCULATE(
        [Precipitación Acumulada],
        dim_date[is_el_nino] = 0
    )",
  "#,0.0 \"mm\"",
  "04 Análisis Niño",
  "Lluvia acumulada solo durante períodos sin Niño");

M("Anomalía Temp vs Promedio Histórico",
  @"VAR HistoricalAvg =
      CALCULATE(
          [Temp Promedio],
          ALL(dim_date),
          dim_date[is_el_nino] = 0
      )
    RETURN [Temp Promedio] - HistoricalAvg",
  "+0.0 \"°C\";-0.0 \"°C\";0",
  "04 Análisis Niño",
  "Diferencia entre temp del rango filtrado y promedio histórico de períodos normales");

// ─── 05. GESTIÓN HÍDRICA ──────────────────────────────────────────────────
M("ETP Diaria Promedio",
  "DIVIDE([ETP Acumulada], [Días con Datos])",
  "0.00 \"mm/día\"",
  "05 Gestión Hídrica",
  "ETP promedio por día en el rango filtrado");

M("Lluvia Diaria Promedio",
  "DIVIDE([Precipitación Acumulada], [Días con Datos])",
  "0.00 \"mm/día\"",
  "05 Gestión Hídrica",
  "Precipitación promedio por día en el rango filtrado");

M("Días con Déficit Hídrico Severo",
  "CALCULATE([Días con Datos], fact_daily_summary[water_balance_mm] < -7)",
  "#,0",
  "05 Gestión Hídrica",
  "Días con balance hídrico < -7 mm (alta demanda de riego)");

M("% Días con Déficit Severo",
  "DIVIDE([Días con Déficit Hídrico Severo], [Días con Datos])",
  "0.0 %",
  "05 Gestión Hídrica",
  "Proporción de días con déficit hídrico severo");

M("Recomendación de Riego",
  @"VAR Balance = [Balance Hídrico]
    VAR DiasConDatos = [Días con Datos]
    VAR BalanceDiario = DIVIDE(Balance, DiasConDatos)
    RETURN
    SWITCH(
        TRUE(),
        BalanceDiario > 0,    ""✅ Sin necesidad de riego"",
        BalanceDiario > -3,   ""🟡 Riego ligero recomendado"",
        BalanceDiario > -6,   ""🟠 Riego moderado necesario"",
        ""🔴 Riego intensivo crítico""
    )",
  "",
  "05 Gestión Hídrica",
  "Recomendación cualitativa de riego basada en balance hídrico promedio");

// ─── 06. FORECAST ─────────────────────────────────────────────────────────
// Note: these measures live on fact_forecast but we organize them in the
// same model. We'll add them on fact_forecast directly:

var fc = Model.Tables["fact_forecast"];

Action<Table, string, string, string, string, string> Mt = (tbl, name, expression, format, folder, description) => {
    var existing = tbl.Measures.FirstOrDefault(meas => meas.Name == name);
    if (existing != null) existing.Delete();
    var newM = tbl.AddMeasure(name, expression);
    newM.FormatString = format;
    newM.DisplayFolder = folder;
    newM.Description = description;
};

Mt(fc, "Forecast Temp",
   @"CALCULATE(
        AVERAGE(fact_forecast[forecast_value]),
        fact_forecast[target] = ""temperatura_media""
   )",
   "0.0 \"°C\"",
   "06 Forecasting",
   "Temperatura promedio prevista (Prophet)");

Mt(fc, "Forecast ETP",
   @"CALCULATE(
        SUM(fact_forecast[forecast_value]),
        fact_forecast[target] = ""etp_diaria""
   )",
   "#,0.0 \"mm\"",
   "06 Forecasting",
   "ETP acumulada prevista en el horizonte");

Mt(fc, "Forecast Temp Lower",
   @"CALCULATE(
        AVERAGE(fact_forecast[forecast_lower_80]),
        fact_forecast[target] = ""temperatura_media""
   )",
   "0.0 \"°C\"",
   "06 Forecasting",
   "Banda inferior 80% de confianza para temperatura");

Mt(fc, "Forecast Temp Upper",
   @"CALCULATE(
        AVERAGE(fact_forecast[forecast_upper_80]),
        fact_forecast[target] = ""temperatura_media""
   )",
   "0.0 \"°C\"",
   "06 Forecasting",
   "Banda superior 80% de confianza para temperatura");

// ─── 07. RANKINGS Y COMPARATIVOS ──────────────────────────────────────────
M("Ranking Temp",
  @"RANKX(
        ALL(dim_station[station_name]),
        [Temp Promedio],
        ,
        DESC,
        Dense
    )",
  "0",
  "07 Rankings",
  "Posición de la estación según temperatura promedio (1 = más caliente)");

M("Ranking ETP",
  @"RANKX(
        ALL(dim_station[station_name]),
        [ETP Acumulada],
        ,
        DESC,
        Dense
    )",
  "0",
  "07 Rankings",
  "Posición de la estación según ETP acumulada (1 = más demanda hídrica)");

M("Estación con Más Calor",
  @"VAR MaxStation =
      TOPN(1, ALL(dim_station[station_name]), [Temp Promedio], DESC)
    RETURN
    CONCATENATEX(MaxStation, dim_station[station_name])",
  "",
  "07 Rankings",
  "Nombre de la estación con mayor temperatura promedio");

// ─── DONE ─────────────────────────────────────────────────────────────────
Info(
    "✅ Climate Lakehouse PE: " +
    t.Measures.Count + " measures on fact_daily_summary, " +
    fc.Measures.Count + " measures on fact_forecast"
);
