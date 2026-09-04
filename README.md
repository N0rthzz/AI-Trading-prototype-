# North Trading AI 🚀
ระบบเทรดอัตโนมัติ (Quantitative Trading System) ทำงานด้วย Hybrid AI (Typhoon/OpenAI) 

## 🛠️ วิธีการติดตั้งและใช้งาน (How to use)
1. ติดตั้งไลบรารีที่จำเป็น:
   `pip install -r requirements.txt`
   
2. ตั้งค่า API Keys:
   - คัดลอกไฟล์ `.env.example` และเปลี่ยนชื่อเป็น `.env`
   - นำ API Key ของคุณมาใส่ในไฟล์ `.env` ให้ครบถ้วน (ระบบปลอดภัย ไม่มีการส่ง Key ออกสู่ภายนอก)

3. สั่งรันระบบ:
   `python trader_bot.py`