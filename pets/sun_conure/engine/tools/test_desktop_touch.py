"""Desktop interaction probes for the sun-conure plugin (v4 rules), through the real plugin path
(registry -> adapter -> ConureMind), at a given on-screen size.

    C:\\Python315\\python.exe pets\\sun_conure\\engine\\tools\\test_desktop_touch.py [seeds=6] [pet_px=130]

Vijai's rules (2026-10-29) as expectations. Fresh bird, 14:00, user present; percepts are what DesktopPets3D sends
(screen px for a bird pet_px tall; cursor_speed = path speed, cursor_jitter = direction reversals per second):
  CURSOR ONLY (no clicks) - never angry beyond 'a bit', and only for abnormal movement:
    approach    cursor glides in and rests close           -> curious, no anger / fear
    wander      normal movement around and over the bird   -> happy / playful, no anger
    hover_body  slow drift over belly / wing / tail        -> no anger
    head_rest   cursor resting on the head                 -> relaxes (content up, lids droop), no anger
    scratch     cursor moving up and down over the head    -> petting (enjoy_petting / head_scratched)
    scrub       frantic scrubbing right on the bird        -> a bit angry at most (no lunges)
    swoop       cursor rushes at the head                  -> alerted, not angry
    passby      fast one-way pass 120 px away              -> nothing negative
    longpet     2 min of scratching                        -> never unpleasant (satiation, not anger)
  CLICKS (left button) - the only real anger:
    head_click  one click on the head                      -> a bit angry
    belly1      one click on the belly                     -> a bit angry, shows it
    clicks5     five clicks in 4 s                         -> very angry
  CALMING:
    soothe      clicks5, then petting the head             -> anger fades much faster than without petting
    food        clicks5, then millet                       -> anger fades faster than without food
  MENU (right button):
    menu_open   right-click menu opened, nothing chosen    -> no anger
    menu_pet    menu 'Pet (head scratch)'                  -> enjoys petting
    menu_poke   menu 'Poke'                                -> a bit angry
  carry         window dragged 3 s                         -> no fear, no anger
Exit code 1 if an expectation fails.
"""
import math
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))       # DesktopPets3D/
sys.path.insert(0, ROOT)
from app.registry import discover  # noqa: E402

DT = 1 / 30
EMO = ('excited', 'happy', 'playful', 'curious', 'affectionate', 'content', 'angry', 'afraid', 'startled', 'frustrated')
NEG_BEH = ('threaten', 'avoid_hand', 'fear', 'frustration')
CURVE_T = (1, 2, 3, 5, 8)
BODY = ('wing', 'belly', 'chest', 'tail', 'back', 'wing')


def F(v, i):
    return v(i) if callable(v) else v


class Probe:
    def __init__(self, spec, seed, px):
        self.e = spec.create_engine(os.path.join(HERE, '_probe_data'), seed=seed, hour=14.0)
        self.px = px
        self.s = px / 160.0                     # scenario speeds/distances are written for a 160 px bird
        self.t = 0.0
        self.rec = []

    def step(self, secs, dist=800.0, approach=0.0, speed=0.0, jitter=0.0, over=False, zone=None, held=False,
             strokes=None, every=0.25):
        n = int(round(secs / DT))
        nxt = self.t
        for i in range(n):
            if strokes and self.t >= nxt:
                st = strokes(i)                         # None = the cursor is not over the bird: no stroke
                if st:
                    self.e.event('pet', zone=st[0], speed=st[1] * self.s)
                nxt = self.t + every
            out = self.e.update(DT, dict(cursor_dist=F(dist, i) * self.s, cursor_approach=F(approach, i) * self.s,
                                         cursor_speed=F(speed, i) * self.s, cursor_jitter=F(jitter, i),
                                         cursor_over=F(over, i), cursor_zone=F(zone, i),
                                         idle_s=1.0, hour=14.0, pet_px=self.px, held=held))
            self.t += DT
            self.rec.append(out)

    def tap(self, zone):
        self.e.event('tap', zone=zone)

    def window(self, start, end=None):
        r = self.rec[start:end]
        peaks = {k: max(o['emotions'][k] for o in r) for k in EMO}
        beh = Counter(o['behaviour'] for o in r)
        tot = sum(beh.values())
        clips = Counter(o['clip'] for o in r if o['changed'])
        return dict(peaks=peaks, beh={k: v / tot for k, v in beh.items()}, clips=dict(clips),
                    droop=max(o['face']['lid_droop'] for o in r),
                    quals=[o['petting']['quality'] for o in r if o.get('petting') and not o['petting'].get('tap')],
                    fx=Counter(f for o in r for f in o['fx']))

    def angry_at(self, idx):
        return self.rec[idx]['emotions']['angry']


def run(seed, spec, px):
    res = {}

    def fresh():
        p = Probe(spec, seed, px)
        p.step(60)                                     # settle: user at the PC, cursor far away
        return p

    # ---------------------------------------------------------------- cursor only
    p = fresh(); s = len(p.rec)
    p.step(1.5, dist=lambda i: 700 - 640 * min(1, i * DT / 1.5), approach=430, speed=450, jitter=0.2)
    p.step(6, dist=60, speed=0)
    res['approach'] = p.window(s)

    p = fresh(); s = len(p.rec)                       # circles around the bird, crossing its body now and then

    def wd(i):
        return 110 + 90 * math.sin(0.7 * i * DT)
    p.step(20, dist=wd, approach=lambda i: max(0.0, 63 * math.cos(0.7 * i * DT)),
           speed=lambda i: 350 + 250 * math.sin(1.3 * i * DT), jitter=0.6, over=lambda i: wd(i) < 70,
           zone=lambda i: BODY[int(i * DT * 3) % 6] if wd(i) < 70 else None,
           strokes=lambda i: (BODY[int(i * DT * 3) % 6], 400.0) if wd(i) < 70 else None)
    res['wander'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.step(10, dist=50, speed=200, jitter=1.0, over=True, zone=lambda i: BODY[int(i * DT) % 6],
           strokes=lambda i: (BODY[int(i * DT) % 6], 200.0))
    res['hover_body'] = p.window(s)

    p = fresh(); s = len(p.rec)
    base_content = p.rec[-1]['emotions']['content']
    p.step(8, dist=8, speed=0, over=True, zone='head')
    res['head_rest'] = p.window(s)
    res['head_rest']['content_gain'] = p.rec[-1]['emotions']['content'] - base_content

    p = fresh(); s = len(p.rec)                       # up and down over the head, ~1.5 Hz
    p.step(15, dist=12, speed=350, jitter=3.0, over=True, zone=lambda i: ('head', 'crown', 'nape')[i % 3],
           strokes=lambda i: (('head', 'crown', 'nape')[i % 3], 350.0))
    res['scratch'] = p.window(s)

    p = fresh(); s = len(p.rec)                       # frantic scrubbing right on the bird
    p.step(6, dist=15, speed=2200, jitter=10.0, over=True, zone='head', strokes=lambda i: ('head', 2200.0))
    p.step(4, dist=150, speed=0)
    res['scrub'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.step(0.3, dist=lambda i: max(50.0, 600 - 3000 * i * DT), approach=3000, speed=3000)
    p.step(2, dist=50)
    res['swoop'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.step(3, dist=120, approach=0.0, speed=1500, jitter=0.0); p.step(2, dist=300)
    res['passby'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.step(120, dist=12, speed=350, jitter=3.0, over=True, zone='head',
           strokes=lambda i: (('head', 'cheek', 'nape')[i % 3], 350.0))
    res['longpet'] = p.window(s)
    res['longpet_first'] = p.window(s, s + int(30 / DT))['beh'].get('enjoy_petting', 0)
    res['longpet_last'] = p.window(len(p.rec) - int(30 / DT))['beh'].get('enjoy_petting', 0)

    # ---------------------------------------------------------------- clicks
    p = fresh(); s = len(p.rec)
    p.tap('head'); p.step(6, dist=40)
    res['head_click'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.tap('belly'); p.step(6, dist=40)
    res['belly1'] = p.window(s)

    def clicks5(p):
        for z in ('belly', 'head', 'belly', 'wing', 'belly'):
            p.tap(z); p.step(0.8, dist=40)

    p = fresh(); s = len(p.rec)
    clicks5(p); p.step(3, dist=40)
    res['clicks5'] = p.window(s)

    # ---------------------------------------------------------------- calming (paired, same seed)
    ctrl = fresh(); clicks5(ctrl); c0 = len(ctrl.rec)
    ctrl.step(8, dist=40, speed=0)
    pet = fresh(); clicks5(pet); s0 = len(pet.rec)
    pet.step(8, dist=12, speed=350, jitter=3.0, over=True, zone='head', strokes=lambda i: (('head', 'crown')[i % 2], 350.0))
    res['curves'] = dict(ctrl=[ctrl.angry_at(c0 + int(t / DT) - 1) for t in CURVE_T],
                         pet=[pet.angry_at(s0 + int(t / DT) - 1) for t in CURVE_T])
    res['soothe'] = dict(ctrl=ctrl.angry_at(c0 + int(5 / DT)), pet=pet.angry_at(s0 + int(5 / DT)),
                         happy_pet=max(o['emotions']['happy'] + o['emotions']['affectionate'] for o in pet.rec[s0:]),
                         happy_ctrl=max(o['emotions']['happy'] + o['emotions']['affectionate'] for o in ctrl.rec[c0:]))
    food = fresh(); clicks5(food); f0 = len(food.rec)
    food.e.event('feed_millet'); food.step(8, dist=200)
    ctrl2 = fresh(); clicks5(ctrl2); g0 = len(ctrl2.rec)
    ctrl2.step(8, dist=200)
    res['food'] = dict(ctrl=ctrl2.angry_at(g0 + int(5 / DT)), food=food.angry_at(f0 + int(5 / DT)))
    res['curves']['food'] = [food.angry_at(f0 + int(t / DT) - 1) for t in CURVE_T]

    # ---------------------------------------------------------------- menu (right button)
    p = fresh(); s = len(p.rec)
    p.e.event('menu_open'); p.step(10, dist=20, speed=0, over=True, zone='chest')
    res['menu_open'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.e.event('pet_session'); p.step(6, dist=600)
    res['menu_pet'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.e.event('poke_once'); p.step(6, dist=600)
    res['menu_poke'] = p.window(s)

    p = fresh(); s = len(p.rec)
    p.e.event('drag_start'); p.step(3, dist=30, held=True); p.e.event('drag_end'); p.step(3, dist=60)
    res['carry'] = p.window(s)
    return res


def main(seeds=6, px=130.0):
    spec = next(p for p in discover() if p.id == 'sun_conure')
    runs = [run(s, spec, px) for s in range(seeds)]
    fails = []
    n = len(runs)

    def mp(key, emo):
        return sum(r[key]['peaks'][emo] for r in runs) / n

    def share(key, behs):
        return sum(sum(v for k, v in r[key]['beh'].items() if k in behs) for r in runs) / n

    def clip_starts(key, names):
        return sum(sum(v for k, v in r[key]['clips'].items() if k in names) for r in runs)

    for key in ('approach', 'wander', 'hover_body', 'head_rest', 'scratch', 'scrub', 'swoop', 'passby', 'longpet',
                'head_click', 'belly1', 'clicks5', 'menu_open', 'menu_pet', 'menu_poke', 'carry'):
        beh = Counter()
        clips = Counter()
        for r in runs:
            beh.update(r[key]['beh'])
            clips.update(r[key]['clips'])
        print(f'\n== {key}')
        print('  mean peaks:', {e: round(mp(key, e), 2) for e in EMO})
        print('  behaviours (mean share):', {k: round(v / n, 2) for k, v in beh.most_common(5)})
        print('  clips started:', dict(clips.most_common(6)))
    print('\n== soothe (angry 5 s after the 5th click):',
          [(round(r['soothe']['ctrl'], 2), round(r['soothe']['pet'], 2)) for r in runs], '(no petting, petting)')
    print('== food   (angry 5 s after the 5th click):',
          [(round(r['food']['ctrl'], 2), round(r['food']['food'], 2)) for r in runs], '(no food, millet)')
    for k in ('ctrl', 'pet', 'food'):
        cv = [sum(r['curves'][k][j] for r in runs) / n for j in range(len(CURVE_T))]
        print(f'== anger after 5 clicks, {k:4s} at +{CURVE_T} s:', [round(v, 2) for v in cv])
    print('== longpet enjoy_petting share first / last 30 s:',
          [(round(r['longpet_first'], 2), round(r['longpet_last'], 2)) for r in runs])

    def expect(cond, msg):
        print(('PASS ' if cond else 'FAIL ') + msg)
        if not cond:
            fails.append(msg)

    print()
    # cursor only
    expect(mp('approach', 'angry') < 0.1 and mp('approach', 'afraid') < 0.15, 'approach: no anger / fear when the cursor comes close')
    expect(mp('approach', 'curious') > 0.5, f'approach: curious (peak {mp("approach", "curious"):.2f} > 0.5)')
    expect(mp('approach', 'startled') < 0.35, 'approach: no startle at a normal approach speed')
    expect(mp('wander', 'angry') < 0.1, f'wander: normal cursor movement never angers (peak {mp("wander", "angry"):.2f})')
    hp = max(mp('wander', 'happy'), mp('wander', 'playful'))
    expect(hp > 0.5, f'wander: happy / playful (peak {hp:.2f} > 0.5)')
    expect(share('wander', NEG_BEH) < 0.05, f'wander: no negative behaviour (share {share("wander", NEG_BEH):.2f})')
    expect(mp('hover_body', 'angry') < 0.1,
           f'hover_body: gliding over belly/wing/tail is not a poke (peak {mp("hover_body", "angry"):.2f})')
    cg = sum(r['head_rest']['content_gain'] for r in runs) / n
    droop = sum(r['head_rest']['droop'] for r in runs) / n
    expect(cg > 0.1 and droop > 0.3 and mp('head_rest', 'angry') < 0.05,
           f'head_rest: relaxes (content +{cg:.2f}, lid droop {droop:.2f}), no anger')
    sc = share('scratch', ('enjoy_petting',))
    expect(sc > 0.5 and mp('scratch', 'angry') < 0.1, f'scratch: petting (enjoy_petting share {sc:.2f} > 0.5), no anger')
    a_scrub = mp('scrub', 'angry')
    expect(0.08 <= a_scrub <= 0.4, f'scrub: frantic movement = a bit angry (peak {a_scrub:.2f} in 0.08..0.4)')
    expect(clip_starts('scrub', ('warn_lunge', 'angry_full')) == 0, 'scrub: no lunges from cursor movement')
    expect(mp('swoop', 'angry') < 0.1, 'swoop: alerted at most, not angry')
    expect(mp('passby', 'angry') < 0.05 and mp('passby', 'startled') < 0.35, 'passby: moving past is nothing')
    qmin = min(min(r['longpet']['quals'] or [0]) for r in runs)
    expect(qmin >= 0 and mp('longpet', 'angry') < 0.1, f'longpet: never unpleasant (min stroke quality {qmin:.2f}), no anger')
    # clicks
    a_head = mp('head_click', 'angry')
    expect(0.2 <= a_head <= 0.6, f'head_click: a bit angry (peak {a_head:.2f} in 0.2..0.6)')
    a1 = mp('belly1', 'angry')
    expect(0.25 <= a1 <= 0.65, f'belly1: a bit angry (peak {a1:.2f} in 0.25..0.65)')
    expect(share('belly1', ('threaten', 'avoid_hand')) > 0.2, 'belly1: shows it (threaten / avoid)')
    lunges1 = clip_starts('belly1', ('warn_lunge', 'angry_full')) + clip_starts('head_click', ('warn_lunge', 'angry_full'))
    expect(lunges1 <= n, f'one click: rarely a lunge ({lunges1} lunges in {2 * n} single clicks)')
    a5 = mp('clicks5', 'angry')
    expect(a5 > 0.8, f'clicks5: repeated clicking = very angry (peak {a5:.2f} > 0.8)')
    # calming
    rs = [r['soothe']['pet'] / max(1e-6, r['soothe']['ctrl']) for r in runs]
    expect(sum(rs) / n < 0.5, f'soothe: petting halves the remaining anger at +5 s (ratio {sum(rs) / n:.2f} < 0.5)')
    hpet = sum(r['soothe']['happy_pet'] - r['soothe']['happy_ctrl'] for r in runs) / n
    expect(hpet > 0.15, f'soothe: petting turns it happy / affectionate again (+{hpet:.2f})')
    rf = [r['food']['food'] / max(1e-6, r['food']['ctrl']) for r in runs]
    expect(sum(rf) / n < 0.7, f'food: a treat lowers the anger (ratio {sum(rf) / n:.2f} < 0.7)')
    # menu
    expect(mp('menu_open', 'angry') < 0.05, f'menu_open: right-click is never a poke (angry peak {mp("menu_open", "angry"):.2f})')
    expect(share('menu_pet', ('enjoy_petting',)) > 0.4 and mp('menu_pet', 'angry') < 0.05, 'menu_pet: enjoys the scratch')
    am = mp('menu_poke', 'angry')
    expect(0.25 <= am <= 0.65, f'menu_poke: a bit angry (peak {am:.2f})')
    expect(mp('carry', 'afraid') < 0.3 and mp('carry', 'angry') < 0.15, 'carry: no fear, no anger when carried')
    return 1 if fails else 0


if __name__ == '__main__':
    a = [x for x in sys.argv[1:]]
    sys.exit(main(int(a[0]) if a else 6, float(a[1]) if len(a) > 1 else 130.0))
