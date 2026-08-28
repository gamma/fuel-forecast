#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from common import pct_change

UA = {"User-Agent": "Mozilla/5.0 FuelForecast/1.0"}

def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def yahoo_series(symbol, range_="1mo", interval="1d"):
    sym = urllib.parse.quote(symbol, safe="")
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{sym}?range={range_}&interval={interval}&includePrePost=false&events=div%2Csplits"
        try:
            j = _get_json(url)
            res = j["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            rows = [(int(t), float(c)) for t, c in zip(ts, closes) if c is not None]
            if rows:
                return rows
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Yahoo market fetch failed for {symbol}: {last_err}")

def yahoo_series_between(symbol, start: date, end: date, interval="1d"):
    """Fetch a bounded Yahoo chart series; end is inclusive for callers."""
    sym = urllib.parse.quote(symbol, safe="")
    period1 = int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), time.min,
                                   tzinfo=timezone.utc).timestamp())
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = (f"https://{host}/v8/finance/chart/{sym}?period1={period1}"
               f"&period2={period2}&interval={interval}&includePrePost=false"
               "&events=div%2Csplits")
        try:
            j = _get_json(url)
            res = j["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
            rows = [(int(t), float(c)) for t, c in zip(ts, closes) if c is not None]
            if rows:
                return rows
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Yahoo historical fetch failed for {symbol}: {last_err}")

def series_features(rows):
    vals = [v for _, v in rows]
    if not vals:
        return {}
    def prior(n):
        return vals[-1-n] if len(vals) > n else None
    return {
        "latest": vals[-1],
        "d1_pct": pct_change(vals[-1], prior(1)),
        "d5_pct": pct_change(vals[-1], prior(5)),
        "d10_pct": pct_change(vals[-1], prior(10)),
        "points": len(vals),
    }

def converted_pct(usd_pct, eurusd_pct):
    """Exact percentage change after converting a USD price to EUR."""
    if usd_pct is None or eurusd_pct is None:
        return None
    fx_factor = 1.0 + float(eurusd_pct) / 100.0
    if fx_factor == 0:
        return None
    return ((1.0 + float(usd_pct) / 100.0) / fx_factor - 1.0) * 100.0

def converted_features(cost, eurusd, divisor=1.0):
    latest_cost = cost.get("latest")
    latest_fx = eurusd.get("latest")
    if latest_cost is None or latest_fx in (None, 0):
        return {}
    out = {
        "latest": float(latest_cost) / float(latest_fx) / divisor,
        "points": min(cost.get("points", 0), eurusd.get("points", 0)),
    }
    for field in ("d1_pct", "d5_pct", "d10_pct"):
        out[field] = converted_pct(cost.get(field), eurusd.get(field))
    return out

def ecb_eurusd():
    # Official ECB 90-day reference rates: USD per EUR.
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        root = ET.parse(r).getroot()
    rows = []
    for daynode in root.iter():
        t = daynode.attrib.get("time")
        if not t:
            continue
        usd = None
        for child in list(daynode):
            if child.attrib.get("currency") == "USD":
                usd = float(child.attrib["rate"])
                break
        if usd is not None:
            rows.append((t, usd))
    rows.sort(key=lambda x:x[0])
    vals = [v for _,v in rows]
    def prior(n): return vals[-1-n] if len(vals) > n else None
    return {
        "latest": vals[-1] if vals else None,
        "d1_pct": pct_change(vals[-1], prior(1)) if vals else None,
        "d5_pct": pct_change(vals[-1], prior(5)) if vals else None,
        "d10_pct": pct_change(vals[-1], prior(10)) if vals else None,
        "points": len(vals),
        "source": "ECB"
    }

def fetch_market(cfg):
    errors = []
    out = {}
    try:
        out["brent"] = series_features(yahoo_series(cfg["market"].get("brent_symbol", "BZ=F")))
        out["brent"]["source"] = "Yahoo Finance futures JSON"
    except Exception as e:
        errors.append(str(e))
        out["brent"] = {}
    try:
        out["distillate"] = series_features(yahoo_series(cfg["market"].get("distillate_symbol", "HO=F")))
        out["distillate"]["source"] = "Yahoo Finance Heating Oil futures proxy"
    except Exception as e:
        errors.append(str(e))
        out["distillate"] = {}
    try:
        out["eurusd"] = ecb_eurusd()
    except Exception as e:
        errors.append("ECB: " + str(e))
        out["eurusd"] = {}
    out["brent_eur"] = converted_features(out["brent"], out["eurusd"])
    if out["brent_eur"]:
        out["brent_eur"]["source"] = "Brent futures converted with ECB EUR/USD"
        out["brent_eur"]["unit"] = "EUR/barrel"
    out["distillate_eur_per_liter"] = converted_features(
        out["distillate"], out["eurusd"], divisor=3.785411784
    )
    if out["distillate_eur_per_liter"]:
        out["distillate_eur_per_liter"]["source"] = (
            "Heating Oil futures proxy converted with ECB EUR/USD"
        )
        out["distillate_eur_per_liter"]["unit"] = "EUR/liter"
    out["errors"] = errors
    out["needs_web_lookup"] = [k for k in ("brent","distillate","eurusd") if not out.get(k,{}).get("latest")]
    return out
