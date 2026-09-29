"""Disegno dei lottatori: kickboxer vettoriali cel-shading dallo scheletro animato.

`RendererLottatore` traduce lo stato di un `Lottatore` (o una posa d'anteprima) in
un'immagine: la posa viene ricavata da `pose.anima`, risolta da `scheletro.calcola`
e dipinta a strati (arto lontano, busto e testa, arto vicino) su una superficie
temporanea ingrandita (supersampling) che poi si rimpicciolisce con smoothscale
sulla sola bounding box: bordi morbidi senza scalettature.

Convenzione di profondita': il lottatore guarda a destra (specchiato se serve);
braccio e gamba ANTERIORI sono dal lato lontano dalla camera (piu' scuri, dietro il
busto), quelli POSTERIORI dal lato vicino (davanti al busto). L'arto che colpisce
viene sempre disegnato sopra a tutto.
"""

from __future__ import annotations

import math
from typing import Optional

import pygame

from .. import costanti as C
from ..personaggi import Personaggio
from ..sim.lottatore import Lottatore
from ..sim.mosse import MOSSE
from . import pose as PZ
from . import scheletro as S

CONTORNO = (17, 12, 20)
LUCE = (0.5, 0.87)                 # direzione della luce nel riferimento locale (avanti, alto)
_LN = math.hypot(*LUCE)
LUCE = (LUCE[0] / _LN, LUCE[1] / _LN)


# ---- colori
def _scura(c, f):
    return (max(0, min(255, int(c[0] * f))), max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def _chiara(c, f):
    return (max(0, min(255, int(c[0] + (255 - c[0]) * f))), max(0, min(255, int(c[1] + (255 - c[1]) * f))),
            max(0, min(255, int(c[2] + (255 - c[2]) * f))))


def _mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _ombra_calda(c, f=0.72):
    """Ombra di un colore: piu' scura e leggermente spostata verso il viola."""
    return (max(0, int(c[0] * f * 0.98)), max(0, int(c[1] * f * 0.86)), max(0, int(c[2] * f * 0.92)))


class Tavolozza:
    """Colori derivati di un personaggio (con la palette alternativa se richiesta)."""

    def __init__(self, p: Personaggio, alt: bool):
        pel = p.pelle
        self.pelle = pel
        self.pelle_o = _ombra_calda(pel, 0.70)
        self.pelle_l = _chiara(pel, 0.16)
        self.lontano = _mix(_ombra_calda(pel, 0.60), (40, 30, 50), 0.22)
        self.lontano_o = _ombra_calda(self.lontano, 0.70)
        pant = p.pantaloncini_alt if alt else p.pantaloncini
        bordo = p.bordo_alt if alt else p.bordo_pantaloncini
        gu = p.guantoni_alt if alt else p.guantoni
        self.pant = pant
        self.pant_o = _ombra_calda(pant, 0.62)
        self.pant_l = _chiara(pant, 0.22)
        self.pant_lont = _mix(_scura(pant, 0.62), (30, 26, 44), 0.2)
        self.pant_lont_o = _ombra_calda(self.pant_lont, 0.7)
        self.bordo = bordo
        self.bordo_o = _ombra_calda(bordo, 0.65)
        self.bordo_lont = _scura(bordo, 0.62)
        self.gu = gu
        self.gu_o = _ombra_calda(gu, 0.6)
        self.gu_l = _chiara(gu, 0.35)
        self.gu_lont = _mix(_scura(gu, 0.6), (30, 24, 42), 0.2)
        self.gu_lont_o = _ombra_calda(self.gu_lont, 0.68)
        self.fasce = p.fasce
        self.fasce_o = _ombra_calda(p.fasce, 0.7)
        self.fasce_lont = _scura(p.fasce, 0.62)
        self.capelli = p.capelli
        self.capelli_o = _ombra_calda(p.capelli, 0.62)
        self.capelli_l = _chiara(p.capelli, 0.22)
        self.top = p.top
        if p.top is not None:
            self.top_o = _ombra_calda(p.top, 0.62)
            self.top_l = _chiara(p.top, 0.2)
            self.top_lont = _scura(p.top, 0.6)
        else:
            self.top_o = self.top_l = self.top_lont = None
        self.accento = p.colore_ui


class Proporzioni:
    """Larghezze del corpo in frazioni di altezza, dalla corporatura."""

    def __init__(self, p: Personaggio):
        c = p.corporatura
        self.c = c
        self.k = c ** 1.1                 # spessore degli arti
        self.donna = p.top is not None
        self.busto = c ** 0.95
        self.vita = c ** 0.55
        self.testa = 1.0


class _Memoria:
    """Stato per-lottatore del renderer: fusione tra pose, coda, scie."""

    def __init__(self):
        self.chiave = None
        self.posa_da = None
        self.t_cambio = -9.0
        self.posa_ultima = None
        self.t_ultimo = None
        self.coda_ang = 30.0
        self.coda_vel = 0.0
        self.testa_prec = None
        self.scia = []
        self.hit_frame = -1


# ============================================================ pennello
class _Pennello:
    """Disegna in coordinate locali (u, v) su una superficie ingrandita."""

    def __init__(self, surf, ox, oy, S_, dx, ow):
        self.s = surf
        self.ox = ox
        self.oy = oy
        self.S = S_
        self.dx = dx
        self.ow = ow

    def pt(self, u, v):
        return (self.ox + self.dx * u * self.S, self.oy - v * self.S)

    # ---- primitive in pixel
    def _cerchio(self, col, p, r):
        pygame.draw.circle(self.s, col, (int(p[0] + 0.5), int(p[1] + 0.5)), max(1, int(r + 0.5)))

    def _capsula(self, col, a, ra, b, rb):
        s = self.s
        ax, ay = a
        bx, by = b
        dx = bx - ax
        dy = by - ay
        d = math.hypot(dx, dy)
        if d > 0.5:
            nx = -dy / d
            ny = dx / d
            pygame.draw.polygon(s, col, ((ax + nx * ra, ay + ny * ra), (bx + nx * rb, by + ny * rb),
                                         (bx - nx * rb, by - ny * rb), (ax - nx * ra, ay - ny * ra)))
        self._cerchio(col, a, ra)
        self._cerchio(col, b, rb)

    def catena_px(self, col, pts, rad):
        s = self.s
        n = len(pts)
        for i in range(n - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            ra = rad[i]
            rb = rad[i + 1]
            dx = bx - ax
            dy = by - ay
            d = math.hypot(dx, dy)
            if d > 0.5:
                nx = -dy / d
                ny = dx / d
                pygame.draw.polygon(s, col, ((ax + nx * ra, ay + ny * ra), (bx + nx * rb, by + ny * rb),
                                             (bx - nx * rb, by - ny * rb), (ax - nx * ra, ay - ny * ra)))
        for i in range(n):
            pygame.draw.circle(s, col, (int(pts[i][0] + 0.5), int(pts[i][1] + 0.5)), max(1, int(rad[i] + 0.5)))

    # ---- forme solide con contorno e ombreggiatura cel
    def solido(self, punti, raggi, base, ombra, luce_k=0.24, lit_scala=0.8, contorno=CONTORNO, ow=None):
        """Una catena di cerchi: contorno, colore d'ombra, colore di luce spostato verso la luce."""
        return self.multi([(punti, raggi)], base, ombra, luce_k, lit_scala, contorno, ow)

    def multi(self, catene, base, ombra, luce_k=0.24, lit_scala=0.8, contorno=CONTORNO, ow=None):
        """Piu' catene disegnate insieme, passata per passata (nessuna cucitura interna)."""
        S_ = self.S
        ow = self.ow if ow is None else ow
        px = []
        for punti, raggi in catene:
            px.append(([self.pt(u, v) for (u, v) in punti], [r * S_ for r in raggi]))
        for pp, rr in px:
            self.catena_px(contorno, pp, [r + ow for r in rr])
        for pp, rr in px:
            self.catena_px(ombra, pp, rr)
        if base is not None:
            lx = LUCE[0] * self.dx
            ly = -LUCE[1]
            for pp, rr in px:
                sh = [(p[0] + lx * r * luce_k, p[1] + ly * r * luce_k) for p, r in zip(pp, rr)]
                self.catena_px(base, sh, [r * lit_scala for r in rr])
        return px

    def cerchio_solido(self, c, r, base, ombra, luce_k=0.26, lit_scala=0.78, ow=None):
        return self.solido([c], [r], base, ombra, luce_k, lit_scala, ow=ow)

    def poligono(self, punti, col, contorno=CONTORNO, ow=None, chiuso=True):
        pp = [self.pt(u, v) for (u, v) in punti]
        ow = self.ow if ow is None else ow
        if contorno is not None:
            # contorno: poligono ingrandito attorno al baricentro + linee spesse
            pygame.draw.polygon(self.s, contorno, pp)
            pygame.draw.lines(self.s, contorno, True, pp, max(1, int(ow * 2)))
            for p in pp:
                self._cerchio(contorno, p, ow)
        pygame.draw.polygon(self.s, col, pp)
        return pp

    def poligono_cel(self, punti, base, ombra, luce_k=0.07, riduzione=0.88, ow=None):
        """Poligono con contorno, colore d'ombra e colore di luce ridotto e spostato."""
        pp = [self.pt(u, v) for (u, v) in punti]
        ow = self.ow if ow is None else ow
        s = self.s
        pygame.draw.polygon(s, CONTORNO, pp)
        pygame.draw.lines(s, CONTORNO, True, pp, max(1, int(ow * 2)))
        for q in pp:
            pygame.draw.circle(s, CONTORNO, (int(q[0] + 0.5), int(q[1] + 0.5)), max(1, int(ow)))
        pygame.draw.polygon(s, ombra, pp)
        if base is not None:
            n = len(pp)
            cx = sum(q[0] for q in pp) / n
            cy = sum(q[1] for q in pp) / n
            ext = max(math.hypot(q[0] - cx, q[1] - cy) for q in pp)
            lx = LUCE[0] * self.dx * ext * luce_k
            ly = -LUCE[1] * ext * luce_k
            pygame.draw.polygon(s, base, [(cx + (q[0] - cx) * riduzione + lx, cy + (q[1] - cy) * riduzione + ly)
                                          for q in pp])
        return pp

    def pantaloncino(self, centro, r0, punti, base, ombra):
        """Trapezio svasato con un cerchio all'attacco: una sola forma con contorno unico."""
        s = self.s
        ow = self.ow
        pp = [self.pt(u, v) for (u, v) in punti]
        c = self.pt(*centro)
        r = r0 * self.S
        ci = (int(c[0] + 0.5), int(c[1] + 0.5))
        pygame.draw.polygon(s, CONTORNO, pp)
        pygame.draw.lines(s, CONTORNO, True, pp, max(1, int(ow * 2)))
        for q in pp:
            pygame.draw.circle(s, CONTORNO, (int(q[0] + 0.5), int(q[1] + 0.5)), max(1, int(ow)))
        pygame.draw.circle(s, CONTORNO, ci, int(r + ow))
        pygame.draw.polygon(s, ombra, pp)
        pygame.draw.circle(s, ombra, ci, int(r))
        n = len(pp)
        cx = sum(q[0] for q in pp) / n
        cy = sum(q[1] for q in pp) / n
        ext = max(math.hypot(q[0] - cx, q[1] - cy) for q in pp)
        lx = LUCE[0] * self.dx * ext * 0.06
        ly = -LUCE[1] * ext * 0.06
        pygame.draw.polygon(s, base, [(cx + (q[0] - cx) * 0.9 + lx, cy + (q[1] - cy) * 0.9 + ly) for q in pp])
        pygame.draw.circle(s, base, (ci[0] + int(lx * 0.5), ci[1] + int(ly * 0.5)), int(r * 0.9))

    def banda(self, a, b, spessore, col, col_o=None, ow=None):
        """Banda dritta (senza estremi tondi) centrata sul segmento a-b."""
        pa = self.pt(*a)
        pb = self.pt(*b)
        d = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) or 1.0
        nx = -(pb[1] - pa[1]) / d * spessore * self.S
        ny = (pb[0] - pa[0]) / d * spessore * self.S
        quad = [(pa[0] + nx, pa[1] + ny), (pb[0] + nx, pb[1] + ny), (pb[0] - nx, pb[1] - ny), (pa[0] - nx, pa[1] - ny)]
        ow = self.ow if ow is None else ow
        s = self.s
        pygame.draw.polygon(s, CONTORNO, quad)
        pygame.draw.lines(s, CONTORNO, True, quad, max(1, int(ow * 2)))
        for q in quad:
            pygame.draw.circle(s, CONTORNO, (int(q[0] + 0.5), int(q[1] + 0.5)), max(1, int(ow)))
        pygame.draw.polygon(s, col, quad)
        if col_o is not None:
            pygame.draw.polygon(s, col_o, [quad[2], quad[3], ((quad[3][0] + quad[0][0]) / 2, (quad[3][1] + quad[0][1]) / 2),
                                           ((quad[2][0] + quad[1][0]) / 2, (quad[2][1] + quad[1][1]) / 2)])

    def linea(self, col, a, b, w):
        pa = self.pt(*a)
        pb = self.pt(*b)
        pygame.draw.line(self.s, col, pa, pb, max(1, int(w * self.S)))

    def fascia(self, a, b, spessore, col, col_o, ow=None):
        """Fascia (polsino/cintura) come capsula tra due punti locali."""
        S_ = self.S
        ow = self.ow if ow is None else ow
        pa = self.pt(*a)
        pb = self.pt(*b)
        r = spessore * S_
        self._capsula(CONTORNO, pa, r + ow, pb, r + ow)
        self._capsula(col_o, pa, r, pb, r)
        lx = LUCE[0] * self.dx
        ly = -LUCE[1]
        self._capsula(col, (pa[0] + lx * r * 0.25, pa[1] + ly * r * 0.25), r * 0.72,
                      (pb[0] + lx * r * 0.25, pb[1] + ly * r * 0.25), r * 0.72)


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _norm(v):
    d = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / d, v[1] / d)


# ============================================================ renderer
class RendererLottatore:
    """Disegna i lottatori. Un'istanza va bene per tutti e due i lottatori."""

    MARGINE = 0.20

    def __init__(self, supersample: int = 2):
        self.ss = max(1, int(supersample))
        self._mem: dict = {}
        self._tavolozze: dict = {}
        self._prop: dict = {}
        self._buf: Optional[pygame.Surface] = None
        self._dest: Optional[pygame.Surface] = None
        self._tex_ombra: Optional[pygame.Surface] = None
        self._tex_aura: dict = {}
        self._anteprima: dict = {}

    # ------------------------------------------------------------ cache
    def _tav(self, p: Personaggio, alt: bool) -> Tavolozza:
        k = (p.id, alt)
        t = self._tavolozze.get(k)
        if t is None:
            t = self._tavolozze[k] = Tavolozza(p, alt)
        return t

    def _pro(self, p: Personaggio) -> Proporzioni:
        t = self._prop.get(p.id)
        if t is None:
            t = self._prop[p.id] = Proporzioni(p)
        return t

    def _superfici(self, w: int, h: int):
        """Superficie ingrandita (w x h) e di destinazione (w/ss x h/ss), riusate."""
        ss = self.ss
        if self._buf is None or self._buf.get_width() < w or self._buf.get_height() < h:
            nw = max(w, self._buf.get_width() if self._buf else 0, 512)
            nh = max(h, self._buf.get_height() if self._buf else 0, 512)
            self._buf = pygame.Surface((nw, nh), pygame.SRCALPHA, 32)
            self._dest = pygame.Surface((nw // ss + 1, nh // ss + 1), pygame.SRCALPHA, 32)
        return self._buf, self._dest

    # ------------------------------------------------------------ API pubblica
    def disegna_ombra(self, superficie, lottatore, camera) -> None:
        """Ombra morbida sul tappeto (da disegnare PRIMA dei lottatori)."""
        l = lottatore
        sx, sy = camera.proietta(l.x, l.z, 0.0)
        sc = camera.scala(l.z)
        H = l.altezza_mondo
        a_terra = l.stato in ('atterrato', 'ko', 'rialzo')
        rx = (0.20 * H) * sc * self._pro(l.personaggio).busto ** 0.5
        cx = sx
        alpha = 150
        if a_terra:
            f = 1.0
            if l.stato == 'atterrato':
                f = PZ.sfuma(l.frame_stato, 0, 22)
            elif l.stato == 'ko':
                f = PZ.sfuma(l.frame_stato, 0, 26)
            elif l.stato == 'rialzo':
                f = 1.0 - PZ.sfuma(l.frame_stato, 4, 30)
            rx = rx + (0.50 * H * sc - rx) * f
            cx = sx + (-1 if l.guarda_destra else 1) * (0.06 * H * sc) * f
        elif l.stato == 'attacco' and l.dati_mossa is not None and l.dati_mossa.arto.startswith('gamba'):
            rx *= 1.1
        elif l.stato == 'schivata':
            rx *= 0.95
        dz = 26.0
        ry = abs(camera.proietta(l.x, l.z - dz, 0.0)[1] - camera.proietta(l.x, l.z + dz, 0.0)[1]) * 0.5
        ry = max(ry, rx * 0.16)
        self._ombra(superficie, cx, sy, rx, ry, alpha)

    def _ombra(self, superficie, cx, cy, rx, ry, alpha):
        if self._tex_ombra is None:
            n = 96
            t = pygame.Surface((n, n // 2), pygame.SRCALPHA, 32)
            for i in range(14, 0, -1):
                f = i / 14.0
                a = int(255 * (1.0 - f) ** 0.9 * 0.95)
                pygame.draw.ellipse(t, (0, 0, 0, a), (int(n / 2 * (1 - f)), int(n / 4 * (1 - f)),
                                                        max(2, int(n * f)), max(2, int(n / 2 * f))))
            self._tex_ombra = t
        w = max(4, int(rx * 2.2))
        h = max(3, int(ry * 2.2))
        if w > 3000 or h > 1200:
            return
        img = pygame.transform.smoothscale(self._tex_ombra, (w, h))
        img.set_alpha(alpha)
        superficie.blit(img, (int(cx - w / 2), int(cy - h * 0.5)))

    def disegna(self, superficie, lottatore, camera, tempo: float, avversario=None) -> None:
        l = lottatore
        sx, sy = camera.proietta(l.x, l.z, l.h)
        E = l.altezza_mondo * camera.scala(l.z)
        if sx < -E * 1.6 or sx > superficie.get_width() + E * 1.6 or sy < -E or sy > superficie.get_height() + E * 0.5:
            return
        mem = self._mem.get(id(l))
        if mem is None:
            mem = self._mem[id(l)] = _Memoria()
        anim = PZ.anima(l, tempo, avversario)
        self._fondi(mem, anim, tempo)
        if l.in_hitstop:
            n = int(tempo * 60.0) & 1
            ampl = anim.tremore or 0.006
            sx += (ampl * E) * (1.0 if n else -1.0)
            sy += (ampl * E * 0.35) * (-1.0 if n else 1.0)
        if l.stato == 'colpito':
            anim.flash = max(anim.flash, PZ.clamp01(1.0 - l.frame_stato / 3.0) * 0.9)
        anim.aura = 1.0 if l.energia >= C.ENERGIA_MAX - 1e-6 else 0.0
        if l.stato == 'schivata' and l.invulnerabile:
            anim.alpha = 0.6
        self._pittura(superficie, l.personaggio, l.palette_alternativa, sx, sy, E, l.guarda_destra,
                      anim, tempo, mem)

    def disegna_anteprima(self, superficie, personaggio, centro: tuple, altezza_px: float,
                          posa: str = 'guardia', tempo: float = 0.0, guarda_destra: bool = True,
                          palette_alternativa: bool = False) -> None:
        """Disegna il lottatore in una posa (guardia, vittoria, intro, mosse o stati).

        `centro` e' il centro del corpo in piedi (meta' altezza), `altezza_px` la sua altezza.
        """
        l = self._lottatore_anteprima(personaggio, palette_alternativa, guarda_destra)
        self._imposta_posa(l, posa, tempo)
        E = float(altezza_px)
        sx = centro[0]
        sy = centro[1] + E * 0.5
        anim = PZ.anima(l, tempo, None)
        anim.aura = 0.0
        chiave = (personaggio.id, palette_alternativa, posa)
        mem = self._anteprima.get(chiave)
        if mem is None:
            mem = self._anteprima[chiave] = _Memoria()
        self._fondi(mem, anim, tempo)
        self._pittura(superficie, personaggio, palette_alternativa, sx, sy, E, guarda_destra, anim, tempo, mem)

    # ------------------------------------------------------------ anteprima
    def _lottatore_anteprima(self, personaggio, alt, destra):
        k = (personaggio.id, alt)
        l = self._anteprima.get(k)
        if l is None:
            l = self._anteprima[k] = Lottatore(0, personaggio, alt, x=900.0, z=210.0, guarda_destra=True)
        l.guarda_destra = bool(destra)
        return l

    def _imposta_posa(self, l, posa: str, tempo: float) -> None:
        """Porta il lottatore d'anteprima nella posa richiesta, con un ciclo su `tempo`."""
        from ..sim.lottatore import STATI
        fps = 60.0
        f = int(max(0.0, tempo) * fps)
        l.punto_impatto = None
        l.in_hitstop = False
        l.direzione_cammino = 0
        l.direzione_profondita = 0
        l.colpo_subito = None
        l.forza_colpo_subito = 0.6
        l.tipo_schivata = None
        if posa in MOSSE:
            m = MOSSE[posa]
            ciclo = m.durata + 34
            l.imposta_mossa(posa, min(f % ciclo, m.durata - 1))
            if f % ciclo >= m.durata:
                l.imposta_stato('guardia')
            return
        if posa == 'guardia' or posa not in STATI:
            l.imposta_stato('guardia')
            return
        durate = {'intro': 110, 'cammina': 72, 'colpito': 26, 'bloccato': 20, 'schivata': 22,
                  'guardia_rotta': 45, 'atterrato': 100, 'rialzo': 40, 'ko': 120, 'vittoria': 200,
                  'sconfitta': 200}
        d = durate.get(posa, 60)
        l.imposta_stato(posa, d if posa in ('intro', 'colpito', 'bloccato', 'schivata', 'guardia_rotta',
                                            'atterrato', 'rialzo') else 0)
        if posa == 'cammina':
            l.direzione_cammino = 1
        if posa == 'schivata':
            l.tipo_schivata = 'indietro'
            l.direzione_cammino = -1
        if posa == 'colpito':
            l.colpo_subito = 'alto'
        l.frame_stato = f % d if posa not in ('vittoria', 'sconfitta', 'ko') else min(f, d * 10)

    # ------------------------------------------------------------ fusione tra pose
    def _fondi(self, mem: _Memoria, anim, tempo: float) -> None:
        if mem.chiave is None:
            mem.chiave = anim.chiave
            mem.t_cambio = -9.0
        elif anim.chiave != mem.chiave:
            mem.posa_da = mem.posa_ultima
            mem.t_cambio = tempo
            mem.chiave = anim.chiave
        p = anim.posa
        if mem.posa_da is not None and anim.fusione > 0:
            w = (tempo - mem.t_cambio) / anim.fusione
            if 0.0 <= w < 1.0:
                q = S.mescola(mem.posa_da, p, PZ._io(w))
                q['Ls'] = p['Ls']
                q['Rs'] = p['Rs']
                anim.posa = p = q
            elif w >= 1.0:
                mem.posa_da = None
        mem.posa_ultima = p

    # ------------------------------------------------------------ pittura
    def _pittura(self, superficie, pers, alt, sx, sy, E, destra, anim, tempo, mem) -> None:
        tav = self._tav(pers, alt)
        pro = self._pro(pers)
        p = anim.posa
        sk = S.calcola(p, anim.bers)
        ss = self.ss
        M = self.MARGINE
        # ---- bounding box locale
        us = []
        vs = []
        for nome in ('anca', 'spalle', 'testa', 'manoL', 'manoR', 'puntaF', 'puntaB', 'talloneF', 'talloneB',
                     'ginocchioF', 'ginocchioB', 'gomitoL', 'gomitoR', 'cavigliaF', 'cavigliaB'):
            q = sk[nome]
            us.append(q[0])
            vs.append(q[1])
        umin = min(us) - 0.09
        umax = max(us) + 0.09
        vmin = min(vs) - 0.06
        vmax = max(vs) + 0.13
        if anim.stelle:
            vmax += 0.12
        if pers.stile_capelli == 'coda':
            umin -= 0.10
        umin -= M * 0.4
        umax += M * 0.4
        vmin -= M * 0.4
        vmax += M * 0.4
        S_ = E * ss
        if S_ < 1.0:
            return
        dx = 1 if destra else -1
        # origine locale (0,0) nel buffer, in pixel, con parte frazionaria della posizione a schermo
        if dx > 0:
            ox0 = -umin * S_
            larg = (umax - umin) * S_
        else:
            ox0 = umax * S_
            larg = (umax - umin) * S_
        oy0 = vmax * S_
        alt_px = (vmax - vmin) * S_
        bx = math.floor(sx - ox0 / ss)
        by = math.floor(sy - oy0 / ss)
        ox = (sx - bx) * ss
        oy = (sy - by) * ss
        W = int(larg) + 2 * ss
        Hh = int(alt_px) + 2 * ss
        W += (-W) % ss
        Hh += (-Hh) % ss
        if W > 3600 or Hh > 3600:
            return
        buf, dest = self._superfici(W, Hh)
        area = buf.subsurface((0, 0, W, Hh))
        area.fill((CONTORNO[0], CONTORNO[1], CONTORNO[2], 0))
        ow = max(1.5, 0.0135 * S_)
        pen = _Pennello(area, ox, oy, S_, dx, ow)
        # ---- coda di cavallo: molla che segue il movimento della testa
        coda = None
        if pers.stile_capelli == 'coda':
            coda = self._molla_coda(mem, sk, tempo)
        _dipingi(pen, sk, p, anim, pro, tav, pers, coda, mem)
        # ---- riduzione
        w = W // ss
        h = Hh // ss
        d = dest.subsurface((0, 0, w, h))
        pygame.transform.smoothscale(area, (w, h), d)
        if anim.flash > 0.0:
            v = int(210 * anim.flash)
            d.fill((v, v, v, 0), special_flags=pygame.BLEND_RGB_ADD)
        if anim.alpha < 0.999:
            d.set_alpha(int(255 * anim.alpha))
        else:
            d.set_alpha(255)
        if anim.aura > 0.0:
            self._aura(superficie, tempo, sx, sy - E * 0.5, E)
        superficie.blit(d, (bx, by))

    def _aura(self, superficie, tempo, cx, cy, E) -> None:
        r = int(E * (0.62 + 0.04 * math.sin(tempo * 9.0)))
        r = max(8, (r // 8) * 8)
        tex = self._tex_aura.get(r)
        if tex is None:
            tex = pygame.Surface((r * 2, r * 2), 0, 24)
            for i in range(16, 0, -1):
                f = i / 16.0
                k = int(70 * (1.0 - f) ** 1.6)
                pygame.draw.circle(tex, (min(255, k * 2), min(255, int(k * 1.4)), k // 3),
                                   (r, r), max(1, int(r * f)))
            self._tex_aura[r] = tex
        pulso = 0.75 + 0.25 * math.sin(tempo * 7.0)
        if pulso < 0.999:
            t2 = tex
            superficie.blit(t2, (int(cx - r), int(cy - r * 1.05)), special_flags=pygame.BLEND_RGB_ADD)

    def _molla_coda(self, mem, sk, tempo):
        t = mem.t_ultimo
        dt = 1.0 / 60.0 if t is None else max(0.0, min(0.05, tempo - t))
        mem.t_ultimo = tempo
        hu, hv = sk['testa']
        if mem.testa_prec is None:
            mem.testa_prec = (hu, hv)
        if dt > 0.0:
            vu = (hu - mem.testa_prec[0]) / dt
            vv = (hv - mem.testa_prec[1]) / dt
            mem.testa_prec = (hu, hv)
            # angolo della coda (gradi dalla verticale verso il basso, dietro = negativo)
            bersaglio = -38.0 + max(-30.0, min(30.0, vu * 10.0)) + max(-20.0, min(20.0, -vv * 6.0))
            acc = (bersaglio - mem.coda_ang) * 260.0 - mem.coda_vel * 16.0
            mem.coda_vel += acc * dt
            mem.coda_ang += mem.coda_vel * dt
            mem.coda_ang = max(-120.0, min(40.0, mem.coda_ang))
        return mem.coda_ang


# ============================================================ pittura del corpo
def _perp(a, b):
    d = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return (-(b[1] - a[1]) / d, (b[0] - a[0]) / d)


def _dipingi(pen, sk, p, anim, pro, tav, pers, coda, mem) -> None:
    """Dipinge il lottatore a strati: arto lontano, busto/testa, arto vicino."""
    if anim.scia:
        _scia(pen, sk, anim, tav)
    _gamba(pen, sk, 'F', True, pro, tav)
    if not anim.lead_avanti:
        _braccio(pen, sk, 'L', True, pro, tav)
    _busto(pen, sk, p, anim, pro, tav, pers)
    _testa(pen, sk, p, anim, pro, tav, pers, coda)
    _gamba(pen, sk, 'B', False, pro, tav)
    _braccio(pen, sk, 'R', False, pro, tav)
    if anim.lead_avanti:
        _braccio(pen, sk, 'L', False, pro, tav)
    if anim.stelle:
        _stelle(pen, sk, anim)


def _scia(pen, sk, anim, tav):
    pass


def _gamba(pen, sk, n, lontano, pro, tav):
    k = pro.k
    hip = sk['anca' + n]
    kn = sk['ginocchio' + n]
    an = sk['caviglia' + n]
    fu, fv = sk['piede_dir' + n]
    su, sv = -fv, fu                     # "su" del piede
    nrm = _perp(kn, an)
    calf = _lerp(kn, an, 0.30)
    calf = (calf[0] - nrm[0] * 0.011, calf[1] - nrm[1] * 0.011)
    top = _lerp(hip, kn, 0.40)
    mid = _lerp(top, kn, 0.5)
    if lontano:
        pelle, ombra = tav.lontano, tav.lontano_o
        pant, pant_o, bordo = tav.pant_lont, tav.pant_lont_o, tav.bordo_lont
        fasce = tav.fasce_lont
    else:
        pelle, ombra = tav.pelle, tav.pelle_o
        pant, pant_o, bordo = tav.pant, tav.pant_o, tav.bordo
        fasce = tav.fasce
    gamba = ([top, mid, kn, calf, an], [0.058 * k, 0.052 * k, 0.041 * k, 0.045 * k, 0.029 * k])
    tallone = (an[0] - fu * 0.020 + su * -0.018, an[1] - fv * 0.020 + sv * -0.018)
    palla = (an[0] + fu * 0.055 + su * -0.022, an[1] + fv * 0.055 + sv * -0.022)
    punta = (an[0] + fu * 0.093 + su * -0.019, an[1] + fv * 0.093 + sv * -0.019)
    piede = ([tallone, an, palla, punta], [0.024 * k ** 0.5, 0.030 * k ** 0.5, 0.025 * k ** 0.5, 0.019 * k ** 0.5])
    pen.multi([gamba, piede], None if lontano and False else pelle, ombra)
    # fasce alla caviglia
    q = _lerp(an, kn, 0.17)
    r = 0.031 * k
    pen.fascia((q[0] - nrm[0] * r, q[1] - nrm[1] * r), (q[0] + nrm[0] * r, q[1] + nrm[1] * r), 0.0125,
               fasce, _scura(fasce, 0.72))
    # pantaloncino thai: trapezio svasato dal bacino a meta' coscia, con bordo colorato dritto
    fine = _lerp(hip, kn, 0.64)
    nn = _perp(hip, kn)
    bp = pro.busto ** 0.5
    r0 = 0.074 * bp
    r1 = 0.098 * bp
    poly = [(hip[0] + nn[0] * r0, hip[1] + nn[1] * r0), (fine[0] + nn[0] * r1, fine[1] + nn[1] * r1),
            (fine[0] - nn[0] * r1, fine[1] - nn[1] * r1), (hip[0] - nn[0] * r0, hip[1] - nn[1] * r0)]
    pen.pantaloncino(hip, r0, poly, pant, pant_o)
    pen.banda((fine[0] - nn[0] * r1, fine[1] - nn[1] * r1), (fine[0] + nn[0] * r1, fine[1] + nn[1] * r1), 0.011, bordo, _scura(bordo, 0.75))


def _braccio(pen, sk, n, lontano, pro, tav):
    k = pro.k
    sp = sk['spalla' + n]
    go = sk['gomito' + n]
    ma = sk['mano' + n]
    fa = _norm((ma[0] - go[0], ma[1] - go[1]))
    polso = (ma[0] - fa[0] * 0.062, ma[1] - fa[1] * 0.062)
    if lontano:
        pelle, ombra = tav.lontano, tav.lontano_o
        gu, gu_o, gu_l = tav.gu_lont, tav.gu_lont_o, tav.gu_lont
        fasce = tav.fasce_lont
    else:
        pelle, ombra = tav.pelle, tav.pelle_o
        gu, gu_o, gu_l = tav.gu, tav.gu_o, tav.gu_l
        fasce = tav.fasce
    m1 = _lerp(sp, go, 0.45)
    m2 = _lerp(go, polso, 0.35)
    pen.solido([sp, m1, go, m2, polso], [0.050 * k, 0.045 * k, 0.037 * k, 0.040 * k, 0.029 * k], pelle, ombra)
    # guantone: polsino imbottito + pugno tondo
    pol = (ma[0] - fa[0] * 0.10, ma[1] - fa[1] * 0.10)
    pen.solido([pol, _lerp(pol, ma, 0.55)], [0.040 * k ** 0.4, 0.052 * k ** 0.4], gu, gu_o, luce_k=0.22)
    perp = (-fa[1], fa[0])
    if perp[1] < 0:
        perp = (-perp[0], -perp[1])
    # fascia bianca al polsino
    q = _lerp(pol, ma, 0.16)
    r = 0.044 * k ** 0.4
    pen.fascia((q[0] - perp[0] * r, q[1] - perp[1] * r), (q[0] + perp[0] * r, q[1] + perp[1] * r), 0.011,
               fasce, _scura(fasce, 0.72), ow=pen.ow * 0.9)
    pen.solido([ma], [RAGGIO_G * k ** 0.3], gu, gu_o, luce_k=0.26, lit_scala=0.80)
    # pollice
    th = (ma[0] + fa[0] * -0.005 + perp[0] * 0.040, ma[1] + fa[1] * -0.005 + perp[1] * 0.040)
    pen.solido([th, (th[0] + fa[0] * 0.02, th[1] + fa[1] * 0.02)], [0.020, 0.018], gu, gu_o, luce_k=0.2)
    # luce sul guantone
    hl = (ma[0] + fa[0] * 0.012 + perp[0] * 0.018, ma[1] + fa[1] * 0.012 + perp[1] * 0.018)
    if not lontano:
        pygame.draw.circle(pen.s, tav.gu_l, (int(pen.pt(*hl)[0]), int(pen.pt(*hl)[1])), max(1, int(0.013 * pen.S)))


RAGGIO_G = S.RAGGIO_GUANTO


def _busto(pen, sk, p, anim, pro, tav, pers):
    hip = sk['anca']
    tors = sk['tors_rad']
    dv = (math.sin(tors), math.cos(tors))
    nn = (sk['nu'], sk['nv'])
    resp = anim.resp
    donna = pro.donna
    b = pro.busto
    v = pro.vita

    def pos(f, off):
        return (hip[0] + dv[0] * f * S.BUSTO + nn[0] * off, hip[1] + dv[1] * f * S.BUSTO + nn[1] * off)

    tw = p['twist']
    if donna:
        seq = [(0.0, -0.004, 0.082 * v), (0.30, 0.0, 0.060 * v), (0.58, 0.005, 0.070 * b),
               (0.80, 0.012 + 0.004 * tw, 0.078 * b * (1 + 0.02 * resp)), (1.0, 0.0, 0.052 * b)]
    else:
        seq = [(0.0, -0.004, 0.080 * v), (0.30, 0.0, 0.064 * v), (0.58, 0.006, 0.078 * b),
               (0.80, 0.012 + 0.005 * tw, 0.090 * b * (1 + 0.025 * resp)), (1.0, 0.0, 0.058 * b)]
    pts = [pos(f, o) for f, o, r in seq]
    rad = [r for f, o, r in seq]
    collo = sk['collo']
    tst = sk['testa']
    nk = _lerp(collo, tst, 0.55)
    catene = [(pts, rad), ([pts[-1], collo, nk], [0.050 * b, 0.034 * pro.k, 0.031 * pro.k])]
    pen.multi(catene, tav.pelle, tav.pelle_o, luce_k=0.30, lit_scala=0.78)
    # muscolatura: ombra sotto il pettorale e addominali
    if not donna:
        c = pos(0.72, 0.045)
        pc = pen.pt(*c)
        r = 0.048 * b * pen.S
        pygame.draw.circle(pen.s, tav.pelle_o, (int(pc[0]), int(pc[1] + r * 0.18)), max(1, int(r)))
        pygame.draw.circle(pen.s, tav.pelle, (int(pc[0] + pen.dx * r * 0.05), int(pc[1] - r * 0.05)), max(1, int(r * 0.93)))
        for i, f in enumerate((0.34, 0.46, 0.58)):
            a = pos(f, 0.012 + 0.006 * i)
            bpt = pos(f, 0.052)
            pen.linea(tav.pelle_o, a, bpt, 0.0055)
    # top sportivo
    if pers.top is not None:
        cima = pos(0.90, 0.006)
        base_ = pos(0.62, 0.008)
        pen.solido([base_, pos(0.76, 0.010), cima], [0.070 * b, 0.081 * b * (1 + 0.02 * resp), 0.058 * b],
                   tav.top, tav.top_o, luce_k=0.26)
    # pantaloncino (bacino) e cintura
    r0 = 0.090 * v ** 0.8
    pen.solido([pos(-0.06, -0.004), pos(0.15, 0.0)], [r0, 0.084 * v ** 0.8], tav.pant, tav.pant_o, luce_k=0.2, lit_scala=0.84)
    a = pos(0.19, -0.084 * v ** 0.8)
    bb = pos(0.19, 0.084 * v ** 0.8)
    pen.banda(a, bb, 0.018, tav.bordo, tav.bordo_o)


def _testa(pen, sk, p, anim, pro, tav, pers, coda):
    th = sk['testa_rad']
    C_ = sk['testa']
    up = (math.sin(th), math.cos(th))
    fw = (math.cos(th), -math.sin(th))

    def H(a, b):
        return (C_[0] + fw[0] * a + up[0] * b, C_[1] + fw[1] * a + up[1] * b)

    kp = pro.k ** 0.35
    stile = pers.stile_capelli
    # coda di cavallo (dietro la testa)
    if stile == 'coda' and coda is not None:
        base = H(-0.040, 0.030)
        ang = math.radians(coda)
        pts = [base]
        segs = 4
        a = ang
        cu, cv = base
        for i in range(segs):
            a += math.radians(-6.0 - 3.0 * i) * (1 if coda < 0 else -1) * 0.0
            cu += math.sin(a) * 0.045
            cv -= math.cos(a) * 0.045
            pts.append((cu, cv))
        pen.solido(pts, [0.024, 0.026, 0.024, 0.018, 0.011], tav.capelli, tav.capelli_o, luce_k=0.25)
    cr = H(-0.004, 0.010)
    ja = H(0.020, -0.030)
    pen.solido([cr, ja], [0.061 * kp, 0.045 * kp], tav.pelle, tav.pelle_o, luce_k=0.28)
    # orecchio
    orec = H(-0.012, -0.004)
    pen.cerchio_solido(orec, 0.016, tav.pelle_o, _scura(tav.pelle_o, 0.8), luce_k=0.1, ow=pen.ow * 0.8)
    # capelli
    _capelli(pen, H, stile, tav, pers)
    # barba
    if pers.barba:
        pts = [H(-0.018, -0.006), H(0.010, -0.002), H(0.034, -0.020), H(0.058, -0.040), H(0.052, -0.070),
               H(0.028, -0.086), H(0.000, -0.076), H(-0.026, -0.052)]
        pen.poligono(pts, tav.capelli, ow=pen.ow * 0.8)
        hl = [H(0.004, -0.030), H(0.030, -0.040), H(0.030, -0.052), H(0.004, -0.048)]
        pygame.draw.polygon(pen.s, tav.capelli_l, [pen.pt(*q) for q in hl])
    # naso
    naso = H(0.056, -0.006)
    pen.cerchio_solido(naso, 0.0125, tav.pelle, tav.pelle_o, luce_k=0.2, ow=pen.ow * 0.85)
    # espressione
    _faccia(pen, H, anim, tav, pers)


def _capelli(pen, H, stile, tav, pers):
    col = tav.capelli
    if stile == 'rasati':
        pts = [H(-0.052, -0.020), H(-0.058, 0.016), H(-0.044, 0.046), H(-0.008, 0.066), H(0.030, 0.058),
               H(0.050, 0.036), H(0.046, 0.030), H(0.024, 0.040), H(-0.004, 0.036), H(-0.030, 0.014),
               H(-0.038, -0.020)]
        pen.poligono(pts, tav.capelli_o, ow=pen.ow * 0.7)
    elif stile == 'corti':
        pts = [H(-0.056, -0.024), H(-0.064, 0.020), H(-0.048, 0.052), H(-0.010, 0.072), H(0.030, 0.066),
               H(0.056, 0.042), H(0.058, 0.022), H(0.040, 0.030), H(0.020, 0.044), H(-0.002, 0.038),
               H(-0.024, 0.014), H(-0.034, -0.024)]
        pen.poligono(pts, col, ow=pen.ow * 0.85)
        hl = [H(-0.030, 0.052), H(0.000, 0.064), H(0.026, 0.058), H(0.004, 0.050)]
        pygame.draw.polygon(pen.s, tav.capelli_l, [pen.pt(*q) for q in hl])
    elif stile == 'cresta':
        pts = [H(-0.052, -0.016), H(-0.058, 0.016), H(-0.048, 0.044), H(-0.030, 0.062), H(-0.036, 0.098),
               H(-0.014, 0.078), H(-0.004, 0.112), H(0.016, 0.082), H(0.030, 0.108), H(0.040, 0.070),
               H(0.056, 0.078), H(0.052, 0.046), H(0.040, 0.034), H(0.020, 0.044), H(-0.002, 0.040),
               H(-0.028, 0.016), H(-0.036, -0.018)]
        pen.poligono(pts, col, ow=pen.ow * 0.85)
        hl = [H(-0.020, 0.064), H(-0.004, 0.100), H(0.010, 0.070)]
        pygame.draw.polygon(pen.s, tav.capelli_l, [pen.pt(*q) for q in hl])
    elif stile == 'coda':
        pts = [H(-0.052, -0.010), H(-0.060, 0.022), H(-0.044, 0.052), H(-0.008, 0.068), H(0.032, 0.060),
               H(0.054, 0.038), H(0.048, 0.030), H(0.024, 0.040), H(-0.002, 0.036), H(-0.028, 0.014),
               H(-0.034, -0.012)]
        pen.poligono(pts, col, ow=pen.ow * 0.85)
        hl = [H(-0.030, 0.052), H(0.000, 0.062), H(0.024, 0.056), H(0.000, 0.048)]
        pygame.draw.polygon(pen.s, tav.capelli_l, [pen.pt(*q) for q in hl])
        # fermaglio
        pen.cerchio_solido(H(-0.050, 0.030), 0.014, tav.accento, _scura(tav.accento, 0.6), luce_k=0.2, ow=pen.ow * 0.7)
    else:                                # raccolti
        pen.cerchio_solido(H(-0.030, 0.076), 0.030, col, tav.capelli_o, luce_k=0.25)
        pts = [H(-0.052, -0.012), H(-0.058, 0.020), H(-0.040, 0.050), H(-0.006, 0.066), H(0.030, 0.058),
               H(0.052, 0.038), H(0.046, 0.030), H(0.022, 0.040), H(-0.004, 0.036), H(-0.028, 0.014)]
        pen.poligono(pts, col, ow=pen.ow * 0.85)


def _faccia(pen, H, anim, tav, pers):
    ow = pen.ow
    S_ = pen.S
    scuro = CONTORNO
    occhi = anim.occhi
    if occhi == 'c':
        a = H(0.024, 0.014)
        b = H(0.046, 0.012)
        pen.linea(scuro, a, b, 0.008)
    elif occhi == 'x':
        c = H(0.034, 0.014)
        pen.linea(scuro, (c[0] - 0.010 * 0.7, c[1] - 0.010), (c[0] + 0.010 * 0.7, c[1] + 0.010), 0.007)
        pen.linea(scuro, (c[0] - 0.010 * 0.7, c[1] + 0.010), (c[0] + 0.010 * 0.7, c[1] - 0.010), 0.007)
    else:
        c = H(0.036, 0.012)
        if occhi == 'a':
            pygame.draw.circle(pen.s, (245, 245, 250), (int(pen.pt(*c)[0]), int(pen.pt(*c)[1])), max(1, int(0.014 * S_)))
            pp = H(0.040, 0.012)
            pygame.draw.circle(pen.s, scuro, (int(pen.pt(*pp)[0]), int(pen.pt(*pp)[1])), max(1, int(0.008 * S_)))
        else:
            pygame.draw.circle(pen.s, (245, 245, 250), (int(pen.pt(*c)[0]), int(pen.pt(*c)[1])), max(1, int(0.010 * S_)))
            pp = H(0.040, 0.010)
            pygame.draw.circle(pen.s, scuro, (int(pen.pt(*pp)[0]), int(pen.pt(*pp)[1])), max(1, int(0.0065 * S_)))
        # sopracciglio
        if occhi == 's':
            pen.linea(scuro, H(0.020, 0.032), H(0.052, 0.020), 0.0095)
        else:
            pen.linea(scuro, H(0.022, 0.034), H(0.050, 0.030), 0.0085)
    bocca = anim.bocca
    if bocca == 'a':
        m = pen.pt(*H(0.042, -0.030))
        pygame.draw.ellipse(pen.s, scuro, (m[0] - 0.012 * S_, m[1] - 0.010 * S_, 0.024 * S_, 0.022 * S_))
    elif bocca == 'd':
        pen.linea(scuro, H(0.030, -0.026), H(0.056, -0.028), 0.0085)
        pen.linea((240, 240, 245), H(0.034, -0.0265), H(0.052, -0.0275), 0.0035)
    elif bocca == 'g':
        m = pen.pt(*H(0.044, -0.030))
        pygame.draw.ellipse(pen.s, scuro, (m[0] - 0.015 * S_, m[1] - 0.012 * S_, 0.030 * S_, 0.026 * S_))
        m2 = pen.pt(*H(0.046, -0.024))
        pygame.draw.rect(pen.s, (240, 240, 245), (m2[0] - 0.010 * S_, m2[1] - 0.004 * S_, 0.020 * S_, 0.006 * S_))
    else:
        pen.linea(scuro, H(0.032, -0.030), H(0.054, -0.030), 0.0075)


def _stelle(pen, sk, anim):
    pass
