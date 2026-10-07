-- =====================================================================
-- Fon ve Hisse Takip — ortak veritabanı şeması (TASLAK v0.1)
-- PostgreSQL 16. Kaynak: Proje Planı v3, Kısım B §5.1
--
-- KURAL: Bu dosya ortak sözleşmedir. Değişiklik yalnızca PR + 3 onay ile.
-- Her tablonun TEK bir yazanı vardır (yorumlarda belirtildi).
-- Alembic göçleri (Kişi 2) bu dosyayla birebir uyumlu olmalıdır.
-- =====================================================================

-- ---------- Kişi 1 yazar ----------

CREATE TABLE IF NOT EXISTS assets (
    code            VARCHAR(16)  PRIMARY KEY,           -- THYAO, IPB
    name            TEXT         NOT NULL,
    type            VARCHAR(8)   NOT NULL CHECK (type IN ('stock', 'fund')),
    sector          TEXT,                               -- hisse: sektör, fon: fon türü
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    min_history_ok  BOOLEAN      NOT NULL DEFAULT FALSE, -- >=120 iş günü geçmiş var mı
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prices (
    code       VARCHAR(16)  NOT NULL REFERENCES assets(code),
    date       DATE         NOT NULL,
    open       NUMERIC(18,6),
    high       NUMERIC(18,6),
    low        NUMERIC(18,6),
    close      NUMERIC(18,6) NOT NULL,                  -- fonlarda yalnızca bu dolu
    adj_close  NUMERIC(18,6),
    volume     BIGINT,
    PRIMARY KEY (code, date)                            -- upsert anahtarı
);

CREATE TABLE IF NOT EXISTS forecasts (
    code      VARCHAR(16) NOT NULL REFERENCES assets(code),
    run_date  DATE        NOT NULL,
    model     VARCHAR(32) NOT NULL,                     -- timesfm, chronos, naive, ma, arima
    horizon   SMALLINT    NOT NULL CHECK (horizon IN (1, 5, 20, 30, 120)),
    p10       NUMERIC(18,6),
    p50       NUMERIC(18,6),                            -- 120 günde NULL (nokta tahmin yok)
    p90       NUMERIC(18,6),
    PRIMARY KEY (code, run_date, model, horizon)
);

CREATE TABLE IF NOT EXISTS scenarios (
    code      VARCHAR(16) NOT NULL REFERENCES assets(code),
    run_date  DATE        NOT NULL,
    horizon   SMALLINT    NOT NULL CHECK (horizon IN (30, 120)),
    bear      NUMERIC(18,6),
    base      NUMERIC(18,6),
    bull      NUMERIC(18,6),
    PRIMARY KEY (code, run_date, horizon)
);

CREATE TABLE IF NOT EXISTS model_errors (
    code         VARCHAR(16) NOT NULL REFERENCES assets(code),
    model        VARCHAR(32) NOT NULL,
    horizon      SMALLINT    NOT NULL,
    window_days  SMALLINT    NOT NULL,                  -- ör. 60
    mae          DOUBLE PRECISION,
    mape         DOUBLE PRECISION,
    dir_acc      DOUBLE PRECISION,                      -- 0..1
    as_of        DATE        NOT NULL,
    PRIMARY KEY (code, model, horizon, window_days, as_of)
);

-- ---------- Kişi 2 yazar ----------

CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY,                       -- Supabase auth.users id
    email       TEXT UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    risk_profile  VARCHAR(12) NOT NULL DEFAULT 'balanced'
                  CHECK (risk_profile IN ('cautious', 'balanced', 'aggressive')),
    budget        NUMERIC(18,2),
    quiet_hours   JSONB,                                -- {"start":"22:30","end":"08:00"}
    daily_push_limit SMALLINT DEFAULT 5
);

CREATE TABLE IF NOT EXISTS analysis (
    code        VARCHAR(16) NOT NULL REFERENCES assets(code),
    run_date    DATE        NOT NULL,
    horizon     SMALLINT    NOT NULL,
    direction   VARCHAR(4)  CHECK (direction IN ('up', 'down', 'flat')),
    confidence  SMALLINT    CHECK (confidence BETWEEN 0 AND 100),
    risk        VARCHAR(8)  CHECK (risk IN ('low', 'medium', 'high')),
    regime      VARCHAR(16),
    weights     JSONB,                                  -- ilk günden doldurulur (Aşama 2)
    indicators  JSONB,                                  -- ilk günden doldurulur (Aşama 2)
    low         NUMERIC(18,6),
    mid         NUMERIC(18,6),
    high        NUMERIC(18,6),
    PRIMARY KEY (code, run_date, horizon)
);

CREATE TABLE IF NOT EXISTS signals (
    id             BIGSERIAL PRIMARY KEY,
    user_id        UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code           VARCHAR(16) NOT NULL REFERENCES assets(code),
    side           VARCHAR(4)  NOT NULL CHECK (side IN ('buy', 'sell')),
    horizon        SMALLINT    NOT NULL CHECK (horizon IN (1, 5, 20, 30)),  -- 120 sinyal üretmez
    confidence     SMALLINT,
    suggested_qty  NUMERIC(18,4),
    stop_level     NUMERIC(18,6),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome        JSONB                                -- ufuk dolunca: {"realized":.., "hit":true}
);

CREATE TABLE IF NOT EXISTS positions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code        VARCHAR(16) NOT NULL REFERENCES assets(code),
    qty         NUMERIC(18,4) NOT NULL,
    buy_price   NUMERIC(18,6) NOT NULL,
    buy_date    DATE        NOT NULL,
    sell_price  NUMERIC(18,6),
    sell_date   DATE,
    signal_id   BIGINT REFERENCES signals(id)
);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id  UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code     VARCHAR(16) NOT NULL REFERENCES assets(code),
    PRIMARY KEY (user_id, code)
);

CREATE TABLE IF NOT EXISTS push_tokens (
    user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token     TEXT NOT NULL,
    platform  VARCHAR(8) CHECK (platform IN ('ios', 'android')),
    PRIMARY KEY (user_id, token)
);

CREATE TABLE IF NOT EXISTS job_runs (
    id          BIGSERIAL PRIMARY KEY,
    job_name    VARCHAR(64) NOT NULL,                   -- collect, forecast, engine, explain, push
    run_date    DATE        NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status      VARCHAR(12) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'success', 'failed')),
    error       TEXT,
    stats       JSONB                                   -- ör. veri kalite raporu
);

-- ---------- Kişi 3 yazar ----------

CREATE TABLE IF NOT EXISTS ai_explanations (
    code      VARCHAR(16) NOT NULL REFERENCES assets(code),
    run_date  DATE        NOT NULL,
    horizon   SMALLINT    NOT NULL,
    text      TEXT        NOT NULL,
    PRIMARY KEY (code, run_date, horizon)
);

-- ---------- İndeksler ----------
CREATE INDEX IF NOT EXISTS idx_prices_date      ON prices (date);
CREATE INDEX IF NOT EXISTS idx_forecasts_run    ON forecasts (run_date);
CREATE INDEX IF NOT EXISTS idx_signals_user     ON signals (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_lookup  ON job_runs (job_name, run_date);
