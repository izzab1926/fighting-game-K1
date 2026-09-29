"""Test della simulazione: movimento, colpi, parate, combo, schivate, round."""

from __future__ import annotations

import math
import random

import pytest

from picchiaduro import costanti as C
from picchiaduro import eventi as E
from picchiaduro.comandi import Comandi
from picchiaduro.personaggi import ROSTER, personaggio
from picchiaduro.sim import regole as R
from picchiaduro.sim.incontro import Incontro
from picchiaduro.sim.lottatore import STATI, Lottatore
from picchiaduro.sim.mosse import DISTANZA_RAVVICINATA, MOSSE

VUOTO = Comandi()


# ---- utilita'

def nuovo(p1="toro", p2="toro", **kw) -> Incontro:
    inc = Incontro(personaggio(p1), personaggio(p2), **kw)
    salta_presentazione(inc)
    return inc


def salta_presentazione(inc: Incontro) -> list:
    ev = []
    while inc.fase == "presentazione":
        ev += inc.aggiorna(VUOTO, VUOTO)
    return ev


def piazza(inc: Incontro, gap: float = 40.0, x1: float = 700.0, z: float = 210.0,
           dz: float = 0.0) -> None:
    """P1 a sinistra che guarda a destra, P2 a `gap` di spazio libero tra i fronti."""
    a, b = inc.lottatori
    a.x, a.z = x1, z
    b.x, b.z = x1 + a.hw + b.hw + gap, z + dz
    a.guarda_destra, b.guarda_destra = True, False


def tick(inc: Incontro, c1: Comandi = None, c2: Comandi = None, n: int = 1) -> list:
    ev = []
    for _ in range(n):
        ev += inc.aggiorna(c1 or VUOTO, c2 or VUOTO)
    return ev


def comandi(*premuti, **tenuti) -> Comandi:
    c = Comandi(**tenuti)
    for p in premuti:
        setattr(c, p, True)
    return c


def premi(inc: Incontro, indice: int, pulsante: str, altro: Comandi = None, **tenuti) -> list:
    """Un tick con `pulsante` premuto dal lottatore `indice`."""
    c = comandi(pulsante, **tenuti)
    return tick(inc, c, altro) if indice == 0 else tick(inc, altro, c)


def fino_a(inc: Incontro, condizione, c1: Comandi = None, c2: Comandi = None,
           limite: int = 600) -> list:
    ev = []
    for _ in range(limite):
        if condizione(inc):
            return ev
        ev += inc.aggiorna(c1 or VUOTO, c2 or VUOTO)
    raise AssertionError("condizione non raggiunta in %d tick" % limite)


def di_tipo(eventi: list, tipo) -> list:
    return [e for e in eventi if isinstance(e, tipo)]


def controlla_invarianti(inc: Incontro) -> None:
    a, b = inc.lottatori
    for l in inc.lottatori:
        for v in (l.x, l.z, l.h, l.vita, l.stamina, l.energia, l.progresso_fase,
                  l.progresso_mossa, l.forza_colpo_subito):
            assert math.isfinite(v)
        lo, hi = R.limiti_x(l.hw)
        assert lo - 1e-6 <= l.x <= hi + 1e-6
        assert R.Z_MIN - 1e-6 <= l.z <= R.Z_MAX + 1e-6
        assert 0.0 <= l.vita <= l.vita_max
        assert 0.0 <= l.stamina <= l.stamina_max + 1e-9
        assert 0.0 <= l.energia <= C.ENERGIA_MAX
        assert l.stato in STATI
        assert 0.0 <= l.progresso_fase <= 1.0 and 0.0 <= l.progresso_mossa <= 1.0
        if l.stato == "attacco":
            assert l.mossa in MOSSE and l.fase_mossa in ("avvio", "attivo", "recupero")
        else:
            assert l.mossa is None and l.fase_mossa is None
    assert abs(a.x - b.x) <= C.DISTANZA_MAX + 1e-6
    if abs(a.z - b.z) < R.SEPARAZIONE_Z - 1e-6:
        assert abs(a.x - b.x) >= a.hw + b.hw - 1e-6


# ---- contratto

def test_attributi_del_contratto():
    l = Lottatore(0, personaggio("muro"))
    for nome in ("indice", "personaggio", "palette_alternativa", "x", "z", "h", "hw",
                 "altezza_mondo", "guarda_destra", "vita", "vita_max", "stamina",
                 "stamina_max", "energia", "stato", "frame_stato", "durata_stato", "mossa",
                 "fase_mossa", "progresso_fase", "progresso_mossa", "punto_impatto",
                 "direzione_cammino", "direzione_profondita", "tipo_schivata", "colpo_subito",
                 "forza_colpo_subito", "in_hitstop", "invulnerabile", "affannato",
                 "atterramenti", "round_vinti", "combo", "statistiche"):
        assert hasattr(l, nome), nome
    p = personaggio("muro")
    assert l.hw == pytest.approx(C.LARGHEZZA_BASE / 2 * p.corporatura)
    assert l.altezza_mondo == pytest.approx(C.ALTEZZA_BASE * p.altezza)
    assert l.vita_max == pytest.approx(100 * p.resistenza)
    assert l.stamina_max == pytest.approx(100 * p.fiato)
    assert set(l.statistiche) == {"colpi_tirati", "colpi_a_segno", "colpi_parati",
                                  "danno_inflitto", "combo_max", "atterramenti_inflitti",
                                  "schivate_riuscite"}
    assert STATI == ('intro', 'guardia', 'cammina', 'attacco', 'parata', 'bloccato', 'colpito',
                     'schivata', 'guardia_rotta', 'atterrato', 'rialzo', 'ko', 'vittoria',
                     'sconfitta')


def test_incontro_iniziale_e_speculare():
    inc = Incontro(personaggio("lama"), personaggio("lama"))
    assert inc.fase == "presentazione" and inc.numero_round == 1
    assert inc.round_per_vincere == C.ROUND_PER_VINCERE
    assert inc.tempo_rimasto == pytest.approx(C.DURATA_ROUND)
    a, b = inc.lottatori
    assert not a.palette_alternativa and b.palette_alternativa
    assert a.x < b.x and a.guarda_destra and not b.guarda_destra
    assert a.stato == b.stato == "intro"
    assert inc.hitstop == 0 and inc.rallentatore == 1.0 and inc.storico_round == []
    assert not Incontro(personaggio("lama"), personaggio("toro")).lottatori[1].palette_alternativa


def test_imposta_mossa_per_anteprime():
    l = Lottatore(1, personaggio("vento"))
    m = MOSSE["calcio_alto"]
    l.imposta_mossa("calcio_alto", m.avvio)
    assert l.stato == "attacco" and l.fase_mossa == "attivo"
    l.imposta_mossa("calcio_alto", 0)
    assert l.fase_mossa == "avvio"
    l.imposta_mossa("calcio_alto", m.durata - 1)
    assert l.fase_mossa == "recupero" and l.progresso_fase == pytest.approx(1.0)
    l.imposta_stato("colpito", 14)
    assert l.mossa is None and l.durata_stato == 14


# ---- movimento e limiti

def test_camminata_avanti_indietro_e_profondita():
    inc = nuovo("vento", "toro")
    a, b = inc.lottatori
    v = R.VELOCITA_CAMMINO * a.personaggio.velocita
    x0 = a.x
    tick(inc, comandi(destra=True), n=10)
    assert a.x - x0 == pytest.approx(10 * v)
    assert a.stato == "cammina" and a.direzione_cammino == 1
    x0 = a.x
    tick(inc, comandi(sinistra=True), n=10)
    assert x0 - a.x == pytest.approx(10 * v * R.FATTORE_INDIETRO)
    assert a.direzione_cammino == -1
    z0 = a.z
    tick(inc, comandi(su=True), n=10)
    assert a.z - z0 == pytest.approx(10 * R.VELOCITA_PROFONDITA * a.personaggio.velocita)
    assert a.direzione_profondita == 1
    z0 = a.z
    tick(inc, comandi(giu=True), n=5)
    assert a.z < z0 and a.direzione_profondita == -1
    tick(inc)
    assert a.stato == "guardia" and a.direzione_cammino == 0 and a.direzione_profondita == 0


def test_camminata_affannato_rallenta():
    inc = nuovo()
    a = inc.lottatori[0]
    a.stamina = 0.1 * a.stamina_max
    tick(inc)
    assert a.affannato
    x0 = a.x
    tick(inc, comandi(destra=True), n=10)
    atteso = 10 * R.VELOCITA_CAMMINO * a.personaggio.velocita * R.FATTORE_AFFANNATO
    assert a.x - x0 == pytest.approx(atteso)


def test_limiti_del_ring():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=200, x1=400)
    tick(inc, comandi(sinistra=True, giu=True), n=400)
    lo, _ = R.limiti_x(a.hw)
    assert a.x == pytest.approx(lo) and a.z == pytest.approx(R.Z_MIN)
    tick(inc, comandi(su=True), None, n=200)
    assert a.z == pytest.approx(R.Z_MAX)
    # P2 verso le corde di destra
    tick(inc, None, comandi(destra=True), n=400)
    _, hi = R.limiti_x(b.hw)
    assert b.x <= hi + 1e-9
    assert abs(b.x - a.x) <= C.DISTANZA_MAX + 1e-9


def test_distanza_massima():
    inc = nuovo()
    a, b = inc.lottatori
    for _ in range(300):
        tick(inc, comandi(sinistra=True), comandi(destra=True))
        assert abs(b.x - a.x) <= C.DISTANZA_MAX + 1e-9
    assert abs(b.x - a.x) == pytest.approx(C.DISTANZA_MAX)
    # chi sta fermo non viene trascinato se l'altro si allontana
    piazza(inc, gap=C.DISTANZA_MAX - a.hw - b.hw, x1=500)
    xb = b.x
    tick(inc, comandi(sinistra=True), n=5)
    assert b.x == pytest.approx(xb)
    assert abs(b.x - a.x) == pytest.approx(C.DISTANZA_MAX)


def test_corpi_non_si_compenetrano_e_si_spingono():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=10, dz=20)
    xb = b.x
    for _ in range(60):
        tick(inc, comandi(destra=True))
        assert b.x - a.x >= a.hw + b.hw - 1e-6
    assert b.x > xb + 20            # chi cammina spinge l'altro
    # se entrambi spingono, nessuno avanza
    xa, xb = a.x, b.x
    tick(inc, comandi(destra=True), comandi(sinistra=True), n=20)
    assert a.x == pytest.approx(xa, abs=1e-6) and b.x == pytest.approx(xb, abs=1e-6)


def test_sorpasso_in_profondita_inverte_orientamento():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40, z=120)
    b.z = 120 + 2 * R.SEPARAZIONE_Z
    tick(inc, comandi(destra=True), n=80)
    assert a.x > b.x
    assert not a.guarda_destra and b.guarda_destra
    # entrare in profondita' sopra l'altro non crea compenetrazione
    b.x = a.x + 10
    for _ in range(40):
        tick(inc, None, comandi(giu=True))
        controlla_invarianti(inc)


def test_orientamento_solo_negli_stati_neutri():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=200)
    premi(inc, 0, "calcio_alto")
    a.guarda_destra = True
    b.x = a.x - 300          # l'avversario "salta" dietro durante l'attacco
    b.z = a.z + 100
    tick(inc)
    assert a.stato == "attacco" and a.guarda_destra
    fino_a(inc, lambda i: a.stato == "guardia")
    tick(inc)
    assert not a.guarda_destra


def test_parata_e_ferma():
    inc = nuovo()
    a = inc.lottatori[0]
    x0 = a.x
    tick(inc, comandi(guardia=True, destra=True, su=True), n=10)
    assert a.stato == "parata" and a.x == x0
    tick(inc)
    assert a.stato == "guardia"


def test_eventi_passo():
    inc = nuovo()
    ev = tick(inc, comandi(destra=True), n=18 * 3)
    passi = di_tipo(ev, E.Passo)
    assert len(passi) == 3 and all(p.indice == 0 for p in passi)


# ---- colpi a segno e mancati

def test_jab_a_segno():
    inc = nuovo("toro", "vento")
    a, b = inc.lottatori
    piazza(inc, gap=50)
    ev = premi(inc, 0, "jab")
    assert di_tipo(ev, E.AttaccoIniziato) == [E.AttaccoIniziato(0, "jab")]
    assert a.stato == "attacco" and a.fase_mossa == "avvio"
    ev = tick(inc, n=MOSSE["jab"].avvio)
    colpi = di_tipo(ev, E.ColpoASegno)
    assert len(colpi) == 1
    c = colpi[0]
    m = MOSSE["jab"]
    assert c.attaccante == 0 and c.difensore == 1 and not c.parato and not c.contro
    assert c.danno == pytest.approx(m.danno * a.personaggio.potenza)
    assert c.combo == 1 and c.livello == "alto"
    assert c.h == pytest.approx(m.altezza_colpo * a.altezza_mondo)
    assert 0 < c.forza <= 1
    assert a.punto_impatto == (c.x, c.z, c.h)
    lo, hi = R.intervallo_colpo(a, "jab")
    assert lo <= c.x <= hi
    assert b.stato == "colpito" and b.durata_stato == m.stordimento
    assert b.colpo_subito == "alto" and b.forza_colpo_subito == pytest.approx(c.forza)
    assert b.vita == pytest.approx(b.vita_max - c.danno)
    assert inc.hitstop == m.hitstop
    assert a.in_hitstop and b.in_hitstop
    assert a.statistiche["colpi_a_segno"] == 1 and a.statistiche["colpi_tirati"] == 1
    # durante l'hitstop tutto e' congelato
    fa, fb, xb = a.frame_stato, b.frame_stato, b.x
    tick(inc, n=m.hitstop)
    assert (a.frame_stato, b.frame_stato, b.x) == (fa, fb, xb)
    tick(inc)
    assert not a.in_hitstop and b.x > xb        # la spinta parte dopo il congelamento


@pytest.mark.parametrize("dz,colpisce", [(0, True), (R.TOLLERANZA_Z - 1, True),
                                         (R.TOLLERANZA_Z + 5, False), (-80, False)])
def test_colpo_e_profondita(dz, colpisce):
    inc = nuovo()
    piazza(inc, gap=40, dz=dz)
    ev = premi(inc, 0, "diretto")
    ev += tick(inc, n=MOSSE["diretto"].durata + 20)
    assert bool(di_tipo(ev, E.ColpoASegno)) == colpisce
    assert bool(di_tipo(ev, E.Mancato)) != colpisce


def test_colpo_e_portata_del_personaggio():
    gap = 110          # jab: 95 * portata + avanzamento 10
    for pid, colpisce in (("lama", True), ("toro", False)):
        inc = nuovo(pid, "muro")
        piazza(inc, gap=gap)
        ev = premi(inc, 0, "jab") + tick(inc, n=30)
        assert bool(di_tipo(ev, E.ColpoASegno)) == colpisce, pid
        if not colpisce:
            assert di_tipo(ev, E.Mancato) == [E.Mancato(0, "jab")]


def test_chi_viene_colpito_si_gira_verso_l_attaccante():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    premi(inc, 1, "calcio_alto")          # P2 si impegna nel calcio...
    b.guarda_destra = True                # ...girato dalla parte sbagliata
    ev = premi(inc, 0, "jab") + tick(inc, n=6)
    assert di_tipo(ev, E.ColpoASegno)[0].attaccante == 0
    assert b.stato == "colpito" and not b.guarda_destra


def test_colpo_alle_spalle_non_tocca():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=30)
    b.x = a.x - a.hw - b.hw - 30          # dietro a P1
    b.z = a.z + 60
    premi(inc, 0, "jab")
    a.guarda_destra = True
    b.z = a.z
    ev = tick(inc, n=25)
    assert not di_tipo(ev, E.ColpoASegno)


# ---- parata

@pytest.mark.parametrize("mossa,chip", [("jab", R.DANNO_PARATA), ("calcio_alto", R.DANNO_PARATA),
                                        ("calcio_basso", R.DANNO_PARATA_BASSO)])
def test_parata_e_danno_residuo(mossa, chip):
    inc = nuovo("toro", "muro")
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
    guardia = comandi(guardia=True)
    tick(inc, None, guardia)
    stamina0 = b.stamina
    ev = premi(inc, 0, mossa, guardia) + tick(inc, None, guardia, n=MOSSE[mossa].avvio)
    colpi = di_tipo(ev, E.ColpoASegno)
    assert len(colpi) == 1 and colpi[0].parato and colpi[0].combo == 0
    base = MOSSE[mossa].danno * a.personaggio.potenza
    assert colpi[0].danno == pytest.approx(base * chip)
    assert b.stato == "bloccato" and b.durata_stato == MOSSE[mossa].stordimento_parata
    rigen = R.RIGENERAZIONE_STAMINA * b.personaggio.fiato      # recupero del frame stesso
    assert b.stamina == pytest.approx(stamina0 - R.costo_parata(mossa), abs=rigen + 1e-6)
    assert b.statistiche["colpi_parati"] == 1 and a.statistiche["colpi_a_segno"] == 0
    assert inc.hitstop == MOSSE[mossa].hitstop
    # la parata spinge
    xb = b.x
    tick(inc, None, guardia, n=inc.hitstop + 20)
    assert b.x > xb + MOSSE[mossa].spinta * 0.8
    assert b.stato == "parata"


def test_la_parata_non_manda_ko():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
    g = comandi(guardia=True)
    tick(inc, None, g)
    b.vita = 0.5
    ev = premi(inc, 0, "calcio_basso", g) + tick(inc, None, g, n=20)
    assert di_tipo(ev, E.ColpoASegno)[0].parato
    assert not di_tipo(ev, E.KO) and b.vita == 0.5 and inc.fase == "combattimento"
    fino_a(inc, lambda i: a.stato == "guardia" and b.stato == "parata", None, g)
    piazza(inc, gap=40)
    b.vita = 3.0
    ev = premi(inc, 0, "jab", g) + tick(inc, None, g, n=20)
    assert b.vita == pytest.approx(3.0 - MOSSE["jab"].danno * a.personaggio.potenza * R.DANNO_PARATA)


def test_parata_del_super_medio_non_atterra():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=60)
    g = comandi(guardia=True)
    tick(inc, None, g)
    a.energia = C.ENERGIA_MAX
    ev = premi(inc, 0, "speciale", g) + tick(inc, None, g, n=20)
    c = di_tipo(ev, E.ColpoASegno)[0]
    m = MOSSE["calcio_girato"]
    assert c.parato and c.livello == "medio"
    assert c.danno == pytest.approx(m.danno * a.personaggio.potenza * R.DANNO_PARATA)
    assert not di_tipo(ev, E.Atterramento) and b.stato == "bloccato"


def test_parata_richiede_guardia_verso_l_attaccante():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=30)
    b.guarda_destra = True             # guarda dalla parte sbagliata (non neutro, forzato)
    b.imposta_stato("bloccato", 30)
    ev = premi(inc, 0, "jab") + tick(inc, n=6)
    assert di_tipo(ev, E.ColpoASegno)[0].parato is False


def test_spinta_alle_corde_arretra_l_attaccante():
    inc = nuovo()
    a, b = inc.lottatori
    _, hi = R.limiti_x(b.hw)
    b.x = hi
    a.x = hi - a.hw - b.hw - 40
    a.guarda_destra, b.guarda_destra = True, False
    xa = a.x
    ev = premi(inc, 0, "diretto") + tick(inc, n=60)
    assert di_tipo(ev, E.ColpoASegno)
    assert b.x == pytest.approx(hi)
    avanz = MOSSE["diretto"].avanzamento
    assert a.x < xa + avanz - MOSSE["diretto"].spinta * 0.8


# ---- colpo d'incontro

def test_colpo_d_incontro():
    inc = nuovo("toro", "toro")
    a, b = inc.lottatori
    piazza(inc, gap=60)
    premi(inc, 0, "jab")
    ev = premi(inc, 1, "diretto")               # P2 in avvio quando arriva il jab
    ev += tick(inc, n=MOSSE["jab"].avvio - 1)
    c = di_tipo(ev, E.ColpoASegno)[0]
    m = MOSSE["jab"]
    assert c.contro and c.attaccante == 0
    assert c.danno == pytest.approx(m.danno * a.personaggio.potenza * R.MOLTIPLICATORE_CONTRO)
    assert b.stato == "colpito" and b.durata_stato == m.stordimento + R.HITSTUN_CONTRO
    assert inc.hitstop == m.hitstop + R.HITSTOP_CONTRO


def test_contro_atterra_con_calcio_alto():
    inc = nuovo("toro", "toro")
    a, b = inc.lottatori
    piazza(inc, gap=120)                          # il calcio basso di P2 non arriva in tempo
    ev = premi(inc, 0, "calcio_alto") + tick(inc, n=4)
    ev += premi(inc, 1, "calcio_basso")           # P2 in avvio quando arriva il calcio
    ev += tick(inc, n=40)
    colpi = di_tipo(ev, E.ColpoASegno)
    assert len(colpi) == 1 and colpi[0].contro and colpi[0].mossa == "calcio_alto"
    assert di_tipo(ev, E.Atterramento) == [E.Atterramento(1, 1)]
    assert b.atterramenti == 1


def test_senza_contro_calcio_alto_non_atterra():
    inc = nuovo()
    b = inc.lottatori[1]
    piazza(inc, gap=100)
    ev = premi(inc, 0, "calcio_alto") + tick(inc, n=20)
    assert not di_tipo(ev, E.ColpoASegno)[0].contro
    assert not di_tipo(ev, E.Atterramento) and b.stato == "colpito"


# ---- combo e cancel

def _combo(inc, sequenza, indice=0, altro=None):
    """Preme ogni pulsante appena il colpo precedente ha toccato (cancel)."""
    att = inc.lottatori[indice]

    def t(c=None):
        return tick(inc, c, altro) if indice == 0 else tick(inc, altro, c)

    ev = []
    for p in sequenza:
        tirati = att.statistiche["colpi_tirati"]
        ev += t(comandi(p))
        for _ in range(60):
            if att.statistiche["colpi_tirati"] > tirati and att._contatto:
                break
            ev += t()
        else:
            raise AssertionError("il colpo %s non e' arrivato" % p)
        ev += t()
    for _ in range(80):
        ev += t()
    return ev


def test_combo_e_scaling():
    inc = nuovo("toro", "muro")
    a, b = inc.lottatori
    piazza(inc, gap=70)
    ev = _combo(inc, ["jab", "diretto", "calcio_basso"])
    colpi = di_tipo(ev, E.ColpoASegno)
    assert [c.mossa for c in colpi] == ["jab", "diretto", "calcio_basso"]
    assert [c.combo for c in colpi] == [1, 2, 3]
    for c in colpi:
        base = MOSSE[c.mossa].danno * a.personaggio.potenza
        assert c.danno == pytest.approx(base * R.scaling_combo(c.combo))
    assert R.scaling_combo(1) == 1.0 and R.scaling_combo(3) == pytest.approx(0.8)
    assert R.scaling_combo(20) == R.SCALING_COMBO_MIN
    assert a.statistiche["combo_max"] == 3
    assert a.combo == 0 and b.stato == "guardia"     # finita l'hitstun la combo si azzera


def test_combo_attributo_e_azzeramento():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: a._contatto)
    assert a.combo == 1
    fino_a(inc, lambda i: b.stato != "colpito")
    assert a.combo == 0
    fino_a(inc, lambda i: a.stato == "guardia")
    ev = premi(inc, 0, "jab") + tick(inc, n=10)
    assert di_tipo(ev, E.ColpoASegno)[0].combo == 1


def test_combo_senza_cancel_non_e_combo():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=60)
    ev = premi(inc, 0, "calcio_alto")
    ev += fino_a(inc, lambda i: a.stato == "guardia")
    ev += premi(inc, 0, "jab") + tick(inc, n=12)
    colpi = di_tipo(ev, E.ColpoASegno)
    assert [c.combo for c in colpi] == [1, 1]


def test_cancel_a_segno_nella_finestra():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
    m = MOSSE["jab"]
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: a._contatto)
    ev = premi(inc, 0, "diretto")            # premuto durante l'hitstop: bufferizzato
    ev += fino_a(inc, lambda i: a.mossa == "diretto")
    # parte all'ultimo frame attivo del jab (inizio della finestra di cancel)
    avvii = di_tipo(ev, E.AttaccoIniziato)
    assert avvii == [E.AttaccoIniziato(0, "diretto")]
    assert a.frame_stato == 0


def test_cancel_frame_esatti():
    m = MOSSE["jab"]
    fine_attivo = m.avvio + m.attivo
    for frame_pressione, atteso in ((fine_attivo + R.FINESTRA_CANCEL - 1, "cancel"),
                                    (fine_attivo + R.FINESTRA_CANCEL, "neutro")):
        inc = nuovo()
        a = inc.lottatori[0]
        piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
        premi(inc, 0, "jab")
        fino_a(inc, lambda i: a._contatto)
        fino_a(inc, lambda i: a.frame_stato == frame_pressione - 1 and not i.hitstop)
        premi(inc, 0, "diretto")                 # questo tick porta il jab a frame_pressione
        assert a.mossa == "diretto" or a.frame_stato == frame_pressione
        if atteso == "cancel":
            assert a.mossa == "diretto" and a.frame_stato == 0
        else:
            assert a.mossa == "jab"
            tick(inc)
            assert a.mossa == "diretto" and a.frame_stato == 0
            assert a.statistiche["colpi_tirati"] == 2


def test_niente_cancel_a_vuoto():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=300)
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: a.frame_stato == MOSSE["jab"].avvio + MOSSE["jab"].attivo)
    ev = premi(inc, 0, "diretto") + tick(inc, n=6)
    assert a.mossa == "jab" or a.stato == "guardia"
    assert not [e for e in di_tipo(ev, E.AttaccoIniziato) if e.mossa == "diretto"]


def test_niente_cancel_fuori_da_cancella_in():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=70)
    assert "jab" not in MOSSE["calcio_basso"].cancella_in
    premi(inc, 0, "calcio_basso")
    fino_a(inc, lambda i: a._contatto)
    tick(inc)
    ev = premi(inc, 0, "jab") + tick(inc, n=4)
    assert a.mossa == "calcio_basso"
    assert not di_tipo(ev, E.AttaccoIniziato)


def test_cancel_su_parata():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
    g = comandi(guardia=True)
    ev = _combo(inc, ["jab", "diretto"], altro=g)
    colpi = di_tipo(ev, E.ColpoASegno)
    assert [c.mossa for c in colpi] == ["jab", "diretto"] and all(c.parato for c in colpi)


def test_super_in_cancel_dal_diretto():
    inc = nuovo("lama", "toro")
    a, b = inc.lottatori
    a.energia = C.ENERGIA_MAX
    piazza(inc, gap=DISTANZA_RAVVICINATA + 20)
    ev = _combo(inc, ["jab", "diretto", "speciale"])
    colpi = di_tipo(ev, E.ColpoASegno)
    assert [c.mossa for c in colpi] == ["jab", "diretto", "calcio_girato"]
    assert [c.combo for c in colpi] == [1, 2, 3]
    assert di_tipo(ev, E.Atterramento)


def test_catena_di_cancel_limitata():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=0)
    ev = _combo(inc, ["jab", "jab"])
    assert [c.combo for c in di_tipo(ev, E.ColpoASegno)] == [1, 2]
    # un terzo jab di fila non si concatena: parte solo dal neutro
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=0)
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: a._contatto)
    tick(inc)
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: a._contatto and a.statistiche["colpi_tirati"] == 2)
    tick(inc)
    ev = premi(inc, 0, "jab") + tick(inc, n=R.FINESTRA_CANCEL + 6)
    assert not di_tipo(ev, E.AttaccoIniziato)
    # lunghezza massima della catena
    a.imposta_mossa("diretto", MOSSE["diretto"].avvio + 1)
    a._contatto = True
    a._catena = ["jab", "jab", "diretto"]
    assert a._cancel_ammesso("calcio_alto", "calcio_alto")
    a._catena = ["jab", "jab", "diretto", "gancio"][:R.LUNGHEZZA_MAX_CATENA]
    assert not a._cancel_ammesso("calcio_alto", "calcio_alto")


def test_combo_da_quattro_colpi():
    inc = nuovo("toro", "vento")
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
    ev = _combo(inc, ["jab", "jab", "diretto", "calcio_alto"])
    colpi = di_tipo(ev, E.ColpoASegno)
    assert [c.mossa for c in colpi] == ["jab", "jab", "diretto", "calcio_alto"]
    assert [c.combo for c in colpi] == [1, 2, 3, 4]


# ---- buffer

def test_buffer_di_sei_frame():
    for anticipo, parte in ((R.BUFFER_INPUT - 1, True), (R.BUFFER_INPUT + 1, False)):
        inc = nuovo()
        a = inc.lottatori[0]
        piazza(inc, gap=400)
        premi(inc, 0, "calcio_basso")
        durata = MOSSE["calcio_basso"].durata
        fino_a(inc, lambda i: a.frame_stato == durata - anticipo)
        premi(inc, 0, "jab")
        ev = tick(inc, n=anticipo + 2)
        assert bool(di_tipo(ev, E.AttaccoIniziato)) == parte, anticipo


def test_variante_ravvicinata_anche_in_cancel():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=10)
    ev = _combo(inc, ["jab", "diretto", "calcio_basso"])
    assert [c.mossa for c in di_tipo(ev, E.ColpoASegno)] == ["jab", "gancio", "ginocchiata"]


def test_avanzamento_della_mossa():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=500)
    x0 = a.x
    premi(inc, 0, "diretto")
    m = MOSSE["diretto"]
    tick(inc, n=m.avvio + m.attivo - 1)
    assert a.x - x0 == pytest.approx(m.avanzamento)
    tick(inc, n=m.recupero)
    assert a.x - x0 == pytest.approx(m.avanzamento)      # nessun movimento in recupero


def test_aggiorna_accetta_none():
    inc = Incontro(personaggio("toro"), personaggio("vento"))
    ev = inc.aggiorna(None, None)
    assert di_tipo(ev, E.InizioRound) == [E.InizioRound(1)]


def test_pulsante_tenuto_non_ripete():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=400)
    ev = tick(inc, comandi(jab=True), n=60)
    assert len(di_tipo(ev, E.AttaccoIniziato)) == 1


# ---- variante ravvicinata

@pytest.mark.parametrize("pulsante,vicina", [("diretto", "gancio"), ("calcio_basso", "ginocchiata")])
def test_variante_ravvicinata(pulsante, vicina):
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA - 20)
    assert a.mossa_per_pulsante(pulsante, b) == vicina
    ev = premi(inc, 0, pulsante) + tick(inc, n=20)
    assert di_tipo(ev, E.AttaccoIniziato) == [E.AttaccoIniziato(0, vicina)]
    assert di_tipo(ev, E.ColpoASegno)[0].mossa == vicina      # la variante arriva sempre
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=DISTANZA_RAVVICINATA + 10)
    ev = premi(inc, 0, pulsante)
    assert di_tipo(ev, E.AttaccoIniziato) == [E.AttaccoIniziato(0, pulsante)]
    # jab e calcio alto non hanno varianti
    assert a.mossa_per_pulsante("jab", b) == "jab"


# ---- stamina

def test_costo_stamina_e_mossa_stanca():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    s0 = a.stamina
    premi(inc, 0, "jab")
    assert a.stamina == pytest.approx(s0 - MOSSE["jab"].stamina) and not a.mossa_stanca
    fino_a(inc, lambda i: a.stato == "guardia" and b.stato == "guardia")
    a.stamina = 2.0
    ev = premi(inc, 0, "jab")
    assert a.mossa_stanca and a.stamina == 0.0
    assert a.durata_stato == MOSSE["jab"].durata + R.RECUPERO_STANCO
    ev += tick(inc, n=10)
    c = di_tipo(ev, E.ColpoASegno)[0]
    assert c.danno == pytest.approx(MOSSE["jab"].danno * a.personaggio.potenza * R.DANNO_STANCO)


def test_rigenerazione_stamina():
    inc = nuovo("vento", "toro")
    a = inc.lottatori[0]
    piazza(inc, gap=400)
    a.stamina = 50.0
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: a.stato == "guardia")
    s0 = a.stamina
    tick(inc, n=R.RITARDO_RIGENERAZIONE - 2)
    assert a.stamina == pytest.approx(s0)
    tick(inc, n=12)
    assert a.stamina > s0
    s1 = a.stamina
    tick(inc, n=10)
    assert a.stamina - s1 == pytest.approx(10 * R.RIGENERAZIONE_STAMINA * a.personaggio.fiato)
    s2 = a.stamina
    tick(inc, comandi(guardia=True), n=10)
    assert a.stamina - s2 == pytest.approx(
        9 * R.RIGENERAZIONE_STAMINA * a.personaggio.fiato * R.FATTORE_RIGENERAZIONE_PARATA
        + R.RIGENERAZIONE_STAMINA * a.personaggio.fiato, rel=0.2)


def test_guardia_rotta():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=30)
    g = comandi(guardia=True)
    tick(inc, None, g)
    b.stamina = 3.0
    ev = premi(inc, 0, "diretto", g) + tick(inc, None, g, n=10)
    assert di_tipo(ev, E.GuardiaRotta) == [E.GuardiaRotta(1)]
    assert di_tipo(ev, E.ColpoASegno)[0].parato
    assert b.stato == "guardia_rotta" and b.durata_stato == R.DURATA_GUARDIA_ROTTA
    assert b.stamina < 1.0
    fino_a(inc, lambda i: b.stato != "guardia_rotta", None, g)
    assert b.stamina >= R.STAMINA_DOPO_GUARDIA_ROTTA * b.stamina_max - 1e-9


def test_guardia_rotta_e_vulnerabile():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=30)
    b.imposta_stato("guardia_rotta", R.DURATA_GUARDIA_ROTTA)
    ev = premi(inc, 0, "jab", comandi(guardia=True))
    ev += tick(inc, None, comandi(guardia=True), n=8)
    assert not di_tipo(ev, E.ColpoASegno)[0].parato


# ---- schivata

def test_schivata_laterale():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=300)
    z0 = a.z
    s0 = a.stamina
    ev = premi(inc, 0, "schivata", su=True)
    assert di_tipo(ev, E.Schivata) == [E.Schivata(0, "laterale", False)]
    assert a.stato == "schivata" and a.tipo_schivata == "laterale"
    assert a.durata_stato == R.DURATA_SCHIVATA_LATERALE
    assert a.stamina == pytest.approx(s0 - R.COSTO_SCHIVATA)
    invuln = [a.invulnerabile]
    for _ in range(R.DURATA_SCHIVATA_LATERALE - 1):
        tick(inc)
        invuln.append(a.invulnerabile)
    ia, ib = R.INVULNERABILE_LATERALE
    assert invuln == [ia <= f <= ib for f in range(R.DURATA_SCHIVATA_LATERALE)]
    assert a.z - z0 == pytest.approx(R.DISTANZA_SCHIVATA_LATERALE * a.personaggio.velocita)
    tick(inc)
    assert a.stato == "guardia"
    # verso la camera
    z0 = a.z
    premi(inc, 0, "schivata", giu=True)
    tick(inc, n=R.DURATA_SCHIVATA_LATERALE)
    assert z0 - a.z == pytest.approx(R.DISTANZA_SCHIVATA_LATERALE * a.personaggio.velocita)


def test_schivata_indietro():
    inc = nuovo("vento", "toro")
    a = inc.lottatori[0]
    piazza(inc, gap=200, x1=900)
    x0 = a.x
    ev = premi(inc, 0, "schivata")
    assert di_tipo(ev, E.Schivata) == [E.Schivata(0, "indietro", False)]
    assert a.durata_stato == R.DURATA_SCHIVATA_INDIETRO and a.direzione_cammino == -1
    invuln = [a.invulnerabile]
    for _ in range(R.DURATA_SCHIVATA_INDIETRO - 1):
        tick(inc)
        invuln.append(a.invulnerabile)
    ia, ib = R.INVULNERABILE_INDIETRO
    assert invuln == [ia <= f <= ib for f in range(R.DURATA_SCHIVATA_INDIETRO)]
    assert x0 - a.x == pytest.approx(R.DISTANZA_SCHIVATA_INDIETRO * a.personaggio.velocita)


def test_schivata_stanca_senza_invulnerabilita():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=300)
    a.stamina = R.COSTO_SCHIVATA - 1
    z0 = a.z
    premi(inc, 0, "schivata", su=True)
    assert a.schivata_stanca and a.stamina == 0.0
    invuln = [a.invulnerabile]
    for _ in range(R.DURATA_SCHIVATA_LATERALE):
        tick(inc)
        invuln.append(a.invulnerabile)
    assert not any(invuln)
    atteso = R.DISTANZA_SCHIVATA_LATERALE * a.personaggio.velocita * R.DISTANZA_SCHIVATA_STANCA
    assert a.z - z0 == pytest.approx(atteso)


def test_schivata_laterale_al_bordo_va_dall_altra_parte():
    inc = nuovo()
    a = inc.lottatori[0]
    piazza(inc, gap=300, z=R.Z_MAX)
    premi(inc, 0, "schivata", su=True)
    assert a.direzione_profondita == -1
    tick(inc, n=R.DURATA_SCHIVATA_LATERALE)
    assert R.Z_MAX - a.z == pytest.approx(R.DISTANZA_SCHIVATA_LATERALE * a.personaggio.velocita)


def test_schivata_riuscita_ed_energia():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    premi(inc, 0, "calcio_alto")
    # P2 schiva in modo che gli i-frame coprano la fase attiva del calcio
    fino_a(inc, lambda i: a.frame_stato == MOSSE["calcio_alto"].avvio - 4)
    ev = premi(inc, 1, "schivata", su=True)
    ev += tick(inc, n=40)
    riuscite = [e for e in di_tipo(ev, E.Schivata) if e.riuscita]
    assert riuscite == [E.Schivata(1, "laterale", True)]
    assert not di_tipo(ev, E.ColpoASegno)
    assert di_tipo(ev, E.Mancato) == [E.Mancato(0, "calcio_alto")]
    assert b.energia == pytest.approx(R.ENERGIA_SCHIVATA)
    assert b.statistiche["schivate_riuscite"] == 1


def test_schivata_indietro_riuscita():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    premi(inc, 0, "diretto")
    fino_a(inc, lambda i: a.frame_stato == MOSSE["diretto"].avvio - 3)
    ev = premi(inc, 1, "schivata") + tick(inc, n=30)
    assert [e for e in di_tipo(ev, E.Schivata) if e.riuscita] == [E.Schivata(1, "indietro", True)]
    assert not di_tipo(ev, E.ColpoASegno)


def test_schivata_troppo_presto_viene_colpita():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    premi(inc, 1, "schivata")          # troppo presto: quando il jab e' attivo gli i-frame
    tick(inc, n=R.INVULNERABILE_INDIETRO[1] - MOSSE["jab"].avvio + 1)   # sono gia' finiti
    b.x = a.x + a.hw + b.hw + 40       # riportato a tiro
    ev = premi(inc, 0, "jab") + tick(inc, n=8)
    assert di_tipo(ev, E.ColpoASegno)
    assert not [e for e in di_tipo(ev, E.Schivata) if e.riuscita]


# ---- energia e super

def test_energia_da_danno_e_super_pronto():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    ev = premi(inc, 0, "diretto") + tick(inc, n=12)
    d = di_tipo(ev, E.ColpoASegno)[0].danno
    assert a.energia == pytest.approx(d * R.ENERGIA_DANNO_INFLITTO)
    assert b.energia == pytest.approx(d * R.ENERGIA_DANNO_SUBITO)
    fino_a(inc, lambda i: a.stato == "guardia" and b.stato == "guardia")
    a.energia = C.ENERGIA_MAX - 1
    ev = premi(inc, 0, "jab") + tick(inc, n=10)
    assert di_tipo(ev, E.SuperPronto) == [E.SuperPronto(0)]
    assert a.energia == C.ENERGIA_MAX and a.super_pronto
    fino_a(inc, lambda i: a.stato == "guardia" and b.stato == "guardia")
    ev = premi(inc, 0, "jab") + tick(inc, n=10)
    assert not di_tipo(ev, E.SuperPronto)        # gia' piena: nessun nuovo evento


def test_speciale_richiede_energia():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=60)
    a.energia = 50.0
    ev = premi(inc, 0, "speciale") + tick(inc, n=5)
    assert not di_tipo(ev, E.AttaccoIniziato) and a.energia == 50.0
    a.energia = C.ENERGIA_MAX
    ev = premi(inc, 0, "speciale")
    assert di_tipo(ev, E.AttaccoIniziato) == [E.AttaccoIniziato(0, "calcio_girato")]
    assert a.energia == 0.0
    ev += tick(inc, n=40)
    colpo = di_tipo(ev, E.ColpoASegno)[0]
    assert colpo.mossa == "calcio_girato" and colpo.forza == pytest.approx(
        R.forza_da_danno(colpo.danno))
    assert di_tipo(ev, E.Atterramento) == [E.Atterramento(1, 1)]        # atterra 'sempre'


def test_energia_conservata_tra_i_round():
    inc = nuovo(durata_round=1)
    a, b = inc.lottatori
    a.energia = 42.0
    fino_a(inc, lambda i: i.fase == "presentazione")
    assert a.energia == 42.0 and inc.numero_round == 2


# ---- atterramento, conteggio, rialzo

def _atterra(inc, att=0):
    a = inc.lottatori[att]
    d = inc.lottatori[1 - att]
    a.energia = C.ENERGIA_MAX
    if att == 0:
        piazza(inc, gap=60, x1=800)
    else:
        piazza(inc, gap=60, x1=800)
        a.x, d.x = d.x, a.x
        a.guarda_destra, d.guarda_destra = True, False
    ev = premi(inc, att, "speciale")
    ev += fino_a(inc, lambda i: d.stato in ("atterrato", "ko"), limite=60)
    return ev


def test_atterramento_conteggio_e_rialzo():
    inc = nuovo()
    a, b = inc.lottatori
    ev = _atterra(inc)
    assert di_tipo(ev, E.Atterramento) == [E.Atterramento(1, 1)]
    assert b.stato == "atterrato" and b.durata_stato == R.DURATA_ATTERRATO and b.invulnerabile
    assert a.statistiche["atterramenti_inflitti"] == 1
    tempo = inc.tempo_rimasto
    conteggi = []
    frame_conteggi = []
    ev = []
    while b.stato == "atterrato":
        nuovi = tick(inc)
        for e in di_tipo(nuovi, E.ConteggioArbitro):
            conteggi.append(e.numero)
            frame_conteggi.append(b.frame_stato)
        ev += nuovi
        assert b.invulnerabile or b.stato != "atterrato"
    assert conteggi == [1, 2, 3, 4]
    assert frame_conteggi == [R.PRIMO_CONTEGGIO + k * R.INTERVALLO_CONTEGGIO for k in range(4)]
    assert di_tipo(ev, E.Rialzo) == [E.Rialzo(1)]
    assert b.stato == "rialzo" and b.durata_stato == R.DURATA_RIALZO
    assert inc.tempo_rimasto == pytest.approx(tempo)   # il tempo e' fermo durante il conteggio
    # P1 prova ad avvicinarsi: l'arbitro lo tiene lontano
    while b.stato == "rialzo":
        assert b.invulnerabile
        tick(inc, comandi(destra=True))
    assert abs(b.x - a.x) >= R.DISTANZA_RIALZO - R.VELOCITA_SEPARAZIONE
    assert b.stato == "guardia" and not b.invulnerabile
    tick(inc, n=5)
    assert inc.tempo_rimasto < tempo


def test_attacco_su_avversario_a_terra_va_a_vuoto():
    inc = nuovo()
    a, b = inc.lottatori
    _atterra(inc)
    fino_a(inc, lambda i: a.stato == "guardia")
    b.x = a.x + a.hw + b.hw + 30            # forzato a tiro
    ev = premi(inc, 0, "jab") + tick(inc, n=10)
    assert not di_tipo(ev, E.ColpoASegno) and di_tipo(ev, E.Mancato)


def test_ko_tecnico_dopo_tre_atterramenti():
    inc = nuovo()
    a, b = inc.lottatori
    for n in (1, 2):
        ev = _atterra(inc)
        assert di_tipo(ev, E.Atterramento) == [E.Atterramento(1, n)]
        fino_a(inc, lambda i: b.stato == "guardia" and a.stato == "guardia")
    ev = _atterra(inc)
    assert not di_tipo(ev, E.Atterramento)
    assert di_tipo(ev, E.KO) == [E.KO(1, tecnico=True)]
    assert di_tipo(ev, E.FineRound) == [E.FineRound(1, 0, "tko")]
    assert b.stato == "ko" and inc.fase == "fine_round" and inc.motivo_fine_round == "tko"
    assert b.atterramenti == 3 and a.round_vinti == 1


# ---- KO e ralenti

def test_ko_e_ralenti():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    b.vita = 1.0
    ev = premi(inc, 0, "diretto") + tick(inc, n=10)
    assert di_tipo(ev, E.KO) == [E.KO(1, False)]
    assert di_tipo(ev, E.FineRound) == [E.FineRound(1, 0, "ko")]
    ko_i = ev.index(di_tipo(ev, E.KO)[0])
    assert isinstance(ev[ko_i - 1], E.ColpoASegno)
    assert b.stato == "ko" and b.vita == 0.0 and b.invulnerabile
    assert inc.fase == "fine_round" and inc.vincitore_round == 0 and inc.motivo_fine_round == "ko"
    assert inc.rallentatore == pytest.approx(R.RALLENTATORE_KO)
    assert inc.hitstop > 0
    fino_a(inc, lambda i: i.hitstop == 0 and not b.in_hitstop)
    # durante il ralenti i lottatori avanzano solo in alcuni tick
    f0 = b.frame_stato
    tick(inc, n=20)
    avanzati = b.frame_stato - f0
    assert 5 <= avanzati <= 9
    assert a.stato != "vittoria"
    fino_a(inc, lambda i: i.rallentatore == 1.0, limite=R.DURATA_RALLENTATORE)
    assert a.stato == "vittoria" and b.stato == "ko"
    assert inc.storico_round == [(0, "ko")] and a.round_vinti == 1
    # dopo DURATA_FINE_ROUND tick: round 2 con vita e stamina piene
    ev = fino_a(inc, lambda i: i.fase == "presentazione", limite=R.DURATA_FINE_ROUND)
    assert inc.numero_round == 2
    assert b.vita == b.vita_max and a.stamina == a.stamina_max and b.stato == "intro"
    assert a.round_vinti == 1 and b.atterramenti == 0
    # InizioRound nello stesso tick in cui i lottatori tornano in posizione
    assert di_tipo(ev, E.InizioRound) == [E.InizioRound(2)]
    assert not di_tipo(tick(inc), E.InizioRound)


def test_durata_fine_round():
    inc = nuovo()
    piazza(inc, gap=40)
    inc.lottatori[1].vita = 1.0
    premi(inc, 0, "jab")
    fino_a(inc, lambda i: i.fase == "fine_round")
    n = 0
    while inc.fase == "fine_round":
        tick(inc)
        n += 1
    assert n == R.DURATA_FINE_ROUND


def test_doppio_ko_pareggio():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    a.vita = b.vita = 1.0
    ev = tick(inc, comandi("jab"), comandi("jab")) + tick(inc, n=10)
    assert sorted(e.indice for e in di_tipo(ev, E.KO)) == [0, 1]
    assert di_tipo(ev, E.FineRound) == [E.FineRound(1, None, "pareggio")]
    assert a.round_vinti == b.round_vinti == 0 and inc.vincitore_round is None


def test_colpi_simultanei():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    ev = tick(inc, comandi("jab"), comandi("jab")) + tick(inc, n=10)
    colpi = di_tipo(ev, E.ColpoASegno)
    assert sorted(c.attaccante for c in colpi) == [0, 1]
    assert not any(c.contro for c in colpi)
    assert a.stato == b.stato == "colpito"


# ---- tempo

def test_tempo_scaduto_ai_punti():
    inc = nuovo(durata_round=2)
    a, b = inc.lottatori
    b.vita = b.vita_max * 0.5
    a.vita = a.vita_max * 0.6
    ev = fino_a(inc, lambda i: i.fase != "combattimento", limite=2 * C.FPS + 5)
    assert inc.tempo_rimasto == 0.0
    assert di_tipo(ev, E.FineRound) == [E.FineRound(1, 0, "punti")]
    assert a.round_vinti == 1 and inc.motivo_fine_round == "punti"
    tick(inc, n=R.TICK_POSE_PUNTI + 1)
    assert a.stato == "vittoria" and b.stato == "sconfitta"


def test_tempo_scaduto_percentuale_non_assoluta():
    inc = nuovo("muro", "vento", durata_round=1)
    a, b = inc.lottatori
    a.vita = 70.0            # 70/122 = 57%
    b.vita = 60.0            # 60/92 = 65%
    fino_a(inc, lambda i: i.fase != "combattimento")
    assert inc.vincitore_round == 1


def test_tempo_scaduto_pareggio_e_timer():
    inc = nuovo(durata_round=3)
    tick(inc, n=C.FPS)
    assert inc.tempo_rimasto == pytest.approx(2.0)
    ev = fino_a(inc, lambda i: i.fase != "combattimento")
    assert di_tipo(ev, E.FineRound) == [E.FineRound(1, None, "pareggio")]
    assert inc.lottatori[0].round_vinti == inc.lottatori[1].round_vinti == 0
    assert inc.storico_round == [(None, "pareggio")]


# ---- flusso dei round e della partita

def test_presentazione():
    inc = Incontro(personaggio("toro"), personaggio("vento"))
    ev = tick(inc)
    assert di_tipo(ev, E.InizioRound) == [E.InizioRound(1)]
    n = 1
    while inc.fase == "presentazione":
        assert all(l.stato == "intro" for l in inc.lottatori)
        ev = tick(inc, comandi("jab"), comandi("calcio_alto"))
        n += 1
    assert n == R.DURATA_PRESENTAZIONE
    assert di_tipo(ev, E.Via) == [E.Via(1)]
    assert all(l.stato == "guardia" for l in inc.lottatori)
    # i pulsanti tenuti durante l'intro non fanno partire nulla
    ev = tick(inc, comandi("jab"), comandi("calcio_alto"), n=5)
    assert not di_tipo(ev, E.AttaccoIniziato)


def _vinci_round_per_ko(inc, indice=0):
    att = inc.lottatori[indice]
    dif = inc.lottatori[1 - indice]
    salta_presentazione(inc)
    dif.vita = 1.0
    if indice == 0:
        piazza(inc, gap=40)
    else:
        piazza(inc, gap=40)
        att.x, dif.x = dif.x, att.x
        att.guarda_destra, dif.guarda_destra = True, False
    ev = premi(inc, indice, "jab")
    ev += fino_a(inc, lambda i: i.fase not in ("combattimento", "fine_round"), limite=400)
    return ev


def test_flusso_partita():
    inc = Incontro(personaggio("toro"), personaggio("lama"))
    ev = _vinci_round_per_ko(inc, 0)
    assert inc.fase == "presentazione" and inc.numero_round == 2
    ev = _vinci_round_per_ko(inc, 1)
    assert inc.numero_round == 3
    ev = _vinci_round_per_ko(inc, 0)
    assert inc.fase == "fine_partita"
    assert di_tipo(ev, E.FinePartita) == [E.FinePartita(0)]
    assert inc.vincitore_partita == 0 and inc.numero_round == 3
    assert inc.storico_round == [(0, "ko"), (1, "ko"), (0, "ko")]
    a, b = inc.lottatori
    assert a.round_vinti == 2 and b.round_vinti == 1
    assert a.stato == "vittoria" and b.stato in ("ko", "sconfitta")
    # la partita finita resta ferma e non emette altro
    ev = tick(inc, comandi("jab"), n=100)
    assert not ev and inc.fase == "fine_partita"


def test_round_per_vincere_personalizzato():
    inc = Incontro(personaggio("toro"), personaggio("lama"), round_per_vincere=1)
    ev = _vinci_round_per_ko(inc, 1)
    assert inc.fase == "fine_partita" and inc.vincitore_partita == 1


def test_oltre_cinque_round_decide_il_danno():
    inc = Incontro(personaggio("toro"), personaggio("lama"), durata_round=1)
    while inc.fase != "fine_partita":
        tick(inc)
        assert inc.numero_round <= R.MAX_ROUND
    assert len(inc.storico_round) == R.MAX_ROUND
    assert all(r == (None, "pareggio") for r in inc.storico_round)
    assert inc.vincitore_partita == 0          # nessun danno: P1
    for danno_p1, danno_p2, atteso in ((10.0, 20.0, 1), (5.0, 5.0, 0), (30.0, 20.0, 0)):
        inc = Incontro(personaggio("toro"), personaggio("lama"), durata_round=1)
        inc.lottatori[0].statistiche["danno_inflitto"] = danno_p1
        inc.lottatori[1].statistiche["danno_inflitto"] = danno_p2
        ev = []
        while inc.fase != "fine_partita":
            ev += tick(inc)
        assert inc.vincitore_partita == atteso
        assert di_tipo(ev, E.FinePartita) == [E.FinePartita(atteso)]


# ---- statistiche

def test_statistiche():
    inc = nuovo()
    a, b = inc.lottatori
    piazza(inc, gap=40)
    _combo(inc, ["jab", "diretto"])
    fino_a(inc, lambda i: a.stato == "guardia" and b.stato == "guardia")
    piazza(inc, gap=40)
    premi(inc, 0, "jab", comandi(guardia=True))
    tick(inc, None, comandi(guardia=True), n=30)
    s = a.statistiche
    assert s["colpi_tirati"] == 3 and s["colpi_a_segno"] == 2 and s["combo_max"] == 2
    assert b.statistiche["colpi_parati"] == 1
    assert s["danno_inflitto"] == pytest.approx(b.vita_max - b.vita)


# ---- determinismo e robustezza

def _comandi_casuali(rng: random.Random, stato: dict, io, altro) -> Comandi:
    """Giocatore pseudo-casuale con pressioni vere (fronti): avanza, si allinea, colpisce."""
    c = Comandi()
    if rng.random() < 0.03:
        stato["dir"] = rng.choice((-1, 0, 1, 1, 1))          # relativo: +1 verso l'avversario
        stato["allinea"] = rng.random() < 0.6
        stato["prof"] = rng.choice((-1, 0, 1))
        stato["guardia"] = rng.random() < 0.15
    verso = 1 if altro.x > io.x else -1
    d = stato.get("dir", 1) * verso
    c.destra, c.sinistra = d > 0, d < 0
    if stato.get("allinea", True):
        dz = altro.z - io.z
        c.su, c.giu = dz > 8, dz < -8
    else:
        c.su, c.giu = stato.get("prof", 0) > 0, stato.get("prof", 0) < 0
    c.guardia = stato.get("guardia", False)
    if rng.random() < 0.10:
        setattr(c, rng.choice(("jab", "jab", "diretto", "diretto", "calcio_basso",
                               "calcio_alto", "speciale", "schivata")), True)
    return c


def _partita_casuale(p1, p2, seme: int, durata_round: int = 25, limite: int = 60000):
    rng = random.Random(seme)
    s1, s2 = {}, {}
    inc = Incontro(p1, p2, durata_round=durata_round)
    a, b = inc.lottatori
    tutti = []
    tick_n = 0
    while inc.fase != "fine_partita":
        ev = inc.aggiorna(_comandi_casuali(rng, s1, a, b), _comandi_casuali(rng, s2, b, a))
        tutti += ev
        controlla_invarianti(inc)
        tick_n += 1
        assert tick_n < limite, "la partita non finisce"
    return inc, tutti


def test_determinismo():
    inc1, ev1 = _partita_casuale(personaggio("vento"), personaggio("muro"), seme=7)
    inc2, ev2 = _partita_casuale(personaggio("vento"), personaggio("muro"), seme=7)
    assert ev1 == ev2 and len(ev1) > 100
    for l1, l2 in zip(inc1.lottatori, inc2.lottatori):
        assert (l1.x, l1.z, l1.vita, l1.energia, l1.statistiche) == \
               (l2.x, l2.z, l2.vita, l2.energia, l2.statistiche)


@pytest.mark.parametrize("seme", range(4))
def test_partite_casuali_tutte_le_coppie(seme):
    p1 = ROSTER[seme % len(ROSTER)]
    for p2 in ROSTER:
        inc, ev = _partita_casuale(p1, p2, seme=seme * 31 + ROSTER.index(p2))
        assert inc.vincitore_partita in (0, 1)
        assert di_tipo(ev, E.FinePartita) == [E.FinePartita(inc.vincitore_partita)]
        fine = di_tipo(ev, E.FineRound)
        assert len(fine) == len(inc.storico_round) >= 2
        assert len(di_tipo(ev, E.InizioRound)) == len(fine)
        assert len(di_tipo(ev, E.Via)) == len(fine)
        assert di_tipo(ev, E.ColpoASegno)
