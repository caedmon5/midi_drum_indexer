# MIDI Drum Indexer

A search tool for the [800,000 Drum Percussion MIDI Archive](https://www.reddit.com/r/WeAreTheMusicMakers/comments/3anwu8/the_drum_percussion_midi_archive_800k/) — the well-known collection of MIDI drum patterns originally shared on music production forums.

The archive contains ~764k MIDI files organized in folders by genre, but with inconsistent naming and no searchable index. This tool parses every file, extracts musical features, stores them in a SQLite database, and provides a browser-based UI to search, filter, and audition patterns instantly.

## What it does

- **Indexes MIDI drum files** — extracts time signature, tempo, swing feel, instruments used, and beat positions from each file
- **Detects time signatures from the music itself** rather than trusting MIDI metadata (which is often wrong — e.g. waltz patterns marked as 4/4)
- **Extracts tempo from filenames** when encoded (common pattern: `120_RockBeat.mid`)
- **Identifies instruments** using the General MIDI percussion map (58 unique drum notes across 13 categories)
- **Builds a searchable beat grid** — every note quantized to a 16th-note grid slot

## Search features

- **Time signature** — filter by detected meter (4/4, 3/4, 6/8, 5/4, 7/8)
- **Tempo range** — min/max BPM slider
- **Feel** — straight or swing
- **Genre** — filter by archive folder (Jazz, Rock, Latin, Funk, Blues, etc.)
- **Instruments** — tri-state filters (must have / must not have / don't care) at both category and individual instrument level
- **Beat pattern** — clickable 16th-note grid: specify "kick on 1 and 3, snare on 2 and 4" and find every pattern that matches
- **Type** — pattern vs. fill
- **Text search** — filename and path substring matching

## In-browser playback

Results can be auditioned directly in the browser using bundled drum samples (48 instruments, ~290KB total) played back via Tone.js. Covers the full GM percussion map including kit drums, Latin percussion, shakers, bells, and more. Playback supports looping and tempo adjustment.

## Getting started

### 1. Download the MIDI archive

Download the [800,000 Drum Percussion MIDI Archive](https://mega.nz/file/ZxgAAIZB#oMYIyy7iLYtnpnwRsKOuVRttOVrAHdQ2-DqPil2s7Lc). It's a single zip file (~1.5 GB). Unzip it somewhere on your machine.

### 2. Clone this repo and install dependencies

```bash
git clone https://github.com/caedmon5/midi_drum_indexer.git
cd midi_drum_indexer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run the app

```bash
python3 app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser. On first run you'll be taken to a setup page that walks you through pointing the tool at your archive and building the database. The curated genre folders (~19k files) index in about 15 seconds.

### Command-line indexing (optional)

You can also build the database from the command line if you prefer:

```bash
python3 indexer.py --archive /path/to/800000_Drum_Percussion_MIDI_Archive[6_19_15]
```

The two massive collections (GM MIDI Pack at 360k files and Superior Drummer 2 at 425k files) are skipped by default. To index everything, pass `--all`. To index specific folders: `--folders "Jazz,Blues Drums,Bossa"`.

The indexer is idempotent — re-running it skips files already in the database.

## Architecture

| File | Purpose |
|------|---------|
| `indexer.py` | Walks the archive, processes files in parallel, writes to SQLite |
| `analyzer.py` | MIDI parser and feature extraction (time sig detection, swing analysis, beat grid quantization) |
| `app.py` | Flask web app with search API, MIDI file serving, and setup wizard |
| `schema.sql` | Database schema (5 tables) and GM percussion instrument seed data |
| `generate_samples.py` | Generates the bundled drum sample mp3s via numpy synthesis |
| `templates/setup.html` | First-run setup wizard (archive path, database build with progress) |
| `templates/index.html` | Search UI with filters, beat grid editor, results table |
| `static/player.js` | Tone.js sample-based MIDI playback engine |
| `static/samples/` | 48 drum sample mp3s (~290KB total) |
| `static/style.css` | Dark theme responsive layout |

## Known limitations

- **Time signature detection is heuristic** — it infers meter from pattern length and folder name hints, which works well for clear cases but can misclassify ambiguous patterns (e.g. a 4-beat pattern from a waltz folder vs. a true 4/4 pattern)
- **Swing detection** relies on hi-hat/ride spacing and may be inaccurate for patterns without a steady timekeeping instrument
- **Brush kit note mappings** (Vintage/Studio/Modern Drummer) use non-standard MIDI notes (81-92) that can't be decoded from GM alone — these are tagged by filename only
- **Tempo from MIDI metadata** defaults to 120 BPM when no tempo event is present, which is the MIDI standard default but often not the intended tempo

## Tech stack

Python 3, mido, SQLite, Flask, Tone.js, @tonejs/midi. No build step — vanilla JS and Jinja templates.

## License

This tool is for indexing and searching MIDI files you already have. The MIDI archive itself has its own distribution terms.
