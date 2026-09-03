# MeetScribe

**Local meeting recorder with Whisper transcription and AI summaries — no cloud, no subscriptions.**

Records audio from your computer (mic + system audio from Zoom, Google Meet, Teams, etc.), transcribes it locally using Whisper, and generates AI meeting summaries via Ollama.

---

## Platform Support

| | macOS | Windows |
|---|---|---|
| **Backend** | `app_mac.py` | `app.py` (`app_windows.py` = in-sync copy) |
| **Dependencies** | `requirements_mac.txt` | `requirements_windows.txt` |
| **Transcription** | mlx-whisper (Apple Silicon) | faster-whisper (CPU, int8) |
| **System audio capture** | BlackHole + Aggregate Device | WASAPI loopback (`soundcard`) — auto-captures **all** output devices |
| **AI Summary** | Ollama (local) | Ollama (local) |
| **Frontend** | React + Vite (shared) | React + Vite (shared) |

---

## macOS Setup

### Requirements

- macOS 12+ with Apple Silicon (M1/M2/M3/M4)
- Python 3.10–3.12
- Node.js 18+
- BlackHole 2ch (free virtual audio cable)
- Ollama (for AI summaries)

### Step 1 — Install BlackHole

BlackHole routes your meeting app's audio into MeetScribe so it can be captured.

1. Download **BlackHole 2ch** from https://existential.audio/blackhole/
2. Run the installer and restart your Mac
3. Confirm it appears in **System Settings → Sound**

### Step 2 — Set Up Audio MIDI

Open **Audio MIDI Setup** (search with Spotlight).

#### Part A — Multi-Output Device (hear the meeting AND capture it)

1. Click **+** → **Create Multi-Output Device**
2. Check in this order:

   | Device | Drift Correction |
   |--------|-----------------|
   | Your speakers / AirPods | ❌ (clock master) |
   | BlackHole 2ch | ✅ |

3. Set **Clock Source** to your speakers/AirPods
4. Right-click → **Use This Device For Sound Output**
5. Rename it **"MeetScribe Output"**

#### Part B — Aggregate Device (captures mic + meeting audio in one stream)

1. Click **+** → **Create Aggregate Device**
2. Check in this order:

   | Device | Use |
   |--------|-----|
   | BlackHole 2ch | ✅ |
   | Your microphone / AirPods | ✅ |

3. Rename it **"MeetScribe Input"**

#### Set your meeting app output

In Zoom / Teams / Meet, set the **Speaker** output to **"MeetScribe Output"**.

### Step 3 — Install Python Dependencies

```bash
pip install -r requirements_mac.txt
```

### Step 4 — Build the Frontend (first time only)

```bash
cd frontend
npm install
npm run build
cd ..
```

### Step 5 — Install Ollama (optional, for AI summaries)

1. Download from https://ollama.com
2. Pull the model:
   ```bash
   ollama pull minimax-m2.7:cloud
   ```

### Step 6 — Run MeetScribe

```bash
python3 app_mac.py
```

Open: **http://localhost:5001**

### Step 7 — Select Your Devices in the UI

- **Mic Input** → select **"MeetScribe Input"** (the Aggregate Device)
- **Loopback** → leave blank (the Aggregate Device already combines both streams)

---

## Windows Setup

### Requirements

- Windows 10 or 11
- Python 3.10–3.12
- Node.js 18+
- Ollama (for AI summaries)
- No virtual audio cable and no Stereo Mix needed — capture is fully automatic

### Step 1 — System audio capture (automatic)

Nothing to set up. MeetScribe uses WASAPI loopback (via the `soundcard` library) to capture your computer's audio directly, and it records **every** output device at once — built-in speakers, wired headphones, USB wireless dongles, and Bluetooth. Whichever device your meeting audio plays through is captured automatically. No Stereo Mix, no virtual cable, no device selection.

### Step 2 — Install Python Dependencies

```bash
pip install -r requirements_windows.txt
```

### Step 3 — Build the Frontend (first time only)

```bash
cd frontend
npm install
npm run build
cd ..
```

### Step 4 — Install Ollama (optional, for AI summaries)

1. Download from https://ollama.com
2. Pull the model:
   ```bash
   ollama pull minimax-m2.7:cloud
   ```

### Step 5 — Run MeetScribe

```bash
python app.py
```

> `app.py` is the Windows entry point that actually runs. `app_windows.py` is kept as an in-sync copy — any edit must land in both.

Open: **http://localhost:5001**

### Step 6 — Select Your Mic in the UI

- **Mic Input** → select your microphone (or leave as default — "Microsoft Sound Mapper" uses the Windows default input)
- **System Audio** → nothing to pick. It reads **"Auto (follows active output)"** — MeetScribe captures every output device and mixes them with your mic automatically.

### Headsets & USB dongles (Bluetooth, wireless gaming, etc.) on Windows

Because MeetScribe now captures **all** output devices, it no longer matters which one your meeting plays through — a USB wireless dongle, wired headphones, or the built-in speakers are all captured automatically. Set your headset as the default input in **Windows Settings → System → Sound → Input** and leave Mic as "Microsoft Sound Mapper" so MeetScribe uses it.

One physical limit remains: a **Bluetooth** headset in call (Hands-Free / HFP) mode can genuinely stop sending audio to any loopback endpoint. If that happens, MeetScribe detects the silence live and flags the recording (see the safeguard below). A wired or USB-dongle output avoids it entirely.

---

## Daily Usage

1. Open your meeting app and join the call
2. Go to **http://localhost:5001**
3. Enter a meeting name and click **Start Recording**
4. When done, click **Stop Recording** — transcription starts automatically
5. Once complete, click **Transcript** or **Summary** to view the results

---

## How Audio Capture Works

### macOS
The Aggregate Device in Audio MIDI Setup combines BlackHole (system audio from the meeting) and your microphone into a single stream. MeetScribe captures it in one go.

### Windows
MeetScribe opens one audio stream for your mic and a WASAPI **loopback stream for every output device** (via the `soundcard` library), all in parallel. At stop time it sums the loopback streams — idle devices contribute silence, the active one carries the meeting — then mixes that with the mic 50/50 before saving the WAV. This is why device selection is unnecessary: whichever output the meeting uses is already being recorded.

**Live audio-health safeguard:** MeetScribe monitors the loopback level while recording. If no system audio is detected on any output (e.g. a Bluetooth headset dropped into HFP mode, or nothing is actually playing), it shows a live ⚠️ warning during the meeting, marks the recording **"⚠️ No audio,"** and skips the AI summary rather than generating a hallucinated one from silence.

---

## AI Summary

After transcription, MeetScribe calls your local Ollama instance to generate a meeting summary using `minimax-m2.7:cloud`. The summary includes:

- Brief overview
- Key topics discussed
- Action items
- Decisions made

If Ollama is not running, the transcript is still saved — only the summary is skipped.

---

## Features

| Feature | Supported |
|---------|-----------|
| On-demand recording | ✅ |
| Mic + system audio capture | ✅ |
| Auto-capture of **all** output devices (Windows) | ✅ |
| Live audio-loss detection + "⚠️ No audio" flag | ✅ |
| Timestamped transcript | ✅ |
| AI meeting summary (Ollama, local) | ✅ |
| Per-meeting folder organization | ✅ |
| Delete recording + all files | ✅ |
| React UI (light theme) | ✅ |
| Fully offline | ✅ |
| Speaker diarization | ❌ (future) |

---

## Project Structure

```
meetscribe/
├── app.py                  # Windows backend — the entry point that runs (faster-whisper)
├── app_windows.py          # in-sync copy of app.py
├── app_mac.py              # macOS backend (mlx-whisper)
├── requirements_mac.txt
├── requirements_windows.txt
├── recordings_index.json   # per-meeting metadata
├── recordings/             # raw .wav + transcripts (one folder per meeting)
└── frontend/               # shared React + Vite app
    ├── src/
    │   ├── App.jsx
    │   └── components/
    │       ├── Topbar.jsx
    │       ├── Recorder.jsx
    │       ├── RecordingsList.jsx
    │       └── TranscriptModal.jsx
    ├── dist/               # built app served by Flask (run npm run build)
    └── vite.config.js
```

---

## Troubleshooting

**Transcript is empty / no audio recorded**
→ On macOS, verify the Aggregate Device appears in the dropdown and is selected. On Windows, system audio is captured automatically — if a recording is flagged **"⚠️ No audio,"** it means no sound reached any output device (check the meeting was actually playing audio; if on a Bluetooth headset, try a wired or USB output).

**Windows: other participants' voices missing, only your mic captured**
→ This was the old default-speaker-only bug (fixed 2026-07): MeetScribe used to record only the Windows default output, so audio playing through a different device (e.g. a USB headset dongle) was missed. It now records **every** output device — make sure you're on the current `app.py` / `app_windows.py`.

**BlackHole not showing in device list (macOS)**
→ Restart MeetScribe after installing BlackHole. Confirm it appears in System Settings → Sound first.

**Can't hear the meeting while recording (macOS)**
→ Your meeting app must output to the Multi-Output Device, not your speakers directly.

**Transcription is slow**
→ Normal on first run (model download ~140MB). On Windows, CPU transcription with `base` model takes roughly 0.5–1× real time.

**Ollama summary not generating**
→ Run `ollama serve` in a terminal, or check it's running with `curl http://localhost:11434/api/tags`.

---

Built with ❤️ by CELESTIAL Coding Agent for Joseph.
