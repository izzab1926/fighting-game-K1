"""IA dell'avversario CPU: si comporta come un giocatore umano.

Usa solo lo stato pubblico dell'`Incontro` e produce `Comandi` frame per frame,
premendo i pulsanti (False -> True -> False) come farebbe una persona.

Struttura (per ogni lottatore controllato c'e' un `_Cervello` separato):
  - percezione: ritardo di reazione per ogni attacco avversario, velocita' stimata
    dell'avversario, riconoscimento dei colpi mancati (punibili);
  - reazioni: interrompere un attacco lento, schivare (laterale/indietro), parare
    con una certa probabilita';
  - offesa: scelta della mossa in base a distanza, portata, stile del personaggio,
    sicurezza e varieta'; combo confermate solo se il primo colpo va a segno;
  - posizionamento: banda di distanza preferita, allineamento in profondita',
    uscita dalle corde, recupero del fiato, finte e pause.
La difficolta' cambia i parametri (ritardo, probabilita', errori), non i trucchi.
"""

from __future__ import annotations

import math
import random
from collections import deque
from types import SimpleNamespace
from typing import Optional

from . import costanti as C
from .comandi import Comandi
from .sim import regole as R
from .sim.mosse import MOSSE

_NEUTRI = ('guardia', 'cammina', 'parata')
_A_TERRA = ('atterrato', 'rialzo', 'ko')
_BASE = ('jab', 'diretto', 'calcio_basso', 'calcio_alto')
_PULSANTI = ('jab', 'diretto', 'calcio_basso', 'calcio_alto', 'guardia', 'schivata', 'speciale')

# ---- parametri per livello
# reazione/jitter: frame di ritardo prima di "accorgersi" di un attacco;
# p_para: parare cio' che si e' visto arrivare; p_prev: propensione a tenere la guardia
# alta "a sentimento"; p_interrompi/p_schiva/p_indietro: risposte piu' evolute;
# aggr: voglia di attaccare; cad: frame tra una decisione e l'altra; p_combo: chance
# di pianificare una combo; conferma: frame prima di proseguire una combo;
# p_punisci/punisci_rit: punizione dei colpi mancati; err_dist/err_z: errori di
# valutazione (unita'); sicurezza: quanto si evitano mosse lente a corta distanza.
_LIVELLI = {
    'facile': dict(
        reazione=21, jitter=6, p_para=0.26, p_prev=0.05, p_interrompi=0.0, p_schiva=0.0,
        p_indietro=0.0, aggr=0.40, cad=(16, 36), p_combo=0.18, conferma=16, p_pressione=0.15,
        p_punisci=0.10, punisci_rit=22, err_dist=32.0, err_z=26.0, sicurezza=0.0,
        p_stordito=0.15, p_super=0.25, soglia_fiato=0.14, pausa_att=(50, 130),
        p_riflesso=0.0, allinea_z=42.0, p_finta=0.03, p_corde=0.2, previsione=0.0, adatt=0.3),
    'normale': dict(
        reazione=13, jitter=4, p_para=0.50, p_prev=0.15, p_interrompi=0.10, p_schiva=0.06,
        p_indietro=0.04, aggr=0.62, cad=(10, 24), p_combo=0.50, conferma=8, p_pressione=0.30,
        p_punisci=0.45, punisci_rit=12, err_dist=16.0, err_z=14.0, sicurezza=0.35,
        p_stordito=0.50, p_super=0.55, soglia_fiato=0.24, pausa_att=(28, 80),
        p_riflesso=0.10, allinea_z=30.0, p_finta=0.06, p_corde=0.5, previsione=0.5, adatt=0.7),
    'difficile': dict(
        reazione=8, jitter=3, p_para=0.74, p_prev=0.21, p_interrompi=0.30, p_schiva=0.24,
        p_indietro=0.14, aggr=0.78, cad=(7, 18), p_combo=0.78, conferma=4, p_pressione=0.40,
        p_punisci=0.80, punisci_rit=7, err_dist=8.0, err_z=8.0, sicurezza=0.7,
        p_stordito=0.80, p_super=0.80, soglia_fiato=0.28, pausa_att=(18, 55),
        p_riflesso=0.25, allinea_z=20.0, p_finta=0.09, p_corde=0.8, previsione=0.85, adatt=1.0),
    'campione': dict(
        reazione=4, jitter=1.5, p_para=0.88, p_prev=0.26, p_interrompi=0.50, p_schiva=0.42,
        p_indietro=0.22, aggr=0.92, cad=(5, 13), p_combo=0.93, conferma=2, p_pressione=0.45,
        p_punisci=0.96, punisci_rit=3, err_dist=4.0, err_z=4.0, sicurezza=1.0,
        p_stordito=0.92, p_super=0.95, soglia_fiato=0.30, pausa_att=(12, 40),
        p_riflesso=0.38, allinea_z=12.0, p_finta=0.10, p_corde=1.0, previsione=1.0, adatt=1.0),
}

# ---- stile per personaggio: banda di distanza (spazio tra i corpi), affinita' con
# le mosse, agilita' (propensione a muoversi di lato) e prudenza
_STILI = {
    'toro': dict(banda=(30, 88), aff={'jab': 1.0, 'diretto': 1.4, 'calcio_basso': 0.9, 'calcio_alto': 0.5},
                 agilita=0.7, prudenza=0.9),
    'vento': dict(banda=(70, 118), aff={'jab': 1.5, 'diretto': 0.9, 'calcio_basso': 1.0, 'calcio_alto': 0.5},
                  agilita=1.7, prudenza=1.0),
    'muro': dict(banda=(20, 72), aff={'jab': 1.0, 'diretto': 1.3, 'calcio_basso': 1.0, 'calcio_alto': 0.4},
                 agilita=0.5, prudenza=1.2),
    'lama': dict(banda=(100, 150), aff={'jab': 0.8, 'diretto': 0.6, 'calcio_basso': 1.3, 'calcio_alto': 1.6},
                 agilita=1.1, prudenza=1.0),
}

# peso base delle mosse quando sono tutte possibili
_PESO_MOSSA = {'jab': 1.0, 'diretto': 0.8, 'gancio': 0.9, 'calcio_basso': 0.7,
               'ginocchiata': 0.8, 'calcio_alto': 0.5, 'calcio_girato': 1.0}

# combo pianificabili dopo la prima mossa: (sequenza di pulsanti, peso)
_COMBO = {
    'jab': (((('diretto', 'calcio_basso')), 3.0), (('diretto', 'calcio_alto'), 1.5),
            (('jab', 'diretto', 'calcio_alto'), 1.2), (('diretto',), 1.5), (('jab',), 0.8)),
    'diretto': ((('calcio_basso',), 2.0), (('calcio_alto',), 2.2), (('speciale',), 1.5)),
    'gancio': ((('calcio_basso',), 2.0), (('calcio_alto',), 2.2), (('speciale',), 1.5)),
}


def _segno(x: float) -> int:
    return (x > 0) - (x < 0)


def _stile_per(personaggio) -> dict:
    """Stile noto per id, oppure ricavato dalle statistiche (roster modificato)."""
    st = _STILI.get(personaggio.id)
    if st is not None:
        return st
    centro = 40 + 70 * (personaggio.portata - 0.9) / 0.25
    return dict(banda=(centro - 30, centro + 30),
                aff={'jab': 1.0, 'diretto': 1.0, 'calcio_basso': 1.0, 'calcio_alto': 0.8},
                agilita=personaggio.velocita, prudenza=1.0)


class _Dati:
    """Misure derivate calcolate una volta per frame."""
    __slots__ = ('gap', 'dz', 'fw', 'vf', 'vz', 'rap_sta', 'rap_sta_opp')


class _Cervello:
    """Il 'giocatore' che guida un lottatore."""

    def __init__(self, indice: int, livello: SimpleNamespace, rng: random.Random):
        self.i = indice
        self.p = livello
        self.rng = rng
        self.t = 0
        self._ultimo_frame = -1
        self._round = None
        self._azzera_round()

    # ---- azzeramenti
    def _azzera_round(self) -> None:
        rng = self.rng
        self.tasti = {}
        self.raff = {}
        self.seg = []                 # segmenti di movimento [dx, dz, ticks]
        self.guardia_fino = 0
        self.prossima = self.t + rng.randint(4, 24)
        self.piano = []               # pulsanti della combo ancora da premere
        self.att_ok_da = self.t + rng.randint(25, 80)
        self.umore = rng.uniform(0.85, 1.2)
        self.umore_fino = self.t + rng.randint(150, 300)
        self.banda = None
        self.stile = None
        self.recenti = deque(maxlen=4)
        self.xs = deque(maxlen=8)
        self.zs = deque(maxlen=8)
        # attacco avversario in corso
        self.o_stato = None
        self.o_mossa = None
        self.o_fs = 0
        self.att_id = 0
        self.att_rit = 10
        self.att_reagito = True
        self.pun_rit = 6
        self.pun_valutato = 0
        self.pun = None               # (pulsante, tick_lancio, att_id)
        self.pend = None              # azione programmata (schivata in ritardo)
        # mio attacco / combo
        self.contatto_t = None
        self.lancio_t = -10
        self.gap_contatto = 0.0
        self.seguito = False
        self.premuto_prosegui = False
        self.conferma = 1
        self.pressione_ok = False
        # altro
        self.st_prec = None
        self.mio_fs = 0
        self.pressione = 0.0          # colpi subiti/parati di recente (decade)
        self.guardia_da = None        # tick in cui e' iniziata la guardia continua
        self.tieni_guardia = False
        self.bl_valutato = False
        self.stanco = False
        self.fuga_ok_da = 0
        self.guardia_dopo = 0

    # ---- utilita'
    def _premi(self, pulsante: str, ticks: int = 2) -> bool:
        if self.tasti.get(pulsante, 0) > 0 or self.raff.get(pulsante, 0) > 0:
            return False
        self.tasti[pulsante] = ticks
        return True

    def _pesata(self, opzioni):
        """Sceglie (elemento, peso) con probabilita' proporzionale al peso."""
        tot = sum(w for _, w in opzioni if w > 0)
        if tot <= 0:
            return None
        r = self.rng.random() * tot
        for x, w in opzioni:
            if w <= 0:
                continue
            r -= w
            if r <= 0:
                return x
        return opzioni[-1][0]

    def _tieni_guardia_per(self, ticks: int) -> None:
        self.guardia_fino = max(self.guardia_fino, self.t + ticks)
        self.seg = []

    # ---- ciclo principale
    def passo(self, inc, io, opp) -> Comandi:
        if inc.frame < self._ultimo_frame:
            self._azzera_round()
            self._round = None
        self._ultimo_frame = inc.frame
        self.t += 1
        c = Comandi()
        if self._round != inc.numero_round:
            self._azzera_round()
            self._round = inc.numero_round
        if self.stile is None:
            self.stile = _stile_per(io.personaggio)
            b = self.stile['banda']
            off = self.rng.uniform(-10, 10)
            self.banda = (b[0] + off, b[1] + off)
        if inc.fase != 'combattimento':
            self.seg = []
            self.piano = []
            self.guardia_fino = 0
            return c
        d = self._misure(inc, io, opp)
        self._osserva(inc, io, opp)
        if self.t >= self.umore_fino:
            self.umore = self.rng.uniform(0.8, 1.25)
            self.umore_fino = self.t + self.rng.randint(150, 320)
        st = io.stato
        self.pressione *= 0.993
        if st in ('colpito', 'bloccato') and (self.st_prec != st or io.frame_stato < self.mio_fs):
            self.pressione += 1.0
        self.mio_fs = io.frame_stato
        if st == 'attacco':
            self._durante_attacco(inc, io, opp, d)
        elif st in _NEUTRI:
            self._neutro(inc, io, opp, d)
        elif st in ('colpito', 'bloccato', 'guardia_rotta', 'atterrato', 'rialzo'):
            self._stordito(inc, io, opp, d)
        else:
            self.seg = []
        if st != 'attacco' and self.t > self.lancio_t + 4:
            self.piano = []
            self.contatto_t = None
        self.st_prec = st
        self._emetti(c, io, opp, d)
        return c

    # ---- percezione
    def _misure(self, inc, io, opp) -> _Dati:
        d = _Dati()
        d.fw = 1 if opp.x >= io.x else -1
        d.gap = abs(opp.x - io.x) - io.hw - opp.hw
        d.dz = opp.z - io.z
        if inc.hitstop == 0:
            self.xs.append(opp.x)
            self.zs.append(opp.z)
        n = len(self.xs)
        if n >= 5 and opp.stato in ('cammina', 'schivata', 'guardia', 'parata'):
            d.vf = (self.xs[-1] - self.xs[-5]) / 4.0 * d.fw
            d.vz = (self.zs[-1] - self.zs[-5]) / 4.0
        else:
            d.vf = 0.0
            d.vz = 0.0
        d.rap_sta = io.stamina / io.stamina_max if io.stamina_max else 0.0
        d.rap_sta_opp = opp.stamina / opp.stamina_max if opp.stamina_max else 0.0
        return d

    def _osserva(self, inc, io, opp) -> None:
        """Riconosce l'inizio di un attacco avversario e campiona il ritardo di reazione."""
        rng = self.rng
        p = self.p
        nuovo = False
        if opp.stato == 'attacco':
            nuovo = (self.o_stato != 'attacco' or opp.mossa != self.o_mossa
                     or opp.frame_stato < self.o_fs)
        elif opp.stato == 'guardia_rotta' and self.o_stato != 'guardia_rotta':
            nuovo = True
        if nuovo:
            self.att_id += 1
            lettura = 1.0 - 0.6 * min(1.0, self.pressione / 3.0) * p.adatt     # riconosce il ritmo
            self.att_rit = max(1, int(round(rng.gauss(p.reazione, p.jitter * 0.5) * lettura)))
            self.pun_rit = max(1, int(round(rng.gauss(p.punisci_rit, p.jitter * 0.5))))
            self.att_reagito = False
        self.o_stato = opp.stato
        self.o_mossa = opp.mossa
        self.o_fs = opp.frame_stato

    # ---- reazione a un attacco in arrivo
    def _reagisci(self, inc, io, opp, d) -> bool:
        if opp.stato != 'attacco' or opp.contatto or opp.fase_mossa != 'avvio':
            return False
        if self.att_reagito or opp.frame_stato < self.att_rit:
            return False
        self.att_reagito = True
        nome = opp.mossa
        m = MOSSE[nome]
        if not R.davanti(opp, io):
            return False
        tot = m.avvio + m.attivo
        avanz = m.avanzamento * (tot - opp.frame_stato) / tot
        if abs(d.dz) > R.TOLLERANZA_Z + 6:
            return False
        if d.gap - 0.8 * avanz > R.portata_effettiva(opp, nome) + 8:
            return False
        p = self.p
        rng = self.rng
        t_att = m.avvio - opp.frame_stato - 1          # tick prima che sia attivo
        stanco_sta = d.rap_sta < 0.12
        if rng.random() < p.p_interrompi and self._interrompi(inc, io, opp, d, t_att):
            return True
        lungo = m.avvio >= 12
        if lungo and io.stamina >= R.COSTO_SCHIVATA and t_att >= 2:
            if rng.random() < p.p_schiva and t_att >= 3:
                if self._schiva_a_tempo('laterale', io, opp, d, t_att, m):
                    return True
            elif rng.random() < p.p_indietro:
                if self._schiva_a_tempo('indietro', io, opp, d, t_att, m):
                    return True
        q = p.p_para * (0.4 if stanco_sta else 1.0)
        if rng.random() < q:
            self._tieni_guardia_per(t_att + m.attivo + 3 + rng.randint(0, 9))
            return True
        return False

    def _interrompi(self, inc, io, opp, d, t_att: int) -> bool:
        """Colpisce per primo durante l'avvio (lento) dell'avversario: colpo d'incontro."""
        m1 = MOSSE[opp.mossa]
        cand = []
        for btn in ('jab', 'diretto', 'calcio_basso'):
            mossa = io.mossa_per_pulsante(btn, opp)
            m2 = MOSSE[mossa]
            if m2.avvio > t_att - 1 or io.stamina < m2.stamina:
                continue
            gap_hit = d.gap - 0.6 * m1.avanzamento - 0.6 * m2.avanzamento
            if gap_hit > R.portata_effettiva(io, mossa) - 3:
                continue
            cand.append((btn, m2.danno * self.stile['aff'][btn]))
        if not cand:
            return False
        btn = self._pesata(cand)
        self._lancia(btn, io, opp)
        return True

    def _schiva_a_tempo(self, tipo: str, io, opp, d, t_att: int, m) -> bool:
        if tipo == 'laterale':
            massimo = 15 - m.attivo
            minimo = 3
        else:
            massimo = 11 - m.attivo
            minimo = 2
            lo, hi = R.limiti_x(io.hw)
            spazio = (io.x - lo) if d.fw > 0 else (hi - io.x)
            if spazio < 55:
                return False
        if t_att < minimo:
            return False
        if t_att > massimo:
            # troppo presto: si programma la schivata per il momento giusto
            self.pend = (self.t + (t_att - (minimo + massimo) // 2), tipo, self.att_id)
            return True
        self._schiva(tipo, io, d)
        return True

    def _schiva(self, tipo: str, io, d) -> None:
        if tipo == 'laterale':
            su = R.Z_MAX - io.z
            giu = io.z - R.Z_MIN
            if abs(d.dz) > 8:
                pref = -1 if d.dz > 0 else 1
            else:
                pref = 1 if su > giu else -1
            spazio = su if pref > 0 else giu
            if spazio < 50:
                pref = -pref
            self.seg = [[0, pref, 3]]
        else:
            self.seg = [[0, 0, 3]]
        self.guardia_fino = 0
        self.piano = []
        self._premi('schivata', 3)

    # ---- attacchi
    def _lancia(self, btn: str, io, opp) -> None:
        mossa = io.mossa_per_pulsante(btn, opp) if btn != 'speciale' else 'calcio_girato'
        self._premi(btn)
        self.lancio_t = self.t
        self.recenti.append(mossa)
        self.piano = self._piano_per(mossa, io)
        self.att_ok_da = self.t + self.rng.randint(*self.p.pausa_att)
        self.seg = []
        self.guardia_fino = 0
        self.pend = None
        self.pun = None
        self.contatto_t = None
        self.seguito = False
        self.conferma = max(1, int(round(self.rng.gauss(self.p.conferma, self.p.conferma * 0.25))))
        self.pressione_ok = self.rng.random() < self.p.p_pressione

    def _piano_per(self, mossa: str, io) -> list:
        opzioni = _COMBO.get(mossa)
        if not opzioni or self.rng.random() >= self.p.p_combo:
            return []
        ok = []
        for seq, w in opzioni:
            if 'speciale' in seq:
                if not io.super_pronto or self.rng.random() >= self.p.p_super:
                    continue
                w = w * 3
            ok.append((list(seq), w))
        s = self._pesata(ok)
        return s if s else []

    def _candidati(self, inc, io, opp, d) -> list:
        """Attacchi eseguibili adesso: [(pulsante, mossa, peso)]."""
        if opp.stato in _A_TERRA or (opp.stato == 'schivata' and opp.invulnerabile):
            return []
        if not R.davanti(io, opp):
            return []
        p = self.p
        rng = self.rng
        e = rng.uniform(-p.err_dist, p.err_dist)
        ez = rng.uniform(-p.err_z, p.err_z)
        jab_opp = R.portata_effettiva(opp, 'jab')
        out = []
        for btn in _BASE:
            mossa = io.mossa_per_pulsante(btn, opp)
            m = MOSSE[mossa]
            if io.stamina < m.stamina:
                continue
            port = R.portata_effettiva(io, mossa)
            mov = max(-35.0, min(35.0, d.vf * m.avvio * p.previsione))
            gap_hit = d.gap + mov - 0.6 * m.avanzamento + e
            if gap_hit > port:
                continue
            dz_hit = abs(d.dz + d.vz * m.avvio * 0.5 * p.previsione + ez)
            if dz_hit > R.TOLLERANZA_Z - 6:
                continue
            w = self.stile['aff'][btn] * _PESO_MOSSA[mossa]
            if gap_hit > port - 10:
                w *= 0.6
            if m.avvio >= 12 and opp.stato in _NEUTRI and d.gap <= jab_opp + 10:
                w *= 1.0 - 0.75 * p.sicurezza
            w *= 0.6 ** sum(1 for r in self.recenti if r == mossa)
            gmin, gmax = self.banda
            w *= 1.35 if gmin - 12 <= d.gap <= gmax + 12 else 0.75
            if opp.stato == 'parata':
                w *= 1.4 if d.rap_sta_opp < 0.3 else 0.45
            out.append((btn, mossa, w))
        return out

    def _durante_attacco(self, inc, io, opp, d) -> None:
        """Proseguimento delle combo dopo un colpo confermato."""
        if not io.contatto:
            self.contatto_t = None
            return
        if self.contatto_t is None:
            self.contatto_t = self.t
            self.gap_contatto = d.gap
            self.seguito = False
        if not self.piano or self.seguito:
            return
        if self.t - self.contatto_t < self.conferma:
            return
        if opp.stato in _A_TERRA or opp.stato in ('ko',):
            self.piano = []
            return
        if opp.stato == 'colpito' or opp.stato == 'guardia_rotta':
            pass
        elif opp.stato in ('bloccato', 'parata'):
            if not self.pressione_ok:
                self.piano = []
                return
        else:
            self.piano = []
            return
        m1 = io.dati_mossa
        m_fin = m1.avvio + m1.attivo + R.FINESTRA_CANCEL
        if io.frame_stato >= m_fin:
            self.piano = []
            return
        # sceglie il seguito che arriva davvero (la spinta allontana l'avversario)
        gap_prev = self.gap_contatto + m1.spinta
        cand = [self.piano[0]] + [b for b in ('diretto', 'calcio_basso', 'jab') if b != self.piano[0]]
        for btn in cand:
            if btn == 'speciale':
                if not io.super_pronto:
                    continue
                mossa = 'calcio_girato'
            else:
                mossa = io.mossa_per_pulsante(btn, opp)
            base = 'calcio_girato' if btn == 'speciale' else btn
            if base not in m1.cancella_in and mossa not in m1.cancella_in:
                continue
            m2 = MOSSE[mossa]
            if io.stamina < m2.stamina * 0.6 and btn != 'speciale':
                continue
            if gap_prev - 0.6 * m2.avanzamento > R.portata_effettiva(io, mossa) - 2:
                continue
            if self._premi(btn):
                self.recenti.append(mossa)
                self.piano = self.piano[1:] if btn == self.piano[0] else []
                self.seguito = True
                self.contatto_t = None
                return
        self.piano = []

    # ---- punizione di colpi mancati / guardia rotta
    def _punisci(self, inc, io, opp, d) -> bool:
        if opp.stato == 'guardia_rotta':
            rimasti = opp.durata_stato - opp.frame_stato
            visto = opp.frame_stato >= self.pun_rit // 2
        elif opp.stato == 'attacco' and opp.fase_mossa == 'recupero':
            m = MOSSE[opp.mossa]
            rimasti = opp.durata_stato - opp.frame_stato
            visto = opp.frame_stato - (m.avvio + m.attivo) >= self.pun_rit
        else:
            return False
        if not visto or self.pun_valutato == self.att_id:
            return False
        self.pun_valutato = self.att_id
        rng = self.rng
        if opp.stato == 'attacco' and opp.contatto and rng.random() < 0.5:
            return False           # potrebbe concatenare: si aspetta
        if rng.random() >= self.p.p_punisci:
            return False
        scelta = self._miglior_punizione(io, opp, d, rimasti, opp.stato == 'guardia_rotta')
        if scelta is None:
            return False
        btn, tw = scelta
        if tw <= 0:
            self._lancia(btn, io, opp)
        else:
            self.seg = [[1, 'A', tw]]
            self.pun = (btn, self.t + tw, self.att_id)
            self.guardia_fino = 0
        return True

    def _miglior_punizione(self, io, opp, d, rimasti: int, senza_difesa: bool):
        v = R.VELOCITA_CAMMINO * io.personaggio.velocita * (R.FATTORE_AFFANNATO if io.affannato else 1.0)
        v *= 0.9
        pot = io.personaggio.potenza
        cand = []
        for btn in _BASE + ('speciale',):
            if btn == 'speciale':
                if not io.super_pronto:
                    continue
                mossa = 'calcio_girato'
            else:
                mossa = io.mossa_per_pulsante(btn, opp)
            m = MOSSE[mossa]
            if io.stamina < m.stamina and not senza_difesa:
                continue
            need = d.gap - 0.6 * m.avanzamento - R.portata_effettiva(io, mossa) + 2
            tw = int(math.ceil(need / v)) if need > 0 else 0
            if abs(d.dz) > R.TOLLERANZA_Z - 10:
                tw = max(tw, int(math.ceil((abs(d.dz) - 30) / (R.VELOCITA_PROFONDITA * io.personaggio.velocita * 0.85))))
            margine = 2 if not senza_difesa else -6
            if tw + m.avvio > rimasti - margine:
                continue
            dmg = m.danno * pot * (1.0 if senza_difesa else 1.3)
            if m.atterra == 'sempre' or (m.atterra == 'contro' and not senza_difesa):
                dmg += 7
            if m.avvio > 10:
                dmg *= 0.9
            cand.append((btn, tw, dmg * (1 - 0.015 * tw)))
        if not cand:
            return None
        if self.rng.random() < 0.7:
            cand.sort(key=lambda x: -x[2])
            return cand[0][0], cand[0][1]
        b = self._pesata([((x[0], x[1]), x[2]) for x in cand])
        return b

    def _esegui_punizione(self, io, opp, d) -> bool:
        """Completa una punizione iniziata con qualche passo di avvicinamento."""
        btn, quando, att_id = self.pun
        if att_id != self.att_id or opp.stato not in ('attacco', 'guardia_rotta'):
            self.pun = None
            self.seg = []
            return False
        if self.t < quando:
            return True
        self.pun = None
        self.seg = []
        mossa = 'calcio_girato' if btn == 'speciale' else io.mossa_per_pulsante(btn, opp)
        m = MOSSE[mossa]
        if d.gap - 0.6 * m.avanzamento > R.portata_effettiva(io, mossa) + 4:
            return False
        if btn == 'speciale' and not io.super_pronto:
            return False
        self._lancia(btn, io, opp)
        return True

    # ---- stati non azionabili
    def _stordito(self, inc, io, opp, d) -> None:
        st = io.stato
        rng = self.rng
        p = self.p
        if st != self.st_prec:
            self.tieni_guardia = rng.random() < self._p_stordito()
            self.bl_valutato = False
            self.seg = []
            self.piano = []
        if st in ('colpito', 'bloccato', 'rialzo', 'atterrato') and self.tieni_guardia:
            self.guardia_fino = self.t + 2
        if st == 'guardia_rotta':
            self.guardia_fino = 0
        if st == 'bloccato' and not self.bl_valutato:
            resto = io.durata_stato - io.frame_stato
            if resto <= 5:
                self.bl_valutato = True
                if opp.stato == 'attacco' and opp.fase_mossa == 'recupero' and rng.random() < min(0.95, p.p_punisci * 0.8 + 0.12 * min(self.pressione, 3.0) * p.adatt):
                    r_opp = opp.durata_stato - opp.frame_stato
                    cand = []
                    for btn in ('jab', 'diretto', 'calcio_basso'):
                        mossa = io.mossa_per_pulsante(btn, opp)
                        m2 = MOSSE[mossa]
                        if resto + m2.avvio > r_opp + 3 or io.stamina < m2.stamina:
                            continue
                        if d.gap - 0.6 * m2.avanzamento > R.portata_effettiva(io, mossa) - 4:
                            continue
                        cand.append((btn, m2.danno))
                    if cand:
                        btn = self._pesata(cand)
                        self._lancia(btn, io, opp)
                        self.guardia_fino = 0

    def _p_stordito(self) -> float:
        p = self.p
        return min(0.95, p.p_stordito + 0.18 * min(self.pressione, 3.0) * p.adatt)

    # ---- neutro: decisioni principali
    def _neutro(self, inc, io, opp, d) -> None:
        p = self.p
        rng = self.rng
        t = self.t
        # appena usciti da una fase di stordimento: guardia per un po'
        if self.st_prec in ('colpito', 'bloccato', 'rialzo') and rng.random() < self._p_stordito():
            self._tieni_guardia_per(rng.randint(4, 12 + int(6 * min(self.pressione, 3.0) * p.adatt)))
        if self.pend is not None:
            quando, tipo, att_id = self.pend
            if att_id != self.att_id or opp.stato != 'attacco':
                self.pend = None
            elif t >= quando:
                self.pend = None
                if io.stamina >= R.COSTO_SCHIVATA:
                    self._schiva(tipo, io, d)
                    return
        if self.pun is not None and self._esegui_punizione(io, opp, d):
            return
        if self._reagisci(inc, io, opp, d):
            return
        if opp.stato == 'attacco' and opp.fase_mossa in ('avvio', 'attivo') and not opp.contatto:
            # non si cammina dentro un colpo in arrivo
            self.seg = [s for s in self.seg if s[0] != 1]
        if self._punisci(inc, io, opp, d):
            return
        self._stanchezza(io, d)
        if opp.stato in _A_TERRA:
            self._avversario_a_terra(io, opp, d)
            return
        # sotto pressione si resta chiusi finche' l'avversario continua ad attaccare
        if (opp.stato == 'attacco' and self.pressione >= 1.0 and d.gap <= self._portata_max(opp) + 20
                and rng.random() < 0.9 * p.adatt):
            self.guardia_fino = max(self.guardia_fino, t + 2)
        if t < self.guardia_fino:
            if self.guardia_da is None:
                self.guardia_da = t
            elif t - self.guardia_da > 70 and opp.stato != 'attacco':
                self.guardia_fino = t          # basta stare chiusi: si torna a giocare
                self.guardia_da = None
            else:
                return
            if t < self.guardia_fino:
                return
        else:
            self.guardia_da = None
        # riflessi: colpisce chi sta entrando nella propria portata
        if self._riflesso(inc, io, opp, d):
            return
        if self.seg and t < self.prossima:
            return
        self._decidi(inc, io, opp, d)

    def _stanchezza(self, io, d) -> None:
        soglia = self.p.soglia_fiato
        if d.rap_sta < soglia:
            self.stanco = True
        elif d.rap_sta > soglia + 0.28:
            self.stanco = False

    def _avversario_a_terra(self, io, opp, d) -> None:
        """Niente attacchi: ci si sistema in profondita' e si aspetta che si rialzi."""
        self.piano = []
        if opp.stato != 'rialzo':
            self.guardia_fino = min(self.guardia_fino, self.t)
        if self.t < self.guardia_fino:
            return
        if not self.seg or self.t >= self.prossima:
            self.prossima = self.t + self.rng.randint(8, 22)
            if abs(d.dz) > self.p.allinea_z and self.rng.random() < 0.7:
                self.seg = [[0, 'A', self.rng.randint(6, 14)]]
            elif opp.stato == 'rialzo' and self.rng.random() < self.p.p_prev * 3:
                self._tieni_guardia_per(self.rng.randint(10, 26))
            else:
                self.seg = []

    def _aggr(self, inc, io, opp, d) -> float:
        a = self.p.aggr * self.umore
        pv = R.percentuale_vita(io) - R.percentuale_vita(opp)
        if inc.tempo_rimasto < 28:
            if pv < -0.05:
                a *= 1.55
            elif pv > 0.05:
                a *= 0.55
        if R.percentuale_vita(opp) < 0.25:
            a *= 1.25
        if opp.affannato:
            a *= 1.5
        if io.affannato:
            a *= 0.5
        return a

    def _riflesso(self, inc, io, opp, d) -> bool:
        p = self.p
        if p.p_riflesso <= 0 or self.stanco or inc.tempo_rimasto <= 0:
            return False
        if self.t < self.att_ok_da or opp.stato not in ('cammina',) or d.vf > -1.5:
            return False
        if self.rng.random() >= p.p_riflesso * 0.25:
            return False
        cand = self._candidati(inc, io, opp, d)
        cand = [x for x in cand if MOSSE[x[1]].avvio <= 11]
        if not cand:
            return False
        btn = self._pesata([(x[0], x[2]) for x in cand])
        if btn is None:
            return False
        self._lancia(btn, io, opp)
        return True

    def _decidi(self, inc, io, opp, d) -> None:
        p = self.p
        rng = self.rng
        st = self.stile
        gmin, gmax = self.banda
        aggr = self._aggr(inc, io, opp, d)
        self.prossima = self.t + rng.randint(*p.cad)
        lo, hi = R.limiti_x(io.hw)
        dist_muro = min(io.x - lo, hi - io.x)
        lato_muro = -1 if (io.x - lo) < (hi - io.x) else 1
        alle_corde = (dist_muro < 120 and _segno(opp.x - io.x) == -lato_muro and d.gap < 240)
        ropes_opp = False
        olo, ohi = R.limiti_x(opp.hw)
        if min(opp.x - olo, ohi - opp.x) < 110 and d.gap < 240:
            ropes_opp = True
        if ropes_opp:
            aggr *= 1.2
        # ---- uscita dalle corde
        if alle_corde and self.t >= self.fuga_ok_da and rng.random() < 0.6 * p.p_corde:
            self._fuga_corde(io, opp, d, lato_muro)
            return
        # ---- elenco delle opzioni
        cand = self._candidati(inc, io, opp, d)
        opz = []
        att_ok = (bool(cand) and self.t >= self.att_ok_da and not self.stanco
                  and inc.tempo_rimasto > 0)
        if att_ok:
            in_banda = gmin - 15 <= d.gap <= gmax + 15
            opz.append(('attacca', 2.2 * aggr * (1.25 if in_banda else 0.9)))
        soglia_vicino = gmin + 5
        if d.gap > gmax + 8:
            opz.append(('avanza', 1.2 + (d.gap - gmax) / 70.0 + 0.6 * aggr))
        elif d.gap > soglia_vicino:
            opz.append(('avanza', 0.28 * aggr))
        if d.gap < soglia_vicino and not alle_corde:
            opz.append(('arretra', 1.0 + (soglia_vicino - d.gap) / 40.0))
        elif d.gap < gmax:
            opz.append(('arretra', 0.22 * st['prudenza']))
        opz.append(('attesa', 0.55 * (1.5 - min(aggr, 1.2))))
        zona = 1.0 if d.gap <= self._portata_max(opp) + 25 else 0.2
        opz.append(('guardia', p.p_prev * 3.2 * zona * st['prudenza']
                    * (1.0 + 0.35 * min(self.pressione, 3.0) * p.adatt)
                    * (0.4 if opp.affannato else 1.0)))
        if abs(d.dz) > p.allinea_z:
            opz.append(('allinea', 0.9 + aggr))
        opz.append(('laterale', 0.22 * st['agilita'] * (0.6 + zona)))
        opz.append(('finta', p.p_finta * 2.0 * (1.2 if p.aggr > 0.7 else 1.0)))
        if self.stanco:
            opz = [(n, w * (0.15 if n in ('attacca', 'avanza') else 1.0)) for n, w in opz]
            opz.append(('recupera', 2.5))
        scelta = self._pesata(opz) or 'attesa'
        if scelta == 'attacca':
            btn = self._pesata([(x[0], x[2]) for x in cand])
            if btn is None:
                scelta = 'attesa'
            else:
                self._lancia(btn, io, opp)
                return
        self._piano_movimento(scelta, io, opp, d, alle_corde)

    def _portata_max(self, opp) -> float:
        return max(R.portata_effettiva(opp, m) for m in ('jab', 'diretto', 'calcio_basso', 'calcio_alto'))

    def _piano_movimento(self, scelta: str, io, opp, d, alle_corde: bool) -> None:
        rng = self.rng
        p = self.p
        if scelta == 'avanza':
            self.seg = [[1, 'A' if abs(d.dz) > p.allinea_z * 0.5 else 0, rng.randint(6, 20)]]
        elif scelta == 'arretra':
            self.seg = [[-1, 'A' if abs(d.dz) > p.allinea_z else 0, rng.randint(5, 16)]]
        elif scelta == 'attesa':
            self.seg = [[0, 0, rng.randint(6, 24)]]
        elif scelta == 'guardia':
            self._tieni_guardia_per(rng.randint(10, 30))
        elif scelta == 'allinea':
            self.seg = [[0, 'A', rng.randint(6, 16)]]
        elif scelta == 'laterale':
            self._passo_laterale(io, d)
        elif scelta == 'finta':
            self.seg = [[1, 0, rng.randint(4, 8)], [0, 0, rng.randint(2, 6)],
                        [-1, 0, rng.randint(5, 10)]]
        elif scelta == 'recupera':
            if d.gap < self._portata_max(opp) + 30:
                self.seg = [[-1, 0, rng.randint(8, 18)]]
            elif rng.random() < 0.4:
                self._tieni_guardia_per(rng.randint(10, 30))
            else:
                self.seg = [[0, 0, rng.randint(12, 30)]]

    def _passo_laterale(self, io, d) -> None:
        rng = self.rng
        su = R.Z_MAX - io.z
        giu = io.z - R.Z_MIN
        if rng.random() < 0.55 and abs(d.dz) > 6:
            dirz = _segno(d.dz)          # verso l'allineamento
        else:
            dirz = 1 if su > giu else -1
            if rng.random() < 0.4:
                dirz = -dirz
        spazio = su if dirz > 0 else giu
        if spazio < 40:
            dirz = -dirz
        self.seg = [[rng.choice((0, 0, 1, -1)), dirz, rng.randint(6, 16)]]

    def _fuga_corde(self, io, opp, d, lato_muro: int) -> None:
        rng = self.rng
        p = self.p
        self.fuga_ok_da = self.t + rng.randint(50, 110)
        su = R.Z_MAX - io.z
        giu = io.z - R.Z_MIN
        if abs(d.dz) > 12:
            dirz = -_segno(d.dz)
        else:
            dirz = 1 if su > giu else -1
        spazio = su if dirz > 0 else giu
        if spazio < 60:
            dirz = -dirz
        # una schivata laterale porta subito fuori linea (livelli alti), poi si scavalca
        if io.stamina >= R.COSTO_SCHIVATA * 1.5 and p.p_schiva > 0.2 and rng.random() < 0.5:
            self._schiva('laterale', io, d)
            self.seg = [[0, dirz, 3], ['C', dirz, rng.randint(16, 28)]]
            return
        self.seg = [[0, dirz, rng.randint(12, 20)], ['C', dirz, rng.randint(16, 30)]]

    # ---- uscita comandi
    def _emetti(self, c: Comandi, io, opp, d) -> None:
        t = self.t
        guardia = t < self.guardia_fino and self.tasti.get('schivata', 0) <= 0
        if not guardia and self.seg:
            s = self.seg[0]
            dxc, dzc = s[0], s[1]
            if dxc == 'C':
                dx = 1 if C.RING_LARGHEZZA / 2 > io.x else -1
            else:
                dx = dxc * d.fw
            if dzc == 'A':
                dz = _segno(d.dz) if abs(d.dz) > max(8.0, self.p.allinea_z * 0.35) else 0
            else:
                dz = dzc
            c.destra = dx > 0
            c.sinistra = dx < 0
            c.su = dz > 0
            c.giu = dz < 0
            s[2] -= 1
            if s[2] <= 0:
                self.seg.pop(0)
        if guardia:
            c.guardia = True
        for b in _PULSANTI:
            if b == 'guardia':
                continue
            n = self.tasti.get(b, 0)
            if n > 0:
                setattr(c, b, True)
                self.tasti[b] = n - 1
                if n - 1 == 0:
                    self.raff[b] = 2
            elif self.raff.get(b, 0) > 0:
                self.raff[b] -= 1


class IA:
    """Avversario CPU. Una istanza puo' guidare uno o entrambi i lottatori."""

    DIFFICOLTA = ('facile', 'normale', 'difficile', 'campione')

    def __init__(self, difficolta: str = 'normale', seme: Optional[int] = None):
        if difficolta not in self.DIFFICOLTA:
            raise ValueError("difficolta' sconosciuta: %r" % (difficolta,))
        self.difficolta = difficolta
        self.seme = seme
        self._livello = SimpleNamespace(**_LIVELLI[difficolta])
        self._rng = random.Random(seme)
        self._cervelli = {}

    def comandi(self, incontro, indice: int) -> Comandi:
        """Comandi del lottatore `indice` per il prossimo tick (da chiamare a ogni tick)."""
        cerv = self._cervelli.get(indice)
        if cerv is None:
            cerv = _Cervello(indice, self._livello, random.Random(self._rng.random()))
            self._cervelli[indice] = cerv
        return cerv.passo(incontro, incontro.lottatori[indice], incontro.lottatori[1 - indice])
