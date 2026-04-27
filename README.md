# MeetScribe

**Local meeting recorder with Whisper transcription and AI summaries — no cloud, no subscriptions.**

Records audio from your computer (mic + system audio from Zoom, Google Meet, Teams, etc.), transcribes it locally using Whisper, and generates AI meeting summaries via Ollama.

---

## Platform Support

| | macOS | Windows |
|---|---|---|
| **Backend** | `app_mac.py` | `app_windows.py` |
| **Dependencies** | `requirements_mac.txt` | `requirements_windows.txt` |
| **Transcription** | mlx-whisper (Apple Silicon) | faster-whisper (CPU, int8) |
| **System audio capture** | BlackHole + Aggregate Device | WASAPI Stereo Mix (built-in) |
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
- No virtual audio cable needed — Windows has built-in Stereo Mix

### Step 1 — Enable Stereo Mix

Stereo Mix captures all system audio (meeting participants) as a virtual input. No extra software needed.

1. Right-click the speaker icon in the taskbar → **Sound settings**
2. Go to **Sound Control Panel** → **Recording** tab
3. Right-click in the empty area → **Show Disabled Devices**
4. Right-click **Stereo Mix** → **Enable**
5. If Stereo Mix is missing, update your audio driver (Realtek HD Audio includes it by default)

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
python app_windows.py
```

Open: **http://localhost:5001**

### Step 6 — Select Your Devices in the UI

- **Mic Input** → select your microphone (or leave as default — "Microsoft Sound Mapper" uses the Windows default input)
- **Loopback / System Audio** → select **Stereo Mix**

Both streams are recorded in parallel and mixed before transcription.

### Bluetooth headsets (AirPods, etc.) on Windows

Set your headset as the default input in **Windows Settings → System → Sound → Input**, then leave Mic as "Microsoft Sound Mapper" in MeetScribe — it will use your headset automatically.

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
MeetScribe opens **two parallel audio streams** — one for your mic and one for Stereo Mix — then mixes them 50/50 in Python before saving the WAV file.

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
├── app_mac.py              # macOS backend (mlx-whisper)
├── app_windows.py          # Windows backend (faster-whisper)
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
→ Make sure both devices are selected before clicking Start. On macOS, verify the Aggregate Device appears in the dropdown.

**Stereo Mix not in device list (Windows)**
→ Enable it in Control Panel → Sound → Recording (right-click → Show Disabled Devices). If missing, update your Realtek audio driver.

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
