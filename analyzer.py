"""Beat pattern analysis and feature extraction from MIDI drum files."""

import re
import os
import mido

# GM drum note to instrument name mapping
GM_DRUM_MAP = {
    35: 'acoustic_bass_drum', 36: 'bass_drum',
    37: 'side_stick', 38: 'acoustic_snare',
    39: 'hand_clap', 40: 'electric_snare',
    41: 'low_floor_tom', 42: 'closed_hihat',
    43: 'high_floor_tom', 44: 'pedal_hihat',
    45: 'low_tom', 46: 'open_hihat',
    47: 'low_mid_tom', 48: 'hi_mid_tom',
    49: 'crash_1', 50: 'high_tom',
    51: 'ride_1', 52: 'chinese_cymbal',
    53: 'ride_bell', 54: 'tambourine',
    55: 'splash', 56: 'cowbell',
    57: 'crash_2', 58: 'vibraslap',
    59: 'ride_2', 60: 'hi_bongo',
    61: 'lo_bongo', 62: 'mute_hi_conga',
    63: 'open_hi_conga', 64: 'low_conga',
    65: 'hi_timbale', 66: 'lo_timbale',
    67: 'hi_agogo', 68: 'lo_agogo',
    69: 'cabasa', 70: 'maracas',
    71: 'short_whistle', 72: 'long_whistle',
    73: 'short_guiro', 74: 'long_guiro',
    75: 'claves', 76: 'hi_wood_block',
    77: 'lo_wood_block', 78: 'mute_cuica',
    79: 'open_cuica', 80: 'mute_triangle',
    81: 'open_triangle', 82: 'shaker',
    83: 'jingle_bell', 84: 'bell_tree',
    85: 'castanets', 86: 'mute_surdo',
    87: 'open_surdo',
}

# Simplified instrument names for beat_grid (merge variants)
INSTRUMENT_SIMPLIFY = {
    'acoustic_bass_drum': 'kick', 'bass_drum': 'kick',
    'acoustic_snare': 'snare', 'electric_snare': 'snare',
    'closed_hihat': 'hihat_closed', 'pedal_hihat': 'hihat_pedal',
    'open_hihat': 'hihat_open',
    'ride_1': 'ride', 'ride_2': 'ride', 'ride_bell': 'ride_bell',
    'crash_1': 'crash', 'crash_2': 'crash',
    'chinese_cymbal': 'crash', 'splash': 'crash',
}


def extract_tempo_from_filename(filename):
    """Try to extract BPM from filename patterns like '120_pattern' or 'pattern_120bpm'."""
    m = re.search(r'(?:^|[_\-\s])(\d{2,3})(?:[_\-\s]|bpm|$)', filename, re.IGNORECASE)
    if m:
        bpm = int(m.group(1))
        if 40 <= bpm <= 300:
            return float(bpm)
    return None


def detect_fill(path, filename):
    """Heuristic: is this a fill/break pattern?"""
    text = (path + '/' + filename).lower()
    return any(w in text for w in ('fill', 'brk', 'break', 'flam'))


def detect_brush(path, filename):
    """Heuristic: is this a brush pattern?"""
    text = (path + '/' + filename).lower()
    return 'brush' in text


def analyze_midi(filepath, archive_root):
    """Parse a MIDI file and extract all features.

    Returns a dict with file info, features, instruments, and beat grid,
    or None if the file can't be parsed.
    """
    try:
        mid = mido.MidiFile(filepath)
    except Exception:
        return None

    rel_path = os.path.relpath(filepath, archive_root)
    filename = os.path.basename(filepath)
    parts = rel_path.split(os.sep)
    folder = parts[0] if len(parts) > 1 else ''
    subfolder = parts[1] if len(parts) > 2 else ''

    ticks_per_beat = mid.ticks_per_beat or 480

    # Collect all note events with absolute tick positions
    notes = []  # (abs_tick, note, velocity)
    tempo = 500000  # default 120 BPM
    time_sig_stated = '4/4'

    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                notes.append((abs_tick, msg.note, msg.velocity))
            elif msg.type == 'set_tempo':
                tempo = msg.tempo
            elif msg.type == 'time_signature':
                time_sig_stated = f'{msg.numerator}/{msg.denominator}'

    if not notes:
        return None

    tempo_bpm = mido.tempo2bpm(tempo)

    # Check for tempo in filename
    fname_tempo = extract_tempo_from_filename(filename)

    # Pattern length in beats
    max_tick = max(n[0] for n in notes)
    pattern_length_beats = max_tick / ticks_per_beat if ticks_per_beat else 0

    # Duration in seconds
    duration_sec = mido.tick2second(max_tick, ticks_per_beat, tempo)

    # Detect time signature from pattern length
    time_sig_detected = detect_time_signature(pattern_length_beats, folder, time_sig_stated)

    # Map notes to instruments and build beat grid
    instrument_counts = {}
    beat_grid = []

    for abs_tick, note, velocity in notes:
        inst_name = GM_DRUM_MAP.get(note)
        if inst_name is None:
            inst_name = f'note_{note}'

        # Count instruments
        instrument_counts[inst_name] = instrument_counts.get(inst_name, 0) + 1

        # Beat position (1-indexed)
        beat_pos = round(abs_tick / ticks_per_beat, 4) + 1.0

        # Simplified instrument for beat grid
        simple_inst = INSTRUMENT_SIMPLIFY.get(inst_name, inst_name)

        # Grid slot quantization
        grid_slot = quantize_to_grid_slot(abs_tick, ticks_per_beat)

        beat_grid.append({
            'instrument': simple_inst,
            'beat_position': beat_pos,
            'velocity': velocity,
            'grid_slot': grid_slot,
        })

    # Swing detection
    swing_ratio = detect_swing(notes, ticks_per_beat)

    # Note density
    note_density = len(notes) / pattern_length_beats if pattern_length_beats > 0 else 0

    return {
        'file': {
            'path': rel_path,
            'filename': filename,
            'folder': folder,
            'subfolder': subfolder,
            'file_size': os.path.getsize(filepath),
            'midi_type': mid.type,
            'ticks_per_beat': ticks_per_beat,
            'duration_sec': round(duration_sec, 3),
            'num_notes': len(notes),
        },
        'features': {
            'time_sig_stated': time_sig_stated,
            'time_sig_detected': time_sig_detected,
            'tempo_bpm': round(fname_tempo or tempo_bpm, 1),
            'pattern_length_beats': round(pattern_length_beats, 2),
            'swing_ratio': round(swing_ratio, 3),
            'note_density': round(note_density, 2),
            'is_fill': detect_fill(rel_path, filename),
            'is_brush': detect_brush(rel_path, filename),
        },
        'instruments': instrument_counts,
        'beat_grid': beat_grid,
    }


def detect_time_signature(pattern_length_beats, folder_name, stated_sig='4/4'):
    """Infer time signature from pattern length, folder hints, and stated sig.

    Strategy: trust the stated time signature unless there's strong evidence
    against it. Pattern length alone is too ambiguous — e.g. a 15-beat pattern
    could be 4 bars of 4/4 (last note on beat 15 of 16) or 5 bars of 3/4.
    """
    folder_lower = folder_name.lower()
    length = round(pattern_length_beats, 1)

    if length <= 0:
        return 'unknown'

    # Strong folder hints override everything
    waltz_folder = any(w in folder_lower for w in ('waltz', 'nothing but three'))
    if waltz_folder:
        return '3/4'

    # Odd meter folders/stated sigs — trust these, they're intentional
    odd_meter_folder = 'odd meter' in folder_lower
    if odd_meter_folder:
        # Try to detect which odd meter from pattern length
        if abs(length % 3.5) < 0.4 or stated_sig == '7/8':
            return '7/8'
        if abs(length % 2.5) < 0.4 or stated_sig == '5/4':
            return '5/4'
        if stated_sig in ('7/8', '5/4', '5/8', '9/8', '11/8'):
            return stated_sig
        # Fall through to length-based detection below

    # For non-standard stated sigs, trust them if the length is compatible
    if stated_sig == '3/4' and _near_multiple(length, 3):
        return '3/4'
    if stated_sig == '6/8' and _near_multiple(length, 3):
        return '6/8'
    if stated_sig == '6/4' and _near_multiple(length, 6):
        return '6/4'
    if stated_sig in ('7/8',) and _near_multiple(length, 3.5):
        return '7/8'
    if stated_sig in ('5/4', '5/8') and _near_multiple(length, 2.5):
        return '5/4'

    # For stated 4/4 (the vast majority), only override with strong evidence:
    # the pattern must fit 3 cleanly AND not fit 4 at all
    fits_3_only = _near_multiple(length, 3) and not _near_multiple(length, 4)
    if fits_3_only and length <= 6.5:
        # Short pattern that's clearly in 3 — but still check folder context
        # Many 3-beat patterns are just 4/4 fills ending on beat 3
        if any(w in folder_lower for w in ('waltz', 'three', '3/4', 'bossa')):
            return '3/4'
        # A 3-beat pattern from a rock/funk/pop folder is almost certainly
        # a truncated 4/4 fill, not a waltz
        return stated_sig

    # Detect 6/8 from pattern length (must not also fit 4)
    if _near_multiple(length, 6) and not _near_multiple(length, 4):
        return '6/8'

    # Default: trust the stated signature
    return stated_sig


def _near_multiple(length, divisor, tolerance=0.5):
    """Check if length is approximately a multiple of divisor."""
    remainder = length % divisor
    return remainder < tolerance or remainder > (divisor - tolerance)


def detect_swing(notes, ticks_per_beat):
    """Detect swing ratio from hi-hat/ride spacing.

    Returns ~1.0 for straight, ~1.5-2.0 for swing.
    """
    # Find hi-hat and ride notes (42, 44, 46, 51, 53, 59)
    ride_hihat_notes = {42, 44, 46, 51, 53, 59}
    timings = sorted(n[0] for n in notes if n[1] in ride_hihat_notes)

    if len(timings) < 3:
        return 1.0

    # Look at consecutive intervals at 8th-note level
    eighth = ticks_per_beat / 2
    intervals = []
    for i in range(1, len(timings)):
        gap = timings[i] - timings[i - 1]
        # Only consider gaps roughly in the 8th-note range
        if eighth * 0.3 < gap < eighth * 2.5:
            intervals.append(gap)

    if len(intervals) < 2:
        return 1.0

    # Group into pairs (long, short) to detect swing
    ratios = []
    for i in range(0, len(intervals) - 1, 2):
        short = min(intervals[i], intervals[i + 1])
        long = max(intervals[i], intervals[i + 1])
        if short > 0:
            ratios.append(long / short)

    if not ratios:
        return 1.0

    avg_ratio = sum(ratios) / len(ratios)
    # Clamp to reasonable range
    return max(1.0, min(3.0, avg_ratio))


def quantize_to_grid_slot(abs_tick, ticks_per_beat):
    """Quantize a tick position to a 16th-note grid slot label.

    Returns labels like "1", "1+", "1e", "1a", "2", "2+", etc.
    """
    sixteenth = ticks_per_beat / 4
    # Position within the pattern in 16th notes
    pos_in_sixteenths = abs_tick / sixteenth
    # Which beat (0-indexed)
    beat = int(pos_in_sixteenths // 4)
    # Which subdivision within the beat (0-3)
    sub = round(pos_in_sixteenths % 4)
    if sub >= 4:
        beat += 1
        sub = 0

    beat_num = beat + 1  # 1-indexed
    suffixes = ['', 'e', '+', 'a']
    return f'{beat_num}{suffixes[sub % 4]}'
