import os
import math
import time
import wave
import array
import struct
import random
import pygame

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import audioop
    HAS_AUDIOOP = True
except ImportError:
    HAS_AUDIOOP = False

SAMPLE_RATE = 22050


# ==============================================================================
# 1. PARSER WAV ABLETON-SAFE (16/24-BIT PCM + 32-BIT FLOAT + EXTENSIBLE + SR)
# ==============================================================================

def load_wav_ableton_safe(filepath):
    """
    Legge WAV esportati da Ableton Live o qualsiasi DAW:
    - Ignora chunk extra (bext, iXML, cue, LIST, smpl, JUNK, FLLR)
    - Supporta 8/16/24-bit PCM (fmt=1), 32-bit IEEE Float (fmt=3) e WAVE_FORMAT_EXTENSIBLE (0xFFFE)
    - Ritorna (samples_float_list, source_sample_rate)
    """
    if not filepath or not os.path.exists(filepath):
        return [], SAMPLE_RATE
    try:
        with open(filepath, "rb") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return [], SAMPLE_RATE

            audio_fmt = 1
            channels = 1
            file_sr = SAMPLE_RATE
            sample_width = 2
            raw_data = b""

            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                chunk_id = header[:4]
                chunk_size = struct.unpack("<I", header[4:8])[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    audio_fmt, channels, file_sr, _, _, bits = struct.unpack("<HHIIHH", fmt_data[:16])
                    sample_width = max(1, bits // 8)
                    # WAVE_FORMAT_EXTENSIBLE (usato spesso da Ableton per 24/32 bit)
                    if audio_fmt == 0xFFFE and len(fmt_data) >= 26:
                        audio_fmt = struct.unpack("<H", fmt_data[24:26])[0]
                elif chunk_id == b"data":
                    raw_data = f.read(chunk_size)
                else:
                    f.seek(chunk_size, 1)

                if chunk_size % 2 == 1:
                    f.seek(1, 1)

        if not raw_data:
            return [], file_sr

        if HAS_NUMPY:
            if audio_fmt == 3 and sample_width == 4:
                arr = np.frombuffer(raw_data, dtype=np.float32)
            elif sample_width == 2:
                arr = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_width == 1:
                arr = (np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            elif sample_width == 3:
                b = np.frombuffer(raw_data, dtype=np.uint8).reshape(-1, 3)
                val = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
                val = np.where(val >= 0x800000, val - 0x1000000, val)
                arr = val.astype(np.float32) / 8388608.0
            elif audio_fmt == 1 and sample_width == 4:
                arr = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                return [], file_sr

            if channels > 1:
                trim_len = (len(arr) // channels) * channels
                arr = arr[:trim_len].reshape(-1, channels).mean(axis=1)
            return np.clip(arr, -1.0, 1.0).tolist(), file_sr

        # Fallback Pure Python
        samples = []
        step = channels * sample_width
        for i in range(0, len(raw_data) - step + 1, step):
            acc = 0.0
            for ch in range(channels):
                off = i + ch * sample_width
                if audio_fmt == 3 and sample_width == 4:
                    v = struct.unpack_from("<f", raw_data, off)[0]
                elif sample_width == 2:
                    v = struct.unpack_from("<h", raw_data, off)[0] / 32768.0
                elif sample_width == 3:
                    b0, b1, b2 = raw_data[off], raw_data[off + 1], raw_data[off + 2]
                    v_int = b0 | (b1 << 8) | (b2 << 16)
                    if v_int & 0x800000:
                        v_int -= 0x1000000
                    v = v_int / 8388608.0
                elif sample_width == 4:
                    v = struct.unpack_from("<i", raw_data, off)[0] / 2147483648.0
                else:
                    v = (raw_data[off] - 128) / 128.0
                acc += max(-1.0, min(1.0, v))
            samples.append(acc / channels)
        return samples, file_sr
    except Exception:
        return [], SAMPLE_RATE


def detect_root_note(samples, sr=SAMPLE_RATE):
    """Autocorrelazione rapida per stimare la nota fondamentale MIDI del campione."""
    if len(samples) < 1024:
        return 60
    start = min(len(samples) // 6, 2048)
    win = samples[start:start + 1024]
    energy = sum(x * x for x in win[::4])
    if energy < 5e-5:
        return 60

    min_lag = int(sr / 880.0)
    max_lag = int(sr / 55.0)
    best_lag = 0
    best_corr = -1.0
    w_len = len(win)

    for lag in range(min_lag, min(max_lag, w_len // 2)):
        corr = 0.0
        for i in range(0, w_len - lag, 4):
            corr += win[i] * win[i + lag]
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_lag <= 0:
        return 60
    freq = sr / float(best_lag)
    midi = int(round(69 + 12 * math.log2(max(20.0, freq) / 440.0)))
    return max(36, min(84, midi))


# ==============================================================================
# 2. MOTORE PRE-RENDERING STRUMENTO (WAV + OSCILLATORI LSDJ STYLE)
# ==============================================================================

class PreRenderedInstrument:
    """Mantiene in RAM i buffer PCM pronti per suonare istantaneamente."""
    def __init__(self, index):
        self.index = index
        self.raw_samples = []
        self.source_sr = SAMPLE_RATE
        self.waveform_peaks = [0.0] * 120
        self.cache = {}  # Chiave: (note_offset, slice_bucket, cutoff_bucket) -> pygame.mixer.Sound

    def load_source(self, inst_data):
        """Carica un WAV oppure sintetizza la forma d'onda dell'oscillatore scelto."""
        src_type = inst_data.source_type
        self.source_sr = SAMPLE_RATE

        if src_type == "WAV":
            if inst_data.sample_path and os.path.exists(inst_data.sample_path):
                loaded, file_sr = load_wav_ableton_safe(inst_data.sample_path)
                if loaded:
                    self.raw_samples = loaded
                    self.source_sr = file_sr
                    inst_data.sample_name = os.path.splitext(os.path.basename(inst_data.sample_path))[0][:18]
                    inst_data.root_note = detect_root_note(self.raw_samples, sr=file_sr)
                else:
                    self.raw_samples = self._synthesize_osc("OSC:SUB")
                    inst_data.sample_name = "ERR_WAV"
            else:
                self.raw_samples = self._synthesize_osc("OSC:SUB")
                inst_data.sample_name = "NO_WAV_LOADED"
                inst_data.root_note = 60
        else:
            self.raw_samples = self._synthesize_osc(src_type)
            inst_data.sample_name = src_type.replace(":", "_")
            inst_data.root_note = 60  # Tutti gli oscillatori sono calibrati su C4 (261.63 Hz)

        inst_data.reload_source = False
        self._compute_peaks()
        self.rebuild_cache(inst_data)

    def _synthesize_osc(self, osc_type):
        """Genera 0.55 secondi di forma d'onda pura calibrata su C4 (261.63 Hz)."""
        n = int(SAMPLE_RATE * 0.55)
        out = [0.0] * n
        c4_freq = 261.625565

        for i in range(n):
            t = i / SAMPLE_RATE
            if osc_type == "OSC:KICK":
                env = math.exp(-t * 11.5)
                freq = 46.0 + 145.0 * math.exp(-t * 36.0)
                val = math.sin(2.0 * math.pi * freq * t) * env
                out[i] = math.tanh(val * 1.4)
            elif osc_type == "OSC:SNARE":
                tone = math.sin(2.0 * math.pi * 190.0 * t) * math.exp(-t * 20.0)
                noise = (random.random() * 2.0 - 1.0) * math.exp(-t * 14.0)
                out[i] = tone * 0.45 + noise * 0.55
            elif osc_type == "OSC:HAT":
                noise = (random.random() * 2.0 - 1.0) * math.exp(-t * 45.0)
                out[i] = noise * 0.8
            elif osc_type == "OSC:SAW":
                env = math.exp(-t * 4.5)
                phase = (c4_freq * t) % 1.0
                out[i] = (2.0 * phase - 1.0) * 0.85 * env
            elif osc_type == "OSC:SQR":
                # Onda quadra classica Game Boy / LSDJ
                env = math.exp(-t * 4.5)
                phase = (c4_freq * t) % 1.0
                out[i] = (0.85 if phase < 0.5 else -0.85) * env
            else:  # OSC:SUB
                env = math.exp(-t * 3.8)
                out[i] = math.sin(2.0 * math.pi * (c4_freq * 0.5) * t) * 0.92 * env
        return out

    def _compute_peaks(self):
        total = len(self.raw_samples)
        if total == 0:
            self.waveform_peaks = [0.0] * 120
            return
        bins = 120
        step = max(1, total // bins)
        peaks = []
        for b in range(bins):
            s = b * step
            e = min(total, s + step)
            pk = 0.0
            stride = max(1, (e - s) // 16)
            for idx in range(s, e, stride):
                v = abs(self.raw_samples[idx])
                if v > pk:
                    pk = v
            peaks.append(min(1.0, pk))
        self.waveform_peaks = peaks

    def rebuild_cache(self, inst_data, tape_drive=0.0):
        self.cache.clear()
        self.get_sound(inst_data, semitone_offset=0, slice_offset=0.0, tape_drive=tape_drive)
        inst_data.dirty = False

    def get_sound(self, inst_data, semitone_offset=0, slice_offset=0.0, tape_drive=0.0, extra_cutoff=0.0, extra_res=0.0):
        slice_bucket = round(slice_offset * 16) / 16.0
        cut_bucket = round(extra_cutoff * 4) / 4.0
        key = (semitone_offset, slice_bucket, cut_bucket)
        if key in self.cache:
            return self.cache[key]

        snd = self._render_buffer(inst_data, semitone_offset, slice_bucket, tape_drive, cut_bucket, extra_res)
        if len(self.cache) > 28:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = snd
        return snd

    def _render_buffer(self, inst_data, semitone_offset, slice_offset, tape_drive, extra_cutoff, extra_res=0.0):
        src = self.raw_samples
        total_src = len(src)
        if total_src == 0:
            return pygame.mixer.Sound(buffer=b"\x00\x00\x00\x00")

        total_semi = inst_data.pitch_semi + semitone_offset
        sr_comp = self.source_sr / float(SAMPLE_RATE)
        rate_ratio = (2.0 ** (total_semi / 12.0)) * sr_comp

        eff_start = min(0.95, max(0.0, inst_data.start_pos + slice_offset))
        start_idx = int(eff_start * total_src)

        if inst_data.mode == "ONE-SHOT":
            max_dur = max(0.05, inst_data.grain_size * 2.5)
            out_len = min(int(SAMPLE_RATE * max_dur), max(64, int((total_src - start_idx) / max(0.05, rate_ratio))))
        else:
            out_len = max(512, int(SAMPLE_RATE * (0.04 + inst_data.grain_size * 0.45)))

        buf = array.array("h")
        lp_state = 0.0
        hp_state = 0.0
        prev_in = 0.0

        cutoff = max(-1.0, min(1.0, inst_data.filter_cutoff + extra_cutoff))
        eff_res = min(0.95, inst_data.filter_res + extra_res)
        res_boost = 1.0 + eff_res * 0.65
        alpha_lp = max(0.03, min(1.0, 1.0 - abs(cutoff) * 0.94)) if cutoff < -0.02 else 1.0
        alpha_hp = max(0.05, min(0.98, 1.0 - cutoff * 0.90)) if cutoff > 0.02 else 1.0

        lfo_depth = inst_data.lfo_depth
        lfo_freq = inst_data.lfo_speed
        spray_samples = int(inst_data.spray * total_src * 0.15)
        spray_jitter = random.randint(-spray_samples, spray_samples) if spray_samples > 0 else 0

        vol = inst_data.volume
        drive = 1.0 + tape_drive * 3.5
        tanh_drive = math.tanh(drive) if tape_drive > 0.02 else 1.0

        if HAS_NUMPY:
            src_arr = np.asarray(src, dtype=np.float32)
            idx_ar = np.arange(out_len, dtype=np.float32)
            env = np.ones(out_len, dtype=np.float32)
            fi = min(64, out_len)
            if fi > 0:
                env[:fi] = np.arange(fi, dtype=np.float32) / 64.0
            if out_len > 256:
                env[out_len - 256:] = np.maximum(0.0, (out_len - np.arange(out_len - 256, out_len, dtype=np.float32)) / 256.0)
            if inst_data.mode == "GRAIN":
                env *= 0.5 * (1.0 - np.cos(2.0 * np.pi * idx_ar / max(1, out_len - 1)))
                grain_span = max(64, int(SAMPLE_RATE * (0.02 + inst_data.grain_size * 0.25)))
                pos_f = start_idx + spray_jitter + ((idx_ar * rate_ratio) % grain_span)
            elif lfo_depth > 0.01:
                lfo_val = np.sin(2.0 * np.pi * lfo_freq * (idx_ar / SAMPLE_RATE)) * lfo_depth
                pos_f = start_idx + spray_jitter + (idx_ar * rate_ratio * (1.0 + lfo_val * 0.06))
            else:
                pos_f = start_idx + spray_jitter + (idx_ar * rate_ratio)

            valid = (pos_f >= 0.0) & (pos_f < total_src - 1)
            idx0 = np.clip(pos_f.astype(np.int32), 0, max(0, total_src - 2))
            frac = pos_f - idx0
            samples = np.where(valid, src_arr[idx0] * (1.0 - frac) + src_arr[idx0 + 1] * frac, 0.0)
            if cutoff < -0.02 or cutoff > 0.02:
                s_list = samples.tolist()
                if cutoff < -0.02:
                    for i in range(out_len):
                        lp_state += alpha_lp * (s_list[i] * res_boost - lp_state)
                        s_list[i] = lp_state
                else:
                    for i in range(out_len):
                        inp_s = s_list[i]
                        hp_state = alpha_hp * (hp_state + inp_s * res_boost - prev_in)
                        prev_in = inp_s
                        s_list[i] = hp_state
                samples = np.asarray(s_list, dtype=np.float32)
            samples *= (vol * env)
            if tape_drive > 0.02:
                samples = np.tanh(samples * drive) / tanh_drive
            s_int = np.clip(samples * 32767.0, -32767.0, 32767.0).astype(np.int16)
            return pygame.mixer.Sound(buffer=np.repeat(s_int, 2).tobytes())

        mono_buf = array.array("h", bytes(out_len * 2))
        flt_mode = -1 if cutoff < -0.02 else (1 if cutoff > 0.02 else 0)
        use_lfo = lfo_depth > 0.01
        lfo_step = (2.0 * math.pi * lfo_freq) / SAMPLE_RATE
        vol_32k = vol * 32767.0
        use_drive = tape_drive > 0.02
        inv_tanh_drive = (1.0 / tanh_drive) if use_drive else 1.0

        is_grain = (inst_data.mode == "GRAIN")
        grain_span = max(64, int(SAMPLE_RATE * (0.02 + inst_data.grain_size * 0.25))) if is_grain else 1
        grain_step = (2.0 * math.pi) / max(1, out_len - 1)
        fade_out_start = out_len - 128
        base_pos = float(start_idx + spray_jitter)
        max_idx = total_src - 2

        sin_fn = math.sin
        cos_fn = math.cos
        tanh_fn = math.tanh

        for i in range(out_len):
            if i < 32:
                env = i * 0.03125
            elif i > fade_out_start:
                env = (out_len - i) * 0.0078125
            else:
                env = 1.0

            if is_grain:
                env *= 0.5 * (1.0 - cos_fn(grain_step * i))
                pos_f = base_pos + ((i * rate_ratio) % grain_span)
            elif use_lfo:
                pos_f = base_pos + (i * rate_ratio * (1.0 + sin_fn(lfo_step * i) * lfo_depth * 0.06))
            else:
                pos_f = base_pos + i * rate_ratio

            idx0 = int(pos_f)
            if idx0 < 0 or idx0 > max_idx:
                sample = 0.0
            else:
                frac = pos_f - idx0
                sample = src[idx0] + (src[idx0 + 1] - src[idx0]) * frac

            if flt_mode == -1:
                lp_state += alpha_lp * (sample * res_boost - lp_state)
                sample = lp_state
            elif flt_mode == 1:
                hp_state = alpha_hp * (hp_state + sample * res_boost - prev_in)
                prev_in = sample
                sample = hp_state

            if use_drive:
                sample = tanh_fn(sample * env * drive) * inv_tanh_drive * vol_32k
            else:
                sample = sample * env * vol_32k

            mono_buf[i] = 32767 if sample > 32767.0 else (-32767 if sample < -32767.0 else int(sample))

        raw_mono = mono_buf.tobytes()
        if HAS_AUDIOOP:
            stereo_bytes = audioop.tostereo(raw_mono, 2, 1.0, 1.0)
        else:
            stereo_buf = array.array("h", bytes(out_len * 4))
            stereo_buf[0::2] = mono_buf
            stereo_buf[1::2] = mono_buf
            stereo_bytes = stereo_buf.tobytes()

        return pygame.mixer.Sound(buffer=stereo_bytes)


# ==============================================================================
# 3. MASTER CLOCK & MOTORE AUDIO PRINCIPALE
# ==============================================================================

class AudioEngine:
    def __init__(self, state):
        self.state = state
        if not pygame.mixer.get_init():
            pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, 512)
            pygame.mixer.init()
        pygame.mixer.set_num_channels(32)

        self.instruments = [PreRenderedInstrument(i) for i in range(state.NUM_INSTRUMENTS)]
        for i, inst_data in enumerate(state.instruments):
            self.instruments[i].load_source(inst_data)

        self.sync_pulse_sound = self._build_sync_pulse()
        self._last_tick = time.perf_counter()
        self._last_rebuild_time = 0.0
        self._step_accum = 0.0

    def _build_sync_pulse(self):
        pulse_len = int(SAMPLE_RATE * 0.008)
        buf = array.array("h")
        for _ in range(pulse_len):
            buf.append(0)
            buf.append(30000)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def sync_dirty_instruments(self, force=False):
        """Rigenera in RAM gli strumenti modificati (throttled a 20 Hz per fluidita' stick)."""
        now = time.perf_counter()
        drive = 0.0 if self.state.master_fx.bypass else self.state.master_fx.tape_drive

        for i, inst_data in enumerate(self.state.instruments):
            if inst_data.reload_source:
                self.instruments[i].load_source(inst_data)
            elif inst_data.dirty and (force or (now - self._last_rebuild_time >= 0.05)):
                self.instruments[i].rebuild_cache(inst_data, tape_drive=drive)
                self._last_rebuild_time = now

    def load_wav_into_instrument(self, inst_idx, filepath):
        inst_data = self.state.instruments[inst_idx]
        inst_data.source_type = "WAV"
        inst_data.sample_path = filepath
        inst_data.reload_source = True
        self.instruments[inst_idx].load_source(inst_data)
        self.audition_instrument(inst_idx)

    def audition_instrument(self, inst_idx, midi_note=None):
        self.sync_dirty_instruments(force=True)
        inst_data = self.state.instruments[inst_idx]
        semi = 0 if midi_note is None else (midi_note - inst_data.root_note)
        snd = self.instruments[inst_idx].get_sound(
            inst_data, semitone_offset=semi, slice_offset=0.0,
            tape_drive=0.0 if self.state.master_fx.bypass else self.state.master_fx.tape_drive
        )
        self._play_with_master_fx(snd, track_idx=self.state.active_track, step_vol=1.0)

    def _play_with_master_fx(self, snd, track_idx, step_vol=1.0):
        mfx = self.state.master_fx
        active_voices = sum(1 for c in range(24) if pygame.mixer.Channel(c).get_busy())
        comp_gain = 1.0
        if not mfx.bypass and active_voices > 2:
            over = (active_voices - 2) * 0.12
            comp_gain = max(0.45, 1.0 - over * (1.1 - mfx.comp_thresh))
            mfx.gain_reduction = min(1.0, (1.0 - comp_gain) * 2.5)
        else:
            mfx.gain_reduction *= 0.85

        final_vol = step_vol * mfx.master_vol * comp_gain

        if self.state.sync_out_2ppqn:
            ch = pygame.mixer.Channel(track_idx * 4)
            ch.play(snd)
            ch.set_volume(final_vol, 0.0)
            self.state.vu_left = min(1.0, max(self.state.vu_left, final_vol))
            return

        ch_main = pygame.mixer.Channel(track_idx * 4)
        ch_main.play(snd)
        ch_main.set_volume(final_vol, final_vol)

        if not mfx.bypass:
            if mfx.chorus_mix > 0.05:
                ch_chorus = pygame.mixer.Channel(track_idx * 4 + 1)
                w = final_vol * mfx.chorus_mix * 0.55
                ch_chorus.play(snd)
                ch_chorus.set_volume(w * 0.3, w)
            if mfx.reverb_mix > 0.05:
                ch_rev = pygame.mixer.Channel(track_idx * 4 + 2)
                r = final_vol * mfx.reverb_mix * 0.45
                ch_rev.play(snd)
                ch_rev.set_volume(r, r * 0.85)

        self.state.vu_left = min(1.0, max(self.state.vu_left, final_vol))
        self.state.vu_right = min(1.0, max(self.state.vu_right, final_vol * (1.0 + mfx.chorus_mix * 0.15)))

    def update(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last_tick)
        self._last_tick = now

        self.state.vu_left = max(0.0, self.state.vu_left - dt * 2.8)
        self.state.vu_right = max(0.0, self.state.vu_right - dt * 2.8)
        self.state.midi_activity = max(0.0, self.state.midi_activity - dt * 4.0)

        self.sync_dirty_instruments()

        if not self.state.playing:
            self._step_accum = 0.0
            return

        base_step_sec = 60.0 / max(40, min(240, self.state.bpm)) / 4.0
        is_odd_step = (self.state.current_step % 2 == 1)
        swing_factor = (1.0 - self.state.swing * 0.35) if not is_odd_step else (1.0 + self.state.swing * 0.35)
        target_step_sec = base_step_sec * swing_factor

        self._step_accum += dt
        while self._step_accum >= target_step_sec:
            self._step_accum -= target_step_sec
            self._trigger_current_step()
            self._advance_step()

    def _trigger_current_step(self):
        if self.state.sync_out_2ppqn and (self.state.current_step % 2 == 0):
            ch_sync = pygame.mixer.Channel(31)
            ch_sync.play(self.sync_pulse_sound)
            ch_sync.set_volume(0.0, 1.0)

        bar = self.state.current_bar
        step_idx = self.state.current_step
        drive = 0.0 if self.state.master_fx.bypass else self.state.master_fx.tape_drive

        for t in range(self.state.NUM_TRACKS):
            if not self.state.is_track_audible(t):
                continue
            pat_idx = self.state.song_grid[bar][t]
            if pat_idx < 0 or pat_idx >= self.state.NUM_PATTERNS:
                continue

            step = self.state.patterns[t][pat_idx][step_idx]
            if not step.active:
                continue

            inst_idx = step.inst
            inst_data = self.state.instruments[inst_idx]
            semi = step.note - inst_data.root_note
            extra_cut = 0.0
            extra_res = 0.0
            eff_slice = step.slice_pos

            if t == self.state.active_track:
                semi += int(round(self.state.live_pitch_bend))
                extra_cut = self.state.live_filter_offset
                extra_res = self.state.live_res_offset
                if self.state.live_stutter > 0.05:
                    eff_slice = min(0.9375, eff_slice + self.state.live_stutter * 0.5)

            snd = self.instruments[inst_idx].get_sound(
                inst_data, semitone_offset=semi, slice_offset=eff_slice,
                tape_drive=drive, extra_cutoff=extra_cut, extra_res=extra_res
            )
            self._play_with_master_fx(snd, track_idx=t, step_vol=step.vol)

    def _advance_step(self):
        self.state.current_step += 1
        if self.state.current_step >= self.state.STEPS_PER_PATTERN:
            self.state.current_step = 0
            if self.state.loop_bar_mode:
                self.state.current_bar = self.state.cursor_bar
            else:
                next_bar = (self.state.current_bar + 1) % self.state.SONG_BARS
                if all(p < 0 for p in self.state.song_grid[next_bar]):
                    next_bar = 0
                self.state.current_bar = next_bar

    def export_song_wav(self, filename="ggrain_master_export.wav"):
        out_path = os.path.join(self.state.base_dir, filename)
        step_samples = int((60.0 / max(40, self.state.bpm) / 4.0) * SAMPLE_RATE)

        active_bars = 1
        for b in range(self.state.SONG_BARS):
            if any(p >= 0 for p in self.state.song_grid[b]):
                active_bars = b + 1

        total_steps = active_bars * self.state.STEPS_PER_PATTERN
        total_len = total_steps * step_samples + SAMPLE_RATE
        mix_l = [0.0] * total_len
        mix_r = [0.0] * total_len

        mfx = self.state.master_fx
        drive = 0.0 if mfx.bypass else mfx.tape_drive

        for g_step in range(total_steps):
            bar = g_step // self.state.STEPS_PER_PATTERN
            s_idx = g_step % self.state.STEPS_PER_PATTERN
            pos_sample = g_step * step_samples

            for t in range(self.state.NUM_TRACKS):
                if not self.state.is_track_audible(t):
                    continue
                pat_idx = self.state.song_grid[bar][t]
                if pat_idx < 0:
                    continue
                step = self.state.patterns[t][pat_idx][s_idx]
                if not step.active:
                    continue

                inst_data = self.state.instruments[step.inst]
                snd = self.instruments[step.inst].get_sound(
                    inst_data, semitone_offset=(step.note - inst_data.root_note),
                    slice_offset=step.slice_pos, tape_drive=drive
                )
                raw = array.array("h")
                raw.frombytes(snd.get_raw())
                n_frames = len(raw) // 2
                for i in range(min(n_frames, total_len - pos_sample)):
                    val = (raw[i * 2] / 32768.0) * step.vol
                    mix_l[pos_sample + i] += val
                    mix_r[pos_sample + i] += val

        out_buf = array.array("h")
        vol = mfx.master_vol
        for i in range(total_len):
            l = math.tanh(mix_l[i] * vol)
            r = math.tanh(mix_r[i] * vol)
            out_buf.append(int(max(-32767, min(32767, l * 32767))))
            out_buf.append(int(max(-32767, min(32767, r * 32767))))

        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(out_buf.tobytes())
        return out_path

    # ==========================================================================
    # 4. SYNTH LAB ENGINE & WAV TRIM/NORMALIZE
    # ==========================================================================

    def render_synth_lab_samples(self):
        """Genera i campioni float [-1..1] calibrati su C4 dai parametri del Synth Lab."""
        sl = self.state.synth_lab
        n = max(1024, int(SAMPLE_RATE * sl.amp_decay))
        out = [0.0] * n
        base_freq = 261.625565  # C4

        phase = 0.0
        sub_phase = 0.0
        lp_state = 0.0
        hp_state = 0.0
        prev_in = 0.0

        cutoff = sl.filter_cutoff
        alpha_lp = max(0.03, min(1.0, 1.0 - abs(cutoff) * 0.94)) if cutoff < -0.02 else 1.0
        alpha_hp = max(0.05, min(0.98, 1.0 - cutoff * 0.90)) if cutoff > 0.02 else 1.0
        drive = 1.0 + sl.drive_crush * 4.5

        for i in range(n):
            t = i / SAMPLE_RATE
            # Pitch envelope (utile per Kick 808, Tom, Laser, Zap)
            p_env = sl.pitch_env_amt * math.exp(-t / max(0.01, sl.pitch_env_dec))
            freq = max(24.0, base_freq * (2.0 ** (p_env / 12.0)))

            # Amp envelope con fade-in anti-click
            att = min(1.0, i / 48.0)
            dec = math.exp(-t * (4.2 / max(0.05, sl.amp_decay)))
            env = att * dec

            w = sl.wave_type
            if w == "SINE":
                osc = math.sin(2.0 * math.pi * phase)
            elif w == "SQUARE":
                osc = 1.0 if phase < 0.5 else -1.0
            elif w == "PULSE25":
                osc = 1.0 if phase < 0.25 else -1.0
            elif w == "SAW":
                osc = 2.0 * phase - 1.0
            elif w == "TRIANGLE":
                osc = 4.0 * abs(phase - 0.5) - 1.0
            else:  # NOISE
                osc = random.random() * 2.0 - 1.0

            sub = math.sin(2.0 * math.pi * sub_phase) * sl.sub_mix
            sample = (osc * (1.0 - sl.sub_mix * 0.35) + sub) * env

            phase = (phase + freq / SAMPLE_RATE) % 1.0
            sub_phase = (sub_phase + (freq * 0.5) / SAMPLE_RATE) % 1.0

            if cutoff < -0.02:
                lp_state += alpha_lp * (sample - lp_state)
                sample = lp_state
            elif cutoff > 0.02:
                hp_state = alpha_hp * (hp_state + sample - prev_in)
                prev_in = sample
                sample = hp_state

            if sl.drive_crush > 0.02:
                sample = math.tanh(sample * drive) / math.tanh(drive)
                if sl.drive_crush > 0.55:
                    # Leggero bit-crush stile retro hardware
                    steps = 24.0
                    sample = round(sample * steps) / steps

            out[i] = max(-1.0, min(1.0, sample))
        return out

    def audition_synth_lab(self):
        samples = self.render_synth_lab_samples()
        buf = array.array("h")
        for s in samples:
            v = int(max(-32767, min(32767, s * 30000.0)))
            buf.append(v)
            buf.append(v)
        snd = pygame.mixer.Sound(buffer=buf.tobytes())
        self._play_with_master_fx(snd, track_idx=self.state.active_track, step_vol=1.0)

    def bounce_synth_lab_wav(self):
        """Esporta il suono creato nel Synth Lab su WAV e lo carica nello strumento attivo."""
        samples = self.render_synth_lab_samples()
        sl = self.state.synth_lab
        folders = self.state.get_synth_folders()
        folder_name = folders[sl.folder_idx % len(folders)]
        target_dir = os.path.join(self.state.samples_dir, *folder_name.split("/"))
        os.makedirs(target_dir, exist_ok=True)

        ts = int(time.time()) % 100000
        fname = f"{sl.wave_type.lower()}_{ts}.wav"
        out_path = os.path.join(target_dir, fname)

        buf = array.array("h")
        for s in samples:
            v = int(max(-32767, min(32767, s * 31500.0)))
            buf.append(v)
            buf.append(v)

        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(buf.tobytes())

        self.load_wav_into_instrument(self.state.active_inst, out_path)
        return f"{folder_name}/{fname}"

    def trim_and_normalize_instrument_wav(self, inst_idx):
        """Taglia silenzio iniziale e normalizza al 95% il file WAV dello strumento attivo."""
        inst = self.state.instruments[inst_idx]
        if inst.source_type != "WAV" or not inst.sample_path or not os.path.exists(inst.sample_path):
            return False

        samples, file_sr = load_wav_ableton_safe(inst.sample_path)
        if len(samples) < 256:
            return False

        thresh = 0.015
        start_i = 0
        for i, v in enumerate(samples):
            if abs(v) > thresh:
                start_i = max(0, i - 64)
                break

        trimmed = samples[start_i:]
        if len(trimmed) < 128:
            return False

        pk = max(abs(v) for v in trimmed)
        gain = (0.95 / pk) if pk > 1e-4 else 1.0

        buf = array.array("h")
        n = len(trimmed)
        for i, v in enumerate(trimmed):
            env = (i / 32.0) if i < 32 else (max(0.0, (n - i) / 64.0) if i > n - 64 else 1.0)
            s_int = int(max(-32767, min(32767, v * gain * env * 32767.0)))
            buf.append(s_int)
            buf.append(s_int)

        with wave.open(inst.sample_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(file_sr)
            wf.writeframes(buf.tobytes())

        inst.reload_source = True
        inst.dirty = True
        self.sync_dirty_instruments(force=True)
        return True