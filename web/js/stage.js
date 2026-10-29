// Stage: renderer, camera framing, lights, contact shadow and model loading. Species-neutral; all numbers come from
// the pet's pet.json "stage" block. Model units: the GLB is normalised so the pet is stage.model_height tall, feet
// at y = 0, facing +Z (towards the camera).
import * as THREE from 'three';
import { GLTFLoader } from '/web/vendor/three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from '/web/vendor/three/addons/environments/RoomEnvironment.js';

function shadowTexture() {
  const s = 128, cv = document.createElement('canvas');
  cv.width = cv.height = s;
  const c = cv.getContext('2d');
  const g = c.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  g.addColorStop(0, 'rgba(0,0,0,1)'); g.addColorStop(0.45, 'rgba(0,0,0,0.55)'); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.fillRect(0, 0, s, s);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Stage {
  constructor(canvas) {
    const r = this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
    r.setClearColor(0x000000, 0);
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.NeutralToneMapping;      // keeps the painted v08 hues (ACES shifts orange towards yellow)
    r.toneMappingExposure = 1.0;
    this.gl = r.getContext();
    this.scene = new THREE.Scene();
    const pm = new THREE.PMREMGenerator(r);
    this.scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
    this.scene.environmentIntensity = 0.45;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x6b5640, 1.1));
    const key = new THREE.DirectionalLight(0xfff4e6, 2.1); key.position.set(-2.0, 4.0, 5.0); this.scene.add(key);
    const rim = new THREE.DirectionalLight(0xffffff, 1.3); rim.position.set(1.5, 3.0, -4.0); this.scene.add(rim);
    const fill = new THREE.DirectionalLight(0xffd9a0, 0.45); fill.position.set(4.0, 1.0, 2.0); this.scene.add(fill);
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.05, 50);
    this.pivot = new THREE.Group();            // body yaw (the +-30 deg turn towards the cursor) is applied here
    this.pivot.name = 'pet_pivot';
    this.scene.add(this.pivot);
    this.root = null;
    this.cfg = {};
    this.w = 1; this.h = 1; this.dpr = 1;
    this._probe = null; this._px = new Uint8Array(4 * 25);
    this.over = false;
  }

  async load(url, stageCfg) {
    this.cfg = stageCfg || {};
    const gltf = await new GLTFLoader().loadAsync(url);
    const root = gltf.scene;
    const H = this.cfg.model_height || 1.0;
    root.scale.setScalar(1.0 / H);
    root.traverse((o) => {
      if (o.isMesh) { o.frustumCulled = false; o.castShadow = o.receiveShadow = false; }
    });
    this.pivot.add(root);
    this.root = root;
    const sh = this.cfg.shadow;
    if (sh && sh.opacity > 0) {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
        new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, opacity: sh.opacity, depthWrite: false, toneMapped: false }));
      m.rotation.x = -Math.PI / 2;
      m.position.set(0, 0.003, 0.08);
      m.scale.set(sh.size?.[0] ?? 0.6, sh.size?.[1] ?? 0.35, 1);
      m.renderOrder = -1;
      m.name = 'contact_shadow';
      this.pivot.add(m);
      this.shadow = { mesh: m, sx: m.scale.x, sy: m.scale.y, op: sh.opacity };
    }
    this.root.updateMatrixWorld(true);
    return gltf;
  }

  // Window size changed: keep the pet at frame.height bird-heights per window height, feet frame.feet above the bottom.
  resize(w, h, dpr) {
    this.w = w; this.h = h; this.dpr = Math.min(dpr || 1, 2);
    this.renderer.setPixelRatio(this.dpr);
    this.renderer.setSize(w, h, false);
    const f = this.cfg.frame || { width: 2.0, height: 1.95, feet: 0.2 };
    const cam = this.cfg.camera || { fov: 30, elevation_deg: 8 };
    const c = this.camera;
    c.fov = cam.fov; c.aspect = w / h;
    const d = (f.height / 2) / Math.tan((cam.fov * Math.PI / 180) / 2);
    const ty = f.height / 2 - f.feet;                 // world y at the window centre
    const e = (cam.elevation_deg || 0) * Math.PI / 180;
    c.position.set(0, ty + d * Math.sin(e), d * Math.cos(e));
    c.lookAt(0, ty, 0);
    c.updateProjectionMatrix();
    this.petPx = h / f.height;                        // on-screen pet height (px)
    this.floorY = h - f.feet * this.petPx;             // feet line (px from top)
  }

  // v5 flight: raise the model by 'extra' (model units) on top of the clip's own root motion; the contact shadow
  // shrinks and fades with the total height above the floor
  setLift(extra, height) {
    if (!this.root) return;
    this.root.position.y = extra;
    if (this.shadow) {
      const k = Math.min(1, Math.max(0, height / 0.45));
      this.shadow.mesh.scale.set(this.shadow.sx * (1 - 0.45 * k), this.shadow.sy * (1 - 0.45 * k), 1);
      this.shadow.mesh.material.opacity = this.shadow.op * (1 - 0.65 * k);
    }
  }

  project(v, out = { x: 0, y: 0 }) {
    const p = v.clone().project(this.camera);
    out.x = (p.x + 1) / 2 * this.w; out.y = (1 - p.y) / 2 * this.h; out.z = p.z;
    return out;
  }

  // ask for an alpha test under the cursor during the next render (exact silhouette hit test, 5x5 px)
  probe(x, y) { this._probe = (x >= 0 && y >= 0 && x < this.w && y < this.h) ? [x, y] : null; if (!this._probe) this.over = false; }

  render() {
    this.renderer.render(this.scene, this.camera);
    if (this._probe) {
      const gl = this.gl, k = this.dpr;
      const px = Math.round(this._probe[0] * k), py = Math.round((this.h - this._probe[1]) * k);
      gl.readPixels(Math.max(0, px - 2), Math.max(0, py - 2), 5, 5, gl.RGBA, gl.UNSIGNED_BYTE, this._px);
      let a = 0;
      for (let i = 3; i < this._px.length; i += 4) a = Math.max(a, this._px[i]);
      this.over = a > 90;          // bird pixels are opaque; the soft contact shadow (~56) is not 'the bird'
      this._probe = null;
    }
  }
}
