"""Fast offline checks. Run: C:/Python315/python.exe -m unittest discover -s tests -v"""
import json
import os
import tempfile
import unittest

from app import paths
from app.fx_director import FxDirector
from app.plugin_api import normalize_output
from app.plugin_check import check
from app.registry import discover
from app.sound_bank import SoundBank
from app.storage import PetMemory, Settings

P = dict(cursor_dist=300.0, cursor_approach=0.0, idle_s=8.0, hour=14.0, pet_px=130)


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pet = next(p for p in discover() if p.id == 'sun_conure')

    def engine(self, td, seed=22):
        return self.pet.create_engine(td, seed=seed, hour=14.0)

    def run_for(self, e, secs, **kw):
        outs = []
        for _ in range(int(secs * 30)):
            outs.append(e.update(1 / 30, {**P, **kw}))
        return outs

    def test_plugin_manifest_and_clip_coverage(self):
        self.assertEqual(len(self.pet.clips), 72)
        self.assertEqual(self.pet.m['stage']['default_size'], 'S')
        self.assertEqual(self.pet.m['stage']['sizes'], {'S': 130, 'M': 190, 'L': 255})
        self.assertNotIn('perch', self.pet.m['stage'])                    # the branch is gone
        for name, c in self.pet.clips.items():
            self.assertGreater(c['dur'], 0, name)

    def test_plugin_check_passes_and_catches_errors(self):
        errs, _ = check(self.pet.dir)
        self.assertEqual(errs, [])
        with tempfile.TemporaryDirectory() as td:                         # a broken copy must be caught
            d = os.path.join(td, 'brokenpet')
            os.makedirs(d)
            m = json.loads(json.dumps(self.pet.m))
            rel = lambda r: os.path.relpath(self.pet.path(r), d).replace(os.sep, '/')
            m['id'] = 'brokenpet'
            m['model']['variants'] = {k: rel(v) for k, v in m['model']['variants'].items()}
            m['model']['clips'] = rel(m['model']['clips'])
            m['engine']['package'] = rel('engine')
            m['sounds']['bank'] = rel(m['sounds']['bank'])
            m['rig']['zones'][0]['bone'] = 'no_such_bone'
            m['fx']['clips']['no_such_clip'] = [{'kind': 'heart', 'rate_hz': 1}]
            with open(os.path.join(d, 'pet.json'), 'w') as fh:
                json.dump(m, fh)
            errs, _ = check(d)
            self.assertTrue(any('no_such_bone' in x for x in errs), errs)
            self.assertTrue(any('no_such_clip' in x for x in errs), errs)

    def test_engine_step_events_restore(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            e.event('feed_sunflower')
            out = e.update(0.1, P)
            self.assertIn(out['clip'], self.pet.clips)
            self.assertEqual(len(out['emotions']), 17)
            st = e.get_state()
            e2 = self.engine(td)
            e2.set_state(st, now=st['saved_at'], hour=14.0)
            self.assertAlmostEqual(e2.get_state()['bond'], st['bond'])

    def test_new_bird_is_hand_tame(self):
        with tempfile.TemporaryDirectory() as td:
            st = self.engine(td).get_state()
            self.assertAlmostEqual(st['bond'], 0.6)
            self.assertAlmostEqual(st['exp_pet'], 0.35)

    def test_cursor_close_is_not_a_threat(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            self.run_for(e, 30, cursor_dist=900.0)
            outs = self.run_for(e, 6, cursor_dist=50.0, cursor_approach=0.0)
            self.assertLess(max(o['emotions']['angry'] for o in outs), 0.15)
            self.assertLess(max(o['emotions']['afraid'] for o in outs), 0.15)

    def test_head_scratch_vs_belly_tap(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            self.run_for(e, 20)
            beh = []
            for i in range(15 * 4):                                         # 15 s of gentle hover-scratches
                e.event('pet', zone='head', speed=300.0)
                beh += [o['behaviour'] for o in self.run_for(e, 0.25, cursor_dist=15.0)]
            self.assertGreater(beh.count('enjoy_petting') / len(beh), 0.5)
            e2 = self.engine(td, seed=5)
            self.run_for(e2, 20)
            e2.event('tap', zone='belly')
            outs = self.run_for(e2, 4, cursor_dist=40.0)
            self.assertLess(outs[0]['petting']['quality'], -0.4)
            self.assertIn('anger', outs[0]['fx'])                           # immediate visible feedback
            self.assertIn('grumble', outs[0]['sounds'])                     # ... and audible
            self.assertGreater(max(o['emotions']['angry'] for o in outs), 0.25)
            self.assertTrue({'avoid_hand', 'threaten'} & {o['behaviour'] for o in outs})

    def test_cursor_movement_never_angers(self):
        """v4 (Vijai): moving the cursor near / over the bird - even over belly and tail - is never a poke."""
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            self.run_for(e, 20)
            angry = []
            for i in range(10 * 4):
                zone = ('wing', 'belly', 'tail', 'chest')[i % 4]
                e.event('pet', zone=zone, speed=400.0)
                angry += [o['emotions']['angry'] for o in self.run_for(e, 0.25, cursor_dist=40.0, cursor_speed=400.0,
                                                                          cursor_jitter=1.0, cursor_over=True,
                                                                          cursor_zone=zone)]
            self.assertLess(max(angry), 0.1)
            # gentle movement nearby = happy / playful
            outs = self.run_for(e, 8, cursor_dist=150.0, cursor_speed=400.0, cursor_jitter=0.5)
            self.assertGreater(max(max(o['emotions']['happy'], o['emotions']['playful']) for o in outs), 0.5)

    def test_frantic_cursor_is_only_a_bit_annoying(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            self.run_for(e, 20)
            outs = self.run_for(e, 6, cursor_dist=10.0, cursor_speed=1500.0, cursor_jitter=10.0, cursor_over=True,
                                cursor_zone='head')
            peak = max(o['emotions']['angry'] for o in outs)
            self.assertGreater(peak, 0.05)
            self.assertLess(peak, 0.4)
            self.assertFalse({'warn_lunge', 'angry_full'} & {o['clip'] for o in outs})

    def test_head_click_is_a_poke_and_petting_calms(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            self.run_for(e, 20)
            e.event('tap', zone='head')
            outs = self.run_for(e, 3, cursor_dist=40.0)
            self.assertGreater(max(o['emotions']['angry'] for o in outs), 0.15)        # head click = poke (v4)
            for _ in range(5):                                                       # then really annoy it
                e.event('tap', zone='belly')
                self.run_for(e, 0.6, cursor_dist=40.0)
            self.assertGreater(e.mind.e[e.mind.ei['angry']], 0.8)
            for _ in range(5 * 4):                                                   # 5 s of head scratching
                e.event('pet', zone='head', speed=350.0)
                last = self.run_for(e, 0.25, cursor_dist=10.0, cursor_speed=350.0, cursor_jitter=3.0,
                                    cursor_over=True, cursor_zone='head')
            self.assertLess(last[-1]['emotions']['angry'], 0.2)

    def test_right_click_menu_and_menu_touch(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td)
            self.run_for(e, 20)
            e.event('menu_open')
            self.assertLess(max(o['emotions']['angry'] for o in self.run_for(e, 5)), 0.05)
            e.event('pet_session')
            self.assertIn('enjoy_petting', {o['behaviour'] for o in self.run_for(e, 5)})
            e.event('poke_once')                                                     # a poke ends the session
            self.assertEqual(e.mind.auto_pet, 0.0)
            self.assertGreater(max(o['emotions']['angry'] for o in self.run_for(e, 4)), 0.25)
        ids = [m['id'] for m in self.pet.m['menu']]
        self.assertIn('pet_session', ids)
        self.assertIn('poke_once', ids)

    def test_adapter_is_size_independent(self):
        with tempfile.TemporaryDirectory() as td:
            near = []
            for px in (130, 255):                                           # same physical gesture at S and L
                e = self.engine(td, seed=3)
                e.update(1 / 30, {**P, 'pet_px': px, 'cursor_dist': 0.8 * px})
                near.append(e.mind.near)
            self.assertAlmostEqual(near[0], near[1], places=6)

    def test_sound_bank_and_selection(self):
        s = SoundBank(self.pet)
        self.assertTrue(s.ok)
        self.assertEqual(sum(len(c.get('files', [])) for c in s.cats.values()), 86)
        c = s._pick('chirp', arousal=0.8)
        self.assertTrue(c and c['url'].startswith('/pets/sun_conure/sounds/bank/'))
        self.assertGreater(c['dur'], 0)

    def test_fx_rules_cooldown_and_defaults(self):
        f = FxDirector(self.pet)
        spawns, levels = f.step(0.016, {'fx': ['anger'], 'emotions': {'sad': 0.9}, 'clip': 'idle_breathe', 'clip_time': 0.1})
        self.assertTrue(any(x['kind'] == 'smoke' for x in spawns))
        self.assertIsNone(spawns[0]['anchor'])                              # JS picks the kind's own anchor
        self.assertGreater(levels['rain_cloud'], 0.8)
        hearts = 0
        for _ in range(10):                                                 # a heart token every frame for 0.16 s
            sp, _ = f.step(0.016, {'fx': ['heart'], 'emotions': {}, 'clip': 'idle_breathe', 'clip_time': 0.2})
            hearts += sum(1 for x in sp if x['kind'] == 'heart')
        self.assertEqual(hearts, 1)                                         # cooldown 0.45 s
        n = normalize_output({'clip': 'idle_breathe'})
        self.assertEqual(n['follow']['mode'], 'idle')

    def test_storage_isolated_and_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get('DP3D_DATA')
            os.environ['DP3D_DATA'] = td
            try:
                settings = Settings(); settings.pet('sun_conure')['size'] = 'L'; settings.save()
                self.assertEqual(Settings().pet('sun_conure')['size'], 'L')
                memory = PetMemory('sun_conure'); memory.save({'bond': 0.73})
                self.assertAlmostEqual(memory.load()['engine']['bond'], 0.73)
                self.assertTrue(memory.path.startswith(td))
            finally:
                if old is None:
                    os.environ.pop('DP3D_DATA', None)
                else:
                    os.environ['DP3D_DATA'] = old

    def test_web_assets_present_and_branch_removed(self):
        js = os.path.join(paths.WEB_DIR, 'js')
        for f in ('pet.js', 'stage.js', 'rig.js', 'touch.js', 'fx.js', 'audio.js'):
            self.assertTrue(os.path.isfile(os.path.join(js, f)), f)
        self.assertFalse(os.path.exists(os.path.join(js, 'perch.js')))
        self.assertFalse(os.path.exists(os.path.join(js, 'panel.js')))        # v5: the panel is its own window

    # ------------------------------------------------------------------ v5 (2026-10-29)
    def test_menu_is_simplified_and_has_fly(self):
        ids = [m['id'] for m in self.pet.m['menu']]
        for gone in ('talk', 'lights_off', 'lights_on'):
            self.assertNotIn(gone, ids)
        self.assertEqual(ids, ['pet_session', 'poke_once', 'feed_sunflower', 'feed_millet', 'play', 'fly'])
        with open(os.path.join(paths.ROOT, 'app', 'desktop.py'), encoding='utf-8') as f:
            src = f.read()
        self.assertNotIn('Music is playing', src)

    def test_mouth_sounds_move_the_beak(self):
        bank = SoundBank(self.pet)
        for cat in bank.mouth:
            if cat in bank.cats and cat != 'grind':
                self.assertGreaterEqual(bank.jaw_for(cat), 18, cat)
        self.assertEqual(bank.tokens.get('grind'), '')                       # no spontaneous beak grinding
        t = 100.0
        # being scratched: a chirp waits, then plays (beak visible) as soon as the clip changes
        quiet = dict(clip='head_scratched', clip_time=0.5, behaviour='enjoy_petting', sounds=['chirp'], clip_events=[])
        self.assertEqual(bank.from_output(quiet, now=t), [])
        later = bank.from_output(dict(clip='idle_breathe', clip_time=0.1, behaviour='rest'), now=t + 0.3)
        self.assertEqual([c['category'] for c in later], ['chirp'])
        self.assertGreaterEqual(later[0]['jaw_deg'], 20)
        self.assertTrue(later[0]['env'])
        # a call that never gets a free beak is dropped
        bank.from_output(dict(quiet, clip_time=1.0), now=t + 5)
        out = [bank.from_output(dict(clip='head_scratched', clip_time=1.0 + k / 30), now=t + 5 + k / 30)
               for k in range(1, 30)]
        self.assertTrue(all(o == [] for o in out))
        self.assertEqual(bank.from_output(dict(clip='idle_breathe', clip_time=0.2), now=t + 7), [])
        # the head-scratch clip's own beak-grind events are silent (the beak barely moves: 4 deg)
        ev = dict(clip='head_scratched', clip_time=0.31, clip_events=[('head_scratched', 'grind')])
        self.assertEqual(bank.from_output(ev, now=t + 20), [])

    def test_baked_calls_without_lip_sync_open_the_beak_in_the_clip(self):
        bank = SoundBank(self.pet)
        jaw = glb_jaw_angles(self.pet.path(self.pet.m['model']['variants']['female']))
        with open(self.pet.path(self.pet.m['model']['clips']), encoding='utf-8') as f:
            clips = json.load(f)['clips']
        checked = 0
        for c, d in clips.items():
            for ev, times in (d.get('events_s') or {}).items():
                m = bank.events.get(f'{c}:{ev}') or bank.events.get(f'*:{ev}')      # same lookup as from_output
                if not m or not m.get('sound') or m.get('lip_sync', True) or not m.get('mouth', True) \
                        or not bank.is_mouth(m['sound']):
                    continue
                for t0 in (times if isinstance(times, list) else [times]):
                    self.assertGreaterEqual(jaw(c, t0, t0 + 0.35), 15, f'{c}:{ev}@{t0}')
                    checked += 1
        self.assertGreaterEqual(checked, 2)                 # squawk:call, warn_lunge:hiss

    def test_scratch_ends_when_the_hand_leaves_the_head(self):
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td, seed=4)
            self.run_for(e, 3)
            head = dict(cursor_dist=10.0, cursor_speed=300.0, cursor_jitter=3.0, cursor_over=True, cursor_zone='head')
            belly = dict(head, cursor_dist=60.0, cursor_zone='belly')
            outs = []
            for i in range(30 * 8):
                if i % 8 == 0:
                    e.event('pet', zone='head', speed=300.0)
                outs.append(e.update(1 / 30, {**P, **head}))
            self.assertEqual(outs[-1]['behaviour'], 'enjoy_petting')
            outs = []
            for i in range(30 * 4):
                if i % 8 == 0:
                    e.event('pet', zone='belly', speed=300.0)
                outs.append(e.update(1 / 30, {**P, **belly}))
            left = next(i for i, o in enumerate(outs) if o['behaviour'] != 'enjoy_petting') / 30
            self.assertLess(left, 2.0)
            self.assertNotIn('enjoy_petting', {o['behaviour'] for o in outs[int(2.5 * 30):]})

    def _debt_bird(self, td, debt, hour=15.0, S=0.4, seed=9):
        e = self.pet.create_engine(td, seed=seed, hour=hour)
        st = e.get_state()
        st.update(sleep_debt=debt, S=S)
        e.set_state(st, now=st['saved_at'], hour=hour)
        return e

    def test_kept_awake_at_night_builds_sleep_debt(self):
        night = dict(P, hour=23.5, idle_s=2.0)
        with tempfile.TemporaryDirectory() as td:
            res = {}
            for mode in ('left_alone', 'kept_awake'):
                e = self._debt_bird(td, 0.0, hour=23.5, S=0.75)
                for k in range(int(3600 / 0.5)):                   # one hour after bedtime, lamp on, user at the PC
                    t = k * 0.5
                    kw = dict(night, cursor_dist=600.0)
                    if mode == 'kept_awake' and t % 20 < 3:          # scratch it awake every 20 s
                        kw = dict(night, cursor_dist=10.0, cursor_speed=300.0, cursor_jitter=3.0,
                                  cursor_over=True, cursor_zone='head')
                        e.event('pet', zone='head', speed=300.0)
                    out = e.update(0.5, kw)
                res[mode] = out['drives']['sleep_debt']
            self.assertLess(res['left_alone'], 0.2)               # it went to sleep on its own, lamp or not
            self.assertGreater(res['kept_awake'], 0.4)

    def test_sleep_deprived_bird_is_grumpy_and_food_does_not_fix_it(self):
        with tempfile.TemporaryDirectory() as td:
            near = dict(P, cursor_dist=150.0, idle_s=1.0)
            peak = {}
            for debt in (0.0, 0.85):
                e = self._debt_bird(td, debt)
                a = self.run_for(e, 60, **near)
                e.event('feed_millet')
                b = self.run_for(e, 40, **near)
                f = lambda outs, k: sum(o['emotions'][k] for o in outs) / len(outs)
                peak[debt] = dict(frus=f(a[-600:], 'frustrated'), happy=f(a[-600:], 'happy'),
                                  frus_fed=f(b[-450:], 'frustrated'), debt_after=b[-1]['drives']['sleep_debt'],
                                  angry_fed=f(b[-450:], 'angry'))
            rested, tired = peak[0.0], peak[0.85]
            self.assertGreater(tired['frus'] - rested['frus'], 0.15)
            self.assertLess(tired['happy'], rested['happy'])
            self.assertGreater(tired['frus_fed'] - rested['frus_fed'], 0.1)     # a treat does not fix it
            self.assertGreater(tired['debt_after'], 0.75)                        # only sleep repays the debt
            self.assertLess(rested['angry_fed'], 0.05)

    def test_sleep_repays_the_debt(self):
        with tempfile.TemporaryDirectory() as td:
            e = self._debt_bird(td, 0.8, hour=23.5, S=0.75)
            for _ in range(int(2 * 3600 / 1.0)):                      # two hours, user away, lights natural
                out = e.update(1.0, dict(P, hour=23.5, idle_s=3600.0, cursor_dist=900.0))
            self.assertLess(out['drives']['sleep_debt'], 0.3)

    def test_fly_takes_off_hovers_and_lands(self):
        bank = SoundBank(self.pet)
        with tempfile.TemporaryDirectory() as td:
            e = self.engine(td, seed=5)
            self.run_for(e, 3)
            e.event('fly')
            outs = self.run_for(e, 6.0)
            fly = [o for o in outs if o['behaviour'] == 'fly']
            self.assertEqual(fly[0]['clip'], 'flap_takeoff')
            self.assertEqual(fly[0]['hold'], dict(start=1.0, end=2.0, repeats=2, lift=1.9))
            self.assertAlmostEqual(len(fly) / 30, 5.0, delta=0.15)              # 3 s clip + 2 x 1 s hover
            ts = [o['clip_time'] for o in fly]
            self.assertEqual(sum(1 for a, b in zip(ts, ts[1:]) if b < a), 2)   # looped back twice
            self.assertLess(max(ts), 3.0)
            self.assertNotEqual(outs[-1]['behaviour'], 'fly')                  # landed, back to normal life
            flaps, now = [], 50.0
            for o in fly:
                now += 1 / 30
                flaps += [now for c in bank.from_output(o, now=now) if c['category'] == 'wing_flap']
            self.assertGreaterEqual(len(flaps), 12)
            self.assertGreater(min(b - a for a, b in zip(flaps, flaps[1:])), 0.2)   # no burst at the loop seam

    def test_mood_panel_window(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from app.panel import MoodPanel
        app = QApplication.instance() or QApplication([])
        cfg = self.pet.m['panel']
        self.assertEqual([m['label'] for m in cfg['meters']], ['Hunger', 'Sleep-deprived'])
        p = MoodPanel('Sun Conure', cfg)
        with tempfile.TemporaryDirectory() as td:
            out = self._debt_bird(td, 0.5).update(0.1, P)
        p.feed(out)
        p.show()
        for _ in range(30):
            p._tick()
        v = p.snapshot_values()
        self.assertAlmostEqual(v['m1'], out['drives']['sleep_debt'], delta=0.02)
        self.assertAlmostEqual(v['m0'], min(1.0, out['drives']['hunger'] / 0.6), delta=0.02)
        img = p.grab()
        self.assertEqual((img.width(), img.height()), (p.width(), p.height()))
        p.close()
        app.processEvents()


def glb_jaw_angles(path, bone='jaw'):
    """(clip, t0, t1) -> max jaw rotation from rest (deg) within [t0, t1], read straight from the GLB."""
    import math
    import struct
    with open(path, 'rb') as fh:
        data = fh.read()
    jl = struct.unpack('<I', data[12:16])[0]
    g = json.loads(data[20:20 + jl])
    off0 = 20 + jl + 8
    node = next(i for i, n in enumerate(g['nodes']) if n.get('name') == bone)
    rest = g['nodes'][node].get('rotation', [0, 0, 0, 1])

    def acc(i, n):
        a = g['accessors'][i]
        bv = g['bufferViews'][a['bufferView']]
        o = off0 + bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        vals = struct.unpack_from(f'<{a["count"] * n}f', data, o)
        return [vals[k * n:(k + 1) * n] for k in range(a['count'])]

    def f(clip, t0, t1):
        an = next(a for a in g['animations'] if a['name'] == clip)
        for ch in an['channels']:
            if ch['target'].get('node') == node and ch['target']['path'] == 'rotation':
                smp = an['samplers'][ch['sampler']]
                ts = [t[0] for t in acc(smp['input'], 1)]
                qs = acc(smp['output'], 4)
                best = 0.0
                for t, q in zip(ts, qs):
                    if t0 - 1e-3 <= t <= t1:
                        d = abs(sum(a * b for a, b in zip(q, rest))) / math.sqrt(sum(a * a for a in q) * sum(b * b for b in rest))
                        best = max(best, math.degrees(2 * math.acos(min(1.0, d))))
                return best
        return 0.0
    return f


if __name__ == '__main__':
    unittest.main()
