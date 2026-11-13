# odx-service-gate

**Review a diagnostic-service contract before an ODX/PDX release reaches the
integration bench.**

`odx-service-gate` compares a deliberately limited, documented subset of ODX
XML. It reports service ID changes, removed/added/changed parameters and
positive/negative response references as JSON, Markdown, standalone HTML,
JUnit XML or SARIF 2.1.0. It reads PDX ZIP members without extracting them and
never sends a diagnostic request.

## 60-second example

```sh
git clone https://github.com/mysteryljn/odx-service-gate.git
cd odx-service-gate
python -m pip install .
python -m odx_service_gate demo --output report.html
```

Open `report.html`. For a release gate in CI:

```sh
odx-service-gate compare baseline.odx candidate.pdx \
  --fail-on breaking --format sarif --output odx-review.sarif
```

Exit status is `0` when the selected policy passes, `1` when it finds a
blocking contract change, and `2` for malformed input or report I/O errors.
Use `--fail-on any` to fail on additions and warnings too, or `--fail-on never`
to generate a report without failing the job.

## Supported subset and limits

- Inputs are `.odx`, `.xml` and `.pdx` files, or directories searched
  recursively. PDX files are inspected in memory; archives are not extracted.
- A `DIAG-SERVICE` must have a direct `SHORT-NAME` and numeric `SERVICE-ID`.
  Services are matched by diagnostic-layer context plus short name.
- Within a service, direct `PARAM` elements are summarized by request/response
  section, name, semantic, byte/bit position, byte length and `DOP-REF`.
- `POS-RESPONSE-REF` and `NEG-RESPONSE-REF` values (text or `ID-REF`) are
  compared as exact references. Removed services, service IDs, parameters,
  parameter layout fields and response references are error-level findings;
  additions are notes or warnings.
- Duplicate service identities and missing service IDs are reported explicitly;
  unsupported or external ODX content is never silently treated as compatible.

This MVP is not a complete ODX 2.x parser, decoder, authoring tool or
conformance validator. It does not resolve the complete ODX reference graph,
decode COMPARAM/UNIT/COMPU-METHOD semantics, evaluate ECU variant inheritance,
prove mandatory parameter behavior, validate XML against an ASAM schema, or
connect to an ECU. For full ODX semantics and diagnostic encoding, use a
specialist parser such as [odxtools](https://github.com/mercedes-benz/odxtools)
and treat this project as a narrow, reviewable CI policy layer.

## Development

```sh
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
```

Fixtures are synthetic, standard-shaped examples and are labelled as such.
Contributions should include a sanitized, redistributable ODX fixture and the
producer/version information. MIT licensed.
