// RadVol 3D · EN-2 · Interfaz del servicio local de reconstrucción
const G = 64;
const ANGULOS = [
  { ang: 0,   nombre: "Proyección AP" },
  { ang: 45,  nombre: "Oblicua 45°" },
  { ang: 90,  nombre: "Lateral" },
  { ang: 135, nombre: "Oblicua 135°" },
];
const archivos = {};          // ang -> File
const $ = (id) => document.getElementById(id);

// ---------- 1. Estado del servicio ----------
async function comprobarServicio() {
  try {
    const s = await (await fetch("/salud")).json();
    $("dot").className = "dot on";
    $("estado-servicio").textContent =
      "Servicio en línea · " + (s.metodo === "unet_refinamiento" ? "U-Net EN-1" : "retroproyección simple");
  } catch {
    $("dot").className = "dot off";
    $("estado-servicio").textContent = "Servicio no disponible";
  }
}

// ---------- 2. Ranuras de proyecciones ----------
function crearRanuras() {
  const cont = $("proys");
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
    cont.appendChild(slot);
  });
}

async function asignar(ang, file) {
  const slot = $("slot-" + ang);
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
  actualizarBoton();
}

// Varios archivos a la vez: se asignan por el sufijo _000/_045/_090/_135 o por orden
$("multi").addEventListener("change", (e) => {
  const lista = [...e.target.files].sort((a, b) => a.name.localeCompare(b.name));
  lista.slice(0, 4).forEach((f, i) => {
    const m = f.name.match(/_(\d{1,3})\.(png|npy)$/i);
    const ang = m && ANGULOS.some((a) => a.ang === +m[1]) ? +m[1] : ANGULOS[i].ang;
    asignar(ang, f);
  });
  e.target.value = "";
});

function actualizarBoton() {
  const n = Object.keys(archivos).length;
  $("btn-reconstruir").disabled = n !== 4;
  $("msg").className = "msg";
  $("msg").textContent = n === 4 ? "Listo: 4 proyecciones asignadas (0°, 45°, 90°, 135°)."
                                 : `Faltan ${4 - n} proyección(es).`;
}

$("btn-limpiar").addEventListener("click", () => {
  Object.keys(archivos).forEach((k) => delete archivos[k]);
  $("proys").innerHTML = "";
  crearRanuras();
  actualizarBoton();
  $("resultado").classList.remove("on");
});

// ---------- 3. Lectores de imagen para la vista previa ----------
async function leerNpy(file) {
  const buf = await file.arrayBuffer();
  const u8 = new Uint8Array(buf);
  if (u8[0] !== 0x93 || String.fromCharCode(...u8.slice(1, 6)) !== "NUMPY") throw new Error("NPY inválido");
  const v1 = u8[6] === 1;
  const hlen = v1 ? new DataView(buf).getUint16(8, true) : new DataView(buf).getUint32(8, true);
  const ini = (v1 ? 10 : 12);
  const cab = new TextDecoder().decode(u8.slice(ini, ini + hlen));
  if (!/'descr':\s*'<f4'/.test(cab)) throw new Error("se espera float32");
  if (!/\(64,\s*64\)/.test(cab)) throw new Error("tamaño distinto de 64×64");
  return new Float32Array(buf.slice(ini + hlen, ini + hlen + G * G * 4));
}

function leerPng(file) {
  return new Promise((ok, mal) => {
    const img = new Image();
    img.onload = () => {
      if (img.width !== G || img.height !== G) return mal(new Error("tamaño distinto de 64×64"));
      const c = document.createElement("canvas"); c.width = c.height = G;
      const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0);
      const d = ctx.getImageData(0, 0, G, G).data;
      const out = new Float32Array(G * G);
      for (let i = 0; i < G * G; i++) out[i] = d[i * 4];
      ok(out);
    };
    img.onerror = () => mal(new Error("no se pudo leer"));
    img.src = URL.createObjectURL(file);
  });
}

// Dibuja una imagen G×G en un canvas; valor(r, c) da el píxel de la fila r, columna c
function pintar(canvas, datos, valor, rango) {
  let [mn, mx] = rango || [Infinity, -Infinity];
  if (!rango) for (const v of datos) { if (v < mn) mn = v; if (v > mx) mx = v; }
  const esc = mx > mn ? 255 / (mx - mn) : 0;
  const ctx = canvas.getContext("2d");
  const im = ctx.createImageData(G, G);
  for (let r = 0; r < G; r++) for (let c = 0; c < G; c++) {
    const g = (valor(r, c) - mn) * esc, i = (r * G + c) * 4;
    im.data[i] = im.data[i + 1] = im.data[i + 2] = g; im.data[i + 3] = 255;
  }
  ctx.putImageData(im, 0, 0);
}

// ---------- 4. Llamada al servicio ----------
$("btn-reconstruir").addEventListener("click", async () => {
  const btn = $("btn-reconstruir");
  const fd = new FormData();
  ANGULOS.forEach(({ ang }) => fd.append("proyeccion_" + ang, archivos[ang]));
  const id = $("id-estudio").value.trim();
  if (id) fd.append("id_estudio", id);
  fd.append("organo", "pulmon");

  btn.disabled = true;
  btn.innerHTML = '<i class="spin"></i>Reconstruyendo…';
  const t0 = performance.now();
  try {
    const resp = await fetch("/reconstruir", { method: "POST", body: fd });
    const j = await resp.json();
    if (!resp.ok) throw new Error((j.archivo_rechazado ? j.archivo_rechazado + ": " : "") + j.detalle);
    mostrarResultado(j, (performance.now() - t0) / 1000);
  } catch (e) {
    $("msg").className = "msg err";
    $("msg").textContent = "Rechazado · " + e.message;
  } finally {
    btn.innerHTML = "Reconstruir volumen";
    actualizarBoton();
  }
});

// ---------- 5. Resultado y visor de cortes ----------
function mostrarResultado(j, total) {
  const bin = atob(j.volumen.datos_base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const vol = new Float32Array(bytes.buffer);

  $("r-estado").textContent = j.estado;
  $("r-id").textContent = j.id_estudio;
  $("r-metodo").textContent = j.metodo === "unet_refinamiento" ? "U-Net (EN-1)" : "Retroproyección";
  $("r-forma").textContent = j.volumen.forma.join(" × ");
  $("r-tiempo").textContent = j.tiempo_s.toFixed(2) + " s";
  $("r-total").textContent = total.toFixed(2) + " s";
  $("r-descarga").href = j.descarga;
  const vista = { ...j, volumen: { ...j.volumen, datos_base64: j.volumen.datos_base64.slice(0, 60) + "… (" + j.volumen.datos_base64.length.toLocaleString() + " caracteres)" } };
  $("r-json").textContent = JSON.stringify(vista, null, 2);

  construirVisor(vol, [j.estadisticas.min, j.estadisticas.max]);
  $("resultado").classList.add("on");
  $("resultado").scrollIntoView({ behavior: "smooth" });
}

function construirVisor(vol, rango) {
  const at = (i, j, k) => vol[i * G * G + j * G + k];
  const pos = { axial: G / 2, coronal: G / 2, sagital: G / 2 };
  const planos = {
    axial:   { titulo: "Axial",   f: (r, c) => at(r, c, pos.axial) },
    coronal: { titulo: "Coronal", f: (r, c) => at(c, pos.coronal, G - 1 - r) },
    sagital: { titulo: "Sagital", f: (r, c) => at(pos.sagital, c, G - 1 - r) },
  };
  const visor = $("visor");
  visor.innerHTML = "";
  const tmp = document.createElement("canvas"); tmp.width = tmp.height = G;

  for (const [clave, p] of Object.entries(planos)) {
    const div = document.createElement("div");
    div.className = "plano";
    div.innerHTML = `
      <div class="tit"><b>${p.titulo}</b><span>corte <b class="idx">${pos[clave]}</b> / ${G - 1}</span></div>
      <canvas width="384" height="384"></canvas>
      <input type="range" min="0" max="${G - 1}" value="${pos[clave]}">`;
    visor.appendChild(div);
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

// ---------- inicio ----------
crearRanuras();
comprobarServicio();