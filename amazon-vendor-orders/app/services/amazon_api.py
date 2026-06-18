"""
Integração com Amazon SP-API (Vendor Orders)
- GET /vendor/orders/v1/purchaseOrders
- POST /vendor/orders/v1/acknowledgements
"""
import httpx
from datetime import datetime, timedelta
from app.config import get_settings
from app.database import get_db

SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

_token_cache = {"token": None, "expires_at": None}

def _get_access_token() -> str:
    now = datetime.utcnow()
    if _token_cache["token"] and _token_cache["expires_at"] > now:
        return _token_cache["token"]

    s = get_settings()
    resp = httpx.post(LWA_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": s.amazon_refresh_token,
        "client_id": s.amazon_client_id,
        "client_secret": s.amazon_client_secret,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + timedelta(seconds=data.get("expires_in", 3600) - 60)
    return _token_cache["token"]

def buscar_pedidos_amazon() -> dict:
    """Busca POs com status NEW da Amazon e salva no banco."""
    token = _get_access_token()
    db = get_db()

    params = {
        "shipFromPartyId": get_settings().amazon_vendor_code,
        "status": "UNCONFIRMED",
        "limit": 100,
    }
    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json",
    }
    resp = httpx.get(f"{SP_API_BASE}/vendor/orders/v1/purchaseOrders", params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    orders = data.get("payload", {}).get("orders", [])
    novos = 0
    for order in orders:
        num = order["purchaseOrderNumber"]
        existe = db.table("pedidos").select("id").eq("pedido_amazon", num).execute().data
        if existe:
            continue

        prazo_ack = datetime.utcnow() + timedelta(hours=48)
        ped = db.table("pedidos").insert({
            "pedido_amazon": num,
            "loja": order.get("shipToPartyId"),
            "status_amazon": order.get("purchaseOrderState"),
            "prazo_acknowledgment": prazo_ack.isoformat(),
            "status_interno": "pendente",
            "origem": "api",
        }).execute().data[0]

        itens = order.get("orderDetails", {}).get("items", [])
        for item in itens:
            isbn_raw = item.get("vendorProductIdentifier") or item.get("buyerProductIdentifier")
            try:
                isbn = int(isbn_raw)
            except (TypeError, ValueError):
                isbn = None
            qtda = item.get("orderedQuantity", {}).get("amount")
            db.table("itens_pedido").insert({
                "pedido_id": ped["id"],
                "pedido_amazon": num,
                "isbn": isbn,
                "asin": item.get("amazonProductIdentifier"),
                "qtda_solicitada": qtda,
                "custo_unitario": float(item.get("netCost", {}).get("amount", 0) or 0),
                "desconto_amazon": None,
                "status_desconto": "desconhecido",
                "rota": "poa",
            }).execute()
        novos += 1

    return {"pedidos_novos": novos, "total_recebidos": len(orders)}

def enviar_acknowledgment(pedido_id: int, usuario_id: str) -> dict:
    """Envia acknowledgment para a Amazon com base nas decisões do validador."""
    token = _get_access_token()
    db = get_db()

    pedido = db.table("pedidos").select("*").eq("id", pedido_id).single().execute().data
    itens  = db.table("itens_pedido").select("*").eq("pedido_id", pedido_id).execute().data

    items_ack = []
    for item in itens:
        decisao = item.get("decisao") or "aceito"
        cod = item.get("codigo_rejeicao") or ("AC" if decisao == "aceito" else "R2")
        qtda = item.get("qtda_aceita") or item.get("qtda_solicitada") or 0
        items_ack.append({
            "itemSequenceNumber": str(itens.index(item) + 1),
            "amazonProductIdentifier": item.get("asin"),
            "vendorProductIdentifier": str(item.get("isbn")),
            "orderedQuantity": {"amount": item.get("qtda_solicitada"), "unitOfMeasure": "Each"},
            "netCost": {"currencyCode": "BRL", "amount": str(item.get("custo_unitario") or 0)},
            "acknowledgementCode": cod,
            "acknowledgedQuantity": {"amount": qtda, "unitOfMeasure": "Each"},
            "estimatedShipDate": item.get("data_envio_prevista"),
            "estimatedDeliveryDate": item.get("data_envio_prevista"),
        })

    payload = {"acknowledgements": [{
        "purchaseOrderNumber": pedido["pedido_amazon"],
        "sellingParty": {"partyId": get_settings().amazon_vendor_code},
        "acknowledgementDate": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": items_ack,
    }]}

    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json",
    }
    resp = httpx.post(f"{SP_API_BASE}/vendor/orders/v1/acknowledgements", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()

    # Atualiza pedido
    db.table("pedidos").update({
        "status_interno": "enviado",
        "acknowledgment_enviado_em": datetime.utcnow().isoformat(),
        "acknowledgment_resposta": resp.json(),
    }).eq("id", pedido_id).execute()

    db.table("audit_log").insert({
        "usuario_id": usuario_id,
        "acao": "acknowledgment_enviado",
        "entidade": "pedidos",
        "entidade_id": str(pedido_id),
        "detalhe": {"pedido_amazon": pedido["pedido_amazon"], "itens": len(itens)},
    }).execute()

    return {"ok": True, "pedido": pedido["pedido_amazon"], "itens": len(itens)}
