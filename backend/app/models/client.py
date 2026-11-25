from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)
    phone = Column(String)  # зашифрован
    is_active = Column(Boolean, nullable=False, default=True, server_default=func.true())  # мягкое удаление: False — скрыт из списка
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="client")
    cars = relationship("Car", back_populates="client")
    appointments = relationship("Appointment", back_populates="client")
    completed_works = relationship("CompletedWork", back_populates="client")