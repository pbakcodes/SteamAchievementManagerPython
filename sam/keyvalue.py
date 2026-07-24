"""Binary VDF (``KeyValues``) parser used to read Steam stat schemas.

Ports :class:`SAM.Game.KeyValue` and :class:`SAM.Game.KeyValueType` plus the
helper stream readers from ``SAM.Game.StreamHelpers``.
"""

from __future__ import annotations

import io
import struct
from enum import IntEnum
from typing import Any, List, Optional


class KeyValueType(IntEnum):
    NoneType = 0
    String = 1
    Int32 = 2
    Float32 = 3
    Pointer = 4
    WideString = 5
    Color = 6
    UInt64 = 7
    End = 8


class KeyValue:
    """Simple tree structure representing a binary VDF document."""

    __slots__ = ("name", "type", "value", "valid", "children")

    _INVALID: "KeyValue"  # populated below

    def __init__(self) -> None:
        self.name: str = "<root>"
        self.type: KeyValueType = KeyValueType.NoneType
        self.value: Any = None
        self.valid: bool = False
        self.children: Optional[List["KeyValue"]] = None

    # -----------------------------------------------------------------
    def __getitem__(self, key: str) -> "KeyValue":
        if not self.children:
            return KeyValue._INVALID
        lower = key.lower()
        for child in self.children:
            if child.name is not None and child.name.lower() == lower:
                return child
        return KeyValue._INVALID

    def __iter__(self):
        return iter(self.children or ())

    def __repr__(self) -> str:
        if not self.valid:
            return "<invalid>"
        if self.type == KeyValueType.NoneType:
            return self.name
        return f"{self.name} = {self.value!r}"

    # -----------------------------------------------------------------
    def as_string(self, default: str = "") -> str:
        if not self.valid or self.value is None:
            return default
        return str(self.value)

    def as_int(self, default: int = 0) -> int:
        if not self.valid:
            return default
        if self.type in (KeyValueType.String, KeyValueType.WideString):
            try:
                return int(self.value)
            except (TypeError, ValueError):
                return default
        if self.type == KeyValueType.Int32:
            return int(self.value)
        if self.type == KeyValueType.Float32:
            return int(float(self.value))
        if self.type == KeyValueType.UInt64:
            return int(self.value) & 0xFFFFFFFF
        return default

    def as_float(self, default: float = 0.0) -> float:
        if not self.valid:
            return default
        if self.type in (KeyValueType.String, KeyValueType.WideString):
            try:
                return float(self.value)
            except (TypeError, ValueError):
                return default
        if self.type == KeyValueType.Int32:
            return float(self.value)
        if self.type == KeyValueType.Float32:
            return float(self.value)
        if self.type == KeyValueType.UInt64:
            return float(int(self.value) & 0xFFFFFFFF)
        return default

    def as_bool(self, default: bool = False) -> bool:
        if not self.valid:
            return default
        if self.type in (KeyValueType.String, KeyValueType.WideString):
            try:
                return int(self.value) != 0
            except (TypeError, ValueError):
                return default
        if self.type == KeyValueType.Int32:
            return int(self.value) != 0
        if self.type == KeyValueType.Float32:
            return int(float(self.value)) != 0
        if self.type == KeyValueType.UInt64:
            return int(self.value) != 0
        return default


KeyValue._INVALID = KeyValue()


# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------
def _read_cstring_utf8(stream: io.BufferedIOBase) -> str:
    out = bytearray()
    while True:
        byte = stream.read(1)
        if not byte:
            raise EOFError("unexpected end of stream reading string")
        if byte == b"\x00":
            break
        out += byte
    return out.decode("utf-8", errors="replace")


def _read_struct(stream: io.BufferedIOBase, fmt: str):
    size = struct.calcsize(fmt)
    data = stream.read(size)
    if len(data) != size:
        raise EOFError(f"expected {size} bytes, got {len(data)}")
    return struct.unpack(fmt, data)[0]


# ---------------------------------------------------------------------------
# Binary VDF parser
# ---------------------------------------------------------------------------
def _read_binary(stream: io.BufferedIOBase, node: KeyValue, length: int) -> bool:
    node.children = []
    while True:
        raw_type = stream.read(1)
        if not raw_type:
            raise EOFError("unexpected end of stream")
        vtype = KeyValueType(raw_type[0])
        if vtype == KeyValueType.End:
            break

        current = KeyValue()
        current.type = vtype
        current.name = _read_cstring_utf8(stream)

        if vtype == KeyValueType.NoneType:
            _read_binary(stream, current, length)
        elif vtype == KeyValueType.String:
            current.valid = True
            current.value = _read_cstring_utf8(stream)
        elif vtype == KeyValueType.WideString:
            raise ValueError("wstring is unsupported")
        elif vtype == KeyValueType.Int32:
            current.valid = True
            current.value = _read_struct(stream, "<i")
        elif vtype == KeyValueType.UInt64:
            current.valid = True
            current.value = _read_struct(stream, "<Q")
        elif vtype == KeyValueType.Float32:
            current.valid = True
            current.value = _read_struct(stream, "<f")
        elif vtype == KeyValueType.Color:
            current.valid = True
            current.value = _read_struct(stream, "<I")
        elif vtype == KeyValueType.Pointer:
            current.valid = True
            current.value = _read_struct(stream, "<I")
        else:
            raise ValueError(f"unexpected type byte: {int(vtype)}")

        node.children.append(current)

        if stream.tell() >= length:
            raise EOFError("stream truncated mid-record")

    node.valid = True
    return stream.tell() == length


def load_binary(path: str) -> Optional[KeyValue]:
    """Load a ``UserGameStatsSchema_*.bin`` file. Returns ``None`` on error."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None

    stream = io.BytesIO(data)
    root = KeyValue()
    try:
        if not _read_binary(stream, root, len(data)):
            return None
    except (EOFError, ValueError):
        return None
    return root
