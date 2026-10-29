"""The plugin contract: what a pet's emotion engine must offer the core, and what the core gives it.

A pet plugin's engine package (pets/<id>/engine/__init__.py) exposes ONE factory:

    def create_engine(ctx: EngineContext) -> engine

The returned object must have the four methods of `EmotionEngine` below (inheriting from it is optional; duck typing
is checked by `check_engine`). The core calls them from the Qt main thread only, at ~30 Hz.

Everything the core reads from `update()` is listed in OUTPUT_DEFAULTS; missing keys fall back to those defaults, so a
simple engine can return only {'clip': ..., 'changed': ...} and still work.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

API_VERSION = 1

# --------------------------------------------------------------------------- what the core sends in
PERCEPTS = {
    'cursor_dist': 'px, mouse pointer to the pet\'s head as drawn on screen (None if unknown)',
    'cursor_approach': 'px/s the pointer moves TOWARDS the head (0 when it moves away or past)',
    'cursor_speed': 'px/s the pointer moves at all (path speed over ~0.25 s, any direction)',
    'cursor_jitter': 'direction reversals per second of the pointer over ~0.6 s (frantic scrubbing ~4-8, normal use < 1)',
    'cursor_over': 'True while the pointer is over the pet\'s silhouette (pixel-exact)',
    'cursor_zone': 'body zone under the pointer (pet.json rig.zones names, e.g. head, cheek, belly) or None',
    'pet_px': 'on-screen pet height in px (Small/Medium/Large) - divide px percepts by it to stay size-independent',
    'idle_s': 's since the last keyboard/mouse input anywhere in Windows (user presence)',
    'hour': 'local clock time as a float 0..24',
    'music': '0/1 music playing. The 0.4 host always sends 0 (the menu item was removed); kept for engines',
    'held': 'True while the user is carrying the pet (dragging its window)',
}

EVENTS = {
    'pet': 'kw zone=<zone>, speed=<px/s>: one stroke sample, sent ~4x per second while the pointer hovers over the pet '
           'and moves (no button pressed). This is how the user scratches the pet.',
    'tap': 'kw zone=<zone>: a single left click on the pet (the right button only opens the menu)',
    'poke': 'kw zone=<zone>: rapid clicking (3 clicks within 1.2 s)',
    'menu_open': 'the right-click menu was opened (a learned cue for food)',
    'drag_start': 'the user picked the pet up (press + move)', 'drag_end': 'put down again',
    '<menu event>': 'any id a pet lists in its own pet.json "menu" (sun conure: pet_session, poke_once, '
                    'feed_sunflower, feed_millet, play, fly)',
}

# --------------------------------------------------------------------------- what the core reads out
OUTPUT_DEFAULTS = dict(
    clip=None,            # clip name (must exist in the pet's animations.json / GLB)
    clip_time=0.0,        # s into the clip
    speed=1.0,            # playback rate
    loop=True,
    changed=False,        # True on the frame a NEW clip starts -> the renderer cross-fades
    crossfade=0.3,        # s
    behaviour='',         # name of the active behaviour (debug panel, fx rules)
    emotion='neutral',    # dominant emotion name
    emotions={},          # name -> 0..1 (fx rules, mood panel)
    affect={},            # valence/arousal/... (mood panel)
    mood={},
    drives={},            # name -> 0..1 (mood panel)
    learned={},
    face={},              # live face layer, e.g. pupil_small 0..1, lid_droop 0..1
    gaze=dict(cursor_weight=0.0, saccade=False),
    blink=None,           # None | 'fast' | 'slow'
    sounds=[],            # sound tokens (mapped to sound categories by the pet's sound_bank.json)
    fx=[],                # fx tokens (mapped to 2D effects by pet.json "fx.tokens")
    clip_events=[],       # [(clip, event_name)] crossed this frame (mapped to sounds)
    follow=dict(mode='idle', walk=False, eagerness=0.0, turn_deg_s=90.0, keep_px=None),
    petting=None,         # dict(quality -1..1, zone, ...) for the stroke just received
    hand={},              # anything the engine wants to show about how it sees the user's hand
)
FOLLOW_MODES = ('none', 'idle', 'watch', 'approach', 'avoid', 'confront', 'turn_away')


@dataclass
class EngineContext:
    """Handed to create_engine(). The engine must not import Qt or touch the window."""
    pet_id: str
    pet_dir: str                    # absolute path of pets/<id>
    manifest: dict                  # parsed pet.json
    clips: dict                     # clip table from animations.json (see app.clips.load_clip_table)
    data_dir: str                   # writable folder for this pet (state.json lives here, managed by the core)
    seed: int | None = None
    hour: float = 12.0
    options: dict = field(default_factory=dict)   # pet.json "engine.options"


class EmotionEngine(ABC):
    """Optional base class documenting the contract."""

    @abstractmethod
    def event(self, name, **kw):
        """A discrete user action (see EVENTS). Unknown names must be ignored, not raise."""

    @abstractmethod
    def update(self, dt, percepts):
        """Advance dt seconds with the current PERCEPTS; return a dict (see OUTPUT_DEFAULTS)."""

    @abstractmethod
    def get_state(self):
        """JSON-serialisable memory (needs, mood, learned associations, bond...). Saved by the core."""

    @abstractmethod
    def set_state(self, state, now=None, hour=None):
        """Restore get_state() output; `now` (unix time) lets the engine fast-forward the time the app was closed."""

    def info(self):
        """Optional: dict(name, version, emotions=[...], behaviours=[...]) for the mood panel and docs."""
        return {}


REQUIRED = ('event', 'update', 'get_state', 'set_state')


def check_engine(obj):
    missing = [m for m in REQUIRED if not callable(getattr(obj, m, None))]
    if missing:
        raise TypeError(f'emotion engine {type(obj).__name__} lacks {missing}')
    return obj


def normalize_output(out):
    """Fill in defaults so the core never KeyErrors on a minimal engine."""
    res = dict(OUTPUT_DEFAULTS)
    if out:
        res.update({k: v for k, v in out.items() if v is not None or k in ('blink', 'petting', 'clip')})
    f = dict(OUTPUT_DEFAULTS['follow'])
    f.update(res.get('follow') or {})
    if f['mode'] not in FOLLOW_MODES:
        f['mode'] = 'idle'
    res['follow'] = f
    g = dict(OUTPUT_DEFAULTS['gaze'])
    g.update(res.get('gaze') or {})
    res['gaze'] = g
    return res
