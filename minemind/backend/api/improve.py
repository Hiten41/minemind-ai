from fastapi import APIRouter, Depends

from services.auth_service import current_user, user_dataset_names
from services.advanced_ai import user_memory_profile
from services.cognee_service import enrich_memory

router = APIRouter()


@router.post("/api/improve")
async def improve_memory(user: dict[str, str] = Depends(current_user)):
    success = await enrich_memory(user_dataset_names(user["id"]))
    profile = user_memory_profile(user["id"])
    return {
        "status": "success" if success else "failed",
        "message": "Memory enriched" if success
                   else "Enrichment failed",
        "profile": profile,
        "improvements": [
            "Refreshed Cognee memory enrichment",
            "Rebuilt user document intelligence profile",
            "Extracted mining risk signals and top entities",
        ],
    }
