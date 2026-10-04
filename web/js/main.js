import { obtenerSalud, reconstruir, decodificarVolumen } from "./api.js";
import { ANGULOS, archivos, iniciarCarga, limpiarCarga } from "./carga.js";
import { construirVisor } from "./visor.js";

const $ = (id) => document.getElementById(id);

// ---------- Estado del servicio ----------
async function comprobarServicio() {
  try {
    const s = await obtenerSalud();
    $("dot").className = "dot on";
    $("estado-servicio").textContent =
      "Servicio en línea · " + (s.metodo === "unet_refinamiento" ? "U-Net EN-1" : "retroproyección simple");
  } catch {
    $("dot").className = "dot off";
    $("estado-servicio").textContent = "Servicio no disponible";
  }
}

function actualizarBoton() {
  const n = Object.keys(archivos).length;
  $("btn-reconstruir").disabled = n !== 4;
  $("msg").className = "msg";
  $("msg").textContent = n === 4 ? "Listo: 4 proyecciones asignadas (0°, 45°, 90°, 135°)."
                                 : `Faltan ${4 - n} proyección(es).`;
}

// ---------- Llamada al servicio ----------
async function enviarEstudio() {
  const btn = $("btn-reconstruir");
  const fd = new FormData();
  ANGULOS.forEach(({ ang }) => fd.append("proyeccion_" + ang, archivos[ang]));
  const id = $("id-estudio").value.trim();
  if (id) fd.append("id_estudio", id);
  fd.append("organo", "pulmon");

  btn.disabled = true;
  btn.innerHTML = '<i class="spin" aria-hidden="true"></i>Reconstruyendo…';
  $("msg").textContent = "Reconstruyendo el volumen…";
  const t0 = performance.now();
  try {
    const { ok, datos: j } = await reconstruir(fd);
    if (!ok) throw new Error((j.archivo_rechazado ? j.archivo_rechazado + ": " : "") + j.detalle);
    mostrarResultado(j, (performance.now() - t0) / 1000);
  } catch (e) {
    $("msg").className = "msg err";
    $("msg").textContent = "Rechazado · " + e.message;
  } finally {
    btn.innerHTML = "Reconstruir volumen";
    actualizarBoton();
  }
}

// ---------- Resultado ----------
function mostrarResultado(j, total) {
  const vol = decodificarVolumen(j.volumen);

  $("r-estado").textContent = j.estado;
  $("r-id").textContent = j.id_estudio;
  $("r-metodo").textContent = j.metodo === "unet_refinamiento" ? "U-Net (EN-1)" : "Retroproyección";
  $("r-forma").textContent = j.volumen.forma.join(" × ");
  $("r-tiempo").textContent = j.tiempo_s.toFixed(2) + " s";
  $("r-total").textContent = total.toFixed(2) + " s";
  $("r-descarga").href = j.descarga;
  const vista = { ...j, volumen: { ...j.volumen, datos_base64: j.volumen.datos_base64.slice(0, 60) + "… (" + j.volumen.datos_base64.length.toLocaleString() + " caracteres)" } };
  $("r-json").textContent = JSON.stringify(vista, null, 2);

  construirVisor($("visor"), vol, [j.estadisticas.min, j.estadisticas.max]);
  $("resultado").classList.add("on");
  $("resultado").scrollIntoView({ behavior: "smooth" });
  $("t-resultado").focus({ preventScroll: true });   // lleva el foco al resultado (2.4.3)
}

// ---------- Inicio ----------
iniciarCarga($("proys"), $("btn-multi"), $("multi"), actualizarBoton);
$("btn-reconstruir").addEventListener("click", enviarEstudio);
$("btn-limpiar").addEventListener("click", () => {
  limpiarCarga();
  $("resultado").classList.remove("on");
});
$("btn-nuevo").addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
  $("id-estudio").focus({ preventScroll: true });
});
comprobarServicio();