import json
import sys
import os
from pathlib import Path

# Path resolution logic
if getattr(sys, "frozen", False):
    if hasattr(sys, "_MEIPASS"):
        # OneFile mode
        APP_ROOT = Path(sys._MEIPASS)
        DATA_ROOT = Path(sys.executable).resolve().parent
    else:
        # OneDir mode
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "_internal").exists():
            APP_ROOT = exe_dir / "_internal"
        else:
            APP_ROOT = exe_dir
        DATA_ROOT = exe_dir
else:
    # Development mode (utils/config.py -> utils -> root)
    APP_ROOT = Path(__file__).resolve().parent.parent
    DATA_ROOT = APP_ROOT

WEB_DIR = APP_ROOT / "web"
MEDIA_DIR = DATA_ROOT / "resources/media"

class ConfigManager:
    def __init__(self, config_path="resources/config.json"):
        self.config_path = DATA_ROOT / config_path
        self.config = self.load_config()

    def load_config(self):
        if not self.config_path.exists():
            return self.create_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.create_default_config()

    def create_default_config(self):
        default_config = {
            "server": {
                "port": 8080,
                "host": "0.0.0.0"
            },
            "player": {
                "default_duration": 10,
                "loop": True,
                "target_screen_index": 1  # Default to second screen (0-based index)
            },
            "database": {
                "path": "data/led.db"
            }
        }
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4)
            
        return default_config
    
    def save(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except KeyError:
            return default
            
    def set(self, key, value):
        keys = key.split('.')
        target = self.config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        self.save()

config = ConfigManager()
