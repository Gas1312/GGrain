import os
import sys
import time
import pygame

from state import (
    ProjectState, quantize_to_scale, SOURCE_TYPES, SCALE_LIST,
    SYNTH_WAVES, SYNTH_FOLDERS, THEME_BG_CHOICES, THEME_INK_CHOICES, THEME_ACCENT_CHOICES
)
from audio_dsp import AudioEngine
from hardware_io import HardwareIOManager
from ui import UIRenderer, SHORTCUT_PAGES, NAME_GRID_CHARS


R36S_BTN_MAP = {
    0: "B",
    1: "A",
    2: "X",
    3: "Y",
    4: "L2",
    5: "R2",
    6: "L1",
    7: "R1",
    8: "UP",
    9: "DOWN",
    10: "LEFT",
    11: "RIGHT",
    12: "SELECT",
    13: "START",
    14: "L3",
    15: "R3",
    16: "FN",
}

PC_KEY_MAP = {
    pygame.K_UP: "UP",
    pygame.K_DOWN: "DOWN",
    pygame.K_LEFT: "LEFT",
    pygame.K_RIGHT: "RIGHT",
    pygame.K_z: "A",
    pygame.K_x: "B",
    pygame.K_a: "X",
    pygame.K_s: "Y",
    pygame.K_q: "L1",
    pygame.K_w: "R1",
    pygame.K_1: "L2",
    pygame.K_2: "R2",
    pygame.K_RSHIFT: "SELECT",
    pygame.K_BACKSPACE: "SELECT",
    pygame.K_RETURN: "START",
}

CUSTOM_SH_PATH = "/userdata/system/custom.sh"
CUSTOM_SH_MARKER = "# GGRAIN_DIRECT_BOOT"


class InputHandler:
    def __init__(self):
        pygame.joystick.init()
        self.joy = None
        self.joy_name = "KEYBOARD (PC)"
        if pygame.joystick.get_count() > 0:
            self.joy = pygame.joystick.Joystick(0)
            self.joy.init()
            self.joy_name = self.joy.get_name()

        self.held = set()
        self.just_pressed = set()
        self.just_released = set()
        self.raw_buttons_held = set()

        self.lx = 0.0
        self.ly = 0.0
        self.rx = 0.0
        self.ry = 0.0

        self.debug_mode = False
        self._debug_combo_locked = False
        self._repeat_timers = {}

    def _apply_deadzone(self, val, dz=0.18):
        if abs(val) < dz:
            return 0.0
        sign = 1.0 if val > 0 else -1.0
        return sign * ((abs(val) - dz) / (1.0 - dz))

    def update(self, events, dt):
        prev_held = set(self.held)
        self.just_pressed.clear()
        self.just_released.clear()

        joy_logical = set()
        self.raw_buttons_held.clear()
        if self.joy is not None:
            num_btns = self.joy.get_numbuttons()
            for b_id in range(num_btns):
                if self.joy.get_button(b_id):
                    self.raw_buttons_held.add(b_id)
                    if b_id in R36S_BTN_MAP:
                        joy_logical.add(R36S_BTN_MAP[b_id])

            if self.joy.get_numhats() > 0:
                hx, hy = self.joy.get_hat(0)
                if hy == 1:
                    joy_logical.add("UP")
                elif hy == -1:
                    joy_logical.add("DOWN")
                if hx == -1:
                    joy_logical.add("LEFT")
                elif hx == 1:
                    joy_logical.add("RIGHT")

            n_axes = self.joy.get_numaxes()
            self.lx = -self._apply_deadzone(self.joy.get_axis(0)) if n_axes > 0 else 0.0
            self.ly = -self._apply_deadzone(self.joy.get_axis(1)) if n_axes > 1 else 0.0
            self.rx = self._apply_deadzone(self.joy.get_axis(2)) if n_axes > 2 else 0.0
            self.ry = -self._apply_deadzone(self.joy.get_axis(3)) if n_axes > 3 else 0.0

        keys = pygame.key.get_pressed()
        key_logical = set()
        for k_code, name in PC_KEY_MAP.items():
            if keys[k_code]:
                key_logical.add(name)

        self.held = joy_logical | key_logical
        self.just_pressed = self.held - prev_held
        self.just_released = prev_held - self.held

        for direction in ("UP", "DOWN", "LEFT", "RIGHT"):
            if direction in self.held:
                if direction in self.just_pressed:
                    self._repeat_timers[direction] = 0.28
                else:
                    self._repeat_timers[direction] = self._repeat_timers.get(direction, 0.28) - dt
                    if self._repeat_timers[direction] <= 0.0:
                        self.just_pressed.add(direction)
                        self._repeat_timers[direction] = 0.075
            else:
                self._repeat_timers.pop(direction, None)

        combo_debug = ({"L2", "R2", "SELECT"}.issubset(self.held)) or keys[pygame.K_F12]
        if combo_debug and not self._debug_combo_locked:
            self.debug_mode = not self.debug_mode
            self._debug_combo_locked = True
        elif not combo_debug:
            self._debug_combo_locked = False

    def is_held(self, name):
        return name in self.held

    def pressed(self, name):
        return name in self.just_pressed

    def released(self, name):
        return name in self.just_released


class GGrainApp:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pygame.init()
        self.screen = pygame.display.set_mode((640, 480))
        pygame.display.set_caption("GGrain v1.0 - produced by Gas1312")
        pygame.mouse.set_visible(False)

        self.state = ProjectState(base_dir=base_dir)
        self.audio = AudioEngine(self.state)
        self.hw = HardwareIOManager(self.state)
        self.ui = UIRenderer(self.screen, self.state, self.audio, self.hw)
        self.inp = InputHandler()

        self.clock = pygame.time.Clock()
        self.running = True
        self._a_used_as_mod = False
        self._stick_audition_timer = 0.0

    def _audition_if_stopped(self):
        if not self.state.playing:
            self.audio.audition_instrument(self.state.active_inst)

    # ==========================================================================
    # R36S DIRECT BOOT HELPER (/userdata/system/custom.sh)
    # ==========================================================================

    def is_direct_boot_enabled(self):
        if not os.path.exists(CUSTOM_SH_PATH):
            return False
        try:
            with open(CUSTOM_SH_PATH, "r", encoding="utf-8", errors="ignore") as f:
                return CUSTOM_SH_MARKER in f.read()
        except Exception:
            return False

    def toggle_direct_boot(self):
        if not os.path.isdir("/userdata/system"):
            self.state.set_toast("PC MODE: DIRECT BOOT WORKS ON R36S")
            return
        try:
            currently = self.is_direct_boot_enabled()
            lines = []
            if os.path.exists(CUSTOM_SH_PATH):
                with open(CUSTOM_SH_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln for ln in f.read().splitlines() if CUSTOM_SH_MARKER not in ln and "GGrain/main.py" not in ln]

            if not currently:
                if not lines or not lines[0].startswith("#!"):
                    lines.insert(0, "#!/bin/bash")
                lines.append(f"python3 /userdata/roms/ports/GGrain/main.py {CUSTOM_SH_MARKER}")
                with open(CUSTOM_SH_PATH, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                os.chmod(CUSTOM_SH_PATH, 0o755)
                self.state.set_toast("DIRECT BOOT ENABLED!")
            else:
                with open(CUSTOM_SH_PATH, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                self.state.set_toast("DIRECT BOOT DISABLED")
        except Exception:
            self.state.set_toast("ERROR WRITING CUSTOM.SH")

    # ==========================================================================
    # MENU RAPIDO CONTESTUALE (TASTO Y)
    # ==========================================================================

    def get_y_menu_items(self):
        scr = self.state.active_screen
        if scr == "SONG_SEQ":
            return [
                "RESET STEP (PITCH & SLICE)",
                "CLEAR PATTERN (16 STEPS)",
                "CLONE PATTERN -> NEXT SLOT",
                "TRANSPOSE PATTERN +1 OCTAVE",
                "TRANSPOSE PATTERN -1 OCTAVE",
                "TOGGLE SOLO TRACK",
            ]
        elif scr == "INSTRUMENT":
            return [
                "RESET PITCH (0 st)",
                "RESET START & GRAIN",
                "RESET FILTER & MINI-LFO",
                "SWITCH ONE-SHOT / GRAIN",
                "TRIM SILENCE & NORMALIZE WAV",
            ]
        elif scr == "MASTERING":
            return [
                "TOGGLE A/B BYPASS ALL FX",
                "RESET MASTER CHAIN",
                "TOGGLE FM-1 SYNC 2 PPQN",
            ]
        elif scr == "SYNTH_LAB":
            return [
                "PRESET: 808 KICK PUNCH",
                "PRESET: ACID SAW BASS",
                "PRESET: LSDJ PULSE LEAD",
                "PRESET: CRISPY HI-HAT",
                "BOUNCE WAV & LOAD TO INST",
            ]
        elif scr == "PROJECT":
            return [
                "QUICK SAVE CURRENT SLOT",
                "EXPORT MASTER WAV NOW",
                "NEW EMPTY PROJECT",
            ]
        return ["CLOSE MENU"]

    def _execute_y_menu_action(self):
        scr = self.state.active_screen
        idx = self.state.y_menu_idx

        if scr == "SONG_SEQ":
            pat = self.state.get_current_pattern()
            st = pat[self.state.cursor_step]
            if idx == 0:
                st.note = self.state.instruments[st.inst].root_note
                st.slice_pos = 0.0
                self.state.set_toast("STEP RESET")
            elif idx == 1:
                self.state.clear_current_pattern()
                self.state.set_toast("PATTERN CLEARED")
            elif idx == 2:
                new_p = self.state.clone_pattern_to_next()
                self.state.set_toast(f"CLONED TO PAT 0{new_p + 1}")
            elif idx == 3:
                self.state.transpose_current_pattern(12)
                self.state.set_toast("TRANSPOSED +1 OCT")
            elif idx == 4:
                self.state.transpose_current_pattern(-12)
                self.state.set_toast("TRANSPOSED -1 OCT")
            elif idx == 5:
                self.state.toggle_solo()
                self.state.set_toast(f"SOLO T{self.state.active_track + 1}")

        elif scr == "INSTRUMENT":
            inst = self.state.instruments[self.state.active_inst]
            if idx == 0:
                inst.pitch_semi = 0
                inst.dirty = True
                self.state.set_toast("PITCH RESET (0 st)")
            elif idx == 1:
                inst.start_pos = 0.0
                inst.grain_size = 0.30
                inst.spray = 0.0
                inst.dirty = True
                self.state.set_toast("START & GRAIN RESET")
            elif idx == 2:
                inst.filter_cutoff = 0.0
                inst.filter_res = 0.15
                inst.lfo_depth = 0.0
                inst.dirty = True
                self.state.set_toast("FILTER & LFO RESET")
            elif idx == 3:
                inst.mode = "GRAIN" if inst.mode == "ONE-SHOT" else "ONE-SHOT"
                inst.dirty = True
                self.state.set_toast(f"MODE: {inst.mode}")
            elif idx == 4:
                ok = self.audio.trim_and_normalize_instrument_wav(self.state.active_inst)
                self.state.set_toast("WAV TRIMMED & NORMALIZED!" if ok else "LOAD A WAV FIRST")

        elif scr == "MASTERING":
            mfx = self.state.master_fx
            if idx == 0:
                mfx.bypass = not mfx.bypass
                for inst in self.state.instruments:
                    inst.dirty = True
                self.state.set_toast("MASTER BYPASSED" if mfx.bypass else "MASTER ACTIVE")
            elif idx == 1:
                mfx.reset()
                for inst in self.state.instruments:
                    inst.dirty = True
                self.state.set_toast("MASTER CHAIN RESET")
            elif idx == 2:
                self.state.sync_out_2ppqn = not self.state.sync_out_2ppqn
                self.state.set_toast("SYNC 2 PPQN ON" if self.state.sync_out_2ppqn else "SYNC 2 PPQN OFF")

        elif scr == "SYNTH_LAB":
            presets = ["KICK", "BASS", "LEAD", "HAT"]
            if idx < 4:
                self.state.synth_lab.apply_preset(presets[idx])
                self.audio.audition_synth_lab()
                self.state.set_toast(f"PRESET: {presets[idx]}")
            elif idx == 4:
                rel = self.audio.bounce_synth_lab_wav()
                self.state.set_toast(f"SAVED {rel} -> I{self.state.active_inst + 1:02d}")

        elif scr == "PROJECT":
            if idx == 0:
                self.state.save_project()
                self.state.set_toast(f"SAVED SLOT 0{self.state.project_slot}")
            elif idx == 1:
                fname = f"ggrain_master_0{self.state.project_slot}.wav"
                self.audio.export_song_wav(fname)
                self.state.set_toast(f"EXPORTED {fname}")
            elif idx == 2:
                self.state.reset_project()
                for i, inst in enumerate(self.state.instruments):
                    self.audio.instruments[i].load_source(inst)
                self.state.set_toast("NEW EMPTY PROJECT")

        self.state.y_menu_open = False

    # ==========================================================================
    # SPLASH & EVENTI HARDWARE
    # ==========================================================================

    def run_splash(self):
        start_t = time.perf_counter()
        last_t = start_t
        while self.running:
            now = time.perf_counter()
            dt = min(0.05, now - last_t)
            last_t = now
            elapsed = now - start_t

            events = pygame.event.get()
            for ev in events:
                if ev.type == pygame.QUIT:
                    self.running = False
                    return
            self.inp.update(events, dt)

            if elapsed >= 2.0 or self.inp.just_pressed:
                break

            self.ui.draw_splash(dt, elapsed)
            pygame.display.flip()
            self.clock.tick(60)

    def _process_hardware_events(self):
        if self.hw.last_recorded_wav:
            wav_path = self.hw.last_recorded_wav
            self.hw.last_recorded_wav = None
            self.audio.load_wav_into_instrument(self.state.active_inst, wav_path)
            self.state.set_toast(f"MIC WAV LOADED IN I{self.state.active_inst + 1:02d}!")

        while self.hw.midi_note_queue:
            midi_note, vel = self.hw.midi_note_queue.popleft()
            if (
                not self.state.playing
                and self.state.midi_step_rec
                and self.state.active_screen == "SONG_SEQ"
            ):
                pat = self.state.get_current_pattern()
                st = pat[self.state.cursor_step]
                st.active = True
                st.note = midi_note
                st.inst = self.state.active_inst
                st.vol = max(0.2, min(1.0, vel / 127.0))
                self.audio.audition_instrument(st.inst, midi_note=st.note)
                self.state.cursor_step = (self.state.cursor_step + 1) % 16
            else:
                self.audio.audition_instrument(self.state.active_inst, midi_note=midi_note)

    # ==========================================================================
    # CONTROLLI GLOBALI, CROCE LSDJ ESTESA & STANZE
    # ==========================================================================

    def _handle_name_editor_controls(self):
        row = self.state.name_grid_idx // 10
        col = self.state.name_grid_idx % 10

        if self.inp.pressed("UP"):
            row = (row - 1) % 4
        elif self.inp.pressed("DOWN"):
            row = (row + 1) % 4
        elif self.inp.pressed("LEFT"):
            col = (col - 1) % 10
        elif self.inp.pressed("RIGHT"):
            col = (col + 1) % 10
        self.state.name_grid_idx = row * 10 + col

        if self.inp.pressed("L1"):
            self.state.name_editor_pos = (self.state.name_editor_pos - 1) % 10
        elif self.inp.pressed("R1"):
            self.state.name_editor_pos = (self.state.name_editor_pos + 1) % 10

        if self.inp.pressed("B"):
            pos = self.state.name_editor_pos
            if self.state.name_editor_chars[pos] != " ":
                self.state.name_editor_chars[pos] = " "
            else:
                pos = max(0, pos - 1)
                self.state.name_editor_pos = pos
                self.state.name_editor_chars[pos] = " "

        if self.inp.pressed("A"):
            chosen = NAME_GRID_CHARS[self.state.name_grid_idx]
            if chosen == "OK":
                self._confirm_project_name()
            elif chosen == "<":
                pos = max(0, self.state.name_editor_pos - 1)
                self.state.name_editor_chars[pos] = " "
                self.state.name_editor_pos = pos
            else:
                self.state.name_editor_chars[self.state.name_editor_pos] = chosen
                self.state.name_editor_pos = min(9, self.state.name_editor_pos + 1)

        if self.inp.pressed("START"):
            self._confirm_project_name()

    def _confirm_project_name(self):
        raw_name = "".join(self.state.name_editor_chars).strip()
        self.state.project_name = raw_name if raw_name else "UNTITLED"
        self.state.name_editor_open = False
        self.state.update_slot_name_on_disk()
        self.state.set_toast(f"NAME: {self.state.project_name}")

    def _handle_global_controls(self):
        if self.inp.is_held("SELECT") and (self.inp.pressed("START") or self.inp.pressed("FN")):
            self.running = False
            return True

        if self.state.name_editor_open:
            self._handle_name_editor_controls()
            return True

        if self.inp.pressed("L3"):
            self.state.toggle_mute()
            t = self.state.active_track + 1
            self.state.set_toast(f"T{t} MUTED" if self.state.track_muted[t - 1] else f"T{t} UNMUTED")

        if self.inp.pressed("R3"):
            if self.state.active_screen == "SYNTH_LAB":
                self.audio.audition_synth_lab()
            else:
                self.audio.audition_instrument(self.state.active_inst)

        if self.inp.pressed("START") and not self.inp.is_held("SELECT"):
            if self.inp.is_held("R1"):
                self.state.loop_bar_mode = False
                self.state.playing = True
                self.state.current_bar = self.state.cursor_bar
                self.state.current_step = 0
                self.state.set_toast("PLAY: SONG CHAIN")
            else:
                self.state.playing = not self.state.playing
                if self.state.playing:
                    self.state.loop_bar_mode = True
                    self.state.current_bar = self.state.cursor_bar
                    self.state.current_step = 0

        # Navigazione a Croce Estesa (SELECT + D-Pad, con doppio tap SX-SX e DX-DX)
        if self.inp.is_held("SELECT"):
            if self.inp.pressed("UP"):
                self.state.wav_browser_open = False
                self.state.y_menu_open = False
                self.state.active_screen = "PROJECT"
            elif self.inp.pressed("LEFT"):
                self.state.wav_browser_open = False
                self.state.y_menu_open = False
                if self.state.active_screen == "SONG_SEQ":
                    self.state.active_screen = "SYNTH_LAB"
                else:
                    self.state.active_screen = "SONG_SEQ"
            elif self.inp.pressed("RIGHT"):
                self.state.wav_browser_open = False
                self.state.y_menu_open = False
                if self.state.active_screen == "INSTRUMENT":
                    self.state.active_screen = "CREDITS"
                elif self.state.active_screen == "SONG_SEQ":
                    self.state.jump_to_step_instrument()
                else:
                    self.state.active_screen = "INSTRUMENT"
            elif self.inp.pressed("DOWN"):
                self.state.wav_browser_open = False
                self.state.y_menu_open = False
                self.state.active_screen = "MASTERING"
            elif self.inp.pressed("B"):
                self.state.toggle_mute()
                t = self.state.active_track + 1
                self.state.set_toast(f"T{t} MUTED" if self.state.track_muted[t - 1] else f"T{t} UNMUTED")
            return True

        # Gestione Menu Contestuale Y
        if self.state.y_menu_open:
            items = self.get_y_menu_items()
            if self.inp.pressed("UP"):
                self.state.y_menu_idx = (self.state.y_menu_idx - 1) % len(items)
            elif self.inp.pressed("DOWN"):
                self.state.y_menu_idx = (self.state.y_menu_idx + 1) % len(items)
            elif self.inp.pressed("A"):
                self._execute_y_menu_action()
            elif self.inp.pressed("B") or self.inp.pressed("Y"):
                self.state.y_menu_open = False
            return True

        if self.inp.pressed("Y") and not self.state.wav_browser_open:
            self.state.y_menu_open = True
            self.state.y_menu_idx = 0
            return True

        return False

    def _handle_project_controls(self):
        if self.inp.pressed("UP"):
            self.state.project_param_idx = (self.state.project_param_idx - 1) % 12
        elif self.inp.pressed("DOWN"):
            self.state.project_param_idx = (self.state.project_param_idx + 1) % 12

        p_idx = self.state.project_param_idx
        delta = 1 if self.inp.pressed("RIGHT") else (-1 if self.inp.pressed("LEFT") else 0)
        shift_a = self.inp.is_held("A")

        if delta != 0:
            if p_idx == 0:  # SLOT
                self.state.project_slot = ((self.state.project_slot - 1 + delta) % 8) + 1
            elif p_idx == 4:  # BPM
                step_bpm = 10 if shift_a else 1
                self.state.bpm = max(40, min(240, self.state.bpm + delta * step_bpm))
            elif p_idx == 5:  # SWING
                self.state.swing = max(0.0, min(0.65, round(self.state.swing + delta * 0.05, 2)))
            elif p_idx == 7:  # THEME BASE / BG
                self.state.theme_bg_idx = (self.state.theme_bg_idx + delta) % len(THEME_BG_CHOICES)
                self.state.save_ui_config()
            elif p_idx == 8:  # THEME INK / TEXT
                self.state.theme_ink_idx = (self.state.theme_ink_idx + delta) % len(THEME_INK_CHOICES)
                self.state.save_ui_config()
            elif p_idx == 9:  # THEME ACCENT
                self.state.theme_accent_idx = (self.state.theme_accent_idx + delta) % len(THEME_ACCENT_CHOICES)
                self.state.save_ui_config()
            elif p_idx == 10:  # DIRECT BOOT
                self.toggle_direct_boot()
            elif p_idx == 11:  # NEW vs EXIT
                self.state.project_exit_mode = 1 - self.state.project_exit_mode

        if self.inp.pressed("A"):
            if p_idx == 1:  # RENAME PROJECT (LSDJ STYLE)
                padded = list(self.state.project_name.ljust(10)[:10])
                self.state.name_editor_chars = padded
                self.state.name_editor_pos = min(9, len(self.state.project_name.strip()))
                self.state.name_grid_idx = 0
                self.state.name_editor_open = True
            elif p_idx == 2:  # LOAD
                ok = self.state.load_project()
                if ok:
                    for i, inst in enumerate(self.state.instruments):
                        self.audio.instruments[i].load_source(inst)
                    self.state.set_toast(f"LOADED: {self.state.project_name}")
                else:
                    self.state.set_toast("SLOT IS EMPTY")
            elif p_idx == 3:  # SAVE
                self.state.save_project()
                self.state.set_toast(f"SAVED: {self.state.project_name}")
            elif p_idx == 6:  # EXPORT MASTER WAV
                safe_nm = self.state.project_name.lower().replace(" ", "_")
                fname = f"ggrain_0{self.state.project_slot}_{safe_nm}.wav"
                self.audio.export_song_wav(fname)
                self.state.set_toast(f"EXPORTED {fname}!")
            elif p_idx == 10:  # DIRECT BOOT
                self.toggle_direct_boot()
            elif p_idx == 11:  # NEW vs EXIT
                if self.state.project_exit_mode == 0:
                    self.state.reset_project()
                    for i, inst in enumerate(self.state.instruments):
                        self.audio.instruments[i].load_source(inst)
                    self.state.set_toast("NEW EMPTY PROJECT READY")
                else:
                    self.running = False

    def _handle_credits_controls(self):
        num_pages = len(SHORTCUT_PAGES)
        _, items = SHORTCUT_PAGES[self.state.credits_page % num_pages]
        visible_rows = 10
        max_scroll = max(0, len(items) - visible_rows)

        if self.inp.pressed("LEFT"):
            self.state.credits_page = (self.state.credits_page - 1) % num_pages
            self.state.credits_scroll = 0
        elif self.inp.pressed("RIGHT"):
            self.state.credits_page = (self.state.credits_page + 1) % num_pages
            self.state.credits_scroll = 0
        elif self.inp.pressed("DOWN"):
            if self.state.credits_scroll < max_scroll:
                self.state.credits_scroll += 1
            else:
                self.state.credits_page = (self.state.credits_page + 1) % num_pages
                self.state.credits_scroll = 0
        elif self.inp.pressed("UP"):
            if self.state.credits_scroll > 0:
                self.state.credits_scroll -= 1
            else:
                self.state.credits_page = (self.state.credits_page - 1) % num_pages
                _, prev_items = SHORTCUT_PAGES[self.state.credits_page]
                self.state.credits_scroll = max(0, len(prev_items) - visible_rows)

    def _handle_song_seq_controls(self):
        # Cambia traccia solo se A non e' tenuto premuto (evita conflitti con A+L1 / A+R1)
        if not self.inp.is_held("A"):
            if self.inp.pressed("L1"):
                self.state.active_track = (self.state.active_track - 1) % 4
            elif self.inp.pressed("R1"):
                self.state.active_track = (self.state.active_track + 1) % 4

        # Stick SX = Filter Cutoff & Resonance | Stick DX = Slice Scrub & Pitch Bend
        self.state.live_filter_offset = self.inp.lx
        self.state.live_res_offset = max(0.0, -self.inp.ly * 0.6)
        self.state.live_stutter = max(0.0, self.inp.rx)
        self.state.live_pitch_bend = -self.inp.ry * 12.0

        if self.state.seq_focus == "SONG":
            b = self.state.cursor_bar
            t = self.state.active_track

            if self.inp.is_held("A"):
                if self.inp.pressed("UP"):
                    cur = self.state.song_grid[b][t]
                    new_p = self.state.last_song_pat if cur < 0 else min(7, cur + 1)
                    self.state.song_grid[b][t] = new_p
                    self.state.last_song_pat = new_p
                    self._a_used_as_mod = True
                elif self.inp.pressed("DOWN"):
                    cur = self.state.song_grid[b][t]
                    new_p = -1 if cur <= 0 else (cur - 1)
                    self.state.song_grid[b][t] = new_p
                    if new_p >= 0:
                        self.state.last_song_pat = new_p
                    self._a_used_as_mod = True
            else:
                if self.inp.pressed("UP"):
                    self.state.cursor_bar = (b - 1) % 8
                elif self.inp.pressed("DOWN"):
                    self.state.cursor_bar = (b + 1) % 8
                elif self.inp.pressed("RIGHT"):
                    if self.state.song_grid[b][t] < 0:
                        self.state.song_grid[b][t] = self.state.last_song_pat
                    self.state.seq_focus = "STEPS"

            if self.inp.released("A"):
                if not self._a_used_as_mod:
                    if self.state.song_grid[b][t] < 0:
                        self.state.song_grid[b][t] = self.state.last_song_pat
                    self.state.seq_focus = "STEPS"
                self._a_used_as_mod = False

            if self.inp.pressed("B"):
                self.state.song_grid[b][t] = -1

            if self.inp.pressed("X"):
                new_p = self.state.clone_pattern_to_next()
                self.state.last_song_pat = new_p
                self.state.set_toast(f"CLONED TO PAT 0{new_p + 1}")

        else:
            pat = self.state.get_current_pattern()
            st = pat[self.state.cursor_step]
            inst_obj = self.state.instruments[st.inst]

            if self.inp.is_held("A"):
                if self.inp.pressed("UP"):
                    st.active = True
                    if self.inp.is_held("L1"):
                        st.note = min(96, st.note + 12)
                    else:
                        st.note = quantize_to_scale(st.note + 1, inst_obj.root_note, inst_obj.scale)
                    self.state.last_step_note = st.note
                    if not self.state.playing:
                        self.audio.audition_instrument(st.inst, midi_note=st.note)
                    self._a_used_as_mod = True
                elif self.inp.pressed("DOWN"):
                    st.active = True
                    if self.inp.is_held("L1"):
                        st.note = max(24, st.note - 12)
                    else:
                        st.note = quantize_to_scale(st.note - 1, inst_obj.root_note, inst_obj.scale)
                    self.state.last_step_note = st.note
                    if not self.state.playing:
                        self.audio.audition_instrument(st.inst, midi_note=st.note)
                    self._a_used_as_mod = True
                elif self.inp.pressed("RIGHT"):
                    st.active = True
                    if self.inp.is_held("L1"):
                        st.slice_pos = min(0.9375, st.slice_pos + 0.0625)
                        self.state.last_step_slice = st.slice_pos
                    elif self.inp.is_held("R1"):
                        st.vol = min(1.0, round(st.vol + 0.1, 2))
                        self.state.last_step_vol = st.vol
                    else:
                        st.inst = (st.inst + 1) % 8
                        self.state.active_inst = st.inst
                    if not self.state.playing:
                        self.audio.audition_instrument(st.inst, midi_note=st.note)
                    self._a_used_as_mod = True
                elif self.inp.pressed("LEFT"):
                    st.active = True
                    if self.inp.is_held("L1"):
                        st.slice_pos = max(0.0, st.slice_pos - 0.0625)
                        self.state.last_step_slice = st.slice_pos
                    elif self.inp.is_held("R1"):
                        st.vol = max(0.1, round(st.vol - 0.1, 2))
                        self.state.last_step_vol = st.vol
                    else:
                        st.inst = (st.inst - 1) % 8
                        self.state.active_inst = st.inst
                    if not self.state.playing:
                        self.audio.audition_instrument(st.inst, midi_note=st.note)
                    self._a_used_as_mod = True
            else:
                if self.inp.pressed("UP"):
                    self.state.cursor_step = (self.state.cursor_step - 1) % 16
                elif self.inp.pressed("DOWN"):
                    self.state.cursor_step = (self.state.cursor_step + 1) % 16
                elif self.inp.pressed("LEFT") and not self.inp.is_held("L1") and not self.inp.is_held("R1"):
                    self.state.seq_focus = "SONG"

            if self.inp.released("A"):
                if not self._a_used_as_mod:
                    if not st.active:
                        st.active = True
                        st.inst = self.state.active_inst
                        st.note = self.state.last_step_note
                        st.slice_pos = self.state.last_step_slice
                        st.vol = self.state.last_step_vol
                        if not self.state.playing:
                            self.audio.audition_instrument(st.inst, midi_note=st.note)
                    else:
                        self.state.active_inst = st.inst
                        self.state.last_step_note = st.note
                        self.state.last_step_slice = st.slice_pos
                        self.state.last_step_vol = st.vol
                        if not self.state.playing:
                            self.audio.audition_instrument(st.inst, midi_note=st.note)
                self._a_used_as_mod = False

            if self.inp.pressed("B"):
                if st.active:
                    st.active = False
                else:
                    self.audio.audition_instrument(self.state.active_inst)

            if self.inp.pressed("X"):
                self.state.midi_step_rec = not self.state.midi_step_rec

    def _handle_synth_lab_controls(self, dt):
        sl = self.state.synth_lab

        if self.inp.pressed("L1"):
            self.state.active_inst = (self.state.active_inst - 1) % 8
        elif self.inp.pressed("R1"):
            self.state.active_inst = (self.state.active_inst + 1) % 8

        # Stick Analogici XY per scolpire il synth live
        if abs(self.inp.lx) > 0.05:
            sl.filter_cutoff = max(-1.0, min(1.0, sl.filter_cutoff + self.inp.lx * dt * 0.9))
        if abs(self.inp.ly) > 0.05:
            sl.pitch_env_amt = max(-24, min(48, int(round(-self.inp.ly * 48))))
        if abs(self.inp.rx) > 0.05:
            sl.amp_decay = max(0.05, min(1.50, sl.amp_decay + self.inp.rx * dt * 0.8))
        if abs(self.inp.ry) > 0.05:
            sl.drive_crush = max(0.0, min(1.0, sl.drive_crush - self.inp.ry * dt * 0.8))

        if self.inp.pressed("UP"):
            self.state.synth_param_idx = (self.state.synth_param_idx - 1) % 8
        elif self.inp.pressed("DOWN"):
            self.state.synth_param_idx = (self.state.synth_param_idx + 1) % 8

        p_idx = self.state.synth_param_idx
        delta = 1 if self.inp.pressed("RIGHT") else (-1 if self.inp.pressed("LEFT") else 0)

        if delta != 0:
            if p_idx == 0:
                wi = SYNTH_WAVES.index(sl.wave_type) if sl.wave_type in SYNTH_WAVES else 0
                sl.wave_type = SYNTH_WAVES[(wi + delta) % len(SYNTH_WAVES)]
            elif p_idx == 1:
                sl.sub_mix = max(0.0, min(1.0, round(sl.sub_mix + delta * 0.05, 2)))
            elif p_idx == 2:
                sl.pitch_env_amt = max(-24, min(48, sl.pitch_env_amt + delta * 2))
            elif p_idx == 3:
                sl.pitch_env_dec = max(0.02, min(0.60, round(sl.pitch_env_dec + delta * 0.02, 2)))
            elif p_idx == 4:
                sl.amp_decay = max(0.05, min(1.50, round(sl.amp_decay + delta * 0.05, 2)))
            elif p_idx == 5:
                sl.filter_cutoff = max(-1.0, min(1.0, round(sl.filter_cutoff + delta * 0.08, 2)))
            elif p_idx == 6:
                sl.drive_crush = max(0.0, min(1.0, round(sl.drive_crush + delta * 0.05, 2)))
            elif p_idx == 7:
                folders = self.state.get_synth_folders()
                sl.folder_idx = (sl.folder_idx + delta) % len(folders)
            self.audio.audition_synth_lab()

        if self.inp.pressed("B") or self.inp.pressed("A"):
            self.audio.audition_synth_lab()

        if self.inp.pressed("X"):
            rel_path = self.audio.bounce_synth_lab_wav()
            self.state.set_toast(f"SAVED {rel_path} -> I{self.state.active_inst + 1:02d}!")

    def _handle_instrument_controls(self, dt):
        inst = self.state.instruments[self.state.active_inst]

        if self.state.wav_browser_open:
            files = self.state.wav_browser_files
            if self.inp.pressed("UP") and files:
                self.state.wav_browser_idx = (self.state.wav_browser_idx - 1) % len(files)
                self.audio.load_wav_into_instrument(self.state.active_inst, files[self.state.wav_browser_idx][1])
            elif self.inp.pressed("DOWN") and files:
                self.state.wav_browser_idx = (self.state.wav_browser_idx + 1) % len(files)
                self.audio.load_wav_into_instrument(self.state.active_inst, files[self.state.wav_browser_idx][1])
            elif self.inp.pressed("A"):
                if files:
                    self.audio.load_wav_into_instrument(self.state.active_inst, files[self.state.wav_browser_idx][1])
                self.state.wav_browser_open = False
            elif self.inp.pressed("B"):
                self.state.wav_browser_open = False
            return

        if self.inp.pressed("L1"):
            self.state.active_inst = (self.state.active_inst - 1) % 8
            self._audition_if_stopped()
            return
        elif self.inp.pressed("R1"):
            self.state.active_inst = (self.state.active_inst + 1) % 8
            self._audition_if_stopped()
            return

        stick_moved = False
        if abs(self.inp.lx) > 0.05:
            inst.start_pos = max(0.0, min(0.95, inst.start_pos + self.inp.lx * dt * 0.65))
            stick_moved = True
        if abs(self.inp.ly) > 0.05:
            inst.pitch_semi = max(-24, min(24, int(round(-self.inp.ly * 24))))
            stick_moved = True
        if abs(self.inp.rx) > 0.05:
            inst.grain_size = max(0.02, min(1.0, inst.grain_size + self.inp.rx * dt * 0.75))
            stick_moved = True
        if abs(self.inp.ry) > 0.05:
            inst.spray = max(0.0, min(1.0, inst.spray - self.inp.ry * dt * 0.75))
            stick_moved = True
        if stick_moved:
            inst.dirty = True
            self._stick_audition_timer -= dt
            if self._stick_audition_timer <= 0.0:
                self._audition_if_stopped()
                self._stick_audition_timer = 0.18
        else:
            self._stick_audition_timer = 0.0

        if self.inp.pressed("UP"):
            self.state.inst_param_idx = (self.state.inst_param_idx - 1) % 8
        elif self.inp.pressed("DOWN"):
            self.state.inst_param_idx = (self.state.inst_param_idx + 1) % 8

        p_idx = self.state.inst_param_idx
        delta = 1 if self.inp.pressed("RIGHT") else (-1 if self.inp.pressed("LEFT") else 0)
        shift_a = self.inp.is_held("A")

        if delta != 0:
            if p_idx == 0:
                cur_s = SOURCE_TYPES.index(inst.source_type) if inst.source_type in SOURCE_TYPES else 0
                inst.source_type = SOURCE_TYPES[(cur_s + delta) % len(SOURCE_TYPES)]
                inst.reload_source = True
                inst.dirty = True
                self._audition_if_stopped()
            elif p_idx == 1:
                inst.source_type = "WAV"
                self.state.refresh_wav_browser()
                self.state.wav_browser_open = True
            elif p_idx == 2:
                inst.mode = "GRAIN" if inst.mode == "ONE-SHOT" else "ONE-SHOT"
                inst.dirty = True
                self._audition_if_stopped()
            elif p_idx == 3:
                if shift_a:
                    inst.root_note = max(36, min(84, inst.root_note + delta))
                else:
                    sc_i = SCALE_LIST.index(inst.scale) if inst.scale in SCALE_LIST else 0
                    inst.scale = SCALE_LIST[(sc_i + delta) % len(SCALE_LIST)]
            elif p_idx == 4:
                if shift_a:
                    inst.start_pos = max(0.0, min(0.95, round(inst.start_pos + delta * 0.05, 2)))
                else:
                    inst.pitch_semi = max(-24, min(24, inst.pitch_semi + delta))
                inst.dirty = True
                self._audition_if_stopped()
            elif p_idx == 5:
                if shift_a:
                    inst.spray = max(0.0, min(1.0, round(inst.spray + delta * 0.05, 2)))
                else:
                    inst.grain_size = max(0.02, min(1.0, round(inst.grain_size + delta * 0.05, 2)))
                inst.dirty = True
                self._audition_if_stopped()
            elif p_idx == 6:
                if shift_a:
                    inst.filter_res = max(0.0, min(0.9, round(inst.filter_res + delta * 0.05, 2)))
                else:
                    inst.filter_cutoff = max(-1.0, min(1.0, round(inst.filter_cutoff + delta * 0.08, 2)))
                inst.dirty = True
                self._audition_if_stopped()
            elif p_idx == 7:
                if shift_a:
                    inst.lfo_depth = max(0.0, min(1.0, round(inst.lfo_depth + delta * 0.08, 2)))
                else:
                    inst.lfo_speed = max(0.2, min(15.0, round(inst.lfo_speed + delta * 0.4, 1)))
                inst.dirty = True
                self._audition_if_stopped()

        if self.inp.pressed("A") and p_idx in (0, 1) and inst.source_type == "WAV":
            self.state.refresh_wav_browser()
            self.state.wav_browser_open = True

        if self.inp.pressed("B"):
            self.audio.audition_instrument(self.state.active_inst)

        if self.inp.pressed("X"):
            if self.state.mic_connected or self.state.mic_recording:
                self.state.mic_recording = not self.state.mic_recording
                if self.state.mic_recording:
                    self.state.set_toast("RECORDING FROM USB MIC...")
            else:
                self.state.set_toast("NO USB MIC ON OTG PORT")

    def _handle_mastering_controls(self, dt):
        mfx = self.state.master_fx

        if abs(self.inp.lx) > 0.05:
            mfx.chorus_mix = max(0.0, min(1.0, mfx.chorus_mix + self.inp.lx * dt * 0.6))
        if abs(self.inp.ly) > 0.05:
            mfx.reverb_mix = max(0.0, min(1.0, mfx.reverb_mix - self.inp.ly * dt * 0.6))
        if abs(self.inp.rx) > 0.05:
            old_drv = mfx.tape_drive
            mfx.tape_drive = max(0.0, min(1.0, mfx.tape_drive + self.inp.rx * dt * 0.6))
            if abs(mfx.tape_drive - old_drv) > 0.03:
                for inst in self.state.instruments:
                    inst.dirty = True
        if abs(self.inp.ry) > 0.05:
            mfx.comp_thresh = max(0.2, min(1.0, mfx.comp_thresh - self.inp.ry * dt * 0.6))

        if self.inp.pressed("UP"):
            self.state.master_param_idx = (self.state.master_param_idx - 1) % 5
        elif self.inp.pressed("DOWN"):
            self.state.master_param_idx = (self.state.master_param_idx + 1) % 5

        p_idx = self.state.master_param_idx
        delta = 1 if self.inp.pressed("RIGHT") else (-1 if self.inp.pressed("LEFT") else 0)
        shift_a = self.inp.is_held("A")

        if delta != 0:
            if p_idx == 0:
                mfx.chorus_mix = max(0.0, min(1.0, round(mfx.chorus_mix + delta * 0.05, 2)))
            elif p_idx == 1:
                if shift_a:
                    mfx.reverb_size = max(0.0, min(1.0, round(mfx.reverb_size + delta * 0.05, 2)))
                else:
                    mfx.reverb_mix = max(0.0, min(1.0, round(mfx.reverb_mix + delta * 0.05, 2)))
            elif p_idx == 2:
                mfx.tape_drive = max(0.0, min(1.0, round(mfx.tape_drive + delta * 0.05, 2)))
                for inst in self.state.instruments:
                    inst.dirty = True
            elif p_idx == 3:
                if shift_a:
                    mfx.master_vol = max(0.1, min(1.0, round(mfx.master_vol + delta * 0.05, 2)))
                else:
                    mfx.comp_thresh = max(0.2, min(1.0, round(mfx.comp_thresh + delta * 0.05, 2)))
            elif p_idx == 4:
                self.state.sync_out_2ppqn = not self.state.sync_out_2ppqn

        if self.inp.pressed("X"):
            mfx.bypass = not mfx.bypass
            for inst in self.state.instruments:
                inst.dirty = True

    def run(self):
        self.run_splash()
        last_t = time.perf_counter()

        while self.running:
            now = time.perf_counter()
            dt = min(0.05, now - last_t)
            last_t = now

            if self.state.toast_timer > 0.0:
                self.state.toast_timer = max(0.0, self.state.toast_timer - dt)

            events = pygame.event.get()
            for ev in events:
                if ev.type == pygame.QUIT:
                    self.running = False

            self.inp.update(events, dt)
            self._process_hardware_events()

            if not self.inp.debug_mode:
                if not self._handle_global_controls():
                    scr = self.state.active_screen
                    if scr == "SONG_SEQ":
                        self._handle_song_seq_controls()
                    elif scr == "SYNTH_LAB":
                        self._handle_synth_lab_controls(dt)
                    elif scr == "INSTRUMENT":
                        self._handle_instrument_controls(dt)
                    elif scr == "MASTERING":
                        self._handle_mastering_controls(dt)
                    elif scr == "PROJECT":
                        self._handle_project_controls()
                    elif scr == "CREDITS":
                        self._handle_credits_controls()

            self.audio.update()
            fps = self.clock.get_fps()
            self.ui.render(self.inp, fps, self.get_y_menu_items(), self.is_direct_boot_enabled())

            pygame.display.flip()
            self.clock.tick(60)

        self.hw.shutdown()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    app = GGrainApp()
    app.run()