import os
import time
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

BASE_URL = os.environ.get("BASE_URL", "https://iknow.service.hihonor.com/weknow/servlet/download/public")
STATE_DIR = "state"
NEXT_START_FILE = os.path.join(STATE_DIR, "next_start.txt")
CSV_FILE = os.path.join(STATE_DIR, "results.csv")
NEW_CSV = os.path.join(STATE_DIR, "new.csv")

os.makedirs(STATE_DIR, exist_ok=True)

# ---------- 常量 ----------
DEFAULT_START = 0
THRESHOLD_NUM = 65484
MAX_CONSECUTIVE = 233
MAX_ENTRIES_PER_RUN = 3250

# ---------- 读取起始编号 ----------
if os.path.exists(NEXT_START_FILE):
    with open(NEXT_START_FILE, 'r') as f:
        content = f.read().strip()
        start_num = int(content) if content.isdigit() else DEFAULT_START
else:
    start_num = DEFAULT_START

# ---------- 初始化 CSV ----------
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w') as f:
        f.write("WValue,ResourceOrStatus\n")
with open(NEW_CSV, 'w') as f:
    f.write("WValue,ResourceOrStatus\n")

# ---------- 扫描循环 ----------
current_num = start_num
consecutive_invalid = 0
checked = 0

print(f"Starting from W{current_num:08d}")

while checked < MAX_ENTRIES_PER_RUN:
    cur = current_num
    w_value = f"W{cur:08d}"
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

    # 写入 CSV
    line = f"{w_value},{status_or_filename}\n"
    with open(CSV_FILE, 'a') as f_results, open(NEW_CSV, 'a') as f_new:
        f_results.write(line)
        f_new.write(line)

    # 更新连续无效计数
    if is_valid:
        print(f"  -> VALID: {status_or_filename}")
        consecutive_invalid = 0
    else:
        consecutive_invalid += 1
        print(f"  -> INVALID ({status_or_filename}), consecutive: {consecutive_invalid}")

    # ---------- 检查是否触发 233 停止（仅当已超过阈值） ----------
    if cur > THRESHOLD_NUM and consecutive_invalid >= MAX_CONSECUTIVE:
        print(f"Reached {MAX_CONSECUTIVE} consecutive invalid after threshold. Stopping.")
        break

    # 移动到下一个编号
    current_num += 1
    checked += 1
    time.sleep(0.1)

# ---------- 确定停止原因和下一次起始点 ----------
if checked == MAX_ENTRIES_PER_RUN:
    # 达到条目上限 → 继续推进
    next_start = current_num   # 已递增，指向下一个未检查编号
    should_continue = True
    reason = "max_entries"
else:
    # 因 233 连续无效停止（此时 current_num 未递增，指向无效段第一个编号）
    next_start = current_num
    should_continue = False
    reason = "consecutive_invalid"

# 保存状态
with open(NEXT_START_FILE, 'w') as f:
    f.write(str(next_start))

# 向 GitHub Actions 输出标志
github_output = os.environ.get('GITHUB_OUTPUT')
if github_output:
    with open(github_output, 'a') as f:
        f.write(f"should_continue={str(should_continue).lower()}\n")

print(f"Stopped. Reason: {reason}, checked {checked} entries.")
print(f"Next start will be: W{next_start:08d}")
print(f"should_continue={should_continue}")