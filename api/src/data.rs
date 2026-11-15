//! One published version of gold/, loaded into memory.
//!
//! Every hexagon level is held in memory (Argentina: about 16 MB of Parquet). Rows are kept as f32, the type
//! they are published in, so nothing is lost; see README (global app) for the global sizes.
use anyhow::{Context, Result};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy)]
pub struct Row {
    pub month: u16, // index from series_start
    pub value: f32,
    pub raw: u32,
    pub detections: u32,
    pub frp: f32,
}

/// One hexagon level: every row in one array, in file order (sorted by cell), and each cell's slice of it.
/// One allocation per level instead of one per hexagon: the global data has 2.5 M hexagons over three levels.
#[derive(Default)]
pub struct Level {
    rows: Vec<Row>,
    index: HashMap<u64, (u32, u32)>,
}

impl Level {
    pub fn get(&self, cell: u64) -> Option<&[Row]> {
        self.index.get(&cell).map(|&(i, n)| &self.rows[i as usize..(i + n) as usize])
    }
}

/// Data published before continents (Argentina up to v11) is one continent, named as its cell-days are.
pub const SINGLE: &str = "study_area";

#[derive(Debug, Clone)]
pub struct MonthStatus {
    pub source: String,
    pub days: u8,
    pub days_with_data: u8,
}

#[derive(Debug, Clone)]
pub struct MissBin {
    pub continent: String,
    pub model: String,
    /// Size of area this table is for (r4, r3, block, region) and its typical area in km².
    pub size: String,
    pub area_km2: f64,
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
    pub cells: HashMap<u8, Level>,
    /// Month status per continent (Argentina: "study_area"; with several continents also "World").
    pub status: HashMap<String, Vec<MonthStatus>>,
    /// Continent names with a month status, sorted.
    pub areas: Vec<String>,
    /// Each hexagon's fire-days per continent over the whole series: level -> cell -> (index in `areas`, value).
    /// Empty for data published before continents.
    pub continents: HashMap<u8, HashMap<u64, Vec<(u8, f32)>>>,
    /// Whether hotspots.parquet was published (not for the global run).
    pub has_export: bool,
    pub misses: Vec<MissBin>,
    /// Last local date with data (manifest `through`).
    pub through: String,
    /// The series' last month when it ends partway through: (month index, days 1..D covered).
    pub in_progress: Option<(usize, u32)>,
    /// Days 1..D of the in-progress calendar month in every year: level -> cell -> (month index, value).
    pub mtd: HashMap<u8, HashMap<u64, Vec<(u16, f64)>>>,
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

pub fn days_in_month(y: i32, m: u32) -> u32 {
    match m {
        2 if (y % 4 == 0 && y % 100 != 0) || y % 400 == 0 => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
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
            let n: i64 = con.query_row(&format!("SELECT count(*) FROM read_parquet('{}')", path.display()), [], |r| r.get(0))?;
            let mut stmt = con.prepare(&format!(
                "SELECT cell, year, month, value, raw, detections, frp FROM read_parquet('{}')",
                path.display()
            ))?;
            let mut level = Level { rows: Vec::with_capacity(n as usize), index: HashMap::new() };
            let mut last: Option<u64> = None;
            let mut rows = stmt.query([])?;
            while let Some(r) = rows.next()? {
                let cell: u64 = r.get(0)?;
                let (y, m): (i16, i8) = (r.get(1)?, r.get(2)?);
                let idx = month_index(start, (y as i32, m as u32));
                if idx < 0 || idx as usize >= n_months {
                    continue;
                }
                if last != Some(cell) {
                    let at = level.rows.len() as u32;
                    anyhow::ensure!(level.index.insert(cell, (at, 0)).is_none(), "{} is not sorted by cell", path.display());
                    last = Some(cell);
                }
                level.index.get_mut(&cell).unwrap().1 += 1;
                level.rows.push(Row {
                    month: idx as u16,
                    value: r.get(3)?,
                    raw: r.get::<_, i32>(4)? as u32,
                    detections: r.get::<_, i32>(5)? as u32,
                    frp: r.get(6)?,
                });
            }
            level.rows.shrink_to_fit();
            level.index.shrink_to_fit();
            cells.insert(res, level);
        }

        // A column added with continents (month_status, misses): older data has none, so it is the one study area.
        let has_column = |file: &str, col: &str| -> Result<bool> {
            let mut stmt = con.prepare(&format!(
                "SELECT count(*) FROM (DESCRIBE SELECT * FROM read_parquet('{}')) WHERE column_name = '{col}'",
                dir.join(file).display()
            ))?;
            Ok(stmt.query_row([], |r| r.get::<_, i64>(0))? > 0)
        };
        let continent_col =
            |file: &str| -> Result<String> { Ok(if has_column(file, "continent")? { "continent".into() } else { format!("'{SINGLE}'") }) };

        let mut status: HashMap<String, Vec<MonthStatus>> = HashMap::new();
        let mut stmt = con.prepare(&format!(
            "SELECT {}, year, month, source, days, days_with_data FROM read_parquet('{}')",
            continent_col("month_status.parquet")?,
            dir.join("month_status.parquet").display()
        ))?;
        let mut rows = stmt.query([])?;
        while let Some(r) = rows.next()? {
            let (y, m): (i16, i8) = (r.get(1)?, r.get(2)?);
            let idx = month_index(start, (y as i32, m as u32));
            if idx >= 0 && (idx as usize) < n_months {
                let st = status.entry(r.get(0)?).or_insert_with(|| {
                    vec![MonthStatus { source: String::new(), days: 0, days_with_data: 0 }; n_months]
                });
                st[idx as usize] = MonthStatus {
                    source: r.get(3)?,
                    days: r.get::<_, i8>(4)? as u8,
                    days_with_data: r.get::<_, i8>(5)? as u8,
                };
            }
        }
        let mut areas: Vec<String> = status.keys().cloned().collect();
        areas.sort();
        anyhow::ensure!(areas.len() < 256, "too many continents");

        let mut continents = HashMap::new();
        for &res in &resolutions {
            let path = dir.join(format!("continents_res{res}.parquet"));
            if !path.exists() {
                continue;
            }
            let mut stmt = con.prepare(&format!("SELECT cell, continent, value FROM read_parquet('{}')", path.display()))?;
            let mut map: HashMap<u64, Vec<(u8, f32)>> = HashMap::new();
            let mut rows = stmt.query([])?;
            while let Some(r) = rows.next()? {
                let name: String = r.get(1)?;
                let i = areas.binary_search(&name).map_err(|_| anyhow::anyhow!("continent {name} has no month status"))?;
                map.entry(r.get(0)?).or_default().push((i as u8, r.get(2)?));
            }
            map.shrink_to_fit();
            continents.insert(res, map);
        }

        let mut misses = Vec::new();
        let mut stmt = con.prepare(&format!(
            "SELECT {}, model, size, area_km2, lo, hi, q10, q90 FROM read_parquet('{}')",
            continent_col("misses.parquet")?,
            dir.join("misses.parquet").display()
        ))?;
        let mut rows = stmt.query([])?;
        while let Some(r) = rows.next()? {
            misses.push(MissBin {
                continent: r.get(0)?,
                model: r.get(1)?,
                size: r.get(2)?,
                area_km2: r.get(3)?,
                lo: r.get(4)?,
                hi: r.get(5)?,
                q10: r.get(6)?,
                q90: r.get(7)?,
            });
        }
        let has_export = dir.join("hotspots.parquet").exists();

        // Older manifests have no `through`: the series then ends on its last month's last day.
        let through = match manifest["through"].as_str() {
            Some(t) => t.to_string(),
            None => {
                let (y, m) = parse_month(&month_label(start, n_months - 1))?;
                format!("{y:04}-{m:02}-{:02}", days_in_month(y, m))
            }
        };
        let in_progress = match manifest["in_progress"].as_object() {
            Some(ip) => {
                let ym = parse_month(ip.get("month").and_then(|v| v.as_str()).context("in_progress.month")?)?;
                let days = ip.get("days").and_then(|v| v.as_u64()).context("in_progress.days")? as u32;
                Some((month_index(start, ym) as usize, days))
            }
            None => None,
        };
        let mut mtd = HashMap::new();
        if let Some((idx, _)) = in_progress {
            let month = month_label(start, idx)[5..].parse::<u32>()?;
            for &res in &resolutions {
                let mut stmt = con.prepare(&format!(
                    "SELECT cell, year, value FROM read_parquet('{}')",
                    dir.join(format!("mtd_res{res}.parquet")).display()
                ))?;
                let mut map: HashMap<u64, Vec<(u16, f64)>> = HashMap::new();
                let mut rows = stmt.query([])?;
                while let Some(r) = rows.next()? {
                    let y: i16 = r.get(1)?;
                    let i = month_index(start, (y as i32, month));
                    if i < 0 || i as usize >= n_months {
                        continue;
                    }
                    map.entry(r.get(0)?).or_default().push((i as u16, r.get::<_, f32>(2)? as f64));
                }
                mtd.insert(res, map);
            }
        }

        Ok(Self {
            version: version.to_string(), dir, manifest, validation, start, n_months, resolutions, cells, status, areas,
            continents, has_export, misses, through, in_progress, mtd,
        })
    }
}
