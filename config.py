import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
RESTORE_SECRET = os.getenv("RESTORE_SECRET")
BOOTSTRAP_ADMIN_SECRET = os.getenv("BOOTSTRAP_ADMIN_SECRET")
RESTORE_IN_PROGRESS = False
