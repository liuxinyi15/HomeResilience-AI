const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require('playwright');
const {serve} = require('./static-site.cjs');

(async () => {
 const server = await serve();
 let browser;
 try {
  browser = await chromium.launch({executablePath:process.env.DECISION_CHROME || undefined});
  for (const width of [1440, 768, 390]) {
   const page = await browser.newPage({viewport:{width, height:900}, acceptDownloads:true});
   const faults = [];
   page.on('pageerror', error => faults.push(error.message));
   page.on('console', message => {
    if (['error','warning'].includes(message.type())) faults.push(message.text());
   });
   page.on('response', response => {
    if (response.status() >= 400) faults.push(response.status() + ' ' + response.url());
   });
   page.on('requestfailed', request => faults.push(request.url() + ' ' + request.failure()?.errorText));
   page.on('request', request => {
    if (!request.url().startsWith(server.url) && !/^(blob|data):/.test(request.url())) {
     faults.push('Request left Pages subpath: ' + request.url());
    }
   });

   const go = async stage => {
    const mobile = page.locator('#mobile-stage');
    if (await mobile.isVisible()) await mobile.selectOption(stage);
    else await page.locator('nav [data-page="' + stage + '"]').click();
    await page.waitForFunction(stage => state.page === stage, stage);
   };
   const layout = async () => {
    await page.locator('#app h1').waitFor();
    const size = await page.evaluate(() => ({
     outer:document.documentElement.scrollWidth, inner:innerWidth,
     headings:[...document.querySelectorAll('#app h1')].map(h => h.getBoundingClientRect()),
    }));
    assert.ok(size.outer <= size.inner + 1, 'Horizontal page overflow at ' + width + ' px: ' + page.url());
    assert.ok(size.headings.every(h => h.left >= -1 && h.right <= size.inner + 1));
   };
   const snap = async name => {
    if (width === 1440 && process.env.CAPTURE_SCREENSHOTS) {
     await page.evaluate(() => scrollTo(0,0));
     await page.screenshot({path:path.join(__dirname, '../screenshots', name + '.png'), animations:'disabled'});
    }
   };

   await page.goto(server.url);
   await page.locator('#journey-consent').check();
   await page.locator('[data-profile="family"]').click();
   await page.waitForFunction(() => state.page === 'property' && analysisCurrent());
   await layout();
   await snap('01-assessment');
   await go('planner');
   await layout();
   await snap('02-recommendations');
   await go('comparison');
   await page.waitForFunction(() => lab.result && !lab.loading);
   await layout();
   await snap('03-comparison');
   await page.locator('[data-journey-select="recommended_balance"]').click();
   await go('funding');
   await layout();
   const funding = page.locator('#journey-funding');
   await funding.locator('[name=contribution]').fill('2000');
   await funding.getByRole('button',{name:'Calculate and save pathway'}).click();
   await page.getByText(/£115 per month and £6,900 total/).waitFor();
   await snap('04-funding');

   for (const stage of ['quotes','action','verify','passport','maintenance','explorer','evidence']) {
    await go(stage);
    await layout();
   }
   const csv = page.getByRole('link', {name:'Subgroup CSV ↗'});
   const [download] = await Promise.all([page.waitForEvent('download'), csv.click()]);
   assert.match(download.suggestedFilename(), /\.csv$/);
   await go('explorer');
   await page.getByText('View publisher legend', {exact:true}).click();
   assert.equal(await page.locator('img[alt*="legend"]').evaluate(img => img.complete && img.naturalWidth > 0), true);

   // Every display/analysis pair is exercised at desktop; sample a non-default layer at other widths.
   const layers = width === 1440
    ? await page.locator('#flood-layer option').evaluateAll(options => options.map(o => o.value))
    : ['future_undefended_100'];
   for (const layer of layers) {
    await page.locator('#flood-layer').selectOption(layer);
    await page.waitForFunction(layer => analysisCurrent() && state.result.flood_scenario.layer === layer, layer);
    assert.ok(await page.evaluate(() => state.geo.features.length > 0), layer);
   }
   await go('passport');
   await layout();
   await snap('05-passport');
   await page.reload();
   await page.waitForFunction(() => state.page === 'passport' && analysisCurrent());
   assert.match(page.url(), /HomeResilience-AI\/#passport$/);
   assert.equal(await page.evaluate(() => home().id || Journey.session.home), 'family');
   assert.deepEqual(faults, []);
   await page.close();
   console.log('Pages subpath, evidence downloads, navigation, refresh, layout and network passed at ' + width + ' px.');
  }
 } finally {
  await browser?.close();
  server.close();
 }
})().catch(error => { console.error(error); process.exitCode = 1; });
