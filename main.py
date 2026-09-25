import uuid
import os
import traceback
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import modal

app = FastAPI(title="3D Product Generator API")

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
    file1: UploadFile = File(..., description="Primary photo (Required)"),
    file2: Optional[UploadFile] = File(None, description="Angle photo 2 (Optional)"),
    file3: Optional[UploadFile] = File(None, description="Angle photo 3 (Optional)"),
    file4: Optional[UploadFile] = File(None, description="Angle photo 4 (Optional)"),
    file5: Optional[UploadFile] = File(None, description="Angle photo 5 (Optional)"),
    file6: Optional[UploadFile] = File(None, description="Angle photo 6 (Optional)"),
    file7: Optional[UploadFile] = File(None, description="Angle photo 7 (Optional)"),
    file8: Optional[UploadFile] = File(None, description="Angle photo 8 (Optional)"),
    file9: Optional[UploadFile] = File(None, description="Angle photo 9 (Optional)"),
    file10: Optional[UploadFile] = File(None, description="Angle photo 10 (Optional)"),
    length_cm: Optional[float] = Form(None),
    width_cm: Optional[float] = Form(None),
    height_cm: Optional[float] = Form(None)
):
    try:
        all_inputs = [file1, file2, file3, file4, file5, file6, file7, file8, file9, file10]
        uploaded_files = [f for f in all_inputs if f is not None and getattr(f, "filename", "")]

        if not uploaded_files:
            raise HTTPException(status_code=400, detail="At least one valid image file is required.")

        # Read uploaded photo bytes
        image_bytes_list = []
        for file in uploaded_files:
            content = await file.read()
            image_bytes_list.append(content)

        job_id = str(uuid.uuid4())
        dimensions = {
            "length_cm": length_cm,
            "width_cm": width_cm,
            "height_cm": height_cm
        }

        # Updated line for Modal lookup syntax:
        gpu_func = modal.Function.from_name("3d-product-pipeline", "process_product_photos")
        result = gpu_func.remote(image_bytes_list, job_id, dimensions)
        
        return {
            "job_id": job_id,
            "status": "completed",
            "model_a_url": result.get("model_a_url"),
            "model_b_url": result.get("model_b_url"),
            "dimensions_cm": result.get("scaled_extents_cm")
        }
    except HTTPException:
        raise
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"Error processing 3D generation: {error_details}")
        raise HTTPException(
            status_code=500, 
            detail=f"GPU Processing failed: {str(e)}"
        )