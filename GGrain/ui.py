import os
import math
import random
import pygame
from state import (
    midi_to_name, SYNTH_FOLDERS,
    THEME_BG_CHOICES, THEME_INK_CHOICES, THEME_ACCENT_CHOICES
)
from audio_dsp import HAS_NUMPY

COL_GREEN = (46, 213, 115)

NAME_GRID_CHARS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
    "U", "V", "W", "X", "Y", "Z", "0", "1", "2", "3",
    "4", "5", "6", "7", "8", "9", "-", "_", "<", "OK",
]

SHORTCUT_PAGES = [
    ("1: GLOBAL & CROSS", [
        ("START", "Loop Current Bar (Play/Stop)"),
        ("R1 + START", "Play Full Song Chain (01-08)"),
        ("SELECT + UP", "1: Project, Rename & Theme"),
        ("SELECT + LEFT", "2: Song & 16-Step Sequencer"),
        ("SEL + LEFT x2", "2B: Mini-Synth & WAV Creator"),
        ("SELECT + RIGHT", "3: Instrument Studio (Auto)"),
        ("SEL + RIGHT x2", "3B: Credits & Shortcut Manual"),
        ("SELECT + DOWN", "4: Master Bus FX & Hardware"),
        ("L3 / SEL + B", "Mute / Unmute Active Track"),
        ("R3", "Audition Active Inst / Synth"),
        ("Y", "Open Context Workflow Tools"),
        ("L2 + R2 + SEL", "Dev Gamepad & Telemetry Test"),
        ("SEL + START/FN", "Safe Exit to KNULLI OS"),
    ]),
    ("2: SONG & SEQUENCER", [
        ("L1 / R1", "Switch Active Track (T1 - T4)"),
        ("LEFT / RIGHT", "Focus: Song Matrix <-> Steps"),
        ("A (TAP)", "Add Step / Pick & Audition"),
        ("A + UP/DOWN", "Step Note (Scale Quantized)"),
        ("A + L1 + U/D", "Step Pitch +/-1 Octave (12st)"),
        ("A + LEFT/RIGHT", "Assign Instrument (I01-I08)"),
        ("A + L1 + L/R", "Adjust Sample Slice Offset"),
        ("A + R1 + L/R", "Adjust Step Level / Volume"),
        ("B", "Clear Step / Audition Inst"),
        ("X (ON SONG)", "Clone Pattern to Next Slot"),
        ("X / X+U/D (STEPS)", "Select Block -> Copy / Paste"),
        ("L-STICK X/Y", "Live Filter Cutoff & Res"),
        ("R-STICK X/Y", "Live Slice Scrub & Pitch Bend"),
    ]),
    ("3: INST & SYNTH LAB", [
        ("L1 / R1", "Select Inst Slot (I01 - I08)"),
        ("UP / DOWN", "Select Parameter Row"),
        ("LEFT / RIGHT", "Edit Parameter Value"),
        ("A + LEFT/RIGHT", "Sub-Param (Root/Start/Spray)"),
        ("A (ON WAV)", "Open Ableton-Safe WAV Browser"),
        ("B", "Audition Sound (When Stopped)"),
        ("X (INSTRUMENT)", "Rec / Auto-Trim USB Mic WAV"),
        ("X (SYNTH LAB)", "Bounce Synth WAV to Inst"),
        ("Y", "Reset Params / Synth Presets"),
        ("L-STICK X/Y", "Start/Pitch (or Filter/Punch)"),
        ("R-STICK X/Y", "Grain/Spray (or Decay/Crush)"),
    ]),
    ("4: MASTER & PROJECT", [
        ("UP / DOWN", "Select FX or System Option"),
        ("LEFT / RIGHT", "Adjust Value / Slot / BPM"),
        ("A + LEFT/RIGHT", "Sub-Param (Rev/Vol/BPM+/-10)"),
        ("X (MASTERING)", "Instant A/B Bypass Master FX"),
        ("Y (MASTERING)", "Reset Master Chain / Sync"),
        ("L-STICK X/Y", "Live Stereo Chorus & Reverb"),
        ("R-STICK X/Y", "Live Tape Drive & Comp Thresh"),
        ("A (PROJECT)", "Rename / Load / Save / Export"),
        ("L/R (THEME)", "Change Base / Text / Accent"),
    ]),
]


class SplashParticle:
    def __init__(self, w, h):
        self.x = random.uniform(0, w)
        self.y = random.uniform(0, h)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(18.0, 55.0)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.is_red = random.random() < 0.65
        self.radius = 2 if self.is_red else 1

    def update(self, dt, w, h):
        self.x = (self.x + self.vx * dt) % w
        self.y = (self.y + self.vy * dt) % h


class UIRenderer:
    def __init__(self, screen, state, audio, hw):
        self.screen = screen
        self.state = state
        self.audio = audio
        self.hw = hw
        self.w, self.h = screen.get_size()  # 640x480

        pygame.font.init()
        font_stack = "dejavusansmono,consolas,liberationmono,monospace"
        self.f_xs = pygame.font.SysFont(font_stack, 11)
        self.f_sm = pygame.font.SysFont(font_stack, 13)
        self.f_md = pygame.font.SysFont(font_stack, 15, bold=True)
        self.f_lg = pygame.font.SysFont(font_stack, 20, bold=True)
        self.f_title = pygame.font.SysFont(font_stack, 54, bold=True)

        self.particles = [SplashParticle(self.w, self.h) for _ in range(44)]
        self._sync_theme()

    def _sync_theme(self):
        bg = THEME_BG_CHOICES[self.state.theme_bg_idx % len(THEME_BG_CHOICES)][1]
        ink = THEME_INK_CHOICES[self.state.theme_ink_idx % len(THEME_INK_CHOICES)][1]
        acc = THEME_ACCENT_CHOICES[self.state.theme_accent_idx % len(THEME_ACCENT_CHOICES)][1]

        lum_bg = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        step = -14 if lum_bg > 128 else 11

        def shift(c, amt):
            return tuple(max(0, min(255, int(v + amt))) for v in c)

        self.c_bg = bg
        self.c_surface = shift(bg, step)
        self.c_panel = shift(bg, step * 2)
        self.c_border = shift(bg, step * 3.5)
        self.c_white = ink
        self.c_muted = tuple(int(ink[i] * 0.48 + bg[i] * 0.52) for i in range(3))
        self.c_red = acc
        self.c_red_dim = tuple(int(acc[i] * 0.36 + bg[i] * 0.64) for i in range(3))
        self.c_green = COL_GREEN

    # ==========================================================================
    # SCHERMATA 0: SPLASH ARCADE (Gas1312)
    # ==========================================================================

    def draw_splash(self, dt, elapsed):
        self._sync_theme()
        self.screen.fill(self.c_bg)

        for p in self.particles:
            p.update(dt, self.w, self.h)

        n = len(self.particles)
        for i in range(n):
            p1 = self.particles[i]
            for j in range(i + 1, n):
                p2 = self.particles[j]
                dx = p1.x - p2.x
                dy = p1.y - p2.y
                if dx * dx + dy * dy < 8500:
                    col = self.c_red_dim if (p1.is_red or p2.is_red) else self.c_panel
                    pygame.draw.line(self.screen, col, (int(p1.x), int(p1.y)), (int(p2.x), int(p2.y)), 1)
            c = self.c_red if p1.is_red else self.c_white
            pygame.draw.circle(self.screen, c, (int(p1.x), int(p1.y)), p1.radius)

        box = pygame.Rect(140, 155, 360, 165)
        pygame.draw.rect(self.screen, self.c_surface, box, border_radius=6)
        pygame.draw.rect(self.screen, self.c_red, box, 2, border_radius=6)

        t_shadow = self.f_title.render("GGrain", True, self.c_red_dim)
        t_main = self.f_title.render("GGrain", True, self.c_white)
        self.screen.blit(t_shadow, (self.w // 2 - t_main.get_width() // 2 + 3, 174))
        self.screen.blit(t_main, (self.w // 2 - t_main.get_width() // 2, 171))

        sub = self.f_sm.render("GRANULAR WORKSTATION // TRACKER v1.0", True, self.c_muted)
        self.screen.blit(sub, (self.w // 2 - sub.get_width() // 2, 240))

        sig = self.f_md.render("produced by Gas1312", True, self.c_red)
        self.screen.blit(sig, (self.w // 2 - sig.get_width() // 2, 272))

        prog = min(1.0, elapsed / 2.0)
        bar_bg = pygame.Rect(180, 304, 280, 4)
        pygame.draw.rect(self.screen, self.c_border, bar_bg)
        pygame.draw.rect(self.screen, self.c_red, (180, 304, int(280 * prog), 4))

    # ==========================================================================
    # BARRA SUPERIORE FISSA
    # ==========================================================================

    def draw_top_bar(self):
        pygame.draw.rect(self.screen, self.c_surface, (0, 0, self.w, 36))
        pygame.draw.line(self.screen, self.c_border, (0, 36), (self.w, 36), 1)

        logo = self.f_md.render("GGrain", True, self.c_white)
        self.screen.blit(logo, (10, 9))

        bpm_txt = self.f_sm.render(f"{self.state.bpm}", True, self.c_muted)
        self.screen.blit(bpm_txt, (72, 11))

        run_col = self.c_red if self.state.playing else self.c_panel
        run_txt_col = self.c_white if self.state.playing else self.c_muted
        run_label = ("LOOP" if self.state.loop_bar_mode else "SONG") if self.state.playing else "HOLD"
        pygame.draw.rect(self.screen, run_col, (104, 8, 42, 20), border_radius=3)
        r_surf = self.f_xs.render(run_label, True, run_txt_col)
        self.screen.blit(r_surf, (125 - r_surf.get_width() // 2, 12))

        # Mini-Mappa a Croce Estesa
        cx, cy = 186, 18
        scr = self.state.active_screen
        nodes = [
            ("SYNTH_LAB", (cx - 24, cy - 3, 6, 6)),
            ("SONG_SEQ", (cx - 15, cy - 4, 8, 8)),
            ("PROJECT", (cx - 4, cy - 13, 8, 8)),
            ("MASTERING", (cx - 4, cy + 5, 8, 8)),
            ("INSTRUMENT", (cx + 7, cy - 4, 8, 8)),
            ("CREDITS", (cx + 18, cy - 3, 6, 6)),
        ]
        for name, rect in nodes:
            c = self.c_red if scr == name else self.c_border
            pygame.draw.rect(self.screen, c, rect, border_radius=1)

        room_names = {
            "PROJECT": "1:PROJECT",
            "SONG_SEQ": "2:SONG/SEQ",
            "INSTRUMENT": "3:INSTRUMENT",
            "MASTERING": "4:MASTERING",
            "SYNTH_LAB": "2B:SYNTH LAB",
            "CREDITS": "3B:SHORTCUTS",
        }
        r_name = self.f_sm.render(room_names.get(scr, scr), True, self.c_white)
        self.screen.blit(r_name, (220, 10))

        # Spie Hardware [MIC] e [MIDI]
        mic_bg = self.c_red if self.state.mic_recording else (self.c_white if self.state.mic_connected else self.c_panel)
        mic_fg = self.c_white if self.state.mic_recording else (self.c_bg if self.state.mic_connected else self.c_muted)
        pygame.draw.rect(self.screen, mic_bg, (382, 8, 38, 20), border_radius=3)
        m_s = self.f_xs.render("MIC", True, mic_fg)
        self.screen.blit(m_s, (401 - m_s.get_width() // 2, 12))

        midi_active = self.state.midi_activity > 0.1
        midi_bg = self.c_red if midi_active else (self.c_white if self.state.midi_connected else self.c_panel)
        midi_fg = self.c_white if midi_active else (self.c_bg if self.state.midi_connected else self.c_muted)
        pygame.draw.rect(self.screen, midi_bg, (426, 8, 42, 20), border_radius=3)
        md_s = self.f_xs.render("MIDI", True, midi_fg)
        self.screen.blit(md_s, (447 - md_s.get_width() // 2, 12))

        # VU-Meter Stereo Master
        vu_x = 480
        pygame.draw.rect(self.screen, self.c_panel, (vu_x, 10, 84, 6))
        pygame.draw.rect(self.screen, self.c_panel, (vu_x, 20, 84, 6))
        wl = int(min(1.0, self.state.vu_left) * 84)
        wr = int(min(1.0, self.state.vu_right) * 84)
        if wl > 0:
            pygame.draw.rect(self.screen, self.c_red if wl > 72 else self.c_white, (vu_x, 10, wl, 6))
        if wr > 0:
            pygame.draw.rect(self.screen, self.c_red if wr > 72 else self.c_white, (vu_x, 20, wr, 6))

        # Batteria R36S
        bat = self.hw.battery_pct
        b_col = self.c_red if bat < 20 else (self.c_green if self.hw.battery_charging else self.c_white)
        bat_s = self.f_xs.render(f"{bat}%", True, b_col)
        self.screen.blit(bat_s, (self.w - bat_s.get_width() - 10, 12))

    # ==========================================================================
    # STANZA 1: PROJECT, SYSTEM & 3-COLOR THEME (SELECT + SU)
    # ==========================================================================

    def draw_project_room(self, direct_boot_enabled):
        left_box = pygame.Rect(12, 44, 386, 408)
        pygame.draw.rect(self.screen, self.c_surface, left_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, left_box, 1, border_radius=4)

        self.screen.blit(self.f_sm.render("PROJECT, SYSTEM & 3-COLOR THEME", True, self.c_white), (24, 50))

        slot_saved_name = self.state.get_slot_display_name(self.state.project_slot)
        slot_status = f"[{slot_saved_name}]" if slot_saved_name else "[EMPTY]"
        exit_lbl = "NEW EMPTY PROJECT" if self.state.project_exit_mode == 0 else "EXIT TO KNULLI OS"

        bg_name, bg_col = THEME_BG_CHOICES[self.state.theme_bg_idx % len(THEME_BG_CHOICES)]
        ink_name, ink_col = THEME_INK_CHOICES[self.state.theme_ink_idx % len(THEME_INK_CHOICES)]
        acc_name, acc_col = THEME_ACCENT_CHOICES[self.state.theme_accent_idx % len(THEME_ACCENT_CHOICES)]

        items = [
            ("01. PROJECT SLOT", f"SLOT 0{self.state.project_slot} {slot_status}", None),
            ("02. PROJECT NAME", f"\"{self.state.project_name}\"  [PRESS A TO RENAME]", None),
            ("03. LOAD PROJECT", f"LOAD SLOT 0{self.state.project_slot} FROM SD", None),
            ("04. SAVE PROJECT", f"WRITE \"{self.state.project_name}\" -> SLOT 0{self.state.project_slot}", None),
            ("05. MASTER TEMPO", f"{self.state.bpm} BPM (A+L/R: +/-10)", None),
            ("06. GROOVE SWING", f"{int(self.state.swing * 100)}%", None),
            ("07. EXPORT MASTER WAV", f"ggrain_0{self.state.project_slot}_{self.state.project_name.lower()}.wav", None),
            ("08. THEME: BASE / BG", f"< {bg_name} >", bg_col),
            ("09. THEME: TEXT / INK", f"< {ink_name} >", ink_col),
            ("10. THEME: ACCENT", f"< {acc_name} >", acc_col),
            ("11. R36S DIRECT BOOT", "ENABLED (BOOT GGRAIN)" if direct_boot_enabled else "OFF (EMULATIONSTATION)", None),
            ("12. SESSION ACTION", f"< {exit_lbl} > [A]", None),
        ]

        iy = 70
        for idx, (k, v, swatch) in enumerate(items):
            is_cur = (idx == self.state.project_param_idx)
            r = pygame.Rect(20, iy, 370, 29)
            if is_cur:
                pygame.draw.rect(self.screen, self.c_panel, r, border_radius=3)
                pygame.draw.rect(self.screen, self.c_red, r, 1, border_radius=3)
            ks = self.f_xs.render(k, True, self.c_red if is_cur else self.c_muted)
            vs = self.f_xs.render(v, True, self.c_white if is_cur else self.c_muted)
            self.screen.blit(ks, (28, iy + 2))
            self.screen.blit(vs, (28, iy + 15))
            if swatch is not None:
                sw_rect = pygame.Rect(354, iy + 5, 26, 19)
                pygame.draw.rect(self.screen, swatch, sw_rect, border_radius=3)
                pygame.draw.rect(self.screen, self.c_white, sw_rect, 1, border_radius=3)
            iy += 31

        # Pannello Destro: Stato e Nomi degli 8 Slot di Memoria
        right_box = pygame.Rect(408, 44, 220, 408)
        pygame.draw.rect(self.screen, self.c_surface, right_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, right_box, 1, border_radius=4)

        self.screen.blit(self.f_sm.render("SD MEMORY SLOTS", True, self.c_white), (420, 52))
        sy = 82
        for s in range(1, 9):
            saved_nm = self.state.get_slot_display_name(s)
            is_sel = (s == self.state.project_slot)
            sr = pygame.Rect(420, sy, 196, 38)
            pygame.draw.rect(self.screen, self.c_red_dim if is_sel else self.c_bg, sr, border_radius=3)
            pygame.draw.rect(self.screen, self.c_red if is_sel else self.c_border, sr, 1, border_radius=3)

            lbl = self.f_sm.render(f"0{s}:", True, self.c_white)
            st_txt = saved_nm if saved_nm else "--- FREE ---"
            st_col = self.c_green if saved_nm else self.c_muted
            st = self.f_sm.render(st_txt, True, st_col)
            self.screen.blit(lbl, (430, sy + 11))
            self.screen.blit(st, (462, sy + 11))
            sy += 45

    def draw_name_editor_overlay(self):
        ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        ov.fill((5, 5, 7, 225))
        self.screen.blit(ov, (0, 0))

        modal = pygame.Rect(110, 88, 420, 298)
        pygame.draw.rect(self.screen, self.c_surface, modal, border_radius=6)
        pygame.draw.rect(self.screen, self.c_red, modal, 2, border_radius=6)

        hdr = self.f_md.render("RENAME PROJECT (LSDJ CHARACTER GRID)", True, self.c_white)
        self.screen.blit(hdr, (modal.centerx - hdr.get_width() // 2, 102))

        # 10 Caselle del Nome Progetto
        start_nx = 142
        for i in range(10):
            bx = start_nx + i * 36
            box = pygame.Rect(bx, 134, 32, 34)
            is_cur = (i == self.state.name_editor_pos)
            pygame.draw.rect(self.screen, self.c_red_dim if is_cur else self.c_bg, box, border_radius=3)
            pygame.draw.rect(self.screen, self.c_red if is_cur else self.c_border, box, 2 if is_cur else 1, border_radius=3)
            ch = self.state.name_editor_chars[i] if i < len(self.state.name_editor_chars) else " "
            cs = self.f_md.render(ch, True, self.c_white)
            self.screen.blit(cs, (box.centerx - cs.get_width() // 2, box.centery - cs.get_height() // 2))

        # Griglia 4x10 Caratteri
        gx0, gy0 = 132, 184
        for idx, ch in enumerate(NAME_GRID_CHARS):
            row = idx // 10
            col = idx % 10
            cx = gx0 + col * 38
            cy = gy0 + row * 30
            cell = pygame.Rect(cx, cy, 34, 25)
            is_sel = (idx == self.state.name_grid_idx)
            if is_sel:
                pygame.draw.rect(self.screen, self.c_red, cell, border_radius=3)
            else:
                pygame.draw.rect(self.screen, self.c_panel, cell, border_radius=3)
            ts = self.f_xs.render(ch, True, self.c_white if is_sel else self.c_muted)
            self.screen.blit(ts, (cell.centerx - ts.get_width() // 2, cell.centery - ts.get_height() // 2))

        tip = self.f_xs.render("DPAD:MOVE  A:PICK  B:DEL  L1/R1:CURSOR  START:CONFIRM", True, self.c_muted)
        self.screen.blit(tip, (modal.centerx - tip.get_width() // 2, 356))

    # ==========================================================================
    # STANZA 2: SONG & SEQ (IBRIDO M8 + NANOLOOP)
    # ==========================================================================

    def draw_song_seq(self):
        left_rect = pygame.Rect(8, 44, 212, 408)
        pygame.draw.rect(self.screen, self.c_surface, left_rect, border_radius=4)
        border_l = self.c_red if self.state.seq_focus == "SONG" else self.c_border
        pygame.draw.rect(self.screen, border_l, left_rect, 1, border_radius=4)

        hdr = self.f_xs.render("SONG CHAIN (8 BARS)", True, self.c_muted)
        self.screen.blit(hdr, (18, 52))

        col_w = 40
        start_x = 44
        for t in range(4):
            tx = start_x + t * col_w
            is_act = (t == self.state.active_track)
            if is_act:
                pygame.draw.rect(self.screen, self.c_red_dim, (tx, 72, 36, 22), border_radius=3)
            label = f"T{t + 1}"
            if self.state.track_muted[t]:
                label = "MT"
            elif self.state.track_solo[t]:
                label = f"S{t + 1}"
            t_col = self.c_red if self.state.track_muted[t] else (self.c_white if is_act else self.c_muted)
            ts = self.f_sm.render(label, True, t_col)
            self.screen.blit(ts, (tx + 18 - ts.get_width() // 2, 76))

        row_h = 38
        start_y = 102
        for b in range(self.state.SONG_BARS):
            ry = start_y + b * row_h
            is_play_bar = (self.state.playing and self.state.current_bar == b)
            if is_play_bar:
                pygame.draw.rect(self.screen, self.c_red_dim, (12, ry, 204, row_h - 4), border_radius=3)
                pygame.draw.rect(self.screen, self.c_red, (12, ry, 3, row_h - 4))

            b_lbl = self.f_xs.render(f"0{b + 1}", True, self.c_white if is_play_bar else self.c_muted)
            self.screen.blit(b_lbl, (20, ry + 11))

            for t in range(4):
                cx = start_x + t * col_w
                cell_rect = pygame.Rect(cx, ry + 2, 36, row_h - 8)
                pat_val = self.state.song_grid[b][t]
                is_cursor = (b == self.state.cursor_bar and t == self.state.active_track)

                if is_cursor:
                    fill_c = self.c_red if self.state.seq_focus == "SONG" else self.c_panel
                    pygame.draw.rect(self.screen, fill_c, cell_rect, border_radius=3)
                    pygame.draw.rect(self.screen, self.c_white, cell_rect, 1, border_radius=3)
                else:
                    pygame.draw.rect(self.screen, self.c_panel if pat_val >= 0 else self.c_bg, cell_rect, border_radius=3)

                txt = f"0{pat_val + 1}" if pat_val >= 0 else "--"
                txt_c = self.c_white if (pat_val >= 0 or is_cursor) else self.c_muted
                cs = self.f_sm.render(txt, True, txt_c)
                self.screen.blit(cs, (cx + 18 - cs.get_width() // 2, ry + 10))

        tip_l = self.f_xs.render("X:CLONE  SEL+SX+SX:SYNTH", True, self.c_muted)
        self.screen.blit(tip_l, (18, 426))

        right_rect = pygame.Rect(228, 44, 404, 408)
        pygame.draw.rect(self.screen, self.c_surface, right_rect, border_radius=4)
        border_r = self.c_red if self.state.seq_focus == "STEPS" else self.c_border
        pygame.draw.rect(self.screen, border_r, right_rect, 1, border_radius=4)

        pat_idx = self.state.get_active_pattern_index()
        cur_pat = self.state.get_current_pattern()
        sel_step = cur_pat[self.state.cursor_step]
        inst_obj = self.state.instruments[sel_step.inst]

        hdr_r = self.f_sm.render(
            f"TRK T{self.state.active_track + 1} [PAT 0{pat_idx + 1}]  |  {inst_obj.name}: {inst_obj.sample_name}",
            True, self.c_white
        )
        self.screen.blit(hdr_r, (238, 51))

        if self.state.midi_step_rec:
            pygame.draw.rect(self.screen, self.c_red, (554, 49, 70, 18), border_radius=3)
            mr = self.f_xs.render("MIDI REC", True, self.c_white)
            self.screen.blit(mr, (589 - mr.get_width() // 2, 52))

        cols_y = 72
        self.screen.blit(self.f_xs.render("STP", True, self.c_muted), (238, cols_y))
        self.screen.blit(self.f_xs.render("NOTE", True, self.c_muted), (274, cols_y))
        self.screen.blit(self.f_xs.render("INST", True, self.c_muted), (324, cols_y))
        self.screen.blit(self.f_xs.render("SLICE / POS", True, self.c_muted), (376, cols_y))
        self.screen.blit(self.f_xs.render("LEVEL", True, self.c_muted), (510, cols_y))

        s_start_y = 90
        s_row_h = 21
        for s in range(16):
            sy = s_start_y + s * s_row_h
            st = cur_pat[s]
            is_play_step = (
                self.state.playing
                and self.state.current_bar == self.state.cursor_bar
                and self.state.current_step == s
            )
            is_cur_step = (s == self.state.cursor_step)

            is_block_sel = False
            if self.state.step_sel_active and self.state.seq_focus == "STEPS":
                lo = min(self.state.step_sel_anchor, self.state.step_sel_end)
                hi = max(self.state.step_sel_anchor, self.state.step_sel_end)
                is_block_sel = (lo <= s <= hi)

            row_rect = pygame.Rect(234, sy, 392, s_row_h - 2)
            if is_block_sel or is_play_step:
                pygame.draw.rect(self.screen, self.c_red_dim, row_rect, border_radius=2)
            elif s % 4 == 0:
                pygame.draw.rect(self.screen, self.c_panel, row_rect, border_radius=2)

            if is_block_sel:
                pygame.draw.line(self.screen, self.c_red, (236, sy + s_row_h - 3), (624, sy + s_row_h - 3), 2)

            if is_cur_step and self.state.seq_focus == "STEPS":
                pygame.draw.rect(self.screen, self.c_red, row_rect, 1, border_radius=2)

            num_c = self.c_red if is_play_step else (self.c_white if s % 4 == 0 else self.c_muted)
            self.screen.blit(self.f_xs.render(f"{s + 1:02d}", True, num_c), (240, sy + 3))

            note_str = midi_to_name(st.note) if st.active else "---"
            note_c = self.c_white if st.active else self.c_muted
            self.screen.blit(self.f_sm.render(note_str, True, note_c), (274, sy + 2))

            inst_str = f"I{st.inst + 1:02d}" if st.active else "..."
            inst_c = self.c_red if (st.active and is_cur_step) else (self.c_white if st.active else self.c_muted)
            self.screen.blit(self.f_xs.render(inst_str, True, inst_c), (326, sy + 3))

            sl_bg = pygame.Rect(376, sy + 5, 118, 9)
            pygame.draw.rect(self.screen, self.c_bg, sl_bg)
            pygame.draw.rect(self.screen, self.c_border, sl_bg, 1)
            if st.active:
                pos_x = 378 + int(st.slice_pos * 104)
                pygame.draw.rect(self.screen, self.c_white, (pos_x, sy + 6, 10, 7))

            vl_bg = pygame.Rect(510, sy + 5, 108, 9)
            pygame.draw.rect(self.screen, self.c_bg, vl_bg)
            pygame.draw.rect(self.screen, self.c_border, vl_bg, 1)
            if st.active:
                vw = int(st.vol * 106)
                pygame.draw.rect(self.screen, self.c_red if is_cur_step else self.c_white, (511, sy + 6, vw, 7))

        if (
            abs(self.state.live_filter_offset) > 0.05
            or abs(self.state.live_pitch_bend) > 0.2
            or self.state.live_stutter > 0.05
        ):
            macro_txt = (
                f"LIVE STICKS >> FLT:{self.state.live_filter_offset:+.2f}  "
                f"BEND:{self.state.live_pitch_bend:+.1f}st  SCRUB:{int(self.state.live_stutter * 100)}%"
            )
            ms = self.f_xs.render(macro_txt, True, self.c_red)
            self.screen.blit(ms, (238, 430))

    # ==========================================================================
    # STANZA 2B: SYNTH LAB & WAV CREATOR (SELECT + SINISTRA + SINISTRA)
    # ==========================================================================

    def draw_synth_lab(self):
        sl = self.state.synth_lab
        folders = self.state.get_synth_folders()
        folder_name = folders[sl.folder_idx % len(folders)]

        left_box = pygame.Rect(12, 46, 344, 404)
        pygame.draw.rect(self.screen, self.c_surface, left_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, left_box, 1, border_radius=4)

        self.screen.blit(self.f_md.render("MINI-SYNTH & WAV CREATOR", True, self.c_white), (24, 56))

        flt_s = "FLAT" if abs(sl.filter_cutoff) <= 0.03 else (
            f"LP {int(abs(sl.filter_cutoff) * 100)}%" if sl.filter_cutoff < 0 else f"HP {int(sl.filter_cutoff * 100)}%"
        )

        params = [
            ("1. OSCILLATOR WAVE", sl.wave_type),
            ("2. SUB OCTAVE (-1 OCT)", f"{int(sl.sub_mix * 100)}%"),
            ("3. PITCH ENV (PUNCH/ZAP)", f"{sl.pitch_env_amt:+d} st"),
            ("4. PITCH ENV DECAY", f"{int(sl.pitch_env_dec * 1000)} ms"),
            ("5. AMP LENGTH / DECAY", f"{int(sl.amp_decay * 1000)} ms"),
            ("6. TONE FILTER LP/HP", flt_s),
            ("7. DRIVE & 8-BIT CRUSH", f"{int(sl.drive_crush * 100)}%"),
            ("8. TARGET WAV FOLDER", f"samples/{folder_name}/"),
        ]

        py = 86
        for idx, (k, v) in enumerate(params):
            is_cur = (idx == self.state.synth_param_idx)
            r = pygame.Rect(22, py, 324, 41)
            if is_cur:
                pygame.draw.rect(self.screen, self.c_panel, r, border_radius=3)
                pygame.draw.rect(self.screen, self.c_red, r, 1, border_radius=3)
            ks = self.f_xs.render(k, True, self.c_red if is_cur else self.c_muted)
            vs = self.f_sm.render(v, True, self.c_white if is_cur else self.c_muted)
            self.screen.blit(ks, (32, py + 4))
            self.screen.blit(vs, (32, py + 20))
            py += 44

        right_box = pygame.Rect(366, 46, 262, 404)
        pygame.draw.rect(self.screen, self.c_surface, right_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, right_box, 1, border_radius=4)

        self.screen.blit(self.f_xs.render("OSCILLOSCOPE PREVIEW (C4)", True, self.c_muted), (380, 58))
        scope = pygame.Rect(380, 80, 234, 130)
        pygame.draw.rect(self.screen, self.c_bg, scope, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, scope, 1, border_radius=4)
        pygame.draw.line(self.screen, self.c_panel, (scope.left, scope.centery), (scope.right, scope.centery), 1)

        pts = []
        for x_i in range(scope.width - 8):
            ph = (x_i / float(scope.width - 8)) * 2.0
            p_mod = ph % 1.0
            if sl.wave_type == "SINE":
                val = math.sin(2.0 * math.pi * p_mod)
            elif sl.wave_type == "SQUARE":
                val = 1.0 if p_mod < 0.5 else -1.0
            elif sl.wave_type == "PULSE25":
                val = 1.0 if p_mod < 0.25 else -1.0
            elif sl.wave_type == "SAW":
                val = 2.0 * p_mod - 1.0
            elif sl.wave_type == "TRIANGLE":
                val = 4.0 * abs(p_mod - 0.5) - 1.0
            else:
                val = math.sin(x_i * 1.9) * math.cos(x_i * 0.7)
            sub_v = math.sin(math.pi * ph) * sl.sub_mix
            comb = max(-1.0, min(1.0, val * (1.0 - sl.sub_mix * 0.35) + sub_v))
            if sl.drive_crush > 0.02:
                drv = 1.0 + sl.drive_crush * 4.0
                comb = math.tanh(comb * drv) / math.tanh(drv)
            py_pt = int(scope.centery - comb * (scope.height // 2 - 12))
            pts.append((scope.left + 4 + x_i, py_pt))

        if len(pts) > 1:
            pygame.draw.lines(self.screen, self.c_red, False, pts, 2)

        dest_box = pygame.Rect(380, 224, 234, 128)
        pygame.draw.rect(self.screen, self.c_panel, dest_box, border_radius=4)
        self.screen.blit(self.f_xs.render("WORKFLOW:", True, self.c_white), (392, 234))
        self.screen.blit(self.f_xs.render("[B] AUDITION SOUND LIVE", True, self.c_muted), (392, 256))
        self.screen.blit(self.f_xs.render("[Y] LOAD SYNTH PRESETS", True, self.c_muted), (392, 276))
        self.screen.blit(self.f_xs.render("[STICKS] XY FILTER/PUNCH/DEC", True, self.c_muted), (392, 296))
        self.screen.blit(self.f_xs.render(f"AUTO-LOAD TARGET: I{self.state.active_inst + 1:02d}", True, self.c_green), (392, 322))

        btn_b = pygame.Rect(380, 366, 234, 68)
        pygame.draw.rect(self.screen, self.c_red, btn_b, border_radius=4)
        t1 = self.f_md.render("BOUNCE & SAVE WAV [X]", True, self.c_white)
        t2 = self.f_xs.render(f"-> samples/{folder_name}/", True, self.c_white)
        self.screen.blit(t1, (btn_b.centerx - t1.get_width() // 2, btn_b.y + 16))
        self.screen.blit(t2, (btn_b.centerx - t2.get_width() // 2, btn_b.y + 40))

    # ==========================================================================
    # STANZA 3: INSTRUMENT STUDIO (SELECT + DESTRA)
    # ==========================================================================

    def draw_instrument_room(self):
        inst = self.state.instruments[self.state.active_inst]
        pre_inst = self.audio.instruments[self.state.active_inst]

        for i in range(8):
            bx = 8 + i * 78
            rect = pygame.Rect(bx, 42, 74, 24)
            is_sel = (i == self.state.active_inst)
            pygame.draw.rect(self.screen, self.c_red if is_sel else self.c_surface, rect, border_radius=3)
            pygame.draw.rect(self.screen, self.c_white if is_sel else self.c_border, rect, 1, border_radius=3)
            lbl = self.f_xs.render(f"I{i + 1:02d}:{self.state.instruments[i].source_type.split(':')[-1][:4]}", True, self.c_white if is_sel else self.c_muted)
            self.screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - lbl.get_height() // 2))

        left_box = pygame.Rect(8, 72, 316, 380)
        pygame.draw.rect(self.screen, self.c_surface, left_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, left_box, 1, border_radius=4)

        flt_label = "FLAT (0)"
        if inst.filter_cutoff < -0.03:
            flt_label = f"LP {int(abs(inst.filter_cutoff) * 100)}%"
        elif inst.filter_cutoff > 0.03:
            flt_label = f"HP {int(inst.filter_cutoff * 100)}%"

        params = [
            ("SOURCE (LSDJ)", inst.source_type),
            ("WAV FILE", inst.sample_name if inst.source_type == "WAV" else "[INTERNAL OSC]"),
            ("ENGINE MODE", inst.mode),
            ("ROOT / SCALE", f"{midi_to_name(inst.root_note)} / {inst.scale}"),
            ("PITCH / START", f"{inst.pitch_semi:+d}st  |  {int(inst.start_pos * 100)}%"),
            ("GRAIN / SPRAY", f"{int(inst.grain_size * 100)}%  |  {int(inst.spray * 100)}%"),
            ("FILTER LP/HP", f"{flt_label}  (RES {int(inst.filter_res * 100)}%)"),
            ("MINI-LFO", f"{inst.lfo_speed:.1f}Hz  |  DEPTH {int(inst.lfo_depth * 100)}%"),
        ]

        py = 82
        for idx, (k, v) in enumerate(params):
            is_cur = (idx == self.state.inst_param_idx and not self.state.wav_browser_open)
            row_r = pygame.Rect(14, py, 304, 42)
            if is_cur:
                pygame.draw.rect(self.screen, self.c_panel, row_r, border_radius=3)
                pygame.draw.rect(self.screen, self.c_red, row_r, 1, border_radius=3)

            ks = self.f_xs.render(k, True, self.c_red if is_cur else self.c_muted)
            vs = self.f_sm.render(v, True, self.c_white if is_cur else (self.c_muted if idx == 1 and inst.source_type != "WAV" else self.c_white))
            self.screen.blit(ks, (22, py + 4))
            self.screen.blit(vs, (22, py + 20))
            py += 45

        right_box = pygame.Rect(332, 72, 300, 380)
        pygame.draw.rect(self.screen, self.c_surface, right_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, right_box, 1, border_radius=4)

        self.screen.blit(self.f_xs.render("WAVEFORM & GRAIN WINDOW", True, self.c_muted), (344, 82))

        wf_rect = pygame.Rect(344, 102, 276, 130)
        pygame.draw.rect(self.screen, self.c_bg, wf_rect, border_radius=3)
        pygame.draw.rect(self.screen, self.c_border, wf_rect, 1, border_radius=3)

        mid_y = wf_rect.centery
        pygame.draw.line(self.screen, self.c_panel, (wf_rect.left, mid_y), (wf_rect.right, mid_y), 1)

        start_px = wf_rect.left + int(inst.start_pos * (wf_rect.width - 4))
        win_w = max(6, int(inst.grain_size * (wf_rect.width - (start_px - wf_rect.left))))
        win_rect = pygame.Rect(start_px, wf_rect.top + 2, min(win_w, wf_rect.right - start_px - 2), wf_rect.height - 4)
        pygame.draw.rect(self.screen, self.c_red_dim, win_rect)

        peaks = pre_inst.waveform_peaks
        bar_step = wf_rect.width / float(len(peaks))
        for i, pk in enumerate(peaks):
            x = int(wf_rect.left + i * bar_step)
            h = int(pk * (wf_rect.height // 2 - 6))
            col = self.c_white if (wf_rect.left <= x <= win_rect.right and x >= start_px) else self.c_muted
            pygame.draw.line(self.screen, col, (x, mid_y - h), (x, mid_y + h), 2)

        pygame.draw.line(self.screen, self.c_red, (start_px, wf_rect.top), (start_px, wf_rect.bottom), 2)

        stk_box = pygame.Rect(344, 242, 276, 74)
        pygame.draw.rect(self.screen, self.c_panel, stk_box, border_radius=3)
        self.screen.blit(self.f_xs.render("ANALOG STICKS XY SCULPTING:", True, self.c_white), (354, 250))
        self.screen.blit(self.f_xs.render("L-STICK: X=START POS   Y=PITCH", True, self.c_muted), (354, 270))
        self.screen.blit(self.f_xs.render("R-STICK: X=GRAIN/DECAY Y=SPRAY", True, self.c_muted), (354, 288))

        mic_box = pygame.Rect(344, 326, 276, 114)
        pygame.draw.rect(self.screen, self.c_bg, mic_box, border_radius=3)
        pygame.draw.rect(self.screen, self.c_red if self.state.mic_recording else self.c_border, mic_box, 1, border_radius=3)

        m_title = "USB MIC SAMPLER (TONOR READY)" if self.state.mic_connected else "USB MIC: NOT DETECTED ON OTG"
        self.screen.blit(self.f_xs.render(m_title, True, self.c_white if self.state.mic_connected else self.c_muted), (354, 334))
        self.screen.blit(self.f_xs.render(f"DEV: {self.state.mic_name}", True, self.c_muted), (354, 352))

        vu_bg = pygame.Rect(354, 374, 256, 14)
        pygame.draw.rect(self.screen, self.c_panel, vu_bg)
        mw = int(min(1.0, self.state.mic_level) * 256)
        if mw > 0:
            pygame.draw.rect(self.screen, self.c_red if mw > 215 else self.c_green, (354, 374, mw, 14))

        rec_btn = pygame.Rect(354, 398, 256, 32)
        pygame.draw.rect(self.screen, self.c_red if self.state.mic_recording else self.c_panel, rec_btn, border_radius=3)
        rec_lbl = "STOP & AUTO-TRIM WAV [PRESS X]" if self.state.mic_recording else "REC FROM USB MIC [PRESS X]"
        rl_s = self.f_xs.render(rec_lbl, True, self.c_white)
        self.screen.blit(rl_s, (rec_btn.centerx - rl_s.get_width() // 2, rec_btn.centery - rl_s.get_height() // 2))

        if self.state.wav_browser_open:
            ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            ov.fill((5, 5, 7, 220))
            self.screen.blit(ov, (0, 0))

            modal = pygame.Rect(70, 64, 500, 356)
            pygame.draw.rect(self.screen, self.c_surface, modal, border_radius=6)
            pygame.draw.rect(self.screen, self.c_red, modal, 2, border_radius=6)

            self.screen.blit(self.f_md.render("SELECT WAV SAMPLE (ABLETON 16/24/32-BIT SAFE)", True, self.c_white), (88, 76))
            self.screen.blit(self.f_xs.render("UP/DOWN: AUDITION   A: LOAD   B: CLOSE", True, self.c_muted), (88, 98))
            pygame.draw.line(self.screen, self.c_border, (88, 118), (552, 118), 1)

            files = self.state.wav_browser_files
            if not files:
                self.screen.blit(self.f_sm.render("Nessun .wav trovato in samples/ o samples/mic/", True, self.c_red), (88, 140))
            else:
                start_i = max(0, self.state.wav_browser_idx - 5)
                end_i = min(len(files), start_i + 11)
                fy = 128
                for idx in range(start_i, end_i):
                    disp, _ = files[idx]
                    is_s = (idx == self.state.wav_browser_idx)
                    if is_s:
                        pygame.draw.rect(self.screen, self.c_red, (84, fy - 2, 472, 24), border_radius=3)
                    fs = self.f_sm.render(disp[:52], True, self.c_white if is_s else self.c_muted)
                    self.screen.blit(fs, (92, fy + 2))
                    fy += 26

    # ==========================================================================
    # STANZA 3B: CREDITS & PAGINATED SHORTCUTS (SELECT + DESTRA + DESTRA)
    # ==========================================================================

    def draw_credits_room(self):
        left_box = pygame.Rect(12, 44, 226, 408)
        pygame.draw.rect(self.screen, self.c_surface, left_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_red, left_box, 1, border_radius=4)

        self.screen.blit(self.f_lg.render("GGrain v1.0", True, self.c_white), (24, 58))
        self.screen.blit(self.f_sm.render("produced by Gas1312", True, self.c_red), (24, 84))
        pygame.draw.line(self.screen, self.c_border, (24, 108), (224, 108), 1)

        info_lines = [
            "ARCHITECTURE:",
            "Single Source of Truth",
            "RAM Pre-Rendered PCM",
            "8 Shared Insts (I01-08)",
            "",
            "HARDWARE TARGET:",
            "R36S (RK3326 / KNULLI)",
            "Tonor USB OTG Mic",
            "USB OTG MIDI Keyboard",
            "M-VAVE FM-1 (2 PPQN)",
            "",
            "DSP ENGINE:",
            "NUMPY FAST" if HAS_NUMPY else "PURE PYTHON ENGINE",
        ]
        iy = 118
        for line in info_lines:
            col = self.c_white if line.endswith(":") else self.c_muted
            self.screen.blit(self.f_xs.render(line, True, col), (24, iy))
            iy += 22

        # Pannello Destro: Mappa Scorciatoie Impaginata & Scorrevole
        right_box = pygame.Rect(246, 44, 382, 408)
        pygame.draw.rect(self.screen, self.c_surface, right_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, right_box, 1, border_radius=4)

        num_pages = len(SHORTCUT_PAGES)
        cur_p = self.state.credits_page % num_pages
        page_title, items = SHORTCUT_PAGES[cur_p]

        # Tab Pagine [1] [2] [3] [4]
        tab_w = 88
        for p_i in range(num_pages):
            tx = 256 + p_i * (tab_w + 4)
            tr = pygame.Rect(tx, 52, tab_w, 20)
            is_act = (p_i == cur_p)
            pygame.draw.rect(self.screen, self.c_red if is_act else self.c_panel, tr, border_radius=3)
            t_lbl = self.f_xs.render(f"PG {p_i + 1}/{num_pages}", True, self.c_white if is_act else self.c_muted)
            self.screen.blit(t_lbl, (tr.centerx - t_lbl.get_width() // 2, tr.centery - t_lbl.get_height() // 2))

        self.screen.blit(self.f_sm.render(page_title, True, self.c_white), (256, 80))
        pygame.draw.line(self.screen, self.c_border, (256, 102), (618, 102), 1)

        visible_rows = 10
        max_scroll = max(0, len(items) - visible_rows)
        scroll = min(self.state.credits_scroll, max_scroll)
        slice_items = items[scroll:scroll + visible_rows]

        sy = 110
        for idx_row, (key_s, desc_s) in enumerate(slice_items):
            if idx_row % 2 == 0:
                pygame.draw.rect(self.screen, self.c_bg, (254, sy - 2, 354, 28), border_radius=2)
            self.screen.blit(self.f_xs.render(key_s, True, self.c_red), (260, sy + 5))
            self.screen.blit(self.f_xs.render(desc_s, True, self.c_white), (382, sy + 5))
            sy += 31

        # Scrollbar laterale
        sb_track = pygame.Rect(614, 110, 6, 308)
        pygame.draw.rect(self.screen, self.c_bg, sb_track, border_radius=2)
        if len(items) > visible_rows:
            thumb_h = max(28, int(308 * (visible_rows / float(len(items)))))
            thumb_y = 110 + int((308 - thumb_h) * (scroll / float(max_scroll)))
            pygame.draw.rect(self.screen, self.c_red, (614, thumb_y, 6, thumb_h), border_radius=2)
        else:
            pygame.draw.rect(self.screen, self.c_border, sb_track, border_radius=2)

        nav_tip = self.f_xs.render("UP/DOWN: SCROLL   LEFT/RIGHT: SWITCH PAGE", True, self.c_muted)
        self.screen.blit(nav_tip, (256, 428))

    # ==========================================================================
    # STANZA 4: CONSOLE MASTERING & HARDWARE I/O (SELECT + GIU)
    # ==========================================================================

    def draw_mastering_room(self):
        mfx = self.state.master_fx

        left_box = pygame.Rect(8, 44, 376, 408)
        pygame.draw.rect(self.screen, self.c_surface, left_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, left_box, 1, border_radius=4)

        hdr = self.f_md.render("MASTER BUS PROCESSOR", True, self.c_white)
        self.screen.blit(hdr, (20, 54))

        byp_rect = pygame.Rect(272, 52, 98, 22)
        pygame.draw.rect(self.screen, self.c_red if mfx.bypass else self.c_green, byp_rect, border_radius=3)
        b_txt = self.f_xs.render("BYPASSED [X]" if mfx.bypass else "ACTIVE [X]", True, self.c_bg if not mfx.bypass else self.c_white)
        self.screen.blit(b_txt, (byp_rect.centerx - b_txt.get_width() // 2, byp_rect.centery - b_txt.get_height() // 2))

        modules = [
            ("1. STEREO CHORUS / WIDENER", f"WIDTH: {int(mfx.chorus_mix * 100)}%", mfx.chorus_mix),
            ("2. SPACE REVERB", f"MIX: {int(mfx.reverb_mix * 100)}%  (SIZE {int(mfx.reverb_size * 100)}%)", mfx.reverb_mix),
            ("3. TAPE SATURATOR", f"DRIVE: {int(mfx.tape_drive * 100)}%", mfx.tape_drive),
            ("4. MASTER COMP / LIMITER", f"THRESH: {int(mfx.comp_thresh * 100)}%  |  OUT: {int(mfx.master_vol * 100)}%", mfx.comp_thresh),
        ]

        my = 88
        for idx, (title, val_str, bar_val) in enumerate(modules):
            is_cur = (idx == self.state.master_param_idx)
            card = pygame.Rect(18, my, 356, 68)
            pygame.draw.rect(self.screen, self.c_panel if is_cur else self.c_bg, card, border_radius=4)
            pygame.draw.rect(self.screen, self.c_red if is_cur else self.c_border, card, 1, border_radius=4)

            ts = self.f_sm.render(title, True, self.c_white if is_cur else self.c_muted)
            vs = self.f_xs.render(val_str, True, self.c_red if is_cur else self.c_white)
            self.screen.blit(ts, (28, my + 8))
            self.screen.blit(vs, (28, my + 26))

            bg_b = pygame.Rect(28, my + 46, 336, 10)
            pygame.draw.rect(self.screen, self.c_surface, bg_b)
            fill_c = self.c_muted if mfx.bypass else (self.c_red if is_cur else self.c_white)
            pygame.draw.rect(self.screen, fill_c, (28, my + 46, int(336 * bar_val), 10))
            my += 76

        gr_box = pygame.Rect(18, 396, 356, 44)
        pygame.draw.rect(self.screen, self.c_bg, gr_box, border_radius=3)
        self.screen.blit(self.f_xs.render("COMPRESSOR GAIN REDUCTION (GR)", True, self.c_muted), (28, 402))
        gr_bg = pygame.Rect(28, 420, 336, 12)
        pygame.draw.rect(self.screen, self.c_panel, gr_bg)
        gr_w = int(min(1.0, mfx.gain_reduction) * 336)
        if gr_w > 0:
            pygame.draw.rect(self.screen, self.c_red, (364 - gr_w, 420, gr_w, 12))

        right_box = pygame.Rect(392, 44, 240, 408)
        pygame.draw.rect(self.screen, self.c_surface, right_box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, right_box, 1, border_radius=4)

        self.screen.blit(self.f_md.render("HARDWARE I/O", True, self.c_white), (404, 54))

        c1 = pygame.Rect(404, 88, 216, 86)
        pygame.draw.rect(self.screen, self.c_bg, c1, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, c1, 1, border_radius=4)
        self.screen.blit(self.f_xs.render("1. USB OTG MICROPHONE", True, self.c_muted), (414, 96))
        st1 = "CONNECTED (5V OK)" if self.state.mic_connected else "DISCONNECTED"
        self.screen.blit(self.f_sm.render(st1, True, self.c_green if self.state.mic_connected else self.c_red), (414, 114))
        self.screen.blit(self.f_xs.render(self.state.mic_name[:26], True, self.c_white), (414, 134))
        pygame.draw.rect(self.screen, self.c_panel, (414, 154, 196, 8))
        pygame.draw.rect(self.screen, self.c_green, (414, 154, int(196 * min(1.0, self.state.mic_level)), 8))

        c2 = pygame.Rect(404, 186, 216, 76)
        pygame.draw.rect(self.screen, self.c_bg, c2, border_radius=4)
        pygame.draw.rect(self.screen, self.c_border, c2, 1, border_radius=4)
        self.screen.blit(self.f_xs.render("2. USB OTG MIDI KEYBOARD", True, self.c_muted), (414, 194))
        st2 = f"ACTIVE ({self.state.midi_name})" if self.state.midi_connected else "DISCONNECTED"
        self.screen.blit(self.f_sm.render(st2, True, self.c_green if self.state.midi_connected else self.c_red), (414, 214))
        self.screen.blit(self.f_xs.render("STEP-REC IN STOP / LIVE IN PLAY", True, self.c_muted), (414, 236))

        is_sync_sel = (self.state.master_param_idx == 4)
        c3 = pygame.Rect(404, 274, 216, 94)
        pygame.draw.rect(self.screen, self.c_panel if is_sync_sel else self.c_bg, c3, border_radius=4)
        pygame.draw.rect(self.screen, self.c_red if is_sync_sel else self.c_border, c3, 1, border_radius=4)
        self.screen.blit(self.f_xs.render("3. M-VAVE FM-1 SYNC OUT", True, self.c_red if is_sync_sel else self.c_muted), (414, 282))
        sync_lbl = "ENABLED (2 PPQN RIGHT CH)" if self.state.sync_out_2ppqn else "OFF (STEREO AUDIO OUT)"
        self.screen.blit(self.f_xs.render(sync_lbl, True, self.c_white), (414, 304))
        self.screen.blit(self.f_xs.render("L=MONO AUDIO / R=CLOCK PULSE", True, self.c_muted), (414, 326))
        self.screen.blit(self.f_xs.render("LEFT/RIGHT TO TOGGLE", True, self.c_muted), (414, 344))

        self.screen.blit(self.f_xs.render("L-STK:CHORUS/REV R-STK:DRV/CMP", True, self.c_muted), (404, 424))

    # ==========================================================================
    # OVERLAY MENU CONTESTUALE (TASTO Y) & NOTIFICHE TOAST
    # ==========================================================================

    def draw_y_menu_overlay(self, items):
        ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        ov.fill((5, 5, 7, 215))
        self.screen.blit(ov, (0, 0))

        h_box = 78 + len(items) * 32
        y_top = (self.h - h_box) // 2
        modal = pygame.Rect(150, y_top, 340, h_box)
        pygame.draw.rect(self.screen, self.c_surface, modal, border_radius=6)
        pygame.draw.rect(self.screen, self.c_red, modal, 2, border_radius=6)

        hdr = self.f_md.render(f"WORKFLOW TOOLS [{self.state.active_screen}]", True, self.c_white)
        self.screen.blit(hdr, (modal.centerx - hdr.get_width() // 2, y_top + 14))
        pygame.draw.line(self.screen, self.c_border, (modal.left + 16, y_top + 40), (modal.right - 16, y_top + 40), 1)

        iy = y_top + 50
        for idx, label in enumerate(items):
            is_sel = (idx == self.state.y_menu_idx)
            r = pygame.Rect(modal.left + 16, iy, modal.width - 32, 26)
            if is_sel:
                pygame.draw.rect(self.screen, self.c_red, r, border_radius=3)
            ls = self.f_xs.render(label, True, self.c_white if is_sel else self.c_muted)
            self.screen.blit(ls, (r.left + 10, r.centery - ls.get_height() // 2))
            iy += 32

    def draw_block_menu_overlay(self):
        ov = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        ov.fill((5, 5, 7, 205))
        self.screen.blit(ov, (0, 0))

        lo = min(self.state.step_sel_anchor, self.state.step_sel_end)
        hi = max(self.state.step_sel_anchor, self.state.step_sel_end)
        sel_cnt = hi - lo + 1
        clip_cnt = len(self.state.step_clipboard)

        modal = pygame.Rect(170, 155, 300, 168)
        pygame.draw.rect(self.screen, self.c_surface, modal, border_radius=6)
        pygame.draw.rect(self.screen, self.c_red, modal, 2, border_radius=6)

        hdr = self.f_md.render(f"BLOCK [STP {lo + 1:02d}..{hi + 1:02d}]", True, self.c_white)
        self.screen.blit(hdr, (modal.centerx - hdr.get_width() // 2, 168))
        pygame.draw.line(self.screen, self.c_border, (modal.left + 16, 194), (modal.right - 16, 194), 1)

        opts = [
            f"1. COPY SELECTION ({sel_cnt} STEP{'S' if sel_cnt > 1 else ''})",
            f"2. PASTE AT STP {self.state.cursor_step + 1:02d} ({clip_cnt} STEP{'S' if clip_cnt != 1 else ''})" if clip_cnt > 0 else "2. PASTE (CLIPBOARD EMPTY)",
            "3. CANCEL",
        ]
        iy = 204
        for idx, label in enumerate(opts):
            is_sel = (idx == self.state.block_menu_idx)
            r = pygame.Rect(modal.left + 16, iy, modal.width - 32, 28)
            if is_sel:
                pygame.draw.rect(self.screen, self.c_red, r, border_radius=3)
            ls = self.f_xs.render(label, True, self.c_white if is_sel else self.c_muted)
            self.screen.blit(ls, (r.left + 10, r.centery - ls.get_height() // 2))
            iy += 34

    def draw_toast(self):
        if self.state.toast_timer <= 0.0 or not self.state.toast_msg:
            return
        ts = self.f_xs.render(self.state.toast_msg, True, self.c_white)
        w_box = ts.get_width() + 24
        box = pygame.Rect(self.w - w_box - 12, 422, w_box, 26)
        pygame.draw.rect(self.screen, self.c_red, box, border_radius=4)
        pygame.draw.rect(self.screen, self.c_white, box, 1, border_radius=4)
        self.screen.blit(ts, (box.x + 12, box.y + 7))

    # ==========================================================================
    # BARRA SUGGERIMENTI IN BASSO
    # ==========================================================================

    def draw_bottom_bar(self):
        pygame.draw.rect(self.screen, self.c_surface, (0, 458, self.w, 22))
        pygame.draw.line(self.screen, self.c_border, (0, 458), (self.w, 458), 1)

        scr = self.state.active_screen
        if self.state.y_menu_open:
            hint = "UP/DOWN: SELECT TOOL   A: EXECUTE   B/Y: CLOSE MENU"
        elif scr == "SONG_SEQ":
            if self.state.seq_focus == "SONG":
                hint = "START:LOOP  R1+START:SONG  A+U/D:PAT  X:CLONE  Y:TOOLS  SEL+LEFTx2:SYNTH"
            else:
                hint = "A+U/D:NOTE(+L1:OCT)  A+L/R:INST  +L1:SLICE  +R1:LVL  START:LOOP"
        elif scr == "SYNTH_LAB":
            hint = "U/D:PARAM  L/R:EDIT  B:AUDITION  X:BOUNCE WAV  Y:PRESETS  SEL+LEFT:BACK"
        elif scr == "INSTRUMENT":
            hint = "L1/R1:INST  U/D:PARAM  L/R:EDIT  A:WAV  B:PLAY  X:MIC REC  SEL+RIGHTx2:INFO"
        elif scr == "CREDITS":
            hint = "UP/DOWN: SCROLL LIST   LEFT/RIGHT: SWITCH CATEGORY   SEL+DPAD: EXIT"
        elif scr == "MASTERING":
            hint = "U/D:MODULE  L/R:ADJUST  A+L/R:SUB  X:A/B BYPASS  Y:RESET  STICKS:XY MIX"
        elif scr == "PROJECT":
            hint = "U/D:SELECT  L/R:EDIT / COLORS  A:EXECUTE  Y:QUICK TOOLS  START:LOOP"
        else:
            hint = "SEL+LEFT:SONG  SEL+RIGHT:INST  SEL+DOWN:MASTER  SEL+UP:PROJECT"

        hs = self.f_xs.render(hint, True, self.c_muted)
        self.screen.blit(hs, (10, 463))

    # ==========================================================================
    # DEVELOPER DEBUG OVERLAY (L2+R2+SELECT)
    # ==========================================================================

    def draw_debug_overlay(self, inp, fps):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((5, 5, 7, 238))
        self.screen.blit(overlay, (0, 0))

        frame = pygame.Rect(14, 14, self.w - 28, self.h - 28)
        pygame.draw.rect(self.screen, self.c_surface, frame, border_radius=6)
        pygame.draw.rect(self.screen, self.c_red, frame, 2, border_radius=6)

        hdr = self.f_md.render("DEV DIAGNOSTICS & GAMEPAD TESTER [L2+R2+SEL TO EXIT]", True, self.c_red)
        self.screen.blit(hdr, (28, 24))
        pygame.draw.line(self.screen, self.c_border, (28, 48), (self.w - 28, 48), 1)

        pad_box = pygame.Rect(28, 60, 340, 384)
        pygame.draw.rect(self.screen, self.c_bg, pad_box, border_radius=6)
        pygame.draw.rect(self.screen, self.c_border, pad_box, 1, border_radius=6)

        def draw_btn(rect, label, active, round_btn=False):
            bg = self.c_red if active else self.c_panel
            fg = self.c_white if active else self.c_muted
            if round_btn:
                pygame.draw.circle(self.screen, bg, rect.center, rect.width // 2)
                pygame.draw.circle(self.screen, self.c_white if active else self.c_border, rect.center, rect.width // 2, 1)
            else:
                pygame.draw.rect(self.screen, bg, rect, border_radius=4)
                pygame.draw.rect(self.screen, self.c_white if active else self.c_border, rect, 1, border_radius=4)
            ts = self.f_xs.render(label, True, fg)
            self.screen.blit(ts, (rect.centerx - ts.get_width() // 2, rect.centery - ts.get_height() // 2))

        draw_btn(pygame.Rect(44, 72, 46, 22), "L2", inp.is_held("L2"))
        draw_btn(pygame.Rect(96, 72, 46, 22), "L1", inp.is_held("L1"))
        draw_btn(pygame.Rect(254, 72, 46, 22), "R1", inp.is_held("R1"))
        draw_btn(pygame.Rect(306, 72, 46, 22), "R2", inp.is_held("R2"))

        dx, dy = 86, 135
        draw_btn(pygame.Rect(dx, dy - 28, 26, 26), "U", inp.is_held("UP"))
        draw_btn(pygame.Rect(dx, dy + 28, 26, 26), "D", inp.is_held("DOWN"))
        draw_btn(pygame.Rect(dx - 28, dy, 26, 26), "L", inp.is_held("LEFT"))
        draw_btn(pygame.Rect(dx + 28, dy, 26, 26), "R", inp.is_held("RIGHT"))
        pygame.draw.rect(self.screen, self.c_panel, (dx, dy, 26, 26))

        bx, by = 282, 135
        draw_btn(pygame.Rect(bx, by - 28, 28, 28), "X", inp.is_held("X"), round_btn=True)
        draw_btn(pygame.Rect(bx, by + 28, 28, 28), "B", inp.is_held("B"), round_btn=True)
        draw_btn(pygame.Rect(bx - 28, by, 28, 28), "Y", inp.is_held("Y"), round_btn=True)
        draw_btn(pygame.Rect(bx + 28, by, 28, 28), "A", inp.is_held("A"), round_btn=True)

        draw_btn(pygame.Rect(130, 206, 54, 22), "SELECT", inp.is_held("SELECT"))
        draw_btn(pygame.Rect(212, 206, 54, 22), "START", inp.is_held("START"))

        def draw_stick_radar(cx, cy, label, ax, ay, clicked=False):
            r = 44
            pygame.draw.circle(self.screen, self.c_red_dim if clicked else self.c_panel, (cx, cy), r)
            pygame.draw.circle(self.screen, self.c_red if clicked else self.c_border, (cx, cy), r, 2 if clicked else 1)
            pygame.draw.line(self.screen, self.c_border, (cx - r, cy), (cx + r, cy), 1)
            pygame.draw.line(self.screen, self.c_border, (cx, cy - r), (cx, cy + r), 1)
            px = int(cx + ax * (r - 6))
            py = int(cy + ay * (r - 6))
            active = clicked or (abs(ax) > 0.05 or abs(ay) > 0.05)
            pygame.draw.circle(self.screen, self.c_red if active else self.c_white, (px, py), 6)
            tag = f"{label}{'[CLK]' if clicked else ''}"
            lbl = self.f_xs.render(f"{tag} ({ax:+.2f},{ay:+.2f})", True, self.c_white if active else self.c_muted)
            self.screen.blit(lbl, (cx - lbl.get_width() // 2, cy + r + 8))

        draw_stick_radar(112, 315, "L-STICK", inp.lx, inp.ly, inp.is_held("L3"))
        draw_stick_radar(284, 315, "R-STICK", inp.rx, inp.ry, inp.is_held("R3"))

        raw_str = f"RAW JOY BTNS: {sorted(list(inp.raw_buttons_held))}"
        self.screen.blit(self.f_xs.render(raw_str, True, self.c_red), (42, 416))

        tel_box = pygame.Rect(382, 60, 230, 384)
        pygame.draw.rect(self.screen, self.c_bg, tel_box, border_radius=6)
        pygame.draw.rect(self.screen, self.c_border, tel_box, 1, border_radius=6)

        tel = self.hw.get_debug_telemetry()
        rows = [
            ("FPS ENGINE", f"{fps:.1f} FPS"),
            ("DSP ENGINE", "NUMPY FAST" if HAS_NUMPY else "PURE PYTHON"),
            ("JOYSTICK", inp.joy_name[:20]),
            ("ALSA MIC DEV", tel["mic_card"]),
            ("MIC MODEL", tel["mic_name"][:20]),
            ("MIC INPUT", tel["mic_lvl"]),
            ("USB MIDI DEV", tel["midi_dev"]),
            ("BATTERY", tel["bat"]),
            ("ACTIVE INST", f"I{self.state.active_inst + 1:02d}"),
            ("AUDIO CHANS", f"{sum(1 for c in range(32) if pygame.mixer.Channel(c).get_busy())}/32"),
        ]

        ty = 76
        for k, v in rows:
            ks = self.f_xs.render(k, True, self.c_muted)
            vs = self.f_sm.render(str(v), True, self.c_white)
            self.screen.blit(ks, (396, ty))
            self.screen.blit(vs, (396, ty + 14))
            ty += 36

    # ==========================================================================
    # RENDER PRINCIPALE
    # ==========================================================================

    def render(self, inp, fps, y_menu_items, direct_boot_enabled):
        self._sync_theme()
        self.screen.fill(self.c_bg)
        self.draw_top_bar()

        scr = self.state.active_screen
        if scr == "SONG_SEQ":
            self.draw_song_seq()
        elif scr == "SYNTH_LAB":
            self.draw_synth_lab()
        elif scr == "INSTRUMENT":
            self.draw_instrument_room()
        elif scr == "CREDITS":
            self.draw_credits_room()
        elif scr == "MASTERING":
            self.draw_mastering_room()
        elif scr == "PROJECT":
            self.draw_project_room(direct_boot_enabled)

        self.draw_toast()
        self.draw_bottom_bar()

        if self.state.block_menu_open:
            self.draw_block_menu_overlay()

        if self.state.y_menu_open:
            self.draw_y_menu_overlay(y_menu_items)

        if self.state.name_editor_open:
            self.draw_name_editor_overlay()

        if inp.debug_mode:
            self.draw_debug_overlay(inp, fps)