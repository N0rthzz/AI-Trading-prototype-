import yfinance as yf
import pandas as pd
import pandas_ta as ta

def get_technical_data(ticker_symbol):
    print(f"📊 กำลังดึงข้อมูลราคาย้อนหลัง และคำนวณกราฟเทคนิคของ {ticker_symbol}...")
    
    # ดึงข้อมูลราคาย้อนหลัง 3 เดือน
    ticker = yf.Ticker(ticker_symbol)
    df = ticker.history(period="3mo")
    
    if df.empty:
        return "ไม่พบข้อมูลราคาหุ้น"

    # คำนวณ RSI (14) ด้วย pandas_ta (มันจะเพิ่มคอลัมน์ 'RSI_14' ให้อัตโนมัติ)
    df.ta.rsi(length=14, append=True)
    
    # คำนวณแนวรับ-แนวต้าน แบบง่ายๆ โดยใช้จุดต่ำสุด-สูงสุด ในรอบ 20 วันล่าสุด
    last_20_days = df.tail(20)
    support = last_20_days['Low'].min()
    resistance = last_20_days['High'].max()
    
    # ดึงข้อมูลวันล่าสุดที่ตลาดเปิด
    latest = df.iloc[-1]
    
    # สรุปข้อมูล
    tech_summary = (
        f"ราคาปัจจุบัน: ${latest['Close']:.2f}\n"
        f"RSI (14): {latest['RSI_14']:.2f}\n"
        f"แนวรับ (20 วัน): ${support:.2f}\n"
        f"แนวต้าน (20 วัน): ${resistance:.2f}"
    )
    
    return tech_summary

# ทดสอบรันข้อมูลของ NVIDIA
if __name__ == "__main__":
    result = get_technical_data("NVDA")
    print("\n[สรุปข้อมูล Technical]")
    print(result)