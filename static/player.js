/**
 * MIDI Drum Player using Tone.js
 * Parses MIDI files client-side with @tonejs/midi and plays with sampled drums.
 */

// GM drum note to sample mapping
const GM_DRUM_SAMPLES = {
    35: 'kick', 36: 'kick',
    37: 'stick', 38: 'snare', 40: 'snare',
    39: 'clap',
    41: 'tom_low', 43: 'tom_low',
    42: 'hihat_closed', 44: 'hihat_closed',
    45: 'tom_mid', 47: 'tom_mid', 48: 'tom_mid',
    46: 'hihat_open',
    49: 'crash', 52: 'crash', 55: 'crash', 57: 'crash',
    50: 'tom_high',
    51: 'ride', 53: 'ride', 59: 'ride',
    54: 'tambourine',
    56: 'cowbell',
};

// Simple synthesized drum sounds (no external samples needed)
class DrumSynth {
    constructor() {
        this.ready = false;
        this.synths = {};
    }

    async init() {
        if (this.ready) return;
        await Tone.start();

        this.synths = {
            kick: new Tone.MembraneSynth({
                pitchDecay: 0.05, octaves: 6, oscillator: { type: 'sine' },
                envelope: { attack: 0.001, decay: 0.3, sustain: 0, release: 0.1 }
            }).toDestination(),
            snare: new Tone.NoiseSynth({
                noise: { type: 'white' },
                envelope: { attack: 0.001, decay: 0.15, sustain: 0, release: 0.05 }
            }).toDestination(),
            hihat_closed: new Tone.MetalSynth({
                frequency: 400, envelope: { attack: 0.001, decay: 0.05, release: 0.01 },
                harmonicity: 5.1, modulationIndex: 32, resonance: 4000, octaves: 1.5
            }).toDestination(),
            hihat_open: new Tone.MetalSynth({
                frequency: 400, envelope: { attack: 0.001, decay: 0.3, release: 0.1 },
                harmonicity: 5.1, modulationIndex: 32, resonance: 4000, octaves: 1.5
            }).toDestination(),
            ride: new Tone.MetalSynth({
                frequency: 300, envelope: { attack: 0.001, decay: 0.8, release: 0.2 },
                harmonicity: 12, modulationIndex: 20, resonance: 5000, octaves: 1
            }).toDestination(),
            crash: new Tone.MetalSynth({
                frequency: 250, envelope: { attack: 0.001, decay: 1.5, release: 0.3 },
                harmonicity: 5.1, modulationIndex: 40, resonance: 3000, octaves: 1.5
            }).toDestination(),
            tom_high: new Tone.MembraneSynth({
                pitchDecay: 0.02, octaves: 4, oscillator: { type: 'sine' },
                envelope: { attack: 0.001, decay: 0.2, sustain: 0, release: 0.05 }
            }).toDestination(),
            tom_mid: new Tone.MembraneSynth({
                pitchDecay: 0.02, octaves: 4, oscillator: { type: 'sine' },
                envelope: { attack: 0.001, decay: 0.25, sustain: 0, release: 0.05 }
            }).toDestination(),
            tom_low: new Tone.MembraneSynth({
                pitchDecay: 0.02, octaves: 4, oscillator: { type: 'sine' },
                envelope: { attack: 0.001, decay: 0.3, sustain: 0, release: 0.05 }
            }).toDestination(),
            stick: new Tone.NoiseSynth({
                noise: { type: 'pink' },
                envelope: { attack: 0.001, decay: 0.03, sustain: 0, release: 0.01 }
            }).toDestination(),
            clap: new Tone.NoiseSynth({
                noise: { type: 'white' },
                envelope: { attack: 0.001, decay: 0.1, sustain: 0, release: 0.05 }
            }).toDestination(),
            cowbell: new Tone.MetalSynth({
                frequency: 560, envelope: { attack: 0.001, decay: 0.15, release: 0.05 },
                harmonicity: 2, modulationIndex: 10, resonance: 2000, octaves: 0.5
            }).toDestination(),
            tambourine: new Tone.MetalSynth({
                frequency: 500, envelope: { attack: 0.001, decay: 0.1, release: 0.05 },
                harmonicity: 8, modulationIndex: 25, resonance: 3500, octaves: 1
            }).toDestination(),
        };

        // Set volumes
        this.synths.kick.volume.value = -3;
        this.synths.hihat_closed.volume.value = -12;
        this.synths.hihat_open.volume.value = -12;
        this.synths.ride.volume.value = -15;
        this.synths.crash.volume.value = -15;
        this.synths.cowbell.volume.value = -10;
        this.synths.tambourine.volume.value = -12;
        this.synths.tom_high.volume.value = -3;
        this.synths.tom_mid.volume.value = -3;
        this.synths.tom_low.volume.value = -3;

        this.ready = true;
    }

    trigger(name, velocity = 1.0, time) {
        const synth = this.synths[name];
        if (!synth) return;

        const vel = Math.min(1, velocity / 127);

        if (synth instanceof Tone.MembraneSynth) {
            const pitches = {
                kick: 'C1', tom_high: 'G3', tom_mid: 'D3', tom_low: 'A2'
            };
            synth.triggerAttackRelease(pitches[name] || 'C2', '8n', time, vel);
        } else if (synth instanceof Tone.NoiseSynth) {
            synth.triggerAttackRelease('16n', time, vel);
        } else if (synth instanceof Tone.MetalSynth) {
            synth.triggerAttackRelease('32n', time, vel);
        }
    }
}

// Player state
const player = {
    drumSynth: new DrumSynth(),
    midi: null,
    fileId: null,
    playing: false,
    looping: true,
    scheduledEvents: [],
    tempo: 120,
    originalTempo: 120,
};

async function loadAndPlay(fileId, filename, tempoHint) {
    await player.drumSynth.init();
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
    const playerBar = document.getElementById('player-bar');
    playerBar.classList.add('active');
    document.getElementById('player-filename').textContent = filename;
    document.getElementById('player-tempo').value = Math.round(player.tempo);
    document.getElementById('player-tempo-display').textContent = Math.round(player.tempo);

    startPlayback();
}

function startPlayback() {
    if (!player.midi) return;

    player.playing = true;
    document.getElementById('btn-play').textContent = '\u23F8';

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
    const patterDuration = maxTime + 0.01;

    // Schedule notes
    const part = new Tone.Part((time, event) => {
        const sampleName = GM_DRUM_SAMPLES[event.midi];
        if (sampleName) {
            player.drumSynth.trigger(sampleName, event.velocity, time);
        }
    }, notes.map(n => [n.time, n]));

    part.loop = player.looping;
    part.loopEnd = patterDuration;
    part.start(0);

    Tone.getTransport().start();
}

function stopPlayback() {
    player.playing = false;
    Tone.getTransport().stop();
    Tone.getTransport().cancel();
    document.getElementById('btn-play').textContent = '\u25B6';
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
}

// Search functionality
let searchTimeout = null;

function doSearch(resetOffset = true) {
    if (resetOffset) {
        currentOffset = 0;
    }

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

    fetch('/api/search?' + params.toString())
        .then(r => r.json())
        .then(data => renderResults(data));
}

let currentOffset = 0;

function renderResults(data) {
    const tbody = document.getElementById('results-body');
    const countEl = document.getElementById('result-count');

    countEl.textContent = `${data.total} results`;

    if (data.results.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:2rem;color:#666">No matching patterns found</td></tr>';
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
            <td>${r.folder}</td>
            <td>${r.time_sig}</td>
            <td>${Math.round(r.tempo_bpm)}</td>
            <td>${feel}</td>
            <td>${r.is_fill ? 'fill' : r.is_brush ? 'brush' : ''}</td>
            <td><div class="instruments-cell">${instTags}</div></td>
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
    document.querySelectorAll('.results-table tr.selected').forEach(r => r.classList.remove('selected'));
    tr.classList.add('selected');
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
    document.querySelectorAll('#time-sig, #feel, #pattern-type, #brush-filter, #sort-by').forEach(el => {
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
