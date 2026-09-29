"""Stile grafico dell'interfaccia: palette, animazioni, testo pesante con contorno
e ombra, pannelli inclinati anti-aliasati, sfumature, aloni, bandiere e icone.

Tutto e' procedurale e messo in cache: le superfici restituite sono condivise
e NON vanno modificate da chi le riceve (per l'alpha usare `blit_alpha`).
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import pygame

from .. import costanti as C

# ---- palette dell'interfaccia
INCHIOSTRO = (8, 8, 13)            # contorni e ombre
NOTTE = (14, 16, 26)               # fondo dei pannelli
NOTTE_CHIARA = (30, 34, 52)
ACCIAIO = (74, 80, 104)            # bordi inattivi
ARGENTO = (200, 206, 222)
BIANCO = C.BIANCO
SPENTO = (140, 146, 168)           # testo secondario
ORO = C.ORO
ORO_CHIARO = (255, 226, 132)
ROSSO_K1 = (228, 36, 50)
ROSSO_SCURO = (112, 12, 22)
AZZURRO = C.AZZURRO
VERDE = C.VERDE
GIALLO = C.GIALLO
COLORE_GIOCATORE = ((240, 72, 60), (60, 144, 252))   # cursori ed etichette 1P / 2P

# sfumature "metalliche" (posizione 0..1 dall'alto, colore)
SFUMATURA_ORO = ((0.0, (255, 250, 218)), (0.40, (255, 214, 96)), (0.56, (222, 138, 30)),
                 (1.0, (255, 196, 84)))
SFUMATURA_ROSSO = ((0.0, (255, 196, 176)), (0.38, (255, 76, 62)), (0.58, (196, 18, 32)),
                   (1.0, (238, 56, 48)))
SFUMATURA_ARGENTO = ((0.0, (255, 255, 255)), (0.44, (226, 232, 246)), (0.56, (150, 158, 182)),
                     (1.0, (222, 228, 242)))
SFUMATURA_BIANCO = ((0.0, (255, 255, 255)), (1.0, (204, 210, 228)))


# ---- numeri e animazione
def limita(v: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if v < a else b if v > b else v


def interpola(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def progresso(t: float, inizio: float, durata: float) -> float:
    """Frazione 0..1 di un intervallo [inizio, inizio + durata]."""
    if durata <= 0:
        return 1.0 if t >= inizio else 0.0
    return limita((t - inizio) / durata)


def ease_out_cubic(t: float) -> float:
    t = limita(t)
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    t = limita(t)
    return t * t * t


def ease_in_out(t: float) -> float:
    t = limita(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t: float, s: float = 1.70158) -> float:
    t = limita(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_elastic(t: float) -> float:
    t = limita(t)
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def pulsa(t: float, frequenza: float = 1.0, minimo: float = 0.0, massimo: float = 1.0) -> float:
    """Oscillazione sinusoidale tra minimo e massimo."""
    return minimo + (massimo - minimo) * (0.5 + 0.5 * math.sin(t * frequenza * math.tau))


# ---- colori
def mescola(c1: Sequence, c2: Sequence, t: float) -> tuple:
    t = limita(t)
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def schiarisci(c: Sequence, t: float) -> tuple:
    return mescola(c[:3], (255, 255, 255), t)


def scurisci(c: Sequence, t: float) -> tuple:
    return mescola(c[:3], (0, 0, 0), t)


def luminosita(c: Sequence) -> float:
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255.0


def colore_su_sfumatura(stop: Sequence, t: float) -> tuple:
    """Colore alla posizione t di una lista di stop (pos, colore) ordinati."""
    if t <= stop[0][0]:
        return tuple(stop[0][1])
    for (p0, c0), (p1, c1) in zip(stop, stop[1:]):
        if t <= p1:
            return mescola(c0, c1, (t - p0) / max(1e-6, p1 - p0))
    return tuple(stop[-1][1])


def accento_leggibile(c: Sequence) -> tuple:
    """Versione del colore d'accento abbastanza chiara da leggersi su fondo scuro."""
    l = luminosita(c)
    return schiarisci(c, 0.35 - l * 0.3) if l < 0.55 else tuple(c[:3])


# ---- cache
_CACHE: dict = {}
_LIMITE_CACHE = 900


def _in_cache(chiave, crea):
    s = _CACHE.get(chiave)
    if s is None:
        if len(_CACHE) >= _LIMITE_CACHE:
            for k in list(_CACHE)[: _LIMITE_CACHE // 2]:
                del _CACHE[k]
        s = crea()
        _CACHE[chiave] = s
    return s


def svuota_cache() -> None:
    _CACHE.clear()
    _FONT.clear()


def _ottimizza(s: pygame.Surface) -> pygame.Surface:
    """convert_alpha() se c'e' un display (blit piu' veloci), altrimenti invariata."""
    try:
        if pygame.display.get_init() and pygame.display.get_surface() is not None:
            return s.convert_alpha()
    except pygame.error:
        pass
    return s


# ---- font
_FONT: dict = {}
_quit_registrato = False


def font(dimensione: int, corsivo: bool = False, grassetto: bool = False) -> pygame.font.Font:
    """Font di base (freesansbold incluso in pygame), in cache."""
    global _quit_registrato
    if not pygame.font.get_init():
        pygame.font.init()
        _FONT.clear()
    if not _quit_registrato:
        pygame.register_quit(_FONT.clear)
        _quit_registrato = True
    chiave = (int(dimensione), bool(corsivo), bool(grassetto))
    f = _FONT.get(chiave)
    if f is None:
        f = pygame.font.Font(None, max(6, int(dimensione)))
        f.set_italic(bool(corsivo))
        f.set_bold(bool(grassetto))
        _FONT[chiave] = f
    return f


def _maschera_testo(stringa: str, dimensione: int, corsivo: bool, condensa: float,
                    spaziatura: int, grassetto: bool) -> pygame.Surface:
    """Glifi bianchi con alpha anti-aliasata (eventualmente spaziati e condensati).

    Sotto i 60 px si renderizza al doppio e si riduce: l'hinting del font di base
    a corpi piccoli produce crenature irregolari ("ATTERR AMENTO").
    """
    ss = 2 if dimensione < 60 else 1
    f = font(dimensione * ss, corsivo, grassetto)
    if not stringa:
        return pygame.Surface((1, max(1, f.get_height() // ss)), pygame.SRCALPHA)
    if spaziatura:
        glifi = [f.render(ch, True, (255, 255, 255)) for ch in stringa]
        avanzamenti = [f.size(ch)[0] + spaziatura * ss for ch in stringa]
        larghezza = (sum(avanzamenti) - spaziatura * ss
                     + max(0, glifi[-1].get_width() - f.size(stringa[-1])[0]))
        m = pygame.Surface((max(1, larghezza), f.get_height()), pygame.SRCALPHA)
        x = 0
        for g, av in zip(glifi, avanzamenti):
            m.blit(g, (x, 0))
            x += av
    else:
        m = f.render(stringa, True, (255, 255, 255))
        if m.get_flags() & pygame.SRCALPHA == 0:
            m = m.convert_alpha() if pygame.display.get_surface() else _con_alpha(m)
    w = m.get_width() / ss * condensa
    h = m.get_height() / ss
    if ss > 1 or abs(condensa - 1.0) > 1e-3:
        m = pygame.transform.smoothscale(m, (max(1, int(round(w))), max(1, int(round(h)))))
    return m


def _con_alpha(s: pygame.Surface) -> pygame.Surface:
    d = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    d.blit(s, (0, 0))
    return d


def _offset_disco(r: int) -> list:
    """Offset interi che campionano un disco di raggio r (per dilatare le maschere)."""
    if r <= 0:
        return [(0, 0)]
    punti = set()
    raggi = [r] if r <= 2 else sorted({r, max(1, round(r * 0.66)), max(1, round(r * 0.33))})
    for rr in raggi:
        n = max(8, int(math.tau * rr * 1.25))
        for k in range(n):
            a = math.tau * k / n
            punti.add((int(round(math.cos(a) * rr)), int(round(math.sin(a) * rr))))
    if r <= 2:
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r + 0.5:
                    punti.add((dx, dy))
    punti.add((0, 0))
    return sorted(punti)


def dilata(maschera: pygame.Surface, r: int) -> pygame.Surface:
    """Maschera (bianca con alpha) allargata di r pixel su ogni lato."""
    w, h = maschera.get_size()
    d = pygame.Surface((w + 2 * r, h + 2 * r), pygame.SRCALPHA)
    for dx, dy in _offset_disco(r):
        d.blit(maschera, (r + dx, r + dy), special_flags=pygame.BLEND_RGBA_MAX)
    return d


def tinta(maschera: pygame.Surface, colore: Sequence) -> pygame.Surface:
    """Maschera bianca -> stesso alpha con colore (e alpha opzionale) dato."""
    s = maschera.copy()
    c = tuple(colore)
    a = c[3] if len(c) > 3 else 255
    s.fill((c[0], c[1], c[2], a), special_flags=pygame.BLEND_RGBA_MULT)
    return s


def sfoca(s: pygame.Surface, raggio: int) -> pygame.Surface:
    """Sfocatura economica (riduci e ringrandisci)."""
    if raggio <= 0:
        return s
    w, h = s.get_size()
    f = 1.0 / (1 + raggio * 0.5)
    piccola = pygame.transform.smoothscale(s, (max(1, int(w * f)), max(1, int(h * f))))
    return pygame.transform.smoothscale(piccola, (w, h))


# ---- sfumature
def sfumatura(w: int, h: int, stop: Sequence, orizzontale: bool = False,
              alpha: int = 255) -> pygame.Surface:
    """Superficie w x h riempita con una sfumatura a stop [(pos, colore), ...]."""
    stop = tuple((float(p), tuple(c[:3])) for p, c in stop)
    chiave = ('sfum', w, h, stop, orizzontale, alpha)

    def crea():
        n = max(1, w if orizzontale else h)
        riga = pygame.Surface((n, 1) if orizzontale else (1, n), pygame.SRCALPHA)
        for i in range(n):
            c = colore_su_sfumatura(stop, i / max(1, n - 1))
            riga.set_at((i, 0) if orizzontale else (0, i), (c[0], c[1], c[2], alpha))
        return pygame.transform.scale(riga, (max(1, w), max(1, h)))
    return _in_cache(chiave, crea)


def due_colori(alto: Sequence, basso: Sequence) -> tuple:
    return ((0.0, tuple(alto[:3])), (1.0, tuple(basso[:3])))


# ---- testo
def testo(stringa: str, dimensione: int, colore: Sequence = BIANCO, *,
          sfumatura_testo: Optional[Sequence] = None,
          contorno: int = 2, colore_contorno: Sequence = INCHIOSTRO,
          contorno_esterno: int = 0, colore_esterno: Sequence = INCHIOSTRO,
          ombra: Optional[tuple] = (2, 3), colore_ombra: Sequence = (0, 0, 0, 150),
          sfocatura_ombra: int = 0, corsivo: bool = False, condensa: float = 1.0,
          spaziatura: int = 0, grassetto: bool = False) -> pygame.Surface:
    """Testo stilizzato in cache: riempimento (tinta o sfumatura), contorno interno,
    contorno esterno opzionale e ombra portata. Il margine attorno ai glifi e'
    simmetrico (contorni), piu' lo spazio dell'ombra a destra/in basso."""
    chiave = ('testo', stringa, int(dimensione), tuple(colore),
              tuple(sfumatura_testo) if sfumatura_testo else None,
              contorno, tuple(colore_contorno), contorno_esterno, tuple(colore_esterno),
              tuple(ombra) if ombra else None, tuple(colore_ombra), sfocatura_ombra,
              corsivo, round(condensa, 3), spaziatura, grassetto)

    def crea():
        m = _maschera_testo(stringa, dimensione, corsivo, condensa, spaziatura, grassetto)
        w, h = m.get_size()
        r_tot = contorno + contorno_esterno
        ox, oy = (ombra if ombra else (0, 0))
        bordo = sfocatura_ombra * 2
        pad_dx = max(0, ox) + bordo
        pad_dy = max(0, oy) + bordo
        pad_sx = max(0, -ox) + bordo
        pad_su = max(0, -oy) + bordo
        W = w + 2 * r_tot + pad_sx + pad_dx
        H = h + 2 * r_tot + pad_su + pad_dy
        out = pygame.Surface((W, H), pygame.SRCALPHA)
        base = (pad_sx, pad_su)             # angolo del blocco dilatato
        esterna = dilata(m, r_tot) if r_tot > 0 else m
        if ombra:
            om = tinta(esterna, colore_ombra)
            if sfocatura_ombra:
                tmp = pygame.Surface((W, H), pygame.SRCALPHA)
                tmp.blit(om, (base[0] + ox, base[1] + oy))
                out.blit(sfoca(tmp, sfocatura_ombra), (0, 0))
            else:
                out.blit(om, (base[0] + ox, base[1] + oy))
        if contorno_esterno > 0:
            out.blit(tinta(esterna, colore_esterno), base)
        if contorno > 0:
            interna = dilata(m, contorno)
            out.blit(tinta(interna, colore_contorno), (base[0] + contorno_esterno,
                                                         base[1] + contorno_esterno))
        if sfumatura_testo:
            riemp = sfumatura(w, h, sfumatura_testo).copy()
            riemp.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        else:
            riemp = tinta(m, colore)
        out.blit(riemp, (base[0] + r_tot, base[1] + r_tot))
        return _ottimizza(out)
    return _in_cache(chiave, crea)


def blit_alpha(superficie: pygame.Surface, s: pygame.Surface, pos, alpha: float = 255,
               flags: int = 0) -> None:
    """Blit con trasparenza globale senza alterare la superficie in cache."""
    a = int(limita(alpha, 0, 255))
    if a <= 0:
        return
    if a >= 255:
        superficie.blit(s, pos, special_flags=flags)
        return
    s.set_alpha(a)
    try:
        superficie.blit(s, pos, special_flags=flags)
    finally:
        # 255 (non None): set_alpha(None) su una superficie con alpha per pixel
        # ne disattiva la fusione e le blit successive (in cache) risultano opache
        s.set_alpha(255)


def scala_superficie(s: pygame.Surface, scala: float) -> pygame.Surface:
    if abs(scala - 1.0) < 1e-3:
        return s
    w = max(1, int(s.get_width() * scala))
    h = max(1, int(s.get_height() * scala))
    return pygame.transform.smoothscale(s, (w, h))


def piazza(superficie: pygame.Surface, s: pygame.Surface, pos, ancora: str = 'center',
           alpha: float = 255, scala: float = 1.0, flags: int = 0) -> pygame.Rect:
    """Disegna s ancorata a pos (ancora = attributo di pygame.Rect), con scala/alpha."""
    if scala != 1.0:
        s = scala_superficie(s, scala)
    r = s.get_rect()
    setattr(r, ancora, (int(round(pos[0])), int(round(pos[1]))))
    blit_alpha(superficie, s, r.topleft, alpha, flags)
    return r


def scrivi(superficie: pygame.Surface, stringa: str, pos, dimensione: int,
           colore: Sequence = BIANCO, ancora: str = 'center', alpha: float = 255,
           scala: float = 1.0, **stile) -> pygame.Rect:
    """Scorciatoia: testo(...) + piazza(...)."""
    return piazza(superficie, testo(stringa, dimensione, colore, **stile), pos, ancora,
                  alpha, scala)


# ---- forme
def forma(w: float, h: float, inclina_sx: float = 0.0, inclina_dx: float = 0.0) -> list:
    """Quadrilatero in un box w x h con i lati sinistro/destro inclinati.

    inclina_* = spostamento orizzontale della cima del lato rispetto alla base
    (positivo = lato "/"). Uguali e positivi -> parallelogramma "/".
    """
    lt, lb = (inclina_sx, 0.0) if inclina_sx >= 0 else (0.0, -inclina_sx)
    rt, rb = (w, w - inclina_dx) if inclina_dx >= 0 else (w + inclina_dx, w)
    return [(lt, 0.0), (rt, 0.0), (rb, h), (lb, h)]


def sposta(punti: Sequence, dx: float, dy: float) -> list:
    return [(x + dx, y + dy) for x, y in punti]


def specchia_x(punti: Sequence, asse: float) -> list:
    return [(2 * asse - x, y) for x, y in punti]


def rientra(punti: Sequence, d: float) -> list:
    """Poligono convesso rientrato di d pixel su ogni lato."""
    n = len(punti)
    area = sum(punti[i][0] * punti[(i + 1) % n][1] - punti[(i + 1) % n][0] * punti[i][1]
               for i in range(n))
    verso = 1.0 if area > 0 else -1.0
    linee = []
    for i in range(n):
        (x1, y1), (x2, y2) = punti[i], punti[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        lung = math.hypot(ex, ey) or 1.0
        nx, ny = -ey / lung * verso, ex / lung * verso      # normale interna
        linee.append(((x1 + nx * d, y1 + ny * d), (ex, ey)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = linee[i - 1], linee[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-9:
            out.append(p2)
            continue
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


def maschera_poligono(w: int, h: int, punti: Sequence, ss: int = 4) -> pygame.Surface:
    """Maschera bianca anti-aliasata (supersampling) di un poligono nel box w x h."""
    chiave = ('mpoli', w, h, tuple((round(x, 2), round(y, 2)) for x, y in punti), ss)

    def crea():
        grande = pygame.Surface((max(1, w * ss), max(1, h * ss)), pygame.SRCALPHA)
        grande.fill((255, 255, 255, 0))
        pygame.draw.polygon(grande, (255, 255, 255, 255), [(x * ss, y * ss) for x, y in punti])
        return pygame.transform.smoothscale(grande, (max(1, w), max(1, h)))
    return _in_cache(chiave, crea)


def poligono_aa(superficie: pygame.Surface, colore: Sequence, punti: Sequence) -> None:
    """Poligono pieno con bordi anti-aliasati disegnato direttamente (per forme dinamiche)."""
    import pygame.gfxdraw as gfx
    pi = [(int(round(x)), int(round(y))) for x, y in punti]
    if len(pi) < 3:
        return
    c = tuple(colore)
    gfx.aapolygon(superficie, pi, c)
    gfx.filled_polygon(superficie, pi, c)


def riempi_mascherata(maschera: pygame.Surface, riempimento: pygame.Surface) -> pygame.Surface:
    """Riempimento (stesse dimensioni) ritagliato dall'alpha della maschera."""
    s = riempimento.copy()
    s.blit(maschera, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return s


def strisce(w: int, h: int, colore: Sequence, alpha: int = 40, passo: int = 10,
            spessore: int = 3, inclina: float = 1.0) -> pygame.Surface:
    """Righe diagonali (texture decorativa)."""
    chiave = ('strisce', w, h, tuple(colore), alpha, passo, spessore, inclina)

    def crea():
        s = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        c = (colore[0], colore[1], colore[2], alpha)
        dx = h * inclina
        x = -abs(dx) - passo
        while x < w + abs(dx) + passo:
            pygame.draw.polygon(s, c, [(x, h), (x + spessore, h), (x + spessore + dx, 0), (x + dx, 0)])
            x += passo
        return s
    return _in_cache(chiave, crea)


def pannello(w: int, h: int, inclina: float = 0.0, inclina_dx: Optional[float] = None, *,
             colore: Sequence = NOTTE, colore_basso: Optional[Sequence] = None,
             stop: Optional[Sequence] = None, alpha: int = 235,
             bordo: Optional[Sequence] = None, spessore: int = 2, alpha_bordo: int = 255,
             lucido: float = 0.0, righe: int = 0, colore_righe: Sequence = (255, 255, 255),
             orizzontale: bool = False) -> pygame.Surface:
    """Pannello inclinato anti-aliasato con sfumatura, bordo, riflesso e texture a righe.

    inclina = inclinazione del lato sinistro; inclina_dx (default = inclina) del destro.
    """
    if inclina_dx is None:
        inclina_dx = inclina
    stop_fill = tuple(stop) if stop else due_colori(colore, colore_basso or colore)
    chiave = ('pannello', w, h, round(inclina, 2), round(inclina_dx, 2), stop_fill, alpha,
              tuple(bordo) if bordo else None, spessore, alpha_bordo, lucido, righe,
              tuple(colore_righe), orizzontale)

    def crea():
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        esterno = forma(w, h, inclina, inclina_dx)
        if bordo and spessore > 0:
            mb = maschera_poligono(w, h, esterno)
            out.blit(tinta(mb, (bordo[0], bordo[1], bordo[2], alpha_bordo)), (0, 0))
            interno = rientra(esterno, spessore)
        else:
            interno = esterno
        mi = maschera_poligono(w, h, interno)
        riemp = sfumatura(w, h, stop_fill, orizzontale, alpha).copy()
        if righe:
            riemp.blit(strisce(w, h, colore_righe, righe, 9, 3, 0.9), (0, 0))
        if lucido > 0:
            riemp.blit(_riflesso(w, h, lucido), (0, 0))
        out.blit(riempi_mascherata(mi, riemp), (0, 0))
        return _ottimizza(out)
    return _in_cache(chiave, crea)


def _riflesso(w: int, h: int, forza: float) -> pygame.Surface:
    """Riflesso bianco che sfuma dall'alto verso meta' altezza."""
    chiave = ('riflesso', w, h, round(forza, 3))

    def crea():
        s = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        n = max(1, int(h * 0.55))
        for y in range(n):
            a = int(255 * forza * (1 - y / n) ** 1.6)
            pygame.draw.line(s, (255, 255, 255, a), (0, y), (w, y))
        return s
    return _in_cache(chiave, crea)


def ombreggiatura(w: int, h: int, forza: float) -> pygame.Surface:
    """Ombra nera che cresce verso il basso (volume dei pannelli e delle barre)."""
    chiave = ('ombreggia', w, h, round(forza, 3))

    def crea():
        s = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        for y in range(h):
            t = y / max(1, h - 1)
            a = int(255 * forza * max(0.0, t - 0.45) / 0.55)
            pygame.draw.line(s, (0, 0, 0, a), (0, y), (w, y))
        return s
    return _in_cache(chiave, crea)


# ---- luci
def alone(w: int, h: int, colore: Sequence, intensita: float = 1.0) -> pygame.Surface:
    """Alone ellittico morbido (da disegnare con BLEND_RGB_ADD). Superficie senza alpha."""
    chiave = ('alone', w, h, tuple(colore[:3]), round(intensita, 3))

    def crea():
        s = pygame.Surface((max(1, w), max(1, h)))
        s.fill((0, 0, 0))
        passi = 24
        for i in range(passi):
            t = i / passi
            k = intensita * (t ** 1.8)
            c = tuple(int(limita(v * k, 0, 255)) for v in colore[:3])
            rw, rh = w * (1 - t), h * (1 - t)
            if rw < 1 or rh < 1:
                break
            pygame.draw.ellipse(s, c, pygame.Rect((w - rw) / 2, (h - rh) / 2, rw, rh))
        return sfoca(s, 3)
    return _in_cache(chiave, crea)


def fascio(w: int, h: int, colore: Sequence, intensita: float = 1.0) -> pygame.Surface:
    """Cono di luce verticale (stretto in alto, largo in basso) per BLEND_RGB_ADD."""
    chiave = ('fascio', w, h, tuple(colore[:3]), round(intensita, 3))

    def crea():
        s = pygame.Surface((max(1, w), max(1, h)))
        s.fill((0, 0, 0))
        strati = 14
        for i in range(strati):
            t = i / strati
            k = intensita * 0.16 * (0.4 + t)
            c = tuple(int(limita(v * k, 0, 255)) for v in colore[:3])
            meta_alto = w * 0.08 * (1 - t) + 2
            meta_basso = w * 0.5 * (1 - t * 0.85)
            cx = w / 2
            pygame.draw.polygon(s, c, [(cx - meta_alto, 0), (cx + meta_alto, 0),
                                       (cx + meta_basso, h), (cx - meta_basso, h)],)
        # sfuma in fondo
        fondo = pygame.Surface((w, h))
        for y in range(h):
            v = int(255 * (1 - max(0.0, (y / h - 0.6) / 0.4)))
            pygame.draw.line(fondo, (v, v, v), (0, y), (w, y))
        s.blit(fondo, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        return sfoca(s, 6)
    return _in_cache(chiave, crea)


def velo(w: int, h: int, colore: Sequence = (0, 0, 0), alpha: int = 160) -> pygame.Surface:
    chiave = ('velo', w, h, tuple(colore[:3]), int(alpha))

    def crea():
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill((colore[0], colore[1], colore[2], int(alpha)))
        return s
    return _in_cache(chiave, crea)


def vignetta(w: int, h: int, forza: float = 0.8) -> pygame.Surface:
    """Scurimento radiale ai bordi (alpha nera)."""
    chiave = ('vignetta', w, h, round(forza, 3))

    def crea():
        pw, ph = 64, 36
        p = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for y in range(ph):
            for x in range(pw):
                dx = (x + 0.5) / pw * 2 - 1
                dy = (y + 0.5) / ph * 2 - 1
                d = math.sqrt(dx * dx * 0.9 + dy * dy * 1.1)
                a = limita((d - 0.55) / 0.75) ** 1.5 * forza
                p.set_at((x, y), (0, 0, 0, int(255 * a)))
        return pygame.transform.smoothscale(p, (w, h))
    return _in_cache(chiave, crea)


def sfondo_scuro(w: int, h: int) -> pygame.Surface:
    """Sfondo di ripiego (senza arena): notte blu profonda con luci e pavimento."""
    chiave = ('sfondo_scuro', w, h)

    def crea():
        s = sfumatura(w, h, ((0.0, (6, 7, 14)), (0.55, (16, 20, 40)), (0.72, (22, 34, 70)),
                             (1.0, (6, 8, 16)))).copy()
        s = _con_alpha(s) if not s.get_flags() & pygame.SRCALPHA else s
        piano = pygame.Surface((w, h), pygame.SRCALPHA)
        top = int(h * 0.64)
        pygame.draw.polygon(piano, (30, 70, 150, 110),
                            [(w * 0.18, top), (w * 0.82, top), (w * 1.05, h), (-w * 0.05, h)])
        s.blit(piano, (0, 0))
        luce = pygame.Surface((w, h))
        luce.fill((0, 0, 0))
        for cx in (0.22, 0.5, 0.78):
            f = fascio(int(w * 0.42), int(h * 0.9), (120, 150, 230), 0.9)
            luce.blit(f, (int(w * cx - f.get_width() / 2), 0), special_flags=pygame.BLEND_RGB_ADD)
        s.blit(luce, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        s.blit(vignetta(w, h, 0.9), (0, 0))
        return s.convert() if pygame.display.get_surface() else s
    return _in_cache(chiave, crea)


# ---- bandiere e icone
def bandiera(nazione: str, w: int, h: int) -> pygame.Surface:
    """Bandiera procedurale (Italia, Giappone, Russia, Brasile; altrimenti sigla)."""
    chiave = ('bandiera', nazione, w, h)

    def crea():
        ss = 4
        W, H = w * ss, h * ss
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        n = nazione.strip().lower()
        if n == 'italia':
            for i, c in enumerate(((0, 146, 70), (244, 245, 240), (206, 43, 55))):
                s.fill(c, pygame.Rect(i * W // 3, 0, W // 3 + 1, H))
        elif n == 'giappone':
            s.fill((246, 246, 244))
            pygame.draw.circle(s, (188, 0, 45), (W // 2, H // 2), int(H * 0.3))
        elif n == 'russia':
            for i, c in enumerate(((246, 246, 244), (0, 57, 166), (213, 43, 30))):
                s.fill(c, pygame.Rect(0, i * H // 3, W, H // 3 + 1))
        elif n == 'brasile':
            s.fill((0, 152, 64))
            mx, my = W * 0.09, H * 0.13
            pygame.draw.polygon(s, (254, 221, 0), [(W / 2, my), (W - mx, H / 2), (W / 2, H - my),
                                                   (mx, H / 2)])
            pygame.draw.circle(s, (0, 39, 118), (W // 2, H // 2), int(H * 0.25))
            pygame.draw.arc(s, (240, 240, 240), pygame.Rect(W / 2 - H * 0.42, H / 2 - H * 0.12,
                                                            H * 0.84, H * 0.8),
                            math.radians(30), math.radians(150), max(1, ss))
        else:
            s.fill((60, 64, 80))
            f = font(int(h * 1.6))
            t = f.render(nazione[:3].upper(), True, (230, 230, 240))
            t = pygame.transform.smoothscale(t, (int(t.get_width() * H / max(1, t.get_height()) * 0.7),
                                                 int(H * 0.7)))
            s.blit(t, t.get_rect(center=(W // 2, H // 2)))
        piccola = pygame.transform.smoothscale(s, (w, h))
        piccola.blit(_riflesso(w, h, 0.35), (0, 0))
        pygame.draw.rect(piccola, (0, 0, 0, 160), piccola.get_rect(), 1)
        return piccola
    return _in_cache(chiave, crea)


def fulmine(dimensione: int, colore: Sequence) -> pygame.Surface:
    """Icona a saetta (energia/super), anti-aliasata."""
    chiave = ('fulmine', dimensione, tuple(colore))

    def crea():
        ss = 4
        d = dimensione * ss
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        p = [(0.58, 0.0), (0.16, 0.56), (0.46, 0.56), (0.36, 1.0), (0.84, 0.40), (0.54, 0.40),
             (0.70, 0.0)]
        pts = [(x * d, y * d) for x, y in p]
        pygame.draw.polygon(s, INCHIOSTRO, pts)
        interno = [(0.5 + (x - 0.5) * 0.78, 0.5 + (y - 0.5) * 0.84) for x, y in p]
        pygame.draw.polygon(s, tuple(colore), [(x * d, y * d) for x, y in interno])
        return pygame.transform.smoothscale(s, (dimensione, dimensione))
    return _in_cache(chiave, crea)


def rombo(dimensione: int, colore: Sequence, pieno: bool = True,
          bordo: Sequence = INCHIOSTRO) -> pygame.Surface:
    """Rombo (medaglia dei round)."""
    chiave = ('rombo', dimensione, tuple(colore), pieno, tuple(bordo))

    def crea():
        ss = 4
        d = dimensione * ss
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        esterno = [(d / 2, 0), (d, d / 2), (d / 2, d), (0, d / 2)]
        pygame.draw.polygon(s, tuple(bordo), esterno)
        interno = rientra(esterno, d * 0.14)
        if pieno:
            pygame.draw.polygon(s, tuple(colore), interno)
            luce = rientra(esterno, d * 0.3)
            pygame.draw.polygon(s, schiarisci(colore, 0.55), [luce[0], luce[1], (d / 2, d / 2), luce[3]])
        else:
            pygame.draw.polygon(s, (40, 44, 60), interno)
            pygame.draw.polygon(s, tuple(colore), interno, max(1, ss))
        return pygame.transform.smoothscale(s, (dimensione, dimensione))
    return _in_cache(chiave, crea)


def freccia(dimensione: int, colore: Sequence, verso: int = 1) -> pygame.Surface:
    """Chevron ">" (verso=1) o "<" (verso=-1)."""
    chiave = ('freccia', dimensione, tuple(colore), verso)

    def crea():
        ss = 4
        d = dimensione * ss
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        s.fill((colore[0], colore[1], colore[2], 0))
        p = [(0.15, 0.0), (0.55, 0.0), (0.95, 0.5), (0.55, 1.0), (0.15, 1.0), (0.55, 0.5)]
        if verso < 0:
            p = [(1 - x, y) for x, y in p]
        pygame.draw.polygon(s, tuple(colore), [(x * d, y * d) for x, y in p])
        return pygame.transform.smoothscale(s, (dimensione, dimensione))
    return _in_cache(chiave, crea)


def tasto(etichetta: str, altezza: int = 30, colore: Sequence = (228, 232, 242)) -> pygame.Surface:
    """Tasto stilizzato (keycap) con etichetta, per suggerimenti e schermata comandi."""
    chiave = ('tasto', etichetta, altezza, tuple(colore))

    def crea():
        dim = max(10, int(altezza * 0.78))
        f = font(dim)
        t = f.render(etichetta, True, NOTTE)
        w = max(altezza, t.get_width() + int(altezza * 0.6))
        ss = 3
        s = pygame.Surface((w * ss, altezza * ss), pygame.SRCALPHA)
        r = pygame.Rect(0, 0, w * ss, altezza * ss)
        rad = int(altezza * ss * 0.22)
        pygame.draw.rect(s, (70, 74, 92), r, border_radius=rad)
        pygame.draw.rect(s, tuple(colore), r.inflate(-ss * 2, -ss * 5).move(0, -ss * 1.5),
                         border_radius=rad)
        s = pygame.transform.smoothscale(s, (w, altezza))
        s.blit(t, t.get_rect(center=(w // 2, altezza // 2 - 1)))
        return s
    return _in_cache(chiave, crea)
