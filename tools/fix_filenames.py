import sqlite3
import os
import sys
import uuid
import re
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "led.db"

def is_ascii(s):
    return all(ord(c) < 128 for c in s)

def fix_filenames():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, name, path FROM media")
        rows = cursor.fetchall()
        
        count = 0
        for row in rows:
            media_id = row['id']
            original_name = row['name']
            current_path_str = row['path']
            
            if not current_path_str:
                continue
                
            current_path = Path(current_path_str)
            filename = current_path.name
            
            # Check if filename needs fixing (non-ascii or spaces)
            # We want strict ASCII, no spaces, no special chars except . _ -
            if is_ascii(filename) and ' ' not in filename:
                continue
                
            if not current_path.exists():
                print(f"Warning: File not found for media {media_id}: {current_path}")
                continue
                
            # Generate new safe filename
            suffix = current_path.suffix
            # Use short UUID to keep it readable but unique
            new_filename = f"{int(os.path.getmtime(current_path))}_{str(uuid.uuid4())[:8]}{suffix}"
            new_path = current_path.parent / new_filename
            
            try:
                # Rename file
                os.rename(current_path, new_path)
                
                # Update database
                # Note: we keep the original 'name' (display name) as is, only change 'path'
                cursor.execute("UPDATE media SET path = ? WHERE id = ?", (str(new_path), media_id))
                
                print(f"Renamed: {filename} -> {new_filename}")
                count += 1
            except Exception as e:
                print(f"Failed to rename {filename}: {e}")
        
        conn.commit()
        print(f"Finished. Fixed {count} files.")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_filenames()
