from fastapi import FastAPI

app = FastAPI(title="SENTINEL-X API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
