// Small progressive enhancements; every page works without JavaScript.
(() => {
  // Filters submit as soon as you change them.
  document.querySelectorAll("form[data-autosubmit]").forEach((form) => {
    form.addEventListener("change", () => form.requestSubmit());
  });

  // Tab inserts 4 spaces in the code editor instead of leaving the field.
  document.querySelectorAll("textarea.code-input").forEach((ta) => {
    ta.addEventListener("keydown", (e) => {
      if (e.key !== "Tab" || e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
      const { selectionStart: s, selectionEnd: end, value } = ta;
      ta.value = value.slice(0, s) + "    " + value.slice(end);
      ta.selectionStart = ta.selectionEnd = s + 4;
    });
  });

  // Cmd/Ctrl+S saves the problem form.
  const work = document.getElementById("work-form");
  if (work) {
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        work.requestSubmit();
      }
    });
    // Warn before leaving with unsaved edits.
    let dirty = false;
    work.addEventListener("input", () => { dirty = true; });
    work.addEventListener("submit", () => { dirty = false; });
    window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
  }

  // Keep scroll position when ticking problems on the dashboard or plan.
  const key = "scroll:" + location.pathname;
  document.querySelectorAll("form.check-form").forEach((f) =>
    f.addEventListener("submit", () => { try { sessionStorage.setItem(key, String(scrollY)); } catch {} })
  );
  try {
    const y = sessionStorage.getItem(key);
    if (y !== null && !location.hash) { scrollTo(0, Number(y)); }
    sessionStorage.removeItem(key);
  } catch {}
})();
