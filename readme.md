# LED Playback Controller / LED 播放控制器

[English](#english) | [中文](#chinese)

<a name="english"></a>
## 🇬🇧 English

### Introduction
A professional LED screen playback control system built with **Python**, **PyQt6**, and **FastAPI**. Designed for stability and performance, this controller provides seamless media playback with professional transition effects, controllable via a local GUI or a remote Web interface.

> **Note**: The vast majority of the code in this project was generated with the assistance of AI.

### Key Features
- **Multi-Format Support**: Seamlessly plays **Images**, **Videos**, and **Text**.
- **High-Performance Rendering**: Utilizes **QML** for hardware-accelerated rendering.
- **Seamless Transitions**: Implements **"Ping-Pong" double buffering** and **Zoom Crossfade** effects for gapless media switching (no black screens between clips).
- **Web Management**: Built-in Web Server (FastAPI) for remote media upload, playlist management, and scheduling.
- **Robust Scheduling**: Custom scheduler for precise timing and priority management.
- **Advanced Text Rendering**: Supports static display and scrolling (marquee) modes with customizable font size, colors, and backgrounds.
- **Dual-Mode Operation**: Supports standalone operation or integration with LED sender cards (via screen positioning).

### Prerequisites
- **Operating System**: Developed and tested on **Windows 10**. Other operating systems have not been verified.
- Python 3.10 or higher
- **VLC Media Player** (must be installed on the system as `libvlc` is required for video decoding)

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/led-player-Manage.git
   cd led-player-Manage
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure **VLC Media Player** is installed.
   - On Windows, install the 64-bit version of VLC if using 64-bit Python.

### Usage
Run the main application:
```bash
python main.py
```

- The application will launch the GUI (System Tray Icon & Control Panel).
- The Web Server will start automatically on port **8080** (default).
- Access the Web Interface at: `http://localhost:8080`

### Project Structure
- `main.py`: Entry point of the application.
- `player/`: Core playback logic (QML rendering, MediaPlayer, Scheduler).
- `web/`: Web application backend (API routes).
- `web_server.py`: Web server initialization.
- `database/`: SQLite database management.
- `utils/`: Configuration and helper utilities.

### Contributing & Feedback
We welcome contributions and suggestions! If you have ideas for improvements or encounter any issues:
- **Issues**: Please file a bug report or feature request in the [Issues](https://github.com/cocashu/led-player-Manager/issues) section.
- **Pull Requests**: Feel free to submit a PR with your enhancements.

---

<a name="chinese"></a>
## 🇨🇳 中文

### 项目简介
本项目是一个基于 **Python**、**PyQt6** 和 **FastAPI** 构建的专业 LED 大屏播放控制系统。专为高稳定性与高性能设计，提供专业级的媒体播放体验，支持无缝切换与丰富的过渡特效，可通过本地 GUI 或 Web 界面进行管理。

> **说明**：本项目绝大部分代码由 AI 辅助生成。

### 核心功能
- **多格式支持**：完美支持 **图片**、**视频** 和 **富文本** 播放。
- **高性能渲染**：采用 **QML** 技术进行硬件加速渲染，确保画面流畅。
- **无缝切换**：独创 **“乒乓”双缓冲 (Ping-Pong Buffering)** 机制配合 **缩放淡入淡出 (Zoom Crossfade)** 特效，实现媒体间零延迟、无黑屏切换。
- **Web 远程管理**：内置 FastAPI Web 服务器，支持远程上传素材、编辑节目单和设置定时任务。
- **精准调度**：内置高精度调度器，支持按时间段、优先级进行节目排期。
- **高级文字渲染**：支持 **静态展示** 和 **滚动跑马灯** 模式，可自定义字号、字体颜色及背景色。
- **双模运行**：支持单机运行或配合 LED 发送卡使用（通过窗口定位）。

### 环境要求
- **操作系统**：本项目基于 **Windows 10** 开发与测试，未在其他操作系统上验证。
- Python 3.10 或更高版本
- **VLC Media Player** (系统必须安装 VLC，程序依赖 `libvlc` 进行视频解码)

### 安装说明
1. 克隆项目代码：
   ```bash
   git clone https://github.com/yourusername/led-player-Manage.git
   cd led-player-Manage
   ```

2. 安装 Python 依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 确保已安装 **VLC Media Player**。
   - Windows 用户请注意：如果使用 64 位 Python，请安装 64 位 VLC。

### 使用方法
运行主程序：
```bash
python main.py
```

- 程序启动后会显示 GUI 控制面板（及系统托盘图标）。
- Web 服务将自动在 **8080** 端口启动。
- 打开浏览器访问 Web 管理界面：`http://localhost:8080`

### 项目结构
- `main.py`: 程序启动入口。
- `player/`: 核心播放逻辑（QML 渲染、媒体播放器、调度器）。
- `web/`: Web 后端应用（API 路由）。
- `web_server.py`: Web 服务器初始化脚本。
- `database/`: SQLite 数据库管理。
- `utils/`: 配置与通用工具模块。

### 贡献与反馈 (Contributing)
欢迎任何形式的贡献和建议！如果您有更好的想法或发现了问题：
- **提交 Issue**：请在 [Issues](https://github.com/cocashu/led-player-Manager/issues) 页面提交 Bug 报告或功能建议。
- **提交 PR**：欢迎 Fork 本项目并提交 Pull Request 来贡献代码。
