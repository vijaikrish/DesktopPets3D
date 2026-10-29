// Procedural layer on top of the baked clips: cursor gaze (eyes -> head/neck -> body yaw), blinks, lid droop,
// pupil pinning, jaw lip-sync, plus bone-attached points (touch zones, effect anchors). Species-neutral: bone names,
// limits and points come from pet.json "rig". Everything is applied AFTER the mixer each frame and the touched bones
// are reset to rest BEFORE the mixer, so nothing accumulates.
import * as THREE from 'three';

const DEG = Math.PI / 180;
const UP = new THREE.Vector3(0, 1, 0);
const _q1 = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _q3 = new THREE.Quaternion(), _qi = new THREE.Quaternion();
const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3();

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const yawOf = (v) => Math.atan2(v.x, v.z);
const pitchOf = (v) => Math.asin(clamp(v.y / Math.max(1e-9, v.length()), -1, 1));
// smooth saturation: linear in the middle, never hits the stop with a visible kink
const soft = (x, lim) => lim * Math.tanh(x / lim);

// exact critically damped spring (stable for any dt)
class Spring {
  constructor(w, x = 0) { this.w = w; this.x = x; this.v = 0; }
  step(target, dt) {
    const w = this.w, e = this.x - target, ex = Math.exp(-w * dt), b = this.v + w * e;
    this.x = target + (e + b * dt) * ex;
    this.v = (this.v - w * b * dt) * ex;
    return this.x;
  }
}

function rotateBoneWorld(bone, qWorld) {        // L' = P^-1 Q P L  (rotate about the bone's own pivot, world axes)
  bone.parent.getWorldQuaternion(_q1);
  _q2.copy(_q1).invert();
  bone.quaternion.premultiply(_q1).premultiply(qWorld).premultiply(_q2);
  bone.updateMatrixWorld(true);
}

export function findNode(root, name) {
  if (!name) return null;
  const s = THREE.PropertyBinding.sanitizeNodeName(name);
  let hit = null;
  root.traverse((o) => { if (!hit && (o.userData?.name === name || o.name === s)) hit = o; });
  return hit;
}

// the local quaternion of `bone` in `clip` at the time it deviates most from rest (e.g. lids in 'blink')
function peakPose(clip, bone, rest) {
  if (!clip || !bone) return null;
  const tn = THREE.PropertyBinding.sanitizeNodeName(bone.name) + '.quaternion';
  const tr = clip.tracks.find((t) => t.name === tn || t.name.endsWith('/' + tn));
  if (!tr) return null;
  let best = null, bestA = 0, bestT = 0;
  const q = new THREE.Quaternion();
  for (let i = 0; i < tr.times.length; i++) {
    q.fromArray(tr.values, i * 4);
    const a = q.angleTo(rest);
    if (a > bestA) { bestA = a; best = q.clone(); bestT = tr.times[i]; }
  }
  return best ? { q: best, angle: bestA, t: bestT, track: tr } : null;
}

function poseAt(track, t) {
  const r = track.createInterpolant(new Float32Array(4)).evaluate(t);
  return new THREE.Quaternion(r[0], r[1], r[2], r[3]).normalize();
}

export class Rig {
  constructor(root, pivot, rigCfg, clipsByName) {
    this.root = root; this.pivot = pivot;
    const g = this.g = rigCfg.gaze || {};
    const f = rigCfg.face || {};
    this.neck = findNode(root, g.neck_bone);
    this.head = findNode(root, g.head_bone);
    this.eyes = (g.eye_bones || []).map((n) => findNode(root, n)).filter(Boolean);
    this.lids = (f.lid_bones || []).map((n) => findNode(root, n)).filter(Boolean);
    this.jaw = findNode(root, f.jaw_bone);
    this.beakUp = findNode(root, f.beak_upper_bone);
    this.ctl = [this.neck, this.head, ...this.eyes, ...this.lids, this.jaw, this.beakUp].filter(Boolean);
    this.rest = new Map(this.ctl.map((b) => [b, b.quaternion.clone()]));
    root.updateMatrixWorld(true);
    // head forward in head-local space = world +Z at rest (the pet faces the camera in the bind pose)
    this.fwdLocal = new THREE.Vector3(0, 0, 1);
    if (this.head) this.fwdLocal.applyQuaternion(this.head.getWorldQuaternion(new THREE.Quaternion()).invert());
    // lids closed = their pose at the peak of the blink clip
    const blink = clipsByName[f.blink_clip];
    this.lidClosed = new Map();
    for (const b of this.lids) { const pk = peakPose(blink, b, this.rest.get(b)); if (pk) this.lidClosed.set(b, pk.q); }
    // jaw opening axis (local) per degree, and the upper beak's coupled lift, from the jaw clip's widest gape
    const jc = clipsByName[f.jaw_clip];
    const pk = this.jaw ? peakPose(jc, this.jaw, this.rest.get(this.jaw)) : null;
    this.jawAxis = null;
    if (pk && pk.angle > 2 * DEG) {
      const d = this.rest.get(this.jaw).clone().invert().multiply(pk.q);           // open = rest * d
      this.jawAxis = new THREE.Vector3(d.x, d.y, d.z).normalize();
      if (d.w < 0) this.jawAxis.negate();
      if (this.beakUp) {
        const bt = peakPose(jc, this.beakUp, this.rest.get(this.beakUp));
        if (bt) {
          const du = this.rest.get(this.beakUp).clone().invert().multiply(poseAt(bt.track, pk.t));
          const au = 2 * Math.acos(clamp(Math.abs(du.w), -1, 1));
          if (au > 0.1 * DEG) {
            this.beakAxis = new THREE.Vector3(du.x, du.y, du.z).normalize();
            if (du.w < 0) this.beakAxis.negate();
            this.beakCouple = au / pk.angle;
          }
        }
      }
    }
    this.pupils = [];
    root.traverse((o) => {
      const i = o.morphTargetDictionary?.[f.pupil_morph];
      if (o.isMesh && i !== undefined) this.pupils.push([o, i]);
    });
    // state
    this.bodyYaw = new Spring(2.4); this.bodyTarget = 0;
    this.headYaw = new Spring(6.5); this.headPitch = new Spring(6.5);
    this.eyeYaw = new Spring(24); this.eyePitch = new Spring(24);
    this.weight = new Spring(4, 0.5);
    this.blinkT = -1; this.blinkDur = [0.07, 0.04, 0.11];
    this.nextAutoBlink = 2 + Math.random() * 4;
    this.sacc = { yaw: 0, pitch: 0, until: 0 };
    this.t = 0;
    this.info = { lids: this.lidClosed.size, jaw: !!this.jawAxis, beakCouple: this.beakCouple || 0, pupils: this.pupils.length };
  }

  // The procedural layer edits bones AFTER the mixer. Before the next mixer.update() those bones must hold exactly what
  // the mixer last wrote: three.js' PropertyMixer only writes a value when it CHANGED since its previous write, so a
  // held pose (a plateau in the bake, a constant lid / jaw / pupil track) would otherwise stay at whatever we reset it
  // to. Resetting to the rest pose here made held poses snap to rest for a few frames (head popping back during
  // head_scratched, lids / pupils flickering in rest_one_leg).
  resetBeforeMixer() {
    if (!this.mixPose) {                                     // first frame: nothing written yet -> rest
      for (const [b, q] of this.rest) b.quaternion.copy(q);
      for (const [m, i] of this.pupils) m.morphTargetInfluences[i] = 0;
      return;
    }
    for (const [b, q] of this.mixPose) b.quaternion.copy(q);
    this.pupils.forEach(([m, i], k) => { m.morphTargetInfluences[i] = this.mixPupil[k]; });
  }

  // call right after mixer.update(): remember the mixer's own pose (before gaze / blink / jaw / pupil edits)
  captureAfterMixer() {
    if (!this.mixPose) this.mixPose = new Map(this.ctl.map((b) => [b, b.quaternion.clone()]));
    for (const [b, q] of this.mixPose) q.copy(b.quaternion);
    this.mixPupil = this.pupils.map(([m, i]) => m.morphTargetInfluences[i]);
  }

  blink(kind = 'fast') {
    if (this.blinkT >= 0) return;
    this.blinkT = 0;
    this.blinkDur = kind === 'slow' ? [0.15, 0.12, 0.25] : [0.07, 0.04, 0.11];
  }

  _blinkAmount(dt) {
    if (this.blinkT < 0) return 0;
    this.blinkT += dt;
    const [a, h, r] = this.blinkDur, t = this.blinkT;
    if (t < a) return t / a;
    if (t < a + h) return 1;
    if (t < a + h + r) return 1 - (t - a - h) / r;
    this.blinkT = -1;
    return 0;
  }

  // s: {cursor:{x,y}|null, headPx:{x,y}, petPx, camera, look 0..1, follow{mode}, clip, asleep, face, jawDeg, active 0..1}
  apply(dt, s) {
    this.t += dt;
    const g = this.g, head = this.head;
    if (!head) return;
    const clipW = s.asleep ? 0 : (g.clip_weights?.[s.clip] ?? 1.0);
    const want = clipW * clamp(0.25 + 0.6 * s.active + 0.35 * (s.look || 0), 0, 1);
    const w = clamp(this.weight.step(s.cursor ? want : 0, dt), 0, 1);
    // --- where is the cursor, as angles from the head (screen offset over a virtual viewing depth)
    head.getWorldPosition(_v1);
    _v2.copy(s.camera.position).sub(_v1);                     // towards the user
    const baseYaw = yawOf(_v2), basePitch = pitchOf(_v2);
    let yawC = baseYaw, pitchC = basePitch;
    if (s.cursor && s.headPx) {
      const D = (g.depth || 2.4) * s.petPx;
      yawC += Math.atan2(s.cursor.x - s.headPx.x, D);
      pitchC += Math.atan2(-(s.cursor.y - s.headPx.y), D);
    }
    // --- body: deliberate turns within +-body_yaw_max (hysteresis, so it re-plants rather than creeps)
    const bmax = (g.body_yaw_max ?? 30) * DEG, mode = s.follow?.mode || 'idle';
    let bt = this.bodyTarget;
    if (mode === 'none' || !s.cursor) bt = s.asleep ? bt : bt * 0.995;
    else if (mode === 'turn_away') bt = -Math.sign(yawC || 1) * bmax;
    else if (mode === 'avoid') bt = clamp(-0.4 * yawC, -bmax, bmax);
    else {
      const ideal = clamp(0.65 * yawC, -bmax, bmax) * (0.4 + 0.6 * w);
      if (Math.abs(ideal - bt) > 9 * DEG || Math.abs(ideal) < 3 * DEG) bt = ideal;
    }
    if (Math.abs(bt - this.bodyTarget) > 12 * DEG) this.blink('fast');   // birds blink with big head/body turns
    this.bodyTarget = bt;
    const by = this.bodyYaw.step(bt, dt);
    this.pivot.rotation.y = by;
    this.pivot.updateMatrixWorld(true);
    // --- head + neck: point the animated head towards the cursor with weight w (gaze stabilisation)
    const yawT = this.headYaw.step(yawC, dt), pitchT = this.headPitch.step(pitchC, dt);
    const ymax = (g.head_yaw_max ?? 60) * DEG;
    const yawD = by + soft(wrap(yawT - by), ymax);
    const pitchD = pitchT >= 0 ? soft(pitchT, (g.head_pitch_up ?? 28) * DEG) : soft(pitchT, (g.head_pitch_down ?? 22) * DEG);
    head.getWorldQuaternion(_q3);
    const fa = this.fwdLocal.clone().applyQuaternion(_q3);
    const ya = yawOf(fa), pa = pitchOf(fa);
    const Q = new THREE.Quaternion().setFromAxisAngle(UP, wrap(yawD - ya))
      .multiply(_q1.setFromAxisAngle(_v2.set(Math.cos(ya), 0, -Math.sin(ya)), -(pitchD - pa)));
    const Qw = _qi.identity().clone().slerp(Q, w);
    if (this.neck) {
      const Qn = new THREE.Quaternion().slerp(Qw, g.neck_share ?? 0.4);
      rotateBoneWorld(this.neck, Qn);
      rotateBoneWorld(head, Qw.clone().multiply(Qn.invert()));
    } else rotateBoneWorld(head, Qw);
    // --- eyes: fast, lead the head, take the residual error (+ small saccades)
    head.getWorldQuaternion(_q3);
    const fh = this.fwdLocal.clone().applyQuaternion(_q3);
    const yh = yawOf(fh), ph = pitchOf(fh);
    if (s.saccade || this.t > this.sacc.until) {
      const big = s.saccade ? 1 : 0.35;
      this.sacc = { yaw: (Math.random() - 0.5) * 7 * DEG * big, pitch: (Math.random() - 0.5) * 4 * DEG * big,
        until: this.t + 0.4 + Math.random() * 1.6 };
    }
    const ew = s.asleep ? 0 : Math.max(w, 0.55 * clipW);
    const eyT = this.eyeYaw.step(clamp(wrap(yawC - yh) * ew + this.sacc.yaw, -1, 1), dt);
    const epT = this.eyePitch.step(clamp((pitchC - ph) * ew + this.sacc.pitch, -1, 1), dt);
    const ey = soft(eyT, (g.eye_yaw_max ?? 14) * DEG), ep = soft(epT, (g.eye_pitch_max ?? 9) * DEG);
    if (this.eyes.length) {
      const Qe = new THREE.Quaternion().setFromAxisAngle(UP, ey)
        .multiply(_q1.setFromAxisAngle(_v2.set(Math.cos(yh), 0, -Math.sin(yh)), -ep));
      for (const e of this.eyes) rotateBoneWorld(e, Qe);
    }
    // --- lids: blink (engine Poisson blinks + own idle blinks) and droop (content / sleepy / being scratched)
    if (s.blink) this.blink(s.blink);
    this.nextAutoBlink -= dt;
    if (this.nextAutoBlink <= 0) { this.blink('fast'); this.nextAutoBlink = 3 + Math.random() * 5; }
    const b = Math.max(this._blinkAmount(dt), 0.5 * clamp(s.face?.lid_droop || 0, 0, 1));
    if (b > 0.001) for (const [lid, qc] of this.lidClosed) lid.quaternion.slerp(qc, b);
    // --- pupils pin (excitement / anger), never below what the clip itself does
    const pin = clamp(s.face?.pupil_small || 0, 0, 1) * 0.85;
    for (const [m, i] of this.pupils) m.morphTargetInfluences[i] = Math.max(m.morphTargetInfluences[i], pin);
    // debug trace (tools: app.trace): lid angle from rest, eye angles, pupil, blink amount, gaze weight
    const lid0 = this.lids[0];
    this.dbg = { lid: lid0 ? 2 * Math.acos(Math.min(1, Math.abs(lid0.quaternion.dot(this.rest.get(lid0))))) / DEG : 0,
      ey: ey / DEG, ep: ep / DEG, pin: this.pupils.length ? this.pupils[0][0].morphTargetInfluences[this.pupils[0][1]] : 0,
      b, w, body: by / DEG };
    // --- jaw follows the voice envelope
    if (this.jawAxis && s.jawDeg > 0.05) {
      this.jaw.quaternion.multiply(_q1.setFromAxisAngle(this.jawAxis, s.jawDeg * DEG));
      if (this.beakAxis) this.beakUp.quaternion.multiply(_q1.setFromAxisAngle(this.beakAxis, s.jawDeg * this.beakCouple * DEG));
    }
  }
}

// Bone-attached points defined in rest-pose model space (pet.json zones / anchors) -> live world positions.
export class Points {
  constructor(root, defs) {
    root.updateMatrixWorld(true);
    this.items = [];
    for (const [key, d] of defs) {
      const bone = findNode(root, d.bone) || root;
      const world = new THREE.Vector3().fromArray(d.at).applyMatrix4(root.matrixWorld);
      const local = world.clone().applyMatrix4(bone.matrixWorld.clone().invert());
      const r = d.r ?? 0;
      this.items.push({ key, zone: d.zone, bone, local, r, w: new THREE.Vector3() });
    }
  }
  update() { for (const it of this.items) it.w.copy(it.local).applyMatrix4(it.bone.matrixWorld); }
}
