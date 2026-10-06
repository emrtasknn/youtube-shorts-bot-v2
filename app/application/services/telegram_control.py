from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.ports.publisher import PublicationRequest, Publisher
from app.application.services.performance_memory import PerformanceMemoryService
from app.application.use_cases.generate_custom_short import (
    CustomShortRequest,
    GenerateCustomShort,
)
from app.domain.enums import (
    ApprovalStatus,
    PublicationPlatform,
    PublicationStatus,
    RunStatus,
)
from app.domain.state_machine import (
    InvalidTransition,
    transition_approval,
    transition_publication,
    transition_run,
)
from app.infrastructure.database.models import (
    ApprovalModel,
    ContentModel,
    PublicationAttemptModel,
    PublicationModel,
    RunModel,
)
from app.infrastructure.telegram.bot import TelegramBot


class TelegramControlPlane:
    def __init__(
        self,
        session: Session,
        bot: TelegramBot,
        *,
        publisher: Publisher | None = None,
        generator: GenerateCustomShort | None = None,
    ) -> None:
        self._session = session
        self._bot = bot
        self._publisher = publisher
        self._generator = generator

    def _approval(self, run_id: UUID) -> ApprovalModel:
        approval = self._session.scalar(
            select(ApprovalModel)
            .where(ApprovalModel.run_id == run_id)
            .order_by(ApprovalModel.requested_at.desc())
        )
        if approval is None:
            raise ValueError(f"Approval not found for run {run_id}")
        return approval

    def _run(self, run_id: UUID) -> RunModel:
        run = self._session.get(RunModel, run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        return run

    async def _video_path(self, run: RunModel) -> Path:
        run_dir = Path("storage/runs") / str(run.id)
        candidates = sorted(run_dir.glob("*.mp4"))
        if candidates:
            return candidates[0]

        approval = self._approval(run.id)
        file_id = str((approval.approval_metadata or {}).get("telegram_file_id") or "")
        if not file_id:
            raise FileNotFoundError(f"No generated MP4 or Telegram file_id found for run {run.id}")
        return await self._bot.download_file(file_id, run_dir / "telegram-recovered.mp4")

    def _keyboard(self, run_id: UUID, *, approved: bool = False) -> dict[str, object]:
        if approved:
            rows = [
                [{"text": "Publish", "callback_data": f"publish:{run_id}"}],
                [{"text": "Reject", "callback_data": f"reject:{run_id}"}],
            ]
        else:
            rows = [
                [
                    {"text": "Approve", "callback_data": f"approve:{run_id}"},
                    {"text": "Reject", "callback_data": f"reject:{run_id}"},
                ],
                [{"text": "Regenerate", "callback_data": f"regenerate:{run_id}"}],
            ]
        return {"inline_keyboard": rows}

    async def send_review(self, chat_id: int, run_id: UUID) -> None:
        run = self._run(run_id)
        if run.status != RunStatus.READY_FOR_APPROVAL:
            raise InvalidTransition(f"Run {run_id} is not ready for approval: {run.status}")

        content = self._session.get(ContentModel, run.content_id)
        video = await self._video_path(run)
        caption = f"Review\n\n{content.topic if content else 'YouTube Short'}\nRun: {run.id}"
        message = await self._bot.send_video(chat_id, video, caption, self._keyboard(run.id))
        video_payload = message.get("video") or {}
        file_id = str(video_payload.get("file_id") or "")
        approval = self._approval(run.id)
        approval.approval_metadata = {
            **(approval.approval_metadata or {}),
            "telegram_file_id": file_id,
        }
        self._session.commit()

    async def approve(self, run_id: UUID, user: str) -> str:
        run = self._run(run_id)
        approval = self._approval(run_id)
        if approval.status == ApprovalStatus.APPROVED and run.status == RunStatus.APPROVED:
            return "Already approved."
        if approval.status != ApprovalStatus.PENDING:
            return f"Approval already resolved: {approval.status}"

        approval.status = transition_approval(approval.status, ApprovalStatus.APPROVED)
        approval.responded_at = datetime.now(UTC)
        approval.responded_by = user
        run.status = transition_run(run.status, RunStatus.APPROVED)
        self._session.commit()
        return "Approved. Publish is now available."

    async def reject(self, run_id: UUID, user: str) -> str:
        run = self._run(run_id)
        approval = self._approval(run_id)
        if approval.status == ApprovalStatus.REJECTED:
            return "Already rejected."
        if approval.status != ApprovalStatus.PENDING:
            return f"Approval already resolved: {approval.status}"

        approval.status = transition_approval(approval.status, ApprovalStatus.REJECTED)
        approval.responded_at = datetime.now(UTC)
        approval.responded_by = user
        run.status = transition_run(run.status, RunStatus.CANCELLED)
        self._session.commit()
        return "Rejected."

    async def regenerate(self, run_id: UUID, user: str) -> str:
        run = self._run(run_id)
        approval = self._approval(run_id)
        if approval.status != ApprovalStatus.PENDING:
            return f"Approval already resolved: {approval.status}"

        approval.status = transition_approval(approval.status, ApprovalStatus.REGENERATE)
        approval.responded_at = datetime.now(UTC)
        approval.responded_by = user
        run.status = transition_run(run.status, RunStatus.CANCELLED)
        content = self._session.get(ContentModel, run.content_id)
        topic = content.topic if content else ""
        self._session.commit()

        if not self._generator:
            raise RuntimeError("Generator is not configured")

        result = await self._generator.execute(
            CustomShortRequest(
                topic=topic,
                run_key=f"regen-{run.id}-{uuid4().hex[:8]}",
                language=run.language,
                requested_by=user,
            )
        )
        return f"Regenerated: {result.run_id}"

    async def publish(self, run_id: UUID, user: str) -> str:
        if not self._publisher:
            raise RuntimeError("YouTube publisher is not configured")

        run = self._run(run_id)
        approval = self._approval(run_id)
        if approval.status != ApprovalStatus.APPROVED or run.status != RunStatus.APPROVED:
            return "Approve the Short before publishing."

        publication = self._session.scalar(
            select(PublicationModel)
            .where(
                PublicationModel.run_id == run_id,
                PublicationModel.platform == PublicationPlatform.YOUTUBE,
            )
            .with_for_update()
        )
        if publication is not None and publication.status == PublicationStatus.PUBLISHED:
            return f"Already published: {publication.url}"
        if publication is not None and publication.status == PublicationStatus.UPLOADING:
            return "Publication is already uploading."

        if publication is None:
            publication = PublicationModel(
                run_id=run_id,
                platform=PublicationPlatform.YOUTUBE,
                status=PublicationStatus.PENDING,
            )
            self._session.add(publication)
            self._session.flush()

        if publication.status not in {
            PublicationStatus.PENDING,
            PublicationStatus.FAILED_RETRYABLE,
        }:
            return f"Publication is already in state: {publication.status}"

        if publication.status == PublicationStatus.FAILED_RETRYABLE:
            publication.status = transition_publication(
                publication.status, PublicationStatus.QUEUED
            )
        elif publication.status == PublicationStatus.PENDING:
            publication.status = transition_publication(
                publication.status, PublicationStatus.QUEUED
            )

        previous_attempt = self._session.scalar(
            select(PublicationAttemptModel)
            .where(PublicationAttemptModel.publication_id == publication.id)
            .order_by(PublicationAttemptModel.attempt_number.desc())
        )
        attempt_number = (previous_attempt.attempt_number if previous_attempt else 0) + 1
        attempt = PublicationAttemptModel(
            publication_id=publication.id,
            attempt_number=attempt_number,
            provider="youtube",
            status=PublicationStatus.UPLOADING,
            started_at=datetime.now(UTC),
            upload_session_url=previous_attempt.upload_session_url if previous_attempt else None,
            bytes_uploaded=previous_attempt.bytes_uploaded if previous_attempt else 0,
            total_bytes=previous_attempt.total_bytes if previous_attempt else None,
        )
        self._session.add(attempt)
        self._session.flush()

        run.status = transition_run(run.status, RunStatus.PUBLISHING)
        publication.status = transition_publication(
            publication.status, PublicationStatus.UPLOADING
        )
        self._session.commit()

        content = self._session.get(ContentModel, run.content_id)
        title = (content.topic if content else "YouTube Short").strip()[:100]
        description = f"{title}\n\n#shorts #tarih"

        def persist_upload_state(upload_url: str, bytes_uploaded: int, total_bytes: int) -> None:
            attempt.upload_session_url = upload_url
            attempt.bytes_uploaded = bytes_uploaded
            attempt.total_bytes = total_bytes
            self._session.commit()

        try:
            result = await self._publisher.publish(
                PublicationRequest(
                    run_id=str(run_id),
                    video_path=await self._video_path(run),
                    title=title,
                    description=description,
                    upload_session_url=attempt.upload_session_url,
                    upload_state_callback=persist_upload_state,
                )
            )
            attempt.status = PublicationStatus.PUBLISHED
            attempt.bytes_uploaded = attempt.total_bytes or attempt.bytes_uploaded
            attempt.completed_at = datetime.now(UTC)
            publication.platform_post_id = result.platform_post_id
            publication.url = result.url
            publication.title = title
            publication.description = description
            publication.status = transition_publication(
                publication.status, PublicationStatus.PUBLISHED
            )
            publication.published_at = datetime.now(UTC)
            run.status = transition_run(run.status, RunStatus.PUBLISHED)
            self._session.commit()

            # Capture immutable production features only after the external publication succeeds.
            # A snapshot failure must not turn a successful YouTube publication into a retryable publish.
            try:
                PerformanceMemoryService(self._session).capture_production_snapshot(publication.id)
                self._session.commit()
            except Exception:
                self._session.rollback()

            return f"Published: {result.url}"
        except Exception as exc:
            retryable = getattr(exc, "retryable", True)
            session_url = getattr(exc, "upload_session_url", None)
            bytes_uploaded = getattr(exc, "bytes_uploaded", attempt.bytes_uploaded)
            if session_url:
                attempt.upload_session_url = session_url
            attempt.bytes_uploaded = bytes_uploaded
            attempt.completed_at = datetime.now(UTC)
            if retryable:
                attempt.status = PublicationStatus.FAILED_RETRYABLE
                publication.status = transition_publication(
                    publication.status, PublicationStatus.FAILED_RETRYABLE
                )
                run.status = RunStatus.FAILED_RETRYABLE
            else:
                attempt.status = PublicationStatus.FAILED_PERMANENT
                publication.status = transition_publication(
                    publication.status, PublicationStatus.FAILED_PERMANENT
                )
                run.status = RunStatus.FAILED_PERMANENT
            self._session.commit()
            raise RuntimeError(f"Publish failed: {exc}") from exc
