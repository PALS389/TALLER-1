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
    const fig = document.createElement("figure");
    fig.className = "plano";
    fig.innerHTML = `
      <figcaption class="tit"><b>${p.titulo}</b><span>corte <b class="idx">${pos[clave]}</b> / ${G - 1}</span></figcaption>
      <canvas width="384" height="384" role="img"></canvas>
      <input type="range" min="0" max="${G - 1}" value="${pos[clave]}" aria-label="Corte ${p.titulo.toLowerCase()}">`;
    contenedor.appendChild(fig);
    const cv = fig.querySelector("canvas");
    const deslizador = fig.querySelector("input");
    const dibujar = () => {
      pintar(tmp, vol, p.f, rango);
      const ctx = cv.getContext("2d");
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(tmp, 0, 0, cv.width, cv.height);
      const texto = `Corte ${p.titulo.toLowerCase()} ${pos[clave]} de ${G - 1}`;
      cv.setAttribute("aria-label", texto + " del volumen reconstruido");
      deslizador.setAttribute("aria-valuetext", texto);
    };
    deslizador.addEventListener("input", (e) => {
      pos[clave] = +e.target.value;
      fig.querySelector(".idx").textContent = pos[clave];
      dibujar();
    });
    dibujar();
  }
}