"""
homography.py
--------------
Calibración de campo: transforma coordenadas de píxel (posición en la imagen
del video) a coordenadas reales de campo en metros, usando una homografía.

CÓMO CALIBRAR TU PROPIO VIDEO (hazlo una sola vez por ángulo de cámara):

1. Elige un fotograma claro de tu video donde se vean 4 puntos identificables
   del campo (normalmente las 4 esquinas del área grande, o las esquinas del
   propio campo si se ven completas).
2. Anota las coordenadas en PÍXELES de esos 4 puntos en la imagen
   (puedes abrir el fotograma en cualquier editor de imágenes y leer la
   posición del cursor, o usar cv2 para hacer clic sobre la imagen).
3. Anota las coordenadas REALES en metros de esos mismos 4 puntos, según las
   medidas oficiales de un campo de fútbol (105 x 68 m es el estándar FIFA;
   ajusta si tu campo es de otra medida).
4. Reemplaza los valores de ejemplo en PIXEL_POINTS y FIELD_POINTS abajo.

Este script NO necesita entrenamiento de ningún modelo — es geometría pura
(cv2.findHomography), por lo que no requiere GPU ni datos de entrenamiento.
"""

import numpy as np
import cv2

# ---------------------------------------------------------------------------
# EJEMPLO — reemplaza estos valores con los de TU video y TU campo.
# Deben ser el mismo punto físico, uno en píxeles y otro en metros, en el
# mismo orden (por ejemplo: esquina superior-izq, superior-der, inferior-der,
# inferior-izq del área o del campo completo).
# ---------------------------------------------------------------------------
PIXEL_POINTS = np.array([
    [100, 80],
    [1180, 80],
    [1180, 700],
    [100, 700],
], dtype=np.float32)

FIELD_POINTS = np.array([
    [0, 0],
    [105, 0],
    [105, 68],
    [0, 68],
], dtype=np.float32)


def compute_homography_matrix(pixel_points: np.ndarray = PIXEL_POINTS,
                               field_points: np.ndarray = FIELD_POINTS) -> np.ndarray:
    """Calcula la matriz de homografía 3x3 que mapea píxeles -> metros de campo."""
    matrix, _ = cv2.findHomography(pixel_points, field_points)
    if matrix is None:
        raise ValueError(
            "No se pudo calcular la homografía. Revisa que los 4 puntos no "
            "sean colineales y que correspondan correctamente entre sí."
        )
    return matrix


def pixel_to_field(x_pixel: float, y_pixel: float, homography_matrix: np.ndarray) -> tuple[float, float]:
    """Convierte una coordenada de píxel a coordenadas reales de campo (metros)."""
    point = np.array([[[x_pixel, y_pixel]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(point, homography_matrix)
    x_field, y_field = transformed[0][0]
    return float(x_field), float(y_field)


if __name__ == "__main__":
    # Prueba rápida con los puntos de ejemplo.
    H = compute_homography_matrix()
    x_m, y_m = pixel_to_field(640, 400, H)
    print(f"Punto de ejemplo (640, 400) px -> ({x_m:.2f}, {y_m:.2f}) m en el campo")
    print("Recuerda reemplazar PIXEL_POINTS y FIELD_POINTS con los de tu propio video.")
