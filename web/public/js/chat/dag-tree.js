// ===== DAG tree fetcher =====
//
// Pull one session's @agentic_function execution forest from the
// backend (which reads SQLite directly) and hand it to the existing
// `trees` state + render pipeline. Replaces the WebSocket-pushed
// `context_tree` field that came from the retired tree-Context
// event system.
//
// Stays tiny and side-effect-only:
//   - one fetch
//   - one state update (`trees` global)
//   - calls into the existing render helpers
// No tree-shape munging or rendering logic here; that lives in
// tree.js / tree-render.js.

(function () {
  function fetchSessionDagTree(sessionId) {
    if (!sessionId) return Promise.resolve(null);
    return fetch('/api/sessions/' + encodeURIComponent(sessionId) + '/dag-tree')
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.trees)) return null;
        applyDagTrees(sessionId, data.trees);
        return data.trees;
      })
      .catch(function () { return null; });
  }

  function applyDagTrees(sessionId, treeList) {
    // The viewer only renders the currently-open session's forest.
    // Skip silently if the user navigated away mid-fetch.
    if (sessionId !== currentSessionId) return;
    trees.length = 0;
    Array.prototype.push.apply(trees, treeList);
    // Mirror onto the conversation so a later session switch can
    // restore without an extra round-trip.
    if (conversations[sessionId]) {
      conversations[sessionId].trees = treeList;
    }
    treeList.forEach(function (t) {
      var key = (t && (t.path || t.name)) || null;
      if (key) expandedNodes.add(key);
    });
    if (typeof refreshInlineTrees === 'function') {
      refreshInlineTrees();
    }
  }

  window.fetchSessionDagTree = fetchSessionDagTree;
  window.applyDagTrees = applyDagTrees;
})();
