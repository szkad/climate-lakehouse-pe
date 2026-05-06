"""
Climate patterns for synthetic data generation.

Implements:
- Annual seasonality (sinusoidal)
- Diurnal cycle (temperature peaks ~14:00, mins ~05:00)
- El Niño shock periods (2023 Coastal + 2023-24 Global)
- Realistic noise and autocorrelation
"""

import numpy as np
import pandas as pd
from datetime import datetime
from .stations import StationConfig


# El Niño event windows (start, end, intensity_factor)
# Intensity 0.0 = normal, 1.0 = strong El Niño
# Based on documented events:
# - El Niño Costero 2023 (Mar-May 2023, includes Cyclone Yaku)
# - El Niño Global 2023-2024 (Jun 2023 - May 2024)
EL_NINO_EVENTS = [
    {
        "name": "El Niño Costero 2023 (Yaku)",
        "start": pd.Timestamp("2023-03-01"),
        "end": pd.Timestamp("2023-05-15"),
        "temp_anomaly_c": 2.8,        # +°C above normal
        "humidity_anomaly_pct": 8.0,  # more humid
        "precip_multiplier": 5.5,     # heavy rains
    },
    {
        "name": "El Niño Global 2023-2024",
        "start": pd.Timestamp("2023-06-01"),
        "end": pd.Timestamp("2024-05-31"),
        "temp_anomaly_c": 1.4,
        "humidity_anomaly_pct": 4.0,
        "precip_multiplier": 2.2,
    },
]


def el_nino_factor(timestamps: pd.DatetimeIndex) -> dict:
    """
    Return per-timestamp climate anomaly factors due to El Niño events.

    Returns a dict with arrays: temp_anomaly, humidity_anomaly, precip_mult.
    Values smoothly ramp up/down at event boundaries to avoid sharp jumps.
    """
    n = len(timestamps)
    temp_anom = np.zeros(n)
    hum_anom = np.zeros(n)
    precip_mult = np.ones(n)

    ramp_days = 14  # smooth boundary

    for event in EL_NINO_EVENTS:
        start = event["start"]
        end = event["end"]
        ramp = pd.Timedelta(days=ramp_days)

        # Build a smooth weight: 0 outside, 1 inside, linear ramps
        w = np.zeros(n)
        in_event = (timestamps >= start) & (timestamps <= end)
        w[in_event] = 1.0

        # Ramp up
        ramp_up = (timestamps >= start - ramp) & (timestamps < start)
        if ramp_up.any():
            days_to_start = (start - timestamps[ramp_up]).total_seconds() / 86400
            w[ramp_up] = 1.0 - (days_to_start / ramp_days)

        # Ramp down
        ramp_dn = (timestamps > end) & (timestamps <= end + ramp)
        if ramp_dn.any():
            days_after = (timestamps[ramp_dn] - end).total_seconds() / 86400
            w[ramp_dn] = 1.0 - (days_after / ramp_days)

        temp_anom += w * event["temp_anomaly_c"]
        hum_anom += w * event["humidity_anomaly_pct"]
        precip_mult += w * (event["precip_multiplier"] - 1.0)

    return {
        "temp_anomaly": temp_anom,
        "humidity_anomaly": hum_anom,
        "precip_multiplier": precip_mult,
    }


def seasonal_temperature(
    timestamps: pd.DatetimeIndex,
    station: StationConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generate temperature series with:
    - Annual cycle (warmest Jan-Mar, coolest Jul-Aug in southern hemisphere)
    - Diurnal cycle (peak ~14:00, min ~05:00)
    - El Niño anomalies
    - Daily-level noise (autoregressive)
    - Sub-daily noise (small)
    """
    day_of_year = timestamps.dayofyear.to_numpy()
    hour_of_day = timestamps.hour.to_numpy() + timestamps.minute.to_numpy() / 60.0

    # Annual cycle: warmest at austral summer (around Feb 15, doy=46)
    # Phase shifted so peak is at doy ~46
    annual_phase = 2 * np.pi * (day_of_year - 46) / 365.25
    annual = (station.temp_annual_amplitude / 2) * np.cos(annual_phase)

    # Diurnal cycle: minimum ~05:00, maximum ~14:00
    # Phase shift so peak is at hour 14
    diurnal_phase = 2 * np.pi * (hour_of_day - 14) / 24
    diurnal = (station.temp_daily_amplitude / 2) * np.cos(diurnal_phase)

    base = station.temp_annual_mean + annual + diurnal

    # El Niño anomaly
    enso = el_nino_factor(timestamps)
    base = base + enso["temp_anomaly"]

    # Daily-level noise (autocorrelated) - simulates weather fronts
    n = len(timestamps)
    daily_noise = _ar1_noise(n, rho=0.95, sigma=0.8, rng=rng)

    # Sub-daily noise (small, uncorrelated)
    fast_noise = rng.normal(0, 0.25, n)

    return base + daily_noise + fast_noise


def seasonal_humidity(
    timestamps: pd.DatetimeIndex,
    station: StationConfig,
    temp_series: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generate humidity series. Inversely correlated with temperature.
    Higher humidity at night and during rainy season.
    """
    day_of_year = timestamps.dayofyear.to_numpy()
    hour_of_day = timestamps.hour.to_numpy() + timestamps.minute.to_numpy() / 60.0

    annual_phase = 2 * np.pi * (day_of_year - 60) / 365.25
    annual = (station.humidity_annual_amplitude / 2) * np.cos(annual_phase)

    # Diurnal: max at dawn (05:00), min at noon (14:00) - inverse of temp
    diurnal_phase = 2 * np.pi * (hour_of_day - 5) / 24
    diurnal = 8.0 * np.cos(diurnal_phase)

    base = station.humidity_annual_mean + annual + diurnal

    # Coupling with temperature: higher temp → lower humidity
    temp_dev = temp_series - station.temp_annual_mean
    humidity_from_temp = -1.5 * temp_dev

    # El Niño humidity anomaly
    enso = el_nino_factor(timestamps)
    base = base + enso["humidity_anomaly"]

    n = len(timestamps)
    noise = _ar1_noise(n, rho=0.92, sigma=2.0, rng=rng)

    result = base + humidity_from_temp + noise
    return np.clip(result, 15, 100)  # physical bounds


def precipitation_series(
    timestamps: pd.DatetimeIndex,
    station: StationConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generate 30-min precipitation series (mm).

    Most timesteps have 0 precipitation. Rainfall is bursty:
    - Probability of rain depends on season + El Niño
    - When it rains, amount follows exponential distribution
    - During El Niño Costero, inject ~6-10 torrential storm events
      with concentrated 30-min bursts (matches real Yaku behavior)
    """
    n = len(timestamps)
    day_of_year = timestamps.dayofyear.to_numpy()

    # Seasonal probability of rain (peaks at rainy_season_peak_month)
    peak_doy = (station.rainy_season_peak_month - 1) * 30 + 15
    season_phase = 2 * np.pi * (day_of_year - peak_doy) / 365.25
    rain_prob_base = 0.005 + 0.020 * np.maximum(0, np.cos(season_phase))

    # El Niño multiplier
    enso = el_nino_factor(timestamps)
    rain_prob = rain_prob_base * enso["precip_multiplier"]
    rain_prob = np.clip(rain_prob, 0, 0.5)

    # Roll for rain
    rains = rng.random(n) < rain_prob

    # When it rains, sample amount (exponential)
    mean_mm = (station.precip_annual_mm / 5000) * enso["precip_multiplier"]
    amounts = rng.exponential(scale=mean_mm, size=n)

    precip = np.where(rains, amounts, 0.0)

    # ─── INJECT TORRENTIAL STORMS during El Niño Costero ─────────────
    # Yaku and similar events: 30-100mm in a few hours
    yaku_start = pd.Timestamp("2023-03-01")
    yaku_end = pd.Timestamp("2023-05-15")
    in_yaku = (timestamps >= yaku_start) & (timestamps <= yaku_end)
    yaku_indices = np.where(in_yaku)[0]

    if len(yaku_indices) > 0:
        # 8 torrential storms during the Yaku window
        # Pre-Andina gets more storms (foothills amplify Niño rain)
        n_storms = 12 if station.precip_annual_mm > 300 else 7
        storm_starts = rng.choice(yaku_indices, n_storms, replace=False)
        for s_idx in storm_starts:
            # Storm lasts 4-8 30-min periods (2-4 hours)
            duration = rng.integers(4, 9)
            end_idx = min(s_idx + duration, n)
            # Each interval gets 5-25mm
            storm_intensity = rng.uniform(8, 25, end_idx - s_idx)
            precip[s_idx:end_idx] += storm_intensity

    return precip



def solar_radiation(
    timestamps: pd.DatetimeIndex,
    station: StationConfig,
    humidity: np.ndarray,
    precip: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generate solar radiation (W/m²).
    Zero at night, peak at solar noon, attenuated by clouds (high humidity).
    """
    hour_of_day = timestamps.hour.to_numpy() + timestamps.minute.to_numpy() / 60.0
    day_of_year = timestamps.dayofyear.to_numpy()

    # Solar elevation proxy: 0 at night, 1 at noon
    # Sunrise ~06:00, sunset ~18:00 in tropics
    is_day = (hour_of_day >= 6.0) & (hour_of_day <= 18.0)
    solar_angle = np.where(
        is_day,
        np.sin(np.pi * (hour_of_day - 6.0) / 12.0),
        0.0
    )

    # Seasonal modulation (slight in tropics)
    season_phase = 2 * np.pi * (day_of_year - 80) / 365.25
    season_mult = 1.0 + 0.10 * np.cos(season_phase)

    base = station.solar_max_wm2 * solar_angle * season_mult

    # Cloud attenuation: high humidity reduces radiation
    cloud_factor = np.clip(1.0 - (humidity - 60) / 100, 0.4, 1.0)

    # Heavy rain blocks even more
    rain_attenuation = np.where(precip > 0.5, 0.3, 1.0)

    # Random cloud noise during day
    n = len(timestamps)
    cloud_noise = np.where(is_day, rng.uniform(0.7, 1.0, n), 1.0)

    result = base * cloud_factor * rain_attenuation * cloud_noise
    return np.maximum(0, result)


def wind_series(
    timestamps: pd.DatetimeIndex,
    station: StationConfig,
    rng: np.random.Generator,
) -> tuple:
    """
    Generate wind speed (km/h), direction (16-pt), and gust (km/h).
    Wind tends to be stronger during day (thermal mixing).
    Includes 4-8 extreme wind events per year (vendavales).
    """
    n = len(timestamps)
    hour_of_day = timestamps.hour.to_numpy() + timestamps.minute.to_numpy() / 60.0

    # Diurnal: stronger during day (12-16h), calmer at night
    diurnal = 1.0 + 0.5 * np.sin(np.pi * np.clip((hour_of_day - 6) / 12, 0, 1))
    diurnal = np.where((hour_of_day >= 6) & (hour_of_day <= 18), diurnal, 0.6)

    base = station.wind_mean_kmh * diurnal
    noise = _ar1_noise(n, rho=0.85, sigma=2.5, rng=rng)
    speed = np.maximum(0, base + noise)

    # Gust = speed * factor (1.3-1.8)
    gust_factor = rng.uniform(1.2, 1.7, n)
    gust = speed * gust_factor

    # ─── INJECT EXTREME WIND EVENTS (vendavales) ────────────────────
    # 5-7 per year, lasting 2-4 hours (4-8 30-min intervals)
    n_years = max(1, int(n / (48 * 365)))
    n_events = rng.integers(5, 8) * n_years
    event_starts = rng.choice(n, n_events, replace=False)
    for e_idx in event_starts:
        duration = rng.integers(4, 9)
        end_idx = min(e_idx + duration, n)
        # Boost wind: speed +15-25 km/h, gust +10-15 km/h on top
        boost = rng.uniform(15, 25, end_idx - e_idx)
        speed[e_idx:end_idx] += boost
        gust_boost = rng.uniform(10, 15, end_idx - e_idx)
        gust[e_idx:end_idx] = (speed[e_idx:end_idx]
                                * rng.uniform(1.4, 1.9, end_idx - e_idx)
                                + gust_boost)

    # Direction: dominant + variability
    dirs_16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    dominant_idx = dirs_16.index(station.wind_dominant_dir)
    direction_offsets = rng.integers(-3, 4, n)
    direction_idx = (dominant_idx + direction_offsets) % 16
    direction = np.array([dirs_16[i] for i in direction_idx])

    gust_offsets = rng.integers(-2, 3, n)
    gust_dir_idx = (direction_idx + gust_offsets) % 16
    gust_dir = np.array([dirs_16[i] for i in gust_dir_idx])

    return speed, direction, gust, gust_dir



def _ar1_noise(n: int, rho: float, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """
    Generate AR(1) autocorrelated noise. Used for daily weather variability.
    rho close to 1 → smooth, slow-changing (like real weather).
    """
    out = np.zeros(n)
    out[0] = rng.normal(0, sigma)
    innovation = rng.normal(0, sigma * np.sqrt(1 - rho**2), n)
    for i in range(1, n):
        out[i] = rho * out[i-1] + innovation[i]
    return out
