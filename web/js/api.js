const BASE = "";   // mismo origen que la página (http://127.0.0.1:8000)

export async function obtenerSalud() {
  const resp = await fetch(`${BASE}/salud`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function reconstruir(formulario) {
  formulario.set("wait_for_result", "false");
  const resp = await fetch(`${BASE}/reconstruir`, { method: "POST", body: formulario });
  const datos = await resp.json();
  if (resp.status === 202) {
    const deadline = Date.now() + 300000;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const response = await fetch(`${BASE}${datos.result_url}`);
      const result = await response.json();
      if (!response.ok || result.estado === "Error") {
        return { ok: false, datos: { ...result, detalle: result.error || result.detail || "Processing failed" } };
      }
      if (result.volumen) return { ok: true, datos: result };
    }
    throw new Error("Processing timeout");
  }
  return { ok: resp.ok, datos };
}

export async function loadStudyResult(studyId) {
  const response = await fetch(`${BASE}/estudios/${encodeURIComponent(studyId)}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export async function loadMeshStudy(studyId) {
  const response = await fetch(`${BASE}/estudios/${encodeURIComponent(studyId)}?include_volume=false`);
  if (!response.ok) throw new Error("Study not found");
  return response.json();
}

export async function loadStudyMesh(studyId, name) {
  if (!["organ.glb", "tumor.glb"].includes(name)) throw new Error("Invalid mesh name");
  const response = await fetch(`${BASE}/estudios/${encodeURIComponent(studyId)}/meshes/${name}`);
  if (!response.ok) throw new Error("Mesh not available");
  return response.arrayBuffer();
}

// Convierte el volumen en base64 de la respuesta en un Float32Array
export function decodificarVolumen(volumen) {
  const bin = atob(volumen.datos_base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}
