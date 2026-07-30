#!/usr/bin/env python3
"""
潮汐查詢網站 — Vercel Serverless Function
資料來源：中央氣象署 CWA Open Data API
"""

import os
import sys
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request
from urllib.parse import unquote
import requests

# Vercel serverless: 專案根目錄為 template_folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

CWA_API_KEY = os.environ.get("CWA_API_KEY", "CWA-A25E5E1C-F5B0-4111-81A9-BC3D6E198E25")

# ── 地點對應表 ──────────────────────────────────────────────

LOCATIONS = {
    "淡水": {
        "tide_name": "新北市淡水區",
        "weather_dataset": "F-D0047-071",
        "weather_township": "淡水區",
        "county_name": "新北市",
        "label": "新北 淡水",
    },
    "貢寮": {
        "tide_name": "新北市貢寮區",
        "weather_dataset": "F-D0047-071",
        "weather_township": "貢寮區",
        "county_name": "新北市",
        "label": "新北 貢寮",
    },
    "壯圍": {
        "tide_name": "宜蘭縣壯圍鄉",
        "weather_dataset": "F-D0047-003",
        "weather_township": "壯圍鄉",
        "county_name": "宜蘭縣",
        "label": "宜蘭 壯圍",
    },
    "蘆竹": {
        "tide_name": "桃園市蘆竹區",
        "weather_dataset": "F-D0047-007",
        "weather_township": "蘆竹區",
        "county_name": "桃園市",
        "label": "桃園 蘆竹",
    },
    "香山": {
        "tide_name": "新竹市香山區",
        "weather_dataset": "F-D0047-055",
        "weather_township": "香山區",
        "county_name": "新竹市",
        "label": "新竹 香山",
    },
    "芳苑": {
        "tide_name": "彰化縣芳苑鄉",
        "weather_dataset": "F-D0047-019",
        "weather_township": "芳苑鄉",
        "county_name": "彰化縣",
        "label": "彰化 芳苑",
    },
    "布袋": {
        "tide_name": "嘉義縣布袋鎮",
        "weather_dataset": "F-D0047-031",
        "weather_township": "布袋鎮",
        "county_name": "嘉義縣",
        "label": "嘉義 布袋",
    },
    "將軍": {
        "tide_name": "臺南市將軍區",
        "weather_dataset": "F-D0047-079",
        "weather_township": "將軍區",
        "county_name": "臺南市",
        "label": "台南 將軍",
    },
    "永安": {
        "tide_name": "高雄市永安區",
        "weather_dataset": "F-D0047-067",
        "weather_township": "永安區",
        "county_name": "高雄市",
        "label": "高雄 永安",
    },
    "東港": {
        "tide_name": "屏東縣東港鎮",
        "weather_dataset": "F-D0047-035",
        "weather_township": "東港鎮",
        "county_name": "屏東縣",
        "label": "屏東 東港",
    },
    "臺東": {
        "tide_name": "臺東縣臺東市",
        "weather_dataset": "F-D0047-039",
        "weather_township": "臺東市",
        "county_name": "臺東縣",
        "label": "台東 台東",
    },
    "花蓮": {
        "tide_name": "花蓮縣花蓮市",
        "weather_dataset": "F-D0047-043",
        "weather_township": "花蓮市",
        "county_name": "花蓮縣",
        "label": "花蓮 花蓮",
    },
    "馬公": {
        "tide_name": "澎湖縣馬公市",
        "weather_dataset": "F-D0047-047",
        "weather_township": "馬公市",
        "county_name": "澎湖縣",
        "label": "澎湖 馬公",
    },
    "金城": {
        "tide_name": "金門縣金城鎮",
        "weather_dataset": "F-D0047-087",
        "weather_township": "金城鎮",
        "county_name": "金門縣",
        "label": "金門 金城",
    },
    "東引": {
        "tide_name": "連江縣東引鄉",
        "weather_dataset": "F-D0047-083",
        "weather_township": "東引鄉",
        "county_name": "連江縣",
        "label": "馬祖 東引",
    },
}


def is_daytime(dt_str):
    """06:00-18:00 為白天，其餘為晚上"""
    hour = int(dt_str[11:13])
    return 6 <= hour < 18


# ── API: 潮汐預報（未來1個月）──────────────────────────────

def fetch_tide_data(tide_location_name):
    """從 CWA F-A0021-001 取得未來1個月潮汐資料"""
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"
    params = {
        "Authorization": CWA_API_KEY,
        "LocationName": tide_location_name,
    }
    r = requests.get(url, params=params, timeout=60)
    if r.status_code != 200:
        return None, f"API 錯誤: HTTP {r.status_code}"

    data = r.json()
    records = data.get("records", {})
    tide_forecasts = records.get("TideForecasts", [])

    if not tide_forecasts:
        return None, "查無潮汐資料"

    loc = tide_forecasts[0].get("Location", {})
    daily_list = loc.get("TimePeriods", {}).get("Daily", [])

    results = []
    for day in daily_list:
        date = day.get("Date", "")
        lunar = day.get("LunarDate", "")
        tide_range = day.get("TideRange", "")
        times = day.get("Time", [])
        for t in times:
            dt = t.get("DateTime", "")
            tide_type = t.get("Tide", "")
            heights = t.get("TideHeights", {})
            results.append({
                "date": date,
                "lunar": lunar,
                "tide_range": tide_range,
                "datetime": dt,
                "time": dt[11:16] if len(dt) >= 16 else "",
                "tide_type": tide_type,
                "height_above_msl": heights.get("AboveLocalMSL", ""),
                "height_above_chart": heights.get("AboveChartDatum", ""),
                "is_daytime": is_daytime(dt),
            })

    return results, None


def get_top3_tides(location_key):
    """功能一：未來一個月，每日取較高的滿潮排序找出最高的五天，
    每天列出該日兩個滿潮時段（按時間先後排列）。"""
    info = LOCATIONS[location_key]
    all_data, err = fetch_tide_data(info["tide_name"])
    if err:
        return None, err

    high_tides = [d for d in all_data if d["tide_type"] == "滿潮"]
    if not high_tides:
        return None, "查無滿潮資料"

    daily = {}
    for t in high_tides:
        date = t["date"]
        h = t["height_above_msl"]
        try:
            h_val = int(h)
        except (ValueError, TypeError):
            continue

        if date not in daily:
            daily[date] = {
                "date": date,
                "lunar": t.get("lunar", ""),
                "tide_range": t.get("tide_range", ""),
                "tides": [],
                "max_height": -999,
            }

        entry = {
            "time": t["time"],
            "height": h,
            "height_val": h_val,
        }
        daily[date]["tides"].append(entry)

        if h_val > daily[date]["max_height"]:
            daily[date]["max_height"] = h_val

    for d in daily.values():
        d["tides"].sort(key=lambda x: x["time"])

    sorted_days = sorted(daily.values(), key=lambda x: x["max_height"], reverse=True)
    top4 = sorted_days[:5]
    top4 = sorted(top4, key=lambda x: x["date"])

    return {
        "location": info["label"],
        "top4": top4,
    }, None


def get_tide_detail(location_key, days=7):
    """功能二：未來 N 天的每日滿潮/乾潮時間"""
    info = LOCATIONS[location_key]
    all_data, err = fetch_tide_data(info["tide_name"])
    if err:
        return None, err

    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    filtered = []
    for d in all_data:
        if today <= d["date"] <= end_date:
            filtered.append(d)

    daily = {}
    for d in filtered:
        date = d["date"]
        if date not in daily:
            daily[date] = {
                "date": date,
                "lunar": d["lunar"],
                "tide_range": d["tide_range"],
                "tides": [],
            }
        daily[date]["tides"].append({
            "time": d["time"],
            "tide_type": d["tide_type"],
            "height": d["height_above_msl"],
            "is_daytime": d["is_daytime"],
        })

    sorted_daily = sorted(daily.values(), key=lambda x: x["date"])
    return {
        "location": info["label"],
        "days": sorted_daily,
    }, None


# ── API: 天氣預報（未來1週）──────────────────────────────────

def fetch_weather_data(location_key):
    """從 CWA 鄉鎮天氣預報 API 取得未來1週天氣"""
    info = LOCATIONS[location_key]
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{info['weather_dataset']}"
    params = {
        "Authorization": CWA_API_KEY,
        "LocationName": info["weather_township"],
    }
    r = requests.get(url, params=params, timeout=60)
    if r.status_code != 200:
        return None, f"天氣 API 錯誤: HTTP {r.status_code}"

    data = r.json()
    records = data.get("records", {})
    locations = records.get("Locations", [])

    if not locations:
        return None, "查無天氣資料"

    inner = locations[0].get("Location", [])
    if not inner:
        return None, "查無鄉鎮天氣資料"

    loc = inner[0]
    we_list = loc.get("WeatherElement", [])

    elem_map = {}
    for elem in we_list:
        name = elem.get("ElementName", "")
        elem_map[name] = elem.get("Time", [])

    weather_by_time = {}

    # 天氣現象
    for t in elem_map.get("天氣現象", []):
        start = t.get("StartTime", "")
        end = t.get("EndTime", "")
        ev = t.get("ElementValue", [])
        wx = ev[0].get("Weather", "") if ev else ""
        key = f"{start}|{end}"
        if key not in weather_by_time:
            weather_by_time[key] = {"start": start, "end": end}
        weather_by_time[key]["wx"] = wx

    # 降雨機率
    for t in elem_map.get("12小時降雨機率", []):
        start = t.get("StartTime", "")
        end = t.get("EndTime", "")
        ev = t.get("ElementValue", [])
        pop = ev[0].get("ProbabilityOfPrecipitation", "") if ev else ""
        key = f"{start}|{end}"
        if key not in weather_by_time:
            weather_by_time[key] = {"start": start, "end": end}
        weather_by_time[key]["pop"] = pop

    # 平均溫度
    for t in elem_map.get("平均溫度", []):
        start = t.get("StartTime", "")
        end = t.get("EndTime", "")
        ev = t.get("ElementValue", [])
        temp = ev[0].get("Temperature", "") if ev else ""
        key = f"{start}|{end}"
        if key not in weather_by_time:
            weather_by_time[key] = {"start": start, "end": end}
        weather_by_time[key]["temp"] = temp

    # 風速
    for t in elem_map.get("風速", []):
        start = t.get("StartTime", "")
        end = t.get("EndTime", "")
        ev = t.get("ElementValue", [])
        ws = ev[0].get("WindSpeed", "") if ev else ""
        bs = ev[0].get("BeaufortScale", "") if ev else ""
        key = f"{start}|{end}"
        if key not in weather_by_time:
            weather_by_time[key] = {"start": start, "end": end}
        weather_by_time[key]["wind_speed"] = ws
        weather_by_time[key]["beaufort"] = bs

    # 風向
    for t in elem_map.get("風向", []):
        start = t.get("StartTime", "")
        end = t.get("EndTime", "")
        ev = t.get("ElementValue", [])
        wd = ev[0].get("WindDirection", "") if ev else ""
        key = f"{start}|{end}"
        if key not in weather_by_time:
            weather_by_time[key] = {"start": start, "end": end}
        weather_by_time[key]["wind_dir"] = wd

    weather_list = sorted(weather_by_time.values(), key=lambda x: x.get("start", ""))
    return weather_list, None


def get_weather_for_days(location_key, days=7):
    weather_list, err = fetch_weather_data(location_key)
    if err:
        return None, err

    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    filtered = []
    for w in weather_list:
        start = w.get("start", "")
        if start and today <= start[:10] <= end_date:
            hour = int(start[11:13]) if len(start) >= 14 else 12
            w["is_daytime"] = 6 <= hour < 18
            filtered.append(w)

    return filtered, None


# ── API: 日出日落時刻 ─────────────────────────────────────────

def fetch_sunrise_sunset(location_key, days=7):
    """從 CWA A-B0062-001 取得日出日落時刻"""
    info = LOCATIONS[location_key]
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/A-B0062-001"
    params = {
        "Authorization": CWA_API_KEY,
        "CountyName": info["county_name"],
        "timeFrom": today,
        "timeTo": end_date,
    }
    r = requests.get(url, params=params, timeout=60)
    if r.status_code != 200:
        return None, f"日出日落 API 錯誤: HTTP {r.status_code}"

    data = r.json()
    locations = data.get("records", {}).get("locations", {}).get("location", [])
    if not locations:
        return None, "查無日出日落資料"

    times = locations[0].get("time", [])
    result = {}
    for t in times:
        date = t.get("Date", "")
        result[date] = {
            "sunrise": t.get("SunRiseTime", ""),
            "sunset": t.get("SunSetTime", ""),
        }

    return result, None


# ── Flask 路由 ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", locations=LOCATIONS)


@app.route("/api/locations")
def api_locations():
    return jsonify({"locations": {k: v["label"] for k, v in LOCATIONS.items()}})


@app.route("/api/top3-tides/<location_key>")
def api_top3_tides(location_key):
    location_key = unquote(location_key)
    if location_key not in LOCATIONS:
        return jsonify({"error": "未知地點"}), 400
    result, err = get_top3_tides(location_key)
    if err:
        return jsonify({"error": err}), 500
    return jsonify(result)


@app.route("/api/tide-detail/<location_key>")
def api_tide_detail(location_key):
    location_key = unquote(location_key)
    if location_key not in LOCATIONS:
        return jsonify({"error": "未知地點"}), 400
    days = request.args.get("days", 7, type=int)
    if days < 3 or days > 7:
        days = 7
    result, err = get_tide_detail(location_key, days)
    if err:
        return jsonify({"error": err}), 500
    return jsonify(result)


@app.route("/api/weather/<location_key>")
def api_weather(location_key):
    location_key = unquote(location_key)
    if location_key not in LOCATIONS:
        return jsonify({"error": "未知地點"}), 400
    days = request.args.get("days", 7, type=int)
    if days < 3 or days > 7:
        days = 7
    result, err = get_weather_for_days(location_key, days)
    if err:
        return jsonify({"error": err}), 500
    return jsonify({"location": LOCATIONS[location_key]["label"], "weather": result})


@app.route("/api/combined/<location_key>")
def api_combined(location_key):
    location_key = unquote(location_key)
    if location_key not in LOCATIONS:
        return jsonify({"error": "未知地點"}), 400
    days = request.args.get("days", 7, type=int)
    if days < 3 or days > 7:
        days = 7

    tide_data, tide_err = get_tide_detail(location_key, days)
    weather_data, weather_err = get_weather_for_days(location_key, days)
    sun_data, sun_err = fetch_sunrise_sunset(location_key, days)

    result = {
        "location": LOCATIONS[location_key]["label"],
        "days": days,
    }
    if tide_err:
        result["tide_error"] = tide_err
    else:
        result["tide"] = tide_data

    if weather_err:
        result["weather_error"] = weather_err
    else:
        result["weather"] = weather_data

    if sun_err:
        result["sun_error"] = sun_err
    else:
        result["sunrise_sunset"] = sun_data

    return jsonify(result)


# Vercel serverless entry point
app = app