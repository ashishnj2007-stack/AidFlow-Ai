from datetime import datetime, timedelta

def now_utc(): return datetime.utcnow()

def safe_shelter_reason(donation, shelter):
    if shelter.status != "open": return "Shelter is closed."
    if donation.requires_water and not shelter.water_available: return "Raw ration kit requires clean water; shelter has no clean water."
    if donation.requires_cooking and not shelter.cooking_available: return "Raw ration kit requires cooking facilities; shelter has none."
    if shelter.demand <= 0: return "Shelter has no unmet demand."
    return None

def arrival_for(travel_minutes=15): return now_utc() + timedelta(minutes=travel_minutes)
