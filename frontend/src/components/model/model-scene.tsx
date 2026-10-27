"use client";

/**
 * Interactive 3D view of a measured IGES model (three.js, loaded only with the model tab).
 *
 * The backend sends binary glTF with one mesh per measured feature (node name = feature id),
 * so the cited feature is a mesh we can light up, and a click on a face selects that feature's
 * fact. Rendering is on demand (no idle loop). Reduced motion turns camera tweens into jumps.
 * WebGL failures and lost contexts are reported so the caller can show the projections instead.
 */

import { useEffect, useLayoutEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { ModelFeature } from "@/lib/api/schemas";

export type ViewPreset = "iso" | "front" | "top" | "right";

type Props = {
  url: string;
  features: ModelFeature[];
  primary: string | null; // feature id
  related: string[]; // feature ids
  hovered: string | null;
  section: boolean;
  edges: boolean;
  preset: ViewPreset;
  presetNonce: number; // re-apply the same preset when clicked again
  onPick: (featureId: string) => void;
  onHover: (featureId: string | null) => void;
  onUnsupported: (reason: string) => void;
  onLoaded?: (triangles: number) => void;
};

// Tailwind palette values (three.js needs numbers, not classes).
const COLOR = {
  light: {
    body: 0xd4d4d8,
    boss: 0xc4c4cc,
    bore: 0x0ea5e9,
    hole: 0x06b6d4,
    pattern: 0x14b8a6,
    chamfer: 0x8b5cf6,
    edge: 0x27272a,
  },
  dark: {
    body: 0x71717a,
    boss: 0x8b8b94,
    bore: 0x38bdf8,
    hole: 0x22d3ee,
    pattern: 0x2dd4bf,
    chamfer: 0xa78bfa,
    edge: 0xe4e4e7,
  },
};
const PRIMARY = new THREE.Color(0xf59e0b);
const RELATED = new THREE.Color(0xfcd34d);
const HOVER = new THREE.Color(0x06b6d4);

const DIRECTIONS: Record<ViewPreset, THREE.Vector3> = {
  iso: new THREE.Vector3(1, -1.2, 0.9).normalize(),
  front: new THREE.Vector3(0, -1, 0),
  top: new THREE.Vector3(0, 0, 1),
  right: new THREE.Vector3(1, 0, 0),
};

function colorFor(kind: string | undefined, theme: "light" | "dark") {
  const c = COLOR[theme];
  if (kind === "bore") return c.bore;
  if (kind === "hole") return c.hole;
  if (kind === "hole_pattern" || kind === "counterbore") return c.pattern;
  if (kind === "chamfer" || kind === "fillet") return c.chamfer;
  if (kind === "boss") return c.boss;
  return c.body;
}

const isDark = () => document.documentElement.classList.contains("dark");
const reducedMotion = () =>
  document.documentElement.dataset.motion === "reduced" ||
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function ModelScene(props: Props) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{
    setState: (p: Props) => void;
    frame: (featureId: string | null, preset: ViewPreset) => void;
  } | null>(null);
  const latest = useRef(props);
  // The scene's event handlers read the newest props without rebuilding the scene.
  useLayoutEffect(() => {
    latest.current = props;
  });

  // Build the scene once per model URL.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    } catch {
      latest.current.onUnsupported("WebGL is not available in this browser");
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.localClippingEnabled = true;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    renderer.domElement.className = "block size-full touch-none outline-none";
    renderer.domElement.setAttribute("aria-hidden", "true");

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8a94, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    scene.add(key, fill);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100000);
    camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.screenSpacePanning = true;

    const meshes = new Map<string, THREE.Mesh[]>();
    let edgeLines: THREE.LineSegments | null = null;
    const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    const box = new THREE.Box3();
    let radius = 50;
    let disposed = false;
    let tween = 0;

    const render = () => {
      if (!disposed) renderer.render(scene, camera);
    };
    controls.addEventListener("change", render);

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    const featureKind = new Map(latest.current.features.map((f) => [f.feature_id, f.kind]));

    const paint = (p: Props) => {
      const theme = isDark() ? "dark" : "light";
      for (const [fid, list] of meshes) {
        for (const m of list) {
          const mat = m.material as THREE.MeshStandardMaterial;
          mat.color.setHex(colorFor(featureKind.get(fid), theme));
          const emissive =
            fid === p.primary
              ? PRIMARY
              : p.related.includes(fid)
                ? RELATED
                : fid === p.hovered
                  ? HOVER
                  : null;
          mat.emissive.copy(emissive ?? new THREE.Color(0x000000));
          mat.emissiveIntensity = fid === p.primary ? 0.75 : emissive ? 0.45 : 0;
          mat.clippingPlanes = p.section ? [clip] : [];
          mat.needsUpdate = true;
        }
      }
      if (edgeLines) {
        edgeLines.visible = p.edges;
        const lm = edgeLines.material as THREE.LineBasicMaterial;
        lm.color.setHex(COLOR[theme].edge);
        lm.clippingPlanes = p.section ? [clip] : [];
      }
      render();
    };

    const frame = (featureId: string | null, preset: ViewPreset) => {
      const f = featureId ? latest.current.features.find((x) => x.feature_id === featureId) : null;
      const center = box.getCenter(new THREE.Vector3());
      const target = f?.anchor && f.anchor.length === 3 ? new THREE.Vector3(...f.anchor) : center;
      const dist = (f ? radius * 1.6 : radius * 2.6) / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / 2;
      const dir = DIRECTIONS[preset];
      const to = target.clone().add(dir.clone().multiplyScalar(dist));
      cancelAnimationFrame(tween);
      if (reducedMotion()) {
        controls.target.copy(target);
        camera.position.copy(to);
        controls.update();
        render();
        return;
      }
      const fromPos = camera.position.clone();
      const fromTarget = controls.target.clone();
      const start = performance.now();
      const step = (t: number) => {
        const k = Math.min(1, (t - start) / 450);
        const e = 1 - Math.pow(1 - k, 3);
        camera.position.lerpVectors(fromPos, to, e);
        controls.target.lerpVectors(fromTarget, target, e);
        controls.update();
        render();
        if (k < 1) tween = requestAnimationFrame(step);
      };
      tween = requestAnimationFrame(step);
    };

    api.current = { setState: paint, frame };

    // Picking: a click (not a drag) on a face selects its feature.
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pickAt = (ev: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const targets = [...meshes.values()].flat();
      const hit = ray.intersectObjects(targets, false).find((h) => {
        if (!latest.current.section) return true;
        return clip.distanceToPoint(h.point) >= 0;
      });
      const name = hit?.object.userData.feature as string | undefined;
      return name && name !== "body" ? name : null;
    };
    let downAt: { x: number; y: number } | null = null;
    const onDown = (ev: PointerEvent) => (downAt = { x: ev.clientX, y: ev.clientY });
    const onUp = (ev: PointerEvent) => {
      if (downAt && Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) < 4) {
        const fid = pickAt(ev);
        if (fid) latest.current.onPick(fid);
      }
      downAt = null;
    };
    let lastHover: string | null = null;
    const onMove = (ev: PointerEvent) => {
      if (ev.buttons) return;
      const fid = pickAt(ev);
      renderer.domElement.style.cursor = fid ? "pointer" : "grab";
      if (fid !== lastHover) {
        lastHover = fid;
        latest.current.onHover(fid);
      }
    };
    const onLeave = () => {
      if (lastHover) latest.current.onHover(null);
      lastHover = null;
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    const onLost = (ev: Event) => {
      ev.preventDefault();
      latest.current.onUnsupported("the 3D view lost its graphics context");
    };
    renderer.domElement.addEventListener("webglcontextlost", onLost);

    // Theme changes repaint without reloading.
    const mo = new MutationObserver(() => paint(latest.current));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    const controller = new AbortController();
    fetch(props.url, { signal: controller.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`mesh request failed (${r.status})`);
        return r.arrayBuffer();
      })
      .then((buf) => new GLTFLoader().parseAsync(buf, ""))
      .then((gltf) => {
        if (disposed) return;
        let triangles = 0;
        gltf.scene.traverse((obj) => {
          const feature = (obj.userData?.feature as string | undefined) ?? obj.parent?.userData?.feature;
          if (obj instanceof THREE.Mesh) {
            const fid = feature ?? obj.name ?? "body";
            obj.userData.feature = fid;
            obj.material = new THREE.MeshStandardMaterial({
              metalness: 0.25,
              roughness: 0.55,
              side: THREE.DoubleSide,
              polygonOffset: true,
              polygonOffsetFactor: 1,
              polygonOffsetUnits: 1,
            });
            triangles += (obj.geometry.index?.count ?? 0) / 3;
            const list = meshes.get(fid) ?? [];
            list.push(obj);
            meshes.set(fid, list);
          } else if (obj instanceof THREE.LineSegments) {
            obj.material = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.7 });
            edgeLines = obj;
          }
        });
        scene.add(gltf.scene);
        box.setFromObject(gltf.scene);
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        radius = Math.max(sphere.radius, 1);
        camera.near = radius / 100;
        camera.far = radius * 100;
        camera.updateProjectionMatrix();
        clip.constant = box.getCenter(new THREE.Vector3()).y;
        key.position.set(radius * 2, -radius * 3, radius * 4);
        fill.position.set(-radius * 3, radius * 2, radius);
        resize();
        paint(latest.current);
        frame(null, latest.current.preset);
        latest.current.onLoaded?.(Math.round(triangles));
      })
      .catch((err: unknown) => {
        if (!disposed && !(err instanceof DOMException && err.name === "AbortError")) {
          latest.current.onUnsupported(err instanceof Error ? err.message : "the model could not be loaded");
        }
      });

    return () => {
      disposed = true;
      controller.abort();
      cancelAnimationFrame(tween);
      ro.disconnect();
      mo.disconnect();
      controls.dispose();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          (obj.material as THREE.Material).dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      api.current = null;
    };
    // The scene is rebuilt only when the model changes.
  }, [props.url]);

  // Highlights, section and edges follow the props.
  const { primary, related, hovered, section, edges } = props;
  useEffect(() => {
    api.current?.setState(latest.current);
  }, [primary, related, hovered, section, edges]);

  // Frame the cited feature, or apply a view preset.
  const { preset, presetNonce } = props;
  useEffect(() => {
    api.current?.frame(primary, preset);
  }, [primary, preset, presetNonce]);

  return <div ref={host} className="size-full" />;
}
