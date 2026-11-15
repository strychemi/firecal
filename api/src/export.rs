//! POST /api/export.csv: the filtered hotspots behind a search, as CSV (docs/api.md).
//! pipeline/firecal_pipeline/reference.py implements the same export; the parity test compares the bytes.
use crate::config::Preset;
use crate::data::{month_index, month_label, parse_month, Data};
use crate::query::{area_cells, ring, Area};
use anyhow::Result;
use h3o::CellIndex;
use serde::Deserialize;
use std::fmt::Write as _;

#[derive(Debug, Deserialize)]
pub struct ExportRequest {
    pub area: Area,
    pub start: Option<String>,
    pub end: Option<String>,
}

pub const HEADER: &str =
    "hex_id,latitude,longitude,acq_date,acq_time,local_solar_date,satellite,instrument,daynight,confidence,frp,in_calendar";

pub enum ExportError {
    /// The search matches more rows than the cap: (rows, cap).
    TooMany(u64, usize),
    Bad(anyhow::Error),
}

impl From<anyhow::Error> for ExportError {
    fn from(e: anyhow::Error) -> Self {
        ExportError::Bad(e)
    }
}

impl From<duckdb::Error> for ExportError {
    fn from(e: duckdb::Error) -> Self {
        ExportError::Bad(e.into())
    }
}

pub struct Export {
    pub csv: String,
    pub filename: String,
}

/// First day of the month and first day of the next month, as YYYY-MM-DD.
fn month_bounds(start: &str, end: &str) -> Result<(String, String)> {
    let (ey, em) = parse_month(end)?;
    let (ny, nm) = if em == 12 { (ey + 1, 1) } else { (ey, em + 1) };
    Ok((format!("{start}-01"), format!("{ny:04}-{nm:02}-01")))
}

fn csv_field(s: &str) -> String {
    if s.contains([',', '"', '\n']) {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

pub fn export(data: &Data, presets: &[Preset], max_hex: usize, max_rows: usize, req: &ExportRequest) -> Result<Export, ExportError> {
    let ring = ring(&req.area, presets)?;
    let (res, cells) = area_cells(&ring, &data.resolutions, max_hex)?;

    let series_start = month_label(data.start, 0);
    let series_end = month_label(data.start, data.n_months - 1);
    let start = req.start.clone().unwrap_or_else(|| series_start.clone());
    let end = req.end.clone().unwrap_or_else(|| series_end.clone());
    for m in [&start, &end] {
        let idx = month_index(data.start, parse_month(m)?);
        if idx < 0 || idx as usize >= data.n_months {
            return Err(anyhow::anyhow!("{m} is outside the series {series_start} to {series_end}").into());
        }
    }
    if start > end {
        return Err(anyhow::anyhow!("start must not be after end").into());
    }
    let (from, to) = month_bounds(&start, &end)?;

    let con = duckdb::Connection::open_in_memory()?;
    con.execute_batch("CREATE TABLE sel(cell UBIGINT)")?;
    {
        let mut app = con.appender("sel")?;
        for c in &cells {
            app.append_row([u64::from(*c)])?;
        }
    }
    let path = data.dir.join("hotspots.parquet");
    if !path.exists() {
        return Err(anyhow::anyhow!("this data version has no hotspot file; re-run the publish step").into());
    }
    let from_where = format!(
        "FROM read_parquet('{}') h JOIN sel ON h.cell{res} = sel.cell \
         WHERE h.local_date >= CAST(? AS DATE) AND h.local_date < CAST(? AS DATE)",
        path.display()
    );
    let n: u64 = con.query_row(&format!("SELECT count(*) {from_where}"), [&from, &to], |r| r.get(0))?;
    if n as usize > max_rows {
        return Err(ExportError::TooMany(n, max_rows));
    }

    let mut stmt = con.prepare(&format!(
        "SELECT h.cell{res}, h.lat, h.lon, strftime(h.acq_utc, '%Y-%m-%d'), strftime(h.acq_utc, '%H%M'), \
                strftime(h.local_date, '%Y-%m-%d'), h.sat, h.dn, h.confidence, h.frp, h.in_calendar \
         {from_where} ORDER BY h.acq_utc, h.lat, h.lon, h.sat"
    ))?;
    let mut csv = String::with_capacity(64 + n as usize * 96);
    csv.push_str(HEADER);
    csv.push('\n');
    let mut rows = stmt.query([&from, &to])?;
    while let Some(r) = rows.next()? {
        let cell: u64 = r.get(0)?;
        let hex = CellIndex::try_from(cell).map(|c| c.to_string()).unwrap_or_default();
        let (lat, lon): (f64, f64) = (r.get(1)?, r.get(2)?);
        let sat: String = r.get(6)?;
        let instrument = if sat == "terra" || sat == "aqua" { "MODIS" } else { "VIIRS" };
        let frp: Option<f64> = r.get(9)?;
        let _ = writeln!(
            csv,
            "{hex},{lat:.5},{lon:.5},{},{},{},{sat},{instrument},{},{},{},{}",
            r.get::<_, String>(3)?,
            r.get::<_, String>(4)?,
            r.get::<_, String>(5)?,
            csv_field(&r.get::<_, String>(7)?),
            csv_field(&r.get::<_, Option<String>>(8)?.unwrap_or_default()),
            frp.map(|f| format!("{f:.1}")).unwrap_or_default(),
            r.get::<_, bool>(10)?,
        );
    }
    Ok(Export { csv, filename: format!("firecal-hotspots-{start}_{end}.csv") })
}

