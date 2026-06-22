import config
from flask import flash, redirect, url_for

def ensure_system_ready():
    """
    Central lock for restore mode
    """
    if config.RESTORE_IN_PROGRESS:
        flash("System is restoring backup. Try again later.", "warning")
        return False
    return True