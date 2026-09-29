"""Effetti d'impatto nel mondo: scintille, sudore, parate, polvere, testi, lampi.

Tutte le particelle vivono in coordinate mondo (x, z, h) e vengono proiettate con
la camera a ogni disegno, quindi seguono pan, zoom e scossoni. Le luci (bagliori,
anelli) sono sprite additivi pre-renderizzati e messi in cache per taglia.
"""

from __future__ import annotations

import math
import random
from typing import Optional

import pygame

from .. import costanti as C
from .. import eventi as E

# ---- parametri
GRAVITA = 0.55                    # unita' mondo / frame^2 (verso il basso)
MAX_PARTICELLE = 420
MAX_LUCI = 40                     # bagliori e anelli contemporanei
COL_SCINTILLA = ((255, 255, 250), (255, 236, 150), (255, 170, 60))
COL_PARATA = (110, 210, 255)
COL_CONTRO = (255, 120, 40)
COL_SUPER = (255, 206, 70)
COL_SUDORE = (205, 232, 255)
COL_POLVERE = (150, 156, 176)
COL_SCHEGGE = (170, 225, 255)

TESTI = {
    "contro": ("CONTRO!", (255, 150, 60), (255, 236, 170)),
    "schivata": ("SCHIVATA!", (90, 210, 255), (225, 250, 255)),
    "guardia_rotta": ("GUARDIA ROTTA!", (255, 196, 40), (255, 246, 190)),
    "super": ("SUPER!", (255, 196, 40), (255, 255, 210)),
}


def _converti(s: pygame.Surface, alfa: bool) -> pygame.Surface:
    try:
        return s.convert_alpha() if alfa else s.convert()
    except pygame.error:
        return s


def _scala_col(c, f: float):
    return (min(255, max(0, int(c[0] * f))), min(255, max(0, int(c[1] * f))),
            min(255, max(0, int(c[2] * f))))


def _mescola(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _font(dim: int) -> pygame.font.Font:
    if not pygame.font.get_init():
        pygame.font.init()
    return pygame.font.Font(None, dim)


# ---- sprite in cache
class _Cache:
    """Bagliori additivi e sbuffi di polvere per taglia quantizzata (passo 10-12%).

    L'intensita' di un bagliore si applica al momento: copia su una superficie
    temporanea, moltiplicazione, somma additiva (tre copie di pochi pixel)."""

    def __init__(self):
        self._bagliori = {}
        self._sbuffi = {}
        self._base_bagliore = {}
        self._base_sbuffo = None
        self._tmp = pygame.Surface((64, 64))
        self._grigio = pygame.Surface((64, 64))

    def _base(self, colore):
        b = self._base_bagliore.get(colore)
        if b is None:
            r = 64
            s = pygame.Surface((r * 2, r * 2))
            s.fill((0, 0, 0))
            for i in range(32):
                f = 1.0 - i / 32
                v = (1.0 - f) ** 2.3
                pygame.draw.circle(s, _mescola(_scala_col(colore, v), (255, 255, 255), v ** 3),
                                   (r, r), r * f)
            b = self._base_bagliore[colore] = s
        return b

    def bagliore(self, colore, raggio_px: float) -> Optional[pygame.Surface]:
        if raggio_px < 1.5:
            return None
        kr = min(52, int(round(math.log(raggio_px) / math.log(1.1))))
        chiave = (colore, kr)
        s = self._bagliori.get(chiave)
        if s is None:
            d = max(3, int(1.1 ** kr * 2))
            s = _converti(pygame.transform.smoothscale(self._base(colore), (d, d)), False)
            self._bagliori[chiave] = s
        return s

    def somma_bagliore(self, dst: pygame.Surface, colore, cx: float, cy: float,
                       raggio_px: float, intensita: float) -> None:
        """Somma (BLEND_ADD) un bagliore centrato in (cx, cy) con l'intensita' data."""
        if intensita <= 0.02:
            return
        spr = self.bagliore(colore, raggio_px)
        if spr is None:
            return
        w, h = spr.get_size()
        x, y = int(cx - w / 2), int(cy - h / 2)
        if x >= dst.get_width() or y >= dst.get_height() or x + w <= 0 or y + h <= 0:
            return
        if intensita >= 0.97:
            dst.blit(spr, (x, y), special_flags=pygame.BLEND_ADD)
            return
        if w > self._tmp.get_width() or h > self._tmp.get_height():
            dim = (max(w, self._tmp.get_width()), max(h, self._tmp.get_height()))
            self._tmp = _converti(pygame.Surface(dim), False)
            self._grigio = _converti(pygame.Surface(dim), False)
        tmp, grigio = self._tmp, self._grigio
        tmp.blit(spr, (0, 0))
        v = int(255 * intensita)
        grigio.fill((v, v, v), (0, 0, w, h))        # fill semplice + blit MULT: 4x piu' veloce
        tmp.blit(grigio, (0, 0), (0, 0, w, h), special_flags=pygame.BLEND_MULT)
        dst.blit(tmp, (x, y), (0, 0, w, h), special_flags=pygame.BLEND_ADD)

    def sbuffo(self, raggio_px: float) -> Optional[pygame.Surface]:
        if raggio_px < 1.5:
            return None
        if self._base_sbuffo is None:
            r = 40
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            s.fill((0, 0, 0, 0))
            for i in range(20):
                f = 1.0 - i / 20
                a = int(255 * (1.0 - f) ** 1.6)
                pygame.draw.circle(s, (*_mescola(COL_POLVERE, (210, 214, 226), 1 - f), a),
                                   (r, r), r * f)
            self._base_sbuffo = s
        kr = int(round(math.log(raggio_px) / math.log(1.12)))
        s = self._sbuffi.get(kr)
        if s is None:
            d = max(3, int(1.12 ** kr * 2))
            s = self._sbuffi[kr] = _converti(pygame.transform.smoothscale(self._base_sbuffo, (d, d)), True)
        return s

    def prepara(self, colori, raggio_max: float = 150.0) -> None:
        """Crea in anticipo le taglie comuni (evita scatti al primo colpo)."""
        r = 2.0
        while r <= raggio_max:
            for c in colori:
                self.bagliore(c, r)
            self.sbuffo(r * 0.6)
            r *= 1.1


def _testo_stilizzato(testo: str, colore, chiaro, dim: int = 58) -> pygame.Surface:
    """Testo pesante: sfumatura verticale, contorno scuro spesso e ombra."""
    f = _font(dim)
    bianco = f.render(testo, True, (255, 255, 255))
    w, h = bianco.get_size()
    grad = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        c = _mescola(chiaro, colore, min(1.0, t * 1.6)) if t < 0.62 else _scala_col(colore, 1.0 - (t - 0.62) * 0.7)
        grad.fill((*c, 255), (0, y, w, 1))
    pieno = bianco.copy()
    pieno.blit(grad, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    nero = f.render(testo, True, (12, 10, 16))
    b = 4
    out = pygame.Surface((w + b * 2 + 4, h + b * 2 + 5), pygame.SRCALPHA)
    out.fill((0, 0, 0, 0))
    ombra = nero.copy()
    ombra.set_alpha(150)
    out.blit(ombra, (b + 4, b + 5))
    for dx in range(-b, b + 1):
        for dy in range(-b, b + 1):
            if dx * dx + dy * dy <= b * b + 1:
                out.blit(nero, (b + dx, b + dy))
    out.blit(pieno, (b, b))
    return _converti(pygame.transform.rotozoom(out, 4, 1.0), True)


# ---- effetti
class Effetti:
    """Particelle e testi nel mondo, lampi a schermo e scossoni di camera."""

    def __init__(self, camera):
        self.camera = camera
        self._rng = random.Random(2024)
        self._cache = _Cache()
        self._testi_base = {}
        self._scintille = []     # [x, z, h, vx, vh, vita, vita_max, largh, lung]
        self._punti = []         # [x, z, h, vx, vz, vh, vita, vita_max, raggio, colore]
        self._gocce = []         # [x, z, h, vx, vz, vh, vita, raggio]
        self._schegge = []       # [x, z, h, vx, vz, vh, vita, vita_max, lato, ang, vang]
        self._polvere = []       # [x, z, h, vx, vz, vh, vita, vita_max, raggio, crescita]
        self._bagliori = []      # [x, z, h, vita, vita_max, raggio, colore, crescita]
        self._anelli = []        # [x, z, h, vita, vita_max, r0, r1, colore, a_terra]
        self._testi = []         # [x, z, h, vita, vita_max, chiave, pop]
        self._lampo = 0.0
        self._lampo_colore = (255, 255, 255)
        self._tmp = pygame.Surface((256, 256))
        self._pop = {}           # (chiave, scala quantizzata) -> superficie
        self._velo = None        # superficie del lampo a tutto schermo
        for chiave, (testo, col, chiaro) in TESTI.items():
            self._testi_base[chiave] = _testo_stilizzato(testo, col, chiaro)
        self._cache.prepara((COL_SCINTILLA[1], COL_PARATA, COL_SUPER, COL_CONTRO))
        self._riscalda()

    def _riscalda(self) -> None:
        """Disegna una volta ogni tipo di effetto su una superficie a vuoto: cache pronte."""
        dim = (getattr(self.camera, "larghezza", C.LARGHEZZA), getattr(self.camera, "altezza", C.ALTEZZA))
        prova = pygame.Surface(dim)
        x, z = C.RING_LARGHEZZA / 2, 200.0
        for chiave in TESTI:
            self.testo(chiave, x, z, 250)
        for chiave in TESTI:
            for i in range(12, 34):
                self._immagine_testo(chiave, i * 0.05)
        self.bagliore(x, z, 150, 100, COL_SCINTILLA[1], 8)
        self.bagliore(x + 50, z, 150, 140, COL_PARATA, 8)
        self.anello(x, z, 150, 14, 90, COL_PARATA, 8)
        self.anello_a_terra(x, z, 40, 300, COL_SUPER, 8)
        self.scintille(x, z, 150, 1.0, 12)
        self.punti(x, z, 150, 1.0, 6)
        self.sudore(x, z, 150, 1.0, 6)
        self.schegge(x, z, 150, 6)
        self.polvere(x, z, 6, 1.0)
        self.scintillio(x, z, 250, 6)
        self.lampo(0.5)
        for _ in range(9):
            self.aggiorna()
            self.disegna_mondo(prova)
            self.disegna_schermo(prova)
        self._azzera()

    def _immagine_testo(self, chiave: str, q: float) -> pygame.Surface:
        q = round(q * 20) / 20
        img = self._pop.get((chiave, q))
        if img is None:
            base = self._testi_base[chiave]
            img = self._pop[(chiave, q)] = pygame.transform.smoothscale(
                base, (max(1, int(base.get_width() * q)), max(1, int(base.get_height() * q))))
        return img

    def _azzera(self) -> None:
        self._scintille, self._punti, self._gocce = [], [], []
        self._schegge, self._polvere, self._bagliori = [], [], []
        self._anelli, self._testi = [], []
        self._lampo = 0.0
        self._rng = random.Random(2024)

    # ------------------------------------------------------------ utilita'
    @staticmethod
    def _lottatore(incontro, indice):
        try:
            return incontro.lottatori[indice]
        except (AttributeError, IndexError, TypeError):
            return None

    def _conta(self) -> int:
        return (len(self._scintille) + len(self._punti) + len(self._gocce) + len(self._schegge)
                + len(self._polvere))

    def _posti(self, n: int) -> int:
        """Quante particelle nuove entrano ancora sotto il limite MAX_PARTICELLE."""
        return max(0, min(n, MAX_PARTICELLE - self._conta()))

    def scuoti(self, intensita: float, durata: int) -> None:
        self.camera.scuoti(intensita, durata)

    def lampo(self, intensita: float, colore=(255, 255, 255)) -> None:
        if intensita > self._lampo:
            self._lampo = min(1.0, intensita)
            self._lampo_colore = colore

    # ------------------------------------------------------------ eventi
    def gestisci_evento(self, evento, incontro) -> None:
        """Traduce un evento della simulazione in effetti (e scossoni di camera)."""
        if isinstance(evento, E.ColpoASegno):
            self._colpo(evento, incontro)
        elif isinstance(evento, E.Schivata):
            l = self._lottatore(incontro, evento.indice)
            if l is None:
                return
            if evento.riuscita:
                self.testo("schivata", l.x, l.z, getattr(l, "altezza_mondo", C.ALTEZZA_BASE) + 22, l)
                self._scia(l)
            else:
                self.polvere(l.x, l.z, 4, 0.5)
        elif isinstance(evento, E.GuardiaRotta):
            l = self._lottatore(incontro, evento.indice)
            if l is None:
                return
            alt = getattr(l, "altezza_mondo", C.ALTEZZA_BASE)
            self.testo("guardia_rotta", l.x, l.z, alt + 22, l)
            self.schegge(l.x + (18 if getattr(l, "guarda_destra", True) else -18), l.z, alt * 0.74)
            self.bagliore(l.x, l.z, alt * 0.74, 70, COL_PARATA, 12)
            self.lampo(0.22, (170, 220, 255))
            self.scuoti(9, 16)
        elif isinstance(evento, E.Atterramento):
            l = self._lottatore(incontro, evento.indice)
            if l is None:
                return
            verso = -1.0 if getattr(l, "guarda_destra", True) else 1.0
            for i in range(5):
                self.polvere(l.x + verso * (20 + i * 38), l.z + self._rng.uniform(-15, 15), 4, 1.1)
            self.anello_a_terra(l.x + verso * 60, l.z, 40, 170, (200, 210, 240), 22)
            self.scuoti(11, 18)
            self.lampo(0.15)
        elif isinstance(evento, E.KO):
            l = self._lottatore(incontro, evento.indice)
            self.lampo(0.85)
            self.scuoti(24, 34)
            if l is not None:
                verso = -1.0 if getattr(l, "guarda_destra", True) else 1.0
                for i in range(7):
                    self.polvere(l.x + verso * (10 + i * 36), l.z + self._rng.uniform(-20, 20), 3, 1.5)
                self.anello_a_terra(l.x + verso * 70, l.z, 50, 320, (255, 236, 190), 30)
        elif isinstance(evento, E.SuperPronto):
            l = self._lottatore(incontro, evento.indice)
            if l is None:
                return
            alt = getattr(l, "altezza_mondo", C.ALTEZZA_BASE)
            self.testo("super", l.x, l.z, alt + 26, l)
            self.anello_a_terra(l.x, l.z, 30, 150, COL_SUPER, 26)
            self.scintillio(l.x, l.z, alt, 26)
        elif isinstance(evento, E.AttaccoIniziato):
            if evento.mossa == "calcio_girato":
                l = self._lottatore(incontro, evento.indice)
                if l is not None:
                    alt = getattr(l, "altezza_mondo", C.ALTEZZA_BASE)
                    self.anello_a_terra(l.x, l.z, 20, 130, COL_SUPER, 20)
                    self.bagliore(l.x, l.z, alt * 0.55, 110, COL_SUPER, 14, crescita=0.02)
                    self.scintillio(l.x, l.z, alt, 16)
        elif isinstance(evento, E.Rialzo):
            l = self._lottatore(incontro, evento.indice)
            if l is not None:
                self.polvere(l.x, l.z, 3, 0.7)
        elif isinstance(evento, E.Passo):
            l = self._lottatore(incontro, evento.indice)
            if l is not None and self._rng.random() < 0.5:
                self.polvere(l.x, l.z, 1, 0.35)

    def _colpo(self, ev, incontro) -> None:
        att = self._lottatore(incontro, ev.attaccante)
        dif = self._lottatore(incontro, ev.difensore)
        verso = 1.0
        if att is not None and dif is not None and dif.x != att.x:
            verso = 1.0 if dif.x > att.x else -1.0
        elif att is not None:
            verso = 1.0 if getattr(att, "guarda_destra", True) else -1.0
        f = max(0.0, min(1.0, ev.forza))
        x, z, h = ev.x, ev.z, ev.h
        if ev.parato:
            self.anello(x, z, h, 14 + 10 * f, 62 + 42 * f, COL_PARATA, 14)
            self.anello(x, z, h, 8, 34 + 22 * f, (200, 240, 255), 9)
            self.bagliore(x, z, h, 40 + 34 * f, COL_PARATA, 9)
            self.scintille(x, z, h, verso, 5 + int(6 * f), 0.55, COL_PARATA)
            self.scuoti(2.5 + 4 * f, 7)
            return
        forza_vis = f + (0.25 if ev.contro else 0.0)
        self.bagliore(x, z, h, 34 + 62 * forza_vis, COL_SCINTILLA[1], 8 + int(5 * f), crescita=0.04)
        self.scintille(x, z, h, verso, 9 + int(20 * forza_vis), 0.6 + 0.7 * f)
        self.punti(x, z, h, verso, 4 + int(10 * f))
        pesante = f >= 0.45 or ev.contro
        if pesante or (ev.livello == "alto" and f >= 0.3):
            hx, hz, hh = x, z, h
            if dif is not None and ev.livello != "alto":
                hx, hz = dif.x, dif.z
                hh = getattr(dif, "altezza_mondo", C.ALTEZZA_BASE) * 0.9
            self.sudore(hx, hz, hh, verso, 4 + int(12 * f))
        if ev.contro:
            self.anello(x, z, h, 20, 110, COL_CONTRO, 12)
            if dif is not None:
                self.testo("contro", dif.x, dif.z, getattr(dif, "altezza_mondo", C.ALTEZZA_BASE) + 22, dif)
        if f >= 0.7 or ev.contro:
            self.lampo(0.12 + 0.22 * f)
        self.scuoti(3 + 13 * f + (4 if ev.contro else 0), int(8 + 10 * f))

    # ------------------------------------------------------------ emettitori
    def scintille(self, x, z, h, verso, n, forza=1.0, colore=None) -> None:
        """Strisce radiali (bianco/giallo) sbilanciate nella direzione del colpo."""
        rng = self._rng
        for _ in range(self._posti(n)):
            if rng.random() < 0.75:
                ang = rng.gauss(0, 0.75)
                dx = math.cos(ang) * verso
            else:
                ang = rng.uniform(-math.pi, math.pi)
                dx = math.cos(ang)
            dh = math.sin(ang) + rng.uniform(-0.2, 0.35)
            v = rng.uniform(7.0, 19.0) * (0.7 + 0.6 * forza)
            vita = rng.randint(7, 14)
            self._scintille.append([x, z + rng.uniform(-6, 6), h, dx * v, dh * v, vita, vita,
                                    rng.uniform(1.8, 3.4) * (0.8 + 0.5 * forza),
                                    rng.uniform(2.2, 3.6), colore])

    def punti(self, x, z, h, verso, n) -> None:
        rng = self._rng
        for _ in range(self._posti(n)):
            ang = rng.uniform(-1.2, 1.2)
            v = rng.uniform(3, 9)
            vita = rng.randint(14, 26)
            self._punti.append([x, z, h, math.cos(ang) * v * verso, rng.uniform(-1, 1),
                                math.sin(ang) * v + 3, vita, vita, rng.uniform(1.2, 2.2),
                                rng.choice(COL_SCINTILLA)])

    def sudore(self, x, z, h, verso, n) -> None:
        rng = self._rng
        for _ in range(self._posti(n)):
            ang = rng.uniform(-0.5, 1.2)
            v = rng.uniform(3.0, 8.5)
            self._gocce.append([x + rng.uniform(-8, 8), z + rng.uniform(-8, 8), h + rng.uniform(-10, 12),
                                math.cos(ang) * v * verso, rng.uniform(-1.5, 1.5),
                                math.sin(ang) * v + 2.5, rng.randint(24, 40), rng.uniform(1.4, 2.8)])

    def schegge(self, x, z, h, n: int = 16) -> None:
        rng = self._rng
        for _ in range(self._posti(n)):
            ang = rng.uniform(0, math.tau)
            v = rng.uniform(4, 11)
            vita = rng.randint(18, 30)
            self._schegge.append([x, z, h, math.cos(ang) * v, rng.uniform(-2, 2), math.sin(ang) * v + 3,
                                  vita, vita, rng.uniform(5, 11), rng.uniform(0, math.tau),
                                  rng.uniform(-0.4, 0.4)])

    def polvere(self, x, z, n: int = 4, forza: float = 1.0) -> None:
        rng = self._rng
        for _ in range(self._posti(n)):
            vita = rng.randint(28, 46)
            self._polvere.append([x + rng.uniform(-18, 18), z + rng.uniform(-10, 10), rng.uniform(4, 14),
                                  rng.uniform(-2.2, 2.2) * forza, rng.uniform(-0.8, 0.8) * forza,
                                  rng.uniform(0.3, 1.3) * forza, vita, vita,
                                  rng.uniform(14, 24) * (0.6 + 0.5 * forza), 0.9 + 0.5 * forza])

    def scintillio(self, x, z, altezza, n) -> None:
        """Pagliuzze dorate che salgono attorno al lottatore (super)."""
        rng = self._rng
        for _ in range(self._posti(n)):
            vita = rng.randint(26, 48)
            self._punti.append([x + rng.uniform(-50, 50), z + rng.uniform(-12, 12),
                                rng.uniform(0.1, 0.9) * altezza, rng.uniform(-0.6, 0.6), 0.0,
                                rng.uniform(1.2, 3.2) + GRAVITA * 0.8, vita, vita,
                                rng.uniform(1.4, 2.6), COL_SUPER])

    def _scia(self, l) -> None:
        """Scia d'aria della schivata riuscita: strisce orizzontali azzurre."""
        rng = self._rng
        alt = getattr(l, "altezza_mondo", C.ALTEZZA_BASE)
        verso = -1.0 if getattr(l, "guarda_destra", True) else 1.0
        for _ in range(self._posti(7)):
            self._scintille.append([l.x + rng.uniform(-30, 30), l.z, rng.uniform(0.3, 0.95) * alt,
                                    verso * rng.uniform(6, 10), 0.0, 10, 10, 1.6, 4.5, COL_PARATA])

    def bagliore(self, x, z, h, raggio, colore, vita, crescita: float = 0.03) -> None:
        if len(self._bagliori) >= MAX_LUCI:
            del self._bagliori[0]
        self._bagliori.append([x, z, h, vita, vita, raggio, colore, crescita])

    def anello(self, x, z, h, r0, r1, colore, vita) -> None:
        if len(self._anelli) >= MAX_LUCI:
            del self._anelli[0]
        self._anelli.append([x, z, h, vita, vita, r0, r1, colore, False])

    def anello_a_terra(self, x, z, r0, r1, colore, vita) -> None:
        if len(self._anelli) >= MAX_LUCI:
            del self._anelli[0]
        self._anelli.append([x, z, 0.0, vita, vita, r0, r1, colore, True])

    def testo(self, chiave: str, x, z, h, lottatore=None) -> None:
        """Testo nel mondo che sale e svanisce ('contro', 'schivata', 'guardia_rotta', 'super').

        Con `lottatore` il testo si sposta verso la schiena del lottatore; se ne
        incontra un altro ancora giovane e vicino, si impila sopra."""
        if chiave not in self._testi_base:
            testo, col, chiaro = TESTI[chiave]
            self._testi_base[chiave] = _testo_stilizzato(testo, col, chiaro)
        if lottatore is not None:
            x -= 45.0 if getattr(lottatore, "guarda_destra", True) else -45.0
        self._testi = [t for t in self._testi if t[5] != chiave or t[3] < t[4] - 12]
        for t in self._testi:
            if abs(t[0] - x) < 280 and abs(t[2] - h) < 46 and t[3] > 16:
                h = t[2] + 48
        self._testi.append([x, z, h, 56, 56, chiave, None])

    # ------------------------------------------------------------ dinamica
    def aggiorna(self) -> None:
        """Avanza tutte le particelle di un frame (60 Hz)."""
        vive = []
        for p in self._scintille:
            p[0] += p[3]
            p[2] += p[4]
            p[3] *= 0.86
            p[4] = p[4] * 0.86 - GRAVITA * 0.35
            p[5] -= 1
            if p[5] > 0:
                vive.append(p)
        self._scintille = vive
        vive = []
        for p in self._punti:
            p[0] += p[3]
            p[1] += p[4]
            p[2] += p[5]
            p[3] *= 0.94
            p[5] -= GRAVITA * (0.1 if p[9] is COL_SUPER else 1.0)
            p[6] -= 1
            if p[6] > 0 and p[2] > -5:
                vive.append(p)
        self._punti = vive
        vive = []
        for p in self._gocce:
            p[0] += p[3]
            p[1] += p[4]
            p[2] += p[5]
            p[5] -= GRAVITA
            p[6] -= 1
            if p[6] > 0 and p[2] > 0:
                vive.append(p)
        self._gocce = vive
        vive = []
        for p in self._schegge:
            p[0] += p[3]
            p[1] += p[4]
            p[2] += p[5]
            p[3] *= 0.95
            p[5] -= GRAVITA
            p[9] += p[10]
            p[6] -= 1
            if p[6] > 0 and p[2] > 0:
                vive.append(p)
        self._schegge = vive
        vive = []
        for p in self._polvere:
            p[0] += p[3]
            p[1] += p[4]
            p[2] += p[5]
            p[3] *= 0.95
            p[4] *= 0.95
            p[5] *= 0.97
            p[8] += p[9] * 0.35
            p[6] -= 1
            if p[6] > 0:
                vive.append(p)
        self._polvere = vive
        for lista in (self._bagliori, self._anelli, self._testi):
            for p in lista:
                p[3] -= 1
        self._bagliori = [p for p in self._bagliori if p[3] > 0]
        self._anelli = [p for p in self._anelli if p[3] > 0]
        for t in self._testi:
            t[2] += 1.1 * (t[3] / t[4]) + 0.3
        self._testi = [t for t in self._testi if t[3] > 0]
        self._lampo = max(0.0, self._lampo * 0.72 - 0.02)

    def attivi(self) -> int:
        """Numero di elementi vivi (particelle, luci, testi)."""
        return self._conta() + len(self._bagliori) + len(self._anelli) + len(self._testi)

    # ------------------------------------------------------------ disegno
    def disegna_mondo(self, superficie: pygame.Surface) -> None:
        """Particelle e testi nel mondo (da chiamare dopo i lottatori)."""
        cam = self.camera
        pr = cam.proietta
        sc = cam.scala
        cache = self._cache
        W, H = superficie.get_width(), superficie.get_height()
        # polvere (sbuffi con alfa)
        for x, z, h, _, _, _, vita, vmax, r, _ in self._polvere:
            sx, sy = pr(x, z, h)
            spr = cache.sbuffo(r * sc(z))
            if spr is None:
                continue
            t = vita / vmax
            spr.set_alpha(int(175 * min(1.0, t * 1.8) * min(1.0, (1 - t) * 6 + 0.2)))
            superficie.blit(spr, (int(sx - spr.get_width() / 2), int(sy - spr.get_height() / 2)))
        # anelli (parata, contro, onde a terra) additivi
        for x, z, h, vita, vmax, r0, r1, col, a_terra in self._anelli:
            t = 1.0 - vita / vmax
            r = r0 + (r1 - r0) * (1 - (1 - t) ** 2.2)
            intens = (1.0 - t) ** 1.2
            self._disegna_anello(superficie, x, z, h, r, col, intens, a_terra)
        # gocce di sudore
        for x, z, h, vx, vz, vh, vita, r in self._gocce:
            s = sc(z)
            sx, sy = pr(x, z, h)
            tx, ty = pr(x - vx * 1.6, z, h - vh * 1.6)
            rr = max(1.0, r * s)
            pygame.draw.line(superficie, (120, 160, 200), (tx, ty), (sx, sy), max(1, int(rr)))
            pygame.draw.circle(superficie, COL_SUDORE, (sx, sy), rr)
            pygame.draw.circle(superficie, (255, 255, 255), (sx - rr * 0.3, sy - rr * 0.3), max(0.8, rr * 0.4))
        # schegge della guardia rotta
        for x, z, h, _, _, _, vita, vmax, lato, ang, _ in self._schegge:
            s = sc(z)
            sx, sy = pr(x, z, h)
            l = lato * s * (0.5 + 0.5 * vita / vmax)
            pts = [(sx + math.cos(ang + k * 2.2) * l, sy + math.sin(ang + k * 2.2) * l * 0.8) for k in range(3)]
            pygame.draw.polygon(superficie, COL_SCHEGGE, pts)
            pygame.draw.aalines(superficie, (255, 255, 255), True, pts)
        # punti caldi e pagliuzze
        for x, z, h, _, _, _, vita, vmax, r, col in self._punti:
            sx, sy = pr(x, z, h)
            rr = r * sc(z)
            if col is COL_SUPER:
                tw = 0.55 + 0.45 * math.sin(vita * 0.9 + x)
                cache.somma_bagliore(superficie, COL_SUPER, sx, sy, rr * 5.0,
                                     tw * min(1.0, vita / vmax * 2.5))
            else:
                pygame.draw.circle(superficie, _mescola(col, (255, 110, 40), 1 - vita / vmax),
                                   (sx, sy), max(1.0, rr))
        # bagliori d'impatto (additivi) con fiammate a stella nei primi frame
        for x, z, h, vita, vmax, r, col, cresc in self._bagliori:
            t = 1.0 - vita / vmax
            s_z = sc(z)
            raggio = r * s_z * (0.7 + 0.45 * min(1.0, t * 3) + cresc * t * 10)
            sx, sy = pr(x, z, h)
            cache.somma_bagliore(superficie, col, sx, sy, raggio, (1.0 - t) ** 1.6)
            if t < 0.4:
                lung = raggio * (0.95 - t)
                larg = max(1.5, raggio * 0.07 * (1 - t * 2))
                c = _mescola((255, 255, 255), col, t * 2.2)
                for k in range(6):
                    a = k * math.pi / 3 + 0.3 + t * 0.8 + x * 0.01
                    ca, sa = math.cos(a), math.sin(a)
                    l = lung * (1.0 if k % 2 == 0 else 0.55)
                    pygame.draw.polygon(superficie, c, [
                        (sx - sa * larg, sy + ca * larg), (sx + ca * l, sy + sa * l * 0.85),
                        (sx + sa * larg, sy - ca * larg)])
        # scintille: strisce affusolate bianco -> giallo -> arancio
        for x, z, h, vx, vh, vita, vmax, largh, lung, col in self._scintille:
            s = sc(z)
            sx, sy = pr(x, z, h)
            tx, ty = pr(x - vx * lung, z, h - vh * lung)
            t = vita / vmax
            if col is None:
                c = COL_SCINTILLA[0] if t > 0.66 else (COL_SCINTILLA[1] if t > 0.33 else COL_SCINTILLA[2])
            else:
                c = _mescola(col, (255, 255, 255), t * 0.6)
            w = max(1.0, largh * s * (0.4 + 0.6 * t))
            dx, dy = sx - tx, sy - ty
            d = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / d * w, dx / d * w
            pygame.draw.polygon(superficie, c, [(sx + nx, sy + ny), (sx - nx, sy - ny), (tx, ty)])
            pygame.draw.circle(superficie, c, (sx, sy), w)
        # testi che salgono e svaniscono
        for x, z, h, vita, vmax, chiave, _ in self._testi:
            eta = vmax - vita
            pop = 1.0 + 0.55 * max(0.0, 1.0 - eta / 7.0) ** 2
            q = round((0.62 + 0.38 * sc(z) / sc(0)) * pop * 20) / 20
            img = self._immagine_testo(chiave, q)
            sx, sy = pr(x, z, h)
            img.set_alpha(int(255 * min(1.0, vita / 14.0)))
            superficie.blit(img, (int(sx - img.get_width() / 2), int(sy - img.get_height())))

    def _disegna_anello(self, superficie, x, z, h, r, col, intens, a_terra) -> None:
        cam = self.camera
        if a_terra:
            pts = [cam.proietta(x + math.cos(a) * r, z + math.sin(a) * r * 0.55, 0)
                   for a in (i / 28 * math.tau for i in range(28))]
        else:
            sx, sy = cam.proietta(x, z, h)
            rr = r * cam.scala(z)
            pts = [(sx + math.cos(a) * rr, sy + math.sin(a) * rr * 0.9)
                   for a in (i / 24 * math.tau for i in range(24))]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, y0 = int(min(xs)) - 4, int(min(ys)) - 4
        w, hgt = int(max(xs)) - x0 + 5, int(max(ys)) - y0 + 5
        if w <= 0 or hgt <= 0 or x0 > superficie.get_width() or y0 > superficie.get_height():
            return
        if w > self._tmp.get_width() or hgt > self._tmp.get_height():
            self._tmp = pygame.Surface((max(w, self._tmp.get_width()), max(hgt, self._tmp.get_height())))
        tmp = self._tmp
        tmp.fill((0, 0, 0), (0, 0, w, hgt))
        loc = [(px - x0, py - y0) for px, py in pts]
        spess = max(1, int((3 if a_terra else 4) * intens + 1))
        pygame.draw.polygon(tmp, _scala_col(col, 0.55 * intens), loc, spess + 2)
        pygame.draw.aalines(tmp, _scala_col(_mescola(col, (255, 255, 255), 0.5), intens), True, loc)
        superficie.blit(tmp, (x0, y0), (0, 0, w, hgt), special_flags=pygame.BLEND_ADD)

    def disegna_schermo(self, superficie: pygame.Surface) -> None:
        """Lampi a tutto schermo (dopo l'HUD)."""
        if self._lampo > 0.01:
            v = self._lampo
            c = self._lampo_colore
            dim = superficie.get_size()
            if self._velo is None or self._velo.get_size() != dim:
                self._velo = _converti(pygame.Surface(dim), False)
            # fill semplice + blit additivo (fill con BLEND_ADD e' ~9 volte piu' lento)
            self._velo.fill((int(c[0] * v), int(c[1] * v), int(c[2] * v)))
            superficie.blit(self._velo, (0, 0), special_flags=pygame.BLEND_ADD)
