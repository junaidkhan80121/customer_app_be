from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, customer_types, customers, invoices, rankings, settings as settings_router

app = FastAPI(title="Lala Traders API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(customer_types.router)
app.include_router(customers.router)
app.include_router(invoices.router)
app.include_router(rankings.router)
app.include_router(settings_router.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
