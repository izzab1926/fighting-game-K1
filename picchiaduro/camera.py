"""Camera prospettica 2.5D: proiezione mondo -> schermo, inseguimento e scossoni.

Tutto il rendering del mondo (arena, lottatori, particelle) deve passare da
qui, cosi' zoom, panoramica e scossoni restano coerenti per ogni elemento.
"""

from __future__ import annotations

import math
import random

from . import costanti as C


class Camera:
    def __init__(self, larghezza: int = C.LARGHEZZA, altezza: int = C.ALTEZZA):
        self.larghezza = larghezza
        self.altezza = altezza
        self.x = C.RING_LARGHEZZA / 2      # x del mondo al centro dello schermo
        self.zoom = C.ZOOM_MIN
        self._x_obiettivo = self.x
        self._zoom_obiettivo = self.zoom
        # scossone
        self._scossa_intensita = 0.0
        self._scossa_durata = 0
        self._scossa_frame = 0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._rng = random.Random(1234)

    # ----------------------------------------------------------- proiezione
    def scala(self, z: float) -> float:
        """Pixel per unita' del mondo alla profondita' z (zoom incluso)."""
        return C.CAMERA_F / (z + C.CAMERA_D) * self.zoom

    def proietta(self, x: float, z: float, h: float = 0.0) -> tuple[float, float]:
        """Punto del mondo -> coordinate schermo (float)."""
        k = C.CAMERA_F / (z + C.CAMERA_D)
        sx = self.larghezza / 2 + (x - self.x) * k * self.zoom
        sy = C.ORIZZONTE_Y + (C.CAMERA_H - h) * k
        sy = C.PERNO_ZOOM_Y + (sy - C.PERNO_ZOOM_Y) * self.zoom
        return sx + self.offset_x, sy + self.offset_y

    def mondo_x_da_schermo(self, sx: float, z: float) -> float:
        """Inverso orizzontale della proiezione (utile per sfondi e culling)."""
        k = C.CAMERA_F / (z + C.CAMERA_D) * self.zoom
        return self.x + (sx - self.offset_x - self.larghezza / 2) / k

    # ---------------------------------------------------------- inseguimento
    def segui(self, x1: float, x2: float, istantaneo: bool = False) -> None:
        """Centra la camera tra i due lottatori e zooma quando sono vicini."""
        centro = (x1 + x2) / 2
        meta_vista = self.larghezza / 2 / self.zoom
        lo = meta_vista - 120
        hi = C.RING_LARGHEZZA - meta_vista + 120
        self._x_obiettivo = min(max(centro, lo), hi) if lo < hi else C.RING_LARGHEZZA / 2

        distanza = abs(x1 - x2)
        t = min(1.0, max(0.0, (distanza - 180) / 600))
        self._zoom_obiettivo = C.ZOOM_MAX + (C.ZOOM_MIN - C.ZOOM_MAX) * t
        if istantaneo:
            self.x = self._x_obiettivo
            self.zoom = self._zoom_obiettivo

    def scuoti(self, intensita: float, durata: int) -> None:
        """Scossone di schermo: intensita' in pixel, durata in frame."""
        if intensita >= self._scossa_intensita * (1 - self._scossa_frame / max(1, self._scossa_durata)):
            self._scossa_intensita = intensita
            self._scossa_durata = max(1, durata)
            self._scossa_frame = 0

    def aggiorna(self) -> None:
        """Da chiamare una volta per frame (60 Hz)."""
        self.x += (self._x_obiettivo - self.x) * 0.12
        self.zoom += (self._zoom_obiettivo - self.zoom) * 0.06

        if self._scossa_frame < self._scossa_durata:
            resto = 1 - self._scossa_frame / self._scossa_durata
            amp = self._scossa_intensita * resto * resto
            ang = self._rng.uniform(0, math.tau)
            self.offset_x = math.cos(ang) * amp
            self.offset_y = math.sin(ang) * amp * 0.6
            self._scossa_frame += 1
        else:
            self.offset_x = self.offset_y = 0.0
            self._scossa_intensita = 0.0
