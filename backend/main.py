from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from pathlib import Path
from datetime import date
import os

app = FastAPI(
    title="City Care Hospital API",
    description="Hospital Appointment Booking & Department Management System",
    version="2.0.0"
)

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"]
)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'hospital.db').as_posix()}"

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

class AppointmentDB(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    date_of_birth = Column(String(20), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    preferred_date = Column(String(20), nullable=False)
    preferred_time = Column(String(20), nullable=False)
    reason = Column(String(500), nullable=False)

Base.metadata.create_all(bind=engine)

class Appointment(BaseModel):
    full_name: str
    date_of_birth: date
    phone: str
    email: EmailStr
    department: str
    preferred_date: date
    preferred_time: str
    reason: str

department_facilities = {
    "Cardiology": [
        "Heart Check-up",
        "ECG",
        "Echocardiography",
        "Cardiac Consultation"
    ],
    "Dentistry": [
        "Dental Check-up",
        "Teeth Cleaning",
        "Root Canal Treatment",
        "Dental Restoration"
    ],
    "General Medicine": [
        "General Helath Check-up",
        "Fever & Infection Care",
        "Chronic Disease Management",
        "Preventive Healthcare"
    ],
    "Pediatrics": [
        "Child Health Check-up",
        "Vaccination",
        "Child Nutrition",
        "Child Illness Treatment"
    ],
    "Pulmonology": [
        "Respiratory Check-up",
        "Asthma Care",
        "Lung Infection Treatment",
        "Breathing Disorder Care"
    ],
    "Orthopedics": [
        "Bone & Joint Check-up",
        "Fracture Treatment",
        "Joint Pain Treatment",
        "Sports Injury Care"
    ]
}

@app.get("/api/health")
def health_check():
    return {
        "status": "success",
        "message": "City Care Hospital Backend is Running!",
        "version": "2.0.0"
    }

@app.get("/api/departments")
def get_departments():
    return department_facilities

@app.get("/api/departments/{department_name}")
def get_department_details(department_name: str):
    normalized_name = department_name.capitalize()
    facilities = department_facilities.get(normalized_name)
    if not facilities:
        raise HTTPException(
            status_code=404,
            detail=f"Department '{department_name}' not found"
        )
    return {
        "department": normalized_name,
        "facilities": facilities
    }

@app.post("/api/appointments", status_code=201)
def book_appointment(appointment: Appointment):
    if appointment.department not in department_facilities:
        raise HTTPException(
            status_code=400,
            detail="Invalid department selected"
        )

    allowed_reasons = department_facilities[appointment.department]
    if appointment.reason not in allowed_reasons and appointment.reason != "General Health Check-up":
        raise HTTPException(
            status_code=400,
            detail="Invalid reason for selected department"
        )

    if appointment.preferred_date <= date.today():
        raise HTTPException(
            status_code=400,
            detail="Appointment date cannot be in the past"
        )

    if (appointment.preferred_date - date.today()).days > 30:
        raise HTTPException(
            status_code=400,
            detail="Appointments cannot be booked more than 90 days in advance"
        )

    if appointment.department == "Pediatrics":
        today = date.today()
        dob = appointment.date_of_birth
        age = today.year - dob.year
        if age >= 18:
            raise HTTPException(
                status_code=400,
                detail="Pediatrics care is reserved for patients aged 18 and below"
            )

    try:
        time_parts = [int(p) for p in appointment.preferred_time.split(":")]
        hour = time_parts[0]
        minute = time_parts[1] if len(time_parts) > 1 else 0
        if hour < 9 or hour > 17 and minute > 0:
            raise HTTPException(
                status_code=400,
                detail="Appointments can only be scheduled between 09:00 and 18:00"
            )
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid time format")

    db = SessionLocal()
    try:
        existing_slot = db.query(AppointmentDB).filter(
            AppointmentDB.department == appointment.department,
            AppointmentDB.preferred_date == str(appointment.preferred_date),
            AppointmentDB.preferred_time == appointment.preferred_time
        ).first()

        if existing_slot and existing_slot.email != str(appointment.email):
            raise HTTPException(
                status_code=409,
                detail="This time slot is already booked for this department. Please choose another time."
            )

        new_appointment = AppointmentDB(
            full_name=appointment.full_name,
            date_of_birth=str(appointment.date_of_birth),
            phone=appointment.phone,
            email=str(appointment.email),
            department=appointment.department,
            preferred_date=str(appointment.preferred_date),
            preferred_time=appointment.preferred_time,
            reason=appointment.reason
        )

        db.add(new_appointment)
        db.commit()
        db.refresh(new_appointment)

        return {
            "message": "Appointment booked successfully!",
            "appointment_id": new_appointment.id
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save appointment"
        )
    finally:
        db.close()

@app.get("/api/appointments")
def get_appointments(department: str = None):
    db = SessionLocal()
    try:
        query = db.query(AppointmentDB)
        if department:
            query = query.filter(AppointmentDB.department == department)
        appointments = query.order_by(AppointmentDB.id.desc()).all()

        return [
            {
                "id": a.id,
                "full_name": a.full_name,
                "date_of_birth": a.date_of_birth,
                "phone": a.phone,
                "email": a.email,
                "department": a.department,
                "preferred_date": a.preferred_date,
                "preferred_time": a.preferred_time,
                "reason": a.reason
            }
            for a in appointments
        ]
    finally:
        db.close()

@app.get("/api/appointments/{appointment_id}")
def get_appointment(appointment_id: int):
    db = SessionLocal()
    try:
        apt = db.query(AppointmentDB).filter(AppointmentDB.id == appointment_id).first()
        if not apt:
            raise HTTPException(status_code=404, detail="Appointment not found")
        return {
            "id": apt.id,
            "full_name": apt.full_name,
            "date_of_birth": apt.date_of_birth,
            "phone": apt.phone,
            "email": apt.email,
            "department": apt.department,
            "preferred_date": apt.preferred_date,
            "preferred_time": apt.preferred_time,
            "reason": apt.reason
        }
    finally:
        db.close()

@app.get("/")
def home():
    homepage = FRONTEND_DIR / "index.html"
    if not homepage.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(homepage)

app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend"
)
