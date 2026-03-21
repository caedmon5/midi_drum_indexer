#!/usr/bin/env python3
"""Flask web app for searching and playing MIDI drum patterns."""

import os
import sqlite3
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'drums.db')
ARCHIVE_ROOT = os.path.expanduser(
    '~/Dropbox/Music/drumMidi/'
    '800000_Drum_Percussion_MIDI_Archive[6_19_15]/'
    '800000_Drum_Percussion_MIDI_Archive[6_19_15]'
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
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


@app.route('/api/search')
def search():
    db = get_db()

    conditions = ['1=1']
    params = []

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

    # Beat pattern search: e.g. beat_kick=1,3 means kick on beats 1 and 3
    for key, val in request.args.items():
        if key.startswith('beat_') and val:
            instrument = key[5:]  # e.g. "kick", "snare"
            slots = [s.strip() for s in val.split(',')]
            for slot in slots:
                conditions.append(
                    f'EXISTS (SELECT 1 FROM beat_grid bg '
                    f'WHERE bg.file_id = f1.id AND bg.instrument = ? '
                    f'AND bg.grid_slot = ?)'
                )
                params.extend([instrument, slot])

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
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    sql = f'''
        SELECT f1.id, f1.path, f1.filename, f1.folder, f1.subfolder,
               f1.num_notes, f2.time_sig_detected as time_sig,
               f2.tempo_bpm, f2.swing_ratio, f2.note_density,
               f2.is_fill, f2.is_brush, f2.pattern_length_beats
        FROM files f1
        JOIN features f2 ON f1.id = f2.file_id
        WHERE {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    '''
    params.extend([limit, offset])

    rows = db.execute(sql, params).fetchall()

    # Get total count
    count_sql = f'''
        SELECT COUNT(*) FROM files f1
        JOIN features f2 ON f1.id = f2.file_id
        WHERE {where}
    '''
    total = db.execute(count_sql, params[:-2]).fetchone()[0]

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
    row = db.execute('SELECT path FROM files WHERE id = ?', (file_id,)).fetchone()
    db.close()
    if not row:
        return 'Not found', 404
    full_path = os.path.join(ARCHIVE_ROOT, row['path'])
    if not os.path.isfile(full_path):
        return 'File not found', 404
    # Ensure the resolved path is within the archive root
    real_path = os.path.realpath(full_path)
    real_root = os.path.realpath(ARCHIVE_ROOT)
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
