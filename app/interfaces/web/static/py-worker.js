// Runs Python 3 (Pyodide/WebAssembly) inside the browser. Nothing is executed on the server.
/* global loadPyodide */
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

const RUNNER = `
import sys, io, time, traceback

def __cft_run(src, data):
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = io.StringIO(data), out, err
    ok = True
    start = time.perf_counter()
    try:
        exec(compile(src, "solution.py", "exec"), {"__name__": "__main__"})
    except SystemExit as e:
        ok = e.code in (None, 0)
    except BaseException:
        ok = False
        lines = traceback.format_exc().splitlines()
        # drop the runner's own frame so the trace starts at your code
        keep = [l for i, l in enumerate(lines) if "__cft_run" not in l and not (i > 0 and "__cft_run" in lines[i - 1] and l.startswith("    "))]
        err.write("\\n".join(keep))
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved
    ms = (time.perf_counter() - start) * 1000
    text = out.getvalue()
    if len(text) > 100_000:
        text = text[:100_000] + "\\n… output truncated"
    return ok, text, err.getvalue()[-20_000:], ms
`;

let pyReady = (async () => {
  try {
    importScripts(PYODIDE + "pyodide.js");
    const py = await loadPyodide({ indexURL: PYODIDE });
    py.runPython(RUNNER);
    self.postMessage({ type: "ready" });
    return py;
  } catch (e) {
    self.postMessage({ type: "load-error", message: String(e && e.message || e) });
    throw e;
  }
})();

self.onmessage = async (e) => {
  const { type, id, code, input } = e.data || {};
  if (type !== "run") return;
  let py;
  try { py = await pyReady; } catch { return; }
  const fn = py.globals.get("__cft_run");
  let res;
  try {
    res = fn(code, input || "");
    const [ok, out, err, ms] = res.toJs();
    self.postMessage({ type: "result", id, ok, out, err, ms });
  } catch (err) {
    self.postMessage({ type: "result", id, ok: false, out: "", err: String(err && err.message || err), ms: 0 });
  } finally {
    if (res && res.destroy) res.destroy();
    fn.destroy();
  }
};
