from __future__ import annotations

import ast
import base64
import json
import math
import re
import struct
from dataclasses import dataclass
from typing import Any

import numpy as np
from skimage import measure


MIN_RESOLUTION = 32
MAX_RESOLUTION = 72
DEFAULT_RESOLUTION = 48
MIN_PERIODS = 1
MAX_PERIODS = 4
DEFAULT_PERIODS = 2
MIN_ISO_LEVEL = -1.0
MAX_ISO_LEVEL = 1.0
DEFAULT_ISO_LEVEL = 0.0
MAX_EXPRESSION_LENGTH = 500
MAX_CONSTANT_ABS = 1_000_000
MAX_POWER_EXPONENT_ABS = 12
MAX_GLB_BYTES = 4_000_000

SURFACE_TYPES = {
    "gyroid",
    "schwarz_p",
    "diamond",
    "neovius",
    "lidinoid",
    "custom_explicit",
    "custom_implicit",
}
COLORING_MODES = {"normal", "height", "radial", "curvature", "none"}
COLORMAPS = {"viridis", "plasma", "coolwarm", "rainbow"}

ALLOWED_NAMES = {
    "sin",
    "cos",
    "tan",
    "sqrt",
    "abs",
    "exp",
    "log",
    "log2",
    "log10",
    "asin",
    "acos",
    "atan",
    "atan2",
    "sinh",
    "cosh",
    "tanh",
    "pi",
    "e",
    "x",
    "y",
    "z",
}
ALLOWED_NODE_TYPES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Mod,
    ast.Load,
)
SAFE_NAMESPACE: dict[str, Any] = {
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "exp": np.exp,
    "log": np.log,
    "log2": np.log2,
    "log10": np.log10,
    "asin": np.arcsin,
    "acos": np.arccos,
    "atan": np.arctan,
    "atan2": np.arctan2,
    "sinh": np.sinh,
    "cosh": np.cosh,
    "tanh": np.tanh,
    "pi": np.pi,
    "e": np.e,
}


@dataclass(frozen=True)
class SurfaceRequest:
    surface_type: str = "gyroid"
    periods: int = DEFAULT_PERIODS
    resolution: int = DEFAULT_RESOLUTION
    iso_level: float = DEFAULT_ISO_LEVEL
    expression: str = ""
    coloring: str = "normal"
    colormap: str = "viridis"


@dataclass(frozen=True)
class GeometryResult:
    summary: str
    file_name: str
    mime_type: str
    base64_bytes: str


class GeometryError(ValueError):
    pass


def normalize_request(raw: dict[str, Any]) -> SurfaceRequest:
    surface_type = str(raw.get("surface_type") or "gyroid").lower().strip()
    if surface_type not in SURFACE_TYPES:
        surface_type = "gyroid"

    periods = int(_clamp(raw.get("periods", DEFAULT_PERIODS), DEFAULT_PERIODS, MIN_PERIODS, MAX_PERIODS))
    resolution = int(_clamp(raw.get("resolution", DEFAULT_RESOLUTION), DEFAULT_RESOLUTION, MIN_RESOLUTION, MAX_RESOLUTION))
    iso_level = float(_clamp(raw.get("iso_level", DEFAULT_ISO_LEVEL), DEFAULT_ISO_LEVEL, MIN_ISO_LEVEL, MAX_ISO_LEVEL))

    expression = raw.get("expression") or ""
    expression = _clean_expression(str(expression))

    coloring = str(raw.get("coloring") or "normal").lower().strip()
    if coloring not in COLORING_MODES:
        coloring = "normal"

    colormap = str(raw.get("colormap") or "viridis").lower().strip()
    if colormap not in COLORMAPS:
        colormap = "viridis"

    return SurfaceRequest(
        surface_type=surface_type,
        periods=periods,
        resolution=resolution,
        iso_level=iso_level,
        expression=expression,
        coloring=coloring,
        colormap=colormap,
    )


def generate_geometry(request: SurfaceRequest) -> GeometryResult:
    volume, spacing, label = _build_scalar_field(request)

    try:
        vertices, faces, normals, _ = measure.marching_cubes(
            volume,
            level=request.iso_level,
            spacing=spacing,
        )
    except ValueError as exc:
        raise GeometryError(
            "No surface was generated. Try an iso_level closer to 0 or a simpler expression."
        ) from exc

    if len(faces) == 0:
        raise GeometryError("No surface was generated. Try a different iso_level.")

    vertices = _center_vertices(vertices.astype(np.float32))
    faces = faces.astype(np.uint32)
    normals = normals.astype(np.float32)
    colors = _compute_colors(vertices, faces, normals, request.coloring, request.colormap)
    glb = _build_glb(vertices, normals, faces, colors)

    if len(glb) > MAX_GLB_BYTES:
        raise GeometryError(
            f"Generated GLB is too large ({len(glb) / 1_000_000:.1f} MB). "
            "Lower the resolution and try again."
        )

    safe_name = _safe_file_name(label)
    color_text = "" if request.coloring == "none" else f", {request.coloring}-colored"
    if request.coloring not in {"none", "normal"}:
        color_text += f" with {request.colormap}"

    summary = (
        f"Generated {label} ({request.resolution}^3 grid, "
        f"{len(vertices):,} vertices, {len(faces):,} triangles{color_text})."
    )

    return GeometryResult(
        summary=summary,
        file_name=f"{safe_name}.glb",
        mime_type="model/gltf-binary",
        base64_bytes=base64.b64encode(glb).decode("ascii"),
    )


def validate_expression(expression: str) -> str | None:
    if len(expression) > MAX_EXPRESSION_LENGTH:
        return f"Expression is too long. Maximum length is {MAX_EXPRESSION_LENGTH} characters."

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return "Expression has invalid syntax."

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in ALLOWED_NAMES:
                return f"Disallowed name: {node.id}."
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return "Only simple math function calls are allowed."
            if node.func.id not in ALLOWED_NAMES:
                return f"Disallowed function: {node.func.id}."
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                return "Only numeric constants are allowed."
            if abs(float(node.value)) > MAX_CONSTANT_ABS:
                return f"Numeric constants must be no larger than {MAX_CONSTANT_ABS:g}."
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = node.right
            if not isinstance(exponent, ast.Constant) or not isinstance(exponent.value, (int, float)):
                return "Exponents must be numeric constants."
            if abs(float(exponent.value)) > MAX_POWER_EXPONENT_ABS:
                return f"Exponent magnitude must be no larger than {MAX_POWER_EXPONENT_ABS:g}."
        elif not isinstance(node, ALLOWED_NODE_TYPES):
            return "Expression contains an unsupported operation."

    return None


def safe_eval_expression(expression: str, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    error = validate_expression(expression)
    if error:
        raise GeometryError(f"Invalid expression: {error}")

    code = compile(expression, "<surface-expression>", "eval")
    value = eval(code, {"__builtins__": {}}, {**SAFE_NAMESPACE, "x": x, "y": y, "z": z})
    return np.nan_to_num(np.asarray(value, dtype=np.float64), nan=0.0, posinf=1e6, neginf=-1e6)


def _build_scalar_field(request: SurfaceRequest) -> tuple[np.ndarray, tuple[float, float, float], str]:
    if request.surface_type == "custom_explicit":
        return _custom_explicit_field(request)
    if request.surface_type == "custom_implicit":
        return _custom_implicit_field(request)

    scale = 2.0 * math.pi * request.periods
    half = scale / 2.0
    lin = np.linspace(-half, half, request.resolution)
    x, y, z = np.meshgrid(lin, lin, lin, indexing="ij")

    if request.surface_type == "gyroid":
        volume = np.sin(x) * np.cos(y) + np.sin(y) * np.cos(z) + np.sin(z) * np.cos(x)
    elif request.surface_type == "schwarz_p":
        volume = np.cos(x) + np.cos(y) + np.cos(z)
    elif request.surface_type == "diamond":
        volume = (
            np.sin(x) * np.sin(y) * np.sin(z)
            + np.sin(x) * np.cos(y) * np.cos(z)
            + np.cos(x) * np.sin(y) * np.cos(z)
            + np.cos(x) * np.cos(y) * np.sin(z)
        )
    elif request.surface_type == "neovius":
        volume = 3.0 * (np.cos(x) + np.cos(y) + np.cos(z)) + 4.0 * np.cos(x) * np.cos(y) * np.cos(z)
    elif request.surface_type == "lidinoid":
        volume = (
            0.5
            * (
                np.sin(2 * x) * np.cos(y) * np.sin(z)
                + np.sin(2 * y) * np.cos(z) * np.sin(x)
                + np.sin(2 * z) * np.cos(x) * np.sin(y)
            )
            - 0.5
            * (
                np.cos(2 * x) * np.cos(2 * y)
                + np.cos(2 * y) * np.cos(2 * z)
                + np.cos(2 * z) * np.cos(2 * x)
            )
            + 0.15
        )
    else:
        raise GeometryError(f"Unsupported surface type: {request.surface_type}")

    step = scale / (request.resolution - 1)
    return volume, (step, step, step), request.surface_type


def _custom_explicit_field(request: SurfaceRequest) -> tuple[np.ndarray, tuple[float, float, float], str]:
    if not request.expression:
        raise GeometryError("Custom explicit surfaces require an expression like: z = sin(x) * cos(y).")

    scale = 10.0
    half = scale / 2.0
    lin = np.linspace(-half, half, request.resolution)
    x2d, y2d = np.meshgrid(lin, lin, indexing="ij")
    z_dummy = np.zeros_like(x2d)
    fxy = safe_eval_expression(request.expression, x2d, y2d, z_dummy)

    if fxy.shape != x2d.shape:
        raise GeometryError("Explicit expression must produce a 2-D z = f(x, y) surface.")

    z_min = float(np.nanmin(fxy)) - 1.0
    z_max = float(np.nanmax(fxy)) + 1.0
    if not np.isfinite(z_min) or not np.isfinite(z_max) or z_max <= z_min:
        raise GeometryError("Expression produced degenerate values.")

    z_line = np.linspace(z_min, z_max, request.resolution)
    volume = z_line[np.newaxis, np.newaxis, :] - fxy[:, :, np.newaxis]
    step_xy = scale / (request.resolution - 1)
    step_z = (z_max - z_min) / (request.resolution - 1)
    return volume, (step_xy, step_xy, step_z), f"z={request.expression}"


def _custom_implicit_field(request: SurfaceRequest) -> tuple[np.ndarray, tuple[float, float, float], str]:
    if not request.expression:
        raise GeometryError("Custom implicit surfaces require an expression like: x**2 + y**2 + z**2 - 4.")

    scale = 10.0
    half = scale / 2.0
    lin = np.linspace(-half, half, request.resolution)
    x, y, z = np.meshgrid(lin, lin, lin, indexing="ij")
    volume = safe_eval_expression(request.expression, x, y, z)

    if volume.shape != x.shape:
        raise GeometryError("Implicit expression must produce a 3-D scalar field.")

    step = scale / (request.resolution - 1)
    return volume, (step, step, step), f"F={request.expression}"


def _compute_colors(
    vertices: np.ndarray,
    faces: np.ndarray,
    normals: np.ndarray,
    mode: str,
    colormap: str,
) -> np.ndarray | None:
    if mode == "none":
        return None
    if mode == "normal":
        colors = np.clip((normals + 1.0) * 0.5, 0.0, 1.0)
    elif mode == "height":
        colors = _apply_colormap(_normalize(vertices[:, 2]), colormap)
    elif mode == "radial":
        colors = _apply_colormap(_normalize(np.linalg.norm(vertices, axis=1)), colormap)
    elif mode == "curvature":
        colors = _apply_colormap(_normalize(_approximate_curvature(vertices, faces, normals)), colormap)
    else:
        colors = np.clip((normals + 1.0) * 0.5, 0.0, 1.0)

    return np.power(np.clip(colors, 0.0, 1.0), 2.2).astype(np.float32)


def _approximate_curvature(vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray) -> np.ndarray:
    neighbor_sum = np.zeros_like(vertices, dtype=np.float64)
    valence = np.zeros(vertices.shape[0], dtype=np.float64)

    for col in range(3):
        src = faces[:, col]
        dst1 = faces[:, (col + 1) % 3]
        dst2 = faces[:, (col + 2) % 3]
        np.add.at(neighbor_sum, src, vertices[dst1])
        np.add.at(neighbor_sum, src, vertices[dst2])
        np.add.at(valence, src, 2.0)

    laplacian = (neighbor_sum / np.maximum(valence[:, np.newaxis], 1.0)) - vertices
    return np.sum(laplacian * normals, axis=1)


def _apply_colormap(values: np.ndarray, name: str) -> np.ndarray:
    stops = {
        "viridis": [(0.267, 0.004, 0.329), (0.128, 0.567, 0.551), (0.993, 0.906, 0.144)],
        "plasma": [(0.050, 0.030, 0.528), (0.797, 0.213, 0.476), (0.940, 0.975, 0.131)],
        "coolwarm": [(0.230, 0.299, 0.754), (0.866, 0.866, 0.866), (0.706, 0.016, 0.150)],
        "rainbow": [(1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1), (1, 0, 1)],
    }[name]
    return _gradient(values, stops).astype(np.float32)


def _gradient(values: np.ndarray, stops: list[tuple[float, float, float]]) -> np.ndarray:
    values = np.clip(values, 0.0, 1.0)
    segment_count = len(stops) - 1
    scaled = values * segment_count
    indices = np.minimum(scaled.astype(np.int32), segment_count - 1)
    local_t = (scaled - indices)[:, np.newaxis]
    left = np.asarray([stops[i] for i in indices], dtype=np.float32)
    right = np.asarray([stops[i + 1] for i in indices], dtype=np.float32)
    return left + (right - left) * local_t


def _build_glb(
    vertices: np.ndarray,
    normals: np.ndarray,
    faces: np.ndarray,
    colors: np.ndarray | None,
) -> bytes:
    vertices = np.ascontiguousarray(vertices, dtype=np.float32)
    normals = np.ascontiguousarray(normals, dtype=np.float32)
    indices = np.ascontiguousarray(faces.reshape(-1), dtype=np.uint32)
    color_bytes = b"" if colors is None else np.ascontiguousarray(colors, dtype=np.float32).tobytes()

    position_bytes = vertices.tobytes()
    normal_bytes = normals.tobytes()
    index_bytes = indices.tobytes()
    position_offset = 0
    normal_offset = len(position_bytes)
    index_offset = normal_offset + len(normal_bytes)
    color_offset = index_offset + len(index_bytes)
    binary = position_bytes + normal_bytes + index_bytes + color_bytes

    attributes: dict[str, int] = {"POSITION": 0, "NORMAL": 1}
    accessors: list[dict[str, Any]] = [
        {
            "bufferView": 0,
            "componentType": 5126,
            "count": int(vertices.shape[0]),
            "type": "VEC3",
            "min": vertices.min(axis=0).tolist(),
            "max": vertices.max(axis=0).tolist(),
        },
        {"bufferView": 1, "componentType": 5126, "count": int(normals.shape[0]), "type": "VEC3"},
        {"bufferView": 2, "componentType": 5125, "count": int(indices.shape[0]), "type": "SCALAR"},
    ]
    views: list[dict[str, Any]] = [
        {"buffer": 0, "byteOffset": position_offset, "byteLength": len(position_bytes), "target": 34962},
        {"buffer": 0, "byteOffset": normal_offset, "byteLength": len(normal_bytes), "target": 34962},
        {"buffer": 0, "byteOffset": index_offset, "byteLength": len(index_bytes), "target": 34963},
    ]
    material: dict[str, Any] = {"doubleSided": True}

    if colors is not None:
        attributes["COLOR_0"] = 3
        accessors.append({"bufferView": 3, "componentType": 5126, "count": int(vertices.shape[0]), "type": "VEC3"})
        views.append({"buffer": 0, "byteOffset": color_offset, "byteLength": len(color_bytes), "target": 34962})
        material["extensions"] = {"KHR_materials_unlit": {}}

    gltf: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "Implicit Geometry A2A Example"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "materials": [material],
        "meshes": [{"primitives": [{"attributes": attributes, "indices": 2, "material": 0, "mode": 4}]}],
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    if colors is not None:
        gltf["extensionsUsed"] = ["KHR_materials_unlit"]

    json_chunk = _pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), b" ")
    bin_chunk = _pad(binary, b"\x00")
    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    return (
        struct.pack("<III", 0x46546C67, 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(bin_chunk), 0x004E4942)
        + bin_chunk
    )


def _normalize(values: np.ndarray) -> np.ndarray:
    low = float(np.min(values))
    high = float(np.max(values))
    if high - low < 1e-10:
        return np.full(values.shape, 0.5, dtype=np.float32)
    return ((values - low) / (high - low)).astype(np.float32)


def _center_vertices(vertices: np.ndarray) -> np.ndarray:
    return vertices - (vertices.min(axis=0) + vertices.max(axis=0)) / 2.0


def _safe_file_name(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_")
    return safe[:80] or "surface"


def _clean_expression(expression: str) -> str:
    expression = expression.strip()
    expression = re.sub(r"^z\s*=\s*", "", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\s*=\s*0\s*$", "", expression, flags=re.IGNORECASE)
    return expression.replace("^", "**")


def _clamp(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _pad(data: bytes, pad_byte: bytes) -> bytes:
    remainder = len(data) % 4
    if remainder:
        data += pad_byte * (4 - remainder)
    return data
