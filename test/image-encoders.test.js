// Checks the BMP, ICO, TIFF, and PDF writers used by image.html.
// Run: node test/image-encoders.test.js [folder for the sample files]
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const E = require("../image-encoders.js");

const root = path.join(__dirname, "..");
const outDir = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), "image-encoders-"));
fs.mkdirSync(outDir, { recursive: true });
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log("ok - " + name); };

// A 64 x 48 gradient with a see-through top-left corner.
function sample(w, h) {
  const px = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    px[i] = Math.round(255 * x / (w - 1)); px[i + 1] = Math.round(255 * y / (h - 1)); px[i + 2] = 128;
    px[i + 3] = x < 8 && y < 8 ? 0 : 255;
  }
  return px;
}

test("fitSize keeps the shape and only shrinks", () => {
  assert.deepEqual(E.fitSize(4000, 3000, {}), { width: 4000, height: 3000, scaled: false });
  assert.deepEqual(E.fitSize(4000, 3000, { maxWidth: 1000 }), { width: 1000, height: 750, scaled: true });
  assert.deepEqual(E.fitSize(4000, 3000, { maxWidth: 1000, maxHeight: 500 }), { width: 666, height: 500, scaled: true });
  assert.deepEqual(E.fitSize(800, 600, { maxWidth: 1920 }), { width: 800, height: 600, scaled: false });
  const big = E.fitSize(8064, 6048, { maxArea: 16777216 });
  assert.ok(big.width * big.height <= 16777216 && big.width / big.height - 8064 / 6048 < 0.01);
});

test("BMP: header, padded rows, bottom-up BGR, transparency on white", () => {
  const px = new Uint8ClampedArray([255, 0, 0, 255,  0, 255, 0, 255,  0, 0, 255, 0,
                                    10, 20, 30, 255,  0, 0, 0, 128,  1, 2, 3, 255]);
  const bmp = E.encodeBMP(px, 3, 2);
  const v = new DataView(bmp.buffer);
  assert.equal(String.fromCharCode(bmp[0], bmp[1]), "BM");
  assert.equal(bmp.length, 54 + 12 * 2);
  assert.equal(v.getUint32(2, true), bmp.length);
  assert.equal(v.getInt32(18, true), 3);
  assert.equal(v.getUint16(28, true), 24);
  // Bottom row of the picture comes first in the file.
  assert.deepEqual([...bmp.subarray(54, 63)], [30, 20, 10, 127, 127, 127, 3, 2, 1]);
  assert.deepEqual([...bmp.subarray(66, 75)], [0, 0, 255, 0, 255, 0, 255, 255, 255]);
  fs.writeFileSync(path.join(outDir, "sample.bmp"), E.encodeBMP(sample(64, 48), 64, 48));
});

test("ICO: one PNG inside, 256 written as 0", () => {
  const png = fs.readFileSync(path.join(root, "img/icon-180.png"));
  const ico = E.encodeICO(png, 180, 180);
  const v = new DataView(ico.buffer);
  assert.deepEqual([v.getUint16(0, true), v.getUint16(2, true), v.getUint16(4, true)], [0, 1, 1]);
  assert.equal(ico[6], 180); assert.equal(ico[7], 180);
  assert.equal(v.getUint32(14, true), png.length);
  assert.equal(v.getUint32(18, true), 22);
  assert.deepEqual(Buffer.from(ico.subarray(22)), png);
  const big = E.encodeICO(new Uint8Array(8), 256, 256);
  assert.equal(big[6], 0); assert.equal(big[7], 0);
  assert.throws(() => E.encodeICO(png, 300, 300));
  fs.writeFileSync(path.join(outDir, "sample.ico"), ico);
});

test("TIFF: tags read back, pixels stored as given", () => {
  const w = 64, h = 48, px = sample(w, h);
  const tif = E.encodeTIFF(px, w, h);
  const v = new DataView(tif.buffer);
  assert.equal(String.fromCharCode(tif[0], tif[1]), "II");
  assert.equal(v.getUint16(2, true), 42);
  const ifd = v.getUint32(4, true), n = v.getUint16(ifd, true);
  const tags = {};
  let last = 0;
  for (let k = 0; k < n; k++) {
    const e = ifd + 2 + k * 12, tag = v.getUint16(e, true), type = v.getUint16(e + 2, true);
    assert.ok(tag > last, "tags must be sorted"); last = tag;
    tags[tag] = type === 3 && v.getUint32(e + 4, true) === 1 ? v.getUint16(e + 8, true) : v.getUint32(e + 8, true);
  }
  assert.equal(tags[256], w); assert.equal(tags[257], h);
  assert.equal(tags[259], 1); assert.equal(tags[262], 2); assert.equal(tags[277], 4); assert.equal(tags[338], 2);
  assert.equal(tags[279], w * h * 4);
  assert.equal(tags[273] + tags[279], tif.length);
  for (let k = 0; k < 4; k++) assert.equal(v.getUint16(tags[258] + k * 2, true), 8);
  assert.deepEqual(Buffer.from(tif.subarray(tags[273])), Buffer.from(px));
  fs.writeFileSync(path.join(outDir, "sample.tiff"), tif);
});

test("PDF: JPEG embedded as is, xref offsets point at their objects", () => {
  const jpeg = new Uint8Array(fs.readFileSync(path.join(root, "img/daxton.jpg")));
  assert.deepEqual(E.jpegInfo(jpeg), { width: 1000, height: 1500, components: 3 });
  assert.throws(() => E.jpegInfo(new Uint8Array([1, 2, 3])));
  const pdf = E.encodePDF(jpeg);
  const text = Buffer.from(pdf).toString("latin1");
  assert.ok(text.startsWith("%PDF-1.4\n"));
  assert.ok(text.endsWith("%%EOF\n"));
  assert.ok(Buffer.from(pdf).includes(Buffer.from(jpeg)), "JPEG bytes are inside unchanged");
  assert.ok(text.includes("/Width 1000 /Height 1500 /ColorSpace /DeviceRGB"));
  assert.ok(text.includes("/MediaBox [0 0 528.00 792.00]"));
  const startxref = Number(text.match(/startxref\n(\d+)\n%%EOF\n$/)[1]);
  assert.equal(text.slice(startxref, startxref + 4), "xref");
  const rows = text.slice(startxref).split("\n").slice(3, 8);
  rows.forEach((row, k) => {
    assert.equal(row.length + 1, 20, "xref rows are 20 bytes");
    const off = Number(row.slice(0, 10));
    assert.equal(text.slice(off, off + 8), (k + 1) + " 0 obj\n");
  });
  fs.writeFileSync(path.join(outDir, "sample.pdf"), pdf);
});

console.log("\n" + passed + " passed. Sample files in " + outDir);
