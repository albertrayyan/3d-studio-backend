import uuid
import os
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import modal

# Explicitly setting OpenAPI 3.0.2 ensures Swagger UI renders standard file pickers
app = FastAPI(
    title="3D Product Generator API",
    openapi_version="3.0.2"
)

# Allow CORS requests from frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "3D Generator API is active"}

@app.post("/generate-3d")
async def generate_3d(
    files: List[UploadFile] = File(..., description="Upload product photos"),
    length_cm: Optional[float] = Form(None),
    width_cm: Optional[float] = Form(None),
    height_cm: Optional[float] = Form(None)
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one image file is required.")

    # Read uploaded photo bytes
    image_bytes_list = []
    for file in files:
        content = await file.read()
        image_bytes_list.append(content)

    job_id = str(uuid.uuid4())
    dimensions = {
        "length_cm": length_cm,
        "width_cm": width_cm,
        "height_cm": height_cm
    }

    try:
        # Lookup deployed Modal worker
        gpu_func = modal.Function.lookup("3d-product-pipeline", "process_product_photos")
        
        # Trigger GPU processing remotely
        result = gpu_func.remote(image_bytes_list, job_id, dimensions)
        
        return {
            "job_id": job_id,
            "status": "completed",
            "model_a_url": result["model_a_url"],
            "model_b_url": result["model_b_url"],
            "dimensions_cm": result["scaled_extents_cm"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")