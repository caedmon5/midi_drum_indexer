# MIDI Drum Indexer

A search tool for the [800,000 Drum Percussion MIDI Archive](https://archive.org/details/800000_Drum_Percussion_MIDI_Archive6_19_15) — the well-known collection of MIDI drum patterns originally shared on music production forums.

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

Results can be auditioned directly in the browser using synthesized drum sounds (Tone.js). No external samples required. Playback supports looping and tempo adjustment.

## Getting started

### 1. Get the MIDI archive

Download the [800,000 Drum Percussion MIDI Archive](https://archive.org/details/800000_Drum_Percussion_MIDI_Archive6_19_15) from the Internet Archive. It's a single zip file (~1.5 GB). Unzip it somewhere on your machine — you'll end up with a folder structure like:

```
800000_Drum_Percussion_MIDI_Archive[6_19_15]/
├── Africa/
├── Blues Drums/
├── Bossa/
├── Funk Drums/
├── Jazz/
├── Rock:Indie/
├── GM MIDI Pack [360,000 files]/
├── Superior Drummer 2 Drum Midi [425,000 files]/
└── ... (47 genre folders total)
```

### 2. Clone this repo and install dependencies

```bash
git clone https://github.com/caedmon5/midi_drum_indexer.git
cd midi_drum_indexer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Build the database

Point the indexer at the top-level archive folder (the one containing the genre subfolders):

```bash
python3 indexer.py --archive /path/to/800000_Drum_Percussion_MIDI_Archive[6_19_15]
```

This indexes the curated genre folders (~19k files) and takes about 15 seconds. A `drums.db` file will be created in the project directory.

The two massive collections (GM MIDI Pack at 360k files and Superior Drummer 2 at 425k files) are skipped by default. To index everything:

```bash
python3 indexer.py --archive /path/to/archive --all
```

To index only specific folders:

```bash
python3 indexer.py --archive /path/to/archive --folders "Jazz,Blues Drums,Bossa,Rock:Indie"
```

The indexer is idempotent — re-running it skips files already in the database.

### 4. Run the web UI

```bash
python3 app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser. You'll see the search interface with filters on the left and results on the right. Click the play button on any result to audition it.

## Architecture

| File | Purpose |
|------|---------|
| `indexer.py` | Walks the archive, processes files in parallel, writes to SQLite |
| `analyzer.py` | MIDI parser and feature extraction (time sig detection, swing analysis, beat grid quantization) |
| `app.py` | Flask web app with search API and MIDI file serving |
| `schema.sql` | Database schema (5 tables) and GM percussion instrument seed data |
| `templates/index.html` | Search UI with filters, beat grid editor, results table |
| `static/player.js` | Tone.js drum synthesizer and MIDI playback engine |
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
