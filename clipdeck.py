"""
ClipDeck  —  instant-replay clipper for Windows.

System tray app with a status panel. Continuously records a selected
monitor + system audio into a rolling buffer.  Press the hotkey to save
the last N seconds as an .mp4.

Settings let you pick:
  - which monitor to record
  - which monitor shows the status panel
  - FPS, quality, clip length, hotkey, save folder

See engine.py for the recording internals.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import os
import threading
import time
import tkinter as tk
import re
import psutil

def get_foreground_window_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value.strip()
    except:
        pass
    return ""


def get_foreground_process_name() -> str:
    """Get the exe name of the current foreground window's process.
    This works reliably even in fullscreen exclusive games.
    """
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = ctypes.wintypes.DWORD(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""
        proc = psutil.Process(pid.value)
        return proc.name().lower()
    except Exception:
        return ""

class OSDNotification:
    def __init__(self, message: str, monitor: dict):
        self.root = ctk.CTkToplevel()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-toolwindow", True)
        self.root.attributes("-alpha", 0.0)
        self.root.configure(fg_color="#18181b") 
        
        # Prevent this notification window from stealing focus / activating
        # (important so fullscreen game doesn't get kicked out)
        try:
            hwnd = self.root.winfo_id()
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            ex_style |= 0x08000000  # WS_EX_NOACTIVATE
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style)
        except Exception:
            pass
        
        lbl = ctk.CTkLabel(self.root, text=message, font=("Inter", 18, "bold"), text_color="#10b981", padx=20, pady=15)
        lbl.pack(expand=True, fill="both")
        
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()
        
        if monitor:
            x = monitor["x"] + (monitor["w"] // 2) - (w // 2)
            y = monitor["y"] + 60
            self.root.geometry(f"+{x}+{y}")
        else:
            self.root.geometry(f"+100+100")
            
        self._fade_in()

    def _fade_in(self, alpha=0.0):
        if alpha < 0.9:
            alpha += 0.1
            try:
                self.root.attributes("-alpha", alpha)
                self.root.after(30, self._fade_in, alpha)
            except: pass
        else:
            try: self.root.after(2500, self._fade_out, alpha)
            except: pass

    def _fade_out(self, alpha=0.9):
        if alpha > 0.0:
            alpha -= 0.1
            try:
                self.root.attributes("-alpha", alpha)
                self.root.after(30, self._fade_out, alpha)
            except: pass
        else:
            try: self.root.destroy()
            except: pass

def show_osd(msg, monitor):
    OSDNotification(msg, monitor)

import keyboard
import customtkinter as ctk

import engine
import gallery

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG = "#09090b"
CARD = "#18181b"
CARD2 = "#27272a"
ACCENT = "#10b981"
ACC_HVR = "#059669"
MUTED = "#a1a1aa"
TXT = "#f4f4f5"
REC = "#ef4444"
GOOD = "#10b981"
BORDER = "#262a36"
FONT = "Segoe UI"

CONFIG_PATH = os.path.join(engine.app_data_dir(), "config.json")

DEFAULTS = {
    "fps": 144,
    "clip_seconds": 30,
    "use_audio": True,
    "audio_bitrate": 320,
    "hotkey": "f4",
    "save_dir": os.path.join(os.path.expanduser("~"), "Videos", "ClipDeck"),
    "capture_monitor": 0,
    "gui_monitor": 1,
    "show_osd": False,
    "smart_record": True,
    "tracked_games": [
        "cs2.exe",
        "csgo.exe",
        "fortniteclient-win64-shipping.exe",
        "valorant-win64-shipping.exe",
        "gta5.exe",
        "league of legends.exe",
        "r5apex.exe",
        "minecraft.exe",
        "eldenring.exe",
        "dota2.exe"
    ]
}

def build_recorder_start_cfg(cfg: dict, monitors: list) -> dict:
    """Pure helper extracted from _start_recording (shipped path)."""
    cap_idx = cfg.get("capture_monitor", 0)
    capture_region = None
    if monitors:
        if cap_idx >= len(monitors):
            cap_idx = 0
        cap_mon = monitors[cap_idx]
        capture_region = (cap_mon["x"], cap_mon["y"], cap_mon["w"], cap_mon["h"])
    return {
        "fps": cfg.get("fps", 120),
        "clip_seconds": cfg.get("clip_seconds", 30),
        "use_audio": cfg["use_audio"],
        "audio_bitrate": cfg["audio_bitrate"],
        "capture_region": capture_region,
        "capture_monitor_idx": cap_idx,
        "mic_device": cfg.get("mic_device", ""),
    }

def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg

def save_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

user32 = ctypes.windll.user32

def get_monitors() -> list[dict]:
    """
    Return list of monitors:  x, y, w, h (full rect), wx, wy, ww, wh (work
    area), primary (bool).
    """
    monitors: list[dict] = []
    MONITORINFOF_PRIMARY = 0x00000001

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.wintypes.DWORD),
        ]

    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hMonitor, ctypes.byref(info))
        m = info.rcMonitor
        w = info.rcWork
        monitors.append(
            {
                "x": m.left,
                "y": m.top,
                "w": m.right - m.left,
                "h": m.bottom - m.top,
                "wx": w.left,
                "wy": w.top,
                "ww": w.right - w.left,
                "wh": w.bottom - w.top,
                "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
            }
        )
        return True

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.RECT),
        ctypes.c_void_p,
    )
    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
    monitors.sort(key=lambda m: (not m["primary"], m["x"]))
    return monitors

def monitor_label(i: int, m: dict) -> str:
    tag = " ★" if m["primary"] else ""
    return f"Monitor {i + 1}: {m['w']}×{m['h']}{tag}"

def _notify(tray, title: str, msg: str) -> None:
    try:
        tray.notify(msg, title)
    except Exception:
        pass

class ClipDeckApp:
    def __init__(self):
        self.cfg = load_config()
        self.monitors = get_monitors()
        self.recorder: engine.Recorder | None = None
        self.tray = None
        self._ffmpeg: str | None = None
        self._encoder = None
        self._ready = False
        self._saving = False
        self._gallery_win = None
        self._wants_to_record = False
        self._is_sleeping = False

        self.root = ctk.CTk(fg_color=BG)
        self.root.withdraw()
        self.root.title("ClipDeck")

    def run(self):
        threading.Thread(target=self._boot, daemon=True).start()
        self.root.after(500, self._open_gallery)
        self.root.mainloop()

    def _boot(self):
        time.sleep(0.3)
        self._ffmpeg = self._ensure_ffmpeg()
        if not self._ffmpeg:
            self._panel_toast("✘ ffmpeg nenájdený!", REC)
            return
        self._encoder = engine.detect_encoder(self._ffmpeg)
        self.recorder = engine.Recorder(self._ffmpeg, self._encoder)
        
        threading.Thread(target=self._game_detector_loop, daemon=True).start()
        
        if not self.cfg.get("smart_record", True):
            self._start_recording()
        else:
            self._is_sleeping = True
            
        self._apply_hotkey()
        self._run_tray()

    def _ensure_ffmpeg(self) -> str | None:
        ff = engine.find_ffmpeg()
        if ff:
            return ff
        try:
            self._panel_toast("Sťahujem ffmpeg…", MUTED)
            return engine.ensure_ffmpeg(lambda d, t: None)
        except Exception:
            return None

    def _stop_recording(self):
        if self.recorder and self.recorder.running:
            self.recorder.stop()
        self._wants_to_record = False
        self._ready = False
        self._is_sleeping = True
        if self._gallery_win:
            self._gallery_win.set_recording(False)

    def _game_detector_loop(self):
        while True:
            time.sleep(3)
            if not self.cfg.get("smart_record", True):
                if self._is_sleeping:
                    self._is_sleeping = False
                    self._start_recording()
                continue
                
            tracked = {g.lower() for g in self.cfg.get("tracked_games", [])}
            found = False

            # Check any tracked process is running (existence based - keeps buffer while game exe is up)
            # Use improved partial matching for different game launchers / exe names
            try:
                for p in psutil.process_iter(['name']):
                    name = p.info['name']
                    if name:
                        n = name.lower()
                        for g in tracked:
                            if g in n or n in g:
                                found = True
                                break
                    if found:
                        break
            except Exception:
                pass
                
            if found and self._is_sleeping:
                self._is_sleeping = False
                self._start_recording()
            elif not found and not self._is_sleeping:
                self._stop_recording()

    def _start_recording(self):
        self._is_sleeping = False
        if self.recorder and self.recorder.running:
            self.recorder.stop()
            time.sleep(0.3)

        self.monitors = get_monitors()
        start_cfg = build_recorder_start_cfg(self.cfg, self.monitors)
        cap_idx = start_cfg["capture_monitor_idx"]
        capture_region = start_cfg["capture_region"]
        cap_mon = None
        if self.monitors:
            if cap_idx < len(self.monitors):
                cap_mon = self.monitors[cap_idx]

        self._wants_to_record = True
        cfg = start_cfg  # use the extracted pure helper result
        try:
            self.recorder.start(cfg)
            self._ready = True
        except RuntimeError as e:
            err_str = str(e).lower()
            err_msg = str(e)
            
            if cfg.get("mic_device") and ("dshow" in err_str or "audio=" in err_str):
                self._panel_toast("⚠ Mikrofón blokovaný! Nahrávam bez neho.", REC)
                cfg["mic_device"] = ""
                try:
                    self.recorder.start(cfg)
                    self._ready = True
                except Exception as e2:
                    self._ready = False
                    self._panel_toast(f"Chyba FFMPEG: {e2}", REC)
            else:
                self._ready = False
                if "failed to capture image (error 5)" in err_str or "gdigrab" in err_str or "desktop" in err_str:
                    self._panel_toast("Chyba: Zvoľ Celý Monitor (Hra to blokuje)", REC)
                elif "žiadne video dáta" in err_str.lower() or "no video" in err_str.lower() or "neposiela" in err_str.lower():
                    self._panel_toast("Chyba: Žiadne dáta – zníž FPS na 60 alebo vypni audio!", REC)
                else:
                    short_err = err_msg.split(" | ")[-1] if " | " in err_msg else err_msg
                    self._panel_toast(f"Chyba: {short_err[:55]}", REC)
                
        if self._ready:
            res = f"{cap_mon['w']}×{cap_mon['h']}" if cap_mon else "?"

            enc = self._encoder[1] if self._encoder else "?"
            if self._gallery_win:
                self.root.after(
                    0, self._gallery_win.set_recording, True, enc, res, self.cfg["fps"]
                )
                self.root.after(800, self._gallery_win.update_game)

        if not getattr(self, "_watchdog_started", False):
            self._watchdog_started = True
            self.root.after(2000, self._watchdog)

    def _watchdog(self):
        if not getattr(self, "_wants_to_record", False) or self._is_sleeping:
            self.root.after(2000, self._watchdog)
            return

        if not self._ready or (self.recorder and not self.recorder.running):
            if self._gallery_win:
                self._gallery_win.set_recording(False)
            threading.Thread(target=self._start_recording, daemon=True).start()
        else:
            self.root.after(2000, self._watchdog)

    def _apply_hotkey(self):
        try:
            keyboard.clear_all_hotkeys()
        except Exception:
            pass
        try:
            keyboard.add_hotkey(self.cfg["hotkey"], self._on_hotkey)
        except Exception:
            pass

    def _open_settings(self):
        self._open_gallery()
        if self._gallery_win:
            self._gallery_win._show_settings()

    def _open_gallery(self):
        if self._gallery_win is not None:
            try:
                self._gallery_win.focus()
                self._gallery_win._load_clips()
                return
            except Exception:
                self._gallery_win = None
        self.monitors = get_monitors()
        self._gallery_win = gallery.GalleryWindow(
            self.root, self.cfg, self.monitors, self._on_settings_saved
        )

    def _on_settings_saved(self, new_cfg):
        self.cfg = new_cfg
        save_config(self.cfg)
        self._apply_hotkey()
        self._panel_toast("Reštartujem nahrávanie…", ACCENT)
        threading.Thread(target=self._restart, daemon=True).start()

    def _restart(self):
        self._wants_to_record = False
        self._ready = False
        time.sleep(0.5)
        if not self.cfg.get("smart_record", True):
            self._start_recording()
            self._panel_toast("✔ Nahrávanie reštartované", GOOD)
        else:
            self._is_sleeping = True
            self._panel_toast("✔ Inteligentný režim aktívny", GOOD)

    def _on_hotkey(self):
        game_title = get_foreground_window_title()
        threading.Thread(target=self._save_clip, args=(game_title,), daemon=True).start()

    def _save_clip(self, game_title=""):
        if self._saving:
            return

        # On hotkey, do an immediate foreground check (helps if detector loop missed it,
        # especially right after alt-tabbing into fullscreen game)
        if self._is_sleeping and self.cfg.get("smart_record", True):
            tracked = {g.lower() for g in self.cfg.get("tracked_games", [])}
            proc_name = get_foreground_process_name()
            if proc_name:
                for g in tracked:
                    if g in proc_name or proc_name in g:
                        self._is_sleeping = False
                        if not (self.recorder and self.recorder.running):
                            self._start_recording()
                        break

        if self._is_sleeping:
            self._feedback("⚠ Zzz... Čakám na hru!", REC)
            return
        if not self._ready or not self.recorder or not self.recorder.running:
            self._feedback("⚠ Buffer nebeží!", REC)
            return
        self._saving = True
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        
        if game_title:
            safe_title = re.sub(r'[\\/*?:"<>|]', "", game_title)[:30]
            if safe_title:
                fname = f"{safe_title} - {stamp}.mp4"
            else:
                fname = f"clip_{stamp}.mp4"
        else:
            fname = f"clip_{stamp}.mp4"
            
        out = os.path.join(self.cfg["save_dir"], fname)
        self._feedback("✂ Ukladám clip…", ACCENT)
        try:
            path = self.recorder.save_clip(self.cfg["clip_seconds"], out)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            self._feedback(f"✔ Uložené ({size_mb:.1f} MB)", GOOD)
            
            monitors = get_monitors()
            cap_idx = self.cfg.get("capture_monitor", 0)
            if monitors and cap_idx < len(monitors):
                m = monitors[cap_idx]
            else:
                m = None
                
            if self.cfg.get("show_osd", False):
                osd_msg = f"✔ Clip Uložený - {game_title[:20]}" if game_title else "✔ Clip Uložený"
                self.root.after(0, show_osd, osd_msg, m)

            if self._gallery_win and self._gallery_win.winfo_exists():
                self.root.after(100, self._gallery_win._load_clips)

        except Exception as e:
            self._feedback(f"✘ {str(e)[:50]}", REC)
        finally:
            self._saving = False

    def _feedback(self, msg, color=GOOD):
        self._panel_toast(msg, color)
        _notify(self.tray, "ClipDeck", msg)

    def _panel_toast(self, msg, color=ACCENT):
        if self._gallery_win:
            self.root.after(0, self._gallery_win.flash_toast, msg, color)

    def _run_tray(self):
        try:
            import pystray
            from PIL import Image
        except ImportError:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self._quit()
            return

        ico = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png"
        )
        img = (
            Image.open(ico)
            if os.path.isfile(ico)
            else Image.new("RGB", (64, 64), "#6c63ff")
        )

        def status(item):
            if self._is_sleeping:
                return "○ Zzz... Čakám na hru"
            if self._ready and self.recorder and self.recorder.running:
                enc = self._encoder[1] if self._encoder else "?"
                return f"● REC  •  {self.cfg['fps']}fps  •  {enc}"
            return "○ Zastavené"

        menu = pystray.Menu(
            pystray.MenuItem(status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f"✂  Uložiť clip ({self.cfg['hotkey'].upper()})",
                lambda: threading.Thread(target=self._save_clip, daemon=True).start(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🖼  Otvoriť galériu",
                lambda: self.root.after(0, self._open_gallery),
                default=True,
            ),
            pystray.MenuItem(
                "⚙  Nastavenia", lambda: self.root.after(0, self._open_settings)
            ),
            pystray.MenuItem("📂  Otvoriť priečinok", lambda: self._open_folder()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌  Ukončiť", lambda: self._quit()),
        )
        self.tray = pystray.Icon("ClipDeck", img, "ClipDeck", menu)
        self.tray.run()

    def _open_folder(self):
        os.makedirs(self.cfg["save_dir"], exist_ok=True)
        os.startfile(self.cfg["save_dir"])

    def _quit(self):
        try:
            keyboard.clear_all_hotkeys()
        except Exception:
            pass
        try:
            if self.recorder:
                self.recorder.stop()
        except Exception:
            pass
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        os._exit(0)

if __name__ == "__main__":
    app = ClipDeckApp()
    app.run()
