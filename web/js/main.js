import { obtenerSalud, reconstruir, decodificarVolumen, loadStudyResult } from "./api.js";
import { ANGULOS, archivos, rechazos, errorSeleccion,
         iniciarCarga, limpiarCarga, marcarRechazo } from "./carga.js";
import { construirVisor } from "./visor.js";

const $ = (id) => document.getElementById(id);
const TEXTO_ESTADO = {
  pendiente: "Pendiente",
  listo: "Listo para procesar",
  procesando: "Procesando",
  completado: "Reconstrucción completada",
  rechazado: "Rechazado",
};
const PASO_DE_ESTADO = {
  pendiente: "carga", listo: "carga", rechazado: "carga",
  procesando: "proceso", completado: "resultado",
};
const escapar = (t) => String(t).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let procesando = false;

// ---------- Estado del servicio ----------
async function comprobarServicio() {
  try {
    const s = await obtenerSalud();
    $("dot").className = "dot on";
    $("estado-servicio").textContent =
      "Servicio en línea · " + (s.metodo === "four_stage_pipeline" ? "EN-1 + EN-4" : s.metodo);
  } catch {
    $("dot").className = "dot off";
    $("estado-servicio").textContent = "Servicio no disponible";
  }
}

// ---------- Estado del estudio y progreso ----------
function ponerEstado(estado, detalle) {
  const badge = $("estado-estudio");
  badge.dataset.estado = estado;
  badge.textContent = TEXTO_ESTADO[estado];
  $("msg-detalle").textContent = detalle;

  const actual = PASO_DE_ESTADO[estado];
  const orden = ["carga", "proceso", "resultado"];
  document.querySelectorAll("#pasos li").forEach((li) => {
    const i = orden.indexOf(li.dataset.paso);
    li.classList.toggle("hecho", i < orden.indexOf(actual) || (estado === "completado" && i === 2));
    if (li.dataset.paso === actual) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });
}

function mostrarRechazos() {
  const lista = Object.entries(rechazos).map(([ang, r]) =>
    `<li>${ang}° · <code>${escapar(r.archivo)}</code> — ${escapar(r.motivo)}</li>`);
  const sel = errorSeleccion();
  let html = "";
  if (sel) {
    html += `<b>${escapar(sel.motivo)}</b><ul>${sel.archivos.map((n) => `<li><code>${escapar(n)}</code></li>`).join("")}</ul>`;
  }
  if (lista.length) {
    html += `<b>Archivo(s) rechazado(s). El estudio no se procesará hasta corregirlos:</b><ul>${lista.join("")}</ul>`;
  }
  $("errores").innerHTML = html;
  return Boolean(html);
}

// Se llama cada vez que cambia una casilla
function alCambiarCarga() {
  if (procesando) return;
  const hayRechazo = mostrarRechazos();
  const n = Object.keys(archivos).length;
  $("btn-reconstruir").disabled = n !== 4 || hayRechazo;
  bloquearVista();                     // cualquier cambio invalida el resultado anterior
  if (hayRechazo) ponerEstado("rechazado", "Corrige o quita los archivos marcados en rojo.");
  else if (n === 4) ponerEstado("listo", "4 proyecciones asignadas (0°, 45°, 90°, 135°).");
  else ponerEstado("pendiente", `Faltan ${4 - n} proyección(es).`);
}

// ---------- Llamada al servicio ----------
async function enviarEstudio() {
  const btn = $("btn-reconstruir");
  const fd = new FormData();
  ANGULOS.forEach(({ ang }) => fd.append("proyeccion_" + ang, archivos[ang]));
  const id = $("id-estudio").value.trim();
  if (id) fd.append("id_estudio", id);
  fd.append("organo", "pulmon");

  procesando = true;
  btn.disabled = true;
  btn.innerHTML = '<i class="spin" aria-hidden="true"></i>Reconstruyendo…';
  ponerEstado("procesando", "Reconstruyendo el volumen…");
  const t0 = performance.now();                 // inicio: el médico envía la carga
  try {
    const { ok, datos: j } = await reconstruir(fd);
    if (!ok) {
      procesando = false;
      const marcado = j.archivo_rechazado && marcarRechazo(j.archivo_rechazado, j.detalle);
      if (!marcado) ponerEstado("rechazado", j.detalle);
      return;
    }
    await mostrarResultado(j);
    const segundos = (performance.now() - t0) / 1000;   // fin: la vista ya está habilitada
    $("r-total").textContent = segundos.toFixed(2) + " s";
    procesando = false;
    ponerEstado("completado", `Vista habilitada en ${segundos.toFixed(2)} s.`);
  } catch (e) {
    procesando = false;
    ponerEstado("rechazado", "No se pudo contactar con el servicio. ¿Está encendido?");
  } finally {
    btn.innerHTML = "Reconstruir volumen";
    btn.disabled = Object.keys(archivos).length !== 4;
  }
}

// ---------- Resultado ----------
function bloquearVista() {
  $("bloqueado").hidden = false;
  $("contenido").hidden = true;
  $("r-estado-caja").hidden = true;
}

async function mostrarResultado(j) {
  const vol = decodificarVolumen(j.volumen);
  $("r-estado").textContent = j.estado;
  $("r-id").textContent = j.id_estudio;
  $("r-metodo").textContent = j.metodo === "four_stage_pipeline" ? "EN-1 + EN-4 + meshes" : j.metodo;
  $("r-forma").textContent = j.volumen.forma.join(" × ");
  $("r-tiempo").textContent = j.tiempo_s.toFixed(2) + " s";
  $("r-descarga").href = j.descarga;
  $("r-mesh-viewer").href = `/mesh-viewer.html?study=${encodeURIComponent(j.id_estudio)}`;
  $("r-mesh-viewer").hidden = !(j.archivos_resultado?.organ_glb && j.archivos_resultado?.tumor_glb);
  const vista = { ...j, volumen: { ...j.volumen, datos_base64: j.volumen.datos_base64.slice(0, 60) + "… (" + j.volumen.datos_base64.length.toLocaleString() + " caracteres)" } };
  $("r-json").textContent = JSON.stringify(vista, null, 2);

  $("bloqueado").hidden = true;
  $("contenido").hidden = false;
  $("r-estado-caja").hidden = false;
  construirVisor($("visor"), vol, [j.estadisticas.min, j.estadisticas.max]);
  await new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));  // ya pintado
  $("resultado").scrollIntoView({ behavior: "smooth" });
  $("t-resultado").focus({ preventScroll: true });   // lleva el foco al resultado (2.4.3)
}

// ---------- Inicio ----------
iniciarCarga($("proys"), $("btn-multi"), $("multi"), alCambiarCarga);
$("btn-reconstruir").addEventListener("click", enviarEstudio);
$("btn-limpiar").addEventListener("click", limpiarCarga);
$("btn-nuevo").addEventListener("click", () => {
  limpiarCarga();
  $("id-estudio").value = "";
  window.scrollTo({ top: 0, behavior: "smooth" });
  $("id-estudio").focus({ preventScroll: true });
});
alCambiarCarga();
comprobarServicio();

const savedStudyId = new URLSearchParams(window.location.search).get("study");
if (savedStudyId) {
  loadStudyResult(savedStudyId).then(async (result) => {
    if (!result.volumen) throw new Error("Study has no completed volume");
    await mostrarResultado(result);
    $("r-total").textContent = "Stored result";
    ponerEstado("completado", "Resultado recuperado del almacenamiento.");
  }).catch(() => ponerEstado("rechazado", "No se pudo recuperar el estudio."));
}
