from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import pedidos, auth, base, amazon

app = FastAPI(title="Amazon Vendor Orders - Grupo A Educacao")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(auth.router,    prefix="/auth",    tags=["auth"])
app.include_router(pedidos.router, prefix="/pedidos", tags=["pedidos"])
app.include_router(base.router,    prefix="/base",    tags=["base"])
app.include_router(amazon.router,  prefix="/amazon",  tags=["amazon"])

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")
# Sistema de Pedidos Amazon - Grupo A Educacao v1.0
