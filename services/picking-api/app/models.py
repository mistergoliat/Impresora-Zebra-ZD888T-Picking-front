"""SQLAlchemy models for the picking API service."""

from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Stock(Base):
    """Represents the stock available for picking operations."""

    __tablename__ = "stock"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_code = Column(String(64), nullable=False)
    lot = Column(String(64))
    serial = Column(String(64))
    location = Column(String(64), nullable=False)
    quantity = Column(Numeric(12, 2), nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index(
            "stock_item_lot_serial_location_uq",
            item_code,
            func.coalesce(lot, ""),
            func.coalesce(serial, ""),
            location,
            unique=True,
        ),
    )
