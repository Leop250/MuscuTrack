from fastapi import FastAPI

app = FastAPI(title="Muscu Track - tracking-service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "tracking-service"}
