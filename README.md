# MeetScribe

**Local meeting recorder with Whisper transcription — no cloud, no subscriptions.**

Records audio from your computer (meeting apps like Zoom, Google Meet, Teams, Facebook Messenger all route through a virtual audio cable), transcribes it locally using Whisper, and exports timestamped .txt transcripts.

---

## Requirements

- **macOS 12+** (also works on Windows 10/11)
- **Python 3.10 or 3.11**
- **BlackHole** (free virtual audio cable for macOS) — routes meeting audio to MeetScribe
- **8GB+ RAM** recommended (16GB for smooth Whisper CPU transcription)

---

## Setup

### Step 1 — Install BlackHole (Virtual Audio Cable)

BlackHole routes audio from your meeting app into MeetScribe.

1. Download **BlackHole 2ch** from: https://existential.audio/blackhole/
2. Run the installer and restart your Mac
3. Verify it appears in **System Settings → Sound** as an input/output option

### Step 2 — Set Up Audio MIDI (Two Devices Required)

You need **two virtual devices** — one for output (hear + capture meeting audio) and one for input (capture your mic + meeting audio together).

Open **Audio MIDI Setup** (search in Spotlight).

#### Part A — Multi-Output Device (so you hear the meeting AND BlackHole captures it)

1. Click **+** → **Create Multi-Output Device**
2. Check devices in this order:

   | Device | Drift Correction |
   |--------|-----------------|
   | AirPods | ❌ (clock master) |
   | BlackHole 2ch | ✅ |

3. Set **Clock Source → AirPods**
4. Right-click → **Use This Device For Sound Output**
5. Rename it **"MeetScribe Output"**

#### Part B — Aggregate Device (captures your mic + meeting audio in one stream)

1. Click **+** → **Create Aggregate Device**
2. Check devices in this order:

   | Device | Use |
   |--------|-----|
   | BlackHole 2ch | ✅ (meeting audio coming in) |
   | AirPods / Built-in Microphone | ✅ (your voice) |

3. Rename it **"MeetScribe Input"**
4. In MeetScribe UI, select **"MeetScribe Input"** as the audio device

#### Set your meeting app output

In your meeting app, set the speaker/output to **"MeetScribe Output"**:

   | App | Where to change |
   |-----|----------------|
   | Zoom | Settings → Audio → Speaker |
   | Google Meet | Uses system default output |
   | Microsoft Teams | Settings → Devices → Speaker |
   | Slack / FaceTime | Uses system default output |

### Step 3 — Install Python Dependencies

```bash
cd "/Users/jamiljoseph/Documents/Code/Web Development/MeetScribe"
pip install -r requirements.txt
```

### Step 4 — Run MeetScribe

```bash
python3 app.py
```

Then open your browser to: **http://localhost:5001**

### Step 5 — Select BlackHole as the Input Device

In the MeetScribe UI, the **Audio Input Device** dropdown will list all available input devices. Select **BlackHole 2ch** (it's auto-selected if detected).

---

## Usage

1. **Select audio input device** — choose BlackHole 2ch from the dropdown
2. **Enter a meeting name** (e.g., "Team Standup - April 5")
3. **Click "Start Recording"** — MeetScribe captures audio from BlackHole
4. **Join your meeting** — audio is being captured in the background
5. **Click "Stop Recording"** — recording stops, transcription begins automatically
6. **View or download the transcript** — timestamps included

---

## Project Structure

```
MeetScribe/
├── app.py              # Flask backend (recording + transcription)
├── templates/
│   └── index.html      # Web UI
├── static/
│   └── style.css       # Dark theme
├── recordings/         # Raw .wav files (one folder per meeting)
├── transcripts/        # Generated .txt transcripts
├── recordings_index.json
└── requirements.txt
```

---

## Features

| Feature | Supported |
|---------|-----------|
| On-demand recording (not automatic) | ✅ |
| Dual stream capture (mic + system audio) | ✅ |
| Timestamped .txt transcript export | ✅ |
| AI meeting summary via Ollama (local) | ✅ |
| Audio device selector (mic + loopback) | ✅ |
| Per-meeting folder organization | ✅ |
| Delete recording + all files | ✅ |
| Light theme React UI | ✅ |
| Offline transcription (faster-whisper) | ✅ |
| Speaker diarization | ❌ (future) |

---

## Troubleshooting

**"No audio recorded" / transcript is empty**
→ Make sure your meeting app's audio output is set to the Multi-Output Device (not just your speakers). If you only hear audio through your speakers and not BlackHole, it won't be captured.

**Can't hear the meeting while recording**
→ You must use a Multi-Output Device (see Step 2). BlackHole alone mutes your speakers.

**Transcription is slow**
→ Normal on CPU. For Apple Silicon Macs, try: `pip install faster-whisper` and change `compute_type="int8"` to `compute_type="float16"` in `app.py`.

**Whisper model not found**
→ First run: faster-whisper will download the model automatically (~140MB for base model). Requires an internet connection on first launch.

**BlackHole not showing in device list**
→ Restart MeetScribe after installing BlackHole. If still missing, go to System Settings → Sound and confirm BlackHole appears there first.

---

## Windows Setup

The Windows edition has been fully rewritten and tested on Windows 10/11. No virtual audio cable required.

### What's different on Windows

| Component | macOS | Windows |
|-----------|-------|---------|
| System audio capture | BlackHole + Aggregate Device | WASAPI Stereo Mix (built-in) |
| Transcription engine | mlx-whisper (Apple Silicon) | faster-whisper (CPU, int8) |
| AI summary | — | Ollama (local LLM) |
| Frontend | Plain HTML | React + Vite |

### Requirements

- **Windows 10 or 11**
- **Python 3.10–3.12**
- **Node.js 18+** (for the React frontend build)
- **Ollama** installed and running (for AI meeting summaries)
- A mic and an audio output device (speakers, headset, etc.)

### Step 1 — Enable Stereo Mix

Stereo Mix is a Windows built-in feature that captures all system audio output (meeting audio, browser sounds, etc.) as a virtual input device. No extra software needed.

1. Right-click the speaker icon in your taskbar → **Sound settings**
2. Go to **Sound Control Panel** → **Recording** tab
3. Right-click in the empty area → check **Show Disabled Devices**
4. If **Stereo Mix** appears, right-click it → **Enable**
5. If Stereo Mix is missing, check your sound card drivers (Realtek HD Audio includes it by default)

### Step 2 — Install Python dependencies

```bash
cd meetscribe
pip install -r requirements.txt
```

`requirements.txt` includes: `flask`, `sounddevice`, `soundfile`, `numpy`, `librosa`, `faster-whisper`

### Step 3 — Build the frontend

Only needed once (or after UI changes):

```bash
cd frontend
npm install
npm run build
```

### Step 4 — Run MeetScribe

```bash
python app.py
```

Open your browser to: **http://localhost:5001**

### Step 5 — Select your devices in the UI

In the MeetScribe UI:

- **Mic Input** — select your microphone (or leave as default; "Microsoft Sound Mapper" uses your Windows default input)
- **Loopback / System Audio** — select **Stereo Mix** from the dropdown (captures meeting audio)

Both streams are recorded simultaneously and mixed before transcription.

### Step 6 — Install Ollama for AI summaries (optional but recommended)

1. Download Ollama from **https://ollama.com**
2. Pull the model:
   ```bash
   ollama pull minimax-m2.7:cloud
   ```
3. Ollama runs in the background automatically; MeetScribe will detect it and generate a summary after each recording

If Ollama is not running, the transcript is still saved — only the AI summary is skipped.

### How audio capture works on Windows

MeetScribe opens **two parallel audio streams**:

1. **Mic stream** — captures your voice from the selected microphone
2. **Loopback stream** — captures system audio (meeting participants) via Stereo Mix

Both streams are mixed (50/50) in Python using numpy, then saved as a single WAV file before transcription.

You do **not** need to change any settings in your meeting app (Zoom, Teams, Meet, etc.) — just use your normal speaker/headset output and let Stereo Mix capture it.

### Bluetooth headsets (AirPods, etc.)

- **For mic input:** Go to Windows **Settings → System → Sound → Input** and set your headset as the default input device. Then in MeetScribe leave Mic as "Microsoft Sound Mapper" — it will use your headset automatically.
- **For system audio capture:** Keep using Stereo Mix as the loopback device regardless of what headset you use.

### Troubleshooting (Windows)

**Stereo Mix not in device list**
→ Enable it in Control Panel → Sound → Recording (right-click → Show Disabled Devices). If missing entirely, update your audio driver from your PC/motherboard manufacturer's site.

**Transcription is slow**
→ Normal on CPU. The `base` Whisper model (~140MB) gives a good speed/accuracy balance. First run downloads the model automatically.

**Ollama summary not generating**
→ Make sure Ollama is running (`ollama serve` in a terminal, or it auto-starts after install). Check with: `curl http://localhost:11434/api/tags`

**"No audio recorded" after stopping**
→ Make sure you selected both a mic device and the Stereo Mix loopback in the UI before clicking Start.

---

## Project Structure (Windows edition)

```
meetscribe/
├── app.py                  # Flask backend — recording, transcription, Ollama summary
├── requirements.txt        # Python dependencies
├── recordings_index.json   # Per-meeting metadata
├── recordings/             # Raw .wav files (one folder per meeting)
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── components/
│   │       ├── Topbar.jsx
│   │       ├── Recorder.jsx
│   │       ├── RecordingsList.jsx
│   │       └── TranscriptModal.jsx
│   ├── dist/               # Built React app (served by Flask)
│   └── vite.config.js
└── transcription_errors.log
```

---

Built with ❤️ by CELESTIAL Coding Agent for Joseph.
