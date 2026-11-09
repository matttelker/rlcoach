//! Walk a replay's network frames and say, for each one, where the ball and every
//! player's car are, and what happened: pickups, flips, touches, first touches and
//! demolitions.
//!
//! A frame only carries what changed, so the walk keeps every actor's last state.
//! Actors are told apart by the object they were made from, and attributes by name.

use std::collections::{BTreeMap, HashMap, HashSet};

use boxcars::{Attribute, Frame, RigidBody, Vector3f};

use crate::pads::{Pads, Spot};
use crate::roster::Roster;

/// Where the ball sits for a kickoff, which is where it starts.
const BALL_AT_REST: Spot = (0.0, 0.0, 93.15);
/// Where a car is taken to be before it sends a position.
const CAR_UNPLACED: Spot = (0.0, 0.0, 17.0);
/// What a car holds before it sends its boost: the kickoff amount.
const KICKOFF_BOOST: i64 = 33;
/// A car whose centre is this close to the ball's touches it.
const TOUCH_UU: f32 = 200.0;
/// A car's touches this close together in time are one touch.
const TOUCH_GAP_S: f64 = 0.2;
/// And this close in place, they're one touch for twice as long.
const TOUCH_SAME_PLACE_UU: f32 = 120.0;

const PLAYER_NAME: &str = "Engine.PlayerReplicationInfo:PlayerName";
const CAR_PRI: &str = "Engine.Pawn:PlayerReplicationInfo";
const COMPONENT_CAR: &str = "TAGame.CarComponent_TA:Vehicle";
const DODGE_TORQUE: &str = "TAGame.CarComponent_Dodge_TA:DodgeTorque";
/// Boost before `ReplicatedBoost` replaced it.
const BOOST_AMOUNT: &str = "TAGame.CarComponent_Boost_TA:ReplicatedBoostAmount";
const FIRST_TOUCHES: &str = "TAGame.PRI_TA:MatchFirstTouches";

#[derive(Clone, Copy, Debug, PartialEq)]
enum Kind {
    Ball,
    Car,
    /// A car's boost, jump, flip and the like, which points at its car.
    Component,
    /// A player's replicated info.
    Pri,
    Other,
}

fn kind_of(object_name: &str) -> Kind {
    if object_name.starts_with("Archetypes.Ball.") {
        Kind::Ball
    } else if object_name.starts_with("Archetypes.Car.") {
        Kind::Car
    } else if object_name.starts_with("Archetypes.CarComponents.") {
        Kind::Component
    } else if object_name == "TAGame.Default__PRI_TA" {
        Kind::Pri
    } else {
        Kind::Other
    }
}

/// One car as the replay has it so far.
#[derive(Default)]
struct Car {
    position: Option<Spot>,
    velocity: Spot,
    /// Angular velocity, in radians a second.
    spin: Spot,
    rotation: Option<[f32; 4]>,
    boost: Option<i64>,
    /// Demolished. It stays so until the car is gone.
    demolished: bool,
    /// When and where its last touch was.
    last_touch: Option<(f64, Spot)>,
}

/// One player's car in one frame. `row` names the player (see `roster`).
#[derive(Clone, Debug, PartialEq)]
pub struct CarFrame {
    pub row: usize,
    pub team: i64,
    pub position: Spot,
    pub velocity: Spot,
    pub spin: Spot,
    /// Quaternion x, y, z, w, once the car has sent one.
    pub rotation: Option<[f32; 4]>,
    /// 0 to 100.
    pub boost: i64,
    pub demolished: bool,
}

/// One network frame, with the players by row.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct FrameOut {
    pub time: f32,
    pub ball_position: Spot,
    pub ball_velocity: Spot,
    pub cars: Vec<CarFrame>,
    /// A pad taken: its index, the player and their team, and when.
    pub pickups: Vec<(usize, usize, Option<i64>, f32)>,
    /// A flip: the player, and its torque in the car's own axes, which points the way
    /// the stick did.
    pub dodges: Vec<(usize, Spot)>,
    pub touches: Vec<usize>,
    /// The game's own first-touch counter rose for this player, up to a second
    /// after the kickoff's first touch.
    pub first_touches: Vec<usize>,
    /// The car demolished, and the one that did it.
    pub demos: Vec<(usize, Option<usize>)>,
}

pub struct Game<'a> {
    objects: &'a [String],
    attributes: Attributes,
    kinds: HashMap<i32, Kind>,
    cars: BTreeMap<i32, Car>,
    /// Each component's car.
    component_car: HashMap<i32, i32>,
    ball: Option<i32>,
    ball_position: Spot,
    ball_velocity: Spot,
    roster: Roster,
    pads: Pads,
    /// Each PRI's first-touch count. The game keeps re-sending it.
    first_touch_counts: HashMap<i32, i32>,
}

/// The object ids of the attributes the walk reads, where the replay has them.
#[derive(Clone, Copy)]
struct Attributes {
    player_name: Option<usize>,
    car_pri: Option<usize>,
    component_car: Option<usize>,
    dodge_torque: Option<usize>,
    boost_amount: Option<usize>,
    first_touches: Option<usize>,
}

impl Attributes {
    fn new(objects: &[String]) -> Self {
        let id = |name: &str| objects.iter().position(|object| object == name);
        Attributes {
            player_name: id(PLAYER_NAME),
            car_pri: id(CAR_PRI),
            component_car: id(COMPONENT_CAR),
            dodge_torque: id(DODGE_TORQUE),
            boost_amount: id(BOOST_AMOUNT),
            first_touches: id(FIRST_TOUCHES),
        }
    }
}

/// Every name the replay's PRIs send.
pub fn stream_names(objects: &[String], frames: &[Frame]) -> HashSet<String> {
    let Some(player_name) = Attributes::new(objects).player_name else {
        return HashSet::new();
    };
    frames
        .iter()
        .flat_map(|frame| &frame.updated_actors)
        .filter_map(|update| match &update.attribute {
            Attribute::String(name) if object_index(update.object_id) == player_name => {
                Some(name.clone())
            }
            _ => None,
        })
        .collect()
}

fn object_index(id: boxcars::ObjectId) -> usize {
    i32::from(id) as usize
}

fn spot(vector: Vector3f) -> Spot {
    (vector.x, vector.y, vector.z)
}

fn distance(a: Spot, b: Spot) -> f32 {
    let (dx, dy, dz) = (a.0 - b.0, a.1 - b.1, a.2 - b.2);
    (dx * dx + dy * dy + dz * dz).sqrt()
}

/// A boost byte (0 to 255) as 0 to 100.
fn boost_percent(raw: u8) -> i64 {
    ((f64::from(raw) * (100.0 / 255.0)).round() as i64).clamp(0, 100)
}

impl<'a> Game<'a> {
    /// `rows` are the header's players, and `pad_spots` the arena's pads, numbered.
    pub fn new(
        objects: &'a [String],
        rows: Vec<(String, i64)>,
        stream_names: &HashSet<String>,
        pad_spots: Vec<Spot>,
    ) -> Self {
        Game {
            objects,
            attributes: Attributes::new(objects),
            kinds: HashMap::new(),
            cars: BTreeMap::new(),
            component_car: HashMap::new(),
            ball: None,
            ball_position: BALL_AT_REST,
            ball_velocity: (0.0, 0.0, 0.0),
            roster: Roster::new(rows, stream_names),
            pads: Pads::new(pad_spots),
            first_touch_counts: HashMap::new(),
        }
    }

    /// Read one network frame, in order, and say what it shows.
    pub fn step(&mut self, frame: &Frame) -> FrameOut {
        for actor in &frame.deleted_actors {
            self.remove(i32::from(*actor));
        }
        let objects = self.objects;
        for actor in &frame.new_actors {
            self.add(
                i32::from(actor.actor_id),
                &objects[object_index(actor.object_id)],
            );
        }
        let mut events = Events::default();
        for update in &frame.updated_actors {
            let actor = i32::from(update.actor_id);
            let attribute = Some(object_index(update.object_id));
            self.update(actor, attribute, &update.attribute, frame.time, &mut events);
        }
        self.finish(frame.time, events)
    }

    fn remove(&mut self, actor: i32) {
        if let Some(car) = self.cars.remove(&actor) {
            self.roster.remove_car(actor, car.position);
        }
        if self.ball == Some(actor) {
            self.place_ball(None);
        }
        self.kinds.remove(&actor);
        self.component_car
            .retain(|component, car| *component != actor && *car != actor);
        self.pads.remove_actor(actor);
    }

    fn add(&mut self, actor: i32, object_name: &str) {
        let kind = kind_of(object_name);
        self.kinds.insert(actor, kind);
        match kind {
            Kind::Ball => self.place_ball(Some(actor)),
            Kind::Car => {
                self.cars.entry(actor).or_default();
                self.roster.add_car(actor);
            }
            _ => {}
        }
        self.pads.add_actor(actor, object_name);
    }

    /// A new ball, or none, back at the centre and still.
    fn place_ball(&mut self, ball: Option<i32>) {
        self.ball = ball;
        self.ball_position = BALL_AT_REST;
        self.ball_velocity = (0.0, 0.0, 0.0);
    }

    fn kind(&self, actor: i32) -> Kind {
        self.kinds.get(&actor).copied().unwrap_or(Kind::Other)
    }

    /// The car a component belongs to, or the actor itself.
    fn car_of(&self, actor: i32) -> i32 {
        let mut car = actor;
        // Components point straight at their car. The limit guards against a loop
        for _ in 0..8 {
            match self.component_car.get(&car) {
                Some(owner) if *owner != car => car = *owner,
                _ => break,
            }
        }
        car
    }

    fn update(
        &mut self,
        actor: i32,
        attribute: Option<usize>,
        value: &Attribute,
        time: f32,
        events: &mut Events,
    ) {
        let names = self.attributes;
        match value {
            Attribute::RigidBody(body) => self.move_actor(actor, body),
            Attribute::ActiveActor(link) if attribute == names.car_pri => {
                if !link.active {
                    self.roster.unlink(actor);
                } else if self.kind(actor) == Kind::Car {
                    let pri = i32::from(link.actor);
                    let is_pri = self.kind(pri) == Kind::Pri;
                    self.roster.link(actor, pri, is_pri);
                }
            }
            Attribute::ActiveActor(link) if attribute == names.component_car => {
                if self.kind(actor) == Kind::Component {
                    self.component_car.insert(actor, i32::from(link.actor));
                }
            }
            Attribute::String(name) if attribute == names.player_name => {
                if self.kind(actor) == Kind::Pri {
                    self.roster.name(actor, name);
                }
            }
            Attribute::TeamPaint(paint) => self.roster.paint(actor, paint.team),
            Attribute::ReplicatedBoost(boost) => self.set_boost(actor, boost.boost_amount),
            Attribute::Byte(raw) if attribute == names.boost_amount => self.set_boost(actor, *raw),
            Attribute::Location(torque) if attribute == names.dodge_torque => {
                events.dodges.push((self.car_of(actor), spot(*torque)));
            }
            Attribute::Int(count) if attribute == names.first_touches => {
                // Only a step of one is a new first touch. A PRI's first count is the
                // 1 from its first touch, so an unseen count is 0
                let seen = self.first_touch_counts.insert(actor, *count);
                if *count == seen.unwrap_or(0) + 1 {
                    events.first_touches.push(actor);
                }
            }
            Attribute::PickupNew(pickup) => {
                let car = pickup.instigator.map(|car| self.car_of(i32::from(car)));
                let at = car
                    .and_then(|car| self.cars.get(&car))
                    .and_then(|car| car.position);
                let taken = self.pads.update(actor, pickup.picked_up, time, car, at);
                events.pickups.extend(taken);
            }
            Attribute::Demolish(demo) => {
                let victim = if demo.victim_flag {
                    i32::from(demo.victim)
                } else {
                    actor
                };
                let attacker = demo.attacker_flag.then(|| i32::from(demo.attacker));
                self.demolish(victim, attacker, events);
            }
            Attribute::DemolishFx(demo) => {
                let victim = if demo.victim_flag {
                    i32::from(demo.victim)
                } else {
                    actor
                };
                let attacker = demo.attacker_flag.then(|| i32::from(demo.attacker));
                self.demolish(victim, attacker, events);
            }
            Attribute::DemolishExtended(demo) => {
                let victim = if demo.victim.active {
                    i32::from(demo.victim.actor)
                } else {
                    actor
                };
                let attacker = demo.attacker.active.then(|| i32::from(demo.attacker.actor));
                self.demolish(victim, attacker, events);
            }
            _ => {}
        }
    }

    fn move_actor(&mut self, actor: i32, body: &RigidBody) {
        let zero = Vector3f {
            x: 0.0,
            y: 0.0,
            z: 0.0,
        };
        let velocity = spot(body.linear_velocity.unwrap_or(zero));
        match self.kind(actor) {
            Kind::Ball => {
                self.ball = Some(actor);
                self.ball_position = spot(body.location);
                self.ball_velocity = velocity;
            }
            Kind::Car => {
                if let Some(car) = self.cars.get_mut(&actor) {
                    // The stream sends angular velocity in hundredths of a radian
                    let spin = spot(body.angular_velocity.unwrap_or(zero));
                    let q = body.rotation;
                    car.position = Some(spot(body.location));
                    car.velocity = velocity;
                    car.spin = (spin.0 / 100.0, spin.1 / 100.0, spin.2 / 100.0);
                    car.rotation = Some([q.x, q.y, q.z, q.w]);
                }
            }
            _ => {}
        }
    }

    fn set_boost(&mut self, component: i32, raw: u8) {
        let car = self.car_of(component);
        if let Some(car) = self.cars.get_mut(&car) {
            car.boost = Some(boost_percent(raw));
        }
    }

    fn demolish(&mut self, victim: i32, attacker: Option<i32>, events: &mut Events) {
        if let Some(car) = self.cars.get_mut(&victim) {
            car.demolished = true;
        }
        events.demos.push((victim, attacker));
    }

    /// The frame as the rest of the code reads it, once every update is in.
    fn finish(&mut self, time: f32, events: Events) -> FrameOut {
        let mut cars: BTreeMap<usize, CarFrame> = BTreeMap::new();
        let actors: Vec<i32> = self.cars.keys().copied().collect();
        for actor in actors {
            let car = &self.cars[&actor];
            let team = self.roster.team(actor);
            if car.position.is_none() && car.boost.is_none() && team.is_none() {
                continue; // Nothing sent yet
            }
            let position = car.position.unwrap_or(CAR_UNPLACED);
            let team = team.unwrap_or(if position.1 > 0.0 { 1 } else { 0 });
            let row = match self.roster.row(actor) {
                Some(row) => Some(row),
                None => self.roster.seat_unseated(actor, team),
            };
            let Some(row) = row else {
                continue;
            };
            // Seating a car can take its row from a car already listed this frame
            cars.insert(
                row,
                CarFrame {
                    row,
                    team,
                    position,
                    velocity: car.velocity,
                    spin: car.spin,
                    rotation: car.rotation,
                    boost: car.boost.unwrap_or(KICKOFF_BOOST),
                    demolished: car.demolished,
                },
            );
        }
        let touches = self.touches(f64::from(time));
        let roster = &self.roster;
        FrameOut {
            time,
            ball_position: self.ball_position,
            ball_velocity: self.ball_velocity,
            cars: cars.into_values().collect(),
            pickups: events
                .pickups
                .iter()
                .filter_map(|p| {
                    let row = roster.collector(p.car)?;
                    Some((p.pad, row, roster.team(p.car), p.time))
                })
                .collect(),
            dodges: events
                .dodges
                .iter()
                .filter_map(|(car, torque)| Some((roster.row(*car)?, *torque)))
                .collect(),
            touches,
            first_touches: events
                .first_touches
                .iter()
                .filter_map(|pri| roster.header_row(*pri))
                .collect(),
            demos: events
                .demos
                .iter()
                .filter_map(|(victim, attacker)| {
                    Some((roster.row(*victim)?, attacker.and_then(|a| roster.row(a))))
                })
                .collect(),
        }
    }

    /// Players whose car came within reach of the ball, once per touch.
    fn touches(&mut self, now: f64) -> Vec<usize> {
        let mut touches = Vec::new();
        for (actor, car) in self.cars.iter_mut() {
            let Some(position) = car.position else {
                continue;
            };
            if distance(position, self.ball_position) >= TOUCH_UU {
                continue;
            }
            if let Some((then, there)) = car.last_touch {
                let gap = now - then;
                let same_place = distance(position, there) <= TOUCH_SAME_PLACE_UU;
                if gap < TOUCH_GAP_S || (same_place && gap < TOUCH_GAP_S * 2.0) {
                    continue;
                }
            }
            if let Some(row) = self.roster.row(*actor) {
                touches.push(row);
                car.last_touch = Some((now, position));
            }
        }
        touches
    }
}

/// What happened during one frame, by actor, until the frame's players are known.
#[derive(Default)]
struct Events {
    pickups: Vec<crate::pads::Pickup>,
    dodges: Vec<(i32, Spot)>,
    first_touches: Vec<i32>,
    demos: Vec<(i32, Option<i32>)>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use boxcars::{
        ActiveActor, ActorId, DemolishFx, NewActor, ObjectId, PickupNew, Quaternion,
        ReplicatedBoost, StreamId, Trajectory, UpdatedAttribute,
    };

    const BALL: i32 = 0;
    const CAR: i32 = 1;
    const COMPONENT: i32 = 2;
    const PRI: i32 = 3;
    const PAD: i32 = 4;
    const BALL_OBJECT: &str = "Archetypes.Ball.Ball_Default";
    const CAR_OBJECT: &str = "Archetypes.Car.Car_Default";
    const COMPONENT_OBJECT: &str = "Archetypes.CarComponents.CarComponent_Boost";
    const PRI_OBJECT: &str = "TAGame.Default__PRI_TA";
    const PAD_OBJECT: &str = "Stadium_P.TheWorld:PersistentLevel.VehiclePickup_Boost_TA_1";
    const RIGID_BODY: &str = "TAGame.RBActor_TA:ReplicatedRBState";
    const BOOST: &str = "TAGame.CarComponent_Boost_TA:ReplicatedBoost";
    const PICKUP: &str = "TAGame.VehiclePickup_TA:NewReplicatedPickupData";
    const DEMOLISH: &str = "TAGame.Car_TA:ReplicatedDemolishGoalExplosion";
    const PAD_SPOT: Spot = (150.0, 0.0, 70.0);
    const ZERO: Vector3f = Vector3f {
        x: 0.0,
        y: 0.0,
        z: 0.0,
    };

    /// A replay's frames, written one update at a time.
    struct Script {
        objects: Vec<String>,
        frames: Vec<Frame>,
    }

    impl Script {
        fn new() -> Self {
            let objects = [
                BALL_OBJECT,
                CAR_OBJECT,
                COMPONENT_OBJECT,
                PRI_OBJECT,
                PAD_OBJECT,
                PLAYER_NAME,
                CAR_PRI,
                COMPONENT_CAR,
                DODGE_TORQUE,
                FIRST_TOUCHES,
                RIGID_BODY,
                BOOST,
                PICKUP,
                DEMOLISH,
            ];
            Script {
                objects: objects.map(String::from).to_vec(),
                frames: Vec::new(),
            }
        }

        fn object(&self, name: &str) -> ObjectId {
            ObjectId(self.objects.iter().position(|o| o == name).unwrap() as i32)
        }

        fn frame(&mut self, time: f32) -> &mut Self {
            self.frames.push(Frame {
                time,
                delta: 0.0,
                new_actors: Vec::new(),
                deleted_actors: Vec::new(),
                updated_actors: Vec::new(),
            });
            self
        }

        fn spawn(&mut self, actor: i32, object_name: &str) -> &mut Self {
            let object_id = self.object(object_name);
            self.frames.last_mut().unwrap().new_actors.push(NewActor {
                actor_id: ActorId(actor),
                name_id: None,
                object_id,
                initial_trajectory: Trajectory {
                    location: None,
                    rotation: None,
                },
            });
            self
        }

        fn delete(&mut self, actor: i32) -> &mut Self {
            let frame = self.frames.last_mut().unwrap();
            frame.deleted_actors.push(ActorId(actor));
            self
        }

        fn set(&mut self, actor: i32, attribute_name: &str, attribute: Attribute) -> &mut Self {
            let object_id = self.object(attribute_name);
            let frame = self.frames.last_mut().unwrap();
            frame.updated_actors.push(UpdatedAttribute {
                actor_id: ActorId(actor),
                stream_id: StreamId(0),
                object_id,
                attribute,
            });
            self
        }

        /// The actor at `at`, moving along x and spinning at 5.5 rad/s.
        fn place(&mut self, actor: i32, at: Spot) -> &mut Self {
            let body = RigidBody {
                sleeping: false,
                location: Vector3f {
                    x: at.0,
                    y: at.1,
                    z: at.2,
                },
                rotation: Quaternion {
                    x: 0.0,
                    y: 0.0,
                    z: 0.0,
                    w: 1.0,
                },
                linear_velocity: Some(Vector3f {
                    x: 100.0,
                    y: 0.0,
                    z: 0.0,
                }),
                angular_velocity: Some(Vector3f {
                    x: 0.0,
                    y: 0.0,
                    z: 550.0,
                }),
            };
            self.set(actor, RIGID_BODY, Attribute::RigidBody(body))
        }

        fn link(&mut self, actor: i32, attribute_name: &str, to: i32) -> &mut Self {
            let link = ActiveActor {
                active: true,
                actor: ActorId(to),
            };
            self.set(actor, attribute_name, Attribute::ActiveActor(link))
        }

        /// Me, the header's row 0 on blue, with my car, its boost and the ball, all
        /// placed, and a pad.
        fn kickoff(&mut self) -> &mut Self {
            let full = ReplicatedBoost {
                grant_count: 0,
                boost_amount: 255,
                unused1: 0,
                unused2: 0,
            };
            self.frame(0.0)
                .spawn(BALL, BALL_OBJECT)
                .spawn(PRI, PRI_OBJECT)
                .spawn(CAR, CAR_OBJECT)
                .spawn(COMPONENT, COMPONENT_OBJECT)
                .spawn(PAD, PAD_OBJECT)
                .set(PRI, PLAYER_NAME, Attribute::String("Me".into()))
                .link(CAR, CAR_PRI, PRI)
                .link(COMPONENT, COMPONENT_CAR, CAR)
                .place(BALL, BALL_AT_REST)
                .place(CAR, (2000.0, -2000.0, 17.0))
                .set(COMPONENT, BOOST, Attribute::ReplicatedBoost(full))
        }

        fn run(&self) -> Vec<FrameOut> {
            let rows = vec![("Me".to_string(), 0), ("Them".to_string(), 1)];
            let names = stream_names(&self.objects, &self.frames);
            let mut game = Game::new(&self.objects, rows, &names, vec![PAD_SPOT]);
            self.frames.iter().map(|frame| game.step(frame)).collect()
        }
    }

    #[test]
    fn a_car_reports_as_its_pris_row_with_its_state() {
        let out = Script::new().kickoff().run();
        let car = &out[0].cars[0];
        assert_eq!((car.row, car.team, car.boost), (0, 0, 100));
        assert_eq!(car.position, (2000.0, -2000.0, 17.0));
        assert_eq!(car.velocity, (100.0, 0.0, 0.0));
        assert_eq!(car.spin, (0.0, 0.0, 5.5), "the stream sends hundredths");
        assert_eq!(car.rotation, Some([0.0, 0.0, 0.0, 1.0]));
        assert_eq!(out[0].ball_velocity, (100.0, 0.0, 0.0));
    }

    #[test]
    fn a_car_without_a_pri_takes_a_free_row_of_the_half_its_on() {
        let mut script = Script::new();
        script.frame(0.0).spawn(CAR, CAR_OBJECT);
        script.frame(0.1).place(CAR, (0.0, 3000.0, 17.0));
        let out = script.run();
        assert!(out[0].cars.is_empty(), "a car that has sent nothing");
        let car = &out[1].cars[0];
        assert_eq!((car.row, car.team, car.boost), (1, 1, KICKOFF_BOOST));
    }

    #[test]
    fn a_touch_counts_once_until_the_car_comes_back() {
        let mut script = Script::new();
        script.kickoff();
        for time in [0.1, 0.2, 0.35, 0.55] {
            script.frame(time).place(CAR, (100.0, 0.0, 93.15));
        }
        let touches: Vec<usize> = script.run().iter().map(|f| f.touches.len()).collect();
        // Again after 0.2 s, or after 0.4 s in the same place
        assert_eq!(touches, vec![0, 1, 0, 0, 1]);
    }

    #[test]
    fn flips_pickups_first_touches_and_demos_name_the_player() {
        let torque = Vector3f {
            x: 0.0,
            y: 2.24,
            z: 0.0,
        };
        let pickup = PickupNew {
            instigator: Some(ActorId(CAR)),
            picked_up: 1,
        };
        let demo = DemolishFx {
            custom_demo_flag: false,
            custom_demo_id: 0,
            attacker_flag: false,
            attacker: ActorId(-1),
            victim_flag: true,
            victim: ActorId(CAR),
            attack_velocity: ZERO,
            victim_velocity: ZERO,
        };
        let mut script = Script::new();
        script
            .kickoff()
            .frame(0.1)
            .place(CAR, (100.0, 0.0, 17.0))
            .set(COMPONENT, DODGE_TORQUE, Attribute::Location(torque))
            .set(PRI, FIRST_TOUCHES, Attribute::Int(1))
            .set(PAD, PICKUP, Attribute::PickupNew(pickup))
            .frame(0.2)
            .set(PRI, FIRST_TOUCHES, Attribute::Int(1))
            .set(CAR, DEMOLISH, Attribute::DemolishFx(Box::new(demo)));
        let out = script.run();
        assert_eq!(out[1].dodges, vec![(0, (0.0, 2.24, 0.0))]);
        assert_eq!(out[1].first_touches, vec![0]);
        assert_eq!(out[1].pickups, vec![(0, 0, Some(0), 0.1)]);
        assert!(
            out[2].first_touches.is_empty(),
            "a re-sent count is no rise"
        );
        assert_eq!(out[2].demos, vec![(0, None)]);
        assert!(out[2].cars[0].demolished);
    }

    #[test]
    fn a_deleted_ball_is_back_at_rest_and_a_deleted_car_is_gone() {
        let mut script = Script::new();
        script
            .kickoff()
            .frame(0.1)
            .place(BALL, (500.0, 500.0, 300.0));
        script.frame(0.2).delete(CAR).delete(BALL);
        let out = script.run();
        assert_eq!(out[1].ball_position, (500.0, 500.0, 300.0));
        assert!(out[2].cars.is_empty());
        assert_eq!(out[2].ball_position, BALL_AT_REST);
        assert_eq!(out[2].ball_velocity, (0.0, 0.0, 0.0));
    }

    #[test]
    fn boost_bytes_read_as_a_percentage() {
        assert_eq!(boost_percent(255), 100);
        assert_eq!(boost_percent(85), 33);
        assert_eq!(boost_percent(0), 0);
    }

    #[test]
    fn actors_are_told_apart_by_their_object() {
        assert_eq!(kind_of("Archetypes.Ball.Ball_BasketBall"), Kind::Ball);
        assert_eq!(kind_of(CAR_OBJECT), Kind::Car);
        assert_eq!(
            kind_of("Archetypes.CarComponents.CarComponent_Dodge"),
            Kind::Component
        );
        assert_eq!(kind_of(PRI_OBJECT), Kind::Pri);
        assert_eq!(
            kind_of("TAGame.Default__CameraSettingsActor_TA"),
            Kind::Other
        );
    }
}
