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
from app.application.services.audio_direction import AudioDirector
from app.application.services.audio_quality import AudioQualityAnalyzer
from app.application.services.autonomous_audio import AutonomousAudioPlanner
from app.application.services.camera_motion import (
    CameraMotionEngine,
    CameraMotionPlan,
    CameraMotionType,
)
from app.application.services.custom_short_support import parse_script, validate_output
from app.application.services.event_memory import EventMemoryCandidate, EventMemoryService
from app.application.services.experiment_persistence import ExperimentPersistenceService
from app.application.services.experiment_production_adapter import ExperimentProductionAdapter
from app.application.services.hook_engine import HookEngine
from app.application.services.narrative_redundancy import NarrativeRedundancyGate
from app.application.services.novelty_hardening import NoveltyHardeningService
from app.application.services.optimization_persistence import OptimizationDecisionPersistenceService
from app.application.services.optimization_production_adapter import OptimizationProductionAdapter
from app.application.services.production_decision_adapter import ProductionDecisionAdapter
from app.application.services.retry_execution_engine import JudgeDrivenRetryExecutionEngine
from app.application.services.retry_orchestrator import JudgeDrivenRetryOrchestrator, RetryAction
from app.application.services.scene_contract import build_scene_contract
from app.application.services.scene_timing import SceneTimingAllocator
from app.application.services.script_completeness import ScriptCompletenessGate
from app.application.services.stock_media_scoring import StockMediaScorer
from app.application.services.stock_media_selector import StockMediaSelector
from app.application.services.topic_selection_production_adapter import (
    TopicSelectionProductionAdapter,
)
from app.application.services.video_judge import (
    AutomatedVideoJudge,
    VideoJudgeInput,
    VideoJudgeReport,
)
from app.application.services.visual_beat import VisualBeatCompiler, VisualBeatTimeline
from app.application.services.visual_beat_render import to_video_scene_inputs
from app.application.services.visual_beat_retriever import VisualBeatRetriever
from app.application.services.visual_beautifier import VisualBeautifier
from app.application.services.visual_quality import VisualQualityDecision
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
    Stage,
    StageStatus,
)
from app.domain.experimentation import ExperimentAssignment, ExperimentVariant
from app.domain.optimization import OptimizationDecision
from app.domain.topic_optimization import TopicSelectionDecision
from app.infrastructure.database.models import (
    ApprovalModel,
    AssetModel,
    ContentModel,
    RunModel,
    SceneModel,
    ScriptModel,
    StageExecutionModel,
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
    experiment_variant: ExperimentVariant | None = None
    experiment_assignment: ExperimentAssignment | None = None
    optimization_decision: OptimizationDecision | None = None


@dataclass(frozen=True, slots=True)
class CustomShortResult:
    run_id: UUID
    content_id: UUID
    script_id: UUID
    output_path: Path
    duration_seconds: float
    status: RunStatus


@dataclass(frozen=True, slots=True)
class VisualBeatAssetSelection:
    timeline: VisualBeatTimeline
    paths: tuple[Path, ...]
    assets: tuple[AssetModel, ...]
    motions: tuple[CameraMotionPlan, ...]


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
        if (request.experiment_variant is None) != (request.experiment_assignment is None):
            raise ValueError("experiment variant and assignment must be provided together")
        if (
            request.experiment_variant is not None
            and request.experiment_assignment is not None
            and request.experiment_assignment.variant_id != request.experiment_variant.variant_id
        ):
            raise ValueError("experiment assignment variant does not match experiment variant")

        experiment_override = (
            ExperimentProductionAdapter().resolve(
                request.experiment_variant,
                production_decision=request.production_decision,
                topic_selection_decision=request.topic_selection_decision,
            )
            if request.experiment_variant is not None
            else None
        )
        optimization_override = (
            OptimizationProductionAdapter().resolve(
                request.optimization_decision,
                production_decision=request.production_decision,
                topic_selection_decision=request.topic_selection_decision,
            )
            if request.optimization_decision is not None
            else None
        )
        selected_topic = TopicSelectionProductionAdapter(
            request.topic_selection_decision
        ).resolve_topic(request.topic)
        topic = (
            experiment_override.topic
            if experiment_override is not None and experiment_override.topic is not None
            else (
                optimization_override.topic
                if optimization_override is not None and optimization_override.topic is not None
                else selected_topic
            )
        )
        decision_adapter = ProductionDecisionAdapter(request.production_decision)
        if not topic:
            raise ValueError("Custom topic must not be empty")
        if self._session.query(RunModel).filter_by(run_key=request.run_key).first() is not None:
            raise ValueError(f"Run key already exists: {request.run_key}")
        if request.experiment_assignment is not None:
            ExperimentPersistenceService(self._session).save_assignment(
                request.experiment_assignment
            )
        if request.optimization_decision is not None:
            OptimizationDecisionPersistenceService(self._session).save(
                request.optimization_decision
            )
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
            fallback_asset_count = 0
            visual_fallback_diagnostics: list[dict[str, object]] = []
            run.status = RunStatus.QUEUED
            run.status = RunStatus.RUNNING
            run.status = RunStatus.RESEARCHING
            run.status = RunStatus.TOPIC_VALIDATION
            run.status = RunStatus.SCRIPTING
            script, script_data, event_candidate = await self._create_script(
                run,
                topic,
                request.language,
                decision_adapter,
                experiment_override,
                optimization_override,
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
            inputs: list[VideoSceneInput] = []
            for scene in scenes:
                try:
                    selection = await self._select_visual_beats(run, scene, retrieval_attempt=1)
                    scene_inputs = to_video_scene_inputs(
                        selection.timeline,
                        selection.paths,
                        selection.motions,
                    )
                    assets = selection.assets
                except Exception as exc:
                    fallback_asset_count += 1
                    visual_fallback_diagnostics.append(
                        {
                            "scene_index": scene.scene_index,
                            "attempt": 1,
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:1200],
                        }
                    )
                    path, asset = await self._select_asset_scene_fallback(
                        run, scene, retrieval_attempt=1
                    )
                    fallback_duration = float(scene.duration or 5)
                    fallback_contract = build_scene_contract(
                        {
                            "narration": scene.narration or "",
                            "visual_goal": scene.visual_goal,
                            "visual_query": scene.primary_subject,
                            "purpose": "support_narration",
                            "subject": scene.primary_subject,
                            "action": scene.action,
                            "location": scene.location,
                            "era": scene.era,
                            "must_show": scene.must_show or [],
                            "must_avoid": scene.must_avoid or [],
                        }
                    )
                    fallback_timeline = VisualBeatCompiler().compile(
                        fallback_contract,
                        scene_index=scene.scene_index,
                        scene_duration_seconds=fallback_duration,
                    )
                    fallback_motion = CameraMotionEngine().plan(
                        purpose="support_narration",
                        duration_seconds=fallback_timeline.beats[0].duration_seconds,
                    )
                    scene_inputs = to_video_scene_inputs(
                        fallback_timeline,
                        (path,),
                        (fallback_motion,),
                    )
                    assets = (asset,)
                scene.status = SceneStatus.READY
                for asset in assets:
                    self._session.add(asset)
                self._session.flush()
                inputs.extend(scene_inputs)
            run.status = RunStatus.ASSET_GENERATION
            direction = AudioDirector().plan(
                hook=script.hook,
                body=script.body,
                cta=script.cta,
            )
            voice = await self._tts.synthesize(
                TTSRequest(
                    run_id=str(run.id),
                    request_id=f"{run.id}:voiceover",
                    text=direction.tts_text,
                )
            )
            run_dir = self._storage_root / str(run.id)
            audio_path = run_dir / f"voiceover.{voice.format}"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(voice.audio_bytes)
            run.status = RunStatus.TTS

            audio_plan = AutonomousAudioPlanner().build(
                run_id=run.id,
                direction=direction,
                scenes=tuple(
                    {
                        "scene_index": scene.scene_index,
                        "narration": scene.narration or "",
                    }
                    for scene in scenes
                ),
                duration_seconds=float(script.duration_target or 30),
                output_dir=run_dir / "audio",
            )
            self._session.add(
                StageExecutionModel(
                    run_id=run.id,
                    stage=Stage.AUDIO_MIX,
                    attempt=1,
                    status=StageStatus.SUCCESS,
                    provider="m15-procedural-audio",
                    stage_metadata={
                        **audio_plan.metadata,
                        "audio_profile": audio_plan.profile,
                        "voice_provider": voice.provider,
                        "voice_energy": direction.energy,
                        "emphasis_terms": list(direction.emphasis_terms),
                    },
                )
            )
            self._session.flush()
            run.status = RunStatus.AUDIO_MIX

            output_path = (
                request.output_path
                if request.output_path.is_absolute()
                else run_dir / request.output_path.name
            )
            background_volume = 0.14
            render = await self._video_engine.render(
                VideoRenderRequest(
                    scenes=tuple(inputs),
                    output_path=output_path,
                    voiceover_path=audio_path,
                    background_audio_path=audio_plan.background_audio_path,
                    subtitle_text=direction.tts_text,
                    background_volume=background_volume,
                    ducking_threshold=0.03,
                    ducking_ratio=8.0,
                    ducking_attack_ms=20.0,
                    ducking_release_ms=250.0,
                )
            )
            run.status = RunStatus.RENDERING
            run.status = RunStatus.QC
            validate_output(render.output_path, render.duration_seconds)
            audio_qc = await AudioQualityAnalyzer().analyze_file(
                render.output_path,
                duration_seconds=render.duration_seconds,
            )
            if not audio_qc.passed:
                # One bounded repair: reduce the music/SFX bed and rerender.
                repaired_volume = background_volume * 0.5
                render = await self._video_engine.render(
                    VideoRenderRequest(
                        scenes=tuple(inputs),
                        output_path=output_path,
                        voiceover_path=audio_path,
                        background_audio_path=audio_plan.background_audio_path,
                        subtitle_text=direction.tts_text,
                        background_volume=repaired_volume,
                        ducking_threshold=0.02,
                        ducking_ratio=10.0,
                        ducking_attack_ms=15.0,
                        ducking_release_ms=300.0,
                    )
                )
                validate_output(render.output_path, render.duration_seconds)
                audio_qc = await AudioQualityAnalyzer().analyze_file(
                    render.output_path,
                    duration_seconds=render.duration_seconds,
                )
                if not audio_qc.passed:
                    raise RuntimeError(
                        "M15 audio QC failed after one bounded repair: "
                        + "; ".join(audio_qc.failures)
                    )
            sync_total = render.synchronization.get(
                "total_duration_seconds",
                render.duration_seconds,
            )
            expected_duration = (
                float(sync_total)
                if isinstance(sync_total, (int, float))
                else render.duration_seconds
            )
            judge = AutomatedVideoJudge().evaluate(
                VideoJudgeInput(
                    output_path=render.output_path,
                    duration_seconds=render.duration_seconds,
                    width=render.width,
                    height=render.height,
                    fps=render.fps,
                    has_audio=render.has_audio,
                    expected_duration_seconds=expected_duration,
                    scene_count=len(scenes),
                    asset_count=len(inputs),
                    narration_word_count=len(direction.tts_text.split()),
                    subtitle_text=direction.tts_text,
                    synchronization=render.synchronization,
                    audio_qc_passed=audio_qc.passed,
                    audio_qc_failures=tuple(audio_qc.failures),
                    fallback_asset_count=fallback_asset_count,
                )
            )
            stage = (
                self._session.query(StageExecutionModel)
                .filter_by(
                    run_id=run.id,
                    stage=Stage.AUDIO_MIX,
                    attempt=1,
                )
                .first()
            )
            if stage is not None:
                stage.stage_metadata = {
                    **(stage.stage_metadata or {}),
                    "m29_synchronization": render.synchronization,
                    "m30_automated_video_judge": {
                        "decision": judge.decision,
                        "score": judge.score,
                        "dimension_scores": judge.dimension_scores,
                        "failures": list(judge.failures),
                        "warnings": list(judge.warnings),
                        "retry_reasons": list(judge.retry_reasons),
                        "evaluated_path": judge.evaluated_path,
                        "fallback_asset_count": fallback_asset_count,
                        "fallback_diagnostics": list(visual_fallback_diagnostics),
                    },
                    "audio_qc": {
                        "passed": audio_qc.passed,
                        "failures": list(audio_qc.failures),
                        "max_volume_dbfs": audio_qc.max_volume_dbfs,
                        "mean_volume_dbfs": audio_qc.mean_volume_dbfs,
                        "silence_ratio": audio_qc.silence_ratio,
                        "repair_applied": background_volume != 0.14,
                    },
                }
            retry_decision = JudgeDrivenRetryOrchestrator(max_attempts=3).decide(
                judge,
                attempt=1,
            )
            if stage is not None:
                stage.stage_metadata = {
                    **(stage.stage_metadata or {}),
                    "m31_retry_orchestration": {
                        "attempt": retry_decision.plan.attempt,
                        "max_attempts": retry_decision.plan.max_attempts,
                        "retryable": retry_decision.plan.retryable,
                        "actions": [action.value for action in retry_decision.plan.actions],
                        "reasons": list(retry_decision.plan.reasons),
                        "terminal_reason": retry_decision.plan.terminal_reason,
                        "next_status": retry_decision.next_status,
                    },
                }
            if judge.decision == "RETRY":
                retry_history: list[dict[str, object]] = []

                async def execute_retry_attempt(
                    *,
                    actions: tuple[RetryAction, ...],
                    attempt: int,
                ) -> VideoJudgeReport:
                    nonlocal inputs, fallback_asset_count, background_volume, render
                    nonlocal visual_fallback_diagnostics

                    if RetryAction.RESELECT_VISUALS in actions:
                        refreshed_inputs: list[VideoSceneInput] = []
                        refreshed_fallbacks = 0
                        for scene in scenes:
                            try:
                                selection = await self._select_visual_beats(
                                    run, scene, retrieval_attempt=attempt
                                )
                                refreshed_inputs.extend(
                                    to_video_scene_inputs(
                                        selection.timeline,
                                        selection.paths,
                                        selection.motions,
                                    )
                                )
                                for asset in selection.assets:
                                    self._session.add(asset)
                            except Exception as exc:
                                refreshed_fallbacks += 1
                                visual_fallback_diagnostics.append(
                                    {
                                        "scene_index": scene.scene_index,
                                        "attempt": attempt,
                                        "error_type": type(exc).__name__,
                                        "error": str(exc)[:1200],
                                    }
                                )
                                path, asset = await self._select_asset_scene_fallback(
                                    run,
                                    scene,
                                    retrieval_attempt=attempt,
                                )
                                fallback_duration = float(scene.duration or 5)
                                fallback_contract = build_scene_contract(
                                    {
                                        "narration": scene.narration or "",
                                        "visual_goal": scene.visual_goal,
                                        "visual_query": scene.primary_subject,
                                        "purpose": "support_narration",
                                        "subject": scene.primary_subject,
                                        "action": scene.action,
                                        "location": scene.location,
                                        "era": scene.era,
                                        "must_show": scene.must_show or [],
                                        "must_avoid": scene.must_avoid or [],
                                    }
                                )
                                fallback_timeline = VisualBeatCompiler().compile(
                                    fallback_contract,
                                    scene_index=scene.scene_index,
                                    scene_duration_seconds=fallback_duration,
                                )
                                fallback_motion = CameraMotionEngine().plan(
                                    purpose="support_narration",
                                    duration_seconds=fallback_timeline.beats[0].duration_seconds,
                                )
                                refreshed_inputs.extend(
                                    to_video_scene_inputs(
                                        fallback_timeline,
                                        (path,),
                                        (fallback_motion,),
                                    )
                                )
                                self._session.add(asset)
                        self._session.flush()
                        inputs = refreshed_inputs
                        fallback_asset_count = refreshed_fallbacks

                    if RetryAction.REPAIR_AUDIO in actions:
                        background_volume = max(background_volume * 0.5, 0.01)

                    if RetryAction.RECONCILE_TIMELINE in actions:
                        # M29 reconciliation is executed by the render engine
                        # against the actual voiceover duration.
                        pass

                    render = await self._video_engine.render(
                        VideoRenderRequest(
                            scenes=tuple(inputs),
                            output_path=output_path,
                            voiceover_path=audio_path,
                            background_audio_path=audio_plan.background_audio_path,
                            subtitle_text=direction.tts_text,
                            background_volume=background_volume,
                            ducking_threshold=0.02,
                            ducking_ratio=10.0 if RetryAction.REPAIR_AUDIO in actions else 8.0,
                            ducking_attack_ms=15.0 if RetryAction.REPAIR_AUDIO in actions else 20.0,
                            ducking_release_ms=300.0
                            if RetryAction.REPAIR_AUDIO in actions
                            else 250.0,
                        )
                    )
                    validate_output(render.output_path, render.duration_seconds)
                    retry_audio_qc = await AudioQualityAnalyzer().analyze_file(
                        render.output_path,
                        duration_seconds=render.duration_seconds,
                    )
                    sync_total = render.synchronization.get(
                        "total_duration_seconds",
                        render.duration_seconds,
                    )
                    retry_expected_duration = (
                        float(sync_total)
                        if isinstance(sync_total, (int, float))
                        else render.duration_seconds
                    )
                    retry_judge = AutomatedVideoJudge().evaluate(
                        VideoJudgeInput(
                            output_path=render.output_path,
                            duration_seconds=render.duration_seconds,
                            width=render.width,
                            height=render.height,
                            fps=render.fps,
                            has_audio=render.has_audio,
                            expected_duration_seconds=retry_expected_duration,
                            scene_count=len(scenes),
                            asset_count=len(inputs),
                            narration_word_count=len(direction.tts_text.split()),
                            subtitle_text=direction.tts_text,
                            synchronization=render.synchronization,
                            audio_qc_passed=retry_audio_qc.passed,
                            audio_qc_failures=tuple(retry_audio_qc.failures),
                            fallback_asset_count=fallback_asset_count,
                        )
                    )
                    retry_history.append(
                        {
                            "attempt": attempt,
                            "actions": [action.value for action in actions],
                            "decision": retry_judge.decision,
                            "score": retry_judge.score,
                            "retry_reasons": list(retry_judge.retry_reasons),
                            "fallback_asset_count": fallback_asset_count,
                            "audio_qc_passed": retry_audio_qc.passed,
                            "synchronization": render.synchronization,
                        }
                    )
                    return retry_judge

                retry_engine = JudgeDrivenRetryExecutionEngine(
                    orchestrator=JudgeDrivenRetryOrchestrator(max_attempts=3),
                    executor=execute_retry_attempt,
                )
                retry_result = await retry_engine.execute(judge, attempt=1)
                judge = retry_result.report
                if stage is not None:
                    stage.stage_metadata = {
                        **(stage.stage_metadata or {}),
                        "m32_retry_execution": {
                            "attempts": retry_history,
                            "attempt_count": len(retry_history),
                            "exhausted": retry_result.exhausted,
                            "terminal_reason": retry_result.terminal_reason,
                            "final_decision": judge.decision,
                        },
                        "visual_fallback_diagnostics": list(visual_fallback_diagnostics),
                        "m33_adaptive_retry": {
                            "effectiveness": [
                                {
                                    "attempt": observation.attempt,
                                    "before_score": observation.before_score,
                                    "after_score": observation.after_score,
                                    "score_delta": observation.score_delta,
                                    "improved": observation.improved,
                                    "actions": [action.value for action in observation.actions],
                                    "dimension_deltas": observation.dimension_deltas,
                                }
                                for observation in retry_result.effectiveness
                            ],
                            "adaptations": [
                                {
                                    "actions": [action.value for action in adaptation.actions],
                                    "excluded_actions": [
                                        action.value for action in adaptation.excluded_actions
                                    ],
                                    "reason": adaptation.reason,
                                }
                                for adaptation in retry_result.adaptations
                            ],
                        },
                        "m34_retry_economics": {
                            "decisions": [
                                {
                                    "actions": [action.value for action in economics.actions],
                                    "preserved_actions": [
                                        action.value for action in economics.preserved_actions
                                    ],
                                    "reason": economics.reason,
                                    "rankings": [
                                        {
                                            "action": item.action.value,
                                            "estimated_cost": item.estimated_cost,
                                            "expected_gain": item.expected_gain,
                                            "efficiency": item.efficiency,
                                        }
                                        for item in economics.rankings
                                    ],
                                }
                                for economics in retry_result.economics
                            ],
                        },
                    }
                if judge.decision == "RETRY":
                    run.status = RunStatus.FAILED_PERMANENT
                    self._session.commit()
                    return CustomShortResult(
                        run.id,
                        content.id,
                        script.id,
                        render.output_path,
                        render.duration_seconds,
                        run.status,
                    )
                if judge.decision == "REJECT":
                    run.status = RunStatus.FAILED_PERMANENT
                    self._session.commit()
                    return CustomShortResult(
                        run.id,
                        content.id,
                        script.id,
                        render.output_path,
                        render.duration_seconds,
                        run.status,
                    )
            if judge.decision == "REJECT":
                run.status = RunStatus.FAILED_PERMANENT
                self._session.commit()
                return CustomShortResult(
                    run.id,
                    content.id,
                    script.id,
                    render.output_path,
                    render.duration_seconds,
                    run.status,
                )
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
        experiment_override: Any | None = None,
        optimization_override: Any | None = None,
    ) -> tuple[ScriptModel, dict[str, Any], EventMemoryCandidate | None]:
        constraints = decision_adapter.script_constraints()
        if experiment_override is not None:
            if experiment_override.angle is not None:
                constraints = f"{constraints} Experiment angle: {experiment_override.angle}."
            if experiment_override.duration_target_seconds is not None:
                constraints = (
                    f"{constraints} Experiment duration target: "
                    f"{experiment_override.duration_target_seconds:g} seconds."
                )
        if optimization_override is not None:
            if optimization_override.angle is not None:
                constraints = f"{constraints} Optimization angle: {optimization_override.angle}."
            if optimization_override.duration_target_seconds is not None:
                constraints = (
                    f"{constraints} Optimization duration target: "
                    f"{optimization_override.duration_target_seconds:g} seconds."
                )
        base_prompt = (
            f"Create a {language} YouTube Short about: {topic}. "
            f"{constraints} Return JSON with hook, body, cta, "
            "duration_target, event_memory, scenes. For historical topics, "
            "event_memory must contain canonical_title, aliases, date, location, "
            "entities, event_summary, core_facts, claims, sources, and status. "
            "Use status NEW_EVENT when the event is believed to be new, KNOWN_EVENT "
            "when it is known, and UNCERTAIN when identity is unclear. "
            "For non-historical topics event_memory may be null. "
            "Each scene must contain duration, narration, "
            "visual_goal, visual_query, purpose, subject, action, entities, "
            "location, era, visual_intent, visual_style, must_show, and must_avoid. "
            "entities, must_show, and must_avoid must be JSON arrays of strings. "
            "must describe the exact subject shown on screen. For historical "
            "topics include concrete entities, location, event and era in "
            "visual_query when relevant; never use generic queries such as "
            "crowd or people when the narration names a specific place/event. "
            "Use concrete stock-photo or historical-illustration queries. "
            "The story must be complete, not a teaser or partial excerpt: body must be at least 35 words, "
            "end with a complete sentence, and reach a clear payoff. "
            "Keep total spoken words in hook + body + cta appropriate for duration_target at about "
            "2.5 words per second; do not exceed 1.3 times the target duration. "
            "Scene narration must collectively cover the full body in the same story order, not just summarize "
            "its beginning. Every important body fact and consequence must appear in at least one scene narration. "
            "Paraphrasing is allowed, but do not omit body beats. The first scene purpose must be exactly hook "
            "and its narration must deliver the hook beat; the final scene purpose must be exactly payoff and "
            "its narration must deliver the ending. Use at least three distinct purposes from hook, context, "
            "event, consequence, payoff. Never end a body or scene narration mid-sentence. "
            "The hook must be 4-18 words and strongly favor one of these types: shocking fact, unanswered question, "
            "impossible event, curiosity gap, contradiction.\n"
            "Narrative progression is mandatory: each sentence must add a new fact, consequence, mechanism, contrast, or payoff. "
            "Do not restate the hook in the first body sentence. Do not repeat an adjacent claim with superficial wording changes. "
            "If two sentences express the same claim, rewrite one so the story advances.\n"
            "Do not invent uncertain historical facts."
        )

        async def generate_candidate(
            *,
            attempt: int,
            repair_failures: tuple[str, ...] = (),
        ) -> tuple[dict[str, Any], EventMemoryCandidate | None, Any]:
            repair_instruction = ""
            if repair_failures:
                repair_instruction = (
                    "\n\nCORRECTION REQUIRED — the previous draft failed deterministic checks. "
                    "Regenerate the complete JSON from scratch and fix every listed failure. "
                    "Do not merely explain the failures. Preserve factual accuracy and visual specificity. "
                    "For scene coverage, map the complete body across the scene narrations in chronological order; "
                    "ensure the total narration word count is at least the body word count. "
                    "Set the first scene purpose to exactly 'hook' and the final scene purpose to exactly 'payoff'. "
                    "If duration is too long, shorten hook/body/CTA to fit the target while keeping the scene narrations "
                    "aligned with the shortened body. Failures: " + "; ".join(repair_failures)
                )
            result = await self._text.generate(
                TextGenerationRequest(
                    run_id=str(run.id),
                    request_id=(
                        f"{run.id}:script" if attempt == 0 else f"{run.id}:script:repair:{attempt}"
                    ),
                    prompt=base_prompt + repair_instruction,
                    system_instruction="Return valid JSON only, with no markdown fences.",
                    generation_config={
                        "responseMimeType": "application/json",
                        "maxOutputTokens": 6000,
                        "thinkingConfig": {"thinkingLevel": "low"},
                    },
                )
            )
            candidate_data = parse_script(result.text)
            event_candidate = None
            event_memory_payload = candidate_data.get("event_memory")
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
            hook_evaluation = hook_engine.evaluate(str(candidate_data["hook"]))
            if not hook_evaluation.is_acceptable:
                candidate_data["hook"] = hook_engine.fallback(topic)
                hook_engine.ensure_acceptable(str(candidate_data["hook"]))

            effective_duration_target = (
                experiment_override.duration_target_seconds
                if experiment_override is not None
                and experiment_override.duration_target_seconds is not None
                else (
                    optimization_override.duration_target_seconds
                    if optimization_override is not None
                    and optimization_override.duration_target_seconds is not None
                    else decision_adapter.duration_target_seconds
                    or candidate_data["duration_target"]
                )
            )
            candidate_data["duration_target"] = float(effective_duration_target)

            if isinstance(candidate_data.get("scenes"), list):
                candidate_scenes = candidate_data["scenes"]
                planned_durations = tuple(
                    float(scene.get("duration") or 6)
                    for scene in candidate_scenes
                    if isinstance(scene, dict)
                )
                narration_word_counts = tuple(
                    len(str(scene.get("narration") or "").split())
                    for scene in candidate_scenes
                    if isinstance(scene, dict)
                )
                if len(planned_durations) == len(candidate_scenes):
                    normalized_durations = SceneTimingAllocator().normalize_for_narration(
                        planned_durations,
                        narration_word_counts,
                    )
                    for scene, duration in zip(
                        candidate_scenes,
                        normalized_durations,
                        strict=True,
                    ):
                        scene["duration"] = duration

            report = ScriptCompletenessGate().evaluate(candidate_data)
            return candidate_data, event_candidate, report

        data, event_candidate, completeness_report = await generate_candidate(attempt=0)
        initial_completeness_failures = completeness_report.failures
        script_generation_attempts = 1
        if not completeness_report.passed:
            # One bounded correction attempt prevents endless generation loops and repeated cost.
            script_generation_attempts = 2
            data, event_candidate, completeness_report = await generate_candidate(
                attempt=1,
                repair_failures=initial_completeness_failures,
            )
        completeness_report.raise_if_failed()
        narrative_report = NarrativeRedundancyGate().evaluate(data)
        self._session.add(
            StageExecutionModel(
                run_id=run.id,
                stage=Stage.SCRIPTING,
                attempt=1,
                status=(
                    StageStatus.SUCCESS if narrative_report.passed else StageStatus.FAILED_PERMANENT
                ),
                provider="deterministic-m23-narrative-redundancy",
                stage_metadata={
                    "gate": "NarrativeRedundancyGate",
                    "passed": narrative_report.passed,
                    "signals": list(narrative_report.signals),
                    "failures": list(narrative_report.failures),
                    "max_similarity": narrative_report.max_similarity,
                    "compared_pairs": narrative_report.compared_pairs,
                    "script_completeness": {
                        "passed": completeness_report.passed,
                        "generation_attempts": script_generation_attempts,
                        "initial_failures": list(initial_completeness_failures),
                        "final_failures": list(completeness_report.failures),
                        "body_word_count": completeness_report.body_word_count,
                        "scene_narration_word_count": completeness_report.narration_word_count,
                        "estimated_speech_seconds": completeness_report.estimated_speech_seconds,
                        "scene_duration_seconds": completeness_report.scene_duration_seconds,
                    },
                },
            )
        )
        self._session.flush()
        narrative_report.raise_if_failed()

        script = ScriptModel(
            content_id=run.content_id,
            version=1,
            language=language,
            hook=str(data["hook"]),
            body=str(data["body"]),
            cta=str(data.get("cta") or "") or None,
            duration_target=Decimal(
                str(
                    experiment_override.duration_target_seconds
                    if experiment_override is not None
                    and experiment_override.duration_target_seconds is not None
                    else (
                        optimization_override.duration_target_seconds
                        if optimization_override is not None
                        and optimization_override.duration_target_seconds is not None
                        else decision_adapter.duration_target_seconds or data["duration_target"]
                    )
                )
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
        try:
            selection = await self._select_visual_beats(run, scene)
            best_index = max(
                range(len(selection.assets)),
                key=lambda index: float(
                    (selection.assets[index].asset_metadata or {}).get("score", 0.0)
                ),
            )
            return selection.paths[best_index], selection.assets[best_index]
        except Exception:
            return await self._select_asset_scene_fallback(run, scene)

    async def _select_visual_beats(
        self,
        run: RunModel,
        scene: SceneModel,
        *,
        retrieval_attempt: int = 1,
    ) -> VisualBeatAssetSelection:
        scene_contract = build_scene_contract(
            {
                "narration": scene.narration,
                "visual_goal": scene.visual_goal,
                "visual_query": scene.primary_subject,
                "purpose": "support_narration",
                "subject": scene.primary_subject,
                "action": scene.action,
                "entities": [],
                "location": scene.location,
                "era": scene.era,
                "visual_intent": scene.visual_goal,
                "visual_style": "documentary",
                "must_show": scene.must_show or [],
                "must_avoid": scene.must_avoid or [],
            }
        )
        timeline = VisualBeatCompiler().compile(
            scene_contract,
            scene_index=scene.scene_index,
            scene_duration_seconds=float(scene.duration or 5),
        )
        retriever = VisualBeatRetriever(self._stock_media)
        results = []
        for beat in timeline.beats:
            results.append(
                await retriever.retrieve(
                    run_id=str(run.id),
                    request_id=(
                        f"{run.id}:scene:{scene.scene_index}:attempt:{retrieval_attempt}:"
                        f"beat:{beat.beat_index}"
                    ),
                    beat=beat,
                )
            )

        motion_engine = CameraMotionEngine()
        motions: list[CameraMotionPlan] = []
        recent_motion: list[CameraMotionType] = []
        for beat in timeline.beats:
            motion = motion_engine.plan(
                purpose=beat.purpose,
                duration_seconds=beat.duration_seconds,
                beat_index=beat.beat_index,
                recent_motion=tuple(recent_motion[-2:]),
            )
            motions.append(motion)
            recent_motion.append(motion.motion_type)

        paths: list[Path] = []
        assets: list[AssetModel] = []
        beautifier = VisualBeautifier()
        for result in results:
            item = result.item
            url = str(item.get("download_url") or "").strip()
            if not url:
                raise RuntimeError(f"Selected beat asset has no download URL: {item.get('id')}")
            source_path = (
                self._storage_root
                / str(run.id)
                / f"scene-{scene.scene_index}-beat-{result.beat.beat_index}.jpg"
            )
            await self._downloader.download(url, source_path)
            path = source_path
            beautification = None
            if result.quality_decision == VisualQualityDecision.BEAUTIFY.value:
                beautified_path = (
                    self._storage_root
                    / str(run.id)
                    / f"scene-{scene.scene_index}-beat-{result.beat.beat_index}-beautified.jpg"
                )
                beautification = beautifier.beautify(source_path, beautified_path)
                path = beautification.output_path

            assets.append(
                AssetModel(
                    asset_type=AssetType.STOCK_IMAGE,
                    provider=result.provider,
                    provider_asset_id=str(item.get("id") or ""),
                    source_url=str(item.get("source_url") or ""),
                    local_path=str(path),
                    mime_type="image/jpeg",
                    width=beautification.width if beautification else int(item.get("width") or 0),
                    height=beautification.height
                    if beautification
                    else int(item.get("height") or 0),
                    status=AssetStatus.READY,
                    asset_metadata={
                        "query": result.query,
                        "score": result.score,
                        "m19_visual_quality": {
                            "decision": result.quality_decision,
                            "overall": result.visual_quality,
                            "beautifiable": result.beautifiable,
                            "beautification_applied": bool(
                                beautification and beautification.changed
                            ),
                            "operations": list(beautification.operations) if beautification else [],
                            "fallback_reason": (
                                beautification.fallback_reason if beautification else None
                            ),
                        },
                        "m18_visual_beat": {
                            "scene_index": scene.scene_index,
                            "beat_index": result.beat.beat_index,
                            "start_seconds": result.beat.start_seconds,
                            "duration_seconds": result.beat.duration_seconds,
                            "beat_count": len(timeline.beats),
                        },
                        "m28_camera_motion": {
                            "motion_type": motions[result.beat.beat_index].motion_type.value,
                            "intensity": motions[result.beat.beat_index].intensity,
                            "focus_x": motions[result.beat.beat_index].focus_x,
                            "focus_y": motions[result.beat.beat_index].focus_y,
                        },
                        "m20_semantic_verification": {
                            "decision": result.verification_decision,
                            "overall": result.semantic_verification_score,
                            "verifier": result.semantic_verifier,
                            "matched_signals": list(result.matched_signals),
                            "missing_signals": list(result.missing_signals),
                            "violated_constraints": list(result.violated_constraints),
                            "retrieval_attempts": list(result.retrieval_attempts),
                        },
                    },
                )
            )
            paths.append(path)

        return VisualBeatAssetSelection(
            timeline=timeline,
            paths=tuple(paths),
            assets=tuple(assets),
            motions=tuple(motions),
        )

    async def _select_asset_scene_fallback(
        self,
        run: RunModel,
        scene: SceneModel,
        *,
        retrieval_attempt: int = 1,
    ) -> tuple[Path, AssetModel]:
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
            request_id=(f"{run.id}:scene:{scene.scene_index}:fallback:attempt:{retrieval_attempt}"),
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
