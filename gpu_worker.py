import modal
import os
import subprocess
import shutil

app = modal.App("3d-product-pipeline")

pipeline_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "ffmpeg", "nodejs", "npm")
    .run_commands("npm install -g @gltf-transform/cli")
    .pip_install(
        "torch",
        "torchvision",
        "rembg[gpu]",
        "trimesh",
        "pillow",
        "boto3",
        "numpy"
    )
    .run_commands("python -c 'from rembg import new_session; new_session(\"u2net\")'")
)

@app.function(
    image=pipeline_image,
    gpu="A10G",
    timeout=300,
    scaledown_window=10,
    secrets=[modal.Secret.from_name("r2-secrets")]
)
def process_product_photos(image_bytes_list: list[bytes], job_id: str, target_dimensions: dict = None):
    import trimesh
    import numpy as np
    from rembg import remove, new_session
    import boto3

    work_dir = f"/tmp/{job_id}"
    cleaned_dir = os.path.join(work_dir, "cleaned")
    os.makedirs(cleaned_dir, exist_ok=True)

    session = new_session("u2net")

    for idx, img_bytes in enumerate(image_bytes_list):
        out_path = os.path.join(cleaned_dir, f"clean_{idx}.png")
        clean_bytes = remove(img_bytes, session=session)
        with open(out_path, "wb") as f:
            f.write(clean_bytes)

    raw_glb = os.path.join(work_dir, "raw.glb")
    model_a_local = os.path.join(work_dir, "model_a.glb")
    model_b_local = os.path.join(work_dir, "model_b.glb")

    mesh = trimesh.creation.icosphere(subdivisions=4, radius=1.0)

    if target_dimensions:
        l_cm = target_dimensions.get("length_cm")
        w_cm = target_dimensions.get("width_cm")
        h_cm = target_dimensions.get("height_cm")

        current_extents = mesh.extents
        target_meters = [
            l_cm / 100.0 if l_cm else None,
            w_cm / 100.0 if w_cm else None,
            h_cm / 100.0 if h_cm else None
        ]

        scale_factors = [1.0, 1.0, 1.0]
        if all(v is not None for v in target_meters):
            scale_factors = [target_meters[i] / current_extents[i] for i in range(3)]
        else:
            valid_ratios = [target_meters[i] / current_extents[i] for i in range(3) if target_meters[i] is not None]
            if valid_ratios:
                scale_factors = [valid_ratios[0]] * 3

        transform = np.diag([scale_factors[0], scale_factors[1], scale_factors[2], 1.0])
        mesh.apply_transform(transform)

    mesh.export(raw_glb)
    final_extents_cm = (mesh.extents * 100.0).tolist()

    def optimize_variant(input_path, output_path, max_polys, tex_size):
        m = trimesh.load(input_path, force='mesh')
        if len(m.faces) > max_polys:
            m = m.simplify_quadratic_decimation(max_polys)
        m.fix_normals()
        
        temp_decimated = output_path.replace(".glb", "_temp.glb")
        m.export(temp_decimated)

        cmd = [
            "gltf-transform", "optimize",
            temp_decimated, output_path,
            "--compress", "draco",
            "--texture-compress", "webp",
            "--max-texture-size", str(tex_size)
        ]
        subprocess.run(cmd, check=True)
        if os.path.exists(temp_decimated):
            os.remove(temp_decimated)

    optimize_variant(raw_glb, model_a_local, max_polys=45000, tex_size=2048)
    optimize_variant(raw_glb, model_b_local, max_polys=15000, tex_size=1024)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        endpoint_url=os.environ["R2_ENDPOINT_URL"]
    )
    bucket = os.environ["R2_BUCKET_NAME"]

    s3.upload_file(model_a_local, bucket, f"{job_id}/model_a.glb")
    s3.upload_file(model_b_local, bucket, f"{job_id}/model_b.glb")

    public_base = os.environ["PUBLIC_STORAGE_URL"]
    shutil.rmtree(work_dir)

    return {
        "model_a_url": f"{public_base}/{job_id}/model_a.glb",
        "model_b_url": f"{public_base}/{job_id}/model_b.glb",
        "scaled_extents_cm": {
            "length": round(final_extents_cm[0], 2),
            "width": round(final_extents_cm[1], 2),
            "height": round(final_extents_cm[2], 2)
        }
    }