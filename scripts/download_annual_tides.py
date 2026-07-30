#!/usr/bin/env python3
"""
年度潮汐資料下載腳本
資料來源：中央氣象署 F-A0023-001（明年高低潮時潮高預報）

注意事項：
1. F-A0023-001 是 rawData 類型，不是 REST API，需要登入 CWA 開放資料平台下載
2. 每年10月才會提供明年的資料
3. 下載後手動執行本腳本，將資料轉換為各 地區 JSON 檔

使用方式：
  1. 先到 https://opendata.cwa.gov.tw/dataset/forecast/F-A0023-001 登入下載 CSV/JSON
  2. 將下載的檔案放到 data/ 目錄下
  3. 執行: python3 scripts/download_annual_tides.py

如果無法下載 F-A0023-001，本腳本也可以用 F-A0021-001 API（近一個月）產生 fallback 資料：
  python3 scripts/download_annual_tides.py --fallback
"""

import os
import sys
import json
import argparse

# 加入專案根目錄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# 地點對應表（從 app.py 載入）
from app import LOCATIONS, CWA_API_KEY, fetch_tide_data


def download_via_api():
    """使用 F-A0021-001 API 下載近一個月資料作為 fallback"""
    import requests

    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    for key, info in LOCATIONS.items():
        print(f"下載 {info['label']} ({info['tide_name']})...")
        all_data, err = fetch_tide_data(info["tide_name"])
        if err:
            print(f"  ❌ 錯誤: {err}")
            continue

        output = {
            "source": "api",
            "source_desc": "F-A0021-001 近一個月潮汐預報（fallback）",
            "location": info["label"],
            "tide_name": info["tide_name"],
            "tides": all_data,
        }

        out_file = os.path.join(data_dir, f"annual_{key}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  ✓ 儲存 {len(all_data)} 筆 → {out_file}")


def convert_raw_file(raw_filepath):
    """將 CWA 下載的 rawData 轉換為各地區 JSON

    預期的 CSV/JSON 格式：
    - locationName: 測站名稱
    - stationID: 測站ID
    - obsTime: 觀測時間 (YYYY-MM-DDTHH:MM:SS+08:00)
    - elementName: 潮高（當地）/ 潮高（相對海圖）/ 潮高(TWVD) / 高低潮

    或 JSON 結構：
    records.TideForecasts[].Location.TimePeriods.Daily[]
    """
    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)

    with open(raw_filepath, "r", encoding="utf-8") as f:
        raw = json.load(f) if raw_filepath.endswith(".json") else None

    if raw is None and raw_filepath.endswith(".csv"):
        import csv
        raw = []
        with open(raw_filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw.append(row)

    # 嘗試 JSON 格式（與 F-A0021-001 類似的結構）
    if isinstance(raw, dict):
        # F-A0023-001 格式：cwaopendata.Resources.Resource.Data.TideForecasts.Location[]
        cwa = raw.get("cwaopendata", raw)
        resource = cwa.get("Resources", {}).get("Resource", {})
        tide_forecasts = None
        if "Data" in resource:
            tide_forecasts = resource["Data"].get("TideForecasts", {})
            loc_list = tide_forecasts.get("Location", [])
        elif "TideForecasts" in cwa.get("records", {}):
            # F-A0021-001 REST API 格式
            loc_list = cwa["records"]["TideForecasts"]
        else:
            loc_list = []

        for loc in loc_list:
            loc_name = loc.get("LocationName", "") or loc.get("StationName", "")
            loc_id = loc.get("LocationId", "") or loc.get("StationID", "")

            # 找到對應的地點 key（先比 LocationName，再比 StationName）
            matched_key = None
            for k, info in LOCATIONS.items():
                if info["tide_name"] == loc_name:
                    matched_key = k
                    break
            # F-A0023-001 使用 StationName，需用 StationID 對應
            STATION_MAP = {
                "淡水": "11006", "貢寮": "1826", "壯圍": "1236", "蘆竹": "1116",
                "香山": "112", "芳苑": "1456", "布袋": "1166", "將軍": "1176",
                "永安": "1786", "東港": "1186", "臺東": "1586", "花蓮": "1256",
                "馬公": "1356", "金城": "1966", "東引": "1926",
            }
            if not matched_key:
                for k, sid in STATION_MAP.items():
                    if str(loc_id) == sid:
                        matched_key = k
                        break

            if not matched_key:
                print(f"  ⚠ 跳過未匹配的地點: {loc_name}")
                continue

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
                    hour = int(dt[11:13]) if len(dt) >= 13 else 12
                    results.append({
                        "date": date,
                        "lunar": lunar,
                        "tide_range": tide_range,
                        "datetime": dt,
                        "time": dt[11:16] if len(dt) >= 16 else "",
                        "tide_type": tide_type,
                        "height_above_msl": heights.get("AboveLocalMSL", ""),
                        "height_above_chart": heights.get("AboveChartDatum", ""),
                        "is_daytime": 6 <= hour < 18,
                    })

            output = {
                "source": "local",
                "source_desc": "F-A0023-001 年度潮汐預報",
                "location": LOCATIONS[matched_key]["label"],
                "tide_name": loc_name,
                "tides": results,
            }

            out_file = os.path.join(data_dir, f"annual_{matched_key}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"  ✓ {loc_name}: {len(results)} 筆 → {out_file}")

    elif isinstance(raw, list):
        # CSV 格式處理
        print("CSV 格式轉換功能需要手動對應欄位，請參考 JSON 格式。")
        print(f"共有 {len(raw)} 行 CSV 資料")
        print("請確認 CSV 欄位後手動調整 convert_raw_file() 函數")
    else:
        print("無法識別的檔案格式")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="年度潮汐資料下載腳本")
    parser.add_argument("--fallback", action="store_true",
                        help="使用 F-A0021-001 API 下載近一個月資料作為 fallback")
    parser.add_argument("--file", type=str,
                        help="轉換 CWA 下載的 rawData JSON 檔案")
    args = parser.parse_args()

    if args.file:
        print(f"轉換檔案: {args.file}")
        convert_raw_file(args.file)
    elif args.fallback:
        print("使用 F-A0021-001 API 下載近一個月資料...")
        download_via_api()
    else:
        parser.print_help()
        print()
        print("使用方式：")
        print("  1. Fallback 模式（用近一個月 API 資料）:")
        print("     python3 scripts/download_annual_tides.py --fallback")
        print("  2. 轉換 CWA 下載的 rawData 檔案:")
        print("     python3 scripts/download_annual_tides.py --file data/raw_F-A0023-001.json")