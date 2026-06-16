from flask import Flask, render_template_string, request, session, redirect, jsonify, send_file, make_response
import json, os, random, string, time, hashlib, threading, shutil, urllib.request as _ureq, urllib.parse, math, mimetypes
from datetime import datetime, timezone, timedelta
from werkzeug.utils import secure_filename
try:
    import requests as _req
    _REQ_OK = True
except ImportError:
    _req = None
    _REQ_OK = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'shoptminh_2026_secret_key_xin_cam_on_ban_da_su_dung')
app.permanent_session_lifetime = timedelta(days=30)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = '/data' if os.path.isdir('/data') else BASE_DIR
DB_FILE = os.path.join(DATA_DIR, 'database.json')
os.makedirs(DATA_DIR, exist_ok=True)

VN_TZ = timezone(timedelta(hours=7))
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
ADMIN_TG_ID = os.environ.get('ADMIN_TG_ID', '')
ADMIN_TG_USERNAME = os.environ.get('ADMIN_TG_USERNAME', '')
ADMIN_USER = os.environ.get('ADMIN_USER', 'mtuan')
ADMIN_PASS = os.environ.get('ADMIN_PASS', '123')
TIKTOK_URL = 'https://www.tiktok.com/@ptminh_adr.trumfileff?_r=1&_t=ZS-97EYuCnWbjA'
ZALO_PHONE = '0904700559'
FACEBOOK_URL = ''

BANK_NAME = os.environ.get('BANK_NAME', 'ZaloPay')
BANK_ACCOUNT = os.environ.get('BANK_ACCOUNT', '')
BANK_HOLDER = os.environ.get('BANK_HOLDER', 'Phạm Tuấn Minh')

# ── ANTI-DDOS ─────────────────────────────────────────────────────────────────
_RATE = {}
_ACTION_RATE = {}
_BANNED = {}
_RLOCK = threading.Lock()

def get_real_ip():
    for h in ['CF-Connecting-IP', 'X-Real-IP', 'X-Forwarded-For']:
        v = request.headers.get(h)
        if v:
            return v.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

def check_ddos(ip):
    now = time.time()
    with _RLOCK:
        ban_until = _BANNED.get(ip, 0)
        if ban_until > now:
            return False, int(ban_until - now)
        ts = [t for t in _RATE.get(ip, []) if now - t < 60]
        ts.append(now)
        _RATE[ip] = ts
        count = len(ts)
        if count > 200:
            _BANNED[ip] = now + 600
            _RATE[ip] = []
            return False, 600
        if count > 150:
            _BANNED[ip] = now + 120
            _RATE[ip] = []
            return False, 120
        return True, 0

def check_rate(ip, mx=30, win=60):
    now = time.time()
    with _RLOCK:
        ts = [t for t in _ACTION_RATE.get(ip, []) if now - t < win]
        if len(ts) >= mx:
            _ACTION_RATE[ip] = ts
            return False
        ts.append(now)
        _ACTION_RATE[ip] = ts
        return True

def cleanup_rate():
    while True:
        time.sleep(120)
        now = time.time()
        with _RLOCK:
            for ip in list(_RATE.keys()):
                _RATE[ip] = [t for t in _RATE[ip] if now - t < 120]
                if not _RATE[ip]:
                    del _RATE[ip]
            for ip in list(_ACTION_RATE.keys()):
                _ACTION_RATE[ip] = [t for t in _ACTION_RATE[ip] if now - t < 120]
                if not _ACTION_RATE[ip]:
                    del _ACTION_RATE[ip]
            for ip in list(_BANNED.keys()):
                if _BANNED[ip] < now:
                    del _BANNED[ip]
threading.Thread(target=cleanup_rate, daemon=True).start()

# ── DB + CACHE ─────────────────────────────────────────────────────────────────
_DB_CACHE = {'data': None, 'ts': 0.0}
_DB_CACHE_TTL = 2.0

def _default_db():
    return {
        'users': {}, 'accounts': {'kim_cuong': [], 'bach_kim': [], 'lv5': []},
        'orders': [], 'carry_orders': [], 'keys': {}, 'daily_keys': {}, 'admin_notice': '',
        'notice_tg_link': '', 'notice_zalo_link': '', 'notice_btn_desc': '',
        'logs': [], 'revenue': {}, 'topup_requests': {}, 'feedback_posts': [],
        'custom_accs': [], 'sub_admins': [], 'ff_files': [], 'discount_codes': {}, 'ff_file_orders': []
    }

def load_db():
    global _DB_CACHE
    now = time.time()
    if _DB_CACHE['data'] is not None and (now - _DB_CACHE['ts']) < _DB_CACHE_TTL:
        try:
            return json.loads(json.dumps(_DB_CACHE['data']))
        except Exception:
            pass
    if not os.path.exists(DB_FILE):
        d = _default_db()
        _DB_CACHE['data'] = d
        _DB_CACHE['ts'] = now
        return _default_db()
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        for k, v in _default_db().items():
            if k not in d:
                d[k] = v
        _DB_CACHE['data'] = d
        _DB_CACHE['ts'] = now
        return d
    except Exception:
        return _default_db()

def save_db(d):
    global _DB_CACHE
    _DB_CACHE['data'] = None
    _DB_CACHE['ts'] = 0.0
    tmp = DB_FILE + '.tmp'
    bak = DB_FILE + '.bak'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        if os.path.exists(DB_FILE):
            shutil.copy2(DB_FILE, bak)
        os.replace(tmp, DB_FILE)
    except Exception:
        pass

def add_log(db, event, detail, user='system'):
    ts = datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M:%S')
    db['logs'].insert(0, {'time': ts, 'event': event, 'detail': detail, 'user': user})
    if len(db['logs']) > 1000:
        db['logs'] = db['logs'][:1000]

# ── HELPERS ────────────────────────────────────────────────────────────────────
def tg_send(chat_id, text, reply_markup=None):
    if not _REQ_OK or not BOT_TOKEN or not chat_id: return
    payload = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        _req.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                  json=payload, timeout=8)
    except Exception:
        pass

def tg_edit_message(chat_id, message_id, text, reply_markup=None):
    if not _REQ_OK or not BOT_TOKEN: return
    payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        _req.post(f'https://api.telegram.org/bot{BOT_TOKEN}/editMessageText',
                  json=payload, timeout=8)
    except Exception:
        pass

def tg_answer_callback(callback_id, text=''):
    if not _REQ_OK or not BOT_TOKEN: return
    try:
        _req.post(f'https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery',
                  json={'callback_query_id': callback_id, 'text': text}, timeout=5)
    except Exception:
        pass

def tg_admin(text, reply_markup=None):
    if ADMIN_TG_ID:
        tg_send(ADMIN_TG_ID, text, reply_markup)

def now_vn():
    return datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M:%S')

def rand_id(n=8):
    return ''.join(random.choices(string.digits, k=n))

def rand_content():
    chars = string.ascii_uppercase + string.digits
    return 'NAPTIEN' + ''.join(random.choices(chars, k=8))

def _find_user(db, query):
    q = query.strip().lower()
    for uid, u in db['users'].items():
        if u.get('username', '').lower() == q or u.get('display', '').lower() == q or uid == q:
            return uid
    return None

def calc_carry_price(rank, stars):
    high_ranks = ['Cao Thủ', 'Thách Đấu']
    price_per_star = 1500 if rank in high_ranks else 1000
    total = stars * price_per_star
    total = math.ceil(total / 1000) * 1000
    if stars >= 10:
        discount = int(total * 0.10)
        total = total - discount
        total = math.ceil(total / 1000) * 1000
    return total, price_per_star

def is_admin():
    return session.get('is_admin') or session.get('is_sub_admin')

def is_main_admin():
    return session.get('is_admin')

# ── STATIC FILES ───────────────────────────────────────────────────────────────
STATIC_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.mp3', '.mp4', '.webm', '.webp', '.svg', '.ico', '.css', '.js', '.pdf', '.zip', '.rar', '.apk', '.txt'}
SKIP_PATHS = {'/healthz', '/tg-webhook', '/favicon.ico'}
SKIP_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.mp3', '.mp4', '.webm', '.webp', '.ico', '.css', '.js', '.svg', '.pdf', '.zip', '.rar', '.apk')

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/<path:fname>')
def static_flat(fname):
    if '..' in fname or fname.count('/') > 0:
        return 'Forbidden', 403
    ext = os.path.splitext(fname)[1].lower()
    if ext not in STATIC_EXTS:
        return page_not_found(None)
    fpath = os.path.join(BASE_DIR, fname)
    if os.path.isfile(fpath):
        mime = mimetypes.guess_type(fname)[0] or 'application/octet-stream'
        resp = make_response(send_file(fpath, mimetype=mime))
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    return page_not_found(None)

# ── MIDDLEWARE ─────────────────────────────────────────────────────────────────
@app.before_request
def before():
    if request.method == 'OPTIONS':
        return
    path = request.path
    if path.endswith(SKIP_EXTS):
        return
    if path in SKIP_PATHS:
        return
    ip = get_real_ip()
    ok, wait = check_ddos(ip)
    if not ok:
        if path.startswith('/api/') or path.startswith('/admin/api/'):
            return jsonify({'ok': False, 'msg': f'Quá nhiều yêu cầu. Thử lại sau {wait}s.'}), 429
        return make_response(
            f'<h1>429 Too Many Requests</h1><p>IP bị tạm khóa {wait}s. Vui lòng thử lại sau.</p>', 429)

@app.after_request
def after(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['X-XSS-Protection'] = '1; mode=block'
    return resp

def _ping():
    time.sleep(60)
    while True:
        time.sleep(12 * 60)
        try:
            host = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host:
                _ureq.urlopen(host.rstrip('/') + '/healthz', timeout=8)
        except Exception:
            pass
threading.Thread(target=_ping, daemon=True).start()

def _ping2():
    time.sleep(420)
    while True:
        time.sleep(14 * 60)
        try:
            host = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host:
                _ureq.urlopen(host.rstrip('/') + '/healthz', timeout=8)
        except Exception:
            pass
threading.Thread(target=_ping2, daemon=True).start()

@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok'})

@app.errorhandler(404)
def page_not_found(e):
    return """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Không tìm thấy - Shop TMinh</title>
<style>*{margin:0;padding:0;box-sizing:border-box;}body{font-family:system-ui,sans-serif;background:linear-gradient(135deg,#4f46e5,#7c3aed);min-height:100vh;display:flex;align-items:center;justify-content:center;}
.box{background:#fff;border-radius:24px;padding:2.5rem 2rem;text-align:center;max-width:340px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2);}
.emoji{font-size:3.5rem;margin-bottom:1rem;}h1{font-size:1.3rem;color:#1e1b4b;margin-bottom:.5rem;}
p{font-size:.85rem;color:#6b7280;margin-bottom:1.5rem;}
a{display:inline-block;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;text-decoration:none;padding:.75rem 1.75rem;border-radius:50px;font-weight:700;font-size:.9rem;}</style>
<script>setTimeout(()=>location.href='/',3000);</script></head>
<body><div class="box"><div class="emoji">🎮</div><h1>Trang không tồn tại</h1>
<p>Đang chuyển về trang chính sau 3 giây...</p><a href="/">Về Trang Chính</a></div></body></html>""", 404

@app.errorhandler(500)
def server_error(e):
    return """<!DOCTYPE html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lỗi Server - Shop TMinh</title>
<style>*{margin:0;padding:0;box-sizing:border-box;}body{font-family:system-ui,sans-serif;background:linear-gradient(135deg,#dc2626,#b91c1c);min-height:100vh;display:flex;align-items:center;justify-content:center;}
.box{background:#fff;border-radius:24px;padding:2.5rem 2rem;text-align:center;max-width:340px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2);}
.emoji{font-size:3.5rem;margin-bottom:1rem;}h1{font-size:1.3rem;color:#1e1b4b;margin-bottom:.5rem;}
p{font-size:.85rem;color:#6b7280;margin-bottom:1.5rem;}
a{display:inline-block;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;text-decoration:none;padding:.75rem 1.75rem;border-radius:50px;font-weight:700;font-size:.9rem;}</style>
<script>setTimeout(()=>location.href='/',5000);</script></head>
<body><div class="box"><div class="emoji">⚠️</div><h1>Lỗi server tạm thời</h1>
<p>Đang tự chuyển về trang chính sau 5 giây...</p><a href="/">Về Trang Chính</a></div></body></html>""", 500

# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('uid'):
        return redirect('/')
    error = ''
    prefill_user = request.args.get('u', '')
    need_captcha = not session.get('captcha_verified', False)
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pw = request.form.get('password', '').strip()
        if need_captcha:
            cap_ans = request.form.get('captcha_answer', '')
            cap_q = session.get('captcha_q')
            if str(cap_q) != str(cap_ans):
                error = '❌ Sai mã xác minh!'
                a, b = random.randint(1, 9), random.randint(1, 9)
                session['captcha_q'] = a + b
                return render_template_string(AUTH_TEMPLATE, mode='login', error=error, cap_a=a, cap_b=b, prefill_user=uname, need_captcha=need_captcha)
            session['captcha_verified'] = True
        if not uname or not pw:
            error = '⚠️ Vui lòng nhập đầy đủ!'
        else:
            db = load_db()
            found = None
            for uid, u in db['users'].items():
                if u.get('username', '').lower() == uname.lower():
                    found = (uid, u)
                    break
            if not found:
                error = '❌ Tài khoản không tồn tại!'
            elif u.get('locked'):
                error = '🔒 Tài khoản đã bị khóa! Liên hệ admin.'
            elif hashlib.sha256(pw.encode()).hexdigest() != found[1].get('pw'):
                error = '❌ Sai mật khẩu!'
            else:
                uid, u = found
                session.permanent = True
                session['uid'] = uid
                session['spw'] = u['pw']
                db['users'][uid]['last_login'] = now_vn()
                db['users'][uid]['last_ip'] = get_real_ip()
                add_log(db, 'Đăng nhập', f'{uname} từ {get_real_ip()}', uname)
                save_db(db)
                return redirect('/')
    a, b = random.randint(1, 9), random.randint(1, 9)
    session['captcha_q'] = a + b
    return render_template_string(AUTH_TEMPLATE, mode='login', error=error, cap_a=a, cap_b=b, prefill_user=prefill_user, need_captcha=need_captcha)

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if session.get('uid'):
        return redirect('/')
    error = ''
    need_captcha = not session.get('captcha_verified', False)
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pw = request.form.get('password', '').strip()
        display = request.form.get('display', '').strip() or uname
        if need_captcha:
            cap_ans = request.form.get('captcha_answer', '')
            cap_q = session.get('captcha_q')
            if str(cap_q) != str(cap_ans):
                error = '❌ Sai mã xác minh!'
                a, b = random.randint(1, 9), random.randint(1, 9)
                session['captcha_q'] = a + b
                return render_template_string(AUTH_TEMPLATE, mode='register', error=error, cap_a=a, cap_b=b, prefill_user='', need_captcha=need_captcha)
            session['captcha_verified'] = True
        if not uname or not pw:
            error = '⚠️ Vui lòng nhập đầy đủ!'
        elif len(uname) < 3:
            error = '⚠️ Tên đăng nhập ít nhất 3 ký tự!'
        elif len(pw) < 4:
            error = '⚠️ Mật khẩu ít nhất 4 ký tự!'
        else:
            db = load_db()
            duplicate = any(u.get('username', '').lower() == uname.lower() for u in db['users'].values())
            if duplicate:
                error = '⛔ Tên đăng nhập đã tồn tại!'
            else:
                uid = 'u' + rand_id(10)
                pw_hash = hashlib.sha256(pw.encode()).hexdigest()
                ip = get_real_ip()
                ua = request.headers.get('User-Agent', '')[:100]
                db['users'][uid] = {
                    'uid': uid, 'username': uname, 'display': display,
                    'pw': pw_hash, 'balance': 0, 'created': now_vn(),
                    'last_ip': ip, 'ua': ua, 'notifs': [], 'role': 'user',
                    'random_id': rand_id(8), 'locked': False
                }
                add_log(db, 'Đăng ký', f'User mới: {uname} | IP: {ip}', uname)
                save_db(db)
                return redirect(f'/login?u={urllib.parse.quote(uname)}&registered=1')
    a, b = random.randint(1, 9), random.randint(1, 9)
    session['captcha_q'] = a + b
    return render_template_string(AUTH_TEMPLATE, mode='register', error=error, cap_a=a, cap_b=b, prefill_user='', need_captcha=need_captcha)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/change-password', methods=['POST'])
def change_password():
    uid = session.get('uid')
    if not uid:
        return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    old_pw = request.form.get('old_pw', '')
    new_pw = request.form.get('new_pw', '')
    if len(new_pw) < 4:
        return jsonify({'ok': False, 'msg': 'Mật khẩu mới ít nhất 4 ký tự'})
    db = load_db()
    u = db['users'].get(uid)
    if not u:
        return jsonify({'ok': False, 'msg': 'Không tìm thấy tài khoản'})
    if hashlib.sha256(old_pw.encode()).hexdigest() != u['pw']:
        return jsonify({'ok': False, 'msg': 'Sai mật khẩu hiện tại'})
    new_hash = hashlib.sha256(new_pw.encode()).hexdigest()
    db['users'][uid]['pw'] = new_hash
    add_log(db, 'Đổi mật khẩu', f'{u["username"]} đổi mật khẩu', u['username'])
    save_db(db)
    session.clear()
    return jsonify({'ok': True, 'msg': 'Đổi thành công! Đang chuyển về đăng nhập...'})

# ══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTES
# ══════════════════════════════════════════════════════════════════════════════
def require_login():
    if not session.get('uid'):
        return redirect('/login')
    return None

@app.route('/')
def home():
    r = require_login()
    if r: return r
    db = load_db()
    notice = db.get('admin_notice', '')
    acc_counts = {k: len([a for a in v if not a.get('sold')]) for k, v in db['accounts'].items()}
    return render_template_string(MAIN_TEMPLATE, notice=notice, acc_counts=acc_counts)

@app.route('/profile-data')
def profile_data():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    u = db['users'].get(uid, {})
    return jsonify({
        'ok': True, 'display': u.get('display', u.get('username')),
        'username': u.get('username'), 'balance': u.get('balance', 0),
        'random_id': u.get('random_id', '00000000'),
        'created': u.get('created', ''), 'last_ip': u.get('last_ip', '')
    })

@app.route('/api/notice')
def api_notice():
    db = load_db()
    return jsonify({
        'notice': db.get('admin_notice', ''),
        'tg_link': db.get('notice_tg_link', ''),
        'zalo_link': db.get('notice_zalo_link', ''),
        'btn_desc': db.get('notice_btn_desc', '')
    })

@app.route('/api/balance')
def api_balance():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    u = db['users'].get(uid, {})
    new_notifs = len([n for n in u.get('notifs', []) if not n.get('read')])
    return jsonify({'ok': True, 'balance': u.get('balance', 0), 'new_notifs': new_notifs})

@app.route('/api/notifs')
def api_notifs():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    u = db['users'].get(uid, {})
    notifs = u.get('notifs', [])
    for n in notifs:
        n['read'] = True
    db['users'][uid]['notifs'] = notifs
    save_db(db)
    return jsonify({'ok': True, 'notifs': notifs[:30]})

@app.route('/api/acc-count')
def api_acc_count():
    db = load_db()
    return jsonify({k: len([a for a in v if not a.get('sold')]) for k, v in db['accounts'].items()})

@app.route('/api/feedbacks')
def api_feedbacks():
    db = load_db()
    posts = db.get('feedback_posts', [])
    return jsonify({'ok': True, 'posts': posts[:20]})

@app.route('/api/admins')
def api_admins():
    db = load_db()
    admins = []
    admins.append({
        'name': 'TMinh',
        'role': 'Admin Chính',
        'tiktok': TIKTOK_URL,
        'zalo': ZALO_PHONE,
        'facebook': FACEBOOK_URL,
        'avatar': '/anh_admin.jpg'
    })
    for sa in db.get('sub_admins', []):
        admins.append({
            'name': sa.get('name', ''),
            'role': sa.get('role', 'Quản Trị Phụ'),
            'tiktok': sa.get('tiktok', ''),
            'zalo': sa.get('zalo', ''),
            'facebook': sa.get('facebook', ''),
            'avatar': sa.get('avatar', '/anh_admin.jpg')
        })
    return jsonify({'ok': True, 'admins': admins})

# ── FF FILES API ───────────────────────────────────────────────────────────────
@app.route('/api/ff-files')
def api_ff_files():
    db = load_db()
    files = db.get('ff_files', [])
    try:
        page = max(1, int(request.args.get('page', 1)))
    except Exception:
        page = 1
    per_page = 6
    total = len(files)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    page_files = files[start:start + per_page]
    safe = []
    for f in page_files:
        safe.append({
            'id': f.get('id', ''),
            'name': f.get('name', ''),
            'image_url': f.get('image_url', ''),
            'desc': f.get('desc', ''),
            'price': f.get('price', 0),
            'video_url': f.get('video_url', ''),
            'added': f.get('added', '')
        })
    return jsonify({'ok': True, 'files': safe, 'total': total, 'page': page, 'total_pages': total_pages})

# ── TOPUP API ──────────────────────────────────────────────────────────────────
@app.route('/api/topup-request', methods=['POST'])
def api_topup_request():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    ip = get_real_ip()
    if not check_rate(ip, 10, 60):
        return jsonify({'ok': False, 'msg': 'Quá nhiều yêu cầu! Vui lòng thử lại sau.'})
    try:
        amount = int(request.form.get('amount', 0))
    except:
        return jsonify({'ok': False, 'msg': 'Số tiền không hợp lệ'})
    if amount < 1000:
        return jsonify({'ok': False, 'msg': 'Số tiền tối thiểu 1.000đ'})
    db = load_db()
    u = db['users'].get(uid)
    if not u: return jsonify({'ok': False, 'msg': 'Không tìm thấy tài khoản'})
    content = rand_content()
    expires = time.time() + 3600
    db.setdefault('topup_requests', {})[content] = {
        'uid': uid, 'username': u['username'], 'amount': amount,
        'content': content, 'created': now_vn(), 'expires': expires, 'status': 'pending',
        'bank_name': BANK_NAME, 'bank_account': BANK_ACCOUNT, 'bank_holder': BANK_HOLDER
    }
    add_log(db, 'Yêu cầu nạp tiền', f'{u["username"]} yêu cầu nạp {amount:,}đ | mã: {content}', u['username'])
    save_db(db)
    if BOT_TOKEN and ADMIN_TG_ID:
        kb = {'inline_keyboard': [[
            {'text': f'✅ Duyệt {amount:,}đ', 'callback_data': f'approve_{content}'},
            {'text': '❌ Từ chối', 'callback_data': f'reject_{content}'}
        ]]}
        def _notify():
            tg_send(ADMIN_TG_ID,
                f'💰 <b>Yêu cầu nạp tiền mới!</b>\n'
                f'👤 User: <b>{u["username"]}</b>\n'
                f'💵 Số tiền: <b>{amount:,}đ</b>\n'
                f'🏦 Nền tảng: <b>{BANK_NAME}</b>\n'
                f'👤 Chủ TK: <b>{BANK_HOLDER}</b>\n'
                f'📝 Nội dung CK: <code>{content}</code>\n'
                f'⏳ Hết hạn: 1 giờ\n'
                f'⏰ {now_vn()}', kb)
        threading.Thread(target=_notify, daemon=True).start()
    return jsonify({
        'ok': True, 'content': content,
        'expires': int(expires),
        'bank_name': BANK_NAME,
        'bank_account': BANK_ACCOUNT,
        'bank_holder': BANK_HOLDER
    })

@app.route('/api/my-topups')
def api_my_topups():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    topups = [r for r in db.get('topup_requests', {}).values() if r.get('uid') == uid]
    topups.sort(key=lambda x: x.get('created', ''), reverse=True)
    return jsonify({'ok': True, 'topups': topups[:20]})

@app.route('/api/my-orders')
def api_my_orders():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    orders = [o for o in db.get('orders', []) if o.get('uid') == uid]
    orders.reverse()
    return jsonify({'ok': True, 'orders': orders[:20]})

@app.route('/api/my-carries')
def api_my_carries():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    carries = [o for o in db.get('carry_orders', []) if o.get('uid') == uid]
    carries.reverse()
    return jsonify({'ok': True, 'carries': carries[:20]})

@app.route('/api/my-ff-orders')
def api_my_ff_orders():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    db = load_db()
    orders = [o for o in db.get('ff_file_orders', []) if o.get('uid') == uid]
    orders.reverse()
    return jsonify({'ok': True, 'orders': orders[:20]})

# ── BUY FF FILE API ────────────────────────────────────────────────────────────
@app.route('/api/buy-ff-file', methods=['POST'])
def api_buy_ff_file():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    ip = get_real_ip()
    if not check_rate(ip, 20, 60):
        return jsonify({'ok': False, 'msg': 'Quá nhiều yêu cầu! Vui lòng thử lại sau.'})
    ff_id = request.form.get('ff_id', '').strip()
    if not ff_id:
        return jsonify({'ok': False, 'msg': 'File không hợp lệ'})
    db = load_db()
    u = db['users'].get(uid)
    if not u: return jsonify({'ok': False, 'msg': 'Không tìm thấy tài khoản'})
    ff_item = next((f for f in db.get('ff_files', []) if f.get('id') == ff_id), None)
    if not ff_item:
        return jsonify({'ok': False, 'msg': 'File không tồn tại'})
    price = ff_item.get('price', 0)
    total = price
    # ── Discount code (optional) ───────────────────────────────────────────
    coupon_code = request.form.get('coupon_code', '').strip().upper()
    discount_pct = 0
    coupon_applied = False
    coupon_msg = ''
    if coupon_code and price > 0:
        codes = db.get('discount_codes', {})
        code_data = codes.get(coupon_code)
        if code_data:
            expires = code_data.get('expires', 0)
            if expires != 0 and time.time() > expires:
                coupon_msg = 'Mã giảm giá đã hết hạn!'
            elif uid in code_data.get('used_by', []):
                coupon_msg = 'Bạn đã dùng mã này rồi!'
            else:
                discount_pct = code_data.get('pct', 0)
                coupon_applied = True
        else:
            coupon_msg = 'Mã giảm giá không hợp lệ!'
    if coupon_applied and discount_pct > 0:
        discount_amt = int(total * discount_pct / 100)
        total = max(0, total - discount_amt)
    # ── Check already purchased ────────────────────────────────────────────
    already = any(o.get('ff_id') == ff_id and o.get('uid') == uid for o in db.get('ff_file_orders', []))
    if already:
        existing = next(o for o in db.get('ff_file_orders', []) if o.get('ff_id') == ff_id and o.get('uid') == uid)
        return jsonify({'ok': True, 'file_url': ff_item.get('file_url', ''), 'video_url': ff_item.get('video_url', ''), 'name': ff_item.get('name', ''), 'already_purchased': True, 'total': existing.get('total', 0)})
    # ── Balance check ──────────────────────────────────────────────────────
    if price > 0 and u.get('balance', 0) < total:
        short = total - u.get('balance', 0)
        return jsonify({'ok': False, 'msg': f'Số dư không đủ! Cần {total:,}đ, bạn có {u.get("balance",0):,}đ', 'need_topup': True, 'short': short, 'needed': total, 'have': u.get('balance', 0), 'coupon_msg': coupon_msg})
    if price > 0:
        db['users'][uid]['balance'] = u.get('balance', 0) - total
    if coupon_applied and coupon_code:
        db.setdefault('discount_codes', {}).setdefault(coupon_code, {}).setdefault('used_by', []).append(uid)
    order_id = 'FF' + rand_id(8)
    order = {
        'id': order_id, 'uid': uid, 'username': u['username'],
        'ff_id': ff_id, 'name': ff_item.get('name', ''),
        'total': total, 'price': price, 'time': now_vn(),
        'coupon': coupon_code if coupon_applied else '', 'discount_pct': discount_pct if coupon_applied else 0
    }
    db.setdefault('ff_file_orders', []).append(order)
    month_key = datetime.now(VN_TZ).strftime('%Y-%m')
    if price > 0:
        db['revenue'][month_key] = db['revenue'].get(month_key, 0) + total
    coupon_note = f' (mã {coupon_code} -{discount_pct}%)' if coupon_applied else ''
    add_log(db, 'Mua file FF', f'{u["username"]} mua "{ff_item.get("name","")}"{coupon_note} | {total:,}đ', u['username'])
    db['users'][uid].setdefault('notifs', []).insert(0, {
        'type': 'ff_file', 'msg': f'✅ Mua file "{ff_item.get("name","")}" thành công!{(" Trừ "+str(total)+"đ") if price>0 else " (Miễn phí)"}', 'time': now_vn()
    })
    save_db(db)
    return jsonify({'ok': True, 'file_url': ff_item.get('file_url', ''), 'video_url': ff_item.get('video_url', ''), 'name': ff_item.get('name', ''), 'total': total, 'coupon_applied': coupon_applied, 'discount_pct': discount_pct, 'coupon_msg': coupon_msg})

# ── SHOP API ──────────────────────────────────────────────────────────────────
PRICES = {'kim_cuong': 25000, 'bach_kim': 20000, 'lv5': 2500}
CAT_NAMES = {'kim_cuong': 'Clon Rank Kim Cương', 'bach_kim': 'Clon Bạch Kim', 'lv5': 'Clon Lv5 Google'}

@app.route('/api/buy', methods=['POST'])
def api_buy():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    ip = get_real_ip()
    if not check_rate(ip, 20, 60):
        return jsonify({'ok': False, 'msg': 'Quá nhiều yêu cầu! Vui lòng thử lại sau.'})
    cat = request.form.get('cat', '')
    try:
        qty = int(request.form.get('qty', 1))
    except:
        return jsonify({'ok': False, 'msg': 'Số lượng không hợp lệ'})
    if cat not in PRICES: return jsonify({'ok': False, 'msg': 'Loại acc không hợp lệ'})
    if qty < 1 or qty > 10: return jsonify({'ok': False, 'msg': 'Số lượng từ 1–10'})
    db = load_db()
    u = db['users'].get(uid)
    if not u: return jsonify({'ok': False, 'msg': 'Không tìm thấy tài khoản'})
    total = PRICES[cat] * qty
    avail = [a for a in db['accounts'].get(cat, []) if not a.get('sold')]
    if len(avail) < qty:
        return jsonify({'ok': False, 'msg': f'Chỉ còn {len(avail)} acc, không đủ {qty}!'})
    # ── Discount code (optional) ───────────────────────────────────────────
    coupon_code = request.form.get('coupon_code', '').strip().upper()
    discount_pct = 0
    coupon_applied = False
    coupon_msg = ''
    if coupon_code:
        codes = db.get('discount_codes', {})
        code_data = codes.get(coupon_code)
        if code_data:
            expires = code_data.get('expires', 0)
            if expires != 0 and time.time() > expires:
                coupon_msg = 'Mã giảm giá đã hết hạn!'
            elif uid in code_data.get('used_by', []):
                coupon_msg = 'Bạn đã dùng mã này rồi!'
            else:
                discount_pct = code_data.get('pct', 0)
                coupon_applied = True
        else:
            coupon_msg = 'Mã giảm giá không hợp lệ!'
    if coupon_applied and discount_pct > 0:
        discount_amt = int(total * discount_pct / 100)
        total = max(0, total - discount_amt)
    # ── End discount ───────────────────────────────────────────────────────
    if u.get('balance', 0) < total:
        short = total - u.get('balance', 0)
        return jsonify({
            'ok': False,
            'msg': f'Số dư không đủ! Cần {total:,}đ, bạn có {u.get("balance",0):,}đ',
            'need_topup': True,
            'short': short,
            'needed': total,
            'have': u.get('balance', 0),
            'coupon_msg': coupon_msg
        })
    bought = avail[:qty]
    result_accs = []
    for a in bought:
        for i, acc in enumerate(db['accounts'][cat]):
            if acc.get('id') == a.get('id') and not acc.get('sold'):
                db['accounts'][cat][i].update({'sold': True, 'sold_to': uid, 'sold_to_name': u['username'], 'sold_time': now_vn()})
                result_accs.append(acc)
                break
    db['users'][uid]['balance'] = u.get('balance', 0) - total
    # Mark coupon used
    if coupon_applied and coupon_code:
        db.setdefault('discount_codes', {}).setdefault(coupon_code, {}).setdefault('used_by', []).append(uid)
    order_id = 'OD' + rand_id(8)
    db['orders'].append({
        'id': order_id, 'uid': uid, 'username': u['username'],
        'cat': cat, 'cat_name': CAT_NAMES[cat], 'qty': qty, 'total': total,
        'accs': result_accs, 'time': now_vn(),
        'coupon': coupon_code if coupon_applied else '', 'discount_pct': discount_pct if coupon_applied else 0
    })
    month_key = datetime.now(VN_TZ).strftime('%Y-%m')
    db['revenue'][month_key] = db['revenue'].get(month_key, 0) + total
    coupon_note = f' (mã {coupon_code} -{discount_pct}%)' if coupon_applied else ''
    add_log(db, 'Mua acc', f'{u["username"]} mua {qty} {CAT_NAMES[cat]} | {total:,}đ{coupon_note}', u['username'])
    db['users'][uid].setdefault('notifs', []).insert(0, {
        'type': 'purchase',
        'msg': f'✅ Mua {qty} acc {CAT_NAMES[cat]} thành công! Trừ {total:,}đ{coupon_note}', 'time': now_vn()
    })
    save_db(db)
    if BOT_TOKEN and ADMIN_TG_ID:
        threading.Thread(target=tg_admin, args=(
            f'🛒 <b>Đơn hàng mới!</b>\n👤 {u["username"]}\n📦 {qty}x {CAT_NAMES[cat]}\n💰 {total:,}đ{coupon_note}\n⏰ {now_vn()}',
        ), daemon=True).start()
    return jsonify({'ok': True, 'accs': result_accs, 'total': total, 'new_balance': db['users'][uid]['balance'],
                    'coupon_applied': coupon_applied, 'discount_pct': discount_pct, 'coupon_msg': coupon_msg})

# ── CARRY API ─────────────────────────────────────────────────────────────────
VALID_RANKS = ['Đồng', 'Bạc', 'Vàng', 'Bạch Kim', 'Kim Cương', 'Cao Thủ', 'Thách Đấu']

@app.route('/api/carry-order', methods=['POST'])
def api_carry_order():
    uid = session.get('uid')
    if not uid: return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    ip = get_real_ip()
    if not check_rate(ip, 20, 60):
        return jsonify({'ok': False, 'msg': 'Quá nhiều yêu cầu!'})
    try:
        stars = int(request.form.get('stars', 0))
    except:
        return jsonify({'ok': False, 'msg': 'Số sao không hợp lệ'})
    rank = request.form.get('rank', '').strip()
    note = request.form.get('note', '').strip()
    if stars < 5:
        return jsonify({'ok': False, 'msg': 'Tối thiểu 5 sao mới nhận kéo!'})
    if stars > 200:
        return jsonify({'ok': False, 'msg': 'Số sao tối đa 200'})
    if not rank or rank not in VALID_RANKS:
        return jsonify({'ok': False, 'msg': 'Vui lòng chọn rank hiện tại hợp lệ'})
    total, price_per_star = calc_carry_price(rank, stars)
    db = load_db()
    u = db['users'].get(uid)
    if not u: return jsonify({'ok': False, 'msg': 'Không tìm thấy tài khoản'})
    if u.get('balance', 0) < total:
        short = total - u.get('balance', 0)
        return jsonify({
            'ok': False,
            'msg': f'Số dư không đủ! Cần {total:,}đ, bạn có {u.get("balance",0):,}đ',
            'need_topup': True,
            'needed': total,
            'short': short
        })
    db['users'][uid]['balance'] = u.get('balance', 0) - total
    order_id = 'CR' + rand_id(8)
    db.setdefault('carry_orders', []).append({
        'id': order_id, 'uid': uid, 'username': u['username'],
        'stars': stars, 'rank': rank, 'note': note,
        'total': total, 'price_per_star': price_per_star, 'time': now_vn(), 'status': 'pending'
    })
    month_key = datetime.now(VN_TZ).strftime('%Y-%m')
    db['revenue'][month_key] = db['revenue'].get(month_key, 0) + total
    add_log(db, 'Kéo thuê FF', f'{u["username"]} kéo {stars} sao rank {rank} ({price_per_star:,}đ/sao) | {total:,}đ', u['username'])
    db['users'][uid].setdefault('notifs', []).insert(0, {
        'type': 'carry',
        'msg': f'✅ Đặt kéo thuê {stars} sao (rank {rank}) thành công! Trừ {total:,}đ. Liên hệ admin TMinh để kéo.',
        'time': now_vn()
    })
    save_db(db)
    if BOT_TOKEN and ADMIN_TG_ID:
        threading.Thread(target=tg_admin, args=(
            f'🏆 <b>Đơn kéo thuê mới!</b>\n👤 {u["username"]}\n⭐ {stars} sao\n🎮 Rank: {rank}\n💵 Đơn giá: {price_per_star:,}đ/sao\n📝 Ghi chú: {note or "Không có"}\n💰 {total:,}đ\n⏰ {now_vn()}',
        ), daemon=True).start()
    sub_admins = db.get('sub_admins', [])
    sub_contact = ''
    if sub_admins:
        sa = sub_admins[0]
        sub_contact = sa.get('name', '')
    return jsonify({
        'ok': True, 'total': total,
        'new_balance': db['users'][uid]['balance'],
        'order_id': order_id,
        'tiktok_url': TIKTOK_URL,
        'zalo_phone': ZALO_PHONE,
        'sub_contact': sub_contact
    })

# ── CUSTOM ACC API ─────────────────────────────────────────────────────────────
@app.route('/api/custom-accs')
def api_custom_accs():
    db = load_db()
    accs = db.get('custom_accs', [])
    try:
        page = max(1, int(request.args.get('page', 1)))
    except Exception:
        page = 1
    per_page = 5
    total = len(accs)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    page_accs = accs[start:start + per_page]
    safe = []
    for a in page_accs:
        safe.append({
            'id': a.get('id', ''),
            'image_url': a.get('image_url', ''),
            'platform': a.get('platform', ''),
            'desc': a.get('desc', ''),
            'price': a.get('price', 0),
            'added': a.get('added', '')
        })
    return jsonify({'ok': True, 'accs': safe, 'total': total, 'page': page, 'total_pages': total_pages})

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('is_admin'): return redirect('/admin/panel')
    if session.get('is_sub_admin'): return redirect('/admin/panel')
    error = ''
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pw = request.form.get('password', '').strip()
        if uname == ADMIN_USER and pw == ADMIN_PASS:
            session['is_admin'] = True
            session.permanent = True
            return redirect('/admin/panel')
        # Check sub-admin login
        db = load_db()
        for sa in db.get('sub_admins', []):
            if sa.get('username') == uname and sa.get('password') == pw:
                session['is_sub_admin'] = True
                session['sub_admin_id'] = sa.get('id')
                session.permanent = True
                return redirect('/admin/panel')
        error = '❌ Sai tài khoản hoặc mật khẩu!'
    return render_template_string(ADMIN_LOGIN_TMPL, error=error)

@app.route('/admin/panel')
def admin_panel():
    if not session.get('is_admin') and not session.get('is_sub_admin'):
        return redirect('/admin')
    db = load_db()
    stats = {
        'users': len(db['users']), 'orders': len(db['orders']),
        'revenue': sum(db['revenue'].values()),
        'carry_orders': len(db.get('carry_orders', [])),
        'acc_kim': len([a for a in db['accounts'].get('kim_cuong', []) if not a.get('sold')]),
        'acc_bach': len([a for a in db['accounts'].get('bach_kim', []) if not a.get('sold')]),
        'acc_lv5': len([a for a in db['accounts'].get('lv5', []) if not a.get('sold')]),
        'acc_kim_total': len(db['accounts'].get('kim_cuong', [])),
        'acc_bach_total': len(db['accounts'].get('bach_kim', [])),
        'acc_lv5_total': len(db['accounts'].get('lv5', [])),
        'pending_topup': len([r for r in db.get('topup_requests', {}).values() if r.get('status') == 'pending']),
        'feedback_count': len(db.get('feedback_posts', []))
    }
    is_main = bool(session.get('is_admin'))
    return render_template_string(ADMIN_PANEL_TMPL, db=db, stats=stats, TIKTOK_URL=TIKTOK_URL, is_main=is_main)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    session.pop('is_sub_admin', None)
    session.pop('sub_admin_id', None)
    return redirect('/admin')

@app.route('/admin/api/add-acc', methods=['POST'])
def admin_add_acc():
    if not session.get('is_admin'): return jsonify({'ok': False, 'msg': 'Chỉ admin chính mới được thêm acc'})
    db = load_db()
    cat = request.form.get('cat', '')
    bulk = request.form.get('bulk_accs', '').strip()
    added = 0
    if bulk:
        for line in bulk.split('\n'):
            line = line.strip()
            if not line: continue
            pp = [x.strip() for x in line.split(':')]
            if len(pp) < 2: continue
            acc = {
                'id': rand_id(10), 'user': pp[0], 'pass': pp[1],
                'platform': pp[2] if len(pp) > 2 else 'Facebook',
                'desc': pp[3] if len(pp) > 3 else '', 'added': now_vn(), 'sold': False
            }
            db['accounts'].setdefault(cat, []).append(acc)
            added += 1
    else:
        u = request.form.get('acc_user', '').strip()
        p = request.form.get('acc_pass', '').strip()
        platform = request.form.get('acc_platform', 'Facebook').strip()
        desc = request.form.get('acc_desc', '').strip()
        if u and p:
            acc = {'id': rand_id(10), 'user': u, 'pass': p, 'platform': platform, 'desc': desc, 'added': now_vn(), 'sold': False}
            db['accounts'].setdefault(cat, []).append(acc)
            added = 1
    add_log(db, 'Admin thêm acc', f'+{added} acc {cat}', 'admin')
    save_db(db)
    return jsonify({'ok': True, 'added': added})

@app.route('/admin/api/del-acc', methods=['POST'])
def admin_del_acc():
    if not session.get('is_admin'): return jsonify({'ok': False})
    db = load_db()
    cat = request.form.get('cat')
    acc_id = request.form.get('id')
    before = len(db['accounts'].get(cat, []))
    db['accounts'][cat] = [a for a in db['accounts'].get(cat, []) if a.get('id') != acc_id]
    save_db(db)
    return jsonify({'ok': True, 'removed': before - len(db['accounts'][cat])})

@app.route('/admin/api/balance', methods=['POST'])
def admin_balance():
    if not session.get('is_admin'): return jsonify({'ok': False, 'msg': 'Chỉ admin chính'})
    db = load_db()
    query = request.form.get('user', '').strip()
    action = request.form.get('action', 'add')
    try:
        amount = int(request.form.get('amount', 0))
    except:
        return jsonify({'ok': False, 'msg': 'Số tiền không hợp lệ'})
    if not query: return jsonify({'ok': False, 'msg': 'Vui lòng nhập tên user'})
    uid = _find_user(db, query)
    if not uid: return jsonify({'ok': False, 'msg': f'❌ Không tìm thấy user "{query}"'})
    old = db['users'][uid].get('balance', 0)
    if action == 'add':
        db['users'][uid]['balance'] = old + amount
        notif_msg = f'✅ Bạn được cộng {amount:,}đ vào tài khoản!'
    else:
        db['users'][uid]['balance'] = max(0, old - amount)
        notif_msg = f'⚠️ Tài khoản bị trừ {amount:,}đ.'
    db['users'][uid].setdefault('notifs', []).insert(0, {'type': 'balance', 'msg': notif_msg, 'time': now_vn()})
    add_log(db, f'Admin {action} tiền', f'{action} {amount:,}đ cho {db["users"][uid]["username"]}', 'admin')
    save_db(db)
    return jsonify({'ok': True, 'new_balance': db['users'][uid]['balance'], 'username': db['users'][uid]['username']})

@app.route('/admin/api/lock-user', methods=['POST'])
def admin_lock_user():
    if not session.get('is_admin') and not session.get('is_sub_admin'):
        return jsonify({'ok': False, 'msg': 'Không có quyền'})
    db = load_db()
    uid = request.form.get('uid', '')
    action = request.form.get('action', 'lock')
    if uid not in db['users']:
        return jsonify({'ok': False, 'msg': 'Không tìm thấy user'})
    db['users'][uid]['locked'] = (action == 'lock')
    uname = db['users'][uid].get('username', uid)
    add_log(db, f'{"Khóa" if action=="lock" else "Mở"} tài khoản', uname, 'admin')
    save_db(db)
    return jsonify({'ok': True})

@app.route('/admin/api/approve-topup', methods=['POST'])
def admin_approve_topup():
    if not session.get('is_admin'): return jsonify({'ok': False})
    content = request.form.get('content', '').strip()
    try:
        amount = int(request.form.get('amount', 0))
    except:
        amount = 0
    db = load_db()
    _do_approve_topup(db, content, amount if amount > 0 else None)
    return jsonify({'ok': True})

@app.route('/admin/api/reject-topup', methods=['POST'])
def admin_reject_topup():
    if not session.get('is_admin'): return jsonify({'ok': False})
    content = request.form.get('content', '').strip()
    db = load_db()
    req = db.get('topup_requests', {}).get(content)
    if req:
        req['status'] = 'rejected'
        uid = req.get('uid')
        if uid and uid in db['users']:
            db['users'][uid].setdefault('notifs', []).insert(0, {
                'type': 'admin', 'msg': f'❌ Yêu cầu nạp {req["amount"]:,}đ bị từ chối. Liên hệ admin.', 'time': now_vn()
            })
        save_db(db)
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': 'Không tìm thấy'})

@app.route('/admin/api/notice', methods=['POST'])
def admin_notice():
    if not session.get('is_admin'): return jsonify({'ok': False})
    db = load_db()
    db['admin_notice'] = request.form.get('notice', '')
    db['notice_tg_link'] = request.form.get('tg_link', '').strip()
    db['notice_zalo_link'] = request.form.get('zalo_link', '').strip()
    db['notice_btn_desc'] = request.form.get('btn_desc', '').strip()
    save_db(db)
    return jsonify({'ok': True})

@app.route('/admin/api/approve-carry', methods=['POST'])
def admin_approve_carry():
    if not session.get('is_admin'): return jsonify({'ok': False})
    order_id = request.form.get('order_id', '').strip()
    db = load_db()
    for i, o in enumerate(db.get('carry_orders', [])):
        if o.get('id') == order_id:
            db['carry_orders'][i]['status'] = 'done'
            uid = o.get('uid')
            if uid and uid in db['users']:
                db['users'][uid].setdefault('notifs', []).insert(0, {
                    'type': 'carry',
                    'msg': f'✅ Đơn kéo thuê {o["stars"]} sao (rank {o["rank"]}) đã hoàn thành! Liên hệ admin TMinh để nhận kết quả.',
                    'time': now_vn()
                })
            add_log(db, 'Admin duyệt kéo thuê', f'{o["username"]} - {o["stars"]} sao rank {o["rank"]}', 'admin')
            save_db(db)
            return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': 'Không tìm thấy đơn'})

@app.route('/admin/api/send-msg', methods=['POST'])
def admin_send_msg():
    if not session.get('is_admin'): return jsonify({'ok': False})
    db = load_db()
    query = request.form.get('user', '').strip()
    msg_text = request.form.get('msg', '').strip()
    if not query: return jsonify({'ok': False, 'msg': 'Nhập tên user'})
    uid = _find_user(db, query)
    if not uid: return jsonify({'ok': False, 'msg': f'❌ Không tìm thấy user "{query}"'})
    db['users'][uid].setdefault('notifs', []).insert(0, {'type': 'admin', 'msg': msg_text, 'time': now_vn()})
    save_db(db)
    return jsonify({'ok': True})

@app.route('/admin/api/del-user', methods=['POST'])
def admin_del_user():
    if not session.get('is_admin'): return jsonify({'ok': False})
    db = load_db()
    uid = request.form.get('uid', '')
    if uid in db['users']:
        uname = db['users'][uid].get('username', uid)
        del db['users'][uid]
        add_log(db, 'Admin xóa user', uname, 'admin')
        save_db(db)
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'msg': 'Không tìm thấy'})

@app.route('/admin/api/logs')
def admin_logs_api():
    if not session.get('is_admin') and not session.get('is_sub_admin'): return jsonify({'ok': False})
    db = load_db()
    page = int(request.args.get('page', 1))
    per = 50
    logs = db.get('logs', [])
    total = len(logs)
    start = (page - 1) * per
    return jsonify({'ok': True, 'logs': logs[start:start+per], 'total': total, 'pages': (total + per - 1) // per})

@app.route('/admin/api/add-feedback', methods=['POST'])
def admin_add_feedback():
    if not session.get('is_admin'): return jsonify({'ok': False})
    desc = request.form.get('desc', '').strip()
    customer = request.form.get('customer', '').strip()
    media_url = request.form.get('media_url', '').strip()
    media_type = 'image'
    allowed_img = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    allowed_vid = {'.mp4', '.webm', '.mov'}
    file = request.files.get('media_file')
    if file and file.filename:
        fname_raw = secure_filename(file.filename)
        ext = os.path.splitext(fname_raw)[1].lower()
        if ext in allowed_img or ext in allowed_vid:
            unique_name = 'fb_' + rand_id(12) + ext
            save_path = os.path.join(BASE_DIR, unique_name)
            file.save(save_path)
            media_url = '/' + unique_name
            media_type = 'video' if ext in allowed_vid else 'image'
    elif media_url:
        ext = os.path.splitext(media_url.split('?')[0])[1].lower()
        media_type = 'video' if ext in allowed_vid else 'image'
    if not media_url and not desc:
        return jsonify({'ok': False, 'msg': 'Cần nhập mô tả hoặc đính kèm ảnh/video'})
    db = load_db()
    post = {
        'id': 'FB' + rand_id(10),
        'media_url': media_url, 'media_type': media_type,
        'desc': desc, 'customer': customer, 'time': now_vn()
    }
    db.setdefault('feedback_posts', []).insert(0, post)
    if len(db['feedback_posts']) > 50:
        db['feedback_posts'] = db['feedback_posts'][:50]
    add_log(db, 'Admin thêm feedback', f'{desc[:30] if desc else media_url[:30]}', 'admin')
    save_db(db)
    return jsonify({'ok': True, 'id': post['id']})

@app.route('/admin/api/del-feedback', methods=['POST'])
def admin_del_feedback():
    if not session.get('is_admin'): return jsonify({'ok': False})
    post_id = request.form.get('id', '')
    db = load_db()
    posts = db.get('feedback_posts', [])
    post_to_del = next((p for p in posts if p.get('id') == post_id), None)
    if post_to_del:
        media_url = post_to_del.get('media_url', '')
        if media_url and media_url.startswith('/fb_'):
            fpath = os.path.join(BASE_DIR, media_url.lstrip('/'))
            if os.path.isfile(fpath):
                try: os.remove(fpath)
                except: pass
    db['feedback_posts'] = [p for p in posts if p.get('id') != post_id]
    add_log(db, 'Admin xóa feedback', post_id, 'admin')
    save_db(db)
    return jsonify({'ok': True})

@app.route('/admin/api/add-custom-acc', methods=['POST'])
def admin_add_custom_acc():
    if not session.get('is_admin'):
        return jsonify({'ok': False})
    allowed_img = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    image_url = request.form.get('image_url', '').strip()
    file = request.files.get('image_file')
    if file and file.filename:
        fname_raw = secure_filename(file.filename)
        ext = os.path.splitext(fname_raw)[1].lower()
        if ext in allowed_img:
            unique_name = 'ca_' + rand_id(12) + ext
            save_path = os.path.join(BASE_DIR, unique_name)
            file.save(save_path)
            image_url = '/' + unique_name
    acc_user = request.form.get('acc_user', '').strip()
    acc_pass = request.form.get('acc_pass', '').strip()
    platform = request.form.get('platform', '').strip()
    desc = request.form.get('desc', '').strip()
    try:
        price = int(request.form.get('price', 0))
    except:
        price = 0
    acc = {
        'id': 'CA' + rand_id(12), 'image_url': image_url,
        'acc_user': acc_user, 'acc_pass': acc_pass,
        'platform': platform, 'desc': desc, 'price': price,
        'added': now_vn(), 'time': now_vn()
    }
    db = load_db()
    db.setdefault('custom_accs', []).insert(0, acc)
    add_log(db, 'Admin thêm acc tự chọn', f'{platform} | {price:,}đ', 'admin')
    save_db(db)
    return jsonify({'ok': True, 'id': acc['id']})

@app.route('/admin/api/del-custom-acc', methods=['POST'])
def admin_del_custom_acc():
    if not session.get('is_admin'):
        return jsonify({'ok': False})
    acc_id = request.form.get('id', '')
    db = load_db()
    accs = db.get('custom_accs', [])
    acc_to_del = next((a for a in accs if a.get('id') == acc_id), None)
    if acc_to_del:
        iu = acc_to_del.get('image_url', '')
        if iu and iu.startswith('/ca_'):
            fpath = os.path.join(BASE_DIR, iu.lstrip('/'))
            if os.path.isfile(fpath):
                try: os.remove(fpath)
                except: pass
    db['custom_accs'] = [a for a in accs if a.get('id') != acc_id]
    add_log(db, 'Admin xóa acc tự chọn', acc_id, 'admin')
    save_db(db)
    return jsonify({'ok': True})

# ── FF FILE API ─────────────────────────────────────────────────────────────────
@app.route('/admin/api/add-ff-file', methods=['POST'])
def admin_add_ff_file():
    if not session.get('is_admin'):
        return jsonify({'ok': False, 'msg': 'Chỉ admin chính'})
    allowed_img = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    allowed_vid = {'.mp4', '.webm', '.mov'}
    allowed_file = {'.zip', '.rar', '.apk', '.pdf', '.txt', '.json'}
    image_url = request.form.get('image_url', '').strip()
    img_file = request.files.get('image_file')
    if img_file and img_file.filename:
        fname_raw = secure_filename(img_file.filename)
        ext = os.path.splitext(fname_raw)[1].lower()
        if ext in allowed_img:
            unique_name = 'ffi_' + rand_id(12) + ext
            img_file.save(os.path.join(BASE_DIR, unique_name))
            image_url = '/' + unique_name
    file_url = ''
    dl_file = request.files.get('dl_file')
    if dl_file and dl_file.filename:
        fname_raw = secure_filename(dl_file.filename)
        ext = os.path.splitext(fname_raw)[1].lower()
        if ext in allowed_file:
            unique_name = 'ffd_' + rand_id(12) + ext
            dl_file.save(os.path.join(BASE_DIR, unique_name))
            file_url = '/' + unique_name
    video_url = request.form.get('video_url', '').strip()
    vid_file = request.files.get('video_file')
    if vid_file and vid_file.filename:
        fname_raw = secure_filename(vid_file.filename)
        ext = os.path.splitext(fname_raw)[1].lower()
        if ext in allowed_vid:
            unique_name = 'ffv_' + rand_id(12) + ext
            vid_file.save(os.path.join(BASE_DIR, unique_name))
            video_url = '/' + unique_name
    name = request.form.get('name', '').strip()
    desc = request.form.get('desc', '').strip()
    try:
        price = int(request.form.get('price', 0))
    except:
        price = 0
    if not name:
        return jsonify({'ok': False, 'msg': 'Vui lòng nhập tên file'})
    ff_item = {
        'id': 'FF' + rand_id(12),
        'name': name,
        'image_url': image_url,
        'file_url': file_url,
        'video_url': video_url,
        'desc': desc,
        'price': price,
        'added': now_vn()
    }
    db = load_db()
    db.setdefault('ff_files', []).insert(0, ff_item)
    add_log(db, 'Admin thêm file FF', f'{name} | {price:,}đ', 'admin')
    save_db(db)
    return jsonify({'ok': True, 'id': ff_item['id']})

@app.route('/admin/api/del-ff-file', methods=['POST'])
def admin_del_ff_file():
    if not session.get('is_admin'):
        return jsonify({'ok': False})
    ff_id = request.form.get('id', '')
    db = load_db()
    files = db.get('ff_files', [])
    item = next((f for f in files if f.get('id') == ff_id), None)
    if item:
        for field in ['image_url', 'file_url', 'video_url']:
            url = item.get(field, '')
            if url and url.startswith('/ff'):
                fpath = os.path.join(BASE_DIR, url.lstrip('/'))
                if os.path.isfile(fpath):
                    try: os.remove(fpath)
                    except: pass
    db['ff_files'] = [f for f in files if f.get('id') != ff_id]
    add_log(db, 'Admin xóa file FF', ff_id, 'admin')
    save_db(db)
    return jsonify({'ok': True})

# ── SUB-ADMIN API ─────────────────────────────────────────────────────────────
@app.route('/admin/api/add-sub-admin', methods=['POST'])
def admin_add_sub_admin():
    if not session.get('is_admin'):
        return jsonify({'ok': False, 'msg': 'Chỉ admin chính mới được thêm'})
    db = load_db()
    if len(db.get('sub_admins', [])) >= 4:
        return jsonify({'ok': False, 'msg': 'Tối đa 4 admin phụ'})
    name = request.form.get('name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'Quản Trị Phụ').strip()
    tiktok = request.form.get('tiktok', '').strip()
    facebook = request.form.get('facebook', '').strip()
    zalo = request.form.get('zalo', '').strip()
    if not name or not username or not password:
        return jsonify({'ok': False, 'msg': 'Vui lòng nhập đủ thông tin'})
    for sa in db.get('sub_admins', []):
        if sa.get('username') == username:
            return jsonify({'ok': False, 'msg': 'Tên đăng nhập đã tồn tại'})
    allowed_img = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    avatar_url = '/anh_admin.jpg'
    avatar_file = request.files.get('avatar_file')
    if avatar_file and avatar_file.filename:
        fname_raw = secure_filename(avatar_file.filename)
        ext = os.path.splitext(fname_raw)[1].lower()
        if ext in allowed_img:
            unique_name = 'sa_' + rand_id(12) + ext
            avatar_file.save(os.path.join(BASE_DIR, unique_name))
            avatar_url = '/' + unique_name
    sa = {
        'id': 'SA' + rand_id(8),
        'name': name,
        'username': username,
        'password': password,
        'role': role,
        'tiktok': tiktok,
        'facebook': facebook,
        'zalo': zalo,
        'avatar': avatar_url,
        'added': now_vn()
    }
    db.setdefault('sub_admins', []).append(sa)
    add_log(db, 'Thêm admin phụ', f'{name} ({username})', 'admin')
    save_db(db)
    return jsonify({'ok': True})

@app.route('/admin/api/del-sub-admin', methods=['POST'])
def admin_del_sub_admin():
    if not session.get('is_admin'):
        return jsonify({'ok': False, 'msg': 'Chỉ admin chính'})
    sa_id = request.form.get('id', '')
    db = load_db()
    db['sub_admins'] = [s for s in db.get('sub_admins', []) if s.get('id') != sa_id]
    add_log(db, 'Xóa admin phụ', sa_id, 'admin')
    save_db(db)
    return jsonify({'ok': True})

# ── DISCOUNT CODE API ──────────────────────────────────────────────────────────
@app.route('/api/check-coupon', methods=['POST'])
def api_check_coupon():
    uid = session.get('uid')
    if not uid:
        return jsonify({'ok': False, 'msg': 'Chưa đăng nhập'})
    code = request.form.get('code', '').strip().upper()
    cat = request.form.get('cat', '')
    try:
        qty = int(request.form.get('qty', 1))
    except Exception:
        qty = 1
    if not code:
        return jsonify({'ok': False, 'msg': 'Nhập mã giảm giá'})
    db = load_db()
    codes = db.get('discount_codes', {})
    code_data = codes.get(code)
    if not code_data:
        return jsonify({'ok': False, 'msg': '❌ Mã giảm giá không hợp lệ!'})
    expires = code_data.get('expires', 0)
    if expires != 0 and time.time() > expires:
        return jsonify({'ok': False, 'msg': '❌ Mã giảm giá đã hết hạn!'})
    if uid in code_data.get('used_by', []):
        return jsonify({'ok': False, 'msg': '❌ Bạn đã sử dụng mã này rồi!'})
    pct = code_data.get('pct', 0)
    base_total = PRICES.get(cat, 0) * qty if cat in PRICES else 0
    discount_amt = int(base_total * pct / 100)
    final_total = max(0, base_total - discount_amt)
    return jsonify({
        'ok': True,
        'msg': f'✅ Mã hợp lệ! Giảm {pct}%',
        'pct': pct,
        'base_total': base_total,
        'discount_amt': discount_amt,
        'final_total': final_total
    })

@app.route('/admin/api/add-coupon', methods=['POST'])
def admin_add_coupon():
    if not session.get('is_admin'):
        return jsonify({'ok': False, 'msg': 'Chỉ admin chính'})
    code = request.form.get('code', '').strip().upper()
    if not code:
        import random as _random
        import string as _string
        code = ''.join(_random.choices(_string.ascii_uppercase + _string.digits, k=8))
    try:
        pct = int(request.form.get('pct', 10))
        pct = max(1, min(100, pct))
    except Exception:
        pct = 10
    expires_type = request.form.get('expires_type', 'permanent')
    if expires_type == 'permanent':
        expires = 0
    else:
        try:
            days = int(request.form.get('expires_days', 7))
            expires = int(time.time() + days * 86400)
        except Exception:
            expires = 0
    db = load_db()
    codes = db.setdefault('discount_codes', {})
    if code in codes:
        return jsonify({'ok': False, 'msg': f'Mã "{code}" đã tồn tại!'})
    codes[code] = {
        'pct': pct,
        'expires': expires,
        'used_by': [],
        'created': now_vn()
    }
    add_log(db, 'Tạo mã giảm giá', f'{code} -{pct}% | {"Vĩnh viễn" if expires==0 else str(days)+" ngày"}', 'admin')
    save_db(db)
    return jsonify({'ok': True, 'code': code, 'pct': pct, 'expires': expires})

@app.route('/admin/api/del-coupon', methods=['POST'])
def admin_del_coupon():
    if not session.get('is_admin'):
        return jsonify({'ok': False, 'msg': 'Chỉ admin chính'})
    code = request.form.get('code', '').strip().upper()
    db = load_db()
    codes = db.get('discount_codes', {})
    if code not in codes:
        return jsonify({'ok': False, 'msg': 'Không tìm thấy mã'})
    del codes[code]
    add_log(db, 'Xóa mã giảm giá', code, 'admin')
    save_db(db)
    return jsonify({'ok': True})

def _do_approve_topup(db, content, amount=None):
    req = db.get('topup_requests', {}).get(content)
    if not req:
        return
    if req.get('status') != 'pending':
        return
    if amount is None:
        amount = req.get('amount', 0)
    uid = req.get('uid')
    if not uid or uid not in db['users']:
        return
    db['users'][uid]['balance'] = db['users'][uid].get('balance', 0) + amount
    db['users'][uid].setdefault('notifs', []).insert(0, {
        'type': 'balance', 'msg': f'✅ Nạp tiền thành công! <b>{amount:,}đ</b> đã được cộng vào tài khoản.', 'time': now_vn()
    })
    req['status'] = 'approved'
    req['approved_at'] = now_vn()
    add_log(db, 'Duyệt nạp tiền', f'+{amount:,}đ cho {req.get("username","?")} | mã: {content}', 'admin')
    save_db(db)

# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════
BASE_CSS = """
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Be Vietnam Pro',sans-serif;-webkit-tap-highlight-color:transparent;}
:root{--bg:#f8f9fb;--white:#fff;--primary:#1a1a2e;--accent:#4f46e5;--accent2:#7c3aed;--green:#10b981;--red:#ef4444;--orange:#f59e0b;--text:#1f2937;--muted:#6b7280;--border:#e5e7eb;--sh:0 4px 24px rgba(0,0,0,.08);}
html{scroll-behavior:smooth;}
body{background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased;}
a{text-decoration:none;color:inherit;}
#ls{position:fixed;inset:0;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:9999;transition:opacity .4s ease;}
.ls-logo{font-size:2rem;font-weight:800;color:var(--primary);margin-bottom:1rem;}
.ls-logo span{color:var(--accent);}
.ls-bar{width:200px;height:3px;background:#e5e7eb;border-radius:9px;overflow:hidden;margin-bottom:1.5rem;}
.ls-fill{height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:9px;animation:lsfill .8s ease forwards;}
@keyframes lsfill{0%{width:0}60%{width:75%}100%{width:100%}}
.ls-text{color:var(--muted);font-size:.85rem;font-weight:500;}
.navbar{position:fixed;top:0;left:0;right:0;background:rgba(255,255,255,.95);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);height:58px;display:flex;align-items:center;padding:0 1.1rem;z-index:1000;gap:.75rem;}
.nav-logo{font-size:1.1rem;font-weight:800;color:var(--primary);flex:1;}
.nav-logo span{color:var(--accent);}
.nav-bal{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;padding:.28rem .85rem;border-radius:20px;font-size:.78rem;font-weight:700;cursor:pointer;white-space:nowrap;transition:transform .15s ease;}
.nav-bal:active{transform:scale(.94);}
.nav-bell{cursor:pointer;width:36px;height:36px;display:flex;align-items:center;justify-content:center;border-radius:10px;background:#f3f4f6;position:relative;flex-shrink:0;transition:transform .15s ease;}
.nav-bell:active{transform:scale(.9);}
.notif-dot{position:absolute;top:4px;right:4px;width:7px;height:7px;background:var(--red);border-radius:50%;display:none;}
.hamburger{cursor:pointer;padding:.35rem;display:flex;flex-direction:column;gap:5px;transition:transform .15s ease;}
.hamburger span{display:block;width:21px;height:2px;background:var(--primary);border-radius:2px;transition:.3s;}
.hamburger:active{transform:scale(.9);}
.doverlay{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:2000;opacity:0;pointer-events:none;transition:opacity .28s ease;backdrop-filter:blur(3px);}
.doverlay.open{opacity:1;pointer-events:all;}
.drawer{position:fixed;top:0;left:-270px;bottom:0;width:258px;background:#fff;z-index:2001;transition:left .28s cubic-bezier(.4,0,.2,1);display:flex;flex-direction:column;box-shadow:4px 0 40px rgba(0,0,0,.14);will-change:transform;}
.drawer.open{left:0;}
.dhead{padding:1.4rem 1.2rem 1rem;border-bottom:1px solid var(--border);}
.dhead h3{font-size:1.05rem;font-weight:800;color:var(--primary);}
.dhead p{font-size:.75rem;color:var(--muted);margin-top:.15rem;}
.dmenu{flex:1;padding:.75rem 0;overflow-y:auto;}
.ditem{display:flex;align-items:center;gap:.85rem;padding:.8rem 1.2rem;cursor:pointer;transition:background .15s ease,border-left-color .15s ease;border-left:3px solid transparent;}
.ditem:active,.ditem.active{background:#f3f4f6;border-left-color:var(--accent);}
.ditem svg{width:19px;height:19px;color:var(--accent);flex-shrink:0;}
.ditem span{font-weight:600;font-size:.88rem;color:var(--text);}
.dfooter{padding:.9rem 1.2rem;border-top:1px solid var(--border);}
.content{padding-top:58px;min-height:100vh;}
.page{display:none;padding:1.1rem;opacity:0;transform:translateY(10px);transition:opacity .25s ease,transform .25s ease;}
.page.active{display:block;}
.page.visible{opacity:1;transform:translateY(0);}
.card{background:#fff;border-radius:16px;padding:1.1rem;box-shadow:var(--sh);border:1px solid var(--border);}
.card-title{font-size:.95rem;font-weight:700;color:var(--primary);margin-bottom:.9rem;}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.4rem;padding:.65rem 1.3rem;border-radius:12px;font-weight:600;font-size:.85rem;cursor:pointer;border:none;transition:transform .15s ease,box-shadow .15s ease;line-height:1;will-change:transform;}
.btn:active{transform:scale(.95);}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;box-shadow:0 4px 15px rgba(79,70,229,.3);}
.btn-green{background:var(--green);color:#fff;}
.btn-red{background:var(--red);color:#fff;}
.btn-outline{background:transparent;border:1.5px solid var(--border);color:var(--text);}
.btn-tt{background:linear-gradient(135deg,#010101,#333);color:#fff;}
.btn-zalo{background:linear-gradient(135deg,#0068ff,#0044cc);color:#fff;}
.btn-fb{background:linear-gradient(135deg,#1877f2,#0c5dc7);color:#fff;}
.btn-sm{padding:.4rem .85rem;font-size:.78rem;border-radius:9px;}
.btn-full{width:100%;}
#fn{position:fixed;bottom:72px;left:50%;transform:translateX(-50%);background:#fff;border:1px solid var(--border);border-radius:16px;padding:.9rem 1.1rem;max-width:340px;width:92%;box-shadow:0 8px 40px rgba(0,0,0,.14);z-index:500;display:none;}
#fn.show{display:block;animation:slideUp .4s cubic-bezier(.34,1.56,.64,1);}
@keyframes slideUp{from{opacity:0;transform:translateX(-50%) translateY(24px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
.fn-top{display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem;margin-bottom:.4rem;}
.fn-admin{display:flex;align-items:center;gap:.5rem;}
.fn-admin-img{width:30px;height:30px;border-radius:50%;object-fit:cover;border:2px solid var(--accent);}
.fn-title{font-weight:700;font-size:.88rem;color:var(--primary);}
.fn-close{cursor:pointer;color:var(--muted);font-size:1.2rem;line-height:1;padding:.1rem;transition:.15s;}
.fn-body{font-size:.8rem;color:var(--text);line-height:1.5;}
.fn-actions{display:flex;gap:.5rem;margin-top:.65rem;}
#st-overlay{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:9998;display:none;}
#st{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) scale(.8);background:#fff;border-radius:20px;padding:1.75rem 2.25rem;text-align:center;z-index:9999;display:none;box-shadow:0 20px 60px rgba(0,0,0,.15);min-width:190px;}
#st.show{display:flex;flex-direction:column;align-items:center;animation:stIn .3s cubic-bezier(.34,1.56,.64,1) forwards;}
@keyframes stIn{from{transform:translate(-50%,-50%) scale(.8);opacity:0}to{transform:translate(-50%,-50%) scale(1);opacity:1}}
.st-check{width:52px;height:52px;border-radius:50%;background:var(--green);display:flex;align-items:center;justify-content:center;margin-bottom:.7rem;animation:checkPop .35s .1s cubic-bezier(.34,1.56,.64,1) both;}
@keyframes checkPop{from{transform:scale(0)}to{transform:scale(1)}}
.st-check svg{width:26px;height:26px;color:#fff;}
.st-msg{font-weight:700;font-size:.92rem;color:var(--primary);}
.st-sub{font-size:.76rem;color:var(--muted);margin-top:.2rem;}
#et{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%) scale(.8);background:#fff;border-radius:20px;padding:1.75rem 2.25rem;text-align:center;z-index:9999;display:none;box-shadow:0 20px 60px rgba(0,0,0,.15);min-width:190px;}
#et.show{display:flex;flex-direction:column;align-items:center;animation:stIn .3s cubic-bezier(.34,1.56,.64,1) forwards;}
.et-x{width:52px;height:52px;border-radius:50%;background:var(--red);display:flex;align-items:center;justify-content:center;margin-bottom:.7rem;animation:checkPop .35s .1s cubic-bezier(.34,1.56,.64,1) both;}
.et-x svg{width:26px;height:26px;color:#fff;}
.et-msg{font-weight:700;font-size:.92rem;color:var(--primary);}
.et-sub{font-size:.76rem;color:var(--muted);margin-top:.2rem;}
.av-wrap{display:inline-block;position:relative;width:80px;height:80px;}
.av-img{width:80px;height:80px;border-radius:50%;object-fit:cover;border:3px solid var(--accent);display:block;}
@keyframes rainbowBg{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.rainbow-wrap{padding:3px;border-radius:14px;background:linear-gradient(270deg,#ff0000,#ff7700,#ffff00,#00ff00,#00cfff,#7c3aed,#ff00ff,#ff0000);background-size:400% 400%;animation:rainbowBg 3s ease infinite;}
.rainbow-wrap img,.rainbow-wrap video{border-radius:11px;display:block;width:100%;}
.acc-card{background:#fff;border-radius:14px;overflow:hidden;box-shadow:var(--sh);border:1px solid var(--border);transition:transform .2s ease;}
.acc-card:active{transform:scale(.99);}
.acc-body{padding:.9rem;}
.acc-badge{display:inline-block;padding:.18rem .55rem;border-radius:20px;font-size:.68rem;font-weight:700;margin-bottom:.4rem;background:linear-gradient(135deg,var(--green),#059669);color:#fff;}
.acc-title{font-weight:700;font-size:.9rem;color:var(--primary);margin-bottom:.2rem;}
.acc-desc{font-size:.73rem;color:var(--muted);margin-bottom:.45rem;line-height:1.4;}
.acc-price{font-size:1.05rem;font-weight:800;color:var(--accent);}
.acc-stock{font-size:.73rem;margin-top:.2rem;}
.acc-stock.s-ok{color:var(--green);}
.acc-stock.s-low{color:var(--orange);}
.acc-stock.s-empty{color:var(--red);font-weight:700;}
.music-disc{width:185px;height:185px;border-radius:50%;margin:0 auto 1.25rem;}
.music-disc.playing{animation:discSpin 7s linear infinite;}
@keyframes discSpin{to{transform:rotate(360deg)}}
.disc-bg{width:100%;height:100%;border-radius:50%;background:conic-gradient(from 0deg,#1a1a2e,#4f46e5,#7c3aed,#1a1a2e);display:flex;align-items:center;justify-content:center;box-shadow:0 8px 40px rgba(79,70,229,.3);}
.disc-center{width:55px;height:55px;border-radius:50%;background:#fff;border:3px solid var(--border);}
.music-seek{width:100%;-webkit-appearance:none;height:4px;border-radius:9px;background:var(--border);outline:none;cursor:pointer;}
.music-seek::-webkit-slider-thumb{-webkit-appearance:none;width:14px;height:14px;border-radius:50%;background:var(--accent);}
.mc-btn{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;border:none;background:#f3f4f6;transition:transform .15s ease;}
.mc-btn:active{transform:scale(.9);}
.mc-play{width:54px;height:54px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;box-shadow:0 4px 20px rgba(79,70,229,.3);}
.mc-btn svg{width:19px;height:19px;}
.mc-play svg{width:22px;height:22px;}
.pl-item{display:flex;align-items:center;gap:.7rem;padding:.65rem .7rem;border-radius:11px;cursor:pointer;transition:background .15s ease;margin-bottom:.2rem;}
.pl-item:active,.pl-item.active{background:#f3f4f6;}
.pl-item.active{border-left:3px solid var(--accent);padding-left:.5rem;}
.fg{margin-bottom:.85rem;}
.fl{display:block;font-size:.75rem;font-weight:700;color:var(--muted);margin-bottom:.35rem;text-transform:uppercase;letter-spacing:.04em;}
.fi{width:100%;padding:.7rem .9rem;border:1.5px solid var(--border);border-radius:11px;font-size:.88rem;background:#fff;outline:none;transition:border-color .15s ease;}
.fi:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,70,229,.1);}
.fsel{width:100%;padding:.7rem .9rem;border:1.5px solid var(--border);border-radius:11px;font-size:.88rem;background:#fff;outline:none;cursor:pointer;}
textarea.fi{min-height:75px;resize:vertical;font-family:monospace;}
.tabs{display:flex;gap:.2rem;background:#f3f4f6;padding:.28rem;border-radius:11px;margin-bottom:1.1rem;}
.tab{flex:1;padding:.5rem;border-radius:8px;text-align:center;font-size:.78rem;font-weight:600;cursor:pointer;transition:all .2s ease;color:var(--muted);}
.tab.active{background:#fff;color:var(--accent);box-shadow:0 2px 8px rgba(0,0,0,.07);}
.info-row{display:flex;justify-content:space-between;align-items:center;padding:.48rem 0;border-bottom:1px solid var(--border);}
.info-row:last-child{border-bottom:none;}
.ik{font-size:.8rem;color:var(--muted);font-weight:500;}
.iv{font-size:.82rem;font-weight:600;color:var(--text);}
.modal-ov{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:3000;display:none;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);}
.modal-ov.show{display:flex;animation:fadeIn .2s ease;}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
.modal{background:#fff;border-radius:20px;padding:1.4rem;width:100%;max-width:380px;box-shadow:0 20px 60px rgba(0,0,0,.18);animation:mIn .25s cubic-bezier(.34,1.56,.64,1);}
@keyframes mIn{from{transform:scale(.88);opacity:0}to{transform:scale(1);opacity:1}}
.modal-title{font-size:1rem;font-weight:700;margin-bottom:.9rem;color:var(--primary);}
.cap-box{background:#f3f4f6;border:1.5px solid var(--border);border-radius:11px;padding:.65rem .9rem;display:flex;align-items:center;gap:.75rem;margin-bottom:.9rem;}
.cap-q{font-size:1.05rem;font-weight:700;color:var(--primary);flex:1;}
.cap-input{width:65px;padding:.45rem;border:1.5px solid var(--border);border-radius:8px;font-size:.95rem;text-align:center;font-weight:700;outline:none;}
.notif-item{display:flex;gap:.7rem;padding:.75rem 0;border-bottom:1px solid var(--border);}
.notif-item:last-child{border:none;}
.notif-avatar{width:36px;height:36px;border-radius:50%;object-fit:cover;flex-shrink:0;}
.notif-body{flex:1;}
.notif-msg{font-size:.83rem;color:var(--text);font-weight:500;line-height:1.4;}
.notif-time{font-size:.7rem;color:var(--muted);margin-top:.2rem;}
.qr-box{background:#f8f9fb;border-radius:14px;padding:1rem;text-align:center;border:1px solid var(--border);}
.qr-box img{width:180px;height:180px;object-fit:contain;border-radius:10px;}
.content-box{background:linear-gradient(135deg,#eef2ff,#f5f3ff);border:2px dashed var(--accent);border-radius:12px;padding:.9rem;text-align:center;margin:.9rem 0;}
.content-code{font-family:monospace;font-size:1.1rem;font-weight:800;color:var(--accent);letter-spacing:.05em;}
.timer-box{display:flex;align-items:center;gap:.5rem;justify-content:center;font-size:.8rem;color:var(--orange);font-weight:600;}
.hist-table{width:100%;border-collapse:collapse;font-size:.78rem;}
.hist-table th{background:#f3f4f6;padding:.45rem .6rem;text-align:left;font-weight:600;color:var(--muted);font-size:.7rem;}
.hist-table td{padding:.5rem .6rem;border-bottom:1px solid var(--border);vertical-align:top;}
.hist-table tr:last-child td{border:none;}
.badge-ok{display:inline-block;background:#d1fae5;color:#065f46;padding:.1rem .45rem;border-radius:20px;font-size:.66rem;font-weight:700;}
.badge-pend{display:inline-block;background:#fef3c7;color:#92400e;padding:.1rem .45rem;border-radius:20px;font-size:.66rem;font-weight:700;}
.badge-rej{display:inline-block;background:#fee2e2;color:#991b1b;padding:.1rem .45rem;border-radius:20px;font-size:.66rem;font-weight:700;}
.carry-price-box{background:linear-gradient(135deg,#eef2ff,#f5f3ff);border:2px solid var(--accent);border-radius:12px;padding:1rem;text-align:center;margin:.9rem 0;}
.carry-price-total{font-size:1.4rem;font-weight:800;color:var(--accent);}
.carry-price-note{font-size:.75rem;color:var(--muted);margin-top:.2rem;}
.hero-section{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);border-radius:20px;padding:1.4rem;margin-bottom:1rem;color:#fff;position:relative;overflow:hidden;}
.quick-card{background:#fff;border-radius:14px;padding:.85rem .5rem;text-align:center;box-shadow:var(--sh);border:1px solid var(--border);cursor:pointer;transition:transform .15s ease;}
.quick-card:active{transform:scale(.94);}
.service-card{border-radius:14px;padding:1rem;border:1px solid var(--border);display:flex;align-items:center;gap:.9rem;cursor:pointer;transition:transform .15s ease;}
.service-card:active{transform:scale(.97);}
.feedback-post{margin-bottom:.9rem;padding-bottom:.9rem;border-bottom:1px solid var(--border);}
.feedback-post:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none;}
.admin-card{background:#fff;border-radius:16px;padding:1rem;border:1px solid var(--border);box-shadow:var(--sh);display:flex;align-items:center;gap:.9rem;margin-bottom:.7rem;}
.admin-card:last-child{margin-bottom:0;}
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:9px;}
</style>
"""

BASE_JS = """
<script>
function showToast(msg,sub){
  const t=document.getElementById('st'),o=document.getElementById('st-overlay');
  if(!t)return;
  t.querySelector('.st-msg').textContent=msg||'Thành công!';
  t.querySelector('.st-sub').textContent=sub||'';
  t.classList.add('show');o.style.display='block';
  setTimeout(()=>{t.classList.remove('show');o.style.display='none';},2200);
}
function showError(msg,sub){
  const t=document.getElementById('et'),o=document.getElementById('st-overlay');
  if(!t){alert(msg);return;}
  t.querySelector('.et-msg').textContent=msg||'Có lỗi xảy ra!';
  t.querySelector('.et-sub').textContent=sub||'';
  t.classList.add('show');o.style.display='block';
  setTimeout(()=>{t.classList.remove('show');o.style.display='none';},2500);
}
function copyText(txt,label){
  navigator.clipboard.writeText(txt).then(()=>showToast('Đã sao chép!',label||'')).catch(()=>{
    const ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);showToast('Đã sao chép!',label||'');
  });
}
function openDrawer(){
  document.getElementById('drawer').classList.add('open');
  document.getElementById('doverlay').classList.add('open');
}
function closeDrawer(){
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('doverlay').classList.remove('open');
}
let _curPage='home';
function showPage(id,el){
  if(_curPage===id){closeDrawer();return;}
  const prev=document.getElementById('pg-'+_curPage);
  if(prev){prev.classList.remove('visible');setTimeout(()=>{prev.classList.remove('active');prev.style.display='';},250);}
  document.querySelectorAll('.ditem').forEach(i=>i.classList.remove('active'));
  const pg=document.getElementById('pg-'+id);
  if(pg){
    pg.style.display='block';
    requestAnimationFrame(()=>{
      pg.classList.add('active');
      requestAnimationFrame(()=>pg.classList.add('visible'));
    });
  }
  if(el)el.classList.add('active');
  _curPage=id;
  closeDrawer();
  if(id==='music')initDisc();
  if(id==='profile')loadProfile();
  if(id==='notifs')loadNotifs();
  if(id==='topup')loadMyTopups();
  if(id==='carry')loadMyCarries();
  if(id==='tuchon')loadTuchon(1);
  if(id==='fffiles')loadFfFiles(1);
  if(id==='support')loadAdmins();
}
function updateBalance(){
  fetch('/api/balance').then(r=>r.json()).then(d=>{
    if(!d.ok)return;
    const b=document.getElementById('nav-bal');
    if(b)b.textContent=d.balance.toLocaleString('vi-VN')+'đ';
    if(d.new_notifs>0){const dot=document.getElementById('notif-dot');if(dot)dot.style.display='block';}
  }).catch(()=>{});
}
function loadNotifs(){
  fetch('/api/notifs').then(r=>r.json()).then(d=>{
    const dot=document.getElementById('notif-dot');if(dot)dot.style.display='none';
    const box=document.getElementById('notif-list');if(!box)return;
    if(!d.ok||!d.notifs||!d.notifs.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.85rem;">📭 Chưa có thông báo nào</div>';return;
    }
    box.innerHTML=d.notifs.map(n=>`
      <div class="notif-item">
        <img src="/anh_admin.jpg" class="notif-avatar" onerror="this.style.display='none'">
        <div class="notif-body">
          <div class="notif-msg">${n.msg}</div>
          <div class="notif-time">${n.time}</div>
        </div>
      </div>`).join('');
  }).catch(()=>{});
}
function loadMyTopups(){
  fetch('/api/my-topups').then(r=>r.json()).then(d=>{
    const box=document.getElementById('topup-hist');if(!box)return;
    if(!d.ok||!d.topups||!d.topups.length){box.innerHTML='<div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.82rem;">Chưa có lịch sử nạp tiền</div>';return;}
    box.innerHTML='<table class="hist-table"><tr><th>Thời gian</th><th>Số tiền</th><th>Mã CK</th><th>Trạng thái</th></tr>'+
      d.topups.map(r=>{
        const st=r.status==='approved'?'<span class="badge-ok">✅ Đã duyệt</span>':r.status==='rejected'?'<span class="badge-rej">❌ Từ chối</span>':'<span class="badge-pend">⏳ Chờ duyệt</span>';
        return `<tr><td style="font-size:.7rem;color:var(--muted);">${r.created}</td><td style="font-weight:700;color:var(--accent);">${(r.amount||0).toLocaleString('vi-VN')}đ</td><td style="font-family:monospace;font-size:.72rem;">${r.content}</td><td>${st}</td></tr>`;
      }).join('')+'</table>';
  }).catch(()=>{});
}
function loadMyCarries(){
  fetch('/api/my-carries').then(r=>r.json()).then(d=>{
    const box=document.getElementById('carry-hist');if(!box)return;
    if(!d.ok||!d.carries||!d.carries.length){box.innerHTML='<div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.82rem;">Chưa có lịch sử kéo thuê</div>';return;}
    box.innerHTML='<table class="hist-table"><tr><th>Thời gian</th><th>Sao</th><th>Rank</th><th>Đơn giá</th><th>Tổng tiền</th></tr>'+
      d.carries.map(o=>`<tr><td style="font-size:.7rem;color:var(--muted);">${o.time}</td><td style="font-weight:700;">⭐ ${o.stars}</td><td>${o.rank||''}</td><td style="font-size:.72rem;">${(o.price_per_star||1000).toLocaleString('vi-VN')}đ/sao</td><td style="color:var(--accent);font-weight:700;">${(o.total||0).toLocaleString('vi-VN')}đ</td></tr>`).join('')+'</table>';
  }).catch(()=>{});
}
let _fbPosts=[],_fbPage=1,_fbPerPage=3;
function loadFeedbacks(){
  fetch('/api/feedbacks').then(r=>r.json()).then(d=>{
    if(!d.ok||!d.posts||!d.posts.length)return;
    const sec=document.getElementById('feedback-section');
    if(!sec)return;
    sec.style.display='block';
    _fbPosts=d.posts;
    _fbPage=1;
    renderFeedbacks();
  }).catch(()=>{});
}
function renderFeedbacks(){
  const list=document.getElementById('feedback-list');
  if(!list)return;
  const total=_fbPosts.length;
  const totalPages=Math.ceil(total/_fbPerPage);
  const start=(_fbPage-1)*_fbPerPage;
  const page=_fbPosts.slice(start,start+_fbPerPage);
  let html=page.map(p=>`
    <div class="feedback-post">
      ${p.media_url?(p.media_type==='video'?
        `<video src="${p.media_url}" style="width:100%;border-radius:10px;margin-bottom:.5rem;" controls playsinline preload="metadata"></video>`:
        `<div class="rainbow-wrap" style="margin-bottom:.5rem;"><img src="${p.media_url}" alt="Feedback" style="width:100%;border-radius:11px;display:block;" loading="lazy" onerror="this.parentNode.style.display='none'"></div>`
      ):''}
      ${p.desc?`<div style="font-size:.83rem;color:var(--text);line-height:1.55;font-weight:500;">${p.desc}</div>`:''}
      <div style="font-size:.7rem;color:var(--muted);margin-top:.3rem;">${p.customer?'👤 '+p.customer+' • ':''}⏰ ${p.time}</div>
    </div>`).join('');
  if(totalPages>1){
    let pg='<div style="display:flex;gap:.4rem;margin-top:.8rem;justify-content:center;flex-wrap:wrap;">';
    for(let i=1;i<=totalPages;i++){
      pg+=`<button onclick="fbGoPage(${i})" style="padding:.3rem .75rem;border-radius:8px;font-size:.75rem;font-weight:600;border:1.5px solid ${i===_fbPage?'var(--accent)':'var(--border)'};background:${i===_fbPage?'var(--accent)':'#fff'};color:${i===_fbPage?'#fff':'var(--text)'};cursor:pointer;">${i}</button>`;
    }
    pg+='</div>';
    html+=pg;
  }
  list.innerHTML=html;
}
function fbGoPage(p){_fbPage=p;renderFeedbacks();}
function loadTuchon(page){
  const box=document.getElementById('tuchon-list');
  if(!box)return;
  box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.85rem;">Đang tải...</div>';
  fetch('/api/custom-accs?page='+(page||1)).then(r=>r.json()).then(d=>{
    if(!d.ok){box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.85rem;">Không tải được danh sách</div>';return;}
    if(!d.accs||!d.accs.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2.5rem 1rem;"><div style="font-size:2rem;margin-bottom:.5rem;">📭</div><div style="font-weight:600;margin-bottom:.3rem;">Chưa có acc nào</div><div style="font-size:.82rem;">Admin sẽ cập nhật sớm!</div></div>';
      return;
    }
    let html=d.accs.map(a=>`
      <div style="background:#fff;border-radius:16px;border:1px solid var(--border);box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden;margin-bottom:.9rem;">
        ${a.image_url?`<div class="rainbow-wrap" style="margin:0;border-radius:0;"><img src="${a.image_url}" alt="Acc" style="width:100%;max-height:200px;object-fit:cover;display:block;" loading="lazy" onerror="this.parentNode.style.display='none'"></div>`:''}
        <div style="padding:.9rem;">
          ${a.platform?`<div style="font-size:.7rem;font-weight:700;color:var(--accent);text-transform:uppercase;margin-bottom:.3rem;">📱 ${a.platform}</div>`:''}
          ${a.desc?`<div style="font-size:.83rem;color:var(--text);line-height:1.55;margin-bottom:.5rem;">${a.desc}</div>`:''}
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;">
            <div style="font-size:1.1rem;font-weight:800;color:var(--accent);">${a.price>0?a.price.toLocaleString('vi-VN')+'đ':'Liên hệ'}</div>
            <a href="https://zalo.me/""" + ZALO_PHONE + """" target="_blank"><button class="btn btn-zalo btn-sm">🔵 Liên Hệ Zalo</button></a>
          </div>
          <div style="font-size:.68rem;color:var(--muted);margin-top:.4rem;">⏰ ${a.added}</div>
        </div>
      </div>`).join('');
    if(d.total_pages>1){
      html+='<div style="display:flex;gap:.4rem;justify-content:center;flex-wrap:wrap;margin-top:.5rem;">';
      for(let i=1;i<=d.total_pages;i++){
        html+=`<button onclick="loadTuchon(${i})" style="padding:.35rem .8rem;border-radius:8px;font-size:.76rem;font-weight:600;border:1.5px solid ${i===d.page?'var(--accent)':'var(--border)'};background:${i===d.page?'var(--accent)':'#fff'};color:${i===d.page?'#fff':'var(--text)'};cursor:pointer;">${i}</button>`;
      }
      html+='</div>';
    }
    box.innerHTML=html;
  }).catch(()=>{box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.85rem;">Lỗi kết nối!</div>';});
}
let _purchasedFfIds=new Set();
function loadFfFiles(page){
  const box=document.getElementById('ff-list');
  if(!box)return;
  box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.85rem;">Đang tải...</div>';
  fetch('/api/ff-files?page='+(page||1)).then(r=>r.json()).then(d=>{
    if(!d.ok){box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;">Lỗi tải dữ liệu</div>';return;}
    if(!d.files||!d.files.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2.5rem 1rem;"><div style="font-size:2rem;margin-bottom:.5rem;">📂</div><div style="font-weight:600;margin-bottom:.3rem;">Chưa có file nào</div><div style="font-size:.82rem;">Admin sẽ cập nhật sớm!</div></div>';
      return;
    }
    let html=d.files.map(f=>{
      const bought=_purchasedFfIds.has(f.id);
      return `<div style="background:#fff;border-radius:16px;border:1px solid var(--border);box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden;margin-bottom:.9rem;" id="ffcard-${f.id}">
        ${f.image_url?`<div class="rainbow-wrap" style="margin:0;border-radius:0;"><img src="${f.image_url}" alt="${f.name}" style="width:100%;max-height:200px;object-fit:cover;display:block;" loading="lazy" onerror="this.parentNode.style.display='none'"></div>`:''}
        <div style="padding:.9rem;">
          <div style="font-weight:700;font-size:.95rem;color:var(--primary);margin-bottom:.3rem;">📁 ${f.name}</div>
          ${f.desc?`<div style="font-size:.83rem;color:var(--text);line-height:1.55;margin-bottom:.5rem;">${f.desc}</div>`:''}
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;">
            <div style="font-size:1.1rem;font-weight:800;color:var(--accent);">${f.price>0?f.price.toLocaleString('vi-VN')+'đ':'🎁 Miễn phí'}</div>
            ${bought?`<button class="btn btn-green btn-sm" onclick="showFfDownload('${f.id}','${f.name}')">📥 Tải File</button>`:
              `<button class="btn btn-primary btn-sm" onclick="openFfBuy('${f.id}','${f.name}',${f.price})">🛒 ${f.price>0?'Mua & Tải':'Tải Miễn Phí'}</button>`}
          </div>
          <div style="font-size:.68rem;color:var(--muted);margin-top:.4rem;">⏰ ${f.added}</div>
          <div id="ff-result-${f.id}" style="display:none;margin-top:.7rem;"></div>
        </div>
      </div>`;
    }).join('');
    if(d.total_pages>1){
      html+='<div style="display:flex;gap:.4rem;justify-content:center;flex-wrap:wrap;margin-top:.5rem;">';
      for(let i=1;i<=d.total_pages;i++){
        html+=`<button onclick="loadFfFiles(${i})" style="padding:.35rem .8rem;border-radius:8px;font-size:.76rem;font-weight:600;border:1.5px solid ${i===d.page?'var(--accent)':'var(--border)'};background:${i===d.page?'var(--accent)':'#fff'};color:${i===d.page?'#fff':'var(--text)'};cursor:pointer;">${i}</button>`;
      }
      html+='</div>';
    }
    box.innerHTML=html;
  }).catch(()=>{box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;">Lỗi kết nối!</div>';});
}
let _ffBuyModal={id:'',name:'',price:0,discountPct:0,couponCode:''};
function openFfBuy(id,name,price){
  _ffBuyModal={id,name,price,discountPct:0,couponCode:''};
  const m=document.getElementById('ff-buy-modal');if(!m)return;
  document.getElementById('ff-buy-name').textContent=name;
  document.getElementById('ff-buy-price-display').textContent=price>0?price.toLocaleString('vi-VN')+'đ':'Miễn phí';
  document.getElementById('ff-buy-total').textContent=price>0?price.toLocaleString('vi-VN')+'đ':'0đ';
  const couponRow=document.getElementById('ff-coupon-row');
  if(couponRow)couponRow.style.display=price>0?'block':'none';
  const ci=document.getElementById('ff-buy-coupon');if(ci)ci.value='';
  const cm=document.getElementById('ff-coupon-msg');if(cm){cm.style.display='none';cm.textContent='';}
  const dr=document.getElementById('ff-coupon-discount-row');if(dr)dr.style.display='none';
  m.classList.add('show');
}
function closeFfBuyModal(){document.getElementById('ff-buy-modal')?.classList.remove('show');_ffBuyModal={id:'',name:'',price:0,discountPct:0,couponCode:''};}
function updFfTotal(){
  const base=_ffBuyModal.price;
  let total=base;
  if(_ffBuyModal.discountPct>0){
    total=Math.max(0,base-Math.floor(base*_ffBuyModal.discountPct/100));
    const dr=document.getElementById('ff-coupon-discount-row');
    if(dr){dr.style.display='block';dr.textContent=`🎟️ Mã "${_ffBuyModal.couponCode}" giảm ${_ffBuyModal.discountPct}% → Tiết kiệm ${(base-total).toLocaleString('vi-VN')}đ`;}
  }
  const tt=document.getElementById('ff-buy-total');
  if(tt)tt.textContent=total>0?total.toLocaleString('vi-VN')+'đ':'0đ (Miễn phí)';
}
function applyFfCoupon(){
  const code=document.getElementById('ff-buy-coupon')?.value.trim().toUpperCase();
  const cm=document.getElementById('ff-coupon-msg');
  const dr=document.getElementById('ff-coupon-discount-row');
  if(!code){if(cm){cm.style.display='block';cm.style.cssText='display:block;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;background:#fee2e2;color:#991b1b;';cm.textContent='Nhập mã giảm giá!';}return;}
  const fd=new FormData();fd.append('code',code);fd.append('cat','ff_file');fd.append('qty',1);
  fetch('/api/check-coupon',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(cm){
      cm.style.display='block';
      if(d.ok){
        cm.style.cssText='display:block;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;background:#d1fae5;color:#065f46;';
        cm.textContent='✅ Mã hợp lệ! Giảm '+d.pct+'%';
        _ffBuyModal.discountPct=d.pct;_ffBuyModal.couponCode=code;
      } else {
        cm.style.cssText='display:block;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;background:#fee2e2;color:#991b1b;';
        cm.textContent=d.msg;
        _ffBuyModal.discountPct=0;_ffBuyModal.couponCode='';
        if(dr)dr.style.display='none';
      }
    }
    updFfTotal();
  }).catch(()=>{if(cm){cm.style.display='block';cm.textContent='Lỗi kết nối!';}});
}
function doFfBuy(){
  const btn=document.getElementById('ff-buy-submit');
  if(btn){btn.textContent='⏳ Đang xử lý...';btn.disabled=true;}
  const fd=new FormData();
  fd.append('ff_id',_ffBuyModal.id);
  if(_ffBuyModal.couponCode)fd.append('coupon_code',_ffBuyModal.couponCode);
  fetch('/api/buy-ff-file',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='✅ Xác Nhận';btn.disabled=false;}
    if(d.ok){
      closeFfBuyModal();
      updateBalance();
      _purchasedFfIds.add(_ffBuyModal.id||d.ff_id);
      showFfDownloadResult(d);
    } else {
      if(d.need_topup)showError('Số dư không đủ!','Vui lòng nạp thêm tiền');
      else showError(d.msg||'Có lỗi xảy ra!','');
    }
  }).catch(()=>{if(btn){btn.textContent='✅ Xác Nhận';btn.disabled=false;}showError('Lỗi kết nối!','');});
}
function showFfDownloadResult(d){
  const m=document.getElementById('ff-result-modal');if(!m)return;
  document.getElementById('ff-result-name').textContent=d.name||'File FF';
  document.getElementById('ff-result-coupon').textContent=d.coupon_applied?`✅ Đã áp dụng mã giảm ${d.discount_pct}%`:'';
  const dlBtn=document.getElementById('ff-download-btn');
  if(dlBtn){
    if(d.file_url){dlBtn.href=d.file_url;dlBtn.style.display='inline-flex';}
    else{dlBtn.style.display='none';}
  }
  const vidBox=document.getElementById('ff-result-video');
  if(vidBox){
    if(d.video_url){vidBox.innerHTML=`<div style="font-size:.8rem;font-weight:700;color:var(--muted);margin-bottom:.4rem;">🎬 Video hướng dẫn cài đặt:</div><video src="${d.video_url}" style="width:100%;border-radius:10px;" controls playsinline preload="metadata"></video>`;vidBox.style.display='block';}
    else{vidBox.style.display='none';}
  }
  m.classList.add('show');
}
function showFfDownload(id,name){
  const fd=new FormData();fd.append('ff_id',id);
  fetch('/api/buy-ff-file',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok)showFfDownloadResult({...d,name:name});
    else showError(d.msg||'Lỗi!','');
  }).catch(()=>showError('Lỗi kết nối!',''));
}
function closeFfResultModal(){document.getElementById('ff-result-modal')?.classList.remove('show');}
function loadAdmins(){
  fetch('/api/admins').then(r=>r.json()).then(d=>{
    if(!d.ok)return;
    const box=document.getElementById('admin-list');
    if(!box)return;
    box.innerHTML=d.admins.map((a,i)=>`
      <div class="admin-card">
        <div style="position:relative;flex-shrink:0;">
          <img src="${a.avatar}" style="width:55px;height:55px;border-radius:50%;object-fit:cover;border:2px solid ${i===0?'#4f46e5':'#10b981'};" onerror="this.style.display='none'" alt="${a.name}">
          ${i===0?'<div style="position:absolute;bottom:-2px;right:-2px;background:#4f46e5;color:#fff;font-size:.5rem;font-weight:800;padding:.1rem .3rem;border-radius:8px;">MAIN</div>':'<div style="position:absolute;bottom:-2px;right:-2px;background:#10b981;color:#fff;font-size:.5rem;font-weight:800;padding:.1rem .3rem;border-radius:8px;">SUB</div>'}
        </div>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;font-size:.92rem;color:var(--primary);">${a.name}</div>
          <div style="font-size:.72rem;color:${i===0?'var(--accent)':'var(--green)'};font-weight:600;margin-bottom:.4rem;">${a.role}</div>
          <div style="display:flex;gap:.35rem;flex-wrap:wrap;">
            ${a.tiktok?`<a href="${a.tiktok}" target="_blank"><button class="btn btn-tt btn-sm" style="padding:.3rem .6rem;font-size:.7rem;">🎵 TikTok</button></a>`:''}
            ${a.zalo?`<a href="https://zalo.me/${a.zalo}" target="_blank"><button class="btn btn-zalo btn-sm" style="padding:.3rem .6rem;font-size:.7rem;">🔵 Zalo</button></a>`:''}
            ${a.facebook?`<a href="${a.facebook}" target="_blank"><button class="btn btn-fb btn-sm" style="padding:.3rem .6rem;font-size:.7rem;">📘 Facebook</button></a>`:''}
          </div>
        </div>
      </div>`).join('');
  }).catch(()=>{});
}
function calcThuAcc(){
  const r=document.getElementById('thu-rank')?.value||'';
  const s=parseInt(document.getElementById('thu-stars')?.value||0);
  const box=document.getElementById('thu-result');
  if(!box)return;
  if(!r||!s||s<1){box.style.display='none';return;}
  const highR=['Cao Thủ','Thách Đấu'];
  const pps=highR.includes(r)?1500:1000;
  let total=s*pps;
  total=Math.ceil(total/1000)*1000;
  if(s>=10){total=total-Math.floor(total*0.10);total=Math.ceil(total/1000)*1000;}
  box.innerHTML=`<div style="font-size:.85rem;color:var(--muted);margin-bottom:.3rem;">${s} sao × ${pps.toLocaleString('vi-VN')}đ${s>=10?' (giảm 10%)':''}</div><div style="font-size:1.5rem;font-weight:800;color:var(--accent);">${total.toLocaleString('vi-VN')}đ</div>`;
  box.style.display='block';
}
function updCarryTotal(){
  const rank=document.getElementById('carry-rank')?.value||'';
  const stars=parseInt(document.getElementById('carry-stars')?.value||0);
  const disp=document.getElementById('carry-total-display');
  const note=document.getElementById('carry-price-per-star');
  if(!disp)return;
  if(!rank||!stars||stars<1){disp.textContent='0đ';if(note)note.textContent='Chọn rank và nhập số sao';return;}
  const highR=['Cao Thủ','Thách Đấu'];
  const pps=highR.includes(rank)?1500:1000;
  let total=stars*pps;
  total=Math.ceil(total/1000)*1000;
  if(stars>=10){total=total-Math.floor(total*0.10);total=Math.ceil(total/1000)*1000;}
  disp.textContent=total.toLocaleString('vi-VN')+'đ';
  if(note)note.textContent=`${stars} sao × ${pps.toLocaleString('vi-VN')}đ/sao${stars>=10?' (giảm 10%)':''}`;
}
let stockMap={};
function renderStock(){
  ['kim_cuong','bach_kim','lv5'].forEach(c=>{
    const el=document.getElementById('stk-'+c);
    if(!el)return;
    const n=stockMap[c]||0;
    el.className='acc-stock '+(n>5?'s-ok':n>0?'s-low':'s-empty');
    el.textContent=n>0?'✅ Còn '+n+' acc':'❌ Hết hàng';
  });
}
function shopTab(cat,el){
  ['kim_cuong','bach_kim','lv5'].forEach(c=>{
    const d=document.getElementById('sh-'+c);
    if(d)d.style.display=c===cat?'':'none';
    const t=document.getElementById('tab-'+c);
    if(t)t.classList.toggle('active',c===cat);
  });
}
let _buyModal={cat:'',max:0,discountPct:0,couponCode:''};
function openBuy(cat){
  const names={'kim_cuong':'Kim Cương (25.000đ)','bach_kim':'Bạch Kim (20.000đ)','lv5':'Lv5 Google (2.500đ)'};
  const prices={'kim_cuong':25000,'bach_kim':20000,'lv5':2500};
  _buyModal.cat=cat;_buyModal.max=stockMap[cat]||0;_buyModal.discountPct=0;_buyModal.couponCode='';
  const m=document.getElementById('buy-modal');
  if(!m)return;
  m.querySelector('#buy-cat-name').textContent=names[cat]||cat;
  const qi=m.querySelector('#buy-qty');
  if(qi){qi.value=1;qi.max=Math.min(10,_buyModal.max);}
  const pp=m.querySelector('#buy-price-preview');
  if(pp)pp.textContent=prices[cat].toLocaleString('vi-VN')+'đ';
  const ci=document.getElementById('buy-coupon');if(ci)ci.value='';
  const cm=document.getElementById('coupon-msg');if(cm){cm.style.display='none';cm.textContent='';}
  const dr=document.getElementById('coupon-discount-row');if(dr)dr.style.display='none';
  m.classList.add('show');
  updBuyTotal();
}
function updBuyTotal(){
  const prices={'kim_cuong':25000,'bach_kim':20000,'lv5':2500};
  const qty=parseInt(document.getElementById('buy-qty')?.value||1);
  const base=(prices[_buyModal.cat]||0)*qty;
  let total=base;
  if(_buyModal.discountPct>0){
    total=Math.max(0,base-Math.floor(base*_buyModal.discountPct/100));
    const dr=document.getElementById('coupon-discount-row');
    if(dr){dr.style.display='block';dr.textContent=`🎟️ Mã "${_buyModal.couponCode}" giảm ${_buyModal.discountPct}% → Tiết kiệm ${(base-total).toLocaleString('vi-VN')}đ`;}
  }
  const pp=document.getElementById('buy-total-preview');
  if(pp)pp.textContent=total.toLocaleString('vi-VN')+'đ';
}
function applyCoupon(){
  const code=document.getElementById('buy-coupon')?.value.trim().toUpperCase();
  const cat=_buyModal.cat;
  const qty=parseInt(document.getElementById('buy-qty')?.value||1);
  const cm=document.getElementById('coupon-msg');
  const dr=document.getElementById('coupon-discount-row');
  if(!code){if(cm){cm.style.display='block';cm.style.cssText='display:block;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;background:#fee2e2;color:#991b1b;';cm.textContent='Nhập mã giảm giá!';}return;}
  const fd=new FormData();fd.append('code',code);fd.append('cat',cat);fd.append('qty',qty);
  fetch('/api/check-coupon',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(cm){
      cm.style.display='block';
      if(d.ok){
        cm.style.cssText='display:block;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;background:#d1fae5;color:#065f46;';
        cm.textContent=d.msg;
        _buyModal.discountPct=d.pct;_buyModal.couponCode=code;
      } else {
        cm.style.cssText='display:block;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;background:#fee2e2;color:#991b1b;';
        cm.textContent=d.msg;
        _buyModal.discountPct=0;_buyModal.couponCode='';
        if(dr)dr.style.display='none';
      }
    }
    updBuyTotal();
  }).catch(()=>{if(cm){cm.style.display='block';cm.textContent='Lỗi kết nối!';}});
}
function closeBuyModal(){
  document.getElementById('buy-modal')?.classList.remove('show');
  _buyModal.discountPct=0;_buyModal.couponCode='';
}
function doBuy(){
  const cat=_buyModal.cat;
  const qty=parseInt(document.getElementById('buy-qty')?.value||1);
  const coupon_code=_buyModal.couponCode||'';
  const btn=document.getElementById('buy-submit-btn');
  if(btn){btn.textContent='⏳ Đang xử lý...';btn.disabled=true;}
  const fd=new FormData();
  fd.append('cat',cat);fd.append('qty',qty);
  if(coupon_code)fd.append('coupon_code',coupon_code);
  fetch('/api/buy',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='✅ Xác Nhận Mua';btn.disabled=false;}
    if(d.ok){
      closeBuyModal();
      updateBalance();
      let html=`<div style="font-weight:700;font-size:.9rem;color:var(--primary);margin-bottom:.7rem;">✅ Mua thành công! ${d.accs.length} acc${d.coupon_applied?' (đã giảm '+d.discount_pct+'%)':''}</div>`;
      d.accs.forEach((a,i)=>{html+=`<div style="background:#f3f4f6;border-radius:9px;padding:.6rem .8rem;margin-bottom:.4rem;font-size:.82rem;font-family:monospace;"><b>${i+1}.</b> ${a.user} : ${a.pass}${a.platform?' ('+a.platform+')':''}</div>`;});
      html+=`<div style="font-size:.78rem;color:var(--muted);margin-top:.5rem;">💾 Lưu thông tin ngay để không mất acc!</div>`;
      const rb=document.getElementById('result-body');if(rb)rb.innerHTML=html;
      document.getElementById('result-modal')?.classList.add('show');
      fetch('/api/acc-count').then(r=>r.json()).then(dd=>{stockMap=dd;renderStock();}).catch(()=>{});
    } else {
      if(d.need_topup){
        showError('Số dư không đủ!','Vui lòng nạp thêm tiền');
      } else {
        if(d.coupon_msg)showError(d.coupon_msg,'Mã giảm giá không hợp lệ');
        else showError(d.msg||'Có lỗi xảy ra!','');
      }
    }
  }).catch(()=>{if(btn){btn.textContent='✅ Xác Nhận Mua';btn.disabled=false;}showError('Lỗi kết nối!','');});
}
function closeResultModal(){document.getElementById('result-modal')?.classList.remove('show');}
function loadProfile(){
  fetch('/profile-data').then(r=>r.json()).then(d=>{
    if(!d.ok)return;
    const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};
    set('pd-display',d.display||d.username);
    set('pd-user','@'+d.username);
    set('pd-bal',(d.balance||0).toLocaleString('vi-VN')+'đ');
    set('pd-id',d.random_id||'---');
    set('pd-created',d.created||'---');
    set('pd-ip',d.last_ip||'---');
  }).catch(()=>{});
  loadHistoryTab('acc');
}
function loadHistoryTab(tab){
  ['acc','carry','topup','ff'].forEach(t=>{
    const btn=document.getElementById('htab-'+t);
    if(btn)btn.classList.toggle('active',t===tab);
    const pane=document.getElementById('hpane-'+t);
    if(pane)pane.style.display=t===tab?'block':'none';
  });
  if(tab==='acc')loadAccHistory();
  else if(tab==='carry')loadCarryHistory();
  else if(tab==='topup')loadTopupHistory();
  else if(tab==='ff')loadFfHistory();
}
function loadAccHistory(){
  const box=document.getElementById('acc-history-list');
  if(!box)return;
  box.innerHTML='<div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.83rem;">Đang tải...</div>';
  fetch('/api/my-orders').then(r=>r.json()).then(d=>{
    if(!d.ok||!d.orders||!d.orders.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.83rem;">📭 Chưa có đơn hàng nào</div>';
      return;
    }
    box.innerHTML=d.orders.map(o=>`<div style="background:#f8faff;border-radius:11px;border:1px solid var(--border);padding:.75rem .9rem;margin-bottom:.55rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem;">
        <div style="font-weight:700;font-size:.85rem;color:var(--primary);">${o.cat||o.category||'Acc'}</div>
        <div style="font-size:.78rem;font-weight:700;color:var(--accent);">${(o.total||0).toLocaleString('vi-VN')}đ</div>
      </div>
      ${o.accs?o.accs.map(a=>`<div style="font-family:monospace;font-size:.78rem;color:var(--text);background:#fff;border-radius:7px;padding:.3rem .5rem;margin-bottom:.2rem;">${a.user}:${a.pass}</div>`).join(''):''}
      <div style="font-size:.68rem;color:var(--muted);margin-top:.3rem;">⏰ ${o.time}${o.coupon?' | 🎟️ '+o.coupon:''}</div>
    </div>`).join('');
  }).catch(()=>{box.innerHTML='<div style="text-align:center;color:var(--red);padding:1.5rem;font-size:.83rem;">Lỗi kết nối!</div>';});
}
function loadCarryHistory(){
  const box=document.getElementById('carry-history-list');
  if(!box)return;
  box.innerHTML='<div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.83rem;">Đang tải...</div>';
  fetch('/api/my-carries').then(r=>r.json()).then(d=>{
    if(!d.ok||!d.carries||!d.carries.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.83rem;">📭 Chưa có đơn kéo thuê nào</div>';
      return;
    }
    box.innerHTML=d.carries.map(o=>`<div style="background:#f8faff;border-radius:11px;border:1px solid var(--border);padding:.75rem .9rem;margin-bottom:.55rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem;">
        <div style="font-weight:700;font-size:.85rem;color:var(--primary);">⭐ ${o.stars} sao — ${o.rank}</div>
        <div style="font-size:.78rem;font-weight:700;color:var(--accent);">${(o.total||0).toLocaleString('vi-VN')}đ</div>
      </div>
      <div style="font-size:.78rem;color:var(--text);">Trạng thái: <span style="font-weight:700;color:${o.status==='done'?'var(--green)':o.status==='cancel'?'var(--red)':'var(--accent)'}">${o.status==='done'?'✅ Hoàn thành':o.status==='cancel'?'❌ Đã hủy':'⏳ Đang kéo'}</span></div>
      ${o.note?`<div style="font-size:.75rem;color:var(--muted);">Ghi chú: ${o.note}</div>`:''}
      <div style="font-size:.68rem;color:var(--muted);margin-top:.3rem;">⏰ ${o.time}</div>
    </div>`).join('');
  }).catch(()=>{box.innerHTML='<div style="text-align:center;color:var(--red);padding:1.5rem;font-size:.83rem;">Lỗi kết nối!</div>';});
}
function loadTopupHistory(){
  const box=document.getElementById('topup-history-list');
  if(!box)return;
  box.innerHTML='<div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.83rem;">Đang tải...</div>';
  fetch('/api/my-topups').then(r=>r.json()).then(d=>{
    if(!d.ok||!d.requests||!d.requests.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.83rem;">📭 Chưa có lần nạp tiền nào</div>';
      return;
    }
    box.innerHTML=d.requests.map(o=>`<div style="background:#f8faff;border-radius:11px;border:1px solid var(--border);padding:.75rem .9rem;margin-bottom:.55rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem;">
        <div style="font-weight:700;font-size:.85rem;color:var(--primary);">💳 Nạp tiền</div>
        <div style="font-size:.78rem;font-weight:700;color:var(--accent);">${(o.amount||0).toLocaleString('vi-VN')}đ</div>
      </div>
      <div style="font-size:.78rem;color:var(--text);">Trạng thái: <span style="font-weight:700;color:${o.status==='approved'?'var(--green)':o.status==='rejected'?'var(--red)':'var(--accent)'}">${o.status==='approved'?'✅ Đã duyệt':o.status==='rejected'?'❌ Từ chối':'⏳ Chờ duyệt'}</span></div>
      <div style="font-size:.68rem;color:var(--muted);margin-top:.3rem;">⏰ ${o.time}</div>
    </div>`).join('');
  }).catch(()=>{box.innerHTML='<div style="text-align:center;color:var(--red);padding:1.5rem;font-size:.83rem;">Lỗi kết nối!</div>';});
}
function loadFfHistory(){
  const box=document.getElementById('ff-history-list');
  if(!box)return;
  box.innerHTML='<div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.83rem;">Đang tải...</div>';
  fetch('/api/my-ff-orders').then(r=>r.json()).then(d=>{
    if(!d.ok||!d.orders||!d.orders.length){
      box.innerHTML='<div style="text-align:center;color:var(--muted);padding:2rem;font-size:.83rem;">📭 Chưa mua file FF nào</div>';
      return;
    }
    box.innerHTML=d.orders.map(o=>`<div style="background:#f8faff;border-radius:11px;border:1px solid var(--border);padding:.75rem .9rem;margin-bottom:.55rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.3rem;">
        <div style="font-weight:700;font-size:.85rem;color:var(--primary);">📁 ${o.name}</div>
        <div style="font-size:.78rem;font-weight:700;color:var(--accent);">${(o.total||0).toLocaleString('vi-VN')}đ</div>
      </div>
      ${o.coupon?`<div style="font-size:.75rem;color:var(--green);">🎟️ Mã giảm giá: ${o.coupon} (-${o.discount_pct}%)</div>`:''}
      <div style="font-size:.68rem;color:var(--muted);margin-top:.3rem;">⏰ ${o.time}</div>
    </div>`).join('');
  }).catch(()=>{box.innerHTML='<div style="text-align:center;color:var(--red);padding:1.5rem;font-size:.83rem;">Lỗi kết nối!</div>';});
}
function setTopupAmt(n){const e=document.getElementById('topup-amount');if(e)e.value=n;}
let _topupData=null;
function requestTopup(){
  const amount=parseInt(document.getElementById('topup-amount')?.value||0);
  if(!amount||amount<1000){showError('Số tiền tối thiểu 1.000đ','');return;}
  const fd=new FormData();fd.append('amount',amount);
  fetch('/api/topup-request',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(!d.ok){showError(d.msg||'Lỗi!','');return;}
    _topupData=d;
    const m=document.getElementById('topup-modal');
    if(!m)return;
    const bd=document.getElementById('topup-bank-detail');
    if(bd){
      bd.innerHTML=`
        <div style="margin-bottom:.6rem;"><div style="font-size:.72rem;font-weight:700;color:var(--muted);margin-bottom:.15rem;">NỀN TẢNG</div><div style="font-weight:700;font-size:.9rem;color:var(--accent);">${d.bank_name||'ZaloPay'}</div></div>
        ${d.bank_account?`<div style="margin-bottom:.6rem;"><div style="font-size:.72rem;font-weight:700;color:var(--muted);margin-bottom:.15rem;">SỐ TÀI KHOẢN</div><div style="font-family:monospace;font-weight:700;font-size:.95rem;cursor:pointer;color:var(--primary);" onclick="copyText('${d.bank_account}','Số tài khoản')">${d.bank_account} 📋</div></div>`:''}
        <div style="margin-bottom:.6rem;"><div style="font-size:.72rem;font-weight:700;color:var(--muted);margin-bottom:.15rem;">CHỦ TÀI KHOẢN</div><div style="font-weight:700;">${d.bank_holder||'Phạm Tuấn Minh'}</div></div>
      `;
    }
    const cc=document.getElementById('topup-content-code');
    if(cc){cc.textContent=d.content;cc.onclick=()=>copyText(d.content,'Mã nội dung');}
    m.classList.add('show');
    startTopupTimer(d.expires);
    setTimeout(()=>loadMyTopups(),500);
  }).catch(()=>showError('Lỗi kết nối!',''));
}
let _timerInt=null;
function startTopupTimer(exp){
  const el=document.getElementById('topup-timer');
  if(!el)return;
  if(_timerInt)clearInterval(_timerInt);
  function upd(){
    const left=Math.max(0,exp-Math.floor(Date.now()/1000));
    const m=Math.floor(left/60),s=left%60;
    el.textContent=`${m}:${s.toString().padStart(2,'0')}`;
    if(left===0)clearInterval(_timerInt);
  }
  upd();
  _timerInt=setInterval(upd,1000);
}
function closeTopupModal(){document.getElementById('topup-modal')?.classList.remove('show');}
function orderCarry(){
  const rank=document.getElementById('carry-rank')?.value;
  const stars=parseInt(document.getElementById('carry-stars')?.value||0);
  const note=document.getElementById('carry-note')?.value||'';
  if(!rank){showError('Vui lòng chọn rank!','');return;}
  if(stars<5){showError('Tối thiểu 5 sao!','');return;}
  const btn=document.getElementById('carry-submit-btn');
  if(btn){btn.textContent='⏳ Đang xử lý...';btn.disabled=true;}
  const fd=new FormData();fd.append('rank',rank);fd.append('stars',stars);fd.append('note',note);
  fetch('/api/carry-order',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='⭐ Đặt Kéo Thuê Ngay';btn.disabled=false;}
    if(d.ok){
      updateBalance();
      showToast('Đặt kéo thuê thành công!',`${stars} sao - ${d.total.toLocaleString('vi-VN')}đ`);
      const cm=document.getElementById('carry-contact-modal');
      if(cm){
        const cb=document.getElementById('carry-contact-body');
        if(cb){
          cb.innerHTML=`
            <div style="text-align:center;margin-bottom:1rem;">
              <div style="font-size:1.4rem;margin-bottom:.3rem;">🏆</div>
              <div style="font-weight:700;color:var(--primary);">Đặt thành công! ${stars} sao</div>
              <div style="font-size:.82rem;color:var(--muted);">Tổng: ${d.total.toLocaleString('vi-VN')}đ đã được trừ</div>
            </div>
            <div style="background:#eef2ff;border-radius:12px;padding:.9rem;margin-bottom:.8rem;">
              <div style="font-weight:700;font-size:.85rem;color:var(--primary);margin-bottom:.5rem;">📞 Liên hệ ngay để kéo:</div>
              <div style="font-size:.82rem;color:var(--text);line-height:1.8;">
                <div>👑 <b>Admin chính:</b> TMinh</div>
                <div style="font-size:.78rem;color:var(--muted);">Liên hệ TikTok hoặc Zalo bên dưới</div>
                ${d.sub_contact?`<div style="margin-top:.4rem;">🛡️ <b>Admin phụ:</b> ${d.sub_contact}<br><div style="font-size:.78rem;color:var(--muted);">Liên hệ nếu admin chính không rep</div></div>`:''}
              </div>
            </div>
            <div style="display:flex;flex-direction:column;gap:.45rem;">
              <a href="${d.tiktok_url}" target="_blank"><button class="btn btn-tt btn-full">🎵 TikTok Admin TMinh</button></a>
              <a href="https://zalo.me/${d.zalo_phone}" target="_blank"><button class="btn btn-zalo btn-full">🔵 Zalo: ${d.zalo_phone}</button></a>
            </div>`;
        }
        cm.classList.add('show');
      }
      loadMyCarries();
    } else {
      if(d.need_topup){showError('Số dư không đủ!','Vui lòng nạp thêm tiền');}
      else showError(d.msg||'Có lỗi!','');
    }
  }).catch(()=>{if(btn){btn.textContent='⭐ Đặt Kéo Thuê Ngay';btn.disabled=false;}showError('Lỗi kết nối!','');});
}
function closeCarryModal(){document.getElementById('carry-contact-modal')?.classList.remove('show');}
let _audio=null,_tracks=[{src:'/music1.mp3',title:'Nhạc FF 1'},{src:'/music2.mp3',title:'Nhạc FF 2'},{src:'/music3.mp3',title:'Nhạc FF 3'}],_curTr=0,_discInit=false;
function initDisc(){
  if(_discInit)return;_discInit=true;
  if(window.NO_MUSIC)return;
  _audio=new Audio();
  _audio.addEventListener('timeupdate',()=>{
    const sk=document.getElementById('music-seek');const ct=document.getElementById('cur-t');
    if(sk&&_audio.duration){sk.value=(_audio.currentTime/_audio.duration)*100;}
    if(ct)ct.textContent=fmtTime(_audio.currentTime);
  });
  _audio.addEventListener('loadedmetadata',()=>{
    const dt=document.getElementById('dur-t');if(dt)dt.textContent=fmtTime(_audio.duration);
  });
  _audio.addEventListener('ended',()=>nextT());
  loadTPlay(_curTr);
}
function fmtTime(s){if(!s||isNaN(s))return'0:00';const m=Math.floor(s/60);return m+':'+(Math.floor(s%60)+'').padStart(2,'0');}
function loadTPlay(i){
  _curTr=i;
  if(!_audio)return;
  const t=_tracks[i];
  _audio.src=t.src;
  _audio.load();
  const tt=document.getElementById('music-title');if(tt)tt.textContent=t.title;
  document.querySelectorAll('.pl-item').forEach((el,idx)=>el.classList.toggle('active',idx===i));
}
function togglePlay(){
  if(!_audio)return;
  const disc=document.getElementById('mdisc');const btn=document.getElementById('play-btn');
  if(_audio.paused){
    _audio.play().then(()=>{disc?.classList.add('playing');if(btn)btn.innerHTML='<svg fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';}).catch(()=>{});
  } else {
    _audio.pause();disc?.classList.remove('playing');if(btn)btn.innerHTML='<svg fill="currentColor" viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>';
  }
}
function nextT(){loadTPlay((_curTr+1)%_tracks.length);_audio?.play().catch(()=>{});}
function prevT(){loadTPlay((_curTr-1+_tracks.length)%_tracks.length);_audio?.play().catch(()=>{});}
function seekTo(v){if(_audio&&_audio.duration)_audio.currentTime=(_audio.duration*v)/100;}
function changePw(){
  const o=document.getElementById('pw-old')?.value;
  const n=document.getElementById('pw-new')?.value;
  if(!o||!n){showError('Nhập đủ thông tin!','');return;}
  const fd=new FormData();fd.append('old_pw',o);fd.append('new_pw',n);
  const msg=document.getElementById('pw-msg');
  fetch('/change-password',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(msg){msg.textContent=d.msg;msg.style.cssText='display:block;background:'+(d.ok?'#d1fae5':'#fee2e2')+';color:'+(d.ok?'#065f46':'#991b1b')+';border-radius:8px;padding:.4rem .6rem;';}
    if(d.ok)setTimeout(()=>location.href='/login',1500);
  }).catch(()=>{if(msg)msg.textContent='Lỗi kết nối!';msg.style.cssText='display:block;background:#fee2e2;color:#991b1b;border-radius:8px;padding:.4rem .6rem;';});
}
document.addEventListener('DOMContentLoaded',()=>{
  fetch('/api/acc-count').then(r=>r.json()).then(d=>{stockMap=d;renderStock();}).catch(()=>{});
  const first=document.getElementById('pg-home');
  if(first)setTimeout(()=>first.classList.add('visible'),80);
  loadFeedbacks();
  setInterval(updateBalance,30000);
  updateBalance();
  if(!window.NO_MUSIC){
    initDisc();
    const tryPlay=()=>{if(_audio&&_audio.paused){_audio.play().then(()=>{const disc=document.getElementById('mdisc');disc?.classList.add('playing');const btn=document.getElementById('play-btn');if(btn)btn.innerHTML='<svg fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';}).catch(()=>{});}};
    document.body.addEventListener('click',tryPlay,{once:true});
    document.body.addEventListener('touchstart',tryPlay,{once:true});
    setTimeout(()=>{if(_audio&&_audio.paused)_audio.play().catch(()=>{});},500);
  }
});
</script>
"""

def LAYOUT(body):
    return """<!DOCTYPE html>
<html lang="vi">
<head>""" + BASE_CSS + """
<title>Shop TMinh - Cày Thuê & Bán Acc Free Fire</title>
</head>
<body>
<div id="ls">
  <div class="ls-logo">Shop <span>TMinh</span></div>
  <div class="ls-bar"><div class="ls-fill"></div></div>
  <div class="ls-text">Đang tải...</div>
</div>
<div id="st-overlay"></div>
<div id="st"><div class="st-check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div><div class="st-msg"></div><div class="st-sub"></div></div>
<div id="et"><div class="et-x"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></div><div class="et-msg"></div><div class="et-sub"></div></div>

<nav class="navbar">
  <div class="hamburger" onclick="openDrawer()"><span></span><span></span><span></span></div>
  <div class="nav-logo">Shop <span>TMinh</span></div>
  <div class="nav-bal" id="nav-bal" onclick="showPage('topup',document.getElementById('mi-topup'))">---đ</div>
  <div class="nav-bell" onclick="showPage('notifs',document.getElementById('mi-notifs'))">
    <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
    <div class="notif-dot" id="notif-dot"></div>
  </div>
</nav>

<div class="doverlay" id="doverlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
  <div class="dhead">
    <h3>Shop TMinh</h3>
    <p>Cày Thuê & Bán Acc Free Fire</p>
  </div>
  <div class="dmenu">
    <div class="ditem active" id="mi-home" onclick="showPage('home',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
      <span>Trang Chủ</span>
    </div>
    <div class="ditem" id="mi-shop" onclick="showPage('shop',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>
      <span>Mua Acc Clone</span>
    </div>
    <div class="ditem" id="mi-tuchon" onclick="showPage('tuchon',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 001.97-1.67l1.63-8.33H6"/></svg>
      <span>Acc Tự Chọn</span>
    </div>
    <div class="ditem" id="mi-carry" onclick="showPage('carry',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
      <span>Kéo Thuê FF</span>
    </div>
    <div class="ditem" id="mi-fffiles" onclick="showPage('fffiles',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
      <span>File Free Fire</span>
    </div>
    <div class="ditem" id="mi-topup" onclick="showPage('topup',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
      <span>Nạp Tiền</span>
    </div>
    <div class="ditem" id="mi-music" onclick="showPage('music',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
      <span>Nhạc Game</span>
    </div>
    <div class="ditem" id="mi-support" onclick="showPage('support',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      <span>Admin & Hỗ Trợ</span>
    </div>
    <div class="ditem" id="mi-notifs" onclick="showPage('notifs',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
      <span>Thông Báo</span>
    </div>
    <div class="ditem" id="mi-profile" onclick="showPage('profile',this)">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      <span>Tài Khoản</span>
    </div>
  </div>
  <div class="dfooter">
    <a href="/logout"><button class="btn btn-outline" style="width:100%;font-size:.82rem;">🚪 Đăng Xuất</button></a>
  </div>
</div>

<!-- MODALS -->
<div class="modal-ov" id="buy-modal">
  <div class="modal">
    <div class="modal-title">🛒 Mua Acc — <span id="buy-cat-name"></span></div>
    <div class="fg"><label class="fl">Số lượng</label><input class="fi" type="number" id="buy-qty" value="1" min="1" max="10" oninput="updBuyTotal()"></div>
    <div style="text-align:center;margin:.5rem 0;"><span style="font-size:.82rem;color:var(--muted);">Đơn giá: </span><span id="buy-price-preview" style="font-weight:700;color:var(--accent);"></span></div>
    <div style="background:#eef2ff;border-radius:10px;padding:.65rem;text-align:center;margin-bottom:.7rem;"><div style="font-size:.8rem;color:var(--muted);">Tổng tiền:</div><div id="buy-total-preview" style="font-size:1.3rem;font-weight:800;color:var(--accent);"></div></div>
    <div class="fg" style="margin-bottom:.5rem;">
      <label class="fl">🎟️ Mã giảm giá (không bắt buộc)</label>
      <div style="display:flex;gap:.4rem;">
        <input class="fi" type="text" id="buy-coupon" placeholder="Nhập mã giảm giá..." style="margin-bottom:0;text-transform:uppercase;" oninput="this.value=this.value.toUpperCase()">
        <button class="btn btn-outline btn-sm" onclick="applyCoupon()" style="flex-shrink:0;white-space:nowrap;">Áp dụng</button>
      </div>
      <div id="coupon-msg" style="display:none;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;"></div>
      <div id="coupon-discount-row" style="display:none;background:#d1fae5;border-radius:8px;padding:.4rem .7rem;margin-top:.3rem;font-size:.8rem;color:#065f46;font-weight:600;"></div>
    </div>
    <div style="display:flex;gap:.6rem;">
      <button class="btn btn-outline" style="flex:1;" onclick="closeBuyModal()">Hủy</button>
      <button class="btn btn-primary" style="flex:1;" id="buy-submit-btn" onclick="doBuy()">✅ Xác Nhận Mua</button>
    </div>
  </div>
</div>
<div class="modal-ov" id="result-modal">
  <div class="modal">
    <div class="modal-title">🎉 Kết Quả Mua Acc</div>
    <div id="result-body"></div>
    <button class="btn btn-primary btn-full" style="margin-top:.9rem;" onclick="closeResultModal()">Đã lưu thông tin ✓</button>
  </div>
</div>
<div class="modal-ov" id="topup-modal">
  <div class="modal">
    <div class="modal-title">💳 Thông Tin Chuyển Khoản</div>
    <div class="qr-box" style="margin-bottom:.8rem;">
      <img src="/bank.jpg" alt="QR" onerror="this.style.display='none'">
    </div>
    <div id="topup-bank-detail" style="margin-bottom:.7rem;font-size:.85rem;line-height:1.9;"></div>
    <div class="content-box">
      <div style="font-size:.72rem;font-weight:700;color:var(--muted);margin-bottom:.3rem;">NỘI DUNG CHUYỂN KHOẢN (BẮT BUỘC)</div>
      <div class="content-code" id="topup-content-code" style="cursor:pointer;"></div>
      <div style="font-size:.7rem;color:var(--muted);margin-top:.3rem;">👆 Nhấn để sao chép</div>
    </div>
    <div class="timer-box"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>Hết hạn: <span id="topup-timer">60:00</span></div>
    <div style="font-size:.78rem;color:var(--red);font-weight:600;margin:.5rem 0;text-align:center;">⚠️ Ghi đúng nội dung CK để admin duyệt nhanh!</div>
    <button class="btn btn-outline btn-full" onclick="closeTopupModal()">Đóng</button>
  </div>
</div>
<div class="modal-ov" id="carry-contact-modal">
  <div class="modal">
    <div id="carry-contact-body"></div>
    <button class="btn btn-outline btn-full" style="margin-top:.7rem;" onclick="closeCarryModal()">Đóng</button>
  </div>
</div>
<div class="modal-ov" id="ff-buy-modal">
  <div class="modal">
    <div class="modal-title">🛒 Mua File — <span id="ff-buy-name"></span></div>
    <div style="text-align:center;margin:.5rem 0;"><span style="font-size:.82rem;color:var(--muted);">Giá: </span><span id="ff-buy-price-display" style="font-weight:700;color:var(--accent);"></span></div>
    <div style="background:#eef2ff;border-radius:10px;padding:.65rem;text-align:center;margin-bottom:.7rem;"><div style="font-size:.8rem;color:var(--muted);">Tổng tiền:</div><div id="ff-buy-total" style="font-size:1.3rem;font-weight:800;color:var(--accent);"></div></div>
    <div id="ff-coupon-row" class="fg" style="margin-bottom:.5rem;">
      <label class="fl">🎟️ Mã giảm giá (không bắt buộc)</label>
      <div style="display:flex;gap:.4rem;">
        <input class="fi" type="text" id="ff-buy-coupon" placeholder="Nhập mã giảm giá..." style="margin-bottom:0;text-transform:uppercase;" oninput="this.value=this.value.toUpperCase()">
        <button class="btn btn-outline btn-sm" onclick="applyFfCoupon()" style="flex-shrink:0;white-space:nowrap;">Áp dụng</button>
      </div>
      <div id="ff-coupon-msg" style="display:none;font-size:.76rem;margin-top:.3rem;padding:.3rem .6rem;border-radius:7px;"></div>
      <div id="ff-coupon-discount-row" style="display:none;background:#d1fae5;border-radius:8px;padding:.4rem .7rem;margin-top:.3rem;font-size:.8rem;color:#065f46;font-weight:600;"></div>
    </div>
    <div style="display:flex;gap:.6rem;">
      <button class="btn btn-outline" style="flex:1;" onclick="closeFfBuyModal()">Hủy</button>
      <button class="btn btn-primary" style="flex:1;" id="ff-buy-submit" onclick="doFfBuy()">✅ Xác Nhận</button>
    </div>
  </div>
</div>
<div class="modal-ov" id="ff-result-modal">
  <div class="modal">
    <div class="modal-title">🎉 Mua File Thành Công!</div>
    <div style="text-align:center;margin:.5rem 0 .9rem;">
      <div style="font-size:1.6rem;margin-bottom:.3rem;">📁</div>
      <div style="font-weight:700;font-size:.95rem;color:var(--primary);" id="ff-result-name"></div>
      <div style="font-size:.75rem;color:var(--green);margin-top:.25rem;" id="ff-result-coupon"></div>
    </div>
    <a id="ff-download-btn" href="#" download style="display:none;text-decoration:none;margin-bottom:.7rem;">
      <button class="btn btn-primary btn-full" style="background:linear-gradient(135deg,#10b981,#059669);font-size:.9rem;padding:.75rem;">📥 Tải File Về Máy</button>
    </a>
    <div id="ff-result-video" style="display:none;margin-bottom:.7rem;"></div>
    <button class="btn btn-outline btn-full" onclick="closeFfResultModal()">Đóng</button>
  </div>
</div>

<div class="content">
""" + body + """
</div>
<div id="fn">
  <div class="fn-top">
    <div class="fn-admin">
      <img src="/anh_admin.jpg" class="fn-admin-img" onerror="this.style.display='none'">
      <div class="fn-title" id="fn-title">Thông Báo</div>
    </div>
    <div class="fn-close" onclick="document.getElementById('fn').classList.remove('show')">✕</div>
  </div>
  <div class="fn-body" id="fn-body"></div>
  <div class="fn-actions" id="fn-actions"></div>
</div>
<script>
(function(){
  const ls=document.getElementById('ls');
  if(ls)setTimeout(()=>{ls.style.opacity='0';setTimeout(()=>ls.style.display='none',400);},700);
})();
fetch('/api/notice').then(r=>r.json()).then(d=>{
  if(!d.notice)return;
  const HIDE_KEY='notice_hidden_until';
  const hiddenUntil=parseInt(localStorage.getItem(HIDE_KEY)||'0');
  if(Date.now()<hiddenUntil)return;
  const fn=document.getElementById('fn');
  document.getElementById('fn-body').innerHTML=d.notice;
  let acts='';
  if(d.btn_desc&&d.zalo_link){acts+=`<a href="${d.zalo_link}" target="_blank"><button class="btn btn-zalo btn-sm">${d.btn_desc}</button></a>`;}
  if(d.tg_link){acts+=`<a href="${d.tg_link}" target="_blank"><button class="btn btn-outline btn-sm">✈️ Telegram</button></a>`;}
  acts+=`<button class="btn btn-outline btn-sm" onclick="document.getElementById('fn').classList.remove('show')" style="color:var(--muted);">Ẩn</button>`;
  acts+=`<button class="btn btn-outline btn-sm" onclick="localStorage.setItem('${HIDE_KEY}',Date.now()+7200000);document.getElementById('fn').classList.remove('show');" style="color:var(--muted);font-size:.72rem;">⏱ Ẩn 2 Giờ</button>`;
  document.getElementById('fn-actions').innerHTML=acts;
  setTimeout(()=>fn.classList.add('show'),1200);
}).catch(()=>{});
</script>
""" + BASE_JS + """
</body></html>"""

MAIN_BODY = """
<!-- HOME -->
<div class="page active" id="pg-home" style="display:block;">
  <div class="hero-section">
    <div style="display:flex;align-items:center;gap:.9rem;margin-bottom:1rem;">
      <img src="/anh_admin.jpg" style="width:52px;height:52px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,.4);" onerror="this.style.display='none'" alt="TMinh">
      <div>
        <div style="font-weight:800;font-size:1.05rem;">Shop TMinh</div>
        <div style="font-size:.72rem;opacity:.75;">Free Fire — Uy Tín #1</div>
      </div>
    </div>
    <div style="font-size:1.25rem;font-weight:800;margin-bottom:.3rem;">🎮 Cày Thuê & Bán Acc</div>
    <div style="font-size:.78rem;opacity:.75;">Kim Cương 25k • Bạch Kim 20k • Lv5 2.5k</div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:.55rem;margin-bottom:1rem;">
    <div class="quick-card" onclick="showPage('shop',document.getElementById('mi-shop'))">
      <div style="font-size:1.4rem;margin-bottom:.2rem;">💜</div>
      <div style="font-size:.65rem;font-weight:700;color:var(--primary);">Mua Acc</div>
    </div>
    <div class="quick-card" onclick="showPage('carry',document.getElementById('mi-carry'))">
      <div style="font-size:1.4rem;margin-bottom:.2rem;">⭐</div>
      <div style="font-size:.65rem;font-weight:700;color:var(--primary);">Kéo Thuê</div>
    </div>
    <div class="quick-card" onclick="showPage('fffiles',document.getElementById('mi-fffiles'))">
      <div style="font-size:1.4rem;margin-bottom:.2rem;">📁</div>
      <div style="font-size:.65rem;font-weight:700;color:var(--primary);">File FF</div>
    </div>
    <div class="quick-card" onclick="showPage('topup',document.getElementById('mi-topup'))">
      <div style="font-size:1.4rem;margin-bottom:.2rem;">💳</div>
      <div style="font-size:.65rem;font-weight:700;color:var(--primary);">Nạp Tiền</div>
    </div>
  </div>

  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">🎮 Dịch Vụ Nổi Bật</div>
    <div onclick="showPage('carry',document.getElementById('mi-carry'))" class="service-card" style="background:linear-gradient(135deg,#fff7ed,#fffbeb);border-color:#fed7aa;margin-bottom:.65rem;">
      <div style="width:44px;height:44px;background:linear-gradient(135deg,#f59e0b,#d97706);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <svg width="22" height="22" fill="white" viewBox="0 0 24 24"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
      </div>
      <div style="flex:1;min-width:0;">
        <div style="font-weight:700;font-size:.88rem;color:#92400e;">Kéo Thuê Rank Free Fire</div>
        <div style="font-size:.72rem;color:#b45309;margin-top:.1rem;">Đồng→Kim Cương: 1.000đ/sao • Cao Thủ→Thách Đấu: 1.500đ/sao</div>
        <div style="font-size:.68rem;color:#78716c;margin-top:.15rem;">✅ Bao thắng • Tối thiểu 5 sao • Chuyên nghiệp</div>
      </div>
    </div>
    <div onclick="showPage('shop',document.getElementById('mi-shop'))" class="service-card" style="background:linear-gradient(135deg,#faf5ff,#f3e8ff);border-color:#d8b4fe;margin-bottom:.65rem;">
      <div style="width:44px;height:44px;background:linear-gradient(135deg,#7c3aed,#6d28d9);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <svg width="22" height="22" fill="none" stroke="white" stroke-width="2" viewBox="0 0 24 24"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>
      </div>
      <div style="flex:1;min-width:0;">
        <div style="font-weight:700;font-size:.88rem;color:#5b21b6;">Bán Acc Clone Free Fire</div>
        <div style="font-size:.72rem;color:#7c3aed;margin-top:.1rem;">Kim Cương 25k • Bạch Kim 20k • Lv5 Google 2.5k</div>
        <div style="font-size:.68rem;color:#78716c;margin-top:.15rem;">✅ Bảo hành 100% • Nhận ngay • Bảo mật</div>
      </div>
    </div>
    <div onclick="showPage('fffiles',document.getElementById('mi-fffiles'))" class="service-card" style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);border-color:#86efac;">
      <div style="width:44px;height:44px;background:linear-gradient(135deg,#10b981,#059669);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <svg width="22" height="22" fill="none" stroke="white" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      </div>
      <div style="flex:1;min-width:0;">
        <div style="font-weight:700;font-size:.88rem;color:#065f46;">Bán File Free Fire</div>
        <div style="font-size:.72rem;color:#10b981;margin-top:.1rem;">File hack, tool, config, apk mod...</div>
        <div style="font-size:.68rem;color:#78716c;margin-top:.15rem;">✅ Có video hướng dẫn • Hỗ trợ cài đặt</div>
      </div>
    </div>
  </div>

  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">🖼️ Acc Nổi Bật</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin-bottom:.7rem;">
      <div onclick="showPage('shop',document.getElementById('mi-shop'))" style="cursor:pointer;">
        <div class="rainbow-wrap">
          <img src="/acc_kim_cuong.jpg" alt="Kim Cương" style="width:100%;display:block;border-radius:11px;" loading="lazy" onerror="this.parentNode.style.cssText='background:linear-gradient(135deg,#8b5cf6,#7c3aed);border-radius:14px;height:100px;padding:3px;'">
        </div>
        <div style="font-size:.72rem;font-weight:700;color:var(--primary);margin-top:.35rem;text-align:center;">💜 Kim Cương — 25k</div>
      </div>
      <div onclick="showPage('shop',document.getElementById('mi-shop'))" style="cursor:pointer;">
        <div class="rainbow-wrap">
          <img src="/acc_bach_kim.png" alt="Bạch Kim" style="width:100%;display:block;border-radius:11px;" loading="lazy" onerror="this.parentNode.style.cssText='background:linear-gradient(135deg,#0891b2,#0e7490);border-radius:14px;height:100px;padding:3px;'">
        </div>
        <div style="font-size:.72rem;font-weight:700;color:var(--primary);margin-top:.35rem;text-align:center;">🔵 Bạch Kim — 20k</div>
      </div>
    </div>
    <div onclick="showPage('carry',document.getElementById('mi-carry'))" style="cursor:pointer;">
      <div class="rainbow-wrap">
        <img src="/keothue.png" alt="Kéo Thuê FF" style="width:100%;display:block;border-radius:11px;" loading="lazy" onerror="this.parentNode.style.cssText='background:linear-gradient(135deg,#f59e0b,#d97706);border-radius:14px;height:80px;padding:3px;'">
      </div>
    </div>
  </div>

  <div class="card" id="feedback-section" style="margin-bottom:.9rem;display:none;">
    <div class="card-title">🏅 Feedback Kéo Rank Thực Tế</div>
    <div id="feedback-list"></div>
  </div>

  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">👤 Admin & Quản Trị</div>
    <div id="admin-list">
      <div class="admin-card">
        <div style="position:relative;flex-shrink:0;">
          <img src="/anh_admin.jpg" style="width:55px;height:55px;border-radius:50%;object-fit:cover;border:2px solid var(--accent);" onerror="this.style.display='none'" alt="TMinh">
          <div style="position:absolute;bottom:-2px;right:-2px;background:var(--accent);color:#fff;font-size:.5rem;font-weight:800;padding:.1rem .3rem;border-radius:8px;">MAIN</div>
        </div>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:700;font-size:.92rem;color:var(--primary);">TMinh</div>
          <div style="font-size:.72rem;color:var(--accent);font-weight:600;margin-bottom:.4rem;">Admin Chính</div>
          <div style="display:flex;gap:.35rem;flex-wrap:wrap;">
            <a href=\"""" + TIKTOK_URL + """\" target="_blank"><button class="btn btn-tt btn-sm" style="padding:.3rem .6rem;font-size:.7rem;">🎵 TikTok</button></a>
            <a href="https://zalo.me/""" + ZALO_PHONE + """" target="_blank"><button class="btn btn-zalo btn-sm" style="padding:.3rem .6rem;font-size:.7rem;">🔵 Zalo</button></a>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">🛡️ Cam Kết</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.6rem;font-size:.75rem;">
      <div style="background:#f0fdf4;border-radius:10px;padding:.65rem;"><div style="font-size:1rem;margin-bottom:.2rem;">✅</div><div style="font-weight:600;color:#065f46;">Bảo hành 100%</div></div>
      <div style="background:#eff6ff;border-radius:10px;padding:.65rem;"><div style="font-size:1rem;margin-bottom:.2rem;">⚡</div><div style="font-weight:600;color:#1e40af;">Nhận ngay tức thì</div></div>
      <div style="background:#fef3c7;border-radius:10px;padding:.65rem;"><div style="font-size:1rem;margin-bottom:.2rem;">🔒</div><div style="font-weight:600;color:#92400e;">Bảo mật tuyệt đối</div></div>
      <div style="background:#fdf4ff;border-radius:10px;padding:.65rem;"><div style="font-size:1rem;margin-bottom:.2rem;">💬</div><div style="font-weight:600;color:#6b21a8;">Hỗ trợ 24/7</div></div>
    </div>
  </div>
</div>

<!-- SHOP -->
<div class="page" id="pg-shop">
  <div class="tabs">
    <div class="tab active" id="tab-kim_cuong" onclick="shopTab('kim_cuong',this)">Kim Cương</div>
    <div class="tab" id="tab-bach_kim" onclick="shopTab('bach_kim',this)">Bạch Kim</div>
    <div class="tab" id="tab-lv5" onclick="shopTab('lv5',this)">Lv5 Google</div>
  </div>
  <div id="sh-kim_cuong">
    <div class="acc-card">
      <div class="rainbow-wrap">
        <img src="/acc_kim_cuong.jpg" alt="Kim Cương" style="width:100%;display:block;" loading="lazy" onerror="this.parentNode.style.cssText='background:linear-gradient(135deg,#8b5cf6,#7c3aed);border-radius:14px;height:170px;padding:3px;'">
      </div>
      <div class="acc-body">
        <div class="acc-badge">⭐ Rank Kim Cương I</div>
        <div class="acc-title">Clon Rank Kim Cương Free Fire</div>
        <div class="acc-desc">🛡️ Bảo Hành Acc 100% Cam Kết Uy Tín • Rank Kim Cương I • Thông tin clone bảo mật • Nhận acc ngay sau thanh toán</div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.7rem;flex-wrap:wrap;gap:.5rem;">
          <div><div class="acc-price">25.000đ / acc</div><div class="acc-stock" id="stk-kim_cuong">Đang tải...</div></div>
          <button class="btn btn-primary" onclick="openBuy('kim_cuong')">🛒 Mua Ngay</button>
        </div>
      </div>
    </div>
  </div>
  <div id="sh-bach_kim" style="display:none;">
    <div class="acc-card">
      <div class="rainbow-wrap">
        <img src="/acc_bach_kim.png" alt="Bạch Kim" style="width:100%;display:block;" loading="lazy" onerror="this.parentNode.style.cssText='background:linear-gradient(135deg,#0891b2,#0e7490);border-radius:14px;height:170px;padding:3px;'">
      </div>
      <div class="acc-body">
        <div class="acc-badge" style="background:linear-gradient(135deg,#0891b2,#0e7490);">💎 Rank Bạch Kim I</div>
        <div class="acc-title">Clon Rank Bạch Kim Free Fire</div>
        <div class="acc-desc">🛡️ Bảo Hành Acc 100% Cam Kết Uy Tín • Rank Bạch Kim I • Thông tin clone bảo mật • Nhận acc ngay sau thanh toán</div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.7rem;flex-wrap:wrap;gap:.5rem;">
          <div><div class="acc-price" style="color:#0891b2;">20.000đ / acc</div><div class="acc-stock" id="stk-bach_kim">Đang tải...</div></div>
          <button class="btn btn-primary" style="background:linear-gradient(135deg,#0891b2,#0e7490);" onclick="openBuy('bach_kim')">🛒 Mua Ngay</button>
        </div>
      </div>
    </div>
  </div>
  <div id="sh-lv5" style="display:none;">
    <div class="acc-card">
      <div class="rainbow-wrap">
        <img src="/acc_lv5.jpg" alt="Lv5" style="width:100%;display:block;" loading="lazy" onerror="this.parentNode.style.cssText='background:linear-gradient(135deg,#2563eb,#1d4ed8);border-radius:14px;height:170px;padding:3px;'">
      </div>
      <div class="acc-body">
        <div class="acc-badge" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);">🎮 Lv5 Google</div>
        <div class="acc-title">Clon Lv5 Google Free Fire</div>
        <div class="acc-desc">🛡️ Bảo Hành Acc 100% Cam Kết Uy Tín • Level 5 Google • Tài khoản sạch bảo mật • Giao ngay sau thanh toán</div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:.7rem;flex-wrap:wrap;gap:.5rem;">
          <div><div class="acc-price" style="color:#2563eb;">2.500đ / acc</div><div class="acc-stock" id="stk-lv5">Đang tải...</div></div>
          <button class="btn btn-primary" style="background:linear-gradient(135deg,#2563eb,#1d4ed8);" onclick="openBuy('lv5')">🛒 Mua Ngay</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ACC TỰ CHỌN -->
<div class="page" id="pg-tuchon">
  <div class="card" style="margin-bottom:.9rem;padding:0;overflow:hidden;">
    <div class="rainbow-wrap">
      <img src="/tuchon.png" alt="Acc Tự Chọn" style="width:100%;display:block;border-radius:14px;" loading="lazy">
    </div>
  </div>
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">🛒 Acc Tự Chọn</div>
    <p style="font-size:.82rem;color:var(--muted);margin-bottom:.9rem;">Acc chọn theo yêu cầu — xem thông tin và liên hệ admin để mua.</p>
    <div id="tuchon-list"><div style="text-align:center;color:var(--muted);padding:2rem;">Đang tải...</div></div>
  </div>
</div>

<!-- FILE FREE FIRE -->
<div class="page" id="pg-fffiles">
  <div style="margin-bottom:.9rem;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.1);">
    <img src="/anhteptin.png" alt="File Free Fire" style="width:100%;display:block;" loading="lazy" onerror="this.parentNode.style.display='none'">
  </div>
  <div class="card" style="margin-bottom:.9rem;background:linear-gradient(135deg,#064e3b,#065f46);color:#fff;">
    <div style="font-weight:800;font-size:1.1rem;margin-bottom:.3rem;">📁 File Free Fire</div>
    <div style="font-size:.78rem;opacity:.8;">Tool, config, apk mod và các file game hỗ trợ chơi FF</div>
    <div style="display:flex;gap:.5rem;margin-top:.7rem;flex-wrap:wrap;">
      <span style="background:rgba(255,255,255,.2);font-size:.7rem;font-weight:600;padding:.25rem .65rem;border-radius:20px;">✅ Có video hướng dẫn</span>
      <span style="background:rgba(255,255,255,.2);font-size:.7rem;font-weight:600;padding:.25rem .65rem;border-radius:20px;">🔒 An toàn</span>
    </div>
  </div>
  <div id="ff-list"><div style="text-align:center;color:var(--muted);padding:2rem;">Đang tải...</div></div>
</div>

<!-- NẠP TIỀN -->
<div class="page" id="pg-topup">
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">💰 Nạp Tiền Tài Khoản</div>
    <div style="background:linear-gradient(135deg,#eef2ff,#f5f3ff);border-radius:12px;padding:.9rem;margin-bottom:.9rem;border:1.5px solid var(--accent);">
      <div style="font-size:.8rem;font-weight:700;color:var(--primary);margin-bottom:.5rem;">🏦 Thông Tin Chuyển Khoản</div>
      <div style="font-size:.8rem;color:var(--text);line-height:1.9;">
        <div>💳 <b>Nền Tảng:</b> <span style="font-weight:700;color:var(--accent);">""" + BANK_NAME + """</span></div>
        <div>👤 <b>Tên:</b> <span style="font-weight:700;">""" + BANK_HOLDER + """</span></div>
      </div>
    </div>
    <div class="qr-box" style="margin-bottom:.9rem;">
      <img src="/bank.jpg" alt="QR Zalopay" onerror="this.style.display='none'">
      <div style="font-size:.75rem;color:var(--muted);margin-top:.5rem;">QR chuyển khoản ZaloPay</div>
    </div>
    <p style="font-size:.82rem;color:var(--muted);margin-bottom:.9rem;">Nhập số tiền muốn nạp, hệ thống tự tạo mã và thông báo admin duyệt. <b>Bắt buộc ghi đúng nội dung CK.</b></p>
    <div class="fg">
      <label class="fl">Số tiền nạp (đ)</label>
      <input class="fi" type="number" id="topup-amount" placeholder="Ví dụ: 50000" min="1000" inputmode="numeric">
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem;margin-bottom:.9rem;">
      <button class="btn btn-outline btn-sm" onclick="setTopupAmt(25000)">25.000đ</button>
      <button class="btn btn-outline btn-sm" onclick="setTopupAmt(50000)">50.000đ</button>
      <button class="btn btn-outline btn-sm" onclick="setTopupAmt(100000)">100.000đ</button>
      <button class="btn btn-outline btn-sm" onclick="setTopupAmt(200000)">200.000đ</button>
      <button class="btn btn-outline btn-sm" onclick="setTopupAmt(500000)">500.000đ</button>
      <button class="btn btn-outline btn-sm" onclick="setTopupAmt(1000000)">1.000.000đ</button>
    </div>
    <button class="btn btn-primary btn-full" onclick="requestTopup()">💳 Tạo Yêu Cầu Nạp Tiền</button>
  </div>
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">📋 Lịch Sử Nạp Tiền</div>
    <div id="topup-hist"><div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.82rem;">Đang tải...</div></div>
  </div>
</div>

<!-- KÉO THUÊ FF -->
<div class="page" id="pg-carry">
  <div class="card" style="margin-bottom:.9rem;padding:0;overflow:hidden;">
    <div class="rainbow-wrap">
      <img src="/keothue.png" alt="Kéo Thuê Free Fire" style="width:100%;display:block;border-radius:14px;" loading="lazy">
    </div>
  </div>
  <div class="card" style="margin-bottom:.9rem;text-align:center;">
    <div style="font-weight:800;font-size:1.1rem;color:var(--primary);margin-bottom:.3rem;">⭐ Kéo Thuê Free Fire</div>
    <div style="font-size:.82rem;color:var(--muted);margin-bottom:.6rem;">Bao thắng • Chuyên nghiệp • Giá rẻ</div>
    <div style="display:flex;justify-content:center;gap:.5rem;flex-wrap:wrap;">
      <span style="background:#fef3c7;color:#92400e;font-size:.72rem;font-weight:700;padding:.25rem .65rem;border-radius:20px;border:1px solid #fde68a;">🥉 Đồng~Kim Cương: 1.000đ/sao</span>
      <span style="background:#fdf4ff;color:#6b21a8;font-size:.72rem;font-weight:700;padding:.25rem .65rem;border-radius:20px;border:1px solid #e9d5ff;">👑 Cao Thủ~Thách Đấu: 1.500đ/sao</span>
      <span style="background:#d1fae5;color:#065f46;font-size:.72rem;font-weight:700;padding:.25rem .65rem;border-radius:20px;border:1px solid #6ee7b7;">🎁 Từ 10 sao: Giảm 10%</span>
    </div>
    <div style="font-size:.72rem;color:var(--red);font-weight:700;margin-top:.5rem;">⚠️ Tối thiểu 5 sao mới nhận đặt</div>
  </div>

  <div class="card" style="margin-bottom:.9rem;background:linear-gradient(135deg,#1a1a2e,#302b63);color:#fff;">
    <div style="font-weight:700;font-size:.9rem;margin-bottom:.6rem;">📞 Liên Hệ Kéo Thuê</div>
    <div style="font-size:.82rem;margin-bottom:.7rem;opacity:.9;">Sau khi đặt đơn thành công, liên hệ admin theo thứ tự:</div>
    <div style="display:flex;flex-direction:column;gap:.45rem;">
      <div style="background:rgba(255,255,255,.1);border-radius:10px;padding:.65rem;">
        <div style="font-weight:700;font-size:.82rem;">👑 Admin Chính: TMinh</div>
        <div style="font-size:.72rem;opacity:.75;margin-bottom:.4rem;">Liên hệ đầu tiên</div>
        <div style="display:flex;gap:.4rem;">
          <a href=\"""" + TIKTOK_URL + """\" target="_blank"><button class="btn btn-tt btn-sm">🎵 TikTok</button></a>
          <a href="https://zalo.me/""" + ZALO_PHONE + """" target="_blank"><button class="btn btn-zalo btn-sm">🔵 Zalo</button></a>
        </div>
      </div>
      <div style="background:rgba(255,255,255,.07);border-radius:10px;padding:.65rem;">
        <div style="font-weight:600;font-size:.82rem;opacity:.8;">🛡️ Admin Phụ</div>
        <div style="font-size:.72rem;opacity:.6;">Liên hệ nếu admin chính không rep</div>
      </div>
    </div>
  </div>

  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">📋 Đặt Kéo Thuê</div>
    <div class="fg">
      <label class="fl">Rank hiện tại</label>
      <select class="fi fsel" id="carry-rank" onchange="updCarryTotal()">
        <option value="">-- Chọn rank --</option>
        <option value="Đồng">🥉 Đồng (1.000đ/sao)</option>
        <option value="Bạc">🥈 Bạc (1.000đ/sao)</option>
        <option value="Vàng">🥇 Vàng (1.000đ/sao)</option>
        <option value="Bạch Kim">💎 Bạch Kim (1.000đ/sao)</option>
        <option value="Kim Cương">💜 Kim Cương (1.000đ/sao)</option>
        <option value="Cao Thủ">🔥 Cao Thủ (1.500đ/sao)</option>
        <option value="Thách Đấu">🏆 Thách Đấu (1.500đ/sao)</option>
      </select>
    </div>
    <div class="fg">
      <label class="fl">Số sao cần kéo (tối thiểu 5 sao)</label>
      <input class="fi" type="number" id="carry-stars" placeholder="Ví dụ: 10" min="5" max="200" inputmode="numeric" oninput="updCarryTotal()">
    </div>
    <div class="carry-price-box" id="carry-price-box">
      <div class="carry-price-total" id="carry-total-display">0đ</div>
      <div class="carry-price-note" id="carry-price-per-star">Chọn rank và nhập số sao để tính tiền</div>
    </div>
    <div class="fg">
      <label class="fl">Ghi chú (tùy chọn)</label>
      <textarea class="fi" id="carry-note" placeholder="Ví dụ: kéo nhanh trong hôm nay..." rows="2"></textarea>
    </div>
    <button class="btn btn-primary btn-full" style="background:linear-gradient(135deg,var(--orange),#d97706);" onclick="orderCarry()" id="carry-submit-btn">⭐ Đặt Kéo Thuê Ngay</button>
  </div>
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">📊 Lịch Sử Kéo Thuê</div>
    <div id="carry-hist"><div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.82rem;">Đang tải...</div></div>
  </div>
</div>

<!-- MUSIC -->
<div class="page" id="pg-music">
  <div style="max-width:360px;margin:0 auto;">
    <div class="music-disc" id="mdisc"><div class="disc-bg"><div class="disc-center"></div></div></div>
    <div style="font-weight:700;font-size:1rem;text-align:center;color:var(--primary);margin-bottom:.2rem;" id="music-title">Nhạc FF 1</div>
    <div style="text-align:center;font-size:.76rem;color:var(--muted);margin-bottom:.9rem;">Shop TMinh Music</div>
    <div style="padding:0 .3rem;">
      <input type="range" class="music-seek" id="music-seek" value="0" min="0" max="100" step="0.1" oninput="seekTo(this.value)">
      <div style="display:flex;justify-content:space-between;font-size:.7rem;color:var(--muted);margin:.35rem 0 .9rem;">
        <span id="cur-t">0:00</span><span id="dur-t">0:00</span>
      </div>
    </div>
    <div style="display:flex;align-items:center;justify-content:center;gap:.9rem;margin-bottom:1.25rem;">
      <button class="mc-btn" onclick="prevT()"><svg fill="currentColor" viewBox="0 0 24 24"><polygon points="19,20 9,12 19,4"/><line x1="5" y1="19" x2="5" y2="5" stroke="currentColor" stroke-width="2"/></svg></button>
      <button class="mc-btn mc-play" id="play-btn" onclick="togglePlay()"><svg fill="currentColor" viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg></button>
      <button class="mc-btn" onclick="nextT()"><svg fill="currentColor" viewBox="0 0 24 24"><polygon points="5,4 15,12 5,20"/><line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2"/></svg></button>
    </div>
    <div class="card">
      <div class="card-title" style="margin-bottom:.6rem;">🎵 Danh sách phát</div>
      <div class="pl-item active" onclick="loadTPlay(0)"><div style="width:22px;text-align:center;font-size:.76rem;color:var(--muted);font-weight:600;">1</div><div style="flex:1;"><div style="font-weight:600;font-size:.83rem;">Nhạc FF 1</div><div style="font-size:.7rem;color:var(--muted);">Shop TMinh</div></div></div>
      <div class="pl-item" onclick="loadTPlay(1)"><div style="width:22px;text-align:center;font-size:.76rem;color:var(--muted);font-weight:600;">2</div><div style="flex:1;"><div style="font-weight:600;font-size:.83rem;">Nhạc FF 2</div><div style="font-size:.7rem;color:var(--muted);">Shop TMinh</div></div></div>
      <div class="pl-item" onclick="loadTPlay(2)"><div style="width:22px;text-align:center;font-size:.76rem;color:var(--muted);font-weight:600;">3</div><div style="flex:1;"><div style="font-weight:600;font-size:.83rem;">Nhạc FF 3</div><div style="font-size:.7rem;color:var(--muted);">Shop TMinh</div></div></div>
    </div>
  </div>
</div>

<!-- NOTIFS -->
<div class="page" id="pg-notifs">
  <div class="card">
    <div class="card-title">🔔 Thông Báo</div>
    <div id="notif-list"><div style="text-align:center;color:var(--muted);padding:2rem;font-size:.85rem;">Đang tải...</div></div>
  </div>
</div>

<!-- ADMIN & HỖ TRỢ -->
<div class="page" id="pg-support">
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">👑 Đội Ngũ Admin</div>
    <div id="admin-list" style="margin-bottom:0;"></div>
  </div>
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">📊 Thống Kê Shop</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.6rem;">
      <div style="background:#eef2ff;border-radius:10px;padding:.75rem;text-align:center;"><div style="font-size:1.3rem;font-weight:800;color:var(--accent);">1000+</div><div style="font-size:.72rem;color:var(--muted);margin-top:.1rem;">Khách hàng</div></div>
      <div style="background:#f0fdf4;border-radius:10px;padding:.75rem;text-align:center;"><div style="font-size:1.3rem;font-weight:800;color:var(--green);">100%</div><div style="font-size:.72rem;color:var(--muted);margin-top:.1rem;">Uy tín</div></div>
      <div style="background:#fffbeb;border-radius:10px;padding:.75rem;text-align:center;"><div style="font-size:1.3rem;font-weight:800;color:var(--orange);">24/7</div><div style="font-size:.72rem;color:var(--muted);margin-top:.1rem;">Hỗ trợ</div></div>
      <div style="background:#fdf4ff;border-radius:10px;padding:.75rem;text-align:center;"><div style="font-size:1.3rem;font-weight:800;color:#7c3aed;">#1</div><div style="font-size:.72rem;color:var(--muted);margin-top:.1rem;">Shop VN</div></div>
    </div>
  </div>
  <div class="card">
    <div class="card-title">❓ Câu Hỏi Thường Gặp</div>
    <div style="font-size:.82rem;color:var(--text);line-height:1.8;">
      <div style="padding:.4rem 0;border-bottom:1px solid var(--border);"><b>Acc có bảo hành không?</b><br>Có, bảo hành 100% hoàn tiền nếu acc lỗi trong 24 giờ.</div>
      <div style="padding:.4rem 0;border-bottom:1px solid var(--border);"><b>Nhận acc trong bao lâu?</b><br>Ngay sau khi thanh toán thành công.</div>
      <div style="padding:.4rem 0;border-bottom:1px solid var(--border);"><b>Nạp tiền như thế nào?</b><br>Vào mục Nạp Tiền, tạo yêu cầu, chuyển khoản ZaloPay đúng nội dung, admin duyệt nhanh.</div>
      <div style="padding:.4rem 0;border-bottom:1px solid var(--border);"><b>Kéo thuê bao lâu?</b><br>Thông thường 1-3 ngày tùy rank và số sao.</div>
      <div style="padding:.4rem 0;border-bottom:1px solid var(--border);"><b>Kéo thuê tối thiểu mấy sao?</b><br>Tối thiểu 5 sao. Đồng~Kim Cương: 1.000đ/sao. Cao Thủ~Thách Đấu: 1.500đ/sao.</div>
      <div style="padding:.4rem 0;"><b>File Free Fire có an toàn không?</b><br>Có, tất cả file đều được kiểm tra và có video hướng dẫn cài đặt.</div>
    </div>
  </div>
</div>

<!-- PROFILE -->
<div class="page" id="pg-profile">
  <div class="card" style="margin-bottom:.9rem;">
    <div style="text-align:center;margin-bottom:1rem;">
      <div style="width:60px;height:60px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto .5rem;">
        <svg width="26" height="26" fill="none" stroke="white" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      </div>
      <div style="font-weight:700;font-size:1.05rem;color:var(--primary);" id="pd-display">---</div>
      <div style="font-size:.76rem;color:var(--muted);" id="pd-user">---</div>
    </div>
    <div class="info-row"><span class="ik">Số dư</span><span class="iv" style="color:var(--accent);" id="pd-bal">---</span></div>
    <div class="info-row"><span class="ik">ID</span><span class="iv" id="pd-id">---</span></div>
    <div class="info-row"><span class="ik">Ngày tạo</span><span class="iv" id="pd-created" style="font-size:.76rem;">---</span></div>
    <div class="info-row"><span class="ik">IP cuối</span><span class="iv" id="pd-ip" style="font-size:.76rem;">---</span></div>
  </div>
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">🔒 Đổi Mật Khẩu</div>
    <div class="fg"><label class="fl">Mật khẩu hiện tại</label><input class="fi" type="password" id="pw-old" placeholder="Nhập mật khẩu hiện tại"></div>
    <div class="fg"><label class="fl">Mật khẩu mới</label><input class="fi" type="password" id="pw-new" placeholder="Ít nhất 4 ký tự"></div>
    <button class="btn btn-primary btn-full" onclick="changePw()">🔒 Đổi Mật Khẩu</button>
    <div id="pw-msg" style="display:none;margin-top:.5rem;font-size:.8rem;padding:.4rem .6rem;border-radius:8px;"></div>
  </div>
  <div class="card" style="margin-bottom:.9rem;">
    <div class="card-title">📋 Lịch Sử Giao Dịch</div>
    <div style="display:flex;gap:.3rem;margin-bottom:.8rem;overflow-x:auto;padding-bottom:.2rem;">
      <button id="htab-acc" class="btn btn-primary btn-sm active" onclick="loadHistoryTab('acc')" style="white-space:nowrap;flex-shrink:0;">📦 Mua Acc</button>
      <button id="htab-carry" class="btn btn-outline btn-sm" onclick="loadHistoryTab('carry')" style="white-space:nowrap;flex-shrink:0;">⭐ Kéo Thuê</button>
      <button id="htab-topup" class="btn btn-outline btn-sm" onclick="loadHistoryTab('topup')" style="white-space:nowrap;flex-shrink:0;">💳 Nạp Tiền</button>
      <button id="htab-ff" class="btn btn-outline btn-sm" onclick="loadHistoryTab('ff')" style="white-space:nowrap;flex-shrink:0;">📁 File FF</button>
    </div>
    <div id="hpane-acc"><div id="acc-history-list"><div style="text-align:center;color:var(--muted);padding:1.5rem;font-size:.83rem;">Đang tải...</div></div></div>
    <div id="hpane-carry" style="display:none;"><div id="carry-history-list"></div></div>
    <div id="hpane-topup" style="display:none;"><div id="topup-history-list"></div></div>
    <div id="hpane-ff" style="display:none;"><div id="ff-history-list"></div></div>
  </div>
  <div style="text-align:center;padding:.5rem 0 1rem;">
    <a href="/admin" style="text-decoration:none;">
      <button style="background:rgba(79,70,229,.08);color:#6b7280;border:1px solid #e5e7eb;border-radius:20px;padding:.3rem .9rem;font-size:.68rem;font-weight:600;cursor:pointer;letter-spacing:.02em;">⚙️ Admin</button>
    </a>
  </div>
</div>
"""

MAIN_TEMPLATE = LAYOUT(MAIN_BODY)

# ── AUTH TEMPLATE ─────────────────────────────────────────────────────────────
AUTH_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>""" + BASE_CSS + """
<title>{% if mode=='login' %}Đăng Nhập{% else %}Đăng Ký{% endif %} - Shop TMinh</title>
<style>
body{display:flex;align-items:center;justify-content:center;min-height:100vh;background:linear-gradient(135deg,#f0f4ff 0%,#fdf4ff 100%);padding:1rem;}
.auth-card{background:#fff;border-radius:22px;padding:1.75rem 1.5rem;width:100%;max-width:380px;box-shadow:0 20px 60px rgba(79,70,229,.11);border:1px solid var(--border);animation:authIn .4s cubic-bezier(.34,1.56,.64,1);}
@keyframes authIn{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}
.auth-tabs{display:flex;background:#f3f4f6;border-radius:11px;padding:.25rem;margin-bottom:1.35rem;}
.auth-tab{flex:1;padding:.5rem;text-align:center;border-radius:8px;font-size:.84rem;font-weight:600;cursor:pointer;color:var(--muted);text-decoration:none;transition:.2s;}
.auth-tab.active{background:#fff;color:var(--accent);box-shadow:0 2px 8px rgba(0,0,0,.07);}
.err-box{background:#fee2e2;border:1px solid #fca5a5;border-radius:10px;padding:.6rem .85rem;font-size:.8rem;color:#991b1b;margin-bottom:.9rem;font-weight:500;}
.ok-box{background:#d1fae5;border:1px solid #6ee7b7;border-radius:10px;padding:.6rem .85rem;font-size:.8rem;color:#065f46;margin-bottom:.9rem;font-weight:500;}
</style>
</head>
<body>
<div id="st-overlay"></div>
<div id="st"><div class="st-check"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div><div class="st-msg"></div><div class="st-sub"></div></div>
<div id="et"><div class="et-x"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></div><div class="et-msg"></div><div class="et-sub"></div></div>
<div class="auth-card">
  <div style="text-align:center;margin-bottom:1.1rem;">
    <div style="font-size:1.45rem;font-weight:800;color:var(--primary);">Shop <span style="color:var(--accent);">TMinh</span></div>
    <div style="font-size:.78rem;color:var(--muted);margin-top:.2rem;">Cày Thuê & Bán Acc Free Fire Uy Tín</div>
  </div>
  <div class="auth-tabs">
    <a href="/login" class="auth-tab {% if mode=='login' %}active{% endif %}">Đăng Nhập</a>
    <a href="/register" class="auth-tab {% if mode=='register' %}active{% endif %}">Đăng Ký</a>
  </div>
  {% if error %}<div class="err-box">{{ error }}</div>{% endif %}
  {% if request.args.get('registered') %}<div class="ok-box">✅ Đăng ký thành công! Hãy đăng nhập để tiếp tục.</div>{% endif %}
  <form method="POST" autocomplete="on">
    {% if mode=='register' %}
    <div class="fg"><label class="fl">Tên hiển thị (tùy chọn)</label><input class="fi" name="display" placeholder="Tên của bạn" autocomplete="name"></div>
    {% endif %}
    <div class="fg"><label class="fl">Tên đăng nhập</label><input class="fi" name="username" placeholder="Nhập tên đăng nhập" required autocomplete="username" value="{{ prefill_user }}"></div>
    <div class="fg"><label class="fl">Mật khẩu</label><input class="fi" type="password" name="password" placeholder="Nhập mật khẩu" required autocomplete="{% if mode=='login' %}current-password{% else %}new-password{% endif %}"></div>
    {% if need_captcha %}
    <div class="cap-box">
      <div class="cap-q">{{ cap_a }} + {{ cap_b }} = ?</div>
      <input class="cap-input" name="captcha_answer" placeholder="?" type="number" required inputmode="numeric">
    </div>
    {% endif %}
    <button type="submit" class="btn btn-primary btn-full" style="font-size:.9rem;padding:.75rem;">
      {% if mode=='login' %}🔓 Đăng Nhập{% else %}✨ Tạo Tài Khoản{% endif %}
    </button>
  </form>
  <div style="text-align:center;margin-top:.9rem;font-size:.78rem;color:var(--muted);">
    {% if mode=='login' %}Chưa có tài khoản? <a href="/register" style="color:var(--accent);font-weight:600;">Đăng ký ngay</a>
    {% else %}Đã có tài khoản? <a href="/login" style="color:var(--accent);font-weight:600;">Đăng nhập</a>{% endif %}
  </div>
</div>
<script>window.NO_MUSIC=true;</script>
""" + BASE_JS + """
</body></html>"""

# ── ADMIN LOGIN ────────────────────────────────────────────────────────────────
ADMIN_LOGIN_TMPL = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Login - Shop TMinh</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif;}
body{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1rem;}
.card{background:rgba(255,255,255,.05);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,.1);border-radius:20px;padding:2rem;width:100%;max-width:380px;animation:fadeIn .4s ease;}
@keyframes fadeIn{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
h1{color:#fff;font-size:1.4rem;font-weight:800;margin-bottom:.3rem;}
p{color:rgba(255,255,255,.6);font-size:.82rem;margin-bottom:1.5rem;}
label{display:block;color:rgba(255,255,255,.7);font-size:.76rem;font-weight:600;margin-bottom:.35rem;text-transform:uppercase;letter-spacing:.04em;}
input{width:100%;padding:.75rem 1rem;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:10px;color:#fff;font-size:.9rem;outline:none;margin-bottom:1rem;transition:.2s;}
input:focus{border-color:#4f46e5;background:rgba(255,255,255,.12);}
input::placeholder{color:rgba(255,255,255,.4);}
button{width:100%;padding:.8rem;background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;border:none;border-radius:10px;font-size:.9rem;font-weight:700;cursor:pointer;transition:.2s;}
button:active{transform:scale(.97);}
.err{background:rgba(239,68,68,.2);border:1px solid rgba(239,68,68,.4);color:#fca5a5;border-radius:10px;padding:.6rem .85rem;font-size:.82rem;margin-bottom:1rem;}
</style>
</head>
<body>
<div class="card">
  <h1>🔐 Admin Panel</h1>
  <p>Shop TMinh Management System</p>
  {% if error %}<div class="err">{{ error }}</div>{% endif %}
  <form method="POST">
    <label>Tên đăng nhập</label>
    <input name="username" placeholder="Admin username" required>
    <label>Mật khẩu</label>
    <input type="password" name="password" placeholder="Admin password" required>
    <button type="submit">Đăng Nhập</button>
  </form>
</div>
</body></html>"""

# ── ADMIN PANEL ────────────────────────────────────────────────────────────────
ADMIN_PANEL_TMPL = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Panel - Shop TMinh</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif;}
:root{--acc:#4f46e5;--acc2:#7c3aed;--bg:#f1f5f9;--white:#fff;--text:#1f2937;--muted:#6b7280;--border:#e5e7eb;--green:#10b981;--red:#ef4444;--orange:#f59e0b;}
body{background:var(--bg);color:var(--text);min-height:100vh;}
.topbar{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#fff;padding:.9rem 1.25rem;display:flex;align-items:center;justify-content:space-between;gap:.5rem;flex-wrap:wrap;position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(79,70,229,.3);}
.topbar h1{font-size:1.05rem;font-weight:800;}
.topbar-btns{display:flex;gap:.5rem;}
.tbtn{padding:.4rem .85rem;border-radius:8px;font-size:.78rem;font-weight:600;cursor:pointer;border:none;transition:.2s;}
.tbtn-out{background:rgba(255,255,255,.2);color:#fff;}
.tbtn-home{background:#fff;color:var(--acc);}
.layout{display:flex;min-height:calc(100vh - 52px);}
.sidebar{width:200px;background:#fff;border-right:1px solid var(--border);flex-shrink:0;padding:.75rem 0;}
.sidebar-item{display:flex;align-items:center;gap:.6rem;padding:.65rem 1rem;cursor:pointer;font-size:.82rem;font-weight:600;color:var(--muted);border-left:3px solid transparent;transition:.15s;}
.sidebar-item:hover{background:#f8fafc;color:var(--text);}
.sidebar-item.active{background:#eef2ff;color:var(--acc);border-left-color:var(--acc);}
.sidebar-item .ico{font-size:.9rem;}
.main{flex:1;padding:1.1rem;overflow-x:hidden;}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:.6rem;margin-bottom:1.25rem;}
.stat{background:#fff;border-radius:12px;padding:.8rem;border:1px solid var(--border);box-shadow:0 2px 6px rgba(0,0,0,.04);text-align:center;}
.stat-val{font-size:1.3rem;font-weight:800;color:var(--acc);}
.stat-lbl{font-size:.65rem;color:var(--muted);margin-top:.1rem;font-weight:500;}
.panel{display:none;}
.panel.active{display:block;}
.card{background:#fff;border-radius:12px;padding:1rem;border:1px solid var(--border);box-shadow:0 2px 6px rgba(0,0,0,.04);margin-bottom:.9rem;}
.card h3{font-size:.88rem;font-weight:700;margin-bottom:.8rem;color:var(--text);display:flex;align-items:center;gap:.4rem;}
.section-divider{font-size:.7rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin:1rem 0 .5rem;padding:0 .2rem;border-left:3px solid var(--acc);padding-left:.6rem;}
label{display:block;font-size:.72rem;font-weight:700;color:var(--muted);margin-bottom:.25rem;text-transform:uppercase;}
input,select,textarea{width:100%;padding:.55rem .8rem;border:1.5px solid var(--border);border-radius:8px;font-size:.84rem;background:#fff;outline:none;margin-bottom:.6rem;transition:.15s;}
input:focus,select:focus,textarea:focus{border-color:var(--acc);box-shadow:0 0 0 2px rgba(79,70,229,.1);}
textarea{min-height:65px;resize:vertical;font-family:monospace;}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:.48rem 1rem;border-radius:8px;font-weight:600;font-size:.8rem;cursor:pointer;border:none;transition:.15s;gap:.3rem;}
.btn:active{transform:scale(.96);}
.btn-p{background:linear-gradient(135deg,var(--acc),var(--acc2));color:#fff;}
.btn-g{background:var(--green);color:#fff;}
.btn-r{background:var(--red);color:#fff;}
.btn-o{background:var(--orange);color:#fff;}
.btn-sm{padding:.28rem .65rem;font-size:.73rem;border-radius:6px;}
.btn-full{width:100%;}
.msg{padding:.45rem .7rem;border-radius:7px;font-size:.78rem;margin-top:.35rem;display:none;}
.msg.ok{background:#d1fae5;color:#065f46;}
.msg.err{background:#fee2e2;color:#991b1b;}
table{width:100%;border-collapse:collapse;font-size:.77rem;}
th{background:#f8fafc;padding:.45rem .6rem;text-align:left;font-weight:600;color:var(--muted);font-size:.68rem;text-transform:uppercase;}
td{padding:.5rem .6rem;border-bottom:1px solid var(--border);vertical-align:top;}
tr:last-child td{border:none;}
tr:hover td{background:#fafafa;}
.badge{display:inline-block;padding:.12rem .45rem;border-radius:16px;font-size:.65rem;font-weight:700;}
.badge-g{background:#d1fae5;color:#065f46;}
.badge-r{background:#fee2e2;color:#991b1b;}
.badge-o{background:#fef3c7;color:#92400e;}
.log-row{display:flex;gap:.5rem;padding:.45rem 0;border-bottom:1px solid var(--border);font-size:.77rem;}
.log-time{color:var(--muted);white-space:nowrap;flex-shrink:0;font-size:.7rem;}
.log-event{font-weight:600;color:var(--acc);flex-shrink:0;min-width:100px;}
.log-detail{color:var(--text);flex:1;word-break:break-word;}
.topup-card{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:.85rem;margin-bottom:.65rem;}
.fb-card{background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:.85rem;margin-bottom:.65rem;display:flex;gap:.75rem;align-items:flex-start;}
.fb-media{width:75px;height:55px;object-fit:cover;border-radius:7px;flex-shrink:0;background:#e5e7eb;}
.order-detail{background:#f8fafc;border-radius:7px;padding:.45rem .6rem;margin-top:.3rem;font-size:.7rem;font-family:monospace;border:1px solid var(--border);}
.admin-sub-card{background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:1px solid #6ee7b7;border-radius:10px;padding:.85rem;margin-bottom:.65rem;display:flex;align-items:center;justify-content:space-between;gap:.5rem;flex-wrap:wrap;}
@media(max-width:640px){.sidebar{display:none;}.layout{flex-direction:column;}}
.mob-menu-btn{display:none;background:rgba(255,255,255,.2);border:none;color:#fff;border-radius:8px;padding:.4rem .7rem;cursor:pointer;font-size:1.1rem;line-height:1;}
@media(max-width:640px){.mob-menu-btn{display:inline-flex;align-items:center;justify-content:center;}}
.mob-menu-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:200;}
.mob-menu-overlay.open{display:block;}
.mob-menu-drawer{position:fixed;top:0;left:0;width:240px;height:100%;background:#fff;z-index:201;padding:.75rem 0;transform:translateX(-100%);transition:transform .25s ease;box-shadow:4px 0 20px rgba(0,0,0,.15);}
.mob-menu-drawer.open{transform:translateX(0);}
.mob-menu-item{display:flex;align-items:center;gap:.6rem;padding:.7rem 1.1rem;cursor:pointer;font-size:.84rem;font-weight:600;color:var(--muted);border-left:3px solid transparent;transition:.15s;}
.mob-menu-item:hover,.mob-menu-item.active{background:#eef2ff;color:var(--acc);border-left-color:var(--acc);}
.mob-tabs{display:none;background:#fff;border-bottom:1px solid var(--border);overflow-x:auto;white-space:nowrap;padding:.4rem .7rem;gap:.3rem;}
@media(max-width:640px){.mob-tabs{display:flex;}}
</style>
</head>
<body>
<div class="topbar">
  <div style="display:flex;align-items:center;gap:.6rem;">
    <button class="mob-menu-btn" onclick="openMobMenu()">☰</button>
    <h1>⚙️ Admin Panel</h1>
  </div>
  <div class="topbar-btns">
    <a href="/"><button class="tbtn tbtn-home">🏠 Web</button></a>
    <a href="/admin/logout"><button class="tbtn tbtn-out">Đăng Xuất</button></a>
  </div>
</div>
<div class="mob-menu-overlay" id="mob-overlay" onclick="closeMobMenu()"></div>
<div class="mob-menu-drawer" id="mob-drawer">
  <div style="padding:.7rem 1rem;font-weight:800;font-size:.95rem;color:var(--acc);border-bottom:1px solid var(--border);margin-bottom:.3rem;">Shop TMinh Admin</div>
  {% if is_main %}
  <div class="mob-menu-item" onclick="aTab('acc',this);closeMobMenu()">📦 Acc Clone</div>
  <div class="mob-menu-item" onclick="aTab('customacc',this);closeMobMenu()">🎮 Acc Tự Chọn</div>
  <div class="mob-menu-item" onclick="aTab('fffiles',this);closeMobMenu()">📁 File FF</div>
  <div class="mob-menu-item" onclick="aTab('orders',this);closeMobMenu()">🛒 Đơn Mua</div>
  <div class="mob-menu-item" onclick="aTab('carry',this);closeMobMenu()">🏆 Kéo Thuê</div>
  <div class="mob-menu-item" onclick="aTab('feedback',this);closeMobMenu()">🏅 Feedback</div>
  <div class="mob-menu-item" onclick="aTab('balance',this);closeMobMenu()">💰 Số Dư</div>
  <div class="mob-menu-item" onclick="aTab('topup',this);closeMobMenu()">💳 Nạp Tiền</div>
  <div class="mob-menu-item" onclick="aTab('notice',this);closeMobMenu()">📢 Thông Báo</div>
  <div class="mob-menu-item" onclick="aTab('admins',this);closeMobMenu()">👑 Admin Phụ</div>
  <div class="mob-menu-item" onclick="aTab('coupons',this);closeMobMenu()">🎟️ Mã Giảm Giá</div>
  <div class="mob-menu-item" onclick="aTab('users',this);closeMobMenu()">👥 Users</div>
  <div class="mob-menu-item" onclick="aTab('msg',this);closeMobMenu()">📨 Nhắn Tin</div>
  <div class="mob-menu-item" onclick="aTab('revenue',this);closeMobMenu()">📈 Doanh Thu</div>
  <div class="mob-menu-item" onclick="aTab('logs',this);closeMobMenu()">📋 Nhật Ký</div>
  {% else %}
  <div class="mob-menu-item" onclick="aTab('carry',this);closeMobMenu()">🏆 Kéo Thuê</div>
  <div class="mob-menu-item" onclick="aTab('topup',this);closeMobMenu()">💳 Nạp Tiền</div>
  <div class="mob-menu-item" onclick="aTab('users',this);closeMobMenu()">👥 Users</div>
  {% endif %}
</div>
<div class="layout">
  <div class="sidebar" id="sidebar">
    {% if is_main %}
    <div class="sidebar-item active" onclick="aTab('acc',this)" id="si-acc"><span class="ico">📦</span> Acc Clone</div>
    <div class="sidebar-item" onclick="aTab('customacc',this)"><span class="ico">🎮</span> Acc Tự Chọn</div>
    <div class="sidebar-item" onclick="aTab('fffiles',this)"><span class="ico">📁</span> File FF</div>
    <div class="sidebar-item" onclick="aTab('orders',this)"><span class="ico">🛒</span> Đơn Mua</div>
    <div class="sidebar-item" onclick="aTab('carry',this)"><span class="ico">🏆</span> Kéo Thuê</div>
    <div class="sidebar-item" onclick="aTab('feedback',this)"><span class="ico">🏅</span> Feedback</div>
    <div class="sidebar-item" onclick="aTab('users',this)"><span class="ico">👥</span> Users</div>
    <div class="sidebar-item" onclick="aTab('balance',this)"><span class="ico">💰</span> Số Dư</div>
    <div class="sidebar-item" onclick="aTab('topup',this)"><span class="ico">💳</span> Nạp Tiền</div>
    <div class="sidebar-item" onclick="aTab('notice',this)"><span class="ico">📢</span> Thông Báo</div>
    <div class="sidebar-item" onclick="aTab('admins',this)"><span class="ico">👑</span> Admin Phụ</div>
    <div class="sidebar-item" onclick="aTab('coupons',this)"><span class="ico">🎟️</span> Mã Giảm Giá</div>
    <div class="sidebar-item" onclick="aTab('msg',this)"><span class="ico">✉️</span> Gửi TB</div>
    <div class="sidebar-item" onclick="aTab('logs',this)"><span class="ico">📋</span> Logs</div>
    {% else %}
    <div class="sidebar-item active" onclick="aTab('users',this)"><span class="ico">👥</span> Quản Lý Users</div>
    <div class="sidebar-item" onclick="aTab('logs',this)"><span class="ico">📋</span> Logs</div>
    {% endif %}
  </div>
  <div class="main">
    <div class="stats">
      <div class="stat"><div class="stat-val">{{ stats.users }}</div><div class="stat-lbl">👥 Users</div></div>
      <div class="stat"><div class="stat-val">{{ stats.orders }}</div><div class="stat-lbl">🛒 Đơn hàng</div></div>
      <div class="stat"><div class="stat-val">{{ stats.carry_orders }}</div><div class="stat-lbl">🏆 Kéo thuê</div></div>
      <div class="stat"><div class="stat-val">{{ db.get('ff_files',[])|length }}</div><div class="stat-lbl">📁 File FF</div></div>
      <div class="stat"><div class="stat-val">{{ "{:,.0f}".format(stats.revenue) }}đ</div><div class="stat-lbl">💰 Doanh thu</div></div>
      <div class="stat"><div class="stat-val">{{ stats.acc_kim }}</div><div class="stat-lbl">💜 Kim Cương</div></div>
      <div class="stat"><div class="stat-val">{{ stats.acc_bach }}</div><div class="stat-lbl">🔵 Bạch Kim</div></div>
      <div class="stat"><div class="stat-val">{{ stats.acc_lv5 }}</div><div class="stat-lbl">🟢 Lv5</div></div>
      {% if stats.pending_topup > 0 %}
      <div class="stat" style="border-color:#fbbf24;background:#fffbeb;"><div class="stat-val" style="color:var(--orange);">{{ stats.pending_topup }}</div><div class="stat-lbl">💰 Nạp chờ</div></div>
      {% endif %}
    </div>

    <!-- TABS MOBILE -->
    <div style="display:flex;gap:.2rem;overflow-x:auto;padding:.2rem;margin-bottom:.9rem;background:#f8fafc;border-radius:10px;-ms-overflow-style:none;scrollbar-width:none;">
      {% if is_main %}
      <div class="btn btn-sm btn-p" onclick="aTab('acc',null)" style="white-space:nowrap;">📦 Acc</div>
      <div class="btn btn-sm btn-o" onclick="aTab('customacc',null)" style="white-space:nowrap;">🎮 TC</div>
      <div class="btn btn-sm" style="background:#10b981;color:#fff;white-space:nowrap;" onclick="aTab('fffiles',null)">📁 File</div>
      <div class="btn btn-sm btn-p" onclick="aTab('users',null)" style="white-space:nowrap;">👥 Users</div>
      <div class="btn btn-sm btn-o" onclick="aTab('orders',null)" style="white-space:nowrap;">🛒 Đơn</div>
      <div class="btn btn-sm btn-o" onclick="aTab('carry',null)" style="white-space:nowrap;">🏆 Kéo</div>
      <div class="btn btn-sm btn-p" onclick="aTab('balance',null)" style="white-space:nowrap;">💰 Tiền</div>
      <div class="btn btn-sm btn-p" onclick="aTab('topup',null)" style="white-space:nowrap;">💳 Nạp</div>
      <div class="btn btn-sm btn-o" onclick="aTab('notice',null)" style="white-space:nowrap;">📢 TB</div>
      <div class="btn btn-sm btn-g" onclick="aTab('admins',null)" style="white-space:nowrap;">👑 Admin</div>
      <div class="btn btn-sm btn-g" onclick="aTab('coupons',null)" style="white-space:nowrap;">🎟️ Mã</div>
      <div class="btn btn-sm btn-p" onclick="aTab('msg',null)" style="white-space:nowrap;">✉️ Gửi</div>
      <div class="btn btn-sm btn-o" onclick="aTab('logs',null)" style="white-space:nowrap;">📋 Log</div>
      <div class="btn btn-sm btn-p" onclick="aTab('feedback',null)" style="white-space:nowrap;">🏅 FB</div>
      {% else %}
      <div class="btn btn-sm btn-p" onclick="aTab('users',null)" style="white-space:nowrap;">👥 Quản Lý Users</div>
      <div class="btn btn-sm btn-o" onclick="aTab('logs',null)" style="white-space:nowrap;">📋 Logs</div>
      {% endif %}
    </div>

    {% if is_main %}
    <!-- ACC TAB -->
    <div class="panel active" id="pn-acc">
      <div class="card">
        <h3>📦 Thêm Acc Clone Mới</h3>
        <label>Loại Acc</label>
        <select id="acc-cat">
          <option value="kim_cuong">💜 Kim Cương (25.000đ)</option>
          <option value="bach_kim">🔵 Bạch Kim (20.000đ)</option>
          <option value="lv5">🟢 Lv5 Google (2.500đ)</option>
        </select>
        <label>Thêm nhiều acc (mỗi dòng: user:pass:platform:mô tả)</label>
        <textarea id="acc-bulk" placeholder="user1:pass1:Facebook:mô tả&#10;user2:pass2:Google:mô tả&#10;..."></textarea>
        <label>Hoặc thêm 1 acc:</label>
        <input id="acc-user" placeholder="Username / Email">
        <input id="acc-pass" placeholder="Mật khẩu">
        <input id="acc-platform" placeholder="Platform (Facebook/Google/...)" value="Facebook">
        <input id="acc-desc" placeholder="Mô tả (tùy chọn)">
        <button class="btn btn-p btn-full" onclick="addAcc()">➕ Thêm Acc</button>
        <div class="msg" id="acc-msg"></div>
      </div>
      <div class="card">
        <h3>📋 Danh Sách Acc Clone</h3>
        {% for cat in ['kim_cuong', 'bach_kim', 'lv5'] %}
        <div style="margin-bottom:1rem;">
          <div class="section-divider">{{ '💜 Kim Cương' if cat=='kim_cuong' else '🔵 Bạch Kim' if cat=='bach_kim' else '🟢 Lv5 Google' }} — <span style="color:var(--green);">{{ db.accounts.get(cat,[])|selectattr('sold','equalto',False)|list|length }} còn</span> / {{ db.accounts.get(cat,[])|length }} tổng</div>
          {% if db.accounts.get(cat) %}
          <table>
            <tr><th>#</th><th>Username</th><th>Pass</th><th>Platform</th><th>Thêm lúc</th><th>Trạng thái</th><th>Bán cho</th><th>Xóa</th></tr>
            {% for a in db.accounts[cat][-50:]|reverse %}
            <tr>
              <td style="color:var(--muted);font-size:.68rem;">{{ loop.index }}</td>
              <td style="font-family:monospace;font-weight:600;">{{ a.user }}</td>
              <td style="font-family:monospace;">{{ a.pass }}</td>
              <td style="font-size:.72rem;">{{ a.get('platform','') }}</td>
              <td style="font-size:.68rem;color:var(--muted);">{{ a.get('added','') }}</td>
              <td>{% if a.get('sold') %}<span class="badge badge-r">Đã bán</span>{% else %}<span class="badge badge-g">Còn</span>{% endif %}</td>
              <td style="font-size:.7rem;color:var(--acc);">{{ a.get('sold_to_name','') }}</td>
              <td><button class="btn btn-r btn-sm" onclick="delAcc('{{ cat }}','{{ a.id }}')">Xóa</button></td>
            </tr>
            {% endfor %}
          </table>
          {% else %}<div style="color:var(--muted);font-size:.8rem;padding:.5rem;">Chưa có acc</div>{% endif %}
        </div>
        {% endfor %}
      </div>
    </div>

    <!-- CUSTOM ACC TAB -->
    <div class="panel" id="pn-customacc">
      <div class="card">
        <h3>🎮 Thêm Acc Tự Chọn</h3>
        <label>Ảnh (upload hoặc URL)</label>
        <input type="file" id="ca-file" accept="image/*" style="margin-bottom:.6rem;">
        <input id="ca-img-url" placeholder="Hoặc nhập URL ảnh (không bắt buộc)">
        <label>Tên đăng nhập acc</label>
        <input id="ca-user" placeholder="Username / Email">
        <label>Mật khẩu acc</label>
        <input id="ca-pass" placeholder="Mật khẩu">
        <label>Nền tảng</label>
        <input id="ca-platform" placeholder="Facebook / Google / Garena..." value="Facebook">
        <label>Mô tả (rank, skin, thông tin nổi bật...)</label>
        <textarea id="ca-desc" placeholder="Ví dụ: Rank Kim Cương I, có skin AK đỏ, Lv15..."></textarea>
        <label>Giá bán (đ)</label>
        <input type="number" id="ca-price" placeholder="Ví dụ: 150000" min="0">
        <button class="btn btn-p btn-full" onclick="addCustomAcc()">➕ Thêm Acc Tự Chọn</button>
        <div class="msg" id="ca-msg"></div>
      </div>
      <div class="card">
        <h3>📋 Danh Sách Acc Tự Chọn ({{ db.get('custom_accs',[])|length }} acc)</h3>
        {% if db.get('custom_accs') %}
          {% for a in db.custom_accs %}
          <div class="fb-card" style="align-items:flex-start;flex-wrap:wrap;">
            {% if a.image_url %}<img src="{{ a.image_url }}" class="fb-media" alt="Acc" onerror="this.style.background='#e5e7eb'">{% endif %}
            <div style="flex:1;min-width:0;">
              <div style="font-size:.78rem;font-weight:700;color:var(--acc);margin-bottom:.2rem;">{{ a.platform or 'N/A' }}</div>
              {% if a.acc_user %}<div style="font-size:.74rem;font-family:monospace;">👤 {{ a.acc_user }}</div>{% endif %}
              {% if a.desc %}<div style="font-size:.76rem;color:var(--text);margin-top:.2rem;line-height:1.4;">{{ a.desc }}</div>{% endif %}
              <div style="font-size:.78rem;font-weight:700;color:var(--green);margin-top:.2rem;">{{ "{:,}".format(a.price) }}đ</div>
            </div>
            <button class="btn btn-r btn-sm" style="flex-shrink:0;" onclick="delCustomAcc('{{ a.id }}')">Xóa</button>
          </div>
          {% endfor %}
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có acc tự chọn</div>{% endif %}
      </div>
    </div>

    <!-- FILE FF TAB -->
    <div class="panel" id="pn-fffiles">
      <div class="card">
        <h3>📁 Thêm File Free Fire</h3>
        <label>Tên file (bắt buộc)</label>
        <input id="ff-name" placeholder="VD: Config aim FF, Tool headshot...">
        <label>Ảnh thumbnail (upload hoặc URL)</label>
        <input type="file" id="ff-img-file" accept="image/*" style="margin-bottom:.6rem;">
        <input id="ff-img-url" placeholder="Hoặc nhập URL ảnh">
        <label>File để tải (zip, rar, apk, pdf...)</label>
        <input type="file" id="ff-dl-file" accept=".zip,.rar,.apk,.pdf,.txt,.json" style="margin-bottom:.6rem;">
        <label>Video hướng dẫn cài (upload hoặc URL YouTube/TikTok)</label>
        <input type="file" id="ff-vid-file" accept="video/*" style="margin-bottom:.6rem;">
        <input id="ff-vid-url" placeholder="Hoặc URL video YouTube/TikTok">
        <label>Mô tả (tùy chọn)</label>
        <textarea id="ff-desc" placeholder="Mô tả nội dung file, hướng dẫn sử dụng..."></textarea>
        <label>Giá bán (đ, để 0 = Free)</label>
        <input type="number" id="ff-price" placeholder="0 = Free" min="0" value="0">
        <button class="btn btn-full" style="background:linear-gradient(135deg,#10b981,#059669);color:#fff;" onclick="addFfFile()">📁 Thêm File FF</button>
        <div class="msg" id="ff-msg"></div>
      </div>
      <div class="card">
        <h3>📋 Danh Sách File FF ({{ db.get('ff_files',[])|length }} file)</h3>
        {% if db.get('ff_files') %}
          {% for f in db.ff_files %}
          <div class="fb-card" style="flex-wrap:wrap;">
            {% if f.image_url %}<img src="{{ f.image_url }}" class="fb-media" onerror="this.style.background='#e5e7eb'">{% endif %}
            <div style="flex:1;min-width:120px;">
              <div style="font-weight:700;font-size:.82rem;color:var(--text);">📁 {{ f.name }}</div>
              {% if f.desc %}<div style="font-size:.74rem;color:var(--muted);margin-top:.15rem;line-height:1.4;">{{ f.desc[:80] }}</div>{% endif %}
              {% if f.file_url %}<div style="font-size:.72rem;color:var(--green);margin-top:.15rem;">✅ Có file tải</div>{% endif %}
              {% if f.video_url %}<div style="font-size:.72rem;color:var(--acc);margin-top:.1rem;">🎬 Có video HD</div>{% endif %}
              <div style="font-size:.76rem;font-weight:700;color:var(--green);margin-top:.2rem;">{{ "Free" if f.price==0 else "{:,}đ".format(f.price) }}</div>
            </div>
            <button class="btn btn-r btn-sm" onclick="delFfFile('{{ f.id }}')">Xóa</button>
          </div>
          {% endfor %}
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có file nào</div>{% endif %}
      </div>
    </div>

    <!-- ORDERS TAB -->
    <div class="panel" id="pn-orders">
      <div class="card">
        <h3>🛒 Lịch Sử Mua Acc ({{ db.orders|length }} đơn)</h3>
        {% if db.orders %}
        <table>
          <tr><th>⏰ Thời gian</th><th>👤 User</th><th>📦 Loại</th><th>SL</th><th>💰 Tiền</th><th>Chi tiết Acc</th></tr>
          {% for o in db.orders|reverse %}
          <tr>
            <td style="font-size:.7rem;color:var(--muted);white-space:nowrap;">{{ o.time }}</td>
            <td><b style="color:var(--acc);">{{ o.username }}</b></td>
            <td style="font-size:.76rem;">{{ o.get('cat_name', o.cat) }}</td>
            <td style="text-align:center;font-weight:700;">{{ o.qty }}</td>
            <td style="color:var(--green);font-weight:700;">{{ "{:,}".format(o.total) }}đ</td>
            <td>{% for a in o.get('accs',[]) %}<div class="order-detail"><b>{{ a.user }}</b> : {{ a.pass }}{% if a.get('platform') %} ({{ a.platform }}){% endif %}</div>{% endfor %}</td>
          </tr>
          {% else %}<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:1.5rem;">Chưa có đơn hàng</td></tr>
          {% endfor %}
        </table>
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có đơn hàng</div>{% endif %}
      </div>
    </div>

    <!-- CARRY TAB -->
    <div class="panel" id="pn-carry">
      <div class="card">
        <h3>🏆 Lịch Sử Đơn Kéo Thuê ({{ db.get('carry_orders',[])|length }} đơn)</h3>
        {% if db.get('carry_orders') %}
        <table>
          <tr><th>⏰ Thời gian</th><th>👤 User</th><th>⭐ Sao</th><th>🎮 Rank</th><th>Đơn giá</th><th>📝 Ghi chú</th><th>💰 Tổng</th><th>Trạng thái</th><th>Hành động</th></tr>
          {% for o in db.get('carry_orders',[])|reverse %}
          <tr>
            <td style="font-size:.7rem;color:var(--muted);white-space:nowrap;">{{ o.time }}</td>
            <td><b style="color:var(--acc);">{{ o.username }}</b></td>
            <td style="font-weight:700;">⭐ {{ o.stars }}</td>
            <td style="font-weight:600;">{{ o.get('rank','') }}</td>
            <td style="font-size:.72rem;color:var(--muted);">{{ "{:,}".format(o.get('price_per_star',1000)) }}đ/⭐</td>
            <td style="font-size:.72rem;max-width:100px;word-break:break-word;">{{ o.get('note','') or '—' }}</td>
            <td style="color:var(--green);font-weight:700;">{{ "{:,}".format(o.total) }}đ</td>
            <td>{% if o.get('status')=='done' %}<span class="badge badge-g">✅ Done</span>{% else %}<span class="badge badge-o">⏳ Chờ</span>{% endif %}</td>
            <td>{% if o.get('status')!='done' %}<button class="btn btn-g btn-sm" onclick="approveCarry('{{ o.id }}','{{ o.username }}')">✅ Done</button>{% endif %}</td>
          </tr>
          {% else %}<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:1.5rem;">Chưa có đơn</td></tr>
          {% endfor %}
        </table>
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có đơn kéo thuê</div>{% endif %}
      </div>
    </div>

    <!-- FEEDBACK TAB -->
    <div class="panel" id="pn-feedback">
      <div class="card">
        <h3>🏅 Thêm Feedback Kéo Rank</h3>
        <label>Ảnh hoặc Video</label>
        <input type="file" id="fb-file" accept="image/*,video/mp4,video/webm" style="padding:.4rem;">
        <label>Hoặc nhập URL ảnh/video</label>
        <input id="fb-url" placeholder="https://...">
        <label>Mô tả</label>
        <textarea id="fb-desc" placeholder="Ví dụ: Khách kéo từ Kim Cương lên Cao Thủ trong 2 ngày..."></textarea>
        <label>Tên khách hàng (tùy chọn)</label>
        <input id="fb-customer" placeholder="Tên khách (để trống nếu ẩn danh)">
        <button class="btn btn-p btn-full" onclick="addFeedback()">📤 Đăng Feedback</button>
        <div class="msg" id="fb-msg"></div>
      </div>
      <div class="card">
        <h3>📋 Danh Sách Feedback ({{ db.get('feedback_posts',[])|length }} bài)</h3>
        {% if db.get('feedback_posts') %}
          {% for p in db.feedback_posts %}
          <div class="fb-card">
            {% if p.media_url %}{% if p.media_type == 'video' %}<video src="{{ p.media_url }}" class="fb-media" muted></video>{% else %}<img src="{{ p.media_url }}" class="fb-media" onerror="this.style.background='#e5e7eb'">{% endif %}{% endif %}
            <div style="flex:1;min-width:0;">
              <div style="font-size:.78rem;color:var(--text);line-height:1.4;">{{ p.desc or '(Không có mô tả)' }}</div>
              {% if p.customer %}<div style="font-size:.72rem;color:var(--acc);font-weight:600;margin-top:.15rem;">👤 {{ p.customer }}</div>{% endif %}
              <div style="font-size:.68rem;color:var(--muted);margin-top:.15rem;">⏰ {{ p.time }}</div>
            </div>
            <button class="btn btn-r btn-sm" onclick="delFeedback('{{ p.id }}')">Xóa</button>
          </div>
          {% endfor %}
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có feedback</div>{% endif %}
      </div>
    </div>

    <!-- BALANCE TAB -->
    <div class="panel" id="pn-balance">
      <div class="card">
        <h3>💰 Quản Lý Số Dư User</h3>
        <label>Tên user</label>
        <input id="bal-user" placeholder="Tên đăng nhập user">
        <label>Số tiền (đ)</label>
        <input type="number" id="bal-amount" placeholder="Số tiền" min="0">
        <div style="display:flex;gap:.6rem;">
          <button class="btn btn-g" style="flex:1;" onclick="doBalance('add')">➕ Cộng Tiền</button>
          <button class="btn btn-r" style="flex:1;" onclick="doBalance('sub')">➖ Trừ Tiền</button>
        </div>
        <div class="msg" id="bal-msg"></div>
      </div>
    </div>

    <!-- TOPUP TAB -->
    <div class="panel" id="pn-topup">
      <div class="card">
        <h3>💳 Yêu Cầu Nạp Tiền Chờ Duyệt</h3>
        <div id="topup-list">
          {% set pending = [] %}
          {% for k, r in db.get('topup_requests', {}).items() %}{% if r.status == 'pending' %}{% set _ = pending.append(r) %}{% endif %}{% endfor %}
          {% if pending %}
            {% for r in pending %}
            <div class="topup-card">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:.5rem;flex-wrap:wrap;">
                <div>
                  <div style="font-weight:700;">👤 {{ r.username }}</div>
                  <div style="font-size:.8rem;color:var(--muted);">💵 {{ "{:,}".format(r.amount) }}đ</div>
                  <div style="font-size:.74rem;color:var(--muted);">🏦 {{ r.get('bank_name','ZaloPay') }} | 👤 {{ r.get('bank_holder','Phạm Tuấn Minh') }}</div>
                  <div style="font-size:.74rem;color:var(--muted);">📝 Mã: <code style="background:#f3f4f6;padding:.1rem .3rem;border-radius:4px;">{{ r.content }}</code></div>
                  <div style="font-size:.72rem;color:var(--muted);">⏰ {{ r.created }}</div>
                </div>
                <div style="display:flex;gap:.4rem;">
                  <button class="btn btn-g btn-sm" onclick="approveTopup('{{ r.content }}',{{ r.amount }})">✅ Duyệt</button>
                  <button class="btn btn-r btn-sm" onclick="rejectTopup('{{ r.content }}')">❌ Từ chối</button>
                </div>
              </div>
            </div>
            {% endfor %}
          {% else %}
            <div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">✅ Không có yêu cầu chờ</div>
          {% endif %}
        </div>
        <div style="border-top:1px solid var(--border);padding-top:.9rem;margin-top:.9rem;">
          <div class="section-divider">Duyệt thủ công theo mã</div>
          <label>Mã nội dung chuyển khoản</label>
          <input id="tp-content" placeholder="NAPTIENABCD1234">
          <label>Số tiền (đ)</label>
          <input type="number" id="tp-amount" placeholder="Số tiền">
          <button class="btn btn-p btn-full" onclick="manualApprove()">✅ Duyệt Nạp Tiền</button>
          <div class="msg" id="tp-msg"></div>
        </div>
      </div>
    </div>

    <!-- NOTICE TAB -->
    <div class="panel" id="pn-notice">
      <div class="card">
        <h3>📢 Thông Báo Nổi</h3>
        <label>Nội dung thông báo (để trống = ẩn)</label>
        <textarea id="notice-txt" placeholder="Nhập thông báo hiển thị cho users...">{{ db.admin_notice }}</textarea>
        <label>Mô tả nút bấm (để trống = ẩn nút)</label>
        <input id="notice-btn-desc" placeholder="Ví dụ: Liên hệ ngay..." value="{{ db.get('notice_btn_desc','') }}">
        <label>Link Zalo (để trống = ẩn)</label>
        <input id="notice-zalo-link" placeholder="https://zalo.me/..." value="{{ db.get('notice_zalo_link','') }}">
        <label>Link Telegram (tùy chọn)</label>
        <input id="notice-tg-link" placeholder="https://t.me/..." value="{{ db.get('notice_tg_link','') }}">
        <div style="display:flex;gap:.6rem;">
          <button class="btn btn-p" style="flex:1;" onclick="setNotice()">💾 Lưu</button>
          <button class="btn btn-r" onclick="clearNotice()">🗑️ Xóa</button>
        </div>
        <div class="msg" id="notice-msg"></div>
      </div>
    </div>

    <!-- ADMIN PHU TAB -->
    <div class="panel" id="pn-admins">
      <div class="card">
        <h3>👑 Thêm Admin Phụ (tối đa 4)</h3>
        <label>Tên hiển thị (bắt buộc)</label>
        <input id="sa-name" placeholder="VD: Nguyễn Văn A">
        <label>Tên tài khoản đăng nhập (bắt buộc)</label>
        <input id="sa-username" placeholder="VD: admin1">
        <label>Mật khẩu (bắt buộc)</label>
        <input id="sa-password" placeholder="Mật khẩu đăng nhập admin phụ">
        <label>Chức vụ</label>
        <input id="sa-role" placeholder="VD: Quản Trị Phụ, Admin 1..." value="Quản Trị Phụ">
        <div class="section-divider">Thông tin liên hệ (tùy chọn)</div>
        <label>TikTok URL</label>
        <input id="sa-tiktok" placeholder="https://www.tiktok.com/@...">
        <label>Facebook URL</label>
        <input id="sa-facebook" placeholder="https://www.facebook.com/...">
        <label>Zalo (số điện thoại)</label>
        <input id="sa-zalo" placeholder="0901234567">
        <div class="section-divider">Ảnh đại diện (tùy chọn)</div>
        <label>Upload ảnh avatar admin phụ</label>
        <input type="file" id="sa-avatar-file" accept="image/*" style="margin-bottom:.6rem;">
        <small style="font-size:.7rem;color:var(--muted);display:block;margin-bottom:.6rem;">Nếu không upload, sẽ dùng ảnh mặc định. Ảnh sẽ hiển thị trên trang web và trang kéo thuê.</small>
        <button class="btn btn-g btn-full" onclick="addSubAdmin()">👑 Thêm Admin Phụ</button>
        <div class="msg" id="sa-msg"></div>
      </div>
      <div class="card">
        <h3>📋 Danh Sách Admin Phụ ({{ db.get('sub_admins',[])|length }}/4)</h3>
        {% if db.get('sub_admins') %}
          {% for sa in db.sub_admins %}
          <div class="admin-sub-card">
            <div style="display:flex;align-items:center;gap:.7rem;flex:1;min-width:0;">
              <img src="{{ sa.get('avatar','/anh_admin.jpg') }}" style="width:44px;height:44px;border-radius:50%;object-fit:cover;border:2px solid #10b981;flex-shrink:0;" onerror="this.style.display='none'" alt="{{ sa.name }}">
              <div>
                <div style="font-weight:700;font-size:.9rem;color:#065f46;">{{ sa.name }}</div>
                <div style="font-size:.74rem;color:var(--muted);">👤 {{ sa.username }} | {{ sa.role }}</div>
                {% if sa.tiktok %}<div style="font-size:.7rem;color:var(--muted);">🎵 {{ sa.tiktok[:40] }}</div>{% endif %}
                {% if sa.zalo %}<div style="font-size:.7rem;color:var(--muted);">🔵 Zalo: {{ sa.zalo }}</div>{% endif %}
                {% if sa.facebook %}<div style="font-size:.7rem;color:var(--muted);">📘 FB: {{ sa.facebook[:40] }}</div>{% endif %}
                <div style="font-size:.68rem;color:var(--muted);">Thêm lúc: {{ sa.added }}</div>
              </div>
            </div>
            <button class="btn btn-r btn-sm" onclick="delSubAdmin('{{ sa.id }}')">Xóa</button>
          </div>
          {% endfor %}
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có admin phụ nào</div>{% endif %}
      </div>
    </div>

    <!-- COUPONS TAB -->
    <div class="panel" id="pn-coupons">
      <div class="card">
        <h3>🎟️ Tạo Mã Giảm Giá</h3>
        <label>Mã giảm giá (để trống = tạo ngẫu nhiên)</label>
        <input id="cp-code" placeholder="VD: SALE50 (để trống = tự tạo)" style="text-transform:uppercase;" oninput="this.value=this.value.toUpperCase()">
        <label>Phần trăm giảm (1–100%)</label>
        <input type="number" id="cp-pct" placeholder="VD: 20 (nghĩa là giảm 20%)" min="1" max="100" value="10">
        <label>Thời hạn</label>
        <select id="cp-expires-type" onchange="document.getElementById('cp-days-row').style.display=this.value==='days'?'block':'none'">
          <option value="permanent">Vĩnh viễn</option>
          <option value="days">Có thời hạn (số ngày)</option>
        </select>
        <div id="cp-days-row" style="display:none;">
          <label>Số ngày có hiệu lực</label>
          <input type="number" id="cp-days" placeholder="VD: 7" min="1" value="7">
        </div>
        <button class="btn btn-p btn-full" onclick="addCoupon()">🎟️ Tạo Mã</button>
        <div class="msg" id="cp-msg"></div>
      </div>
      <div class="card">
        <h3>📋 Danh Sách Mã Giảm Giá ({{ db.get('discount_codes',{})|length }} mã)</h3>
        {% if db.get('discount_codes') %}
          {% for code, c in db.discount_codes.items() %}
          <div style="background:#f8fafc;border:1px solid var(--border);border-radius:10px;padding:.8rem;margin-bottom:.6rem;display:flex;align-items:center;justify-content:space-between;gap:.5rem;flex-wrap:wrap;">
            <div>
              <div style="font-weight:700;font-size:.9rem;font-family:monospace;color:var(--acc);">{{ code }}</div>
              <div style="font-size:.76rem;color:var(--muted);">Giảm: <b style="color:#10b981;">{{ c.pct }}%</b> | Hạn: <b>{{ "Vĩnh viễn" if c.expires==0 else "Có hạn" }}</b> | Đã dùng: <b>{{ c.get('used_by',[])|length }}</b> lượt</div>
              <div style="font-size:.68rem;color:var(--muted);">Tạo lúc: {{ c.created }}</div>
            </div>
            <button class="btn btn-r btn-sm" onclick="delCoupon('{{ code }}')">Xóa</button>
          </div>
          {% endfor %}
        {% else %}<div style="color:var(--muted);font-size:.83rem;padding:.8rem;text-align:center;">Chưa có mã nào</div>{% endif %}
      </div>
    </div>

    <!-- MSG TAB -->
    <div class="panel" id="pn-msg">
      <div class="card">
        <h3>✉️ Gửi Thông Báo Cho User</h3>
        <label>Tên user</label>
        <input id="msg-user" placeholder="Tên đăng nhập">
        <label>Nội dung thông báo</label>
        <textarea id="msg-txt" placeholder="Nhập nội dung..."></textarea>
        <button class="btn btn-p btn-full" onclick="sendMsg()">✉️ Gửi</button>
        <div class="msg" id="msg-res"></div>
      </div>
    </div>
    {% endif %}

    <!-- USERS TAB (both admin types) -->
    <div class="panel {% if not is_main %}active{% endif %}" id="pn-users">
      <div class="card">
        <h3>👥 Danh Sách Users ({{ db.users|length }})</h3>
        <table>
          <tr><th>Username</th><th>Số dư</th><th>Ngày tạo</th><th>IP</th><th>Trạng thái</th><th>Khóa/Mở</th>{% if is_main %}<th>Xóa</th>{% endif %}</tr>
          {% for uid, u in db.users.items() %}
          <tr>
            <td><b>{{ u.username }}</b>{% if u.get('display') and u.display != u.username %} <span style="color:var(--muted);font-size:.72rem;">({{ u.display }})</span>{% endif %}</td>
            <td style="color:var(--acc);font-weight:700;">{{ "{:,}".format(u.get('balance',0)) }}đ</td>
            <td style="font-size:.72rem;color:var(--muted);">{{ u.get('created','') }}</td>
            <td style="font-size:.72rem;color:var(--muted);">{{ u.get('last_ip','') }}</td>
            <td>{% if u.get('locked') %}<span class="badge badge-r">🔒 Bị khóa</span>{% else %}<span class="badge badge-g">✅ Hoạt động</span>{% endif %}</td>
            <td>
              {% if u.get('locked') %}
              <button class="btn btn-g btn-sm" onclick="lockUser('{{ uid }}','unlock')">🔓 Mở</button>
              {% else %}
              <button class="btn btn-o btn-sm" onclick="lockUser('{{ uid }}','lock')">🔒 Khóa</button>
              {% endif %}
            </td>
            {% if is_main %}<td><button class="btn btn-r btn-sm" onclick="delUser('{{ uid }}')">Xóa</button></td>{% endif %}
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>

    <!-- LOGS TAB -->
    <div class="panel" id="pn-logs">
      <div class="card">
        <h3>📋 Nhật Ký Hoạt Động</h3>
        <div style="display:flex;gap:.5rem;margin-bottom:.9rem;">
          <input id="log-search" placeholder="🔍 Tìm kiếm..." style="flex:1;margin:0;" oninput="filterLogs()">
          <button class="btn btn-p btn-sm" onclick="loadLogs(1)">Tải lại</button>
        </div>
        <div id="log-container">
          {% for l in db.logs[:100] %}
          <div class="log-row">
            <span class="log-time">{{ l.time }}</span>
            <span class="log-event">{{ l.event }}</span>
            <span class="log-detail">{{ l.detail }} {% if l.user != 'system' %}<span style="color:var(--muted);font-size:.7rem;">({{ l.user }})</span>{% endif %}</span>
          </div>
          {% else %}
          <div style="color:var(--muted);font-size:.8rem;padding:.5rem;">Chưa có nhật ký</div>
          {% endfor %}
        </div>
        <div id="log-pages" style="display:flex;gap:.4rem;margin-top:.75rem;flex-wrap:wrap;"></div>
      </div>
    </div>

  </div>
</div>

<script>
function aTab(id,el){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.sidebar-item').forEach(t=>t.classList.remove('active'));
  const pn=document.getElementById('pn-'+id);if(pn)pn.classList.add('active');
  if(el)el.classList.add('active');
  if(id==='logs')loadLogs(1);
}
function openMobMenu(){
  document.getElementById('mob-overlay')?.classList.add('open');
  document.getElementById('mob-drawer')?.classList.add('open');
}
function closeMobMenu(){
  document.getElementById('mob-overlay')?.classList.remove('open');
  document.getElementById('mob-drawer')?.classList.remove('open');
}
function showMsg(id,ok,txt){
  const el=document.getElementById(id);if(!el)return;
  el.textContent=txt;el.className='msg '+(ok?'ok':'err');el.style.display='block';
  setTimeout(()=>el.style.display='none',3500);
}
function addAcc(){
  const fd=new FormData();
  fd.append('cat',document.getElementById('acc-cat').value);
  fd.append('bulk_accs',document.getElementById('acc-bulk').value);
  fd.append('acc_user',document.getElementById('acc-user').value);
  fd.append('acc_pass',document.getElementById('acc-pass').value);
  fd.append('acc_platform',document.getElementById('acc-platform').value||'Facebook');
  fd.append('acc_desc',document.getElementById('acc-desc').value);
  fetch('/admin/api/add-acc',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    showMsg('acc-msg',d.ok,d.ok?'✅ Đã thêm '+d.added+' acc!':'❌ '+(d.msg||'Lỗi!'));
    if(d.ok){document.getElementById('acc-bulk').value='';document.getElementById('acc-user').value='';document.getElementById('acc-pass').value='';}
  }).catch(()=>showMsg('acc-msg',false,'❌ Lỗi kết nối!'));
}
function delAcc(cat,id){
  if(!confirm('Xóa acc này?'))return;
  const fd=new FormData();fd.append('cat',cat);fd.append('id',id);
  fetch('/admin/api/del-acc',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('Đã xóa!');location.reload();}else alert('Lỗi!');
  });
}
function lockUser(uid,action){
  const fd=new FormData();fd.append('uid',uid);fd.append('action',action);
  fetch('/admin/api/lock-user',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert(action==='lock'?'🔒 Đã khóa tài khoản!':'🔓 Đã mở tài khoản!');location.reload();}
    else alert('❌ '+(d.msg||'Lỗi!'));
  });
}
function delUser(uid){
  if(!confirm('Xóa user này?'))return;
  const fd=new FormData();fd.append('uid',uid);
  fetch('/admin/api/del-user',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('Đã xóa!');location.reload();}else alert('Lỗi!');
  });
}
function doBalance(action){
  const user=document.getElementById('bal-user').value;
  const amount=document.getElementById('bal-amount').value;
  if(!user||!amount){showMsg('bal-msg',false,'Nhập đủ thông tin!');return;}
  const fd=new FormData();fd.append('user',user);fd.append('action',action);fd.append('amount',amount);
  fetch('/admin/api/balance',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    showMsg('bal-msg',d.ok,d.ok?`✅ ${action==='add'?'Cộng':'Trừ'} ${Number(amount).toLocaleString('vi-VN')}đ cho ${d.username}. Số dư: ${(d.new_balance||0).toLocaleString('vi-VN')}đ`:d.msg||'❌ Lỗi!');
  }).catch(()=>showMsg('bal-msg',false,'❌ Lỗi kết nối!'));
}
function approveTopup(content,amount){
  if(!confirm(`Duyệt ${typeof amount==='number'?amount.toLocaleString('vi-VN'):amount}đ?`))return;
  const fd=new FormData();fd.append('content',content);fd.append('amount',amount);
  fetch('/admin/api/approve-topup',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    alert(d.ok?'✅ Đã duyệt!':'❌ Lỗi!');if(d.ok)location.reload();
  });
}
function rejectTopup(content){
  if(!confirm('Từ chối yêu cầu này?'))return;
  const fd=new FormData();fd.append('content',content);
  fetch('/admin/api/reject-topup',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    alert(d.ok?'✅ Đã từ chối!':'❌ Lỗi!');if(d.ok)location.reload();
  });
}
function manualApprove(){
  const content=document.getElementById('tp-content').value.trim();
  const amount=parseInt(document.getElementById('tp-amount').value);
  if(!content||!amount){showMsg('tp-msg',false,'Nhập đủ mã và số tiền!');return;}
  const fd=new FormData();fd.append('content',content);fd.append('amount',amount);
  fetch('/admin/api/approve-topup',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    showMsg('tp-msg',d.ok,'✅ Đã duyệt thành công!');
  }).catch(()=>showMsg('tp-msg',false,'❌ Lỗi kết nối!'));
}
function setNotice(){
  const fd=new FormData();
  fd.append('notice',document.getElementById('notice-txt').value);
  fd.append('btn_desc',(document.getElementById('notice-btn-desc')||{}).value||'');
  fd.append('tg_link',(document.getElementById('notice-tg-link')||{}).value||'');
  fd.append('zalo_link',(document.getElementById('notice-zalo-link')||{}).value||'');
  fetch('/admin/api/notice',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    showMsg('notice-msg',d.ok,d.ok?'✅ Đã cập nhật!':'❌ Lỗi!');
  });
}
function clearNotice(){
  const fd=new FormData();fd.append('notice','');fd.append('btn_desc','');fd.append('tg_link','');fd.append('zalo_link','');
  fetch('/admin/api/notice',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    showMsg('notice-msg',d.ok,d.ok?'✅ Đã xóa!':'❌ Lỗi!');
    if(d.ok){['notice-txt','notice-btn-desc','notice-tg-link','notice-zalo-link'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});}
  });
}
function approveCarry(orderId,username){
  if(!confirm('Đánh dấu đơn kéo thuê của '+username+' là đã hoàn thành?'))return;
  const fd=new FormData();fd.append('order_id',orderId);
  fetch('/admin/api/approve-carry',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    alert(d.ok?'✅ Đã duyệt! User sẽ nhận thông báo.':'❌ '+(d.msg||'Lỗi!'));
    if(d.ok)location.reload();
  }).catch(()=>alert('❌ Lỗi kết nối!'));
}
function sendMsg(){
  const user=document.getElementById('msg-user').value;
  const msg=document.getElementById('msg-txt').value;
  if(!user||!msg){showMsg('msg-res',false,'Nhập đủ thông tin!');return;}
  const fd=new FormData();fd.append('user',user);fd.append('msg',msg);
  fetch('/admin/api/send-msg',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    showMsg('msg-res',d.ok,d.ok?'✅ Đã gửi!':d.msg||'❌ Lỗi!');
  });
}
let _allLogs=[];
function loadLogs(page){
  fetch('/admin/api/logs?page='+(page||1)).then(r=>r.json()).then(d=>{
    if(!d.ok)return;
    _allLogs=d.logs;renderLogs(_allLogs);
    const pg=document.getElementById('log-pages');if(!pg)return;
    pg.innerHTML='';
    for(let i=1;i<=d.pages;i++){
      const b=document.createElement('button');b.className='btn btn-sm '+(i===page?'btn-p':'btn-o');
      b.textContent=i;b.onclick=(()=>{const pp=i;return()=>loadLogs(pp);})();
      pg.appendChild(b);
    }
  });
}
function renderLogs(logs){
  const con=document.getElementById('log-container');if(!con)return;
  if(!logs||!logs.length){con.innerHTML='<div style="color:var(--muted);font-size:.8rem;padding:.5rem;">Không có nhật ký</div>';return;}
  con.innerHTML=logs.map(l=>`<div class="log-row"><span class="log-time">${l.time}</span><span class="log-event">${l.event}</span><span class="log-detail">${l.detail}${l.user&&l.user!=='system'?` <span style="color:var(--muted);font-size:.7rem;">(${l.user})</span>`:''}</span></div>`).join('');
}
function filterLogs(){
  const q=document.getElementById('log-search').value.toLowerCase();
  if(!q){renderLogs(_allLogs);return;}
  renderLogs(_allLogs.filter(l=>(l.event+l.detail+l.user).toLowerCase().includes(q)));
}
function addCustomAcc(){
  const fd=new FormData();
  const fileInput=document.getElementById('ca-file');
  if(fileInput&&fileInput.files.length)fd.append('image_file',fileInput.files[0]);
  fd.append('image_url',(document.getElementById('ca-img-url')||{}).value||'');
  fd.append('acc_user',(document.getElementById('ca-user')||{}).value||'');
  fd.append('acc_pass',(document.getElementById('ca-pass')||{}).value||'');
  fd.append('platform',(document.getElementById('ca-platform')||{}).value||'Facebook');
  fd.append('desc',(document.getElementById('ca-desc')||{}).value||'');
  fd.append('price',(document.getElementById('ca-price')||{}).value||'0');
  const btn=document.querySelector('#pn-customacc .btn-p');if(btn){btn.textContent='⏳ Đang thêm...';btn.disabled=true;}
  fetch('/admin/api/add-custom-acc',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='➕ Thêm Acc Tự Chọn';btn.disabled=false;}
    showMsg('ca-msg',d.ok,d.ok?'✅ Đã thêm!':d.msg||'❌ Lỗi!');
    if(d.ok)setTimeout(()=>location.reload(),1200);
  }).catch(()=>{if(btn){btn.textContent='➕ Thêm Acc Tự Chọn';btn.disabled=false;}showMsg('ca-msg',false,'❌ Lỗi kết nối!');});
}
function delCustomAcc(id){
  if(!confirm('Xóa acc tự chọn này?'))return;
  const fd=new FormData();fd.append('id',id);
  fetch('/admin/api/del-custom-acc',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('✅ Đã xóa!');location.reload();}else alert('❌ Lỗi!');
  });
}
function addFfFile(){
  const fd=new FormData();
  const imgF=document.getElementById('ff-img-file');if(imgF&&imgF.files.length)fd.append('image_file',imgF.files[0]);
  fd.append('image_url',(document.getElementById('ff-img-url')||{}).value||'');
  const dlF=document.getElementById('ff-dl-file');if(dlF&&dlF.files.length)fd.append('dl_file',dlF.files[0]);
  const vidF=document.getElementById('ff-vid-file');if(vidF&&vidF.files.length)fd.append('video_file',vidF.files[0]);
  fd.append('video_url',(document.getElementById('ff-vid-url')||{}).value||'');
  fd.append('name',(document.getElementById('ff-name')||{}).value||'');
  fd.append('desc',(document.getElementById('ff-desc')||{}).value||'');
  fd.append('price',(document.getElementById('ff-price')||{}).value||'0');
  if(!(document.getElementById('ff-name')||{}).value){showMsg('ff-msg',false,'Vui lòng nhập tên file!');return;}
  const btn=document.querySelector('#pn-fffiles .btn-full');if(btn){btn.textContent='⏳ Đang thêm...';btn.disabled=true;}
  fetch('/admin/api/add-ff-file',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='📁 Thêm File FF';btn.disabled=false;}
    showMsg('ff-msg',d.ok,d.ok?'✅ Đã thêm file!':d.msg||'❌ Lỗi!');
    if(d.ok)setTimeout(()=>location.reload(),1200);
  }).catch(()=>{if(btn){btn.textContent='📁 Thêm File FF';btn.disabled=false;}showMsg('ff-msg',false,'❌ Lỗi kết nối!');});
}
function delFfFile(id){
  if(!confirm('Xóa file FF này?'))return;
  const fd=new FormData();fd.append('id',id);
  fetch('/admin/api/del-ff-file',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('✅ Đã xóa!');location.reload();}else alert('❌ Lỗi!');
  });
}
function addSubAdmin(){
  const fd=new FormData();
  fd.append('name',(document.getElementById('sa-name')||{}).value||'');
  fd.append('username',(document.getElementById('sa-username')||{}).value||'');
  fd.append('password',(document.getElementById('sa-password')||{}).value||'');
  fd.append('role',(document.getElementById('sa-role')||{}).value||'Quản Trị Phụ');
  fd.append('tiktok',(document.getElementById('sa-tiktok')||{}).value||'');
  fd.append('facebook',(document.getElementById('sa-facebook')||{}).value||'');
  fd.append('zalo',(document.getElementById('sa-zalo')||{}).value||'');
  const avatarFile=document.getElementById('sa-avatar-file');
  if(avatarFile&&avatarFile.files.length)fd.append('avatar_file',avatarFile.files[0]);
  const btn=document.querySelector('#pn-admins .btn-g.btn-full');if(btn){btn.textContent='⏳ Đang thêm...';btn.disabled=true;}
  fetch('/admin/api/add-sub-admin',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='👑 Thêm Admin Phụ';btn.disabled=false;}
    showMsg('sa-msg',d.ok,d.ok?'✅ Đã thêm admin phụ!':d.msg||'❌ Lỗi!');
    if(d.ok)setTimeout(()=>location.reload(),1200);
  }).catch(()=>{if(btn){btn.textContent='👑 Thêm Admin Phụ';btn.disabled=false;}showMsg('sa-msg',false,'❌ Lỗi kết nối!');});
}
function delSubAdmin(id){
  if(!confirm('Xóa admin phụ này?'))return;
  const fd=new FormData();fd.append('id',id);
  fetch('/admin/api/del-sub-admin',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('✅ Đã xóa!');location.reload();}else alert('❌ '+(d.msg||'Lỗi!'));
  });
}
function addCoupon(){
  const code=document.getElementById('cp-code').value.trim();
  const pct=document.getElementById('cp-pct').value.trim();
  const expires_type=document.getElementById('cp-expires-type').value;
  const days=document.getElementById('cp-days').value.trim();
  if(!pct||parseInt(pct)<1||parseInt(pct)>100){showMsg('cp-msg',false,'Nhập % giảm từ 1–100!');return;}
  const fd=new FormData();
  fd.append('code',code);fd.append('pct',pct);fd.append('expires_type',expires_type);
  if(expires_type==='days')fd.append('expires_days',days||7);
  fetch('/admin/api/add-coupon',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){
      showMsg('cp-msg',true,'✅ Tạo mã thành công: '+d.code+' (-'+d.pct+'%)');
      document.getElementById('cp-code').value='';
      setTimeout(()=>location.reload(),1200);
    } else {showMsg('cp-msg',false,'❌ '+(d.msg||'Lỗi!'));}
  }).catch(()=>showMsg('cp-msg',false,'❌ Lỗi kết nối!'));
}
function delCoupon(code){
  if(!confirm('Xóa mã "'+code+'"?'))return;
  const fd=new FormData();fd.append('code',code);
  fetch('/admin/api/del-coupon',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('✅ Đã xóa mã '+code+'!');location.reload();}else alert('❌ '+(d.msg||'Lỗi!'));
  });
}
function addFeedback(){
  const fileInput=document.getElementById('fb-file');
  const url=document.getElementById('fb-url').value.trim();
  const desc=document.getElementById('fb-desc').value.trim();
  const customer=document.getElementById('fb-customer').value.trim();
  if(!fileInput.files.length&&!url&&!desc){showMsg('fb-msg',false,'Cần nhập mô tả hoặc chọn ảnh/video!');return;}
  const fd=new FormData();
  if(fileInput.files.length)fd.append('media_file',fileInput.files[0]);
  fd.append('media_url',url);fd.append('desc',desc);fd.append('customer',customer);
  const btn=document.querySelector('#pn-feedback .btn-p');if(btn){btn.textContent='⏳ Đang tải...';btn.disabled=true;}
  fetch('/admin/api/add-feedback',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(btn){btn.textContent='📤 Đăng Feedback';btn.disabled=false;}
    showMsg('fb-msg',d.ok,d.ok?'✅ Đã đăng!':d.msg||'❌ Lỗi!');
    if(d.ok){fileInput.value='';document.getElementById('fb-url').value='';document.getElementById('fb-desc').value='';document.getElementById('fb-customer').value='';setTimeout(()=>location.reload(),1200);}
  }).catch(()=>{if(btn){btn.textContent='📤 Đăng Feedback';btn.disabled=false;}showMsg('fb-msg',false,'❌ Lỗi kết nối!');});
}
function delFeedback(id){
  if(!confirm('Xóa feedback này?'))return;
  const fd=new FormData();fd.append('id',id);
  fetch('/admin/api/del-feedback',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
    if(d.ok){alert('✅ Đã xóa!');location.reload();}else alert('❌ Lỗi!');
  });
}
</script>
</body></html>"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
