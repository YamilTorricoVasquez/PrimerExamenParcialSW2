"""
jersey_ocr.py
-------------
Intenta leer el número de camiseta de cada jugador detectado, muestreando
unos pocos fotogramas del video y recortando la región del torso de cada
track_id ya conocido (a partir del CSV de tracking).

IMPORTANTE — esto es EXPERIMENTAL, no una fuente confiable:
- El número está en la espalda de la camiseta. Con cámara elevada o
  jugadores de frente a la cámara, el número simplemente no es visible.
- El número es pequeño y el jugador se mueve — el OCR va a fallar con
  frecuencia. Esto es una ayuda de sugerencia, no un resultado garantizado.
- Esta función se ejecuta DURANTE el procesamiento del video (antes de que
  se borre el archivo), porque necesita los fotogramas originales, no solo
  las coordenadas ya guardadas en el CSV.

La asignación confiable de nombre a jugador sigue siendo la que hace el
entrenador manualmente (ver player_names en app.py) — esto solo la ayuda a
ir más rápido cuando el número sí se logra leer.
"""

from collections import Counter, defaultdict
from typing import Dict, Optional

import cv2
import numpy as np
import pandas as pd


def _crop_number_region(frame_bgr: np.ndarray, x_center: float, y_center: float, w: float, h: float) -> Optional[np.ndarray]:
    """Recorta la región central de la espalda, donde normalmente va el número."""
    frame_h, frame_w = frame_bgr.shape[:2]
    x1 = int(max(x_center - w / 3, 0))
    x2 = int(min(x_center + w / 3, frame_w - 1))
    y1 = int(max(y_center - h / 2 + h * 0.15, 0))
    y2 = int(min(y_center - h / 2 + h * 0.55, frame_h - 1))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame_bgr[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def guess_jersey_numbers(video_path: str, tracking_df: pd.DataFrame, num_samples: int = 6) -> Dict[int, str]:
    """
    Devuelve un diccionario {track_id: "número"} con la mejor conjetura de
    número de camiseta para cada jugador, o simplemente omite los track_id
    donde no se pudo leer nada con confianza razonable.

    Nunca lanza una excepción hacia afuera: cualquier fallo (sin easyocr
    instalado, video no legible, etc.) devuelve un diccionario vacío, para
    que el resto del análisis siga funcionando con la plantilla manual.
    """
    try:
        import easyocr
    except ImportError:
        return {}

    try:
        players = tracking_df[tracking_df["class"] == "person"]
        if players.empty:
            return {}

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return {}

        sample_frames = sorted(set(np.linspace(0, total_frames - 1, num_samples, dtype=int).tolist()))
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)

        votes = defaultdict(list)  # track_id -> lista de números leídos

        for frame_num in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_num))
            ok, frame = cap.read()
            if not ok:
                continue

            # Detecciones más cercanas a este fotograma para cada jugador
            frame_rows = players.iloc[(players["frame"] - frame_num).abs().groupby(players["track_id"]).idxmin()]

            for _, row in frame_rows.iterrows():
                crop = _crop_number_region(frame, row["x_center"], row["y_center"], row["width"], row["height"])
                if crop is None or crop.shape[0] < 10 or crop.shape[1] < 10:
                    continue
                # Se agranda el recorte: los números son pequeños y el OCR
                # rinde mejor con más resolución.
                crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                results = reader.readtext(crop, allowlist="0123456789")
                for _, text, confidence in results:
                    text = text.strip()
                    if text.isdigit() and 1 <= len(text) <= 2 and confidence > 0.35:
                        votes[int(row["track_id"])].append(text)

        cap.release()

        guesses = {}
        for track_id, numbers in votes.items():
            if numbers:
                most_common, count = Counter(numbers).most_common(1)[0]
                if count >= 1:  # cualquier lectura es solo una sugerencia, no una certeza
                    guesses[track_id] = most_common

        return guesses

    except Exception:
        return {}
