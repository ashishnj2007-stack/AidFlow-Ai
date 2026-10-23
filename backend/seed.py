from datetime import timedelta
from models import Donation, Rider, Shelter, Assignment, Event
from safety import now_utc

def seed_demo(db):
    db.query(Event).delete(); db.query(Assignment).delete(); db.query(Donation).delete(); db.query(Rider).delete(); db.query(Shelter).delete(); db.commit()
    now = now_utc()
    demo_expiry_minutes = 45  # Adjust this value to tune the live demo urgency window.
    d = Donation(donor_name="Sunrise Community Kitchen", item_type="prepared_meals", quantity=100, remaining_quantity=100,
                 expires_at=now + timedelta(minutes=demo_expiry_minutes), requires_water=False, requires_cooking=False, status="available")
    raw = Donation(donor_name="City Relief Store", item_type="raw_ration_kit", quantity=20, remaining_quantity=20,
                   expires_at=now + timedelta(hours=5), requires_water=True, requires_cooking=True, status="available")
    db.add_all([d, raw]); db.flush()
    riders = [Rider(name="Aarav Patil", capacity=40, reserved_capacity=0, status="available"),
              Rider(name="Meera Shah", capacity=40, reserved_capacity=0, status="available"),
              Rider(name="Kabir Joshi", capacity=20, reserved_capacity=0, status="available")]
    shelters = [Shelter(name="Hope Shelter", demand=35, water_available=True, cooking_available=True, status="open"),
                Shelter(name="Riverbank Relief Camp", demand=40, water_available=False, cooking_available=False, status="open"),
                Shelter(name="Greenfield Community Centre", demand=30, water_available=True, cooking_available=True, status="open"),
                Shelter(name="Eastside Safe Hub", demand=50, water_available=True, cooking_available=True, status="open")]
    db.add_all(riders + shelters); db.flush()
    # Example assignments: one timeout candidate and one in-transit shipment for the live demo.
    a1 = Assignment(donation_id=d.id, rider_id=riders[0].id, shelter_id=shelters[0].id, quantity=10,
        status="reserved", claim_expires_at=now - timedelta(seconds=10), estimated_arrival=now + timedelta(minutes=10), note="Demo ghost reservation: timeout already elapsed.")
    a2 = Assignment(donation_id=d.id, rider_id=riders[1].id, shelter_id=shelters[2].id, quantity=10,
        status="in_transit", claim_expires_at=None, estimated_arrival=now + timedelta(minutes=12), note="Demo in-transit assignment for shelter closure/rerouting test.")
    # Reflect the example assignment reservations in inventory/capacity/demand.
    d.remaining_quantity -= 20; riders[0].reserved_capacity = 10; riders[1].reserved_capacity = 10; shelters[0].demand -= 10; shelters[2].demand -= 10
    db.add_all([a1, a2]); db.add(Event(kind="seed", message="Demo dataset loaded. Assignment #1 is an expired ghost reservation; #2 is in transit.")); db.commit()
