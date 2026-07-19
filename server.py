from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import requests
from datetime import datetime, timedelta
import uuid

# Роли и права
ROLES = {
    "кадет": {
        "name": "Кадет",
        "can_fine": True,
        "can_warn": True,
        "can_wanted": False,
        "can_clear": False,
        "can_audit": False
    },
    "офицер": {
        "name": "Офицер",
        "can_fine": True,
        "can_warn": True,
        "can_wanted": True,
        "can_clear": False,
        "can_audit": False
    },
    "сержант": {
        "name": "Сержант",
        "can_fine": True,
        "can_warn": True,
        "can_wanted": True,
        "can_clear": True,
        "can_audit": True
    },
    "лейтенант": {
        "name": "Лейтенант",
        "can_fine": True,
        "can_warn": True,
        "can_wanted": True,
        "can_clear": True,
        "can_audit": True
    }
}




app = Flask(__name__, static_folder='site', static_url_path='')
CORS(app)

DB_FILE = 'database.json'
CONFIG_FILE = 'config.json'

with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
    config = json.load(f)

# Инициализация базы
if os.path.exists(DB_FILE):
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        db = json.load(f)
else:
    db = {
        "players": [],
        "fines": [],
        "wanted": [],
        "warnings": [],
        "vehicles": [],
        "audit_log": [],
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
        "audit_counter": 0
    }
    save_db_flag = True

def save_db():
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def add_audit(action_type, description, moderator="LSPD#5816"):
    db['audit_counter'] += 1
    db['audit_log'].append({
        "id": db['audit_counter'],
        "action_type": action_type,
        "description": description,
        "moderator": moderator,
        "timestamp": datetime.now().isoformat()
    })
    # Храним только последние 500 записей
    if len(db['audit_log']) > 500:
        db['audit_log'] = db['audit_log'][-500:]
    save_db()

def send_webhook(webhook_url, embed):
    payload = {"embeds": [embed]}
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 200:
            try:
                return response.json().get('id')
            except:
                return None
        return None
    except Exception as e:
        print(f"Webhook exception: {e}")
        return None

def send_webhook_message(webhook_url, content):
    payload = {"content": content}
    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except:
        pass

def delete_webhook_message(webhook_url, message_id):
    if not message_id:
        return False
    url = f"{webhook_url}/messages/{message_id}"
    try:
        response = requests.delete(url, timeout=10)
        return response.status_code == 204
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
            "created_at": datetime.now().isoformat()
        }
        db['players'].append(player)
        save_db()
    return player

def get_avatar_url(nickname):
    """Получает аватарку игрока через Roblox API (асинхронно)"""
    try:
        # Сначала получаем user ID
        resp = requests.post("https://users.roblox.com/v1/usernames/users", 
                            json={"usernames": [nickname]}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data['data']:
                user_id = data['data'][0]['id']
                # Получаем аватарку
                avatar_resp = requests.get(
                    f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png",
                    timeout=5
                )
                if avatar_resp.status_code == 200:
                    avatar_data = avatar_resp.json()
                    if avatar_data['data']:
                        return avatar_data['data'][0]['imageUrl']
    except:
        pass
    return ""

# ============================================================
#                           M A R S H R U T Y
# ============================================================

@app.route('/')
def index():
    return send_from_directory('site', 'index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    if data.get('password') == config['password']:
        return jsonify({"success": True, "moderators": config.get('moderators', {})})
    return jsonify({"success": False}), 403

# ---- СТАТИСТИКА ----

@app.route('/api/stats', methods=['GET'])
def get_stats():
    expired_fines = 0
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    for f in db['fines']:
        if f.get('created_at', '') < cutoff and not f.get('expired'):
            f['expired'] = True
    save_db()
    
    active_wanted = [w for w in db['wanted'] if not w.get('expired', False)]
    return jsonify({
        "total_fines": len([f for f in db['fines'] if not f.get('expired', False)]),
        "total_wanted": len(active_wanted),
        "total_players": len(db['players']),
        "total_warnings": len(db['warnings']),
        "total_vehicles": len(db['vehicles'])
    })

# ---- БАЗА ИГРОКОВ ----

@app.route('/api/players', methods=['GET'])
def get_players():
    search = request.args.get('search', '').lower()
    if search:
        filtered = [p for p in db['players'] if 
                   search in p['nickname'].lower() or 
                   search in p.get('rp_name', '').lower() or
                   search in p.get('notes', '').lower()]
        return jsonify(filtered)
    return jsonify(db['players'])

@app.route('/api/players/<nickname>', methods=['GET'])
def get_player(nickname):
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player:
        return jsonify(None)
    
    player_fines = [f for f in db['fines'] if f['nickname'].lower() == nickname.lower()]
    player_wanted = [w for w in db['wanted'] if w['nickname'].lower() == nickname.lower() and not w.get('expired', False)]
    player_warnings = [w for w in db['warnings'] if w['nickname'].lower() == nickname.lower()]
    player_vehicles = [v for v in db['vehicles'] if v.get('owner_nickname', '').lower() == nickname.lower()]
    
    # Автоматически подгружаем аватарку, если её нет
    if not player.get('photo_url') or player.get('photo_url') == '':
        avatar = get_avatar_url(nickname)
        if avatar:
            player['photo_url'] = avatar
            save_db()
    
    return jsonify({
        "player": player,
        "fines": player_fines,
        "wanted": player_wanted,
        "warnings": player_warnings,
        "vehicles": player_vehicles
    })

@app.route('/api/players/<nickname>', methods=['PUT'])
def update_player(nickname):
    data = request.json
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player:
        player = {
            "nickname": nickname,
            "rp_name": data.get('rp_name', ''),
            "rp_age": data.get('rp_age', ''),
            "notes": data.get('notes', ''),
            "photo_url": data.get('photo_url', ''),
            "created_at": datetime.now().isoformat()
        }
        db['players'].append(player)
    else:
        player['rp_name'] = data.get('rp_name', player.get('rp_name', ''))
        player['rp_age'] = data.get('rp_age', player.get('rp_age', ''))
        player['notes'] = data.get('notes', player.get('notes', ''))
        if data.get('photo_url'):
            player['photo_url'] = data['photo_url']
    save_db()
    add_audit("player_update", f"Обновлены данные игрока {nickname}")
    return jsonify({"success": True, "player": player})

@app.route('/api/players/<nickname>/clear', methods=['POST'])
def clear_player_data(nickname):
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if not player:
        return jsonify({"success": False, "error": "Игрок не найден"}), 404
    
    player_fines = [f for f in db['fines'] if f['nickname'].lower() == nickname.lower()]
    for fine in player_fines:
        if fine.get('discord_message_id'):
            delete_webhook_message(config['fine_webhook_url'], fine['discord_message_id'])
    
    player_wanted = [w for w in db['wanted'] if w['nickname'].lower() == nickname.lower()]
    for w in player_wanted:
        if w.get('discord_message_id'):
            delete_webhook_message(config['wanted_webhook_url'], w['discord_message_id'])
    
    player_warnings = [w for w in db['warnings'] if w['nickname'].lower() == nickname.lower()]
    
    db['fines'] = [f for f in db['fines'] if f['nickname'].lower() != nickname.lower()]
    db['wanted'] = [w for w in db['wanted'] if w['nickname'].lower() != nickname.lower()]
    db['warnings'] = [w for w in db['warnings'] if w['nickname'].lower() != nickname.lower()]
    
    send_webhook_message(config['log_webhook_url'],
        f"🧹 **Очистка данных**\n👤 Все данные игрока **{nickname}** очищены.\n"
        f"📋 Штрафов: {len(player_fines)} | Розысков: {len(player_wanted)} | Предупреждений: {len(player_warnings)}")
    
    add_audit("clear_data", f"Очищены все данные игрока {nickname}")
    save_db()
    return jsonify({
        "success": True,
        "fines_removed": len(player_fines),
        "wanted_removed": len(player_wanted),
        "warnings_removed": len(player_warnings)
    })

# ---- ШТРАФЫ ----

@app.route('/api/fines', methods=['GET'])
def get_fines():
    search = request.args.get('search', '').lower()
    show_expired = request.args.get('show_expired', 'true') == 'true'
    
    fines = db['fines']
    if not show_expired:
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        fines = [f for f in fines if f.get('created_at', '') >= cutoff]
    
    if search:
        fines = [f for f in fines if search in f['nickname'].lower() or search in f.get('reason', '').lower()]
    
    return jsonify(fines)

@app.route('/api/fines', methods=['POST'])
def add_fine():
    data = request.json
    nickname = data.get('nickname')
    reason = data.get('reason')
    article = data.get('article', '')
    time = data.get('time', datetime.now().strftime('%H:%M'))
    issued_by = data.get('issued_by', 'LSPD#5816')

    if not nickname or not reason:
        return jsonify({"success": False, "error": "Ник и причина обязательны"}), 400

    get_or_create_player(nickname)
    db['fine_counter'] += 1
    fine_id = db['fine_counter']
    
    # Если указана статья, добавляем в причину
    full_reason = reason
    if article:
        article_obj = next((a for a in db['articles'] if a['id'] == article), None)
        if article_obj:
            full_reason = f"[{article}] {reason} (Штраф: ${article_obj['fine']})"

    embed = {
        "title": f"📋 Штраф #{fine_id}",
        "color": 16766720,
        "fields": [
            {"name": "👤 Нарушитель", "value": nickname, "inline": True},
            {"name": "🕐 Время", "value": time, "inline": True},
            {"name": "👮 Выдал", "value": issued_by, "inline": True},
            {"name": "📋 Причина", "value": full_reason, "inline": False}
        ],
        "footer": {"text": f"LSPD | {datetime.now().strftime('%d.%m.%Y')}"}
    }

    message_id = send_webhook(config['fine_webhook_url'], embed)

    fine_record = {
        "id": fine_id,
        "nickname": nickname,
        "reason": full_reason,
        "article": article,
        "time": time,
        "issued_by": issued_by,
        "discord_message_id": message_id,
        "expired": False,
        "created_at": datetime.now().isoformat()
    }
    db['fines'].append(fine_record)
    add_audit("fine_add", f"Штраф #{fine_id} выписан {nickname}: {full_reason}", issued_by)
    save_db()

    return jsonify({"success": True, "fine": fine_record})

@app.route('/api/fines/<int:fine_id>', methods=['DELETE'])
def delete_fine(fine_id):
    fine = next((f for f in db['fines'] if f['id'] == fine_id), None)
    if not fine:
        return jsonify({"success": False, "error": "Штраф не найден"}), 404

    if fine.get('discord_message_id'):
        delete_webhook_message(config['fine_webhook_url'], fine['discord_message_id'])

    send_webhook_message(config['log_webhook_url'],
        f"✅ **Штраф #{fine['id']} снят**\n👤 С игрока **{fine['nickname']}** снят штраф.\n📋 Причина была: {fine['reason']}")
    
    add_audit("fine_remove", f"Штраф #{fine_id} снят с {fine['nickname']}")
    db['fines'] = [f for f in db['fines'] if f['id'] != fine_id]
    save_db()
    return jsonify({"success": True})

# ---- ПРЕДУПРЕЖДЕНИЯ ----

@app.route('/api/warnings', methods=['GET'])
def get_warnings():
    search = request.args.get('search', '').lower()
    if search:
        return jsonify([w for w in db['warnings'] if search in w['nickname'].lower()])
    return jsonify(db['warnings'])

@app.route('/api/warnings', methods=['POST'])
def add_warning():
    data = request.json
    nickname = data.get('nickname')
    reason = data.get('reason')
    warning_type = data.get('type', 'verbal')
    issued_by = data.get('issued_by', 'LSPD#5816')

    if not nickname or not reason:
        return jsonify({"success": False, "error": "Ник и причина обязательны"}), 400

    get_or_create_player(nickname)
    db['warning_counter'] += 1
    warning_id = db['warning_counter']

    warning_record = {
        "id": warning_id,
        "nickname": nickname,
        "reason": reason,
        "type": warning_type,
        "issued_by": issued_by,
        "created_at": datetime.now().isoformat()
    }
    db['warnings'].append(warning_record)
    
    # Проверяем, не пора ли в розыск
    player_warnings = [w for w in db['warnings'] if w['nickname'].lower() == nickname.lower()]
    if len(player_warnings) >= 3:
        # Автоматический розыск
        db['wanted_counter'] += 1
        wanted_id = db['wanted_counter']
        wanted_record = {
            "id": wanted_id,
            "nickname": nickname,
            "reason": "Автоматический розыск: 3 предупреждения",
            "stars": 1,
            "discord_message_id": None,
            "expired": False,
            "created_at": datetime.now().isoformat()
        }
        db['wanted'].append(wanted_record)
        add_audit("auto_wanted", f"Авто-розыск {nickname} из-за 3 предупреждений")
    
    add_audit("warning_add", f"Предупреждение #{warning_id} вынесено {nickname}: {reason}")
    save_db()
    return jsonify({"success": True, "warning": warning_record, "auto_wanted": len(player_warnings) >= 3})

@app.route('/api/warnings/<int:warning_id>', methods=['DELETE'])
def delete_warning(warning_id):
    warning = next((w for w in db['warnings'] if w['id'] == warning_id), None)
    if not warning:
        return jsonify({"success": False, "error": "Предупреждение не найдено"}), 404
    db['warnings'] = [w for w in db['warnings'] if w['id'] != warning_id]
    add_audit("warning_remove", f"Предупреждение #{warning_id} снято с {warning['nickname']}")
    save_db()
    return jsonify({"success": True})

# ---- РОЗЫСК ----

@app.route('/api/wanted', methods=['GET'])
def get_wanted():
    show_expired = request.args.get('show_expired', 'false') == 'true'
    if show_expired:
        return jsonify(db['wanted'])
    return jsonify([w for w in db['wanted'] if not w.get('expired', False)])

@app.route('/api/wanted', methods=['POST'])
def add_wanted():
    data = request.json
    nickname = data.get('nickname')
    reason = data.get('reason')
    stars = data.get('stars', 1)
    issued_by = data.get('issued_by', 'LSPD#5816')

    if not nickname or not reason:
        return jsonify({"success": False, "error": "Ник и причина обязательны"}), 400

    stars = max(0, min(5, int(stars)))
    get_or_create_player(nickname)
    
    db['wanted_counter'] += 1
    wanted_id = db['wanted_counter']

    colors = [0x808080, 0x00E676, 0xFFEA00, 0xFF9100, 0xFF1744, 0xD50000]
    danger_emoji = ["⚪", "🟢", "🟡", "🟠", "🔴", "💀"]
    danger_levels = ["Не опасен", "Низкая", "Средняя", "Высокая", "Очень высокая", "КРИТИЧЕСКАЯ"]

    embed = {
        "title": f"{danger_emoji[stars]} РОЗЫСК #{wanted_id}",
        "description": "",
        "color": colors[stars],
        "fields": [
            {"name": "👤 Разыскивается", "value": nickname, "inline": True},
            {"name": "⚠️ Уровень", "value": f"{'⭐'*stars}{'☆'*(5-stars)} — {danger_levels[stars]}", "inline": True},
            {"name": "📋 Причина", "value": reason, "inline": False},
            {"name": "👮 Объявил", "value": issued_by, "inline": True},
            {"name": "📅 Дата", "value": datetime.now().strftime('%d.%m.%Y %H:%M'), "inline": True}
        ],
        "image": {"url": ""},
        "footer": {"text": "LSPD | При задержании — дежурная часть"}
    }

    if stars >= 4:
        embed["description"] = "🚨 **@everyone СРОЧНО! Особо опасный преступник!**"

    # Добавляем фото, если есть
    player = next((p for p in db['players'] if p['nickname'].lower() == nickname.lower()), None)
    if player and player.get('photo_url'):
        embed["image"]["url"] = player['photo_url']

    message_id = send_webhook(config['wanted_webhook_url'], embed)

    wanted_record = {
        "id": wanted_id,
        "nickname": nickname,
        "reason": reason,
        "stars": stars,
        "issued_by": issued_by,
        "discord_message_id": message_id,
        "expired": False,
        "created_at": datetime.now().isoformat()
    }
    db['wanted'].append(wanted_record)
    add_audit("wanted_add", f"Розыск #{wanted_id} объявлен на {nickname}: {stars}★ — {reason}", issued_by)
    save_db()

    return jsonify({"success": True, "wanted": wanted_record})

@app.route('/api/wanted/<int:wanted_id>', methods=['DELETE'])
def delete_wanted(wanted_id):
    wanted = next((w for w in db['wanted'] if w['id'] == wanted_id), None)
    if not wanted:
        return jsonify({"success": False, "error": "Розыск не найден"}), 404

    if wanted.get('discord_message_id'):
        delete_webhook_message(config['wanted_webhook_url'], wanted['discord_message_id'])

    send_webhook_message(config['log_webhook_url'],
        f"🔓 **Розыск #{wanted['id']} снят**\n👤 С игрока **{wanted['nickname']}** снят розыск.\n⭐ Был уровень: {wanted['stars']}/5")
    
    add_audit("wanted_remove", f"Розыск #{wanted_id} снят с {wanted['nickname']}")
    db['wanted'] = [w for w in db['wanted'] if w['id'] != wanted_id]
    save_db()
    return jsonify({"success": True})

# ---- ТРАНСПОРТ ----

@app.route('/api/vehicles', methods=['GET'])
def get_vehicles():
    search = request.args.get('search', '').lower()
    if search:
        return jsonify([v for v in db['vehicles'] if 
                       search in v.get('plate', '').lower() or 
                       search in v.get('model', '').lower() or
                       search in v.get('owner_nickname', '').lower()])
    return jsonify(db['vehicles'])

@app.route('/api/vehicles', methods=['POST'])
def add_vehicle():
    data = request.json
    plate = data.get('plate', '').upper()
    model = data.get('model', '')
    owner_nickname = data.get('owner_nickname', '')
    color = data.get('color', '')

    if not plate:
        return jsonify({"success": False, "error": "Госномер обязателен"}), 400

    vehicle = {
        "plate": plate,
        "model": model,
        "owner_nickname": owner_nickname,
        "color": color,
        "created_at": datetime.now().isoformat()
    }
    
    # Обновляем или добавляем
    existing = next((v for v in db['vehicles'] if v['plate'] == plate), None)
    if existing:
        existing.update(vehicle)
    else:
        db['vehicles'].append(vehicle)
    
    if owner_nickname:
        get_or_create_player(owner_nickname)
    
    add_audit("vehicle_add", f"ТС {plate} ({model}) привязано к {owner_nickname or 'неизвестному'}")
    save_db()
    return jsonify({"success": True, "vehicle": vehicle})

@app.route('/api/vehicles/<plate>', methods=['DELETE'])
def delete_vehicle(plate):
    vehicle = next((v for v in db['vehicles'] if v['plate'].upper() == plate.upper()), None)
    if not vehicle:
        return jsonify({"success": False, "error": "ТС не найдено"}), 404
    db['vehicles'] = [v for v in db['vehicles'] if v['plate'].upper() != plate.upper()]
    add_audit("vehicle_remove", f"ТС {plate} удалено из базы")
    save_db()
    return jsonify({"success": True})

# ---- АУДИТ ----

@app.route('/api/audit', methods=['GET'])
def get_audit():
    limit = request.args.get('limit', 100, type=int)
    action_type = request.args.get('type', '')
    
    logs = db['audit_log']
    if action_type:
        logs = [l for l in logs if l['action_type'] == action_type]
    
    # Сортировка: новые сверху
    logs = sorted(logs, key=lambda x: x['timestamp'], reverse=True)[:limit]
    return jsonify(logs)

# ---- СТАТЬИ ----

@app.route('/api/articles', methods=['GET'])
def get_articles():
    return jsonify(db['articles'])

# ---- ЭКСПОРТ ----

@app.route('/api/export/<data_type>', methods=['GET'])
def export_data(data_type):
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if data_type == 'fines':
        writer.writerow(['ID', 'Ник', 'Причина', 'Статья', 'Время', 'Выдал', 'Дата'])
        for f in db['fines']:
            writer.writerow([f['id'], f['nickname'], f['reason'], f.get('article', ''), 
                           f['time'], f['issued_by'], f.get('created_at', '')])
    elif data_type == 'wanted':
        writer.writerow(['ID', 'Ник', 'Причина', 'Звёзды', 'Объявил', 'Дата'])
        for w in db['wanted']:
            writer.writerow([w['id'], w['nickname'], w['reason'], w['stars'], 
                           w.get('issued_by', ''), w.get('created_at', '')])
    elif data_type == 'players':
        writer.writerow(['Ник', 'RP-имя', 'RP-возраст', 'Заметки', 'Дата регистрации'])
        for p in db['players']:
            writer.writerow([p['nickname'], p.get('rp_name', ''), p.get('rp_age', ''),
                           p.get('notes', ''), p.get('created_at', '')])
    elif data_type == 'vehicles':
        writer.writerow(['Госномер', 'Модель', 'Владелец', 'Цвет'])
        for v in db['vehicles']:
            writer.writerow([v['plate'], v['model'], v.get('owner_nickname', ''), v.get('color', '')])
    else:
        return jsonify({"error": "Неизвестный тип"}), 400
    
    return output.getvalue(), 200, {'Content-Type': 'text/csv; charset=utf-8'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config['server_port'], debug=True)