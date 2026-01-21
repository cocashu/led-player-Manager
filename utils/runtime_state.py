current = {
    "schedule_id": None,
    "media_id": None,
    "media_name": None,
    "media_type": None,
    "path": None,
    "text_size": None,
    "text_color": None,
    "bg_color": None,
    "text_scroll_mode": None,
    "elapsed": 0,
    "total": 0,
    "scheduler_playing": False,
    "scheduler_paused": False,
    "scheduler_window_blocked": False,
}

snapshot = None

def set_play_start(schedule_id, media_id, media_name, media_type, path, total, text_size=None, text_color=None, bg_color=None, text_scroll_mode=None):
    current["schedule_id"] = schedule_id
    current["media_id"] = media_id
    current["media_name"] = media_name
    current["media_type"] = media_type
    current["path"] = path
    current["text_size"] = text_size
    current["text_color"] = text_color
    current["bg_color"] = bg_color
    current["text_scroll_mode"] = text_scroll_mode
    current["elapsed"] = 0
    current["total"] = int(total or 0)

def set_time(elapsed, total=None):
    current["elapsed"] = int(elapsed or 0)
    if total is not None:
        current["total"] = int(total or 0)

def set_scheduler_state(is_playing, paused, window_blocked):
    current["scheduler_playing"] = bool(is_playing)
    current["scheduler_paused"] = bool(paused)
    current["scheduler_window_blocked"] = bool(window_blocked)

def set_snapshot(data):
    global snapshot
    snapshot = data

def get_snapshot():
    return snapshot

def clear():
    current["schedule_id"] = None
    current["media_id"] = None
    current["media_name"] = None
    current["media_type"] = None
    current["path"] = None
    current["text_size"] = None
    current["text_color"] = None
    current["bg_color"] = None
    current["text_scroll_mode"] = None
    current["elapsed"] = 0
    current["total"] = 0
