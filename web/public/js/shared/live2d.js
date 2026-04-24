// Live2D widget loader — uses oh-my-live2d, an actively-maintained
// wrapper around pixi-live2d-display. Picks a default character on
// first load; no hidden state in localStorage, no mobile auto-hide.

(function () {
  if (window.__live2dLoaded) return;
  window.__live2dLoaded = true;

  var s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/oh-my-live2d@latest';
  s.async = true;
  s.onload = function () {
    try {
      var OML2D = window.OML2D || window.oml2d;
      if (!OML2D || typeof OML2D.loadOml2d !== 'function') {
        console.error('[live2d] oh-my-live2d loaded but OML2D API missing');
        return;
      }
      OML2D.loadOml2d({
        mobileDisplay: true,
        // Pin one model so we always see a character — the default
        // model list sometimes 404s when the wrapper's CDN upstream
        // is flaky.
        models: [{
          name: 'pio',
          path: 'https://model.oml2d.com/Pio/model.json',
          position: [0, 40],
          scale: 0.25,
          stageStyle: { height: 300 },
        }],
        menus: { disable: true },
        tips: { idleTips: { interval: 20000 } },
      });
    } catch (err) {
      console.error('[live2d] init failed:', err);
    }
  };
  s.onerror = function (e) {
    console.error('[live2d] failed to load oh-my-live2d from jsDelivr', e);
  };
  document.head.appendChild(s);
})();
