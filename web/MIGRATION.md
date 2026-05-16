# Web 迁移交接 — legacy JS / CSS 收尾

新会话直接说「读 web/MIGRATION.md,继续」即可。

分支:`phase3-message-flip`。本地:`web` 跑在 `:3000`,backend `:8109`。
开发流程:改源码 → `cd web && npm run build` → 在仓库根
`OPENPROGRAM_WEB_PORT=3000 python -m openprogram worker restart`。

---

## 已完成

`public/js/` 原本 11 个 legacy 文件,现在只剩 1 个。已迁移到 `web/lib/`:

```
public/js/chat/chat.js        → lib/chat-handlers.ts
public/js/chat/chat-ws.js     → lib/chat-handlers.ts
public/js/chat/init.js        → lib/chat-handlers.ts
public/js/shared/conversations.js → lib/conversations.ts
public/js/shared/providers.js     → lib/providers.ts
public/js/shared/programs-panel.js→ lib/programs-panel.ts
public/js/shared/scrollbar.js     → lib/scrollbar.ts
public/js/shared/helpers.js       → lib/helpers.ts
public/js/shared/ui.js            → lib/ui.ts
public/js/shared/state.js         → lib/state.ts
```

迁移模式:每个 TS 模块把函数 export 给 `useWS` / 其它 TS 直接调用,
同时仍 `window.*` 桥接,供唯一剩下的 legacy 脚本 history-graph.js 和
inline-onclick HTML 调用。`useWS` 直接 import handler;其余模块由
`app-shell.tsx` 顶部 `import "@/lib/..."` 按 state→helpers→ui→providers→
programs-panel 顺序做 side-effect 导入。`SHARED_JS` 现在只剩
`["shared/history-graph.js"]`。

WebSocket 连接 + 25 种消息分发都在 `lib/use-ws.ts`。`useWS` 在
`__sharedScriptsReady` resolve 后才 connect —— 否则 connect 早于
history-graph.js 加载,且 initChatPage 依赖的 window 函数还没装好。

全部 build 过、浏览器实测过(发普通 chat / `/run` / 加载历史会话 /
切分支 / 选 channel / 打开 fn-form / code modal)。

---

## 还剩什么

### 1. history-graph.js → lib/history-graph.ts

`public/js/shared/history-graph.js`(1308 行,单个 IIFE)是右栏
History DAG 的 SVG 渲染器。自包含,通过 `window.*` 暴露
`renderHistoryGraph` / `repaintBranchTags` / `setHistoryContextRange`
/ `refreshHistoryContextRange` / `recomputeHistoryVisibility`,被
`conversations.ts` 经 `W.renderHistoryGraph` 调用。

它读 bare global(`trees` / `conversations` / `selectedPath` /
`expandedNodes` / `_nodeCache` 等)—— 这些由 `lib/state.ts` 装到
`window.*`,bare 标识符回退到 global object 所以能读到。

迁移方式:照 ui.ts / conversations.ts 的模式,faithful 端口成
`lib/history-graph.ts`,把 5 个 `window.*` 函数 export + 桥接,
`app-shell.tsx` 加 `import "@/lib/history-graph"`,从 `SHARED_JS`
删掉(变成空数组,可顺手把 app-shell 里 SHARED_JS 的 fetch/inject
逻辑一并删掉)。迁完 `public/js/` 整个目录可删。

### 2. legacy CSS → 组件级 CSS module

`app/styles/*.css`(约 2500 行全局 CSS,经 `app/styles.css` →
`app/globals.css` 导入):

```
01-base.css       270  :root tokens / reset / 基础排版
02-sidebar.css    137  侧栏
03-settings.css    96
05-chat.css      1324  聊天区(最大)
06-detail.css     199  右栏 detail
08-dropdown.css   163
09-right-dock.css  304
```

要拆进各 React 组件的 co-located `*.module.css` / Tailwind。
注意:`01-base.css` 的 `:root` token(`--bg-*` / `--accent-*` /
`--text-*` / 几何量)是全局的,**保留为全局**(组件 module 都依赖
这些 CSS 变量);只迁组件专属的类规则。`html { font-size: 14px }`
使 Tailwind rem 缩放 0.875×,arbitrary px 值要锁死。

---

## 注意的坑

- `git add` 明确列文件,别 `git add -A`(仓库有会话前就存在的无关改动)。
- 改 `public/js/*` 不用 build;改 `lib/` / 组件要 build + worker restart。
- 移除 `SHARED_JS` 条目时,确认同时 `git rm` 文件、别留悬空条目
  (scrollbar 那次就是留了条目导致 404 → PageShell setErr)。
