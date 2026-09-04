import asyncio
import sqlite3
import uuid
import nest_asyncio
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import os
from datetime import datetime
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from dotenv import load_dotenv

# คำสั่งนี้จะวิ่งไปหาไฟล์ .env ในโฟลเดอร์เดียวกัน แล้วดูดข้อมูลเตรียมไว้ให้
load_dotenv()
# ==========================================
# 🏦 Execution Engine Imports (Alpaca, Binance, MT5)
# ==========================================
# 1. Alpaca (US Stocks)
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# 2. Binance (Crypto)
import ccxt

# 3. MetaTrader 5 (Forex)
import MetaTrader5 as mt5

def classify_asset(ticker: str) -> str:
    ticker = ticker.upper().strip()
    if ticker in ["XAUUSD", "GOLD"] or "GC=F" in ticker:
        return "GOLD"
    elif ticker in ["BTCUSD", "ETHUSD", "BNBUSD", "SOLUSD"] or "-USD" in ticker:
        return "CRYPTO"
    elif ticker in ["EURUSD", "USDJPY", "JPYUSD", "GBPUSD", "AUDUSD"] or "=X" in ticker:
        return "FOREX"
    else:
        return "STOCK"

# ฟังก์ชันใหม่: ทำหน้าที่แปลงชื่อให้ตรงใจ Yahoo Finance อัตโนมัติ
def get_yf_ticker(ticker: str) -> str:
    ticker = ticker.upper().strip()
    asset_type = classify_asset(ticker)
    
    if asset_type == "GOLD":
        return "GC=F"
    elif asset_type == "CRYPTO" and "-" not in ticker:
        return ticker.replace("USD", "-USD") # แปลง BTCUSD เป็น BTC-USD อัตโนมัติ
    elif asset_type == "FOREX":
        if ticker in ["JPYUSD", "USDJPY"]:
            return "JPY=X" # แปลงเงินเยนเป็นฟอร์แมตมาตรฐาน Yahoo
        elif "=X" not in ticker:
            return f"{ticker}=X" # แปลง EURUSD เป็น EURUSD=X อัตโนมัติ
    return ticker
    
# อนุญาตให้รัน asyncio ในสภาพแวดล้อมต่างๆ ได้อย่างราบรื่น
nest_asyncio.apply()

# ==========================================
# ✈️ ตั้งค่า Telegram Bot
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 1. ดึงค่ามาจาก .env ก่อน
typhoon_api_key = os.getenv("TYPHOON_API_KEY")

# 2. เช็คว่ามีค่าไหม (อยู่นอกวงเล็บ)
if not typhoon_api_key:
    print("⚠️ ไม่พบ TYPHOON_API_KEY ในไฟล์ .env")
    master_reasoning = "System Error: Missing Typhoon API Key."
else:
    # 3. ถ้ามีค่า ค่อยเอามาใส่เพื่อสร้าง Client
    client = AsyncOpenAI(
        api_key=typhoon_api_key,  # ต้องใช้คำว่า api_key= เสมอครับ
        base_url="https://api.opentyphoon.ai/v1"
    )

class AgentResponse(BaseModel):
    score: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

def send_telegram_alert(asset, action, z_score, current_price, master_reasoning):
    import os
    import requests
    
    # 1. ดูดค่าจากไฟล์ .env
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    # 2. เช็คว่ามีค่าไหม ถ้าไม่มีให้ข้ามการส่งไปเลย ระบบจะได้ไม่พัง
    if not bot_token or not chat_id:
        print("⚠️ ข้ามการแจ้งเตือน Telegram: ไม่พบ Token หรือ Chat ID ใน .env")
        return

    # 3. โค้ดส่งข้อความเดิมของคุณ
    message = f"🚨 ได่เวลาลุย!\nAsset: {asset}\nAction: {action} ..."
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    try:
        payload = {"chat_id": chat_id, "text": message}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"❌ ส่ง Telegram ไม่สำเร็จ: {e}")
        
class QuantMultiAgentTrader:
    def __init__(self, db_name="trade_database.db"):
        self.weights = [0.15, 0.15, 0.30, 0.40]
        self.model = "typhoon-v2.5-30b-a3b-instruct"
        self.decision_threshold = 0.60 # ปรับให้เขี้ยวขึ้นตามที่เราคุยกัน
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # ตารางใหม่สำหรับเก็บการตั้งค่าและ API Keys
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS SystemSettings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker_name TEXT,
                api_key TEXT,
                api_secret TEXT,
                trading_mode TEXT, -- 'LIVE' หรือ 'SIGNAL'
                updated_at TEXT
            )
        """)
        # ตารางเก็บผลการเทรด (อันเดิม)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS TradeDecision (
                id TEXT PRIMARY KEY, ticker TEXT, timestamp TEXT,
                macroScore REAL, geoScore REAL, techScore REAL, assetScore REAL,
                masterScore REAL, action TEXT, reasoning TEXT,
                news_data TEXT, tech_data TEXT
            )
        """)
        # 🟢 เพิ่มตารางเก็บ Watchlist (อันใหม่)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Watchlist (
                ticker TEXT PRIMARY KEY,
                added_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def save_to_db(self, broker, asset, adjusted_scores, z_score, action, master_reasoning, news_content, tech_content):
        import sqlite3
        from datetime import datetime
        import json
        
        current_broker = broker if broker else "UNKNOWN"
        
        try:
            with sqlite3.connect('trade_database.db') as conn:
                cursor = conn.cursor()
                
                # อัปเดตโครงสร้างตารางให้ตรงกับที่หน้าเว็บต้องการเป๊ะๆ
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS TradeHistory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        broker TEXT,
                        asset TEXT,
                        action TEXT,
                        z_score REAL,
                        scores_json TEXT,
                        reasoning TEXT,
                        news_content TEXT,
                        tech_content TEXT
                    )
                ''')
                
                cursor.execute('''
                    INSERT INTO TradeHistory (timestamp, broker, asset, action, z_score, scores_json, reasoning, news_content, tech_content)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    current_broker,
                    asset,
                    action,
                    z_score,
                    json.dumps(adjusted_scores, ensure_ascii=False) if adjusted_scores else "{}",
                    master_reasoning,
                    news_content,
                    tech_content
                ))
                conn.commit()
        except Exception as e:
            print(f"⚠️ ไม่สามารถบันทึกประวัติลงฐานข้อมูลได้: {e}")

    async def analyze_and_trade(self, asset: str, news_content: str, tech_content: str):
        # ==========================================
        # 🧠 ส่วนที่ 1: AI วิเคราะห์ข้อมูล (TYPHOON LLM)
        # ==========================================
        import json
        import os
        from openai import AsyncOpenAI
        
        # ใส่ API Key ของ Typhoon (หรือตั้งเป็น Environment Variable)
        typhoon_api_key = "TYPHOON_API_KEY"
        
        action = "HOLD"
        z_score = 0.0
        adjusted_scores = {"Macro": 0, "Geo": 0, "Tech": 0, "Asset": 0}
        master_reasoning = ""
        
        if not typhoon_api_key or typhoon_api_key == "ใส่_KEY_ของ_TYPHOON_ตรงนี้":
            print("⚠️ ไม่พบ TYPHOON_API_KEY")
            master_reasoning = "System Error: Missing Typhoon API Key."
        else:
            # ชี้เป้าไปที่ Server ของ Typhoon
            client = AsyncOpenAI(
                api_key=typhoon_api_key,
                base_url="https://api.opentyphoon.ai/v1"
            )
            
            # Prompt สั่งให้ Typhoon ตอบกลับมาเป็น JSON เสมอ
            system_prompt = """
            คุณคือ 'North Trading AI' บอทเทรดอัจฉริยะ 
            จงวิเคราะห์ Market News และ Technical Data ที่ส่งให้
            
            ให้คะแนนปัจจัย 4 ด้าน (Macro, Geo, Tech, Asset) ตั้งแต่ -1.0 (แย่มาก) ถึง 1.0 (ดีมาก)
            และสรุป z_score (Master Score) ออกมา 
            ถ้า z_score > 0.6 ให้ action = "BUY"
            ถ้า z_score < -0.6 ให้ action = "SELL"
            นอกนั้นให้ "HOLD"
            
            **ตอบกลับเป็น JSON Format ตามโครงสร้างนี้เท่านั้น ห้ามมีข้อความอื่นปน:**
            {
                "action": "BUY" หรือ "SELL" หรือ "HOLD",
                "z_score": 0.85,
                "scores": {
                    "Macro": 0.5,
                    "Geo": 0.2,
                    "Tech": 0.9,
                    "Asset": 0.8
                },
                "reasoning": "อธิบายเหตุผลสั้นๆ กระชับ ดุดัน เป็นภาษาไทย"
            }
            """
            
            user_prompt = f"Asset: {asset}\n\n[Market News]\n{news_content}\n\n[Technical Data]\n{tech_content}"
            
            try:
                print(f"🌪️ กำลังส่งข้อมูล {asset} ให้ Typhoon วิเคราะห์...")
                response = await client.chat.completions.create(
                    model="typhoon-v2.5-30b-a3b-instruct",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2
                )
                
                # ทำความสะอาดข้อความ เผื่อโมเดลแถม ```json มาให้
                raw_content = response.choices[0].message.content.strip()
                if raw_content.startswith("```json"):
                    raw_content = raw_content[7:-3].strip()
                elif raw_content.startswith("```"):
                    raw_content = raw_content[3:-3].strip()
                    
                ai_data = json.loads(raw_content)
                
                # แกะค่าลงตัวแปร
                action = ai_data.get("action", "HOLD").upper()
                z_score = float(ai_data.get("z_score", 0.0))
                adjusted_scores = ai_data.get("scores", {"Macro": 0, "Geo": 0, "Tech": 0, "Asset": 0})
                master_reasoning = ai_data.get("reasoning", "ไม่มีคำอธิบาย")
                
                print(f"🎯 Typhoon วิเคราะห์เสร็จสิ้น: ตัดสินใจ {action} (Z-Score: {z_score})")
                
            except Exception as e:
                print(f"❌ Typhoon Error: {e}")
                action = "HOLD"
                master_reasoning = f"เกิดข้อผิดพลาดในการวิเคราะห์ด้วย Typhoon: {str(e)}"

        # ==========================================
        # ⚡ EXECUTION ENGINE
        # ==========================================
        if action != "HOLD":
            # 1. เช็คราคาปัจจุบันจากข้อมูล Tech
            current_price = "N/A"
            for line in tech_content.split('\n'):
                if "ราคาปัจจุบัน:" in line:
                    current_price = line.split(":")[1].strip()
            
            # 2. ดึงการตั้งค่า API จาก Database
            settings = None
            try:
                import sqlite3
                with sqlite3.connect('trade_database.db') as db_conn:
                    cursor = db_conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='SystemSettings'")
                    if cursor.fetchone():
                        cursor.execute("SELECT broker_name, api_key, api_secret, trading_mode FROM SystemSettings ORDER BY id DESC LIMIT 1")
                        settings = cursor.fetchone()
            except Exception as e:
                print(f"⚠️ ไม่สามารถอ่านการตั้งค่า API ได้: {e}")
            
            if settings:
                broker, api_key, api_secret, mode = settings
                
                # 3. ลุยของจริง! ยิงคำสั่งเข้า Broker
                if mode == "LIVE":
                    
                    # 🦙 1. ALPACA
                    if broker == "ALPACA":
                        print(f"⚡ [ALPACA] ตรวจสอบเงื่อนไขพอร์ตก่อนส่งคำสั่ง {action} {asset}...")
                        try:
                            trading_client = TradingClient(api_key, api_secret, paper=True)
                            has_position = False
                            try:
                                position = trading_client.get_open_position(asset)
                                has_position = True
                            except:
                                has_position = False
                                
                            if action == "BUY" and has_position:
                                print(f"🛑 ยกเลิก BUY: มี {asset} ในพอร์ตอยู่แล้ว (One Bullet)")
                            elif action == "SELL" and not has_position:
                                print(f"🛑 ยกเลิก SELL: ไม่มี {asset} ให้ขาย")
                            elif action == "SELL" and has_position:
                                trading_client.close_position(asset)
                                print(f"🎉 [SUCCESS] ขายล้างพอร์ต Alpaca สำเร็จ!")
                            elif action == "BUY" and not has_position:
                                account = trading_client.get_account()
                                buying_power = float(account.buying_power)
                                trade_amount = max(round(buying_power * 0.05, 2), 1.0)
                                market_order_data = MarketOrderRequest(symbol=asset, notional=trade_amount, side=OrderSide.BUY, time_in_force=TimeInForce.DAY)
                                trading_client.submit_order(order_data=market_order_data)
                                print(f"🎉 [SUCCESS] ซื้อ Alpaca แบบสัดส่วนสำเร็จ!")
                        except Exception as e:
                            print(f"❌ [ERROR] Alpaca: {e}")

                    # 🪙 2. BINANCE
                    elif broker == "BINANCE":
                        print(f"⚡ [BINANCE] ตรวจสอบเงื่อนไขพอร์ตก่อนส่งคำสั่ง {action} {asset}...")
                        try:
                            import ccxt
                            exchange = ccxt.binance({'apiKey': api_key, 'secret': api_secret, 'enableRateLimit': True, 'options': {'defaultType': 'spot'}})
                            exchange.set_sandbox_mode(True) 
                            
                            base_coin = asset.split('/')[0] if '/' in asset else asset.replace('USDT', '')
                            balance = exchange.fetch_balance()
                            coin_amount = balance['free'].get(base_coin, 0)
                            has_position = coin_amount > 0.0001
                            
                            if action == "BUY" and has_position:
                                print(f"🛑 ยกเลิก BUY: มี {asset} ถืออยู่แล้ว")
                            elif action == "SELL" and not has_position:
                                print(f"🛑 ยกเลิก SELL: ไม่มี {asset} ให้ขาย")
                            else:
                                if action == "BUY":
                                    ticker_info = exchange.fetch_ticker(asset)
                                    buy_amount = 20.0 / ticker_info['last']
                                    exchange.create_market_buy_order(asset, buy_amount)
                                else:
                                    exchange.create_market_sell_order(asset, coin_amount)
                                print(f"🎉 [SUCCESS] ออเดอร์ Binance สำเร็จ!")
                        except Exception as e:
                            print(f"❌ [ERROR] Binance: {e}")

                    # 💱 3. MT5
                    elif broker == "MT5":
                        print(f"⚡ [MT5] ตรวจสอบเงื่อนไขพอร์ตก่อนส่งคำสั่ง {action} {asset}...")
                        try:
                            import MetaTrader5 as mt5
                            if mt5.initialize() and mt5.login(int(api_key), password=api_secret):
                                positions = mt5.positions_get(symbol=asset)
                                has_position = len(positions) > 0 if positions else False
                                
                                if action == "BUY" and has_position:
                                    print(f"🛑 ยกเลิก BUY: มี Position ถืออยู่แล้ว")
                                elif action == "SELL" and not has_position:
                                    print(f"🛑 ยกเลิก SELL: ไม่มี Position ให้ปิด")
                                else:
                                    price = mt5.symbol_info_tick(asset).ask if action == "BUY" else mt5.symbol_info_tick(asset).bid
                                    request = {
                                        "action": mt5.TRADE_ACTION_DEAL, "symbol": asset, "volume": 0.01,
                                        "type": mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL,
                                        "price": price, "deviation": 20, "magic": 234000,
                                        "comment": "North Trading AI", "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
                                    }
                                    result = mt5.order_send(request)
                                    print(f"🎉 [SUCCESS] ออเดอร์ MT5 ส่งแล้ว!" if result.retcode == mt5.TRADE_RETCODE_DONE else f"❌ MT5 พลาด: {result.comment}")
                                mt5.shutdown()
                        except Exception as e:
                            print(f"❌ [ERROR] MT5: {e}")

                else:
                    print(f"🟡 [SIGNAL MODE] ตรวจพบสัญญาณ {action} {asset} แต่ไม่ได้เปิดโหมด LIVE")
                    
            # 4. ส่ง Telegram 
            send_telegram_alert(asset, action, z_score, current_price, master_reasoning)

        # 5. บันทึกลง Database (เรียกใช้ฟังก์ชัน DB แบบใหม่)
        current_broker = broker if 'broker' in locals() else "UNKNOWN"
        self.save_to_db(current_broker, asset, adjusted_scores, z_score, action, master_reasoning, news_content, tech_content)

# --- ฟังก์ชันดึงข้อมูลเสริม ---
def fetch_real_news(ticker_symbol: str) -> str:
    asset_type = classify_asset(ticker_symbol)
    
    # ==========================================
    # ระบบที่ 1: ดึงข่าวหุ้นเฉพาะตัวจาก Yahoo Finance
    # ==========================================
    if asset_type == "STOCK":
        print(f"📰 กำลังดึงข่าวตรงจากบริษัท {ticker_symbol} (Yahoo Finance)...")
        try:
            ticker = yf.Ticker(ticker_symbol)
            news = ticker.news
            if news:
                headlines = [n['title'] for n in news[:3] if 'title' in n]
                if headlines:
                    return " | ".join(headlines)
        except Exception as e:
            print(f"⚠️ Yahoo Finance ขัดข้อง เลื่อนไปใช้ระบบสำรอง... ({e})")
            
        # ถ้า Yahoo ไม่มีข่าวหุ้นตัวนี้ ให้ตั้งค่า Query สำหรับค้นหาระบบสำรอง
        query = f"{ticker_symbol} company stock market news"
        
    # ==========================================
    # ระบบที่ 2: ตั้งค่าคีย์เวิร์ดสำหรับ ทองคำ, Forex, Crypto
    # ==========================================
    else:
        if asset_type == "GOLD":
            query = "Gold market commodities inflation news"
        elif asset_type == "FOREX":
            query = f"{ticker_symbol} forex interest rate central bank news"
        else: # CRYPTO
            query = f"{ticker_symbol} cryptocurrency market news"

    # ==========================================
    # เครื่องยนต์ RSS (Google News) ทำงาน
    # ==========================================
    print(f"🔎 ค้นหาข่าวภาพรวมจาก Google News: '{query}' ...")
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}+when:3d&hl=en-US&gl=US&ceid=US:en"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        headlines = []
        
        for item in root.findall('.//item')[:3]:
            title = item.find('title').text
            # ตัดชื่อสำนักข่าวข้างหลังทิ้งเพื่อให้ AI อ่านง่ายขึ้น
            clean_title = title.rsplit(' - ', 1)[0] if ' - ' in title else title
            headlines.append(clean_title)
            
        if headlines:
            return " | ".join(headlines)
        else:
            return f"ไม่มีข่าวอัปเดตของ {ticker_symbol} ให้เน้นวิเคราะห์จากกราฟเทคนิคเป็นหลัก"
            
    except Exception as e:
        print(f"⚠️ ดึงข่าวล้มเหลวทั้ง 2 ระบบ: {e}")
        return "ไม่สามารถดึงข้อมูลข่าวได้ ให้วิเคราะห์จากกราฟเทคนิคแทน"

def get_technical_data(ticker_symbol: str) -> str:
    yf_ticker = get_yf_ticker(ticker_symbol)
    print(f"📈 กำลังคำนวณกราฟ Technical ของ {ticker_symbol} (ดึงข้อมูลผ่าน {yf_ticker})...")
    
    try:
        ticker = yf.Ticker(yf_ticker)
        df = ticker.history(period="6mo")
        
        if df.empty: 
            return f"ไม่พบข้อมูลราคา (ระบบพยายามค้นหาด้วยชื่อ {yf_ticker} แล้ว)"
        
        # คำนวณ Indicators
        df.ta.rsi(length=14, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        df.ta.macd(append=True)
        
        # พยายามดึงค่า P/E Ratio (ถ้ามี)
        try:
            info = ticker.info
            pe_ratio = info.get('trailingPE', info.get('forwardPE', 'N/A'))
            if isinstance(pe_ratio, (float, int)):
                pe_ratio = f"{pe_ratio:.2f}"
        except:
            pe_ratio = "N/A"
            
        last_20_days = df.tail(20)
        support = last_20_days['Low'].min()
        resistance = last_20_days['High'].max()
        avg_volume_20 = last_20_days['Volume'].mean()
        latest = df.iloc[-1]
        
        volume_status = "สูงกว่าค่าเฉลี่ย" if latest['Volume'] > avg_volume_20 else "ต่ำกว่าค่าเฉลี่ย"
        trend_ema = "ขาขึ้น (Uptrend)" if latest['EMA_20'] > latest['EMA_50'] else "ขาลง (Downtrend)"
        
        tech_summary = (
            f"[Technical Analysis - {ticker_symbol}]\n"
            f"ราคาปัจจุบัน: {latest['Close']:.4f}\n"
            f"Volume: {latest['Volume']:,.0f} ({volume_status})\n"
            f"P/E Ratio: {pe_ratio}\n" # <--- เพิ่ม P/E ตรงนี้
            f"แนวรับ (20D): {support:.4f} | แนวต้าน (20D): {resistance:.4f}\n"
            f"RSI (14): {latest['RSI_14']:.2f}\n"
            f"EMA Trend: {trend_ema} (EMA20={latest['EMA_20']:.4f}, EMA50={latest['EMA_50']:.4f})\n"
            f"MACD: {latest['MACD_12_26_9']:.4f} | Signal: {latest['MACDs_12_26_9']:.4f}\n"
        )
        return tech_summary
        
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการดึงข้อมูล Technical: {e}"

# --- เพิ่มฟังก์ชันแปลภาษาไว้ตรงนี้ (เหนือฟังก์ชัน main) ---
async def translate_news_to_thai(news_text: str) -> str:
    if "ไม่มี" in news_text or not news_text.strip(): 
        return news_text
        
    print("🇹🇭 กำลังให้ AI แปลพาดหัวข่าวเป็นภาษาไทย...")
    try:
        response = await client.chat.completions.create(
            model="typhoon-v2.5-30b-a3b-instruct",
            messages=[
                {
                    "role": "system", 
                    "content": "คุณคือนักแปลข่าวการเงินมืออาชีพ จงแปลพาดหัวข่าวภาษาอังกฤษต่อไปนี้เป็นภาษาไทยให้สละสลวย ใช้คำศัพท์วงการหุ้น และต้องคั่นแต่ละข่าวด้วย ' | ' เหมือนต้นฉบับเป๊ะๆ ห้ามพิมพ์คำอธิบายหรือข้อความอื่นนอกจากคำแปล"
                },
                {"role": "user", "content": news_text}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ แปลภาษาล้มเหลว: {e}")
        return news_text # ถ้าแปลพัง ให้ดึงภาษาอังกฤษไปใช้แทนเลย

def get_watchlist_from_db(db_name="trade_database.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("SELECT ticker FROM Watchlist")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows] # แปลงผลลัพธ์เป็น list ของชื่อหุ้น

async def main():
    trader = QuantMultiAgentTrader()
    
    # 🟢 ดึงรายชื่อหุ้นจากฐานข้อมูล
    watchlist = get_watchlist_from_db()
    
    if not watchlist:
        print("📭 Watchlist ว่างเปล่า! กรุณาไปเพิ่มชื่อหุ้นผ่านหน้าเว็บ Dashboard ก่อนครับ")
        return

    print(f"📋 หุ้นในคิววิเคราะห์รอบนี้: {', '.join(watchlist)}")
    
    for asset in watchlist:
        print(f"\n{'='*40}\nเริ่มกระบวนการของ: {asset}\n{'='*40}")
        news_data_en = fetch_real_news(asset)
        news_data_th = await translate_news_to_thai(news_data_en)
        tech_data = get_technical_data(asset)
        await trader.analyze_and_trade(asset, news_data_th, tech_data)
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())