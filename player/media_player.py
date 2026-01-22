import sys
import vlc
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl
from pathlib import Path
from PyQt6.QtGui import QFont, QColor
from utils.config import config

class MediaPlayer(QWidget):
    # Signals
    media_finished = pyqtSignal()
    time_updated = pyqtSignal(int, int)  # elapsed, total
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instance = vlc.Instance(
            "--ignore-config",
            "--no-snapshot-preview",
            "--no-osd",
            "--avcodec-hw=none", 
            "--vout=direct3d9",
            "--no-video-title-show",
            "--quiet"
        )
        # Local preview player
        self.preview_player = self.instance.media_player_new()
        
        self.output_window = None
        self.output_windows = []
        
        # State tracking
        self.current_output_url = None
        self.current_duration = 0
        self.elapsed_seconds = 0
        self.text_mode = False
        self._disposed = False
        
        self.init_ui()
        
        # Timer for time updates
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start(200) # 200ms update rate

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Video frame for VLC (Local Preview)
        self.video_frame = QFrame()
        self.video_frame.setFrameShape(QFrame.Shape.Box)
        self.video_frame.setFrameShadow(QFrame.Shadow.Raised)
        self.video_frame.setStyleSheet("background-color: black;")
        
        layout.addWidget(self.video_frame)
        self.setLayout(layout)
        
        self.preview_text = QLabel(self.video_frame)
        self.preview_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_text.setWordWrap(True)
        self.preview_text.setGeometry(self.video_frame.rect())
        self.preview_text.hide()
        
        # Bind preview player to frame
        if sys.platform.startswith('linux'):
            self.preview_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.preview_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.preview_player.set_nsobject(self.video_frame.winId())

    def set_output_window(self, window):
        if self.output_window:
            try:
                self.output_window.media_finished.disconnect(self._on_output_media_finished)
            except:
                pass
                
        self.output_window = window
        self.output_windows = [window] if window else []
        
        if self.output_window:
            self.output_window.media_finished.connect(self._on_output_media_finished)
            
            # Connect resize for aspect ratio?
            if hasattr(self.output_window, "resized"):
                self.output_window.resized.connect(self._apply_aspect)

    def set_output_windows(self, windows):
        self.set_output_window(windows[0] if windows else None)
        self.output_windows = [w for w in (windows or []) if w]

    def set_extended_active(self, active: bool):
        pass # Not used with QML output for now

    def set_extended_scale_mode(self, mode: str):
        pass

    def _apply_aspect(self):
        pass

    def _on_output_media_finished(self, url, type):
        # Called when QML finishes a transition to a new media
        # This implies the PREVIOUS media is done and the NEW one is active.
        # But for Scheduler, 'media_finished' means "The item I asked to play has finished".
        # If QML transitions from A to B, it emits mediaFinished(B).
        # This means A is finished.
        
        # Scheduler expects a signal to know that the CURRENT item (A) is done.
        # So we emit media_finished.
        
        # Update our internal state
        self.current_output_url = url
        self.media_finished.emit()

    def play_media(self, payload):
        file_path = payload.get("path")
        duration = payload.get("duration")
        media_type = payload.get("type")
        text_color = payload.get("text_color")
        bg_color = payload.get("bg_color")
        text_size = payload.get("text_size")
        scroll_mode = payload.get("text_scroll_mode")
        
        if not file_path:
            return

        # Prepare content
        path_obj = Path(file_path)
        content_or_path = str(path_obj.resolve())
        
        # Local Preview Setup
        if media_type == "text":
            self.text_mode = True
            try:
                if path_obj.exists():
                    text_content = path_obj.read_text(encoding="utf-8")
                    content_or_path = text_content # Use content for QML too
            except:
                text_content = "Error reading file"
                content_or_path = text_content
                
            self.preview_text.setText(text_content)
            self.preview_text.show()
            self.preview_player.stop()
        else:
            self.text_mode = False
            self.preview_text.hide()
            if path_obj.exists():
                media = self.instance.media_new(str(path_obj))
                self.preview_player.set_media(media)
                self.preview_player.audio_set_mute(True) # Mute preview
                self.preview_player.play()
        
        if self.output_window:
            self.output_window.text_label.hide()

        # Output Window Setup
        if self.output_window:
            # Logic to determine if we need force_play
            req_url = content_or_path
            
            curr_url = self.current_output_url
            should_force = True
            
            # Check if seamless transition already happened
            if curr_url:
                if media_type == "text":
                    if curr_url == req_url:
                        should_force = False
                else:
                    # Handle file:/// prefix
                    if curr_url.startswith("file:///"):
                        curr_path = QUrl(curr_url).toLocalFile()
                    else:
                        curr_path = curr_url
                    
                    if str(Path(curr_path).resolve()) == str(path_obj.resolve()):
                        should_force = False
            
            dur_ms = (duration or 10) * 1000
            
            if should_force:
                print(f"[MediaPlayer] Force playing {media_type}")
                self.output_window.force_play(req_url, media_type, dur_ms, text_color, bg_color, text_size, scroll_mode)
                self.current_output_url = req_url
            else:
                print(f"[MediaPlayer] Skipping force_play (Already playing)")

        # Reset timers
        self.current_duration = duration if duration else 10
        self.elapsed_seconds = 0
        self.time_updated.emit(0, self.current_duration)

    def prefetch_next(self, payload):
        if not payload or not self.output_window:
            return
            
        path = payload.get("path")
        media_type = payload.get("type")
        duration = payload.get("duration")
        text_color = payload.get("text_color")
        bg_color = payload.get("bg_color")
        text_size = payload.get("text_size")
        scroll_mode = payload.get("text_scroll_mode")
        
        if path:
            content_or_path = str(Path(path).resolve())
            if media_type == "text":
                try:
                    if Path(path).exists():
                        content_or_path = Path(path).read_text(encoding="utf-8")
                except:
                    pass
            
            dur_ms = (duration or 10) * 1000
            print(f"[MediaPlayer] Prefetching {media_type}")
            self.output_window.prepare_next(content_or_path, media_type, dur_ms, text_color, bg_color, text_size, scroll_mode)

    def _handle_text_play(self, payload):
        pass # Deprecated, logic moved to play_media

    def _on_timer_tick(self):
        if self._disposed:
            return
            
        # Update elapsed time
        if self.text_mode:
            self.elapsed_seconds += 0.2
            # Only emit finished if NO output window (QML handles finishing)
            if not self.output_window and self.current_duration > 0 and self.elapsed_seconds >= self.current_duration:
                self.media_finished.emit()
            self.time_updated.emit(int(self.elapsed_seconds), int(self.current_duration))
            return

        # Video/Image mode
        if self.output_window:
            pos, dur = self.output_window.get_time_info()
            if dur > 0:
                self.elapsed_seconds = pos / 1000.0
                self.current_duration = dur / 1000.0
                self.time_updated.emit(int(self.elapsed_seconds), int(self.current_duration))
                
                # Update overlay if needed
                self.output_window.update_time(int(self.elapsed_seconds), int(self.current_duration))
            else:
                # Fallback for image timer if QML doesn't report it (we set property to 0/10000 but maybe it fails)
                # If QML reports 0, we rely on QML to emit mediaFinished.
                pass

    def stop(self):
        self.preview_player.stop()
        # QML output stop? forcePlay("")?
        # self.output_window.force_play("", "image")
        pass

    def cleanup(self):
        self._disposed = True
        self.stop()
        self.preview_player.release()

    def play(self):
        self.preview_player.play()
        
    def pause(self):
        self.preview_player.pause()
