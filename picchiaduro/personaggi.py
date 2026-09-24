"""Roster dei lottatori: statistiche di gioco e aspetto.

Le statistiche sono moltiplicatori attorno a 1.0 applicati dalla simulazione:
  velocita    -> velocita' di camminata/schivata
  potenza     -> danno inflitto
  resistenza  -> vita massima
  fiato       -> stamina massima e recupero
  portata     -> portata dei colpi
L'aspetto e' usato dal renderer (colori, proporzioni, capelli) e dai menu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Colore = tuple  # (r, g, b)


@dataclass(frozen=True)
class Personaggio:
    id: str
    nome: str
    soprannome: str
    nazione: str
    stile: str                     # descrizione breve dello stile di combattimento
    # statistiche (moltiplicatori)
    velocita: float
    potenza: float
    resistenza: float
    fiato: float
    portata: float
    # proporzioni del corpo (moltiplicatori di ALTEZZA_BASE / LARGHEZZA_BASE)
    altezza: float
    corporatura: float
    # aspetto
    pelle: Colore
    capelli: Colore
    stile_capelli: str             # 'rasati' | 'corti' | 'cresta' | 'coda' | 'raccolti'
    pantaloncini: Colore
    bordo_pantaloncini: Colore
    guantoni: Colore
    fasce: Colore                  # fasciature di caviglie/polsi
    colore_ui: Colore              # colore d'accento in HUD e menu
    top: Optional[Colore] = None   # top sportivo (None = a torso nudo)
    barba: bool = False
    # palette alternativa per lo scontro speculare (stesso personaggio)
    pantaloncini_alt: Colore = (40, 40, 48)
    bordo_alt: Colore = (230, 230, 235)
    guantoni_alt: Colore = (230, 230, 235)


ROSTER: tuple[Personaggio, ...] = (
    Personaggio(
        id="toro", nome="Marco Ferri", soprannome="IL TORO", nazione="Italia",
        stile="Picchiatore: colpi pesanti, lento ma devastante",
        velocita=0.92, potenza=1.15, resistenza=1.05, fiato=0.95, portata=1.00,
        altezza=1.00, corporatura=1.12,
        pelle=(214, 168, 128), capelli=(48, 34, 26), stile_capelli="rasati",
        pantaloncini=(200, 36, 44), bordo_pantaloncini=(36, 150, 72),
        guantoni=(210, 32, 40), fasce=(240, 240, 240), colore_ui=(226, 56, 64),
        barba=True,
        pantaloncini_alt=(30, 110, 60), bordo_alt=(240, 240, 240), guantoni_alt=(30, 120, 64),
    ),
    Personaggio(
        id="vento", nome="Kenji Arata", soprannome="VENTO", nazione="Giappone",
        stile="Velocista: combinazioni rapide e ottimo fiato",
        velocita=1.15, potenza=0.90, resistenza=0.92, fiato=1.12, portata=0.97,
        altezza=0.96, corporatura=0.92,
        pelle=(232, 196, 160), capelli=(20, 20, 26), stile_capelli="cresta",
        pantaloncini=(240, 240, 244), bordo_pantaloncini=(214, 40, 52),
        guantoni=(40, 96, 214), fasce=(214, 40, 52), colore_ui=(64, 132, 236),
        pantaloncini_alt=(20, 24, 60), bordo_alt=(240, 200, 60), guantoni_alt=(240, 200, 60),
    ),
    Personaggio(
        id="muro", nome="Ivan Volkov", soprannome="IL MURO", nazione="Russia",
        stile="Incassatore: resistenza enorme, pressione costante",
        velocita=0.88, potenza=1.05, resistenza=1.22, fiato=0.92, portata=1.00,
        altezza=1.06, corporatura=1.18,
        pelle=(236, 204, 184), capelli=(200, 170, 110), stile_capelli="corti",
        pantaloncini=(24, 24, 30), bordo_pantaloncini=(230, 180, 60),
        guantoni=(236, 186, 56), fasce=(60, 60, 70), colore_ui=(236, 180, 60),
        pantaloncini_alt=(120, 20, 30), bordo_alt=(240, 240, 240), guantoni_alt=(150, 24, 36),
    ),
    Personaggio(
        id="lama", nome="Luana Costa", soprannome="LAMA", nazione="Brasile",
        stile="Calciatrice: portata lunga, calci fulminei",
        velocita=1.05, potenza=0.97, resistenza=0.95, fiato=1.05, portata=1.10,
        altezza=1.02, corporatura=0.88,
        pelle=(160, 108, 76), capelli=(34, 22, 16), stile_capelli="coda",
        pantaloncini=(250, 210, 40), bordo_pantaloncini=(20, 140, 70),
        guantoni=(30, 160, 80), fasce=(250, 250, 250), colore_ui=(72, 206, 110),
        top=(20, 140, 70),
        pantaloncini_alt=(40, 60, 170), bordo_alt=(250, 210, 40), guantoni_alt=(40, 70, 190),
    ),
)

PER_ID = {p.id: p for p in ROSTER}


def personaggio(id_: str) -> Personaggio:
    return PER_ID[id_]
