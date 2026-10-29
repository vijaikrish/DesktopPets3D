# Installing and running DesktopPets3D

There are two ways to run it:

- **A. The ready-made app** - download, unzip, double-click. No Python needed. Best for most people.
- **B. From source** - run the Python code directly. Needed on Linux, for Intel Macs, and for development.

Your pet's memory, settings and log are stored per user, never in the app folder:

| | Folder |
|---|---|
| Windows | `%APPDATA%\DesktopPets3D` (paste that into the Explorer address bar) |
| macOS | `~/Library/Application Support/DesktopPets3D` (Finder: Go > Go to Folder...) |
| Linux | `~/.local/share/DesktopPets3D` |

Inside: `settings.json` (size, position, volume, panel), `pets/sun_conure/state.json` (the bird's memory),
`logs/desktoppets3d.log`.

---

## A. Ready-made app

Download from the repository's **Releases** page (right-hand side on GitHub).

### Windows 10 / 11 (64-bit)

1. Download `DesktopPets3D-windows-x64.zip` (about 240 MB; about 535 MB unpacked - most of it is the built-in
   Chromium engine that draws the 3D bird).
2. Right-click the zip > **Extract All...** and extract to a permanent place, for example
   `C:\Users\<you>\Documents\DesktopPets3D`. Do not run it from inside the zip.
3. Open the folder and double-click **`DesktopPets3D.exe`**. The bird appears at the bottom-right of the screen, just
   above the taskbar, and an icon appears in the system tray.
4. If Windows shows **"Windows protected your PC"** (SmartScreen, because the app is not code-signed): click
   **More info > Run anyway**. This is needed only once.
5. Optional - start with Windows: press `Win+R`, type `shell:startup`, Enter, and put a shortcut to
   `DesktopPets3D.exe` in that folder (right-click the exe > Show more options > Create shortcut, then move it).
6. Optional - a desktop shortcut: right-click `DesktopPets3D.exe` > Show more options > Send to > Desktop.

Keep the `_internal` folder next to the exe; the app needs it.

### macOS (Apple silicon: M1 or newer)

1. Download `DesktopPets3D-macos-arm64.zip` and double-click it to unzip.
2. Drag **DesktopPets3D.app** into **Applications**.
3. The first time: **right-click (or Ctrl+click) the app > Open > Open.** The app is not signed by an Apple developer
   ID, so a normal double-click is refused the first time.
4. If macOS says the app **"is damaged and can't be opened"** or **"cannot be verified"**, open Terminal and run
   ```bash
   xattr -dr com.apple.quarantine /Applications/DesktopPets3D.app
   ```
   then open it again. (This removes the "downloaded from the internet" flag; it does not change the app.)
5. The bird appears at the bottom-right of the screen. The app has **no Dock icon** (it is a desktop companion); it
   lives in the **menu bar** (top-right) and in the bird's own right-click menu.
6. Optional - start at login: System Settings > General > Login Items > **+** > DesktopPets3D.

Right-click on a Mac = two-finger click on the trackpad, or **Ctrl+click**.

Intel Macs: the ready-made app is built for Apple silicon only. Use **B. From source** below - it works the same.

> The macOS version is built automatically by GitHub but has **not yet been tested on a real Mac**. If something
> looks wrong, please open an issue with the log file (`~/Library/Application Support/DesktopPets3D/logs/`).

---

## B. From source

You need **Python 3.10 or newer** and an internet connection for the first setup (it downloads PySide6 - the Qt
toolkit, about 200 MB - and numpy into a private folder `.venv` inside the project).

Get the source: on GitHub, **Code > Download ZIP** and unzip it, or `git clone <repository URL>`.

### Windows

1. Install Python from <https://www.python.org/downloads/windows/>. In the installer tick
   **"Add python.exe to PATH"** (the `py` launcher is installed by default as well).
2. In the project folder double-click **`setup_windows.bat`**. It creates `.venv` and installs the requirements
   (a few minutes). It ends with "Done. Start the bird with run.bat".
3. Double-click **`run.bat`**. The bird starts without a console window.
   - **`run_debug.bat`** starts it with a console window that shows errors - use it if nothing appears.

### macOS

1. Install Python 3 from <https://www.python.org/downloads/macos/> (or `brew install python`).
2. Open Terminal in the project folder (Finder: right-click the folder > New Terminal at Folder) and run
   ```bash
   bash setup.sh
   ```
3. Start the bird with
   ```bash
   bash run.sh            # starts in the background; quit from the bird's menu or the menu-bar icon
   bash run.sh --debug    # stays in the terminal and shows errors
   ```
   or double-click **`run_mac.command`** in Finder (the first time: right-click > Open). It runs the setup if needed.

### Linux (X11)

```bash
bash setup.sh
bash run.sh
```
Needs an X11 session with a compositor (transparent windows). Wayland sessions are not supported for click-through.
Not tested - reports welcome.

### Without the setup scripts

```bash
python -m pip install -r requirements.txt
python -m app.desktop          # from the project folder
```

---

## Using it

- **Quit:** right-click the bird > **Quit DesktopPets3D**, or the tray / menu-bar icon > Quit.
- **Hide / show:** right-click > Hide; bring it back with a click on the tray / menu-bar icon.
- Only **one copy** runs at a time; starting it again while it runs does nothing.
- Everything else: [USER_GUIDE.md](USER_GUIDE.md).

## Troubleshooting

| Problem | What to do |
|---|---|
| Nothing appears | Look in the tray / menu bar - it may be hidden. Check the log file (folder table above). From source: use `run_debug.bat` / `run.sh --debug` to see the error. |
| "Already running" / nothing happens on the second start | One copy is already running (maybe hidden). Quit it from the tray icon first. |
| A black or grey box around the bird | The graphics driver does not support transparent windows for the embedded browser. Update the graphics driver. On Linux, start a compositor. |
| The bird does not react to clicks, or clicks around it do not reach the desktop | Move the cursor away and back over the bird once; report the log if it persists. |
| No sound | Right-click > Sound: check "Mute" is off and the volume. The sound plays through the default output device. |
| It is always grumpy | Look at the mood panel: probably "Sleep-deprived". Leave it alone in the evening so it can sleep; it recovers within an hour or two of sleep, and while the app is closed. |
| Start fresh (forget everything) | Quit, then delete the `pets/sun_conure/state.json` file in the data folder. Delete `settings.json` to reset size, position and volume. |
| Windows: "VCRUNTIME140.dll was not found" | Install the Microsoft Visual C++ Redistributable (x64) from Microsoft's website. |
| macOS: "damaged" / "cannot be verified" | See step 4 of the macOS install above. |

## Uninstall

- **Ready-made app:** quit it, then delete the app folder (Windows) or `DesktopPets3D.app` (macOS). Remove the data
  folder (table at the top) if you also want to delete the bird's memory and settings. Remove any startup shortcut /
  login item you added.
- **From source:** quit it and delete the project folder (the `.venv` inside it goes with it), plus the data folder.
