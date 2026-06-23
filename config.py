import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
RESTORE_SECRET = os.getenv("RESTORE_SECRET")
RESTORE_IN_PROGRESS = False
