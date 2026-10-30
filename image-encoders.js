// Small file writers for the Picture Converter (image.html). The browser's canvas can make
// JPG, PNG, WebP, and sometimes AVIF. These cover the rest: BMP, ICO, TIFF, and PDF.
// Plain functions on byte arrays, so they also run in Node for the tests.
(function (root) {
  "use strict";

  // Fit width x height inside the limits without stretching. Blank limits mean no limit.
  function fitSize(width, height, opts) {
    const o = opts || {};
    let s = 1;
    if (o.maxWidth > 0 && width * s > o.maxWidth) s = o.maxWidth / width;
    if (o.maxHeight > 0 && height * s > o.maxHeight) s = o.maxHeight / height;
    if (o.maxArea > 0 && width * height * s * s > o.maxArea) s = Math.sqrt(o.maxArea / (width * height));
    if (s >= 1) return { width, height, scaled: false };
    return { width: Math.max(1, Math.floor(width * s)), height: Math.max(1, Math.floor(height * s)), scaled: true };
  }

  // 24-bit Windows bitmap. BMP has no reliable transparency, so see-through pixels go on white.
  function encodeBMP(rgba, width, height) {
    const rowSize = Math.ceil(width * 3 / 4) * 4;
    const dataSize = rowSize * height;
    const out = new Uint8Array(54 + dataSize);
    const v = new DataView(out.buffer);
    out[0] = 0x42; out[1] = 0x4d;                   // "BM"
    v.setUint32(2, out.length, true);
    v.setUint32(10, 54, true);                       // pixel data offset
    v.setUint32(14, 40, true);                       // BITMAPINFOHEADER
    v.setInt32(18, width, true);
    v.setInt32(22, height, true);                    // positive: rows run bottom to top
    v.setUint16(26, 1, true);                        // planes
    v.setUint16(28, 24, true);                       // bits per pixel
    v.setUint32(34, dataSize, true);
    v.setInt32(38, 3780, true);                      // 96 dpi
    v.setInt32(42, 3780, true);
    for (let y = 0; y < height; y++) {
      let o = 54 + (height - 1 - y) * rowSize;
      let i = y * width * 4;
      for (let x = 0; x < width; x++, i += 4, o += 3) {
        const a = rgba[i + 3], w = 255 - a;
        out[o]     = Math.round((rgba[i + 2] * a + 255 * w) / 255);
        out[o + 1] = Math.round((rgba[i + 1] * a + 255 * w) / 255);
        out[o + 2] = Math.round((rgba[i] * a + 255 * w) / 255);
      }
    }
    return out;
  }

  // Icon file holding one PNG. Icons are at most 256 x 256; a 0 in the header means 256.
  function encodeICO(png, width, height) {
    if (width > 256 || height > 256) throw new Error("ICO images can be at most 256 x 256.");
    const out = new Uint8Array(22 + png.length);
    const v = new DataView(out.buffer);
    v.setUint16(2, 1, true);                         // type: icon
    v.setUint16(4, 1, true);                         // one image
    out[6] = width === 256 ? 0 : width;
    out[7] = height === 256 ? 0 : height;
    v.setUint16(10, 1, true);                        // color planes
    v.setUint16(12, 32, true);                       // bits per pixel
    v.setUint32(14, png.length, true);
    v.setUint32(18, 22, true);                       // image offset
    out.set(png, 22);
    return out;
  }

  // Uncompressed TIFF, 8-bit RGBA in one strip, little-endian. Opens in Preview, Photoshop, and print tools.
  function encodeTIFF(rgba, width, height) {
    const entries = [
      [256, 4, 1, width],                            // ImageWidth
      [257, 4, 1, height],                           // ImageLength
      [258, 3, 4, "bps"],                            // BitsPerSample 8,8,8,8
      [259, 3, 1, 1],                                // Compression: none
      [262, 3, 1, 2],                                // Photometric: RGB
      [273, 4, 1, "pixels"],                         // StripOffsets
      [277, 3, 1, 4],                                // SamplesPerPixel
      [278, 4, 1, height],                           // RowsPerStrip
      [279, 4, 1, width * height * 4],               // StripByteCounts
      [282, 5, 1, "xres"],                           // XResolution
      [283, 5, 1, "yres"],                           // YResolution
      [284, 3, 1, 1],                                // PlanarConfiguration: chunky
      [296, 3, 1, 2],                                // ResolutionUnit: inch
      [338, 3, 1, 2]                                 // ExtraSamples: unassociated alpha
    ];
    const ifd = 8, extra = ifd + 2 + entries.length * 12 + 4;
    const at = { bps: extra, xres: extra + 8, yres: extra + 16, pixels: extra + 24 };
    const out = new Uint8Array(at.pixels + width * height * 4);
    const v = new DataView(out.buffer);
    out[0] = 0x49; out[1] = 0x49;                   // "II"
    v.setUint16(2, 42, true);
    v.setUint32(4, ifd, true);
    v.setUint16(ifd, entries.length, true);
    entries.forEach(([tag, type, count, value], n) => {
      const e = ifd + 2 + n * 12;
      v.setUint16(e, tag, true);
      v.setUint16(e + 2, type, true);
      v.setUint32(e + 4, count, true);
      const val = typeof value === "string" ? at[value] : value;
      if (type === 3 && count === 1) v.setUint16(e + 8, val, true);
      else v.setUint32(e + 8, val, true);
    });
    v.setUint32(extra - 4, 0, true);                 // no next IFD
    for (let k = 0; k < 4; k++) v.setUint16(at.bps + k * 2, 8, true);
    v.setUint32(at.xres, 72, true); v.setUint32(at.xres + 4, 1, true);
    v.setUint32(at.yres, 72, true); v.setUint32(at.yres + 4, 1, true);
    out.set(rgba.subarray ? rgba.subarray(0, width * height * 4) : rgba, at.pixels);
    return out;
  }

  // Size and color channels from a JPEG's frame header.
  function jpegInfo(jpeg) {
    if (jpeg[0] !== 0xff || jpeg[1] !== 0xd8) throw new Error("Not a JPEG.");
    let i = 2;
    while (i + 9 < jpeg.length) {
      if (jpeg[i] !== 0xff) { i++; continue; }
      const m = jpeg[i + 1];
      if (m === 0xff) { i++; continue; }
      if (m === 0xd8 || m === 0x01 || (m >= 0xd0 && m <= 0xd7)) { i += 2; continue; }
      const len = (jpeg[i + 2] << 8) | jpeg[i + 3];
      if (m >= 0xc0 && m <= 0xcf && m !== 0xc4 && m !== 0xc8 && m !== 0xcc) {
        return { height: (jpeg[i + 5] << 8) | jpeg[i + 6], width: (jpeg[i + 7] << 8) | jpeg[i + 8], components: jpeg[i + 9] };
      }
      i += 2 + len;
    }
    throw new Error("JPEG has no frame header.");
  }

  // One-page PDF that shows a JPEG. The page fits the picture: 96 dpi, long side at most 11 inches.
  function encodePDF(jpeg) {
    const info = jpegInfo(jpeg);
    const scale = Math.min(0.75, 792 / Math.max(info.width, info.height));
    const pw = (info.width * scale).toFixed(2), ph = (info.height * scale).toFixed(2);
    const cs = info.components === 1 ? "/DeviceGray" : info.components === 4 ? "/DeviceCMYK" : "/DeviceRGB";
    const draw = "q " + pw + " 0 0 " + ph + " 0 0 cm /Im0 Do Q\n";
    const enc = s => { const b = new Uint8Array(s.length); for (let k = 0; k < s.length; k++) b[k] = s.charCodeAt(k) & 0xff; return b; };
    const parts = [], offsets = [];
    let size = 0;
    const put = b => { parts.push(b); size += b.length; };
    const obj = (n, text) => { offsets[n] = size; put(enc(n + " 0 obj\n" + text + "\nendobj\n")); };
    put(enc("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"));
    obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
    obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
    obj(3, "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + pw + " " + ph + "] /Resources << /XObject << /Im0 4 0 R >> /ProcSet [/PDF /ImageB /ImageC] >> /Contents 5 0 R >>");
    offsets[4] = size;
    put(enc("4 0 obj\n<< /Type /XObject /Subtype /Image /Width " + info.width + " /Height " + info.height +
      " /ColorSpace " + cs + " /BitsPerComponent 8 /Filter /DCTDecode /Length " + jpeg.length + " >>\nstream\n"));
    put(jpeg);
    put(enc("\nendstream\nendobj\n"));
    obj(5, "<< /Length " + draw.length + " >>\nstream\n" + draw + "endstream");
    const xref = size;
    let tail = "xref\n0 6\n0000000000 65535 f \n";
    for (let n = 1; n <= 5; n++) tail += String(offsets[n]).padStart(10, "0") + " 00000 n \n";
    tail += "trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + xref + "\n%%EOF\n";
    put(enc(tail));
    const out = new Uint8Array(size);
    let o = 0;
    for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  }

  const api = { fitSize, encodeBMP, encodeICO, encodeTIFF, jpegInfo, encodePDF };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ImageEncoders = api;
})(typeof self !== "undefined" ? self : this);
