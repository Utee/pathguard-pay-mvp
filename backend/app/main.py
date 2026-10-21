from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.intelligence import router as intelligence_router
from app.api.limits import router as limits_router
from app.api.payments import router as payments_router
from app.api.paypal_connection import router as paypal_connection_router
from app.api.reviews import router as reviews_router
from app.core.config import get_settings
from app.db import initialize_database

settings = get_settings()
initialize_database()

app = FastAPI(
    title="PathGuard Pay",
    version="0.3.0",
    description="AI safety layer for authenticated PayPal payments.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(intelligence_router)
app.include_router(payments_router)
app.include_router(paypal_connection_router)
app.include_router(limits_router)
app.include_router(reviews_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "pathguard-pay"}
