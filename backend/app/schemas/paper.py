"""Sanal portföy (Aşama 2): alım yönlü model sinyallerine otomatik uyulsaydı ne olurdu?"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class PaperPosition(BaseModel):
    signal_id: int
    code: str
    horizon: int
    confidence: int | None
    opened_at: datetime
    qty: float = Field(description="Sinyaldeki önerilen adet; öneri yoksa 1")
    entry: float | None = Field(description="Sinyal günündeki kapanış")
    exit: float | None = Field(description="Ufuk dolunca gerçekleşen fiyat (kapalı pozisyon)")
    last_price: float | None = Field(description="Açık pozisyonda son kapanış")
    closed: bool
    closed_on: date | None
    pnl: float | None
    pnl_pct: float | None


class PaperSummary(BaseModel):
    positions: int
    open: int
    closed: int
    invested: float = Field(description="Toplam giriş tutarı (TL)")
    value: float = Field(description="Kapalılarda çıkış, açıklarda güncel değer toplamı (TL)")
    pnl: float
    pnl_pct: float | None
    hit_rate: float | None = Field(description="Kapanan pozisyonlarda kârlı olanların oranı")


class PaperPortfolio(BaseModel):
    summary: PaperSummary
    positions: list[PaperPosition]
    note: str = (
        "Sanal portföydür: gerçek işlem yapılmamıştır. Model sinyallerine otomatik uyulsaydı oluşacak "
        "sonucu gösterir; yatırım tavsiyesi değildir."
    )
