from fastapi import APIRouter, Depends

from app.auth import get_current_user

router = APIRouter()


@router.get("/me")
def read_current_user(user_id: str = Depends(get_current_user)) -> dict:
    return {"user_id": user_id}
