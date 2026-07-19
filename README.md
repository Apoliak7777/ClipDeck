<div align="center">

[![Slovenčina](https://img.shields.io/badge/SK-Sloven%C4%8Dina-2ea043?style=for-the-badge)](README.md) [![English](https://img.shields.io/badge/EN-English-30363d?style=for-the-badge)](README.en.md)

</div>

<div align="center">

# 🎬 ClipDeck

**Instant-replay klipovač pre Windows - beží na pozadí, jedným klávesom uloží posledných N sekúnd hry.**

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-only-0078D6?style=flat-square&logo=windows&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-gdigrab%20%2B%20NVENC-007808?style=flat-square&logo=ffmpeg&logoColor=white)
![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-1f6feb?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

</div>

---

## 📑 Obsah

- [Prehľad](#-prehľad)
- [Funkcie](#-funkcie)
- [Inštalácia](#-inštalácia)
- [Build .exe](#-build-exe)
- [Štruktúra projektu](#-štruktúra-projektu)
- [Konfigurácia](#-konfigurácia)
- [Ako to funguje](#-ako-to-funguje)
- [Testy](#-testy)
- [Známe obmedzenia](#-známe-obmedzenia)
- [Licencia](#-licencia)

---

## 🧭 Prehľad

ClipDeck je klipovač herných momentov v štýle Medal alebo ShadowPlay. Na pozadí drží jeden dlho bežiaci proces FFmpeg, ktorý zachytáva zvolený monitor (`gdigrab`) plus systémový zvuk (WASAPI loopback) do kruhového bufferu 1-sekundových MPEG-TS segmentov na disku.

Po stlačení globálnej klávesovej skratky (predvolene `F4`) sa najnovšie segmenty spoja cez `concat -c copy` do `.mp4`. Žiadne prekódovanie znamená, že uloženie je okamžité a bezstratové - a keďže je kruh ohraničený, spotreba disku ostáva konštantná bez ohľadu na to, ako dlho aplikácia beží.

Aplikácia žije v system tray a má tmavé CustomTkinter okno s galériou klipov a nastaveniami. V inteligentnom režime sa buffer sám zapne len vtedy, keď beží sledovaný herný proces.

---

## ✨ Funkcie

- ⚡ **Okamžité uloženie klipu** - `concat -c copy` bez prekódovania, klip je na disku prakticky ihneď a v pôvodnej kvalite.
- 🔁 **Rolling buffer s pevnou veľkosťou** - `segment` muxer píše 1-sekundové `.ts` súbory, kruh má `clip_seconds + 6` (minimálne 8) segmentov.
- ⌨️ **Globálna skratka** - predvolene `F4`, prebindovateľná priamo v aplikácii cez `keyboard.read_hotkey()`.
- 🎮 **Inteligentné nahrávanie** - slučka každé 3 sekundy skenuje procesy a buffer zapne len keď beží sledovaná hra. Zoznam hier sa dá editovať v UI.
- 🚀 **Automatická detekcia enkodéra** - reťazec `hevc_nvenc` → `h264_nvenc` → `h264_qsv` → `h264_amf` → `libx264`, každý s vlastnými kvalitatívnymi parametrami.
- 📥 **Auto-download FFmpeg** - pri prvom spustení sa stiahne statický build a rozbalí do `%LOCALAPPDATA%\ClipDeck\bin\`.
- 🖥️ **Podpora viacerých monitorov** - výber, ktorý monitor sa nahráva, a samostatne, na ktorom sa zobrazuje okno aplikácie.
- 🔊 **Systémový zvuk plus mikrofón** - WASAPI loopback (callback mód) sa mixuje s voliteľným DirectShow mikrofónom cez `amix`.
- 🖼️ **Galéria klipov** - mriežka kariet s automaticky generovanými JPG náhľadmi, veľkosťou, dátumom, prehratím na klik a mazaním.
- 🔔 **OSD toast bez kradnutia fokusu** - borderless topmost okno s `WS_EX_NOACTIVATE`, aby hru v celej obrazovke nevyhodilo. Predvolene vypnuté a zapnúť sa dá len ručnou úpravou `config.json` - v UI preň neexistuje ovládací prvok.
- 🏷️ **Pomenovanie podľa hry** - názov klipu sa berie z titulku aktívneho okna, napr. `Game Title - 2026-07-19_14-30-00.mp4`.
- 🩺 **Watchdog** - kontroluje stav bufferu každé 2 sekundy a po páde FFmpeg spustí jeden pokus o reštart. Slučka watchdogu sa pritom už znovu nenaplánuje, takže po tomto jedinom pokuse prestane bežať až do reštartu aplikácie.
- 📊 **Live CPU a GPU vyťaženie** - v nastaveniach cez `psutil` a `nvidia-smi`.

---

## 📦 Inštalácia

> **Windows only.** Kód používa `ctypes.windll`, `winreg`, `gdigrab`, `dshow`, WASAPI loopback a `os.startfile`. Na Linuxe ani macOS sa moduly ani nenaimportujú.

Spustenie zo zdrojáku v koreňovom priečinku repozitára:

```powershell
pip install -r requirements.txt
python clipdeck.py
```

To je celé - žiadny server, databáza ani API kľúč. Aplikácia sa spustí skrytá, po asi 500 ms otvorí okno galérie a nainštaluje tray ikonu.

> [!NOTE]
> Verzia Pythonu nie je nikde v repozitári vynútená - chýba `pyproject.toml`, `python_requires` aj runtime kontrola. Jediná skutočná spodná hranica v kóde je `shlex.join` (`engine.py`), teda **Python 3.8+**. Moderné anotácie typu `str | None` a `list[dict]` sú vo všetkých troch moduloch neutralizované cez `from __future__ import annotations`, takže sa za behu nevyhodnocujú. `build.ps1` napriek tomu ako prvú možnosť skúša Python 3.13.

> [!NOTE]
> Pri prvom spustení `engine.ensure_ffmpeg()` stiahne statický FFmpeg build z `gyan.dev`, takže prvý štart potrebuje internet - pokiaľ už `ffmpeg` nemáš v `PATH`.

> [!IMPORTANT]
> Aplikáciu spúšťaj **ako správca**. Knižnica `keyboard` inak nedostane globálnu skratku, keď má fokus hra bežiaca s vyššími právami alebo v exkluzívnom fullscreene. Build skript preto pridáva `--uac-admin`.

---

## 🔨 Build .exe

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Skript najprv spustí `python make_icon.py` (pregeneruje ikony), potom zavolá PyInstaller v režime one-file / windowed. Výstup je `dist\ClipDeck.exe`.

> [!WARNING]
> `pyinstaller` **nie je** v `requirements.txt`, treba ho doinštalovať zvlášť (`pip install pyinstaller`). `build.ps1` navyše najprv skúša natvrdo zadanú cestu k Pythonu 3.13 a až potom `python` z `PATH`.

---

## 📁 Štruktúra projektu

```text
ClipDeck/
├── clipdeck.py          # Vstupný bod. ClipDeckApp: boot, bootstrap ffmpeg, detekcia
│                        # enkodéra, slučka detekcie hier, hotkey, watchdog, tray menu.
│                        # Obsahuje DEFAULTS, load/save_config, get_monitors(),
│                        # OSDNotification a čistý build_recorder_start_cfg().
├── engine.py            # Nahrávacie jadro bez UI. Recorder (ffmpeg príkaz, save_clip,
│                        # _tail_segments, _janitor), AudioPump (WASAPI loopback),
│                        # find_ffmpeg/ensure_ffmpeg, detect_encoder, generate_thumbnail.
├── gallery.py           # Celé GUI. GalleryWindow (sidebar, mriežka klipov, nastavenia),
│                        # HWMonitor (CPU/GPU) a čisté helpery apply_settings_fields,
│                        # apply_topbar_capture a prepare_monitor_menus, ktoré priamo
│                        # importujú testy (resolve_monitor_index volajú len nepriamo).
├── make_icon.py         # Generuje assets/icon.ico (7 veľkostí) a icon.png cez Pillow.
├── build.ps1            # Pregeneruje ikonu a spustí PyInstaller (onefile, windowed, UAC).
├── requirements.txt     # customtkinter, keyboard, pystray, Pillow, PyAudioWPatch, psutil
├── tests/
│   └── test_engine.py   # unittest: _tail_segments, save_clip (mockovaný subprocess)
│                        # a config flow apply_settings_fields -> build_recorder_start_cfg.
├── assets/              # icon.ico a icon.png (generované, pre tray, okno a exe)
└── LICENSE              # MIT
```

---

## 🔧 Konfigurácia

Nastavenia sa ukladajú do `%LOCALAPPDATA%\ClipDeck\config.json`. Súbor sa merguje nad `DEFAULTS`, poškodený alebo chýbajúci súbor ticho spadne späť na predvolené hodnoty. Konfigurácia sa nedá riadiť premennými prostredia ani `.env` súborom; jediná priamo čítaná premenná je `LOCALAPPDATA` (v `engine.app_data_dir()`), ktorá určuje umiestnenie dátového priečinka - a nepriamo `USERPROFILE` cez `os.path.expanduser("~")` pri predvolenom `save_dir`.

| Kľúč              | Predvolené                      | Voľby v UI                | Popis                                                        |
| :---------------- | :------------------------------ | :------------------------ | :----------------------------------------------------------- |
| `fps`             | `144`                           | 30 / 60 / 90 / 120 / 144  | Snímková frekvencia zachytávania                             |
| `clip_seconds`    | `30`                            | 15 / 30 / 60 / 90 / 120   | Dĺžka ukladaného klipu v sekundách                           |
| `use_audio`       | `true`                          | prepínač                  | Systémový zvuk cez WASAPI loopback                           |
| `audio_bitrate`   | `320`                           | 128 / 192 / 256 / 320     | Bitrate AAC v kbps                                           |
| `hotkey`          | `"f4"`                          | ľubovoľná kombinácia      | Skratka na uloženie klipu                                    |
| `save_dir`        | `%USERPROFILE%\Videos\ClipDeck` | výber priečinka           | Kam sa ukladajú `.mp4` a `.jpg`                              |
| `capture_monitor` | `0`                             | zoznam monitorov          | Index nahrávaného monitora (primárny prvý)                   |
| `gui_monitor`     | `1`                             | zoznam monitorov          | Na ktorom monitore sa centruje okno aplikácie                |
| `show_osd`        | `false`                         | iba ručne v `config.json` | OSD toast po uložení klipu (v UI preň nie je ovládací prvok) |
| `smart_record`    | `true`                          | prepínač                  | Nahrávať len keď beží sledovaná hra                          |
| `tracked_games`   | 10 hier                         | editor v UI               | Zoznam `.exe` mien (cs2, valorant, gta5 a ďalšie)            |
| `mic_device`      | nie je v `DEFAULTS`             | zoznam DirectShow         | Názov mikrofónu, prázdny reťazec znamená bez mikrofónu       |

### Runtime cesty

| Cesta                                    | Obsah                                           |
| :--------------------------------------- | :---------------------------------------------- |
| `%LOCALAPPDATA%\ClipDeck\config.json`    | Nastavenia                                      |
| `%LOCALAPPDATA%\ClipDeck\bin\ffmpeg.exe` | Automaticky stiahnutý FFmpeg                    |
| `%LOCALAPPDATA%\ClipDeck\buffer\`        | Kruh segmentov `seg*.ts` a `buffer.m3u8`        |
| `save_dir`                               | `.mp4` klipy a k nim súrodenecké `.jpg` náhľady |

---

## 🔬 Ako to funguje

| Krok            | Čo sa deje                                                                                               |
| :-------------- | :------------------------------------------------------------------------------------------------------- |
| 1. Zachytávanie | `ffmpeg -f gdigrab -framerate <fps>` s `-offset_x`, `-offset_y` a `-video_size` podľa zvoleného monitora |
| 2. Zvuk         | `AudioPump` čerpá WASAPI loopback v callback móde a píše surové `s16le` PCM do `stdin` FFmpeg            |
| 3. Enkódovanie  | Prvý dostupný enkodér z tabuľky, NVENC beží s `-rc vbr -cq 8 -preset p7 -tune hq`                        |
| 4. Buffer       | `segment` muxer píše `seg%08d.ts` po jednej sekunde a udržiava `buffer.m3u8`                             |
| 5. Údržba       | Vlákno janitora maže segmenty staršie než `ring + 4`, aby klipovanie nikdy nezávodilo s mazaním          |
| 6. Uloženie     | `_tail_segments()` prečíta playlist, skopíruje len potrebný chvost a `concat -c copy` s `+faststart`     |
| 7. Náhľad       | Snímka z času `00:00:02` (fallback `00:00:00`) sa uloží ako `.jpg` vedľa klipu                           |

Po štarte buffera aplikácia čaká až 12 sekúnd na aspoň 3 neprázdne segmenty. Ak `gdigrab` nedodá žiadne snímky, spustenie skončí zrozumiteľnou chybou s odporúčaním znížiť FPS alebo vypnúť zvuk.

---

## 🧪 Testy

Z koreňového priečinka repozitára, aby boli moduly `engine`, `clipdeck` a `gallery` importovateľné:

```powershell
python -m unittest discover -s tests -v
```

Testy pokrývajú `_tail_segments` (happy path, preskočenie nulových segmentov, prázdny a krátky playlist), `save_clip` (prázdny buffer, volanie concat a náhľadu s mockovaným `subprocess`, zlyhanie concat) a tok konfigurácie od `apply_settings_fields` cez `build_recorder_start_cfg` až po výpočet veľkosti kruhu.

> [!WARNING]
> Testy nie sú CI-friendly. Importujú `clipdeck` a `gallery`, ktoré už pri importe volajú `ctypes.windll` a inicializáciu CustomTkinter, takže vyžadujú Windows a všetky GUI závislosti. V repozitári nie je `tests/__init__.py` ani CI konfigurácia.

---

## 📋 Známe obmedzenia

- 🪟 **Výhradne Windows.** Neexistuje žiadna vetva pre Linux ani macOS.
- 🛡️ **FFmpeg sa sťahuje bez overenia.** Binárka z `gyan.dev` sa stiahne cez HTTPS bez kontrolného súčtu či podpisu a následne spúšťa.
- 🩺 **Watchdog sa po prvom reštarte zastaví.** Vetva zlyhania v `_watchdog()` spustí `_start_recording` v novom vlákne, ale už sa nepreplánuje cez `root.after(2000, ...)`, a `_start_recording` timer znovu nenasadí, lebo príznak `_watchdog_started` je vtedy už `True`.
- 🎤 **Bug v položke "žiadny mikrofón".** Voľba `Žiadny (Iba hra)` sa uloží do `mic_device` doslovne ako reťazec, `engine.py` ju berie ako reálne zariadenie a FFmpeg dostane `-f dshow -i audio=Žiadny (Iba hra)`. Funguje to len preto, že `clipdeck.py` zachytí zlyhanie `dshow`, zobrazí varovanie a spustí sa znova bez mikrofónu - teda jeden zbytočný pokus pri každom štarte buffera.
- 🔔 **`show_osd` nemá ovládací prvok.** Kľúč existuje v `DEFAULTS` aj v `_save_clip`, ale nastavenia stavajú prepínače len pre `smart_record` a `use_audio`. Zapnúť OSD sa dá výhradne ručnou úpravou `config.json`.
- 🖨️ **Ladiaci `print`.** Riadok `print("FFMPEG CMD:", ...)` ostal v `engine.Recorder.start()`. V `--windowed` builde je neškodný, pri spustení zo zdrojáku hlučný.
- 🪟 **Blik konzoly.** `_get_dshow_audio_devices()` v `gallery.py` volá `subprocess.run` bez `CREATE_NO_WINDOW`, takže otvorenie nastavení môže krátko blysnúť konzolovým oknom.
- 🗑️ **Mazanie klipov je okamžité a tiché** - `os.remove` na `.mp4` aj `.jpg`, bez potvrdenia a bez koša.
- 🔥 **144 FPS je náročné.** Priebežné enkódovanie na predvolených 144 fps plní `%LOCALAPPDATA%` stálym prúdom segmentov. Bez NVENC padá reťazec až na `libx264 -preset fast -crf 10`, čo veľmi zaťaží CPU.
- 🎯 **`gdigrab` nezachytí spoľahlivo skutočný exkluzívny fullscreen.** Ide o limit desktopového grabbera, nie o niečo, čo aplikácia vie obísť.
- 🌍 **Celé UI, tray menu aj chybové hlášky sú len po slovensky.** Žiadna lokalizačná vrstva.
- 🔎 **`smart_record` matchuje existenciu procesu kdekoľvek v systéme**, nie aktívne okno, a používa voľné obojsmerné porovnávanie podreťazcov (`g in n or n in g`), čo pri krátkych názvoch `.exe` môže dávať falošné zhody.
- 📦 **Žiadne packaging metadáta** - v repozitári nie je `setup.py`, `pyproject.toml`, deklarovaná minimálna verzia Pythonu ani verzia kdekoľvek v kóde. Rovnako tu nie sú žiadne release artefakty, `.exe` si treba zbuildovať sám.

---

## 📄 Licencia

Projekt je pod licenciou **MIT** - plné znenie je v súbore [`LICENSE`](LICENSE). Copyright riadok znie `Copyright (c) 2026 ClipDeck`, konkrétny autor ani organizácia v ňom uvedení nie sú.

---

<div align="center">

Vytvoril **Alex Poliak** - [GitHub](https://github.com/Apoliak7777) - [alexpoliak21@gmail.com](mailto:alexpoliak21@gmail.com)

</div>
