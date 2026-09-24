"""Comandi di un lottatore per un singolo frame.

Prodotti da tastiera/gamepad (picchiaduro.input) o dalla CPU (picchiaduro.ia)
e consumati dalla simulazione. Sono stati "tenuti premuti": la simulazione
ricava da sola le pressioni (fronti di salita) confrontando col frame prima,
e bufferizza gli attacchi per qualche frame.

Direzioni in coordinate schermo/mondo (NON relative al lottatore):
  sinistra/destra -> asse x
  su              -> verso il fondo del ring (z cresce)
  giu             -> verso la camera (z cala)
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Comandi:
    sinistra: bool = False
    destra: bool = False
    su: bool = False
    giu: bool = False
    jab: bool = False
    diretto: bool = False
    calcio_basso: bool = False
    calcio_alto: bool = False
    guardia: bool = False
    schivata: bool = False
    speciale: bool = False

    def copia(self) -> "Comandi":
        return Comandi(**{f.name: getattr(self, f.name) for f in fields(self)})

    def unisci(self, altro: "Comandi") -> "Comandi":
        """OR logico di due set di comandi (es. tastiera + gamepad)."""
        return Comandi(**{f.name: getattr(self, f.name) or getattr(altro, f.name)
                          for f in fields(self)})


PULSANTI_ATTACCO = ("jab", "diretto", "calcio_basso", "calcio_alto", "speciale")
