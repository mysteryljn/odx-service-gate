"""Conservative ODX/PDX service contract comparison.

This MVP intentionally consumes a small, common ODX XML vocabulary instead of
claiming to implement the complete ODX schema. It is useful for a CI review of
service IDs, parameter layout summaries and response references, while
odxtools remains the right choice for full decoding and authoring.
"""

from __future__ import annotations

from collections import defaultdict
import io
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


class OdxInputError(ValueError):
    pass


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].upper()


def child_text(element: ET.Element, wanted: str) -> str | None:
    for child in list(element):
        if local_name(child.tag) == wanted and child.text:
            return child.text.strip()
    return None


def parse_number(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    text = value.strip()
    try:
        return int(text, 0) if text.lower().startswith("0x") else int(text, 10)
    except ValueError as exc:
        raise OdxInputError(f"invalid numeric value {value!r}") from exc


def _ref_value(element: ET.Element) -> str | None:
    if element.text and element.text.strip():
        return element.text.strip()
    for key, value in element.attrib.items():
        if local_name(key) in {"ID-REF", "ID_REF"} and value.strip():
            return value.strip()
    return None


def _iter_input_members(inputs: list[Path]):
    paths: list[Path] = []
    for item in inputs:
        if not item.exists():
            raise OdxInputError(f"input does not exist: {item}")
        if item.is_dir():
            paths.extend(sorted(p for p in item.rglob("*") if p.is_file() and p.suffix.lower() in {".odx", ".xml", ".pdx"}))
        elif item.suffix.lower() in {".odx", ".xml", ".pdx"}:
            paths.append(item)
        else:
            raise OdxInputError(f"expected an .odx, .xml or .pdx file/directory: {item}")
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.suffix.lower() == ".pdx":
            try:
                with zipfile.ZipFile(path) as archive:
                    for name in sorted(archive.namelist()):
                        if name.endswith("/") or Path(name).suffix.lower() not in {".odx", ".xml"}:
                            continue
                        yield f"{resolved}!{name}", archive.read(name)
            except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
                raise OdxInputError(f"cannot read PDX {path}: {exc}") from exc
        else:
            try:
                yield str(resolved), path.read_bytes()
            except (OSError, UnicodeError) as exc:
                raise OdxInputError(f"cannot read {path}: {exc}") from exc


def _parameter_records(service: ET.Element) -> list[dict]:
    result: list[dict] = []

    def walk(element: ET.Element, section: str):
        tag = local_name(element.tag)
        next_section = section
        if tag in {"REQUEST", "POS-RESPONSE", "NEG-RESPONSE", "RESPONSE"}:
            next_section = tag
        if tag == "PARAM":
            name = child_text(element, "SHORT-NAME") or element.attrib.get("ID") or "<unnamed>"
            refs = []
            for child in element.iter():
                child_tag = local_name(child.tag)
                if child is not element and child_tag.endswith("REF"):
                    value = _ref_value(child)
                    if value:
                        refs.append((child_tag, value))
            result.append({
                "section": next_section or "UNKNOWN",
                "name": name,
                "semantic": child_text(element, "SEMANTIC"),
                "byte_position": parse_number(child_text(element, "BYTE-POSITION")),
                "bit_position": parse_number(child_text(element, "BIT-POSITION")),
                "byte_length": parse_number(child_text(element, "BYTE-LENGTH")),
                "dop_ref": next((value for tag_name, value in refs if "DOP" in tag_name), None),
            })
            return
        for child in list(element):
            walk(child, next_section)

    walk(service, "")
    return sorted(result, key=lambda item: (item["section"], item["name"]))


def _response_refs(service: ET.Element) -> list[dict]:
    refs = []
    for element in service.iter():
        tag = local_name(element.tag)
        if "RESPONSE" not in tag or not tag.endswith("REF"):
            continue
        value = _ref_value(element)
        if not value:
            continue
        kind = "negative" if "NEG" in tag else "positive" if "POS" in tag else "response"
        refs.append({"kind": kind, "target": value})
    return sorted(refs, key=lambda item: (item["kind"], item["target"]))


def _service_record(service: ET.Element, context: str, source: str) -> tuple[dict | None, dict | None]:
    name = child_text(service, "SHORT-NAME") or service.attrib.get("ID")
    service_id = parse_number(child_text(service, "SERVICE-ID"))
    if not name or service_id is None:
        return None, {"code": "unsupported_service", "severity": "warning", "source": source, "name": name or "<unnamed>", "reason": "DIAG-SERVICE needs SHORT-NAME and numeric SERVICE-ID"}
    record = {
        "context": context or "<default>",
        "name": name,
        "service_id": service_id,
        "parameters": _parameter_records(service),
        "response_refs": _response_refs(service),
        "source": source,
    }
    record["key"] = f"{record['context']}::{name}"
    return record, None


def _parse_xml(data: bytes, source: str) -> tuple[list[dict], list[dict]]:
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, UnicodeError) as exc:
        raise OdxInputError(f"cannot parse {source}: {exc}") from exc
    services: list[dict] = []
    issues: list[dict] = []

    def walk(element: ET.Element, context: str):
        tag = local_name(element.tag)
        next_context = context
        if tag in {"DIAG-LAYER", "ECU-VARIANT", "BASE-VARIANT", "FUNCTIONAL-GROUP"}:
            next_context = child_text(element, "SHORT-NAME") or context
        if tag == "DIAG-SERVICE":
            record, issue = _service_record(element, next_context, source)
            if record:
                services.append(record)
            if issue:
                issues.append(issue)
            return
        for child in list(element):
            walk(child, next_context)

    walk(root, "")
    if not services and not issues:
        issues.append({"code": "no_diag_services", "severity": "warning", "source": source, "reason": "no DIAG-SERVICE elements found"})
    return services, issues


def snapshot(inputs: list[Path]) -> dict:
    services: dict[str, list[dict]] = defaultdict(list)
    issues: list[dict] = []
    files: list[str] = []
    for source, data in _iter_input_members(inputs):
        files.append(source)
        records, parse_issues = _parse_xml(data, source)
        issues.extend(parse_issues)
        for record in records:
            services[record["key"]].append(record)
    if not files:
        raise OdxInputError("no ODX or PDX documents found")
    return {"services": dict(services), "issues": issues, "files": files}


def _signature(record: dict) -> dict:
    return {"service_id": record["service_id"], "parameters": record["parameters"], "response_refs": record["response_refs"]}


def compare(baseline_inputs: list[Path], current_inputs: list[Path], fail_on: str = "breaking") -> dict:
    before = snapshot(baseline_inputs)
    after = snapshot(current_inputs)
    findings: list[dict] = before["issues"] + after["issues"]
    changes: list[dict] = []
    for key in sorted(set(before["services"]) | set(after["services"])):
        old = before["services"].get(key, [])
        new = after["services"].get(key, [])
        if len(old) > 1 or len(new) > 1:
            changes.append({"code": "ambiguous_service", "severity": "error", "service": key, "before_count": len(old), "after_count": len(new)})
            continue
        if not old:
            changes.append({"code": "service_added", "severity": "note", "service": key, "service_id": new[0]["service_id"], "source": new[0]["source"]})
            continue
        if not new:
            changes.append({"code": "service_removed", "severity": "error", "service": key, "service_id": old[0]["service_id"], "source": old[0]["source"]})
            continue
        previous, current = old[0], new[0]
        if previous["service_id"] != current["service_id"]:
            changes.append({"code": "service_id_changed", "severity": "error", "service": key, "before": previous["service_id"], "after": current["service_id"], "source": current["source"]})
        old_params = {(p["section"], p["name"]): p for p in previous["parameters"]}
        new_params = {(p["section"], p["name"]): p for p in current["parameters"]}
        for param_key in sorted(set(old_params) | set(new_params)):
            if param_key not in new_params:
                changes.append({"code": "parameter_removed", "severity": "error", "service": key, "parameter": param_key, "source": current["source"]})
            elif param_key not in old_params:
                changes.append({"code": "parameter_added", "severity": "warning", "service": key, "parameter": param_key, "source": current["source"]})
            elif old_params[param_key] != new_params[param_key]:
                changes.append({"code": "parameter_changed", "severity": "error", "service": key, "parameter": param_key, "before": old_params[param_key], "after": new_params[param_key], "source": current["source"]})
        if previous["response_refs"] != current["response_refs"]:
            changes.append({"code": "response_reference_changed", "severity": "error", "service": key, "before": previous["response_refs"], "after": current["response_refs"], "source": current["source"]})
    findings.extend(changes)
    levels = {"note": 0, "warning": 1, "error": 2}
    threshold = {"never": 99, "breaking": 2, "any": 0}.get(fail_on)
    if threshold is None:
        raise OdxInputError("fail-on must be breaking, any, or never")
    blocking = [item for item in findings if levels.get(item["severity"], 2) >= threshold]
    return {
        "tool": "odx-service-gate", "version": "0.1.0", "passed": not blocking, "fail_on": fail_on,
        "files": {"baseline": before["files"], "current": after["files"]},
        "changes": changes, "issues": before["issues"] + after["issues"],
        "summary": {"changes": len(changes), "issues": len(before["issues"]) + len(after["issues"]), "blocking": len(blocking)},
    }


def demo_paths() -> tuple[Path, Path]:
    from importlib.resources import files
    root = files("odx_service_gate").joinpath("fixtures")
    return Path(str(root.joinpath("before.odx"))), Path(str(root.joinpath("after.odx")))
