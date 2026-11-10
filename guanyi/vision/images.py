"""Validate and normalize a user-selected screenshot, without screen capture."""

import base64
import hashlib
import io
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from .config import MAX_EDGE


class ImageInputError(ValueError):
    pass


@dataclass(frozen=True)
class ImageFrame:
    png: bytes
    source_name: str
    original_size: tuple
    size: tuple
    source_sha256: str

    @property
    def sha256(self):
        return hashlib.sha256(self.png).hexdigest()

    @property
    def data_uri(self):
        return "data:image/png;base64," + base64.b64encode(self.png).decode("ascii")

    def metadata(self):
        return {"source_name": self.source_name, "original_size": list(self.original_size),
                "submitted_size": list(self.size), "source_sha256": self.source_sha256,
                "submitted_sha256": self.sha256, "submitted_bytes": len(self.png)}


def prepare_image(path, max_edge=MAX_EDGE):
    """Limit file/pixel size, apply orientation, remove metadata, encode PNG."""
    try:
        path = Path(path)
        if not path.is_file():
            raise ImageInputError("找不到截图文件，请重新选择")
        with path.open("rb") as stream:
            raw = stream.read(20 * 1024 * 1024 + 1)
        if len(raw) > 20 * 1024 * 1024:
            raise ImageInputError("图片超过20 MB，请裁剪为游戏区域后再识别")
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ("PNG", "JPEG", "WEBP", "BMP"):
                    raise ImageInputError("请使用 PNG、JPEG、WebP 或 BMP 静态图片")
                if getattr(source, "n_frames", 1) != 1:
                    raise ImageInputError("暂不支持动画或多帧图片，请先导出一帧")
                if min(source.size) < 64 or source.width * source.height > 40_000_000:
                    raise ImageInputError("图片过小或像素过多，请选用清晰的游戏截图（至少64×64，最多4000万像素）")
                original_size = source.size
                oriented = ImageOps.exif_transpose(source)
                # Flatten transparency on white and copy pixels to omit EXIF/text metadata.
                rgba = oriented.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
                image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                extrema = image.getextrema()
                if all(high <= 8 for low, high in extrema) or all(low >= 247 for low, high in extrema):
                    raise ImageInputError("图片接近纯黑或纯白，没有可识别内容，请换一张游戏截图")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
        return ImageFrame(buffer.getvalue(), path.name, original_size, image.size,
                          hashlib.sha256(raw).hexdigest())
    except ImageInputError:
        raise
    except (OSError, ValueError, TypeError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageInputError("无法读取这张图片，请检查文件是否损坏或换一张截图") from exc
