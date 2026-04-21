"""
MeetScribe - Local Meeting Recorder
Flask backend for audio recording and transcription using Whisper.
"""

import os
import sys
import threading
import uuid
import json
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify, request, send_file
import sounddevice as sd
import soundfile as sf
import numpy as np

# Transcription + audio preprocessing
import mlx_whisper
import librosa

app = Flask(__name__)
app.config['RECORDINGS_DIR'] = Path(__file__).parent / 'recordings'
app.config['TRANSCRIPTS_DIR'] = Path(__file__).parent / 'transcripts'

# Ensure dirs exist
app.config['RECORDINGS_DIR'].mkdir(exist_ok=True)
app.config['TRANSCRIPTS_DIR'].mkdir(exist_ok=True)

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
        self.audio_queue = []
        self.stream = None
        self.sample_rate = 16000
        self.channels = 1
        self.recording_thread = None

state = RecordingState()

# ---------------------------------------------------------------------------
# Audio device helpers
# ---------------------------------------------------------------------------
def list_input_devices():
    """Return a list of available audio input devices."""
    devices = []
    for i, dev in enumerate(sd.query_devices()):
        if dev['max_input_channels'] > 0:
            devices.append({"index": i, "name": dev['name']})
    return devices

# mlx-whisper model repo (Apple Silicon optimized, large-v3)
MLX_MODEL = "mlx-community/whisper-large-v3-mlx"

# ---------------------------------------------------------------------------
# Audio recording
# ---------------------------------------------------------------------------
def audio_callback(indata, frames, time, status):
    """Callback from sounddevice stream — appends audio chunk to queue."""
    if status:
        print(f"[Audio callback status] {status}")
    if state.is_recording:
        state.audio_queue.append(indata.copy())

def start_recording_meeting(meeting_name: str, device=None):
    """Start recording audio to a per-meeting folder."""
    if state.is_recording:
        return False, "Already recording"

    # Sanitize folder name and create directory
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in meeting_name.strip())
    meeting_id = uuid.uuid4().hex[:8]
    meeting_dir = app.config['RECORDINGS_DIR'] / f"{safe_name}_{meeting_id}"
    meeting_dir.mkdir(parents=True, exist_ok=True)

    # Detect channel count — multi-channel for Aggregate Devices (mic + BlackHole)
    if device is not None:
        try:
            dev_info = sd.query_devices(device)
            n_channels = max(1, min(dev_info['max_input_channels'], 8))
        except Exception:
            n_channels = 1
    else:
        n_channels = 1

    state.is_recording = True
    state.current_meeting_name = meeting_name
    state.current_meeting_id = meeting_id
    state.current_meeting_dir = meeting_dir
    state.audio_queue = []
    state.sample_rate = 16000
    state.channels = n_channels

    def record_loop():
        try:
            stream_kwargs = dict(
                samplerate=state.sample_rate,
                channels=n_channels,
                dtype='float32',
                callback=audio_callback,
            )
            if device is not None:
                stream_kwargs['device'] = device
            with sd.InputStream(**stream_kwargs):
                while state.is_recording:
                    sd.sleep(100)
        except Exception as e:
            print(f"[Recording error] {e}")

    state.recording_thread = threading.Thread(target=record_loop, daemon=True)
    state.recording_thread.start()
    return True, f"Recording started: {meeting_name}"

def stop_recording_meeting():
    """Stop recording and save audio file."""
    if not state.is_recording:
        return None

    state.is_recording = False
    if state.recording_thread:
        state.recording_thread.join(timeout=2)

    if not state.audio_queue:
        return None

    # Concatenate all audio chunks and mix to mono
    audio_data = np.concatenate(state.audio_queue, axis=0)
    if audio_data.ndim > 1 and audio_data.shape[1] > 1:
        audio_data = audio_data.mean(axis=1)
    audio_path = state.current_meeting_dir / "recording.wav"
    sf.write(str(audio_path), audio_data, state.sample_rate)

    meeting_info = {
        "id": state.current_meeting_id,
        "name": state.current_meeting_name,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "duration": round(len(audio_data) / state.sample_rate, 1),
        "audio_file": str(audio_path),
        "transcript_file": None,
        "status": "recorded"
    }

    state.audio_queue = []
    return meeting_info

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------  
def _preprocess_audio(audio_path: str) -> str:
    """Resample to 16kHz mono and normalize. Overwrites the file in place."""
    print(f"[Preprocess] Loading {audio_path}...")
    audio, sr = librosa.load(str(audio_path), sr=16000, mono=True)

    # Normalize to -1dB headroom
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (0.891 / peak)  # 0.891 ≈ -1dBFS
        print(f"[Preprocess] Normalized (peak {peak:.4f} -> {np.max(np.abs(audio)):.4f})")

    sf.write(str(audio_path), audio, 16000)
    print(f"[Preprocess] Saved preprocessed audio ({len(audio)/16000:.1f}s @ 16kHz mono)")
    return str(audio_path)


def _generate_summary_ollama(transcript: str, meeting_name: str) -> str | None:
    """Call local Ollama to summarize the transcript. Returns None if unavailable."""
    import urllib.request as _urlreq
    import json as _json

    prompt = (
        f"You are a meeting assistant. Summarize the following meeting transcript for '{meeting_name}'.\n"
        "Provide:\n"
        "- A brief overview (2-3 sentences)\n"
        "- Key topics discussed\n"
        "- Action items (if any)\n"
        "- Decisions made (if any)\n\n"
        f"Transcript:\n{transcript[:8000]}\n\nSummary:"
    )

    payload = _json.dumps({
        "model": "minimax-m2.7",
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
    """Core transcription logic — raises on error."""
    # Preprocess: resample to 16kHz mono + normalize
    _preprocess_audio(audio_path)

    print(f"[Transcribe] Running mlx-whisper large-v3 on {audio_path}...")
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=MLX_MODEL,
        verbose=False,
    )

    detected_language = result.get("language", "unknown")
    print(f"[Transcribe] Detected language: {detected_language}")

    transcript_lines = []
    prev_text = None
    for segment in result.get("segments", []):
        text = segment["text"].strip()
        # Skip blank segments and consecutive duplicate lines (Whisper hallucination)
        if not text or text == prev_text:
            continue
        start_hms = seconds_to_hms(segment["start"])
        transcript_lines.append(f"[{start_hms}] Speaker: {text}")
        prev_text = text

    # Save transcript
    meeting_dir = Path(audio_path).parent
    transcript_path = meeting_dir / "transcript.txt"
    full_transcript = "\n".join(transcript_lines)
    transcript_path.write_text(full_transcript, encoding="utf-8")
    print(f"[Transcribe] Transcript saved to {transcript_path} ({len(full_transcript)} chars)")

    # Update recordings index
    update_recording_index(meeting_id, transcript_path=str(transcript_path), status="transcribed")
    print(f"[Transcribe] Updated index for {meeting_id}")

    # Generate summary via Ollama, fall back to a plain header if unavailable
    duration = result["segments"][-1]["end"] if result.get("segments") else 0
    summary_path = meeting_dir / "summary.txt"

    print(f"[Summary] Requesting Ollama summary for {meeting_id}...")
    ollama_summary = _generate_summary_ollama(full_transcript, meeting_name)

    header = (
        f"Meeting: {meeting_name}\n"
        f"Duration: {duration:.1f}s\n"
        f"Language: {detected_language}\n\n"
    )
    if ollama_summary:
        summary_content = header + f"=== AI Summary ===\n{ollama_summary}\n\n=== Full Transcript ===\n{full_transcript}"
        print(f"[Summary] Ollama summary generated ({len(ollama_summary)} chars)")
    else:
        summary_content = header + f"[Summary unavailable — start Ollama with: ollama serve]\n\n=== Full Transcript ===\n{full_transcript}"
    summary_path.write_text(summary_content, encoding="utf-8")

    print(f"[Transcribe] Transcription complete for {meeting_id}")


def transcribe_audio(audio_path: str, meeting_id: str, meeting_name: str):
    """Run Whisper transcription in a background thread with proper error propagation."""
    state.is_transcribing = True
    print(f"[Transcribe] Starting transcription for {meeting_id}...")

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
        status = f" Error: {error_msg}" if error_occurred else " Success"
        print(f"[Transcribe] Thread done for {meeting_id}.{status}")

def seconds_to_hms(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string."""
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
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.get_json() or {}
    meeting_name = data.get('meeting_name', '').strip()
    if not meeting_name:
        return jsonify({"success": False, "error": "Meeting name is required"}), 400

    if state.is_recording:
        return jsonify({"success": False, "error": "Already recording"}), 409

    device = data.get('device')  # optional: device index (int) from /api/devices
    if device is not None:
        try:
            device = int(device)
        except (ValueError, TypeError):
            device = None

    success, msg = start_recording_meeting(meeting_name, device=device)
    return jsonify({"success": success, "message": msg})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    if not state.is_recording:
        return jsonify({"success": False, "error": "Not recording"}), 400

    meeting_info = stop_recording_meeting()
    if meeting_info is None:
        return jsonify({"success": False, "error": "No audio recorded"}), 400

    # Add to index
    index = load_recordings_index()
    index.insert(0, meeting_info)
    save_recordings_index(index)

    # Start transcription in background
    threading.Thread(
        target=transcribe_audio,
        args=(meeting_info["audio_file"], meeting_info["id"], meeting_info["name"]),
        daemon=True
    ).start()

    return jsonify({"success": True, "meeting": meeting_info})

@app.route('/api/recordings', methods=['GET'])
def api_recordings():
    index = load_recordings_index()
    return jsonify(index)

@app.route('/api/delete', methods=['POST'])
def api_delete():
    data = request.get_json() or {}
    meeting_id = data.get('id')
    if not meeting_id:
        return jsonify({"success": False, "error": "Missing meeting id"}), 400

    index = load_recordings_index()
    entry_to_delete = None
    for entry in index:
        if entry.get("id") == meeting_id:
            entry_to_delete = entry
            break

    if entry_to_delete is None:
        return jsonify({"success": False, "error": "Meeting not found"}), 404

    # Remove folder
    meeting_dir = Path(entry_to_delete["audio_file"]).parent
    if meeting_dir.exists():
        import shutil
        shutil.rmtree(meeting_dir)

    # Remove from index
    index = [e for e in index if e.get("id") != meeting_id]
    save_recordings_index(index)

    return jsonify({"success": True})

@app.route('/api/transcript/<meeting_id>', methods=['GET'])
def api_transcript(meeting_id):
    index = load_recordings_index()
    for entry in index:
        if entry.get("id") == meeting_id:
            # Support both transcript_file and transcript_path
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
    status = "idle"
    if state.is_recording:
        status = "recording"
    elif state.is_transcribing:
        status = "transcribing"
    return jsonify({"status": status})

@app.route('/api/devices', methods=['GET'])
def api_devices():
    """Return available audio input devices (for device selector in UI)."""
    try:
        devices = list_input_devices()
        return jsonify({"success": True, "devices": devices})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/live_status', methods=['GET'])
def api_live_status():
    """Return live recording stats — chunk count and precise duration."""
    if not state.is_recording:
        return jsonify({"is_recording": False, "duration": 0.0, "chunks": 0})
    chunks = state.audio_queue
    total_samples = sum(c.shape[0] for c in chunks) if chunks else 0
    duration = round(total_samples / state.sample_rate, 1) if total_samples else 0.0
    return jsonify({
        "is_recording": True,
        "duration": duration,
        "chunks": len(chunks)
    })

if __name__ == '__main__':
    print("Starting MeetScribe...")
    print(f"Recordings dir: {app.config['RECORDINGS_DIR']}")
    print(f"Transcripts dir: {app.config['TRANSCRIPTS_DIR']}")
    app.run(host='0.0.0.0', port=5001, debug=False)
