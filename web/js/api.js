const BASE = "";   // mismo origen que la página (http://127.0.0.1:8000)

export async function obtenerSalud() {
  const resp = await fetch(`${BASE}/salud`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function reconstruir(formulario) {
  const resp = await fetch(`${BASE}/reconstruir`, { method: "POST", body: formulario });
  const datos = await resp.json();
  return { ok: resp.ok, datos };
}

// Convierte el volumen en base64 de la respuesta en un Float32Array
export function decodificarVolumen(volumen) {
  const bin = atob(volumen.datos_base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}