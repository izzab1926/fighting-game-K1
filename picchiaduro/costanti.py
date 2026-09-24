"""Costanti globali condivise da simulazione, rendering, UI e audio.

Unita' del mondo: 1 unita' ~ 7 mm. Un lottatore standard e' alto
ALTEZZA_BASE unita'. Assi del mondo:
  x  lungo il ring (sinistra -> destra sullo schermo)
  z  profondita' (0 = bordo vicino alla camera, RING_PROFONDITA = fondo)
  h  altezza dal tappeto (0 = pavimento, verso l'alto positivo)
"""

# --- Schermo logico (si scala sulla finestra reale) ---
LARGHEZZA = 1280
ALTEZZA = 720
FPS = 60
TITOLO = "KICKBOXING K1"

# --- Ring (mondo) ---
RING_LARGHEZZA = 1800.0
RING_PROFONDITA = 420.0
MARGINE_CORDE = 40.0            # distanza minima dei lottatori dalle corde
DISTANZA_MAX = 1000.0           # separazione massima in x (muri invisibili camera)

# --- Corporatura base dei lottatori (mondo) ---
ALTEZZA_BASE = 250.0
LARGHEZZA_BASE = 70.0           # larghezza del corpo per collisioni

# --- Camera prospettica (pinhole) ---
# sx = centro_x + F * (x - cam_x) / (z + D) * zoom
# sy = ORIZZONTE_Y + F * (CAM_H - h) / (z + D)          (poi zoom attorno al perno)
# Tarata perche' il bordo vicino del tappeto (z=0) cada a y~690 con scala 1.0
# e il bordo lontano (z=RING_PROFONDITA) a y~390 con scala 0.6.
CAMERA_D = 630.0
CAMERA_F = 630.0
CAMERA_H = 750.0
ORIZZONTE_Y = -60.0
ZOOM_MIN = 1.0
ZOOM_MAX = 1.12
PERNO_ZOOM_Y = 560.0            # y schermo attorno a cui avviene lo zoom

# --- Round / partita ---
ROUND_PER_VINCERE = 2           # al meglio dei 3
DURATA_ROUND = 90               # secondi
ATTERRAMENTI_TKO = 3            # 3 atterramenti nello stesso round = KO tecnico

# --- Palette di base ---
NERO = (10, 10, 14)
BIANCO = (245, 245, 250)
GRIGIO = (120, 120, 132)
GRIGIO_SCURO = (46, 46, 56)
ROSSO = (226, 56, 64)
VERDE = (72, 206, 110)
GIALLO = (250, 206, 60)
ORO = (236, 180, 60)
BLU = (64, 132, 236)
AZZURRO = (96, 206, 240)
ARANCIO = (244, 140, 48)
VIOLA = (150, 90, 220)

# --- Energia speciale (super) ---
ENERGIA_MAX = 100.0
