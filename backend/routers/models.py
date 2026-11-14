"""Inference models offered in the UI, with their last update on Hugging Face."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("/instance-settings")
def instance_settings():
    """Clustering settings of the instance network (from the JSON next to it on Hugging Face)."""
    from services.instance_nn import clustering_settings
    params, source = clustering_settings()
    return {"params": params, "source": source}


@router.get("")
def list_models(refresh: bool = False):
    from services.predictor import model_catalog
    return model_catalog(refresh=refresh)
