"""
MeetScribe - Local Meeting Recorder (Windows Edition)
Flask backend for audio recording and transcription using faster-whisper.

Windows audio setup:
  - System audio (meeting output) is captured via WASAPI Loopback device.
  - Microphone is captured from any standard input device.
  - Both streams are mixed together before transcription.

No virtual audio cable needed for system audio — Windows exposes loopback
devices natively through WASAPI (they show up as inputs named like
"Speakers (Loopback)" or "Stereo Mix").

KNOWN LIMITATION — Bluetooth output during calls:
  Loopback attaches to the default speaker at record start. Bluetooth
  headsets (AirPods etc.) expose TWO endpoints: a high-quality A2DP
  "Headphones" endpoint used for media, and a mono "Hands-Free" (HFP)
  endpoint used during calls. When a meeting needs your mic, Windows
  switches the headset into HFP mode and routes the meeting audio to the
  Hands-Free endpoint — but loopback is often still attached to the now-idle
  A2DP endpoint, so it records near-silence. (Root cause of the mostly-empty
  2026-07-01 "Meeting with the Hills" transcript.)
  Reliable workaround: send meeting AUDIO to laptop speakers or wired
  output while recording; the mic can be anything.

SAFEGUARD:
  The loopback worker tracks live RMS and flags Bluetooth output at start.
  /api/live_status returns a `warning` when the system-audio capture is dead
  (no stream), silent for 20s+, or attached to a Bluetooth endpoint, so a
  failed capture is caught DURING the meeting instead of the next morning.
"""

import os
import sys
import threading
import uuid
import json
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory
import sounddevice as sd
import soundfile as sf
import numpy as np

import librosa

import soundcard as sc

FRONTEND_DIST = Path(__file__).parent / 'frontend' / 'dist'

app = Flask(__name__, static_folder=None)
app.config['RECORDINGS_DIR'] = Path(__file__).parent / 'recordings'
app.config['TRANSCRIPTS_DIR'] = Path(__file__).parent / 'transcripts'

app.config['RECORDINGS_DIR'].mkdir(exist_ok=True)
app.config['TRANSCRIPTS_DIR'].mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Whisper model (loaded once, reused)
# ---------------------------------------------------------------------------
_whisper_model = None
_whisper_lock = threading.Lock()

def get_whisper_model():
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel
            print("[Whisper] Loading model (base, CPU, int8)...")
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            print("[Whisper] Model ready.")
    return _whisper_model

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class RecordingState:
    def __init__(self):
        self.is_recording = False
        self.is_transcribing = False
        self.current_meeting_name = None
        self.current_meeting_id = None
        self.current_meeting_dir = None

        # Mic queue + one loopback capture per output endpoint. We record EVERY
        # output device's loopback and mix them at stop time, so the meeting is
        # captured no matter which speaker/headset/dongle Windows routes it to.
        # (The old code guessed the single default speaker and missed the audio
        # whenever it played out of a different device — e.g. a USB headset
        # dongle while the default output was the built-in speakers.)
        self.mic_queue = []
        self.loopback_queue = []           # legacy/unused; kept so dead callbacks don't crash
        self.loopback_devices = []         # list of {"id","name","is_bluetooth","rms","queue":[]}
        self.sample_rate = 16000
        self.recording_thread = None

        # Live audio-health monitoring (so a dead/silent capture is caught
        # while it's still recording, not the next morning).
        self.loopback_rms = 0.0            # max recent RMS across all captured outputs, 0..1
        self.loopback_silent_seconds = 0.0  # consecutive seconds ALL outputs below the speech floor
        self.output_device_name = None      # human summary of the output device(s) being captured
        self.output_is_bluetooth = False    # True only if every captured output is Bluetooth/HFP

state = RecordingState()

# Loopback below this RMS (0..1 float scale) is treated as silence/dead air.
# Measured dead-air ≈ 0.0012, real speech ≈ 0.015–0.045, so 0.004 cleanly splits them.
LOOPBACK_SILENCE_RMS = 0.004
# Markers in an output device name that indicate a Bluetooth/hands-free endpoint,
# whose WASAPI loopback goes silent once Windows switches it into call (HFP) mode.
_BLUETOOTH_OUTPUT_MARKERS = ('bluetooth', 'hands-free', 'hands free', 'airpod', 'wireless')

# ---------------------------------------------------------------------------
# Audio device helpers
# ---------------------------------------------------------------------------
def list_input_devices():
    """
    Return all audio input devices, tagged with whether they are loopback.
    On Windows, WASAPI loopback devices appear as inputs and typically have
    'loopback' or 'stereo mix' in their name.
    """
    devices = []
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0:
            name = dev['name']
            name_lower = name.lower()
            is_loopback = (
                'loopback' in name_lower or
                'stereo mix' in name_lower or
                'what u hear' in name_lower or
                'wave out mix' in name_lower
            )
            devices.append({
                "index": i,
                "name": name,
                "is_loopback": is_loopback,
                "channels": dev['max_input_channels'],
            })
    return devices

# ---------------------------------------------------------------------------
# Audio callbacks (one per stream type)
# ---------------------------------------------------------------------------
def _mic_callback(indata, frames, time, status):
    if status:
        print(f"[Mic callback] {status}")
    if state.is_recording:
        # Mix to mono immediately
        chunk = indata.copy()
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1, keepdims=True)
        state.mic_queue.append(chunk)

def _loopback_callback(indata, frames, time, status):
    if status:
        print(f"[Loopback callback] {status}")
    if state.is_recording:
        chunk = indata.copy()
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1, keepdims=True)
        state.loopback_queue.append(chunk)

# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def start_recording_meeting(meeting_name: str, mic_device=None):
    """Start recording from mic + auto-detected WASAPI loopback (works with any output incl. Bluetooth)."""
    if state.is_recording:
        return False, "Already recording"

    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in meeting_name.strip())
    meeting_id = uuid.uuid4().hex[:8]
    meeting_dir = app.config['RECORDINGS_DIR'] / f"{safe_name}_{meeting_id}"
    meeting_dir.mkdir(parents=True, exist_ok=True)

    state.is_recording = True
    state.current_meeting_name = meeting_name
    state.current_meeting_id = meeting_id
    state.current_meeting_dir = meeting_dir
    state.mic_queue = []
    state.loopback_queue = []
    state.loopback_devices = []
    state.sample_rate = 16000
    state.loopback_rms = 0.0
    state.loopback_silent_seconds = 0.0
    state.output_device_name = None
    state.output_is_bluetooth = False

    def record_loop():
        sd_streams = []
        loopback_threads = []
        try:
            # Mic stream (sounddevice)
            if mic_device is not None:
                try:
                    dev_info = sd.query_devices(mic_device)
                    ch = max(1, min(dev_info['max_input_channels'], 2))
                    mic_stream = sd.InputStream(
                        device=mic_device,
                        samplerate=state.sample_rate,
                        channels=ch,
                        dtype='float32',
                        callback=_mic_callback,
                    )
                    mic_stream.start()
                    sd_streams.append(mic_stream)
                    print(f"[Record] Mic stream started: device={mic_device}")
                except Exception as e:
                    print(f"[Record] Mic stream failed: {e}")

            if not sd_streams:
                print("[Record] No valid mic device — using default input")
                fallback = sd.InputStream(
                    samplerate=state.sample_rate,
                    channels=1,
                    dtype='float32',
                    callback=_mic_callback,
                )
                fallback.start()
                sd_streams.append(fallback)

            # Loopback via soundcard — opens output devices directly in WASAPI
            # loopback mode (works for any device incl. Bluetooth/USB dongles, no
            # separate loopback input needed, unlike pyaudiowpatch/Stereo Mix).
            #
            # We capture EVERY output endpoint concurrently and mix them at stop
            # time. This is the fix for the "audio played out of a different
            # device than the default speaker" failure: instead of guessing which
            # single device carries the meeting, we record them all — an idle
            # endpoint just contributes silence, the live one carries the meeting.
            try:
                speakers = sc.all_speakers()
            except Exception as e:
                print(f"[Record] Could not enumerate speakers: {e}")
                speakers = []
            if not speakers:
                try:
                    speakers = [sc.default_speaker()]
                except Exception as e:
                    print(f"[Record] No output device available for loopback: {e}")
                    speakers = []

            # Register each endpoint up front so live_status/stop see them even if
            # a worker is slow to produce its first chunk.
            for spk in speakers:
                is_bt = any(m in spk.name.lower() for m in _BLUETOOTH_OUTPUT_MARKERS)
                state.loopback_devices.append(
                    {"id": spk.id, "name": spk.name, "is_bluetooth": is_bt, "rms": 0.0, "queue": []}
                )
            state.output_device_name = ", ".join(d["name"] for d in state.loopback_devices) or None
            state.output_is_bluetooth = bool(state.loopback_devices) and all(
                d["is_bluetooth"] for d in state.loopback_devices
            )
            print(f"[Record] Capturing loopback from {len(state.loopback_devices)} output(s): "
                  f"{state.output_device_name}")

            def loopback_worker(dev):
                try:
                    lb_mic = sc.get_microphone(dev["id"], include_loopback=True)
                    chunk_size = int(state.sample_rate * 0.1)
                    with lb_mic.recorder(samplerate=state.sample_rate, channels=1, blocksize=chunk_size) as rec:
                        while state.is_recording:
                            data = rec.record(numframes=chunk_size)
                            if state.is_recording:
                                chunk = data.copy().astype(np.float32)
                                dev["queue"].append(chunk)
                                dev["rms"] = float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0
                except Exception as e:
                    print(f"[Record] Loopback failed for '{dev['name']}': {e}")

            loopback_threads = []
            for dev in state.loopback_devices:
                t = threading.Thread(target=loopback_worker, args=(dev,), daemon=True)
                t.start()
                loopback_threads.append(t)

            # Central health tracker: live RMS = loudest endpoint; silence only
            # counts when EVERY endpoint is below the speech floor.
            tick = 0.2
            while state.is_recording:
                sd.sleep(int(tick * 1000))
                agg_rms = max((d["rms"] for d in state.loopback_devices), default=0.0)
                state.loopback_rms = agg_rms
                if state.loopback_devices:
                    if agg_rms < LOOPBACK_SILENCE_RMS:
                        state.loopback_silent_seconds += tick
                    else:
                        state.loopback_silent_seconds = 0.0

        except Exception as e:
            print(f"[Record] Unexpected error: {e}")
        finally:
            for s in sd_streams:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass
            for t in loopback_threads:
                t.join(timeout=2)

    state.recording_thread = threading.Thread(target=record_loop, daemon=True)
    state.recording_thread.start()
    return True, f"Recording started: {meeting_name}"


def _active_ratio(audio, sr, thr=LOOPBACK_SILENCE_RMS, win_s=0.5):
    """Fraction of 0.5s windows whose RMS is above the speech floor.

    Robust to sparse loud artifacts (a whole-file RMS would be inflated by a few
    loud blips); this measures how much of the recording actually carried audio.
    """
    if audio is None or len(audio) == 0:
        return 0.0
    win = max(1, int(sr * win_s))
    n = len(audio) // win
    if n == 0:
        return 1.0 if float(np.sqrt(np.mean(np.square(audio)))) >= thr else 0.0
    trimmed = audio[:n * win].reshape(n, win)
    rms = np.sqrt(np.mean(np.square(trimmed), axis=1))
    return float(np.mean(rms >= thr))


def _classify_system_audio(lb_audio, lb_ratio, mic_ratio):
    """Decide whether the meeting/system audio was actually captured.

    'missing' — loopback never produced samples, or was silent almost the whole
                time (the Bluetooth-HFP failure). 'low' — mostly silent while the
                mic clearly worked (system audio dropped but mic didn't). 'ok'.
    """
    if lb_audio is None or len(lb_audio) == 0 or lb_ratio < 0.02:
        return "missing"
    if lb_ratio < 0.15 and mic_ratio > (lb_ratio * 2 + 0.05):
        return "low"
    return "ok"


def stop_recording_meeting():
    """Stop recording, mix mic + loopback, and save a single WAV file."""
    if not state.is_recording:
        return None

    state.is_recording = False
    if state.recording_thread:
        state.recording_thread.join(timeout=3)

    mic_chunks = state.mic_queue
    have_lb = any(d["queue"] for d in state.loopback_devices)

    if not mic_chunks and not have_lb:
        return None

    sr = state.sample_rate

    def concat(chunks):
        if not chunks:
            return None
        data = np.concatenate(chunks, axis=0)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data.astype(np.float32)

    def merge_loopback(devices):
        """Sum every captured output endpoint into one track. Idle endpoints are
        silence and contribute nothing; the live one carries the meeting. Padded
        to the longest so a device that started/stopped early still lines up."""
        tracks = [t for t in (concat(d["queue"]) for d in devices) if t is not None and len(t)]
        if not tracks:
            return None
        max_len = max(len(t) for t in tracks)
        acc = np.zeros(max_len, dtype=np.float32)
        for t in tracks:
            acc[:len(t)] += t
        return acc

    mic_audio = concat(mic_chunks)
    lb_audio = merge_loopback(state.loopback_devices)

    if mic_audio is not None and lb_audio is not None:
        # Pad shorter array to match longer one
        max_len = max(len(mic_audio), len(lb_audio))
        mic_audio = np.pad(mic_audio, (0, max_len - len(mic_audio)))
        lb_audio  = np.pad(lb_audio,  (0, max_len - len(lb_audio)))
        # Mix at equal levels; clamp to [-1, 1]
        mixed = np.clip(mic_audio * 0.5 + lb_audio * 0.5, -1.0, 1.0)
        print(f"[Stop] Mixed mic+loopback: {len(mixed)/sr:.1f}s")
    elif mic_audio is not None:
        mixed = mic_audio
        print(f"[Stop] Mic only: {len(mixed)/sr:.1f}s")
    else:
        mixed = np.clip(lb_audio, -1.0, 1.0)
        print(f"[Stop] Loopback only: {len(lb_audio)/sr:.1f}s")

    audio_path = state.current_meeting_dir / "recording.wav"
    sf.write(str(audio_path), mixed, sr)

    # Assess whether the meeting/system audio was actually captured, so a dead
    # loopback (e.g. Bluetooth output during a call) is flagged instead of
    # silently producing a hallucinated transcript + summary.
    try:
        lb_ratio = _active_ratio(lb_audio, sr)
        mic_ratio = _active_ratio(mic_audio, sr)
        system_audio = _classify_system_audio(lb_audio, lb_ratio, mic_ratio)
    except Exception as e:
        print(f"[Stop] Audio-health check failed: {e}")
        lb_ratio, mic_ratio, system_audio = None, None, "unknown"
    print(f"[Stop] system_audio={system_audio} (loopback active {lb_ratio}, mic active {mic_ratio}, "
          f"output='{state.output_device_name}', bluetooth={state.output_is_bluetooth})")

    meeting_info = {
        "id": state.current_meeting_id,
        "name": state.current_meeting_name,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "duration": round(len(mixed) / sr, 1),
        "audio_file": str(audio_path),
        "transcript_file": None,
        "status": "recorded",
        "system_audio": system_audio,
        "output_device": state.output_device_name,
        "output_is_bluetooth": state.output_is_bluetooth,
    }

    state.mic_queue = []
    state.loopback_queue = []
    state.loopback_devices = []
    return meeting_info

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
def _preprocess_audio(audio_path: str) -> str:
    """Resample to 16kHz mono and normalize. Overwrites the file in place."""
    print(f"[Preprocess] Loading {audio_path}...")
    audio, sr = librosa.load(str(audio_path), sr=16000, mono=True)

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (0.891 / peak)
        print(f"[Preprocess] Normalized (peak {peak:.4f} -> {np.max(np.abs(audio)):.4f})")

    sf.write(str(audio_path), audio, 16000)
    print(f"[Preprocess] Saved {len(audio)/16000:.1f}s @ 16kHz mono")
    return str(audio_path)


def _build_summary_prompt(transcript: str, meeting_name: str) -> str:
    return (
        f"You are a meeting assistant. Carefully read the full transcript below and write a detailed summary for the meeting '{meeting_name}'.\n\n"
        "Your summary must include:\n"
        "## Overview\n"
        "2-3 sentences covering the overall purpose and outcome of the meeting.\n\n"
        "## Key Topics Discussed\n"
        "For each major topic, write 2-4 sentences explaining what was discussed, any context given, and any conclusions reached. Be specific — include names, systems, numbers, and details mentioned.\n\n"
        "## Action Items\n"
        "List each action item with who is responsible (if mentioned) and any deadlines stated.\n\n"
        "## Decisions Made\n"
        "List each decision clearly, including the reasoning behind it if explained in the meeting.\n\n"
        "Be thorough. Do not skip topics. If something was discussed at length, reflect that in your summary.\n\n"
        f"Transcript:\n{transcript[:100000]}\n\nSummary:"
    )


def _generate_summary_claude(transcript: str, meeting_name: str):
    """Call Claude Code CLI to summarize. Returns None if unavailable."""
    import subprocess as _sp
    prompt = _build_summary_prompt(transcript, meeting_name)
    try:
        result = _sp.run(
            ["claude", "-p"],
            input=prompt, capture_output=True, text=True, timeout=120
        )
        return result.stdout.strip() or None
    except Exception as e:
        print(f"[Summary] Claude CLI unavailable: {e}")
        return None


def _generate_summary_ollama(transcript: str, meeting_name: str):
    """Fallback: call local Ollama to summarize. Returns None if unavailable."""
    import urllib.request as _urlreq
    import json as _json

    prompt = _build_summary_prompt(transcript, meeting_name)
    payload = _json.dumps({
        "model": "llama3.1:8b",
        "prompt": prompt,
        "stream": False
    }).encode()

    req = _urlreq.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with _urlreq.urlopen(req, timeout=180) as resp:
            data = _json.loads(resp.read())
            return data.get("response", "").strip() or None
    except Exception as e:
        print(f"[Summary] Ollama unavailable: {e}")
        return None


def _do_transcribe(audio_path: str, meeting_id: str, meeting_name: str):
    """Core transcription logic using faster-whisper."""
    _preprocess_audio(audio_path)

    model = get_whisper_model()
    print(f"[Transcribe] Running faster-whisper on {audio_path}...")
    segments_gen, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,      # skip silent regions
        vad_parameters={"min_silence_duration_ms": 500},
    )

    detected_language = info.language
    print(f"[Transcribe] Detected language: {detected_language} ({info.language_probability:.0%})")

    transcript_lines = []
    prev_text = None
    for segment in segments_gen:
        text = segment.text.strip()
        if not text or text == prev_text:
            continue
        start_hms = seconds_to_hms(segment.start)
        transcript_lines.append(f"[{start_hms}] Speaker: {text}")
        prev_text = text

    meeting_dir = Path(audio_path).parent
    transcript_path = meeting_dir / "transcript.txt"
    full_transcript = "\n".join(transcript_lines)

    # Pull the recording's captured health + duration to decide whether the
    # transcript is trustworthy or the meeting audio was lost.
    entry = next((e for e in load_recordings_index() if e.get("id") == meeting_id), {})
    system_audio = entry.get("system_audio", "unknown")
    duration_min = float(entry.get("duration", 0) or 0) / 60.0
    density = len(full_transcript) / max(duration_min, 0.1)  # transcript chars per minute
    # A multi-minute meeting that yielded almost no text means the audio was
    # near-silent — Whisper then hallucinates fragments on silence.
    sparse = duration_min >= 3 and density < 120
    audio_lost = system_audio in ("missing", "low") or sparse

    if audio_lost:
        out = state.output_device_name or entry.get("output_device")
        bt = state.output_is_bluetooth or entry.get("output_is_bluetooth")
        reason = "on Bluetooth output, which usually isn't captured during a call" if bt \
            else "— the meeting/system audio wasn't captured"
        banner = (
            "⚠️ SYSTEM AUDIO NOT CAPTURED — this transcript is unreliable.\n"
            f"Little or no meeting audio was recorded {reason}"
            + (f" (output: {out})" if out else "") + ".\n"
            "The lines below are sparse and may be Whisper hallucinating on silence.\n"
            "Fix for next time: set your meeting AUDIO output to laptop speakers or wired headphones\n"
            "(your microphone can stay on Bluetooth).\n"
            + ("=" * 70) + "\n\n"
        )
        full_transcript = banner + full_transcript

    transcript_path.write_text(full_transcript, encoding="utf-8")
    print(f"[Transcribe] Transcript saved ({len(full_transcript)} chars, system_audio={system_audio}, "
          f"density={density:.0f}/min, audio_lost={audio_lost})")

    update_recording_index(
        meeting_id, transcript_path=str(transcript_path),
        status="transcribed", audio_lost=audio_lost,
    )
    print(f"[Transcribe] Updated index for {meeting_id}")

    summary_path = meeting_dir / "summary.txt"
    header = (
        f"Meeting: {meeting_name}\n"
        f"Language: {detected_language}\n\n"
    )

    if audio_lost:
        # Don't ask the LLM to summarize silence — it just invents a meeting.
        out = state.output_device_name or entry.get("output_device")
        print(f"[Summary] Skipping AI summary for {meeting_id}: system audio not captured.")
        summary_content = header + (
            "=== ⚠️ No usable audio ===\n"
            "The meeting/system audio was not captured, so no summary was generated.\n"
            f"Output device at record time: {out or 'unknown'}.\n\n"
            "This is almost always caused by Bluetooth headphones: during a call Windows\n"
            "switches them into hands-free mode and the meeting audio stops being captured.\n"
            "To record reliably, send meeting audio to laptop speakers or wired headphones\n"
            "(your microphone can stay on Bluetooth)."
        )
        summary_path.write_text(summary_content, encoding="utf-8")
        print(f"[Transcribe] Done for {meeting_id} (flagged: audio not captured)")
        return

    print(f"[Summary] Requesting Claude summary for {meeting_id}...")
    ai_summary = _generate_summary_claude(full_transcript, meeting_name)
    if ai_summary:
        print(f"[Summary] Claude summary generated ({len(ai_summary)} chars)")
    else:
        print(f"[Summary] Claude unavailable, falling back to Ollama...")
        ai_summary = _generate_summary_ollama(full_transcript, meeting_name)
        if ai_summary:
            print(f"[Summary] Ollama summary generated ({len(ai_summary)} chars)")

    if ai_summary:
        summary_content = header + f"=== AI Summary ===\n{ai_summary}"
    else:
        summary_content = header + "[Summary unavailable — start Ollama with: ollama serve]"
    summary_path.write_text(summary_content, encoding="utf-8")

    print(f"[Transcribe] Done for {meeting_id}")


def transcribe_audio(audio_path: str, meeting_id: str, meeting_name: str):
    """Run transcription in a background thread."""
    state.is_transcribing = True
    print(f"[Transcribe] Starting for {meeting_id}...")

    error_occurred = False
    error_msg = None
    try:
        _do_transcribe(audio_path, meeting_id, meeting_name)
    except Exception as e:
        error_occurred = True
        error_msg = f"[Transcription error] {e}\n{traceback.format_exc()}"
        print(error_msg)
        log_path = Path(__file__).parent / "transcription_errors.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- Error at {datetime.now().isoformat()} ---\n")
            f.write(error_msg)
        update_recording_index(meeting_id, status="error")
    finally:
        state.is_transcribing = False
        status = f"Error: {error_msg}" if error_occurred else "Success"
        print(f"[Transcribe] Thread done for {meeting_id}. {status}")


def seconds_to_hms(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# ---------------------------------------------------------------------------
# Recording index (JSON file-based)
# ---------------------------------------------------------------------------
INDEX_FILE = Path(__file__).parent / "recordings_index.json"

def load_recordings_index() -> list:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_recordings_index(index: list):
    INDEX_FILE.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

def update_recording_index(meeting_id: str, **kwargs):
    index = load_recordings_index()
    for entry in index:
        if entry.get("id") == meeting_id:
            entry.update(kwargs)
            break
    save_recordings_index(index)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    # Serve React build; API routes are matched before this catch-all
    if path and (FRONTEND_DIST / path).is_file():
        return send_from_directory(FRONTEND_DIST, path)
    index = FRONTEND_DIST / 'index.html'
    if index.exists():
        return send_file(index)
    return '<h2>Run <code>npm run build</code> inside the <code>frontend/</code> folder first.</h2>', 503

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.get_json() or {}
    meeting_name = data.get('meeting_name', '').strip()
    if not meeting_name:
        return jsonify({"success": False, "error": "Meeting name is required"}), 400

    if state.is_recording:
        return jsonify({"success": False, "error": "Already recording"}), 409

    def parse_device(val):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    mic_device = parse_device(data.get('mic_device'))

    # Pre-flight: we capture every output endpoint, so device choice no longer
    # matters — but if EVERY available output is Bluetooth, warn, since Bluetooth
    # audio can still drop out mid-call regardless of which one we record.
    output_device, output_is_bluetooth, preflight_warning = None, False, None
    try:
        speakers = sc.all_speakers()
        output_device = ", ".join(s.name for s in speakers) or None
        output_is_bluetooth = bool(speakers) and all(
            any(m in s.name.lower() for m in _BLUETOOTH_OUTPUT_MARKERS) for s in speakers
        )
        if output_is_bluetooth:
            preflight_warning = (
                f"Your only audio output(s) — {output_device} — look like Bluetooth. Bluetooth "
                "audio can drop out during a call; a wired or USB output is more reliable for recording."
            )
    except Exception as e:
        print(f"[Start] Output pre-flight check failed: {e}")

    success, msg = start_recording_meeting(meeting_name, mic_device=mic_device)
    return jsonify({
        "success": success,
        "message": msg,
        "output_device": output_device,
        "output_is_bluetooth": output_is_bluetooth,
        "warning": preflight_warning,
    })

@app.route('/api/stop', methods=['POST'])
def api_stop():
    if not state.is_recording:
        return jsonify({"success": False, "error": "Not recording"}), 400

    meeting_info = stop_recording_meeting()
    if meeting_info is None:
        return jsonify({"success": False, "error": "No audio recorded"}), 400

    index = load_recordings_index()
    index.insert(0, meeting_info)
    save_recordings_index(index)

    threading.Thread(
        target=transcribe_audio,
        args=(meeting_info["audio_file"], meeting_info["id"], meeting_info["name"]),
        daemon=True
    ).start()

    return jsonify({"success": True, "meeting": meeting_info})

@app.route('/api/recordings', methods=['GET'])
def api_recordings():
    return jsonify(load_recordings_index())

@app.route('/api/delete', methods=['POST'])
def api_delete():
    data = request.get_json() or {}
    meeting_id = data.get('id')
    if not meeting_id:
        return jsonify({"success": False, "error": "Missing meeting id"}), 400

    index = load_recordings_index()
    entry_to_delete = next((e for e in index if e.get("id") == meeting_id), None)

    if entry_to_delete is None:
        return jsonify({"success": False, "error": "Meeting not found"}), 404

    meeting_dir = Path(entry_to_delete["audio_file"]).parent
    if meeting_dir.exists():
        import shutil
        shutil.rmtree(meeting_dir)

    index = [e for e in index if e.get("id") != meeting_id]
    save_recordings_index(index)
    return jsonify({"success": True})

@app.route('/api/transcript/<meeting_id>', methods=['GET'])
def api_transcript(meeting_id):
    index = load_recordings_index()
    for entry in index:
        if entry.get("id") == meeting_id:
            transcript_path = entry.get("transcript_file") or entry.get("transcript_path")
            if transcript_path and Path(transcript_path).exists():
                content = Path(transcript_path).read_text(encoding="utf-8")
                return jsonify({"success": True, "content": content})
            return jsonify({"success": False, "error": "Transcript not ready"}), 404
    return jsonify({"success": False, "error": "Meeting not found"}), 404

@app.route('/api/summary/<meeting_id>', methods=['GET'])
def api_summary(meeting_id):
    index = load_recordings_index()
    for entry in index:
        if entry.get("id") == meeting_id:
            audio_file = entry.get("audio_file")
            if audio_file:
                summary_path = Path(audio_file).parent / "summary.txt"
                if summary_path.exists():
                    content = summary_path.read_text(encoding="utf-8")
                    return jsonify({"success": True, "content": content})
            return jsonify({"success": False, "error": "Summary not ready"}), 404
    return jsonify({"success": False, "error": "Meeting not found"}), 404

@app.route('/api/status', methods=['GET'])
def api_status():
    if state.is_recording:
        status = "recording"
    elif state.is_transcribing:
        status = "transcribing"
    else:
        status = "idle"
    return jsonify({"status": status})

@app.route('/api/devices', methods=['GET'])
def api_devices():
    try:
        devices = list_input_devices()
        return jsonify({"success": True, "devices": devices})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/live_status', methods=['GET'])
def api_live_status():
    if not state.is_recording:
        return jsonify({"is_recording": False, "duration": 0.0, "chunks": 0})
    mic_samples = sum(c.shape[0] for c in state.mic_queue) if state.mic_queue else 0
    lb_chunks_total = sum(len(d["queue"]) for d in state.loopback_devices)
    lb_samples = sum(c.shape[0] for d in state.loopback_devices for c in d["queue"])
    total_samples = max(mic_samples, lb_samples)
    duration = round(total_samples / state.sample_rate, 1)

    # Flag a dead/silent system-audio capture in real time. Priority: no stream at
    # all → sustained silence → Bluetooth heads-up. Give the loopback a few seconds
    # to spin up before complaining about silence. Because we now capture every
    # output endpoint, "silent" means the meeting audio isn't reaching ANY of them.
    warning = None
    if duration >= 20 and lb_samples == 0:
        warning = ("No system-audio stream — loopback capture failed to start. "
                   "The meeting audio is NOT being recorded.")
    elif state.loopback_silent_seconds >= 20:
        warning = (f"No system audio detected on any output for {int(state.loopback_silent_seconds)}s. "
                   "The meeting audio may not be captured — check that the call's audio is actually "
                   "playing, and unmute the other participants if needed.")
    elif state.output_is_bluetooth:
        warning = (f"All outputs ({state.output_device_name}) look like Bluetooth. "
                   "Bluetooth audio can drop out during a call — a wired/USB output is more reliable.")

    return jsonify({
        "is_recording": True,
        "duration": duration,
        "chunks": len(state.mic_queue) + lb_chunks_total,
        "mic_chunks": len(state.mic_queue),
        "loopback_chunks": lb_chunks_total,
        "loopback_rms": round(state.loopback_rms, 4),
        "loopback_silent_seconds": round(state.loopback_silent_seconds, 1),
        "output_device": state.output_device_name,
        "warning": warning,
    })


# ---------------------------------------------------------------------------
# Remote browser capture (Mode B) — see remote_capture.py
#
# Registered last so every helper it needs is already defined. Purely additive:
# it adds /api/remote/* routes and touches nothing in the local record path.
# ---------------------------------------------------------------------------
try:
    from remote_capture import register_remote_capture

    register_remote_capture(
        app,
        recordings_dir=app.config['RECORDINGS_DIR'],
        active_ratio=_active_ratio,
        classify_system_audio=_classify_system_audio,
        load_index=load_recordings_index,
        save_index=save_recordings_index,
        transcribe_audio=transcribe_audio,
        state=state,
    )
except Exception as _e:
    # A failure here must never stop the local recorder from starting.
    print(f"[Remote] Browser-capture routes unavailable: {_e}")


def _start_https_listener(port=5443):
    """Serve the same app over HTTPS in a background thread.

    Browsers only expose getUserMedia/getDisplayMedia in a secure context, so
    remote capture from another laptop cannot work over plain http://<lan-ip>.
    The existing HTTP listener on 5001 is left exactly as it was; this is an
    additional door, not a replacement.
    """
    cert_dir = Path(__file__).parent / "certs"
    cert, key = cert_dir / "cert.pem", cert_dir / "key.pem"
    if not (cert.exists() and key.exists()):
        print("[HTTPS] No certificate found — run `python make_cert.py` to enable remote capture.")
        return
    try:
        import ssl
        from werkzeug.serving import make_server

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        server = make_server('0.0.0.0', port, app, ssl_context=ctx, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"[HTTPS] Secure listener on https://0.0.0.0:{port} (for remote browser capture)")
    except Exception as e:
        print(f"[HTTPS] Could not start secure listener: {e}")

if __name__ == '__main__':
    print("Starting MeetScribe (Windows)...")
    print(f"Recordings dir: {app.config['RECORDINGS_DIR']}")
    print(f"Transcripts dir: {app.config['TRANSCRIPTS_DIR']}")
    # Pre-load Whisper model in background so first transcription is fast
    threading.Thread(target=get_whisper_model, daemon=True).start()
    _start_https_listener()
    app.run(host='0.0.0.0', port=5001, debug=False)
