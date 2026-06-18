import io, openpyxl, pandas as pd
from datetime import datetime
from app.database import get_db

def importar_base_produtos(conteudo: bytes, usuario_id: str) -> dict:
    db = get_db()
    df = pd.read_excel(io.BytesIO(conteudo), dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Mapeamento flexível de colunas
    col_map = {
        "ISBN": ["ISBN", "isbn"],
        "produto": ["Produto", "produto", "Titulo", "TITULO"],
        "editora": ["Editora", "editora", "EDITORA"],
        "status": ["Status", "status", "STATUS"],
        "estoque_sp": ["Estoque SP", "EstoqueSP", "Estoque_SP"],
        "estoque_cl": ["Estoque CL", "EstoqueCL", "Estoque_CL"],
        "preco_venda": ["Preço de Venda", "Preco de Venda", "PrcVenda"],
        "custo_stand": ["Custo Stand", "CustoStand"],
    }

    def get_col(df, opcoes):
        for o in opcoes:
            if o in df.columns:
                return o
        return None

    ok, erros = 0, 0
    upload = db.table("uploads_base").insert({
        "tipo": "produtos",
        "arquivo_nome": "base_produtos.xlsx",
        "total_linhas": len(df),
        "status": "processando",
        "usuario_id": usuario_id,
    }).execute().data[0]

    registros = []
    col_isbn = get_col(df, col_map["ISBN"])
    if not col_isbn:
        db.table("uploads_base").update({"status": "erro", "mensagem_erro": "Coluna ISBN não encontrada"}).eq("id", upload["id"]).execute()
        raise ValueError("Coluna ISBN não encontrada no arquivo")

    for _, row in df.iterrows():
        try:
            isbn = int(float(str(row[col_isbn])))
            reg = {"isbn": isbn}
            for campo, opcoes in col_map.items():
                if campo == "ISBN":
                    continue
                c = get_col(df, opcoes)
                if c and pd.notna(row.get(c)):
                    val = row[c]
                    if campo in ("estoque_sp", "estoque_cl"):
                        reg[campo] = int(float(str(val))) if val not in ("", "nan") else 0
                    elif campo in ("preco_venda", "custo_stand"):
                        reg[campo] = float(str(val).replace(",", ".")) if val not in ("", "nan") else None
                    else:
                        reg[campo] = str(val).strip()
            registros.append(reg)
            ok += 1
        except Exception:
            erros += 1

    # Upsert em lotes de 500
    LOTE = 500
    for i in range(0, len(registros), LOTE):
        db.table("base_produtos").upsert(registros[i:i+LOTE]).execute()

    db.table("uploads_base").update({
        "status": "concluido",
        "linhas_ok": ok,
        "linhas_erro": erros,
        "concluido_em": datetime.utcnow().isoformat(),
    }).eq("id", upload["id"]).execute()

    return {"ok": ok, "erros": erros, "total": len(df)}

def importar_base_p12(conteudo: bytes, usuario_id: str) -> dict:
    db = get_db()
    df = pd.read_excel(io.BytesIO(conteudo), dtype=str)
    df.columns = [c.strip() for c in df.columns]

    upload = db.table("uploads_base").insert({
        "tipo": "p12",
        "arquivo_nome": "base_p12.xlsx",
        "total_linhas": len(df),
        "status": "processando",
        "usuario_id": usuario_id,
    }).execute().data[0]

    col_rename = {
        "Filial": "filial",
        "Descricao": "descricao",
        "Prc Lista": "prc_lista",
        "Prc Unitario": "prc_unitario",
        "Quantidade": "quantidade",
        "Vlr.Total": "vlr_total",
        "% Desconto": "pct_desconto",
        "Qtd.Entregue": "qtd_entregue",
        "Ped Cliente": "ped_cliente",
        "Entrega": "entrega",
        "Vlr Desconto": "vlr_desconto",
        "Num. Pedido": "num_pedido",
        "Nota Fiscal": "nota_fiscal",
        "Item": "item",
        "Produto": "produto",
        "Tipo Saida": "tipo_saida",
    }
    df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns}, inplace=True)

    # Limpa tabela atual e reinsere (é uma base que substitui a anterior)
    db.table("base_p12").delete().neq("id", 0).execute()

    registros = df.where(pd.notnull(df), None).to_dict(orient="records")

    LOTE = 1000
    ok = 0
    for i in range(0, len(registros), LOTE):
        db.table("base_p12").insert(registros[i:i+LOTE]).execute()
        ok += len(registros[i:i+LOTE])

    db.table("uploads_base").update({
        "status": "concluido",
        "linhas_ok": ok,
        "linhas_erro": 0,
        "concluido_em": datetime.utcnow().isoformat(),
    }).eq("id", upload["id"]).execute()

    return {"ok": ok, "total": len(df)}
