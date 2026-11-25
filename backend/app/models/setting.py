from sqlalchemy import Column, Integer, String, Text
from .base import Base


class Setting(Base):
    """Произвольная настройка сервиса (key-value)."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, nullable=False, index=True)
    value = Column(Text)
