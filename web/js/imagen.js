export const G = 128;

export async function leerNpy(file) {
  const buf = await file.arrayBuffer();
  const u8 = new Uint8Array(buf);
  if (u8[0] !== 0x93 || String.fromCharCode(...u8.slice(1, 6)) !== "NUMPY") throw new Error("NPY inválido");
  const v1 = u8[6] === 1;
  const hlen = v1 ? new DataView(buf).getUint16(8, true) : new DataView(buf).getUint32(8, true);
  const ini = (v1 ? 10 : 12);
  const cab = new TextDecoder().decode(u8.slice(ini, ini + hlen));
  if (!/'descr':\s*'<f4'/.test(cab)) throw new Error("se espera float32");
  if (!/\(128,\s*128\)/.test(cab)) throw new Error("Expected a 128x128 image");
  if (/'fortran_order':\s*True/.test(cab)) throw new Error("Expected a C-order array");
  return new Float32Array(buf.slice(ini + hlen, ini + hlen + G * G * 4));
}

export function leerPng(file) {
  return new Promise((ok, mal) => {
    const img = new Image();
    img.onload = () => {
      if (img.width !== G || img.height !== G) return mal(new Error("Expected a 128x128 image"));
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
export function pintar(canvas, datos, valor, rango) {
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
