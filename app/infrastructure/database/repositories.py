from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database.models import ContentModel, RunModel


class SqlAlchemyContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, content_id: UUID) -> ContentModel | None:
        return self.session.get(ContentModel, content_id)

    def add(self, content: ContentModel) -> ContentModel:
        self.session.add(content)
        self.session.flush()
        return content


class SqlAlchemyRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: UUID) -> RunModel | None:
        return self.session.get(RunModel, run_id)

    def get_by_key(self, run_key: str) -> RunModel | None:
        return self.session.scalar(select(RunModel).where(RunModel.run_key == run_key))

    def add(self, run: RunModel) -> RunModel:
        self.session.add(run)
        self.session.flush()
        return run
