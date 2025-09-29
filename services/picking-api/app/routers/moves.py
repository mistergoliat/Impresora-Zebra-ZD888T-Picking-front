from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def create_move() -> dict[str, str]:  # pragma: no cover - placeholder
    return {"status": "not_implemented"}


@router.post("/{move_id}/confirm")
async def confirm_move(move_id: str) -> dict[str, str]:  # pragma: no cover - placeholder
    return {"move_id": move_id, "status": "not_implemented"}
