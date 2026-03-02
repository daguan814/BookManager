from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from Controller.book_controller import router as book_router
from Controller.health_controller import router as health_router
from Controller.inventory_controller import router as inventory_router
from config import settings
from db.database import ensure_runtime_schema

app = FastAPI(title="BookManager API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(inventory_router)
app.include_router(book_router)


@app.on_event("startup")
def startup_schema_sync():
    ensure_runtime_schema()


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=False)
