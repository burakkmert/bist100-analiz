"""Güven skoru -> geçmiş isabet oranı eşlemesi + zamana göre doğrulama.

Sorun (bkz. confidence_calibration.py): motorun ham güven puanı isabeti ayırt etmiyor (hisse) ya da ters
çalışıyor (fon 1g, fon flat). Çözüm iki parçalı:

  1) Eşleme: (tür, ufuk, yön) başına ham puan kovaları -> geçmişte gerçekleşen isabet oranı.
     Kova oranları sıralı (puan arttıkça isabet azalmasın) hâle getirilir (izotonik, PAV).
     İsabet oranı kıyas oranını (rastgele isabet) anlamlı biçimde aşmıyorsa o anahtarda güven
     GÖSTERİLMEZ ("bu varlık türünde sinyalin ayırt edici gücü yok").
  2) Tavan: flat kararında güven, eşlemeden çıkan en yüksek isabet oranıyla sınırlanır
     (flat varsayılan sonuçtur; "yüzde 96 güvenli" demek yanıltıcıdır).

Doğrulama: tahmin günleri zamana göre ikiye bölünür (ortadaki 30 gün boşluk bırakılır, örtüşen
hedefler sızmasın). İlk yarıda eşleme kurulur, ikinci yarıda ölçülür:
  ECE_ham    : puanı olasılık gibi okursak (puan/100) ortalama kalibrasyon hatası
  ECE_eşleme : gösterilecek isabet oranının ortalama kalibrasyon hatası
Sonunda eşleme TÜM veriyle yeniden kurulup JSON olarak yazılır (Kişi 2'nin motoru bunu okur).

Kullanım:
    python -m backtest.confidence_mapping --raw backtest/reports/raw_2026-10-12_u500.parquet --every 2
    python -m backtest.confidence_mapping --raw ... --replay backtest/reports/confidence_replay_<ad>.parquet
Çıktı: ekrana tablolar + backtest/reports/confidence_mapping_<ad>.json (+ backtest/summary/ kopyası)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.confidence_calibration import BUCKET_LABELS, BUCKETS, load_ohlc_frames, replay

REPORTS = Path(__file__).resolve().parent / "reports"
SUMMARY = Path(__file__).resolve().parent / "summary"
MIN_N = 30            # kovada en az örnek
MIN_KEY_N = 300       # anahtarın (tür, ufuk, yön) toplamında en az örnek; azıyla tesadüfi "bilgi verici" çıkar
MIN_GAIN = 0.05       # eşlenen isabet oranı aralığı (en yüksek - en düşük) en az bu kadar olmalı
MIN_EDGE = 0.02       # en yüksek eşlenen oran kıyasın en az bu kadar üstünde olmalı
MIN_SPEARMAN = 0.05
EMBARGO_DAYS = 30


# ---------------------------------------------------------------- yardımcılar

def bucket_of(score: float) -> str:
    return str(pd.cut([score], bins=BUCKETS, labels=BUCKET_LABELS, right=False)[0])


def key_of(asset_type: str, horizon: int, direction: str) -> str:
    return f"{asset_type}|{int(horizon)}|{direction}"


def pav(values: list[float], weights: list[float]) -> list[float]:
    """Azalmayan (izotonik) uyum: komşu kovalar sıralamayı bozuyorsa ağırlıklı ortalamayla birleştirilir."""
    blocks: list[list[float]] = []   # [değer, ağırlık, eleman sayısı]
    for v, w in zip(values, weights):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, n2 = blocks.pop()
            v1, w1, n1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    out: list[float] = []
    for v, _, n in blocks:
        out.extend([v] * n)
    return out


def add_bucket(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(bucket=pd.cut(df["confidence"], bins=BUCKETS, labels=BUCKET_LABELS, right=False).astype(str))


def base_rates(df: pd.DataFrame) -> dict[str, float]:
    """Anahtar başına kıyas oranı: güvene ve yöne bakmadan (tür, ufuk) içindeki koşulsuz oran."""
    out = {}
    for (t, h), g in df.groupby(["type", "horizon"]):
        out[key_of(t, h, "flat")] = float(g["inside"].mean())
        out[key_of(t, h, "up")] = float(g["up_move"].mean())
        out[key_of(t, h, "down")] = 1 - float(g["up_move"].mean())
    return out


# ---------------------------------------------------------------- eşleme kurma

def fit_mapping(df: pd.DataFrame, min_n: int = MIN_N) -> dict:
    """Anahtar -> {informative, base_rate, n, fitted: {kova: oran}, suggested_cap, reason}."""
    d = add_bucket(df)
    base = base_rates(d)
    keys: dict[str, dict] = {}
    for (t, h, dirn), g in d.groupby(["type", "horizon", "direction"]):
        k = key_of(t, h, dirn)
        tab = (g.groupby("bucket").agg(n=("hit", "size"), hit=("hit", "mean"), conf=("confidence", "mean"))
               .reindex(BUCKET_LABELS).dropna())
        tab = tab[tab["n"] >= min_n]
        entry = {"informative": False, "base_rate": round(base[k], 4), "n": int(len(g)), "fitted": {},
                 "suggested_cap": None, "reason": "yetersiz örnek"}
        if len(g) < MIN_KEY_N:
            keys[k] = entry          # yetersiz örnek: güven gösterilmez
            continue
        if len(tab) >= 2:
            fitted = pav(tab["hit"].tolist(), tab["n"].tolist())
            entry["fitted"] = {b: round(float(v), 4) for b, v in zip(tab.index, fitted)}
            spearman = g["confidence"].corr(g["hit"], method="spearman") if g["hit"].nunique() > 1 else 0.0
            spearman = 0.0 if pd.isna(spearman) else float(spearman)
            gain = max(fitted) - min(fitted)
            edge = max(fitted) - base[k]
            entry["spearman"] = round(spearman, 3)
            if gain >= MIN_GAIN and edge >= MIN_EDGE and spearman >= MIN_SPEARMAN:
                entry["informative"], entry["reason"] = True, "güven isabeti ayırt ediyor"
            else:
                entry["reason"] = (f"güven isabeti ayırt etmiyor (en yüksek eşlenen oran {max(fitted):.2f}, "
                                   f"kıyas {base[k]:.2f}, Spearman {spearman:.2f})")
            if dirn == "flat":
                entry["suggested_cap"] = int(round(100 * max(fitted)))
        keys[k] = entry
    return {"version": 1, "buckets": BUCKET_LABELS, "keys": keys,
            "rules": {"min_n": min_n, "min_key_n": MIN_KEY_N, "min_gain": MIN_GAIN, "min_edge": MIN_EDGE, "min_spearman": MIN_SPEARMAN}}


# ---------------------------------------------------------------- kullanım (Kişi 2'nin motoru bunu çağırabilir)

def rate_for(fitted: dict[str, float], bucket: str) -> float:
    """Kovanın eşlenen oranı; kovada yeterli örnek yoksa en yakın kovanın değeri."""
    if bucket in fitted:
        return fitted[bucket]
    order = {lab: i for i, lab in enumerate(BUCKET_LABELS)}
    return fitted[min(fitted, key=lambda x: abs(order[x] - order[bucket]))]


def display_confidence(mapping: dict, asset_type: str, horizon: int, direction: str, score: float) -> dict:
    """Ham puandan kullanıcıya gösterilecek ifade. Tavsiye dili yok: yalnızca geçmiş istatistiği."""
    m = mapping["keys"].get(key_of(asset_type, horizon, direction))
    if m is None or not m["fitted"]:
        return {"shown": False, "reason": "yetersiz geçmiş veri"}
    if not m["informative"]:
        return {"shown": False, "reason": "ayırt edici güç yok",
                "message": "Bu varlık türünde sinyalin geçmiş isabeti rastgele isabetten ayırt edilemiyor."}
    rate = rate_for(m["fitted"], bucket_of(score))
    return {"shown": True, "hit_rate": rate, "base_rate": m["base_rate"],
            "message": (f"Geçmişte benzer sinyallerin %{round(rate * 100)}'i gerçekleşti "
                        f"(kıyas: %{round(m['base_rate'] * 100)}).")}


def capped_confidence(mapping: dict, asset_type: str, horizon: int, direction: str, score: int) -> int:
    """Hızlı çözüm: flat kararında ham puanı eşlemeden çıkan tavanla sınırlar."""
    m = mapping["keys"].get(key_of(asset_type, horizon, direction))
    cap = m.get("suggested_cap") if m else None
    return min(int(score), cap) if (direction == "flat" and cap is not None) else int(score)


# ---------------------------------------------------------------- doğrulama

def time_split(df: pd.DataFrame, embargo_days: int = EMBARGO_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tahmin günlerine göre ilk yarı / ikinci yarı; arada `embargo_days` boşluk (hedef örtüşmesi sızmasın)."""
    o = pd.to_datetime(df["origin"])
    cut = o.sort_values().iloc[len(o) // 2]
    return df[o <= cut], df[o > cut + pd.Timedelta(days=embargo_days)]


def ece(pred: pd.Series, hit: pd.Series, bucket: pd.Series) -> float:
    """Kovalara göre ağırlıklı ortalama |tahmin - gerçekleşen isabet|."""
    t = pd.DataFrame({"p": pred, "h": hit, "b": bucket}).groupby("b").agg(p=("p", "mean"), h=("h", "mean"), n=("h", "size"))
    return float((t["n"] / t["n"].sum() * (t["p"] - t["h"]).abs()).sum())


def evaluate(mapping: dict, test: pd.DataFrame) -> pd.DataFrame:
    """Test yarısında anahtar başına: ham puan ECE'si ve (gösterilecekse) eşleme ECE'si."""
    t = add_bucket(test)
    rows = []
    for (typ, h, dirn), g in t.groupby(["type", "horizon", "direction"]):
        if len(g) < MIN_N:
            continue
        m = mapping["keys"].get(key_of(typ, h, dirn))
        raw_ece = ece(g["confidence"] / 100, g["hit"], g["bucket"])
        mapped = None
        if m and m["informative"]:
            pred = g["bucket"].map(lambda b: rate_for(m["fitted"], b))
            mapped = ece(pred, g["hit"], g["bucket"])
        rows.append({"type": typ, "horizon": int(h), "direction": dirn, "n_test": len(g),
                     "informative": bool(m and m["informative"]), "ece_raw": round(raw_ece, 3),
                     "ece_mapped": None if mapped is None else round(mapped, 3)})
    return pd.DataFrame(rows)


def summarize(ev: pd.DataFrame) -> pd.DataFrame:
    """Tür bazında: satırların kaçında güven gösterilir; gösterilenlerde ham vs eşleme hatası."""
    rows = []
    for typ, g in ev.groupby("type"):
        shown = g[g["informative"]]
        rows.append({"type": typ, "n_test": int(g["n_test"].sum()),
                     "guven_gosterilen_pay": round(shown["n_test"].sum() / g["n_test"].sum(), 3),
                     "ece_ham_tum": round(float((g["ece_raw"] * g["n_test"]).sum() / g["n_test"].sum()), 3),
                     "ece_ham_gosterilen": round(float((shown["ece_raw"] * shown["n_test"]).sum() / shown["n_test"].sum()), 3) if len(shown) else None,
                     "ece_esleme_gosterilen": round(float((shown["ece_mapped"] * shown["n_test"]).sum() / shown["n_test"].sum()), 3) if len(shown) else None})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Güven skoru -> isabet oranı eşlemesi ve doğrulama")
    p.add_argument("--raw", required=True)
    p.add_argument("--every", type=int, default=2)
    p.add_argument("--replay", help="önceden kaydedilmiş motor yeniden oynatma sonucu (parquet)")
    a = p.parse_args(argv)

    stem = Path(a.raw).stem
    REPORTS.mkdir(exist_ok=True)
    replay_path = Path(a.replay) if a.replay else REPORTS / f"confidence_replay_{stem}.parquet"
    if replay_path.exists():
        df = pd.read_parquet(replay_path)
        print(f"yeniden oynatma önbellekten okundu: {replay_path.name} ({len(df)} satır)")
    else:
        raw = pd.read_parquet(a.raw)
        if "type" in raw:
            types = dict(zip(raw["code"], raw["type"]))
        else:
            from ml.batch_forecast import load_universe_codes
            uni = load_universe_codes()
            types = dict(zip(uni["code"], uni["type"]))
        frames = load_ohlc_frames(sorted(raw["code"].unique()), types)
        print(f"{len(frames)} varlık yüklendi; motor yeniden oynatılıyor (~30 dk, bir kez; sonuç kaydedilir)...")
        df = replay(raw, frames, types, every=a.every)
        df.assign(origin=pd.to_datetime(df["origin"])).to_parquet(replay_path)
        print(f"kaydedildi: {replay_path}")

    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 200)
    train, test = time_split(df)
    print(f"\neşleme: {len(train)} satır (ilk yarı) | test: {len(test)} satır (ikinci yarı, {EMBARGO_DAYS} gün boşluklu)")
    ev = evaluate(fit_mapping(train), test)
    print("\n== Test yarısı: anahtar başına kalibrasyon hatası (ECE; düşük iyi)")
    print(ev.to_string(index=False))
    print("\n== Tür bazında özet")
    print(summarize(ev).to_string(index=False))

    final = fit_mapping(df)
    print("\n== Nihai eşleme (tüm veri): anahtar, bilgi verici mi, kıyas, flat tavanı")
    for k, v in final["keys"].items():
        print(f"{k:16s} informative={str(v['informative']):5s} base={v['base_rate']:.3f} cap={v['suggested_cap']}  {v['reason']}")
    out = REPORTS / f"confidence_mapping_{stem}.json"
    out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY.mkdir(exist_ok=True)
    (SUMMARY / "confidence_mapping.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    ev.to_csv(SUMMARY / "confidence_mapping_validation.csv", index=False)
    print(f"\nKaydedildi: {out}\n           {SUMMARY / 'confidence_mapping.json'}\n           {SUMMARY / 'confidence_mapping_validation.csv'}")


if __name__ == "__main__":
    main()
