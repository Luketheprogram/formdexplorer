/* Local synthetic preview only:
 * .venv/bin/python scripts/preview_research.py
 * NODE_PATH=<existing-playwright-modules> node tests/research.browser.cjs
 * No external resources or SEC/ad-provider requests are allowed.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require('playwright');
const origin = 'http://127.0.0.1:8767';
const output = 'outputs/adsense-quality';

(async () => {
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless:true, executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const checks = [];
  const paths = ['/research/', '/research/filing-activity/', '/research/amendments/', '/research/coverage/',
    '/research/compare/?kind=state&left=CA&right=NY', '/research/compare/?kind=industry&left=biotechnology&right=other-technology',
    '/research/filing-changes/?cik=9000001', '/issuer/synthetic-preview-issuer-1-test-data-9000001/',
    '/state/CA/', '/industry/biotechnology/', '/learn/how-to-read-a-form-d/', '/about/', '/editorial/'];
  try {
    for (const width of [320, 390, 768, 1024, 1440]) {
      const context = await browser.newContext({viewport:{width, height:1000}});
      await context.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
      const page = await context.newPage();
      const errors=[];
      page.on('pageerror', e => errors.push(e.message));
      for (const path of paths) {
        const response = await page.goto(origin + path);
        assert.equal(response.status(), 200, path);
        assert.equal(await page.locator('h1').count(), 1, path);
        assert.ok(await page.locator('h1').isVisible(), path);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `${width}px overflow: ${path}`);
        assert.equal(await page.locator('[data-ad-slot]').count(), 0, `unexpected ads: ${path}`);
        assert.equal(await page.locator('link[rel=canonical]').count(), 1, path);
        assert.equal(await page.locator('input:not([type=hidden]), select, textarea').evaluateAll(elements => elements.every(el => el.labels && el.labels.length > 0)), true, `unlabeled form: ${path}`);
        checks.push({width, path, status:response.status(), documentOverflow:false, labeledControls:true});
        if ([390,1440].includes(width) && ['/research/', '/research/filing-activity/', '/research/filing-changes/?cik=9000001'].includes(path)) {
          const name = path.includes('filing-changes') ? 'changes' : path.includes('filing-activity') ? 'activity' : 'hub';
          await page.screenshot({path:`${output}/${name}-${width}.png`, fullPage:true});
        }
      }
      await page.goto(origin + '/research/compare/?kind=state&left=CA&right=NY');
      await page.selectOption('#left','TX');
      await page.getByRole('button', {name:'Compare activity'}).click();
      assert.equal(new URL(page.url()).searchParams.get('left'),'TX');
      assert.ok(await page.getByRole('heading', {name:'Texas', exact:true}).isVisible());
      await page.goto(origin + '/research/filing-changes/?cik=9000001');
      await page.getByRole('button', {name:'Compare disclosures'}).click();
      assert.ok(await page.getByRole('heading', {name:'Differences between reported disclosures'}).isVisible());
      await page.goto(origin + '/research/');
      await page.keyboard.press('Tab');
      assert.equal(await page.locator('.skip-link').evaluate(el => el === document.activeElement), true);
      await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'main-content');
      if (width < 1024) {
        await page.locator('#menu-toggle').click();
        assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'true');
        assert.ok(await page.locator('#mobile-menu a[href="/research/"]').isVisible());
      }
      assert.deepEqual(errors, []);
      await context.close();
    }
    fs.writeFileSync(`${output}/browser-checks.json`, JSON.stringify({fixture:'Synthetic local SQLite; all external requests blocked', assertions:'Response, heading, overflow, ad isolation, canonical, form labeling, category selection, filing comparison, skip link and mobile menu',checks},null,2));
    console.log(`PASS: ${checks.length} route/viewport checks and research interaction/keyboard checks at five widths.`);
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
