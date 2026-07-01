"""
ClipDeck engine
===============
Low-level recording engine for ClipDeck.

The core idea (Medal-style instant replay):

  * One long-running ffmpeg process captures the game window (gdigrab) and the
    system audio (raw PCM piped in from a WASAPI loopback thread) and writes a
    rolling ring of 1-second MPEG-TS segments to disk via the `segment` muxer.
  * The ring is bounded (`-segment_wrap`), so old footage is overwritten and
    disk usage stays flat no matter how long you leave it running.
  * When you hit the hotkey we read the segment playlist, grab just enough of
    the most-recent segments to cover the requested duration, copy them out and
    `concat -c copy` them into an .mp4. No re-encode => instant & lossless.

Nothing here touches the UI; `clipdeck.py` drives this module.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile

APP_NAME = "ClipDeck"
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL = 0x00004000

FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

def app_data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d

def _bin_dir() -> str:
    d = os.path.join(app_data_dir(), "bin")
    os.makedirs(d, exist_ok=True)
    return d

def buffer_dir() -> str:
    d = os.path.join(app_data_dir(), "buffer")
    os.makedirs(d, exist_ok=True)
    return d

def find_ffmpeg() -> str | None:
    """Return a usable ffmpeg path, or None. Prefers our private copy."""
    local = os.path.join(_bin_dir(), "ffmpeg.exe")
    if os.path.isfile(local):
        return local
    on_path = shutil.which("ffmpeg")
    return on_path

def ensure_ffmpeg(progress=None) -> str:
    """
    Guarantee an ffmpeg.exe exists, downloading a static build on first run.

    `progress(done_bytes, total_bytes)` is called during the download so the UI
    can show a bar. Returns the absolute path to ffmpeg.exe.
    """
    existing = find_ffmpeg()
    if existing:
        return existing

    target = os.path.join(_bin_dir(), "ffmpeg.exe")
    tmp_zip = os.path.join(_bin_dir(), "_ffmpeg_dl.zip")

    req = urllib.request.Request(FFMPEG_ZIP_URL, headers={"User-Agent": APP_NAME})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_zip, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)

    with zipfile.ZipFile(tmp_zip) as zf:
        member = next(
            (
                n
                for n in zf.namelist()
                if n.replace("\\", "/").endswith("bin/ffmpeg.exe")
            ),
            None,
        )
        if member is None:
            raise RuntimeError("ffmpeg.exe not found inside the downloaded archive")
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    try:
        os.remove(tmp_zip)
    except OSError:
        pass

    if not os.path.isfile(target):
        raise RuntimeError("ffmpeg download failed")
    return target

_ENCODER_TABLE = [
    (
        "hevc_nvenc",
        "NVIDIA NVENC HEVC (Max Quality)",
        ["-rc", "vbr", "-cq", "8", "-preset", "p7", "-tune", "hq", "-b:v", "0", "-spatial-aq", "1", "-temporal-aq", "1"],
    ),
    (
        "h264_nvenc",
        "NVIDIA NVENC (Max Quality)",
        ["-rc", "vbr", "-cq", "8", "-preset", "p7", "-tune", "hq", "-b:v", "0", "-spatial-aq", "1", "-temporal-aq", "1"],
    ),
    ("h264_qsv", "Intel QuickSync", ["-global_quality", "10", "-preset", "veryslow"]),
    (
        "h264_amf",
        "AMD AMF",
        ["-quality", "quality", "-rc", "cqp", "-qp_i", "10", "-qp_p", "10"],
    ),
    ("libx264", "x264 (CPU)", ["-preset", "fast", "-crf", "10"]),
]

def detect_encoder(ffmpeg: str) -> tuple[str, str, list[str]]:
    """Return (encoder_id, human_label, extra_args) for the best available encoder."""
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            timeout=20,
        ).stdout
    except Exception:
        out = ""
    available = {
        line.split()[1]
        for line in out.splitlines()
        if line.strip() and len(line.split()) > 1 and line.lstrip()[0] in "VAS"
    }
    for enc, label, args in _ENCODER_TABLE:
        if enc in available:
            return enc, label, args
    return _ENCODER_TABLE[-1]

class AudioPump:
    """
    Captures the default playback device via WASAPI loopback and pushes raw
    16-bit PCM into a file-like sink (ffmpeg's stdin).

    Uses PyAudio *callback* mode rather than blocking reads. This matters: a
    blocking read on a WASAPI loopback device never returns while the system is
    silent, which would deadlock shutdown. Callback mode stops cleanly via
    stop_stream() and keeps the capture endpoint alive so silence still flows.
    """

    def __init__(self):
        self.rate = 48000
        self.channels = 2
        self._dev_index = None
        self._pa = None
        self._stream = None
        self._running = False
        self._sink = None

    @staticmethod
    def available() -> bool:
        try:
            import pyaudiowpatch

            return True
        except Exception:
            return False

    def open(self) -> bool:
        """Probe the loopback device. Returns False if unavailable."""
        try:
            import pyaudiowpatch as pyaudio
        except Exception:
            return False
        try:
            self._pa = pyaudio.PyAudio()
            info = self._pa.get_default_wasapi_loopback()
            self.rate = int(info["defaultSampleRate"])
            self.channels = min(2, int(info["maxInputChannels"]) or 2)
            self._dev_index = info["index"]
            return True
        except Exception:
            self.close()
            return False

    def start(self, sink) -> None:
        import pyaudiowpatch as pyaudio

        self._sink = sink
        self._running = True

        def callback(in_data, frame_count, time_info, status):
            if self._running and in_data:
                try:
                    self._sink.write(in_data)
                except (BrokenPipeError, ValueError, OSError):
                    self._running = False
                    return (None, pyaudio.paComplete)
            return (None, pyaudio.paContinue)

        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=self._dev_index,
            frames_per_buffer=2048,
            stream_callback=callback,
        )

    def close(self) -> None:
        self._running = False
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        try:
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass
        self._pa = None

class Recorder:
    """
    Owns the long-running ffmpeg buffer process and turns the on-disk ring into
    .mp4 clips on demand.
    """

    SEG_SECONDS = 1

    def __init__(self, ffmpeg: str, encoder: tuple[str, str, list[str]]):
        self.ffmpeg = ffmpeg
        self.encoder_id, self.encoder_label, self.encoder_args = encoder
        self.proc: subprocess.Popen | None = None
        self.audio: AudioPump | None = None
        self._stderr_tail: list[str] = []
        self._stderr_thread: threading.Thread | None = None
        self._seg_dir = buffer_dir()
        self._playlist = os.path.join(self._seg_dir, "buffer.m3u8")
        self._lock = threading.Lock()
        self._ring = 35
        self._janitor_thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, cfg: dict) -> None:
        """
        cfg keys: fps, clip_seconds, use_audio (bool)
        Always captures the full desktop.
        """
        if self.running:
            return
        self._clear_buffer()
        self._stderr_tail = []

        ring = max(
            8, int(cfg["clip_seconds"]) + 6
        )
        self._ring = ring
        use_audio = bool(cfg.get("use_audio")) and AudioPump.available()

        self.audio = AudioPump() if use_audio else None
        if self.audio and not self.audio.open():
            self.audio = None

        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]

        region = cfg.get("capture_region")

        # Use user's requested fps for capture. For best quality use 144fps (or 120).
        # High fps on high-res + audio is demanding with gdigrab; the data guard waits longer.
        capture_fps = int(cfg.get("fps", 144))
        cmd += [
            "-f", "gdigrab",
            "-framerate", str(capture_fps),
            "-draw_mouse", "0",
        ]
        if region:
            x, y, w, h = region
            cmd += [
                "-offset_x", str(int(x)),
                "-offset_y", str(int(y)),
                "-video_size", f"{int(w)}x{int(h)}",
            ]
        cmd += ["-thread_queue_size", "1024", "-i", "desktop"]

        mic_name = cfg.get("mic_device", "")
        if self.audio:
            cmd += [
                "-f", "s16le",
                "-ar", str(self.audio.rate),
                "-ac", str(self.audio.channels),
                "-use_wallclock_as_timestamps", "1",
                "-thread_queue_size", "1024",
                "-i", "pipe:0",
            ]
            
        if mic_name:
            cmd += [
                "-f", "dshow",
                "-thread_queue_size", "1024",
                "-i", f"audio={mic_name}",
            ]

        if self.audio and mic_name:
            cmd += [
                "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=longest[aout]",
                "-map", "0:v",
                "-map", "[aout]"
            ]
        elif self.audio or mic_name:
            cmd += ["-map", "0:v", "-map", "1:a"]
        else:
            cmd += ["-map", "0:v"]

        cmd += ["-fps_mode", "passthrough"]

        enc_args = list(self.encoder_args)
        cmd += [
            "-c:v", self.encoder_id,
            *enc_args,
            "-pix_fmt", "yuv420p",
            "-g", str(capture_fps),
        ]

        if self.audio or mic_name:
            ab = str(cfg.get("audio_bitrate", 320)) + "k"
            cmd += ["-c:a", "aac", "-b:a", ab]

        cmd += [
            "-f",
            "segment",
            "-segment_time",
            str(self.SEG_SECONDS),
            "-segment_format",
            "mpegts",
            "-segment_list",
            self._playlist,
            "-segment_list_size",
            str(ring),
            "-segment_list_flags",
            "+live",
            "-reset_timestamps",
            "1",
            os.path.join(self._seg_dir, "seg%08d.ts"),
        ]

        import shlex
        print("FFMPEG CMD:", shlex.join(cmd))
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if self.audio else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW | BELOW_NORMAL,
        )

        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        if self.audio:
            self.audio.start(self.proc.stdin)

        time.sleep(0.6)
        if self.proc.poll() is not None:
            err = self.last_error() or "ffmpeg exited immediately"
            self.stop()
            raise RuntimeError(err)

        # Wait for actual video data (non-zero segments) to appear.
        # Require a few sustained non-empty segments.
        # 144fps max quality needs more headroom on high-res monitors.
        deadline = time.time() + 12.0
        data_ok = False
        while time.time() < deadline and self.proc and self.proc.poll() is None:
            time.sleep(0.3)
            try:
                good = []
                for name in os.listdir(self._seg_dir):
                    if name.startswith("seg") and name.endswith(".ts"):
                        p = os.path.join(self._seg_dir, name)
                        if os.path.getsize(p) > 300:
                            good.append(p)
                if len(good) >= 3:
                    data_ok = True
                    break
            except Exception:
                pass
        if not data_ok:
            err = self.last_error() or "Žiadne video dáta (gdigrab neposiela snímky). Skús nižšie FPS (30-60), vypni audio, alebo iný monitor."
            self.stop()
            raise RuntimeError(err)

        self._janitor_thread = threading.Thread(target=self._janitor, daemon=True)
        self._janitor_thread.start()

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
            try:
                p.wait(timeout=4)
            except Exception:
                pass

        a, self.audio = self.audio, None
        if a:
            t = threading.Thread(target=a.close, daemon=True)
            t.start()
            t.join(timeout=2.0)

        try:
            if p and p.stdin:
                p.stdin.close()
        except Exception:
            pass

    def _janitor(self) -> None:
        """Keep the on-disk ring bounded by deleting the oldest segments.

        We keep a few more files than the playlist references so the clipper can
        never race a delete: a clip only ever touches the newest ~clip_seconds
        segments, while we only prune well past that.
        """
        keep = self._ring + 4
        while self.running:
            try:
                segs = sorted(
                    f
                    for f in os.listdir(self._seg_dir)
                    if f.startswith("seg") and f.endswith(".ts")
                )
                for f in segs[:-keep]:
                    try:
                        os.remove(os.path.join(self._seg_dir, f))
                    except OSError:
                        pass
            except OSError:
                pass
            time.sleep(2)

    def _drain_stderr(self) -> None:
        p = self.proc
        if not p or not p.stderr:
            return
        for raw in iter(p.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if line:
                self._stderr_tail.append(line)
                del self._stderr_tail[:-5]

    def last_error(self) -> str:
        return " | ".join(self._stderr_tail[-5:]) if self._stderr_tail else ""

    def save_clip(self, seconds: float, out_path: str) -> str:
        """
        Build an .mp4 from the most recent `seconds` of the ring. Blocking;
        call from a worker thread. Returns out_path on success.
        """
        with self._lock:
            segments = self._tail_segments(seconds)
            if not segments:
                raise RuntimeError(
                    "Buffer je prázdny. Nahrávaj dlhšie, alebo zníž FPS (gdigrab + audio + vysoké rozlíšenie nestíha)."
                )

            work = os.path.join(self._seg_dir, "_clip_tmp")
            shutil.rmtree(work, ignore_errors=True)
            os.makedirs(work, exist_ok=True)

            listing = os.path.join(work, "list.txt")
            with open(listing, "w", encoding="utf-8") as lf:
                for i, (path, _dur) in enumerate(segments):
                    safe = os.path.join(work, f"s{i:05d}.ts")
                    try:
                        shutil.copyfile(path, safe)
                    except OSError:
                        continue
                    lf.write(f"file '{safe.replace(os.sep, '/')}'\n")

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            cmd = [
                self.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                listing,
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                out_path,
            ]
            res = subprocess.run(
                cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
            )
            shutil.rmtree(work, ignore_errors=True)
            if res.returncode != 0 or not os.path.isfile(out_path):
                raise RuntimeError(
                    res.stderr.strip().splitlines()[-1]
                    if res.stderr.strip()
                    else "concat zlyhal"
                )

            thumb_path = out_path.rsplit(".", 1)[0] + ".jpg"
            generate_thumbnail(self.ffmpeg, out_path, thumb_path)

            return out_path

    def _tail_segments(self, seconds: float) -> list[tuple[str, float]]:
        """Parse the playlist and return the tail (path, dur) covering `seconds`."""
        try:
            with open(self._playlist, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return []

        entries: list[tuple[str, float]] = []
        dur = self.SEG_SECONDS
        for line in lines:
            if line.startswith("#EXTINF:"):
                try:
                    dur = float(line[len("#EXTINF:") :].split(",")[0])
                except ValueError:
                    dur = self.SEG_SECONDS
            elif line and not line.startswith("#"):
                name = os.path.basename(line.strip())
                path = os.path.join(self._seg_dir, name)
                try:
                    if os.path.getsize(path) > 0:
                        entries.append((path, dur))
                except OSError:
                    pass

        chosen: list[tuple[str, float]] = []
        acc = 0.0
        for item in reversed(entries):
            chosen.append(item)
            acc += item[1]
            if acc >= seconds:
                break
        chosen.reverse()
        return chosen

    def _clear_buffer(self) -> None:
        for name in os.listdir(self._seg_dir):
            if name.endswith(".ts") or name.endswith(".m3u8"):
                try:
                    os.remove(os.path.join(self._seg_dir, name))
                except OSError:
                    pass

def generate_thumbnail(ffmpeg: str, video_path: str, thumb_path: str) -> bool:
    """Extract a 16:9 thumbnail from the middle of the video."""
    if not os.path.isfile(video_path):
        return False
    try:
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "00:00:02",
            "-i",
            video_path,
            "-vframes",
            "1",
            "-q:v",
            "5",
            "-vf",
            "scale=480:-2",
            thumb_path,
        ]
        res = subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
        if res.returncode != 0 and not os.path.isfile(thumb_path):
            cmd[6] = "00:00:00"
            subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
        return os.path.isfile(thumb_path)
    except Exception:
        return False
