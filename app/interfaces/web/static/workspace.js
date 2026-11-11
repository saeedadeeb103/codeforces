// Problem workspace: editor, background saves, resizable panes, stopwatch, test runner.
// Rule: the <textarea name="solution"> is the source of truth. The editor only writes into it
// after it has loaded, so a failed CDN load can never save an empty solution.
(() => {
  "use strict";
  const form = document.getElementById("work-form");
  if (!form) return;

  const CODE = form.dataset.code;
  const MONACO = "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min";
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
  };
  const session = {
    get(key, fallback) { try { const v = sessionStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
    set(key, value) { try { sessionStorage.setItem(key, JSON.stringify(value)); } catch {} },
  };

  // ---------------------------------------------------------------- toast
  const toastEl = $("#toast");
  let toastTimer;
  function toast(msg, isError = false) {
    toastEl.textContent = msg;
    toastEl.classList.toggle("is-error", isError);
    toastEl.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("is-on"), isError ? 6000 : 2200);
  }

  // ---------------------------------------------------------------- tabs
  $$("[data-tabs]").forEach((bar) => {
    const key = "tab:" + bar.dataset.tabs;
    const buttons = Array.from(bar.querySelectorAll("[data-tab]"));
    const show = (id) => {
      buttons.forEach((b) => {
        const on = b.dataset.tab === id;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
        document.getElementById(b.dataset.tab).hidden = !on;
      });
    };
    bar.show = show;
    buttons.forEach((b) => b.addEventListener("click", () => { show(b.dataset.tab); if (bar.dataset.tabs === "left") store.set(key, b.dataset.tab); }));
    if (bar.dataset.tabs === "left") {
      const saved = store.get(key, null);
      if (saved && document.getElementById(saved)) show(saved);
    }
  });
  const consoleTabs = $('[data-tabs="console"]');

  // ---------------------------------------------------------------- saving
  const stateEl = $("#save-state");
  const solutionTa = $("#solution");
  let editor = null;
  let dirty = false;
  let inflight = null;
  let autosaveTimer;

  function setState(kind, text) {
    stateEl.className = "save-state is-" + kind;
    stateEl.textContent = text;
  }
  function syncEditor() {
    if (editor) solutionTa.value = editor.getValue();
  }
  function markDirty() {
    dirty = true;
    setState("dirty", "Unsaved");
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => save(), 2000);
  }

  form.addEventListener("input", (e) => { if (e.target.name) markDirty(); });
  form.addEventListener("change", (e) => { if (e.target.name && e.target.name !== "status") markDirty(); });

  async function save(status) {
    if (inflight) { await inflight.catch(() => {}); }
    clearTimeout(autosaveTimer);
    syncEditor();
    const data = new FormData(form);
    data.delete("status");
    if (status) data.set("status", status);
    setState("dirty", "Saving…");
    inflight = (async () => {
      let res, body = null;
      try {
        res = await fetch(form.action, {
          method: "POST",
          body: new URLSearchParams(data),
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if ((res.headers.get("content-type") || "").includes("application/json")) body = await res.json();
      } catch {
        setState("error", "Offline — not saved");
        toast("Couldn't reach the server. Your code is still here; press ⌘/Ctrl+S to retry.", true);
        return false;
      }
      if (res.status === 401) {
        setState("error", "Not saved — log in");
        toast("Your session expired. Log in again in another tab, then press ⌘/Ctrl+S here.", true);
        return false;
      }
      if (!res.ok || !body || body.ok !== true) {
        setState("error", "Not saved");
        toast((body && body.error) || "Couldn't save. Try again.", true);
        return false;
      }
      dirty = false;
      setState("ok", "Saved");
      applyStatus(body);
      return true;
    })();
    try { return await inflight; } finally { inflight = null; }
  }

  function applyStatus(body) {
    $$(".seg").forEach((b) => {
      const on = b.value === body.status;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    const done = body.status === "solved" || body.status === "review";
    const flag = $("#solved-flag");
    flag.hidden = !done;
    const field = $("#solved-on-field");
    const input = $("#solved-on");
    field.hidden = !done;
    input.disabled = !done;
    if (done && body.solved_on) {
      input.value = body.solved_on;
      const d = new Date(body.solved_on + "T00:00:00");
      flag.querySelector("span").textContent = "Solved " + d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    }
    $("#minutes").value = body.minutes;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = e.submitter && e.submitter.name === "status" ? e.submitter.value : null;
    if (status === "solved" || status === "review") stopTimer(true);
    const ok = await save(status);
    if (ok && status) {
      const label = { todo: "To do", attempted: "Attempted", solved: "Solved", review: "Review again" }[status];
      toast(status === "solved" ? "Nice! Marked as solved ✓" : "Status: " + label);
    } else if (ok) {
      toast("Saved");
    }
  });

  document.addEventListener("keydown", (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); save().then((ok) => ok && toast("Saved")); }
    if (mod && e.key === "Enter") { e.preventDefault(); run(); }
  });

  window.addEventListener("beforeunload", (e) => {
    if (dirty || inflight) { e.preventDefault(); e.returnValue = ""; }
  });
  // Best effort: flush on tab hide (e.g. closing the laptop).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && dirty) {
      syncEditor();
      const data = new FormData(form);
      data.delete("status");
      try { navigator.sendBeacon(form.action, new URLSearchParams(data)); dirty = false; } catch {}
    }
  });

  // ---------------------------------------------------------------- editor
  const langSel = $("#language");
  const monacoLang = (v) => ({ python: "python", cpp: "cpp", java: "java", kotlin: "kotlin", go: "go", rust: "rust", javascript: "javascript" }[v] || "plaintext");
  const cursorEl = $("#cursor-pos");

  // Plain textarea niceties (used on phones or if the editor can't load).
  solutionTa.addEventListener("keydown", (e) => {
    if (e.key !== "Tab" || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return;
    e.preventDefault();
    const { selectionStart: s, selectionEnd: end, value } = solutionTa;
    solutionTa.value = value.slice(0, s) + "    " + value.slice(end);
    solutionTa.selectionStart = solutionTa.selectionEnd = s + 4;
    markDirty();
  });

  function initMonaco() {
    window.MonacoEnvironment = {
      getWorkerUrl: () => "data:text/javascript;charset=utf-8," + encodeURIComponent(
        `self.MonacoEnvironment={baseUrl:'${MONACO}/'};importScripts('${MONACO}/vs/base/worker/workerMain.js');`),
    };
    window.require.config({ paths: { vs: MONACO + "/vs" } });
    window.require(["vs/editor/editor.main"], () => {
      const m = window.monaco;
      m.editor.defineTheme("cft", {
        base: "vs-dark", inherit: true, rules: [],
        colors: {
          "editor.background": "#262626",
          "editorGutter.background": "#262626",
          "editor.lineHighlightBackground": "#ffffff08",
          "editor.lineHighlightBorder": "#00000000",
          "editorLineNumber.foreground": "#5c5f66",
          "editorLineNumber.activeForeground": "#c9ccd3",
          "editorIndentGuide.background1": "#ffffff10",
          "scrollbarSlider.background": "#ffffff18",
        },
      });
      editor = m.editor.create(document.getElementById("monaco"), {
        value: solutionTa.value,
        language: monacoLang(langSel.value),
        theme: "cft",
        automaticLayout: true,
        fontFamily: "'JetBrains Mono', Menlo, monospace",
        fontSize: 14,
        lineHeight: 22,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        tabSize: 4,
        padding: { top: 12, bottom: 12 },
        smoothScrolling: true,
        bracketPairColorization: { enabled: true },
        renderLineHighlight: "line",
        overviewRulerBorder: false,
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
      });
      document.getElementById("editor-host").classList.add("has-monaco");
      editor.onDidChangeModelContent(() => { solutionTa.value = editor.getValue(); markDirty(); });
      editor.onDidChangeCursorPosition((e) => { cursorEl.textContent = `Ln ${e.position.lineNumber}, Col ${e.position.column}`; });
      editor.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.KeyS, () => save().then((ok) => ok && toast("Saved")));
      editor.addCommand(m.KeyMod.CtrlCmd | m.KeyCode.Enter, () => run());
      langSel.addEventListener("change", () => m.editor.setModelLanguage(editor.getModel(), monacoLang(langSel.value)));
      if (!solutionTa.value) editor.focus();
    }, () => { /* keep the textarea */ });
  }

  const touch = window.matchMedia("(pointer: coarse)").matches;
  if (!touch) {
    const s = document.createElement("script");
    s.src = MONACO + "/vs/loader.js";
    s.onload = initMonaco;
    s.onerror = () => { /* textarea stays visible and usable */ };
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------- resizable panes
  const desktop = window.matchMedia("(min-width: 901px)");
  const sizes = store.get("ws:sizes", {});
  if (sizes.left) form.style.setProperty("--left-w", sizes.left + "%");
  if (sizes.console) form.style.setProperty("--console-h", sizes.console + "%");

  function drag(gutter, onMove) {
    gutter.addEventListener("pointerdown", (e) => {
      if (!desktop.matches) return;
      e.preventDefault();
      gutter.setPointerCapture(e.pointerId);
      gutter.classList.add("is-drag");
      document.body.classList.add("is-resizing");
      const move = (ev) => onMove(ev);
      const up = () => {
        gutter.classList.remove("is-drag");
        document.body.classList.remove("is-resizing");
        gutter.removeEventListener("pointermove", move);
        gutter.removeEventListener("pointerup", up);
        store.set("ws:sizes", sizes);
      };
      gutter.addEventListener("pointermove", move);
      gutter.addEventListener("pointerup", up);
    });
  }
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  drag($('[data-gutter="v"]'), (e) => {
    const box = form.getBoundingClientRect();
    sizes.left = clamp(((e.clientX - box.left) / box.width) * 100, 22, 70);
    form.style.setProperty("--left-w", sizes.left + "%");
  });
  drag($('[data-gutter="h"]'), (e) => {
    const col = $(".ws-right-col").getBoundingClientRect();
    sizes.console = clamp(((col.bottom - e.clientY) / col.height) * 100, 8, 80);
    form.style.setProperty("--console-h", sizes.console + "%");
  });

  // ---------------------------------------------------------------- stopwatch
  const timerBtn = $("#timer");
  const timerLabel = timerBtn.querySelector("span");
  const timerKey = "timer:" + CODE;
  let t = session.get(timerKey, { start: null, acc: 0 });
  const elapsed = () => t.acc + (t.start ? Date.now() - t.start : 0);
  const fmt = (ms) => {
    const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return (h ? h + ":" + pad(m) : pad(m)) + ":" + pad(sec);
  };
  function paint() {
    timerLabel.textContent = fmt(elapsed());
    timerBtn.classList.toggle("is-running", !!t.start);
  }
  function stopTimer(log) {
    if (!t.start && !t.acc) return;
    const ms = elapsed();
    t = { start: null, acc: 0 };
    session.set(timerKey, t);
    paint();
    if (log && ms >= 30000) {
      const mins = Math.max(1, Math.round(ms / 60000));
      const input = $("#minutes");
      input.value = (parseInt(input.value, 10) || 0) + mins;
      markDirty();
      toast(`Logged ${mins} min to this problem`);
    }
  }
  timerBtn.addEventListener("click", () => {
    if (t.start) { stopTimer(true); return; }
    t = { start: Date.now(), acc: t.acc };
    session.set(timerKey, t);
    paint();
  });
  setInterval(() => { if (t.start) paint(); }, 1000);
  paint();

  // ---------------------------------------------------------------- test cases
  const casesKey = "cases:" + CODE;
  let cases = store.get(casesKey, null) || [{ input: "", expected: "" }];
  let active = 0;
  let lastResults = [];
  const caseTabs = $("#case-tabs");
  const caseInput = $("#case-input");
  const caseExpected = $("#case-expected");

  function renderCases() {
    caseTabs.innerHTML = "";
    cases.forEach((c, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "case-tab" + (i === active ? " is-active" : "");
      const r = lastResults[i];
      if (r) { const dot = document.createElement("span"); dot.className = "dot " + (r.pass ? "ok" : "bad"); b.appendChild(dot); }
      b.appendChild(document.createTextNode("Case " + (i + 1)));
      if (cases.length > 1) {
        const x = document.createElement("span");
        x.className = "x"; x.textContent = "×"; x.title = "Remove case";
        x.addEventListener("click", (e) => { e.stopPropagation(); cases.splice(i, 1); lastResults = []; active = Math.min(active, cases.length - 1); persistCases(); renderCases(); });
        b.appendChild(x);
      }
      b.addEventListener("click", () => { active = i; renderCases(); });
      caseTabs.appendChild(b);
    });
    if (cases.length < 10) {
      const add = document.createElement("button");
      add.type = "button"; add.className = "case-tab"; add.title = "Add a test case"; add.textContent = "+";
      add.addEventListener("click", () => { cases.push({ input: "", expected: "" }); active = cases.length - 1; persistCases(); renderCases(); caseInput.focus(); });
      caseTabs.appendChild(add);
    }
    caseInput.value = cases[active].input;
    caseExpected.value = cases[active].expected;
  }
  function persistCases() { store.set(casesKey, cases); }
  caseInput.addEventListener("input", () => { cases[active].input = caseInput.value; persistCases(); });
  caseExpected.addEventListener("input", () => { cases[active].expected = caseExpected.value; persistCases(); });
  renderCases();

  // ---------------------------------------------------------------- runner (Python in a Web Worker)
  const runButtons = $$("[data-run]");
  const resultEl = $("#result");
  const resultEmpty = $("#result-empty");
  const TIME_LIMIT_MS = 10000;
  let worker = null;
  let workerReady = null;
  let running = false;

  function updateRunAvailability() {
    const isPy = langSel.value === "python";
    runButtons.forEach((b) => { b.disabled = !isPy || running; b.title = isPy ? "Run your code on the test cases (⌘/Ctrl + Enter)" : "Run works for Python only"; });
  }
  langSel.addEventListener("change", updateRunAvailability);
  updateRunAvailability();

  function getWorker() {
    if (worker) return workerReady;
    worker = new Worker("/static/py-worker.js");
    workerReady = new Promise((resolve, reject) => {
      const onMsg = (e) => {
        if (e.data.type === "ready") { worker.removeEventListener("message", onMsg); resolve(worker); }
        if (e.data.type === "load-error") { worker.removeEventListener("message", onMsg); killWorker(); reject(new Error(e.data.message)); }
      };
      worker.addEventListener("message", onMsg);
      worker.addEventListener("error", () => { killWorker(); reject(new Error("Python failed to load")); });
    });
    return workerReady;
  }
  function killWorker() { if (worker) worker.terminate(); worker = null; workerReady = null; }

  let jobId = 0;
  function runOne(w, code, input) {
    return new Promise((resolve) => {
      const id = ++jobId;
      const timer = setTimeout(() => { w.removeEventListener("message", onMsg); killWorker(); resolve({ timeout: true }); }, TIME_LIMIT_MS);
      const onMsg = (e) => {
        if (e.data.type !== "result" || e.data.id !== id) return;
        clearTimeout(timer);
        w.removeEventListener("message", onMsg);
        resolve(e.data);
      };
      w.addEventListener("message", onMsg);
      w.postMessage({ type: "run", id, code, input });
    });
  }

  const normalize = (s) => s.replace(/\r\n/g, "\n").split("\n").map((l) => l.replace(/\s+$/, "")).join("\n").replace(/\n+$/, "");
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function run() {
    if (running) return;
    if (langSel.value !== "python") { toast("Run works for Python only. Switch the language to Python 3.", true); return; }
    syncEditor();
    const code = solutionTa.value;
    if (!code.trim()) { toast("Write some code first.", true); return; }
    running = true;
    updateRunAvailability();
    consoleTabs.show("pane-result");
    resultEmpty.hidden = true;
    resultEl.hidden = false;
    resultEl.innerHTML = `<div class="result-head"><span class="spinner"></span><span>${worker ? "Running…" : "Loading Python (first run takes a few seconds)…"}</span></div>`;
    let w;
    try { w = await getWorker(); }
    catch (err) {
      resultEl.innerHTML = `<div class="result-head"><strong class="bad">Couldn't load Python</strong></div><pre class="io-box is-err">${esc(String(err.message || err))}</pre>`;
      running = false; updateRunAvailability(); return;
    }
    resultEl.innerHTML = `<div class="result-head"><span class="spinner"></span><span>Running…</span></div>`;
    const results = [];
    for (const c of cases) {
      const r = await runOne(w, code, c.input);
      const hasExpected = c.expected.trim() !== "";
      const pass = !r.timeout && r.ok && (!hasExpected || normalize(r.out) === normalize(c.expected));
      results.push({ ...r, pass, hasExpected, input: c.input, expected: c.expected });
      if (r.timeout) { try { w = await getWorker(); } catch { break; } }
    }
    lastResults = results;
    renderCases();
    showResults(results, 0);
    running = false;
    updateRunAvailability();
  }
  runButtons.forEach((b) => b.addEventListener("click", run));

  function showResults(results, idx) {
    const anyTimeout = results.some((r) => r.timeout);
    const anyError = results.some((r) => !r.timeout && !r.ok);
    const compared = results.filter((r) => r.hasExpected);
    const allPass = results.every((r) => r.pass);
    let head, cls;
    if (anyTimeout) { head = "Time limit (10 s)"; cls = "warn"; }
    else if (anyError) { head = "Runtime error"; cls = "bad"; }
    else if (!compared.length) { head = "Finished"; cls = "ok"; }
    else if (allPass) { head = "Output matches expected"; cls = "ok"; }
    else { head = "Output doesn't match"; cls = "bad"; }
    const ms = Math.max(...results.map((r) => r.ms || 0));
    const tabs = results.map((r, i) => `<button type="button" class="case-tab${i === idx ? " is-active" : ""}" data-res="${i}"><span class="dot ${r.pass ? "ok" : "bad"}"></span>Case ${i + 1}</button>`).join("");
    const r = results[idx];
    const box = (label, text, err = false) => `<div class="case-field"><label>${label}</label><pre class="io-box${err ? " is-err" : ""}">${esc(text || "") || "&nbsp;"}</pre></div>`;
    let body = box("Input", r.input);
    if (r.timeout) body += box("Output", "Stopped after 10 seconds — infinite loop or too slow?", true);
    else {
      body += box("Output", r.out);
      if (r.hasExpected) body += box("Expected", r.expected);
      if (r.err) body += box(r.ok ? "Stderr" : "Error", r.err, !r.ok);
    }
    resultEl.innerHTML = `<div class="result-head"><strong class="${cls}">${head}</strong>${anyTimeout ? "" : `<span>Runtime: ${ms.toFixed(0)} ms · in your browser</span>`}</div>
      <div class="case-tabs">${tabs}</div>${body}`;
    resultEl.querySelectorAll("[data-res]").forEach((b) => b.addEventListener("click", () => showResults(results, +b.dataset.res)));
  }
})();
