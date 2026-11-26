from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    car_id = Column(Integer, ForeignKey("cars.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="booked")  # booked, completed, cancelled, no_show
    cancelled_by = Column(String(20))  # 'master' / 'client' — кто отменил запись
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    reminded_at = Column(DateTime(timezone=True))  # основное напоминание о записи
    reminded_soon_at = Column(DateTime(timezone=True))  # напоминание "скоро" (за 3 часа)
    reminder_last_error_at = Column(DateTime(timezone=True))  # последняя неудачная отправка
    reminder_failures = Column(Integer, nullable=False, default=0)  # число неудач подряд

    client = relationship("Client", back_populates="appointments")
    car = relationship("Car", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
    completed_work = relationship("CompletedWork", back_populates="appointment", uselist=False)