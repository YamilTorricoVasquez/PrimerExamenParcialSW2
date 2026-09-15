"""
scoreboard_ocr.py
------------------
Intenta leer texto (posibles nombres de equipo) desde el marcador que
aparece en video de transmisión de TV, usando OCR sobre una región de la
pantalla.

IMPORTANTE — esto es EXPERIMENTAL y de apoyo, no una fuente confiable:
- Solo tiene sentido en video de transmisión (broadcast); un video de
  cámara táctica fija normalmente no tiene marcador en pantalla.
- El formato y posición del marcador varía mucho entre canales/transmisiones,
  así que el texto detectado puede venir incompleto, mezclado con el
  marcador de tiempo, o simplemente no detectarse nada.
- Esta función NO asigna jugadores a equipos — solo sugiere posibles
  nombres de texto encontrados en pantalla para que el entrenador los use
  (o no) como nombre de equipo. La asignación real de jugador -> equipo
  sigue haciéndose por color de camiseta (ver teams.py).

Usa EasyOCR, que no requiere instalar un binario aparte en el sistema
(a diferencia de Tesseract), pero sí descarga modelos de reconocimiento la
primera vez que se usa (requiere conexión a internet en ese momento).
"""

from typing import List

import cv2
import numpy as np


def _get_sample_frames(video_path: str, num_frames: int = 3) -> List[np.ndarray]:
    """Extrae unos pocos fotogramas repartidos al inicio del video."""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []

    # Se muestrean fotogramas de los primeros segundos, donde el marcador
    # suele estar ya visible y sin overlays de reproducción/anuncios.
    sample_points = np.linspace(0, min(total_frames - 1, 150), num_frames, dtype=int) if total_frames > 0 else [0]

    for frame_num in sample_points:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_num))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)

    cap.release()
    return frames


def suggest_team_names_from_scoreboard(video_path: str, top_crop_fraction: float = 0.18) -> List[str]:
    """
    Intenta extraer fragmentos de texto desde la franja superior del video
    (donde suele estar el marcador en muchas transmisiones) usando OCR.

    Devuelve una lista de fragmentos de texto candidatos (puede venir
    vacía si no se detecta nada, o si EasyOCR no está disponible/falla).
    Esta función NUNCA lanza una excepción hacia afuera: cualquier fallo
    (sin internet para descargar el modelo, formato de video no soportado,
    etc.) se traduce simplemente en una lista vacía, para que el dashboard
    pueda seguir funcionando con la opción manual.
    """
    try:
        import easyocr  # import perezoso: solo se carga si el usuario activa esta opción
    except ImportError:
        return []

    try:
        frames = _get_sample_frames(video_path)
        if not frames:
            return []

        reader = easyocr.Reader(["es", "en"], gpu=False, verbose=False)

        candidates = set()
        for frame in frames:
            h, w = frame.shape[:2]
            top_strip = frame[0:int(h * top_crop_fraction), :]
            results = reader.readtext(top_strip)
            for (_, text, confidence) in results:
                cleaned = text.strip()
                # Filtra fragmentos muy cortos o que parecen solo números
                # (probablemente el marcador de goles o el reloj, no el nombre).
                if confidence > 0.4 and len(cleaned) >= 3 and not cleaned.replace(":", "").isdigit():
                    candidates.add(cleaned)

        return sorted(candidates)

    except Exception:
        # Cualquier error inesperado (video corrupto, fallo de red al bajar
        # el modelo, etc.) degrada silenciosamente a "sin sugerencias".
        return []
