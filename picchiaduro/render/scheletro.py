"""Scheletro 2D del lottatore in vista laterale: proporzioni e cinematica.

Il corpo e' descritto da una `Posa` (dizionario di parametri: posizione del
bacino, angolo del busto, obiettivi di mani e piedi in coordinate polari o
cartesiane) e risolto in articolazioni con una cinematica a due ossa. Per l'arto
che colpisce una posa puo' chiedere di portarsi con una IK sul bersaglio (il punto
d'impatto della simulazione), avanzando il corpo quanto serve per arrivarci:
cosi' la grafica tocca dove sta la hitbox.

Sistema di coordinate locale (orientato a destra): `u` in avanti, `v` in alto,
entrambi in frazioni di `altezza_mondo`; l'origine e' a terra sotto il lottatore.
Angoli in gradi, misurati dalla verticale verso il basso, positivi in avanti.
Arti: L = braccio anteriore (lontano dalla camera), R = braccio posteriore
(vicino), F = gamba anteriore (lontana), B = gamba posteriore (vicina).
"""

from __future__ import annotations

import math

# ---- proporzioni (frazioni di altezza_mondo, ~7.5 teste)
COSCIA = 0.25
STINCO = 0.245
CAVIGLIA = 0.04              # altezza della caviglia da terra a piede piatto
PIEDE_AVANTI = 0.09          # caviglia -> punta
PIEDE_DIETRO = 0.03          # caviglia -> tallone
BUSTO = 0.315                # bacino -> centro delle spalle
COLLO = 0.106                # centro spalle -> centro testa
OMERO = 0.16
AVAMBRACCIO = 0.17           # gomito -> centro del guantone
RAGGIO_GUANTO = 0.058
RAGGIO_TESTA = 0.058
SFASAMENTO_SPALLE = 0.032    # separazione delle spalle per la rotazione del busto
AVANZO_MAX = 0.30            # quanto puo' avanzare il corpo per raggiungere il bersaglio

PORTATA_BRACCIO = OMERO + AVAMBRACCIO
PORTATA_GAMBA = COSCIA + STINCO

# ---- posa di base (guardia): tutti i parametri con il loro valore neutro
BASE = {
    # bacino e busto
    'hx': -0.015, 'hy': 0.492, 'tors': 7.0, 'twist': 0.5,
    # testa: inclinazione assoluta (gradi, avanti positivo) e spostamento
    'testa': 7.0, 'tx': 0.0, 'ty': 0.0,
    # braccio anteriore L e posteriore R: (x, y) cartesiani dalla spalla,
    # (a, d) polari dalla spalla (angolo, frazione di portata), w = peso polare,
    # s = verso del gomito (+1 basso/dietro, -1 alto/avanti)
    'Lx': 0.235, 'Ly': 0.01, 'La': 70.0, 'Ld': 0.7, 'Lw': 0.0, 'Ls': 1.0,
    'Rx': 0.13, 'Ry': 0.03, 'Ra': 60.0, 'Rd': 0.5, 'Rw': 0.0, 'Rs': 1.0,
    # gamba anteriore F e posteriore B: (x, y) caviglia assoluta da terra,
    # (a, d) polari dal bacino, w = peso polare, p = angolo del piede (tallone su)
    'Fx': 0.135, 'Fy': 0.04, 'Fa': 20.0, 'Fd': 0.8, 'Fw': 0.0, 'Fp': 0.0,
    'Bx': -0.12, 'By': 0.072, 'Ba': -10.0, 'Bd': 0.8, 'Bw': 0.0, 'Bp': 22.0,
    # pesi dell'IK verso il bersaglio per ciascun arto
    'kL': 0.0, 'kR': 0.0, 'kF': 0.0, 'kB': 0.0,
    # sollevamento dell'intero corpo da terra
    'alz': 0.0,
}
CAMPI = tuple(BASE.keys())


def posa(**kw) -> dict:
    """Copia della posa di base con alcuni parametri modificati."""
    p = dict(BASE)
    for k, v in kw.items():
        if k not in p:
            raise KeyError("parametro di posa sconosciuto: %r" % (k,))
        p[k] = v
    return p


def caviglia_y(pitch_deg: float) -> float:
    """Altezza della caviglia perche' la punta del piede inclinato tocchi terra."""
    r = math.radians(pitch_deg)
    return PIEDE_AVANTI * math.sin(r) + 0.040 * math.cos(r) + 0.001 if pitch_deg >= 0 else 0.041 + 0.03 * math.sin(-r)


def mescola(a: dict, b: dict, t: float) -> dict:
    """Interpolazione lineare tra due pose."""
    if t <= 0.0:
        return dict(a)
    if t >= 1.0:
        return dict(b)
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


# ---- cinematica a due ossa
def ik2(ax: float, ay: float, tx: float, ty: float, l1: float, l2: float, segno: float):
    """Risolve un arto a due ossa da (ax, ay) verso (tx, ty).

    Ritorna (giunto, estremo): il gomito/ginocchio sta dal lato antiorario del
    vettore radice->bersaglio se `segno` > 0. L'estremo e' limitato alla portata.
    """
    dx = tx - ax
    dy = ty - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        dx, dy, d = 0.0, -1.0, 1e-9
    ux = dx / d
    uy = dy / d
    dmax = (l1 + l2) * 0.9995
    dmin = abs(l1 - l2) + 1e-3
    if d > dmax:
        d = dmax
    elif d < dmin:
        d = dmin
    a = (l1 * l1 - l2 * l2 + d * d) / (2.0 * d)
    h2 = l1 * l1 - a * a
    h = math.sqrt(h2) if h2 > 0.0 else 0.0
    mx = ax + ux * a
    my = ay + uy * a
    return ((mx - uy * h * segno, my + ux * h * segno), (ax + ux * d, ay + uy * d))


def _polare(ax: float, ay: float, ang: float, dist: float):
    r = math.radians(ang)
    return ax + math.sin(r) * dist, ay - math.cos(r) * dist


class Bersaglio:
    """Punto da colpire (locale, frazioni di altezza) e parametri dell'arto che colpisce."""

    __slots__ = ('u', 'v', 'arto', 'ext', 'ginocchio')

    def __init__(self, u: float, v: float, arto: str, ext: float = 0.98, ginocchio: bool = False):
        self.u = u
        self.v = v
        self.arto = arto          # 'L' | 'R' | 'F' | 'B'
        self.ext = ext            # estensione massima dell'arto (0..1)
        self.ginocchio = ginocchio


def calcola(p: dict, bers=None) -> dict:
    """Articolazioni della posa `p` (con IK opzionale verso `bers`).

    Ritorna un dizionario di punti (u, v) e alcuni valori derivati.
    """
    hx = p['hx']
    hy = p['hy'] + p['alz']
    tors = math.radians(p['tors'])
    st = math.sin(tors)
    ct = math.cos(tors)
    tw = p['twist'] * SFASAMENTO_SPALLE
    # normale in avanti al busto
    nu, nv = ct, -st

    def spalle(hx_):
        smu = hx_ + BUSTO * st
        smv = hy + BUSTO * ct
        return smu, smv

    # ---- avanzamento del corpo per raggiungere il bersaglio
    avanzo = 0.0
    tgt = None                          # obiettivo dell'estremo dell'arto che colpisce
    k = 0.0
    if bers is not None:
        arto = bers.arto
        k = p['k' + arto]
        if k > 1e-3:
            smu, smv = spalle(hx)
            if arto in ('L', 'R'):
                segno_sp = 1.0 if arto == 'L' else -1.0
                ru = smu + nu * tw * segno_sp
                rv = smv + nv * tw * segno_sp
                portata = PORTATA_BRACCIO * bers.ext
                bu, bv = bers.u, bers.v
                dd = math.hypot(bu - ru, bv - rv) or 1.0
                # la mano (centro del guantone) sta un po' prima del bersaglio
                tu = bu - (bu - ru) / dd * (RAGGIO_GUANTO * 0.85)
                tv = bv - (bv - rv) / dd * (RAGGIO_GUANTO * 0.85)
            else:
                ru, rv = hx, hy
                portata = PORTATA_GAMBA * bers.ext
                bu, bv = bers.u, bers.v
                dd = math.hypot(bu - ru, bv - rv) or 1.0
                if bers.ginocchio:
                    tu = bu - (bu - ru) / dd * 0.04
                    tv = bv - (bv - rv) / dd * 0.04
                    portata = COSCIA * 0.98
                else:
                    tu = bu - (bu - ru) / dd * 0.055
                    tv = bv - (bv - rv) / dd * 0.055
            dv = tv - rv
            if abs(dv) < portata:
                du_max = math.sqrt(portata * portata - dv * dv)
                avanzo = max(0.0, (tu - du_max) - ru)
            else:
                avanzo = max(0.0, tu - ru)
            avanzo = min(AVANZO_MAX, avanzo) * k
            tgt = (tu, tv)
    hx += avanzo
    smu, smv = spalle(hx)

    P = {}
    P['anca'] = (hx, hy)
    P['spalle'] = (smu, smv)
    P['nu'] = nu
    P['nv'] = nv
    P['tors_rad'] = tors
    P['avanzo'] = avanzo

    # ---- testa
    th = math.radians(p['testa'])
    hu = smu + p['tx'] + math.sin(th) * COLLO
    hv = smv + p['ty'] + math.cos(th) * COLLO
    P['testa'] = (hu, hv)
    P['testa_rad'] = th
    P['collo'] = (smu + p['tx'] * 0.5 + math.sin(th) * 0.02, smv + p['ty'] * 0.5 + math.cos(th) * 0.02)

    # ---- braccia
    for nome, segno_sp in (('L', 1.0), ('R', -1.0)):
        su = smu + nu * tw * segno_sp
        sv = smv + nv * tw * segno_sp
        wp = p[nome + 'w']
        cx_, cy_ = su + p[nome + 'x'], sv + p[nome + 'y']
        pu, pv = _polare(su, sv, p[nome + 'a'], p[nome + 'd'] * PORTATA_BRACCIO)
        mu = cx_ + (pu - cx_) * wp
        mv = cy_ + (pv - cy_) * wp
        if tgt is not None and bers.arto == nome:
            kk = p['k' + nome]
            mu += (tgt[0] - mu) * kk
            mv += (tgt[1] - mv) * kk
        gomito, mano = ik2(su, sv, mu, mv, OMERO, AVAMBRACCIO, -p[nome + 's'])
        P['spalla' + nome] = (su, sv)
        P['gomito' + nome] = gomito
        P['mano' + nome] = mano

    # ---- gambe
    for nome, off in (('F', 0.012), ('B', -0.012)):
        au = hx + off
        av = hy - 0.02
        wp = p[nome + 'w']
        cu, cv = p[nome + 'x'], p[nome + 'y']
        # i piedi a terra seguono l'avanzamento in parte (il corpo scivola in avanti)
        if avanzo:
            cu += avanzo * (0.85 if nome == 'F' else 0.5)
        pu, pv = _polare(au, av, p[nome + 'a'], p[nome + 'd'] * PORTATA_GAMBA)
        mu = cu + (pu - cu) * wp
        mv = cv + (pv - cv) * wp
        if tgt is not None and bers.arto == nome:
            kk = p['k' + nome]
            if bers.ginocchio:
                # il ginocchio va sul bersaglio: caviglia ricavata dalla coscia in avanti
                ang_c = math.atan2(tgt[0] - au, av - tgt[1])
                ang_s = ang_c - math.radians(78.0)
                ku = au + math.sin(ang_c) * COSCIA
                kv = av - math.cos(ang_c) * COSCIA
                tu2 = ku + math.sin(ang_s) * STINCO
                tv2 = kv - math.cos(ang_s) * STINCO
            else:
                tu2, tv2 = tgt
            mu += (tu2 - mu) * kk
            mv += (tv2 - mv) * kk
        ginocchio, caviglia = ik2(au, av, mu, mv, COSCIA, STINCO, 1.0)
        pr = math.radians(p[nome + 'p'])
        fu, fv = math.cos(pr), -math.sin(pr)
        P['anca' + nome] = (au, av)
        P['ginocchio' + nome] = ginocchio
        P['caviglia' + nome] = caviglia
        P['punta' + nome] = (caviglia[0] + fu * PIEDE_AVANTI, caviglia[1] + fv * PIEDE_AVANTI)
        P['tallone' + nome] = (caviglia[0] - fu * PIEDE_DIETRO, caviglia[1] - fv * PIEDE_DIETRO)
        P['piede_dir' + nome] = (fu, fv)
    return P
