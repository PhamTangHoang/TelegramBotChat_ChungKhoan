from fastapi import FastAPI

app = FastAPI(title="VN Stock Analyst Bot", version="1.5.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
