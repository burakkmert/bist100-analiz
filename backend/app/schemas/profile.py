from typing import Literal

from pydantic import BaseModel, Field

RiskProfile = Literal["cautious", "balanced", "aggressive"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class QuietHours(BaseModel):
    """Bildirim gönderilmeyecek saat aralığı, ör. 22:30–08:00 (gece yarısını geçebilir)."""

    start: str = Field(pattern=HHMM, examples=["22:30"])
    end: str = Field(pattern=HHMM, examples=["08:00"])


class ProfileOut(BaseModel):
    email: str
    risk_profile: RiskProfile
    budget: float | None = Field(description="TL; null = girilmemiş")
    quiet_hours: QuietHours | None
    daily_push_limit: int | None


class ProfileUpdate(BaseModel):
    """Yalnızca gönderilen alanlar güncellenir. Bir alanı silmek için null gönderin."""

    risk_profile: RiskProfile | None = None
    budget: float | None = Field(default=None, ge=0)
    quiet_hours: QuietHours | None = None
    daily_push_limit: int | None = Field(default=None, ge=0, le=50)
