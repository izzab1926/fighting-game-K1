"""Audio procedurale di KICKBOXING K1.

Tutti i suoni sono sintetizzati a runtime (nessun asset): impatti con corpo,
fruscii d'aria, campana del ring con parziali inarmoniche, folla, musica in
loop. La sintesi e' in puro Python (modulo `array`), a 22050 Hz mono; i buffer
vengono poi adattati al formato del mixer (frequenza, canali, bit).

Tempi: gli effetti (parte sincrona) si generano in ~1 s; folla e musica in un
thread di sfondo. Il risultato e' salvato in `~/.cache/kickboxing_k1/` (chiave =
versione + CRC di questo file) cosi' dalla seconda esecuzione l'avvio e' quasi
istantaneo. Se il mixer non parte, ogni chiamata e' un no-op silenzioso.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import threading
import time
import zlib
from array import array
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pygame

from . import eventi as ev

try:  # larghezza del ring per il panning stereo
    from .costanti import RING_LARGHEZZA as _RING_L
except Exception:  # pragma: no cover - fondazione assente
    _RING_L = 1800

# ---- costanti

VERSIONE_AUDIO = 1
FREQ_SINTESI = 22050
_SR = FREQ_SINTESI
_DUE_PI = 2.0 * math.pi

VOLUME_SFX = 0.8
VOLUME_MUSICA = 0.42
VOLUME_FOLLA_MAX = 0.55
NUM_CANALI = 24
CANALE_MUSICA_A = 0
CANALE_MUSICA_B = 1
CANALE_FOLLA = 2
CANALI_RISERVATI = 3

NOMI_SFX = (
    'whoosh_leggero', 'whoosh_pesante', 'impatto_pugno', 'impatto_calcio',
    'impatto_contro', 'parata', 'schivata', 'guardia_rotta', 'atterramento',
    'ko', 'campana', 'campana_tripla', 'conteggio', 'super_pronto',
    'ui_muovi', 'ui_conferma', 'ui_indietro', 'passo',
)
NOMI_FOLLA = ('folla', 'boato')
TRACCE = ('menu', 'combattimento')

# rapporti di pitch per le varianti (una scelta casuale, mai la stessa due volte di fila)
_VARIANTI: Dict[str, Tuple[float, ...]] = {
    'whoosh_leggero': (0.92, 1.0, 1.09),
    'whoosh_pesante': (0.93, 1.0, 1.08),
    'impatto_pugno': (0.9, 1.0, 1.1),
    'impatto_calcio': (0.9, 1.0, 1.1),
    'impatto_contro': (0.94, 1.0, 1.07),
    'parata': (0.9, 1.0, 1.12),
    'schivata': (0.93, 1.0, 1.08),
    'atterramento': (0.92, 1.0, 1.06),
    'passo': (0.82, 0.92, 1.0, 1.1),
    'ui_muovi': (0.97, 1.0, 1.03),
}

_WHOOSH_MOSSA = {  # mossa -> (nome, volume)
    'jab': ('whoosh_leggero', 0.5),
    'diretto': ('whoosh_leggero', 0.75),
    'gancio': ('whoosh_pesante', 0.7),
    'calcio_basso': ('whoosh_pesante', 0.7),
    'ginocchiata': ('whoosh_leggero', 0.85),
    'calcio_alto': ('whoosh_pesante', 0.9),
    'calcio_girato': ('whoosh_pesante', 1.0),
}
_MOSSE_CALCIO = ('calcio_basso', 'ginocchiata', 'calcio_alto', 'calcio_girato')


# ---- utilita' DSP (liste di float in [-1, 1], 22050 Hz)

def _n(secondi: float) -> int:
    return max(1, int(secondi * _SR))


def _rumore(n: int, rng: random.Random) -> List[float]:
    r = rng.random
    return [r() * 2.0 - 1.0 for _ in range(n)]


def _passabasso(x: Sequence[float], fc: float) -> List[float]:
    """Filtro a un polo (6 dB/ott)."""
    a = 1.0 - math.exp(-_DUE_PI * fc / _SR)
    y = 0.0
    out: List[float] = []
    ap = out.append
    for s in x:
        y += a * (s - y)
        ap(y)
    return out


def _passaalto(x: Sequence[float], fc: float) -> List[float]:
    return [s - l for s, l in zip(x, _passabasso(x, fc))]


def _biquad(x: Sequence[float], b0: float, b1: float, b2: float,
            a1: float, a2: float) -> List[float]:
    x1 = x2 = y1 = y2 = 0.0
    out: List[float] = []
    ap = out.append
    for s in x:
        y = b0 * s + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1
        x1 = s
        y2 = y1
        y1 = y
        ap(y)
    return out


def _banda(x: Sequence[float], f: float, q: float) -> List[float]:
    """Passabanda risonante (RBJ, guadagno di picco unitario)."""
    f = min(f, _SR * 0.45)
    w0 = _DUE_PI * f / _SR
    al = math.sin(w0) / (2.0 * q)
    a0 = 1.0 + al
    return _biquad(x, al / a0, 0.0, -al / a0, -2.0 * math.cos(w0) / a0, (1.0 - al) / a0)


def _passabasso_q(x: Sequence[float], f: float, q: float = 0.707) -> List[float]:
    """Passabasso a 12 dB/ott con risonanza."""
    f = min(f, _SR * 0.45)
    w0 = _DUE_PI * f / _SR
    al = math.sin(w0) / (2.0 * q)
    c = math.cos(w0)
    a0 = 1.0 + al
    b = (1.0 - c) / 2.0 / a0
    return _biquad(x, b, 2.0 * b, b, -2.0 * c / a0, (1.0 - al) / a0)


def _svf_banda(x: Sequence[float], freqs: Sequence[float], smorz: float) -> List[float]:
    """Passabanda a frequenza variabile nel tempo (per i fruscii)."""
    k = _DUE_PI / _SR
    gs = [2.0 * math.sin(min(f, _SR * 0.4) * k * 0.5) for f in freqs]
    low = band = 0.0
    out: List[float] = []
    ap = out.append
    for s, g in zip(x, gs):
        low += g * band
        high = s - low - smorz * band
        band += g * high
        ap(band)
    return out


def _decad(n: int, tau: float) -> List[float]:
    """Decadimento esponenziale con costante di tempo `tau` secondi."""
    r = math.exp(-1.0 / (tau * _SR))
    e = 1.0
    out: List[float] = []
    ap = out.append
    for _ in range(n):
        ap(e)
        e *= r
    return out


def _bump(n: int, picco: float = 0.35, asim: float = 1.0) -> List[float]:
    """Campana liscia 0..1..0 con il picco a `picco` (frazione della durata)."""
    out: List[float] = []
    sin = math.sin
    pi = math.pi
    for i in range(n):
        t = i / n
        if t < picco:
            u = t / picco
        else:
            u = ((1.0 - t) / (1.0 - picco)) ** asim
        out.append(sin(u * pi * 0.5) ** 2 if t < picco else u * u * (3 - 2 * u))
    return out


def _mul(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [p * q for p, q in zip(a, b)]


def _scala(a: Sequence[float], g: float) -> List[float]:
    return [p * g for p in a]


def _sat(x: Sequence[float], drive: float) -> List[float]:
    th = math.tanh
    return [th(s * drive) for s in x]


def _sweep_sin(n: int, f_ini: float, f_fin: float, tau: float, fase: float = 0.0) -> List[float]:
    """Sinusoide con glissato esponenziale f_ini -> f_fin."""
    k = math.exp(-1.0 / (tau * _SR))
    d = f_ini - f_fin
    c = _DUE_PI / _SR
    ph = fase
    sin = math.sin
    out: List[float] = []
    ap = out.append
    for _ in range(n):
        ap(sin(ph))
        ph += (f_fin + d) * c
        d *= k
    return out


def _seno(n: int, f: float, fase: float = 0.0) -> List[float]:
    w = _DUE_PI * f / _SR
    sin = math.sin
    return [sin(w * i + fase) for i in range(n)]


def _sega(n: int, f: float, fase: float = 0.0) -> List[float]:
    inc = f / _SR
    return [2.0 * ((fase + inc * i) % 1.0) - 1.0 for i in range(n)]


def _quadra(n: int, f: float, duty: float = 0.5) -> List[float]:
    inc = f / _SR
    ph = 0.0
    out: List[float] = []
    ap = out.append
    for _ in range(n):
        ap(1.0 if ph < duty else -1.0)
        ph += inc
        if ph >= 1.0:
            ph -= 1.0
    return out


def _ar(n: int, att: int, rel: int) -> List[float]:
    """Inviluppo lineare: attacco e rilascio di `att`/`rel` campioni, sostegno a 1."""
    att = max(0, min(att, n))
    rel = max(0, min(rel, n - att))
    return ([i / att for i in range(att)] + [1.0] * (n - att - rel)
            + [(rel - i) / rel for i in range(rel)])


def _somma(n: int, strati: Sequence[Tuple[Sequence[float], float, int]]) -> List[float]:
    """Somma strati (campioni, guadagno, ritardo in campioni) in un buffer di n campioni."""
    buf = [0.0] * n
    for x, g, off in strati:
        if off >= n:
            continue
        m = min(len(x), n - off)
        buf[off:off + m] = [b + g * v for b, v in zip(buf[off:off + m], x)]
    return buf


def _rms(x: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in x) / len(x)) if len(x) else 0.0


def _unitario(x: Sequence[float]) -> List[float]:
    """Scala a RMS unitario (per bilanciare strati con larghezza di banda diversa)."""
    r = _rms(x) or 1.0
    return [v / r for v in x]


def _picco(x: Sequence[float]) -> float:
    return max(max(x), -min(x)) if len(x) else 0.0


def _int16(x: Sequence[float], picco: float, fade_ms: float = 4.0) -> array:
    """Normalizza a `picco` (0..1) con dissolvenza finale e converte in int16."""
    p = _picco(x) or 1.0
    k = picco * 32767.0 / p
    nf = min(len(x), int(fade_ms * 0.001 * _SR))
    out = [int(s * k) for s in x]
    for i in range(nf):
        out[len(out) - 1 - i] = int(out[len(out) - 1 - i] * (i / nf))
    return array('h', out)


def _ripassa(x: Sequence[float], rapporto: float) -> array:
    """Cambia il pitch (e la durata) di un buffer int16 per interpolazione lineare."""
    n = len(x)
    if abs(rapporto - 1.0) < 1e-6 or n < 2:
        return array('h', x)
    n2 = int((n - 1) / rapporto)
    out: List[int] = []
    ap = out.append
    for i in range(n2):
        p = i * rapporto
        j = int(p)
        a = x[j]
        ap(int(a + (x[j + 1] - a) * (p - j)))
    return array('h', out)


# ---- effetti: gli impatti

def _transiente(n: int, rng: random.Random, fc: float, tau: float) -> List[float]:
    """Click secco: rumore passaalto con decadimento rapidissimo."""
    return _mul(_passaalto(_rumore(n, rng), fc), _decad(n, tau))


def _fx_impatto_pugno(rng: random.Random) -> array:
    n = _n(0.26)
    ru = _rumore(n, rng)
    schiaffo = _mul(_banda(ru, 1500.0, 0.9), _decad(n, 0.02))
    cuoio = _mul(_banda(ru, 3200.0, 2.0), _decad(n, 0.008))
    corpo = _sat(_mul(_sweep_sin(n, 190.0, 80.0, 0.018), _decad(n, 0.05)), 1.6)
    pancia = _mul(_passabasso(ru, 500.0), _decad(n, 0.035))
    click = _transiente(n, rng, 2500.0, 0.0011)
    x = _somma(n, [(schiaffo, 1.3, 0), (cuoio, 0.8, 0), (corpo, 0.55, 0),
                   (pancia, 0.7, 0), (click, 0.9, 0)])
    return _int16(_sat(x, 1.1), 0.9)


def _fx_impatto_calcio(rng: random.Random) -> array:
    n = _n(0.5)
    ru = _rumore(n, rng)
    schiaffo = _mul(_passabasso(_banda(ru, 900.0, 0.7), 2400.0), _decad(n, 0.045))
    carne = _mul(_banda(ru, 260.0, 1.0), _decad(n, 0.075))
    corpo = _sat(_mul(_sweep_sin(n, 125.0, 52.0, 0.05), _decad(n, 0.13)), 1.7)
    coda = _mul(_sweep_sin(n, 62.0, 48.0, 0.2), _decad(n, 0.22))
    click = _transiente(n, rng, 1800.0, 0.0016)
    x = _somma(n, [(schiaffo, 1.1, 0), (carne, 1.2, 0), (corpo, 1.0, 0),
                   (coda, 0.35, 0), (click, 0.6, 0)])
    return _int16(_sat(x, 1.1), 0.92)


def _fx_impatto_contro(rng: random.Random) -> array:
    """Colpo d'incontro: piu' secco e brillante, con 'crack' risonante e rimbalzo."""
    n = _n(0.6)
    ru = _rumore(n, rng)
    crack = _mul(_passaalto(ru, 2200.0), _decad(n, 0.02))
    tock = _mul(_banda(ru, 2300.0, 14.0), _decad(n, 0.055))
    schiaffo = _mul(_banda(ru, 1200.0, 0.8), _decad(n, 0.035))
    corpo = _sat(_mul(_sweep_sin(n, 170.0, 62.0, 0.025), _decad(n, 0.09)), 1.6)
    boom = _mul(_sweep_sin(n, 66.0, 48.0, 0.15), _decad(n, 0.22))
    click = _transiente(n, rng, 3500.0, 0.0009)
    x = _somma(n, [(crack, 1.2, 0), (tock, 1.3, 0), (schiaffo, 0.9, 0), (corpo, 1.0, 0),
                   (boom, 0.45, 0), (click, 1.0, 0)])
    x = _sat(x, 1.2)
    # eco di rimbalzo dell'arena
    x = _somma(n, [(x, 1.0, 0), (x, 0.22, _n(0.038)), (x, 0.1, _n(0.083))])
    return _int16(_sat(x, 1.0), 0.95)


def _fx_parata(rng: random.Random) -> array:
    n = _n(0.26)
    ru = _rumore(n, rng)
    tonfo = _mul(_passabasso(_banda(ru, 500.0, 0.6), 900.0), _decad(n, 0.035))
    corpo = _mul(_sweep_sin(n, 125.0, 78.0, 0.03), _decad(n, 0.06))
    cuoio = _mul(_banda(ru, 1300.0, 1.5), _decad(n, 0.014))
    x = _somma(n, [(tonfo, 1.5, 0), (corpo, 1.3, 0), (cuoio, 0.5, 0)])
    return _int16(_sat(x, 1.2), 0.75)


def _fx_whoosh(rng: random.Random, pesante: bool) -> array:
    dur = 0.36 if pesante else 0.2
    n = _n(dur)
    ru = _rumore(n, rng)
    if pesante:
        f = [260.0 + 1300.0 * math.sin(math.pi * (i / n) ** 0.8) for i in range(n)]
        f2 = [900.0 + 2600.0 * math.sin(math.pi * (i / n) ** 0.9) for i in range(n)]
        env = _bump(n, 0.45, 1.3)
        a = _mul(_svf_banda(ru, f, 0.55), env)
        b = _mul(_svf_banda(ru, f2, 0.9), env)
        rombo = _mul(_passabasso(ru, 180.0), env)
        x = _somma(n, [(a, 1.0, 0), (b, 0.55, 0), (rombo, 0.9, 0)])
    else:
        f = [900.0 + 3400.0 * math.sin(math.pi * (i / n) ** 0.85) for i in range(n)]
        env = _bump(n, 0.4, 1.2)
        a = _mul(_svf_banda(ru, f, 0.5), env)
        x = _somma(n, [(a, 1.0, 0), (_mul(_passaalto(ru, 5000.0), env), 0.12, 0)])
    return _int16(x, 0.6 if pesante else 0.5, fade_ms=8.0)


def _fx_schivata(rng: random.Random) -> array:
    n = _n(0.3)
    ru = _rumore(n, rng)
    f = [4600.0 - 3300.0 * (i / n) ** 0.6 + 700.0 * math.sin(math.pi * i / n) for i in range(n)]
    env = _bump(n, 0.25, 1.1)
    a = _mul(_svf_banda(ru, f, 0.4), env)
    scatto = _mul(_banda(ru, 1900.0, 1.6), _decad(n, 0.03))
    tonfo = _mul(_sweep_sin(n, 130.0, 90.0, 0.04), _decad(n, 0.05))
    x = _somma(n, [(a, 1.0, 0), (scatto, 0.35, _n(0.09)), (tonfo, 0.25, _n(0.09))])
    return _int16(x, 0.42, fade_ms=10.0)


def _fx_guardia_rotta(rng: random.Random) -> array:
    n = _n(0.85)
    ru = _rumore(n, rng)
    crack = _mul(_passaalto(ru, 2000.0), _decad(n, 0.03))
    tock = _mul(_banda(ru, 2600.0, 10.0), _decad(n, 0.07))
    corpo = _mul(_sweep_sin(n, 140.0, 55.0, 0.04), _decad(n, 0.18))
    # cedimento: tono discendente sporco
    glide = _sat(_sweep_sin(n, 1150.0, 170.0, 0.09), 3.0)
    glide = _mul(_passabasso(glide, 2600.0), _decad(n, 0.16))
    # sonaglio: rumore modulato che si spegne
    mod = [0.55 + 0.45 * (1.0 if math.sin(_DUE_PI * 38.0 * i / _SR) > 0 else -0.2) for i in range(n)]
    sonaglio = _mul(_mul(_banda(ru, 2300.0, 2.5), mod), _decad(n, 0.16))
    x = _somma(n, [(crack, 1.1, 0), (tock, 1.4, 0), (corpo, 1.0, 0),
                   (glide, 0.6, _n(0.02)), (sonaglio, 0.8, _n(0.03))])
    return _int16(_sat(x, 1.0), 0.9)


def _fx_atterramento(rng: random.Random) -> array:
    n = _n(0.75)
    ru = _rumore(n, rng)
    thump = _sat(_mul(_sweep_sin(n, 95.0, 46.0, 0.06), _decad(n, 0.14)), 1.5)
    fwump = _mul(_passabasso(ru, 380.0), _decad(n, 0.08))
    rimbalzo = _mul(_sweep_sin(n, 70.0, 38.0, 0.05), _decad(n, 0.12))
    fruscio = _mul(_banda(ru, 1500.0, 0.7), _decad(n, 0.16))
    x = _somma(n, [(thump, 1.0, 0), (fwump, 1.2, 0), (rimbalzo, 0.4, _n(0.16)),
                   (fruscio, 0.33, _n(0.025)), (_transiente(n, rng, 1200.0, 0.004), 0.6, 0)])
    return _int16(_sat(x, 1.0), 0.88)


def _fx_ko(rng: random.Random) -> array:
    n = _n(1.9)
    ru = _rumore(n, rng)
    boom = _mul(_sweep_sin(n, 90.0, 29.0, 0.35), _decad(n, 0.5))
    sub = _mul(_seno(n, 38.0), _decad(n, 0.55))
    rombo = _mul(_passabasso(ru, 210.0), _decad(n, 0.45))
    riverbero = _mul(_passabasso(ru, 520.0), _decad(n, 0.85))
    riverbero = _mul(riverbero, [0.5 + 0.5 * math.sin(_DUE_PI * 4.5 * i / _SR + 1.0) for i in range(n)])
    crack = _mul(_passaalto(ru, 1800.0), _decad(n, 0.03))
    corpo = _mul(_sweep_sin(n, 170.0, 60.0, 0.04), _decad(n, 0.14))
    boom = _sat(boom, 1.4)
    x = _somma(n, [(boom, 1.1, 0), (sub, 0.5, _n(0.02)), (rombo, 0.9, 0),
                   (riverbero, 0.45, _n(0.03)), (crack, 0.7, 0), (corpo, 0.9, 0)])
    x = _sat(x, 1.0)
    return _int16(x, 0.95, fade_ms=30.0)


# ---- effetti: campana, arbitro, folla, UI

_PARZIALI_CAMPANA = (
    # (rapporto, ampiezza, tau) - profilo di campana: ronzio, primo, terza minore, quinta, nominale...
    (0.5, 0.30, 1.5), (1.0, 0.85, 1.25), (1.003, 0.55, 1.1), (1.19, 0.6, 1.0),
    (1.5, 0.32, 0.8), (2.0, 0.62, 0.7), (2.006, 0.3, 0.65), (2.5, 0.28, 0.5),
    (2.98, 0.3, 0.42), (4.1, 0.2, 0.28), (5.43, 0.11, 0.18),
)


def _fx_campana(rng: random.Random) -> array:
    n = _n(2.6)
    f0 = 540.0
    strati = []
    for rapp, amp, tau in _PARZIALI_CAMPANA:
        w = _DUE_PI * f0 * rapp / _SR
        r = math.exp(-1.0 / (tau * _SR))
        c1 = 2.0 * r * math.cos(w)
        c2 = -r * r
        m = min(n, int(tau * 7.0 * _SR))  # oltre 7 tau e' inudibile
        y2 = 0.0
        y1 = amp * r * math.sin(w)
        x = [0.0, y1]
        ap = x.append
        for _ in range(m - 2):
            y = c1 * y1 + c2 * y2
            ap(y)
            y2 = y1
            y1 = y
        strati.append((x, 1.0, 0))
    battente = _mul(_banda(_rumore(n, rng), 3400.0, 3.0), _decad(n, 0.012))
    tonfo = _mul(_banda(_rumore(n, rng), 900.0, 2.0), _decad(n, 0.02))
    strati += [(battente, 0.9, 0), (tonfo, 0.6, 0)]
    x = _somma(n, strati)
    x = [s * min(1.0, i / 24.0) for i, s in enumerate(x)]  # attacco di 1 ms: niente click
    return _int16(x, 0.85, fade_ms=40.0)


def _campana_tripla(singola: array) -> array:
    n = int(_SR * 3.5)
    x = _somma(n, [(singola, 0.8, 0), (singola, 0.8, int(_SR * 0.55)), (singola, 0.9, int(_SR * 1.1))])
    return _int16(x, 0.88, fade_ms=40.0)


def _fx_conteggio(rng: random.Random) -> array:
    """Voce dell'arbitro stilizzata: 'uáh' con formanti, sopra un colpo secco."""
    n = _n(0.5)
    # sorgente glottica: sega con glissato discendente e vibrato leggero
    inc0 = 128.0 / _SR
    ph = 0.0
    src = []
    ap = src.append
    for i in range(n):
        t = i / n
        f = 128.0 * (1.12 - 0.22 * t) * (1.0 + 0.012 * math.sin(_DUE_PI * 5.5 * i / _SR))
        ph += f / _SR
        if ph >= 1.0:
            ph -= 1.0
        ap(2.0 * ph - 1.0)
    f1 = _banda(src, 600.0, 4.0)
    f2 = _banda(src, 1050.0, 5.0)
    f3 = _banda(src, 2500.0, 6.0)
    voce = _somma(n, [(f1, 1.0, 0), (f2, 0.8, 0), (f3, 0.25, 0)])
    env = [min(1.0, i / (0.02 * _SR)) * math.exp(-max(0, i - 0.15 * _SR) / (0.11 * _SR)) for i in range(n)]
    voce = _mul(voce, env)
    consonante = _mul(_banda(_rumore(n, rng), 3200.0, 1.5), _decad(n, 0.012))
    colpo = _mul(_sweep_sin(n, 110.0, 60.0, 0.03), _decad(n, 0.08))
    x = _somma(n, [(voce, 1.0, 0), (consonante, 0.9, 0), (colpo, 0.7, 0)])
    return _int16(_sat(x, 1.2), 0.8, fade_ms=15.0)


def _fx_super_pronto(rng: random.Random) -> array:
    n = _n(1.05)
    strati = []
    note = (440.0, 554.37, 659.25, 880.0, 1108.7)
    for k, f in enumerate(note):
        off = int(_SR * 0.06 * k)
        m = n - off
        tono = _somma(m, [(_seno(m, f), 1.0, 0), (_seno(m, f * 2.005), 0.35, 0),
                          (_seno(m, f * 3.01), 0.12, 0)])
        strati.append((_mul(tono, _decad(m, 0.28 + 0.03 * k)), 0.55, off))
    riser = _svf_banda(_rumore(n, rng), [500.0 + 5500.0 * (i / n) ** 1.6 for i in range(n)], 0.35)
    riser = _mul(riser, _bump(n, 0.4, 1.0))
    sub = _mul(_sweep_sin(n, 60.0, 110.0, 0.2), _bump(n, 0.25, 1.0))
    strati += [(riser, 0.6, 0), (sub, 0.8, 0)]
    return _int16(_somma(n, strati), 0.7, fade_ms=20.0)


def _pizzico(n: int, f: float, tau: float, ricchezza: float = 1.0) -> List[float]:
    """Nota pizzicata FM morbida (per i suoni UI)."""
    w = _DUE_PI * f / _SR
    r = math.exp(-1.0 / (tau * _SR))
    rm = math.exp(-1.0 / (tau * 0.4 * _SR))
    sin = math.sin
    e = em = 1.0
    out = []
    ap = out.append
    for i in range(n):
        ap(sin(w * i + ricchezza * 1.6 * em * sin(w * 2.0 * i)) * e)
        e *= r
        em *= rm
    return out


def _fx_ui_muovi(rng: random.Random) -> array:
    n = _n(0.09)
    x = _somma(n, [(_pizzico(n, 1180.0, 0.02, 0.5), 1.0, 0),
                   (_transiente(n, rng, 3000.0, 0.0015), 0.3, 0)])
    return _int16(x, 0.42, fade_ms=8.0)


def _fx_ui_conferma(rng: random.Random) -> array:
    n = _n(0.3)
    a = _pizzico(n, 660.0, 0.07, 0.8)
    b = _pizzico(n - _n(0.07), 990.0, 0.1, 0.8)
    x = _somma(n, [(a, 0.8, 0), (b, 1.0, _n(0.07)), (_transiente(n, rng, 2500.0, 0.002), 0.2, 0)])
    return _int16(x, 0.55, fade_ms=15.0)


def _fx_ui_indietro(rng: random.Random) -> array:
    n = _n(0.22)
    a = _pizzico(n, 620.0, 0.05, 0.6)
    b = _pizzico(n - _n(0.06), 415.0, 0.07, 0.6)
    x = _somma(n, [(a, 0.8, 0), (b, 1.0, _n(0.06))])
    return _int16(x, 0.48, fade_ms=12.0)


def _fx_passo(rng: random.Random) -> array:
    n = _n(0.12)
    ru = _rumore(n, rng)
    x = _somma(n, [(_mul(_passabasso(ru, 320.0), _decad(n, 0.022)), 1.6, 0),
                   (_mul(_sweep_sin(n, 95.0, 55.0, 0.02), _decad(n, 0.04)), 1.2, 0),
                   (_mul(_banda(ru, 1400.0, 1.0), _decad(n, 0.01)), 0.3, 0)])
    return _int16(x, 0.5, fade_ms=6.0)


def genera_sfx(seme: int = 7) -> Dict[str, array]:
    """Genera tutti gli effetti (int16 mono a 22050 Hz). Parte sincrona di ~1 s."""
    rng = random.Random(seme)
    out: Dict[str, array] = {}
    out['impatto_pugno'] = _fx_impatto_pugno(rng)
    out['impatto_calcio'] = _fx_impatto_calcio(rng)
    out['impatto_contro'] = _fx_impatto_contro(rng)
    out['parata'] = _fx_parata(rng)
    out['whoosh_leggero'] = _fx_whoosh(rng, False)
    out['whoosh_pesante'] = _fx_whoosh(rng, True)
    out['schivata'] = _fx_schivata(rng)
    out['guardia_rotta'] = _fx_guardia_rotta(rng)
    out['atterramento'] = _fx_atterramento(rng)
    out['ko'] = _fx_ko(rng)
    out['campana'] = _fx_campana(rng)
    out['campana_tripla'] = _campana_tripla(out['campana'])
    out['conteggio'] = _fx_conteggio(rng)
    out['super_pronto'] = _fx_super_pronto(rng)
    out['ui_muovi'] = _fx_ui_muovi(rng)
    out['ui_conferma'] = _fx_ui_conferma(rng)
    out['ui_indietro'] = _fx_ui_indietro(rng)
    out['passo'] = _fx_passo(rng)
    return out


# ---- folla

def _ciclo(x: Sequence[float], n: int, sovrapposizione: int) -> List[float]:
    """Rende un buffer di n+sovrapposizione campioni ciclico (crossfade coda->testa)."""
    out = list(x[:n])
    for i in range(sovrapposizione):
        w = i / sovrapposizione
        out[i] = x[i] * w + x[n + i] * (1.0 - w)
    return out


def _fx_folla(rng: random.Random) -> array:
    """Brusio del pubblico in loop (4 s)."""
    n = _n(4.0)
    ov = _n(0.6)
    m = n + ov
    a = _banda(_rumore(m, rng), 430.0, 0.7)
    b = _banda(_rumore(m, rng), 1050.0, 0.9)
    c = _passabasso(_passaalto(_rumore(m, rng), 1800.0), 4200.0)
    lento = _passabasso(_rumore(m, rng), 1.6)
    pk = _picco(lento) or 1.0
    mod = [0.68 + 0.32 * s / pk for s in lento]
    x = _somma(m, [(_mul(_unitario(a), mod), 1.0, 0), (_unitario(b), 0.55, 0), (_unitario(c), 0.07, 0)])
    # urla isolate (formanti): "ohh", "vaii"
    for _ in range(9):
        durata = _n(rng.uniform(0.18, 0.4))
        pos = rng.randrange(0, m - durata)
        f0 = rng.uniform(250.0, 520.0)
        src = _sega(durata, f0)
        voce = _somma(durata, [(_banda(src, 700.0 + rng.uniform(-120, 150), 3.0), 1.0, 0),
                               (_banda(src, 1300.0 + rng.uniform(-200, 250), 4.0), 0.5, 0)])
        voce = _mul(_unitario(voce), _bump(durata, 0.35, 1.0))
        x[pos:pos + durata] = [p + 0.7 * q for p, q in zip(x[pos:pos + durata], voce)]
    return _int16(_ciclo(x, n, ov), 0.6, fade_ms=0.0)


def _fx_boato(rng: random.Random) -> array:
    """Boato/ovazione della folla con applausi (2.4 s)."""
    n = _n(2.4)
    ru = _rumore(n, rng)
    env = [min(1.0, (i / (0.32 * _SR))) ** 1.5 * math.exp(-max(0, i - 0.5 * _SR) / (0.75 * _SR)) for i in range(n)]
    soffio = _somma(n, [(_unitario(_banda(ru, 700.0, 0.8)), 1.0, 0), (_unitario(_banda(ru, 1500.0, 1.0)), 0.5, 0)])
    voci = []
    for k in range(5):
        f0 = 170.0 + 38.0 * k
        vib = math.pi * 2 * (4.5 + 0.7 * k) / _SR
        ph = rng.random()
        v = []
        for i in range(n):
            ph += f0 * (1.0 + 0.02 * math.sin(vib * i + k)) * (1.0 + 0.15 * i / n) / _SR
            ph -= int(ph)
            v.append(2.0 * ph - 1.0)
        voci.append((v, 0.35, 0))
    voce = _passabasso_q(_somma(n, voci), 1400.0, 0.9)
    voce = _unitario(_banda(voce, 900.0, 0.5))
    applausi = [0.0] * n
    clic = _mul(_unitario(_banda(_rumore(_n(0.03), rng), 2600.0, 1.2)), _decad(_n(0.03), 0.004))
    ln = len(clic)
    for _ in range(170):
        pos = int(rng.random() ** 0.8 * (n - ln))
        if rng.random() < env[pos] * 1.1 + 0.05:
            g = rng.uniform(0.3, 1.0)
            applausi[pos:pos + ln] = [p + g * q for p, q in zip(applausi[pos:pos + ln], clic)]
    x = _somma(n, [(_mul(soffio, env), 1.0, 0), (_mul(voce, env), 0.8, 0), (applausi, 0.5, 0)])
    return _int16(x, 0.85, fade_ms=120.0)


def genera_folla(seme: int = 11) -> Dict[str, array]:
    rng = random.Random(seme)
    return {'folla': _fx_folla(rng), 'boato': _fx_boato(rng)}


# ---- musica

def _midi(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def _eco(x: List[float], ritardo: int, retroazione: float) -> List[float]:
    """Delay circolare (il loop resta continuo), a blocchi di `ritardo` campioni."""
    n = len(x)
    y = x + x
    for i in range(ritardo, 2 * n, ritardo):
        fine = min(i + ritardo, 2 * n)
        y[i:fine] = [a + retroazione * b for a, b in zip(y[i:fine], y[i - ritardo:fine - ritardo])]
    return y[n:]


class _Traccia:
    """Buffer di loop su cui si sommano i colpi (con avvolgimento circolare)."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.buf = [0.0] * n

    def aggiungi(self, x: Sequence[float], off: int, g: float = 1.0) -> None:
        n = self.n
        off %= n
        m = len(x)
        fine = off + m
        buf = self.buf
        if fine <= n:
            buf[off:fine] = [b + g * v for b, v in zip(buf[off:fine], x)]
        else:
            k = n - off
            buf[off:] = [b + g * v for b, v in zip(buf[off:], x[:k])]
            resto = min(m - k, n)
            buf[:resto] = [b + g * v for b, v in zip(buf[:resto], x[k:k + resto])]


class _Strumenti:
    """Suoni singoli riusati dalle tracce (renderizzati una volta)."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self._cache: Dict[tuple, List[float]] = {}

    def memo(self, chiave: tuple, fabbrica: Callable[[], List[float]]) -> List[float]:
        v = self._cache.get(chiave)
        if v is None:
            v = fabbrica()
            self._cache[chiave] = v
        return v

    def cassa(self, morbida: bool = False) -> List[float]:
        def f() -> List[float]:
            n = _n(0.34)
            corpo = _mul(_sweep_sin(n, 130.0 if morbida else 175.0, 46.0, 0.03), _decad(n, 0.14 if morbida else 0.17))
            click = _transiente(n, self.rng, 2800.0, 0.002)
            return _sat(_somma(n, [(corpo, 1.3, 0), (click, 0.0 if morbida else 0.35, 0)]), 1.6)
        return self.memo(('cassa', morbida), f)

    def rullante(self, morbido: bool = False) -> List[float]:
        def f() -> List[float]:
            n = _n(0.3)
            ru = _rumore(n, self.rng)
            fruscio = _mul(_passaalto(_banda(ru, 2400.0, 0.5), 900.0), _decad(n, 0.075 if morbido else 0.11))
            tono = _mul(_sweep_sin(n, 240.0, 175.0, 0.02), _decad(n, 0.06))
            coda = _mul(_passabasso(ru, 3000.0), _decad(n, 0.22))
            return _sat(_somma(n, [(fruscio, 1.1, 0), (tono, 0.9, 0), (coda, 0.0 if morbido else 0.35, 0)]), 1.3)
        return self.memo(('rullante', morbido), f)

    def hat(self, aperto: bool = False) -> List[float]:
        def f() -> List[float]:
            n = _n(0.26 if aperto else 0.07)
            ru = _passaalto(_rumore(n, self.rng), 6500.0)
            return _mul(ru, _decad(n, 0.075 if aperto else 0.014))
        return self.memo(('hat', aperto), f)

    def rim(self) -> List[float]:
        def f() -> List[float]:
            n = _n(0.09)
            return _somma(n, [(_mul(_banda(_rumore(n, self.rng), 1750.0, 9.0), _decad(n, 0.012)), 1.6, 0),
                              (_mul(_sweep_sin(n, 420.0, 330.0, 0.01), _decad(n, 0.02)), 0.7, 0)])
        return self.memo(('rim',), f)

    def tom(self, f0: float) -> List[float]:
        def f() -> List[float]:
            n = _n(0.55)
            c = _mul(_sweep_sin(n, f0 * 1.7, f0, 0.045), _decad(n, 0.2))
            p = _mul(_banda(_rumore(n, self.rng), f0 * 5.0, 2.0), _decad(n, 0.012))
            return _sat(_somma(n, [(c, 1.5, 0), (p, 0.45, 0)]), 1.4)
        return self.memo(('tom', f0), f)

    def basso(self, midi: float, n: int, aspro: float = 1.0) -> List[float]:
        def f() -> List[float]:
            fr = _midi(midi)
            sega = _sega(n, fr)
            quad = _quadra(n, fr * 1.004, 0.4)
            sub = _seno(n, fr)
            corpo = _somma(n, [(sega, 0.6, 0), (quad, 0.3, 0)])
            corpo = _passabasso_q(corpo, 260.0 + 520.0 * aspro, 1.6)
            x = _somma(n, [(corpo, 1.0, 0), (sub, 0.9, 0)])
            gate = _mul(_decad(n, max(0.05, n / _SR * 0.6)), _ar(n, 60, 200))
            return _sat(_mul(x, gate), 1.2)
        return self.memo(('basso', midi, n, aspro), f)

    def pizzico(self, midi: float, n: int, tau: float, luce: float = 3000.0) -> List[float]:
        def f() -> List[float]:
            fr = _midi(midi)
            x = _somma(n, [(_sega(n, fr), 0.6, 0), (_sega(n, fr * 1.006, 0.3), 0.45, 0),
                           (_quadra(n, fr * 0.5, 0.5), 0.25, 0)])
            x = _passabasso_q(x, luce, 1.2)
            return _mul(x, _mul(_decad(n, tau), _ar(n, 25, 300)))
        return self.memo(('pizz', midi, n, tau, luce), f)

    def accordo(self, midis: Sequence[float], n: int, tau: float, luce: float) -> List[float]:
        def f() -> List[float]:
            strati = []
            for i, m in enumerate(midis):
                fr = _midi(m)
                strati.append((_sega(n, fr, 0.13 * i), 0.5, 0))
                strati.append((_sega(n, fr * 1.008, 0.41 * i), 0.4, 0))
            x = _passabasso_q(_somma(n, strati), luce, 1.0)
            return _mul(x, _mul(_decad(n, tau), _ar(n, 40, 400)))
        return self.memo(('acc', tuple(midis), n, tau, luce), f)

    def pad(self, midis: Sequence[float], n: int) -> List[float]:
        def f() -> List[float]:
            m = n // 2  # renderizzato a meta' frequenza (e' un suono morbido) e poi raddoppiato
            acc = [0.0] * m
            for i, mi in enumerate(midis):
                inc = _midi(mi) / _SR * 2.0
                for det, ph in ((0.997, 0.2 * i), (1.004, 0.55 * i)):
                    k = inc * det
                    acc = [a + 2.0 * ((ph + k * j) % 1.0) - 1.0 for j, a in enumerate(acc)]
            acc = _passabasso_q(acc, 2200.0, 0.8)  # 1100 Hz reali
            x: List[float] = []
            for a, b in zip(acc, acc[1:] + acc[-1:]):
                x.append(a)
                x.append((a + b) * 0.5)
            x = x + [x[-1]] * (n - len(x))
            return _mul(x, _ar(n, int(0.7 * _SR), int(0.9 * _SR)))
        return self.memo(('pad', tuple(midis), n), f)


def _finale_musica(tr: _Traccia, picco: float = 0.8) -> array:
    ordinati = sorted(abs(v) for v in tr.buf[::7])
    p = ordinati[int(len(ordinati) * 0.995)] or 1.0
    x = _sat(tr.buf, 1.1 / p)  # limitatore morbido: il 99,5% dei campioni resta lineare
    return _int16(x, picco, fade_ms=0.0)


def _musica_combattimento(seme: int) -> array:
    """Loop di 8 battute a 138 BPM in La minore: cassa, taiko, basso, arpeggi."""
    rng = random.Random(seme)
    S = _Strumenti(rng)
    passo = int(round(_SR * 15.0 / 138.0))
    n = passo * 16 * 8
    batt = passo * 16
    base = _Traccia(n)     # batteria
    grave = _Traccia(n)    # basso
    sint = _Traccia(n)     # synth (con delay)

    accordi = [(57, 60, 64), (57, 60, 64), (53, 57, 60), (53, 57, 60),
               (55, 60, 64), (55, 60, 64), (55, 59, 62), (55, 59, 62)]
    radici = [33, 33, 29 + 12, 29 + 12, 36, 36, 31 + 12, 31 + 12]
    for b in range(8):
        o = b * batt
        ultima = (b == 7)
        # cassa
        cassa = [0, 4, 8, 12] + ([10] if b % 2 else [7]) if not ultima else [0, 4, 8]
        for s in cassa:
            base.aggiungi(S.cassa(), o + s * passo, 0.95 if s % 4 == 0 else 0.6)
        # rullante e battito di mani
        for s in ([4, 12] if not ultima else [4, 10, 12, 13, 14, 15]):
            v = 1.0 if s in (4, 12) else 0.55 + 0.1 * (s - 10)
            base.aggiungi(S.rullante(), o + s * passo, 0.8 * v)
        # hi-hat
        for s in range(0, 16, 2):
            acc = 0.5 if s % 4 == 2 else 0.28
            if not (ultima and s >= 12):
                base.aggiungi(S.hat(False), o + s * passo, acc)
        if not ultima:
            base.aggiungi(S.hat(True), o + 14 * passo, 0.32)
        if b >= 4 and not ultima:
            for s in (1, 3, 5, 7, 9, 11, 13, 15):
                base.aggiungi(S.hat(False), o + s * passo, 0.12)
        # taiko: colpi larghi sugli inizi di frase
        if b % 2 == 0:
            base.aggiungi(S.tom(78.0), o, 0.85)
            base.aggiungi(S.tom(78.0), o + 8 * passo, 0.55)
        if b % 4 == 3 or ultima:
            for k, (s, f0) in enumerate(((12, 118.0), (13, 104.0), (14, 92.0), (15, 78.0))):
                base.aggiungi(S.tom(f0), o + s * passo, 0.6 + 0.08 * k)
        # basso: 8-ini con salti d'ottava
        r = radici[b]
        schema = [(0, 0, 2), (2, 0, 1), (3, 12, 1), (6, 0, 2), (8, 0, 2), (10, 0, 1),
                  (11, 7, 1), (14, 12, 1)]
        if ultima:
            schema = [(0, 0, 2), (2, 0, 1), (3, 12, 1), (6, 0, 2), (8, 0, 4)]
        for s, iv, lung in schema:
            grave.aggiungi(S.basso(r + iv, lung * passo - 120, 1.0), o + s * passo, 1.0)
        # synth: stab sul levare (barre 1-4), arpeggio a sedicesimi (barre 5-8)
        ch = accordi[b]
        if b < 4:
            for s in (2, 6, 10, 14) if b % 2 == 0 else (3, 6, 11, 14):
                sint.aggiungi(S.accordo([m + 12 for m in ch], passo * 2 - 100, 0.09, 3400.0), o + s * passo, 0.55)
        else:
            ordine = (0, 1, 2, 1, 0, 2, 1, 2)
            for s in range(16):
                m = ch[ordine[s % 8]] + 12 + (12 if (s % 8) == 7 else 0)
                sint.aggiungi(S.pizzico(m, passo * 2 - 80, 0.085, 3800.0), o + s * passo, 0.42 if s % 4 else 0.6)
    # accordo tenuto al culmine (ultime due battute) per sostenere la tensione
    sint.aggiungi(S.pad([57, 60, 64, 69], batt * 2), batt * 6, 0.35)
    sint.buf = _eco(sint.buf, int(passo * 3), 0.42)
    tr = _Traccia(n)
    tr.buf = _somma(n, [(base.buf, 0.5, 0), (grave.buf, 1.0, 0), (sint.buf, 0.75, 0)])
    return _finale_musica(tr)


def _musica_menu(seme: int) -> array:
    """Loop di 8 battute a 84 BPM in Re minore: atmosfera da presentazione, pad e pizzichi."""
    rng = random.Random(seme)
    S = _Strumenti(rng)
    passo = int(round(_SR * 15.0 / 84.0))
    n = passo * 16 * 8
    batt = passo * 16
    base = _Traccia(n)
    grave = _Traccia(n)
    sint = _Traccia(n)
    pad = _Traccia(n)

    accordi = [(62, 65, 69), (58, 62, 65), (55, 58, 62), (57, 61, 64)]
    radici = [38, 34, 31 + 12, 33]
    for b in range(8):
        o = b * batt
        k = b // 2
        base.aggiungi(S.cassa(True), o, 0.8)
        if b % 2:
            base.aggiungi(S.cassa(True), o + 10 * passo, 0.5)
        base.aggiungi(S.rim(), o + 8 * passo, 0.7)
        if b % 4 == 3:
            base.aggiungi(S.rullante(True), o + 15 * passo, 0.35)
        for s in range(0, 16, 2):
            base.aggiungi(S.hat(False), o + s * passo, 0.35 if s % 4 == 2 else 0.2)
        if b % 2 == 1:
            base.aggiungi(S.hat(True), o + 14 * passo, 0.25)
        r = radici[k]
        grave.aggiungi(S.basso(r, 7 * passo, 0.5), o, 1.0)
        grave.aggiungi(S.basso(r, 3 * passo, 0.5), o + 7 * passo, 0.8)
        grave.aggiungi(S.basso(r + 7, 2 * passo, 0.5), o + 10 * passo, 0.7)
        grave.aggiungi(S.basso(r + 12, 3 * passo, 0.5), o + 13 * passo, 0.6)
        ch = accordi[k]
        # pizzichi 'dreamy' in ottava alta, a ottavi
        ordine = (0, 2, 1, 2, 0, 1, 2, 1)
        for i, s in enumerate(range(0, 16, 2)):
            if (b + i) % 4 == 3:
                continue
            sint.aggiungi(S.pizzico(ch[ordine[i]] + 24, passo * 2 - 100, 0.16, 3000.0), o + s * passo, 0.5)
    for k in range(4):
        pad.aggiungi(S.pad([m for m in accordi[k]] + [accordi[k][0] + 12], batt * 2 + passo * 2), k * batt * 2, 0.5)
    sint.buf = _eco(sint.buf, int(passo * 3), 0.5)
    tr = _Traccia(n)
    tr.buf = _somma(n, [(base.buf, 1.3, 0), (grave.buf, 1.0, 0), (sint.buf, 1.2, 0), (pad.buf, 0.3, 0)])
    return _finale_musica(tr)


def genera_musica(traccia: str, seme: int = 3) -> Dict[str, array]:
    if traccia == 'menu':
        return {'menu': _musica_menu(seme)}
    if traccia == 'combattimento':
        return {'combattimento': _musica_combattimento(seme)}
    raise ValueError('traccia sconosciuta: %r' % (traccia,))


# ---- cache su disco

def _chiave_versione() -> str:
    try:
        with open(__file__, 'rb') as f:
            crc = zlib.crc32(f.read()) & 0xFFFFFFFF
    except OSError:
        crc = 0
    return 'v%d_%08x' % (VERSIONE_AUDIO, crc)


def _dir_cache() -> str:
    return os.environ.get('KICKBOXING_K1_CACHE') or os.path.join(
        os.path.expanduser('~'), '.cache', 'kickboxing_k1')


def _percorso_cache(gruppo: str) -> str:
    return os.path.join(_dir_cache(), 'audio_%s_%s.bin' % (_chiave_versione(), gruppo))


def _carica_cache(gruppo: str) -> Optional[Dict[str, array]]:
    try:
        with open(_percorso_cache(gruppo), 'rb') as f:
            testa = f.readline()
            indice = json.loads(testa.decode('utf-8'))
            dati = f.read()
        out: Dict[str, array] = {}
        pos = 0
        for nome, campioni in indice:
            a = array('h')
            a.frombytes(dati[pos:pos + campioni * 2])
            if len(a) != campioni:
                return None
            if sys.byteorder == 'big':
                a.byteswap()
            out[nome] = a
            pos += campioni * 2
        return out if pos == len(dati) else None
    except Exception:
        return None


def _salva_cache(gruppo: str, suoni: Dict[str, array]) -> None:
    try:
        os.makedirs(_dir_cache(), exist_ok=True)
        percorso = _percorso_cache(gruppo)
        tmp = '%s.%d.tmp' % (percorso, os.getpid())
        indice = [[nome, len(a)] for nome, a in suoni.items()]
        with open(tmp, 'wb') as f:
            f.write(json.dumps(indice).encode('utf-8') + b'\n')
            for nome, a in suoni.items():
                if sys.byteorder == 'big':
                    b = array('h', a)
                    b.byteswap()
                    f.write(b.tobytes())
                else:
                    f.write(a.tobytes())
        os.replace(tmp, percorso)
        # elimina le cache di versioni precedenti dello stesso gruppo
        for nome_file in os.listdir(_dir_cache()):
            if nome_file.endswith('_%s.bin' % gruppo) and nome_file.startswith('audio_') \
                    and os.path.join(_dir_cache(), nome_file) != percorso:
                os.remove(os.path.join(_dir_cache(), nome_file))
    except Exception:
        pass


def _gruppo(gruppo: str, generatore: Callable[[], Dict[str, array]]) -> Dict[str, array]:
    dati = _carica_cache(gruppo)
    if dati is None:
        dati = generatore()
        _salva_cache(gruppo, dati)
    return dati


# ---- adattamento al formato del mixer

def _campiona(x: Sequence[int], freq_out: int) -> array:
    """Ricampiona da 22050 Hz a freq_out (interpolazione lineare)."""
    if freq_out == _SR:
        return array('h', x)
    if freq_out == 2 * _SR:
        n = len(x)
        out = array('h', bytes(4 * n))
        out[0::2] = array('h', x)
        out[1::2] = array('h', [(p + q) >> 1 for p, q in zip(x, x[1:])] + [x[-1] if n else 0])
        return out
    rapporto = _SR / float(freq_out)
    n2 = int((len(x) - 1) / rapporto)
    out2: List[int] = []
    ap = out2.append
    for i in range(n2):
        p = i * rapporto
        j = int(p)
        a = x[j]
        ap(int(a + (x[j + 1] - a) * (p - j)))
    return array('h', out2)


def formatta_per_mixer(x: Sequence[int], freq: int, canali: int, formato: int) -> bytes:
    """Converte un buffer mono int16 a 22050 Hz nel formato (freq, canali, bit) del mixer."""
    m = _campiona(x, freq)
    if formato == -16:
        dati: array = m
    elif formato == 16:
        dati = array('H', [v + 32768 for v in m])
    elif formato == -8:
        dati = array('b', [v >> 8 for v in m])
    elif formato == 8:
        dati = array('B', [(v >> 8) + 128 for v in m])
    elif formato == 32:
        dati = array('f', [v / 32768.0 for v in m])
    else:
        dati = m
    if canali > 1:
        n = len(dati)
        multi = array(dati.typecode, bytes(dati.itemsize * n * canali))
        for c in range(canali):
            multi[c::canali] = dati
        dati = multi
    return dati.tobytes()


# ---- la classe pubblica

class Audio:
    """Sistema audio: effetti reattivi agli eventi, musica e folla in loop."""

    def __init__(self, abilitato: bool = True) -> None:
        self.attivo = False            # True se il mixer funziona
        self.tempo_generazione = 0.0   # secondi spesi nella parte sincrona (effetti)
        self.tempo_sfondo = 0.0        # secondi spesi nel thread (folla + musica)
        self._muto = False
        self._lock = threading.RLock()
        self._rng = random.Random(1234)
        self._base: Dict[str, array] = {}       # sorgenti 22050 Hz mono
        self._suoni: Dict[tuple, object] = {}   # (nome, variante) -> pygame Sound
        self._ultima_var: Dict[str, int] = {}
        self._traccia: Optional[str] = None     # traccia richiesta
        self._canale_mus = CANALE_MUSICA_A
        self._traccia_in_corso: Optional[str] = None
        self._folla_livello = 0.0
        self._folla_in_corso = False
        self._ultimo_boato = -10.0
        self._thread: Optional[threading.Thread] = None
        self._fine_sfondo = threading.Event()
        self._formato: Tuple[int, int, int] = (44100, -16, 2)
        if not abilitato:
            self._fine_sfondo.set()
            return
        if not self._avvia_mixer():
            self._fine_sfondo.set()
            return
        t0 = time.perf_counter()
        try:
            self._base.update(_gruppo('sfx', genera_sfx))
            for nome in self._base:
                self._crea_suono(nome, 1.0)
        except Exception:
            self.attivo = False
            self._fine_sfondo.set()
            return
        self.tempo_generazione = time.perf_counter() - t0
        self._thread = threading.Thread(target=self._lavoro_sfondo, name='audio-sfondo', daemon=True)
        self._thread.start()

    # ---- avvio

    def _avvia_mixer(self) -> bool:
        try:
            if not pygame.mixer.get_init():
                try:
                    pygame.mixer.init(44100, -16, 2, 512)
                except pygame.error:
                    pygame.mixer.init()
            info = pygame.mixer.get_init()
            if not info:
                return False
            self._formato = (int(info[0]), int(info[1]), int(info[2]))
            pygame.mixer.set_num_channels(NUM_CANALI)
            pygame.mixer.set_reserved(CANALI_RISERVATI)
            self.attivo = True
            return True
        except Exception:
            self.attivo = False
            return False

    def _crea_suono(self, nome: str, rapporto: float, chiave: Optional[tuple] = None):
        sorgente = self._base.get(nome)
        if sorgente is None:
            return None
        chiave = chiave or (nome, rapporto)
        with self._lock:
            s = self._suoni.get(chiave)
            if s is not None:
                return s
            freq, fmt, can = self._formato
            dati = formatta_per_mixer(_ripassa(sorgente, rapporto), freq, can, fmt)
            s = pygame.mixer.Sound(buffer=dati)
            self._suoni[chiave] = s
            return s

    def _lavoro_sfondo(self) -> None:
        t0 = time.perf_counter()
        try:
            for gruppo, gen, nomi in (
                ('folla', genera_folla, NOMI_FOLLA),
                ('musica_combattimento', lambda: genera_musica('combattimento'), ('combattimento',)),
                ('musica_menu', lambda: genera_musica('menu'), ('menu',)),
            ):
                dati = _gruppo(gruppo, gen)
                with self._lock:
                    self._base.update(dati)
                    for nome in nomi:
                        s = self._crea_suono(nome, 1.0)
                        if s is not None and nome in TRACCE:
                            s.set_volume(0.0 if self._muto else VOLUME_MUSICA)
                        if s is not None and nome == 'folla':
                            s.set_volume(self._volume_folla())
                    self._riprendi_richieste()
                time.sleep(0)
        except Exception:
            pass
        finally:
            self.tempo_sfondo = time.perf_counter() - t0
            self._fine_sfondo.set()

    def _riprendi_richieste(self) -> None:
        """Avvia musica/folla richieste prima che fossero pronte."""
        if self._traccia and self._traccia != self._traccia_in_corso:
            self._avvia_traccia(self._traccia)
        if self._folla_livello > 0.0 and not self._folla_in_corso:
            self.pubblico(self._folla_livello)

    def attendi(self, timeout: Optional[float] = None) -> bool:
        """Attende la fine della generazione in sfondo (per test e strumenti)."""
        return self._fine_sfondo.wait(timeout)

    def pronto(self) -> bool:
        return self._fine_sfondo.is_set()

    # ---- effetti

    def suona(self, nome: str, volume: float = 1.0, pan: float = 0.0,
              pitch: Optional[float] = None) -> None:
        """Riproduce un effetto. `pan` in [-1, 1]; `pitch` = rapporto di frequenza opzionale."""
        if not self.attivo or self._muto:
            return
        try:
            if nome not in self._base:
                return
            if pitch is not None:
                r = round(max(0.5, min(2.0, float(pitch))), 3)
                s = self._crea_suono(nome, r)
            else:
                var = _VARIANTI.get(nome)
                if var:
                    i = self._rng.randrange(len(var))
                    if i == self._ultima_var.get(nome):
                        i = (i + 1) % len(var)
                    self._ultima_var[nome] = i
                    s = self._crea_suono(nome, var[i])
                else:
                    s = self._crea_suono(nome, 1.0)
            if s is None:
                return
            v = max(0.0, min(1.0, volume)) * VOLUME_SFX
            canale = s.play()
            if canale is not None:
                p = max(-1.0, min(1.0, pan))
                canale.set_volume(v * (1.0 - max(0.0, p) * 0.7), v * (1.0 + min(0.0, p) * 0.7))
        except Exception:
            pass

    def _pan_x(self, x: float) -> float:
        return max(-1.0, min(1.0, (x / float(_RING_L) - 0.5) * 1.6))

    # ---- musica e folla

    def musica(self, traccia: Optional[str]) -> None:
        """Avvia il loop 'menu' o 'combattimento'; None lo ferma (dissolvenza)."""
        if not self.attivo:
            return
        try:
            with self._lock:
                if traccia not in TRACCE:
                    traccia = None
                if traccia == self._traccia and (traccia is None or self._traccia_in_corso == traccia):
                    return
                self._traccia = traccia
                if traccia is None:
                    pygame.mixer.Channel(self._canale_mus).fadeout(600)
                    self._traccia_in_corso = None
                    return
                self._avvia_traccia(traccia)
        except Exception:
            pass

    def _avvia_traccia(self, traccia: str) -> None:
        s = self._suoni.get((traccia, 1.0))
        if s is None:
            return  # sara' avviata a fine generazione
        vecchio = pygame.mixer.Channel(self._canale_mus)
        self._canale_mus = CANALE_MUSICA_B if self._canale_mus == CANALE_MUSICA_A else CANALE_MUSICA_A
        vecchio.fadeout(500)
        s.set_volume(0.0 if self._muto else VOLUME_MUSICA)
        pygame.mixer.Channel(self._canale_mus).play(s, loops=-1, fade_ms=500)
        self._traccia_in_corso = traccia

    def _volume_folla(self) -> float:
        if self._muto:
            return 0.0
        return VOLUME_FOLLA_MAX * (0.12 + 0.88 * self._folla_livello ** 1.3) if self._folla_livello > 0 else 0.0

    def pubblico(self, intensita: float) -> None:
        """Livello del brusio della folla, 0..1 (0 = spento)."""
        if not self.attivo:
            return
        try:
            with self._lock:
                self._folla_livello = max(0.0, min(1.0, float(intensita)))
                s = self._suoni.get(('folla', 1.0))
                if s is None:
                    return
                canale = pygame.mixer.Channel(CANALE_FOLLA)
                if self._folla_livello <= 0.0:
                    if self._folla_in_corso:
                        canale.fadeout(700)
                        self._folla_in_corso = False
                    return
                s.set_volume(self._volume_folla())
                if not self._folla_in_corso or not canale.get_busy():
                    canale.play(s, loops=-1, fade_ms=800)
                    self._folla_in_corso = True
        except Exception:
            pass

    def _boato(self, volume: float) -> None:
        adesso = time.monotonic()
        if adesso - self._ultimo_boato < 1.2:
            return
        self._ultimo_boato = adesso
        self.suona('boato', volume)

    def muto(self, attivo: Optional[bool] = None) -> bool:
        """Imposta (o alterna, se None) il silenzio totale. Ritorna lo stato."""
        self._muto = (not self._muto) if attivo is None else bool(attivo)
        if not self.attivo:
            return self._muto
        try:
            with self._lock:
                for t in TRACCE:
                    s = self._suoni.get((t, 1.0))
                    if s is not None:
                        s.set_volume(0.0 if self._muto else VOLUME_MUSICA)
                f = self._suoni.get(('folla', 1.0))
                if f is not None:
                    f.set_volume(self._volume_folla())
                if self._muto:
                    pygame.mixer.stop()  # ferma anche gli effetti in coda; i loop riprendono a smontaggio
                    self._traccia_in_corso = None
                    self._folla_in_corso = False
                else:
                    self._riprendi_richieste()
        except Exception:
            pass
        return self._muto

    def ferma(self) -> None:
        """Ferma tutto (uscita dal gioco)."""
        if not self.attivo:
            return
        try:
            pygame.mixer.stop()
            self._traccia = None
            self._traccia_in_corso = None
            self._folla_in_corso = False
        except Exception:
            pass

    # ---- eventi della simulazione

    def gestisci_evento(self, evento) -> None:
        """Traduce un evento della simulazione in suoni (ignora quelli sconosciuti)."""
        if not self.attivo:
            return
        try:
            self._dispatch(evento)
        except Exception:
            pass

    def _dispatch(self, e) -> None:
        if isinstance(e, ev.AttaccoIniziato):
            nome, vol = _WHOOSH_MOSSA.get(e.mossa, ('whoosh_leggero', 0.6))
            self.suona(nome, vol)
        elif isinstance(e, ev.ColpoASegno):
            f = max(0.0, min(1.0, float(e.forza)))
            pan = self._pan_x(e.x)
            if e.parato:
                self.suona('parata', 0.45 + 0.5 * f, pan)
            elif e.contro:
                self.suona('impatto_contro', 0.75 + 0.25 * f, pan)
                self._boato(0.35 + 0.3 * f)
            else:
                nome = 'impatto_calcio' if e.mossa in _MOSSE_CALCIO else 'impatto_pugno'
                # i colpi pesanti suonano piu' gravi
                self.suona(nome, 0.45 + 0.55 * f, pan)
                if f > 0.8:
                    self._boato(0.3)
        elif isinstance(e, ev.Schivata):
            self.suona('schivata', 0.9 if e.riuscita else 0.5)
        elif isinstance(e, ev.GuardiaRotta):
            self.suona('guardia_rotta', 1.0)
        elif isinstance(e, ev.Atterramento):
            self.suona('atterramento', 1.0)
            self._boato(0.8)
            self.pubblico(0.75)
        elif isinstance(e, ev.ConteggioArbitro):
            self.suona('conteggio', 0.9, pitch=1.0 + 0.045 * (max(1, e.numero) - 1))
        elif isinstance(e, ev.Rialzo):
            self.suona('passo', 0.7, pitch=0.8)
        elif isinstance(e, ev.KO):
            self.suona('ko', 1.0)
            self._boato(1.0)
            self.pubblico(1.0)
        elif isinstance(e, ev.SuperPronto):
            self.suona('super_pronto', 0.85)
        elif isinstance(e, ev.InizioRound):
            self.suona('campana', 0.9)
            self.pubblico(0.4)
        elif isinstance(e, ev.Via):
            self.suona('impatto_calcio', 0.5, pitch=0.8)
            self.pubblico(0.55)
        elif isinstance(e, ev.FineRound):
            self.suona('campana_tripla', 0.9)
            self.pubblico(0.5)
        elif isinstance(e, ev.FinePartita):
            self._boato(1.0)
            self.pubblico(0.8)
        elif isinstance(e, ev.Passo):
            self.suona('passo', 0.22)
        # Mancato e altri: nessun suono
