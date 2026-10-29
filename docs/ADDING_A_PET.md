# Adding a pet (new species, new animations, new emotion engine)

A pet is one folder. The app needs no code changes to load it, only `pet.json` and the files it points to. The
emotion engine can be any algorithm: a CTRNN like the conure, a state machine, or a small learned model. It only has
to implement the four methods of `app/plugin_api.py`.

## 1. Copy the template

```text
pets/_template/  ->  pets/<pet_id>/          pet_id = folder name = a Python identifier (e.g. border_collie)
  pet.json                                    manifest (below)
  icon.png                                    optional, 256x256 with transparency (tray icon)
  model/<variant>.glb                         one GLB per look (female/male, colours...), same skeleton + clips
  model/animations.json                       clip table (written by the Blender export)
  engine/__init__.py                          def create_engine(ctx) -> object with event/update/get_state/set_state
  sounds/sound_bank.json + sounds/bank/*.wav  optional; plus CREDITS.md for licences
```

Folders starting with `_` or `.` are ignored, so the template never shows up as a pet.

## 2. Model and animations (Blender)

- Model about 1 m tall in Blender units, facing −Y, feet at z = 0. Export glTF binary with +Y up, skinning, shape keys, every clip as an action (NLA tracks), and "always sample". The app normalises by `stage.model_height`.
- `animations.json` has, per clip: `seconds`, `loop`, optional `events_s` (e.g. footsteps, beak taps), `blend_in_s`, `category`, `root_motion`. Clip names must match the GLB animation names; `plugin_check` verifies this.
- Clips should start and end near the rest pose, and emotion clips should loop cleanly. Hidden props: scale their bones to 0.001 in every clip.
- For live gaze the rig needs a head bone, ideally a neck bone, and eye bones that rotate the iris. Blinks need lid bones plus a `blink` clip; the app reads the closed pose from its peak. A jaw bone plus one wide-open clip enables lip-sync.

## 3. `pet.json` reference

```jsonc
{
  "schema": 1,
  "id": "border_collie",                 // = folder name
  "name": "Border Collie",
  "icon": "icon.png",
  "model": {
    "variants": {"tricolour": "model/collie_tri.glb", "merle": "model/collie_merle.glb"},
    "default_variant": "tricolour",
    "clips": "model/animations.json"
  },
  "engine": {"api": 1, "package": "engine", "factory": "create_engine",
             "options": {"start": {}}},   // passed to the factory as ctx.options
  "stage": {
    "default_size": "S",
    "sizes": {"S": 130, "M": 190, "L": 255},        // on-screen pet height in px
    "frame": {"width": 2.0, "height": 1.95, "feet": 0.2},   // window = pet_px x (width, height); feet above bottom
    "model_height": 1.0,                            // model units for the pet's height
    "camera": {"fov": 30, "elevation_deg": 8},
    "idle_clip": "idle_breathe",
    "shadow": {"opacity": 0.22, "size": [0.62, 0.34]}   // or opacity 0 for none
  },
  "rig": {
    "gaze": {"neck_bone": "neck", "head_bone": "head", "eye_bones": ["eye.L", "eye.R"],
             "neck_share": 0.4, "head_yaw_max": 60, "head_pitch_up": 28, "head_pitch_down": 22,
             "eye_yaw_max": 14, "eye_pitch_max": 9, "body_yaw_max": 30, "depth": 2.4,
             "clip_weights": {"sleep": 0, "eat": 0.3}},      // how much each clip lets the head follow the cursor
    "face": {"lid_bones": ["lid_up.L", "lid_up.R"], "blink_clip": "blink",
             "jaw_bone": "jaw", "jaw_clip": "bark", "beak_upper_bone": null, "pupil_morph": null},
    "zones": [                                       // touch zones: rest-pose point (model space) on a bone + radius (m)
      {"zone": "head", "bone": "head", "at": [0, 0.8, 0.2], "r": 0.1},
      {"zone": "belly", "bone": "spine", "at": [0, 0.3, 0.25], "r": 0.12}
    ],
    "lift": {"bone": "root", "clips": {"jump_big": 1.5}},   // optional: raise the model by (k-1) x the clip's root lift
    "anchors": {                                     // where 2D effects attach
      "head_top": {"bone": "head", "at": [0, 1.0, 0.1]}, "head": {"bone": "head", "at": [0, 0.8, 0.15]},
      "beak": {"bone": "head", "at": [0, 0.7, 0.4]}, "eye_l": {"bone": "head", "at": [0.1, 0.8, 0.3]},
      "eye_r": {"bone": "head", "at": [-0.1, 0.8, 0.3]}, "body": {"bone": "chest", "at": [0, 0.45, 0.2]},
      "feet": {"bone": "root", "at": [0, 0, 0.1]}
    }
  },
  "sounds": {
    "bank": "sounds/sound_bank.json",
    "vocal_categories": ["bark", "whine"],            // one at a time
    "sleep_categories": ["sigh"],                     // the only ones allowed while asleep
    "mouth_categories": ["pant"],                     // + vocal = sounds that must move the jaw
    "min_jaw_deg": 22, "jaw_deg": {"pant": 8},        // lip-sync opening (explicit values win over the minimum)
    "quiet_clips": ["sleep", "eat", "being_petted"],  // mouth busy / hidden: spontaneous mouth sounds wait 0.6 s, then drop
    "engine_tokens": {"grumble": "growl"},            // overrides of the bank; "" = silent
    "clip_events": {"eat:crunch": {"sound": ""}},     //   "
    "clip_sounds": {"jump_big": [[0.4, "thud", -3]]}  //   "  (time-scheduled sounds per clip)
  },
  "menu": [{"id": "throw_ball", "label": "Throw the ball"},
           {"id": "sit", "label": "Sit", "when": "awake"}],              // id = engine event name; when: awake / asleep
  "panel": {                                          // the mood panel window (all optional)
    "meters": [{"label": "Hunger", "from": "drives.hunger", "full": 1.0, "color": "#E8A33C",
                "levels": [[0.3, "Full"], [0.7, "Peckish"], [1.01, "Hungry"]]}],   // from = path in the engine output
    "emotions": [["happy", "Happy", "#F2B705"], ["angry", "Angry", "#E5484D"]],     // fixed rows: name, label, colour
    "behaviours": {"play": "playing"},                // plain words for out.behaviour
    "emotion_words": {"neutral": "Calm"}
  },
  "fx": {
    "scale_ref_px": 190,
    "cooldown_s": {"heart": 0.45},
    "tokens":  {"heart": [{"kind": "heart"}]},                                // engine fx token -> effects
    "ambient": [{"when": {"emotion": "happy", "above": 0.6}, "kind": "sparkle", "rate_hz": 0.4}],
    "levels":  {"rain_cloud": "sad"},
    "clips":   {"play_bow": [{"kind": "leaf", "rate_hz": 1.0}], "bark": [{"kind": "call", "at": 0.1}]},
    "sounds":  {"bark": [{"kind": "call"}]}
  }
}
```

Effect kinds available in `web/js/fx.js`:
- symbols: heart, spark, sparkle, smoke, ha, note, zzz, anger, exclaim, question
- particles: dust, puff, tear, sweat, rain, petal, leaf, leaf_dry, feather, call

`when` conditions: `{emotion, above}`, `{drive, above}`, `{behaviour}`, `{behaviour_in: [...]}`, `{clip_in: [...]}`.
A new effect kind is the only change that touches core code: add a recipe and a painter to `fx.js`.

## 4. The engine

```python
def create_engine(ctx):            # ctx: pet_id, pet_dir, manifest, clips {name: {dur, loop, events}}, data_dir, seed, hour, options
    return MyEngine(ctx)

class MyEngine:
    def event(self, name, **kw): ...          # 'pet'(zone, speed) 'tap'(zone) 'poke'(zone) 'drag_start' 'drag_end' 'menu_open' + menu ids; ignore unknown
    def update(self, dt, percepts): ...       # -> dict; at minimum {'clip': name, 'changed': bool}
                                              #    optional: 'drives' (panel meters), 'emotions', 'behaviour', 'sounds',
                                              #    'fx', 'hold': {start, end, repeats} = loop [start, end) n times (hover)
    def get_state(self): ...                  # JSON-serialisable long-term memory
    def set_state(self, state, now=None, hour=None): ...   # restore + fast-forward the closed time
```

Percepts arrive in screen pixels for the pet as drawn (`pet_px` tells you the size). Divide by `pet_px` to make the pet
behave the same at every size. The full field lists are in `app/plugin_api.py`. Missing output keys get defaults, so
start minimal (the template engine just loops `idle`) and grow it.

Keep the engine free of Qt and of file I/O; the core saves `get_state()` for you.

## 5. Check, review, test

```bat
python -m app.plugin_check border_collie      :: must say OK
python -m app.review C:\temp\collie_review --pet border_collie
python -m app.desktop                         :: the new pet appears next to the others
```

Look at every review sheet before calling it done. Gaze directions, framing at S/M/L, effects placement and the
face close-ups are visual judgements; the hit-test and e2e lines in `review.json` must all be PASS. (The review's mood
list is written for the conure; give a new species its own list in `app/review.py` when its clips differ.)

To disable a pet without deleting it, set `"enabled": false` for it in the user `settings.json`
(`%APPDATA%\DesktopPets3D` on Windows, `~/Library/Application Support/DesktopPets3D` on macOS).

A new pet ships inside the built app automatically: `packaging/DesktopPets3D.spec` bundles the whole `pets/` folder.
If its engine imports a library other than numpy, add it to `hiddenimports` in the spec.
