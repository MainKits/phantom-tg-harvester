from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import httpx
import os
import uuid
import asyncio
import subprocess

router = APIRouter(prefix="/api/media", tags=["media"])

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media_temp")
os.makedirs(MEDIA_DIR, exist_ok=True)

async def cleanup_file(filepath: str, delay: int = 300):
    """Delete file after a delay."""
    await asyncio.sleep(delay)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except:
            pass

async def uniqualize_media_logic(input_path: str, aggressiveness: int, frame_style: str) -> str:
    """Internal logic to uniqualize a file using FFmpeg. Returns the output path."""
    file_ext = os.path.splitext(input_path)[1].lower()
    is_video = file_ext in [".mp4", ".mov", ".avi"]
    
    task_id = str(uuid.uuid4())
    output_path = os.path.join(MEDIA_DIR, f"out_{task_id}{file_ext}")
    
    try:
        if is_video:
            speed_multiplier = [1.01, 1.02, 1.03][aggressiveness - 1]
            brightness = [0.01, 0.02, 0.03][aggressiveness - 1]
            saturation = [1.05, 1.10, 1.15][aggressiveness - 1]
            noise_level = [1, 2, 4][aggressiveness - 1]
            
            vf = f"setpts={1/speed_multiplier}*PTS,crop=iw-4:ih-4,eq=brightness={brightness}:saturation={saturation},noise=alls={noise_level}:allf=t+u"
            af = f"atempo={speed_multiplier}"
            
            if frame_style == "blur":
                cmd = ["ffmpeg", "-y", "-i", input_path, "-filter_complex", 
                       f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[bg];[0:v]setpts={1/speed_multiplier}*PTS,scale=1080:1920:force_original_aspect_ratio=decrease,eq=brightness={brightness}:saturation={saturation},noise=alls={noise_level}:allf=t+u[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2", 
                       "-af", af, "-map_metadata", "-1"]
            elif frame_style == "neon":
                cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", 
                       f"eq=brightness={brightness},noise=alls={noise_level}:allf=t+u,pad=iw+20:ih+20:10:10:color=magenta", 
                       "-af", af, "-map_metadata", "-1"]
            elif frame_style == "casino":
                cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", 
                       f"eq=brightness={brightness},noise=alls={noise_level}:allf=t+u,pad=iw+16:ih+16:8:8:color=gold", 
                       "-af", af, "-map_metadata", "-1"]
            else:
                cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf, "-af", af, "-map_metadata", "-1"]
                
            cmd.extend(["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-profile:v", "high", "-c:a", "aac", "-b:a", "192k"])
        else:
            noise_level = [2, 4, 6][aggressiveness - 1]
            brightness = [0.02, 0.04, 0.06][aggressiveness - 1]
            saturation = [1.05, 1.10, 1.15][aggressiveness - 1]
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"crop=iw-2:ih-2,eq=brightness={brightness}:saturation={saturation},noise=alls={noise_level}:allf=t+u", "-map_metadata", "-1", "-q:v", "2"]
            
        cmd.append(output_path)
        
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg failed: {stderr.decode()}")
        return output_path
    except Exception as e:
        if os.path.exists(output_path): os.remove(output_path)
        raise e

@router.get("/tiktok-info")
async def get_tiktok_info(url: str):
    """Fetch TikTok video info without watermark using tikwm API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://tikwm.com/api/?url={url}")
            data = response.json()
            if data.get("code") == 0:
                vid_data = data["data"]
                return {"success": True, "title": vid_data.get("title", "TikTok Video"), "cover": vid_data.get("cover"), "play_url": vid_data.get("play"), "author": vid_data.get("author", {}).get("nickname", "Unknown")}
            else:
                raise HTTPException(status_code=400, detail="Could not fetch TikTok info.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/uniqualize")
async def uniqualize_media(background_tasks: BackgroundTasks, file: UploadFile = File(...), aggressiveness: int = Form(1), frame_style: str = Form("none")):
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".mp4", ".mov", ".avi", ".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    task_id = str(uuid.uuid4())
    input_path = os.path.join(MEDIA_DIR, f"in_{task_id}{file_ext}")
    content = await file.read()
    with open(input_path, "wb") as f:
        f.write(content)
        
    try:
        output_path = await uniqualize_media_logic(input_path, aggressiveness, frame_style)
        background_tasks.add_task(cleanup_file, input_path, 10)
        background_tasks.add_task(cleanup_file, output_path, 600)
        return FileResponse(output_path, filename=f"unique_{file.filename}", media_type="video/mp4" if file_ext in [".mp4", ".mov", ".avi"] else "image/jpeg")
    except Exception as e:
        if os.path.exists(input_path): os.remove(input_path)
        raise HTTPException(status_code=500, detail=str(e))
