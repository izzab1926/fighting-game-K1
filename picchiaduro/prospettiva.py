"""Proiezione prospettica 2.5D: converte coordinate del mondo in coordinate schermo.

Il ring e' un trapezio: la linea vicina (Z=0) e' larga e in basso,
la linea lontana (Z massimo) e' stretta e in alto. I lottatori vengono
scalati in base alla profondita' per dare l'effetto 2.5D.
"""

from . import settings as S


def _lerp(a, b, t):
    return a + (b - a) * t


def t_profondita(z):
    """Frazione di profondita' 0 (vicino) .. 1 (lontano)."""
    return max(0.0, min(1.0, z / S.RING_PROFONDITA))


def scala(z):
    """Fattore di scala del lottatore alla profondita' z."""
    return _lerp(S.SCALA_VICINO, S.SCALA_LONTANO, t_profondita(z))


def suolo_y(z):
    """Y schermo del pavimento (dove poggiano i piedi) alla profondita' z."""
    return _lerp(S.NEAR_Y, S.FAR_Y, t_profondita(z))


def proietta(x, z):
    """Mappa un punto del mondo (x lungo il ring, z profondita') sullo schermo."""
    t = t_profondita(z)
    sinistra = _lerp(S.NEAR_MARGINE, S.FAR_MARGINE, t)
    larghezza = _lerp(S.LARGHEZZA - 2 * S.NEAR_MARGINE,
                      S.LARGHEZZA - 2 * S.FAR_MARGINE, t)
    sx = sinistra + (x / S.RING_LARGHEZZA) * larghezza
    sy = _lerp(S.NEAR_Y, S.FAR_Y, t)
    return sx, sy


def angoli_ring():
    """I quattro angoli del pavimento del ring sullo schermo (per disegnarlo)."""
    bl = proietta(0, 0)                       # basso-sinistra (vicino)
    br = proietta(S.RING_LARGHEZZA, 0)        # basso-destra (vicino)
    tr = proietta(S.RING_LARGHEZZA, S.RING_PROFONDITA)  # alto-destra (lontano)
    tl = proietta(0, S.RING_PROFONDITA)       # alto-sinistra (lontano)
    return bl, br, tr, tl
