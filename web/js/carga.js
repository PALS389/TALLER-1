import { G, leerNpy, leerPng, pintar } from "./imagen.js";

export const ANGULOS = [
  { ang: 0,   nombre: "Proyección AP" },
  { ang: 45,  nombre: "Oblicua 45°" },
  { ang: 90,  nombre: "Lateral" },
  { ang: 135, nombre: "Oblicua 135°" },
];
export const archivos = {};          // ang -> File
let alCambiar = () => {};
let contenedor = null;

export function iniciarCarga(cont, entradaMultiple, onCambio) {
  contenedor = cont;
  alCambiar = onCambio;
  crearRanuras();
  // Varios archivos a la vez: se asignan por el sufijo _000/_045/_090/_135 o por orden
  entradaMultiple.addEventListener("change", (e) => {
    const lista = [...e.target.files].sort((a, b) => a.name.localeCompare(b.name));
    lista.slice(0, 4).forEach((f, i) => {
      const m = f.name.match(/_(\d{1,3})\.(png|npy)$/i);
      const ang = m && ANGULOS.some((a) => a.ang === +m[1]) ? +m[1] : ANGULOS[i].ang;
      asignar(ang, f);
    });
    e.target.value = "";
  });
}

export function limpiarCarga() {
  Object.keys(archivos).forEach((k) => delete archivos[k]);
  contenedor.innerHTML = "";
  crearRanuras();
  alCambiar();
}

function crearRanuras() {
  ANGULOS.forEach(({ ang, nombre }) => {
    const slot = document.createElement("label");
    slot.className = "slot";
    slot.id = "slot-" + ang;
    slot.innerHTML = `
      <canvas width="${G}" height="${G}"></canvas>
      <b>${ang}° · ${nombre}</b>
      <span>sin cargar</span>
      <input type="file" accept=".png,.npy" hidden>`;
    const input = slot.querySelector("input");
    input.addEventListener("change", () => input.files[0] && asignar(ang, input.files[0]));
    slot.addEventListener("dragover", (e) => { e.preventDefault(); slot.classList.add("drag"); });
    slot.addEventListener("dragleave", () => slot.classList.remove("drag"));
    slot.addEventListener("drop", (e) => {
      e.preventDefault(); slot.classList.remove("drag");
      if (e.dataTransfer.files[0]) asignar(ang, e.dataTransfer.files[0]);
    });
    contenedor.appendChild(slot);
  });
}

async function asignar(ang, file) {
  const slot = document.getElementById("slot-" + ang);
  const ext = file.name.split(".").pop().toLowerCase();
  slot.querySelector("span").textContent = file.name;
  try {
    if (!["png", "npy"].includes(ext)) throw new Error("formato no admitido");
    const img = ext === "npy" ? await leerNpy(file) : await leerPng(file);
    pintar(slot.querySelector("canvas"), img, (r, c) => img[c * G + (G - 1 - r)]);
    archivos[ang] = file;
    slot.className = "slot lleno";
  } catch (e) {
    delete archivos[ang];
    slot.className = "slot malo";
    slot.querySelector("span").textContent = file.name + " · " + e.message;
  }
  alCambiar();
}