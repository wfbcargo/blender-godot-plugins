// Minimal PNG read/write for lookdev's image checks, with no dependency beyond Node.
//
//   import { readPNG, writePNG, crop } from "./png.mjs";
//   const img = readPNG("tile.png");   // {width, height, data: Uint8Array RGBA8}
//   writePNG("out.png", crop(img, x, y, w, h, scale));
//
// Reads 8-bit greyscale, grey+alpha, RGB, RGBA and palette PNGs, non-interlaced (what Godot's
// Image.save_png, Blender and most tools write). 16-bit and interlaced files are refused by name.

import fs from "node:fs";
import zlib from "node:zlib";

const SIG = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

export function decodePNG(buf) {
  if (!buf.subarray(0, 8).equals(SIG)) throw new Error("not a PNG file");
  let off = 8;
  let width = 0, height = 0, depth = 0, ctype = 0, interlace = 0;
  let palette = null, trns = null;
  const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString("latin1", off + 4, off + 8);
    const body = buf.subarray(off + 8, off + 8 + len);
    off += 12 + len;
    if (type === "IHDR") {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      depth = body[8];
      ctype = body[9];
      interlace = body[12];
    } else if (type === "PLTE") palette = body;
    else if (type === "tRNS") trns = body;
    else if (type === "IDAT") idat.push(body);
    else if (type === "IEND") break;
  }
  if (depth !== 8) throw new Error(`PNG bit depth ${depth} is not supported (8 only)`);
  if (interlace) throw new Error("interlaced PNG is not supported");
  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[ctype];
  if (!channels) throw new Error(`PNG colour type ${ctype} is not supported`);
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * channels;
  const px = new Uint8Array(stride * height);
  let prev = new Uint8Array(stride);
  for (let y = 0; y < height; y++) {
    const f = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const cur = px.subarray(y * stride, (y + 1) * stride);
    for (let i = 0; i < stride; i++) {
      const a = i >= channels ? cur[i - channels] : 0;
      const b = prev[i];
      const c = i >= channels ? prev[i - channels] : 0;
      let v = line[i];
      if (f === 1) v += a;
      else if (f === 2) v += b;
      else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) v += paeth(a, b, c);
      cur[i] = v & 255;
    }
    prev = cur;
  }
  const data = new Uint8Array(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    let r, g, b, a = 255;
    if (ctype === 0) r = g = b = px[i];
    else if (ctype === 4) { r = g = b = px[2 * i]; a = px[2 * i + 1]; }
    else if (ctype === 2) { r = px[3 * i]; g = px[3 * i + 1]; b = px[3 * i + 2]; }
    else if (ctype === 6) { r = px[4 * i]; g = px[4 * i + 1]; b = px[4 * i + 2]; a = px[4 * i + 3]; }
    else {
      const k = px[i];
      r = palette[3 * k]; g = palette[3 * k + 1]; b = palette[3 * k + 2];
      if (trns && k < trns.length) a = trns[k];
    }
    data.set([r, g, b, a], 4 * i);
  }
  return { width, height, data };
}

export function readPNG(file) {
  return decodePNG(fs.readFileSync(file));
}

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC[(c ^ b) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, body) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(body.length);
  const tb = Buffer.concat([Buffer.from(type, "latin1"), body]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(tb));
  return Buffer.concat([len, tb, crc]);
}

export function encodePNG(img) {
  const { width, height, data } = img;
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0;
    Buffer.from(data.buffer, data.byteOffset + y * width * 4, width * 4).copy(raw, y * (width * 4 + 1) + 1);
  }
  return Buffer.concat([SIG, chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

export function writePNG(file, img) {
  fs.writeFileSync(file, encodePNG(img));
}

// A rectangle of `img`, clamped to it, enlarged `scale` times by pixel replication (so a crop shows the
// pixels as they are, not resampled).
export function crop(img, x, y, w, h, scale = 1) {
  x = Math.max(0, Math.min(img.width - 1, Math.round(x)));
  y = Math.max(0, Math.min(img.height - 1, Math.round(y)));
  w = Math.max(1, Math.min(img.width - x, Math.round(w)));
  h = Math.max(1, Math.min(img.height - y, Math.round(h)));
  const s = Math.max(1, Math.round(scale));
  const out = new Uint8Array(w * s * h * s * 4);
  for (let j = 0; j < h * s; j++) {
    for (let i = 0; i < w * s; i++) {
      const src = 4 * ((y + Math.floor(j / s)) * img.width + x + Math.floor(i / s));
      out.set(img.data.subarray(src, src + 4), 4 * (j * w * s + i));
    }
  }
  return { width: w * s, height: h * s, data: out };
}

// Images side by side (tops aligned) on a grey ground, `gap` pixels apart.
export function beside(images, gap = 8) {
  const width = images.reduce((s, im) => s + im.width, 0) + gap * (images.length - 1);
  const height = Math.max(...images.map((im) => im.height));
  const data = new Uint8Array(width * height * 4).fill(128);
  let x0 = 0;
  for (const im of images) {
    for (let y = 0; y < im.height; y++) {
      data.set(im.data.subarray(y * im.width * 4, (y + 1) * im.width * 4), 4 * (y * width + x0));
    }
    x0 += im.width + gap;
  }
  return { width, height, data };
}

// Nearest-neighbour resize to a given width (keeps aspect), for pairing tiles rendered at different sizes.
export function resizeTo(img, width) {
  const s = width / img.width;
  const height = Math.max(1, Math.round(img.height * s));
  const out = new Uint8Array(width * height * 4);
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      const src = 4 * (Math.min(img.height - 1, Math.floor(j / s)) * img.width + Math.min(img.width - 1, Math.floor(i / s)));
      out.set(img.data.subarray(src, src + 4), 4 * (j * width + i));
    }
  }
  return { width, height, data: out };
}
