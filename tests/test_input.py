"""Test del modulo input: tastiera simulata, eventi sintetici, gamepad finti."""

from __future__ import annotations

import pygame
import pytest

from picchiaduro import input as inp
from picchiaduro.comandi import Comandi
from picchiaduro.input import AzioneMenu, GestoreInput


# ---- utilita'

class TastiFinti:
    """Sostituto di pygame.key.get_pressed(): indicizzabile per costante K_*."""

    def __init__(self, premuti=()):
        self.premuti = set(premuti)

    def __getitem__(self, k):
        return k in self.premuti


class JoystickFinto:
    def __init__(self, indice, instance_id):
        self.indice = indice
        self.instance_id = instance_id

    def init(self):
        pass

    def get_instance_id(self):
        return self.instance_id

    def get_id(self):
        return self.indice


@pytest.fixture
def tasti(monkeypatch):
    stato = TastiFinti()
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: stato)
    return stato


@pytest.fixture
def hw(monkeypatch):
    """Joystick finti: hw.presenti (lista di JoystickFinto) e hw.gestore()."""

    class Hw:
        presenti = []

        def collega(self, instance_id):
            j = JoystickFinto(len(self.presenti), instance_id)
            self.presenti.append(j)
            return j

    h = Hw()
    h.presenti = []
    monkeypatch.setattr(pygame.joystick, "get_init", lambda: True)
    monkeypatch.setattr(pygame.joystick, "get_count", lambda: len(h.presenti))
    monkeypatch.setattr(pygame.joystick, "Joystick", lambda i: h.presenti[i])
    return h


def tasto(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k)


def bottone(iid, b, giu=True):
    t = pygame.JOYBUTTONDOWN if giu else pygame.JOYBUTTONUP
    return pygame.event.Event(t, instance_id=iid, button=b)


def asse(iid, a, v):
    return pygame.event.Event(pygame.JOYAXISMOTION, instance_id=iid, axis=a, value=v)


def hat(iid, v, h=0):
    return pygame.event.Event(pygame.JOYHATMOTION, instance_id=iid, hat=h, value=v)


def aggiunto(device_index):
    return pygame.event.Event(pygame.JOYDEVICEADDED, device_index=device_index)


def rimosso(iid):
    return pygame.event.Event(pygame.JOYDEVICEREMOVED, instance_id=iid)


def campi_attivi(c):
    return {k for k, v in vars(c).items() if v}


# ---- tastiera: singolo

def test_senza_input_comandi_vuoti(tasti, hw):
    g = GestoreInput()
    assert g.comandi(0, "singolo") == Comandi()
    assert g.comandi(1, "doppio") == Comandi()


def test_singolo_wasd_e_frecce_equivalenti(tasti, hw):
    g = GestoreInput()
    tasti.premuti = {pygame.K_a, pygame.K_w}
    assert campi_attivi(g.comandi(0, "singolo")) == {"sinistra", "su"}
    tasti.premuti = {pygame.K_RIGHT, pygame.K_DOWN}
    assert campi_attivi(g.comandi(0, "singolo")) == {"destra", "giu"}


@pytest.mark.parametrize("campo,principale,alternativo", [
    ("jab", pygame.K_j, pygame.K_f),
    ("diretto", pygame.K_k, pygame.K_g),
    ("calcio_basso", pygame.K_u, pygame.K_r),
    ("calcio_alto", pygame.K_i, pygame.K_t),
    ("guardia", pygame.K_l, pygame.K_h),
    ("schivata", pygame.K_SPACE, pygame.K_v),
    ("speciale", pygame.K_o, pygame.K_y),
])
def test_singolo_attacchi_e_schema_alternativo(tasti, hw, campo, principale, alternativo):
    g = GestoreInput()
    for k in (principale, alternativo):
        tasti.premuti = {k}
        assert campi_attivi(g.comandi(0, "singolo")) == {campo}


def test_singolo_giocatore2_e_cpu(tasti, hw):
    g = GestoreInput()
    tasti.premuti = {pygame.K_j, pygame.K_LEFT}
    assert g.comandi(1, "singolo") == Comandi()


def test_singolo_tasti_multipli_insieme(tasti, hw):
    g = GestoreInput()
    tasti.premuti = {pygame.K_d, pygame.K_j, pygame.K_l}
    assert campi_attivi(g.comandi(0, "singolo")) == {"destra", "jab", "guardia"}


def test_modalita_sconosciuta(tasti, hw):
    g = GestoreInput()
    with pytest.raises(ValueError):
        g.comandi(0, "boh")
    with pytest.raises(ValueError):
        g.descrizione_comandi("cpu")


# ---- tastiera: doppio

def test_doppio_p1_wasd_e_fghrtvy(tasti, hw):
    g = GestoreInput()
    attesi = {
        pygame.K_f: "jab", pygame.K_g: "diretto", pygame.K_r: "calcio_basso",
        pygame.K_t: "calcio_alto", pygame.K_h: "guardia", pygame.K_v: "schivata",
        pygame.K_y: "speciale",
        pygame.K_a: "sinistra", pygame.K_d: "destra", pygame.K_w: "su", pygame.K_s: "giu",
    }
    for k, campo in attesi.items():
        tasti.premuti = {k}
        assert campi_attivi(g.comandi(0, "doppio")) == {campo}
        assert g.comandi(1, "doppio") == Comandi()


def test_doppio_p1_ignora_tasti_di_p2(tasti, hw):
    g = GestoreInput()
    tasti.premuti = {pygame.K_j, pygame.K_LEFT, pygame.K_SPACE, pygame.K_KP1}
    assert g.comandi(0, "doppio") == Comandi()


@pytest.mark.parametrize("campo,tasti_ok", [
    ("jab", (pygame.K_j, pygame.K_KP1)),
    ("diretto", (pygame.K_k, pygame.K_KP2)),
    ("calcio_basso", (pygame.K_u, pygame.K_KP4)),
    ("calcio_alto", (pygame.K_i, pygame.K_KP5)),
    ("guardia", (pygame.K_l, pygame.K_KP0)),
    ("schivata", (pygame.K_m, pygame.K_KP3)),
    ("speciale", (pygame.K_o, pygame.K_KP6)),
    ("sinistra", (pygame.K_LEFT,)),
    ("destra", (pygame.K_RIGHT,)),
    ("su", (pygame.K_UP,)),
    ("giu", (pygame.K_DOWN,)),
])
def test_doppio_p2_frecce_lettere_e_tastierino(tasti, hw, campo, tasti_ok):
    g = GestoreInput()
    for k in tasti_ok:
        tasti.premuti = {k}
        assert campi_attivi(g.comandi(1, "doppio")) == {campo}
        assert g.comandi(0, "doppio") == Comandi()


def test_get_pressed_che_solleva_non_rompe(monkeypatch, hw):
    def boom():
        raise pygame.error("video non inizializzato")

    monkeypatch.setattr(pygame.key, "get_pressed", boom)
    assert GestoreInput().comandi(0, "singolo") == Comandi()


# ---- menu tastiera

def test_menu_tasti_base(tasti, hw):
    g = GestoreInput()
    casi = {
        pygame.K_UP: AzioneMenu.SU, pygame.K_w: AzioneMenu.SU,
        pygame.K_DOWN: AzioneMenu.GIU, pygame.K_s: AzioneMenu.GIU,
        pygame.K_LEFT: AzioneMenu.SINISTRA, pygame.K_a: AzioneMenu.SINISTRA,
        pygame.K_RIGHT: AzioneMenu.DESTRA, pygame.K_d: AzioneMenu.DESTRA,
        pygame.K_RETURN: AzioneMenu.CONFERMA, pygame.K_SPACE: AzioneMenu.CONFERMA,
        pygame.K_j: AzioneMenu.CONFERMA, pygame.K_f: AzioneMenu.CONFERMA,
        pygame.K_KP_ENTER: AzioneMenu.CONFERMA,
        pygame.K_BACKSPACE: AzioneMenu.INDIETRO,
        pygame.K_p: AzioneMenu.PAUSA,
    }
    for k, azione in casi.items():
        g.gestisci_evento(tasto(k))
        assert g.azioni_menu() == [(0, azione)], pygame.key.name(k)
        g.fine_frame()
    assert g.azioni_menu() == []


def test_esc_e_indietro_e_pausa(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(tasto(pygame.K_ESCAPE))
    assert set(g.azioni_menu()) == {(0, AzioneMenu.INDIETRO), (0, AzioneMenu.PAUSA)}


def test_fronte_di_salita_una_volta_sola(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(tasto(pygame.K_RETURN))
    assert g.azioni_menu() == [(0, AzioneMenu.CONFERMA)]
    # senza fine_frame le azioni restano; con fine_frame spariscono
    assert g.azioni_menu() == [(0, AzioneMenu.CONFERMA)]
    g.fine_frame()
    assert g.azioni_menu() == []


def test_azioni_menu_restituisce_copia(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(tasto(pygame.K_UP))
    g.azioni_menu().clear()
    assert g.azioni_menu() == [(0, AzioneMenu.SU)]


def test_menu_nessun_duplicato(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(tasto(pygame.K_UP))
    g.gestisci_evento(tasto(pygame.K_w))
    assert g.azioni_menu() == [(0, AzioneMenu.SU)]


def test_menu_doppio_tastiera_divisa(tasti, hw):
    g = GestoreInput()
    g.modalita_menu = "doppio"
    g.gestisci_evento(tasto(pygame.K_a))
    g.gestisci_evento(tasto(pygame.K_RIGHT))
    g.gestisci_evento(tasto(pygame.K_f))
    g.gestisci_evento(tasto(pygame.K_RETURN))
    assert g.azioni_menu() == [
        (0, AzioneMenu.SINISTRA), (1, AzioneMenu.DESTRA),
        (0, AzioneMenu.CONFERMA), (1, AzioneMenu.CONFERMA),
    ]


def test_menu_doppio_indietro_per_giocatore(tasti, hw):
    g = GestoreInput()
    g.modalita_menu = "doppio"
    g.gestisci_evento(tasto(pygame.K_BACKSPACE))
    g.gestisci_evento(tasto(pygame.K_g))
    assert g.azioni_menu() == [(1, AzioneMenu.INDIETRO), (0, AzioneMenu.INDIETRO)]


def test_modalita_menu_invalida(tasti, hw):
    g = GestoreInput()
    g.modalita_menu = "xx"
    with pytest.raises(ValueError):
        g.gestisci_evento(tasto(pygame.K_UP))


def test_tasto_sconosciuto_ignorato(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(tasto(pygame.K_z))
    g.gestisci_evento(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1), rel=(0, 0), buttons=(0, 0, 0)))
    assert g.azioni_menu() == []


# ---- gamepad: collegamento

def test_pad_presenti_all_avvio(tasti, hw):
    hw.collega(10)
    hw.collega(11)
    g = GestoreInput()
    assert g.numero_gamepad() == 2


def test_hotplug_aggiunta_e_rimozione(tasti, hw):
    g = GestoreInput()
    assert g.numero_gamepad() == 0
    hw.collega(5)
    g.gestisci_evento(aggiunto(0))
    assert g.numero_gamepad() == 1
    hw.collega(6)
    g.gestisci_evento(aggiunto(1))
    assert g.numero_gamepad() == 2
    g.gestisci_evento(rimosso(5))
    assert g.numero_gamepad() == 1
    g.gestisci_evento(rimosso(5))  # doppia rimozione innocua
    assert g.numero_gamepad() == 1
    g.gestisci_evento(rimosso(6))
    assert g.numero_gamepad() == 0


def test_device_added_duplicato_non_raddoppia(tasti, hw):
    hw.collega(3)
    g = GestoreInput()  # pygame 2 posta comunque DEVICEADDED all'avvio
    g.gestisci_evento(aggiunto(0))
    assert g.numero_gamepad() == 1


def test_device_added_con_indice_invalido(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(aggiunto(7))
    assert g.numero_gamepad() == 0


def test_eventi_di_pad_sconosciuto_ignorati(tasti, hw):
    g = GestoreInput()
    g.gestisci_evento(bottone(99, inp.PAD_X))
    g.gestisci_evento(asse(99, 0, 1.0))
    assert g.azioni_menu() == []
    assert g.comandi(0, "singolo") == Comandi()


def test_rimozione_azzera_stato_pad(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, inp.PAD_X))
    assert g.comandi(0, "singolo").jab
    g.gestisci_evento(rimosso(1))
    assert g.comandi(0, "singolo") == Comandi()


# ---- gamepad: comandi

@pytest.mark.parametrize("pulsante,campo", [
    (inp.PAD_X, "jab"), (inp.PAD_Y, "diretto"), (inp.PAD_A, "calcio_basso"),
    (inp.PAD_B, "calcio_alto"), (inp.PAD_RB, "guardia"), (inp.PAD_LB, "schivata"),
])
def test_pad_pulsanti_xbox(tasti, hw, pulsante, campo):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, pulsante))
    assert campi_attivi(g.comandi(0, "singolo")) == {campo}
    g.gestisci_evento(bottone(1, pulsante, giu=False))
    assert g.comandi(0, "singolo") == Comandi()


def test_pad_layout_xbox_indici_standard():
    assert (inp.PAD_A, inp.PAD_B, inp.PAD_X, inp.PAD_Y) == (0, 1, 2, 3)
    assert (inp.PAD_LB, inp.PAD_RB, inp.PAD_START) == (4, 5, 7)


def test_pad_stick_direzioni_con_su_verso_il_fondo(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(asse(1, inp.ASSE_Y, -1.0))  # stick in alto
    assert campi_attivi(g.comandi(0, "singolo")) == {"su"}
    g.gestisci_evento(asse(1, inp.ASSE_Y, 1.0))
    assert campi_attivi(g.comandi(0, "singolo")) == {"giu"}
    g.gestisci_evento(asse(1, inp.ASSE_Y, 0.0))
    g.gestisci_evento(asse(1, inp.ASSE_X, -0.9))
    assert campi_attivi(g.comandi(0, "singolo")) == {"sinistra"}
    g.gestisci_evento(asse(1, inp.ASSE_X, 0.9))
    g.gestisci_evento(asse(1, inp.ASSE_Y, -0.9))
    assert campi_attivi(g.comandi(0, "singolo")) == {"destra", "su"}


def test_pad_zona_morta_stick(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    for v in (0.0, 0.1, -0.25, 0.39, -0.39):
        g.gestisci_evento(asse(1, inp.ASSE_X, v))
        g.gestisci_evento(asse(1, inp.ASSE_Y, v))
        assert g.comandi(0, "singolo") == Comandi(), v
    assert g.azioni_menu() == []  # il drift non genera nemmeno azioni di menu
    g.gestisci_evento(asse(1, inp.ASSE_X, 0.41))
    assert g.comandi(0, "singolo").destra


def test_pad_croce_hat(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(hat(1, (0, 1)))
    assert campi_attivi(g.comandi(0, "singolo")) == {"su"}
    g.gestisci_evento(hat(1, (-1, -1)))
    assert campi_attivi(g.comandi(0, "singolo")) == {"sinistra", "giu"}
    g.gestisci_evento(hat(1, (1, 0)))
    assert campi_attivi(g.comandi(0, "singolo")) == {"destra"}
    g.gestisci_evento(hat(1, (0, 0)))
    assert g.comandi(0, "singolo") == Comandi()


def test_pad_grilletto_destro_come_asse(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(asse(1, inp.ASSE_GRILLETTO_DX, -1.0))  # a riposo (SDL2: -1)
    assert not g.comandi(0, "singolo").speciale
    g.gestisci_evento(asse(1, inp.ASSE_GRILLETTO_DX, 0.2))
    assert not g.comandi(0, "singolo").speciale
    g.gestisci_evento(asse(1, inp.ASSE_GRILLETTO_DX, 1.0))
    assert campi_attivi(g.comandi(0, "singolo")) == {"speciale"}
    g.gestisci_evento(asse(1, inp.ASSE_GRILLETTO_DX, -1.0))
    assert g.comandi(0, "singolo") == Comandi()


def test_pad_e_tastiera_si_uniscono(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    tasti.premuti = {pygame.K_j}
    g.gestisci_evento(bottone(1, inp.PAD_RB))
    g.gestisci_evento(asse(1, inp.ASSE_X, 1.0))
    assert campi_attivi(g.comandi(0, "singolo")) == {"jab", "guardia", "destra"}


# ---- gamepad: assegnazione ai giocatori

def test_doppio_primo_pad_p1_secondo_p2(tasti, hw):
    hw.collega(1)
    hw.collega(2)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, inp.PAD_X))
    g.gestisci_evento(bottone(2, inp.PAD_Y))
    assert campi_attivi(g.comandi(0, "doppio")) == {"jab"}
    assert campi_attivi(g.comandi(1, "doppio")) == {"diretto"}


def test_doppio_secondo_pad_diventa_p1_se_il_primo_si_scollega(tasti, hw):
    hw.collega(1)
    hw.collega(2)
    g = GestoreInput()
    g.gestisci_evento(bottone(2, inp.PAD_Y))
    g.gestisci_evento(rimosso(1))
    assert campi_attivi(g.comandi(0, "doppio")) == {"diretto"}
    assert g.comandi(1, "doppio") == Comandi()


def test_doppio_un_solo_pad_guida_solo_p1(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, inp.PAD_X))
    assert g.comandi(0, "doppio").jab
    assert g.comandi(1, "doppio") == Comandi()


def test_doppio_pad_e_tastiera_insieme(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, inp.PAD_X))
    tasti.premuti = {pygame.K_h}
    assert campi_attivi(g.comandi(0, "doppio")) == {"jab", "guardia"}


def test_singolo_qualunque_pad_guida_p1(tasti, hw):
    hw.collega(1)
    hw.collega(2)
    g = GestoreInput()
    g.gestisci_evento(bottone(2, inp.PAD_B))
    assert campi_attivi(g.comandi(0, "singolo")) == {"calcio_alto"}
    assert g.comandi(1, "singolo") == Comandi()


# ---- gamepad: menu

def test_menu_pad_pulsanti(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, inp.PAD_A))
    g.gestisci_evento(bottone(1, inp.PAD_B))
    g.gestisci_evento(bottone(1, inp.PAD_START))
    g.gestisci_evento(bottone(1, inp.PAD_X))  # non e' un'azione di menu
    assert g.azioni_menu() == [
        (0, AzioneMenu.CONFERMA), (0, AzioneMenu.INDIETRO), (0, AzioneMenu.PAUSA)]


def test_menu_pad_hat_e_stick_fronti_di_salita(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(hat(1, (0, 1)))
    g.gestisci_evento(hat(1, (0, 0)))
    g.gestisci_evento(hat(1, (-1, 0)))
    g.gestisci_evento(hat(1, (0, 0)))
    assert g.azioni_menu() == [(0, AzioneMenu.SU), (0, AzioneMenu.SINISTRA)]
    g.fine_frame()
    # stick: una sola azione finche' resta inclinato
    g.gestisci_evento(asse(1, inp.ASSE_Y, 0.6))
    g.gestisci_evento(asse(1, inp.ASSE_Y, 0.9))
    g.gestisci_evento(asse(1, inp.ASSE_Y, 1.0))
    assert g.azioni_menu() == [(0, AzioneMenu.GIU)]
    g.fine_frame()
    g.gestisci_evento(asse(1, inp.ASSE_Y, 0.0))
    g.gestisci_evento(asse(1, inp.ASSE_Y, 1.0))
    assert g.azioni_menu() == [(0, AzioneMenu.GIU)]


def test_menu_pad_stick_su_e_destra(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    g.gestisci_evento(asse(1, inp.ASSE_Y, -1.0))
    g.gestisci_evento(asse(1, inp.ASSE_X, 1.0))
    assert g.azioni_menu() == [(0, AzioneMenu.SU), (0, AzioneMenu.DESTRA)]


def test_menu_pad_per_giocatore(tasti, hw):
    hw.collega(1)
    hw.collega(2)
    g = GestoreInput()
    g.gestisci_evento(bottone(1, inp.PAD_A))
    g.gestisci_evento(bottone(2, inp.PAD_A))
    g.gestisci_evento(hat(2, (1, 0)))
    assert g.azioni_menu() == [
        (0, AzioneMenu.CONFERMA), (1, AzioneMenu.CONFERMA), (1, AzioneMenu.DESTRA)]


def test_menu_pad_singolo_tutto_a_p1(tasti, hw):
    hw.collega(1)
    hw.collega(2)
    g = GestoreInput()
    g.modalita_menu = "singolo"
    g.gestisci_evento(bottone(2, inp.PAD_A))
    assert g.azioni_menu() == [(0, AzioneMenu.CONFERMA)]


def test_menu_pad_terzo_ignorato(tasti, hw):
    for i in range(3):
        hw.collega(i + 1)
    g = GestoreInput()
    g.gestisci_evento(bottone(3, inp.PAD_A))
    assert g.azioni_menu() == []


# ---- descrizione comandi

@pytest.mark.parametrize("modalita", ["singolo", "doppio"])
def test_descrizione_struttura(tasti, hw, modalita):
    d = GestoreInput().descrizione_comandi(modalita)
    assert d["modalita"] == modalita
    assert isinstance(d["titolo"], str) and d["titolo"]
    assert d["gamepad_collegati"] == 0
    assert d["sezioni"] and d["note"]
    for s in d["sezioni"]:
        assert s["titolo"] and s["righe"]
        for azione, tasti_txt in s["righe"]:
            assert isinstance(azione, str) and azione
            assert isinstance(tasti_txt, str) and tasti_txt


def test_descrizione_contenuti(tasti, hw):
    g = GestoreInput()
    s = g.descrizione_comandi("singolo")
    testo = " ".join(t for sez in s["sezioni"] for r in sez["righe"] for t in r)
    for atteso in ("Jab", "Calcio alto", "Schivata", "Speciale", "Guardia", "Spazio", "RB", "LB", "Start"):
        assert atteso in testo
    dbl = g.descrizione_comandi("doppio")
    titoli = [x["titolo"] for x in dbl["sezioni"]]
    assert "GIOCATORE 1 - TASTIERA" in titoli and "GIOCATORE 2 - TASTIERA" in titoli
    testo2 = " ".join(t for sez in dbl["sezioni"] for r in sez["righe"] for t in r)
    assert "Tastierino" in testo2


def test_descrizione_conta_gamepad(tasti, hw):
    hw.collega(1)
    g = GestoreInput()
    assert g.descrizione_comandi("singolo")["gamepad_collegati"] == 1
    hw.collega(2)
    g.gestisci_evento(aggiunto(1))
    d = g.descrizione_comandi("doppio")
    assert d["gamepad_collegati"] == 2
    assert any("2 gamepad" in n for n in d["note"])


# ---- robustezza con pygame reale (senza finti)

def test_gestore_si_crea_con_pygame_reale():
    """Senza finti: nessuna eccezione, anche senza gamepad ne' finestra."""
    g = GestoreInput()
    assert g.numero_gamepad() >= 0
    assert isinstance(g.comandi(0, "singolo"), Comandi)
    assert isinstance(g.comandi(1, "doppio"), Comandi)
