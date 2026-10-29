// Touch input -> species-neutral events for the core (Python), which forwards them to the pet's engine.
//   hover over the pet + gentle cursor motion (no button) = stroke  {zone, speed px/s}   ~4 per second
//   click (press+release, no motion)                       = tap    {zone}
//   3 clicks within 1.2 s                                  = poke   {zone}
//   press + move > 6 px                                    = drag_start / drag_end (the core moves the window)
//   right button                                           = menu
// Percepts at 10 Hz: distance cursor->head (px), approach speed towards the head (px/s), path speed (px/s),
// jitter (direction reversals per second), over-pet flag, zone. Only LEFT clicks are touch events; the right button
// only opens the menu.
// The cursor position comes from the core every frame (global mouse, also when it is outside this window).

export class Touch {
  constructor(el, post) {
    this.post = post;
    this.cursor = null;
    this.hist = [];
    this.over = false; this.overSince = -1; this.zone = null;
    this.nextStroke = 0; this.nextPercept = 0;
    this.press = null; this.dragging = false; this.clicks = [];
    this.dist = null; this.approach = 0; this._d = null; this._dt = 0;
    this.speed = 0; this.jitter = 0;
    el.addEventListener('pointerdown', (e) => this._down(e));
    el.addEventListener('pointermove', (e) => this._move(e));
    el.addEventListener('pointerup', (e) => this._up(e));
    el.addEventListener('pointercancel', () => this._cancel());
    el.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  _now() { return performance.now() / 1000; }

  _down(e) {
    if (e.button === 2 || (e.button === 0 && e.ctrlKey)) { this.post('menu', {}); return; }   // Ctrl+click = right click on macOS
    if (e.button !== 0) return;
    this.press = { x: e.clientX, y: e.clientY, t: this._now(), zone: this.zone };
    this.dragging = false;
    try { e.target.setPointerCapture(e.pointerId); } catch (_) { /* synthetic or already released pointer */ }
    this.post('press', {});
  }

  _move(e) {
    if (this.press && !this.dragging && Math.hypot(e.clientX - this.press.x, e.clientY - this.press.y) > 6) {
      this.dragging = true;
      this.post('drag_start', {});
    }
  }

  _up(e) {
    if (e.button !== 0 || !this.press) return;
    const p = this.press;
    this.press = null;
    if (this.dragging) { this.dragging = false; this.post('drag_end', {}); return; }
    if (this._now() - p.t > 0.6) return;                       // a long press without moving: nothing
    const t = this._now(), zone = p.zone || this.zone || 'body';
    this.clicks = this.clicks.filter((c) => t - c < 1.2);
    this.clicks.push(t);
    if (this.clicks.length >= 3) { this.clicks = []; this.post('poke', { zone }); }
    else this.post('tap', { zone });
  }

  _cancel() {
    if (this.dragging) this.post('drag_end', {});
    this.press = null; this.dragging = false;
  }

  // external: the core ended a drag (mouse released outside, menu opened...)
  reset() { this.press = null; this.dragging = false; }

  setCursor(c, petPx = 130) {
    this.cursor = c;
    if (!c) { this.hist = []; return; }
    const t = this._now(), h = this.hist, last = h[h.length - 1];
    // a jump of > 0.4 pet heights between two samples is a discontinuity (flick / teleport), not part of a stroke
    if (last && Math.hypot(c.x - last[1], c.y - last[2]) > 0.4 * petPx) this.hist = [];
    this.hist.push([t, c.x, c.y]);
    while (this.hist.length && t - this.hist[0][0] > 0.7) this.hist.shift();
  }

  // path speed (px/s) over the last 0.25 s and direction reversals per second over the last 0.6 s. Reversals are
  // counted on ~40 ms steps longer than 2 % of the pet height, so hand tremor does not count.
  _kinematics(petPx) {
    const t = this._now(), h = this.hist;
    if (h.length < 2) return [0, 0];
    let L = 0, T0 = null;
    for (let i = h.length - 1; i > 0 && t - h[i - 1][0] <= 0.25; i--) {
      L += Math.hypot(h[i][1] - h[i - 1][1], h[i][2] - h[i - 1][2]); T0 = h[i - 1][0];
    }
    const v = T0 === null ? 0 : L / Math.max(0.05, t - T0);
    const pts = []; let lastT = -1;
    for (const p of h) if (t - p[0] <= 0.6 && p[0] - lastT >= 0.04) { pts.push(p); lastT = p[0]; }
    let rev = 0, pv = null;
    const minStep = 0.02 * petPx;
    for (let i = 1; i < pts.length; i++) {
      const dx = pts[i][1] - pts[i - 1][1], dy = pts[i][2] - pts[i - 1][2], n = Math.hypot(dx, dy);
      if (n < minStep) continue;
      if (pv && (dx * pv[0] + dy * pv[1]) / (n * pv[2]) < -0.5) rev++;     // turned by more than 120 deg
      pv = [dx, dy, n];
    }
    const span = pts.length > 1 ? Math.max(0.2, pts[pts.length - 1][0] - pts[0][0]) : 0.6;
    return [v, rev / span];
  }

  // a stroke = local rubbing over the pet: path speed over the last 0.3 s. A fast one-way pass (net displacement close to
  // the path length) is the hand passing by, not a stroke -> null. Back-and-forth rubbing at any speed IS a stroke.
  _stroke(petPx, span = 0.3) {
    const t = this._now(), h = this.hist.filter((p) => t - p[0] <= span);
    if (h.length < 3) return null;
    let L = 0;
    for (let i = 1; i < h.length; i++) L += Math.hypot(h[i][1] - h[i - 1][1], h[i][2] - h[i - 1][2]);
    const T = Math.max(0.05, h[h.length - 1][0] - h[0][0]), v = L / T;
    const N = Math.hypot(h[h.length - 1][1] - h[0][1], h[h.length - 1][2] - h[0][2]);
    if (v > 5 * petPx && N > 0.6 * L) return null;
    return v;
  }

  // per rendered frame: over = silhouette hit under the cursor, zoneAt(x,y) -> zone, headPx = head on screen
  update(dt, over, zoneAt, headPx, petPx) {
    const t = this._now(), c = this.cursor;
    if (over !== this.over) {
      this.over = over;
      this.overSince = over ? t : -1;
      this.post('hover', { over });
    }
    this.zone = over && c ? zoneAt(c.x, c.y) : null;
    // distance / approach (px, px/s) -> engine percepts
    if (c && headPx) {
      const d = Math.hypot(c.x - headPx.x, c.y - headPx.y);
      if (this._d !== null && dt > 0) {
        const a = Math.max(0, (this._d - d) / dt);
        this.approach += (a - this.approach) * (1 - Math.exp(-dt / 0.08));
      }
      this._d = d; this.dist = d;
    } else { this._d = null; this.dist = null; this.approach *= 0.8; }
    if (c) {
      const [v, j] = this._kinematics(petPx);
      const k = 1 - Math.exp(-dt / 0.12);
      this.speed += (v - this.speed) * k; this.jitter += (j - this.jitter) * k;
    } else { this.speed *= 0.8; this.jitter *= 0.8; }
    if (t >= this.nextPercept) {
      this.nextPercept = t + 0.1;
      this.post('percept', { dist: this.dist, approach: Math.round(this.approach), speed: Math.round(this.speed),
        jitter: Math.round(this.jitter * 10) / 10, over: this.over, zone: this.zone, pet_px: Math.round(petPx) });
    }
    // strokes: over the pet for > 0.35 s, no button, moving
    if (this.over && !this.press && this.overSince > 0 && t - this.overSince > 0.35 && t >= this.nextStroke) {
      const sp = this._stroke(petPx);
      if (sp !== null && sp > 25) {
        this.nextStroke = t + 0.25;
        this.post('stroke', { zone: this.zone || 'body', speed: Math.round(sp) });
      }
    }
  }
}
