/** Authenticate local font bytes and the browser's actual glyph provider. */
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';

export async function observeFonts(page) {
  const loaded = await page.evaluate(async () => {
    await Promise.all([document.fonts.load('400 16px Inter'), document.fonts.load('600 32px Inter')]);
    await document.fonts.ready;
    return { checks: [document.fonts.check('400 16px Inter'), document.fonts.check('600 32px Inter')],
      faces: [...document.fonts].map(face => ({ family: face.family, weight: face.weight, status: face.status })) };
  });
  if (!loaded.checks.every(Boolean) || !loaded.faces.filter(face => face.family === 'Inter').every(face => face.status === 'loaded')) {
    throw new Error('Local Inter font did not load');
  }
  const assets = [];
  for (const filename of ['inter-regular.woff2', 'inter-semibold.woff2']) {
    const response = await page.request.get(new URL(filename, page.url()).href);
    const bytes = await response.body();
    const local = await fs.readFile(new URL(filename, import.meta.url));
    if (response.status() !== 200 || !bytes.equals(local)) throw new Error(`Served font differs from producer snapshot: ${filename}`);
    assets.push({ url: response.url(), status: response.status(), bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
  }
  const session = await page.context().newCDPSession(page);
  try {
    await session.send('DOM.enable');
    await session.send('CSS.enable');
    const { root } = await session.send('DOM.getDocument');
    const { nodeIds } = await session.send('DOM.querySelectorAll', { nodeId: root.nodeId, selector: '[data-semantic]' });
    const rendered = [];
    for (const nodeId of nodeIds) {
      const { attributes } = await session.send('DOM.getAttributes', { nodeId });
      const semanticId = attributes[attributes.indexOf('data-semantic') + 1];
      const { fonts } = await session.send('CSS.getPlatformFontsForNode', { nodeId });
      if (fonts.some(font => font.glyphCount > 0 && (!font.isCustomFont || !font.familyName.startsWith('Inter')))) {
        throw new Error(`Rendered glyphs used a fallback font: ${semanticId}`);
      }
      rendered.push({ semantic_id: semanticId, fonts });
    }
    if (!rendered.some(row => row.fonts.some(font => font.glyphCount > 0))) throw new Error('No rendered font glyphs observed');
    return { ...loaded, assets, rendered };
  } finally {
    await session.detach();
  }
}
