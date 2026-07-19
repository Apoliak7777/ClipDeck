<div align="center">

[![Slovenčina](https://img.shields.io/badge/SK-Sloven%C4%8Dina-30363d?style=for-the-badge)](README.md) [![English](https://img.shields.io/badge/EN-English-2ea043?style=for-the-badge)](README.en.md)

</div>

<div align="center">

# 🎬 ClipDeck

**Instant-replay clipper for Windows - runs in the background, saves the last N seconds of your game with a single key.**

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-only-0078D6?style=flat-square&logo=windows&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-gdigrab%20%2B%20NVENC-007808?style=flat-square&logo=ffmpeg&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-1f6feb?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

</div>

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Installation](#-installation)
- [Build .exe](#-build-exe)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [How It Works](#-how-it-works)
- [Tests](#-tests)
- [Known Limitations](#-known-limitations)
- [License](#-license)

---

## 🧭 Overview

ClipDeck is a game-moment clipper in the style of Medal or ShadowPlay. In the background it keeps a single long-running FFmpeg process that captures the selected monitor (`gdigrab`) plus system audio (WASAPI loopback) into a ring buffer of 1-second MPEG-TS segments on disk.

When the global hotkey (`F4` by default) is pressed, the most recent segments are joined into an `.mp4` via `concat -c copy`. No re-encoding means saving is instant and lossless - and because the ring is bounded, disk usage stays constant no matter how long the app has been running.

The app lives in the system tray and has a dark CustomTkinter window with a clip gallery and settings. In smart mode the buffer switches itself on only when a tracked game process is running.

---

## ✨ Features

- ⚡ **Instant clip saving** - `concat -c copy` with no re-encoding, the clip lands on disk practically immediately and in its original quality.
- 🔁 **Fixed-size rolling buffer** - the `segment` muxer writes 1-second `.ts` files, the ring holds `clip_seconds + 6` (minimum 8) segments.
- ⌨️ **Global hotkey** - `F4` by default, rebindable directly in the app via `keyboard.read_hotkey()`.
- 🎮 **Smart recording** - a loop scans processes every 3 seconds and enables the buffer only when a tracked game is running. The game list is editable in the UI.
- 🚀 **Automatic encoder detection** - the chain `hevc_nvenc` → `h264_nvenc` → `h264_qsv` → `h264_amf` → `libx264`, each with its own quality parameters.
- 📥 **FFmpeg auto-download** - on first launch a static build is downloaded and extracted into `%LOCALAPPDATA%\ClipDeck\bin\`.
- 🖥️ **Multi-monitor support** - choose which monitor is recorded and, separately, which one shows the app window.
- 🔊 **System audio plus microphone** - WASAPI loopback (callback mode) is mixed with an optional DirectShow microphone via `amix`.
- 🖼️ **Clip gallery** - a card grid with automatically generated JPG thumbnails, size, date, click-to-play and deletion.
- 🔔 **OSD toast that does not steal focus** - a borderless topmost window with `WS_EX_NOACTIVATE` so a fullscreen game does not get kicked out. Disabled by default and can only be enabled by editing `config.json` by hand - there is no control for it in the UI.
- 🏷️ **Naming based on the game** - the clip name is taken from the active window title, e.g. `Game Title - 2026-07-19_14-30-00.mp4`.
- 🩺 **Watchdog** - checks the buffer state every 2 seconds and, after an FFmpeg crash, launches one restart attempt. The watchdog loop is not rescheduled in the process, so after this single attempt it stops running until the app is restarted.
- 📊 **Live CPU and GPU usage** - in the settings via `psutil` and `nvidia-smi`.

---

## 📦 Installation

> **Windows only.** The code uses `ctypes.windll`, `winreg`, `gdigrab`, `dshow`, WASAPI loopback and `os.startfile`. On Linux or macOS the modules will not even import.

Running from source in the repository root folder:

```powershell
pip install -r requirements.txt
python clipdeck.py
```

That is all - no server, database or API key. The app starts hidden, opens the gallery window after roughly 500 ms and installs the tray icon.

> [!NOTE]
> The Python version is not enforced anywhere in the repository - there is no `pyproject.toml`, no `python_requires` and no runtime check. The only real lower bound in the code is `shlex.join` (`engine.py`), i.e. **Python 3.8+**. Modern type annotations such as `str | None` and `list[dict]` are neutralized in all three modules via `from __future__ import annotations`, so they are not evaluated at runtime. `build.ps1` nevertheless tries Python 3.13 as its first option.

> [!NOTE]
> On first launch `engine.ensure_ffmpeg()` downloads a static FFmpeg build from `gyan.dev`, so the first start needs an internet connection - unless you already have `ffmpeg` in your `PATH`.

> [!IMPORTANT]
> Run the app **as administrator**. Otherwise the `keyboard` library will not receive the global hotkey when focus belongs to a game running with elevated privileges or in exclusive fullscreen. That is why the build script adds `--uac-admin`.

---

## 🔨 Build .exe

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

The script first runs `python make_icon.py` (regenerates the icons), then calls PyInstaller in one-file / windowed mode. The output is `dist\ClipDeck.exe`.

> [!WARNING]
> `pyinstaller` is **not** in `requirements.txt`, it has to be installed separately (`pip install pyinstaller`). On top of that, `build.ps1` first tries a hardcoded path to Python 3.13 and only then `python` from `PATH`.

---

## 📁 Project Structure

```text
ClipDeck/
├── clipdeck.py          # Entry point. ClipDeckApp: boot, ffmpeg bootstrap, encoder
│                        # detection, game detection loop, hotkey, watchdog, tray menu.
│                        # Contains DEFAULTS, load/save_config, get_monitors(),
│                        # OSDNotification and the pure build_recorder_start_cfg().
├── engine.py            # Recording core with no UI. Recorder (ffmpeg command, save_clip,
│                        # _tail_segments, _janitor), AudioPump (WASAPI loopback),
│                        # find_ffmpeg/ensure_ffmpeg, detect_encoder, generate_thumbnail.
├── gallery.py           # The entire GUI. GalleryWindow (sidebar, clip grid, settings),
│                        # HWMonitor (CPU/GPU) and the pure helpers apply_settings_fields,
│                        # apply_topbar_capture and prepare_monitor_menus, which the tests
│                        # import directly (resolve_monitor_index is only called indirectly).
├── make_icon.py         # Generates assets/icon.ico (7 sizes) and icon.png via Pillow.
├── build.ps1            # Regenerates the icon and runs PyInstaller (onefile, windowed, UAC).
├── requirements.txt     # customtkinter, keyboard, pystray, Pillow, PyAudioWPatch, psutil
├── tests/
│   └── test_engine.py   # unittest: _tail_segments, save_clip (mocked subprocess)
│                        # and the config flow apply_settings_fields -> build_recorder_start_cfg.
├── assets/              # icon.ico and icon.png (generated, for tray, window and exe)
└── LICENSE              # MIT
```

---

## 🔧 Configuration

Settings are stored in `%LOCALAPPDATA%\ClipDeck\config.json`. The file is merged on top of `DEFAULTS`; a corrupted or missing file silently falls back to the default values. The configuration cannot be driven by environment variables or a `.env` file; the only variable read directly is `LOCALAPPDATA` (in `engine.app_data_dir()`), which determines the location of the data folder - and indirectly `USERPROFILE` via `os.path.expanduser("~")` for the default `save_dir`.

| Key               | Default                         | Options in the UI              | Description                                                 |
| :---------------- | :------------------------------ | :----------------------------- | :---------------------------------------------------------- |
| `fps`             | `144`                           | 30 / 60 / 90 / 120 / 144       | Capture frame rate                                          |
| `clip_seconds`    | `30`                            | 15 / 30 / 60 / 90 / 120        | Length of the saved clip in seconds                         |
| `use_audio`       | `true`                          | toggle                         | System audio via WASAPI loopback                            |
| `audio_bitrate`   | `320`                           | 128 / 192 / 256 / 320          | AAC bitrate in kbps                                         |
| `hotkey`          | `"f4"`                          | any combination                | Hotkey for saving a clip                                    |
| `save_dir`        | `%USERPROFILE%\Videos\ClipDeck` | folder picker                  | Where `.mp4` and `.jpg` files are stored                    |
| `capture_monitor` | `0`                             | monitor list                   | Index of the recorded monitor (primary first)               |
| `gui_monitor`     | `1`                             | monitor list                   | Which monitor the app window is centered on                 |
| `show_osd`        | `false`                         | only manually in `config.json` | OSD toast after saving a clip (no control for it in the UI) |
| `smart_record`    | `true`                          | toggle                         | Record only when a tracked game is running                  |
| `tracked_games`   | 10 games                        | editor in the UI               | List of `.exe` names (cs2, valorant, gta5 and others)       |
| `mic_device`      | not in `DEFAULTS`               | DirectShow list                | Microphone name, an empty string means no microphone        |

### Runtime paths

| Path                                     | Contents                                         |
| :--------------------------------------- | :----------------------------------------------- |
| `%LOCALAPPDATA%\ClipDeck\config.json`    | Settings                                         |
| `%LOCALAPPDATA%\ClipDeck\bin\ffmpeg.exe` | Automatically downloaded FFmpeg                  |
| `%LOCALAPPDATA%\ClipDeck\buffer\`        | Ring of `seg*.ts` segments and `buffer.m3u8`     |
| `save_dir`                               | `.mp4` clips and their sibling `.jpg` thumbnails |

---

## 🔬 How It Works

| Step           | What happens                                                                                                   |
| :------------- | :------------------------------------------------------------------------------------------------------------- |
| 1. Capture     | `ffmpeg -f gdigrab -framerate <fps>` with `-offset_x`, `-offset_y` and `-video_size` for the chosen monitor    |
| 2. Audio       | `AudioPump` pumps WASAPI loopback in callback mode and writes raw `s16le` PCM into FFmpeg's `stdin`            |
| 3. Encoding    | The first available encoder from the table, NVENC runs with `-rc vbr -cq 8 -preset p7 -tune hq`                |
| 4. Buffer      | The `segment` muxer writes `seg%08d.ts` one second at a time and maintains `buffer.m3u8`                       |
| 5. Maintenance | The janitor thread deletes segments older than `ring + 4` so that clipping never races with deletion           |
| 6. Saving      | `_tail_segments()` reads the playlist, copies only the needed tail and runs `concat -c copy` with `+faststart` |
| 7. Thumbnail   | A frame from `00:00:02` (fallback `00:00:00`) is saved as a `.jpg` next to the clip                            |

After the buffer starts, the app waits up to 12 seconds for at least 3 non-empty segments. If `gdigrab` delivers no frames, startup ends with an understandable error recommending you lower the FPS or turn off audio.

---

## 🧪 Tests

From the repository root folder, so that the `engine`, `clipdeck` and `gallery` modules are importable:

```powershell
python -m unittest discover -s tests -v
```

The tests cover `_tail_segments` (happy path, skipping zero-length segments, empty and short playlist), `save_clip` (empty buffer, the concat and thumbnail calls with a mocked `subprocess`, concat failure) and the configuration flow from `apply_settings_fields` through `build_recorder_start_cfg` all the way to the ring size calculation.

> [!WARNING]
> The tests are not CI-friendly. They import `clipdeck` and `gallery`, which already call `ctypes.windll` and the CustomTkinter initialization at import time, so they require Windows and all the GUI dependencies. The repository contains neither `tests/__init__.py` nor any CI configuration.

---

## 📋 Known Limitations

- 🪟 **Windows exclusively.** There is no branch for Linux or macOS.
- 🛡️ **FFmpeg is downloaded without verification.** The binary from `gyan.dev` is downloaded over HTTPS without a checksum or signature check and then executed.
- 🩺 **The watchdog stops after the first restart.** The failure branch in `_watchdog()` launches `_start_recording` in a new thread, but does not reschedule itself via `root.after(2000, ...)`, and `_start_recording` does not set the timer up again because the `_watchdog_started` flag is already `True` at that point.
- 🎤 **Bug in the "no microphone" item.** The `Žiadny (Iba hra)` option is stored into `mic_device` literally as a string, `engine.py` treats it as a real device and FFmpeg receives `-f dshow -i audio=Žiadny (Iba hra)`. It only works because `clipdeck.py` catches the `dshow` failure, shows a warning and starts again without a microphone - i.e. one pointless attempt on every buffer start.
- 🔔 **`show_osd` has no control.** The key exists in `DEFAULTS` as well as in `_save_clip`, but the settings only build toggles for `smart_record` and `use_audio`. OSD can be enabled exclusively by editing `config.json` by hand.
- 🖨️ **Debug `print`.** The line `print("FFMPEG CMD:", ...)` was left in `engine.Recorder.start()`. In a `--windowed` build it is harmless, when running from source it is noisy.
- 🪟 **Console flash.** `_get_dshow_audio_devices()` in `gallery.py` calls `subprocess.run` without `CREATE_NO_WINDOW`, so opening the settings may briefly flash a console window.
- 🗑️ **Clip deletion is immediate and silent** - `os.remove` on both the `.mp4` and the `.jpg`, without confirmation and without a recycle bin.
- 🔥 **144 FPS is demanding.** Continuous encoding at the default 144 fps fills `%LOCALAPPDATA%` with a steady stream of segments. Without NVENC the chain falls all the way down to `libx264 -preset fast -crf 10`, which puts a heavy load on the CPU.
- 🎯 **`gdigrab` does not reliably capture true exclusive fullscreen.** This is a limitation of the desktop grabber, not something the app can work around.
- 🌍 **The entire UI, tray menu and error messages are in Slovak only.** There is no localization layer.
- 🔎 **`smart_record` matches the existence of a process anywhere in the system**, not the active window, and uses loose bidirectional substring comparison (`g in n or n in g`), which can produce false matches with short `.exe` names.
- 📦 **No packaging metadata** - the repository contains no `setup.py`, no `pyproject.toml`, no declared minimum Python version and no version anywhere in the code. There are likewise no release artifacts here, you have to build the `.exe` yourself.

---

## 📄 License

The project is licensed under **MIT** - the full text is in the [`LICENSE`](LICENSE) file. The copyright line reads `Copyright (c) 2026 ClipDeck`, no specific author or organization is named in it.

---

<div align="center">

Built by **Alex Poliak** - [GitHub](https://github.com/Apoliak7777) - [alexpoliak21@gmail.com](mailto:alexpoliak21@gmail.com)

</div>
