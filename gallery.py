from __future__ import annotations

import os
import time
import math
import threading
import ctypes
import ctypes.wintypes
from datetime import datetime
import tkinter as tk
from collections import namedtuple

import customtkinter as ctk
from PIL import Image
import keyboard

import platform
import winreg
import subprocess
try:
    import psutil
except ImportError:
    psutil = None

import engine

BG = "#09090b"
BG2 = "#0c0c0f"
SIDEBAR = "#111114"
CARD = "#141419"
CARD_HVR = "#1c1c24"
CARD2 = "#1e1e26"
ACCENT = "#10b981"
ACC_HVR = "#059669"
ACC_DIM = "#0d9668"
MUTED = "#71717a"
MUTED_LT = "#a1a1aa"
TXT = "#fafafa"
TXT2 = "#d4d4d8"
BORDER = "#27272a"
DANGER = "#ef4444"
FONT = "Segoe UI"

HDR_TOP = "#0f1a15"

_user32 = ctypes.windll.user32
_SKIP_TITLES = frozenset(
    {
        "",
        "Program Manager",
        "ClipDeck",
        "ClipDeck Status",
        "Settings",
        "Microsoft Text Input Application",
        "Windows Input Experience",
        "MSCTFIME UI",
        "Default IME",
        "Windows Shell Experience Host",
    }
)

def get_foreground_title() -> str:
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return "Desktop"
    length = _user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return "Desktop"
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value.strip()
    if title in _SKIP_TITLES:
        return "Desktop"
    return title

def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent,
        fg_color=CARD,
        corner_radius=14,
        border_width=1,
        border_color="#1f1f28",
        **kw,
    )

def _section(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text.upper(), font=(FONT, 11, "bold"), text_color=ACC_DIM
    )

def _divider(parent) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, height=1, fg_color=BORDER)


# Pure helpers for monitor label/index (no tkinter deps) - canonical impl to prevent desync
def format_monitor_label(i, m, *, curr_idx=None):
    tag = ""
    if curr_idx is not None and i == curr_idx:
        tag += " ★ (Tu je okno)"
    if m.get("primary"):
        tag += " [Hlavný]"
    return f"Monitor {i + 1}: {m['w']}×{m['h']}{tag}"

def build_monitor_options(monitors, curr_idx=None):
    if not monitors:
        return ["Monitor 1: neznámy"]
    return [format_monitor_label(i, m, curr_idx=curr_idx) for i, m in enumerate(monitors)]

def resolve_monitor_index(selected_label, labels):
    """Return index for full labels list (topbar/capture_monitor)."""
    for i, lbl in enumerate(labels):
        if lbl == selected_label:
            return i
    # normalized match (handles tags)
    ns = selected_label.split(" ★")[0].strip() if " ★" in selected_label else selected_label.strip()
    for i, lbl in enumerate(labels):
        nl = lbl.split(" ★")[0].strip() if " ★" in lbl else lbl.strip()
        if nl == ns:
            return i
    return 0

def resolve_gui_monitor_index(selected_label, all_labels):
    """Return original index in monitors list for a (possibly filtered) selected label."""
    ns = selected_label.split(" ★")[0].strip() if " ★" in selected_label else selected_label.strip()
    for i, lbl in enumerate(all_labels):
        nl = lbl.split(" ★")[0].strip() if " ★" in lbl else lbl.strip()
        if nl == ns:
            return i
    return 0

def filter_gui_monitor_labels(labels):
    """Pure: return only the labels without the ★ (Tu je okno) tag for the gui menu."""
    return [lbl for lbl in labels if " ★" not in lbl]

def get_initial_gui_selection_label(mon_labels, gui_idx):
    """Pure helper: get the (clean) label to set for gui menu init, given full index from cfg."""
    gui_mon_opts = filter_gui_monitor_labels(mon_labels)
    if gui_idx < 0 or gui_idx >= len(mon_labels):
        gui_idx = 0
    candidate = mon_labels[gui_idx]
    if " ★" not in candidate:
        return candidate
    return gui_mon_opts[0] if gui_mon_opts else mon_labels[0]

# Pure builder for consistent monitor label source across UI and tests.
MonitorMenus = namedtuple("MonitorMenus", ["capture_labels", "gui_labels", "topbar_labels", "initial_capture", "initial_gui"])

def prepare_monitor_menus(monitors, *, curr_idx=None, capture_idx=0, gui_idx=0):
    if not monitors:
        labels = ["Monitor 1: neznámy"]
        return MonitorMenus(labels, labels, labels, 0, 0)
    capture_labels = build_monitor_options(monitors, curr_idx=curr_idx)
    gui_labels = filter_gui_monitor_labels(capture_labels)
    topbar_labels = build_monitor_options(monitors, curr_idx=None)  # no current tag for topbar
    cap_i = min(capture_idx, len(capture_labels)-1) if capture_labels else 0
    # compute initial_gui as position in gui_labels (not full index)
    init_label_for_gui = get_initial_gui_selection_label(capture_labels, gui_idx)
    try:
        gui_i = gui_labels.index(init_label_for_gui)
    except ValueError:
        gui_i = 0 if gui_labels else 0
    return MonitorMenus(capture_labels, gui_labels, topbar_labels, cap_i, gui_i)

def apply_topbar_capture(cfg, label, cap_labels):
    """Pure: apply topbar selection to cfg."""
    cfg = dict(cfg)
    idx = resolve_monitor_index(label, cap_labels)
    cfg["capture_monitor"] = idx
    return cfg

def apply_settings_fields(cfg, fields, cap_labels):
    """Pure: apply the settings fields (from widgets or dict) to cfg, using resolves."""
    cfg = dict(cfg)
    if "fps" in fields:
        cfg["fps"] = int(fields["fps"])
    if "clip_seconds" in fields:
        cfg["clip_seconds"] = int(fields["clip_seconds"])
    if "use_audio" in fields:
        cfg["use_audio"] = bool(fields["use_audio"])
    if "audio_bitrate" in fields:
        cfg["audio_bitrate"] = int(fields["audio_bitrate"])
    if "smart_record" in fields:
        cfg["smart_record"] = bool(fields["smart_record"])
    if "mic_device" in fields:
        cfg["mic_device"] = fields["mic_device"] or ""
    if "capture_label" in fields:
        cfg["capture_monitor"] = resolve_monitor_index(fields["capture_label"], cap_labels)
    if "gui_label" in fields:
        cfg["gui_monitor"] = resolve_gui_monitor_index(fields["gui_label"], cap_labels)
    if "save_dir" in fields:
        cfg["save_dir"] = fields["save_dir"]
    return cfg


class HWMonitor:
    def __init__(self):
        self.cpu_name = self._get_cpu_name()
        self.gpu_name = "Neznáma GPU"
        self.cpu_usage = 0.0
        self.gpu_usage = 0.0
        self._running = False
        self._thread = None
        self._get_gpu_name()

    def _get_cpu_name(self):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except Exception:
            return platform.processor()

    def _get_gpu_name(self):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True
            ).strip()
            if out:
                self.gpu_name = out.split("\n")[0]
        except Exception:
            pass

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            if psutil:
                self.cpu_usage = psutil.cpu_percent(interval=1.0)
            else:
                time.sleep(1.0)
                
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    text=True
                ).strip()
                if out:
                    self.gpu_usage = float(out.split("\n")[0])
            except Exception:
                pass

class GalleryWindow(ctk.CTkToplevel):
    def __init__(self, master, cfg: dict, monitors: list[dict], on_save_settings):
        super().__init__(master, fg_color=BG)
        self.cfg = cfg
        self.save_dir = cfg["save_dir"]
        self.monitors = monitors
        self._on_save_settings = on_save_settings

        self._recording = False
        self._start_time = 0.0
        self._blink_on = True
        self._toast_id = None

        self.hw = HWMonitor()
        self.hw.start()

        self.title("ClipDeck")
        self.geometry("1100x720")
        self.minsize(860, 620)

        ico = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico"
        )
        if os.path.isfile(ico):
            try:
                self.after(200, lambda: self.iconbitmap(ico))
            except Exception:
                pass

        def _center():
            try:
                gui_idx = self.cfg.get("gui_monitor", 0)
                if gui_idx < 0 or gui_idx >= len(self.monitors):
                    gui_idx = 0
                m = self.monitors[gui_idx]
                w, h = 1100, 720
                x = int(m["wx"] + (m["ww"] - w) / 2)
                y = int(m["wy"] + (m["wh"] - h) / 2)
                self.geometry(f"+{x}+{y}")
            except Exception:
                pass

        self.after(50, _center)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(100, self._load_clips)

    def _build(self):
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkFrame(
            self, fg_color=SIDEBAR, corner_radius=0, width=72, border_width=0
        )
        self.sidebar.grid(row=1, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        ctk.CTkFrame(self.sidebar, height=3, fg_color=ACCENT, corner_radius=0).pack(
            fill="x"
        )

        ctk.CTkFrame(self.sidebar, fg_color="transparent", height=20).pack()

        self.btn_gallery = ctk.CTkButton(
            self.sidebar,
            text="🎬",
            font=(FONT, 22),
            width=50,
            height=50,
            corner_radius=14,
            fg_color=CARD_HVR,
            hover_color=ACC_HVR,
            command=self._show_gallery,
        )
        self.btn_gallery.pack(pady=4)

        self.btn_folder = ctk.CTkButton(
            self.sidebar,
            text="📁",
            font=(FONT, 22),
            width=50,
            height=50,
            corner_radius=14,
            fg_color="transparent",
            hover_color=CARD_HVR,
            command=self._open_folder,
        )
        self.btn_folder.pack(pady=4)

        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(expand=True)

        self.btn_settings = ctk.CTkButton(
            self.sidebar,
            text="⚙",
            font=(FONT, 22),
            width=50,
            height=50,
            corner_radius=14,
            fg_color="transparent",
            hover_color=CARD_HVR,
            command=self._show_settings,
        )
        self.btn_settings.pack(pady=(4, 24))

        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=1, column=1, sticky="nsew")
        self.main_content.grid_rowconfigure(0, weight=1)
        self.main_content.grid_columnconfigure(0, weight=1)

        self._build_gallery_frame()
        self._build_settings_frame()
        self._build_status_bar()
        self._show_gallery()

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=44, fg_color=CARD2, corner_radius=0)
        self.status_bar.grid(row=0, column=0, columnspan=2, sticky="new")
        self.status_bar.grid_propagate(False)

        inner = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20)

        self.status_dot = ctk.CTkLabel(
            inner, text="●", font=(FONT, 16, "bold"), text_color=MUTED
        )
        self.status_dot.pack(side="left")

        self.status_lbl = ctk.CTkLabel(
            inner, text=" Zastavené  |", font=(FONT, 12, "bold"), text_color=MUTED
        )
        self.status_lbl.pack(side="left", padx=(4, 8))

        self.topbar_target_menu = ctk.CTkOptionMenu(
            inner,
            values=["Načítavam..."],
            width=260,
            height=30,
            font=(FONT, 12, "bold"),
            dropdown_font=(FONT, 12),
            fg_color="#18181b",
            button_color="#18181b",
            button_hover_color=ACCENT,
            corner_radius=6,
            command=self._on_topbar_target_changed,
        )
        self.topbar_target_menu.pack(side="left", padx=(0, 12))

        self.info_lbl = ctk.CTkLabel(
            inner, text="", font=(FONT, 11), text_color=MUTED_LT
        )
        self.info_lbl.pack(side="left")

        self.duration_lbl = ctk.CTkLabel(
            inner, text="--:--", font=("Consolas", 13, "bold"), text_color=MUTED
        )
        self.duration_lbl.pack(side="right")

        self.toast_lbl = ctk.CTkLabel(
            inner, text="", font=(FONT, 12, "bold"), text_color=ACCENT
        )
        self.toast_lbl.pack(side="right", padx=(0, 20))

        self._update_topbar_menu()

    def _update_topbar_menu(self):
        # Capture target is always a monitor (window/game paths removed for consistency)
        # Use prepare to have consistent labels; topbar uses capture_labels (may have curr tag, resolve handles)
        menus = prepare_monitor_menus(self.monitors, capture_idx=self.cfg.get("capture_monitor", 0))
        self.cap_mon_opts = menus.capture_labels
        opts = menus.capture_labels

        self.topbar_target_menu.configure(values=opts)

        idx = menus.initial_capture
        if 0 <= idx < len(opts):
            sel = opts[idx]
        else:
            sel = opts[0] if opts else "Monitor 1"

        self.topbar_target_menu.set(sel)

    def _on_topbar_target_changed(self, val):
        # Only monitor selection is supported and used by recorder
        self.cfg = apply_topbar_capture(self.cfg, val, self.cap_mon_opts)
        self.save_dir = self.cfg["save_dir"]
        if self._on_save_settings:
            self._on_save_settings(self.cfg)

    def _build_gallery_frame(self):
        self.gallery_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.gallery_frame.grid_rowconfigure(1, weight=1)
        self.gallery_frame.grid_columnconfigure(0, weight=1)

        self.header = ctk.CTkFrame(
            self.gallery_frame, fg_color=HDR_TOP, corner_radius=0, height=80
        )
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_propagate(False)

        hdr_inner = ctk.CTkFrame(self.header, fg_color="transparent")
        hdr_inner.pack(fill="both", expand=True, padx=28)

        title_row = ctk.CTkFrame(hdr_inner, fg_color="transparent")
        title_row.pack(fill="x", expand=True)

        ctk.CTkFrame(
            title_row, fg_color=ACCENT, width=4, height=28, corner_radius=2
        ).pack(side="left", padx=(0, 12))
        self.title_lbl = ctk.CTkLabel(
            title_row, text="Moje klipy", font=(FONT, 22, "bold"), text_color=TXT
        )
        self.title_lbl.pack(side="left")

        self.stats_badge = ctk.CTkFrame(
            title_row,
            fg_color=CARD,
            corner_radius=20,
            border_width=1,
            border_color=BORDER,
        )
        self.stats_badge.pack(side="right")
        self.stats_lbl = ctk.CTkLabel(
            self.stats_badge,
            text="  Načítavam…  ",
            font=(FONT, 12),
            text_color=MUTED_LT,
        )
        self.stats_lbl.pack(padx=14, pady=6)

        ctk.CTkFrame(
            self.gallery_frame, height=1, fg_color=ACCENT, corner_radius=0
        ).grid(row=0, column=0, sticky="sew")

        self.scroll_area = ctk.CTkScrollableFrame(
            self.gallery_frame,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        self.scroll_area.grid(row=1, column=0, sticky="nsew", padx=6, pady=(8, 6))
        self.cards = []

    def _build_settings_frame(self):
        self.settings_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")

        body = ctk.CTkScrollableFrame(
            self.settings_frame,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        body.pack(fill="both", expand=True, padx=32)

        hdr = ctk.CTkFrame(
            body,
            fg_color=HDR_TOP,
            corner_radius=14,
            border_width=1,
            border_color="#1a2a22",
        )
        hdr.pack(fill="x", pady=(12, 20))
        hdr_inner = ctk.CTkFrame(hdr, fg_color="transparent")
        hdr_inner.pack(fill="x", padx=24, pady=18)

        title_grp = ctk.CTkFrame(hdr_inner, fg_color="transparent")
        title_grp.pack(side="left")
        ctk.CTkLabel(title_grp, text="⚙", font=(FONT, 28), text_color=ACCENT).pack(
            side="left", padx=(0, 12)
        )
        t_col = ctk.CTkFrame(title_grp, fg_color="transparent")
        t_col.pack(side="left")
        ctk.CTkLabel(
            t_col, text="Nastavenia", font=(FONT, 22, "bold"), text_color=TXT
        ).pack(anchor="w")
        ctk.CTkLabel(
            t_col,
            text="Prispôsob si nahrávanie podľa seba",
            font=(FONT, 12),
            text_color=MUTED,
        ).pack(anchor="w")

        c_sys = _card(body)
        c_sys.pack(fill="x", pady=8)
        inner_sys = ctk.CTkFrame(c_sys, fg_color="transparent")
        inner_sys.pack(fill="x", padx=24, pady=20)
        _section(inner_sys, "🖥  Systém").pack(anchor="w")

        sys_row = ctk.CTkFrame(inner_sys, fg_color="transparent")
        sys_row.pack(fill="x", pady=(14, 0))

        cpu_col = ctk.CTkFrame(sys_row, fg_color="transparent")
        cpu_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(cpu_col, text="CPU: " + self.hw.cpu_name, font=(FONT, 13), text_color=TXT2).pack(anchor="w")
        self.lbl_cpu_use = ctk.CTkLabel(cpu_col, text="0%", font=(FONT, 14, "bold"), text_color=ACCENT)
        self.lbl_cpu_use.pack(anchor="w")

        gpu_col = ctk.CTkFrame(sys_row, fg_color="transparent")
        gpu_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(gpu_col, text="GPU: " + self.hw.gpu_name, font=(FONT, 13), text_color=TXT2).pack(anchor="w")
        self.lbl_gpu_use = ctk.CTkLabel(gpu_col, text="0%", font=(FONT, 14, "bold"), text_color=ACCENT)
        self.lbl_gpu_use.pack(anchor="w")
        
        def _update_hw():
            if not self.winfo_exists(): return
            self.lbl_cpu_use.configure(text=f"{int(self.hw.cpu_usage)}%")
            self.lbl_gpu_use.configure(text=f"{int(self.hw.gpu_usage)}%")
            self.after(1000, _update_hw)
        self.after(1000, _update_hw)

        def _get_curr_mon():
            try:
                wx = self.winfo_x() + self.winfo_width() // 2
                wy = self.winfo_y() + self.winfo_height() // 2
                for i, m in enumerate(self.monitors):
                    if (
                        m["x"] <= wx < m["x"] + m["w"]
                        and m["y"] <= wy < m["y"] + m["h"]
                    ):
                        return i
            except Exception:
                pass
            return -1

        curr_idx = _get_curr_mon()

        menus = prepare_monitor_menus(self.monitors, curr_idx=curr_idx, capture_idx=self.cfg.get("capture_monitor", 0), gui_idx=self.cfg.get("gui_monitor", 0))
        mon_labels = menus.capture_labels
        if not mon_labels or mon_labels == ["Monitor 1: neznámy"]:
            mon_labels = prepare_monitor_menus(self.monitors).capture_labels  # fallback via prepare
        if not mon_labels:
            mon_labels = ["Monitor 1: neznámy"]

        c_cap = _card(body)
        c_cap.pack(fill="x", pady=8)
        inner_cap = ctk.CTkFrame(c_cap, fg_color="transparent")
        inner_cap.pack(fill="x", padx=24, pady=20)
        _section(inner_cap, "🎯  Čo nahrávať").pack(anchor="w")

        sm_row = ctk.CTkFrame(inner_cap, fg_color="transparent")
        sm_row.pack(fill="x", pady=(14, 0))
        sm_left = ctk.CTkFrame(sm_row, fg_color="transparent")
        sm_left.pack(side="left")
        ctk.CTkLabel(sm_left, text="Inteligentné nahrávanie", font=(FONT, 14), text_color=TXT2).pack(anchor="w")
        ctk.CTkLabel(sm_left, text="Nahrávať iba keď hrám hru", font=(FONT, 10), text_color=MUTED).pack(anchor="w")
        
        self.smart_switch = ctk.CTkSwitch(
            sm_row, text="", width=46, progress_color=ACCENT, button_color=TXT
        )
        if self.cfg.get("smart_record", True):
            self.smart_switch.select()
        self.smart_switch.pack(side="right")

        self.games_container = ctk.CTkFrame(inner_cap, fg_color="transparent")
        self.games_container.pack(fill="x", pady=(10, 0))
        
        ctk.CTkLabel(self.games_container, text="Sledované hry", font=(FONT, 12, "bold"), text_color=TXT2).pack(anchor="w")
        
        self.games_list_frame = ctk.CTkFrame(self.games_container, fg_color=CARD2, corner_radius=8, border_width=1, border_color=BORDER)
        self.games_list_frame.pack(fill="x", pady=(6, 8))
        
        self._render_tracked_games()
        
        add_row = ctk.CTkFrame(self.games_container, fg_color="transparent")
        add_row.pack(fill="x")
        
        self.new_game_entry = ctk.CTkEntry(add_row, placeholder_text="napr. hl2.exe", height=32, font=(FONT, 13), fg_color=CARD2, border_color=BORDER)
        self.new_game_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        
        ctk.CTkButton(
            add_row, text="+ Pridať", width=80, height=32, font=(FONT, 12, "bold"), 
            fg_color=ACCENT, text_color="#000", hover_color=ACC_HVR,
            command=self._add_game_action
        ).pack(side="right")

        _divider(inner_cap).pack(fill="x", pady=(14, 0))

        self.monitor_frame = ctk.CTkFrame(inner_cap, fg_color="transparent")

        mon_row = ctk.CTkFrame(self.monitor_frame, fg_color="transparent")
        mon_row.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(mon_row, text="Monitor", font=(FONT, 14), text_color=TXT2).pack(
            side="left"
        )

        self.cap_mon_opts = menus.capture_labels
        cap_idx = menus.initial_capture
        self.cap_mon_menu = ctk.CTkOptionMenu(
            mon_row,
            values=menus.capture_labels,
            width=300,
            height=38,
            font=(FONT, 13),
            dropdown_font=(FONT, 12),
            fg_color=CARD2,
            button_color=CARD2,
            button_hover_color=ACCENT,
            corner_radius=10,
        )
        self.cap_mon_menu.set(menus.capture_labels[cap_idx] if menus.capture_labels else "Monitor 1")
        self.cap_mon_menu.pack(side="right")

        self.monitor_frame.pack(fill="x")

        c0 = _card(body)
        c0.pack(fill="x", pady=8)
        inner0 = ctk.CTkFrame(c0, fg_color="transparent")
        inner0.pack(fill="x", padx=24, pady=20)
        _section(inner0, "🖥  Status panel").pack(anchor="w")

        grow = ctk.CTkFrame(inner0, fg_color="transparent")
        grow.pack(fill="x", pady=(14, 0))
        gui_left = ctk.CTkFrame(grow, fg_color="transparent")
        gui_left.pack(side="left")
        ctk.CTkLabel(
            gui_left, text="Aplikácia (Hlavné okno)", font=(FONT, 14), text_color=TXT2
        ).pack(anchor="w")
        ctk.CTkLabel(
            gui_left, text="Kde sa zobrazí aplikácia", font=(FONT, 10), text_color=MUTED
        ).pack(anchor="w")

        gui_mon_opts = menus.gui_labels
        gui_idx_in_gui = menus.initial_gui if 0 <= menus.initial_gui < len(gui_mon_opts) else 0
        gui_sel = gui_mon_opts[gui_idx_in_gui] if gui_mon_opts else mon_labels[0]

        self.gui_menu = ctk.CTkOptionMenu(
            grow,
            values=gui_mon_opts,
            width=300,
            height=38,
            font=(FONT, 13),
            dropdown_font=(FONT, 12),
            fg_color=CARD2,
            button_color=CARD2,
            button_hover_color=ACCENT,
            corner_radius=10,
        )
        self.gui_menu.set(gui_sel)
        self.gui_menu.pack(side="right")

        c1 = _card(body)
        c1.pack(fill="x", pady=8)
        inner1 = ctk.CTkFrame(c1, fg_color="transparent")
        inner1.pack(fill="x", padx=24, pady=20)
        _section(inner1, "🎥  Kvalita nahrávania").pack(anchor="w")

        frow = ctk.CTkFrame(inner1, fg_color="transparent")
        frow.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(frow, text="FPS (144 = najkvalitnejšie)", font=(FONT, 14), text_color=TXT2).pack(
            side="left"
        )
        self.fps_seg = ctk.CTkSegmentedButton(
            frow,
            values=["30", "60", "90", "120", "144"],
            font=(FONT, 12),
            selected_color=ACCENT,
            selected_hover_color=ACC_HVR,
            unselected_color=CARD2,
            unselected_hover_color=CARD_HVR,
            width=220,
            corner_radius=10,
        )
        self.fps_seg.set(str(self.cfg.get("fps", 144)))
        self.fps_seg.pack(side="right")

        _divider(inner1).pack(fill="x", pady=(18, 0))

        qrow = ctk.CTkFrame(inner1, fg_color="transparent")
        qrow.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(qrow, text="Kvalita videa", font=(FONT, 14), text_color=TXT2).pack(
            side="left"
        )

        self.q_value = ctk.CTkLabel(
            qrow,
            font=(FONT, 14, "bold"),
            text_color=ACCENT,
            text="Max (HEVC/H264 144fps VBR+AQ)",
        )
        self.q_value.pack(side="right")

        _divider(inner1).pack(fill="x", pady=(14, 0))

        arow = ctk.CTkFrame(inner1, fg_color="transparent")
        arow.pack(fill="x", pady=(16, 0))
        a_left = ctk.CTkFrame(arow, fg_color="transparent")
        a_left.pack(side="left")
        ctk.CTkLabel(a_left, text="Zvuk hry", font=(FONT, 14), text_color=TXT2).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            a_left, text="WASAPI loopback", font=(FONT, 10), text_color=MUTED
        ).pack(anchor="w")
        self.audio_switch = ctk.CTkSwitch(
            arow, text="", width=46, progress_color=ACCENT, button_color=TXT
        )
        if self.cfg["use_audio"]:
            self.audio_switch.select()
        if not engine.AudioPump.available():
            self.audio_switch.configure(state="disabled")
        self.audio_switch.pack(side="right")

        mic_row = ctk.CTkFrame(inner1, fg_color="transparent")
        mic_row.pack(fill="x", pady=(14, 0))
        m_left = ctk.CTkFrame(mic_row, fg_color="transparent")
        m_left.pack(side="left")
        ctk.CTkLabel(m_left, text="Mikrofón", font=(FONT, 14), text_color=TXT2).pack(anchor="w")
        ctk.CTkLabel(m_left, text="Zmixuje hlas do videa", font=(FONT, 10), text_color=MUTED).pack(anchor="w")
        
        mic_opts = self._get_dshow_audio_devices()
        self.mic_menu = ctk.CTkOptionMenu(
            mic_row,
            values=mic_opts,
            width=200,
            height=32,
            font=(FONT, 12),
            dropdown_font=(FONT, 11),
            fg_color=CARD2,
            button_color=CARD2,
            button_hover_color=ACCENT,
            corner_radius=8,
        )
        saved_mic = self.cfg.get("mic_device", "Žiadny (Iba hra)")
        if saved_mic in mic_opts:
            self.mic_menu.set(saved_mic)
        else:
            self.mic_menu.set(mic_opts[0])
        self.mic_menu.pack(side="right")

        abrow = ctk.CTkFrame(inner1, fg_color="transparent")
        abrow.pack(fill="x", pady=(14, 0))
        ctk.CTkLabel(
            abrow, text="Audio bitrate", font=(FONT, 13), text_color=MUTED
        ).pack(side="left")
        self.ab_seg = ctk.CTkSegmentedButton(
            abrow,
            values=["128", "192", "256", "320"],
            font=(FONT, 12),
            selected_color=ACCENT,
            selected_hover_color=ACC_HVR,
            unselected_color=CARD2,
            unselected_hover_color=CARD_HVR,
            width=240,
            corner_radius=10,
        )
        self.ab_seg.set(str(self.cfg.get("audio_bitrate", 320)))
        self.ab_seg.pack(side="right")

        c2 = _card(body)
        c2.pack(fill="x", pady=8)
        inner2 = ctk.CTkFrame(c2, fg_color="transparent")
        inner2.pack(fill="x", padx=24, pady=20)
        _section(inner2, "✂  Clip").pack(anchor="w")

        drow = ctk.CTkFrame(inner2, fg_color="transparent")
        drow.pack(fill="x", pady=(16, 0))
        ctk.CTkLabel(drow, text="Dĺžka clipu (s)", font=(FONT, 14), text_color=TXT2).pack(
            side="left"
        )
        self.clip_seg = ctk.CTkSegmentedButton(
            drow,
            values=["15", "30", "60", "90", "120"],
            font=(FONT, 12),
            selected_color=ACCENT,
            selected_hover_color=ACC_HVR,
            unselected_color=CARD2,
            unselected_hover_color=CARD_HVR,
            width=200,
            corner_radius=10,
        )
        self.clip_seg.set(str(self.cfg.get("clip_seconds", 30)))
        self.clip_seg.pack(side="right")

        _divider(inner2).pack(fill="x", pady=(18, 0))

        hkrow = ctk.CTkFrame(inner2, fg_color="transparent")
        hkrow.pack(fill="x", pady=(16, 0))
        hk_left = ctk.CTkFrame(hkrow, fg_color="transparent")
        hk_left.pack(side="left")
        ctk.CTkLabel(hk_left, text="Hotkey", font=(FONT, 14), text_color=TXT2).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            hk_left, text="Klikni a stlač klávesy", font=(FONT, 10), text_color=MUTED
        ).pack(anchor="w")
        self.hk_btn = ctk.CTkButton(
            hkrow,
            text=self.cfg["hotkey"].upper(),
            width=150,
            height=40,
            font=(FONT, 15, "bold"),
            fg_color=CARD2,
            hover_color=ACCENT,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
            command=self._grab_hotkey,
        )
        self.hk_btn.pack(side="right")

        c3 = _card(body)
        c3.pack(fill="x", pady=8)
        inner3 = ctk.CTkFrame(c3, fg_color="transparent")
        inner3.pack(fill="x", padx=24, pady=20)
        _section(inner3, "📁  Kam ukladať klipy").pack(anchor="w")

        ctk.CTkLabel(
            inner3,
            text="Priečinok na disku kde sa uložia tvoje videá",
            font=(FONT, 11),
            text_color=MUTED,
        ).pack(anchor="w", pady=(4, 0))

        dir_row = ctk.CTkFrame(inner3, fg_color="transparent")
        dir_row.pack(fill="x", pady=(12, 0))

        path_frame = ctk.CTkFrame(
            dir_row,
            fg_color=CARD2,
            corner_radius=10,
            border_width=1,
            border_color=BORDER,
        )
        path_frame.pack(side="left", fill="x", expand=True)
        path_inner = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_inner.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(path_inner, text="📂", font=(FONT, 14)).pack(side="left")
        self.dir_lbl = ctk.CTkLabel(
            path_inner,
            text=self.cfg["save_dir"],
            font=(FONT, 12),
            text_color=MUTED_LT,
            anchor="w",
            wraplength=360,
        )
        self.dir_lbl.pack(side="left", padx=(8, 0), fill="x", expand=True)

        ctk.CTkButton(
            dir_row,
            text="Zmeniť",
            width=100,
            height=38,
            font=(FONT, 13, "bold"),
            fg_color=ACCENT,
            hover_color=ACC_HVR,
            text_color="#000",
            corner_radius=10,
            command=self._pick_dir,
        ).pack(side="right", padx=(12, 0))

        ctk.CTkButton(
            inner3,
            text="📁 Otvoriť priečinok",
            width=180,
            height=32,
            font=(FONT, 12),
            fg_color="transparent",
            hover_color=CARD_HVR,
            text_color=MUTED_LT,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
            command=self._open_folder,
        ).pack(anchor="w", pady=(10, 0))

        ctk.CTkButton(
            body,
            text="💾  Uložiť nastavenia",
            height=56,
            font=(FONT, 16, "bold"),
            corner_radius=14,
            fg_color=ACCENT,
            hover_color=ACC_HVR,
            text_color="#000",
            command=self._save_settings_action,
        ).pack(fill="x", pady=(24, 30))

    def _show_gallery(self):
        self.btn_settings.configure(fg_color="transparent")
        self.btn_gallery.configure(fg_color=CARD_HVR)
        self.settings_frame.grid_forget()
        self.gallery_frame.grid(row=0, column=0, sticky="nsew")
        self._load_clips()

    def _show_settings(self):
        self.btn_gallery.configure(fg_color="transparent")
        self.btn_settings.configure(fg_color=CARD_HVR)
        self.gallery_frame.grid_forget()
        self.settings_frame.grid(row=0, column=0, sticky="nsew")

    def _open_folder(self):
        os.makedirs(self.save_dir, exist_ok=True)
        os.startfile(self.save_dir)

    def _load_clips(self):
        for w in self.cards:
            w.destroy()
        self.cards.clear()

        if hasattr(self, "_empty_msg") and self._empty_msg:
            self._empty_msg.destroy()
            self._empty_msg = None

        if not os.path.isdir(self.save_dir):
            self.stats_lbl.configure(text="  0 klipov  ")
            return

        clips = []
        total_size = 0
        for f in os.listdir(self.save_dir):
            if f.endswith(".mp4"):
                path = os.path.join(self.save_dir, f)
                try:
                    stat = os.stat(path)
                    size = stat.st_size
                    total_size += size
                    clips.append(
                        {
                            "filename": f,
                            "path": path,
                            "size": size,
                            "time": stat.st_mtime,
                        }
                    )
                except OSError:
                    pass

        clips.sort(key=lambda x: x["time"], reverse=True)

        sz_mb = total_size / (1024 * 1024)
        sz_gb = sz_mb / 1024
        size_str = f"{sz_gb:.1f} GB" if sz_gb > 1 else f"{sz_mb:.1f} MB"
        self.stats_lbl.configure(text=f"  {len(clips)} Klipov  •  {size_str}  ")

        if not clips:
            empty_frame = ctk.CTkFrame(self.scroll_area, fg_color="transparent")
            empty_frame.grid(row=0, column=0, pady=80, padx=20, sticky="n")
            self.scroll_area.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(empty_frame, text="🎮", font=(FONT, 52)).pack()
            ctk.CTkLabel(
                empty_frame,
                text="Zatiaľ žiadne klipy",
                font=(FONT, 20, "bold"),
                text_color=TXT2,
            ).pack(pady=(12, 4))
            ctk.CTkLabel(
                empty_frame,
                text="Zapni hru, spusti nahrávanie a stlač hotkey!",
                font=(FONT, 13),
                text_color=MUTED,
            ).pack()

            self._empty_msg = empty_frame
            return

        cols = 3
        for i, clip in enumerate(clips):
            r = i // cols
            c = i % cols

            card = ctk.CTkFrame(
                self.scroll_area,
                fg_color=CARD,
                corner_radius=14,
                border_width=1,
                border_color="#1f1f28",
            )
            card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            self.scroll_area.grid_columnconfigure(c, weight=1)

            thumb_container = ctk.CTkFrame(
                card, fg_color="#000000", corner_radius=12, height=180
            )
            thumb_container.pack(fill="x", padx=3, pady=(3, 0))
            thumb_container.pack_propagate(False)

            thumb_path = clip["path"].rsplit(".", 1)[0] + ".jpg"
            img_obj = None
            if os.path.isfile(thumb_path):
                try:
                    img = Image.open(thumb_path)
                    img_obj = ctk.CTkImage(
                        light_image=img, dark_image=img, size=(320, 180)
                    )
                except Exception:
                    pass

            if img_obj:
                img_lbl = ctk.CTkLabel(thumb_container, text="", image=img_obj)
            else:
                img_lbl = ctk.CTkLabel(
                    thumb_container,
                    text="🎬 Náhľad nedostupný",
                    width=320,
                    height=180,
                    fg_color="#0a0a0a",
                    text_color=MUTED,
                    font=(FONT, 13),
                )
            img_lbl.pack(fill="both", expand=True)

            c_sz_mb = clip["size"] / (1024 * 1024)
            ctk.CTkLabel(
                thumb_container,
                text=f" {c_sz_mb:.1f} MB ",
                font=(FONT, 10, "bold"),
                fg_color="#000000",
                text_color=MUTED_LT,
                corner_radius=6,
            ).place(relx=1.0, rely=0.0, anchor="ne", x=-8, y=8)

            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(fill="both", expand=True, padx=14, pady=(10, 12))

            title_lbl = ctk.CTkLabel(
                info_frame,
                text=clip["filename"],
                font=(FONT, 13, "bold"),
                text_color=TXT,
            )
            title_lbl.pack(anchor="w")

            date_str = datetime.fromtimestamp(clip["time"]).strftime("%d. %b %H:%M")
            meta_lbl = ctk.CTkLabel(
                info_frame, text=f"📅 {date_str}", font=(FONT, 11), text_color=MUTED
            )
            meta_lbl.pack(anchor="w", pady=(2, 10))

            action_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            action_frame.pack(fill="x", side="bottom")

            ctk.CTkButton(
                action_frame,
                text="▶ Prehrať",
                font=(FONT, 12, "bold"),
                width=90,
                height=30,
                fg_color=ACCENT,
                hover_color=ACC_HVR,
                text_color="#000",
                corner_radius=8,
                command=lambda p=clip["path"]: os.startfile(p),
            ).pack(side="left")

            ctk.CTkButton(
                action_frame,
                text="🗑",
                font=(FONT, 13),
                width=34,
                height=30,
                fg_color="transparent",
                hover_color=DANGER,
                text_color=MUTED,
                corner_radius=8,
                border_width=1,
                border_color=BORDER,
                command=lambda p=clip["path"], w=card: self._delete_clip(p, w),
            ).pack(side="right")

            def enter(e, c=card):
                c.configure(fg_color=CARD_HVR, border_color=ACCENT)

            def leave(e, c=card):
                c.configure(fg_color=CARD, border_color="#1f1f28")

            for widget in (
                card,
                img_lbl,
                info_frame,
                title_lbl,
                meta_lbl,
                action_frame,
            ):
                widget.bind("<Enter>", enter)
            card.bind("<Leave>", leave)

            img_lbl.bind("<Button-1>", lambda e, p=clip["path"]: os.startfile(p))
            img_lbl.configure(cursor="hand2")

            self.cards.append(card)

    def _delete_clip(self, path, card_widget):
        try:
            os.remove(path)
            thumb = path.rsplit(".", 1)[0] + ".jpg"
            if os.path.isfile(thumb):
                os.remove(thumb)
            self.after(50, self._load_clips)
        except Exception:
            pass

    def _get_dshow_audio_devices(self):
        import subprocess
        ff = engine.find_ffmpeg() or "ffmpeg"
        cmd = [ff, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            devices = ["Žiadny (Iba hra)"]
            for line in res.stderr.splitlines():
                if '"' in line and "(audio)" in line and "Alternative name" not in line:
                    parts = line.split('"')
                    if len(parts) >= 3:
                        devices.append(parts[1])
            return devices
        except:
            return ["Žiadny (Iba hra)"]

    def _render_tracked_games(self):
        for widget in self.games_list_frame.winfo_children():
            widget.destroy()
            
        games = self.cfg.get("tracked_games", [])
        if not games:
            ctk.CTkLabel(self.games_list_frame, text="Žiadne hry v zozname.", font=(FONT, 12), text_color=MUTED).pack(pady=8)
            return
            
        for g in games:
            row = ctk.CTkFrame(self.games_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(row, text=g, font=(FONT, 13), text_color=TXT).pack(side="left")
            ctk.CTkButton(
                row, text="🗑", width=28, height=24, fg_color="transparent", text_color=DANGER, 
                hover_color=CARD, command=lambda x=g: self._remove_game_action(x)
            ).pack(side="right")

    def _add_game_action(self):
        name = self.new_game_entry.get().strip()
        if not name:
            return
        if not name.lower().endswith(".exe"):
            name += ".exe"
            
        games = self.cfg.get("tracked_games", [])
        if name not in games:
            games.append(name)
            self.cfg["tracked_games"] = games
            self.new_game_entry.delete(0, "end")
            self._render_tracked_games()
            if self._on_save_settings:
                self._on_save_settings(self.cfg)

    def _remove_game_action(self, name):
        games = self.cfg.get("tracked_games", [])
        if name in games:
            games.remove(name)
            self.cfg["tracked_games"] = games
            self._render_tracked_games()
            if self._on_save_settings:
                self._on_save_settings(self.cfg)

    def _grab_hotkey(self):
        self.hk_btn.configure(text="stlač klávesy…", state="disabled")

        def grab():
            try:
                combo = keyboard.read_hotkey(suppress=False)
            except Exception:
                combo = self.cfg["hotkey"]
            self.after(0, self._set_hk, combo)

        threading.Thread(target=grab, daemon=True).start()

    def _set_hk(self, combo):
        self.cfg["hotkey"] = combo
        self.hk_btn.configure(text=combo.upper(), state="normal")

    def _pick_dir(self):
        from tkinter import filedialog

        d = filedialog.askdirectory(initialdir=self.cfg["save_dir"])
        if d:
            self.cfg["save_dir"] = d
            self.save_dir = d
            self.dir_lbl.configure(text=d)

    def _save_settings_action(self):
        fields = {
            "fps": int(self.fps_seg.get()),
            "clip_seconds": int(self.clip_seg.get()),
            "use_audio": bool(self.audio_switch.get()),
            "audio_bitrate": int(self.ab_seg.get()),
            "smart_record": bool(self.smart_switch.get()),
            "mic_device": self.mic_menu.get() or "",
            "capture_label": self.cap_mon_menu.get(),
            "gui_label": self.gui_menu.get(),
            "save_dir": self.save_dir,
        }
        self.cfg = apply_settings_fields(self.cfg, fields, self.cap_mon_opts)
        self.save_dir = self.cfg["save_dir"]

        if self._on_save_settings:
            self._on_save_settings(self.cfg)

        self._show_gallery()

    def destroy(self):
        if hasattr(self, "hw"):
            self.hw.stop()
        super().destroy()

    def set_recording(self, is_rec: bool, encoder: str = "?", resolution: str = "?", fps: int = 60):
        self._recording = is_rec
        self._start_time = time.time() if is_rec else 0.0
        if is_rec:
            self.status_dot.configure(text_color=DANGER)
            self.status_lbl.configure(text=" Nahrávam  |", text_color=DANGER)
            self.info_lbl.configure(text=f"📺 {resolution}  •  {fps}fps  •  {encoder}")
            self._blink()
        else:
            self.status_dot.configure(text_color=MUTED)
            self.status_lbl.configure(text=" Zastavené  |", text_color=MUTED)
            self.duration_lbl.configure(text="--:--", text_color=MUTED)

    def update_game(self):
        title = get_foreground_title()
        if len(title) > 35:
            title = title[:33] + "…"
        # capture is monitor-based; title shown in status elsewhere
        if self._recording and self.winfo_exists():
            self.after(2000, self.update_game)

    def flash_toast(self, text: str, color: str = ACCENT):
        self.toast_lbl.configure(text=text, text_color=color)
        if self._toast_id:
            self.after_cancel(self._toast_id)
        self._toast_id = self.after(5000, self._clear_toast)

    def _clear_toast(self):
        self.toast_lbl.configure(text="")
        self._toast_id = None

    def _blink(self):
        if not self._recording or not self.winfo_exists():
            return
        self._blink_on = not self._blink_on
        self.status_dot.configure(text_color=DANGER if self._blink_on else BG)
        elapsed = int(time.time() - self._start_time)
        m, s = divmod(elapsed, 60)
        self.duration_lbl.configure(text=f"{m:02d}:{s:02d}", text_color=TXT)
        self.after(800, self._blink)
