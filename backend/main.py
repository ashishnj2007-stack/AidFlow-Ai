from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from database import Base, engine, get_db
from models import Donation, Rider, Shelter, Assignment, Event
from schemas import DonationCreate, RiderCreate, ShelterCreate, DemandUpdate
from safety import now_utc
from dispatch import run_dispatch, event
from recovery import release_once, expire_assignment, reroute_in_transit
from seed import seed_demo

Base.metadata.create_all(bind=engine)
app = FastAPI(title="AidFlow AI API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    from database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(Donation).count() == 0: seed_demo(db)
    finally: db.close()

def serialize(obj):
    data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    for k, v in data.items():
        if hasattr(v, "isoformat"): data[k] = v.isoformat()
    return data

def log(db, kind, message): db.add(Event(kind=kind, message=message))

@app.get("/api/health")
def health(): return {"status": "ok"}

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = now_utc()
    donations = db.scalars(select(Donation).order_by(Donation.expires_at)).all()
    riders = db.scalars(select(Rider)).all(); shelters = db.scalars(select(Shelter)).all(); assignments = db.scalars(select(Assignment).order_by(Assignment.created_at.desc())).all()
    active = [a for a in assignments if a.status in {"reserved", "claimed", "in_transit", "picked_up"}]
    urgent = [d for d in donations if d.remaining_quantity > 0 and d.expires_at > now and d.expires_at <= now + timedelta(hours=1)]
    events = db.scalars(select(Event).order_by(Event.created_at.desc()).limit(12)).all()
    return {"total_donations": len(donations), "available_meals": sum(d.remaining_quantity for d in donations if d.expires_at > now), "active_riders": sum(r.status == "available" for r in riders), "active_deliveries": len(active), "urgent_donations": [serialize(d) for d in urgent], "assignments": [serialize(a) for a in assignments[:12]], "events": [serialize(e) for e in events]}

@app.get("/api/donations")
def get_donations(db: Session = Depends(get_db)): return [serialize(x) for x in db.scalars(select(Donation).order_by(Donation.id)).all()]
@app.post("/api/donations", status_code=201)
def create_donation(body: DonationCreate, db: Session = Depends(get_db)):
    # Normalize timezone-aware input to UTC before comparing with naive UTC DB timestamps.
    exp = body.expires_at
    if exp.tzinfo is not None:
        from datetime import timezone
        exp = exp.astimezone(timezone.utc).replace(tzinfo=None)
    if exp <= now_utc(): raise HTTPException(422, "Expiry must be in the future (UTC). Please choose a later deadline.")
    d = Donation(**body.model_dump(exclude={"expires_at"}), expires_at=exp, remaining_quantity=body.quantity, status="available")
    db.add(d); log(db, "donation", f"Donation created by {body.donor_name}: {body.quantity} {body.item_type}."); db.commit(); db.refresh(d); return serialize(d)
@app.get("/api/riders")
def get_riders(db: Session = Depends(get_db)): return [serialize(x) for x in db.scalars(select(Rider).order_by(Rider.id)).all()]
@app.post("/api/riders", status_code=201)
def create_rider(body: RiderCreate, db: Session = Depends(get_db)):
    r = Rider(**body.model_dump(), reserved_capacity=0, status="available"); db.add(r); db.commit(); db.refresh(r); return serialize(r)
@app.get("/api/shelters")
def get_shelters(db: Session = Depends(get_db)): return [serialize(x) for x in db.scalars(select(Shelter).order_by(Shelter.id)).all()]
@app.post("/api/shelters", status_code=201)
def create_shelter(body: ShelterCreate, db: Session = Depends(get_db)):
    s = Shelter(**body.model_dump(), status="open"); db.add(s); db.commit(); db.refresh(s); return serialize(s)
@app.post("/api/dispatch")
def dispatch(db: Session = Depends(get_db)): return run_dispatch(db)

@app.post("/api/assignments/{assignment_id}/claim")
def claim(assignment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assignment, assignment_id)
    if not a: raise HTTPException(404, "Assignment not found.")
    if a.status != "reserved": raise HTTPException(409, f"Cannot claim assignment in status '{a.status}'.")
    if a.claim_expires_at and a.claim_expires_at <= now_utc(): raise HTTPException(409, "Reservation has expired; run expiry recovery.")
    a.status = "claimed"; log(db, "claim", f"Rider claimed assignment #{a.id}."); db.commit(); return serialize(a)
@app.post("/api/assignments/{assignment_id}/pickup")
def pickup(assignment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assignment, assignment_id)
    if not a: raise HTTPException(404, "Assignment not found.")
    if a.status not in {"reserved", "claimed"}: raise HTTPException(409, f"Cannot confirm pickup in status '{a.status}'.")
    if a.claim_expires_at and a.claim_expires_at <= now_utc(): raise HTTPException(409, "Reservation has expired.")
    if now_utc() >= a.estimated_arrival: pass
    a.status = "in_transit"; a.claim_expires_at = None; log(db, "pickup", f"Pickup confirmed for assignment #{a.id}."); db.commit(); return serialize(a)
@app.post("/api/assignments/{assignment_id}/deliver")
def deliver(assignment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assignment, assignment_id)
    if not a: raise HTTPException(404, "Assignment not found.")
    if a.status != "in_transit": raise HTTPException(409, "Delivery can only be confirmed for an in-transit assignment.")
    r = db.get(Rider, a.rider_id); r.reserved_capacity = max(0, r.reserved_capacity - a.quantity); a.status = "delivered"; a.note = "Delivery explicitly confirmed by operator."; log(db, "delivery", f"Delivery confirmed for assignment #{a.id}."); db.commit(); return serialize(a)
@app.post("/api/assignments/{assignment_id}/expire")
def expire(assignment_id: int, db: Session = Depends(get_db)):
    payload, code = expire_assignment(db, assignment_id)
    if code != 200: raise HTTPException(code, payload["error"])
    return payload
@app.patch("/api/shelters/{shelter_id}/demand")
def update_demand(shelter_id: int, body: DemandUpdate, db: Session = Depends(get_db)):
    s = db.get(Shelter, shelter_id)
    if not s: raise HTTPException(404, "Shelter not found.")
    s.demand = body.demand; result = []
    if body.demand == 0:
        active = db.scalars(select(Assignment).where(Assignment.shelter_id == shelter_id, Assignment.status == "in_transit")).all()
        for a in active: result.append({"assignment_id": a.id, **reroute_in_transit(db, a)})
    log(db, "demand", f"Demand for {s.name} updated to {body.demand}."); db.commit()
    return {"shelter": serialize(s), "recovery": result}
@app.post("/api/demo/reset")
def reset(db: Session = Depends(get_db)):
    seed_demo(db); return {"message": "Demo data reset.", "dashboard": dashboard(db)}
@app.post("/api/demo/simulate-ghost")
def simulate_ghost(db: Session = Depends(get_db)):
    a = db.scalars(select(Assignment).where(Assignment.status == "reserved").order_by(Assignment.id)).first()
    if not a: raise HTTPException(404, "No reserved assignment available to simulate.")
    a.claim_expires_at = now_utc() - timedelta(seconds=1); db.commit()
    payload, code = expire_assignment(db, a.id)
    if code != 200: raise HTTPException(code, payload.get("error", "Could not expire reservation."))
    return {"scenario": "ghost_reservation", "assignment_id": a.id, **payload}
@app.post("/api/demo/simulate-shelter-close")
def simulate_shelter_close(db: Session = Depends(get_db)):
    a = db.scalars(select(Assignment).where(Assignment.status == "in_transit").order_by(Assignment.id)).first()
    if not a: raise HTTPException(404, "No in-transit assignment available. Reset demo data first.")
    s = db.get(Shelter, a.shelter_id); s.demand = 0
    result = reroute_in_transit(db, a); log(db, "simulation", f"Simulated demand drop at {s.name}."); db.commit()
    return {"scenario": "shelter_demand_zero", "assignment_id": a.id, **result}
