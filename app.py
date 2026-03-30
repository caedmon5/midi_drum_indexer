#!/usr/bin/env python3
"""Flask web app for searching and playing MIDI drum patterns."""

import json
import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, \
    redirect, url_for, Response

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'drums.db')
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
LOG_PATH = os.path.join(os.path.dirname(__file__), 'indexer.log')

# Indexer progress tracking
indexer_status = {
    'running': False,
    'progress': 0,
    'total': 0,
    'message': '',
    'done': False,
    'error': None,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def get_archive_root():
    config = load_config()
    return config.get('archive_root', '')


def db_ready():
    """Check if the database exists and has indexed files."""
    if not os.path.exists(DB_PATH):
        return False
    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute('SELECT COUNT(*) FROM files').fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    if not db_ready():
        return redirect(url_for('setup'))

    db = get_db()
    folders = [r[0] for r in db.execute(
        'SELECT DISTINCT folder FROM files ORDER BY folder').fetchall()]
    categories = [r[0] for r in db.execute(
        'SELECT DISTINCT category FROM instruments ORDER BY category').fetchall()]
    instruments_by_cat = {}
    for cat in categories:
        instruments_by_cat[cat] = [dict(r) for r in db.execute(
            'SELECT id, name, gm_note FROM instruments WHERE category = ? ORDER BY name',
            (cat,)).fetchall()]
    db.close()
    return render_template('index.html', folders=folders, categories=categories,
                           instruments_by_cat=instruments_by_cat)


@app.route('/setup')
def setup():
    config = load_config()
    archive_root = config.get('archive_root', '')
    return render_template('setup.html', archive_root=archive_root,
                           db_exists=db_ready(),
                           indexer_status=indexer_status)


@app.route('/api/setup/validate', methods=['POST'])
def validate_path():
    """Check if a path looks like the MIDI archive."""
    data = request.get_json()
    path = data.get('path', '').strip()

    if not path:
        return jsonify({'valid': False, 'error': 'Please enter a path.'})

    path = os.path.expanduser(path)

    if not os.path.isdir(path):
        return jsonify({'valid': False, 'error': 'Directory not found.'})

    # Auto-detect double-nested archive structure:
    # The zip extracts to folder/folder/, so user might point at either level.
    # If we see only 1-2 subdirs and one matches the parent name, go deeper.
    entries = [e for e in os.listdir(path)
               if os.path.isdir(os.path.join(path, e)) and e != '__MACOSX']
    if len(entries) <= 2:
        for e in entries:
            inner = os.path.join(path, e)
            inner_subs = [s for s in os.listdir(inner)
                          if os.path.isdir(os.path.join(inner, s))]
            if len(inner_subs) > 5:
                # This looks like the real archive root
                path = inner
                break

    # Look for MIDI files
    midi_count = 0
    folders_found = []
    for entry in os.listdir(path):
        entry_path = os.path.join(path, entry)
        if os.path.isdir(entry_path) and entry != '__MACOSX':
            folders_found.append(entry)
            # Quick check: any .mid files in this folder?
            for _, _, files in os.walk(entry_path):
                midi_count += sum(1 for f in files if f.lower().endswith(('.mid', '.midi')))
                if midi_count > 10:
                    break
            if midi_count > 10:
                break

    if midi_count == 0:
        return jsonify({'valid': False,
                        'error': 'No MIDI files found in this directory. '
                                 'Make sure you point to the folder containing '
                                 'the genre subfolders (Jazz, Rock, etc.).'})

    return jsonify({
        'valid': True,
        'resolved_path': path,
        'folders': sorted(folders_found),
        'message': f'Found {len(folders_found)} folders with MIDI files.'
    })


@app.route('/api/setup/start', methods=['POST'])
def start_indexing():
    """Start the indexing process."""
    global indexer_status

    if indexer_status['running']:
        return jsonify({'error': 'Indexer is already running.'}), 409

    data = request.get_json()
    archive_path = os.path.expanduser(data.get('path', '').strip())
    index_all = data.get('index_all', False)

    if not os.path.isdir(archive_path):
        return jsonify({'error': 'Invalid path.'}), 400

    # Save config
    save_config({'archive_root': archive_path})

    # Reset status
    indexer_status = {
        'running': True,
        'progress': 0,
        'total': 0,
        'message': 'Starting...',
        'done': False,
        'error': None,
    }

    # Run indexer in background thread
    def run_indexer():
        try:
            _run_indexer(archive_path, index_all)
        except Exception as e:
            indexer_status['error'] = str(e)
            indexer_status['running'] = False

    thread = threading.Thread(target=run_indexer, daemon=True)
    thread.start()

    return jsonify({'started': True})


def _setup_log():
    """Configure a logger that writes to indexer.log."""
    logger = logging.getLogger('indexer')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s  %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(fh)
    return logger


def _run_indexer(archive_root, index_all):
    """Run the indexer in-process with progress tracking."""
    global indexer_status
    from indexer import init_db, get_indexed_paths, collect_midi_files, \
        build_instrument_lookup, insert_result, _analyze_wrapper
    from multiprocessing import Pool, cpu_count

    log = _setup_log()
    log.info('=' * 60)
    log.info('Indexing started')
    log.info(f'Archive root: {archive_root}')
    log.info(f'Index all: {index_all}')
    start_time = datetime.now()

    indexer_status['message'] = 'Initializing database...'
    conn = init_db(DB_PATH)
    indexed = get_indexed_paths(conn)
    instrument_lookup = build_instrument_lookup(conn)
    log.info(f'Already indexed: {len(indexed)} files')

    indexer_status['message'] = 'Scanning for MIDI files...'

    # Determine folders
    folders = None
    if not index_all:
        exclude = {'GM MIDI Pack [360,000 files]',
                   'Superior Drummer 2 Drum Midi [425,000 files]',
                   '__MACOSX'}
        all_dirs = [d for d in os.listdir(archive_root)
                    if os.path.isdir(os.path.join(archive_root, d))]
        folders = [d for d in all_dirs if d not in exclude]
        log.info(f'Curated folders ({len(folders)}): {", ".join(sorted(folders))}')

    midi_files = collect_midi_files(archive_root, folders)
    to_process = [(f, archive_root) for f in midi_files
                  if os.path.relpath(f, archive_root) not in indexed]

    log.info(f'Found {len(midi_files)} MIDI files, {len(to_process)} new')
    indexer_status['total'] = len(to_process)
    indexer_status['message'] = f'Indexing {len(to_process)} files...'

    if not to_process:
        log.info('Nothing to index')
        indexer_status['message'] = 'All files already indexed.'
        indexer_status['done'] = True
        indexer_status['running'] = False
        conn.close()
        return

    workers = min(cpu_count(), 8)
    results_batch = []
    processed = 0
    failed = 0

    with Pool(workers) as pool:
        for result in pool.imap_unordered(_analyze_wrapper, to_process):
            processed += 1
            indexer_status['progress'] = processed

            if result is not None:
                results_batch.append(result)
            else:
                failed += 1

            if len(results_batch) >= 500:
                for r in results_batch:
                    insert_result(conn, r, instrument_lookup, archive_root)
                conn.commit()
                results_batch.clear()

            if processed % 100 == 0:
                indexer_status['message'] = \
                    f'Indexed {processed} / {len(to_process)} files...'

            if processed % 1000 == 0:
                log.info(f'Progress: {processed} / {len(to_process)}')

    # Insert remaining
    for r in results_batch:
        insert_result(conn, r, instrument_lookup, archive_root)
    conn.commit()

    total = conn.execute('SELECT COUNT(*) FROM files').fetchone()[0]
    elapsed = (datetime.now() - start_time).total_seconds()
    log.info(f'Indexing complete: {total} files in database, '
             f'{failed} files failed to parse, {elapsed:.1f}s elapsed')
    indexer_status['message'] = f'Done! {total} files indexed.'
    indexer_status['done'] = True
    indexer_status['running'] = False
    conn.close()


@app.route('/api/setup/status')
def indexer_progress():
    """Return current indexer status."""
    return jsonify(indexer_status)


@app.route('/api/search')
def search():
    db = get_db()

    conditions = ['1=1']
    params = []

    # Standard instruments filter (default: hide files with unmapped notes)
    standard_only = request.args.get('standard', '1')
    if standard_only == '1':
        conditions.append('f2.has_unmapped_notes = 0')

    # Time signature
    time_sig = request.args.get('time_sig')
    if time_sig and time_sig != 'any':
        conditions.append('f2.time_sig_detected = ?')
        params.append(time_sig)

    # Tempo range
    tempo_min = request.args.get('tempo_min', type=float)
    tempo_max = request.args.get('tempo_max', type=float)
    if tempo_min:
        conditions.append('f2.tempo_bpm >= ?')
        params.append(tempo_min)
    if tempo_max:
        conditions.append('f2.tempo_bpm <= ?')
        params.append(tempo_max)

    # Feel (swing)
    feel = request.args.get('feel')
    if feel == 'straight':
        conditions.append('f2.swing_ratio < 1.15')
    elif feel == 'swing':
        conditions.append('f2.swing_ratio >= 1.15')

    # Type (fill/pattern)
    pattern_type = request.args.get('type')
    if pattern_type == 'fill':
        conditions.append('f2.is_fill = 1')
    elif pattern_type == 'pattern':
        conditions.append('f2.is_fill = 0')

    # Brush
    brush = request.args.get('brush')
    if brush == 'yes':
        conditions.append('f2.is_brush = 1')
    elif brush == 'no':
        conditions.append('f2.is_brush = 0')

    # Folders
    folders = request.args.getlist('folder')
    if folders:
        placeholders = ','.join('?' * len(folders))
        conditions.append(f'f1.folder IN ({placeholders})')
        params.extend(folders)

    # Text search
    q = request.args.get('q', '').strip()
    if q:
        conditions.append('(f1.filename LIKE ? OR f1.path LIKE ?)')
        like = f'%{q}%'
        params.extend([like, like])

    # Must-have instruments (by instrument ID)
    must_have = request.args.getlist('must_have', type=int)
    for inst_id in must_have:
        conditions.append(
            f'EXISTS (SELECT 1 FROM file_instruments fi '
            f'WHERE fi.file_id = f1.id AND fi.instrument_id = ?)'
        )
        params.append(inst_id)

    # Must-not-have instruments
    must_not = request.args.getlist('must_not', type=int)
    for inst_id in must_not:
        conditions.append(
            f'NOT EXISTS (SELECT 1 FROM file_instruments fi '
            f'WHERE fi.file_id = f1.id AND fi.instrument_id = ?)'
        )
        params.append(inst_id)

    # Must-have instrument categories
    must_have_cat = request.args.getlist('must_have_cat')
    for cat in must_have_cat:
        conditions.append(
            f'EXISTS (SELECT 1 FROM file_instruments fi '
            f'JOIN instruments i ON fi.instrument_id = i.id '
            f'WHERE fi.file_id = f1.id AND i.category = ?)'
        )
        params.append(cat)

    # Must-not-have instrument categories
    must_not_cat = request.args.getlist('must_not_cat')
    for cat in must_not_cat:
        conditions.append(
            f'NOT EXISTS (SELECT 1 FROM file_instruments fi '
            f'JOIN instruments i ON fi.instrument_id = i.id '
            f'WHERE fi.file_id = f1.id AND i.category = ?)'
        )
        params.append(cat)

    # Beat pattern search using precomputed bitmask signatures.
    # Each basic kit instrument has a 16-bit mask in beat_signature where
    # bit N corresponds to grid slot N (0="1", 1="1e", 2="1+", ..., 15="4a").
    beat_selections = {}
    for key, val in request.args.items(multi=True):
        if key.startswith('beat_') and val:
            instrument = key[5:]  # e.g. "kick", "snare"
            beat_selections.setdefault(instrument, []).append(val.strip())

    slot_to_bit = {
        '1': 0, '1e': 1, '1+': 2, '1a': 3,
        '2': 4, '2e': 5, '2+': 6, '2a': 7,
        '3': 8, '3e': 9, '3+': 10, '3a': 11,
        '4': 12, '4e': 13, '4+': 14, '4a': 15,
    }

    beat_joins = []
    beat_join_params = []
    for i, (instrument, slots) in enumerate(beat_selections.items()):
        required_mask = 0
        for slot in slots:
            bit = slot_to_bit.get(slot)
            if bit is not None:
                required_mask |= (1 << bit)
        disallowed_mask = 0xFFFF & ~required_mask
        alias = f'bs{i}'
        beat_joins.append(
            f'JOIN beat_signature {alias} ON {alias}.file_id = f1.id '
            f'AND {alias}.instrument = ? '
            f'AND {alias}.mask & ? = ? AND {alias}.mask & ? = 0'
        )
        beat_join_params.extend([instrument, required_mask, required_mask, disallowed_mask])

    # Sort
    sort = request.args.get('sort', 'tempo')
    sort_map = {
        'tempo': 'f2.tempo_bpm',
        'density': 'f2.note_density DESC',
        'folder': 'f1.folder, f1.filename',
        'name': 'f1.filename',
        'length': 'f2.pattern_length_beats',
    }
    order_by = sort_map.get(sort, 'f2.tempo_bpm')

    where = ' AND '.join(conditions)
    beat_join_clause = '\n        '.join(beat_joins)
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    # Params order: beat_join_params (for JOINs), then params (for WHERE), then limit/offset
    all_params = beat_join_params + params

    sql = f'''
        SELECT f1.id, f1.path, f1.filename, f1.folder, f1.subfolder,
               f1.num_notes, f2.time_sig_detected as time_sig,
               f2.tempo_bpm, f2.swing_ratio, f2.note_density,
               f2.is_fill, f2.is_brush, f2.pattern_length_beats
        FROM files f1
        JOIN features f2 ON f1.id = f2.file_id
        {beat_join_clause}
        WHERE {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    '''

    rows = db.execute(sql, all_params + [limit, offset]).fetchall()

    # Get total count
    count_sql = f'''
        SELECT COUNT(*) FROM files f1
        JOIN features f2 ON f1.id = f2.file_id
        {beat_join_clause}
        WHERE {where}
    '''
    total = db.execute(count_sql, all_params).fetchone()[0]

    results = []
    for row in rows:
        r = dict(row)
        # Get instruments for this file
        insts = db.execute('''
            SELECT i.name, i.category, fi.hit_count
            FROM file_instruments fi
            JOIN instruments i ON fi.instrument_id = i.id
            WHERE fi.file_id = ?
            ORDER BY fi.hit_count DESC
        ''', (row['id'],)).fetchall()
        r['instruments'] = [{'name': i['name'], 'category': i['category'],
                             'hits': i['hit_count']} for i in insts]
        results.append(r)

    db.close()
    return jsonify({'results': results, 'total': total,
                    'limit': limit, 'offset': offset})


@app.route('/api/file/<int:file_id>/grid')
def beat_grid(file_id):
    """Return beat grid data for a specific file."""
    db = get_db()
    rows = db.execute(
        'SELECT instrument, beat_position, velocity, grid_slot '
        'FROM beat_grid WHERE file_id = ? ORDER BY beat_position',
        (file_id,)
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/midi/<int:file_id>')
def serve_midi(file_id):
    """Serve a MIDI file for playback."""
    db = get_db()
    row = db.execute('SELECT path, archive_root FROM files WHERE id = ?',
                     (file_id,)).fetchone()
    db.close()
    if not row:
        return 'Not found', 404
    # Use per-file archive_root if available, fall back to config
    archive_root = row['archive_root'] or get_archive_root()
    if not archive_root:
        return 'Archive not configured', 500
    full_path = os.path.join(archive_root, row['path'])
    if not os.path.isfile(full_path):
        return 'File not found', 404
    # Ensure the resolved path is within the archive root
    real_path = os.path.realpath(full_path)
    real_root = os.path.realpath(archive_root)
    if not real_path.startswith(real_root):
        return 'Forbidden', 403
    return send_file(real_path, mimetype='audio/midi')


@app.route('/api/stats')
def stats():
    """Return database statistics."""
    db = get_db()
    total_files = db.execute('SELECT COUNT(*) FROM files').fetchone()[0]
    folders = db.execute(
        'SELECT folder, COUNT(*) as cnt FROM files GROUP BY folder ORDER BY cnt DESC'
    ).fetchall()
    time_sigs = db.execute(
        'SELECT time_sig_detected, COUNT(*) as cnt FROM features '
        'GROUP BY time_sig_detected ORDER BY cnt DESC'
    ).fetchall()
    db.close()
    return jsonify({
        'total_files': total_files,
        'folders': [{'name': r[0], 'count': r[1]} for r in folders],
        'time_signatures': [{'sig': r[0], 'count': r[1]} for r in time_sigs],
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
