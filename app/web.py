"""Bosqichma-bosqich o'quv UI (o'zbekcha).

Har bir funksiya alohida ekranda: yuqoridagi tugmalar (1..5) bilan o'tasiz. Har
ekranda: "Bu nima?", kerakli video, faqat shu funksiyaning katta raqamlari, va
"Hozir sinab ko'ring" ko'rsatmasi. Maqsad — funksiyalarni bittalab tushunish.

Backend endpointlari oldingidek: /api/state, /api/alerts, /stream/{name},
POST /api/control/{name}. Ishga tushirish:
`python run.py --config config/ui-demo.yaml --web`.
"""
from __future__ import annotations

import time

_ALLOWED = {"paused", "blur", "reset_seq", "queue_n", "queue_seconds", "empty_seconds"}

_PAGE = """<!doctype html>
<html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Do'kon analitikasi — o'quv</title>
<style>
  :root{color-scheme:dark}
  *{box-sizing:border-box}
  body{font:16px system-ui,sans-serif;margin:0;background:#0f1419;color:#e6edf3}
  header{padding:16px 20px 0}
  h1{font-size:19px;margin:0 0 12px}
  .tabs{display:flex;gap:8px;flex-wrap:wrap;border-bottom:1px solid #222;padding-bottom:12px}
  .tab{font:inherit;font-size:14px;background:#21262d;color:#cdd6e0;border:1px solid #3a4250;
    border-radius:9px;padding:8px 14px;cursor:pointer}
  .tab:hover{background:#2b323b}
  .tab.on{background:#1f6feb;border-color:#1f6feb;color:#fff;font-weight:600}
  .wrap{max-width:900px;margin:0 auto;padding:22px 20px 40px}
  .panel{display:none}
  .panel.active{display:block}
  h2{font-size:22px;margin:0 0 10px}
  .what{background:#132132;border:1px solid #1f3a57;border-radius:10px;padding:14px 16px;color:#b8c4d0;line-height:1.6;margin-bottom:16px}
  .feed{display:block;width:100%;max-width:760px;background:#000;aspect-ratio:16/9;object-fit:contain;border-radius:10px;margin:0 auto}
  .tiles{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin:16px 0}
  .tile{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px 26px;text-align:center;min-width:140px}
  .tile .v{font-size:44px;font-weight:700;line-height:1}
  .tile .l{color:#9aa4af;font-size:14px;margin-top:6px}
  .tile.green .v{color:#50dc50}.tile.red .v{color:#ff7b72}.tile.yellow .v{color:#f0d228}.tile.blue .v{color:#5aa9e6}
  .try{background:#1a2412;border:1px solid #2f4420;border-radius:10px;padding:14px 16px;color:#c8d9b8;line-height:1.6;margin-top:16px}
  .try b{color:#a6e27a}
  .status{font-size:22px;font-weight:700;text-align:center;margin:14px 0}
  .hot{color:#ff7b72}
  .ctrlrow{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:center;margin:12px 0}
  button.act{font:inherit;font-size:14px;background:#21262d;color:#e6edf3;border:1px solid #3a4250;border-radius:8px;padding:8px 14px;cursor:pointer}
  button.act:hover{background:#2b323b}
  button.act.on{background:#1f6feb;border-color:#1f6feb}
  .thbox{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:8px 16px;margin:14px 0}
  .th{display:flex;align-items:center;gap:10px;padding:8px 0;font-size:14px;color:#b8c4d0}
  .th label{flex:1}
  .th input{width:64px;background:#0d1117;color:#e6edf3;border:1px solid #3a4250;border-radius:7px;padding:6px 8px;font-size:16px}
  .eps{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:12px 16px;font-size:14px}
  .eps h4{margin:2px 0 8px;font-size:12px;text-transform:uppercase;color:#7d8590}
  .ep{color:#9aa4af;padding:3px 0}.ep b{color:#ff9d5c}
  .two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .two .feed{max-width:100%}
  .cap{text-align:center;color:#9aa4af;font-size:14px;margin-top:6px}
  @media(max-width:640px){.two{grid-template-columns:1fr}}
</style></head><body>
<header>
  <h1>Do'kon kamera analitikasi — funksiyalarni bittalab o'rganish</h1>
  <div class="tabs" id="tabs"></div>
</header>
<div class="wrap">

  <section class="panel active" data-tab="1">
    <h2>1 · Odam aniqlash va kuzatish</h2>
    <div class="what">Model videodagi har bir odamni topadi va ustiga yashil <b>ramka</b> hamda raqam (<b>#ID</b>) qo'yadi. Odam boshqa joyga yursa ham ID o'zgarmaydi — shuning uchun "kuzatish" deyiladi. Bu boshqa hamma funksiyaning poydevori.</div>
    <img class="feed" data-src="/stream/market-square" alt="">
    <div class="tiles"><div class="tile green"><div class="v" id="det-n">0</div><div class="l">hozir aniqlangan odam</div></div></div>
    <div class="ctrlrow"><button class="act on" id="btn-blur">🙈 Yuz blur: yoniq</button>
      <span style="color:#9aa4af;font-size:14px">Maxfiylik: yuzlar xiralashtiriladi (yuzni tanib olish YO'Q)</span></div>
    <div class="try"><b>Hozir sinab ko'ring:</b> videodagi yashil ramkalarga qarang — har bir odam alohida. "Yuz blur" tugmasini bosing — yuzlar xira bo'ladi/ochiladi.</div>
  </section>

  <section class="panel" data-tab="2">
    <h2>2 · Eshik hisobi — KIRDI / CHIQDI</h2>
    <div class="what">subway kamerasida yashil <b>chiziq</b> = eshik. Odam chiziqni kesib bir tomonga o'tsa <b>KIRDI</b>, teskari tomonga o'tsa <b>CHIQDI</b> +1 bo'ladi. Chiziqda to'xtab qolgan, orqaga qaytgan yoki chiziq bo'ylab yurgan odam <b>sanalmaydi</b>, va bitta o'tish ikki marta sanalmaydi.</div>
    <img class="feed" data-src="/stream/subway" alt="">
    <div class="tiles">
      <div class="tile green"><div class="v" id="cnt-in">0</div><div class="l">KIRDI</div></div>
      <div class="tile red"><div class="v" id="cnt-out">0</div><div class="l">CHIQDI</div></div>
    </div>
    <div class="ctrlrow"><button class="act" id="btn-reset2">↺ Nollash</button></div>
    <div class="try"><b>Hozir sinab ko'ring:</b> odam yashil chiziqni kesganda raqam oshadi. "<b>Nollash</b>" bosib 0 dan kuzating.</div>
  </section>

  <section class="panel" data-tab="3">
    <h2>3 · Zonalar — navbat va sotuvchi</h2>
    <div class="what">market-square kamerasida config'da ikki zona belgilangan: sariq = <b>navbat</b> (mijozlar turadigan joy), ko'k = <b>sotuvchi</b> (kassa). Har soniyada har zonada nechta odam borligi sanaladi. Bu raqamlar keyin alertlarga ishlatiladi.</div>
    <img class="feed" data-src="/stream/market-square" alt="">
    <div class="tiles">
      <div class="tile yellow"><div class="v" id="zon-q">0</div><div class="l">navbat zonasida</div></div>
      <div class="tile blue"><div class="v" id="zon-s">0</div><div class="l">sotuvchi zonasida</div></div>
    </div>
    <div class="try"><b>Hozir sinab ko'ring:</b> odamlar sariq zonaga kirsa "navbat" oshadi, ko'k zonaga kirsa "sotuvchi" oshadi.</div>
  </section>

  <section class="panel" data-tab="4">
    <h2>4 · Alertlar (ogohlantirishlar)</h2>
    <div class="what">Ikki ogohlantirish bor:<br>• <b>Navbat to'lgan</b>: navbat zonasida kamida <b>N</b> odam, kamida <b>T</b> soniya.<br>• <b>Bo'sh kassa</b>: sotuvchi zonasi kamida <b>T</b> soniya bo'sh, lekin navbatda kamida 1 odam bor.<br>Har alert bir marta chiqadi (miltillamaydi) va boshlanish/tugash/eng ko'p soni yoziladi.</div>
    <img class="feed" data-src="/stream/market-square" alt="">
    <div class="status" id="alr-status">—</div>
    <div class="thbox">
      <div class="th"><label>Navbat alerti: kamida N odam…</label><input type="number" id="th-n" min="1" max="12" step="1" value="3"></div>
      <div class="th"><label>…kamida T soniya davomida</label><input type="number" id="th-qs" min="0" max="60" step="1" value="3"></div>
      <div class="th"><label>Bo'sh kassa: sotuvchi zonasi T soniya bo'sh bo'lsa</label><input type="number" id="th-es" min="0" max="60" step="1" value="3"></div>
    </div>
    <div class="ctrlrow"><button class="act" id="btn-reset4">↺ Nollash</button></div>
    <div class="eps"><h4>Alert tarixi</h4><div id="alr-eps" class="ep">— hali yo'q —</div></div>
    <div class="try"><b>Hozir sinab ko'ring:</b> "<b>kamida N</b>" ni <b>8</b> qiling → navbatda 8 odam yo'q, alert o'chadi. <b>2</b> qiling → alert chiqadi. Alert tugagach tarixda boshlanish→tugash va eng ko'p soni bilan yoziladi.</div>
  </section>

  <section class="panel" data-tab="5">
    <h2>5 · Ko'p kamera bir vaqtda</h2>
    <div class="what">Bitta dastur bir vaqtning o'zida bir nechta kamerani qayta ishlaydi. Bittasi uzilib qolsa ham, boshqasi ishlashda davom etadi (crash bo'lmaydi). Har kameraning tezligi — <b>fps</b> (soniyasiga kadr).</div>
    <div class="two">
      <div><img class="feed" data-src="/stream/subway" alt=""><div class="cap" id="m-sub">subway</div></div>
      <div><img class="feed" data-src="/stream/market-square" alt=""><div class="cap" id="m-mkt">market-square</div></div>
    </div>
    <div class="try"><b>Hozir sinab ko'ring:</b> ikkala kamera bir vaqtda ishlayapti — fps raqamlariga qarang. <br><br><b>Chiqish fayllari:</b> har kamera uchun daqiqalik <b>CSV</b> va alert <b>JSONL</b> fayllari <code>output_ui/</code> papkasiga yoziladi. Bular UI emas — fayl (Safia shuni so'ragan).</div>
  </section>

</div>
<script>
const TABS = [[1,"1 · Odam aniqlash"],[2,"2 · Eshik hisobi"],[3,"3 · Zonalar"],[4,"4 · Alertlar"],[5,"5 · Ko'p kamera"]];
const ATYPE = {queue: "navbat to'lgan", empty_counter: "bo'sh kassa"};
let blurOn = true, rseq = {}, thInit = false;

const tabsEl = document.getElementById('tabs');
TABS.forEach(([n,label])=>{
  const b = document.createElement('button'); b.className='tab'+(n===1?' on':''); b.dataset.tab=n; b.textContent=label;
  b.onclick = ()=>show(n); tabsEl.appendChild(b);
});

function show(n){
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active', p.dataset.tab==String(n)));
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('on', b.dataset.tab==String(n)));
  document.querySelectorAll('.feed').forEach(img=>{
    const active = img.closest('.panel').dataset.tab==String(n);
    const want = active ? img.dataset.src : '';
    if(img.getAttribute('src')!==want) img.src = want;   // only active tab streams (closes others)
  });
}

async function post(name, body){
  try{ await fetch('/api/control/'+encodeURIComponent(name),
    {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); }catch(e){}
}
function set(id,v){ const e=document.getElementById(id); if(e) e.textContent=v; }
function setH(id,v){ const e=document.getElementById(id); if(e) e.innerHTML=v; }

// controls
document.getElementById('btn-blur').onclick = (e)=>{
  blurOn = !blurOn; e.target.classList.toggle('on', blurOn);
  e.target.textContent = blurOn ? '🙈 Yuz blur: yoniq' : '👁 Yuz blur: o\\'chiq';
  post('market-square', {blur: blurOn});
};
function reset(name){ rseq[name]=(rseq[name]||0)+1; post(name, {reset_seq: rseq[name]}); }
document.getElementById('btn-reset2').onclick = ()=>reset('subway');
document.getElementById('btn-reset4').onclick = ()=>reset('market-square');
function thnum(key, el){ const v=parseFloat(el.value); if(!isNaN(v)) post('market-square',{[key]:v}); }
document.getElementById('th-n').onchange  = (e)=>thnum('queue_n', e.target);
document.getElementById('th-qs').onchange = (e)=>thnum('queue_seconds', e.target);
document.getElementById('th-es').onchange = (e)=>thnum('empty_seconds', e.target);

async function tick(){
  let s, al;
  try{ s=await (await fetch('/api/state')).json(); al=await (await fetch('/api/alerts')).json(); }catch(e){ return; }
  const sub = s['subway']||{}, mkt = s['market-square']||{};
  set('det-n', mkt.n_people??0);
  set('cnt-in', sub.in??0); set('cnt-out', sub.out??0);
  set('zon-q', mkt.queue??0); set('zon-s', mkt.staff??0);

  const act = (mkt.active_alerts||[]).map(a=>ATYPE[a]||a);
  setH('alr-status', act.length ? `<span class="hot">🔴 Faol: ${act.join(', ')}</span>` : "🟢 Hozir alert yo'q");
  if(!thInit && mkt.queue_n!=null){
    document.getElementById('th-n').value=mkt.queue_n;
    document.getElementById('th-qs').value=mkt.queue_seconds;
    document.getElementById('th-es').value=mkt.empty_seconds; thInit=true;
  }
  const eps = al['market-square']||[];
  const rows = act.map(a=>`<div class="ep"><b>${a}</b> — <span class="hot">● hozir davom etmoqda</span></div>`)
    .concat(eps.slice(-6).reverse().map(e=>`<div class="ep"><b>${ATYPE[e.type]||e.type}</b> — ${e.start}s→${e.end}s (${e.duration}s), eng ko'p ${e.peak}</div>`));
  setH('alr-eps', rows.length ? rows.join('') : "— hali yo'q —");

  set('m-sub', `subway — fps ${sub.fps??0} · KIRDI ${sub.in??0} / CHIQDI ${sub.out??0}`);
  set('m-mkt', `market-square — fps ${mkt.fps??0} · navbat ${mkt.queue??0} / sotuvchi ${mkt.staff??0}`);
}
show(1); setInterval(tick, 1000); tick();
</script></body></html>"""


def serve(shared, host="127.0.0.1", port=8000):
    from fastapi import FastAPI, Body
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    import uvicorn

    app = FastAPI(title="store-analytics")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE

    @app.get("/api/state")
    def state():
        return JSONResponse(shared.snapshot())

    @app.get("/api/alerts")
    def alerts():
        return JSONResponse(shared.alerts_all())

    @app.post("/api/control/{name}")
    def control(name: str, body: dict = Body(default={})):
        clean = {k: body[k] for k in body if k in _ALLOWED}
        if clean:
            shared.set_control(name, **clean)
        return {"ok": True, "applied": clean}

    def mjpeg(name: str):
        while True:
            jpg = shared.get_frame(name)
            if jpg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            time.sleep(0.07)

    @app.get("/stream/{name}")
    def stream(name: str):
        return StreamingResponse(mjpeg(name),
                                 media_type="multipart/x-mixed-replace; boundary=frame")

    uvicorn.run(app, host=host, port=port, log_level="warning")
