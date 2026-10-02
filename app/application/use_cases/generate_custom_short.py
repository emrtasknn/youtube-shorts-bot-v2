from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.ports.asset_downloader import AssetDownloader
from app.application.ports.stock_media import StockMediaGateway, StockMediaStrategy
from app.application.ports.text_generation import TextGenerationGateway, TextGenerationRequest
from app.application.ports.tts import TTSGateway, TTSRequest
from app.application.ports.video_engine import VideoEngine, VideoRenderRequest, VideoSceneInput
from app.application.services.custom_short_support import parse_script, validate_output
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.stock_media_strategy import StockMediaStrategyRouter
from app.application.use_cases.search_stock_media import SearchStockMedia
from app.domain.enums import ApprovalStatus, AssetStatus, AssetType, ContentCategory, ContentStatus, RunStatus, RunType, SceneStatus, ScriptStatus
from app.infrastructure.database.models import ApprovalModel, AssetModel, ContentModel, RunModel, SceneModel, ScriptModel

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
    def __init__(self, *, session: Session, text: TextGenerationGateway, stock_media: StockMediaGateway, tts: TTSGateway, video_engine: VideoEngine, downloader: AssetDownloader, storage_root: Path = Path("storage/runs")) -> None:
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
        content = ContentModel(content_key=f"custom:{request.run_key}", language=request.language, category=ContentCategory.CUSTOM, topic=topic, status=ContentStatus.ACTIVE)
        self._session.add(content)
        self._session.flush()
        run = RunModel(run_key=request.run_key, content_id=content.id, run_type=RunType.CUSTOM, status=RunStatus.CREATED, requested_by=request.requested_by, language=request.language, strategy="custom_single_vertical_slice")
        self._session.add(run)
        self._session.flush()
        try:
            run.status = RunStatus.QUEUED
            run.status = RunStatus.RUNNING
            run.status = RunStatus.RESEARCHING
            run.status = RunStatus.TOPIC_VALIDATION
            run.status = RunStatus.SCRIPTING
            script = await self._create_script(run, topic, request.language)
            run.status = RunStatus.STORYBOARDING
            scenes = self._create_scenes(script, self._script_data)
            run.status = RunStatus.ASSET_PLANNING
            inputs = []
            for scene in scenes:
                path, asset = await self._select_asset(run, scene)
                scene.status = SceneStatus.READY
                self._session.add(asset)
                self._session.flush()
                inputs.append(VideoSceneInput(path=path, duration_seconds=float(scene.duration or 5), is_image=True))
            run.status = RunStatus.ASSET_GENERATION
            voice = await self._tts.synthesize(TTSRequest(run_id=str(run.id), request_id=f"{run.id}:voiceover", text=f"{script.hook} {script.body} {script.cta or ''}".strip()))
            run_dir = self._storage_root / str(run.id)
            audio_path = run_dir / f"voiceover.{voice.format}"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(voice.audio_bytes)
            run.status = RunStatus.TTS
            run.status = RunStatus.AUDIO_MIX
            output_path = request.output_path if request.output_path.is_absolute() else run_dir / request.output_path.name
            render = await self._video_engine.render(VideoRenderRequest(scenes=tuple(inputs), output_path=output_path, voiceover_path=audio_path))
            run.status = RunStatus.RENDERING
            run.status = RunStatus.QC
            validate_output(render.output_path, render.duration_seconds)
            run.status = RunStatus.READY_FOR_APPROVAL
            self._session.add(ApprovalModel(run_id=run.id, status=ApprovalStatus.PENDING))
            self._session.commit()
            return CustomShortResult(run.id, content.id, script.id, render.output_path, render.duration_seconds, run.status)
        except Exception:
            run.status = RunStatus.FAILED_RETRYABLE
            self._session.commit()
            raise

    async def _create_script(self, run: RunModel, topic: str, language: str) -> ScriptModel:
        result = await self._text.generate(TextGenerationRequest(run_id=str(run.id), request_id=f"{run.id}:script", prompt=f"Create a {language} YouTube Short about: {topic}. Target 25-40 seconds. Return JSON with hook, body, cta, duration_target, scenes. scenes must contain 4 items with duration, narration, visual_goal, visual_query. Use concrete stock-photo queries. Do not invent uncertain historical facts.", system_instruction="Return valid JSON only, with no markdown fences.", generation_config={"temperature": 0.7, "responseMimeType": "application/json"}))
        self._script_data = parse_script(result.text)
        data = self._script_data
        script = ScriptModel(content_id=run.content_id, version=1, language=language, hook=str(data["hook"]), body=str(data["body"]), cta=str(data.get("cta") or "") or None, duration_target=Decimal(str(data["duration_target"])), word_count=len(str(data["body"]).split()), status=ScriptStatus.DRAFT)
        self._session.add(script)
        self._session.flush()
        return script

    def _create_scenes(self, script: ScriptModel, data: Any) -> list[SceneModel]:
        if not isinstance(data, list):
            raise ValueError("Scene data must be a list")
        scenes = []
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError("Scene must be an object")
            scene = SceneModel(script_id=script.id, scene_index=index, duration=Decimal(str(item.get("duration", 6))), narration=str(item.get("narration", "")), visual_goal=str(item.get("visual_goal", "")), primary_subject=str(item.get("visual_query", "")), status=SceneStatus.PLANNED)
            self._session.add(scene)
            scenes.append(scene)
        self._session.flush()
        return scenes

    async def _select_asset(self, run: RunModel, scene: SceneModel) -> tuple[Path, AssetModel]:
        query = scene.primary_subject or scene.visual_goal or "historical scene"
        router = StockMediaStrategyRouter()
        result = await SearchStockMedia(self._stock_media).execute_strategy(run_id=str(run.id), request_id=f"{run.id}:scene:{scene.scene_index}", strategies=[router.build_exact(query), router.build_broad(query)])
        selected = StockMediaSelector(StockMediaScorer()).select(result.items, query=result.query)
        if selected is None:
            raise RuntimeError(f"No eligible stock asset found for scene {scene.scene_index}")
        item = selected.item
        url = str(item.get("download_url") or "").strip()
        if not url:
            raise RuntimeError(f"Selected asset has no download URL: {item.get('id')}")
        path = self._storage_root / str(run.id) / f"scene-{scene.scene_index}.jpg"
        await self._downloader.download(url, path)
        asset = AssetModel(asset_type=AssetType.STOCK_IMAGE, provider=result.provider, provider_asset_id=str(item.get("id") or ""), source_url=str(item.get("source_url") or ""), local_path=str(path), mime_type="image/jpeg", width=int(item.get("width") or 0), height=int(item.get("height") or 0), status=AssetStatus.READY, asset_metadata={"query": result.query, "score": selected.score.score})
        return path, asset