"""Lottatore: stato pubblico e macchina a stati di un singolo lottatore.

Le interazioni tra i due (colpi, spinte, collisioni, round) le gestisce
`Incontro`; qui c'e' la logica individuale: input bufferizzato, mosse,
schivate, movimento, stamina. Gli attributi pubblici sono il contratto
letto da renderer, HUD e IA (vedi SPEC).
"""

from __future__ import annotations

from typing import Optional

from .. import costanti as C
from .. import eventi as E
from ..comandi import Comandi
from ..personaggi import Personaggio
from . import regole as R
from .mosse import MOSSE, MOSSA_DA_PULSANTE, VARIANTE_RAVVICINATA, DISTANZA_RAVVICINATA

STATI = ('intro', 'guardia', 'cammina', 'attacco', 'parata', 'bloccato', 'colpito',
         'schivata', 'guardia_rotta', 'atterrato', 'rialzo', 'ko', 'vittoria', 'sconfitta')
STATI_NEUTRI = ('guardia', 'cammina', 'parata')
STATI_A_TERRA = ('atterrato', 'rialzo', 'ko')
PULSANTI_BUFFER = ('jab', 'diretto', 'calcio_basso', 'calcio_alto', 'speciale', 'schivata')
_PRIORITA = {p: i for i, p in enumerate(
    ('speciale', 'calcio_alto', 'calcio_basso', 'diretto', 'jab', 'schivata'))}
CHIAVI_STATISTICHE = ('colpi_tirati', 'colpi_a_segno', 'colpi_parati', 'danno_inflitto',
                      'combo_max', 'atterramenti_inflitti', 'schivate_riuscite')


class Lottatore:
    """Un lottatore sul ring. Costruibile anche da solo (anteprime, test del renderer)."""

    def __init__(self, indice: int, personaggio: Personaggio, palette_alternativa: bool = False,
                 x: Optional[float] = None, z: Optional[float] = None,
                 guarda_destra: Optional[bool] = None):
        self.indice = indice
        self.personaggio = personaggio
        self.palette_alternativa = palette_alternativa
        self.hw = C.LARGHEZZA_BASE / 2 * personaggio.corporatura
        self.altezza_mondo = C.ALTEZZA_BASE * personaggio.altezza
        self.vita_max = 100.0 * personaggio.resistenza
        self.stamina_max = 100.0 * personaggio.fiato
        self.energia = 0.0
        self.round_vinti = 0
        self.statistiche = {k: 0 for k in CHIAVI_STATISTICHE}
        self.statistiche['danno_inflitto'] = 0.0
        self.prepara_round(x, z, guarda_destra)

    # ---- round
    def prepara_round(self, x: Optional[float] = None, z: Optional[float] = None,
                      guarda_destra: Optional[bool] = None, stato: str = 'guardia',
                      durata: int = 0) -> None:
        """Rimette il lottatore in piedi a inizio round (vita e stamina piene)."""
        self.x = float(R.x_iniziale(self.indice) if x is None else x)
        self.z = float(R.Z_INIZIALE if z is None else z)
        self.h = 0.0
        self.guarda_destra = (self.indice == 0) if guarda_destra is None else bool(guarda_destra)
        self.vita = self.vita_max
        self.stamina = self.stamina_max
        self.atterramenti = 0
        self.combo = 0
        self.colpo_subito = None
        self.forza_colpo_subito = 0.0
        self.in_hitstop = False
        self.direzione_cammino = 0
        self.direzione_profondita = 0
        self._buffer = {}
        self._prec = Comandi()
        self._spinta_vx = 0.0
        self._spinta_decadimento = R.DECADIMENTO_SPINTA
        self._vx = 0.0
        self._vz = 0.0
        self._x_prec = self.x
        self._frame_senza_attacco = 0
        self._schivata_riuscita = False
        self._x0_schivata = self.x
        self._z0_schivata = self.z
        self._dir_schivata = (0, 0)
        self._dist_schivata = 0.0
        self._avanz_frame = 0.0
        self._catena = []
        self.schivata_stanca = False
        self.imposta_stato(stato, durata)
        self.aggiorna_indicatori()

    # ---- stato
    def imposta_stato(self, stato: str, durata: int = 0) -> None:
        """Entra in `stato` da frame 0 (usabile anche per anteprime).

        Per 'attacco' usa imposta_mossa (qui si ripiega sulla mossa corrente o sul jab).
        """
        if stato not in STATI:
            raise ValueError("stato sconosciuto: %r" % (stato,))
        if stato == 'attacco':
            self.imposta_mossa(self.mossa or 'jab')
            return
        self._entra(stato, durata)

    def _entra(self, stato: str, durata: int) -> None:
        self.stato = stato
        self.frame_stato = 0
        self.durata_stato = int(durata)
        if stato != 'attacco':
            self.mossa = None
            self.fase_mossa = None
            self.progresso_fase = 0.0
            self.progresso_mossa = 0.0
            self.punto_impatto = None
            self.mossa_stanca = False
            self._contatto = False
        if stato != 'schivata':
            self.tipo_schivata = None
            self.schivata_stanca = False

    def imposta_mossa(self, nome: str, frame_stato: int = 0, stanca: bool = False) -> None:
        """Mette il lottatore in una mossa a un certo frame (anteprime/test)."""
        m = MOSSE[nome]
        self._entra('attacco', m.durata + (R.RECUPERO_STANCO if stanca else 0))
        self.tipo_schivata = None
        self.mossa = nome
        self.mossa_stanca = stanca
        self._contatto = False
        self.punto_impatto = None
        self._avanz_frame = m.avanzamento / max(1, m.avvio + m.attivo)
        self.frame_stato = max(0, min(int(frame_stato), self.durata_stato - 1))
        self._aggiorna_fase()

    def _torna_neutro(self) -> None:
        self.imposta_stato('guardia')

    def _aggiorna_fase(self) -> None:
        m = MOSSE[self.mossa]
        f = self.frame_stato
        fine_attivo = m.avvio + m.attivo
        recupero = max(1, self.durata_stato - fine_attivo)
        if f < m.avvio:
            self.fase_mossa = 'avvio'
            self.progresso_fase = (f + 1) / m.avvio
        elif f < fine_attivo:
            self.fase_mossa = 'attivo'
            self.progresso_fase = (f - m.avvio + 1) / m.attivo
        else:
            self.fase_mossa = 'recupero'
            self.progresso_fase = min(1.0, (f - fine_attivo + 1) / recupero)
        self.progresso_mossa = min(1.0, (f + 1) / max(1, self.durata_stato))

    # ---- proprieta' utili (IA, renderer)
    @property
    def neutro(self) -> bool:
        return self.stato in STATI_NEUTRI

    @property
    def a_terra(self) -> bool:
        return self.stato in STATI_A_TERRA

    @property
    def dati_mossa(self):
        return MOSSE[self.mossa] if self.mossa else None

    @property
    def fronte(self) -> float:
        return R.fronte(self)

    @property
    def contatto(self) -> bool:
        """True se la mossa corrente ha toccato (a segno o parata); in recupero senza
        contatto la mossa e' andata a vuoto (punibile)."""
        return self._contatto

    @property
    def in_finestra_cancel(self) -> bool:
        """True se in questo momento una pressione bufferizzata puo' concatenare."""
        return self.stato == 'attacco' and self._puo_cancellare()

    @property
    def super_pronto(self) -> bool:
        return self.energia >= MOSSE[MOSSA_DA_PULSANTE['speciale']].costo_super

    def portata_effettiva(self, nome_mossa: str) -> float:
        return R.portata_effettiva(self, nome_mossa)

    def e_invulnerabile(self) -> bool:
        s = self.stato
        if s in STATI_A_TERRA:
            return True
        if s == 'schivata' and not self.schivata_stanca:
            a, b = (R.INVULNERABILE_LATERALE if self.tipo_schivata == 'laterale'
                    else R.INVULNERABILE_INDIETRO)
            return a <= self.frame_stato <= b
        return False

    def mossa_per_pulsante(self, pulsante: str, avversario=None) -> str:
        """Mossa che partirebbe premendo `pulsante` (variante ravvicinata inclusa)."""
        base = MOSSA_DA_PULSANTE[pulsante]
        if avversario is not None and pulsante in VARIANTE_RAVVICINATA:
            if (R.davanti(self, avversario)
                    and abs(avversario.z - self.z) <= R.TOLLERANZA_Z
                    and R.distanza_fronti(self, avversario) < DISTANZA_RAVVICINATA):
                return VARIANTE_RAVVICINATA[pulsante]
        return base

    def aggiorna_indicatori(self) -> None:
        self.invulnerabile = self.e_invulnerabile()
        self.affannato = self.stamina < R.SOGLIA_AFFANNO * self.stamina_max

    # ---- input
    def registra_comandi(self, c: Comandi, bufferizza: bool = True) -> None:
        """Ricava i fronti di salita e li mette nel buffer (anche durante l'hitstop)."""
        prec = self._prec
        if bufferizza:
            for p in PULSANTI_BUFFER:
                if getattr(c, p) and not getattr(prec, p):
                    self._buffer[p] = R.BUFFER_INPUT
        self._prec = c.copia()

    def scala_buffer(self) -> None:
        for p in list(self._buffer):
            self._buffer[p] -= 1
            if self._buffer[p] <= 0:
                del self._buffer[p]

    def svuota_buffer(self) -> None:
        self._buffer.clear()

    def _scegli_dal_buffer(self, avversario, cancel: bool = False):
        """(pulsante, mossa|None) piu' recente eseguibile, o None."""
        ordine = sorted(self._buffer.items(), key=lambda kv: (-kv[1], _PRIORITA[kv[0]]))
        for p, _ in ordine:
            if p == 'schivata':
                if not cancel:
                    return p, None
                continue
            base = MOSSA_DA_PULSANTE[p]
            if MOSSE[base].costo_super > self.energia:
                del self._buffer[p]
                continue
            eff = self.mossa_per_pulsante(p, avversario)
            if cancel and not self._cancel_ammesso(base, eff):
                continue
            return p, eff
        return None

    def _cancel_ammesso(self, base: str, eff: str) -> bool:
        cancella_in = MOSSE[self.mossa].cancella_in
        if base not in cancella_in and eff not in cancella_in:
            return False
        return (len(self._catena) < R.LUNGHEZZA_MAX_CATENA
                and self._catena.count(eff) < R.RIPETIZIONI_MAX_CATENA)

    # ---- passo di simulazione (chiamato da Incontro)
    def avanza_stato(self, eventi: list) -> None:
        """Avanza di un frame il timer dello stato e gestisce le transizioni a tempo."""
        self.frame_stato += 1
        s = self.stato
        if s == 'attacco':
            fase_prec = self.fase_mossa
            if self.frame_stato >= self.durata_stato:
                self._torna_neutro()
                return
            self._aggiorna_fase()
            if fase_prec == 'attivo' and self.fase_mossa == 'recupero' and not self._contatto:
                eventi.append(E.Mancato(self.indice, self.mossa))
        elif s in ('colpito', 'bloccato', 'schivata'):
            if self.frame_stato >= self.durata_stato:
                self._torna_neutro()
        elif s == 'guardia_rotta':
            if self.frame_stato >= self.durata_stato:
                self.stamina = max(self.stamina, R.STAMINA_DOPO_GUARDIA_ROTTA * self.stamina_max)
                self._torna_neutro()
        elif s == 'atterrato':
            f = self.frame_stato - R.PRIMO_CONTEGGIO
            if f >= 0 and f % R.INTERVALLO_CONTEGGIO == 0 and self.frame_stato < self.durata_stato:
                eventi.append(E.ConteggioArbitro(self.indice, f // R.INTERVALLO_CONTEGGIO + 1))
            if self.frame_stato >= self.durata_stato:
                self.imposta_stato('rialzo', R.DURATA_RIALZO)
                eventi.append(E.Rialzo(self.indice))
        elif s == 'rialzo':
            if self.frame_stato >= self.durata_stato:
                self._torna_neutro()

    def applica_comandi(self, c: Comandi, avversario, eventi: list) -> None:
        """Decide l'azione del frame: attacco, cancel, schivata, parata o cammino."""
        self._vx = 0.0
        self._vz = 0.0
        s = self.stato
        if s != 'schivata':
            self.direzione_cammino = 0
            self.direzione_profondita = 0
        if s == 'attacco':
            if self._puo_cancellare():
                scelta = self._scegli_dal_buffer(avversario, cancel=True)
                if scelta is not None:
                    del self._buffer[scelta[0]]
                    self._inizia_mossa(scelta[1], eventi, cancel=True)
            return
        if s not in STATI_NEUTRI:
            return
        scelta = self._scegli_dal_buffer(avversario)
        if scelta is not None:
            del self._buffer[scelta[0]]
            if scelta[0] == 'schivata':
                self._inizia_schivata(c, eventi)
            else:
                self._inizia_mossa(scelta[1], eventi)
            return
        if c.guardia:
            if s != 'parata':
                self.imposta_stato('parata')
            return
        ix = int(c.destra) - int(c.sinistra)
        iz = int(c.su) - int(c.giu)
        if ix == 0 and iz == 0:
            if s != 'guardia':
                self.imposta_stato('guardia')
            return
        if s != 'cammina':
            self.imposta_stato('cammina')
        rel = ix * R.verso(self)
        v = R.VELOCITA_CAMMINO * self.personaggio.velocita
        if rel < 0:
            v *= R.FATTORE_INDIETRO
        vz = R.VELOCITA_PROFONDITA * self.personaggio.velocita
        if self.affannato:
            v *= R.FATTORE_AFFANNATO
            vz *= R.FATTORE_AFFANNATO
        if ix and iz:
            v *= R.FATTORE_DIAGONALE
            vz *= R.FATTORE_DIAGONALE
        self._vx = ix * v
        self._vz = iz * vz
        self.direzione_cammino = rel
        self.direzione_profondita = iz

    def _puo_cancellare(self) -> bool:
        if not self._contatto or not self.mossa:
            return False
        m = MOSSE[self.mossa]
        fine_attivo = m.avvio + m.attivo
        return fine_attivo - 1 <= self.frame_stato < fine_attivo + R.FINESTRA_CANCEL

    def _inizia_mossa(self, nome: str, eventi: list, cancel: bool = False) -> None:
        m = MOSSE[nome]
        if cancel:
            self._catena.append(nome)
        else:
            self._catena = [nome]
        stanca = self.stamina < m.stamina
        self.stamina = max(0.0, self.stamina - m.stamina)
        if m.costo_super > 0:
            self.energia = max(0.0, self.energia - m.costo_super)
        self.imposta_mossa(nome, 0, stanca)
        self._frame_senza_attacco = 0
        self.statistiche['colpi_tirati'] += 1
        eventi.append(E.AttaccoIniziato(self.indice, nome))

    def _inizia_schivata(self, c: Comandi, eventi: list) -> None:
        iz = int(c.su) - int(c.giu)
        stanca = self.stamina < R.COSTO_SCHIVATA
        if iz != 0:
            tipo = 'laterale'
            durata = R.DURATA_SCHIVATA_LATERALE
            dist = R.DISTANZA_SCHIVATA_LATERALE * self.personaggio.velocita
            # contro il bordo del ring si schiva dall'altra parte
            spazio = (R.Z_MAX - self.z) if iz > 0 else (self.z - R.Z_MIN)
            opposto = (self.z - R.Z_MIN) if iz > 0 else (R.Z_MAX - self.z)
            if spazio < 0.4 * dist and opposto > spazio:
                iz = -iz
            self._dir_schivata = (0, iz)
        else:
            tipo = 'indietro'
            durata = R.DURATA_SCHIVATA_INDIETRO
            dist = R.DISTANZA_SCHIVATA_INDIETRO * self.personaggio.velocita
            self._dir_schivata = (-R.verso(self), 0)
        self._dist_schivata = dist * (R.DISTANZA_SCHIVATA_STANCA if stanca else 1.0)
        self.stamina = max(0.0, self.stamina - R.COSTO_SCHIVATA)
        self._frame_senza_attacco = 0
        self._x0_schivata = self.x
        self._z0_schivata = self.z
        self._schivata_riuscita = False
        self.imposta_stato('schivata', durata)
        self.tipo_schivata = tipo
        self.schivata_stanca = stanca
        self.direzione_cammino = -1 if tipo == 'indietro' else 0
        self.direzione_profondita = iz
        eventi.append(E.Schivata(self.indice, tipo, False))

    def spostamento(self) -> tuple:
        """(dx, dz) volontario del frame: cammino, avanzamento della mossa, schivata."""
        s = self.stato
        if s == 'cammina':
            return self._vx, self._vz
        if s == 'attacco':
            if self.fase_mossa in ('avvio', 'attivo') and not self._contatto:
                return R.verso(self) * self._avanz_frame, 0.0
            return 0.0, 0.0
        if s == 'schivata':
            durata_moto = max(1.0, self.durata_stato * R.FRAZIONE_MOTO_SCHIVATA)
            t0 = min(1.0, self.frame_stato / durata_moto)
            t1 = min(1.0, (self.frame_stato + 1) / durata_moto)
            d = self._dist_schivata * ((1 - (1 - t1) ** 2) - (1 - (1 - t0) ** 2))
            return self._dir_schivata[0] * d, self._dir_schivata[1] * d
        return 0.0, 0.0

    def fine_passo(self, avversario, eventi: list) -> None:
        """Orientamento, reset combo, stamina, passi: a fine frame di simulazione."""
        if self.stato in STATI_NEUTRI or self.stato == 'intro':
            dx = avversario.x - self.x
            if abs(dx) > 0.5:
                self.guarda_destra = dx > 0
        if avversario.stato != 'colpito':
            self.combo = 0
        if self.stato in ('attacco', 'schivata'):
            self._frame_senza_attacco = 0
        else:
            self._frame_senza_attacco += 1
            if self._frame_senza_attacco >= R.RITARDO_RIGENERAZIONE:
                rigen = R.RIGENERAZIONE_STAMINA * self.personaggio.fiato
                if self.stato in ('parata', 'bloccato'):
                    rigen *= R.FATTORE_RIGENERAZIONE_PARATA
                self.stamina = min(self.stamina_max, self.stamina + rigen)
        if self.stato == 'cammina' and self.frame_stato % R.INTERVALLO_PASSO == R.FASE_PASSO:
            eventi.append(E.Passo(self.indice))

    def __repr__(self) -> str:
        return ("Lottatore(%d %s %s f=%d x=%.1f z=%.1f vita=%.1f sta=%.1f en=%.1f)"
                % (self.indice, self.personaggio.id, self.stato, self.frame_stato,
                   self.x, self.z, self.vita, self.stamina, self.energia))
