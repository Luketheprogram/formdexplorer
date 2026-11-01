/* Google CMP is a separate prerequisite, not replaced by the local opt-in. */
(() => {
  'use strict';
  const dialog = document.getElementById('advertising-choices');
  if (!dialog) return;
  const key = 'formd-advertising-v1';
  const lifetime = 180 * 24 * 60 * 60 * 1000;
  const configNode = document.getElementById('advertising-config') || document.getElementById('consent-config');
  const config = configNode ? JSON.parse(configNode.textContent) : null;
  const servingEnabled = dialog.dataset.adServing === 'true';
  const container = document.querySelector('[data-ad-container]');
  const note = document.querySelector('[data-ad-note]');
  const status = dialog.querySelector('[data-ad-status]');
  const allowButton = dialog.querySelector('[data-ad-allow]');
  const partnersButton = dialog.querySelector('[data-ad-partners]');
  if (config?.preferencesOnly) partnersButton.hidden = false;
  let choice = readChoice();
  let cmpStarted = false;
  let adStarted = false;
  let tcfAllowed = false;
  let usAllowed = false;
  let observer;
  const gpc = () => navigator.globalPrivacyControl === true;

  function readChoice() {
    try {
      const saved = JSON.parse(localStorage.getItem(key));
      return saved && saved.expires > Date.now() && ['allow', 'deny'].includes(saved.value) ? saved.value : null;
    } catch (_) { return null; }
  }

  function saveChoice(value) {
    choice = value;
    try { localStorage.setItem(key, JSON.stringify({value, expires: Date.now() + lifetime})); }
    catch (_) { /* In restricted browsers the choice lasts only for this page. */ }
  }

  function updateControls() {
    allowButton.disabled = gpc() || !servingEnabled;
    partnersButton.disabled = gpc();
    status.textContent = gpc() ? 'Global Privacy Control is on. Advertising is disabled.' :
      !servingEnabled ? 'Advertising is turned off for this site. Reviewing Google privacy choices cannot turn it on.' :
      choice === 'allow' ? 'Advertising is allowed on this browser, subject to your Google consent settings.' :
        'Advertising is off. This does not affect access to any site features.';
    if (note) note.hidden = choice === 'allow' || gpc();
  }

  function disable() {
    saveChoice('deny');
    tcfAllowed = false;
    usAllowed = false;
    if (observer) observer.disconnect();
    if (container) container.hidden = true;
    // A loaded vendor script cannot be unloaded safely; a fresh document stops it.
    if (cmpStarted || adStarted) window.location.reload();
    else { updateControls(); dialog.close(); }
  }

  function permitted() { return servingEnabled && config?.allowAds === true && choice === 'allow' && !gpc() && tcfAllowed && usAllowed; }

  function requestAd() {
    if (adStarted || !permitted() || !container || container.getBoundingClientRect().width < 250) return;
    adStarted = true;
    const tag = document.createElement('script');
    tag.async = true;
    tag.crossOrigin = 'anonymous';
    tag.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' + encodeURIComponent(config.client);
    tag.onload = () => {
      if (!permitted()) return;
      try {
        const queue = window.adsbygoogle = window.adsbygoogle || [];
        // Conservative launch: contextual ads, even when personalization is permitted.
        queue.requestNonPersonalizedAds = 1;
        queue.push({});
      } catch (_) { container.hidden = true; }
    };
    tag.onerror = () => { container.hidden = true; };
    document.head.appendChild(tag);
  }

  function maybeShowAd() {
    if (!permitted()) {
      if (container) container.hidden = true;
      if (observer) { observer.disconnect(); observer = null; }
      if (adStarted) disable();
      return;
    }
    if (!container || adStarted || observer) return;
    container.hidden = false;
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting) && permitted()) {
          requestAd();
          if (adStarted) observer.disconnect();
        }
      }, {rootMargin: '200px'});
      observer.observe(container);
    } else requestAd();
  }

  function startCmp(preferences = false) {
    if (!config || cmpStarted || gpc() || (!preferences && (choice !== 'allow' || config.preferencesOnly))) return;
    cmpStarted = true;
    window.googlefc = window.googlefc || {};
    window.googlefc.callbackQueue = window.googlefc.callbackQueue || [];
    window.googlefc.callbackQueue.push({CONSENT_API_READY: () => {
      partnersButton.hidden = typeof window.googlefc.showRevocationMessage !== 'function';
      if (typeof window.__tcfapi === 'function') {
        window.__tcfapi('addEventListener', 2, (data, success) => {
          // Opening preferences is not itself a new consent decision.
          if (success && data?.eventStatus === 'cmpuishown') return;
          const settled = data && ['tcloaded', 'useractioncomplete'].includes(data.eventStatus);
          tcfAllowed = Boolean(success && data && data.cmpStatus === 'loaded' && (
            data.gdprApplies === false || (data.gdprApplies === true && settled &&
              data.purpose?.consents?.[1] === true && data.vendor?.consents?.[755] === true)
          ));
          maybeShowAd();
        });
      }
      // Google consumes GPP signals itself. Stop this page's ads on subsequent
      // US privacy changes; require a fresh opt-in rather than keep old requests.
      if (typeof window.__gpp === 'function') {
        window.__gpp('addEventListener', (event, success) => {
          if (success && event?.eventName === 'sectionChange' && (adStarted || usAllowed)) disable();
        });
      }
    }});
    window.googlefc.callbackQueue.push({INITIAL_US_STATES_OPT_OUT_DATA_READY: () => {
      const api = window.googlefc.usstatesoptout;
      if (!api || typeof api.getInitialUsStatesOptOutStatus !== 'function') return;
      const value = api.getInitialUsStatesOptOutStatus();
      // Google's documented enum: 1 = does not apply; 2 = not opted out.
      usAllowed = value === 1 || value === 2;
      maybeShowAd();
    }});
    // Bootstrap from the publisher's actual Google message tag. This signals
    // that the standalone CMP is present; it does not load an advertising tag.
    if (!window.frames['googlefcPresent']) {
      const iframe = document.createElement('iframe');
      iframe.style.cssText = 'width: 0; height: 0; border: none; z-index: -1000; left: -1000px; top: -1000px;';
      iframe.style.display = 'none';
      iframe.name = 'googlefcPresent';
      document.body.appendChild(iframe);
    }
    const script = document.createElement('script');
    script.async = true;
    script.src = config.cmpUrl;
    script.onerror = () => {
      if (container) container.hidden = true;
      cmpStarted = false;
      updateControls();
      status.textContent = 'Google privacy settings could not load. Advertising remains off. Please try again or contact us using the privacy policy.';
      if (!dialog.open) dialog.showModal();
    };
    document.head.appendChild(script);
    // Missing, blocked, or incomplete CMP callbacks never unlock ad requests.
  }

  document.querySelectorAll('[data-ad-choices]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => { updateControls(); dialog.showModal(); });
  });
  dialog.querySelector('[data-ad-close]').addEventListener('click', () => dialog.close());
  dialog.querySelector('[data-ad-deny]').addEventListener('click', disable);
  allowButton.addEventListener('click', () => {
    if (gpc() || !servingEnabled) return;
    saveChoice('allow');
    updateControls();
    dialog.close();
    startCmp();
  });
  partnersButton.addEventListener('click', () => {
    if (gpc() || !config) return;
    dialog.close();
    startCmp(true);
    window.googlefc.callbackQueue.push({CONSENT_API_READY: () => {
      if (typeof window.googlefc.showRevocationMessage === 'function') window.googlefc.showRevocationMessage();
    }});
  });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    choice = readChoice();
    if (choice !== 'allow' && cmpStarted) window.location.reload();
    else { updateControls(); startCmp(); }
  });
  window.addEventListener('pageshow', event => {
    if (event.persisted) window.location.reload();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    if (gpc() || readChoice() !== 'allow') {
      if (cmpStarted) disable();
    }
  });
  if (container && 'MutationObserver' in window) {
    new MutationObserver(() => {
      if (container.querySelector('ins')?.getAttribute('data-ad-status') === 'unfilled') container.hidden = true;
    }).observe(container, {attributes: true, subtree: true, attributeFilter: ['data-ad-status']});
  }
  updateControls();
  startCmp();
})();
