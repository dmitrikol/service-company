from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    accounts = relationship("PlatformAccount", back_populates="user")
    client = relationship("Client", back_populates="user", uselist=False)


class PlatformAccount(Base):
    __tablename__ = "platform_accounts"
    # ID в разных платформах — независимые числовые пространства и могут
    # случайно совпасть, поэтому уникальность — по паре (platform, external_id),
    # а не по одному external_id (см. миграцию e1a2b3c4d5f6).
    __table_args__ = (
        UniqueConstraint("platform", "external_id",
                          name="uq_platform_accounts_platform_external_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String(10), nullable=False)  # название платформы (сейчас 'vk')
    external_id = Column(String, nullable=False)  # ID пользователя в платформе
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String)
    phone = Column(String)  # может быть зашифрован
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="accounts")