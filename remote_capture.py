"""
Remote browser capture (Mode B) — record a meeting from a browser on ANOTHER
machine while this PC does the Whisper + Ollama work.

Why this exists
---------------
MeetScribe's normal path captures the mic + WASAPI loopback of the machine
running the server. That is useless when the meeting is on a different laptop:
the audio physically lives over there. Rather than install Python/Whisper on a
slow laptop, the browser on that laptop captures the audio itself
(getUserMedia for the mic, getDisplayMedia for the Google Meet tab), encodes it
with the hardware Opus encoder, and streams chunks here. This PC decodes,
mixes, and hands the result to the EXISTING pipeline.

Design constraint: nothing in the local recording path is touched. These routes
join the pipeline only once a WAV exists on disk — the point where
transcribe_audio() already cannot tell how the audio was captured.

Channel layout
--------------
The browser sends a 2-channel stream: LEFT = microphone, RIGHT = meeting/tab
audio. Keeping them separate until they reach the server lets the same
audio-health classifier used by the local path decide whether the meeting audio
was really captured, instead of guessing from a pre-mixed blob.
"""

import shutil
import subprocess
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from flask import jsonify, request

# Browsers cap a single MediaRecorder blob well under this; the guard is here so
# a malformed or hostile request cannot fill the disk.
MAX_CHUNK_BYTES = 32 * 1024 * 1024
# A meeting longer than this is almost certainly a session someone forgot to stop.
MAX_SESSION_BYTES = 2 * 1024 * 1024 * 1024

_sessions = {}
_lock = threading.Lock()


def _find_ffmpeg():
    """Locate ffmpeg. PATH first, then the WinGet install location."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for pattern in ("ffmpeg*/bin/ffmpeg.exe", "*/ffmpeg*/bin/ffmpeg.exe"):
        base = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
        for candidate in base.glob(f"*/{pattern}"):
            return str(candidate)
    return None


def register_remote_capture(app, *, recordings_dir, active_ratio, classify_system_audio,
                            load_index, save_index, transcribe_audio, state,
                            sample_rate=16000):
    """Attach the /api/remote/* routes to an existing Flask app.

    Dependencies are injected rather than imported so this module stays
    decoupled from app.py / app_windows.py (which must remain identical twins).
    """

    def _reap_stale_sessions(max_age_hours=8):
        """Discard sessions the browser never finished.

        Closing the laptop lid or killing the tab mid-meeting leaves a session
        holding an open file handle with nothing to finalize it. Without this,
        those handles and their empty directories accumulate until a restart.
        """
        now = datetime.now()
        with _lock:
            stale = [
                s for s in _sessions.values()
                if (now - s["started_at"]).total_seconds() > max_age_hours * 3600
            ]
            for s in stale:
                _sessions.pop(s["id"], None)
        for s in stale:
            try:
                s["handle"].close()
            except Exception:
                pass
            # Keep anything that actually captured audio; drop empty shells.
            if s["bytes"] == 0:
                shutil.rmtree(s["dir"], ignore_errors=True)
            print(f"[Remote] Reaped stale session {s['id']} ({s['bytes']} bytes)")

    def _session_dir(meeting_name, meeting_id):
        safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_"
                       for c in meeting_name.strip())
        d = Path(recordings_dir) / f"{safe}_{meeting_id}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @app.route("/api/remote/start", methods=["POST"])
    def api_remote_start():
        _reap_stale_sessions()

        data = request.get_json() or {}
        meeting_name = (data.get("meeting_name") or "").strip()
        if not meeting_name:
            return jsonify({"success": False, "error": "Meeting name is required"}), 400

        # Refuse to run both capture modes at once: they would produce two
        # recordings of the same meeting and fight over the transcription queue.
        if state.is_recording:
            return jsonify({
                "success": False,
                "error": "This PC is already recording locally. Stop that first.",
            }), 409

        meeting_id = uuid.uuid4().hex[:8]
        meeting_dir = _session_dir(meeting_name, meeting_id)
        raw_path = meeting_dir / "remote_capture.webm"

        with _lock:
            _sessions[meeting_id] = {
                "id": meeting_id,
                "name": meeting_name,
                "dir": meeting_dir,
                "raw_path": raw_path,
                "handle": open(raw_path, "wb"),
                "bytes": 0,
                "started_at": datetime.now(),
                "finalized": False,
            }

        print(f"[Remote] Session {meeting_id} started for '{meeting_name}' -> {raw_path}")
        return jsonify({"success": True, "id": meeting_id, "name": meeting_name})

    @app.route("/api/remote/chunk", methods=["POST"])
    def api_remote_chunk():
        meeting_id = request.args.get("id")
        with _lock:
            session = _sessions.get(meeting_id)
        if not session or session["finalized"]:
            return jsonify({"success": False, "error": "Unknown or finished session"}), 404

        blob = request.get_data()
        if not blob:
            return jsonify({"success": True, "bytes": session["bytes"]})
        if len(blob) > MAX_CHUNK_BYTES:
            return jsonify({"success": False, "error": "Chunk too large"}), 413
        if session["bytes"] + len(blob) > MAX_SESSION_BYTES:
            return jsonify({"success": False, "error": "Session size limit reached"}), 413

        # MediaRecorder chunks after the first are not independently decodable,
        # but appended in order they form one valid WebM stream.
        session["handle"].write(blob)
        session["handle"].flush()
        session["bytes"] += len(blob)
        return jsonify({"success": True, "bytes": session["bytes"]})

    @app.route("/api/remote/finalize", methods=["POST"])
    def api_remote_finalize():
        data = request.get_json() or {}
        meeting_id = data.get("id")
        with _lock:
            session = _sessions.get(meeting_id)
            if not session or session["finalized"]:
                return jsonify({"success": False, "error": "Unknown or finished session"}), 404
            session["finalized"] = True

        try:
            session["handle"].close()
        except Exception:
            pass

        if session["bytes"] == 0:
            return jsonify({"success": False, "error": "No audio was received"}), 400

        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            return jsonify({"success": False, "error": "ffmpeg not found on this PC"}), 500

        meeting_dir = session["dir"]
        stereo_path = meeting_dir / "remote_stereo.wav"
        audio_path = meeting_dir / "recording.wav"

        # Decode the browser's Opus stream, preserving the two channels so the
        # mic and the meeting audio can still be judged independently.
        proc = subprocess.run(
            [ffmpeg, "-y", "-i", str(session["raw_path"]),
             "-ac", "2", "-ar", str(sample_rate), str(stereo_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not stereo_path.exists():
            print(f"[Remote] ffmpeg failed: {proc.stderr[-800:]}")
            return jsonify({"success": False, "error": "Could not decode the uploaded audio"}), 500

        audio, sr = sf.read(str(stereo_path), dtype="float32", always_2d=True)
        mic_audio = audio[:, 0]
        sys_audio = audio[:, 1] if audio.shape[1] > 1 else np.zeros_like(mic_audio)

        try:
            mic_ratio = active_ratio(mic_audio, sr)
            sys_ratio = active_ratio(sys_audio, sr)
            system_audio = classify_system_audio(sys_audio, sys_ratio, mic_ratio)
        except Exception as e:
            print(f"[Remote] Audio-health check failed: {e}")
            mic_ratio, sys_ratio, system_audio = None, None, "unknown"

        # Same 50/50 balance the local path uses, so transcription quality is
        # consistent no matter which machine captured the meeting.
        mixed = (mic_audio + sys_audio) * 0.5
        peak = float(np.max(np.abs(mixed))) if len(mixed) else 0.0
        if peak > 1.0:
            mixed = mixed / peak
        sf.write(str(audio_path), mixed, sr)

        duration = round(len(mixed) / sr, 1) if sr else 0.0
        print(f"[Remote] {meeting_id}: system_audio={system_audio} "
              f"(system active {sys_ratio}, mic active {mic_ratio}, {duration}s)")

        for tmp in (stereo_path, session["raw_path"]):
            try:
                tmp.unlink()
            except Exception:
                pass

        meeting_info = {
            "id": meeting_id,
            "name": session["name"],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "duration": duration,
            "audio_file": str(audio_path),
            "transcript_file": None,
            "status": "recorded",
            "system_audio": system_audio,
            "output_device": "Remote browser (mic + shared tab)",
            "output_is_bluetooth": False,
            "source": "remote",
        }

        index = load_index()
        index.insert(0, meeting_info)
        save_index(index)

        threading.Thread(
            target=transcribe_audio,
            args=(meeting_info["audio_file"], meeting_id, meeting_info["name"]),
            daemon=True,
        ).start()

        with _lock:
            _sessions.pop(meeting_id, None)

        return jsonify({"success": True, "meeting": meeting_info})

    @app.route("/api/remote/cancel", methods=["POST"])
    def api_remote_cancel():
        data = request.get_json() or {}
        meeting_id = data.get("id")
        with _lock:
            session = _sessions.pop(meeting_id, None)
        if not session:
            return jsonify({"success": False, "error": "Unknown session"}), 404
        try:
            session["handle"].close()
        except Exception:
            pass
        try:
            shutil.rmtree(session["dir"], ignore_errors=True)
        except Exception:
            print(f"[Remote] Cleanup failed for {meeting_id}: {traceback.format_exc()}")
        print(f"[Remote] Session {meeting_id} cancelled and discarded")
        return jsonify({"success": True})

    @app.route("/api/remote/status", methods=["GET"])
    def api_remote_status():
        """Lets the browser confirm the server still has its session."""
        meeting_id = request.args.get("id")
        with _lock:
            session = _sessions.get(meeting_id)
            if not session:
                return jsonify({"active": False})
            elapsed = (datetime.now() - session["started_at"]).total_seconds()
            return jsonify({
                "active": True,
                "id": session["id"],
                "name": session["name"],
                "bytes": session["bytes"],
                "elapsed": round(elapsed, 1),
            })

    print("[Remote] Browser-capture routes registered at /api/remote/*")
