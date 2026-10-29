"""Interaction scenarios for ConureMind v2 (touch & the hand): does the way you pet the bird decide how it reacts
when the cursor comes close?

    C:\\Python315\\python.exe engine\\test_interaction.py [seeds=8]

History (3 h at the PC, cursor mostly far away), then the PROBE: cursor parked far for 60 s, glides to the bird in
1.5 s and hovers 8 s without petting. Reported: peak emotions in the probe, behaviours/clips, follow modes.
  loving   - every 6-10 min: 10-25 s of gentle head/cheek/nape scratches
  neglect  - never touches the bird
  rough    - every 6-10 min: fast strokes on back/tail/wings, now and then a poke
  overpet  - loving for 2 h, then one 3-minute non-stop petting session (does it get too much?)
Plus a zone/speed table of single-stroke quality for a relaxed, bonded bird.
"""
import os
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)                       # pets/<id>/engine (plugin layout)
MANIFEST = os.path.join(os.path.dirname(ENGINE), 'model', 'animations.json')
sys.path.insert(0, HERE)
sys.path.insert(0, ENGINE)
from conure_mind import ConureMind, clip_table_from_manifest  # noqa: E402

CLIPS = clip_table_from_manifest(MANIFEST)
DT = 0.25
EMO = ('excited', 'happy', 'affectionate', 'sad', 'angry', 'afraid', 'frustrated', 'lonely')


def history(mind, kind, rng, hours=3.0):
    t, d = 0.0, 900.0
    next_visit = rng.uniform(4, 8) * 60
    visit_end, pets = None, []
    overpet_at = 2.0 * 3600 if kind == 'overpet' else None
    log = []
    while t < hours * 3600:
        target, speed, ev = rng.uniform(600, 1300), 0.0, []
        if rng.random() < DT / 5:
            speed = rng.uniform(100, 900)
        if kind != 'neglect' and t >= next_visit and visit_end is None:
            visit_end = t + (rng.uniform(10, 25) if kind != 'rough' else rng.uniform(6, 15))
        if overpet_at is not None and overpet_at <= t < overpet_at + 180:
            visit_end = max(visit_end or 0, overpet_at + 180)
        if visit_end is not None:
            target = rng.uniform(30, 70)
            if d < 120:
                if kind in ('loving', 'overpet'):
                    if rng.random() < DT / 0.3:
                        ev.append(('pet', dict(zone=str(rng.choice(['head', 'cheek', 'nape', 'neck'])),
                                               speed=float(rng.uniform(80, 320)))))
                    speed = rng.uniform(80, 320)
                elif kind == 'rough':
                    if rng.random() < DT / 0.3:
                        ev.append(('pet', dict(zone=str(rng.choice(['back', 'tail', 'wing', 'head'])),
                                               speed=float(rng.uniform(800, 1600)))))
                    if rng.random() < DT / 12:
                        ev.append(('poke', {}))
                    speed = rng.uniform(800, 1600)
            if t >= visit_end:
                visit_end = None
                next_visit = t + rng.uniform(6, 10) * 60
        d += (target - d) * (1 - np.exp(-DT / 0.6))
        for name, kw in ev:
            mind.event(name, **kw)
        out = mind.update(DT, dict(cursor_dist=d, cursor_speed=speed, idle_s=0.5, hour=10 + t / 3600))
        if overpet_at is not None and overpet_at <= t < overpet_at + 200 and out['petting']:
            log.append((t - overpet_at, out['petting']['quality'], out['behaviour']))
        t += DT
    return log


def probe(mind, hour):
    res = dict(peak={k: 0.0 for k in EMO}, beh=Counter(), clips=Counter(), follow=Counter(), hand=[])
    t, d = 0.0, 900.0
    while t < 69.5:
        if t < 60:
            d = 900.0
        elif t < 61.5:
            d = 900.0 + (60.0 - 900.0) * (t - 60) / 1.5
        else:
            d = 60.0
        sp = 560.0 if 60 <= t < 61.5 else 0.0
        out = mind.update(DT, dict(cursor_dist=d, cursor_speed=sp, idle_s=0.5, hour=hour))
        if t >= 60:
            for k in EMO:
                res['peak'][k] = max(res['peak'][k], out['emotions'][k])
            res['beh'][out['behaviour']] += 1
            res['follow'][out['follow']['mode']] += 1
            if out['changed']:
                res['clips'][out['clip']] += 1
            res['hand'].append((out['hand']['good'], out['hand']['bad'], out['hand']['sad']))
        t += DT
    h = np.array(res['hand'])
    res['hand'] = tuple(np.round(h.max(0), 2))
    return res


def main(seeds=8):
    print('PROBE: cursor glides to the bird after a 3 h history (mean peak emotion over seeds; behaviours = share of probe time)')
    for kind in ('loving', 'neglect', 'rough', 'overpet'):
        peaks = {k: [] for k in EMO}
        beh, fol, clips, hands, extra = Counter(), Counter(), Counter(), [], []
        for s in range(seeds):
            rng = np.random.default_rng(100 + s)
            mind = ConureMind(CLIPS, seed=s, hour=10.0)
            mind.h_max = DT
            log = history(mind, kind, rng)
            st = dict(bond=mind.bond, exp_pet=mind.exp_pet, exp_poke=mind.exp_poke, touch=mind.touch,
                      neglect=mind.neglect, mood=mind.mood_v)
            r = probe(mind, 13.0)
            for k in EMO:
                peaks[k].append(r['peak'][k])
            beh.update(r['beh'])
            fol.update(r['follow'])
            clips.update(r['clips'])
            hands.append(r['hand'])
            extra.append(st)
            if kind == 'overpet' and s == 0:
                qs = [(round(tt), round(q, 2), b) for tt, q, b in log[::40]]
        tot = sum(beh.values())
        print(f'\n== {kind}')
        print('  state before probe:', {k: round(float(np.mean([e[k] for e in extra])), 3) for k in extra[0]})
        print('  peaks:', {k: f'{np.mean(v):.2f}+-{np.std(v):.2f}' for k, v in peaks.items()})
        print('  hand good/bad/sad max:', tuple(np.round(np.mean(hands, axis=0), 2)))
        print('  behaviours:', {k: round(v / tot, 2) for k, v in beh.most_common(6)})
        print('  follow:', {k: round(v / tot, 2) for k, v in fol.most_common()})
        print('  clips started:', dict(clips.most_common(8)))
        if kind == 'overpet':
            print('  3-min session (t s, stroke quality, behaviour):', qs)
    # stroke quality table
    mind = ConureMind(CLIPS, seed=0, hour=10.0, bond=0.7)
    mind.touch = 0.6
    print('\nSTROKE QUALITY (bond 0.7, touch need 0.6, fresh session)')
    for zone in ('head', 'cheek', 'neck', 'beak', 'chest', 'back', 'wing', 'tail'):
        row = [f'{mind.pet_quality(zone, sp)[0]:+.2f}' for sp in (20, 150, 400, 700, 1100, 1600)]
        print(f'  {zone:6s}', ' '.join(row), '   (speeds 20 150 400 700 1100 1600 px/s)')


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
