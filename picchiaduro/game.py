"""Loop principale, stati di gioco, ring 2.5D e HUD del kickboxing."""

import sys

import pygame

from . import settings as S
from . import prospettiva as P
from .fighter import Lottatore
from .ia import IAKickboxer

# Stati di gioco
MENU = "menu"
COMBATTIMENTO = "combattimento"
FINE_ROUND = "fine_round"
FINE_PARTITA = "fine_partita"

# Posizioni di partenza nel mondo
START_X1 = S.RING_LARGHEZZA * 0.30
START_X2 = S.RING_LARGHEZZA * 0.70
START_Z = S.RING_PROFONDITA * 0.5


class Gioco:
    def __init__(self):
        pygame.init()
        self.schermo = pygame.display.set_mode((S.LARGHEZZA, S.ALTEZZA))
        pygame.display.set_caption(S.TITOLO)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 28)
        self.font_grande = pygame.font.SysFont("consolas", 64, bold=True)
        self.font_piccolo = pygame.font.SysFont("consolas", 20)

        self.stato = MENU
        self.in_esecuzione = True
        self.vs_cpu = True               # modalita' selezionata nel menu
        self.ia = None
        self.crea_lottatori()
        self.timer_pausa = 0.0
        self.tempo_round = float(S.DURATA_ROUND)
        self.messaggio = ""

    # ------------------------------------------------------------- setup
    def crea_lottatori(self):
        self.p1 = Lottatore(START_X1, START_Z, "Giocatore 1", S.BLU,
                            S.CONTROLLI_P1, guarda_destra=True)
        nome2 = "CPU" if self.vs_cpu else "Giocatore 2"
        self.p2 = Lottatore(START_X2, START_Z, nome2, S.ROSSO,
                            S.CONTROLLI_P2, guarda_destra=False)

    def nuovo_round(self):
        self.p1.reset_round(START_X1, START_Z, True)
        self.p2.reset_round(START_X2, START_Z, False)
        self.tempo_round = float(S.DURATA_ROUND)
        self.stato = COMBATTIMENTO

    def nuova_partita(self):
        self.p2.nome = "CPU" if self.vs_cpu else "Giocatore 2"
        self.ia = IAKickboxer(difficolta="media") if self.vs_cpu else None
        self.p1.round_vinti = 0
        self.p2.round_vinti = 0
        self.nuovo_round()

    # -------------------------------------------------------------- eventi
    def gestisci_eventi(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.in_esecuzione = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.stato == MENU:
                        self.in_esecuzione = False
                    else:
                        self.stato = MENU
                elif self.stato == MENU:
                    if ev.key in (pygame.K_UP, pygame.K_DOWN,
                                  pygame.K_LEFT, pygame.K_RIGHT):
                        self.vs_cpu = not self.vs_cpu
                    elif ev.key == pygame.K_RETURN:
                        self.nuova_partita()
                elif self.stato == FINE_PARTITA and ev.key == pygame.K_RETURN:
                    self.stato = MENU

    # ------------------------------------------------------------ logica
    def risolvi_colpi(self, attaccante, difensore):
        if attaccante.colpo_a_segno:
            return
        if attaccante.colpisce(difensore):
            dati = S.ATTACCHI[attaccante.attacco]
            direzione = 1 if attaccante.guarda_destra else -1
            difensore.subisci_colpo(dati, direzione)
            attaccante.colpo_a_segno = True

    def aggiorna(self, dt):
        if self.stato == COMBATTIMENTO:
            tasti = pygame.key.get_pressed()
            self.p1.gestisci_input(tasti)
            if self.vs_cpu:
                self.ia.agisci(self.p2, self.p1)
            else:
                self.p2.gestisci_input(tasti)

            self.p1.aggiorna(self.p2)
            self.p2.aggiorna(self.p1)
            self.separa(self.p1, self.p2)

            self.risolvi_colpi(self.p1, self.p2)
            self.risolvi_colpi(self.p2, self.p1)

            self.tempo_round -= dt
            self.controlla_fine_round()

        elif self.stato == FINE_ROUND:
            self.timer_pausa -= dt
            if self.timer_pausa <= 0:
                if (self.p1.round_vinti >= S.ROUND_PER_VINCERE or
                        self.p2.round_vinti >= S.ROUND_PER_VINCERE):
                    self.stato = FINE_PARTITA
                else:
                    self.nuovo_round()

    def separa(self, a, b):
        """Evita la compenetrazione solo se vicini anche in profondita'."""
        if abs(a.z - b.z) > S.LARGHEZZA_LOTTATORE * 0.6:
            return
        dist = a.x - b.x
        minimo = a.meta_larghezza + b.meta_larghezza
        if abs(dist) < minimo:
            spinta = (minimo - abs(dist)) / 2 + 0.5
            segno = 1 if dist >= 0 else -1
            a.x += spinta * segno
            b.x -= spinta * segno
            for f in (a, b):
                f.x = max(f.meta_larghezza,
                          min(S.RING_LARGHEZZA - f.meta_larghezza, f.x))

    def controlla_fine_round(self):
        fine = False
        if self.p1.ko and not self.p2.ko:
            self.p2.round_vinti += 1
            self.messaggio = f"{self.p2.nome} vince il round!"
            fine = True
        elif self.p2.ko and not self.p1.ko:
            self.p1.round_vinti += 1
            self.messaggio = f"{self.p1.nome} vince il round!"
            fine = True
        elif (self.p1.ko and self.p2.ko) or self.tempo_round <= 0:
            if self.p1.vita > self.p2.vita:
                self.p1.round_vinti += 1
                self.messaggio = f"{self.p1.nome} vince ai punti!"
            elif self.p2.vita > self.p1.vita:
                self.p2.round_vinti += 1
                self.messaggio = f"{self.p2.nome} vince ai punti!"
            else:
                self.messaggio = "Pareggio!"
            fine = True

        if fine:
            self.timer_pausa = S.PAUSA_KO
            self.stato = FINE_ROUND

    # ------------------------------------------------------------- disegno
    def disegna_ring(self):
        self.schermo.fill(S.CIELO)
        bl, br, tr, tl = P.angoli_ring()
        # pavimento (trapezio prospettico)
        pygame.draw.polygon(self.schermo, S.RING, [bl, br, tr, tl])
        # corde/linee di profondita'
        for i in range(1, 4):
            z = S.RING_PROFONDITA * i / 4
            a = P.proietta(0, z)
            b = P.proietta(S.RING_LARGHEZZA, z)
            pygame.draw.line(self.schermo, S.GRIGIO_SCURO, a, b, 2)
        # bordo del ring
        pygame.draw.polygon(self.schermo, S.RING_BORDO, [bl, br, tr, tl], 4)

    def disegna_scena(self):
        self.disegna_ring()
        # disegna prima chi e' piu' in fondo (z maggiore)
        for f in sorted([self.p1, self.p2], key=lambda f: -f.z):
            f.disegna(self.schermo)
        self.disegna_hud()

    def disegna_barra(self, x, y, larg, alt, frazione, colore, allinea_destra):
        cornice = pygame.Rect(x - larg if allinea_destra else x, y, larg, alt)
        pygame.draw.rect(self.schermo, S.GRIGIO_SCURO, cornice)
        riempita = int(larg * max(0, min(1, frazione)))
        if allinea_destra:
            barra = pygame.Rect(cornice.right - riempita, y, riempita, alt)
        else:
            barra = pygame.Rect(cornice.left, y, riempita, alt)
        pygame.draw.rect(self.schermo, colore, barra)
        pygame.draw.rect(self.schermo, S.BIANCO, cornice, 2)
        return cornice

    def disegna_hud_lottatore(self, lott, bordo_x, allinea_destra):
        larg = 360
        vita_frac = lott.vita / S.VITA_MAX
        col_vita = S.VERDE if vita_frac > 0.3 else S.ROSSO
        cornice = self.disegna_barra(bordo_x, 24, larg, 26, vita_frac,
                                     col_vita, allinea_destra)
        # stamina (piu' sottile, sotto la vita)
        self.disegna_barra(bordo_x, 54, larg, 10,
                           lott.stamina / S.STAMINA_MAX, S.AZZURRO, allinea_destra)
        # nome
        testo = self.font_piccolo.render(lott.nome, True, S.BIANCO)
        tx = cornice.right - testo.get_width() if allinea_destra else cornice.left
        self.schermo.blit(testo, (tx, 70))
        # pallini round
        for i in range(S.ROUND_PER_VINCERE):
            cx = (cornice.right - 12 - i * 24) if allinea_destra else (cornice.left + 12 + i * 24)
            col = S.GIALLO if i < lott.round_vinti else S.GRIGIO
            pygame.draw.circle(self.schermo, col, (cx, 100), 8)

    def disegna_hud(self):
        self.disegna_hud_lottatore(self.p1, 30, False)
        self.disegna_hud_lottatore(self.p2, S.LARGHEZZA - 30, True)
        secondi = max(0, int(self.tempo_round))
        testo = self.font_grande.render(str(secondi), True, S.BIANCO)
        self.schermo.blit(testo, (S.LARGHEZZA // 2 - testo.get_width() // 2, 18))

    def testo_centrato(self, testo, font, y, colore=S.BIANCO):
        sup = font.render(testo, True, colore)
        self.schermo.blit(sup, (S.LARGHEZZA // 2 - sup.get_width() // 2, y))

    def disegna_menu(self):
        self.disegna_ring()
        self.testo_centrato("KICKBOXING K1", self.font_grande, 70, S.GIALLO)
        self.testo_centrato("2.5D", self.font, 140, S.AZZURRO)

        # selettore modalita'
        opzioni = [("1 GIOCATORE (vs CPU)", self.vs_cpu),
                   ("2 GIOCATORI", not self.vs_cpu)]
        for i, (testo, sel) in enumerate(opzioni):
            col = S.GIALLO if sel else S.GRIGIO
            prefix = "> " if sel else "  "
            self.testo_centrato(prefix + testo, self.font, 200 + i * 40, col)
        self.testo_centrato("FRECCE per scegliere  -  INVIO per iniziare  -  ESC esci",
                            self.font_piccolo, 300, S.BIANCO)

        comandi = [
            "P1:  A/D lati  -  W/S profondita'  -  F jab  G diretto  V calcio basso  B calcio alto  Shift guardia",
            "P2:  Frecce lati/profondita'  -  Num1 jab  Num2 diretto  Num3 calcio basso  Num5 calcio alto  Num0 guardia",
        ]
        for i, riga in enumerate(comandi):
            self.testo_centrato(riga, self.font_piccolo, 380 + i * 32, S.BIANCO)

    def disegna(self):
        if self.stato == MENU:
            self.disegna_menu()
        else:
            self.disegna_scena()
            if self.stato == FINE_ROUND:
                self.testo_centrato(self.messaggio, self.font_grande,
                                    S.ALTEZZA // 2 - 40, S.GIALLO)
            elif self.stato == FINE_PARTITA:
                vincitore = self.p1 if self.p1.round_vinti > self.p2.round_vinti else self.p2
                self.testo_centrato(f"{vincitore.nome} VINCE!",
                                    self.font_grande, S.ALTEZZA // 2 - 60, S.GIALLO)
                self.testo_centrato("Premi INVIO per tornare al menu",
                                    self.font, S.ALTEZZA // 2 + 20)
        pygame.display.flip()

    # --------------------------------------------------------------- loop
    def esegui(self):
        while self.in_esecuzione:
            dt = self.clock.tick(S.FPS) / 1000.0
            self.gestisci_eventi()
            self.aggiorna(dt)
            self.disegna()
        pygame.quit()
        sys.exit()
