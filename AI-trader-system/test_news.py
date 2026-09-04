import yfinance as yf

def fetch_real_news(ticker_symbol):
    print(f"กำลังดึงข้อมูลข่าวล่าสุดของ {ticker_symbol}...")
    ticker = yf.Ticker(ticker_symbol)
    news_items = ticker.news
    
    if not news_items:
        return "ไม่มีข่าวอัปเดตในช่วงนี้"
    
    headlines = []
    # ดึงมาเช็คทีละข่าว
    for news in news_items:
        # กรณีที่ 1: โครงสร้างแบบเก่า มี 'title' ให้เลย
        if 'title' in news:
            headlines.append(news['title'])
        # กรณีที่ 2: โครงสร้างแบบใหม่ ซ่อนอยู่ใน 'content'
        elif 'content' in news and 'title' in news['content']:
            headlines.append(news['content']['title'])
            
        # ถ้าได้ครบ 3 ข่าวแล้วให้หยุดดึง
        if len(headlines) == 3:
            break
            
    # กรณีดึงมาแล้วหาพาดหัวไม่เจอเลย (เผื่อ Yahoo เปลี่ยนโครงสร้างแปลกๆ อีก)
    if not headlines:
        print("\n[Debug] โครงสร้างข้อมูลที่ได้มาหน้าตาแบบนี้ครับ:")
        print(news_items[0])
        return "ดึงข้อมูลสำเร็จ แต่หาพาดหัวข่าวไม่เจอ"
        
    combined_news = " | ".join(headlines)
    return combined_news

# ทดสอบดึงข่าว
real_news = fetch_real_news("NVDA")
print(f"\nพาดหัวข่าวที่ดึงมาได้:\n{real_news}")