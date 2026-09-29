"""Incontro: due lottatori, round, colpi, spinte, collisioni e fasi della partita.

`Incontro.aggiorna(c1, c2)` avanza la simulazione di UN tick a 60 Hz e
restituisce gli eventi del tick. Tutto e' deterministico: nessun random.
"""

from __future__ import annotations

from typing import Optional

from .. import costanti as C
from .. import eventi as E
from ..comandi import Comandi
from ..personaggi import Personaggio
from . import regole as R
from .lottatore import Lottatore, STATI_A_TERRA
from .mosse import MOSSE

FASI = ('presentazione', 'combattimento', 'fine_round', 'fine_partita')
_VUOTI = (Comandi(), Comandi())


class _Colpo:
    """Fotografia di un colpo che tocca, presa prima di applicare qualunque effetto."""
    __slots__ = ('att', 'dif', 'nome', 'stanca', 'contro', 'parato', 'in_hitstun',
                 'punto', 'verso')

    def __init__(self, att, dif, parato: bool):
        self.att = att
        self.dif = dif
        self.nome = att.mossa
        self.stanca = att.mossa_stanca
        self.contro = (not parato and dif.stato == 'attacco'
                       and dif.fase_mossa in ('avvio', 'recupero'))
        self.parato = parato
        self.in_hitstun = dif.stato == 'colpito'
        self.punto = R.punto_impatto(att, dif, att.mossa)
        dx = dif.x - att.x
        self.verso = (1 if dx > 0 else -1) if abs(dx) > 1.0 else R.verso(att)


class Incontro:
    """Una partita tra due personaggi (al meglio di 2*round_per_vincere-1 round)."""

    def __init__(self, pers1: Personaggio, pers2: Personaggio,
                 round_per_vincere: int = C.ROUND_PER_VINCERE,
                 durata_round: int = C.DURATA_ROUND):
        speculare = pers1.id == pers2.id
        self.lottatori = [Lottatore(0, pers1), Lottatore(1, pers2, palette_alternativa=speculare)]
        self.round_per_vincere = int(round_per_vincere)
        self.durata_round = durata_round
        self.numero_round = 1
        self.storico_round = []
        self.vincitore_partita = None
        self.frame = 0
        self._prepara_round()

    # ---- utilita' pubbliche
    def avversario(self, indice: int) -> Lottatore:
        return self.lottatori[1 - indice]

    @property
    def in_corso(self) -> bool:
        return self.fase != 'fine_partita'

    @property
    def round_massimi(self) -> int:
        """Round oltre i quali decide il danno totale inflitto."""
        return max(R.MAX_ROUND, 2 * self.round_per_vincere - 1)

    # ---- round
    def _prepara_round(self) -> None:
        self.fase = 'presentazione'
        self.frame_fase = 0
        self._frame_round = 0
        self.tempo_rimasto = float(self.durata_round)
        self.vincitore_round = None
        self.motivo_fine_round = None
        self.hitstop = 0
        self.rallentatore = 1.0
        self._ralenti_rimasti = 0
        self._accumulo = 0.0
        self._pose_fatte = False
        self._inizio_annunciato = False
        self._lato = 1
        for l in self.lottatori:
            l.prepara_round(R.x_iniziale(l.indice), R.Z_INIZIALE, l.indice == 0,
                            stato='intro', durata=R.DURATA_PRESENTAZIONE)

    # ---- tick
    def aggiorna(self, c1: Optional[Comandi], c2: Optional[Comandi]) -> list:
        """Un tick a 60 Hz. Restituisce la lista degli eventi emessi."""
        eventi = []
        self.frame += 1
        comandi = (c1 if c1 is not None else _VUOTI[0], c2 if c2 is not None else _VUOTI[1])
        attivo = self.fase == 'combattimento'
        for l, c in zip(self.lottatori, comandi):
            l.registra_comandi(c, bufferizza=attivo)
        if self.fase == 'presentazione':
            self._tick_presentazione(eventi)
        elif self.fase == 'combattimento':
            self._tick_combattimento(comandi, eventi)
        elif self.fase == 'fine_round':
            self._tick_fine_round(eventi)
        else:
            self.frame_fase += 1
            for l in self.lottatori:
                l.in_hitstop = False
            self._passo(_VUOTI, eventi, controllo=False)
        for l in self.lottatori:
            l.aggiorna_indicatori()
        return eventi

    def _tick_presentazione(self, eventi: list) -> None:
        if self.frame_fase == 0 and not self._inizio_annunciato:
            eventi.append(E.InizioRound(self.numero_round))
        self._inizio_annunciato = False
        self.frame_fase += 1
        a, b = self.lottatori
        for l, o in ((a, b), (b, a)):
            l.in_hitstop = False
            l.avanza_stato(eventi)
            l.fine_passo(o, eventi)
        if self.frame_fase >= R.DURATA_PRESENTAZIONE:
            self.fase = 'combattimento'
            self.frame_fase = 0
            for l in self.lottatori:
                l.imposta_stato('guardia')
                l.svuota_buffer()
            eventi.append(E.Via(self.numero_round))

    def _tick_combattimento(self, comandi, eventi: list) -> None:
        self.frame_fase += 1
        if self.hitstop > 0:
            self.hitstop -= 1
            for l in self.lottatori:
                l.in_hitstop = True
            return
        self._passo(comandi, eventi, controllo=True)
        for l in self.lottatori:
            l.in_hitstop = self.hitstop > 0
        if self.fase != 'combattimento':
            return
        if not any(l.stato in ('atterrato', 'rialzo') for l in self.lottatori):
            self._frame_round += 1
            self.tempo_rimasto = max(0.0, self.durata_round - self._frame_round / C.FPS)
            if self._frame_round >= self.durata_round * C.FPS:
                self.tempo_rimasto = 0.0
                self._decisione_ai_punti(eventi)

    def _tick_fine_round(self, eventi: list) -> None:
        self.frame_fase += 1
        if self.hitstop > 0:
            self.hitstop -= 1
            for l in self.lottatori:
                l.in_hitstop = True
        else:
            for l in self.lottatori:
                l.in_hitstop = False
            if self._ralenti_rimasti > 0:
                self._ralenti_rimasti -= 1
                self._accumulo += self.rallentatore
                if self._accumulo >= 1.0:
                    self._accumulo -= 1.0
                    self._passo(_VUOTI, eventi, controllo=False)
                if self._ralenti_rimasti == 0:
                    self.rallentatore = 1.0
            else:
                self._passo(_VUOTI, eventi, controllo=False)
            if (not self._pose_fatte and self._ralenti_rimasti == 0
                    and (self.motivo_fine_round in ('ko', 'tko')
                         or self.frame_fase >= R.TICK_POSE_PUNTI)):
                self._assegna_pose()
        if self.frame_fase >= R.DURATA_FINE_ROUND:
            self._chiudi_round(eventi)

    # ---- passo di simulazione dei lottatori
    def _passo(self, comandi, eventi: list, controllo: bool) -> None:
        a, b = self.lottatori
        coppie = ((a, b), (b, a))
        for l in self.lottatori:
            l.avanza_stato(eventi)
        for (l, o), c in zip(coppie, comandi):
            l.applica_comandi(c if controllo else _VUOTI[l.indice], o, eventi)
        self._muovi()
        self._vincoli()
        if controllo:
            self._colpi(eventi)
        for l, o in coppie:
            l.fine_passo(o, eventi)
            if controllo:
                l.scala_buffer()

    def _muovi(self) -> None:
        a, b = self.lottatori
        for l in self.lottatori:
            l._x_prec = l.x
            dx, dz = l.spostamento()
            l.x += dx
            l.z += dz
        for l, o in ((a, b), (b, a)):
            v = l._spinta_vx
            if v == 0.0:
                continue
            prima = l.x
            l.x += v
            self._limita_x(l)
            resto = v - (l.x - prima)
            if abs(resto) > 1e-9:
                # alle corde: il resto della spinta fa arretrare l'altro
                o.x -= resto
                self._limita_x(o)
            v *= l._spinta_decadimento
            l._spinta_vx = v if abs(v) > 0.05 else 0.0

    # ---- vincoli: ring, distanze, compenetrazioni
    @staticmethod
    def _limita_x(l) -> float:
        lo, hi = R.limiti_x(l.hw)
        nx = min(max(l.x, lo), hi)
        r = nx - l.x
        l.x = nx
        return r

    @staticmethod
    def _limita_z(l) -> float:
        nz = min(max(l.z, R.Z_MIN), R.Z_MAX)
        r = nz - l.z
        l.z = nz
        return r

    def _vincoli(self) -> None:
        for l in self.lottatori:
            self._limita_x(l)
            self._limita_z(l)
        self._distanza_arbitro()
        self._distanza_massima()
        self._separa()
        a, b = self.lottatori
        if abs(b.x - a.x) > 0.5:
            self._lato = 1 if b.x > a.x else -1

    def _separa(self) -> None:
        a, b = self.lottatori
        dx = b.x - a.x
        dz = b.z - a.z
        wx = a.hw + b.hw
        if abs(dz) >= R.SEPARAZIONE_Z or abs(dx) >= wx:
            return
        px = wx - abs(dx)
        pz = R.SEPARAZIONE_Z - abs(dz)
        if pz < px and abs(dz) > 1e-6 and self._separa_z(a, b, pz, 1 if dz > 0 else -1):
            return
        s = (1 if dx > 0 else -1) if abs(dx) > 1e-6 else self._lato
        meta = px / 2
        a.x -= s * meta
        b.x += s * meta
        b.x += self._limita_x(a)
        a.x += self._limita_x(b)
        self._limita_x(a)

    def _separa_z(self, a, b, pz: float, s: int) -> bool:
        za, zb = a.z, b.z
        a.z -= s * pz / 2
        b.z += s * pz / 2
        b.z += self._limita_z(a)
        a.z += self._limita_z(b)
        self._limita_z(a)
        if abs(b.z - a.z) >= R.SEPARAZIONE_Z - 1e-6:
            return True
        a.z, b.z = za, zb      # bloccati dai limiti in z: si separa in x
        return False

    def _distanza_massima(self) -> None:
        a, b = self.lottatori
        dx = b.x - a.x
        eccesso = abs(dx) - C.DISTANZA_MAX
        if eccesso <= 0:
            return
        s = 1 if dx > 0 else -1
        va = max(0.0, -(a.x - a._x_prec) * s)
        vb = max(0.0, (b.x - b._x_prec) * s)
        tot = va + vb
        qa, qb = ((eccesso * va / tot, eccesso * vb / tot) if tot > 1e-9
                  else (eccesso / 2, eccesso / 2))
        a.x += s * qa
        b.x -= s * qb
        self._limita_x(a)
        self._limita_x(b)

    def _distanza_arbitro(self) -> None:
        """Durante atterramento e rialzo l'arbitro tiene lontano chi e' in piedi."""
        a, b = self.lottatori
        for giu, su in ((a, b), (b, a)):
            if giu.stato not in ('atterrato', 'rialzo') or su.stato in STATI_A_TERRA:
                continue
            dx = su.x - giu.x
            manca = R.DISTANZA_RIALZO - abs(dx)
            if manca <= 0:
                continue
            s = (1 if dx > 0 else -1) if abs(dx) > 1e-6 else (-1 if su.guarda_destra else 1)
            su.x += s * min(manca, R.VELOCITA_SEPARAZIONE)
            resto = self._limita_x(su)
            if giu.stato == 'rialzo' and abs(resto) > 1e-9:
                giu.x += resto
                self._limita_x(giu)

    # ---- colpi
    def _colpi(self, eventi: list) -> None:
        a, b = self.lottatori
        colpi = []
        for att, dif in ((a, b), (b, a)):
            if att.stato != 'attacco' or att.fase_mossa != 'attivo' or att._contatto:
                continue
            raggiunge = R.colpo_raggiunge(att, dif, att.mossa)
            if dif.e_invulnerabile():
                if dif.stato == 'schivata' and not dif._schivata_riuscita and (
                        raggiunge or R.colpo_raggiunge(att, dif, att.mossa,
                                                       dif._x0_schivata, dif._z0_schivata)):
                    self._registra_schivata(dif, eventi)
                continue
            if not raggiunge:
                continue
            parato = dif.stato in ('parata', 'bloccato') and R.davanti(dif, att)
            colpi.append(_Colpo(att, dif, parato))
        if not colpi:
            return
        caduti = []
        for colpo in colpi:
            self._applica_colpo(colpo, eventi, caduti)
        if caduti:
            for l, tecnico in caduti:
                eventi.append(E.KO(l.indice, tecnico))
            self.hitstop = max(self.hitstop, R.HITSTOP_KO)
            if len(caduti) == 2:
                self._fine_round(None, 'pareggio', eventi, da_ko=True)
            else:
                l, tecnico = caduti[0]
                self._fine_round(1 - l.indice, 'tko' if tecnico else 'ko', eventi, da_ko=True)

    def _applica_colpo(self, colpo: _Colpo, eventi: list, caduti: list) -> None:
        att, dif = colpo.att, colpo.dif
        m = MOSSE[colpo.nome]
        base = m.danno * att.personaggio.potenza
        if colpo.stanca:
            base *= R.DANNO_STANCO
        if colpo.parato:
            danno = base * R.fattore_parata(colpo.nome)
            numero_combo = 0
            forza = R.forza_da_danno(base) * R.FORZA_PARATA
        else:
            if colpo.contro:
                base *= R.MOLTIPLICATORE_CONTRO
            numero_combo = att.combo + 1 if colpo.in_hitstun else 1
            danno = base * R.scaling_combo(numero_combo)
            forza = R.forza_da_danno(danno)
            att.combo = numero_combo
            att.statistiche['combo_max'] = max(att.statistiche['combo_max'], numero_combo)
            att.statistiche['colpi_a_segno'] += 1
        # la parata non manda mai KO: il danno residuo lascia almeno VITA_MINIMA_PARATA
        limite = max(0.0, dif.vita - R.VITA_MINIMA_PARATA) if colpo.parato else dif.vita
        danno = max(0.0, min(danno, limite))
        dif.vita = max(0.0, dif.vita - danno)
        att.statistiche['danno_inflitto'] += danno
        att._contatto = True
        att.punto_impatto = colpo.punto
        if not colpo.parato:
            dif.guarda_destra = colpo.verso < 0     # chi viene colpito si gira verso l'attaccante
        dif.colpo_subito = m.livello
        dif.forza_colpo_subito = forza
        x, z, h = colpo.punto
        eventi.append(E.ColpoASegno(att.indice, dif.indice, colpo.nome, danno, colpo.parato,
                                    colpo.contro, numero_combo, m.livello, forza, x, z, h))
        self._aggiungi_energia(att, danno * R.ENERGIA_DANNO_INFLITTO, eventi)
        self._aggiungi_energia(dif, danno * R.ENERGIA_DANNO_SUBITO, eventi)
        spinta = m.spinta
        decadimento = R.DECADIMENTO_SPINTA
        if colpo.parato:
            dif.statistiche['colpi_parati'] += 1
            dif.stamina -= R.costo_parata(colpo.nome)
            if dif.stamina <= 0:
                dif.stamina = 0.0
                dif.imposta_stato('guardia_rotta', R.DURATA_GUARDIA_ROTTA)
                eventi.append(E.GuardiaRotta(dif.indice))
            else:
                dif.imposta_stato('bloccato', m.stordimento_parata)
            spinta *= R.FATTORE_SPINTA_PARATA
            self.hitstop = max(self.hitstop, m.hitstop)
        else:
            atterra = m.atterra == 'sempre' or (m.atterra == 'contro' and colpo.contro)
            if dif.vita <= 0 or atterra:
                spinta *= R.FATTORE_SPINTA_ATTERRAMENTO
                decadimento = R.DECADIMENTO_SPINTA_CADUTA
            if dif.vita <= 0:
                dif.imposta_stato('ko')
                caduti.append((dif, False))
            elif atterra:
                dif.atterramenti += 1
                att.statistiche['atterramenti_inflitti'] += 1
                if dif.atterramenti >= C.ATTERRAMENTI_TKO:
                    dif.imposta_stato('ko')
                    caduti.append((dif, True))
                else:
                    dif.imposta_stato('atterrato', R.DURATA_ATTERRATO)
                    eventi.append(E.Atterramento(dif.indice, dif.atterramenti))
            else:
                dif.imposta_stato('colpito',
                                  m.stordimento + (R.HITSTUN_CONTRO if colpo.contro else 0))
            self.hitstop = max(self.hitstop, m.hitstop + (R.HITSTOP_CONTRO if colpo.contro else 0))
        dif._spinta_vx = colpo.verso * spinta * (1.0 - decadimento)
        dif._spinta_decadimento = decadimento

    def _registra_schivata(self, l: Lottatore, eventi: list) -> None:
        l._schivata_riuscita = True
        l.statistiche['schivate_riuscite'] += 1
        eventi.append(E.Schivata(l.indice, l.tipo_schivata, True))
        self._aggiungi_energia(l, R.ENERGIA_SCHIVATA, eventi)

    @staticmethod
    def _aggiungi_energia(l: Lottatore, quanto: float, eventi: list) -> None:
        if quanto <= 0:
            return
        prima = l.energia
        l.energia = min(C.ENERGIA_MAX, l.energia + quanto)
        if prima < C.ENERGIA_MAX <= l.energia:
            eventi.append(E.SuperPronto(l.indice))

    # ---- fine round / partita
    def _decisione_ai_punti(self, eventi: list) -> None:
        a, b = self.lottatori
        pa, pb = R.percentuale_vita(a), R.percentuale_vita(b)
        if abs(pa - pb) < 1e-9:
            self._fine_round(None, 'pareggio', eventi)
        else:
            self._fine_round(0 if pa > pb else 1, 'punti', eventi)

    def _fine_round(self, vincitore: Optional[int], motivo: str, eventi: list,
                    da_ko: bool = False) -> None:
        self.fase = 'fine_round'
        self.frame_fase = 0
        self.vincitore_round = vincitore
        self.motivo_fine_round = motivo
        self._pose_fatte = False
        if vincitore is not None:
            self.lottatori[vincitore].round_vinti += 1
        self.storico_round.append((vincitore, motivo))
        if da_ko:
            self.rallentatore = R.RALLENTATORE_KO
            self._ralenti_rimasti = R.DURATA_RALLENTATORE
            self._accumulo = 0.0
        for l in self.lottatori:
            l.combo = 0
            l.svuota_buffer()
        eventi.append(E.FineRound(self.numero_round, vincitore, motivo))

    def _assegna_pose(self) -> None:
        v = self.vincitore_round
        if v is None:
            self._pose_fatte = True
            return
        vinc, perd = self.lottatori[v], self.lottatori[1 - v]
        if vinc.stato in ('atterrato', 'rialzo'):
            return                      # prima si rialza, poi esulta
        vinc.imposta_stato('vittoria')
        if perd.stato != 'ko':
            perd.imposta_stato('sconfitta')
        self._pose_fatte = True

    def _chiudi_round(self, eventi: list) -> None:
        a, b = self.lottatori
        vincitore = None
        for l in self.lottatori:
            if l.round_vinti >= self.round_per_vincere:
                vincitore = l.indice
        if vincitore is None and self.numero_round >= self.round_massimi:
            vincitore = (1 if b.statistiche['danno_inflitto'] > a.statistiche['danno_inflitto']
                         else 0)
        if vincitore is None:
            self.numero_round += 1
            self._prepara_round()
            # annunciato subito: in questo tick i lottatori sono gia' in posizione
            eventi.append(E.InizioRound(self.numero_round))
            self._inizio_annunciato = True
            return
        self.fase = 'fine_partita'
        self.frame_fase = 0
        self.hitstop = 0
        self.rallentatore = 1.0
        self._ralenti_rimasti = 0
        self.vincitore_partita = vincitore
        vinc, perd = self.lottatori[vincitore], self.lottatori[1 - vincitore]
        if vinc.stato != 'vittoria':
            vinc.imposta_stato('vittoria')
        if perd.stato not in ('ko', 'sconfitta'):
            perd.imposta_stato('sconfitta')
        eventi.append(E.FinePartita(vincitore))
