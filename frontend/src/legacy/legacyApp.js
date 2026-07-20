// Legacy JavaScript — the original vanilla-JS UI. app/static/index.html has been
// removed, so this file (+ legacyShellHtml.js + styles/global.css) is now the
// CANONICAL source of the legacy UI and is hand-maintained.
//
// The original two <script> blocks, concatenated. LegacyApp.jsx imports this file
// with Vite's `?raw` suffix and injects it as a classic <script> element, so it
// runs in GLOBAL scope exactly like the old single-file page. Because of that,
// every top-level `function foo(){}` / `const foo = ...` is reachable from the
// inline on* handlers in the shell markup (e.g. onclick="navigateTo(...)") with
// no window.* shim required.

// ---- toast + prompt helpers (replace browser popups) ----
// toast(message, isErr)  — backward compatible.
// toast(message, {type:'ok'|'err'|'info', title, duration})  — richer form.
function toast(msg,opt){
  let type="ok",title,duration;
  if(opt===true){type="err";}
  else if(opt&&typeof opt==="object"){type=opt.type||(opt.isErr?"err":"ok");title=opt.title;duration=opt.duration;}
  const titles={ok:"Success",err:"Something went wrong",info:"Heads up"};
  const icons={ok:"✓",err:"!",info:"i"};
  title=title||titles[type];
  // Errors stay longer and scale a little with length so they're actually readable.
  duration=duration||(type==="err"?Math.min(9000,5200+((msg||"").length*35)):3800);
  const d=document.createElement("div");
  d.className="toastmsg "+type;
  d.innerHTML=`<div class="t-ico">${icons[type]}</div>`+
    `<div class="t-body"><div class="t-title"></div><div class="t-msg"></div></div>`+
    `<button class="t-close" aria-label="Dismiss">×</button>`+
    `<div class="t-timer" style="animation:toastTimer ${duration}ms linear forwards"></div>`;
  d.querySelector(".t-title").textContent=title;
  d.querySelector(".t-msg").textContent=msg==null?"":String(msg);
  const remove=()=>{if(d.dataset.gone)return;d.dataset.gone="1";d.classList.add("leaving");setTimeout(()=>d.remove(),220);};
  d.querySelector(".t-close").onclick=remove;
  document.getElementById("toast").appendChild(d);
  const timer=setTimeout(remove,duration);
  d.addEventListener("mouseenter",()=>{clearTimeout(timer);const bar=d.querySelector(".t-timer");if(bar)bar.style.animationPlayState="paused";});
  return d;
}

// confirmModal(...) — styled, promise-based replacement for window.confirm.
// Resolves true if confirmed, false if cancelled (Cancel / backdrop / Esc).
// Usage: if(!(await confirmModal({title, body, confirmText, danger:true})))return;
function confirmModal(opts){
  opts=opts||{};
  const m=document.getElementById("confirm-modal");
  const okBtn=document.getElementById("confirm-ok");
  const cancelBtn=document.getElementById("confirm-cancel");
  if(!m||!okBtn||!cancelBtn){return Promise.resolve(window.confirm(opts.body||"Are you sure?"));}
  document.getElementById("confirm-title").textContent=opts.title||"Please confirm";
  document.getElementById("confirm-body").textContent=opts.body||"";
  okBtn.textContent=opts.confirmText||"Continue";
  okBtn.className=opts.danger?"danger":"go";
  m.classList.add("show");
  setTimeout(()=>okBtn.focus(),40);
  return new Promise(resolve=>{
    let done=false;
    const close=val=>{if(done)return;done=true;
      m.classList.remove("show");
      okBtn.onclick=null;cancelBtn.onclick=null;m.onclick=null;document.removeEventListener("keydown",onKey);
      resolve(val);};
    const onKey=e=>{if(e.key==="Escape")close(false);else if(e.key==="Enter")close(true);};
    okBtn.onclick=()=>close(true);
    cancelBtn.onclick=()=>close(false);
    m.onclick=e=>{if(e.target===m)close(false);};   // backdrop click cancels
    document.addEventListener("keydown",onKey);
  });
}

// ---- skeleton placeholders (returned as HTML strings) ----
function skeletonState(body,label="Loading content"){
  return `<div class="sk-state" role="status" aria-label="${esc(label)}">${body}</div>`;
}
const skeleton={
  line(w){return `<div class="sk sk-line"${w?` style="width:${w}"`:""}></div>`;},
  cards(n=6,label="Loading cards"){let c="";for(let i=0;i<n;i++)c+=`<div class="sk-card"><div class="sk sk-line lg"></div><div class="sk sk-line sm"></div><div class="sk sk-line" style="width:40%;margin-top:22px"></div></div>`;return skeletonState(`<div class="sk-grid">${c}</div>`,label);},
  kpis(n=7){let c="";for(let i=0;i<n;i++)c+=`<div class="sk-kpi"><div class="sk sk-line" style="width:50%;height:24px"></div><div class="sk sk-line sm" style="margin-top:10px"></div></div>`;return c;},
  rows(n=5,label="Loading rows"){let c="";for(let i=0;i<n;i++)c+=`<div class="sk-row"><div class="sk sk-dot"></div><div style="flex:1"><div class="sk sk-line lg" style="margin:0 0 8px"></div><div class="sk sk-line sm" style="margin:0"></div></div><div class="sk sk-badge"></div></div>`;return skeletonState(`<div class="sk-row-wrap">${c}</div>`,label);},
  table(cols=5,n=5,label="Loading table"){const head=`<tr>${Array(cols).fill('<th><div class="sk sk-line sm" style="margin:0;width:70%"></div></th>').join("")}</tr>`;let body="";for(let i=0;i<n;i++)body+=`<tr>${Array(cols).fill('<td><div class="sk sk-line" style="margin:0"></div></td>').join("")}</tr>`;return skeletonState(`<div style="overflow:auto"><table>${head}${body}</table></div>`,label);},
  block(label="Loading details"){return skeletonState(`<div class="sk sk-line lg"></div><div class="sk sk-line"></div><div class="sk sk-line sm"></div>`,label);},
  dashboard(){return skeletonState(
    `<div class="sk sk-line lg" style="width:180px;height:24px;margin-bottom:20px"></div>`+
    `<div class="dash-metrics">${this.kpis(7)}</div>`+
    `<div class="dash-row c2"><div class="sk-card">${this.kpis(2)}</div><div class="sk-card">${this.blockLines(5)}</div></div>`+
    `<div class="sk-card" style="margin-top:16px">${this.blockLines(6)}</div>`,
    "Loading dashboard"
  );},
  blockLines(n=4){let c="";for(let i=0;i<n;i++)c+=`<div class="sk sk-line${i===0?" lg":i===n-1?" sm":""}"></div>`;return c;}
};
// paint a skeleton into a container if it exists
function skIn(sel,html){const el=$(sel);if(el)el.innerHTML=html;}
// Compact detail-pane placeholder.
function loadingRow(text){return skeleton.block(text||"Loading details");}

// ---- button busy state ----
function setBusy(elOrSel,on){const el=typeof elOrSel==="string"?$(elOrSel):elOrSel;if(!el)return;
  if(on){el.setAttribute("aria-busy","true");}else{el.removeAttribute("aria-busy");}}
// run an async action while showing a button spinner; re-throws so callers keep their try/catch
async function withBusy(elOrSel,fn){const el=typeof elOrSel==="string"?$(elOrSel):elOrSel;setBusy(el,true);
  try{return await fn();}finally{setBusy(el,false);}}

// ---- top progress bar (driven by live api() request count) ----
// Top route-progress bar removed — no-op stub kept so existing start()/done() callers don't break.
const NProgress={start(){},done(){}};

// ============ BRANDED LOADERS (ported from the wardenIQ test-generator app) ============
// --- gear SVG generator (ported from AnalyzeLoader GearSVG) ---
function _gearSVG(size,teeth,fill,stroke){
  const r=size/2,inner=r*0.58,toothH=r*0.24,hole=r*0.23,step=(Math.PI*2)/teeth;let d="";
  const pt=(a,rad)=>[Math.cos(a)*rad,Math.sin(a)*rad];
  for(let i=0;i<teeth;i++){const a0=step*i-step*0.36,a1=step*i-step*0.14,a2=step*i+step*0.14,a3=step*i+step*0.36;
    const[x0,y0]=pt(a0,inner),[x1,y1]=pt(a1,r+toothH),[x2,y2]=pt(a2,r+toothH),[x3,y3]=pt(a3,inner);
    if(i===0)d+=`M ${x0.toFixed(2)},${y0.toFixed(2)} `;
    d+=`L ${x1.toFixed(2)},${y1.toFixed(2)} L ${x2.toFixed(2)},${y2.toFixed(2)} L ${x3.toFixed(2)},${y3.toFixed(2)} `;}
  d+="Z";const vb=r+toothH+2;
  return `<svg width="${(vb*2).toFixed(0)}" height="${(vb*2).toFixed(0)}" viewBox="${-vb} ${-vb} ${vb*2} ${vb*2}" style="overflow:visible">`+
    `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="1.3"/>`+
    `<circle r="${hole.toFixed(2)}" fill="none" stroke="${stroke}" stroke-width="1.6"/>`+
    `<circle r="${(hole*0.38).toFixed(2)}" fill="${stroke}" opacity="0.75"/></svg>`;
}
const ANALYZE_STEPS=["Analyzing inputs","AI processing","Generating output"];
const ANALYZE_MESSAGES=["Checking readiness…","Processing sources…","Building AI context…","Generating outputs…","Finalizing workspace…"];
const _analyzeCards=[
  {ico:"✓",color:"#a78bfa",border:"rgba(139,92,246,.55)",bg:"rgba(139,92,246,.18)",name:"requirements.txt",x:8,y:26},
  {ico:"⚠",color:"#fb923c",border:"rgba(251,146,60,.5)",bg:"rgba(251,146,60,.15)",name:"bug_report.md",x:0,y:112},
  {ico:"?",color:"#818cf8",border:"rgba(99,102,241,.5)",bg:"rgba(99,102,241,.18)",name:"ambiguous.spec",x:18,y:196},
  {ico:"≡",color:"#38bdf8",border:"rgba(56,189,248,.5)",bg:"rgba(56,189,248,.15)",name:"api_docs.yaml",x:300,y:56}];

// Build a branded loader HTML string. variant: "analyze" | "quiz".
// opts: {compact, inline, messages, steps, questionLabel, optionLabel}
function brandLoader(variant,opts){
  opts=opts||{};
  const sizeCls=(opts.compact?" compact":(opts.inline===false?"":" inline"));
  if(variant==="quiz"){
    const steps=opts.steps||["Analyzing inputs","AI Processing","Generating output"];
    const q=opts.questionLabel||"Question 01",o=opts.optionLabel||"Option:";
    return `<div class="wql-root${sizeCls}" role="status" aria-label="Loading">
      <div class="wql-shell">
        <div class="wql-stepper" aria-hidden="true">
          <span class="wql-step wql-step-1"><span class="wql-step-dot"></span>${esc(steps[0])}</span>
          <span class="wql-step-line"></span>
          <span class="wql-step wql-step-2"><span class="wql-step-dot"></span>${esc(steps[1])}</span>
          <span class="wql-step-line"></span>
          <span class="wql-step wql-step-3"><span class="wql-step-dot"></span>${esc(steps[2])}</span>
        </div>
        <div class="wql-stack">
          <div class="wql-qcard"><div class="wql-qtitle">${esc(q)}</div>
            <div class="wql-qrow"><div class="wql-track"><div class="wql-line"></div></div><div class="wql-qmark">?</div></div></div>
          <div class="wql-ocard"><div class="wql-otitle">${esc(o)}</div>
            <div class="wql-olist" aria-hidden="true">
              <div class="wql-orow wql-row-1"><span class="wql-odot"></span><span class="wql-oline wql-l1"></span></div>
              <div class="wql-orow wql-row-2"><span class="wql-odot"></span><span class="wql-oline wql-l2"></span></div>
              <div class="wql-orow wql-row-3"><span class="wql-odot"></span><span class="wql-oline wql-l3"></span></div>
              <div class="wql-orow wql-row-4"><span class="wql-odot"></span><span class="wql-oline wql-l4"></span></div></div></div>
          <button class="wql-next" type="button" tabindex="-1">Next</button>
        </div>
      </div></div>`;
  }
  // analyze (gear machine)
  const steps=opts.steps||ANALYZE_STEPS;
  const msgs=opts.messages||ANALYZE_MESSAGES;
  const stepper=steps.map((s,i)=>`${i>0?'<span class="aql-stp-line"></span>':''}<span class="aql-stp${i===0?' active':''}"><span class="aql-stp-dot"></span><span class="aql-stp-label">${esc(s)}</span></span>`).join("");
  const cards=_analyzeCards.map(c=>`<div class="aql-card" style="left:${c.x}px;top:${c.y}px;border:1px solid ${c.border};color:${c.color}">
    <span class="aql-ico" style="background:${c.bg};color:${c.color}">${c.ico}</span>${esc(c.name)}</div>`).join("");
  return `<div class="aql-root${sizeCls}" role="status" aria-label="Loading">
    <div class="aql-scene">
      <div class="aql-stepper" aria-hidden="true">${stepper}</div>
      ${cards}
      <div class="aql-machine">
        <span class="aql-gear big">${_gearSVG(58,15,"rgba(124,58,237,.9)","rgba(196,181,253,.9)")}</span>
        <span class="aql-gear small">${_gearSVG(34,11,"rgba(56,189,248,.85)","rgba(186,230,253,.9)")}</span>
      </div>
      <div class="aql-msg" data-msgs='${esc(JSON.stringify(msgs))}' data-i="0"><div class="aql-msg-pill">${esc(msgs[0])}</div></div>
    </div></div>`;
}

// Global ticker cycles analyze-loader messages + phase steppers (auto-skips removed nodes).
let _brandTick=0;
setInterval(()=>{_brandTick++;
  document.querySelectorAll(".aql-msg[data-msgs]").forEach(el=>{
    let msgs;try{msgs=JSON.parse(el.dataset.msgs);}catch(e){return;}
    if(!msgs.length)return;const i=_brandTick%msgs.length;if(String(i)===el.dataset.i)return;el.dataset.i=String(i);
    const pill=el.querySelector(".aql-msg-pill");if(pill){pill.textContent=msgs[i];pill.classList.remove("swap");void pill.offsetWidth;pill.classList.add("swap");}
    // reflect progress in the stepper of the same scene
    const scene=el.closest(".aql-scene");if(scene){const stps=[...scene.querySelectorAll(".aql-stp")];const active=Math.min(stps.length-1,Math.floor(i/Math.max(1,Math.ceil(msgs.length/stps.length))));
      stps.forEach((s,si)=>{s.classList.toggle("active",si===active);s.classList.toggle("passed",si<active);});}
  });
},1900);

// Fullscreen branded loader overlay
function showBrandLoader(variant,opts){
  hideBrandLoader();
  const ov=document.createElement("div");ov.className="brand-loader-overlay";ov.id="brand-loader-overlay";
  ov.innerHTML=brandLoader(variant,Object.assign({inline:false},opts||{}));
  document.body.appendChild(ov);return ov;
}
function hideBrandLoader(){const ov=document.getElementById("brand-loader-overlay");if(ov)ov.remove();}
// Inject a compact inline branded loader into a container by selector
function brandLoaderIn(sel,variant,opts){const el=$(sel);if(el)el.innerHTML=brandLoader(variant||"analyze",Object.assign({compact:true},opts||{}));}

// ============ REFERENCE DASHBOARD COMPONENTS (ported from test-generator DashboardPage) ============
const RC_COLORS={sky:"#38bdf8",violet:"#a78bfa",amber:"#fbbf24",emerald:"#34d399",rose:"#fb7185",teal:"#2dd4bf",slate:"#94a3b8"};
const RC_ICONS={
  testCases:"M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
  testPlan:"M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2",
  analysis:"M3 3v18h18M7 14l4-4 3 3 5-6",
  testCycles:"M3 12a9 9 0 1 0 9-9 9 9 0 0 0-7 3.5M3 4v4h4",
  coverage:"M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zM2 12h20M12 2a15 15 0 0 1 0 20"};
const rcNum=n=>Number(n||0).toLocaleString();
function rcIcon(path){return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${path}"/></svg>`;}
function rcMetric(o){
  const subs=(o.subs&&o.subs.length)?`<dl class="rc-metric-subs">${o.subs.map(s=>`<div class="rc-metric-sub"><dt>${esc(s.label)}</dt><dd${s.tone?` style="color:${s.tone}"`:""}>${esc(s.value)}</dd></div>`).join("")}</dl>`:"";
  return `<div class="rc-card hover rc-metric"><div class="rc-metric-top"><span style="color:${o.accent}">${o.icon||""}</span><h2>${esc(o.title)}</h2></div>
    <div class="rc-metric-val">${esc(o.value)}</div>${o.caption?`<div class="rc-metric-cap">${esc(o.caption)}</div>`:""}${subs}</div>`;
}
function rcSection(title,body,extraCls){return `<div class="rc-card hover rc-section ${extraCls||""}"><h3 class="rc-section-title">${esc(title)}</h3>${body}</div>`;}
function rcBars(items){
  const upper=Math.max(1,...items.map(i=>+i.value||0));
  const total=items.reduce((s,i)=>s+Math.max(0,+i.value||0),0);
  if(!total)return `<div class="rc-empty">No data yet</div>`;
  return `<div class="rc-bars" role="img" aria-label="${esc(items.map(i=>i.label+": "+i.value).join(", "))}">`+
    items.map(i=>{const pct=Math.round(Math.max(0,+i.value||0)/upper*100);
      return `<div class="rc-bar"><span class="rc-bar-lab">${esc(i.label)}</span>`+
        `<span class="rc-bar-track"><span class="rc-bar-fill" style="width:${pct}%;background:${i.color}"></span></span>`+
        `<span class="rc-bar-val">${rcNum(i.value)}</span></div>`;}).join("")+`</div>`;
}
function rcDonut(o){
  const size=o.size||132,thickness=o.thickness||14,segs=o.segments||[];
  const total=segs.reduce((s,x)=>s+Math.max(0,+x.value||0),0);
  const r=(size-thickness)/2,circ=2*Math.PI*r,cx=size/2;let off=0;
  let arcs=`<circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="${thickness}"/>`;
  if(total>0)segs.forEach(s=>{const v=Math.max(0,+s.value||0);if(!v)return;const dash=v/total*circ;
    arcs+=`<circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${thickness}" stroke-linecap="butt" stroke-dasharray="${dash} ${circ-dash}" stroke-dashoffset="${-off}" transform="rotate(-90 ${cx} ${cx})"/>`;off+=dash;});
  const center=(o.centerValue!=null||o.centerLabel)?`<g>${o.centerValue!=null?`<text x="${cx}" y="${cx-(o.centerLabel?2:-5)}" text-anchor="middle" fill="#fff" style="font-size:18px;font-weight:600">${esc(o.centerValue)}</text>`:""}${o.centerLabel?`<text x="${cx}" y="${cx+14}" text-anchor="middle" fill="#94a3b8" style="font-size:9px;letter-spacing:.08em;text-transform:uppercase">${esc(o.centerLabel)}</text>`:""}</g>`:"";
  const legend=`<dl class="rc-legend">${segs.map(s=>`<div class="rc-legend-row"><span class="rc-legend-sw" style="background:${s.color}"></span><dt class="rc-legend-lab">${esc(s.label)}</dt><dd class="rc-legend-val">${rcNum(s.value)}</dd></div>`).join("")}${total===0?`<div class="rc-empty">No data yet</div>`:""}</dl>`;
  return `<div class="rc-donut" role="img" aria-label="${esc(segs.map(s=>s.label+": "+s.value).join(", "))||"No data"}"><svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">${arcs}${center}</svg>${legend}</div>`;
}
function rcRing(o){
  const size=o.size||148,thickness=o.thickness||16,pct=Math.max(0,Math.min(100,Math.round(o.percent||0)));
  const r=(size-thickness)/2,circ=2*Math.PI*r,cx=size/2,dash=pct/100*circ;
  const tone=pct>=80?RC_COLORS.emerald:pct>=50?RC_COLORS.amber:RC_COLORS.rose;
  return `<div style="display:flex;justify-content:center" role="img" aria-label="${esc(o.label||"")}: ${pct}%">
    <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">
      <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="${thickness}"/>
      <circle cx="${cx}" cy="${cx}" r="${r}" fill="none" stroke="${tone}" stroke-width="${thickness}" stroke-linecap="round" stroke-dasharray="${dash} ${circ-dash}" transform="rotate(-90 ${cx} ${cx})"/>
      <text x="${cx}" y="${cx-2}" text-anchor="middle" fill="#fff" style="font-size:22px;font-weight:600">${pct}%</text>
      ${o.label?`<text x="${cx}" y="${cx+16}" text-anchor="middle" fill="#94a3b8" style="font-size:9px;letter-spacing:.08em;text-transform:uppercase">${esc(o.label)}</text>`:""}
    </svg></div>`;
}
function uiPrompt(title,label,value){return new Promise(res=>{
  const m=document.getElementById("pmodal");document.getElementById("pm-title").textContent=title;
  document.getElementById("pm-label").textContent=label||"Value";const inp=document.getElementById("pm-input");inp.value=value||"";
  m.classList.add("show");setTimeout(()=>inp.focus(),50);
  const done=v=>{m.classList.remove("show");document.getElementById("pm-ok").onclick=null;document.getElementById("pm-cancel").onclick=null;inp.onkeydown=null;res(v);};
  document.getElementById("pm-ok").onclick=()=>done(inp.value.trim());
  document.getElementById("pm-cancel").onclick=()=>done(null);
  inp.onkeydown=e=>{if(e.key==="Enter")done(inp.value.trim());if(e.key==="Escape")done(null);};
});}
function uiConfirm(msg, title = "Confirm Action", confirmLabel = "Confirm", danger = false) {
  return new Promise(res => {
    openCaseConfirmation({
      title: title,
      copy: msg,
      summary: "",
      confirmLabel: confirmLabel,
      danger: danger,
      onConfirm: () => { res(true); }
    });
    $("#cc-cancel").onclick = () => {
      $("#case-confirm").classList.remove("show");
      res(false);
    };
  });
}
// Generic HTML modal → resolves true (confirm) / false (cancel). Body HTML stays in
// the DOM while open so callers can read its inputs after resolve.
function uiModalHTML(title, bodyHTML, confirmLabel = "Save") {
  return new Promise(res => {
    let m = document.getElementById("html-modal");
    if (!m) {
      m = document.createElement("div");
      m.className = "modal"; m.id = "html-modal";
      m.innerHTML = `<div class="box" style="max-width:520px;width:92vw">
        <div class="editor-head"><h2 id="hm-title" style="margin:0;font-size:17px"></h2><button class="ghost" id="hm-x">close</button></div>
        <div id="hm-body" style="padding:16px 20px"></div>
        <div class="editor-foot" style="display:flex;gap:8px;justify-content:flex-end;padding:14px 20px;border-top:1px solid var(--line)">
          <button class="ghost" id="hm-cancel">Cancel</button><button class="go" id="hm-ok"></button></div>
      </div>`;
      document.body.appendChild(m);
    }
    $("#hm-title").textContent = title;
    $("#hm-body").innerHTML = bodyHTML;
    $("#hm-ok").textContent = confirmLabel;
    m.classList.add("show");
    // Wire the specific-projects radio toggle + project search (used by manageAccess).
    m.querySelectorAll('input[name="ma-scope"]').forEach(r => r.onchange = () => {
      const some = (document.querySelector('input[name="ma-scope"]:checked') || {}).value === "some";
      const list = document.getElementById("ma-list");
      const search = document.getElementById("ma-search");
      if (list) list.hidden = !some;
      if (search) search.hidden = !some;
    });
    const maSearch = document.getElementById("ma-search");
    if (maSearch) maSearch.addEventListener("input", () => {
      const q = maSearch.value.trim().toLowerCase();
      document.querySelectorAll('#ma-list label').forEach(l => {
        l.style.display = (!q || (l.getAttribute("data-name") || "").includes(q)) ? "" : "none";
      });
    });
    const done = v => { m.classList.remove("show"); res(v); };
    $("#hm-ok").onclick = () => done(true);
    $("#hm-cancel").onclick = () => done(false);
    $("#hm-x").onclick = () => done(false);
  });
}


// ----- second <script> block -----

const $=s=>document.querySelector(s);
// Escapes &, <, >, " and ' so the result is safe in BOTH element text and quoted
// HTML attribute contexts (e.g. href="...", title="..."). Entities decode back to
// the original characters when rendered, so this is also safe for text nodes.
const esc=s=>(s??"").toString().replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const escAttr=esc;   // alias: same escaper is attribute-safe now
// ---- shared verdict + evidence renderers (used by Impact, PR coverage & Mind Map) ----
function vStatus(s){const m={matched:["mm-covered","matched"],covered:["mm-covered","covered"],
  review_needed:["mm-partial","review"],partial:["mm-partial","partial"],uncovered:["mm-uncovered","uncovered"]};
  const x=m[s];return x?`<span class="badge ${x[0]}">${x[1]}</span>`:"";}
function vConf(c,tier,stype){return (c!=null)?`<span class="badge" title="confidence">${Math.round(c*100)}%${tier?` · T${tier}`:""}</span>`
  :(stype==="ai"?`<span class="pill" title="LLM-inferred (no exact code signal)">AI</span>`:"");}
function vSignal(sig,stype){return sig?`<span class="pill" title="matched code signal">${esc(stype||"")}: ${esc(sig)}</span>`:"";}
function vEvidence(ev){return (ev||[]).map(e=>`<div class="muted" style="font-size:11.5px;margin-left:12px">↳ <code>${esc(e.file||"")}${e.line?":"+e.line:""}</code>${e.sha?` <a class="pill" ${e.url?`href="${e.url}" target="_blank"`:""}>${esc((e.sha||"").slice(0,7))}</a>`:""}</div>`).join("");}
// Priority badge — accepts High/Mid/Low, P1/P2/P3 or 1/2/3 (previously everything showed "Low").
// Canonical priority everywhere: High=red, Medium=blue, Low=green. Accepts High/Med/Low, P1/P2/P3, 1/2/3.
function prioKey(p){const s=(p==null?"":p).toString().toLowerCase();
  if(["high","critical","p1","1"].includes(s))return"high";
  if(["medium","mid","p2","2"].includes(s))return"medium";return"low";}
function prioLabel(p){return{high:"High",medium:"Medium",low:"Low"}[prioKey(p)];}
function prioBadge(p){const k=prioKey(p);
  const C={high:["rgba(239,68,68,0.25)","rgba(239,68,68,0.12)","#fca5a5"],
           medium:["rgba(59,130,246,0.25)","rgba(59,130,246,0.12)","#93c5fd"],
           low:["rgba(34,197,94,0.25)","rgba(34,197,94,0.12)","#86efac"]}[k];
  return `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;border:1px solid ${C[0]};background:${C[1]};color:${C[2]}">${prioLabel(p)}</span>`;}
// Canonical step table (# / Step / Expected result) — same look as the test-case detail.
// Accepts dicts {action,expected} or "action → expected" / "action -> expected" strings.
function stepsHtml(steps){if(!steps||!steps.length)return"";
  const norm=steps.map(s=>{
    if(typeof s==="string"){const p=s.split(/\s*(?:→|->)\s*/);return{action:p[0]||"",expected:p.slice(1).join(" → ")};}
    return{action:s.action||"",expected:s.expected||""};});
  const rows=norm.map((s,i)=>`<div class="case-step"><span class="case-step-num">${i+1}.</span><span>${esc(s.action)}</span><span class="case-step-expected">${esc(s.expected||"No separate expected result")}</span></div>`).join("");
  return `<div class="case-steps-table" style="margin:8px 0 2px"><div class="case-step case-step-head"><span>#</span><span>Step</span><span>Expected result</span></div>${rows}</div>`;}
// Turn raw backend / httpx error strings into a short, human message (used app-wide).
function cleanErr(detail,status){
  let d=(detail==null?"":detail).toString().trim();
  d=d.replace(/\s*For more information check:\s*https?:\/\/\S+/gi,"");           // drop MDN hint
  d=d.replace(/(?:client|server) error '([^']+)' for url '[^']*'/gi,"$1");       // → "404 Not Found"
  d=d.replace(/\s*for url '[^']*'/gi,"");
  d=d.replace(/https?:\/\/\S+/g,"").replace(/\s*\n\s*/g," ").replace(/[ \t]{2,}/g," ").trim();
  d=d.replace(/[:\s]+$/,"").trim();
  if(d)return d;
  // No useful detail from the server — give a friendly, status-aware fallback.
  const byStatus={400:"That request wasn't valid. Please check your input and try again.",
    404:"We couldn't find what you were looking for.",
    408:"The request timed out. Please try again.",
    409:"That conflicts with something that already exists.",
    413:"The file or payload is too large.",
    422:"Some of the information provided couldn't be processed. Please review and try again.",
    429:"Too many requests — please wait a moment and try again.",
    500:"The server ran into a problem. Please try again in a moment.",
    502:"The server is unreachable right now (bad gateway). Please try again shortly.",
    503:"The service is temporarily unavailable. Please try again shortly.",
    504:"The server took too long to respond. Please try again."};
  return byStatus[status] || `Request failed${status?` (${status})`:""}. Please try again.`;
}
async function api(p,o){
  // NOTE: never log request bodies or response payloads — they can carry PATs,
  // API keys, SMTP passwords, OTP codes and other secrets into the browser console.
  try{NProgress.start();}catch(e){}
  let r,raw;
  try{ r=await fetch(p,o); raw=await r.text(); }
  catch(netErr){
    // Network / server-unreachable — give the user a clear, non-technical message.
    console.error(`[API Net] ${p}`, netErr);
    if(typeof toast==="function")toast("Can't reach the server. Check that wardenIQ is running and your connection is active.",{type:"err",title:"Connection problem"});
    throw new Error("Can't reach the server — please check your connection and try again.");
  }
  finally{try{NProgress.done();}catch(e){}}
  let j={};
  try{j=raw?JSON.parse(raw):{};}catch(e){j={detail:raw||`Request failed with status ${r.status}`};}
  if(r.status===401&&!p.startsWith("/api/auth/")){
    // Includes session invalidation after a role change / disable / forced logout.
    ME=null;showLogin();
    if(typeof toast==="function")toast(j.detail||"Your session ended — please sign in again.",{type:"info",title:"Session expired"});
    throw new Error(j.detail||"Please sign in");
  }
  if(r.status===403){
    // Authorization denial — surface it instead of failing silently, and refresh
    // identity in case the user's role changed under them.
    if(typeof toast==="function")toast(j.detail||"You don't have permission to do that.",{type:"err",title:"Not allowed"});
    if(!p.startsWith("/api/auth/"))setTimeout(()=>{try{refreshMe();}catch(e){}},0);
    throw new Error(cleanErr(j.detail||"not permitted", r.status));
  }
  if(!r.ok) {
    throw new Error(cleanErr(j.detail, r.status));
  }
  return j;
}
let currentProject=null,currentFeature=null,currentFeatureData=null,currentFeatureCases=[],currentViewName="dashboard",editing={id:null,steps:[]},tcPage=0;
const TITLES={dashboard:"Dashboard",projects:"Projects & Repos",features:"Features",validator:"MCQ Validator",testplan:"Test Plan",cases:"Test Cases",gap:"Gap Analysis",cycles:"Code Analysis",testcycles:"Test Cycles",mindmap:"Mind Map",develop:"Start Developing",steps:"Step Library",usage:"LLM Usage & Cost",users:"Users",config:"Configuration"};
let ME=null;
let ANALYSIS_IMPACTED=[];

// ---- nav ----
function navigateTo(v){
  currentViewName=v;
  const sidebarView=["features","validator","testplan"].includes(v)?"projects":v;
  document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("active",x.dataset.view===sidebarView));
  document.querySelectorAll(".view").forEach(s=>s.hidden=(s.id!=="view-"+v));
  $("#view-title").textContent=TITLES[v] || "";
  if(v==="dashboard")loadDashboard(); if(v==="projects"){showProjectList();loadProjects();loadSyncStatus();}
  if(v==="features"){loadProjects();loadFeatures();if(currentFeature)openFeature(currentFeature);else showFeatureList();} if(v==="cases")initCases(); if(v==="steps")loadSteps();
  if(v==="cycles")initCycles(); if(v==="testcycles")initTestCycles(); if(v==="mindmap")initMindmap(); if(v==="develop")initDevelop(); if(v==="config")loadConfig(); if(v==="jobs")initJobs(); if(v==="users"){loadProjectPicker();loadUsers();loadAudit();} if(v==="usage")loadUsage();
  if(v==="validator")initValidator(); if(v==="testplan")initTestPlan(); if(v==="gap")initGap();
  renderBreadcrumbs();
  updateBackbar();
  // Enforce viewer read-only on the freshly-shown view (now + after async loaders
  // inject their buttons).
  try{enforceViewerReadOnly();setTimeout(enforceViewerReadOnly,400);}catch(e){}
  // Remember where the user is so a refresh restores it instead of jumping to Dashboard.
  try{history.replaceState(null,"","#"+v);}catch(e){}
  try{localStorage.setItem("wq_nav",JSON.stringify({view:v,project:currentProject,feature:currentFeature}));}catch(e){}
}
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>navigateTo(b.dataset.view));
if($("#sidebar-toggle"))$("#sidebar-toggle").onclick=()=>{
  $("#app-shell").classList.toggle("sidebar-collapsed");
  $("#sidebar-toggle").textContent=$("#app-shell").classList.contains("sidebar-collapsed")?"›":"‹";
};

function renderBreadcrumbs() {
  // The guided breadcrumb strip was removed in favor of simple back navigation.
}
function updateBackbar(){
  const bar=$("#backbar"),btn=$("#backbar-btn"),label=$("#backbar-label");
  if(!bar||!btn||!label)return;
  let show=true,text="",handler=null;
  if(currentViewName==="projects" && !$("#project-detail-page")?.hidden){
    text="Project settings";handler=()=>showProjectList();
  }else if(currentViewName==="features" && !$("#feature-create-page")?.hidden){
    text="Create feature";handler=()=>showFeatureList();
  }else if(currentViewName==="features" && currentFeature){
    text="Feature workspace";handler=()=>showFeatureList();
  }else if(currentViewName==="features" && currentProject){
    text="Features";handler=()=>{navigateTo("projects");showProjectList();loadProjects();};
  }else if(["validator","testplan","gap"].includes(currentViewName)){
    const labels = { validator: "Validator", testplan: "Test plan", gap: "Gap analysis" };
    text=labels[currentViewName];handler=()=>navigateTo("features");
  }else if(currentViewName==="cases" && currentFeature){
    text="Test cases";handler=()=>navigateTo("features");
  }else{
    show=false;
  }
  bar.classList.toggle("show",show);
  label.textContent=text;
  btn.onclick=handler||null;
}

window.clickBreadcrumb = function(stepId) {
  if (stepId === "projects") {
    navigateTo("projects");
  } else if (stepId === "features") {
    if (!currentProject) {
      toast("Please select a project first.");
      return;
    }
    currentFeature = null;
    navigateTo("features");
  } else if (stepId === "workspace") {
    if (!currentProject) {
      toast("Please select a project first.");
      return;
    }
    if (!currentFeature) {
      toast("Please select a feature first.");
      return;
    }
    navigateTo("features");
  }
};

// ---- status ----
async function refreshStatus(){
  if($("#status")&&!$("#status").dataset.loaded)$("#status").innerHTML=`<span class="stat"><span class="spin-inline"></span>Checking services…</span>`;
  try{const s=await api("/api/status");const c=s.counts||{};
  if($("#status"))$("#status").dataset.loaded="1";
  $("#status").innerHTML=
    `<span class="status-group">`+
      `<span class="stat" title="MongoDB connection">${dot(s.mongo_connected)}Mongo</span>`+
      `<span class="stat" title="Embeddings: ${esc(s.embedding?.provider||'')}${s.embedding?.dims?(' · '+s.embedding.dims+'-d'):''}${s.embedding?.health?.error?(' · '+s.embedding.health.error):''}">${dot(s.embedding?.health?.ok)}${esc(s.embedding?.model)}</span>`+
      `<span class="stat" title="LLM: ${esc(s.llm?.health?.error||s.llm?.provider||'')}">${dot(s.llm?.health?.ok)}${esc(s.llm?.model)}</span>`+
    `</span>`+
    `<span class="stat-metric" title="Features and test cases in scope"><span><b>${c.features||0}</b> features</span><span class="sep"></span><span><b>${c.test_cases||0}</b> cases</span></span>`+
    (s.boot?.ready?"":(s.boot?.stage==="error"
      ?`<span class="err" title="${esc(s.boot?.detail||"")}">⚠ ${esc(s.boot?.detail||"startup error")}</span>`
      :`<span class="stat" style="color:var(--amber)">${dot(false)}${esc(s.boot?.stage||"")}${s.boot?.detail?` · ${esc(s.boot.detail)}`:""}</span>`));
}catch(e){$("#status").innerHTML=`<span class="err">${esc(e.message)}</span>`;}}
const dot=ok=>`<span class="dot ${ok?"ok":"bad"}"></span>`;

// ---- dashboard ----
async function loadDashboard(){
  const root=$("#dash-root");if(!root)return;
  skIn("#dash-root",skeleton.dashboard());
  try{const d=await api("/api/dashboard");const c=d.counts;const g=d.coverage;const bt=d.by_type||{};
    // ── Overview KPI tiles (exact same fields/labels as before) ──
    const tiles=[["projects","Projects"],["features","Features"],["test_cases","Test cases"],
      ["test_steps","Steps"],["documents","Documents"],["repos","Repos"],["pull_requests","PRs"]];
    const kpis=tiles.map(([k,l])=>`<div class="rc-card hover rc-kpi"><div class="rc-kpi-v">${c[k]??0}</div><div class="rc-kpi-l">${esc(l)}</div></div>`).join("");
    // ── Coverage gauges (same two gauges + note as before) ──
    const cov=`<div class="dash-gauge"><div class="top"><span>Code coverage (cases hit by PRs)</span><b>${g.code_pct}%</b></div><div class="track"><div class="fill code" style="width:${g.code_pct}%"></div></div></div>`+
      `<div class="dash-gauge"><div class="top"><span>Automation Test Coverage (dev-written tests)</span><b>${g.automation_pct}%</b></div><div class="track"><div class="fill auto" style="width:${g.automation_pct}%"></div></div></div>`+
      `<div class="dash-cov-note">${g.covered_cases} covered · ${g.automated_cases} automated of ${c.test_cases} cases</div>`;
    // ── Test cases by type (same bars/data as before) ──
    const typePalette=[RC_COLORS.sky,RC_COLORS.violet,RC_COLORS.emerald,RC_COLORS.amber,RC_COLORS.rose,RC_COLORS.teal];
    const typeBars=Object.entries(bt).map(([t,n],i)=>({label:t,value:n,color:typePalette[i%typePalette.length]}));
    const byType=typeBars.length?rcBars(typeBars):`<span class="rc-empty">no data</span>`;
    // ── Projects rollup (same table/columns as before) ──
    const rollup=d.projects.length
      ? `<div style="overflow:auto"><table class="rc-table"><tr><th>Project</th><th>Features</th><th>Cases</th><th>Code %</th><th>Automation %</th><th>Repos</th><th>PRs</th></tr>`+
          d.projects.map(p=>`<tr><td>${esc(p.name)}</td><td>${p.features}</td><td>${p.test_cases}</td><td>${p.code_pct}%</td><td>${p.automation_pct}%</td><td>${p.repos}</td><td>${p.prs}</td></tr>`).join("")+`</table></div>`
      : `<span class="rc-empty">no projects yet</span>`;
    root.innerHTML=
      `<header class="dash-head"><div><h1>Overview</h1><p>Live across all projects.</p></div></header>`+
      `<div class="dash-metrics">${kpis}</div>`+
      `<div class="dash-row c2">`+
        rcSection("Coverage",`<div class="sub" style="color:var(--rc-s400);font-size:12px;margin:-8px 0 12px">Test cases exercised by code (mapped PRs) and by developer-written automated tests.</div>`+cov)+
        rcSection("Test cases by type",byType)+
      `</div>`+
      rcSection("Projects rollup",rollup);
  }catch(e){root.innerHTML=`<header class="dash-head"><div><h1>Overview</h1></div></header><div class="rc-card rc-section" style="border-color:rgba(251,113,133,.3);background:rgba(251,113,133,.08)"><div style="color:#fecaca;font-weight:600">Could not load dashboard</div><div style="color:#fda4af;margin-top:6px;font-size:13px">${esc(e.message)}</div><div style="margin-top:12px"><button class="ghost" onclick="loadDashboard()">Retry</button></div></div>`;}
}
const gauge=(label,pct,cls)=>`<div class="gauge"><div class="top"><span>${label}</span><b>${pct}%</b></div><div class="track"><div class="fill ${cls}" style="width:${pct}%"></div></div></div>`;

// ---- projects + repos ----
async function loadProjects(){
  if($("#project-cards-container")&&!$("#project-cards-container").dataset.loaded)skIn("#project-cards-container",skeleton.cards(6,"Loading projects"));
  try{let r=await api("/api/projects");
    if($("#project-cards-container"))$("#project-cards-container").dataset.loaded="1";
    if(r.projects.length){
      if(!currentProject||!r.projects.find(p=>p.id===currentProject))currentProject=r.projects[0].id;
    } else {
      currentProject="";
    }
    
    const opts=r.projects.map(p=>`<option value="${p.id}">${esc(p.name)} — ${p.repo_count} repos · ${p.feature_count} features</option>`).join("");
    if($("#proj-sel")){$("#proj-sel").innerHTML=opts;$("#proj-sel").value=currentProject;}
    if($("#f-project")){$("#f-project").innerHTML=opts;$("#f-project").value=currentProject;}
    if($("#cyc-proj")){$("#cyc-proj").innerHTML=opts;$("#cyc-proj").value=currentProject;}
    if($("#tcy-proj")){$("#tcy-proj").innerHTML=opts;$("#tcy-proj").value=currentProject;}
    if($("#mm-proj")){$("#mm-proj").innerHTML=opts;$("#mm-proj").value=currentProject;}
    if($("#dev-proj")){$("#dev-proj").innerHTML=opts;$("#dev-proj").value=currentProject;}
    if($("#tc-proj")){$("#tc-proj").innerHTML=`<option value="">All projects</option>`+opts;}
    
    // Project selection cards: click enters the project's feature list; management lives in the menu.
    if($("#project-cards-container")){
      $("#project-cards-container").innerHTML = r.projects.map(p => `
        <div class="entity-card" data-project-card="${p.id}" onclick="openProjectFeatures('${p.id}')">
            <button class="entity-menu-btn" title="Project options" onclick="event.stopPropagation();toggleProjectMenu('${p.id}')"><svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px;display:block"><circle cx="12" cy="5" r="2"></circle><circle cx="12" cy="12" r="2"></circle><circle cx="12" cy="19" r="2"></circle></svg></button>
          <div class="entity-menu" onclick="event.stopPropagation()">
            <button onclick="openProjectSettings('${p.id}')">Settings & repositories</button>
            <button onclick="renameProjectFromCard('${p.id}')">Rename</button>
            <button class="danger-option" onclick="deleteProjectFromCard('${p.id}')">Delete</button>
          </div>
          <div class="entity-name">${esc(p.name)}</div>
          <div class="entity-meta">${p.feature_count} feature${p.feature_count===1?"":"s"} · ${p.repo_count} repositor${p.repo_count===1?"y":"ies"}</div>
          <div class="entity-foot"><span>Open features</span><span class="entity-arrow">›</span></div>
        </div>
      `).join("") || `<div class="empty-state" style="grid-column: 1 / -1"><div class="empty-state-icon">+</div><h3>No projects yet</h3><p>Create your first project to continue.</p><button class="go" onclick="showProjectCreate()">Create project</button></div>`;

      const activeProj = r.projects.find(p => p.id === currentProject);
      if (activeProj) {
        $("#active-proj-title").textContent = activeProj.name;
        $("#active-proj-stats").textContent = `${activeProj.repo_count} repositories · ${activeProj.feature_count} features`;
        $("#project-feature-count").textContent=activeProj.feature_count;
        $("#project-repo-count").textContent=activeProj.repo_count;
        api(`/api/test-cases?project_id=${activeProj.id}&status=all&limit=1`).then(x=>$("#project-case-count").textContent=x.total).catch(()=>$("#project-case-count").textContent="—");
        if($("#features-page-title"))$("#features-page-title").textContent=activeProj.name;
        if($("#features-project-context"))$("#features-project-context").textContent=`${activeProj.feature_count} feature${activeProj.feature_count===1?"":"s"}`;
      } else {
        if($("#active-proj-title")) $("#active-proj-title").textContent = "";
        if($("#active-proj-stats")) $("#active-proj-stats").textContent = "";
        if($("#project-feature-count")) $("#project-feature-count").textContent = "0";
        if($("#project-repo-count")) $("#project-repo-count").textContent = "0";
        if($("#project-case-count")) $("#project-case-count").textContent = "—";
        if($("#features-page-title")) $("#features-page-title").textContent = "";
        if($("#features-project-context")) $("#features-project-context").textContent = "";
      }
    }
    if(!$("#project-detail-page").hidden)loadRepos();
  }catch(e){}
}

function showProjectList(){
  if($("#project-list-toolbar"))$("#project-list-toolbar").style.display="";
  if($("#proj-create-card"))$("#proj-create-card").style.display="none";
  if($("#project-cards-container"))$("#project-cards-container").style.display="";
  if($("#proj-new-btn"))$("#proj-new-btn").style.display="";
  if($("#project-list-page"))$("#project-list-page").hidden=false;
  if($("#project-detail-page"))$("#project-detail-page").hidden=true;
  updateBackbar();
}
function showProjectCreate(){
  if($("#project-list-page"))$("#project-list-page").hidden=false;
  if($("#project-detail-page"))$("#project-detail-page").hidden=true;
  if($("#project-list-toolbar"))$("#project-list-toolbar").style.display="none";
  if($("#project-cards-container"))$("#project-cards-container").style.display="none";
  if($("#proj-create-card"))$("#proj-create-card").style.display="block";
  updateBackbar();
}
function showProjectDetail(){
  $("#project-list-page").hidden=true;$("#project-detail-page").hidden=false;
  updateBackbar();
}
window.openProjectFeatures = async pid => {
  currentProject = pid;
  currentFeature = null;
  navigateTo("features");
  await loadFeatures();
  showFeatureList();
};
window.openProjectSettings = async pid => {
  currentProject = pid;
  showProjectDetail();
  await loadProjects();
  renderBreadcrumbs();
  // Apply the project's saved provider so the PAT/repo panel starts on the right toggle.
  try {
    const proj = await api(`/api/projects/${pid}`);
    const dp = (proj.default_git_provider || "github").toLowerCase();
    PD_PROVIDER = dp;
    document.querySelectorAll("[data-pd-provider]").forEach(b => {
      const isMatch = b.dataset.pdProvider === dp;
      b.classList.toggle("active", isMatch);
      b.style.display = isMatch ? "" : "none";
    });
    if ($("#pd-pat")) $("#pd-pat").placeholder = dp === "gitlab" ? "glpat-..." : "ghp_...";
  } catch(e) { /* fall through to default github */ }
  refreshProjectPatStatus();
};
window.selectProject = window.openProjectSettings;
window.toggleProjectMenu = pid => {
  document.querySelectorAll("[data-project-card]").forEach(card=>{
    if(card.dataset.projectCard!==pid)card.classList.remove("menu-open");
  });
  const card=document.querySelector(`[data-project-card="${pid}"]`);
  if(card)card.classList.toggle("menu-open");
};
document.addEventListener("click",e=>{
  if(!e.target.closest("[data-project-card]"))document.querySelectorAll("[data-project-card]").forEach(card=>card.classList.remove("menu-open"));
});
if($("#project-detail-back"))$("#project-detail-back").onclick=()=>showProjectList();
if($("#proj-features-btn"))$("#proj-features-btn").onclick=()=>{currentFeature=null;navigateTo("features");showFeatureList();};
if($("#features-back-project"))$("#features-back-project").onclick=()=>{navigateTo("projects");showProjectList();loadProjects();};

if($("#f-project"))$("#f-project").onchange=async e=>{currentProject=e.target.value;loadFeatures();renderBreadcrumbs();await loadFeatureTicketOptions();};

// New Project — multi-step form state
const NEW_PROJ = {
  provider: "github",
  appRepos: [],      // [{full_name, label}]
  testRepos: [],
  available: [],     // last loaded list
};

function _resetNewProj(){
  NEW_PROJ.provider = "github";
  NEW_PROJ.appRepos = [];
  NEW_PROJ.testRepos = [];
  NEW_PROJ.available = [];
  $("#new-proj-name").value = "";
  $("#new-proj-desc").value = "";
  $("#new-proj-pat").value = "";
  $("#new-proj-name-err").textContent = "";
  $("#new-proj-pat-status").textContent = "";
  $("#new-proj-jira-status").textContent = "";
  $("#new-proj-confluence-status").textContent = "";
  $("#proj-create-status").textContent = "";
  $("#new-proj-jira").innerHTML = '<option value="">— none —</option>';
  $("#new-proj-confluence").innerHTML = '<option value="">— none —</option>';
  _renderCpRepoPickers();
  document.querySelectorAll(".cp-prov").forEach(b => {
    b.classList.toggle("active", b.dataset.provider === "github");
  });
}

function _renderCpRepoPickers(){
  const stagedAppFullNames = new Set(NEW_PROJ.appRepos.map(r => r.full_name));
  const stagedTestFullNames = new Set(NEW_PROJ.testRepos.map(r => r.full_name));
  const stagedMapFor = key => {
    const bucket = key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
    return new Map(bucket.map(r => [r.full_name, r]));
  };
  const render = (el, staged, otherStaged, sectionKey) => {
    if(!el) return;
    el.innerHTML = "";
    if(NEW_PROJ.available.length === 0){
      el.innerHTML = '<div class="muted cp-repo-empty">Load repositories above to pick.</div>';
      return;
    }
    const stagedMap = stagedMapFor(sectionKey);
    // Show staged first, then everything not staged in either section
    const lines = [];
    NEW_PROJ.available.forEach(r => {
      const isStaged = staged.has(r.full_name);
      const usedElsewhere = otherStaged.has(r.full_name);
      if(usedElsewhere) return;
      const stagedRepo = stagedMap.get(r.full_name);
      lines.push(`<div class="cp-repo-row${isStaged?" staged":""}">
        <div class="cp-repo-main">
          <div class="cp-repo-name"><b>${esc(r.full_name)}</b> <span class="cp-repo-meta">${r.private?"private":"public"}${r.default_branch?" · "+esc(r.default_branch):""}</span></div>
          ${isStaged
            ? `<input class="cp-repo-label-input" data-key="${sectionKey}" data-fn="${esc(r.full_name)}" value="${esc((stagedRepo && stagedRepo.label) || "")}" placeholder="Display name (e.g. Backend API)"/>`
            : ``}
        </div>
        <div class="cp-repo-actions">
        ${isStaged
          ? `<button type="button" class="cp-repo-remove" data-key="${sectionKey}" data-fn="${esc(r.full_name)}">remove</button>`
          : `<button type="button" class="cp-repo-add" data-key="${sectionKey}" data-fn="${esc(r.full_name)}">add</button>`}
        </div>
      </div>`);
    });
    el.innerHTML = lines.join("") || '<div class="muted cp-repo-empty">No more repositories available.</div>';
  };
  render($("#new-proj-app-picker"), stagedAppFullNames, stagedTestFullNames, "app");
  render($("#new-proj-test-picker"), stagedTestFullNames, stagedAppFullNames, "test");
  $("#new-proj-app-count").textContent = NEW_PROJ.appRepos.length;
  $("#new-proj-test-count").textContent = NEW_PROJ.testRepos.length;
}

document.addEventListener("click", e => {
  const t = e.target.closest(".cp-repo-add, .cp-repo-remove");
  if(!t) return;
  const fn = t.dataset.fn;
  const key = t.dataset.key;
  const bucket = key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
  const isRemove = t.classList.contains("cp-repo-remove");
  const meta = NEW_PROJ.available.find(r => r.full_name === fn);
  if(isRemove){
    const idx = bucket.findIndex(r => r.full_name === fn);
    if(idx >= 0) bucket.splice(idx, 1);
  } else if(meta){
    bucket.push({full_name: fn, label: (fn.split("/").pop() || fn).replace(/[-_]+/g, " ")});
  }
  _renderCpRepoPickers();
});

document.addEventListener("input", e => {
  const t = e.target.closest(".cp-repo-label-input");
  if(!t) return;
  const fn = t.dataset.fn;
  const key = t.dataset.key;
  const bucket = key === "app" ? NEW_PROJ.appRepos : NEW_PROJ.testRepos;
  const repo = bucket.find(r => r.full_name === fn);
  if(repo) repo.label = t.value;
});

document.querySelectorAll(".cp-prov").forEach(btn => {
  btn.onclick = () => {
    NEW_PROJ.provider = btn.dataset.provider;
    document.querySelectorAll(".cp-prov").forEach(b => b.classList.toggle("active", b === btn));
    NEW_PROJ.available = [];
    NEW_PROJ.appRepos = [];
    NEW_PROJ.testRepos = [];
    $("#new-proj-pat").placeholder = NEW_PROJ.provider === "gitlab" ? "glpat-..." : "ghp_...";
    $("#new-proj-pat-status").textContent = "";
    _renderCpRepoPickers();
  };
});

async function loadJiraProjectsForCreate(){
  $("#new-proj-jira-status").textContent = "Loading…";
  try{
    const r = await api("/api/atlassian/accessible-jira-projects");
    const sel = $("#new-proj-jira");
    const avail = (r.projects||[]).filter(p => !p.in_use);
    sel.innerHTML = '<option value="">— none —</option>' +
      avail.map(p => `<option value="${esc(p.key)}" data-name="${esc(p.name)}">${esc(p.key)} — ${esc(p.name)}</option>`).join("");
    const usedCount = (r.projects||[]).length - avail.length;
    $("#new-proj-jira-status").textContent = `${avail.length} project(s) available` + (usedCount?` · ${usedCount} already linked`:"");
  }catch(e){
    $("#new-proj-jira-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
}

async function loadConfluenceSpacesForCreate(){
  $("#new-proj-confluence-status").textContent = "Loading…";
  try{
    const r = await api("/api/atlassian/accessible-confluence-spaces");
    const sel = $("#new-proj-confluence");
    sel.innerHTML = '<option value="">— none —</option>' +
      (r.spaces||[]).map(s => `<option value="${esc(s.key)}" data-name="${esc(s.name)}">${esc(s.key)} — ${esc(s.name)}</option>`).join("");
    $("#new-proj-confluence-status").textContent = `${(r.spaces||[]).length} space(s) available`;
  }catch(e){
    $("#new-proj-confluence-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
}

if($("#new-proj-jira-refresh")) $("#new-proj-jira-refresh").onclick = loadJiraProjectsForCreate;
if($("#new-proj-confluence-refresh")) $("#new-proj-confluence-refresh").onclick = loadConfluenceSpacesForCreate;

if($("#new-proj-load-repos")) $("#new-proj-load-repos").onclick = async () => {
  const pat = $("#new-proj-pat").value.trim();
  if(!pat){ $("#new-proj-pat-status").innerHTML = '<span class="err">Enter a PAT first</span>'; return; }
  setBusy("#new-proj-load-repos", true);
  $("#new-proj-pat-status").innerHTML = `<span class="spin-inline"></span>Loading repositories…`;
  // We need a transient project context to call the API. Pre-create the project? No — better:
  // hit a paginated repo-list endpoint that accepts X-Provider-PAT *without* a project id by
  // routing through the legacy GitHub paginated path.
  try {
    let repos = [];
    for(let page = 1; page <= 5; page++){
      const url = `/api/git/accessible-repos?provider=${encodeURIComponent(NEW_PROJ.provider)}&page=${page}`;
      const r = await api(url, {headers:{"X-Provider-PAT": pat}});
      if(!r.repos || !r.repos.length) break;
      repos = repos.concat(r.repos);
      if(r.repos.length < 30) break;
    }
    NEW_PROJ.available = repos;
    _renderCpRepoPickers();
    $("#new-proj-pat-status").innerHTML = `<span class="ok">${repos.length} repos loaded</span>`;
  } catch(e){
    $("#new-proj-pat-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  } finally {
    setBusy("#new-proj-load-repos", false);
  }
};

if($("#proj-new-btn")) $("#proj-new-btn").onclick = () => {
  _resetNewProj();
  showProjectCreate();
  $("#new-proj-name").focus();
  // Pre-load Jira lists if the user already configured them in Settings; silently
  // no-op when not configured (the status line surfaces the reason).
  loadJiraProjectsForCreate();
  loadConfluenceSpacesForCreate();
};

if($("#proj-create-back")) $("#proj-create-back").onclick = () => {
  showProjectList();
};

if($("#proj-create-cancel")) $("#proj-create-cancel").onclick = () => {
  showProjectList();
};

if($("#proj-create-save")) $("#proj-create-save").onclick = async () => {
  const name = $("#new-proj-name").value.trim();
  $("#new-proj-name-err").textContent = "";
  if(!name){
    $("#new-proj-name-err").textContent = "Project name is required.";
    return;
  }
  const description = $("#new-proj-desc").value.trim();
  const jiraOpt = $("#new-proj-jira").selectedOptions[0];
  const jiraKey = jiraOpt && jiraOpt.value ? jiraOpt.value : null;
  const jiraName = jiraOpt && jiraOpt.value ? (jiraOpt.dataset.name || jiraOpt.textContent) : null;
  const conOpt = $("#new-proj-confluence").selectedOptions[0];
  const conKey = conOpt && conOpt.value ? conOpt.value : null;
  const conName = conOpt && conOpt.value ? (conOpt.dataset.name || conOpt.textContent) : null;
  const pat = $("#new-proj-pat").value.trim();

  $("#proj-create-status").innerHTML = `<span class="spin-inline"></span>Creating project…`;
  setBusy("#proj-create-save", true);
  $("#proj-create-save").disabled = true;
  $("#proj-create-cancel").disabled = true;
  const finishCreate = () => { setBusy("#proj-create-save", false); $("#proj-create-save").disabled = false; $("#proj-create-cancel").disabled = false; };
  let createdId = null;
  try {
    const r = await api("/api/projects", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        name, description,
        jira_project_key: jiraKey, jira_project_name: jiraName,
        confluence_space_key: conKey, confluence_space_name: conName,
        default_git_provider: NEW_PROJ.provider,
      })
    });
    createdId = r.id;
  } catch(e){
    $("#proj-create-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    finishCreate();
    return;
  }

  if(pat){
    try{
      const patUrl = NEW_PROJ.provider === "gitlab"
        ? `/api/projects/${createdId}/gitlab/pat`
        : `/api/projects/${createdId}/github/pat`;
      await api(patUrl, {method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify({pat})});
    } catch(e){
      toast(`Project created, but PAT save failed: ${e.message}`, true);
    }
    const allRepos = [
      ...NEW_PROJ.appRepos.map(r => ({...r, repo_type: "app"})),
      ...NEW_PROJ.testRepos.map(r => ({...r, repo_type: "test"}))
    ];
    let connected = 0;
    if(allRepos.length) $("#proj-create-status").innerHTML = `<span class="spin-inline"></span>Connecting ${allRepos.length} repositor${allRepos.length===1?"y":"ies"}…`;
    for(const r of allRepos){
      try{
        await api(`/api/projects/${createdId}/repos`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            repo_full_name: r.full_name,
            label: (r.label || "").trim() || r.full_name,
            repo_type: r.repo_type,
            git_provider: NEW_PROJ.provider,
            kind: r.repo_type === "test" ? "other" : "BE",
          })
        });
        connected += 1;
      }catch(e){
        toast(`Repo ${r.full_name} failed: ${e.message}`, true);
      }
    }
    if(connected > 0) toast(`Project created · ${connected} repo(s) connected`);
    else toast("Project created");
  } else {
    toast("Project created");
  }

  $("#proj-create-status").innerHTML = `<span class="spin-inline"></span>Opening project…`;
  currentProject = createdId;
  showProjectList();
  try {
    await loadProjects();
    await openProjectFeatures(createdId);
    renderBreadcrumbs();
  } finally {
    finishCreate();
    $("#proj-create-status").textContent = "";
  }
};

// Rename/delete handlers
if($("#proj-rename-btn")) $("#proj-rename-btn").onclick = async () => {
  if(!currentProject) return;
  const title = $("#active-proj-title").textContent;
  const name = await uiPrompt("Rename project", "New name for the project", title);
  if(!name) return;
  try {
    await api(`/api/projects/${currentProject}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name})
    });
    loadProjects();
    toast("Project renamed successfully!");
  } catch(e) {
    toast(e.message, true);
  }
};
function projectCardName(pid){
  return document.querySelector(`[data-project-card="${pid}"] .entity-name`)?.textContent?.trim()||"Project";
}
window.renameProjectFromCard=async(pid)=>{
  const name=projectCardName(pid);
  const next = await uiPrompt("Rename project", "New name for the project", name||"");
  if(!next)return;
  try{
    await api(`/api/projects/${pid}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:next})});
    loadProjects();toast("Project renamed");
  }catch(e){toast(e.message,true);}
};
if($("#proj-del-btn")) $("#proj-del-btn").onclick = async () => {
  if(!currentProject) return;
  const projectId=currentProject;
  openCaseConfirmation({
    title:"Delete project",
    copy:"This removes this project, its features, repositories, and project-only test-case links. Test cases linked to features in another project will remain.",
    summary:`<b>${esc($("#active-proj-title").textContent)}</b><div class="muted" style="margin-top:6px">${esc($("#active-proj-stats").textContent)}</div>`,
    confirmLabel:"Delete project",danger:true,
    onConfirm:async()=>{
      const r=await api(`/api/projects/${projectId}`, {method:"DELETE"});
      currentProject=null;showProjectList();loadProjects();refreshStatus();
      toast(`Project deleted · ${r.features} feature(s), ${r.removed_orphan_cases} orphan test case(s) removed, ${r.preserved_shared_cases} shared test case(s) preserved`);
    }
  });
};
window.deleteProjectFromCard=async(pid)=>{
  const name=projectCardName(pid);
  currentProject=pid;
  openCaseConfirmation({
    title:"Delete project",
    copy:"This removes this project, its features, repositories, and project-only test-case links. Test cases linked to another project remain available.",
    summary:`<b>${esc(name||"Project")}</b>`,
    confirmLabel:"Delete project",danger:true,
    onConfirm:async()=>{
      const r=await api(`/api/projects/${pid}`, {method:"DELETE"});
      currentProject=null;showProjectList();loadProjects();refreshStatus();
      toast(`Project deleted · ${r.features} feature(s), ${r.removed_orphan_cases} orphan test case(s) removed, ${r.preserved_shared_cases} shared test case(s) preserved`);
    }
  });
};

// Project-detail provider toggle + PAT management
let PD_PROVIDER = "github";
document.querySelectorAll("[data-pd-provider]").forEach(btn => {
  btn.onclick = async () => {
    PD_PROVIDER = btn.dataset.pdProvider;
    document.querySelectorAll("[data-pd-provider]").forEach(b => b.classList.toggle("active", b === btn));
    if($("#pd-pat")) $("#pd-pat").placeholder = PD_PROVIDER === "gitlab" ? "glpat-..." : "ghp_...";
    // Persist the change so future PR coverage routes through the right API.
    if (currentProject) {
      try {
        await api(`/api/projects/${currentProject}`, {
          method:"PATCH", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({default_git_provider: PD_PROVIDER})
        });
      } catch(e) { /* non-fatal — toggle still takes effect for this session */ }
    }
    refreshProjectPatStatus();
  };
});

async function refreshProjectPatStatus(){
  if(!currentProject || !$("#pd-pat-status")) return;
  try{
    const url = PD_PROVIDER === "gitlab"
      ? `/api/projects/${currentProject}/gitlab/pat`
      : `/api/projects/${currentProject}/github/pat`;
    const r = await api(url);
    $("#pd-pat-status").innerHTML = r.configured
      ? `<span class="ok">${PD_PROVIDER==="gitlab"?"GitLab":"GitHub"} PAT configured</span>`
      : `<span class="muted">No ${PD_PROVIDER==="gitlab"?"GitLab":"GitHub"} PAT set for this project</span>`;
  }catch(e){
    $("#pd-pat-status").innerHTML = `<span class="muted">PAT status unknown</span>`;
  }
}

if($("#pd-pat-save")) $("#pd-pat-save").onclick = async () => {
  const pat = $("#pd-pat").value.trim();
  if(!pat){ toast("Enter a PAT first", true); return; }
  const url = PD_PROVIDER === "gitlab"
    ? `/api/projects/${currentProject}/gitlab/pat`
    : `/api/projects/${currentProject}/github/pat`;
  try{
    await api(url, {method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify({pat})});
    $("#pd-pat").value = "";
    toast("PAT saved");
    refreshProjectPatStatus();
  }catch(e){ toast(e.message, true); }
};

if($("#pd-pat-clear")) $("#pd-pat-clear").onclick = async () => {
  const url = PD_PROVIDER === "gitlab"
    ? `/api/projects/${currentProject}/gitlab/pat`
    : `/api/projects/${currentProject}/github/pat`;
  try{
    await api(url, {method:"DELETE"});
    $("#pd-pat").value = "";
    toast("PAT cleared");
    refreshProjectPatStatus();
  }catch(e){ toast(e.message, true); }
};

if($("#repo-add")) $("#repo-add").onclick=async()=>{
  const url=$("#repo-url").value.trim();
  if(!url || !currentProject) return;
  try{
    await api(`/api/projects/${currentProject}/repos`,{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        url,
        kind: $("#repo-kind").value,
        repo_type: ($("#repo-type") ? $("#repo-type").value : "app"),
        git_provider: PD_PROVIDER,
      })
    });
    $("#repo-url").value="";
    loadRepos();
    toast("Repo added & watching");
  }catch(e){ toast(e.message,true); }
};

if($("#repo-pick")) $("#repo-pick").onclick=async()=>{
  if(!currentProject) return;
  try{
    const url = PD_PROVIDER === "gitlab"
      ? `/api/projects/${currentProject}/gitlab/accessible-repos?page=1`
      : `/api/projects/${currentProject}/github/accessible-repos?page=1`;
    const r = await api(url);
    $("#myrepos").innerHTML = (r.repos||[]).map(x =>
      `<option value="${esc(x.full_name)}">${x.private?"private":"public"}${x.language?(" · "+esc(x.language)):""}</option>`
    ).join("");
    toast(`${(r.repos||[]).length} repos loaded — type in the box to filter`);
  }catch(e){ toast(e.message,true); }
};

async function loadRepos(){if(!currentProject||!$("#repo-list"))return;
  try{const r=await api(`/api/projects/${currentProject}/repos`);
    $("#repo-list").innerHTML=r.repos.map(rp=>`
      <div class="repo-item-card">
        <div style="display: flex; align-items: center; gap: 10px;">
          <div>
            <div style="font-weight: 600; font-size: 13.5px; color: var(--text);">${esc(rp.full_name)}</div>
            <div style="display: flex; gap: 6px; margin-top: 4px; flex-wrap: wrap;">
              <span class="badge ${rp.kind.toLowerCase()}" style="font-size: 10px;">${esc(rp.kind)}</span>
              <span class="badge" style="font-size: 10px;">${rp.pr_count} PRs</span>
              <span style="font-size: 10.5px; display: flex; align-items: center; gap: 4px;" class="muted">
                <span class="dot ${rp.watch ? 'ok' : ''}" style="margin: 0; width: 6px; height: 6px;"></span>
                ${rp.watch ? 'watching' : 'paused'}
              </span>
            </div>
          </div>
        </div>
        
        <div style="display: flex; gap: 6px; align-items: center;">
          <button class="go" style="padding: 6px 12px; font-size: 12px; display: flex; align-items: center; gap: 4px;" onclick="gotoAnalyze('${rp.id}','${currentProject}')">Analyze</button>
          <button class="ghost" style="padding: 5px 10px; font-size: 11.5px;" onclick="syncRepo('${rp.id}')">Sync</button>
          <button class="ghost" style="padding: 5px 10px; font-size: 11.5px;" onclick="toggleWatch('${rp.id}',${!rp.watch})">
            ${rp.watch ? 'Pause' : 'Resume'}
          </button>
          <button class="danger" style="padding: 6px 9px; font-size: 11.5px; display: flex; align-items: center; justify-content: center;" onclick="delRepo('${rp.id}')">Remove</button>
        </div>
      </div>
    `).join("")||`<span class="muted">no repos yet</span>`;
  }catch(e){}}

window.gotoAnalyze=async(rid,pid)=>{
  currentProject=pid;
  document.querySelectorAll("nav button").forEach(x=>x.classList.toggle("active",x.dataset.view==="cycles"));
  document.querySelectorAll(".view").forEach(s=>s.hidden=(s.id!=="view-cycles"));
  $("#view-title").textContent=TITLES.cycles;
  await loadProjects(); if($("#cyc-proj"))$("#cyc-proj").value=pid; await loadCycleRepos();
  document.querySelectorAll(".cyc-repo-chk").forEach(c=>{c.checked=(c.value===rid);}); loadCycles();
  toast("Repo selected — set days & click Analyze changes");};
window.delRepo=async id=>{if(!await uiConfirm("Remove this repo and its tracked PRs?", "Delete Repository", "Remove", true))return;await api(`/api/repos/${id}`,{method:"DELETE"});loadRepos();toast("Repo removed");};
window.syncRepo=async id=>{await api(`/api/repos/${id}/sync`,{method:"POST"});$("#sync-status").textContent="sync started…";setTimeout(()=>{loadRepos();loadSyncStatus();},1500);};
window.toggleWatch=async(id,w)=>{await api(`/api/repos/${id}/watch`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({watch:w})});loadRepos();};
async function loadSyncStatus(){try{const s=await api("/api/sync/status");if($("#sync-status"))$("#sync-status").innerHTML=`poller every ${s.poll_interval_s}s · ${s.github_authenticated?"authenticated":"public-only"} · ingested ${s.ingested}, mapped ${s.mapped}`+(s.errors&&s.errors.length?` · <span class="err">${esc(s.errors.slice(-1)[0])}</span>`:"");}catch(e){}}

// ---- features ----
function showFeatureList(){
  if($("#feature-list-page"))$("#feature-list-page").hidden=false;
  if($("#feature-create-page"))$("#feature-create-page").hidden=true;
  if($("#detail-card"))$("#detail-card").hidden=true;
  currentFeature=null;renderBreadcrumbs();updateBackbar();
}
async function loadFeatureTicketOptions(){
  const pid=$("#f-project").value||currentProject||"";
  const select=$("#f-key");
  const status=$("#f-key-status");
  if(!select||!status)return;
  select.innerHTML=`<option value="">No Jira epic</option>`;
  status.textContent="Associate an Epic so PRs auto-link to this feature (ticket → epic → feature). Each Epic maps to one feature only.";
  if(!pid)return;
  try{
    const r=await api(`/api/projects/${pid}`);
    const jiraProjectKey=(r.jira_project_key||"").trim();
    if(!jiraProjectKey){
      status.textContent="No Jira project is linked to this project.";
      return;
    }
    status.textContent=`Loading available Epics from ${jiraProjectKey}…`;
    const issues=await api(`/api/projects/${pid}/jira-issues`);
    const items=issues.issues||[];
    select.innerHTML=`<option value="">No Jira epic</option>`+items.map(item=>{
      return `<option value="${esc(item.key)}">${esc(item.key)} — ${esc(item.summary)}</option>`;
    }).join("");
    status.textContent=items.length?`${items.length} unassociated Epic(s) available from ${jiraProjectKey}`:`No unassociated Epics found in ${jiraProjectKey}`;
  }catch(e){
    status.innerHTML=`<span class="err">${esc(e.message)}</span>`;
  }
}
async function showFeatureCreate(){
  $("#feature-list-page").hidden=true;$("#feature-create-page").hidden=false;$("#detail-card").hidden=true;
  $("#f-name").value="";$("#f-key").innerHTML=`<option value="">No Jira ticket</option>`;$("#f-file").value="";$("#f-text").value="";$("#f-filelist").textContent="";$("#f-status").textContent="";$("#f-log").textContent="";$("#f-log").style.display="none";if($("#f-match-key"))$("#f-match-key").value="";
  await loadFeatureTicketOptions();
  updateBackbar();
}
if($("#feature-new-btn"))$("#feature-new-btn").onclick=()=>showFeatureCreate();
if($("#feature-create-back"))$("#feature-create-back").onclick=showFeatureList;
$("#f-file").onchange=e=>{const fs=[...e.target.files].map(f=>f.name);$("#f-filelist").textContent=fs.length?`${fs.length} file(s): ${fs.join(", ")}`:"";};
const FOCUS_TYPES=["functional","e2e","api","nfr"];
function focusVals(){return FOCUS_TYPES.reduce((o,t)=>{o[t]=parseInt($("#foc-"+t).value)||0;return o;},{});}
let FOCUS_PREVIOUS=focusVals();
let FOCUS_PARTNER=null;
function largestFocusOther(changed,values,exclude=[]){
  return FOCUS_TYPES.filter(t=>t!==changed&&!exclude.includes(t))
    .sort((a,b)=>values[b]-values[a]||FOCUS_TYPES.indexOf(a)-FOCUS_TYPES.indexOf(b))[0];
}
function paintFocus(){
  const values=focusVals();
  FOCUS_TYPES.forEach(t=>{
    $("#foc-"+t+"-v").textContent=values[t]+"%";
    $("#foc-"+t).style.setProperty("--fill",values[t]+"%");
  });
  $("#foc-total").textContent=FOCUS_TYPES.reduce((sum,t)=>sum+values[t],0)+"%";
}
function rebalanceFocus(changed){
  const values=focusVals();
  const previous=FOCUS_PREVIOUS;
  const changedValue=Math.max(0,Math.min(100,values[changed]));
  let delta=changedValue-(previous[changed]||0);
  values[changed]=changedValue;
  const exhausted=[];
  while(delta!==0){
    let partner=FOCUS_PARTNER;
    if(!partner||partner===changed||exhausted.includes(partner)){
      partner=largestFocusOther(changed,values,exhausted);
      FOCUS_PARTNER=partner;
    }
    if(!partner)break;
    if(delta>0){
      const taken=Math.min(delta,values[partner]);
      values[partner]-=taken;delta-=taken;
      if(values[partner]===0)exhausted.push(partner);
    }else{
      values[partner]+=-delta;delta=0;
    }
  }
  FOCUS_TYPES.forEach(t=>$("#foc-"+t).value=values[t]);
  FOCUS_PREVIOUS={...values};
  paintFocus();
}
FOCUS_TYPES.forEach(t=>{
  const slider=$("#foc-"+t);
  const start=()=>{FOCUS_PARTNER=largestFocusOther(t,FOCUS_PREVIOUS);};
  slider.addEventListener("pointerdown",start);
  slider.addEventListener("focus",()=>{if(!FOCUS_PARTNER)start();});
  slider.addEventListener("input",()=>rebalanceFocus(t));
  slider.addEventListener("change",()=>{FOCUS_PARTNER=null;FOCUS_PREVIOUS=focusVals();});
  slider.addEventListener("blur",()=>{FOCUS_PARTNER=null;});
});
paintFocus();
$("#f-go").onclick=async()=>{
  const name=$("#f-name").value.trim();
  // --- validation with visible, non-scrolling feedback ---
  const fail=(msg,focusEl)=>{$("#f-status").innerHTML=`<span class="err">${esc(msg)}</span>`;toast(msg,true);if(focusEl)focusEl.focus();};
  if(!name){fail("Enter a feature name to continue.",$("#f-name"));return;}
  const pid=$("#f-project").value||currentProject||"";
  const splitLinks=el=>((el&&el.value)||"").split(/[\s,]+/).map(s=>s.trim()).filter(Boolean);
  const conflList=splitLinks($("#f-confluence"));
  const figmaList=splitLinks($("#f-figma"));
  if(!$("#f-file").files.length&&!$("#f-text").value.trim()&&!conflList.length&&!figmaList.length){
    fail("Add at least one source — upload a document, paste requirement text, or add a Confluence/Figma link.");return;}
  const fd=new FormData();fd.append("name",name);fd.append("project_id",pid);fd.append("key",$("#f-key").value.trim());fd.append("match_key",(($("#f-match-key")&&$("#f-match-key").value)||"").trim());
  for(const f of $("#f-file").files)fd.append("files",f);fd.append("text",$("#f-text").value);
  fd.append("focus",JSON.stringify(focusVals()));
  conflList.forEach(u=>fd.append("confluence_url",u));
  figmaList.forEach(u=>fd.append("figma_url",u));
  $("#f-go").disabled=true;setBusy("#f-go",true);
  $("#f-status").innerHTML=`<span class="muted">Uploading sources and starting generation…</span>`;
  $("#f-log").style.display="block";$("#f-log").textContent="Starting generation…";
  try{const r=await api("/api/features",{method:"POST",body:fd});
    $("#f-status").innerHTML=`<span class="ok">✓ ${r.doc_count} document(s) accepted · ${r.chunks} chunk(s) prepared.</span> Live progress below.`;
    toast("Generation started");
    // Optional sheet import alongside ingest — fires its own job.
    const sheet = $("#f-sheet") && $("#f-sheet").files && $("#f-sheet").files[0];
    if (sheet && r.feature_id && pid) {
      try {
        const sfd = new FormData(); sfd.append("file", sheet);
        const sr = await fetch(`/api/projects/${pid}/features/${r.feature_id}/tests/import`,
          { method: "POST", body: sfd });
        const sj = await sr.json();
        if (sr.ok) toast(`Sheet queued for import (${sheet.name})`);
        else toast(`Sheet import failed: ${sj.detail||sr.status}`, true);
      } catch(e) { toast("Sheet import failed: " + e.message, true); }
    }
    watchGen(r.job_id, r.feature_id);
  }catch(e){$("#f-status").innerHTML=`<span class="err">✕ Couldn't start generation: ${esc(e.message)}</span>`;toast("Generation failed: "+e.message,true);$("#f-go").disabled=false;setBusy("#f-go",false);}};
if ($("#f-sheet-template")) $("#f-sheet-template").onclick = (e) => {
  e.preventDefault();
  // No feature yet — use a known feature template route, or fall back to /api/features/_/...
  // The template endpoint doesn't care about the feature id; any will do.
  const fid = currentFeature || "_";
  window.location.href = `/api/features/${fid}/tests/import/template?format=xlsx`;
};
function fmtTok(n){return Number(n||0).toLocaleString();}
function fmtUsd(c){return (c==null)?"—":("$"+Number(c).toFixed(Number(c)<1?4:2));}
function usageLogLines(u){
  if(!u||!u.total_tokens)return [];
  const out=["","── LLM tokens ──"];
  Object.entries(u.by_model||{}).sort((a,b)=>b[1].total_tokens-a[1].total_tokens).forEach(([m,d])=>{
    out.push(`${m}${d.estimated?" (~est)":""}: ${fmtTok(d.total_tokens)} tok  (${fmtTok(d.prompt_tokens)} in / ${fmtTok(d.completion_tokens)} out)  ${fmtUsd(d.cost_usd)}`);
  });
  out.push(`TOTAL: ${fmtTok(u.total_tokens)} tok · ${fmtUsd(u.cost_usd)}`);
  return out;
}
function renderJobLog(target,j){
  const el=$(target);if(!el)return;
  const logs=(j.logs||[]).map(x=>`${x.progress==null?"   ":String(x.progress).padStart(3)+"%"}  ${x.stage||""}`);
  if(j.error)logs.push(`ERR  ${j.error}`);
  logs.push(...usageLogLines(j.usage));
  el.style.display=logs.length?"block":"none";el.textContent=logs.join("\n");el.scrollTop=el.scrollHeight;
}
async function loadUsage(){
  const totals=$("#usage-totals");if(!totals)return;
  try{
    const r=await api("/api/usage");   // global view — the table breaks it down by project
    const t=r.totals||{};
    totals.innerHTML=[
      ["Total tokens",fmtTok(t.total_tokens),""],
      ["Input tokens",fmtTok(t.prompt_tokens),""],
      ["Output tokens",fmtTok(t.completion_tokens),""],
      ["Estimated cost",fmtUsd(t.cost_usd),"is-cost"]
    ].map(([l,v,cls])=>`<div class="usage-stat ${cls}"><b>${v}</b><span>${l}</span></div>`).join("");

    const bm=Object.entries(r.by_model||{}).sort((a,b)=>b[1].total_tokens-a[1].total_tokens);
    $("#usage-by-model").innerHTML=bm.length?`<table><tr><th>Model</th><th>Type</th><th>Calls</th><th>Input</th><th>Output</th><th>Total</th><th>Est. cost</th></tr>`+
      bm.map(([m,d])=>`<tr><td><code>${esc(m)}</code>${d.estimated?' <span class="muted" title="tokens estimated">~est</span>':""}</td><td>${esc(d.kind||"")}</td><td>${fmtTok(d.calls)}</td><td>${fmtTok(d.prompt_tokens)}</td><td>${fmtTok(d.completion_tokens)}</td><td>${fmtTok(d.total_tokens)}</td><td>${fmtUsd(d.cost_usd)}</td></tr>`).join("")+`</table>`
      :'<span class="muted">No usage recorded yet — run a generation or analysis.</span>';
    // model dropdown: only the models actually used (dynamic), preserving selection
    fillUsageSelect("#usage-model-filter","All models",bm.map(([m])=>[m,m]));

    const bp=r.by_project||[];
    $("#usage-by-project").innerHTML=bp.length?`<table><tr><th>Project</th><th>Total tokens</th><th>Est. cost</th></tr>`+
      bp.map(p=>`<tr><td>${esc(p.name||p.project_id||"Unassigned")}</td><td>${fmtTok(p.total_tokens)}</td><td>${fmtUsd(p.cost_usd)}</td></tr>`).join("")+`</table>`:'<span class="muted">—</span>';
    // project dropdown: ALL projects (not just those with usage)
    let projOpts=bp.map(p=>[p.name||p.project_id||"Unassigned",p.name||p.project_id||"Unassigned"]);
    try{const pr=await api("/api/projects");const all=(pr.projects||pr||[]).map(p=>p.name).filter(Boolean);
      const seen=new Set(projOpts.map(o=>o[0])); all.forEach(n=>{if(!seen.has(n)){seen.add(n);projOpts.push([n,n]);}});
    }catch(e){}
    fillUsageSelect("#usage-project-filter","All projects",projOpts);

    const rec=r.recent||[];
    $("#usage-recent").innerHTML=rec.length?`<table><tr><th>Process</th><th>Project</th><th>Feature</th><th>Status</th><th>When</th><th>Models</th><th>Total tokens</th><th>Est. cost</th></tr>`+
      rec.map(j=>{const models=Object.keys(j.by_model||{}).map(esc).join(", ")||"—";const when=j.created_at?new Date(j.created_at*1000).toLocaleString():"";
        const st=esc(j.status||"");const stCls=j.status==="failed"?"err":(j.status==="running"?"warn":"ok");
        return `<tr><td>${esc(j.label||j.type||"")}</td><td>${esc(j.project_name||j.project_id||"—")}</td><td>${esc(j.feature_name||"—")}</td><td><span class="${stCls}">${st}</span></td><td class="muted" style="white-space:nowrap">${esc(when)}</td><td><span class="muted" style="font-size:11px">${models}</span></td><td>${fmtTok(j.total_tokens)}</td><td>${fmtUsd(j.cost_usd)}</td></tr>`;}).join("")+`</table>`
      :'<span class="muted">No processes yet.</span>';
    // re-apply any active filters after re-render
    filterUsageTable("#usage-recent-search","usage-recent");
    filterUsageTable("#usage-model-filter","usage-by-model");
    filterUsageTable("#usage-project-filter","usage-by-project");
  }catch(e){totals.innerHTML=`<div class="err">${esc(e.message)}</div>`;}
}
// Populate a <select> with [value,label] options, keeping the current selection if still present.
function fillUsageSelect(sel,allLabel,options){
  const el=$(sel);if(!el)return;
  const cur=el.value;
  el.innerHTML=`<option value="">${esc(allLabel)}</option>`+options.map(([v,l])=>`<option value="${esc(v)}">${esc(l)}</option>`).join("");
  if(cur&&options.some(o=>o[0]===cur))el.value=cur;
}
// Filter table rows by a select's value (or a text input's value); skips the header.
function filterUsageTable(ctrlSel,containerId){
  const ctrl=$(ctrlSel);if(!ctrl)return;
  const q=(ctrl.value||"").trim().toLowerCase();
  document.querySelectorAll(`#${containerId} table tr`).forEach(tr=>{
    if(tr.querySelector("th"))return;
    tr.style.display=(!q||tr.textContent.toLowerCase().includes(q))?"":"none";
  });
}
if($("#usage-recent-search"))$("#usage-recent-search").oninput=()=>filterUsageTable("#usage-recent-search","usage-recent");
if($("#usage-model-filter"))$("#usage-model-filter").onchange=()=>filterUsageTable("#usage-model-filter","usage-by-model");
if($("#usage-project-filter"))$("#usage-project-filter").onchange=()=>filterUsageTable("#usage-project-filter","usage-by-project");
if($("#usage-refresh"))$("#usage-refresh").onclick=loadUsage;
// Generic durable job watcher. SSE gives immediate stage/log updates; polling is
// retained as a fallback for proxies that buffer or block event streams.
function watchJob(jobId, onTick, intervalMs){
  let stop=false,settled=false,es=null,pollTimer=null;
  // Client-side stall detector — if the server's updated_at never advances
  // while status stays "running", the worker thread is likely dead (backend
  // sweeper will confirm it shortly). Deliver a synthetic "failed" tick so the
  // loader in the caller is replaced instead of spinning forever.
  let lastUpdatedAt=null,lastAdvanceMs=Date.now();
  const STALL_MS=120000;   // 2 min without progress = give up; slightly longer than backend sweep default
  const finish=()=>{settled=true;if(es){es.close();es=null;}if(pollTimer){clearTimeout(pollTimer);pollTimer=null;}};
  const deliver=j=>{
    if(stop||settled)return;
    // Track heartbeat: any change in updated_at (or stage/progress) is progress.
    const beat=(j&&(j.updated_at!=null))?j.updated_at:null;
    if(beat!==null&&beat!==lastUpdatedAt){lastUpdatedAt=beat;lastAdvanceMs=Date.now();}
    if(j&&j.status==="running"&&(Date.now()-lastAdvanceMs)>STALL_MS){
      const synth=Object.assign({},j,{status:"failed",stage:"stalled",
        error:(j.error||"Worker appears unresponsive — please retry.")});
      onTick(synth);finish();return;
    }
    onTick(j);if(j.status!=="running")finish();
  };
  // Safety poll ALWAYS runs alongside SSE (slow cadence). SSE gives instant updates,
  // but if the stream goes quiet on a long job (proxy buffering, busy event loop)
  // without firing onerror, the poll still catches the terminal state so the UI never
  // gets stuck "in progress" after the job has finished.
  const poll=async()=>{if(stop||settled)return;try{deliver(await api("/api/jobs/"+jobId));}catch(e){}if(!stop&&!settled)pollTimer=setTimeout(poll,intervalMs||3000);};
  try{
    es=new EventSource(`/api/jobs/${jobId}/stream`);
    es.addEventListener("update",e=>deliver(JSON.parse(e.data)));
    es.addEventListener("done",e=>deliver(JSON.parse(e.data)));
    es.onerror=()=>{if(es){es.close();es=null;}};   // SSE dropped — the safety poll carries on
  }catch(e){}
  pollTimer=setTimeout(poll,intervalMs||3000);       // always-on safety net
  return ()=>{stop=true;finish();};
}
function watchGen(jobId, fid){
  if(!jobId){$("#f-go").disabled=false;setBusy("#f-go",false);return;}
  watchJob(jobId,j=>{const res=j.result||{};
    renderJobLog("#f-log",j);
    const line=`${res.cases_new||0} new + ${res.cases_reused||0} reused cases · ${res.steps_new||0} new + ${res.steps_reused||0} reused steps`;
    $("#f-status").innerHTML=j.status==="running"?`<span class="muted">${esc(j.stage)}</span> — ${line}`
      :j.status==="failed"?`<span class="err">✕ Generation failed: ${esc(j.error||"unknown error")}</span>`
      :`<span class="ok">✓ Done</span> — ${line}${(res.errors&&res.errors.length)?`<br><span class="err">${esc(res.errors.join("; "))}</span>`:""}`;
    if(j.status!=="running"){
      $("#f-go").disabled=false;setBusy("#f-go",false);loadFeatures();refreshStatus();
      if(j.status==="failed")toast("Generation failed: "+(j.error||"unknown error"),true);
      else toast(`Generation complete — ${res.cases_new||0} new, ${res.cases_reused||0} reused test cases.`);
      if(fid)openFeature(fid);
    }
  });
}
// Shows a live loader inside the feature detail while a generation job runs, so the
// user isn't left staring at the old/carried cases wondering if anything happened.
const GEN_WATCHING=new Set();
function watchFeatureGen(jobId, fid){
  const banner=$("#d-genbanner");
  if(!banner||!jobId)return;
  if(GEN_WATCHING.has(jobId))return;   // avoid stacking watchers for the same job
  GEN_WATCHING.add(jobId);
  // Render the branded analyze loader once (so its animation doesn't reset each poll),
  // then update just the caption line below it as progress streams in.
  banner.innerHTML=`${brandLoader("analyze",{compact:true,messages:["Generating test cases…","AI drafting scenarios…","Normalizing & de-duping…","Finalizing suite…"]})}<div class="gen-sub" id="d-gencap" style="text-align:center;margin:2px 0 6px">this can take a minute; results will refresh automatically.</div>`;
  watchJob(jobId,j=>{
    const res=j.result||{};
    if(j.status==="running"){
      const cap=$("#d-gencap");if(cap)cap.textContent=`${esc(j.stage||"Generating test cases…")} · ${res.cases_new||0} new · ${res.cases_reused||0} reused so far`;
    }else if(j.status==="failed"){
      GEN_WATCHING.delete(jobId);
      banner.innerHTML=`<div class="gen-banner err"><span>Generation failed: ${esc(j.error||"unknown error")}</span></div>`;
    }else{
      GEN_WATCHING.delete(jobId);
      banner.innerHTML="";
      loadFeatures();refreshStatus();
      if(fid)openFeature(fid);   // refresh the detail so the new cases appear
    }
  });
}
// If a feature has a generation/ingest job still running (e.g. after a refresh or
// navigating away and back), attach the live loader so it never looks "stuck at 0".
async function attachRunningGenWatcher(fid){
  try{
    const r=await api("/api/jobs?status=running&limit=50");
    const job=(r.jobs||[]).find(j=>j.feature_id===fid && ["generate","ingest"].includes(j.type));
    if(job)watchFeatureGen(job.id,fid);
  }catch(e){}
}
async function loadFeatures(){if(!$("#feat-list"))return;
  skIn("#feat-list",skeleton.cards(6,"Loading features"));
  try{const r=await api("/api/features"+(currentProject?`?project_id=${currentProject}`:""));
  if($("#feature-new-btn"))$("#feature-new-btn").style.display=r.features.length?"":"none";
  $("#feat-list").innerHTML=r.features.map(f=>`<div class="entity-card" onclick="openFeature('${f.id}')">
    <button class="entity-menu-btn" title="Feature options" onclick="event.stopPropagation();toggleFeatureMenu('${f.id}')"><svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px;display:block"><circle cx="12" cy="5" r="2"></circle><circle cx="12" cy="12" r="2"></circle><circle cx="12" cy="19" r="2"></circle></svg></button>
    <div class="entity-menu" onclick="event.stopPropagation()">
      <button onclick="renameFeatureFromCard('${f.id}')">Rename</button>
      <button onclick="importSheetForFeature('${f.id}','${f.project_id||""}')">Import Sheet</button>
      <button class="danger-option" onclick="deleteFeatureFromCard('${f.id}')">Delete</button>
    </div>
    <div class="entity-name">${esc(f.name)}</div>
    <div class="entity-meta">Version ${f.version||1} · ${f.case_count} test case${f.case_count===1?"":"s"}${f.key?` · ${esc(f.key)}`:""}</div>
    <div class="entity-foot"><span>Open workspace</span><span class="entity-arrow">›</span></div>
  </div>`).join("")||`<div class="empty-state"><div class="empty-state-icon">+</div><h3>No features yet</h3><p>Create your first feature to continue.</p><button class="go" onclick="showFeatureCreate()">Create feature</button></div>`;
}catch(e){$("#feat-list").innerHTML=`<div class="empty-state"><div class="empty-state-icon">!</div><h3>Couldn't load features</h3><p>${esc(e.message)}</p><button class="ghost" onclick="loadFeatures()">Retry</button></div>`;}}
window.toggleFeatureMenu = fid => {
  document.querySelectorAll("#feat-list .entity-card").forEach(card=>{
    if(!card.querySelector(`[onclick*="${fid}"]`))card.classList.remove("menu-open");
  });
  const card=[...document.querySelectorAll("#feat-list .entity-card")].find(c=>c.querySelector(`[onclick*="${fid}"]`));
  if(card)card.classList.toggle("menu-open");
};
window.renameFeatureFromCard=async(fid)=>{
  const card=[...document.querySelectorAll("#feat-list .entity-card")].find(c=>c.querySelector(`[onclick*="${fid}"]`));
  const current=card?.querySelector(".entity-name")?.textContent?.trim()||"";
  const name=await uiPrompt("Rename feature","Feature name",current);
  if(!name)return;
  await api("/api/features/"+fid,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});
  loadFeatures();toast("Feature renamed");
};
window.deleteFeatureFromCard=async(fid)=>{
  currentFeature=fid;
  const f=await api("/api/features/"+fid);
  openCaseConfirmation({
    title:"Delete feature",
    copy:"This removes the feature, its document chunks, and its test-case links. Test cases still linked to another feature will not be deleted.",
    summary:`<b>${esc(f.name)}</b><div class="muted" style="margin-top:6px">Version ${f.version||1} · ${(f.test_cases||[]).length} test case${(f.test_cases||[]).length===1?"":"s"}</div>`,
    confirmLabel:"Delete feature",danger:true,
    onConfirm:async()=>{
      const r=await api("/api/features/"+fid,{method:"DELETE"});
      currentFeature=null;showFeatureList();loadFeatures();refreshStatus();
      toast(`Feature deleted · ${r.removed_orphan_cases} orphan test case(s) removed · ${r.preserved_shared_cases} shared test case(s) preserved`);
    }
  });
};
function featureSummaryText(f){
  const summary=String(f.summary||"").replace(/\s+/g," ").trim();
  if(summary && !/^(###|Document:|PRD|HLD|LLD)\b/i.test(summary))return summary;
  const text=String(f.text||"").replace(/\s+/g," ").trim();
  const stripped=text
    .replace(/###\s*(document|uploaded documents?|pasted requirement|requirements?)\s*:?.*?(?=\n|$)/ig,"")
    .replace(/\b[A-Za-z0-9_-]+\.pdf\b/ig,"")
    .replace(/\b(PRD|HLD|LLD)\s*[—-]\s*[^.?!\n]{0,180}/ig,"")
    .replace(/\b(PRD|HLD|LLD)\b\s*:?/ig,"")
    .replace(/\s{2,}/g," ")
    .trim();
  const sentence=(stripped.match(/[^.!?]{40,260}[.!?]/)||[])[0];
  if(sentence)return sentence.trim();
  if(stripped.length>80)return stripped.slice(0,240).trim()+"…";
  return `${f.name} is ready for review with generated test coverage across functional, API, end-to-end, and reliability scenarios.`;
}
window.showAndScrollToTestCases = () => {
  document.querySelectorAll("#d-cases details.case-group").forEach(details => {
    details.open = true;
  });
  const el = $("#d-cases");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};
function renderMatchKey(f){
  const box=$("#d-match-key"); if(!box) return;
  const cur=(f&&f.match_key)||"";
  box.innerHTML=`<span title="PRs whose title/body contain [TAG] auto-map to this feature">PR match tag: </span>`+
    `<input id="d-match-key-input" class="needs-editor" style="width:130px" placeholder="e.g. HOLDS" value="${esc(cur)}"/> `+
    `<button class="ghost needs-editor" type="button" onclick="saveFeatureMatchKey()">Save</button> `+
    `<span id="d-match-key-status" class="muted"></span>`;
}
window.saveFeatureMatchKey=async()=>{
  if(!currentFeature) return;
  const v=(($("#d-match-key-input")&&$("#d-match-key-input").value)||"").trim();
  try{
    const r=await api(`/api/features/${currentFeature}/match-key`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({match_key:v})});
    if(currentFeatureData) currentFeatureData.match_key=r.match_key;
    if($("#d-match-key-status"))$("#d-match-key-status").textContent=r.match_key?`saved · PRs tagged [${esc(r.match_key)}] map here`:"cleared";
    toast("PR match tag "+(r.match_key?("set to ["+r.match_key+"]"):"cleared"));
  }catch(e){ if($("#d-match-key-status"))$("#d-match-key-status").textContent=e.message||"failed"; toast(e.message||"failed",true); }
};
window.openFeature=async fid=>{try{const f=await api("/api/features/"+fid);currentFeature=fid;
  currentFeatureData=f;currentFeatureCases=f.test_cases||[];
  if($("#d-genbanner"))$("#d-genbanner").innerHTML="";
  $("#feature-list-page").hidden=true;$("#feature-create-page").hidden=true;$("#detail-card").hidden=false;$("#d-name").textContent=f.name;renderMatchKey(f);
  const featureMeta=`Version ${f.version||1}${f.key?` · ${esc(f.key)}`:""} · ${f.test_cases.length} test case${f.test_cases.length===1?"":"s"}`;
  $("#d-meta").innerHTML="";
  $("#d-export").onclick=()=>bulkExportSelected("pdf");if($("#d-export-csv"))$("#d-export-csv").onclick=()=>bulkExportSelected("csv");
  $("#d-jira").style.display=f.key?"":"none";$("#d-jira").onclick=()=>syncJira(fid);
  // version switcher
  const vers=f.versions||[];
  $("#d-version").innerHTML=vers.map(v=>`<option value="${v.id}" ${v.id===fid?"selected":""}>v${v.version} · ${v.case_count} cases</option>`).join("");
  $("#d-version-chip").textContent=`Version ${f.version||1} · ${f.test_cases.length} cases`;
  $("#d-version").onchange=e=>openFeature(e.target.value);
  // version diff summary
  const vd=f.version_diff||{};
  if(vd.mode==="version"||(vd.retired&&vd.retired.length)){
    const ret=(vd.retired||[]);
    $("#d-verinfo").innerHTML=`<div class="explain" style="background:rgba(19,112,171,.08);border:1px solid rgba(19,112,171,.25);border-radius:8px;padding:10px 12px;margin:10px 0;font-size:12.5px">
      <b>Version ${vd.version} diff:</b> ${vd.kept||0} cases carried over${ret.length?`, ${ret.length} retired`:""}, new cases added by generation.
      ${ret.length?`<details style="margin-top:6px"><summary class="muted">retired cases</summary>${ret.map(r=>`<div class="muted" style="margin-top:4px">• ${esc(r.title||r.id)} — ${esc(r.reason||"")}</div>`).join("")}</details>`:""}</div>`;
  } else if(vd.mode==="replace"){ $("#d-verinfo").innerHTML=`<div class="muted" style="margin:8px 0">This version was regenerated; ${vd.retired_orphans||0} obsolete cases removed.</div>`; }
  else { $("#d-verinfo").innerHTML=""; }
  const bt={};f.test_cases.forEach(c=>{const _k=c.category||c.type;(bt[_k]=bt[_k]||[]).push(c);});
  const groups=[
    ["api","API","Endpoint happy paths, validation, authorization, and failure handling"],
    ["ui","UI validations","Visible fields, controls, and client-side validation"],
    ["functional","Business / functional","Business rules and requirement behavior"],
    ["e2e","End-to-end","Complete user journeys across UI, API, and persisted state"],
    ["nfr","Edge & reliability","Concurrency, resilience, limits, latency, and degraded dependencies"],
    ["integration","Integration","Cross-feature scenarios: cases inherited / linked from other features"]
  ];
  const overviewStats=groups.map(([t,label])=>{
    const cases=bt[t]||[];
    return `<div class="feature-stat"><b>${cases.length}</b><span>${label}</span></div>`;
  }).join("");
  const summaryText=featureSummaryText(f);
  $("#d-overview").innerHTML=`<div class="feature-hero">
    <div class="muted">${esc(featureMeta)}</div>
    <div class="feature-summary">${esc(summaryText)}</div>
    <div class="feature-stats">${overviewStats}</div>
    <div class="feature-action-grid">
      <button class="feature-action" onclick="showAndScrollToTestCases()"><b>Test cases</b><span>Review, filter, execute, and edit ${f.test_cases.length} cases.</span></button>
      <button class="feature-action" onclick="navigateTo('validator')"><b>Validator</b><span>Check requirement clarity and missing decisions.</span></button>
      <button class="feature-action" onclick="navigateTo('testplan')"><b>Test plan</b><span>Create the QA strategy and exportable plan.</span></button>
      <button class="feature-action" onclick="navigateTo('gap')"><b>Gap Analysis</b><span>PR code coverage and automation coverage with exact commit links.</span></button>
    </div>
  </div>`;
  const h=groups.map(([t,label,help],index)=>{
    const cases=bt[t]||[];
    return `<details class="case-group">
      <summary title="${esc(help)}"><span>${label} (${cases.length})</span></summary>
      <div class="case-group-body">${cases.length?caseListHeader("feature")+cases.map(caseCard).join(""):`<div class="case-group-empty">No ${label.toLowerCase()} were generated from the current evidence.</div>`}</div>
    </details>`;
  }).join("");
  $("#d-cases").innerHTML=h;updateCaseSelection();loadCoverage(fid);window.scrollTo({top:0,behavior:"smooth"});
  renderBreadcrumbs();
  updateBackbar();
  attachRunningGenWatcher(fid);   // show the live loader if generation is still running
}catch(e){$("#d-cases").innerHTML=`<div class="err">${esc(e.message)}</div>`;}};
async function openFeatureTestCases(fid,pid){
  navigateTo("cases");
  await initCases();
  $("#tc-proj").value=pid||currentProject||"";
  await fillFeatFilter();
  $("#tc-feat").value=fid;
  $("#tc-type").value="";$("#tc-tag").value="";$("#tc-status").value="active";$("#tc-result").value="";$("#tc-lineage").value="";$("#tc-q").value="";
  tcPage=0;loadCases();
}
function activeCaseRoot(){
  if(!$("#view-features").hidden&&!$("#detail-card").hidden)return $("#detail-card");
  if(!$("#view-cases").hidden)return $("#view-cases");
  return document;
}
function activeCaseCheckboxes(){
  return [...activeCaseRoot().querySelectorAll(".case-select[data-case-id]")];
}
function selectedCaseIds(){
  return activeCaseCheckboxes().filter(x=>x.checked).map(x=>x.dataset.caseId);
}
function setVisibleCaseSelection(checked){
  activeCaseCheckboxes().forEach(x=>x.checked=checked);
  updateCaseSelection();
}
function updateCaseSelection(){
  const root=activeCaseRoot();
  const boxes=activeCaseCheckboxes();
  const selected=boxes.filter(x=>x.checked);
  document.querySelectorAll(".case-bulk-toolbar").forEach(bar=>bar.classList.remove("show"));
  const scope=root.id==="detail-card"?"feature":"cases";
  document.querySelectorAll(`[data-bulk-scope="${scope}"]`).forEach(bar=>{
    if(selected.length)bar.classList.add("show");
  });
  document.querySelectorAll(`[data-bulk-count="${scope}"]`).forEach(x=>x.textContent=`${selected.length} selected`);
  document.querySelectorAll(`[data-bulk-count="${scope}-floating"]`).forEach(x=>x.textContent=selected.length);
  root.querySelectorAll(".case-select-all").forEach(x=>{
    x.checked=boxes.length>0&&selected.length===boxes.length;
    x.indeterminate=selected.length>0&&selected.length<boxes.length;
  });
  document.querySelectorAll(`[data-bulk-scope="${scope}-floating"]`).forEach(bar=>bar.classList.toggle("show",selected.length>0));
}
document.addEventListener("change",e=>{
  if(e.target.matches(".case-select-all"))setVisibleCaseSelection(e.target.checked);
  if(e.target.matches(".case-select[data-case-id]"))updateCaseSelection();
});
function selectedExportIds(){
  const rowIds=selectedCaseIds();
  if(rowIds.length)return rowIds;
  return [...document.querySelectorAll(".export-case-check")]
    .filter(x=>x.checked)
    .map(x=>x.value);
}
function refreshExportCount(){
  const n=selectedExportIds().length;
  $("#export-count").textContent=`${n} selected`;
  $("#export-pdf").disabled=!n;$("#export-csv").disabled=!n;
}
function openExportModal(){
  if(!currentFeature||!currentFeatureData)return;
  const cases=currentFeatureCases||[];
  $("#export-sub").textContent=`${currentFeatureData.name} · Version ${currentFeatureData.version||1} · ${cases.length} test case${cases.length===1?"":"s"}`;
  $("#export-select-all").checked=true;
  $("#export-list").innerHTML=cases.map(c=>`<label class="export-row">
    <input class="export-case-check" type="checkbox" value="${esc(c.id)}" checked/>
    <span class="badge">${esc(c.display_id||"")}</span>
    <span><span class="title">${esc(caseTitle(c))}</span><div class="meta">${esc(typeLabel(c.type))} · ${c.steps?.length||0} step${(c.steps?.length||0)===1?"":"s"}</div></span>
    <span class="meta">${prioBadge(c.priority)}</span>
  </label>`).join("")||`<div class="muted" style="padding:14px">No test cases available.</div>`;
  document.querySelectorAll(".export-case-check").forEach(x=>x.onchange=()=>{
    const all=[...document.querySelectorAll(".export-case-check")];
    $("#export-select-all").checked=all.length&&all.every(c=>c.checked);
    refreshExportCount();
  });
  refreshExportCount();
  $("#export-modal").classList.add("show");
}
async function downloadFeatureExport(format, explicitIds=null){
  const ids=explicitIds===null?selectedExportIds():explicitIds;
  const featureId=!$("#view-cases").hidden?$("#tc-feat")?.value:currentFeature;
  if(!featureId){toast("Choose one feature before exporting selected test cases",true);return;}
  const ext=format==="pdf"?"pdf":"csv";
  const mime=format==="pdf"?"application/pdf":"text/csv";
  const request=ids.length
    ? {
        url:`/api/features/${featureId}/export/${format}-selected`,
        init:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({testCaseIds:ids})}
      }
    : {
        url:`/api/features/${featureId}/export/${format}`,
        init:{method:"GET"}
      };
  const res=await fetch(request.url,request.init);
  if(!res.ok){let detail="Export failed";try{detail=(await res.json()).detail||detail;}catch(e){}throw new Error(detail);}
  const blob=await res.blob();
  const url=URL.createObjectURL(new Blob([blob],{type:mime}));
  const a=document.createElement("a");
  a.href=url;a.download=`${(currentFeatureData?.name||"feature").replace(/[^a-z0-9]+/gi,"_").toLowerCase()}_test_cases.${ext}`;
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
}
async function downloadGapExport(kind, fmt){
  if(!currentFeature){toast("Open a feature first",true);return;}
  const mime=fmt==="pdf"?"application/pdf":"text/csv";
  const res=await fetch(`/api/features/${currentFeature}/gap/${kind}/export/${fmt}`,{method:"GET"});
  if(!res.ok){let detail="Export failed";try{detail=(await res.json()).detail||detail;}catch(e){}throw new Error(detail);}
  const blob=await res.blob();
  const url=URL.createObjectURL(new Blob([blob],{type:mime}));
  const a=document.createElement("a");
  const base=(currentFeatureData?.name||"feature").replace(/[^a-z0-9]+/gi,"_").toLowerCase();
  const label=kind==="pr-coverage"?"pr_coverage":"automation_coverage";
  a.href=url;a.download=`${base}_${label}.${fmt}`;
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
}
async function bulkExportSelected(format="pdf"){
  const ids=selectedCaseIds();
  try{await downloadFeatureExport(format,ids);toast(ids.length?"Selected test cases exported":"All feature test cases exported");}catch(e){toast(e.message,true);}
}
async function bulkSetCaseResult(status){
  const ids=selectedCaseIds();
  if(!ids.length){toast("Select test cases first",true);return;}
  try{
    await Promise.all(ids.map(id=>api(`/api/test-cases/${id}/execution`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})})));
    ids.forEach(id=>{
      const item=document.querySelector(`[data-case-item="${id}"]`);
      const select=item?.querySelector(".result-select");
      if(select){select.value=status;select.className=`result-select needs-editor ${status}`;[...select.options].forEach(o=>o.defaultSelected=o.value===status);}
    });
    toast(`${ids.length} test case${ids.length===1?"":"s"} marked ${RESULT_LABELS[status].toLowerCase()}`);
  }catch(e){toast(e.message,true);}
}
async function bulkDeleteSelected(){
  const ids=selectedCaseIds();
  if(!ids.length){toast("Select test cases first",true);return;}
  if(!await uiConfirm(`Delete ${ids.length} selected test case${ids.length===1?"":"s"}? Shared test cases are only removed from the current feature when a feature is in context.`, "Delete Test Cases", "Delete", true))return;
  const scopedFeature=!$("#view-cases").hidden?($("#tc-feat")?.value||""):currentFeature;
  try{
    for(const id of ids){
      if(scopedFeature)await api(`/api/features/${scopedFeature}/test-cases/${id}`,{method:"DELETE"});
      else await api(`/api/test-cases/${id}`,{method:"DELETE"});
    }
    toast(`${ids.length} selected test case${ids.length===1?"":"s"} removed`);
    if(!$("#view-cases").hidden)loadCases();
    if(currentFeature)openFeature(currentFeature);
  }catch(e){toast(e.message,true);}
}
if($("#export-close"))$("#export-close").onclick=()=>$("#export-modal").classList.remove("show");
if($("#export-select-all"))$("#export-select-all").onchange=e=>{
  document.querySelectorAll(".export-case-check").forEach(x=>x.checked=e.target.checked);
  refreshExportCount();
};
if($("#export-pdf"))$("#export-pdf").onclick=async()=>{try{await downloadFeatureExport("pdf");}catch(e){toast(e.message,true);}};
if($("#export-csv"))$("#export-csv").onclick=async()=>{try{await downloadFeatureExport("csv");}catch(e){toast(e.message,true);}};
document.querySelectorAll(".feature-workspace-back").forEach(button=>{
  button.onclick=()=>navigateTo("features");
});
document.querySelectorAll(".feature-workspace-cases").forEach(button=>{
  button.onclick=()=>{
    if(currentFeature)openFeatureTestCases(currentFeature,currentProject);
  };
});
const TYPE_LABELS={functional:"Business / functional",e2e:"End-to-end",api:"API",ui:"UI validation",nfr:"Edge & reliability",integration:"Integration"};
const typeLabel=t=>TYPE_LABELS[t]||t;
const caseTitle=c=>cleanRequirementText(c?.title||"Untitled test case")||"Untitled test case";
function caseListHeader(scope){
  return `<div class="case-list-head">
    <input type="checkbox" class="case-select case-select-all" data-bulk-scope="${scope}" title="Select all visible test cases" aria-label="Select all visible test cases" onclick="event.stopPropagation()"/>
    <span></span>
    <span>Test case</span>
    <span>Result</span>
    <span>Priority</span>
    <span>Action</span>
  </div>`;
}
function caseCard(c){
  const orig=c.association&&c.association.origin;
  const context=orig?`${orig.replaceAll("_"," ")} · `:"";
  const inherited=["reused","carried","carried_repaired","inherited","adapted"].includes(orig);
  const title=caseTitle(c);
  // "Imported from sheet" takes priority over the generic inherited badge, so a case
  // that came from an uploaded sheet is never mislabelled as inherited from a feature.
  // Fall back to the origin when the backend `imported` flag isn't present yet.
  const isImported=c.imported||orig==="imported";
  const originBadge=isImported
    ?`<span class="badge reused" style="margin-left:7px" title="Came from an uploaded sheet">Imported from sheet</span>`
    :(inherited?`<span class="badge reused" style="margin-left:7px">Inherited / reused</span>`:"");
  return `<div class="testcase-item" data-case-item="${c.id}">
    <div class="testcase-row" onclick="viewCase('${c.id}',this)">
      <input class="case-select" data-case-id="${esc(c.id)}" type="checkbox" aria-label="Select ${esc(title)}" onclick="event.stopPropagation()"/>
      <span class="testcase-chevron">›</span>
      <div><div class="testcase-title">${c.display_id?`<span class="badge" style="margin-right:7px">${esc(c.display_id)}</span>`:""}${esc(title)}${originBadge}</div><div class="testcase-sub">${esc(context+typeLabel(c.type))} · ${c.steps.length} step${c.steps.length===1?"":"s"}</div></div>
      ${resultSelect(c)}
      <span class="testcase-priority">${prioBadge(c.priority)}</span>
      <button class="testcase-delete needs-editor" title="Delete testcase" onclick="event.stopPropagation();requestDeleteCase('${c.id}')"><span>Delete</span></button>
    </div>
    <div class="testcase-detail" data-case-detail="${c.id}"></div>
  </div>`;
}
async function loadCoverage(fid){
  $("#d-coverage").innerHTML="";
  try{
    const r=await api(`/api/features/${fid}/coverage`);
    const s=r.summary; if(!s) return;
    const thr=(s.ready_threshold!=null)?s.ready_threshold:80;
    const banner=s.ready
      ? `<div style="margin-top:10px;color:#34d399;font-weight:600;font-size:13px">✓ Minimum code-coverage target reached (${s.code_pct}% ≥ ${thr}%) — ready for manual QA.</div>`
      : `<div style="margin-top:10px;color:#f6a623;font-size:12.5px">Not ready for manual QA — code coverage ${s.code_pct}% is below the ${thr}% target for this feature.</div>`;
    const strategy=`<div style="margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12.5px;color:var(--muted,#94a3b8)">
      <span>QA-readiness target:</span>
      <input id="fc-threshold" class="needs-editor" type="number" min="0" max="100" value="${thr}" style="width:64px" />
      <span>% code coverage</span>
      <button class="ghost needs-editor" type="button" onclick="saveReadyThreshold('${fid}')">Save</button>
      <span id="fc-threshold-status" class="muted"></span>
    </div>`;
    $("#d-coverage").innerHTML=`<div style="margin-top:14px;border:1px solid var(--line,#1e293b);border-radius:12px;padding:14px 16px;background:var(--panel,#0d1728)">
      <div style="font-size:13px;font-weight:600">Coverage <span style="font-weight:400;color:var(--muted,#94a3b8)">— aggregated across all PRs linked to this feature</span></div>
      <div style="font-size:12px;color:var(--muted,#94a3b8);margin:2px 0 10px">A test case counts as covered once ANY linked PR implements it (no single repo need cover everything).</div>
      <div class="dash-gauge"><div class="top"><span>Code coverage (cases hit by PRs)</span><b>${s.code_pct}%</b></div><div class="track"><div class="fill code" style="width:${s.code_pct}%"></div></div></div>
      <div class="dash-gauge"><div class="top"><span>Automation Test Coverage (dev-written tests)</span><b>${s.automation_pct}%</b></div><div class="track"><div class="fill auto" style="width:${s.automation_pct}%"></div></div></div>
      <div class="dash-cov-note">${s.covered_cases} covered · ${s.automated_cases} automated of ${s.total_cases} cases</div>
      ${banner}
      ${strategy}
    </div>`;
  }catch(e){/* non-fatal: coverage card just stays empty */}
}
window.saveReadyThreshold=async(fid)=>{
  const el=$("#fc-threshold"); const v=parseInt((el&&el.value)||"80",10);
  try{
    const r=await api(`/api/features/${fid}/ready-threshold`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({threshold:isNaN(v)?80:v})});
    toast(`QA-readiness target set to ${r.ready_threshold}% code coverage`);
    loadCoverage(fid);
  }catch(e){ if($("#fc-threshold-status"))$("#fc-threshold-status").textContent=e.message||"failed"; toast(e.message||"Could not save target",true); }
}
$("#d-close").onclick=showFeatureList;

// ---- test cases view ----
async function initCases(){await loadProjects();try{const t=await api("/api/tags");$("#tc-tag").innerHTML=`<option value="">Any tag</option>`+t.tags.map(x=>`<option>${esc(x)}</option>`).join("");}catch(e){}
  // feature filter depends on project
  await fillFeatFilter(); loadCases();}
async function fillFeatFilter(){try{const pf=$("#tc-proj").value;const r=await api("/api/features"+(pf?`?project_id=${pf}`:""));
  $("#tc-feat").innerHTML=`<option value="">All features</option>`+r.features.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join("");}catch(e){}}
$("#tc-proj").onchange=async()=>{$("#tc-feat").value="";await fillFeatFilter();tcPage=0;loadCases();};
$("#tc-feat").onchange=()=>{tcPage=0;loadCases();};
$("#tc-type").onchange=()=>{tcPage=0;loadCases();};
$("#tc-tag").onchange=()=>{tcPage=0;loadCases();};
$("#tc-status").onchange=()=>{tcPage=0;loadCases();};
$("#tc-result").onchange=()=>{tcPage=0;loadCases();};
$("#tc-lineage").onchange=()=>{tcPage=0;loadCases();};
$("#tc-q").onkeydown=e=>{if(e.key==="Enter"){tcPage=0;loadCases();}};
$("#tc-apply").onclick=()=>{tcPage=0;loadCases();};
$("#tc-reset").onclick=async()=>{
  $("#tc-proj").value="";$("#tc-type").value="";$("#tc-tag").value="";
  $("#tc-status").value="active";$("#tc-result").value="";$("#tc-lineage").value="";$("#tc-q").value="";tcPage=0;
  await fillFeatFilter();$("#tc-feat").value="";loadCases();
};
async function loadCases(){
  const qp=new URLSearchParams();const m={project_id:$("#tc-proj").value,feature_id:$("#tc-feat").value,type:$("#tc-type").value,tag:$("#tc-tag").value,q:$("#tc-q").value.trim(),status:$("#tc-status").value,execution_status:$("#tc-result").value,lineage:$("#tc-lineage").value};
  Object.entries(m).forEach(([k,v])=>{if(v)qp.set(k,v);});qp.set("limit",25);qp.set("skip",tcPage*25);
  skIn("#tc-list",skeleton.rows(8,"Loading test cases"));
  try{const r=await api("/api/test-cases?"+qp.toString());
    $("#tc-list").innerHTML=r.items.length?`<div class="testcase-list">`+caseListHeader("cases")+
      r.items.map(testcaseRow).join("")+`</div>`:`<span class="muted">No test cases match the selected filters.</span>`;
    updateCaseSelection();
    const activeFilters=[
      $("#tc-proj").selectedOptions[0]?.textContent!=="All projects"?$("#tc-proj").selectedOptions[0]?.textContent:null,
      $("#tc-feat").value?$("#tc-feat").selectedOptions[0]?.textContent:null,
      $("#tc-type").value?typeLabel($("#tc-type").value):null,
      $("#tc-tag").value?`tag: ${$("#tc-tag").value}`:null,
      $("#tc-status").value!=="active"?`lifecycle: ${$("#tc-status").value}`:null,
      $("#tc-result").value?`result: ${$("#tc-result").value}`:null,
      $("#tc-lineage").value?`lineage: ${$("#tc-lineage").selectedOptions[0]?.textContent}`:null,
      $("#tc-q").value.trim()?`search contains “${$("#tc-q").value.trim()}”`:null
    ].filter(Boolean);
    $("#tc-summary").textContent=`${r.total} matching test case${r.total===1?"":"s"}${activeFilters.length?` · ${activeFilters.join(" · ")}`:""}`;
    const pages=Math.max(1,Math.ceil(r.total/25));
    $("#tc-pager").innerHTML=`<div style="display:flex;align-items:center;justify-content:center;gap:14px;margin:16px 0 4px">
      <button class="go" id="tcp" ${tcPage<=0?"disabled":""} style="flex:0 0 auto;padding:6px 16px">‹ Prev</button>
      <span class="muted" style="font-size:12.5px;white-space:nowrap">${r.total} cases · page ${tcPage+1} of ${pages}</span>
      <button class="go" id="tcn" ${tcPage>=pages-1?"disabled":""} style="flex:0 0 auto;padding:6px 16px">Next ›</button></div>`;
    $("#tcp").onclick=()=>{if(tcPage>0){tcPage--;loadCases();}};$("#tcn").onclick=()=>{if(tcPage<pages-1){tcPage++;loadCases();}};
  }catch(e){$("#tc-list").innerHTML=`<div class="empty-state"><div class="empty-state-icon">!</div><h3>Couldn't load test cases</h3><p>${esc(e.message)}</p><button class="ghost" onclick="loadCases()">Retry</button></div>`;}}

const RESULT_LABELS={untested:"Untested",passed:"Passed",failed:"Failed",blocked:"Blocked"};
const resultSelect=(c)=>`<select class="result-select needs-editor ${esc(c.execution_status||"untested")}" aria-label="Latest execution result" onclick="event.stopPropagation()" onchange="setCaseResult('${c.id}',this.value,this)"><option value="untested" ${(c.execution_status||"untested")==="untested"?"selected":""}>Untested</option><option value="passed" ${c.execution_status==="passed"?"selected":""}>Passed</option><option value="failed" ${c.execution_status==="failed"?"selected":""}>Failed</option><option value="blocked" ${c.execution_status==="blocked"?"selected":""}>Blocked</option></select>`;
function testcaseRow(c){
  const lineageImported=c.imported||c.association_origin==="imported";
  const lineageBadge=lineageImported
    ?`<span class="badge reused" style="margin-left:7px" title="This test case came from an uploaded sheet (imported / reused across features)">Imported from sheet</span>`
    :(c.inherited?`<span class="badge reused" style="margin-left:7px">Inherited${c.source_feature_name?` from ${esc(c.source_feature_name)}`:""}</span>`:"");
  const title=caseTitle(c);
  return `<div class="testcase-item" data-case-item="${c.id}" style="${c.deprecated?"opacity:.6":""}">
    <div class="testcase-row" onclick="viewCase('${c.id}',this)">
      <input class="case-select" data-case-id="${esc(c.id)}" type="checkbox" aria-label="Select ${esc(title)}" onclick="event.stopPropagation()"/>
      <span class="testcase-chevron">›</span>
      <div><div class="testcase-title">${c.display_id?`<span class="badge" style="margin-right:7px">${esc(c.display_id)}</span>`:""}${esc(title)}${lineageBadge}</div><div class="testcase-sub">${esc(typeLabel(c.type))} · ${c.step_count} step${c.step_count===1?"":"s"}${c.shared_with_features>1?` · linked to ${c.shared_with_features} features`:""}${c.deprecated?" · deprecated":""}</div></div>
      ${resultSelect(c)}
      <span class="testcase-priority">${prioBadge(c.priority)}</span>
      <button class="testcase-delete needs-editor" title="Delete testcase" aria-label="Delete testcase" onclick="event.stopPropagation();requestDeleteCase('${c.id}')"><span>Delete</span></button>
    </div>
    <div class="testcase-detail" data-case-detail="${c.id}"></div>
  </div>`;
}

const caseMetaText=(value)=>{
  if(value===null||value===undefined||value==="")return "Not specified";
  if(Array.isArray(value))return value.length?value.map(x=>typeof x==="object"?JSON.stringify(x):String(x)).join("\n• "):"None";
  if(typeof value==="object")return Object.entries(value).map(([k,v])=>`${k.replaceAll("_"," ")}: ${Array.isArray(v)?v.join(", "):typeof v==="object"?JSON.stringify(v):v}`).join("\n");
  return String(value);
};
function cleanRequirementText(value){
  let text=String(value||"").trim();
  const original=text.toLowerCase();
  const sourceKeyword=String.raw`(?:prd|hld|lld|spec|specification|document|requirements?|product|business|functional|technical|api|ui|ux|security|compliance|architecture|design|uploaded|source|reference)(?:\s+[\w.-]+){0,5}`;
  const sourceExact=String.raw`(?:[A-Z][A-Z0-9_-]{1,20}|[\w.-]+\.(?:pdf|docx?|md|txt))`;
  const kind=String.raw`(?:document|docs?|spec(?:ification)?|requirements?|rules?|design|architecture|guide|policy|story|ticket|epic|acceptance\s+criteria)`;
  const verb=String.raw`(?:requires?|states?|specifies?|defines?|indicates?|says?|suggests?|allows?|documents?|mandates?|notes?|describes?)`;
  text=text.replace(new RegExp(`^according\\s+to\\s+(?:the\\s+)?(?:${sourceExact}|${sourceKeyword})(?:\\s+${kind})?\\s*[,;:]\\s*`,"i"),"");
  text=text.replace(new RegExp(`^(?:the\\s+)?${sourceExact}(?:\\s+${kind})?\\s*(?:rule|requirement)?(?:\\s*:\\s*|\\s+-\\s+)`),"");
  text=text.replace(new RegExp(`^(?:the\\s+)?${sourceKeyword}(?:\\s+${kind})?\\s*(?:rule|requirement)?(?:\\s*:\\s*|\\s+-\\s+)`,"i"),"");
  text=text.replace(new RegExp(`^(?:the\\s+)?${sourceExact}(?:\\s+${kind})?\\s+${verb}\\s+(?:that\\s+)?`),"");
  text=text.replace(new RegExp(`^(?:the\\s+)?${sourceKeyword}(?:\\s+${kind})?\\s+${verb}\\s+(?:that\\s+)?`,"i"),"");
  if(original.includes("requires"))text=text.replace(/\bto be\b/i,"must be");
  return text?text.charAt(0).toUpperCase()+text.slice(1):text;
}
const EXPECTED_LABELS={status_code:"Status code",db_changes:"Database changes",side_effects:"Side effects",negative_assertions:"Must not happen"};
function expectedValueHtml(value){
  if(Array.isArray(value))return value.length?`<ul>${value.map(item=>`<li>${esc(typeof item==="object"?JSON.stringify(item):item)}</li>`).join("")}</ul>`:`<span class="muted">None</span>`;
  if(value&&typeof value==="object")return `<ul>${Object.entries(value).map(([key,item])=>`<li><b>${esc(key.replaceAll("_"," "))}:</b> ${esc(Array.isArray(item)?item.join(", "):item)}</li>`).join("")}</ul>`;
  return `<span>${esc(value===null||value===undefined||value===""?"Not specified":value)}</span>`;
}
function expectedResultHtml(value){
  if(!value||typeof value!=="object"||Array.isArray(value))return `<div class="case-detail-value">${esc(caseMetaText(value))}</div>`;
  const preferred=["status_code","db_changes","side_effects","negative_assertions"];
  const keys=[...preferred.filter(k=>Object.prototype.hasOwnProperty.call(value,k)),...Object.keys(value).filter(k=>!preferred.includes(k))];
  return `<div class="expected-grid">${keys.map(key=>`<div class="expected-row"><div class="expected-key">${esc(EXPECTED_LABELS[key]||key.replaceAll("_"," "))}</div><div class="expected-content">${expectedValueHtml(value[key])}</div></div>`).join("")}</div>`;
}
function caseDetailHtml(c){
  const m=c.metadata||{};
  const title=caseTitle(c);
  const description=cleanRequirementText(m.description||m.intent||m.scenario||c.preconditions)||"No separate description was generated.";
  const endpoint=[m.method,m.endpoint||m.path].filter(Boolean).join(" ");
  const expected=m.expected_result||m.expected_behavior||m.result;
  const lineage=(c.features||[]).map(f=>`${f.name}${f.version?` v${f.version}`:""}${f.origin?` · ${f.origin}`:""}`).join("\n");
  // Imported when the backend flag says so, or any feature link's origin is an import.
  const isImported=c.imported||(c.features||[]).some(f=>String(f.origin||"").toLowerCase().includes("import"));
  const lineageText=(isImported?"Imported from sheet\n":"")+(lineage||"No feature lineage recorded");
  const importedBadge=isImported?`<span class="badge reused" style="margin-left:6px" title="Came from an uploaded sheet">Imported from sheet</span>`:"";
  const steps=(c.steps||[]);
  return `<div class="case-detail-head"><div><div style="font-size:15px;font-weight:700">${c.display_id?`<span class="badge" style="margin-right:8px">${esc(c.display_id)}</span>`:""}${esc(title)}${importedBadge}</div><div style="margin-top:5px"><span class="badge ${c.type}">${esc(typeLabel(c.type))}</span> ${prioBadge(c.priority)} ${(c.tags||[]).map(t=>`<span class="badge">${esc(t)}</span>`).join(" ")}</div></div><div style="display:flex;gap:7px"><button class="ghost needs-editor" onclick="event.stopPropagation();editCase('${c.id}')">Edit testcase</button><button class="ghost" onclick="event.stopPropagation();viewCase('${c.id}',this)">Close</button></div></div>
    <div class="case-detail-grid">
      <div class="case-detail-panel"><div class="case-detail-label">Description</div><div class="case-detail-value">${esc(caseMetaText(description))}</div></div>
      <div class="case-detail-panel"><div class="case-detail-label">Endpoint</div><div class="case-detail-value">${esc(endpoint||"Not applicable or not specified")}</div></div>
      <div class="case-detail-panel"><div class="case-detail-label">Expected result</div>${expectedResultHtml(expected)}</div>
      <div class="case-detail-panel"><div class="case-detail-label">Source lineage</div><div class="case-detail-value">${esc(lineageText)}</div></div>
    </div>
    <div class="case-steps-table"><div class="case-step case-step-head"><span>#</span><span>Step</span><span>Expected result</span></div>${steps.length?steps.map((s,i)=>`<div class="case-step"><span class="case-step-num">${i+1}.</span><span>${esc(s.action)}</span><span class="case-step-expected">${esc(s.expected||"No separate expected result")}</span></div>`).join(""):`<div class="case-detail-loading">No detailed steps were saved for this testcase.</div>`}</div>`;
}
window.viewCase=async(cid,source)=>{
  const item=source?.closest?.(`[data-case-item="${cid}"]`)||document.querySelector(`[data-case-item="${cid}"]`);
  if(!item)return;
  const detail=item.querySelector(`[data-case-detail="${cid}"]`);
  if(item.classList.contains("open")){item.classList.remove("open");return;}
  document.querySelectorAll(".testcase-item.open").forEach(x=>x.classList.remove("open"));
  item.classList.add("open");
  if(detail.dataset.loaded)return;
  detail.innerHTML=skeleton.block("Loading test case details");
  try{const c=await api("/api/test-cases/"+cid);detail.innerHTML=caseDetailHtml(c);detail.dataset.loaded="1";}
  catch(e){detail.innerHTML=`<div class="err">${esc(e.message)}</div>`;}
};
window.setCaseResult=async(cid,status,select)=>{
  const old=[...select.options].find(o=>o.defaultSelected)?.value||"untested";
  select.disabled=true;
  try{await api(`/api/test-cases/${cid}/execution`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});
    select.className=`result-select ${status}`;[...select.options].forEach(o=>o.defaultSelected=o.value===status);toast(`Marked ${RESULT_LABELS[status].toLowerCase()}`);
  }catch(e){select.value=old;toast(e.message,true);}finally{select.disabled=false;}
};

// ---- case editor ----
window.editCase=async cid=>{try{const c=await api("/api/test-cases/"+cid);
  editing={id:cid,shared_with_features:c.shared_with_features||0,steps:c.steps.map(s=>({id:s.id,action:s.action,expected:s.expected,usage_count:s.usage_count}))};
  $("#m-heading").textContent="Edit test case";
  $("#m-title").value=c.title;$("#m-type").value=c.type;$("#m-prio").value=prioLabel(c.priority);$("#m-pre").value=c.preconditions||"";$("#m-tags").value=(c.tags||[]).join(", ");
  $("#m-warn").textContent=c.shared_with_features>1?`Linked to ${c.shared_with_features} features. Testcase field changes appear in every linked feature; shared-step edits also update other cases that use those exact steps.`:"";
  $("#m-del").style.display="";$("#m-del").onclick=()=>requestDeleteCase(cid,c);
  renderSteps();$("#m-msg").textContent="";$("#modal").classList.add("show");
}catch(e){toast(e.message,true);}};
function renderSteps(){
  $("#m-steps").innerHTML=editing.steps.map((s,i)=>`
    <div class="steprow" draggable="true" data-i="${i}">
      <div class="drag-handle">⋮⋮</div>
      <textarea draggable="false" data-i="${i}" data-f="action" placeholder="action">${esc(s.action)}</textarea>
      <textarea draggable="false" data-i="${i}" data-f="expected" placeholder="expected">${esc(s.expected)}</textarea>
      <div class="ctrl"><button class="iconbtn" title="Remove step from this testcase" onclick="rmStep(${i})">×</button></div>
      ${s.usage_count>1?`<div class="editor-shared-note">This exact step is shared by ${s.usage_count} testcases. Editing its text updates all of them; removing it only unlinks it from this testcase.</div>`:""}
    </div>`).join("");
  
  $("#m-steps").querySelectorAll("textarea").forEach(t=>t.oninput=e=>{editing.steps[+e.target.dataset.i][e.target.dataset.f]=e.target.value;});
  
  let draggedIdx = null;
  const rows = $("#m-steps").querySelectorAll(".steprow");
  rows.forEach(row => {
    row.addEventListener("dragstart", e => {
      draggedIdx = +row.dataset.i;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      rows.forEach(r => r.classList.remove("drag-over"));
    });
    row.addEventListener("dragover", e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      row.classList.add("drag-over");
    });
    row.addEventListener("dragleave", () => {
      row.classList.remove("drag-over");
    });
    row.addEventListener("drop", e => {
      e.preventDefault();
      row.classList.remove("drag-over");
      const targetIdx = +row.dataset.i;
      if (draggedIdx !== null && draggedIdx !== targetIdx) {
        const item = editing.steps.splice(draggedIdx, 1)[0];
        editing.steps.splice(targetIdx, 0, item);
        renderSteps();
      }
    });
  });
}
window.rmStep=i=>{editing.steps.splice(i,1);renderSteps();};
$("#m-addstep").onclick=()=>{editing.steps.push({action:"",expected:""});renderSteps();};
function editorBody(){return {title:$("#m-title").value.trim(),type:$("#m-type").value,priority:$("#m-prio").value,preconditions:$("#m-pre").value.trim(),
    tags:$("#m-tags").value.split(",").map(t=>t.trim().toLowerCase()).filter(Boolean),
    steps:editing.steps.filter(s=>s.action||s.expected).map(s=>s.id?{id:s.id,action:s.action,expected:s.expected}:{action:s.action,expected:s.expected})};}
function openCaseConfirmation({title,copy,summary,confirmLabel,danger=false,onConfirm,secondaryLabel=null,onSecondary=null}){
  $("#cc-title").textContent=title;$("#cc-copy").textContent=copy;
  // Only show the summary box when there's actual summary content — otherwise it
  // renders as a stray empty input-looking box (role-change / delete confirmations).
  $("#cc-summary").innerHTML=summary||"";$("#cc-summary").style.display=summary?"":"none";
  $("#cc-error").textContent="";
  $("#cc-confirm").textContent=confirmLabel;$("#cc-confirm").className=danger?"danger":"go";
  $("#cc-cancel").style.display="";
  $("#cc-cancel").textContent="Cancel";
  $("#cc-secondary").style.display=secondaryLabel?"":"none";
  $("#cc-secondary").textContent=secondaryLabel||"";
  $("#case-confirm").classList.add("show");
  $("#cc-cancel").onclick=()=>$("#case-confirm").classList.remove("show");
  $("#cc-confirm").onclick=async()=>{try{$("#cc-confirm").disabled=true;await onConfirm();$("#case-confirm").classList.remove("show");}catch(e){$("#cc-error").textContent=e.message;}finally{$("#cc-confirm").disabled=false;}};
  $("#cc-secondary").onclick=secondaryLabel?async()=>{try{$("#cc-secondary").disabled=true;await onSecondary();$("#case-confirm").classList.remove("show");}catch(e){$("#cc-error").textContent=e.message;}finally{$("#cc-secondary").disabled=false;}}:null;
}
function openInfoDialog({title,copy,summary,closeLabel="Close"}){
  $("#cc-title").textContent=title;$("#cc-copy").textContent=copy;
  $("#cc-summary").innerHTML=summary||"";$("#cc-summary").style.display=summary?"":"none";
  $("#cc-error").textContent="";
  $("#cc-secondary").style.display="none";
  $("#cc-cancel").style.display="none";
  $("#cc-confirm").textContent=closeLabel;
  $("#cc-confirm").className="go";
  $("#case-confirm").classList.add("show");
  $("#cc-confirm").onclick=()=>$("#case-confirm").classList.remove("show");
}
$("#m-save").onclick=()=>{
  const body=editorBody();
  if(!body.title){$("#m-msg").innerHTML=`<span class="err">Title is required.</span>`;return;}
  openCaseConfirmation({
    title:editing.id?"Confirm testcase update":"Confirm new testcase",
    copy:editing.id?`Review the fields before updating “${body.title}”.`:`Create “${body.title}” in the selected feature.`,
    summary:`<div><b>${esc(body.title)}</b></div><div class="muted" style="margin-top:6px">${esc(typeLabel(body.type))} · ${prioLabel(body.priority)} · ${body.steps.length} step${body.steps.length===1?"":"s"}${editing.shared_with_features>1?` · linked to ${editing.shared_with_features} features`:""}</div>`,
    confirmLabel:editing.id?"Update testcase":"Create testcase",
    onConfirm:()=>saveCase(body)
  });
};
async function saveCase(body){$("#m-save").disabled=true;$("#m-msg").textContent="saving…";
  try{let r;
    if(editing.id){r=await api("/api/test-cases/"+editing.id,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      $("#m-msg").innerHTML=`<span class="ok">Saved ${r.steps} steps${r.other_cases_affected_by_step_edits?` · ${r.other_cases_affected_by_step_edits} other case(s) updated via shared steps`:""}</span>`;}
    else{r=await api("/api/test-cases",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...body,feature_id:editing.feature_id})});
      $("#m-msg").innerHTML=`<span class="ok">Created${r&&r.display_id?` — ${esc(r.display_id)}`:""}</span>`;
      if(editing.cycle_id&&r&&r.id){try{await api(`/api/test-cycles/${editing.cycle_id}/items`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({case_ids:[r.id]})});}catch(e){}}}
    loadCases();loadSteps();if(currentFeature)openFeature(currentFeature);refreshStatus();
    if(window._cycle&&$("#cyc-detail-card")&&$("#cyc-detail-card").style.display!=="none"){openCycle(window._cycle);}
    document.querySelectorAll(`[data-case-detail="${editing.id}"]`).forEach(x=>{x.dataset.loaded="";});
    setTimeout(()=>$("#modal").classList.remove("show"),500);
  }catch(e){$("#m-msg").innerHTML=`<span class="err">${esc(e.message)}</span>`;throw e;}finally{$("#m-save").disabled=false;}};
$("#m-cancel").onclick=$("#m-close").onclick=()=>$("#modal").classList.remove("show");

// ---- steps ----
let ALL_STEPS=[];
let STEPMAP={};
let SELECTED_STEP_ID=null;

async function loadSteps(){
  if(!document.getElementById("s-list-body"))return;
  skIn("#s-list-body",skeleton.rows(8,"Loading step library"));
  try{
    const r=await api("/api/steps?limit=1000");
    ALL_STEPS=r.steps||[];
    $("#s-count").textContent=`(${ALL_STEPS.length})`;
    STEPMAP={};
    ALL_STEPS.forEach(s=>STEPMAP[s.id]=s);
    renderStepList();
  }catch(e){
    $("#s-list-body").innerHTML=`<div class="err" style="padding:18px">Couldn't load steps. ${esc(e.message)}</div>`;
  }
}

function getStepType(action) {
  const clean = (action || "").trim().toLowerCase();
  if (clean.startsWith("given ")) return "given";
  if (clean.startsWith("when ")) return "when";
  if (clean.startsWith("then ")) return "then";
  if (clean.startsWith("and ") || clean.startsWith("but ")) return "and";
  return "other";
}

function getStepBase(action) {
  const clean = (action || "").trim();
  const lower = clean.toLowerCase();
  if (lower.startsWith("given ")) return clean.slice(6).trim();
  if (lower.startsWith("when ")) return clean.slice(5).trim();
  if (lower.startsWith("then ")) return clean.slice(5).trim();
  if (lower.startsWith("and ")) return clean.slice(4).trim();
  if (lower.startsWith("but ")) return clean.slice(4).trim();
  return clean;
}

function renderStepList(){
  const tbody = $("#s-list-body");
  if (!tbody) return;
  
  const searchVal = $("#s-search").value.trim().toLowerCase();
  const typeFilter = $("#s-filter-type").value;
  const usageFilter = $("#s-filter-usage").value;
  
  const filtered = ALL_STEPS.filter(s => {
    if (searchVal) {
      const inAction = (s.action || "").toLowerCase().includes(searchVal);
      const inExpected = (s.expected || "").toLowerCase().includes(searchVal);
      if (!inAction && !inExpected) return false;
    }
    const detectedType = getStepType(s.action);
    if (typeFilter) {
      if (typeFilter === "Other") {
        if (["given", "when", "then", "and"].includes(detectedType)) return false;
      } else if (typeFilter === "And") {
        if (detectedType !== "and") return false;
      } else {
        if (detectedType !== typeFilter.toLowerCase()) return false;
      }
    }
    if (usageFilter) {
      if (usageFilter === "used" && s.used_in_cases === 0) return false;
      if (usageFilter === "unused" && s.used_in_cases > 0) return false;
    }
    return true;
  });
  
  // Given/When/Then convey the step's role (setup / action / assertion) and are shown
  // as a colored inline prefix. "And/But" is intentionally NOT shown here: it only
  // means "continues the line above", which is meaningless in this flat, reused-out-of-
  // -order library — so those steps show as a plain (capitalized) sentence instead.
  const KW = { given: "Given", when: "When", then: "Then" };

  tbody.innerHTML = filtered.map(s => {
    const t = getStepType(s.action);
    const isSelected = SELECTED_STEP_ID === s.id ? " selected" : "";
    const kw = KW[t];   // undefined for "and"/"but" and plain actions → no keyword prefix
    const kwHtml = kw ? `<span class="step-kw ${t}">${kw}</span>` : "";
    let base = getStepBase(s.action);
    if (!kw && base) base = base.charAt(0).toUpperCase() + base.slice(1);  // standalone sentence
    const actionText = esc(base);
    const expected = (s.expected || "").trim();
    const used = s.used_in_cases;
    const usageHtml = used > 0
      ? `<span class="step-usage" title="Used in ${used} test case${used===1?"":"s"}">${used} case${used===1?"":"s"}</span>`
      : `<span class="step-usage unused" title="Not referenced by any test case yet">Unused</span>`;

    return `<div class="step-item${isSelected}" onclick="selectStepRow(event, '${s.id}')">
      <div class="step-item-main">
        <div class="step-line">${kwHtml}<span class="step-text">${actionText}</span></div>
        ${expected ? `<div class="step-expected"><span class="step-exp-label">Expected</span>${esc(expected)}</div>` : ""}
      </div>
      <div class="step-item-meta" onclick="event.stopPropagation()">
        ${usageHtml}
        <div class="step-actions">
          <button class="step-act-btn" onclick="editStepFromMap('${s.id}')">Edit</button>
          <button class="step-act-btn del" onclick="delStepLib('${s.id}')">Delete</button>
        </div>
      </div>
    </div>`;
  }).join("") || `<div class="muted" style="text-align:center;padding:32px">No matching steps found.</div>`;
}

window.selectStepRow = (event, id) => {
  SELECTED_STEP_ID = id;
  const rows = $("#s-list-body").querySelectorAll(".step-item");
  rows.forEach(r => r.classList.remove("selected"));
  const row = event.currentTarget;
  if (row) row.classList.add("selected");
  showStepDetails(id);
};

window.showStepDetails = async (id) => {
  const s = STEPMAP[id];
  if (!s) return;
  const pane = $("#s-detail-pane");
  if (!pane) return;
  pane.style.display = "flex";
  const t = getStepType(s.action);
  const label = t === "other" ? "Action" : (t === "and" ? "And/But" : t.toUpperCase());
  $("#s-detail-type").innerHTML = `<span class="step-badge ${t}">${esc(label)}</span>`;
  $("#s-detail-action").textContent = getStepBase(s.action);
  $("#s-detail-expected").textContent = s.expected || "No separate expected result defined.";
  const listDiv = $("#s-detail-cases-list");
  listDiv.innerHTML = loadingRow("Loading cases…");
  try {
    const res = await api(`/api/test-cases?step_id=${id}&limit=200`);
    const cases = res.items || [];
    $("#s-detail-cases-title").textContent = `Used in Cases (${cases.length})`;
    listDiv.innerHTML = cases.map(c => `
      <div class="stepitem" style="font-size:12.5px;padding:6px 8px;background:rgba(255,255,255,0.02);border:1px solid #1E2A40;border-radius:6px;display:flex;justify-content:space-between;align-items:center;gap:10px">
        <span style="font-weight:500;color:#e2e8f0">${c.display_id ? `<code style="font-size:10.5px;background:rgba(255,255,255,.06);padding:1px 5px;border-radius:3px;margin-right:6px;color:#94a3b8">${esc(c.display_id)}</code>` : ""}${esc(c.title)}</span>
        <button class="ghost" style="padding:2px 6px;font-size:11px" onclick="openAndGoToCase('${c.id}', '${c.feature_id}')">Open ↗</button>
      </div>
    `).join("") || `<span class="muted" style="font-size:12px">Not referenced by any active test cases.</span>`;
  } catch (e) {
    listDiv.innerHTML = `<span class="err" style="font-size:12px">${esc(e.message)}</span>`;
  }
};

window.openAndGoToCase = async (caseId, featureId) => {
  await openFeature(featureId);
  navigateTo("features");
  setTimeout(() => {
    viewCase(caseId);
    const el = document.querySelector(`[data-case-item="${caseId}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, 300);
};

// Bind UI event handlers
setTimeout(() => {
  if ($("#s-search")) $("#s-search").oninput = renderStepList;
  if ($("#s-filter-type")) $("#s-filter-type").onchange = renderStepList;
  if ($("#s-filter-usage")) $("#s-filter-usage").onchange = renderStepList;
  if ($("#s-detail-close")) {
    $("#s-detail-close").onclick = () => {
      $("#s-detail-pane").style.display = "none";
      SELECTED_STEP_ID = null;
      const rows = $("#s-list-body").querySelectorAll(".step-item");
      rows.forEach(r => r.classList.remove("selected"));
    };
  }
}, 500);

// ---- configuration ----
async function loadConfig(){try{const s=await api("/api/settings");
  const llmProv=s.llm_provider||"ollama";
  $("#cfg-llm-provider").value=llmProv;
  if($("#cfg-llm-region"))$("#cfg-llm-region").value=s.llm_region||"";
  updateModelOptions(llmProv, s.llm_model||"");
  $("#cfg-llm-status").innerHTML=s.llm_api_key_set?`<span class="ok">API key / secret configured</span>`:`<span class="muted">no API key set</span>`;
  // Unified Endpoint URL field: shows the Ollama URL for Ollama (with the env-lock /
  // effective-URL hint), else the provider base/endpoint URL.
  if($("#cfg-llm-endpoint")){
    const inp=$("#cfg-llm-endpoint"),hint=$("#cfg-ollama-hint");
    if(llmProv==="ollama"){
      if(s.ollama_url_env_locked){
        inp.value=s.ollama_url_effective||"";inp.disabled=true;
        hint.innerHTML=`Pinned by <code>OLLAMA_URL</code> in <code>.env</code> (takes priority). Edit <code>.env</code> to change it.`;
      }else{
        inp.disabled=false;inp.value=s.ollama_url||"";
        hint.innerHTML=`In use: <code>${esc(s.ollama_url_effective||"")}</code>${s.ollama_url?"":" (bundled default)"}. Applies immediately on save — no restart.`;
      }
    }else{
      inp.disabled=false;inp.value=s.llm_base_url||"";hint.innerHTML="";
    }
  }
  applyLlmProviderUI(llmProv);
  // Deploy-time provider lock (e.g. an air-gapped Bedrock-only client): pin the LLM
  // dropdown only. Embeddings stay the admin's choice (handled in the embed section).
  if(s.provider_lock){
    const lp=$("#cfg-llm-provider");if(lp&&[...lp.options].some(o=>o.value===s.provider_lock)){lp.value=s.provider_lock;lp.disabled=true;applyLlmProviderUI(s.provider_lock);}
  }
  if($("#cfg-jira-base")){$("#cfg-jira-base").value=s.jira_base_url||"";$("#cfg-jira-email").value=s.jira_email||"";$("#cfg-jira-status").innerHTML=s.jira_token_set?`<span class="ok">Jira token configured</span>`:`<span class="muted">no Jira token set</span>`;}
  if($("#cfg-figma-status")){$("#cfg-figma-status").innerHTML=s.figma_token_set?`<span class="ok">Figma token configured</span>`:`<span class="muted">no Figma token set</span>`;}
  if($("#cfg-smtp-host")){$("#cfg-smtp-host").value=s.smtp_host||"";$("#cfg-smtp-port").value=s.smtp_port||"";$("#cfg-smtp-user").value=s.smtp_user||"";$("#cfg-smtp-from").value=s.smtp_from||"";$("#cfg-smtp-tls").checked=s.smtp_tls!==false;$("#cfg-smtp-ssl").checked=!!s.smtp_ssl;
    $("#cfg-smtp-status").innerHTML=s.smtp_configured?`<span class="ok">SMTP configured${s.smtp_pass_set?" (password saved)":""}</span>`:`<span class="warn">not configured — email sign-in unavailable</span>`;}
  // Embedding model
  if($("#cfg-embed-provider")){
    EMBED_OPTS=s.embed_model_options||{};
    const embSel=$("#cfg-embed-provider");
    embSel.value=s.embed_provider||"ollama";
    // In a locked (air-gapped) install the admin may still pick their embedder, but
    // only the offline-safe ones: the local bundled Ollama or the locked provider
    // (e.g. Bedrock). Internet embedders (OpenAI / Gemini / Voyage) are hidden.
    if(s.provider_lock){
      const allowed=new Set(["ollama", s.provider_lock]);
      [...embSel.options].forEach(o=>{o.hidden=!allowed.has(o.value);});
      if(!allowed.has(embSel.value))embSel.value="ollama";
    }else{
      [...embSel.options].forEach(o=>{o.hidden=false;});
    }
    const embProv=embSel.value;
    $("#cfg-embed-base").value=s.embed_base_url||"";
    if($("#cfg-embed-region"))$("#cfg-embed-region").value=s.embed_region||"";
    updateEmbedModelOptions(embProv, s.embed_model||"");
    $("#cfg-embed-status").innerHTML=`<span class="muted">Active: ${esc(embProv)} / ${esc(s.embed_model||"nomic-embed-text")} · ${s.embed_dim||768}-d${s.embed_api_key_set?" · key set":""}</span>`;
  }
  loadDbStatus();
}catch(e){}}

// ---- read-only Database status panel ----
async function loadDbStatus(){
  const box=$("#cfg-db-body");if(!box)return;
  box.innerHTML=skeleton.block("Loading database status");
  try{
    const d=await api("/api/db-status");
    const boot=d.boot||{};
    const err=boot.stage==="error";
    // Show only the connection status; the URL input below is always available.
    const rows=[];
    rows.push(dbRow("Connection", err
      ? `<span class="err">⚠ ${esc(boot.detail||"not ready")}</span>`
      : (boot.ready?`<span class="ok">● connected</span>`:`<span class="warn">● ${esc(boot.stage||"starting")}</span>`)));
    box.innerHTML=`<div class="db-table">${rows.join("")}</div>`;
    const sw=$("#cfg-db-switch"); if(sw)sw.style.display="block";
  }catch(e){
    box.innerHTML=`<span class="err">${esc(e.message||"could not load database status")}</span>`;
    const sw=$("#cfg-db-switch"); if(sw)sw.style.display="block";
  }
}
// Ollama endpoint presets: point at native Ollama (uses the computer's GPU) or the
// bundled Docker container. Only fill the field — the user still clicks Save (LLM card).
// Show the Ollama-only convenience buttons only when Ollama is the provider (the
// input fields themselves stay common across every provider).
function applyLlmProviderUI(prov){
  const presets=$("#cfg-ollama-presets");
  if(presets)presets.style.display=(prov==="ollama")?"flex":"none";
}
if($("#cfg-ollama-native"))$("#cfg-ollama-native").onclick=()=>{
  const inp=$("#cfg-llm-endpoint");if(!inp||inp.disabled)return;
  inp.value="http://host.docker.internal:11434";
  const h=$("#cfg-ollama-hint");if(h)h.innerHTML=`Points at Ollama on your computer (uses its GPU — much faster). <b>Important:</b> first <b>stop the bundled Ollama</b> so port 11434 is free (<code>docker compose stop ollama</code>), then <b>install Ollama</b> from ollama.com and pull a model, then click <b>Save</b>. <span class="warn">If the bundled Ollama is still running, this address just reaches it again (no speed gain).</span> On Linux, also add <code>--add-host=host.docker.internal:host-gateway</code> to the app container.`;
};
if($("#cfg-ollama-bundled"))$("#cfg-ollama-bundled").onclick=()=>{
  const inp=$("#cfg-llm-endpoint");if(!inp||inp.disabled)return;
  inp.value="http://ollama:11434";
  const h=$("#cfg-ollama-hint");if(h)h.innerHTML=`Set to the bundled Docker Ollama (no install, but CPU-only — slower for the language model). Click <b>Save</b> to apply.`;
};
function dbRow(k,v){return `<div class="db-r"><span class="db-k">${esc(k)}</span><span class="db-v">${v}</span></div>`;}
if($("#cfg-db-refresh"))$("#cfg-db-refresh").onclick=loadDbStatus;

// One simple action: copy the user's data into the database they entered, then switch
// to it. (If that database already has data, we ask once whether to overwrite it.)
async function runDbSwitch(overwrite){
  const uri=($("#cfg-db-uri").value||"").trim();
  const st=$("#cfg-db-status"), btn=$("#cfg-db-switch-go"), lbl="Switch to this database";
  if(!uri){if(st){st.classList.remove("ok","err");st.innerHTML=`<span class="warn">Enter a database connection string.</span>`;}return;}
  btn.disabled=true;btn.textContent="Starting…";
  if(st){st.classList.remove("ok","err");st.classList.add("is-saving");st.textContent="Checking the database…";}
  try{
    const r=await api("/api/db-migrate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target_uri:uri,overwrite:!!overwrite})});
    watchJob(r.job_id,j=>{
      if(!st)return;
      if(j.status==="running"){
        st.classList.add("is-saving");st.classList.remove("ok","err");
        st.textContent=`Transferring your data…${j.progress?` ${j.progress}%`:""}`;
      }else if(j.status==="succeeded"){
        const res=j.result||{};
        st.classList.remove("is-saving");
        st.innerHTML=`<span class="ok">Your data has been copied to the new database.</span> Run <code>${esc(res.apply_cmd||"docker compose up -d")}</code> to finish switching.`;
        $("#cfg-db-uri").value="";
        btn.disabled=false;btn.textContent=lbl;
      }else{
        st.classList.remove("is-saving");
        st.innerHTML=`<span class="err">Couldn't switch: ${esc(j.error||"unknown error")}</span>`;
        btn.disabled=false;btn.textContent=lbl;
      }
    });
  }catch(e){
    btn.disabled=false;btn.textContent=lbl;
    // If the target already has data, offer one clear yes/no instead of a separate control.
    if(!overwrite && /already contains data/i.test(e.message||"")){
      if(await confirmModal({
        title: "Replace existing data?",
        body: "That database already has data in it.\n\nReplace it with your current data?",
        confirmText: "Replace data",
        danger: true
      })) return runDbSwitch(true);
      if(st){st.classList.remove("is-saving");st.innerHTML=`<span class="muted">Cancelled — pick an empty database, or confirm replacing it.</span>`;}
      return;
    }
    if(st){st.classList.remove("is-saving");st.innerHTML=`<span class="err">${esc(e.message)}</span>`;}
  }
}
if($("#cfg-db-switch-go"))$("#cfg-db-switch-go").onclick=async()=>{
  if(!($("#cfg-db-uri").value||"").trim()){const st=$("#cfg-db-status");if(st){st.classList.remove("ok","err");st.innerHTML=`<span class="warn">Enter a database connection string.</span>`;}return;}
  if(!(await confirmModal({
    title: "Switch database?",
    body: "Copy your data to this database and switch wardenIQ to it?\n\nYour current database stays intact until you restart, so nothing is lost.",
    confirmText: "Switch database"
  }))) return;
  runDbSwitch(false);
};

let EMBED_OPTS={};
function updateEmbedModelOptions(provider, selected){
  // Built-in embedding models only — fixed list per provider, no custom entry.
  const opts=EMBED_OPTS[provider]||[];
  const sel=$("#cfg-embed-model-select"),inp=$("#cfg-embed-model");
  if(!sel||!inp)return;
  if(!opts.length){
    // No built-in list (custom OpenAI-compatible) → plain typed model name.
    sel.style.display="none";inp.style.display="block";inp.value=selected||"";return;
  }
  sel.style.display="";
  const chosen=opts.some(m=>m.id===selected)?selected:opts[0].id;
  sel.innerHTML=opts.map(m=>`<option value="${esc(m.id)}" ${m.id===chosen?"selected":""}>${esc(m.id)} (${m.dim}-d)</option>`).join("");
  inp.style.display="none";inp.value=sel.value;
}
if($("#cfg-embed-provider"))$("#cfg-embed-provider").onchange=()=>updateEmbedModelOptions($("#cfg-embed-provider").value,"");
if($("#cfg-embed-model-select"))$("#cfg-embed-model-select").onchange=()=>{const inp=$("#cfg-embed-model");if(inp)inp.value=$("#cfg-embed-model-select").value;};
if($("#cfg-embed-save"))$("#cfg-embed-save").onclick=async()=>{
  const provider=$("#cfg-embed-provider").value;
  // Dropdown for providers with a built-in list; the text input only for providers
  // without one (custom OpenAI-compatible), which is the only time it's visible.
  const inpEl=$("#cfg-embed-model");
  const model=(inpEl && inpEl.style.display!=="none") ? inpEl.value.trim() : $("#cfg-embed-model-select").value;
  if(!model){toast("Choose or enter an embedding model",true);return;}
  if(!(await confirmModal({
    title:"Switch embedding model?",
    body:"This will RE-EMBED every stored vector and rebuild the search indexes. Search, dedup and Mind-Map results will be degraded until it completes.",
    confirmText:"Switch & re-embed",
    danger:true
  })))return;
  const btn=$("#cfg-embed-save");btn.disabled=true;$("#cfg-embed-status").textContent="Validating model & measuring dimension…";
  const body={provider,model,base_url:$("#cfg-embed-base").value.trim(),region:$("#cfg-embed-region")?$("#cfg-embed-region").value.trim():""};
  const key=$("#cfg-embed-key").value;if(key)body.api_key=key;
  try{
    const r=await api("/api/embedding/switch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    $("#cfg-embed-status").innerHTML=`<span class="ok">Switching to ${esc(r.provider)}/${esc(r.model)} (${r.dim}-d) — re-embedding…</span>`;
    $("#cfg-embed-log").style.display="block";$("#cfg-embed-key").value="";
    watchJob(r.job_id,j=>{renderJobLog("#cfg-embed-log",j);
      if(j.status!=="running"){btn.disabled=false;
        if(j.status==="failed")$("#cfg-embed-status").innerHTML=`<span class="err">Re-embed failed: ${esc(j.error||"")}</span>`;
        else{$("#cfg-embed-status").innerHTML=`<span class="ok">Done — all vectors re-embedded with ${esc(r.model)} (${r.dim}-d).</span>`;loadConfig();}
      }});
  }catch(e){$("#cfg-embed-status").innerHTML=`<span class="err">${esc(e.message)}</span>`;btn.disabled=false;}
};

const PREDEFINED_MODELS = {
  ollama: [
    { id: "llama3.2:1b", label: "Llama 3.2 1B — fastest, basic quality" },
    { id: "qwen2.5:3b", label: "Qwen 2.5 3B — balanced (built-in default)" },
    { id: "llama3.2:3b", label: "Llama 3.2 3B — balanced" },
    { id: "qwen2.5:7b", label: "Qwen 2.5 7B — best quality, slowest" }
  ],
  groq: [
    { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B Instant — fastest" },
    { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B — best quality" }
  ],
  openai: [
    { id: "gpt-4o", label: "GPT-4o (Recommended)" },
    { id: "gpt-4o-mini", label: "GPT-4o Mini" },
    { id: "gpt-4.1", label: "GPT-4.1" }
  ],
  anthropic: [
    { id: "claude-opus-4-6", label: "Claude Opus 4.6 (Recommended)" },
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
    { id: "claude-haiku-4-5", label: "Claude Haiku 4.5" }
  ],
  gemini: [
    { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash (Recommended)" },
    { id: "gemini-3.5-pro", label: "Gemini 3.5 Pro" },
    { id: "gemini-3.1-pro", label: "Gemini 3.1 Pro" },
    { id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash-Lite" }
  ],
  mistral: [
    { id: "mistral-large-latest", label: "Mistral Large (Recommended)" },
    { id: "mistral-small-latest", label: "Mistral Small" },
    { id: "open-mistral-nemo", label: "Mistral Nemo" },
    { id: "codestral-latest", label: "Codestral" }
  ],
  "openai-compatible": [],
  // Bedrock model IDs vary by account/region and may be inference-profile ARNs, so
  // this stays free-text (empty list → the model text input is shown).
  bedrock: []
};

function updateModelOptions(provider, selectedModel) {
  // Built-in models only — a fixed curated list per provider, no free-text/custom
  // entry (keeps model choice simple and supported for the open-source launch).
  const models = PREDEFINED_MODELS[provider] || [];
  const select = $("#cfg-llm-model-select");
  const input = $("#cfg-llm-model");
  if (!select || !input) return;

  if (!models.length) {
    // Providers with no built-in list (e.g. custom OpenAI-compatible) still need a
    // typed model name — keep a plain input for just those.
    select.style.display = "none";
    input.style.display = "block";
    input.value = selectedModel || "";
    return;
  }
  select.style.display = "";
  const sel = models.some(m => m.id === selectedModel) ? selectedModel : models[0].id;
  select.innerHTML = models.map(m => `<option value="${m.id}" ${m.id === sel ? "selected" : ""}>${m.label} (${m.id})</option>`).join("");
  input.style.display = "none";
  input.value = select.value;   // hidden input mirrors the dropdown; save reads it
}

if ($("#cfg-llm-model-select")) {
  $("#cfg-llm-model-select").onchange = e => {
    const input = $("#cfg-llm-model");
    if (input) input.value = e.target.value;   // built-in choice → mirror to hidden input
  };
}

if ($("#cfg-llm-provider")) {
  $("#cfg-llm-provider").onchange = e => {
    const prov=e.target.value;
    updateModelOptions(prov, "");
    applyLlmProviderUI(prov);
    // Reset the unified endpoint + its hint when switching provider families.
    const ep=$("#cfg-llm-endpoint");if(ep){ep.disabled=false;ep.value="";}
    const h=$("#cfg-ollama-hint");if(h)h.innerHTML=(prov==="ollama")?`Click <b>Use bundled (Docker) Ollama</b> or <b>Use Ollama on my computer</b>, or leave blank for the bundled default.`:"";
  };
}
async function saveConfigSection({buttonId,statusId,body,clearIds=[],successMessage="Settings saved"}){
  const btn=$(buttonId), status=$(statusId);
  const originalLabel=btn.textContent;
  btn.disabled=true;
  btn.textContent="Saving...";
  if(status){
    status.classList.add("is-saving");
    status.classList.remove("ok","err");
    status.textContent="Checking and saving settings...";
  }
  try{
    await api("/api/settings",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    clearIds.forEach(id=>{ if($(id)) $(id).value=""; });
    await loadConfig();
    if(status){
      status.classList.remove("is-saving");
      status.innerHTML=`<span class="ok">${esc(successMessage)}</span>`;
    }
  }catch(e){
    if(status){
      status.classList.remove("is-saving");
      status.innerHTML=`<span class="err">${esc(e.message)}</span>`;
    }
    throw e;
  }finally{
    btn.disabled=false;
    btn.textContent=originalLabel;
  }
}
$("#cfg-llm-save").onclick=async()=>{
  const prov=$("#cfg-llm-provider").value;
  const ep=$("#cfg-llm-endpoint");
  const epv=ep?ep.value.trim():"";
  // Unified "Endpoint URL" field maps to the Ollama URL for Ollama, else the
  // provider base/endpoint URL (custom OpenAI-compatible or a Bedrock VPC endpoint).
  const b={llm_provider:prov,llm_model:$("#cfg-llm-model").value.trim(),llm_region:$("#cfg-llm-region").value.trim()};
  if(prov==="ollama"){ if(ep&&!ep.disabled)b.ollama_url=epv; b.llm_base_url=""; }
  else { b.llm_base_url=epv; }
  const k=$("#cfg-llm-key").value;
  if(k)b.llm_api_key=k;
  try{
    await saveConfigSection({buttonId:"#cfg-llm-save",statusId:"#cfg-llm-status",body:b,clearIds:["#cfg-llm-key"],successMessage:"LLM settings saved"});
    // For Ollama, report what the reached instance actually has, so users can confirm
    // which Ollama answered (bundled container vs a native install).
    if(b.llm_provider==="ollama"){
      const h=$("#cfg-ollama-hint");if(h){
        try{
          const r=await api("/api/llm/test",{method:"POST"});
          const n=(r.models||[]).length;
          h.innerHTML=`<span class="ok">Connected to Ollama — ${n} model${n===1?"":"s"} available${n?`: <code>${(r.models||[]).slice(0,6).map(esc).join(", ")}</code>`:""}.</span>`;
        }catch(e){ h.innerHTML=`<span class="warn">Saved, but the test call to Ollama failed: ${esc(e.message)}</span>`; }
      }
    }
  }catch(e){toast(e.message,true);}
};
$("#cfg-jira-save").onclick=async()=>{
  const b={jira_base_url:$("#cfg-jira-base").value.trim(),jira_email:$("#cfg-jira-email").value.trim()};
  const t=$("#cfg-jira-token").value;
  if(t)b.jira_api_token=t;
  try{
    await saveConfigSection({buttonId:"#cfg-jira-save",statusId:"#cfg-jira-status",body:b,clearIds:["#cfg-jira-token"],successMessage:"Jira settings saved"});
  }catch(e){toast(e.message,true);}
};
$("#cfg-figma-save").onclick=async()=>{
  const t=$("#cfg-figma-token").value;
  if(!t){toast("Enter a Figma token",true);return;}
  try{
    await saveConfigSection({buttonId:"#cfg-figma-save",statusId:"#cfg-figma-status",body:{figma_api_token:t},clearIds:["#cfg-figma-token"],successMessage:"Figma token saved"});
  }catch(e){toast(e.message,true);}
};
$("#cfg-smtp-save").onclick=async()=>{
  const b={smtp_host:$("#cfg-smtp-host").value.trim(),smtp_port:parseInt($("#cfg-smtp-port").value)||null,smtp_user:$("#cfg-smtp-user").value.trim(),smtp_from:$("#cfg-smtp-from").value.trim(),smtp_tls:$("#cfg-smtp-tls").checked,smtp_ssl:$("#cfg-smtp-ssl").checked};
  const p=$("#cfg-smtp-pass").value.trim();
  if(p)b.smtp_pass=p;
  try{
    await saveConfigSection({buttonId:"#cfg-smtp-save",statusId:"#cfg-smtp-status",body:b,clearIds:["#cfg-smtp-pass"],successMessage:b.smtp_host?"SMTP settings saved":"Settings saved"});
  }catch(e){toast(e.message,true);}
};
$("#cfg-smtp-test").onclick=async()=>{
  const st=$("#cfg-smtp-status");
  const def=$("#cfg-smtp-user").value.trim()||(ME&&ME.email)||"";
  const to=((await uiPrompt("Send test email","Send a test sign-in email to:",def))||"").trim();
  if(!to)return;
  const btn=$("#cfg-smtp-test"),lbl=btn.textContent;
  btn.disabled=true;btn.textContent="Sending...";
  if(st){st.classList.remove("ok","err");st.classList.add("is-saving");st.textContent="Sending test email (uses saved settings)...";}
  try{
    await api("/api/smtp/test",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:to})});
    if(st){st.classList.remove("is-saving");st.innerHTML=`<span class="ok">Test email sent to ${esc(to)} — check the inbox (and spam).</span>`;}
  }catch(e){
    if(st){st.classList.remove("is-saving");st.innerHTML=`<span class="err">${esc(e.message)}</span>`;}
  }finally{btn.disabled=false;btn.textContent=lbl;}
};

// ---- step library CRUD ----
let STEP_MODAL_MODE = "create";
let STEP_MODAL_ID = null;

setTimeout(() => {
  const newBtn = document.getElementById("s-new");
  if (newBtn) {
    newBtn.onclick = () => {
      STEP_MODAL_MODE = "create";
      STEP_MODAL_ID = null;
      
      $("#step-modal-heading").textContent = "Create Step";
      $("#step-modal-prefix").value = "Given";
      $("#step-modal-action").value = "";
      $("#step-modal-expected").value = "";
      $("#step-modal-warn").style.display = "none";
      $("#step-modal").classList.add("show");
    };
  }
  
  if ($("#step-modal-close")) {
    $("#step-modal-close").onclick = $("#step-modal-cancel").onclick = () => {
      $("#step-modal").classList.remove("show");
    };
  }
  
  if ($("#step-modal-save")) {
    $("#step-modal-save").onclick = async () => {
      const prefix = $("#step-modal-prefix").value;
      const rawAction = $("#step-modal-action").value.trim();
      const expected = $("#step-modal-expected").value.trim();
      
      if (!rawAction) {
        toast("Action / Description is required", true);
        return;
      }
      
      const action = prefix ? `${prefix} ${rawAction}` : rawAction;
      const saveBtn = $("#step-modal-save");
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
      
      try {
        if (STEP_MODAL_MODE === "create") {
          await api("/api/steps", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, expected })
          });
          toast("Step created ✓");
        } else {
          const r = await api("/api/steps/" + STEP_MODAL_ID, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, expected })
          });
          toast(`Updated — affects ${r.affected_cases} case(s) ✓`);
          
          if (SELECTED_STEP_ID === STEP_MODAL_ID) {
            setTimeout(() => showStepDetails(STEP_MODAL_ID), 200);
          }
        }
        $("#step-modal").classList.remove("show");
        loadSteps();
      } catch (e) {
        toast(e.message, true);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save";
      }
    };
  }
}, 500);

window.editStepFromMap = id => {
  const s = STEPMAP[id];
  if (!s) return;
  
  STEP_MODAL_MODE = "edit";
  STEP_MODAL_ID = id;
  
  $("#step-modal-heading").textContent = "Edit Step";
  
  const detectedPrefix = getStepType(s.action);
  let prefix = "";
  if (["given", "when", "then", "and"].includes(detectedPrefix)) {
    prefix = s.action.split(" ")[0];
  }
  $("#step-modal-prefix").value = prefix;
  $("#step-modal-action").value = getStepBase(s.action);
  $("#step-modal-expected").value = s.expected || "";
  
  const warnDiv = $("#step-modal-warn");
  if (s.used_in_cases > 0) {
    warnDiv.textContent = `Warning: This step is referenced by ${s.used_in_cases} active testcase(s). Updating it will immediately affect all of them.`;
    warnDiv.style.display = "block";
  } else {
    warnDiv.style.display = "none";
  }
  
  $("#step-modal").classList.add("show");
};

window.editStepLib = (id, a, e) => {
  editStepFromMap(id);
};

window.delStepLib = async id => {
  const s = STEPMAP[id];
  if (!s) return;
  
  if (s.used_in_cases > 0) {
    toast(`Cannot delete: Step is referenced by ${s.used_in_cases} case(s).`, true);
    return;
  }
  

  
  try {
    const r = await api("/api/steps/" + id, { method: "DELETE" });
    if (r.deleted) {
      if (SELECTED_STEP_ID === id) {
        $("#s-detail-pane").style.display = "none";
        SELECTED_STEP_ID = null;
      }
      loadSteps();
      toast("Step deleted");
    } else {
      toast(r.reason, true);
    }
  } catch (e) {
    toast(e.message, true);
  }
};

// ---- new / delete test case ----
$("#tc-new").onclick=()=>{const fid=$("#tc-feat").value;if(!fid){toast("Pick a Feature filter first, so the new case is added to it",true);return;}
  editing={id:null,feature_id:fid,shared_with_features:0,steps:[{action:"",expected:""}]};$("#m-heading").textContent="Create test case";$("#m-title").value="";$("#m-type").value="functional";$("#m-prio").value="Medium";$("#m-pre").value="";$("#m-tags").value="";$("#m-warn").textContent="The testcase will be linked to the selected feature.";$("#m-del").style.display="none";renderSteps();$("#m-msg").textContent="";$("#modal").classList.add("show");};
window.requestDeleteCase=async(cid,known)=>{
  let c=known;try{if(!c)c=await api("/api/test-cases/"+cid);}catch(e){toast(e.message,true);return;}
  const links=c.shared_with_features||0;
  const casesViewOpen=!$("#view-cases").hidden;
  const scopedFeature=casesViewOpen?$("#tc-feat").value:(currentFeature||"");
  const scopedLink=(c.features||[]).find(feature=>feature.id===scopedFeature);
  const refreshAfterDelete=()=>{
    $("#modal").classList.remove("show");loadCases();
    if(currentFeature)openFeature(currentFeature);
  };
  if(scopedLink){
    const inherited=["reused","carried","carried_repaired","inherited","adapted"].includes(scopedLink.origin);
    openCaseConfirmation({
      title:"Remove testcase from this feature",
      copy:links>1
        ?`This removes “${c.title}” only from ${scopedLink.name}. Its ${links-1} other feature link${links-1===1?"":"s"} will stay intact.`
        :`This is the testcase's only feature link, so removing it from ${scopedLink.name} will also remove the orphaned testcase.`,
      summary:`<b>${esc(c.display_id||"")} ${esc(c.title)}</b><div class="muted" style="margin-top:6px">${inherited?"Inherited / reused here":"Created here"} · linked to ${links} feature${links===1?"":"s"}</div>`,
      confirmLabel:`Remove from ${scopedLink.name}`,
      onConfirm:async()=>{
        await api(`/api/features/${scopedFeature}/test-cases/${cid}`,{method:"DELETE"});
        refreshAfterDelete();toast(links>1?"Removed from this feature; other links were preserved":"Testcase removed");
      },
      secondaryLabel:links>1?"Delete everywhere":null,
      onSecondary:links>1?async()=>{
        await api(`/api/test-cases/${cid}?force=true`,{method:"DELETE"});
        refreshAfterDelete();toast("Testcase deleted from every feature");
      }:null
    });
    return;
  }
  openCaseConfirmation({
    title:"Delete testcase",
    copy:links>1?`This is a global delete. “${c.title}” will be removed from all ${links} linked features.`:`“${c.title}” will be permanently deleted.`,
    summary:`<b>${esc(c.title)}</b><div class="muted" style="margin-top:6px">${links} feature link${links===1?"":"s"} · ${(c.steps||[]).length} step${(c.steps||[]).length===1?"":"s"}</div>`,
    confirmLabel:links>1?"Delete from all features":"Delete testcase",danger:true,
    onConfirm:async()=>{
      await api(`/api/test-cases/${cid}${links>1?"?force=true":""}`,{method:"DELETE"});
      refreshAfterDelete();toast("Testcase deleted");
    }
  });
};

// ---- feature delete / rename ----
$("#d-del").onclick=async()=>{
  if(!currentFeature)return;
  const featureId=currentFeature;
  openCaseConfirmation({
    title:"Delete feature",
    copy:"This removes the feature, its document chunks, and its testcase links. Testcases still linked to another feature will not be deleted.",
    summary:`<b>${esc($("#d-name").textContent)}</b><div class="muted" style="margin-top:6px">${esc($("#d-meta").textContent)}</div>`,
    confirmLabel:"Delete feature",danger:true,
    onConfirm:async()=>{
      const r=await api("/api/features/"+featureId,{method:"DELETE"});
      currentFeature=null;showFeatureList();loadFeatures();refreshStatus();
      toast(`Feature deleted · ${r.removed_orphan_cases} orphan testcase(s) removed · ${r.preserved_shared_cases} shared testcase(s) preserved`);
    }
  });
};
$("#d-rename").onclick=async()=>{if(!currentFeature)return;const name=await uiPrompt("Rename feature","Feature name",$("#d-name").textContent);if(!name)return;await api("/api/features/"+currentFeature,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});openFeature(currentFeature);loadFeatures();toast("Renamed");};
// ---- new version ----
$("#d-newver").onclick=()=>{if(!currentFeature)return;$("#vm-feat").textContent=`${$("#d-name").textContent} — current ${$("#d-version").selectedOptions[0]?.textContent||""}`;$("#vm-file").value="";$("#vm-text").value="";if($("#vm-confluence"))$("#vm-confluence").value="";if($("#vm-figma"))$("#vm-figma").value="";$("#vm-replace").checked=false;$("#vm-msg").textContent="";$("#vmodal").classList.add("show");};
if ($("#d-reuse-imports")) $("#d-reuse-imports").onclick = () => {
  if (!currentFeature) { toast("Open a feature first", true); return; }
  openImportLibraryModal(currentFeature);
};
$("#vm-cancel").onclick=()=>$("#vmodal").classList.remove("show");
$("#vm-go").onclick=async()=>{
  const splitLinks=el=>((el&&el.value)||"").split(/[\s,]+/).map(s=>s.trim()).filter(Boolean);
  const vConfl=splitLinks($("#vm-confluence"));
  const vFigma=splitLinks($("#vm-figma"));
  if(!$("#vm-file").files.length && !$("#vm-text").value.trim() && !vConfl.length && !vFigma.length){$("#vm-msg").innerHTML=`<span class="err">Upload a doc, paste text, or add a Confluence/Figma link.</span>`;return;}
  $("#vm-go").disabled=true;$("#vm-msg").textContent="uploading + diffing against previous version…";
  const fd=new FormData();for(const f of $("#vm-file").files)fd.append("files",f);fd.append("text",$("#vm-text").value);fd.append("replace",$("#vm-replace").checked?"true":"false");
  vConfl.forEach(u=>fd.append("confluence_url",u));
  vFigma.forEach(u=>fd.append("figma_url",u));
  try{const r=await api(`/api/features/${currentFeature}/versions`,{method:"POST",body:fd});
    const d=r.diff||{};
    $("#vm-msg").innerHTML=`<span class="ok">v${r.version} created — ${d.kept||0} kept${d.retired&&d.retired.length?`, ${d.retired.length} retired`:""}. Generating new cases…</span>`;
    toast(`Version ${r.version} created`);
    setTimeout(()=>{$("#vmodal").classList.remove("show");openFeature(r.feature_id).then(()=>watchFeatureGen(r.job_id,r.feature_id));loadFeatures();},1200);
  }catch(e){$("#vm-msg").innerHTML=`<span class="err">${esc(e.message)}</span>`;}finally{$("#vm-go").disabled=false;}};

// ---- test cycles + code analysis ----
async function initCycles(){await loadProjects();await loadCycleRepos();loadUnmappedPRs();loadLatestAnalysis();}
$("#cyc-proj").onchange=()=>{currentProject=$("#cyc-proj").value;loadCycleRepos();loadUnmappedPRs();loadLatestAnalysis();};
if($("#cyc-refresh")) $("#cyc-refresh").onclick=()=>{loadCycleRepos();loadUnmappedPRs();loadLatestAnalysis();};
// ---- Test Cycles view (independent of change-impact analysis) ----
async function initTestCycles(){await loadProjects();if($("#tcy-proj"))$("#tcy-proj").value=currentProject;loadCycles();loadCycleTemplates();}
if($("#tcy-proj"))$("#tcy-proj").onchange=()=>{currentProject=$("#tcy-proj").value;loadCycles();loadCycleTemplates();};
if($("#tcy-refresh"))$("#tcy-refresh").onclick=()=>{loadCycles();loadCycleTemplates();};
async function createEmptyCycle(){
  const pid=($("#tcy-proj")&&$("#tcy-proj").value)||currentProject;
  if(!pid){toast("Select a project first",true);return;}
  const name=($("#tcy-name")&&$("#tcy-name").value.trim())||`Cycle ${new Date().toLocaleDateString()}`;
  try{const r=await api("/api/test-cycles",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:pid,name,case_ids:[]})});
    if($("#tcy-name"))$("#tcy-name").value="";toast("Cycle created — add the test cases you want to retest");loadCycles();if(r&&r.id)openCycle(r.id);}
  catch(e){toast(e.message||"Could not create cycle",true);}
}
window.createEmptyCycle=createEmptyCycle;
if($("#tcy-new"))$("#tcy-new").onclick=createEmptyCycle;
async function loadCycleRepos(){const pid=$("#cyc-proj").value||currentProject;if(!pid)return;
  try{const r=await api(`/api/projects/${pid}/repos?repo_type=app`);   // app repos only (test repos excluded)
    $("#cyc-repos").innerHTML=repoBranchRows(r.repos,"cyc-repo");
    fillBranchDropdowns("cyc-repo",r.repos);
    if($("#pr-repo"))$("#pr-repo").innerHTML=r.repos.map(rp=>`<option value="${rp.id}">${esc(rp.full_name)}</option>`).join("");
  }catch(e){}}
async function loadUnmappedPRs(){const pid=$("#cyc-proj").value||currentProject;if(!pid||!$("#unmapped-prs"))return;
  try{const [u,f]=await Promise.all([api(`/api/projects/${pid}/unmapped-prs`),api(`/api/features?project_id=${pid}`)]);
    const feats=f.features||f.items||[];
    if(!u.prs.length){$("#unmapped-prs").innerHTML=`<span class="muted">no unmapped PRs 🎉</span>`;return;}
    const opts=feats.map(ft=>`<option value="${ft.id}">${esc(ft.name)}</option>`).join("");
    $("#unmapped-prs").innerHTML=u.prs.map(p=>`<div class="stepitem" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer"><b>#${p.number}</b></a> ${esc(p.title||"")} <span class="muted">· ${esc(p.repo||"")}</span>
      <select class="asg-feat" data-pr="${p.id}" style="width:auto;flex:0 0 220px">${opts}</select>
      <button class="go asg-btn" data-pr="${p.id}" style="flex:0 0 auto;padding:5px 12px">Assign & cover</button></div>`).join("");
    document.querySelectorAll(".asg-btn").forEach(b=>b.onclick=async()=>{
      const pr=b.dataset.pr;const sel=document.querySelector(`.asg-feat[data-pr="${pr}"]`);const fid=sel&&sel.value;
      if(!fid){toast("Pick a feature",true);return;}
      b.disabled=true;b.textContent="Assigning…";
      try{await api(`/api/prs/${pr}/assign`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({feature_id:fid})});
        toast("Assigned ✓ — coverage is computing in the background (check the feature's coverage shortly)");
        loadUnmappedPRs();}
      catch(e){toast("Assign failed: "+e.message,true);b.disabled=false;b.textContent="Assign & cover";}});
  }catch(e){$("#unmapped-prs").innerHTML=`<span class="muted">${esc(e.message)}</span>`;}}
$("#cyc-analyze").onclick=async()=>{
  const ids=[...document.querySelectorAll(".cyc-repo-chk")].filter(c=>c.checked).map(c=>c.value);
  if(!ids.length){toast("Select at least one repo",true);return;}
  const days=parseInt($("#cyc-days").value)||14;const pid=$("#cyc-proj").value||currentProject;const branches=collectBranches("cyc-repo");
  $("#cyc-impacted").innerHTML="";$("#cyc-create").style.display="none";$("#cyc-status").textContent=`Starting change impact review for ${ids.length} repo${ids.length===1?"":"s"}…`;$("#cyc-analyze").disabled=true;
  try{const r=await api("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:pid,repo_ids:ids,branches,days})});watchAnalyze(r.job_id);}
  catch(e){$("#cyc-status").innerHTML=`<span class="err">${esc(e.message)}</span>`;$("#cyc-analyze").disabled=false;}};

function formatCycleStage(stage){
  const s=(stage||"").toLowerCase();
  if(!s)return "Preparing change impact review…";
  if(s.startsWith("fetching github commits")||s.startsWith("fetching gitlab commits")) return "Reading recent commits from the selected repositories…";
  if(s.startsWith("grounded matching")) return "Matching changed code to impacted test cases…";
  if(s.startsWith("llm impact analysis")) return "Reviewing the remaining cases for likely impact…";
  return stage;
}

function cycleImpactStatusBadge(status){
  const s=(status||"").toLowerCase();
  if(s==="matched"||s==="covered") return `<span class="badge mm-covered">Direct match</span>`;
  if(s==="review_needed"||s==="partial") return `<span class="badge mm-partial">Needs review</span>`;
  return `<span class="badge mm-uncovered">Unverified</span>`;
}

function cycleImpactConfidenceBadges(confidence,tier,signalType){
  const badges=[];
  if(confidence!=null) badges.push(`<span class="badge">${Math.round(confidence*100)}% confidence</span>`);
  if(tier) badges.push(`<span class="badge">Tier ${tier}</span>`);
  if(signalType==="ai") badges.push(`<span class="pill">Model reviewed</span>`);
  return badges.join("");
}

function cycleImpactTypeBadge(type){
  const normalized=type||"functional";
  return `<span class="badge ${esc(normalized)}">${esc(typeLabel(normalized))}</span>`;
}

function cycleImpactRiskBadge(risk){
  const s=(risk||"medium").toString().trim().toLowerCase();
  const k=["high","critical","p1"].includes(s)?"high":(["low","p3"].includes(s)?"low":"medium");
  const C={high:["rgba(239,68,68,0.25)","rgba(239,68,68,0.12)","#fca5a5"],
           medium:["rgba(59,130,246,0.25)","rgba(59,130,246,0.12)","#93c5fd"],
           low:["rgba(34,197,94,0.25)","rgba(34,197,94,0.12)","#86efac"]}[k];
  const label={high:"High",medium:"Medium",low:"Low"}[k];
  return `<span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px;border:1px solid ${C[0]};background:${C[1]};color:${C[2]}">${label} risk</span>`;
}

function cycleImpactNarrative(c){
  if(c.signal_type==="endpoint") return c.signal
    ? `A changed API endpoint directly maps to this testcase, so it should be part of the next regression pass.`
    : `A changed API endpoint directly maps to this testcase.`;
  if(c.signal_type==="symbol") return c.signal
    ? `A changed implementation signal overlaps with this testcase closely enough to treat it as directly impacted.`
    : `A changed implementation signal overlaps with this testcase closely enough to treat it as directly impacted.`;
  if(c.signal_type==="ai") return c.reason
    ? c.reason
    : `The broader change set looks related to this testcase, so it is included for a quick manual review.`;
  return c.reason || "This testcase appears related to the recent implementation changes.";
}

function cycleImpactSignalRow(c){
  if(!c.signal) return "";
  const label = c.signal_type==="endpoint" ? "Matched endpoint" : c.signal_type==="symbol" ? "Matched code signal" : "Reference";
  return `<div class="cycle-impact-signal"><span class="pill">${label}</span><code>${esc(c.signal)}</code></div>`;
}

function cycleImpactEvidence(ev){
  if(!(ev||[]).length){
    return `<div class="cycle-impact-empty">No direct code evidence was saved for this item. It was surfaced from the broader impact review.</div>`;
  }
  return `<div class="cycle-impact-evidence">
    <div class="cycle-impact-evidence-label">Code evidence</div>
    ${(ev||[]).map(e=>{
      const fileLine=`${esc(e.file||"")}${e.line?`:${e.line}`:""}`;
      const commit=(e.sha||"").slice(0,7);
      const row=`<span class="cycle-impact-evidence-file">${fileLine}</span><span class="cycle-impact-evidence-meta">${commit?`<span class="pill">${esc(commit)}</span>`:""}${e.repo?`<span class="badge">${esc(e.repo)}</span>`:""}</span>`;
      return e.url
        ? `<a class="cycle-impact-evidence-row" href="${e.url}" target="_blank" rel="noopener">${row}</a>`
        : `<div class="cycle-impact-evidence-row">${row}</div>`;
    }).join("")}
  </div>`;
}

function watchAnalyze(jobId){if(!jobId)return;watchJob(jobId,j=>{const a=j.result||{};
  $("#cyc-status").innerHTML=j.status==="running"?`⏳ ${esc(formatCycleStage(j.stage))}${a.commit_count?` (${a.commit_count} commits, ${(a.changed_files||[]).length} files)`:""}`
    :j.status==="failed"?`<span class="err">Analysis failed: ${esc(j.error||"")}</span>`
    :`Review complete · ${a.commit_count||0} commits · ${(a.changed_files||[]).length} files changed${a.note?` · ${esc(a.note)}`:""}`;
  if(j.status==="running")return;
  $("#cyc-analyze").disabled=false;
  renderImpacted(a);
});}
function renderImpacted(a){
  ANALYSIS_IMPACTED=a.impacted||[];
  if(!ANALYSIS_IMPACTED.length){
    $("#cyc-impacted").innerHTML=`<div class="mindmap-summary-card"><div class="mindmap-summary-head"><h2>No impacted test cases</h2><div class="mindmap-chip-row"><span class="badge">0 impacted</span></div></div><div class="sub">No recent changes in the selected repositories mapped to the current test suite for this lookback window.</div></div>`;
    $("#cyc-create").style.display="none";return;
  }
  const grounded=a.grounded||0, ai=a.ai||0, commits=a.commits||[];
  const summary=`<div class="mindmap-summary-card"><div class="mindmap-summary-head"><h2>Impact review</h2><div class="mindmap-chip-row"><span class="badge mm-covered">${grounded} direct evidence</span><span class="badge mm-partial">${ai} needs review</span><span class="badge">${ANALYSIS_IMPACTED.length} impacted cases</span></div></div><div class="sub">These testcases are the strongest candidates for regression based on the selected code changes. Open any row to inspect the matching signal and exact evidence.</div></div>`;
  const items=`<div class="cycles-select-bar" style="align-items:center;gap:12px;flex-wrap:wrap">
    <label class="case-select-label" style="margin:0"><input type="checkbox" id="imp-select-all" onchange="toggleImpactSelection(this.checked)" style="width:auto"/> Select all impacted cases</label>
    <span class="cycles-select-count" id="imp-selected-count">0 selected</span>
    <button class="go" id="imp-create-top" style="margin-left:auto;padding:6px 14px" onclick="createCycleFromSelection()">Create cycle from selected</button>
  </div>` + ANALYSIS_IMPACTED.map((c,i)=>{
    const evidenceCount=(c.evidence||[]).length;
    const sourceLabel=c.signal_type==="ai"?"Model-reviewed suggestion":"Direct code evidence";
    return `<details class="cycle-impact-item">
      <summary>
        <span class="cycle-impact-check" onclick="event.preventDefault();event.stopPropagation()"><input type="checkbox" class="imp-chk" data-i="${i}" onchange="updateImpactSelectionUI()" onclick="event.stopPropagation()" style="width:auto"/></span>
        <span class="cycle-impact-toggle" aria-hidden="true"></span>
        <div class="cycle-impact-main">
          <div class="cycle-impact-title">${c.display_id?`<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;color:#94a3b8;margin-right:6px">${esc(c.display_id)}</code>`:""}${esc(c.title)}</div>
          <div class="cycle-impact-sub"><span>${esc(typeLabel(c.type))}</span><span>·</span><span>${esc(sourceLabel)}</span><span>·</span><span>${evidenceCount} evidence point${evidenceCount===1?"":"s"}</span></div>
        </div>
        <div class="cycle-impact-badges">${cycleImpactStatusBadge(c.status)}${cycleImpactTypeBadge(c.type)}${cycleImpactRiskBadge(c.risk)}</div>
      </summary>
      <div class="cycle-impact-body">
        <div class="cycle-impact-summary">${esc(cycleImpactNarrative(c))}</div>
        ${stepsHtml(c.steps)}
        ${cycleImpactSignalRow(c)}
        ${cycleImpactEvidence(c.evidence)}
      </div>
    </details>`;}).join("");
  let html=summary+`<div class="mindmap-feature-card"><div class="mindmap-feature-head"><div><div class="mindmap-feature-title"><strong>Impacted test cases</strong></div><div class="mindmap-feature-meta">Select the cases you want to carry into a release regression cycle.</div></div><div class="mindmap-chip-row"><span class="pill">${ANALYSIS_IMPACTED.length} case${ANALYSIS_IMPACTED.length===1?"":"s"}</span></div></div><div class="mindmap-case-list">${items}</div></div>`;
  if(commits.length){html+=
    `<div class="card mindmap-diagnostics cycles-commit-list"><details><summary>${commits.length} commits reviewed as evidence</summary><div class="sub">`+
    commits.map(cm=>`<div class="stepitem">${cm.repo?`<span class="pill">${esc(cm.repo)}</span> `:""}<a href="${esc(cm.url)}" target="_blank" rel="noopener noreferrer">${esc(cm.sha)}</a> <span class="muted">${esc(cm.message)}</span></div>`).join("")+`</div></details></div>`;}
  $("#cyc-impacted").innerHTML=html;
  $("#cyc-create").style.display="";
  updateImpactSelectionUI();
}
window.toggleImpactSelection=(checked)=>{document.querySelectorAll(".imp-chk").forEach(c=>{c.checked=!!checked;});updateImpactSelectionUI();};
window.updateImpactSelectionUI=()=>{
  const boxes=[...document.querySelectorAll(".imp-chk")];
  const selected=boxes.filter(c=>c.checked).length;
  const all=boxes.length>0 && selected===boxes.length;
  if($("#imp-select-all")) $("#imp-select-all").checked=all;
  if($("#imp-selected-count")) $("#imp-selected-count").textContent=`${selected} selected`;
  if($("#cyc-make")){
    $("#cyc-make").disabled = selected===0;
    $("#cyc-make").textContent = selected>0 ? `Create cycle (${selected})` : "Create cycle";
  }
};
function clearImpacted(msg){ANALYSIS_IMPACTED=[];if($("#cyc-impacted"))$("#cyc-impacted").innerHTML="";if($("#cyc-status"))$("#cyc-status").innerHTML=msg?`<span class="muted">${msg}</span>`:"";if($("#cyc-create"))$("#cyc-create").style.display="none";}
async function loadLatestAnalysis(){const pid=$("#cyc-proj").value||currentProject;if(!pid||!$("#cyc-impacted"))return;
  clearImpacted("");   // reset so a project with no saved analysis doesn't show the previous one
  try{const run=await api(`/api/projects/${pid}/commit-analysis/latest`);
    const results=run.results||[];
    if(!results.length){clearImpacted("No saved impact analysis for this project yet — click Analyze changes.");return;}
    const grounded=results.filter(r=>r.signal_type&&r.signal_type!=="ai").length;
    const ai=results.filter(r=>r.signal_type==="ai").length;
    $("#cyc-status").innerHTML=`<span class="muted">↻ Restored the latest saved impact review · ${results.length} impacted case(s)</span>`;
    renderImpacted({impacted:results,grounded,ai,commits:run.commits||[]});
  }catch(e){clearImpacted("");}}
async function createCycleFromSelection(){
  const ids=[...document.querySelectorAll(".imp-chk")].filter(c=>c.checked).map(c=>ANALYSIS_IMPACTED[+c.dataset.i].case_id);
  if(!ids.length){toast("Select at least one case",true);return;}
  const name=($("#cyc-name")&&$("#cyc-name").value.trim())||`Cycle ${new Date().toLocaleDateString()}`;
  const pid=$("#cyc-proj").value||currentProject;
  const repoIds=[...document.querySelectorAll(".cyc-repo-chk")].filter(c=>c.checked).map(c=>c.value);
  try{await api("/api/test-cycles",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:pid,name,case_ids:ids,source:{repo_ids:repoIds,days:parseInt($("#cyc-days").value)||14}})});
    if($("#cyc-name"))$("#cyc-name").value="";toast(`Cycle created with ${ids.length} case(s) — see it under Test Cycles`);loadCycles();}
  catch(e){toast(e.message,true);}}
window.createCycleFromSelection=createCycleFromSelection;
if($("#cyc-make"))$("#cyc-make").onclick=createCycleFromSelection;
async function loadCycleTemplates(){const pid=($("#tcy-proj")&&$("#tcy-proj").value)||currentProject;if(!pid||!$("#cyc-templates"))return;
  try{const r=await api(`/api/projects/${pid}/cycle-templates`);
    $("#cyc-templates").innerHTML=(r.templates||[]).map(t=>`<div class="feat" style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <div><div class="n">${esc(t.name)}</div><div class="m">${t.case_count} case(s)${t.description?` · ${esc(t.description)}`:""}</div></div>
      <div style="display:flex;gap:6px"><button class="go" style="padding:5px 12px" onclick="newCycleFromTemplate('${t.id}')">New cycle</button><button class="danger" style="padding:5px 12px" onclick="deleteCycleTemplate('${t.id}')">Delete</button></div>
    </div>`).join("")||`<span class="muted">no templates yet — open a cycle and click “Save as template”</span>`;
  }catch(e){}}
window.saveCycleAsTemplate=async(cid)=>{
  const name=await uiPrompt("Save cycle as template","Template name",(window.CYCLE_DETAIL_DATA||{}).name||"");
  if(name==null)return;const n=name.trim();if(!n){toast("Name required",true);return;}
  try{await api(`/api/test-cycles/${cid}/save-template`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n})});toast("Template saved");loadCycleTemplates();}
  catch(e){toast(e.message,true);}};
window.newCycleFromTemplate=async(tid)=>{
  const name=await uiPrompt("New cycle from template","Cycle name",`Cycle ${new Date().toLocaleDateString()}`);
  if(name==null)return;const n=name.trim();if(!n){toast("Name required",true);return;}
  try{const r=await api(`/api/cycle-templates/${tid}/create-cycle`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:n})});
    toast("Cycle created from template");loadCycles();if(r&&r.id)openCycle(r.id);}
  catch(e){toast(e.message,true);}};
window.deleteCycleTemplate=async(tid)=>{
  if(!await uiConfirm("Delete this template? Existing cycles are not affected.","Delete template","Delete",true))return;
  try{await api(`/api/cycle-templates/${tid}`,{method:"DELETE"});toast("Template deleted");loadCycleTemplates();}
  catch(e){toast(e.message,true);}};
async function loadCycles(){const pid=($("#tcy-proj")&&$("#tcy-proj").value)||currentProject;if(!pid)return;
  skIn("#cyc-list",skeleton.rows(5,"Loading test cycles"));
  try{const r=await api(`/api/projects/${pid}/test-cycles`);
    $("#cyc-list").innerHTML=r.cycles.map(c=>{const cc=c.counts||{};const done=(cc.passed||0)+(cc.failed||0)+(cc.skipped||0)+(cc.blocked||0),pct=c.total?Math.round(done/c.total*100):0;
      return `<div class="feat" onclick="openCycle('${c.id}')"><div class="n">${esc(c.name)} <span class="badge">${esc(c.status||"draft")}</span></div>
        <div class="progress" style="margin:7px 0 4px"><div class="pbar" style="width:${pct}%"></div></div>
        <div class="m">${done}/${c.total} executed · ${cc.passed||0} passed · ${cc.failed||0} failed · ${cc.skipped||0} skipped · ${cc.blocked||0} blocked · ${esc(c.environment||"environment not set")}</div></div>`;}).join("")||`<span class="muted">no cycles yet</span>`;
  }catch(e){if($("#cyc-list"))$("#cyc-list").innerHTML=`<div class="err">Couldn't load test cycles. ${esc(e.message)}</div>`;}}
window.CYCLE_DETAIL_DATA=null;
window.CYCLE_EDIT_ITEM=null;
window.CYCLE_EDIT_DRAFT=null;
const cycleStatusOptions=st=>["pending","passed","failed","skipped","blocked"].map(s=>`<option ${s===st?"selected":""}>${s}</option>`).join("");
const cycleStatusPill=st=>`<span class="cycle-status-pill ${esc(st||"pending")}">${esc(st||"pending")}</span>`;
function cycleNeedsInlineEditor(item,itemId){
  return window.CYCLE_EDIT_ITEM===itemId || ((item.execution_status==="failed"||item.execution_status==="blocked") && !!(item.actual_result||item.notes||item.defect_link));
}
function renderCycleDetail(c){
  window.CYCLE_DETAIL_DATA=c;
  $("#cyc-detail-card").style.display="block";
  $("#cyc-d-name").innerHTML=`${esc(c.name)} <span class="badge">${esc(c.status||"draft")}</span>`;
  const cc=c.counts||{},done=(cc.passed||0)+(cc.failed||0)+(cc.skipped||0)+(cc.blocked||0),pct=c.total?Math.round(done/c.total*100):0;
  const cycToday=new Date().toISOString().slice(0,10);
  const cycStart=c.scheduled_start_at?String(c.scheduled_start_at).slice(0,10):"";
  const cycEnd=c.scheduled_end_at?String(c.scheduled_end_at).slice(0,10):"";
  const items=(c.items||[]).map(it=>{
    const itemId=it.id;
    const editing=window.CYCLE_EDIT_ITEM===itemId;
    const draft=editing ? (window.CYCLE_EDIT_DRAFT||{}) : {};
    const status=editing ? (draft.status||it.execution_status||"pending") : (it.execution_status||"pending");
    const actual=editing ? (draft.actual_result ?? it.actual_result ?? "") : (it.actual_result||"");
    const notes=editing ? (draft.notes ?? it.notes ?? "") : (it.notes||"");
    const defect=editing ? (draft.defect_link ?? it.defect_link ?? "") : (it.defect_link||"");
    const showEditor = editing || cycleNeedsInlineEditor(it,itemId);
    const noteSummary = !showEditor && (actual||notes||defect)
      ? `<div class="cycle-exec-notes"><div>${esc(actual||notes)}</div>${defect?`<div style="margin-top:4px"><a href="${esc(defect)}" target="_blank" rel="noopener">Open defect link</a></div>`:""}</div>`
      : "";
    const steps=stepsHtml(it.steps);
    const editor = showEditor ? `<div class="cycle-exec-editor">
      <div class="cycle-exec-editor-grid">
        <div class="full"><label>Execution result</label><textarea oninput="updateCycleDraftField('actual_result',this.value)">${esc(actual)}</textarea></div>
        <div class="full"><label>Notes</label><textarea oninput="updateCycleDraftField('notes',this.value)">${esc(notes)}</textarea></div>
        <div class="full"><label>Defect link</label><input value="${esc(defect)}" placeholder="https://…" oninput="updateCycleDraftField('defect_link',this.value)"/></div>
      </div>
      <div class="cycle-exec-actions"><button class="ghost" onclick="cancelCycleItemEdit()">Cancel</button><button class="go" onclick="saveCycleItemStatus('${c.id}','${itemId}')">Save status</button></div>
    </div>` : "";
    return `<div class="cycle-exec-item status-${esc(status)}">
      <div class="cycle-exec-head">
        <div class="cycle-exec-order">${it.display_order||""}</div>
        <div>
          <div class="cycle-exec-title">${it.display_id?`<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;color:#94a3b8;margin-right:6px">${esc(it.display_id)}</code>`:""}${esc(it.title)}</div>
          <div class="cycle-exec-sub"><span class="badge ${it.category}">${esc(it.category||"")}</span>${it.priority?prioBadge(it.priority):""}${cycleStatusPill(status)}${it.case_id?`<button class="ghost" style="padding:1px 9px;font-size:10.5px" onclick="event.stopPropagation();editCase('${it.case_id}')">Edit case</button>`:""}</div>
          ${steps}
        </div>
        <div class="cycle-exec-priority muted">${it.priority?prioLabel(it.priority):""}</div>
        <div class="cycle-exec-status"><select onchange="startCycleItemStatusEdit('${c.id}','${itemId}',this.value)" style="width:100%">${cycleStatusOptions(status)}</select></div>
      </div>
      ${noteSummary}
      ${editor}
    </div>`;
  }).join("");
  $("#cyc-d-items").innerHTML=`<div class="muted" style="margin:8px 0">${esc(c.description||"")} ${c.environment?`· env <b>${esc(c.environment)}</b>`:""} ${c.build_version?`· build <b>${esc(c.build_version)}</b>`:""}</div>
    <div class="progress"><div class="pbar" style="width:${pct}%"></div></div>
    <div class="cycle-detail-summary">
      <div class="cycle-detail-kpi"><b>${c.total||0}</b><span>Total cases</span></div>
      <div class="cycle-detail-kpi"><b>${cc.passed||0}</b><span>Passed</span></div>
      <div class="cycle-detail-kpi"><b>${cc.failed||0}</b><span>Failed</span></div>
      <div class="cycle-detail-kpi"><b>${cc.blocked||0}</b><span>Blocked</span></div>
      <div class="cycle-detail-kpi"><b>${pct}%</b><span>Progress</span></div>
    </div>
    <div class="cycle-detail-actions"><a class="export-btn" href="/api/test-cycles/${c.id}/export/csv">Export CSV</a><a class="export-btn" href="/api/test-cycles/${c.id}/export/pdf">Export PDF</a><button class="ghost" onclick="showCycleReport('${c.id}')">View summary</button><button class="ghost" onclick="editCycleDescription('${c.id}')">Edit description</button><button class="ghost" onclick="saveCycleAsTemplate('${c.id}')">Save as template</button></div>
    <div class="cycle-detail-actions" style="margin-top:10px;align-items:center;flex-wrap:wrap;gap:12px">
      <label class="muted" style="font-size:12px;display:flex;align-items:center;gap:6px">Start <input type="date" id="cyc-start" value="${cycStart}" min="${cycToday}" onchange="scheduleCycle('${c.id}','scheduled_start_at',this.value)" style="width:auto;padding:4px 8px"/></label>
      <label class="muted" style="font-size:12px;display:flex;align-items:center;gap:6px">End <input type="date" id="cyc-end" value="${cycEnd}" min="${cycStart||cycToday}" onchange="scheduleCycle('${c.id}','scheduled_end_at',this.value)" style="width:auto;padding:4px 8px"/></label>
      ${cycleDateStatus(cycStart,cycEnd)}
      <button class="go" style="padding:5px 12px;margin-left:auto" onclick="openAddCaseChooser('${c.id}')">+ Add test cases</button>
    </div>
    <div class="cycle-exec-list">${items}</div>`;
  $("#cyc-detail-card").scrollIntoView({behavior:"smooth"});
}
window.openCycle=async id=>{try{
  const c=await api("/api/test-cycles/"+id);
  window._cycle=id;
  window.CYCLE_EDIT_ITEM=null;
  window.CYCLE_EDIT_DRAFT=null;
  renderCycleDetail(c);
}catch(e){toast(e.message,true);}};
window.openCreateCaseInCycle=async(cid)=>{
  const pid=(window.CYCLE_DETAIL_DATA||{}).project_id||currentProject;
  let feats=[];
  try{const r=await api(`/api/features?project_id=${encodeURIComponent(pid)}`);feats=r.features||[];}
  catch(e){toast(e.message,true);return;}
  if(!feats.length){toast("Create a feature first — every test case must belong to a feature",true);return;}
  const proceed=(fid)=>{
    editing={id:null,feature_id:fid,cycle_id:cid,shared_with_features:0,steps:[{action:"",expected:""}]};
    $("#m-heading").textContent="Create test case (adds to this cycle)";
    $("#m-title").value="";$("#m-type").value="functional";$("#m-prio").value="Medium";$("#m-pre").value="";
    $("#m-tags").value="from-test-cycle";
    $("#m-warn").textContent="Gets a new project ID, is linked to the selected feature, tagged “from-test-cycle”, and added to this cycle.";
    $("#m-del").style.display="none";renderSteps();$("#m-msg").textContent="";$("#modal").classList.add("show");
  };
  if(feats.length===1){proceed(feats[0].id);return;}
  const ov=document.createElement("div");
  ov.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML=`<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:460px;width:90%;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:6px">New test case → which feature?</div>
    <div class="muted" style="font-size:12px;margin-bottom:10px">Every test case belongs to a feature. It'll also be added to this cycle and tagged <code>from-test-cycle</code>.</div>
    <select id="ncf-feat" style="width:100%">${feats.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join("")}</select>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="ncf-cancel">Cancel</button><button class="go" id="ncf-go">Continue</button></div></div>`;
  document.body.appendChild(ov);
  ov.onclick=e=>{if(e.target===ov)ov.remove();};
  document.getElementById("ncf-cancel").onclick=()=>ov.remove();
  document.getElementById("ncf-go").onclick=()=>{const fid=document.getElementById("ncf-feat").value;ov.remove();proceed(fid);};
};
function cycleDateStatus(start,end){const t=new Date().toISOString().slice(0,10);
  if(start&&t<start)return `<span class="badge mm-partial">Scheduled</span>`;
  if(end&&t>end)return `<span class="badge">Ended</span>`;
  if(start||end)return `<span class="badge mm-covered">Active</span>`;
  return "";}
window.scheduleCycle=async(cid,field,value)=>{
  const c0=window.CYCLE_DETAIL_DATA||{};
  const start=field==="scheduled_start_at"?value:(c0.scheduled_start_at?String(c0.scheduled_start_at).slice(0,10):"");
  const end=field==="scheduled_end_at"?value:(c0.scheduled_end_at?String(c0.scheduled_end_at).slice(0,10):"");
  if(start&&end&&end<start){toast("End date can't be before the start date",true);renderCycleDetail(c0);return;}
  try{const c=await api("/api/test-cycles/"+cid,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({[field]:value||""})});
    renderCycleDetail(c);toast(value?"Schedule updated":"Schedule cleared");}
  catch(e){toast(e.message,true);}};
window.editCycleDescription=async(cid)=>{
  const cur=(window.CYCLE_DETAIL_DATA||{}).description||"";
  const d=await uiPrompt("Edit cycle description","Description",cur);
  if(d==null)return;
  try{const c=await api("/api/test-cycles/"+cid,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({description:d})});
    renderCycleDetail(c);toast("Description updated");}
  catch(e){toast(e.message,true);}};
window.openAddCaseChooser=(cid)=>{
  const ov=document.createElement("div");
  ov.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML=`<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:420px;width:88%;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:12px">Add test cases</div>
    <button class="go" id="acc-existing" style="width:100%;margin-bottom:8px;padding:9px">From existing project cases</button>
    <button class="ghost" id="acc-new" style="width:100%;padding:9px">Create a new test case</button>
    <div style="text-align:right;margin-top:12px"><button class="ghost" id="acc-cancel">Cancel</button></div></div>`;
  document.body.appendChild(ov);
  const close=()=>ov.remove();
  ov.onclick=e=>{if(e.target===ov)close();};
  document.getElementById("acc-cancel").onclick=close;
  document.getElementById("acc-existing").onclick=()=>{close();openAddCasesToCycle(cid);};
  document.getElementById("acc-new").onclick=()=>{close();openCreateCaseInCycle(cid);};};
window.openAddCasesToCycle=async(cid)=>{
  const pid=(window.CYCLE_DETAIL_DATA||{}).project_id||currentProject;
  if(!pid){toast("No project",true);return;}
  let items=[];
  try{const r=await api(`/api/test-cases?project_id=${encodeURIComponent(pid)}&limit=500`);items=r.items||[];}
  catch(e){toast(e.message,true);return;}
  const existing=new Set(((window.CYCLE_DETAIL_DATA||{}).items||[]).map(i=>i.case_id));
  const avail=items.filter(c=>!existing.has(c.id));
  if(!avail.length){toast("All project test cases are already in this cycle");return;}
  const ov=document.createElement("div");
  ov.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML=`<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:660px;width:92%;max-height:80vh;display:flex;flex-direction:column;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:4px">Add existing test cases</div>
    <div class="muted" style="font-size:12px;margin-bottom:10px">Pick cases from this project to add to the cycle.</div>
    <input id="addcase-q" placeholder="Filter by title or ID…" style="margin-bottom:10px"/>
    <div id="addcase-list" style="overflow:auto;flex:1;border:1px solid var(--line);border-radius:8px;padding:8px"></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="addcase-cancel">Cancel</button><button class="go" id="addcase-add">Add selected</button></div></div>`;
  document.body.appendChild(ov);
  const renderList=(q)=>{const ql=(q||"").toLowerCase();
    document.getElementById("addcase-list").innerHTML=avail.filter(c=>!ql||(c.title||"").toLowerCase().includes(ql)||(c.display_id||"").toLowerCase().includes(ql))
      .map(c=>`<label style="display:flex;gap:8px;align-items:center;padding:6px 4px;font-size:12.5px;border-bottom:1px solid rgba(255,255,255,.04)"><input type="checkbox" class="addcase-chk" value="${c.id}" style="width:auto"/>${c.display_id?`<code style="font-size:10px;color:#94a3b8">${esc(c.display_id)}</code>`:""}<span style="flex:1">${esc(c.title)}</span><span class="badge ${c.type}">${esc(typeLabel(c.type))}</span></label>`).join("")||`<div class="muted" style="padding:8px">No matching cases.</div>`;};
  renderList("");
  document.getElementById("addcase-q").oninput=e=>renderList(e.target.value);
  const close=()=>ov.remove();
  document.getElementById("addcase-cancel").onclick=close;
  ov.onclick=e=>{if(e.target===ov)close();};
  document.getElementById("addcase-add").onclick=async()=>{
    const ids=[...ov.querySelectorAll(".addcase-chk")].filter(x=>x.checked).map(x=>x.value);
    if(!ids.length){toast("Select at least one case",true);return;}
    try{await api(`/api/test-cycles/${cid}/items`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({case_ids:ids})});
      close();openCycle(cid);loadCycles();toast(`${ids.length} case(s) added`);}
    catch(e){toast(e.message,true);}};
};
window.startCycleItemStatusEdit=async(cid,itemId,status)=>{
  const cycle=window.CYCLE_DETAIL_DATA;
  const item=(cycle?.items||[]).find(x=>x.id===itemId);
  if(!item){toast("Cycle item not found",true);return;}
  if(status==="failed"||status==="blocked"){
    window.CYCLE_EDIT_ITEM=itemId;
    window.CYCLE_EDIT_DRAFT={status,actual_result:item.actual_result||"",notes:item.notes||"",defect_link:item.defect_link||""};
    renderCycleDetail(cycle);
    return;
  }
  await api(`/api/test-cycles/${cid}/items`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({item_id:itemId,status,actual_result:item.actual_result||"",notes:item.notes||"",defect_link:item.defect_link||""})});
  const updated=await api(`/api/test-cycles/${cid}`);
  window.CYCLE_EDIT_ITEM=null;
  window.CYCLE_EDIT_DRAFT=null;
  renderCycleDetail(updated);
  loadCycles();
  toast("status updated");
};
window.updateCycleDraftField=(field,value)=>{if(!window.CYCLE_EDIT_DRAFT)window.CYCLE_EDIT_DRAFT={};window.CYCLE_EDIT_DRAFT[field]=value;};
window.cancelCycleItemEdit=()=>{window.CYCLE_EDIT_ITEM=null;window.CYCLE_EDIT_DRAFT=null;if(window.CYCLE_DETAIL_DATA)renderCycleDetail(window.CYCLE_DETAIL_DATA);};
window.saveCycleItemStatus=async(cid,itemId)=>{
  const draft=window.CYCLE_EDIT_DRAFT||{};
  const status=draft.status||"failed";
  await api(`/api/test-cycles/${cid}/items`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({item_id:itemId,status,actual_result:draft.actual_result||"",notes:draft.notes||"",defect_link:draft.defect_link||""})});
  const updated=await api(`/api/test-cycles/${cid}`);
  window.CYCLE_EDIT_ITEM=null;
  window.CYCLE_EDIT_DRAFT=null;
  renderCycleDetail(updated);
  loadCycles();
  toast("status updated");
};
window.showCycleReport=async id=>{
  const r=await api(`/api/test-cycles/${id}/report`),s=r.summary||{};
  openInfoDialog({
    title:"Cycle summary",
    copy:"A quick progress snapshot for this saved test cycle.",
    summary:`<div class="cycle-detail-summary" style="margin-top:12px">
      <div class="cycle-detail-kpi"><b>${s.completion_rate||0}%</b><span>Completion</span></div>
      <div class="cycle-detail-kpi"><b>${s.pass_rate||0}%</b><span>Pass rate</span></div>
      <div class="cycle-detail-kpi"><b>${s.passed||0}</b><span>Passed</span></div>
      <div class="cycle-detail-kpi"><b>${s.failed||0}</b><span>Failed</span></div>
      <div class="cycle-detail-kpi"><b>${s.blocked||0}</b><span>Blocked</span></div>
    </div>`
  });
};
$("#cyc-d-close").onclick=()=>{$("#cyc-detail-card").style.display="none";};
$("#cyc-d-rename").onclick=async()=>{
  if(!window._cycle)return;
  const cur=(window.CYCLE_DETAIL_DATA||{}).name||"";
  const name=await uiPrompt("Rename test cycle","Cycle name",cur);
  if(name==null){return;}
  const trimmed=name.trim();
  if(!trimmed||trimmed===cur)return;
  try{const c=await api("/api/test-cycles/"+window._cycle,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:trimmed})});
    renderCycleDetail(c);loadCycles();toast("Cycle renamed");}
  catch(e){toast(e.message,true);}
};
$("#cyc-d-del").onclick=()=>{
  if(!window._cycle||!window.CYCLE_DETAIL_DATA)return;
  const cycle=window.CYCLE_DETAIL_DATA;
  const counts=cycle.counts||{};
  openCaseConfirmation({
    title:"Delete test cycle",
    copy:`Delete “${cycle.name}”? This removes its saved execution state and cannot be undone.`,
    summary:`<b>${esc(cycle.name)}</b><div class="muted" style="margin-top:6px">${cycle.total||0} cases · ${counts.passed||0} passed · ${counts.failed||0} failed · ${counts.blocked||0} blocked</div>`,
    confirmLabel:"Delete cycle",
    danger:true,
    onConfirm:async()=>{
      await api("/api/test-cycles/"+window._cycle,{method:"DELETE"});
      $("#cyc-detail-card").style.display="none";
      window.CYCLE_DETAIL_DATA=null;
      window.CYCLE_EDIT_ITEM=null;
      window.CYCLE_EDIT_DRAFT=null;
      loadCycles();
      toast("Cycle deleted");
    }
  });
};

// ---- mind map (deep code analysis) ----
async function initMindmap(){await loadProjects();await loadMindmapRepos();loadMindmap();}
$("#mm-proj").onchange=()=>{currentProject=$("#mm-proj").value;loadMindmapRepos();loadMindmap();};
$("#mm-refresh").onclick=()=>loadMindmap();
function repoBranchRows(repos,cls){
  return repos.map(rp=>`<div style="display:flex;gap:8px;align-items:center;font-size:12.5px">
    <label style="display:flex;gap:6px;align-items:center;margin:0;flex:1"><input type="checkbox" class="${cls}-chk" value="${rp.id}" checked style="width:auto"/> ${esc(rp.full_name)} <span class="pill">${esc(rp.kind)}</span></label>
    <select class="${cls}-branch" data-rid="${rp.id}" title="branch to analyze" style="flex:0 0 220px;font-size:12px;padding:5px 8px"><option value="">${esc(rp.default_branch||'default')} (default)</option></select>
  </div>`).join("")||`<span class="muted">no repos yet — connect one under Projects & Repos</span>`;}
// populate each repo's branch <select> from the repo's configured provider
async function fillBranchDropdowns(cls,repos){
  for(const rp of (repos||[])){
    try{const r=await api(`/api/repos/${rp.id}/branches`);
      const sel=document.querySelector(`.${cls}-branch[data-rid="${rp.id}"]`);
      if(!sel||!(r.branches||[]).length)continue;
      const def=r.default||rp.default_branch||"";
      sel.innerHTML=`<option value="">${esc(def||'default')} (default)</option>`+
        r.branches.filter(b=>b!==def).map(b=>`<option value="${esc(b)}">${esc(b)}</option>`).join("");
    }catch(e){/* leave the default-only option if branches can't be fetched */}
  }
}
function collectBranches(cls){const m={};document.querySelectorAll(`.${cls}-branch`).forEach(i=>{if(i.value.trim())m[i.dataset.rid]=i.value.trim();});return m;}
// Pick ANY repo the GitHub PAT can access, add it to the project, then it's analyzable here.
async function openGitRepoPicker(pid,reload){
  if(!pid){toast("Pick a project first",true);return;}
  let repos=[];
  try{
    // Use the PROJECT's PAT (same source the Connect-repo picker uses), not the global token.
    for(let page=1;page<=4;page++){
      const r=await api(`/api/projects/${pid}/github/accessible-repos?page=${page}`);
      const batch=r.repos||[];repos=repos.concat(batch);
      if(batch.length<30)break;
    }
  }catch(e){toast(`Couldn't list repos for this project (${e.message}). Check the project's GitHub PAT under Projects & Repos.`,true);return;}
  // drop repos already connected to this project so they don't show up twice
  try{const pr=await api(`/api/projects/${pid}/repos`);
    const existing=new Set((pr.repos||[]).map(r=>(r.full_name||"").toLowerCase()));
    repos=repos.filter(r=>!existing.has((r.full_name||"").toLowerCase()));
  }catch(e){}
  if(!repos.length){toast("No new repos to add — all your accessible repos are already in this project",true);return;}
  const ov=document.createElement("div");
  ov.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:9999";
  ov.innerHTML=`<div style="background:#0d151f;border:1px solid var(--line);border-radius:14px;max-width:680px;width:92%;max-height:82vh;display:flex;flex-direction:column;padding:18px">
    <div style="font-weight:700;font-size:15px;margin-bottom:4px">Add a repo from GitHub</div>
    <div class="muted" style="font-size:12px;margin-bottom:10px">Any repository your GitHub token can access. Selected repos are added to the project and become available to analyze here.</div>
    <input id="gitrepo-q" placeholder="Filter repositories…" style="margin-bottom:10px"/>
    <div id="gitrepo-list" style="overflow:auto;flex:1;border:1px solid var(--line);border-radius:8px;padding:8px"></div>
    <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="gitrepo-cancel">Cancel</button><button class="go" id="gitrepo-add">Add selected</button></div></div>`;
  document.body.appendChild(ov);
  const render=(q)=>{const ql=(q||"").toLowerCase();
    document.getElementById("gitrepo-list").innerHTML=repos.filter(r=>!ql||(r.full_name||"").toLowerCase().includes(ql)).slice(0,300)
      .map(r=>`<label style="display:flex;gap:8px;align-items:center;padding:6px 4px;font-size:12.5px;border-bottom:1px solid rgba(255,255,255,.04)"><input type="checkbox" class="gitrepo-chk" value="${esc(r.full_name)}" data-def="${esc(r.default_branch||'main')}" style="width:auto"/><span style="flex:1">${esc(r.full_name)}</span>${r.private?`<span class="pill">private</span>`:""}${r.language?`<span class="badge">${esc(r.language)}</span>`:""}</label>`).join("")||`<div class="muted" style="padding:8px">No matches.</div>`;};
  render("");
  document.getElementById("gitrepo-q").oninput=e=>render(e.target.value);
  const close=()=>ov.remove();ov.onclick=e=>{if(e.target===ov)close();};
  document.getElementById("gitrepo-cancel").onclick=close;
  document.getElementById("gitrepo-add").onclick=async()=>{
    const picks=[...ov.querySelectorAll(".gitrepo-chk")].filter(x=>x.checked);
    if(!picks.length){toast("Select at least one repo",true);return;}
    let ok=0,fail=0;
    for(const p of picks){
      try{await api(`/api/projects/${pid}/repos`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({repo_full_name:p.value,default_branch:p.dataset.def||"main",repo_type:"app"})});ok++;}
      catch(e){fail++;}
    }
    close();toast(`${ok} repo(s) added${fail?` · ${fail} skipped (already added or inaccessible)`:""}`);if(reload)reload();
  };
}
if($("#cyc-add-git"))$("#cyc-add-git").onclick=()=>openGitRepoPicker($("#cyc-proj").value||currentProject,loadCycleRepos);
if($("#mm-add-git"))$("#mm-add-git").onclick=()=>openGitRepoPicker($("#mm-proj").value||currentProject,loadMindmapRepos);
async function loadMindmapRepos(){const pid=$("#mm-proj").value||currentProject;if(!pid)return;
  try{const r=await api(`/api/projects/${pid}/repos?repo_type=app`);   // app repos only (test repos excluded)
    $("#mm-repos").innerHTML=repoBranchRows(r.repos,"mm-repo");
    fillBranchDropdowns("mm-repo",r.repos);
  }catch(e){}}
$("#mm-analyze").onclick=async()=>{
  const ids=[...document.querySelectorAll(".mm-repo-chk")].filter(c=>c.checked).map(c=>c.value);
  if(!ids.length){toast("Select at least one repo",true);return;}
  const pid=$("#mm-proj").value||currentProject;const branches=collectBranches("mm-repo");
  $("#mm-status").textContent=`Starting implementation coverage review for ${ids.length} repo${ids.length===1?"":"s"}…`;$("#mm-analyze").disabled=true;setBusy("#mm-analyze",true);$("#mm-diag").innerHTML="";
  skIn("#mm-map",skeleton.rows(5,"Analyzing code coverage"));
  try{const r=await api("/api/code-analysis",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:pid,repo_ids:ids,branches})});watchMindmap(r.job_id);}
  catch(e){$("#mm-status").innerHTML=`<span class="err">${esc(e.message)}</span>`;$("#mm-analyze").disabled=false;setBusy("#mm-analyze",false);}};
function formatMindmapStage(stage){
  const s=(stage||"").toLowerCase();
  if(!s)return "Preparing implementation coverage review…";
  if(s.startsWith("fetching github code")||s.startsWith("fetching gitlab code")) return "Downloading repository code…";
  if(s.startsWith("reusing index")) return "Reusing the existing code index for unchanged repositories…";
  if(s.startsWith("indexed ")) return "Indexing implementation files and preparing coverage checks…";
  if(s.startsWith("reviewing — ")) return `Reviewing coverage for ${stage.split("reviewing — ")[1]||"the selected feature"}…`;
  return stage;
}
function watchMindmap(jobId){if(!jobId)return;watchJob(jobId,j=>{const a=j.result||{};
  const progressBits=[
    a.code_chunks?`${a.code_chunks} implementation chunks indexed`:null,
    a.features_mapped?`${a.features_mapped} feature${a.features_mapped===1?"":"s"} reviewed`:null
  ].filter(Boolean).join(" · ");
  $("#mm-status").innerHTML=j.status==="running"?`⏳ ${esc(formatMindmapStage(j.stage))}${progressBits?` <span class="muted">· ${esc(progressBits)}</span>`:""}`
    :j.status==="failed"?`<span class="err">Analysis failed: ${esc(j.error||"")}</span>`
    :`Review complete · ${a.code_chunks||0} implementation chunks indexed · ${a.features_mapped||0} feature${(a.features_mapped||0)===1?"":"s"} reviewed${a.tests_skipped?` · ${a.tests_skipped} test files excluded`:""}${a.note?` · <span class="warn">${esc(a.note)}</span>`:""}${(a.errors||[]).length?` · <span class="err">${a.errors.length} repo issue(s)</span>`:""}`;
  if(j.status!=="running"){$("#mm-analyze").disabled=false;setBusy("#mm-analyze",false);
    renderMindmapDiag(a.per_repo||[]);loadMindmap();}
});}
function renderMindmapDiag(perRepo){
  if(!perRepo.length){$("#mm-diag").innerHTML="";return;}
  $("#mm-diag").innerHTML=`<div class="card mindmap-diagnostics"><details><summary>Indexed code by repository</summary>
    <div class="sub" style="margin-top:8px">Production files indexed from each repo's selected branch (test/spec files excluded). If a file you expected is missing here, it's not on that branch — pick the right branch and re-run.</div>`+
    perRepo.map(r=>r.error?`<div class="stepitem"><b>${esc(r.repo)}</b> <span class="badge mm-uncovered">fetch error</span><div class="err">${esc(r.error)}</div></div>`
      :r.reused?`<div class="stepitem"><b>${esc(r.repo)}</b> <span class="pill">${esc(r.branch||"default")}</span> <span class="badge mm-covered">index reused (unchanged)</span> <span class="muted">${r.impl_files} impl files</span></div>`
      :`<div class="stepitem"><b>${esc(r.repo)}</b> <span class="pill">${esc(r.branch||"default")}</span>
         <span class="muted">${r.files_in_repo} files in repo · <b style="color:var(--text)">${r.impl_files} impl indexed</b> · ${r.test_files} tests excluded</span>
         ${(r.extensions||[]).length?`<div class="muted" style="margin-top:3px">extensions: ${r.extensions.map(e=>`<code>${esc(e[0])}×${e[1]}</code>`).join(" ")}</div>`:""}
         ${(r.impl_sample||[]).length?`<div class="muted" style="margin-top:3px">indexed files: ${r.impl_sample.map(s=>`<code>${esc(s)}</code>`).join(" ")}</div>`
            :(r.sample||[]).length?`<div class="muted" style="margin-top:3px">sample paths: ${r.sample.slice(0,8).map(s=>`<code>${esc(s)}</code>`).join(" ")}</div>`:""}</div>`).join("")+`</details></div>`;
}
async function loadMindmap(){const pid=$("#mm-proj").value||currentProject;
  // Guard: if we're called with no project (selector cleared while an Analyze
  // job was in flight, or nav returned before a project is picked), CLEAR the
  // loader first — otherwise the "Downloading repository code…" loader set by
  // the Analyze click stays on screen forever.
  const mmEl=$("#mm-map");
  if(!pid){if(mmEl)mmEl.innerHTML=`<div class="card"><span class="muted">Pick a project to see its coverage map.</span></div>`;return;}
  skIn("#mm-map",skeleton.rows(5,"Loading coverage map"));
  try{const r=await api(`/api/projects/${pid}/mindmap`);
    if(!r.features.length){$("#mm-map").innerHTML=`<div class="card"><span class="muted">No features in this project yet.</span></div>`;return;}
    const tot={covered:0,partial:0,uncovered:0};r.features.forEach(f=>{tot.covered+=f.counts.covered;tot.partial+=f.counts.partial;tot.uncovered+=f.counts.uncovered;});
    const grand=tot.covered+tot.partial+tot.uncovered;
    const head=`<div class="mindmap-summary-card"><div class="mindmap-summary-head"><h2>Project coverage map</h2>
      <div class="mindmap-chip-row">${mmChip("covered",tot.covered)} ${mmChip("partial",tot.partial)} ${mmChip("uncovered",tot.uncovered)}</div></div>
      ${grand?mmBar(tot,grand):`<div class="sub">Not analyzed yet — click <b>Analyze codebase</b> to read the code and map coverage.</div>`}</div>`;
    const cards=r.features.map(f=>{const c=f.counts;const t=c.covered+c.partial+c.uncovered;
      const cases=(f.cases||[]).slice().sort((x,y)=>mmRank(x.status)-mmRank(y.status)).map(cs=>
        `<div class="mindmap-case-item"><div class="mindmap-case-title">
          <span class="mm-case-left"><span class="mm-dot ${cs.status}"></span>${cs.display_id?`<code style="font-size:10px;background:rgba(255,255,255,.06);padding:1px 6px;border-radius:4px;color:#94a3b8">${esc(cs.display_id)}</code>`:""}<b>${esc(cs.title)}</b></span>
          <span class="mm-case-right"><span class="badge ${cs.type}">${esc(typeLabel(cs.type))}</span><span class="badge mm-${cs.status}">${cs.status}</span></span>
          </div><div class="mindmap-case-body">${esc(cs.rationale||"")}${(cs.files||[]).length?`<br><span style="color:var(--accent2)">Files reviewed:</span> ${cs.files.map(ff=>`<code>${esc(ff)}</code>`).join(" ")}`:""}</div></div>`).join("");
      const open=(c.uncovered>0||c.partial>0)?" open":"";
      return `<details class="mindmap-feature-card"${open}><summary>
        <div class="mindmap-summary-main"><div class="mindmap-feature-title"><strong>${esc(f.feature)}</strong> <span class="pill">v${f.version}</span> ${f.analyzed?"":'<span class="badge">not analyzed</span>'}</div>
        ${f.repos&&f.repos.length?`<div class="mindmap-feature-meta">Reviewed against ${f.repos.map(rp=>`<span class="pill">${esc(rp)}</span>`).join(" ")}</div>`:""}</div>
        <div class="mindmap-chip-row">${mmChip("covered",c.covered)} ${mmChip("partial",c.partial)} ${mmChip("uncovered",c.uncovered)}</div></summary>
        <div class="mindmap-feature-body">
        ${t?mmBar(c,t):`<div class="muted" style="margin:6px 0">${f.case_count||0} test cases — run analysis to map them to code.</div>`}
        ${(f.reviewed_files||[]).length?`<details style="margin:6px 0 8px"><summary class="muted" style="cursor:pointer;font-size:11.5px">Files reviewed for this feature (${f.reviewed_files.length})</summary><div class="muted" style="margin-top:4px">${f.reviewed_files.map(ff=>`<code>${esc(ff)}</code>`).join(" ")}</div></details>`:""}
        <div class="mindmap-case-list">${cases}</div></div></details>`;}).join("");
    $("#mm-map").innerHTML=head+cards;
  }catch(e){$("#mm-map").innerHTML=`<div class="card err">Couldn't load the coverage map. ${esc(e.message)}</div>`;}}
const mmRank=s=>({covered:0,partial:1,uncovered:2}[s]??3);
const mmChip=(s,n)=>`<span class="badge mm-${s}">${n} ${s}</span>`;
function mmBar(c,t){const p=k=>Math.round((c[k]||0)/t*100);
  return `<div class="mm-bar" title="${c.covered} covered · ${c.partial} partial · ${c.uncovered} uncovered">
    <span class="mm-seg covered" style="width:${p("covered")}%"></span><span class="mm-seg partial" style="width:${p("partial")}%"></span><span class="mm-seg uncovered" style="width:${p("uncovered")}%"></span></div>`;}

window.syncJira=async fid=>{try{const r=await api(`/api/features/${fid}/jira-sync`,{method:"POST"});toast("Posted coverage to Jira "+r.issue);}catch(e){toast(e.message,true);}};

// ---- Start Developing ----
async function initDevelop(){
  if(!$("#dev-proj")) return;
  await loadProjects();
  await loadDevFR();
}
if ($("#dev-proj")) {
  $("#dev-proj").onchange=()=>{currentProject=$("#dev-proj").value;loadDevFR();};
}
async function loadDevFR(){
  if(!$("#dev-proj")) return;
  const pid=$("#dev-proj").value||currentProject;if(!pid)return;
  try{const f=await api("/api/features?project_id="+pid);$("#dev-feat").innerHTML=f.features.map(x=>`<option value="${x.id}">${esc(x.name)} (v${x.version||1})</option>`).join("")||`<option value="">no features</option>`;}catch(e){}
  try{const r=await api(`/api/projects/${pid}/repos?repo_type=app`);$("#dev-repo").innerHTML=r.repos.map(x=>`<option value="${x.id}">${esc(x.full_name)}</option>`).join("")||`<option value="">no implementation repos</option>`;}catch(e){}}
if ($("#dev-go")) {
  $("#dev-go").onclick=async()=>{const fid=$("#dev-feat").value,rid=$("#dev-repo").value;if(!fid||!rid){toast("Pick a feature and a repo",true);return;}
    $("#dev-go").disabled=true;$("#dev-out").innerHTML="";$("#dev-status").textContent="starting…";
    try{const r=await api("/api/develop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({feature_id:fid,repo_id:rid,base_branch:$("#dev-base").value.trim()||"main",language:$("#dev-lang").value})});
      $("#dev-status").innerHTML="Running in the background — track it in <b>Jobs</b>, or watch here:";watchDev(r.job_id);}
    catch(e){$("#dev-status").innerHTML=`<span class="err">${esc(e.message)}</span>`;$("#dev-go").disabled=false;}};
}
function watchDev(jobId){if(!jobId){if($("#dev-go")) $("#dev-go").disabled=false;return;}watchJob(jobId,j=>{const d=j.result||{};
  if($("#dev-status")) $("#dev-status").textContent=j.status==="running"?`${esc(j.stage)}…`:(j.status==="failed"?"":"Done");
  if(j.status==="running") return;
  if($("#dev-go")) $("#dev-go").disabled=false;
  if(j.status==="failed"){if($("#dev-out")) $("#dev-out").innerHTML=`<div class="err">failed: ${esc(j.error||"")}</div>`;return;}
  if($("#dev-out")) $("#dev-out").innerHTML=`<div class="explain" style="margin-top:10px">Opened <a href="${esc(d.pr_url)}" target="_blank" rel="noopener noreferrer">PR #${d.pr_number}</a> on branch <code>${esc(d.branch)}</code> — ${d.file_count} implementation file(s) built to satisfy ${d.cases} test cases.<br>${(d.files||[]).map(f=>`<code>${esc(f)}</code>`).join(" · ")}<br><button class="go" style="margin-top:8px" onclick="analyzeDevPR('${d.repo_id}',${d.pr_number})">Analyze this PR for coverage</button></div>`;
});}
window.analyzeDevPR=async (rid,num)=>{
  if (currentFeature) {
    await openFeature(currentFeature);
    navigateTo("gap");
  } else {
    navigateTo("features");
  }
};

// ---- regenerate feature ----
$("#d-regen").onclick=async()=>{if(!currentFeature)return;
  const btn=$("#d-regen");btn.disabled=true;btn.textContent="↻ starting…";
  try{const r=await api(`/api/features/${currentFeature}/regenerate`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
    toast("Regeneration started — live progress is shown below");watchFeatureGen(r.job_id,currentFeature);}
  catch(e){toast(e.message,true);}
  finally{btn.disabled=false;btn.textContent="↻ regenerate";}};

// ---- Jobs screen ----
let jobsTimer=null;
function initJobs(){
  if(!document.getElementById("view-jobs")) return;
  loadJobsList();clearInterval(jobsTimer);jobsTimer=setInterval(()=>{if(document.getElementById("view-jobs") && !document.getElementById("view-jobs").hidden)loadJobsList();else clearInterval(jobsTimer);},3000);
}
if($("#jobs-refresh")) $("#jobs-refresh").onclick=loadJobsList;
async function loadJobsList(){
  if(!$("#jobs-list")) return;
  try{const r=await api("/api/jobs?limit=80");
    const badge=s=>({running:'<span class="badge" style="color:var(--accent2)">running</span>',succeeded:'<span class="badge new">succeeded</span>',failed:'<span class="badge" style="color:var(--red)">failed</span>'}[s]||`<span class="badge">${esc(s)}</span>`);
    $("#jobs-list").innerHTML=r.jobs.length?`<table><tr><th>Type</th><th>Label</th><th>Status</th><th>Stage / error</th><th>When</th><th></th></tr>`+
      r.jobs.map(j=>`<tr><td><span class="badge">${esc(j.type)}</span></td><td>${esc(j.label||"")}</td><td>${badge(j.status)}</td>
        <td class="muted">${esc(j.status==="failed"?(j.error||""):(j.stage||""))}</td>
        <td class="muted">${j.created_at?new Date(j.created_at*1000).toLocaleString():""}</td>
        <td>${j.status!=="running"?`<button class="ghost" onclick="retryJob('${j.id}')">retry</button>`:""}</td></tr>`).join("")+`</table>`
      :`<span class="muted">no jobs yet</span>`;
  }catch(e){$("#jobs-list").innerHTML=`<div class="err">${esc(e.message)}</div>`;}}
window.retryJob=async id=>{try{await api(`/api/jobs/${id}/retry`,{method:"POST"});toast("Retry started");loadJobsList();}catch(e){toast(e.message,true);}};

// ---- auth / login ----
async function showLogin(){ME=null;$("#login").hidden=false;$("#usermenu").hidden=true;
  $("#login-err").textContent="";$("#login-msg").textContent="";
  clearLoginCode();
  try {
    const status = await api("/api/auth/smtp-status");
    if (status && status.smtp_setup) {
      $("#login-intro").textContent = "Sign in with a one-time code sent to your email. No password needed.";
      $("#login-step1").hidden = false;
      $("#login-step2").hidden = true;
      $("#login-password").hidden = true;
      setTimeout(() => $("#login-email")?.focus(), 50);
    } else {
      $("#login-intro").textContent = "Sign in with your admin credentials. (SMTP is not configured)";
      $("#login-step1").hidden = true;
      $("#login-step2").hidden = true;
      $("#login-password").hidden = false;
      setTimeout(() => $("#login-username")?.focus(), 50);
    }
  } catch (e) {
    $("#login-intro").textContent = "Sign in with a one-time code sent to your email. No password needed.";
    $("#login-step1").hidden = false;
    $("#login-step2").hidden = true;
    $("#login-password").hidden = true;
    setTimeout(() => $("#login-email")?.focus(), 50);
  }
}
function applyRole(){const role=(ME&&ME.role)||"viewer";
  $("#usermenu").hidden=false;$("#user-email").textContent=ME.email;
  const rb=$("#user-role");rb.textContent=role;rb.className="rolebadge "+role;
  document.body.classList.toggle("role-viewer",role==="viewer");
  document.body.classList.toggle("role-editor",role==="editor");
  const admin=role==="admin";
  document.querySelectorAll('nav button[data-admin]').forEach(b=>b.hidden=!admin);
  const rob=$("#ro-banner");if(rob)rob.hidden=(role!=="viewer");
  applyRoleTooltips(role);
  // "Change password" only makes sense for the local admin account (email===
  // "admin"). Email-based accounts sign in with a one-time code and have no
  // password at all.
  const pwBtn=$("#change-pw-btn");if(pwBtn)pwBtn.hidden=!(ME&&ME.email==="admin");
}

// ---- change password (local admin account only) ----
// Reused for both the voluntary "Change password" profile-menu action and the
// mandatory first-login prompt. In mandatory mode the Cancel/close controls are
// hidden and the returned promise only resolves once a new password is saved —
// there is no way to click past it, matching the shipped default being a known,
// public credential (admin123) that shouldn't stay active silently.
function openChangePasswordModal(mandatory){
  return new Promise(resolve=>{
    const m=$("#pwd-modal");
    $("#pwd-current").value="";$("#pwd-new").value="";$("#pwd-confirm").value="";$("#pwd-err").textContent="";
    $("#pwd-title").textContent=mandatory?"Set a new password":"Change password";
    $("#pwd-intro").textContent=mandatory
      ?"You're signed in with the default admin123 password. For security, set a new one before continuing."
      :"Update the local admin password.";
    $("#pwd-x").style.display=mandatory?"none":"";
    $("#pwd-cancel").style.display=mandatory?"none":"";
    m.classList.add("show");
    setTimeout(()=>$("#pwd-current")?.focus(),50);
    const cleanup=()=>{$("#pwd-save").onclick=null;$("#pwd-cancel").onclick=null;$("#pwd-x").onclick=null;
      $("#pwd-current").onkeydown=$("#pwd-new").onkeydown=$("#pwd-confirm").onkeydown=null;};
    const done=(ok)=>{m.classList.remove("show");cleanup();resolve(ok);};
    $("#pwd-cancel").onclick=()=>{if(!mandatory)done(false);};
    $("#pwd-x").onclick=()=>{if(!mandatory)done(false);};
    const save=async()=>{
      const current=$("#pwd-current").value,next=$("#pwd-new").value,confirm=$("#pwd-confirm").value;
      $("#pwd-err").textContent="";
      if(!current){$("#pwd-err").textContent="Enter your current password.";return;}
      if(!next){$("#pwd-err").textContent="Enter a new password.";return;}
      if(next!==confirm){$("#pwd-err").textContent="New passwords don't match.";return;}
      $("#pwd-save").disabled=true;setBusy("#pwd-save",true);
      try{
        const r=await api("/api/auth/change-password",{method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({current_password:current,new_password:next})});
        if(r&&r.user)ME=r.user;
        toast("Password changed.");
        done(true);
      }catch(e){$("#pwd-err").textContent=e.message;}
      finally{$("#pwd-save").disabled=false;setBusy("#pwd-save",false);}
    };
    $("#pwd-save").onclick=save;
    $("#pwd-current").onkeydown=$("#pwd-new").onkeydown=$("#pwd-confirm").onkeydown=e=>{if(e.key==="Enter")save();};
  });
}
if($("#change-pw-btn"))$("#change-pw-btn").onclick=()=>openChangePasswordModal(false);
// Auto read-only enforcement for viewers: many write buttons aren't tagged
// .needs-editor, so we identify them by their label/action and disable+dim+tooltip
// them, instead of letting a viewer click and hit a 403. Idempotent; safe to call
// after every view render and after async loaders inject more buttons.
const _VIEWER_WRITE_RE=/\b(create|add|new|save|delete|remove|edit|generate|regenerate|import|invite|run|start|associate|assign|reassign|sync|rescan|watch|apply|submit|upload|clear|reset|link|unlink|promote|export)\b/i;
const _VIEWER_SKIP_RE=/\b(cancel|close|back|search|filter|view|open|download|refresh|copy|sign out|logout|use a different|expand|collapse|show|hide|next|prev|previous)\b/i;
function enforceViewerReadOnly(){
  const isViewer=(ME&&ME.role)==="viewer";
  const scope=document.querySelector(".view:not([hidden])")||document;
  scope.querySelectorAll("button").forEach(b=>{
    const label=(b.textContent||b.getAttribute("aria-label")||b.title||"").trim();
    if(!label)return;
    const looksWrite=_VIEWER_WRITE_RE.test(label)&&!_VIEWER_SKIP_RE.test(label);
    if(!looksWrite)return;
    b.classList.add("needs-editor");   // reuse the dim/disable CSS + tooltip logic
  });
  applyRoleTooltips(isViewer?"viewer":(ME&&ME.role)||"viewer");
}
// Explain WHY a control is disabled, on hover, for restricted roles.
function applyRoleTooltips(role){
  const msg = role==="viewer"
    ? "Read-only — your Viewer role can't make changes. Ask an admin for Editor access."
    : "";
  document.querySelectorAll(".needs-editor").forEach(el=>{
    if(role==="viewer"){ if(!el.dataset._t){el.dataset._t=el.getAttribute("title")||"";} el.setAttribute("title",msg);}
    else if(el.dataset._t!==undefined){ if(el.dataset._t)el.setAttribute("title",el.dataset._t); else el.removeAttribute("title"); }
  });
}
async function checkAuth(){try{const r=await api("/api/auth/me");ME=r.user;$("#login").hidden=true;applyRole();return true;}
  catch(e){showLogin();return false;}}

// ---- invite banner (pending invite shown after login) ----
function fmtDate(ts){try{return ts?new Date(ts*1000).toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"}):"";}catch(e){return "";}}
// Returns true if a pending invite is being shown (caller should NOT start the app yet).
async function maybeShowInvite(){
  try{
    const r=await api("/api/auth/my-invite");
    const inv=r&&r.invite;
    if(!inv||!inv.pending){$("#invite-gate").hidden=true;return false;}
    // Populate the banner.
    $("#invite-workspace").textContent=inv.workspace||"WardenIQ";
    const by=inv.invited_by;
    const byLabel=by?(by.name?`${esc(by.name)} (${esc(by.email)})`:esc(by.email)):"an administrator";
    const rows=[
      ["Invited by", byLabel],
      ["Workspace", esc(inv.workspace||"WardenIQ")],
      ["Role granted", `<span class="rolebadge ${esc(inv.role)}">${esc(inv.role)}</span>`],
      ["Sent", esc(fmtDate(inv.invited_at))||"—"],
    ];
    const roleDesc=(window.RBAC&&RBAC.DESC[inv.role])||"";
    $("#invite-meta").innerHTML=rows.map(([k,v])=>`<div class="row"><span>${k}</span><span>${v}</span></div>`).join("")
      +(roleDesc?`<div class="row-desc">${esc(roleDesc)}</div>`:"");
    $("#invite-err").textContent="";
    $("#invite-gate").hidden=false;
    return true;
  }catch(e){$("#invite-gate").hidden=true;return false;}
}
$("#invite-accept").onclick=async()=>{
  $("#invite-accept").disabled=true;$("#invite-err").textContent="";
  try{const r=await api("/api/auth/invite/accept",{method:"POST"});
    if(r&&r.user)ME=r.user;
    $("#invite-gate").hidden=true;applyRole();toast("Invitation accepted — welcome!");startApp();
  }catch(e){$("#invite-err").textContent=e.message;}finally{$("#invite-accept").disabled=false;}
};
$("#invite-decline").onclick=async()=>{
  if(!await uiConfirm("Decline this invitation? You'll be signed out and won't have access.","Decline invitation","Decline",true))return;
  $("#invite-decline").disabled=true;$("#invite-err").textContent="";
  try{await api("/api/auth/invite/decline",{method:"POST"});
    $("#invite-gate").hidden=true;ME=null;showLogin();toast("Invitation declined.");
  }catch(e){$("#invite-err").textContent=e.message;}finally{$("#invite-decline").disabled=false;}
};
// Re-fetch identity so a role change / disable made by an admin takes effect live
// without a manual refresh. Called on window focus and on a light poll.
let _refreshingMe=false;
async function refreshMe(){
  if(_refreshingMe||!ME)return;               // only while signed in
  _refreshingMe=true;
  try{
    const r=await fetch("/api/auth/me");
    if(r.status===401){                        // session invalidated (role change / disabled)
      ME=null;showLogin();
      if(typeof toast==="function")toast("Your access changed — please sign in again.",true);
      return;
    }
    if(!r.ok)return;
    const j=await r.json();const prevRole=ME&&ME.role;
    ME=j.user;
    if(ME&&ME.role!==prevRole){
      applyRole();
      if(typeof toast==="function")toast(`Your role is now "${ME.role}".`);
      // If the current view is no longer permitted for the new role, fall back home.
      const adminOnly=["users","config"];
      if(ME.role!=="admin"&&adminOnly.includes(currentViewName)){
        try{navigateTo("dashboard");}catch(e){}
      }else{
        try{navigateTo(currentViewName);}catch(e){}   // re-render with new permissions
      }
    }
  }catch(e){/* transient network — ignore */}
  finally{_refreshingMe=false;}
}
window.addEventListener("focus",()=>{try{refreshMe();}catch(e){}});
$("#login-send").onclick=async()=>{const email=$("#login-email").value.trim();if(!email){$("#login-err").textContent="Enter your email";return;}
  $("#login-send").disabled=true;setBusy("#login-send",true);$("#login-err").textContent="";$("#login-msg").textContent="Sending your sign-in code…";
  try{const r=await api("/api/auth/request-otp",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});
    $("#login-step1").hidden=true;$("#login-step2").hidden=false;$("#login-to").textContent=email;
    if(r&&r.delivery==="log"){
      $("#login-sent-text").textContent="Email isn't set up (demo mode) — your one-time code for ";
      // Show the code inline so contributors/evaluators can sign in without SMTP.
      // The same code is also printed to the server log (docker logs wardeniq).
      const code=r.dev_code?String(r.dev_code):"";
      if(code){
        $("#login-msg").innerHTML="Demo sign-in code: <b style=\"font-size:16px;letter-spacing:.3em;font-family:ui-monospace,monospace\">"+esc(code)+"</b><br><span style=\"opacity:.75\">Configure SMTP under Configuration → Email to stop showing codes in the UI.</span>";
      }else{
        $("#login-msg").textContent="Check the server log (e.g. docker logs wardeniq) for the code, then set up email under Configuration → Email.";
      }
    }else{
      $("#login-sent-text").textContent="We emailed a 6-digit code to ";
      $("#login-msg").textContent="Code sent — check your email.";
    }
    clearLoginCode();setTimeout(focusLoginCode,50);
  }catch(e){$("#login-err").textContent=e.message;}finally{$("#login-send").disabled=false;setBusy("#login-send",false);}};
$("#login-verify").onclick=async()=>{const email=$("#login-to").textContent,code=getLoginCode();
  if(!code){$("#login-err").textContent="Enter the code";return;}
  $("#login-verify").disabled=true;setBusy("#login-verify",true);$("#login-err").textContent="";
  try{const r=await api("/api/auth/verify-otp",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,code})});
    ME=r.user;$("#login").hidden=true;applyRole();
    try{sessionStorage.removeItem("wq_invite_token");}catch(e){}
    if(await maybeShowInvite())return;   // gate on a pending invite before entering
    startApp();
  }catch(e){$("#login-err").textContent=e.message;}finally{$("#login-verify").disabled=false;setBusy("#login-verify",false);}};
$("#login-email").onkeydown=e=>{if(e.key==="Enter")$("#login-send").click();};
$("#login-back").onclick=()=>{$("#login-step1").hidden=false;$("#login-step2").hidden=true;$("#login-err").textContent="";$("#login-msg").textContent="";clearLoginCode();};
$("#login-signin").onclick=async()=>{
  const username=$("#login-username").value.trim();
  const password=$("#login-pw").value;
  if(!username){$("#login-err").textContent="Enter your username";return;}
  if(!password){$("#login-err").textContent="Enter your password";return;}
  $("#login-signin").disabled=true;setBusy("#login-signin",true);$("#login-err").textContent="";
  try{
    const r=await api("/api/auth/login-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username,password})});
    ME=r.user;$("#login").hidden=true;applyRole();
    try{sessionStorage.removeItem("wq_invite_token");}catch(e){}
    if(await maybeShowInvite())return;
    startApp();
  }catch(e){$("#login-err").textContent=e.message;}finally{$("#login-signin").disabled=false;setBusy("#login-signin",false);}};
$("#login-username").onkeydown=e=>{if(e.key==="Enter")$("#login-pw").focus();};
$("#login-pw").onkeydown=e=>{if(e.key==="Enter")$("#login-signin").click();};
// ---- 6-box OTP entry: digits only, auto-advance, backspace, paste (spaces/letters stripped) ----
function loginCodeBoxes(){return Array.from(document.querySelectorAll("#login-code .otp-box"));}
function getLoginCode(){return loginCodeBoxes().map(b=>b.value).join("").replace(/\D/g,"");}
function clearLoginCode(){loginCodeBoxes().forEach(b=>{b.value="";});}
function focusLoginCode(){const b=loginCodeBoxes();(b.find(x=>!x.value)||b[0])?.focus();}
(function wireLoginOtp(){
  const boxes=loginCodeBoxes();
  boxes.forEach((box,i)=>{
    box.addEventListener("input",()=>{
      box.value=box.value.replace(/\D/g,"").slice(0,1);          // digits only
      if(box.value&&i<boxes.length-1)boxes[i+1].focus();          // auto-advance
    });
    box.addEventListener("keydown",e=>{
      if(e.key==="Enter"){$("#login-verify").click();}
      else if(e.key==="Backspace"&&!box.value&&i>0){boxes[i-1].value="";boxes[i-1].focus();e.preventDefault();}
      else if(e.key==="ArrowLeft"&&i>0){boxes[i-1].focus();e.preventDefault();}
      else if(e.key==="ArrowRight"&&i<boxes.length-1){boxes[i+1].focus();e.preventDefault();}
    });
    box.addEventListener("paste",e=>{                             // paste a whole code
      e.preventDefault();
      const digits=(((e.clipboardData||window.clipboardData).getData("text"))||"").replace(/\D/g,"").slice(0,boxes.length);
      if(!digits)return;
      digits.split("").forEach((d,k)=>{if(boxes[k])boxes[k].value=d;});
      (boxes[Math.min(digits.length,boxes.length-1)]||box).focus();
      if(digits.length>=boxes.length)$("#login-verify").click();
    });
  });
})();
$("#logout-btn").onclick=async()=>{try{await api("/api/auth/logout",{method:"POST"});}catch(e){}showLogin();};

// ---- users (admin) ----
function accessCell(u){
  if(u.role==="admin")return '<span class="access-cell">All projects <span class="muted">(admin)</span></span>';
  if(u.all_projects)return '<span class="access-cell">All projects</span>';
  const ids=u.project_ids||[];
  if(!ids.length)return '<span class="access-cell" style="color:var(--red)">No projects</span>';
  const names=ids.map(id=>{const p=ALL_PROJECTS_CACHE.find(x=>x.id===id);return esc(p?(p.name||p.id):id);});
  return `<span class="access-cell">${names.map(n=>`<span class="chip">${n}</span>`).join("")}</span>`;
}
function _userMatchesFilters(u){
  const q=($("#u-search")?.value||"").trim().toLowerCase();
  const st=$("#u-filter-status")?.value||"";
  const ro=$("#u-filter-role")?.value||"";
  if(q && !((u.email||"").toLowerCase().includes(q) || (u.name||"").toLowerCase().includes(q)))return false;
  if(ro && u.role!==ro)return false;
  if(st){
    const pending=u.invite_status==="pending";
    if(st==="pending" && !pending)return false;
    if(st==="active" && (pending || !u.active))return false;
    if(st==="disabled" && (pending || u.active))return false;
  }
  return true;
}
async function loadUsers(){
  skIn("#u-list",skeleton.table(7,6,"Loading users"));
  try{
  if(!ALL_PROJECTS_CACHE.length){try{const pr=await api("/api/projects");ALL_PROJECTS_CACHE=pr.projects||[];}catch(e){}}
  const r=await api("/api/users");
  window._USERS_CACHE=r.users;
  renderUsers();
}catch(e){$("#u-list").innerHTML=`<div class="err">${esc(e.message)}</div>`;}}
function renderUsers(){
  const all=window._USERS_CACHE||[];
  const rows=all.filter(_userMatchesFilters);
  const c=$("#u-count");if(c)c.textContent=`${rows.length} of ${all.length}`;
  // Counted over ALL users (not the filtered/visible rows) — this is the same
  // "how many active admins exist" question the backend guard answers, just
  // computed client-side so the UI can proactively hide/redirect instead of
  // showing a button that only fails with a raw error on click.
  const activeAdmins=all.filter(x=>x.role==="admin"&&x.active).length;
  if(!rows.length){
    $("#u-list").innerHTML=all.length
      ? '<div class="muted" style="padding:16px 0">No users match these filters.</div>'
      : '<div class="muted" style="padding:16px 0">No users yet. Invite your first teammate above.</div>';
    return;
  }
  $("#u-list").innerHTML=`<table><tr><th>Email</th><th>Name</th><th>Role</th><th>Access</th><th>Status</th><th>Last login</th><th></th></tr>`+
    rows.map(u=>{const self=ME&&ME.id===u.id;
      const pending=u.invite_status==="pending";
      const status=pending
        ?'<span class="badge" style="background:rgba(216,158,44,.18);color:#e9c46a">invite pending</span>'
        :`<span class="badge ${u.active?'new':''}">${u.active?'active':'disabled'}</span>`;
      const ICON={
        access:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z"/></svg>',
        resend:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l9 6 9-6"/><rect x="3" y="5" width="18" height="14" rx="2"/></svg>',
        cancel:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>',
        disable:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M5 5l14 14"/></svg>',
        enable:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
        lock:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
        del:'<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>'};
      const manageAccess=u.role==="admin"?'':`<button class="u-action" onclick="manageAccess('${u.id}')" title="Manage project access">${ICON.access}Access</button>`;
      // The only active admin can't disable themselves — the backend already
      // refuses this (it would lock everyone out), so don't even show a button
      // that can only ever fail. Offer the actual way out instead: add another
      // admin first.
      const isSoleAdminSelf=self&&u.role==="admin"&&u.active&&activeAdmins<=1;
      const actions=pending
        ?`${manageAccess}<button class="u-action" onclick="resendInvite('${u.id}','${esc(u.email)}')" title="Resend invite email">${ICON.resend}Resend</button>
           <button class="u-action danger" onclick="cancelInvite('${u.id}','${esc(u.email)}')" title="Cancel this invite">${ICON.cancel}Cancel</button>`
        :isSoleAdminSelf
        ?`${manageAccess}<button class="u-action" onclick="promptAdminHandoff()" title="You're the only admin — add another admin first to unlock this">${ICON.lock}Add admin to unlock</button>`
        :`${manageAccess}<button class="u-action" onclick="toggleUser('${u.id}',${u.active?'false':'true'})" title="${u.active?'Disable this user':'Enable this user'}">${u.active?ICON.disable+'Disable':ICON.enable+'Enable'}</button>
           ${self?'':`<button class="u-action danger" onclick="delUser('${u.id}','${esc(u.email)}')" title="Delete this user">${ICON.del}Delete</button>`}`;
      return `<tr><td>${esc(u.email)}${self?' <span class="muted">(you)</span>':''}</td><td>${esc(u.name||"")}</td>
        <td><select onchange="setUserRole('${u.id}',this.value)" style="width:auto">${["viewer","editor","admin"].map(x=>`<option ${x===u.role?"selected":""}>${x}</option>`).join("")}</select></td>
        <td>${accessCell(u)}</td>
        <td>${status}</td>
        <td class="muted">${u.last_login?new Date(u.last_login*1000).toLocaleString():(pending?"awaiting first sign-in":"never")}</td>
        <td><div class="u-actions">${actions}</div></td></tr>`;}).join("")+`</table>`;
}
// Guided hand-off: shown instead of "Disable" when you're the only active admin.
// Cancel = "keep using this local admin" (just closes, nothing changes). Confirm
// jumps to the existing invite form above, preset to the Admin role, so the next
// admin can be added through the normal invite flow (works with or without SMTP —
// without it, the invite still creates the account and the link can be shared
// manually; see the "Resend" flow once email is configured).
window.promptAdminHandoff=async()=>{
  const html=`<p style="margin:0 0 10px">You're the <b>only admin</b> for this workspace, so disabling your own
    access isn't allowed — that would lock everyone out.</p>
  <p class="muted" style="font-size:12.5px;margin:0">Assign another email address as admin first. Once they accept
    the invite and sign in, you'll be able to disable (or hand off) this local admin account.</p>`;
  const ok=await uiModalHTML("Add another admin first", html, "Assign an admin email");
  if(!ok)return;   // "keep using this local admin" — no change
  const roleSel=$("#u-role");
  if(roleSel){roleSel.value="admin";roleSel.dispatchEvent(new Event("change"));}
  $("#u-email")?.scrollIntoView({behavior:"smooth",block:"center"});
  setTimeout(()=>$("#u-email")?.focus(),300);
  toast("Role preset to Admin — enter their email above and click Invite.");
};
// Re-render on filter changes (client-side, no refetch).
["u-search","u-filter-status","u-filter-role"].forEach(id=>{
  const el=document.getElementById(id);
  if(el)el.addEventListener("input",()=>{try{renderUsers();}catch(e){}});
});
// Manage a user's project access via a prompt-driven modal (checkbox list).
window.manageAccess=async(id)=>{
  const u=(window._USERS_CACHE||[]).find(x=>x.id===id);if(!u)return;
  if(!ALL_PROJECTS_CACHE.length){try{const pr=await api("/api/projects");ALL_PROJECTS_CACHE=pr.projects||[];}catch(e){}}
  const cur=new Set(u.all_projects?[]:(u.project_ids||[]));
  const rows=ALL_PROJECTS_CACHE.map(p=>`<label data-name="${esc((p.name||p.id).toLowerCase())}" style="display:flex;gap:8px;align-items:center;padding:4px 0"><input type="checkbox" data-pid="${esc(p.id)}" ${cur.has(p.id)?"checked":""}/> ${esc(p.name||p.id)}</label>`).join("")||'<span class="muted">No projects exist yet.</span>';
  const html=`<div style="margin-bottom:8px"><label class="radio-inline"><input type="radio" name="ma-scope" value="all" ${u.all_projects?"checked":""}/> All projects</label>
    <label class="radio-inline" style="margin-left:16px"><input type="radio" name="ma-scope" value="some" ${u.all_projects?"":"checked"}/> Specific</label></div>
    <input id="ma-search" type="search" placeholder="Search projects…" ${u.all_projects?'hidden':''} style="width:100%;margin-bottom:8px"/>
    <div id="ma-list" ${u.all_projects?'hidden':''} style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:10px">${rows}</div>`;
  const ok=await uiModalHTML(`Project access — ${esc(u.email)}`,html,"Save access");
  if(!ok)return;
  const mode=(document.querySelector('input[name="ma-scope"]:checked')||{}).value||"all";
  const all_projects=mode==="all";
  const project_ids=all_projects?[]:[...document.querySelectorAll('#ma-list input[data-pid]:checked')].map(c=>c.getAttribute("data-pid"));
  if(!all_projects && !project_ids.length){toast("Select at least one project, or choose All projects.",true);return;}
  try{await api(`/api/users/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({all_projects,project_ids})});
    toast("Project access updated");loadUsers();
  }catch(e){toast(e.message,true);}
};
// ---- project-access picker (invite form) ----
let ALL_PROJECTS_CACHE=[];
async function loadProjectPicker(){
  try{const r=await api("/api/projects");ALL_PROJECTS_CACHE=r.projects||[];}catch(e){ALL_PROJECTS_CACHE=[];}
  const box=$("#u-proj-list");if(!box)return;
  box.innerHTML=ALL_PROJECTS_CACHE.length
    ? ALL_PROJECTS_CACHE.map(p=>`<label><input type="checkbox" value="${esc(p.id)}"/> ${esc(p.name||p.id)}</label>`).join("")
    : '<span class="empty">No projects yet — create one first, or grant access to all.</span>';
}
function inviteScope(){
  const mode=(document.querySelector('input[name="u-scope"]:checked')||{}).value||"all";
  const role=$("#u-role").value;
  if(role==="admin"||mode==="all")return {all_projects:true,project_ids:[]};
  const ids=[...document.querySelectorAll('#u-proj-list input:checked')].map(c=>c.value);
  return {all_projects:false,project_ids:ids};
}
// Toggle the checklist when the radio changes; hide it entirely for admin role.
document.addEventListener("change",e=>{
  if(e.target && (e.target.name==="u-scope" || e.target.id==="u-role")){
    const role=$("#u-role")?.value, mode=(document.querySelector('input[name="u-scope"]:checked')||{}).value||"all";
    const list=$("#u-proj-list"), acc=$("#u-proj-access");
    if(!list||!acc)return;
    const adminForcesAll=role==="admin";
    acc.querySelectorAll('input[name="u-scope"]').forEach(r=>r.disabled=adminForcesAll);
    list.hidden = adminForcesAll || mode!=="some";
    $("#u-proj-hint").textContent = adminForcesAll
      ? "Admins always have access to all projects."
      : (mode==="some"?"Select the projects this user can access.":"This user will have access to every project.");
  }
});
$("#u-invite").onclick=async()=>{const email=$("#u-email").value.trim(),name=$("#u-name").value.trim(),role=$("#u-role").value;
  if(!email){toast("Email required",true);return;}
  const scope=inviteScope();
  if(!scope.all_projects && scope.project_ids.length===0){toast("Select at least one project, or choose All projects.",true);return;}
  try{const r=await api("/api/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,name,role,...scope})});
    $("#u-email").value="";$("#u-name").value="";
    const msg=(r&&r.message)||"User created.";
    $("#u-msg").innerHTML=esc(msg);
    if(r&&(r.delivery==="refused"||r.delivery==="error"))toast(msg,true);else toast(msg);
    loadUsers();
  }catch(e){toast(e.message,true);}};
window.setUserRole=async(id,role)=>{
  const u=(window._USERS_CACHE||[]).find(x=>x.id===id);
  const who=u?(u.name||u.email):"this user";
  const desc=(window.RBAC&&RBAC.DESC[role])?` ${RBAC.DESC[role]}`:"";
  if(!await uiConfirm(`Change ${esc(who)}'s role to "${role}"?${desc} They'll be re-authenticated with the new permissions.`,"Change role","Change role")){
    loadUsers();return;   // revert the dropdown
  }
  try{await api(`/api/users/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({role})});toast(`Role changed to ${role}.`);loadUsers();}
  catch(e){toast(e.message,true);loadUsers();}};
window.toggleUser=async(id,active)=>{try{await api(`/api/users/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({active})});toast(active?"Enabled":"Disabled");loadUsers();}catch(e){toast(e.message,true);}};
window.delUser=async(id,email)=>{if(!await uiConfirm(`Delete ${email}?`, "Delete User", "Delete", true))return;try{await api(`/api/users/${id}`,{method:"DELETE"});toast("User deleted");loadUsers();}catch(e){toast(e.message,true);}};
window.resendInvite=async(id,email)=>{try{const r=await api(`/api/users/${id}/resend-invite`,{method:"POST"});
  const msg=(r&&r.message)||"Invite re-sent.";
  $("#u-msg").innerHTML=esc(msg);
  if(r&&(r.delivery==="refused"||r.delivery==="error"))toast(msg,true);else toast(msg);loadUsers();
}catch(e){toast(e.message,true);}};
window.cancelInvite=async(id,email)=>{if(!await uiConfirm(`Cancel the pending invite for ${email}?`, "Cancel Invite", "Cancel invite", true))return;
  try{await api(`/api/users/${id}/cancel-invite`,{method:"POST"});toast("Invite cancelled");loadUsers();}catch(e){toast(e.message,true);}};
async function loadAudit(){const box=$("#audit-list");if(!box)return;
  skIn("#audit-list",skeleton.table(5,6,"Loading audit log"));
  try{const r=await api("/api/audit-logs?limit=100");const logs=r.logs||[];
    if(!logs.length){box.innerHTML='<span class="muted">No audit entries yet.</span>';return;}
    const fmt=ts=>{try{return new Date(ts*1000).toLocaleString();}catch(e){return "";}};
    box.innerHTML=`<table><tr><th>When</th><th>Action</th><th>Actor</th><th>Target</th><th>Details</th></tr>`+
      logs.map(l=>{const det=l.detail||[l.old&&`from ${JSON.stringify(l.old)}`,l.new&&`to ${JSON.stringify(l.new)}`].filter(Boolean).join(" ");
        const danger=/deleted|denied|disabled/.test(l.action||"");
        return `<tr><td class="muted" style="white-space:nowrap">${fmt(l.ts)}</td>
          <td><span class="badge ${danger?'':'new'}" style="${danger?'color:var(--red)':''}">${esc(l.action||"")}</span></td>
          <td>${esc(l.actor_email||l.actor_id||"—")}</td>
          <td>${esc(l.target||"—")}</td>
          <td class="muted" style="font-size:11.5px">${esc(det||"")}</td></tr>`;}).join("")+`</table>`;
  }catch(e){box.innerHTML=`<div class="err">Couldn't load the audit log. ${esc(e.message)}</div>`;}}

// ---- MCQ Validator ----
let validatorAnswers = {};
// Load existing validator state ONLY — never triggers generation.
// Generation happens on the "Generate Validator" / "Retake Validator" buttons (runValidator).
async function initValidator() {
  if (!currentFeature) {
    $("#val-no-feature").style.display = "block";
    $("#val-workspace").style.display = "none";
    return;
  }
  $("#val-no-feature").style.display = "none";
  $("#val-workspace").style.display = "block";
  $("#val-feat-title").textContent = `${$("#d-name").textContent || "Feature"} — MCQ Validator`;
  $("#val-results").style.display = "none";
  skIn("#val-qa-container",skeleton.cards(3,"Loading validator"));
  $("#val-progress").style.display = "none";
  $("#val-log").style.display = "none";
  $("#val-generate-btn").style.display = "none";
  $("#val-retake-btn").style.display = "none";
  $("#val-status").textContent = "Loading validator...";

  try {
    const res = await api(`/api/features/${currentFeature}/validator/latest`);
    if (!res || res.mode === "none") {
      $("#val-qa-container").innerHTML = "";
      $("#val-status").textContent = "No validator generated yet.";
      $("#val-generate-btn").style.display = "inline-block";
      $("#val-generate-btn").disabled = false;
      return;
    }
    currentRunId = res.run && res.run.id;
    if (res.mode === "generating") {
      watchValidatorJob(res.run && res.run.job_id);
      return;
    }
    $("#val-qa-container").innerHTML = "";
    $("#val-status").textContent = "";
    $("#val-retake-btn").style.display = "inline-block";
    $("#val-retake-btn").disabled = false;
    if (res.mode === "score") {
      renderValidatorResults(res.score);
    } else {
      validatorAnswers = {};
      if (res.answers && res.answers.length) {
        res.answers.forEach(a => {
          validatorAnswers[a.question_id] = {
            selectedIndex: a.selected_index,
            confidence: a.confidence,
            comment: a.comment || ""
          };
        });
      }
      renderValidatorQuestions(res.questions);
    }
  } catch (e) {
    $("#val-progress").style.display = "none";
    $("#val-qa-container").innerHTML = "";
    $("#val-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
}

// Trigger validator generation (button-driven).
async function runValidator(forceNew=false) {
  if (!currentFeature) return;
  $("#val-results").style.display = "none";
  $("#val-generate-btn").style.display = "none";
  $("#val-retake-btn").disabled = true;
  skIn("#val-qa-container",skeleton.cards(3,"Generating validator questions"));
  $("#val-progress").style.display = "block";
  $("#val-bar").style.width = "40%";
  $("#val-status").textContent = "Loading validator...";

  try {
    const res = await api(`/api/features/${currentFeature}/validator`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ forceNew: forceNew })
    });
    currentRunId = res.run && res.run.id;
    if (res.mode === "generating") {
      watchValidatorJob(res.job_id || (res.run && res.run.job_id));
      return;
    }
    // An existing run was returned directly — reload the view to render it.
    initValidator();
  } catch (e) {
    $("#val-progress").style.display = "none";
    $("#val-qa-container").innerHTML = "";
    $("#val-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    $("#val-generate-btn").style.display = "inline-block";
    $("#val-generate-btn").disabled = false;
  }
}

function watchValidatorJob(jobId) {
  $("#val-progress").style.display = "block";
  $("#val-log").style.display = "block";
  $("#val-status").textContent = "Generating validator questions…";
  if (!jobId) { setTimeout(() => initValidator(), 1500); return; }
  watchJob(jobId, j => {
    $("#val-bar").style.width = (j.progress || 5) + "%"; renderJobLog("#val-log", j);
    $("#val-status").textContent = j.status === "running" ? (j.stage || "Generating…") : "";
    if (j.status === "succeeded") initValidator();
    if (j.status === "failed") {
      $("#val-progress").style.display = "none"; $("#val-log").style.display = "none";
      $("#val-qa-container").innerHTML = "";
      $("#val-status").innerHTML = `<span class="err">${esc(j.error || "Validator generation failed")}</span>`;
      $("#val-generate-btn").style.display = "inline-block";
      $("#val-generate-btn").disabled = false;
    }
  });
}

$("#val-generate-btn").onclick = () => runValidator(false);

function renderValidatorQuestions(questions) {
  let html = "";
  questions.forEach((q, idx) => {
    const qId = q.id;
    validatorAnswers[qId] = validatorAnswers[qId] || { selectedIndex: null, confidence: 3, comment: "" };
    const optionsHtml = q.options.map((opt, oIdx) => {
      return `<button class="val-opt" data-qid="${qId}" data-oidx="${oIdx}" id="opt-${qId}-${oIdx}" onclick="selectValOption('${qId}', ${oIdx})">${esc(opt)}</button>`;
    }).join("");
    
    html += `
    <div class="val-qcard" id="qcard-${qId}">
      <div class="category">${esc(q.category.replace('_', ' '))}</div>
      <div class="qtext">${idx + 1}. ${esc(q.question)}</div>
      <div class="val-opts">${optionsHtml}</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:12px;flex-wrap:wrap">
        <div class="val-conf-row" style="margin:0">
          <span style="font-size:12.5px;color:var(--muted)">Confidence:</span>
          ${[1,2,3,4,5].map(lvl => `<button class="val-conf-btn" id="conf-${qId}-${lvl}" onclick="selectValConfidence('${qId}', ${lvl})">${lvl}</button>`).join("")}
        </div>
        <div style="flex:1;min-width:180px">
          <input placeholder="Clarifying comment (optional)…" id="comment-${qId}" onchange="updateValComment('${qId}', this.value)" style="padding:6px 10px;font-size:12.5px"/>
        </div>
      </div>
    </div>`;
  });
  html += `<button class="go" id="val-submit-btn" style="width:100%;margin-top:20px" onclick="submitValidatorAnswers()">Submit Answers</button>`;
  $("#val-qa-container").innerHTML = html;
  
  questions.forEach(q => {
    const qId = q.id;
    const ans = validatorAnswers[qId];
    if (ans.selectedIndex !== null) selectValOption(qId, ans.selectedIndex);
    selectValConfidence(qId, ans.confidence);
    $(`#comment-${qId}`).value = ans.comment || "";
  });
}

window.selectValOption = (qId, oIdx) => {
  validatorAnswers[qId].selectedIndex = oIdx;
  document.querySelectorAll(`#qcard-${qId} .val-opt`).forEach(btn => {
    btn.classList.toggle("selected", parseInt(btn.dataset.oidx) === oIdx);
  });
};

window.selectValConfidence = (qId, lvl) => {
  validatorAnswers[qId].confidence = lvl;
  document.querySelectorAll(`#qcard-${qId} .val-conf-btn`).forEach(btn => {
    btn.classList.toggle("selected", parseInt(btn.textContent) === lvl);
  });
};

window.updateValComment = (qId, val) => {
  validatorAnswers[qId].comment = val;
};

window.submitValidatorAnswers = async () => {
  const qIds = Object.keys(validatorAnswers);
  const unanswered = qIds.filter(id => validatorAnswers[id].selectedIndex === null);
  if (unanswered.length > 0) {
    toast(`Please answer all questions before submitting.`, true);
    return;
  }
  const payload = qIds.map(id => ({
    questionId: id,
    selectedIndex: validatorAnswers[id].selectedIndex,
    confidence: validatorAnswers[id].confidence,
    comment: validatorAnswers[id].comment
  }));
  $("#val-submit-btn").disabled = true;
  $("#val-submit-btn").textContent = "Submitting...";
  
  try {
    const score = await api(`/api/validator/runs/${currentRunId}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers: payload })
    });
    toast("Answers submitted!");
    renderValidatorResults(score);
  } catch (e) {
    toast(e.message, true);
    $("#val-submit-btn").disabled = false;
    $("#val-submit-btn").textContent = "Submit Answers";
  }
};

function renderValidatorResults(score) {
  $("#val-qa-container").innerHTML = "";
  $("#val-results").style.display = "block";
  $("#val-score").textContent = `${score.clarityScore}%`;
  $("#val-rating").textContent = score.rating;
  $("#val-rating").className = "v " + (score.clarityScore >= 75 ? "ok" : "err");
  $("#val-weak-count").textContent = score.weakAreas.length;
  
  if (score.weakAreas.length) {
    $("#val-weak-list").innerHTML = score.weakAreas.map(w => `<span class="badge" style="color:var(--red);margin-right:6px">${esc(w.replace('_', ' '))}</span>`).join("") + `<div style="margin-top:8px;font-size:12.5px" class="err">These categories scored below 60% accuracy, indicating requirement gaps.</div>`;
  } else {
    $("#val-weak-list").innerHTML = `<span class="badge new" style="color:var(--green)">None</span> <span class="muted" style="margin-left:6px">Strong requirement clarity across all categories.</span>`;
  }
  
  const results = score.questionResults || [];
  $("#val-details-list").innerHTML = results.map((q, idx) => {
    const isCorrect = q.isCorrect;
    return `
    <div class="val-qcard" style="border-left: 4px solid ${isCorrect ? 'var(--green)' : 'var(--red)'}">
      <div class="category">${esc(q.category.replace('_', ' '))}</div>
      <div class="qtext">${idx + 1}. ${esc(q.question)}</div>
      <div style="font-size:12.5px;margin-bottom:6px">
        <b>Your Answer:</b> <span style="color:${isCorrect ? 'var(--green)' : 'var(--red)'}">${esc(q.selectedOption || "unanswered")}</span>
        ${isCorrect ? '' : `<br><b>Correct Answer:</b> <span style="color:var(--green)">${esc(q.correctOption)}</span>`}
      </div>
      ${q.comment ? `<div class="muted" style="background:var(--panel);padding:6px 10px;border-radius:6px;margin-top:6px"><b>Note:</b> ${esc(q.comment)}</div>` : ''}
    </div>`;
  }).join("");
}

$("#val-retake-btn").onclick = async () => {
  if (await uiConfirm("Are you sure you want to retake the validator? This will generate completely fresh questions.", "Retake Validator")) {
    runValidator(true);
  }
};

// ---- Gap Analysis ----
let GAP_TAB = "pr";
let GAP_AUTO_POLL = null;

async function initGap() {
  if (!currentFeature) {
    $("#gap-no-feature").style.display = "block";
    $("#gap-workspace").style.display = "none";
    return;
  }
  // Reset any run-detail panel left over from a previously-viewed feature. It is
  // otherwise only cleared by its own Close button, so without this it leaks across
  // features (e.g. a Loan_2 PR run staying visible under Catalog_2's gap view).
  $("#gap-pr-detail").style.display = "none";
  $("#gap-pr-detail-body").innerHTML = "";
  $("#gap-no-feature").style.display = "none";
  $("#gap-workspace").style.display = "block";
  $("#gap-feat-title").textContent = `${$("#d-name").textContent || "Feature"} — Gap Analysis`;
  const _gx=(id,kind,fmt)=>{const a=$(id); if(a) a.onclick=(e)=>{e.preventDefault();downloadGapExport(kind,fmt).then(()=>toast("Export ready")).catch(err=>toast(err.message||"Export failed",true));};};
  _gx("#gap-pr-export-csv","pr-coverage","csv"); _gx("#gap-pr-export-pdf","pr-coverage","pdf");
  _gx("#gap-auto-export-csv","automation","csv"); _gx("#gap-auto-export-pdf","automation","pdf");
  switchGapTab(GAP_TAB);
}

function switchGapTab(tab) {
  GAP_TAB = tab;
  // Stop any running pollers before switching so they don't leak across tabs.
  stopGapPrPoll();
  if (GAP_AUTO_POLL) { clearTimeout(GAP_AUTO_POLL); GAP_AUTO_POLL = null; }
  document.querySelectorAll("[data-gap-tab]").forEach(b => b.classList.toggle("active", b.dataset.gapTab === tab));
  $("#gap-tab-pr").style.display = tab === "pr" ? "block" : "none";
  $("#gap-tab-auto").style.display = tab === "auto" ? "block" : "none";
  if (tab === "pr") loadGapPrRuns();
  else loadGapAuto();
}

document.querySelectorAll("[data-gap-tab]").forEach(btn => {
  btn.onclick = () => switchGapTab(btn.dataset.gapTab);
});

let GAP_PR_POLL = null;
function stopGapPrPoll() { if (GAP_PR_POLL) { clearTimeout(GAP_PR_POLL); GAP_PR_POLL = null; } }

// Re-schedule the PR-runs poller. Fast cadence while a run is active (so the
// RUNNING→DONE flip shows without manual refresh); slow idle cadence so a newly
// raised PR appears on its own. Only runs while the PR tab is actually visible.
function _scheduleGapPrPoll(anyActive) {
  stopGapPrPoll();
  if (GAP_TAB !== "pr" || $("#gap-workspace").style.display === "none" || !currentFeature) return;
  GAP_PR_POLL = setTimeout(() => loadGapPrRuns({ silent: true }), anyActive ? 2000 : 4000);
}

async function loadGapPrRuns(opts) {
  const silent = !!(opts && opts.silent === true);
  if (!currentFeature) return;
  if (!silent) skIn("#gap-pr-list",skeleton.rows(4,"Loading pull request coverage runs"));
  try {
    const r = await api(`/api/features/${currentFeature}/code-coverage/runs?limit=50`);
    const runs = r.runs || [];
    const anyActive = runs.some(run => run.status === "running" || run.status === "pending");
    const live = $("#gap-pr-live");
    if (live) live.innerHTML = anyActive
      ? '<span class="badge functional">⏳ gap analysis running…</span>'
      : "";
    if (!runs.length) {
      $("#gap-pr-list").innerHTML = `<div class="muted">No PR coverage runs yet. Waiting for a PR… (updates automatically)</div>`;
      _scheduleGapPrPoll(false);
      return;
    }
    $("#gap-pr-list").innerHTML = runs.map(run => {
      const statusBadge = {
        done: '<span class="badge api">DONE</span>',
        running: '<span class="badge functional">RUNNING</span>',
        pending: '<span class="badge">PENDING</span>',
        failed: '<span class="badge nfr" style="color:var(--red)">FAILED</span>',
      }[run.status] || `<span class="badge">${esc(run.status||"")}</span>`;
      const total = run.tests_total ?? 0;
      const covered = run.tests_covered ?? 0;
      const pct = total ? Math.round(100 * covered / total) : 0;
      const ts = run.completed_at || run.created_at;
      const when = ts ? new Date(ts*1000).toLocaleString() : "";
      const prTitle = esc(run.pr_title || `PR #${run.pr_number}`);
      const rerunBadge = run.needs_rerun ? '<span class="badge nfr" style="color:var(--amber)">NEEDS RERUN</span>' : '';
      const excluded = !!run.excluded;
      const exclBadge = excluded ? '<span class="badge" style="background:#3a2a20;color:var(--amber)">EXCLUDED</span>' : '';
      const exclBtn = run.pr_id
        ? `<button class="ghost needs-editor" type="button" title="${excluded?'Count this PR in coverage again':'Ignore this PR in coverage'}" style="font-size:11px;padding:3px 9px;margin-top:5px" onclick="event.stopPropagation();togglePrExcluded('${run.pr_id}',${excluded?'false':'true'})">${excluded?'Include':'Exclude'}</button>`
        : '';
      return `<div class="repo-item-card" style="cursor:pointer${excluded?';opacity:.55':''}" onclick="openGapPrRun('${run.id}')">
        <div style="flex:1">
          <div><b>#${run.pr_number}</b> · ${prTitle} ${statusBadge} ${rerunBadge} ${exclBadge}</div>
          <div class="muted" style="font-size:11px;margin-top:3px">${esc(run.repo_full_name||"")} · branch <b>${esc(run.pr_branch||"")}</b> · ${esc(when)}</div>
        </div>
        <div style="text-align:right">
          <div><b>${covered}/${total}</b> covered</div>
          <div class="muted" style="font-size:11px">${pct}% · ${run.source||"webhook"}</div>
          ${exclBtn}
        </div>
      </div>`;
    }).join("");
    _scheduleGapPrPoll(anyActive);
  } catch (e) {
    if (!silent) $("#gap-pr-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
    _scheduleGapPrPoll(false);   // keep retrying slowly on transient errors
  }
}

window.togglePrExcluded = async (prId, excluded) => {
  if (!prId) { toast("PR id unavailable for this run", true); return; }
  try {
    await api(`/api/prs/${prId}/exclude`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ excluded })
    });
    toast(excluded ? "PR excluded from coverage" : "PR included in coverage");
    loadGapPrRuns();
    // Refresh the feature's coverage card so the % reflects the change.
    if (currentFeature && typeof loadCoverage === "function") loadCoverage(currentFeature);
  } catch (e) { toast(e.message || "Could not update PR", true); }
};

window.toggleCovMode = (btn, section, mode) => {
  const container = btn.closest('.case-group-body');
  if (!container) return;
  
  // Update buttons active style
  container.querySelectorAll('.cov-toggle-btn').forEach(b => {
    b.style.background = 'transparent';
    b.style.color = 'var(--muted)';
  });
  btn.style.background = '#35507a';
  btn.style.color = '#d5e5ff';
  
  // Show/hide lists
  const covList = container.querySelector(`.cov-list-covered-${section}`);
  const missList = container.querySelector(`.cov-list-missing-${section}`);
  const badge = container.querySelector(`.cov-status-badge`);
  
  const covCount = covList ? covList.dataset.count : 0;
  const missCount = missList ? missList.dataset.count : 0;
  
  if (mode === 'covered') {
    if (covList) covList.style.display = 'block';
    if (missList) missList.style.display = 'none';
    if (badge) {
      badge.textContent = `${covCount} covered`;
      badge.style.background = 'rgba(52,211,153,0.15)';
      badge.style.color = '#34d399';
      badge.style.borderColor = 'rgba(52,211,153,0.2)';
    }
  } else {
    if (covList) covList.style.display = 'none';
    if (missList) missList.style.display = 'block';
    if (badge) {
      badge.textContent = `${missCount} missing`;
      badge.style.background = 'rgba(244,113,113,0.15)';
      badge.style.color = '#f87171';
      badge.style.borderColor = 'rgba(244,113,113,0.2)';
    }
  }
};

window.openGapPrRun = async (rid) => {
  $("#gap-pr-detail").style.display = "block";
  $("#gap-pr-detail-body").innerHTML = skeleton.block("Loading coverage run details");
  try {
    const r = await api(`/api/code-coverage/runs/${rid}`);
    // Guard: never render a run whose feature differs from the one being viewed.
    if (r.feature_id && currentFeature && r.feature_id !== currentFeature) {
      $("#gap-pr-detail").style.display = "none";
      $("#gap-pr-detail-body").innerHTML = "";
      return;
    }
    $("#gap-pr-detail-title").textContent = `Run · PR #${r.pr_number} · ${r.repo_full_name||""}`;
    
    const result = r.result || {};
    const covered = result.covered || [];
    const cmp = result.comparison || {};
    const newlySet = new Set(cmp.newly_covered || []);
    const lostSet  = new Set(cmp.no_longer_covered || []);
    
    // Group feature test cases
    const coveredById = {};
    for (const c of covered) coveredById[c.test_case_id] = c;
    const allCases = r.feature_cases || [];
    const sections = {};
    for (const c of allCases) {
      const t = (c.type || "other").toLowerCase();
      (sections[t] = sections[t] || {covered:[], missing:[]});
      const ev = coveredById[c.id];
      if (ev) sections[t].covered.push({ ...c, rationale: ev.rationale,
                                          by_dev_test: !!ev.by_dev_test });
      else    sections[t].missing.push(c);
    }

    const TYPE_TITLES = {
      functional: "Business tests", 
      e2e: "End-to-End",
      api: "API tests", 
      ui: "UI validations", 
      nfr: "Edge cases",
      other: "Other tests"
    };
    const TYPE_ORDER = ["functional","e2e","api","ui","nfr","other"];

    const headerLinks = [];
    if (r.pr_url) headerLinks.push(`<a class="ghost" target="_blank" rel="noopener" href="${esc(r.pr_url)}">Open PR ↗</a>`);
    if (r.commit_url) headerLinks.push(`<a class="ghost" target="_blank" rel="noopener" href="${esc(r.commit_url)}">View commit ↗</a>`);
    if (r.head_sha) headerLinks.push(`<span class="muted" style="font-size:11px">SHA <code>${esc(r.head_sha.slice(0,7))}</code></span>`);
    if (r.feature_name) headerLinks.push(`<span class="muted" style="font-size:11px">Feature: <b>${esc(r.feature_name)}</b></span>`);
    headerLinks.push(`<button class="ghost" type="button" onclick="reassignGapRun('${r.id}')">Reassign feature…</button>`);
    if (r.needs_rerun) headerLinks.push('<span class="badge nfr" style="color:var(--amber)">feature edited after run — rerun recommended</span>');

    const total = allCases.length || (r.tests_total ?? 0);
    const cov = covered.filter(c => c.status === "covered" || c.status === "partial").length;
    const gaps = Math.max(0, total - cov);
    const newlyCount = cmp.newly_covered_detail ? cmp.newly_covered_detail.length : (cmp.newly_covered||[]).length;

    const legendHtml = `
      <div style="display:flex;flex-wrap:wrap;align-items:center;gap:16px;border:1px solid #0e1f35;background:#07111f;border-radius:12px;padding:12px 16px;margin-bottom:14px;font-size:12px;color:#a0aec0">
        <div style="display:flex;align-items:center;gap:6px">
          <span style="color:#34d399;font-weight:bold;font-size:14px">↑</span>
          <span><b>Upstream</b> means the testcase is newly covered in this run.</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <span style="color:#f87171;font-weight:bold;font-size:14px">↓</span>
          <span><b>Downstream</b> means the testcase was covered before and is now missing.</span>
        </div>
      </div>
    `;

    const sectionsHtml = TYPE_ORDER.filter(t => sections[t]).map(t => {
      const sec = sections[t];
      const secTotal = sec.covered.length + sec.missing.length;
      const defaultMode = sec.covered.length ? "covered" : "missing";
      const isCovActive = defaultMode === "covered";
      
      const badgeText = isCovActive ? `${sec.covered.length} covered` : `${sec.missing.length} missing`;
      const badgeBg = isCovActive ? 'rgba(52,211,153,0.15)' : 'rgba(244,113,113,0.15)';
      const badgeColor = isCovActive ? '#34d399' : '#f87171';
      const badgeBorder = isCovActive ? 'rgba(52,211,153,0.2)' : 'rgba(244,113,113,0.2)';

      const renderItem = (c, mode) => {
        let arrowHtml = "";
        if (mode === "covered" && newlySet.has(c.id)) {
          arrowHtml = `<span style="color:#34d399;font-weight:bold;font-size:14px;margin-right:2px" title="Newly covered in this run">↑</span>`;
        } else if (mode === "missing" && lostSet.has(c.id)) {
          arrowHtml = `<span style="color:#f87171;font-weight:bold;font-size:14px;margin-right:2px" title="No longer covered in this run">↓</span>`;
        }
        
        const displayCodeHtml = c.display_id 
          ? `<code style="font-family:monospace;font-size:10px;background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px;color:#94a3b8">${esc(c.display_id)}</code>` 
          : "";
          
        const prioBadgeHtml = prioBadge(c.priority);
        
        let commitBadgeHtml = "";
        if (r.head_sha) {
          const shortSha = r.head_sha.slice(0, 7);
          if (r.commit_url) {
            commitBadgeHtml = `<a href="${esc(r.commit_url)}" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:3px;font-family:monospace;font-size:10px;background:rgba(59,130,246,0.1);color:#60a5fa;border:1px solid rgba(59,130,246,0.2);padding:2px 6px;border-radius:4px;text-decoration:none">${esc(shortSha)} ↗</a>`;
          } else {
            commitBadgeHtml = `<span style="font-family:monospace;font-size:10px;background:rgba(255,255,255,0.06);color:#94a3b8;padding:2px 6px;border-radius:4px">${esc(shortSha)}</span>`;
          }
        }
        
        const featureBadgeHtml = r.feature_name 
          ? `<span style="font-size:10.5px;background:rgba(51, 65, 85, 0.4);color:#94a3b8;padding:2px 8px;border-radius:4px">${esc(r.feature_name)}</span>` 
          : "";
          
        return `
          <div style="border:1px solid #1E2A40;background:#0D1728;border-radius:10px;padding:12px 14px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px">
              <div style="display:flex;align-items:center;gap:6px">
                ${arrowHtml}
                ${displayCodeHtml}
              </div>
              ${prioBadgeHtml}
            </div>
            <div style="font-size:13.5px;font-weight:500;color:#e2e8f0;line-height:1.4;margin-bottom:8px">${esc(c.title)}</div>
            ${stepsHtml(c.steps)}
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              ${commitBadgeHtml}
              ${featureBadgeHtml}
            </div>
          </div>
        `;
      };

      return `<details class="case-group gap-section" ${sec.covered.length>0?"open":""}>
        <summary style="color:var(--text);font-size:13px;text-transform:none;letter-spacing:normal;font-weight:600">
          <div style="display:flex;align-items:center;gap:8px">
            <span>${esc(TYPE_TITLES[t]||t.toUpperCase())}</span>
            <span class="badge" style="border-radius:999px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--muted);padding:2px 7px;font-size:10px">${sec.covered.length} covered · ${sec.missing.length} missing</span>
          </div>
        </summary>
        <div class="case-group-body" style="padding:10px 14px 14px">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px">
            <div class="inline-flex" style="display:inline-flex;background:#0d1728;border:1px solid #28405f;border-radius:999px;padding:2px">
              <button type="button" class="cov-toggle-btn" onclick="toggleCovMode(this, '${t}', 'covered')" style="background:${isCovActive ? '#35507a' : 'transparent'};color:${isCovActive ? '#d5e5ff' : 'var(--muted)'};border:none;border-radius:999px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;transition:all 0.15s">Covered</button>
              <button type="button" class="cov-toggle-btn" onclick="toggleCovMode(this, '${t}', 'missing')" style="background:${!isCovActive ? '#35507a' : 'transparent'};color:${!isCovActive ? '#d5e5ff' : 'var(--muted)'};border:none;border-radius:999px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;transition:all 0.15s">Missing</button>
            </div>
            <span class="cov-status-badge" style="font-size:11px;font-weight:600;padding:3px 10px;border-radius:999px;background:${badgeBg};color:${badgeColor};border:1px solid ${badgeBorder};transition:all 0.15s">
              ${badgeText}
            </span>
          </div>
          
          <div class="cov-list-covered-${t}" data-count="${sec.covered.length}" style="display:${isCovActive ? 'block' : 'none'}">
            ${sec.covered.length ? sec.covered.map(c => renderItem(c, "covered")).join("") : `<div class="muted" style="padding:8px 4px">No covered test cases.</div>`}
          </div>
          
          <div class="cov-list-missing-${t}" data-count="${sec.missing.length}" style="display:${!isCovActive ? 'block' : 'none'}">
            ${sec.missing.length ? sec.missing.map(c => renderItem(c, "missing")).join("") : `<div class="muted" style="padding:8px 4px">No missing test cases.</div>`}
          </div>
        </div>
      </details>`;
    }).join("");

    $("#gap-pr-detail-body").innerHTML = `
      <div class="sub" style="margin:8px 0">${esc(r.pr_title||"")} · branch <b>${esc(r.pr_branch||"")}</b></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center">${headerLinks.join("")}</div>
      <div style="display:flex;gap:0;padding:14px 18px;background:var(--panel2);border:1px solid var(--line);border-radius:9px;margin-bottom:14px">
        <div style="flex:1;min-width:140px"><div style="font-size:18px;font-weight:700;line-height:1">${cov} / ${total}</div><div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px">Tests covered</div></div>
        <div style="flex:1;min-width:140px;border-left:1px solid var(--line);padding-left:18px"><div style="font-size:18px;font-weight:700;line-height:1">${newlyCount}</div><div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px">New tests found</div></div>
        <div style="flex:1;min-width:140px;border-left:1px solid var(--line);padding-left:18px"><div style="font-size:18px;font-weight:700;line-height:1">${gaps}</div><div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:5px">Gaps</div></div>
      </div>
      ${legendHtml}
      ${sectionsHtml || '<div class="muted">No test cases on this feature yet.</div>'}
    `;
  } catch (e) {
    $("#gap-pr-detail-body").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
};

if($("#gap-pr-detail-close")) $("#gap-pr-detail-close").onclick = () => {
  $("#gap-pr-detail").style.display = "none";
};

window.reassignGapRun = async (runId) => {
  if(!currentProject) return;
  try{
    const r = await api(`/api/features?project_id=${currentProject}`);
    const features = (r.features || []);
    if(!features.length){ toast("No features in this project", true); return; }
    const labels = features.map((f, i) => `${i+1}. ${f.name}${f.version?" (v"+f.version+")":""}`).join("\n");
    const choice = await uiPrompt("Reassign feature",
      `Pick a feature for this run by number:\n${labels}`, "1");
    const idx = parseInt(choice || "0", 10) - 1;
    if(isNaN(idx) || idx < 0 || idx >= features.length){ toast("Invalid pick", true); return; }
    const fid = features[idx].id;
    await api(`/api/code-coverage/runs/${runId}/reassign`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({feature_id: fid})
    });
    toast(`Reassigning + re-running against ${features[idx].name}…`);
    setTimeout(loadGapPrRuns, 1500);
    $("#gap-pr-detail").style.display = "none";
  }catch(e){ toast(e.message, true); }
};
if($("#gap-pr-refresh")) $("#gap-pr-refresh").onclick = () => loadGapPrRuns();

if($("#gap-pr-manual")) $("#gap-pr-manual").onclick = async () => {
  if(!currentFeature || !currentProject){ toast("Open a feature first",true); return; }
  const choice = await uiPrompt("Run PR coverage",
    "Paste a full PR/MR URL (github.com/.../pull/N or gitlab.com/.../merge_requests/N) — or just a PR number if you only have one App repo connected.", "");
  if(!choice) return;
  const v = String(choice).trim();
  const body = {feature_id: currentFeature};
  if (/https?:\/\//i.test(v)) {
    body.pr_url = v;
  } else {
    // Number-only — fall back to the project's first App repo
    const repos = await api(`/api/projects/${currentProject}/repos`);
    const appRepos = (repos.repos||[]).filter(rp => (rp.repo_type||"app")==="app");
    if(!appRepos.length){ toast("No App repos connected on this project", true); return; }
    const pn = parseInt(v.replace(/[^0-9]/g,""));
    if(!pn){ toast("Enter a numeric PR number or a full PR/MR URL", true); return; }
    body.repo_id = appRepos[0].id;
    body.pr_number = pn;
  }
  const btn = $("#gap-pr-manual");
  const origLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Starting…";
  $("#gap-pr-list").innerHTML = `<div class="muted">⏳ Starting coverage analysis…</div>`;
  let jobId = null;
  try{
    const r = await api("/api/code-coverage/runs/manual", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify(body)
    });
    jobId = r.job_id;
    toast(`Coverage run started · ${r.repo_full_name||""} #${r.pr_number||""}`);
  }catch(e){
    toast(e.message, true);
    btn.disabled = false; btn.textContent = origLabel;
    $("#gap-pr-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }
  // Poll the job + refresh the run list periodically until terminal.
  const start = Date.now();
  async function poll(){
    try{
      const j = await api(`/api/jobs/${jobId}`);
      const stage = j.stage || "Working…";
      const progress = j.progress || 0;
      $("#gap-pr-list").innerHTML = `<div class="muted">⏳ ${esc(stage)} · ${progress}%</div>`;
      if (j.status === "succeeded" || j.status === "failed") {
        btn.disabled = false; btn.textContent = origLabel;
        if (j.status === "failed") toast(`Run failed: ${j.error||""}`, true);
        loadGapPrRuns();
        return;
      }
    } catch(e){ /* keep polling on transient errors */ }
    if (Date.now() - start > 10*60*1000) {  // give up after 10 min
      btn.disabled = false; btn.textContent = origLabel;
      loadGapPrRuns();
      return;
    }
    setTimeout(poll, 1500);
  }
  poll();
};

async function loadGapAuto() {
  if (!currentFeature) return;
  $("#gap-auto-stats").style.display = "none";
  skIn("#gap-auto-repos",skeleton.rows(4,"Loading automation repositories"));
  try {
    const r = await api(`/api/features/${currentFeature}/automation-coverage`);
    const repos = r.test_repos || [];
    if (!repos.length) {
      $("#gap-auto-repos").innerHTML = `<div class="muted">No <b>Test</b> repos connected on this project. Add one from the project detail page (type = Test).</div>`;
      $("#gap-auto-summary").textContent = "";
      return;
    }
    $("#gap-auto-repos").innerHTML = repos.map(rp => {
      const status = rp.scan_status || "never";
      const last = rp.last_scan_at ? new Date(rp.last_scan_at*1000).toLocaleString() : "never";
      const badge = {
        running: '<span class="badge functional">scanning…</span>',
        done: '<span class="badge api">scanned</span>',
        failed: '<span class="badge nfr" style="color:var(--red)">scan failed</span>',
        never: '<span class="badge">never scanned</span>',
      }[status] || `<span class="badge">${esc(status)}</span>`;
      const actionBtns = status === 'running'
        ? `<button class="ghost" type="button" disabled>Scanning…</button>
           <button class="ghost" type="button" onclick="resetScanStatus('${rp.id}')" title="Force-clear a scan that's been stuck for too long" style="color:var(--amber)">Reset</button>`
        : `<button class="ghost" type="button" onclick="rescanTestRepo('${rp.id}')">Rescan</button>`;
      return `<div class="repo-item-card">
        <div style="flex:1">
          <div><b>${esc(rp.full_name)}</b> ${badge}</div>
          <div class="muted" style="font-size:11px;margin-top:3px">files: ${rp.scan_files_found||0} · tests extracted: ${rp.scan_cases_count||0} · last scan: ${esc(last)}${rp.scan_error?` · <span class="err">${esc(rp.scan_error)}</span>`:""}</div>
        </div>
        <div style="display:flex;gap:6px">${actionBtns}</div>
      </div>`;
    }).join("");

    const haveScan = (r.total_generated || 0) > 0 && (r.items || []).length;
    if(!haveScan){
      $("#gap-auto-summary").textContent = repos.length ? "Rescan a test repo to populate coverage." : "";
      return;
    }
    $("#gap-auto-stats").style.display = "block";
    $("#gap-auto-pct").textContent = (r.coverage_pct ?? 0) + "%";
    $("#gap-auto-covered").textContent = r.covered_count ?? 0;
    $("#gap-auto-missing").textContent = r.missing_count ?? 0;
    $("#gap-auto-total").textContent = r.total_generated ?? 0;
    $("#gap-auto-summary").textContent =
      `${r.covered_count}/${r.total_generated} covered · scanned ${r.scanned_repo_full_name||""}`;
    const sections = {};
    for (const it of r.items || []) {
      const t = (it.generated_type || "other").toLowerCase();
      (sections[t] = sections[t] || {covered:[], missing:[]});
      if (it.status === "covered") {
        sections[t].covered.push(it);
      } else {
        sections[t].missing.push(it);
      }
    }

    const TYPE_TITLES = {
      functional: "Business tests", 
      e2e: "End-to-End",
      api: "API tests", 
      ui: "UI validations", 
      nfr: "Edge cases",
      other: "Other tests"
    };
    const TYPE_ORDER = ["functional","e2e","api","ui","nfr","other"];

    $("#gap-auto-items").innerHTML = TYPE_ORDER.filter(t => sections[t]).map(t => {
      const sec = sections[t];
      const secTotal = sec.covered.length + sec.missing.length;
      
      const renderItem = it => {
        const m = it.match;
        const isCov = it.status === "covered" && m;
        const prio = ({p1:"high",p2:"medium",p3:"low","1":"high","2":"medium","3":"low",critical:"high",mid:"medium",high:"high",medium:"medium",low:"low"}[(it.priority||"low").toString().toLowerCase()]||"low");
        const displayCodeHtml = it.display_id 
          ? `<code class="auto-cov-code">${esc(it.display_id)}</code>` 
          : "";
          
        let detailHtml = "";
        if (isCov) {
          const fw = m.framework || "unknown";
          const fwClass = ["playwright", "cypress", "cucumber", "jest"].includes(fw.toLowerCase()) 
            ? fw.toLowerCase() 
            : "unknown";
            
          const shortRepo = (m.repo_full_name || "").split("/").pop() || m.repo_full_name || "";
          
          let fileLink = "";
          if (m.file_url) {
            const shortPath = (m.file_path || "").split("/").slice(-3).join("/");
            fileLink = `<a href="${esc(m.file_url)}" target="_blank" rel="noopener" class="auto-cov-detail-link" title="Open file">${esc(shortPath)}</a>`;
          } else if (m.file_path) {
            const shortPath = (m.file_path || "").split("/").slice(-3).join("/");
            fileLink = `<span class="auto-cov-detail-link" title="${esc(m.file_path)}">${esc(shortPath)}</span>`;
          }
          
          detailHtml = `
            <div class="auto-cov-detail">
              <p class="auto-cov-detail-label">Matched Automation Test</p>
              <p class="auto-cov-detail-title">${esc(m.title || "Untitled test")}</p>
              <div class="auto-cov-detail-meta">
                <span class="auto-cov-fw-badge ${fwClass}">${esc(fw)}</span>
                <span class="auto-cov-repo-badge" title="${esc(m.repo_full_name)}">${esc(shortRepo)}</span>
                ${fileLink}
                <span class="auto-cov-detail-confidence">${Math.round((m.score || 0) * 100)}% match confidence</span>
              </div>
            </div>
          `;
        }

        const cardClass = `auto-cov-card ${isCov ? 'covered' : 'missing'}`;
        const checkClass = `auto-cov-check ${isCov ? 'covered' : 'missing'}`;
        const prioClass = `auto-cov-priority ${prio}`;
        const statusBadgeClass = `auto-cov-badge-status ${isCov ? 'covered' : 'missing'}`;
        const typeLabelMuted = it.generated_type 
          ? `<span class="badge" style="border:none;background:transparent;padding:0;color:var(--muted);font-size:11px;margin-left:auto">${esc(it.generated_type.replace(/_/g, " "))} tests</span>` 
          : "";
          
        const statusBadge = isCov 
          ? `<span class="${statusBadgeClass}">✓ Test Exists</span>` 
          : `<span class="${statusBadgeClass}">○ Test Missing</span>`;
          
        const chevronHtml = isCov 
          ? `<span class="auto-cov-chevron">▼</span>` 
          : "";
          
        const onclickAttr = isCov 
          ? `onclick="this.closest('.auto-cov-card').classList.toggle('open')"` 
          : "";

        return `
          <div class="${cardClass}">
            <button type="button" class="auto-cov-row" ${onclickAttr}>
              <span class="${checkClass}">${isCov ? "✓" : "○"}</span>
              <span class="${prioClass}" title="Priority: ${esc(prio)}"></span>
              ${displayCodeHtml}
              <span class="auto-cov-title">${esc(it.generated_title || "")}</span>
              ${typeLabelMuted}
              ${statusBadge}
              ${chevronHtml}
            </button>
            ${detailHtml}
          </div>
        `;
      };

      return `<details class="case-group gap-section" ${sec.covered.length>0?"open":""}>
        <summary style="color:var(--text);font-size:13px;text-transform:none;letter-spacing:normal;font-weight:600">
          <div style="display:flex;align-items:center;gap:8px">
            <span>${esc(TYPE_TITLES[t]||t.toUpperCase())}</span>
            <span class="badge" style="border-radius:999px;background:rgba(255,255,255,.05);border:1px solid var(--line);color:var(--muted);padding:2px 7px;font-size:10px">${secTotal}</span>
          </div>
        </summary>
        <div class="case-group-body" style="padding:10px 14px 14px">
          ${sec.covered.length ? `
            <div class="typehdr" style="margin:0 0 8px;font-size:10.5px;color:var(--green)">DONE (${sec.covered.length})</div>
            ${sec.covered.map(renderItem).join("")}
          ` : ""}
          ${sec.missing.length ? `
            <div class="typehdr" style="margin:12px 0 8px;font-size:10.5px;color:var(--red)">MISSING (${sec.missing.length})</div>
            ${sec.missing.map(renderItem).join("")}
          ` : ""}
        </div>
      </details>`;
    }).join("");

    const stillRunning = repos.some(rp => rp.scan_status === "running");
    if (stillRunning) {
      if (GAP_AUTO_POLL) clearTimeout(GAP_AUTO_POLL);
      GAP_AUTO_POLL = setTimeout(loadGapAuto, 3000);
    }
  } catch (e) {
    $("#gap-auto-repos").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

if($("#gap-auto-refresh")) $("#gap-auto-refresh").onclick = loadGapAuto;

window.rescanTestRepo = async (rid) => {
  if(!currentProject) return;
  try{
    const fid = currentFeature ? `?feature_id=${currentFeature}` : "";
    await api(`/api/projects/${currentProject}/repos/${rid}/rescan${fid}`, {method:"POST"});
    toast("Rescan started — matching only the current feature for speed");
    setTimeout(loadGapAuto, 1500);
  }catch(e){ toast(e.message, true); }
};

window.resetScanStatus = async (rid) => {
  if(!currentProject) return;
  if(!await uiConfirm("Force-mark this scan as failed? Use this when a scan has been stuck for several minutes.", "Reset Scan Status", "Reset", true)) return;
  try{
    await api(`/api/projects/${currentProject}/repos/${rid}/scan/reset`, {method:"POST"});
    toast("Scan reset — you can now try Rescan again");
    setTimeout(loadGapAuto, 500);
  }catch(e){ toast(e.message, true); }
};

// ---- Test Plan ----
async function initTestPlan() {
  if (!currentFeature) {
    $("#tp-no-feature").style.display = "block";
    $("#tp-workspace").style.display = "none";
    return;
  }
  $("#tp-no-feature").style.display = "none";
  $("#tp-workspace").style.display = "block";
  $("#tp-feat-title").textContent = `${$("#d-name").textContent || "Feature"} — Test Plan`;
  $("#tp-content").innerHTML = skeletonState(`<div style="display:grid;gap:18px">${skeleton.blockLines(5)}${skeleton.blockLines(4)}</div>`,"Loading test plan");
  $("#tp-content").style.display = "block";
  $("#tp-progress").style.display = "block";
  $("#tp-bar").style.width = "30%";
  $("#tp-status").textContent = "Loading test plan status...";
  $("#tp-generate-btn").style.display = "none";
  $("#tp-export-csv").style.display = "none";
  $("#tp-export-pdf").style.display = "none";
  
  try {
    const res = await api(`/api/features/${currentFeature}/test-plan/latest`);
    const run = res.run;
    if (!run) {
      $("#tp-progress").style.display = "none";
      $("#tp-content").innerHTML = "";
      $("#tp-content").style.display = "none";
      $("#tp-status").textContent = "No test plan generated yet.";
      $("#tp-generate-btn").style.display = "inline-block";
      $("#tp-generate-btn").disabled = false;
    } else if (run.status === "COMPLETED") {
      $("#tp-progress").style.display = "none";
      $("#tp-status").textContent = "";
      $("#tp-content").innerHTML = renderTestPlan(run.content);
      $("#tp-content").style.display = "block";
      $("#tp-export-csv").href = `/api/test-plan/runs/${run.id}/export/csv`;
      $("#tp-export-csv").style.display = "inline-block";
      $("#tp-export-pdf").href = `/api/test-plan/runs/${run.id}/export/pdf`;
      $("#tp-export-pdf").style.display = "inline-block";
    } else if (run.status === "PROCESSING") {
      watchTestPlanStream(run.id);
    } else {
      $("#tp-progress").style.display = "none";
      $("#tp-content").innerHTML = "";
      $("#tp-content").style.display = "none";
      $("#tp-status").innerHTML = `<span class="err">Previous generation failed.</span>`;
      $("#tp-generate-btn").style.display = "inline-block";
      $("#tp-generate-btn").disabled = false;
    }
  } catch (e) {
    $("#tp-progress").style.display = "none";
    $("#tp-content").innerHTML = "";
    $("#tp-content").style.display = "none";
    $("#tp-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
  }
}

$("#tp-generate-btn").onclick = async () => {
  if (!currentFeature) return;
  $("#tp-generate-btn").disabled = true;
  $("#tp-status").textContent = "Initializing test plan run...";
  $("#tp-progress").style.display = "block";
  $("#tp-bar").style.width = "20%";
  
  try {
    const res = await api(`/api/features/${currentFeature}/test-plan`, { method: "POST" });
    watchTestPlanStream(res.runId);
  } catch (e) {
    $("#tp-progress").style.display = "none";
    $("#tp-status").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    $("#tp-generate-btn").disabled = false;
  }
};

function watchTestPlanStream(runId) {
  $("#tp-progress").style.display="block";
  $("#tp-bar").style.width="30%";
  $("#tp-status").textContent="Synthesizing test plan via LLM...";
  $("#tp-content").style.fontFamily="inherit";
  $("#tp-content").innerHTML=skeletonState(`<div style="display:grid;gap:18px">${skeleton.blockLines(5)}${skeleton.blockLines(4)}${skeleton.blockLines(6)}</div>`,"Generating test plan");
  $("#tp-content").style.display="block";
  $("#tp-generate-btn").style.display="none";
  $("#tp-export-csv").style.display="none";
  $("#tp-export-pdf").style.display="none";
  
  const es = new EventSource(`/api/test-plan/runs/${runId}/stream`);
  es.addEventListener("status", e => {
    const payload = JSON.parse(e.data);
    if (payload.status === "COMPLETED") {
      es.close();
      $("#tp-progress").style.display="none";
      $("#tp-status").textContent="Completed";
      $("#tp-content").style.fontFamily="monospace";
      $("#tp-content").innerHTML = renderTestPlan(payload.testPlan);
      $("#tp-content").style.display="block";
      $("#tp-export-csv").href = `/api/test-plan/runs/${runId}/export/csv`;
      $("#tp-export-csv").style.display = "inline-block";
      $("#tp-export-pdf").href = `/api/test-plan/runs/${runId}/export/pdf`;
      $("#tp-export-pdf").style.display = "inline-block";
    } else if (payload.status === "FAILED") {
      es.close();
      $("#tp-progress").style.display="none";
      $("#tp-content").innerHTML="";$("#tp-content").style.display="none";
      $("#tp-status").innerHTML = `<span class="err">Failed to generate test plan.</span>`;
      $("#tp-generate-btn").style.display = "inline-block";
      $("#tp-generate-btn").disabled = false;
    } else {
      $("#tp-bar").style.width="60%";
      $("#tp-status").textContent="Synthesizing sections via LLM...";
    }
  });
  es.addEventListener("done", () => es.close());
  es.addEventListener("error", () => {
    es.close();
    $("#tp-progress").style.display="none";
    $("#tp-status").innerHTML = `<span class="err">Connection lost. Re-checking...</span>`;
    setTimeout(initTestPlan, 2000);
  });
}

function renderTestPlan(plan) {
  if (!plan || !plan.sections) return "";
  let html = "";
  const meta = plan.meta || {};
  html += `<h1>${esc(meta.featureName || 'Test Plan')}</h1>`;
  if (meta.projectName) {
    html += `<div class="muted" style="margin-bottom:15px">Project: ${esc(meta.projectName)} · Version: ${esc(meta.featureVersionNumber)}</div>`;
  }
  
  plan.sections.forEach(sec => {
    html += `<h2 style="color:var(--accent2);margin-top:20px;border-bottom:1px solid var(--line);padding-bottom:5px">${esc(sec.title)}</h2>`;
    const type = sec.type;
    const content = sec.content;
    
    if (type === 'paragraph') {
      html += `<p>${esc(content)}</p>`;
    } else if (type === 'bullets' || type === 'checklist') {
      if (Array.isArray(content)) {
        html += `<ul style="padding-left:20px;margin:8px 0">${content.map(x => `<li style="margin:4px 0">${esc(x)}</li>`).join("")}</ul>`;
      }
    } else if (type === 'key_value') {
      if (Array.isArray(content)) {
        html += `<table style="margin-top:10px">` + content.map(x => `<tr><td style="font-weight:600;width:180px">${esc(x.key)}</td><td>${esc(x.value)}</td></tr>`).join("") + `</table>`;
      }
    } else if (type === 'grouped_list') {
      if (content && typeof content === 'object') {
        if (content.in_scope && content.in_scope.length) {
          html += `<h3 style="font-size:13px;margin:10px 0 4px">In Scope:</h3><ul style="padding-left:20px;margin-bottom:8px">` + content.in_scope.map(x => `<li style="margin:4px 0">${esc(x)}</li>`).join("") + `</ul>`;
        }
        if (content.out_of_scope && content.out_of_scope.length) {
          html += `<h3 style="font-size:13px;margin:10px 0 4px">Out of Scope:</h3><ul style="padding-left:20px;margin-bottom:8px">` + content.out_of_scope.map(x => `<li style="margin:4px 0">${esc(x)}</li>`).join("") + `</ul>`;
        }
      }
    } else if (type === 'table') {
      if (content && typeof content === 'object') {
        const columns = content.columns || [];
        const rows = content.rows || [];
        html += `<table style="margin-top:10px"><thead><tr>` + columns.map(c => `<th>${esc(c)}</th>`).join("") + `</tr></thead><tbody>`;
        rows.forEach(r => {
          if (Array.isArray(r)) {
            html += `<tr>` + r.map(cell => `<td>${esc(cell)}</td>`).join("") + `</tr>`;
          } else if (r && typeof r === 'object') {
            html += `<tr>` + columns.map(c => `<td>${esc(r[c] || '')}</td>`).join("") + `</tr>`;
          }
        });
        html += `</tbody></table>`;
      }
    } else {
      html += `<pre>${esc(JSON.stringify(content, null, 2))}</pre>`;
    }
  });
  return html;
}


// ---- Import Sheet ----
// Track which feature the import modals operate on (set by entry-point handlers).
let IMP_FID = null, IMP_PID = null;
let IMP_FILE_NAME = "";
let IMPLIB_ITEMS = [];
let IMPLIB_DESIRED = new Map();

window.openImportSheetModal = async (fid, pid) => {
  IMP_FID = fid || currentFeature || null;
  IMP_PID = pid || currentProject || null;
  if (!IMP_FID || !IMP_PID) { toast("Open a feature first", true); return; }
  IMP_FILE_NAME = "";
  const fname = (currentFeatureData && currentFeatureData.id === IMP_FID)
    ? currentFeatureData.name
    : ($("#d-name")?.textContent || "this feature");
  $("#imp-heading").textContent = "Import test cases";
  $("#imp-subtitle").innerHTML = `Updating: <b>${esc(fname)}</b>`;
  $("#imp-modal").classList.add("show");
  $("#imp-file").value = "";
  $("#imp-selected").textContent = "Selected: none";
  $("#imp-status").textContent = "";
  $("#imp-summary").innerHTML = "";
  $("#imp-upload").disabled = false;
  $("#imp-upload").style.display = "";
  $("#imp-cancel").textContent = "Cancel";
  $("#imp-progress").hidden = true;
};
window.importSheetForFeature = (fid, pid) => openImportSheetModal(fid, pid);
window.reuseImportsForFeature = (fid) => openImportLibraryModal(fid);

// Event-delegated handlers — the modals live OUTSIDE the original <script> tag,
// so direct $("#…").onclick assignments at script-parse time wouldn't bind.
document.addEventListener("click", (e) => {
  const actionEl = e.target.closest("[data-implib-action]");
  if (actionEl) {
    e.preventDefault();
    e.stopPropagation();
    handleImplibAction(actionEl);
    return;
  }
  const t = e.target.closest("button");
  if (!t || !t.id) return;
  if (t.id === "imp-close" || t.id === "imp-cancel") {
    $("#imp-modal").classList.remove("show");
  } else if (t.id === "imp-file-pick") {
    $("#imp-file").click();
  } else if (t.id === "imp-file-clear") {
    $("#imp-file").value = "";
    IMP_FILE_NAME = "";
    $("#imp-selected").textContent = "Selected: none";
    $("#imp-summary").innerHTML = "";
    $("#imp-status").textContent = "";
    $("#imp-upload").style.display = "";
    $("#imp-cancel").textContent = "Cancel";
    $("#imp-progress").hidden = true;
  } else if (t.id === "imp-template-xlsx" || t.id === "imp-template-csv") {
    const fmt = t.id === "imp-template-csv" ? "csv" : "xlsx";
    const fid = IMP_FID || currentFeature || "_";
    window.location.href = `/api/features/${fid}/tests/import/template?format=${fmt}`;
  } else if (t.id === "imp-upload") {
    runImpUpload();
  } else if (t.id === "implib-close") {
    $("#implib-modal").classList.remove("show");
  } else if (t.id === "implib-refresh") {
    runImplibRefresh();
  } else if (t.id === "implib-cancel") {
    $("#implib-modal").classList.remove("show");
  } else if (t.id === "implib-save") {
    saveImplibChanges();
  }
});

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "imp-file") {
    const f = e.target.files && e.target.files[0];
    IMP_FILE_NAME = f ? f.name : "";
    $("#imp-selected").textContent = `Selected: ${IMP_FILE_NAME || "none"}`;
    $("#imp-summary").innerHTML = "";
    $("#imp-status").textContent = "";
    $("#imp-upload").style.display = "";
    $("#imp-cancel").textContent = "Cancel";
    $("#imp-progress").hidden = true;
  }
});

// Also close modals when clicking outside the inner box.
document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "imp-modal") $("#imp-modal").classList.remove("show");
  if (e.target && e.target.id === "implib-modal") $("#implib-modal").classList.remove("show");
});

async function runImpUpload () {
  const f = $("#imp-file").files && $("#imp-file").files[0];
  if (!f) { toast("Pick a file first", true); return; }
  const fid = IMP_FID || currentFeature;
  const pid = IMP_PID || currentProject;
  if (!fid || !pid) { toast("No feature in scope", true); return; }
  $("#imp-heading").textContent = "Import test cases";
  $("#imp-status").innerHTML = `<span>AI analyzing test cases...</span>`;
  $("#imp-summary").innerHTML = "";
  $("#imp-progress").hidden = false;
  $("#imp-upload").disabled = true;
  const fd = new FormData(); fd.append("file", f);
  let resp;
  try {
    const r = await fetch(`/api/projects/${pid}/features/${fid}/tests/import`,
      { method: "POST", body: fd });
    resp = await r.json();
    if (!r.ok) throw new Error(resp.detail || `${r.status}`);
    if (resp.alreadyUploaded) toast("Already uploaded · reusing saved import");
  } catch (e) { toast(e.message, true); $("#imp-upload").disabled = false; $("#imp-progress").hidden = true; $("#imp-status").innerHTML = `<span class="err">${esc(e.message)}</span>`; return; }
  const iid = resp.feature_import_id;
  const start = Date.now();
  async function pollImport() {
    let s;
    try { s = await api(`/api/features/${fid}/tests/import/${iid}/status`); }
    catch (e) { s = null; }
    if (!s) { $("#imp-upload").disabled = false; return; }
    const d = s.data || {};
    $("#imp-status").innerHTML = `<span>${esc(d.details || d.status || "AI analyzing test cases...")}</span>`;
    if (d.completed) {
      $("#imp-progress").hidden = true;
      renderImportSummary(d.result_json || {}, fid, iid);
      $("#imp-upload").disabled = false;
      return;
    }
    if (Date.now() - start > 5*60*1000) { $("#imp-upload").disabled = false; return; }
    setTimeout(pollImport, 1500);
  }
  pollImport();
}

// Post-import review state (GAP1): one entry per row with the reviewer's current
// include/exclude decision + note. Seeded from the scorer's action.
let IMP_REVIEW = [];
let IMP_REVIEW_CTX = { fid: null, iid: null };

function renderImportSummary(data, fid, iid) {
  const items = data.items || [];
  IMP_REVIEW_CTX = { fid, iid };
  IMP_REVIEW = items.map(it => ({
    rid: it.project_imported_row_id || null,
    hash: it.identity_hash || null,
    included: it.action === "matched",
    note: "",
  }));
  if (!items.length) {
    $("#imp-heading").textContent = "Spreadsheet import finished";
    $("#imp-upload").style.display = "none";
    $("#imp-cancel").textContent = "Close";
    $("#imp-status").innerHTML = data.alreadyUploaded
      ? `<span class="ok">✓ Already uploaded · no parsing was repeated</span>`
      : `<span class="muted">No test rows recognized in this sheet.</span>`;
    return;
  }
  const matched = items.filter(i => i.action === "matched").length;
  const stored = items.filter(i => i.action !== "matched").length;
  const duplicateMerges = items.filter(i => i.already_uploaded).length;
  const rejected = data.rejected_count || 0;
  $("#imp-heading").textContent = "Spreadsheet import finished";
  $("#imp-subtitle").innerHTML = `Imported into <b>${esc(currentFeatureData?.name || $("#d-name")?.textContent || "this feature")}</b>`;
  $("#imp-upload").style.display = "none";
  $("#imp-cancel").textContent = "Close";
  $("#imp-status").innerHTML = "";
  $("#imp-summary").innerHTML = `
    <div class="sheet-chip-row" style="display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 18px">
      <span class="pill">${esc(IMP_FILE_NAME || "Uploaded sheet")}</span>
      ${data.alreadyUploaded ? `<span class="sheet-pill green">Already uploaded</span>` : `<span class="sheet-pill green">First import for this feature</span>`}
    </div>
    ${sheetKpis([
      ["Included", matched, "green", "OK"],
      ["Stored for later", stored, "amber", "BOX"],
      ["Rejected", rejected, "red", "!"],
      ["Duplicate merges", duplicateMerges, "purple", "NET"],
    ])}
    <div class="sheet-meta-row">
      <b>Total rows: ${items.length}</b>
      <span>Processed rows: ${items.length}</span>
    </div>
    <div class="sheet-section-head">
      <div>
        <div class="typehdr">Review imported tests</div>
        <div class="muted">Include a row in this feature, or keep it in the project library for later. Then save.</div>
      </div>
      <button class="go" onclick="impSaveReview()" style="margin:0">Save review</button>
    </div>
    <div class="sheet-list" id="imp-review-list">${items.map((it, i) => renderImportDetailCard(it, i)).join("")}</div>
  `;
  if (matched > 0) {
    // Reload the feature list + workspace if open, so the new test cases appear.
    if (typeof loadFeatures === "function") loadFeatures();
    if (fid && currentFeature === fid && typeof openFeature === "function") {
      setTimeout(() => openFeature(currentFeature), 300);
    }
  }
}

function sheetKpis(defs) {
  return `<div class="sheet-summary-grid">${defs.map(([label, value, color, icon]) => `
    <div class="sheet-kpi ${color}">
      <div class="l">${esc(label)}</div>
      <div class="v">${value}</div>
      <div class="ico">${esc(icon)}</div>
    </div>`).join("")}</div>`;
}

function renderImportDetailCard(it, idx) {
  const rv = (typeof idx === "number" && IMP_REVIEW[idx]) ? IMP_REVIEW[idx]
             : { included: it.action === "matched", note: "" };
  const included = rv.included;
  const steps = (it.steps_preview || []).join(" · ") || `${it.steps_count || 0} steps`;
  const reason = breakdownReason(it.breakdown);
  const controls = (typeof idx === "number") ? `
    <div class="imp-review-controls" style="display:flex;gap:6px;align-items:center;margin-top:10px;flex-wrap:wrap">
      <button class="${included ? "go" : "ghost"}" style="padding:4px 10px;font-size:11px;margin:0"
        onclick="impSetRow(${idx}, true)">Include</button>
      <button class="${included ? "ghost" : "go"}" style="padding:4px 10px;font-size:11px;margin:0"
        onclick="impSetRow(${idx}, false)">Keep for later</button>
      <input type="text" placeholder="note (optional)" value="${esc(rv.note || "")}"
        oninput="impSetNote(${idx}, this.value)"
        style="flex:1;min-width:140px;font-size:11.5px;padding:4px 8px"/>
    </div>` : "";
  return `<div class="sheet-test-card ${included ? "included" : "pending"}">
    <div class="sheet-card-top">
      <div class="sheet-card-title">${esc(it.title || "(no title)")}</div>
      <span class="sheet-pill ${included ? "green" : "amber"}">${included ? "Included" : "Stored"}</span>
    </div>
    <div class="sheet-card-meta">
      <span class="sheet-pill">Source row ${esc(it.row_number || it.row_index + 1 || "")}</span>
      ${it.category ? `<span class="sheet-pill blue">${esc(it.category)}</span>` : ""}
      ${it.priority ? `<span class="sheet-pill ${String(it.priority).toLowerCase()==="high"?"red":"amber"}">${esc(it.priority)}</span>` : ""}
      ${it.endpoint ? `<span class="sheet-pill">${esc(it.method || "")} ${esc(it.endpoint)}</span>` : `<span class="sheet-pill">No endpoint</span>`}
    </div>
    <div class="sheet-detail-box">
      <b>Steps:</b> ${esc(steps)}<br>
      <b>Expected:</b> ${esc(it.expected_result || "As described in the imported row.")}
    </div>
    ${reason ? `<div class="sheet-reason"><b>Reason:</b> ${esc(reason)}</div>` : ""}
    ${controls}
  </div>`;
}

// Toggle one row's include/exclude decision and re-render just its pill/buttons.
window.impSetRow = function (idx, included) {
  if (!IMP_REVIEW[idx]) return;
  IMP_REVIEW[idx].included = !!included;
  const list = $("#imp-review-list");
  if (!list) return;
  const card = list.children[idx];
  if (card) {
    card.classList.toggle("included", included);
    card.classList.toggle("pending", !included);
    const pill = card.querySelector(".sheet-card-top .sheet-pill");
    if (pill) { pill.className = `sheet-pill ${included ? "green" : "amber"}`; pill.textContent = included ? "Included" : "Stored"; }
    const btns = card.querySelectorAll(".imp-review-controls button");
    if (btns[0]) btns[0].className = included ? "go" : "ghost";
    if (btns[1]) btns[1].className = included ? "ghost" : "go";
  }
};
window.impSetNote = function (idx, val) { if (IMP_REVIEW[idx]) IMP_REVIEW[idx].note = val; };

// Persist all decisions to the /review endpoint (idempotent per row).
window.impSaveReview = async function () {
  const { fid, iid } = IMP_REVIEW_CTX;
  if (!fid || !iid) { toast("Nothing to save", true); return; }
  const reviews = IMP_REVIEW.map(r => ({
    project_imported_row_id: r.rid, identity_hash: r.hash,
    action: r.included ? "include" : "exclude", note: r.note || "",
  }));
  try {
    const r = await api(`/api/features/${fid}/tests/import/${iid}/review`,
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviews }) });
    const d = r.data || {};
    toast(`Review saved · ${d.included || 0} included, ${d.excluded || 0} removed`);
    if (typeof loadFeatures === "function") loadFeatures();
    if (fid && currentFeature === fid && typeof openFeature === "function") {
      setTimeout(() => openFeature(currentFeature), 300);
    }
  } catch (e) { toast(e.message, true); }
};

function breakdownReason(breakdown) {
  if (!breakdown || typeof breakdown !== "object") return "";
  const parts = [];
  if (breakdown.feature_anchor) parts.push("feature anchor matches");
  if (breakdown.route_family) parts.push("route family matches feature context");
  if (breakdown.intent_similarity) parts.push(`intent similarity ${(breakdown.intent_similarity || 0).toFixed ? breakdown.intent_similarity.toFixed(2) : breakdown.intent_similarity}`);
  if (breakdown.title_similarity) parts.push(`title similarity ${(breakdown.title_similarity || 0).toFixed ? breakdown.title_similarity.toFixed(2) : breakdown.title_similarity}`);
  return parts.join("; ");
}

// ---- Imported Sheet Library ----
window.openImportLibraryModal = async (fid) => {
  IMP_FID = fid || currentFeature || null;
  if (!IMP_FID) { toast("Open a feature first", true); return; }
  $("#implib-modal").classList.add("show");
  skIn("#implib-list",skeleton.rows(4,"Loading imported sheets"));
  $("#implib-stats").innerHTML = "";
  $("#implib-save").disabled = true;
  await loadImportLibrary();
};

async function runImplibRefresh () {
  const fid = IMP_FID || currentFeature;
  if (!fid) { toast("No feature in scope", true); return; }
  const btn = $("#implib-refresh");
  if (btn) { btn.disabled = true; btn.textContent = "Rescoring…"; }
  try {
    const r = await api(`/api/features/${fid}/imported-sheets/refresh`, { method: "POST" });
    const d = r.data || {};
    toast(`Rescored ${d.rescored||0} rows · auto-promoted ${d.newly_promoted||0}`);
    await loadImportLibrary();
    if (currentFeature === fid && typeof openFeature === "function") openFeature(currentFeature);
  } catch (e) { toast(e.message, true); }
  finally { if (btn) { btn.disabled = false; btn.textContent = "Refresh / rescore"; } }
}

async function loadImportLibrary() {
  const fid = IMP_FID || currentFeature;
  if (!fid) return;
  try {
    const r = await api(`/api/features/${fid}/imported-sheets`);
    IMPLIB_ITEMS = ((r.data || {}).imported_sheet_tests || []).sort((a,b) =>
      String(a.original_filename||"").localeCompare(String(b.original_filename||"")) ||
      String(a.sheet||"").localeCompare(String(b.sheet||"")) ||
      (b.score||0) - (a.score||0));
    IMPLIB_DESIRED = new Map(IMPLIB_ITEMS.map(it => [it.identity_hash, !!it.is_in_feature]));
    renderImplibList();
  } catch (e) {
    $("#implib-list").innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

function implibGroups() {
  const groups = new Map();
  for (const it of IMPLIB_ITEMS) {
    const key = `${it.feature_import_id||""}::${it.original_filename||""}::${it.sheet||""}`;
    if (!groups.has(key)) groups.set(key, { key, feature_import_id: it.feature_import_id||"", original_filename: it.original_filename||"", sheet: it.sheet||"", rows: [] });
    groups.get(key).rows.push(it);
  }
  return Array.from(groups.values());
}

function renderImplibList() {
  const groups = implibGroups();
  const rows = IMPLIB_ITEMS.length;
  const included = IMPLIB_ITEMS.filter(it => IMPLIB_DESIRED.get(it.identity_hash)).length;
  const stored = rows - included;
  $("#implib-stats").innerHTML = sheetKpis([
    ["Sheets", groups.length, "green", "DOC"],
    ["Rows", rows, "purple", "GRID"],
    ["Included", included, "green", "OK"],
    ["Stored for later", stored, "amber", "BOX"],
  ]);
  $("#implib-loaded-count").textContent = `${rows} row${rows===1?"":"s"} loaded`;
  if (!rows) {
    $("#implib-list").innerHTML = `<div class="sheet-empty">No imported tests in this project yet. Upload a sheet from Import Sheet first.</div>`;
    $("#implib-save").disabled = true;
    return;
  }
  $("#implib-list").innerHTML = groups.map((g, idx) => renderImplibGroup(g, idx === 0)).join("");
  updateImplibSaveState();
}

function attr(v) {
  return esc(v || "").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function renderImplibGroup(g, open) {
  const included = g.rows.filter(it => IMPLIB_DESIRED.get(it.identity_hash)).length;
  const total = g.rows.length;
  return `<details class="sheet-group" ${open ? "open" : ""}>
    <summary>
      <div class="sheet-group-main">
        <div class="sheet-icon">DOC</div>
        <div>
          <div class="sheet-group-title">${esc(g.original_filename || "Imported sheet")} ${g.sheet ? `<span class="sheet-pill blue">${esc(g.sheet)}</span>` : ""}</div>
          <div class="sheet-group-sub">${total} row${total===1?"":"s"} total · <span class="ok">${included} included</span></div>
        </div>
      </div>
      <div class="sheet-group-actions">
        <button class="sheet-danger-ghost" data-implib-action="remove-all" data-group="${attr(g.key)}" type="button"
          title="Remove every row of this sheet from THIS feature. The rows stay in the project library.">Remove all from feature</button>
        <button class="sheet-danger-ghost" data-implib-action="delete-sheet" data-feature-import-id="${attr(g.feature_import_id)}" data-filename="${attr(g.original_filename)}" data-sheet="${attr(g.sheet)}" type="button"
          title="Delete this sheet's rows from the WHOLE project library (all features). Cannot be undone.">Delete sheet from project</button>
        <span class="sheet-collapse">^</span>
      </div>
    </summary>
    <div class="sheet-group-body">${g.rows.map(renderImplibRow).join("")}</div>
  </details>`;
}

function renderImplibRow(it) {
  const desired = !!IMPLIB_DESIRED.get(it.identity_hash);
  const steps = (it.steps_preview || []).join(" · ") || `${it.steps_count || 0} steps`;
  return `<div class="sheet-test-card ${desired ? "included" : "pending"}">
    <div class="sheet-card-top">
      <div>
        <div class="sheet-card-title">${esc(it.title || "(no title)")}</div>
        <div class="muted">Source row ${esc(it.source_row_number || "")}</div>
      </div>
      <span class="sheet-pill ${desired ? "green" : ""}">${desired ? "Included" : "Available"}</span>
    </div>
    <div class="sheet-card-meta">
      ${it.category ? `<span class="sheet-pill blue">${esc(it.category)}</span>` : ""}
      ${it.priority ? `<span class="sheet-pill ${String(it.priority).toLowerCase()==="high"?"red":"amber"}">${esc(it.priority)}</span>` : ""}
      ${it.endpoint ? `<span class="sheet-pill">${esc(it.method || "")} ${esc(it.endpoint)}</span>` : ""}
      <span class="sheet-pill">Score ${(it.score || 0).toFixed(2)}</span>
    </div>
    <div class="sheet-detail-box">
      <b>Steps:</b> ${esc(steps)}<br>
      <b>Expected:</b> ${esc(it.expected_result || "As described in the imported row.")}
    </div>
    <div class="sheet-action-row">
      <button class="${desired ? "sheet-danger-ghost" : "sheet-primary"}" data-implib-action="${desired ? "toggle-remove" : "toggle-add"}" data-hash="${attr(it.identity_hash)}" type="button"
        title="${desired ? "Remove this test case from this feature (it stays in the project library)" : "Add this row to this feature as a test case"}">${desired ? "Remove from feature" : "Add to feature"}</button>
    </div>
  </div>`;
}

function updateImplibSaveState() {
  const changed = IMPLIB_ITEMS.some(it => !!it.is_in_feature !== !!IMPLIB_DESIRED.get(it.identity_hash));
  $("#implib-save").disabled = !changed;
}

function handleImplibAction(el) {
  const action = el.dataset.implibAction;
  if (action === "toggle-add" || action === "toggle-remove") {
    const hash = el.dataset.hash;
    IMPLIB_DESIRED.set(hash, action === "toggle-add");
    renderImplibList();
  } else if (action === "remove-all") {
    const key = el.dataset.group;
    const group = implibGroups().find(g => g.key === key);
    if (group) group.rows.forEach(it => IMPLIB_DESIRED.set(it.identity_hash, false));
    renderImplibList();
  } else if (action === "delete-sheet") {
    implibDeleteSheet(el.dataset.featureImportId || "", el.dataset.filename || "", el.dataset.sheet || "");
  }
}

async function saveImplibChanges() {
  const fid = IMP_FID || currentFeature;
  if (!fid) return;
  const add = IMPLIB_ITEMS.filter(it => !it.is_in_feature && IMPLIB_DESIRED.get(it.identity_hash)).map(it => it.identity_hash);
  const remove = IMPLIB_ITEMS.filter(it => it.is_in_feature && !IMPLIB_DESIRED.get(it.identity_hash)).map(it => it.identity_hash);
  if (!add.length && !remove.length) return;
  const btn = $("#implib-save");
  btn.disabled = true;
  btn.textContent = "Saving...";
  try {
    if (add.length) {
      await api(`/api/features/${fid}/imported-sheets/add`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ identity_hashes: add }) });
    }
    if (remove.length) {
      await api(`/api/features/${fid}/imported-sheets/remove`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ identity_hashes: remove }) });
    }
    toast("Imported sheet changes saved");
    await loadImportLibrary();
    if (typeof openFeature === "function") openFeature(fid);
  } catch (e) {
    toast(e.message, true);
    updateImplibSaveState();
  } finally {
    btn.textContent = "Save changes";
  }
}

window.implibToggle = async (hash, add, deleteSystem=false) => {
  const fid = IMP_FID || currentFeature;
  if (!fid) return;
  const proceed = async () => {
    const url = `/api/features/${fid}/imported-sheets/${add?"add":"remove"}`;
    try {
      await api(url, { method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ identity_hashes: [hash], delete_from_system: !!deleteSystem }) });
      toast(add ? "Added to this feature" : (deleteSystem ? "Deleted from imported library" : "Removed"));
      await loadImportLibrary();
      if ((add || deleteSystem) && typeof openFeature === "function") openFeature(currentFeature);
    } catch (e) { toast(e.message, true); }
  };
  if (deleteSystem) {
    openCaseConfirmation({
      title: "Delete imported test",
      copy: "Delete this imported test from the project library and every linked feature?",
      summary: "",
      confirmLabel: "Delete test",
      danger: true,
      onConfirm: proceed
    });
  } else {
    await proceed();
  }
};

window.implibDeleteSheet = async (featureImportId, originalFilename, sheetName) => {
  const fid = IMP_FID || currentFeature;
  if (!fid) return;
  const label = `${originalFilename || "this upload"}${sheetName?` · ${sheetName}`:""}`;
  openCaseConfirmation({
    title: "Delete imported sheet",
    copy: `Permanently delete ${label}?`,
    summary: `<div style="color:var(--red);font-weight:600;margin-top:4px">This will delete all imported test cases from this sheet across every feature in this project.</div>`,
    confirmLabel: "Delete sheet",
    danger: true,
    onConfirm: async () => {
      await api(`/api/features/${fid}/imported-sheets/remove`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          delete_from_system: true,
          feature_import_id: featureImportId || null,
          original_filename: originalFilename || null,
          sheet_name: sheetName || null
        })
      });
      toast("Deleted imported sheet permanently");
      await loadImportLibrary();
      if (typeof openFeature === "function") openFeature(currentFeature);
    }
  });
};

// ---- boot ----
// First-run gate: until the required LLM section has been saved (settings.configured),
// sign-in lands on Configuration. This is a soft redirect only — the user is free to
// navigate anywhere else; nothing is locked.
async function needsConfig(){
  try{const s=await api("/api/settings");return !s.configured;}catch(e){return false;}
}
async function startApp(){
  // Block on a mandatory password change before anything else renders — only
  // ever true for the local admin account, and only while it's still on the
  // shipped default password.
  if(ME&&ME.must_change_password)await openChangePasswordModal(true);
  refreshStatus();
  let nav={};try{nav=JSON.parse(localStorage.getItem("wq_nav")||"{}");}catch(e){}
  if(nav.project)currentProject=nav.project;
  if(nav.feature)currentFeature=nav.feature;
  if(await needsConfig()){navigateTo("config");return;}
  const hashView=(location.hash||"").replace(/^#/,"");
  navigateTo(hashView||nav.view||"dashboard");   // restore last view, not always Dashboard
}
// If the user arrived via an invitation LINK (/invite?token=… or ?token=…), resolve
// the token, steer them through login-in-context, then straight to accept/decline.
// Returns true if it handled the boot (caller should stop).
async function handleInviteLink(){
  let token=null;
  try{token=new URLSearchParams(location.search).get("token");}catch(e){}
  if(!token)return false;
  // Remember it so we survive the login round-trip, then clean the URL.
  try{sessionStorage.setItem("wq_invite_token",token);}catch(e){}
  try{history.replaceState(null,"",location.pathname.replace(/\/invite$/,"/")||"/");}catch(e){}
  let info=null;
  try{const r=await fetch(`/api/invite/verify?token=${encodeURIComponent(token)}`);
    if(r.ok)info=await r.json();}catch(e){}
  if(!info){                              // bad/expired token
    showLogin();
    if(typeof toast==="function")toast("This invitation link is invalid or has expired.",true);
    return true;
  }
  // Already signed in as the invited person? Go straight to accept/decline.
  const me=await checkAuth();
  if(me && ME && ME.email===info.email){
    try{sessionStorage.removeItem("wq_invite_token");}catch(e){}
    if(await maybeShowInvite())return true;
    startApp();return true;
  }
  // Not signed in (or as someone else): prompt login prefilled with the invited email.
  showLogin();
  const em=$("#login-email");if(em){em.value=info.email;}
  $("#login-msg").textContent=`You've been invited to ${info.invite&&info.invite.workspace||"WardenIQ"} as ${info.invite&&info.invite.role||"a user"}. Sign in as ${info.email} to accept.`;
  return true;
}
(async()=>{
  if(await handleInviteLink())return;
  if(await checkAuth()){if(await maybeShowInvite())return;startApp();}
})();
setInterval(()=>{if(ME)refreshStatus();},5000);
// Poll identity so admin-side role/disable changes propagate within ~30s even
// without a tab focus event (focus handler covers the common case instantly).
setInterval(()=>{if(ME)refreshMe();},30000);

// ---- disable browser autofill / autocomplete / suggestions on every field ----
// Applies to inputs/textareas/selects that exist now AND any added later (modals,
// tables, config forms are rendered dynamically), so nothing slips through.
function hardenField(el){
  if(!el||el.dataset.wqNoauto)return;
  const tag=el.tagName;
  if(tag!=="INPUT"&&tag!=="TEXTAREA"&&tag!=="SELECT")return;
  const type=(el.getAttribute("type")||"").toLowerCase();
  // "new-password" is the most reliable way to stop the password-manager dropdown.
  el.setAttribute("autocomplete", type==="password" ? "new-password" : "off");
  el.setAttribute("autocorrect","off");
  el.setAttribute("autocapitalize","off");
  el.setAttribute("spellcheck","false");
  el.setAttribute("data-lpignore","true");   // LastPass
  el.setAttribute("data-1p-ignore","true");   // 1Password
  el.dataset.wqNoauto="1";
}
function hardenFields(root){
  const r=root||document;
  if(r.querySelectorAll)r.querySelectorAll("input,textarea,select").forEach(hardenField);
  if(r.querySelectorAll)r.querySelectorAll("form").forEach(f=>f.setAttribute("autocomplete","off"));
}
hardenFields(document);
new MutationObserver(muts=>{
  for(const m of muts)for(const n of m.addedNodes){
    if(n.nodeType!==1)continue;
    if(n.matches&&n.matches("input,textarea,select"))hardenField(n);
    hardenFields(n);
  }
}).observe(document.documentElement,{childList:true,subtree:true});
