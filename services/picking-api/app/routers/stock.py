from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_stock() -> list[dict[str, str]]:  # pragma: no cover - placeholder
    return []
