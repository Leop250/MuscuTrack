from fastapi import FastAPI

app = FastAPI(title="Muscu Track - auth-service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth-service"}
