from datetime import timedelta
from sqlalchemy import select
from models import Donation, Rider, Shelter, Assignment, Event
from safety import now_utc, safe_shelter_reason

TRAVEL_MINUTES = {1: 10, 2: 18, 3: 25, 4: 30}
CLAIM_TIMEOUT_MINUTES = 2

def event(db, kind, message): db.add(Event(kind=kind, message=message))

def run_dispatch(db):
    created, rejected = [], []
    donations = db.scalars(select(Donation).order_by(Donation.expires_at)).all()
    riders = db.scalars(select(Rider).order_by(Rider.id)).all()
    shelters = db.scalars(select(Shelter).order_by(Shelter.id)).all()
    now = now_utc()
    for d in donations:
        if d.expires_at <= now or d.remaining_quantity <= 0:
            if d.remaining_quantity <= 0: d.status = "allocated"
            else: d.status = "expired"
            continue
        for s in shelters:
            reason = safe_shelter_reason(d, s)
            if reason:
                if s.status == "open" and (s.demand > 0 or "requires clean water" in reason or "requires cooking facilities" in reason):
                    rejected.append({"donation_id": d.id, "shelter_id": s.id, "reason": reason})
                    event(db, "rejected", f"Donation #{d.id} to shelter #{s.id} rejected: {reason}")
                continue
            for r in riders:
                if d.remaining_quantity <= 0 or s.demand <= 0: break
                if r.status != "available": continue
                free = r.capacity - r.reserved_capacity
                qty = min(d.remaining_quantity, s.demand, free)
                if qty <= 0: continue
                travel = TRAVEL_MINUTES.get(s.id, 20)
                eta = now + timedelta(minutes=travel)
                if eta >= d.expires_at:
                    rejected.append({"donation_id": d.id, "shelter_id": s.id, "reason": "Estimated arrival is after the safe-use deadline."})
                    continue
                a = Assignment(donation_id=d.id, rider_id=r.id, shelter_id=s.id, quantity=qty,
                    status="reserved", claim_expires_at=now + timedelta(minutes=CLAIM_TIMEOUT_MINUTES), estimated_arrival=eta,
                    note=f"ETA {travel} minutes; reservation expires in {CLAIM_TIMEOUT_MINUTES} minutes")
                db.add(a); db.flush()
                d.remaining_quantity -= qty; s.demand -= qty; r.reserved_capacity += qty
                created.append({"id": a.id, "donation_id": d.id, "rider_id": r.id, "shelter_id": s.id, "quantity": qty, "status": a.status, "estimated_arrival": a.estimated_arrival.isoformat()})
                event(db, "dispatch", f"Reserved {qty} from donation #{d.id} for shelter #{s.id} with rider #{r.id}.")
            if d.remaining_quantity <= 0: d.status = "allocated"; break
        if d.remaining_quantity > 0 and d.status != "expired": d.status = "available"
    db.commit()
    return {"created": created, "rejected": rejected, "message": f"Created {len(created)} assignment(s); {len(rejected)} compatibility/deadline rejection(s)."}
