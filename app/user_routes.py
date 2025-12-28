from fastapi import APIRouter, Depends, HTTPException, Header, Body, Query
from pydantic import BaseModel
from typing import Optional, Annotated, List
from datetime import datetime
import logging

from .database import user_activity_collection, user_follows_collection
from .firebase_config import verify_token

router = APIRouter()
logger = logging.getLogger("uvicorn")

# --- Pydantic Models ---
class UserActivity(BaseModel):
    video_id: str
    event_type: str
    duration_watched: int = 0
    paused_at: Optional[float] = None

class UserFollow(BaseModel):
    channel_id: str

# --- Reusable Authentication Dependency ---
def get_current_user(authorization: Annotated[str | None, Header()] = None):
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    
    id_token = parts[1]
    uid = verify_token(id_token)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return uid

# --- User API Endpoints ---

@router.get("/")
def api_root():
    """Root endpoint for API to verify connectivity."""
    return {"status": "Triangle API is operational"}

# --- User Activity Tracking ---

@router.post("/user/activity")
def track_user_activity(activity: UserActivity, uid: str = Depends(get_current_user)):
    """
    Tracks user interactions with videos (like, watch, pause, etc.)
    """
    try:
        activity_data = {
            "uid": uid,
            "video_id": activity.video_id,
            "last_updated": datetime.utcnow()
        }
        
        update_fields = {}
        
        if activity.event_type == "like":
            update_fields["liked"] = True
        elif activity.event_type == "unlike":
            update_fields["liked"] = False
        elif activity.event_type == "watch":
            update_fields["watched"] = True
            # Increment watch count?
        elif activity.event_type == "pause":
            update_fields["paused_at"] = activity.paused_at
        
        if activity.duration_watched > 0:
             # This would need $inc, so we handle it separately or change structure
             pass 

        if update_fields:
            user_activity_collection.update_one(
                {"uid": uid, "video_id": activity.video_id},
                {"$set": update_fields, "$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True
            )
            
        return {"status": "Activity tracked"}
    except Exception as e:
        logger.error(f"Error tracking activity: {e}")
        raise HTTPException(status_code=500, detail="Failed to track activity")

@router.post("/user/follow")
def follow_channel(follow: UserFollow, uid: str = Depends(get_current_user)):
    """
    Follows a channel.
    """
    try:
        user_follows_collection.update_one(
            {"uid": uid, "channel_id": follow.channel_id},
            {"$set": {"followed_at": datetime.utcnow()}},
            upsert=True
        )
        return {"status": "Channel followed"}
    except Exception as e:
        logger.error(f"Error following channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to follow channel")

@router.delete("/user/follow/{channel_id}")
def unfollow_channel(channel_id: str, uid: str = Depends(get_current_user)):
    """
    Unfollows a channel.
    """
    try:
        result = user_follows_collection.delete_one({"uid": uid, "channel_id": channel_id})
        if result.deleted_count == 0:
             raise HTTPException(status_code=404, detail="Channel not found in follows")
        return {"status": "Channel unfollowed"}
    except Exception as e:
        logger.error(f"Error unfollowing channel: {e}")
        raise HTTPException(status_code=500, detail="Failed to unfollow channel")

@router.get("/user/follows")
def get_user_follows(uid: str = Depends(get_current_user)):
    """
    Gets list of channels followed by user.
    """
    follows = list(user_follows_collection.find({"uid": uid}, {"_id": 0, "channel_id": 1}))
    return [f["channel_id"] for f in follows]