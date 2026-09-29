"""Arena da serata K-1 in TV: sala buia, pubblico, luci a cono, ring in prospettiva.

Tutto cio' che sta nel mondo passa da `camera.proietta` / `camera.scala`:
  - tappeto, logo "K1", grembiule, corde e pali sono geometria proiettata
    vertice per vertice a ogni frame (pan, zoom e scossoni sempre coerenti);
  - pubblico, cartelloni LED, fasci e pozze di luce sono strati statici
    pre-renderizzati (supersampling 2x) a ZOOM_RIF, ciascuno su un piano a
    profondita' fissa: a ogni frame si proietta il loro punto d'ancoraggio,
    cosi' la parallasse del pan e' quella giusta per la loro profondita'.
"""

from __future__ import annotations

import bisect
import math
import random
from typing import Optional

import pygame
import pygame.gfxdraw as gfx

from .. import costanti as C
from .. import eventi as E

# ---- geometria del ring (mondo)
BORDO_LATO = 70.0              # tappeto oltre le corde ai lati
BORDO_FONDO = 70.0             # ... sul fondo
BORDO_FRONTE = 30.0            # ... davanti (quasi fuori schermo)
QUOTA_SALA = -170.0            # pavimento della sala rispetto al tappeto
ALTEZZE_CORDE = (62.0, 118.0, 176.0)
RAGGIO_CORDA = 3.2
SPORGENZA_PALO = 9.0           # i pali stanno appena fuori dall'angolo delle corde
ALTEZZA_PALO = 214.0
RAGGIO_PALO = 8.0
RAGGIO_CUSCINO = 16.0
CUSCINO_BASSO, CUSCINO_ALTO = 38.0, 198.0
ZOOM_RIF = 1.1                 # zoom a cui sono pre-renderizzati gli strati rigidi

# ---- sala (mondo)
Z_LED = 760.0                  # barriera LED dietro al ring
LED_BASSO, LED_ALTO = QUOTA_SALA, -82.0
FILE_BORDO = ((930.0, QUOTA_SALA), (830.0, QUOTA_SALA))            # dal fondo in avanti
FILE_TRIBUNA_BASSA = ((1260.0, -20.0), (1160.0, -70.0), (1060.0, -120.0))
FILE_TRIBUNA_ALTA = ((1460.0, 80.0), (1360.0, 30.0))
FILE_ANELLO = ((1905.0, 450.0), (1810.0, 400.0), (1715.0, 350.0), (1620.0, 300.0))
BALCONATA = (1560.0, 214.0, 330.0)   # z, quota bassa, quota alta del parapetto
X_BARRIERA_LATO = 300.0              # distanza della barriera laterale dal ring
SEDILE = 56.0                        # passo dei posti a sedere (mondo)
LARGHEZZA_STRATO = 1600              # periodo (px) degli strati ripetuti
MARGINE_STRATI = 16.0                # sovrapposizione minima tra strati (slittamento con lo zoom)

# ---- palette
SALA = (6, 7, 13)
NEBBIA = (13, 14, 24)             # foschia della sala che inghiotte il pubblico lontano
PAVIMENTO = (11, 11, 17)
GRADINO = (14, 15, 23)
TELA_VICINO = (20, 44, 104)
TELA = (24, 54, 122)
TELA_FONDO = (15, 34, 86)
GREMBIULE = (13, 13, 19)
LINEA_TELA = (214, 44, 56)
LOGO_PIENO = (126, 140, 184)
LOGO_BORDO = (190, 28, 42)
LOGO_OMBRA = (14, 24, 58)
LOGO_LUCE = (158, 172, 212)
ORO = (232, 178, 64)
CORDE_COLORI = ((40, 92, 212), (214, 214, 224), (214, 38, 50))   # bassa, media, alta
COLORI_CUSCINO = {"rosso": (210, 36, 46), "blu": (38, 88, 208), "bianco": (230, 230, 236)}
ACCIAIO = (66, 70, 82)
ALFA_CORDE_DAVANTI = 125
ALFA_PALI_DAVANTI = 175

SPONSOR_LED = ("RAIJIN ENERGY", "SAKURA MOTORS", "TITAN GLOVES", "KAIZEN TV",
               "OKAMI RAMEN", "NOVA SPORT", "FERRO GYM", "DRAGO ROSSO")
COLORI_LED = ((236, 60, 64), (240, 240, 245), (250, 196, 60), (80, 170, 250),
              (250, 120, 50), (90, 220, 140), (230, 230, 235), (236, 50, 60))
SPONSOR_TAPPETO = ("RAIJIN ENERGY", "KAIZEN TV", "NOVA SPORT", "FERRO GYM")
STRISCIONI = (("FORZA TORO!", (200, 30, 40), (245, 245, 245)),
              ("VENTO  JAPAN", (240, 240, 245), (200, 30, 40)),
              ("IL MURO NON CADE", (240, 190, 60), (20, 20, 24)),
              ("LAMA DO BRASIL", (30, 150, 70), (250, 214, 40)),
              ("K1 WORLD GP", (20, 20, 26), (236, 180, 60)),
              ("ITALIA ALE'!", (30, 130, 60), (245, 245, 245)),
              ("OSS!", (230, 230, 235), (30, 30, 36)))


# ---- utilita'
def _k(z: float) -> float:
    return C.CAMERA_F / (z + C.CAMERA_D)


def _y_rif(z: float, h: float) -> float:
    """y schermo di un punto (z, h) con zoom ZOOM_RIF e senza scossone."""
    y0 = C.ORIZZONTE_Y + (C.CAMERA_H - h) * _k(z)
    return C.PERNO_ZOOM_Y + (y0 - C.PERNO_ZOOM_Y) * ZOOM_RIF


def _px(z: float) -> float:
    """Pixel per unita' di mondo in x alla profondita' z, a ZOOM_RIF."""
    return _k(z) * ZOOM_RIF


def _converti(s: pygame.Surface, alfa: bool) -> pygame.Surface:
    try:
        return s.convert_alpha() if alfa else s.convert()
    except pygame.error:
        return s


def _mescola(a, b, t: float):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _desatura(c, t: float):
    g = (c[0] * 0.3 + c[1] * 0.59 + c[2] * 0.11)
    return (int(c[0] + (g - c[0]) * t), int(c[1] + (g - c[1]) * t), int(c[2] + (g - c[2]) * t))


def _scala_col(c, f: float):
    return (min(255, max(0, int(c[0] * f))), min(255, max(0, int(c[1] * f))),
            min(255, max(0, int(c[2] * f))))


def _font(dim: int) -> pygame.font.Font:
    if not pygame.font.get_init():
        pygame.font.init()
    return pygame.font.Font(None, dim)


def _offset_poligono(punti, d: float, limite: float = 2.2):
    """Contorno di un poligono (anche concavo) spostato verso l'esterno di d."""
    n = len(punti)
    area = sum(punti[i][0] * punti[(i + 1) % n][1] - punti[(i + 1) % n][0] * punti[i][1]
               for i in range(n))
    verso = 1.0 if area > 0 else -1.0
    normali = []
    for i in range(n):
        x0, y0 = punti[i]
        x1, y1 = punti[(i + 1) % n]
        lx, ly = x1 - x0, y1 - y0
        lung = math.hypot(lx, ly) or 1.0
        normali.append((ly / lung * verso, -lx / lung * verso))
    out = []
    for i in range(n):
        n1 = normali[i - 1]
        n2 = normali[i]
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        ml = math.hypot(mx, my)
        px, py = punti[i]
        if ml < 1e-6:
            out.append((px + n1[0] * d, py + n1[1] * d))
            continue
        mx, my = mx / ml, my / ml
        coseno = mx * n1[0] + my * n1[1]
        lung = d / max(coseno, 1e-3)
        if abs(lung) > abs(d) * limite:
            out.append((px + n1[0] * d, py + n1[1] * d))
            out.append((px + n2[0] * d, py + n2[1] * d))
        else:
            out.append((px + mx * lung, py + my * lung))
    return out


# ---- logo "K1" (spazio logo: u a destra, v verso il fondo del ring)
_K = ((0, 0), (52, 0), (52, 82), (82, 112), (146, 0), (206, 0), (116, 146),
      (198, 240), (136, 240), (52, 140), (52, 240), (0, 240))
_UNO = ((34, 0), (94, 0), (94, 240), (54, 240), (-14, 190), (4, 150), (34, 168))
_CORSIVO = 0.2
_LOGO_CENTRO = (C.RING_LARGHEZZA / 2, 218.0)
_LOGO_SCALA = 0.96


def _taglia_poligono(punti, z_min: float):
    """Parte del poligono con z >= z_min (Sutherland-Hodgman su un semipiano)."""
    out = []
    n = len(punti)
    for i in range(n):
        a, b = punti[i], punti[(i + 1) % n]
        dentro_a, dentro_b = a[1] >= z_min, b[1] >= z_min
        if dentro_a:
            out.append(a)
        if dentro_a != dentro_b:
            t = (z_min - a[1]) / (b[1] - a[1])
            out.append((a[0] + (b[0] - a[0]) * t, z_min))
    return out


def _ritaglia(a, b, w: float, h: float, margine: float):
    """Parametri (t0, t1) del segmento a-b dentro il rettangolo schermo (Liang-Barsky)."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] + margine), (dx, w + margine - a[0]),
                 (-dy, a[1] + margine), (dy, h + margine - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return t0, t1


def _poligoni_logo():
    """Lettere del logo in coordinate mondo (x, z) sul tappeto."""
    lettere = []
    for pts, dx in ((_K, 0.0), (_UNO, 250.0)):
        lettere.append([(u + dx + v * _CORSIVO, v) for u, v in pts])
    tutte = [p for l in lettere for p in l]
    u0 = min(p[0] for p in tutte)
    u1 = max(p[0] for p in tutte)
    cu, cv = (u0 + u1) / 2, 120.0
    cx, cz = _LOGO_CENTRO
    return [[(cx + (u - cu) * _LOGO_SCALA, cz + (v - cv) * _LOGO_SCALA) for u, v in l]
            for l in lettere]


# ---- pubblico
_MAGLIE = ((62, 62, 72), (96, 38, 44), (40, 54, 92), (58, 58, 60), (118, 118, 128),
           (28, 28, 34), (128, 32, 42), (40, 82, 62), (150, 138, 124), (34, 44, 74),
           (84, 70, 50), (22, 22, 26), (150, 150, 158), (100, 40, 90))
_PELLI = ((150, 110, 86), (118, 84, 62), (172, 132, 106), (90, 62, 46), (160, 124, 96))
_CAPELLI = ((22, 18, 16), (40, 30, 22), (70, 56, 40), (16, 16, 18), (120, 100, 70))
_SCIARPE = ((200, 30, 40), (40, 90, 210), (240, 190, 50), (30, 150, 70))


class _Persona:
    __slots__ = ("u", "scala", "maglia", "pelle", "capelli", "acconciatura",
                 "eccitabilita", "fase", "vuoto", "sciarpa", "destro", "alto")

    def __init__(self, rng: random.Random, u: float):
        self.u = u
        self.scala = rng.uniform(0.84, 1.14)
        self.alto = rng.uniform(-6.0, 7.0)          # busto piu' o meno eretto
        self.maglia = rng.choice(_MAGLIE)
        self.pelle = rng.choice(_PELLI)
        self.capelli = rng.choice(_CAPELLI)
        self.acconciatura = rng.choice((0, 0, 0, 1, 2, 3, 3))
        self.eccitabilita = rng.random()
        self.fase = rng.randrange(4)
        self.vuoto = rng.random() < 0.035
        self.sciarpa = rng.choice(_SCIARPE) if rng.random() < 0.16 else None
        self.destro = rng.random() < 0.6


def _posa(p: _Persona, livello: int, fotogramma: int):
    """(alzato, braccia, apertura, telefono): posa della persona per livello/fotogramma.

    braccia: 0 nessuna, 1 un braccio, 2 due braccia, 3 sciarpa tesa sopra la testa.
    """
    e = p.eccitabilita
    alterna = (p.fase + fotogramma) % 2
    if livello == 0:
        if e > 0.975:
            return 0.0, 1, 0.25 + 0.1 * alterna, False
        return (1.5 if alterna and p.fase < 2 else 0.0), 0, 0.0, False
    if livello == 1:
        if e > 0.62:
            br = 3 if p.sciarpa else (2 if e > 0.84 else 1)
            return 38.0, br, 0.2 + 0.18 * alterna, e > 0.93
        if e > 0.4:
            return 36.0 + 2 * alterna, 0, 0.0, False
        return 1.5 * alterna, 0, 0.0, False
    if e > 0.22:
        br = 3 if p.sciarpa else (2 if e > 0.5 else 1)
        return 38.0 + 3 * alterna, br, 0.12 + 0.3 * alterna, e > 0.82
    if e > 0.08:
        return 37.0 + 2 * alterna, 0, 0.0, False
    return 0.0, 0, 0.0, False


def _colori_persona(p: _Persona, luce: float) -> tuple:
    """Toni (maglia, maglia_scura, pelle, capelli, bordo, collo, testa_bordo, sciarpa, cappello)."""
    amb = 0.07 + 0.52 * luce
    nebbia = 0.55 * (1.0 - luce)

    def tono(c, f=1.0):
        return _mescola(_scala_col(_desatura(c, 0.35), amb * f), NEBBIA, nebbia)

    maglia = tono(p.maglia)
    pelle = tono(p.pelle, 0.85)
    sciarpa = (_mescola(_scala_col(p.sciarpa, 0.2 + 0.55 * luce), NEBBIA, nebbia * 0.7)
               if p.sciarpa else None)
    return (maglia, tono(p.maglia, 0.72), pelle, tono(p.capelli),
            _mescola(maglia, (120, 132, 176), 0.22 * luce + 0.06), tono(p.pelle, 0.55),
            _mescola(pelle, (130, 140, 180), 0.2 * luce + 0.05), sciarpa,
            tono(p.sciarpa or p.maglia, 1.1), tono((200, 200, 200)))


def _disegna_persona(s: pygame.Surface, p: _Persona, cx: float, y_sedile: float,
                     scala: float, colori: tuple, posa) -> tuple:
    """Silhouette di uno spettatore (supersampling: scala = px per unita').

    Ritorna (x, y) della testa, dove puo' scattare un flash.
    """
    alzato, braccia, apertura, telefono = posa
    sc = scala * p.scala
    y0 = y_sedile - (alzato + p.alto) * scala

    def Y(h):
        return y0 - h * sc

    (maglia, maglia_scura, pelle, capelli, bordo, collo, testa_bordo, col_sciarpa,
     cap, riga_sciarpa) = colori
    # busto (scende fin sotto la fila davanti)
    mezza = 22 * sc
    pygame.draw.rect(s, maglia_scura, (cx - mezza * 0.95, Y(40), mezza * 1.9, 72 * sc))
    pygame.draw.ellipse(s, bordo, (cx - mezza * 1.12, Y(52), mezza * 2.24, 22 * sc))
    pygame.draw.ellipse(s, maglia, (cx - mezza * 1.08, Y(50.5), mezza * 2.16, 22 * sc))
    pygame.draw.rect(s, maglia, (cx - mezza * 1.0, Y(42), mezza * 2.0, 60 * sc))
    # braccia alzate
    spalla = 17 * sc
    lati = ()
    if braccia == 1:
        lati = (1 if p.destro else -1,)
    elif braccia >= 2:
        lati = (-1, 1)
    mani = []
    for lato in lati:
        ax, ay = cx + lato * spalla, Y(44)
        ang = apertura if braccia != 3 else 0.12
        hx = ax + lato * math.sin(ang) * 64 * sc
        hy = ay - math.cos(ang) * 64 * sc
        pygame.draw.line(s, bordo, (ax, ay), (hx, hy), max(2, int(11 * sc)))
        pygame.draw.line(s, maglia, (ax + 1, ay + 1), (hx + 1, hy + 1), max(1, int(8 * sc)))
        pygame.draw.circle(s, pelle, (hx, hy), 6.5 * sc)
        mani.append((hx, hy))
    if braccia == 3 and len(mani) == 2 and col_sciarpa:
        (x1, y1), (x2, y2) = mani
        pygame.draw.rect(s, col_sciarpa, (min(x1, x2), min(y1, y2) - 4 * sc, abs(x2 - x1), 11 * sc))
        pygame.draw.rect(s, riga_sciarpa,
                         (min(x1, x2), min(y1, y2) + 0.5 * sc, abs(x2 - x1), 2.5 * sc))
    # collo e testa
    pygame.draw.rect(s, collo, (cx - 6 * sc, Y(60), 12 * sc, 12 * sc))
    hy = Y(67)
    rx, ry = 11 * sc, 13 * sc
    pygame.draw.ellipse(s, testa_bordo,
                        (cx - rx - 0.8 * sc, hy - ry - 1.2 * sc, 2 * rx + 1.6 * sc, 2 * ry + 1.2 * sc))
    pygame.draw.ellipse(s, pelle, (cx - rx, hy - ry, 2 * rx, 2 * ry))
    if p.acconciatura == 0:        # capelli corti
        pygame.draw.ellipse(s, capelli, (cx - rx * 1.02, hy - ry * 1.1, rx * 2.04, ry * 1.15))
    elif p.acconciatura == 1:      # capelli lunghi
        pygame.draw.ellipse(s, capelli, (cx - rx * 1.15, hy - ry * 1.12, rx * 2.3, ry * 1.2))
        pygame.draw.rect(s, capelli, (cx - rx * 1.15, hy - ry * 0.3, rx * 0.5, ry * 1.4))
        pygame.draw.rect(s, capelli, (cx + rx * 0.65, hy - ry * 0.3, rx * 0.5, ry * 1.4))
    elif p.acconciatura == 3:      # cappellino
        pygame.draw.ellipse(s, cap, (cx - rx * 1.05, hy - ry * 1.15, rx * 2.1, ry * 1.1))
        pygame.draw.rect(s, cap, (cx - rx * 1.2, hy - ry * 0.35, rx * 2.4, ry * 0.3))
    for (mx, my) in mani[:1] if telefono else ():
        pygame.draw.rect(s, (40, 40, 50), (mx - 4 * sc, my - 12 * sc, 8 * sc, 12 * sc))
        pygame.draw.rect(s, (150, 180, 235), (mx - 3 * sc, my - 11 * sc, 6 * sc, 9 * sc))
    return cx, hy


class _Strato:
    """Piano pre-renderizzato a profondita' fissa, ripetuto in x con periodo `larghezza`.

    A ogni frame si proietta il punto (camera.x, z, h): il pixel `ancora` dello
    strato finisce li'. Il pan scorre lo strato con la parallasse della sua z.
    Ogni variante e' una lista di pezzi (superficie, y_locale): la parte con
    trasparenze e' separata da quella piena, che si copia senza alfa (piu' veloce).
    """

    def __init__(self, varianti, z: float, h: float, ancora_v: float, opaco: bool,
                 teste=None):
        self.varianti = [v if isinstance(v, list) else [(v, 0)] for v in varianti]
        self.z = z
        self.h = h
        self.ancora_v = ancora_v
        self.opaco = opaco
        self.larghezza = self.varianti[0][0][0].get_width()
        self.altezza = sum(p[0].get_height() for p in self.varianti[0])
        self.px = _px(z)
        self.teste = teste or []          # [(u, v, scala)] ordinati per u
        self._u = [t[0] for t in self.teste]

    def origine(self, camera, scorrimento: float = 0.0) -> tuple:
        sx, sy = camera.proietta(camera.x, self.z, self.h)
        u_c = (camera.x * self.px + scorrimento) % self.larghezza
        x0 = sx - u_c
        x0 -= math.ceil(x0 / self.larghezza) * self.larghezza   # prima copia a sinistra
        return x0, sy - self.ancora_v

    def disegna(self, superficie: pygame.Surface, camera, variante: int = 0,
                scorrimento: float = 0.0) -> None:
        pezzi = self.varianti[variante % len(self.varianti)]
        x0, y0 = self.origine(camera, scorrimento)
        yi = int(round(y0))
        larg = superficie.get_width()
        if yi >= superficie.get_height() or yi + self.altezza <= 0:
            return
        xs = []
        x = int(round(x0))
        while x < larg:
            xs.append(x)
            x += self.larghezza
        superficie.blits([(img, (x, yi + dy)) for img, dy in pezzi for x in xs], doreturn=False)

    def testa_vicina(self, u: float):
        if not self.teste:
            return None
        i = bisect.bisect_left(self._u, u % self.larghezza)
        return self.teste[i % len(self.teste)]


CHIAVE = (255, 0, 255)            # colore trasparente degli strati (colorkey + RLE)


def _a_chiave(img: pygame.Surface, fondo) -> pygame.Surface:
    """Superficie con alfa -> superficie con colorkey RLE (5x piu' veloce da copiare).

    I bordi antialias vengono fusi su `fondo`, il tono scuro che sta dietro."""
    w, h = img.get_size()
    base = pygame.Surface((w, h), pygame.SRCALPHA)
    base.fill((*fondo, 255))
    base.blit(img, (0, 0))
    maschera = pygame.mask.from_surface(img, 96)
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    maschera.to_surface(out, setsurface=base, unsetcolor=(*CHIAVE, 255))
    rgb = pygame.Surface((w, h))                 # senza alfa anche se manca il display
    rgb.blit(out, (0, 0))
    rgb = _converti(rgb, False)
    rgb.set_colorkey(CHIAVE, pygame.RLEACCEL)
    return rgb


def _genera_folla(file, z_rif: float, h_rif: float, rng: random.Random, luce_file,
                  varianti, y_fine: Optional[float] = None,
                  opaco: bool = False, sfondo=None, decora=None) -> _Strato:
    """Genera uno strato di pubblico (file dal fondo in avanti) con le sue varianti.

    varianti: lista di (livello, fotogramma). Supersampling 2x.
    """
    W = LARGHEZZA_STRATO
    y_top = min(_y_rif(z, h + 222) for z, h in file) - 3     # pugni alzati in piedi
    y_bot = y_fine if y_fine is not None else max(_y_rif(z, h) for z, h in file) + 60.0
    if sfondo is not None:
        y_top = min(y_top, sfondo[0])
    H = int(math.ceil(y_bot - y_top))
    SS = 2
    persone = []
    for z, h in file:
        passo = SEDILE * _px(z)
        n = max(1, int(round(W / passo)))
        passo = W / n
        riga = [_Persona(rng, (i + rng.uniform(-0.3, 0.3)) * passo) for i in range(n)]
        persone.append(riga)
    colori_file = [[_colori_persona(p, luce) for p in riga] for riga, luce in zip(persone, luce_file)]
    immagini = []
    teste = []
    for vi, (livello, fot) in enumerate(varianti):
        if opaco:
            grande = pygame.Surface((W * SS, H * SS))
            grande.fill(SALA)
        else:
            grande = pygame.Surface((W * SS, H * SS), pygame.SRCALPHA)
            grande.fill((0, 0, 0, 0))
        if decora is not None:
            decora(grande, y_top, SS, "prima")
        for fi, ((z, h), riga, luce) in enumerate(zip(file, persone, luce_file)):
            sc = _px(z) * SS
            y_sedile = (_y_rif(z, h + 45) - y_top) * SS
            y_gradino = (_y_rif(z, h + 30) - y_top) * SS
            if fi + 1 < len(file):          # la fila davanti coprira' il resto
                y_fine = (_y_rif(file[fi + 1][0], file[fi + 1][1] + 30) - y_top) * SS + 2 * SS
            else:
                y_fine = H * SS
            pygame.draw.rect(grande, _scala_col(GRADINO, 0.7 + 0.6 * luce),
                             (0, y_gradino, W * SS, y_fine - y_gradino))
            pygame.draw.rect(grande, _scala_col(GRADINO, 1.2 + 0.8 * luce),
                             (0, y_gradino, W * SS, max(1, 2 * SS)))
            for p, colori in zip(riga, colori_file[fi]):
                if p.vuoto:
                    continue
                posa = _posa(p, livello, fot)
                for dup in (-W, 0, W):
                    cx = (p.u + dup) * SS
                    if -60 * SS < cx < (W + 60) * SS:
                        tx, ty = _disegna_persona(grande, p, cx, y_sedile, sc, colori, posa)
                        if vi == 0 and dup == 0:
                            teste.append((tx / SS, ty / SS, sc / SS))
        if decora is not None:
            decora(grande, y_top, SS, "dopo")
        piccola = pygame.transform.smoothscale(grande, (W, H))
        if opaco:
            immagini.append([(_converti(piccola, False), 0)])
        else:
            immagini.append([(_a_chiave(piccola, _scala_col(GRADINO, 0.8 + 0.6 * luce_file[0])), 0)])
    teste.sort()
    ancora_v = _y_rif(z_rif, h_rif) - y_top
    return _Strato(immagini, z_rif, h_rif, ancora_v, opaco, teste)


# ---- sprite di luce (additivi, senza alfa)
def _sfuma(poligoni_da, dim, intensita, colore, passi=28, gamma=1.8, riduzione=4):
    """Disegna una sfumatura morbida: poligoni concentrici a bassa risoluzione + smoothscale."""
    w, h = dim
    pw, ph = max(2, w // riduzione), max(2, h // riduzione)
    s = pygame.Surface((pw, ph))
    s.fill((0, 0, 0))
    for i in range(passi):
        f = 1.0 - i / passi
        v = intensita * (1.0 - f) ** gamma
        pts = [(x / riduzione, y / riduzione) for x, y in poligoni_da(f)]
        if len(pts) >= 3:
            pygame.draw.polygon(s, _scala_col(colore, v / 255.0), pts)
    return _converti(pygame.transform.smoothscale(s, (w, h)), False)


def _sprite_pozza(rx: float, rz: float, z: float, intensita: float, colore):
    """Pozza di luce ellittica sul tappeto centrata in (0, z). Ritorna (sprite, ancora)."""
    k_x = _px
    campioni = 40
    punti_pieni = []
    for i in range(campioni):
        a = i / campioni * math.tau
        punti_pieni.append((math.cos(a), math.sin(a)))
    x_min = -rx * k_x(z - rz) - 4
    x_max = rx * k_x(z - rz) + 4
    y_min = _y_rif(z + rz, 0) - 4
    y_max = _y_rif(z - rz, 0) + 4
    w, h = int(x_max - x_min), int(y_max - y_min)

    def poligono(f):
        out = []
        for c, s_ in punti_pieni:
            zz = z + s_ * rz * f
            out.append((c * rx * f * k_x(zz) - x_min, _y_rif(zz, 0) - y_min))
        return out

    spr = _sfuma(poligono, (w, h), intensita, colore, passi=26, gamma=1.6)
    return spr, (-x_min, _y_rif(z, 0) - y_min)


def _sprite_fascio(x_lampada: float, h_lampada: float, z: float, r_lampada: float,
                   r_terra: float, intensita: float, colore):
    """Fascio di luce nel piano z costante, dalla lampada (x_lampada, h_lampada) al
    punto (0, z, 0). Ritorna (sprite, ancora) con ancora = pixel del punto a terra."""
    k = _px(z)
    y_cima = -70.0
    y_lampada = _y_rif(z, h_lampada)
    y_terra = _y_rif(z, 0)
    t0 = max(0.0, (y_cima - y_lampada) / (y_terra - y_lampada))

    def asse(t):
        return x_lampada * (1 - t) * k, y_lampada + (y_terra - y_lampada) * t

    ax0, ay0 = asse(t0)
    ax1, ay1 = asse(1.0)
    dx, dy = ax1 - ax0, ay1 - ay0
    lung = math.hypot(dx, dy)
    nx, ny = -dy / lung, dx / lung
    if nx < 0:
        nx, ny = -nx, -ny
    r0 = (r_lampada + (r_terra - r_lampada) * t0) * k
    r1 = r_terra * k
    xs = [ax0 - nx * r0, ax0 + nx * r0, ax1 - r1, ax1 + r1]
    x_min, x_max = min(xs) - 6, max(xs) + 6
    y_min, y_max = min(y_cima, ay0 - abs(ny) * r0), ay1 + 2
    w, h = int(x_max - x_min), int(y_max - y_min)

    def poligono(f):
        return [(ax0 - nx * r0 * f - x_min, ay0 - ny * r0 * f - y_min),
                (ax0 + nx * r0 * f - x_min, ay0 + ny * r0 * f - y_min),
                (ax1 + r1 * f - x_min, ay1 - y_min),
                (ax1 - r1 * f - x_min, ay1 - y_min)]

    spr = _sfuma(poligono, (w, h), intensita, colore, passi=22, gamma=1.25)
    # foschia: il fascio compare dall'alto e si spegne sul tappeto (li' c'e' la pozza)
    grad = pygame.Surface((1, 64))
    for i in range(64):
        t = i / 63
        su = 0.45 + 0.55 * min(1.0, t / 0.45)
        giu = 1.0 - max(0.0, min(1.0, (t - 0.5) / 0.5)) ** 1.3
        grad.set_at((0, i), _scala_col((255, 255, 255), su * giu))
    spr.blit(pygame.transform.smoothscale(grad, (w, h)), (0, 0),
             special_flags=pygame.BLEND_MULT)
    return spr, (-x_min, ay1 - y_min)


def _sprite_flash(raggio: float, intensita: float) -> pygame.Surface:
    d = int(raggio * 2 + 2)
    s = pygame.Surface((d, d))
    s.fill((0, 0, 0))
    c = d / 2
    for i in range(12):
        f = 1.0 - i / 12
        v = intensita * (1 - f) ** 2.2
        pygame.draw.circle(s, _scala_col((210, 225, 255), v), (c, c), raggio * f * 0.75)
    v = int(255 * intensita)
    lung = raggio
    col = (int(v * 0.8), int(v * 0.8), min(255, int(v * 0.8) + 20))
    pygame.draw.line(s, col, (c - lung, c), (c + lung, c), 1)
    pygame.draw.line(s, col, (c, c - lung * 0.7), (c, c + lung * 0.7), 1)
    pygame.draw.circle(s, (v, v, v), (c, c), max(1.0, raggio * 0.12))
    return _converti(s, False)


# ---- testo su piano del tappeto (righe con scorrimento prospettico)
class _ScrittaTappeto:
    """Scritta stampata sul tappeto: ogni riga schermo prende la riga di tessitura
    alla sua profondita' e viene spostata alla x proiettata (inclinazione esatta)."""

    def __init__(self, testo: str, x_centro: float, z_vicino: float, z_lontano: float,
                 colore, alfa: int = 255):
        self.x = x_centro
        self.z0, self.z1 = z_vicino, z_lontano
        zm = (z_vicino + z_lontano) / 2
        altezza_mondo = z_lontano - z_vicino
        f = _font(72)
        img = f.render(testo, True, colore)
        rapporto = img.get_width() / max(1, img.get_height() * 0.74)
        self.larghezza_mondo = altezza_mondo * rapporto
        self.px = _px(zm) * 0.97
        w = max(4, int(self.larghezza_mondo * self.px))
        righe = max(8, int((_y_rif(z_vicino, 0) - _y_rif(z_lontano, 0)) * 1.6))
        taglio = img.subsurface((0, int(img.get_height() * 0.12), img.get_width(),
                                 int(img.get_height() * 0.76)))
        tess = pygame.transform.smoothscale(taglio, (w, righe))
        if alfa < 255:
            tess.fill((255, 255, 255, alfa), special_flags=pygame.BLEND_RGBA_MULT)
        self.tessitura = _converti(tess, True)
        self.righe = righe
        self.w = w

    def disegna(self, superficie, camera) -> None:
        a = camera.proietta(self.x, self.z1, 0)[1]
        b = camera.proietta(self.x, self.z0, 0)[1]
        y_a, y_b = int(math.ceil(a)), int(b)
        if y_b < 0 or y_a >= superficie.get_height():
            return
        cx0 = camera.proietta(self.x, self.z0, 0)[0]
        if cx0 + self.w < -50 or cx0 - self.w > superficie.get_width() + 50:
            return
        zoom = camera.zoom
        off_y = camera.offset_y
        lista = []
        mezza = self.w / 2
        for y in range(max(0, y_a), min(superficie.get_height(), y_b + 1)):
            k = ((y - off_y - C.PERNO_ZOOM_Y) / zoom + C.PERNO_ZOOM_Y - C.ORIZZONTE_Y) / C.CAMERA_H
            if k <= 0:
                continue
            z = C.CAMERA_F / k - C.CAMERA_D
            t = (self.z1 - z) / (self.z1 - self.z0)
            r = int(t * self.righe)
            if 0 <= r < self.righe:
                sx = camera.proietta(self.x, z, 0)[0]
                lista.append((self.tessitura, (int(sx - mezza), y), (0, r, self.w, 1)))
        if lista:
            superficie.blits(lista, doreturn=False)


class _CameraRif:
    """Proiezione con zoom dato, centrata su x, senza scossoni (per sprite in cache)."""

    def __init__(self, zoom: float, x: float):
        self.zoom = zoom
        self.x = x

    def scala(self, z: float) -> float:
        return C.CAMERA_F / (z + C.CAMERA_D) * self.zoom

    def proietta(self, x: float, z: float, h: float = 0.0) -> tuple:
        k = C.CAMERA_F / (z + C.CAMERA_D)
        sy = C.ORIZZONTE_Y + (C.CAMERA_H - h) * k
        return (C.LARGHEZZA / 2 + (x - self.x) * k * self.zoom,
                C.PERNO_ZOOM_Y + (sy - C.PERNO_ZOOM_Y) * self.zoom)


# ---- eccitazione del pubblico dagli eventi (aiuto per l'integrazione)
def eccitazione_da_evento(evento) -> float:
    """Intensita' 0..1 suggerita per `Arena.eccita_pubblico` in risposta a un evento."""
    if isinstance(evento, E.KO):
        return 1.0
    if isinstance(evento, E.Atterramento):
        return 0.85
    if isinstance(evento, (E.FinePartita, E.FineRound)):
        return 0.8
    if isinstance(evento, E.ColpoASegno):
        if evento.parato:
            return 0.1
        return min(1.0, 0.25 + 0.6 * evento.forza + (0.2 if evento.contro else 0.0))
    if isinstance(evento, (E.GuardiaRotta, E.SuperPronto)):
        return 0.55
    if isinstance(evento, E.Schivata) and evento.riuscita:
        return 0.35
    if isinstance(evento, E.Via):
        return 0.7
    if isinstance(evento, E.InizioRound):
        return 0.45
    return 0.0


# ---- arena
class Arena:
    """Sala, pubblico, luci e ring. Vedi disegna_sfondo / disegna_primo_piano."""

    def __init__(self, larghezza: int = C.LARGHEZZA, altezza: int = C.ALTEZZA):
        self.larghezza = larghezza
        self.altezza = altezza
        self._rng = random.Random(4242)
        self._eccitazione = 0.0
        self._frame = 0
        self._flash = []              # [strato_i, u, v, eta, taglia]
        self._costruisci_folla()
        self._costruisci_led()
        self._costruisci_luci()
        self._costruisci_ring()
        self._costruisci_lati()
        self._costruisci_primo_piano()
        self._riscalda()

    def _riscalda(self) -> None:
        """Un giro di disegno a vuoto: codifica RLE e cache pronte prima della prima partita."""
        from ..camera import Camera
        prova = pygame.Surface((self.larghezza, self.altezza))
        cam = Camera(self.larghezza, self.altezza)
        for zoom in (C.ZOOM_MIN, C.ZOOM_MAX):
            cam.zoom = zoom
            self.disegna_sfondo(prova, cam, 0.0)
            self.disegna_primo_piano(prova, cam, 0.0)

    # ---------------------------------------------------------------- pubblico
    def _costruisci_folla(self) -> None:
        rng = random.Random(7)
        var = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)]

        def decora_fondo(s, y_top, SS, momento):
            W = s.get_width()
            if momento == "prima":
                # buio della volta con uscite di sicurezza
                y_bal = (_y_rif(BALCONATA[0], BALCONATA[2]) - y_top) * SS
                for i in range(0, int(y_bal), 4):
                    t = i / max(1, y_bal)
                    pygame.draw.rect(s, _mescola((4, 4, 9), (12, 12, 20), t), (0, i, W, 4))
                return
            z, h0, h1 = BALCONATA
            ya = (_y_rif(z, h1) - y_top) * SS
            yb = (_y_rif(z, h0) - y_top) * SS
            pygame.draw.rect(s, (16, 16, 24), (0, ya, W, yb - ya))
            pygame.draw.rect(s, (40, 40, 56), (0, ya, W, 2 * SS))
            # nastro LED della balconata
            nastro = (ya + (yb - ya) * 0.62, (yb - ya) * 0.16)
            pygame.draw.rect(s, (30, 14, 18), (0, nastro[0], W, nastro[1]))
            for i in range(0, W, 7 * SS):
                pygame.draw.rect(s, (120, 30, 36), (i, nastro[0] + SS, 4 * SS, nastro[1] - 2 * SS))
            pygame.draw.rect(s, (8, 8, 12), (0, yb - 2 * SS, W, 2 * SS))
            # striscioni dei tifosi appesi al parapetto
            r2 = random.Random(99)
            f = _font(int((yb - ya) * 0.62))
            x = 40 * SS
            for testo, fondo, inchiostro in STRISCIONI * 2:
                img = f.render(testo, True, _scala_col(inchiostro, 0.46))
                wban = img.get_width() + 16 * SS
                hban = (yb - ya) * 0.78
                if x + wban > W - 30 * SS:
                    break
                yban = ya + (yb - ya) * 0.06 + r2.uniform(0, 3) * SS
                pygame.draw.rect(s, _scala_col(fondo, 0.36), (x, yban, wban, hban))
                pygame.draw.rect(s, _scala_col(fondo, 0.24), (x, yban + hban - 3 * SS, wban, 3 * SS))
                s.blit(img, (x + 8 * SS, yban + (hban - img.get_height()) / 2 + SS))
                x += wban + r2.randint(60, 190) * SS
            # uscite di sicurezza in alto
            fu = _font(9 * SS)
            for ux in (0.13, 0.47, 0.81):
                img = fu.render("USCITA", True, (170, 255, 190))
                bx, by = ux * W, 6 * SS
                pygame.draw.rect(s, (20, 110, 50), (bx - 3 * SS, by - 2 * SS,
                                                    img.get_width() + 6 * SS, img.get_height() + 3 * SS))
                s.blit(img, (bx, by))

        # ogni strato finisce appena sotto il punto in cui quello davanti diventa pieno
        # (margine per lo slittamento relativo con lo zoom): niente pixel copiati due volte
        def pieno(file):
            return _y_rif(file[0][0], file[0][1] + 30) + MARGINE_STRATI

        y_fondo_su = _y_rif(FILE_ANELLO[0][0], FILE_ANELLO[0][1] + 170) - 60
        self._fondo = _genera_folla(FILE_ANELLO, 1650.0, 380.0, rng, (0.12, 0.15, 0.18, 0.21),
                                    [(0, 0)], y_fine=pieno(FILE_TRIBUNA_ALTA), opaco=True,
                                    sfondo=(y_fondo_su, None),
                                    decora=decora_fondo)
        self._tribuna_alta = _genera_folla(FILE_TRIBUNA_ALTA, 1410.0, 120.0, rng,
                                           (0.27, 0.32), var, y_fine=pieno(FILE_TRIBUNA_BASSA))
        self._tribuna_bassa = _genera_folla(FILE_TRIBUNA_BASSA, 1160.0, 0.0, rng,
                                            (0.36, 0.42, 0.48), var, y_fine=pieno(FILE_BORDO))
        self._bordo = _genera_folla(FILE_BORDO, 880.0, -90.0, rng, (0.55, 0.66), var,
                                    y_fine=_y_rif(Z_LED, LED_ALTO) + MARGINE_STRATI)
        self._strati_folla = (self._tribuna_alta, self._tribuna_bassa, self._bordo)
        # la codifica RLE avviene alla prima copia: la si fa subito (niente scatti in partita)
        prova = pygame.Surface((8, 8))
        for strato in self._strati_folla:
            for pezzi in strato.varianti:
                for img, _ in pezzi:
                    prova.blit(img, (0, 0))

    def _costruisci_led(self) -> None:
        SS = 2
        W = LARGHEZZA_STRATO
        y_a = _y_rif(Z_LED, LED_ALTO)
        y_b = _y_rif(Z_LED, LED_BASSO)
        H = int(math.ceil(y_b - y_a)) + 2
        # pavimento sotto la barriera fino al bordo della pedana (che lo copre in parte)
        estensione = int(math.ceil(_y_rif(C.RING_PROFONDITA + BORDO_FONDO, 0) + MARGINE_STRATI - y_b))
        s = pygame.Surface((W * SS, H * SS))
        s.fill((8, 8, 12))
        f = _font(int(H * SS * 0.62))
        pannello = W // 4
        for i in range(4):
            x = i * pannello * SS
            j = (i * 3 + 1) % len(SPONSOR_LED)
            pygame.draw.rect(s, (14, 14, 22), (x + SS, 3 * SS, pannello * SS - 2 * SS, H * SS - 6 * SS))
            img = f.render(SPONSOR_LED[j], True, _scala_col(COLORI_LED[j], 0.62))
            s.blit(img, (x + (pannello * SS - img.get_width()) / 2, (H * SS - img.get_height()) / 2 + SS))
            pygame.draw.rect(s, _scala_col(COLORI_LED[j], 0.55), (x + 6 * SS, H * SS - 7 * SS,
                                                                pannello * SS - 12 * SS, SS))
        for y in range(0, H * SS, 2 * SS):         # trama dei LED
            pygame.draw.line(s, (0, 0, 0), (0, y), (W * SS, y), 1)
        pygame.draw.rect(s, (24, 24, 32), (0, 0, W * SS, 2 * SS))
        pygame.draw.rect(s, (4, 4, 6), (0, H * SS - 2 * SS, W * SS, 2 * SS))
        led = pygame.Surface((W, H + estensione))
        led.fill(PAVIMENTO)
        led.blit(pygame.transform.smoothscale(s, (W, H)), (0, 0))
        self._led = _Strato([_converti(led, False)], Z_LED, LED_ALTO, 0.0, True)

    # ------------------------------------------------------------------- luci
    def _costruisci_luci(self) -> None:
        """Fasci e pozze fusi in un unico sprite additivo ancorato al centro del ring."""
        caldo = (255, 236, 205)
        pezzi = []                       # (sprite, x_schermo_ancora, y_schermo_ancora)
        xc = C.RING_LARGHEZZA / 2

        def metti(spr, anc, x, z):
            sx = C.LARGHEZZA / 2 + (x - xc) * _px(z)
            pezzi.append((spr, sx - anc[0], _y_rif(z, 0) - anc[1]))

        spr, anc = _sprite_pozza(1000.0, 240.0, 212.0, 38, (150, 176, 255))
        metti(spr, anc, xc, 212.0)
        for x_t, z in ((520.0, 250.0), (900.0, 170.0), (1280.0, 250.0)):
            spr, anc = _sprite_pozza(300.0, 150.0, z, 46, caldo)
            metti(spr, anc, x_t, z)
        for x_t, dx_l, z, inten in ((520.0, -640.0, 250.0, 44), (900.0, 0.0, 170.0, 36),
                                    (1280.0, 640.0, 250.0, 44)):
            spr, anc = _sprite_fascio(dx_l, 1500.0, z, 24.0, 240.0, inten, caldo)
            metti(spr, anc, x_t, z)
        margine = 1150
        x_min = max(min(p[1] for p in pezzi), C.LARGHEZZA / 2 - margine)
        x_max = min(max(p[1] + p[0].get_width() for p in pezzi), C.LARGHEZZA / 2 + margine)
        y_min = min(p[2] for p in pezzi)
        y_max = max(p[2] + p[0].get_height() for p in pezzi)
        luci = pygame.Surface((int(x_max - x_min), int(y_max - y_min)))
        luci.fill((0, 0, 0))
        for spr, x, y in pezzi:
            luci.blit(spr, (int(x - x_min), int(y - y_min)), special_flags=pygame.BLEND_ADD)
        self._ancora_luci = (C.LARGHEZZA / 2 - x_min, _y_rif(212.0, 0) - y_min)
        # tessere: si copiano (additive) solo quelle non nere
        self._tessere_luci = []
        tw, th = 128, 96
        for ty in range(0, luci.get_height(), th):
            for tx in range(0, luci.get_width(), tw):
                r = pygame.Rect(tx, ty, tw, th).clip(luci.get_rect())
                pezzo = luci.subsurface(r)
                if pygame.mask.from_threshold(pezzo, (255, 255, 255), (253, 253, 253, 255)).count():
                    self._tessere_luci.append((_converti(pezzo.copy(), False), r.x, r.y))
        self._sprite_flash = []
        for taglia in (9.0, 14.0, 20.0):
            self._sprite_flash.append([_sprite_flash(taglia, v) for v in (1.0, 0.72, 0.45, 0.22)])

    # ------------------------------------------------------------------- ring
    def _costruisci_ring(self) -> None:
        L, P = C.RING_LARGHEZZA, C.RING_PROFONDITA
        self._logo = _poligoni_logo()
        self._logo_bordo = [_offset_poligono(l, 12.0) for l in self._logo]
        self._logo_ombra = [[(x + 9, z - 11) for x, z in l] for l in self._logo_bordo]
        # riflesso: meta' superiore (lontana) di ogni lettera un po' piu' chiara
        self._logo_luce = []
        for l in self._logo:
            zs = [z for _, z in l]
            zm = (min(zs) + max(zs)) / 2 + 30
            self._logo_luce.append(_taglia_poligono(_offset_poligono(l, -7.0), zm))
        cx, cz = _LOGO_CENTRO
        self._ovale = [(cx + math.cos(i / 56 * math.tau) * 340.0,
                        cz + math.sin(i / 56 * math.tau) * 168.0) for i in range(56)]
        n = 16
        self._fasce_tela = [P * i / n for i in range(n + 1)]
        self._colori_tela = []
        for i in range(n):
            t = (i + 0.5) / n
            self._colori_tela.append(_mescola(TELA_VICINO, TELA, t / 0.45) if t < 0.45
                                     else _mescola(TELA, TELA_FONDO, (t - 0.45) / 0.55))
        self._scritte = []
        z0, z1 = P + 20.0, P + BORDO_FONDO - 18.0
        for i, testo in enumerate(SPONSOR_TAPPETO):
            x = L * (i + 0.5) / len(SPONSOR_TAPPETO)
            self._scritte.append(_ScrittaTappeto(testo, x, z0, z1, (150, 154, 170), 230))
        self._scritta_logo = _ScrittaTappeto("WORLD GRAND PRIX", cx, 36.0, 60.0,
                                             (226, 176, 70), 210)
        s = P + SPORGENZA_PALO
        self._pali = (
            (-SPORGENZA_PALO, s, "rosso"), (L + SPORGENZA_PALO, s, "blu"),
            (-SPORGENZA_PALO, -SPORGENZA_PALO, "bianco"), (L + SPORGENZA_PALO, -SPORGENZA_PALO, "bianco"))

    def _costruisci_lati(self) -> None:
        rng = random.Random(55)
        self._spettatori_lato = ([], [])
        for i, lato in enumerate((-1, 1)):
            for fila, dx in enumerate((150.0, 70.0)):        # prima la fila piu' lontana
                riga = []
                z = -120.0 + fila * SEDILE * 0.5
                while z < Z_LED - 40:
                    x = (-X_BARRIERA_LATO - dx) if lato < 0 else (C.RING_LARGHEZZA + X_BARRIERA_LATO + dx)
                    p = _Persona(rng, 0.0)
                    luce = 0.3 + 0.1 * fila
                    amb = 0.07 + 0.52 * luce
                    tono = [_mescola(_scala_col(_desatura(c, 0.35), amb * f), NEBBIA, 0.5 * (1 - luce))
                            for c, f in ((p.maglia, 0.8), (p.pelle, 0.85), (p.capelli, 1.0))]
                    tono.append(_mescola(tono[0], (150, 160, 210), 0.5 + 0.1 * fila))      # spalle in luce
                    riga.append((x, z + rng.uniform(-8, 8), p, tuple(tono)))
                    z += SEDILE * rng.uniform(0.95, 1.2)
                riga.sort(key=lambda t: -t[1])
                self._spettatori_lato[i].append(riga)

    def _costruisci_primo_piano(self) -> None:
        # strisce delle corde anteriori (orizzontali: z e quota costanti)
        self._strisce_corde = []
        spessore = RAGGIO_CORDA * 2 * _px(0.0)
        for col in CORDE_COLORI:
            h = int(math.ceil(spessore)) + 3
            s = pygame.Surface((self.larghezza + 400, h), pygame.SRCALPHA)
            for y in range(h):
                t = (y + 0.5) / h
                if t < 0.1 or t > 0.9:
                    c = (*_scala_col(col, 0.3), int(ALFA_CORDE_DAVANTI * 0.55))
                elif t < 0.3:
                    c = (*_mescola(col, (255, 255, 255), 0.5), ALFA_CORDE_DAVANTI)
                elif t < 0.55:
                    c = (*_scala_col(col, 0.78), ALFA_CORDE_DAVANTI)
                else:
                    c = (*_scala_col(col, 0.42), ALFA_CORDE_DAVANTI)
                s.fill(c, (0, y, s.get_width(), 1))
            self._strisce_corde.append(_converti(s, True))
        self._cache_pali = {}
        # vignettatura moltiplicativa sulle sole colonne laterali (piu' scura in alto)
        W, H = self.larghezza, self.altezza
        bx = int(W * 0.17)
        piccola = pygame.Surface((32, 24))
        for y in range(24):
            for x in range(32):
                d = 1.0 - (x + 0.5) / 32               # 1 al bordo schermo, 0 verso l'interno
                d = d * d * (3 - 2 * d)
                forza = 0.3 + 0.22 * (1.0 - (y + 0.5) / 24)
                piccola.set_at((x, y), _scala_col((255, 255, 255), 1.0 - forza * d))
        col_sx = pygame.transform.smoothscale(piccola, (bx, H))
        col_sx.fill((255, 255, 255), (bx - 1, 0, 1, H))
        self._vignette = ((_converti(col_sx, False), (0, 0)),
                          (_converti(pygame.transform.flip(col_sx, True, False), False), (W - bx, 0)))

    # ------------------------------------------------------------- dinamica
    def aggiorna(self) -> None:
        """Da chiamare una volta per frame: eccitazione e flash fotografici."""
        self._frame += 1
        e = self._eccitazione
        self._eccitazione = max(0.0, e * 0.993 - 0.0012)
        prob = 0.035 + 0.5 * e ** 1.5
        while prob > 0:
            if self._rng.random() < min(1.0, prob):
                self._nuovo_flash()
            prob -= 1.0
        for f in self._flash:
            f[3] += 1
        self._flash = [f for f in self._flash if f[3] < 4]

    def eccita_pubblico(self, intensita: float) -> None:
        """0..1: il pubblico si alza, alza le braccia, scattano i flash."""
        intensita = max(0.0, min(1.0, float(intensita)))
        self._eccitazione = max(self._eccitazione, intensita)
        for _ in range(int(intensita * 12)):
            self._nuovo_flash()

    @property
    def eccitazione(self) -> float:
        return self._eccitazione

    def _nuovo_flash(self) -> None:
        r = self._rng.random()
        i = 0 if r < 0.3 else (1 if r < 0.72 else 2)
        strato = (self._tribuna_alta, self._tribuna_bassa, self._bordo)[i]
        t = strato.testa_vicina(self._rng.uniform(0, strato.larghezza))
        if t is None:
            return
        u, v, _ = t
        v -= self._rng.uniform(0, 14) * strato.px
        self._flash.append([i, u, v, -self._rng.randrange(3), i])

    def _livello_folla(self, tempo: float, strato_i: int) -> int:
        e = self._eccitazione
        livello = 0 if e < 0.28 else (1 if e < 0.62 else 2)
        velocita = (2.2, 3.6, 5.5)[livello]
        fot = int(tempo * velocita + strato_i * 0.37) % 2
        return livello * 2 + fot

    # --------------------------------------------------------------- disegno
    def disegna_sfondo(self, superficie: pygame.Surface, camera, tempo: float) -> None:
        """Tutto cio' che sta dietro ai lottatori: sala, pubblico, tappeto, corde e pali posteriori."""
        W, H = superficie.get_width(), superficie.get_height()
        self._fondo.disegna(superficie, camera)
        for i, strato in enumerate(self._strati_folla):
            strato.disegna(superficie, camera, self._livello_folla(tempo, i))
        self._led.disegna(superficie, camera, 0, tempo * 26.0)
        self._disegna_flash(superficie, camera)
        self._disegna_lati(superficie, camera, tempo)
        self._disegna_tappeto(superficie, camera)
        sx, sy = camera.proietta(C.RING_LARGHEZZA / 2, 212.0, 0)
        ox, oy = int(sx - self._ancora_luci[0]), int(sy - self._ancora_luci[1])
        superficie.blits([(t, (ox + x, oy + y), None, pygame.BLEND_ADD)
                          for t, x, y in self._tessere_luci
                          if -t.get_width() < ox + x < W and -t.get_height() < oy + y < H],
                         doreturn=False)
        self._disegna_corde_fondo(superficie, camera)
        for x, z, col in self._pali[:2]:
            self._disegna_palo(superficie, camera, x, z, col)

    def disegna_primo_piano(self, superficie: pygame.Surface, camera, tempo: float) -> None:
        """Corde e pali anteriori (semitrasparenti) e vignettatura."""
        L = C.RING_LARGHEZZA
        W = superficie.get_width()
        xa = camera.proietta(0.0, 0.0, 0)[0]
        xb = camera.proietta(L, 0.0, 0)[0]
        x0, x1 = max(0, int(xa)), min(W, int(xb) + 1)
        if x1 > x0:
            for h, striscia in zip(ALTEZZE_CORDE, self._strisce_corde):
                y = camera.proietta(0.0, 0.0, h)[1]
                yi = int(round(y - striscia.get_height() / 2))
                superficie.blit(striscia, (x0, yi), (0, 0, x1 - x0, striscia.get_height()))
        for x, z, col in self._pali[2:]:
            self._disegna_palo(superficie, camera, x, z, col, ALFA_PALI_DAVANTI)
        superficie.blits([(img, pos, None, pygame.BLEND_MULT) for img, pos in self._vignette],
                         doreturn=False)

    # -------------------------------------------------------------- dettagli
    def _disegna_flash(self, superficie, camera) -> None:
        if not self._flash:
            return
        strati = (self._tribuna_alta, self._tribuna_bassa, self._bordo)
        origini = {}
        W = superficie.get_width()
        for i, u, v, eta, taglia in self._flash:
            if eta < 0:
                continue
            strato = strati[i]
            if i not in origini:
                origini[i] = strato.origine(camera)
            x0, y0 = origini[i]
            sx = x0 + u
            while sx < -40:
                sx += strato.larghezza
            if sx > W + 40:
                continue
            spr = self._sprite_flash[taglia][min(eta, 3)]
            superficie.blit(spr, (int(sx - spr.get_width() / 2), int(y0 + v - spr.get_height() / 2)),
                            special_flags=pygame.BLEND_ADD)

    def _disegna_tappeto(self, superficie, camera) -> None:
        L, P = C.RING_LARGHEZZA, C.RING_PROFONDITA
        pr = camera.proietta
        W = superficie.get_width()
        # pedana: grembiule (bordo esterno) e tela a fasce (piu' scura verso il fondo)
        xl, xr = -BORDO_LATO, L + BORDO_LATO
        zf, zb = -BORDO_FRONTE, P + BORDO_FONDO
        # faccia anteriore della pedana (si vede solo con gli scossoni verso l'alto)
        ya = pr(xl, zf)[1]
        if ya < superficie.get_height():
            pygame.draw.polygon(superficie, (9, 9, 13), [pr(xl, zf), pr(xr, zf), pr(xr, zf, QUOTA_SALA),
                                                         pr(xl, zf, QUOTA_SALA)])
        # un solo quadrilatero: la tela, disegnata dopo, ne copre il centro (niente fessure sulle giunzioni)
        pygame.draw.polygon(superficie, GREMBIULE, [pr(xl, zf), pr(xr, zf), pr(xr, zb), pr(xl, zb)])
        a, b = pr(xl, zb), pr(xr, zb)
        x0, x1 = max(0, int(a[0])), min(W, int(b[0]) + 1)
        if x1 > x0:
            superficie.fill((40, 40, 54), (x0, int(a[1]), x1 - x0, 1))
        for i, col in enumerate(self._colori_tela):
            za, zb = self._fasce_tela[i], self._fasce_tela[i + 1]
            pygame.draw.polygon(superficie, col, [pr(0, za), pr(L, za), pr(L, zb), pr(0, zb)])
        # filo rosso lungo il bordo della tela: orizzontali pieni, lati antialias
        a, b, c, d = pr(0, 0), pr(L, 0), pr(L, P), pr(0, P)
        for (xa, y), (xb, _) in ((d, c), (a, b)):
            xa, xb = max(0, int(xa)), min(W, int(xb) + 1)
            if xb > xa:
                superficie.fill(LINEA_TELA, (xa, int(y), xb - xa, 2))
        pygame.draw.aaline(superficie, LINEA_TELA, a, d)
        pygame.draw.aaline(superficie, LINEA_TELA, b, c)
        for sc in self._scritte:
            sc.disegna(superficie, camera)
        # ovale dorato, ombra, contorno rosso e riempimento del logo
        gfx.aapolygon(superficie, [(int(x), int(y)) for x, y in
                                   (pr(x, z) for x, z in self._ovale)], ORO)
        for l in self._logo_ombra:
            pygame.draw.polygon(superficie, LOGO_OMBRA, [pr(x, z) for x, z in l])
        for colore, lettere, aa in ((LOGO_BORDO, self._logo_bordo, True), (LOGO_PIENO, self._logo, False)):
            for l in lettere:
                pts = [(int(x + 0.5), int(y + 0.5)) for x, y in (pr(x, z) for x, z in l)]
                pygame.draw.polygon(superficie, colore, pts)
                if aa:                       # solo il bordo esterno (rosso su blu) e' antialias
                    gfx.aapolygon(superficie, pts, colore)
        for l in self._logo_luce:
            pygame.draw.polygon(superficie, LOGO_LUCE, [pr(x, z) for x, z in l])
        self._scritta_logo.disegna(superficie, camera)

    def _disegna_corde_fondo(self, superficie, camera) -> None:
        L, P = C.RING_LARGHEZZA, C.RING_PROFONDITA
        pr = camera.proietta
        W = superficie.get_width()
        # corde laterali (dal palo anteriore a quello posteriore)
        for x in (0.0, L):
            sx_fondo = pr(x, P)[0]
            sx_fronte = pr(x, 0)[0]
            if max(sx_fondo, sx_fronte) < -20 or min(sx_fondo, sx_fronte) > W + 20:
                continue
            for h, col in zip(ALTEZZE_CORDE, CORDE_COLORI):
                self._corda_obliqua(superficie, camera, (x, 0.0, h), (x, P, h), col)
            # legaccio a meta' lato
            a = pr(x, P / 2, ALTEZZE_CORDE[-1])
            b = pr(x, P / 2, ALTEZZE_CORDE[0])
            pygame.draw.line(superficie, (220, 220, 226), a, b, max(1, int(3 * camera.scala(P / 2))))
        # corde posteriori: orizzontali
        s = camera.scala(P)
        xa, xb = pr(0, P)[0], pr(L, P)[0]
        x0, x1 = max(0, int(xa)), min(W, int(xb) + 1)
        spess = max(2, int(round(RAGGIO_CORDA * 2 * s)))
        for h, col in zip(ALTEZZE_CORDE, CORDE_COLORI):
            y = int(round(pr(0, P, h)[1] - spess / 2))
            superficie.fill(_scala_col(col, 0.8), (x0, y, x1 - x0, spess))
            superficie.fill(_mescola(col, (255, 255, 255), 0.5), (x0, y, x1 - x0, 1))
            superficie.fill(_scala_col(col, 0.4), (x0, y + spess - 1, x1 - x0, 1))
        for xt in (L / 3, 2 * L / 3):
            a = pr(xt, P, ALTEZZE_CORDE[-1])
            b = pr(xt, P, ALTEZZE_CORDE[0])
            superficie.fill((200, 200, 208), (int(a[0]) - 1, int(a[1]), max(2, int(3 * s)), int(b[1] - a[1])))

    def _corda_obliqua(self, superficie, camera, a3, b3, col) -> None:
        a = camera.proietta(*a3)
        b = camera.proietta(*b3)
        ra = RAGGIO_CORDA * camera.scala(a3[1])
        rb = RAGGIO_CORDA * camera.scala(b3[1])
        tagliato = _ritaglia(a, b, superficie.get_width(), superficie.get_height(), 12)
        if tagliato is None:
            return
        t0, t1 = tagliato
        dx, dy = b[0] - a[0], b[1] - a[1]
        a, b = (a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1)
        ra, rb = ra + (rb - ra) * t0, ra + (rb - ra) * t1
        lung = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / lung, dx / lung
        if ny > 0:
            nx, ny = -nx, -ny                      # normale verso l'alto dello schermo
        corpo = [(a[0] + nx * ra, a[1] + ny * ra), (b[0] + nx * rb, b[1] + ny * rb),
                 (b[0] - nx * rb, b[1] - ny * rb), (a[0] - nx * ra, a[1] - ny * ra)]
        pygame.draw.polygon(superficie, _scala_col(col, 0.78), corpo)
        pygame.draw.aaline(superficie, _scala_col(col, 0.4), corpo[2], corpo[3])
        pygame.draw.aaline(superficie, _mescola(col, (255, 255, 255), 0.45), corpo[0], corpo[1])

    def _disegna_palo(self, superficie, camera, x: float, z: float, colore: str,
                      alfa: int = 255) -> None:
        """Palo d'angolo: sprite esatto per lo zoom corrente (quantizzato a 1/400), in cache."""
        sx, sy0 = camera.proietta(x, z, 0)
        rc = RAGGIO_CUSCINO * camera.scala(z)
        if sx + rc < -2 or sx - rc > superficie.get_width() + 2:
            return
        livello = int(round(camera.zoom * 400))
        chiave = (x, z, colore, livello)
        voce = self._cache_pali.get(chiave)
        if voce is None:
            if len(self._cache_pali) > 96:
                self._cache_pali.clear()
            cam = _CameraRif(livello / 400.0, x)
            s = cam.scala(z)
            _, b0 = cam.proietta(x, z, 0)
            b1 = cam.proietta(x, z, ALTEZZA_PALO)[1]
            w, h = int(RAGGIO_CUSCINO * s * 2 + 8), int(b0 - b1 + 16)
            spr = pygame.Surface((w, h), pygame.SRCALPHA)
            spr.fill((0, 0, 0, 0))
            oy = b1 - 8
            self._palo_su(spr, cam, w / 2, oy, s, x, z, colore)
            voce = self._cache_pali[chiave] = (_converti(spr, True), w / 2, b0 - oy)
        spr, ax, ay = voce
        spr.set_alpha(alfa if alfa < 255 else None)
        superficie.blit(spr, (int(round(sx - ax)), int(round(sy0 - ay))))

    def _palo_su(self, dst, camera, sx, dy, s, x, z, colore) -> None:
        """Palo d'angolo con cuscino; `dy` sposta le y proiettate (disegno su temporanea)."""
        def Y(h):
            return camera.proietta(x, z, h)[1] - dy
        sy0, sy1 = Y(0), Y(ALTEZZA_PALO)
        rp, rc = RAGGIO_PALO * s, RAGGIO_CUSCINO * s
        # asta d'acciaio con riflesso
        pygame.draw.rect(dst, (18, 18, 24), (sx - rp - 1, sy1, 2 * rp + 2, sy0 - sy1 + 1))
        pygame.draw.rect(dst, ACCIAIO, (sx - rp, sy1, 2 * rp, sy0 - sy1))
        pygame.draw.rect(dst, (150, 156, 172), (sx - rp * 0.45, sy1, max(1, rp * 0.4), sy0 - sy1))
        pygame.draw.ellipse(dst, (120, 124, 140), (sx - rp * 1.3, sy1 - rp * 0.5, rp * 2.6, rp))
        pygame.draw.rect(dst, (22, 22, 28), (sx - rp * 1.6, sy0 - 3 * s, rp * 3.2, 5 * s))
        # cuscino d'angolo (due toni cel + riflesso + fascette alle corde)
        ya, yb = Y(CUSCINO_ALTO), Y(CUSCINO_BASSO)
        col = COLORI_CUSCINO[colore]
        raggio = int(rc * 0.8)
        pygame.draw.rect(dst, (14, 14, 18), (sx - rc - 1.5, ya - 1.5, 2 * rc + 3, yb - ya + 3),
                         border_radius=raggio + 1)
        pygame.draw.rect(dst, _scala_col(col, 0.6), (sx - rc, ya, 2 * rc, yb - ya),
                         border_radius=raggio)
        pygame.draw.rect(dst, col, (sx - rc, ya, 2 * rc * 0.7, yb - ya), border_radius=raggio)
        pygame.draw.rect(dst, _mescola(col, (255, 255, 255), 0.55),
                         (sx - rc * 0.6, ya + rc * 0.45, max(1, rc * 0.26), yb - ya - rc * 0.9),
                         border_radius=max(1, int(rc * 0.13)))
        for h in ALTEZZE_CORDE:
            yy = Y(h)
            pygame.draw.line(dst, _scala_col(col, 0.42), (sx - rc + 1, yy), (sx + rc - 1, yy),
                             max(1, int(2.2 * s)))

    def _disegna_lati(self, superficie, camera, tempo: float) -> None:
        """Pavimento, barriera LED laterale e spettatori a bordo ring (visibili ai lati)."""
        W = superficie.get_width()
        L, P = C.RING_LARGHEZZA, C.RING_PROFONDITA
        pr = camera.proietta
        z_a, z_b = -250.0, Z_LED
        for i, lato in enumerate((-1, 1)):
            x_bordo = -BORDO_LATO if lato < 0 else L + BORDO_LATO
            xf, yf = pr(x_bordo, P + BORDO_FONDO)
            if (xf < 2) if lato < 0 else (xf > W - 2):
                continue
            xn, yn = pr(x_bordo, -BORDO_FRONTE)
            # pavimento: cuneo tra il bordo dello schermo e il bordo della pedana; sconfina di
            # 2 px sotto la pedana (disegnata dopo) per non lasciare fessure sul lato in comune
            d = 2 if lato < 0 else -2
            xe = min(-2, xn - 2) if lato < 0 else max(W + 2, xn + 2)
            pygame.draw.polygon(superficie, PAVIMENTO, [(xe, yf - 1), (xf + d, yf - 1), (xn + d, yn),
                                                        (xn + d, yn + 400), (xe, yn + 400)])
            for fila, riga in enumerate(self._spettatori_lato[i]):
                for x, z, pers, colori in riga:
                    sx = pr(x, z)[0]
                    if (sx < -80) if lato < 0 else (sx > W + 80):
                        break                      # i successivi della fila sono ancora piu' fuori
                    self._disegna_spettatore(superficie, camera, sx, x, z, pers, colori, tempo, fila == 1)
            xb = -X_BARRIERA_LATO if lato < 0 else L + X_BARRIERA_LATO
            # tratto visibile della barriera: da dove esce dallo schermo (di lato o in basso)
            dist = (camera.x - xb) if lato < 0 else (xb - camera.x)
            margine_x = W / 2 + 30 + (camera.offset_x if lato < 0 else -camera.offset_x)
            z_a = -250.0
            if dist > 0:
                z_a = max(z_a, C.CAMERA_F * dist * camera.zoom / margine_x - C.CAMERA_D)
            k_sotto = (((superficie.get_height() + 30 - camera.offset_y - C.PERNO_ZOOM_Y) / camera.zoom
                        + C.PERNO_ZOOM_Y - C.ORIZZONTE_Y) / (C.CAMERA_H - LED_ALTO))
            z_a = max(z_a, C.CAMERA_F / k_sotto - C.CAMERA_D)
            if z_a >= z_b:
                continue
            quad = [pr(xb, z_a, LED_BASSO), pr(xb, z_b, LED_BASSO), pr(xb, z_b, LED_ALTO),
                    pr(xb, z_a, LED_ALTO)]
            pygame.draw.polygon(superficie, (10, 10, 15), quad)
            fascia = [pr(xb, z_a, LED_BASSO + 22), pr(xb, z_b, LED_BASSO + 22),
                      pr(xb, z_b, LED_ALTO - 14), pr(xb, z_a, LED_ALTO - 14)]
            pygame.draw.polygon(superficie, (28, 12, 16), fascia)
            passo = 150.0
            zz = -250.0 + (tempo * 40.0) % passo
            while zz < z_b - 60:
                if zz + 60 > z_a:
                    seg = [pr(xb, zz, LED_BASSO + 26), pr(xb, zz + 60, LED_BASSO + 26),
                           pr(xb, zz + 60, LED_ALTO - 18), pr(xb, zz, LED_ALTO - 18)]
                    pygame.draw.polygon(superficie, (84, 24, 30), seg)
                zz += passo
            pygame.draw.aaline(superficie, (70, 70, 90), quad[3], quad[2])

    def _disegna_spettatore(self, superficie, camera, sx, x, z, pers, colori, tempo, vicino) -> None:
        """Spettatore a bordo ring sul lato: silhouette disegnata al volo (spalle e viso
        illuminati dal lato del ring; la fila vicina ha anche i capelli)."""
        sy = camera.proietta(x, z, QUOTA_SALA + 45)[1]
        s = camera.scala(z) * pers.scala
        if sy - 150 * s > superficie.get_height():
            return
        e = self._eccitazione
        livello = 0 if e < 0.28 else (1 if e < 0.62 else 2)
        alzato, braccia, apertura, _ = _posa(pers, livello, int(tempo * 3 + pers.fase) % 2)
        maglia, pelle, capelli, luce = colori
        verso = 1 if x < C.RING_LARGHEZZA / 2 else -1        # lato rivolto al ring
        y0 = sy - (alzato + pers.alto) * s
        scura = _scala_col(maglia, 0.7)
        if braccia:
            lati = (-1, 1) if braccia >= 2 else ((1 if pers.destro else -1),)
            for lato in lati:
                ax, ay = sx + lato * 17 * s, y0 - 44 * s
                hx = ax + lato * math.sin(apertura) * 62 * s
                hy = ay - math.cos(apertura) * 62 * s
                pygame.draw.line(superficie, maglia, (ax, ay), (hx, hy), max(2, int(10 * s)))
                pygame.draw.circle(superficie, pelle, (hx, hy), max(1.5, 6 * s))
        # busto con spalle arrotondate
        pygame.draw.polygon(superficie, scura, [(sx - 22 * s, y0 - 40 * s), (sx + 22 * s, y0 - 40 * s),
                                                (sx + 19 * s, y0 + 30 * s), (sx - 19 * s, y0 + 30 * s)])
        pygame.draw.ellipse(superficie, maglia, (sx - 25 * s, y0 - 54 * s, 50 * s, 34 * s))
        pygame.draw.rect(superficie, maglia, (sx - 24 * s, y0 - 38 * s, 48 * s, 60 * s))
        # luce di taglio sul lato del ring
        pygame.draw.line(superficie, luce, (sx + verso * 21 * s, y0 - 36 * s),
                         (sx + verso * 18 * s, y0 + 24 * s), max(1, int(4 * s)))
        pygame.draw.arc(superficie, luce, (sx - 25 * s, y0 - 54 * s, 50 * s, 34 * s),
                        math.pi * (0.05 if verso > 0 else 0.55), math.pi * (0.45 if verso > 0 else 0.95),
                        max(1, int(3 * s)))
        # collo e testa
        pygame.draw.rect(superficie, _scala_col(pelle, 0.7), (sx - 5 * s, y0 - 64 * s, 10 * s, 14 * s))
        pygame.draw.ellipse(superficie, pelle, (sx - 12.5 * s, y0 - 92 * s, 25 * s, 30 * s))
        pygame.draw.ellipse(superficie, _scala_col(pelle, 1.25),
                            (sx + verso * 4 * s - 4 * s, y0 - 84 * s, 8 * s, 16 * s))
        pygame.draw.ellipse(superficie, capelli, (sx - 13 * s, y0 - 93.5 * s, 26 * s, 15 * s))
