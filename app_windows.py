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

        # Separate queues for mic and loopback streams
        self.mic_queue = []
        self.loopback_queue = []

        self.sample_rate = 16000
        self.recording_thread = None

state = RecordingState()

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
def start_recording_meeting(meeting_name: str, mic_device=None, loopback_device=None):
    """Start recording from mic and/or loopback device in parallel threads."""
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
    state.sample_rate = 16000

    def record_loop():
        streams = []
        try:
            # Mic stream
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
                    streams.append(mic_stream)
                    print(f"[Record] Mic stream started: device={mic_device}")
                except Exception as e:
                    print(f"[Record] Mic stream failed: {e}")

            # Loopback stream (system audio)
            if loopback_device is not None:
                try:
                    dev_info = sd.query_devices(loopback_device)
                    ch = max(1, min(dev_info['max_input_channels'], 2))
                    lb_stream = sd.InputStream(
                        device=loopback_device,
                        samplerate=state.sample_rate,
                        channels=ch,
                        dtype='float32',
                        callback=_loopback_callback,
                    )
                    lb_stream.start()
                    streams.append(lb_stream)
                    print(f"[Record] Loopback stream started: device={loopback_device}")
                except Exception as e:
                    print(f"[Record] Loopback stream failed: {e}")

            # If no streams opened, fall back to default input
            if not streams:
                print("[Record] No valid devices — using default input as mic")
                fallback = sd.InputStream(
                    samplerate=state.sample_rate,
                    channels=1,
                    dtype='float32',
                    callback=_mic_callback,
                )
                fallback.start()
                streams.append(fallback)

            while state.is_recording:
                sd.sleep(100)

        except Exception as e:
            print(f"[Record] Unexpected error: {e}")
        finally:
            for s in streams:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass

    state.recording_thread = threading.Thread(target=record_loop, daemon=True)
    state.recording_thread.start()
    return True, f"Recording started: {meeting_name}"


def stop_recording_meeting():
    """Stop recording, mix mic + loopback, and save a single WAV file."""
    if not state.is_recording:
        return None

    state.is_recording = False
    if state.recording_thread:
        state.recording_thread.join(timeout=3)

    mic_chunks = state.mic_queue
    lb_chunks = state.loopback_queue

    if not mic_chunks and not lb_chunks:
        return None

    sr = state.sample_rate

    def concat(chunks):
        if not chunks:
            return None
        data = np.concatenate(chunks, axis=0)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data.astype(np.float32)

    mic_audio = concat(mic_chunks)
    lb_audio = concat(lb_chunks)

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
        mixed = lb_audio
        print(f"[Stop] Loopback only: {len(lb_audio)/sr:.1f}s")

    audio_path = state.current_meeting_dir / "recording.wav"
    sf.write(str(audio_path), mixed, sr)

    meeting_info = {
        "id": state.current_meeting_id,
        "name": state.current_meeting_name,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "duration": round(len(mixed) / sr, 1),
        "audio_file": str(audio_path),
        "transcript_file": None,
        "status": "recorded"
    }

    state.mic_queue = []
    state.loopback_queue = []
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


def _generate_summary_ollama(transcript: str, meeting_name: str):
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
        "model": "minimax-m2.7:cloud",
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
    transcript_path.write_text(full_transcript, encoding="utf-8")
    print(f"[Transcribe] Transcript saved ({len(full_transcript)} chars)")

    update_recording_index(meeting_id, transcript_path=str(transcript_path), status="transcribed")
    print(f"[Transcribe] Updated index for {meeting_id}")

    summary_path = meeting_dir / "summary.txt"
    print(f"[Summary] Requesting Ollama summary for {meeting_id}...")
    ollama_summary = _generate_summary_ollama(full_transcript, meeting_name)

    header = (
        f"Meeting: {meeting_name}\n"
        f"Language: {detected_language}\n\n"
    )
    if ollama_summary:
        summary_content = header + f"=== AI Summary ===\n{ollama_summary}\n\n=== Full Transcript ===\n{full_transcript}"
        print(f"[Summary] Ollama summary generated ({len(ollama_summary)} chars)")
    else:
        summary_content = header + "[Summary unavailable — start Ollama with: ollama serve]\n\n=== Full Transcript ===\n{full_transcript}"
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

    mic_device      = parse_device(data.get('mic_device'))
    loopback_device = parse_device(data.get('loopback_device'))

    success, msg = start_recording_meeting(meeting_name, mic_device=mic_device, loopback_device=loopback_device)
    return jsonify({"success": success, "message": msg})

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
    lb_samples  = sum(c.shape[0] for c in state.loopback_queue) if state.loopback_queue else 0
    total_samples = max(mic_samples, lb_samples)
    duration = round(total_samples / state.sample_rate, 1)
    return jsonify({
        "is_recording": True,
        "duration": duration,
        "chunks": len(state.mic_queue) + len(state.loopback_queue),
        "mic_chunks": len(state.mic_queue),
        "loopback_chunks": len(state.loopback_queue),
    })

if __name__ == '__main__':
    print("Starting MeetScribe (Windows)...")
    print(f"Recordings dir: {app.config['RECORDINGS_DIR']}")
    print(f"Transcripts dir: {app.config['TRANSCRIPTS_DIR']}")
    # Pre-load Whisper model in background so first transcription is fast
    threading.Thread(target=get_whisper_model, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, debug=False)
