"""
Station configuration for Climate Lakehouse PE.

Defines 4 SYNTHETIC weather stations representing typical climate zones
of northern Peru (without referencing any specific real location).

All stations are FICTITIOUS. Coordinates are illustrative regional points
in northern Peru with offsets applied; they do not correspond to any real
station, fundo, or facility. Climate parameters are synthetically generated
based on published regional climate normals.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StationConfig:
    """Climate parameters for a synthetic weather station."""
    station_id: str
    name: str
    zone: str
    latitude: float
    longitude: float
    altitude_m: int

    # Annual temperature baseline (°C)
    temp_annual_mean: float
    temp_annual_amplitude: float    # peak-to-peak seasonal swing
    temp_daily_amplitude: float     # peak-to-peak diurnal swing

    # Humidity baseline (%)
    humidity_annual_mean: float
    humidity_annual_amplitude: float

    # Precipitation pattern (mm/year baseline, before El Niño shock)
    precip_annual_mm: float
    rainy_season_peak_month: int    # month of max rainfall (1-12)

    # Wind pattern
    wind_mean_kmh: float
    wind_dominant_dir: str

    # Solar / UV
    solar_max_wm2: float            # peak solar radiation at noon

    # Pressure (hPa) - depends mainly on altitude
    pressure_baseline: float


# 4 stations spanning typical climate zones of northern Peru's
# agroindustrial corridor. Names are descriptive of climate zone,
# not geographic location.
STATIONS = [
    StationConfig(
        station_id="STN_CN_01",
        name="Estación Costa Norte",
        zone="Costa Norte semi-árida",
        latitude=-6.10,
        longitude=-79.85,
        altitude_m=170,
        temp_annual_mean=24.5,
        temp_annual_amplitude=6.0,
        temp_daily_amplitude=11.0,
        humidity_annual_mean=68.0,
        humidity_annual_amplitude=12.0,
        precip_annual_mm=180.0,
        rainy_season_peak_month=2,
        wind_mean_kmh=8.5,
        wind_dominant_dir="W",
        solar_max_wm2=1100.0,
        pressure_baseline=1010.0,
    ),
    StationConfig(
        station_id="STN_VC_02",
        name="Estación Valle Central",
        zone="Valle Bajo Costero",
        latitude=-4.95,
        longitude=-80.85,
        altitude_m=80,
        temp_annual_mean=25.8,
        temp_annual_amplitude=5.0,
        temp_daily_amplitude=9.0,
        humidity_annual_mean=72.0,
        humidity_annual_amplitude=10.0,
        precip_annual_mm=120.0,
        rainy_season_peak_month=2,
        wind_mean_kmh=10.0,
        wind_dominant_dir="SW",
        solar_max_wm2=1080.0,
        pressure_baseline=1012.0,
    ),
    StationConfig(
        station_id="STN_VI_03",
        name="Estación Valle Interior",
        zone="Valle Medio Interior",
        latitude=-5.25,
        longitude=-80.55,
        altitude_m=29,
        temp_annual_mean=26.2,
        temp_annual_amplitude=4.5,
        temp_daily_amplitude=10.0,
        humidity_annual_mean=70.0,
        humidity_annual_amplitude=11.0,
        precip_annual_mm=110.0,
        rainy_season_peak_month=2,
        wind_mean_kmh=9.0,
        wind_dominant_dir="S",
        solar_max_wm2=1090.0,
        pressure_baseline=1013.0,
    ),
    StationConfig(
        station_id="STN_PA_04",
        name="Estación Pre-Andina",
        zone="Estribación Pre-Andina",
        latitude=-5.25,
        longitude=-79.90,
        altitude_m=140,
        temp_annual_mean=23.8,
        temp_annual_amplitude=5.5,
        temp_daily_amplitude=12.0,
        humidity_annual_mean=65.0,
        humidity_annual_amplitude=14.0,
        precip_annual_mm=380.0,
        rainy_season_peak_month=3,
        wind_mean_kmh=7.5,
        wind_dominant_dir="SE",
        solar_max_wm2=1070.0,
        pressure_baseline=1010.5,
    ),
]


def get_station(station_id: str) -> StationConfig:
    """Lookup a station by ID."""
    for s in STATIONS:
        if s.station_id == station_id:
            return s
    raise ValueError(f"Unknown station: {station_id}")
