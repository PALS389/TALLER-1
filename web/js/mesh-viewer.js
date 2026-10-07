/* EN-42 viewer adapted from Bray's delivery; study files come through Layer 1. */
import { loadMeshStudy, loadStudyMesh } from "./api.js";

const $ = (id) => document.getElementById(id);
const status = $("viewer-status");
window.lucide?.createIcons();

async function initialize() {
  const THREE = window.THREE;
  if (!THREE?.OrbitControls || !THREE?.GLTFLoader) throw new Error("No se pudo cargar el visor 3D.");
  const host = $("scene");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0e1114);
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.localClippingEnabled = true;
  renderer.domElement.setAttribute("aria-label", "Modelo 3D del órgano y tumor");
  host.appendChild(renderer.domElement);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotateSpeed = 2.2;
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const light = new THREE.DirectionalLight(0xffffff, 0.85);
  light.position.set(1, 1.2, 1);
  scene.add(light);
  const fill = new THREE.DirectionalLight(0x88bbff, 0.35);
  fill.position.set(-1, -0.6, -1);
  scene.add(fill);
  const group = new THREE.Group();
  scene.add(group);
  const plane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);
  const loader = new THREE.GLTFLoader();
  let organ = null, tumor = null, radius = 200, generation = 0, benchmark = null;

  function dispose(root) {
    root.traverse((object) => {
      object.geometry?.dispose();
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material) => material?.dispose());
    });
  }

  function clear() {
    const roots = new Set([...group.children, organ, tumor].filter(Boolean));
    for (const child of roots) { group.remove(child); dispose(child); }
    group.position.set(0, 0, 0);
    organ = tumor = null;
    if (benchmark) { benchmark = null; $("benchmark").disabled = false; }
    $("benchmark-result").textContent = "";
    $("organ-triangles").textContent = $("tumor-triangles").textContent = $("confidence").textContent = "-";
    renderer.domElement.dataset.meshCount = "0";
  }

  function parse(content, color, opaque) {
    return new Promise((resolve, reject) => loader.parse(content, "", (gltf) => {
      gltf.scene.traverse((object) => {
        if (!object.isMesh) return;
        const old = Array.isArray(object.material) ? object.material : [object.material];
        old.forEach((material) => material.dispose());
        object.material = new THREE.MeshStandardMaterial({ color, roughness: 0.78,
          metalness: 0, transparent: !opaque, opacity: opaque ? 1 : 0.35,
          side: opaque ? THREE.DoubleSide : THREE.FrontSide, depthWrite: opaque,
          clippingPlanes: [] });
      });
      resolve(gltf.scene);
    }, reject));
  }

  function triangles(root) {
    let count = 0;
    root?.traverse((object) => {
      if (object.isMesh) count += (object.geometry.index?.count ?? object.geometry.attributes.position.count) / 3;
    });
    return count;
  }

  function resetView() {
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect);
    const distance = radius / Math.sin(Math.min(verticalFov, horizontalFov) / 2) * 1.12;
    camera.position.set(1.9, 1.1, 1.9).normalize().multiplyScalar(distance);
    camera.near = radius * 0.02;
    camera.far = radius * 30;
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.update();
  }

  function applyControls() {
    const opacity = Number($("opacity").value) / 100;
    $("opacity-value").textContent = `${Math.round(opacity * 100)} %`;
    if (organ) {
      organ.visible = $("organ-visible").checked;
      organ.traverse((object) => {
        if (!object.isMesh) return;
        object.material.opacity = opacity;
        object.material.transparent = opacity < 0.99;
        object.material.depthWrite = opacity >= 0.99;
        object.material.needsUpdate = true;
      });
    }
    if (tumor) tumor.visible = $("tumor-visible").checked;
    const clipped = $("clip-enabled").checked;
    $("clip-position").disabled = !clipped;
    plane.constant = Number($("clip-position").value) / 100 * radius;
    $("clip-value").textContent = `${$("clip-position").value} %`;
    group.traverse((object) => {
      if (!object.isMesh) return;
      object.material.clippingPlanes = clipped ? [plane] : [];
      object.material.needsUpdate = true;
    });
    controls.autoRotate = Boolean(benchmark) || $("rotate").checked;
  }

  async function openStudy(studyId) {
    const token = ++generation;
    clear();
    $("mesh-controls").disabled = true;
    status.hidden = false;
    status.textContent = "Cargando mallas del estudio...";
    try {
      if (!/^[A-Za-z0-9_-]{1,64}$/.test(studyId)) throw new Error("Identificador de estudio inválido.");
      const study = await loadMeshStudy(studyId);
      if (study.estado !== "Reconstrucción completada") throw new Error("El estudio todavía no tiene mallas disponibles.");
      const contents = await Promise.all([loadStudyMesh(studyId, "organ.glb"), loadStudyMesh(studyId, "tumor.glb")]);
      if (token !== generation) return;
      const roots = await Promise.allSettled([parse(contents[0], 0x9fb6c9, false), parse(contents[1], 0xe8835a, true)]);
      if (token !== generation || roots.some((result) => result.status === "rejected")) {
        roots.forEach((result) => { if (result.status === "fulfilled") dispose(result.value); });
        if (token === generation) throw new Error("No se pudieron interpretar las mallas GLB.");
        return;
      }
      [organ, tumor] = roots.map((result) => result.value);
      if (!triangles(organ)) throw new Error("La malla del órgano no contiene geometría.");
      group.add(organ, tumor);
      const box = new THREE.Box3().setFromObject(group);
      radius = box.getSize(new THREE.Vector3()).length() * 0.5 || 200;
      group.position.sub(box.getCenter(new THREE.Vector3()));
      resetView();
      $("mesh-controls").disabled = false;
      $("tumor-visible").disabled = triangles(tumor) === 0;
      $("organ-triangles").textContent = triangles(organ).toLocaleString("es");
      $("tumor-triangles").textContent = triangles(tumor).toLocaleString("es");
      const confidence = study.metricas?.tumor_confidence;
      const maskMethod = study.metricas?.meshes?.organ?.segmentation?.mask_method;
      $("organ-source").textContent = maskMethod === "en42_internal_lung_air_v1"
        ? "Máscara pulmonar morfológica EN-42. Sin validación clínica. La confianza EN-4 no es precisión diagnóstica."
        : "Superficie del órgano aproximada; no es una segmentación pulmonar validada. La confianza EN-4 no es precisión diagnóstica.";
      $("confidence").textContent = Number.isFinite(confidence) ? `${(confidence * 100).toFixed(1)} %` : "-";
      $("back").href = `/?study=${encodeURIComponent(studyId)}`;
      const url = new URL(location.href); url.searchParams.set("study", studyId);
      history.replaceState(null, "", url);
      renderer.domElement.dataset.studyId = studyId;
      renderer.domElement.dataset.meshCount = String(group.children.length);
      status.textContent = triangles(tumor) ? "Mallas cargadas" : "No se detectó una malla tumoral.";
      status.hidden = triangles(tumor) > 0;
      applyControls();
    } catch (error) {
      if (token !== generation) return;
      clear();
      status.hidden = false;
      status.textContent = error.message || "No se pudo cargar el estudio.";
    }
  }

  $("study-form").addEventListener("submit", (event) => { event.preventDefault(); openStudy($("study-id").value.trim()); });
  ["opacity", "organ-visible", "tumor-visible", "clip-enabled", "clip-position", "rotate"].forEach((id) => $(id).addEventListener("input", applyControls));
  $("reset-view").addEventListener("click", resetView);
  $("benchmark").addEventListener("click", () => {
    if (!organ || benchmark) return;
    benchmark = { start: performance.now(), previous: performance.now(), intervals: [] };
    $("benchmark").disabled = true;
    applyControls();
  });
  const resize = () => {
    const width = host.clientWidth, height = host.clientHeight;
    renderer.setSize(width, height);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
    if (organ) resetView();
  };
  const observer = new ResizeObserver(resize); observer.observe(host); resize();

  let frameCount = 0, framesSinceUpdate = 0, lastUpdate = performance.now();
  function animate(now) {
    requestAnimationFrame(animate);
    controls.update(); renderer.render(scene, camera);
    frameCount++; framesSinceUpdate++;
    if (now - lastUpdate >= 1000) {
      $("fps").textContent = Math.round(framesSinceUpdate * 1000 / (now - lastUpdate));
      framesSinceUpdate = 0; lastUpdate = now;
      renderer.domElement.dataset.frames = String(frameCount);
      // Read rendered pixels for development QA without exposing WebGL internals.
      const gl = renderer.getContext(), width = gl.drawingBufferWidth, height = gl.drawingBufferHeight;
      const pixels = new Uint8Array(width * height * 4);
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      let visible = 0, signature = 0;
      for (let i = 0; i < pixels.length; i += 64) {
        if (Math.abs(pixels[i] - 14) + Math.abs(pixels[i + 1] - 17) + Math.abs(pixels[i + 2] - 20) > 20) visible++;
        signature = (signature * 31 + pixels[i] + pixels[i + 1] + pixels[i + 2]) >>> 0;
      }
      renderer.domElement.dataset.visiblePixels = String(visible);
      renderer.domElement.dataset.pixelSignature = String(signature);
    }
    if (benchmark) {
      benchmark.intervals.push(now - benchmark.previous); benchmark.previous = now;
      $("benchmark-result").textContent = `${Math.min(30, (now - benchmark.start) / 1000).toFixed(1)} / 30 s`;
      if (now - benchmark.start >= 30000) {
        const intervals = benchmark.intervals.slice(8).filter((interval) => interval > 0);
        const average = intervals.reduce((sum, interval) => sum + interval, 0) / intervals.length;
        const minimumFps = 1000 / Math.max(...intervals);
        $("benchmark-result").textContent = `Media ${(1000 / average).toFixed(1)} FPS | Mínimo ${minimumFps.toFixed(1)} FPS`;
        benchmark = null; $("benchmark").disabled = false; applyControls();
      }
    }
  }
  requestAnimationFrame(animate);
  const studyId = new URLSearchParams(location.search).get("study");
  if (studyId) { $("study-id").value = studyId; await openStudy(studyId); }
}

initialize().catch(() => { status.hidden = false; status.textContent = "No se pudo iniciar WebGL. Comprueba la aceleración gráfica del navegador."; });
