"""Flutter-less static sanity check for the new mobile Dart files.

No Flutter SDK on this machine, so the compiler can't run. This checks what
can be checked statically:
  1. Delimiter balance (braces/brackets/parens) with strings & comments
     stripped — catches truncation/typo-level syntax damage.
  2. Every relative import resolves to an existing file.
  3. Every `package:mausam_nextgen/...` self-import resolves.
  4. The bundled checklist asset is valid JSON with the expected shape.
  5. pubspec.yaml registers the checklists asset dir.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MOBILE = Path(__file__).resolve().parents[1]
PKG = "package:mausam_nextgen/"

FAILS: list[str] = []


def strip_code(src: str) -> str:
    """Remove strings and comments so delimiter counting is meaningful."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and nxt == "*":
            i = src.find("*/", i + 2)
            i = n if i < 0 else i + 2
        elif c in ("'", '"'):
            q = c
            triple = src[i : i + 3] == q * 3
            i += 3 if triple else 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if triple:
                    if src[i : i + 3] == q * 3:
                        i += 3
                        break
                elif src[i] == q:
                    i += 1
                    break
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_balance(path: Path) -> None:
    code = strip_code(path.read_text(encoding="utf-8"))
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ln, line in enumerate(code.splitlines(), 1):
        for ch in line:
            if ch in "([{":
                stack.append((ch, ln))
            elif ch in ")]}":
                if not stack or stack[-1][0] != pairs[ch]:
                    FAILS.append(f"{path.name}:{ln} unbalanced '{ch}'")
                    return
                stack.pop()
    if stack:
        FAILS.append(f"{path.name}: unclosed {stack[-1][0]} from line {stack[-1][1]}")


def check_imports(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for m in re.finditer(r"import\s+'([^']+)'", text):
        imp = m.group(1)
        if imp.startswith("dart:") or imp.startswith("package:flutter"):
            continue
        if imp.startswith(PKG):
            rel = imp[len(PKG):]
            if not (MOBILE / "lib" / rel).exists():
                FAILS.append(f"{path.name}: unresolved {imp}")
        elif imp.startswith("package:"):
            # third-party dep: must be declared in pubspec.yaml
            dep = imp.split("/")[0][len("package:"):]
            if dep not in Path(MOBILE / "pubspec.yaml").read_text(encoding="utf-8"):
                FAILS.append(f"{path.name}: dep '{dep}' not in pubspec")
        else:
            target = (path.parent / imp).resolve()
            if not target.exists():
                FAILS.append(f"{path.name}: relative import '{imp}' missing")


def main() -> int:
    # Walk the whole lib + test tree — every Dart file gets the static
    # soundness check (balance, imports, deps) until `flutter analyze`
    # takes over on a machine with the SDK.
    files = sorted((MOBILE / "lib").rglob("*.dart")) + sorted((MOBILE / "test").glob("*.dart"))
    if not files:
        FAILS.append("no dart files found")
    for f in files:
        check_balance(f)
        check_imports(f)

    # 4. Asset JSON shape.
    asset = MOBILE / "assets" / "checklists" / "ndma_checklists.json"
    try:
        data = json.loads(asset.read_text(encoding="utf-8"))
        hazards = data["checklists"]
        for key in ("cyclone", "flood", "heatwave", "lightning"):
            h = hazards[key]
            for phase in ("before", "during", "after"):
                assert isinstance(h[phase], list) and h[phase], f"{key}.{phase} empty"
        assert data["emergency_numbers"], "emergency_numbers empty"
        print(f"asset OK: 4 hazards, {sum(len(h[p]) for h in hazards.values() for p in ('before','during','after'))} steps, "
              f"{len(data['emergency_numbers'])} emergency numbers")
    except Exception as exc:
        FAILS.append(f"asset invalid: {exc}")

    # 5. pubspec registration.
    pubspec = (MOBILE / "pubspec.yaml").read_text(encoding="utf-8")
    if "- assets/checklists/" not in pubspec:
        FAILS.append("pubspec.yaml missing assets/checklists/")

    # 6. Test files: every import of the app package must resolve, and each
    # test file must declare at least one test group/test.
    for t in [f for f in files if "/test/" in str(f)]:
        text = t.read_text(encoding="utf-8")
        if not re.search(r"\b(test|testWidgets)\s*\(", text):
            FAILS.append(f"{t.name}: no test/testWidgets declarations")

    if FAILS:
        print("FAILURES:")
        for f in FAILS:
            print("  -", f)
        return 1
    print("sanity OK: all dart files balanced, imports resolve, asset wired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
