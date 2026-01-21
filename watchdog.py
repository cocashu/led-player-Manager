import sys
import time
import subprocess
from pathlib import Path
from utils.logger import setup_logger


logger = setup_logger(name="Watchdog", log_file="logs/watchdog.log")


def resolve_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def build_command(base_dir: Path):
    exe_path = base_dir / "LEDController.exe"
    py_path = base_dir / "main.py"
    if exe_path.exists():
        logger.info("Watchdog using executable target: %s", exe_path)
        return [str(exe_path)]
    if py_path.exists():
        logger.info("Watchdog using python target: %s %s", sys.executable, py_path)
        return [sys.executable, str(py_path)]
    logger.error("No executable or script target found (expected %s or %s)", exe_path, py_path)
    return None


def main():
    base_dir = resolve_base_dir()
    while True:
        cmd = build_command(base_dir)
        if not cmd:
            time.sleep(10)
            continue
        logger.info("Starting main process: %s", cmd)
        try:
            proc = subprocess.Popen(cmd, cwd=str(base_dir))
            code = proc.wait()
            logger.warning("Main process exited with code %s (0x%08X)", code, code & 0xFFFFFFFF)
        except Exception as e:
            logger.error("Failed to start or monitor main process: %s", e)
        time.sleep(5)


if __name__ == "__main__":
    main()
