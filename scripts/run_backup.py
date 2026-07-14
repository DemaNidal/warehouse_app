import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    filename=os.path.join(os.path.dirname(__file__), "backup_task.log"),
)

from app import app
from utils.backup import create_backup_zip

with app.app_context():
    try:
        name = create_backup_zip()
        logging.info("Scheduled backup created: %s", name)
        print(f"Backup created: {name}")
    except Exception:
        logging.exception("Scheduled backup failed")
        raise
