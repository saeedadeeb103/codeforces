// Small progressive enhancements; every page works without JavaScript.
(() => {
  // Filters submit as soon as you change them (search waits for a pause in typing).
  document.querySelectorAll("form[data-autosubmit]").forEach((form) => {
    let t;
    form.addEventListener("change", () => form.requestSubmit());
    form.querySelectorAll('input[type="search"]').forEach((input) =>
      input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => form.requestSubmit(), 450); })
    );
  });

  // Keep scroll position when ticking problems on the dashboard or the list.
  const key = "scroll:" + location.pathname + location.search;
  document.querySelectorAll("form.check-form").forEach((f) =>
    f.addEventListener("submit", () => { try { sessionStorage.setItem(key, String(scrollY)); } catch {} })
  );
  try {
    const y = sessionStorage.getItem(key);
    if (y !== null && !location.hash) scrollTo(0, Number(y));
    sessionStorage.removeItem(key);
  } catch {}

  // Keep the cursor at the end of the search box after an auto-submit.
  const search = document.querySelector('input[type="search"]');
  if (search && search.value) { search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
})();
