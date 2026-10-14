"""Türkiye saati. Türkiye 2016'dan beri kalıcı UTC+3 (yaz saati yok); sabit ofset kullanmak
Docker imajında tzdata bulunmasına bağımlılığı da ortadan kaldırır."""

from datetime import date, datetime, timedelta, timezone

TR = timezone(timedelta(hours=3), "TRT")


def now_tr() -> datetime:
    return datetime.now(TR)


def today_tr() -> date:
    return now_tr().date()
