from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pathlib import Path
import mimetypes
import threading
import uvicorn
import os
import sys
from web.api import router as api_router
from utils.logger import logger
from utils.config import WEB_DIR, MEDIA_DIR

app = FastAPI()

# Directories are now resolved in utils.config
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

if not STATIC_DIR.exists() and not getattr(sys, "frozen", False):
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

if not TEMPLATES_DIR.exists() and not getattr(sys, "frozen", False):
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include API router
app.include_router(api_router, prefix="/api")

@app.get("/media_files/{file_path:path}")
async def media_files(file_path: str, range: str = Header(None)):
    base = MEDIA_DIR.resolve()
    full = (MEDIA_DIR / file_path).resolve()
    if base not in full.parents and full != base:
        raise HTTPException(status_code=404, detail="Not found")
    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    
    file_size = full.stat().st_size
    media_type, _ = mimetypes.guess_type(str(full))
    media_type = media_type or "application/octet-stream"

    # Basic headers
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
    }

    # Handle Range request manually for better compatibility
    start = 0
    end = file_size - 1
    status_code = 200
    content_length = file_size

    if range:
        try:
            range_value = range.strip().replace("bytes=", "")
            parts = range_value.split("-")
            range_start = parts[0]
            range_end = parts[1] if len(parts) > 1 else ""
            
            start = int(range_start) if range_start else 0
            end = int(range_end) if range_end else file_size - 1
            
            if end >= file_size:
                end = file_size - 1
            
            content_length = end - start + 1
            status_code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        except Exception:
            pass
            
    headers["Content-Length"] = str(content_length)

    if not range:
        return FileResponse(
            path=str(full),
            media_type=media_type,
            headers=headers
        )

    def iterfile():
        try:
            with open(full, mode="rb") as file_like:
                file_like.seek(start)
                bytes_to_read = content_length
                chunk_size = 1024 * 64
                while bytes_to_read > 0:
                    read_size = min(chunk_size, bytes_to_read)
                    chunk = file_like.read(read_size)
                    if not chunk:
                        break
                    yield chunk
                    bytes_to_read -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            return

    return StreamingResponse(
        iterfile(),
        status_code=status_code,
        headers=headers,
        media_type=media_type
    )

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

class WebServerManager:
    def __init__(self):
        self.server = None
        self.thread = None

    def run(self, port):
        try:
            logger.info(f"Starting Web Server on port {port}...")
            logger.info(f"Web Server WEB_DIR: {WEB_DIR}")
            logger.info(f"Static directory: {STATIC_DIR}")
            logger.info(f"Templates directory: {TEMPLATES_DIR}")
            
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=port,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception as e:
            logger.error(f"Failed to start Web Server: {e}", exc_info=True)

    def start(self, port=8080):
        if self.thread and self.thread.is_alive():
            logger.warning("Web Server thread already active")
            return
            
        self.thread = threading.Thread(target=self.run, args=(port,), daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.should_exit = True
        if self.thread:
            self.thread.join(timeout=3.0)
            self.thread = None
            self.server = None

    def restart(self, port=8080):
        self.stop()
        self.start(port)

_web_server_manager = WebServerManager()

def start_web_server(port=8080):
    """启动Web服务器"""
    _web_server_manager.start(port)

def restart_web_server(port=8080):
    """重启Web服务器"""
    _web_server_manager.restart(port)
