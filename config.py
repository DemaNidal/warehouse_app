import os
from dotenv import load_dotenv

load_dotenv()

RESTORE_SECRET = os.getenv("RESTORE_SECRET")
RESTORE_IN_PROGRESS = False
