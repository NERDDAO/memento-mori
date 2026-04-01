# Roadmap

## Completed

### Phase 0: Spike
- [x] CrewAI + Bonfires KG integration validated
- [x] Flow state passing confirmed
- [x] Tool string serialization works

### Phase 1: Foundation
- [x] Pydantic models (Character, Location, Region, Item, Faction, Quest)
- [x] 10 KG tools wrapping Bonfires SDK
- [x] 8 deterministic mechanic tools (skill checks, damage, XP, loot, disposition)
- [x] YAML config with per-crew model assignments
- [x] 42 unit tests

### Phase 2: Core Game Loop
- [x] ContextGatherCrew (KG context assembly)
- [x] ClassificationCrew (action → event categories)
- [x] NarrationCrew (narrator + NPC voice + slopword filter)
- [x] GameTurnFlow (context → plausibility → detect → narrate)
- [x] EventDetectionFlow (classify → dispatch detectors → merge)

### Phase 3: World + NPC + Item Generation
- [x] RegionDesignCrew, LocationPlanningCrew, LocationCrew, ExitConnectionCrew
- [x] NPCPlanningCrew, ConceptCrew, MechanicsCrew, FinalizationCrew
- [x] ItemConceptCrew, ItemMechanicsCrew, BalanceReviewCrew
- [x] WorldGenFlow, NPCGenerationFlow, ItemGenerationFlow

### Phase 4: Combat + Permadeath
- [x] CombatAssessmentCrew, AttackResolutionCrew, AbilityResolutionCrew
- [x] ConsequenceCrew, PermadeathCrew
- [x] CombatFlow, PermadeathFlow
- [x] Combat wired into GameTurnFlow

### Phase 5: Memory + Quests + Factions
- [x] MemoryConsolidationCrew, NPCMemoryCrew
- [x] QuestDesignCrew, QuestStageCrew, QuestDialogueCrew
- [x] FactionGenerationCrew, ReputationCrew
- [x] 5 event detector crews (combat, inventory, quest, world_change, merge)
- [x] EpisodicMemoryFlow, QuestFlow, FactionFlow

### Phase 6: Gateway
- [x] FastAPI app with CORS, health check
- [x] Matrix bridge (room management, message relay)
- [x] WebSocket hub (location-aware broadcast)
- [x] REST routes (action, session, state)
- [x] Static file serving for client

### Phase 7: Web Client
- [x] Dark fantasy HTML/CSS layout
- [x] WebSocket connection + message handling
- [x] Rich text narrative with styled segments

### Phase 8: Integration
- [x] SessionManager (create player, kEngram, opening narration)
- [x] RoundManager (multiplayer action batching)
- [x] Gateway → engine wiring via Matrix

### Phase 9: Completion
- [x] EventDetectionFlow dispatches all 5 detector crews
- [x] EpisodicMemoryFlow wired into post-turn
- [x] QuestFlow + reputation tracking wired into resolve_events
- [x] AbilityResolution routed in CombatFlow
- [x] /api/state queries KG (not hardcoded)
- [x] State sync via WebSocket (engine → gateway → client)
- [x] Client renderState + text-renderer wired
- [x] Gateway serves client static files
- [x] Startup script

### Phase 10: UI
- [x] Session extraction from globals to module
- [x] Character creation overlay
- [x] All 6 panels functional (narrative, input, character, inventory, map, actions)
- [x] applyStateUpdate for server→client state sync
- [x] Pretext-powered virtualized narrative scrolling
- [x] Auto-reconnect with indicator
- [x] Death screen + create new character flow

---

## Next Up

### Phase 11: Matrix End-to-End
- [ ] Deploy Synapse (Docker compose)
- [ ] Test gateway ↔ engine communication through real Matrix
- [ ] Verify room-per-location topology works
- [ ] Test multiplayer (2+ players in same location, round batching)
- [ ] Test cross-location (player moves, joins new room, leaves old)
- [ ] Death feed room — broadcast permadeath announcements

### Phase 12: World Seeding
- [ ] Run WorldGenFlow to generate a starting region with 5+ locations
- [ ] Persist to Bonfires KG
- [ ] Verify players spawn into the generated world
- [ ] Add starting location selection (if multiple regions exist)

### Phase 13: Rich State Updates
- [ ] Engine sends full state snapshots (health, inventory, exits, NPCs) in state_update
- [ ] Parse narrative for structured events (damage numbers, item pickups, quest triggers)
- [ ] Client-side sound/visual effects for combat, level-up, death
- [ ] Inventory management UI (equip, drop, use)

### Phase 14: FactionFlow Integration
- [ ] Wire FactionFlow into WorldGenFlow (generate factions during region creation)
- [ ] Faction reputation visible in character panel
- [ ] NPC dialogue influenced by faction standing
- [ ] Faction-gated locations and quests

### Phase 15: Advanced Narrative
- [ ] Lorebook integration (SillyTavern format)
- [ ] Custom tone presets (grimdark, heroic, comedic)
- [ ] Scene illustration via image generation API
- [ ] NPC portrait generation
- [ ] Sound design — ambient audio per location type

### Phase 16: Player Experience
- [ ] Tutorial / guided first session
- [ ] Character customization (class, origin, starting skills)
- [ ] Skill tree UI
- [ ] Quest journal panel
- [ ] World map (graph visualization of discovered locations)

### Phase 17: Production
- [ ] Docker Compose (Synapse + Gateway + Engine)
- [ ] Authentication (Matrix login or standalone)
- [ ] Rate limiting (actions per minute)
- [ ] Cost monitoring (LLM tokens per turn)
- [ ] Admin panel (manage games, view KG, monitor players)
- [ ] Backup/restore (KG snapshots, session export)

---

## Design Principles

- **The world is a graph.** Every game object lives in the Bonfires KG. Relationships are edges. Search is semantic.
- **Death is permanent.** The world remembers. Dead characters become lore.
- **Agents reason, tools calculate.** Creative tasks (narration, NPC design) use CrewAI agents. Mechanical tasks (damage, skill checks) use deterministic tools.
- **Matrix is invisible.** Players see the web UI. Matrix handles persistence and multiplayer under the hood.
- **Less code, more YAML.** Agents are defined declaratively. The engine is orchestration, not implementation.
