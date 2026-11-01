use crate::arena_tables::{
    lookup_arena_slug, pad_table_for_slug, snap_to_pad, within_snap_tolerance, ArenaPadDef,
};
use std::collections::{HashMap, VecDeque};
use std::env;

/// Object name for a pad actor whose `NewActor` was never seen.
const UNTRACKED_PAD_NAME: &str = "VehiclePickup_Boost_TA";

#[derive(Clone, Copy, Debug)]
pub enum PadEventStatus {
    Collected,
    Respawned,
}

impl PadEventStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            PadEventStatus::Collected => "COLLECTED",
            PadEventStatus::Respawned => "RESPAWNED",
        }
    }
}

/// A replicated pickup state, in the form its attribute carries it.
#[derive(Clone, Copy, Debug)]
pub enum PickupState {
    /// `ReplicatedPickupData`: 1 when picked up, 0 when not.
    Flag(u8),
    /// `NewReplicatedPickupData`: odd and rising by 2 per collection, 255 once the
    /// pad is back. A goal reset goes to 255 without advancing it, so the next
    /// collection can repeat the previous value.
    Counter(u8),
}

impl PickupState {
    fn raw(self) -> u8 {
        match self {
            PickupState::Flag(raw) | PickupState::Counter(raw) => raw,
        }
    }
}

#[derive(Clone, Debug)]
pub struct PadEvent {
    pub pad_id: usize,
    pub is_big: bool,
    /// "blue" | "orange" | "mid"
    pub pad_side: &'static str,
    /// Canonical arena slug (e.g. "soccar") or "unknown".
    pub arena: &'static str,
    /// True when the arena was recognised and pad metadata comes from a verified
    /// canonical table. False when the arena slug is "unknown" — callers should
    /// treat pad_id / pad_side / is_big as unreliable in that case.
    pub arena_supported: bool,
    pub object_name: String,
    pub position: (f32, f32, f32),
    pub timestamp: f32,
    pub raw_state: u8,
    pub instigator_actor_id: Option<i32>,
    pub resolved_actor_id: Option<i32>,
    pub status: PadEventStatus,
    /// Snap distance from observed position to canonical pad centre (uu).
    pub snap_distance: Option<f32>,
    /// Alias for snap_distance, exposed as snap_error_uu in Python payload.
    pub snap_error_uu: Option<f32>,
}

#[derive(Clone, Debug)]
struct PendingEvent {
    raw_state: u8,
    timestamp: f32,
    instigator_actor_id: Option<i32>,
    resolved_actor_id: Option<i32>,
}

#[derive(Clone, Debug)]
struct PadInstance {
    object_name: String,
    pad_def: Option<ArenaPadDef>,
    position: Option<(f32, f32, f32)>,
    /// Last accepted state of any kind, to spot re-sends.
    last_state: Option<u8>,
    /// State of the last accepted collection, to spot a counter that advanced.
    last_collected: Option<u8>,
    pending: VecDeque<PendingEvent>,
    snap_distance: Option<f32>,
}

impl PadInstance {
    fn new(object_name: &str) -> Self {
        PadInstance {
            object_name: object_name.to_string(),
            pad_def: None,
            position: None,
            last_state: None,
            last_collected: None,
            pending: VecDeque::new(),
            snap_distance: None,
        }
    }

    /// Whether a replicated state is a real change rather than a re-send.
    ///
    /// Replay checkpoints re-send each pad's last state, sometimes an older one,
    /// and name a dead (-1) or unrelated car as its instigator. A counter that
    /// advanced is always real. One that did not is real only after a goal reset,
    /// and then the car has to be at the pad.
    fn accepts(
        &self,
        state: PickupState,
        instigator_actor_id: Option<i32>,
        car_position: Option<(f32, f32, f32)>,
    ) -> bool {
        if self.last_state == Some(state.raw()) {
            return false;
        }
        let Some(instigator) = instigator_actor_id else {
            return true;
        };
        if instigator < 0 {
            return false;
        }
        match state {
            PickupState::Flag(_) => true,
            PickupState::Counter(raw) => {
                counter_advanced(self.last_collected, raw) || self.car_at_pad(car_position)
            }
        }
    }

    fn car_at_pad(&self, car_position: Option<(f32, f32, f32)>) -> bool {
        match (self.pad_def, car_position) {
            (Some(def), Some((x, y, z))) => within_snap_tolerance(&def, x, y, z),
            _ => false,
        }
    }

    fn drain_ready(&mut self, arena_slug: &'static str) -> Vec<PadEvent> {
        let mut ready: Vec<PadEvent> = Vec::new();
        let (Some(pad_def), Some(position)) = (self.pad_def, self.position) else {
            return ready;
        };

        while let Some(pending) = self.pending.pop_front() {
            let status = if pending.instigator_actor_id.is_some() {
                PadEventStatus::Collected
            } else {
                PadEventStatus::Respawned
            };
            ready.push(PadEvent {
                pad_id: pad_def.id,
                is_big: pad_def.is_big,
                pad_side: pad_def.side,
                arena: arena_slug,
                arena_supported: arena_slug != "unknown",
                object_name: self.object_name.clone(),
                position,
                timestamp: pending.timestamp,
                raw_state: pending.raw_state,
                instigator_actor_id: pending.instigator_actor_id,
                resolved_actor_id: pending.resolved_actor_id,
                status,
                snap_distance: self.snap_distance,
                snap_error_uu: self.snap_distance,
            });
        }
        ready
    }
}

/// True when `raw` is ahead of `previous`, allowing for the u8 wrapping around.
fn counter_advanced(previous: Option<u8>, raw: u8) -> bool {
    previous.map_or(true, |prev| (1..128).contains(&raw.wrapping_sub(prev)))
}

pub struct PadRegistry {
    /// Pad state by level object name. Replays re-spawn every pad actor at each
    /// checkpoint, about every 10s and often under a new actor id, so this has to
    /// outlive the actors. Pads never replicate a position either, so a pad located
    /// once stays located only if it is kept here.
    instances: HashMap<String, PadInstance>,
    /// Live actor id to its key in `instances`.
    actor_keys: HashMap<i32, String>,
    /// Active arena slug — resolved from header map name.
    arena_slug: &'static str,
    /// Pad table for the active arena (None for unsupported arenas).
    pad_table: Option<&'static [ArenaPadDef]>,
    debug_enabled: bool,
}

impl PadRegistry {
    #[allow(dead_code)]
    pub fn new() -> Self {
        Self::new_with_arena("unknown")
    }

    /// Construct a PadRegistry pre-loaded with the correct pad table for `map_name`.
    pub fn new_with_arena(map_name: &str) -> Self {
        let raw_debug = env::var("RLCOACH_DEBUG_BOOST_EVENTS").ok();
        let debug_enabled = raw_debug
            .as_deref()
            .map(|val| {
                let trimmed = val.trim();
                matches!(trimmed, "1" | "true" | "TRUE" | "True" | "on" | "ON")
            })
            .unwrap_or(false);

        let arena_slug = lookup_arena_slug(map_name).unwrap_or("unknown");
        let pad_table = pad_table_for_slug(arena_slug);

        PadRegistry {
            instances: HashMap::new(),
            actor_keys: HashMap::new(),
            arena_slug,
            pad_table,
            debug_enabled,
        }
    }

    pub fn track_new_actor(&mut self, actor_id: i32, object_name: &str) {
        if !object_name.contains("VehiclePickup_Boost_TA") {
            self.actor_keys.remove(&actor_id);
            return;
        }
        self.actor_keys.insert(actor_id, object_name.to_string());
        self.instances
            .entry(object_name.to_string())
            .or_insert_with(|| PadInstance::new(object_name));
    }

    pub fn remove_actor(&mut self, actor_id: i32) {
        self.actor_keys.remove(&actor_id);
    }

    pub fn update_position(&mut self, actor_id: i32, position: (f32, f32, f32)) -> Vec<PadEvent> {
        let Some(key) = self.actor_keys.get(&actor_id).cloned() else {
            return Vec::new();
        };
        if let Some(instance) = self.instances.get_mut(&key) {
            instance.position = Some(position);
        }
        self.assign_pad_def(&key, Some(position));
        // snap_distance is set inside assign_pad_def; no extra calculation needed here.
        self.flush_pad(&key)
    }

    pub fn handle_pickup(
        &mut self,
        actor_id: i32,
        state: PickupState,
        timestamp: f32,
        instigator_actor_id: Option<i32>,
        resolved_actor_id: Option<i32>,
        car_position: Option<(f32, f32, f32)>,
    ) -> Vec<PadEvent> {
        let key = self
            .actor_keys
            .entry(actor_id)
            .or_insert_with(|| format!("{UNTRACKED_PAD_NAME}#{actor_id}"))
            .clone();
        let instance = self
            .instances
            .entry(key.clone())
            .or_insert_with(|| PadInstance::new(UNTRACKED_PAD_NAME));

        if !instance.accepts(state, instigator_actor_id, car_position) {
            return Vec::new();
        }
        instance.last_state = Some(state.raw());
        if instigator_actor_id.is_some() {
            instance.last_collected = Some(state.raw());
        }
        instance.pending.push_back(PendingEvent {
            raw_state: state.raw(),
            timestamp,
            instigator_actor_id,
            resolved_actor_id,
        });

        self.assign_pad_def(&key, car_position);
        self.flush_pad(&key)
    }

    pub fn flush_ready_events(&mut self) -> Vec<PadEvent> {
        let arena_slug = self.arena_slug;
        let mut out = Vec::new();
        for instance in self.instances.values_mut() {
            out.extend(instance.drain_ready(arena_slug));
        }
        self.log_events(&out);
        out
    }

    fn assign_pad_def(&mut self, key: &str, fallback: Option<(f32, f32, f32)>) {
        let pad_table = self.pad_table;
        if let Some(instance) = self.instances.get_mut(key) {
            if instance.pad_def.is_none() {
                let position_hint = instance.position.as_ref().copied().or(fallback);
                if let Some((px, py, pz)) = position_hint {
                    if let Some(table) = pad_table {
                        if let Some(snap) = snap_to_pad(table, px, py, pz) {
                            let def = snap.pad_def;
                            instance.pad_def = Some(def);
                            if instance.position.is_none() {
                                instance.position = Some((def.x, def.y, def.z));
                                instance.snap_distance = Some(0.0);
                            } else {
                                instance.snap_distance = Some(snap.snap_error_uu);
                            }
                        }
                    }
                    // Unsupported arenas: do NOT assign a pad_def. Leaving pad_def as None
                    // prevents flush_actor from emitting events with fabricated Soccar
                    // metadata for non-standard maps (Hoops, Dropshot, etc.).
                }
            }
        }
    }

    fn flush_pad(&mut self, key: &str) -> Vec<PadEvent> {
        let arena_slug = self.arena_slug;
        let ready = self
            .instances
            .get_mut(key)
            .map(|instance| instance.drain_ready(arena_slug))
            .unwrap_or_default();
        self.log_events(&ready);
        ready
    }

    fn log_events(&self, events: &[PadEvent]) {
        if !self.debug_enabled {
            return;
        }
        for event in events {
            let instigator = event
                .instigator_actor_id
                .map(|id| id.to_string())
                .unwrap_or_else(|| "None".to_string());
            let resolved = event
                .resolved_actor_id
                .map(|id| id.to_string())
                .unwrap_or_else(|| "None".to_string());
            let distance = event
                .snap_distance
                .map(|d| format!("{:.3}", d))
                .unwrap_or_else(|| "None".to_string());
            let position = format!(
                "({:.1},{:.1},{:.1})",
                event.position.0, event.position.1, event.position.2
            );
            eprintln!(
                "[pad_registry] ts={:.3} pad_id={} actor_id={} instigator_actor_id={} position={} snap_distance={} state={} status={}",
                event.timestamp,
                event.pad_id,
                resolved,
                instigator,
                position,
                distance,
                event.raw_state,
                event.status.as_str()
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const PAD_OBJECT: &str = "Stadium_P.TheWorld:PersistentLevel.VehiclePickup_Boost_TA_1";
    /// Beside small pad 6 at (0, -4240), where a car really is at pickup.
    const AT_PAD: Option<(f32, f32, f32)> = Some((150.0, -4200.0, 17.0));
    const FAR_FROM_PAD: Option<(f32, f32, f32)> = Some((3000.0, 3000.0, 17.0));

    fn registry() -> PadRegistry {
        let mut registry = PadRegistry::new_with_arena("CHN_Stadium_P");
        registry.track_new_actor(80, PAD_OBJECT);
        registry
    }

    fn collect(
        registry: &mut PadRegistry,
        actor_id: i32,
        counter: u8,
        timestamp: f32,
        car: i32,
        position: Option<(f32, f32, f32)>,
    ) -> Vec<PadEvent> {
        registry.handle_pickup(
            actor_id,
            PickupState::Counter(counter),
            timestamp,
            Some(car),
            Some(car),
            position,
        )
    }

    fn respawn(registry: &mut PadRegistry, actor_id: i32, timestamp: f32) -> Vec<PadEvent> {
        registry.handle_pickup(
            actor_id,
            PickupState::Counter(255),
            timestamp,
            None,
            None,
            None,
        )
    }

    #[test]
    fn collection_identifies_pad_from_car_position() {
        let mut registry = registry();
        let events = collect(&mut registry, 80, 1, 1.0, 9, AT_PAD);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].pad_id, 6);
        assert!(!events[0].is_big);
        assert_eq!(events[0].status.as_str(), "COLLECTED");
        assert_eq!(events[0].timestamp, 1.0);
    }

    #[test]
    fn big_pad_is_identified_from_a_real_pickup_position() {
        let mut registry = registry();
        let events = collect(&mut registry, 80, 1, 1.0, 9, Some((2930.0, -4030.0, 17.0)));
        assert_eq!(events[0].pad_id, 1);
        assert!(events[0].is_big);
    }

    #[test]
    fn pad_keeps_emitting_after_checkpoint_respawn() {
        let mut registry = registry();
        collect(&mut registry, 80, 1, 1.0, 9, AT_PAD);
        respawn(&mut registry, 80, 5.0);

        registry.track_new_actor(80, PAD_OBJECT);

        let events = collect(&mut registry, 80, 3, 12.0, 9, FAR_FROM_PAD);
        assert_eq!(events.len(), 1, "a located pad needs no second car fix");
        assert_eq!(events[0].pad_id, 6);
        assert_eq!(events[0].raw_state, 3);
    }

    #[test]
    fn pad_keeps_its_state_across_a_new_actor_id() {
        let mut registry = registry();
        collect(&mut registry, 80, 1, 1.0, 9, AT_PAD);

        registry.remove_actor(80);
        registry.track_new_actor(99, PAD_OBJECT);

        assert!(collect(&mut registry, 99, 1, 10.0, 9, AT_PAD).is_empty());
        let events = respawn(&mut registry, 99, 11.0);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].status.as_str(), "RESPAWNED");
    }

    #[test]
    fn checkpoint_resends_are_ignored() {
        let mut registry = registry();
        assert_eq!(collect(&mut registry, 80, 1, 1.0, 9, AT_PAD).len(), 1);
        registry.track_new_actor(80, PAD_OBJECT);
        assert!(collect(&mut registry, 80, 1, 2.0, 9, AT_PAD).is_empty());

        assert_eq!(respawn(&mut registry, 80, 5.0).len(), 1);
        registry.track_new_actor(80, PAD_OBJECT);
        assert!(respawn(&mut registry, 80, 12.0).is_empty());
    }

    #[test]
    fn resend_with_dead_instigator_is_ignored() {
        let mut registry = registry();
        collect(&mut registry, 80, 13, 1.0, 9, AT_PAD);
        respawn(&mut registry, 80, 5.0);

        assert!(collect(&mut registry, 80, 13, 20.0, -1, None).is_empty());
        assert!(
            respawn(&mut registry, 80, 21.0).is_empty(),
            "a rejected state must not disturb re-send detection"
        );
    }

    #[test]
    fn counter_reused_after_goal_reset_counts_when_car_is_at_pad() {
        let mut registry = registry();
        collect(&mut registry, 80, 5, 1.0, 52, AT_PAD);
        respawn(&mut registry, 80, 12.0);

        let events = collect(&mut registry, 80, 5, 24.0, 99, AT_PAD);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].instigator_actor_id, Some(99));
    }

    #[test]
    fn reused_counter_with_car_elsewhere_is_ignored() {
        let mut registry = registry();
        collect(&mut registry, 80, 17, 1.0, 119, AT_PAD);
        respawn(&mut registry, 80, 5.0);

        assert!(collect(&mut registry, 80, 17, 6.0, 96, FAR_FROM_PAD).is_empty());
        assert!(collect(&mut registry, 80, 17, 7.0, 98, None).is_empty());
        assert_eq!(
            collect(&mut registry, 80, 19, 8.0, 96, FAR_FROM_PAD).len(),
            1,
            "the next advance is real wherever the car has got to"
        );
    }

    #[test]
    fn older_counter_with_car_elsewhere_is_ignored() {
        let mut registry = registry();
        collect(&mut registry, 80, 13, 1.0, 9, AT_PAD);
        respawn(&mut registry, 80, 5.0);
        assert!(collect(&mut registry, 80, 11, 6.0, 9, FAR_FROM_PAD).is_empty());
    }

    #[test]
    fn counter_advance_survives_wrapping() {
        assert!(counter_advanced(None, 1));
        assert!(counter_advanced(Some(1), 3));
        assert!(counter_advanced(Some(253), 1));
        assert!(!counter_advanced(Some(5), 5));
        assert!(!counter_advanced(Some(5), 3));
    }

    #[test]
    fn flag_pickups_collect_on_every_cycle() {
        let mut registry = registry();
        let flag = |raw| PickupState::Flag(raw);
        let events = registry.handle_pickup(80, flag(1), 1.0, Some(9), Some(9), AT_PAD);
        assert_eq!(events.len(), 1);
        assert_eq!(
            registry
                .handle_pickup(80, flag(0), 5.0, None, None, None)
                .len(),
            1
        );

        let events = registry.handle_pickup(80, flag(1), 6.0, Some(7), Some(7), None);
        assert_eq!(events.len(), 1, "flags have no counter and need no car fix");
        assert_eq!(events[0].status.as_str(), "COLLECTED");
    }

    #[test]
    fn unlocated_collection_waits_through_checkpoint_for_a_car_fix() {
        let mut registry = registry();
        assert!(collect(&mut registry, 80, 1, 1.0, 9, FAR_FROM_PAD).is_empty());

        registry.track_new_actor(80, PAD_OBJECT);

        let events = collect(&mut registry, 80, 3, 12.0, 9, AT_PAD);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].timestamp, 1.0);
        assert_eq!(events[1].timestamp, 12.0);
    }

    #[test]
    fn untracked_actors_do_not_share_state() {
        let mut registry = PadRegistry::new_with_arena("CHN_Stadium_P");
        let first = collect(&mut registry, 5, 1, 1.0, 9, AT_PAD);
        let second = collect(&mut registry, 6, 1, 2.0, 9, Some((-940.0, -3100.0, 17.0)));
        assert_eq!(first[0].pad_id, 6);
        assert_eq!(second[0].pad_id, 9);
        assert_eq!(second[0].object_name, UNTRACKED_PAD_NAME);
    }

    #[test]
    fn reused_actor_id_no_longer_feeds_the_old_pad() {
        let mut registry = registry();
        registry.track_new_actor(80, "Archetypes.Car.Car_Default");
        assert!(registry
            .update_position(80, (150.0, -4200.0, 17.0))
            .is_empty());
        assert!(registry.instances[PAD_OBJECT].position.is_none());
    }

    #[test]
    fn unsupported_arena_emits_nothing() {
        let mut registry = PadRegistry::new_with_arena("HoopsStadium_P");
        registry.track_new_actor(80, PAD_OBJECT);
        assert!(collect(&mut registry, 80, 1, 1.0, 9, AT_PAD).is_empty());
        assert!(registry.flush_ready_events().is_empty());
    }
}
