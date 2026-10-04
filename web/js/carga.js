import { G, leerNpy, leerPng, pintar } from "./imagen.js";

export const ANGULOS = [
  { ang: 0,   nombre: "Proyección AP" },
  { ang: 45,  nombre: "Oblicua 45°" },
  { ang: 90,  nombre: "Lateral" },
  { ang: 135, nombre: "Oblicua 135°" },
];
export const archivos = {};     
export const rechazos = {};     
let rechazoSeleccion = null;       
let alCambiar = () => {};
let contenedor = null;

export function iniciarCarga(cont, botonMultiple, entradaMultiple, onCambio) {
  contenedor = cont;
  alCambiar = onCambio;
  crearRanuras();
  botonMultiple.addEventListener("click", () => entradaMultiple.click());
  entradaMultiple.addEventListener("change", (e) => {
    asignarVarios([...e.target.files]);
    e.target.value = "";
  });
}

export function errorSeleccion() { return rechazoSeleccion; }

// Varios archivos a la vez: deben ser exactamente 4 y se asignan por el sufijo
// _000/_045/_090/_135 del nombre o, si no lo tienen, por orden alfabético.
function asignarVarios(lista) {
  rechazoSeleccion = null;
  lista.sort((a, b) => a.name.localeCompare(b.name));
  if (lista.length !== 4) {
    rechazoSeleccion = {
      motivo: `Se seleccionaron ${lista.length} archivo(s); se requieren exactamente 4. No se cargó ninguno.`,
      archivos: lista.map((f) => f.name),
    };
    alCambiar();
    return;
  }
  const destino = lista.map((f, i) => {
    const m = f.name.match(/_(\d{1,3})\.[a-z0-9]+$/i);
    return m && ANGULOS.some((a) => a.ang === +m[1]) ? +m[1] : ANGULOS[i].ang;
  });
  const repetidos = lista.filter((_, i) => destino.indexOf(destino[i]) !== i);
  if (repetidos.length) {
    rechazoSeleccion = {
      motivo: "Dos archivos corresponden al mismo ángulo. No se cargó ninguno.",
      archivos: repetidos.map((f) => f.name),
    };
    alCambiar();
    return;
  }
  lista.forEach((f, i) => asignar(destino[i], f));
}

export function limpiarCarga() {
  Object.keys(archivos).forEach((k) => delete archivos[k]);
  Object.keys(rechazos).forEach((k) => delete rechazos[k]);
  rechazoSeleccion = null;
  contenedor.innerHTML = "";
  crearRanuras();
  alCambiar();
}

// El servicio rechazó un archivo: se marca su casilla con el motivo (HU-1.1)
export function marcarRechazo(nombreArchivo, motivo) {
  const ang = Object.keys(archivos).find((a) => archivos[a].name === nombreArchivo);
  if (ang === undefined) return false;
  ponerRechazo(+ang, archivos[ang], motivo);
  delete archivos[ang];
  alCambiar();
  return true;
}

function crearRanuras() {
  ANGULOS.forEach(({ ang, nombre }) => {
    const slot = document.createElement("li");
    slot.className = "slot";
    slot.id = "slot-" + ang;
    slot.innerHTML = `
      <button type="button" class="slot-btn">
        <canvas width="${G}" height="${G}" aria-hidden="true"></canvas>
        <b>${ang}° · ${nombre}</b>
        <span class="slot-estado">sin cargar</span>
      </button>
      <div class="slot-pie" hidden>
        <button type="button" class="btn-quitar" aria-label="Quitar la proyección de ${ang}°">Quitar</button>
      </div>
      <input type="file" accept=".png,.npy" hidden>`;
    const boton = slot.querySelector(".slot-btn");
    const input = slot.querySelector("input");
    boton.addEventListener("click", () => input.click());
    slot.querySelector(".btn-quitar").addEventListener("click", () => quitar(ang));
    input.addEventListener("change", () => { input.files[0] && asignar(ang, input.files[0]); input.value = ""; });
    slot.addEventListener("dragover", (e) => { e.preventDefault(); slot.classList.add("drag"); });
    slot.addEventListener("dragleave", () => slot.classList.remove("drag"));
    slot.addEventListener("drop", (e) => {
      e.preventDefault(); slot.classList.remove("drag");
      if (e.dataTransfer.files.length > 1) asignarVarios([...e.dataTransfer.files]);
      else if (e.dataTransfer.files[0]) asignar(ang, e.dataTransfer.files[0]);
    });
    contenedor.appendChild(slot);
    nombrar(ang, "sin cargar");
  });
}

// Nombre accesible de la casilla: ángulo + estado + acción
function nombrar(ang, estado) {
  const { nombre } = ANGULOS.find((a) => a.ang === ang);
  document.querySelector(`#slot-${ang} .slot-btn`)
    .setAttribute("aria-label", `${ang}° · ${nombre}: ${estado}. Seleccionar archivo`);
}

function ponerRechazo(ang, file, motivo) {
  const slot = document.getElementById("slot-" + ang);
  rechazos[ang] = { archivo: file.name, motivo };
  slot.querySelector("canvas").getContext("2d").clearRect(0, 0, G, G);   // sin imagen engañosa
  slot.className = "slot malo";
  slot.querySelector(".slot-estado").textContent = `${file.name} · ${motivo}`;
  slot.querySelector(".slot-pie").hidden = false;
  nombrar(ang, `rechazado ${file.name}, ${motivo}`);
}

function quitar(ang) {
  const slot = document.getElementById("slot-" + ang);
  delete archivos[ang];
  delete rechazos[ang];
  slot.className = "slot";
  slot.querySelector(".slot-estado").textContent = "sin cargar";
  slot.querySelector(".slot-pie").hidden = true;
  slot.querySelector("canvas").getContext("2d").clearRect(0, 0, G, G);
  nombrar(ang, "sin cargar");
  slot.querySelector(".slot-btn").focus();          // el foco no se pierde (2.4.3)
  alCambiar();
}

async function asignar(ang, file) {
  const slot = document.getElementById("slot-" + ang);
  const ext = file.name.split(".").pop().toLowerCase();
  rechazoSeleccion = null;
  try {
    if (!["png", "npy"].includes(ext)) throw new Error("formato no admitido (usa .png o .npy)");
    const img = ext === "npy" ? await leerNpy(file) : await leerPng(file);
    pintar(slot.querySelector("canvas"), img, (r, c) => img[c * G + (G - 1 - r)]);
    archivos[ang] = file;
    delete rechazos[ang];
    slot.className = "slot lleno";
    slot.querySelector(".slot-estado").textContent = file.name;
    slot.querySelector(".slot-pie").hidden = false;
    nombrar(ang, `cargado ${file.name}`);
  } catch (e) {
    delete archivos[ang];
    ponerRechazo(ang, file, e.message);
  }
  alCambiar();
}