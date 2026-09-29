"""HUD del combattimento: barre inclinate, timer, combo, annunci e conteggio dell'arbitro.

Uso (una volta per frame di gioco):
    hud.gestisci_evento(ev, incontro)   # per ogni evento emesso da Incontro.aggiorna
    hud.aggiorna(incontro)
    hud.disegna(superficie, incontro)

Tutto lo stato animato (scia del danno, pop del combo, annunci) vive nell'HUD e
dipende solo dallo stato pubblico dell'Incontro e dagli eventi.
"""

from __future__ import annotations

import math
from typing import Optional

import pygame

from .. import costanti as C
from .. import eventi as E
from . import stile as S

L, A = C.LARGHEZZA, C.ALTEZZA

# ---- geometria (pixel logici 1280x720)
MARGINE = 30
BARRA_W, BARRA_H = 524, 36
BARRA_Y = 20
INCLINA = 24                     # inclinazione dei lati delle barre di vita
BORDO_BARRA = 3
STAMINA_W, STAMINA_H, STAMINA_Y = 320, 9, 64
STAMINA_INCLINA = 9
TARGA_Y, TARGA_H = 82, 30
BADGE_W, BADGE_H, BADGE_Y = 146, 86, 6
ENERGIA_W, ENERGIA_H, ENERGIA_Y = 344, 20, A - 44
ENERGIA_SEGMENTI = 10

# ---- colori
VITA_VERDE = (70, 216, 104)
VITA_GIALLO = (252, 210, 52)
VITA_ROSSO = (240, 52, 60)
SCIA = (255, 236, 196)
STAMINA_COL = (74, 200, 250)
STAMINA_AFFANNO = (255, 120, 56)
ENERGIA_BASSA = (70, 150, 255)
ENERGIA_PIENA = (255, 212, 70)
VITA_BASSA = 0.28                # sotto questa frazione la barra pulsa

DURATA_ROUND, DURATA_FIGHT, DURATA_KO, DURATA_TEMPO = 118, 66, 112, 78
DURATA_PAREGGIO, DURATA_VINCE = 90, 96


# ---- utilita'
def _quantizza(v: float, passi: int) -> float:
    return round(v * passi) / passi


def _colore_vita(f: float) -> tuple:
    f = S.limita(f)
    if f >= 0.5:
        return S.mescola(VITA_GIALLO, VITA_VERDE, (f - 0.5) / 0.5)
    return S.mescola(VITA_ROSSO, VITA_GIALLO, f / 0.5)


def _gradiente_barra(colore: tuple) -> pygame.Surface:
    """Gradiente lucido per il riempimento (cache per colore)."""
    stop = ((0.0, S.schiarisci(colore, 0.62)), (0.32, S.schiarisci(colore, 0.12)),
            (0.52, colore), (0.56, S.scurisci(colore, 0.2)), (1.0, S.scurisci(colore, 0.5)))
    return S.sfumatura(BARRA_W, BARRA_H, stop)


def _accento(p) -> tuple:
    return tuple(p.colore_ui[:3])


def _testo_accento(colore: tuple) -> tuple:
    """Sfumatura di riempimento del testo nei colori del personaggio."""
    c = S.accento_leggibile(colore)
    return ((0.0, S.schiarisci(c, 0.75)), (0.42, S.schiarisci(c, 0.2)), (0.58, c),
            (1.0, S.scurisci(c, 0.25)))


def _banda(w: int, h: int, alpha: int) -> pygame.Surface:
    """Fascia scura con bordi morbidi sopra e sotto (per gli annunci)."""
    chiave = ('hud_banda', w, h, alpha)

    def crea():
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = y / max(1, h - 1)
            k = min(1.0, min(t, 1 - t) / 0.28)
            pygame.draw.line(s, (4, 5, 12, int(alpha * (k ** 1.3))), (0, y), (w, y))
        return S._ottimizza(s)
    return S._in_cache(chiave, crea)


def _polig_barra(x0: float, y0: float, w: float, h: float, incl: float) -> list:
    """Parallelogramma "\\" (angoli alto-sx, alto-dx, basso-dx, basso-sx)."""
    return [(x0, y0), (x0 + w - incl, y0), (x0 + w, y0 + h), (x0 + incl, y0 + h)]


class _Sagoma:
    """Barra a parallelogramma "\\" in spazio P1 (per P2 si specchia il risultato).

    Prepara una volta cornice, maschera interna e overlay lucido; a ogni frame
    ritaglia il riempimento con un taglio inclinato come i lati.
    """

    def __init__(self, w: int, h: int, incl: int, bordo: int, ticks: bool = True):
        self.w, self.h, self.incl, self.bordo = w, h, incl, bordo
        esterno = S.forma(w, h, -incl, -incl)
        self.esterno = esterno
        self.maschera = S.maschera_poligono(w, h, S.rientra(esterno, bordo))
        self.ticks = ticks
        self._overlay = None

    def cornice(self, colore_bordo: tuple, fondo_alto: tuple, fondo_basso: tuple) -> pygame.Surface:
        return S.pannello(self.w, self.h, -self.incl, -self.incl, colore=fondo_alto,
                          colore_basso=fondo_basso, alpha=240, bordo=colore_bordo,
                          spessore=self.bordo)

    def overlay(self) -> pygame.Surface:
        """Riflesso in alto + tacche al 25/50/75%, ritagliati sulla forma interna."""
        if self._overlay is None:
            w, h = self.w, self.h
            o = pygame.Surface((w, h), pygame.SRCALPHA)
            # riflesso
            for y in range(int(h * 0.5)):
                a = int(70 * (1 - y / (h * 0.5)) ** 1.5)
                pygame.draw.line(o, (255, 255, 255, a), (0, y), (w, y))
            # ombra in basso
            o.blit(S.ombreggiatura(w, h, 0.35), (0, 0))
            if self.ticks:
                L_ = w - self.incl
                for k in (0.25, 0.5, 0.75):
                    xt = k * L_
                    pygame.draw.line(o, (0, 0, 0, 90), (xt, 0), (xt + self.incl, h), 2)
                    pygame.draw.line(o, (255, 255, 255, 40), (xt + 2, 0), (xt + 2 + self.incl, h), 1)
            o.blit(self.maschera, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._overlay = S._ottimizza(o)
        return self._overlay

    def riempimento(self, frazione: float, gradiente: pygame.Surface) -> Optional[pygame.Surface]:
        frazione = S.limita(frazione)
        if frazione <= 0.002:
            return None
        w, h, incl = self.w, self.h, self.incl
        xc = frazione * (w - incl)
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        S.poligono_aa(s, (255, 255, 255, 255), [(-2, 0), (xc, 0), (xc + incl, h), (-2, h)])
        s.blit(self.maschera, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        s.blit(gradiente, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return s


class _StatoCombo:
    __slots__ = ('n', 'danno', 'f_colpo', 'f_fine', 'vivo')

    def __init__(self):
        self.n = 0
        self.danno = 0.0
        self.f_colpo = -999
        self.f_fine = -999
        self.vivo = False


class _Annuncio:
    """Un annuncio centrale animato."""
    __slots__ = ('tipo', 'testo', 'sotto', 'colore', 'f0', 'durata', 'extra')

    def __init__(self, tipo: str, testo: str, sotto: str, colore: tuple, f0: int, durata: int,
                 extra=None):
        self.tipo, self.testo, self.sotto, self.colore = tipo, testo, sotto, colore
        self.f0, self.durata, self.extra = f0, durata, extra


class HUD:
    """Interfaccia di combattimento."""

    def __init__(self):
        self._f = 0
        self._incontro = None
        self._sagoma_vita = _Sagoma(BARRA_W, BARRA_H, INCLINA, BORDO_BARRA)
        self._sagoma_stamina = _Sagoma(STAMINA_W, STAMINA_H, STAMINA_INCLINA, 2, ticks=False)
        self._azzera()

    # ---- stato
    def _azzera(self) -> None:
        self._vita = [1.0, 1.0]
        self._scia = [1.0, 1.0]
        self._scia_attesa = [0, 0]
        self._scossa = [0.0, 0.0]
        self._colpo_f = [-999, -999]           # ultimo danno subito (per il lampo)
        self._stamina = [1.0, 1.0]
        self._energia = [0.0, 0.0]
        self._super_f = [-999, -999]           # ultimo SuperPronto
        self._combo = [_StatoCombo(), _StatoCombo()]
        self._annunci = []
        self._programmati = []
        self._conteggio = None
        self._flash = [0, 0.0]                 # frame residui, intensita'
        self._entrata = 1.0
        self._riempi = 1.0

    def resetta(self) -> None:
        """Riporta l'HUD allo stato iniziale (nuova partita)."""
        self._azzera()
        self._incontro = None

    # ---- eventi
    def _lega(self, incontro) -> None:
        """Associa l'HUD a un Incontro (azzerando lo stato se e' un altro)."""
        if incontro is self._incontro:
            return
        self._azzera()
        self._incontro = incontro
        for i, l in enumerate(incontro.lottatori):
            self._vita[i] = self._scia[i] = l.vita / max(1e-6, l.vita_max)
            self._energia[i] = l.energia / C.ENERGIA_MAX
            self._stamina[i] = l.stamina / max(1e-6, l.stamina_max)

    def gestisci_evento(self, evento, incontro) -> None:
        self._lega(incontro)
        f = self._f
        L_ = incontro.lottatori
        if isinstance(evento, E.InizioRound):
            self._annunci = [a for a in self._annunci if a.tipo == 'vince_partita']
            self._programmati = []
            self._conteggio = None
            n = evento.numero
            p1, p2 = L_[0].personaggio, L_[1].personaggio
            decisivo = (L_[0].round_vinti >= incontro.round_per_vincere - 1
                        and L_[1].round_vinti >= incontro.round_per_vincere - 1)
            sotto = "ROUND DECISIVO" if decisivo and incontro.round_per_vincere > 1 else ""
            self._annunci.append(_Annuncio('round', "ROUND", sotto, S.ORO, f, DURATA_ROUND,
                                           extra=(str(n), p1, p2)))
        elif isinstance(evento, E.Via):
            self._annunci.append(_Annuncio('fight', "FIGHT!", "", S.ORO, f, DURATA_FIGHT))
        elif isinstance(evento, E.ColpoASegno):
            self._colpo(evento, incontro)
        elif isinstance(evento, E.KO):
            self._conteggio = None
            if not any(a.tipo == 'ko' for a in self._annunci):
                txt = "K.O. TECNICO" if evento.tecnico else "K.O."
                sotto = "TRE ATTERRAMENTI" if evento.tecnico else ""
                self._annunci.append(_Annuncio('ko', txt, sotto, S.ROSSO_K1, f, DURATA_KO,
                                               extra=evento.tecnico))
                self._flash = [7, 0.85]
        elif isinstance(evento, E.FineRound):
            self._fine_round(evento, incontro)
        elif isinstance(evento, E.FinePartita):
            p = L_[evento.vincitore].personaggio
            self._annunci = [a for a in self._annunci if a.tipo != 'vince']
            self._programmati = []
            self._annunci.append(_Annuncio('vince_partita', "VINCE", "HA VINTO L'INCONTRO",
                                           _accento(p), f, 10 ** 7, extra=p))
        elif isinstance(evento, E.ConteggioArbitro):
            self._conteggio = {'indice': evento.indice, 'numero': evento.numero, 'f0': f,
                               'fine': None}
        elif isinstance(evento, E.Rialzo):
            if self._conteggio is not None and self._conteggio['fine'] is None:
                self._conteggio['fine'] = f
        elif isinstance(evento, E.SuperPronto):
            self._super_f[evento.indice] = f

    def _colpo(self, ev, incontro) -> None:
        st = self._combo[ev.attaccante]
        if ev.parato:
            return
        if ev.combo <= 1:
            st.danno = 0.0
            st.n = 0
        st.danno += ev.danno
        st.n = max(st.n, ev.combo)
        st.f_colpo = self._f
        st.vivo = True
        d = incontro.lottatori[ev.difensore]
        self._colpo_f[ev.difensore] = self._f
        self._scossa[ev.difensore] = min(11.0, 2.0 + ev.danno * 0.45)
        self._scia_attesa[ev.difensore] = 34 if d.vita > 0 else 60

    def _fine_round(self, ev, incontro) -> None:
        f = self._f
        v = ev.vincitore
        tempo_scaduto = incontro.tempo_rimasto <= 0.0
        ritardo = 0
        if ev.motivo == 'punti' or (ev.motivo == 'pareggio' and tempo_scaduto):
            self._annunci.append(_Annuncio('tempo', "TEMPO!", "", S.ARGENTO, f, DURATA_TEMPO))
            ritardo = DURATA_TEMPO - 6
        elif ev.motivo in ('ko', 'tko', 'pareggio'):
            ritardo = DURATA_KO - 4
        if v is None:
            self._programmati.append((f + ritardo, 'pareggio', None, ev.numero))
        else:
            self._programmati.append((f + ritardo, 'vince', v, ev.numero))

    def _attiva_programmati(self, incontro) -> None:
        resto = []
        for quando, tipo, v, numero in self._programmati:
            if self._f < quando:
                resto.append((quando, tipo, v, numero))
                continue
            if tipo == 'pareggio':
                self._annunci.append(_Annuncio('pareggio', "PAREGGIO", "NESSUN PUNTO ASSEGNATO",
                                               S.ARGENTO, self._f, DURATA_PAREGGIO))
            else:
                p = incontro.lottatori[v].personaggio
                self._annunci.append(_Annuncio('vince', "VINCE", "ROUND %d" % numero,
                                               _accento(p), self._f, DURATA_VINCE, extra=p))
        self._programmati = resto

    # ---- aggiornamento
    def aggiorna(self, incontro) -> None:
        self._lega(incontro)
        self._f += 1
        f = self._f
        pres = incontro.fase == 'presentazione'
        self._entrata = S.ease_out_cubic(incontro.frame_fase / 34.0) if pres else 1.0
        self._riempi = S.ease_out_cubic((incontro.frame_fase - 8) / 46.0) if pres else 1.0
        for i, l in enumerate(incontro.lottatori):
            frac = l.vita / max(1e-6, l.vita_max)
            if pres:
                self._vita[i] = self._scia[i] = frac
                self._stamina[i] = l.stamina / max(1e-6, l.stamina_max)
            else:
                self._vita[i] += (frac - self._vita[i]) * 0.55
                if abs(frac - self._vita[i]) < 0.0008:
                    self._vita[i] = frac
                if self._scia_attesa[i] > 0:
                    self._scia_attesa[i] -= 1
                else:
                    self._scia[i] = max(self._vita[i], self._scia[i] - 0.0075)
                if frac > self._scia[i]:
                    self._scia[i] = frac
                self._stamina[i] += (l.stamina / max(1e-6, l.stamina_max) - self._stamina[i]) * 0.3
            self._energia[i] += (l.energia / C.ENERGIA_MAX - self._energia[i]) * 0.25
            self._scossa[i] *= 0.82
            if self._scossa[i] < 0.15:
                self._scossa[i] = 0.0
            # combo: chiusura quando l'attaccante non sta piu' concatenando
            st = self._combo[i]
            if l.combo >= 1 and l.combo > st.n:
                st.n = l.combo
                st.f_colpo = f
                st.vivo = True
            elif l.combo == 0 and st.vivo and (f - st.f_colpo) > 2:
                st.vivo = False
                st.f_fine = f
        if self._flash[0] > 0:
            self._flash[0] -= 1
        c = self._conteggio
        if c is not None:
            l = incontro.lottatori[c['indice']]
            if c['fine'] is None and l.stato not in ('atterrato',):
                c['fine'] = f
            if c['fine'] is not None and f - c['fine'] > 14:
                self._conteggio = None
        self._attiva_programmati(incontro)
        self._annunci = [a for a in self._annunci if f - a.f0 < a.durata]

    # ---- disegno
    def disegna(self, superficie: pygame.Surface, incontro) -> None:
        self._lega(incontro)
        ent = self._entrata
        dy = -(1.0 - ent) * 130.0
        for i in (0, 1):
            self._disegna_giocatore(superficie, incontro, i, dy)
        self._disegna_badge(superficie, incontro, dy)
        for i in (0, 1):
            self._disegna_energia(superficie, incontro, i, (1.0 - ent) * 90.0)
            self._disegna_combo(superficie, incontro, i)
        self._disegna_conteggio(superficie, incontro)
        for a in self._annunci:
            self._disegna_annuncio(superficie, incontro, a)
        if self._flash[0] > 0:
            k = self._flash[0] / 7.0
            superficie.blit(S.velo(L, A, (255, 255, 255), int(255 * self._flash[1] * k * k)), (0, 0))

    # -- barre di un giocatore
    def _disegna_giocatore(self, sup: pygame.Surface, incontro, i: int, dy: float) -> None:
        l = incontro.lottatori[i]
        p = l.personaggio
        acc = _accento(p)
        f_now = self._f
        lato = 1 if i == 0 else -1
        scossa = self._scossa[i]
        sx = sy = 0
        if scossa > 0:
            sx = int(math.sin(f_now * 2.3) * scossa)
            sy = int(math.cos(f_now * 3.1) * scossa * 0.5)

        vita = self._vita[i] * self._riempi
        scia = self._scia[i] * self._riempi
        basso = self._vita[i] < VITA_BASSA and l.vita > 0 and incontro.fase != 'presentazione'
        ritmo = 1.0 + 1.6 * (1 - self._vita[i] / VITA_BASSA) if basso else 1.0
        puls = S.pulsa(f_now / 60.0, 1.6 * ritmo) if basso else 0.0

        # --- barra di vita composta in spazio P1
        sg = self._sagoma_vita
        col = _colore_vita(_quantizza(vita, 40))
        if basso:
            col = S.mescola(col, (255, 200, 190), puls * 0.55)
        barra = pygame.Surface((BARRA_W, BARRA_H), pygame.SRCALPHA)
        barra.blit(sg.cornice(S.mescola(acc, (255, 255, 255), 0.12),
                              (20, 22, 34), (8, 9, 16)), (0, 0))
        r = sg.riempimento(scia, S.sfumatura(BARRA_W, BARRA_H, (
            (0.0, (255, 228, 168)), (0.5, (255, 184, 92)), (1.0, (206, 112, 44)))))
        if r is not None:
            if scia > vita + 0.002 and self._scia_attesa[i] > 0 and (f_now - self._colpo_f[i]) < 8:
                r.fill((70, 70, 70, 0), special_flags=pygame.BLEND_RGB_ADD)
            barra.blit(r, (0, 0))
        r = sg.riempimento(vita, _gradiente_barra(col))
        if r is not None:
            barra.blit(r, (0, 0))
        barra.blit(sg.overlay(), (0, 0))
        # lampo bianco sul colpo subito
        dtf = f_now - self._colpo_f[i]
        if 0 <= dtf < 6:
            bag = S.velo(BARRA_W, BARRA_H, (255, 255, 255), int(150 * (1 - dtf / 6)))
            bag = bag.copy()
            bag.blit(sg.maschera, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            barra.blit(bag, (0, 0))
        if i == 1:
            barra = pygame.transform.flip(barra, True, False)

        x0 = MARGINE if i == 0 else L - MARGINE - BARRA_W
        x0 += sx
        y0 = BARRA_Y + dy + sy
        # ombra portata
        ombra = S.tinta(sg.maschera if i == 0 else pygame.transform.flip(sg.maschera, True, False),
                        (0, 0, 0, 130))
        sup.blit(ombra, (x0 + 3, y0 + 5))
        if basso:
            k = _quantizza(0.35 + 0.65 * puls, 6)
            bag = S.alone(BARRA_W + 60, BARRA_H + 46, VITA_ROSSO, k)
            sup.blit(bag, (x0 - 30, y0 - 23), special_flags=pygame.BLEND_RGB_ADD)
        sup.blit(barra, (x0, y0))

        # --- stamina
        aff = l.affannato and incontro.fase == 'combattimento'
        col_s = STAMINA_COL
        if aff:
            col_s = S.mescola(STAMINA_AFFANNO, (255, 220, 100), S.pulsa(f_now / 60.0, 2.8))
        gr_s = S.sfumatura(STAMINA_W, STAMINA_H, ((0.0, S.schiarisci(col_s, 0.55)),
                                                  (0.5, col_s), (1.0, S.scurisci(col_s, 0.45))))
        sgs = self._sagoma_stamina
        stam = self._stamina[i] * self._riempi
        sb = pygame.Surface((STAMINA_W, STAMINA_H), pygame.SRCALPHA)
        sb.blit(sgs.cornice((90, 100, 130), (14, 16, 26), (6, 7, 12)), (0, 0))
        r = sgs.riempimento(stam, gr_s)
        if r is not None:
            sb.blit(r, (0, 0))
        if i == 1:
            sb = pygame.transform.flip(sb, True, False)
        xs = MARGINE + 8 if i == 0 else L - MARGINE - 8 - STAMINA_W
        sup.blit(sb, (xs, STAMINA_Y + dy))
        if aff:
            S.scrivi(sup, "SENZA FIATO", (xs + (STAMINA_W + 8 if i == 0 else -8), STAMINA_Y + dy + 5),
                     15, S.mescola(STAMINA_AFFANNO, (255, 255, 255), 0.3),
                     'midleft' if i == 0 else 'midright', contorno=2, ombra=(1, 1),
                     corsivo=True, alpha=140 + 115 * S.pulsa(f_now / 60.0, 2.8))

        # --- medaglie dei round vinti (lato interno, sotto la barra)
        n_med = incontro.round_per_vincere
        d = 20
        for k in range(n_med):
            vinto = k < l.round_vinti
            ic = S.rombo(d, S.ORO_CHIARO if vinto else acc, pieno=vinto)
            if i == 0:
                mx = MARGINE + BARRA_W - 6 - (n_med - k) * (d + 3)
            else:
                mx = L - MARGINE - BARRA_W + 6 + k * (d + 3) + 6
            sup.blit(ic, (mx, STAMINA_Y + dy - 6))

        # --- targa: bandiera + soprannome, e nome per esteso
        self._disegna_targa(sup, l, i, dy + sy, sx)

    def _disegna_targa(self, sup: pygame.Surface, l, i: int, dy: float, sx: int) -> None:
        p = l.personaggio
        acc = _accento(p)
        nome = S.testo(p.soprannome, 30, S.BIANCO, corsivo=True, contorno=2, ombra=(1, 2))
        larg = max(214, nome.get_width() + 84)
        h = TARGA_H
        inc = 12
        plate = S.pannello(larg, h, -inc, -inc, stop=(
            (0.0, S.schiarisci(acc, 0.28)), (0.5, acc), (1.0, S.scurisci(acc, 0.55))),
            alpha=255, bordo=(8, 8, 13), spessore=2, lucido=0.28)
        bandiera = S.bandiera(p.nazione, 34, 22)
        if i == 0:
            x = MARGINE + sx
            y = TARGA_Y + dy
            sup.blit(plate, (x, y))
            sup.blit(bandiera, (x + 20, y + 4))
            sup.blit(nome, nome.get_rect(midleft=(x + 62, y + h // 2 + 1)))
            S.scrivi(sup, "%s  ·  %s" % (p.nome.upper(), p.nazione.upper()), (x + larg + 12, y + h // 2 + 2),
                     17, S.SPENTO, 'midleft', contorno=2, ombra=(1, 1))
        else:
            plate = pygame.transform.flip(plate, True, False)
            x = L - MARGINE - larg + sx
            y = TARGA_Y + dy
            sup.blit(plate, (x, y))
            sup.blit(bandiera, (x + larg - 20 - 34, y + 4))
            sup.blit(nome, nome.get_rect(midright=(x + larg - 62, y + h // 2 + 1)))
            S.scrivi(sup, "%s  ·  %s" % (p.nome.upper(), p.nazione.upper()), (x - 12, y + h // 2 + 2),
                     17, S.SPENTO, 'midright', contorno=2, ombra=(1, 1))

    # -- timer
    def _disegna_badge(self, sup: pygame.Surface, incontro, dy: float) -> None:
        f_now = self._f
        t = max(0.0, incontro.tempo_rimasto)
        sec = int(math.ceil(t - 1e-6))
        sec = max(0, min(99, sec))
        urgente = sec <= 10 and incontro.fase == 'combattimento' and sec > 0
        w, h = BADGE_W, BADGE_H
        x = (L - w) // 2
        y = BADGE_Y + dy
        bordo = S.ORO
        if urgente:
            bordo = S.mescola(S.ORO, S.ROSSO_K1, S.pulsa(f_now / 60.0, 1.0))
        ombra = S.tinta(S.maschera_poligono(w, h, S.forma(w, h, -22, 22)), (0, 0, 0, 140))
        sup.blit(ombra, (x + 3, y + 6))
        pan = S.pannello(w, h, -22, 22, stop=((0.0, (34, 38, 58)), (0.5, (14, 16, 28)),
                                              (1.0, (6, 7, 13))), alpha=250,
                         bordo=bordo, spessore=3, lucido=0.22)
        sup.blit(pan, (x, y))
        # etichetta round
        S.scrivi(sup, "ROUND %d" % incontro.numero_round, (L // 2, y + 17), 21, S.ORO_CHIARO,
                 contorno=2, ombra=(1, 2), corsivo=True)
        # numero
        colore = S.BIANCO
        scala = 1.0
        if urgente:
            frazione = t - math.floor(t)
            scala = 1.0 + 0.18 * max(0.0, 1.0 - (1.0 - frazione) * 5.0) if frazione > 0.8 else 1.0
            colore = S.mescola((255, 110, 100), (255, 255, 255), S.pulsa(f_now / 60.0, 1.0) * 0.4)
        elif incontro.fase in ('fine_round', 'fine_partita') and sec == 0:
            colore = (255, 120, 110)
        S.scrivi(sup, "%02d" % sec if sec < 100 else str(sec), (L // 2, y + 55), 66, colore,
                 scala=scala, contorno=3, ombra=(2, 3))

    # -- energia
    def _disegna_energia(self, sup: pygame.Surface, incontro, i: int, dy: float) -> None:
        l = incontro.lottatori[i]
        f_now = self._f
        e = S.limita(self._energia[i])
        piena = l.energia >= C.ENERGIA_MAX - 1e-6
        w, h = ENERGIA_W, ENERGIA_H
        n = ENERGIA_SEGMENTI
        gap, incl = 5, 8
        sw = (w - gap * (n - 1)) / n
        x0 = MARGINE + 4 if i == 0 else L - MARGINE - 4 - w
        y0 = ENERGIA_Y + dy
        lampo = f_now - self._super_f[i]
        # alone dorato quando piena
        if piena:
            k = _quantizza(0.5 + 0.4 * S.pulsa(f_now / 60.0, 1.4), 8)
            sup.blit(S.alone(w + 90, h + 70, ENERGIA_PIENA, k), (x0 - 45, y0 - 35),
                     special_flags=pygame.BLEND_RGB_ADD)
        elif 0 <= lampo < 24:
            k = _quantizza(1.0 - lampo / 24.0, 8)
            sup.blit(S.alone(w + 90, h + 70, ENERGIA_PIENA, k), (x0 - 45, y0 - 35),
                     special_flags=pygame.BLEND_RGB_ADD)
        col = S.mescola(ENERGIA_BASSA, ENERGIA_PIENA, e ** 1.5)
        if piena:
            col = S.mescola(ENERGIA_PIENA, (255, 255, 235), S.pulsa(f_now / 60.0, 2.0) * 0.6)
        piastra = S.pannello(w + 26, h + 12, -9, -9, colore=(10, 11, 20), colore_basso=(4, 4, 9),
                             alpha=200, bordo=S.mescola(col, (40, 44, 64), 0.55) if piena else (52, 58, 82),
                             spessore=2)
        if i == 1:
            piastra = pygame.transform.flip(piastra, True, False)
        sup.blit(piastra, (x0 - 13, y0 - 6))
        for k in range(n):
            # k = indice del segmento dall'esterno verso l'interno
            if i == 0:
                sx_ = x0 + k * (sw + gap)
            else:
                sx_ = x0 + w - (k + 1) * sw - k * gap
            q = S.limita(e * n - k)
            pts = _polig_barra(sx_, y0, sw, h, incl) if i == 0 else \
                [(sx_ + incl, y0), (sx_ + sw, y0), (sx_ + sw - incl, y0 + h), (sx_, y0 + h)]
            # sfondo del segmento
            S.poligono_aa(sup, (6, 7, 13, 235), pts)
            bordo_c = S.mescola((84, 92, 120), col, 0.85) if q > 0 else (70, 76, 100)
            pygame.draw.aalines(sup, bordo_c, True, pts)
            if q > 0.01:
                interni = S.rientra(pts, 2)
                if q < 0.999:
                    interni = _taglia_segmento(interni, q, i == 0)
                cc = col
                S.poligono_aa(sup, S.scurisci(cc, 0.25), interni)
                chiaro = _limita_poligono_y(interni, y0 + h * 0.5)
                if len(chiaro) >= 3:
                    S.poligono_aa(sup, S.schiarisci(cc, 0.35), chiaro)
        # etichetta
        ic = S.fulmine(20, ENERGIA_PIENA if piena else S.mescola(ENERGIA_BASSA, ENERGIA_PIENA, e))
        ly = y0 - 15
        if piena:
            sc = 1.0 + 0.09 * S.pulsa(f_now / 60.0, 2.2)
            testo_s = S.testo("SUPER!", 26, (255, 246, 190), sfumatura_testo=S.SFUMATURA_ORO,
                              corsivo=True, contorno=2, ombra=(1, 2))
            if i == 0:
                S.piazza(sup, testo_s, (x0 + 22, ly), 'midleft', scala=sc)
                sup.blit(ic, ic.get_rect(midleft=(x0 - 2, ly)))
            else:
                S.piazza(sup, testo_s, (x0 + w - 22, ly), 'midright', scala=sc)
                sup.blit(ic, ic.get_rect(midright=(x0 + w + 2, ly)))
        else:
            if i == 0:
                sup.blit(ic, ic.get_rect(midleft=(x0 - 2, ly)))
                S.scrivi(sup, "SUPER", (x0 + 22, ly + 1), 17, S.SPENTO, 'midleft', corsivo=True,
                         contorno=2, ombra=(1, 1))
            else:
                sup.blit(ic, ic.get_rect(midright=(x0 + w + 2, ly)))
                S.scrivi(sup, "SUPER", (x0 + w - 22, ly + 1), 17, S.SPENTO, 'midright', corsivo=True,
                         contorno=2, ombra=(1, 1))

    # -- combo
    @staticmethod
    def _sprite_combo(n: int, danno: int, acc: tuple, lato: int) -> pygame.Surface:
        """Cartello del combo (cache per numero/danno/colore)."""
        chiave = ('hud_combo', n, danno, tuple(acc), lato)

        def crea():
            num = S.testo(str(n), 150, S.ORO_CHIARO, sfumatura_testo=S.SFUMATURA_ORO, corsivo=True,
                          contorno=5, colore_contorno=(96, 30, 6), contorno_esterno=2, ombra=(3, 5))
            colpi = S.testo("COLPI", 50, S.BIANCO, corsivo=True, contorno=3, ombra=(2, 3))
            dan = S.testo("DANNO  %d" % danno, 30, acc, corsivo=True, contorno=3, ombra=(2, 2))
            tag = S.testo("COMBO", 24, S.BIANCO, corsivo=True, contorno=2, ombra=(1, 2),
                          spaziatura=5)
            gap = 10
            w = 34 + num.get_width() + gap + max(colpi.get_width(), dan.get_width()) + 44
            h = 34 + num.get_height() - 26
            pan = S.pannello(w, h, -18, -18, stop=((0.0, (24, 26, 42)), (1.0, (6, 7, 14))), alpha=205,
                             bordo=S.mescola(acc, (255, 255, 255), 0.1), spessore=3, lucido=0.16)
            surf = pygame.Surface((w, h + 14), pygame.SRCALPHA)
            xn = 40
            if lato > 0:
                surf.blit(pan, (0, 14))
                surf.blit(tag, (xn - 4, 0))
                surf.blit(num, (xn - 4, 8))
                xt = xn - 4 + num.get_width() + gap
                surf.blit(colpi, (xt, 14 + h // 2 - colpi.get_height() + 4))
                surf.blit(dan, (xt + 2, 14 + h // 2 + 6))
            else:
                surf.blit(pygame.transform.flip(pan, True, False), (0, 14))
                surf.blit(tag, (w - xn - tag.get_width() + 4, 0))
                surf.blit(num, (w - xn - num.get_width() + 4, 8))
                xt = w - xn + 4 - num.get_width() - gap
                surf.blit(colpi, (xt - colpi.get_width(), 14 + h // 2 - colpi.get_height() + 4))
                surf.blit(dan, (xt - dan.get_width() - 2, 14 + h // 2 + 6))
            return S._ottimizza(surf)
        return S._in_cache(chiave, crea)

    def _disegna_combo(self, sup: pygame.Surface, incontro, i: int) -> None:
        st = self._combo[i]
        f = self._f
        if st.n < 2:
            return
        if st.vivo:
            alpha = 255
        else:
            resto = f - st.f_fine
            if resto > 70:
                return
            alpha = 255 * (1.0 - S.progresso(resto, 40, 30))
        acc = S.accento_leggibile(_accento(incontro.lottatori[i].personaggio))
        dt = f - st.f_colpo
        scala = 0.6 + 0.4 * S.ease_out_back(dt / 12.0, 2.2) if dt < 12 else 1.0
        entrata = S.ease_out_cubic(dt / 9.0) if st.n <= 2 else 1.0
        lato = 1 if i == 0 else -1
        surf = self._sprite_combo(st.n, int(round(st.danno)), acc, lato)
        desl = (1.0 - entrata) * 260 * -lato
        y = 232
        if scala != 1.0:
            surf = S.scala_superficie(surf, scala)
        r = surf.get_rect()
        if i == 0:
            r.midleft = (-16 + desl, y)
        else:
            r.midright = (L + 16 + desl, y)
        S.blit_alpha(sup, surf, r.topleft, alpha)

    # -- conteggio dell'arbitro
    def _disegna_conteggio(self, sup: pygame.Surface, incontro) -> None:
        c = self._conteggio
        if c is None:
            return
        f = self._f
        dt = f - c['f0']
        alpha = 255.0
        if c['fine'] is not None:
            alpha = 255 * (1 - S.progresso(f, c['fine'], 14))
        n = c['numero']
        colori = {1: (255, 255, 255), 2: (255, 236, 120), 3: (255, 168, 60)}
        base = colori.get(n, (255, 84, 70))
        pop = S.ease_out_back(dt / 10.0) if dt < 10 else 1.0
        scala = 0.5 + 0.5 * pop if dt < 10 else 1.0 + 0.03 * math.sin(dt * 0.25)
        if dt < 3:
            scala *= 1.25
        g = ((0.0, S.schiarisci(base, 0.7)), (0.5, base), (1.0, S.scurisci(base, 0.35)))
        num = S.testo(str(n), 270, base, sfumatura_testo=g, contorno=6, contorno_esterno=3,
                      ombra=(4, 6), colore_contorno=(255, 255, 255) if n < 4 else (255, 240, 240),
                      colore_esterno=(30, 6, 10))
        l = incontro.lottatori[c['indice']]
        p = l.personaggio
        yc = 316
        S.blit_alpha(sup, _banda(L, 270, 215), (0, yc - 135), alpha)
        S.piazza(sup, S.testo("CONTEGGIO", 34, S.ORO_CHIARO, corsivo=True, contorno=2, ombra=(1, 2),
                              spaziatura=8), (L // 2, yc - 112), 'center', alpha)
        sub = "%s  ·  ATTERRAMENTO %d/%d" % (p.soprannome, max(1, l.atterramenti), C.ATTERRAMENTI_TKO)
        S.scrivi(sup, sub, (L // 2, yc + 114), 26, S.accento_leggibile(_accento(p)), 'center',
                 alpha=alpha, corsivo=True, contorno=2, ombra=(1, 2))
        S.piazza(sup, num, (L // 2, yc + 2), 'center', alpha, scala)
        # tacche del conteggio
        for k in range(1, 5):
            col = base if k <= n else (60, 66, 90)
            ic = S.rombo(16, col, pieno=k <= n)
            sup.blit(ic, ic.get_rect(center=(L // 2 + (k - 2.5) * 30, yc + 142)), )

    # -- annunci
    def _disegna_annuncio(self, sup: pygame.Surface, incontro, a: _Annuncio) -> None:
        t = self._f - a.f0
        if t < 0:
            return
        durata = a.durata
        resto = durata - t
        if a.tipo == 'round':
            self._an_round(sup, a, t, resto)
        elif a.tipo == 'fight':
            self._an_fight(sup, a, t, resto)
        elif a.tipo == 'ko':
            self._an_ko(sup, a, t, resto)
        elif a.tipo in ('tempo', 'pareggio'):
            self._an_grande(sup, a, t, resto)
        elif a.tipo in ('vince', 'vince_partita'):
            self._an_vince(sup, a, t, resto)

    @staticmethod
    def _uscita(resto: float, frame: float = 14.0) -> float:
        """1 -> 0 negli ultimi `frame` frame."""
        return S.limita(resto / frame)

    def _fascia(self, sup, yc: float, altezza: int, prog: float, alpha: float, colore_linea) -> None:
        h = int(altezza * S.limita(prog))
        if h < 4:
            return
        S.blit_alpha(sup, _banda(L, max(4, h), 228), (0, int(yc - h / 2)), alpha)
        lw = int(L * S.ease_out_cubic(prog))
        for sgn in (-1, 1):
            yy = int(yc + sgn * (h / 2 - h * 0.14))
            r = pygame.Rect(0, 0, lw, 3)
            r.center = (L // 2, yy)
            sup.fill(S.mescola(colore_linea, (0, 0, 0), 0.0), r) if alpha >= 250 else \
                sup.blit(S.velo(lw, 3, colore_linea, int(alpha)), r)

    def _an_round(self, sup, a, t, resto) -> None:
        numero, p1, p2 = a.extra
        usc = self._uscita(resto, 16)
        alpha = 255 * usc
        yc = 322
        self._fascia(sup, yc, 232, S.ease_out_cubic(t / 12.0) * (0.85 + 0.15 * usc), alpha, S.ORO)
        e = S.ease_out_cubic(t / 15.0)
        roundt = S.testo("ROUND", 104, S.BIANCO, sfumatura_testo=S.SFUMATURA_BIANCO, corsivo=True,
                         contorno=4, colore_contorno=(180, 14, 32), contorno_esterno=3, ombra=(3, 5))
        num = S.testo(numero, 210, S.ORO_CHIARO, sfumatura_testo=S.SFUMATURA_ORO, corsivo=True,
                      contorno=5, colore_contorno=(120, 34, 8), contorno_esterno=3, ombra=(4, 6))
        gap = 26
        wtot = roundt.get_width() + gap + num.get_width()
        x_r = L // 2 - wtot // 2 + roundt.get_width() // 2
        x_n = L // 2 + wtot // 2 - num.get_width() // 2
        S.piazza(sup, roundt, (x_r - (1 - e) * 700, yc - 8), 'center', alpha)
        S.piazza(sup, num, (x_n + (1 - e) * 700, yc - 2), 'center', alpha)
        if a.extra:
            k = S.progresso(t, 12, 12)
            vs = S.testo("%s   VS   %s" % (p1.soprannome, p2.soprannome), 30, S.BIANCO,
                         corsivo=True, contorno=3, ombra=(2, 3), spaziatura=2)
            S.piazza(sup, vs, (L // 2, yc + 82), 'center', alpha * k, 1.0 + (1 - k) * 0.2)
            if a.sotto:
                pulsazione = S.pulsa(t / 60.0, 1.5)
                S.scrivi(sup, a.sotto, (L // 2, yc - 92), 26, S.mescola((255, 120, 110),
                                                                        (255, 220, 200), pulsazione),
                         'center', alpha=alpha * k, corsivo=True, contorno=3, ombra=(2, 2),
                         spaziatura=6)

    def _an_fight(self, sup, a, t, resto) -> None:
        usc = self._uscita(resto, 14)
        if t < 10:
            scala = 0.3 + 0.95 * S.ease_out_back(t / 10.0, 2.4)
        elif t < 18:
            scala = 1.25 - 0.25 * S.ease_out_cubic((t - 10) / 8.0)
        else:
            scala = 1.0 + 0.05 * math.sin((t - 18) * 0.35) + (1 - usc) * 0.55
        alpha = 255 * S.limita(t / 4.0) * usc
        yc = 318
        # esplosione additiva dietro il testo
        if t < 30:
            k = _quantizza(1.0 - t / 30.0, 10)
            if k > 0:
                sup.blit(S.alone(1000, 380, (255, 190, 70), k), (L // 2 - 500, yc - 190),
                         special_flags=pygame.BLEND_RGB_ADD)
        g = S.SFUMATURA_ORO
        txt = S.testo("FIGHT!", 214, S.ORO_CHIARO, sfumatura_testo=g, corsivo=True, contorno=6,
                      colore_contorno=(112, 34, 6), contorno_esterno=3, ombra=(4, 7))
        sx = int(math.sin(t * 2.7) * 6 * max(0.0, 1 - t / 16.0))
        S.piazza(sup, txt, (L // 2 + sx, yc), 'center', alpha, scala)

    def _an_ko(self, sup, a, t, resto) -> None:
        usc = self._uscita(resto, 16)
        alpha = 255 * S.limita(t / 3.0) * usc
        tec = bool(a.extra)
        yc = 318
        self._fascia(sup, yc, 300 if not tec else 320, S.ease_out_cubic(t / 8.0), alpha, S.ROSSO_K1)
        if t < 10:
            scala = 1.0 + 2.6 * (1 - S.ease_out_cubic(t / 10.0))
        else:
            scala = 1.0 + 0.035 * math.sin((t - 10) * 0.22)
        scala *= 1.0 + (1 - usc) * 0.4
        dim = 250 if not tec else 168
        if t < 46:
            k = _quantizza(1.0 - t / 46.0, 10)
            if k > 0:
                sup.blit(S.alone(1100, 420, (255, 50, 40), k), (L // 2 - 550, yc - 210),
                         special_flags=pygame.BLEND_RGB_ADD)
        g = ((0.0, (255, 214, 200)), (0.36, (255, 70, 58)), (0.58, (196, 14, 30)),
             (1.0, (255, 60, 50)))
        txt = S.testo(a.testo, dim, S.ROSSO_K1, sfumatura_testo=g, corsivo=True, contorno=7,
                      colore_contorno=(255, 255, 255), contorno_esterno=4,
                      colore_esterno=(14, 2, 6), ombra=(5, 8))
        sh = int(math.sin(t * 3.1) * 9 * max(0.0, 1 - t / 18.0))
        sv = int(math.cos(t * 2.3) * 6 * max(0.0, 1 - t / 18.0))
        S.piazza(sup, txt, (L // 2 + sh, yc - (10 if tec else 0) + sv), 'center', alpha, scala)
        if a.sotto:
            k = S.progresso(t, 16, 12)
            S.scrivi(sup, a.sotto, (L // 2, yc + 100), 30, S.BIANCO, 'center', alpha=alpha * k,
                     corsivo=True, contorno=3, ombra=(2, 3), spaziatura=6)

    def _an_grande(self, sup, a, t, resto) -> None:
        usc = self._uscita(resto, 14)
        alpha = 255 * S.limita(t / 4.0) * usc
        yc = 322
        self._fascia(sup, yc, 230, S.ease_out_cubic(t / 10.0), alpha, S.ARGENTO)
        if t < 12:
            scala = 1.0 + 1.6 * (1 - S.ease_out_back(t / 12.0, 1.4))
        else:
            scala = 1.0 + (1 - usc) * 0.25
        dim = 180 if a.tipo == 'tempo' else 138
        txt = S.testo(a.testo, dim, S.BIANCO, sfumatura_testo=S.SFUMATURA_ARGENTO, corsivo=True,
                      contorno=6, colore_contorno=(24, 30, 60), contorno_esterno=3, ombra=(4, 6))
        S.piazza(sup, txt, (L // 2, yc - (0 if not a.sotto else 14)), 'center', alpha, scala)
        if a.sotto:
            k = S.progresso(t, 14, 12)
            S.scrivi(sup, a.sotto, (L // 2, yc + 82), 26, S.SPENTO, 'center', alpha=alpha * k,
                     corsivo=True, contorno=3, ombra=(1, 2), spaziatura=5)

    def _an_vince(self, sup, a, t, resto) -> None:
        p = a.extra
        acc = _accento(p)
        finale = a.tipo == 'vince_partita'
        usc = 1.0 if finale else self._uscita(resto, 16)
        alpha = 255 * S.limita(t / 5.0) * usc
        yc = 322 if not finale else 300
        self._fascia(sup, yc, 300, S.ease_out_cubic(t / 12.0), alpha, S.mescola(acc, (255, 255, 255), 0.15))
        e = S.ease_out_cubic(t / 16.0)
        vince = S.testo("VINCE", 78, S.BIANCO, sfumatura_testo=S.SFUMATURA_BIANCO, corsivo=True,
                        contorno=4, ombra=(3, 4), spaziatura=6)
        nome = S.testo(p.soprannome, 148, S.BIANCO, sfumatura_testo=_testo_accento(acc),
                       corsivo=True, contorno=6, colore_contorno=S.scurisci(acc, 0.72),
                       contorno_esterno=3, ombra=(4, 6))
        if nome.get_width() > 1120:
            nome = S.scala_superficie(nome, 1120 / nome.get_width())
        S.piazza(sup, vince, (L // 2 - (1 - e) * 500, yc - 88), 'center', alpha)
        scala = 1.0 + (1 - S.ease_out_back(t / 14.0, 1.6)) * 0.9 if t < 14 else \
            1.0 + 0.02 * math.sin(t * 0.18)
        S.piazza(sup, nome, (L // 2, yc + 6), 'center', alpha, scala)
        k = S.progresso(t, 14, 12)
        if a.sotto:
            S.scrivi(sup, a.sotto, (L // 2, yc + 100), 28, S.accento_leggibile(acc), 'center',
                     alpha=alpha * k, corsivo=True, contorno=3, ombra=(2, 3), spaziatura=6)


# ---- geometria dei segmenti dell'energia
def _taglia_segmento(pts: list, q: float, da_sinistra: bool) -> list:
    """Parte piena di un segmento (quadrilatero) tagliata parallelamente ai lati."""
    (a, b, c, d) = pts
    if da_sinistra:
        top = (a[0] + (b[0] - a[0]) * q, a[1])
        bot = (d[0] + (c[0] - d[0]) * q, d[1])
        return [a, top, bot, d]
    top = (b[0] - (b[0] - a[0]) * q, b[1])
    bot = (c[0] - (c[0] - d[0]) * q, c[1])
    return [top, b, c, bot]


def _limita_poligono_y(pts: list, y_max: float) -> list:
    """Ritaglia un quadrilatero convesso tenendo solo la parte con y <= y_max."""
    out = []
    n = len(pts)
    for k in range(n):
        p, q = pts[k], pts[(k + 1) % n]
        p_in, q_in = p[1] <= y_max, q[1] <= y_max
        if p_in:
            out.append(p)
        if p_in != q_in and abs(q[1] - p[1]) > 1e-9:
            t = (y_max - p[1]) / (q[1] - p[1])
            out.append((p[0] + (q[0] - p[0]) * t, y_max))
    return out
