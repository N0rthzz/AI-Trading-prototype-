import schedule
import time
import subprocess

def run_trading_bot():
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚀 เริ่มรันบอท AI Quant ตามรอบเวลา...")
    # สั่งรันไฟล์ trader_bot.py แบบซ่อนอยู่เบื้องหลัง
    subprocess.run(["python", "trader_bot.py"])
    print("✅ วิเคราะห์เสร็จสิ้น รอรอบถัดไป...")

# ตั้งให้รันทุกวันตอน 08:00 น.
schedule.every().day.at("08:00").do(run_trading_bot)

# ถ้าอยากเทสว่าระบบทำงานไหม ให้ปลดคอมเมนต์บรรทัดล่างนี้ (มันจะรันทุกๆ 1 นาทีแทน)
# schedule.every(1).minutes.do(run_trading_bot)

print("⏳ ระบบ Automation เริ่มทำงาน ปล่อยจอนี้ทิ้งไว้ได้เลย...")
while True:
    schedule.run_pending()
    time.sleep(30)