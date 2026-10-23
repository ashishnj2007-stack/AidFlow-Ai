from sqlalchemy import select
from models import Assignment, Donation, Rider, Shelter, Event
from safety import now_utc
from dispatch import event, run_dispatch

def release_once(db, a, final_status, reason):
    if a.status in {"expired", "delivered", "cancelled"}: return False
    d = db.get(Donation, a.donation_id); r = db.get(Rider, a.rider_id); s = db.get(Shelter, a.shelter_id)
    # Unpicked reservations have already reduced remaining stock/demand; restore them once.
    if a.status in {"reserved", "claimed"}:
        d.remaining_quantity += a.quantity
        s.demand += a.quantity
    if a.status in {"reserved", "claimed", "picked_up", "in_transit"}:
        r.reserved_capacity = max(0, r.reserved_capacity - a.quantity)
    a.status = final_status; a.note = reason
    event(db, final_status, f"Assignment #{a.id}: {reason}")
    return True

def expire_assignment(db, assignment_id):
    a = db.get(Assignment, assignment_id)
    if not a: return {"error": "Assignment not found"}, 404
    if a.status not in {"reserved", "claimed"}: return {"error": f"Cannot expire assignment in status '{a.status}'."}, 409
    if a.claim_expires_at and a.claim_expires_at > now_utc(): return {"error": "Reservation timeout has not elapsed yet."}, 409
    release_once(db, a, "expired", "Claim timed out; reservation released exactly once.")
    db.commit()
    # Reassign only if there is enough safe-use window; dispatch enforces arrival deadline.
    result = run_dispatch(db)
    return {"message": "Reservation expired and released.", "reassignment": result}, 200

def reroute_in_transit(db, a):
    d = db.get(Donation, a.donation_id); old = db.get(Shelter, a.shelter_id); r = db.get(Rider, a.rider_id)
    old.shelter_id if False else None
    candidates = db.scalars(select(Shelter).where(Shelter.id != old.id, Shelter.status == "open", Shelter.demand > 0).order_by(Shelter.id)).all()
    for s in candidates:
        if d.requires_water and not s.water_available: continue
        if d.requires_cooking and not s.cooking_available: continue
        if a.estimated_arrival >= d.expires_at: continue
        qty = min(a.quantity, s.demand)
        if qty <= 0: continue
        # Avoid duplicate quantity: keep this assignment as the same shipment and only change destination.
        if qty < a.quantity:
            # Only reroute full load if the alternative can accept all; otherwise alert operator.
            continue
        s.demand -= a.quantity
        a.shelter_id = s.id
        a.note = f"Rerouted from shelter #{old.id} to shelter #{s.id} after demand dropped to zero."
        event(db, "reroute", f"Assignment #{a.id} rerouted to shelter #{s.id}.")
        return {"rerouted": True, "shelter_id": s.id, "message": a.note}
    a.status = "operator_alert"
    a.note = "Shelter demand became zero; no safe eligible destination can accept the full shipment. Operator action required."
    event(db, "alert", f"Assignment #{a.id}: {a.note}")
    return {"rerouted": False, "alert": a.note}
