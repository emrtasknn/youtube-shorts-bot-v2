from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.ports.asset_downloader import AssetDownloader
from app.application.ports.stock_media import StockMediaGateway, StockMediaStrategy
from app.application.ports.text_generation import TextGenerationGateway, TextGenerationRequest
from app.application.ports.tts import TTSGateway, TTSRequest
from app.application.ports.video_engine import VideoEngine, VideoRenderRequest, VideoSceneInput
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.stock_media_strategy import StockMediaStrategyRouter
from app.application.use_cases.search_stock_media import SearchStockMedia
from app.domain.enums import (
    ApprovalStatus,
    AssetStatus,
    AssetType,
    ContentCategory,
    ContentStatus,
    RunStatus,
    RunType,
    SceneStatus,
    ScriptStatus,
)
from app.infrastructure.database.models import (
    ApprovalModel,
    AssetModel,
    ContentModel,
    RunModel,
    SceneModel,
    ScriptModel,
)


@dataclass(frozen=True, slots=True)
class CustomShortRequest:
    topic: str
    run_key: str
    language: str = "tr"
    requested_by: str = "manual"
    output_path: Path = Path("storage/renders/custom.mp4")


@dataclass(frozen=True, slots=True)
class CustomShortResult:
    run_id: UUID
    content_id: UUID
    script_id: UUID
    output_path: Path
    duration_seconds: float
    status: RunStatus


class GenerateCustomShort:
    def __init__(
        self,
        *,
        session: Session,
        text: TextGenerationGateway,
        stock_media: StockMediaGateway,
        tts: TTSGateway,
        video_engine: VideoEngine,
        downloader: AssetDownloader,
        storage_root: Path = Path("storage/runs"),
    ) -> None:
        self._session = session
        self._text = text
        self._stock_media = stock_media
        self._tts = tts
        self._video_engine = video_engine
        self._downloader = downloader
        self._storage_root = storage_root

    async def execute(self, request: CustomShortRequest) -> CustomShortResult:
        topic = request.topic.strip()
        if not topic:
            raise ValueError("Custom topic must not be empty")
        if self._session.query(RunModel).filter_by(run_key=request.run_key).first() is not None:
            raise ValueError(f"Run key already exists: {request.run_key}")

        content = ContentModel(
            content_key=f"custom:{request.run_key}",
            language=request.language,
            category=ContentCategory.CUSTOM,
            topic=topic,
            status=ContentStatus.ACTIVE,
        )
        self._session.add(content)
        self._session.flush()

        run = RunModel(
            run_key=request.run_key,
            content_id=content.id,
            run_type=RunType.CUSTOM,
            status=RunStatus.CREATED,
            requested_by=request.requested_by,
            language=request.language,
            strategy="custom_single_vertical_slice",
        )
        self._session.add(run)
        self._session.flush()

        try:
            run.status = RunStatus.QUEUED
            run.status = RunStatus.RUNNING
            run.status = RunStatus.RESEARCHING
            run.status = RunStatus.TOPIC_VALIDATION
            run.status = RunStatus.SCRIPTING
            script_data = await self._generate_script(run.id, topic, request.language)
            script = ScriptModel(
                content_id=content.id,
                version=1,
                language=request.language,
                hook=str(script_data["hook"]),
                body=str(script_data["body"]),
                cta=str(script_data.get("cta") or "") or None,
                duration_target=Decimal(str(script_data["duration_target"])),
                word_count=len(str(script_data["body"]).split()),
                status=ScriptStatus.DRAFT,
            )
            self._session.add(script)
            self._session.flush()

            run.status = RunStatus.STORYBOARDING
            scenes = self._create_scenes(script.id, script_data["scenes"])
            run.status = RunStatus.ASSET_PLANNING
            scene_inputs: list[VideoSceneInput] = []
            for scene in scenes:
                asset_path, asset = await self._select_asset(run.id, scene)
                scene.status = SceneStatus.READY
                self._session.add(asset)
                self._session.flush()
                scene_inputs.append(VideoSceneInput(
                    path=asset_path,
                    duration_seconds=float(scene.duration or 5),
                    is_image=True,
                ))

            run.status = RunStatus.ASSET_GENERATION
            tts_result = await self._tts.synthesize(TTSRequest(
                run_id=str(run.id),
                request_id=f"{run.id}:voiceover",
                text=f"{script.hook} {script.body} {script.cta or ''}".strip(),
            ))
            run_dir = self._storage_root / str(run.id)
            audio_path = run_dir / f"voiceover.{tts_result.format}"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(tts_result.audio_bytes)

            run.status = RunStatus.TTS
            run.status = RunStatus.AUDIO_MIX
            output_path = request.output_path
            if not output_path.is_absolute():
                output_path = run_dir / output_path.name
            render = await self._video_engine.render(VideoRenderRequest(
                scenes=tuple(scene_inputs),
                output_path=output_path,
                voiceover_path=audio_path,
            ))
            run.status = RunStatus.RENDERING
            run.status = RunStatus.QC
            self._validate_output(render.output_path, render.duration_seconds)
            run.status = RunStatus.READY_FOR_APPROVAL
            self._session.add(ApprovalModel(run_id=run.id, status=ApprovalStatus.PENDING))
            self._session.commit()

            return CustomShortResult(
                run_id=run.id,
                content_id=content.id,
                script_id=script.id,
                output_path=render.output_path,
                duration_seconds=render.duration_seconds,
                status=run.status,
            )
        except Exception:
            run.status = RunStatus.FAILED_RETRYABLE
            self._session.commit()
            raise
