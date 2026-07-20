from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import requests
from datetime import datetime, timedelta
from collections import Counter, defaultdict

app = Flask(__name__, static_folder='site', static_url_path='')
CORS(app)

DB_FILE = 'database.json'
CONFIG_FILE = 'config.json'

# ============================================================
# ⭐ ТОКЕН ВАШЕГО БОТА (экономического) ⭐
# ============================================================
BOT_TOKEN = "MTUyODcyNzg5MTg0NjYzMTQ4Ng.GWurRL.kWSJ2NsEHLcQF64fQHNKJ-dBb3w2r0x0MP-kp4"

# Загрузка конфига
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
except:
    config = {
        "moderators": {}, 
        "fine_webhook_url": "", 
        "wanted_webhook_url": "", 
        "log_webhook_url": "", 
        "panic_webhook_url": "",
        "bot_channel_id": "1528738908655976599"  # Канал для команд бота
    }

# Права ролей
ROLES = {
    "кадет": {"name": "Кадет", "can_fine": True, "can_warn": True, "can_wanted": False, "can_clear": False, "can_audit": False},
    "офицер": {"name": "Офицер", "can_fine": True, "can_warn": True, "can_wanted": True, "can_clear": False, "can_audit": False},
    "сержант": {"name": "Сержант", "can_fine": True, "can_warn": True, "can_wanted": True, "can_clear": True, "can_audit": True},
    "лейтенант": {"name": "Лейтенант", "can_fine": True, "can_warn": True, "can_wanted": True, "can_clear": True, "can_audit": True}
}

# Загрузка БД
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except:
        db = {}
else:
    db = {}

# Структура БД
default_db = {
    "players": [], 
    "fines": [], 
    "wanted": [], 
    "warnings": [], 
    "vehicles": [], 
    "audit_log": [],
    "warrants": [], 
    "shifts": [], 
    "officer_achievements": [], 
    "panic_log": [], 
    "detentions": [],
    "articles": [
        {"id": "12.1", "title": "Проезд на красный свет", "fine": 500},
        {"id": "12.2", "title": "Превышение скорости", "fine": 300},
        {"id": "12.3", "title": "Езда по встречной полосе", "fine": 700},
        {"id": "12.4", "title": "Парковка в неположенном месте", "fine": 200},
        {"id": "12.5", "title": "Управление без прав", "fine": 1000},
        {"id": "12.6", "title": "Опасное вождение", "fine": 800},
        {"id": "12.7", "title": "Оскорбление офицера", "fine": 400},
        {"id": "12.8", "title": "Сопротивление при задержании", "fine": 1500},
        {"id": "12.9", "title": "Нарушение общественного порядка", "fine": 350}
    ],
    "fine_counter": 0, 
    "wanted_counter": 0, 
    "warning_counter": 0, 
    "audit_counter": 0,
    "warrant_counter": 0, 
    "shift_counter": 0, 
    "panic_counter": 0
}
for key, value in default_db.items():
    if key not in db:
        db[key] = value

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def save_db():
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except: 
        pass

def add_audit(action_type, description, moderator="Неизвестно"):
    db['audit_counter'] += 1
    db['audit_log'].append({
        "id": db['audit_counter'], 
        "action_type": action_type, 
        "description": description, 
        "moderator": moderator, 
        "timestamp": datetime.now().isoformat()
    })
    if len(db['audit_log']) > 500: 
        db['audit_log'] = db['audit_log'][-500:]
    save_db()

# ============================================================
# ⭐ ФУНКЦИЯ ОТПРАВКИ КОМАНДЫ БОТУ ⭐
# ============================================================

def send_bot_command(command):
    """
    Отправляет команду боту через Discord API в канал 1528738908655976599
    """
    channel_id = config.get('bot_channel_id', '1528738908655976599')
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "content": command
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200 or response.status_code == 201:
            print(f"✅ Команда отправлена боту: {command}")
            return True, None
        else:
            error_msg = f"Ошибка {response.status_code}: {response.text}"
            print(f"❌ {error_msg}")
            return False, error_msg
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Ошибка отправки команды: {error_msg}")
        return False, error_msg

# ============================================================
# ВЕБХУКИ ДЛЯ ЛОГОВ И УВЕДОМЛЕНИЙ
# ============================================================

def send_webhook(webhook_url, embed):
    if not webhook_url: 
        return None
    try:
        resp = requests.post(webhook_url, json={"embeds": [embed]}, timeout=10)
        if resp.status_code == 200:
            try: 
                return resp.json().get('id')
            except: 
                return None
    except: 
        pass
    return None

def send_webhook_message(webhook_url, content):
    if not webhook_url: 
        return
    try: 
        requests.post(webhook_url, json={"content": content}, timeout=10)
    except: 
        pass

def delete_webhook_message(webhook_url, message_id):
    if not webhook_url or not message_id: 
        return False
    try:
        resp = requests.delete(f"{webhook_url}/messages/{message_id}", timeout=10)
        return resp.status_code == 204
    except: 
        return False

def get_or_create_player(nickname):
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player:
        player = {
            "nickname": nickname, 
            "rp_name": "", 
            "rp_age": "", 
            "notes": "", 
            "photo_url": "", 
            "player_rank": "гражданский", 
            "created_at": datetime.now().isoformat()
        }
        db['players'].append(player)
        save_db()
    return player

def get_avatar_url(nickname):
    try:
        resp = requests.post("https://users.roblox.com/v1/usernames/users", 
                           json={"usernames": [nickname]}, timeout=5)
        if resp.status_code == 200 and resp.json().get('data'):
            uid = resp.json()['data'][0]['id']
            av = requests.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={uid}&size=150x150&format=Png", timeout=5)
            if av.status_code == 200 and av.json().get('data'):
                return av.json()['data'][0]['imageUrl']
    except: 
        pass
    return ""

def update_officer_achievements(badge):
    if not badge: 
        return
    officer = next((o for o in db['officer_achievements'] if o['badge'] == badge), None)
    if not officer:
        officer = {"badge": badge, "fines": 0, "wanted": 0, "clears": 0, "achievements": []}
        db['officer_achievements'].append(officer)
    officer['fines'] = len([f for f in db['fines'] if f.get('issued_by') == badge])
    officer['wanted'] = len([w for w in db['wanted'] if w.get('issued_by') == badge])
    officer['clears'] = len([a for a in db['audit_log'] if a['action_type'] == 'clear_data' and a['moderator'] == badge])
    save_db()

# ============================================================
# ОСНОВНЫЕ МАРШРУТЫ
# ============================================================

@app.route('/')
def index():
    return send_from_directory('site', 'index.html')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('site', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('site', 'sw.js')

# ============================================================
# АВТОРИЗАЦИЯ
# ============================================================

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    moder = config.get('moderators', {}).get(username)
    if moder and moder.get('password') == password:
        rank = moder.get('rank', 'кадет')
        role = ROLES.get(rank, ROLES['кадет'])
        return jsonify({
            "success": True, 
            "moderator": {
                "username": username, 
                "rank": rank, 
                "rank_name": role['name'],
                "rp_name": moder.get('rp_name', ''), 
                "badge": moder.get('badge', ''),
                "permissions": {
                    k: role[k] for k in ["can_fine","can_warn","can_wanted","can_clear","can_audit"]
                }
            }
        })
    return jsonify({"success": False, "error": "Неверный логин или пароль"}), 403

# ============================================================
# СТАТИСТИКА
# ============================================================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify({
        "total_fines": len(db['fines']), 
        "total_wanted": len([w for w in db['wanted'] if not w.get('expired')]),
        "total_players": len(db['players']), 
        "total_warnings": len(db['warnings']),
        "total_vehicles": len(db['vehicles']), 
        "total_warrants": len([w for w in db['warrants'] if w.get('active')]),
        "officers_on_duty": len([s for s in db['shifts'] if not s.get('end')])
    })

# ============================================================
# ИГРОКИ
# ============================================================

@app.route('/api/players', methods=['GET'])
def get_players():
    search = request.args.get('search', '').lower()
    if search: 
        return jsonify([p for p in db['players'] if search in p['nickname'].lower() or search in p.get('rp_name','').lower() or search in p.get('notes','').lower()])
    return jsonify(db['players'])

@app.route('/api/players/<nickname>', methods=['GET'])
def get_player(nickname):
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player: 
        return jsonify(None)
    if not player.get('photo_url'):
        avatar = get_avatar_url(nickname)
        if avatar: 
            player['photo_url'] = avatar
            save_db()
    return jsonify({
        "player": player,
        "fines": [f for f in db['fines'] if f['nickname'].lower() == nickname.lower()],
        "wanted": [w for w in db['wanted'] if w['nickname'].lower() == nickname.lower() and not w.get('expired')],
        "warnings": [w for w in db['warnings'] if w['nickname'].lower() == nickname.lower()],
        "vehicles": [v for v in db['vehicles'] if v.get('owner_nickname','').lower() == nickname.lower()],
        "warrants": [w for w in db['warrants'] if w['nickname'].lower() == nickname.lower() and w.get('active')]
    })

@app.route('/api/players/<nickname>', methods=['PUT'])
def update_player(nickname):
    data = request.json
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player:
        player = {
            "nickname": nickname, 
            "rp_name": "", 
            "rp_age": "", 
            "notes": "", 
            "photo_url": "", 
            "player_rank": "гражданский", 
            "created_at": datetime.now().isoformat()
        }
        db['players'].append(player)
    for k in ['rp_name','rp_age','notes','photo_url','player_rank']:
        if k in data: 
            player[k] = data[k]
    add_audit("player_update", f"Обновлены данные {nickname}")
    save_db()
    return jsonify({"success": True, "player": player})

@app.route('/api/players/<nickname>/clear', methods=['POST'])
def clear_player_data(nickname):
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player: 
        return jsonify({"success": False, "error": "Игрок не найден"}), 404
    pf = [f for f in db['fines'] if f['nickname'].lower() == nickname.lower()]
    pw = [w for w in db['wanted'] if w['nickname'].lower() == nickname.lower()]
    for f in pf:
        if f.get('discord_message_id'): 
            delete_webhook_message(config.get('fine_webhook_url',''), f['discord_message_id'])
    for w in pw:
        if w.get('discord_message_id'): 
            delete_webhook_message(config.get('wanted_webhook_url',''), w['discord_message_id'])
    db['fines'] = [f for f in db['fines'] if f['nickname'].lower() != nickname.lower()]
    db['wanted'] = [w for w in db['wanted'] if w['nickname'].lower() != nickname.lower()]
    db['warnings'] = [w for w in db['warnings'] if w['nickname'].lower() != nickname.lower()]
    send_webhook_message(config.get('log_webhook_url',''), f"🧹 Очистка: {nickname}\nШтрафов: {len(pf)} | Розысков: {len(pw)}")
    add_audit("clear_data", f"Очищены все данные {nickname}")
    save_db()
    return jsonify({"success": True, "fines_removed": len(pf), "wanted_removed": len(pw)})

# ============================================================
# ⭐ ШТРАФЫ (ГЛАВНАЯ ФУНКЦИЯ) ⭐
# ============================================================

@app.route('/api/fines', methods=['GET'])
def get_fines():
    search = request.args.get('search', '').lower()
    fines = db['fines']
    if search: 
        fines = [f for f in fines if search in f['nickname'].lower() or search in f.get('reason','').lower()]
    return jsonify(fines)

@app.route('/api/fines', methods=['POST'])
def add_fine():
    data = request.json
    nickname = data.get('nickname', '').strip()
    reason = data.get('reason', '').strip()
    
    if not nickname or not reason: 
        return jsonify({"success": False, "error": "Ник и причина обязательны"}), 400
    
    get_or_create_player(nickname)
    db['fine_counter'] += 1
    fid = db['fine_counter']
    
    article = data.get('article', '')
    full_reason = reason
    fine_amount = 500
    
    if article:
        a = next((x for x in db['articles'] if x['id'] == article), None)
        if a:
            full_reason = f"[{article}] {reason} (${a['fine']})"
            fine_amount = a['fine']
    
    issued_by = data.get('issued_by', 'CCPD#0000')
    
    # === ОТПРАВКА ШТРАФА В ОСНОВНОЙ КАНАЛ (через вебхук) ===
    embed = {
        "title": f"📋 Штраф #{fid}", 
        "color": 9807270, 
        "fields": [
            {"name": "👤 Нарушитель", "value": nickname, "inline": True},
            {"name": "🕐 Время", "value": data.get('time', datetime.now().strftime('%H:%M')), "inline": True},
            {"name": "👮 Выдал", "value": issued_by, "inline": True},
            {"name": "📋 Причина", "value": full_reason, "inline": False},
            {"name": "💰 Сумма", "value": f"{fine_amount}$", "inline": True}
        ], 
        "footer": {"text": f"CCSV3 POLICE | {datetime.now().strftime('%d.%m.%Y')}"}
    }
    msg_id = send_webhook(config.get('fine_webhook_url',''), embed)
    
    # Сохраняем штраф
    fine = {
        "id": fid, 
        "nickname": nickname, 
        "reason": full_reason, 
        "article": article, 
        "time": data.get('time', datetime.now().strftime('%H:%M')), 
        "issued_by": issued_by, 
        "discord_message_id": msg_id, 
        "expired": False, 
        "created_at": datetime.now().isoformat(),
        "amount": fine_amount
    }
    db['fines'].append(fine)
    add_audit("fine_add", f"Штраф #{fid} → {nickname}", issued_by)
    update_officer_achievements(issued_by)
    save_db()
    
    # ============================================================
    # ⭐ ОТПРАВКА КОМАНДЫ БОТУ (РОБЛОКС НИК → ПОИСК В КАНАЛЕ) ⭐
    # ============================================================
    command = f"/remove {nickname} {fine_amount} Штраф #{fid}: {reason}"
    success, error = send_bot_command(command)
    
    if success:
        send_webhook_message(config.get('log_webhook_url',''), 
            f"🤖 Команда боту отправлена: `{command}`")
    else:
        send_webhook_message(config.get('log_webhook_url',''), 
            f"❌ Ошибка отправки команды боту: {error}\nКоманда: `{command}`")
    
    return jsonify({
        "success": True, 
        "fine": db['fines'][-1],
        "bot_command_sent": success,
        "bot_command": command
    })

@app.route('/api/fines/<int:fid>', methods=['DELETE'])
def delete_fine(fid):
    fine = next((f for f in db['fines'] if f['id'] == fid), None)
    if not fine: 
        return jsonify({"success": False, "error": "Не найден"}), 404
    if fine.get('discord_message_id'): 
        delete_webhook_message(config.get('fine_webhook_url',''), fine['discord_message_id'])
    send_webhook_message(config.get('log_webhook_url',''), f"✅ Штраф #{fid} снят с {fine['nickname']}")
    add_audit("fine_remove", f"Штраф #{fid} снят с {fine['nickname']}")
    db['fines'] = [f for f in db['fines'] if f['id'] != fid]
    save_db()
    return jsonify({"success": True})

# ============================================================
# РОЗЫСК
# ============================================================

@app.route('/api/wanted', methods=['GET'])
def get_wanted():
    return jsonify([w for w in db['wanted'] if not w.get('expired')])

@app.route('/api/wanted', methods=['POST'])
def add_wanted():
    data = request.json
    nickname, reason = data.get('nickname'), data.get('reason')
    if not nickname or not reason: 
        return jsonify({"success": False, "error": "Ник и причина обязательны"}), 400
    
    stars = max(0, min(5, int(data.get('stars', 1))))
    get_or_create_player(nickname)
    db['wanted_counter'] += 1
    wid = db['wanted_counter']
    issued_by = data.get('issued_by', 'CCPD#0000')
    
    colors = [0x808080, 0x00E676, 0xFFEA00, 0xFF9100, 0xFF1744, 0xD50000]
    emoji = ["⚪","🟢","🟡","🟠","🔴","💀"]
    levels = ["Не опасен","Низкая","Средняя","Высокая","Очень высокая","КРИТИЧЕСКАЯ"]
    
    embed = {
        "title": f"{emoji[stars]} РОЗЫСК #{wid}", 
        "color": colors[stars], 
        "fields": [
            {"name": "👤 Разыскивается", "value": nickname, "inline": True},
            {"name": "⚠️ Уровень", "value": f"{'⭐'*stars}{'☆'*(5-stars)} — {levels[stars]}", "inline": True},
            {"name": "📋 Причина", "value": reason, "inline": False},
            {"name": "👮 Объявил", "value": issued_by, "inline": True}
        ], 
        "footer": {"text": "CCSV3 POLICE"}
    }
    if stars >= 4: 
        embed["description"] = "🚨 @everyone СРОЧНО!"
    
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if player and player.get('photo_url'): 
        embed["image"] = {"url": player['photo_url']}
    
    msg_id = send_webhook(config.get('wanted_webhook_url',''), embed)
    
    wanted = {
        "id": wid, 
        "nickname": nickname, 
        "reason": reason, 
        "stars": stars, 
        "issued_by": issued_by, 
        "discord_message_id": msg_id, 
        "expired": False, 
        "created_at": datetime.now().isoformat()
    }
    db['wanted'].append(wanted)
    add_audit("wanted_add", f"Розыск #{wid} → {nickname}: {stars}★", issued_by)
    update_officer_achievements(issued_by)
    save_db()
    return jsonify({"success": True, "wanted": db['wanted'][-1]})

@app.route('/api/wanted/<int:wid>', methods=['DELETE'])
def delete_wanted(wid):
    wanted = next((w for w in db['wanted'] if w['id'] == wid), None)
    if not wanted: 
        return jsonify({"success": False, "error": "Не найден"}), 404
    if wanted.get('discord_message_id'): 
        delete_webhook_message(config.get('wanted_webhook_url',''), wanted['discord_message_id'])
    send_webhook_message(config.get('log_webhook_url',''), f"🔓 Розыск #{wid} снят с {wanted['nickname']}")
    add_audit("wanted_remove", f"Розыск #{wid} снят")
    db['wanted'] = [w for w in db['wanted'] if w['id'] != wid]
    save_db()
    return jsonify({"success": True})

# ============================================================
# ПРЕДУПРЕЖДЕНИЯ
# ============================================================

@app.route('/api/warnings', methods=['GET'])
def get_warnings():
    return jsonify(db['warnings'])

@app.route('/api/warnings', methods=['POST'])
def add_warning():
    data = request.json
    nickname, reason = data.get('nickname'), data.get('reason')
    if not nickname or not reason: 
        return jsonify({"success": False, "error": "Ник и причина обязательны"}), 400
    get_or_create_player(nickname)
    db['warning_counter'] += 1
    wid = db['warning_counter']
    issued_by = data.get('issued_by', 'CCPD#0000')
    db['warnings'].append({
        "id": wid, 
        "nickname": nickname, 
        "reason": reason, 
        "type": data.get('type','verbal'), 
        "issued_by": issued_by, 
        "created_at": datetime.now().isoformat()
    })
    
    auto_wanted = False
    if len([w for w in db['warnings'] if w['nickname'].lower() == nickname.lower()]) >= 3:
        db['wanted_counter'] += 1
        db['wanted'].append({
            "id": db['wanted_counter'], 
            "nickname": nickname, 
            "reason": "Авто-розыск: 3 предупреждения", 
            "stars": 1, 
            "issued_by": "SYSTEM", 
            "discord_message_id": None, 
            "expired": False, 
            "created_at": datetime.now().isoformat()
        })
        add_audit("auto_wanted", f"Авто-розыск {nickname}")
        auto_wanted = True
    
    add_audit("warning_add", f"Предупреждение #{wid} → {nickname}", issued_by)
    save_db()
    return jsonify({"success": True, "warning": db['warnings'][-1], "auto_wanted": auto_wanted})

@app.route('/api/warnings/<int:wid>', methods=['DELETE'])
def delete_warning(wid):
    db['warnings'] = [w for w in db['warnings'] if w['id'] != wid]
    save_db()
    return jsonify({"success": True})

# ============================================================
# ОРДЕРА
# ============================================================

@app.route('/api/warrants', methods=['GET'])
def get_warrants():
    return jsonify([w for w in db['warrants'] if w.get('active')])

@app.route('/api/warrants', methods=['POST'])
def add_warrant():
    data = request.json
    db['warrant_counter'] += 1
    warrant = {
        "id": db['warrant_counter'], 
        "nickname": data.get('nickname'), 
        "type": data.get('type','search'), 
        "reason": data.get('reason',''), 
        "issued_by": data.get('issued_by','CCPD#0000'), 
        "expires": (datetime.now() + timedelta(hours=24)).isoformat(), 
        "active": True, 
        "created_at": datetime.now().isoformat()
    }
    db['warrants'].append(warrant)
    add_audit("warrant_add", f"Ордер #{warrant['id']} → {warrant['nickname']}")
    save_db()
    return jsonify({"success": True, "warrant": warrant})

@app.route('/api/warrants/<int:wid>', methods=['DELETE'])
def revoke_warrant(wid):
    w = next((x for x in db['warrants'] if x['id'] == wid), None)
    if w: 
        w['active'] = False
        add_audit("warrant_revoke", f"Ордер #{wid} отозван")
        save_db()
    return jsonify({"success": True})

# ============================================================
# ТРАНСПОРТ
# ============================================================

@app.route('/api/vehicles', methods=['GET'])
def get_vehicles():
    search = request.args.get('search', '').lower()
    if search: 
        return jsonify([v for v in db['vehicles'] if search in v.get('plate','').lower() or search in v.get('model','').lower() or search in v.get('owner_nickname','').lower()])
    return jsonify(db['vehicles'])

@app.route('/api/vehicles', methods=['POST'])
def add_vehicle():
    data = request.json
    plate = data.get('plate', '').upper()
    if not plate: 
        return jsonify({"success": False, "error": "Госномер обязателен"}), 400
    vehicle = {
        "plate": plate, 
        "model": data.get('model',''), 
        "owner_nickname": data.get('owner_nickname',''), 
        "color": data.get('color',''), 
        "created_at": datetime.now().isoformat()
    }
    existing = next((v for v in db['vehicles'] if v['plate'] == plate), None)
    if existing: 
        existing.update(vehicle)
    else: 
        db['vehicles'].append(vehicle)
    if vehicle['owner_nickname']: 
        get_or_create_player(vehicle['owner_nickname'])
    add_audit("vehicle_add", f"ТС {plate} → {vehicle['owner_nickname'] or '—'}")
    save_db()
    return jsonify({"success": True, "vehicle": vehicle})

@app.route('/api/vehicles/<plate>', methods=['DELETE'])
def delete_vehicle(plate):
    db['vehicles'] = [v for v in db['vehicles'] if v['plate'].upper() != plate.upper()]
    save_db()
    return jsonify({"success": True})

@app.route('/api/vehicle/check/<plate>', methods=['GET'])
def check_vehicle(plate):
    v = next((x for x in db['vehicles'] if x['plate'].upper() == plate.upper()), None)
    if not v: 
        return jsonify(None)
    owner = next((p for p in db['players'] if p['nickname'].lower() == v.get('owner_nickname','').lower()), None)
    fines = [f for f in db['fines'] if f.get('nickname','').lower() == v.get('owner_nickname','').lower()]
    wanted = [w for w in db['wanted'] if w.get('nickname','').lower() == v.get('owner_nickname','').lower() and not w.get('expired')]
    return jsonify({"vehicle": v, "owner": owner, "fines": fines, "wanted": wanted})

# ============================================================
# СМЕНЫ
# ============================================================

@app.route('/api/shifts', methods=['GET'])
def get_shifts():
    return jsonify(db['shifts'])

@app.route('/api/shifts/start', methods=['POST'])
def start_shift():
    data = request.json
    db['shift_counter'] += 1
    shift = {
        "id": db['shift_counter'], 
        "officer": data.get('officer',''), 
        "code": data.get('code', 4), 
        "start": datetime.now().isoformat(), 
        "end": None
    }
    db['shifts'].append(shift)
    add_audit("shift_start", f"Смена #{shift['id']} начата: {shift['officer']} (Code {shift['code']})")
    save_db()
    return jsonify({"success": True, "shift": shift})

@app.route('/api/shifts/<int:sid>/end', methods=['POST'])
def end_shift(sid):
    s = next((x for x in db['shifts'] if x['id'] == sid), None)
    if s: 
        s['end'] = datetime.now().isoformat()
        add_audit("shift_end", f"Смена #{sid} завершена")
        save_db()
    return jsonify({"success": True})

@app.route('/api/shifts/<int:sid>/code', methods=['PUT'])
def update_shift_code(sid):
    s = next((x for x in db['shifts'] if x['id'] == sid), None)
    if s: 
        s['code'] = request.json.get('code', 4)
        add_audit("shift_code", f"Смена #{sid}: Code {s['code']}")
        save_db()
    return jsonify({"success": True})

@app.route('/api/shifts/active', methods=['GET'])
def active_shifts():
    return jsonify([s for s in db['shifts'] if not s.get('end')])

# ============================================================
# ТРЕВОГА
# ============================================================

@app.route('/api/panic', methods=['POST'])
def panic():
    data = request.json
    db['panic_counter'] += 1
    officer = data.get('officer', 'Неизвестно')
    location = data.get('location', 'Не указано')
    embed = {
        "title": "🚨 ТРЕВОГА!", 
        "description": "**Офицер запросил подкрепление!**", 
        "color": 0xFF0000, 
        "fields": [
            {"name": "👮 Офицер", "value": officer, "inline": True},
            {"name": "📍 Локация", "value": location, "inline": True},
            {"name": "🕐 Время", "value": datetime.now().strftime('%H:%M:%S'), "inline": True}
        ], 
        "footer": {"text": "CCSV3 POLICE — Тревожная кнопка"}
    }
    send_webhook(config.get('panic_webhook_url', config.get('log_webhook_url','')), embed)
    db['panic_log'].append({
        "id": db['panic_counter'], 
        "officer": officer, 
        "location": location, 
        "timestamp": datetime.now().isoformat()
    })
    add_audit("panic", f"Тревога #{db['panic_counter']}: {officer}")
    save_db()
    return jsonify({"success": True, "panic_id": db['panic_counter']})

# ============================================================
# ЗАДЕРЖАНИЯ
# ============================================================

@app.route('/api/detentions', methods=['GET'])
def get_detentions():
    return jsonify(db['detentions'])

@app.route('/api/detentions', methods=['POST'])
def add_detention():
    data = request.json
    detention = {
        "id": len(db['detentions'])+1, 
        "nickname": data.get('nickname'), 
        "officer": data.get('officer'), 
        "reason": data.get('reason'), 
        "start": datetime.now().isoformat(), 
        "released": False
    }
    db['detentions'].append(detention)
    add_audit("detention", f"Задержан {data.get('nickname')}: {data.get('reason')}")
    save_db()
    return jsonify({"success": True, "detention": detention})

@app.route('/api/detentions/<int:did>/release', methods=['POST'])
def release_detention(did):
    d = next((x for x in db['detentions'] if x['id'] == did), None)
    if d: 
        d['released'] = True
        d['end'] = datetime.now().isoformat()
        add_audit("release", f"Освобождён {d['nickname']}")
        save_db()
    return jsonify({"success": True})

# ============================================================
# ДОСТИЖЕНИЯ
# ============================================================

@app.route('/api/achievements/<badge>', methods=['GET'])
def get_achievements(badge):
    update_officer_achievements(badge)
    officer = next((o for o in db['officer_achievements'] if o['badge'] == badge), {
        "badge": badge, 
        "fines": 0, 
        "wanted": 0, 
        "clears": 0
    })
    return jsonify(officer)

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    for moder in config.get('moderators', {}).values(): 
        update_officer_achievements(moder.get('badge', ''))
    return jsonify(sorted(db['officer_achievements'], 
                         key=lambda x: x['fines'] + x['wanted']*2 + x['clears'], 
                         reverse=True)[:5])

# ============================================================
# АУДИТ
# ============================================================

@app.route('/api/audit', methods=['GET'])
def get_audit():
    limit = request.args.get('limit', 100, type=int)
    atype = request.args.get('type', '')
    logs = [l for l in db['audit_log'] if not atype or l['action_type'] == atype]
    return jsonify(sorted(logs, key=lambda x: x['timestamp'], reverse=True)[:limit])

# ============================================================
# СТАТЬИ
# ============================================================

@app.route('/api/articles', methods=['GET'])
def get_articles():
    return jsonify(db['articles'])

# ============================================================
# ⭐ РУЧНАЯ ОТПРАВКА КОМАНДЫ БОТУ ⭐
# ============================================================

@app.route('/api/bot/command', methods=['POST'])
def send_bot_command_api():
    """
    Ручная отправка команды боту
    POST /api/bot/command
    {"command": "/remove JohnDoe 500 Штраф"}
    """
    data = request.json
    command = data.get('command', '')
    
    if not command:
        return jsonify({"success": False, "error": "Команда не указана"}), 400
    
    success, error = send_bot_command(command)
    
    if success:
        return jsonify({"success": True, "message": f"Команда отправлена: {command}"})
    else:
        return jsonify({"success": False, "error": f"Не удалось отправить команду: {error}"}), 500

# ============================================================
# АНАЛИТИКА
# ============================================================

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    fc = Counter(f['nickname'] for f in db['fines'])
    oc = Counter(f.get('issued_by','Неизвестно') for f in db['fines'])
    df = defaultdict(int)
    for f in db['fines']:
        if f.get('created_at',''): 
            df[f['created_at'][:10]] += 1
    
    return jsonify({
        "top_offenders": [{"nickname": n, "count": c} for n,c in fc.most_common(10)],
        "top_officers": [{"name": n, "count": c} for n,c in oc.most_common(10)],
        "daily_fines": [{"date": d, "count": c} for d,c in sorted(df.items())[-30:]],
        "summary": {
            "total_fines": len(db['fines']), 
            "total_wanted": len(db['wanted']), 
            "total_players": len(db['players'])
        }
    })

# ============================================================
# ЭКСПОРТ
# ============================================================

@app.route('/api/export/<dtype>', methods=['GET'])
def export_data(dtype):
    import csv, io
    output = io.StringIO()
    w = csv.writer(output)
    
    if dtype == 'fines':
        w.writerow(['ID','Ник','Причина','Статья','Время','Выдал','Дата','Сумма'])
        for f in db['fines']: 
            w.writerow([f['id'],f['nickname'],f['reason'],f.get('article',''),f['time'],f['issued_by'],f.get('created_at',''),f.get('amount',0)])
    
    elif dtype == 'wanted':
        w.writerow(['ID','Ник','Причина','Звёзды','Объявил','Дата'])
        for x in db['wanted']: 
            w.writerow([x['id'],x['nickname'],x['reason'],x['stars'],x.get('issued_by',''),x.get('created_at','')])
    
    elif dtype == 'players':
        w.writerow(['Ник','RP-имя','RP-возраст','Заметки','Ранг','Дата'])
        for p in db['players']: 
            w.writerow([p['nickname'],p.get('rp_name',''),p.get('rp_age',''),p.get('notes',''),p.get('player_rank',''),p.get('created_at','')])
    
    elif dtype == 'vehicles':
        w.writerow(['Госномер','Модель','Владелец','Цвет'])
        for v in db['vehicles']: 
            w.writerow([v['plate'],v['model'],v.get('owner_nickname',''),v.get('color','')])
    
    else: 
        return jsonify({"error": "Неизвестный тип"}), 400
    
    return output.getvalue(), 200, {'Content-Type': 'text/csv; charset=utf-8'}

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
