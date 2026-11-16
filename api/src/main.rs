//! firecal API: serves the published gold/ data (docs/api.md) and the built frontend (web/build).
mod config;
mod data;
mod export;
mod query;

use anyhow::Result;
use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use config::{Config, Preset};
use data::{current_version, Data};
use std::path::PathBuf;
use std::sync::{Arc, RwLock};
use std::time::Duration;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};
use tower_http::compression::CompressionLayer;
use tower_http::services::{ServeDir, ServeFile};

struct AppState {
    data: RwLock<Arc<Data>>,
    presets: Vec<Preset>,
    max_hex: usize,
    max_export_rows: usize,
    areas: Arc<query::AreaCache>,
    /// One search or export at a time per core: the work is all CPU, so more at once only slows each.
    slots: Arc<Semaphore>,
}

/// Areas whose work is kept (query::AreaCache).
const AREA_CACHE: usize = 64;
/// How long a request waits for a free slot before the server says it is busy.
const QUEUE_WAIT: Duration = Duration::from_secs(10);
/// How long a request waits for its answer once it has a slot. The work itself cannot be stopped, so it
/// finishes (keeping its slot, which keeps the load bounded) and its answer is dropped.
const WORK_WAIT: Duration = Duration::from_secs(30);

/// Wait for a slot; a client that gives up while waiting (the browser cancels a search it no longer
/// needs) drops this future, so its work never starts.
async fn slot(state: &Shared) -> Result<OwnedSemaphorePermit, ApiError> {
    match tokio::time::timeout(QUEUE_WAIT, state.slots.clone().acquire_owned()).await {
        Ok(Ok(p)) => Ok(p),
        _ => Err(ApiError(StatusCode::SERVICE_UNAVAILABLE, "The server is busy; try again in a moment.".into())),
    }
}

fn too_slow() -> ApiError {
    ApiError(StatusCode::SERVICE_UNAVAILABLE, "This search took too long; try a smaller area.".into())
}

type Shared = Arc<AppState>;

struct ApiError(StatusCode, String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(serde_json::json!({ "error": self.1 }))).into_response()
    }
}

fn snapshot(state: &Shared) -> Arc<Data> {
    state.data.read().unwrap().clone()
}

async fn meta(State(state): State<Shared>) -> Json<serde_json::Value> {
    Json(query::meta(&snapshot(&state), &state.presets, state.max_export_rows))
}

async fn run_query(
    State(state): State<Shared>,
    body: Result<Json<query::QueryRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let Json(req) = body.map_err(|e| ApiError(StatusCode::BAD_REQUEST, e.body_text()))?;
    let permit = slot(&state).await?;
    let data = snapshot(&state);
    let max_hex = state.max_hex;
    let presets = state.presets.clone();
    let areas = state.areas.clone();
    let work = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        query::query(&data, &presets, max_hex, &req, &areas)
    });
    tokio::time::timeout(WORK_WAIT, work)
        .await
        .map_err(|_| too_slow())?
        .map_err(|e| ApiError(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .map(Json)
        .map_err(|e| ApiError(StatusCode::BAD_REQUEST, e.to_string()))
}

/// POST /api/export.csv: the filtered hotspots for an area and dates, or 413 with the row count if over the cap.
async fn run_export(
    State(state): State<Shared>,
    body: Result<Json<export::ExportRequest>, axum::extract::rejection::JsonRejection>,
) -> Response {
    let Json(req) = match body {
        Ok(b) => b,
        Err(e) => return ApiError(StatusCode::BAD_REQUEST, e.body_text()).into_response(),
    };
    let permit = match slot(&state).await {
        Ok(p) => p,
        Err(e) => return e.into_response(),
    };
    let data = snapshot(&state);
    let (presets, max_hex, cap) = (state.presets.clone(), state.max_hex, state.max_export_rows);
    let work = tokio::task::spawn_blocking(move || {
        let _permit = permit;
        export::export(&data, &presets, max_hex, cap, &req)
    });
    let Ok(out) = tokio::time::timeout(WORK_WAIT, work).await else { return too_slow().into_response() };
    match out {
        Ok(Ok(x)) => (
            [
                (axum::http::header::CONTENT_TYPE, "text/csv; charset=utf-8".to_string()),
                (axum::http::header::CONTENT_DISPOSITION, format!("attachment; filename=\"{}\"", x.filename)),
            ],
            x.csv,
        )
            .into_response(),
        Ok(Err(export::ExportError::TooMany(n, cap))) => (
            StatusCode::PAYLOAD_TOO_LARGE,
            Json(serde_json::json!({
                "error": format!(
                    "This search has {} hotspots; one file holds at most {}. Narrow the dates or the area.",
                    query::thousands(n as f64),
                    query::thousands(cap as f64)
                ),
                "rows": n, "limit": cap,
            })),
        )
            .into_response(),
        Ok(Err(export::ExportError::Unavailable)) => {
            ApiError(StatusCode::NOT_FOUND, export::UNAVAILABLE.to_string()).into_response()
        }
        Ok(Err(export::ExportError::Bad(e))) => ApiError(StatusCode::BAD_REQUEST, format!("{e:#}")).into_response(),
        Err(e) => ApiError(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()).into_response(),
    }
}

/// Swap in a new data version when gold/CURRENT changes.
async fn watch(state: Shared, gold: PathBuf) {
    loop {
        tokio::time::sleep(Duration::from_secs(10)).await;
        let Ok(version) = current_version(&gold) else { continue };
        if version == snapshot(&state).version {
            continue;
        }
        let g = gold.clone();
        let v = version.clone();
        match tokio::task::spawn_blocking(move || Data::load(&g, &v)).await {
            Ok(Ok(new)) => {
                *state.data.write().unwrap() = Arc::new(new);
                tracing::info!("now serving data {version}");
            }
            Ok(Err(e)) => tracing::warn!("could not load data {version}: {e:#}"),
            Err(e) => tracing::warn!("loader panicked: {e}"),
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt().init();
    let root = config::find_root()?;
    let cfg = Config::load(&root)?;
    let gold = root.join(&cfg.data.out_dir).join("gold");
    let version = current_version(&gold)?;
    let data = Data::load(&gold, &version)?;
    tracing::info!("serving data {version} from {}", gold.display());

    let state: Shared = Arc::new(AppState {
        data: RwLock::new(Arc::new(data)),
        presets: cfg.presets,
        max_hex: cfg.api.max_hexagons,
        max_export_rows: cfg.api.max_export_rows,
        areas: Arc::new(query::AreaCache::new(AREA_CACHE)),
        slots: Arc::new(Semaphore::new(std::thread::available_parallelism().map_or(4, |n| n.get()))),
    });
    tokio::spawn(watch(state.clone(), gold));

    let mut app = Router::new().route("/api/meta", get(meta)).route("/api/query", post(run_query))
        .route("/api/export.csv", post(run_export));
    // The built frontend: FIRECAL_WEB, or web/build under the root (the browser tests serve the repo's
    // build while reading the sample data from another root).
    let web = std::env::var("FIRECAL_WEB").map(PathBuf::from).unwrap_or_else(|_| root.join("web").join("build"));
    if web.join("index.html").exists() {
        app = app.fallback_service(ServeDir::new(&web).fallback(ServeFile::new(web.join("index.html"))));
        tracing::info!("serving frontend from {}", web.display());
    }
    let app = app.with_state(state).layer(CompressionLayer::new());

    let bind = std::env::var("FIRECAL_BIND").unwrap_or(cfg.api.bind);
    let listener = tokio::net::TcpListener::bind(&bind).await?;
    tracing::info!("listening on http://{bind}");
    axum::serve(listener, app).await?;
    Ok(())
}
