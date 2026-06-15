"""Costanti e configurazione globale del kickboxing 2.5D."""

import pygame

# --- Finestra ---
LARGHEZZA = 1000
ALTEZZA = 600
FPS = 60
TITOLO = "Kickboxing K1 - 2.5D"

# --- Ring (coordinate del mondo) ---
RING_LARGHEZZA = 900          # ampiezza giocabile lungo X (mondo)
RING_PROFONDITA = 260         # profondita' del ring lungo Z (mondo)

# --- Proiezione 2.5D (mappa mondo -> schermo) ---
# Pavimento disegnato come trapezio: bordo vicino largo in basso,
# bordo lontano stretto e piu' in alto.
NEAR_Y = ALTEZZA - 70         # Y schermo del bordo vicino (davanti)
FAR_Y = int(ALTEZZA * 0.42)   # Y schermo del bordo lontano (in fondo)
NEAR_MARGINE = 30             # margine X schermo del bordo vicino
FAR_MARGINE = int(LARGHEZZA * 0.27)  # margine X schermo del bordo lontano
SCALA_VICINO = 1.05           # scala lottatore in primo piano
SCALA_LONTANO = 0.60          # scala lottatore in fondo

# --- Movimento (kickboxing: footwork, niente salti) ---
VELOCITA_X = 4.2
VELOCITA_Z = 3.0
TOLLERANZA_PROFONDITA = 46    # quanto devono essere allineati in Z per colpire

# --- Combattenti ---
LARGHEZZA_LOTTATORE = 64      # unita' mondo (a scala 1)
ALTEZZA_LOTTATORE = 168
VITA_MAX = 100
STAMINA_MAX = 100
STAMINA_RIGEN = 0.45          # recupero fiato per frame
STAMINA_MIN_COLPO = 6         # fiato minimo per tirare un colpo

# --- Round ---
ROUND_PER_VINCERE = 2         # al meglio dei 3
DURATA_ROUND = 60             # secondi
PAUSA_KO = 2.5                # secondi di pausa prima del round successivo

# --- Colpi di kickboxing ---
# bersaglio: "alto" (pugni/calcio alto) o "basso" (calcio basso)
ATTACCHI = {
    "jab": {
        "danno": 6, "durata": 14, "attivo": (3, 6), "portata": 72,
        "knockback": 4, "stamina": 8, "stordimento": 9,
        "bersaglio": "alto", "altezza": 38, "offset_y": 0.30,
    },
    "diretto": {
        "danno": 11, "durata": 22, "attivo": (5, 9), "portata": 88,
        "knockback": 7, "stamina": 15, "stordimento": 13,
        "bersaglio": "alto", "altezza": 42, "offset_y": 0.32,
    },
    "calcio_basso": {
        "danno": 13, "durata": 26, "attivo": (7, 12), "portata": 96,
        "knockback": 6, "stamina": 18, "stordimento": 15,
        "bersaglio": "basso", "altezza": 40, "offset_y": 0.78,
    },
    "calcio_alto": {
        "danno": 18, "durata": 32, "attivo": (9, 15), "portata": 112,
        "knockback": 13, "stamina": 26, "stordimento": 20,
        "bersaglio": "alto", "altezza": 50, "offset_y": 0.18,
    },
}

DANNO_PARATA = 0.22           # frazione di danno subita in guardia
KB_PARATA = 0.35             # frazione di knockback in guardia

# --- Colori ---
NERO = (12, 12, 16)
BIANCO = (240, 240, 245)
GRIGIO = (90, 90, 100)
GRIGIO_SCURO = (40, 40, 48)
ROSSO = (220, 60, 60)
VERDE = (70, 200, 90)
GIALLO = (240, 210, 70)
BLU = (70, 130, 220)
ARANCIO = (235, 140, 50)
AZZURRO = (90, 200, 230)
RING = (60, 50, 80)
RING_BORDO = (200, 70, 90)
CIELO = (24, 20, 38)
OMBRA = (0, 0, 0)

# --- Schemi di controllo ---
# Movimento: sinistra/destra su X, avanti/indietro in profondita' (Z).
CONTROLLI_P1 = {
    "sinistra": pygame.K_a,
    "destra": pygame.K_d,
    "avanti": pygame.K_s,        # verso la camera (Z-)
    "indietro": pygame.K_w,      # verso il fondo (Z+)
    "jab": pygame.K_f,
    "diretto": pygame.K_g,
    "calcio_basso": pygame.K_v,
    "calcio_alto": pygame.K_b,
    "guardia": pygame.K_LSHIFT,
}

CONTROLLI_P2 = {
    "sinistra": pygame.K_LEFT,
    "destra": pygame.K_RIGHT,
    "avanti": pygame.K_DOWN,
    "indietro": pygame.K_UP,
    "jab": pygame.K_KP1,
    "diretto": pygame.K_KP2,
    "calcio_basso": pygame.K_KP3,
    "calcio_alto": pygame.K_KP5,
    "guardia": pygame.K_KP0,
}
