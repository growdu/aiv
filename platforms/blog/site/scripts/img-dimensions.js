'use strict';

// Add intrinsic width/height to the images of a post.
//
// Why: the article body is a wall of <img> tags whose size is only known
// once the bitmap has been downloaded.  The browser therefore reserves
// zero space for them, and the page jumps while the reader scrolls
// (cumulative layout shift).  Declaring width/height lets the browser
// reserve the right box from the attributes alone -- it derives the
// aspect ratio and scales the box with `max-width:100%; height:auto`.
//
// Only *local* images are handled: an image hosted somewhere else would
// have to be downloaded at build time to be measured, and a build that
// depends on a third-party host is a build that fails when that host is
// down.  External images keep whatever attributes they already have.
//
// No dependencies on purpose: the dimensions are read straight out of the
// file headers (PNG / JPEG / GIF / WebP / SVG), so the build stays as
// cheap as it was before.

const fs = require('fs');
const path = require('path');

// --- header parsers ------------------------------------------------------

function pngSize(buf) {
  // 8 byte signature, then an IHDR chunk whose payload starts at 16:
  // 4 bytes width, 4 bytes height, both big endian.
  if (buf.length < 24) return null;
  if (buf.readUInt32BE(0) !== 0x89504e47) return null;
  if (buf.toString('ascii', 12, 16) !== 'IHDR') return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function jpegSize(buf) {
  // Walk the marker segments until a start-of-frame is found.
  if (buf.length < 4) return null;
  if (buf[0] !== 0xff || buf[1] !== 0xd8) return null;
  let offset = 2;
  while (offset + 9 < buf.length) {
    if (buf[offset] !== 0xff) return null;
    const marker = buf[offset + 1];
    // Standalone markers carry no payload.
    if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) {
      offset += 2;
      continue;
    }
    const length = buf.readUInt16BE(offset + 2);
    // SOF0..SOF15, minus DHT (c4), JPG (c8) and DAC (cc).
    const isSOF = marker >= 0xc0 && marker <= 0xcf
      && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
    if (isSOF) {
      return {
        height: buf.readUInt16BE(offset + 5),
        width: buf.readUInt16BE(offset + 7),
      };
    }
    if (length < 2) return null;
    offset += 2 + length;
  }
  return null;
}

function gifSize(buf) {
  if (buf.length < 10) return null;
  const magic = buf.toString('ascii', 0, 6);
  if (magic !== 'GIF87a' && magic !== 'GIF89a') return null;
  return { width: buf.readUInt16LE(6), height: buf.readUInt16LE(8) };
}

function webpSize(buf) {
  if (buf.length < 30) return null;
  if (buf.toString('ascii', 0, 4) !== 'RIFF') return null;
  if (buf.toString('ascii', 8, 12) !== 'WEBP') return null;
  const chunk = buf.toString('ascii', 12, 16);
  if (chunk === 'VP8 ') {
    // Key frame: 3 byte tag, 3 byte sync code (9d 01 2a), then the size.
    if (buf[23] !== 0x9d || buf[24] !== 0x01 || buf[25] !== 0x2a) return null;
    return {
      width: buf.readUInt16LE(26) & 0x3fff,
      height: buf.readUInt16LE(28) & 0x3fff,
    };
  }
  if (chunk === 'VP8L') {
    // Lossless: 1 byte signature (2f) then 14 bits width-1, 14 bits height-1.
    if (buf[20] !== 0x2f) return null;
    const bits = buf.readUInt32LE(21);
    return {
      width: (bits & 0x3fff) + 1,
      height: ((bits >> 14) & 0x3fff) + 1,
    };
  }
  if (chunk === 'VP8X') {
    // Extended: 4 bytes flags, then the canvas size minus one.
    return {
      width: (buf[24] | (buf[25] << 8) | (buf[26] << 16)) + 1,
      height: (buf[27] | (buf[28] << 8) | (buf[29] << 16)) + 1,
    };
  }
  return null;
}

function svgSize(buf) {
  // Only explicit pixel width/height attributes are trusted; a viewBox
  // alone does not say how large the image should be drawn.
  const head = buf.toString('utf8', 0, Math.min(buf.length, 2048));
  const width = /\bwidth\s*=\s*["']\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*["']/i.exec(head);
  const height = /\bheight\s*=\s*["']\s*(\d+(?:\.\d+)?)\s*(?:px)?\s*["']/i.exec(head);
  if (!width || !height) return null;
  const w = Math.round(parseFloat(width[1]));
  const h = Math.round(parseFloat(height[1]));
  if (!w || !h) return null;
  return { width: w, height: h };
}

function imageSize(file) {
  let buf;
  try {
    buf = fs.readFileSync(file);
  } catch (e) {
    return null;
  }
  // Sniff the content, not the extension: the content tree does contain
  // files named .png that are really JPEG (and vice versa).  Dispatching
  // on the extension would silently skip those.
  let size = null;
  if (buf.length >= 8 && buf.readUInt32BE(0) === 0x89504e47) {
    size = pngSize(buf);
  } else if (buf.length >= 3 && buf[0] === 0xff && buf[1] === 0xd8) {
    size = jpegSize(buf);
  } else if (buf.length >= 6 && /^GIF8[79]a$/.test(buf.toString('ascii', 0, 6))) {
    size = gifSize(buf);
  } else if (buf.length >= 12
             && buf.toString('ascii', 0, 4) === 'RIFF'
             && buf.toString('ascii', 8, 12) === 'WEBP') {
    size = webpSize(buf);
  } else if (/\.svg$/i.test(file)) {
    size = svgSize(buf);
  }
  if (!size) return null;
  // A zero or absurd size means the header was not what we expected.
  if (!size.width || !size.height) return null;
  if (size.width > 100000 || size.height > 100000) return null;
  return size;
}

// --- the filter -----------------------------------------------------------

function registerFilter() {
  hexo.extend.filter.register('after_post_render', function (data) {
    if (!data.content || data.content.indexOf('<img') === -1) return data;

    const root = hexo.config.root || '/';
    const searchRoots = [hexo.source_dir, path.join(hexo.theme_dir, 'source')];
    const cache = new Map();

    data.content = data.content.replace(/<img\b[^>]*>/gi, function (tag) {
      if (/\bwidth\s*=/i.test(tag) || /\bheight\s*=/i.test(tag)) return tag;

      const m = /\bsrc\s*=\s*["']([^"']+)["']/i.exec(tag);
      if (!m) return tag;
      let src = m[1];

      // Remote images are left alone on purpose.
      if (/^(?:https?:|data:|blob:|mailto:|\/\/)/i.test(src)) return tag;

      src = src.split('#')[0].split('?')[0];
      try {
        src = decodeURIComponent(src);
      } catch (e) { /* keep the raw value */ }
      // A path may carry Windows separators (the content sync writes them
      // that way on Windows); they mean the same thing as a slash here.
      src = src.replace(/\\/g, '/');

      if (root !== '/' && src.indexOf(root) === 0) src = src.slice(root.length);
      src = src.replace(/^\/+/, '');
      if (!src) return tag;

      let file = null;
      for (const base of searchRoots) {
        const candidate = path.join(base, src);
        try {
          if (fs.statSync(candidate).isFile()) { file = candidate; break; }
        } catch (e) { /* not here, try the next root */ }
      }
      if (!file) return tag;

      let size = cache.get(file);
      if (size === undefined) {
        size = imageSize(file);
        cache.set(file, size);
      }
      if (!size) return tag;

      const cut = tag.lastIndexOf('>');
      if (cut === -1) return tag;
      return tag.slice(0, cut)
        + ' width="' + size.width + '" height="' + size.height + '"'
        + tag.slice(cut);
    });

    return data;
  });
}

if (typeof hexo !== 'undefined' && hexo && hexo.extend) {
  registerFilter();
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    registerFilter: registerFilter,
    imageSize: imageSize,
    pngSize: pngSize,
    jpegSize: jpegSize,
    gifSize: gifSize,
    webpSize: webpSize,
    svgSize: svgSize,
  };
}
