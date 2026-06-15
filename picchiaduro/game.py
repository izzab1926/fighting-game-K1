"""Loop principale, stati di gioco e HUD del picchiaduro."""

import sys

import pygame

from . import settings as S
from .fighter import Lottatore

# Stati di gioco
MENU = "menu"
COMBATTIMENTO = "combattimento"
FINE_ROUND = "fine_round"
FINE_PARTITA = "fine_partita"


class Gioco:
    def __init__(self):
        pygame.init()
        self.schermo = pygame.display.set_mode((S.LARGHEZZA, S.ALTEZZA))
        pygame.display.set_caption(S.TITOLO)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 28)
        self.font_grande = pygame.font.SysFont("consolas", 72, bold=True)
        self.font_piccolo = pygame.font.SysFont("consolas", 20)

        self.stato = MENU
        self.in_esecuzione = True
        self.crea_lottatori()
        self.timer_pausa = 0.0
        self.tempo_round = float(S.DURATA_ROUND)
        self.messaggio = ""

    # ------------------------------------------------------------- setup
    def crea_lottatori(self):
        margine = 150
        self.p1 = Lottatore(margine, "Giocatore 1", S.BLU,
                            S.CONTROLLI_P1, guarda_destra=True)
        self.p2 = Lottatore(S.LARGHEZZA - margine - S.LARGHEZZA_LOTTATORE,
                            "Giocatore 2", S.ROSSO,
                            S.CONTROLLI_P2, guarda_destra=False)

    def nuovo_round(self):
        margine = 150
        self.p1.reset_round(margine, True)
        self.p2.reset_round(S.LARGHEZZA - margine - S.LARGHEZZA_LOTTATORE, False)
        self.tempo_round = float(S.DURATA_ROUND)
        self.stato = COMBATTIMENTO

    def nuova_partita(self):
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
                    self.in_esecuzione = False
                elif ev.key == pygame.K_RETURN:
                    if self.stato == MENU:
                        self.nuova_partita()
                    elif self.stato == FINE_PARTITA:
                        self.stato = MENU

    # ------------------------------------------------------------ logica
    def risolvi_colpi(self, attaccante, difensore):
        if attaccante.attacco is None or attaccante.colpo_a_segno:
            return
        hb = attaccante.hitbox_attacco()
        if hb is None:
            return
        if hb.colliderect(difensore.rect):
            dati = S.ATTACCHI[attaccante.attacco]
            direzione = 1 if attaccante.guarda_destra else -1
            difensore.subisci_colpo(dati["danno"], dati["knockback"], direzione)
            attaccante.colpo_a_segno = True

    def aggiorna(self, dt):
        if self.stato == COMBATTIMENTO:
            tasti = pygame.key.get_pressed()
            self.p1.gestisci_input(tasti)
            self.p2.gestisci_input(tasti)

            self.p1.aggiorna(self.p2)
            self.p2.aggiorna(self.p1)

            # impedisci la sovrapposizione dei corpi
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
        ra, rb = a.rect, b.rect
        if ra.colliderect(rb):
            sovrapp = min(ra.right, rb.right) - max(ra.left, rb.left)
            meta = sovrapp / 2 + 1
            if a.centro_x < b.centro_x:
                a.x -= meta
                b.x += meta
            else:
                a.x += meta
                b.x -= meta
            a.x = max(0, min(S.LARGHEZZA - a.larghezza, a.x))
            b.x = max(0, min(S.LARGHEZZA - b.larghezza, b.x))

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
            # tempo scaduto o doppio KO: vince chi ha più vita
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
    def disegna_scena(self):
        self.schermo.fill(S.CIELO)
        # pavimento
        pygame.draw.rect(self.schermo, S.GRIGIO_SCURO,
                        (0, S.SUOLO, S.LARGHEZZA, S.ALTEZZA - S.SUOLO))
        pygame.draw.line(self.schermo, S.GRIGIO,
                        (0, S.SUOLO), (S.LARGHEZZA, S.SUOLO), 3)
        self.p1.disegna(self.schermo)
        self.p2.disegna(self.schermo)
        self.disegna_hud()

    def disegna_barra_vita(self, lottatore, x, allinea_destra):
        larghezza = 380
        altezza = 26
        y = 24
        if allinea_destra:
            x = x - larghezza
        cornice = pygame.Rect(x, y, larghezza, altezza)
        pygame.draw.rect(self.schermo, S.GRIGIO_SCURO, cornice)

        frazione = lottatore.vita / S.VITA_MAX
        riempita = int(larghezza * frazione)
        colore = S.VERDE if frazione > 0.3 else S.ROSSO
        if allinea_destra:
            barra = pygame.Rect(cornice.right - riempita, y, riempita, altezza)
        else:
            barra = pygame.Rect(x, y, riempita, altezza)
        pygame.draw.rect(self.schermo, colore, barra)
        pygame.draw.rect(self.schermo, S.BIANCO, cornice, 2)

        # nome
        testo = self.font_piccolo.render(lottatore.nome, True, S.BIANCO)
        tx = cornice.right - testo.get_width() if allinea_destra else x
        self.schermo.blit(testo, (tx, y + altezza + 4))

        # indicatori round vinti
        for i in range(S.ROUND_PER_VINCERE):
            cx = (cornice.right - 12 - i * 24) if allinea_destra else (x + 12 + i * 24)
            colore_pallino = S.GIALLO if i < lottatore.round_vinti else S.GRIGIO
            pygame.draw.circle(self.schermo, colore_pallino, (cx, y + altezza + 34), 8)

    def disegna_hud(self):
        self.disegna_barra_vita(self.p1, 30, allinea_destra=False)
        self.disegna_barra_vita(self.p2, S.LARGHEZZA - 30, allinea_destra=True)

        # timer al centro
        secondi = max(0, int(self.tempo_round))
        testo = self.font_grande.render(str(secondi), True, S.BIANCO)
        self.schermo.blit(testo, (S.LARGHEZZA // 2 - testo.get_width() // 2, 16))

    def testo_centrato(self, testo, font, y, colore=S.BIANCO):
        sup = font.render(testo, True, colore)
        self.schermo.blit(sup, (S.LARGHEZZA // 2 - sup.get_width() // 2, y))

    def disegna_menu(self):
        self.schermo.fill(S.CIELO)
        self.testo_centrato("PICCHIADURO K1", self.font_grande, 120, S.GIALLO)
        self.testo_centrato("Premi INVIO per iniziare", self.font, 260)
        self.testo_centrato("ESC per uscire", self.font_piccolo, 300, S.GRIGIO)

        comandi = [
            "Giocatore 1:  A/D muovi  -  W salta  -  S accovaccia  -  F pugno  G calcio  H parata",
            "Giocatore 2:  </> muovi  -  UP salta  -  DOWN accovaccia  -  Num1 pugno  Num2 calcio  Num3 parata",
        ]
        for i, riga in enumerate(comandi):
            self.testo_centrato(riga, self.font_piccolo, 400 + i * 34, S.BIANCO)

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
                                    self.font, S.ALTEZZA // 2 + 30)
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
