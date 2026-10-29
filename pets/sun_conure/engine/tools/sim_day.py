"""Simulate ConureMind over several days with a synthetic owner and report what emerges.

    C:\\Python315\\python.exe engine\\sim_day.py [days=4] [seed=1] [--png out.png] [--json out.json]

Owner model (work-from-home day; jittered every day): at the PC 07:45-12:15, 13:00-17:35, 19:30-22:40 with a
coffee break; cursor wanders, visits the bird ~4x/h (sometimes pets it); sunflower seed at ~12:15 (days 1-3,
skipped on the last day to test extinction/frustration), millet at ~17:30, petting session ~15:00, a poke burst on
day 2 at 16:00, Play at ~20:00, then the PC is left at ~22:40.
Only what the 0.4 app can send: no Talk, no Music, no Good night (lights_off) - the room goes dark when the owner
leaves the PC and the bird keeps its own body clock (bio_night). --legacy-evening restores the pre-0.4 evening
(talk x3, music 20:30-21:00, lights off ~22:45) for comparisons.
"""
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

import numpy as np

LEGACY_EVENING = '--legacy-evening' in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)                       # pets/<id>/engine (plugin layout)
MANIFEST = os.path.join(os.path.dirname(ENGINE), 'model', 'animations.json')
sys.path.insert(0, HERE)
sys.path.insert(0, ENGINE)
import genome as G                                   # noqa: E402
from conure_mind import ConureMind, clip_table_from_source, clip_table_from_manifest  # noqa: E402

ROOT = os.path.dirname(HERE)
DT = 0.5
GROUP_OF = {b: g for g, bs in G.GROUPS.items() for b in bs}


class Owner:
    def __init__(self, rng, day, days, skip_last=True):
        j = lambda m: rng.normal(0, m / 60.0)                      # noqa: E731  jitter in minutes -> hours
        self.rng = rng
        self.present = [(7.75 + j(10), 10.5 + j(5)), (10.75 + j(5), 12.25 + j(4)), (13.0 + j(8), 17.58 + j(6)),
                        (19.5 + j(15), 22.67 + j(8))]
        self.ev = []                                               # (hour, event)
        if day < days - 1 or not skip_last:
            t = 12.22 + j(4)
            self.ev += [(t - 0.001, 'menu_open'), (t, 'feed_sunflower')]
        t = 17.5 + j(8)
        self.ev += [(t - 0.001, 'menu_open'), (t, 'feed_millet')]
        t = 15.0 + j(15)
        self.pet_session = (t, t + rng.uniform(1.0, 2.0) / 60.0)
        self.poke_t = None
        if day == 1:
            t = 16.0 + j(5)
            self.poke_t = t
            self.ev += [(t + k * 0.0002, 'poke') for k in range(4)]
        t = 20.0 + j(10)
        if LEGACY_EVENING:                                         # pre-0.4 menu (Talk / Music / Good night)
            self.ev += [(t, 'talk'), (t + 0.004, 'talk'), (t + 0.01, 'talk'), (t + 0.25, 'play')]
            t = 20.5 + j(10)
            self.music = (t, t + 0.5)
            self.ev += [(22.75 + j(5), 'lights_off')]
        else:                                                      # 0.4 app: Play from the menu, music always 0
            self.ev += [(t + 0.25, 'play')]
            self.music = (0.0, 0.0)
        self.ev.sort()
        self.cur_d = 900.0
        self.visit = None                                          # (end_hour, pets?)
        self.last_input = 0.0
        self.next_pet = None

    def at_pc(self, hr):
        return any(a <= hr < b for a, b in self.present)

    def percepts(self, hr, dt):
        rng = self.rng
        present = self.at_pc(hr)
        if present:
            if rng.random() < dt / 4.0:                            # input every few s; occasional reading pauses
                self.last_input = 0.0 if rng.random() > 0.03 else -rng.uniform(30, 150)
            self.last_input += dt
            idle = max(0.0, self.last_input)
        else:
            idle = 3600.0
        speed = 0.0
        events = []
        if present:
            in_pet = self.pet_session[0] <= hr < self.pet_session[1]
            if self.poke_t and self.poke_t - 0.002 <= hr < self.poke_t + 0.002:   # cursor on the bird to poke it
                self.cur_d = 40.0
            if self.visit is None and (in_pet or rng.random() < dt * 4 / 3600.0):
                dur = rng.uniform(5, 25) if not in_pet else (self.pet_session[1] - hr) * 3600
                self.visit = (hr + dur / 3600.0, in_pet or rng.random() < 0.4)
                self.next_pet = hr + rng.uniform(1.5, 3.0) / 3600.0
            if self.visit:
                target, speed = rng.uniform(30, 110), rng.uniform(20, 140)
                if self.visit[1] and hr >= self.next_pet:
                    events.append('pet')
                    self.next_pet = hr + rng.uniform(1.5, 3.0) / 3600.0
                if hr >= self.visit[0]:
                    self.visit = None
            else:
                target, speed = rng.uniform(400, 1500), (rng.uniform(200, 1200) if rng.random() < 0.3 else 0.0)
            self.cur_d += (target - self.cur_d) * (1 - math.exp(-dt / 0.8))
        music = 1.0 if self.music[0] <= hr < self.music[1] else 0.0
        return dict(cursor_dist=self.cur_d if present else None, cursor_speed=speed, idle_s=idle, hour=hr % 24,
                    music=music), events


def run(days=4, seed=1, start_hour=6.0, verbose=True, skip_last=True):
    clips = clip_table_from_manifest(MANIFEST)
    rng = np.random.default_rng(seed + 1000)
    mind = ConureMind(clips, seed=seed, hour=start_hour)
    mind.h_max = DT
    if verbose and mind.missing:
        print('MISSING CLIPS', mind.missing)
    rec = []
    budget = defaultdict(lambda: defaultdict(float))
    stints, cur, cur_start = [], None, 0.0
    clip_counter = defaultdict(Counter)
    marks = []
    t0 = time.time()
    total = int(days * 24 * 3600 / DT)
    owner = None
    emax = np.zeros(len(mind.E))
    for k in range(total):
        hr_abs = start_hour + k * DT / 3600.0
        day = int((hr_abs - start_hour) // 24)
        if owner is None or owner.day != day:
            owner = Owner(rng, day, days, skip_last)
            owner.day = day
        hr = hr_abs - 24 * day                                     # hour within this sim day (may exceed 24)
        p, evs = owner.percepts(hr % 24 if hr >= 24 else hr, DT)
        p['hour'] = hr % 24
        while owner.ev and owner.ev[0][0] <= hr:
            evs.append(owner.ev.pop(0)[1])
        for ev in evs:
            mind.event(ev)
            marks.append((hr_abs, ev))
        out = mind.update(DT, p)
        b = out['behaviour']
        g = GROUP_OF.get(b, 'feeding' if b == 'feed' else 'other')
        budget[day][('day' if 8 <= hr % 24 < 22 else 'night' if (hr % 24 >= 23 or hr % 24 < 6.5) else 'edge', g)] += DT
        if out['changed']:
            clip_counter[day][out['clip']] += 1
        if b != cur:
            if cur is not None:
                stints.append((cur, hr_abs - cur_start))
            cur, cur_start = b, hr_abs
        emax = np.maximum(emax, mind.e)                             # max-pool emotions over each 10 s record
        if k % int(10 / DT) == 0:
            rec.append(dict(h=round(hr_abs, 4), b=b, clip=out['clip'], e=[round(float(v), 3) for v in emax],
                            d={kk: round(v, 3) for kk, v in out['drives'].items()},
                            mood=round(out['mood']['valence'], 3), V=round(out['affect']['valence'], 3),
                            A=round(out['affect']['arousal'], 3), food=round(out['learned']['food_now'], 3),
                            pet=round(out['learned']['pet'], 3), poke=round(out['learned']['poke'], 3)))
            emax[:] = 0.0
    if verbose:
        print(f'SIM {days} days in {time.time() - t0:.1f} s ({total} steps)')
    return mind, rec, budget, stints, clip_counter, marks


def window(rec, h0, h1):
    return [r for r in rec if h0 <= r['h'] < h1]


def analyse(mind, rec, budget, stints, clip_counter, marks, days):
    E = mind.E
    ei = {n: i for i, n in enumerate(E)}
    rep = {}
    # time budgets (daytime 08-22) per day
    tb = {}
    for d in range(days):
        tot = sum(v for (part, g), v in budget[d].items() if part == 'day')
        tb[d] = {g: round(v / tot, 3) for (part, g), v in sorted(budget[d].items()) if part == 'day'}
        nt = sum(v for (part, g), v in budget[d].items() if part == 'night')
        if nt:
            tb[d]['NIGHT_sleep'] = round(budget[d][('night', 'sleep')] / nt, 3)
    rep['time_budget_day'] = tb
    # stint statistics (non-sleep)
    durs = np.array([s for b, s in stints if b != 'sleep']) * 3600
    rep['stint_s'] = dict(n=len(durs), median=round(float(np.median(durs)), 1), mean=round(float(durs.mean()), 1),
                          cv=round(float(durs.std() / durs.mean()), 2), p95=round(float(np.percentile(durs, 95)), 1))
    # clip variety
    rep['distinct_clips_per_day'] = {d: len(c) for d, c in clip_counter.items()}
    rep['top_clips_day2'] = clip_counter[min(2, days - 1)].most_common(12)
    # responses to events
    def peak(h, name, span=0.01):
        w = window(rec, h, h + span)
        return round(max(r['e'][ei[name]] for r in w), 3) if w else None
    feeds = [(h, e) for h, e in marks if e.startswith('feed_')]
    rep['feeding'] = [dict(day=int((h - 6) // 24), kind=e, excited=peak(h, 'excited', 0.008),
                           happy_after=peak(h + 0.005, 'happy', 0.03), arousal=max(r['A'] for r in window(rec, h, h + 0.01)))
                      for h, e in feeds]
    # anticipation of the habitual noon feed: 11:40-12:12 each day
    rep['anticipation_noon'] = []
    for d in range(days):
        w = window(rec, 24 * d + 11.67, 24 * d + 12.2)
        if w:
            rep['anticipation_noon'].append(dict(day=d, food_expect=round(float(np.mean([r['food'] for r in w])), 3),
                                                 excited=round(float(np.mean([r['e'][ei['excited']] for r in w])), 3),
                                                 hungry=round(float(np.mean([r['e'][ei['hungry']] for r in w])), 3),
                                                 asks=sum(1 for r in w if r['b'] in ('request_food', 'anticipate'))))
    d = days - 1
    w = window(rec, 24 * d + 12.25, 24 * d + 13.0)
    rep['no_feed_last_day'] = dict(frustrated=round(max(r['e'][ei['frustrated']] for r in w), 3),
                                   requests=sum(1 for r in w if r['b'] in ('request_food', 'anticipate', 'frustration')))
    pokes = [h for h, e in marks if e == 'poke']
    if pokes:
        h = pokes[0]
        rep['poke'] = dict(startled=peak(h, 'startled', 0.003), angry=peak(h, 'angry', 0.01),
                           afraid=peak(h, 'afraid', 0.01),
                           behaviours=sorted({r['b'] for r in window(rec, h, h + 0.02)}),
                           exp_poke_after=window(rec, h + 0.05, h + 0.06)[0]['poke'])
    # absence 17:35-19:30 on day 1
    d = min(1, days - 1)
    w = window(rec, 24 * d + 17.7, 24 * d + 19.45)
    rep['absence'] = dict(lonely_max=round(max(r['e'][ei['lonely']] for r in w), 3),
                          social_need_max=max(r['d']['social'] for r in w),
                          calls=sum(1 for r in w if r['b'] == 'contact_call'),
                          sad_max=round(max(r['e'][ei['sad']] for r in w), 3))
    greets = []
    for i in range(1, len(rec)):
        if rec[i]['b'] == 'greet' and rec[i - 1]['b'] != 'greet':
            greets.append(round(rec[i]['h'] % 24, 2))
    rep['greet_times'] = greets[:12]
    rep['clip_starts_per_day'] = {k: {d: clip_counter[d].get(k, 0) for d in clip_counter} for k in
                                  ('greet', 'startle_flinch', 'warn_lunge', 'angry_puff', 'knock_screen', 'lonely_call',
                                   'head_scratched', 'ask_head_scratch', 'playful_crouch', 'show_off_strut', 'sneeze')}
    # emotion occupancy (dominant > 0.25) daytime
    dom = Counter()
    for r in rec:
        if 8 <= r['h'] % 24 < 22:
            i = int(np.argmax(r['e']))
            dom[E[i] if r['e'][i] > 0.25 else 'neutral'] += 1
    tot = sum(dom.values())
    rep['dominant_emotion_daytime'] = {k: round(v / tot, 3) for k, v in dom.most_common()}
    nb = Counter(r['b'] for r in rec if (r['h'] % 24 >= 23 or r['h'] % 24 < 6.5) and r['h'] > 7)
    rep['night_behaviours'] = dict(nb.most_common(6))
    rep['final_learning'] = dict(bond=round(mind.bond, 3), L_menu=round(mind.L_menu, 3),
                                 exp_pet=round(mind.exp_pet, 3), exp_poke=round(mind.exp_poke, 3),
                                 L_time_peak_hour=int(np.argmax(mind.L_time)), L_time_peak=round(float(mind.L_time.max()), 3))
    return rep


# ----------------------------------------------------------------------------- picture of one day
GROUP_COL = dict(calm=(120, 170, 120), groom=(90, 160, 220), social=(240, 160, 60), play=(250, 220, 60),
                 explore=(170, 120, 220), negative=(220, 70, 70), sleep=(60, 60, 110), feeding=(250, 120, 200),
                 other=(128, 128, 128))
EMO_COL = dict(content=(130, 200, 130), happy=(255, 215, 0), playful=(255, 170, 40), affectionate=(255, 120, 170),
               curious=(80, 200, 220), excited=(255, 90, 0), proud=(200, 120, 255), hungry=(190, 140, 70),
               lonely=(120, 140, 255), bored=(150, 150, 150), frustrated=(230, 120, 80), angry=(230, 30, 30),
               afraid=(160, 60, 200), startled=(255, 255, 255), sad=(70, 90, 170), sleepy=(50, 50, 90),
               mischievous=(0, 230, 160))


def draw_day(rec, marks, E, day, path, start_hour=6.0):
    from PIL import Image, ImageDraw
    W, LM = 1440, 120
    rows = [('behaviour', 18), ('emotion', 18)] + [(n, 7) for n in E] + [('drives', 110), ('mood', 50)]
    Ht = 40 + sum(hh + 3 for _, hh in rows) + 30
    im = Image.new('RGB', (W + LM + 20, Ht), (28, 28, 30))
    d = ImageDraw.Draw(im)
    h0 = start_hour + 24 * day
    w = [r for r in rec if h0 <= r['h'] < h0 + 24]
    X = lambda h: LM + int((h - h0) / 24 * W)                     # noqa: E731
    d.text((LM, 8), f'ConureMind - simulated day {day + 1} (06:00 -> 06:00)', fill=(230, 230, 230))
    for hh in range(0, 25, 2):
        x = LM + int(hh / 24 * W)
        d.line([(x, 30), (x, Ht - 25)], fill=(55, 55, 60))
        d.text((x - 10, Ht - 20), f'{int((start_hour + hh) % 24):02d}:00', fill=(170, 170, 170))
    y = 36
    tops = {}
    for name, hh in rows:
        tops[name] = y
        d.text((6, y + (hh - 10) // 2 if hh > 10 else y - 2), name, fill=(200, 200, 200))
        y += hh + 3
    for r in w:
        x = X(r['h'])
        g = GROUP_OF.get(r['b'], 'feeding' if r['b'] == 'feed' else 'other')
        d.line([(x, tops['behaviour']), (x, tops['behaviour'] + 18)], fill=GROUP_COL[g])
        i = int(np.argmax(r['e']))
        c = EMO_COL[E[i]] if r['e'][i] > 0.25 else (70, 70, 70)
        d.line([(x, tops['emotion']), (x, tops['emotion'] + 18)], fill=c)
        for k, n in enumerate(E):
            v = r['e'][k]
            col = tuple(int(30 + v * (cc - 30)) for cc in EMO_COL[n])
            d.line([(x, tops[n]), (x, tops[n] + 7)], fill=col)
    for key, col in (('hunger', (190, 140, 70)), ('sleep', (140, 140, 255)), ('social', (255, 120, 170)),
                     ('boredom', (170, 170, 170)), ('groom', (90, 160, 220)), ('stress', (230, 50, 50))):
        pts = [(X(r['h']), tops['drives'] + 110 - int(r['d'][key] * 108)) for r in w]
        d.line(pts, fill=col, width=1)
    lx = W + LM - 300
    for i, (key, col) in enumerate((('hunger', (190, 140, 70)), ('sleep', (140, 140, 255)), ('social', (255, 120, 170)),
                                    ('boredom', (170, 170, 170)), ('groom', (90, 160, 220)), ('stress', (230, 50, 50)))):
        d.text((lx + (i % 3) * 100, tops['drives'] + 2 + (i // 3) * 12), key, fill=col)
    mid = tops['mood'] + 25
    d.line([(LM, mid), (LM + W, mid)], fill=(70, 70, 70))
    d.line([(X(r['h']), mid - int(r['mood'] * 60)) for r in w], fill=(255, 255, 255))
    d.line([(X(r['h']), mid - int(r['V'] * 22)) for r in w], fill=(120, 120, 120))
    for h, ev in marks:
        if h0 <= h < h0 + 24:
            x = X(h)
            d.line([(x, 30), (x, 34)], fill=(255, 255, 255))
            if ev in ('feed_sunflower', 'feed_millet', 'poke', 'lights_off', 'play'):
                d.text((x + 2, 22), ev.replace('feed_', ''), fill=(255, 255, 255))
    y = Ht - 36
    x = LM
    for g, col in GROUP_COL.items():
        d.rectangle([x, y, x + 10, y + 8], fill=col)
        d.text((x + 13, y - 2), g, fill=(200, 200, 200))
        x += 85
    im.save(path)
    return path


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    days = int(args[0]) if args else 4
    seed = int(args[1]) if len(args) > 1 else 1
    mind, rec, budget, stints, cc, marks = run(days, seed)
    rep = analyse(mind, rec, budget, stints, cc, marks, days)
    print(json.dumps(rep, indent=1, default=str))
    if '--png' in sys.argv:
        out = sys.argv[sys.argv.index('--png') + 1]
        for d in range(days):
            print('PNG', draw_day(rec, marks, mind.E, d, out.replace('.png', f'_day{d + 1}.png')))
    if '--json' in sys.argv:
        with open(sys.argv[sys.argv.index('--json') + 1], 'w') as f:
            json.dump(dict(report=rep, rec=rec, marks=marks, emotions=mind.E), f)
