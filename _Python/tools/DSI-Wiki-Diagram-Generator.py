#!/usr/bin/env python3
"""
generate_diagram.py — DOT syntax string'den PNG üretir.
Kullanım: python3 generate_diagram.py <dot_file> <output_png>
         veya import edip dot_to_png(dot_source, output_path) çağır.

Graphviz sisteme kurulu olmalı (apt install graphviz).
Kurulu değilse python graphviz kütüphanesi render() ile dener.
"""
import sys
import os
import subprocess
import tempfile


def dot_to_png(dot_source: str, output_path: str) -> bool:
    """DOT kaynak metni → PNG dosyası. Başarıda True döner."""
    # Önce sistem graphviz'i dene
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False) as f:
            f.write(dot_source)
            tmp = f.name
        result = subprocess.run(
            ["dot", "-Tpng", tmp, "-o", output_path],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(tmp)
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: python graphviz kütüphanesi
    try:
        import graphviz
        src = graphviz.Source(dot_source)
        # output_path: /path/to/name.png → format=png, filename=name
        base = output_path.rsplit(".", 1)[0]
        src.render(filename=base, format="png", cleanup=True)
        rendered = base + ".png"
        if rendered != output_path and os.path.exists(rendered):
            os.rename(rendered, output_path)
        return os.path.exists(output_path)
    except Exception as e:
        print(f"Diagram render hatası: {e}", file=sys.stderr)
        return False


def mermaid_stub_to_dot(mermaid_lines: str) -> str:
    """Basit flowchart mermaid → DOT dönüşümü (sadece A-->B formatı)."""
    lines = mermaid_lines.strip().splitlines()
    edges = []
    for line in lines:
        line = line.strip()
        if "-->" in line:
            parts = line.split("-->")
            if len(parts) == 2:
                src = parts[0].strip().strip('"')
                dst = parts[1].strip().strip('"')
                edges.append(f'  "{src}" -> "{dst}"')
    dot = "digraph G {\n  rankdir=LR;\n  node [shape=box];\n"
    dot += "\n".join(edges)
    dot += "\n}"
    return dot


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Kullanım: generate_diagram.py <dot_file> <output.png>")
        sys.exit(1)
    dot_file, out_png = sys.argv[1], sys.argv[2]
    src = open(dot_file).read()
    ok = dot_to_png(src, out_png)
    sys.exit(0 if ok else 1)
