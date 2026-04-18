/**
 * workdir.js — working directory picker for every function form.
 *
 * Workdir is a runtime-level setting, not a function argument. It travels
 * alongside the normal `run <func> key=val ...` command as `work_dir=<path>`;
 * server.py intercepts it before dispatch and routes it into
 * exec_rt.set_workdir().
 *
 * UI: a single pill button at the top of the function form. Click opens a
 * dropdown with Choose a folder…, Use OpenProgram repo, and recent
 * folders (localStorage-backed). Hidden <input id="fnField_work_dir">
 * stores the actual value so submitFnForm can read it uniformly.
 */

var _WORKDIR_RECENT_KEY = 'openprogram_workdir_recent';
var _WORKDIR_RECENT_MAX = 6;

function buildWorkdirField() {
  return (
    '<div class="workdir-field" id="workdirField">' +
      '<input type="hidden" id="fnField_work_dir" value="">' +
      '<button type="button" class="workdir-pill workdir-pill-empty" id="workdirPill" onclick="toggleWorkdirMenu()">' +
        '<svg class="workdir-icon" viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M3 6a2 2 0 0 1 2-2h3l2 2h5a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>' +
        '</svg>' +
        '<span class="workdir-pill-text" id="workdirPillText">Choose working directory</span>' +
        '<svg class="workdir-chev" viewBox="0 0 20 20" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
          '<polyline points="5 8 10 13 15 8"></polyline>' +
        '</svg>' +
      '</button>' +
      '<div class="workdir-menu" id="workdirMenu" hidden></div>' +
    '</div>'
  );
}

async function initWorkdirField(fnName) {
  var input = document.getElementById('fnField_work_dir');
  if (!input) return;
  input.dataset.fnName = fnName || '';

  var convId = (typeof currentConvId !== 'undefined') ? currentConvId : null;
  var url = '/api/workdir/defaults?function_name=' + encodeURIComponent(fnName || '');
  if (convId) url += '&conv_id=' + encodeURIComponent(convId);
  try {
    var r = await fetch(url);
    var data = await r.json();
    window._workdirRepoRoot = data.repo;
    window._workdirHome = data.home;
    if (data.last) {
      _setWorkdirValue(data.last, /*skipRecent*/ true);
    } else {
      _setWorkdirValue('', true);
    }
  } catch (e) {
    // non-fatal — user can still open the picker
  }

  // Close dropdown on outside click
  document.addEventListener('click', _workdirOutsideClick, true);
}

function _workdirOutsideClick(e) {
  var field = document.getElementById('workdirField');
  if (!field) {
    document.removeEventListener('click', _workdirOutsideClick, true);
    return;
  }
  if (!field.contains(e.target)) {
    _closeWorkdirMenu();
  }
}

function _setWorkdirValue(path, skipRecent) {
  var input = document.getElementById('fnField_work_dir');
  var pill = document.getElementById('workdirPill');
  var text = document.getElementById('workdirPillText');
  if (!input || !pill || !text) return;
  input.value = path || '';
  if (path) {
    text.textContent = _shortenPath(path);
    pill.title = path;
    pill.classList.remove('workdir-pill-empty');
    pill.classList.remove('workdir-pill-error');
    if (!skipRecent) _pushRecent(path);
  } else {
    text.textContent = 'Choose working directory';
    pill.removeAttribute('title');
    pill.classList.add('workdir-pill-empty');
  }
}

function _shortenPath(p) {
  if (!p) return '';
  // Show the last two path segments; prefix with ~ if inside $HOME.
  var home = window._workdirHome || '';
  var display = p;
  if (home && p.indexOf(home) === 0) {
    display = '~' + p.slice(home.length);
  }
  var parts = display.split('/').filter(Boolean);
  if (parts.length <= 2) return display;
  var last = parts.slice(-2).join('/');
  return (display.startsWith('~') ? '~/…/' : '…/') + last;
}

function _getRecent() {
  try {
    var raw = localStorage.getItem(_WORKDIR_RECENT_KEY);
    var arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch (e) {
    return [];
  }
}

function _pushRecent(path) {
  if (!path) return;
  var arr = _getRecent();
  arr = arr.filter(function(p) { return p !== path; });
  arr.unshift(path);
  if (arr.length > _WORKDIR_RECENT_MAX) arr = arr.slice(0, _WORKDIR_RECENT_MAX);
  try { localStorage.setItem(_WORKDIR_RECENT_KEY, JSON.stringify(arr)); } catch (e) {}
}

function toggleWorkdirMenu() {
  var menu = document.getElementById('workdirMenu');
  if (!menu) return;
  if (!menu.hasAttribute('hidden')) {
    _closeWorkdirMenu();
    return;
  }
  _openWorkdirMenu();
}

function _openWorkdirMenu() {
  var menu = document.getElementById('workdirMenu');
  var pill = document.getElementById('workdirPill');
  if (!menu || !pill) return;
  menu.innerHTML = _renderWorkdirMenu();
  menu.removeAttribute('hidden');
  pill.classList.add('workdir-pill-open');
}

function _closeWorkdirMenu() {
  var menu = document.getElementById('workdirMenu');
  var pill = document.getElementById('workdirPill');
  if (menu) menu.setAttribute('hidden', '');
  if (pill) pill.classList.remove('workdir-pill-open');
}

function _renderWorkdirMenu() {
  var input = document.getElementById('fnField_work_dir');
  var current = input ? input.value : '';
  var repoRoot = window._workdirRepoRoot;

  var html = '';
  html +=
    '<button type="button" class="workdir-menu-item" onclick="_workdirChooseFolder()">' +
      '<svg class="workdir-menu-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M3 6a2 2 0 0 1 2-2h3l2 2h5a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>' +
        '<path d="M10 9v4m-2-2h4"/>' +
      '</svg>' +
      '<span>Choose a folder…</span>' +
    '</button>';

  if (repoRoot && repoRoot !== current) {
    html +=
      '<button type="button" class="workdir-menu-item" onclick="_workdirUseRepo()">' +
        '<svg class="workdir-menu-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
          '<circle cx="10" cy="10" r="7"/>' +
          '<circle cx="10" cy="10" r="2.5"/>' +
          '<path d="M10 3v3M10 14v3M3 10h3M14 10h3"/>' +
        '</svg>' +
        '<span>Use OpenProgram repo</span>' +
      '</button>';
  }

  var recent = _getRecent().filter(function(p) { return p && p !== current; });
  if (recent.length > 0) {
    html += '<div class="workdir-menu-sep"></div>';
    html += '<div class="workdir-menu-label">Recent</div>';
    for (var i = 0; i < recent.length; i++) {
      var p = recent[i];
      html +=
        '<button type="button" class="workdir-menu-item workdir-menu-recent" title="' + _escAttr(p) + '" ' +
                'onclick="_workdirUseRecent(\'' + _escJs(p) + '\')">' +
          '<svg class="workdir-menu-icon" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
            '<path d="M3 6a2 2 0 0 1 2-2h3l2 2h5a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>' +
          '</svg>' +
          '<span class="workdir-menu-recent-text">' + _escHtml(_shortenPath(p)) + '</span>' +
        '</button>';
    }
  }

  return html;
}

function _workdirChooseFolder() {
  _closeWorkdirMenu();
  var input = document.getElementById('fnField_work_dir');
  var start = (input && input.value) || window._workdirHome || '';
  _showPickerOverlay(start, function(chosen) {
    _setWorkdirValue(chosen);
  });
}

function _workdirUseRepo() {
  if (window._workdirRepoRoot) _setWorkdirValue(window._workdirRepoRoot);
  _closeWorkdirMenu();
}

function _workdirUseRecent(path) {
  _setWorkdirValue(path);
  _closeWorkdirMenu();
}

// ── Folder picker modal ─────────────────────────────────────────────

function _showPickerOverlay(initialPath, onSelect) {
  _closePicker();
  var overlay = document.createElement('div');
  overlay.id = 'folderPickerOverlay';
  overlay.className = 'folder-picker-overlay';
  overlay.innerHTML =
    '<div class="folder-picker">' +
      '<div class="folder-picker-header">' +
        '<span>Choose a folder</span>' +
        '<button type="button" class="folder-picker-close" onclick="_closePicker()">&times;</button>' +
      '</div>' +
      '<div class="folder-picker-crumbs" id="folderPickerCrumbs"></div>' +
      '<div class="folder-picker-list" id="folderPickerList">Loading…</div>' +
      '<div class="folder-picker-footer">' +
        '<span class="folder-picker-current" id="folderPickerCurrent"></span>' +
        '<div class="folder-picker-actions">' +
          '<button type="button" class="folder-picker-btn" onclick="_closePicker()">Cancel</button>' +
          '<button type="button" class="folder-picker-btn folder-picker-btn-primary" id="folderPickerSelect">Select</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);
  overlay.addEventListener('click', function(e) { if (e.target === overlay) _closePicker(); });
  document.addEventListener('keydown', _pickerKeyHandler);

  document.getElementById('folderPickerSelect').onclick = function() {
    var cur = overlay.dataset.currentPath;
    if (cur && typeof onSelect === 'function') onSelect(cur);
    _closePicker();
  };
  _browseTo(initialPath);
}

function _closePicker() {
  var el = document.getElementById('folderPickerOverlay');
  if (el && el.parentNode) el.parentNode.removeChild(el);
  document.removeEventListener('keydown', _pickerKeyHandler);
}

function _pickerKeyHandler(e) {
  if (e.key === 'Escape') _closePicker();
}

async function _browseTo(path) {
  var list = document.getElementById('folderPickerList');
  var crumbs = document.getElementById('folderPickerCrumbs');
  var current = document.getElementById('folderPickerCurrent');
  var overlay = document.getElementById('folderPickerOverlay');
  if (!list || !overlay) return;
  list.textContent = 'Loading…';
  try {
    var r = await fetch('/api/browse?path=' + encodeURIComponent(path || ''));
    var data = await r.json();
    if (!r.ok) {
      list.textContent = data.error || 'Unable to browse';
      return;
    }
    overlay.dataset.currentPath = data.path;
    current.textContent = data.path;
    crumbs.innerHTML = _renderCrumbs(data.path, data.home);
    if (!data.subdirs || data.subdirs.length === 0) {
      list.innerHTML = '<div class="folder-picker-empty">No subdirectories.</div>';
    } else {
      var html = '';
      if (data.parent) {
        html += '<div class="folder-picker-item folder-picker-parent" ' +
                'onclick="_browseTo(\'' + _escJs(data.parent) + '\')">⬑ .. (parent)</div>';
      }
      for (var i = 0; i < data.subdirs.length; i++) {
        var d = data.subdirs[i];
        html += '<div class="folder-picker-item" onclick="_browseTo(\'' + _escJs(d.path) + '\')">📁 ' + _escHtml(d.name) + '</div>';
      }
      list.innerHTML = html;
    }
  } catch (e) {
    list.textContent = 'Error: ' + e.message;
  }
}

function _renderCrumbs(fullPath, home) {
  var parts = fullPath.split('/').filter(Boolean);
  var html = '<span class="folder-picker-crumb" onclick="_browseTo(\'/\')">/</span>';
  var acc = '';
  for (var i = 0; i < parts.length; i++) {
    acc += '/' + parts[i];
    html += '<span class="folder-picker-crumb-sep">›</span>' +
            '<span class="folder-picker-crumb" onclick="_browseTo(\'' + _escJs(acc) + '\')">' + _escHtml(parts[i]) + '</span>';
  }
  if (home) {
    html += '<span class="folder-picker-crumb-sep">·</span>' +
            '<span class="folder-picker-crumb" onclick="_browseTo(\'' + _escJs(home) + '\')">~ Home</span>';
  }
  return html;
}

function _escHtml(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : String(s); return d.innerHTML; }
function _escJs(s) { return String(s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"); }
function _escAttr(s) { return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
