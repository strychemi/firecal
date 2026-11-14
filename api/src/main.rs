//! firecal API: serves the published gold/ data (docs/api.md) and the built frontend (web/build).
mod config;
mod data;
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
use tower_http::compression::CompressionLayer;
use tower_http::services::{ServeDir, ServeFile};

struct AppState {
    data: RwLock<Arc<Data>>,
    presets: Vec<Preset>,
    max_hex: usize,
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
    Json(query::meta(&snapshot(&state), &state.presets))
}

async fn run_query(
    State(state): State<Shared>,
    body: Result<Json<query::QueryRequest>, axum::extract::rejection::JsonRejection>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let Json(req) = body.map_err(|e| ApiError(StatusCode::BAD_REQUEST, e.body_text()))?;
    let data = snapshot(&state);
    let max_hex = state.max_hex;
    let presets = state.presets.clone();
    tokio::task::spawn_blocking(move || query::query(&data, &presets, max_hex, &req))
        .await
        .map_err(|e| ApiError(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
        .map(Json)
        .map_err(|e| ApiError(StatusCode::BAD_REQUEST, e.to_string()))
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

    let state: Shared = Arc::new(AppState { data: RwLock::new(Arc::new(data)), presets: cfg.presets, max_hex: cfg.api.max_hexagons });
    tokio::spawn(watch(state.clone(), gold));

    let mut app = Router::new().route("/api/meta", get(meta)).route("/api/query", post(run_query));
    let web = root.join("web").join("build");
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
