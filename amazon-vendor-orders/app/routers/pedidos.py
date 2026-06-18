from fastapi import APIRouter, HTTPException, UploadFile, File, Header
from pydantic import BaseModel
from typing import Optional
import io, openpyxl
from datetime import datetime, timedelta
from app.database import get_db
from app.services.processador import processar_pedido_amazon

router = APIRouter()

def usuario_autenticado(authorization: str = Header(...)):
    """Valida JWT e retorna dados do usuário."""
    db = get_db()
    token = authorization.replace("Bearer ", "")
    try:
        resp = db.auth.get_user(token)
        user = resp.user
        perfil = db.table("perfis").select("*").eq("id", user.id).single().execute()
        return {"id": user.id, "email": user.email, **perfil.data}
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

@router.get("/")
def listar_pedidos(authorization: str = Header(...)):
    usuario = usuario_autenticado(authorization)
    db = get_db()
    pedidos = db.table("pedidos").select("*, itens_pedido(count)").order("criado_em", desc=True).execute()
    return pedidos.data

@router.get("/{pedido_id}/itens")
def listar_itens(pedido_id: int, authorization: str = Header(...)):
    usuario = usuario_autenticado(authorization)
    db = get_db()
    itens = db.table("itens_pedido").select("*").eq("pedido_id", pedido_id).execute()
    return itens.data

@router.post("/upload")
async def upload_pedido(
    arquivo: UploadFile = File(...),
    authorization: str = Header(...)
):
    """Recebe XLS da Amazon, processa e salva no banco."""
    usuario = usuario_autenticado(authorization)
    conteudo = await arquivo.read()
    try:
        resultado = processar_pedido_amazon(conteudo, usuario["id"])
        return resultado
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

class DecisaoItem(BaseModel):
    item_id: int
    decisao: str          # aceito | rejeitado | aceito_parcial
    qtda_aceita: Optional[int] = None
    codigo_rejeicao: Optional[str] = None
    motivo: Optional[str] = None
    data_envio: Optional[str] = None

@router.post("/{pedido_id}/validar")
def validar_pedido(pedido_id: int, itens: list[DecisaoItem], authorization: str = Header(...)):
    """Validador registra decisão por item."""
    usuario = usuario_autenticado(authorization)
    db = get_db()
    for item in itens:
        db.table("itens_pedido").update({
            "decisao": item.decisao,
            "qtda_aceita": item.qtda_aceita,
            "codigo_rejeicao": item.codigo_rejeicao,
            "motivo_rejeicao": item.motivo,
            "data_envio_prevista": item.data_envio,
            "atualizado_em": datetime.utcnow().isoformat(),
        }).eq("id", item.item_id).execute()
        # Audit log
        db.table("audit_log").insert({
            "usuario_id": usuario["id"],
            "usuario_nome": usuario.get("nome"),
            "acao": "validou_item",
            "entidade": "itens_pedido",
            "entidade_id": str(item.item_id),
            "detalhe": item.dict(),
        }).execute()
    # Marca pedido como validado
    db.table("pedidos").update({
        "status_interno": "validado",
        "validado_por": usuario["id"],
        "validado_em": datetime.utcnow().isoformat(),
    }).eq("id", pedido_id).execute()
    return {"ok": True, "itens_validados": len(itens)}
