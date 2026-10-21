/* Run from the repo after local migrate/seed_articles and building Tailwind:
 * npm install --prefix /tmp/formd-ad-browser @playwright/test
 * NODE_PATH=/tmp/formd-ad-browser/node_modules node --test tests/advertising.browser.cjs
 * Uses installed Chrome (or CHROME_PATH); every external request is intercepted.
 */
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {chromium} = require('@playwright/test');
let browser, server;
const origin = 'http://127.0.0.1:8765';
const guide = '/learn/what-is-form-d/';
const key = 'formd-advertising-v1';
const cmpStub = `
  window.__tcfapi = (command, version, cb) => { window.testTcf = cb; cb({cmpStatus:'loaded', gdprApplies:true, eventStatus:'tcloaded', purpose:{consents:{1:true}}, vendor:{consents:{755:true}}}, true); };
  window.__gpp = (command, cb) => { window.testGpp = cb; };
  window.googlefc.usstatesoptout = {getInitialUsStatesOptOutStatus: () => window.testUsStatus || 1};
  window.googlefc.showRevocationMessage = () => { window.testRevoked = true; };
  window.testCmpCallbacks = window.googlefc.callbackQueue;
  window.googlefc.callbackQueue = {push: item => Object.values(item).forEach(fn => fn())};
  window.testCmpCallbacks.forEach(item => window.googlefc.callbackQueue.push(item));
`;

before(async () => {
  server = spawn('.venv/bin/python', ['manage.py', 'runserver', '127.0.0.1:8765', '--noreload'], {
    env: {...process.env, DEBUG:'True', ALLOWED_HOSTS:'127.0.0.1', DATABASE_URL:'',
      ADSENSE_ENABLED:'True', ADSENSE_CMP_READY:'True',
      ADSENSE_CLIENT_ID:'ca-pub-1234567890123456', ADSENSE_ARTICLE_SLOT_ID:'1234567890', ADSENSE_GUIDES_SLOT_ID:'0987654321',
      ADSENSE_CMP_SCRIPT_URL:'https://fundingchoicesmessages.google.com/i/pub-1234567890123456?ers=1'},
    stdio: ['ignore', 'ignore', 'pipe']
  });
  server.stderr.on('data', data => { if (String(data).includes('Error')) console.error(String(data)); });
  for (let i=0; i<100; i++) {
    try { if ((await fetch(origin + '/privacy/', {signal:AbortSignal.timeout(1000)})).ok) break; } catch (_) {}
    if (i===99) throw new Error('Local Django server did not start');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
});
after(async () => { if (browser) await browser.close(); if (server) server.kill(); });

async function pageFor(options = {}) {
  const context = await browser.newContext({viewport:{width:options.width || 1280, height:900}});
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  const requests = {cmp:0, ads:0};
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(({key, options}) => {
    if (options.gpc) Object.defineProperty(navigator, 'globalPrivacyControl', {value:true});
    if (options.choice) localStorage.setItem(key, JSON.stringify({value:options.choice, expires:Date.now() + 60000}));
    if (options.expired) localStorage.setItem(key, JSON.stringify({value:'allow', expires:1}));
    if (options.blockStorage) {
      Storage.prototype.getItem = () => { throw new Error('Storage disabled'); };
      Storage.prototype.setItem = () => { throw new Error('Storage disabled'); };
    }
    window.testUsStatus = options.usStatus;
  }, {key, options});
  await context.route('**/*', async route => {
    const url = route.request().url();
    if (url.startsWith(origin + '/')) return route.continue();
    if (url.startsWith('https://fundingchoicesmessages.google.com/')) {
      requests.cmp++;
      if (options.blockCmp) return route.abort();
      let body = cmpStub;
      if (options.denyTcf) body = body.replace('consents:{1:true}', 'consents:{1:false}');
      if (options.unknownTcf) body = body.replace('gdprApplies:true', 'gdprApplies:undefined');
      if (options.nonEu) body = body.replace('gdprApplies:true', 'gdprApplies:false');
      if (options.noApi) body = '';
      return route.fulfill({contentType:'application/javascript', body});
    }
    if (url.startsWith('https://pagead2.googlesyndication.com/')) {
      requests.ads++;
      if (options.blockAds) return route.abort();
      return route.fulfill({contentType:'application/javascript', body:`
        window.adsbygoogle = {push: () => {
          window.testAdPushes = (window.testAdPushes || 0) + 1;
          const ins = document.querySelector('ins.adsbygoogle');
          ins.setAttribute('data-ad-status', '${options.unfilled ? 'unfilled' : 'filled'}');
          ins.textContent = 'Test advertisement — no real ad request';
          ins.style.background = '#f1f5f9';
        }};
      `});
    }
    return route.abort();
  });
  await page.goto(origin + (options.path || guide));
  return {page, context, requests, errors};
}

async function allow(page) {
  await page.locator('[data-ad-choices]').last().click();
  await page.locator('[data-ad-allow]').click();
}
async function settle(page) {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(150);
}

test('fresh, denied, expired and GPC visits never contact advertising providers', async () => {
  for (const options of [{}, {choice:'deny'}, {expired:true}, {choice:'allow',gpc:true}]) {
    const {page, context, requests, errors} = await pageFor(options);
    await settle(page);
    assert.deepEqual(requests, {cmp:0, ads:0});
    if (options.gpc) {
      await page.locator('[data-ad-choices]').last().click();
      assert.equal(await page.locator('[data-ad-allow]').isDisabled(), true);
    }
    assert.deepEqual(errors, []);
    await context.close();
  }
});

test('unknown, denied, missing or blocked CMP and US opt-out fail closed', async () => {
  for (const options of [{denyTcf:true},{unknownTcf:true},{blockCmp:true},{noApi:true},{usStatus:3}]) {
    const {page, context, requests, errors} = await pageFor(options);
    await allow(page);
    await settle(page);
    assert.equal(requests.cmp, 1);
    assert.equal(requests.ads, 0);
    assert.deepEqual(errors, []);
    await context.close();
  }
});

test('consented ads load once, remain responsive, and use non-personalized requests', async () => {
  for (const width of [320, 390, 768, 1440]) {
    const {page, context, requests, errors} = await pageFor({width});
    await allow(page);
    await settle(page);
    await page.waitForFunction(() => window.testAdPushes === 1);
    assert.deepEqual(requests, {cmp:1, ads:1});
    assert.equal(await page.evaluate(() => window.adsbygoogle.requestNonPersonalizedAds), 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.evaluate(() => window.testCmpCallbacks.forEach(item => window.googlefc.callbackQueue.push(item)));
    assert.equal(requests.ads, 1);
    if (width === 390 || width === 1440) {
      await page.locator('[data-ad-container]').evaluate(el => el.scrollIntoView({block:'center'}));
      await page.screenshot({path:'/tmp/formd-ad-preview-' + width + '.png'});
    }
    assert.deepEqual(errors, []);
    await context.close();
  }
});

test('ads also work with confirmed non-European status or unavailable local storage', async () => {
  for (const options of [{nonEu:true},{blockStorage:true}]) {
    const {page, context, requests} = await pageFor(options);
    await allow(page);
    await settle(page);
    await page.waitForFunction(() => window.testAdPushes === 1);
    assert.equal(requests.ads, 1);
    await context.close();
  }
});

test('local revocation and TCF withdrawal stop ads after reload', async () => {
  for (const tcfWithdrawal of [false,true]) {
    const {page, context, requests} = await pageFor();
    await allow(page);
    await settle(page);
    await page.waitForFunction(() => window.testAdPushes === 1);
    const loaded = page.waitForEvent('load');
    if (tcfWithdrawal) {
      await page.evaluate(() => window.testTcf({cmpStatus:'loaded',gdprApplies:true,eventStatus:'useractioncomplete',purpose:{consents:{1:false}},vendor:{consents:{755:true}}},true));
    } else {
      await page.locator('[data-ad-choices]').last().click();
      await page.locator('[data-ad-deny]').click();
    }
    await loaded;
    await settle(page);
    assert.deepEqual(requests, {cmp:1,ads:1});
    assert.equal(await page.locator('[data-ad-container]').isVisible(), false);
    await context.close();
  }
});

test('unfilled and blocked ads collapse without breaking content', async () => {
  for (const options of [{unfilled:true},{blockAds:true}]) {
    const {page, context, errors} = await pageFor(options);
    await allow(page);
    await settle(page);
    await page.waitForFunction(() => document.querySelector('[data-ad-container]').hidden);
    assert.equal(await page.locator('article h1').count(), 1);
    assert.deepEqual(errors, []);
    await context.close();
  }
});

test('utility pages never load Google even with an existing opt-in', async () => {
  for (const path of ['/', '/search/', '/login/', '/pricing/', '/privacy/', '/learn/api/']) {
    const {page, context, requests} = await pageFor({path, choice:'allow'});
    await settle(page);
    assert.deepEqual(requests, {cmp:0,ads:0});
    assert.equal(await page.locator('[data-ad-container]').count(), 0);
    await context.close();
  }
});

test('privacy dialog fits a small screen and is keyboard dismissible', async () => {
  const {page, context} = await pageFor({width:320});
  await page.locator('[data-ad-choices]').last().click();
  assert.equal(await page.locator('#advertising-choices').evaluate(el => el.scrollWidth <= el.clientWidth), true);
  assert.equal(await page.locator('[data-ad-deny]').evaluate(el => el === document.activeElement), true);
  await page.screenshot({path:'/tmp/formd-consent-preview.png'});
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#advertising-choices').isVisible(), false);
  await context.close();
});

test('US privacy changes and cross-tab opt-outs stop loaded advertising', async () => {
  for (const crossTab of [false,true]) {
    const {page, context, requests} = await pageFor();
    await allow(page);
    await settle(page);
    await page.waitForFunction(() => window.testAdPushes === 1);
    const loaded = page.waitForEvent('load');
    if (crossTab) {
      const other = await context.newPage();
      // Same-origin storage write; use an existing page that does not load ads.
      await other.goto(origin + '/privacy/');
      await other.evaluate(key => localStorage.setItem(key, JSON.stringify({value:'deny',expires:Date.now()+60000})), key);
    } else await page.evaluate(() => window.testGpp({eventName:'sectionChange'},true));
    await loaded;
    await settle(page);
    assert.deepEqual(requests, {cmp:1,ads:1});
    assert.equal(await page.locator('[data-ad-container]').isVisible(), false);
    await context.close();
  }
});
