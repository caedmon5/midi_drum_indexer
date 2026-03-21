#!/usr/bin/env python3
"""Generate synthesized drum samples as mp3 files.

Creates punchy, distinct drum sounds using numpy synthesis.
Each sample is short (50-500ms) to keep file sizes tiny.
"""

import numpy as np
import wave
import struct
import subprocess
import os

SAMPLE_RATE = 44100
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'static', 'samples')


def normalize(signal, peak=0.9):
    mx = np.max(np.abs(signal))
    if mx > 0:
        signal = signal * (peak / mx)
    return signal


def envelope(length, attack=0.002, decay=0.05, sustain_level=0.3, release=0.1):
    """ADSR envelope."""
    n = int(length * SAMPLE_RATE)
    a = int(attack * SAMPLE_RATE)
    d = int(decay * SAMPLE_RATE)
    r = int(release * SAMPLE_RATE)
    s = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a),
        np.linspace(1, sustain_level, d),
        np.full(s, sustain_level),
        np.linspace(sustain_level, 0, r),
    ])
    return env[:n]


def exp_decay(length, rate=10):
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    return np.exp(-rate * t)


def noise(length):
    return np.random.randn(int(length * SAMPLE_RATE))


def sine(freq, length, phase=0):
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    return np.sin(2 * np.pi * freq * t + phase)


def save_wav(filename, signal):
    signal = np.clip(signal, -1, 1)
    data = (signal * 32767).astype(np.int16)
    wav_path = os.path.join(OUTPUT_DIR, filename)
    with wave.open(wav_path, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(data.tobytes())
    return wav_path


def wav_to_mp3(wav_path):
    mp3_path = wav_path.replace('.wav', '.mp3')
    subprocess.run(['ffmpeg', '-y', '-i', wav_path, '-b:a', '128k', '-ar', '44100',
                    mp3_path], capture_output=True)
    os.remove(wav_path)
    return mp3_path


def make_kick():
    """Punchy kick drum — pitch sweep from ~150Hz down to ~50Hz + click transient."""
    length = 0.35
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    # Pitch sweep
    freq = 150 * np.exp(-12 * t) + 45
    phase = np.cumsum(2 * np.pi * freq / SAMPLE_RATE)
    body = np.sin(phase) * exp_decay(length, 8)
    # Click transient
    click = noise(0.005) * np.linspace(1, 0, int(0.005 * SAMPLE_RATE))
    click = np.pad(click, (0, len(body) - len(click)))
    return normalize(body * 0.9 + click * 0.3)


def make_snare():
    """Snare — body tone + noise burst with bandpass character."""
    length = 0.3
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    # Body
    body = sine(200, length) * exp_decay(length, 15) * 0.6
    body += sine(160, length) * exp_decay(length, 18) * 0.3
    # Noise (snare wires)
    n = noise(length) * exp_decay(length, 12) * 0.7
    # Transient
    click = noise(0.003) * np.linspace(1, 0, int(0.003 * SAMPLE_RATE))
    click = np.pad(click, (0, len(body) - len(click)))
    return normalize(body + n + click * 0.4)


def make_side_stick():
    """Side stick — short, bright click."""
    length = 0.08
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    click = sine(1800, length) * exp_decay(length, 60)
    click += sine(3200, length) * exp_decay(length, 70) * 0.5
    click += noise(length) * exp_decay(length, 80) * 0.2
    return normalize(click)


def make_clap():
    """Hand clap — multiple short noise bursts."""
    length = 0.2
    n = int(length * SAMPLE_RATE)
    signal = np.zeros(n)
    # Multiple micro-bursts to simulate multiple hands
    for offset_ms in [0, 8, 14, 20]:
        start = int(offset_ms * SAMPLE_RATE / 1000)
        burst_len = int(0.012 * SAMPLE_RATE)
        end = min(start + burst_len, n)
        signal[start:end] += np.random.randn(end - start) * 0.5
    # Tail
    tail = noise(length) * exp_decay(length, 20) * 0.4
    signal += tail
    return normalize(signal)


def make_hihat_closed():
    """Closed hi-hat — short metallic noise."""
    length = 0.08
    n = noise(length)
    # Bandpass-ish: mix high-freq tones
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    metal = sine(6000, length) * 0.3 + sine(8500, length) * 0.2 + sine(12000, length) * 0.15
    signal = (n * 0.5 + metal) * exp_decay(length, 50)
    return normalize(signal)


def make_hihat_open():
    """Open hi-hat — longer metallic noise."""
    length = 0.4
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    n = noise(length)
    metal = sine(6000, length) * 0.3 + sine(8500, length) * 0.2 + sine(12000, length) * 0.15
    signal = (n * 0.5 + metal) * exp_decay(length, 6)
    return normalize(signal)


def make_pedal_hihat():
    """Pedal hi-hat — like closed but softer attack."""
    length = 0.1
    metal = sine(5500, length) * 0.3 + sine(7500, length) * 0.2
    n = noise(length) * 0.4
    env = envelope(length, attack=0.005, decay=0.03, sustain_level=0.1, release=0.05)
    signal = (n + metal) * env
    return normalize(signal)


def make_tom(freq, decay_rate=12):
    """Generic tom — pitched body with attack."""
    length = 0.35
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    # Slight pitch drop
    f = freq * (1 + 0.3 * np.exp(-20 * t))
    phase = np.cumsum(2 * np.pi * f / SAMPLE_RATE)
    body = np.sin(phase) * exp_decay(length, decay_rate)
    # Attack transient
    click = noise(0.004) * np.linspace(1, 0, int(0.004 * SAMPLE_RATE))
    click = np.pad(click, (0, len(body) - len(click)))
    return normalize(body * 0.8 + click * 0.3)


def make_ride():
    """Ride cymbal — complex metallic with long sustain."""
    length = 0.8
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    # Multiple inharmonic partials
    signal = (sine(3400, length) * 0.3 + sine(5100, length) * 0.25 +
              sine(7200, length) * 0.2 + sine(9800, length) * 0.1 +
              noise(length) * 0.08)
    signal *= exp_decay(length, 3)
    # Stick attack
    click = noise(0.003) * np.linspace(1, 0, int(0.003 * SAMPLE_RATE)) * 0.6
    click = np.pad(click, (0, len(signal) - len(click)))
    return normalize(signal + click)


def make_ride_bell():
    """Ride bell — brighter, more tonal."""
    length = 0.6
    signal = (sine(4200, length) * 0.4 + sine(6800, length) * 0.3 +
              sine(2800, length) * 0.2)
    signal *= exp_decay(length, 4)
    click = noise(0.002) * np.linspace(1, 0, int(0.002 * SAMPLE_RATE)) * 0.3
    click = np.pad(click, (0, len(signal) - len(click)))
    return normalize(signal + click)


def make_crash():
    """Crash cymbal — wide, washy."""
    length = 1.2
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    signal = (sine(3000, length) * 0.2 + sine(4500, length) * 0.2 +
              sine(6700, length) * 0.15 + sine(9200, length) * 0.1 +
              noise(length) * 0.25)
    signal *= exp_decay(length, 2.5)
    return normalize(signal)


def make_cowbell():
    """Cowbell — two inharmonic tones."""
    length = 0.2
    signal = sine(560, length) * 0.6 + sine(845, length) * 0.4
    signal *= exp_decay(length, 15)
    # Hard attack
    click = noise(0.002) * np.linspace(1, 0, int(0.002 * SAMPLE_RATE)) * 0.5
    click = np.pad(click, (0, len(signal) - len(click)))
    return normalize(signal + click)


def make_tambourine():
    """Tambourine — jingles + tap."""
    length = 0.25
    jingles = noise(length) * 0.4
    jingles += sine(8000, length) * 0.2 + sine(11000, length) * 0.15
    jingles *= exp_decay(length, 10)
    tap = noise(0.005) * np.linspace(1, 0, int(0.005 * SAMPLE_RATE)) * 0.3
    tap = np.pad(tap, (0, len(jingles) - len(tap)))
    return normalize(jingles + tap)


def make_conga(freq, decay_rate=14):
    """Conga — warm body with skin slap."""
    length = 0.3
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    f = freq * (1 + 0.5 * np.exp(-25 * t))
    phase = np.cumsum(2 * np.pi * f / SAMPLE_RATE)
    body = np.sin(phase) * exp_decay(length, decay_rate)
    slap = noise(0.003) * np.linspace(1, 0, int(0.003 * SAMPLE_RATE)) * 0.4
    slap = np.pad(slap, (0, len(body) - len(slap)))
    return normalize(body * 0.8 + slap)


def make_bongo(freq):
    """Bongo — higher, tighter than conga."""
    length = 0.15
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    f = freq * (1 + 0.4 * np.exp(-30 * t))
    phase = np.cumsum(2 * np.pi * f / SAMPLE_RATE)
    body = np.sin(phase) * exp_decay(length, 25)
    click = noise(0.002) * np.linspace(1, 0, int(0.002 * SAMPLE_RATE)) * 0.3
    click = np.pad(click, (0, len(body) - len(click)))
    return normalize(body * 0.8 + click)


def make_timbale(freq):
    """Timbale — bright, ringy."""
    length = 0.25
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    body = sine(freq, length) * exp_decay(length, 12)
    ring = sine(freq * 2.3, length) * exp_decay(length, 18) * 0.3
    click = noise(0.002) * np.linspace(1, 0, int(0.002 * SAMPLE_RATE)) * 0.5
    click = np.pad(click, (0, len(body) - len(click)))
    return normalize(body + ring + click)


def make_agogo(freq):
    """Agogo bell."""
    length = 0.3
    signal = sine(freq, length) * 0.6 + sine(freq * 2.8, length) * 0.3
    signal *= exp_decay(length, 10)
    return normalize(signal)


def make_claves():
    """Claves — very short, bright stick sound."""
    length = 0.06
    signal = sine(2500, length) * exp_decay(length, 70)
    signal += sine(3800, length) * exp_decay(length, 80) * 0.3
    return normalize(signal)


def make_wood_block(freq):
    """Wood block."""
    length = 0.08
    signal = sine(freq, length) * exp_decay(length, 50)
    signal += sine(freq * 1.5, length) * exp_decay(length, 60) * 0.3
    click = noise(0.001) * np.linspace(1, 0, int(0.001 * SAMPLE_RATE)) * 0.2
    click = np.pad(click, (0, len(signal) - len(click)))
    return normalize(signal + click)


def make_cabasa():
    """Cabasa — beaded shaker."""
    length = 0.12
    signal = noise(length) * exp_decay(length, 25)
    # High-pass character
    signal += sine(9000, length) * exp_decay(length, 30) * 0.1
    return normalize(signal)


def make_maracas():
    """Maracas — short noise burst."""
    length = 0.08
    signal = noise(length) * exp_decay(length, 40)
    return normalize(signal)


def make_shaker():
    """Shaker."""
    length = 0.1
    signal = noise(length) * envelope(length, attack=0.005, decay=0.02, sustain_level=0.4, release=0.04)
    return normalize(signal)


def make_triangle(open=False):
    """Triangle — high, ringing."""
    length = 0.8 if open else 0.15
    decay = 2 if open else 20
    signal = sine(6000, length) * exp_decay(length, decay)
    signal += sine(12000, length) * exp_decay(length, decay * 1.2) * 0.3
    return normalize(signal)


def make_guiro(long=False):
    """Guiro — scraped gourd."""
    length = 0.3 if long else 0.1
    n = int(length * SAMPLE_RATE)
    # Simulate scraping: amplitude-modulated noise
    t = np.linspace(0, length, n)
    scrape_freq = 30 if long else 50
    am = 0.5 + 0.5 * np.sin(2 * np.pi * scrape_freq * t)
    signal = noise(length) * am * exp_decay(length, 5 if long else 15)
    signal += sine(1200, length) * exp_decay(length, 10) * 0.15
    return normalize(signal)


def make_cuica(open=False):
    """Cuica — friction drum, pitch bend."""
    length = 0.25 if open else 0.12
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    # Pitch sweep up for open, steady for mute
    if open:
        freq = 400 + 600 * t / length
    else:
        freq = 500 * np.ones_like(t)
    phase = np.cumsum(2 * np.pi * freq / SAMPLE_RATE)
    signal = np.sin(phase) * exp_decay(length, 8 if open else 20)
    return normalize(signal)


def make_surdo(open=False):
    """Surdo — deep Brazilian bass drum."""
    length = 0.5 if open else 0.2
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    freq = 70 * (1 + 0.2 * np.exp(-15 * t))
    phase = np.cumsum(2 * np.pi * freq / SAMPLE_RATE)
    body = np.sin(phase) * exp_decay(length, 5 if open else 15)
    click = noise(0.004) * np.linspace(1, 0, int(0.004 * SAMPLE_RATE)) * 0.2
    click = np.pad(click, (0, len(body) - len(click)))
    return normalize(body + click)


def make_whistle(long=False):
    """Whistle."""
    length = 0.5 if long else 0.15
    signal = sine(3200, length) * envelope(length, attack=0.01, decay=0.02,
                                            sustain_level=0.8, release=0.05)
    return normalize(signal)


def make_vibraslap():
    """Vibraslap — rattling metal."""
    length = 0.6
    t = np.linspace(0, length, int(length * SAMPLE_RATE))
    rattle = noise(length) * exp_decay(length, 4)
    # Amplitude modulation for rattle character
    am = 0.5 + 0.5 * np.sin(2 * np.pi * 40 * t)
    rattle *= am
    metal = sine(1800, length) * exp_decay(length, 6) * 0.2
    return normalize(rattle + metal)


def make_bell(freq, length=0.4):
    """Generic bell sound."""
    signal = sine(freq, length) * 0.5 + sine(freq * 2.6, length) * 0.3 + sine(freq * 4.2, length) * 0.1
    signal *= exp_decay(length, 5)
    return normalize(signal)


SAMPLES = {
    'kick':             make_kick,
    'snare':            make_snare,
    'side_stick':       make_side_stick,
    'clap':             make_clap,
    'hihat_closed':     make_hihat_closed,
    'hihat_open':       make_hihat_open,
    'hihat_pedal':      make_pedal_hihat,
    'tom_high':         lambda: make_tom(300, 14),
    'tom_hi_mid':       lambda: make_tom(230, 13),
    'tom_low_mid':      lambda: make_tom(170, 12),
    'tom_low':          lambda: make_tom(130, 11),
    'tom_hi_floor':     lambda: make_tom(100, 10),
    'tom_low_floor':    lambda: make_tom(80, 9),
    'ride':             make_ride,
    'ride_bell':        make_ride_bell,
    'crash':            make_crash,
    'splash':           lambda: make_crash(),  # reuse, shorter would be better but ok
    'cowbell':          make_cowbell,
    'tambourine':       make_tambourine,
    'hi_bongo':         lambda: make_bongo(450),
    'lo_bongo':         lambda: make_bongo(320),
    'mute_hi_conga':    lambda: make_conga(280, 20),
    'open_hi_conga':    lambda: make_conga(260, 10),
    'low_conga':        lambda: make_conga(180, 12),
    'hi_timbale':       lambda: make_timbale(800),
    'lo_timbale':       lambda: make_timbale(550),
    'hi_agogo':         lambda: make_agogo(900),
    'lo_agogo':         lambda: make_agogo(650),
    'cabasa':           make_cabasa,
    'maracas':          make_maracas,
    'shaker':           make_shaker,
    'claves':           make_claves,
    'hi_wood_block':    lambda: make_wood_block(1200),
    'lo_wood_block':    lambda: make_wood_block(800),
    'mute_triangle':    lambda: make_triangle(open=False),
    'open_triangle':    lambda: make_triangle(open=True),
    'short_guiro':      lambda: make_guiro(long=False),
    'long_guiro':       lambda: make_guiro(long=True),
    'mute_cuica':       lambda: make_cuica(open=False),
    'open_cuica':       lambda: make_cuica(open=True),
    'mute_surdo':       lambda: make_surdo(open=False),
    'open_surdo':       lambda: make_surdo(open=True),
    'short_whistle':    lambda: make_whistle(long=False),
    'long_whistle':     lambda: make_whistle(long=True),
    'vibraslap':        make_vibraslap,
    'jingle_bell':      lambda: make_bell(2500, 0.3),
    'bell_tree':        lambda: make_bell(3500, 0.6),
    'castanets':        lambda: make_wood_block(1600),
}


# Mix levels — metallic/noise sounds are perceptually louder at the same peak,
# so we scale them down to sit properly against tonal sounds (kick, toms, congas).
# 1.0 = full level, lower = quieter.
MIX_LEVELS = {
    'kick': 1.0, 'snare': 0.9, 'side_stick': 0.5, 'clap': 0.7,
    'hihat_closed': 0.35, 'hihat_open': 0.35, 'hihat_pedal': 0.3,
    'tom_high': 0.9, 'tom_hi_mid': 0.9, 'tom_low_mid': 0.9,
    'tom_low': 0.9, 'tom_hi_floor': 0.9, 'tom_low_floor': 0.9,
    'ride': 0.3, 'ride_bell': 0.35, 'crash': 0.3, 'splash': 0.3,
    'cowbell': 0.5, 'tambourine': 0.35,
    'hi_bongo': 0.7, 'lo_bongo': 0.7,
    'mute_hi_conga': 0.7, 'open_hi_conga': 0.7, 'low_conga': 0.7,
    'hi_timbale': 0.5, 'lo_timbale': 0.5,
    'hi_agogo': 0.4, 'lo_agogo': 0.4,
    'cabasa': 0.3, 'maracas': 0.3, 'shaker': 0.3,
    'claves': 0.45, 'hi_wood_block': 0.45, 'lo_wood_block': 0.45,
    'mute_triangle': 0.3, 'open_triangle': 0.3,
    'short_guiro': 0.3, 'long_guiro': 0.3,
    'mute_cuica': 0.5, 'open_cuica': 0.5,
    'mute_surdo': 0.9, 'open_surdo': 0.9,
    'short_whistle': 0.4, 'long_whistle': 0.4,
    'vibraslap': 0.35,
    'jingle_bell': 0.3, 'bell_tree': 0.3, 'castanets': 0.35,
}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f'Generating {len(SAMPLES)} drum samples...')
    for name, gen_func in SAMPLES.items():
        signal = gen_func()
        # Apply mix level
        level = MIX_LEVELS.get(name, 0.5)
        signal = signal * level
        wav_path = save_wav(f'{name}.wav', signal)
        mp3_path = wav_to_mp3(wav_path)
        size_kb = os.path.getsize(mp3_path) / 1024
        print(f'  {name}.mp3 ({size_kb:.1f} KB)')

    total_size = sum(os.path.getsize(os.path.join(OUTPUT_DIR, f))
                     for f in os.listdir(OUTPUT_DIR) if f.endswith('.mp3'))
    print(f'\nTotal: {total_size / 1024:.0f} KB')


if __name__ == '__main__':
    main()
