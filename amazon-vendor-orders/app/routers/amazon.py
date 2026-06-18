from fastapi import APIRouter, HTTPException, Header
from app.routers.pedidos import usuario_autenticado
from app.services.amazon_api import buscar_pedidos_amazon, enviar_acknowledgment
from app.database import get_db

router = APIRouter()

@router.post("/sincronizar")
def sincronizar_pedidos(authorization: str = Header(...)):
    """Busca POs na Amazon SP-API e salva no banco."""
    usuario = usuario_autenticado(authorization)
    if usuario["role"] not in ("admin", "validador"):
        raise HTTPException(status_code=403, detail="Sem permissão")
    resultado = buscar_pedidos_amazon()
    return resultado

@router.post("/pedidos/{pedido_id}/acknowledgment")
def enviar_ack(pedido_id: int, authorization: str = Header(...)):
    """Envia acknowledgment para a Amazon com base nas decisões validadas."""
    usuario = usuario_autenticado(authorization)
    if usuario["role"] not in ("admin", "validador"):
        raise HTTPException(status_code=403, detail="Sem permissão")
    resultado = enviar_acknowledgment(pedido_id, usuario["id"])
    return resultado
