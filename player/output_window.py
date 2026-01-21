from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtQuickWidgets import QQuickWidget
from pathlib import Path

class OutputWindow(QWidget):
    resized = pyqtSignal()
    media_finished = pyqtSignal(str, str) # url, type

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LED Output")
        
        # Set black background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
        self.setPalette(palette)
        
        # QQuickWidget for QML content
        self.qml_widget = QQuickWidget(self)
        self.qml_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.qml_widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        self.qml_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.qml_widget.setClearColor(QColor(0, 0, 0))
        
        # Load QML
        qml_path = Path(__file__).parent / "output.qml"
        self.qml_widget.setSource(QUrl.fromLocalFile(str(qml_path.resolve())))
        
        # Connect signals
        if self.qml_widget.rootObject():
            self.qml_widget.rootObject().mediaFinished.connect(self._on_media_finished)
            self.qml_widget.rootObject().mediaInfo.connect(self._on_media_info)
        else:
            print("Error: QML root object not found")
            for err in self.qml_widget.errors():
                print(err.toString())

        # Frameless and Always on Top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        
        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.qml_widget)
        self.setLayout(layout)

        self.overlay = QLabel(self)
        self.overlay.setStyleSheet("color: white; background-color: rgba(0,0,0,0.4); padding: 4px; font-size: 16px;")
        self.overlay.move(10, 10)
        self.overlay.hide()
        self.text_label = QLabel(self)
        self.text_label.hide()
        self.fill_label = QLabel(self)
        self.fill_label.hide()
        
        # For compatibility with existing MediaPlayer calls
        self.surface_a = QWidget() # Dummy
        self.surface_b = QWidget() # Dummy

    def _on_media_finished(self, url, type):
        self.media_finished.emit(url, type)
    
    def _on_media_info(self, msg):
        print(f"[QML] {msg}")

    def get_time_info(self):
        if self.qml_widget.rootObject():
            pos = self.qml_widget.rootObject().property("videoPosition")
            dur = self.qml_widget.rootObject().property("videoDuration")
            return pos, dur
        return 0, 0

    def show_on_screen(self, screen):
        if not screen:
            return
        geometry = screen.geometry()
        self.setGeometry(geometry)
        self.showFullScreen()
    
    def show_on_rect(self, rect: QRect):
        if not rect:
            return
        self.setGeometry(rect)
        self.show()

    def resizeEvent(self, event):
        self.overlay.move(10, 10)
        self.fill_label.setGeometry(self.rect())
        self.text_label.setGeometry(self.rect())
        try:
            self.resized.emit()
        except Exception:
            pass
        super().resizeEvent(event)

    def prepare_next(self, url, type, duration=0, text_color=None, bg_color=None, text_size=None, scroll_mode=None):
        if self.qml_widget.rootObject():
            # QML expects URL string (file://...)
            # We assume url is a file path if it doesn't start with file:
            if type == "text":
                qurl = str(url)
            else:
                qurl = QUrl.fromLocalFile(str(url)).toString()
            self.qml_widget.rootObject().prepareNext(qurl, type, duration, text_color, bg_color, text_size, scroll_mode)
            
    def force_play(self, url, type, duration=0, text_color=None, bg_color=None, text_size=None, scroll_mode=None):
        if self.qml_widget.rootObject():
            if type == "text":
                qurl = str(url)
            else:
                qurl = QUrl.fromLocalFile(str(url)).toString()
            self.qml_widget.rootObject().forcePlay(qurl, type, duration, text_color, bg_color, text_size, scroll_mode)

    def update_time(self, elapsed, total=None):
        if total is not None and total > 0:
            m1 = elapsed // 60
            s1 = elapsed % 60
            m2 = total // 60
            s2 = total % 60
            text = f"{m1:02d}:{s1:02d} / {m2:02d}:{s2:02d}"
        else:
            m1 = elapsed // 60
            s1 = elapsed % 60
            text = f"{m1:02d}:{s1:02d}"
        self.overlay.setText(text)
        self.overlay.adjustSize()
        self.overlay.show()

    def clear_overlay(self):
        self.overlay.hide()
    
    def show_fill_color(self, color: str):
        self.fill_label.setStyleSheet(f"background-color: {color};")
        self.fill_label.setGeometry(self.rect())
        self.fill_label.raise_()
        self.fill_label.show()
    
    def clear_fill(self):
        self.fill_label.hide()
