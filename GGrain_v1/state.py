import os
import json
import copy

# ==============================================================================
# GGrain v1.0 - Single Source of Truth (ProjectState)
# ==============================================================================

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALES = {
    "CHROMATIC": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    "MAJOR":     [0, 2, 4, 5, 7, 9, 11],
    "MINOR":     [0, 2, 3, 5, 7, 8, 10],
    "PENT_MIN":  [0, 3, 5, 7, 10],
    "DORIAN":    [0, 2, 3, 5, 7, 9, 10],
    "PHRYGIAN":  [0, 1, 3, 5, 7, 8, 10],
}
SCALE_LIST = list(SCALES.keys())

SOURCE_TYPES = [
    "WAV",
    "OSC:KICK",
    "OSC:SNARE",
    "OSC:HAT",
    "OSC:SAW",
    "OSC:SQR",
    "OSC:SUB",
]


def midi_to_name(midi_note):
    if midi_note is None or midi_note < 0:
        return "---"
    octave = (midi_note // 12) - 1
    name = NOTE_NAMES[midi_note % 12]
    return f"{name}{octave}"


def quantize_to_scale(midi_note, root_midi, scale_name):
    intervals = SCALES.get(scale_name, SCALES["CHROMATIC"])
    if len(intervals) == 12:
        return max(24, min(96, midi_note))
    root_pc = root_midi % 12
    best_note = midi_note
    best_dist = 999
    for cand in range(max(24, midi_note - 6), min(97, midi_note + 7)):
        rel = (cand - root_pc) % 12
        if rel in intervals:
            dist = abs(cand - midi_note)
            if dist < best_dist:
                best_dist = dist
                best_note = cand
    return best_note


class InstrumentData:
    """Rappresenta uno degli 8 strumenti condivisi (I01 - I08)."""
    def __init__(self, index):
        self.index = index  # 0..7 -> I01..I08
        self.name = f"I{index + 1:02d}"

        # Selettore Sorgente a la LSDJ (WAV oppure Oscillatore interno)
        default_sources = ["OSC:KICK", "OSC:SNARE", "OSC:HAT", "OSC:SAW", "OSC:SQR", "OSC:SUB", "WAV", "WAV"]
        self.source_type = default_sources[index]

        self.sample_path = ""
        self.sample_name = "NONE"
        self.mode = "ONE-SHOT"     # "ONE-SHOT" o "GRAIN"
        self.root_note = 60        # C4 default
        self.scale = "MINOR"
        self.pitch_semi = 0        # -24 .. +24
        self.start_pos = 0.0       # 0.0 .. 0.95
        self.grain_size = 0.30     # 0.02 .. 1.0 (o Decay in ONE-SHOT)
        self.spray = 0.0           # 0.0 .. 1.0
        self.volume = 0.85         # 0.0 .. 1.0

        # 2 Effetti dedicati per strumento
        self.filter_cutoff = 0.0   # -1.0 (LP chiuso) .. 0.0 (aperto) .. +1.0 (HP)
        self.filter_res = 0.15     # 0.0 .. 0.9
        self.lfo_speed = 2.0       # Hz (0.1 .. 15.0)
        self.lfo_depth = 0.0       # 0.0 .. 1.0 (modula pitch/posizione)

        self.dirty = True          # Flag per rigenerare buffer in RAM
        self.reload_source = True  # Flag per ricaricare WAV o rigenerare forma d'onda OSC

    def reset_sound(self):
        self.pitch_semi = 0
        self.start_pos = 0.0
        self.grain_size = 0.30
        self.spray = 0.0
        self.filter_cutoff = 0.0
        self.filter_res = 0.15
        self.lfo_speed = 2.0
        self.lfo_depth = 0.0
        self.dirty = True

    def to_dict(self):
        return {
            "source_type": self.source_type,
            "sample_path": self.sample_path,
            "sample_name": self.sample_name,
            "mode": self.mode,
            "root_note": self.root_note,
            "scale": self.scale,
            "pitch_semi": self.pitch_semi,
            "start_pos": self.start_pos,
            "grain_size": self.grain_size,
            "spray": self.spray,
            "volume": self.volume,
            "filter_cutoff": self.filter_cutoff,
            "filter_res": self.filter_res,
            "lfo_speed": self.lfo_speed,
            "lfo_depth": self.lfo_depth,
        }

    def from_dict(self, d):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.reload_source = True
        self.dirty = True


class StepData:
    """Singolo step di un pattern (16 per pattern)."""
    def __init__(self, active=False, note=60, inst=0, slice_pos=0.0, vol=1.0):
        self.active = active
        self.note = note            # MIDI note (es. 60 = C4)
        self.inst = inst            # 0..7 (I01..I08)
        self.slice_pos = slice_pos  # 0.0..1.0 offset sul campione
        self.vol = vol              # 0.1..1.0

    def reset(self, default_inst=0):
        self.active = False
        self.note = 60
        self.inst = default_inst
        self.slice_pos = 0.0
        self.vol = 1.0

    def to_dict(self):
        return {
            "active": self.active,
            "note": self.note,
            "inst": self.inst,
            "slice_pos": self.slice_pos,
            "vol": self.vol,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            active=d.get("active", False),
            note=d.get("note", 60),
            inst=d.get("inst", 0),
            slice_pos=d.get("slice_pos", 0.0),
            vol=d.get("vol", 1.0),
        )


class MasterFXState:
    """Parametri della console di Mastering (SELECT + GIU)."""
    def __init__(self):
        self.bypass = False
        self.chorus_mix = 0.20      # 0.0 .. 1.0 (Stereo Widener / Chorus)
        self.reverb_size = 0.35     # 0.0 .. 1.0
        self.reverb_mix = 0.18      # 0.0 .. 1.0
        self.tape_drive = 0.25      # 0.0 .. 1.0 (Saturazione armonica)
        self.comp_thresh = 0.75     # 0.2 .. 1.0 (Soglia compressore/limiter)
        self.master_vol = 0.90      # 0.0 .. 1.0
        self.gain_reduction = 0.0   # Letto dalla UI per il meter GR (0.0..1.0)

    def reset(self):
        self.bypass = False
        self.chorus_mix = 0.0
        self.reverb_size = 0.35
        self.reverb_mix = 0.0
        self.tape_drive = 0.0
        self.comp_thresh = 0.85
        self.master_vol = 0.90

    def to_dict(self):
        return {
            "bypass": self.bypass,
            "chorus_mix": self.chorus_mix,
            "reverb_size": self.reverb_size,
            "reverb_mix": self.reverb_mix,
            "tape_drive": self.tape_drive,
            "comp_thresh": self.comp_thresh,
            "master_vol": self.master_vol,
        }

    def from_dict(self, d):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)


SYNTH_WAVES = ["SINE", "SQUARE", "PULSE25", "SAW", "TRIANGLE", "NOISE"]
SYNTH_FOLDERS = ["synth", "kick", "bass", "hats", "fx"]

THEME_BG_CHOICES = [
    ("PURE BLACK", (5, 5, 7)),
    ("OBSIDIAN", (12, 14, 20)),
    ("DEEP NAVY", (8, 14, 26)),
    ("FOREST DARK", (8, 18, 14)),
    ("WARM CHARCOAL", (20, 17, 16)),
    ("PAPER LIGHT", (235, 236, 240)),
]

THEME_INK_CHOICES = [
    ("ARCTIC WHITE", (244, 247, 250)),
    ("PHOSPHOR GREEN", (120, 255, 160)),
    ("AMBER CRT", (255, 198, 92)),
    ("ICE CYAN", (130, 235, 255)),
    ("SOFT ROSE", (255, 205, 215)),
    ("CARBON BLACK", (18, 20, 26)),
]

THEME_ACCENT_CHOICES = [
    ("CRIMSON RED", (255, 30, 56)),
    ("ELECTRIC CYAN", (0, 210, 255)),
    ("ACID LIME", (165, 255, 45)),
    ("SOLAR ORANGE", (255, 125, 20)),
    ("SYNTH MAGENTA", (235, 55, 220)),
    ("GOLD YELLOW", (255, 205, 35)),
]


class SynthLabState:
    """Parametri del Mini-Synth per creare e salvare nuovi campioni WAV (SELECT + SX + SX)."""
    def __init__(self):
        self.wave_type = "SAW"
        self.sub_mix = 0.30         # 0.0 .. 1.0 (-1 ottava sub)
        self.pitch_env_amt = 0      # -24 .. +48 semitoni (positivo = punch kick/zap)
        self.pitch_env_dec = 0.08   # 0.02 .. 0.60 s
        self.amp_decay = 0.45       # 0.05 .. 1.50 s
        self.filter_cutoff = 0.0    # -1.0 LP .. 0.0 Flat .. +1.0 HP
        self.drive_crush = 0.15     # 0.0 .. 1.0 (drive + grit)
        self.folder_idx = 0         # indice in SYNTH_FOLDERS

    def apply_preset(self, name):
        if name == "KICK":
            self.wave_type = "SINE"
            self.sub_mix = 0.50
            self.pitch_env_amt = 34
            self.pitch_env_dec = 0.06
            self.amp_decay = 0.42
            self.filter_cutoff = -0.25
            self.drive_crush = 0.35
            self.folder_idx = 1  # kick
        elif name == "BASS":
            self.wave_type = "SAW"
            self.sub_mix = 0.60
            self.pitch_env_amt = 0
            self.pitch_env_dec = 0.05
            self.amp_decay = 0.55
            self.filter_cutoff = -0.45
            self.drive_crush = 0.25
            self.folder_idx = 2  # bass
        elif name == "LEAD":
            self.wave_type = "PULSE25"
            self.sub_mix = 0.20
            self.pitch_env_amt = 2
            self.pitch_env_dec = 0.04
            self.amp_decay = 0.65
            self.filter_cutoff = 0.0
            self.drive_crush = 0.15
            self.folder_idx = 0  # synth
        elif name == "HAT":
            self.wave_type = "NOISE"
            self.sub_mix = 0.0
            self.pitch_env_amt = 0
            self.pitch_env_dec = 0.03
            self.amp_decay = 0.11
            self.filter_cutoff = 0.55
            self.drive_crush = 0.10
            self.folder_idx = 3  # hats


class ProjectState:
    """Unico stato centrale letto e scritto da tutte le 4 facciate della croce."""
    NUM_TRACKS = 4
    NUM_PATTERNS = 8
    STEPS_PER_PATTERN = 16
    SONG_BARS = 8
    NUM_INSTRUMENTS = 8

    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.samples_dir = os.path.join(base_dir, "samples")
        self.projects_dir = os.path.join(base_dir, "projects")
        os.makedirs(self.samples_dir, exist_ok=True)
        os.makedirs(os.path.join(self.samples_dir, "mic"), exist_ok=True)
        os.makedirs(self.projects_dir, exist_ok=True)

        self.config_path = os.path.join(base_dir, "ggrain_config.json")
        self.theme_bg_idx = 0
        self.theme_ink_idx = 0
        self.theme_accent_idx = 0
        self.credits_page = 0
        self.credits_scroll = 0

        self.reset_project()
        self.load_ui_config()

    def reset_project(self):
        # Transport & Timing Globale
        self.bpm = 122
        self.swing = 0.0            # 0.0 .. 0.65
        self.playing = False
        self.loop_bar_mode = True   # True = Loop battuta (START), False = Song Chain (R1+START)
        self.current_bar = 0        # 0..7
        self.current_step = 0       # 0..15

        # Navigazione Croce & Selezione Attiva
        # "PROJECT", "SONG_SEQ", "INSTRUMENT", "MASTERING"
        self.active_screen = "SONG_SEQ"
        self.active_track = 0       # 0..3 (T1..T4)
        self.active_inst = 0        # 0..7 (I01..I08)
        self.seq_focus = "STEPS"    # "SONG" (sinistra) o "STEPS" (destra)
        self.cursor_bar = 0         # 0..7 nella mappa Song
        self.cursor_step = 0        # 0..15 nei 16 step
        self.midi_step_rec = False  # Step-record automatico da tastiera MIDI
        self.project_slot = 1       # 1..8
        self.project_name = "UNTITLED"
        self.name_editor_open = False
        self.name_editor_chars = list("UNTITLED  ")
        self.name_editor_pos = 0
        self.name_grid_idx = 0

        # Smart Inheritance (ricorda ultimi valori editati)
        self.last_step_note = 60
        self.last_step_slice = 0.0
        self.last_step_vol = 1.0
        self.last_song_pat = 0

        # Cursori UI per tutte le stanze
        self.inst_param_idx = 0      # 0..7 nella stanza INSTRUMENT
        self.master_param_idx = 0    # 0..4 nella stanza MASTERING
        self.project_param_idx = 0   # 0..11 nella stanza PROJECT
        self.project_exit_mode = 0   # 0 = NEW PROJECT, 1 = EXIT TO KNULLI
        self.synth_param_idx = 0     # 0..7 nella stanza SYNTH_LAB
        self.synth_lab = SynthLabState()

        # Menu Rapido Contestuale (Tasto Y) & Notifiche Toast
        self.y_menu_open = False
        self.y_menu_idx = 0
        self.toast_msg = ""
        self.toast_timer = 0.0

        self.wav_browser_open = False
        self.wav_browser_files = []  # Lista di (display_name, full_path)
        self.wav_browser_idx = 0

    # Stato Tracce
        self.track_muted = [False] * self.NUM_TRACKS
        self.track_solo = [False] * self.NUM_TRACKS

        # Mappa Song: 8 righe (battute) x 4 tracce -> valore 0..7 (pattern 1..8) o -1 (vuoto "--")
        self.song_grid = [[-1 for _ in range(self.NUM_TRACKS)] for _ in range(self.SONG_BARS)]
        for t in range(self.NUM_TRACKS):
            self.song_grid[0][t] = 0

        # Pattern Bank: [track 0..3][pattern 0..7][step 0..15]
        self.patterns = [
            [
                [StepData(active=False, note=60, inst=t) for _ in range(self.STEPS_PER_PATTERN)]
                for _ in range(self.NUM_PATTERNS)
            ]
            for t in range(self.NUM_TRACKS)
        ]

        # Banco condiviso 8 Strumenti (I01 - I08)
        self.instruments = [InstrumentData(i) for i in range(self.NUM_INSTRUMENTS)]

        # Console Master FX
        self.master_fx = MasterFXState()

        # Hardware I/O State
        self.sync_out_2ppqn = False
        self.mic_connected = False
        self.mic_name = "NOT CONNECTED"
        self.mic_recording = False
        self.mic_level = 0.0
        self.midi_connected = False
        self.midi_name = "NOT CONNECTED"
        self.midi_activity = 0.0

        # Macro temporanee Stick Analogici in SONG_SEQ
        self.live_filter_offset = 0.0
        self.live_res_offset = 0.0
        self.live_pitch_bend = 0.0
        self.live_stutter = 0.0

        # Meter Audio
        self.vu_left = 0.0
        self.vu_right = 0.0

    def set_toast(self, msg, duration=2.4):
        self.toast_msg = msg
        self.toast_timer = duration

    def load_ui_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.theme_bg_idx = int(cfg.get("theme_bg_idx", 0)) % len(THEME_BG_CHOICES)
            self.theme_ink_idx = int(cfg.get("theme_ink_idx", 0)) % len(THEME_INK_CHOICES)
            self.theme_accent_idx = int(cfg.get("theme_accent_idx", 0)) % len(THEME_ACCENT_CHOICES)
        except Exception:
            pass

    def save_ui_config(self):
        try:
            cfg = {
                "theme_bg_idx": self.theme_bg_idx,
                "theme_ink_idx": self.theme_ink_idx,
                "theme_accent_idx": self.theme_accent_idx,
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    # --- Helpers Cartelle & WAV Browser ---

    def get_synth_folders(self):
        """Legge dinamicamente tutte le sottocartelle reali dentro samples/."""
        folders = []
        if os.path.isdir(self.samples_dir):
            for root, dirs, _ in os.walk(self.samples_dir):
                dirs.sort(key=lambda s: s.lower())
                for d in dirs:
                    full_d = os.path.join(root, d)
                    rel = os.path.relpath(full_d, self.samples_dir).replace("\\", "/")
                    folders.append(rel)
        return folders if folders else list(SYNTH_FOLDERS)

    def refresh_wav_browser(self):
        """Scansiona ricorsivamente samples/ (incluso samples/mic/) per il browser WAV."""
        found = []
        if os.path.isdir(self.samples_dir):
            for root, _, files in os.walk(self.samples_dir):
                rel_dir = os.path.relpath(root, self.samples_dir)
                for fn in sorted(files):
                    if fn.lower().endswith(".wav"):
                        full_p = os.path.join(root, fn)
                        if rel_dir == ".":
                            disp = fn
                        else:
                            disp = f"[{rel_dir}] {fn}"
                        found.append((disp, full_p))
        self.wav_browser_files = found
        self.wav_browser_idx = min(self.wav_browser_idx, max(0, len(found) - 1))

    # --- Helpers di Composizione ---

    def get_active_pattern_index(self, track=None, bar=None):
        t = self.active_track if track is None else track
        b = self.cursor_bar if bar is None else bar
        pat = self.song_grid[b][t]
        return pat if 0 <= pat < self.NUM_PATTERNS else 0

    def get_current_pattern(self, track=None, bar=None):
        t = self.active_track if track is None else track
        pat_idx = self.get_active_pattern_index(t, bar)
        return self.patterns[t][pat_idx]

    def clone_pattern_to_next(self):
        t = self.active_track
        b = self.cursor_bar
        src_idx = self.song_grid[b][t]
        if src_idx < 0:
            src_idx = 0
            self.song_grid[b][t] = 0

        used = set(self.song_grid[row][t] for row in range(self.SONG_BARS) if self.song_grid[row][t] >= 0)
        target_idx = None
        for cand in range(self.NUM_PATTERNS):
            if cand not in used:
                target_idx = cand
                break
        if target_idx is None:
            target_idx = (src_idx + 1) % self.NUM_PATTERNS

        self.patterns[t][target_idx] = copy.deepcopy(self.patterns[t][src_idx])
        self.song_grid[b][t] = target_idx
        self.seq_focus = "STEPS"
        return target_idx

    def clear_current_pattern(self):
        pat = self.get_current_pattern()
        for step in pat:
            step.reset(default_inst=self.active_inst)

    def transpose_current_pattern(self, semitones):
        pat = self.get_current_pattern()
        for step in pat:
            if step.active:
                step.note = max(24, min(96, step.note + semitones))

    def toggle_mute(self, track=None):
        t = self.active_track if track is None else track
        self.track_muted[t] = not self.track_muted[t]

    def toggle_solo(self, track=None):
        t = self.active_track if track is None else track
        new_state = not self.track_solo[t]
        self.track_solo = [False] * self.NUM_TRACKS
        self.track_solo[t] = new_state

    def is_track_audible(self, track):
        if any(self.track_solo):
            return self.track_solo[track]
        return not self.track_muted[track]

    def jump_to_step_instrument(self):
        pat = self.get_current_pattern()
        step = pat[self.cursor_step]
        if step.active:
            self.active_inst = step.inst
        self.active_screen = "INSTRUMENT"

    # --- Salvataggio / Caricamento Progetto (8 Slot) ---

    def get_slot_path(self, slot=None):
        s = self.project_slot if slot is None else slot
        return os.path.join(self.projects_dir, f"ggrain_project_{s:02d}.json")

    def refresh_slot_names_cache(self):
        cache = {}
        for s in range(1, 9):
            p = self.get_slot_path(s)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    nm = str(d.get("project_name", f"SONG_{s:02d}")).strip()[:10]
                    cache[s] = nm if nm else f"SONG_{s:02d}"
                except Exception:
                    cache[s] = f"SONG_{s:02d}"
            else:
                cache[s] = None
        self.slot_names_cache = cache

    def get_slot_display_name(self, slot):
        if not hasattr(self, "slot_names_cache"):
            self.refresh_slot_names_cache()
        return self.slot_names_cache.get(slot)

    def update_slot_name_on_disk(self, slot=None):
        path = self.get_slot_path(slot)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["project_name"] = self.project_name
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
        self.refresh_slot_names_cache()

    def save_project(self, slot=None):
        path = self.get_slot_path(slot)
        data = {
            "version": "1.0",
            "project_name": self.project_name,
            "bpm": self.bpm,
            "swing": self.swing,
            "song_grid": self.song_grid,
            "patterns": [
                [[st.to_dict() for st in pat] for pat in trk]
                for trk in self.patterns
            ],
            "instruments": [inst.to_dict() for inst in self.instruments],
            "master_fx": self.master_fx.to_dict(),
            "sync_out_2ppqn": self.sync_out_2ppqn,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.refresh_slot_names_cache()
        return path

    def load_project(self, slot=None):
        s = self.project_slot if slot is None else slot
        path = self.get_slot_path(s)
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.playing = False
        self.current_bar = 0
        self.current_step = 0
        self.project_name = str(data.get("project_name", f"SONG_{s:02d}")).strip()[:10] or f"SONG_{s:02d}"
        self.bpm = data.get("bpm", 122)
        self.swing = data.get("swing", 0.0)
        self.sync_out_2ppqn = data.get("sync_out_2ppqn", False)

        saved_grid = data.get("song_grid")
        if saved_grid and len(saved_grid) == self.SONG_BARS:
            self.song_grid = saved_grid

        saved_pats = data.get("patterns")
        if saved_pats:
            for t in range(min(self.NUM_TRACKS, len(saved_pats))):
                for p in range(min(self.NUM_PATTERNS, len(saved_pats[t]))):
                    for s in range(min(self.STEPS_PER_PATTERN, len(saved_pats[t][p]))):
                        self.patterns[t][p][s] = StepData.from_dict(saved_pats[t][p][s])

        saved_insts = data.get("instruments")
        if saved_insts:
            for i in range(min(self.NUM_INSTRUMENTS, len(saved_insts))):
                self.instruments[i].from_dict(saved_insts[i])

        saved_master = data.get("master_fx")
        if saved_master:
            self.master_fx.from_dict(saved_master)

        return True