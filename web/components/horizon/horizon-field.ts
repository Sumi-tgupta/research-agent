/**
 * Emerald Horizon — a WebGL field study.
 *
 * A wide grid of points laid on a receding plane. Layered traveling waves
 * lift them into a living surface; a "structure band" sweeps through depth so
 * the field periodically resolves into a tighter lattice — the signature idea
 * is a field that keeps forming structure and letting it dissolve. Colour runs
 * deep viridian in the troughs to luminous mint on the crests and along the
 * sweeping band, with rare champagne sparkles. It reads the shared horizon
 * store so pipeline activity tightens the lattice and each finished stage
 * sends a ripple across it.
 *
 * Framework-agnostic on purpose: React only mounts/tears it down. All motion
 * lives in the vertex shader (one draw call), so the CPU cost per frame is a
 * couple of uniform writes.
 */

import * as THREE from "three";
import {
  subscribeHorizon,
  getHorizonState,
  type HorizonState,
} from "@/lib/horizon-store";

export interface HorizonPalette {
  base: [number, number, number];
  glow: [number, number, number];
  accent: [number, number, number];
  opacity: number;
  additive: boolean;
}

export const DARK_PALETTE: HorizonPalette = {
  base: [0.047, 0.318, 0.22],
  glow: [0.435, 0.945, 0.761],
  accent: [0.925, 0.839, 0.651],
  opacity: 0.9,
  additive: true,
};

export const LIGHT_PALETTE: HorizonPalette = {
  base: [0.42, 0.62, 0.55],
  glow: [0.11, 0.5, 0.39],
  accent: [0.72, 0.55, 0.25],
  opacity: 0.5,
  additive: false,
};

const VERTEX_SHADER = /* glsl */ `
  uniform float uTime;
  uniform float uActivity;
  uniform float uPulse;
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uReducedMotion;

  attribute float aPhase;
  attribute float aSparkle;

  varying float vGlow;
  varying float vSparkle;
  varying float vFog;

  void main() {
    vec3 pos = position;
    float t = uTime;

    float w =
        sin(pos.x * 0.15 + t * 0.6 + aPhase) * 1.2
      + sin(pos.z * 0.12 - t * 0.4) * 1.6
      + sin((pos.x + pos.z) * 0.08 + t * 0.3) * 0.9;
    float motion = mix(0.18, 1.0, uActivity) * (1.0 - uReducedMotion * 0.82);
    pos.y += w * motion;

    float d = length(pos.xz);
    float ripple = sin(d * 0.2 - t * 3.0) * uPulse * 0.6;
    pos.y += ripple * (1.0 - uReducedMotion);

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mv;

    float band = fract(t * 0.045);
    float bandZ = mix(20.0, -120.0, band);
    float structure = smoothstep(26.0, 0.0, abs(pos.z - bandZ));

    float crest = smoothstep(0.4, 2.2, pos.y);
    vGlow = clamp(structure * 0.7 + crest * 0.5 + uActivity * 0.5 + uPulse * 0.4, 0.0, 1.0);
    vSparkle = aSparkle;

    float dist = -mv.z;
    vFog = clamp((dist - 20.0) / 120.0, 0.0, 1.0);

    float size = uSize * mix(0.6, 1.7, vGlow);
    gl_PointSize = size * uPixelRatio * (300.0 / max(dist, 1.0));
  }
`;

const FRAGMENT_SHADER = /* glsl */ `
  precision mediump float;

  uniform vec3 uColorBase;
  uniform vec3 uColorGlow;
  uniform vec3 uColorAccent;
  uniform float uOpacity;

  varying float vGlow;
  varying float vSparkle;
  varying float vFog;

  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float r = length(uv);
    if (r > 0.5) discard;
    float alpha = smoothstep(0.5, 0.0, r);
    alpha *= alpha;

    vec3 color = mix(uColorBase, uColorGlow, vGlow);
    color = mix(color, uColorAccent, step(0.985, vSparkle) * vGlow * 0.85);

    float a = alpha * uOpacity * (1.0 - vFog);
    if (a < 0.01) discard;
    gl_FragColor = vec4(color, a);
  }
`;

export default class HorizonField {
  private container: HTMLElement;
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private points: THREE.Points;
  private material: THREE.ShaderMaterial;
  private geometry: THREE.BufferGeometry;

  private clock = new THREE.Clock();
  private rafId = 0;
  private running = false;
  private reducedMotion = false;

  private currentActivity = getHorizonState().activity;
  private currentPulse = 0;

  private unsubscribeStore: () => void;
  private handleResize = () => this.resize();
  private handleVisibility = () => {
    if (document.hidden) this.stop();
    else if (!this.reducedMotion) this.start();
  };

  constructor(
    container: HTMLElement,
    palette: HorizonPalette,
    reducedMotion = false
  ) {
    this.container = container;
    this.reducedMotion = reducedMotion;

    const width = container.clientWidth || window.innerWidth;
    const height = container.clientHeight || window.innerHeight;

    this.renderer = new THREE.WebGLRenderer({
      antialias: false,
      alpha: true,
      powerPreference: "low-power",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    this.renderer.setSize(width, height);
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.domElement.style.display = "block";
    this.renderer.domElement.style.width = "100%";
    this.renderer.domElement.style.height = "100%";
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 400);
    this.camera.position.set(0, 12, 26);
    this.camera.lookAt(0, -2, -34);

    this.geometry = this.buildGeometry(width);
    this.material = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uActivity: { value: this.currentActivity },
        uPulse: { value: 0 },
        uSize: { value: 8.0 },
        uPixelRatio: { value: this.renderer.getPixelRatio() },
        uReducedMotion: { value: reducedMotion ? 1 : 0 },
        uColorBase: { value: new THREE.Vector3(...palette.base) },
        uColorGlow: { value: new THREE.Vector3(...palette.glow) },
        uColorAccent: { value: new THREE.Vector3(...palette.accent) },
        uOpacity: { value: palette.opacity },
      },
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: palette.additive
        ? THREE.AdditiveBlending
        : THREE.NormalBlending,
    });

    this.points = new THREE.Points(this.geometry, this.material);
    this.scene.add(this.points);

    window.addEventListener("resize", this.handleResize, { passive: true });
    document.addEventListener("visibilitychange", this.handleVisibility);
    this.renderer.domElement.addEventListener(
      "webglcontextlost",
      (e) => {
        e.preventDefault();
        this.stop();
      },
      false
    );

    this.unsubscribeStore = subscribeHorizon((s: HorizonState) => {
      // targets only; easing happens per-frame in render()
      void s;
    });

    // Always draw at least one frame so the field is visible immediately.
    this.renderFrame(0);
    if (!reducedMotion) this.start();
  }

  private buildGeometry(width: number): THREE.BufferGeometry {
    const dense = width < 640 ? 0.6 : width < 1100 ? 0.82 : 1;
    const cols = Math.round(180 * dense);
    const rows = Math.round(120 * dense);

    const spanX = 130;
    const nearZ = 22;
    const farZ = -128;

    const count = cols * rows;
    const positions = new Float32Array(count * 3);
    const phases = new Float32Array(count);
    const sparkles = new Float32Array(count);

    let i = 0;
    for (let c = 0; c < cols; c++) {
      for (let r = 0; r < rows; r++) {
        const u = cols > 1 ? c / (cols - 1) : 0.5;
        const v = rows > 1 ? r / (rows - 1) : 0.5;
        // widen the field toward the horizon for a sense of depth
        const widen = 0.6 + v * 0.9;
        positions[i * 3] = (u - 0.5) * spanX * widen;
        positions[i * 3 + 1] = 0;
        positions[i * 3 + 2] = nearZ + v * (farZ - nearZ);
        phases[i] = Math.random() * Math.PI * 2;
        sparkles[i] = Math.random();
        i++;
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
    geo.setAttribute("aSparkle", new THREE.BufferAttribute(sparkles, 1));
    return geo;
  }

  setPalette(palette: HorizonPalette) {
    const u = this.material.uniforms;
    (u.uColorBase.value as THREE.Vector3).set(...palette.base);
    (u.uColorGlow.value as THREE.Vector3).set(...palette.glow);
    (u.uColorAccent.value as THREE.Vector3).set(...palette.accent);
    u.uOpacity.value = palette.opacity;
    this.material.blending = palette.additive
      ? THREE.AdditiveBlending
      : THREE.NormalBlending;
    this.material.needsUpdate = true;
    if (!this.running) this.renderFrame(this.clock.getElapsedTime());
  }

  setReducedMotion(reduced: boolean) {
    this.reducedMotion = reduced;
    this.material.uniforms.uReducedMotion.value = reduced ? 1 : 0;
    if (reduced) {
      this.stop();
      this.renderFrame(this.clock.getElapsedTime());
    } else {
      this.start();
    }
  }

  private resize() {
    const width = this.container.clientWidth || window.innerWidth;
    const height = this.container.clientHeight || window.innerHeight;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.material.uniforms.uPixelRatio.value = this.renderer.getPixelRatio();
    if (!this.running) this.renderFrame(this.clock.getElapsedTime());
  }

  private renderFrame(elapsed: number) {
    const u = this.material.uniforms;

    // Ease ambient activity toward the store's target.
    const target = getHorizonState().activity;
    this.currentActivity += (target - this.currentActivity) * 0.05;
    u.uActivity.value = this.currentActivity;

    // Consume + decay the pulse.
    const state = getHorizonState();
    if (state.pulse > this.currentPulse) this.currentPulse = state.pulse;
    this.currentPulse *= 0.94;
    state.pulse *= 0.9;
    if (state.pulse < 0.01) state.pulse = 0;
    u.uPulse.value = this.currentPulse;

    u.uTime.value = elapsed;
    this.renderer.render(this.scene, this.camera);
  }

  private loop = () => {
    if (!this.running) return;
    this.rafId = requestAnimationFrame(this.loop);
    this.renderFrame(this.clock.getElapsedTime());
  };

  start() {
    if (this.running || this.reducedMotion) return;
    this.running = true;
    if (!this.clock.running) this.clock.start();
    this.rafId = requestAnimationFrame(this.loop);
  }

  stop() {
    this.running = false;
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = 0;
  }

  dispose() {
    this.stop();
    window.removeEventListener("resize", this.handleResize);
    document.removeEventListener("visibilitychange", this.handleVisibility);
    this.unsubscribeStore?.();
    this.geometry.dispose();
    this.material.dispose();
    this.renderer.dispose();
    if (this.renderer.domElement.parentNode === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
