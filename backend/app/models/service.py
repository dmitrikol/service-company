from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    price_from = Column(Float, nullable=False)  # цена "от"
    duration_minutes = Column(Integer, nullable=False)  # продолжительность в минутах
    is_active = Column(Boolean, default=True)
    is_pdr = Column(Boolean, default=False, nullable=False, server_default=func.false())  # PDR-записи не пересекаются с другими услугами
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # История цен (не обязательно для внешних ключей, но можно связать)
    price_history = relationship("ServicePriceHistory", back_populates="service")
    appointments = relationship("Appointment", back_populates="service")
    completed_works = relationship("CompletedWork", back_populates="service")


class ServicePriceHistory(Base):
    __tablename__ = "service_price_history"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    price_from = Column(Float, nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    service = relationship("Service", back_populates="price_history")