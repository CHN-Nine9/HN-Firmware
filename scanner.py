import os
import time
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

BASE_URL = os.environ.get("BASE_URL", "https://iknow.service.hihonor.com/weknow/servlet/download/public")
STATE_DIR = "state"
BLOCK_START_FILE = os.path.join(STATE_DIR, "block_start.txt")
CSV_FILE = os.path.join(STATE_DIR, "results.csv")
NEW_CSV = os.path.join(STATE_DIR, "new.csv")

os.makedirs(STATE_DIR, exist_ok=True)

# ---------- 初始化起点：从 W00000000 (0) 开始 ----------
DEFAULT_START = 0
if os.path.exists(BLOCK_START_FILE):
    with open(BLOCK_START_FILE, 'r') as f:
        content = f.read().strip()
        # 若文件存在且内容为有效数字则使用，否则回退到 0
        start_num = int(content) if content.isdigit() else DEFAULT_START
else:
    start_num = DEFAULT_START

# ---------- 初始化 CSV 表头 ----------
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w') as f:
        f.write("WValue,ResourceOrStatus\n")

# 清空本次新增文件，写入表头
with open(NEW_CSV, 'w') as f:
    f.write("WValue,ResourceOrStatus\n")

# ---------- 扫描逻辑 ----------
current_num = start_num
consecutive_invalid = 0
MAX_CONSECUTIVE = 233
checked = 0

print(f"Starting from W{current_num:08d}")

while consecutive_invalid < MAX_CONSECUTIVE:
    w_value = f"W{current_num:08d}"
    url = f"{BASE_URL}?contextNo={w_value}"
    print(f"[{checked+1}] Checking: {url}")

    status_or_filename = ""
    is_valid = False

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
            else:
                status_or_filename = str(resp.status)
    except urllib.error.HTTPError as e:
        status_or_filename = str(e.code)
    except Exception as e:
        status_or_filename = f"Error: {type(e).__name__}"

    # 写入 results.csv 和 new.csv
    line = f"{w_value},{status_or_filename}\n"
    with open(CSV_FILE, 'a') as f_results, open(NEW_CSV, 'a') as f_new:
        f_results.write(line)
        f_new.write(line)

    if is_valid:
        print(f"  -> VALID: {status_or_filename}")
        consecutive_invalid = 0
    else:
        consecutive_invalid += 1
        print(f"  -> INVALID ({status_or_filename}), consecutive: {consecutive_invalid}")

    current_num += 1
    checked += 1
    time.sleep(0.1)

# 更新起点为本次连续无效段的第一个数字
new_block_start = current_num - MAX_CONSECUTIVE
with open(BLOCK_START_FILE, 'w') as f:
    f.write(str(new_block_start))

print(f"Stopped. Checked {checked} records.")
print(f"New block start (to retry next run): W{new_block_start:08d}")
