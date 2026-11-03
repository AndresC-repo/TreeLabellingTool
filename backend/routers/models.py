"""Inference models offered in the UI, with their last update on Hugging Face."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("")
def list_models(refresh: bool = False):
    from services.predictor import model_catalog
    return model_catalog(refresh=refresh)
