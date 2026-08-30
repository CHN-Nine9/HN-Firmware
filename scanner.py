import os
import time
import re
import urllib.request
import urllib.error
import csv
import json
import xml.etree.ElementTree as ET
import xml.dom.minidom
from urllib.parse import urlparse

BASE_URL = os.environ.get("BASE_URL", "https://iknow.service.hihonor.com/weknow/servlet/download/public")
STATE_DIR = "state"
NEXT_START_FILE = os.path.join(STATE_DIR, "next_start.txt")

# 4个用于底层状态缓存的2列CSV文件路径
CSV_ALL = os.path.join(STATE_DIR, "results.csv")
CSV_VALID_ALL = os.path.join(STATE_DIR, "valid_results.csv")
CSV_NEW = os.path.join(STATE_DIR, "new.csv")
CSV_VALID_NEW = os.path.join(STATE_DIR, "valid_new.csv")

os.makedirs(STATE_DIR, exist_ok=True)

DEFAULT_START = 0
THRESHOLD_NUM = 65550
MAX_CONSECUTIVE = 233
MAX_ENTRIES_PER_RUN = 3250
MAX_RETRIES = 3

if os.path.exists(NEXT_START_FILE):
    with open(NEXT_START_FILE, 'r') as f:
        content = f.read().strip()
        start_num = int(content) if content.isdigit() else DEFAULT_START
else:
    start_num = DEFAULT_START

def init_csv(filepath):
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("WID,FileName\n")

init_csv(CSV_ALL)
init_csv(CSV_VALID_ALL)

with open(CSV_NEW, 'w', encoding='utf-8') as f:
    f.write("WID,FileName\n")
with open(CSV_VALID_NEW, 'w', encoding='utf-8') as f:
    f.write("WID,FileName\n")

current_num = start_num
consecutive_invalid = 0
checked = 0

print(f"Starting from W{current_num:08d}")

while checked < MAX_ENTRIES_PER_RUN:
    cur = current_num
    w_value = f"W{cur:08d}"
    url = f"{BASE_URL}?contextNo={w_value}"
    
    is_valid = False
    status_or_filename = ""

    # 网络重试机制
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    is_valid = True
                    content_disp = resp.headers.get('Content-Disposition')
                    if content_disp:
                        match = re.search(r'filename="?([^";]+)"?', content_disp)
                        if match:
                            status_or_filename = match.group(1)
                    if not status_or_filename:
                        parsed = urlparse(url)
                        status_or_filename = parsed.path.split('/')[-1] or "unknown"
                    break
                else:
                    status_or_filename = str(resp.status)
        except urllib.error.HTTPError as e:
            status_or_filename = str(e.code)
        except Exception as e:
            status_or_filename = f"Error: {type(e).__name__}"
            
        if not is_valid and attempt < MAX_RETRIES - 1:
            time.sleep(1)

    print(f"[{checked+1}] {w_value} -> {status_or_filename} (Valid: {is_valid})")

    line = f"{w_value},{status_or_filename}\n"
    
    with open(CSV_ALL, 'a', encoding='utf-8') as f_all, open(CSV_NEW, 'a', encoding='utf-8') as f_new:
        f_all.write(line)
        f_new.write(line)

    if is_valid:
        with open(CSV_VALID_ALL, 'a', encoding='utf-8') as fv_all, open(CSV_VALID_NEW, 'a', encoding='utf-8') as fv_new:
            fv_all.write(line)
            fv_new.write(line)
        consecutive_invalid = 0
    else:
        consecutive_invalid += 1

    if cur > THRESHOLD_NUM and consecutive_invalid >= MAX_CONSECUTIVE:
        print(f"Reached {MAX_CONSECUTIVE} consecutive invalid after threshold. Stopping.")
        # 将游标回滚到这 233 个无效链接的第一个位置
        current_num = cur - MAX_CONSECUTIVE + 1
        break

    current_num += 1
    checked += 1
    time.sleep(0.1)

if checked == MAX_ENTRIES_PER_RUN:
    next_start = current_num
    should_continue = True
else:
    next_start = current_num
    should_continue = False

with open(NEXT_START_FILE, 'w') as f:
    f.write(str(next_start))

github_output = os.environ.get('GITHUB_OUTPUT')
if github_output:
    with open(github_output, 'a') as f:
        f.write(f"should_continue={str(should_continue).lower()}\n")

# ---------- 格式转换 (生成带URL的CSV, JSON, XML) ----------
def generate_formats(csv_path, output_base_name):
    if not os.path.exists(csv_path): return
    json_list = []
    xml_root = ET.Element("Records")
    
    enriched_csv_path = os.path.join(STATE_DIR, f"{output_base_name}_with_url.csv")
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # 使用 csv.writer 安全写入
    with open(enriched_csv_path, 'w', encoding='utf-8', newline='') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["WID", "FileName", "URL"]) # 写入表头
        
        for line in lines[1:]:
            line = line.strip()
            if not line: continue
            
            # 依然用 split(',', 1) 安全读取旧缓存，因为旧缓存只有两列
            parts = line.split(',', 1)
            wid = parts[0]
            filename = parts[1] if len(parts) > 1 else ""
            url = f"{BASE_URL}?contextNo={wid}"
            
            # 使用 csv.writer 写入，它会自动把带有逗号的 filename 用双引号包裹
            writer.writerow([wid, filename, url])
            
            json_list.append({"WID": wid, "FileName": filename, "URL": url})
            
            # 提取纯数字 ID (去掉 'W' 并去除前导零，例如 W00065550 -> 65550)
            numeric_id = str(int(wid[1:]))
            
            # 创建带有 id 属性的 Record 节点
            record = ET.SubElement(xml_root, "Record", id=numeric_id)
            ET.SubElement(record, "WID").text = wid
            ET.SubElement(record, "FileName").text = filename
            ET.SubElement(record, "URL").text = url
            
    with open(os.path.join(STATE_DIR, f"{output_base_name}.json"), 'w', encoding='utf-8') as f:
        json.dump(json_list, f, indent=2, ensure_ascii=False)
        
    xml_str = xml.dom.minidom.parseString(ET.tostring(xml_root)).toprettyxml(indent="  ")
    with open(os.path.join(STATE_DIR, f"{output_base_name}.xml"), 'w', encoding='utf-8') as f:
        f.write(xml_str)
print("Generating output formats (CSV+URL, JSON, XML)...")
generate_formats(CSV_ALL, "results_all")
generate_formats(CSV_VALID_ALL, "valid_all")
generate_formats(CSV_NEW, "results_new")
generate_formats(CSV_VALID_NEW, "valid_new")

print(f"Stopped. checked {checked} entries. Next start: W{next_start:08d}")
