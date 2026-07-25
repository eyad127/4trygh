# -*- coding: utf-8 -*-
import os, json, uuid
from functools import wraps
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, make_response, g, jsonify, Response, stream_with_context
from markupsafe import Markup
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///car_shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['CHAT_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'chat')
app.config['PAYMENT_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'payments')
app.config['MAX_CONTENT_LENGTH'] = None

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CHAT_FOLDER'], exist_ok=True)
os.makedirs(app.config['PAYMENT_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'من فضلك سجل الدخول أولاً.'

# ====================== النماذج ======================
class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def get_id(self):
        return f'admin:{self.id}'

class Customer(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    address = db.Column(db.Text, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    password_plain = db.Column(db.String(128), nullable=True)  # نسخة لعرضها في لوحة الأدمن فقط
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        return f'cust:{self.id}'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    main_image = db.Column(db.String(120), default='default.jpg')
    extra_images = db.relationship('ProductImage', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='product', lazy='dynamic', cascade='all, delete-orphan')

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), index=True, nullable=True)
    customer_uid = db.Column(db.String(40), index=True, nullable=True)
    customer_name = db.Column(db.String(80), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    transaction_ref = db.Column(db.String(100), nullable=True)
    payment_proof = db.Column(db.String(120), nullable=True)  # صورة تأكيد التحويل (فودافون كاش / إنستاباي)
    total = db.Column(db.Float, nullable=False)
    confirmed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    product = db.relationship('Product')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), index=True, nullable=True)
    author = db.Column(db.String(80), nullable=False)
    rating = db.Column(db.Integer, default=5, nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ReturnRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), index=True, nullable=True)
    customer_uid = db.Column(db.String(40), index=True, nullable=True)
    reason = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(30), default='قيد المراجعة')
    admin_note = db.Column(db.Text, nullable=True)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(40), index=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), index=True, nullable=True)
    customer_name = db.Column(db.String(80), nullable=True)
    sender = db.Column(db.String(10), nullable=False)  # 'user' أو 'admin'
    body = db.Column(db.Text, nullable=True)
    msg_type = db.Column(db.String(10), default='text', nullable=False)  # 'text' | 'image' | 'voice'
    media_file = db.Column(db.String(120), nullable=True)  # اسم ملف الصورة أو الصوت
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_by_admin = db.Column(db.Boolean, default=False)
    read_by_user = db.Column(db.Boolean, default=True)

@login_manager.user_loader
def load_user(user_id):
    try:
        kind, _id = str(user_id).split(':', 1)
    except ValueError:
        # توافق مع الجلسات القديمة (كانت للأدمن فقط)
        return db.session.get(Admin, int(user_id))
    if kind == 'admin':
        return db.session.get(Admin, int(_id))
    if kind == 'cust':
        return db.session.get(Customer, int(_id))
    return None

# -------- صلاحيات --------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (current_user.is_authenticated and isinstance(current_user, Admin)):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper

def customer_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not (current_user.is_authenticated and isinstance(current_user, Customer)):
            flash('من فضلك سجّل الدخول للمتابعة.', 'warning')
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapper

def current_customer():
    if current_user.is_authenticated and isinstance(current_user, Customer):
        return current_user
    return None

def link_orders_to_customer(customer):
    """يربط الطلبات القديمة (بدون حساب) بهذا الحساب عبر مطابقة رقم الهاتف."""
    changed = False
    orphan_orders = Order.query.filter(Order.customer_id.is_(None), Order.customer_phone == customer.phone).all()
    for o in orphan_orders:
        o.customer_id = customer.id
        # اربط أيضاً طلبات الاسترجاع المرتب��ة بهذا الطلب
        for r in ReturnRequest.query.filter_by(order_id=o.id).all():
            if r.customer_id is None:
                r.customer_id = customer.id
        changed = True
    if changed:
        db.session.commit()

# -------- هوية زائر عبر الكوكي (للعربة قبل تسجيل الدخول) --------
@app.before_request
def _load_uid():
    uid = request.cookies.get('mo_uid')
    if not uid:
        uid = uuid.uuid4().hex
        g.new_uid = uid
    g.uid = uid

@app.after_request
def _save_uid(response):
    new_uid = getattr(g, 'new_uid', None)
    if new_uid:
        response.set_cookie('mo_uid', new_uid, max_age=60*60*24*365, httponly=True, samesite='Lax')
    return response

def current_uid():
    return getattr(g, 'uid', None) or request.cookies.get('mo_uid')

@app.context_processor
def inject_globals():
    unread = 0
    admin_unread = 0
    admin_unread_guests = 0
    cust = current_customer()
    try:
        if cust:
            unread = ChatMessage.query.filter_by(customer_id=cust.id, sender='admin', read_by_user=False).count()
        else:
            unread = ChatMessage.query.filter_by(uid=current_uid(), customer_id=None, sender='admin', read_by_user=False).count()
        admin_unread = ChatMessage.query.filter(ChatMessage.sender == 'user', ChatMessage.read_by_admin == False, ChatMessage.customer_id.isnot(None)).count()
        admin_unread_guests = ChatMessage.query.filter(ChatMessage.sender == 'user', ChatMessage.read_by_admin == False, ChatMessage.customer_id.is_(None)).count()
    except Exception:
        unread = 0
        admin_unread = 0
        admin_unread_guests = 0
    return {
        'unread_user': unread,
        'admin_unread': admin_unread,
        'admin_unread_guests': admin_unread_guests,
        'is_customer': cust is not None,
        'customer_name': cust.name if cust else None,
    }

def get_cart_info():
    cart = session.get('cart', {})
    items = []
    total = 0
    for pid, qty in cart.items():
        product = db.session.get(Product, int(pid))
        if product:
            subtotal = product.price * qty
            total += subtotal
            items.append({'product': product, 'qty': qty, 'subtotal': subtotal})
    return items, total

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp'}

IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
AUDIO_EXTS = {'webm', 'ogg', 'oga', 'mp3', 'wav', 'm4a', 'mp4', 'aac'}

def _ext(filename, default='bin'):
    return filename.rsplit('.', 1)[1].lower() if ('.' in filename) else default

def save_upload(file_storage, folder, allowed_exts):
    """يحفظ ملفاً مرفوعاً باسم فريد داخل المجلد المحدد ويعيد اسم الملف."""
    if not file_storage or not file_storage.filename:
        return None
    ext = _ext(file_storage.filename)
    if ext not in allowed_exts:
        return None
    fname = f'{uuid.uuid4().hex}.{ext}'
    file_storage.save(os.path.join(folder, fname))
    return fname

def save_chat_image(file_storage):
    return save_upload(file_storage, app.config['CHAT_FOLDER'], IMAGE_EXTS)

def save_chat_voice(file_storage):
    # المتصفح غالباً يرسل webm بدون امتداد؛ نحدد الامتداد من نوع الملف
    if not file_storage or not file_storage.filename:
        return None
    ext = _ext(file_storage.filename, 'webm')
    if ext not in AUDIO_EXTS:
        ext = 'webm'
    fname = f'{uuid.uuid4().hex}.{ext}'
    file_storage.save(os.path.join(app.config['CHAT_FOLDER'], fname))
    return fname

def save_payment_proof(file_storage):
    return save_upload(file_storage, app.config['PAYMENT_FOLDER'], IMAGE_EXTS)

def build_chat_message(**kwargs):
    """ينشئ رسالة شات مع دعم النص/الصورة/الصوت من طلب واحد. يعيد الرسالة أو None."""
    body = (request.form.get('body') or '').strip()
    image = request.files.get('image')
    voice = request.files.get('voice')
    msg_type = 'text'
    media_file = None
    img_name = save_chat_image(image) if image else None
    if img_name:
        msg_type = 'image'
        media_file = img_name
    else:
        voice_name = save_chat_voice(voice) if voice else None
        if voice_name:
            msg_type = 'voice'
            media_file = voice_name
    if not body and not media_file:
        return None
    return ChatMessage(body=body or '', msg_type=msg_type, media_file=media_file, **kwargs)

# -------- تقييمات حقيقية --------
def get_rating(product):
    ratings = [r.rating for r in product.reviews.all()]
    if not ratings:
        return 0.0, 0
    return round(sum(ratings) / len(ratings), 1), len(ratings)

def stars_html(avg, size='.8rem'):
    avg = float(avg or 0)
    full = int(avg)
    half = 1 if (avg - full) >= 0.5 else 0
    empty = 5 - full - half
    html = f'<span class="stars" style="font-size:{size};">'
    html += '<i class="bi bi-star-fill"></i>' * full
    if half:
        html += '<i class="bi bi-star-half"></i>'
    html += '<i class="bi bi-star"></i>' * empty
    html += '</span>'
    return html

# -------- حساب المبالغ والأرباح --------
def return_amount(ret):
    """قيمة طلب الاسترجاع = سعر المنتج × الكمية في هذا الطلب."""
    item = OrderItem.query.filter_by(order_id=ret.order_id, product_id=ret.product_id).first()
    qty = item.quantity if item else 1
    product = db.session.get(Product, ret.product_id)
    price = product.price if product else 0
    return price * qty

def compute_revenue():
    """الأرباح = مجموع الطلبات المؤكدة - مجموع الاسترجاعات المقبولة."""
    confirmed_total = sum(o.total for o in Order.query.filter_by(confirmed=True).all())
    accepted_returns = sum(return_amount(r) for r in ReturnRequest.query.filter_by(status='مقبول').all())
    return confirmed_total, accepted_returns, confirmed_total - accepted_returns

# ======================================================================
# ============  واجهة ماركت بليس فاتحة (على طراز أمازون / نون)  ==========
# ======================================================================
BASE_HTML = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <meta name="theme-color" content="#111c2e">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800;900&family=Cairo:wght@600;700;800;900&display=swap" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css" rel="stylesheet">
    <style>
        *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
        :root{
            --brand:#111c2e; --brand-2:#1c2b45;
            --accent:#ff7a00; --accent-dark:#e56a00; --accent-soft:#fff2e6;
            --price:#e34a1f;
            --ink:#0f1720; --ink-2:#4b5563; --muted:#8b95a3;
            --bg:#f3f4f6; --surface:#ffffff; --surface-2:#f8f9fb;
            --line:#e4e7ec; --line-2:#eef0f3;
            --ok:#1a9e5e; --ok-soft:#e6f6ee; --warn:#b8860b; --warn-soft:#fdf3d9;
            --radius:14px; --radius-sm:10px;
            --shadow-sm:0 1px 3px rgba(16,23,32,.08);
            --shadow:0 6px 20px rgba(16,23,32,.10);
            --shadow-lg:0 20px 50px rgba(16,23,32,.18);
            --t:.25s ease;
            --header-h:118px;
        }
        ::-webkit-scrollbar{width:10px}
        ::-webkit-scrollbar-track{background:var(--bg)}
        ::-webkit-scrollbar-thumb{background:#c7ccd4;border-radius:9px;border:2px solid var(--bg)}
        ::-webkit-scrollbar-thumb:hover{background:var(--accent)}
        html{background:var(--bg)}
        body{background:var(--bg);color:var(--ink);font-family:'Tajawal',sans-serif;padding-top:var(--header-h);min-height:100vh;overflow-x:hidden;display:flex;flex-direction:column}
        main.container{flex:1 0 auto;width:100%;position:relative;z-index:1}
        .num{font-family:'Cairo','Tajawal',sans-serif}

        /* ===== Header (marketplace) ===== */
        .site-header{position:fixed;top:0;left:0;right:0;z-index:1050}
        .topbar{background:var(--brand);padding:12px 0}
        .topbar .inner{display:flex;align-items:center;gap:14px}
        .brand{display:flex;align-items:center;gap:9px;color:#fff!important;font-family:'Cairo',sans-serif;font-weight:800;font-size:1.5rem;text-decoration:none;white-space:nowrap;letter-spacing:-.3px}
        .brand .dot{width:11px;height:11px;border-radius:50%;background:var(--accent);display:inline-block}
        .brand-name{display:inline-flex;flex-direction:column;line-height:1}
        .brand-name .brand-sub{font-size:.6rem;font-weight:600;color:#9fb0c9;letter-spacing:2px;margin-top:2px}
        /* search */
        .searchbar{flex:1;display:flex;background:#fff;border-radius:11px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.15);max-width:640px}
        .searchbar input{flex:1;min-width:0;border:none;outline:none;padding:11px 16px;font-family:'Tajawal',sans-serif;font-size:.95rem;color:var(--ink)}
        .searchbar input::placeholder{color:var(--muted)}
        .searchbar button{background:var(--accent);border:none;color:#fff;padding:0 20px;font-size:1.15rem;transition:var(--t)}
        .searchbar button:hover{background:var(--accent-dark)}
        .h-actions{display:flex;align-items:center;gap:4px;flex-shrink:0}
        .h-action{display:flex;align-items:center;gap:6px;color:#e7ecf3!important;text-decoration:none;font-weight:600;font-size:.85rem;padding:8px 10px;border-radius:10px;transition:var(--t);position:relative;white-space:nowrap}
        .h-action:hover{background:rgba(255,255,255,.1);color:#fff!important}
        .h-action i{font-size:1.3rem}
        .h-action .lbl{display:flex;flex-direction:column;line-height:1.2}
        .h-action .lbl span{font-size:.7rem;color:#9fb0c9}
        .h-action .lbl b{font-size:.85rem}
        .cart-count{position:absolute;top:2px;right:2px;background:var(--accent);color:#fff;font-size:.62rem;font-weight:800;min-width:18px;height:18px;padding:0 4px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;font-family:'Cairo',sans-serif}
        /* sub bar */
        .subbar{background:var(--brand-2);padding:8px 0}
        .subbar .inner{display:flex;align-items:center;gap:22px;flex-wrap:wrap;color:#c7d2e0;font-size:.82rem;font-weight:600}
        .subbar a{color:#c7d2e0;text-decoration:none;display:inline-flex;align-items:center;gap:6px;transition:var(--t)}
        .subbar a:hover{color:#fff}
        .subbar i{color:var(--accent)}

        /* ===== Buttons ===== */
        .btn-accent{background:var(--accent);color:#fff;font-weight:700;border:none;border-radius:11px;padding:11px 22px;transition:var(--t);font-family:'Tajawal',sans-serif}
        .btn-accent:hover{background:var(--accent-dark);color:#fff;box-shadow:0 6px 16px rgba(255,122,0,.32);transform:translateY(-1px)}
        .btn-ghost{background:var(--surface);color:var(--ink);font-weight:700;border:1.5px solid var(--line);border-radius:11px;padding:10px 20px;transition:var(--t);font-family:'Tajawal',sans-serif}
        .btn-ghost:hover{border-color:var(--brand);color:var(--brand);transform:translateY(-1px)}
        .btn-icon{width:42px;height:42px;border-radius:11px;display:inline-flex;align-items:center;justify-content:center;padding:0;font-size:1.05rem}

        /* ===== Titles ===== */
        .page-title{font-family:'Cairo',sans-serif;font-weight:800;font-size:1.7rem;color:var(--ink);margin-bottom:1.4rem;letter-spacing:-.4px;display:flex;align-items:center;gap:10px}
        .page-title i{color:var(--accent)}
        .eyebrow{display:inline-flex;align-items:center;gap:7px;background:var(--accent-soft);color:var(--accent-dark);font-weight:800;font-size:.78rem;padding:6px 13px;border-radius:30px;letter-spacing:.2px}

        /* ===== Hero banner ===== */
        .hero{position:relative;border-radius:20px;overflow:hidden;background:linear-gradient(105deg,var(--brand) 0%,var(--brand-2) 60%,#2a3f63 100%);color:#fff;margin-bottom:30px;box-shadow:var(--shadow)}
        .hero-img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.28;mix-blend-mode:luminosity}
        .hero-inner{position:relative;z-index:2;padding:46px 42px}
        .hero h1{font-family:'Cairo',sans-serif;font-weight:900;font-size:2.7rem;line-height:1.2;letter-spacing:-1px;margin-bottom:12px}
        .hero h1 .hl{color:var(--accent)}
        .hero p{color:#c7d2e0;font-size:1.05rem;max-width:440px;line-height:1.8;margin-bottom:22px}
        .hero-stats{display:flex;gap:12px;margin-top:26px;flex-wrap:wrap}
        .stat-chip{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.14);border-radius:12px;padding:10px 16px}
        .stat-chip .s-num{font-family:'Cairo',sans-serif;font-weight:800;font-size:1.3rem;color:#fff;line-height:1}
        .stat-chip .s-label{color:#9fb0c9;font-size:.76rem;margin-top:3px}

        /* ===== Product cards (marketplace) ===== */
        .product-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;transition:var(--t);height:100%;display:flex;flex-direction:column;position:relative}
        .product-card:hover{box-shadow:var(--shadow);transform:translateY(-4px);border-color:#d4d9e0}
        .product-card .img-wrap{position:relative;overflow:hidden;aspect-ratio:1/1;background:#fff;border-bottom:1px solid var(--line-2)}
        .product-card .img-wrap img{width:100%;height:100%;object-fit:contain;padding:10px;transition:transform .5s ease;cursor:pointer}
        .product-card:hover .img-wrap img{transform:scale(1.06)}
        .ship-tag{position:absolute;top:10px;right:10px;background:var(--ok-soft);color:var(--ok);font-size:.68rem;font-weight:800;padding:4px 10px;border-radius:20px;z-index:2}
        .product-card .card-body{padding:14px;flex-grow:1;display:flex;flex-direction:column}
        .p-name{font-weight:700;color:var(--ink);font-size:.95rem;margin-bottom:6px;line-height:1.5;min-height:2.8em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
        .stars{color:#ffb400}
        .rating-line{display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:.8rem}
        .rating-line .rcount{color:var(--muted);font-family:'Cairo',sans-serif}
        .rating-line .no-rate{color:var(--muted);font-size:.78rem}
        .p-price{font-family:'Cairo',sans-serif;font-weight:800;font-size:1.35rem;color:var(--price);line-height:1}
        .p-price span{font-size:.72rem;font-weight:600;color:var(--muted);font-family:'Tajawal',sans-serif}
        .btn-cart{width:100%;background:var(--accent);color:#fff;font-weight:700;border:none;border-radius:10px;padding:10px;margin-top:12px;transition:var(--t);display:flex;align-items:center;justify-content:center;gap:7px;text-decoration:none}
        .btn-cart:hover{background:var(--accent-dark);color:#fff}

        /* ===== Surfaces ===== */
        .panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:24px}
        .soft-line{height:1px;background:var(--line);margin:22px 0}

        /* ===== Auth ===== */
        .auth-wrap{max-width:440px;margin:0 auto}
        .auth-icon{width:70px;height:70px;border-radius:20px;background:var(--accent-soft);color:var(--accent);display:inline-flex;align-items:center;justify-content:center;font-size:1.8rem;margin-bottom:18px}

        /* ===== Star rating input ===== */
        .rate-input{display:inline-flex;flex-direction:row-reverse;justify-content:flex-end;gap:6px}
        .rate-input input{display:none}
        .rate-input label{font-size:1.7rem;color:var(--line);cursor:pointer;transition:var(--t);line-height:1}
        .rate-input label:hover,.rate-input label:hover ~ label,.rate-input input:checked ~ label{color:#ffb400}

        /* ===== Tables ===== */
        .table-clean{background:var(--surface);border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);color:var(--ink)}
        .table-clean thead{background:var(--surface-2)}
        .table-clean thead th{border-bottom:1px solid var(--line);color:var(--ink-2);font-weight:700;padding:14px 16px;font-size:.85rem}
        .table-clean tbody td{border-color:var(--line-2);padding:13px 16px;vertical-align:middle;color:var(--ink)}
        .table-clean tbody tr{transition:var(--t)}
        .table-clean tbody tr:hover{background:var(--surface-2)}
        .cart-img{width:66px;height:66px;object-fit:contain;background:#fff;border-radius:12px;border:1px solid var(--line);padding:4px}

        /* ===== Cart quantity controls ===== */
        .qty-control{display:inline-flex;align-items:center;gap:0;border:1.5px solid var(--line);border-radius:11px;overflow:hidden;background:var(--surface)}
        .qty-btn{width:38px;height:38px;display:inline-flex;align-items:center;justify-content:center;color:var(--ink-2);text-decoration:none;font-size:.95rem;transition:var(--t);background:var(--surface-2);cursor:pointer;border:none}
        .qty-btn:hover{background:var(--accent);color:#fff}
        .qty-val{min-width:44px;text-align:center;font-weight:800;color:var(--ink);font-size:1.05rem}
        .btn-icon-del{width:38px;height:38px;display:inline-flex;align-items:center;justify-content:center;border-radius:10px;border:1.5px solid #f0c9c9;color:#c0392b;text-decoration:none;transition:var(--t);cursor:pointer;background:transparent}
        .btn-icon-del:hover{background:#c0392b;color:#fff;border-color:#c0392b}

        /* ===== Support chat float ===== */
        .chat-fab{position:fixed;bottom:22px;left:22px;z-index:1040;width:60px;height:60px;border-radius:50%;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;font-size:1.5rem;box-shadow:0 8px 22px rgba(255,122,0,.4);text-decoration:none;transition:var(--t)}
        .chat-fab:hover{background:var(--accent-dark);color:#fff;transform:scale(1.06)}
        .chat-fab .cnt{position:absolute;top:-3px;right:-3px;background:var(--price);color:#fff;font-size:.68rem;font-weight:800;min-width:20px;height:20px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-family:'Cairo',sans-serif;border:2px solid var(--bg)}
        .chat-wrap{max-width:760px;margin:0 auto}
        .chat-box{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);height:56vh;min-height:340px;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:10px}
        .msg{max-width:78%;padding:11px 15px;border-radius:16px;font-size:.92rem;line-height:1.6;position:relative;word-break:break-word}
        .chat-media-img{max-width:220px;max-height:240px;border-radius:12px;display:block;margin:2px 0;cursor:pointer;object-fit:cover}
        .chat-media-audio{width:230px;max-width:100%;height:40px;margin:2px 0;display:block}
        .chat-input-form{margin-top:12px}
        .chat-input-row{display:flex;gap:8px;align-items:center}
        .chat-tool-btn{width:44px;height:44px;flex:0 0 auto;border-radius:11px;border:1.5px solid var(--line);background:var(--surface);color:var(--brand);display:inline-flex;align-items:center;justify-content:center;font-size:1.15rem;padding:0;transition:var(--t)}
        .chat-tool-btn:hover{border-color:var(--accent);color:var(--accent)}
        .chat-tool-btn.recording{background:var(--accent);color:#fff;border-color:var(--accent);animation:recPulse 1s infinite}
        @keyframes recPulse{0%,100%{box-shadow:0 0 0 0 rgba(255,122,0,.5)}50%{box-shadow:0 0 0 6px rgba(255,122,0,0)}}
        .chat-send-btn{width:46px;height:44px;flex:0 0 auto;border-radius:11px;padding:0;display:inline-flex;align-items:center;justify-content:center}
        .chat-preview-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
        .chat-preview-bar .prev-item{position:relative}
        .chat-preview-bar .prev-item img{width:64px;height:64px;object-fit:cover;border-radius:10px;border:1px solid var(--line)}
        .chat-preview-bar .prev-item.voice audio{height:38px}
        .chat-preview-bar .prev-item button{position:absolute;top:-8px;inset-inline-end:-8px;width:22px;height:22px;border-radius:50%;border:none;background:var(--price);color:#fff;font-size:.9rem;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center}
        .chat-rec-bar{display:flex;align-items:center;gap:12px;margin-bottom:10px;padding:8px 12px;background:var(--surface);border:1.5px solid var(--line);border-radius:26px;color:var(--price);font-weight:700;font-size:.9rem;box-shadow:var(--shadow-sm)}
        .chat-rec-bar .rec-dot{width:11px;height:11px;border-radius:50%;background:var(--price);flex:0 0 auto;animation:recPulse 1s infinite}
        .chat-rec-bar .rec-time{font-size:.95rem;min-width:44px;color:var(--ink)}
        .chat-rec-bar .rec-wave{flex:1;display:flex;align-items:center;justify-content:center;gap:3px;height:26px;overflow:hidden}
        .chat-rec-bar .rec-wave span{display:block;width:3px;height:6px;border-radius:3px;background:var(--accent);animation:recWave 1s ease-in-out infinite}
        .chat-rec-bar .rec-wave span:nth-child(2n){animation-duration:.85s}
        .chat-rec-bar .rec-wave span:nth-child(3n){animation-duration:1.15s}
        .chat-rec-bar .rec-wave span:nth-child(4n){animation-duration:.7s}
        @keyframes recWave{0%,100%{height:6px;opacity:.5}50%{height:22px;opacity:1}}
        .chat-rec-bar .rec-cancel,.chat-rec-bar .rec-send{width:40px;height:40px;flex:0 0 auto;border:none;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:1.05rem;cursor:pointer;transition:var(--t)}
        .chat-rec-bar .rec-cancel{background:var(--surface-2);color:var(--price);border:1.5px solid var(--line)}
        .chat-rec-bar .rec-cancel:hover{background:#fdeaea;border-color:#f5c2c2}
        .chat-rec-bar .rec-send{background:var(--accent);color:#fff}
        .chat-rec-bar .rec-send:hover{background:var(--accent-dark);transform:scale(1.05)}
        /* ===== مشغّل الصوت (شكل واتساب) ===== */
        .voice-player{display:inline-flex;align-items:center;gap:10px;background:rgba(15,23,32,.05);border-radius:22px;padding:6px 14px 6px 6px;min-width:210px;max-width:270px;margin:2px 0}
        .msg.admin .voice-player{background:rgba(255,255,255,.18)}
        .voice-player .vp-play{width:38px;height:38px;flex:0 0 auto;border:none;border-radius:50%;background:var(--accent);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:1.1rem;cursor:pointer;transition:var(--t)}
        .voice-player .vp-play:hover{background:var(--accent-dark)}
        .msg.admin .voice-player .vp-play{background:#fff;color:var(--brand)}
        .voice-player .vp-track{flex:1;height:5px;border-radius:5px;background:rgba(15,23,32,.15);position:relative;cursor:pointer}
        .msg.admin .voice-player .vp-track{background:rgba(255,255,255,.35)}
        .voice-player .vp-progress{position:absolute;inset-block:0;inset-inline-start:0;width:0;background:var(--accent);border-radius:5px}
        .msg.admin .voice-player .vp-progress{background:#fff}
        .voice-player .vp-time{font-size:.72rem;opacity:.8;min-width:34px;text-align:center}
        /* ===== مكالمة صوتية (شكل ديسكورد) ===== */
        .call-btn{display:inline-flex;align-items:center;gap:8px;border:1.5px solid var(--line);background:var(--surface);color:var(--ink);border-radius:12px;padding:7px 14px;font-weight:700;font-size:.85rem;cursor:pointer;transition:var(--t)}
        .call-btn:hover{border-color:var(--accent);color:var(--accent)}
        .call-btn.peer-online{border-color:var(--accent);color:var(--accent)}
        .call-btn .call-presence{width:9px;height:9px;border-radius:50%;background:var(--muted);flex:0 0 auto;box-shadow:0 0 0 0 rgba(0,0,0,0)}
        .call-btn .call-presence.online{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.22);animation:presPulse 2s infinite}
        @keyframes presPulse{0%,100%{box-shadow:0 0 0 2px rgba(34,197,94,.25)}50%{box-shadow:0 0 0 5px rgba(34,197,94,0)}}
        .call-overlay{position:fixed;inset:0;z-index:3000;display:none;align-items:center;justify-content:center;background:rgba(8,12,18,.72);backdrop-filter:blur(6px)}
        .call-overlay.show{display:flex;animation:callFade .2s ease}
        @keyframes callFade{from{opacity:0}to{opacity:1}}
        .call-modal{width:min(92vw,340px);background:var(--surface);border:1px solid var(--line);border-radius:24px;padding:34px 26px 26px;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,.45)}
        .call-avatar{position:relative;width:104px;height:104px;margin:0 auto 18px;border-radius:50%;background:linear-gradient(145deg,var(--accent),var(--accent-dark));color:#fff;display:flex;align-items:center;justify-content:center;font-size:2.4rem;font-weight:800}
        .call-avatar .call-ring{position:absolute;inset:-6px;border-radius:50%;border:3px solid var(--accent);opacity:0}
        .call-avatar.pulsing .call-ring{animation:callRing 1.5s ease-out infinite}
        @keyframes callRing{0%{transform:scale(1);opacity:.6}100%{transform:scale(1.35);opacity:0}}
        .call-peer-name{font-size:1.25rem;font-weight:800;color:var(--ink);margin-bottom:4px}
        .call-status{color:var(--muted);font-size:.92rem;min-height:22px}
        .call-timer{font-size:1.05rem;font-weight:800;color:var(--accent);margin-top:6px}
        .call-actions{display:flex;align-items:center;justify-content:center;gap:22px;margin-top:24px}
        .call-ic{width:60px;height:60px;border:none;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:1.5rem;color:#fff;cursor:pointer;transition:var(--t)}
        .call-ic:hover{transform:translateY(-2px) scale(1.05)}
        .call-accept{background:#22c55e}
        .call-decline{background:#ef4444}
        .call-mute{background:var(--surface-2);color:var(--ink);border:1.5px solid var(--line)}
        .call-mute:hover{background:var(--line)}
        .call-spk{background:var(--surface-2);color:var(--ink);border:1.5px solid var(--line)}
        .call-spk:hover{background:var(--line)}
        .call-spk.on{background:var(--accent);color:#fff;border-color:var(--accent)}
        .msg .time{display:block;font-size:.66rem;opacity:.6;margin-top:4px}
        .msg.user{align-self:flex-start;background:var(--surface-2);border:1px solid var(--line);color:var(--ink);border-bottom-right-radius:5px}
        .msg.admin{align-self:flex-end;background:var(--brand);color:#fff;border-bottom-left-radius:5px}
        .chat-empty{margin:auto;text-align:center;color:var(--muted)}

        /* ===== Alerts ===== */
        .alert{border-radius:var(--radius-sm);border:1px solid var(--line);font-weight:600}
        .alert-success{background:var(--ok-soft);border-color:#bfe6cf;color:#137a48}
        .alert-danger{background:#fdeaea;border-color:#f5c2c2;color:#c0392b}
        .alert-warning{background:var(--warn-soft);border-color:#f0dca0;color:#8a6300}
        .alert-info{background:#e8f1fd;border-color:#c3dbf7;color:#1c5aa8}

        /* ===== Forms ===== */
        .form-control,.form-select{background:var(--surface)!important;border:1.5px solid var(--line)!important;color:var(--ink)!important;border-radius:11px!important;padding:12px 15px!important;transition:var(--t)!important;font-family:'Tajawal',sans-serif!important}
        .form-control:focus,.form-select:focus{border-color:var(--accent)!important;box-shadow:0 0 0 4px var(--accent-soft)!important;outline:none!important}
        .form-control::placeholder{color:var(--muted)!important}
        .form-label{color:var(--ink);font-weight:700;font-size:.88rem;margin-bottom:6px}
        .form-text{color:var(--muted)!important;font-size:.8rem}

        /* ===== Badges ===== */
        .badge-confirmed{background:var(--ok-soft);color:var(--ok);padding:6px 13px;border-radius:20px;font-weight:800;font-size:.78rem}
        .badge-pending{background:var(--warn-soft);color:#8a6300;padding:6px 13px;border-radius:20px;font-weight:800;font-size:.78rem}
        .badge-rejected{background:#fdeaea;color:#c0392b;padding:6px 13px;border-radius:20px;font-weight:800;font-size:.78rem}

        /* ===== Reviews / Orders ===== */
        .review-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-sm);padding:16px 18px;margin-bottom:12px;transition:var(--t)}
        .review-card:hover{box-shadow:var(--shadow-sm)}
        .order-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:14px;transition:var(--t)}
        .order-card:hover{box-shadow:var(--shadow);transform:translateY(-2px)}
        .order-id{font-family:'Cairo',sans-serif;font-weight:800;color:var(--ink);font-size:1.1rem}

        /* ===== Thumbs / detail ===== */
        .thumb-img{cursor:pointer;border-radius:11px;border:2px solid var(--line);transition:var(--t);object-fit:contain;background:#fff;height:74px;width:100%;padding:4px}
        .thumb-img:hover,.thumb-img.active{border-color:var(--accent)}
        .detail-img-main{border-radius:var(--radius);border:1px solid var(--line);cursor:pointer;width:100%;max-height:460px;object-fit:contain;transition:var(--t);background:#fff;padding:16px}
        .detail-img-main:hover{box-shadow:var(--shadow)}

        /* ===== Lightbox ===== */
        .lightbox{display:none;position:fixed;inset:0;z-index:9999;background:rgba(15,23,32,.9);align-items:center;justify-content:center;animation:fade .3s}
        .lightbox.active{display:flex}
        .lightbox img{max-width:92%;max-height:85vh;border-radius:var(--radius);background:#fff}
        .lb-close{position:absolute;top:22px;left:26px;font-size:1.3rem;color:#fff;cursor:pointer;width:46px;height:46px;border-radius:50%;background:rgba(255,255,255,.14);display:flex;align-items:center;justify-content:center;transition:var(--t)}
        .lb-close:hover{background:var(--accent)}
        .lb-prev,.lb-next{position:absolute;top:50%;transform:translateY(-50%);font-size:1.2rem;color:#fff;cursor:pointer;background:rgba(255,255,255,.14);width:52px;height:52px;border:none;border-radius:50%;transition:var(--t)}
        .lb-prev:hover,.lb-next:hover{background:var(--accent)}
        .lb-prev{right:20px}.lb-next{left:20px}

        /* ===== Empty / success ===== */
        .empty-state{text-align:center;padding:66px 20px}
        .empty-state .ico{width:92px;height:92px;border-radius:24px;background:var(--surface);border:1px solid var(--line);display:inline-flex;align-items:center;justify-content:center;font-size:2.5rem;color:var(--accent);margin-bottom:20px;box-shadow:var(--shadow-sm)}
        .empty-state h4{color:var(--ink);font-weight:800;margin-bottom:8px;font-family:'Cairo',sans-serif}
        .success-icon{width:92px;height:92px;border-radius:50%;background:var(--ok-soft);display:inline-flex;align-items:center;justify-content:center;font-size:2.7rem;color:var(--ok);animation:pulse 2s ease-in-out infinite}
        @keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(26,158,94,.22)}50%{box-shadow:0 0 0 18px rgba(26,158,94,0)}}

        .trust{display:flex;align-items:center;gap:8px;color:var(--ink-2);font-size:.83rem;font-weight:700}
        .trust i{font-size:1.2rem;color:var(--accent)}

        /* ===== Toast ===== */
        .toast-custom{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(120px);background:var(--brand);border:1px solid rgba(255,255,255,.1);color:#fff;padding:14px 26px;border-radius:13px;z-index:10000;font-weight:700;box-shadow:var(--shadow-lg);transition:transform .4s cubic-bezier(.68,-.55,.27,1.55);display:flex;align-items:center;gap:10px}
        .toast-custom.show{transform:translateX(-50%) translateY(0)}
        .toast-custom i{color:#4ade80;font-size:1.2rem}

        .breadcrumb-item a{color:var(--accent-dark);text-decoration:none;font-weight:700}
        .breadcrumb-item.active{color:var(--muted)}

        .fade-up{opacity:0;transform:translateY(22px);transition:opacity .5s ease,transform .5s ease}
        .fade-up.visible{opacity:1;transform:translateY(0)}
        @keyframes fade{from{opacity:0}to{opacity:1}}
        .cropper-container{touch-action:none}

        footer.site-footer{background:var(--brand);color:#c7d2e0;margin-top:56px;padding:30px 0;flex-shrink:0}
        footer.site-footer a{color:#9fb0c9;text-decoration:none}
        footer.site-footer a:hover{color:#fff}

        /* ===== Responsive ===== */
        @media(max-width:991px){
            .hero h1{font-size:2.2rem}
        }
        @media(max-width:768px){
            :root{--header-h:150px}
            .topbar .inner{flex-wrap:wrap;gap:10px}
            .brand{font-size:1.25rem}
            .searchbar{order:3;flex-basis:100%;max-width:100%}
            .h-actions{margin-right:auto}
            .h-action{padding:6px 8px}
            .h-action .lbl{display:none}
            .hero-inner{padding:32px 20px}
            .hero h1{font-size:1.8rem}
            .hero p{font-size:.95rem}
            .page-title{font-size:1.35rem}
            .panel{padding:18px}
            .subbar{display:none}
        }
        @media(max-width:480px){
            .brand-name .brand-sub{display:none}
            .hero h1{font-size:1.55rem}
            .empty-state{padding:44px 14px}
        }
    </style>
</head>
<body>
    <header class="site-header" id="siteHeader">
        <div class="topbar">
            <div class="container inner">
                <a class="brand" href="{{ url_for('home') }}" dir="ltr">
                    <span class="dot"></span>
                    <span class="brand-name" dir="ltr" style="unicode-bidi:isolate;">
                        <span>Mo<span style="color:var(--accent)">.</span>palace</span>
                        <span class="brand-sub">CAR PARTS</span>
                    </span>
                </a>
                <form class="searchbar" action="{{ url_for('home') }}" method="get" id="searchForm" onsubmit="return doSearch(event)">
                    <input type="text" name="q" id="globalSearch" placeholder="ابحث عن قطع غيار وإكسسوارات سيارتك..." value="{{ request.args.get('q','') }}">
                    <button type="submit"><i class="bi bi-search"></i></button>
                </form>
                <div class="h-actions">
                    {% if is_customer %}
                        <a class="h-action" href="{{ url_for('my_orders') }}"><i class="bi bi-box-seam"></i><span class="lbl"><span>الشحنات</span><b>طلباتي</b></span></a>
                        <a class="h-action" href="{{ url_for('account') }}"><i class="bi bi-person-circle"></i><span class="lbl"><span>{{ customer_name }}</span><b>حسابي</b></span></a>
                        <a class="h-action" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right"></i><span class="lbl"><span>تسجيل</span><b>خروج</b></span></a>
                    {% else %}
                        <a class="h-action" href="{{ url_for('login') }}"><i class="bi bi-person"></i><span class="lbl"><span>مرحباً</span><b>دخول / تسجيل</b></span></a>
                    {% endif %}
                    <a class="h-action" href="{{ url_for('view_cart') }}">
                        <i class="bi bi-cart2"></i><span class="lbl"><span>العربة</span><b>السلة</b></span>
                        {% set cart_count = session.get('cart', {}) | length %}
                        {% if cart_count > 0 %}<span class="cart-count num">{{ cart_count }}</span>{% endif %}
                    </a>
                </div>
            </div>
        </div>
        <div class="subbar">
            <div class="container inner">
                <a href="{{ url_for('home') }}"><i class="bi bi-grid-fill"></i> كل المنتجات</a>
                <span><i class="bi bi-truck"></i> شحن سريع لكل المحافظات</span>
                <span><i class="bi bi-shield-check"></i> ضمان الجودة</span>
                <span><i class="bi bi-arrow-return-left"></i> استرجاع خلال 14 يوم</span>
            </div>
        </div>
    </header>

    <main class="container my-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% for category, message in messages %}
                <div class="alert alert-{{ category }} alert-dismissible fade show mb-3">
                    <i class="bi bi-{% if category == 'success' %}check-circle-fill{% elif category == 'danger' %}exclamation-triangle-fill{% elif category == 'warning' %}exclamation-circle-fill{% else %}info-circle-fill{% endif %} me-2"></i>
                    {{ message }}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            {% endfor %}
        {% endwith %}
        {{ content | safe }}
    </main>

    <footer class="site-footer">
        <div class="container d-flex flex-wrap justify-content-between align-items-center gap-2">
            <div class="brand" style="font-size:1.2rem;" dir="ltr">
                <span class="dot"></span>
                <span dir="ltr" style="unicode-bidi:isolate;">Mo<span style="color:var(--accent)">.</span>palace</span>
            </div>
            <span style="font-size:.85rem;">قطع غيار وإكسسوار سيارات &copy; 2026</span>
            <a href="{{ url_for('admin_login') }}" style="font-size:.82rem;"><i class="bi bi-lock me-1"></i>لوحة التحكم</a>
        </div>
    </footer>

    <a href="{{ url_for('support') }}" class="chat-fab" title="مساعدة / محادثة">
        <i class="bi bi-chat-dots-fill"></i>
        <span class="cnt num" id="chatFabBadge" {% if not (unread_user and unread_user > 0) %}style="display:none;"{% endif %}>{{ unread_user }}</span>
    </a>

    <div class="toast-custom" id="customToast"><i class="bi bi-check-circle-fill"></i><span id="toastMsg"></span></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>
    <script>
    const obs=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('visible');obs.unobserve(e.target)}}),{threshold:.06});
    document.querySelectorAll('.fade-up').forEach(el=>obs.observe(el));
    function showToast(m){const t=document.getElementById('customToast');document.getElementById('toastMsg').textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000)}
    function doSearch(e){
        const grid=document.getElementById('productGrid');
        const val=document.getElementById('globalSearch').value.trim();
        if(grid){e.preventDefault();filterProducts(val);return false;}
        return true;
    }
    function filterProducts(q){
        q=(q||'').toLowerCase();
        let shown=0;
        document.querySelectorAll('#productGrid [data-name]').forEach(c=>{
            const match=c.getAttribute('data-name').toLowerCase().includes(q);
            c.style.display=match?'':'none';if(match)shown++;
        });
        const empty=document.getElementById('noResults');
        if(empty)empty.style.display=shown?'none':'block';
    }
    document.addEventListener('DOMContentLoaded',function(){
        const params=new URLSearchParams(location.search);
        const q=params.get('q');
        if(q&&document.getElementById('productGrid'))filterProducts(q);
    });
    (function(){
        const badge=document.getElementById('chatFabBadge');
        if(!badge)return;
        async function pollNotify(){
            try{
                const r=await fetch('{{ url_for("notify_count") }}');
                const d=await r.json();
                if(d.count>0){badge.textContent=d.count;badge.style.display='';}
                else{badge.style.display='none';}
            }catch(e){}
        }
        setInterval(pollNotify,5000);
    })();
    </script>
    {% if scripts %}{{ scripts | safe }}{% endif %}
</body>
</html>'''

ADMIN_BASE = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800;900&family=Cairo:wght@600;700;800;900&display=swap" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css" rel="stylesheet">
    <style>
        *,*::before,*::after{box-sizing:border-box}
        :root{--brand:#111c2e;--accent:#ff7a00;--accent-dark:#e56a00;--accent-soft:#fff2e6;--price:#e34a1f;--ink:#0f1720;--ink-2:#4b5563;--muted:#8b95a3;--bg:#f3f4f6;--surface:#ffffff;--surface-2:#f8f9fb;--line:#e4e7ec;--ok:#1a9e5e;--ok-soft:#e6f6ee;--warn-soft:#fdf3d9;--radius:14px}
        ::-webkit-scrollbar{width:9px}::-webkit-scrollbar-thumb{background:#c7ccd4;border-radius:9px}
        html{background:var(--bg)}
        body{background:var(--bg);color:var(--ink);font-family:'Tajawal',sans-serif;min-height:100vh}
        .num{font-family:'Cairo','Tajawal',sans-serif}
        .navbar{background:var(--brand);padding:15px 0}
        .navbar-brand{color:#fff!important;font-family:'Cairo',sans-serif;font-weight:800;font-size:1.2rem;display:flex;align-items:center;gap:9px}
        .navbar-brand .dot{width:10px;height:10px;border-radius:50%;background:var(--accent);display:inline-block}
        .btn-accent{background:var(--accent);color:#fff;font-weight:700;border-radius:11px;border:none;transition:.25s}
        .btn-accent:hover{background:var(--accent-dark);color:#fff;transform:translateY(-1px);box-shadow:0 6px 16px rgba(255,122,0,.3)}
        .btn-light-ghost{background:rgba(255,255,255,.12);color:#fff;border:none;border-radius:10px;font-weight:600;transition:.25s;position:relative}
        .btn-light-ghost:hover{background:rgba(255,255,255,.22);color:#fff}
        .nav-badge{position:absolute;top:-6px;right:-6px;background:var(--price);color:#fff;font-size:.62rem;font-weight:800;min-width:18px;height:18px;padding:0 4px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;font-family:'Cairo',sans-serif}
        .table-clean{background:var(--surface);color:var(--ink);border-radius:var(--radius);overflow:hidden;border:1px solid var(--line)}
        .table-clean thead{background:var(--surface-2)}
        .table-clean thead th{border-bottom:1px solid var(--line);color:var(--ink-2);font-weight:700;padding:13px 14px;font-size:.83rem}
        .table-clean tbody td{border-color:#eef0f3;padding:12px 14px;vertical-align:middle}
        .table-clean tbody tr:hover{background:var(--surface-2)}
        .form-control,.form-select{background:var(--surface)!important;border:1.5px solid var(--line)!important;color:var(--ink)!important;border-radius:11px!important;padding:11px 14px!important;transition:.25s!important;font-family:'Tajawal',sans-serif!important}
        .form-control:focus,.form-select:focus{border-color:var(--accent)!important;box-shadow:0 0 0 4px var(--accent-soft)!important}
        .form-label{color:var(--ink);font-weight:700;font-size:.86rem;margin-bottom:5px}
        .alert{border-radius:var(--radius);border:1px solid var(--line);font-weight:600}
        .alert-success{background:var(--ok-soft);border-color:#bfe6cf;color:#137a48}
        .alert-danger{background:#fdeaea;border-color:#f5c2c2;color:#c0392b}
        .alert-warning{background:var(--warn-soft);border-color:#f0dca0;color:#8a6300}
        .alert-info{background:#e8f1fd;border-color:#c3dbf7;color:#1c5aa8}
        .section-title{color:var(--ink);font-family:'Cairo',sans-serif;font-weight:800;font-size:1.15rem;margin-bottom:16px;display:flex;align-items:center;gap:8px}
        .section-title i{color:var(--accent)}
        .stat-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:22px;transition:.25s;height:100%}
        .stat-card:hover{box-shadow:0 10px 26px rgba(16,23,32,.1);transform:translateY(-3px)}
        .stat-card .stat-num{font-family:'Cairo',sans-serif;font-size:2rem;font-weight:800;color:var(--ink)}
        .stat-card .stat-ico{width:46px;height:46px;border-radius:13px;background:var(--accent-soft);color:var(--accent);display:inline-flex;align-items:center;justify-content:center;font-size:1.35rem;margin-bottom:14px}
        .stat-card .stat-label{color:var(--muted);font-size:.85rem;margin-top:3px}
        .glass-form{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:26px}
        .badge-confirmed{background:var(--ok-soft);color:var(--ok);padding:5px 12px;border-radius:16px;font-weight:800;font-size:.78rem}
        .badge-pending{background:var(--warn-soft);color:#8a6300;padding:5px 12px;border-radius:16px;font-weight:800;font-size:.78rem}
        .badge-rejected{background:#fdeaea;color:#c0392b;padding:5px 12px;border-radius:16px;font-weight:800;font-size:.78rem}
        .btn-outline-secondary{color:var(--ink-2);border-color:var(--line)}
        .btn-outline-secondary:hover{background:var(--surface-2);color:var(--ink);border-color:#cfd4dc}
        .cropper-container{touch-action:none}
        .chat-box{background:var(--surface-2);border:1px solid var(--line);border-radius:var(--radius);height:46vh;min-height:280px;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
        .msg{max-width:80%;padding:10px 14px;border-radius:15px;font-size:.9rem;line-height:1.6;word-break:break-word}
        .chat-media-img{max-width:220px;max-height:240px;border-radius:12px;display:block;margin:2px 0;cursor:pointer;object-fit:cover}
        .chat-media-audio{width:230px;max-width:100%;height:40px;margin:2px 0;display:block}
        .chat-input-form{margin-top:12px}
        .chat-input-row{display:flex;gap:8px;align-items:center}
        .chat-tool-btn{width:44px;height:44px;flex:0 0 auto;border-radius:11px;border:1.5px solid var(--line);background:var(--surface);color:var(--brand);display:inline-flex;align-items:center;justify-content:center;font-size:1.15rem;padding:0;transition:var(--t)}
        .chat-tool-btn:hover{border-color:var(--accent);color:var(--accent)}
        .chat-tool-btn.recording{background:var(--accent);color:#fff;border-color:var(--accent);animation:recPulse 1s infinite}
        @keyframes recPulse{0%,100%{box-shadow:0 0 0 0 rgba(255,122,0,.5)}50%{box-shadow:0 0 0 6px rgba(255,122,0,0)}}
        .chat-send-btn{width:46px;height:44px;flex:0 0 auto;border-radius:11px;padding:0;display:inline-flex;align-items:center;justify-content:center}
        .chat-preview-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
        .chat-preview-bar .prev-item{position:relative}
        .chat-preview-bar .prev-item img{width:64px;height:64px;object-fit:cover;border-radius:10px;border:1px solid var(--line)}
        .chat-preview-bar .prev-item.voice audio{height:38px}
        .chat-preview-bar .prev-item button{position:absolute;top:-8px;inset-inline-end:-8px;width:22px;height:22px;border-radius:50%;border:none;background:var(--price);color:#fff;font-size:.9rem;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center}
        .chat-rec-bar{display:flex;align-items:center;gap:12px;margin-bottom:10px;padding:8px 12px;background:var(--surface);border:1.5px solid var(--line);border-radius:26px;color:var(--price);font-weight:700;font-size:.9rem;box-shadow:var(--shadow-sm)}
        .chat-rec-bar .rec-dot{width:11px;height:11px;border-radius:50%;background:var(--price);flex:0 0 auto;animation:recPulse 1s infinite}
        .chat-rec-bar .rec-time{font-size:.95rem;min-width:44px;color:var(--ink)}
        .chat-rec-bar .rec-wave{flex:1;display:flex;align-items:center;justify-content:center;gap:3px;height:26px;overflow:hidden}
        .chat-rec-bar .rec-wave span{display:block;width:3px;height:6px;border-radius:3px;background:var(--accent);animation:recWave 1s ease-in-out infinite}
        .chat-rec-bar .rec-wave span:nth-child(2n){animation-duration:.85s}
        .chat-rec-bar .rec-wave span:nth-child(3n){animation-duration:1.15s}
        .chat-rec-bar .rec-wave span:nth-child(4n){animation-duration:.7s}
        @keyframes recWave{0%,100%{height:6px;opacity:.5}50%{height:22px;opacity:1}}
        .chat-rec-bar .rec-cancel,.chat-rec-bar .rec-send{width:40px;height:40px;flex:0 0 auto;border:none;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:1.05rem;cursor:pointer;transition:var(--t)}
        .chat-rec-bar .rec-cancel{background:var(--surface-2);color:var(--price);border:1.5px solid var(--line)}
        .chat-rec-bar .rec-cancel:hover{background:#fdeaea;border-color:#f5c2c2}
        .chat-rec-bar .rec-send{background:var(--accent);color:#fff}
        .chat-rec-bar .rec-send:hover{background:var(--accent-dark);transform:scale(1.05)}
        /* ===== مشغّل الصوت (شكل واتساب) ===== */
        .voice-player{display:inline-flex;align-items:center;gap:10px;background:rgba(15,23,32,.05);border-radius:22px;padding:6px 14px 6px 6px;min-width:210px;max-width:270px;margin:2px 0}
        .msg.admin .voice-player{background:rgba(255,255,255,.18)}
        .voice-player .vp-play{width:38px;height:38px;flex:0 0 auto;border:none;border-radius:50%;background:var(--accent);color:#fff;display:inline-flex;align-items:center;justify-content:center;font-size:1.1rem;cursor:pointer;transition:var(--t)}
        .voice-player .vp-play:hover{background:var(--accent-dark)}
        .msg.admin .voice-player .vp-play{background:#fff;color:var(--brand)}
        .voice-player .vp-track{flex:1;height:5px;border-radius:5px;background:rgba(15,23,32,.15);position:relative;cursor:pointer}
        .msg.admin .voice-player .vp-track{background:rgba(255,255,255,.35)}
        .voice-player .vp-progress{position:absolute;inset-block:0;inset-inline-start:0;width:0;background:var(--accent);border-radius:5px}
        .msg.admin .voice-player .vp-progress{background:#fff}
        .voice-player .vp-time{font-size:.72rem;opacity:.8;min-width:34px;text-align:center}
        /* ===== مكالمة صوتية (شكل ديسكورد) ===== */
        .call-btn{display:inline-flex;align-items:center;gap:8px;border:1.5px solid var(--line);background:var(--surface);color:var(--ink);border-radius:12px;padding:7px 14px;font-weight:700;font-size:.85rem;cursor:pointer;transition:var(--t)}
        .call-btn:hover{border-color:var(--accent);color:var(--accent)}
        .call-btn.peer-online{border-color:var(--accent);color:var(--accent)}
        .call-btn .call-presence{width:9px;height:9px;border-radius:50%;background:var(--muted);flex:0 0 auto;box-shadow:0 0 0 0 rgba(0,0,0,0)}
        .call-btn .call-presence.online{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.22);animation:presPulse 2s infinite}
        @keyframes presPulse{0%,100%{box-shadow:0 0 0 2px rgba(34,197,94,.25)}50%{box-shadow:0 0 0 5px rgba(34,197,94,0)}}
        .call-overlay{position:fixed;inset:0;z-index:3000;display:none;align-items:center;justify-content:center;background:rgba(8,12,18,.72);backdrop-filter:blur(6px)}
        .call-overlay.show{display:flex;animation:callFade .2s ease}
        @keyframes callFade{from{opacity:0}to{opacity:1}}
        .call-modal{width:min(92vw,340px);background:var(--surface);border:1px solid var(--line);border-radius:24px;padding:34px 26px 26px;text-align:center;box-shadow:0 24px 60px rgba(0,0,0,.45)}
        .call-avatar{position:relative;width:104px;height:104px;margin:0 auto 18px;border-radius:50%;background:linear-gradient(145deg,var(--accent),var(--accent-dark));color:#fff;display:flex;align-items:center;justify-content:center;font-size:2.4rem;font-weight:800}
        .call-avatar .call-ring{position:absolute;inset:-6px;border-radius:50%;border:3px solid var(--accent);opacity:0}
        .call-avatar.pulsing .call-ring{animation:callRing 1.5s ease-out infinite}
        @keyframes callRing{0%{transform:scale(1);opacity:.6}100%{transform:scale(1.35);opacity:0}}
        .call-peer-name{font-size:1.25rem;font-weight:800;color:var(--ink);margin-bottom:4px}
        .call-status{color:var(--muted);font-size:.92rem;min-height:22px}
        .call-timer{font-size:1.05rem;font-weight:800;color:var(--accent);margin-top:6px}
        .call-actions{display:flex;align-items:center;justify-content:center;gap:22px;margin-top:24px}
        .call-ic{width:60px;height:60px;border:none;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:1.5rem;color:#fff;cursor:pointer;transition:var(--t)}
        .call-ic:hover{transform:translateY(-2px) scale(1.05)}
        .call-accept{background:#22c55e}
        .call-decline{background:#ef4444}
        .call-mute{background:var(--surface-2);color:var(--ink);border:1.5px solid var(--line)}
        .call-mute:hover{background:var(--line)}
        .call-spk{background:var(--surface-2);color:var(--ink);border:1.5px solid var(--line)}
        .call-spk:hover{background:var(--line)}
        .call-spk.on{background:var(--accent);color:#fff;border-color:var(--accent)}
        .msg .time{display:block;font-size:.64rem;opacity:.6;margin-top:4px}
        .msg.user{align-self:flex-start;background:#fff;border:1px solid var(--line);color:var(--ink);border-bottom-right-radius:5px}
        .msg.admin{align-self:flex-end;background:var(--brand);color:#fff;border-bottom-left-radius:5px}
        .chat-empty{margin:auto;text-align:center;color:var(--muted)}
        @media(max-width:768px){.navbar-brand{font-size:1rem}}
    </style>
</head>
<body>
    <nav class="navbar navbar-dark mb-4">
        <div class="container d-flex justify-content-between align-items-center flex-wrap gap-2">
            <a href="{{ url_for('admin_dashboard') }}" class="navbar-brand"><span class="dot"></span> لوحة التحكم</a>
            <div class="d-flex gap-2 flex-wrap">
                {% if current_user.is_authenticated %}
                <a href="{{ url_for('admin_customers') }}" class="btn btn-light-ghost btn-sm"><i class="bi bi-people"></i> العملاء</a>
                <a href="{{ url_for('admin_chats') }}" class="btn btn-light-ghost btn-sm"><i class="bi bi-chat-dots"></i> المحادثات<span class="nav-badge num" id="navBadgeCustomers" {% if not (admin_unread and admin_unread > 0) %}style="display:none;"{% endif %}>{{ admin_unread }}</span></a>
                <a href="{{ url_for('admin_guest_chats') }}" class="btn btn-light-ghost btn-sm"><i class="bi bi-person-badge"></i> الزوّار<span class="nav-badge num" id="navBadgeGuests" {% if not (admin_unread_guests and admin_unread_guests > 0) %}style="display:none;"{% endif %}>{{ admin_unread_guests }}</span></a>
                <a href="{{ url_for('admin_returns') }}" class="btn btn-light-ghost btn-sm"><i class="bi bi-arrow-return-left"></i> الاسترجاع</a>
                {% endif %}
                <a href="{{ url_for('home') }}" class="btn btn-light-ghost btn-sm"><i class="bi bi-shop"></i> المتجر</a>
                {% if current_user.is_authenticated %}
                <a href="{{ url_for('admin_logout') }}" class="btn btn-light-ghost btn-sm"><i class="bi bi-box-arrow-right"></i> خروج</a>
                {% endif %}
            </div>
        </div>
    </nav>
    <div class="container pb-5">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% for category, message in messages %}
            <div class="alert alert-{{ category }} alert-dismissible fade show mb-3">
                <i class="bi bi-{% if category == 'success' %}check-circle-fill{% elif category == 'danger' %}exclamation-triangle-fill{% elif category == 'warning' %}exclamation-circle-fill{% else %}info-circle-fill{% endif %} me-2"></i>
                {{ message }}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
          {% endfor %}
        {% endwith %}
        {{ content | safe }}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>
    {% if current_user.is_authenticated %}
    <script>
    (function(){
        function setBadge(id,n){
            const el=document.getElementById(id);
            if(!el)return;
            if(n>0){el.textContent=n;el.style.display='';}else{el.style.display='none';}
        }
        async function pollNotify(){
            try{
                const r=await fetch('{{ url_for("admin_notify_count") }}');
                const d=await r.json();
                setBadge('navBadgeCustomers',d.customers);
                setBadge('navBadgeGuests',d.guests);
            }catch(e){}
        }
        setInterval(pollNotify,5000);
    })();
    </script>
    {% endif %}
    {% if scripts %}{{ scripts | safe }}{% endif %}
</body>
</html>'''

# ====================== دوال المحتوى ======================
def home_page():
    products = Product.query.all()
    hero = f'''
    <div class="hero fade-up">
        <img src="{url_for('static', filename='img/hero.png')}" class="hero-img" alt="" onerror="this.style.display='none'">
        <div class="hero-inner">
            <span class="eyebrow"><i class="bi bi-lightning-charge-fill"></i> عروض 2026</span>
            <h1 class="mt-3">كل ما تحتاجه <span class="hl">سيارتك</span><br>في مكان واحد</h1>
            <p>قطع غيار وإكسسوارات أصلية بأفضل الأسعار، مع شحن سريع ودفع آمن وضمان استرجاع.</p>
            <a href="#products" class="btn btn-accent"><i class="bi bi-bag-fill me-2"></i>تسوّق الآن</a>
            <div class="hero-stats">
                <div class="stat-chip"><div class="s-num num">+{max(len(products),1)}</div><div class="s-label">منتج متاح</div></div>
                <div class="stat-chip"><div class="s-num num">24/7</div><div class="s-label">دعم العملاء</div></div>
                <div class="stat-chip"><div class="s-num num">100%</div><div class="s-label">ضمان الجودة</div></div>
            </div>
        </div>
    </div>'''
    if not products:
        empty = ('<div class="empty-state"><div class="ico"><i class="bi bi-box-seam"></i></div>'
                 '<h4>لا توجد منتجات بعد</h4><p style="color:var(--muted)">سيتم إضافة المنتجات قريباً</p></div>')
        return render_template_string(BASE_HTML, title='Mo.palace - متجر قطع غيار السيارات', content=Markup(hero + empty))
    cards = ''
    for p in products:
        detail_url = url_for('product_page', pid=p.id)
        cart_url = url_for('add_to_cart', pid=p.id)
        img_src = url_for('static', filename='uploads/' + p.main_image) + '?t=' + str(datetime.utcnow().timestamp())
        avg, count = get_rating(p)
        if count:
            rating_html = f'''<div class="rating-line">{stars_html(avg)}<span class="rcount">{avg} ({count})</span></div>'''
        else:
            rating_html = '''<div class="rating-line"><span class="no-rate"><i class="bi bi-star"></i> لا تقييمات بعد</span></div>'''
        cards += f'''<div class="col-6 col-md-4 col-lg-3" data-name="{p.name}">
            <div class="product-card fade-up">
                <div class="img-wrap">
                    <span class="ship-tag"><i class="bi bi-truck"></i> شحن سريع</span>
                    <img src="{img_src}" alt="{p.name}" onclick="location.href='{detail_url}'">
                </div>
                <div class="card-body">
                    <a href="{detail_url}" style="text-decoration:none;"><div class="p-name">{p.name}</div></a>
                    {rating_html}
                    <div class="mt-auto">
                        <div class="p-price num">{p.price:.0f} <span>ج.م</span></div>
                        <a href="{cart_url}" class="btn-cart" onclick="event.preventDefault(); showToast('تمت الإضافة إلى العربة'); setTimeout(function(){{location.href='{cart_url}'}}, 500);"><i class="bi bi-cart-plus"></i> أضف إلى العربة</a>
                    </div>
                </div>
            </div>
        </div>'''
    content = f'''{hero}
    <div id="products" class="d-flex justify-content-between align-items-center mb-3">
        <h2 class="page-title mb-0"><i class="bi bi-grid-1x2-fill"></i> كل المنتجات</h2>
        <span style="color:var(--muted);font-weight:700;">{len(products)} منتج</span>
    </div>
    <div class="row g-3 g-md-4" id="productGrid">{cards}</div>
    <div id="noResults" class="empty-state" style="display:none;">
        <div class="ico"><i class="bi bi-search"></i></div>
        <h4>لا توجد نتائج</h4><p style="color:var(--muted)">جرّب كلمة بحث أخرى</p>
    </div>'''
    return render_template_string(BASE_HTML, title='Mo.palace - متجر قطع غيار السيارات', content=Markup(content))

def product_detail_page(pid):
    product = db.session.get(Product, pid)
    if not product:
        return "المنتج غير موجود", 404
    reviews = product.reviews.order_by(Review.timestamp.desc()).all()
    avg, count = get_rating(product)

    cust = current_customer()
    already_reviewed = False
    has_purchased = False
    if cust:
        already_reviewed = Review.query.filter_by(product_id=pid, customer_id=cust.id).first() is not None
        has_purchased = db.session.query(OrderItem.id).join(Order).filter(
            Order.customer_id == cust.id, OrderItem.product_id == pid).first() is not None
    can_review = cust is not None and has_purchased and not already_reviewed
    extra_images = product.extra_images.all()

    images_js = f'"{url_for("static", filename="uploads/" + product.main_image)}"'
    thumbnails = ''
    for idx, img in enumerate(extra_images):
        images_js += f', "{url_for("static", filename="uploads/" + img.filename)}"'
        thumbnails += f'<div class="col-3 col-md-2"><img src="{url_for("static", filename="uploads/" + img.filename)}" class="thumb-img" onclick="openLightbox({idx+1})" onerror="this.style.display=\'none\'"></div>'

    review_html = ''
    for r in reviews:
        review_html += f'''<div class="review-card fade-up">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <strong style="color:var(--ink);"><i class="bi bi-person-circle me-1" style="color:var(--accent)"></i>{r.author}</strong>
                <small style="color:var(--muted)">{r.timestamp.strftime('%Y-%m-%d')}</small>
            </div>
            <div class="mb-2">{stars_html(r.rating, '.9rem')}</div>
            <p class="mb-0" style="color:var(--ink-2); line-height:1.8;">{r.body}</p>
        </div>'''
    if not reviews:
        review_html = '<div class="text-center py-4"><i class="bi bi-chat-square-heart" style="font-size:2rem; color:var(--accent);"></i><p style="color:var(--muted)" class="mt-2">لا توجد تقييمات بعد. كن أول من يقيّم!</p></div>'

    review_form = ''
    if can_review:
        review_form = f'''
        <div class="panel mt-4 fade-up">
            <h5 style="color:var(--ink); font-weight:800; margin-bottom:16px; font-family:'Cairo',sans-serif;"><i class="bi bi-star-fill me-1" style="color:var(--accent)"></i> أضف تقييمك</h5>
            <form method="POST" action="{url_for('add_review', pid=product.id)}">
                <div class="mb-3">
                    <label class="form-label d-block">تقييمك بالنجوم</label>
                    <div class="rate-input">
                        <input type="radio" name="rating" id="star5" value="5" checked><label for="star5"><i class="bi bi-star-fill"></i></label>
                        <input type="radio" name="rating" id="star4" value="4"><label for="star4"><i class="bi bi-star-fill"></i></label>
                        <input type="radio" name="rating" id="star3" value="3"><label for="star3"><i class="bi bi-star-fill"></i></label>
                        <input type="radio" name="rating" id="star2" value="2"><label for="star2"><i class="bi bi-star-fill"></i></label>
                        <input type="radio" name="rating" id="star1" value="1"><label for="star1"><i class="bi bi-star-fill"></i></label>
                    </div>
                </div>
                <div class="row g-3">
                    <div class="col-md-8"><textarea name="body" class="form-control" rows="2" placeholder="شاركنا رأيك في المنتج..." required></textarea></div>
                </div>
                <button class="btn btn-accent mt-3"><i class="bi bi-send me-1"></i> إرسال التقييم</button>
            </form>
        </div>'''
    elif already_reviewed:
        review_form = '<div class="alert alert-info mt-4 fade-up"><i class="bi bi-check-circle me-1"></i> لقد قمت بتقييم هذا المنتج بالفعل. شكراً لك!</div>'
    elif cust and not has_purchased:
        review_form = '<div class="alert alert-info mt-4 fade-up"><i class="bi bi-info-circle me-1"></i> يمكنك تقييم هذا المنتج بعد شرائه.</div>'
    elif not cust:
        review_form = f'<div class="alert alert-info mt-4 fade-up"><i class="bi bi-info-circle me-1"></i> <a href="{url_for("login")}" style="font-weight:800;color:var(--accent-dark)">سجّل الدخول</a> بعد الشراء لتتمكن من التقييم.</div>'

    if count:
        rating_summary = f'''<div class="d-flex align-items-center gap-2 mb-3">{stars_html(avg, '.95rem')}<span style="color:var(--muted);font-family:'Cairo',sans-serif;">{avg} من 5 ({count} تقييم)</span></div>'''
    else:
        rating_summary = '''<div class="mb-3"><span style="color:var(--muted);"><i class="bi bi-star me-1"></i>لا توجد تقييمات بعد</span></div>'''

    content = f'''
    <nav aria-label="breadcrumb" class="mb-3 fade-up">
        <ol class="breadcrumb" style="font-size:.85rem;">
            <li class="breadcrumb-item"><a href="{url_for('home')}">الرئيسية</a></li>
            <li class="breadcrumb-item active">{product.name}</li>
        </ol>
    </nav>
    <div class="row g-4 fade-up">
        <div class="col-lg-7">
            <div class="panel">
                <img src="{url_for('static', filename='uploads/' + product.main_image)}?t={datetime.utcnow().timestamp()}" class="detail-img-main" id="mainDetailImg" onclick="openLightbox(0)">
                {f'<div class="row mt-3 g-2">{thumbnails}</div>' if thumbnails else ''}
            </div>
        </div>
        <div class="col-lg-5">
            <div class="panel h-100 d-flex flex-column">
                <span class="eyebrow mb-3" style="align-self:flex-start;"><i class="bi bi-car-front-fill"></i> إكسسوار سيارات</span>
                <h1 style="font-family:'Cairo',sans-serif; font-weight:800; color:var(--ink); font-size:1.7rem; margin-bottom:10px; line-height:1.4;">{product.name}</h1>
                {rating_summary}
                <p style="color:var(--ink-2); line-height:2; margin-bottom:20px;">{product.description}</p>
                <div class="soft-line" style="margin:6px 0 18px;"></div>
                <div style="margin-bottom:20px;">
                    <span style="font-size:.85rem; color:var(--muted);">السعر شامل الضريبة</span>
                    <div class="num" style="font-weight:800; font-size:2.3rem; color:var(--price); line-height:1.2;">{product.price:.0f} <span style="font-size:1rem; font-weight:600; color:var(--muted); font-family:'Tajawal',sans-serif;">ج.م</span></div>
                </div>
                <a href="{url_for('add_to_cart', pid=product.id)}" class="btn btn-accent btn-lg" style="padding:14px 24px;"><i class="bi bi-cart-plus me-2"></i>أضف إلى العربة</a>
                <div class="d-flex flex-wrap gap-4 mt-4">
                    <div class="trust"><i class="bi bi-truck"></i> توصيل سريع</div>
                    <div class="trust"><i class="bi bi-shield-check"></i> ضمان الجودة</div>
                    <div class="trust"><i class="bi bi-arrow-return-left"></i> استرجاع سهل</div>
                </div>
            </div>
        </div>
    </div>

    <div class="lightbox" id="lightbox">
        <span class="lb-close" onclick="closeLightbox()"><i class="bi bi-x-lg"></i></span>
        <button class="lb-prev" onclick="changeImage(-1)"><i class="bi bi-chevron-right"></i></button>
        <button class="lb-next" onclick="changeImage(1)"><i class="bi bi-chevron-left"></i></button>
        <img id="lightboxImg">
    </div>

    <div class="soft-line"></div>
    <h3 class="page-title fade-up"><i class="bi bi-chat-square-quote-fill"></i> التقييمات</h3>
    <div class="mt-3">{review_html}</div>
    {review_form}'''

    scripts = f'''<script>
        const images = [{images_js}];
        let currentIndex = 0;
        function openLightbox(i){{currentIndex=i;document.getElementById('lightbox').classList.add('active');document.getElementById('lightboxImg').src=images[currentIndex];document.body.style.overflow='hidden'}}
        function closeLightbox(){{document.getElementById('lightbox').classList.remove('active');document.body.style.overflow=''}}
        function changeImage(d){{currentIndex=(currentIndex+d+images.length)%images.length;document.getElementById('lightboxImg').src=images[currentIndex]}}
        document.addEventListener('keydown',function(e){{
            if(document.getElementById('lightbox').classList.contains('active')){{
                if(e.key==='ArrowLeft')changeImage(1);else if(e.key==='ArrowRight')changeImage(-1);else if(e.key==='Escape')closeLightbox();
            }}
        }});
        document.getElementById('lightbox').addEventListener('click',function(e){{if(e.target===this)closeLightbox()}});
    </script>'''
    return render_template_string(BASE_HTML, title=f'{product.name} - Mo.palace', content=Markup(content), scripts=Markup(scripts))

def cart_page():
    items, total = get_cart_info()
    if not items:
        content = f'''<div class="empty-state">
            <div class="ico"><i class="bi bi-cart-x"></i></div>
            <h4>العربة فارغة</h4>
            <p style="color:var(--muted)" class="mb-3">لم تضف أي منتجات بعد</p>
            <a href="{url_for('home')}" class="btn btn-accent"><i class="bi bi-grid-1x2-fill me-1"></i> تصفح المنتجات</a>
        </div>'''
    else:
        rows = ''.join(
            f'''<tr>
                <td><img src="{url_for('static', filename='uploads/' + it['product'].main_image)}" class="cart-img"></td>
                <td><strong>{it['product'].name}</strong></td>
                <td>
                    <div class="qty-control">
                        <a href="{url_for('cart_decrease', pid=it['product'].id)}" class="qty-btn" title="{'إزالة' if it['qty'] == 1 else 'نقصان'}">{'<i class="bi bi-trash"></i>' if it['qty'] == 1 else '<i class="bi bi-dash-lg"></i>'}</a>
                        <span class="qty-val num">{it['qty']}</span>
                        <a href="{url_for('cart_increase', pid=it['product'].id)}" class="qty-btn" title="زيادة"><i class="bi bi-plus-lg"></i></a>
                    </div>
                </td>
                <td style="color:var(--ink-2)" class="num">{it['product'].price:.0f} ج.م</td>
                <td><strong style="color:var(--price);" class="num">{it['subtotal']:.0f} ج.م</strong></td>
                <td><a href="{url_for('cart_remove', pid=it['product'].id)}" class="btn-icon-del" title="إزالة المنتج" onclick="return confirm('إزالة هذا المنتج من العربة؟')"><i class="bi bi-x-lg"></i></a></td>
            </tr>''' for it in items
        )
        content = f'''
        <h2 class="page-title fade-up"><i class="bi bi-cart-fill"></i> عربة التسوق</h2>
        <div class="table-responsive fade-up">
            <table class="table table-borderless align-middle table-clean mb-0">
                <thead><tr><th style="width:88px;">الصورة</th><th>المنتج</th><th style="text-align:center;">الكمية</th><th>السعر</th><th>الإجمالي</th><th></th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        <div class="panel mt-4 fade-up d-flex flex-wrap justify-content-between align-items-center gap-3">
            <div>
                <span style="color:var(--muted);">الإجمالي الكلي</span>
                <div class="num" style="font-weight:800; font-size:1.9rem; color:var(--price);">{total:.0f} <span style="font-size:.9rem; font-weight:600; color:var(--muted); font-family:'Tajawal',sans-serif;">ج.م</span></div>
            </div>
            <div class="d-flex gap-2">
                <a href="{url_for('home')}" class="btn btn-ghost"><i class="bi bi-arrow-right me-1"></i> متابعة التسوق</a>
                <a href="{url_for('checkout')}" class="btn btn-accent btn-lg" style="padding:13px 30px;"><i class="bi bi-credit-card-2-front me-2"></i>إتمام الشراء</a>
            </div>
        </div>'''
    return render_template_string(BASE_HTML, title='العربة - Mo.palace', content=Markup(content))

def checkout_page(cust):
    if not session.get('cart'):
        flash('العربة فارغة', 'warning')
        return redirect(url_for('home'))
    items, total = get_cart_info()
    summary_rows = ''.join(
        f'''<div class="d-flex justify-content-between align-items-center mb-2" style="font-size:.9rem;">
            <span style="color:var(--ink-2)">{it['product'].name} <span style="color:var(--muted)">×{it['qty']}</span></span>
            <strong class="num">{it['subtotal']:.0f} ج.م</strong>
        </div>''' for it in items
    )
    content = f'''
    <h2 class="page-title fade-up"><i class="bi bi-credit-card-2-front-fill"></i> إتمام الطلب</h2>
    <div class="row g-4">
        <div class="col-lg-8">
            <div class="panel fade-up">
                <form method="POST" id="checkoutForm" enctype="multipart/form-data">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 style="color:var(--ink); font-weight:800; margin:0; font-family:'Cairo',sans-serif;"><i class="bi bi-person-vcard me-1" style="color:var(--accent)"></i> بيانات الشحن</h5>
                        <span class="form-text"><i class="bi bi-pencil-square me-1"></i>محفوظة من حسابك — يمكنك تعديلها</span>
                    </div>
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">الاسم الكامل *</label>
                            <input type="text" name="name" class="form-control" value="{cust.name}" placeholder="أدخل اسمك الثلاثي" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">رقم الهاتف *</label>
                            <input type="text" name="phone" class="form-control" value="{cust.phone}" placeholder="01xxxxxxxxx" required>
                        </div>
                        <div class="col-12">
                            <label class="form-label">عنوان التوصيل *</label>
                            <textarea name="address" class="form-control" rows="2" placeholder="المدينة - المنطقة - الشارع - رقم العمارة" required>{cust.address}</textarea>
                        </div>
                        <div class="col-12">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="saveInfo" name="save_info" value="1">
                                <label class="form-check-label" for="saveInfo" style="color:var(--ink-2);">تحديث بياناتي المحفوظة بهذه المعلومات</label>
                            </div>
                        </div>
                    </div>
                    <div class="soft-line" style="margin:22px 0;"></div>
                    <h5 style="color:var(--ink); font-weight:800; margin-bottom:20px; font-family:'Cairo',sans-serif;"><i class="bi bi-wallet2 me-1" style="color:var(--accent)"></i> طريقة الدفع</h5>
                    <div class="row g-3">
                        <div class="col-12">
                            <select name="payment_method" id="payMethod" class="form-select" required>
                                <option value="vodafone">فودافون كاش</option>
                                <option value="instapay">إنستاباي</option>
                                <option value="cash_on_delivery">دفع عند الاستلام</option>
                            </select>
                        </div>
                        <div class="col-12" id="refGroup">
                            <label class="form-label">رقم التحويل / المرجع <span style="color:var(--muted); font-weight:600;">(اختياري)</span></label>
                            <input type="text" name="transaction_ref" class="form-control" placeholder="أدخل رقم العملية">
                            <div class="form-text mt-1"><i class="bi bi-info-circle me-1"></i>رقم المحفظة: 01001234567</div>
                        </div>
                        <div class="col-12" id="proofGroup">
                            <label class="form-label">صورة تأكيد التحويل *</label>
                            <div class="proof-upload" id="proofDrop" role="button" tabindex="0">
                                <input type="file" name="payment_proof" id="proofInput" accept="image/*" hidden>
                                <div id="proofPlaceholder" class="proof-placeholder">
                                    <i class="bi bi-cloud-arrow-up"></i>
                                    <span>اضغط لرفع صورة إيصال / لقطة التحويل</span>
                                </div>
                                <img id="proofPreview" class="proof-preview" style="display:none;" alt="معاينة إثبات الدفع">
                            </div>
                            <div class="form-text mt-1"><i class="bi bi-shield-check me-1" style="color:var(--ok)"></i>حمّل صورة واضحة لإثبات الدفع (فودافون كاش / إنستاباي) ليتم تأكيد طلبك بسرعة.</div>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-accent btn-lg w-100 mt-4" style="padding:15px;"><i class="bi bi-check-lg me-2"></i>تأكيد الطلب</button>
                </form>
            </div>
        </div>
        <div class="col-lg-4">
            <div class="panel fade-up" style="position:sticky; top:132px;">
                <h5 style="color:var(--ink); font-weight:800; margin-bottom:16px; font-family:'Cairo',sans-serif;"><i class="bi bi-receipt me-1" style="color:var(--accent)"></i> ملخص الطلب</h5>
                {summary_rows}
                <div class="soft-line" style="margin:14px 0;"></div>
                <div class="d-flex justify-content-between align-items-center">
                    <span style="color:var(--muted)">الإجمالي</span>
                    <strong class="num" style="font-size:1.5rem; color:var(--price);">{total:.0f} ج.م</strong>
                </div>
            </div>
        </div>
    </div>
    <style>
        .proof-upload{{border:2px dashed var(--line);border-radius:var(--radius-sm);background:var(--surface-2);padding:22px;text-align:center;cursor:pointer;transition:var(--t)}}
        .proof-upload:hover{{border-color:var(--accent);background:var(--accent-soft)}}
        .proof-placeholder{{display:flex;flex-direction:column;align-items:center;gap:8px;color:var(--muted)}}
        .proof-placeholder i{{font-size:2rem;color:var(--accent)}}
        .proof-placeholder span{{font-size:.9rem;font-weight:600}}
        .proof-preview{{max-width:100%;max-height:260px;border-radius:var(--radius-sm);object-fit:contain}}
    </style>
    <script>
        (function(){{
            const method=document.getElementById('payMethod');
            const refGroup=document.getElementById('refGroup');
            const proofGroup=document.getElementById('proofGroup');
            const proofDrop=document.getElementById('proofDrop');
            const proofInput=document.getElementById('proofInput');
            const proofPh=document.getElementById('proofPlaceholder');
            const proofPrev=document.getElementById('proofPreview');
            function sync(){{
                const isCash=method.value==='cash_on_delivery';
                refGroup.style.display=isCash?'none':'block';
                proofGroup.style.display=isCash?'none':'block';
                proofInput.required=!isCash;
            }}
            method.addEventListener('change',sync);
            sync();
            proofDrop.addEventListener('click',function(){{ proofInput.click(); }});
            proofDrop.addEventListener('keydown',function(e){{ if(e.key==='Enter'||e.key===' '){{e.preventDefault();proofInput.click();}} }});
            proofInput.addEventListener('change',function(){{
                const f=proofInput.files[0];
                if(f){{
                    proofPrev.src=URL.createObjectURL(f);
                    proofPrev.style.display='block';
                    proofPh.style.display='none';
                }}else{{
                    proofPrev.style.display='none';
                    proofPh.style.display='flex';
                }}
            }});
        }})();
    </script>'''
    return render_template_string(BASE_HTML, title='إتمام الطلب - Mo.palace', content=Markup(content))

def success_page(order):
    payment_note = '' if order.payment_method == 'cash_on_delivery' else '<p style="color:var(--muted); margin-top:8px;"><i class="bi bi-clock-history me-1"></i>سيتم مراجعة التحويل وتأكيد الطلب خلال ساعات</p>'
    proof_block = ''
    if order.payment_proof:
        _src = url_for('static', filename='uploads/payments/' + order.payment_proof)
        proof_block = f'''<div class="soft-line" style="margin:18px 0;"></div>
            <div class="text-start">
                <span style="color:var(--muted); font-size:.85rem;"><i class="bi bi-receipt-cutoff me-1" style="color:var(--accent)"></i>صورة تأكيد التحويل</span>
                <a href="{_src}" target="_blank" rel="noopener"><img src="{_src}" alt="إثبات الدفع" style="width:100%; max-height:280px; object-fit:contain; border-radius:12px; border:1px solid var(--line); margin-top:8px;"></a>
            </div>'''
    content = f'''
    <div class="text-center py-5 fade-up">
        <div class="panel d-inline-block" style="padding:44px 52px; max-width:520px;">
            <div class="success-icon mb-4"><i class="bi bi-check-lg"></i></div>
            <h2 style="font-family:'Cairo',sans-serif; font-weight:800; color:var(--ink); margin-bottom:6px;">تم تقديم طلبك بنجاح</h2>
            <p style="color:var(--muted); margin-bottom:22px;">شكراً لثقتك بنا</p>
            <div class="soft-line" style="margin:18px 0;"></div>
            <div class="row g-3 text-start" style="margin-bottom:22px;">
                <div class="col-6"><span style="color:var(--muted); font-size:.85rem;">رقم الطلب</span><div class="num" style="font-weight:800; color:var(--accent); font-size:1.3rem;">#{order.id}</div></div>
                <div class="col-6"><span style="color:var(--muted); font-size:.85rem;">الإجمالي</span><div class="num" style="font-weight:800; color:var(--ink); font-size:1.3rem;">{order.total:.0f} ج.م</div></div>
                <div class="col-12"><span style="color:var(--muted); font-size:.85rem;">طريقة الدفع</span><div style="font-weight:700;">{order.payment_method}</div></div>
            </div>
            {payment_note}
            {proof_block}
            <div class="d-flex gap-3 mt-4">
                <a href="{url_for('home')}" class="btn btn-ghost flex-grow-1"><i class="bi bi-grid-1x2-fill me-1"></i> متابعة التسوق</a>
                <a href="{url_for('my_orders')}" class="btn btn-accent flex-grow-1"><i class="bi bi-bag-check me-1"></i> تتبع الطلب</a>
            </div>
        </div>
    </div>'''
    return render_template_string(BASE_HTML, title='تم الطلب - Mo.palace', content=Markup(content))

def my_orders_page(cust):
    orders = Order.query.filter_by(customer_id=cust.id).order_by(Order.created_at.desc()).all()
    if not orders:
        content = f'''<div class="empty-state">
            <div class="ico"><i class="bi bi-inbox"></i></div>
            <h4>لا توجد طلبات سابقة</h4>
            <p style="color:var(--muted)" class="mb-3">ابدأ التسوق الآن واكتشف منتجاتنا</p>
            <a href="{url_for('home')}" class="btn btn-accent"><i class="bi bi-grid-1x2-fill me-1"></i> تسوق الآن</a>
        </div>'''
    else:
        orders_html = ''
        for order in orders:
            status = '<span class="badge-confirmed"><i class="bi bi-check-circle me-1"></i>مؤكد</span>' if order.confirmed else '<span class="badge-pending"><i class="bi bi-hourglass-split me-1"></i>قيد المراجعة</span>'
            imgs = ''.join(f'<img src="{url_for("static", filename="uploads/" + item.product.main_image)}" style="width:46px; height:46px; object-fit:contain; background:#fff; border-radius:10px; border:1px solid var(--line); margin-left:4px; padding:3px;" title="{item.product.name}">' for item in order.items)
            orders_html += f'''
            <div class="order-card fade-up">
                <div class="d-flex justify-content-between align-items-start flex-wrap gap-3">
                    <div>
                        <div class="d-flex align-items-center gap-3 mb-2">
                            <span class="order-id num">#{order.id}</span>
                            {status}
                        </div>
                        <div style="color:var(--muted); font-size:.85rem; margin-bottom:8px;"><i class="bi bi-calendar3 me-1"></i>{order.created_at.strftime('%Y-%m-%d %H:%M')}</div>
                        <div class="num" style="font-weight:800; color:var(--price); font-size:1.1rem; margin-bottom:8px;">{order.total:.0f} ج.م</div>
                        <div class="d-flex flex-wrap">{imgs}</div>
                    </div>
                    <a href="{url_for('order_detail', oid=order.id)}" class="btn btn-ghost"><i class="bi bi-arrow-left me-1"></i> التفاصيل</a>
                </div>
            </div>'''
        content = f'<h2 class="page-title fade-up"><i class="bi bi-bag-check-fill"></i> طلباتي</h2>{orders_html}'
    return render_template_string(BASE_HTML, title='طلباتي - Mo.palace', content=Markup(content))

def order_detail_page(order):
    items_rows = ''.join(
        f'''<div class="d-flex align-items-center gap-3 mb-3 p-3" style="background:var(--surface); border-radius:var(--radius-sm); border:1px solid var(--line);">
            <img src="{url_for('static', filename='uploads/' + item.product.main_image)}" class="cart-img">
            <div class="flex-grow-1">
                <strong>{item.product.name}</strong>
                <div style="color:var(--muted); font-size:.85rem;">الكمية: {item.quantity} &bull; السعر: {item.product.price:.0f} ج.م</div>
            </div>
            <div class="num" style="font-weight:800; color:var(--price);">{item.product.price * item.quantity:.0f} ج.م</div>
        </div>''' for item in order.items
    )
    existing_returns = ReturnRequest.query.filter_by(order_id=order.id).order_by(ReturnRequest.created_at.desc()).all()
    returned_pids = {r.product_id for r in existing_returns if r.status != 'مرفوض'}
    returns_status_html = ''
    if existing_returns:
        rows_r = ''
        for ret in existing_returns:
            prod = db.session.get(Product, ret.product_id)
            if ret.status == 'مقبول':
                badge = '<span class="badge-confirmed">مقبول</span>'
            elif ret.status == 'مرفوض':
                badge = '<span class="badge-rejected">مرفوض</span>'
            else:
                badge = '<span class="badge-pending">قيد المراجعة</span>'
            note = f'<div style="color:var(--ink-2); font-size:.85rem; margin-top:6px;"><i class="bi bi-chat-left-text me-1" style="color:var(--accent)"></i>رد المتجر: {ret.admin_note}</div>' if ret.admin_note else ''
            rows_r += f'''<div class="review-card">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <strong>{prod.name if prod else 'منتج'}</strong>{badge}
                </div>
                <div style="color:var(--muted); font-size:.85rem;">السبب: {ret.reason}</div>
                <div style="color:var(--muted); font-size:.78rem; margin-top:4px;"><i class="bi bi-calendar3 me-1"></i>{ret.created_at.strftime('%Y-%m-%d %H:%M')}</div>
                {note}
            </div>'''
        returns_status_html = f'''<div class="panel mt-4 fade-up">
            <h5 style="color:var(--ink); font-weight:800; margin-bottom:16px; font-family:'Cairo',sans-serif;"><i class="bi bi-clock-history me-1" style="color:var(--accent)"></i> حالة طلبات الاسترجاع</h5>
            {rows_r}
        </div>'''

    return_form = ''
    if order.confirmed:
        available_options = ''
        for item in order.items:
            if item.product.id not in returned_pids:
                available_options += f'<option value="{item.product.id}">{item.product.name}</option>'
        if available_options:
            return_form = f'''
            <div class="panel mt-4 fade-up">
                <h5 style="color:var(--ink); font-weight:800; margin-bottom:8px; font-family:'Cairo',sans-serif;"><i class="bi bi-arrow-return-left me-1" style="color:var(--accent)"></i> طلب استرجاع</h5>
                <div class="alert alert-warning mb-3"><i class="bi bi-exclamation-triangle-fill me-1"></i> تنبيه: يتم خصم <strong>رسوم شحن واسترجاع</strong> من قيمة المبلغ المسترد، ويجب أن يكون المنتج بحالته الأصلية خلال 14 يوماً من الاستلام.</div>
                <form method="POST" action="{url_for('request_return', oid=order.id)}">
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">المنتج</label>
                            <select name="product_id" class="form-select" required>
                                {available_options}
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">سبب الاسترجاع</label>
                            <textarea name="reason" class="form-control" rows="2" required></textarea>
                        </div>
                    </div>
                    <div class="form-check mt-3">
                        <input class="form-check-input" type="checkbox" id="agreeFees" required>
                        <label class="form-check-label" for="agreeFees" style="color:var(--ink-2);">أوافق على خصم رسوم الشحن والاسترجاع من المبلغ المسترد</label>
                    </div>
                    <button class="btn btn-accent mt-3"><i class="bi bi-send me-1"></i> إرسال الطلب</button>
                </form>
            </div>'''
        else:
            return_form = '<div class="alert alert-info mt-4 fade-up"><i class="bi bi-info-circle me-1"></i> تم طلب استرجاع كل منتجات هذا الطلب. تابع حالتها بالأعلى.</div>'
    else:
        return_form = '<div class="alert alert-info mt-4 fade-up"><i class="bi bi-info-circle me-1"></i> يمكنك طلب الاسترجاع بعد تأكيد الطلب واستلامه.</div>'
    return_form = returns_status_html + return_form
    proof_html = ''
    if order.payment_proof:
        _psrc = url_for('static', filename='uploads/payments/' + order.payment_proof)
        proof_html = f'''<div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">صورة تأكيد التحويل</span>
            <a href="{_psrc}" target="_blank" rel="noopener"><img src="{_psrc}" alt="إثبات الدفع" style="width:100%; max-height:220px; object-fit:contain; border-radius:10px; border:1px solid var(--line); margin-top:6px;"></a></div>'''
    status = '<span class="badge-confirmed"><i class="bi bi-check-circle me-1"></i>مؤكد</span>' if order.confirmed else '<span class="badge-pending"><i class="bi bi-hourglass-split me-1"></i>قيد المراجعة</span>'
    content = f'''
    <nav aria-label="breadcrumb" class="mb-3 fade-up">
        <ol class="breadcrumb" style="font-size:.85rem;">
            <li class="breadcrumb-item"><a href="{url_for('home')}">الرئيسية</a></li>
            <li class="breadcrumb-item"><a href="{url_for('my_orders')}">طلباتي</a></li>
            <li class="breadcrumb-item active">طلب #{order.id}</li>
        </ol>
    </nav>
    <div class="row g-4">
        <div class="col-lg-8">
            <h2 class="page-title fade-up"><i class="bi bi-receipt"></i> تفاصيل الطلب #{order.id}</h2>
            {items_rows}
            {return_form}
        </div>
        <div class="col-lg-4">
            <div class="panel fade-up" style="position:sticky; top:132px;">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <span style="color:var(--muted);">الحالة</span>
                    {status}
                </div>
                <div class="soft-line" style="margin:14px 0;"></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">العميل</span><div style="font-weight:700;">{order.customer_name}</div></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">الهاتف</span><div style="font-weight:700; direction:ltr; text-align:right;">{order.customer_phone}</div></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">العنوان</span><div style="font-weight:500;">{order.address}</div></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">طريقة الدفع</span><div style="font-weight:700;">{order.payment_method}</div></div>
                {f'<div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">رقم التحويل</span><div style="font-weight:700; direction:ltr; text-align:right;">{order.transaction_ref}</div></div>' if order.transaction_ref else ''}
                {proof_html}
                <div class="soft-line" style="margin:14px 0;"></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">التاريخ</span><div style="font-weight:500;">{order.created_at.strftime('%Y-%m-%d %H:%M')}</div></div>
                <div><span style="color:var(--muted); font-size:.85rem;">الإجمالي</span><div class="num" style="font-weight:800; font-size:1.7rem; color:var(--price);">{order.total:.0f} <span style="font-size:.8rem; font-weight:600; color:var(--muted); font-family:'Tajawal',sans-serif;">ج.م</span></div></div>
                <a href="{url_for('my_orders')}" class="btn btn-ghost w-100 mt-4"><i class="bi bi-arrow-right me-1"></i> العودة للطلبات</a>
            </div>
        </div>
    </div>'''
    return render_template_string(BASE_HTML, title=f'طلب #{order.id} - Mo.palace', content=Markup(content))

# ------- صفحات الحساب (تسجيل / دخول / إعدادات) -------
def signup_page():
    content = f'''
    <div class="auth-wrap fade-up">
        <div class="panel text-center">
            <div class="auth-icon"><i class="bi bi-person-plus-fill"></i></div>
            <h3 style="font-family:'Cairo',sans-serif; font-weight:800; color:var(--ink); margin-bottom:4px;">إنشاء حساب جديد</h3>
            <p style="color:var(--muted); font-size:.88rem; margin-bottom:22px;">سجّل بياناتك مرة واحدة لتتسوّق بسهولة</p>
            <form method="POST" class="text-start">
                <div class="mb-3">
                    <label class="form-label">الاسم الكامل</label>
                    <input name="name" class="form-control" placeholder="الاسم الثلاثي" required>
                </div>
                <div class="mb-3">
                    <label class="form-label">رقم الهاتف</label>
                    <input name="phone" class="form-control" placeholder="01xxxxxxxxx" required dir="ltr" style="text-align:right;">
                    <div class="form-text mt-1">سيُستخدم لتسجيل الدخول</div>
                </div>
                <div class="mb-3">
                    <label class="form-label">العنوان</label>
                    <textarea name="address" class="form-control" rows="2" placeholder="المدينة - المنطقة - الشارع - رقم العمارة" required></textarea>
                </div>
                <div class="mb-3">
                    <label class="form-label">كلمة المرور</label>
                    <input type="password" name="password" class="form-control" placeholder="6 أحرف على الأقل" required>
                </div>
                <button class="btn btn-accent w-100" style="padding:12px;"><i class="bi bi-check-lg me-1"></i> إنشاء الحساب</button>
            </form>
            <div class="soft-line"></div>
            <p style="color:var(--muted); font-size:.88rem; margin:0;">لديك حساب بالفعل؟ <a href="{url_for('login')}" style="color:var(--accent-dark); font-weight:800; text-decoration:none;">سجّل الدخول</a></p>
        </div>
    </div>'''
    return render_template_string(BASE_HTML, title='إنشاء حساب - Mo.palace', content=Markup(content))

def login_page():
    content = f'''
    <div class="auth-wrap fade-up">
        <div class="panel text-center">
            <div class="auth-icon"><i class="bi bi-box-arrow-in-left"></i></div>
            <h3 style="font-family:'Cairo',sans-serif; font-weight:800; color:var(--ink); margin-bottom:4px;">تسجيل الدخول</h3>
            <p style="color:var(--muted); font-size:.88rem; margin-bottom:22px;">أدخل رقم هاتفك وكلمة المرور</p>
            <form method="POST" class="text-start">
                <div class="mb-3">
                    <label class="form-label">رقم الهاتف</label>
                    <input name="phone" class="form-control" placeholder="01xxxxxxxxx" required dir="ltr" style="text-align:right;">
                </div>
                <div class="mb-3">
                    <label class="form-label">كلمة المرور</label>
                    <input type="password" name="password" class="form-control" placeholder="كلمة المرور" required>
                </div>
                <button class="btn btn-accent w-100" style="padding:12px;"><i class="bi bi-box-arrow-in-left me-1"></i> دخول</button>
            </form>
            <div class="soft-line"></div>
            <p style="color:var(--muted); font-size:.88rem; margin:0;">ليس لديك حساب؟ <a href="{url_for('signup')}" style="color:var(--accent-dark); font-weight:800; text-decoration:none;">أنشئ حساباً</a></p>
        </div>
    </div>'''
    return render_template_string(BASE_HTML, title='تسجيل الدخول - Mo.palace', content=Markup(content))

def account_page(cust):
    orders_count = Order.query.filter_by(customer_id=cust.id).count()
    content = f'''
    <h2 class="page-title fade-up"><i class="bi bi-person-gear"></i> إعدادات الحساب</h2>
    <div class="row g-4">
        <div class="col-lg-7">
            <div class="panel fade-up">
                <h5 style="color:var(--ink); font-weight:800; margin-bottom:18px; font-family:'Cairo',sans-serif;"><i class="bi bi-pencil-square me-1" style="color:var(--accent)"></i> تعديل بياناتي</h5>
                <form method="POST">
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">الاسم الكامل</label>
                            <input name="name" class="form-control" value="{cust.name}" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">رقم الهاتف</label>
                            <input name="phone" class="form-control" value="{cust.phone}" required dir="ltr" style="text-align:right;">
                        </div>
                        <div class="col-12">
                            <label class="form-label">العنوان</label>
                            <textarea name="address" class="form-control" rows="2" required>{cust.address}</textarea>
                        </div>
                    </div>
                    <div class="soft-line"></div>
                    <h6 style="color:var(--ink); font-weight:800; margin-bottom:12px;"><i class="bi bi-key me-1" style="color:var(--accent)"></i> تغيير كلمة المرور <span style="color:var(--muted); font-weight:500; font-size:.82rem;">(اتركها فارغة إن لم ترد التغيير)</span></h6>
                    <div class="row g-3">
                        <div class="col-md-6">
                            <label class="form-label">كلمة المرور الحالية</label>
                            <input type="password" name="current_password" class="form-control" placeholder="••••••">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label">كلمة المرور الجديدة</label>
                            <input type="password" name="new_password" class="form-control" placeholder="6 أحرف على الأقل">
                        </div>
                    </div>
                    <button class="btn btn-accent mt-4"><i class="bi bi-check-lg me-1"></i> حفظ التغييرات</button>
                </form>
            </div>
        </div>
        <div class="col-lg-5">
            <div class="panel fade-up">
                <h5 style="color:var(--ink); font-weight:800; margin-bottom:16px; font-family:'Cairo',sans-serif;"><i class="bi bi-person-badge me-1" style="color:var(--accent)"></i> ملخص الحساب</h5>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">الاسم</span><div style="font-weight:700;">{cust.name}</div></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">الهاتف</span><div style="font-weight:700; direction:ltr; text-align:right;">{cust.phone}</div></div>
                <div class="mb-3"><span style="color:var(--muted); font-size:.85rem;">عدد الطلبات</span><div class="num" style="font-weight:800;">{orders_count}</div></div>
                <div class="soft-line" style="margin:14px 0;"></div>
                <a href="{url_for('my_orders')}" class="btn btn-ghost w-100 mb-2"><i class="bi bi-bag-check me-1"></i> طلباتي</a>
                <a href="{url_for('logout')}" class="btn btn-ghost w-100" style="border-color:#f0c9c9; color:#c0392b;"><i class="bi bi-box-arrow-right me-1"></i> تسجيل الخروج</a>
            </div>
        </div>
    </div>'''
    return render_template_string(BASE_HTML, title='حسابي - Mo.palace', content=Markup(content))

# ====================== صفحات الأدمن ======================
def admin_login_page():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    content = '''
    <div class="row justify-content-center" style="min-height:68vh; align-items:center;">
        <div class="col-md-5 col-lg-4">
            <div class="glass-form text-center" style="padding:40px 32px;">
                <div style="width:70px; height:70px; border-radius:20px; background:var(--accent-soft); color:var(--accent); display:inline-flex; align-items:center; justify-content:center; font-size:1.8rem; margin-bottom:18px;">
                    <i class="bi bi-shield-lock-fill"></i>
                </div>
                <h3 style="color:var(--ink); font-family:'Cairo',sans-serif; font-weight:800; margin-bottom:6px;">لوحة التحكم</h3>
                <p style="color:var(--muted); font-size:.85rem; margin-bottom:26px;">سجل دخولك للمتابعة</p>
                <form method="POST">
                    <div class="mb-3"><input name="username" class="form-control" placeholder="اسم المستخدم" required></div>
                    <div class="mb-3"><input type="password" name="password" class="form-control" placeholder="كلمة المرور" required></div>
                    <button class="btn btn-accent w-100" style="padding:12px;"><i class="bi bi-box-arrow-in-left me-1"></i> دخول</button>
                </form>
            </div>
        </div>
    </div>'''
    return render_template_string(ADMIN_BASE, title='دخول الأدمن - Mo.palace', content=Markup(content))

def admin_dashboard_page():
    products = Product.query.all()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    confirmed_total, accepted_returns, net_revenue = compute_revenue()
    pending_count = sum(1 for o in orders if not o.confirmed)
    pending_returns = ReturnRequest.query.filter_by(status='قيد المراجعة').count()
    customers_count = Customer.query.count()

    prod_rows = ''.join(
        f'<tr><td style="max-width:200px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{p.name}</td><td class="num" style="color:var(--price); font-weight:800;">{p.price:.0f} ج.م</td><td><a href="{url_for("admin_edit_product", pid=p.id)}" class="btn btn-sm btn-outline-secondary" style="border-radius:9px;"><i class="bi bi-pencil"></i></a> <a href="{url_for("admin_delete_product", pid=p.id)}" class="btn btn-sm btn-outline-danger" style="border-radius:9px;" onclick="return confirm(\'هل أنت متأكد من حذف هذا المنتج؟\')"><i class="bi bi-trash"></i></a></td></tr>'
        for p in products
    )

    order_rows = ''
    for o in orders:
        status_badge = '<span class="badge-confirmed">مؤكد</span>' if o.confirmed else '<span class="badge-pending">معلق</span>'
        order_rows += f'<tr><td class="num" style="font-weight:800;">#{o.id}</td><td>{o.customer_name}</td><td>{o.payment_method}</td><td>{status_badge}</td><td><a href="{url_for("admin_order", oid=o.id)}" class="btn btn-sm btn-outline-secondary" style="border-radius:9px;"><i class="bi bi-eye"></i></a></td></tr>'

    returns_note = ''
    if accepted_returns > 0:
        returns_note = f'<div class="stat-label mt-1" style="color:var(--price);">مخصوم استرجاعات مقبولة: {accepted_returns:.0f} ج.م</div>'

    content = f'''
    <div class="row g-3 mb-4">
        <div class="col-6 col-md-3"><a href="{url_for('admin_customers')}" style="text-decoration:none;"><div class="stat-card"><div class="stat-ico"><i class="bi bi-people"></i></div><div class="stat-num num">{customers_count}</div><div class="stat-label">العملاء</div></div></a></div>
        <div class="col-6 col-md-3"><div class="stat-card"><div class="stat-ico"><i class="bi bi-receipt"></i></div><div class="stat-num num">{len(orders)}</div><div class="stat-label">الطلبات</div></div></div>
        <div class="col-6 col-md-3"><div class="stat-card"><div class="stat-ico"><i class="bi bi-hourglass-split"></i></div><div class="stat-num num">{pending_count}</div><div class="stat-label">طلبات معلقة</div></div></div>
        <div class="col-6 col-md-3"><a href="{url_for('admin_returns')}" style="text-decoration:none;"><div class="stat-card"><div class="stat-ico"><i class="bi bi-arrow-return-left"></i></div><div class="stat-num num">{pending_returns}</div><div class="stat-label">استرجاع معلق</div></div></a></div>
    </div>
    <div class="row g-3 mb-4">
        <div class="col-12"><div class="stat-card d-flex align-items-center justify-content-between"><div><div class="stat-label">صافي الأرباح (بعد خصم الاسترجاعات المقبولة)</div><div class="stat-num num" style="color:var(--price);">{net_revenue:.0f} ج.م</div>{returns_note}</div><div class="stat-ico" style="margin:0;"><i class="bi bi-cash-stack"></i></div></div></div>
    </div>
    <div class="row g-4">
        <div class="col-lg-6">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h4 class="section-title mb-0"><i class="bi bi-box-seam"></i> المنتجات</h4>
                <a href="{url_for('admin_add_product')}" class="btn btn-accent btn-sm"><i class="bi bi-plus-lg me-1"></i> منتج جديد</a>
            </div>
            <div class="table-responsive"><table class="table table-borderless table-clean mb-0"><thead><tr><th>الاسم</th><th>السعر</th><th>تحكم</th></tr></thead><tbody>{prod_rows}</tbody></table></div>
        </div>
        <div class="col-lg-6">
            <h4 class="section-title"><i class="bi bi-receipt"></i> الطلبات</h4>
            <div class="table-responsive"><table class="table table-borderless table-clean mb-0"><thead><tr><th>رقم</th><th>العميل</th><th>الدفع</th><th>الحالة</th><th></th></tr></thead><tbody>{order_rows}</tbody></table></div>
        </div>
    </div>'''
    return render_template_string(ADMIN_BASE, title='لوحة التحكم - Mo.palace', content=Markup(content))

def admin_product_form(edit_mode=False, product=None):
    main_img_html = ''
    if product and product.main_image != 'default.jpg':
        main_img_html = f'<img src="{url_for("static", filename="uploads/" + product.main_image)}" class="mt-2" height="80" style="border-radius:12px; border:1px solid var(--line);" id="currentImagePreview">'
    extra_images_html = ''
    if edit_mode and product:
        extra_imgs = product.extra_images.all()
        if extra_imgs:
            checkboxes = ''.join(
                f'<div class="d-inline-block me-2 mb-2" style="position:relative;"><input class="form-check-input" type="checkbox" name="remove_images" value="{img.id}" style="position:absolute; top:4px; right:4px; z-index:2;"><img src="{url_for("static", filename="uploads/" + img.filename)}" height="60" style="border-radius:10px; border:1px solid var(--line);"></div>'
                for img in extra_imgs
            )
            extra_images_html = f'<div class="mt-3"><label class="form-label" style="color:var(--accent);">حذف صور مختارة</label><div>{checkboxes}</div></div>'
    content = f'''
    <h4 class="section-title"><i class="bi bi-{'pencil-square' if edit_mode else 'plus-circle'}"></i> {'تعديل المنتج' if edit_mode else 'منتج جديد'}</h4>
    <div class="glass-form">
        <form method="POST" enctype="multipart/form-data">
            <div class="row g-3">
                <div class="col-md-6"><label class="form-label">اسم المنتج</label><input name="name" class="form-control" value="{product.name if product else ''}" required></div>
                <div class="col-md-6"><label class="form-label">السعر (ج.م)</label><input type="number" step="0.01" name="price" class="form-control" value="{product.price if product else ''}" required></div>
                <div class="col-12"><label class="form-label">الوصف</label><textarea name="description" class="form-control" rows="3" required>{product.description if product else ''}</textarea></div>
                <div class="col-md-6">
                    <label class="form-label">الصورة الرئيسية</label>
                    <input type="file" name="main_image" id="mainImageInput" class="form-control" accept="image/*">
                    {main_img_html}
                    <div class="mt-2" id="cropContainer" style="display:none; max-width:100%;">
                        <img id="cropImage" style="max-width:100%; border:2px solid var(--line); border-radius:12px;">
                        <div class="mt-2">
                            <button type="button" class="btn btn-accent btn-sm me-2" onclick="performCrop()"><i class="bi bi-crop me-1"></i> قص</button>
                            <button type="button" class="btn btn-outline-secondary btn-sm" onclick="cancelCrop()">إلغاء</button>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <label class="form-label">صور إضافية</label>
                    <input type="file" name="extra_images" class="form-control" accept="image/*" multiple>
                    {extra_images_html}
                </div>
            </div>
            <div class="mt-4 d-flex gap-2">
                <button type="submit" class="btn btn-accent"><i class="bi bi-check-lg me-1"></i> حفظ</button>
                <a href="{url_for('admin_dashboard')}" class="btn btn-outline-secondary" style="border-radius:11px;">إلغاء</a>
            </div>
        </form>
    </div>'''
    scripts = '''<script>
        let cropper;
        const mainInput=document.getElementById('mainImageInput');
        const cropContainer=document.getElementById('cropContainer');
        const cropImage=document.getElementById('cropImage');
        const preview=document.getElementById('currentImagePreview');
        mainInput.addEventListener('change',function(e){
            const file=e.target.files[0];if(!file)return;
            const reader=new FileReader();
            reader.onload=function(ev){
                cropImage.src=ev.target.result;cropContainer.style.display='block';
                if(cropper)cropper.destroy();
                cropper=new Cropper(cropImage,{aspectRatio:NaN,viewMode:1,autoCropArea:.8,responsive:true,background:false});
            };
            reader.readAsDataURL(file);
        });
        window.performCrop=function(){
            if(!cropper)return;
            cropper.getCroppedCanvas().toBlob(function(blob){
                const file=new File([blob],'cropped_'+Date.now()+'.jpg',{type:'image/jpeg'});
                const dt=new DataTransfer();dt.items.add(file);mainInput.files=dt.files;
                if(preview)preview.src=URL.createObjectURL(blob);
                cropContainer.style.display='none';cropper.destroy();cropper=null;
            },'image/jpeg',.9);
        };
        window.cancelCrop=function(){cropContainer.style.display='none';if(cropper){cropper.destroy();cropper=null}mainInput.value=''};
    </script>'''
    return render_template_string(ADMIN_BASE, title='نموذج المنتج - Mo.palace', content=Markup(content), scripts=Markup(scripts))

def admin_order_detail_page(order):
    items_rows = ''.join(f'<tr><td>{item.product.name}</td><td style="text-align:center;" class="num">{item.quantity}</td><td class="num" style="color:var(--price);">{item.product.price:.0f} ج.م</td><td class="num" style="font-weight:800;">{item.product.price * item.quantity:.0f} ج.م</td></tr>' for item in order.items)
    proof_html = ''
    if order.payment_proof:
        _psrc = url_for('static', filename='uploads/payments/' + order.payment_proof)
        proof_html = f'''<div class="glass-form mb-3">
            <h6 style="font-weight:800; margin-bottom:12px;"><i class="bi bi-receipt-cutoff me-1" style="color:var(--accent)"></i> صورة تأكيد التحويل</h6>
            <a href="{_psrc}" target="_blank" rel="noopener"><img src="{_psrc}" alt="إثبات الدفع" style="width:100%; max-height:360px; object-fit:contain; border-radius:12px; border:1px solid var(--line);"></a>
        </div>'''
    returns = ReturnRequest.query.filter_by(order_id=order.id).order_by(ReturnRequest.created_at.desc()).all()
    returns_html = ''
    if returns:
        returns_html = '<h5 class="section-title mt-4"><i class="bi bi-arrow-return-left"></i> طلبات الاسترجاع</h5>'
        for ret in returns:
            product = db.session.get(Product, ret.product_id)
            if ret.status == 'مقبول':
                badge = '<span class="badge-confirmed">مقبول</span>'
            elif ret.status == 'مرفوض':
                badge = '<span class="badge-rejected">مرفوض</span>'
            else:
                badge = '<span class="badge-pending">قيد المراجعة</span>'
            note_html = f'<div class="mt-1" style="color:var(--ink-2); font-size:.85rem;"><i class="bi bi-chat-left-text me-1" style="color:var(--accent)"></i>ردك: {ret.admin_note}</div>' if ret.admin_note else ''
            actions = ''
            if ret.status == 'قيد المراجعة':
                actions = f'''
                <form method="POST" action="{url_for('admin_return_update', rid=ret.id)}" class="mt-3">
                    <textarea name="admin_note" class="form-control mb-2" rows="2" placeholder="ملاحظة / رد للعميل (اختياري)"></textarea>
                    <div class="d-flex gap-2">
                        <button name="action" value="accept" class="btn btn-accent btn-sm"><i class="bi bi-check-lg me-1"></i> قبول الاسترجاع</button>
                        <button name="action" value="reject" class="btn btn-outline-danger btn-sm" style="border-radius:11px;"><i class="bi bi-x-lg me-1"></i> رفض</button>
                    </div>
                </form>'''
            else:
                actions = f'''
                <form method="POST" action="{url_for('admin_return_update', rid=ret.id)}" class="mt-2 d-flex gap-2">
                    <input type="hidden" name="admin_note" value="{ret.admin_note or ''}">
                    <button name="action" value="pending" class="btn btn-outline-secondary btn-sm" style="border-radius:11px;"><i class="bi bi-arrow-counterclockwise me-1"></i> إعادة للمراجعة</button>
                </form>'''
            returns_html += f'''<div class="glass-form mb-3" style="padding:16px 18px;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>{product.name if product else "منتج"}</strong>{badge}
                </div>
                <div style="color:var(--muted); font-size:.88rem;">السبب: {ret.reason}</div>
                <div style="color:var(--muted); font-size:.78rem; margin-top:4px;"><i class="bi bi-calendar3 me-1"></i>{ret.created_at.strftime('%Y-%m-%d %H:%M')}</div>
                {note_html}
                {actions}
            </div>'''
    action_btn = f'<a href="{url_for("admin_unconfirm", oid=order.id)}" class="btn btn-outline-warning w-100" style="border-radius:11px;"><i class="bi bi-x-circle me-1"></i> إلغاء التأكيد</a>' if order.confirmed else f'<a href="{url_for("admin_confirm", oid=order.id)}" class="btn btn-accent w-100"><i class="bi bi-check-circle me-1"></i> تأكيد الطلب</a>'
    customer_link = ''
    if order.customer_id:
        customer_link = f'<a href="{url_for("admin_customer", cid=order.customer_id)}" class="btn btn-outline-secondary w-100 mt-2" style="border-radius:11px;"><i class="bi bi-person-lines-fill me-1"></i> ملف العميل والمحادثة</a>'
    content = f'''
    <h4 class="section-title"><i class="bi bi-receipt"></i> طلب رقم #{order.id}</h4>
    <div class="row g-4">
        <div class="col-lg-8">
            <div class="glass-form mb-3">
                <div class="row g-3">
                    <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">العميل</span><div style="font-weight:700;">{order.customer_name}</div></div>
                    <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">الهاتف</span><div style="font-weight:700; direction:ltr; text-align:right;">{order.customer_phone}</div></div>
                    <div class="col-12"><span style="color:var(--muted); font-size:.85rem;">العنوان</span><div>{order.address}</div></div>
                    <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">الدفع</span><div style="font-weight:700;">{order.payment_method}</div></div>
                    {f'<div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">رقم التحويل</span><div style="font-weight:700; direction:ltr; text-align:right;">{order.transaction_ref}</div></div>' if order.transaction_ref else ''}
                    <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">التاريخ</span><div>{order.created_at.strftime("%Y-%m-%d %H:%M")}</div></div>
                    <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">الإجمالي</span><div class="num" style="font-weight:800; color:var(--price); font-size:1.2rem;">{order.total:.0f} ج.م</div></div>
                </div>
            </div>
            {proof_html}
            <h5 class="section-title"><i class="bi bi-box-seam"></i> المنتجات</h5>
            <div class="table-responsive"><table class="table table-borderless table-clean mb-0"><thead><tr><th>المنتج</th><th style="text-align:center;">الكمية</th><th>السعر</th><th>الإجمالي</th></tr></thead><tbody>{items_rows}</tbody></table></div>
            {returns_html}
        </div>
        <div class="col-lg-4">
            <div class="glass-form" style="position:sticky; top:20px;">
                <h6 style="color:var(--muted); margin-bottom:12px;">إجراءات</h6>
                {action_btn}
                {customer_link}
                <a href="{url_for('admin_dashboard')}" class="btn btn-outline-secondary w-100 mt-2" style="border-radius:11px;"><i class="bi bi-arrow-right me-1"></i> العودة</a>
            </div>
        </div>
    </div>'''
    return render_template_string(ADMIN_BASE, title=f'طلب #{order.id} - Mo.palace', content=Markup(content))

def render_messages(msgs, admin_view=False):
    if not msgs:
        return '<div class="chat-empty"><i class="bi bi-chat-heart" style="font-size:2rem;color:var(--accent)"></i><p class="mt-2">ابدأ المحادثة، فريق الدعم في خدمتك</p></div>'
    html = ''
    for m in msgs:
        cls = 'admin' if m.sender == 'admin' else 'user'
        if admin_view:
            who = 'أنت (الدعم)' if m.sender == 'admin' else (m.customer_name or 'العميل')
        else:
            who = 'الدعم' if m.sender == 'admin' else (m.customer_name or 'أنت')
        inner = ''
        if getattr(m, 'msg_type', 'text') == 'image' and m.media_file:
            src = url_for('static', filename='uploads/chat/' + m.media_file)
            inner += f'<a href="{src}" target="_blank" rel="noopener"><img src="{src}" class="chat-media-img" alt="صورة مرفقة"></a>'
        elif getattr(m, 'msg_type', 'text') == 'voice' and m.media_file:
            src = url_for('static', filename='uploads/chat/' + m.media_file)
            inner += (
                f'<div class="voice-player" data-src="{src}">'
                f'<button type="button" class="vp-play" aria-label="تشغيل"><i class="bi bi-play-fill"></i></button>'
                f'<div class="vp-track"><div class="vp-progress"></div></div>'
                f'<span class="vp-time num">0:00</span>'
                f'</div>'
            )
        if m.body:
            inner += f'<div>{m.body}</div>'
        html += f'''<div class="msg {cls}"><b style="font-size:.72rem;opacity:.75;">{who}</b>{inner}<span class="time num">{m.created_at.strftime('%m-%d %H:%M')}</span></div>'''
    return html

def chat_input_form(placeholder='اكتب رسالتك...', guest_name=None):
    """نموذج إدخال شات موحّد يدعم النص + إرفاق صورة + تسجيل رسالة صوتية."""
    guest_field = ''
    if guest_name is not None:
        guest_field = f'<input type="text" id="guestName" class="form-control mb-2" placeholder="اسمك أو رقم هاتفك (اختياري)" value="{guest_name}">'
    return f'''
        <form id="chatForm" class="chat-input-form" enctype="multipart/form-data">
            {guest_field}
            <div id="previewBar" class="chat-preview-bar" style="display:none;"></div>
            <div id="recBar" class="chat-rec-bar" style="display:none;">
                <button type="button" id="recCancel" class="rec-cancel" title="إلغاء"><i class="bi bi-trash3-fill"></i></button>
                <span class="rec-dot"></span>
                <span id="recTime" class="num rec-time">0:00</span>
                <div class="rec-wave" aria-hidden="true">
                    <span></span><span></span><span></span><span></span><span></span><span></span>
                    <span></span><span></span><span></span><span></span><span></span><span></span>
                </div>
                <button type="button" id="recSend" class="rec-send" title="إرسال"><i class="bi bi-send-fill"></i></button>
            </div>
            <div class="chat-input-row">
                <input type="file" id="imgInput" accept="image/*" hidden>
                <button type="button" id="imgBtn" class="btn chat-tool-btn" title="إرفاق صورة"><i class="bi bi-image"></i></button>
                <button type="button" id="micBtn" class="btn chat-tool-btn" title="رسالة صوتية"><i class="bi bi-mic-fill"></i></button>
                <input type="text" id="chatMsg" class="form-control" placeholder="{placeholder}">
                <button class="btn btn-accent chat-send-btn" type="submit"><i class="bi bi-send-fill"></i></button>
            </div>
        </form>'''

def chat_widget_script(send_url, poll_url, guest=False):
    """سكربت موحّد: polling + إرفاق صورة + تسجيل صوت عبر MediaRecorder."""
    return f'''<script>
    (function(){{
        const box=document.getElementById('chatBox');
        const form=document.getElementById('chatForm');
        const msg=document.getElementById('chatMsg');
        const imgInput=document.getElementById('imgInput');
        const imgBtn=document.getElementById('imgBtn');
        const micBtn=document.getElementById('micBtn');
        const previewBar=document.getElementById('previewBar');
        const recBar=document.getElementById('recBar');
        const recTime=document.getElementById('recTime');
        const recSend=document.getElementById('recSend');
        const recCancel=document.getElementById('recCancel');
        const guestNameEl=document.getElementById('guestName');
        let pendingImage=null, recordedVoice=null;
        let mediaRecorder=null, chunks=[], recording=false, recTimer=null, recSeconds=0;

        function scrollBottom(){{ box.scrollTop=box.scrollHeight; }}

        function fmtTime(s){{ s=Math.max(0,Math.round(s||0)); const m=Math.floor(s/60); const ss=String(s%60).padStart(2,'0'); return m+':'+ss; }}

        // مشغّل صوت مخصّص بشكل واتساب + إصلاح مشكلة مدة ملفات webm (اللي بتقطع بعد ثانيتين)
        function initVoicePlayers(root){{
            (root||document).querySelectorAll('.voice-player:not([data-ready])').forEach(function(vp){{
                vp.setAttribute('data-ready','1');
                const src=vp.getAttribute('data-src');
                const playBtn=vp.querySelector('.vp-play');
                const track=vp.querySelector('.vp-track');
                const progress=vp.querySelector('.vp-progress');
                const timeEl=vp.querySelector('.vp-time');
                const audio=new Audio();
                audio.preload='metadata';
                audio.src=src;
                let dur=0;

                // نحسب المدة الحقيقية عبر Web Audio (decodeAudioData) لأن ملفات
                // MediaRecorder (webm/opus) بتيجي بمدة Infinity فالشريط كان بيتجمّد.
                function setDur(d){{
                    if(d&&isFinite(d)&&d>0){{ dur=d; if(audio.paused)timeEl.textContent=fmtTime(dur); }}
                }}
                (function loadRealDuration(){{
                    try{{
                        const AC=window.AudioContext||window.webkitAudioContext;
                        if(!AC)return;
                        window._vpAC=window._vpAC||new AC();
                        fetch(src).then(function(r){{ return r.arrayBuffer(); }})
                            .then(function(buf){{ return window._vpAC.decodeAudioData(buf.slice(0)); }})
                            .then(function(ab){{ setDur(ab.duration); }})
                            .catch(function(){{}});
                    }}catch(e){{}}
                }})();
                audio.addEventListener('loadedmetadata',function(){{ if(isFinite(audio.duration))setDur(audio.duration); }});
                audio.addEventListener('durationchange',function(){{ if(isFinite(audio.duration))setDur(audio.duration); }});
                // currentTime بيتقدّم صح حتى لو المدة Infinity، فنعتمد عليه للشريط
                audio.addEventListener('timeupdate',function(){{
                    const cur=audio.currentTime||0;
                    const total=(dur&&isFinite(dur))?dur:(isFinite(audio.duration)?audio.duration:0);
                    if(total>0){{ progress.style.width=Math.min(100,(cur/total)*100)+'%'; }}
                    timeEl.textContent=fmtTime(cur);
                }});
                audio.addEventListener('ended',function(){{
                    playBtn.innerHTML='<i class="bi bi-play-fill"></i>';
                    progress.style.width='0%';
                    timeEl.textContent=fmtTime(dur);
                }});
                playBtn.addEventListener('click',function(){{
                    // أوقف أي مشغّل صوت تاني شغّال (زي واتساب)
                    document.querySelectorAll('.voice-player').forEach(function(other){{
                        if(other!==vp&&other._audio&&!other._audio.paused){{
                            other._audio.pause();
                            const b=other.querySelector('.vp-play');
                            if(b)b.innerHTML='<i class="bi bi-play-fill"></i>';
                        }}
                    }});
                    if(audio.paused){{
                        audio.play().then(function(){{ playBtn.innerHTML='<i class="bi bi-pause-fill"></i>'; }}).catch(function(){{}});
                    }} else {{
                        audio.pause(); playBtn.innerHTML='<i class="bi bi-play-fill"></i>';
                    }}
                }});
                track.addEventListener('click',function(e){{
                    if(!dur)return;
                    const rect=track.getBoundingClientRect();
                    let ratio=(e.clientX-rect.left)/rect.width;
                    if(document.dir==='rtl'||getComputedStyle(track).direction==='rtl'){{ ratio=1-ratio; }}
                    ratio=Math.min(1,Math.max(0,ratio));
                    audio.currentTime=ratio*dur;
                }});
                vp._audio=audio;
            }});
        }}
        initVoicePlayers(box);
        scrollBottom();

        let lastHtml=box.innerHTML;
        function anyVoicePlaying(){{
            let playing=false;
            document.querySelectorAll('.voice-player').forEach(function(vp){{
                if(vp._audio&&!vp._audio.paused)playing=true;
            }});
            return playing;
        }}
        async function poll(){{
            try{{
                const r=await fetch('{poll_url}');
                const data=await r.json();
                // لا نعيد بناء الرسائل إلا لو اتغيّر المحتوى فعلاً، وكمان مننساش
                // أي رسالة صوتية شغّالة دلوقتي عشان الشريط ما يفصلش ويرجع من الأول.
                if(data.html===lastHtml||anyVoicePlaying())return;
                const atBottom=box.scrollHeight-box.scrollTop-box.clientHeight<80;
                box.innerHTML=data.html;
                lastHtml=data.html;
                initVoicePlayers(box);
                if(atBottom)scrollBottom();
            }}catch(e){{}}
        }}

        function renderPreview(){{
            previewBar.innerHTML='';
            if(pendingImage){{
                const url=URL.createObjectURL(pendingImage);
                previewBar.insertAdjacentHTML('beforeend','<div class="prev-item"><img src="'+url+'"><button type="button" data-clear="img">&times;</button></div>');
            }}
            if(recordedVoice){{
                const url=URL.createObjectURL(recordedVoice);
                previewBar.insertAdjacentHTML('beforeend',
                    '<div class="prev-item voice">'+
                    '<div class="voice-player" data-src="'+url+'">'+
                    '<button type="button" class="vp-play" aria-label="تشغيل"><i class="bi bi-play-fill"></i></button>'+
                    '<div class="vp-track"><div class="vp-progress"></div></div>'+
                    '<span class="vp-time num">0:00</span>'+
                    '</div>'+
                    '<button type="button" data-clear="voice">&times;</button></div>');
                initVoicePlayers(previewBar);
            }}
            previewBar.style.display=(pendingImage||recordedVoice)?'flex':'none';
        }}
        previewBar.addEventListener('click',function(e){{
            const t=e.target.closest('[data-clear]'); if(!t)return;
            const c=t.getAttribute('data-clear');
            if(c==='img'){{pendingImage=null; imgInput.value='';}}
            if(c==='voice'){{recordedVoice=null;}}
            renderPreview();
        }});

        imgBtn.addEventListener('click',function(){{ imgInput.click(); }});
        imgInput.addEventListener('change',function(){{
            if(imgInput.files[0]){{ pendingImage=imgInput.files[0]; renderPreview(); }}
        }});

        let audioStream=null, recMime='audio/webm', recExt='webm', cancelled=false;

        function pickMime(){{
            const cands=['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/mp4','audio/mpeg'];
            for(const c of cands){{
                if(window.MediaRecorder&&MediaRecorder.isTypeSupported&&MediaRecorder.isTypeSupported(c)) return c;
            }}
            return '';
        }}
        function extFromMime(m){{
            if(!m)return 'webm';
            if(m.indexOf('mp4')>=0)return 'm4a';
            if(m.indexOf('mpeg')>=0)return 'mp3';
            if(m.indexOf('ogg')>=0)return 'ogg';
            return 'webm';
        }}

        async function startRec(){{
            if(!window.isSecureContext){{
                alert('التسجيل الصوتي يحتاج اتصال آمن (HTTPS). افتح الموقع عبر رابط https أو localhost.');
                return;
            }}
            if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia||!window.MediaRecorder){{
                alert('متصفحك لا يدعم التسجيل الصوتي. جرّب Chrome أو Safari المحدّث.');
                return;
            }}
            try{{
                audioStream=await navigator.mediaDevices.getUserMedia({{
                    audio:{{ echoCancellation:true, noiseSuppression:true, autoGainControl:true, channelCount:1 }}
                }});
            }}catch(err){{
                if(err&&(err.name==='NotAllowedError'||err.name==='SecurityError')){{
                    alert('تم رفض إذن الميكروفون. اضغط على أيقونة القفل بجانب رابط الموقع واسمح بالميكروفون ثم أعد المحاولة.');
                }}else if(err&&err.name==='NotFoundError'){{
                    alert('لم يتم العثور على ميكروفون في جهازك.');
                }}else{{
                    alert('تعذّر الوصول للميكروفون. تأكد من توصيله والسماح باستخدامه.');
                }}
                return;
            }}
            recMime=pickMime(); recExt=extFromMime(recMime);
            try{{
                mediaRecorder=recMime?new MediaRecorder(audioStream,{{mimeType:recMime,audioBitsPerSecond:128000}}):new MediaRecorder(audioStream);
            }}catch(e){{
                mediaRecorder=new MediaRecorder(audioStream);
            }}
            chunks=[]; cancelled=false;
            mediaRecorder.ondataavailable=function(e){{ if(e.data&&e.data.size>0)chunks.push(e.data); }};
            mediaRecorder.onstop=function(){{
                if(audioStream){{ audioStream.getTracks().forEach(function(t){{t.stop();}}); audioStream=null; }}
                clearInterval(recTimer);
                micBtn.classList.remove('recording');
                micBtn.innerHTML='<i class="bi bi-mic-fill"></i>';
                recBar.style.display='none';
                recBar.classList.remove('active');
                recording=false;
                if(cancelled||chunks.length===0){{ chunks=[]; return; }}
                recordedVoice=new Blob(chunks,{{type:recMime||'audio/webm'}});
                renderPreview();
            }};
            // نجمع البيانات كل 200ms عشان مايضيعش أي جزء من التسجيل
            mediaRecorder.start(200);
            recording=true; recSeconds=0; recTime.textContent='0:00';
            micBtn.classList.add('recording');
            micBtn.innerHTML='<i class="bi bi-stop-fill"></i>';
            recBar.style.display='flex';
            recBar.classList.add('active');
            recTimer=setInterval(function(){{ recSeconds++; recTime.textContent=fmtTime(recSeconds); }},1000);
        }}

        function finishRec(){{
            // ينهي التسجيل ويحتفظ به
            cancelled=false;
            if(mediaRecorder&&mediaRecorder.state!=='inactive'){{ mediaRecorder.stop(); }}
        }}
        function cancelRec(){{
            cancelled=true; recordedVoice=null;
            if(mediaRecorder&&mediaRecorder.state!=='inactive'){{ mediaRecorder.stop(); }}
            renderPreview();
        }}

        micBtn.addEventListener('click',function(){{ recording?finishRec():startRec(); }});
        if(recSend)recSend.addEventListener('click',finishRec);
        if(recCancel)recCancel.addEventListener('click',cancelRec);

        form.addEventListener('submit',async function(e){{
            e.preventDefault();
            if(recording){{ finishRec(); await new Promise(r=>setTimeout(r,350)); }}
            const text=msg.value.trim();
            if(!text&&!pendingImage&&!recordedVoice)return;
            const fd=new FormData();
            fd.append('body',text);
            {"if(guestNameEl)fd.append('name',guestNameEl.value);" if guest else ""}
            if(pendingImage)fd.append('image',pendingImage,'chat-image.'+((pendingImage.name||'jpg').split('.').pop()));
            if(recordedVoice)fd.append('voice',recordedVoice,'voice.'+recExt);
            msg.value=''; pendingImage=null; recordedVoice=null; imgInput.value=''; renderPreview();
            try{{ await fetch('{send_url}',{{method:'POST',body:fd}}); }}catch(e){{}}
            poll();
        }});
        setInterval(poll,4000);
    }})();
    </script>'''

# ================== مكالمات صوتية (WebRTC signaling عبر polling) ==================
import time as _time, threading as _threading, queue as _queue
_call_lock = _threading.Lock()
CALL_SIGNALS = {}    # cid -> {'admin': [..], 'user': [..]}
CALL_PRESENCE = {}   # cid -> {'admin': ts, 'user': ts}
CALL_PRESENCE_TTL = 12  # ثانية: يُعتبر الطرف متصلاً إذا استفسر خلال هذه المدة

# ---- ترحيل الصوت عبر الخادم نفسه بـ HTTP Streaming (بدون WebSocket ولا خدمة خارجية) ----
# نلتقط صوت الميكروفون في المتصفح كـ PCM 16kHz. الطلوع (الإرسال) يتم عبر طلبات
# POST صغيرة متتابعة، والنزول (الاستقبال) عبر ردّ HTTP متدفّق يبقى مفتوحاً ويدفع
# الصوت لحظة وصوله. هذا HTTP عادي بالكامل فيعمل بثبات على خادم Flask التطويري
# (threaded=True) دون أي مكتبة WebSocket ولا سيرفر خاص — وهو الحل المضمون محلياً.
# لكل مكالمة ولكل طرف طابور صوت (Queue) يجمع ما وصله من الطرف الآخر ليتدفّق إليه.
CALL_AUDIO = {}   # cid -> {'admin': Queue, 'user': Queue}  طوابير صوت الاستقبال

def _get_audio_q(cid, role):
    """يعيد (وينشئ عند الحاجة) طابور صوت الاستقبال لهذا الطرف في هذه المكالمة."""
    with _call_lock:
        d = CALL_AUDIO.setdefault(cid, {})
        q = d.get(role)
        if q is None:
            q = _queue.Queue(maxsize=512)
            d[role] = q
        return q

def _end_audio(cid):
    """يوقف أي بثّ صوتي نشط لهذه المكالمة بإرسال إشارة إنهاء لطوابير الطرفين."""
    d = CALL_AUDIO.get(cid)
    if d:
        for aq in list(d.values()):
            try:
                aq.put_nowait(None)   # None = إشارة إنهاء البثّ
            except Exception:
                pass

def _peer_role(role):
    return 'user' if role == 'admin' else 'admin'

def call_role_for(cid):
    """يحدد دور المستخدم الحالي في مكالمة عميل معيّن، أو None لو غير مصرّح له."""
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return 'admin'
    if current_user.is_authenticated and isinstance(current_user, Customer) and current_user.id == cid:
        return 'user'
    return None

def call_button_html(cid, peer_online=False):
    """زر بدء المكالمة الصوتية مع مؤشّر الحضور (أونلاين)."""
    dot_cls = 'online' if peer_online else ''
    return f'''<button type="button" id="callBtn" class="call-btn" title="مكالمة صوتية">
        <span class="call-presence {dot_cls}" id="callPresence"></span>
        <i class="bi bi-telephone-fill"></i>
        <span class="call-btn-label" id="callBtnLabel">اتصال صوتي</span>
    </button>'''

_CALL_JS_TEMPLATE = r'''<script>
(function(){
    var CID=__CID__, ROLE="__ROLE__", PEER_NAME="__PEER_NAME__", PEER_INITIAL="__PEER_INITIAL__";
    var POLL_URL="__POLL_URL__", SIGNAL_URL="__SIGNAL_URL__";
    // روابط ترحيل الصوت عبر HTTP: بثّ ��تدفّق للنزول + POST للطلوع (بدون WebSocket)
    var RECV_URL="__RECV_URL__", SEND_URL="__SEND_URL__";
    var RATE=16000;   // معدّل عيّنات المكالمة (أحادي = صوت واضح وخفيف)

    var callBtn=document.getElementById("callBtn");
    var presenceDot=document.getElementById("callPresence");
    var btnLabel=document.getElementById("callBtnLabel");
    var canStart=(ROLE==="admin");   // الأدمن فقط هو من يبدأ الرنين

    var localStream=null;
    // ---- ترحيل الصوت عبر HTTP (نزول متدفّق + طلوع POST، بدون أي خدمة خارجية) ----
    // نلتقط الميكروفون PCM ونرسله عبر POST متتابعة، ونستقبل صوت الطرف الآخر عبر
    // ردّ HTTP متدفّق يبقى مفتوحاً. HTTP عادي = يعمل بثبات على خادم Flask محلياً.
    var recvAbort=null;          // للتحكم في إلغاء بثّ الاستقبال
    var sendBuf=[];              // قطع PCM المتراكمة قبل الإرسال
    var sendTimer=null;          // مؤقّت دفع الصوت المتراكم
    var sending=false;           // طلب إرسال قيد التنفيذ (يمنع تكدّس الاتصالات)
    var micCtx=null, micNode=null, micSource=null, micSilent=null;
    var playCtx=null, playTime=0, playGain=null;
    var speakerOn=true;          // true = سبيكر (مكبّر) / false = سماعة المكالمة
    var relayOn=false;           // نشط أثناء المكالمة
    var state="idle";           // idle | calling | ringing | connecting | connected
    var pendingOffer=null, peerOnline=false;
    var overlay=null, statusEl=null, timerEl=null, actionsEl=null, avatarEl=null;
    var timerInt=null, timerStart=0, pollTimer=null, ringOsc=null, ringInt=null, muted=false;

    function fmt(s){s=Math.max(0,Math.round(s));var m=Math.floor(s/60);var ss=(""+(s%60)).padStart(2,"0");return m+":"+ss;}

    // ---------- نغمة الرنين ----------
    var AC=null;
    function beep(freq,dur){
        try{
            if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();
            var o=AC.createOscillator(),g=AC.createGain();
            o.type="sine";o.frequency.value=freq;o.connect(g);g.connect(AC.destination);
            g.gain.setValueAtTime(0.0001,AC.currentTime);
            g.gain.exponentialRampToValueAtTime(0.15,AC.currentTime+0.02);
            g.gain.exponentialRampToValueAtTime(0.0001,AC.currentTime+dur);
            o.start();o.stop(AC.currentTime+dur);
        }catch(e){}
    }
    function startRing(incoming){
        stopRing();
        var f=incoming?520:440;
        beep(f,0.4);
        ringInt=setInterval(function(){beep(f,0.4);},incoming?1400:2500);
    }
    function stopRing(){ if(ringInt){clearInterval(ringInt);ringInt=null;} }

    // ---------- الواجهة ----------
    function buildOverlay(){
        if(overlay) return;
        overlay=document.createElement("div");
        overlay.className="call-overlay";
        overlay.innerHTML=''+
            '<div class="call-modal">'+
            '  <div class="call-avatar"><span>'+PEER_INITIAL+'</span><span class="call-ring"></span></div>'+
            '  <div class="call-peer-name">'+PEER_NAME+'</div>'+
            '  <div class="call-status" id="callStatus">...</div>'+
            '  <div class="call-timer num" id="callTimer" style="display:none">0:00</div>'+
            '  <div class="call-actions" id="callActions"></div>'+
            '</div>';
        document.body.appendChild(overlay);
        statusEl=overlay.querySelector("#callStatus");
        timerEl=overlay.querySelector("#callTimer");
        actionsEl=overlay.querySelector("#callActions");
        avatarEl=overlay.querySelector(".call-avatar");
    }
    function showOverlay(){ buildOverlay(); overlay.classList.add("show"); }
    function hideOverlay(){ if(overlay)overlay.classList.remove("show"); }

    function btn(cls,icon,label){ return '<button type="button" class="'+cls+'" data-act="'+label+'"><i class="bi '+icon+'"></i></button>'; }
    function setActions(){
        if(!actionsEl)return;
        if(state==="ringing"){
            actionsEl.innerHTML=btn("call-ic call-accept","bi-telephone-fill","accept")+btn("call-ic call-decline","bi-telephone-x-fill","decline");
        }else{
            var m=muted?"bi-mic-mute-fill":"bi-mic-fill";
            var sp=speakerOn?"bi-volume-up-fill":"bi-telephone-fill";   // سبيكر / سماعة المكالمة
            var spCls=speakerOn?"call-ic call-spk on":"call-ic call-spk";
            actionsEl.innerHTML='<button type="button" class="call-ic call-mute" data-act="mute"><i class="bi '+m+'"></i></button>'+
                '<button type="button" class="'+spCls+'" data-act="speaker" title="السبيكر"><i class="bi '+sp+'"></i></button>'+
                btn("call-ic call-decline","bi-telephone-x-fill","hangup");
        }
    }
    function setStatus(txt,animate){
        if(statusEl)statusEl.textContent=txt;
        if(avatarEl){ if(animate)avatarEl.classList.add("pulsing"); else avatarEl.classList.remove("pulsing"); }
    }

    document.addEventListener("click",function(e){
        var b=e.target.closest && e.target.closest("[data-act]");
        if(!b||!overlay||!overlay.classList.contains("show"))return;
        var act=b.getAttribute("data-act");
        if(act==="accept")acceptCall();
        else if(act==="decline"){ send("decline"); teardown("تم الرفض"); }
        else if(act==="hangup"){ send("hangup"); teardown("انتهت المكالمة"); }
        else if(act==="mute")toggleMute();
        else if(act==="speaker")toggleSpeaker();
    });

    function toggleMute(){
        if(!localStream)return;
        muted=!muted;
        localStream.getAudioTracks().forEach(function(t){t.enabled=!muted;});
        setActions();
    }

    // ---------- الإشارات ----------
    function send(type,data){
        return fetch(SIGNAL_URL,{method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({type:type,data:data||null})}).catch(function(){});
    }

    async function ensureMic(){
        if(localStream)return true;
        if(!window.isSecureContext){ alert("المكالمة تحتاج اتصال آمن (HTTPS)."); return false; }
        if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){ alert("متصفحك لا يدعم المكالمات الصوتية."); return false; }
        try{
            localStream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
            return true;
        }catch(err){
            if(err&&(err.name==="NotAllowedError"||err.name==="SecurityError"))
                alert("تم رفض إذن الميكروفون. اضغط على القفل بجانب الرابط واسمح بالميكروفون.");
            else alert("تعذّر ا��وصول للميكروفون.");
            return false;
        }
    }

    // ---------- محرّك ترحيل الصوت عبر بثّ HTTP ----------
    // تحويل عيّنات float [-1,1] إلى PCM 16-bit
    function floatTo16(f32){
        var out=new Int16Array(f32.length);
        for(var i=0;i<f32.length;i++){ var s=f32[i]; if(s>1)s=1; else if(s<-1)s=-1; out[i]=s<0?s*0x8000:s*0x7FFF; }
        return out;
    }
    // تقليل معدّل العيّنات (مثلاً 48kHz -> 16kHz) بمتوسّط بسيط
    function downsample(buf,inRate,outRate){
        if(outRate>=inRate)return buf;
        var ratio=inRate/outRate, newLen=Math.round(buf.length/ratio);
        var res=new Float32Array(newLen), pos=0, i=0;
        while(i<newLen){
            var next=Math.round((i+1)*ratio), sum=0, cnt=0;
            for(var j=pos;j<next&&j<buf.length;j++){ sum+=buf[j]; cnt++; }
            res[i]=cnt?sum/cnt:0; pos=next; i++;
        }
        return res;
    }

    // دمج قطع PCM المتراكمة وإرسالها في طلب POST واحد.
    // نمنع تكدّس الاتصالات: لا نبدأ طلباً جديداً قبل انتهاء السابق (sending)،
    // وإذا تأخّر الطرف الآخر نُسقط الأقدم حتى لا يتضخّم التأخير (سقف ~1.5 ثانية).
    function flushSend(){
        if(!relayOn||sending||!sendBuf.length)return;
        var total=0,i; for(i=0;i<sendBuf.length;i++)total+=sendBuf[i].length;
        // نُسقط فقط عند تراكم كبير جداً (الطرف الآخر متوقّف تماماً) حتى لا نفقد صوتاً
        // في الظروف العادية — الإسقاط المبكّر كان أحد أسباب التقطيع.
        var CAP=RATE*5|0;   // ~5 ثوانٍ
        while(total>CAP&&sendBuf.length>1){ total-=sendBuf[0].length; sendBuf.shift(); }
        var merged=new Int16Array(total),off=0;
        for(i=0;i<sendBuf.length;i++){ merged.set(sendBuf[i],off); off+=sendBuf[i].length; }
        sendBuf=[];
        sending=true;
        try{
            fetch(SEND_URL,{method:"POST",headers:{"Content-Type":"application/octet-stream"},
                body:merged.buffer,cache:"no-store"})
                .then(function(){ sending=false; })
                .catch(function(){ sending=false; });
        }catch(e){ sending=false; }
    }

    // إذا انقطع بثّ الاستقبال أثناء مكالمة قائمة، لا نُنهي المكالمة بل نعيد فتحه
    // فوراً (الإنهاء الحقيقي يأتي فقط من إشارة hangup عبر الاستفسار). هذا يمنع
    // "تطفية المكالمة" عند أي انقطاع لحظي للبثّ من الخادم التطويري.
    function recvDropped(){
        if(!relayOn)return;
        if(state==="connected"){ setTimeout(function(){ if(relayOn)startRecv(); },150); }
        else teardown("انقطع الاتصال");
    }
    // فتح بثّ الاستقبال المتدفّق: يقرأ إطارات [4 بايت طول][PCM] ويشغّلها فوراً
    function startRecv(){
        try{ recvAbort=new AbortController(); }catch(e){ recvAbort=null; }
        var opts={cache:"no-store"};
        if(recvAbort)opts.signal=recvAbort.signal;
        fetch(RECV_URL,opts).then(function(resp){
            if(!resp.ok||!resp.body){ recvDropped(); return; }
            onConnected();   // البثّ فُتح = المكالمة متصلة
            var reader=resp.body.getReader();
            var buf=new Uint8Array(0);
            function append(a,b){ var c=new Uint8Array(a.length+b.length); c.set(a,0); c.set(b,a.length); return c; }
            function pump(){
                reader.read().then(function(res){
                    if(res.done){ recvDropped(); return; }
                    if(res.value&&res.value.length)buf=append(buf,res.value);
                    while(buf.length>=4){
                        var len=((buf[0]<<24)|(buf[1]<<16)|(buf[2]<<8)|buf[3])>>>0;
                        if(len===0){ buf=buf.subarray(4); continue; }   // نبضة إبقاء حيّ
                        if(buf.length<4+len)break;
                        var payload=buf.subarray(4,4+len);
                        var n=payload.length>>1, pcm=new Int16Array(n);
                        var dv=new DataView(payload.buffer,payload.byteOffset,payload.length);
                        for(var i=0;i<n;i++)pcm[i]=dv.getInt16(i*2,true);
                        playPcm(pcm);
                        buf=buf.subarray(4+len);
                    }
                    if(relayOn)pump();
                }).catch(function(){ recvDropped(); });
            }
            pump();
        }).catch(function(){ recvDropped(); });
    }

    // بدء التقاط الميكروفون + فتح بثّ الاستقبال + مؤقّت الإرسال
    function startRelay(){
        if(relayOn)return;
        relayOn=true;
        try{
            var ACtx=window.AudioContext||window.webkitAudioContext;
            playCtx=new ACtx(); playTime=0;
            try{ if(playCtx.state==="suspended")playCtx.resume(); }catch(e){}
            // تشغيل مباشر منخفض التأخير: كل الصوت يمرّ عبر عقدة كسب رئيسية ثم للمخرج.
            // (تجنّبنا توجيهه عبر عنصر <audio> لأنه يسبّب تقطيعاً على الموبايل.)
            playGain=playCtx.createGain(); playGain.gain.value=1;
            playGain.connect(playCtx.destination);
            applySpeaker();   // نطبّق وضع المخرج الحالي (سبيكر/سماعة)
            startRecv();

            micCtx=new ACtx();
            micSource=micCtx.createMediaStreamSource(localStream);
            micNode=micCtx.createScriptProcessor(2048,1,1);
            micSilent=micCtx.createGain(); micSilent.gain.value=0;  // لا نسمع صوتنا
            micSource.connect(micNode); micNode.connect(micSilent); micSilent.connect(micCtx.destination);
            micNode.onaudioprocess=function(e){
                if(!relayOn||muted)return;
                var input=e.inputBuffer.getChannelData(0);
                sendBuf.push(floatTo16(downsample(input,micCtx.sampleRate,RATE)));
            };
            sendTimer=setInterval(flushSend,160);   // ندفع الصوت المتراكم كل 160ms
        }catch(err){ teardown("تعذّر تشغيل الصوت"); }
    }

    // مخزّن اهتزاز (jitter buffer): الصوت يصل دفعات عبر HTTP كل ~160ms + تذبذب
    // الشبكة، فنسمح بتقديم يصل حتى ~1.2s قبل أن نقصّ. القصّ القاسي هو ما كان
    // يسبّب التقطيع، لذا وسّعنا المدى ليمرّ الصوت كاملاً بسلاسة.
    var JITTER=0.12, MAXLEAD=1.2;
    function playPcm(int16){
        if(!playCtx||!playGain||int16.length===0)return;
        var now=playCtx.currentTime;
        if(playTime<now+0.02)playTime=now+JITTER;   // إعادة بناء تأخير صغير بعد أي انقطاع
        var lead=(playTime-now)+(int16.length/RATE);
        if(lead>MAXLEAD){   // تأخّرنا كثيراً: نقفز للأمام بدل قصّ العيّنات (أنظف صوتاً)
            playTime=now+JITTER;
        }
        var f32=new Float32Array(int16.length);
        for(var i=0;i<int16.length;i++){ f32[i]=int16[i]/0x8000; }
        var buf=playCtx.createBuffer(1,f32.length,RATE);
        buf.copyToChannel(f32,0);
        var srcNode=playCtx.createBufferSource();
        srcNode.buffer=buf;
        srcNode.connect(playGain);   // عبر عقدة الكسب الرئيسية ثم المخرج
        srcNode.start(playTime); playTime+=buf.duration;
    }

    // ---------- التبديل بين السبيكر وسماعة المكالمة ----------
    // الويب لا يوفّر واجهة موحّدة لاختيار "سماعة الأذن"، لذا نجمع طريقتين:
    // (١) setSinkId على الـ AudioContext نفسه لتحويل المخرج فعلياً حيثما يُدعم،
    // (٢) تغيير مستوى الكسب (سبيكر أعلى / سماعة أهدأ) ليكون للتبديل أثر مسموع
    //     مؤكّد على كل الأجهزة حتى لو لم يتوفّر تحويل المخرج.
    function applySpeaker(){
        if(playGain){
            try{ playGain.gain.setTargetAtTime(speakerOn?1.0:0.5, playCtx.currentTime, 0.02); }catch(e){ playGain.gain.value=speakerOn?1.0:0.5; }
        }
        // تحويل المخرج الفعلي عبر AudioContext.setSinkId عند دعم المتصفح له
        if(playCtx&&typeof playCtx.setSinkId==="function"&&navigator.mediaDevices&&navigator.mediaDevices.enumerateDevices){
            navigator.mediaDevices.enumerateDevices().then(function(list){
                var outs=list.filter(function(d){return d.kind==="audiooutput";});
                if(outs.length<2)return;   // لا يوجد أكثر من مخرج لنبدّل بينه
                var target=null,i,l;
                for(i=0;i<outs.length;i++){
                    l=(outs[i].label||"").toLowerCase();
                    if(speakerOn&&(l.indexOf("speaker")>=0||l.indexOf("مكبر")>=0||l.indexOf("loud")>=0)){ target=outs[i]; break; }
                    if(!speakerOn&&(l.indexOf("earpiece")>=0||l.indexOf("receiver")>=0||l.indexOf("سماع")>=0)){ target=outs[i]; break; }
                }
                if(!target)target=speakerOn?outs[0]:outs[outs.length-1];
                if(target){ try{ var r=playCtx.setSinkId(target.deviceId); if(r&&r.catch)r.catch(function(){}); }catch(e){} }
            }).catch(function(){});
        }
    }
    function toggleSpeaker(){
        speakerOn=!speakerOn;
        try{ if(playCtx&&playCtx.state==="suspended")playCtx.resume(); }catch(e){}
        applySpeaker(); setActions();
    }

    // ---------- إطفاء الشاشة عند تقريبها من الأذن ----------
    // لا يمكن للويب إطفاء شاشة الهاتف فعلياً، لكن عند اقتراب الوجه نعرض غطاءً
    // أسود يبتلع كل اللمسات، فلا يحدث ضغط خاطئ على "إنهاء المكالمة" بالخدّ/الأذن.
    var proxSensor=null, proxCover=null, proxNear=false;
    function showProxCover(on){
        proxNear=on;
        if(on){
            if(!proxCover){
                proxCover=document.createElement("div");
                proxCover.id="callProxCover";
                proxCover.style.cssText="position:fixed;inset:0;z-index:2147483646;background:#000;touch-action:none;";
                // نبتلع كل مؤشّرات اللمس أثناء القرب (منع الضغط الخاطئ)
                ["pointerdown","pointerup","click","touchstart","touchend","mousedown","mouseup"].forEach(function(ev){
                    proxCover.addEventListener(ev,function(e){ e.preventDefault(); e.stopPropagation(); },{passive:false,capture:true});
                });
                document.body.appendChild(proxCover);
            }
            proxCover.style.display="block";
        }else if(proxCover){ proxCover.style.display="none"; }
    }
    function onProx(e){
        var near=false;
        if(typeof e.near==="boolean")near=e.near;                 // حدث userproximity القديم
        else if(typeof e.value==="number")near=e.value<(e.max||5)/2; // مستشعر ProximitySensor
        else if(typeof e.distance==="number")near=e.distance<5;
        showProxCover(near);
    }
    function startProximity(){
        // 1) الحدث القديم userproximity (فايرفوكس للجوال)
        if("ondeviceproximity" in window || "onuserproximity" in window){
            window.addEventListener("userproximity",onProx);
            window.addEventListener("deviceproximity",onProx);
        }
        // 2) Generic Sensor API (كروم مع تفعيل الميزة)
        try{
            if("ProximitySensor" in window){
                proxSensor=new window.ProximitySensor({frequency:5});
                proxSensor.addEventListener("reading",function(){ showProxCover(!!proxSensor.near); });
                proxSensor.addEventListener("error",function(){});
                proxSensor.start();
            }
        }catch(e){ proxSensor=null; }
    }
    function stopProximity(){
        try{ window.removeEventListener("userproximity",onProx); }catch(e){}
        try{ window.removeEventListener("deviceproximity",onProx); }catch(e){}
        try{ if(proxSensor){ proxSensor.stop(); proxSensor=null; } }catch(e){}
        showProxCover(false);
    }

    function stopMedia(){
        relayOn=false; sending=false;
        try{ if(recvAbort)recvAbort.abort(); }catch(e){} recvAbort=null;
        try{ if(sendTimer){ clearInterval(sendTimer); sendTimer=null; } }catch(e){}
        sendBuf=[];
        try{ if(micNode){ micNode.onaudioprocess=null; micNode.disconnect(); } }catch(e){}
        try{ if(micSource)micSource.disconnect(); }catch(e){}
        try{ if(micSilent)micSilent.disconnect(); }catch(e){}
        try{ if(micCtx)micCtx.close(); }catch(e){}
        try{ if(playGain)playGain.disconnect(); }catch(e){}
        try{ if(playCtx)playCtx.close(); }catch(e){}
        stopProximity();
        micNode=micSource=micSilent=micCtx=playCtx=playGain=null; playTime=0;
    }

    // ---------- مكالمة صادرة ----------
    async function startCall(){
        if(state!=="idle")return;
        if(!peerOnline){ alert(PEER_NAME+" غير متصل بالموقع الآن، لا يمكن إجراء المكالمة."); return; }
        if(!(await ensureMic()))return;
        state="calling"; muted=false;
        showOverlay(); setActions(); setStatus("جارٍ الاتصال بـ "+PEER_NAME+"...",true); startRing(false);
        send("offer");   // رنين لدى الطرف الآخر
    }

    // ---------- مكالمة واردة ----------
    function incoming(offer){
        if(state!=="idle")return;
        pendingOffer=offer; state="ringing"; muted=false;
        showOverlay(); setActions(); setStatus(PEER_NAME+" يتصل بك...",true); startRing(true);
    }
    async function acceptCall(){
        if(state!=="ringing")return;
        if(!(await ensureMic())){ send("decline"); teardown(""); return; }
        stopRing(); state="connecting"; setStatus("جارٍ الربط...",true); setActions();
        // نبلّغ الأدمن بالقبول، والطرفان يفتحان اتصال الصوت فوراً
        send("answer");
        startRelay();
    }

    function onConnected(){
        if(state==="connected")return;
        state="connected"; stopRing(); setActions();
        setStatus("متصل الآن",false);
        timerEl.style.display=""; timerStart=Date.now();
        timerEl.textContent="0:00";
        timerInt=setInterval(function(){ timerEl.textContent=fmt((Date.now()-timerStart)/1000); },1000);
        startProximity();   // تفعيل غطاء إطفاء الشاشة عند تقريبها من الأذن
    }

    function teardown(msg){
        stopRing();
        if(timerInt){clearInterval(timerInt);timerInt=null;}
        stopMedia();
        if(localStream){ localStream.getTracks().forEach(function(t){t.stop();}); localStream=null; }
        var tap=document.getElementById("callTapHear"); if(tap)tap.remove();
        pendingOffer=null; muted=false;
        if(msg&&overlay){ setStatus(msg,false); if(timerEl)timerEl.style.display="none"; if(actionsEl)actionsEl.innerHTML="";
            setTimeout(hideOverlay,1200);
        }else hideOverlay();
        state="idle";
    }

    // ---------- معالجة الإشارات الواردة ----------
    async function handle(sig){
        var t=sig.type;
        if(t==="offer"){ incoming(sig.data); }
        else if(t==="answer"){
            if(state==="calling"){
                stopRing(); state="connecting"; setStatus("جارٍ الربط...",true);
                startRelay();   // الأدمن يفتح اتصال الصوت بعد قبول الطرف الآخر
            }
        }
        else if(t==="decline"){ teardown(PEER_NAME+" رفض المكالمة"); }
        else if(t==="cancel"){ teardown("أُلغيت المكالمة"); }
        else if(t==="hangup"){ teardown("انتهت المكالمة"); }
    }

    // ---------- حلقة الاستفسار (presence + signaling) ----------
    function updatePresence(on){
        peerOnline=on;
        if(presenceDot)presenceDot.classList.toggle("online",on);
        if(btnLabel)btnLabel.textContent = on ? "متصل الآن" : "غير متصل";
        if(callBtn)callBtn.classList.toggle("peer-online",on);
    }
    async function loop(){
        try{
            var r=await fetch(POLL_URL); var data=await r.json();
            if(data&&data.ok){
                updatePresence(!!data.peer_online);
                if(data.signals&&data.signals.length){ for(var i=0;i<data.signals.length;i++){ await handle(data.signals[i]); } }
            }
        }catch(e){}
        // الصوت يمر عبر بثّ HTTP؛ هذا الاستفسار فقط للحضور وإشارات الرنين
        var delay=(state==="idle")?2500:600;
        pollTimer=setTimeout(loop,delay);
    }
    loop();

    if(callBtn&&canStart)callBtn.addEventListener("click",function(){
        if(state==="idle")startCall();
    });
    window.addEventListener("beforeunload",function(){ if(state!=="idle")send(state==="calling"?"cancel":"hangup"); });
})();
</script>'''

def call_widget_script(cid, role, peer_name):
    peer_name = (peer_name or 'الطرف الآخر').replace('"', '')
    initial = (peer_name.strip()[:1] or '?')
    return (_CALL_JS_TEMPLATE
            .replace('__CID__', str(cid))
            .replace('__ROLE__', role)
            .replace('__PEER_NAME__', peer_name)
            .replace('__PEER_INITIAL__', initial)
            .replace('__RECV_URL__', url_for('call_recv', cid=cid))
            .replace('__SEND_URL__', url_for('call_send', cid=cid))
            .replace('__POLL_URL__', url_for('call_poll', cid=cid))
            .replace('__SIGNAL_URL__', url_for('call_signal', cid=cid)))

def support_page(cust):
    ChatMessage.query.filter_by(customer_id=cust.id, sender='admin', read_by_user=False).update({'read_by_user': True})
    db.session.commit()
    msgs = ChatMessage.query.filter_by(customer_id=cust.id).order_by(ChatMessage.created_at.asc()).all()
    content = f'''
    <div class="chat-wrap">
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-1">
            <h2 class="page-title fade-up mb-0"><i class="bi bi-headset"></i> المساعدة والدعم</h2>
        </div>
        <p style="color:var(--muted); margin-bottom:16px;">أهلاً {cust.name}، اكتب استفسارك وسيرد عليك فريق الدعم في أقرب وقت.</p>
        <div class="chat-box" id="chatBox">{render_messages(msgs)}</div>
        {chat_input_form()}
    </div>'''
    scripts = chat_widget_script(url_for('support_send'), url_for('support_poll'))
    scripts += call_widget_script(cust.id, 'user', 'فريق الدعم')
    return render_template_string(BASE_HTML, title='الدعم - Mo.palace', content=Markup(content), scripts=Markup(scripts))

def guest_support_page():
    uid = current_uid()
    ChatMessage.query.filter_by(uid=uid, customer_id=None, sender='admin', read_by_user=False).update({'read_by_user': True})
    db.session.commit()
    msgs = ChatMessage.query.filter_by(uid=uid, customer_id=None).order_by(ChatMessage.created_at.asc()).all()
    guest_name = session.get('guest_name', '')
    content = f'''
    <div class="chat-wrap">
        <h2 class="page-title fade-up"><i class="bi bi-headset"></i> المساعدة والدعم</h2>
        <div class="panel mb-3" style="padding:14px 16px; border-inline-start:4px solid var(--accent);">
            <div style="font-weight:700; margin-bottom:4px;"><i class="bi bi-info-circle me-1" style="color:var(--accent)"></i> محادثة بدون حساب</div>
            <p style="color:var(--muted); font-size:.88rem; margin:0;">تقدر تراسل الدعم مباشرة حتى لو مش مسجّل دخول (مثلاً نسيت كلمة السر أو عندك أي استفسار). لو حابب، اكتب اسمك عشان ��تعرف عليك.</p>
        </div>
        <div class="chat-box" id="chatBox">{render_messages(msgs)}</div>
        {chat_input_form(guest_name=guest_name)}
    </div>'''
    scripts = chat_widget_script(url_for('support_send'), url_for('support_poll'), guest=True)
    return render_template_string(BASE_HTML, title='الدعم - Mo.palace', content=Markup(content), scripts=Markup(scripts))

# ------- صفحات الأدمن: العملاء / المحادثات / الاسترجاع -------
def admin_customers_page():
    customers = Customer.query.all()
    data = []
    for c in customers:
        orders = Order.query.filter_by(customer_id=c.id).all()
        total_spent = sum(o.total for o in orders)
        unread = ChatMessage.query.filter_by(customer_id=c.id, sender='user', read_by_admin=False).count()
        last_msg = ChatMessage.query.filter_by(customer_id=c.id).order_by(ChatMessage.created_at.desc()).first()
        last_order = orders[0] if orders else None
        last = max([d for d in [last_msg.created_at if last_msg else None,
                                 orders[-1].created_at if orders else None] if d] or [c.created_at or datetime.min])
        data.append({'c': c, 'orders': len(orders), 'spent': total_spent, 'unread': unread, 'last': last})
    data.sort(key=lambda x: (x['unread'] > 0, x['last']), reverse=True)
    if not data:
        body = '<div class="glass-form text-center" style="padding:40px;"><i class="bi bi-people" style="font-size:2.4rem;color:var(--accent)"></i><p class="mt-2" style="color:var(--muted)">لا يوجد عملاء بعد</p></div>'
    else:
        rows = ''
        for d in data:
            c = d['c']
            badge = f'<span class="badge-rejected">{d["unread"]} جديد</span>' if d['unread'] else ''
            rows += f'''<tr>
                <td><strong>{c.name}</strong> {badge}<div style="color:var(--muted); font-size:.75rem; direction:ltr; text-align:right;">{c.phone}</div></td>
                <td class="num">{d['orders']}</td>
                <td class="num" style="color:var(--price); font-weight:800;">{d['spent']:.0f} ج.م</td>
                <td>{d['last'].strftime('%Y-%m-%d %H:%M') if d['last'] != datetime.min else '-'}</td>
                <td><a href="{url_for('admin_customer', cid=c.id)}" class="btn btn-accent btn-sm"><i class="bi bi-person-lines-fill me-1"></i> عرض / مساعدة</a></td>
            </tr>'''
        body = f'''<div class="table-responsive"><table class="table table-borderless table-clean mb-0">
            <thead><tr><th>العميل</th><th>الطلبات</th><th>إجمالي الشراء</th><th>آخر نشاط</th><th></th></tr></thead>
            <tbody>{rows}</tbody></table></div>'''
    content = f'<h4 class="section-title"><i class="bi bi-people"></i> العملاء ({len(data)})</h4>{body}'
    return render_template_string(ADMIN_BASE, title='العملاء - Mo.palace', content=Markup(content))

def admin_chats_page():
    convos = []
    for c in Customer.query.all():
        last_msg = ChatMessage.query.filter_by(customer_id=c.id).order_by(ChatMessage.created_at.desc()).first()
        if not last_msg:
            continue
        unread = ChatMessage.query.filter_by(customer_id=c.id, sender='user', read_by_admin=False).count()
        convos.append({'c': c, 'last_msg': last_msg, 'unread': unread})
    convos.sort(key=lambda x: (x['unread'] > 0, x['last_msg'].created_at), reverse=True)
    if not convos:
        body = '<div class="glass-form text-center" style="padding:40px;"><i class="bi bi-chat-dots" style="font-size:2.4rem;color:var(--accent)"></i><p class="mt-2" style="color:var(--muted)">لا توجد محادثات بعد</p></div>'
    else:
        rows = ''
        for conv in convos:
            c = conv['c']
            badge = f'<span class="badge-rejected">{conv["unread"]}</span>' if conv['unread'] else ''
            preview = (conv['last_msg'].body[:45] + '…') if len(conv['last_msg'].body) > 45 else conv['last_msg'].body
            sender_lbl = 'العميل' if conv['last_msg'].sender == 'user' else 'أنت'
            rows += f'''<tr>
                <td><strong>{c.name}</strong> {badge}</td>
                <td style="color:var(--muted); font-size:.88rem;">{sender_lbl}: {preview}</td>
                <td class="num" style="font-size:.8rem;">{conv['last_msg'].created_at.strftime('%m-%d %H:%M')}</td>
                <td><a href="{url_for('admin_customer', cid=c.id)}" class="btn btn-accent btn-sm"><i class="bi bi-reply me-1"></i> رد</a></td>
            </tr>'''
        body = f'''<div class="table-responsive"><table class="table table-borderless table-clean mb-0">
            <thead><tr><th>العميل</th><th>آخر رسالة</th><th>الوقت</th><th></th></tr></thead>
            <tbody>{rows}</tbody></table></div>'''
    content = f'<h4 class="section-title"><i class="bi bi-chat-dots"></i> المحادثات</h4>{body}'
    return render_template_string(ADMIN_BASE, title='المحادثات - Mo.palace', content=Markup(content))

def admin_guest_chats_page():
    # محادثات الزوّار غير المسجّلين (customer_id فارغ) مجمّعة حسب uid
    guest_msgs = ChatMessage.query.filter_by(customer_id=None).order_by(ChatMessage.created_at.desc()).all()
    convos = {}
    for m in guest_msgs:
        if m.uid not in convos:
            convos[m.uid] = {'uid': m.uid, 'name': m.customer_name or 'زائر', 'last_msg': m, 'unread': 0}
        if m.sender == 'user' and not m.read_by_admin:
            convos[m.uid]['unread'] += 1
        if m.sender == 'user' and (convos[m.uid]['name'] in (None, 'زائر')) and m.customer_name:
            convos[m.uid]['name'] = m.customer_name
    conv_list = list(convos.values())
    conv_list.sort(key=lambda x: (x['unread'] > 0, x['last_msg'].created_at), reverse=True)
    if not conv_list:
        body = '<div class="glass-form text-center" style="padding:40px;"><i class="bi bi-person-badge" style="font-size:2.4rem;color:var(--accent)"></i><p class="mt-2" style="color:var(--muted)">لا توجد محادثات من زوّار غير مسجّلين بعد</p></div>'
    else:
        rows = ''
        for conv in conv_list:
            badge = f'<span class="badge-rejected">{conv["unread"]}</span>' if conv['unread'] else ''
            preview = (conv['last_msg'].body[:45] + '…') if len(conv['last_msg'].body) > 45 else conv['last_msg'].body
            sender_lbl = 'الزائر' if conv['last_msg'].sender == 'user' else 'أنت'
            rows += f'''<tr>
                <td><strong>{conv['name']}</strong> {badge}<div style="color:var(--muted); font-size:.7rem;">زائر غير مسجّل</div></td>
                <td style="color:var(--muted); font-size:.88rem;">{sender_lbl}: {preview}</td>
                <td class="num" style="font-size:.8rem;">{conv['last_msg'].created_at.strftime('%m-%d %H:%M')}</td>
                <td><a href="{url_for('admin_guest_chat', uid=conv['uid'])}" class="btn btn-accent btn-sm"><i class="bi bi-reply me-1"></i> رد</a></td>
            </tr>'''
        body = f'''<div class="table-responsive"><table class="table table-borderless table-clean mb-0">
            <thead><tr><th>الزائر</th><th>آخر رسالة</th><th>الوقت</th><th></th></tr></thead>
            <tbody>{rows}</tbody></table></div>'''
    content = f'<h4 class="section-title"><i class="bi bi-person-badge"></i> محادثات الزوّار</h4>{body}'
    return render_template_string(ADMIN_BASE, title='محادثات الزوّار - Mo.palace', content=Markup(content))

def admin_guest_chat_page(uid):
    ChatMessage.query.filter_by(uid=uid, customer_id=None, sender='user', read_by_admin=False).update({'read_by_admin': True})
    db.session.commit()
    msgs = ChatMessage.query.filter_by(uid=uid, customer_id=None).order_by(ChatMessage.created_at.asc()).all()
    guest_name = 'زائر'
    for m in msgs:
        if m.sender == 'user' and m.customer_name:
            guest_name = m.customer_name
    chat_html = f'''<h5 class="section-title"><i class="bi bi-chat-dots"></i> المحادثة</h5>
        <div class="chat-box" id="chatBox">{render_messages(msgs, admin_view=True)}</div>
        {chat_input_form(placeholder='اكتب ردك للزائر...')}'''
    content = f'''
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h4 class="section-title mb-0"><i class="bi bi-person-badge"></i> {guest_name} <span style="color:var(--muted); font-size:.8rem; font-weight:600;">(زائر غير مسجّل)</span></h4>
        <a href="{url_for('admin_guest_chats')}" class="btn btn-outline-secondary btn-sm" style="border-radius:11px;"><i class="bi bi-arrow-right me-1"></i> محادثات الزوّار</a>
    </div>
    <div class="glass-form">{chat_html}</div>'''
    scripts = chat_widget_script(url_for('admin_guest_reply', uid=uid), url_for('admin_guest_chat_poll', uid=uid))
    return render_template_string(ADMIN_BASE, title=f'{guest_name} - Mo.palace', content=Markup(content), scripts=Markup(scripts))

def admin_customer_page(cust):
    ChatMessage.query.filter_by(customer_id=cust.id, sender='user', read_by_admin=False).update({'read_by_admin': True})
    db.session.commit()

    orders = Order.query.filter_by(customer_id=cust.id).order_by(Order.created_at.desc()).all()
    total_spent = sum(o.total for o in orders)

    if cust.password_plain:
        pass_display = f'''<div style="font-weight:800; direction:ltr; text-align:right;" class="num">
            <span id="passText" style="letter-spacing:1px;">••••••••</span>
            <span id="passReal" style="display:none;">{cust.password_plain}</span>
            <button type="button" onclick="togglePass()" class="btn btn-sm btn-outline-secondary" style="border-radius:8px; padding:1px 8px; margin-inline-start:6px;"><i class="bi bi-eye" id="passIcon"></i></button>
        </div>'''
    else:
        pass_display = '<div style="color:var(--muted); font-size:.82rem;">غير متاحة (الحساب أُنشئ قبل التحديث) — اضبط كلمة سر جديدة بالأسفل</div>'

    info = f'''<div class="glass-form mb-3">
        <div class="row g-3">
            <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">الاسم</span><div style="font-weight:800; font-size:1.1rem;">{cust.name}</div></div>
            <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">الهاتف</span><div style="font-weight:700; direction:ltr; text-align:right;">{cust.phone}</div></div>
            <div class="col-12"><span style="color:var(--muted); font-size:.85rem;">العنوان</span><div>{cust.address}</div></div>
            <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">عدد الطلبات</span><div class="num" style="font-weight:800;">{len(orders)}</div></div>
            <div class="col-md-6"><span style="color:var(--muted); font-size:.85rem;">إجمالي الشراء</span><div class="num" style="font-weight:800; color:var(--price);">{total_spent:.0f} ج.م</div></div>
            <div class="col-12"><span style="color:var(--muted); font-size:.85rem;"><i class="bi bi-key-fill me-1" style="color:var(--accent)"></i>كلمة السر</span>{pass_display}</div>
        </div>
    </div>
    <div class="glass-form mb-3">
        <h6 style="font-weight:800; margin-bottom:12px;"><i class="bi bi-shield-lock me-1" style="color:var(--accent)"></i> تغيير كلمة سر العميل</h6>
        <form method="POST" action="{url_for('admin_change_customer_password', cid=cust.id)}" class="d-flex gap-2 flex-wrap">
            <input type="text" name="new_password" class="form-control" style="flex:1; min-width:180px;" placeholder="كلمة السر الجديدة (6 أحرف على الأقل)" required minlength="6">
            <button class="btn btn-accent" type="submit"><i class="bi bi-check-lg me-1"></i> حفظ</button>
        </form>
    </div>'''

    if orders:
        order_rows = ''
        for o in orders:
            status_badge = '<span class="badge-confirmed">مؤكد</span>' if o.confirmed else '<span class="badge-pending">معلق</span>'
            order_rows += f'<tr><td class="num" style="font-weight:800;">#{o.id}</td><td class="num">{o.total:.0f} ج.م</td><td>{o.payment_method}</td><td>{status_badge}</td><td class="num" style="font-size:.8rem;">{o.created_at.strftime("%Y-%m-%d")}</td><td><a href="{url_for("admin_order", oid=o.id)}" class="btn btn-sm btn-outline-secondary" style="border-radius:9px;"><i class="bi bi-eye"></i></a></td></tr>'
        orders_html = f'''<h5 class="section-title"><i class="bi bi-receipt"></i> طلبات العميل</h5>
            <div class="table-responsive mb-3"><table class="table table-borderless table-clean mb-0">
            <thead><tr><th>رقم</th><th>الإجمالي</th><th>الدفع</th><th>الحالة</th><th>التاريخ</th><th></th></tr></thead>
            <tbody>{order_rows}</tbody></table></div>'''
    else:
        orders_html = '<div class="alert alert-info">لا توجد طلبات لهذا العميل.</div>'

    rets = ReturnRequest.query.filter_by(customer_id=cust.id).order_by(ReturnRequest.created_at.desc()).all()
    returns_html = ''
    if rets:
        rrows = ''
        for ret in rets:
            product = db.session.get(Product, ret.product_id)
            if ret.status == 'مقبول':
                badge = '<span class="badge-confirmed">مقبول</span>'
            elif ret.status == 'مرفوض':
                badge = '<span class="badge-rejected">مرفوض</span>'
            else:
                badge = '<span class="badge-pending">قيد المراجعة</span>'
            rrows += f'<tr><td>{product.name if product else "منتج"}</td><td style="color:var(--muted); font-size:.85rem;">{ret.reason}</td><td>{badge}</td><td><a href="{url_for("admin_order", oid=ret.order_id)}" class="btn btn-sm btn-outline-secondary" style="border-radius:9px;">طلب #{ret.order_id}</a></td></tr>'
        returns_html = f'''<h5 class="section-title mt-2"><i class="bi bi-arrow-return-left"></i> طلبات الاس��رجاع</h5>
            <div class="table-responsive mb-3"><table class="table table-borderless table-clean mb-0">
            <thead><tr><th>المنتج</th><th>السبب</th><th>الحالة</th><th></th></tr></thead><tbody>{rrows}</tbody></table></div>'''

    msgs = ChatMessage.query.filter_by(customer_id=cust.id).order_by(ChatMessage.created_at.asc()).all()
    chat_html = f'''<h5 class="section-title"><i class="bi bi-chat-dots"></i> المحادثة</h5>
        <div class="chat-box" id="chatBox">{render_messages(msgs, admin_view=True)}</div>
        {chat_input_form(placeholder='اكتب ردك للعميل...')}'''

    content = f'''
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h4 class="section-title mb-0"><i class="bi bi-person-lines-fill"></i> {cust.name}</h4>
        <div class="d-flex align-items-center gap-2 flex-wrap">
            {call_button_html(cust.id)}
            <a href="{url_for('admin_customers')}" class="btn btn-outline-secondary btn-sm" style="border-radius:11px;"><i class="bi bi-arrow-right me-1"></i> العملاء</a>
        </div>
    </div>
    <div class="row g-4">
        <div class="col-lg-6">
            {info}
            {orders_html}
            {returns_html}
        </div>
        <div class="col-lg-6">
            {chat_html}
        </div>
    </div>'''

    scripts = f'''<script>
        function togglePass(){{
            const t=document.getElementById('passText'), r=document.getElementById('passReal'), ic=document.getElementById('passIcon');
            if(t.style.display==='none'){{t.style.display='';r.style.display='none';ic.className='bi bi-eye';}}
            else{{t.style.display='none';r.style.display='';ic.className='bi bi-eye-slash';}}
        }}
    </script>''' + chat_widget_script(url_for('admin_customer_reply', cid=cust.id), url_for('admin_customer_poll', cid=cust.id)) \
        + call_widget_script(cust.id, 'admin', cust.name)
    return render_template_string(ADMIN_BASE, title=f'{cust.name} - Mo.palace', content=Markup(content), scripts=Markup(scripts))

def admin_returns_page():
    rets = ReturnRequest.query.order_by(ReturnRequest.created_at.desc()).all()
    if not rets:
        body = '<div class="glass-form text-center" style="padding:40px;"><i class="bi bi-arrow-return-left" style="font-size:2.4rem;color:var(--accent)"></i><p class="mt-2" style="color:var(--muted)">لا توجد طلبات استرجاع</p></div>'
    else:
        cards = ''
        for ret in rets:
            product = db.session.get(Product, ret.product_id)
            order = db.session.get(Order, ret.order_id)
            cust = db.session.get(Customer, ret.customer_id) if ret.customer_id else None
            cust_name = cust.name if cust else (order.customer_name if order else '-')
            amount = return_amount(ret)
            if ret.status == 'مقبول':
                badge = '<span class="badge-confirmed">مقبول</span>'
            elif ret.status == 'مرفوض':
                badge = '<span class="badge-rejected">مرفوض</span>'
            else:
                badge = '<span class="badge-pending">قيد المراجعة</span>'
            note_html = f'<div class="mt-1" style="color:var(--ink-2); font-size:.85rem;"><i class="bi bi-chat-left-text me-1" style="color:var(--accent)"></i>ردك: {ret.admin_note}</div>' if ret.admin_note else ''
            if ret.status == 'قيد المراجعة':
                actions = f'''
                <form method="POST" action="{url_for('admin_return_update', rid=ret.id)}" class="mt-3">
                    <textarea name="admin_note" class="form-control mb-2" rows="2" placeholder="ملاحظة / رد للعميل (اختياري)"></textarea>
                    <div class="d-flex gap-2 flex-wrap">
                        <button name="action" value="accept" class="btn btn-accent btn-sm"><i class="bi bi-check-lg me-1"></i> قبول</button>
                        <button name="action" value="reject" class="btn btn-outline-danger btn-sm" style="border-radius:11px;"><i class="bi bi-x-lg me-1"></i> رفض</button>
                        <a href="{url_for('admin_order', oid=ret.order_id)}" class="btn btn-outline-secondary btn-sm" style="border-radius:11px;">الطلب #{ret.order_id}</a>
                    </div>
                </form>'''
            else:
                actions = f'''<div class="mt-2 d-flex gap-2 flex-wrap">
                    <form method="POST" action="{url_for('admin_return_update', rid=ret.id)}">
                        <input type="hidden" name="admin_note" value="{ret.admin_note or ''}">
                        <button name="action" value="pending" class="btn btn-outline-secondary btn-sm" style="border-radius:11px;"><i class="bi bi-arrow-counterclockwise me-1"></i> إعادة للمراجعة</button>
                    </form>
                    <a href="{url_for('admin_order', oid=ret.order_id)}" class="btn btn-outline-secondary btn-sm" style="border-radius:11px;">الطلب #{ret.order_id}</a>
                </div>'''
            deduct_note = f'<span style="color:var(--price); font-weight:700;"> • يُخصم {amount:.0f} ج.م من الأرباح</span>' if ret.status == 'مقبول' else ''
            cards += f'''<div class="glass-form mb-3">
                <div class="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-2">
                    <div><strong>{product.name if product else "منتج"}</strong> <span style="color:var(--muted); font-size:.85rem;">— {cust_name}</span></div>
                    {badge}
                </div>
                <div style="color:var(--muted); font-size:.88rem;">السبب: {ret.reason}</div>
                <div style="color:var(--muted); font-size:.78rem; margin-top:4px;"><i class="bi bi-calendar3 me-1"></i>{ret.created_at.strftime('%Y-%m-%d %H:%M')} • طلب #{ret.order_id}{deduct_note}</div>
                {note_html}
                {actions}
            </div>'''
        body = cards
    content = f'''<h4 class="section-title"><i class="bi bi-arrow-return-left"></i> طلبات الا��ترجاع</h4>
        <div class="alert alert-warning mb-3"><i class="bi bi-info-circle me-1"></i> عند قبول الاسترجاع يتم خصم قيمة المنتج من صافي الأرباح تلقائياً، وإذا ألغيت الموافقة تعود القيمة للأرباح.</div>
        {body}'''
    return render_template_string(ADMIN_BASE, title='الاسترجاع - Mo.palace', content=Markup(content))

# ====================== المسارات ======================
@app.route('/')
def home():
    return home_page()

# -------- حسابات العملاء --------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_customer():
        return redirect(url_for('home'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        password = request.form.get('password', '')
        if not (name and phone and address and password):
            flash('يرجى ملء جميع الحقول', 'danger')
            return redirect(url_for('signup'))
        if len(password) < 6:
            flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
            return redirect(url_for('signup'))
        if Customer.query.filter_by(phone=phone).first():
            flash('رقم الهاتف مسجّل بالفعل، يمكنك تسجيل الدخول', 'warning')
            return redirect(url_for('login'))
        hashed = bcrypt.generate_password_hash(password).decode('utf-8')
        customer = Customer(name=name, phone=phone, address=address, password=hashed, password_plain=password)
        db.session.add(customer)
        db.session.commit()
        link_orders_to_customer(customer)
        login_user(customer)
        flash(f'أهلاً بك {name}! تم إنشاء حسابك بنجاح', 'success')
        return redirect(url_for('home'))
    return signup_page()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_customer():
        return redirect(url_for('home'))
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        customer = Customer.query.filter_by(phone=phone).first()
        if customer and bcrypt.check_password_hash(customer.password, password):
            link_orders_to_customer(customer)
            login_user(customer)
            flash(f'أهلاً بعودتك {customer.name}!', 'success')
            nxt = request.args.get('next')
            return redirect(nxt or url_for('home'))
        flash('رقم الهاتف أو كلمة المرور غير صحيحة', 'danger')
    return login_page()

@app.route('/logout')
def logout():
    logout_user()
    flash('تم تسجيل الخروج', 'info')
    return redirect(url_for('home'))

@app.route('/account', methods=['GET', 'POST'])
@customer_required
def account():
    cust = current_customer()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        if not (name and phone and address):
            flash('يرجى ملء الاسم والهاتف والعنوان', 'danger')
            return redirect(url_for('account'))
        # التأكد أن رقم الهاتف غير مستخدم لحساب آخر
        other = Customer.query.filter(Customer.phone == phone, Customer.id != cust.id).first()
        if other:
            flash('رقم الهاتف مستخدم بحساب آخر', 'danger')
            return redirect(url_for('account'))
        cust.name = name
        cust.phone = phone
        cust.address = address
        if new_password:
            if not current_password or not bcrypt.check_password_hash(cust.password, current_password):
                flash('كلمة المرور الحالية غير صحيحة', 'danger')
                return redirect(url_for('account'))
            if len(new_password) < 6:
                flash('كل��ة المرور الجديدة يجب أن تكون 6 أحرف على الأقل', 'danger')
                return redirect(url_for('account'))
            cust.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            cust.password_plain = new_password
        db.session.commit()
        flash('تم حفظ التغييرات بنجاح', 'success')
        return redirect(url_for('account'))
    return account_page(cust)

# -------- الدعم --------
@app.route('/support')
def support():
    cust = current_customer()
    if cust:
        return support_page(cust)
    return guest_support_page()

@app.route('/support/send', methods=['POST'])
def support_send():
    cust = current_customer()
    if cust:
        msg = build_chat_message(uid=f'u{cust.id}', customer_id=cust.id, customer_name=cust.name,
                                 sender='user', read_by_admin=False, read_by_user=True)
    else:
        name = request.form.get('name', '').strip()
        if name:
            session['guest_name'] = name
        guest_name = session.get('guest_name') or 'زائر'
        msg = build_chat_message(uid=current_uid(), customer_id=None, customer_name=guest_name,
                                 sender='user', read_by_admin=False, read_by_user=True)
    if msg:
        db.session.add(msg)
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/support/poll')
def support_poll():
    cust = current_customer()
    if cust:
        ChatMessage.query.filter_by(customer_id=cust.id, sender='admin', read_by_user=False).update({'read_by_user': True})
        db.session.commit()
        msgs = ChatMessage.query.filter_by(customer_id=cust.id).order_by(ChatMessage.created_at.asc()).all()
    else:
        uid = current_uid()
        ChatMessage.query.filter_by(uid=uid, customer_id=None, sender='admin', read_by_user=False).update({'read_by_user': True})
        db.session.commit()
        msgs = ChatMessage.query.filter_by(uid=uid, customer_id=None).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({'html': render_messages(msgs)})

# عدّاد الإشعارات للعميل/الزائر (تحديث حي للأيقونة البرتقالية)
@app.route('/notify/count')
def notify_count():
    cust = current_customer()
    if cust:
        n = ChatMessage.query.filter_by(customer_id=cust.id, sender='admin', read_by_user=False).count()
    else:
        n = ChatMessage.query.filter_by(uid=current_uid(), customer_id=None, sender='admin', read_by_user=False).count()
    return jsonify({'count': n})

# ------- مكالمات صوتية: presence + signaling عبر polling -------
@app.route('/call/<int:cid>/poll')
def call_poll(cid):
    role = call_role_for(cid)
    if not role:
        return jsonify({'ok': False}), 403
    now = _time.time()
    peer = _peer_role(role)
    with _call_lock:
        pres = CALL_PRESENCE.setdefault(cid, {})
        pres[role] = now
        peer_online = (now - pres.get(peer, 0)) < CALL_PRESENCE_TTL
        q = CALL_SIGNALS.setdefault(cid, {'admin': [], 'user': []})
        msgs = q[role]
        q[role] = []
    return jsonify({'ok': True, 'peer_online': peer_online, 'signals': msgs})

@app.route('/call/<int:cid>/recv')
def call_recv(cid):
    """ردّ HTTP متدفّق يبقى مفتوحاً ويدفع صوت الطرف الآخر لحظة وصوله.
    الإطار = 4 بايت (طول big-endian) + حمولة PCM. طول 0 = نبضة إبقاء حيّ.
    """
    role = call_role_for(cid)
    if not role:
        return Response(status=403)
    q = _get_audio_q(cid, role)
    # نُفرّغ أي صوت قديم متبقٍّ من مكالمة سابقة قبل بدء البثّ الجديد
    try:
        while True:
            q.get_nowait()
    except _queue.Empty:
        pass

    def gen():
        yield b''   # يفتح الرد فوراً حتى يعتبره العميل متصلاً
        idle = 0
        while True:
            try:
                chunk = q.get(timeout=0.5)
            except _queue.Empty:
                idle += 1
                if idle > 1200:      # ~10 دقائق بلا صوت: نُغلق البثّ
                    break
                yield b'\x00\x00\x00\x00'   # نبضة إبقاء حيّ (طول 0)
                continue
            idle = 0
            if chunk is None:        # إشارة إنهاء المكالمة
                break
            yield len(chunk).to_bytes(4, 'big') + chunk

    return Response(stream_with_context(gen()),
                    mimetype='application/octet-stream',
                    headers={
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'X-Accel-Buffering': 'no',   # يمنع أي تخزين مؤقّت للبثّ
                        'Connection': 'keep-alive',
                    })

@app.route('/call/<int:cid>/send', methods=['POST'])
def call_send(cid):
    """يستقبل قطعة صوت PCM من هذا الطرف ويضعها في طابور الطرف الآخر فوراً."""
    role = call_role_for(cid)
    if not role:
        return ('', 403)
    peer = _peer_role(role)
    data = request.get_data(cache=False)   # حمولة ثنائية خام
    if data:
        q = _get_audio_q(cid, peer)
        try:
            q.put_nowait(data)
        except _queue.Full:
            # الطابور ممتلئ (الطرف الآخر متأخّر): نُسقط أقدم قطعة لصالح الأحدث
            try:
                q.get_nowait()
            except Exception:
                pass
            try:
                q.put_nowait(data)
            except Exception:
                pass
    return ('', 204)

@app.route('/call/<int:cid>/signal', methods=['POST'])
def call_signal(cid):
    role = call_role_for(cid)
    if not role:
        return jsonify({'ok': False}), 403
    data = request.get_json(silent=True) or {}
    sig_type = data.get('type')
    if not sig_type:
        return jsonify({'ok': False}), 400
    peer = _peer_role(role)
    entry = {'type': sig_type, 'data': data.get('data'), 'from': role}
    with _call_lock:
        q = CALL_SIGNALS.setdefault(cid, {'admin': [], 'user': []})
        if sig_type in ('hangup', 'cancel', 'decline'):
            # إنهاء المكالمة: نفرّغ طوابير الطرفين ونُبقي إشارة الإنهاء فقط
            q[peer] = [entry]
            q[role] = []
            _end_audio(cid)   # نُغلق أي بثّ صوتي متدفّق لدى الطرفين
        else:
            q[peer].append(entry)
    return jsonify({'ok': True})

@app.route('/product/<int:pid>')
def product_page(pid):
    return product_detail_page(pid)

@app.route('/cart/add/<int:pid>')
def add_to_cart(pid):
    product = db.session.get(Product, pid)
    if not product:
        flash('المنتج غير موجود', 'danger')
        return redirect(url_for('home'))
    cart = session.get('cart', {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session['cart'] = cart
    session.modified = True
    flash('تمت الإضافة إلى العربة', 'success')
    return redirect(request.referrer or url_for('home'))

@app.route('/cart/increase/<int:pid>')
def cart_increase(pid):
    cart = session.get('cart', {})
    if str(pid) in cart:
        cart[str(pid)] += 1
        session['cart'] = cart
        session.modified = True
    return redirect(url_for('view_cart'))

@app.route('/cart/decrease/<int:pid>')
def cart_decrease(pid):
    cart = session.get('cart', {})
    if str(pid) in cart:
        cart[str(pid)] -= 1
        if cart[str(pid)] <= 0:
            cart.pop(str(pid), None)
            flash('تمت إزالة المنتج من العربة', 'info')
        session['cart'] = cart
        session.modified = True
    return redirect(url_for('view_cart'))

@app.route('/cart/remove/<int:pid>')
def cart_remove(pid):
    cart = session.get('cart', {})
    if str(pid) in cart:
        cart.pop(str(pid), None)
        session['cart'] = cart
        session.modified = True
        flash('تمت إزالة المنتج من العربة', 'info')
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    return cart_page()

@app.route('/checkout', methods=['GET', 'POST'])
@customer_required
def checkout():
    cust = current_customer()
    if not session.get('cart'):
        flash('العربة فارغة', 'warning')
        return redirect(url_for('home'))
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone = request.form['phone'].strip()
        address = request.form['address'].strip()
        method = request.form['payment_method']
        ref = request.form.get('transaction_ref', '').strip()
        proof_name = None
        if method == 'cash_on_delivery':
            ref = None
        else:
            # فودافون كاش / إنستاباي: لازم صورة تأكيد التحويل
            proof_file = request.files.get('payment_proof')
            proof_name = save_payment_proof(proof_file) if proof_file else None
            if not proof_name:
                flash('يرجى رفع صورة تأكيد التحويل لإتمام الطلب', 'danger')
                return redirect(url_for('checkout'))
        items, total = get_cart_info()
        if total <= 0:
            flash('لا توجد منتجات', 'danger')
            return redirect(url_for('view_cart'))
        # تحديث بيانات الحساب لو طلب ذلك
        if request.form.get('save_info'):
            if not Customer.query.filter(Customer.phone == phone, Customer.id != cust.id).first():
                cust.name = name
                cust.phone = phone
                cust.address = address
        order = Order(customer_id=cust.id, customer_uid=current_uid(), customer_name=name, customer_phone=phone,
                     address=address, payment_method=method, transaction_ref=ref, payment_proof=proof_name, total=total)
        db.session.add(order)
        db.session.flush()
        for it in items:
            db.session.add(OrderItem(order_id=order.id, product_id=it['product'].id, quantity=it['qty']))
        db.session.commit()
        session['last_order_id'] = order.id
        session.pop('cart', None)
        session.modified = True
        flash('تم استلام طلبك بنجاح', 'success')
        return redirect(url_for('order_done'))
    return checkout_page(cust)

@app.route('/order-done')
@customer_required
def order_done():
    last_id = session.get('last_order_id')
    if last_id:
        order = db.session.get(Order, last_id)
        if order and order.customer_id == current_customer().id:
            return success_page(order)
    return redirect(url_for('home'))

@app.route('/my-orders')
@customer_required
def my_orders():
    return my_orders_page(current_customer())

@app.route('/order/<int:oid>')
@customer_required
def order_detail(oid):
    order = db.session.get(Order, oid)
    if not order:
        return "الطلب غير موجود", 404
    if order.customer_id != current_customer().id:
        flash('غير مصرح لك بعرض هذا الطلب', 'danger')
        return redirect(url_for('my_orders'))
    return order_detail_page(order)

@app.route('/request-return/<int:oid>', methods=['POST'])
@customer_required
def request_return(oid):
    order = db.session.get(Order, oid)
    if not order or order.customer_id != current_customer().id:
        flash('الطلب غير موجود', 'danger')
        return redirect(url_for('my_orders'))
    if not order.confirmed:
        flash('لا يمكن طلب الاسترجاع قبل تأكيد الطلب', 'warning')
        return redirect(url_for('order_detail', oid=oid))
    product_id = request.form.get('product_id')
    reason = request.form.get('reason', '').strip()
    if not product_id or not reason:
        flash('يرجى اختيار المنتج وكتابة سبب الإرجاع', 'danger')
        return redirect(url_for('order_detail', oid=oid))
    exists = ReturnRequest.query.filter_by(order_id=oid, product_id=int(product_id)).filter(ReturnRequest.status != 'مرفوض').first()
    if exists:
        flash('يوجد بالفعل طلب استرجاع لهذا المنتج قيد المعالجة', 'warning')
        return redirect(url_for('order_detail', oid=oid))
    ret = ReturnRequest(order_id=oid, product_id=int(product_id), reason=reason, customer_id=order.customer_id)
    db.session.add(ret)
    db.session.commit()
    flash('تم إرسال طلب الاسترجاع وسيتم مراجعته. تنبيه: سيتم خصم رسوم الشحن والاسترجاع من المبلغ المسترد.', 'success')
    return redirect(url_for('order_detail', oid=oid))

@app.route('/review/<int:pid>', methods=['POST'])
@customer_required
def add_review(pid):
    cust = current_customer()
    has_purchased = db.session.query(OrderItem.id).join(Order).filter(
        Order.customer_id == cust.id, OrderItem.product_id == pid).first() is not None
    if not has_purchased:
        flash('يجب شراء المنتج أولاً حتى تتمكن من تقييمه', 'danger')
        return redirect(url_for('product_page', pid=pid))
    if Review.query.filter_by(product_id=pid, customer_id=cust.id).first():
        flash('لقد قمت بتقييم هذا المنتج بالفعل', 'warning')
        return redirect(url_for('product_page', pid=pid))
    body = request.form.get('body', '').strip()
    try:
        rating = int(request.form.get('rating', 5))
    except (ValueError, TypeError):
        rating = 5
    rating = max(1, min(5, rating))
    if body:
        db.session.add(Review(product_id=pid, customer_id=cust.id, author=cust.name, body=body, rating=rating))
        db.session.commit()
        flash('شكراً لتقييمك! تم إضافة رأيك بنجاح.', 'success')
    else:
        flash('يرجى كتابة تعليقك', 'danger')
    return redirect(url_for('product_page', pid=pid))

# ====================== مسارات ا��أدمن ======================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and isinstance(current_user, Admin):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        user = Admin.query.filter_by(username=request.form['username'].strip()).first()
        if user and bcrypt.check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('بيانات خاطئة', 'danger')
    return admin_login_page()

@app.route('/admin/logout')
@admin_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    return admin_dashboard_page()

@app.route('/admin/customers')
@admin_required
def admin_customers():
    return admin_customers_page()

@app.route('/admin/customer/<int:cid>')
@admin_required
def admin_customer(cid):
    cust = db.session.get(Customer, cid)
    if not cust:
        flash('العميل غير موجود', 'danger')
        return redirect(url_for('admin_customers'))
    return admin_customer_page(cust)

@app.route('/admin/customer/<int:cid>/password', methods=['POST'])
@admin_required
def admin_change_customer_password(cid):
    cust = db.session.get(Customer, cid)
    if not cust:
        flash('العميل غير موجود', 'danger')
        return redirect(url_for('admin_customers'))
    new_password = request.form.get('new_password', '')
    if len(new_password) < 6:
        flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل', 'danger')
        return redirect(url_for('admin_customer', cid=cid))
    cust.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    cust.password_plain = new_password
    db.session.commit()
    flash(f'تم تغيير كلمة سر العميل {cust.name} بنجاح', 'success')
    return redirect(url_for('admin_customer', cid=cid))

@app.route('/admin/customer/<int:cid>/reply', methods=['POST'])
@admin_required
def admin_customer_reply(cid):
    cust = db.session.get(Customer, cid)
    if not cust:
        return jsonify({'ok': False}), 404
    msg = build_chat_message(uid=f'u{cust.id}', customer_id=cust.id, customer_name=None,
                             sender='admin', read_by_admin=True, read_by_user=False)
    if msg:
        db.session.add(msg)
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/customer/<int:cid>/poll')
@admin_required
def admin_customer_poll(cid):
    ChatMessage.query.filter_by(customer_id=cid, sender='user', read_by_admin=False).update({'read_by_admin': True})
    db.session.commit()
    msgs = ChatMessage.query.filter_by(customer_id=cid).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({'html': render_messages(msgs, admin_view=True)})

@app.route('/admin/chats')
@admin_required
def admin_chats():
    return admin_chats_page()

@app.route('/admin/guest-chats')
@admin_required
def admin_guest_chats():
    return admin_guest_chats_page()

@app.route('/admin/guest-chat/<uid>')
@admin_required
def admin_guest_chat(uid):
    return admin_guest_chat_page(uid)

@app.route('/admin/guest-chat/<uid>/reply', methods=['POST'])
@admin_required
def admin_guest_reply(uid):
    msg = build_chat_message(uid=uid, customer_id=None, customer_name=None,
                             sender='admin', read_by_admin=True, read_by_user=False)
    if msg:
        db.session.add(msg)
        db.session.commit()
    return jsonify({'ok': True})

@app.route('/admin/guest-chat/<uid>/poll')
@admin_required
def admin_guest_chat_poll(uid):
    ChatMessage.query.filter_by(uid=uid, customer_id=None, sender='user', read_by_admin=False).update({'read_by_admin': True})
    db.session.commit()
    msgs = ChatMessage.query.filter_by(uid=uid, customer_id=None).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({'html': render_messages(msgs, admin_view=True)})

@app.route('/admin/notify/count')
@admin_required
def admin_notify_count():
    customers = ChatMessage.query.filter(ChatMessage.sender == 'user', ChatMessage.read_by_admin == False, ChatMessage.customer_id.isnot(None)).count()
    guests = ChatMessage.query.filter(ChatMessage.sender == 'user', ChatMessage.read_by_admin == False, ChatMessage.customer_id.is_(None)).count()
    return jsonify({'customers': customers, 'guests': guests})

@app.route('/admin/returns')
@admin_required
def admin_returns():
    return admin_returns_page()

@app.route('/admin/return/<int:rid>/update', methods=['POST'])
@admin_required
def admin_return_update(rid):
    ret = db.session.get(ReturnRequest, rid)
    if not ret:
        flash('طلب الاسترجاع غير موجود', 'danger')
        return redirect(url_for('admin_returns'))
    action = request.form.get('action')
    note = request.form.get('admin_note', '').strip()
    if action == 'accept':
        ret.status = 'مقبول'
        ret.admin_note = note or 'تم قبول الاسترجاع. سيتم خصم رسوم الشحن والاسترجاع من المبلغ المسترد.'
        flash('تم قبول طلب الاسترجاع وخُصمت قيمته من الأرباح', 'success')
    elif action == 'reject':
        ret.status = 'مرفوض'
        ret.admin_note = note or 'تم رفض طلب الاسترجاع.'
        flash('تم رفض طلب الاسترجاع', 'warning')
    elif action == 'pending':
        ret.status = 'قيد المراجعة'
        flash('تمت إعا��ة الطلب لقيد المراجعة وأُعيدت قيمته للأرباح', 'info')
    db.session.commit()
    return redirect(request.referrer or url_for('admin_returns'))

@app.route('/admin/product/new', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form['name']
        desc = request.form['description']
        price = float(request.form['price'])
        main_name = 'default.jpg'
        main_file = request.files.get('main_image')
        if main_file and allowed_file(main_file.filename):
            main_name = secure_filename(main_file.filename)
            main_file.save(os.path.join(app.config['UPLOAD_FOLDER'], main_name))
        product = Product(name=name, description=desc, price=price, main_image=main_name)
        db.session.add(product)
        db.session.flush()
        for f in request.files.getlist('extra_images'):
            if f and allowed_file(f.filename):
                fname = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                db.session.add(ProductImage(filename=fname, product_id=product.id))
        db.session.commit()
        flash('تمت إضافة المنتج بنجاح', 'success')
        return redirect(url_for('admin_dashboard'))
    return admin_product_form(edit_mode=False)

@app.route('/admin/product/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(pid):
    product = db.session.get(Product, pid)
    if not product:
        return "المنتج غير موجود", 404
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        main_file = request.files.get('main_image')
        if main_file and allowed_file(main_file.filename):
            fname = secure_filename(main_file.filename)
            main_file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            if product.main_image != 'default.jpg':
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.main_image))
                except: pass
            product.main_image = fname
        for rid in request.form.getlist('remove_images'):
            img = db.session.get(ProductImage, int(rid))
            if img:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
                except: pass
                db.session.delete(img)
        for f in request.files.getlist('extra_images'):
            if f and allowed_file(f.filename):
                fname = secure_filename(f.filename)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                db.session.add(ProductImage(filename=fname, product_id=product.id))
        db.session.commit()
        flash('تم تحديث المنتج بنجاح', 'success')
        return redirect(url_for('admin_dashboard'))
    return admin_product_form(edit_mode=True, product=product)

@app.route('/admin/product/delete/<int:pid>')
@admin_required
def admin_delete_product(pid):
    product = db.session.get(Product, pid)
    if product:
        for img in product.extra_images:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
            except: pass
        if product.main_image != 'default.jpg':
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.main_image))
            except: pass
        db.session.delete(product)
        db.session.commit()
        flash('تم حذف المنتج', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/<int:oid>')
@admin_required
def admin_order(oid):
    order = db.session.get(Order, oid)
    if not order:
        return "الطلب غير موجود", 404
    return admin_order_detail_page(order)

@app.route('/admin/order/confirm/<int:oid>')
@admin_required
def admin_confirm(oid):
    order = db.session.get(Order, oid)
    if order:
        order.confirmed = True
        db.session.commit()
        flash('تم تأكيد الطلب', 'success')
    return redirect(url_for('admin_order', oid=oid))

@app.route('/admin/order/unconfirm/<int:oid>')
@admin_required
def admin_unconfirm(oid):
    order = db.session.get(Order, oid)
    if order:
        order.confirmed = False
        db.session.commit()
        flash('تم إلغاء التأكيد', 'warning')
    return redirect(url_for('admin_order', oid=oid))

# ====================== تشغيل ======================
def ensure_schema():
    """Migration خفيف: يضيف الأعمدة الناقصة للجداول القديمة بدون فقدان البيانات."""
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    required = {
        'customer': {
            'password_plain': 'VARCHAR(128)',
        },
        'review': {
            'rating': 'INTEGER DEFAULT 5',
            'customer_id': 'INTEGER',
        },
        'order': {
            'customer_id': 'INTEGER',
            'customer_uid': 'VARCHAR(40)',
            'transaction_ref': 'VARCHAR(100)',
            'payment_proof': 'VARCHAR(120)',
            'confirmed': 'BOOLEAN DEFAULT 0',
        },
        'return_request': {
            'customer_id': 'INTEGER',
            'customer_uid': 'VARCHAR(40)',
            'status': "VARCHAR(30) DEFAULT 'قيد المراجعة'",
            'admin_note': 'TEXT',
        },
        'chat_message': {
            'customer_id': 'INTEGER',
            'customer_name': 'VARCHAR(80)',
            'read_by_admin': 'BOOLEAN DEFAULT 0',
            'read_by_user': 'BOOLEAN DEFAULT 1',
            'msg_type': "VARCHAR(10) DEFAULT 'text'",
            'media_file': 'VARCHAR(120)',
        },
    }

    for table, columns in required.items():
        if table not in existing_tables:
            continue
        existing_cols = [c['name'] for c in inspector.get_columns(table)]
        for col, ddl in columns.items():
            if col not in existing_cols:
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {col} {ddl}'))
                print(f'Migration: added {table}.{col} column')

with app.app_context():
    ensure_schema()
    db.create_all()
    if not Admin.query.filter_by(username='admin').first():
        hashed = bcrypt.generate_password_hash('123456').decode('utf-8')
        db.session.add(Admin(username='admin', password=hashed))
        db.session.commit()
        print('Default admin: admin / 123456')

if __name__ == '__main__':
    # threaded=True ضروري: بثّ الاستقبال المتدفّق يحجز خيطاً طوال المكالمة، فبدونه
    # يخدم الخادم طلباً واحداً فقط وتبدو المكالمة وكأنها انقطعت. وهذا بثّ HTTP عادي
    # يعمل بثبات على خادم Flask التطويري دون أي مكتبة WebSocket ولا سيرفر خاص.
    # use_reloader=False يمنع إعادة تحميل الكود من قطع البثّ المفتوح.
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
