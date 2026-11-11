from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Distance = Literal["5k", "10k", "semi", "marathon"]


class SetIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    exercise: str = Field(min_length=1, max_length=100)
    reps: int = Field(ge=1, le=1000)
    weight_kg: float = Field(ge=0, le=1000)


class SetOut(SetIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class SessionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    performed_on: date
    notes: str | None = Field(default=None, max_length=500)
    sets: list[SetIn] = Field(min_length=1, max_length=100)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    performed_on: date
    notes: str | None
    sets: list[SetOut]


class ExerciseStats(BaseModel):
    exercise: str
    best_weight_kg: float
    total_sets: int
    last_performed_on: date


class RecordIn(BaseModel):
    distance: Distance
    duration_seconds: int = Field(ge=1, le=24 * 3600)
    performed_on: date


class RecordOut(RecordIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
