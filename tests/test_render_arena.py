"""Test di arena ed effetti: disegno, copertura dello schermo, coerenza con la camera,
eventi di ogni tipo, limiti e prestazioni."""

from __future__ import annotations

import statistics
import time

import pygame
import pytest

from picchiaduro import costanti as C
from picchiaduro import eventi as E
from picchiaduro.camera import Camera

SENTINELLA = (255, 0, 254)


# ---- fixture e finti oggetti del contratto
@pytest.fixture(scope="module")
def schermo():
    pygame.init()
    return pygame.display.set_mode((C.LARGHEZZA, C.ALTEZZA))


@pytest.fixture(scope="module")
def arena(schermo):
    from picchiaduro.render.arena import Arena
    return Arena()


class LottatoreFinto:
    def __init__(self, x, z, destra=True, altezza=1.0):
        self.x, self.z, self.h = x, z, 0.0
        self.hw = C.LARGHEZZA_BASE / 2
        self.altezza_mondo = C.ALTEZZA_BASE * altezza
        self.guarda_destra = destra


class IncontroFinto:
    def __init__(self):
        self.lottatori = [LottatoreFinto(820, 200, True), LottatoreFinto(960, 215, False, 1.06)]


def tutti_gli_eventi():
    return [
        E.AttaccoIniziato(0, "jab"), E.AttaccoIniziato(1, "calcio_girato"),
        E.ColpoASegno(0, 1, "diretto", 9.0, False, False, 1, "alto", 0.4, 925, 207, 210),
        E.ColpoASegno(0, 1, "calcio_alto", 17.0, False, True, 2, "alto", 1.0, 925, 207, 215),
        E.ColpoASegno(1, 0, "calcio_basso", 3.0, True, False, 1, "basso", 0.6, 855, 207, 70),
        E.ColpoASegno(1, 0, "ginocchiata", 13.0, False, False, 3, "medio", 0.7, 855, 207, 140),
        E.Mancato(0, "gancio"), E.Schivata(1, "laterale", True), E.Schivata(0, "indietro", False),
        E.GuardiaRotta(0), E.Atterramento(1, 1), E.ConteggioArbitro(1, 3), E.Rialzo(1),
        E.KO(0), E.KO(1, tecnico=True), E.SuperPronto(0), E.InizioRound(1), E.Via(1),
        E.FineRound(1, 0, "ko"), E.FineRound(2, None, "pareggio"), E.FinePartita(1), E.Passo(0),
    ]


def camera(x, zoom, off=(0.0, 0.0)):
    cam = Camera()
    cam.x, cam.zoom = x, zoom
    cam.offset_x, cam.offset_y = off
    return cam


# ---- arena
@pytest.mark.parametrize("x, zoom", [(520, 1.0), (900, 1.06), (1280, 1.12), (0, 1.0),
                                     (1800, 1.12), (-700, 1.0), (2600, 1.08)])
def test_arena_si_disegna_da_ogni_posizione(arena, schermo, x, zoom):
    for off in ((0, 0), (22, -13), (-22, 13)):
        cam = camera(x, zoom, off)
        for t in (0.0, 1.37, 12.9):
            arena.disegna_sfondo(schermo, cam, t)
            arena.disegna_primo_piano(schermo, cam, t)


@pytest.mark.parametrize("x", [520, 659, 700, 881, 900, 955, 1100, 1280])
@pytest.mark.parametrize("zoom", [C.ZOOM_MIN, 1.03, 1.06, C.ZOOM_MAX])
def test_sfondo_copre_tutto_lo_schermo(arena, schermo, x, zoom):
    """Nessun pixel resta del frame precedente, anche con scossoni forti."""
    for off in ((0, 0), (24, 14), (-24, -14), (18, -14), (-18, 14)):
        schermo.fill(SENTINELLA)
        arena.disegna_sfondo(schermo, camera(x, zoom, off), 3.0)
        buchi = pygame.mask.from_threshold(schermo, SENTINELLA, (1, 1, 1, 255)).count()
        assert buchi == 0, (x, zoom, off, buchi)


def _colore(superficie, p):
    x, y = int(p[0]), int(p[1])
    return superficie.get_at((x, y))[:3]


@pytest.mark.parametrize("x, zoom, off", [(520, 1.0, (0, 0)), (700, 1.12, (9, -6)),
                                          (900, 1.05, (-15, 8))])
def test_ring_segue_la_camera(arena, schermo, x, zoom, off):
    """Pali e tela stanno dove li mette camera.proietta, per ogni pan/zoom/scossone."""
    from picchiaduro.render import arena as A
    cam = camera(x, zoom, off)
    arena.disegna_sfondo(schermo, cam, 0.0)
    P = C.RING_PROFONDITA + A.SPORGENZA_PALO
    rosso = _colore(schermo, cam.proietta(-A.SPORGENZA_PALO, P, 140))
    assert rosso[0] > 120 and rosso[0] > rosso[1] + 60 and rosso[0] > rosso[2] + 60, rosso
    if cam.proietta(C.RING_LARGHEZZA + A.SPORGENZA_PALO, P)[0] < C.LARGHEZZA - 4:
        blu = _colore(schermo, cam.proietta(C.RING_LARGHEZZA + A.SPORGENZA_PALO, P, 140))
        assert blu[2] > 120 and blu[2] > blu[0] + 60, blu
    tela = _colore(schermo, cam.proietta(160, 330))
    assert tela[2] > tela[0] + 40 and tela[2] > 70, tela
    # appena fuori dal bordo posteriore del grembiule non c'e' piu' la tela blu
    fuori = _colore(schermo, cam.proietta(160, C.RING_PROFONDITA + A.BORDO_FONDO + 20))
    assert fuori[2] < 110 or fuori[2] < fuori[0] + 40, fuori     # niente blu (un grigio LED va bene)


def test_corde_anteriori_semitrasparenti(arena, schermo):
    from picchiaduro.render import arena as A
    cam = camera(900, 1.06)
    schermo.fill((0, 0, 0))
    arena.disegna_primo_piano(schermo, cam, 0.0)
    x, y = cam.proietta(700, 0, A.ALTEZZE_CORDE[1])
    c_nero = _colore(schermo, (x, y))
    schermo.fill((255, 255, 255))
    arena.disegna_primo_piano(schermo, cam, 0.0)
    c_bianco = _colore(schermo, (x, y))
    assert c_nero != c_bianco, "la corda davanti deve lasciar vedere cio' che c'e' dietro"
    assert max(c_nero) > 20, "la corda davanti deve comunque vedersi"


def test_parallasse_strati(arena):
    """Gli strati piu' vicini scorrono piu' veloci di quelli lontani durante il pan."""
    velocita = []
    for strato in (arena._fondo, arena._tribuna_alta, arena._tribuna_bassa, arena._bordo, arena._led):
        a = strato.origine(camera(900, 1.1))[0]
        b = strato.origine(camera(910, 1.1))[0]
        d = (a - b) % strato.larghezza
        velocita.append(d / 10.0)
    assert velocita == sorted(velocita), velocita
    assert all(0.2 < v < 0.6 for v in velocita), velocita


def test_eccitazione_pubblico(arena, schermo):
    arena.eccita_pubblico(5.0)
    assert arena.eccitazione == pytest.approx(1.0)
    assert len(arena._flash) > 0
    arena.disegna_sfondo(schermo, camera(900, 1.1), 1.0)
    for _ in range(600):
        arena.aggiorna()
    assert arena.eccitazione == 0.0
    arena.eccita_pubblico(-3.0)
    assert arena.eccitazione == 0.0
    arena.eccita_pubblico(0.5)
    assert arena.eccitazione == pytest.approx(0.5)


def test_eccitazione_da_evento():
    from picchiaduro.render.arena import eccitazione_da_evento
    for ev in tutti_gli_eventi():
        assert 0.0 <= eccitazione_da_evento(ev) <= 1.0
    assert eccitazione_da_evento(E.KO(0)) == 1.0
    assert eccitazione_da_evento(E.Passo(0)) == 0.0


def test_prestazioni_arena(arena, schermo):
    """Budget SPEC: sfondo + primo piano <= 3 ms per frame (qui con margine per macchine lente)."""
    cam = Camera()
    tempi = []
    for f in range(240):
        centro = 900 + 700 * ((f % 120) / 60 - 1)
        cam.segui(centro - 150, centro + 150)
        if f % 60 == 0:
            cam.scuoti(15, 20)
            arena.eccita_pubblico(0.9)
        cam.aggiorna()
        arena.aggiorna()
        t0 = time.perf_counter()
        arena.disegna_sfondo(schermo, cam, f / 60)
        arena.disegna_primo_piano(schermo, cam, f / 60)
        tempi.append((time.perf_counter() - t0) * 1000)
    mediana = statistics.median(tempi[20:])
    print("arena: mediana %.2f ms, media %.2f ms" % (mediana, statistics.mean(tempi[20:])))
    assert mediana < 4.0


# ---- effetti
@pytest.fixture
def effetti(schermo):
    from picchiaduro.render.effetti import Effetti
    cam = Camera()
    cam.segui(820, 960, istantaneo=True)
    return Effetti(cam)


def test_effetti_ogni_evento(effetti, schermo):
    inc = IncontroFinto()
    for ev in tutti_gli_eventi():
        effetti.gestisci_evento(ev, inc)
    assert effetti.attivi() > 0
    for _ in range(150):
        effetti.aggiorna()
        effetti.camera.aggiorna()
        effetti.disegna_mondo(schermo)
        effetti.disegna_schermo(schermo)
    assert effetti.attivi() == 0


def test_effetti_senza_incontro(effetti, schermo):
    for ev in tutti_gli_eventi():
        effetti.gestisci_evento(ev, None)
    for _ in range(5):
        effetti.aggiorna()
        effetti.disegna_mondo(schermo)
        effetti.disegna_schermo(schermo)


def test_colpo_pesante_scuote_e_lampeggia(effetti, schermo):
    inc = IncontroFinto()
    effetti.gestisci_evento(E.ColpoASegno(0, 1, "calcio_alto", 17.0, False, True, 1, "alto",
                                          1.0, 925, 207, 215), inc)
    effetti.camera.aggiorna()
    assert abs(effetti.camera.offset_x) + abs(effetti.camera.offset_y) > 1.0
    schermo.fill((20, 20, 20))
    effetti.disegna_schermo(schermo)
    assert schermo.get_at((5, 5))[0] > 60, "lampo bianco a tutto schermo"
    assert any(t[5] == "contro" for t in effetti._testi)


def test_parata_non_lampeggia(effetti, schermo):
    inc = IncontroFinto()
    effetti.gestisci_evento(E.ColpoASegno(1, 0, "diretto", 1.0, True, False, 1, "alto",
                                          0.5, 855, 207, 210), inc)
    assert effetti._lampo == 0.0
    assert effetti._anelli, "anello azzurro della parata"
    assert not effetti._gocce


def test_testi_nel_mondo(effetti, schermo):
    inc = IncontroFinto()
    effetti.gestisci_evento(E.Schivata(1, "laterale", True), inc)
    effetti.gestisci_evento(E.GuardiaRotta(0), inc)
    effetti.gestisci_evento(E.SuperPronto(0), inc)
    chiavi = {t[5] for t in effetti._testi}
    assert chiavi == {"schivata", "guardia_rotta", "super"}
    h0 = {t[5]: t[2] for t in effetti._testi}
    for _ in range(10):
        effetti.aggiorna()
    assert all(t[2] > h0[t[5]] for t in effetti._testi), "i testi salgono"
    effetti.gestisci_evento(E.Schivata(1, "indietro", False), inc)
    assert sum(t[5] == "schivata" for t in effetti._testi) == 1


def test_sudore_solo_sui_colpi_pesanti(effetti):
    inc = IncontroFinto()
    effetti.gestisci_evento(E.ColpoASegno(0, 1, "jab", 2.0, False, False, 1, "basso", 0.1,
                                          925, 207, 70), inc)
    assert not effetti._gocce
    effetti.gestisci_evento(E.ColpoASegno(0, 1, "diretto", 12.0, False, False, 1, "alto", 0.8,
                                          925, 207, 210), inc)
    assert effetti._gocce


def test_limite_particelle(effetti, schermo):
    from picchiaduro.render.effetti import MAX_PARTICELLE
    inc = IncontroFinto()
    for _ in range(200):
        effetti.gestisci_evento(E.ColpoASegno(0, 1, "calcio_alto", 17.0, False, True, 1, "alto",
                                              1.0, 925, 207, 215), inc)
        effetti.gestisci_evento(E.KO(1), inc)
    assert effetti._conta() <= MAX_PARTICELLE + 64
    effetti.disegna_mondo(schermo)


def test_prestazioni_effetti(effetti, schermo):
    inc = IncontroFinto()
    tempi = []
    for f in range(120):
        if f % 20 == 0:
            effetti.gestisci_evento(E.ColpoASegno(0, 1, "calcio_alto", 17.0, False, f % 40 == 0, 1,
                                                  "alto", 0.9, 925, 207, 215), inc)
        if f == 60:
            effetti.gestisci_evento(E.KO(1), inc)
        effetti.aggiorna()
        t0 = time.perf_counter()
        effetti.disegna_mondo(schermo)
        effetti.disegna_schermo(schermo)
        tempi.append((time.perf_counter() - t0) * 1000)
    print("effetti: media %.2f ms, max %.2f ms" % (statistics.mean(tempi), max(tempi)))
    assert statistics.mean(tempi) < 3.0


def test_limite_luci(effetti):
    from picchiaduro.render.effetti import MAX_LUCI
    inc = IncontroFinto()
    for _ in range(100):
        for ev in tutti_gli_eventi():
            effetti.gestisci_evento(ev, inc)
    assert len(effetti._bagliori) <= MAX_LUCI
    assert len(effetti._anelli) <= MAX_LUCI


def test_partita_vera(schermo, arena):
    """Effetti e arena pilotati da una vera Incontro (contratto degli eventi e dei lottatori)."""
    import random
    from picchiaduro.comandi import Comandi
    from picchiaduro.personaggi import ROSTER
    from picchiaduro.render.arena import eccitazione_da_evento
    from picchiaduro.render.effetti import Effetti
    from picchiaduro.sim.incontro import Incontro

    rng = random.Random(5)
    inc = Incontro(ROSTER[0], ROSTER[3], durata_round=20)
    cam = Camera()
    cam.segui(inc.lottatori[0].x, inc.lottatori[1].x, istantaneo=True)
    fx = Effetti(cam)
    tipi = set()
    for f in range(1800):
        c = []
        for i in (0, 1):
            l, o = inc.lottatori[i], inc.lottatori[1 - i]
            k = Comandi()
            if abs(l.x - o.x) > 190:
                k.destra, k.sinistra = o.x > l.x, o.x < l.x
            elif rng.random() < 0.05:
                setattr(k, rng.choice(["jab", "diretto", "calcio_basso", "calcio_alto", "speciale"]), True)
            k.su, k.giu = l.z < o.z - 30, l.z > o.z + 30
            c.append(k)
        for ev in inc.aggiorna(*c):
            tipi.add(type(ev).__name__)
            fx.gestisci_evento(ev, inc)
            arena.eccita_pubblico(eccitazione_da_evento(ev))
        cam.segui(inc.lottatori[0].x, inc.lottatori[1].x)
        cam.aggiorna()
        arena.aggiorna()
        fx.aggiorna()
        if f % 7 == 0:
            arena.disegna_sfondo(schermo, cam, f / 60)
            arena.disegna_primo_piano(schermo, cam, f / 60)
            fx.disegna_mondo(schermo)
            fx.disegna_schermo(schermo)
    assert {"ColpoASegno", "KO"} <= tipi, tipi
