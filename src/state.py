import json
from pathlib import Path

STATE_FILE = Path("data/state.json")


def load_state():
    """قراءة حالة البوت المحفوظة."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state):
    """حفظ حالة البوت."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
