# Demo image: the API, the built frontend, and the current published data for the global and the
# Argentina apps. APP=global (default) or APP=argentina picks which one a container serves.
# Build context is limited by .dockerignore / .gcloudignore to the files copied below.

FROM rust:1.98-bookworm AS build
WORKDIR /src
COPY api/Cargo.toml api/Cargo.lock ./
COPY api/src ./src
RUN cargo build --release --locked

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /src/target/release/firecal-api /app/firecal-api
COPY web/build /app/web
COPY global/firecal.toml /app/global/firecal.toml
COPY data/global/gold /app/data/global/gold
COPY firecal.toml /app/argentina/firecal.toml
COPY data/gold /app/argentina/data/gold
ENV APP=global FIRECAL_WEB=/app/web PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "FIRECAL_ROOT=/app/$APP FIRECAL_BIND=0.0.0.0:$PORT exec /app/firecal-api"]
