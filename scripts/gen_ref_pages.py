"""Generate API reference pages for mkdocs.

This script automatically generates documentation pages for all Python modules
in the interlock package. It's run by the mkdocs-gen-files plugin during build.
"""

from pathlib import Path

import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

src = Path(__file__).parent.parent / "interlock"

for path in sorted(src.rglob("*.py")):
    module_path = path.relative_to(src.parent)
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("reference", doc_path)

    parts = tuple(module_path.with_suffix("").parts)

    # Skip __pycache__ directories
    if "__pycache__" in parts:
        continue

    # Handle __init__.py files
    if parts[-1] == "__init__":
        parts = parts[:-1]
        if not parts:
            continue
        doc_path = doc_path.with_name("index.md")
        full_doc_path = full_doc_path.with_name("index.md")

    # Build navigation
    nav_parts = parts[1:] if parts[0] == "interlock" else parts
    if nav_parts:
        nav[nav_parts] = doc_path.as_posix()

    # Generate the markdown file
    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        ident = ".".join(parts)
        fd.write(f"::: {ident}")

    mkdocs_gen_files.set_edit_path(full_doc_path, path)

# Write the navigation file
with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())

