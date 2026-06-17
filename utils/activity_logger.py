from models import (
    db,
    ActivityLog
)

def log_activity(
    user_id,
    action,
    description=""
):

    log = ActivityLog(
        user_id=user_id,
        action=action,
        description=description
    )

    db.session.add(log)

    db.session.commit()