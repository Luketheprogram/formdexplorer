/* Pure JavaScript unit tests. No browser, network, or advertising requests. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/advertising.js', 'utf8');

function fixture({serving=false, preferencesOnly=true, choice=null, gpc=false,search=''}={}) {
  const events = new Map(), scripts = [], frames = [], timers = [];
  let reloads = 0, revocations = 0;
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
  const window = {frames:{},setTimeout:fn=>timers.push(fn),addEventListener:(name,fn)=>events.set('window:'+name,fn),location:{search,reload(){reloads++;}}};
  vm.runInNewContext(source, {document,window,URL,URLSearchParams,navigator:{globalPrivacyControl:gpc},localStorage:{getItem:()=>stored,setItem:(_,value)=>{stored=value;}},console:{...console,info(){}}});
  function settle({tcf=true,us=1,existing=false}={}) {
    window.__tcfapi=(_,version,cb)=>{
      if (tcf && !existing) cb({cmpStatus:'loaded',gdprApplies:true,eventStatus:'cmpuishown'},true);
      cb({cmpStatus:'loaded',gdprApplies:tcf,eventStatus:existing?'tcloaded':'useractioncomplete',purpose:{consents:{1:true}},vendor:{consents:{755:true}}},true);
    };
    window.googlefc.usstatesoptout={getInitialUsStatesOptOutStatus:()=>us};
    window.googlefc.showRevocationMessage=()=>{revocations++;};
    while(window.googlefc.callbackQueue.length) for (const item of window.googlefc.callbackQueue.splice(0)) Object.values(item).forEach(fn=>fn());
  }
  return {scripts,frames,settle,providerStatus,stored:()=>stored,reloads:()=>reloads,revocations:()=>revocations,loadProvider:fn=>{window.googlefc.__executeManualDeployment=fn;scripts[0].onload();},visible:()=>events.get('document:visibilitychange')(),timeout:()=>timers.forEach(fn=>fn()),click: id=>events.get(id+':click')()};
}

test('opening Google preferences does not opt into ads, including fully granted provider consent',()=>{
  const f=fixture();
  assert.equal(f.scripts.length,0);
  f.click('allow');
  assert.equal(f.scripts.length,0);
  f.click('partners');
  assert.equal(f.scripts.length,1);
  assert.match(f.scripts[0].src,/^https:\/\/fundingchoicesmessages\.google\.com\//);
  assert.equal(f.frames[0].name,'googlefcPresent');
  f.settle();
  assert.equal(f.scripts.length,1);
  assert.equal(f.stored(),null);
  assert.equal(f.revocations(),0);
});

test('explicit privacy settings survive a return to the tab without advertising permission',()=>{
  const f=fixture({choice:'deny'});
  f.click('partners'); f.visible();
  assert.equal(f.reloads(),0);
  assert.equal(f.scripts.length,1);
});

test('privacy previews forward only Google privacy parameters to the message service',()=>{
  const f=fixture({search:'?fc=alwaysshow&fctype=gdpr&private=never-share'}); f.click('partners');
  const url=new URL(f.scripts[0].src);
  assert.equal(url.searchParams.get('fc'),'alwaysshow');
  assert.equal(url.searchParams.get('fctype'),'gdpr');
  assert.equal(url.searchParams.has('private'),false);
  const other=fixture({search:'?fc=alwaysshow&fctype=monetization'});other.click('partners');
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

test('explicit non-applicability is shown without implying a consent grant',()=>{
  const f=fixture(); f.click('partners'); f.settle({tcf:false,us:1});
  assert.match(f.providerStatus.textContent,/no regional privacy message applies/);
  assert.equal(f.revocations(),0);
  assert.equal(f.stored(),null);
  assert.equal(f.scripts.length,1);
});

test('existing advertising permission cannot auto-load the privacy-page CMP or enable ads while the site is off',()=>{
  const f=fixture({choice:'allow'});
  assert.equal(f.scripts.length,0);
  f.click('partners'); f.settle();
  assert.equal(f.scripts.length,1);
  assert.ok(f.scripts.every(s=>!s.src.includes('googlesyndication')));
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
