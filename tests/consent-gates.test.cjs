/* Pure JavaScript unit tests. No browser, network, or advertising requests. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('static/js/advertising.js', 'utf8');

function fixture({serving=false, preferencesOnly=true, choice=null, gpc=false}={}) {
  const events = new Map(), scripts = [], frames = [];
  const control = id => ({hidden:true, addEventListener(event, callback) { events.set(id+':'+event, callback); }});
  const controls = Object.fromEntries(['status','allow','partners','close','deny'].map(x => [x,control(x)]));
  const dialog = {dataset:{adServing:String(serving)}, querySelector: selector => controls[selector.match(/data-ad-(\w+)/)[1]], close(){}, showModal(){}};
  const config = {client:'ca-pub-1234567890123456',cmpUrl:'https://fundingchoicesmessages.google.com/i/pub-1234567890123456?ers=1',allowAds:serving,preferencesOnly};
  const container = {hidden:true,getBoundingClientRect:()=>({width:900})};
  let stored = choice ? JSON.stringify({value:choice,expires:Date.now()+60000}) : null;
  const document = {
    getElementById: id => id==='advertising-choices' ? dialog : id==='consent-config' ? {textContent:JSON.stringify(config)} : null,
    querySelector: selector => selector==='[data-ad-container]' ? container : null,
    querySelectorAll:()=>[],addEventListener(){},
    createElement: tag => ({tag,style:{}}),
    head:{appendChild: script => scripts.push(script)}, body:{appendChild: frame=>frames.push(frame)},
  };
  const window = {frames:{},addEventListener(){},location:{reload(){}}};
  vm.runInNewContext(source, {document,window,navigator:{globalPrivacyControl:gpc},localStorage:{getItem:()=>stored,setItem:(_,value)=>{stored=value;}},console});
  function settle({tcf=true,us=1}={}) {
    window.__tcfapi=(_,version,cb)=>cb({cmpStatus:'loaded',gdprApplies:tcf,eventStatus:'useractioncomplete',purpose:{consents:{1:true}},vendor:{consents:{755:true}}},true);
    window.googlefc.usstatesoptout={getInitialUsStatesOptOutStatus:()=>us};
    window.googlefc.showRevocationMessage=()=>{};
    for (const item of window.googlefc.callbackQueue.splice(0)) Object.values(item).forEach(fn=>fn());
  }
  return {scripts,frames,settle,stored:()=>stored,click: id=>events.get(id+':click')()};
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
