from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class Car(Base):
    __tablename__ = "cars"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    brand = Column(String, nullable=False)
    model = Column(String, nullable=False)
    plate_number = Column(String)  # госномер (может быть зашифрован)
    vin = Column(String)           # VIN (может быть зашифрован)
    comment = Column(String)
    is_active = Column(Boolean, nullable=False, default=True, server_default=func.true())  # мягкое удаление
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="cars")
    appointments = relationship("Appointment", back_populates="car")
    completed_works = relationship("CompletedWork", back_populates="car")