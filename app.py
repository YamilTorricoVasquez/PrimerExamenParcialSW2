"""
app.py
------
Backend Flask del dashboard de análisis de fútbol.

Arquitectura:
- El video se procesa en un hilo en segundo plano (threading.Thread) para
  que subir el video y ver el progreso no bloquee al servidor.
- El estado y los resultados de cada análisis se guardan en memoria en el
  diccionario JOBS, indexado por un job_id único.
- El frontend (templates/result.html) consulta /api/status/<job_id> cada
  pocos segundos para actualizar la barra de progreso, y una vez terminado
  pide los datos a /api/data/<job_id>.

LIMITACIÓN IMPORTANTE (documentar en la tesis): al guardar el estado en
memoria del proceso, este backend debe correr con UN SOLO worker/proceso
(ver Procfile: gunicorn --workers 1). Si se necesitara escalar a varios
workers o varias instancias, habría que mover JOBS a un almacenamiento
compartido (Redis, base de datos), lo cual queda fuera del alcance de
este proyecto académico.
"""

import os
import sys
import io
import json
import uuid
import shutil
import threading
import tempfile
from collections import Counter

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort

import matplotlib
matplotlib.use("Agg")  # backend sin interfaz gráfica, necesario en un servidor
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from detect_track import run_tracking, DEFAULT_MODEL_PATH
from homography import compute_homography_matrix
from analytics import (
    add_field_coordinates,
    compute_player_distance_and_speed,
    get_heatmap_points,
    classify_activity_level,
    classify_field_zone,
    compute_fatigue_indicator,
)
from teams import assign_teams_by_color, rename_teams, rgb_to_hex
from reports import generate_match_summary, generate_player_pdf

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB máximo de subida

BASE_TMP_DIR = os.path.join(tempfile.gettempdir(), "futbol_jobs")
os.makedirs(BASE_TMP_DIR, exist_ok=True)

# Estado de cada análisis en memoria. Ver limitación de un solo worker arriba.
JOBS = {}


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------
def _fig_to_png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _make_heatmap_png(points_df: pd.DataFrame) -> bytes:
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 68)
    ax.set_facecolor("#2e8b57")
    if not points_df.empty:
        sns.kdeplot(x=points_df["x_field"], y=points_df["y_field"],
                    fill=True, cmap="hot", alpha=0.65, ax=ax, thresh=0.05)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    return _fig_to_png_bytes(fig)


def _get_cluster_to_name(job: dict) -> dict:
    """Mapea cluster_id (0/1) -> nombre de equipo, respetando el swap si el usuario lo activó."""
    colors = job.get("team_colors", {})
    cluster_ids = sorted(colors.keys())
    swap = job.get("swap", False)

    if len(cluster_ids) >= 2:
        if swap:
            return {cluster_ids[0]: job["team_b_name"], cluster_ids[1]: job["team_a_name"]}
        return {cluster_ids[0]: job["team_a_name"], cluster_ids[1]: job["team_b_name"]}
    elif len(cluster_ids) == 1:
        return {cluster_ids[0]: job["team_a_name"]}
    return {}


# ---------------------------------------------------------------------------
# Procesamiento en segundo plano
# ---------------------------------------------------------------------------
def process_video_job(job_id, video_path, team_a_name, team_b_name, conf, vid_stride, fps, roster, try_jersey_ocr):
    job = JOBS[job_id]
    try:
        job["status"] = "processing"
        job["progress"] = 0
        output_csv = os.path.join(BASE_TMP_DIR, job_id, "tracking.csv")

        def progress_cb(current, total):
            job["progress"] = int(min(current / total, 1.0) * 90)  # deja 10% para el paso de nombres

        run_tracking(
            source=video_path, output_csv=output_csv, model_path=DEFAULT_MODEL_PATH,
            conf=conf, vid_stride=vid_stride, progress_callback=progress_cb,
        )
        df = pd.read_csv(output_csv)

        if df.empty:
            job["status"] = "error"
            job["error"] = ("No se detectaron jugadores ni balón en el video. "
                             "Prueba bajando el umbral de confianza o revisa que el "
                             "campo se vea con claridad.")
            return

        # OCR experimental de número de camiseta — se hace AQUÍ porque
        # todavía tenemos el video original en disco (se borra al final).
        jersey_guesses = {}
        if try_jersey_ocr:
            job["progress"] = 92
            try:
                from jersey_ocr import guess_jersey_numbers
                jersey_guesses = guess_jersey_numbers(video_path, df)
            except Exception:
                jersey_guesses = {}

        homography_matrix = compute_homography_matrix()
        df = add_field_coordinates(df, homography_matrix)
        df, team_colors = assign_teams_by_color(df)

        summary_df = compute_player_distance_and_speed(df, fps=fps)
        fatigue_df = compute_fatigue_indicator(df, fps=fps)

        total_frames = (df["frame"].max() - df["frame"].min()) if not df.empty else 0
        minutes_analyzed = (total_frames / fps) / 60 if fps > 0 else 0

        # Sugerir nombre automáticamente cuando el número leído coincide con la plantilla
        player_names = {}
        for track_id, number in jersey_guesses.items():
            if number in roster:
                player_names[track_id] = roster[number]

        job.update({
            "status": "done",
            "progress": 100,
            "df": df,
            "team_colors": team_colors,
            "summary_df": summary_df,
            "fatigue_df": fatigue_df,
            "minutes_analyzed": minutes_analyzed,
            "fps": fps,
            "team_a_name": team_a_name,
            "team_b_name": team_b_name,
            "swap": False,
            "roster": roster,
            "jersey_guesses": jersey_guesses,
            "player_names": player_names,
        })
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        # El video ya no hace falta en disco: los resultados quedan en memoria.
        shutil.rmtree(os.path.join(BASE_TMP_DIR, job_id), ignore_errors=True)


# ---------------------------------------------------------------------------
# Páginas HTML
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    video_file = request.files.get("video")
    if not video_file or video_file.filename == "":
        return render_template("index.html", error="Debes subir un video antes de analizar.")

    team_a_name = (request.form.get("team_a_name") or "Equipo A").strip() or "Equipo A"
    team_b_name = (request.form.get("team_b_name") or "Equipo B").strip() or "Equipo B"
    try:
        conf = float(request.form.get("conf", 0.3))
        vid_stride = int(request.form.get("vid_stride", 2))
        fps = float(request.form.get("fps", 25.0))
    except ValueError:
        conf, vid_stride, fps = 0.3, 2, 25.0

    try_jersey_ocr = request.form.get("try_jersey_ocr") == "on"

    roster = {}
    roster_raw = request.form.get("roster_json", "")
    if roster_raw:
        try:
            parsed = json.loads(roster_raw)
            for entry in parsed:
                number = str(entry.get("number", "")).strip()
                name = str(entry.get("name", "")).strip()
                if number and name:
                    roster[number] = name
        except (json.JSONDecodeError, AttributeError, TypeError):
            roster = {}

    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(BASE_TMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    video_path = os.path.join(job_dir, video_file.filename)
    video_file.save(video_path)

    JOBS[job_id] = {"status": "queued", "progress": 0, "error": None}

    thread = threading.Thread(
        target=process_video_job,
        args=(job_id, video_path, team_a_name, team_b_name, conf, vid_stride, fps, roster, try_jersey_ocr),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("result_page", job_id=job_id))


@app.route("/result/<job_id>")
def result_page(job_id):
    if job_id not in JOBS:
        abort(404)
    return render_template("result.html", job_id=job_id)


# ---------------------------------------------------------------------------
# API JSON (usada por el JavaScript del frontend)
# ---------------------------------------------------------------------------
@app.route("/api/scoreboard_suggest", methods=["POST"])
def api_scoreboard_suggest():
    """
    Endpoint experimental: recibe el video, intenta leer el marcador y
    devuelve sugerencias de texto. No falla nunca de forma ruidosa —
    si algo sale mal, simplemente devuelve una lista vacía.
    """
    video_file = request.files.get("video")
    if not video_file:
        return jsonify({"suggestions": []})

    tmp_path = os.path.join(tempfile.gettempdir(), f"scoreboard_{uuid.uuid4().hex}.mp4")
    video_file.save(tmp_path)
    suggestions = []
    try:
        from scoreboard_ocr import suggest_team_names_from_scoreboard
        suggestions = suggest_team_names_from_scoreboard(tmp_path)
    except Exception:
        suggestions = []
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return jsonify({"suggestions": suggestions})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": job["status"],
        "progress": job.get("progress", 0),
        "error": job.get("error"),
    })


@app.route("/api/swap/<job_id>", methods=["POST"])
def api_swap(job_id):
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "not_found"}), 404
    job["swap"] = not job.get("swap", False)
    return jsonify({"swap": job["swap"]})


@app.route("/api/player_names/<job_id>", methods=["POST"])
def api_player_names(job_id):
    """Guarda los nombres que el entrenador asignó manualmente a cada jugador."""
    job = JOBS.get(job_id)
    if job is None:
        return jsonify({"error": "not_found"}), 404

    payload = request.get_json(silent=True) or {}
    names = payload.get("names", {})

    updated = job.get("player_names", {})
    for track_id_str, name in names.items():
        try:
            track_id = int(track_id_str)
        except ValueError:
            continue
        name = (name or "").strip()
        if name:
            updated[track_id] = name
        else:
            updated.pop(track_id, None)

    job["player_names"] = updated
    return jsonify({"player_names": {str(k): v for k, v in updated.items()}})


@app.route("/api/data/<job_id>")
def api_data(job_id):
    job = JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        return jsonify({"error": "Resultado no disponible todavía."}), 404

    cluster_to_name = _get_cluster_to_name(job)
    df = rename_teams(job["df"], cluster_to_name)
    summary_df = job["summary_df"]
    fatigue_df = job["fatigue_df"]
    minutes_analyzed = job["minutes_analyzed"]

    summary_text = generate_match_summary(summary_df, fatigue_df, cluster_to_name, minutes_analyzed)
    colors_hex = {k: rgb_to_hex(v) for k, v in job["team_colors"].items()}
    player_names = job.get("player_names", {})
    jersey_guesses = job.get("jersey_guesses", {})
    roster_names = sorted(set(job.get("roster", {}).values()))

    players = []
    for _, row in summary_df.iterrows():
        tid = int(row["track_id"])
        cluster_series = df[df["track_id"] == tid]["team_cluster"]
        cluster_id = int(cluster_series.iloc[0]) if not cluster_series.empty else -1
        fatigue_row = fatigue_df[fatigue_df["track_id"] == tid]
        player_points = df[(df["track_id"] == tid) & (df["class"] == "person")]
        avg_x = player_points["x_field"].mean() if not player_points.empty else float("nan")

        players.append({
            "track_id": tid,
            "name": player_names.get(tid),
            "jersey_guess": jersey_guesses.get(tid),
            "team_name": cluster_to_name.get(cluster_id, "Sin equipo"),
            "team_color": colors_hex.get(cluster_id, "#888888"),
            "zone": classify_field_zone(avg_x),
            "distance_m": round(float(row["distancia_total_m"]), 1),
            "avg_speed_kmh": round(float(row["velocidad_promedio_kmh"]), 1),
            "max_speed_kmh": round(float(row["velocidad_max_kmh"]), 1),
            "activity_level": classify_activity_level(row["distancia_total_m"], minutes_analyzed),
            "fatigue_alert": bool(fatigue_row["alerta_fatiga"].iloc[0]) if not fatigue_row.empty else False,
        })
    players.sort(key=lambda p: p["distance_m"], reverse=True)

    teams_payload = [
        {"cluster_id": cid, "name": name, "color_hex": colors_hex.get(cid, "#888888")}
        for cid, name in cluster_to_name.items()
    ]

    # Comparación agregada por equipo (para la vista de comparación)
    team_comparison = []
    for cid, name in cluster_to_name.items():
        team_players = [p for p in players if p["team_name"] == name]
        total_distance = sum(p["distance_m"] for p in team_players)
        counts = Counter(p["activity_level"] for p in team_players)
        team_comparison.append({
            "name": name,
            "color_hex": colors_hex.get(cid, "#888888"),
            "player_count": len(team_players),
            "total_distance_m": round(total_distance, 0),
            "avg_distance_m": round(total_distance / len(team_players), 0) if team_players else 0,
            "activity_counts": {"Alto": counts.get("Alto", 0), "Medio": counts.get("Medio", 0), "Bajo": counts.get("Bajo", 0)},
        })

    return jsonify({
        "summary_text": summary_text,
        "minutes_analyzed": round(minutes_analyzed, 1),
        "teams": teams_payload,
        "team_comparison": team_comparison,
        "players": players,
        "roster_names": roster_names,
    })


@app.route("/image/team_heatmap/<job_id>/<int:cluster_id>.png")
def image_team_heatmap(job_id, cluster_id):
    job = JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        abort(404)
    points = get_heatmap_points(job["df"][job["df"]["team_cluster"] == cluster_id])
    return send_file(io.BytesIO(_make_heatmap_png(points)), mimetype="image/png")


@app.route("/image/player_heatmap/<job_id>/<int:track_id>.png")
def image_player_heatmap(job_id, track_id):
    job = JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        abort(404)
    points = get_heatmap_points(job["df"], track_id=track_id)
    return send_file(io.BytesIO(_make_heatmap_png(points)), mimetype="image/png")


@app.route("/download/pdf/<job_id>/<int:track_id>")
def download_pdf(job_id, track_id):
    job = JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        abort(404)

    cluster_to_name = _get_cluster_to_name(job)
    df = rename_teams(job["df"], cluster_to_name)
    summary_df = job["summary_df"]
    fatigue_df = job["fatigue_df"]
    minutes_analyzed = job["minutes_analyzed"]

    row = summary_df[summary_df["track_id"] == track_id]
    if row.empty:
        abort(404)
    row = row.iloc[0]

    cluster_series = df[df["track_id"] == track_id]["team_cluster"]
    cluster_id = int(cluster_series.iloc[0]) if not cluster_series.empty else -1
    team_name = cluster_to_name.get(cluster_id, "Sin equipo")
    player_name = job.get("player_names", {}).get(track_id)

    activity_level = classify_activity_level(row["distancia_total_m"], minutes_analyzed)
    fatigue_row = fatigue_df[fatigue_df["track_id"] == track_id]
    fatigue_alert = bool(fatigue_row["alerta_fatiga"].iloc[0]) if not fatigue_row.empty else False

    points = get_heatmap_points(job["df"], track_id=track_id)
    heatmap_path = os.path.join(tempfile.gettempdir(), f"heatmap_{job_id}_{track_id}.png")
    with open(heatmap_path, "wb") as f:
        f.write(_make_heatmap_png(points))

    pdf_bytes = generate_player_pdf(
        track_id=track_id, player_name=player_name, team_name=team_name,
        distance_m=float(row["distancia_total_m"]), avg_speed_kmh=float(row["velocidad_promedio_kmh"]),
        max_speed_kmh=float(row["velocidad_max_kmh"]), activity_level=activity_level,
        minutes_analyzed=minutes_analyzed, fatigue_alert=fatigue_alert, heatmap_image_path=heatmap_path,
    )

    try:
        os.remove(heatmap_path)
    except OSError:
        pass

    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf",
                      as_attachment=True, download_name=f"ficha_jugador_{track_id}.pdf")


@app.route("/download/csv/<job_id>")
def download_csv(job_id):
    job = JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        abort(404)
    cluster_to_name = _get_cluster_to_name(job)
    df = rename_teams(job["df"], cluster_to_name)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return send_file(io.BytesIO(csv_bytes), mimetype="text/csv",
                      as_attachment=True, download_name="tracking_resultado.csv")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # threaded=True permite que el servidor de desarrollo atienda la
    # consulta de progreso mientras el hilo de análisis sigue corriendo.
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
