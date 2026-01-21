import sqlite3
import os
import sys
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "led.db"
MEDIA_ROOT = PROJECT_ROOT / "resources" / "media" / "video"

def convert_videos():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get all video files
        cursor.execute("SELECT id, path FROM media WHERE type = 'video'")
        rows = cursor.fetchall()
        
        count = 0
        for row in rows:
            media_id = row['id']
            current_path_str = row['path']
            
            if not current_path_str:
                continue
                
            current_path = Path(current_path_str)
            
            # Skip if file doesn't exist
            if not current_path.exists():
                print(f"Skipping missing file: {current_path}")
                continue
            
            # We want to convert if:
            # 1. It's not .mp4
            # 2. It IS .mp4 but we want to ensure H.264 (optional, but let's stick to extension for now to fix the MOV issue)
            
            # For this task, let's target non-mp4 files specifically
            if current_path.suffix.lower() == '.mp4':
                continue
                
            print(f"Converting {current_path.name} to MP4...")
            
            new_filename = current_path.stem + ".mp4"
            new_path = current_path.parent / new_filename
            
            # FFmpeg command
            cmd = [
                "ffmpeg", "-y",
                "-i", str(current_path),
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(new_path)
            ]
            
            try:
                # Run conversion
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                if result.returncode != 0:
                    print(f"FFmpeg failed for {current_path.name}: {result.stderr.decode()}")
                    continue
                    
                if not new_path.exists():
                    print(f"Conversion failed, output file not created: {new_path}")
                    continue
                    
                # Update database
                cursor.execute("UPDATE media SET path = ? WHERE id = ?", (str(new_path), media_id))
                
                # Delete original file
                try:
                    current_path.unlink()
                except Exception as e:
                    print(f"Warning: Could not delete original file {current_path}: {e}")
                
                print(f"Success: {current_path.name} -> {new_filename}")
                count += 1
                
            except Exception as e:
                print(f"Error converting {current_path.name}: {e}")
        
        conn.commit()
        print(f"Finished. Converted {count} videos.")
        
    except Exception as e:
        print(f"Database error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    convert_videos()
