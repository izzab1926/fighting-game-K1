"""Il combattente: stato, fisica, attacchi e disegno."""

import pygame

from . import settings as S


class Lottatore:
    """Un personaggio controllato da un giocatore."""

    def __init__(self, x, nome, colore, controlli, guarda_destra=True):
        self.nome = nome
        self.colore = colore
        self.controlli = controlli

        self.larghezza = S.LARGHEZZA_LOTTATORE
        self.altezza = S.ALTEZZA_LOTTATORE
        self.x = float(x)
        self.y = float(S.SUOLO - self.altezza)
        self.vx = 0.0
        self.vy = 0.0

        self.guarda_destra = guarda_destra
        self.vita = S.VITA_MAX
        self.round_vinti = 0

        self.a_terra = True
        self.accovacciato = False
        self.sta_parando = False

        # gestione attacchi
        self.attacco = None          # nome dell'attacco in corso
        self.frame_attacco = 0
        self.colpo_a_segno = False   # il colpo corrente ha già colpito?

        self.hitstun = 0             # frame in cui non può agire
        self.ko = False

    # ------------------------------------------------------------------ geom
    @property
    def altezza_corrente(self):
        if self.accovacciato and self.a_terra:
            return S.ALTEZZA_ACCOVACCIATO
        return self.altezza

    @property
    def rect(self):
        h = self.altezza_corrente
        return pygame.Rect(int(self.x), int(S.SUOLO - h), self.larghezza, h)

    @property
    def centro_x(self):
        return self.x + self.larghezza / 2

    # ---------------------------------------------------------------- stato
    def puo_agire(self):
        return not self.ko and self.hitstun <= 0 and self.attacco is None

    def inizia_attacco(self, nome):
        if not self.puo_agire() or self.accovacciato:
            return
        self.attacco = nome
        self.frame_attacco = 0
        self.colpo_a_segno = False
        self.vx = 0

    def hitbox_attacco(self):
        """Rect attivo dell'attacco corrente, o None."""
        if self.attacco is None:
            return None
        dati = S.ATTACCHI[self.attacco]
        ini, fine = dati["attivo"]
        if not (ini <= self.frame_attacco <= fine):
            return None
        cima = S.SUOLO - self.altezza_corrente
        y = cima + dati["offset_y"]
        portata = dati["portata"]
        if self.guarda_destra:
            x = self.x + self.larghezza
        else:
            x = self.x - portata
        return pygame.Rect(int(x), int(y), portata, dati["altezza_hitbox"])

    def subisci_colpo(self, danno, knockback, direzione):
        if self.ko:
            return
        if self.sta_parando:
            danno *= S.DANNO_PARATA
            knockback *= 0.4
        else:
            self.hitstun = S.STORDIMENTO_COLPO
            self.attacco = None
        self.vita = max(0, self.vita - danno)
        self.vx = knockback * direzione
        if self.vita <= 0:
            self.ko = True

    # ------------------------------------------------------------- aggiorna
    def gestisci_input(self, tasti):
        if not self.puo_agire():
            return
        c = self.controlli
        self.sta_parando = tasti[c["parata"]] and self.a_terra
        self.accovacciato = tasti[c["accovaccia"]] and self.a_terra

        self.vx = 0
        if not self.sta_parando and not self.accovacciato:
            if tasti[c["sinistra"]]:
                self.vx = -S.VELOCITA_CAMMINO
            if tasti[c["destra"]]:
                self.vx = S.VELOCITA_CAMMINO
            if tasti[c["salta"]] and self.a_terra:
                self.vy = S.FORZA_SALTO
                self.a_terra = False

        if tasti[c["pugno"]]:
            self.inizia_attacco("pugno")
        elif tasti[c["calcio"]]:
            self.inizia_attacco("calcio")

    def aggiorna(self, avversario):
        if self.hitstun > 0:
            self.hitstun -= 1

        # avanzamento attacco
        if self.attacco is not None:
            self.frame_attacco += 1
            if self.frame_attacco > S.ATTACCHI[self.attacco]["durata"]:
                self.attacco = None

        # fisica
        self.vy += S.GRAVITA
        self.x += self.vx
        self.y += self.vy

        if self.y >= S.SUOLO - self.altezza:
            self.y = S.SUOLO - self.altezza
            self.vy = 0
            self.a_terra = True

        # limiti arena
        self.x = max(0, min(S.LARGHEZZA - self.larghezza, self.x))

        # orientamento verso l'avversario (solo se libero di muoversi)
        if avversario is not None and self.puo_agire():
            self.guarda_destra = avversario.centro_x >= self.centro_x

        self.vx *= 0.6  # attrito leggero sul knockback

    # ---------------------------------------------------------------- reset
    def reset_round(self, x, guarda_destra):
        self.x = float(x)
        self.y = float(S.SUOLO - self.altezza)
        self.vx = self.vy = 0
        self.vita = S.VITA_MAX
        self.guarda_destra = guarda_destra
        self.a_terra = True
        self.accovacciato = False
        self.sta_parando = False
        self.attacco = None
        self.hitstun = 0
        self.ko = False

    # --------------------------------------------------------------- disegno
    def disegna(self, surf):
        r = self.rect

        # corpo
        colore = self.colore
        if self.hitstun > 0:
            colore = S.BIANCO
        pygame.draw.rect(surf, colore, r, border_radius=6)
        pygame.draw.rect(surf, S.NERO, r, width=2, border_radius=6)

        # testa
        raggio = 22
        cx = int(self.centro_x)
        cy = r.top - raggio + 6
        pygame.draw.circle(surf, colore, (cx, cy), raggio)
        pygame.draw.circle(surf, S.NERO, (cx, cy), raggio, 2)

        # occhio nella direzione di sguardo
        dx = raggio // 2 if self.guarda_destra else -raggio // 2
        pygame.draw.circle(surf, S.NERO, (cx + dx, cy - 4), 4)

        # scudo di parata
        if self.sta_parando:
            scudo = r.inflate(18, 18)
            pygame.draw.rect(surf, S.GIALLO, scudo, width=3, border_radius=10)

        # braccio/gamba d'attacco
        hb = self.hitbox_attacco()
        if hb is not None:
            col = S.ARANCIO if self.attacco == "pugno" else S.ROSSO
            pygame.draw.rect(surf, col, hb, border_radius=4)
