"""Tabella delle mosse di kickboxing (dati di frame).

Contratto condiviso:
  - la simulazione usa tutti i campi;
  - il renderer usa `portata` e `altezza_colpo` per far arrivare pugno/piede
    esattamente sul punto d'impatto durante la fase attiva;
  - l'IA usa portata/avvio/livello per decidere.
I VALORI si possono ribilanciare; i NOMI dei campi e delle mosse no.

Tutti i tempi sono in frame a 60 FPS.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mossa:
    nome: str
    etichetta: str            # nome mostrato a schermo
    arto: str                 # 'pugno_avanti' | 'pugno_dietro' | 'gamba_dietro' | 'gamba_avanti'
    livello: str              # 'alto' | 'medio' | 'basso'
    danno: float
    avvio: int                # frame prima che il colpo diventi attivo
    attivo: int               # frame in cui il colpo puo' toccare
    recupero: int             # frame dopo la fase attiva
    portata: float            # unita' mondo oltre il fronte del corpo
    altezza_colpo: float      # altezza del punto d'impatto, frazione dell'altezza del lottatore
    stamina: float            # costo in fiato
    stordimento: int          # hitstun inflitto a segno
    stordimento_parata: int   # blockstun inflitto se parato
    spinta: float             # arretramento del difensore (unita' mondo)
    hitstop: int              # frame di congelamento all'impatto
    atterra: str              # 'mai' | 'contro' (solo d'incontro) | 'sempre'
    avanzamento: float = 0.0  # spostamento in avanti dell'attaccante durante la mossa
    cancella_in: tuple = ()   # mosse in cui si puo' concatenare a segno/parato
    ravvicinata: bool = False # variante automatica a distanza corta
    costo_super: float = 0.0  # energia speciale richiesta

    @property
    def durata(self) -> int:
        return self.avvio + self.attivo + self.recupero


MOSSE: dict[str, Mossa] = {m.nome: m for m in (
    Mossa("jab", "JAB", "pugno_avanti", "alto",
          danno=5, avvio=5, attivo=3, recupero=9, portata=95, altezza_colpo=0.84,
          stamina=6, stordimento=14, stordimento_parata=9, spinta=18, hitstop=5,
          atterra="mai", avanzamento=10,
          cancella_in=("jab", "diretto", "calcio_basso", "calcio_alto")),
    Mossa("diretto", "DIRETTO", "pugno_dietro", "alto",
          danno=9, avvio=8, attivo=3, recupero=14, portata=110, altezza_colpo=0.84,
          stamina=10, stordimento=18, stordimento_parata=12, spinta=30, hitstop=7,
          atterra="mai", avanzamento=18,
          cancella_in=("gancio", "calcio_basso", "calcio_alto")),
    Mossa("gancio", "GANCIO", "pugno_avanti", "alto",
          danno=12, avvio=9, attivo=3, recupero=16, portata=60, altezza_colpo=0.82,
          stamina=12, stordimento=20, stordimento_parata=13, spinta=34, hitstop=8,
          atterra="contro", avanzamento=8, ravvicinata=True,
          cancella_in=("calcio_basso", "calcio_alto")),
    Mossa("calcio_basso", "LOW KICK", "gamba_dietro", "basso",
          danno=11, avvio=11, attivo=4, recupero=18, portata=105, altezza_colpo=0.28,
          stamina=13, stordimento=19, stordimento_parata=13, spinta=26, hitstop=8,
          atterra="mai", avanzamento=10),
    Mossa("ginocchiata", "GINOCCHIATA", "gamba_dietro", "medio",
          danno=13, avvio=10, attivo=4, recupero=17, portata=45, altezza_colpo=0.55,
          stamina=13, stordimento=22, stordimento_parata=14, spinta=40, hitstop=9,
          atterra="contro", avanzamento=14, ravvicinata=True),
    Mossa("calcio_alto", "HIGH KICK", "gamba_dietro", "alto",
          danno=17, avvio=16, attivo=4, recupero=24, portata=140, altezza_colpo=0.86,
          stamina=20, stordimento=26, stordimento_parata=16, spinta=55, hitstop=11,
          atterra="contro", avanzamento=12),
    Mossa("calcio_girato", "CALCIO GIRATO", "gamba_dietro", "medio",
          danno=26, avvio=18, attivo=5, recupero=26, portata=150, altezza_colpo=0.62,
          stamina=10, stordimento=34, stordimento_parata=20, spinta=90, hitstop=15,
          atterra="sempre", avanzamento=30, costo_super=100.0),
)}

# pulsante -> mossa (a distanza normale); la versione ravvicinata sostituisce
# automaticamente la mossa quando i lottatori sono a distanza corta.
MOSSA_DA_PULSANTE = {
    "jab": "jab",
    "diretto": "diretto",
    "calcio_basso": "calcio_basso",
    "calcio_alto": "calcio_alto",
    "speciale": "calcio_girato",
}
VARIANTE_RAVVICINATA = {
    "diretto": "gancio",
    "calcio_basso": "ginocchiata",
}
DISTANZA_RAVVICINATA = 95.0   # distanza tra i fronti dei corpi sotto cui scatta la variante
