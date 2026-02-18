import json
import logging
from pywebpush import webpush, WebPushException
from app.core.config import settings
from app.models.db import PushSubscription

logger = logging.getLogger(__name__)

def send_push_notification(db_session, title: str, body: str, url: str = "/"):
    """
    Broadcast a push notification to all stored subscriptions.
    """
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not configured. Skipping push notification.")
        return

    subscriptions = db_session.query(PushSubscription).all()
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url
    })

    success_count = 0
    failure_count = 0

    for sub in subscriptions:
        sub_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth
            }
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CLAIMS_EMAIL}
            )
            success_count += 1
        except WebPushException as ex:
            logger.error(f"WebPush error for endpoint {sub.endpoint}: {ex}")
            # If the subscription is no longer valid, delete it
            if ex.response and ex.response.status_code in [404, 410]:
                db_session.delete(sub)
                db_session.commit()
            failure_count += 1
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            failure_count += 1

    logger.info(f"Push notification broadcast finished: {success_count} success, {failure_count} failure")
