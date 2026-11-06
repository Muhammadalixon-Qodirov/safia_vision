"""Optional tiny live page: current IN/OUT, queue/staff counts and active alerts
per source. Read-only; it just polls the shared state the workers publish.
Run with `python run.py --web`."""
from __future__ import annotations

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Store analytics</title>
<style>
  body{font:16px system-ui,sans-serif;margin:0;background:#0f1419;color:#e6edf3}
  h1{font-size:20px;padding:16px 20px;margin:0;border-bottom:1px solid #222}
  .grid{display:grid;gap:14px;padding:20px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
  .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:16px}
  .name{font-weight:600;margin-bottom:10px}
  .row{display:flex;justify-content:space-between;padding:3px 0;color:#9aa4af}
  .row b{color:#e6edf3}
  .alert{margin-top:10px;background:#3d1418;color:#ff7b72;border-radius:6px;padding:6px 10px;font-weight:600}
  .ok{margin-top:10px;color:#3fb950}
</style></head><body>
<h1>Store camera analytics — live</h1>
<div class="grid" id="g">loading...</div>
<script>
async function tick(){
  try{
    const s = await (await fetch('/api/state')).json();
    const g = document.getElementById('g');
    const keys = Object.keys(s).sort();
    if(!keys.length){ g.textContent='no data yet'; return; }
    g.innerHTML = keys.map(k=>{
      const d = s[k];
      const al = (d.active_alerts||[]);
      const alert = al.length ? al.map(a=>`<div class="alert">ALERT: ${a}</div>`).join('')
                              : `<div class="ok">no alerts</div>`;
      return `<div class="card"><div class="name">${k}</div>
        <div class="row"><span>IN</span><b>${d.in??0}</b></div>
        <div class="row"><span>OUT</span><b>${d.out??0}</b></div>
        <div class="row"><span>queue</span><b>${d.queue??0}</b></div>
        <div class="row"><span>staff</span><b>${d.staff??0}</b></div>
        <div class="row"><span>fps</span><b>${d.fps??0}</b></div>
        ${alert}</div>`;
    }).join('');
  }catch(e){}
}
setInterval(tick, 1000); tick();
</script></body></html>"""


def serve(shared, host="127.0.0.1", port=8000):
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn

    app = FastAPI(title="store-analytics")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE

    @app.get("/api/state")
    def state():
        return JSONResponse(shared.snapshot())

    uvicorn.run(app, host=host, port=port, log_level="warning")
