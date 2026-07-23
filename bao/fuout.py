import sys
import os
import time
import subprocess

RUN_TIME = 270      # 4分30秒
CHECK_INTERVAL = 0.02

s = ""

start_time = time.time()

while time.time() - start_time < RUN_TIME:

    # 启动 final.py（保持原路径）
    proc = subprocess.Popen([r"D:\radioconda\envs\gnuradio\python.exe", "final.py"])

    try:
        # 固定等待1秒
        remaining = RUN_TIME - (time.time() - start_time)
        time.sleep(min(1.0, remaining))

        # 如果1.txt存在，则读取
        if os.path.exists("1.txt"):
            try:
                with open("1.txt", "r", encoding="utf-8") as f:
                    data = f.read()

                s += data

                print(f"收到一次数据，长度 {len(data)}")

                os.remove("1.txt")

            except Exception as e:
                print("读取1.txt失败：", e)

    finally:
        # 结束 final.py 
        if proc.poll() is None:
            proc.terminate()

            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

# 保存最终结果
with open("2.txt", "w", encoding="utf-8") as f:
    f.write(s)

print("完成，共接收 {} 字符".format(len(s)))