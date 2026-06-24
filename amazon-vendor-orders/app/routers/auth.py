import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import get_settings
from app.database import get_db

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login(body: LoginRequest):
    s = get_settings()
    url = f"{s.supabase_url}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": s.supabase_service_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(url, json={"email": body.email, "password": body.password}, headers=headers, timeout=15)

    print(f"SUPABASE AUTH: {r.status_code} -> {r.text[:300]}")

    if r.status_code != 200:
        detail = r.json().get("error_description") or r.json().get("msg") or r.text
        raise HTTPException(status_code=401, detail=detail)

    data = r.json()
    user_id = data["user"]["id"]

    db = get_db()
    perfil = db.table("perfis").select("*").eq("id", user_id).single().execute()

    return {
        "access_token": data["access_token"],
        "token_type": "bearer",
        "usuario": {
            "id": user_id,
            "email": data["user"]["email"],
            "nome": perfil.data.get("nome") if perfil.data else None,
            "role": perfil.data.get("role") if perfil.data else None,
        }
    }

@router.post("/logout")
def logout():
    return {"ok": True}
