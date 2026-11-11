import config
from flask import flash

def ensure_system_ready():
    """
    Central lock for restore mode
    """
    if config.RESTORE_IN_PROGRESS:
        flash("النظام قيد استرجاع نسخة احتياطية حالياً، حاول مرة أخرى لاحقاً", "warning")
        return False
    return True