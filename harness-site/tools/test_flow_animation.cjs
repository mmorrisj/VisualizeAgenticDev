// Optional browser regression check. Requires Playwright in the development
// environment, plus a running static server. No dependencies ship with the site.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
    await page.clock.install();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.argv[2] || 'http://127.0.0.1:8000/harness-site/sections/flows.html');
    await page.waitForSelector('[data-control=sandbox]');
    const svg = await page.locator('#trace-scene svg').elementHandle();
    const control = await page.locator('[data-control=sandbox]').elementHandle();
    await page.clock.runFor(280);
    const start = await page.locator('.flow-packet').first().getAttribute('transform');
    await page.clock.runFor(100);
    assert.notEqual(await page.locator('.flow-packet').first().getAttribute('transform'), start);
    await page.locator('#trace-play').click();
    const paused = await page.locator('.flow-packet').first().getAttribute('transform');
    await page.clock.runFor(150);
    assert.equal(await page.locator('.flow-packet').first().getAttribute('transform'), paused);
    const stageTop = await page.locator('#trace-scene').evaluate(n => n.getBoundingClientRect().top + scrollY);
    await page.locator('[data-control=sandbox]').click();
    assert(await page.evaluate(n => n === document.querySelector('#trace-scene svg'), svg));
    assert(await page.evaluate(n => n === document.querySelector('[data-control=sandbox]'), control));
    assert.equal(await page.locator('#trace-scene').evaluate(n => n.getBoundingClientRect().top + scrollY), stageTop);
    await page.locator('#flow-playhead').evaluate(n => { n.value = 50; n.dispatchEvent(new Event('input', { bubbles: true })); });
    const seeked = await page.locator('.flow-packet').evaluateAll(ns => ns.map(n => n.getAttribute('transform')));
    await page.clock.runFor(150);
    assert.deepEqual(await page.locator('.flow-packet').evaluateAll(ns => ns.map(n => n.getAttribute('transform'))), seeked);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.locator('[data-control=sandbox]').click();
    assert.equal(await page.locator('#flow-playhead').inputValue(), '100');
    assert.deepEqual(errors, []);
    console.log('PASS: continuous movement, pause, persistent SVG/controls, stable layout, scrub, reduced motion.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
