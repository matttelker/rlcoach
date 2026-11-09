//! Which player each car is.
//!
//! The header's `PlayerStats` rows number the players who finished the match, and a
//! car is called after its player's row. A car points at its player's PRI (the
//! actor holding the player's replicated info), and the PRI sends the player's name,
//! which picks the row. `PlayerStats` leaves out leavers and the bots that replaced
//! them, so a PRI no row names gets a number past the rows.
//!
//! The PRI's name can arrive after its car, and a player renamed mid-match has a
//! name no row carries. So rows no PRI will claim are free for any car of the team,
//! while every other row waits for its own PRI.

use std::collections::{BTreeMap, HashMap, HashSet};

/// What the roster knows about one car.
#[derive(Clone, Debug, Default)]
pub struct Seat {
    /// The car's PRI, while the game links them.
    pub pri: Option<i32>,
    /// The game cleared the link. A demolished car stays about 5 s and its
    /// replacement comes after 3 s, so for 2 s a player has two cars. The wreck keeps
    /// reporting until then, but can't take the player back or claim a free row.
    pub unlinked: bool,
    /// The row the car reports as.
    pub row: Option<usize>,
    /// The car's team: its paint, or its row's once its PRI names the row.
    pub team: Option<i64>,
}

pub struct Roster {
    /// Each `PlayerStats` row's name and team.
    rows: Vec<(String, i64)>,
    /// The row each PRI plays as. It outlives the PRI, so a row its PRI held never
    /// goes back to the free rows.
    pri_row: HashMap<i32, usize>,
    /// Rows a car can take by its team alone, in order, for teams 0 and 1.
    free: HashMap<i64, Vec<usize>>,
    /// The next number past the rows, for a PRI no row names.
    next_extra: usize,
    /// Every live car, by actor id.
    seats: BTreeMap<i32, Seat>,
}

impl Roster {
    /// `stream_names` is every name the replay's PRIs send.
    pub fn new(rows: Vec<(String, i64)>, stream_names: &HashSet<String>) -> Self {
        let mut free = HashMap::from([(0, Vec::new()), (1, Vec::new())]);
        for (row, (name, team)) in rows.iter().enumerate() {
            let claimed = stream_names.contains(name) && unique_row(&rows, name) == Some(row);
            if !claimed {
                free.entry(if *team == 0 { 0 } else { 1 })
                    .or_default()
                    .push(row);
            }
        }
        Roster {
            next_extra: rows.len(),
            rows,
            pri_row: HashMap::new(),
            free,
            seats: BTreeMap::new(),
        }
    }

    /// The row a car reports as.
    pub fn row(&self, car: i32) -> Option<usize> {
        self.seats.get(&car).and_then(|seat| seat.row)
    }

    pub fn team(&self, car: i32) -> Option<i64> {
        self.seats.get(&car).and_then(|seat| seat.team)
    }

    /// The row a car's pickups count for: the one it reports as, else its PRI's. Bots
    /// reuse names, so two PRIs can share a row while only one of their cars holds it.
    pub fn collector(&self, car: i32) -> Option<usize> {
        let seat = self.seats.get(&car)?;
        seat.row
            .or_else(|| seat.pri.and_then(|pri| self.pri_row.get(&pri).copied()))
    }

    /// The row a PRI plays as: its header row, or a number past them.
    pub fn pri_row(&self, pri: i32) -> Option<usize> {
        self.pri_row.get(&pri).copied()
    }

    /// The header row a PRI plays as, if it has one.
    pub fn header_row(&self, pri: i32) -> Option<usize> {
        self.pri_row(pri).filter(|row| *row < self.rows.len())
    }

    pub fn add_car(&mut self, car: i32) {
        self.seats.entry(car).or_default();
    }

    /// The car is gone. Its row goes back to the free rows unless a PRI holds it.
    /// `position` places a car with no team on the half it was in.
    pub fn remove_car(&mut self, car: i32, position: Option<(f32, f32, f32)>) {
        let Some(seat) = self.seats.remove(&car) else {
            return;
        };
        let Some(row) = seat.row else {
            return;
        };
        let team = seat
            .team
            .or_else(|| self.row_team(row))
            .or_else(|| position.map(|(_, y, _)| if y > 0.0 { 1 } else { 0 }));
        let held = self.pri_row.values().any(|held| *held == row);
        if let (false, Some(team)) = (held, team) {
            if let Some(queue) = self.free.get_mut(&team) {
                queue.push(row);
            }
        }
    }

    /// The game links a car to an actor. Only a PRI makes it a player's car.
    pub fn link(&mut self, car: i32, pri: i32, is_pri: bool) {
        if !(is_pri || self.pri_row.contains_key(&pri)) {
            return;
        }
        let Some(seat) = self.seats.get_mut(&car) else {
            return;
        };
        seat.pri = Some(pri);
        seat.unlinked = false;
        if let Some(row) = self.pri_row.get(&pri).copied() {
            self.take_row(car, row);
        }
    }

    /// The game cleared a car's link to its PRI.
    pub fn unlink(&mut self, car: i32) {
        if let Some(seat) = self.seats.get_mut(&car) {
            seat.pri = None;
            seat.unlinked = true;
        }
    }

    /// A PRI sent its player's name. A name only one row carries gives the PRI that
    /// row, and its car too.
    pub fn name(&mut self, pri: i32, name: &str) {
        let Some(row) = unique_row(&self.rows, name) else {
            return;
        };
        self.pri_row.insert(pri, row);
        let cars: Vec<i32> = self
            .seats
            .iter()
            .filter(|(_, seat)| seat.pri == Some(pri))
            .map(|(car, _)| *car)
            .collect();
        for car in cars {
            self.take_row(car, row);
        }
    }

    /// A car sent its paint, which carries its team.
    pub fn paint(&mut self, car: i32, team: u8) {
        let Some(seat) = self.seats.get_mut(&car) else {
            return;
        };
        seat.team = Some(i64::from(team.min(1)));
        let (row, pri) = (seat.row, seat.pri);
        let row = match row {
            Some(row) => Some(row),
            None => {
                let row = pri.and_then(|pri| self.pri_row.get(&pri).copied());
                if let Some(row) = row {
                    self.bind(car, row);
                }
                row
            }
        };
        self.row_team_for_linked(car, row);
    }

    /// Seat a car that reports as nobody yet, at the end of a frame. Cars are seated
    /// in actor id order. `team` is the car's team, or the half it's on.
    ///
    /// A car takes its PRI's row. A PRI without one takes a free row of the team, or
    /// failing that a number past the rows, and keeps it for its later cars. A car
    /// with no PRI can take a free row, and a wreck takes nothing.
    pub fn seat_unseated(&mut self, car: i32, team: i64) -> Option<usize> {
        let seat = self.seats.get(&car)?;
        if seat.unlinked {
            return None;
        }
        let pri = seat.pri;
        let row = match pri.and_then(|pri| self.pri_row.get(&pri).copied()) {
            Some(row) => row,
            None => {
                let row = match (self.pop_free(team), pri) {
                    (Some(row), _) => row,
                    (None, Some(_)) => {
                        self.next_extra += 1;
                        self.next_extra - 1
                    }
                    (None, None) => return None,
                };
                if let Some(pri) = pri {
                    self.pri_row.insert(pri, row);
                }
                row
            }
        };
        self.bind(car, row);
        self.row_team_for_linked(car, Some(row));
        Some(row)
    }

    fn row_team(&self, row: usize) -> Option<i64> {
        self.rows.get(row).map(|(_, team)| *team)
    }

    /// A car linked to its PRI plays for its row's team.
    fn row_team_for_linked(&mut self, car: i32, row: Option<usize>) {
        let team = row.and_then(|row| self.row_team(row));
        if let (Some(seat), Some(team)) = (self.seats.get_mut(&car), team) {
            if seat.pri.is_some() {
                seat.team = Some(team);
            }
        }
    }

    /// Give a linked car its PRI's row and that row's team.
    fn take_row(&mut self, car: i32, row: usize) {
        self.bind(car, row);
        if let (Some(seat), Some(team)) = (self.seats.get_mut(&car), self.rows.get(row)) {
            seat.team = Some(team.1);
        }
    }

    /// The car reports as `row`, and no other car does.
    fn bind(&mut self, car: i32, row: usize) {
        for queue in self.free.values_mut() {
            queue.retain(|free| *free != row);
        }
        for (other, seat) in self.seats.iter_mut() {
            if *other != car && seat.row == Some(row) {
                seat.row = None;
            }
        }
        if let Some(seat) = self.seats.get_mut(&car) {
            seat.row = Some(row);
        }
    }

    /// The first free row of the team that no car holds.
    fn pop_free(&mut self, team: i64) -> Option<usize> {
        let held: HashSet<usize> = self.seats.values().filter_map(|seat| seat.row).collect();
        let queue = self.free.get_mut(&team)?;
        while !queue.is_empty() {
            let row = queue.remove(0);
            if !held.contains(&row) {
                return Some(row);
            }
        }
        None
    }
}

/// The row with this name, if no other row has it too.
fn unique_row(rows: &[(String, i64)], name: &str) -> Option<usize> {
    let mut matches = rows
        .iter()
        .enumerate()
        .filter(|(_, (row_name, _))| row_name == name);
    let (row, _) = matches.next()?;
    matches.next().is_none().then_some(row)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn roster(rows: &[(&str, i64)], stream_names: &[&str]) -> Roster {
        let rows = rows.iter().map(|(n, t)| (n.to_string(), *t)).collect();
        let names = stream_names.iter().map(|n| n.to_string()).collect();
        Roster::new(rows, &names)
    }

    /// A car linked to a PRI, as the game sends it.
    fn car(roster: &mut Roster, car: i32, pri: i32) {
        roster.add_car(car);
        roster.link(car, pri, true);
    }

    /// The end of a frame: each car not yet seated, in actor id order.
    fn end_frame(roster: &mut Roster, team: i64) {
        let cars: Vec<i32> = roster.seats.keys().copied().collect();
        for car in cars {
            if roster.row(car).is_none() {
                roster.seat_unseated(car, team);
            }
        }
    }

    #[test]
    fn a_named_pri_gives_its_car_the_row_and_its_team() {
        let mut r = roster(&[("Ann", 0), ("Bo", 1)], &["Ann", "Bo"]);
        car(&mut r, 10, 5);
        r.name(5, "Bo");
        assert_eq!(r.row(10), Some(1));
        assert_eq!(r.team(10), Some(1));
        assert_eq!(r.header_row(5), Some(1));
    }

    #[test]
    fn the_respawned_car_keeps_the_player_while_the_wreck_lingers() {
        // E8D9: car 149 is demolished, car 141 spawns 3 s later and 149 goes 2 s after
        let mut r = roster(
            &[("A", 0), ("B", 0), ("C", 1), ("D", 1)],
            &["A", "B", "C", "D"],
        );
        car(&mut r, 149, 47);
        r.name(47, "D");
        assert_eq!(r.row(149), Some(3));

        r.unlink(149);
        end_frame(&mut r, 1);
        assert_eq!(r.row(149), Some(3), "the wreck reports until it's replaced");

        car(&mut r, 141, 47);
        for _ in 0..3 {
            end_frame(&mut r, 1);
            assert_eq!(r.row(141), Some(3));
            assert_eq!(r.row(149), None);
        }
        assert_eq!(r.collector(141), Some(3));
    }

    #[test]
    fn an_unlinked_wreck_takes_no_free_row() {
        let mut r = roster(&[("Gone", 0)], &[]);
        r.add_car(149);
        r.unlink(149);
        end_frame(&mut r, 0);
        assert_eq!(r.row(149), None);
        assert_eq!(r.free[&0], vec![0]);
    }

    #[test]
    fn a_player_missing_from_the_header_gets_a_number_past_the_rows() {
        // D5B7: PRI 80 left before the end, so PlayerStats has no row for it
        let mut r = roster(
            &[("A", 0), ("B", 0), ("C", 0), ("D", 1), ("E", 1), ("F", 1)],
            &["A", "B", "C", "D", "E", "F"],
        );
        car(&mut r, 85, 80);
        end_frame(&mut r, 0);
        assert_eq!(r.row(85), Some(6));

        // A later car of the same PRI is the same player, and a second leaver isn't
        r.remove_car(85, None);
        car(&mut r, 176, 80);
        car(&mut r, 19, 43);
        end_frame(&mut r, 0);
        assert_eq!(r.row(176), Some(6));
        assert_eq!(r.row(19), Some(7));
        assert_eq!(r.collector(176), Some(6));
        assert_eq!(
            r.header_row(80),
            None,
            "a number past the rows is no header row"
        );
    }

    #[test]
    fn a_named_row_waits_for_its_pri() {
        // D5B7: Alan zitro's PRI joins at 56 s. A leaver's car on his team used to take
        // his row at the start and collect under his name
        let mut r = roster(&[("Alan zitro", 1)], &["Alan zitro", "YoZae--"]);
        car(&mut r, 19, 43);
        end_frame(&mut r, 1);
        assert_eq!(r.row(19), Some(1));

        car(&mut r, 137, 128);
        r.name(128, "Alan zitro");
        end_frame(&mut r, 1);
        assert_eq!(r.row(137), Some(0));
        assert_eq!(r.row(19), Some(1));
    }

    #[test]
    fn a_renamed_player_takes_the_row_no_pri_names_and_keeps_it() {
        // FBBB: the header says Poncho, the stream says fanta_666_due
        let mut r = roster(
            &[("Stayed", 1), ("Poncho", 1)],
            &["Stayed", "fanta_666_due"],
        );
        assert_eq!(r.free[&1], vec![1]);
        car(&mut r, 50, 43);
        r.name(43, "fanta_666_due");
        end_frame(&mut r, 1);
        assert_eq!(r.row(50), Some(1));
        assert_eq!(r.team(50), Some(1));

        // Demolished: the wreck holds the row, yet the new car gets it from the PRI
        r.unlink(50);
        car(&mut r, 60, 43);
        end_frame(&mut r, 1);
        assert_eq!(r.row(60), Some(1));
        assert_eq!(r.row(50), None);
    }

    #[test]
    fn rows_sharing_a_name_stay_free_for_their_team() {
        let r = roster(&[("Twin", 0), ("Twin", 0)], &["Twin"]);
        assert_eq!(r.free[&0], vec![0, 1]);
    }

    #[test]
    fn a_car_collects_for_its_pri_when_another_car_reports_as_that_player() {
        // Two bots called Rex share a row, and only one of their cars can hold it
        let mut r = roster(&[("Rex", 0)], &[]);
        r.name(66, "Rex");
        r.name(95, "Rex");
        car(&mut r, 60, 66);
        car(&mut r, 39, 95);
        assert_eq!(r.row(60), None);
        assert_eq!(r.row(39), Some(0));
        assert_eq!(r.collector(60), Some(0));
        assert_eq!(r.collector(39), Some(0));
    }

    #[test]
    fn a_link_to_anything_but_a_pri_is_ignored() {
        let mut r = roster(&[("A", 0)], &["A"]);
        r.add_car(10);
        r.link(10, 77, false);
        assert_eq!(r.seats[&10].pri, None);
    }

    #[test]
    fn paint_sets_a_cars_team_until_its_pri_names_the_row() {
        let mut r = roster(&[("A", 1)], &["A"]);
        r.add_car(10);
        r.paint(10, 0);
        assert_eq!(r.team(10), Some(0));
        r.link(10, 5, true);
        r.name(5, "A");
        r.paint(10, 0);
        assert_eq!(r.team(10), Some(1), "a linked car plays for its row's team");
    }

    #[test]
    fn a_removed_cars_row_goes_back_unless_a_pri_holds_it() {
        let mut r = roster(&[("A", 0), ("B", 0)], &[]);
        r.add_car(10);
        end_frame(&mut r, 0);
        assert_eq!(r.row(10), Some(0));
        r.remove_car(10, None);
        assert_eq!(r.free[&0], vec![1, 0]);

        car(&mut r, 11, 5);
        end_frame(&mut r, 0);
        assert_eq!(r.row(11), Some(1));
        r.remove_car(11, None);
        assert_eq!(r.free[&0], vec![0], "PRI 5 keeps row 1");
    }
}
