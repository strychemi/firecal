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

fn polygon_cells(ring: &[(f64, f64)], res: u8) -> Result<HashSet<CellIndex>> {
    let poly = Polygon::new(LineString::from(ring.iter().map(|&(x, y)| Coord { x, y }).collect::<Vec<_>>()), vec![]);
    let mut tiler = TilerBuilder::new(Resolution::try_from(res)?).containment_mode(ContainmentMode::ContainsCentroid).build();
    tiler.add(poly).map_err(|e| anyhow::anyhow!("invalid area: {e}"))?;
    Ok(tiler.into_coverage().collect())
}

/// Finest published level that keeps the area at or under max_hex hexagons (docs/api.md).
pub(crate) fn area_cells(ring: &[(f64, f64)], resolutions: &[u8], max_hex: usize) -> Result<(u8, HashSet<CellIndex>)> {
    let mut levels = resolutions.to_vec();
    levels.sort_unstable_by(|a, b| b.cmp(a));
    for &res in &levels {
        let cells = polygon_cells(ring, res)?;
        if !cells.is_empty() && cells.len() <= max_hex {
            return Ok((res, cells));
        }
    }
    let (finest, coarsest) = (levels[0], *levels.last().unwrap());
    let cells = polygon_cells(ring, coarsest)?;
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

fn range_for(data: &Data, source: &str, value: f64) -> (Option<f64>, Option<f64>) {
    let Some(model) = model_of(source) else { return (None, None) };
    if value <= 0.0 {
        return (None, None);
    }
    match data.misses.iter().find(|b| b.model == model && b.lo <= value && value < b.hi) {
        Some(b) => (Some(value * b.q10.exp()), Some(value * b.q90.exp())),
        None => (None, None),
    }
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
    let table = data.cells.get(&res).context("resolution not loaded")?;

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
        if let Some(rows) = table.get(&u64::from(*cell)) {
            active += 1;
            let (mut in_month, mut in_range) = (0f64, 0f64);
            for r in rows {
                let s = &mut sums[r.month as usize];
                s.0 += r.value;
                s.1 += r.raw as u64;
                s.2 += r.detections as u64;
                s.3 += r.frp;
                let i = r.month as i64;
                if i == sel_idx as i64 {
                    in_month += r.value;
                }
                if i >= start_idx as i64 && i <= end_idx as i64 {
                    in_range += r.value;
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
            let st = &data.status[i];
            let (value, raw, detections, frp) = sums[i];
            let (lo, hi) = range_for(data, &st.source, value);
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
        "start": start, "end": end, "months": shown,
        "stats": stats(&compared, &selected, &baseline, to_date)?,
        "cells": hexes,
    }))
}

pub fn meta(data: &Data, presets: &[Preset], export_limit: usize) -> Value {
    let m = &data.manifest;
    let mut validation = serde_json::Map::new();
    if let Some(obj) = data.validation.as_object() {
        for (k, d) in obj {
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
            validation.insert(k.clone(), entry);
        }
    }
    json!({
        "data_version": data.version, "series_start": m["series_start"], "series_end": m["series_end"],
        "through": data.through, "in_progress": m["in_progress"],
        "unit": m["unit"], "region": m["region"], "eras": m["eras"], "gaps": m["gaps"],
        "days_filled_by": m["days_filled_by"], "validation": validation, "presets": presets,
        "export_limit": export_limit,
    })
}
