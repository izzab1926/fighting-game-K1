# Picchiaduro K1 🥊

Un picchiaduro 2D locale a due giocatori scritto in **Python** con
[pygame](https://www.pygame.org/). Grafica a forme geometriche: nessun asset
esterno richiesto, gira ovunque ci sia Python + pygame.

## Caratteristiche

- ⚔️ Combattimento 1 contro 1 in locale sulla stessa tastiera
- ❤️ Barre della vita, timer di round e indicatori dei round vinti
- 🥊 Due attacchi: **pugno** (veloce, poco danno) e **calcio** (lento, più danno e portata)
- 🛡️ **Parata** che riduce il danno, **salto** e **accovacciata**
- 🔁 Sistema a round: vince chi si aggiudica per primo 2 round (al meglio dei 3)
- ⏱️ Allo scadere del tempo vince chi ha più vita

## Installazione

```bash
pip install -r requirements.txt
```

## Avvio

```bash
python main.py
```

Premi **INVIO** nel menu per iniziare, **ESC** per uscire.

## Comandi

| Azione       | Giocatore 1 | Giocatore 2 |
|--------------|-------------|-------------|
| Muovi        | `A` / `D`   | `←` / `→`   |
| Salta        | `W`         | `↑`         |
| Accovacciati | `S`         | `↓`         |
| Pugno        | `F`         | `Num 1`     |
| Calcio       | `G`         | `Num 2`     |
| Parata       | `H`         | `Num 3`     |

## Struttura del progetto

```
main.py                 punto di ingresso
picchiaduro/
├── __init__.py
├── settings.py         costanti: finestra, fisica, attacchi, colori, comandi
├── fighter.py          classe Lottatore: stato, fisica, attacchi, disegno
└── game.py             loop di gioco, stati (menu/combattimento/round/partita), HUD
```

## Personalizzazione

Quasi tutto il bilanciamento è in `picchiaduro/settings.py`:
danno e portata degli attacchi nel dizionario `ATTACCHI`, gravità e velocità
nella sezione fisica, durata del round in `DURATA_ROUND` e i tasti in
`CONTROLLI_P1` / `CONTROLLI_P2`.
