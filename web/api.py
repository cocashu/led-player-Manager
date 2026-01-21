from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pathlib import Path
import shutil
import time
import subprocess
from database.db_manager import db
from pydantic import BaseModel
from typing import Optional
from utils.command_bus import command_bus
from datetime import datetime
from utils.runtime_state import current as runtime_current, get_snapshot
import hashlib
import json

import uuid
import re
import requests
from utils.config import MEDIA_DIR as MEDIA_ROOT

router = APIRouter()

class ScheduleCreate(BaseModel):
    media_id: int
    start_time: str
    end_time: str
    play_duration: Optional[int] = None
    priority: int = 0
    is_temporary: bool = False
    text_size: Optional[int] = None
    text_color: Optional[str] = None
    bg_color: Optional[str] = None
    text_scroll_mode: Optional[str] = None
 
class ScheduleUpdate(BaseModel):
    play_duration: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    text_size: Optional[int] = None
    text_color: Optional[str] = None
    bg_color: Optional[str] = None
    priority: Optional[int] = None
    text_scroll_mode: Optional[str] = None

class PlayWindowUpdate(BaseModel):
    enabled: bool
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class OutputSet(BaseModel):
    mode: str
    targets: Optional[list[int]] = None
    scale_mode: Optional[str] = None

class CameraConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None
    stream_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    notes: Optional[str] = None

def _validate_hhmm(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if not re.match(r"^\d{2}:\d{2}$", value):
        raise HTTPException(status_code=400, detail="Invalid time format, expected HH:MM")
    hh, mm = value.split(":")
    h = int(hh)
    m = int(mm)
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise HTTPException(status_code=400, detail="Invalid time value")
    return f"{h:02d}:{m:02d}"


class LoginRequest(BaseModel):
    username: str
    password: str


SESSIONS: dict[str, int] = {}


def get_current_user(request: Request) -> int:
    session_id = request.cookies.get("session_id")
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return SESSIONS[session_id]


@router.post("/login")
async def login(data: LoginRequest, response: Response):
    user = db.fetch_one("SELECT * FROM users WHERE username = ?", (data.username,))
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    ph = hashlib.sha256(data.password.encode("utf-8")).hexdigest()
    if ph != user["password_hash"]:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = user["id"]
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        max_age=86400,
        samesite="lax",
        path="/api",
    )
    return {
        "status": "success",
        "user": {"id": user["id"], "username": user["username"], "is_admin": user["is_admin"]},
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
    response.delete_cookie("session_id")
    return {"status": "success"}


@router.get("/auth/check")
async def auth_check(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and session_id in SESSIONS:
        return {"status": "authenticated"}
    return {"status": "unauthenticated"}

@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    media_type: str = Form(...),
    user_id: int = Depends(get_current_user)
):
    """上传媒体文件"""
    if media_type not in ['video', 'image', 'text']:
        raise HTTPException(status_code=400, detail="Invalid media type")

    original_name = file.filename or ""
    ext = Path(original_name).suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".pngg"}
    video_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".ogg"}
    text_exts = {".txt"}

    detected_type = media_type
    if ext in image_exts:
        detected_type = "image"
    elif ext in text_exts:
        detected_type = "text"
    elif ext in video_exts:
        detected_type = "video"

    normalized_suffix = ".png" if ext == ".pngg" else ext

    # 保存文件
    media_dir = MEDIA_ROOT / detected_type
    media_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique, safe filename
    # Use timestamp + short uuid + extension to ensure ASCII-only path
    timestamp = int(time.time())
    safe_filename = f"{timestamp}_{str(uuid.uuid4())[:8]}{normalized_suffix}"
    
    file_path = media_dir / safe_filename
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 如果是视频，确保格式为 MP4 (H.264/AAC)
    if detected_type == 'video':
        try:
            should_convert = False
            if file_path.suffix.lower() != ".mp4":
                should_convert = True
            else:
                # Check codec for existing MP4
                try:
                    check_cmd = [
                        "ffprobe", "-v", "error", 
                        "-select_streams", "v:0", 
                        "-show_entries", "stream=codec_name", 
                        "-of", "default=noprint_wrappers=1:nokey=1", 
                        str(file_path)
                    ]
                    # Use creationflags for Windows to hide console window
                    startupinfo = None
                    if hasattr(subprocess, 'STARTUPINFO'):
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        
                    res = subprocess.run(
                        check_cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True,
                        startupinfo=startupinfo
                    )
                    codec = res.stdout.strip()
                    if codec != "h264":
                        should_convert = True
                except Exception:
                    # If check fails, assume safe to leave alone or maybe convert?
                    # Let's assume if we can't probe, we might as well try to convert if we want to be safe,
                    # but maybe better to just leave it to avoid breaking valid files.
                    pass

            if should_convert:
                output_path = file_path.with_suffix(".mp4")
                # If path is same (e.g. replacing h265 mp4), use temp file
                if output_path == file_path:
                    output_path = file_path.with_name(f"temp_{file_path.name}")
                
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(file_path),
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "18",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(output_path)
                ]
                
                startupinfo = None
                if hasattr(subprocess, 'STARTUPINFO'):
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                
                if result.returncode == 0 and output_path.exists():
                    try:
                        if output_path != file_path:
                            file_path.unlink(missing_ok=True)
                            output_path.rename(file_path)
                        # If we used a temp name that wasn't rename, we should handle that, 
                        # but here rename(file_path) overwrites original.
                    except Exception:
                        pass
                    # file_path is now the converted file (or original name with new content)
        except Exception:
            # ffmpeg 不存在或转码失败时，保留原文件
            pass
    
    # 计算文件大小（以最终保存文件为准）
    file_size = getattr(file, "size", None)
    try:
        file_size = file_path.stat().st_size
    except Exception:
        pass
    
    # 保存到数据库
    try:
        media_id = db.execute("""
            INSERT INTO media (name, type, path, upload_time, file_size)
            VALUES (?, ?, ?, datetime('now'), ?)
        """, (original_name, detected_type, str(file_path), file_size))
        
        return {"status": "success", "id": media_id, "path": str(file_path)}
    except Exception as e:
        # If DB fails, remove file
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule")
async def create_schedule(data: ScheduleCreate, user_id: int = Depends(get_current_user)):
    """创建播放计划"""
    try:
        schedule_id = db.execute("""
            INSERT INTO schedules 
            (media_id, start_time, end_time, play_duration, priority, is_temporary, text_size, text_color, bg_color, text_scroll_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.media_id,
            data.start_time,
            data.end_time,
            data.play_duration,
            data.priority,
            data.is_temporary,
            data.text_size,
            data.text_color,
            data.bg_color,
            data.text_scroll_mode
        ))
        return {"status": "success", "id": schedule_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/system/screens")
async def get_screens():
    try:
        from PyQt6.QtWidgets import QApplication
        screens = QApplication.screens()
        data = []
        for i, s in enumerate(screens):
            g = s.geometry()
            data.append({
                "index": i,
                "name": s.name(),
                "width": g.width(),
                "height": g.height()
            })
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/system/output")
async def set_output(data: OutputSet, user_id: int = Depends(get_current_user)):
    try:
        mode = (data.mode or "").lower()
        if mode not in ("specified", "sync", "extended", "off"):
            raise HTTPException(status_code=400, detail="Invalid mode")
        targets = data.targets or []
        scale_mode = (data.scale_mode or "").lower() if data.scale_mode else None
        command_bus.send("OUTPUT_SET", {"mode": mode, "targets": targets, "scale_mode": scale_mode})
        try:
            tjson = json.dumps(targets, ensure_ascii=False)
        except Exception:
            tjson = "[]"
        db.execute("INSERT OR IGNORE INTO screen_config (id) VALUES (1)")
        db.execute("""
            UPDATE screen_config
            SET output_mode = ?, output_targets = ?, extended_scale_mode = ?
            WHERE id = 1
        """, (mode, tjson, scale_mode))
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/system/output")
async def get_output():
    try:
        row = db.fetch_one("SELECT output_mode, output_targets, extended_scale_mode FROM screen_config WHERE id = 1")
        if not row:
            return {"data": {"mode": "specified", "targets": [], "scale_mode": "fit"}}
        targets = []
        try:
            if row.get("output_targets"):
                targets = json.loads(row.get("output_targets"))
        except Exception:
            targets = []
        return {"data": {"mode": row.get("output_mode") or "specified", "targets": targets, "scale_mode": row.get("extended_scale_mode") or "fit"}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/camera/config")
async def get_camera_config(user_id: int = Depends(get_current_user)):
    try:
        row = db.fetch_one("SELECT id, enabled, name, stream_url, username, notes FROM camera_config WHERE id = 1")
        if not row:
            return {"data": None}
        row["enabled"] = bool(row.get("enabled") or 0)
        return {"data": row}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.put("/camera/config")
async def update_camera_config(data: CameraConfigUpdate, user_id: int = Depends(get_current_user)):
    try:
        db.execute("INSERT OR IGNORE INTO camera_config (id) VALUES (1)")
        updates = []
        params = []
        if data.enabled is not None:
            updates.append("enabled = ?")
            params.append(1 if data.enabled else 0)
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name)
        if data.stream_url is not None:
            updates.append("stream_url = ?")
            params.append(data.stream_url)
        if data.username is not None:
            updates.append("username = ?")
            params.append(data.username)
        if data.password is not None:
            updates.append("password = ?")
            params.append(data.password)
        if data.notes is not None:
            updates.append("notes = ?")
            params.append(data.notes)
        if not updates:
            return {"status": "noop"}
        params.append(1)
        sql = f"UPDATE camera_config SET {', '.join(updates)} WHERE id = ?"
        db.execute(sql, tuple(params))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
class TestColor(BaseModel):
    color: str
    targets: Optional[list[int]] = None

@router.post("/system/output/test_color")
async def test_color(data: TestColor, user_id: int = Depends(get_current_user)):
    try:
        color = data.color
        if not isinstance(color, str) or not color:
            raise HTTPException(status_code=400, detail="Invalid color")
        targets = data.targets or []
        command_bus.send("OUTPUT_TEST_COLOR", {"targets": targets, "color": color})
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/media")
async def get_media_list():
    """获取媒体列表"""
    try:
        media_list = db.fetch_all("SELECT * FROM media ORDER BY upload_time DESC")
        
        # Get IDs of media currently in schedules
        used_media_rows = db.fetch_all("SELECT DISTINCT media_id FROM schedules")
        used_media_ids = {row['media_id'] for row in used_media_rows}
        
        # Add is_used flag
        for media in media_list:
            media['is_used'] = media['id'] in used_media_ids
            
        return {"data": media_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/media/{media_id}")
async def delete_media(media_id: int, user_id: int = Depends(get_current_user)):
    """删除媒体文件"""
    try:
        # Check if used in schedule
        schedule_count = db.fetch_one("SELECT COUNT(*) as count FROM schedules WHERE media_id = ?", (media_id,))
        if schedule_count and schedule_count['count'] > 0:
            raise HTTPException(status_code=400, detail="Cannot delete media that is currently scheduled")
            
        # Get file path
        media = db.fetch_one("SELECT path FROM media WHERE id = ?", (media_id,))
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
            
        # Delete from DB
        db.execute("DELETE FROM media WHERE id = ?", (media_id,))
        
        # Delete from filesystem
        file_path = Path(media['path'])
        if file_path.exists():
            file_path.unlink()
            
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/schedule")
async def get_schedule_list():
    """获取播放计划列表"""
    try:
        schedule_list = db.fetch_all("""
            SELECT s.*, m.name as media_name, m.type as media_type, m.path as media_path, m.duration as default_duration
            FROM schedules s
            JOIN media m ON s.media_id = m.id
            ORDER BY s.priority DESC, COALESCE(s.order_index, 0) ASC, s.start_time ASC
        """)
        return {"data": schedule_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/play_window")
async def get_play_window():
    try:
        row = db.fetch_one("""
            SELECT schedule_window_enabled, schedule_window_start, schedule_window_end
            FROM screen_config
            WHERE id = 1
        """)
        if not row:
            return {"data": {"enabled": False, "start_time": None, "end_time": None}}
        return {
            "data": {
                "enabled": bool(row.get("schedule_window_enabled") or 0),
                "start_time": row.get("schedule_window_start"),
                "end_time": row.get("schedule_window_end"),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/play_window")
async def update_play_window(data: PlayWindowUpdate, user_id: int = Depends(get_current_user)):
    try:
        start_time = _validate_hhmm(data.start_time)
        end_time = _validate_hhmm(data.end_time)
        enabled = 1 if data.enabled else 0
        db.execute("INSERT OR IGNORE INTO screen_config (id) VALUES (1)")
        db.execute("""
            UPDATE screen_config
            SET schedule_window_enabled = ?, schedule_window_start = ?, schedule_window_end = ?
            WHERE id = 1
        """, (enabled, start_time, end_time))
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
@router.put("/schedule/{schedule_id}")
async def update_schedule(schedule_id: int, data: ScheduleUpdate, user_id: int = Depends(get_current_user)):
    """更新播放计划"""
    try:
        schedule = db.fetch_one("SELECT s.*, m.type as media_type FROM schedules s JOIN media m ON s.media_id = m.id WHERE s.id = ?", (schedule_id,))
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        updates = []
        params = []
        if data.play_duration is not None:
            updates.append("play_duration = ?")
            params.append(data.play_duration)
        if data.start_time is not None:
            updates.append("start_time = ?")
            params.append(data.start_time)
        if data.end_time is not None:
            updates.append("end_time = ?")
            params.append(data.end_time)
        if schedule['media_type'] == 'text':
            if data.text_size is not None:
                updates.append("text_size = ?")
                params.append(data.text_size)
            if data.text_color is not None:
                updates.append("text_color = ?")
                params.append(data.text_color)
            if data.bg_color is not None:
                updates.append("bg_color = ?")
                params.append(data.bg_color)
            if data.text_scroll_mode is not None:
                updates.append("text_scroll_mode = ?")
                params.append(data.text_scroll_mode)
        if data.priority is not None:
            updates.append("priority = ?")
            params.append(data.priority)
        if not updates:
            return {"status": "noop"}
        params.append(schedule_id)
        sql = f"UPDATE schedules SET {', '.join(updates)} WHERE id = ?"
        db.execute(sql, tuple(params))
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.post("/schedule/reorder")
async def reorder_schedules(order: list[int], user_id: int = Depends(get_current_user)):
    """根据前端传入的计划ID顺序，更新播放顺序"""
    try:
        for idx, sid in enumerate(order):
            db.execute("UPDATE schedules SET order_index = ? WHERE id = ?", (idx, sid))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs")
async def get_play_logs(limit: int = 100, page: int = 1, start_date: Optional[str] = None, end_date: Optional[str] = None):
    """播放日志明细"""
    try:
        where = []
        params = []
        if start_date:
            where.append("l.start_time >= ?")
            params.append(f"{start_date}T00:00:00")
        if end_date:
            where.append("l.end_time <= ?")
            params.append(f"{end_date}T23:59:59")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        offset = max(0, (page - 1) * limit)
        sql = f"""
            SELECT l.*, m.name as media_name
            FROM play_logs l
            JOIN media m ON l.media_id = m.id
            {where_sql}
            ORDER BY l.start_time DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        logs = db.fetch_all(sql, tuple(params))
        return {"data": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs/stats")
async def get_play_stats():
    """播放统计（每媒体）"""
    try:
        stats = db.fetch_all("""
            SELECT m.id as media_id, m.name as media_name, 
                   COUNT(l.id) as play_count, COALESCE(SUM(l.duration_seconds), 0) as total_seconds
            FROM media m
            LEFT JOIN play_logs l ON l.media_id = m.id
            GROUP BY m.id, m.name
            ORDER BY total_seconds DESC
        """)
        return {"data": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/camera/snapshot")
async def get_camera_snapshot():
    try:
        row = db.fetch_one("SELECT enabled, stream_url, username, password FROM camera_config WHERE id = 1")
        if not row or not (row.get("enabled") or 0):
            return Response(status_code=204)
        url = (row.get("stream_url") or "").strip()
        if not url:
            return Response(status_code=204)
        username = row.get("username") or None
        password = row.get("password") or None
        final_url = url
        if username and final_url.startswith("rtsp://") and "@" not in final_url:
            auth = username
            if password:
                auth = f"{auth}:{password}"
            final_url = "rtsp://" + auth + "@" + final_url[len("rtsp://"):]
        cmd = [
            "ffmpeg",
            "-rtsp_transport",
            "tcp",
            "-i",
            final_url,
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                startupinfo=startupinfo,
            )
        except Exception:
            raise HTTPException(status_code=500, detail="capture_failed")
        if result.returncode != 0 or not result.stdout:
            raise HTTPException(status_code=500, detail="capture_failed")
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        }
        return Response(content=result.stdout, media_type="image/jpeg", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.get("/status/current")
async def get_current_status():
    """当前播放状态"""
    try:
        return {"data": runtime_current}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/preview/snapshot")
async def get_preview_snapshot():
    try:
        data = get_snapshot()
        if not data:
            return Response(status_code=204)
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        }
        return Response(content=data, media_type="image/jpeg", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: Optional[int] = 0

class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[int] = None

@router.get("/users")
async def list_users(user_id: int = Depends(get_current_user)):
    try:
        rows = db.fetch_all("SELECT id, username, is_admin FROM users ORDER BY id ASC")
        return {"data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users")
async def create_user(data: UserCreate, user_id: int = Depends(get_current_user)):
    try:
        ph = hashlib.sha256(data.password.encode("utf-8")).hexdigest()
        db.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)", (data.username, ph, int(data.is_admin or 0)))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/users/{user_id}")
async def update_user(user_id: int, data: UserUpdate, current_user_id: int = Depends(get_current_user)):
    try:
        updates = []
        params = []
        if data.username is not None:
            updates.append("username = ?")
            params.append(data.username)
        if data.password is not None:
            ph = hashlib.sha256(data.password.encode("utf-8")).hexdigest()
            updates.append("password_hash = ?")
            params.append(ph)
        if data.is_admin is not None:
            updates.append("is_admin = ?")
            params.append(data.is_admin)
            
        if not updates:
            return {"status": "noop"}
            
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        db.execute(sql, tuple(params))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user_id: int = Depends(get_current_user)):
    try:
        if user_id == 1: # Protect default admin
             raise HTTPException(status_code=400, detail="Cannot delete default admin")
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return {"status": "success"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/schedule/{schedule_id}")
async def delete_schedule(schedule_id: int, user_id: int = Depends(get_current_user)):
    """删除播放计划"""
    try:
        db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/control/play/{schedule_id}")
async def force_play_schedule(schedule_id: int, user_id: int = Depends(get_current_user)):
    """强制播放指定计划"""
    try:
        command_bus.send("FORCE_PLAY", schedule_id)
        return {"status": "success", "message": f"Command sent to play schedule {schedule_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
@router.post("/control/scheduler/stop")
async def stop_all_schedules(user_id: int = Depends(get_current_user)):
    try:
        command_bus.send("STOP_ALL", None)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
@router.post("/control/scheduler/start")
async def start_all_schedules():
    try:
        command_bus.send("START_ALL", None)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
@router.post("/schedule/{schedule_id}/enable")
async def enable_schedule(schedule_id: int):
    try:
        db.execute("UPDATE schedules SET is_enabled = 1 WHERE id = ?", (schedule_id,))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
@router.post("/schedule/{schedule_id}/disable")
async def disable_schedule(schedule_id: int, user_id: int = Depends(get_current_user)):
    try:
        db.execute("UPDATE schedules SET is_enabled = 0 WHERE id = ?", (schedule_id,))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
