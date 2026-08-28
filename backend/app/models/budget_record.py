"""预算明细表（说明书 6.6 budget_records）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BudgetRecord(Base):
    __tablename__ = "budget_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("travel_plans.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # traffic/hotel/ticket/food/other
    item: Mapped[str] = mapped_column(String(256), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
