// Variables used by Scriptable.
// icon-color: cyan; icon-glyph: gas-pump;
// FuelForecast dual learning capture: 11:50 target and 12:20 noon reset.
// Reads iCloud Drive/Scriptable/FuelForecast/memory/config.json

const fm = FileManager.iCloud();
const root = fm.joinPath(fm.documentsDirectory(), "FuelForecast");
const memory = fm.joinPath(root, "memory");
const configPath = fm.joinPath(memory, "config.json");
const observationsPath = fm.joinPath(memory, "observations.jsonl");
const noonResetsPath = fm.joinPath(memory, "noon_resets.jsonl");
const noonStatusPath = fm.joinPath(memory, "noon_reset_status.json");
const noonShadowPath = fm.joinPath(memory, "noon_shadow_forecast.json");
const noonShadowHistoryPath = fm.joinPath(memory, "noon_shadow_history.jsonl");
const forecastPath = fm.joinPath(memory, "forecast.json");
const morningContextPath = fm.joinPath(memory, "morning_context.json");
const rejectionsPath = fm.joinPath(memory, "capture_rejections.jsonl");
const recoveryPath = fm.joinPath(memory, "capture_recovery_request.json");
const statusPath = fm.joinPath(memory, "capture_status.json");

if (!fm.fileExists(root)) fm.createDirectory(root, true);
if (!fm.fileExists(memory)) fm.createDirectory(memory, true);
await ensureDownloaded(configPath);
if (!fm.fileExists(configPath)) throw new Error("FuelForecast/memory/config.json fehlt.");
await ensureDownloaded(observationsPath);
await ensureDownloaded(noonResetsPath);
await ensureDownloaded(noonStatusPath);
await ensureDownloaded(noonShadowHistoryPath);
await ensureDownloaded(forecastPath);
await ensureDownloaded(morningContextPath);
await ensureDownloaded(rejectionsPath);
await ensureDownloaded(recoveryPath);

const cfg = JSON.parse(fm.readString(configPath));
const c = cfg.region.center;
const radius = cfg.region.radius_km || 25;
const fuel = cfg.fuel || "diesel";
const key = cfg.tankerkoenig_api_key;
if (!key || key.startsWith("PASTE_")) throw new Error("Tankerkönig API Key in config.json eintragen.");

const now = new Date();
const df = new DateFormatter(); df.dateFormat = "yyyy-MM-dd";
const iso = now.toISOString();
const today = df.string(now);
let observationRows=readJsonLines(observationsPath);
let noonRows=readJsonLines(noonResetsPath);
const morningContext=fm.fileExists(morningContextPath)
  ? JSON.parse(fm.readString(morningContextPath))
  : {};
const shortcutParameter=(typeof args!=="undefined" && args.shortcutParameter!=null)
  ? String(args.shortcutParameter).trim().toLowerCase()
  : "auto";
const requestedMode=["pre_noon","noon_reset"].includes(shortcutParameter)
  ? shortcutParameter : "auto";
const timeAssessment=assessCapture(null, requestedMode);
if (!timeAssessment.accepted) {
  rejectCapture(timeAssessment, null);
  throw new Error(`FuelForecast Capture abgelehnt: ${timeAssessment.reasons.map(x=>x.code).join(", ")}`);
}
const captureType=timeAssessment.capture_type;
let rows=captureType==="pre_noon" ? observationRows : noonRows;

const url =
  `https://creativecommons.tankerkoenig.de/json/list.php?lat=${c.lat.toFixed(5)}` +
  `&lng=${c.lng.toFixed(5)}&rad=${radius}&sort=price&type=${fuel}&apikey=${encodeURIComponent(key)}`;

const data = await new Request(url).loadJSON();
if (!data.ok) throw new Error(`Tankerkönig: ${data.message || "API Fehler"}`);

const open = (data.stations || [])
  .filter(s => s.isOpen === true && s.price != null)
  .map(s => ({
    id: s.id, name: s.name, brand: s.brand, place: s.place,
    postCode: s.postCode, street: s.street, houseNumber: s.houseNumber,
    lat: s.lat, lng: s.lng, dist: s.dist, price: Number(s.price), isOpen: true
  }))
  .sort((a,b) => a.price - b.price);

function median(a) {
  const x = [...a].sort((a,b)=>a-b);
  if (!x.length) return null;
  const m = Math.floor(x.length/2);
  return x.length % 2 ? x[m] : (x[m-1]+x[m])/2;
}
function quantile(a, q) {
  const x=[...a].sort((a,b)=>a-b);
  if (!x.length) return null;
  const pos=(x.length-1)*q, lo=Math.floor(pos), hi=Math.ceil(pos);
  return lo===hi ? x[lo] : x[lo]*(hi-pos)+x[hi]*(pos-lo);
}
function placeMetrics(place) {
  const needle = place.toLocaleLowerCase("de-DE");
  const subset = open.filter(s =>
    (s.place || "").toLocaleLowerCase("de-DE").includes(needle) ||
    (s.name || "").toLocaleLowerCase("de-DE").includes(needle));
  return {
    count: subset.length,
    best: subset.length ? subset[0].price : null,
    cheap_reference: subset.length ? median(subset.slice(0,3).map(s=>s.price)) : null,
    stations: subset.slice(0,5)
  };
}

const prices=open.map(s=>s.price);
const places={};
for (const p of (cfg.region.preferred_places || [])) places[p]=placeMetrics(p);
const preNoonRow=observationRows.find(x=>x.date===today && x.metrics?.cheap_reference!=null);
const preNoonReference=preNoonRow ? Number(preNoonRow.metrics.cheap_reference) : null;

const observation = {
  version: 1,
  capture_type: captureType,
  date: today,
  captured_at: iso,
  source: "Tankerkönig realtime API / MTS-K",
  fuel,
  metrics: {
    count: open.length,
    best: prices.length ? prices[0] : null,
    cheap_reference: open.length ? median(open.slice(0,5).map(s=>s.price)) : null,
    q25: quantile(prices, 0.25),
    median: median(prices),
    top5: open.slice(0,5),
    places
  }
};
if (captureType==="noon_reset") {
  observation.target_time=(cfg.capture || {}).noon_reset_target_time || "12:20";
  observation.target_semantics="post-12 reset proxy; later price reductions remain possible";
  observation.pre_noon_reference=preNoonReference;
  observation.reset_jump_ct=preNoonReference==null
    ? null
    : Number(((observation.metrics.cheap_reference-preNoonReference)*100).toFixed(1));
}

const assessment=assessCapture(observation, captureType);
if (!assessment.accepted) {
  rejectCapture(assessment, observation);
  throw new Error(`FuelForecast Capture abgelehnt: ${assessment.reasons.map(x=>x.code).join(", ")}`);
}

// Idempotent daily write: replace today's line only after all guards pass.
rows=rows.filter(x=>x.date !== observation.date);
rows.push(observation); rows.sort((a,b)=>a.date.localeCompare(b.date));
const targetPath=captureType==="pre_noon" ? observationsPath : noonResetsPath;
writeJsonLines(targetPath, rows);
if (captureType==="pre_noon") observationRows=rows; else noonRows=rows;
const acceptedStatus={
  version:1, status:"accepted", capture_type:captureType, date:observation.date,
  captured_at:observation.captured_at,
  cheap_reference:observation.metrics.cheap_reference,
  policy:assessment.policy
};
if (captureType==="noon_reset") acceptedStatus.reset_jump_ct=observation.reset_jump_ct;
fm.writeString(captureType==="pre_noon" ? statusPath : noonStatusPath,
  JSON.stringify(acceptedStatus, null, 2)+"\n");
if (captureType==="pre_noon" && fm.fileExists(recoveryPath)) {
  await ensureDownloaded(recoveryPath);
  try {
    const recovery=JSON.parse(fm.readString(recoveryPath));
    if (recovery.date===observation.date && String(recovery.status||"").startsWith("pending")) {
      recovery.status="resolved_by_valid_capture";
      recovery.resolved_at=observation.captured_at;
      fm.writeString(recoveryPath, JSON.stringify(recovery,null,2)+"\n");
    }
  } catch(e) {}
}
if (captureType==="noon_reset") writeNoonShadow(observation);

console.log(`FuelForecast ${observation.date} ${captureType}: ${observation.metrics.cheap_reference?.toFixed(3)} €/l, ${open.length} offene Stationen`);
Script.complete();

async function ensureDownloaded(path) {
  if (fm.fileExists(path) && fm.isFileStoredIniCloud(path)) {
    try { await fm.downloadFileFromiCloud(path); } catch(e) {}
  }
}

function readJsonLines(path) {
  if (!fm.fileExists(path)) return [];
  return fm.readString(path).split("\n").filter(Boolean)
    .map(x=>{ try{return JSON.parse(x)}catch(e){return null} }).filter(Boolean);
}

function writeJsonLines(path, values) {
  fm.writeString(path, values.map(x=>JSON.stringify(x)).join("\n")+(values.length?"\n":""));
}

function clockMinutes(value) {
  const parts=String(value).split(":").map(Number);
  return parts[0]*60+parts[1];
}

function dateMinutes(value) {
  return value.getHours()*60+value.getMinutes()+value.getSeconds()/60;
}

function policy() {
  const capture=cfg.capture || {};
  return {
    window_start:capture.window_start || "11:40",
    window_end:capture.window_end || "12:00",
    target_time:cfg.region.target_time || capture.target_time || "11:50",
    max_upward_jump_ct:Number(capture.max_upward_jump_ct ?? 6.0),
    max_downward_jump_ct:Number(capture.max_downward_jump_ct ?? 12.0),
    minimum_open_stations:Number(capture.minimum_open_stations ?? 5),
    noon_reset_window_start:capture.noon_reset_window_start || "12:15",
    noon_reset_window_end:capture.noon_reset_window_end || "12:31",
    noon_reset_target_time:capture.noon_reset_target_time || "12:20"
  };
}

function activePolicy(captureType) {
  const p=policy();
  if (captureType==="noon_reset") return {
    window_start:p.noon_reset_window_start,
    window_end:p.noon_reset_window_end,
    target_time:p.noon_reset_target_time,
    minimum_open_stations:p.minimum_open_stations
  };
  return {
    window_start:p.window_start, window_end:p.window_end,
    target_time:p.target_time,
    max_upward_jump_ct:p.max_upward_jump_ct,
    max_downward_jump_ct:p.max_downward_jump_ct,
    minimum_open_stations:p.minimum_open_stations
  };
}

function detectCaptureType() {
  const minute=dateMinutes(now), p=policy();
  if (minute>=clockMinutes(p.window_start) && minute<clockMinutes(p.window_end)) return "pre_noon";
  if (minute>=clockMinutes(p.noon_reset_window_start) && minute<clockMinutes(p.noon_reset_window_end)) return "noon_reset";
  return null;
}

function reason(code, message, details={}) {
  return Object.assign({code,message},details);
}

function sameDayAnchors(captureType) {
  const anchors=[];
  const sourceRows=captureType==="pre_noon" ? observationRows : noonRows;
  const sourceName=captureType==="pre_noon" ? "existing_observation" : "existing_noon_reset";
  for (const row of sourceRows) {
    if (row.date!==today || row.metrics?.cheap_reference==null || !row.captured_at) continue;
    const timestamp=new Date(row.captured_at);
    if (!Number.isFinite(timestamp.getTime()) || timestamp>now) continue;
    anchors.push({
      source:sourceName, timestamp:timestamp.toISOString(),
      reference:Number(row.metrics.cheap_reference), minute:dateMinutes(timestamp)
    });
  }
  if (captureType==="pre_noon" && morningContext?.date===today && morningContext.local?.cheap_reference!=null && morningContext.generated_at) {
    const timestamp=new Date(morningContext.generated_at);
    if (Number.isFinite(timestamp.getTime()) && timestamp<=now) {
      anchors.push({
        source:"morning_context", timestamp:timestamp.toISOString(),
        reference:Number(morningContext.local.cheap_reference), minute:dateMinutes(timestamp)
      });
    }
  }
  anchors.sort((a,b)=>new Date(a.timestamp)-new Date(b.timestamp));
  return anchors;
}

function assessCapture(observation, requestedMode="auto") {
  const captureType=requestedMode==="auto" ? detectCaptureType() : requestedMode;
  if (!captureType) {
    const p=activePolicy("pre_noon"), full=policy();
    return {
      accepted:false, capture_type:null, captured_at:iso, policy:p, anchors:[],
      reasons:[reason("outside_capture_windows",
        "Capture liegt außerhalb beider Lernfenster.",
        {local_time:`${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`,
         pre_noon_window:`${full.window_start}–${full.window_end}`,
         noon_reset_window:`${full.noon_reset_window_start}–${full.noon_reset_window_end}`})]
    };
  }
  const p=activePolicy(captureType);
  const minute=dateMinutes(now), start=clockMinutes(p.window_start), end=clockMinutes(p.window_end);
  const target=clockMinutes(p.target_time), reasons=[];
  if (minute<start || minute>=end) {
    reasons.push(reason("outside_capture_window",
      `Capture muss lokal zwischen ${p.window_start} und ${p.window_end} laufen.`,
      {local_time:`${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`}));
  }
  const anchors=sameDayAnchors(captureType);
  if (observation) {
    const reference=observation.metrics?.cheap_reference;
    const count=Number(observation.metrics?.count || 0);
    if (reference==null || Number(reference)<0.5 || Number(reference)>5.0) {
      reasons.push(reason("invalid_reference","Regionale Preisreferenz fehlt oder ist unplausibel.",{reference}));
    }
    if (count<p.minimum_open_stations) {
      reasons.push(reason("too_few_stations","Zu wenige offene Tankstellen für eine robuste Referenz.",
        {count,minimum:p.minimum_open_stations}));
    }
    const currentDistance=Math.abs(minute-target);
    for (const anchor of anchors) {
      const expectedSource=captureType==="pre_noon" ? "existing_observation" : "existing_noon_reset";
      if (anchor.source!==expectedSource) continue;
      if (anchor.minute>=start && anchor.minute<end && Math.abs(anchor.minute-target)<currentDistance) {
        reasons.push(reason("existing_capture_closer_to_target",
          "Ein gespeicherter Capture liegt bereits näher an der Zielzeit.",
          {existing_timestamp:anchor.timestamp}));
        break;
      }
    }
    if (captureType==="pre_noon" && reference!=null && anchors.length) {
      const anchor=anchors[anchors.length-1];
      const deltaCt=(Number(reference)-anchor.reference)*100;
      if (deltaCt>p.max_upward_jump_ct) {
        reasons.push(reason("implausible_upward_jump",
          "Preis liegt zu weit über dem letzten Pre-Noon-Anker.",
          {delta_ct:Number(deltaCt.toFixed(1)),maximum_ct:p.max_upward_jump_ct,
           anchor_source:anchor.source,anchor_timestamp:anchor.timestamp}));
      } else if (deltaCt < -p.max_downward_jump_ct) {
        reasons.push(reason("implausible_downward_jump",
          "Preis liegt zu weit unter dem letzten Pre-Noon-Anker.",
          {delta_ct:Number(deltaCt.toFixed(1)),maximum_ct:p.max_downward_jump_ct,
           anchor_source:anchor.source,anchor_timestamp:anchor.timestamp}));
      }
    }
  }
  return {
    accepted:reasons.length===0, capture_type:captureType, captured_at:iso, policy:p,
    anchors:anchors.map(({minute,...anchor})=>anchor), reasons
  };
}

function rejectCapture(assessment, observation) {
  const rejection={
    version:1,status:"rejected",capture_type:assessment.capture_type,
    date:today,attempted_at:iso,
    target_time:assessment.policy.target_time,reasons:assessment.reasons,
    anchors:assessment.anchors,attempted_observation:observation
  };
  const rejected=readJsonLines(rejectionsPath); rejected.push(rejection);
  writeJsonLines(rejectionsPath,rejected);
  if (assessment.capture_type!=="pre_noon") {
    fm.writeString(noonStatusPath, JSON.stringify(rejection,null,2)+"\n");
    return;
  }
  const recovery={
    version:1,status:"pending_verified_historical_lookup",date:today,
    target_time:assessment.policy.target_time,created_at:iso,
    reasons:assessment.reasons,anchors:assessment.anchors,
    recovery_rules:[
      "Do not write a current live price after the capture window.",
      "Use only event-level historical prices timestamped at or before the local target time, or an already stored local target-time snapshot.",
      "Do not promote tankzeit noon data or an untimestamped web value to 11:50 ground truth.",
      "Leave the observation missing when no verified target-time value exists."
    ]
  };
  fm.writeString(recoveryPath, JSON.stringify(recovery,null,2)+"\n");
  fm.writeString(statusPath, JSON.stringify(rejection,null,2)+"\n");
}

function addDays(day, count) {
  const value=new Date(`${day}T12:00:00`);
  value.setDate(value.getDate()+count);
  return df.string(value);
}

function rowsByDate(values) {
  const out={};
  for (const row of values) {
    if (row.date && row.metrics?.cheap_reference!=null) out[row.date]=row;
  }
  return out;
}

function estimateNextPreNoonOffset(beforeDate) {
  const resets=rowsByDate(noonRows), observations=rowsByDate(observationRows);
  const offsets=[];
  for (const issueDate of Object.keys(resets).sort()) {
    if (issueDate>=beforeDate) continue;
    const targetDate=addDays(issueDate,1);
    if (!observations[targetDate]) continue;
    const offset=(Number(observations[targetDate].metrics.cheap_reference)-
      Number(resets[issueDate].metrics.cheap_reference))*100;
    if (offset>=-30 && offset<=10) offsets.push(offset);
  }
  const recent=offsets.slice(-30), sampleMedian=median(recent);
  const learnedWeight=Math.min(1,recent.length/8);
  const estimate=sampleMedian==null ? -4.0 :
    (1-learnedWeight)*-4.0+learnedWeight*sampleMedian;
  const errors=recent.map(value=>Math.abs(value-estimate));
  return {
    version:1, method:"prior_blended_rolling_median",
    offset_ct:Number(estimate.toFixed(2)), prior_offset_ct:-4.0,
    samples:recent.length,
    sample_median_ct:sampleMedian==null ? null : Number(sampleMedian.toFixed(2)),
    mae_ct:errors.length ? Number((errors.reduce((a,b)=>a+b,0)/errors.length).toFixed(2)) : null
  };
}

function writeNoonShadow(noonObservation) {
  const issueDate=noonObservation.date, targetDate=addDays(issueDate,1);
  const model=estimateNextPreNoonOffset(issueDate);
  const noonReference=Number(noonObservation.metrics.cheap_reference);
  const noonProjection=noonReference+model.offset_ct/100;
  let forecast={};
  if (fm.fileExists(forecastPath)) {
    try { forecast=JSON.parse(fm.readString(forecastPath)); } catch(e) {}
  }
  const base=forecast.date===issueDate
    ? (forecast.forecast || []).find(row=>row.date===targetDate && row.price!=null)
    : null;
  const basePrice=base ? Number(base.price) : null;
  const weight=Math.min(0.65,0.15+0.05*model.samples);
  let correction=null, shadowPrice=noonProjection;
  if (basePrice!=null) {
    correction=Math.max(-8,Math.min(8,(noonProjection-basePrice)*100*weight));
    shadowPrice=basePrice+correction/100;
  }
  const shadow={
    version:1,status:"shadow_only",issue_date:issueDate,target_date:targetDate,
    generated_at:noonObservation.captured_at,source_capture:"noon_reset",
    noon_reference:Number(noonReference.toFixed(3)),
    pre_noon_reference:noonObservation.pre_noon_reference,
    reset_jump_ct:noonObservation.reset_jump_ct,
    base_morning_price:basePrice==null ? null : Number(basePrice.toFixed(3)),
    noon_projection_price:Number(noonProjection.toFixed(3)),
    shadow_revised_price:Number(shadowPrice.toFixed(3)),
    shadow_correction_ct:correction==null ? null : Number(correction.toFixed(1)),
    shadow_weight:Number(weight.toFixed(2)),model,
    production_effect:"none_until_validated"
  };
  fm.writeString(noonShadowPath,JSON.stringify(shadow,null,2)+"\n");
  let history=readJsonLines(noonShadowHistoryPath)
    .filter(row=>row.issue_date!==issueDate);
  history.push(shadow); history.sort((a,b)=>a.issue_date.localeCompare(b.issue_date));
  writeJsonLines(noonShadowHistoryPath,history);
  const correctionText=correction==null ? "keine Morgenbasis" : `${correction>=0?"+":""}${correction.toFixed(1)} ct`;
  console.log(`Shadow D+1 ${targetDate}: ${shadow.shadow_revised_price.toFixed(3)} €/l (${correctionText}, ohne Produktionseffekt)`);
}
