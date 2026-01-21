from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from database.db_manager import db
from datetime import datetime
from utils.command_bus import command_bus
from utils.runtime_state import set_scheduler_state

class Scheduler(QObject):
    play_media = pyqtSignal(dict)
    prefetch_media = pyqtSignal(dict)
    stop_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_loop)
        self.timer.start(1000) # Check every 1 second for commands and status
        
        self.current_schedule_id = None
        self.last_played_id = None
        self.is_playing = False
        self.force_play_mode = False
        self.play_start_time = None
        self.current_media_id = None
        self.paused = False
        self._window_blocked = False
        self.next_payload = None
        self._prefetched_for = None
        set_scheduler_state(self.is_playing, self.paused, self._window_blocked)

    def _get_play_window_config(self):
        row = db.fetch_one("""
            SELECT schedule_window_enabled, schedule_window_start, schedule_window_end
            FROM screen_config
            WHERE id = 1
        """)
        if not row:
            return {"enabled": False, "start": None, "end": None}
        return {
            "enabled": bool(row.get("schedule_window_enabled") or 0),
            "start": row.get("schedule_window_start"),
            "end": row.get("schedule_window_end"),
        }

    def _is_within_play_window(self, now_local: datetime) -> bool:
        cfg = self._get_play_window_config()
        if not cfg["enabled"]:
            return True
        start = cfg["start"]
        end = cfg["end"]
        if not start or not end:
            return True

        now_minutes = now_local.hour * 60 + now_local.minute
        start_h, start_m = start.split(":")
        end_h, end_m = end.split(":")
        start_minutes = int(start_h) * 60 + int(start_m)
        end_minutes = int(end_h) * 60 + int(end_m)

        if start_minutes == end_minutes:
            return True
        if start_minutes < end_minutes:
            return start_minutes <= now_minutes < end_minutes
        return now_minutes >= start_minutes or now_minutes < end_minutes

    def check_loop(self):
        cmd = command_bus.get()
        if cmd:
            c = cmd.get('command')
            if c == 'FORCE_PLAY':
                self.handle_force_play(cmd.get('data'))
                return
            if c == 'STOP_ALL':
                self.paused = True
                if self.is_playing:
                    self.stop_requested.emit()
                set_scheduler_state(self.is_playing, self.paused, self._window_blocked)
                return
            if c == 'START_ALL':
                self.paused = False
                self.check_schedule()
                set_scheduler_state(self.is_playing, self.paused, self._window_blocked)
                return
            if c in ("OUTPUT_SET", "OUTPUT_TEST_COLOR"):
                command_bus.send(c, cmd.get('data'))

        within_window = self._is_within_play_window(datetime.now())
        if not within_window:
            if self.is_playing:
                self.stop_requested.emit()
                self.is_playing = False
                self.current_schedule_id = None
                self.current_media_id = None
                self.play_start_time = None
            self._window_blocked = True
            set_scheduler_state(self.is_playing, self.paused, self._window_blocked)
            return
        self._window_blocked = False
        set_scheduler_state(self.is_playing, self.paused, self._window_blocked)

        if self.paused or self.is_playing:
            return
        self.check_schedule()

    def handle_force_play(self, schedule_id):
        print(f"Force playing schedule: {schedule_id}")
        sql = """
            SELECT s.*, m.path, m.duration as default_duration, m.type as media_type
            FROM schedules s
            JOIN media m ON s.media_id = m.id
            WHERE s.id = ?
        """
        schedule = db.fetch_one(sql, (schedule_id,))
        
        if schedule:
            self.force_play_mode = True
            self.play_item(schedule)
        else:
            print(f"Schedule {schedule_id} not found")

    def check_schedule(self):
        now_local = datetime.now().isoformat(timespec="seconds")
        now_utc = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        
        # Fetch ALL valid schedules active now
        sql = """
            SELECT s.*, m.path, m.duration as default_duration, m.type as media_type
            FROM schedules s
            JOIN media m ON s.media_id = m.id
            WHERE COALESCE(s.is_enabled, 1) = 1
              AND (
                (s.start_time <= ? AND s.end_time >= ?)
                OR
                (s.start_time <= ? AND s.end_time >= ?)
              )
            ORDER BY s.priority DESC, COALESCE(s.order_index, 0) ASC, s.start_time ASC
        """
        schedules = db.fetch_all(sql, (now_local, now_local, now_utc, now_utc))
        
        if not schedules:
            self.current_schedule_id = None
            self.is_playing = False
            set_scheduler_state(self.is_playing, self.paused, self._window_blocked)
            return

        # Group by highest priority
        max_priority = schedules[0]['priority']
        valid_schedules = [s for s in schedules if s['priority'] == max_priority]
        
        if not valid_schedules:
            return

        # Loop Logic
        next_schedule = None
        follow_schedule = None
        
        if self.last_played_id:
            # Find current index
            try:
                # Find the index of the last played item in the CURRENT valid list
                # This handles cases where items are added/removed
                current_index = -1
                for i, s in enumerate(valid_schedules):
                    if s['id'] == self.last_played_id:
                        current_index = i
                        break
                
                # Pick next one (circular)
                next_index = (current_index + 1) % len(valid_schedules)
                next_schedule = valid_schedules[next_index]
                follow_index = (next_index + 1) % len(valid_schedules)
                follow_schedule = valid_schedules[follow_index]
            except ValueError:
                # Last played item no longer valid, start from 0
                next_schedule = valid_schedules[0]
                follow_index = 1 if len(valid_schedules) > 1 else 0
                follow_schedule = valid_schedules[follow_index]
        else:
            # First run
            next_schedule = valid_schedules[0]
            follow_index = 1 if len(valid_schedules) > 1 else 0
            follow_schedule = valid_schedules[follow_index]

        if next_schedule:
            if follow_schedule:
                pd = follow_schedule.get('play_duration')
                media_type = follow_schedule.get('media_type')
                default_dur = follow_schedule.get('default_duration')
                if media_type == 'video':
                    if pd is None:
                        duration = default_dur if default_dur is not None else 0
                    elif pd == 0:
                        duration = 0
                    else:
                        duration = pd
                else:
                    if pd is None or pd == 0:
                        duration = default_dur if (default_dur is not None and default_dur > 0) else 10
                    else:
                        duration = pd
                self.next_payload = {
                    "path": follow_schedule['path'],
                    "duration": duration,
                    "type": follow_schedule.get('media_type'),
                    "text_size": follow_schedule.get('text_size'),
                    "text_color": follow_schedule.get('text_color'),
                    "bg_color": follow_schedule.get('bg_color'),
                    "text_scroll_mode": follow_schedule.get('text_scroll_mode'),
                    "schedule_id": follow_schedule['id'],
                    "media_id": follow_schedule.get('media_id')
                }
            self.play_item(next_schedule)

    def play_item(self, schedule):
        self.current_schedule_id = schedule['id']
        pd = schedule.get('play_duration')
        media_type = schedule.get('media_type')
        default_dur = schedule.get('default_duration')
        if media_type == 'video':
            if pd is None:
                duration = default_dur if default_dur is not None else 0
            elif pd == 0:
                duration = 0
            else:
                duration = pd
        else:
            if pd is None or pd == 0:
                duration = default_dur if (default_dur is not None and default_dur > 0) else 10
            else:
                duration = pd
        self.play_start_time = datetime.now()
        self.current_media_id = schedule.get('media_id')
        payload = {
            "path": schedule['path'],
            "duration": duration,
            "type": schedule.get('media_type'),
            "text_size": schedule.get('text_size'),
            "text_color": schedule.get('text_color'),
            "bg_color": schedule.get('bg_color'),
            "text_scroll_mode": schedule.get('text_scroll_mode'),
            "schedule_id": schedule['id'],
            "media_id": self.current_media_id
        }
        self.play_media.emit(payload)
        self.is_playing = True
        set_scheduler_state(self.is_playing, self.paused, self._window_blocked)

        # Prefetch next item immediately for seamless transition
        if self.next_payload:
            try:
                self.prefetch_media.emit(self.next_payload)
                self._prefetched_for = self.current_schedule_id
            except Exception:
                pass

    def on_media_finished(self):
        """Called when media playback finishes"""
        # Write play log
        try:
            if self.play_start_time and self.current_media_id:
                end_time = datetime.now()
                duration_sec = int((end_time - self.play_start_time).total_seconds())
                db.execute("""
                    INSERT INTO play_logs (media_id, schedule_id, start_time, end_time, duration_seconds)
                    VALUES (?, ?, ?, ?, ?)
                """, (self.current_media_id, self.current_schedule_id, self.play_start_time.isoformat(), end_time.isoformat(), duration_sec))
        except Exception as e:
            print(f"Failed to write play log: {e}")
        finally:
            self.play_start_time = None
            self.current_media_id = None
        self.is_playing = False
        set_scheduler_state(self.is_playing, self.paused, self._window_blocked)
        
        # If we were in force play mode, finish it and return to normal scheduling
        # Or should we loop the forced item? Usually "Play" means "Play once" or "Start playing this".
        # If we want to support "Start playing this list starting from this item", that's different.
        # Assuming "Force Play" is a one-off override.
        if self.force_play_mode:
            self.force_play_mode = False
            # Don't set last_played_id for forced items to avoid messing up the loop?
            # Or do we? If we force play an item that is IN the schedule, maybe we should set it.
            # Let's check if the forced item is in the current valid list.
            # For simplicity, let's just update last_played_id so the loop continues from there if possible.
            self.last_played_id = self.current_schedule_id
        else:
            self.last_played_id = self.current_schedule_id
            
        # Immediately check for next item
        self._prefetched_for = None
        self.check_loop()

    def on_time_tick(self, elapsed, total):
        if total is None or total <= 0:
            return
        remaining = max(0, total - elapsed)
        if remaining > 1:
            return
        if not self.next_payload:
            return
        if self._prefetched_for == self.current_schedule_id:
            return
        try:
            self.prefetch_media.emit(self.next_payload)
            self._prefetched_for = self.current_schedule_id
        except Exception:
            pass
