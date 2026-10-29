// Generic pet viewer. Python (app/desktop.py) owns the window, the emotion engine and the decisions; this page owns
// the pixels: GLB + clip mixer, procedural gaze/face layer, 2D effects, audio, touch input.
// Per frame: reset procedural bones -> mixer -> rig (body yaw, head/neck, eyes, lids, pupils, jaw) -> anchors -> fx
// -> render -> silhouette hit test under the cursor.
import * as THREE from 'three';
import { Stage } from './stage.js';
import { Rig, Points } from './rig.js';
import { FxLayer } from './fx.js';
import { AudioPlayer } from './audio.js';
import { Touch } from './touch.js';

const $ = (id) => document.getElementById(id);
const stage = new Stage($('three'));
const fx = new FxLayer($('fx'));
const audio = new AudioPlayer();
let bridge = null, manifest = null, rig = null, zones = null, anchors = null, mixer = null;
const clips = {}, actions = new Map();
let current = null, currentName = '', ready = false, out = {}, cursor = null, cursorMovedAt = -1e9;
let pendingBlink = null, pendingSaccade = false, snapReq = null, last = performance.now(), fpsAcc = [0, 0], fps = 60;
let trace = null;                                         // debug: per-frame rig values (app.trace)
let hold = null;                                          // v5: hover loop of the playing clip {action, start, end, left}
let lift = null, liftK = 0;                               // v5: extra root lift for flight clips
let jawSm = 0, jawForce = null;                           // smoothed lip-sync jaw (deg); debug override
const headPx = { x: 0, y: 0, init: false };

function post(name, data = {}) { if (bridge) bridge.actionData(name, data); }
const touch = new Touch($('three'), post);
window.addEventListener('error', (e) => post('error', { msg: String(e.message || e) }));
window.addEventListener('unhandledrejection', (e) => post('error', { msg: String(e.reason?.stack || e.reason) }));

function status(txt) { const s = $('status'); s.textContent = txt; s.classList.add('on'); setTimeout(() => s.classList.remove('on'), 2500); }

function resize() {
  stage.resize(innerWidth, innerHeight, devicePixelRatio);
  fx.resize(innerWidth, innerHeight, devicePixelRatio);
}
addEventListener('resize', resize);

// ------------------------------------------------------------------ clips
function action(name, alt) {
  let pair = actions.get(name);
  if (!pair) {
    if (!clips[name]) return null;
    pair = [mixer.clipAction(clips[name]), null];
    actions.set(name, pair);
  }
  if (alt && !pair[1]) pair[1] = mixer.clipAction(clips[name].clone());   // same clip, second action -> self-crossfade
  return alt ? pair[1] : pair[0];
}

function play(name, t = 0, speed = 1, loop = true, fade = 0.3) {
  if (!mixer) return;
  const same = name === currentName;
  const next = action(name, same && current === actions.get(name)?.[0]);
  if (!next) { post('error', { msg: 'missing clip ' + name }); return; }
  next.reset();
  next.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
  next.clampWhenFinished = !loop;
  next.time = Math.max(0, t || 0);
  next.timeScale = speed || 1;
  next.setEffectiveWeight(1);
  next.play();
  if (current && current !== next && fade > 0) current.crossFadeTo(next, fade, false);
  else if (current && current !== next) current.stop();
  current = next; currentName = name;
  hold = null;
}

// ------------------------------------------------------------------ init
async function init(msg) {
  manifest = msg.manifest;
  const gltf = await stage.load(`/pets/${msg.pet_id}/${msg.model}`, manifest.stage);
  resize();
  mixer = new THREE.AnimationMixer(stage.root);
  for (const c of gltf.animations) clips[c.name] = c;
  rig = new Rig(stage.root, stage.pivot, manifest.rig || {}, clips);
  zones = new Points(stage.root, (manifest.rig?.zones || []).map((z, i) => [i, z]));
  anchors = new Points(stage.root, Object.entries(manifest.rig?.anchors || {}));
  const lc = manifest.rig?.lift;
  const lb = lc ? stage.root.getObjectByName(lc.bone) : null;
  if (lb) {
    const ws = new THREE.Vector3();
    lb.parent.getWorldScale(ws);
    lift = { bone: lb, restY: lb.position.y, scale: ws.y, clips: lc.clips || {} };   // bone units -> world
  }
  play(manifest.stage?.idle_clip || gltf.animations[0]?.name, 0, 1, true, 0);
  ready = true;
  $('three').classList.add('ready');
  post('loaded', { clips: gltf.animations.length, rig: rig.info, petPx: stage.petPx });
}

// ------------------------------------------------------------------ messages from the core
function onFrame(f) {
  out = f.out || {};
  const c = f.cursor || null;
  if (c && (!cursor || Math.abs(c.x - cursor.x) + Math.abs(c.y - cursor.y) > 0.5)) cursorMovedAt = performance.now();
  cursor = c;
  touch.setCursor(c, stage.petPx || 130);
  audio.setVolume(f.volume ?? 0.8, !!f.muted);
  if (out.clip && (out.changed || out.clip !== currentName)) {
    play(out.clip, out.clip_time || 0, out.speed || 1, out.loop ?? true, out.changed ? (out.crossfade ?? 0.3) : 0.25);
    if (out.hold && current) hold = { action: current, start: out.hold.start, end: out.hold.end, left: out.hold.repeats | 0 };
  } else if (current && out.speed) current.timeScale = out.speed;
  for (const cmd of f.sounds || []) audio.play(cmd).catch(() => {});
  for (const s of f.fx || []) fx.spawn(s.kind, s.anchor, s.count || 1, s.size || 1);
  for (const [k, v] of Object.entries(f.levels || {})) fx.setLevel(k, v);
  if (out.blink) pendingBlink = out.blink;
  if (out.gaze?.saccade) pendingSaccade = true;
  if (f.drag_ended) touch.reset();
}

function consume(msg) {
  if (msg.type === 'init') { init(msg).catch((e) => { post('error', { msg: 'model load: ' + (e.stack || e) }); status('Could not load the pet'); }); return; }
  if (msg.type === 'frame') { if (ready) onFrame(msg); return; }
  if (msg.type === 'snapshot') { snapReq = msg.tag; return; }
  if (msg.type === 'fx_clear') { fx.clear(); return; }
  if (msg.type === 'debug_blink') { pendingBlink = 'slow'; return; }
  if (msg.type === 'debug_jaw') { jawForce = msg.deg == null ? null : +msg.deg; return; }
  if (msg.type === 'debug_trace') { trace = { n: msg.frames || 600, rows: [] }; return; }
  if (msg.type === 'debug_click') {                      // review harness: a synthetic click through the real handlers
    const el = $('three'), o = { button: 0, clientX: msg.x, clientY: msg.y, pointerId: 77, bubbles: true };
    el.dispatchEvent(new PointerEvent('pointerdown', o));
    setTimeout(() => el.dispatchEvent(new PointerEvent('pointerup', o)), 80);
    return;
  }
}

// ------------------------------------------------------------------ render loop
function project(name) {
  const it = anchors.items.find((a) => a.key === name);
  return it ? stage.project(it.w) : null;
}

function zoneAt(x, y) {
  if (!zones) return null;
  const cam = stage.camera, inv = cam.matrixWorldInverse, petPx = stage.petPx;
  const chest = anchors.items.find((a) => a.key === 'body');
  const zc = chest ? chest.w.clone().applyMatrix4(inv).z : 0;
  let best = null, bs = 1e9;
  for (const it of zones.items) {
    if (it.w.clone().applyMatrix4(inv).z < zc - 0.12) continue;          // behind the body: not touchable from here
    const p = stage.project(it.w);
    const s = Math.hypot(x - p.x, y - p.y) / Math.max(4, it.r * petPx);
    if (s < bs) { bs = s; best = it.zone; }
  }
  return best;
}

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, Math.max(0.001, (now - last) / 1000)); last = now;
  fpsAcc[0] += dt; fpsAcc[1]++;
  if (fpsAcc[0] > 1) { fps = Math.round(fpsAcc[1] / fpsAcc[0]); fpsAcc = [0, 0]; }
  if (ready) {
    rig.resetBeforeMixer();
    mixer.update(dt);
    if (hold && current === hold.action && hold.left > 0 && current.time >= hold.end) {
      current.time -= hold.end - hold.start;               // hover: the airborne part is periodic -> seamless loop
      hold.left--;
    }
    rig.captureAfterMixer();
    if (lift) {                                            // flight: rise higher than the bake (shadow follows)
      const k = (lift.clips[currentName] ?? 1) - 1;
      liftK += (k - liftK) * (1 - Math.exp(-dt / 0.3));
      const dy = Math.max(0, (lift.bone.position.y - lift.restY) * lift.scale);
      stage.setLift(liftK * dy, dy * (1 + liftK));
    }
    const ang = (b) => (b ? 2 * Math.acos(Math.min(1, Math.abs(b.quaternion.dot(rig.rest.get(b))))) * 57.2958 : 0);
    const lidMix = trace ? ang(rig.lids?.[0]) : 0, headMix = trace ? ang(rig.head) : 0;
    stage.root.updateMatrixWorld(true);
    anchors.update();
    const h = project('head');
    if (h) {                                               // smoothed: the head's own bobbing must not jitter the gaze
      if (!headPx.init) Object.assign(headPx, h, { init: true });
      const k = 1 - Math.exp(-dt / 0.25);
      headPx.x += (h.x - headPx.x) * k; headPx.y += (h.y - headPx.y) * k;
    }
    const active = Math.exp(-(now - cursorMovedAt) / 6000);
    const jt = jawForce ?? audio.jawNow();                 // lip-sync: fast open, slightly slower close (readable)
    jawSm += (jt - jawSm) * (1 - Math.exp(-dt / (jt > jawSm ? 0.025 : 0.07)));
    rig.apply(dt, {
      cursor, headPx, petPx: stage.petPx, camera: stage.camera, look: out.gaze?.cursor_weight || 0,
      follow: out.follow, clip: currentName, asleep: out.behaviour === 'sleep', face: out.face, active,
      blink: pendingBlink, saccade: pendingSaccade, jawDeg: jawSm,
    });
    pendingBlink = null; pendingSaccade = false;
    if (trace && rig.dbg) {
      const d = rig.dbg;
      trace.rows.push([Math.round(now), currentName, +d.lid.toFixed(2), +d.ey.toFixed(2), +d.ep.toFixed(2),
        +d.pin.toFixed(3), +d.b.toFixed(3), +d.w.toFixed(3), +d.body.toFixed(2), out.behaviour || '', +lidMix.toFixed(2),
        +headMix.toFixed(2),
        mixer._actions.filter((a) => a.isRunning()).map((a) => `${a.getClip().name}:${a.getEffectiveWeight().toFixed(2)}`).join(',')]);
      if (trace.rows.length >= trace.n) { post('trace', { rows: trace.rows }); trace = null; }
    }
    stage.root.updateMatrixWorld(true);
    anchors.update(); zones.update();
    const A = {};
    for (const it of anchors.items) A[it.key] = stage.project(it.w);
    fx.setAnchors(A, stage.petPx / (manifest.fx?.scale_ref_px || 190), stage.floorY);
    touch.update(dt, stage.over, zoneAt, headPx, stage.petPx);
  }
  fx.update(dt);
  fx.draw();
  if (cursor && !touch.dragging) stage.probe(cursor.x, cursor.y); else stage.probe(-1, -1);
  stage.render();
  if (snapReq) {
    const tag = snapReq; snapReq = null;
    const c = document.createElement('canvas');
    c.width = $('three').width; c.height = $('three').height;
    const g = c.getContext('2d');
    g.drawImage($('three'), 0, 0); g.drawImage($('fx'), 0, 0, c.width, c.height);
    post('snapshot', { tag, png: c.toDataURL('image/png'), modelPng: $('three').toDataURL('image/png'), fps, over: stage.over, zone: touch.zone });
  }
}
requestAnimationFrame(frame);

new QWebChannel(qt.webChannelTransport, (ch) => {
  bridge = ch.objects.pet;
  bridge.stateSig.connect((text) => { try { consume(JSON.parse(text)); } catch (e) { post('error', { msg: String(e.stack || e) }); } });
  resize();
  bridge.ready();
});
