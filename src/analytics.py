"""
analytics.py
------------
A partir del CSV de tracking (generado por detect_track.py) y, opcionalmente,
la homografía de campo (homography.py), calcula métricas útiles para el
cuerpo técnico:

- Distancia total recorrida por jugador
- Velocidad estimada (instantánea y máxima) por jugador
- Datos de posición listos para graficar mapas de calor

Este módulo NO requiere entrenar ningún modelo: son cálculos estadísticos
directos sobre las posiciones ya detectadas.
"""

import numpy as np
import pandas as pd

from homography import compute_homography_matrix, pixel_to_field


def load_tracking_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    return df


def add_field_coordinates(df: pd.DataFrame, homography_matrix: np.ndarray | None = None) -> pd.DataFrame:
    """
    Añade columnas x_field, y_field (en metros) a partir de x_center, y_center
    (en píxeles), usando la homografía calibrada.

    Si no se provee una homografía, usa la de ejemplo definida en
    homography.py — ADVERTENCIA: los resultados en metros no serán reales
    hasta que calibres los puntos para tu propio video.
    """
    if homography_matrix is None:
        homography_matrix = compute_homography_matrix()

    field_coords = df.apply(
        lambda row: pixel_to_field(row["x_center"], row["y_center"], homography_matrix),
        axis=1,
        result_type="expand",
    )
    df["x_field"], df["y_field"] = field_coords[0], field_coords[1]
    return df


def compute_player_distance_and_speed(df: pd.DataFrame, fps: float = 25.0) -> pd.DataFrame:
    """
    Calcula, para cada jugador (track_id, clase "person"), la distancia
    recorrida (m) y velocidad (km/h) entre fotogramas consecutivos.

    Devuelve un DataFrame resumen con: track_id, distancia_total_m,
    velocidad_promedio_kmh, velocidad_max_kmh.
    """
    empty_result = pd.DataFrame(columns=["track_id", "distancia_total_m", "velocidad_promedio_kmh", "velocidad_max_kmh"])

    players = df[df["class"] == "person"].copy()
    if players.empty:
        return empty_result

    players = players.sort_values(["track_id", "frame"])

    summary_rows = []
    for track_id, group in players.groupby("track_id"):
        group = group.sort_values("frame")
        dx = group["x_field"].diff()
        dy = group["y_field"].diff()
        dt_frames = group["frame"].diff()
        dt_seconds = dt_frames / fps

        dist_m = np.sqrt(dx**2 + dy**2)
        speed_ms = dist_m / dt_seconds.replace(0, np.nan)
        speed_kmh = speed_ms * 3.6

        summary_rows.append({
            "track_id": track_id,
            "distancia_total_m": np.nansum(dist_m),
            "velocidad_promedio_kmh": np.nanmean(speed_kmh) if len(speed_kmh.dropna()) else 0.0,
            "velocidad_max_kmh": np.nanmax(speed_kmh) if len(speed_kmh.dropna()) else 0.0,
        })

    if not summary_rows:
        return empty_result

    return pd.DataFrame(summary_rows).sort_values("track_id").reset_index(drop=True)


def get_heatmap_points(df: pd.DataFrame, track_id: int | None = None) -> pd.DataFrame:
    """
    Devuelve las coordenadas de campo (x_field, y_field) para graficar un
    mapa de calor. Si track_id es None, devuelve las posiciones de TODOS
    los jugadores (heatmap de equipo); si se especifica, solo ese jugador
    (heatmap individual).
    """
    players = df[df["class"] == "person"]
    if track_id is not None:
        players = players[players["track_id"] == track_id]
    return players[["x_field", "y_field"]].dropna()


# NOTA: la identificación de equipo por color de camiseta ya está
# implementada en teams.py (assign_teams_by_color), no aquí.


def classify_field_zone(avg_x_field: float, field_length_m: float = 105.0) -> str:
    """
    Clasifica la posición promedio de un jugador en un tercio del campo
    (según el eje X de las coordenadas calibradas). Esto es solo
    informativo — NO indica una posición táctica real (lateral, delantero,
    etc.), ya que no sabemos hacia qué lado ataca cada equipo. Se etiqueta
    de forma neutral a propósito.
    """
    if pd.isna(avg_x_field):
        return "Sin datos"
    third = field_length_m / 3
    if avg_x_field < third:
        return "Tercio A del campo"
    elif avg_x_field < 2 * third:
        return "Tercio medio del campo"
    else:
        return "Tercio B del campo"


def classify_activity_level(distance_m: float, minutes_analyzed: float) -> str:
    """
    Traduce la distancia recorrida a una categoría en lenguaje simple para
    el entrenador, en vez de mostrar solo un número técnico.

    Los umbrales (m/min) son una referencia orientativa basada en cargas
    típicas de jugadores de campo en fútbol amateur/semiprofesional —
    ajústalos según la categoría/edad de tus jugadores si hace falta.
    """
    if minutes_analyzed <= 0:
        return "Sin datos suficientes"

    m_per_min = distance_m / minutes_analyzed

    if m_per_min >= 110:
        return "Alto"
    elif m_per_min >= 70:
        return "Medio"
    else:
        return "Bajo"


def compute_fatigue_indicator(df: pd.DataFrame, fps: float = 25.0, drop_threshold_pct: float = 20.0) -> pd.DataFrame:
    """
    Compara la distancia recorrida por cada jugador en la primera mitad del
    video analizado contra la segunda mitad, para señalar una posible baja
    de rendimiento físico (lenguaje simple, sin diagnosticar nada médico).

    Devuelve un DataFrame con: track_id, distancia_primera_mitad_m,
    distancia_segunda_mitad_m, caida_pct, alerta_fatiga (True/False).
    """
    players = df[df["class"] == "person"].copy()
    if players.empty:
        return pd.DataFrame(columns=["track_id", "distancia_primera_mitad_m",
                                      "distancia_segunda_mitad_m", "caida_pct", "alerta_fatiga"])

    mid_frame = players["frame"].max() / 2
    first_half = players[players["frame"] <= mid_frame]
    second_half = players[players["frame"] > mid_frame]

    first_summary = compute_player_distance_and_speed(first_half, fps=fps)[["track_id", "distancia_total_m"]]
    second_summary = compute_player_distance_and_speed(second_half, fps=fps)[["track_id", "distancia_total_m"]]

    merged = first_summary.merge(second_summary, on="track_id", how="outer",
                                  suffixes=("_primera", "_segunda")).fillna(0)
    merged = merged.rename(columns={
        "distancia_total_m_primera": "distancia_primera_mitad_m",
        "distancia_total_m_segunda": "distancia_segunda_mitad_m",
    })

    merged["caida_pct"] = np.where(
        merged["distancia_primera_mitad_m"] > 0,
        (1 - merged["distancia_segunda_mitad_m"] / merged["distancia_primera_mitad_m"]) * 100,
        0.0,
    )
    merged["alerta_fatiga"] = merged["caida_pct"] >= drop_threshold_pct

    return merged.sort_values("track_id").reset_index(drop=True)
