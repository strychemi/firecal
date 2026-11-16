//! POST /api/query and GET /api/meta, as specified in docs/api.md.
//! pipeline/firecal_pipeline/reference.py implements the same contract; tests compare the two.
use crate::config::Preset;
use crate::data::{month_index, month_label, parse_month, Data};
use anyhow::{bail, Context, Result};
use geo::{Coord, LineString, Polygon};
use h3o::geom::{ContainmentMode, TilerBuilder};
use h3o::{CellIndex, LatLng, Resolution};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashSet;

const MONTHS: [&str; 12] = [
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December",
];

#[derive(Debug, Deserialize)]
pub struct QueryRequest {
    pub area: Area,
    pub start: Option<String>,
    pub end: Option<String>,
    pub month: Option<String>,
    pub baseline: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
pub enum Area {
    Preset { preset: String },
    Bbox { bbox: [f64; 4] },
    Polygon { polygon: Vec<[f64; 2]> },
    Circle { point: [f64; 2], radius_km: f64 },
}

#[derive(Debug, Serialize, Clone)]
pub struct MonthOut {
    pub month: String,
    pub source: String,
    pub value: f64,
    pub lower: Option<f64>,
    pub upper: Option<f64>,
    pub raw: u64,
    pub detections: u64,
    pub frp: f64,
    pub days: u8,
    pub days_with_data: u8,
    pub complete: bool,
    pub in_progress: bool,
}

fn round(x: f64, dp: i32) -> f64 {
    let f = 10f64.powi(dp);
    (x * f).round() / f
}

pub(crate) fn ring(area: &Area, presets: &[Preset]) -> Result<Vec<(f64, f64)>> {
    let bbox = |b: &[f64; 4]| {
        let [x0, y0, x1, y1] = *b;
        vec![(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    };
    Ok(match area {
        Area::Preset { preset } => {
            let p = presets.iter().find(|p| &p.id == preset).with_context(|| format!("unknown preset '{preset}'"))?;
            bbox(&p.bbox)
        }
        Area::Bbox { bbox: b } => {
            if !(b[0] < b[2] && b[1] < b[3]) {
                bail!("bbox must be [minLon, minLat, maxLon, maxLat] with min < max");
            }
            bbox(b)
        }
        Area::Polygon { polygon } => {
            if polygon.len() < 3 {
                bail!("polygon needs at least 3 points");
            }
            let mut r: Vec<(f64, f64)> = polygon.iter().map(|p| (p[0], p[1])).collect();
            if r.first() != r.last() {
                r.push(r[0]);
            }
            r
        }
        Area::Circle { point, radius_km } => {
            if !(*radius_km > 0.0 && *radius_km <= 2000.0) {
                bail!("radius_km must be between 0 and 2000");
            }
            let (lon, lat) = (point[0], point[1]);
            let dlat = radius_km / 111.32;
            let dlon = radius_km / (111.32 * lat.to_radians().cos());
            let mut r: Vec<(f64, f64)> = (0..64)
                .map(|i| {
                    let a = 2.0 * std::f64::consts::PI * i as f64 / 64.0;
                    (lon + dlon * a.cos(), lat + dlat * a.sin())
                })
                .collect();
            r.push(r[0]);
            r
        }
    })
}

/// The ring as pieces H3 can fill. H3 takes each edge the short way round the globe, so an area more than 180° of
/// longitude wide would be filled as the rest of the world. A box that wide is split into strips at most 90° wide;
/// a polygon that wide is refused (docs/api.md). Same as fill_pieces in the Python reference.
fn fill_pieces(ring: &[(f64, f64)]) -> Result<Vec<Vec<(f64, f64)>>> {
    let x0 = ring.iter().map(|p| p.0).fold(f64::INFINITY, f64::min);
    let x1 = ring.iter().map(|p| p.0).fold(f64::NEG_INFINITY, f64::max);
    if x1 - x0 <= 180.0 {
        return Ok(vec![ring.to_vec()]);
    }
    let (y0, y1) = (ring[0].1, ring[2].1);
    let rect = |a: f64, b: f64| vec![(a, y0), (b, y0), (b, y1), (a, y1), (a, y0)];
    if ring != rect(x0, x1).as_slice() {
        bail!("polygon is more than 180 degrees of longitude wide; use a box, or draw it in parts");
    }
    let k = ((x1 - x0) / 90.0).ceil() as usize;
    let mut edges: Vec<f64> = (0..k).map(|i| x0 + (x1 - x0) * i as f64 / k as f64).collect();
    edges.push(x1);
    Ok(edges.windows(2).map(|w| rect(w[0], w[1])).collect())
}

fn polygon_cells(pieces: &[Vec<(f64, f64)>], res: u8) -> Result<HashSet<CellIndex>> {
    let mut tiler = TilerBuilder::new(Resolution::try_from(res)?).containment_mode(ContainmentMode::ContainsCentroid).build();
    for ring in pieces {
        let poly = Polygon::new(LineString::from(ring.iter().map(|&(x, y)| Coord { x, y }).collect::<Vec<_>>()), vec![]);
        tiler.add(poly).map_err(|e| anyhow::anyhow!("invalid area: {e}"))?;
    }
    Ok(tiler.into_coverage().collect())
}

/// Finest published level that keeps the area at or under max_hex hexagons (docs/api.md).
pub(crate) fn area_cells(ring: &[(f64, f64)], resolutions: &[u8], max_hex: usize) -> Result<(u8, HashSet<CellIndex>)> {
    let pieces = fill_pieces(ring)?;
    let mut levels = resolutions.to_vec();
    levels.sort_unstable_by(|a, b| b.cmp(a));
    for &res in &levels {
        let cells = polygon_cells(&pieces, res)?;
        if !cells.is_empty() && cells.len() <= max_hex {
            return Ok((res, cells));
        }
    }
    let (finest, coarsest) = (levels[0], *levels.last().unwrap());
    let cells = polygon_cells(&pieces, coarsest)?;
    if !cells.is_empty() {
        return Ok((coarsest, cells));
    }
    let n = (ring.len() - 1) as f64;
    let lon = ring[..ring.len() - 1].iter().map(|p| p.0).sum::<f64>() / n;
    let lat = ring[..ring.len() - 1].iter().map(|p| p.1).sum::<f64>() / n;
    let cell = LatLng::new(lat, lon)?.to_cell(Resolution::try_from(finest)?);
    Ok((finest, HashSet::from([cell])))
}

fn model_of(source: &str) -> Option<&'static str> {
    match source {
        "terra_harmonized" => Some("terra"),
        "aqua_harmonized" => Some("aqua"),
        _ => None,
    }
}

/// 80 % range: the search's continent's miss table of the size of area nearest the search's area on a log
/// scale (PREREGISTRATION.md §7, 2026-11-15), and the bin containing `value`.
fn range_for(data: &Data, continent: &str, source: &str, value: f64, area_km2: f64) -> (Option<f64>, Option<f64>) {
    let Some(model) = model_of(source) else { return (None, None) };
    if value <= 0.0 {
        return (None, None);
    }
    let table = |b: &&crate::data::MissBin| b.continent == continent && b.model == model;
    let dist = |b: &&crate::data::MissBin| (b.area_km2.ln() - area_km2.ln()).abs();
    let Some(size) = data.misses.iter().filter(table).min_by(|a, b| dist(a).total_cmp(&dist(b))) else {
        return (None, None);
    };
    match data.misses.iter().filter(table).find(|b| b.size == size.size && b.lo <= value && value < b.hi) {
        Some(b) => (Some(value * b.q10.exp()), Some(value * b.q90.exp())),
        None => (None, None),
    }
}

/// The search's continent: the one holding most of its fire-days over the whole series (ties: the first name),
/// whose model, error ranges and month status the search uses (docs/api.md). A search with no fire uses "World"
/// (several continents) or the one study area. Returns (index in `data.areas`, its share or None).
fn continent_of(data: &Data, res: u8, cells: &HashSet<CellIndex>) -> (usize, Option<f64>) {
    let fallback = data.areas.iter().position(|a| a == "World").unwrap_or(0);
    let Some(table) = data.continents.get(&res) else { return (fallback, None) };
    let mut sums = vec![0f64; data.areas.len()];
    for cell in cells {
        for &(i, v) in table.get(&u64::from(*cell)).map(Vec::as_slice).unwrap_or(&[]) {
            sums[i as usize] += v as f64;
        }
    }
    let total: f64 = sums.iter().sum();
    if total <= 0.0 {
        return (fallback, None);
    }
    // First maximum: `areas` is sorted, so ties go to the first name.
    let (best, top) = sums.iter().enumerate().fold((0, f64::MIN), |acc, (i, &v)| if v > acc.1 { (i, v) } else { acc });
    (best, Some(round(top / total, 3)))
}

fn ordinal(n: usize) -> String {
    let suffix = if (10..=20).contains(&(n % 100)) {
        "th"
    } else {
        match n % 10 {
            1 => "st",
            2 => "nd",
            3 => "rd",
            _ => "th",
        }
    };
    format!("{n}{suffix}")
}

pub(crate) fn thousands(x: f64) -> String {
    let s = format!("{x:.0}");
    let (sign, digits) = s.strip_prefix('-').map_or(("", s.as_str()), |d| ("-", d));
    let mut out = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            out.push(',');
        }
        out.push(c);
    }
    format!("{sign}{out}")
}

fn median(v: &mut [f64]) -> f64 {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = v.len();
    if n % 2 == 1 { v[n / 2] } else { (v[n / 2 - 1] + v[n / 2]) / 2.0 }
}

/// "November 1–13" (or "November 1" for one day).
fn days_label(mname: &str, days: u32) -> String {
    if days == 1 { format!("{mname} 1") } else { format!("{mname} 1–{days}") }
}

/// `to_date`: Some((through, D)) when `series` values are days 1..D of the in-progress month.
fn stats(series: &[MonthOut], selected: &str, baseline: &str, to_date: Option<(&str, u32)>) -> Result<Value> {
    let cur = series.iter().find(|m| m.month == selected).with_context(|| format!("month {selected} is outside the series"))?;
    let mon = &selected[5..];
    let others: Vec<&MonthOut> =
        series.iter().filter(|m| &m.month[5..] == mon && m.month != selected && m.complete).collect();
    let mut vals: Vec<f64> = others.iter().map(|m| m.value).collect();
    let n = vals.len();
    let base = if n == 0 {
        0.0
    } else if baseline == "median" {
        median(&mut vals.clone())
    } else {
        vals.iter().sum::<f64>() / n as f64
    };
    let ratio = if base > 0.0 { Some(cur.value / base) } else { None };
    let rank = 1 + vals.iter().filter(|&&v| v > cur.value).count();
    let pct = if n > 0 { Some(round(vals.iter().filter(|&&v| v < cur.value).count() as f64 / n as f64 * 100.0, 1)) } else { None };
    let category = ratio.map(|r| match r {
        r if r < 0.5 => "much lower than usual",
        r if r < 0.8 => "lower than usual",
        r if r < 1.25 => "about usual",
        r if r < 2.0 => "higher than usual",
        _ => "much higher than usual",
    });
    let mname = MONTHS[mon.parse::<usize>()? - 1];
    let (name, usual, same) = match to_date {
        Some((_, d)) => (format!("{}, {}", days_label(mname, d), &selected[..4]), days_label(mname, d), "the same days are"),
        None => (format!("{mname} {}", &selected[..4]), mname.to_string(), "the same month is"),
    };
    let word = if baseline == "median" { "median" } else { "average" };
    let sentence = match ratio {
        _ if cur.value == 0.0 && base == 0.0 => {
            format!("No fire was detected in {name}, and {same} usually fire-free here.")
        }
        None => format!("{name} had {} fire-days; {same} usually fire-free here.", thousands(cur.value)),
        Some(r) => format!(
            "{name} had {} fire-days, {r:.1}× the usual {usual} ({word} of {n} years), {} highest of {} years.",
            thousands(cur.value),
            ordinal(rank),
            n + 1
        ),
    };
    vals.sort_by(|a, b| a.partial_cmp(b).unwrap());
    Ok(json!({
        "month": selected, "value": cur.value, "lower": cur.lower, "upper": cur.upper, "source": cur.source,
        "baseline": baseline, "baseline_value": round(base, 2),
        "baseline_years": others.iter().map(|m| m.month[..4].parse::<i32>().unwrap_or(0)).collect::<Vec<_>>(),
        "ratio": ratio.map(|r| round(r, 3)), "rank": rank, "of": n + 1, "percentile": pct,
        "category": category, "sentence": sentence, "through": to_date.map(|(t, _)| t),
    }))
}

pub fn query(data: &Data, presets: &[Preset], max_hex: usize, req: &QueryRequest) -> Result<Value> {
    let ring = ring(&req.area, presets)?;
    let (res, cells) = area_cells(&ring, &data.resolutions, max_hex)?;
    let area_km2: f64 = cells.iter().map(|c| c.area_km2()).sum();
    let table = data.cells.get(&res).context("resolution not loaded")?;
    let (ci, share) = continent_of(data, res, &cells);
    let continent = data.areas[ci].as_str();
    let status = data.status.get(continent).context("no month status")?;

    let series_start = month_label(data.start, 0);
    let series_end = month_label(data.start, data.n_months - 1);
    let start = req.start.clone().unwrap_or_else(|| series_start.clone());
    let end = req.end.clone().unwrap_or_else(|| series_end.clone());
    for m in [&start, &end] {
        let idx = month_index(data.start, parse_month(m)?);
        if idx < 0 || idx as usize >= data.n_months {
            bail!("{m} is outside the series {series_start} to {series_end}");
        }
    }
    if start > end {
        bail!("start must not be after end");
    }
    let selected = req.month.clone().unwrap_or_else(|| end.clone());
    let sel_idx = month_index(data.start, parse_month(&selected)?);
    let baseline = req.baseline.clone().unwrap_or_else(|| "median".into());
    if baseline != "median" && baseline != "mean" {
        bail!("baseline must be 'median' or 'mean'");
    }
    let start_idx = month_index(data.start, parse_month(&start)?);
    let end_idx = month_index(data.start, parse_month(&end)?);

    let mut sums = vec![(0f64, 0u64, 0u64, 0f64); data.n_months];
    let mut active = 0usize;
    // Per-hexagon values for the map: the selected month and the start..end total.
    let mut per_cell: Vec<(String, f64, f64)> = Vec::new();
    for cell in &cells {
        if let Some(rows) = table.get(u64::from(*cell)) {
            active += 1;
            let (mut in_month, mut in_range) = (0f64, 0f64);
            for r in rows {
                let s = &mut sums[r.month as usize];
                let value = r.value as f64;
                s.0 += value;
                s.1 += r.raw as u64;
                s.2 += r.detections as u64;
                s.3 += r.frp as f64;
                let i = r.month as i64;
                if i == sel_idx as i64 {
                    in_month += value;
                }
                if i >= start_idx as i64 && i <= end_idx as i64 {
                    in_range += value;
                }
            }
            if in_month > 0.0 || in_range > 0.0 {
                per_cell.push((cell.to_string(), in_month, in_range));
            }
        }
    }
    per_cell.sort_by(|a, b| a.0.cmp(&b.0));
    let hexes: Vec<Value> =
        per_cell.iter().map(|(h, m, r)| json!({"h3": h, "month": round(*m, 2), "range": round(*r, 2)})).collect();

    let series: Vec<MonthOut> = (0..data.n_months)
        .map(|i| {
            let st = &status[i];
            let (value, raw, detections, frp) = sums[i];
            let (lo, hi) = range_for(data, continent, &st.source, value, area_km2);
            MonthOut {
                month: month_label(data.start, i),
                source: st.source.clone(),
                value: round(value, 2),
                lower: lo.map(|x| round(x, 2)),
                upper: hi.map(|x| round(x, 2)),
                raw,
                detections,
                frp: round(frp, 1),
                days: st.days,
                days_with_data: st.days_with_data,
                complete: st.days_with_data == st.days,
                in_progress: data.in_progress.is_some_and(|(ip, _)| ip == i),
            }
        })
        .collect();

    // The in-progress month is compared on days 1..D: every year's same-month value becomes its month to date.
    let mut compared = series.clone();
    let to_date = match data.in_progress {
        Some((ip, days)) if ip as i64 == sel_idx => {
            let mtd = data.mtd.get(&res).context("month-to-date level not loaded")?;
            let mut sums = vec![0f64; data.n_months];
            for cell in &cells {
                for &(i, v) in mtd.get(&u64::from(*cell)).map(Vec::as_slice).unwrap_or(&[]) {
                    sums[i as usize] += v;
                }
            }
            let mon = &selected[5..];
            for (i, m) in compared.iter_mut().enumerate() {
                if &m.month[5..] == mon {
                    m.value = round(sums[i], 2);
                }
            }
            Some((data.through.as_str(), days))
        }
        _ => None,
    };

    let shown: Vec<&MonthOut> = series.iter().filter(|m| m.month >= start && m.month <= end).collect();
    let outline: Vec<[f64; 2]> = ring.iter().map(|&(x, y)| [round(x, 5), round(y, 5)]).collect();
    Ok(json!({
        "data_version": data.version,
        "area": {"resolution": res, "hexagons": cells.len(), "active_hexagons": active, "ring": outline},
        "continent": continent, "continent_share": share,
        "start": start, "end": end, "months": shown,
        "stats": stats(&compared, &selected, &baseline, to_date)?,
        "cells": hexes,
    }))
}

/// validation.json for one study area -> meta's per-satellite scores. A satellite that could not be fitted
/// (Antarctica) has no entry.
fn validation_entries(v: &Value) -> serde_json::Map<String, Value> {
    let mut out = serde_json::Map::new();
    for (k, d) in v.as_object().into_iter().flatten() {
        if d.get("leave_one_year_out").is_none() {
            continue;
        }
        // A conversion the pre-registered rule rejected is not used: report the scores of what is (no conversion).
        let converted = d["decision"]["kept"].as_bool().unwrap_or(true);
        let entry = if converted {
            json!({
                "whole_area_typical_error_pct": d["leave_one_year_out"]["whole_area"]["median"],
                "small_area_typical_error_pct": d["leave_one_year_out"]["small_area_2deg"]["median"],
                "backward_join_gap_pct": d["backward_join"]["gap_pct"]["all"],
                "converted": true,
            })
        } else {
            let n = &d["no_conversion"]["leave_one_year_out"];
            json!({
                "whole_area_typical_error_pct": n["whole_area"]["median"],
                "small_area_typical_error_pct": n["small_area_2deg"]["median"],
                "backward_join_gap_pct": n["gap_pct"]["all"],
                "converted": false,
            })
        };
        out.insert(k.clone(), entry);
    }
    out
}

pub fn meta(data: &Data, presets: &[Preset], export_limit: usize) -> Value {
    let m = &data.manifest;
    let nested = data.validation.get("continents");
    // Per continent (Argentina: the one study area): fitted or not, validation scores, its own gaps and filled days.
    let mut continents = serde_json::Map::new();
    for c in &data.areas {
        let info = &m["continents"][c.as_str()];
        let v = validation_entries(match nested {
            Some(n) => &n[c.as_str()],
            None => &data.validation,
        });
        let fitted = info["fitted"].as_bool().unwrap_or(true) && (c == "World" || !v.is_empty());
        let (gaps, filled) =
            if info.is_object() { (&info["gaps"], &info["days_filled_by"]) } else { (&m["gaps"], &m["days_filled_by"]) };
        continents.insert(c.clone(), json!({"fitted": fitted, "validation": v, "gaps": gaps, "days_filled_by": filled}));
    }
    let validation = if nested.is_some() { serde_json::Map::new() } else { validation_entries(&data.validation) };
    json!({
        "data_version": data.version, "series_start": m["series_start"], "series_end": m["series_end"],
        "through": data.through, "in_progress": m["in_progress"],
        "unit": m["unit"], "region": m["region"], "eras": m["eras"], "gaps": m["gaps"],
        "days_filled_by": m["days_filled_by"], "validation": validation, "continents": continents, "presets": presets,
        "export_limit": if data.has_export { Some(export_limit) } else { None },
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<(f64, f64)> {
        vec![(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    }

    #[test]
    fn wide_boxes_are_filled_as_strips() {
        assert_eq!(fill_pieces(&rect(-80.0, -20.0, 80.0, 20.0)).unwrap().len(), 1);
        let world = fill_pieces(&rect(-180.0, -85.0, 180.0, 85.0)).unwrap();
        assert_eq!(world.len(), 4);
        assert_eq!(world[0], rect(-180.0, -85.0, -90.0, 85.0));
        assert_eq!(world[3], rect(90.0, -85.0, 180.0, 85.0));
        // Without strips H3 fills the other side: a 200° box came back with a 160° box's hexagons.
        let (_, wide) = area_cells(&rect(-100.0, -20.0, 100.0, 20.0), &[4], usize::MAX).unwrap();
        let (_, narrow) = area_cells(&rect(-80.0, -20.0, 80.0, 20.0), &[4], usize::MAX).unwrap();
        assert!(wide.len() > narrow.len() && narrow.is_subset(&wide));
    }

    #[test]
    fn wide_polygons_are_refused() {
        let tri = vec![(-100.0, 0.0), (100.0, 0.0), (0.0, 10.0), (-100.0, 0.0)];
        assert!(fill_pieces(&tri).is_err());
    }
}
