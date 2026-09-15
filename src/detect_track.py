"""
detect_track.py
----------------
Detección y seguimiento (tracking) de jugadores y balón en un video de fútbol.

Usa un modelo YOLOv8 pre-entrenado (Ultralytics), incluido directamente en
este proyecto en models/yolov8n.pt (no requiere descarga ni entrenamiento),
sobre la clase COCO "person" para detectar jugadores, y el tracker
ByteTrack integrado en la librería para mantener una identidad (track_id)
consistente de cada jugador entre fotogramas.

NOTA IMPORTANTE (honestidad metodológica para la tesis):
El modelo YOLOv8 incluido está entrenado sobre el dataset COCO, que no
distingue "balón de fútbol" como clase separada de "sports ball" en todos
los casos, ni distingue jugadores por equipo. Este script es un punto de
partida funcional; para resultados de nivel profesional se recomienda
fine-tuning sobre un dataset específico de fútbol (p. ej. SoccerNet),
lo cual puede plantearse como una fase posterior o trabajo futuro de la tesis.

Uso por línea de comandos:
    python detect_track.py --source video.mp4 --output data/tracking.csv

También se puede importar y usar run_tracking() directamente desde el
dashboard (app.py), incluyendo un progress_callback para mostrar avance.
"""

import argparse
import os
import csv
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
from ultralytics import YOLO

# Ruta al modelo YA INCLUIDO en el proyecto (no se descarga en tiempo de uso).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = str(PROJECT_ROOT / "models" / "yolov8n.pt")

# Clases de interés dentro del dataset COCO (id: nombre)
# 0 = person, 32 = sports ball
CLASSES_OF_INTEREST = {0: "person", 32: "ball"}


def sample_jersey_color(frame_bgr: np.ndarray, x_center: float, y_center: float, w: float, h: float) -> tuple[int, int, int]:
    """
    Toma una pequeña región del torso (aprox. el tercio superior del cuerpo
    detectado, evitando la cabeza y las piernas) y devuelve su color
    promedio en formato RGB. Se usa para agrupar jugadores por equipo según
    el color de camiseta, sin necesidad de entrenar un modelo nuevo.
    """
    frame_h, frame_w = frame_bgr.shape[:2]

    x1 = int(max(x_center - w / 4, 0))
    x2 = int(min(x_center + w / 4, frame_w - 1))
    # Torso: entre ~25% y ~55% de la altura del bounding box (debajo de la
    # cabeza, arriba de las piernas/shorts).
    y1 = int(max(y_center - h / 2 + h * 0.25, 0))
    y2 = int(min(y_center - h / 2 + h * 0.55, frame_h - 1))

    if x2 <= x1 or y2 <= y1:
        return (128, 128, 128)  # gris neutro si la región es inválida

    crop = frame_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return (128, 128, 128)

    mean_bgr = crop.reshape(-1, 3).mean(axis=0)
    b, g, r = mean_bgr
    return (int(r), int(g), int(b))


def get_video_frame_count(source: str) -> int:
    """Devuelve el número total de fotogramas del video (para barras de progreso)."""
    cap = cv2.VideoCapture(source)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return max(total, 0)


def run_tracking(
    source: str,
    output_csv: str,
    model_path: str = DEFAULT_MODEL_PATH,
    conf: float = 0.3,
    vid_stride: int = 1,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """
    Corre detección + tracking sobre el video de entrada y guarda los
    resultados en un CSV con una fila por detección por fotograma.

    Args:
        source: ruta al video de entrada.
        output_csv: ruta donde guardar el CSV de resultados.
        model_path: ruta al modelo YOLO (por defecto, el incluido en el proyecto).
        conf: umbral mínimo de confianza de detección.
        vid_stride: procesa 1 de cada N fotogramas (acelera videos largos en CPU).
        progress_callback: función opcional callback(frame_procesado, total_frames)
            para actualizar una barra de progreso (usada por el dashboard).

    Columnas del CSV:
        frame, track_id, class, x_center, y_center, width, height, confidence
    """
    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"No se encontró el modelo en '{model_path}'. Verifica que "
            f"models/yolov8n.pt esté presente en el proyecto."
        )

    model = YOLO(model_path)
    total_frames = get_video_frame_count(source)

    rows = []
    frame_idx = 0

    # model.track() ya integra ByteTrack internamente (persist=True mantiene
    # las identidades entre llamadas/fotogramas del mismo video).
    results_generator = model.track(
        source=source,
        classes=list(CLASSES_OF_INTEREST.keys()),
        conf=conf,
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,          # procesa fotograma a fotograma sin cargar todo el video en memoria
        vid_stride=vid_stride,
        verbose=False,
    )

    for result in results_generator:
        boxes = result.boxes
        frame_image = result.orig_img  # numpy array BGR del fotograma actual

        if boxes is not None and boxes.id is not None:
            for box, track_id, cls, conf_score in zip(
                boxes.xywh.cpu().numpy(),
                boxes.id.cpu().numpy(),
                boxes.cls.cpu().numpy(),
                boxes.conf.cpu().numpy(),
            ):
                x_center, y_center, w, h = box
                class_name = CLASSES_OF_INTEREST.get(int(cls), "unknown")

                if class_name == "person" and frame_image is not None:
                    r, g, b = sample_jersey_color(frame_image, x_center, y_center, w, h)
                else:
                    r, g, b = (0, 0, 0)  # el balón no tiene "equipo"

                rows.append({
                    "frame": frame_idx,
                    "track_id": int(track_id),
                    "class": class_name,
                    "x_center": float(x_center),
                    "y_center": float(y_center),
                    "width": float(w),
                    "height": float(h),
                    "confidence": float(conf_score),
                    "color_r": r,
                    "color_g": g,
                    "color_b": b,
                })
        frame_idx += 1

        if progress_callback is not None:
            # total_frames ya tiene en cuenta el vídeo completo; al usar
            # vid_stride el número de iteraciones reales es menor, así que
            # estimamos el total efectivo para que la barra llegue a 100%.
            effective_total = max(total_frames // vid_stride, 1)
            progress_callback(frame_idx, effective_total)

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["frame", "track_id", "class", "x_center", "y_center", "width", "height",
                           "confidence", "color_r", "color_g", "color_b"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Procesados {frame_idx} fotogramas. {len(rows)} detecciones guardadas en: {output_csv}")
    return output_csv


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detección y tracking de jugadores/balón en video de fútbol.")
    parser.add_argument("--source", required=True, help="Ruta al video de entrada (mp4, avi, etc).")
    parser.add_argument("--output", default="data/tracking.csv", help="Ruta del CSV de salida.")
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="Ruta al modelo YOLOv8 (por defecto, el incluido en el proyecto).")
    parser.add_argument("--conf", type=float, default=0.3, help="Umbral mínimo de confianza de detección.")
    parser.add_argument("--stride", type=int, default=1, help="Procesar 1 de cada N fotogramas (acelera en CPU).")
    args = parser.parse_args()

    run_tracking(args.source, args.output, args.model, args.conf, args.stride)

