"""
Rebuild docs/ARCHITECTURE.pdf from docs/ARCHITECTURE.md:

    python docs/build_pdf.py

Headless Microsoft Edge (or Chrome) renders the Markdown and its Mermaid diagrams, using marked and
mermaid from the jsDelivr CDN (so it needs internet), then prints the page to PDF.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

DOCS = pathlib.Path(__file__).resolve().parent
SOURCE, TARGET = DOCS / "ARCHITECTURE.md", DOCS / "ARCHITECTURE.pdf"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge", "google-chrome", "chromium",
]

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>TradBot architecture</title>
<style>
  @page {
    size: A4; margin: 14mm 13mm 16mm;
    @bottom-left { content: "TradBot · Architecture, Flows & Environment"; font: 7.5pt "Segoe UI", sans-serif; color: #6b7686; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 7.5pt "Segoe UI", sans-serif; color: #6b7686; }
  }
  body { margin: 0; font: 10pt/1.5 "Segoe UI", system-ui, sans-serif; color: #1c2430; background: #fff; }
  h1 { font-size: 21pt; line-height: 1.2; margin: 0 0 8pt; color: #13233d; }
  h2 { font-size: 14.5pt; color: #13233d; border-bottom: 1.2pt solid #cfd8e5; padding-bottom: 3pt;
       margin: 20pt 0 8pt; break-after: avoid; }
  h3 { font-size: 11.5pt; color: #13233d; margin: 14pt 0 6pt; break-after: avoid; }
  p, li { max-width: 175mm; }
  table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 6pt 0 10pt; }
  th, td { border: 0.7pt solid #cfd8e5; padding: 3.5pt 6pt; text-align: left; vertical-align: top; }
  th { background: #eef2f8; }
  tr { break-inside: avoid; }
  code { font-family: Consolas, "Cascadia Mono", monospace; font-size: 8.6pt; background: #eef2f8;
         padding: 0 2pt; border-radius: 2pt; }
  pre { background: #f5f7fa; border: 0.7pt solid #cfd8e5; border-radius: 3pt; padding: 7pt 9pt;
        font-size: 8.4pt; line-height: 1.4; white-space: pre-wrap; break-inside: avoid; }
  pre code { background: none; padding: 0; }
  hr { border: 0; border-top: 0.7pt solid #cfd8e5; margin: 10pt 0; }
  a { color: #0b5cad; text-decoration: none; }
  .mermaid { break-inside: avoid; margin: 8pt 0 10pt; text-align: center; }
  .mermaid svg { max-width: 100% !important; max-height: 225mm; height: auto; }
</style>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
</head>
<body><main id="doc"></main>
<script>
  const markdown = __MARKDOWN__;
  document.getElementById("doc").innerHTML = marked.parse(markdown, { gfm: true });
  document.querySelectorAll("pre > code.language-mermaid").forEach(code => {
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = code.textContent;
    code.parentElement.replaceWith(div);
  });
  mermaid.initialize({
    startOnLoad: false, securityLevel: "loose", theme: "base",
    themeVariables: {
      fontFamily: "Segoe UI, sans-serif", fontSize: "14px",
      primaryColor: "#eef3fb", primaryBorderColor: "#5b7db1", primaryTextColor: "#1c2430",
      secondaryColor: "#fdf3dc", tertiaryColor: "#f4f6f9", lineColor: "#5b6b82",
      clusterBkg: "#f7f9fc", clusterBorder: "#c9d3e2", edgeLabelBackground: "#ffffff",
    },
    flowchart: { curve: "basis", padding: 10 },
    sequence: { mirrorActors: false },
  });
  mermaid.run({ querySelector: ".mermaid" })
    .then(() => { document.body.dataset.ready = "1"; })
    .catch(err => { console.error(err); document.body.dataset.error = String(err); document.body.dataset.ready = "1"; });
</script>
</body></html>
"""


def find_browser() -> str:
    for name in BROWSERS:
        path = shutil.which(name) or (name if pathlib.Path(name).is_file() else None)
        if path:
            return path
    sys.exit("Microsoft Edge or Google Chrome is needed to build the PDF.")


def headless(exe: str, profile: pathlib.Path, url: str, *args: str) -> subprocess.CompletedProcess:
    # A separate profile keeps headless runs away from any browser window you have open.
    return subprocess.run(
        [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         f"--user-data-dir={profile}", "--run-all-compositor-stages-before-draw",
         "--virtual-time-budget=30000", *args, url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )


def main() -> None:
    exe = find_browser()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        page = pathlib.Path(tmp) / "ARCHITECTURE.html"
        page.write_text(PAGE.replace("__MARKDOWN__", json.dumps(SOURCE.read_text(encoding="utf-8"))), encoding="utf-8")
        profile, url = pathlib.Path(tmp) / "profile", page.as_uri()

        dom = headless(exe, profile, url, "--dump-dom").stdout
        if 'data-ready="1"' not in dom:
            sys.exit("The page didn't finish rendering. Is cdn.jsdelivr.net reachable?")
        if "data-error=" in dom or "Syntax error in text" in dom:
            sys.exit("A Mermaid diagram failed to render; check the mermaid blocks in ARCHITECTURE.md.")
        print(f"Rendered {dom.count('<svg')} diagrams")

        if TARGET.exists():
            TARGET.unlink()
        headless(exe, profile, url, f"--print-to-pdf={TARGET}", "--no-pdf-header-footer", "--print-to-pdf-no-header")
    if not TARGET.exists():
        sys.exit("The browser didn't write the PDF.")
    print(f"Wrote {TARGET} ({TARGET.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
