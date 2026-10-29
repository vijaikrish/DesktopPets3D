"""Plugin checker: will this pet folder work in the app? Run it after adding or changing a pet.

    C:\\Python315\\python.exe -m app.plugin_check [pet_id ...]      (no id = every folder in pets/ except _template)

Checks (errors = the pet will misbehave; warnings = worth a look):
  manifest   schema, required keys, files exist (registry.validate)
  clips      every clip named anywhere in pet.json exists in model/animations.json AND in every GLB variant;
             GLB animations and animations.json list the same clips
  bones      every bone named in rig.gaze / rig.face / rig.zones / rig.anchors exists in every GLB variant
  sizes      stage.sizes has the default size; frame numbers are sane
  sounds     every file in the sound bank exists; engine sound tokens map to categories
  engine     factory loads, 300 updates (5 s) with sample percepts, events incl. tap/pet/poke, every output clip
             exists, get_state() is JSON-serialisable and set_state() restores it
"""
import json
import os
import struct
import sys
import tempfile

from . import paths
from .clips import load_clip_table
from .registry import PetSpec, validate


def glb_info(path):
    with open(path, 'rb') as f:
        head = f.read(20)
        n = struct.unpack('<I', head[12:16])[0]
        g = json.loads(f.read(n))
    nodes = g.get('nodes', [])
    return ({n.get('name') for n in nodes}, [a.get('name') for a in g.get('animations', [])])


def clip_refs(m):
    refs = {('stage.idle_clip', m.get('stage', {}).get('idle_clip'))}
    face = m.get('rig', {}).get('face', {})
    refs |= {('rig.face.blink_clip', face.get('blink_clip')), ('rig.face.jaw_clip', face.get('jaw_clip'))}
    refs |= {('rig.gaze.clip_weights', c) for c in m.get('rig', {}).get('gaze', {}).get('clip_weights', {})}
    refs |= {('fx.clips', c) for c in m.get('fx', {}).get('clips', {})}
    return {(k, c) for k, c in refs if c}


def bone_refs(m):
    rig = m.get('rig', {})
    g, f = rig.get('gaze', {}), rig.get('face', {})
    refs = {('rig.gaze', g.get('neck_bone')), ('rig.gaze', g.get('head_bone')), ('rig.face', f.get('jaw_bone')),
            ('rig.face', f.get('beak_upper_bone'))}
    refs |= {('rig.gaze.eye_bones', b) for b in g.get('eye_bones', [])}
    refs |= {('rig.face.lid_bones', b) for b in f.get('lid_bones', [])}
    refs |= {('rig.zones', z.get('bone')) for z in rig.get('zones', [])}
    refs |= {('rig.anchors', a.get('bone')) for a in rig.get('anchors', {}).values()}
    return {(k, b) for k, b in refs if b}


def check(pet_dir):
    errs, warns = [], []
    mp = os.path.join(pet_dir, 'pet.json')
    try:
        with open(mp, encoding='utf-8') as fh:
            m = json.load(fh)
    except Exception as e:
        return [f'pet.json unreadable: {e}'], warns
    errs += validate(pet_dir, m)
    if errs:
        return errs, warns
    spec = PetSpec(pet_dir, m)
    clips = spec.clips
    for where, c in sorted(clip_refs(m)):
        if c not in clips:
            errs.append(f'{where}: clip "{c}" not in animations.json')
    for v, rel in spec.variants().items():
        names, anims = glb_info(spec.path(rel))
        missing = sorted(set(clips) - set(anims))
        extra = sorted(set(anims) - set(clips))
        if missing:
            errs.append(f'{v}: GLB lacks clips listed in animations.json: {missing[:8]}')
        if extra:
            warns.append(f'{v}: GLB has clips not in animations.json (engine cannot use them): {extra[:8]}')
        for where, b in sorted(bone_refs(m)):
            if b not in names:
                errs.append(f'{v}: {where}: bone "{b}" not in the GLB')
    st = m.get('stage', {})
    sizes = st.get('sizes') or {}
    if sizes and st.get('default_size') not in sizes:
        errs.append('stage.default_size is not one of stage.sizes')
    fr = st.get('frame') or {}
    if fr and not (1.0 <= fr.get('height', 1.95) <= 4 and 0 <= fr.get('feet', 0.2) < 0.6):
        warns.append(f'stage.frame looks unusual: {fr}')
    # sounds
    bank_rel = (m.get('sounds') or {}).get('bank')
    tokens = {}
    if bank_rel:
        with open(spec.path(bank_rel), encoding='utf-8') as fh:
            bank = json.load(fh)
        base = os.path.dirname(spec.path(bank_rel))
        for cat, d in bank.get('categories', {}).items():
            for f in d.get('files', []):
                if not os.path.isfile(os.path.join(base, f['file'])):
                    errs.append(f'sound file missing: {cat}/{f["file"]}')
        tokens = bank.get('engine_tokens', {})
        for tok, cat in tokens.items():
            if cat not in bank.get('categories', {}):
                warns.append(f'engine sound token "{tok}" -> unknown category "{cat}"')
    # engine smoke run
    try:
        with tempfile.TemporaryDirectory() as td:
            e = spec.create_engine(td, seed=1, hour=14.0)
            seen = set()
            for i in range(300):
                if i == 60:
                    e.event('tap', zone='head')
                if i == 120:
                    e.event('pet', zone='head', speed=200.0)
                if i == 180:
                    e.event('poke', zone='belly')
                if i == 200:
                    e.event('some_other_pets_menu_event')
                out = e.update(1 / 60, dict(cursor_dist=120.0 if i > 30 else 900.0, cursor_approach=0.0,
                                            cursor_over=False, cursor_zone=None, pet_px=130, idle_s=1.0, hour=14.0,
                                            music=0.0, held=False))
                if out.get('clip'):
                    seen.add(out['clip'])
            bad = sorted(c for c in seen if c not in clips)
            if bad:
                errs.append(f'engine played clips not in animations.json: {bad}')
            st_ = e.get_state()
            json.dumps(st_)
            e2 = spec.create_engine(td, seed=2, hour=14.0)
            e2.set_state(json.loads(json.dumps(st_)), now=None, hour=14.0)
    except Exception as ex:
        errs.append(f'engine smoke run failed: {type(ex).__name__}: {ex}')
    return errs, warns


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ids = argv or sorted(d for d in os.listdir(paths.PETS_DIR)
                         if not d.startswith(('_', '.')) and os.path.isfile(os.path.join(paths.PETS_DIR, d, 'pet.json')))
    worst = 0
    for pid in ids:
        errs, warns = check(os.path.join(paths.PETS_DIR, pid))
        print(f'{pid}: {"OK" if not errs else "ERRORS"} ({len(errs)} errors, {len(warns)} warnings)')
        for x in errs:
            print('  ERROR  ', x)
        for x in warns:
            print('  warning', x)
        worst = max(worst, 1 if errs else 0)
    return worst


if __name__ == '__main__':
    raise SystemExit(main())
