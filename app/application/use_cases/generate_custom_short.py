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
from app.application.services.event_memory import EventMemoryCandidate, EventMemoryService
from app.application.services.hook_engine import HookEngine
from app.application.services.novelty_hardening import NoveltyHardeningService
from app.application.services.production_decision_adapter import ProductionDecisionAdapter
from app.application.services.scene_contract import build_scene_contract
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.topic_selection_production_adapter import (
    TopicSelectionProductionAdapter,
)
from app.application.services.visual_relevance import VisualRelevanceContext
from app.application.services.visual_source_resolver import VisualSourceResolver
from app.application.use_cases.search_stock_media import SearchStockMedia
from app.domain.decision import ProductionDecision
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
from app.domain.topic_optimization import TopicSelectionDecision
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
    production_decision: ProductionDecision | None = None
    topic_selection_decision: TopicSelectionDecision | None = None


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
        topic = TopicSelectionProductionAdapter(request.topic_selection_decision).resolve_topic(request.topic)
        decision_adapter = ProductionDecisionAdapter(request.production_decision)
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
            strategy=decision_adapter.production_strategy or "custom_single_vertical_slice",
        )
        self._session.add(run)
        self._session.flush()
        try:
            run.status = RunStatus.QUEUED
            run.status = RunStatus.RUNNING
            run.status = RunStatus.RESEARCHING
            run.status = RunStatus.TOPIC_VALIDATION
            run.status = RunStatus.SCRIPTING
            script, script_data, event_candidate = await self._create_script(
                run, topic, request.language, decision_adapter
            )
            if event_candidate is not None:
                novelty = NoveltyHardeningService(EventMemoryService(self._session)).evaluate(
                    event_candidate
                )
                if not novelty.accepted:
                    raise ValueError(
                        f"Novelty check rejected event: {novelty.reason}"
                        f" ({novelty.matched_event_id or 'unknown'})"
                    )
            run.status = RunStatus.STORYBOARDING
            scenes = self._create_scenes(script, script_data["scenes"])
            run.status = RunStatus.ASSET_PLANNING
            inputs = []
            for scene in scenes:
                path, asset = await self._select_asset(run, scene)
                scene.status = SceneStatus.READY
                self._session.add(asset)
                self._session.flush()
                inputs.append(
                    VideoSceneInput(
                        path=path,
                        duration_seconds=float(scene.duration or 5),
                        is_image=True,
                    )
                )
            run.status = RunStatus.ASSET_GENERATION
            narration_text = f"{script.hook} {script.body} {script.cta or ''}".strip()
            voice = await self._tts.synthesize(
                TTSRequest(
                    run_id=str(run.id),
                    request_id=f"{run.id}:voiceover",
                    text=narration_text,
                )
            )
            run_dir = self._storage_root / str(run.id)
            audio_path = run_dir / f"voiceover.{voice.format}"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(voice.audio_bytes)
            run.status = RunStatus.TTS
            run.status = RunStatus.AUDIO_MIX
            output_path = (
                request.output_path
                if request.output_path.is_absolute()
                else run_dir / request.output_path.name
            )
            render = await self._video_engine.render(
                VideoRenderRequest(
                    scenes=tuple(inputs),
                    output_path=output_path,
                    voiceover_path=audio_path,
                    subtitle_text=narration_text,
                )
            )
            run.status = RunStatus.RENDERING
            run.status = RunStatus.QC
            validate_output(render.output_path, render.duration_seconds)
            if event_candidate is not None:
                EventMemoryService(self._session).upsert(
                    EventMemoryCandidate(
                        event_id=event_candidate.event_id,
                        canonical_title=event_candidate.canonical_title,
                        aliases=event_candidate.aliases,
                        date=event_candidate.date,
                        location=event_candidate.location,
                        entities=event_candidate.entities,
                        event_summary=event_candidate.event_summary,
                        core_facts=event_candidate.core_facts,
                        claims=event_candidate.claims,
                        sources=event_candidate.sources,
                        first_video_id=event_candidate.first_video_id,
                        status="USED",
                    )
                )
            run.status = RunStatus.READY_FOR_APPROVAL
            self._session.add(ApprovalModel(run_id=run.id, status=ApprovalStatus.PENDING))
            self._session.commit()
            return CustomShortResult(
                run.id,
                content.id,
                script.id,
                render.output_path,
                render.duration_seconds,
                run.status,
            )
        except Exception:
            run.status = RunStatus.FAILED_RETRYABLE
            self._session.commit()
            raise

    async def _create_script(
        self,
        run: RunModel,
        topic: str,
        language: str,
        decision_adapter: ProductionDecisionAdapter,
    ) -> tuple[ScriptModel, dict[str, Any], EventMemoryCandidate | None]:
        result = await self._text.generate(
            TextGenerationRequest(
                run_id=str(run.id),
                request_id=f"{run.id}:script",
                prompt=(
                    f"Create a {language} YouTube Short about: {topic}. "
                    f"{decision_adapter.script_constraints()} Return JSON with hook, body, cta, "
                    "duration_target, event_memory, scenes. For historical topics, "
                    "event_memory must contain canonical_title, aliases, date, location, "
                    "entities, event_summary, core_facts, claims, sources, and status. "
                    "Use status NEW_EVENT when the event is believed to be new, KNOWN_EVENT "
                    "when it is known, and UNCERTAIN when identity is unclear. "
                    "For non-historical topics event_memory may be null. "
                    "Each scene must contain duration, narration, "
                    "visual_goal, visual_query, purpose, subject, action, entities, "
                    "location, era, visual_intent, visual_style, must_show, and must_avoid. "
                    "must describe the exact subject shown on screen. For historical "
                    "topics include concrete entities, location, event and era in "
                    "visual_query when relevant; never use generic queries such as "
                    "crowd or people when the narration names a specific place/event. "
                    "Use concrete stock-photo or historical-illustration queries. "
                    "The hook must be 4-18 words and strongly favor one of these types: shocking fact, unanswered question, impossible event, curiosity gap, contradiction.\n"
                    "Do not invent uncertain historical facts."
                ),
                system_instruction="Return valid JSON only, with no markdown fences.",
                generation_config={
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 3000,
                },
            )
        )
        data = parse_script(result.text)
        event_candidate = None
        event_memory_payload = data.get("event_memory")
        if event_memory_payload is not None and not isinstance(event_memory_payload, dict):
            raise ValueError("event_memory must be an object or null")
        if isinstance(event_memory_payload, dict):
            normalized_event_memory = dict(event_memory_payload)
            normalized_event_memory.pop("event_id", None)
            event_candidate = EventMemoryCandidate.from_payload(
                normalized_event_memory,
                fallback_title=topic,
            )
        hook_engine = HookEngine()
        hook_evaluation = hook_engine.evaluate(str(data["hook"]))
        if not hook_evaluation.is_acceptable:
            data["hook"] = hook_engine.fallback(topic)
            hook_engine.ensure_acceptable(str(data["hook"]))
        script = ScriptModel(
            content_id=run.content_id,
            version=1,
            language=language,
            hook=str(data["hook"]),
            body=str(data["body"]),
            cta=str(data.get("cta") or "") or None,
            duration_target=Decimal(
                str(decision_adapter.duration_target_seconds or data["duration_target"])
            ),
            word_count=len(str(data["body"]).split()),
            status=ScriptStatus.DRAFT,
        )
        self._session.add(script)
        self._session.flush()
        return script, data, event_candidate

    def _create_scenes(self, script: ScriptModel, data: Any) -> list[SceneModel]:
        if not isinstance(data, list):
            raise ValueError("Scene data must be a list")
        scenes = []
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError("Scene must be an object")
            contract = build_scene_contract(item)
            scene = SceneModel(
                script_id=script.id,
                scene_index=index,
                duration=Decimal(str(item.get("duration", 6))),
                narration=contract.narration,
                visual_goal=contract.visual_goal,
                primary_subject=contract.visual_query,
                action=contract.action,
                era=contract.era,
                location=contract.location,
                must_show=list(contract.must_show),
                must_avoid=list(contract.must_avoid),
                status=SceneStatus.PLANNED,
            )
            self._session.add(scene)
            scenes.append(scene)
        self._session.flush()
        return scenes

    async def _select_asset(self, run: RunModel, scene: SceneModel) -> tuple[Path, AssetModel]:
        scene_contract = build_scene_contract(
            {
                "narration": scene.narration,
                "visual_goal": scene.visual_goal,
                "visual_query": scene.primary_subject,
                "action": scene.action,
                "location": scene.location,
                "era": scene.era,
                "must_show": scene.must_show or [],
                "must_avoid": scene.must_avoid or [],
            }
        )
        source_plan = VisualSourceResolver().resolve(scene_contract)
        if source_plan.kind != "stock":
            raise RuntimeError(f"Unsupported visual source: {source_plan.kind}")
        strategies = [
            StockMediaStrategy(
                name="exact",
                query=source_plan.exact_query,
                operation="search_photos",
                orientation="portrait",
            ),
            *[
                StockMediaStrategy(
                    name=f"broader_{index}",
                    query=query,
                    operation="search_photos",
                    orientation="portrait",
                    min_relevance=0.10,
                )
                for index, query in enumerate(source_plan.broader_queries, start=1)
            ],
        ]
        result, selected = await SearchStockMedia(
            self._stock_media
        ).execute_strategy_until_selected(
            run_id=str(run.id),
            request_id=f"{run.id}:scene:{scene.scene_index}",
            strategies=strategies,
            selector=StockMediaSelector(StockMediaScorer()),
            relevance_context=VisualRelevanceContext.from_scene(scene_contract),
        )
        item = selected.item
        url = str(item.get("download_url") or "").strip()
        if not url:
            raise RuntimeError(f"Selected asset has no download URL: {item.get('id')}")
        path = self._storage_root / str(run.id) / f"scene-{scene.scene_index}.jpg"
        await self._downloader.download(url, path)
        asset = AssetModel(
            asset_type=AssetType.STOCK_IMAGE,
            provider=result.provider,
            provider_asset_id=str(item.get("id") or ""),
            source_url=str(item.get("source_url") or ""),
            local_path=str(path),
            mime_type="image/jpeg",
            width=int(item.get("width") or 0),
            height=int(item.get("height") or 0),
            status=AssetStatus.READY,
            asset_metadata={
                "query": result.query,
                "source_plan": source_plan.to_dict(),
                "score": selected.score.score,
                "scene_contract": {
                    "visual_goal": scene.visual_goal,
                    "subject": scene.primary_subject,
                    "action": scene.action,
                    "location": scene.location,
                    "era": scene.era,
                    "must_show": scene.must_show or [],
                    "must_avoid": scene.must_avoid or [],
                },
            },
        )
        return path, asset
