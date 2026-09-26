"""Build data/validation/label.html: a self-contained page for hand-labelling
data/validation/labels.csv in a browser (no spreadsheet needed).

The page shows each cache step's path, key and restore keys, plus a link to
the workflow file at the sampled commit. It never shows the classifier's
answers. Progress is kept in the browser; "Download labels.csv" writes the
finished file, which goes back in data/validation/.

  python scripts/make_label_page.py
"""
from __future__ import annotations

import csv
import html
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
VAL = os.path.join(ROOT, "data", "validation")


def main():
    rows = list(csv.DictReader(open(os.path.join(VAL, "labels.csv"), encoding="utf-8")))
    shas = {}
    for m in open(os.path.join(ROOT, "data", "raw", "manifest.jsonl"), encoding="utf-8"):
        r = json.loads(m)
        shas[r["repo"]] = r.get("sha", "")
    for r in rows:
        r["url"] = f"https://github.com/{r['repo']}/blob/{shas.get(r['repo'], 'HEAD')}/.github/workflows/{r['file']}"
    rubric = open(os.path.join(VAL, "RUBRIC.md"), encoding="utf-8").read()
    page = TEMPLATE.replace("__ROWS__", json.dumps(rows)).replace("__RUBRIC__", html.escape(rubric))
    out = os.path.join(VAL, "label.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print(f"wrote {out} ({len(rows)} rows)")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Label cache steps</title>
<style>
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --card:#fff; --line:#e3e1da; --accent:#2f5d8a; --done:#2e7d4f; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ecebe6; --muted:#a09f99; --card:#201f1d; --line:#35342f; --accent:#7fb0e0; --done:#6cc08e; } }
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, sans-serif; }
main { max-width:900px; margin:0 auto; padding:20px 16px 80px; }
h1 { font-size:20px; margin:0 0 4px }
.muted { color:var(--muted); font-size:14px }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; }
.field { margin:10px 0 }
.label { font-size:13px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em }
pre { white-space:pre-wrap; word-break:break-all; margin:4px 0 0; font:14px/1.45 ui-monospace, Consolas, monospace; }
.choices { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px }
button { font:inherit; padding:8px 12px; border-radius:8px; border:1px solid var(--line); background:var(--bg); color:var(--fg); cursor:pointer }
button.on { border-color:var(--accent); outline:2px solid var(--accent) }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent) }
.bar { height:6px; background:var(--line); border-radius:3px; overflow:hidden; margin:8px 0 }
.bar > div { height:100%; background:var(--done) }
.nav { display:flex; gap:8px; flex-wrap:wrap; align-items:center }
textarea { width:100%; font:inherit; padding:8px; border-radius:8px; border:1px solid var(--line); background:var(--bg); color:var(--fg) }
details { margin-top:16px } summary { cursor:pointer }
a { color:var(--accent) }
kbd { font:12px ui-monospace, monospace; border:1px solid var(--line); border-radius:4px; padding:0 4px }
</style></head><body><main>
<h1>Label cache steps</h1>
<div class="muted">Read the path and key, then pick one answer in each group. Keys: <kbd>1</kbd>-<kbd>3</kbd> path kind, <kbd>q</kbd> <kbd>w</kbd> <kbd>e</kbd> <kbd>r</kbd> <kbd>t</kbd> verdict, <kbd>&rarr;</kbd> next, <kbd>&larr;</kbd> back. Progress saves in this browser.</div>
<div class="bar"><div id="bar"></div></div>
<div class="nav"><span id="pos"></span><span class="muted" id="count"></span></div>
<div class="card">
  <div class="field"><div class="label">Repository / workflow</div><div id="where"></div></div>
  <div class="field"><div class="label">Cached path(s)</div><pre id="paths"></pre></div>
  <div class="field"><div class="label">Key</div><pre id="key"></pre></div>
  <div class="field"><div class="label">Restore keys</div><pre id="rkeys"></pre></div>
</div>
<div class="card">
  <div class="field"><div class="label">1. What does the path hold?</div><div class="choices" id="pk"></div></div>
  <div class="field"><div class="label">2. Does the key pin the Python version? (only for built_env)</div><div class="choices" id="vd"></div></div>
  <div class="field"><div class="label">Note (optional)</div><textarea id="note" rows="2"></textarea></div>
</div>
<div class="nav">
  <button id="prev">&larr; Back</button><button id="next" class="primary">Next &rarr;</button>
  <button id="nextBlank">Next unlabelled</button><span style="flex:1"></span>
  <button id="dl">Download labels.csv</button>
</div>
<details><summary>Rubric</summary><pre>__RUBRIC__</pre></details>
</main>
<script>
const ROWS = __ROWS__;
const PK = [["built_env","1"],["download_store","2"],["other","3"]];
const VD = [["sound","q"],["minor_only","w"],["no_interpreter","e"],["version_file","r"],["not_applicable","t"]];
const KEY = "cks-labels-v1";
let store = {};
try { store = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
let i = 0;
const id = r => [r.repo, r.file, r.job, r.step_index].join("|");
const get = r => store[id(r)] || {pk:"", vd:"", note:""};
function save(){ try { localStorage.setItem(KEY, JSON.stringify(store)); } catch (e) {} }
function set(field, v){ const r = ROWS[i]; const s = get(r); s[field] = v;
  if (field === "pk" && v !== "built_env") s.vd = "not_applicable";
  if (field === "pk" && v === "built_env" && s.vd === "not_applicable") s.vd = "";
  store[id(r)] = s; save(); render(); }
function buttons(el, opts, field, cur){ el.innerHTML = "";
  for (const [v,k] of opts){ const b = document.createElement("button");
    b.textContent = v + " (" + k + ")"; if (cur === v) b.className = "on";
    b.onclick = () => set(field, v); el.appendChild(b); } }
function done(r){ const s = get(r); return s.pk && s.vd; }
function render(){ const r = ROWS[i], s = get(r);
  document.getElementById("pos").textContent = "Row " + (i+1) + " of " + ROWS.length;
  const n = ROWS.filter(done).length;
  document.getElementById("count").textContent = " - " + n + " labelled";
  document.getElementById("bar").style.width = (100*n/ROWS.length) + "%";
  const a = document.getElementById("where"); a.innerHTML = "";
  const link = document.createElement("a"); link.href = r.url; link.target = "_blank"; link.rel = "noopener";
  link.textContent = r.repo + " / " + r.file + " (job " + r.job + ", step " + (Number(r.step_index)+1) + ")"; a.appendChild(link);
  document.getElementById("paths").textContent = r.paths.split(" | ").join("\n");
  document.getElementById("key").textContent = r.key;
  document.getElementById("rkeys").textContent = r.restore_keys ? r.restore_keys.split(" | ").join("\n") : "(none)";
  buttons(document.getElementById("pk"), PK, "pk", s.pk);
  buttons(document.getElementById("vd"), VD, "vd", s.vd);
  const note = document.getElementById("note"); if (document.activeElement !== note) note.value = s.note || ""; }
document.getElementById("note").oninput = e => { const r = ROWS[i]; const s = get(r); s.note = e.target.value; store[id(r)] = s; save(); };
document.getElementById("prev").onclick = () => { if (i > 0) { i--; render(); } };
document.getElementById("next").onclick = () => { if (i < ROWS.length-1) { i++; render(); } };
document.getElementById("nextBlank").onclick = () => { for (let k=1;k<=ROWS.length;k++){ const j=(i+k)%ROWS.length; if(!done(ROWS[j])){ i=j; render(); return; } } };
document.addEventListener("keydown", e => { if (e.target.tagName === "TEXTAREA") return;
  for (const [v,k] of PK) if (e.key === k) set("pk", v);
  for (const [v,k] of VD) if (e.key === k) set("vd", v);
  if (e.key === "ArrowRight") document.getElementById("next").click();
  if (e.key === "ArrowLeft") document.getElementById("prev").click(); });
function q(v){ v = String(v ?? ""); return /[",\n]/.test(v) ? '"' + v.replace(/"/g,'""') + '"' : v; }
document.getElementById("dl").onclick = () => {
  const cols = ["repo","file","job","step_index","paths","key","restore_keys","label_path_kind","label_verdict","label_note"];
  const lines = [cols.join(",")];
  for (const r of ROWS){ const s = get(r);
    lines.push([r.repo,r.file,r.job,r.step_index,r.paths,r.key,r.restore_keys,s.pk,s.vd,s.note].map(q).join(",")); }
  const blob = new Blob([lines.join("\n") + "\n"], {type:"text/csv"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "labels.csv"; a.click(); };
render();
</script></body></html>
"""

if __name__ == "__main__":
    main()
