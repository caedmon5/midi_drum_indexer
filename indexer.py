#!/usr/bin/env python3
"""MIDI drum file indexer — walks archive directory, extracts features, stores in SQLite."""

import argparse
import os
import sqlite3
import sys
from multiprocessing import Pool, cpu_count
from functools import partial

from tqdm import tqdm
from analyzer import analyze_midi

DEFAULT_ARCHIVE = os.path.expanduser(
    '~/Dropbox/Music/drumMidi/'
    '800000_Drum_Percussion_MIDI_Archive[6_19_15]/'
    '800000_Drum_Percussion_MIDI_Archive[6_19_15]'
)
DEFAULT_DB = os.path.join(os.path.dirname(__file__), 'drums.db')


def init_db(db_path):
    """Create database and tables from schema.sql."""
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    conn = sqlite3.connect(db_path)
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def get_indexed_paths(conn):
    """Return set of already-indexed relative paths."""
    cursor = conn.execute('SELECT path FROM files')
    return {row[0] for row in cursor}


def collect_midi_files(archive_root, folders=None):
    """Walk archive and collect .mid file paths, optionally filtering by folder."""
    midi_files = []
    for dirpath, dirnames, filenames in os.walk(archive_root):
        # Skip __MACOSX junk
        dirnames[:] = [d for d in dirnames if d != '__MACOSX']

        rel_dir = os.path.relpath(dirpath, archive_root)
        top_folder = rel_dir.split(os.sep)[0] if rel_dir != '.' else ''

        # Filter by folder list if specified
        if folders and top_folder and top_folder not in folders:
            dirnames.clear()
            continue

        for fn in filenames:
            if fn.lower().endswith(('.mid', '.midi')):
                midi_files.append(os.path.join(dirpath, fn))

    return midi_files


def _analyze_wrapper(args):
    """Wrapper for multiprocessing — unpacks (filepath, archive_root)."""
    filepath, archive_root = args
    return analyze_midi(filepath, archive_root)


def build_instrument_lookup(conn):
    """Build name→id mapping from instruments table."""
    cursor = conn.execute('SELECT id, name FROM instruments')
    return {row[1]: row[0] for row in cursor}


def insert_result(conn, result, instrument_lookup):
    """Insert one analysis result into the database."""
    f = result['file']
    cursor = conn.execute(
        'INSERT INTO files (path, filename, folder, subfolder, file_size, '
        'midi_type, ticks_per_beat, duration_sec, num_notes) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (f['path'], f['filename'], f['folder'], f['subfolder'],
         f['file_size'], f['midi_type'], f['ticks_per_beat'],
         f['duration_sec'], f['num_notes'])
    )
    file_id = cursor.lastrowid

    feat = result['features']
    conn.execute(
        'INSERT INTO features (file_id, time_sig_stated, time_sig_detected, '
        'tempo_bpm, pattern_length_beats, swing_ratio, note_density, '
        'is_fill, is_brush) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (file_id, feat['time_sig_stated'], feat['time_sig_detected'],
         feat['tempo_bpm'], feat['pattern_length_beats'], feat['swing_ratio'],
         feat['note_density'], feat['is_fill'], feat['is_brush'])
    )

    for inst_name, count in result['instruments'].items():
        inst_id = instrument_lookup.get(inst_name)
        if inst_id is None:
            # Unknown instrument (e.g. note_91) — insert it
            category = 'Other'
            gm_note = None
            if inst_name.startswith('note_'):
                try:
                    gm_note = int(inst_name.split('_')[1])
                except ValueError:
                    pass
            cursor = conn.execute(
                'INSERT OR IGNORE INTO instruments (name, category, gm_note) '
                'VALUES (?, ?, ?)', (inst_name, category, gm_note)
            )
            if cursor.lastrowid:
                inst_id = cursor.lastrowid
                instrument_lookup[inst_name] = inst_id
            else:
                inst_id = conn.execute(
                    'SELECT id FROM instruments WHERE name = ?', (inst_name,)
                ).fetchone()[0]
                instrument_lookup[inst_name] = inst_id

        conn.execute(
            'INSERT OR IGNORE INTO file_instruments (file_id, instrument_id, hit_count) '
            'VALUES (?, ?, ?)', (file_id, inst_id, count)
        )

    for bg in result['beat_grid']:
        conn.execute(
            'INSERT INTO beat_grid (file_id, instrument, beat_position, '
            'velocity, grid_slot) VALUES (?, ?, ?, ?, ?)',
            (file_id, bg['instrument'], bg['beat_position'],
             bg['velocity'], bg['grid_slot'])
        )


def main():
    parser = argparse.ArgumentParser(description='Index MIDI drum files')
    parser.add_argument('--archive', default=DEFAULT_ARCHIVE,
                        help='Path to archive root directory')
    parser.add_argument('--db', default=DEFAULT_DB,
                        help='SQLite database path')
    parser.add_argument('--folders', type=str, default=None,
                        help='Comma-separated list of folders to index (default: all curated)')
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of parallel workers (default: CPU count)')
    parser.add_argument('--all', action='store_true',
                        help='Index all folders including GM MIDI Pack and Superior Drummer')
    args = parser.parse_args()

    archive_root = args.archive
    if not os.path.isdir(archive_root):
        print(f'Archive not found: {archive_root}')
        sys.exit(1)

    # Default: index curated folders (exclude the huge GM/SD2 collections)
    folders = None
    if args.folders:
        folders = [f.strip() for f in args.folders.split(',')]
    elif not args.all:
        # Exclude the two massive collections by default
        exclude = {'GM MIDI Pack [360,000 files]',
                   'Superior Drummer 2 Drum Midi [425,000 files]',
                   '__MACOSX'}
        all_dirs = [d for d in os.listdir(archive_root)
                    if os.path.isdir(os.path.join(archive_root, d))]
        folders = [d for d in all_dirs if d not in exclude]

    conn = init_db(args.db)
    indexed = get_indexed_paths(conn)
    instrument_lookup = build_instrument_lookup(conn)

    print(f'Scanning {archive_root}...')
    midi_files = collect_midi_files(archive_root, folders)
    print(f'Found {len(midi_files)} MIDI files')

    # Filter out already indexed
    to_process = [(f, archive_root) for f in midi_files
                  if os.path.relpath(f, archive_root) not in indexed]
    print(f'{len(to_process)} new files to index')

    if not to_process:
        print('Nothing to do.')
        conn.close()
        return

    workers = args.workers or min(cpu_count(), 8)
    print(f'Processing with {workers} workers...')

    results = []
    with Pool(workers) as pool:
        for result in tqdm(pool.imap_unordered(_analyze_wrapper, to_process),
                           total=len(to_process), desc='Indexing'):
            if result is not None:
                results.append(result)

            # Batch insert every 500 results
            if len(results) >= 500:
                for r in results:
                    insert_result(conn, r, instrument_lookup)
                conn.commit()
                results.clear()

    # Insert remaining
    for r in results:
        insert_result(conn, r, instrument_lookup)
    conn.commit()

    total = conn.execute('SELECT COUNT(*) FROM files').fetchone()[0]
    print(f'Done. Total indexed files: {total}')
    conn.close()


if __name__ == '__main__':
    main()
