"""
Meteorological derived variables.

Implements internationally recognized formulas:
- Dew point: Magnus-Tetens approximation
- Heat Index: NWS Rothfusz regression
- Wind Chill: NWS formula (only valid below 10°C)
- THW Index: Heat Index adjusted for wind
- THSW Index: THW adjusted for solar radiation
- Air density: ideal gas law with humidity correction
- ETP (Reference Evapotranspiration): FAO-56 Penman-Monteith
"""

import numpy as np


def dew_point_c(temp_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """
    Dew point in Celsius using Magnus-Tetens formula.
    Valid range: temp -45°C to +60°C, RH 1% to 100%.
    """
    a, b = 17.625, 243.04
    rh = np.clip(rh_pct, 1, 100) / 100.0
    alpha = np.log(rh) + (a * temp_c) / (b + temp_c)
    return (b * alpha) / (a - alpha)


def heat_index_c(temp_c: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """
    Heat Index (apparent temperature) in Celsius.
    NWS Rothfusz regression. Only meaningful when temp > 26.7°C.
    Below that threshold, returns the actual temperature.
    """
    # Convert to Fahrenheit for the standard formula
    t_f = temp_c * 9/5 + 32
    rh = rh_pct

    # Simple formula first (Steadman)
    hi_simple = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))

    # If average ≥ 80°F, use the full Rothfusz regression
    avg = (hi_simple + t_f) / 2
    use_full = avg >= 80

    hi_full = (-42.379
               + 2.04901523 * t_f
               + 10.14333127 * rh
               - 0.22475541 * t_f * rh
               - 0.00683783 * t_f**2
               - 0.05481717 * rh**2
               + 0.00122874 * t_f**2 * rh
               + 0.00085282 * t_f * rh**2
               - 0.00000199 * t_f**2 * rh**2)

    # Adjustments
    # Low humidity adjustment
    low_hum_mask = (rh < 13) & (t_f >= 80) & (t_f <= 112)
    # Guard sqrt against negatives (only valid where mask is true,
    # but np.where computes both branches)
    sqrt_arg = np.maximum(0, (17 - np.abs(t_f - 95)) / 17)
    adj_low = ((13 - rh) / 4) * np.sqrt(sqrt_arg)
    hi_full = np.where(low_hum_mask, hi_full - adj_low, hi_full)

    # High humidity adjustment
    high_hum_mask = (rh > 85) & (t_f >= 80) & (t_f <= 87)
    adj_high = ((rh - 85) / 10) * ((87 - t_f) / 5)
    hi_full = np.where(high_hum_mask, hi_full + adj_high, hi_full)

    hi_f = np.where(use_full, hi_full, hi_simple)

    # Below threshold, just return temp
    hi_f = np.where(t_f < 80, t_f, hi_f)

    # Back to Celsius
    return (hi_f - 32) * 5/9


def wind_chill_c(temp_c: np.ndarray, wind_kmh: np.ndarray) -> np.ndarray:
    """
    Wind Chill in Celsius. NWS formula.
    Only valid for temp ≤ 10°C and wind ≥ 4.8 km/h.
    Outside that range, returns actual temperature.
    """
    valid = (temp_c <= 10) & (wind_kmh >= 4.8)
    wc = (13.12
          + 0.6215 * temp_c
          - 11.37 * (wind_kmh ** 0.16)
          + 0.3965 * temp_c * (wind_kmh ** 0.16))
    return np.where(valid, wc, temp_c)


def thw_index_c(temp_c, rh_pct, wind_kmh):
    """
    THW Index = Heat Index adjusted for wind cooling.
    Approximation: HI - cooling_from_wind.
    """
    hi = heat_index_c(temp_c, rh_pct)
    # Wind cooling (very approximate Davis methodology)
    wind_cooling = 1.072 * wind_kmh / 10.0
    return hi - wind_cooling


def thsw_index_c(temp_c, rh_pct, wind_kmh, solar_wm2):
    """
    THSW Index = THW + solar heating contribution.
    Solar heating: roughly 0.025°C per W/m² (typical Davis approximation).
    """
    thw = thw_index_c(temp_c, rh_pct, wind_kmh)
    solar_heating = solar_wm2 * 0.025 * 0.5  # 0.5 = body absorption coeff
    return thw + solar_heating


def air_density_kg_m3(temp_c, pressure_hpa, rh_pct):
    """
    Air density (kg/m³) from temp, pressure, and humidity.
    Uses ideal gas law with vapor pressure correction.
    """
    t_k = temp_c + 273.15
    # Saturation vapor pressure (Tetens)
    es_hpa = 6.1078 * np.exp((17.27 * temp_c) / (temp_c + 237.3))
    # Actual vapor pressure
    e_hpa = es_hpa * (rh_pct / 100.0)
    # Partial pressure of dry air
    pd_hpa = pressure_hpa - e_hpa
    # Density
    Rd = 287.058  # J/(kg·K) dry air
    Rv = 461.495  # J/(kg·K) water vapor
    return (pd_hpa * 100) / (Rd * t_k) + (e_hpa * 100) / (Rv * t_k)


def degree_days(temp_c: np.ndarray, base_c: float, mode: str) -> np.ndarray:
    """
    Heating Degree Days (HDD) or Cooling Degree Days (CDD).
    For agriculture: CDD with base 10°C is a common growing-degree proxy.
    """
    if mode == "heat":
        return np.maximum(0, base_c - temp_c) / 48  # per 30-min step
    elif mode == "cool":
        return np.maximum(0, temp_c - base_c) / 48
    raise ValueError("mode must be 'heat' or 'cool'")


def etp_penman_monteith_30min(
    temp_c, rh_pct, wind_kmh, solar_wm2, pressure_hpa, altitude_m
):
    """
    Reference Evapotranspiration (mm per 30-min interval) using
    a simplified FAO-56 Penman-Monteith adapted for sub-daily intervals.

    This is the KEY metric for agricultural water management.

    Note: FAO-56 PM is technically defined for hourly/daily intervals.
    Here we apply it per 30-min step, scaling solar and wind appropriately.
    Real systems would use hourly aggregates; this approximation works
    well for our synthetic context.
    """
    # Convert wind to m/s
    u2 = wind_kmh / 3.6

    # Saturation vapor pressure (kPa)
    es = 0.6108 * np.exp((17.27 * temp_c) / (temp_c + 237.3))
    # Actual vapor pressure
    ea = es * (rh_pct / 100.0)

    # Slope of vapor pressure curve (kPa/°C)
    delta = (4098 * es) / ((temp_c + 237.3) ** 2)

    # Pressure in kPa
    p_kpa = pressure_hpa / 10.0

    # Psychrometric constant (kPa/°C)
    gamma = 0.000665 * p_kpa

    # Net radiation approximation (MJ/m²/30min)
    # Solar W/m² → MJ/m²/30min: × 1800s × 1e-6
    rs_mj = solar_wm2 * 1800 * 1e-6
    # Approximate net shortwave (albedo 0.23)
    rns = (1 - 0.23) * rs_mj
    # Net longwave (very simplified for sub-daily)
    rnl = 0.0  # negligible at 30-min scale for our purposes
    rn = rns - rnl

    # Soil heat flux (small fraction of Rn)
    g_factor = np.where(solar_wm2 > 0, 0.1, 0.5)  # daytime vs nighttime
    g = g_factor * rn

    # FAO-56 Penman-Monteith for short reference (grass)
    # ET (mm/30min)
    numerator = (0.408 * delta * (rn - g)
                 + gamma * (37 / (temp_c + 273)) * u2 * (es - ea))
    denominator = delta + gamma * (1 + 0.34 * u2)

    et = numerator / denominator
    # Scale: above formula is typically for hourly; for 30-min we already
    # used 30-min Rs. Result is mm/30min directly.
    return np.maximum(0, et)
