from fastapi import APIRouter
from pydantic import BaseModel
from math import radians, sin, cos, sqrt, atan2

router = APIRouter()

# 🔧 Set your college GPS coordinates here
COLLEGE_LAT = 17.307132770018764
COLLEGE_LNG = 78.45283493447559
MAX_DISTANCE = 200  # meters

class GPSInput(BaseModel):
    latitude:  float
    longitude: float

def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))

@router.post("/verify")
def verify_gps(data: GPSInput):
    distance = haversine(data.latitude, data.longitude, COLLEGE_LAT, COLLEGE_LNG)
    if distance <= MAX_DISTANCE:
        return {
            "verified":         True,
            "distance_meters":  round(distance),
            "message":          "You are inside campus ✅"
        }
    return {
        "verified":        False,
        "distance_meters": round(distance),
        "message":         f"You are {round(distance)}m away from campus ❌ Must be within {MAX_DISTANCE}m"
    }