"""Schermate (scene) dei menu: titolo, menu principale, difficolta', selezione dei
lottatori, pausa, risultati e comandi.

Ogni scena espone la stessa interfaccia:

    scena.prossima      None finche' la scena non vuole cambiare; poi (nome_scena, {parametri})
    scena.gestisci(azioni)   azioni = [(giocatore, AzioneMenu.X), ...]
    scena.aggiorna(dt)       dt in secondi
    scena.disegna(superficie)

Le dipendenze pesanti sono iniettate nel costruttore (uguali per tutte le scene):
    sfondo(superficie, tempo)   disegna l'arena di sfondo (opzionale)
    anteprima(superficie, personaggio, centro, altezza_px, posa, tempo,
              guarda_destra, palette_alternativa)     (RendererLottatore.disegna_anteprima)
    suono(nome)                 'ui_muovi' | 'ui_conferma' | 'ui_indietro'
Tutte e tre sono opzionali: senza, la scena usa un ripiego semplice.
"""

from __future__ import annotations

import math
import random
import re
from typing import Callable, Optional

import pygame

from .. import costanti as C
from ..personaggi import ROSTER, Personaggio, PER_ID
from . import stile as S

try:                                             # costanti di azione del modulo input
    from ..input import AzioneMenu as _AzioneMenu
    SU, GIU = _AzioneMenu.SU, _AzioneMenu.GIU
    SINISTRA, DESTRA = _AzioneMenu.SINISTRA, _AzioneMenu.DESTRA
    CONFERMA, INDIETRO, PAUSA = _AzioneMenu.CONFERMA, _AzioneMenu.INDIETRO, _AzioneMenu.PAUSA
except Exception:                                # pragma: no cover - ripiego
    SU, GIU, SINISTRA, DESTRA = "su", "giu", "sinistra", "destra"
    CONFERMA, INDIETRO, PAUSA = "conferma", "indietro", "pausa"

L, A = C.LARGHEZZA, C.ALTEZZA

# ---- nomi delle scene (valori di `prossima`)
SCENA_TITOLO = 'titolo'
SCENA_MENU = 'menu_principale'
SCENA_DIFFICOLTA = 'scelta_difficolta'
SCENA_SELEZIONE = 'selezione_personaggi'
SCENA_COMBATTIMENTO = 'combattimento'
SCENA_COMANDI = 'comandi'
SCENA_PAUSA = 'menu_pausa'
SCENA_RISULTATI = 'risultati'
SCENA_RIPRENDI = 'riprendi'
SCENA_RICOMINCIA = 'ricomincia'
SCENA_ESCI = 'esci'

DIFFICOLTA = ('facile', 'normale', 'difficile', 'campione')
MODALITA = ('singolo', 'doppio', 'cpu')

ROSSO = S.ROSSO_K1
COL_DIFFICOLTA = {'facile': (72, 206, 110), 'normale': (64, 170, 250), 'difficile': (252, 150, 50),
                  'campione': (240, 50, 62)}
DESC_DIFFICOLTA = {
    'facile': ("Reazioni lente, molti errori.", "Ideale per imparare i colpi e le combo."),
    'normale': ("Avversario equilibrato.", "Para, punisce i colpi a vuoto e concatena."),
    'difficile': ("Reazioni rapide e schivate.", "Conferma le combo e non concede errori."),
    'campione': ("Il livello massimo.", "Quasi perfetto: solo per i veri campioni."),
}
STAT_PERSONAGGIO = (("POTENZA", 'potenza'), ("VELOCITÀ", 'velocita'), ("RESISTENZA", 'resistenza'),
                    ("FIATO", 'fiato'), ("PORTATA", 'portata'))


# ---- utilita'
def _norma(azione) -> str:
    return str(azione).lower()


def _accento(p: Personaggio) -> tuple:
    return tuple(p.colore_ui[:3])


def _valore_stat(p: Personaggio, chiave: str) -> float:
    """Statistica del personaggio normalizzata su 0..1 (0.80 -> 0, 1.25 -> 1)."""
    return S.limita((getattr(p, chiave) - 0.80) / 0.45)


def _adatta(s: pygame.Surface, larghezza_max: float) -> pygame.Surface:
    if s.get_width() <= larghezza_max:
        return s
    return S.scala_superficie(s, larghezza_max / s.get_width())


def _avvolgi(stringa: str, dimensione: int, larghezza: int) -> list:
    """Spezza una frase in righe che stanno in `larghezza` pixel."""
    f = S.font(dimensione)
    righe, corrente = [], ""
    for parola in stringa.split():
        prova = (corrente + " " + parola).strip()
        if f.size(prova)[0] <= larghezza or not corrente:
            corrente = prova
        else:
            righe.append(corrente)
            corrente = parola
    if corrente:
        righe.append(corrente)
    return righe


def _sfumatura_accento(colore: tuple) -> tuple:
    c = S.accento_leggibile(colore)
    return ((0.0, S.schiarisci(c, 0.75)), (0.42, S.schiarisci(c, 0.22)), (0.58, c),
            (1.0, S.scurisci(c, 0.28)))


def _chip(testo: str, colore: tuple, dimensione: int = 22, colore_testo: tuple = S.BIANCO) -> pygame.Surface:
    """Etichetta inclinata compatta (es. "1P", "CPU", "PRONTO")."""
    chiave = ('chip', testo, tuple(colore), dimensione, tuple(colore_testo))

    def crea():
        t = S.testo(testo, dimensione, colore_testo, corsivo=True, contorno=2, ombra=(1, 2))
        w, h = t.get_width() + 30, t.get_height() + 4
        pan = S.pannello(w, h, -10, -10, stop=((0.0, S.schiarisci(colore, 0.3)), (0.5, colore),
                                                (1.0, S.scurisci(colore, 0.5))),
                         alpha=255, bordo=S.INCHIOSTRO, spessore=2, lucido=0.3)
        pan = pan.copy()
        pan.blit(t, t.get_rect(center=(w // 2, h // 2)))
        return pan
    return S._in_cache(chiave, crea)


def _cornice(w: int, h: int, inclina: int, colore: tuple, spessore: int = 4) -> pygame.Surface:
    """Solo il bordo (cavo) di un parallelogramma inclinato: per i cursori di selezione."""
    chiave = ('cornice', w, h, inclina, tuple(colore), spessore)

    def crea():
        esterno = S.forma(w, h, inclina, inclina)
        s = S.tinta(S.maschera_poligono(w, h, esterno), colore)
        cava = S.maschera_poligono(w, h, S.rientra(esterno, spessore)).copy()
        cava.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)      # solo alpha
        s.blit(cava, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        return S._ottimizza(s)
    return S._in_cache(chiave, crea)


def _segnaposto(sup, p, centro, altezza_px, posa, tempo, guarda_destra, alt) -> None:
    """Sagoma semplice usata quando non e' stata iniettata un'anteprima."""
    cx, cy = centro
    h = altezza_px
    s = 1 if guarda_destra else -1
    col = tuple(S.scurisci(p.colore_ui, 0.35))
    pygame.draw.ellipse(sup, col, pygame.Rect(cx - h * 0.16, cy + h * 0.5 - h * 0.03, h * 0.32, h * 0.06))
    pygame.draw.polygon(sup, col, [(cx - h * 0.16, cy - h * 0.25), (cx + h * 0.16, cy - h * 0.25),
                                   (cx + h * 0.12, cy + h * 0.5), (cx - h * 0.12, cy + h * 0.5)])
    pygame.draw.circle(sup, col, (int(cx + s * h * 0.02), int(cy - h * 0.36)), int(h * 0.075))


class _Scintille:
    """Scintille dorate che salgono lente (decorazione dei titoli)."""

    def __init__(self, n: int = 46, seme: int = 5):
        r = random.Random(seme)
        self.p = [(r.uniform(0, L), r.uniform(0, A), r.uniform(14, 46), r.uniform(0, 6.28),
                   r.uniform(0.5, 1.0), r.choice((6, 8, 10))) for _ in range(n)]

    def disegna(self, sup: pygame.Surface, t: float, colore: tuple = (255, 190, 80),
                forza: float = 1.0) -> None:
        for x0, y0, v, ph, k, d in self.p:
            y = (y0 - t * v) % (A + 40) - 20
            x = x0 + math.sin(t * 0.7 + ph) * 22
            lu = k * (0.5 + 0.5 * math.sin(t * 2.2 + ph)) * forza
            if lu < 0.1:
                continue
            g = S.alone(d, d, colore, _q(lu, 5))
            sup.blit(g, (int(x - d / 2), int(y - d / 2)), special_flags=pygame.BLEND_RGB_ADD)


def _q(v: float, passi: int) -> float:
    return round(S.limita(v) * passi) / passi


class _Lista:
    """Elenco verticale (o orizzontale) di voci a pannello inclinato con selezione animata."""

    def __init__(self, voci, x: int, y: int, larghezza: int = 470, altezza: int = 62,
                 passo: int = 76, dimensione: int = 34, colore: tuple = ROSSO,
                 orizzontale: bool = False, scarto: int = 26, inclina: int = 18):
        self.voci = list(voci)
        self.x, self.y = x, y
        self.larghezza, self.altezza, self.passo = larghezza, altezza, passo
        self.dimensione = dimensione
        self.colore = colore
        self.orizzontale = orizzontale
        self.scarto = scarto
        self.inclina = inclina
        self.indice = 0
        self.peso = [1.0 if i == 0 else 0.0 for i in range(len(self.voci))]
        self.abilitate = [True] * len(self.voci)

    def muovi(self, d: int) -> bool:
        n = len(self.voci)
        for _ in range(n):
            self.indice = (self.indice + d) % n
            if self.abilitate[self.indice]:
                return True
        return False

    def aggiorna(self, dt: float) -> None:
        k = 1.0 - math.exp(-dt * 16.0)
        for i in range(len(self.voci)):
            bersaglio = 1.0 if i == self.indice else 0.0
            self.peso[i] += (bersaglio - self.peso[i]) * k

    def disegna(self, sup: pygame.Surface, t: float, colore: Optional[tuple] = None) -> None:
        colore = colore or self.colore
        w, h, inc = self.larghezza, self.altezza, self.inclina
        base = S.pannello(w, h, inc, inc, stop=((0.0, (30, 34, 54)), (1.0, (12, 14, 24))), alpha=205,
                          bordo=S.ACCIAIO, spessore=2)
        sel = S.pannello(w, h, inc, inc, stop=((0.0, S.schiarisci(colore, 0.42)), (0.48, colore),
                                               (1.0, S.scurisci(colore, 0.55))),
                         alpha=255, bordo=S.mescola(colore, (255, 255, 255), 0.78), spessore=3,
                         lucido=0.3)
        for i, voce in enumerate(self.voci):
            e = S.ease_out_cubic((t - 0.07 * i) / 0.34)
            if e <= 0.0:
                continue
            peso = self.peso[i]
            ok = self.abilitate[i]
            if self.orizzontale:
                x = self.x + i * self.passo
                y = self.y + (1 - e) * 90 - peso * 8
            else:
                x = self.x - (1 - e) * (w + self.x + 80) + peso * self.scarto
                y = self.y + i * self.passo
            pos = (int(x), int(y))
            sup.blit(base, pos)
            if peso > 0.02:
                if peso > 0.35:
                    bag = S.alone(w + 70, h + 60, colore, _q(0.5 * peso, 6))
                    sup.blit(bag, (pos[0] - 35, pos[1] - 30), special_flags=pygame.BLEND_RGB_ADD)
                S.blit_alpha(sup, sel, pos, 255 * peso)
            if peso > 0.5 and ok:
                s = S.testo(voce, self.dimensione, S.BIANCO, corsivo=True, contorno=3, ombra=(2, 3))
            else:
                s = S.testo(voce, self.dimensione, S.ARGENTO if ok else (90, 96, 118), corsivo=True,
                            contorno=3, ombra=(2, 3))
            s = _adatta(s, (w - 2 * inc - 24) if self.orizzontale else (w - inc - 70))
            if self.orizzontale:
                sup.blit(s, s.get_rect(center=(pos[0] + w // 2, pos[1] + h // 2)))
            else:
                sup.blit(s, s.get_rect(midleft=(pos[0] + inc + 34, pos[1] + h // 2 + 1)))
                if peso > 0.05:
                    fr = S.freccia(22, S.mescola(colore, (255, 255, 255), 0.85))
                    dx = int(math.sin(t * 7.0) * 3 * peso)
                    S.blit_alpha(sup, fr, (pos[0] + inc - 2 + dx, pos[1] + h // 2 - 11), 255 * peso)


# ---- scena di base
class Scena:
    """Base delle scene. Le sottoclassi ridefiniscono `azione`, `aggiorna` e `disegna`."""

    nome = ''

    def __init__(self, sfondo: Optional[Callable] = None, anteprima: Optional[Callable] = None,
                 suono: Optional[Callable] = None):
        self.sfondo = sfondo
        self.anteprima = anteprima or _segnaposto
        self._suono = suono
        self.prossima: Optional[tuple] = None
        self.t = 0.0

    # ---- interfaccia pubblica
    def gestisci(self, azioni) -> None:
        for giocatore, azione in azioni:
            self.azione(giocatore, _norma(azione))

    def aggiorna(self, dt: float) -> None:
        self.t += min(max(dt, 0.0), 0.1)

    def disegna(self, superficie: pygame.Surface) -> None:
        self._disegna_sfondo(superficie)

    # ---- per le sottoclassi
    def azione(self, giocatore: int, azione: str) -> None:
        pass

    def _vai(self, nome: str, **parametri) -> None:
        if self.prossima is None:
            self.prossima = (nome, dict(parametri))

    def suona(self, nome: str) -> None:
        if self._suono is not None:
            try:
                self._suono(nome)
            except Exception:
                pass

    def _disegna_sfondo(self, sup: pygame.Surface, velo: int = 120) -> None:
        if self.sfondo is not None:
            self.sfondo(sup, self.t)
        else:
            sup.blit(S.sfondo_scuro(L, A), (0, 0))
        if velo:
            sup.blit(S.velo(L, A, (3, 4, 10), velo), (0, 0))
        sup.blit(S.vignetta(L, A, 0.95), (0, 0))

    # ---- elementi comuni
    def _intestazione(self, sup: pygame.Surface, titolo: str, sotto: str = "", x: int = 56,
                      y: int = 34, colore: tuple = ROSSO) -> None:
        e = S.ease_out_cubic(self.t / 0.45)
        s = S.testo(titolo, 60, S.BIANCO, sfumatura_testo=S.SFUMATURA_BIANCO, corsivo=True, contorno=4,
                    ombra=(3, 5), spaziatura=2)
        s = _adatta(s, L - 2 * x - 40)
        S.blit_alpha(sup, s, (int(x - (1 - e) * 240), y), 255 * e)
        lw = int((s.get_width() + 30) * e)
        if lw > 6:
            sup.blit(S.pannello(lw, 8, -8, -8, stop=((0.0, S.schiarisci(colore, 0.3)),
                                                     (1.0, S.scurisci(colore, 0.3))), alpha=255),
                     (x - 6, y + s.get_height() + 2))
            sup.blit(S.pannello(max(8, lw // 4), 4, -4, -4, colore=S.ORO, alpha=255),
                     (x - 6 + 10, y + s.get_height() + 14))
        if sotto:
            S.scrivi(sup, sotto, (x + 4, y + s.get_height() + 34), 24, S.SPENTO, 'topleft',
                     alpha=255 * S.progresso(self.t, 0.2, 0.4), corsivo=True, contorno=2,
                     ombra=(1, 2), spaziatura=2)

    def _suggerimenti(self, sup: pygame.Surface, voci, y: int = A - 40, x: Optional[int] = None,
                      allinea: str = 'right', alpha: float = 255) -> None:
        """Riga di suggerimenti: [(etichetta_tasto, testo), ...]."""
        elementi = []
        for tasto, testo in voci:
            cap = S.tasto(tasto, 28)
            tx = S.testo(testo, 22, S.ARGENTO, contorno=2, ombra=(1, 2))
            elementi.append((cap, tx))
        totale = sum(c.get_width() + 8 + t.get_width() + 26 for c, t in elementi) - 26
        if x is None:
            x = L - 50 - totale if allinea == 'right' else (L - totale) // 2
        for cap, tx in elementi:
            S.blit_alpha(sup, cap, (x, y - cap.get_height() // 2), alpha)
            x += cap.get_width() + 8
            S.blit_alpha(sup, tx, (x, y - tx.get_height() // 2 + 1), alpha)
            x += tx.get_width() + 26

    def _lottatore(self, sup: pygame.Surface, p: Personaggio, centro: tuple, altezza: float,
                   posa: str = 'guardia', destra: bool = True, alt: bool = False,
                   tempo: Optional[float] = None) -> None:
        """Disegna un'anteprima del lottatore; un guasto dell'anteprima non blocca il menu."""
        try:
            self.anteprima(sup, p, centro, altezza * p.altezza, posa,
                           self.t if tempo is None else tempo, destra, alt)
        except Exception:
            _segnaposto(sup, p, centro, altezza * p.altezza, posa, self.t, destra, alt)

    def _lampo(self, sup: pygame.Surface, t0: float, durata: float = 0.35, forza: int = 200) -> None:
        k = 1.0 - S.progresso(self.t, t0, durata)
        if 0.0 < k < 1.0:
            sup.blit(S.velo(L, A, (255, 255, 255), int(forza * k * k)), (0, 0))

    def _luce_accento(self, sup, centro, colore, w=760, h=620, k=0.8) -> None:
        sup.blit(S.alone(w, h, colore, _q(k, 8)), (centro[0] - w // 2, centro[1] - h // 2),
                 special_flags=pygame.BLEND_RGB_ADD)


# ---- titolo
class SchermataTitolo(Scena):
    """Logo animato e "PREMI INVIO".

    prossima: CONFERMA -> ('menu_principale', {})
    """

    nome = SCENA_TITOLO

    def __init__(self, sfondo=None, anteprima=None, suono=None):
        super().__init__(sfondo, anteprima, suono)
        self._scintille = _Scintille()
        self._lampo_dato = False
        self._prima_coppia = (0, 1)

    def azione(self, giocatore: int, azione: str) -> None:
        if azione == CONFERMA:
            self.suona('ui_conferma')
            self._vai(SCENA_MENU)

    # ---- disegno
    def _coppia(self) -> tuple:
        ciclo = int(self.t / 6.0)
        a = ciclo % len(ROSTER)
        b = (a + 1 + (ciclo // len(ROSTER)) % (len(ROSTER) - 1)) % len(ROSTER)
        return a, b

    def disegna(self, sup: pygame.Surface) -> None:
        self._disegna_sfondo(sup, 140)
        t = self.t
        # fasci di luce che oscillano
        for k, cx in enumerate((0.2, 0.5, 0.8)):
            f = S.fascio(520, 640, (110, 140, 230) if k != 1 else (230, 90, 100),
                         0.75 + 0.15 * math.sin(t * 0.9 + k))
            sup.blit(f, (int(L * cx - 260 + math.sin(t * 0.5 + k * 2) * 60), 0),
                     special_flags=pygame.BLEND_RGB_ADD)
        # lottatori affrontati
        a, b = self._coppia()
        ciclo_t = t % 6.0
        e = S.ease_out_cubic(ciclo_t / 0.7)
        pa, pb = ROSTER[a], ROSTER[b]
        alt = pa.id == pb.id
        self._luce_accento(sup, (250, 420), _accento(pa), 640, 560, 0.55 * e)
        self._luce_accento(sup, (L - 250, 420), _accento(pb), 640, 560, 0.55 * e)
        self._lottatore(sup, pa, (int(250 - (1 - e) * 240), 470), 470, 'guardia', True, False)
        self._lottatore(sup, pb, (int(L - 250 + (1 - e) * 240), 470), 470, 'guardia', False, alt)
        self._scintille.disegna(sup, t)
        self._logo(sup)
        # PREMI INVIO
        entra = S.progresso(t, 1.5, 0.6)
        if entra > 0:
            pulsa = S.pulsa(t, 0.8, 0.45, 1.0)
            s = S.testo("PREMI INVIO", 54, S.BIANCO, sfumatura_testo=S.SFUMATURA_BIANCO, corsivo=True,
                        contorno=4, ombra=(3, 4), spaziatura=6)
            y = 606
            lw = int(300 * S.ease_out_cubic(entra))
            for sgn in (-1, 1):
                sup.blit(S.pannello(max(8, lw), 4, -4, -4, colore=S.ORO, alpha=int(200 * pulsa)),
                         (L // 2 - (lw + s.get_width() // 2 + 20 if sgn < 0 else -s.get_width() // 2 - 20),
                          y - 2))
            S.piazza(sup, s, (L // 2, y), 'center', 255 * pulsa * entra)
            self._suggerimenti(sup, [("INVIO", "Inizia"), ("ESC", "Esci")], A - 40, allinea='centro',
                               alpha=200 * entra)
        self._lampo(sup, 0.42, 0.5, 230)

    def _logo(self, sup: pygame.Surface) -> None:
        t = self.t
        # KICKBOXING
        e1 = S.ease_out_cubic((t - 0.1) / 0.5)
        kb = S.testo("KICKBOXING", 104, S.BIANCO, sfumatura_testo=S.SFUMATURA_ARGENTO, corsivo=True,
                     contorno=5, colore_contorno=(28, 34, 66), contorno_esterno=3, ombra=(4, 6),
                     spaziatura=10)
        kb = _adatta(kb, 760)
        S.piazza(sup, kb, (L // 2 - (1 - e1) * 700, 130), 'center', 255 * e1)
        # K1
        if t >= 0.0:
            u = (t - 0.2) / 0.5
            scala = 1.0 + 2.2 * (1 - S.ease_out_cubic(u)) if u < 1 else 1.0 + 0.012 * math.sin(t * 1.6)
            k1 = S.testo("K1", 330, ROSSO, sfumatura_testo=S.SFUMATURA_ROSSO, corsivo=True, contorno=9,
                         colore_contorno=(255, 255, 255), contorno_esterno=5,
                         colore_esterno=S.INCHIOSTRO, ombra=(6, 10))
            alpha = 255 * S.limita(u * 3)
            r = S.piazza(sup, k1, (L // 2, 318), 'center', alpha, scala)
            # riflesso che attraversa il logo
            ciclo = (t - 1.2) % 4.5
            if t > 1.0 and ciclo < 1.1 and u >= 1:
                self._sweep(sup, k1, r, ciclo / 1.1)
        # fascia sottotitolo
        e2 = S.ease_out_cubic((t - 0.9) / 0.5)
        if e2 > 0:
            band = S.pannello(470, 44, -14, -14, stop=((0.0, S.schiarisci(S.ORO, 0.2)), (0.5, S.ORO),
                                                       (1.0, S.scurisci(S.ORO, 0.5))),
                              alpha=255, bordo=S.INCHIOSTRO, spessore=3, lucido=0.35)
            S.blit_alpha(sup, band, (L // 2 - 235, 468 + int((1 - e2) * 30)), 255 * e2)
            S.scrivi(sup, "CAMPIONATO MONDIALE", (L // 2, 490 + int((1 - e2) * 30)), 30,
                     (40, 20, 6), 'center', alpha=255 * e2, corsivo=True, contorno=0, ombra=None,
                     spaziatura=5)

    def _sweep(self, sup: pygame.Surface, testo: pygame.Surface, rect: pygame.Rect, p: float) -> None:
        """Banda luminosa diagonale che scorre sul testo (si vede solo sui glifi)."""
        w, h = testo.get_size()
        band = pygame.Surface((w, h))
        band.fill((0, 0, 0))
        x = -w * 0.3 + p * w * 1.6
        pygame.draw.polygon(band, (200, 200, 200), [(x, 0), (x + w * 0.16, 0), (x + w * 0.16 - h * 0.35, h),
                                                    (x - h * 0.35, h)])
        pygame.draw.polygon(band, (255, 255, 255), [(x + w * 0.05, 0), (x + w * 0.11, 0),
                                                    (x + w * 0.11 - h * 0.35, h), (x + w * 0.05 - h * 0.35, h)])
        lum = testo.copy()
        lum.blit(band, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        sup.blit(lum, rect.topleft, special_flags=pygame.BLEND_RGB_ADD)


# ---- menu principale
class MenuPrincipale(Scena):
    """Menu principale.

    prossima:
      "1 GIOCATORE"    -> ('scelta_difficolta', {'modalita': 'singolo'})
      "2 GIOCATORI"    -> ('selezione_personaggi', {'modalita': 'doppio', 'difficolta': None})
      "CPU CONTRO CPU" -> ('scelta_difficolta', {'modalita': 'cpu'})
      "COMANDI"        -> ('comandi', {'ritorno': 'menu_principale'})
      "ESCI"           -> ('esci', {})
      INDIETRO         -> ('titolo', {})
    """

    nome = SCENA_MENU
    VOCI = ("1 GIOCATORE", "2 GIOCATORI", "CPU CONTRO CPU", "COMANDI", "ESCI")
    DESCRIZIONI = (
        "Affronta la CPU e scala il campionato.",
        "Sfida un amico: due giocatori, stessa tastiera o due gamepad.",
        "Guarda due lottatori controllati dalla CPU.",
        "Tasti della tastiera e del gamepad.",
        "Chiudi il gioco.",
    )

    def __init__(self, sfondo=None, anteprima=None, suono=None):
        super().__init__(sfondo, anteprima, suono)
        self.lista = _Lista(self.VOCI, 64, 250, 480, 62, 76, 36, ROSSO)
        self._scintille = _Scintille(30, 11)

    @property
    def indice(self) -> int:
        return self.lista.indice

    def azione(self, giocatore: int, azione: str) -> None:
        if azione in (SU, GIU):
            if self.lista.muovi(-1 if azione == SU else 1):
                self.suona('ui_muovi')
        elif azione == CONFERMA:
            self.suona('ui_conferma')
            i = self.lista.indice
            if i == 0:
                self._vai(SCENA_DIFFICOLTA, modalita='singolo')
            elif i == 1:
                self._vai(SCENA_SELEZIONE, modalita='doppio', difficolta=None)
            elif i == 2:
                self._vai(SCENA_DIFFICOLTA, modalita='cpu')
            elif i == 3:
                self._vai(SCENA_COMANDI, ritorno=SCENA_MENU)
            else:
                self._vai(SCENA_ESCI)
        elif azione == INDIETRO:
            self.suona('ui_indietro')
            self._vai(SCENA_TITOLO)

    def aggiorna(self, dt: float) -> None:
        super().aggiorna(dt)
        self.lista.aggiorna(min(dt, 0.1))

    def disegna(self, sup: pygame.Surface) -> None:
        self._disegna_sfondo(sup, 135)
        t = self.t
        # fighter a destra che ruota nel roster
        ciclo = int(t / 5.0)
        p = ROSTER[ciclo % len(ROSTER)]
        tc = t % 5.0
        e = S.ease_out_cubic(tc / 0.6)
        uscita = 1.0 - S.progresso(tc, 4.6, 0.4)
        self._luce_accento(sup, (930, 400), _accento(p), 780, 640, 0.7 * e * uscita)
        self._scintille.disegna(sup, t, _accento(p), 0.8)
        if uscita > 0.02:
            self._lottatore(sup, p, (int(930 + (1 - e) * 200 + (1 - uscita) * 120), 430), 500, 'guardia',
                            False)
        # logo
        e_l = S.ease_out_cubic(t / 0.5)
        k1 = S.testo("K1", 130, ROSSO, sfumatura_testo=S.SFUMATURA_ROSSO, corsivo=True, contorno=5,
                     colore_contorno=(255, 255, 255), contorno_esterno=3, ombra=(3, 5))
        kb = S.testo("KICKBOXING", 44, S.BIANCO, sfumatura_testo=S.SFUMATURA_ARGENTO, corsivo=True,
                     contorno=3, ombra=(2, 3), spaziatura=6)
        S.blit_alpha(sup, k1, (int(58 - (1 - e_l) * 200), 34), 255 * e_l)
        S.blit_alpha(sup, kb, (int(58 + k1.get_width() + 12 - (1 - e_l) * 200), 62), 255 * e_l)
        S.scrivi(sup, "CAMPIONATO MONDIALE", (int(58 + k1.get_width() + 14 - (1 - e_l) * 200), 118), 22,
                 S.ORO, 'topleft', alpha=255 * e_l, corsivo=True, contorno=2, ombra=(1, 2), spaziatura=3)
        self.lista.disegna(sup, t)
        # descrizione della voce
        i = self.lista.indice
        S.scrivi(sup, self.DESCRIZIONI[i], (72, 250 + 5 * 76 + 8), 24, S.ARGENTO, 'topleft',
                 alpha=255 * S.progresso(t, 0.5, 0.4), contorno=2, ombra=(1, 2))
        self._suggerimenti(sup, [("INVIO", "Conferma"), ("ESC", "Indietro")])


# ---- difficolta'
class SceltaDifficolta(Scena):
    """Scelta della difficolta' della CPU.

    Costruttore: SceltaDifficolta(sfondo, anteprima, suono, modalita='singolo')
    prossima:
      CONFERMA -> ('selezione_personaggi', {'modalita': modalita,
                                            'difficolta': 'facile'|'normale'|'difficile'|'campione'})
      INDIETRO -> ('menu_principale', {})
    """

    nome = SCENA_DIFFICOLTA
    ETICHETTE = ("FACILE", "NORMALE", "DIFFICILE", "CAMPIONE")

    def __init__(self, sfondo=None, anteprima=None, suono=None, modalita: str = 'singolo'):
        super().__init__(sfondo, anteprima, suono)
        self.modalita = modalita
        self.lista = _Lista(self.ETICHETTE, 64, 210, 470, 70, 88, 40, ROSSO)
        self.lista.indice = 1
        self.lista.peso = [0.0, 1.0, 0.0, 0.0]
        self._livello = 1.0
        self._scintille = _Scintille(24, 3)

    @property
    def indice(self) -> int:
        return self.lista.indice

    @property
    def difficolta(self) -> str:
        return DIFFICOLTA[self.lista.indice]

    def azione(self, giocatore: int, azione: str) -> None:
        if azione in (SU, GIU):
            if self.lista.muovi(-1 if azione == SU else 1):
                self.suona('ui_muovi')
        elif azione == CONFERMA:
            self.suona('ui_conferma')
            self._vai(SCENA_SELEZIONE, modalita=self.modalita, difficolta=self.difficolta)
        elif azione == INDIETRO:
            self.suona('ui_indietro')
            self._vai(SCENA_MENU)

    def aggiorna(self, dt: float) -> None:
        super().aggiorna(dt)
        self.lista.aggiorna(min(dt, 0.1))
        self._livello += (self.lista.indice + 1 - self._livello) * (1 - math.exp(-min(dt, 0.1) * 10))

    def disegna(self, sup: pygame.Surface) -> None:
        self._disegna_sfondo(sup, 140)
        t = self.t
        col = COL_DIFFICOLTA[self.difficolta]
        # colore che cambia con la voce
        self._luce_accento(sup, (900, 380), col, 900, 700, 0.6)
        self._scintille.disegna(sup, t, col, 0.8)
        titolo = "DIFFICOLTÀ DELLE CPU" if self.modalita == 'cpu' else "DIFFICOLTÀ"
        self._intestazione(sup, titolo, "Quanto e' forte il tuo avversario?", colore=col)
        self.lista.disegna(sup, t, col)
        self._pannello_dettaglio(sup, col)
        self._suggerimenti(sup, [("INVIO", "Conferma"), ("ESC", "Indietro")])

    def _pannello_dettaglio(self, sup: pygame.Surface, col: tuple) -> None:
        e = S.ease_out_cubic((self.t - 0.25) / 0.5)
        if e <= 0:
            return
        x0, y0, w, h = 620, 190, 604, 400
        pan = S.pannello(w, h, 30, 30, stop=((0.0, (24, 28, 48)), (1.0, (8, 9, 18))), alpha=215,
                         bordo=S.mescola(col, (255, 255, 255), 0.25), spessore=3, lucido=0.1)
        S.blit_alpha(sup, pan, (int(x0 + (1 - e) * 120), y0), 255 * e)
        dx = int((1 - e) * 120)
        nome = S.testo(self.ETICHETTE[self.lista.indice], 92, col, sfumatura_testo=_sfumatura_accento(col),
                       corsivo=True, contorno=5, colore_contorno=S.scurisci(col, 0.7),
                       contorno_esterno=3, ombra=(4, 6))
        S.blit_alpha(sup, nome, (x0 + 70 + dx, y0 + 26), 255 * e)
        # misuratore a barre crescenti
        bx, base_y = x0 + 74 + dx, y0 + 268
        for k in range(4):
            hh = 34 + k * 24
            q = S.limita(self._livello - k)
            r = pygame.Rect(bx + k * 92, base_y - hh, 74, hh)
            fondo = S.pannello(74, hh, 12, 12, colore=(20, 22, 36), alpha=230, bordo=(60, 66, 92),
                               spessore=2)
            sup.blit(fondo, r.topleft)
            if q > 0.01:
                c = COL_DIFFICOLTA[DIFFICOLTA[k]]
                vivo = S.pannello(74, hh, 12, 12, stop=((0.0, S.schiarisci(c, 0.4)),
                                                       (1.0, S.scurisci(c, 0.45))),
                                  alpha=255, bordo=S.INCHIOSTRO, spessore=2, lucido=0.3)
                S.blit_alpha(sup, vivo, r.topleft, 255 * q)
        d1, d2 = DESC_DIFFICOLTA[self.difficolta]
        S.scrivi(sup, d1, (x0 + 60 + dx, y0 + 296), 28, S.BIANCO, 'topleft', alpha=255 * e,
                 corsivo=True, contorno=2, ombra=(1, 2))
        S.scrivi(sup, d2, (x0 + 60 + dx, y0 + 332), 24, S.ARGENTO, 'topleft', alpha=255 * e,
                 contorno=2, ombra=(1, 2))


# ---- selezione dei lottatori
class SelezionePersonaggi(Scena):
    """Selezione dei lottatori con ritratti animati, statistiche e sorteggio della CPU.

    Costruttore: SelezionePersonaggi(sfondo, anteprima, suono, modalita='singolo',
                                     difficolta='normale', seme=None, roster=ROSTER)
      modalita 'singolo': P1 umano sceglie, poi la CPU (P2) sorteggia con animazione;
      modalita 'doppio' : P1 e P2 scelgono in parallelo (azioni del giocatore 0 e 1);
      modalita 'cpu'    : entrambi sorteggiati dalla CPU (INVIO salta l'animazione).
    prossima:
      a scelte fatte (dopo la schermata VS) ->
          ('combattimento', {'modalita': modalita, 'difficolta': difficolta,
                             'p1': id_personaggio, 'p2': id_personaggio})
      INDIETRO senza nulla di bloccato ->
          singolo/cpu: ('scelta_difficolta', {'modalita': modalita})
          doppio:      ('menu_principale', {})
    """

    nome = SCENA_SELEZIONE
    CARTA = 186
    DURATA_VS = 2.1

    def __init__(self, sfondo=None, anteprima=None, suono=None, modalita: str = 'singolo',
                 difficolta: Optional[str] = 'normale', seme: Optional[int] = None,
                 roster=ROSTER):
        super().__init__(sfondo, anteprima, suono)
        self.roster = tuple(roster)
        self.modalita = modalita
        self.difficolta = difficolta
        self._rng = random.Random(seme)
        n = len(self.roster)
        self.cursore = [0, min(1, n - 1)]
        self.bloccato = [False, False]
        self.cpu = [modalita == 'cpu', modalita in ('singolo', 'cpu')]
        # sorteggio della CPU: per ogni giocatore CPU (t_inizio, durata, bersaglio)
        self._sorteggio = [None, None]
        self._vs_t: Optional[float] = None
        self._visto = [self.cursore[0], self.cursore[1]]
        self._t_cambio = [-9.0, -9.0]
        self._stat = [[_valore_stat(self.roster[self.cursore[k]], c) for _, c in STAT_PERSONAGGIO]
                      for k in (0, 1)]
        self._scintille = _Scintille(30, 21)
        if modalita == 'cpu':
            self._avvia_sorteggio(0, 0.6)
            self._avvia_sorteggio(1, 1.3)

    # ---- stato
    @property
    def fase(self) -> str:
        if self._vs_t is not None:
            return 'vs'
        if any(s is not None for s in self._sorteggio):
            return 'sorteggio'
        return 'scelta'

    def scelte(self) -> tuple:
        """Personaggi attualmente sotto ai cursori (P1, P2)."""
        return self.roster[self.cursore[0]], self.roster[self.cursore[1]]

    def _avvia_sorteggio(self, k: int, ritardo: float = 0.0) -> None:
        durata = 1.7 + (0.5 if k == 1 else 0.0) + self._rng.random() * 0.4
        self._sorteggio[k] = (self.t + ritardo, durata, self._rng.randrange(len(self.roster)),
                              self.cursore[k])

    def _blocca(self, k: int) -> None:
        self.bloccato[k] = True
        self._sorteggio[k] = None
        self._controlla_completo()

    def _controlla_completo(self) -> None:
        if all(self.bloccato) and self._vs_t is None:
            self._vs_t = 0.0

    def _sbloccati_umani(self) -> list:
        return [k for k in (0, 1) if not self.cpu[k]]

    # ---- input
    def azione(self, giocatore: int, azione: str) -> None:
        if self._vs_t is not None:
            if azione == CONFERMA and self._vs_t > 0.5:
                self._vs_t = max(self._vs_t, self.DURATA_VS - 0.05)
            elif azione == INDIETRO and self._vs_t < self.DURATA_VS - 0.4 and self.modalita != 'cpu':
                self._annulla_vs()
            return
        if self.modalita == 'doppio':
            k = 0 if giocatore == 0 else 1
        else:
            k = 0
        if self.modalita == 'cpu':
            if azione == CONFERMA:
                self.suona('ui_conferma')
                for j in (0, 1):
                    if self._sorteggio[j] is not None:
                        self.cursore[j] = self._sorteggio[j][2]
                    self._blocca(j)
            elif azione == INDIETRO:
                self.suona('ui_indietro')
                self._vai(SCENA_DIFFICOLTA, modalita=self.modalita)
            return
        if self.fase == 'sorteggio':
            if azione == INDIETRO:
                self.suona('ui_indietro')
                self._sorteggio = [None, None]
                self.bloccato[0] = False
            elif azione == CONFERMA:
                for j in (0, 1):
                    if self._sorteggio[j] is not None:
                        self.cursore[j] = self._sorteggio[j][2]
                        self._blocca(j)
            return
        n = len(self.roster)
        if azione in (SINISTRA, DESTRA, SU, GIU) and not self.bloccato[k]:
            c = self.cursore[k]
            col, riga = c % 2, c // 2
            if azione == SINISTRA:
                col = (col - 1) % 2
            elif azione == DESTRA:
                col = (col + 1) % 2
            elif azione == SU:
                riga = (riga - 1) % max(1, (n + 1) // 2)
            else:
                riga = (riga + 1) % max(1, (n + 1) // 2)
            nuovo = min(n - 1, riga * 2 + col)
            if nuovo != c:
                self.cursore[k] = nuovo
                self.suona('ui_muovi')
        elif azione == CONFERMA and not self.bloccato[k]:
            self.suona('ui_conferma')
            self.bloccato[k] = True
            if self.modalita == 'singolo':
                self._avvia_sorteggio(1, 0.35)
            self._controlla_completo()
        elif azione == INDIETRO:
            self.suona('ui_indietro')
            if self.bloccato[k]:
                self.bloccato[k] = False
            elif self.modalita == 'doppio':
                self._vai(SCENA_MENU)
            else:
                self._vai(SCENA_DIFFICOLTA, modalita=self.modalita)

    def _annulla_vs(self) -> None:
        self._vs_t = None
        self.suona('ui_indietro')
        for k in (0, 1):
            if not self.cpu[k]:
                self.bloccato[k] = False
        if self.modalita == 'singolo':
            self.bloccato[1] = False
            self._sorteggio = [None, None]

    # ---- animazione
    def aggiorna(self, dt: float) -> None:
        dt = min(max(dt, 0.0), 0.1)
        super().aggiorna(dt)
        for k in (0, 1):
            s = self._sorteggio[k]
            if s is None:
                continue
            inizio, durata, bersaglio, _ = s
            u = (self.t - inizio) / durata
            if u < 0:
                continue
            if u >= 1.0:
                self.cursore[k] = bersaglio
                self._sorteggio[k] = None
                self.bloccato[k] = True
                self.suona('ui_conferma')
                self._controlla_completo()
                continue
            # cursore che scorre rallentando verso il bersaglio
            n = len(self.roster)
            idx = (bersaglio + int((1.0 - S.ease_out_cubic(u)) * 22)) % n
            if idx != self.cursore[k]:
                self.cursore[k] = idx
                self.suona('ui_muovi')
        for k in (0, 1):
            if self.cursore[k] != self._visto[k]:
                self._visto[k] = self.cursore[k]
                self._t_cambio[k] = self.t
            bersaglio = [_valore_stat(self.roster[self.cursore[k]], c) for _, c in STAT_PERSONAGGIO]
            for j, v in enumerate(bersaglio):
                self._stat[k][j] += (v - self._stat[k][j]) * (1 - math.exp(-dt * 12))
        if self._vs_t is not None:
            self._vs_t += dt
            if self._vs_t >= self.DURATA_VS and self.prossima is None:
                p1, p2 = self.scelte()
                self._vai(SCENA_COMBATTIMENTO, modalita=self.modalita, difficolta=self.difficolta,
                          p1=p1.id, p2=p2.id)

    # ---- disegno
    def disegna(self, sup: pygame.Surface) -> None:
        self._disegna_sfondo(sup, 150)
        vs = 0.0 if self._vs_t is None else S.limita(self._vs_t / 0.5)
        ui = 1.0 - S.ease_in_cubic(vs)
        p1, p2 = self.scelte()
        self._luce_accento(sup, (230, 300), _accento(p1), 720, 640, 0.6)
        self._luce_accento(sup, (L - 230, 300), _accento(p2), 720, 640, 0.6)
        self._scintille.disegna(sup, self.t, S.ORO, 0.7)
        for k in (0, 1):
            self._lato(sup, k, vs)
        if ui > 0.01:
            self._griglia(sup, ui)
            self._confronto(sup, ui)
        self._testata(sup, ui)
        if self._vs_t is not None:
            self._disegna_vs(sup)

    def _testata(self, sup: pygame.Surface, ui: float) -> None:
        if ui <= 0.01:
            return
        e = S.ease_out_cubic(self.t / 0.45)
        titolo = "SCEGLI IL LOTTATORE" if self.modalita != 'cpu' else "SORTEGGIO DEI LOTTATORI"
        s = S.testo(titolo, 40, S.BIANCO, sfumatura_testo=S.SFUMATURA_BIANCO, corsivo=True, contorno=3,
                    ombra=(2, 3), spaziatura=4)
        S.blit_alpha(sup, s, (L // 2 - s.get_width() // 2, int(20 - (1 - e) * 60)), 255 * e * ui)
        modo = {'singolo': "1 GIOCATORE", 'doppio': "2 GIOCATORI", 'cpu': "CPU CONTRO CPU"}[self.modalita]
        if self.difficolta and self.modalita != 'doppio':
            modo += "  ·  " + str(self.difficolta).upper()
        S.scrivi(sup, modo, (L // 2, 70), 20, S.ORO, 'center', alpha=255 * e * ui, corsivo=True,
                 contorno=2, ombra=(1, 2), spaziatura=3)
        if self.modalita == 'doppio':
            voci = [("F", "P1 conferma"), ("INVIO", "P2 conferma")]
        else:
            voci = [("INVIO", "Conferma"), ("ESC", "Indietro")]
        self._suggerimenti(sup, voci, A - 18, allinea='centro', alpha=190 * ui)

    def _centro_carta(self, i: int) -> tuple:
        c = self.CARTA
        col, riga = i % 2, i // 2
        return 448 + col * (c + 12), 100 + riga * (c + 12)

    def _griglia(self, sup: pygame.Surface, ui: float) -> None:
        c = self.CARTA
        for i, p in enumerate(self.roster):
            e = S.ease_out_cubic((self.t - 0.1 - 0.07 * i) / 0.4)
            if e <= 0:
                continue
            x, y = self._centro_carta(i)
            y += int((1 - e) * 60)
            sel = [k for k in (0, 1) if self.cursore[k] == i]
            acc = _accento(p)
            alza = -6 if sel else 0
            pan = S.pannello(c, c, 16, 16, stop=((0.0, S.mescola((26, 30, 50), acc, 0.28)),
                                                  (0.55, (14, 16, 28)),
                                                  (1.0, S.mescola((8, 9, 16), acc, 0.4))),
                             alpha=235, bordo=S.mescola(S.ACCIAIO, acc, 0.4), spessore=2)
            S.blit_alpha(sup, pan, (x, y + alza), 255 * e * ui)
            # lottatore in miniatura
            base_y = y + alza + c - 46
            self._lottatore(sup, p, (x + c // 2 + 6, int(base_y - 138 * p.altezza / 2 + 8)), 138, 'guardia',
                            True, False)
            # bandiera e nome
            S.blit_alpha(sup, S.bandiera(p.nazione, 34, 22), (x + 26, y + alza + 12), 255 * e * ui)
            plate = S.pannello(c - 8, 36, 12, 12, stop=((0.0, S.schiarisci(acc, 0.2)),
                                                      (1.0, S.scurisci(acc, 0.5))), alpha=255,
                               bordo=S.INCHIOSTRO, spessore=2, lucido=0.25)
            S.blit_alpha(sup, plate, (x + 2, y + alza + c - 40), 255 * e * ui)
            nome = _adatta(S.testo(p.soprannome, 26, S.BIANCO, corsivo=True, contorno=2, ombra=(1, 2)), c - 50)
            S.blit_alpha(sup, nome, nome.get_rect(center=(x + c // 2 + 4, y + alza + c - 22)).topleft,
                         255 * e * ui)
            if not sel:
                S.blit_alpha(sup, S.velo(c, c, (0, 0, 0), 110), (x, y), 255 * e * ui)
            # cursori
            for r, k in enumerate(sel):
                col = S.COLORE_GIOCATORE[k]
                pulsa = S.pulsa(self.t, 1.6, 0.6, 1.0)
                inset = r * 5
                cur = _cornice(c - 2 * inset, c - 2 * inset, 16, col,
                               4 if not self.bloccato[k] else 7)
                sup.blit(S.alone(c + 60, c + 60, col, _q(0.55 * pulsa, 6)), (x - 30, y + alza - 30),
                         special_flags=pygame.BLEND_RGB_ADD)
                S.blit_alpha(sup, cur, (x + inset, y + alza + inset), 255 * ui)
                etichetta = "CPU" if self.cpu[k] else ("1P" if k == 0 else "2P")
                if self.bloccato[k]:
                    etichetta = "PRONTO"
                chip = _chip(etichetta, col, 20)
                if k == 0:
                    sup.blit(chip, (x + 2 - 6, y + alza - 12))
                else:
                    sup.blit(chip, (x + c - chip.get_width() + 10, y + alza - 12))

    def _lato(self, sup: pygame.Surface, k: int, vs: float) -> None:
        """Ritratto grande, piastra colorata e targa di un giocatore."""
        p = self.roster[self.cursore[k]]
        acc = _accento(p)
        lato = 1 if k == 0 else -1
        e_in = S.ease_out_cubic((self.t - 0.05) / 0.5)
        anim = S.ease_out_cubic((self.t - self._t_cambio[k]) / 0.32)
        w = 440
        # piastra inclinata dietro al lottatore
        slab = S.pannello(w, 400, 0, 34, stop=((0.0, S.mescola((10, 12, 22), acc, 0.5)),
                                              (0.6, S.mescola((8, 9, 16), acc, 0.2)),
                                              (1.0, (6, 7, 12))), alpha=205,
                          bordo=S.mescola(acc, (255, 255, 255), 0.15), spessore=3,
                          righe=16, colore_righe=acc)
        if k == 1:
            slab = pygame.transform.flip(slab, True, False)
        x_slab = -(1 - e_in) * 500 * lato + (0 if k == 0 else L - w)
        sup.blit(slab, (int(x_slab) + (-6 if k == 0 else 6), 100))
        # lottatore
        cx = (230 if k == 0 else L - 230)
        cx += lato * -(1 - anim) * 70 + (-(1 - e_in) * 500 * lato)
        # in fase VS i lottatori si avvicinano
        cx += lato * 70 * S.ease_out_cubic(vs)
        self._lottatore(sup, p, (int(cx), 306), 340, 'guardia',
                        k == 0, self._speculare(k))
        # targa: soprannome, nome, stile
        self._targa(sup, k, p, acc, e_in)
        # indicatore giocatore in alto sulla piastra
        col = S.COLORE_GIOCATORE[k]
        stato = "CPU" if self.cpu[k] else ("1P" if k == 0 else "2P")
        if self.bloccato[k]:
            stato = "PRONTO!"
        elif self._sorteggio[k] is not None:
            stato = "CPU SCEGLIE..."
        chip = _chip(stato, col, 26)
        S.blit_alpha(sup, chip, (24 if k == 0 else L - 24 - chip.get_width(), 114), 255 * e_in)

    def _speculare(self, k: int) -> bool:
        return k == 1 and self.cursore[0] == self.cursore[1]

    def _targa(self, sup: pygame.Surface, k: int, p: Personaggio, acc: tuple, e: float) -> None:
        anim = S.ease_out_cubic((self.t - self._t_cambio[k]) / 0.3)
        x = 30 if k == 0 else L - 30
        ancora = 'topleft' if k == 0 else 'topright'
        nome = S.testo(p.soprannome, 62, S.BIANCO, sfumatura_testo=_sfumatura_accento(acc), corsivo=True,
                       contorno=4, colore_contorno=S.scurisci(acc, 0.72), contorno_esterno=2,
                       ombra=(3, 5))
        nome = _adatta(nome, 400)
        off = (1 - anim) * 50 * (-1 if k == 0 else 1)
        S.piazza(sup, nome, (x + off, 508), ancora, 255 * e * anim)
        bandiera = S.bandiera(p.nazione, 36, 24)
        yy = 508 + nome.get_height() + 2
        if k == 0:
            sup.blit(bandiera, (x + 4, yy + 2))
            S.scrivi(sup, "%s  ·  %s" % (p.nome.upper(), p.nazione.upper()), (x + 50, yy + 14), 22,
                     S.ARGENTO, 'midleft', contorno=2, ombra=(1, 2), corsivo=True)
        else:
            sup.blit(bandiera, (x - 40, yy + 2))
            S.scrivi(sup, "%s  ·  %s" % (p.nome.upper(), p.nazione.upper()), (x - 50, yy + 14), 22,
                     S.ARGENTO, 'midright', contorno=2, ombra=(1, 2), corsivo=True)
        y0 = yy + 36
        for j, riga in enumerate(_avvolgi(p.stile, 20, 400)[:2]):
            S.scrivi(sup, riga, (x, y0 + j * 24), 20, S.SPENTO, ancora, contorno=2, ombra=(1, 1),
                     alpha=255 * e)

    def _confronto(self, sup: pygame.Surface, ui: float) -> None:
        """Statistiche affiancate: barre che crescono dal centro verso i due lati."""
        e = S.ease_out_cubic((self.t - 0.35) / 0.5) * ui
        if e <= 0:
            return
        cx = L // 2
        y0 = 500
        larg = 176
        S.scrivi(sup, "CONFRONTO", (cx, y0 - 6), 20, S.ORO, 'center', alpha=255 * e, corsivo=True,
                 contorno=2, ombra=(1, 2), spaziatura=5)
        for j, (etichetta, chiave) in enumerate(STAT_PERSONAGGIO):
            y = y0 + 20 + j * 34
            S.scrivi(sup, etichetta, (cx, y + 11), 19, S.ARGENTO, 'center', alpha=255 * e,
                     contorno=2, ombra=(1, 1), corsivo=True)
            for k in (0, 1):
                p = self.roster[self.cursore[k]]
                acc = _accento(p)
                v = self._stat[k][j]
                bw = int(larg * S.limita(v * e) )
                fondo = S.pannello(larg, 14, 6, 6, colore=(14, 16, 26), alpha=220, bordo=(56, 62, 88),
                                   spessore=1)
                if k == 0:
                    bx = cx - 62 - larg
                else:
                    bx = cx + 62
                S.blit_alpha(sup, fondo, (bx, y + 4), 255 * e)
                if bw > 3:
                    col = S.accento_leggibile(acc)
                    fill = S.pannello(bw, 14, 6, 6, stop=((0.0, S.schiarisci(col, 0.5)),
                                                        (1.0, S.scurisci(col, 0.35))), alpha=255,
                                      bordo=S.INCHIOSTRO, spessore=1, lucido=0.2)
                    if k == 0:
                        sup.blit(fill, (bx + larg - bw, y + 4))
                    else:
                        sup.blit(fill, (bx, y + 4))

    def _disegna_vs(self, sup: pygame.Surface) -> None:
        t = self._vs_t
        u = t / 0.45
        # VS gigante che si schianta al centro
        scala = 1.0 + 3.0 * (1 - S.ease_out_cubic(u)) if u < 1 else 1.0 + 0.02 * math.sin(t * 6)
        vs = S.testo("VS", 260, S.ORO_CHIARO, sfumatura_testo=S.SFUMATURA_ORO, corsivo=True, contorno=8,
                     colore_contorno=(110, 30, 6), contorno_esterno=4, ombra=(6, 9))
        if t > 0.35:
            k = _q(1.0 - S.progresso(t, 0.35, 0.8), 8)
            if k > 0:
                sup.blit(S.alone(900, 500, (255, 180, 70), k), (L // 2 - 450, 330 - 250),
                         special_flags=pygame.BLEND_RGB_ADD)
        sh = int(math.sin(t * 60) * 8 * max(0.0, 1 - t / 0.5)) if t < 0.5 else 0
        S.piazza(sup, vs, (L // 2 + sh, 300), 'center', 255 * S.limita(u * 2), scala)
        k = 1.0 - S.progresso(t, 0.3, 0.3)
        if k > 0:
            sup.blit(S.velo(L, A, (255, 255, 255), int(190 * k)), (0, 0))
        # nomi in basso
        fine = S.progresso(t, self.DURATA_VS - 0.35, 0.3)
        if fine > 0:
            sup.blit(S.velo(L, A, (0, 0, 0), int(255 * fine)), (0, 0))


# ---- pausa
class MenuPausa(Scena):
    """Overlay di pausa sopra il combattimento.

    Costruttore: MenuPausa(sfondo, anteprima, suono, incontro=None)
      `incontro` (opzionale) serve solo a mostrare "ROUND n" e il punteggio.
      Al primo disegna() cattura il contenuto gia' presente sulla superficie (il frame
      del combattimento) e lo riusa come fondo: non serve ridisegnare il combattimento.
    prossima:
      RIPRENDI (o INDIETRO / PAUSA) -> ('riprendi', {})
      RICOMINCIA (dopo conferma SI')  -> ('ricomincia', {})
      COMANDI                         -> ('comandi', {'ritorno': 'menu_pausa'})
      MENU PRINCIPALE (dopo conferma) -> ('menu_principale', {})
    """

    nome = SCENA_PAUSA
    VOCI = ("RIPRENDI", "RICOMINCIA", "COMANDI", "MENU PRINCIPALE")

    def __init__(self, sfondo=None, anteprima=None, suono=None, incontro=None):
        super().__init__(sfondo, anteprima, suono)
        self.lista = _Lista(self.VOCI, (L - 480) // 2 - 10, 262, 480, 60, 72, 32, S.ROSSO_K1,
                            scarto=0)
        self.info = ""
        if incontro is not None:
            try:
                a, b = incontro.lottatori
                self.info = "ROUND %d   ·   %s  %d - %d  %s" % (
                    incontro.numero_round, a.personaggio.soprannome, a.round_vinti, b.round_vinti,
                    b.personaggio.soprannome)
            except Exception:
                self.info = ""
        self._istantanea = None
        self.conferma: Optional[str] = None      # 'ricomincia' | 'menu' quando c'e' il dialogo
        self._scelta_conferma = 1                # 0 = SI', 1 = NO

    @property
    def indice(self) -> int:
        return self.lista.indice

    def azione(self, giocatore: int, azione: str) -> None:
        if self.conferma is not None:
            if azione in (SINISTRA, DESTRA, SU, GIU):
                self._scelta_conferma = 1 - self._scelta_conferma
                self.suona('ui_muovi')
            elif azione == CONFERMA:
                if self._scelta_conferma == 0:
                    self.suona('ui_conferma')
                    self._vai(SCENA_RICOMINCIA if self.conferma == 'ricomincia' else SCENA_MENU)
                else:
                    self.suona('ui_indietro')
                    self.conferma = None
            elif azione in (INDIETRO, PAUSA):
                self.suona('ui_indietro')
                self.conferma = None
            return
        if azione in (SU, GIU):
            if self.lista.muovi(-1 if azione == SU else 1):
                self.suona('ui_muovi')
        elif azione == CONFERMA:
            self.suona('ui_conferma')
            i = self.lista.indice
            if i == 0:
                self._vai(SCENA_RIPRENDI)
            elif i == 1:
                self.conferma, self._scelta_conferma = 'ricomincia', 1
            elif i == 2:
                self._vai(SCENA_COMANDI, ritorno=SCENA_PAUSA)
            else:
                self.conferma, self._scelta_conferma = 'menu', 1
        elif azione in (INDIETRO, PAUSA):
            self.suona('ui_indietro')
            self._vai(SCENA_RIPRENDI)

    def aggiorna(self, dt: float) -> None:
        super().aggiorna(dt)
        self.lista.aggiorna(min(dt, 0.1))

    def disegna(self, sup: pygame.Surface) -> None:
        if self._istantanea is None:
            self._istantanea = sup.copy()
        sup.blit(self._istantanea, (0, 0))
        e = S.ease_out_cubic(self.t / 0.25)
        sup.blit(S.velo(L, A, (2, 3, 9), int(150 * e)), (0, 0))
        sup.blit(S.vignetta(L, A, 0.9), (0, 0))
        # titolo
        titolo = S.testo("PAUSA", 120, S.BIANCO, sfumatura_testo=S.SFUMATURA_BIANCO, corsivo=True,
                         contorno=6, colore_contorno=(150, 12, 30), contorno_esterno=3, ombra=(4, 7),
                         spaziatura=8)
        y = 150 + int((1 - S.ease_out_back(self.t / 0.4)) * -60)
        S.piazza(sup, titolo, (L // 2, y), 'center', 255 * e)
        for sgn in (-1, 1):
            lw = int(230 * S.ease_out_cubic((self.t - 0.1) / 0.4))
            sup.blit(S.pannello(max(6, lw), 5, -5, -5, colore=S.ROSSO_K1, alpha=255),
                     (L // 2 + sgn * (titolo.get_width() // 2 + 26) - (lw if sgn < 0 else 0), y - 2))
        if self.info:
            S.scrivi(sup, self.info, (L // 2, 226), 24, S.ORO_CHIARO, 'center', alpha=255 * e,
                     corsivo=True, contorno=2, ombra=(1, 2), spaziatura=2)
        self.lista.disegna(sup, max(0.0, self.t - 0.05))
        if self.conferma is None:
            self._suggerimenti(sup, [("INVIO", "Conferma"), ("ESC", "Riprendi")], 620, allinea='centro',
                               alpha=220 * e)
        else:
            self._dialogo(sup)

    def _dialogo(self, sup: pygame.Surface) -> None:
        sup.blit(S.velo(L, A, (0, 0, 0), 150), (0, 0))
        w, h = 620, 250
        x, y = (L - w) // 2, 220
        pan = S.pannello(w, h, 24, 24, stop=((0.0, (30, 34, 56)), (1.0, (10, 11, 20))), alpha=250,
                         bordo=S.ORO, spessore=3, lucido=0.12)
        sup.blit(pan, (x, y))
        domanda = "RICOMINCIARE L'INCONTRO?" if self.conferma == 'ricomincia' else "TORNARE AL MENU PRINCIPALE?"
        S.scrivi(sup, domanda, (L // 2, y + 66), 36, S.BIANCO, 'center', corsivo=True, contorno=3,
                 ombra=(2, 3))
        S.scrivi(sup, "I progressi dell'incontro andranno persi.", (L // 2, y + 108), 22, S.SPENTO,
                 'center', contorno=2, ombra=(1, 1))
        for k, etichetta in enumerate(("SÌ", "NO")):
            bw = 200
            bx = L // 2 - bw - 16 + k * (bw + 32)
            sel = k == self._scelta_conferma
            col = S.ROSSO_K1 if k == 0 else (60, 130, 240)
            if sel:
                sup.blit(S.alone(bw + 60, 110, col, 0.6), (bx - 30, y + 150 - 25),
                         special_flags=pygame.BLEND_RGB_ADD)
            b = S.pannello(bw, 56, 14, 14, stop=((0.0, S.schiarisci(col, 0.4 if sel else 0.0)),
                                                 (1.0, S.scurisci(col, 0.5 if sel else 0.75))),
                           alpha=255 if sel else 200, bordo=S.BIANCO if sel else S.ACCIAIO,
                           spessore=3 if sel else 2, lucido=0.3 if sel else 0.0)
            sup.blit(b, (bx, y + 150))
            S.scrivi(sup, etichetta, (bx + bw // 2, y + 178), 32, S.BIANCO if sel else S.ARGENTO, 'center',
                     corsivo=True, contorno=3, ombra=(2, 2))


# ---- risultati
class SchermataRisultati(Scena):
    """Vincitore e tabella delle statistiche di entrambi i lottatori.

    Costruttore: SchermataRisultati(sfondo, anteprima, suono, incontro,
                                    modalita='singolo', difficolta='normale')
      `incontro` e' un Incontro finito (fase 'fine_partita'); le statistiche vengono
      copiate al momento della creazione.
    prossima:
      RIVINCITA         -> ('combattimento', {'modalita': modalita, 'difficolta': difficolta,
                                              'p1': id_personaggio, 'p2': id_personaggio})
      CAMBIA LOTTATORI  -> ('selezione_personaggi', {'modalita': modalita, 'difficolta': difficolta})
      MENU PRINCIPALE   -> ('menu_principale', {})    (anche con INDIETRO)
    """

    nome = SCENA_RISULTATI
    VOCI = ("RIVINCITA", "CAMBIA LOTTATORI", "MENU PRINCIPALE")
    RIGHE = (
        ("ROUND VINTI", 'round_vinti', 0),
        ("COLPI TIRATI", 'colpi_tirati', 0),
        ("COLPI A SEGNO", 'colpi_a_segno', 0),
        ("PRECISIONE", 'precisione', 1),
        ("COLPI PARATI", 'colpi_parati', 0),
        ("DANNO INFLITTO", 'danno_inflitto', 0),
        ("COMBO MASSIMA", 'combo_max', 0),
        ("ATTERRAMENTI INFLITTI", 'atterramenti_inflitti', 0),
        ("SCHIVATE RIUSCITE", 'schivate_riuscite', 0),
    )

    def __init__(self, sfondo=None, anteprima=None, suono=None, incontro=None,
                 modalita: str = 'singolo', difficolta: Optional[str] = 'normale'):
        super().__init__(sfondo, anteprima, suono)
        self.modalita = modalita
        self.difficolta = difficolta
        self.personaggi = []
        self.dati = []
        self.palette_alt = [False, False]
        self.vincitore = 0
        for l in incontro.lottatori:
            self.personaggi.append(l.personaggio)
            st = dict(l.statistiche)
            st['round_vinti'] = l.round_vinti
            tirati = max(0, st.get('colpi_tirati', 0))
            st['precisione'] = (100.0 * st.get('colpi_a_segno', 0) / tirati) if tirati else 0.0
            self.dati.append(st)
        self.palette_alt = [bool(l.palette_alternativa) for l in incontro.lottatori]
        v = getattr(incontro, 'vincitore_partita', None)
        if v is None:
            v = 0 if self.dati[0]['round_vinti'] >= self.dati[1]['round_vinti'] else 1
        self.vincitore = int(v)
        self.lista = _Lista(self.VOCI, 486, 610, 244, 56, 254, 24, S.ROSSO_K1, orizzontale=True,
                            inclina=14)
        self._scintille = _Scintille(50, 8)

    @property
    def indice(self) -> int:
        return self.lista.indice

    def azione(self, giocatore: int, azione: str) -> None:
        if azione in (SINISTRA, DESTRA, SU, GIU):
            if self.lista.muovi(-1 if azione in (SINISTRA, SU) else 1):
                self.suona('ui_muovi')
        elif azione == CONFERMA:
            self.suona('ui_conferma')
            i = self.lista.indice
            if i == 0:
                self._vai(SCENA_COMBATTIMENTO, modalita=self.modalita, difficolta=self.difficolta,
                          p1=self.personaggi[0].id, p2=self.personaggi[1].id)
            elif i == 1:
                self._vai(SCENA_SELEZIONE, modalita=self.modalita, difficolta=self.difficolta)
            else:
                self._vai(SCENA_MENU)
        elif azione == INDIETRO:
            self.suona('ui_indietro')
            self._vai(SCENA_MENU)

    def aggiorna(self, dt: float) -> None:
        super().aggiorna(dt)
        self.lista.aggiorna(min(dt, 0.1))

    # ---- disegno
    def disegna(self, sup: pygame.Surface) -> None:
        self._disegna_sfondo(sup, 165)
        v = self.vincitore
        pv = self.personaggi[v]
        acc = _accento(pv)
        t = self.t
        self._luce_accento(sup, (230, 340), acc, 760, 700, 0.75)
        self._scintille.disegna(sup, t, S.mescola(acc, (255, 220, 120), 0.6), 1.0)
        self._colonna_vincitore(sup, pv, acc, v)
        self._tabella(sup)
        self.lista.disegna(sup, max(0.0, t - 0.7), acc)
        self._suggerimenti(sup, [("INVIO", "Conferma")], A - 16, allinea='centro', alpha=180)
        self._lampo(sup, 0.0, 0.35, 200)

    def _colonna_vincitore(self, sup: pygame.Surface, p: Personaggio, acc: tuple, v: int) -> None:
        e = S.ease_out_cubic(self.t / 0.6)
        slab = S.pannello(420, 430, 0, 36, stop=((0.0, S.mescola((10, 12, 22), acc, 0.5)),
                                                (0.6, S.mescola((8, 9, 16), acc, 0.22)),
                                                (1.0, (6, 7, 12))), alpha=210,
                          bordo=S.mescola(acc, (255, 255, 255), 0.2), spessore=3, righe=16,
                          colore_righe=acc)
        sup.blit(slab, (int(-6 - (1 - e) * 500), 96))
        cx = int(212 - (1 - e) * 500)
        self._lottatore(sup, p, (cx, 300), 400, 'vittoria', self.personaggi[0] is p or v == 0,
                        self.palette_alt[v])
        # corona di scritte
        chip = _chip("VINCITORE", S.ORO, 26, (40, 22, 4))
        S.blit_alpha(sup, chip, (26, 108), 255 * e)
        nome = S.testo(p.soprannome, 70, S.BIANCO, sfumatura_testo=_sfumatura_accento(acc), corsivo=True,
                       contorno=5, colore_contorno=S.scurisci(acc, 0.72), contorno_esterno=3,
                       ombra=(3, 6))
        nome = _adatta(nome, 400)
        u = S.ease_out_back((self.t - 0.3) / 0.5)
        S.piazza(sup, nome, (28, 536), 'topleft', 255 * S.limita((self.t - 0.3) / 0.2), 0.7 + 0.3 * u)
        band = S.bandiera(p.nazione, 36, 24)
        S.blit_alpha(sup, band, (32, 536 + nome.get_height() + 6), 255 * e)
        S.scrivi(sup, "%s  ·  %s" % (p.nome.upper(), p.nazione.upper()), (78, 536 + nome.get_height() + 19),
                 21, S.ARGENTO, 'midleft', alpha=255 * e, corsivo=True, contorno=2, ombra=(1, 1))

    def _tabella(self, sup: pygame.Surface) -> None:
        e = S.ease_out_cubic((self.t - 0.15) / 0.5)
        if e <= 0:
            return
        x0, y0, w, h = 470, 86, 780, 500
        pan = S.pannello(w, h, 22, 22, stop=((0.0, (22, 26, 46)), (1.0, (8, 9, 18))), alpha=222,
                         bordo=S.ACCIAIO, spessore=2, lucido=0.08)
        S.blit_alpha(sup, pan, (int(x0 + (1 - e) * 200), y0), 255 * e)
        dx = int((1 - e) * 200)
        cx = x0 + w // 2 + dx
        # intestazione: nomi dei due lottatori e punteggio
        for k in (0, 1):
            p = self.personaggi[k]
            acc = _accento(p)
            nome = _adatta(S.testo(p.soprannome, 34, S.BIANCO, sfumatura_testo=_sfumatura_accento(acc),
                                   corsivo=True, contorno=3, colore_contorno=S.scurisci(acc, 0.7),
                                   ombra=(2, 3)), 250)
            if k == 0:
                S.blit_alpha(sup, nome, (x0 + 78 + dx, y0 + 18), 255 * e)
            else:
                S.blit_alpha(sup, nome, (x0 + w - 78 - nome.get_width() + dx, y0 + 18), 255 * e)
            chip = _chip("1P" if k == 0 else "2P", S.COLORE_GIOCATORE[k], 18)
            sup.blit(chip, (x0 + 22 + dx, y0 + 26) if k == 0 else (x0 + w - 22 - chip.get_width() + dx - 6, y0 + 26))
        punteggio = "%d  -  %d" % (self.dati[0]['round_vinti'], self.dati[1]['round_vinti'])
        S.scrivi(sup, punteggio, (cx, y0 + 34), 52, S.ORO_CHIARO, 'center', alpha=255 * e, corsivo=True,
                 contorno=4, ombra=(2, 4))
        S.scrivi(sup, "ROUND", (cx, y0 + 66), 16, S.SPENTO, 'center', alpha=255 * e, corsivo=True,
                 contorno=1, ombra=(1, 1), spaziatura=3)
        # righe
        ry0 = y0 + 92
        passo = 44
        lung = 250
        for j, (etichetta, chiave, formato) in enumerate(self.RIGHE):
            inizio = 0.55 + 0.09 * j
            u = S.ease_out_cubic((self.t - inizio) / 0.7)
            if u <= 0:
                continue
            y = ry0 + j * passo
            if j % 2 == 0:
                S.blit_alpha(sup, S.velo(w - 60, passo - 4, (255, 255, 255), 10), (x0 + 30 + dx, y), 255 * e)
            valori = [self.dati[0][chiave], self.dati[1][chiave]]
            massimo = max(valori[0], valori[1], 1e-6)
            S.scrivi(sup, etichetta, (cx, y + 9), 17, S.SPENTO, 'center', alpha=255 * u,
                     corsivo=True, contorno=1, ombra=(1, 1), spaziatura=2)
            for k in (0, 1):
                vinc = valori[k] > valori[1 - k] + 1e-9
                acc = S.accento_leggibile(_accento(self.personaggi[k]))
                col = acc if vinc or valori[k] == valori[1 - k] else S.mescola(acc, (70, 74, 96), 0.55)
                bl = lung * (valori[k] / massimo) * u if massimo > 0 else 0
                bl = max(bl, 4 * u) if valori[k] > 0 else 0
                fondo = S.pannello(lung, 12, 5, 5, colore=(12, 14, 24), alpha=210, bordo=(46, 52, 76),
                                   spessore=1)
                bx = cx - 74 - lung if k == 0 else cx + 74
                S.blit_alpha(sup, fondo, (bx, y + 21), 255 * u)
                bw = int(bl)
                if bw > 6:
                    riemp = S.pannello(bw, 12, 5, 5, stop=((0.0, S.schiarisci(col, 0.5)),
                                                          (1.0, S.scurisci(col, 0.35))),
                                       alpha=255, bordo=S.INCHIOSTRO, spessore=1, lucido=0.25)
                    sup.blit(riemp, (bx + lung - bw if k == 0 else bx, y + 21))
                val = valori[k] * u
                txt = ("%d%%" % round(val)) if formato == 1 else ("%d" % round(val))
                colore_num = S.ORO_CHIARO if vinc else S.ARGENTO
                s = S.testo(txt, 26, colore_num, corsivo=True, contorno=2, ombra=(1, 2))
                if k == 0:
                    sup.blit(s, s.get_rect(midright=(bx - 16, y + 27)))
                else:
                    sup.blit(s, s.get_rect(midleft=(bx + lung + 16, y + 27)))


# ---- comandi
class SchermataComandi(Scena):
    """Elenco dei comandi da `GestoreInput.descrizione_comandi`.

    Costruttore: SchermataComandi(sfondo, anteprima, suono, descrizione, ritorno='menu_principale')
      descrizione: il dict di descrizione_comandi(modalita) oppure una lista/tupla di dict
      (pagine, con SINISTRA/DESTRA per passare dall'una all'altra).
    prossima: CONFERMA o INDIETRO (o PAUSA) -> (ritorno, {})
    """

    nome = SCENA_COMANDI
    COLORI_PAD = {'X': (140, 180, 255), 'Y': (255, 224, 110), 'A': (140, 225, 150), 'B': (255, 140, 130)}

    def __init__(self, sfondo=None, anteprima=None, suono=None, descrizione=None,
                 ritorno: str = SCENA_MENU):
        super().__init__(sfondo, anteprima, suono)
        if isinstance(descrizione, dict):
            pagine = [descrizione]
        else:
            pagine = [d for d in (descrizione or []) if isinstance(d, dict)]
        self.pagine = pagine or [{'titolo': "COMANDI", 'sezioni': [], 'note': []}]
        self.pagina = 0
        self.ritorno = ritorno

    def azione(self, giocatore: int, azione: str) -> None:
        if azione in (SINISTRA, DESTRA) and len(self.pagine) > 1:
            self.pagina = (self.pagina + (1 if azione == DESTRA else -1)) % len(self.pagine)
            self._t_pagina = self.t
            self.suona('ui_muovi')
        elif azione in (CONFERMA, INDIETRO, PAUSA):
            self.suona('ui_indietro' if azione != CONFERMA else 'ui_conferma')
            self._vai(self.ritorno)

    _t_pagina = 0.0

    # ---- analisi dei testi dei tasti
    @staticmethod
    def gruppi_tasti(stringa) -> list:
        """'W A S D  oppure  Frecce' -> [['W','A','S','D'], ['Frecce']]."""
        if isinstance(stringa, (list, tuple)):
            return [[str(x)] for x in stringa]
        gruppi = []
        for alt in re.split(r"\s+oppure\s+|\s*/\s*", str(stringa)):
            alt = alt.strip()
            if not alt:
                continue
            if ',' in alt:
                etichette = [x.strip() for x in alt.split(',') if x.strip()]
            else:
                tok = alt.split()
                etichette = tok if len(tok) > 1 and all(len(x) == 1 for x in tok) else [alt]
            gruppi.append(etichette)
        return gruppi

    def _riga_tasti(self, sup: pygame.Surface, x: int, y: int, stringa, larghezza: int, pad: bool,
                    alpha: float) -> None:
        gruppi = self.gruppi_tasti(stringa)
        caps = []
        for gi, etichette in enumerate(gruppi):
            for et in etichette:
                col = self.COLORI_PAD.get(et.upper(), (228, 232, 242)) if pad and len(et) == 1 else (228, 232, 242)
                caps.append(S.tasto(et, 23, col))
            if gi < len(gruppi) - 1:
                caps.append(None)
        tot = sum((c.get_width() if c else 16) + 5 for c in caps)
        scala = min(1.0, larghezza / max(1, tot))
        cx = x
        for c in caps:
            if c is None:
                S.scrivi(sup, "/", (int(cx + 6), y), 20, S.SPENTO, 'midleft', alpha=alpha, contorno=1,
                         ombra=None)
                cx += 16 * scala + 5 * scala
                continue
            if scala < 1.0:
                c = S.scala_superficie(c, scala)
            S.blit_alpha(sup, c, (int(cx), y - c.get_height() // 2), alpha)
            cx += c.get_width() + 5 * scala

    def disegna(self, sup: pygame.Surface) -> None:
        self._disegna_sfondo(sup, 190)
        d = self.pagine[self.pagina]
        self._intestazione(sup, str(d.get('titolo', "COMANDI")),
                           "" if len(self.pagine) < 2 else "Sinistra / destra per cambiare modalita'",
                           y=22)
        sezioni = list(d.get('sezioni', []))
        riga_h, testa_h = 25, 30
        altezze = [testa_h + 6 + len(s.get('righe', [])) * riga_h + 12 for s in sezioni]
        colonne = [[], []]
        tot = [0, 0]
        for idx, (s, h) in enumerate(zip(sezioni, altezze)):
            c = 0 if tot[0] <= tot[1] else 1
            colonne[c].append((idx, s, h))
            tot[c] += h
        cw = 566
        for ci, col in enumerate(colonne):
            x = 56 + ci * (cw + 36)
            y = 138
            for idx, s, h in col:
                e = S.ease_out_cubic((self.t - 0.12 - 0.09 * idx) / 0.4)
                if e <= 0:
                    y += h
                    continue
                titolo = str(s.get('titolo', ""))
                pad = 'GAMEPAD' in titolo.upper()
                stop = ((0.0, S.schiarisci(ROSSO, 0.2)), (1.0, S.scurisci(ROSSO, 0.55)))
                if pad:
                    stop = ((0.0, (120, 200, 255)), (1.0, (28, 70, 140)))
                elif 'MENU' in titolo.upper():
                    stop = ((0.0, S.schiarisci(S.ORO, 0.2)), (1.0, S.scurisci(S.ORO, 0.6)))
                testa = S.pannello(cw, testa_h, 14, 14, stop=stop, alpha=255, bordo=S.INCHIOSTRO,
                                   spessore=2, lucido=0.3)
                off = int((1 - e) * 80)
                S.blit_alpha(sup, testa, (x - off, y), 255 * e)
                S.scrivi(sup, titolo.upper(), (x + 30 - off, y + testa_h // 2 + 1), 20, S.BIANCO,
                         'midleft', alpha=255 * e, corsivo=True, contorno=2, ombra=(1, 2), spaziatura=2)
                y += testa_h + 6
                for j, (azione, tasti) in enumerate(s.get('righe', [])):
                    yy = y + j * riga_h
                    if j % 2 == 0:
                        S.blit_alpha(sup, S.velo(cw, riga_h - 1, (255, 255, 255), 9), (x, yy), 255 * e)
                    S.scrivi(sup, str(azione), (x + 14, yy + riga_h // 2), 20, S.ARGENTO, 'midleft',
                             alpha=255 * e, contorno=2, ombra=(1, 1))
                    self._riga_tasti(sup, x + 178, yy + riga_h // 2, tasti, cw - 190, pad, 255 * e)
                y += len(s.get('righe', [])) * riga_h + 12
        # note: nella colonna piu' libera, sotto l'ultima sezione
        c = 0 if tot[0] <= tot[1] else 1
        y = 138 + tot[c] + 8
        x = 56 + c * (cw + 36)
        for nota in (d.get('note') or []):
            for riga in _avvolgi(str(nota), 18, cw - 10):
                if y > A - 40:
                    break
                S.scrivi(sup, riga, (x + 6, y), 18, S.SPENTO, 'topleft',
                         alpha=255 * S.progresso(self.t, 0.7, 0.4), contorno=2, ombra=(1, 1))
                y += 21
            y += 4
        self._suggerimenti(sup, [("INVIO", "Indietro")] if len(self.pagine) < 2 else
                           [("<>", "Cambia"), ("INVIO", "Indietro")], A - 30)
