                )
        result = await self._text.generate(
            TextGenerationRequest(
                run_id=str(run.id),
                request_id=f"{run.id}:script",
                prompt=(
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
                    "end with a complete sentence, and reach a clear payoff. Scene narration must collectively "
                    "cover the full body rather than summarize only its beginning. Use narrative purposes from "
                    "hook, context, event, consequence, payoff; first scene must be hook and final scene must be payoff. "
                    "Include at least three distinct narrative purposes. Never end a body or scene narration mid-sentence. "
                    "The hook must be 4-18 words and strongly favor one of these types: shocking fact, unanswered question, impossible event, curiosity gap, contradiction.\n"
                    "Do not invent uncertain historical facts."
                ),
                system_instruction="Return valid JSON only, with no markdown fences.",
                generation_config={
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 6000,
                    "thinkingConfig": {"thinkingLevel": "low"},
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
