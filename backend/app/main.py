from fastapi import FastAPI

app = FastAPI(title="Mathlings API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
