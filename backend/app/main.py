from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.api.payments import router as payments_router
from app.api.reviews import router as reviews_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PathGuard Pay",
    version="0.1.0",
    description="AI safety layer for PayPal payments.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this when the React frontend is deployed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(payments_router)
app.include_router(reviews_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "pathguard-pay"}
