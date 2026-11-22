import os
import re
import time
import math
import wave
import array
import struct
import threading
import subprocess
from collections import deque
from datetime import datetime

SAMPLE_RATE = 44100


class HardwareIOManager:
    """
    Gestisce in background (zero lag sul clock audio):
    1. Rilevamento hot-plug Microfono USB (Tonor ecc.) + Input VU-Meter + REC Mono->Stereo
    2. Rilevamento hot-plug Tastiera USB-MIDI (/dev/snd/midi*)
    3. Lettura batteria R36S e telemetria per la Developer Debug Mode
    """

    def __init__(self, state):
        self.state = state
        self._running = True

        # Stato USB Mic
        self._mic_card_idx = None
        self._mic_device_str = ""
        self._rec_frames = bytearray()
        self._rec_lock = threading.Lock()
        self._was_recording = False
        self.last_recorded_wav = None  # Letto da main.py appena finisce la registrazione

        # Stato USB MIDI
        self._midi_dev_path = None
        self._midi_fd = None
        self.midi_note_queue = deque(maxlen=64)  # Coda thread-safe di (note, velocity)

        # Telemetria Debug
        self.battery_pct = 100
        self.battery_charging = False
        self.last_scan_time = 0.0
        self.last_bat_time = 0.0

        # Avvia thread daemon per monitoraggio periferiche e stream audio mic
        self._hotplug_thread = threading.Thread(target=self._hotplug_loop, daemon=True)
        self._hotplug_thread.start()

        self._mic_thread = threading.Thread(target=self._mic_stream_loop, daemon=True)
        self._mic_thread.start()

    def shutdown(self):
        self._running = False
        self._close_midi()

    # ==========================================================================
    # 1. HOT-PLUG SCANNER (ALSA USB MIC + RAW MIDI + BATTERIA)
    # ==========================================================================

    def _hotplug_loop(self):
        while self._running:
            now = time.monotonic()

            # Scansiona USB Mic e MIDI ogni 1.5 secondi
            if now - self.last_scan_time >= 1.5:
                self.last_scan_time = now
                self._scan_usb_mic()
                self._scan_usb_midi()

            # Legge batteria ogni 5 secondi
            if now - self.last_bat_time >= 5.0:
                self.last_bat_time = now
                self._read_battery()

            # Leggi eventuali byte MIDI in arrivo (polling rapido 5ms)
            self._poll_midi_bytes()
            time.sleep(0.005)

    def _scan_usb_mic(self):
        """Legge /proc/asound/cards su Linux per trovare microfoni USB (es. Tonor)."""
        cards_path = "/proc/asound/cards"
        if not os.path.exists(cards_path):
            # Ambiente Windows/PC di test
            self.state.mic_connected = False
            self.state.mic_name = "NO LINUX ALSA (PC)"
            self._mic_card_idx = None
            return

        try:
            with open(cards_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            found_idx = None
            found_name = "NOT CONNECTED"

            # Cerca righe tipo: " 1 [Device         ]: USB-Audio - USB PnP Sound Device"
            for line in content.splitlines():
                m = re.match(r"^\s*(\d+)\s+\[.*?\]:\s*(.+)$", line)
                if m:
                    idx = int(m.group(1))
                    desc = m.group(2).strip()
                    low = desc.lower()
                    # Ignora la scheda interna Rockchip (rk3326 / rk817)
                    if "usb" in low or "mic" in low or "tonor" in low or "pnp" in low or "audio" in low:
                        if "rk3326" not in low and "rk817" not in low and "rockchip" not in low:
                            found_idx = idx
                            # Estrae nome pulito dopo il trattino se presente
                            clean = desc.split("-")[-1].strip() if "-" in desc else desc
                            found_name = clean[:22]
                            break

            if found_idx is not None:
                self._mic_card_idx = found_idx
                self._mic_device_str = f"plughw:{found_idx},0"
                self.state.mic_connected = True
                self.state.mic_name = found_name
            else:
                self._mic_card_idx = None
                self._mic_device_str = ""
                self.state.mic_connected = False
                self.state.mic_name = "NOT CONNECTED"
                self.state.mic_level = 0.0
        except Exception:
            self._mic_card_idx = None
            self.state.mic_connected = False
            self.state.mic_name = "SCAN ERROR"

    def _scan_usb_midi(self):
        """Cerca porte raw MIDI in /dev/snd/midi* (tastiere USB-OTG)."""
        snd_dir = "/dev/snd"
        if not os.path.isdir(snd_dir):
            self.state.midi_connected = False
            self.state.midi_name = "NOT CONNECTED"
            return

        try:
            midi_devs = sorted(
                os.path.join(snd_dir, fn)
                for fn in os.listdir(snd_dir)
                if fn.startswith("midi")
            )
            if not midi_devs:
                self._close_midi()
                self.state.midi_connected = False
                self.state.midi_name = "NOT CONNECTED"
                return

            target = midi_devs[0]
            if self._midi_dev_path != target or self._midi_fd is None:
                self._close_midi()
                fd = os.open(target, os.O_RDONLY | os.O_NONBLOCK)
                self._midi_fd = fd
                self._midi_dev_path = target
                self.state.midi_connected = True
                self.state.midi_name = os.path.basename(target).upper()
        except Exception:
            self._close_midi()
            self.state.midi_connected = False
            self.state.midi_name = "NOT CONNECTED"

    def _close_midi(self):
        if self._midi_fd is not None:
            try:
                os.close(self._midi_fd)
            except Exception:
                pass
        self._midi_fd = None
        self._midi_dev_path = None

    def _poll_midi_bytes(self):
        """Parser MIDI raw leggero per Note-On da tastiera USB OTG."""
        if self._midi_fd is None:
            return
        try:
            data = os.read(self._midi_fd, 64)
            if not data:
                return
            i = 0
            n = len(data)
            while i < n:
                status = data[i]
                cmd = status & 0xF0
                # Note On (0x90) con 2 byte dati
                if cmd == 0x90 and i + 2 < n:
                    note = data[i + 1] & 0x7F
                    vel = data[i + 2] & 0x7F
                    if vel > 0:
                        self.midi_note_queue.append((note, vel))
                        self.state.midi_activity = 1.0
                    i += 3
                elif cmd in (0x80, 0xA0, 0xB0, 0xE0) and i + 2 < n:
                    i += 3
                elif cmd in (0xC0, 0xD0) and i + 1 < n:
                    i += 2
                else:
                    i += 1
        except BlockingIOError:
            pass
        except OSError:
            # Dispositivo scollegato a caldo
            self._close_midi()
            self.state.midi_connected = False
            self.state.midi_name = "NOT CONNECTED"

    def _read_battery(self):
        base = "/sys/class/power_supply"
        if not os.path.isdir(base):
            return
        for name in ("battery", "BAT0", "rk817-battery"):
            cap_file = os.path.join(base, name, "capacity")
            stat_file = os.path.join(base, name, "status")
            if os.path.exists(cap_file):
                try:
                    with open(cap_file, "r") as f:
                        self.battery_pct = max(0, min(100, int(f.read().strip())))
                    if os.path.exists(stat_file):
                        with open(stat_file, "r") as f:
                            self.battery_charging = (f.read().strip().lower() == "charging")
                except Exception:
                    pass
                break

    # ==========================================================================
    # 2. STREAM AUDIO USB MIC (LIVE VU-METER + REGISTRAZIONE CON AUTO-TRIM)
    # ==========================================================================

    def _mic_stream_loop(self):
        """
        Mantiene attivo arecord quando il mic USB e' collegato:
        - Calcola il livello in ingresso in tempo reale (Input VU-Meter)
        - Cattura i frame quando state.mic_recording == True
        """
        proc = None
        active_dev = ""
        chunk_bytes = 2048  # 1024 campioni mono 16-bit (~23 ms)

        while self._running:
            target_dev = self._mic_device_str if self.state.mic_connected else ""

            # Se il microfono e' stato scollegato o cambiato, chiudi il vecchio processo
            if proc is not None and target_dev != active_dev:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except Exception:
                    pass
                proc = None
                active_dev = ""

            # Se c'e' un microfono collegato e arecord non e' ancora avviato, avvialo
            if target_dev and proc is None:
                try:
                    cmd = [
                        "arecord",
                        "-D", target_dev,
                        "-f", "S16_LE",
                        "-c", "1",
                        "-r", str(SAMPLE_RATE),
                        "-t", "raw",
                        "-q"
                    ]
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        bufsize=chunk_bytes
                    )
                    active_dev = target_dev
                except Exception:
                    proc = None
                    time.sleep(1.0)
                    continue

            if proc is None:
                # Controlla se l'utente ha appena fermato una registrazione
                if self._was_recording and not self.state.mic_recording:
                    self._finalize_recording()
                self._was_recording = self.state.mic_recording
                time.sleep(0.1)
                continue

            # Leggi blocco PCM mono 16-bit dal microfono
            try:
                raw = proc.stdout.read(chunk_bytes)
                if not raw:
                    proc = None
                    active_dev = ""
                    time.sleep(0.2)
                    continue

                # Calcola picco per VU-Meter live (campionando 1 ogni 4 per zero carico CPU)
                samples = array.array("h")
                samples.frombytes(raw)
                peak = 0
                for s in samples[::4]:
                    a = -s if s < 0 else s
                    if a > peak:
                        peak = a
                lvl = min(1.0, (peak / 32768.0) * 1.6)
                self.state.mic_level = max(lvl, self.state.mic_level * 0.72)

                # Gestione stato registrazione
                if self.state.mic_recording:
                    with self._rec_lock:
                        if not self._was_recording:
                            self._rec_frames = bytearray()
                        # Limite di sicurezza 10 secondi max
                        if len(self._rec_frames) < SAMPLE_RATE * 2 * 10:
                            self._rec_frames.extend(raw)
                elif self._was_recording:
                    self._finalize_recording()

                self._was_recording = self.state.mic_recording

            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
                proc = None
                active_dev = ""
                time.sleep(0.5)

    def _finalize_recording(self):
        """Taglia silenzio iniziale, normalizza, converte Mono->Stereo e salva WAV."""
        with self._rec_lock:
            raw_bytes = bytes(self._rec_frames)
            self._rec_frames = bytearray()

        if len(raw_bytes) < 2048:
            return

        mono = array.array("h")
        mono.frombytes(raw_bytes)

        # 1. Trim silenzio iniziale (soglia ~ -38 dB)
        thresh = 420
        start_idx = 0
        for i, v in enumerate(mono):
            if abs(v) > thresh:
                start_idx = max(0, i - 128)  # 3ms di pre-roll anti-click
                break

        trimmed = mono[start_idx:]
        if len(trimmed) < 512:
            return

        # 2. Normalizzazione al 95%
        max_pk = max(abs(v) for v in trimmed)
        gain = (31000.0 / max_pk) if max_pk > 100 else 1.0

        # 3. Conversione Mono -> Stereo interleaved con fade-in/out morbido
        stereo = array.array("h")
        n = len(trimmed)
        for i, v in enumerate(trimmed):
            env = 1.0
            if i < 64:
                env = i / 64.0
            elif i > n - 128:
                env = max(0.0, (n - i) / 128.0)
            s_val = int(max(-32767, min(32767, v * gain * env)))
            stereo.append(s_val)
            stereo.append(s_val)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        mic_dir = os.path.join(self.state.samples_dir, "mic")
        os.makedirs(mic_dir, exist_ok=True)
        out_path = os.path.join(mic_dir, f"mic_{ts}.wav")

        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(stereo.tobytes())

        self.last_recorded_wav = out_path

    # ==========================================================================
    # 3. TELEMETRIA PER DEVELOPER DEBUG MODE
    # ==========================================================================

    def get_debug_telemetry(self):
        return {
            "mic_card": self._mic_device_str if self._mic_device_str else "NONE",
            "mic_name": self.state.mic_name,
            "mic_lvl": f"{int(self.state.mic_level * 100):03d}%",
            "midi_dev": self._midi_dev_path if self._midi_dev_path else "NONE",
            "bat": f"{self.battery_pct}%{' (CHG)' if self.battery_charging else ''}",
        }