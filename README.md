```text
 ██████╗  ██████╗ ██████╗  █████╗ ██╗███╗   ██╗
██╔════╝ ██╔════╝ ██╔══██╗██╔══██╗██║████╗  ██║
██║  ███╗██║  ███╗██████╔╝███████║██║██╔██╗ ██║
██║   ██║██║   ██║██╔══██╗██╔══██║██║██║╚██╗██║
╚██████╔╝╚██████╔╝██║  ██║██║  ██║██║██║ ╚████║
 ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝
  >> 4-TRACK GRANULAR WORKSTATION & CHIP-TRACKER <<
  >> CODED IN PURE PYTHON BY:  [ GAS1312 ]  <<
  >>     (with the precious help of gemini)     <<
```
# GGrain v0.1 // R36S Handheld Synthesizer & Tracker
**GGrain** (`seq/sampler by Gas1312`) is a standalone, zero-dependency, pure-Python granular synthesizer, one-shot sampler, and tracker workstation designed specifically for the **R36S handheld console** running **KNULLI OS** (640×480).
Built using only Python's standard library (`array`, `math`, `struct`) and `pygame-ce`, it turns a €35 retro gaming handheld into a pocket electronic music groovebox with hardware MIDI and analog clock sync.
---
## Key Features

### 1. 4-Track Sequencer & 8 Shared Instruments (`2:SONG/SEQ`)
- **Hybrid M8 + Nanoloop Workflow:** Program 4 tracks (`T1`–`T4`) across an 8-bar Song Chain matrix, editing 16 vertical steps per pattern with real-time visual **Slice Position** and **Level** bars.
- **8 Shared Instrument Slots (`I01`–`I08`):** Any track can trigger any of the 8 global instruments on any step, allowing drum kits, basslines, and granular textures to interlock seamlessly.
- **Fast Chip-Tracker Ergonomics:** Instant bar looping (`START`) vs. full song playback (`R1 + START`), 1-click pattern cloning (`X`), LSDJ-style Smart Inheritance (tapping `A` on an active step auditions and picks its parameters without accidental deletion), and per-step octave jumps (`A + L1 + Up/Down`).

### 2. Dual-Engine Instrument Studio (`3:INSTRUMENT`)
- **LSDJ-Style Source Selector:** Switch each slot (`I01`–`I08`) on the fly between external `.wav` samples and built-in C4-calibrated oscillators (`OSC:KICK`, `OSC:SNARE`, `OSC:HAT`, `OSC:SAW`, `OSC:SQR`, `OSC:SUB`).
- **Ableton-Safe WAV Loader:** Natively parses 8/16/24-bit PCM, 32-bit IEEE Float, and `WAVE_FORMAT_EXTENSIBLE` files (stripping DAW metadata chunks) with automatic sample-rate compensation and autocorrelation **Root Note** pitch detection.
- **Granular & One-Shot Shaping:** Switch between `ONE-SHOT` and `GRAIN` engines, sculpt Start Position, Pitch, Grain Size, and Spray with the dual analog sticks, and shape tone with a bipolar **LP/HP Resonant Filter** and dedicated **Mini-LFO**.

### 3. Mini-Synth Lab & WAV Creator (`2B:SYNTH LAB`)
- **On-Console Sound Design (`SELECT + Left` twice):** Build custom kicks, acid basses, chiptune leads, and percussion from scratch without touching a PC.
- **Multi-Wave Synth Engine:** Combine 6 core waveforms (`SINE`, `SQUARE`, `PULSE25`, `SAW`, `TRIANGLE`, `NOISE`) with a `-1 Octave` Sub-Oscillator, exponential Pitch Envelope (for 808 punches and laser zaps), Amp Decay, LP/HP Tone Filter, and Drive / 8-Bit Crush.
- **Direct Folder Bounce:** Dynamically scans all user subfolders inside `samples/` and bounces your patch to a 44.1 kHz / 16-bit stereo `.wav` file (`X`), auto-loading it straight into your active instrument slot.

### 4. Master Bus Processor & Hardware I/O (`4:MASTERING`)
- **4-Stage Master Rack:** **Stereo Chorus / Widener**, **Space Reverb**, **Tape Saturator**, and **Master Compressor / Limiter** with live Gain Reduction (`GR`) metering and instant `X` **A/B Bypass**.
- **USB-OTG Microphone Sampling:** Hot-plug ALSA detection for USB microphones (e.g. Tonor) with live input VU metering; press `X` in `3:INSTRUMENT` to record, auto-trim leading silence, normalize to 95%, and save to `samples/mic/`.
- **USB-MIDI & 2 PPQN Analog Sync:** Play instruments chromatically or step-record patterns via class-compliant USB-MIDI keyboards, or enable **2 PPQN Sync Out** to send mono audio on Left and an 8 ms +5V clock pulse on Right (ideal for M-VAVE FM-1, Korg Volcas, and Pocket Operators).

### 5. LSDJ Project Manager & Custom UI (`1:PROJECT`)
- **8 Named Save Slots:** Save and load complete projects (`ggrain_project_01.json`–`08.json`) with an on-screen **LSDJ-style character grid** (`02. PROJECT NAME`) to title your tracks without a keyboard.
- **Master WAV Export:** Render full arrangements directly to `ggrain_0X_<name>.wav`.
- **3-Color Theme Customizer & Direct Boot:** Customize Base, Text, and Accent colors (saved persistently in `ggrain_config.json`), enable **R36S Direct Boot** (`/userdata/system/custom.sh`), or open the built-in **Developer Gamepad Tester** (`L2 + R2 + SELECT`).

---

## Installation on R36S (KNULLI OS)

1. Copy the `GGrain` folder to `/userdata/roms/ports/GGrain/` on your SD card.
2. Place your `.wav` samples inside any subfolder under `GGrain/samples/` (e.g. `samples/kick/`, `samples/bass/`, `samples/synth/`) — all folders are scanned automatically.
3. Create `/userdata/roms/ports/GGrain.sh` (using **Unix LF** line endings) containing:
   ```bash
   #!/bin/bash
   cd /userdata/roms/ports/GGrain || exit 1
   export SDL_GAMECONTROLLERCONFIG_FILE="/userdata/system/configs/emulationstation/es_input.cfg"
   python3 main.py
   ```
4. Launch **GGrain** from the **Ports** section in KNULLI (or toggle **R36S DIRECT BOOT** inside `1:PROJECT`).

---

## Controls & Shortcuts

| Action | R36S Hardware | PC Keyboard |
| :--- | :--- | :--- |
| **Cross Navigation** (`PROJECT`, `SONG/SEQ`, `INST`, `MASTER`) | `SELECT + D-Pad` | `Backspace + Arrows` |
| **Open Synth Lab / Shortcut Manual** | `SELECT + Left x2` / `Right x2` | `Backspace + Left x2` / `Right x2` |
| **Loop Current Bar** (Play / Stop) | `START` | `Enter` |
| **Play Full Song Chain** (`01–08`) | `R1 + START` | `W + Enter` |
| **Switch Active Track (`T1–T4`) or Inst (`I01–I08`)** | `L1` / `R1` | `Q` / `W` |
| **Mute / Unmute Active Track** | `L3` (Left Stick Click) or `SELECT + B` | `Backspace + X` |
| **Audition Active Inst / Synth Lab** | `R3` (Right Stick Click) or `B` | `X` |
| **Add Step / Pick & Audition / Confirm** | `A` | `Z` |
| **Edit Step Note** (Scale Quantized) | `A + Up / Down` | `Z + Up / Down` |
| **Step Pitch ±1 Octave (`±12st`)** | `A + L1 + Up / Down` | `Z + Q + Up / Down` |
| **Assign Step Instrument (`I01–I08`)** | `A + Left / Right` | `Z + Left / Right` |
| **Adjust Step Slice Offset / Step Volume** | `A + L1 + L/R` / `A + R1 + L/R` | `Z + Q + L/R` / `Z + W + L/R` |
| **Clear Step / Close Popup** | `B` | `X` |
| **Context Action** (Clone / MIDI-Rec / Mic / Bounce / Bypass) | `X` | `A` |
| **Context Workflow Tools Menu** | `Y` | `S` |
| **Live Filter & Res / Slice Scrub & Pitch Bend** | `Left Stick` / `Right Stick` | — |
| **Developer Gamepad & Telemetry Tester** | `L2 + R2 + SELECT` | `F12` |
| **Safe Exit to KNULLI OS** | `SELECT + START` or `SELECT + FN` | `Backspace + Enter` |

---

## License

Released under the **MIT License** — Created by **Gas1312** *(with the precious help of Gemini)*.

## Tutorial

See [TUTORIAL.md](TUTORIAL.md) for a step-by-step song walkthrough.