/**
 * MIDI Drum Player using Tone.js
 * Parses MIDI files client-side with @tonejs/midi and plays with sample-based drums.
 */

// GM drum note to sample file mapping
const GM_DRUM_SAMPLES = {
    35: 'kick', 36: 'kick',
    37: 'side_stick', 38: 'snare', 40: 'snare',
    39: 'clap',
    41: 'tom_low_floor', 42: 'hihat_closed', 43: 'tom_hi_floor',
    44: 'hihat_pedal', 45: 'tom_low', 46: 'hihat_open',
    47: 'tom_low_mid', 48: 'tom_hi_mid',
    49: 'crash', 50: 'tom_high',
    51: 'ride', 52: 'crash', 53: 'ride_bell',
    54: 'tambourine', 55: 'splash', 56: 'cowbell',
    57: 'crash', 58: 'vibraslap', 59: 'ride',
    60: 'hi_bongo', 61: 'lo_bongo',
    62: 'mute_hi_conga', 63: 'open_hi_conga', 64: 'low_conga',
    65: 'hi_timbale', 66: 'lo_timbale',
    67: 'hi_agogo', 68: 'lo_agogo',
    69: 'cabasa', 70: 'maracas',
    71: 'short_whistle', 72: 'long_whistle',
    73: 'short_guiro', 74: 'long_guiro',
    75: 'claves', 76: 'hi_wood_block', 77: 'lo_wood_block',
    78: 'mute_cuica', 79: 'open_cuica',
    80: 'mute_triangle', 81: 'open_triangle',
    82: 'shaker', 83: 'jingle_bell', 84: 'bell_tree',
    85: 'castanets', 86: 'mute_surdo', 87: 'open_surdo',
};

// All unique sample names
const SAMPLE_NAMES = [...new Set(Object.values(GM_DRUM_SAMPLES))];

class DrumSampler {
    constructor() {
        this.ready = false;
        this.players = {};
        this.gainNodes = {};
    }

    async init() {
        if (this.ready) return;
        await Tone.start();

        // Load all samples
        const loadPromises = SAMPLE_NAMES.map(name => {
            return new Promise((resolve) => {
                const p = new Tone.Player({
                    url: `/static/samples/${name}.mp3`,
                    onload: () => resolve(),
                    onerror: () => {
                        console.warn(`Failed to load sample: ${name}`);
                        resolve();
                    }
                });
                const gain = new Tone.Gain(1).toDestination();
                p.connect(gain);
                this.players[name] = p;
                this.gainNodes[name] = gain;
            });
        });

        await Promise.all(loadPromises);
        this.ready = true;
        console.log(`Loaded ${Object.keys(this.players).length} drum samples`);
    }

    trigger(name, velocity = 100, time) {
        const p = this.players[name];
        if (!p || !p.loaded) return;

        const vel = Math.min(1, velocity / 127);
        this.gainNodes[name].gain.setValueAtTime(vel, time);

        // Stop any currently playing instance of this sample to prevent overlap buildup
        try { p.stop(time); } catch(e) {}
        p.start(time);
    }
}

// Player state
const player = {
    drumSampler: new DrumSampler(),
    midi: null,
    fileId: null,
    playing: false,
    looping: true,
    scheduledEvents: [],
    tempo: 120,
    originalTempo: 120,
};

async function loadAndPlay(fileId, filename, tempoHint) {
    // Show loading state
    const playerBar = document.getElementById('player-bar');
    playerBar.classList.add('active');
    document.body.classList.add('player-visible');
    document.getElementById('player-filename').textContent = 'Loading...';

    await player.drumSampler.init();
    stopPlayback();

    player.fileId = fileId;
    player.originalTempo = tempoHint || 120;
    player.tempo = tempoHint || 120;

    // Fetch MIDI file
    const response = await fetch(`/api/midi/${fileId}`);
    if (!response.ok) {
        console.error('Failed to fetch MIDI file');
        return;
    }
    const arrayBuffer = await response.arrayBuffer();

    // Parse with @tonejs/midi
    player.midi = new Midi(arrayBuffer);

    // Update UI
    document.getElementById('player-filename').textContent = filename;
    document.getElementById('player-tempo').value = Math.round(player.tempo);
    document.getElementById('player-tempo-display').textContent = Math.round(player.tempo);

    startPlayback();
}

function startPlayback() {
    if (!player.midi) return;

    player.playing = true;
    document.getElementById('btn-play').textContent = 'Pause';

    Tone.getTransport().cancel();
    Tone.getTransport().bpm.value = player.tempo;

    const notes = [];
    for (const track of player.midi.tracks) {
        for (const note of track.notes) {
            notes.push({
                time: note.time,
                midi: note.midi,
                velocity: note.velocity * 127,
            });
        }
    }

    // Find pattern duration
    const maxTime = notes.reduce((max, n) => Math.max(max, n.time), 0);
    const patternDuration = maxTime + 0.01;

    // Schedule notes
    const part = new Tone.Part((time, event) => {
        const sampleName = GM_DRUM_SAMPLES[event.midi];
        if (sampleName) {
            player.drumSampler.trigger(sampleName, event.velocity, time);
        }
    }, notes.map(n => [n.time, n]));

    part.loop = player.looping;
    part.loopEnd = patternDuration;
    part.start(0);

    Tone.getTransport().start();
}

function stopPlayback() {
    player.playing = false;
    Tone.getTransport().stop();
    Tone.getTransport().cancel();
    document.getElementById('btn-play').textContent = 'Play';
}

function togglePlayback() {
    if (player.playing) {
        stopPlayback();
    } else {
        startPlayback();
    }
}

function setTempo(bpm) {
    player.tempo = parseFloat(bpm);
    document.getElementById('player-tempo-display').textContent = Math.round(player.tempo);
    if (player.playing) {
        Tone.getTransport().bpm.value = player.tempo;
    }
}

function closePlayer() {
    stopPlayback();
    document.getElementById('player-bar').classList.remove('active');
    document.body.classList.remove('player-visible');
}

// Search functionality
let searchTimeout = null;
let searchController = null;

function doSearch(resetOffset = true) {
    if (resetOffset) {
        currentOffset = 0;
    }

    // Cancel any in-flight search request
    if (searchController) {
        searchController.abort();
    }
    searchController = new AbortController();

    const params = new URLSearchParams();

    // Time signature
    const timeSig = document.getElementById('time-sig').value;
    if (timeSig !== 'any') params.set('time_sig', timeSig);

    // Tempo
    const tempoMin = document.getElementById('tempo-min').value;
    const tempoMax = document.getElementById('tempo-max').value;
    if (tempoMin) params.set('tempo_min', tempoMin);
    if (tempoMax) params.set('tempo_max', tempoMax);

    // Feel
    const feel = document.getElementById('feel').value;
    if (feel !== 'any') params.set('feel', feel);

    // Type
    const type = document.getElementById('pattern-type').value;
    if (type !== 'any') params.set('type', type);

    // Brush
    const brush = document.getElementById('brush-filter').value;
    if (brush !== 'any') params.set('brush', brush);

    // Standard instruments only
    const standardOnly = document.getElementById('standard-only').checked;
    params.set('standard', standardOnly ? '1' : '0');

    // Folders
    document.querySelectorAll('.folder-cb:checked').forEach(cb => {
        params.append('folder', cb.value);
    });

    // Text search
    const q = document.getElementById('text-search').value.trim();
    if (q) params.set('q', q);

    // Instrument filters (tri-state)
    document.querySelectorAll('.inst-filter').forEach(el => {
        const state = el.dataset.state;
        const id = el.dataset.instId;
        if (state === 'must-have') params.append('must_have', id);
        else if (state === 'must-not') params.append('must_not', id);
    });

    // Category filters
    document.querySelectorAll('.cat-filter').forEach(el => {
        const state = el.dataset.state;
        const cat = el.dataset.cat;
        if (state === 'must-have') params.append('must_have_cat', cat);
        else if (state === 'must-not') params.append('must_not_cat', cat);
    });

    // Beat pattern
    document.querySelectorAll('.beat-cell.active').forEach(cell => {
        const inst = cell.dataset.instrument;
        const slot = cell.dataset.slot;
        params.append(`beat_${inst}`, slot);
    });

    // Sort
    const sort = document.getElementById('sort-by').value;
    params.set('sort', sort);

    params.set('limit', 100);
    params.set('offset', currentOffset);

    // Show loading state
    document.getElementById('result-count').textContent = 'Searching...';

    const signal = searchController.signal;
    fetch('/api/search?' + params.toString(), { signal })
        .then(r => r.json())
        .then(data => renderResults(data))
        .catch(err => {
            if (err.name !== 'AbortError') throw err;
        });
}

let currentOffset = 0;

function renderResults(data) {
    const tbody = document.getElementById('results-body');
    const countEl = document.getElementById('result-count');

    countEl.textContent = `${data.total} results`;

    if (data.results.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:#666">No matching patterns found</td></tr>';
        return;
    }

    tbody.innerHTML = data.results.map(r => {
        const instTags = r.instruments.slice(0, 6).map(i => {
            const cat = getCatClass(i.category);
            return `<span class="inst-tag ${cat}">${i.name.replace(/_/g, ' ')}</span>`;
        }).join('');

        const feel = r.swing_ratio >= 1.15 ? 'swing' : 'straight';

        return `<tr onclick="selectRow(this, ${r.id}, '${escapeHtml(r.filename)}', ${r.tempo_bpm})">
            <td><button class="play-btn" onclick="event.stopPropagation(); loadAndPlay(${r.id}, '${escapeHtml(r.filename)}', ${r.tempo_bpm})">\u25B6</button></td>
            <td title="${escapeHtml(r.path)}">${escapeHtml(r.filename)}</td>
            <td>${r.time_sig}</td>
            <td>${Math.round(r.tempo_bpm)}</td>
            <td>${feel}</td>
            <td><div class="instruments-cell">${instTags}</div></td>
            <td>${r.folder}</td>
        </tr>`;
    }).join('');

    // Pagination
    const pagination = document.getElementById('pagination');
    const pages = Math.ceil(data.total / data.limit);
    const currentPage = Math.floor(data.offset / data.limit) + 1;
    if (pages > 1) {
        let html = '';
        if (currentPage > 1) html += `<button class="secondary" onclick="goToPage(${currentPage - 1})">Prev</button>`;
        html += `<span style="color:#888">Page ${currentPage} of ${pages}</span>`;
        if (currentPage < pages) html += `<button class="secondary" onclick="goToPage(${currentPage + 1})">Next</button>`;
        pagination.innerHTML = html;
    } else {
        pagination.innerHTML = '';
    }
}

function goToPage(page) {
    currentOffset = (page - 1) * 100;
    doSearch(false);
}

function selectRow(tr, fileId, filename, tempo) {
    // If clicking the already-selected row, toggle it closed
    if (tr.classList.contains('selected')) {
        tr.classList.remove('selected');
        document.querySelectorAll('.grid-detail-row').forEach(r => r.remove());
        return;
    }

    // Remove previous selection and grid detail rows
    document.querySelectorAll('.results-table tr.selected').forEach(r => r.classList.remove('selected'));
    document.querySelectorAll('.grid-detail-row').forEach(r => r.remove());

    tr.classList.add('selected');

    // Fetch and show beat grid visualization
    fetch(`/api/file/${fileId}/grid`)
        .then(r => r.json())
        .then(grid => {
            const detailRow = document.createElement('tr');
            detailRow.className = 'grid-detail-row';
            const td = document.createElement('td');
            td.colSpan = 7;
            td.innerHTML = renderBeatGrid(grid);
            detailRow.appendChild(td);
            tr.after(detailRow);
        });
}

function renderBeatGrid(grid) {
    if (!grid.length) return '<div style="padding:0.5rem;color:#666">No beat data</div>';

    // Find all instruments and max beat
    const instruments = [];
    const instSet = new Set();
    let maxBeat = 4;
    for (const hit of grid) {
        if (!instSet.has(hit.instrument)) {
            instSet.add(hit.instrument);
            instruments.push(hit.instrument);
        }
        const beatNum = parseInt(hit.grid_slot);
        if (beatNum > maxBeat) maxBeat = beatNum;
    }

    // Preferred instrument order
    const instOrder = ['kick', 'snare', 'hihat_closed', 'hihat_pedal', 'hihat_open', 'ride', 'ride_bell', 'crash'];
    instruments.sort((a, b) => {
        const ai = instOrder.indexOf(a);
        const bi = instOrder.indexOf(b);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });

    // Cap display at 2 bars (8 beats) for readability
    const displayBeats = Math.min(maxBeat, 8);

    // Build slot headers
    const suffixes = ['', 'e', '+', 'a'];
    const slots = [];
    for (let b = 1; b <= displayBeats; b++) {
        for (const s of suffixes) {
            slots.push(`${b}${s}`);
        }
    }

    // Build hit lookup: instrument -> set of grid_slots
    const hits = {};
    for (const h of grid) {
        if (!hits[h.instrument]) hits[h.instrument] = {};
        hits[h.instrument][h.grid_slot] = h.velocity;
    }

    // Render table
    let html = '<div class="grid-detail"><table class="beat-grid-display"><thead><tr><th></th>';
    for (let b = 1; b <= displayBeats; b++) {
        html += `<th class="beat-marker">${b}</th><th></th><th></th><th></th>`;
    }
    html += '</tr></thead><tbody>';

    const instLabels = {
        'kick': 'KK', 'snare': 'SN', 'hihat_closed': 'HH', 'hihat_pedal': 'HP',
        'hihat_open': 'HO', 'ride': 'RD', 'ride_bell': 'RB', 'crash': 'CR',
    };

    for (const inst of instruments) {
        html += `<tr><th>${instLabels[inst] || inst.substring(0, 3).toUpperCase()}</th>`;
        for (const slot of slots) {
            const vel = hits[inst] && hits[inst][slot];
            if (vel) {
                const opacity = Math.max(0.4, vel / 127);
                html += `<td class="grid-hit" style="opacity:${opacity}"></td>`;
            } else {
                html += `<td class="grid-empty"></td>`;
            }
        }
        html += '</tr>';
    }

    html += '</tbody></table></div>';
    return html;
}

function getCatClass(category) {
    const map = {
        'Kick': 'kick', 'Snare': 'snare', 'Hi-Hat': 'hihat',
        'Ride': 'ride', 'Crash': 'crash', 'Toms': 'toms', 'Latin': 'latin'
    };
    return map[category] || '';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/'/g, "\\'");
}

// Tri-state toggle for instrument/category filters
function cycleTriState(el) {
    const states = ['any', 'must-have', 'must-not'];
    const current = el.dataset.state || 'any';
    const next = states[(states.indexOf(current) + 1) % states.length];
    el.dataset.state = next;
    el.className = el.className.replace(/\b(must-have|must-not)\b/g, '').trim();
    if (next !== 'any') el.classList.add(next);
    el.classList.add('tri-state');
    debouncedSearch();
}

// Beat grid editor toggle
function toggleBeatCell(td) {
    td.classList.toggle('active');
    debouncedSearch();
}

function debouncedSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => doSearch(), 300);
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    // Bind search controls
    document.querySelectorAll('#time-sig, #feel, #pattern-type, #brush-filter, #sort-by, #standard-only').forEach(el => {
        el.addEventListener('change', () => doSearch());
    });
    document.querySelectorAll('#tempo-min, #tempo-max').forEach(el => {
        el.addEventListener('change', () => doSearch());
    });
    document.getElementById('text-search').addEventListener('input', debouncedSearch);

    // Folder checkboxes
    document.querySelectorAll('.folder-cb').forEach(cb => {
        cb.addEventListener('change', () => doSearch());
    });

    // Initial search
    doSearch();
});
