"""Alembic ortamı. Yeni göç oluşturmak için (backend/ klasöründe):

    alembic revision --autogenerate -m "aciklama"
    alembic upgrade head

Not: Şema değişikliği shared/db_schema.sql'i de değiştirir → PR + 3 onay.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Testler -x url=... ile farklı bir DB verebilir
url = context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url
# ConfigParser "%" işaretini değişken sanır; şifredeki %XX kodlamaları için kaçış gerekir
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
