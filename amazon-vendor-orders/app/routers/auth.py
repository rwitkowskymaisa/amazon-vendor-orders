from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
def login(body: LoginRequest):
    """Autentica via Supabase Auth e retorna token JWT."""
    db = get_db()
    try:
                resp = db.auth.sign_in_with_password({"email": body.email, "password": body.password})
        user = resp.user
        session = resp.session
        perfil = db.table("perfis").select("*").eq("id", user.id).single().execute()
        return {
            "access_token": session.access_token,
            "token_type": "bearer",
            "usuario": {
                "id": user.id,
                "email": user.email,
                "nome": perfil.data.get("nome"),
                "role": perfil.data.get("role"),
            }
        }
    except Exception as e:
        print(f"ERRO LOGIN: {type(e).__name__}: {e}")
        raise HTTPException(status_code=401, detail=f"Erro: {str(e)}")

@router.post("/logout")
def logout():
    return {"ok": True}
