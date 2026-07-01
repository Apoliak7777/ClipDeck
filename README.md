# ClipDeck

**Background game clipping tool** — high quality, high FPS screen recording for Windows with zero game disruption.

## Features

- **True background clipping** — Press hotkey (default F4) without minimizing or stealing focus from fullscreen games (even on dual monitors).
- **Up to 144 FPS** — Default is 144 fps for the smoothest clips. Fully configurable (30/60/90/120/144).
- **Maximum quality encoding** — Uses NVIDIA NVENC (HEVC preferred) with p7 preset, low CQ, spatial/temporal AQ, unlimited VBR.
- **Simple mini settings** — Segmented controls for FPS, clip length (15-120s), audio bitrate.
- **Smart recording** — Only records when supported games are active.
- **Monitor selection** — Full support for multi-monitor setups.
- **Slovak UI** — Clean, dark interface.

## Requirements

- Windows 10/11
- NVIDIA GPU (recommended for best quality; falls back to other encoders)
- Python 3.10+ (if running from source)
- FFmpeg (automatically downloaded on first run)

## Quick Start (Recommended)

1. Download the latest `ClipDeck.exe` from Releases (or build it yourself).
2. Run it. It will appear in the system tray.
3. Configure hotkey, FPS (144 recommended), clip length, etc.
4. Start playing your game in fullscreen.
5. Press **F4** (or your hotkey) — clip is saved silently in the background.

Clips are saved to `~/Videos/ClipDeck/` by default.

## Running from Source

```powershell
cd ClipDeck
pip install -r requirements.txt
python clipdeck.py
```

First run will download FFmpeg automatically.

## Building the Executable

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name ClipDeck --icon "assets/icon.ico" --add-data "assets;assets" --collect-all customtkinter --hidden-import pyaudiowpatch clipdeck.py
```

The built exe will be in `dist/`.

## How It Works

- Uses `gdigrab` for reliable desktop/monitor capture.
- Rolling 1-second MPEG-TS segments in a ring buffer.
- On hotkey: trims the last N seconds and concatenates with ffmpeg (fast copy).
- Pure functions for settings/monitor logic (easy to test).
- No focus stealing: notifications are disabled by default or use non-activating windows.

## Configuration

Settings are stored in `%LOCALAPPDATA%\ClipDeck\config.json`.

Key options:
- `fps`: 144 (best quality)
- `clip_seconds`: 30-90 recommended
- `show_osd`: false (recommended for background operation)
- `smart_record`: true

## Known Limitations

- High FPS (120-144) + very high resolution + audio can be demanding on the capture path. Lower FPS or disable audio if you see "no data" errors.
- Exclusive fullscreen games on high refresh rate + multi-monitor setups may have variable results with any desktop grabber.

## License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

## Contributing

Pull requests are welcome. Focus areas include better capture backends, more robust high-FPS handling, and improved notifications.

---

Made for gamers who want reliable background clipping at high quality and frame rates.