"""Clip tables: every pet ships model/animations.json next to its GLB (written by the Blender export).

Shared format (per clip):  seconds, loop, events_s {name: t | [t...]}, root_motion {velocity_m_s | end_offset_m},
blend_in_s, category. Only 'seconds' and 'loop' are required.
"""
import json


def load_clip_table(path):
    with open(path, encoding='utf-8') as f:
        man = json.load(f)
    clips = man.get('clips', man)
    out = {}
    for name, c in clips.items():
        ev = []
        for k, v in (c.get('events_s') or {}).items():
            for t in (v if isinstance(v, list) else [v]):
                ev.append((float(t), k))
        out[name] = dict(dur=float(c['seconds']), loop=bool(c.get('loop', True)), events=sorted(ev),
                         blend_in=float(c.get('blend_in_s', 0.3)), category=c.get('category', ''),
                         root_motion=c.get('root_motion'))
    return out


def walk_speed(clip_info):
    """Forward speed (m/s) of an in-place walk clip, else 0."""
    rm = (clip_info or {}).get('root_motion') or {}
    v = rm.get('velocity_m_s')
    if not v:
        return 0.0
    return float(sum(x * x for x in v) ** 0.5)
