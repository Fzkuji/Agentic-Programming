// Live2D widget loader — drops a 2D anime mascot (看板娘) onto the
// page. Uses stevenjoezhang/live2d-widget via jsDelivr; the autoload
// script picks a random model from its bundled set (shizuku, hibiki,
// etc.) on each page load and injects its own canvas + tips bubble.
//
// Loads once per window; subsequent navigations between chat routes
// don't re-inject.

(function () {
  if (window.__live2dLoaded) return;
  window.__live2dLoaded = true;

  // Position override — the widget ships at bottom-left; move it to
  // bottom-right above the chat input bar so it sits next to the
  // textarea instead of overlapping the sidebar.
  var style = document.createElement('style');
  style.textContent =
    '#waifu { ' +
      'left: auto !important; ' +
      'right: 12px !important; ' +
      'bottom: 88px !important; ' +
      'z-index: 20 !important; ' +
    '} ' +
    '#waifu-tips { ' +
      'left: auto !important; ' +
      'right: 0 !important; ' +
    '}';
  document.head.appendChild(style);

  var s = document.createElement('script');
  s.src = 'https://fastly.jsdelivr.net/gh/stevenjoezhang/live2d-widget@latest/autoload.js';
  s.async = true;
  // Autoload.js computes its own base URL from its own <script> src,
  // so jsDelivr is what it uses to fetch model / waifu-tips.json.
  document.head.appendChild(s);
})();
