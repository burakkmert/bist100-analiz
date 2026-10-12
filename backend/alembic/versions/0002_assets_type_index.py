"""sozlesme v0.2: assets.type 'index' degerini alabilir (XU100)

Revision ID: 0002_assets_type_index
Revises: 0001_initial
Create Date: 2026-10-12

shared/db_schema.sql v0.2 ile uyum: rejim tespiti için BIST100 endeksi (XU100)
prices tablosuna yazılabilsin diye assets.type kontrolüne 'index' eklendi.
Postgres sütun içi CHECK'e otomatik "assets_type_check" adını verir.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_assets_type_index"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_type_check")
    op.execute(
        "ALTER TABLE assets ADD CONSTRAINT assets_type_check "
        "CHECK (type IN ('stock', 'fund', 'index'))"
    )


def downgrade() -> None:
    # Geri almadan önce endeks satırları silinmeli, yoksa kısıt eklenemez
    op.execute("ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_type_check")
    op.execute("ALTER TABLE assets ADD CONSTRAINT assets_type_check CHECK (type IN ('stock', 'fund'))")
