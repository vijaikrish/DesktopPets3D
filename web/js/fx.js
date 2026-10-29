// 2D effects drawn on a transparent canvas over the 3D pet (CSS pixels). Painters ported from DesktopPets v5
// (heart, spark, smoke, ha, note, zzz, dust, tear, splash, rain, petal, leaf, feather, anger) plus sparkle, leaf_dry,
// exclaim, question, sweat, call rings and puff. Positions come from bone-attached anchors projected every frame
// (head_top, head, beak, eye_l, eye_r, body, feet) plus 'sky' (top edge) and 'cloud'. Sizes and speeds scale with the
// pet's on-screen size. WHICH effect appears WHEN is decided in Python (app/fx_director.py) from pet.json "fx" rules.

const TAU = Math.PI * 2;
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

const HEART = new Path2D('M0 -4 C-6 -12 -16 -6 -8 2 L0 10 L8 2 C16 -6 6 -12 0 -4 Z');
const SPARK = new Path2D('M0 -10 L2.5 -2.5 L10 0 L2.5 2.5 L0 10 L-2.5 2.5 L-10 0 L-2.5 -2.5 Z');
const DROP = new Path2D('M0 -12 Q-9 2 -7 8 Q-4 14 0 14 Q4 14 7 8 Q9 2 0 -12 Z');
const LEAF = new Path2D('M0 0 Q14 -12 34 0 Q14 12 0 0 Z');
const LEAF_VEIN = new Path2D('M2 0 L30 0');
const FEATHER = new Path2D('M0 -18 Q10 -4 0 18 Q-10 -4 0 -18 Z');
const ANGER = new Path2D('M-12 -4 Q-4 -6 -2 -14 M12 -4 Q4 -6 2 -14 M-12 4 Q-4 6 -2 14 M12 4 Q4 6 2 14');

export const DEFAULT_ANCHOR = {
  heart: 'head_top', spark: 'body', sparkle: 'body', smoke: 'head', ha: 'head', note: 'beak', zzz: 'head_top',
  dust: 'feet', puff: 'beak', tear: 'eye', sweat: 'head', rain: 'cloud', petal: 'sky', leaf: 'sky', leaf_dry: 'sky',
  feather: 'body', anger: 'head_top', exclaim: 'head_top', question: 'head_top', call: 'beak',
};

// recipes: p = anchor point {x, y}, k = size factor (pet px / reference px), i = index within a burst
const POSITIVE = new Set(['heart', 'sparkle']);
const NEGATIVE = new Set(['anger', 'smoke', 'sweat']);

const R = {
  heart:    (p, k) => ({ x: p.x + rnd(-28, 28) * k, y: p.y, vy: rnd(-58, -42) * k, life: 2.0, s: rnd(0.8, 1.15) }),
  spark:    (p, k) => ({ x: p.x + rnd(-70, 70) * k, y: p.y + rnd(-60, 30) * k, life: 0.8, s: rnd(0.6, 1.1), vr: 120, color: pick(['#FFC93C', '#FFE680']) }),
  sparkle:  (p, k) => ({ x: p.x + rnd(-75, 75) * k, y: p.y + rnd(-85, 35) * k, life: rnd(0.7, 1.1), s: rnd(0.35, 0.7), vr: 60, color: pick(['#FFFFFF', '#FFF3B0', '#FFD84D']) }),
  smoke:    (p, k, i) => { const sd = (i % 2 ? 1 : -1) * pick([1, 1, -1]); return { x: p.x + sd * rnd(26, 40) * k, y: p.y - 6 * k, vx: sd * rnd(10, 30) * k, vy: -rnd(70, 100) * k, life: 1.1, s: rnd(0.45, 0.6) }; },
  ha:       (p, k) => { const sd = pick([-1, 1]); return { x: p.x + sd * rnd(50, 70) * k, y: p.y - rnd(0, 30) * k, vy: -26 * k, life: 0.9, s: rnd(0.4, 0.55), r: sd * rnd(5, 18) }; },
  note:     (p, k) => { const sd = pick([-1, 1]); return { x: p.x + sd * rnd(34, 44) * k, y: p.y + 6 * k, vx: sd * rnd(40, 58) * k, vy: rnd(-44, -32) * k, life: 1.8, s: rnd(0.5, 0.7), r: sd * rnd(5, 20), color: pick(['#7B3FA0', '#3F6FD8', '#D8406F', '#2E9E6A']) }; },
  zzz:      (p, k) => ({ x: p.x + 18 * k, y: p.y - 6 * k, vx: 14 * k, vy: -26 * k, life: 2.4, s: 0.5 }),
  dust:     (p, k) => ({ x: p.x + rnd(-40, 40) * k, y: p.y + rnd(-6, 4) * k, vx: rnd(-35, 35) * k, vy: rnd(-12, 2) * k, life: 0.9, s: rnd(0.35, 0.6) }),
  puff:     (p, k) => ({ kind: 'dust', x: p.x + rnd(-10, 10) * k, y: p.y + rnd(-4, 4) * k, vx: rnd(-50, 50) * k, vy: rnd(-25, 5) * k, life: 0.6, s: rnd(0.3, 0.45) }),
  tear:     (p, k) => ({ x: p.x + rnd(-2, 2) * k, y: p.y + 4 * k, vy: 18 * k, g: 700 * k, life: 2.2, s: 0.42 }),
  sweat:    (p, k) => ({ x: p.x + pick([-1, 1]) * rnd(26, 36) * k, y: p.y + rnd(-6, 6) * k, vy: 24 * k, g: 90 * k, life: 1.0, s: 0.4 }),
  rain:     (p, k) => ({ x: p.x + rnd(-30, 34) * k, y: p.y + 10 * k, vy: 420 * k, life: 1.4, s: k }),
  petal:    (p, k, i, w) => ({ x: rnd(0.08, 0.92) * w, y: -8, vy: rnd(52, 70) * k, sway: 30 * k, life: 7, s: rnd(0.5, 0.75), r: rnd(0, 360), vr: rnd(-160, 160) }),
  leaf:     (p, k, i, w) => ({ x: rnd(0.08, 0.92) * w, y: -8, vy: rnd(48, 64) * k, sway: 34 * k, life: 8, s: rnd(0.45, 0.7), r: rnd(0, 360), vr: rnd(-90, 90), color: pick(['#5DB04A', '#7CC35A', '#4A9A3C']) }),
  leaf_dry: (p, k, i, w) => ({ kind: 'leaf', x: rnd(0.08, 0.92) * w, y: -8, vy: rnd(50, 66) * k, sway: 38 * k, life: 8, s: rnd(0.45, 0.7), r: rnd(0, 360), vr: rnd(-120, 120), color: pick(['#C98A3A', '#B5652B', '#D9A95B']) }),
  feather:  (p, k) => ({ x: p.x + rnd(-45, 45) * k, y: p.y + rnd(-15, 15) * k, vy: rnd(22, 38) * k, sway: 30 * k, life: 3.0, s: rnd(0.4, 0.6), r: rnd(0, 360), vr: rnd(-120, 120) }),
  anger:    (p, k) => ({ x: p.x + rnd(-28, 28) * k, y: p.y - rnd(0, 18) * k, life: 0.9, s: rnd(0.6, 0.8) }),
  exclaim:  (p, k) => ({ x: p.x + rnd(-6, 6) * k, y: p.y - 6 * k, vy: -18 * k, life: 1.0, s: 0.7 }),
  question: (p, k) => ({ x: p.x + rnd(-6, 20) * k, y: p.y - 6 * k, vy: -16 * k, life: 1.5, s: 0.65, r: rnd(-10, 10) }),
  call:     (p, k) => ({ x: p.x, y: p.y, life: 0.7, s: 1.0, dir: p.dir || 1 }),
};

export const FX_KINDS = Object.keys(R);

export class FxLayer {
  constructor(canvas) {
    this.cv = canvas;
    this.cx = canvas.getContext('2d');
    this.p = [];
    this.max = 160;
    this.cloud = null;
    this.cloudLevel = 0;
    this.t = 0;
    this.k = 1;
    this.anchors = {};
    this.floor = 0;
    this.w = 1; this.h = 1; this.dpr = 1;
  }

  resize(w, h, dpr) {
    this.w = w; this.h = h; this.dpr = Math.min(dpr || 1, 2);
    this.cv.width = Math.round(w * this.dpr); this.cv.height = Math.round(h * this.dpr);
    this.cv.style.width = w + 'px'; this.cv.style.height = h + 'px';
  }

  // anchors: {name: {x, y}} in CSS px; k = size factor; floor = feet line (px)
  setAnchors(anchors, k, floor) { this.anchors = anchors; this.k = k; this.floor = floor; }

  _anchor(name, kind) {
    const a = this.anchors;
    name = name || DEFAULT_ANCHOR[kind] || 'head';
    if (name === 'eye') return pick([a.eye_l, a.eye_r].filter(Boolean)) || a.head;
    if (name === 'cloud') return this.cloud || a.head_top;
    if (name === 'sky') return { x: this.w / 2, y: -8 };
    return a[name] || a.head || { x: this.w / 2, y: this.h / 2 };
  }

  spawn(kind, anchor = null, count = 1, size = 1) {
    const rec = R[kind];
    if (!rec) return false;
    const p = this._anchor(anchor, kind);
    if (!p) return false;
    if (NEGATIVE.has(kind)) {                         // mood flipped: hearts/sparkles still in the air fade out in 0.35 s
      for (const q of this.p) if (POSITIVE.has(q.kind) && q.killAt === undefined) q.killAt = q.age;
    }
    for (let i = 0; i < count && this.p.length < this.max; i++) {
      const q = Object.assign({ kind, vx: 0, vy: 0, r: 0, vr: 0, g: 0, sway: 0, age: 0, seed: Math.random() * TAU },
        rec(p, this.k, i, this.w));
      q.s *= size * this.k;
      q.floor = this.floor + rnd(-3, 4) * this.k;
      this.p.push(q);
    }
    return true;
  }

  setLevel(name, v) { if (name === 'rain_cloud') this.cloudLevel = v; }

  clear() { this.p = []; this.cloud = null; }

  update(dt) {
    this.t += dt;
    const k = this.k, head = this.anchors.head_top;
    const want = this.cloudLevel > 0.35 ? clamp((this.cloudLevel - 0.35) / 0.35, 0, 1) : 0;
    if ((want > 0.02 || this.cloud) && head) {
      const ty = Math.max(24 * k, head.y - 38 * k);
      if (!this.cloud) this.cloud = { x: head.x, y: ty, a: 0 };
      const c = this.cloud, f = 1 - Math.exp(-2.5 * dt);
      c.x += (head.x - c.x) * f; c.y += (ty - c.y) * f;
      c.a += (want - c.a) * (1 - Math.exp(-3 * dt));
      if (c.a < 0.02 && want < 0.02) this.cloud = null;
      else if (c.a > 0.5 && Math.random() < 14 * dt) this.spawn('rain', 'cloud');
    }
    const keep = [];
    for (const q of this.p) {
      q.age += dt;
      if (q.age >= q.life || (q.killAt !== undefined && q.age - q.killAt > 0.35)) continue;
      const kd = q.kind;
      q.vy += q.g * dt;
      if (q.sway) q.vx = q.sway * Math.sin(q.age * 2.2 + q.seed) * (q.landed ? 0 : 1);
      else if (kd === 'heart') q.vx = 20 * k * Math.sin(q.age * 4 + q.seed);
      else if (kd === 'note') { q.vx0 ??= q.vx; q.vx = q.vx0 * Math.exp(-1.2 * q.age) + 14 * k * Math.sin(q.age * 5 + q.seed); }
      else if (kd === 'smoke') q.vy *= (1 - 1.2 * dt);
      else if (kd === 'dust') q.vx *= (1 - 3 * dt);
      if (!q.landed) { q.x += q.vx * dt; q.y += q.vy * dt; q.r += q.vr * dt; }
      if (q.vy > 0 && q.y >= q.floor) {
        if (kd === 'tear' || kd === 'rain' || kd === 'sweat') {
          if (kd !== 'rain' || Math.random() < 0.35)
            this.p.push({ kind: 'splash', x: q.x, y: q.floor, vx: 0, vy: 0, g: 0, r: 0, vr: 0, sway: 0, age: 0, life: 0.35, s: (kd === 'rain' ? 0.4 : 0.6) * k });
          continue;
        }
        if (!q.landed) { q.landed = true; q.y = q.floor; q.vy = 0; q.vr = 0; q.life = Math.min(q.life, q.age + 1.6); }
      }
      if (q.y > this.h + 40 || q.x < -60 || q.x > this.w + 60) continue;
      keep.push(q);
    }
    this.p = keep;
  }

  draw() {
    const c = this.cx;
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    c.clearRect(0, 0, this.w, this.h);
    if (this.cloud) this._cloud(this.cloud.x + 4 * this.k * Math.sin(this.t * 0.9), this.cloud.y, 0.95 * this.k, this.cloud.a);
    for (const q of this.p) {
      const u = q.age / q.life;
      let fade = u < 0.6 ? 1 : Math.max(0, 1 - (u - 0.6) / 0.4);
      if (q.killAt !== undefined) fade *= Math.max(0, 1 - (q.age - q.killAt) / 0.35);
      c.save();
      c.translate(q.x, q.y);
      this['_' + q.kind](c, q, u, fade);
      c.restore();
    }
  }

  // ------------------------------------------------------------------ painters (local coords at the particle)
  _heart(c, q, u, f) { const s = q.s * 1.6 * Math.min(1, 0.4 + q.age * 3); c.globalAlpha = f; c.scale(s, s); c.fillStyle = '#FF6F91'; c.fill(HEART); c.strokeStyle = 'rgba(255,255,255,0.75)'; c.lineWidth = 1.2; c.stroke(HEART); }
  _spark(c, q, u) { const s = q.s * 1.6 * Math.sin(Math.PI * u); c.rotate(q.r * Math.PI / 180); c.scale(s, s); c.fillStyle = q.color || '#FFC93C'; c.fill(SPARK); }
  _sparkle(c, q, u) { const s = q.s * 1.8 * Math.sin(Math.PI * u); c.rotate(q.r * Math.PI / 180); c.scale(s, s); c.fillStyle = q.color; c.shadowColor = q.color; c.shadowBlur = 6; c.fill(SPARK); }
  _smoke(c, q, u) {
    const s = q.s * (1.0 + 1.8 * u); c.globalAlpha = 0.85 * (1 - u); c.scale(s, s);
    c.fillStyle = '#E9EDF1'; c.strokeStyle = '#B9C3CE'; c.lineWidth = 1.5;
    for (const [x, y, r] of [[0, 0, 14], [-13, 6, 10], [12, 7, 11]]) { c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill(); c.stroke(); }
  }
  _ha(c, q, u, f) {
    const a = Math.min(1, q.age * 6), s = q.s * (0.6 + 0.6 * a);
    c.globalAlpha = f; c.rotate(q.r * Math.PI / 180); c.scale(s, s);
    c.font = 'bold 64px Arial'; c.textAlign = 'center'; c.lineWidth = 12; c.strokeStyle = '#fff'; c.strokeText('HA', 0, 0); c.fillStyle = '#F59E0B'; c.fillText('HA', 0, 0);
  }
  _note(c, q, u, f) {
    c.globalAlpha = f; c.rotate(q.r * Math.PI / 180); c.scale(q.s * 1.6, q.s * 1.6);
    c.lineJoin = 'round'; c.strokeStyle = 'rgba(255,255,255,0.9)'; c.lineWidth = 6; c.lineCap = 'round';
    c.beginPath(); c.moveTo(8, -2); c.lineTo(8, -34); c.quadraticCurveTo(20, -28, 22, -18); c.stroke();
    c.fillStyle = q.color; c.strokeStyle = q.color; c.lineWidth = 3.5;
    c.save(); c.rotate(-20 * Math.PI / 180); c.beginPath(); c.ellipse(0, 0, 9, 6.5, 0, 0, TAU); c.fill(); c.restore();
    c.beginPath(); c.moveTo(8, -2); c.lineTo(8, -34); c.quadraticCurveTo(20, -28, 22, -18); c.stroke();
  }
  _zzz(c, q, u, f) {
    const s = q.s * (0.7 + 0.8 * u); c.globalAlpha = f; c.rotate(-12 * Math.PI / 180); c.scale(s, s);
    c.font = 'bold 60px Arial'; c.lineWidth = 6; c.strokeStyle = '#fff'; c.lineJoin = 'round'; c.strokeText('z', 0, 0); c.fillStyle = '#6C7FD8'; c.fillText('z', 0, 0);
  }
  _dust(c, q, u) {
    const s = q.s * (0.6 + 1.6 * u); c.globalAlpha = 0.6 * (1 - u); c.scale(s, s); c.fillStyle = '#D8C3A5';
    for (const [x, y, r] of [[0, 0, 14], [-12, 4, 9], [11, 5, 10]]) { c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill(); }
  }
  _drop(c, s, a) { c.globalAlpha = a; c.scale(s, s); c.fillStyle = '#8ED0F5'; c.strokeStyle = '#5BAEDB'; c.lineWidth = 1; c.fill(DROP); c.stroke(DROP); c.globalAlpha = a * 0.8; c.fillStyle = '#fff'; c.beginPath(); c.ellipse(-2.5, 6, 1.8, 3, 0, 0, TAU); c.fill(); }
  _tear(c, q) { this._drop(c, 1.4 * q.s, 0.95); }
  _sweat(c, q, u, f) { this._drop(c, 1.4 * q.s, f); }
  _rain(c, q) { c.globalAlpha = 0.8; c.strokeStyle = '#5BAEDB'; c.lineWidth = 2.5 * q.s; c.lineCap = 'round'; c.beginPath(); c.moveTo(0, 0); c.lineTo(-2.5 * q.s, 11 * q.s); c.stroke(); }
  _splash(c, q, u) { c.globalAlpha = 1 - u; c.strokeStyle = '#5BAEDB'; c.lineWidth = 2; c.beginPath(); c.ellipse(0, 0, (8 + 30 * u) * q.s, (3 + 7 * u) * q.s, 0, 0, TAU); c.stroke(); }
  _petal(c, q, u, f) { c.globalAlpha = f; c.rotate(q.r * Math.PI / 180); c.scale(q.s, q.s); c.fillStyle = '#F6A5BE'; c.beginPath(); c.ellipse(0, 0, 9, 14, 0, 0, TAU); c.fill(); c.fillStyle = 'rgba(255,255,255,0.35)'; c.beginPath(); c.ellipse(-2, -4, 3, 6, 0, 0, TAU); c.fill(); }
  _leaf(c, q, u, f) { c.globalAlpha = f; c.rotate(q.r * Math.PI / 180); c.scale(q.s, q.s * (0.75 + 0.25 * Math.cos(q.age * 3 + q.seed))); c.fillStyle = q.color || '#5DB04A'; c.fill(LEAF); c.strokeStyle = 'rgba(0,0,0,0.25)'; c.lineWidth = 1.5; c.stroke(LEAF_VEIN); }
  _feather(c, q, u, f) { c.globalAlpha = f; c.rotate(q.r * Math.PI / 180); c.scale(q.s, q.s); c.fillStyle = '#FFC61A'; c.strokeStyle = '#E8920F'; c.lineWidth = 1.5; c.fill(FEATHER); c.stroke(FEATHER); }
  _anger(c, q, u) { const pop = Math.min(1, q.age * 8); const s = q.s * (0.6 + 0.5 * pop) * (1 + 0.08 * Math.sin(q.age * 30)); c.globalAlpha = 1 - Math.max(0, u - 0.7) / 0.3; c.scale(s, s); c.strokeStyle = '#fff'; c.lineWidth = 8; c.lineCap = 'round'; c.stroke(ANGER); c.strokeStyle = '#E53935'; c.lineWidth = 4.5; c.stroke(ANGER); }
  _bubble(c, txt, color, s, a) {
    c.globalAlpha = a; c.scale(s, s); c.font = 'bold 46px Arial'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.lineWidth = 9; c.strokeStyle = '#fff'; c.lineJoin = 'round'; c.strokeText(txt, 0, 0); c.fillStyle = color; c.fillText(txt, 0, 0);
  }
  _exclaim(c, q, u, f) { const pop = Math.min(1, q.age * 7); this._bubble(c, '!', '#E53935', q.s * (0.5 + 0.6 * pop - 0.1 * Math.sin(Math.min(1, q.age * 3) * Math.PI)), f); }
  _question(c, q, u, f) { const pop = Math.min(1, q.age * 6); c.rotate(q.r * Math.PI / 180); this._bubble(c, '?', '#3F6FD8', q.s * (0.5 + 0.5 * pop), f); }
  _call(c, q, u) {
    c.globalAlpha = 0.85 * (1 - u); c.lineCap = 'round';
    for (let j = 0; j < 3; j++) {
      const r = (12 + 20 * u + 9 * j) * q.s;
      for (const [col, lw] of [['rgba(0,0,0,0.25)', 4], ['#FFFFFF', 2.5]]) {
        c.strokeStyle = col; c.lineWidth = lw;
        c.beginPath(); c.arc(0, 0, r, -2.2, -0.9); c.stroke();
      }
    }
  }
  _cloud(x, y, s, a) {
    const c = this.cx; c.save(); c.translate(x, y); c.scale(s, s); c.globalAlpha = a;
    c.fillStyle = '#9AA8B8';
    c.beginPath(); c.ellipse(0, 0, 34, 16, 0, 0, TAU); c.fill();
    c.beginPath(); c.arc(-16, -8, 16, 0, TAU); c.fill();
    c.fillStyle = '#A9B7C6'; c.beginPath(); c.arc(8, -14, 20, 0, TAU); c.fill();
    c.fillStyle = '#9AA8B8'; c.beginPath(); c.arc(24, -4, 13, 0, TAU); c.fill();
    c.strokeStyle = '#C3CEDA'; c.lineWidth = 3; c.lineCap = 'round'; c.beginPath(); c.moveTo(-10, -14); c.quadraticCurveTo(-2, -20, 6, -14); c.stroke();
    c.restore();
  }
}
