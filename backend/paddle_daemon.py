import os
import sys
import json
import time
import traceback
from pathlib import Path
from loguru import logger

# Set up logging for the daemon
logger.add("paddle_daemon.log", rotation="10 MB")

def main():
    logger.info("PaddleOCR Daemon starting up...")
    try:
        from paddleocr import PaddleOCR
        # Pre-load the models
        ocr = PaddleOCR(use_angle_cls=True, lang="en", enable_mkldnn=False)
        logger.info("PaddleOCR models loaded and ready.")
    except Exception as e:
        logger.error(f"Failed to initialize PaddleOCR: {e}")
        sys.exit(1)

    # Simple directory-based IPC: watch for .request files
    import tempfile
    request_dir = Path(tempfile.gettempdir()) / "ai_cfo_ocr_queue"
    request_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Watching {request_dir.absolute()} for tasks...")
    
    while True:
        try:
            # Look for *.req files
            requests = list(request_dir.glob("*.req"))
            for req_file in requests:
                logger.info(f"Processing request: {req_file.name}")
                try:
                    with open(req_file, "r") as f:
                        config = json.load(f)
                    
                    img_path = config.get("img_path")
                    out_path = config.get("out_path")
                    
                    result = ocr.ocr(img_path)
                    
                    lines = []
                    if result and result[0]:
                        first_item = result[0]
                        # Handle new PaddleX dict-like OCRResult
                        if hasattr(first_item, 'get') and 'rec_texts' in first_item:
                            texts = first_item.get('rec_texts', [])
                            lines = [str(t).strip() for t in texts if str(t).strip()]
                        else:
                            # Legacy nested list
                            for block in result:
                                if not block: continue
                                for line in block:
                                    try:
                                        text = line[1][0]
                                        if text.strip(): lines.append(text.strip())
                                    except: pass
                    
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump({"text": "\n".join(lines)}, f)
                        
                    logger.info(f"Success: {req_file.name}")
                except Exception as e:
                    logger.error(f"Error processing {req_file.name}: {e}")
                    if "out_path" in locals():
                        with open(out_path, "w") as f:
                            json.dump({"error": str(e), "traceback": traceback.format_exc()}, f)
                finally:
                    # Mark as done by deleting the request file
                    try:
                        req_file.unlink()
                    except:
                        pass
            
            time.sleep(0.5) # Poll every 500ms
        except KeyboardInterrupt:
            logger.info("Daemon shutting down.")
            break
        except Exception as e:
            logger.error(f"Daemon loop error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()
