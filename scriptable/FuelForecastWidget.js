// Variables used by Scriptable.
// icon-color: deep-blue; icon-glyph: gas-pump;
// FuelForecast medium widget: live cheapest station + 5-day model forecast.

const fm = FileManager.iCloud();
const root = fm.joinPath(fm.documentsDirectory(), "FuelForecast");
const memory = fm.joinPath(root, "memory");
const configPath = fm.joinPath(memory, "config.json");
const forecastPath = fm.joinPath(memory, "forecast.json");

await download(configPath); await download(forecastPath);
if (!fm.fileExists(configPath)) throw new Error("FuelForecast/memory/config.json fehlt.");
const cfg=JSON.parse(fm.readString(configPath));
const forecast=fm.fileExists(forecastPath) ? JSON.parse(fm.readString(forecastPath)) : null;

let location;
if (cfg.widget?.use_current_location !== false) {
  Location.setAccuracyToKilometer();
  location = await Location.current();
} else {
  location = { latitude: cfg.region.center.lat, longitude: cfg.region.center.lng };
}
const rad=cfg.widget?.radius_km || 5;
const key=cfg.tankerkoenig_api_key;
const fuel=cfg.fuel || "diesel";
const url=`https://creativecommons.tankerkoenig.de/json/list.php?lat=${location.latitude.toFixed(5)}&lng=${location.longitude.toFixed(5)}&rad=${rad}&sort=price&type=${fuel}&apikey=${encodeURIComponent(key)}`;
let live=null;
try {
  const data=await new Request(url).loadJSON();
  if (data.ok) live=(data.stations||[]).filter(s=>s.isOpen && s.price!=null).sort((a,b)=>a.price-b.price)[0] || null;
} catch(e) {}

const w=new ListWidget();
w.refreshAfterDate = new Date(Date.now()+15*60*1000);

const header=w.addStack(); header.centerAlignContent();
let title=header.addText("Diesel OHV"); title.font=Font.boldSystemFont(15);
header.addSpacer();
let rec=header.addText(forecast?.recommendation_de || "…");
rec.font=Font.boldSystemFont(12);
if (forecast?.recommendation==="WAIT") rec.textColor=Color.blue();
else if (forecast?.recommendation==="TANK_TODAY") rec.textColor=Color.green();

w.addSpacer(5);
if (live) {
  const row=w.addStack(); row.centerAlignContent();
  let price=row.addText(`${Number(live.price).toFixed(3)} €`);
  price.font=Font.boldSystemFont(25);
  row.addSpacer(8);
  let station=row.addText(`${live.brand || live.name}\n${live.place} · ${live.dist} km`);
  station.font=Font.systemFont(10); station.textColor=Color.gray();
  station.minimumScaleFactor=0.7;
  w.url = `http://maps.apple.com/?q=${live.lat},${live.lng}`;
} else {
  let t=w.addText("Livepreis nicht verfügbar"); t.font=Font.systemFont(11); t.textColor=Color.gray();
}

w.addSpacer(6);
if (forecast?.forecast?.length) {
  const grid=w.addStack(); grid.layoutHorizontally();
  for (const f of forecast.forecast.slice(0,5)) {
    const col=grid.addStack(); col.layoutVertically(); col.centerAlignContent();
    const d=new Date(f.date+"T12:00:00");
    const day=["So","Mo","Di","Mi","Do","Fr","Sa"][d.getDay()];
    let a=col.addText(day); a.font=Font.mediumSystemFont(9); a.textColor=Color.gray();
    let b=col.addText(Number(f.price).toFixed(3)); b.font=Font.boldSystemFont(11);
    let c=col.addText(`${Number(f.delta_ct)>=0?"+":""}${Number(f.delta_ct).toFixed(1)}ct`);
    c.font=Font.systemFont(8); c.textColor=Color.gray();
    if (f !== forecast.forecast.slice(0,5)[forecast.forecast.slice(0,5).length - 1]) grid.addSpacer();
  }
  w.addSpacer(4);
  let foot=w.addText(`Bester Tag: ${forecast.best_day} (${forecast.best_advantage_ct>0?"+":""}${forecast.best_advantage_ct} ct) · Tankerkönig/MTS-K`);
  foot.font=Font.systemFont(8); foot.textColor=Color.gray(); foot.minimumScaleFactor=0.7;
} else {
  let t=w.addText("Noch keine Prognose. Morgendlichen Minis-Task ausführen.");
  t.font=Font.systemFont(10); t.textColor=Color.gray();
}

if (!config.runsInWidget) await w.presentMedium();
Script.setWidget(w);
Script.complete();

async function download(path) {
  if (fm.fileExists(path) && fm.isFileStoredIniCloud(path)) {
    try { await fm.downloadFileFromiCloud(path); } catch(e) {}
  }
}
