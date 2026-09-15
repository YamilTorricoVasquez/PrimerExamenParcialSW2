"""
reports.py
----------
Genera contenido "amigable" para el entrenador y los jugadores a partir de
las métricas ya calculadas:

- Un resumen de texto del partido (basado en plantillas + los números
  reales, NO usa un modelo de lenguaje — así funciona sin conexión a
  ninguna API externa y sin costo adicional).
- Una ficha individual en PDF por jugador, descargable/imprimible.
"""

from typing import Dict, Optional

import pandas as pd
from fpdf import FPDF

from analytics import classify_activity_level


def generate_match_summary(
    player_summary: pd.DataFrame,
    fatigue_df: pd.DataFrame,
    team_names: Dict[int, str],
    minutes_analyzed: float,
) -> str:
    """
    Arma un párrafo de resumen del partido en lenguaje natural simple,
    usando los datos ya calculados (sin IA generativa — es texto basado en
    plantillas con los números reales insertados).
    """
    if player_summary.empty:
        return "No se detectaron suficientes datos en este video para generar un resumen."

    total_players = len(player_summary)
    top_distance_row = player_summary.loc[player_summary["distancia_total_m"].idxmax()]
    top_speed_row = player_summary.loc[player_summary["velocidad_max_kmh"].idxmax()]

    lines = []
    lines.append(
        f"Se analizaron {minutes_analyzed:.0f} minutos de video con {total_players} "
        f"jugadores identificados."
    )
    lines.append(
        f"El jugador con mayor recorrido fue el #{int(top_distance_row['track_id'])}, "
        f"con {top_distance_row['distancia_total_m']:.0f} metros."
    )
    lines.append(
        f"La velocidad máxima registrada en el partido fue de "
        f"{top_speed_row['velocidad_max_kmh']:.1f} km/h, alcanzada por el jugador "
        f"#{int(top_speed_row['track_id'])}."
    )

    if fatigue_df is not None and not fatigue_df.empty:
        fatigued = fatigue_df[fatigue_df["alerta_fatiga"]]
        if not fatigued.empty:
            ids = ", ".join(f"#{int(t)}" for t in fatigued["track_id"])
            lines.append(
                f"⚠️ Se detectó una baja notable de actividad física en la segunda mitad "
                f"del video para el/los jugador(es) {ids} — puede valer la pena revisar "
                f"su condición física o rotación en próximos partidos."
            )
        else:
            lines.append("No se detectaron caídas notables de rendimiento entre la primera y segunda mitad del video analizado.")

    return " ".join(lines)


def generate_player_pdf(
    track_id: int,
    player_name: Optional[str],
    team_name: Optional[str],
    distance_m: float,
    avg_speed_kmh: float,
    max_speed_kmh: float,
    activity_level: str,
    minutes_analyzed: float,
    fatigue_alert: bool,
    heatmap_image_path: Optional[str] = None,
) -> bytes:
    """
    Genera una ficha individual en PDF para un jugador, lista para imprimir
    o compartir. Devuelve los bytes del PDF (para usar con
    st.download_button en el dashboard, sin necesidad de guardar a disco).
    """
    display_name = player_name if player_name else f"Jugador #{track_id}"

    pdf = FPDF(format="A4")
    pdf.add_page()

    # --- Encabezado ---
    pdf.set_fill_color(30, 90, 50)
    pdf.rect(0, 0, 210, 30, style="F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_xy(10, 8)
    pdf.cell(0, 10, "Ficha de Rendimiento", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_xy(10, 18)
    subtitle = display_name if not team_name else f"{display_name}  |  {team_name}"
    pdf.cell(0, 8, subtitle, ln=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_y(38)

    # --- Nivel de actividad (badge grande y simple) ---
    level_colors = {"Alto": (46, 139, 87), "Medio": (230, 168, 0), "Bajo": (200, 60, 60)}
    badge_color = level_colors.get(activity_level, (120, 120, 120))
    pdf.set_fill_color(*badge_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(60, 12, f"  Actividad: {activity_level}", fill=True, align="L")
    pdf.ln(20)

    # --- Métricas clave ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Métricas del video analizado", ln=True)
    pdf.set_font("Helvetica", "", 12)

    rows = [
        ("Tiempo analizado", f"{minutes_analyzed:.0f} minutos"),
        ("Distancia total recorrida", f"{distance_m:.0f} metros"),
        ("Velocidad promedio", f"{avg_speed_kmh:.1f} km/h"),
        ("Velocidad máxima", f"{max_speed_kmh:.1f} km/h"),
    ]
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(70, 9, label, border=0)
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 9, value, ln=True)

    pdf.ln(4)

    if fatigue_alert:
        pdf.set_fill_color(255, 235, 235)
        pdf.set_text_color(180, 40, 40)
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 8,
            "Se observó una baja notable de actividad en la segunda mitad del "
            "video analizado respecto a la primera. Vale la pena revisar condición "
            "física o carga de minutos.",
            fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

    # --- Mapa de calor (si se generó una imagen) ---
    if heatmap_image_path:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Mapa de posiciones en el campo", ln=True)
        pdf.image(heatmap_image_path, x=25, w=160)

    pdf.set_y(-15)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 10, "Generado automáticamente - Sistema de Análisis Predictivo de Fútbol (proyecto académico)", align="C")

    return bytes(pdf.output())
