"""Eventi emessi dalla simulazione a ogni tick.

Sono il contratto tra la logica (picchiaduro.sim) e tutto cio' che reagisce:
effetti visivi, audio, HUD, camera, statistiche. La simulazione non sa nulla
di rendering: pubblica eventi, gli altri sistemi li consumano.

Indici dei lottatori: 0 = Giocatore 1 (sinistra), 1 = Giocatore 2.
Coordinate x, z, h: mondo (vedi costanti.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Evento:
    """Base di tutti gli eventi."""


@dataclass(frozen=True)
class AttaccoIniziato(Evento):
    indice: int
    mossa: str                 # nome in sim.mosse.MOSSE


@dataclass(frozen=True)
class ColpoASegno(Evento):
    """Un colpo ha raggiunto il difensore (a segno o parato)."""
    attaccante: int
    difensore: int
    mossa: str
    danno: float               # danno effettivamente sottratto alla vita
    parato: bool
    contro: bool               # colpo d'incontro (difensore in avvio/recupero)
    combo: int                 # numero del colpo nella combo corrente (1 = primo)
    livello: str               # 'alto' | 'medio' | 'basso'
    forza: float               # 0..1, intensita' per effetti/suoni
    x: float                   # punto d'impatto nel mondo
    z: float
    h: float


@dataclass(frozen=True)
class Mancato(Evento):
    """La finestra attiva di un colpo si e' chiusa senza toccare nulla."""
    indice: int
    mossa: str


@dataclass(frozen=True)
class Schivata(Evento):
    indice: int
    tipo: str                  # 'laterale' (in profondita') | 'indietro'
    riuscita: bool = False     # True se ha evitato un colpo attivo


@dataclass(frozen=True)
class GuardiaRotta(Evento):
    indice: int


@dataclass(frozen=True)
class Atterramento(Evento):
    """Knockdown: il lottatore finisce al tappeto (non ancora KO)."""
    indice: int
    numero: int                # atterramenti subiti in questo round


@dataclass(frozen=True)
class ConteggioArbitro(Evento):
    """Conteggio dell'arbitro durante un atterramento (1, 2, 3...)."""
    indice: int
    numero: int


@dataclass(frozen=True)
class Rialzo(Evento):
    indice: int


@dataclass(frozen=True)
class KO(Evento):
    indice: int                # chi e' andato KO
    tecnico: bool = False      # True se KO tecnico (3 atterramenti)


@dataclass(frozen=True)
class SuperPronto(Evento):
    """La barra speciale del lottatore si e' appena riempita."""
    indice: int


@dataclass(frozen=True)
class InizioRound(Evento):
    numero: int                # 1, 2, 3


@dataclass(frozen=True)
class Via(Evento):
    """Fine dell'introduzione: il combattimento comincia ("FIGHT!")."""
    numero: int


@dataclass(frozen=True)
class FineRound(Evento):
    numero: int
    vincitore: Optional[int]   # None = pareggio
    motivo: str                # 'ko' | 'tko' | 'punti' | 'pareggio'


@dataclass(frozen=True)
class FinePartita(Evento):
    vincitore: int


@dataclass(frozen=True)
class Passo(Evento):
    """Appoggio di un piede (per suoni di passi), opzionale."""
    indice: int
