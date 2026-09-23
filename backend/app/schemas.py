from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    latitude: float = Field(ge=24.8, le=25.4)
    longitude: float = Field(ge=121.3, le=122.1)


class RecommendationIn(BaseModel):
    rider_alias: str = Field(pattern=r"^demo_rider_(full|light|cold)$")
    location: LocationIn
    datetime: datetime

    @field_validator("datetime")
    @classmethod
    def needs_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime 必須包含時區偏移")
        return value


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool


class ErrorResponse(BaseModel):
    error: ErrorBody


class RideEstimateIn(BaseModel):
    request_id: str = Field(pattern=r"^rec_[a-f0-9]{16}$")
    place_key: str = Field(min_length=1, max_length=80)
    origin: LocationIn
    destination: LocationIn
    datetime: datetime

    @field_validator("datetime")
    @classmethod
    def ride_needs_offset(cls, value: datetime) -> datetime:
        return RecommendationIn.needs_offset(value)


class FeedbackIn(BaseModel):
    request_id: str = Field(pattern=r"^rec_[a-f0-9]{16}$")
    place_key: str = Field(min_length=1, max_length=80)
    action: Literal["impression", "restaurant_clicked", "explanation_opened", "ride_clicked"]
