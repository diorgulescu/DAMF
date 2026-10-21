"""Configuration and YAML/JSON loader utilities for DAMF.

Uses PyYAML (yaml.safe_load) when installed and provides a built-in pure-Python
YAML subset parser/dumper fallback so DAMF works out of the box in zero-dependency
environments.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from damf.exceptions import ConfigurationError

try:
    import yaml as _pyyaml
except ImportError:
    _pyyaml = None


def _parse_scalar(val: str) -> Any:
    """Parse a YAML scalar value into a Python primitive."""
    val = val.strip()
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item) for item in inner.split(",")]
    low = val.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~"):
        return None
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _strip_inline_comment(line: str) -> str:
    """Remove unquoted # comments from a YAML line."""
    in_single = False
    in_double = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx].rstrip()
    return line.rstrip()


def _fallback_yaml_load(text: str) -> Any:
    """Parse a standard block-structured YAML document without external dependencies."""
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)

    raw_lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        cleaned = _strip_inline_comment(raw)
        if not cleaned.strip() or cleaned.strip() == "---":
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        raw_lines.append((indent, cleaned.strip()))

    if not raw_lines:
        return {}

    def parse_block(index: int, min_indent: int) -> tuple[Any, int]:
        if index >= len(raw_lines):
            return {}, index

        first_indent, first_content = raw_lines[index]
        if first_indent < min_indent:
            return {}, index

        if first_content.startswith("- ") or first_content == "-":
            items: list[Any] = []
            while index < len(raw_lines):
                indent, content = raw_lines[index]
                if indent < first_indent:
                    break
                if indent > first_indent:
                    break
                if not (content.startswith("- ") or content == "-"):
                    break
                after_dash = content[1:].strip()
                index += 1
                if not after_dash:
                    sub_val, index = parse_block(index, indent + 1)
                    items.append(sub_val)
                elif ":" in after_dash and not (after_dash.startswith('"') or after_dash.startswith("'")):
                    # Inline mapping inside list item
                    k, _, v = after_dash.partition(":")
                    item_dict: dict[str, Any] = {}
                    v_str = v.strip()
                    if v_str:
                        item_dict[k.strip()] = _parse_scalar(v_str)
                    else:
                        sub_val, index = parse_block(index, indent + 1)
                        item_dict[k.strip()] = sub_val
                    # Check if subsequent lines belong to this dict item
                    while index < len(raw_lines) and raw_lines[index][0] > indent:
                        sub_map, index = parse_block(index, raw_lines[index][0])
                        if isinstance(sub_map, dict):
                            item_dict.update(sub_map)
                        else:
                            break
                    items.append(item_dict)
                else:
                    items.append(_parse_scalar(after_dash))
            return items, index

        mapping: dict[str, Any] = {}
        while index < len(raw_lines):
            indent, content = raw_lines[index]
            if indent < first_indent:
                break
            if indent > first_indent:
                # Unexpected deeper indent; consume and attach if possible
                index += 1
                continue
            if content.startswith("- ") or content == "-":
                break
            if ":" not in content:
                index += 1
                continue
            key, _, rest = content.partition(":")
            key = key.strip().strip("'\"")
            rest = rest.strip()
            index += 1
            if rest:
                mapping[key] = _parse_scalar(rest)
            else:
                if index < len(raw_lines) and raw_lines[index][0] > indent:
                    sub_val, index = parse_block(index, raw_lines[index][0])
                    mapping[key] = sub_val
                else:
                    mapping[key] = {}
        return mapping, index

    result, _ = parse_block(0, 0)
    return result


def safe_load_yaml(stream_or_text: Any) -> Any:
    """Safely parse YAML/JSON text or file stream."""
    if hasattr(stream_or_text, "read"):
        text = stream_or_text.read()
    else:
        text = str(stream_or_text)
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return _fallback_yaml_load(text)


def safe_load_all_yaml(stream_or_text: Any) -> list[Any]:
    """Safely parse multi-document YAML text or file stream."""
    if hasattr(stream_or_text, "read"):
        text = stream_or_text.read()
    else:
        text = str(stream_or_text)
    if _pyyaml is not None:
        return [doc for doc in _pyyaml.safe_load_all(text) if doc is not None]
    docs = [chunk for chunk in text.split("\n---") if chunk.strip()]
    return [_fallback_yaml_load(doc) for doc in docs]


def dump_yaml(data: Any) -> str:
    """Serialize data to YAML string."""
    if _pyyaml is not None:
        return _pyyaml.safe_dump(data, sort_keys=False)

    def _dump(obj: Any, indent: int = 0) -> list[str]:
        prefix = " " * indent
        lines: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)) and v:
                    lines.append(f"{prefix}{k}:")
                    lines.extend(_dump(v, indent + 2))
                elif isinstance(v, list) and not v:
                    lines.append(f"{prefix}{k}: []")
                elif isinstance(v, dict) and not v:
                    lines.append(f"{prefix}{k}: {{}}")
                else:
                    lines.append(f"{prefix}{k}: {json.dumps(v) if isinstance(v, str) and (':' in v or v == '') else v}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item:
                    first = True
                    for k, v in item.items():
                        head = f"{prefix}- " if first else f"{prefix}  "
                        first = False
                        if isinstance(v, (dict, list)) and v:
                            lines.append(f"{head}{k}:")
                            lines.extend(_dump(v, indent + 4))
                        else:
                            lines.append(f"{head}{k}: {v}")
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{obj}")
        return lines

    return "\n".join(_dump(data)) + "\n"


def load_config_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML or JSON configuration file from disk."""
    file_path = Path(path)
    if not file_path.exists():
        raise ConfigurationError(f"Configuration file not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = safe_load_yaml(text)
    if not isinstance(data, dict):
        raise ConfigurationError(f"Expected top-level mapping in config file: {file_path}")
    return data
