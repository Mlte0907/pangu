import uvicorn
uvicorn.run(
    "pangu.api.server:create_app",
    host="0.0.0.0",
    port=19529,
    factory=True,
    log_level="info",
)
