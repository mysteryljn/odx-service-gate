from __future__ import annotations

import html
import json
from xml.sax.saxutils import escape as xml_escape


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _label(item: dict) -> str:
    return item.get("service") or item.get("source") or item.get("name") or "input"


def to_markdown(report: dict) -> str:
    lines = ["# ODX service gate report", "", f"- Passed: **{report['passed']}**", f"- Policy: `{report['fail_on']}`", "", "## Findings"]
    findings = report["changes"] + report["issues"]
    if not findings:
        lines.append("\nNo service changes or input warnings were found.\n")
        return "\n".join(lines)
    for item in findings:
        lines.append(f"- **{item['severity']}** `{item['code']}` — `{_label(item)}`")
    return "\n".join(lines) + "\n"


def to_html(report: dict) -> str:
    rows = []
    for item in report["changes"] + report["issues"]:
        rows.append("<tr><td>{}</td><td><code>{}</code></td><td><code>{}</code></td></tr>".format(
            html.escape(item["severity"]), html.escape(item["code"]), html.escape(_label(item))))
    body = "".join(rows) or '<tr><td colspan="3">No findings</td></tr>'
    return """<!doctype html><meta charset="utf-8"><title>ODX service gate report</title>
<style>body{{font:15px system-ui;margin:2rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.45rem;text-align:left}}</style>
<h1>ODX service gate report</h1><p>Passed: <b>{passed}</b>; policy: <code>{policy}</code></p>
<table><thead><tr><th>Severity</th><th>Code</th><th>Service / source</th></tr></thead><tbody>{body}</tbody></table>
""".format(passed=html.escape(str(report["passed"])), policy=html.escape(report["fail_on"]), body=body)


def to_junit(report: dict) -> str:
    findings = report["changes"] + report["issues"]
    failures = [item for item in findings if item["severity"] == "error"]
    if not findings:
        cases = '<testcase classname="odx-service-gate" name="contract"/>'
    else:
        cases_list = []
        for item in findings:
            name = xml_escape(f"{item['code']}:{_label(item)}")
            if item["severity"] == "error":
                cases_list.append(f'<testcase classname="odx-service-gate" name="{name}"><failure message="blocking finding"/></testcase>')
            else:
                cases_list.append(f'<testcase classname="odx-service-gate" name="{name}"><system-out>{xml_escape(json.dumps(item, ensure_ascii=False))}</system-out></testcase>')
        cases = "".join(cases_list)
    count = len(findings) or 1
    return f'<testsuite name="odx-service-gate" tests="{count}" failures="{len(failures)}">{cases}</testsuite>\n'


def to_sarif(report: dict) -> str:
    results = []
    for item in report["changes"] + report["issues"]:
        results.append({
            "ruleId": item["code"],
            "level": {"error": "error", "warning": "warning", "note": "note"}[item["severity"]],
            "message": {"text": f"{_label(item)}: {item['code']}"},
        })
    payload = {"version": "2.1.0", "$schema": "https://json.schemastore.org/sarif-2.1.0.json", "runs": [{"tool": {"driver": {"name": "odx-service-gate", "version": "0.1.0"}}, "results": results}]}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render(report: dict, fmt: str) -> str:
    if fmt == "json":
        return to_json(report)
    if fmt == "markdown":
        return to_markdown(report)
    if fmt == "html":
        return to_html(report)
    if fmt == "junit":
        return to_junit(report)
    if fmt == "sarif":
        return to_sarif(report)
    raise ValueError(f"unsupported report format: {fmt}")
