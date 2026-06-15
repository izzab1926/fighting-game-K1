"""Genera una GIF di anteprima del picchiaduro in modalita' headless.

Guida un combattimento simulato (IA molto semplice) e cattura i frame.
Uso:  SDL_VIDEODRIVER=dummy python tools/genera_anteprima.py
"""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image

from picchiaduro.game import Gioco, COMBATTIMENTO, FINE_ROUND, FINE_PARTITA
import picchiaduro.settings as S

random.seed(7)
SCALA = 0.55  # riduci dimensione GIF


def ia(lott, avv):
    """Controllo automatico molto semplice per la demo."""
    if not lott.puo_agire():
        # ogni tanto para quando l'avversario attacca
        lott.sta_parando = avv.attacco is not None and random.random() < 0.5
        return
    lott.sta_parando = False
    dist = abs(lott.centro_x - avv.centro_x)
    portata = S.ATTACCHI["calcio"]["portata"] + lott.larghezza

    if dist > portata:
        # avvicinati
        lott.vx = S.VELOCITA_CAMMINO if avv.centro_x > lott.centro_x else -S.VELOCITA_CAMMINO
        if random.random() < 0.02 and lott.a_terra:
            lott.vy = S.FORZA_SALTO
            lott.a_terra = False
    else:
        r = random.random()
        if r < 0.10:
            lott.inizia_attacco("calcio")
        elif r < 0.28:
            lott.inizia_attacco("pugno")
        elif r < 0.34 and lott.a_terra:
            lott.vy = S.FORZA_SALTO
            lott.a_terra = False
        elif r < 0.45:
            lott.sta_parando = True


def cattura(gioco):
    raw = pygame.image.tostring(gioco.schermo, "RGB")
    img = Image.frombytes("RGB", (S.LARGHEZZA, S.ALTEZZA), raw)
    return img.resize((int(S.LARGHEZZA * SCALA), int(S.ALTEZZA * SCALA)))


def main():
    gioco = Gioco()
    frames = []

    # --- menu (qualche frame) ---
    gioco.disegna_menu()
    pygame.display.flip()
    for _ in range(18):
        frames.append(cattura(gioco))

    # --- combattimento ---
    gioco.nuova_partita()
    frame_totali = 0
    max_frame = 60 * 22  # massimo ~22s simulati
    while gioco.stato != FINE_PARTITA and frame_totali < max_frame:
        if gioco.stato == COMBATTIMENTO:
            ia(gioco.p1, gioco.p2)
            ia(gioco.p2, gioco.p1)
            gioco.p1.aggiorna(gioco.p2)
            gioco.p2.aggiorna(gioco.p1)
            gioco.separa(gioco.p1, gioco.p2)
            gioco.risolvi_colpi(gioco.p1, gioco.p2)
            gioco.risolvi_colpi(gioco.p2, gioco.p1)
            gioco.tempo_round -= 1.0 / S.FPS
            gioco.controlla_fine_round()
        elif gioco.stato == FINE_ROUND:
            gioco.timer_pausa -= 1.0 / S.FPS
            if gioco.timer_pausa <= 0:
                if (gioco.p1.round_vinti >= S.ROUND_PER_VINCERE or
                        gioco.p2.round_vinti >= S.ROUND_PER_VINCERE):
                    gioco.stato = FINE_PARTITA
                else:
                    gioco.nuovo_round()

        gioco.disegna()
        frame_totali += 1
        if frame_totali % 3 == 0:       # campiona 1 frame su 3 (~20 fps)
            frames.append(cattura(gioco))

    # --- schermata finale (qualche frame) ---
    for _ in range(24):
        gioco.disegna()
        frames.append(cattura(gioco))

    out = "anteprima.gif"
    frames[0].save(
        out, save_all=True, append_images=frames[1:],
        duration=50, loop=0, optimize=True,
    )
    print(f"GIF salvata: {out} ({len(frames)} frame)")
    pygame.quit()


if __name__ == "__main__":
    main()
