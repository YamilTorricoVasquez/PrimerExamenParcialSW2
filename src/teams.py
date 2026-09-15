"""
teams.py
--------
Identificación de equipos a partir del color de camiseta detectado en cada
jugador (columnas color_r, color_g, color_b generadas por detect_track.py).

No requiere entrenar ningún modelo ni depender de un marcador en pantalla:
usa un k-means simple (implementado con numpy, sin dependencias extra)
sobre el color promedio de cada jugador a lo largo del video, y agrupa a
los jugadores en 2 equipos según ese color dominante.

El árbitro y eventuales colores atípicos pueden generar un tercer grupo
pequeño; este módulo se queda con los 2 clusters más grandes como los
"equipos" y trata el resto como no clasificado.
"""

from typing import Dict, Tuple

import numpy as np
import pandas as pd


def _kmeans_2(points: np.ndarray, n_iter: int = 25, seed: int = 42) -> np.ndarray:
    """
    K-means minimalista para 2 clusters, implementado con numpy puro
    (evita depender de scikit-learn solo para esto).

    Args:
        points: array (n_muestras, n_features), aquí colores RGB.

    Returns:
        array (n_muestras,) con la etiqueta de cluster (0 o 1) de cada punto.
    """
    rng = np.random.default_rng(seed)
    if len(points) < 2:
        return np.zeros(len(points), dtype=int)

    # Inicialización: dos puntos aleatorios distintos como centroides.
    idx = rng.choice(len(points), size=2, replace=False)
    centroids = points[idx].astype(float)

    labels = np.zeros(len(points), dtype=int)
    for _ in range(n_iter):
        distances = np.stack([
            np.linalg.norm(points - centroids[0], axis=1),
            np.linalg.norm(points - centroids[1], axis=1),
        ], axis=1)
        new_labels = np.argmin(distances, axis=1)

        if np.array_equal(new_labels, labels) and _ > 0:
            break
        labels = new_labels

        for k in (0, 1):
            cluster_points = points[labels == k]
            if len(cluster_points) > 0:
                centroids[k] = cluster_points.mean(axis=0)

    return labels


def assign_teams_by_color(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[int, Tuple[int, int, int]]]:
    """
    Agrupa a los jugadores (track_id) en 2 equipos según el color promedio
    de su camiseta a lo largo de todo el video (más estable que usar un
    solo fotograma).

    Devuelve:
        - El DataFrame original con una columna nueva 'team_cluster' (0 o 1).
        - Un diccionario {cluster_id: (r, g, b)} con el color representativo
          de cada equipo, útil para mostrar un "swatch" de color en el
          dashboard y que el entrenador confirme cuál es cuál.
    """
    df = df.copy()
    players = df[df["class"] == "person"]

    if players.empty:
        df["team_cluster"] = -1
        return df, {}

    # Color promedio POR JUGADOR (no por detección individual) — más
    # robusto ante ruido de un fotograma puntual mal iluminado.
    player_colors = players.groupby("track_id")[["color_r", "color_g", "color_b"]].mean()

    if len(player_colors) < 2:
        # Solo se detectó un jugador o ninguno: no hay nada que agrupar.
        df["team_cluster"] = 0
        return df, {0: tuple(player_colors.iloc[0].astype(int)) if len(player_colors) else (128, 128, 128)}

    labels = _kmeans_2(player_colors.values)
    track_id_to_cluster = dict(zip(player_colors.index, labels))

    df["team_cluster"] = df["track_id"].map(track_id_to_cluster).fillna(-1).astype(int)

    representative_colors = {}
    for cluster_id in (0, 1):
        cluster_track_ids = [tid for tid, c in track_id_to_cluster.items() if c == cluster_id]
        if cluster_track_ids:
            colors = player_colors.loc[cluster_track_ids].mean()
            representative_colors[cluster_id] = (int(colors["color_r"]), int(colors["color_g"]), int(colors["color_b"]))

    return df, representative_colors


def rename_teams(df: pd.DataFrame, cluster_to_name: Dict[int, str]) -> pd.DataFrame:
    """
    Reemplaza los IDs de cluster (0/1) por los nombres de equipo reales que
    escribió el entrenador (ej. {0: 'Local', 1: 'Visitante'}).
    """
    df = df.copy()
    df["team_name"] = df["team_cluster"].map(cluster_to_name).fillna("Sin clasificar")
    return df


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convierte una tupla RGB (0-255) a formato hexadecimal para mostrar en HTML/CSS."""
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"
