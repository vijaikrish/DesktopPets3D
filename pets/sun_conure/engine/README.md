# ConureMind — the sun conure's emotion engine (plugin `sun_conure`)

Species-specific documentation. The desktop core never imports anything in this folder except `create_engine()`
from `__init__.py`; another species can use a completely different engine (see `docs/ADDING_A_PET.md`).

## Files

| File | Purpose |
|---|---|
| `__init__.py` | **Adapter.** `create_engine(ctx)` builds ConureMind, applies the starting temperament from `pet.json` (`engine.options.start`) and converts core percepts into ConureMind units. Screen pixels are scaled by `160 / pet_px`, so a gesture means the same at Small/Medium/Large. Mapping: `cursor_approach` → `cursor_speed` ("how fast the hand comes at me"); `cursor_speed` → `cursor_move` (path speed); `cursor_jitter`, `cursor_over` and `cursor_zone` pass through. |
| `conure_mind.py` | The engine: senses → body drives → learning → **appraisal layer** → 17-neuron CTRNN with **neuromodulated time constants** → core affect & mood → 30 behaviour units → clip + face/gaze/sound/fx outputs. numpy only; no Qt, no Blender. |
| `genome.py` | All numbers and wiring as data, each with a research reason: 50 input features, `APPRAISAL`, `NEUROMOD`, 17 emotion neurons, recurrent excitation/inhibition, personality, drives, `PETTING` (zones, speed bands, soothing), `TAP` (every click a poke), `MENU_TOUCH`, 30 behaviours with clips/gates/priorities, `SELECTION` (hysteresis), feeding sequences, Poisson rates, references. |
| `tools/test_desktop_touch.py` | Vijai's interaction rules as 26 pass/fail expectations through the real plugin path, at any size (cursor-only, clicks, calming, menu, carry). Exit 1 if one fails. |
| `tools/test_interaction.py` | v2 probes: a 3-hour owner history (loving / neglect / rough / over-petting), then the cursor approaches. |
| `tools/sim_day.py` | Simulated owner days. Reports time budgets (calm, groom, social, play, explore, negative), night sleep and clip variety; optional timeline PNG. |
| `tools/calibrate.py` | Refits the behaviour group biases against published time budgets. |

## What "neural network" means here

ConureMind is a **continuous-time recurrent neural network (CTRNN)**. Its wiring was written by hand from bird
ethology and affective neuroscience (Panksepp's systems, Russell's circumplex, Mendl's mood framework, Scherer's
appraisal theory) and then calibrated by simulation. It is **not** a deep network trained on a bird-emotion dataset;
no such dataset exists. It is a plausible, inspectable simulation, not a measurement of a real bird's feelings.

### Processing chain (every frame, any frame rate; internal step h ≤ 0.25 s)

1. **Senses.**
   - Percepts: cursor distance to the head, approach speed, path speed, jitter (direction reversals/s), over/zone, user idle time, clock, music, held.
   - Events: `pet` (hover strokes with zone + speed), `tap` (left click with zone), `poke` (3 fast clicks), `drag_start/end`, `menu_open`, and the menu items, including `pet_session` and `poke_once`.
   - Events leave decaying **traces** (τ): petting 3 s, pet_bad 6 s, poke 8 s, irritate 4 s, comfort 20 s, sudden 0.5 s, …
2. **Body.** First-order ODEs: hunger, sleep pressure S (Borbély two-process with a light/clock input), social need, boredom, grooming need, stress (corticosterone-like), touch need, neglect and (v5) **sleep debt**.
3. **Learning (prediction error, Rescorla–Wagner).**
   - `L_time[24]`: time of day → food (Gaussian hourly basis); `L += 0.3·(1 − L·φ)·φ` per feed.
   - `L_menu`: "the right-click menu means food".
   - `exp_pet` / `exp_poke`: what the approaching hand means. Updated by every stroke, click and poke; a hand that comes and does nothing slowly extinguishes them.
   - `bond`: trust in the user.
   - `hab`: startle habituation.
4. **Appraisal layer (v4).** A small hand-wired layer judges *what the hand is doing*, not just where it is. Units are leaky integrators over the raw kinematics. Speeds are in reference px/s (a 160 px bird); *near* = e^(−d/250 px).

   | Unit | Fires when | Mainly drives |
   |---|---|---|
   | `cursor_gentle` | 30–1400 px/s movement within ~2.5 bird heights. Habituates by up to 60 % over ~5 min of constant movement. | happy, playful (a moving "toy"), watch, play |
   | `cursor_still` | cursor resting close by | curious (tilts, peeks) |
   | `head_touch` | cursor resting on / moving slowly over head, crown, nape, cheek or neck | content (relax, lids droop), affection, comfort |
   | `irritation` | **frantic** = close × speed 1200→2200 px/s × jitter 4→8 reversals/s. Capped at 1. | a bit angry (max ≈ 0.25), avoid_hand |
   | `comfort` | good strokes, head touch, food (+1.0) | calms: see 5 |

5. **Emotion CTRNN: 17 leaky-integrator sigmoid neurons.** For each neuron *i*:

   `net_i = Σ_f Wx[i,f]·x_f + Σ_j We[i,j]·e_j + b_i + η_i`
   `y_i ← y_i + (net_i − y_i)·(1 − e^(−h/τ_i))`, with `τ_i = rise_i` when rising and the decay constant below when falling
   `e_i = σ(y_i)`

   - `x` holds the 50 features (body, senses, appraisal, traces, learned expectations, mood).
   - `We` holds self-excitation (persistence), mutual inhibition (e.g. afraid ⟂ content) and excitation (e.g. playful → happy).
   - `η` is Ornstein–Uhlenbeck noise (τ = 90 s), giving spontaneous, non-repeating drift.
   - **Neuromodulated decay (v4).** Two modulators shorten the release time constant, in the style of GasNets:

     `τ_decay,i = tau_i / (1 + k_c,i · comfort + k_p,i · provocation)`

     - *comfort* (petting, head touch, food) acts on angry ×2.5, frustrated ×2.5, afraid ×2.5, startled ×1 and sad ×1, so anger lets go several times faster while the bird is being petted.
     - *provocation* (= poke + ½ pet_bad + sudden, i.e. clicks) acts on content ×6, affectionate ×4, sleepy ×3, happy ×2 and playful ×2, so a poke breaks a calm, cuddly state at once instead of being masked by it.

   Neurons: content, happy, playful, affectionate, curious, excited, proud, hungry, lonely, bored, frustrated, angry,
   afraid, startled, sad, sleepy, mischievous.
6. **Core affect and mood.** Activations are averaged into valence/arousal/stance. Mood is a 30-minute low-pass of that point and feeds back as optimistic or pessimistic bias.
7. **Behaviour.** 30 units.
   - **Motivation** = bias + emotion weights + feature weights + Lorenz-style urge − waning interest + persistence + noise, gated by minimum conditions.
   - **Choice:** softmax sampling when a clip ends; temperature rises with arousal.
   - **Priority ranks** let urgent behaviours cut in at any step: startle 3 > fear/threaten 2 > greet/enjoy_petting/approach_hand/avoid_hand 1.
   - **v4 stability** (`SELECTION`):
     - A running behaviour stays eligible down to 40 % of its entry gate (hysteresis).
     - A running priority behaviour is not swapped out by chance at a clip end while its own motivation is within 0.5 of the best alternative.
     - Without this, petting hovering at its threshold between strokes made the bird leave the scratch pose and come straight back.
   - **Clips:** each behaviour picks one of its baked clips, filtered by emotion bands, with no immediate repeats.
8. **Expression.**
   - Outputs: clip, playback time, crossfade, the live face layer (lid droop incl. head touch, pupil pinning), gaze interest, blinks, saccades, sound tokens, effect tokens, body-follow intent and petting feedback.
   - Pupil pinning (v4) is an excitement/aggression display. It uses a smooth envelope (no on/off threshold), a steady 2–3.5 Hz rhythm, and is off in calm or affectionate behaviours (resting, preening, being scratched).

There are no fixed timers. Everything happens because a state crossed a threshold or a Poisson process fired.

## Touch: what the bird does (v4 rules, 2026-10-29)

The rules: moving the cursor never causes real anger; only left clicks do. Petting and food calm the bird down; the
right-click menu is never a poke.

| You do | The engine receives | The bird |
|---|---|---|
| Bring the cursor close and hold it there | `cursor_still`, approach | **Curious**: peeks and tilts its head, then walks over and asks for a scratch |
| Move the cursor around normally near it, even across its body | `cursor_gentle`; hover strokes on body zones score ≥ 0 | **Happy / playful**: head bobs, tail shakes, play. Never angry (anger peak 0.01 in tests) |
| Rest the cursor on its head | `head_touch` | **Relaxes**: lids droop, contentment up, bows into your hand |
| Move the cursor up and down over the head | `pet(zone, speed)` ~4/s | **Head scratch** (`enjoy_petting` → `head_scratched`), hearts. Gentle to vigorous (up to ~1000 px/s) all count |
| Scrub frantically right on top of it | `irritation` | **A bit angry** (≈ 0.25 max): leans back, turns away. No lunges |
| Pet for minutes | satiation (dose vs tolerance) | Pleasure fades to zero and the bird moves on. Never unpleasant |
| **Left-click** anywhere (head included) | `tap(zone)` = a poke | **A bit angry** (head ≈ 0.4, belly ≈ 0.55): grumble, anger mark, lean back / puff |
| Click several times | taps add up in the poke trace | **Very angry** (≈ 1.0): angry puff, warning lunges, full anger display |
| Pet an angry bird | comfort; each stroke clears part of the provocation | **Calms**: anger 0.99 → 0.34 after 3 s → 0 after 5 s (no petting: still 0.99) |
| Offer a treat (menu) | comfort, `offer`, reward | **Calms**: anger 0.97 → 0.13 after 5 s, then eats happily |
| Right-click | `menu_open` | Nothing negative (a learned food cue) |
| Menu → Fly | `fly` | Takes off, hovers ~3.5 s, lands (v5) |
| Keep it awake late in the evening (petting, clicking, treats) | sleep debt builds | **Grumpy**: frustrated, quicker to anger, grumbles; less happy and playful. **A treat does not fix it** - only sleep does (v5) |
| Menu → Pet (head scratch) | `pet_session` (6 s hand-free scratch) | Enjoys the scratch. A poke ends it |
| Menu → Poke | `poke_once` (belly) | A bit angry |
| Drag the window | `drag_start/end` (held) | No fear, no anger for a bonded bird |
| After many pokes, bring the cursor close | `hand_bad` (learned) | Curious but **cautious** (wary lean-back clip), not angry. Petting retrains it |

Why the belly annoys most: owners are told to keep petting to the head and neck. Belly, tail and lower back are
hormonal hot spots, and grumbling, pinned eyes and lunges are the warning signs before a bite (Lafeber; PetMD).
See `genome.REFERENCES`.

### v5 changes (2026-10-29) vs v4

Vijai's requests: *"if I keep the bird awake, it gets sleep deprived and gets grumpy, even if I feed the food"*;
*"while head scratching and if I moved the cursor to the belly, the animations still look like scratching but the
bird makes noise"*; a **Fly** menu item; Good night / Good morning / Talk / Music removed from the menu.

- **Sleep debt** (`SLEEP_DEBT` in the genome). Raw sleep pressure
  `p = clamp(1.25 S + 0.85 max(night, 0.6 · bio_night) - 0.5)`.
  - Awake with `p` above 0.45: `debt += (1 - debt) · clamp((p - 0.45)/0.45) · dt / 1 h`, so about an hour of being kept
    up past bedtime gives ~63 %.
  - Woken while still sleepy: `+0.06 · p` each time.
  - Repaid only by sleep (τ 1 h; dozing τ 4 h; under a lamp ×1/0.6 slower). Closed app: τ 3 h (it slept meanwhile).
  - Effects: feature `sleep_debt` → frustrated +3.6, angry +1.8, sleepy +1.5, happy −1.5, playful −2.0, content −1.0;
    provocation features × (1 + 0.8 debt) (amygdala over-reactivity after sleep loss, Yoo et al. 2007); comfort, treats
    and offers × (1 − 0.85 debt) - so food no longer fixes the mood; the over-tired bird plays `grumpy_grumble` and
    grumbles; `sleep_drive += 0.5 debt` (it naps more readily).
  - Measured (unit test): debt 0.85 vs rested, 60 s with the cursor nearby: frustrated 0.38 vs 0.01, happy 0.03-0.06 vs
    0.2-0.4; 40 s after millet: frustrated 0.17-0.27 vs 0.002, happy 0.04-0.08 vs 0.74. An hour after bedtime with
    the lamp on: left alone → asleep, debt < 0.2; scratched awake every 20 s → debt > 0.4. Two hours of sleep: 0.8 → < 0.3.
- **The bird's own clock** (`bio_night`, 21:00-22:30 ramp, 06:00-07:30 ramp). With Good night gone, a bird whose
  person is still at the PC late in the evening (lamp on) now still feels it is night (at 60 %) and goes to sleep on
  its own unless kept busy.
- **The scratch ends when the hand leaves the head.** `scratching` = a good head stroke (quality > 0.15) in the last
  1.2 s, or the hand resting on the head, or a menu Pet session. Without it `enjoy_petting` is gated off and, if it is
  running, the bird leaves the pose at once (`_decide`, 0.3 s crossfade). Before: the pose lingered ~7 s (until the
  3 s petting trace decayed). Probe: cursor slides from head to belly → the pose ends after 1.23 s (8 seeds).
- **No sound without a moving beak.** See `docs/ARCHITECTURE.md` "Sounds and the beak". The plugin silences the
  head-scratch grind and spontaneous grinding, lifts the lip-sync opening to ≥ 22° (chirp 24, excited 26) and lists
  the quiet clips. During a scratch the bird is now silent; every mouth sound opens the beak 18-28° (probe: 0
  violations).
- **Fly** (`FLY`): see `docs/ARCHITECTURE.md` "Flight". A sequence like feeding (not interruptible), 5 s in total.
- Removed from the menu (events still accepted by the engine): `talk`, `lights_off`, `lights_on`, music.
- Verified: unit tests 24/24; the 26 interaction rules at S/M/L; `sim_day.py` with the 0.4 owner (only what the app
  can send: no Talk, Music or Good night; the owner leaves the PC at ~22:40), 4 days x 2 seeds: calm 40-46 %,
  social 13-18 %, play 6-12 %, negative 8-11 %, day-time naps 3-5 %, night sleep >= 99.6 %. It settles to sleep
  between ~21:35 and 22:40. An owner who stays at the PC and keeps visiting it until 22:40 makes it 'Grumpy'
  (sleep debt 0.4-0.7) for 15-75 min around 22:00-23:00 ('Exhausted' > 0.7 once in 8 nights, 16 min); by
  06:00 the debt is back to <= 0.08. `--legacy-evening` replays the pre-0.4 evening for comparison (same night sleep).

### v4 changes (2026-10-29) vs v3

- **Root cause of "it gets angry when I move the cursor".** In v3, hovering over the wing, belly, back or tail scored as a *bad stroke*, and any fast stroke scored as rough. Both fed straight into anger. With no clicks at all, moving around the bird reached anger 0.51 and gliding over its body 0.99. v4: strokes are never negative, and only clicks feed anger.
- **Appraisal layer and comfort/provocation neuromodulators** (above). New features: `cursor_gentle`, `cursor_still`, `head_touch`, `irritation`, `annoyed`, `comfort`.
- **Clicks.** Every left click is a poke, head included (`TAP`, `poke_gain` 0.25 so clicks add up). A click also ends a petting session, lifts the hand off the head and removes 95 % of the comfort.
- **Anger wiring.**
  - Removed from anger: `hand_bad` (the cursor's bad reputation) → now drives wariness and curiosity; `amb_neg`; and looming/petting/talk in `disturb_sleep`.
  - Added: `irritation` +3.0; and against anger, comfort −3, head touch −1.5, rewards −2/−3, offer −2.
  - Contentment inhibits anger half as much (0.5).
  - Lunges need anger ≥ 0.6, i.e. repeated clicking.
- **Petting.**
  - Zones: head/neck 0.85–1.0, chest 0.3, back 0.2, wing 0.15, beak 0.1, belly/tail/feet 0.
  - Good up to 1000 px/s, no pleasure by 1600 px/s.
  - Over-petting is satiation; an upset bird is calmed first and enjoys it after.
- **Personality.** Playfulness 0.85 (was 0.75), neuroticism 0.25 (was 0.35): a playful, easy-going bird.
- **Behaviour stability.** Hysteresis and the priority keep (above). `enjoy_petting` is held by `head_touch` between strokes; `approach_hand` is blocked while the hand is on the head. Head-scratch "excursions" in 6 × 90 s of intermittent scratching: gentle 0, brisk 0, vigorous 1 (a sneeze). Before: 0 / 2 / 6.
- **Menu.** `pet_session` and `poke_once`.

The plugin copy here is the runtime version. `SunConure3D/engine/` still holds v2 for the Blender demo bakes.

Verified on 2026-10-29:
- `test_desktop_touch.py`: 26/26 at S (8 seeds), M and L (4 seeds each).
- Unit tests: 15/15.
- `sim_day.py`, 2 days: calm 46 %, groom 12 %, social 13–15 %, play 9–14 %, explore 7 %, negative 8–9 %, night sleep ≥ 99.8 %, 59 distinct clips/day.
- `test_interaction.py`:
  - loving → affectionate 0.98;
  - neglect → sad 0.67, frustrated 0.62;
  - rough history → no anger at the approaching cursor (was 0.85 in v3, by design), wary instead.

## Memory: what the bird remembers

Saved by the core to `%APPDATA%\DesktopPets3D\pets\sun_conure\state.json` every 60 s, after a drag and at quit,
using an atomic replace. Only what `get_state()` returns:

| Field | Meaning | Changes with |
|---|---|---|
| `hunger` | 0..1 | time awake; treats |
| `S` | sleep pressure (Borbély process S) | awake time; sleep |
| `social` | need for company | being alone vs attention |
| `boredom`, `groom` | under-stimulation, preening need | time; play; preening |
| `stress` | corticosterone-like, decays over minutes | clicks and pokes up; petting and treats down |
| `touch` | need for physical affection | grows over ~90 min awake; good strokes fill it |
| `sleep_debt` | lost sleep, 0..1 (v5) | kept awake past bedtime / woken up; only sleep repays it |
| `neglect` | "ignored while my person is here" | unmet touch need while you are at the PC |
| `mood` | [valence, arousal], 30-min running mean | everything above |
| `bond` | trust in you, 0..1 (new bird: 0.6) | good strokes and feeding up; clicks and pokes down |
| `exp_pet`, `exp_poke` | learned meaning of the approaching hand (new bird: 0.35 / 0) | each stroke / click / poke (prediction error) |
| `L_time[24]` | expected food per hour of day | feeding times |
| `L_menu` | "menu means food" | whether opening the menu is followed by food |
| `personality` | neuroticism, extraversion, playfulness, volatility | stored for reference; the genome's values are used |
| `saved_at`, `version` | bookkeeping (version 5) | |

Transient, never stored: the appraisal units, comfort, irritation and other traces.

**On start** the engine fast-forwards the closed time (capped at 24 h):
- hunger, social and touch needs grow and sleep pressure decays; sleep debt is repaid (τ 3 h);
- neglect fades, because being away is not ignoring;
- mood relaxes towards neutral;
- a long absence triggers a reunion greeting.

**Not stored:** cursor positions or history, keystrokes, screen content, sounds, or anything outside this file.
Cursor distance, speed and jitter exist only in memory for the current frame.
