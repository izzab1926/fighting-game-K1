"""Regole di gioco e costanti della simulazione.

Tempi in frame a 60 FPS, distanze in unita' del mondo (vedi costanti.py).
Le funzioni geometriche accettano qualunque oggetto con gli attributi
pubblici di `Lottatore` (x, z, hw, guarda_destra, personaggio,
altezza_mondo): cosi' le possono usare anche IA, renderer e test.
"""

from __future__ import annotations

from typing import Optional

from .. import costanti as C
from .mosse import MOSSE

# ---- ring e posizioni
Z_MIN = 30.0
Z_MAX = C.RING_PROFONDITA - 30.0
Z_INIZIALE = C.RING_PROFONDITA / 2
DISTANZA_INIZIALE = 380.0         # distanza tra i centri a inizio round
TOLLERANZA_Z = 55.0               # |dz| massimo perche' un colpo tocchi
SEPARAZIONE_Z = 50.0              # sotto questo |dz| i corpi non si compenetrano

# ---- movimento
VELOCITA_CAMMINO = 4.2            # unita'/frame in avanti con velocita' 1.0
FATTORE_INDIETRO = 0.8
VELOCITA_PROFONDITA = 3.0         # unita'/frame in z con velocita' 1.0
FATTORE_DIAGONALE = 0.85          # x e z insieme
FATTORE_AFFANNATO = 0.8
INTERVALLO_PASSO = 18             # evento Passo quando frame_stato % 18 == FASE_PASSO
FASE_PASSO = 9

# ---- input
BUFFER_INPUT = 6                  # frame di validita' di una pressione
FINESTRA_CANCEL = 8               # frame di recupero in cui si puo' concatenare
LUNGHEZZA_MAX_CATENA = 4          # mosse al massimo in una catena di cancel
RIPETIZIONI_MAX_CATENA = 2        # la stessa mossa al massimo 2 volte per catena

# ---- stamina
SOGLIA_AFFANNO = 0.2              # frazione di stamina_max sotto cui si e' affannati
RITARDO_RIGENERAZIONE = 30        # frame senza attaccare prima di recuperare fiato
RIGENERAZIONE_STAMINA = 0.8       # per frame, moltiplicata per `fiato`
FATTORE_RIGENERAZIONE_PARATA = 0.5
DANNO_STANCO = 0.6                # moltiplicatore del danno di una mossa "stanca"
RECUPERO_STANCO = 6               # frame di recupero in piu' di una mossa "stanca"
COSTO_PARATA_BASE = 1.5           # stamina consumata parando: base + k * danno mossa
COSTO_PARATA_DANNO = 0.5
DURATA_GUARDIA_ROTTA = 45
STAMINA_DOPO_GUARDIA_ROTTA = 0.3  # frazione minima di stamina al termine

# ---- parata, contro, combo
DANNO_PARATA = 0.15               # danno residuo di un colpo parato
DANNO_PARATA_BASSO = 0.30         # ... per il calcio basso
FATTORE_SPINTA_PARATA = 1.0
VITA_MINIMA_PARATA = 1.0          # un colpo parato non puo' mandare KO
MOLTIPLICATORE_CONTRO = 1.3
HITSTUN_CONTRO = 6
HITSTOP_CONTRO = 3
SCALING_COMBO_PASSO = 0.1
SCALING_COMBO_MIN = 0.5

# ---- spinte
DECADIMENTO_SPINTA = 0.75         # la spinta e' una velocita' che decade (somma = spinta)
DECADIMENTO_SPINTA_CADUTA = 0.86  # ... piu' lunga e morbida su atterramento e KO
FATTORE_SPINTA_ATTERRAMENTO = 1.6

# ---- atterramento, rialzo, KO
DURATA_CADUTA = 30                # frame di caduta (anche per lo stato 'ko')
DURATA_A_TERRA = 70
DURATA_ATTERRATO = DURATA_CADUTA + DURATA_A_TERRA
PRIMO_CONTEGGIO = 10              # ConteggioArbitro a frame 10, 35, 60, 85 di 'atterrato'
INTERVALLO_CONTEGGIO = 25
DURATA_RIALZO = 40
DISTANZA_RIALZO = 250.0           # distanza minima tra i centri ripristinata
VELOCITA_SEPARAZIONE = 7.0        # unita'/frame con cui l'arbitro separa
HITSTOP_KO = 18                   # congelamento sul colpo del KO (prima del ralenti)

# ---- schivata
DURATA_SCHIVATA_LATERALE = 22
DISTANZA_SCHIVATA_LATERALE = 110.0
INVULNERABILE_LATERALE = (3, 14)  # frame_stato compresi
DURATA_SCHIVATA_INDIETRO = 20
DISTANZA_SCHIVATA_INDIETRO = 90.0
INVULNERABILE_INDIETRO = (2, 10)
FRAZIONE_MOTO_SCHIVATA = 0.72     # parte della durata in cui avviene lo spostamento
COSTO_SCHIVATA = 8.0              # senza stamina sufficiente la schivata e' "stanca":
DISTANZA_SCHIVATA_STANCA = 0.6    # ... niente invulnerabilita' e distanza x0.6
ENERGIA_SCHIVATA = 8.0

# ---- energia speciale
ENERGIA_DANNO_INFLITTO = 1.2
ENERGIA_DANNO_SUBITO = 0.8

# ---- fasi dell'incontro
DURATA_PRESENTAZIONE = 110
DURATA_FINE_ROUND = 200
RALLENTATORE_KO = 0.35
DURATA_RALLENTATORE = 60          # tick di ralenti dopo il congelamento del KO
TICK_POSE_PUNTI = 45              # vittoria/sconfitta dopo una decisione ai punti
MAX_ROUND = 5                     # oltre: decide il danno totale inflitto (poi P1)

# ---- effetti
FORZA_RIFERIMENTO = 26.0          # danno che corrisponde a forza 1.0
FORZA_PARATA = 0.5                # scala della forza su un colpo parato


# ---- funzioni

def limiti_x(hw: float) -> tuple:
    """Intervallo ammesso per il centro di un corpo largo 2*hw."""
    return (C.MARGINE_CORDE + hw, C.RING_LARGHEZZA - C.MARGINE_CORDE - hw)


def x_iniziale(indice: int) -> float:
    centro = C.RING_LARGHEZZA / 2
    return centro - DISTANZA_INIZIALE / 2 if indice == 0 else centro + DISTANZA_INIZIALE / 2


def verso(lottatore) -> int:
    """+1 se guarda a destra, -1 altrimenti."""
    return 1 if lottatore.guarda_destra else -1


def fronte(lottatore) -> float:
    """x del fronte del corpo (lato dell'orientamento)."""
    return lottatore.x + verso(lottatore) * lottatore.hw


def portata_effettiva(lottatore, nome_mossa: str) -> float:
    return MOSSE[nome_mossa].portata * lottatore.personaggio.portata


def intervallo_colpo(lottatore, nome_mossa: str) -> tuple:
    """(x_min, x_max) coperto dal colpo: dal fronte a fronte + portata."""
    f = fronte(lottatore)
    punta = f + verso(lottatore) * portata_effettiva(lottatore, nome_mossa)
    return (min(f, punta), max(f, punta))


def colpo_raggiunge(att, dif, nome_mossa: str,
                    x_dif: Optional[float] = None, z_dif: Optional[float] = None) -> bool:
    """True se la mossa di `att` tocca `dif` (eventualmente in una posizione ipotetica)."""
    xd = dif.x if x_dif is None else x_dif
    zd = dif.z if z_dif is None else z_dif
    if abs(att.z - zd) > TOLLERANZA_Z:
        return False
    lo, hi = intervallo_colpo(att, nome_mossa)
    return lo <= xd + dif.hw and hi >= xd - dif.hw


def distanza_fronti(a, b) -> float:
    """Spazio libero in x tra i due corpi (negativo se si sovrappongono)."""
    return abs(b.x - a.x) - a.hw - b.hw


def davanti(a, b) -> bool:
    """True se b sta dal lato verso cui guarda a."""
    dx = b.x - a.x
    return dx * verso(a) >= 0


def punto_impatto(att, dif, nome_mossa: str) -> tuple:
    """(x, z, h) del contatto: superficie vicina del difensore, dentro la portata."""
    s = verso(att)
    x = dif.x - s * dif.hw * 0.75
    lo, hi = intervallo_colpo(att, nome_mossa)
    x = min(max(x, lo), hi)
    z = (att.z + dif.z) / 2
    h = MOSSE[nome_mossa].altezza_colpo * att.altezza_mondo
    return (x, z, h)


def scaling_combo(numero: int) -> float:
    """Moltiplicatore del danno per il colpo `numero` di una combo (1 = primo)."""
    return max(SCALING_COMBO_MIN, 1.0 - SCALING_COMBO_PASSO * (numero - 1))


def fattore_parata(nome_mossa: str) -> float:
    return DANNO_PARATA_BASSO if nome_mossa == "calcio_basso" else DANNO_PARATA


def costo_parata(nome_mossa: str) -> float:
    return COSTO_PARATA_BASE + COSTO_PARATA_DANNO * MOSSE[nome_mossa].danno


def forza_da_danno(danno: float) -> float:
    return max(0.05, min(1.0, danno / FORZA_RIFERIMENTO))


def percentuale_vita(lottatore) -> float:
    return lottatore.vita / lottatore.vita_max if lottatore.vita_max > 0 else 0.0
