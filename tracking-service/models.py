from datetime import date, datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# user_id n'est pas une clé étrangère : les comptes appartiennent à auth-service,
# ce service ne connaît que l'identifiant présent dans le JWT.


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    performed_on: Mapped[date]
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sets: Mapped[list["WorkoutSet"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="WorkoutSet.position",
    )


class WorkoutSet(Base):
    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    exercise: Mapped[str] = mapped_column(String(100))
    reps: Mapped[int]
    weight_kg: Mapped[float]
    session: Mapped[WorkoutSession] = relationship(back_populates="sets")


class RunningRecord(Base):
    __tablename__ = "running_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    distance: Mapped[str] = mapped_column(String(20))
    duration_seconds: Mapped[int]
    performed_on: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
