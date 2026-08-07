#!/usr/bin/env python3
# 🔱 OSINT ULTIMATE BOT - 

import requests, time, json, re, socket, subprocess, sys, hashlib
import phonenumbers, dns.resolver, whois
import os, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from phonenumbers import carrier, geocoder, timezone as pn_timezone

# ========== خادم صحي لـ Render ==========
PORT = int(os.environ.get("PORT", 8080))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ========== التكوينات الأساسية ==========
TOKEN = "8749267871:AAGhgXTCzg3TEEszmMpHulDpOXi7pW5n-s0"
REQUIRED_CHANNEL = "@mklz7z"
OWNER_ID = 6888107255
WHITELIST_USERS = [OWNER_ID]
LOG_GROUP_ID = -1003890891288
API_URL = f"https://api.telegram.org/bot{TOKEN}"

user_states = {}
user_last_bot_msg = {}
user_last_user_msg = {}

CACHE_TTL = 300
cache = {}

COMMON_PORTS = [21,22,23,25,53,80,110,443,993,995,3306,3389,8080]

# ========== متغيرات التحكم بالأنيميشن ==========
animation_stop_flags = {}

# ========== دوال مساعدة ==========
def get_session():
    return requests.Session()

def send_message(chat_id, text, reply_markup=None, disable_preview=False):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if disable_preview:
        data["disable_web_page_preview"] = True
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(f"{API_URL}/sendMessage", json=data, timeout=10).json()
    except:
        return None

def edit_message(chat_id, msg_id, text, reply_markup=None, disable_preview=False):
    data = {"chat_id": chat_id, "message_id": msg_id, "text": text, "parse_mode": "Markdown"}
    if disable_preview:
        data["disable_web_page_preview"] = True
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    try:
        return requests.post(f"{API_URL}/editMessageText", json=data, timeout=10).json()
    except:
        return None

def delete_message(chat_id, msg_id):
    try:
        requests.post(f"{API_URL}/deleteMessage", json={"chat_id": chat_id, "message_id": msg_id}, timeout=5)
    except:
        pass

def answer_callback(cb_id, text=None):
    data = {"callback_query_id": cb_id}
    if text:
        data["text"] = text
    requests.post(f"{API_URL}/answerCallbackQuery", json=data, timeout=5)

def is_member(user_id):
    if user_id in WHITELIST_USERS:
        return True
    try:
        r = requests.get(f"{API_URL}/getChatMember", params={"chat_id": REQUIRED_CHANNEL, "user_id": user_id}, timeout=5)
        return r.json().get("result", {}).get("status") in ["member", "administrator", "creator"]
    except:
        return False

def log_action(user_id, username, action, result_summary):
    try:
        text = f"📋 **سجل OSINT**\n👤 `{user_id}` (@{username})\n⚙️ {action}\n📝 {result_summary[:200]}"
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": LOG_GROUP_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except:
        pass

# ========== أزرار موحدة ==========
def back_main_button():
    return {"inline_keyboard": [[{"text": "🏠 القائمة الرئيسية", "callback_data": "back_main"}]]}

def result_buttons(tool_callback):
    return {"inline_keyboard": [
        [{"text": "🔄 تكرار العملية", "callback_data": tool_callback}],
        [{"text": "❓ مساعدة", "callback_data": f"help_{tool_callback}"}],
        [{"text": "🏠 القائمة الرئيسية", "callback_data": "back_main"}]
    ]}

# ========== نصوص المساعدة ==========
HELP_TEXTS = {
    "net_ip": """🔍 **ما هي IP Intelligence؟**
تقوم بإدخال عنوان IP (مثل 8.8.8.8) ويقوم البوت بجلب:
• الدولة، المدينة، المنطقة
• اسم مزود الخدمة (ISP)
• الإحداثيات وخريطة الموقع
📌 **الفائدة:** معرفة مصدر الـ IP وتحديد موقعه الجغرافي تقريباً.
💡 **مثال:** `8.8.8.8` → سيرى أن المزود Google ومقره الولايات المتحدة.""",

    "net_port_basic": """🔌 **ما هي Port Scanner (Common)؟**
تقوم بفحص مجموعة من المنافذ الشائعة (21,22,80,443,3306,...) على الـ IP الذي تدخله.
📌 **الفائدة:** معرفة الخدمات المفتوحة على الخادم (HTTP, SSH, MySQL...) والتي قد تكون ثغرات.
💡 **مثال:** `scanme.nmap.org` → سيرى المنافذ 22,80,443 مفتوحة.""",

    "net_reverse_dns": """🔄 **ما هي Reverse DNS؟**
تحويل عنوان IP إلى اسم نطاق (مثال: 8.8.8.8 → dns.google).
📌 **الفائدة:** معرفة النطاق المرتبط بالـ IP.
💡 **مثال:** `8.8.8.8` → النتيجة `dns.google`.""",

    "net_ping": """🏓 **ما هي Ping Test؟**
إرسال 4 حزم اختبار إلى المضيف (host) لقياس زمن الاستجابة وفقدان الحزم.
📌 **الفائدة:** اختبار ما إذا كان الخادم يعمل وسرعة الاتصال به.
💡 **مثال:** `google.com` → سترى زمن الاستجابة (time) وفقدان الحزم.""",

    "dom_dns": """🔍 **ما هي DNS Lookup؟**
جلب سجلات DNS للنطاق: A (العنوان), MX (البريد), TXT, NS, CNAME.
📌 **الفائدة:** معرفة خوادم البريد، العناوين IP، وإعدادات الأمان (SPF).
💡 **مثال:** `google.com` → سترى سجلات A متعددة و MX.""",

    "dom_subdomain": """🌐 **ما هي Subdomain Finder؟**
يبحث عن النطاقات الفرعية التابعة لنطاق رئيسي (مثل mail.google.com, drive.google.com).
📌 **الفائدة:** اكتشاف جميع الخدمات والبوابات المخفية تحت النطاق.
💡 **مثال:** `github.com` → قد يظهر `api.github.com`, `education.github.com`.""",

    "dom_whois": """🏢 **ما هي WHOIS؟**
استعلام عن معلومات مالك النطاق: تاريخ التسجيل، انتهاء الصلاحية، خوادم الأسماء، المسجل.
📌 **الفائدة:** معرفة الجهة المالكة للنطاق وتواريخه الهامة.
💡 **مثال:** `example.com` → سترى معلومات ICANN.""",

    "dom_to_ip": """🔄 **ما هي Domain → IP؟**
تحويل اسم النطاق إلى عنوان IP المقابل له.
📌 **الفائدة:** معرفة الخادم الذي يستضيف الموقع.
💡 **مثال:** `github.com` → تحصل على IP مثل `140.82.112.3`.""",

    "dom_reverse_ip": """🔄 **ما هي Reverse IP؟**
البحث عن جميع النطاقات المستضافة على نفس عنوان IP (مشاركة السيرفر).
📌 **الفائدة:** اكتشاف مواقع أخرى على نفس الخادم.
💡 **مثال:** `8.8.8.8` → يعرض نطاقات مثل `dns.google`, `google-public-dns-a.google.com`.""",

    "acc_username": """🔍 **ما هي Username Search؟**
يبحث في أكثر من 30 منصة (Twitter, GitHub, Instagram, TikTok, Reddit, YouTube, Facebook, Telegram, Snapchat, Pinterest, Twitch, Steam, Spotify, Medium, Quora, Tumblr, VK, Imgur, DeviantArt, Flickr, Dribbble, Behance, Keybase, Patreon وغيرها) عن اسم المستخدم.
📌 **الفائدة:** تعقب وجود الشخص على منصات متعددة وجمع معلومات عنه.
💡 **مثال:** `github` → سيجد حسابات على GitHub, Twitter, TikTok وغيرها.""",

    "acc_github": """🐙 **ما هي GitHub User Info؟**
يعرض معلومات حساب GitHub: الاسم، البايو، الشركة، عدد الريبوزيتوريات، المتابعين، تاريخ الإنشاء.
📌 **الفائدة:** تحليل نشاط المطور ومشاريعه.
💡 **مثال:** `octocat` → يعرض معلومات حساب GitHub التوضيحي.""",

    "phone_lookup": """📞 **ما هي Phone Lookup؟**
تحليل رقم الهاتف: الدولة، المشغل، المنطقة الزمنية، روابط واتساب وتلغرام.
📌 **الفائدة:** التحقق من صحة الرقم ومعرفة الشركة والدولة المرتبطة به.
💡 **مثال:** `+14155552671` (رقم وهمي أمريكي) أو رقمك الحقيقي مع مفتاح الدولة.""",

    "web_tech": """💻 **ما هي Web Technology؟**
تحديد التقنيات المستخدمة في موقع الويب (الخادم، X-Powered-By، إلخ).
📌 **الفائدة:** معرفة لغة البرمجة ونوع الخادم.
💡 **مثال:** `github.com` → الخادم: `GitHub.com`, X-Powered-By: `Express`.""",

    "web_info": """🌐 **ما هي Website Info؟**
عرض رؤوس HTTP (Headers) للموقع: حالة الصفحة، نوع الخادم، تاريخ التعديل، إلخ.
📌 **الفائدة:** الحصول على معلومات فنية عن الموقع.
💡 **مثال:** `example.com` → سترى `Content-Type`, `Server`, `Cache-Control`.""",

    "web_crawler": """🕷️ **ما هي Crawler؟**
استخراج جميع الروابط (URLs) الموجودة في صفحة الموقع.
📌 **الفائدة:** اكتشاف بنية الموقع وجميع صفحاته.
💡 **مثال:** `example.com` → يعرض روابط داخلية وخارجية.""",

    "web_robots": """🤖 **ما هي robots.txt؟**
جلب الملف robots.txt الذي يوجه محركات البحث.
📌 **الفائدة:** معرفة الأجزاء المخفية أو المحظورة من الموقع.
💡 **مثال:** `google.com` → سترى تعليمات لمحركات البحث.""",

    "web_sitemap": """🗺️ **ما هي sitemap.xml؟**
جلب خريطة الموقع (sitemap) التي تحتوي على جميع الروابط المهمة.
📌 **الفائدة:** رؤية هيكل الموقع الكامل.
💡 **مثال:** `example.com` → قد يعرض روابط الصفحات الرئيسية.""",

    "web_admin": """🔐 **ما هي Admin Finder؟**
يبحث عن صفحات الإدارة الشائعة (/admin, /login, /dashboard...).
📌 **الفائدة:** اختبار أمان الموقع ومعرفة نقاط الدخول للإدارة.
💡 **مثال:** `example.com` → قد يكتشف `/admin` أو `/login` إذا كانت موجودة.""",

    "web_methods": """🔧 **ما هي HTTP Methods Test؟**
اختبار الطرق HTTP المسموحة على الخادم (GET, POST, PUT, DELETE, OPTIONS, HEAD, TRACE, PATCH).
📌 **الفائدة:** اكتشاف الثغرات الأمنية مثل TRACE أو PUT المفتوح.
💡 **مثال:** `example.com` → يعرض الطرق المسموحة والممنوعة.""",

    "email_lookup": """✉️ **ما هي Email Lookup؟**
تحليل البريد الإلكتروني: سجلات MX، SPF، Gravatar، وصحة الصيغة.
📌 **الفائدة:** التأكد من إعدادات البريد وصورة Gravatar المرتبطة.
💡 **مثال:** `admin@example.com` → يعرض خوادم البريد ووجود SPF.""",

    "report_domain": """📊 **ما هي Quick Domain Report؟**
تقرير شامل عن النطاق يشمل: IP, WHOIS, DNS, التقنيات, robots.txt.
📌 **الفائدة:** الحصول على نظرة كاملة عن الموقع في تقرير واحد.
💡 **مثال:** `github.com` → يعرض 6 أدوات مجتمعة.""",

    "report_ip": """📊 **ما هي Quick IP Report؟**
تقرير شامل عن الـ IP يشمل: الموقع الجغرافي، Reverse DNS، Reverse IP، والمنافذ المفتوحة.
📌 **الفائدة:** تحليل شامل للخادم من عنوان IP واحد.
💡 **مثال:** `8.8.8.8` → يعرض 4 أدوات مجتمعة.""",

    "report_social": """📊 **ما هي Social Media Report؟**
تقرير شامل عن اسم المستخدم في منصات التواصل الاجتماعي + GitHub.
📌 **الفائدة:** معرفة وجود الشخص على جميع المنصات دفعة واحدة.
💡 **مثال:** `github` → يعرض نتائج Username Search و GitHub معاً."""
}

def show_help(chat_id, tool_id, msg_id):
    help_text = HELP_TEXTS.get(tool_id, "⚠️ لا توجد مساعدة متاحة لهذه الأداة.")
    kb = {"inline_keyboard": [[{"text": "🔙 رجوع لطلب الإدخال", "callback_data": f"back_to_{tool_id}"}]]}
    edit_message(chat_id, msg_id, help_text, kb)

# ========== أدوات OSINT الأساسية ==========
def ip_intelligence(ip):
    try:
        r = get_session().get(f"http://ip-api.com/json/{ip}?fields=66846719", timeout=6)
        if r.status_code == 200 and r.json().get("status") == "success":
            data = r.json()
            return f"""🌐 **IP Intelligence:** `{ip}`
━━━━━━━━━━━━━━━━━━━
📍 الدولة: {data.get('country', '?')}
🏙️ المدينة: {data.get('city', '?')}
📌 المنطقة: {data.get('regionName', '?')}
📡 ISP: {data.get('isp', '?')}
🏢 المنظمة: {data.get('org', '?')}
🌍 الإحداثيات: {data.get('lat', '?')}, {data.get('lon', '?')}
🗺️ [خريطة](https://www.google.com/maps?q={data.get('lat',0)},{data.get('lon',0)})"""
        else:
            return "❌ فشل جلب المعلومات."
    except:
        return "❌ خطأ في الاتصال."

def port_scanner_basic(ip):
    open_ports = []
    for port in COMMON_PORTS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            if sock.connect_ex((ip, port)) == 0:
                open_ports.append(port)
            sock.close()
        except:
            pass
    if open_ports:
        return f"✅ **المنافذ المفتوحة:**\n`{', '.join(str(p) for p in open_ports)}`"
    else:
        return "❌ لا توجد منافذ شائعة مفتوحة."

def reverse_dns(ip):
    try:
        host = socket.gethostbyaddr(ip)[0]
        return f"🔄 **Reverse DNS:** `{ip}` → `{host}`"
    except:
        return f"❌ لا يوجد PTR سجل لـ {ip}"

def ping_test(host):
    is_windows = sys.platform.lower().startswith('win')
    try:
        if is_windows:
            output = subprocess.check_output(["ping", "-n", "4", host], timeout=10, stderr=subprocess.STDOUT, universal_newlines=True)
        else:
            output = subprocess.check_output(["ping", "-c", "4", host], timeout=10, stderr=subprocess.STDOUT, universal_newlines=True)
        return f"🏓 **نتائج Ping لـ `{host}`:**\n```\n{output[:500]}\n```"
    except:
        return f"❌ فشل ping لـ {host}"

def dns_lookup(domain):
    records = {}
    for qtype in ['A', 'MX', 'TXT', 'NS', 'CNAME']:
        try:
            answers = dns.resolver.resolve(domain, qtype)
            records[qtype] = [str(r) for r in answers]
        except:
            records[qtype] = []
    txt = f"📡 **DNS Records لـ `{domain}`**\n\n"
    for q, vals in records.items():
        if vals:
            txt += f"**{q}:** `{', '.join(vals)}`\n"
    return txt if len(txt) > 30 else "❌ لا توجد سجلات DNS."

def subdomain_finder(domain):
    try:
        r = get_session().get(f"https://crt.sh/?q=%.{domain}&output=json", timeout=12)
        if r.status_code == 200:
            data = r.json()
            subs = set()
            for entry in data:
                name = entry.get('name_value', '')
                if name.endswith(f".{domain}"):
                    subs.add(name.strip())
            if subs:
                return f"🔍 **الساب دومينات:**\n`" + "\n".join(list(subs)[:30]) + "`"
            else:
                return "❌ لم يتم العثور على ساب دومينات."
    except:
        return "⚠️ فشل الاتصال بـ crt.sh"
    return "❌ لا توجد نتائج."

def whois_lookup(domain):
    try:
        w = whois.whois(domain)
        info = f"🏢 **WHOIS لـ `{domain}`**\n"
        if w.registrar: info += f"Registrar: {w.registrar}\n"
        if w.creation_date: info += f"Creation: {w.creation_date}\n"
        if w.expiration_date: info += f"Expiry: {w.expiration_date}\n"
        if w.name_servers: info += f"Name Servers: {', '.join(w.name_servers)}\n"
        return info[:1000]
    except:
        return "❌ لا يمكن جلب WHOIS."

def domain_to_ip(domain):
    try:
        ip = socket.gethostbyname(domain)
        return f"🔄 **Domain → IP:** `{domain}` → `{ip}`"
    except:
        return "❌ فشل التحليل."

def reverse_ip(ip):
    try:
        r = get_session().get(f"https://api.hackertarget.com/reverseiplookup/?q={ip}", timeout=8)
        if r.status_code == 200:
            domains = r.text.strip().split("\n")
            if domains and domains[0] != "error":
                return f"🔄 **Reverse IP:**\n`" + "\n".join(domains[:15]) + "`"
            else:
                return "❌ لا توجد مواقع مشاركة."
    except:
        return "⚠️ فشل الاتصال."
    return "❌ لا توجد نتائج."

def username_search_parallel(username):
    platforms = {
        "GitHub": f"https://github.com/{username}",
        "Instagram": f"https://instagram.com/{username}",
        "Twitter": f"https://twitter.com/{username}",
        "TikTok": f"https://tiktok.com/@{username}",
        "Reddit": f"https://reddit.com/user/{username}",
        "YouTube": f"https://youtube.com/@{username}",
        "Facebook": f"https://facebook.com/{username}",
        "Telegram": f"https://t.me/{username}",
        "Snapchat": f"https://snapchat.com/add/{username}",
        "Pinterest": f"https://pinterest.com/{username}",
        "Twitch": f"https://twitch.tv/{username}",
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Spotify": f"https://open.spotify.com/user/{username}",
        "Medium": f"https://medium.com/@{username}",
        "Quora": f"https://quora.com/profile/{username}",
        "Tumblr": f"https://{username}.tumblr.com",
        "VK": f"https://vk.com/{username}",
        "Imgur": f"https://imgur.com/user/{username}",
        "DeviantArt": f"https://deviantart.com/{username}",
        "Flickr": f"https://flickr.com/people/{username}",
        "Dribbble": f"https://dribbble.com/{username}",
        "Behance": f"https://behance.net/{username}",
        "Keybase": f"https://keybase.io/{username}",
        "Patreon": f"https://patreon.com/{username}"
    }
    found = []
    def check_platform(name, url):
        try:
            r = get_session().head(url, timeout=4, allow_redirects=True)
            if r.status_code == 200:
                return (name, url)
        except:
            pass
        return None
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(check_platform, name, url): name for name, url in platforms.items()}
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(f"✅ [{result[0]}]({result[1]})")
    if found:
        return f"🔍 **نتائج البحث عن `{username}`** (30 منصة):\n" + "\n".join(found)
    else:
        return f"❌ لم يتم العثور على حسابات باسم `{username}`"

def github_user_info(user):
    try:
        r = get_session().get(f"https://api.github.com/users/{user}", timeout=6)
        if r.status_code == 200:
            data = r.json()
            return f"""🐙 **GitHub: @{user}**
━━━━━━━━━━━━━━━━━━━
📛 الاسم: {data.get('name', 'غير متاح')}
📝 البايو: {data.get('bio', 'لا يوجد')}
🏢 الشركة: {data.get('company', 'غير معروف')}
📍 الموقع: {data.get('location', 'غير معروف')}
📦 الريبوزيتوريات: {data.get('public_repos', 0)}
👥 المتابعون: {data.get('followers', 0)}
👣 يتابع: {data.get('following', 0)}
📅 تاريخ الإنشاء: {data.get('created_at', 'غير متاح')[:10]}
🔗 [الملف الشخصي]({data.get('html_url')})"""
        else:
            return "❌ المستخدم غير موجود."
    except:
        return "❌ فشل الاتصال بـ GitHub."

def phone_lookup(phone):
    try:
        parsed = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(parsed):
            return "❌ رقم غير صالح. مثال: `+966512345678`"
        country = geocoder.description_for_number(parsed, "ar")
        carrier_name = carrier.name_for_number(parsed, "ar")
        tz = pn_timezone.time_zones_for_number(parsed)
        national = parsed.national_number
        return f"""📱 **معلومات الرقم:** `{phone}`
━━━━━━━━━━━━━━━━━━━
🌍 الدولة: {country}
📶 المشغل: {carrier_name or 'غير معروف'}
⏰ المنطقة الزمنية: {', '.join(tz)}
💚 [واتساب](https://wa.me/{national})
💙 [تيليجرام](https://t.me/{national})"""
    except:
        return "❌ خطأ في تحليل الرقم."

def fix_url(url):
    if not url.startswith(('http://','https://')):
        return 'http://' + url
    return url

def web_technology(url):
    url = fix_url(url)
    try:
        r = get_session().get(url, timeout=6)
        server = r.headers.get('Server', 'غير معروف')
        power = r.headers.get('X-Powered-By', 'غير معروف')
        return f"💻 **تقنيات:**\n• الخادم: `{server}`\n• X-Powered-By: `{power}`"
    except:
        return "❌ لا يمكن الوصول."

def website_info(url):
    url = fix_url(url)
    try:
        r = get_session().get(url, timeout=6, allow_redirects=True)
        headers = r.headers
        txt = f"🌐 **معلومات `{url}`**\n**Status:** {r.status_code}\n**Headers:**\n"
        for k, v in list(headers.items())[:8]:
            txt += f"• `{k}`: `{v}`\n"
        return txt[:800]
    except:
        return "❌ فشل الجلب."

def crawler(url):
    url = fix_url(url)
    try:
        r = get_session().get(url, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            full = urljoin(url, href)
            if full.startswith(('http://','https://')):
                links.add(full)
        result = f"🕷️ **روابط مكتشفة:**\n" + "\n".join(list(links)[:25])
        return result[:1200]
    except:
        return "❌ فشل الزحف."

def robots_txt(url):
    base = url.split('//')[-1].split('/')[0]
    for proto in ['https', 'http']:
        try:
            r = get_session().get(f"{proto}://{base}/robots.txt", timeout=4)
            if r.status_code == 200:
                return f"🤖 **robots.txt**\n```\n{r.text[:600]}\n```"
        except:
            continue
    return "❌ لم يتم العثور على robots.txt."

def sitemap_xml(url):
    base = url.split('//')[-1].split('/')[0]
    for proto in ['https', 'http']:
        try:
            r = get_session().get(f"{proto}://{base}/sitemap.xml", timeout=4)
            if r.status_code == 200:
                return f"🗺️ **sitemap.xml**\n```\n{r.text[:600]}\n```"
        except:
            continue
    return "❌ لم يتم العثور على sitemap.xml."

def admin_finder(url):
    base = fix_url(url).rstrip('/')
    admin_paths = ["/admin", "/login", "/dashboard", "/wp-admin", "/administrator", "/cpanel", "/phpmyadmin", "/admin.php"]
    found = []
    for path in admin_paths:
        try:
            full = f"{base}{path}"
            r = get_session().get(full, timeout=3, allow_redirects=False)
            if r.status_code == 200:
                found.append(f"✅ `{full}`")
            elif r.status_code == 403:
                found.append(f"⚠️ `{full}` (ممنوع)")
        except:
            continue
    return f"🔐 **صفحات الإدارة المحتملة:**\n" + ("\n".join(found) if found else "❌ لا توجد.")

def http_methods(url):
    url = fix_url(url)
    methods = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD', 'TRACE', 'PATCH']
    allowed = []
    for method in methods:
        try:
            r = requests.request(method, url, timeout=5, allow_redirects=False)
            if r.status_code not in [405, 501, 403]:
                allowed.append(f"✅ {method} → {r.status_code}")
            else:
                allowed.append(f"❌ {method} → {r.status_code}")
        except:
            allowed.append(f"⚠️ {method} → Timeout/Error")
    return "🔧 **HTTP Methods Test**\n" + "\n".join(allowed)

def email_lookup(email):
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "❌ صيغة البريد غير صالحة."
    domain = email.split('@')[1]
    result = f"📧 **تحليل البريد:** `{email}`\n━━━━━━━━━━━━━━━━━━━\n"
    try:
        mx = dns.resolver.resolve(domain, 'MX')
        result += f"📬 MX: `{', '.join(str(r.exchange) for r in mx)}`\n"
    except:
        result += "📬 MX: لا يوجد\n"
    try:
        spf = dns.resolver.resolve(domain, 'TXT')
        spf_txt = [str(r) for r in spf if 'v=spf' in str(r)]
        result += f"🛡️ SPF: `{spf_txt[0][:100] if spf_txt else 'لا يوجد'}`\n"
    except:
        result += "🛡️ SPF: لا يوجد\n"
    hash_md5 = hashlib.md5(email.strip().lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{hash_md5}?d=404"
    try:
        g = get_session().get(gravatar_url, timeout=4)
        if g.status_code == 200:
            result += f"🖼️ Gravatar: [صورة]({gravatar_url})\n"
        else:
            result += "🖼️ Gravatar: غير موجود\n"
    except:
        result += "🖼️ Gravatar: فشل الاتصال\n"
    return result

# ========== الأدوات الجديدة (Reports) ==========

def quick_report_domain(domain):
    results = []
    results.append(f"📊 **QUICK REPORT FOR `{domain}`**\n" + "="*40)
    results.append(domain_to_ip(domain))
    try:
        ip = socket.gethostbyname(domain)
        results.append(ip_intelligence(ip))
    except:
        results.append("❌ Cannot resolve IP")
    results.append(dns_lookup(domain))
    results.append(whois_lookup(domain))
    results.append(web_technology(domain))
    results.append(robots_txt(domain))
    return "\n\n".join(results)

def quick_report_ip(ip):
    results = []
    results.append(f"📊 **QUICK REPORT FOR IP `{ip}`**\n" + "="*40)
    results.append(ip_intelligence(ip))
    results.append(reverse_dns(ip))
    results.append(reverse_ip(ip))
    results.append(port_scanner_basic(ip))
    return "\n\n".join(results)

def social_report(username):
    results = []
    results.append(f"📊 **SOCIAL MEDIA REPORT FOR `{username}`**\n" + "="*40)
    results.append(username_search_parallel(username))
    gh = github_user_info(username)
    if "❌" not in gh:
        results.append("\n" + gh)
    return "\n\n".join(results)

# ========== أنيميشن للفحوصات الطويلة ==========

def show_loading_if_slow(chat_id, msg_id, tool_name, start_time, user_id):
    """
    تظهر رسالة انتظار فقط إذا مرت 3 ثواني وما زال الفحص يعمل
    مع إمكانية إيقافها عند ظهور النتيجة
    """
    def check_and_show():
        # ننتظر 3 ثواني
        time.sleep(3)
        
        # نتحقق إذا تم إيقاف الأنيميشن
        if animation_stop_flags.get(user_id, False):
            return
        
        elapsed = time.time() - start_time
        if elapsed >= 3:
            try:
                dots = ["", "•", "••", "•••", "••••"]
                i = 0
                while time.time() - start_time < 30:
                    # نتحقق كل دورة إذا تم الإيقاف
                    if animation_stop_flags.get(user_id, False):
                        return
                    
                    dot = dots[i % len(dots)]
                    text = f"""⏳ **جاري التنفيذ** {dot}

📌 **الأداة:** `{tool_name}`
⏱️ **مضى:** {int(time.time() - start_time)} ثانية
━━━━━━━━━━━━━━━━━━━
🔄 يرجى الانتظار..."""
                    try:
                        edit_message(chat_id, msg_id, text, disable_preview=True)
                        time.sleep(0.5)
                        i += 1
                    except:
                        break
            except:
                pass
    
    thread = threading.Thread(target=check_and_show, daemon=True)
    thread.start()
    return thread

# ========== بناء القوائم ==========

def main_menu_keyboard():
    return {"inline_keyboard": [
        [{"text": "🌐 Network", "callback_data": "menu_network"}],
        [{"text": "🏠 Domain", "callback_data": "menu_domain"}],
        [{"text": "👤 Account", "callback_data": "menu_account"}],
        [{"text": "📞 Phone", "callback_data": "menu_phone"}],
        [{"text": "🌍 Web", "callback_data": "menu_web"}],
        [{"text": "✉️ Email", "callback_data": "menu_email"}],
        [{"text": "📊 OSINT Report", "callback_data": "menu_report"}]
    ]}

def get_submenu(menu_name):
    submenus = {
        "network": [
            [{"text": "🕵️ IP info", "callback_data": "net_ip"}],
            [{"text": "🔌 Port Scanner (Common)", "callback_data": "net_port_basic"}],
            [{"text": "🔄 Reverse DNS", "callback_data": "net_reverse_dns"}],
            [{"text": "🏓 Ping Test", "callback_data": "net_ping"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ],
        "domain": [
            [{"text": "🔍 DNS Lookup", "callback_data": "dom_dns"}],
            [{"text": "🌐 Subdomain Finder", "callback_data": "dom_subdomain"}],
            [{"text": "🏢 WHOIS", "callback_data": "dom_whois"}],
            [{"text": "🔄 Domain → IP", "callback_data": "dom_to_ip"}],
            [{"text": "🔄 Reverse IP", "callback_data": "dom_reverse_ip"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ],
        "account": [
            [{"text": "🔍 Username Search (30+ platforms)", "callback_data": "acc_username"}],
            [{"text": "🐙 GitHub User Info", "callback_data": "acc_github"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ],
        "phone": [
            [{"text": "📞 Phone info", "callback_data": "phone_lookup"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ],
        "web": [
            [{"text": "💻 Web Technology", "callback_data": "web_tech"}],
            [{"text": "🌐 Website Info (Headers)", "callback_data": "web_info"}],
            [{"text": "🔧 HTTP Methods", "callback_data": "web_methods"}],
            [{"text": "🕷️ Crawler", "callback_data": "web_crawler"}],
            [{"text": "🤖 robots.txt", "callback_data": "web_robots"}],
            [{"text": "🗺️ sitemap.xml", "callback_data": "web_sitemap"}],
            [{"text": "🔐 Admin Finder", "callback_data": "web_admin"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ],
        "email": [
            [{"text": "✉️ Email Lookup", "callback_data": "email_lookup"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ],
        "report": [
            [{"text": "📊 Quick Domain Report", "callback_data": "report_domain"}],
            [{"text": "📊 Quick IP Report", "callback_data": "report_ip"}],
            [{"text": "📊 Social Media Report", "callback_data": "report_social"}],
            [{"text": "🔙 الرجوع", "callback_data": "back_main"}]
        ]
    }
    return {"inline_keyboard": submenus.get(menu_name, [])}

def show_main_menu(chat_id, user_id, try_msg_id=None):
    text = """       🔱 **OSINT BOT** 🔱

👨‍💻 **المطور:** [@vvz_1]
**القناة الرسمية:** [https://t.me/mklz7z]
━━━━━━━━━━━━━━━━━━━
 **هذا البوت يوفر أدوات OSINT :**

• 🌐 معلومات IP والمواقع  
• 🏠 تحليل النطاقات و DNS  
• 👤 البحث عن الحسابات في 30+ منصة  
• 📞 تحليل أرقام الهاتف  
• 💻 فحص المواقع والتقنيات  
• ✉️ تحليل البريد الإلكتروني  
• 📊 تقارير شاملة (All-in-One)
━━━━━━━━━━━━━━━━━━━
 **القائمة الرئيسية : **"""
    if try_msg_id:
        res = edit_message(chat_id, try_msg_id, text, main_menu_keyboard())
        if res and res.get("ok"):
            user_last_bot_msg[user_id] = try_msg_id
            return
    res = send_message(chat_id, text, main_menu_keyboard())
    if res and res.get("ok"):
        user_last_bot_msg[user_id] = res["result"]["message_id"]

def show_submenu(chat_id, msg_id, menu_name, user_id):
    sub_kb = get_submenu(menu_name)
    edit_message(chat_id, msg_id, f"📂 **قائمة {menu_name.capitalize()}**", sub_kb)
    user_last_bot_msg[user_id] = msg_id

def get_prompt_for_tool(tool_id):
    prompts = {
        "net_ip": "🌐 **أرسل عنوان IP**\nمثال: `8.8.8.8`",
        "net_port_basic": "🔌 **أرسل عنوان IP لفحص المنافذ**\nمثال: `scanme.nmap.org`",
        "net_reverse_dns": "🔄 **أرسل عنوان IP لـ Reverse DNS**\nمثال: `8.8.8.8`",
        "net_ping": "🏓 **أرسل اسم المضيف أو IP**\nمثال: `google.com`",
        "dom_dns": "🔍 **أرسل النطاق لاستعلام DNS**\nمثال: `example.com`",
        "dom_subdomain": "🌐 **أرسل النطاق للبحث عن subdomains**\nمثال: `google.com`",
        "dom_whois": "🏢 **أرسل النطاق لاستعلام WHOIS**\nمثال: `github.com`",
        "dom_to_ip": "🔄 **أرسل النطاق لتحويله إلى IP**\nمثال: `github.com`",
        "dom_reverse_ip": "🔄 **أرسل عنوان IP لـ Reverse IP**\nمثال: `8.8.8.8`",
        "acc_username": "🔍 **أرسل اسم المستخدم للبحث**\nمثال: `github`",
        "acc_github": "🐙 **أرسل اسم مستخدم GitHub**\nمثال: `octocat`",
        "phone_lookup": "📞 **أرسل رقم الهاتف مع مفتاح الدولة**\nمثال: `+966512345678`",
        "web_tech": "💻 **أرسل رابط الموقع**\nمثال: `example.com`",
        "web_info": "🌐 **أرسل رابط الموقع**\nمثال: `example.com`",
        "web_crawler": "🕷️ **أرسل رابط الموقع**\nمثال: `example.com`",
        "web_robots": "🤖 **أرسل رابط الموقع**\nمثال: `google.com`",
        "web_sitemap": "🗺️ **أرسل رابط الموقع**\nمثال: `example.com`",
        "web_admin": "🔐 **أرسل رابط الموقع**\nمثال: `example.com`",
        "web_methods": "🔧 **أرسل رابط الموقع**\nمثال: `example.com`",
        "email_lookup": "✉️ **أرسل البريد الإلكتروني**\nمثال: `admin@example.com`",
        "report_domain": "📊 **أرسل النطاق لتقرير شامل**\nمثال: `github.com`",
        "report_ip": "📊 **أرسل عنوان IP لتقرير شامل**\nمثال: `8.8.8.8`",
        "report_social": "📊 **أرسل اسم المستخدم**\nمثال: `github`"
    }
    return prompts.get(tool_id, "✏️ أرسل القيمة المطلوبة:")

# ========== معالجة الكولباك والرسائل ==========

def process_callback(callback):
    data = callback["data"]
    chat_id = callback["message"]["chat"]["id"]
    msg_id = callback["message"]["message_id"]
    cb_id = callback["id"]
    user_id = callback["from"]["id"]
    username = callback["from"].get("username", "")

    if data == "check_join":
        if is_member(user_id):
            edit_message(chat_id, msg_id, "✅ تم التحقق!")
            show_main_menu(chat_id, user_id)
        else:
            edit_message(chat_id, msg_id, "❌ لم تشترك بعد. اشترك ثم اضغط /start")
        answer_callback(cb_id)
        return

    if not is_member(user_id):
        kb = {"inline_keyboard": [[{"text": "📢 اشترك في القناة", "url": f"https://t.me/{REQUIRED_CHANNEL[1:]}"}],
                                  [{"text": "🔄 تأكيد الاشتراك", "callback_data": "check_join"}]]}
        edit_message(chat_id, msg_id, f"🔒 يجب الاشتراك في [القناة](https://t.me/{REQUIRED_CHANNEL[1:]}) أولاً.", kb)
        answer_callback(cb_id)
        return

    if data == "back_main":
        show_main_menu(chat_id, user_id, msg_id)
        answer_callback(cb_id)
        return

    if data.startswith("help_"):
        tool_id = data[5:]
        show_help(chat_id, tool_id, msg_id)
        answer_callback(cb_id)
        return

    if data.startswith("back_to_"):
        tool_id = data[8:]
        prompt = get_prompt_for_tool(tool_id)
        edit_message(chat_id, msg_id, prompt, result_buttons(tool_id))
        user_states[user_id] = tool_id
        answer_callback(cb_id)
        return

    # القوائم الرئيسية
    if data == "menu_network":
        show_submenu(chat_id, msg_id, "network", user_id)
    elif data == "menu_domain":
        show_submenu(chat_id, msg_id, "domain", user_id)
    elif data == "menu_account":
        show_submenu(chat_id, msg_id, "account", user_id)
    elif data == "menu_phone":
        show_submenu(chat_id, msg_id, "phone", user_id)
    elif data == "menu_web":
        show_submenu(chat_id, msg_id, "web", user_id)
    elif data == "menu_email":
        show_submenu(chat_id, msg_id, "email", user_id)
    elif data == "menu_report":
        show_submenu(chat_id, msg_id, "report", user_id)

    # أدوات
    elif data in ["net_ip", "net_port_basic", "net_reverse_dns", "net_ping",
                  "dom_dns", "dom_subdomain", "dom_whois", "dom_to_ip", "dom_reverse_ip",
                  "acc_username", "acc_github", "phone_lookup",
                  "web_tech", "web_info", "web_crawler", "web_robots", "web_sitemap", "web_admin",
                  "web_methods", "email_lookup",
                  "report_domain", "report_ip", "report_social"]:
        prompt = get_prompt_for_tool(data)
        edit_message(chat_id, msg_id, prompt, result_buttons(data))
        user_states[user_id] = data

    answer_callback(cb_id)

def process_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "").strip()
    username = message["from"].get("username", "")
    user_msg_id = message["message_id"]

    delete_message(chat_id, user_msg_id)

    if not is_member(user_id):
        kb = {"inline_keyboard": [[{"text": "📢 اشترك في القناة", "url": f"https://t.me/{REQUIRED_CHANNEL[1:]}"}],
                                  [{"text": "🔄 تأكيد الاشتراك", "callback_data": "check_join"}]]}
        send_message(chat_id, f"🔒 يجب الاشتراك في [القناة](https://t.me/{REQUIRED_CHANNEL[1:]}) أولاً.", kb)
        return

    state = user_states.pop(user_id, None)
    if not state:
        last_bot = user_last_bot_msg.get(user_id)
        if last_bot:
            show_main_menu(chat_id, user_id, last_bot)
        else:
            show_main_menu(chat_id, user_id)
        return

    last_bot = user_last_bot_msg.get(user_id)
    
    # أسماء الأدوات
    tool_names = {
        "net_ip": "IP Intelligence",
        "net_port_basic": "Port Scanner",
        "net_reverse_dns": "Reverse DNS",
        "net_ping": "Ping Test",
        "dom_dns": "DNS Lookup",
        "dom_subdomain": "Subdomain Finder",
        "dom_whois": "WHOIS Lookup",
        "dom_to_ip": "Domain to IP",
        "dom_reverse_ip": "Reverse IP",
        "acc_username": "Username Search",
        "acc_github": "GitHub Info",
        "phone_lookup": "Phone Lookup",
        "web_tech": "Web Technology",
        "web_info": "Website Info",
        "web_crawler": "Crawler",
        "web_robots": "robots.txt",
        "web_sitemap": "sitemap.xml",
        "web_admin": "Admin Finder",
        "web_methods": "HTTP Methods",
        "email_lookup": "Email Lookup",
        "report_domain": "Domain Report",
        "report_ip": "IP Report",
        "report_social": "Social Report"
    }
    tool_name = tool_names.get(state, state)
    
    # ====== بدء التوقيت ======
    start_time = time.time()
    
    # ====== إزالة أي علم سابق ======
    animation_stop_flags[user_id] = False
    
    # ====== تشغيل الأنيميشن الشرطي ======
    if last_bot:
        show_loading_if_slow(chat_id, last_bot, tool_name, start_time, user_id)
    
    # ====== تنفيذ الفحص ======
    result = None
    try:
        if state == "net_ip":
            result = ip_intelligence(text)
        elif state == "net_port_basic":
            result = port_scanner_basic(text)
        elif state == "net_reverse_dns":
            result = reverse_dns(text)
        elif state == "net_ping":
            result = ping_test(text)
        elif state == "dom_dns":
            result = dns_lookup(text)
        elif state == "dom_subdomain":
            result = subdomain_finder(text)
        elif state == "dom_whois":
            result = whois_lookup(text)
        elif state == "dom_to_ip":
            result = domain_to_ip(text)
        elif state == "dom_reverse_ip":
            result = reverse_ip(text)
        elif state == "acc_username":
            result = username_search_parallel(text)
        elif state == "acc_github":
            result = github_user_info(text)
        elif state == "phone_lookup":
            result = phone_lookup(text)
        elif state == "web_tech":
            result = web_technology(text)
        elif state == "web_info":
            result = website_info(text)
        elif state == "web_crawler":
            result = crawler(text)
        elif state == "web_robots":
            result = robots_txt(text)
        elif state == "web_sitemap":
            result = sitemap_xml(text)
        elif state == "web_admin":
            result = admin_finder(text)
        elif state == "web_methods":
            result = http_methods(text)
        elif state == "email_lookup":
            result = email_lookup(text)
        elif state == "report_domain":
            result = quick_report_domain(text)
        elif state == "report_ip":
            result = quick_report_ip(text)
        elif state == "report_social":
            result = social_report(text)
        else:
            result = "⚠️ أداة غير معروفة."

        # ====== إيقاف الأنيميشن فوراً ======
        animation_stop_flags[user_id] = True

        # ====== عرض النتيجة ======
        if result:
            last_bot = user_last_bot_msg.get(user_id)
            if last_bot:
                edit_message(chat_id, last_bot, result, result_buttons(state), disable_preview=True)
            else:
                send_message(chat_id, result, result_buttons(state), disable_preview=True)
            log_action(user_id, username, state, result[:100])
            
    except Exception as e:
        # ====== إيقاف الأنيميشن في حالة الخطأ ======
        animation_stop_flags[user_id] = True
        
        err_msg = f"❌ خطأ: {str(e)}"
        last_bot = user_last_bot_msg.get(user_id)
        if last_bot:
            edit_message(chat_id, last_bot, err_msg, back_main_button())
        else:
            send_message(chat_id, err_msg, back_main_button())
        log_action(user_id, username, state, f"ERROR: {str(e)}")

# ========== التشغيل الرئيسي ==========

def main():
    global last_update_id
    last_update_id = 0
    try:
        resp = requests.get(f"{API_URL}/getUpdates", params={"offset": -1, "timeout": 0})
        if resp.status_code == 200 and resp.json().get("ok") and resp.json().get("result"):
            last_update_id = resp.json()["result"][-1]["update_id"] + 1
    except:
        pass
    print("="*70)
    print("🔱 OSINT BOT - FINAL VERSION")
    print("✅ جميع الأدوات الأصلية تعمل")
    print("✅ إضافات جديدة: HTTP Methods, Quick Reports")
    print("✅ أنيميشن يظهر فقط للفحوصات الطويلة ويتوقف فوراً عند ظهور النتيجة")
    print("✅ Web موحدة في قائمة واحدة")
    print("="*70)
    while True:
        try:
            params = {"timeout": 30, "offset": last_update_id + 1}
            r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=35)
            if r.status_code == 200:
                data = r.json()
                if data.get("ok"):
                    for update in data["result"]:
                        uid = update["update_id"]
                        if uid <= last_update_id:
                            continue
                        last_update_id = uid
                        if "callback_query" in update:
                            process_callback(update["callback_query"])
                        elif "message" in update:
                            process_message(update["message"])
        except Exception as e:
            print(f"خطأ: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
