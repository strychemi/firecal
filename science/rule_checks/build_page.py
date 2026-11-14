"""Inline the chart data into the teaching page. Run: python3 build_page.py"""
import json, pathlib
here = pathlib.Path(__file__).parent
data = json.loads((here / "viz_data.json").read_text())
data["frp"] = json.loads((here / "frp_results.json").read_text())
html = (here / "primer.template.html").read_text().replace("__DATA__", json.dumps(data))
(here / "primer.html").write_text(html)
print(len(html))
