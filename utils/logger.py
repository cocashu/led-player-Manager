import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

def setup_logger(name="LEDController", log_file="logs/app.log", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Create logs directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # File handler
    handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    return logger

logger = setup_logger()
