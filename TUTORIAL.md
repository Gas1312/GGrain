# GGrain v1.0 // Quickstart Tutorial: Building Your First 4-Bar Song

In **GGrain v1.0**, **`2:SONG/SEQ`** (`SELECT + D-Pad Left`) combines an LSDJ-style **Song Chain Matrix** on the left with a **16-Step Vertical Sequencer** on the right:
- **Left Panel (`SONG CHAIN`):** 4 tracks (**`T1`–`T4`**) arranged across **8 bars (`01`–`08`)**. Each cell holds a pattern number (`01`–`08`) or `--` (silent bar).
- **Right Panel (`STEPS`):** 16 vertical steps (`01`–`16`) for the selected bar and track, showing **Note**, **Instrument (`I01`–`I08`)**, **Slice/Pos**, and **Level** bars.
- **Dual Playback Modes:** Press **`START`** (`Enter`) to **Loop** the current bar infinitely while editing (`LOOP`), or **`R1 + START`** (`W + Enter`) to play the **Full Song Chain** (`SONG`) from bar `01` through your arranged bars.

Follow this button-by-button walkthrough to build a complete **4-bar electronic groove** (Kick + Minor Acid Bassline + Off-beat Hi-Hat + Snare) directly on your R36S (PC keyboard equivalents are shown in brackets).

---

## Step 1: Shape Your Instruments (`3:INSTRUMENT` & `2B:SYNTH LAB`)

GGrain boots directly into **`2:SONG/SEQ`** with 8 shared instrument slots (`I01`–`I08`) pre-loaded and calibrated to `C4`:
- **`I01`:** `OSC:KICK` | **`I02`:** `OSC:SNARE` | **`I03`:** `OSC:HAT` | **`I04`:** `OSC:SAW` | **`I05`:** `OSC:SQR` | **`I06`:** `OSC:SUB` | **`I07`–`I08`:** `WAV`

1. **Shape the Bass Sound on `I04`:**
   - Press **`SELECT + D-Pad Right`** (`Backspace + Right`) to open **`3:INSTRUMENT`**.
   - Press **`R1`** (`W`) 3 times to select slot **`I04`** (`OSC:SAW`).
   - Verify row **`ROOT / SCALE`** is set to **`C4 / MINOR`** (all notes programmed with `I04` will stay in key automatically).
   - Press **`D-Pad Down`** to highlight **`FILTER LP/HP`**, then press **`D-Pad Left`** 4 times to dial in a warm Low-Pass filter (**`LP 32%`**). Hold **`A + D-Pad Right`** (`Z + Right`) 3 times to add filter resonance (**`RES 30%`**).
2. *(Optional)* **Design a Custom Kick or Bass in `2B:SYNTH LAB`:**
   - Press **`SELECT + D-Pad Left`** twice (`Backspace + Left` x2) to enter **`2B:SYNTH LAB`**.
   - Press **`Y`** (`S`) to load a starter preset (e.g. `808 KICK PUNCH` or `ACID SAW BASS`), sculpt it with the D-Pad or Analog Sticks, and press **`X`** (`A`) to bounce it to `.wav` and auto-load it into your active instrument slot.
3. Return to **`2:SONG/SEQ`** with **`SELECT + D-Pad Left`** (`Backspace + Left`).

---

## Step 2: Program 2 Kick Variations on `T1` (`2:SONG/SEQ`)

When GGrain starts, **`Bar 01`** already has **`PAT 01`** assigned across `T1`–`T4`, and your cursor is on **`T1`**, **`STEP 01`**.

1. **Start Bar Loop Playback:**
   - Press **`START`** (`Enter`). The top bar switches from `HOLD` to **`LOOP`**, looping the 16 steps of `Bar 01` so you hear every edit immediately.
2. **Program `PAT 01` (Steady 4/4 Kick using `I01`):**
   - On **`STEP 01`**, tap **`A`** (`Z`) to turn the kick `ON` (note `C4`, instrument `I01`).
   - Press **`D-Pad Down`** 4 times to **`STEP 05`** -> tap **`A`** (`Z`).
   - Press **`D-Pad Down`** 4 times to **`STEP 09`** -> tap **`A`** (`Z`).
   - Press **`D-Pad Down`** 4 times to **`STEP 13`** -> tap **`A`** (`Z`).
3. **Clone `PAT 01` into `PAT 02` for a Bar-4 Turnaround Fill:**
   - Press **`D-Pad Left`** to move focus to the left **Song Chain Matrix** (`Bar 01`, `T1`).
   - Press **`D-Pad Down`** 3 times to highlight **`Bar 04`** (currently `--`).
   - Hold **`A + D-Pad Up`** (`Z + Up`) once to assign **`01`**, then press **`X`** (`A`) to **Clone** `PAT 01` into **`PAT 02`** (focus automatically jumps back to the right-hand step editor on `Bar 04`).
   - Press **`D-Pad Up`** once from `STEP 01` to wrap straight to **`STEP 16`**, and tap **`A`** (`Z`) to add the double-kick turnaround hit.

---

## Step 3: Program a Minor Bassline on `T2` (`2:SONG/SEQ`)

1. Press **`D-Pad Left`** to return to the Song Matrix, press **`D-Pad Up`** 3 times back to **`Bar 01`**, and press **`R1`** (`W`) once to select **`T2`**.
2. Press **`D-Pad Right`** to enter **`STEPS`** for `T2` (`PAT 01`):
   - **Step `01` (Root `C3` with `I04`):** Hold **`A + D-Pad Right`** (`Z + Right`) 2 times so `INST` changes from `I02` to **`I04`** (`OSC:SAW`). Then hold **`A + L1 + D-Pad Down`** (`Z + Q + Down`) once to drop the pitch 1 octave from `C4` to **`C3`**.
   - **Step `04` (`C3`):** Press **`D-Pad Down`** 3 times to `STEP 04` and tap **`A`** (`Z`). Thanks to **Smart Inheritance**, it automatically uses `I04` and `C3`.
   - **Step `07` (`C3`):** Press **`D-Pad Down`** 3 times to `STEP 07` and tap **`A`** (`Z`).
   - **Step `11` (Fifth `G3`):** Press **`D-Pad Down`** 4 times to `STEP 11`, tap **`A`** (`Z`), then hold **`A + D-Pad Up`** (`Z + Up`) 4 times in the `MINOR` scale (`C3 -> D3 -> D#3 -> F3 -> G3`).
   - **Step `14` (Ghost Note `C3`):** Press **`D-Pad Down`** 3 times to `STEP 14`, tap **`A`** (`Z`), press **`A + L1 + D-Pad Down`** (`Z + Q + Down`) to return to **`C3`**, and hold **`A + R1 + D-Pad Left`** (`Z + W + Left`) 4 times to lower its **Level** bar to `60%`.
3. **Create an Octave-Lift Variation (`PAT 02`) for Bars 3 & 4:**
   - Press **`D-Pad Left`** to focus the Song Matrix (`Bar 01`, `T2`), press **`D-Pad Down`** twice to **`Bar 03`**, press **`A + D-Pad Up`** (`Z + Up`) to set `01`, and press **`X`** (`A`) to clone it into **`PAT 02`**.
   - On **`STEP 11`** (still highlighted!), hold **`A + L1 + D-Pad Up`** (`Z + Q + Up`) once to lift `G3` up an octave to **`G4`**.

---

## Step 4: Program Off-Beat Hi-Hats (`T3`) & Snare (`T4`)

1. **Off-Beat Hi-Hat on `T3`:**
   - Press **`R1`** (`W`) to switch to **`T3`** (defaults to **`I03`** = `OSC:HAT`).
   - Activate steps **`03`**, **`07`**, **`11`**, and **`15`** by tapping **`A`** (`Z`) on each.
   - *(Tip)* Hold **`A + R1 + D-Pad Left/Right`** (`Z + W + Left/Right`) on steps `03` and `11` to lower their **Level** slightly for a natural shuffle feel.
2. **Backbeat Snare on `T4`:**
   - Press **`R1`** (`W`) to switch to **`T4`** (defaults to **`I02`** = `OSC:SNARE`).
   - Move to **`STEP 05`** -> tap **`A`** (`Z`), then move to **`STEP 13`** -> tap **`A`** (`Z`).

---

## Step 5: Arrange the 4-Bar Song Chain (`2:SONG/SEQ` Left Matrix)

Press **`D-Pad Left`** to focus the **Song Chain Matrix** on the left and arrange Bars **`01`–`04`** across all 4 tracks:

| Bar | `T1` (Kick) | `T2` (Bass) | `T3` (Hi-Hat) | `T4` (Snare) | Musical Role |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`01`** | `01` | `01` | `--` | `--` | Intro (Kick + Low Bass) |
| **`02`** | `01` | `01` | `01` | `01` | Drums Drop In |
| **`03`** | `01` | `02` | `01` | `01` | Bass Octave Lift |
| **`04`** | `02` | `02` | `01` | `01` | Kick Turnaround Fill |

- Use **`A + D-Pad Up/Down`** (`Z + Up/Down`) to set pattern numbers (`01` or `02`), and **`B`** (`X`) to clear a cell to `--` (mute `T3` and `T4` on `Bar 01` for the intro).
- Leave **`Bar 05`** as `-- -- -- --` so the Song Chain loops cleanly after 4 bars.

---

## Step 6: Full Song Playback, Live Jam & LSDJ Save

1. **Launch Full Song Mode:**
   - Move the cursor back up to **`Bar 01`** and press **`R1 + START`** (`W + Enter`).
   - The top status badge changes to **`SONG`**: all 4 tracks play Bars `01` -> `02` -> `03` -> `04` in sync and loop back to `Bar 01`.
2. **Live Analog Stick Performance:**
   - Move the **Left Stick** (`X/Y`) to sweep **Filter Cutoff & Resonance** on the active track.
   - Move the **Right Stick** (`X/Y`) to perform live **Slice Scrubbing & Pitch Bends**.
   - Press **`SELECT + B`** (`Backspace + X`) at any time to mute/unmute tracks on the fly.
3. **Master Polish (`4:MASTERING`):**
   - Press **`SELECT + D-Pad Down`** (`Backspace + Down`) to open **`4:MASTERING`**, tweak **Stereo Chorus**, **Space Reverb**, **Tape Saturator**, and **Master Compressor**, or press **`X`** (`A`) to A/B Bypass the entire rack.
4. **Name & Save Your Song (`1:PROJECT`):**
   - Press **`SELECT + D-Pad Up`** (`Backspace + Up`) to open **`1:PROJECT`**.
   - Highlight **`02. PROJECT NAME`**, press **`A`** (`Z`) to open the **LSDJ-style character grid**, spell a title (e.g. `FIRST_SONG`), and press **`START`** (`Enter`) to confirm.
   - Highlight **`04. SAVE PROJECT`** and press **`A`** (`Z`) to save the complete project to **Slot `01`** (or export a stereo `.wav` via **`07. EXPORT MASTER WAV`**).