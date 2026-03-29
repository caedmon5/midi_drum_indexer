CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    folder TEXT,
    subfolder TEXT,
    file_size INTEGER,
    midi_type INTEGER,
    ticks_per_beat INTEGER,
    duration_sec REAL,
    num_notes INTEGER
);

CREATE TABLE IF NOT EXISTS features (
    file_id INTEGER PRIMARY KEY REFERENCES files(id),
    time_sig_stated TEXT,
    time_sig_detected TEXT,
    tempo_bpm REAL,
    pattern_length_beats REAL,
    swing_ratio REAL,
    note_density REAL,
    is_fill BOOLEAN DEFAULT 0,
    is_brush BOOLEAN DEFAULT 0,
    has_unmapped_notes BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    gm_note INTEGER
);

CREATE TABLE IF NOT EXISTS file_instruments (
    file_id INTEGER REFERENCES files(id),
    instrument_id INTEGER REFERENCES instruments(id),
    hit_count INTEGER,
    PRIMARY KEY (file_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS beat_grid (
    file_id INTEGER REFERENCES files(id),
    instrument TEXT NOT NULL,
    beat_position REAL NOT NULL,
    velocity INTEGER,
    grid_slot TEXT
);

CREATE INDEX IF NOT EXISTS idx_features_time_sig ON features(time_sig_detected);
CREATE INDEX IF NOT EXISTS idx_features_tempo ON features(tempo_bpm);
CREATE INDEX IF NOT EXISTS idx_features_swing ON features(swing_ratio);
CREATE INDEX IF NOT EXISTS idx_features_fill ON features(is_fill);
CREATE INDEX IF NOT EXISTS idx_features_brush ON features(is_brush);
CREATE INDEX IF NOT EXISTS idx_file_instruments_instrument ON file_instruments(instrument_id);
CREATE INDEX IF NOT EXISTS idx_beat_grid_file ON beat_grid(file_id);
CREATE INDEX IF NOT EXISTS idx_beat_grid_instrument ON beat_grid(instrument);
CREATE INDEX IF NOT EXISTS idx_beat_grid_slot ON beat_grid(grid_slot);
CREATE INDEX IF NOT EXISTS idx_beat_grid_composite ON beat_grid(file_id, instrument, grid_slot);

-- Precomputed bitmask for beat pattern search on basic kit instruments.
-- Each row stores a 16-bit mask encoding which grid slots have hits in bar 1.
-- Bit 0 = slot "1", bit 1 = "1e", bit 2 = "1+", ..., bit 15 = "4a".
CREATE TABLE IF NOT EXISTS beat_signature (
    file_id INTEGER REFERENCES files(id),
    instrument TEXT NOT NULL,
    mask INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (file_id, instrument)
);
CREATE INDEX IF NOT EXISTS idx_beat_sig_inst_mask ON beat_signature(instrument, mask);
CREATE INDEX IF NOT EXISTS idx_files_folder ON files(folder);

-- Seed instrument catalog
INSERT OR IGNORE INTO instruments (name, category, gm_note) VALUES
    ('acoustic_bass_drum', 'Kick', 35),
    ('bass_drum', 'Kick', 36),
    ('side_stick', 'Snare', 37),
    ('acoustic_snare', 'Snare', 38),
    ('hand_clap', 'Claps/FX', 39),
    ('electric_snare', 'Snare', 40),
    ('low_floor_tom', 'Toms', 41),
    ('closed_hihat', 'Hi-Hat', 42),
    ('high_floor_tom', 'Toms', 43),
    ('pedal_hihat', 'Hi-Hat', 44),
    ('low_tom', 'Toms', 45),
    ('open_hihat', 'Hi-Hat', 46),
    ('low_mid_tom', 'Toms', 47),
    ('hi_mid_tom', 'Toms', 48),
    ('crash_1', 'Crash', 49),
    ('high_tom', 'Toms', 50),
    ('ride_1', 'Ride', 51),
    ('chinese_cymbal', 'Crash', 52),
    ('ride_bell', 'Ride', 53),
    ('tambourine', 'Shakers', 54),
    ('splash', 'Crash', 55),
    ('cowbell', 'Cowbell/Blocks', 56),
    ('crash_2', 'Crash', 57),
    ('vibraslap', 'Claps/FX', 58),
    ('ride_2', 'Ride', 59),
    ('hi_bongo', 'Latin', 60),
    ('lo_bongo', 'Latin', 61),
    ('mute_hi_conga', 'Latin', 62),
    ('open_hi_conga', 'Latin', 63),
    ('low_conga', 'Latin', 64),
    ('hi_timbale', 'Latin', 65),
    ('lo_timbale', 'Latin', 66),
    ('hi_agogo', 'Latin', 67),
    ('lo_agogo', 'Latin', 68),
    ('cabasa', 'Shakers', 69),
    ('maracas', 'Shakers', 70),
    ('short_whistle', 'Whistles', 71),
    ('long_whistle', 'Whistles', 72),
    ('short_guiro', 'Shakers', 73),
    ('long_guiro', 'Shakers', 74),
    ('claves', 'Cowbell/Blocks', 75),
    ('hi_wood_block', 'Cowbell/Blocks', 76),
    ('lo_wood_block', 'Cowbell/Blocks', 77),
    ('mute_cuica', 'Latin', 78),
    ('open_cuica', 'Latin', 79),
    ('mute_triangle', 'Bells/Metal', 80),
    ('open_triangle', 'Bells/Metal', 81),
    ('shaker', 'Shakers', 82),
    ('jingle_bell', 'Bells/Metal', 83),
    ('bell_tree', 'Bells/Metal', 84),
    ('castanets', 'Bells/Metal', 85),
    ('mute_surdo', 'Latin', 86),
    ('open_surdo', 'Latin', 87);
