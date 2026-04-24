// Live2D widget loader — uses oh-my-live2d, an actively-maintained
// wrapper around pixi-live2d-display. Picks the Pio model; the
// wrapper renders it at the bottom-right corner by default.

(function () {
  if (window.__live2dLoaded) return;
  window.__live2dLoaded = true;

  var s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/oh-my-live2d@latest';
  s.async = true;
  s.onload = function () {
    try {
      var loader = window.loadOml2d
        || (window.OML2D && window.OML2D.loadOml2d)
        || (window.oml2d && window.oml2d.loadOml2d);
      if (typeof loader !== 'function') {
        console.error('[live2d] oh-my-live2d loaded but loadOml2d API not found');
        return;
      }
      loader({
        mobileDisplay: true,
        // model.oml2d.com returned ERR_CONNECTION_CLOSED on the
        // user's network. Switch to a jsDelivr-hosted mirror that
        // shares reachability with the oh-my-live2d script itself —
        // if jsDelivr works for the JS, it works for the model.
        models: [{
          name: 'shizuku',
          path: 'https://fastly.jsdelivr.net/gh/guansss/pixi-live2d-display/test/assets/shizuku/shizuku.model.json',
          position: [0, 40],
          scale: 0.18,
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
