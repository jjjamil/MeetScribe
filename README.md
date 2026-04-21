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
| Timestamped .txt transcript export | ✅ |
| Audio input device selector | ✅ |
| Per-meeting folder organization | ✅ |
| Delete recording + all files | ✅ |
| Dark theme UI | ✅ |
| Offline transcription (Whisper) | ✅ |
| Speaker diarization | ❌ (future) |
| Summary generation | ❌ (future) |

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

1. Install **VB-CABLE** from https://www.vb-audio.com/Cable/
2. Set your meeting app output to **CABLE Input (VB-Audio Virtual Cable)**
3. In MeetScribe, select **CABLE Output** as the audio input device
4. Run: `pip install -r requirements.txt` then `python app.py`

---

Built with ❤️ by CELESTIAL Coding Agent for Joseph.
