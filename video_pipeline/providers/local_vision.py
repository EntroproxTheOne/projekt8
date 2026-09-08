from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter


class LocalVisionProvider:
    provider_name = "local-vision"

    def run(self, operation: str, input_path: Path, output_path: Path, **kwargs: Any) -> dict[str, Any]:
        if operation == "hide_faces":
            return self.hide_faces(input_path, output_path, blur_radius=int(kwargs.get("blur_radius", 18)))
        if operation == "background_blur":
            return self.background_blur(input_path, output_path, blur_radius=int(kwargs.get("blur_radius", 10)))
        raise ValueError(f"Unsupported local vision operation: {operation}")

    def hide_faces(self, input_path: Path, output_path: Path, blur_radius: int = 18) -> dict[str, Any]:
        image = Image.open(input_path).convert("RGB")
        faces = _detect_faces(input_path)
        if not faces:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path)
            return {"faces_detected": 0, "output_path": str(output_path)}
        result = image.copy()
        for x, y, w, h in faces:
            crop = result.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(blur_radius))
            result.paste(crop, (x, y))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path)
        return {"faces_detected": len(faces), "output_path": str(output_path)}

    def background_blur(self, input_path: Path, output_path: Path, blur_radius: int = 10) -> dict[str, Any]:
        image = Image.open(input_path).convert("RGB")
        image.filter(ImageFilter.GaussianBlur(blur_radius)).save(output_path)
        return {"operation": "background_blur", "output_path": str(output_path)}


def _detect_faces(input_path: Path) -> list[tuple[int, int, int, int]]:
    try:
        import cv2  # type: ignore
    except Exception:
        return []
    image = cv2.imread(str(input_path))
    if image is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade_path = getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
