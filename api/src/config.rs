//! Reads firecal.toml (the same file the pipeline reads).
use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
pub struct Config {
    pub data: DataCfg,
    pub api: ApiCfg,
    #[serde(default)]
    pub presets: Vec<Preset>,
}

#[derive(Debug, Deserialize)]
pub struct DataCfg {
    pub out_dir: String,
}

#[derive(Debug, Deserialize)]
pub struct ApiCfg {
    pub max_hexagons: usize,
    pub bind: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Preset {
    pub id: String,
    pub name: String,
    pub note: String,
    pub bbox: [f64; 4],
}

/// The repository root: the first command-line argument, $FIRECAL_ROOT, or the nearest parent of the
/// working directory holding firecal.toml.
pub fn find_root() -> Result<PathBuf> {
    if let Some(root) = std::env::args().nth(1) {
        return Ok(PathBuf::from(root));
    }
    if let Ok(root) = std::env::var("FIRECAL_ROOT") {
        return Ok(PathBuf::from(root));
    }
    let mut dir = std::env::current_dir()?;
    loop {
        if dir.join("firecal.toml").exists() {
            return Ok(dir);
        }
        if !dir.pop() {
            anyhow::bail!("firecal.toml not found; set FIRECAL_ROOT");
        }
    }
}

impl Config {
    pub fn load(root: &Path) -> Result<Self> {
        let path = root.join("firecal.toml");
        let text = std::fs::read_to_string(&path).with_context(|| format!("reading {}", path.display()))?;
        Ok(toml::from_str(&text)?)
    }
}
