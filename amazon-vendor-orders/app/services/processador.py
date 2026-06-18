"""
Processa XLS de pedido Amazon:
- Lê colunas do arquivo
- Valida descontos contra tabela do banco
- Roteia por POA / SP-POD / Especial / Erro
- Salva pedido + itens no Supabase
"""
import io, openpyxl
from datetime import datetime, timedelta
from app.database import get_db

TOLERANCE = 0.003

def _carregar_descontos():
    db = get_db()
    rows = db.table("descontos_editora").select("*").eq("ativo", True).execute().data
    return {r["editora"].upper(): r for r in rows}

def _validar_desconto(editora, desc_amazon, descontos):
    if not editora:
        return "desconhecido", None
    upper = str(editora).upper().strip()
    match = next((v for k, v in descontos.items() if k in upper or upper in k), None)
    if not match:
        return "desconhecido", None
    try:
        desc = float(str(desc_amazon))
    except (ValueError, TypeError):
        return "outro", f"Desconto não numérico: {desc_amazon}"
    padrao   = float(match["desconto_padrao"])
    especial = float(match["desconto_especial"])
    if abs(desc - padrao) <= TOLERANCE:
        return "padrao", None
    elif abs(desc - especial) <= TOLERANCE:
        return "especial", f"Desconto especial {desc:.1%} — confirmar por e-mail"
    else:
        return "outro", f"Desconto {desc:.1%} ≠ padrão ({padrao:.1%}) nem especial ({especial:.1%})"

def processar_pedido_amazon(conteudo_bytes: bytes, usuario_id: str) -> dict:
    db = get_db()
    descontos = _carregar_descontos()

    wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Arquivo vazio")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    idx = {h: i for i, h in enumerate(headers)}

    def g(row, col, default=None):
        i = idx.get(col)
        return row[i] if i is not None and i < len(row) else default

    pedidos_criados = []
    itens_criados = 0

    # Agrupa por número de pedido
    grupos: dict[str, list] = {}
    for row in rows[1:]:
        num = str(g(row, "Pedido de compra") or g(row, "Purchase Order Number") or "")
        if num:
            grupos.setdefault(num, []).append(row)

    for num_pedido, linhas in grupos.items():
        primeira = linhas[0]
        loja = g(primeira, "Local de entrega") or g(primeira, "Ship To Location")
        fim_janela_raw = g(primeira, "Janela de entrega - Data de encerramento")
        fim_janela = fim_janela_raw if isinstance(fim_janela_raw, datetime) else None
        prazo_ack = datetime.utcnow() + timedelta(hours=48)

        # Verifica se pedido já existe
        existe = db.table("pedidos").select("id").eq("pedido_amazon", num_pedido).execute().data
        if existe:
            pedido_id = existe[0]["id"]
        else:
            ped = db.table("pedidos").insert({
                "pedido_amazon": num_pedido,
                "loja": loja,
                "prazo_fim": fim_janela.isoformat() if fim_janela else None,
                "prazo_acknowledgment": prazo_ack.isoformat(),
                "status_interno": "pendente",
                "origem": "upload",
            }).execute()
            pedido_id = ped.data[0]["id"]
            pedidos_criados.append(num_pedido)

        for row in linhas:
            isbn_raw = g(row, "ID externa") or g(row, "External ID")
            try:
                isbn = int(float(str(isbn_raw))) if isbn_raw else None
            except (ValueError, TypeError):
                isbn = None

            editora_raw = None
            qtda = g(row, "Quantidade solicitada") or g(row, "Ordered Quantity")
            desc  = g(row, "Desconto") or g(row, "Discount")
            custo = g(row, "Custo líquido") or g(row, "Net Cost")
            tipo_est = ""
            disponib = g(row, "Disponibilidade") or ""

            # Busca dados do produto
            produto = None
            if isbn:
                r = db.table("base_produtos").select("*").eq("isbn", isbn).execute().data
                if r:
                    produto = r[0]
                    editora_raw = produto.get("editora")
                    tipo_est = produto.get("status", "")

            status_desc, alerta = _validar_desconto(editora_raw, desc, descontos)

            # Roteamento
            if tipo_est == "POD":
                rota = "sp_pod"
            else:
                rota = "poa"

            db.table("itens_pedido").insert({
                "pedido_id": pedido_id,
                "pedido_amazon": num_pedido,
                "isbn": isbn,
                "nome_produto": produto.get("produto") if produto else g(row, "Titulo") or g(row, "Title"),
                "editora": editora_raw,
                "disponibilidade_amazon": str(disponib),
                "qtda_solicitada": int(qtda) if qtda else None,
                "custo_unitario": float(custo) if custo else None,
                "desconto_amazon": float(desc) if desc else None,
                "status_produto": tipo_est,
                "estoque_disponivel": produto.get("estoque_total") if produto else None,
                "qtda_a_faturar": int(qtda) if qtda else None,
                "rota": rota,
                "status_desconto": status_desc,
                "alerta_desconto": alerta,
            }).execute()
            itens_criados += 1

    # Audit
    db.table("audit_log").insert({
        "usuario_id": usuario_id,
        "acao": "upload_pedido",
        "entidade": "pedidos",
        "detalhe": {"pedidos_novos": pedidos_criados, "itens": itens_criados},
    }).execute()

    return {
        "pedidos_novos": len(pedidos_criados),
        "pedidos_ja_existentes": len(grupos) - len(pedidos_criados),
        "itens_criados": itens_criados,
    }
