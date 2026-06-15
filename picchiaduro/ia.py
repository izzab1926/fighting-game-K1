"""Avversario controllato dalla CPU per la modalita' 1 giocatore.

Strategia da kickboxer: allinearsi in profondita', gestire la distanza,
colpire quando e' a portata, alzare la guardia quando l'avversario attacca,
e arretrare ogni tanto per recuperare fiato.
"""

import random

from . import settings as S


class IAKickboxer:
    """Controlla un Lottatore reagendo allo stato dell'avversario."""

    def __init__(self, difficolta="media", seme=None):
        # aggressivita' e prontezza dei riflessi per difficolta'
        livelli = {
            "facile": (0.45, 0.30, 0.10),
            "media": (0.65, 0.55, 0.06),
            "difficile": (0.85, 0.80, 0.03),
        }
        self.aggressivita, self.riflessi, self.errore = livelli.get(
            difficolta, livelli["media"])
        self.rng = random.Random(seme)
        self.cooldown = 0

    def agisci(self, io, avversario):
        """Imposta movimento/azioni del lottatore 'io' contro 'avversario'."""
        if self.cooldown > 0:
            self.cooldown -= 1

        if not io.puo_agire():
            # reagisci all'attacco alzando la guardia
            io.sta_parando = (avversario.attacco is not None
                              and self.rng.random() < self.riflessi)
            return

        dist_x = abs(io.x - avversario.x)
        dist_z = io.z - avversario.z
        segno_x = 1 if avversario.x > io.x else -1

        io.vx = io.vz = 0
        io.sta_parando = False

        # 1) allineati in profondita'
        if abs(dist_z) > S.TOLLERANZA_PROFONDITA * 0.6:
            io.vz = -S.VELOCITA_Z if dist_z > 0 else S.VELOCITA_Z

        # 2) guardia reattiva se l'avversario sta colpendo da vicino
        if (avversario.attacco_attivo() and dist_x < 130
                and self.rng.random() < self.riflessi):
            io.sta_parando = True
            return

        # raggio reale dei colpi (dal centro): mezza larghezza + portata
        raggio_calcio = io.meta_larghezza + S.ATTACCHI["calcio_alto"]["portata"]
        raggio_pugno = io.meta_larghezza + S.ATTACCHI["diretto"]["portata"]

        # 3) gestione della distanza
        if dist_x > raggio_calcio * 0.92:
            io.vx = segno_x * S.VELOCITA_X          # avvicinati per entrare in portata
        elif dist_x < raggio_pugno * 0.45:
            # troppo vicino: a volte arretra per respirare
            if io.stamina < 30 or self.rng.random() < 0.3:
                io.vx = -segno_x * S.VELOCITA_X
        else:
            # 4) a portata: attacca se ha fiato e non e' in cooldown
            if (self.cooldown == 0 and io.stamina > 20
                    and self.rng.random() < self.aggressivita):
                self._scegli_colpo(io, dist_x, raggio_pugno)
                self.cooldown = self.rng.randint(8, 22)

    def _scegli_colpo(self, io, dist_x, raggio_pugno):
        if dist_x <= raggio_pugno:
            scelta = self.rng.choices(
                ["jab", "diretto", "calcio_basso"], weights=[3, 3, 2])[0]
        else:
            scelta = self.rng.choices(
                ["calcio_alto", "calcio_basso"], weights=[3, 2])[0]
        io.inizia_attacco(scelta)
