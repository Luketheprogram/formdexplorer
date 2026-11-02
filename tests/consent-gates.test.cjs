/* Pure JavaScript unit tests. No browser, network, or advertising requests. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/advertising.js', 'utf8');

function fixture({serving=false, preferencesOnly=true, choice=null, gpc=false,search=''}={}) {
  const events = new Map(), scripts = [], frames = [], timers = [];
  let reloads = 0, revocations = 0, gppCallback;
  const control = id => ({hidden:true, addEventListener(event, callback) { events.set(id+':'+event, callback); }});
  const controls = Object.fromEntries(['status','allow','partners','close','deny'].map(x => [x,control(x)]));
  const dialog = {dataset:{adServing:String(serving)}, querySelector: selector => controls[selector.match(/data-ad-(\w+)/)[1]], close(){}, showModal(){}};
  const config = {client:'ca-pub-1234567890123456',cmpUrl:'https://fundingchoicesmessages.google.com/i/pub-1234567890123456?ers=1',allowAds:serving,preferencesOnly};
  const container = {hidden:true,getBoundingClientRect:()=>({width:900})};
  const providerStatus = {dataset:{},textContent:''};
  let stored = choice ? JSON.stringify({value:choice,expires:Date.now()+60000}) : null;
  const document = {
    getElementById: id => id==='advertising-choices' ? dialog : id==='consent-config' ? {textContent:JSON.stringify(config)} : null,
    querySelector: selector => selector==='[data-ad-container]' ? container : selector==='[data-consent-status]' ? providerStatus : null,
    querySelectorAll:()=>[],addEventListener:(name,fn)=>events.set('document:'+name,fn),visibilityState:'visible',
    createElement: tag => ({tag,style:{}}),
    head:{appendChild: script => scripts.push(script)}, body:{appendChild: frame=>frames.push(frame)},
  };
  const page = new URL('https://publisher.example/privacy/'+search);
  const window = {frames:{},setTimeout:fn=>timers.push(fn),addEventListener:(name,fn)=>events.set('window:'+name,fn),location:{href:page.href,search:page.search,reload(){reloads++;}}};
  vm.runInNewContext(source, {document,window,URL,URLSearchParams,navigator:{globalPrivacyControl:gpc},localStorage:{getItem:()=>stored,setItem:(_,value)=>{stored=value;}},console:{...console,info(){}}});
  function settle({tcf=true,us=1,existing=false,inactive=false}={}) {
    window.__gpp=(_,callback)=>{gppCallback=callback;};
    window.__tcfapi=(_,version,cb)=>{
      if (inactive) { cb({cmpStatus:'loaded',gdprApplies:true},true); return; }
      if (tcf && !existing) cb({cmpStatus:'loaded',gdprApplies:true,eventStatus:'cmpuishown'},true);
      cb({cmpStatus:'loaded',gdprApplies:tcf,eventStatus:existing?'tcloaded':'useractioncomplete',purpose:{consents:{1:true}},vendor:{consents:{755:true}}},true);
    };
    window.googlefc.usstatesoptout={getInitialUsStatesOptOutStatus:()=>us};
    window.googlefc.showRevocationMessage=()=>{revocations++;};
    while(window.googlefc.callbackQueue.length) for (const item of window.googlefc.callbackQueue.splice(0)) Object.values(item).forEach(fn=>fn());
  }
  return {scripts,frames,settle,providerStatus,adQueue:()=>window.adsbygoogle,sectionChange:()=>gppCallback({eventName:'sectionChange'},true),stored:()=>stored,reloads:()=>reloads,revocations:()=>revocations,visible:()=>events.get('document:visibilitychange')(),timeout:()=>timers.forEach(fn=>fn()),click: id=>events.get(id+':click')()};
}

test('opening Google preferences does not opt into ads, including fully granted provider consent',()=>{
  const f=fixture();
  assert.equal(f.scripts.length,0);
  f.click('allow');
  assert.equal(f.scripts.length,0);
  f.click('partners');
  assert.equal(f.scripts.length,1);
  assert.match(f.scripts[0].src,/^https:\/\/pagead2\.googlesyndication\.com\/pagead\/js\/adsbygoogle.js\?client=ca-pub-/);
  assert.equal(f.adQueue().pauseAdRequests,1);
  assert.equal(f.adQueue().length,0);
  assert.equal(f.frames.length,0);
  f.settle();
  assert.equal(f.scripts.length,1);
  assert.equal(f.stored(),null);
  assert.equal(f.revocations(),0);
  assert.equal(f.adQueue().pauseAdRequests,1);
  assert.equal(f.adQueue().length,0);
});

test('the paused publisher tag explicitly starts the message tag without queuing ads',()=>{
  const f=fixture({search:'?fc=alwaysshow&fctype=gdpr'}); f.click('partners');
  assert.equal(f.adQueue().pauseAdRequests,1);
  f.scripts[0].onload();
  assert.equal(f.scripts.length,2);
  assert.match(f.scripts[1].src,/fundingchoicesmessages\.google\.com/);
  assert.equal(new URL(f.scripts[1].src).searchParams.get('fctype'),'gdpr');
  assert.equal(f.frames[0].name,'googlefcPresent');
  f.settle();
  assert.equal(f.adQueue().length,0);
  assert.equal(f.adQueue().pauseAdRequests,1);
  assert.equal(f.scripts.length,2);
});

test('privacy settings cannot opt into ads even when the publisher serving flag is enabled',()=>{
  const f=fixture({serving:true,preferencesOnly:true});
  f.click('allow');
  assert.equal(f.stored(),null);
  assert.equal(f.scripts.length,0);
  f.click('partners'); f.scripts[0].onload(); f.settle();
  assert.equal(f.stored(),null);
  assert.equal(f.adQueue().pauseAdRequests,1);
  assert.equal(f.adQueue().length,0);
});

test('explicit privacy settings survive a return to the tab without advertising permission',()=>{
  const f=fixture({choice:'deny'});
  f.click('partners'); f.visible();
  assert.equal(f.reloads(),0);
  assert.equal(f.scripts.length,1);
});

test('Google receives the published page context without private query or fragment data',()=>{
  const f=fixture({search:'?fc=alwaysshow&fctype=gdpr&private=never-share#private-section'});
  f.click('partners'); f.scripts[0].onload();
  const url=new URL(f.scripts[1].src);
  assert.equal(url.searchParams.get('href'),'https://publisher.example/privacy');
  assert.equal(url.searchParams.get('fctype'),'gdpr');
  assert.equal(url.href.includes('never-share'),false);
  assert.equal(url.href.includes('private-section'),false);
  assert.equal(f.adQueue().pauseAdRequests,1);
  assert.equal(f.adQueue().length,0);
});

test('US privacy updates cannot reload an ads-off preferences session',()=>{
  const f=fixture(); f.click('partners'); f.settle({tcf:false,us:2}); f.sectionChange();
  assert.equal(f.reloads(),0);
  assert.equal(f.stored(),null);
  assert.equal(f.scripts.length,1);
});

test('US privacy changes still stop enabled advertising',()=>{
  const f=fixture({serving:true,preferencesOnly:false,choice:'allow'});
  f.settle({tcf:false,us:2});
  assert.equal(f.scripts.length,2);
  f.sectionChange();
  assert.equal(f.reloads(),1);
  assert.equal(JSON.parse(f.stored()).value,'deny');
});

test('privacy previews forward only Google privacy parameters to the message service',()=>{
  const f=fixture({serving:true,preferencesOnly:false,search:'?fc=alwaysshow&fctype=gdpr&private=never-share'}); f.click('allow');
  const url=new URL(f.scripts[0].src);
  assert.equal(url.searchParams.get('fc'),'alwaysshow');
  assert.equal(url.searchParams.get('fctype'),'gdpr');
  assert.equal(url.searchParams.has('private'),false);
  const other=fixture({serving:true,preferencesOnly:false,search:'?fc=alwaysshow&fctype=monetization'});other.click('allow');
  assert.equal(new URL(other.scripts[0].src).searchParams.has('fc'),false);
});

test('an existing European decision is reopened only after consent data is ready',()=>{
  const f=fixture(); f.click('partners');
  assert.equal(f.revocations(),0);
  f.settle({existing:true});
  assert.equal(f.revocations(),1);
  assert.equal(f.scripts.length,1);
});

test('an unavailable provider produces clear feedback and never unlocks ads',()=>{
  const f=fixture(); f.click('partners'); f.timeout();
  assert.equal(f.providerStatus.dataset.phase,'unavailable');
  assert.match(f.providerStatus.textContent,/Advertising remains off/);
  assert.equal(f.scripts.length,1);
});

test('an inactive Google bootstrap is not mistaken for an existing consent decision',()=>{
  const f=fixture(); f.click('partners'); f.settle({inactive:true,us:1}); f.timeout();
  assert.equal(f.revocations(),0);
  assert.equal(f.stored(),null);
  assert.equal(f.scripts.length,1);
  assert.equal(f.providerStatus.dataset.phase,'unavailable');
});

test('explicit non-applicability is shown without implying a consent grant',()=>{
  const f=fixture(); f.click('partners'); f.settle({tcf:false,us:1});
  assert.match(f.providerStatus.textContent,/no regional privacy message applies/);
  assert.equal(f.revocations(),0);
  assert.equal(f.stored(),null);
  assert.equal(f.scripts.length,1);
});

test('a stored Google US opt-out blocks ads despite an earlier local opt-in',()=>{
  const f=fixture({serving:true,preferencesOnly:false,choice:'allow'});
  f.settle({us:3});
  assert.equal(f.scripts.length,1);
  assert.match(f.providerStatus.textContent,/have opted out/);
});

test('existing advertising permission cannot auto-load the privacy-page CMP or enable ads while the site is off',()=>{
  const f=fixture({choice:'allow'});
  assert.equal(f.scripts.length,0);
  f.click('partners'); f.settle();
  assert.equal(f.scripts.length,1);
  assert.equal(f.adQueue().pauseAdRequests,1);
  assert.equal(f.adQueue().length,0);
});

test('GPC prevents both advertising and explicit CMP loading',()=>{
  const f=fixture({choice:'allow',gpc:true});
  f.click('partners'); f.click('allow');
  assert.equal(f.scripts.length,0);
});

test('ad delivery still requires the site flag, local opt-in, and both known provider decisions',()=>{
  const f=fixture({serving:true,preferencesOnly:false});
  assert.equal(f.scripts.length,0);
  f.click('allow');
  assert.equal(f.scripts.length,1);
  f.settle({us:0});
  assert.equal(f.scripts.length,1);
  const allowed=fixture({serving:true,preferencesOnly:false});
  allowed.click('allow'); allowed.settle();
  assert.equal(allowed.scripts.length,2);
  assert.match(allowed.scripts[1].src,/^https:\/\/pagead2\.googlesyndication\.com\//);
});
