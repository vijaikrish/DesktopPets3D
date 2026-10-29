# DesktopPets3D — architecture

The core is species-neutral. A pet is a folder under `pets/` (see `ADDING_A_PET.md`). The core discovers it, runs its
engine, and draws it with the generic viewer. Nothing in `app/` or `web/` knows the word "conure".

```text
DesktopPets3D/
  run.bat / run_debug.bat     start from source on Windows (setup_windows.bat makes the .venv once)
  run.sh / run_mac.command    start from source on macOS / Linux (setup.sh makes the .venv once)
  requirements*.txt           PySide6 + numpy (+ PyInstaller, Pillow to build)
  app/                        Python/Qt host (OS integration, engine loop, persistence, mood panel)
  web/                        the page each pet window shows (Three.js 3D + 2D effects + audio + touch)
  pets/<pet_id>/              one plugin per species (model, clips, engine, sounds, effect rules, menu, panel)
  pets/_template/             copy-me skeleton (folders starting with '_' are not loaded)
  packaging/                  PyInstaller recipe (Windows .exe folder, macOS .app) + icon maker
  .github/workflows/build.yml GitHub Actions: tests + Windows and macOS builds, attached to tagged releases
  docs/                       this file, ADDING_A_PET, INSTALL, USER_GUIDE, BUILDING, PUBLISHING
  tests/                      offline unit tests
  tools/perf_probe.py         CPU / RAM measurement of a live run (Windows)
User data (never in the app folder): settings.json, pets/<id>/state.json (memory), logs/
  Windows %APPDATA%\DesktopPets3D   macOS ~/Library/Application Support/DesktopPets3D   Linux ~/.local/share/DesktopPets3D
```

## Files

### `app/` (Python 3.10+, PySide6 6.6+; developed on Python 3.15 / PySide6 6.12)

| File | Purpose |
|---|---|
| `__init__.py` | Name, version, core API version. |
| `paths.py` | Install root (source or PyInstaller bundle), `web/`, `pets/`, per-user data and log folders. `DP3D_DATA` redirects all user data (tests, review). |
| `plugin_api.py` | **The contract** between core and pet engines: `EngineContext`, the 4 required engine methods, documented `PERCEPTS` / `EVENTS` / `OUTPUT_DEFAULTS`, `normalize_output()` (a minimal engine still works). |
| `registry.py` | Finds `pets/*/pet.json`, validates it, imports each engine package under a private module name, calls its factory. Broken plugins are logged and skipped, not fatal. |
| `plugin_check.py` | `python -m app.plugin_check [id]`: every clip and bone `pet.json` names exists in every GLB variant, sound files exist, and the engine runs 5 s with events and round-trips its state. Run it for every new or changed pet. |
| `clips.py` | Parses `animations.json` (duration, loop, events, blend-in, root motion). |
| `storage.py` | `Settings` (global and per-pet: size, variant, position, volume…) and `PetMemory` (engine state). Atomic writes; a corrupt file is kept as `.broken_<time>` and the pet starts fresh. |
| `desktop.py` | `PetWindow`: frameless, translucent, always-on-top tool window per pet. 60 Hz tick: drag, click-through, engine update, sounds, effects, frame to the page, mood panel feed. Also the right-click menu (from `pet.json`), S/M/L sizing, tray icon, single-instance lock, `--selftest`. |
| `panel.py` | `MoodPanel`: the mood panel as its **own** small window (QPainter, no web view) - drag it anywhere, x closes it, position remembered. Meters, feeling rows and behaviour wording come from `pet.json` `panel`. Values are smoothed (0.45 s) and the row order is fixed, so it reads calmly. |
| `sound_bank.py` | Engine sound tokens and clip events → concrete sound files from the pet's `sound_bank.json` (+ overrides in `pet.json` `sounds`). One vocal at a time, no immediate repeats, pitch/level jitter by arousal, quiet sounds only while asleep, and the **beak rule** (below). |
| `fx_director.py` | Decides which 2D effects to spawn from `pet.json` `fx` rules: engine tokens, emotion thresholds (Poisson), behaviours, clips, sound categories. Per-kind cooldowns. |
| `asset_server.py` | Read-only HTTP server on 127.0.0.1 (random port) serving only `web/` and `pets/` (Chromium will not run ES modules from `file://`). No directory listing, no path escapes. |
| `osapi.py` | The OS layer the host uses: `idle_seconds()`, `local_hour()`, `set_click_through(widget, on)`, `prepare_window()`. Picks the implementation per platform (below). |
| `win32.py` | Windows: `GetLastInputInfo` idle time; `WS_EX_TRANSPARENT` toggle on the layered window. |
| `macos.py` | macOS: idle time from CoreGraphics (`CGEventSourceSecondsSinceLastEventType`) via ctypes - no PyObjC. |
| `review.py` | `python -m app.review <out> [--only eyes,e2e]`: visual and functional review harness (see Verification). |
| `trace.py` | `python -m app.trace <out.json> [--cursor wander\|scratch\|still\|far] [--clip name]`: per-frame trace of the live rig (lid / eye / pupil / head straight out of the mixer and after the procedural layer) to find glitches a screenshot cannot show. |

### `web/` (ES modules, Three.js r186 vendored, no network)

| File | Purpose |
|---|---|
| `pet.html`, `css/pet.css` | Transparent page; strict CSP (self only); the 3D canvas fades in when the model is ready. |
| `js/pet.js` | Orchestrator: WebChannel bridge, clip mixer (crossfades, self-crossfade for restarted one-shot clips, hover loops), flight lift, smoothed lip-sync, per-frame order, snapshots. |
| `js/stage.js` | Renderer (Neutral tone mapping keeps the painted v08 colours), environment and lights, contact shadow (shrinks and fades when the pet is airborne), deterministic framing from `stage.frame`, and the pixel-exact hit test under the cursor (alpha read-back). |
| `js/rig.js` | Procedural layer over the baked clips: body yaw ±30°, head/neck look-at, eyes, blinks, lid droop, pupil pinning, jaw lip-sync. Also bone-attached points for touch zones and effect anchors. |
| `js/touch.js` | Hover strokes, taps, pokes, drag, menu (right button, or Ctrl+click on macOS); distance, approach, speed and jitter percepts. |
| `js/fx.js` | 2D effect painters and particle physics, anchored to bones, scaled to the pet's size. |
| `js/audio.js` | WebAudio playback and the loudness envelope that drives the jaw. |
| `vendor/three/` | Three.js modules plus LICENSE (MIT). |

## One frame

```text
Python (60 Hz QTimer)                                   Page (requestAnimationFrame, vsync 60 fps)
---------------------                                   ------------------------------------------
cursor = QCursor.pos() - window.pos()
percepts = {cursor_dist, cursor_approach, cursor_speed,  <- 'percept' 10 Hz {dist, approach, speed, jitter, over, zone}
            cursor_jitter, cursor_over, cursor_zone,
            pet_px, idle_s, hour, held}
out = engine.update(dt, percepts)
sounds = SoundBank.from_output(out)
fx, levels = FxDirector.step(out, sounds)
panel.feed(out)  (mood panel window, 5 Hz repaint)
send {type:'frame', out, sounds, fx, levels, cursor}  ->  play/crossfade clip if changed (+ out.hold hover loop); sounds; fx
                                                          rig.resetBeforeMixer(); mixer.update(dt); hover loop wrap
                                                          rig.captureAfterMixer(); flight lift + shadow
                                                          rig.apply(): body yaw -> neck/head -> eyes -> lids -> pupils -> jaw
                                                          anchors/zones -> screen; fx.update + draw
                                                          stage.probe(cursor) ; render ; alpha under cursor
stroke / tap / poke / drag  -> engine.event(...)        <- 'hover' {over} (on change), 'stroke' ~4 Hz, 'tap', ...
click-through = not (over or dragging or menu)          (osapi.set_click_through)
```

The mixer owns playback time. The engine's `clip_time` is used only when a clip starts, so the two 60 Hz clocks never
fight. Snapping the time every frame caused visible stutter in 0.1.

## Gaze and body turn (`rig.js`)

- **Target.** The cursor's offset from the (smoothed) head on screen is turned into angles over a virtual viewing depth `D = gaze.depth × pet_px`: `yaw = atan2(dx, D)`, `pitch = atan2(−dy, D)`. Both are added to the direction from the head to the camera, so "cursor on the bird" means "look at the user". `atan2(dx, D)` with `D > 0` cannot flip ±180°, unlike the v4 bug.
- **Body.** Turns the whole pet about its vertical axis, up to `body_yaw_max` (30°), towards 0.65 × the cursor yaw. It turns in deliberate steps: hysteresis of 9° re-plants rather than creeps. A critically damped spring (ω = 2.4 s⁻¹) drives it, and the bird blinks on big turns, as birds do. Follow modes from the engine: `turn_away` turns away when sulking, `avoid` leans away, `none` (sleep) stays put.
- **Head and neck.** The animated head direction is measured each frame and rotated towards the target with weight `w`, so the head locks onto the cursor while the clip plays underneath. Rotation is applied in world space about each bone's own pivot (`L' = P⁻¹·Q·P·L`): 40 % neck, 60 % head. Limits use a soft tanh stop (yaw ±60° relative to the body, pitch +28/−22°); spring ω = 6.5 s⁻¹.
- **Eyes.** Fast spring (ω = 24 s⁻¹). They take the error the head has not closed yet, up to ±14°/±9°, plus small saccades. Eyes lead, head follows, body last.
- **Weight w** = clip weight (`gaze.clip_weights`, e.g. preen 0.1, head_scratched 0.15) × (0.25 + 0.6 × recent cursor activity + 0.35 × engine interest). When the cursor has not moved for a while, the bird's own animation takes over again.
- **Blink and lids.** The closed-lid pose is read from the `blink` clip at its peak, so no axis is guessed. Blink = slerp(animated lids, closed, b(t)); droop = 0.5 × `face.lid_droop` (content, sleepy, scratched).
- **Pupils.** The `pupil_small` morph is set to max(clip value, engine pinning).
- **Jaw.** The opening axis and the upper-beak coupling are read from the `squawk` clip (measured coupling 0.150°/°, matching the v10 rig). Sound loudness envelopes (60 fps) open the jaw while the pet vocalises; the jaw value is smoothed (open 25 ms, close 70 ms) so even a 0.2 s chirp reads as a beak movement.

**Mixer hand-off (fixed 2026-10-29).** The procedural layer edits bones *after* the mixer, so they must be put back
before the next `mixer.update()`. Put them back to **what the mixer last wrote** (`captureAfterMixer` /
`resetBeforeMixer`), never to the rest pose. Why: three.js' `PropertyMixer.apply()` only writes a bone when its
blended value *changed* since its previous write. Any held pose (a plateau in the bake, a constant lid, jaw or pupil
track) is therefore not re-written. Resetting to rest left those bones at rest:
- the head popped back to neutral for a few frames during `head_scratched`;
- the lids opened during the scratch (they should be 38° closed);
- the lids and pupils flickered in `rest_one_leg`.

`app.trace` shows it: the `lidMix` / `headMix` columns hold the pose straight out of the mixer.

## Sounds and the beak (v5)

Rule: **a sound that comes out of the mouth is never heard without the beak moving.** (Reported: "while head
scratching and I move the cursor to the belly, the animation still looks like scratching but the bird makes noise".
The head-scratch clip had beak-grinding events whose baked jaw moves 4° - invisible.)

- *Mouth sounds* = the vocal categories + `mouth_categories` (beak grinding, clicks).
- Each one is either lip-synced - the jaw follows its loudness envelope and opens at least `min_jaw_deg` (22° for the
  conure; checked visible at Small size) - or it is a baked clip event with `lip_sync: false` whose clip already opens
  the beak at that moment (squawk 30°, warn_lunge 26°; a unit test reads this from the GLB).
- `quiet_clips` (being scratched, asleep, eating, preening, yawning...): the engine's spontaneous mouth sounds wait up
  to 0.6 s for another clip, otherwise they are dropped. Baked events always play - they belong to that animation.
- A token or event mapped to `""` is silent (the conure's head-scratch grind; spontaneous grinding - grinding now
  only plays inside the `beak_grind` clip).

## Flight (v5)

The engine starts `fly` (menu) as a sequence: `flap_takeoff` with `out.hold = {start, end, repeats, lift}`. The bake
is take-off 0-0.8 s, airborne 0.8-2.2 s, landing 2.2-3.0 s; the airborne part is exactly periodic (1.0 s = three wing
beats, pose distance 0), so both the engine clock and the web player loop `[start, end)` `repeats` times - a seamless
hover - and then play the landing. `rig.lift` raises the model by `(lift - 1) ×` the clip's own root lift (the bird
rises ~0.35 pet heights, inside the window's head-room), and the contact shadow shrinks and fades with height.
Wing-flap sounds sit on the measured downstrokes (`sounds.clip_sounds`); a hover loop does not re-fire the earlier ones.

## Mood panel (v5)

A separate always-on-top tool window (`app/panel.py`), so it can sit anywhere and never covers the pet. Its content is
data: `pet.json` `panel.meters` (label, value path in the engine output such as `drives.sleep_debt`, full scale,
level words, colour), `panel.emotions` (fixed rows) and `panel.behaviours` (plain-language "what it is doing").
Toggle: right-click menu > Mood panel (remembered); drag anywhere; x closes.

## Platforms

| | Windows | macOS | Linux (X11) |
|---|---|---|---|
| Click-through | `WS_EX_TRANSPARENT` on the layered window (win32.py) | Qt `WindowTransparentForInput` on the QWindow → `NSWindow.ignoresMouseEvents`, toggled live | same Qt flag → X11 input shape |
| User idle time | `GetLastInputInfo` | CoreGraphics `CGEventSourceSecondsSinceLastEventType` | cursor movement only |
| Tool windows | always visible | `WA_MacAlwaysShowToolWindow` (otherwise hidden when another app is active); the packaged `.app` has `LSUIElement` (no Dock icon) | - |
| Right-click | right button | right button, two-finger click or Ctrl+click | right button |
| Tested | yes (Windows 11) | built by CI, **not yet run on a real Mac** | not tested |

## Touch and click-through

- Qt renders a translucent WebEngine window as one rectangle: **transparent pixels are not click-through by themselves** (verified with `WindowFromPoint`). The page therefore reads the alpha of a 5×5 px patch under the cursor right after rendering. Python makes the window click-through (`osapi.set_click_through`) whenever the cursor is not on the pet, so clicks next to the bird reach the desktop. Dragging and the open menu keep it clickable.
- **Zones.** Bone-attached points from `rig.zones`. The nearest one, by screen distance ÷ projected radius, wins; zones behind the body (back, tail when facing you) are skipped.
- **Kinematics.** Path speed over 0.25 s and direction reversals per second over 0.6 s (sampled on ≥ 40 ms steps longer than 2 % of the pet height, so hand tremor does not count). They go to the engine as `cursor_speed` and `cursor_jitter`. Normal use is ~300–1500 px/s with < 2 reversals/s; a gentle up-down scratch 2–4 reversals/s; frantic scrubbing 8–12.
- **Only the left button touches.** The right button only opens the menu (no tap, no press).
- **Strokes.** The cursor must be over the pet for > 0.35 s. Path speed is measured over 0.3 s. A fast one-way pass is ignored (the hand passing by), and a jump > 0.4 pet heights resets the history (flick). Back-and-forth rubbing at any speed is a stroke, and fast rubbing is rough.
- **Click** = press + release < 0.6 s without moving → `tap`; 3 clicks within 1.2 s → `poke`; press + move > 6 px → drag (the window follows the cursor; the pet is `held`).

## Sizes

`stage.sizes` gives the on-screen pet height per size (sun conure: S 130 px — the original size — M 190, L 255).
The window is `pet_px × frame.width` by `pet_px × frame.height` (2.0 × 1.95), with the feet `frame.feet` (0.2) pet heights
above the bottom. The space above the head is for effects. On a size change the feet stay where they were (the
bottom-centre is anchored), and the window is kept on screen. The camera distance follows from `frame.height` and the
field of view, so framing is identical at every size and never depends on runtime bounding boxes. Hidden props at
rest made the 0.1 fit wrong.

## 2D effects

`fx.js` knows how to draw; `pet.json` `fx` decides when. Default anchors per kind: hearts, Zzz, `!`, `?` and anger
marks above the head; notes from the beak, drifting outwards past the eyes; tears from the eyes; smoke and sweat at
the head sides; dust at the feet; leaves and petals from the top edge, settling on the feet line; rain cloud above
the head. Sizes and speeds scale with `pet_px / fx.scale_ref_px`; there are at most 160 particles.

Sun conure mapping: anger → smoke puffs and anger mark; singing/whistling/chirps/talk → notes; play/dance → green
leaves and petals; bored/lonely → dry brown leaves; sad → rain cloud and tears; petting/affection → hearts and
sparkles; sleep → Zzz; startle → `!`; curious → `?`; afraid → sweat drops; contact calls → call rings.

## Performance

Measured with `tools/perf_probe.py` (24-thread desktop, RTX 3080). The host process includes Chromium's browser and
compositor threads.

| Size | Tick | CPU (% of one core) | Machine | RAM |
|---|---|---|---|---|
| S | 60 Hz | 65 % | 2.7 % | 620 MB |
| S | 30 Hz | 59 % | 2.5 % | 614 MB |
| L | 60 Hz | 57 % | 2.4 % | 614 MB |

Most of it is Chromium compositing a 60 fps WebGL character into a transparent window. The engine costs ~0.15 ms per
step. `DP3D_TICK_MS` can lower the Python rate; rendering stays at vsync.

## Verification (run before calling a change done)

```bat
python -m unittest discover -s tests -v                   :: 24 offline tests (QT_QPA_PLATFORM=offscreen on a headless machine)
python -m app.plugin_check                                :: every plugin: clips, bones, sounds, engine
python -m app.desktop --selftest                          :: real window; exits 0 only if the model loaded and frames flowed
python -m app.review <outdir> [--only fly,panel,beak]     :: sheets + hit-test + click-through + live e2e checks
python pets\sun_conure\engine\tools\test_desktop_touch.py 8 130   :: Vijai's 26 interaction rules
python tools\perf_probe.py 15 --size S                   :: Windows only
python -m app.trace trace.json --cursor scratch           :: glitch hunt: per-frame rig values
dist\DesktopPets3D\DesktopPets3D.exe --selftest          :: the BUILT app, after packaging (docs/BUILDING.md)
```
(`python` = the environment with the requirements, e.g. `.venv\Scripts\python`.)

`app.review` drives a real window with a virtual cursor. Your mouse is never moved. It writes:
- `sheet_sizes.png`: S/M/L over a light and a dark desktop;
- `sheet_gaze.png`: 9 cursor positions;
- `sheet_moods.png`: 12 emotions with their effects;
- `sheet_closeup.png`: face, beak and blink;
- `sheet_eyes.png`: XL close-ups of the eyes under half-closed lids (`rest_one_leg`) with the cursor in 5 places;
- `sheet_e2e.png`: live engine with a per-tick virtual cursor: head scratch, normal movement (no anger), frantic scrub (a bit angry, no lunges), belly click;
- `sheet_fly.png`: the Fly action at S and L - checks the bird rises > 0.25 pet heights, is never cut off at the top, and lands;
- `panel_*.png`: the mood panel window (hungry + sleep-deprived state);
- `sheet_beak.png`: lip-sync jaw at 0 / 22 / 28° at Small size;
- `review.json`.

Run Python with `PYTHONPATH` / `PYTHONHOME` / `VIRTUAL_ENV` unset (`run.bat` does this).
