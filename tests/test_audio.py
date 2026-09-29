"""Test del modulo audio: sintesi, formato del mixer, eventi, muto, fallback."""

from __future__ import annotations

import math
import os
import time
from array import array

import pygame
import pytest

from picchiaduro import audio as A
from picchiaduro import eventi as ev


@pytest.fixture(scope='module', autouse=True)
def cache_temporanea(tmp_path_factory):
    """Cache su disco isolata: i test non toccano ~/.cache."""
    vecchio = os.environ.get('KICKBOXING_K1_CACHE')
    os.environ['KICKBOXING_K1_CACHE'] = str(tmp_path_factory.mktemp('cache_audio'))
    yield
    if vecchio is None:
        os.environ.pop('KICKBOXING_K1_CACHE', None)
    else:
        os.environ['KICKBOXING_K1_CACHE'] = vecchio


@pytest.fixture(scope='module')
def sfx():
    t0 = time.perf_counter()
    dati = A.genera_sfx()
    dati['_tempo'] = time.perf_counter() - t0
    return dati


@pytest.fixture(scope='module')
def audio():
    a = A.Audio()
    assert a.attendi(60)
    yield a
    a.ferma()


def _picco(a):
    return max(max(a), -min(a))


def _rms(a):
    return math.sqrt(sum(v * v for v in a) / len(a))


TUTTI_EVENTI = [
    ev.AttaccoIniziato(0, 'jab'), ev.AttaccoIniziato(0, 'diretto'), ev.AttaccoIniziato(1, 'gancio'),
    ev.AttaccoIniziato(1, 'calcio_basso'), ev.AttaccoIniziato(0, 'ginocchiata'),
    ev.AttaccoIniziato(0, 'calcio_alto'), ev.AttaccoIniziato(0, 'calcio_girato'),
    ev.AttaccoIniziato(0, 'mossa_inventata'),
    ev.ColpoASegno(0, 1, 'jab', 5.0, False, False, 1, 'alto', 0.3, 900.0, 200.0, 150.0),
    ev.ColpoASegno(0, 1, 'calcio_alto', 12.0, False, False, 2, 'alto', 0.9, 100.0, 200.0, 150.0),
    ev.ColpoASegno(1, 0, 'diretto', 9.0, False, True, 1, 'medio', 0.7, 1700.0, 100.0, 120.0),
    ev.ColpoASegno(1, 0, 'gancio', 1.0, True, False, 1, 'medio', 0.4, 900.0, 100.0, 120.0),
    ev.Mancato(0, 'jab'), ev.Schivata(0, 'laterale'), ev.Schivata(1, 'indietro', True),
    ev.GuardiaRotta(1), ev.Atterramento(1, 1), ev.ConteggioArbitro(1, 1), ev.ConteggioArbitro(1, 8),
    ev.Rialzo(1), ev.KO(1), ev.KO(0, True), ev.SuperPronto(0), ev.InizioRound(1), ev.Via(1),
    ev.FineRound(1, 0, 'ko'), ev.FinePartita(0), ev.Passo(0),
]


# ---- sintesi

def test_sfx_completi_e_puliti(sfx):
    for nome in A.NOMI_SFX:
        assert nome in sfx, nome
        a = sfx[nome]
        assert a.typecode == 'h' and len(a) > 200
        assert 0.3 * 32767 <= _picco(a) <= 0.96 * 32767, nome  # presente ma senza clipping
        assert _rms(a) > 200, nome


def test_durate_plausibili(sfx):
    d = {n: len(sfx[n]) / A.FREQ_SINTESI for n in A.NOMI_SFX}
    assert d['ui_muovi'] < 0.15
    assert d['impatto_pugno'] < d['impatto_calcio'] <= d['impatto_contro'] + 0.2
    assert d['ko'] > 1.5
    assert d['campana'] > 2.0
    assert d['campana_tripla'] > d['campana']
    assert 0.3 < d['conteggio'] < 0.8


def test_fine_senza_scatti(sfx):
    """Nessun suono termina con un salto (dissolvenza finale a zero)."""
    for nome in A.NOMI_SFX:
        assert abs(sfx[nome][-1]) < 400, nome


def test_tempo_generazione_effetti(sfx):
    assert sfx['_tempo'] <= 1.5, sfx['_tempo']


def test_determinismo(sfx):
    ancora = A.genera_sfx()
    for nome in A.NOMI_SFX:
        assert ancora[nome] == sfx[nome], nome


def test_campana_ha_parziali_inarmoniche(sfx):
    """Lo spettro della campana ha picchi non multipli interi di un'unica fondamentale."""
    a = sfx['campana']
    n = 16384
    seg = [a[i] * (0.5 - 0.5 * math.cos(2 * math.pi * i / n)) for i in range(2000, 2000 + n)]
    # DFT solo su alcune frequenze candidate (evita FFT): rapporto 1.19 (terza minore) vs 1.25
    def ampiezza(f):
        w = 2 * math.pi * f / A.FREQ_SINTESI
        re = sum(v * math.cos(w * i) for i, v in enumerate(seg))
        im = sum(v * math.sin(w * i) for i, v in enumerate(seg))
        return math.hypot(re, im)
    f0 = 540.0
    assert ampiezza(f0 * 1.19) > 4 * ampiezza(f0 * 1.25)
    assert ampiezza(f0 * 2.98) > 4 * ampiezza(f0 * 2.7)


def test_impatti_differenziati(sfx):
    """Il calcio ha piu' energia grave del pugno, il contro piu' brillante."""
    def frazione_grave(a):
        lento = 0.0
        tot = 0.0
        y = 0.0
        k = 1 - math.exp(-2 * math.pi * 250 / A.FREQ_SINTESI)
        for s in a:
            y += k * (s - y)
            lento += y * y
            tot += s * s
        return lento / tot
    assert frazione_grave(sfx['impatto_calcio']) > frazione_grave(sfx['impatto_pugno'])
    assert frazione_grave(sfx['ko']) > 0.5


def test_folla_e_musica_in_loop():
    folla = A.genera_folla()
    assert set(folla) == {'folla', 'boato'}
    f = folla['folla']
    assert _picco(f) <= 0.61 * 32767
    # ciclica: salto tra coda e testa dello stesso ordine dei salti interni
    salti = sorted(abs(f[i + 1] - f[i]) for i in range(0, len(f) - 1, 5))
    assert abs(f[0] - f[-1]) <= salti[-1] * 1.5


@pytest.mark.parametrize('traccia,durata_min', [('menu', 14.0), ('combattimento', 10.0)])
def test_musica(traccia, durata_min):
    t0 = time.perf_counter()
    m = A.genera_musica(traccia)[traccia]
    assert time.perf_counter() - t0 < 6.0
    assert len(m) / A.FREQ_SINTESI >= durata_min
    assert 0.5 * 32767 < _picco(m) <= 0.81 * 32767
    assert _rms(m) > 2000
    # 8 battute di 16 passi: la lunghezza e' esattamente un multiplo di 128 passi
    assert len(m) % 128 == 0
    # il loop non deve avere scatti al giro
    salti = sorted(abs(m[i + 1] - m[i]) for i in range(0, len(m) - 1, 11))
    assert abs(m[0] - m[-1]) <= salti[-1] + 1


def test_traccia_sconosciuta():
    with pytest.raises(ValueError):
        A.genera_musica('polka')


# ---- formato mixer

@pytest.mark.parametrize('freq,canali,fmt,byte_camp', [
    (22050, 1, -16, 2), (44100, 2, -16, 4), (48000, 2, -16, 4), (44100, 1, 16, 2),
    (44100, 2, -8, 2), (44100, 2, 8, 2), (44100, 2, 32, 8),
])
def test_formatta_per_mixer(freq, canali, fmt, byte_camp):
    src = array('h', [0, 1000, -1000, 20000, -20000, 0] * 100)
    b = A.formatta_per_mixer(src, freq, canali, fmt)
    atteso = len(src) * freq / A.FREQ_SINTESI
    assert abs(len(b) / byte_camp - atteso) <= 4
    assert isinstance(b, bytes)


def test_formatta_16bit_stereo_duplicato():
    src = array('h', [100, 200, 300, 400])
    b = array('h')
    b.frombytes(A.formatta_per_mixer(src, 22050, 2, -16))
    assert list(b) == [100, 100, 200, 200, 300, 300, 400, 400]


# ---- classe Audio

def test_audio_attivo(audio):
    assert audio.attivo
    assert pygame.mixer.get_init()
    assert audio.tempo_generazione < 1.5
    assert audio.pronto()


def test_ogni_evento_e_gestito(audio):
    for e in TUTTI_EVENTI:
        audio.gestisci_evento(e)
    audio.gestisci_evento(object())     # evento sconosciuto: ignorato
    audio.gestisci_evento(None)


def test_evento_produce_suono(audio):
    pygame.mixer.stop()
    audio._ultimo_boato = -10.0
    audio.gestisci_evento(ev.ColpoASegno(0, 1, 'diretto', 9.0, False, False, 1, 'medio', 0.7, 900.0, 100.0, 120.0))
    assert any(pygame.mixer.Channel(i).get_busy() for i in range(A.CANALI_RISERVATI, A.NUM_CANALI))


def test_suona_nomi_e_volumi(audio):
    for nome in A.NOMI_SFX + ('boato',):
        audio.suona(nome)
        audio.suona(nome, 0.3)
        audio.suona(nome, 5.0)      # volume fuori scala: clamp
        audio.suona(nome, -1.0)
    audio.suona('non_esiste')
    audio.suona('conteggio', 1.0, pitch=1.2)
    audio.suona('passo', 1.0, pan=-1.0)
    audio.suona('passo', 1.0, pan=1.0)


def test_varianti_di_pitch(audio):
    """Suonare piu' volte lo stesso colpo crea varianti (buffer di lunghezza diversa)."""
    for _ in range(30):
        audio.suona('impatto_pugno', 0.1)
    lunghezze = {chiave[1] for chiave in audio._suoni if chiave[0] == 'impatto_pugno'}
    assert len(lunghezze) >= 3


def test_musica_e_pubblico(audio):
    audio.musica('menu')
    assert pygame.mixer.Channel(audio._canale_mus).get_busy()
    audio.musica('combattimento')
    assert audio._traccia_in_corso == 'combattimento'
    audio.musica('combattimento')
    audio.musica('non_esiste')          # traccia sconosciuta = stop
    assert audio._traccia is None
    audio.musica(None)
    audio.pubblico(0.6)
    assert pygame.mixer.Channel(A.CANALE_FOLLA).get_busy()
    audio.pubblico(5.0)
    audio.pubblico(-1.0)
    assert not audio._folla_in_corso
    audio.pubblico(0.0)


def test_muto(audio):
    audio.musica('combattimento')
    audio.pubblico(0.5)
    assert audio.muto() is True
    assert audio.muto(True) is True
    pygame.mixer.stop()
    audio.suona('ko')
    assert not any(pygame.mixer.Channel(i).get_busy() for i in range(A.NUM_CANALI))
    assert audio.muto(False) is False
    assert audio.muto() is True
    assert audio.muto() is False
    audio.suona('ko')
    assert any(pygame.mixer.Channel(i).get_busy() for i in range(A.CANALI_RISERVATI, A.NUM_CANALI))
    audio.ferma()


def test_disabilitato_e_no_op():
    a = A.Audio(abilitato=False)
    assert not a.attivo and a.pronto()
    for e in TUTTI_EVENTI:
        a.gestisci_evento(e)
    a.suona('ko')
    a.musica('menu')
    a.pubblico(1.0)
    assert a.muto() is True
    assert a.muto(False) is False
    a.ferma()


def test_fallback_senza_mixer(monkeypatch):
    """Se il mixer non parte, tutto diventa silenzioso senza eccezioni."""
    pygame.mixer.quit()

    def guasto(*args, **kwargs):
        raise pygame.error('nessun dispositivo audio')
    monkeypatch.setattr(pygame.mixer, 'init', guasto)
    a = A.Audio()
    assert not a.attivo and a.pronto()
    for e in TUTTI_EVENTI:
        a.gestisci_evento(e)
    a.suona('ko')
    a.musica('combattimento')
    a.pubblico(0.7)
    assert a.muto() is True
    monkeypatch.undo()
    pygame.mixer.init()


def test_mixer_con_formato_diverso():
    """Con un mixer a 22050 Hz mono l'audio si adatta."""
    pygame.mixer.quit()
    pygame.mixer.init(22050, -16, 1, 512)
    try:
        a = A.Audio()
        assert a.attendi(60)
        assert a.attivo
        a.suona('ko')
        a.gestisci_evento(ev.KO(0))
        a.musica('menu')
        a.ferma()
    finally:
        pygame.mixer.quit()
        pygame.mixer.init()


# ---- cache

def test_cache_su_disco_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv('KICKBOXING_K1_CACHE', str(tmp_path))
    dati = {'x': array('h', [1, -2, 3, 32767]), 'y': array('h', [5] * 1000)}
    assert A._carica_cache('prova') is None
    A._salva_cache('prova', dati)
    assert A._carica_cache('prova') == dati
    # file corrotto: ignorato
    percorso = A._percorso_cache('prova')
    with open(percorso, 'ab') as f:
        f.write(b'\x00\x01')
    assert A._carica_cache('prova') is None


def test_cache_ricarica_veloce(tmp_path, monkeypatch):
    monkeypatch.setenv('KICKBOXING_K1_CACHE', str(tmp_path))
    dati = A._gruppo('sfx', A.genera_sfx)
    t0 = time.perf_counter()
    ancora = A._gruppo('sfx', lambda: (_ for _ in ()).throw(AssertionError('rigenerato')))
    assert time.perf_counter() - t0 < 0.3
    assert ancora == dati
