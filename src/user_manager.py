# src/user_manager.py
import json
import logging
from .config import ALLOWED_USERS_FILE, OWNER_ID

logger = logging.getLogger(__name__)

# --- Кэш в памяти ---
_user_cache = None          # {"users": set, "admins": set, "blacklist": set, "whitelist_enabled": bool}
_cache_valid = False

def _invalidate_cache():
    global _cache_valid
    _cache_valid = False

def _get_cache():
    global _cache_valid, _user_cache
    if not _cache_valid:
        data = load_all_data()
        _user_cache = {
            "users": set(data.get("users", [])),
            "admins": set(data.get("admins", [])),
            "blacklist": set(data.get("blacklist", [])),
            "whitelist_enabled": data.get("whitelist_enabled", True)
        }
        _cache_valid = True
    return _user_cache

# --- Загрузка/сохранение данных (без изменений) ---
def load_all_data():
    """Загружает все данные, создавая структуру по умолчанию при отсутствии."""
    default_data = {
        "whitelist_enabled": True,
        "users": [],
        "admins": [],
        "blacklist": []
    }
    if ALLOWED_USERS_FILE.exists():
        try:
            with open(ALLOWED_USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "whitelist_enabled" not in data:
                    data["whitelist_enabled"] = True
                if "users" not in data:
                    data["users"] = []
                if "admins" not in data:
                    data["admins"] = []
                if "blacklist" not in data:
                    data["blacklist"] = []
                return data
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
    return default_data

def save_all_data(data: dict):
    try:
        with open(ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# --- Управление вайтлистом (глобальный режим) ---
def is_whitelist_enabled() -> bool:
    return _get_cache()["whitelist_enabled"]

def set_whitelist_enabled(enabled: bool):
    data = load_all_data()
    data["whitelist_enabled"] = enabled
    save_all_data(data)
    _invalidate_cache()
    logger.info(f"Whitelist mode set to {enabled}")

# --- Чёрный список ---
def is_blacklisted(user_id: int) -> bool:
    return user_id in _get_cache()["blacklist"]

def add_blacklist(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    data = load_all_data()
    if user_id not in data["blacklist"]:
        data["blacklist"].append(user_id)
        save_all_data(data)
        _invalidate_cache()
        return True
    return False

def remove_blacklist(user_id: int) -> bool:
    data = load_all_data()
    if user_id in data["blacklist"]:
        data["blacklist"].remove(user_id)
        save_all_data(data)
        _invalidate_cache()
        return True
    return False

def get_blacklist() -> list:
    return list(_get_cache()["blacklist"])

# --- Разрешённые пользователи (обычные) ---
def load_allowed_users() -> set:
    return _get_cache()["users"]

def load_admins() -> set:
    return _get_cache()["admins"]

def is_user_allowed(user_id: int) -> bool:
    """Проверяет, может ли пользователь пользоваться ботом с учётом whitelist/blacklist."""
    if is_blacklisted(user_id):
        return False
    if not is_whitelist_enabled():
        return True
    if user_id == OWNER_ID:
        return True
    cache = _get_cache()
    return user_id in cache["users"] or user_id in cache["admins"]

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором (или владельцем)."""
    if user_id == OWNER_ID:
        return True
    return user_id in _get_cache()["admins"]

def add_allowed_user(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    data = load_all_data()
    if user_id in data["users"] or user_id in data["admins"]:
        return False
    data["users"].append(user_id)
    save_all_data(data)
    _invalidate_cache()
    return True

def remove_allowed_user(user_id: int) -> bool:
    data = load_all_data()
    if user_id in data["users"]:
        data["users"].remove(user_id)
        save_all_data(data)
        _invalidate_cache()
        return True
    return False

def add_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    data = load_all_data()
    if user_id not in data["users"] and user_id not in data["admins"]:
        return False
    if user_id in data["admins"]:
        return False
    data["admins"].append(user_id)
    if user_id in data["users"]:
        data["users"].remove(user_id)
    save_all_data(data)
    _invalidate_cache()
    return True

def remove_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    data = load_all_data()
    if user_id not in data["admins"]:
        return False
    data["admins"].remove(user_id)
    if user_id not in data["users"]:
        data["users"].append(user_id)
    save_all_data(data)
    _invalidate_cache()
    return True

def list_allowed_users():
    data = load_all_data()
    return data["users"], data["admins"]