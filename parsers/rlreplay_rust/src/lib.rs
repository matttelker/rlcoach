//! rlreplay_rust: read Rocket League replays for rlcoach, with boxcars underneath.
//!
//! `header` gives every header property as Python values. `frames` walks the
//! network frames (see `game`) and gives one dict per frame, with vectors as tuples.

mod game;
mod pads;
mod roster;

use boxcars::{HeaderProp, ParserBuilder, Replay};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::{IntoPyObjectExt, intern};

use game::{FrameOut, Game};
use pads::Spot;

fn read(path: &str) -> PyResult<Vec<u8>> {
    std::fs::read(path).map_err(|e| PyOSError::new_err(format!("couldn't read {path}: {e}")))
}

/// Every header property, by name. A struct becomes a dict of its fields, an array
/// a list of dicts, and an enum byte its value.
#[pyfunction]
fn header(py: Python<'_>, path: &str) -> PyResult<Py<PyAny>> {
    let data = read(path)?;
    let replay = ParserBuilder::new(&data)
        .never_parse_network_data()
        .parse()
        .map_err(|e| PyValueError::new_err(format!("couldn't read the header: {e}")))?;
    let properties = PyDict::new(py);
    for (key, value) in &replay.properties {
        properties.set_item(key, property(py, value)?)?;
    }
    properties.into_py_any(py)
}

fn property(py: Python<'_>, value: &HeaderProp) -> PyResult<Py<PyAny>> {
    let fields = |fields: &[(String, HeaderProp)]| -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        for (key, value) in fields {
            dict.set_item(key, property(py, value)?)?;
        }
        dict.into_py_any(py)
    };
    match value {
        HeaderProp::Array(entries) => {
            let list = PyList::empty(py);
            for entry in entries {
                list.append(fields(entry)?)?;
            }
            list.into_py_any(py)
        }
        HeaderProp::Struct { fields: inner, .. } => fields(inner),
        HeaderProp::Bool(value) => value.into_py_any(py),
        HeaderProp::Byte { value, .. } => value.into_py_any(py),
        HeaderProp::Float(value) => f64::from(*value).into_py_any(py),
        HeaderProp::Int(value) => value.into_py_any(py),
        HeaderProp::QWord(value) => value.into_py_any(py),
        HeaderProp::Name(value) | HeaderProp::Str(value) => value.into_py_any(py),
    }
}

/// Every network frame, in order. `pad_spots` are the arena's boost pads (x, y, z),
/// which number the pickups. Give none for an arena whose pads aren't known.
#[pyfunction]
fn frames(py: Python<'_>, path: &str, pad_spots: Vec<Spot>) -> PyResult<Py<PyAny>> {
    let data = read(path)?;
    let frames = py
        .detach(|| walk(&data, pad_spots))
        .map_err(PyValueError::new_err)?;
    let list = PyList::empty(py);
    for frame in &frames {
        list.append(frame_dict(py, frame)?)?;
    }
    list.into_py_any(py)
}

fn walk(data: &[u8], pad_spots: Vec<Spot>) -> Result<Vec<FrameOut>, String> {
    let Replay {
        properties,
        objects,
        network_frames,
        ..
    } = ParserBuilder::new(data)
        .must_parse_network_data()
        .parse()
        .map_err(|e| format!("couldn't read the frames: {e}"))?;
    let frames = network_frames.map(|n| n.frames).unwrap_or_default();
    let names = game::stream_names(&objects, &frames);
    let mut game = Game::new(&objects, header_rows(&properties), &names, pad_spots);
    Ok(frames.iter().map(|frame| game.step(frame)).collect())
}

/// Each `PlayerStats` row's name and team. A row with no name isn't a player.
fn header_rows(properties: &[(String, HeaderProp)]) -> Vec<(String, i64)> {
    let Some((_, HeaderProp::Array(rows))) = properties.iter().find(|(k, _)| k == "PlayerStats")
    else {
        return Vec::new();
    };
    rows.iter()
        .filter_map(|row| {
            let field = |key: &str| row.iter().find(|(k, _)| k == key).map(|(_, v)| v);
            let name = field("Name")?.as_string()?.to_string();
            let team = field("Team").and_then(|team| team.as_i32()).unwrap_or(0);
            Some((name, i64::from(team)))
        })
        .collect()
}

fn xyz(spot: Spot) -> (f64, f64, f64) {
    (f64::from(spot.0), f64::from(spot.1), f64::from(spot.2))
}

fn frame_dict<'py>(py: Python<'py>, frame: &FrameOut) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item(intern!(py, "time"), f64::from(frame.time))?;
    dict.set_item(
        intern!(py, "ball"),
        (xyz(frame.ball_position), xyz(frame.ball_velocity)),
    )?;
    dict.set_item(intern!(py, "hit_team"), frame.hit_team)?;
    let cars = frame.cars.iter().map(|car| {
        let rotation = car.rotation.map(|q| q.map(f64::from));
        (
            car.row,
            car.team,
            xyz(car.position),
            xyz(car.velocity),
            xyz(car.spin),
            rotation.map(|[x, y, z, w]| (x, y, z, w)),
            car.boost,
            car.demolished,
            (
                car.controls.jumping,
                car.controls.double_jumping,
                car.controls.dodging,
            ),
        )
    });
    dict.set_item(intern!(py, "cars"), PyList::new(py, cars)?)?;
    let pickups = frame
        .pickups
        .iter()
        .map(|(pad, row, team, time)| (*pad, *row, *team, f64::from(*time)));
    dict.set_item(intern!(py, "pickups"), PyList::new(py, pickups)?)?;
    let dodges = frame
        .dodges
        .iter()
        .map(|(row, torque)| (*row, xyz(*torque)));
    dict.set_item(intern!(py, "dodges"), PyList::new(py, dodges)?)?;
    dict.set_item(intern!(py, "touches"), PyList::new(py, &frame.touches)?)?;
    dict.set_item(
        intern!(py, "first_touches"),
        PyList::new(py, &frame.first_touches)?,
    )?;
    dict.set_item(intern!(py, "demos"), PyList::new(py, &frame.demos)?)?;
    Ok(dict)
}

#[pymodule]
fn rlreplay_rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(header, module)?)?;
    module.add_function(wrap_pyfunction!(frames, module)?)?;
    Ok(())
}
