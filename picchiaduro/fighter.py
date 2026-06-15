"""Il kickboxer: stato, footwork 2.5D, colpi, stamina e disegno."""

import pygame

from . import settings as S
from . import prospettiva as P


class Lottatore:
    """Un kickboxer controllato da un giocatore o dalla CPU."""

    def __init__(self, x, z, nome, colore, controlli=None, guarda_destra=True):
        self.nome = nome
        self.colore = colore
        self.controlli = controlli or {}

        self.larghezza = S.LARGHEZZA_LOTTATORE
        self.altezza = S.ALTEZZA_LOTTATORE

        # posizione nel mondo: x lungo il ring, z profondita' (centro corpo)
        self.x = float(x)
        self.z = float(z)
        self.vx = 0.0
        self.vz = 0.0

        self.guarda_destra = guarda_destra
        self.vita = S.VITA_MAX
        self.stamina = S.STAMINA_MAX
        self.round_vinti = 0

        self.sta_parando = False

        # gestione colpi
        self.attacco = None
        self.frame_attacco = 0
        self.colpo_a_segno = False

        self.hitstun = 0
        self.ko = False

    # ---------------------------------------------------------------- stato
    @property
    def meta_larghezza(self):
        return self.larghezza / 2

    def puo_agire(self):
        return not self.ko and self.hitstun <= 0 and self.attacco is None

    def inizia_attacco(self, nome):
        if not self.puo_agire():
            return False
        costo = S.ATTACCHI[nome]["stamina"]
        if self.stamina < S.STAMINA_MIN_COLPO:
            return False
        self.attacco = nome
        self.frame_attacco = 0
        self.colpo_a_segno = False
        self.vx = self.vz = 0
        self.stamina = max(0, self.stamina - costo)
        return True

    def attacco_attivo(self):
        """Vero se la hitbox del colpo corrente e' nella finestra attiva."""
        if self.attacco is None:
            return False
        ini, fine = S.ATTACCHI[self.attacco]["attivo"]
        return ini <= self.frame_attacco <= fine

    def colpisce(self, avversario):
        """Vero se il colpo attivo raggiunge l'avversario (in X e in Z)."""
        if not self.attacco_attivo():
            return False
        if abs(self.z - avversario.z) > S.TOLLERANZA_PROFONDITA:
            return False
        dati = S.ATTACCHI[self.attacco]
        segno = 1 if self.guarda_destra else -1
        fronte = self.x + segno * self.meta_larghezza
        estremo = fronte + segno * dati["portata"]
        lo, hi = min(fronte, estremo), max(fronte, estremo)
        return lo <= avversario.x <= hi

    def subisci_colpo(self, dati, direzione):
        if self.ko:
            return
        danno = dati["danno"]
        kb = dati["knockback"]
        if self.sta_parando:
            danno *= S.DANNO_PARATA
            kb *= S.KB_PARATA
        else:
            self.hitstun = dati["stordimento"]
            self.attacco = None
        self.vita = max(0, self.vita - danno)
        self.vx = kb * direzione
        if self.vita <= 0:
            self.ko = True

    # -------------------------------------------------------------- input
    def gestisci_input(self, tasti):
        if not self.puo_agire():
            return
        c = self.controlli
        self.sta_parando = tasti[c["guardia"]]

        self.vx = self.vz = 0
        if not self.sta_parando:
            if tasti[c["sinistra"]]:
                self.vx = -S.VELOCITA_X
            if tasti[c["destra"]]:
                self.vx = S.VELOCITA_X
            if tasti[c["avanti"]]:        # verso la camera (Z-)
                self.vz = -S.VELOCITA_Z
            if tasti[c["indietro"]]:      # verso il fondo (Z+)
                self.vz = S.VELOCITA_Z

        if tasti[c["jab"]]:
            self.inizia_attacco("jab")
        elif tasti[c["diretto"]]:
            self.inizia_attacco("diretto")
        elif tasti[c["calcio_basso"]]:
            self.inizia_attacco("calcio_basso")
        elif tasti[c["calcio_alto"]]:
            self.inizia_attacco("calcio_alto")

    # ----------------------------------------------------------- aggiorna
    def aggiorna(self, avversario):
        if self.hitstun > 0:
            self.hitstun -= 1

        # recupero fiato (piu' lento mentre si para)
        rigen = S.STAMINA_RIGEN * (0.5 if self.sta_parando else 1.0)
        self.stamina = min(S.STAMINA_MAX, self.stamina + rigen)

        # avanzamento colpo
        if self.attacco is not None:
            self.frame_attacco += 1
            if self.frame_attacco > S.ATTACCHI[self.attacco]["durata"]:
                self.attacco = None

        # movimento nel piano del ring
        self.x += self.vx
        self.z += self.vz
        self.x = max(self.meta_larghezza,
                     min(S.RING_LARGHEZZA - self.meta_larghezza, self.x))
        self.z = max(0, min(S.RING_PROFONDITA, self.z))

        # orientamento verso l'avversario
        if avversario is not None and self.puo_agire():
            self.guarda_destra = avversario.x >= self.x

        self.vx *= 0.55  # smorza il knockback

    # ------------------------------------------------------------- reset
    def reset_round(self, x, z, guarda_destra):
        self.x = float(x)
        self.z = float(z)
        self.vx = self.vz = 0
        self.vita = S.VITA_MAX
        self.stamina = S.STAMINA_MAX
        self.guarda_destra = guarda_destra
        self.sta_parando = False
        self.attacco = None
        self.frame_attacco = 0
        self.colpo_a_segno = False
        self.hitstun = 0
        self.ko = False

    # ----------------------------------------------------------- disegno
    def disegna(self, surf):
        s = P.scala(self.z)
        piede_x, piede_y = P.proietta(self.x, self.z)
        larg = self.larghezza * s
        alt = self.altezza * s

        # ombra a terra (indizio di profondita')
        ombra = pygame.Surface((int(larg * 1.3), int(larg * 0.45)), pygame.SRCALPHA)
        pygame.draw.ellipse(ombra, (*S.OMBRA, 110), ombra.get_rect())
        surf.blit(ombra, (piede_x - larg * 0.65, piede_y - larg * 0.22))

        corpo = pygame.Rect(0, 0, int(larg), int(alt))
        corpo.midbottom = (int(piede_x), int(piede_y))

        colore = S.BIANCO if self.hitstun > 0 else self.colore
        pygame.draw.rect(surf, colore, corpo, border_radius=int(6 * s) + 1)
        pygame.draw.rect(surf, S.NERO, corpo, width=2, border_radius=int(6 * s) + 1)

        # testa
        raggio = int(22 * s)
        cx = corpo.centerx
        cy = corpo.top - raggio + int(6 * s)
        pygame.draw.circle(surf, colore, (cx, cy), raggio)
        pygame.draw.circle(surf, S.NERO, (cx, cy), raggio, 2)
        dx = raggio // 2 if self.guarda_destra else -raggio // 2
        pygame.draw.circle(surf, S.NERO, (cx + dx, cy - int(4 * s)), max(2, int(4 * s)))

        # guantoni in guardia
        if self.sta_parando:
            gy = corpo.top + int(alt * 0.28)
            for off in (-int(larg * 0.30), int(larg * 0.30)):
                pygame.draw.circle(surf, S.ROSSO, (cx + off, gy), int(11 * s))
            scudo = corpo.inflate(int(16 * s), int(16 * s))
            pygame.draw.rect(surf, S.GIALLO, scudo, width=2,
                             border_radius=int(10 * s))

        # arto che colpisce
        if self.attacco is not None:
            self._disegna_colpo(surf, corpo, s)

    def _disegna_colpo(self, surf, corpo, s):
        dati = S.ATTACCHI[self.attacco]
        attivo = self.attacco_attivo()
        segno = 1 if self.guarda_destra else -1
        y = corpo.top + int(corpo.height * dati["offset_y"])
        lung = int(dati["portata"] * s * (1.0 if attivo else 0.55))
        spess = int(dati["altezza"] * s)
        x = corpo.right if self.guarda_destra else corpo.left - lung
        rect = pygame.Rect(x, y, lung, spess)
        if "calcio" in self.attacco:
            col = S.ROSSO if attivo else S.ARANCIO
        else:
            col = S.ARANCIO if attivo else S.GIALLO
        pygame.draw.rect(surf, col, rect, border_radius=int(4 * s))
        # guantone/piede in punta
        punta = (rect.right, rect.centery) if self.guarda_destra else (rect.left, rect.centery)
        pygame.draw.circle(surf, col, punta, max(3, int(10 * s)))
