from fastapi import APIRouter, UploadFile, File, HTTPException, Header
from app.database import get_db
from app.services.importador_base import importar_base_produtos, importar_base_p12
from app.routers.pedidos import usuario_autenticado

router = APIRouter()

@router.post("/produtos/upload")
async def upload_base_produtos(arquivo: UploadFile = File(...), authorization: str = Header(...)):
    usuario = usuario_autenticado(authorization)
    if usuario["role"] not in ("admin", "validador"):
        raise HTTPException(status_code=403, detail="Sem permissão")
    conteudo = await arquivo.read()
    resultado = importar_base_produtos(conteudo, usuario["id"])
    return resultado

@router.post("/p12/upload")
async def upload_base_p12(arquivo: UploadFile = File(...), authorization: str = Header(...)):
    usuario = usuario_autenticado(authorization)
    if usuario["role"] not in ("admin", "validador"):
        raise HTTPException(status_code=403, detail="Sem permissão")
    conteudo = await arquivo.read()
    resultado = importar_base_p12(conteudo, usuario["id"])
    return resultado

@router.get("/descontos")
def listar_descontos(authorization: str = Header(...)):
    usuario = usuario_autenticado(authorization)
    db = get_db()
    return db.table("descontos_editora").select("*").order("editora").execute().data
