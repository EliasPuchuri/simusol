import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { DEFAULT_OPACITY } from "./defaults";

export class WebGLUnavailableError extends Error {}
export type Role = "previous" | "current" | "common" | "added" | "removed";

const COLORS: Record<Role, number> = {
  previous: 0xd9731a, current: 0x8a9199, common: 0x3d9a5a, added: 0x3b78c4, removed: 0x8a4fc4,
};

function label(text: string, color: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.font = "bold 36px system-ui, sans-serif";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 32);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
  sprite.scale.set(4, 1, 1);
  return sprite;
}

/**
 * Minimal comparison scene. Scene axes (Y-up): x = East, y = Elevation, z = -North,
 * with one origin shared by both periods (computed by the server).
 * Renders on demand and releases every GPU resource in `dispose()`.
 */
export class ThreeScene {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1e6);
  private controls: OrbitControls;
  private layers = new Map<Role, THREE.Group>();
  private helpers = new THREE.Group();
  private observer?: ResizeObserver;
  private frame = 0;
  private home = { position: new THREE.Vector3(), target: new THREE.Vector3() };
  private disposed = false;

  constructor(private container: HTMLElement) {
    try {
      this.renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      throw new WebGLUnavailableError("WebGL is not available");
    }
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0xf7f8f9);
    container.appendChild(this.renderer.domElement);

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(1, 2, 1.5);
    this.scene.add(sun, this.helpers);

    this.camera.up.set(0, 1, 0);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = false;
    this.controls.addEventListener("change", () => this.requestRender());

    this.resize();
    if (typeof ResizeObserver !== "undefined") {
      this.observer = new ResizeObserver(() => this.resize());
      this.observer.observe(container);
    }
    this.requestRender();
  }

  async setLayer(role: Role, url: string): Promise<void> {
    const gltf = await new GLTFLoader().loadAsync(url);
    if (this.disposed) {
      this.disposeObject(gltf.scene);
      return;
    }
    this.removeLayer(role);
    gltf.scene.traverse((node) => {
      const mesh = node as THREE.Mesh;
      if (!mesh.isMesh) return;
      (mesh.material as THREE.Material).dispose?.();
      if (!mesh.geometry.attributes.normal) mesh.geometry.computeVertexNormals();
      // Double sided: the pilot meshes have inverted global orientation (negative signed volume).
      // Overlay rule: the previous period is drawn first and writes depth; the current one is pulled slightly
      // forward (polygonOffset) so that where both surfaces coincide the current shows, and where the previous
      // one sticks out it stays visible.
      const material = new THREE.MeshStandardMaterial({
        color: COLORS[role], side: THREE.DoubleSide, roughness: 0.85, metalness: 0,
        polygonOffset: role === "current", polygonOffsetFactor: -2, polygonOffsetUnits: -2,
      });
      this.applyOpacity(material, DEFAULT_OPACITY[role]);
      mesh.material = material;
      mesh.renderOrder = role === "previous" ? 1 : role === "current" ? 2 : 3; // difference zones are drawn opaque, last
    });
    const group = new THREE.Group();
    group.add(gltf.scene);
    this.layers.set(role, group);
    this.scene.add(group);
    this.fit();
  }

  setVisible(role: Role, visible: boolean) {
    const group = this.layers.get(role);
    if (group) group.visible = visible;
    this.requestRender();
  }

  setOpacity(role: Role, opacity: number) {
    this.layers.get(role)?.traverse((node) => {
      const material = (node as THREE.Mesh).material as THREE.Material | undefined;
      if (material) this.applyOpacity(material, opacity);
    });
    this.requestRender();
  }

  resetView() {
    this.camera.position.copy(this.home.position);
    this.controls.target.copy(this.home.target);
    this.controls.update();
    this.requestRender();
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.observer?.disconnect();
    this.controls.dispose();
    this.disposeObject(this.scene);
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }

  // ---------------------------------------------------------------------------
  private applyOpacity(material: THREE.Material, opacity: number) {
    material.opacity = opacity;
    material.transparent = opacity < 1;
    material.depthWrite = opacity >= 1;
    material.needsUpdate = true;
  }

  private removeLayer(role: Role) {
    const old = this.layers.get(role);
    if (!old) return;
    this.scene.remove(old);
    this.disposeObject(old);
    this.layers.delete(role);
  }

  private disposeObject(root: THREE.Object3D) {
    root.traverse((node) => {
      const any = node as THREE.Mesh & THREE.Sprite;
      any.geometry?.dispose?.();
      const materials = Array.isArray(any.material) ? any.material : any.material ? [any.material] : [];
      for (const material of materials) {
        (material as THREE.SpriteMaterial).map?.dispose();
        material.dispose();
      }
    });
  }

  private fit() {
    const box = new THREE.Box3();
    this.layers.forEach((g) => box.expandByObject(g));
    if (box.isEmpty()) return;
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 1);

    this.camera.near = Math.max(radius / 1000, 0.01);
    this.camera.far = radius * 100;
    this.camera.updateProjectionMatrix();
    this.home.target.copy(center);
    this.home.position.copy(center).add(new THREE.Vector3(1, 0.8, 1.2).normalize().multiplyScalar(radius * 2.6));
    this.resetView();
    this.drawHelpers(box, radius);
  }

  private drawHelpers(box: THREE.Box3, radius: number) {
    this.helpers.children.slice().forEach((c) => {
      this.helpers.remove(c);
      this.disposeObject(c);
    });
    const step = 10 ** Math.floor(Math.log10(radius));
    const size = Math.ceil((radius * 2.4) / step) * step;
    const grid = new THREE.GridHelper(size, Math.round(size / step), 0xaab2b8, 0xdfe3e6);
    grid.position.set((box.min.x + box.max.x) / 2, box.min.y, (box.min.z + box.max.z) / 2);
    this.helpers.add(grid);

    const corner = new THREE.Vector3(box.min.x, box.min.y, box.max.z);
    const length = radius * 0.7;
    const axis = (dir: THREE.Vector3, color: number, text: string, css: string) => {
      const line = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([corner, corner.clone().addScaledVector(dir, length)]),
        new THREE.LineBasicMaterial({ color }),
      );
      const tag = label(text, css);
      tag.position.copy(corner).addScaledVector(dir, length * 1.12);
      tag.scale.set(length * 0.5, length * 0.125, 1);
      this.helpers.add(line, tag);
    };
    axis(new THREE.Vector3(1, 0, 0), 0xd33, "Este", "#d33");
    axis(new THREE.Vector3(0, 1, 0), 0x2a2, "Elevación", "#2a2");
    axis(new THREE.Vector3(0, 0, -1), 0x35c, "Norte", "#35c");
    this.requestRender();
  }

  private resize() {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  private requestRender() {
    if (this.disposed || this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      if (!this.disposed) this.renderer.render(this.scene, this.camera);
    });
  }
}
