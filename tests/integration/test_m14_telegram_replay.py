from __future__ import annotations

import os
from typing import cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.application.services.telegram_worker import TelegramWorker
from app.infrastructure.database.models import TelegramUpdateReceiptModel
from app.infrastructure.telegram.bot import TelegramBot


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for the M14 integration test")
    return value


def build_worker(session: Session) -> TelegramWorker:
    return TelegramWorker(
        session=session,
        bot=cast(TelegramBot, object()),
        control=cast(object, object()),
        admin_chat_id=1,
        admin_user_id=1,
    )


def test_telegram_update_claim_is_durable_and_idempotent() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            worker = build_worker(session)
            update_id = 14_000_001

            assert worker._claim_update(update_id) is True
            assert worker._claim_update(update_id) is False

            receipt = session.query(TelegramUpdateReceiptModel).filter_by(
                update_id=update_id
            ).one()
            assert receipt.update_id == update_id

            worker._release_update(update_id)
            assert session.query(TelegramUpdateReceiptModel).filter_by(
                update_id=update_id
            ).one_or_none() is None
    finally:
        engine.dispose()
