from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class CompletedWork(Base):
    __tablename__ = "completed_works"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_completed_works_appointment_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)  # может быть создана вручную
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    car_id = Column(Integer, ForeignKey("cars.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    description = Column(Text)  # описание повреждения/работы
    actual_price = Column(Float, nullable=False)  # фактическая цена
    additional_works_json = Column(Text)  # JSON с дополнительными работами
    total_amount = Column(Float, nullable=False)  # общая сумма заказа
    master_comment = Column(Text)
    performed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    appointment = relationship("Appointment", back_populates="completed_work")
    client = relationship("Client", back_populates="completed_works")
    car = relationship("Car", back_populates="completed_works")
    service = relationship("Service", back_populates="completed_works")