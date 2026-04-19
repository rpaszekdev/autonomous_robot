"""describe_scene tool — Camera snapshot + vision prompt."""

import logging

logger = logging.getLogger(__name__)

_camera_instance = None
_llama_url = None


def set_camera(camera):
    global _camera_instance
    _camera_instance = camera


def set_llama_url(url: str):
    global _llama_url
    _llama_url = url


def tool_describe_scene(focus: str = None, **kwargs) -> dict:
    """Take a fresh camera snapshot and return scene description."""
    if _camera_instance is None:
        return {"error": "Camera not available"}

    try:
        image_b64 = _camera_instance.capture_base64()
    except Exception as e:
        logger.error("Camera capture failed: %s", e)
        return {"error": f"Camera failed: {e}"}

    prompt = "Describe what you see in this image concisely."
    if focus:
        prompt = f"Focus on '{focus}' in this image and describe what you see."

    # If llama.cpp is available, use it for vision description
    if _llama_url:
        import requests
        import json
        try:
            resp = requests.post(
                f"{_llama_url}/v1/chat/completions",
                json={
                    "messages": [
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }},
                        ]},
                    ],
                    "max_tokens": 128,
                },
                timeout=15,
            )
            data = resp.json()
            description = data["choices"][0]["message"]["content"]
            return {"description": description}
        except Exception as e:
            logger.error("Vision LLM call failed: %s", e)
            return {"error": str(e), "image_captured": True}

    return {"image_captured": True, "note": "No LLM available for description"}
