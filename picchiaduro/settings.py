"""Costanti e configurazione globale del gioco."""

import pygame

# --- Finestra ---
LARGHEZZA = 1000
ALTEZZA = 600
FPS = 60
TITOLO = "Picchiaduro K1"

# --- Mondo / fisica ---
SUOLO = ALTEZZA - 80          # coordinata Y del pavimento
GRAVITA = 0.9
FORZA_SALTO = -16
VELOCITA_CAMMINO = 5

# --- Combattenti ---
LARGHEZZA_LOTTATORE = 70
ALTEZZA_LOTTATORE = 160
ALTEZZA_ACCOVACCIATO = 100
VITA_MAX = 100

# --- Round ---
ROUND_PER_VINCERE = 2          # al meglio dei 3
DURATA_ROUND = 60              # secondi
PAUSA_KO = 2.5                 # secondi di pausa prima del round successivo

# --- Attacchi (danno, durata in frame, frame attivi, portata, knockback) ---
ATTACCHI = {
    "pugno": {
        "danno": 8,
        "durata": 18,
        "attivo": (5, 10),     # frame in cui la hitbox fa male
        "portata": 55,
        "altezza_hitbox": 40,
        "offset_y": 40,        # da cima del lottatore
        "knockback": 6,
    },
    "calcio": {
        "danno": 14,
        "durata": 28,
        "attivo": (8, 16),
        "portata": 80,
        "altezza_hitbox": 50,
        "offset_y": 80,
        "knockback": 11,
    },
}

DANNO_PARATA = 0.25            # frazione di danno subita parando
STORDIMENTO_COLPO = 12         # frame di hitstun

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
CIELO = (35, 30, 55)

# --- Schemi di controllo ---
CONTROLLI_P1 = {
    "sinistra": pygame.K_a,
    "destra": pygame.K_d,
    "salta": pygame.K_w,
    "accovaccia": pygame.K_s,
    "pugno": pygame.K_f,
    "calcio": pygame.K_g,
    "parata": pygame.K_h,
}

CONTROLLI_P2 = {
    "sinistra": pygame.K_LEFT,
    "destra": pygame.K_RIGHT,
    "salta": pygame.K_UP,
    "accovaccia": pygame.K_DOWN,
    "pugno": pygame.K_KP1,
    "calcio": pygame.K_KP2,
    "parata": pygame.K_KP3,
}
