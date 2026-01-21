import sys
import os

# Ensure VLC is found when frozen
if getattr(sys, 'frozen', False):
    # Determine base directory
    if hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    else:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.exists(os.path.join(exe_dir, '_internal')):
            base_dir = os.path.join(exe_dir, '_internal')
        else:
            base_dir = exe_dir
        
    libvlc_path = os.path.join(base_dir, 'libvlc.dll')
    
    # Only set if it exists, otherwise let vlc.py try its default search
    if os.path.exists(libvlc_path):
        os.environ['PYTHON_VLC_LIB_PATH'] = libvlc_path
        os.environ['PYTHON_VLC_MODULE_PATH'] = os.path.join(base_dir, 'plugins')

import faulthandler
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QSystemTrayIcon, QMenu, 
                             QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QSpinBox)
from PyQt6.QtGui import QIcon, QAction, QPixmap
from PyQt6.QtCore import Qt, QTimer, QBuffer, QByteArray, QIODevice
from web_server import start_web_server, restart_web_server
from player.media_player import MediaPlayer
from player.scheduler import Scheduler
from player.output_window import OutputWindow
from utils.config import config
from utils.runtime_state import set_play_start, set_time, clear as clear_runtime, set_snapshot, current as runtime_current
from database.db_manager import db
import json
from pathlib import Path
import socket
import traceback
from datetime import datetime
from utils.logger import logger as app_logger
import vlc
import subprocess

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "error.log"
FATAL_FILE = LOG_DIR / "fatal.log"

try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

_fatal_fp = None
try:
    _fatal_fp = FATAL_FILE.open("a", encoding="utf-8")
    faulthandler.enable(_fatal_fp)
except Exception:
    try:
        faulthandler.enable()
    except Exception:
        pass


def log_exception(exc_type, exc_value, exc_traceback):
    try:
        app_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    except Exception:
        pass
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except Exception:
        pass


sys.excepthook = log_exception

class LEDController(QMainWindow):
    def __init__(self):
        super().__init__()
        self.output_window = None
        self.output_windows = []
        self.preview_enabled = True
        self._heartbeat_counter = 0
        self.init_ui()
        self.init_services()
        self.init_tray()
        
    def init_ui(self):
        self.setWindowTitle("LED屏幕控制器(单机局域网版)")
        self.setGeometry(100, 100, 408, 135)
        
        # Create tabs
        tabs = QTabWidget()
        
        remote_tab = QWidget()
        remote_layout = QVBoxLayout()
        remote_layout.setContentsMargins(12, 12, 12, 12)
        remote_layout.setSpacing(8)
        title = QLabel("远程管理地址")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        remote_layout.addWidget(title)
        # Remote Address Label
        current_port = config.get("server.port", 8080)
        self.remote_addr_label = QLabel(self._get_remote_manage_text(current_port))
        self.remote_addr_label.setTextInteractionFlags(self.remote_addr_label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        remote_layout.addWidget(self.remote_addr_label)
        
        # Web Server Settings
        web_settings_layout = QHBoxLayout()
        web_settings_layout.addWidget(QLabel("Web端口:"))
        
        self.web_port_spin = QSpinBox()
        self.web_port_spin.setRange(1024, 65535)
        self.web_port_spin.setValue(config.get("server.port", 8080))
        self.web_port_spin.setFixedWidth(80)
        web_settings_layout.addWidget(self.web_port_spin)
        
        self.restart_web_btn = QPushButton("开启/重启Web服务")
        self.restart_web_btn.clicked.connect(self.on_restart_web_server)
        web_settings_layout.addWidget(self.restart_web_btn)
        
        web_settings_layout.addStretch()
        remote_layout.addLayout(web_settings_layout)

        remote_layout.addStretch()
        remote_tab.setLayout(remote_layout)
        tabs.addTab(remote_tab, "远程管理")
        
        # Controls moved to Remote tab
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.addWidget(QLabel("输出显示器:"))
        self.screen_combo = QComboBox()
        self.refresh_screens()
        self.screen_combo.setFixedHeight(24)
        controls_layout.addWidget(self.screen_combo)
        apply_btn = QPushButton("应用设置")
        apply_btn.clicked.connect(self.apply_screen_settings)
        apply_btn.setFixedHeight(24)
        controls_layout.addWidget(apply_btn)
        self.toggle_output_btn = QPushButton("关闭输出")
        self.toggle_output_btn.clicked.connect(self.toggle_output_window)
        self.toggle_output_btn.setFixedHeight(24)
        controls_layout.addWidget(self.toggle_output_btn)
        controls_layout.addStretch()
        controls_container = QWidget()
        controls_container.setLayout(controls_layout)
        controls_container.setFixedHeight(32)
        remote_layout.addWidget(controls_container)
        
        
        self.setCentralWidget(tabs)

    def refresh_screens(self):
        self.screen_combo.clear()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            name = screen.name()
            geometry = screen.geometry()
            self.screen_combo.addItem(f"{name} ({geometry.width()}x{geometry.height()})", i)
        
        # Set current selection from config
        target_index = config.get("player.target_screen_index", 1)
        if target_index < len(screens):
            self.screen_combo.setCurrentIndex(target_index)
        else:
            self.screen_combo.setCurrentIndex(0)

    def apply_screen_settings(self):
        index = self.screen_combo.currentData()
        config.set("player.target_screen_index", index)
        if self.output_window:
            QMessageBox.warning(self, "需先关闭输出", "切换显示器前请先关闭视频输出")
            return
        self.setup_output_window(index)
        QMessageBox.information(self, "设置已保存", f"输出目标已设置为显示器 {index}，请开启输出以生效")

    def on_restart_web_server(self):
        port = self.web_port_spin.value()
        config.set("server.port", port)
        
        # Disable button to prevent spamming
        self.restart_web_btn.setEnabled(False)
        self.restart_web_btn.setText("正在重启...")
        QApplication.processEvents()
        
        try:
            restart_web_server(port)
            self.remote_addr_label.setText(self._get_remote_manage_text(port))
            QMessageBox.information(self, "成功", f"Web服务已重启，端口: {port}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"重启Web服务失败: {e}")
        finally:
            self.restart_web_btn.setEnabled(True)
            self.restart_web_btn.setText("开启/重启Web服务")

    def update_output_button_label(self):
        if self.output_window:
            self.toggle_output_btn.setText("关闭输出")
        else:
            self.toggle_output_btn.setText("开启输出")

    # Removed preview monitor controls/buttons

    def toggle_output_window(self):
        """Toggle external output window on/off"""
        if self.output_window:
            try:
                for w in self.output_windows:
                    w.close()
            except Exception:
                pass
            self.output_windows = []
            self.output_window = None
            self.player_widget.set_output_windows([])
            # QMessageBox.information(self, "操作成功", "输出窗口已关闭")
            self.update_output_button_label()
        else:
            index = self.screen_combo.currentData()
            if index is None:
                index = config.get("player.target_screen_index", 1)
            self.setup_output_window(index)
            # QMessageBox.information(self, "操作成功", "输出窗口已开启")
            self.update_output_button_label()

    def setup_output_window(self, screen_index):
        screens = QApplication.screens()
        if screen_index >= len(screens):
            screen_index = 0
            
        target_screen = screens[screen_index]
        
        # Close existing output window if any
        if self.output_window:
            try:
                for w in self.output_windows:
                    w.close()
            except Exception:
                pass
            self.output_windows = []
            self.output_window = None
            
        # Create new output window
        self.output_window = OutputWindow()
        self.output_window.show_on_screen(target_screen)
        self.output_windows = [self.output_window]
        
        # Update player to use this window
        self.player_widget.set_output_windows(self.output_windows)
        self.player_widget.set_extended_active(False)
        self.update_output_button_label()
    
    def setup_output_windows(self, screen_indices):
        screens = QApplication.screens()
        valid_indices = [i for i in screen_indices if 0 <= i < len(screens)]
        if not valid_indices:
            valid_indices = [0]
        if self.output_window:
            try:
                for w in self.output_windows:
                    w.close()
            except Exception:
                pass
        self.output_windows = []
        for idx in valid_indices:
            w = OutputWindow()
            w.show_on_screen(screens[idx])
            self.output_windows.append(w)
        self.output_window = self.output_windows[0] if self.output_windows else None
        self.player_widget.set_output_windows(self.output_windows)
        self.player_widget.set_extended_active(False)
        self.update_output_button_label()
    
    def setup_extended_output(self, screen_indices):
        screens = QApplication.screens()
        valid = [screens[i] for i in screen_indices if 0 <= i < len(screens)]
        if not valid:
            valid = [screens[0]] if screens else []
        if not valid:
            return
        min_x = min(s.geometry().x() for s in valid)
        min_y = min(s.geometry().y() for s in valid)
        max_r = max(s.geometry().right() for s in valid)
        max_b = max(s.geometry().bottom() for s in valid)
        from PyQt6.QtCore import QRect
        union = QRect(min_x, min_y, max_r - min_x + 1, max_b - min_y + 1)
        if self.output_window:
            try:
                for w in self.output_windows:
                    w.close()
            except Exception:
                pass
        self.output_windows = []
        self.output_window = OutputWindow()
        self.output_window.show_on_rect(union)
        self.output_windows = [self.output_window]
        self.player_widget.set_output_window(self.output_window)
        self.player_widget.set_extended_active(True)
        self.update_output_button_label()

    def init_services(self):
        # Start Web Server
        port = config.get("server.port", 8080)
        start_web_server(port=port)
        try:
            self.remote_addr_label.setText(self._get_remote_manage_text(port))
        except Exception:
            pass
        # Create player (no local preview UI)
        self.player_widget = MediaPlayer()
        
        # Initialize Output Window based on DB config
        try:
            row = db.fetch_one("SELECT * FROM screen_config WHERE id = 1")
            if row:
                mode = row.get("output_mode") or "specified"
                targets_json = row.get("output_targets") or "[]"
                scale_mode = row.get("extended_scale_mode")
                
                try:
                    targets = json.loads(targets_json)
                except:
                    targets = []
                
                if mode == "specified":
                    idx = targets[0] if targets else config.get("player.target_screen_index", 1)
                    if idx >= len(QApplication.screens()):
                        idx = 0
                    self.setup_output_window(idx)
                elif mode == "sync":
                    self.setup_output_windows(targets if targets else [0])
                elif mode == "extended":
                    self.setup_extended_output(targets if targets else [0])
                    if scale_mode:
                        self.player_widget.set_extended_scale_mode(scale_mode)
                # mode == "off" do nothing (default state)
            else:
                # Fallback to config.json
                target_index = config.get("player.target_screen_index", 1)
                if target_index >= len(QApplication.screens()):
                    target_index = 0
                self.setup_output_window(target_index)
        except Exception as e:
            print(f"Error loading output config: {e}")
            # Fallback
            target_index = config.get("player.target_screen_index", 1)
            if target_index >= len(QApplication.screens()):
                target_index = 0
            self.setup_output_window(target_index)
        
        # Initialize Scheduler
        self.scheduler = Scheduler()
        
        # Connect signals
        self.scheduler.play_media.connect(self.on_play_media)
        self.scheduler.prefetch_media.connect(self.player_widget.prefetch_next)
        self.player_widget.time_updated.connect(self.scheduler.on_time_tick)
        self.player_widget.media_finished.connect(self.scheduler.on_media_finished)
        self.player_widget.time_updated.connect(self.on_time_updated)
        self.scheduler.stop_requested.connect(self.player_widget.stop)
        
        # Initial check
        self.scheduler.check_schedule()
        self.update_output_button_label()
        
        self._cmd_timer = QTimer(self)
        self._cmd_timer.timeout.connect(self._check_commands)
        self._cmd_timer.start(200)

        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.timeout.connect(self.capture_output_snapshot)
        self._snapshot_timer.start(1000)

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._log_heartbeat)
        self._heartbeat_timer.start(60000)
        
    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("LED播放控制器")
        
        menu = QMenu()
        
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show)
        menu.addAction(show_action)
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
    def quit_app(self):
        try:
            app_logger.info("quit_app called, beginning shutdown")
        except Exception:
            pass
        try:
            if hasattr(self, "scheduler") and self.scheduler and hasattr(self.scheduler, "timer"):
                self.scheduler.timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_snapshot_timer") and self._snapshot_timer:
                self._snapshot_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_cmd_timer") and self._cmd_timer:
                self._cmd_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_heartbeat_timer") and self._heartbeat_timer:
                self._heartbeat_timer.stop()
        except Exception:
            pass
        try:
            self.player_widget.cleanup()
        except Exception:
            pass
        if self.output_window:
            try:
                for w in self.output_windows:
                    w.close()
            except Exception:
                pass
        QApplication.quit()
        
    def closeEvent(self, event):
        self.quit_app()
        event.accept()

    def _log_heartbeat(self):
        self._heartbeat_counter += 1
        try:
            app_logger.info("Heartbeat: application running, minutes=%s", self._heartbeat_counter)
        except Exception:
            pass
    
    def on_play_media(self, payload):
        self.player_widget.play_media(payload)
        # Reset labels when new media starts
        self.update_time_labels(0, payload.get("duration") or 0)
        try:
            set_play_start(
                payload.get("schedule_id"),
                payload.get("media_id"),
                Path(payload.get("path")).name if payload.get("path") else None,
                payload.get("type"),
                payload.get("path"),
                payload.get("duration") or 0,
                payload.get("text_size"),
                payload.get("text_color"),
                payload.get("bg_color"),
                payload.get("text_scroll_mode")
            )
        except Exception:
            pass
    
    def _check_commands(self):
        from utils.command_bus import command_bus
        cmd = command_bus.get()
        if not cmd:
            return
        name = cmd.get("command")
        data = cmd.get("data")
        if name == "OUTPUT_SET":
            mode = (data or {}).get("mode") or "specified"
            targets = (data or {}).get("targets") or []
            scale_mode = (data or {}).get("scale_mode")
            if mode == "specified":
                idx = targets[0] if targets else config.get("player.target_screen_index", 1)
                config.set("player.target_screen_index", idx)
                if self.output_window:
                    return
                self.setup_output_window(idx)
            elif mode == "sync":
                indices = targets if targets else [config.get("player.target_screen_index", 1)]
                self.setup_output_windows(indices)
            elif mode == "extended":
                indices = targets if targets else [config.get("player.target_screen_index", 1)]
                self.setup_extended_output(indices)
                if scale_mode:
                    self.player_widget.set_extended_scale_mode(scale_mode)
            elif mode == "off":
                if self.output_window:
                    try:
                        for w in self.output_windows:
                            w.close()
                    except Exception:
                        pass
                self.output_windows = []
                self.output_window = None
                self.player_widget.set_output_windows([])
                self.player_widget.set_extended_active(False)
                self.update_output_button_label()
        elif name == "OUTPUT_TEST_COLOR":
            color = (data or {}).get("color") or "#FF0000"
            targets = (data or {}).get("targets") or []
            if targets:
                self.setup_output_windows(targets)
            for w in self.output_windows:
                try:
                    w.show_fill_color(color)
                except Exception:
                    pass
        elif name in ("FORCE_PLAY", "STOP_ALL", "START_ALL"):
            try:
                command_bus.send(name, data)
            except Exception:
                pass
    
    def on_time_updated(self, elapsed, total):
        self.update_time_labels(elapsed, total)
        try:
            set_time(elapsed, total)
        except Exception:
            pass
        if elapsed is not None and total is not None and total > 0 and elapsed >= total:
            try:
                clear_runtime()
            except Exception:
                pass
    
    def update_time_labels(self, elapsed, total):
        try:
            if hasattr(self, "time_plan_label") and hasattr(self, "time_elapsed_label"):
                m1 = (elapsed or 0) // 60
                s1 = (elapsed or 0) % 60
                m2 = (total or 0) // 60
                s2 = (total or 0) % 60
                self.time_plan_label.setText(f"计划时长: {m2:02d}:{s2:02d}")
                self.time_elapsed_label.setText(f"已播放: {m1:02d}:{s1:02d}")
        except Exception:
            pass

    def capture_output_snapshot(self):
        try:
            if not hasattr(self, "player_widget"):
                return
            player = self.player_widget
            if not self.output_window and not getattr(player, "extended_active", False):
                set_snapshot(None)
                return
            try:
                if getattr(player, "text_mode", False):
                    pix = None
                    if self.output_window:
                        try:
                            pix = self.output_window.grab()
                        except Exception as e:
                            pix = None
                            try:
                                app_logger.error("snapshot grab output_window failed: %s", e)
                            except Exception:
                                pass
                    if (pix is None or pix.isNull()) and hasattr(player, "preview_text") and player.preview_text.isVisible():
                        try:
                            pix = player.preview_text.grab()
                        except Exception as e:
                            pix = None
                            try:
                                app_logger.error("snapshot grab preview_text failed: %s", e)
                            except Exception:
                                pass
                    if pix is None or pix.isNull():
                        set_snapshot(None)
                        return
                else:
                    media_path = runtime_current.get("path")
                    media_type = runtime_current.get("media_type")
                    if not media_path:
                        set_snapshot(None)
                        return
                    p = Path(media_path)
                    if not p.exists():
                        set_snapshot(None)
                        return
                    suffix = p.suffix.lower()
                    if media_type == "image" or suffix in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"):
                        pix = QPixmap(str(p))
                        if pix.isNull():
                            set_snapshot(None)
                            return
                    else:
                        tmp_dir = Path("resources") / "tmp"
                        try:
                            tmp_dir.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            pass
                        tmp_path = tmp_dir / "snapshot_ffmpeg.jpg"
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        elapsed = runtime_current.get("elapsed") or 0
                        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
                        if elapsed and elapsed > 1:
                            cmd += ["-ss", str(max(0, int(elapsed) - 1))]
                        cmd += ["-i", str(p), "-frames:v", "1", "-q:v", "5", str(tmp_path)]
                        
                        startupinfo = None
                        if hasattr(subprocess, 'STARTUPINFO'):
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                        try:
                            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, startupinfo=startupinfo)
                            if result.returncode != 0 or not tmp_path.exists():
                                set_snapshot(None)
                                return
                        except Exception as e:
                            try:
                                app_logger.error("snapshot ffmpeg failed: %s", e)
                            except Exception:
                                pass
                            set_snapshot(None)
                            return
                        try:
                            data = tmp_path.read_bytes()
                        except Exception as e:
                            try:
                                app_logger.error("snapshot ffmpeg read failed: %s", e)
                            except Exception:
                                pass
                            set_snapshot(None)
                            return
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                        set_snapshot(data)
                        return
                image = pix.toImage()
                ba = QByteArray()
                buf = QBuffer(ba)
                if not buf.open(QIODevice.OpenModeFlag.WriteOnly):
                    return
                image.save(buf, "JPEG", 80)
                buf.close()
                set_snapshot(bytes(ba))
            except Exception as e:
                try:
                    app_logger.error("snapshot unexpected exception: %s", e)
                except Exception:
                    pass
                return
        except Exception:
            pass

    def _get_remote_manage_text(self, port: int) -> str:
        ip = self._get_local_ip()
        return f"http://{ip}:{port}"

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            if ip:
                return ip
        except Exception:
            pass
        return "127.0.0.1"

if __name__ == "__main__":
    try:
        app_logger.info("Application starting")
    except Exception:
        pass
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        controller = LEDController()
        controller.show()
        code = app.exec()
        try:
            app_logger.info("Application event loop exited with code %s", code)
        except Exception:
            pass
        sys.exit(code)
    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        log_exception(exc_type, exc_value, exc_traceback)
        raise
# pyinstaller LEDController.spec
#更新打包
# pyinstaller LEDController.spec --clean
#运行主机选装VCL播放器，否则会报错：
# Failed to load platform plugin "windows" (available: "minimal, windows").
# Consider setting the QT_QPA_PLATFORM environment variable.
