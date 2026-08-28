// Variables used by Scriptable.
// icon-color: cyan; icon-glyph: gas-pump;
// FuelForecast 11:50 learning capture.
// Reads iCloud Drive/Scriptable/FuelForecast/memory/config.json

const fm = FileManager.iCloud();
const root = fm.joinPath(fm.documentsDirectory(), "FuelForecast");
const memory = fm.joinPath(root, "memory");
const configPath = fm.joinPath(memory, "config.json");
const observationsPath = fm.joinPath(memory, "observations.jsonl");

if (!fm.fileExists(root)) fm.createDirectory(root, true);
if (!fm.fileExists(memory)) fm.createDirectory(memory, true);
await ensureDownloaded(configPath);
if (!fm.fileExists(configPath)) throw new Error("FuelForecast/memory/config.json fehlt.");

const cfg = JSON.parse(fm.readString(configPath));
const c = cfg.region.center;
const radius = cfg.region.radius_km || 25;
const fuel = cfg.fuel || "diesel";
const key = cfg.tankerkoenig_api_key;
if (!key || key.startsWith("PASTE_")) throw new Error("Tankerkönig API Key in config.json eintragen.");

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

const now = new Date();
const df = new DateFormatter(); df.dateFormat = "yyyy-MM-dd";
const iso = now.toISOString();
const observation = {
  version: 1,
  date: df.string(now),
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

// Idempotent daily write: replace today's line if automation is run twice.
let rows=[];
if (fm.fileExists(observationsPath)) {
  await ensureDownloaded(observationsPath);
  rows=fm.readString(observationsPath).split("\n").filter(Boolean)
    .map(x=>{ try{return JSON.parse(x)}catch(e){return null} }).filter(Boolean)
    .filter(x=>x.date !== observation.date);
}
rows.push(observation);
rows.sort((a,b)=>a.date.localeCompare(b.date));
fm.writeString(observationsPath, rows.map(x=>JSON.stringify(x)).join("\n")+"\n");

console.log(`FuelForecast ${observation.date}: ${observation.metrics.cheap_reference?.toFixed(3)} €/l, ${open.length} offene Stationen`);
Script.complete();

async function ensureDownloaded(path) {
  if (fm.fileExists(path) && fm.isFileStoredIniCloud(path)) {
    try { await fm.downloadFileFromiCloud(path); } catch(e) {}
  }
}
