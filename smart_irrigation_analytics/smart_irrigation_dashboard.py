import json
import os
import urllib.error
import urllib.request
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:3000").rstrip("/")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32_soil_001")

PAGE = r'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Irrigation Monitor</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#142238;--muted:#91a2b9;--text:#edf4ff;--line:#293b53;--green:#46d39a;--red:#ff737d}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0%,#1b3047 0,transparent 48%),var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}
main{max-width:1050px;margin:auto;padding:30px 18px}header{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:24px}
h1{font-size:clamp(24px,4vw,34px);margin:0}h2{font-size:17px;margin:0 0 14px}.muted,.sub{color:var(--muted)}.sub{margin-top:4px}
.pill,.status{border:1px solid var(--line);border-radius:99px;padding:6px 11px;font-size:12px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#8795a8;margin-right:7px}.dot.ok{background:var(--green)}.dot.bad{background:var(--red)}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.card{background:linear-gradient(145deg,#172941,#111d2e);border:1px solid var(--line);border-radius:16px;padding:19px;box-shadow:0 12px 32px #0002}
.label{color:var(--muted);font-size:13px;margin-bottom:8px}.metric{font-size:clamp(27px,4vw,38px);font-weight:700;letter-spacing:-1px}.unit{font-size:14px;color:var(--muted);font-weight:500}
.status{display:inline-block;margin-top:9px;background:#26374b}.status.dry{background:#48262c;color:#ff9da4}.status.wet{background:#173d35;color:#83e8bd}
.section{margin-top:16px}.chart{height:260px}.chart canvas{width:100%;height:100%;display:block}.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.meta .card{padding:14px 17px}.meta strong{display:block;margin-top:4px;font-size:14px;overflow-wrap:anywhere}
.error{color:#ff9da4;min-height:22px;margin-top:12px;font-size:13px}footer{color:var(--muted);font-size:12px;margin-top:18px}
.analytics-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}.analytics-head h2{margin:0}
select{background:#0e1929;color:var(--text);border:1px solid var(--line);border-radius:9px;padding:8px 11px;font:inherit}
.analytics-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.analytics-grid .card{padding:15px 16px}.analytics-grid .metric{font-size:28px}
.analytics-lower{display:grid;grid-template-columns:1.5fr 1fr;gap:13px;margin-top:13px}.bar-track{height:13px;background:#27384e;border-radius:99px;overflow:hidden;display:flex;margin:12px 0 8px}.bar-dry{background:#ff737d}.bar-wet{background:#46d39a}.legend{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:var(--muted)}.insights{display:grid;gap:9px}.insight{padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#101d2e;color:#dce8f7;font-size:13px}.trend-up{color:#ff9da4}.trend-down{color:#83e8bd}.trend-flat{color:#a9c4e8}
@media(max-width:850px){.analytics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.analytics-lower{grid-template-columns:1fr}}
@media(max-width:700px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.meta{grid-template-columns:1fr}}@media(max-width:420px){main{padding:20px 12px}.card{padding:14px}.analytics-grid{gap:9px}.analytics-grid .metric{font-size:24px}}
</style></head>
<body><main>
<header><div><h1>Smart Irrigation Monitor</h1><div class="sub">Soil sensor telemetry · <span id="deviceId"></span></div></div><div class="pill"><span id="apiDot" class="dot"></span><span id="apiText">Checking backend…</span></div></header>
<section class="grid">
<div class="card"><div class="label">Soil moisture</div><div class="metric" id="moisture">—<span class="unit"> %</span></div><span id="soilStatus" class="status">WAITING</span></div>
<div class="card"><div class="label">Raw ADC reading</div><div class="metric" id="raw">—</div><div class="muted">ESP32 · 12-bit ADC</div></div>
<div class="card"><div class="label">Device status</div><div class="metric" id="deviceStatus" style="font-size:27px">—</div><div class="muted" id="lastSeen">Waiting for telemetry</div></div>
<div class="card"><div class="label">Configured threshold</div><div class="metric" id="threshold">—</div><div class="muted">Raw ADC value</div></div>
</section>
<section class="section card"><h2>Moisture history</h2><div class="chart"><canvas id="chart"></canvas></div><div class="muted" id="chartNote">Loading…</div></section>
<section class="section card">
<div class="analytics-head"><h2>Sensor analytics</h2><select id="rangeSelect" aria-label="Analytics time range"><option value="24">Last 24 hours</option><option value="168" selected>Last 7 days</option><option value="all">All available history</option></select></div>
<div class="analytics-grid">
<div class="card"><div class="label">Average moisture</div><div class="metric" id="avgMoisture">—</div><div class="muted">Selected period</div></div>
<div class="card"><div class="label">Minimum moisture</div><div class="metric" id="minMoisture">—</div><div class="muted">Lowest recorded</div></div>
<div class="card"><div class="label">Maximum moisture</div><div class="metric" id="maxMoisture">—</div><div class="muted">Highest recorded</div></div>
<div class="card"><div class="label">Dry readings</div><div class="metric" id="dryPercent">—</div><div class="muted" id="dryCount">Based on sensor status</div></div>
<div class="card"><div class="label">Total readings</div><div class="metric" id="totalReadings">—</div><div class="muted">In selected period</div></div>
<div class="card"><div class="label">Moisture variability</div><div class="metric" id="stdDev">—</div><div class="muted">Standard deviation</div></div>
<div class="card"><div class="label">Change over period</div><div class="metric" id="periodChange">—</div><div class="muted">First to latest reading</div></div>
<div class="card"><div class="label">Current classification</div><div class="metric" id="currentClass" style="font-size:24px">—</div><div class="muted">Latest sensor status</div></div>
</div>
<div class="analytics-lower">
<div class="card"><h2>Daily average moisture</h2><div class="chart"><canvas id="analyticsChart"></canvas></div><div class="muted" id="dailyNote">Waiting for history…</div></div>
<div class="card"><h2>Dry / wet distribution</h2><div class="bar-track"><div class="bar-dry" id="dryBar" style="width:0%"></div><div class="bar-wet" id="wetBar" style="width:0%"></div></div><div class="legend"><span id="dryLegend">Dry: —</span><span id="wetLegend">Wet: —</span></div><h2 style="margin-top:22px">Data insights</h2><div class="insights" id="insights"><div class="insight">Analytics will appear when historical readings are available.</div></div></div>
</div>
</section>
<section class="section meta"><div class="card"><span class="muted">Backend API</span><strong id="backendState">Checking…</strong></div><div class="card"><span class="muted">MQTT broker</span><strong id="mqttState">Checking…</strong></div><div class="card"><span class="muted">Database</span><strong id="dbState">Checking…</strong></div></section>
<div class="error" id="error"></div><footer>Auto-refreshes every 3 seconds. Monitoring only: this page does not control the water pump.</footer>
</main>
<script>
const DEVICE_ID={{ device_id|tojson }};document.getElementById('deviceId').textContent=DEVICE_ID;
function first(o,keys,fb=null){if(!o||typeof o!=='object')return fb;for(const k of keys)if(o[k]!==undefined&&o[k]!==null)return o[k];return fb}
function rowsOf(p){if(Array.isArray(p))return p;if(!p||typeof p!=='object')return[];for(const k of ['reading','data','latest','readings','results','devices'])if(p[k]!==undefined)return Array.isArray(p[k])?p[k]:[p[k]];return[p]}
async function get(path){const r=await fetch(path,{cache:'no-store'});const d=await r.json().catch(()=>({error:'Invalid JSON'}));if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);return d}
function connection(id,value,ok){const e=document.getElementById(id);e.textContent=value;e.style.color=ok?'var(--green)':'var(--red)'}
function time(v){if(!v)return'—';const d=new Date(v);return isNaN(d)?String(v):d.toLocaleString()}
let history=[];
let latestRecord=null;
function latest(p){const r=rowsOf(p)[0]||{};latestRecord=r;const m=first(r,['moisture_percent','moisturePercent','moisture']);const raw=first(r,['moisture_raw','moistureRaw','raw']);const s=String(first(r,['soil_status','soilStatus','status'],'UNKNOWN')).toUpperCase();
document.getElementById('moisture').innerHTML=`${m===null?'—':Number(m).toFixed(1)}<span class="unit"> %</span>`;document.getElementById('raw').textContent=raw??'—';
const se=document.getElementById('soilStatus');se.textContent=s;se.className='status '+(s==='DRY'?'dry':s==='WET'?'wet':'');document.getElementById('threshold').textContent=first(r,['threshold','moisture_threshold'])??'—';
document.getElementById('lastSeen').textContent='Last reading: '+time(first(r,['recorded_at','created_at','timestamp','time']));document.getElementById('deviceStatus').textContent='Receiving';document.getElementById('deviceStatus').style.color='var(--green)'}
function chart(data){const c=document.getElementById('chart'),b=c.getBoundingClientRect(),dpr=devicePixelRatio||1;c.width=Math.max(1,b.width*dpr);c.height=Math.max(1,b.height*dpr);const x=c.getContext('2d');x.scale(dpr,dpr);const w=b.width,h=b.height,p={l:38,r:10,t:12,b:27};x.clearRect(0,0,w,h);
const pts=data.map(r=>Number(first(r,['moisture_percent','moisturePercent','moisture'],NaN))).filter(Number.isFinite).slice(-60);const cw=w-p.l-p.r,ch=h-p.t-p.b;x.font='11px system-ui';x.lineWidth=1;x.strokeStyle='#293b53';x.fillStyle='#91a2b9';
for(let v=0;v<=100;v+=25){const yy=p.t+ch-(v/100)*ch;x.beginPath();x.moveTo(p.l,yy);x.lineTo(w-p.r,yy);x.stroke();x.fillText(v+'%',3,yy+4)}
if(!pts.length){x.fillText('No historical readings yet',p.l,34);return}const xx=i=>p.l+(pts.length===1?cw/2:i/(pts.length-1)*cw),yy=v=>p.t+ch-Math.max(0,Math.min(100,v))/100*ch;
x.beginPath();pts.forEach((v,i)=>i?x.lineTo(xx(i),yy(v)):x.moveTo(xx(i),yy(v)));x.strokeStyle='#46d39a';x.lineWidth=2.5;x.stroke();x.lineTo(xx(pts.length-1),p.t+ch);x.lineTo(xx(0),p.t+ch);x.closePath();x.fillStyle='rgba(70,211,154,.10)';x.fill();x.fillStyle='#91a2b9';x.fillText('Older',p.l,h-6);x.textAlign='right';x.fillText('Latest',w-p.r,h-6);x.textAlign='left'}
function readingTime(r){const v=first(r,['recorded_at','created_at','timestamp','time','createdAt']);if(v===null)return null;const d=new Date(v);return Number.isNaN(d.getTime())?null:d}
function moistureValue(r){const n=Number(first(r,['moisture_percent','moisturePercent','moisture'],NaN));return Number.isFinite(n)&&n>=0&&n<=100?n:null}
function normalizeHistory(list){return list.slice().sort((a,b)=>(readingTime(a)?.getTime()||0)-(readingTime(b)?.getTime()||0))}
function selectedHistory(){const range=document.getElementById('rangeSelect').value;if(range==='all')return history;const cutoff=Date.now()-Number(range)*60*60*1000;return history.filter(r=>{const t=readingTime(r);return t&&t.getTime()>=cutoff})}
function drawDaily(data){const c=document.getElementById('analyticsChart'),b=c.getBoundingClientRect(),dpr=devicePixelRatio||1;c.width=Math.max(1,b.width*dpr);c.height=Math.max(1,b.height*dpr);const x=c.getContext('2d');x.scale(dpr,dpr);const w=b.width,h=b.height,p={l:38,r:10,t:12,b:32};x.clearRect(0,0,w,h);const days={};
 data.forEach(r=>{const t=readingTime(r),v=moistureValue(r);if(!t||v===null)return;const key=t.toLocaleDateString();(days[key]??=[]).push(v)});
 const entries=Object.entries(days).map(([day,vals])=>({day,avg:vals.reduce((a,b)=>a+b,0)/vals.length}));const cw=w-p.l-p.r,ch=h-p.t-p.b;x.font='11px system-ui';x.strokeStyle='#293b53';x.fillStyle='#91a2b9';
 for(let v=0;v<=100;v+=25){const yy=p.t+ch-v/100*ch;x.beginPath();x.moveTo(p.l,yy);x.lineTo(w-p.r,yy);x.stroke();x.fillText(v+'%',3,yy+4)}
 if(!entries.length){x.fillText('Not enough timestamped data',p.l,34);document.getElementById('dailyNote').textContent='Daily averages need valid reading timestamps.';return}
 const xx=i=>p.l+(entries.length===1?cw/2:i/(entries.length-1)*cw),yy=v=>p.t+ch-v/100*ch;x.beginPath();entries.forEach((e,i)=>i?x.lineTo(xx(i),yy(e.avg)):x.moveTo(xx(i),yy(e.avg)));x.strokeStyle='#73a7ff';x.lineWidth=2.5;x.stroke();entries.forEach((e,i)=>{x.beginPath();x.arc(xx(i),yy(e.avg),3,0,Math.PI*2);x.fillStyle='#73a7ff';x.fill()});x.fillStyle='#91a2b9';x.fillText(entries[0].day,p.l,h-7);x.textAlign='right';x.fillText(entries[entries.length-1].day,w-p.r,h-7);x.textAlign='left';document.getElementById('dailyNote').textContent=entries.length+' day(s) with readings; daily averages are calculated from stored samples.'}
function renderAnalytics(){const data=selectedHistory();const valid=data.map(r=>({r,v:moistureValue(r)})).filter(x=>x.v!==null);const vals=valid.map(x=>x.v);const n=vals.length;const avg=n?vals.reduce((a,b)=>a+b,0)/n:null;const min=n?Math.min(...vals):null,max=n?Math.max(...vals):null;const variance=n?vals.reduce((a,v)=>a+(v-avg)**2,0)/n:0;const sd=n?Math.sqrt(variance):null;
 const dry=valid.filter(x=>String(first(x.r,['soil_status','soilStatus','status'],'')).toUpperCase()==='DRY').length;const wet=valid.filter(x=>String(first(x.r,['soil_status','soilStatus','status'],'')).toUpperCase()==='WET').length;const classified=dry+wet;const firstVal=n?vals[0]:null,lastVal=n?vals[n-1]:null;const change=n>1?lastVal-firstVal:null;
 const put=(id,v)=>document.getElementById(id).textContent=v;put('avgMoisture',avg===null?'—':avg.toFixed(1)+'%');put('minMoisture',min===null?'—':min.toFixed(1)+'%');put('maxMoisture',max===null?'—':max.toFixed(1)+'%');put('dryPercent',classified?((dry/classified)*100).toFixed(1)+'%':'—');put('dryCount',classified?`${dry} dry of ${classified} classified readings`:'No DRY/WET status values');put('totalReadings',n);put('stdDev',sd===null?'—':sd.toFixed(1)+' pp');put('periodChange',change===null?'—':(change>0?'+':'')+change.toFixed(1)+' pp');
 const current=String(first(latestRecord,['soil_status','soilStatus','status'],'—')).toUpperCase();put('currentClass',current);document.getElementById('dryBar').style.width=classified?(dry/classified*100)+'%':'0%';document.getElementById('wetBar').style.width=classified?(wet/classified*100)+'%':'0%';put('dryLegend',`Dry: ${classified?(dry/classified*100).toFixed(1)+'%':'—'} (${dry})`);put('wetLegend',`Wet: ${classified?(wet/classified*100).toFixed(1)+'%':'—'} (${wet})`);drawDaily(data);
 const messages=[];if(!n){messages.push('No valid moisture readings in this time range.');}else{messages.push(`Average soil moisture was ${avg.toFixed(1)}%, across ${n} valid readings.`);if(classified){const pct=dry/classified*100;messages.push(pct>=50?`${pct.toFixed(1)}% of classified readings were DRY; the sensor frequently detected dry conditions.`:`${pct.toFixed(1)}% of classified readings were DRY in this period.`)}if(sd>=20)messages.push(`Moisture varied considerably (standard deviation ${sd.toFixed(1)} percentage points).`);else messages.push(`Moisture readings were relatively consistent (standard deviation ${sd.toFixed(1)} percentage points).`);if(change!==null){messages.push(change>=5?'Moisture increased from the first to the latest reading in this period.':change<=-5?'Moisture decreased from the first to the latest reading in this period.':'Moisture was broadly stable from the first to the latest reading.')}}
 document.getElementById('insights').innerHTML=messages.map(m=>`<div class="insight">${m}</div>`).join('');if(!data.length)document.getElementById('dailyNote').textContent='No readings available for this period.'}

async function refresh(){const err=document.getElementById('error');try{const h=await get('/proxy/health');const ok=String(h.status||'').toLowerCase()==='ok';document.getElementById('apiDot').className='dot '+(ok?'ok':'bad');document.getElementById('apiText').textContent=ok?'Backend connected':'Backend issue';connection('backendState',h.status||'Connected',ok);connection('mqttState',h.mqtt_connected?'Connected':'Disconnected',!!h.mqtt_connected);connection('dbState',h.database_connected?'Connected':'Disconnected',!!h.database_connected)}catch(e){document.getElementById('apiDot').className='dot bad';document.getElementById('apiText').textContent='Backend unavailable';connection('backendState','Unavailable',false);err.textContent='Backend: '+e.message;return}
try{latest(await get('/proxy/latest'));err.textContent=''}catch(e){err.textContent='Latest reading: '+e.message;document.getElementById('deviceStatus').textContent='No data';document.getElementById('deviceStatus').style.color='var(--red)'}
try{history=normalizeHistory(rowsOf(await get('/proxy/history')));chart(history);renderAnalytics();document.getElementById('chartNote').textContent=history.length?history.length+' historical record(s) loaded':'No historical readings returned'}catch(e){history=[];document.getElementById('chartNote').textContent='History unavailable: '+e.message;chart([]);renderAnalytics()}}
document.getElementById('rangeSelect').addEventListener('change',renderAnalytics);
refresh();setInterval(refresh,3000);addEventListener('resize',()=>{chart(history);renderAnalytics()});
</script></body></html>
'''

def backend_get(path):
    request = urllib.request.Request(BACKEND_URL + path, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body), exc.code
        except json.JSONDecodeError:
            return {"error": body or str(exc)}, exc.code
    except Exception as exc:
        return {"error": str(exc)}, 502

@app.get("/")
def home():
    return render_template_string(PAGE, device_id=DEVICE_ID)

@app.get("/proxy/<resource>")
def proxy(resource):
    endpoints = {
        "health": "/api/health",
        "devices": "/api/devices",
        "latest": f"/api/devices/{DEVICE_ID}/latest",
        "history": f"/api/devices/{DEVICE_ID}/history",
    }
    if resource not in endpoints:
        return jsonify({"error": "Unknown endpoint"}), 404
    result = backend_get(endpoints[resource])
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)

if __name__ == "__main__":
    print(f"Dashboard for device: {DEVICE_ID}")
    print(f"Using backend: {BACKEND_URL}")
    app.run(host="127.0.0.1", port=5000, debug=False)
