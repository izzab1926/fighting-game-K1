"""Animazione del lottatore: pose per ogni stato e mossa, strati procedurali.

Da uno `Lottatore` (stato, frame, fase della mossa, direzioni, ...) e dal tempo di
gioco ricava la `Posa` dello scheletro (vedi scheletro.py) piu' alcuni dati di
contorno (espressione, lampo, tremolio, bersaglio dell'IK). Non disegna nulla.

Ogni animazione e' una funzione continua del tempo: keyframe con easing per le
mosse e le reazioni, cicli per camminata e guardia, e sopra tutto strati
procedurali (molleggio a ritmo, respiro, affanno).
"""

from __future__ import annotations

import math
from typing import Optional

from ..sim import regole as R
from ..sim.mosse import MOSSE
from . import scheletro as S
from .scheletro import BASE, Bersaglio, mescola, posa

# ---- easing


def _lin(t):
    return t


def _out(t):
    return 1.0 - (1.0 - t) * (1.0 - t)


def _out3(t):
    u = 1.0 - t
    return 1.0 - u * u * u


def _in(t):
    return t * t


def _in3(t):
    return t * t * t


def _io(t):
    return t * t * (3.0 - 2.0 * t)


def _back(t):
    """Arriva un po' oltre e torna (rimbalzo elastico leggero)."""
    c = 1.4
    u = t - 1.0
    return 1.0 + (c + 1.0) * u * u * u + c * u * u


EASE = {'l': _lin, 'o': _out, 'o3': _out3, 'i': _in, 'i3': _in3, 'io': _io, 'b': _back}


def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def sfuma(x: float, a: float, b: float) -> float:
    """0 sotto a, 1 sopra b, liscio in mezzo."""
    if b == a:
        return 1.0 if x >= b else 0.0
    return _io(clamp01((x - a) / (b - a)))


# ---- campionamento di keyframe
def campiona(chiavi, t: float) -> dict:
    """Interpola una lista di (t, posa, easing) ordinata per t.

    L'easing di una chiave vale per il tratto che ARRIVA a quella chiave. I parametri
    'Ls'/'Rs' (verso del gomito) non si interpolano: si prende quello del tratto.
    """
    if t <= chiavi[0][0]:
        return dict(chiavi[0][1])
    for i in range(1, len(chiavi)):
        t1, p1, e1 = chiavi[i]
        if t <= t1:
            t0, p0, _ = chiavi[i - 1]
            u = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            r = mescola(p0, p1, EASE[e1](clamp01(u)))
            r['Ls'] = p0['Ls'] if u < 0.999 else p1['Ls']
            r['Rs'] = p0['Rs'] if u < 0.999 else p1['Rs']
            return r
    return dict(chiavi[-1][1])


# ---- pose fondamentali
GUARDIA = posa()

PARATA = posa(hx=-0.03, hy=0.452, tors=14.0, twist=0.3, testa=14.0,
              Lx=0.115, Ly=0.075, Rx=0.07, Ry=0.12,
              Fx=0.14, Bx=-0.14)

# a terra (supino): busto orizzontale all'indietro, gambe in avanti
A_TERRA = posa(hx=-0.05, hy=0.085, tors=-88.0, twist=0.0, testa=-84.0, ty=-0.026,
               Lx=-0.02, Ly=-0.075, Rx=0.03, Ry=-0.07,
               Fx=0.40, Fy=0.06, Fp=-28.0, Bx=0.37, By=0.075, Bp=-32.0,
               alz=0.0)


# ============================================================ risultato
class Anim:
    """Esito dell'animazione di un frame."""

    __slots__ = ('posa', 'bers', 'occhi', 'bocca', 'flash', 'tremore', 'stelle', 'alpha',
                 'resp', 'lead_avanti', 'aura', 'sudore', 'scia', 'chiave', 'fusione', 'giro')

    def __init__(self, p: dict):
        self.posa = p
        self.bers: Optional[Bersaglio] = None
        self.occhi = 's'            # a aperti, s stretti, c chiusi, x storditi
        self.bocca = 'c'            # c chiusa, a aperta, d denti stretti, g urlo/sorriso
        self.flash = 0.0            # 0..1 lampo bianco
        self.tremore = 0.0          # ampiezza (frazione dell'altezza) del tremolio da hitstop
        self.stelle = False         # stelle di stordimento
        self.alpha = 1.0
        self.resp = 0.0             # -1..1 ciclo del respiro
        self.lead_avanti = False    # braccio anteriore disegnato sopra il busto
        self.aura = 0.0
        self.sudore = 0.0
        self.scia = None            # arto che lascia la scia ('L','R','F','B')
        self.chiave = None          # identifica la sequenza (per la fusione tra pose)
        self.fusione = 0.09         # secondi di fusione dalla posa precedente
        self.giro = 0.0             # rotazione su se stesso (-1..1) per il calcio girato


# ============================================================ strati procedurali
def _molleggio(p: dict, tempo: float, ritmo: float, fase: float, amp: float) -> None:
    """Guardia che molleggia a ritmo, con spostamento del peso."""
    if amp <= 0.0:
        return
    w = 2.0 * math.pi * 1.75 * ritmo
    a = w * tempo + fase
    s = math.sin(a)
    c = math.cos(a)
    peso = math.sin(2.0 * math.pi * 0.31 * tempo + fase * 1.7)
    su = 0.5 + 0.5 * s                       # 0 giu, 1 su
    p['hy'] += (0.006 - 0.014 * su) * amp
    p['hx'] += (0.006 * c + 0.010 * peso) * amp
    p['tors'] += (1.6 * s + 1.2 * peso) * amp
    p['testa'] += (-1.8 * s + 0.8 * peso) * amp
    p['By'] += 0.014 * su * amp
    p['Bp'] += 9.0 * su * amp
    p['Fy'] += 0.004 * (1.0 - su) * amp
    p['Bx'] += 0.006 * peso * amp
    p['Fx'] += -0.006 * peso * amp
    p['Ly'] += 0.014 * math.sin(a + 0.9) * amp
    p['Lx'] += 0.010 * math.cos(a * 0.5 + 0.4) * amp
    p['Ry'] += 0.010 * math.sin(a + 1.6) * amp
    p['Rx'] += 0.006 * math.cos(a + 0.2) * amp


def _affanno(p: dict, tempo: float, quanto: float, fase: float) -> None:
    """Fiato corto: spalle basse, testa avanti, braccia pesanti."""
    if quanto <= 0.0:
        return
    hv = math.sin(2.0 * math.pi * 0.85 * tempo + fase)
    p['tors'] += (7.0 + 2.5 * hv) * quanto
    p['testa'] += (7.0 - 3.0 * hv) * quanto
    p['hy'] -= 0.016 * quanto
    p['Ly'] -= 0.05 * quanto
    p['Ry'] -= 0.05 * quanto
    p['Lx'] -= 0.03 * quanto
    p['hx'] -= 0.006 * quanto
    p['Fx'] += 0.01 * quanto
    p['Bx'] -= 0.01 * quanto


# ============================================================ stati semplici
def _guardia(l, tempo, fase, amp=1.0, ritmo=1.0):
    p = dict(GUARDIA)
    _molleggio(p, tempo, ritmo, fase, amp)
    return p


def _parata(l, tempo, fase):
    p = dict(PARATA)
    _molleggio(p, tempo, 0.8, fase, 0.45)
    return p


def _cammina(l, tempo, fase, vel):
    """Passo di combattimento: i piedi si alternano, il busto resta in guardia."""
    p = dict(GUARDIA)
    avanti = l.direzione_cammino
    lat = l.direzione_profondita
    f = l.frame_stato / 36.0
    if avanti == 0 and lat != 0:
        ampiezza = 0.055
        sens = 1.0
    elif avanti < 0:
        ampiezza = 0.075
        sens = -1.0
    else:
        ampiezza = 0.105
        sens = 1.0
    # atterraggi del piede anteriore a f=0.25 e del posteriore a f=0.75 (evento Passo)
    def piede(atterra, base, avvio_pos):
        ph = (f * sens - atterra + 1.0) % 1.0        # 0 = appena appoggiato
        # appoggio 0..0.7: scivola indietro; volo 0.7..1: va avanti
        if ph < 0.70:
            x = ampiezza * (1.0 - 2.0 * ph / 0.70)
            y = 0.0
        else:
            s = (ph - 0.70) / 0.30
            x = ampiezza * (-1.0 + 2.0 * _io(s))
            y = 0.038 * math.sin(math.pi * s)
        return base + x, y, ph
    fx, fy, fph = piede(0.25, GUARDIA['Fx'], 0.0)
    bx, by, bph = piede(0.75, GUARDIA['Bx'], 0.0)
    p['Fx'] = fx
    p['Fy'] = 0.04 + fy
    p['Bx'] = bx
    p['By'] = 0.05 + by + 0.02
    p['Bp'] = 14.0 + 30.0 * max(0.0, 1.0 - abs(bph - 0.85) * 5.0)
    p['Fp'] = -6.0 * (fy / 0.038 if fy else 0.0)
    p['hy'] = 0.452 + 0.010 * math.cos(4.0 * math.pi * f - 0.5) * (0.6 + 0.4 * (ampiezza / 0.105))
    p['hx'] = -0.02 + 0.012 * sens
    p['tors'] = 11.0 + 3.0 * sens
    # le braccia dondolano a ritmo del passo
    p['Ly'] += 0.014 * math.sin(4.0 * math.pi * f)
    p['Ry'] += 0.012 * math.sin(4.0 * math.pi * f + 1.2)
    _molleggio(p, tempo, 0.9, fase, 0.25)
    return p


# ============================================================ mosse
# Ogni mossa: dizionario fase -> lista di keyframe (t, posa, easing) con t = progresso
# della fase. La posa "estesa" ha k*=1: l'arto va sul bersaglio dell'IK (il punto d'impatto).
def _p(**kw):
    return posa(**kw)


def _chiavi_mosse() -> dict:
    G = GUARDIA
    M = {}

    def std(carica, esteso, t_carica=0.5, rec=0.5):
        return {
            'avvio': [(0.0, G, 'l'), (t_carica, carica, 'o'), (1.0, mescola(carica, esteso, 0.88), 'i')],
            'attivo': [(0.0, esteso, 'l'), (1.0, esteso, 'l')],
            'recupero': [(0.0, esteso, 'l'), (rec, mescola(esteso, G, 0.6), 'o'), (1.0, G, 'io')],
        }

    # ---- JAB (braccio anteriore): scatto dritto con avanzamento della spalla
    carica = _p(hx=-0.035, tors=4.0, twist=0.1, testa=4.0, Lx=0.10, Ly=0.03, Rx=0.13, Ry=0.05,
                Fx=0.13, Bx=-0.135, Bp=26.0)
    esteso = _p(hx=0.03, tors=20.0, twist=1.0, testa=12.0, Lx=0.30, Ly=0.02, La=84.0, Ld=1.0,
                Lw=1.0, kL=1.0, Rx=0.10, Ry=0.06, Fx=0.19, Bx=-0.14, By=0.096, Bp=40.0)
    M['jab'] = std(carica, esteso, 0.45)

    # ---- DIRETTO (braccio posteriore): rotazione dell'anca, spalla posteriore avanti
    carica = _p(hx=-0.055, hy=0.48, tors=2.0, twist=1.2, testa=3.0, Lx=0.19, Ly=0.06, Rx=0.04, Ry=0.03,
                Fx=0.14, Bx=-0.14, By=0.078, Bp=26.0)
    esteso = _p(hx=0.055, hy=0.49, tors=25.0, twist=-1.2, testa=13.0, Lx=0.12, Ly=0.07,
                Rx=0.32, Ry=0.02, Ra=84.0, Rd=1.0, Rw=1.0, kR=1.0,
                Fx=0.20, Bx=-0.11, By=0.112, Bp=58.0)
    M['diretto'] = std(carica, esteso, 0.55)

    # ---- GANCIO (braccio anteriore, gomito alto)
    carica = _p(hx=-0.05, hy=0.48, tors=1.0, twist=-0.6, testa=5.0,
                Lx=-0.04, Ly=0.09, Ls=-1.0, Rx=0.12, Ry=0.05, Fx=0.13, Bx=-0.14, Bp=26.0)
    esteso = _p(hx=0.05, hy=0.48, tors=16.0, twist=1.3, testa=10.0,
                Lx=0.24, Ly=0.07, La=80.0, Ld=0.8, Lw=1.0, Ls=-1.0, kL=1.0,
                Rx=0.10, Ry=0.06, Fx=0.19, Bx=-0.14, By=0.09, Bp=42.0)
    M['gancio'] = std(carica, esteso, 0.6)

    # ---- CALCIO BASSO (gamba posteriore, colpo alla coscia)
    carica = _p(hx=-0.04, hy=0.485, tors=-3.0, twist=0.9, testa=4.0, Lx=0.16, Ly=0.07, Rx=0.02, Ry=0.06,
                Fx=0.12, Bx=-0.20, By=0.10, Bp=34.0)
    volo = _p(hx=0.0, hy=0.49, tors=-9.0, twist=1.0, testa=3.0, Lx=0.17, Ly=0.08, Rx=-0.06, Ry=0.03,
              Fx=0.12, Fp=0.0, Bx=-0.03, By=0.15, Ba=42.0, Bd=0.95, Bw=1.0, Bp=-10.0)
    esteso = _p(hx=0.06, hy=0.49, tors=-15.0, twist=1.0, testa=2.0, Lx=0.17, Ly=0.09, Rx=-0.10, Ry=0.0,
                Fx=0.14, Fp=-4.0, Ba=68.0, Bd=1.0, Bw=1.0, Bp=-12.0, kB=1.0)
    M['calcio_basso'] = {
        'avvio': [(0.0, G, 'l'), (0.5, carica, 'o'), (0.85, volo, 'io'), (1.0, mescola(volo, esteso, 0.9), 'i')],
        'attivo': [(0.0, esteso, 'l'), (1.0, esteso, 'l')],
        'recupero': [(0.0, esteso, 'l'), (0.5, mescola(esteso, G, 0.55), 'o'), (1.0, G, 'io')],
    }

    # ---- GINOCCHIATA (ginocchio verso l'alto, mani che tirano)
    carica = _p(hx=-0.03, hy=0.47, tors=12.0, twist=0.0, testa=10.0, Lx=0.24, Ly=0.09, Rx=0.20, Ry=0.06,
                Fx=0.12, Bx=-0.16, By=0.09, Bp=34.0)
    esteso = _p(hx=0.05, hy=0.50, tors=2.0, twist=0.3, testa=8.0, Lx=0.16, Ly=-0.07, Rx=0.14, Ry=-0.10,
                Fx=0.14, Fp=20.0, Fy=caviglia_y_(20.0),
                Ba=40.0, Bd=0.7, Bw=1.0, Bp=-35.0, kB=1.0)
    M['ginocchiata'] = std(carica, esteso, 0.5)

    # ---- CALCIO ALTO (gamba posteriore alta, busto indietro)
    carica = _p(hx=-0.03, hy=0.495, tors=-4.0, twist=0.7, testa=3.0, Lx=0.17, Ly=0.07, Rx=0.08, Ry=0.05,
                Fx=0.12, Fp=28.0, Fy=caviglia_y_(28.0),
                Ba=48.0, Bd=0.62, Bw=1.0, Bp=30.0)
    esteso = _p(hx=0.05, hy=0.51, tors=-26.0, twist=1.0, testa=-4.0, Lx=0.13, Ly=0.10, Rx=-0.10, Ry=-0.03,
                Fx=0.14, Fp=52.0, Fy=caviglia_y_(52.0),
                Ba=112.0, Bd=1.0, Bw=1.0, Bp=-20.0, kB=1.0)
    M['calcio_alto'] = {
        'avvio': [(0.0, G, 'l'), (0.45, carica, 'o'), (1.0, mescola(carica, esteso, 0.9), 'i3')],
        'attivo': [(0.0, esteso, 'l'), (1.0, esteso, 'l')],
        'recupero': [(0.0, esteso, 'l'), (0.5, mescola(esteso, carica, 0.6), 'o'), (1.0, G, 'io')],
    }

    # ---- CALCIO GIRATO (super: giro su se stessi e calcio a frusta)
    carica = _p(hx=-0.05, hy=0.44, tors=22.0, twist=1.6, testa=14.0, Lx=0.02, Ly=0.06, La=-40.0, Ld=0.9,
                Lw=0.0, Rx=-0.10, Ry=0.08, Fx=0.10, Bx=-0.19, By=0.09, Bp=34.0)
    giro = _p(hx=-0.02, hy=0.43, tors=32.0, twist=-1.4, testa=20.0, Lx=0.02, Ly=-0.02, Rx=-0.06, Ry=0.10,
              Fx=0.09, Bx=-0.10, By=0.20, Ba=-20.0, Bd=0.95, Bw=1.0, Bp=-10.0)
    esteso = _p(hx=0.05, hy=0.46, tors=30.0, twist=-1.0, testa=14.0, Lx=0.10, Ly=0.13, Rx=-0.20, Ry=-0.02,
                Fx=0.10, Ba=80.0, Bd=1.0, Bw=1.0, Bp=-14.0, kB=1.0)
    M['calcio_girato'] = {
        'avvio': [(0.0, G, 'l'), (0.35, carica, 'o'), (0.7, giro, 'io'), (1.0, mescola(giro, esteso, 0.9), 'i')],
        'attivo': [(0.0, esteso, 'l'), (1.0, esteso, 'l')],
        'recupero': [(0.0, esteso, 'l'), (0.4, mescola(esteso, carica, 0.5), 'o'), (1.0, G, 'io')],
    }
    return M


def caviglia_y_(pitch):
    return S.caviglia_y(pitch)


_MOSSE_CHIAVI = None


def chiavi_mosse() -> dict:
    global _MOSSE_CHIAVI
    if _MOSSE_CHIAVI is None:
        _MOSSE_CHIAVI = _chiavi_mosse()
    return _MOSSE_CHIAVI


ARTO_MOSSA = {'pugno_avanti': 'L', 'pugno_dietro': 'R', 'gamba_dietro': 'B', 'gamba_avanti': 'F'}
ESTENSIONE = {'gancio': 0.80}


def bersaglio_mossa(l, avv=None) -> Optional[Bersaglio]:
    """Bersaglio locale dell'IK (frazioni di altezza) per la mossa in corso."""
    m = l.dati_mossa
    if m is None:
        return None
    H = l.altezza_mondo
    verso = 1.0 if l.guarda_destra else -1.0
    if l.punto_impatto is not None:
        px, _, ph = l.punto_impatto
    elif avv is not None and R.colpo_raggiunge(l, avv, m.nome):
        px, _, ph = R.punto_impatto(l, avv, m.nome)
    else:
        px = R.fronte(l) + verso * R.portata_effettiva(l, m.nome)
        ph = m.altezza_colpo * H
    u = (px - l.x) * verso / H
    v = (ph - l.h) / H
    return Bersaglio(u, v, ARTO_MOSSA[m.arto], ESTENSIONE.get(m.nome, 0.98), m.nome == 'ginocchiata')


def _attacco(l, a: 'Anim') -> dict:
    tab = chiavi_mosse().get(l.mossa) or chiavi_mosse()['jab']
    ph = l.fase_mossa or 'avvio'
    p = campiona(tab[ph], clamp01(l.progresso_fase))
    m = l.dati_mossa
    a.bers = None
    a.scia = ARTO_MOSSA[m.arto] if m else None
    a.lead_avanti = bool(m and m.arto == 'pugno_avanti')
    a.occhi = 's'
    a.bocca = 'a' if getattr(l, 'mossa_stanca', False) else 'd'
    a.fusione = 0.035
    return p


# ============================================================ reazioni
HIT_ALTO = _p(hx=-0.075, hy=0.485, tors=-20.0, twist=-0.2, testa=-36.0, tx=-0.03, ty=-0.005,
              Lx=0.09, Ly=0.06, Rx=0.03, Ry=0.03, Rw=0.0, Fx=0.16, Bx=-0.16, Bp=10.0, By=0.055)
HIT_MEDIO = _p(hx=-0.05, hy=0.44, tors=38.0, twist=0.0, testa=32.0, Lx=0.12, Ly=-0.12, Rx=0.08, Ry=-0.13,
               Fx=0.13, Bx=-0.15, Bp=14.0, By=0.06)
HIT_BASSO = _p(hx=-0.04, hy=0.41, tors=13.0, twist=0.6, testa=10.0, Lx=0.22, Ly=0.10, Rx=0.02, Ry=0.09,
               Fx=0.19, Fy=0.11, Fp=10.0, Bx=-0.13, Bp=14.0, By=0.06)


def _reazione(l, a: 'Anim', tempo, fase) -> dict:
    """Colpito: scatto immediato nella direzione del colpo, poi ritorno alla guardia."""
    f = l.frame_stato
    d = max(1, l.durata_stato)
    forza = clamp01(l.forza_colpo_subito if l.forza_colpo_subito else 0.5)
    amp = 0.55 + 0.6 * forza
    liv = l.colpo_subito or 'alto'
    bersaglio = {'alto': HIT_ALTO, 'medio': HIT_MEDIO, 'basso': HIT_BASSO}.get(liv, HIT_ALTO)
    salita = 1.0 - math.exp(-(f + 1) / 1.5)
    ritorno = 1.0 - sfuma(f / d, 0.25, 1.0)
    onda = 1.0 + 0.22 * math.sin(f * 0.75) * math.exp(-f / 7.0)
    env = salita * ritorno * onda * amp
    p = mescola(GUARDIA, bersaglio, min(1.35, env)) if env <= 1.0 else _estrapola(GUARDIA, bersaglio, env)
    if liv == 'alto':
        a.occhi, a.bocca = 'c', 'a'
    elif liv == 'medio':
        a.occhi, a.bocca = 'c', 'a'
    else:
        a.occhi, a.bocca = 's', 'd'
    a.tremore = 0.008 + 0.010 * forza
    a.fusione = 0.012
    return p


def _estrapola(a: dict, b: dict, t: float) -> dict:
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


BLOCCO = _p(hx=-0.075, hy=0.462, tors=22.0, twist=0.2, testa=18.0, Lx=0.10, Ly=0.075, Rx=0.06, Ry=0.12,
            Fx=0.155, Bx=-0.155, Bp=8.0, By=0.052)


def _bloccato(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    d = max(1, l.durata_stato)
    rinculo = math.exp(-f / 5.0) * (1.0 - sfuma(f / d, 0.6, 1.0))
    forza = 0.6 + 0.4 * clamp01(l.forza_colpo_subito or 0.5)
    p = mescola(PARATA, BLOCCO, clamp01(rinculo * forza))
    a.occhi, a.bocca = 's', 'd'
    a.fusione = 0.02
    return p


ROTTA_A = _p(hx=-0.06, hy=0.47, tors=-14.0, twist=0.0, testa=-16.0, tx=-0.01,
             Lx=0.05, Ly=0.02, La=95.0, Ld=0.95, Lw=1.0, Rx=-0.02, Ry=0.02, Ra=-70.0, Rd=0.95, Rw=1.0,
             Fx=0.16, Bx=-0.15, Bp=14.0, By=0.06)
ROTTA_B = _p(hx=-0.03, hy=0.44, tors=8.0, twist=0.3, testa=-8.0,
             Lx=0.03, Ly=-0.02, La=125.0, Ld=0.85, Lw=1.0, Rx=0.0, Ry=0.0, Ra=-95.0, Rd=0.9, Rw=1.0,
             Fx=0.13, Bx=-0.17, Bp=8.0, By=0.055)


def _rotta(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    d = max(1, l.durata_stato)
    ondeggio = 0.5 + 0.5 * math.sin(f * 0.28)
    p = mescola(ROTTA_A, ROTTA_B, ondeggio)
    uscita = sfuma(f / d, 0.82, 1.0)
    p = mescola(p, GUARDIA, uscita)
    p['hx'] += 0.02 * math.sin(f * 0.14)
    a.occhi, a.bocca = 'x', 'a'
    a.stelle = uscita < 0.7
    a.fusione = 0.03
    return p


# ============================================================ schivate
def _schivata(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    d = max(1, l.durata_stato)
    u = f / d
    if l.tipo_schivata == 'indietro':
        env = math.sin(math.pi * clamp01(u * 1.05))
        base = _p(hx=-0.11, hy=0.50, tors=-14.0, twist=0.3, testa=-4.0, Lx=0.19, Ly=0.06, Rx=0.10, Ry=0.09,
                  Fx=0.12, Fy=0.14, Fp=-10.0, Bx=-0.10, By=0.17, Bp=6.0, alz=0.0)
        p = mescola(GUARDIA, base, clamp01(env * 1.4))
        p['alz'] = 0.055 * math.sin(math.pi * clamp01(u * 1.05)) ** 0.8
        # atterraggio in accosciata
        att = sfuma(u, 0.78, 0.95) * (1.0 - sfuma(u, 0.95, 1.0))
        p['hy'] -= 0.05 * att
    else:
        env = math.sin(math.pi * clamp01(u)) ** 0.7
        base = _p(hx=-0.02, hy=0.395, tors=26.0, twist=0.9, testa=20.0, Lx=0.14, Ly=0.08, Rx=0.08, Ry=0.11,
                  Fx=0.17, Bx=-0.15, Bp=10.0, By=0.055)
        p = mescola(GUARDIA, base, env)
        p['tors'] += 5.0 * math.sin(u * 9.0) * env
    a.occhi, a.bocca = 's', 'c'
    a.fusione = 0.03
    return p


# ============================================================ a terra
def _cf(chiavi_frame, f):
    """Campiona chiavi espresse in frame: (frame, posa, easing)."""
    return campiona(chiavi_frame, float(f))


CADUTA_1 = _p(hx=-0.16, hy=0.45, tors=-34.0, twist=-0.3, testa=-40.0, tx=-0.03,
              Lx=0.04, Ly=0.10, La=140.0, Ld=0.9, Lw=1.0, Rx=0.0, Ry=0.06, Ra=-110.0, Rd=0.9, Rw=1.0,
              Fx=0.20, Fy=0.20, Fp=-25.0, Bx=-0.05, By=0.16, Bp=-20.0, alz=0.0)
CADUTA_2 = _p(hx=-0.16, hy=0.26, tors=-68.0, twist=0.0, testa=-70.0, ty=-0.012,
              Lx=0.0, Ly=0.06, La=160.0, Ld=0.9, Lw=1.0, Rx=0.0, Ry=0.0, Ra=-130.0, Rd=0.9, Rw=1.0,
              Fx=0.30, Fy=0.22, Fp=-30.0, Bx=0.24, By=0.16, Bp=-30.0)
STESO = _p(hx=-0.03, hy=0.085, tors=-88.0, twist=0.0, testa=-86.0, ty=-0.034,
           Lx=-0.16, Ly=-0.045, Rx=-0.12, Ry=-0.06,
           Fx=0.43, Fy=0.06, Fp=-30.0, Bx=0.40, By=0.075, Bp=-34.0)
STESO_2 = _p(hx=-0.03, hy=0.09, tors=-86.0, twist=0.0, testa=-80.0, ty=-0.030,
             Lx=-0.14, Ly=-0.05, Rx=-0.10, Ry=-0.06,
             Fx=0.41, Fy=0.06, Fp=-28.0, Bx=0.33, By=0.085, Bp=-28.0)
# a terra che prova a tirarsi su: busto sollevato, appoggio sui gomiti
STESO_SU = _p(hx=-0.05, hy=0.095, tors=-58.0, twist=0.0, testa=-30.0, ty=-0.01,
              Lx=-0.06, Ly=-0.14, Rx=-0.02, Ry=-0.17,
              Fx=0.40, Fy=0.06, Fp=-28.0, Bx=0.25, By=0.14, Bp=-10.0)
SEDUTO = _p(hx=-0.08, hy=0.09, tors=-14.0, twist=0.0, testa=8.0, ty=-0.01,
            Lx=-0.06, Ly=-0.13, Rx=-0.10, Ry=-0.12,
            Fx=0.38, Fy=0.06, Fp=-24.0, Bx=0.32, By=0.075, Bp=-24.0)
INGINOCCHIATO = _p(hx=-0.02, hy=0.30, tors=30.0, twist=0.3, testa=16.0,
                   Lx=0.20, Ly=-0.05, Rx=0.18, Ry=-0.12,
                   Fx=0.15, Fy=0.04, Fp=0.0, Bx=-0.16, By=0.075, Bp=52.0)


def _atterrato(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    ch = [(0, _colpito_lancio(), 'l'), (9, CADUTA_1, 'o'), (20, CADUTA_2, 'i'), (28, mescola(STESO, CADUTA_2, 0.08), 'i'),
          (33, mescola(STESO, STESO_SU, 0.0), 'b'), (36, STESO, 'o'), (70, STESO_2, 'io'), (100, STESO_SU, 'io')]
    p = _cf(ch, f)
    # rimbalzo sul tappeto
    if 27 <= f <= 38:
        p['hy'] += 0.022 * math.sin(math.pi * (f - 27) / 11.0)
    if f > 36:
        p['tors'] += 1.2 * math.sin(tempo * 2.4 + fase)
    a.occhi = 'x' if f < 60 else 'c'
    a.bocca = 'a'
    a.stelle = 32 < f < 90
    a.fusione = 0.02
    return p


def _colpito_lancio() -> dict:
    return HIT_ALTO


def _ko(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    ch = [(0, HIT_ALTO, 'l'), (8, CADUTA_1, 'o'), (19, CADUTA_2, 'i'), (27, STESO, 'i'), (36, STESO, 'o'),
          (70, STESO_2, 'io')]
    p = _cf(ch, min(f, 200))
    if 26 <= f <= 38:
        p['hy'] += 0.024 * math.sin(math.pi * (f - 26) / 12.0)
    if f > 36:
        p['tors'] += 0.8 * math.sin(tempo * 1.9 + fase)
    a.occhi = 'x' if f < 50 else 'c'
    a.bocca = 'a'
    a.stelle = 30 < f < 200
    a.fusione = 0.02
    return p


def _rialzo(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    ch = [(0, STESO_SU, 'l'), (11, SEDUTO, 'io'), (23, INGINOCCHIATO, 'io'), (33, mescola(GUARDIA, INGINOCCHIATO, 0.25), 'o'),
          (40, GUARDIA, 'io')]
    p = _cf(ch, f)
    a.occhi = 's'
    a.bocca = 'a' if f < 30 else 'd'
    a.fusione = 0.03
    return p


# ============================================================ fine round
def _vittoria(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    ritmo = 2.0 * math.pi * 1.5 * tempo + fase
    su = _p(hx=-0.02, hy=0.51, tors=-6.0, twist=0.0, testa=-10.0,
            Lx=0.0, Ly=0.0, La=150.0, Ld=1.0, Lw=1.0, Rx=0.0, Ry=0.0, Ra=176.0, Rd=1.0, Rw=1.0,
            Fx=0.17, Bx=-0.15, Bp=10.0, By=0.06)
    p = dict(su)
    t = sfuma(f, 0, 8)
    p = mescola(GUARDIA, su, t)
    # pugni alzati che pompano a tempo
    pompa = math.sin(ritmo)
    p['La'] += 12.0 * pompa
    p['Ra'] += -10.0 * pompa
    p['hy'] += 0.008 * math.sin(2.0 * ritmo)
    # salto iniziale
    if f < 26:
        p['alz'] = 0.085 * math.sin(math.pi * f / 26.0)
        p['Fy'] += 0.05 * math.sin(math.pi * f / 26.0)
        p['By'] += 0.05 * math.sin(math.pi * f / 26.0)
    a.occhi = 's'
    a.bocca = 'g'
    a.fusione = 0.05
    return p


def _sconfitta(l, a: 'Anim', tempo, fase) -> dict:
    p = _p(hx=-0.05, hy=0.475, tors=24.0, twist=0.0, testa=38.0, tx=0.01, ty=-0.02,
           Lx=0.0, Ly=0.0, La=6.0, Ld=0.92, Lw=1.0, Rx=0.0, Ry=0.0, Ra=-8.0, Rd=0.92, Rw=1.0, Rs=1.0,
           Fx=0.11, Bx=-0.09, Bp=0.0, By=0.043)
    r = math.sin(2.0 * math.pi * 0.55 * tempo + fase)
    p['tors'] += 2.5 * r
    p['hy'] += 0.004 * r
    p['testa'] += -2.0 * r
    p['La'] += 3.0 * math.sin(tempo * 1.7 + 1.0)
    p['Ra'] += 3.0 * math.sin(tempo * 1.5)
    a.occhi = 'c'
    a.bocca = 'a'
    a.sudore = 1.0
    a.fusione = 0.12
    return p


def _intro(l, a: 'Anim', tempo, fase) -> dict:
    f = l.frame_stato
    # 1) guanti che si battono e scalpitio, 2) saluto al pubblico, 3) guardia
    batti = _p(hx=-0.02, hy=0.485, tors=5.0, twist=0.2, testa=3.0, Lx=0.16, Ly=-0.03, Rx=0.15, Ry=-0.02,
               Fx=0.15, Bx=-0.14)
    saluto = _p(hx=-0.02, hy=0.505, tors=-3.0, twist=0.0, testa=-8.0,
                Lx=0.10, Ly=-0.08, Rx=0.0, Ry=0.0, Ra=155.0, Rd=1.0, Rw=1.0,
                Fx=0.15, Bx=-0.14)
    saluto2 = _p(hx=-0.02, hy=0.505, tors=-3.0, twist=0.0, testa=-8.0,
                 La=150.0, Ld=1.0, Lw=1.0, Ra=170.0, Rd=1.0, Rw=1.0,
                 Fx=0.15, Bx=-0.14)
    ch = [(0, GUARDIA, 'l'), (14, batti, 'io'), (38, batti, 'l'), (50, saluto, 'io'), (72, saluto2, 'io'),
          (92, saluto2, 'l'), (110, GUARDIA, 'io')]
    p = _cf(ch, min(f, 110))
    ritmo = 2.0 * math.pi * 1.9 * tempo + fase
    p['hy'] += 0.010 * math.sin(ritmo)
    if 14 <= f < 38:
        pt = math.sin(f * 1.1)
        p['Lx'] += 0.03 * pt
        p['Rx'] -= 0.03 * pt
    if 50 <= f < 92:
        p['tors'] += 2.0 * math.sin(ritmo * 0.5)
    a.occhi = 's'
    a.bocca = 'g' if 48 <= f < 96 else 'c'
    a.fusione = 0.06
    return p


# ============================================================ funzione principale
def anima(l, tempo: float, avv=None) -> Anim:
    """Posa e dati di contorno del lottatore `l` al tempo `tempo` (secondi)."""
    fase = 1.3 * l.indice + (0.9 if l.palette_alternativa else 0.0)
    ritmo = 0.9 + 0.2 * l.personaggio.velocita
    st = l.stato
    a = Anim(GUARDIA)
    affanno = 1.0 if (l.affannato and st in ('guardia', 'cammina', 'parata')) else 0.0
    if st == 'guardia':
        a.posa = _guardia(l, tempo, fase, 1.0, ritmo)
    elif st == 'cammina':
        a.posa = _cammina(l, tempo, fase, ritmo)
    elif st == 'parata':
        a.posa = _parata(l, tempo, fase)
        a.occhi, a.bocca = 's', 'd'
    elif st == 'attacco':
        a.posa = _attacco(l, a)
        a.bers = bersaglio_mossa(l, avv)
    elif st == 'colpito':
        a.posa = _reazione(l, a, tempo, fase)
    elif st == 'bloccato':
        a.posa = _bloccato(l, a, tempo, fase)
    elif st == 'schivata':
        a.posa = _schivata(l, a, tempo, fase)
    elif st == 'guardia_rotta':
        a.posa = _rotta(l, a, tempo, fase)
    elif st == 'atterrato':
        a.posa = _atterrato(l, a, tempo, fase)
    elif st == 'rialzo':
        a.posa = _rialzo(l, a, tempo, fase)
    elif st == 'ko':
        a.posa = _ko(l, a, tempo, fase)
    elif st == 'vittoria':
        a.posa = _vittoria(l, a, tempo, fase)
    elif st == 'sconfitta':
        a.posa = _sconfitta(l, a, tempo, fase)
    elif st == 'intro':
        a.posa = _intro(l, a, tempo, fase)
    else:
        a.posa = _guardia(l, tempo, fase, 1.0, ritmo)
    if affanno:
        _affanno(a.posa, tempo, affanno, fase)
        a.bocca = 'a'
        a.sudore = 1.0
    a.resp = math.sin(2.0 * math.pi * (0.85 if (affanno or st == 'sconfitta') else 0.33) * tempo + fase)
    if affanno or st in ('sconfitta', 'ko', 'atterrato', 'rialzo'):
        a.resp *= 1.5
    a.chiave = (st, l.mossa, l.tipo_schivata if st == 'schivata' else None)
    return a
