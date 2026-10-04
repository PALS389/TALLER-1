import { G, pintar } from "./imagen.js";

export function construirVisor(contenedor, vol, rango) {
  const at = (i, j, k) => vol[i * G * G + j * G + k];
  const pos = { axial: G / 2, coronal: G / 2, sagital: G / 2 };
  const planos = {
    axial:   { titulo: "Axial",   f: (r, c) => at(r, c, pos.axial) },
    coronal: { titulo: "Coronal", f: (r, c) => at(c, pos.coronal, G - 1 - r) },
    sagital: { titulo: "Sagital", f: (r, c) => at(pos.sagital, c, G - 1 - r) },
  };
  contenedor.innerHTML = "";
  const tmp = document.createElement("canvas"); tmp.width = tmp.height = G;

  for (const [clave, p] of Object.entries(planos)) {
    const div = document.createElement("div");
    div.className = "plano";
    div.innerHTML = `
      <div class="tit"><b>${p.titulo}</b><span>corte <b class="idx">${pos[clave]}</b> / ${G - 1}</span></div>
      <canvas width="384" height="384"></canvas>
      <input type="range" min="0" max="${G - 1}" value="${pos[clave]}">`;
    contenedor.appendChild(div);
    const cv = div.querySelector("canvas");
    const dibujar = () => {
      pintar(tmp, vol, p.f, rango);
      const ctx = cv.getContext("2d");
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(tmp, 0, 0, cv.width, cv.height);
    };
    div.querySelector("input").addEventListener("input", (e) => {
      pos[clave] = +e.target.value;
      div.querySelector(".idx").textContent = pos[clave];
      dibujar();
    });
    dibujar();
  }
}