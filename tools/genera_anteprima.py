"""Genera una GIF di anteprima del kickboxing 2.5D in modalita' headless.

Fa combattere due CPU e cattura i frame.
Uso:  SDL_VIDEODRIVER=dummy PYTHONPATH=. python tools/genera_anteprima.py
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image

from picchiaduro.game import (Gioco, COMBATTIMENTO, FINE_ROUND, FINE_PARTITA)
from picchiaduro.ia import IAKickboxer
import picchiaduro.settings as S

SCALA = 0.55  # riduci dimensione GIF


def cattura(gioco):
    raw = pygame.image.tostring(gioco.schermo, "RGB")
    img = Image.frombytes("RGB", (S.LARGHEZZA, S.ALTEZZA), raw)
    return img.resize((int(S.LARGHEZZA * SCALA), int(S.ALTEZZA * SCALA)))


def main():
    gioco = Gioco()
    gioco.vs_cpu = True
    frames = []

    # --- menu ---
    gioco.disegna_menu()
    pygame.display.flip()
    for _ in range(16):
        frames.append(cattura(gioco))

    # --- combattimento: due CPU una contro l'altra ---
    gioco.nuova_partita()
    ia1 = IAKickboxer(difficolta="media", seme=1)
    ia2 = IAKickboxer(difficolta="media", seme=2)

    frame_totali = 0
    max_frame = 60 * 24
    while gioco.stato != FINE_PARTITA and frame_totali < max_frame:
        if gioco.stato == COMBATTIMENTO:
            ia1.agisci(gioco.p1, gioco.p2)
            ia2.agisci(gioco.p2, gioco.p1)
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
        if frame_totali % 3 == 0:
            frames.append(cattura(gioco))

    # --- schermata finale ---
    for _ in range(22):
        gioco.disegna()
        frames.append(cattura(gioco))

    out = "anteprima.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=50, loop=0, optimize=True)
    print(f"GIF salvata: {out} ({len(frames)} frame)")
    pygame.quit()


if __name__ == "__main__":
    main()
