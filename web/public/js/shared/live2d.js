// Anime mascot — static image + CSS breathing animation.
//
// Original plan was Live2D (oh-my-live2d) but that needs WebGL, and
// the user's Chrome has hardware acceleration disabled. Falling back
// to a random waifu image from api.waifu.pics (SFW endpoint) wrapped
// in a gentle idle animation — same visual role (anime character in
// the corner), no WebGL dependency.

(function () {
  if (window.__waifuLoaded) return;
  window.__waifuLoaded = true;

  var style = document.createElement('style');
  style.textContent =
    '#waifu-mascot {' +
      'position: fixed;' +
      'right: 16px;' +
      'bottom: 96px;' +
      'width: 160px;' +
      'height: 220px;' +
      'z-index: 20;' +
      'pointer-events: none;' +
      'border-radius: 14px;' +
      'overflow: hidden;' +
      'box-shadow: 0 6px 20px rgba(0,0,0,0.18);' +
      'animation: waifu-idle 4s ease-in-out infinite;' +
      'opacity: 0;' +
      'transition: opacity 400ms ease;' +
    '}' +
    '#waifu-mascot.ready { opacity: 1; }' +
    '#waifu-mascot img {' +
      'width: 100%; height: 100%; object-fit: cover; display: block;' +
    '}' +
    '@keyframes waifu-idle {' +
      '0%, 100% { transform: translateY(0) scale(1); }' +
      '50%     { transform: translateY(-3px) scale(1.012); }' +
    '}';
  document.head.appendChild(style);

  var container = document.createElement('div');
  container.id = 'waifu-mascot';
  var img = document.createElement('img');
  img.alt = '';
  img.addEventListener('load', function () {
    container.classList.add('ready');
  });
  img.addEventListener('error', function () {
    console.error('[waifu] image failed to load; removing mascot');
    if (container.parentNode) container.parentNode.removeChild(container);
  });
  container.appendChild(img);
  document.body.appendChild(container);

  fetch('https://api.waifu.pics/sfw/waifu')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data && data.url) img.src = data.url;
      else throw new Error('no url in response');
    })
    .catch(function (err) {
      console.error('[waifu] API failed:', err);
      if (container.parentNode) container.parentNode.removeChild(container);
    });
})();
