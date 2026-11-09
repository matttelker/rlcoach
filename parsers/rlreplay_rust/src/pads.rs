//! Boost pad pickups, from each pad's replicated pickup counter.
//!
//! A pad sends `NewReplicatedPickupData`: the car that took it, and a counter that
//! rises by 2 per pickup and reads 255 once the pad is back. Pads never send where
//! they are, so a pad is placed by the first car seen taking it.
//!
//! Replay checkpoints, about every 10 s, re-create every pad actor, often under a
//! new actor id, and re-send each pad's last state, sometimes an older one, naming
//! a dead (-1) or unrelated car. So a pad is known by its level object name, and a
//! state the pad already had, or one naming a dead car, isn't a pickup. A goal reset
//! puts the counter to 255 without advancing it, so the next pickup can repeat the
//! last value. That one counts only if the car is at the pad.

use std::collections::HashMap;

/// A car this close to a pad's centre is on it. Cars report their own centre, well
/// outside the pad when their hitbox touches it: 183 and 216 uu at the median for
/// small and big pads over 3,590 real pickups, 428 and 412 uu at the 99.9th
/// percentile. Pads are at least 1,061 uu apart, so the nearest is never in doubt.
const ON_PAD_UU: f32 = 450.0;

pub type Spot = (f32, f32, f32);

/// A car took a pad.
#[derive(Clone, Debug, PartialEq)]
pub struct Pickup {
    /// The pad's index in the spots the parser was given.
    pub pad: usize,
    /// When the pad was taken. It can be earlier than the frame that reports it, when
    /// the pad had to wait for a car to place it.
    pub time: f32,
    pub car: i32,
}

#[derive(Default)]
struct Pad {
    /// Where it is, once a car has placed it.
    spot: Option<usize>,
    /// Its last state, to spot a re-send.
    state: Option<u8>,
    /// The state of its last pickup, to tell a counter that advanced.
    taken: Option<u8>,
    /// Changes waiting for the pad to be placed: when, and the car if one took it.
    waiting: Vec<(f32, Option<i32>)>,
}

pub struct Pads {
    /// Each pad's centre, numbered as given. Empty for an arena whose pads aren't
    /// known, which then reports no pickups.
    spots: Vec<Spot>,
    /// Pads by level object name.
    pads: HashMap<String, Pad>,
    /// Each live pad actor's object name.
    actors: HashMap<i32, String>,
}

impl Pads {
    pub fn new(spots: Vec<Spot>) -> Self {
        Pads {
            spots,
            pads: HashMap::new(),
            actors: HashMap::new(),
        }
    }

    /// A new actor. Only pads are kept.
    pub fn add_actor(&mut self, actor: i32, object_name: &str) {
        if is_pad(object_name) {
            self.actors.insert(actor, object_name.to_string());
            self.pads.entry(object_name.to_string()).or_default();
        } else {
            self.actors.remove(&actor);
        }
    }

    pub fn remove_actor(&mut self, actor: i32) {
        self.actors.remove(&actor);
    }

    /// A pad actor sent its state. `car` took it, or is None when the pad came back,
    /// and `car_position` is where that car was. Returns the pickups this places.
    pub fn update(
        &mut self,
        actor: i32,
        counter: u8,
        time: f32,
        car: Option<i32>,
        car_position: Option<Spot>,
    ) -> Vec<Pickup> {
        let name = self
            .actors
            .entry(actor)
            .or_insert_with(|| format!("unseen pad actor {actor}"))
            .clone();
        let spots = &self.spots;
        let pad = self.pads.entry(name).or_default();
        if pad.state == Some(counter) {
            return Vec::new();
        }
        if let Some(car) = car {
            let at_pad = match (pad.spot, car_position) {
                (Some(spot), Some(position)) => distance(spots[spot], position) <= ON_PAD_UU,
                _ => false,
            };
            if car < 0 || !(advanced(pad.taken, counter) || at_pad) {
                return Vec::new();
            }
            pad.taken = Some(counter);
        }
        pad.state = Some(counter);
        pad.waiting.push((time, car));
        if pad.spot.is_none() {
            pad.spot = car_position.and_then(|position| nearest(spots, position));
        }
        let Some(spot) = pad.spot else {
            return Vec::new();
        };
        pad.waiting
            .drain(..)
            .filter_map(|(time, car)| {
                car.map(|car| Pickup {
                    pad: spot,
                    time,
                    car,
                })
            })
            .collect()
    }
}

fn is_pad(object_name: &str) -> bool {
    object_name.contains("VehiclePickup_Boost_TA")
}

/// True when `counter` is ahead of `previous`, allowing for the u8 wrapping round.
fn advanced(previous: Option<u8>, counter: u8) -> bool {
    previous.is_none_or(|previous| (1..128).contains(&counter.wrapping_sub(previous)))
}

fn distance(a: Spot, b: Spot) -> f32 {
    let (dx, dy, dz) = (b.0 - a.0, b.1 - a.1, b.2 - a.2);
    (dx * dx + dy * dy + dz * dz).sqrt()
}

/// The spot a car at `position` is on, if any.
fn nearest(spots: &[Spot], position: Spot) -> Option<usize> {
    let mut best: Option<(usize, f32)> = None;
    for (index, spot) in spots.iter().enumerate() {
        let gap = distance(*spot, position);
        if gap <= ON_PAD_UU && best.is_none_or(|(_, nearest)| gap < nearest) {
            best = Some((index, gap));
        }
    }
    best.map(|(index, _)| index)
}

#[cfg(test)]
mod tests {
    use super::*;

    const PAD_OBJECT: &str = "Stadium_P.TheWorld:PersistentLevel.VehiclePickup_Boost_TA_1";
    /// Two pads: small pad 0 at (0, -4240) and big pad 1 at (3072, -4096).
    const SPOTS: [Spot; 2] = [(0.0, -4240.0, 70.0), (3072.0, -4096.0, 73.0)];
    /// Beside pad 0, where a car really is at pickup.
    const AT_PAD: Option<Spot> = Some((150.0, -4200.0, 17.0));
    const FAR_FROM_PAD: Option<Spot> = Some((3000.0, 3000.0, 17.0));

    fn pads() -> Pads {
        let mut pads = Pads::new(SPOTS.to_vec());
        pads.add_actor(80, PAD_OBJECT);
        pads
    }

    fn take(pads: &mut Pads, counter: u8, time: f32, car: i32, at: Option<Spot>) -> Vec<Pickup> {
        pads.update(80, counter, time, Some(car), at)
    }

    fn back(pads: &mut Pads, time: f32) -> Vec<Pickup> {
        pads.update(80, 255, time, None, None)
    }

    #[test]
    fn a_pickup_is_placed_at_the_pad_the_car_is_on() {
        let mut pads = pads();
        let taken = take(&mut pads, 1, 1.0, 9, AT_PAD);
        assert_eq!(
            taken,
            vec![Pickup {
                pad: 0,
                time: 1.0,
                car: 9
            }]
        );
        let taken = pads.update(81, 1, 2.0, Some(9), Some((2930.0, -4030.0, 17.0)));
        assert_eq!(taken[0].pad, 1, "a real big pad pickup position");
    }

    #[test]
    fn a_pad_comes_back_without_a_pickup() {
        let mut pads = pads();
        take(&mut pads, 1, 1.0, 9, AT_PAD);
        assert!(back(&mut pads, 5.0).is_empty());
        assert_eq!(take(&mut pads, 3, 12.0, 9, AT_PAD).len(), 1);
    }

    #[test]
    fn a_placed_pad_stays_placed_across_a_checkpoint() {
        let mut pads = pads();
        take(&mut pads, 1, 1.0, 9, AT_PAD);
        back(&mut pads, 5.0);
        pads.add_actor(80, PAD_OBJECT);

        let taken = take(&mut pads, 3, 12.0, 9, FAR_FROM_PAD);
        assert_eq!(
            taken.len(),
            1,
            "a placed pad needs no second car to place it"
        );
        assert_eq!(taken[0].pad, 0);
    }

    #[test]
    fn a_pad_keeps_its_state_under_a_new_actor_id() {
        let mut pads = pads();
        take(&mut pads, 1, 1.0, 9, AT_PAD);
        pads.remove_actor(80);
        pads.add_actor(99, PAD_OBJECT);
        assert!(pads.update(99, 1, 10.0, Some(9), AT_PAD).is_empty());
        assert_eq!(pads.update(99, 3, 20.0, Some(9), AT_PAD).len(), 1);
    }

    #[test]
    fn checkpoint_resends_are_ignored() {
        let mut pads = pads();
        assert_eq!(take(&mut pads, 1, 1.0, 9, AT_PAD).len(), 1);
        pads.add_actor(80, PAD_OBJECT);
        assert!(take(&mut pads, 1, 2.0, 9, AT_PAD).is_empty());
    }

    #[test]
    fn a_resend_naming_a_dead_car_is_ignored_and_changes_nothing() {
        let mut pads = pads();
        take(&mut pads, 13, 1.0, 9, AT_PAD);
        back(&mut pads, 5.0);
        assert!(take(&mut pads, 13, 20.0, -1, None).is_empty());
        assert_eq!(pads.pads[PAD_OBJECT].state, Some(255));
    }

    #[test]
    fn a_repeated_counter_after_a_goal_reset_counts_when_the_car_is_at_the_pad() {
        let mut pads = pads();
        take(&mut pads, 5, 1.0, 52, AT_PAD);
        back(&mut pads, 12.0);
        assert_eq!(take(&mut pads, 5, 24.0, 99, AT_PAD)[0].car, 99);
    }

    #[test]
    fn a_repeated_counter_with_the_car_elsewhere_is_ignored() {
        let mut pads = pads();
        take(&mut pads, 17, 1.0, 119, AT_PAD);
        back(&mut pads, 5.0);
        assert!(take(&mut pads, 17, 6.0, 96, FAR_FROM_PAD).is_empty());
        assert!(take(&mut pads, 17, 7.0, 98, None).is_empty());
        assert_eq!(
            take(&mut pads, 19, 8.0, 96, FAR_FROM_PAD).len(),
            1,
            "the next advance is real wherever the car has got to"
        );
    }

    #[test]
    fn an_older_counter_with_the_car_elsewhere_is_ignored() {
        let mut pads = pads();
        take(&mut pads, 13, 1.0, 9, AT_PAD);
        back(&mut pads, 5.0);
        assert!(take(&mut pads, 11, 6.0, 9, FAR_FROM_PAD).is_empty());
    }

    #[test]
    fn the_counter_advances_through_its_wrap() {
        assert!(advanced(None, 1));
        assert!(advanced(Some(1), 3));
        assert!(advanced(Some(253), 1));
        assert!(!advanced(Some(5), 5));
        assert!(!advanced(Some(5), 3));
    }

    #[test]
    fn an_unplaced_pickup_waits_for_a_car_to_place_the_pad() {
        let mut pads = pads();
        assert!(take(&mut pads, 1, 1.0, 9, FAR_FROM_PAD).is_empty());
        pads.add_actor(80, PAD_OBJECT);
        let taken = take(&mut pads, 3, 12.0, 9, AT_PAD);
        let times: Vec<f32> = taken.iter().map(|pickup| pickup.time).collect();
        assert_eq!(times, vec![1.0, 12.0]);
    }

    #[test]
    fn pad_actors_never_created_keep_apart() {
        let mut pads = Pads::new(SPOTS.to_vec());
        let first = pads.update(5, 1, 1.0, Some(9), AT_PAD);
        let second = pads.update(6, 1, 2.0, Some(9), Some((3000.0, -4000.0, 17.0)));
        assert_eq!((first[0].pad, second[0].pad), (0, 1));
    }

    #[test]
    fn a_reused_actor_id_no_longer_feeds_its_old_pad() {
        let mut pads = pads();
        pads.add_actor(80, "Archetypes.Car.Car_Default");
        assert!(!pads.actors.contains_key(&80));
    }

    #[test]
    fn an_arena_without_known_pads_reports_nothing() {
        let mut pads = Pads::new(Vec::new());
        pads.add_actor(80, PAD_OBJECT);
        assert!(take(&mut pads, 1, 1.0, 9, AT_PAD).is_empty());
    }
}
