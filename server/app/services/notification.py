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
    # 1. Check if the path to the PEM file is configured
    private_key_path = getattr(settings, "VAPID_PRIVATE_KEY_PATH", None)
    if not private_key_path:
        logger.warning("VAPID_PRIVATE_KEY_PATH not configured. Skipping push notification.")
        return

    # 2. Ensure claims are formatted correctly (must start with mailto: or https:)
    vapid_claims = {"sub": settings.VAPID_CLAIMS_EMAIL}
    if not vapid_claims["sub"].startswith("mailto:") and not vapid_claims["sub"].startswith("https://"):
        vapid_claims["sub"] = f"mailto:{vapid_claims['sub']}"

    subscriptions = db_session.query(PushSubscription).all()
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url
    })

    success_count = 0
    failure_count = 0
    stale_subscriptions = []

    for sub in subscriptions:
        sub_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth
            }
        }
        
        try:
            # 3. pywebpush natively accepts the path to the PEM file
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=private_key_path, 
                vapid_claims=vapid_claims,
                ttl=86400  # 24 hour Time-To-Live
            )
            success_count += 1
            
        except WebPushException as ex:
            logger.error(f"WebPush error for endpoint {sub.endpoint}: {ex}")
            # 4. Clean up dead subscriptions (404/410)
            if ex.response is not None and ex.response.status_code in [404, 410]:
                stale_subscriptions.append(sub)
            failure_count += 1
            
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}", exc_info=True)
            failure_count += 1

    # 5. Batch delete stale subscriptions
    if stale_subscriptions:
        for stale_sub in stale_subscriptions:
            db_session.delete(stale_sub)
        try:
            db_session.commit()
            logger.info(f"Cleaned up {len(stale_subscriptions)} stale subscriptions.")
        except Exception as e:
            db_session.rollback()
            logger.error(f"Failed to commit deletion of stale subscriptions: {e}")

    logger.info(f"Push notification broadcast finished: {success_count} success, {failure_count} failure")
