# Kickboxing K1 — 2.5D 🥊

Un picchiaduro **kickboxing 2.5D** scritto in **Python** con
[pygame](https://www.pygame.org/). Grafica a forme geometriche con
prospettiva: nessun asset esterno richiesto, gira ovunque ci sia Python + pygame.

## Caratteristiche

- 🥋 **Kickboxing**: jab, diretto, calcio basso e calcio alto + guardia
- 🌀 **2.5D**: il ring è disegnato in prospettiva e i lottatori si muovono
  anche **in profondità** (avanti/indietro). I colpi vanno a segno solo se
  i due sono allineati anche in profondità, come nei picchiaduro 2.5D
- 🤖 **Avversario IA**: modalità **1 giocatore (vs CPU)** oltre ai **2 giocatori**
- 💨 **Stamina (fiato)**: ogni colpo consuma fiato che si recupera nel tempo,
  niente spam di calci
- ❤️ Barre vita e stamina, timer di round e indicatori dei round vinti
- 🛡️ **Guardia** che riduce danno e knockback
- 🔁 Round al meglio dei 3; a tempo scaduto vince chi ha più vita

## Installazione

```bash
pip install -r requirements.txt
```

## Avvio

```bash
python main.py
```

Nel menu: **FRECCE** per scegliere la modalità, **INVIO** per iniziare,
**ESC** per uscire (o tornare al menu durante il match).

## Comandi

| Azione         | Giocatore 1 | Giocatore 2 |
|----------------|-------------|-------------|
| Sinistra/Destra| `A` / `D`   | `←` / `→`   |
| Profondità     | `W` / `S`   | `↑` / `↓`   |
| Jab            | `F`         | `Num 1`     |
| Diretto        | `G`         | `Num 2`     |
| Calcio basso   | `V`         | `Num 3`     |
| Calcio alto    | `B`         | `Num 5`     |
| Guardia        | `Shift sx`  | `Num 0`     |

In modalità 1 giocatore controlli il Giocatore 1; il Giocatore 2 è la CPU.

## Struttura del progetto

```
main.py                 punto di ingresso
picchiaduro/
├── __init__.py
├── settings.py         costanti: ring, proiezione, fisica, colpi, colori, comandi
├── prospettiva.py      proiezione 2.5D mondo -> schermo (trapezio + scala)
├── fighter.py          classe Lottatore: stato, footwork, colpi, stamina, disegno
├── ia.py               IAKickboxer: avversario controllato dalla CPU
└── game.py             loop, stati, ring 2.5D, HUD, menu modalità
tools/
└── genera_anteprima.py genera una GIF di anteprima in modalità headless
```

## Personalizzazione

Quasi tutto il bilanciamento è in `picchiaduro/settings.py`:

- **Colpi** (danno, durata, portata, knockback, costo stamina) nel dizionario `ATTACCHI`
- **2.5D**: profondità del ring, prospettiva e scala nelle costanti `RING_*`,
  `NEAR_*`, `FAR_*`, `SCALA_*` e `TOLLERANZA_PROFONDITA`
- **Movimento e fiato**: `VELOCITA_X`, `VELOCITA_Z`, `STAMINA_*`
- **Round**: `ROUND_PER_VINCERE`, `DURATA_ROUND`
- **Comandi**: `CONTROLLI_P1` / `CONTROLLI_P2`
- **Difficoltà CPU**: parametro `difficolta` di `IAKickboxer` (`facile`/`media`/`difficile`)
