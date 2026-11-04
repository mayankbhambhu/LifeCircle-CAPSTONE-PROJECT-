// Live-demo transport: starts Python (Pyodide) in the browser and runs the
// real LifeCircle FastAPI app there. Used only by the GitHub Pages build.
const PYODIDE_VERSION = "314.0.7";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

window.LC_BACKEND = (() => {
  let call;
  const status = (msg) => {
    const el = document.getElementById("app");
    if (el) el.innerHTML = `<div class="card" style="text-align:center;margin-top:40px">
      <h2 style="margin-top:0">Starting LifeCircle…</h2><p class="muted">${msg}</p>
      <p class="label">The real Python backend runs inside your browser. First load takes 10 to 30 seconds.</p></div>`;
  };
  const ready = (async () => {
    status("Downloading Python");
    await new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = PYODIDE_URL + "pyodide.js"; s.onload = ok; s.onerror = () => fail(new Error("Could not load Python runtime"));
      document.head.appendChild(s);
    });
    const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
    status("Installing FastAPI and SQLAlchemy");
    await pyodide.loadPackage(["fastapi", "sqlalchemy", "pydantic"]);
    status("Loading LifeCircle code");
    const files = await (await fetch("py/manifest.json")).json();
    for (const f of files) {
      const text = await (await fetch("py/" + f)).text();
      const full = "/home/pyodide/lifecircle/" + f;
      pyodide.FS.mkdirTree(full.substring(0, full.lastIndexOf("/")));
      pyodide.FS.writeFile(full, text);
    }
    status("Seeding demo donors");
    await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, "/home/pyodide/lifecircle")
import app.browser
`);
    call = pyodide.pyimport("app.browser").call;
  })();
  return {
    ready,
    async request(method, path, auth, body) {
      await ready;
      const res = await call(method, path, auth || "", body || "");
      const [s, text] = res.toJs();
      res.destroy();
      return { status: s, text };
    },
  };
})();
