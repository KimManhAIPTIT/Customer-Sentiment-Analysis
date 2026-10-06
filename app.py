from fastapi import FastAPI

app = FastAPI(title="Customer Review Insights")

@app.get("/")
def root():
    return {"status": "backend_ready"}
