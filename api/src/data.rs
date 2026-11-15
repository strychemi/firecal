//! One published version of gold/, loaded into memory.
//!
//! The prototype holds every hexagon level in memory (Argentina: about 16 MB of Parquet).
//! For the globe, levels 4 and 5 stay in memory and level 6 is read from disk (ARCHITECTURE.md §5).
use anyhow::{Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy)]
pub struct Row {
    pub month: u16, // index from series_start
    pub value: f64,
    pub raw: u32,
    pub detections: u32,
    pub frp: f64,
}

#[derive(Debug, Clone)]
pub struct MonthStatus {
    pub source: String,
    pub days: u8,
    pub days_with_data: u8,
}

#[derive(Debug, Clone)]
pub struct MissBin {
    pub model: String,
    pub lo: f64,
    pub hi: f64,
    pub q10: f64,
    pub q90: f64,
}

pub struct Data {
    pub version: String,
    /// gold/vN, for files read per request (hotspots.parquet)
    pub dir: PathBuf,
    pub manifest: Value,
    pub validation: Value,
    pub start: (i32, u32),
    pub n_months: usize,
    pub resolutions: Vec<u8>,
    pub cells: HashMap<u8, HashMap<u64, Vec<Row>>>,
    pub status: Vec<MonthStatus>,
    pub misses: Vec<MissBin>,
}

pub fn parse_month(s: &str) -> Result<(i32, u32)> {
    let (y, m) = s.split_once('-').context("month must be YYYY-MM")?;
    let (y, m): (i32, u32) = (y.parse()?, m.parse()?);
    anyhow::ensure!((1..=12).contains(&m), "month must be YYYY-MM");
    Ok((y, m))
}

pub fn month_index(start: (i32, u32), ym: (i32, u32)) -> i64 {
    (ym.0 - start.0) as i64 * 12 + ym.1 as i64 - start.1 as i64
}

pub fn month_label(start: (i32, u32), idx: usize) -> String {
    let total = start.0 as i64 * 12 + start.1 as i64 - 1 + idx as i64;
    format!("{:04}-{:02}", total / 12, total % 12 + 1)
}

pub fn current_version(gold: &Path) -> Result<String> {
    Ok(std::fs::read_to_string(gold.join("CURRENT")).context("reading gold/CURRENT")?.trim().to_string())
}

impl Data {
    pub fn load(gold: &Path, version: &str) -> Result<Self> {
        let dir: PathBuf = gold.join(version);
        let manifest: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("manifest.json"))?)?;
        let validation: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("validation.json"))?)?;
        let start = parse_month(manifest["series_start"].as_str().context("series_start")?)?;
        let end = parse_month(manifest["series_end"].as_str().context("series_end")?)?;
        let n_months = (month_index(start, end) + 1) as usize;
        let resolutions: Vec<u8> = manifest["resolutions"]
            .as_array()
            .context("resolutions")?
            .iter()
            .filter_map(|v| v.as_u64().map(|r| r as u8))
            .collect();

        let con = duckdb::Connection::open_in_memory()?;
        let mut cells = HashMap::new();
        for &res in &resolutions {
            let path = dir.join(format!("monthly_res{res}.parquet"));
            let mut stmt = con.prepare(&format!(
                "SELECT cell, year, month, value, raw, detections, frp FROM read_parquet('{}')",
                path.display()
            ))?;
            let mut map: HashMap<u64, Vec<Row>> = HashMap::new();
            let mut rows = stmt.query([])?;
            while let Some(r) = rows.next()? {
                let cell: u64 = r.get(0)?;
                let (y, m): (i16, i8) = (r.get(1)?, r.get(2)?);
                let idx = month_index(start, (y as i32, m as u32));
                if idx < 0 || idx as usize >= n_months {
                    continue;
                }
                map.entry(cell).or_default().push(Row {
                    month: idx as u16,
                    value: r.get::<_, f32>(3)? as f64,
                    raw: r.get::<_, i32>(4)? as u32,
                    detections: r.get::<_, i32>(5)? as u32,
                    frp: r.get::<_, f32>(6)? as f64,
                });
            }
            cells.insert(res, map);
        }

        let mut status = vec![MonthStatus { source: String::new(), days: 0, days_with_data: 0 }; n_months];
        let mut stmt = con.prepare(&format!(
            "SELECT year, month, source, days, days_with_data FROM read_parquet('{}')",
            dir.join("month_status.parquet").display()
        ))?;
        let mut rows = stmt.query([])?;
        while let Some(r) = rows.next()? {
            let (y, m): (i16, i8) = (r.get(0)?, r.get(1)?);
            let idx = month_index(start, (y as i32, m as u32));
            if idx >= 0 && (idx as usize) < n_months {
                status[idx as usize] = MonthStatus {
                    source: r.get(2)?,
                    days: r.get::<_, i8>(3)? as u8,
                    days_with_data: r.get::<_, i8>(4)? as u8,
                };
            }
        }

        let mut misses = Vec::new();
        let mut stmt = con.prepare(&format!(
            "SELECT model, lo, hi, q10, q90 FROM read_parquet('{}')",
            dir.join("misses.parquet").display()
        ))?;
        let mut rows = stmt.query([])?;
        while let Some(r) = rows.next()? {
            misses.push(MissBin { model: r.get(0)?, lo: r.get(1)?, hi: r.get(2)?, q10: r.get(3)?, q90: r.get(4)? });
        }

        Ok(Self { version: version.to_string(), dir, manifest, validation, start, n_months, resolutions, cells, status, misses })
    }
}
