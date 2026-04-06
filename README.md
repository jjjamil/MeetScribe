# MeetScribe

**Local meeting recorder with Whisper transcription — no cloud, no subscriptions.**

Records audio from your computer (meeting apps like Zoom, Google Meet, Teams, Facebook Call all route through a virtual audio cable), transcribes it locally using Whisper, and exports timestamped .txt transcripts.

---

## Requirements

- **Windows 10/11**
- **Python 3.10 or 3.11**
- **VB-Audio Virtual Cable** (free) — routes meeting audio to MeetScribe
- **8GB+ RAM** recommended (16GB for smooth Whisper CPU transcription)

---

## Setup

### Step 1 — Install a Virtual Audio Cable

VB-CABLE requires a donation to download. Two free alternatives:

**Option A — Voicemeeter Banana (Recommended, Free)**
1. Download from: https://www.vb-audio.com/Voicemeeter Banana
2. Install and run Voicemeeter Banana
3. In your meeting app, set output to **VB-Audio VoiceMeeter VAIO**
4. In MeetScribe, select **VoiceMeeter Input** as the recording device

**Option B — OBS Studio (Completely Free)**
1. Download: https://obsproject.com
2. Use OBS Virtual Camera as a virtual output
3. Route meeting audio through OBS

**Option C — VB-CABLE (Donationware)**
1. Go to https://www.vb-audio.com/Cable/VirtualCables.htm
2. Click Donate to get your personal download link
3. Run the installer, restart computer
4. Set meeting app output to **CABLE Input**

### Step 2 — Route Meeting Audio to the Virtual Cable

**Zoom:**
- Settings → Audio → Speaker → Select **CABLE Input (VB-Audio Virtual Cable)**

**Google Meet:**
- Uses your system default output. Set system default:
  - Right-click speaker icon → Open Sound Settings
  - Output device → **CABLE Input (VB-Audio Virtual Cable)**

**Microsoft Teams:**
- Settings → Devices → Speaker → **CABLE Input (VB-Audio Virtual Cable)**

**Facebook Call:**
- Uses system default output (set as above)

### Step 3 — Install Python Dependencies

```bash
cd C:\Users\Joseph\CodingAgent\MeetScribe
pip install -r requirements.txt
```

### Step 4 — Run MeetScribe

```bash
python app.py
```

Then open your browser to: **[http://localhost:5000](http://localhost:5000)**

---

## Usage

1. **Enter a meeting name** (e.g., "Team Standup - April 5")
2. **Click "Start Recording"** — the app captures audio from the virtual cable
3. **Join your meeting** — audio is being captured in the background
4. **Click "Stop Recording"** — recording stops, transcription begins automatically
5. **View or download the transcript** — timestamps included

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
| Per-meeting folder organization | ✅ |
| Delete recording + all files | ✅ |
| Dark theme UI | ✅ |
| Offline transcription (Whisper) | ✅ |
| Speaker diarization | ❌ (future) |
| Summary generation | ❌ (future) |

---

## Troubleshooting

**"No audio recorded"**
→ Make sure your meeting app's audio output is set to VB-Cable, not your speakers. If you hear audio, it won't be captured.

**Transcription is slow**
→ Use GPU transcription: change `device="cuda"` in `app.py`. Requires CUDA + NVIDIA GPU.

**Whisper model not found**
→ First run: faster-whisper will download the model automatically (~140MB for base model).

---

Built with ❤️ by CELESTIAL Coding Agent for Joseph.
