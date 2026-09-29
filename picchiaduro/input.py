"""Input di KICKBOXING K1: tastiera e gamepad -> `Comandi` e azioni di menu.

Il combattimento legge lo STATO dei tasti (`comandi`), i menu leggono i FRONTI
di salita raccolti dagli eventi (`azioni_menu`, da svuotare con `fine_frame`).

Uso tipico, una volta per frame:
    for ev in pygame.event.get():
        input.gestisci_evento(ev)
    azioni = input.azioni_menu()          # [(giocatore, AzioneMenu.X), ...]
    c1 = input.comandi(0, 'singolo')
    ...
    input.fine_frame()
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import pygame

from picchiaduro.comandi import Comandi


# ---- azioni di menu

class AzioneMenu:
    """Azioni di menu (costanti stringa)."""

    SU = "su"
    GIU = "giu"
    SINISTRA = "sinistra"
    DESTRA = "destra"
    CONFERMA = "conferma"
    INDIETRO = "indietro"
    PAUSA = "pausa"


_MODALITA = ("singolo", "doppio")


# ---- layout tastiera (comando -> tasti alternativi)

_K = pygame

LAYOUT_SINGOLO: Dict[str, Tuple[int, ...]] = {
    "sinistra": (_K.K_a, _K.K_LEFT),
    "destra": (_K.K_d, _K.K_RIGHT),
    "su": (_K.K_w, _K.K_UP),
    "giu": (_K.K_s, _K.K_DOWN),
    "jab": (_K.K_j, _K.K_f),
    "diretto": (_K.K_k, _K.K_g),
    "calcio_basso": (_K.K_u, _K.K_r),
    "calcio_alto": (_K.K_i, _K.K_t),
    "guardia": (_K.K_l, _K.K_h),
    "schivata": (_K.K_SPACE, _K.K_v),
    "speciale": (_K.K_o, _K.K_y),
}

LAYOUT_DOPPIO_P1: Dict[str, Tuple[int, ...]] = {
    "sinistra": (_K.K_a,),
    "destra": (_K.K_d,),
    "su": (_K.K_w,),
    "giu": (_K.K_s,),
    "jab": (_K.K_f,),
    "diretto": (_K.K_g,),
    "calcio_basso": (_K.K_r,),
    "calcio_alto": (_K.K_t,),
    "guardia": (_K.K_h,),
    "schivata": (_K.K_v,),
    "speciale": (_K.K_y,),
}

LAYOUT_DOPPIO_P2: Dict[str, Tuple[int, ...]] = {
    "sinistra": (_K.K_LEFT,),
    "destra": (_K.K_RIGHT,),
    "su": (_K.K_UP,),
    "giu": (_K.K_DOWN,),
    "jab": (_K.K_j, _K.K_KP1),
    "diretto": (_K.K_k, _K.K_KP2),
    "calcio_basso": (_K.K_u, _K.K_KP4),
    "calcio_alto": (_K.K_i, _K.K_KP5),
    "guardia": (_K.K_l, _K.K_KP0),
    "schivata": (_K.K_m, _K.K_KP3),
    "speciale": (_K.K_o, _K.K_KP6),
}

_CAMPI_COMANDI = tuple(LAYOUT_SINGOLO.keys())


# ---- tasti di menu: modalita' -> tasto -> [(giocatore, azione)]

def _tabella_menu(voci: List[Tuple[int, str, Tuple[int, ...]]]) -> Dict[int, List[Tuple[int, str]]]:
    tab: Dict[int, List[Tuple[int, str]]] = {}
    for giocatore, azione, tasti in voci:
        for t in tasti:
            tab.setdefault(t, []).append((giocatore, azione))
    return tab


_AM = AzioneMenu

# Modalita' non specificata / singolo: tutta la tastiera guida il giocatore 0.
_MENU_TASTI_UNICO = _tabella_menu([
    (0, _AM.SU, (_K.K_UP, _K.K_w)),
    (0, _AM.GIU, (_K.K_DOWN, _K.K_s)),
    (0, _AM.SINISTRA, (_K.K_LEFT, _K.K_a)),
    (0, _AM.DESTRA, (_K.K_RIGHT, _K.K_d)),
    (0, _AM.CONFERMA, (_K.K_RETURN, _K.K_KP_ENTER, _K.K_SPACE, _K.K_j, _K.K_f)),
    (0, _AM.INDIETRO, (_K.K_ESCAPE, _K.K_BACKSPACE)),
    (0, _AM.PAUSA, (_K.K_ESCAPE, _K.K_p)),
])

# Modalita' doppio: WASD/F/SPAZIO -> P1, frecce/INVIO/J -> P2.
_MENU_TASTI_DOPPIO = _tabella_menu([
    (0, _AM.SU, (_K.K_w,)),
    (0, _AM.GIU, (_K.K_s,)),
    (0, _AM.SINISTRA, (_K.K_a,)),
    (0, _AM.DESTRA, (_K.K_d,)),
    (0, _AM.CONFERMA, (_K.K_f, _K.K_SPACE)),
    (0, _AM.INDIETRO, (_K.K_g, _K.K_ESCAPE)),
    (0, _AM.PAUSA, (_K.K_ESCAPE, _K.K_p)),
    (1, _AM.SU, (_K.K_UP,)),
    (1, _AM.GIU, (_K.K_DOWN,)),
    (1, _AM.SINISTRA, (_K.K_LEFT,)),
    (1, _AM.DESTRA, (_K.K_RIGHT,)),
    (1, _AM.CONFERMA, (_K.K_RETURN, _K.K_KP_ENTER, _K.K_j, _K.K_KP1)),
    (1, _AM.INDIETRO, (_K.K_BACKSPACE, _K.K_k, _K.K_KP2)),
])


# ---- gamepad (layout Xbox, SDL2/pygame 2)

PAD_A = 0
PAD_B = 1
PAD_X = 2
PAD_Y = 3
PAD_LB = 4
PAD_RB = 5
PAD_START = 7

ASSE_X = 0
ASSE_Y = 1            # negativo = stick verso l'alto
ASSE_GRILLETTO_DX = 5  # da -1 (rilasciato) a +1 (a fondo)

ZONA_MORTA = 0.4       # stick: sotto questa soglia l'asse e' ignorato
SOGLIA_GRILLETTO = 0.5

PULSANTI_PAD = {
    PAD_X: "jab",
    PAD_Y: "diretto",
    PAD_A: "calcio_basso",
    PAD_B: "calcio_alto",
    PAD_RB: "guardia",
    PAD_LB: "schivata",
}


class _Pad:
    """Stato di un gamepad collegato (aggiornato dagli eventi)."""

    def __init__(self, joy, instance_id: int) -> None:
        self.joy = joy
        self.instance_id = instance_id
        self.pulsanti: Set[int] = set()
        self.assi: Dict[int, float] = {}
        self.hat: Tuple[int, int] = (0, 0)

    def asse(self, indice: int) -> float:
        return self.assi.get(indice, 0.0)

    def direzioni(self) -> Set[str]:
        """Direzioni digitali attive (stick sinistro oltre zona morta + croce)."""
        d: Set[str] = set()
        x, y = self.asse(ASSE_X), self.asse(ASSE_Y)
        if x <= -ZONA_MORTA or self.hat[0] < 0:
            d.add("sinistra")
        if x >= ZONA_MORTA or self.hat[0] > 0:
            d.add("destra")
        if y <= -ZONA_MORTA or self.hat[1] > 0:
            d.add("su")
        if y >= ZONA_MORTA or self.hat[1] < 0:
            d.add("giu")
        return d

    def comandi(self) -> Comandi:
        c = Comandi()
        d = self.direzioni()
        c.sinistra = "sinistra" in d
        c.destra = "destra" in d
        c.su = "su" in d
        c.giu = "giu" in d
        for pulsante, campo in PULSANTI_PAD.items():
            if pulsante in self.pulsanti:
                setattr(c, campo, True)
        if self.asse(ASSE_GRILLETTO_DX) >= SOGLIA_GRILLETTO:
            c.speciale = True
        return c


_AZIONE_DA_DIREZIONE = {
    "su": _AM.SU,
    "giu": _AM.GIU,
    "sinistra": _AM.SINISTRA,
    "destra": _AM.DESTRA,
}

_AZIONE_DA_PULSANTE_PAD = {
    PAD_A: _AM.CONFERMA,
    PAD_B: _AM.INDIETRO,
    PAD_START: _AM.PAUSA,
}


# ---- gestore

class GestoreInput:
    """Raccoglie tastiera e gamepad e li traduce in `Comandi` e azioni di menu."""

    def __init__(self) -> None:
        # None = non specificata: tastiera -> P1, pad i-esimo -> giocatore i.
        # 'singolo': tutto -> P1. 'doppio': tastiera divisa P1/P2, pad i -> i.
        self.modalita_menu: Optional[str] = None
        self._pad: List[_Pad] = []
        self._menu: List[Tuple[int, str]] = []
        try:
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                self._aggiungi_pad(i)
        except pygame.error:
            pass

    # ---- eventi

    def gestisci_evento(self, ev) -> None:
        """Da chiamare per ogni evento pygame (KEYDOWN, JOY*, hot-plug)."""
        t = ev.type
        if t == pygame.KEYDOWN:
            self._tasto_giu(ev.key)
        elif t == pygame.JOYBUTTONDOWN:
            pad = self._pad_da_evento(ev)
            if pad is not None:
                pad.pulsanti.add(ev.button)
                azione = _AZIONE_DA_PULSANTE_PAD.get(ev.button)
                if azione is not None:
                    self._menu_pad(pad, azione)
        elif t == pygame.JOYBUTTONUP:
            pad = self._pad_da_evento(ev)
            if pad is not None:
                pad.pulsanti.discard(ev.button)
        elif t == pygame.JOYHATMOTION:
            pad = self._pad_da_evento(ev)
            if pad is not None and getattr(ev, "hat", 0) == 0:
                prima = pad.direzioni()
                pad.hat = (int(ev.value[0]), int(ev.value[1]))
                self._fronti_direzioni(pad, prima)
        elif t == pygame.JOYAXISMOTION:
            pad = self._pad_da_evento(ev)
            if pad is not None:
                prima = pad.direzioni()
                pad.assi[ev.axis] = float(ev.value)
                self._fronti_direzioni(pad, prima)
        elif t == getattr(pygame, "JOYDEVICEADDED", -1):
            self._aggiungi_pad(getattr(ev, "device_index", None))
        elif t == getattr(pygame, "JOYDEVICEREMOVED", -1):
            self._rimuovi_pad(getattr(ev, "instance_id", None))

    def _tasto_giu(self, tasto: int) -> None:
        tabella = _MENU_TASTI_DOPPIO if self._modalita_menu() == "doppio" else _MENU_TASTI_UNICO
        for voce in tabella.get(tasto, ()):
            self._menu.append(voce)

    def _modalita_menu(self) -> Optional[str]:
        m = self.modalita_menu
        if m is not None and m not in _MODALITA:
            raise ValueError("modalita' sconosciuta: %r" % (m,))
        return m

    # ---- gamepad: collegamento

    def _aggiungi_pad(self, device_index) -> None:
        if device_index is None:
            return
        try:
            joy = pygame.joystick.Joystick(device_index)
            try:
                joy.init()
            except (AttributeError, pygame.error):
                pass
            try:
                iid = joy.get_instance_id()
            except (AttributeError, pygame.error):
                iid = joy.get_id()
        except (pygame.error, IndexError):
            return
        if any(p.instance_id == iid for p in self._pad):
            return  # gia' presente (pygame 2 posta DEVICEADDED anche all'avvio)
        self._pad.append(_Pad(joy, iid))

    def _rimuovi_pad(self, instance_id) -> None:
        self._pad = [p for p in self._pad if p.instance_id != instance_id]

    def _pad_da_evento(self, ev) -> Optional[_Pad]:
        iid = getattr(ev, "instance_id", None)
        if iid is None:
            iid = getattr(ev, "joy", None)
        for p in self._pad:
            if p.instance_id == iid:
                return p
        return None

    def numero_gamepad(self) -> int:
        """Quanti gamepad sono collegati."""
        return len(self._pad)

    # ---- gamepad: menu

    def _giocatore_pad(self, pad: _Pad) -> Optional[int]:
        if self._modalita_menu() == "singolo":
            return 0
        slot = self._pad.index(pad)
        return slot if slot < 2 else None

    def _menu_pad(self, pad: _Pad, azione: str) -> None:
        g = self._giocatore_pad(pad)
        if g is not None:
            self._menu.append((g, azione))

    def _fronti_direzioni(self, pad: _Pad, prima: Set[str]) -> None:
        for d in ("su", "giu", "sinistra", "destra"):
            if d in pad.direzioni() and d not in prima:
                self._menu_pad(pad, _AZIONE_DA_DIREZIONE[d])

    # ---- lettura

    def comandi(self, giocatore: int, modalita: str) -> Comandi:
        """Comandi tenuti premuti ora dal giocatore (0 = P1, 1 = P2).

        'singolo': un solo umano (giocatore 0), tastiera completa e qualunque
        pad; il giocatore 1 e' la CPU e riceve comandi vuoti.
        'doppio': P1 = WASD (+ primo pad), P2 = frecce/tastierino (+ secondo pad).
        """
        if modalita not in _MODALITA:
            raise ValueError("modalita' sconosciuta: %r" % (modalita,))
        if giocatore not in (0, 1):
            return Comandi()
        if modalita == "singolo":
            if giocatore == 1:
                return Comandi()
            c = self._da_tastiera(LAYOUT_SINGOLO)
            for pad in self._pad:
                c = c.unisci(pad.comandi())
            return c
        layout = LAYOUT_DOPPIO_P1 if giocatore == 0 else LAYOUT_DOPPIO_P2
        c = self._da_tastiera(layout)
        if giocatore < len(self._pad):
            c = c.unisci(self._pad[giocatore].comandi())
        return c

    @staticmethod
    def _da_tastiera(layout: Dict[str, Tuple[int, ...]]) -> Comandi:
        try:
            tasti = pygame.key.get_pressed()
        except pygame.error:
            return Comandi()
        c = Comandi()
        for campo in _CAMPI_COMANDI:
            for k in layout[campo]:
                try:
                    premuto = tasti[k]
                except (IndexError, KeyError):
                    premuto = False
                if premuto:
                    setattr(c, campo, True)
                    break
        return c

    def azioni_menu(self) -> List[Tuple[int, str]]:
        """(giocatore, azione) scattate in questo frame, senza duplicati (copia).

        Con `modalita_menu = 'doppio'` la tastiera e' divisa (WASD/F/Spazio ->
        giocatore 0, frecce/Invio/J -> giocatore 1); con 'singolo' o None tutta
        la tastiera e' il giocatore 0. I pad seguono l'ordine di collegamento
        (primo -> 0, secondo -> 1; in 'singolo' tutti -> 0).
        """
        visti: Set[Tuple[int, str]] = set()
        ris: List[Tuple[int, str]] = []
        for voce in self._menu:
            if voce not in visti:
                visti.add(voce)
                ris.append(voce)
        return ris

    def fine_frame(self) -> None:
        """Azzera i fronti di salita (azioni di menu) del frame."""
        self._menu.clear()

    # ---- descrizione per la schermata Comandi

    def descrizione_comandi(self, modalita: str) -> dict:
        """Testi italiani per la schermata Comandi.

        Formato: {'modalita', 'titolo', 'gamepad_collegati',
                  'sezioni': [{'titolo': str, 'righe': [(azione, tasti), ...]}, ...],
                  'note': [str, ...]}
        """
        if modalita not in _MODALITA:
            raise ValueError("modalita' sconosciuta: %r" % (modalita,))
        sezioni: List[dict] = []
        if modalita == "singolo":
            titolo = "COMANDI - 1 GIOCATORE"
            sezioni.append({"titolo": "TASTIERA", "righe": [
                ("Movimento", "W A S D  oppure  Frecce"),
                ("Jab", "J  oppure  F"),
                ("Diretto", "K  oppure  G"),
                ("Calcio basso", "U  oppure  R"),
                ("Calcio alto", "I  oppure  T"),
                ("Guardia", "L  oppure  H"),
                ("Schivata", "Spazio  oppure  V"),
                ("Speciale", "O  oppure  Y"),
            ]})
            sezioni.append({"titolo": "GAMEPAD XBOX (QUALUNQUE)", "righe": list(_RIGHE_PAD)})
        else:
            titolo = "COMANDI - 2 GIOCATORI"
            sezioni.append({"titolo": "GIOCATORE 1 - TASTIERA", "righe": [
                ("Movimento", "W A S D"),
                ("Jab", "F"),
                ("Diretto", "G"),
                ("Calcio basso", "R"),
                ("Calcio alto", "T"),
                ("Guardia", "H"),
                ("Schivata", "V"),
                ("Speciale", "Y"),
            ]})
            sezioni.append({"titolo": "GIOCATORE 2 - TASTIERA", "righe": [
                ("Movimento", "Frecce"),
                ("Jab", "J  oppure  Tastierino 1"),
                ("Diretto", "K  oppure  Tastierino 2"),
                ("Calcio basso", "U  oppure  Tastierino 4"),
                ("Calcio alto", "I  oppure  Tastierino 5"),
                ("Guardia", "L  oppure  Tastierino 0"),
                ("Schivata", "M  oppure  Tastierino 3"),
                ("Speciale", "O  oppure  Tastierino 6"),
            ]})
            sezioni.append({"titolo": "GAMEPAD XBOX (1o PAD = P1, 2o PAD = P2)",
                            "righe": list(_RIGHE_PAD)})
        sezioni.append({"titolo": "MENU", "righe": [
            ("Muoversi", "Frecce  oppure  W A S D  /  Croce o stick"),
            ("Conferma", "Invio, Spazio, J, F  /  Pulsante A"),
            ("Indietro", "Esc, Backspace  /  Pulsante B"),
            ("Pausa", "Esc  oppure  P  /  Start"),
        ]})
        note = [
            "Su e giu' spostano il lottatore in profondita' sul ring.",
            "Schivata con su/giu = schivata laterale; senza direzione = indietro.",
            "Il colpo speciale richiede la barra energia piena.",
        ]
        if modalita == "doppio":
            note.append("Nel menu il giocatore 1 usa WASD/F/Spazio, il giocatore 2 le frecce/Invio/J.")
        n = self.numero_gamepad()
        if n == 0:
            note.append("Nessun gamepad collegato: puoi collegarlo in qualsiasi momento.")
        elif n == 1:
            note.append("1 gamepad collegato.")
        else:
            note.append("%d gamepad collegati." % n)
        return {
            "modalita": modalita,
            "titolo": titolo,
            "gamepad_collegati": n,
            "sezioni": sezioni,
            "note": note,
        }


_RIGHE_PAD = (
    ("Movimento", "Stick sinistro  oppure  Croce"),
    ("Jab", "X"),
    ("Diretto", "Y"),
    ("Calcio basso", "A"),
    ("Calcio alto", "B"),
    ("Guardia", "RB"),
    ("Schivata", "LB"),
    ("Speciale", "Grilletto destro (RT)"),
    ("Pausa", "Start"),
)
