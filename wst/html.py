"""Interactive pie-chart page: hover a sector for its holdings, click to drill in."""

import datetime
import json
from collections import defaultdict


def net_by_symbol(rows):
    """Net long stock + short option overlays per symbol (pies need one slice)."""
    agg = {}
    for r in rows:
        a = agg.setdefault(
            r["sym"],
            {"sym": r["sym"], "name": r["name"], "value": 0.0,
             "pnl_w": 0.0, "sector": r["sector"]},
        )
        a["value"] += r["value"]
        a["pnl_w"] += r["pnl_pct"] * r["value"]
    out = []
    for a in agg.values():
        v = a.pop("pnl_w")
        a["pnl_pct"] = (v / a["value"]) if a["value"] else 0.0
        if a["value"] > 0:
            out.append(a)
    return sorted(out, key=lambda r: -r["value"])


def make_view(label, rows):
    stocks = net_by_symbol(rows)
    total = sum(s["value"] for s in stocks)
    for s in stocks:
        s["pct"] = s["value"] / total * 100 if total else 0.0
    buckets = defaultdict(list)
    for s in stocks:
        buckets[s["sector"]].append(s)
    sectors = []
    for bname, blist in buckets.items():
        v = sum(s["value"] for s in blist)
        sectors.append(
            {"name": bname, "value": v,
             "pct": v / total * 100 if total else 0.0, "stocks": blist}
        )
    sectors.sort(key=lambda b: -b["value"])
    return {"label": label, "total": total, "sectors": sectors, "stocks": stocks}


def cmd_pie(args, accounts, scope_label, rows, labels, config):
    scope_ids = [a["id"] for a in accounts]
    views = {"__all__": make_view(f"All accounts ({scope_label})",
                                  [r for r in rows if r["account_id"] in scope_ids])}
    tabs = [{"id": "__all__", "label": "All accounts"}]
    for name, ids in (config.get("scopes") or {}).items():
        s = [i for i in ids if i in scope_ids]
        if s and set(s) != set(scope_ids):
            key = f"__scope__{name}"
            views[key] = make_view(name.title(), [r for r in rows if r["account_id"] in s])
            tabs.append({"id": key, "label": name.title()})
    for a in accounts:
        key = f"__acct__{a['id']}"
        view = make_view(labels[a["id"]],
                         [r for r in rows if r["account_id"] == a["id"]])
        if view["total"] == 0:
            continue  # cash / credit / managed accounts with no visible holdings
        views[key] = view
        tabs.append({"id": key, "label": labels[a["id"]]})

    asof = datetime.datetime.now(datetime.timezone.utc).astimezone().strftime(
        "%b %d, %Y %I:%M %p %Z")
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(views))
    html = html.replace("__TABS__", json.dumps(tabs))
    html = html.replace("__ASOF__", asof)
    with open(args.output, "w") as f:
        f.write(html)
    print(f"Wrote {args.output}")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Holdings overview</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0;
         background: #f7f8fa; color: #1c1e21; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #65676b; font-size: 13px; margin-bottom: 16px; }
  .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .tab { border: 1px solid #ccd0d5; background: #fff; border-radius: 999px;
         padding: 7px 16px; font-size: 14px; cursor: pointer; }
  .tab.active { background: #1c1e21; color: #fff; border-color: #1c1e21; }
  .modes { display: flex; gap: 8px; align-items: center; margin: 12px 0 4px; }
  .mode { border: none; background: none; font-size: 14px; cursor: pointer;
          color: #65676b; padding: 4px 2px; border-bottom: 2px solid transparent; }
  .mode.active { color: #1c1e21; border-bottom-color: #1c1e21; font-weight: 600; }
  #back { display: none; margin-left: auto; border: 1px solid #ccd0d5;
          background: #fff; border-radius: 8px; padding: 6px 12px; font-size: 13px;
          cursor: pointer; }
  #chart { width: 100%; height: 560px; background: #fff; border-radius: 12px;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .foot { color: #90949c; font-size: 12px; margin-top: 12px; }
  .tip { min-width: 220px; max-width: 320px; }
  .tip .hd { font-weight: 700; margin-bottom: 6px; font-size: 14px; }
  .tip .row { display: flex; justify-content: space-between; gap: 20px;
              font-size: 13px; padding: 1px 0; }
  .tip .mut { color: #90949c; font-size: 12px; margin-top: 6px; }
</style>
</head>
<body>
<div class="wrap">
  <h1 id="title">Holdings overview</h1>
  <div class="sub">Data as of __ASOF__ &middot; hover a slice for detail, click a sector to drill in</div>
  <div class="tabs" id="tabs"></div>
  <div class="modes">
    <button class="mode active" id="m-sectors">Sectors</button>
    <button class="mode" id="m-stocks">Stocks</button>
    <button id="back">&larr; Back to sectors</button>
  </div>
  <div id="chart"></div>
  <div class="foot">Residual cash is not a holding and is excluded. Managed-account positions are not visible via Wealthsimple's API. Regenerate the page for fresh data.</div>
</div>
<script>
var DATA = __DATA__;
var TABS = __TABS__;
var cur = TABS[0].id, mode = "sectors", drill = null;
var chart = echarts.init(document.getElementById("chart"));
function fmt$(v){ return "$" + Math.round(v).toLocaleString("en-US"); }
function sectorTip(p){
  var s = p.data.sector, h = '<div class="tip"><div class="hd">' + p.name +
    " &mdash; " + fmt$(s.value) + " (" + s.pct.toFixed(1) + "%)</div>";
  s.stocks.slice(0, 10).forEach(function(st){
    h += '<div class="row"><span>' + st.sym + '</span><span>' + fmt$(st.value) +
         " &middot; " + st.pct.toFixed(1) + "%</span></div>";
  });
  if (s.stocks.length > 10)
    h += '<div class="mut">+' + (s.stocks.length - 10) + " more &mdash; click to drill in</div>";
  return h + "</div>";
}
function stockTip(p){
  var st = p.data.stock;
  return '<div class="tip"><div class="hd">' + st.sym + " &mdash; " + fmt$(st.value) +
    " (" + st.pct.toFixed(1) + "%)</div>" +
    '<div class="row"><span>' + st.name + '</span></div>' +
    '<div class="row"><span>P&amp;L</span><span>' +
    (st.pnl_pct >= 0 ? "+" : "") + st.pnl_pct.toFixed(1) + "%</span></div></div>";
}
function render(){
  var v = DATA[cur], data;
  document.getElementById("title").textContent =
    "Holdings overview — " + v.label + " (" + fmt$(v.total) + ")";
  document.getElementById("back").style.display = drill ? "" : "none";
  var opt;
  if (drill) {
    var s = v.sectors.find(function(x){ return x.name === drill; });
    data = s.stocks.map(function(st){
      return { name: st.sym, value: st.value, stock: st }; });
    opt = pieOpt(data, drill + " — " + fmt$(s.value) + " (" + s.pct.toFixed(1) + "%)", stockTip, false);
  } else if (mode === "sectors") {
    data = v.sectors.map(function(s){
      return { name: s.name, value: s.value, sector: s }; });
    opt = pieOpt(data, v.label + " by sector", sectorTip, true);
  } else {
    data = v.stocks.map(function(st){
      return { name: st.sym, value: st.value, stock: st }; });
    opt = pieOpt(data, v.label + " by stock", stockTip, false);
  }
  chart.setOption(opt, true);
}
function pieOpt(data, title, tip, clickable){
  return {
    title: { text: title, left: "center", top: 12,
             textStyle: { fontSize: 16, fontWeight: 600 } },
    tooltip: { trigger: "item", formatter: tip,
               confine: true, backgroundColor: "#fff", borderColor: "#ccd0d5",
               textStyle: { color: "#1c1e21" } },
    legend: { type: "scroll", bottom: 8, textStyle: { fontSize: 12 } },
    series: [{ type: "pie", radius: ["42%", "68%"], center: ["50%", "52%"],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: "#fff", borderWidth: 2 },
      label: { formatter: "{b}\\n{d}%", fontSize: 11 },
      labelLine: { length: 10, length2: 8 },
      cursor: clickable ? "pointer" : "default",
      data: data,
      emphasis: { scale: true, scaleSize: 4 }
    }],
    color: ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948",
            "#b07aa1","#ff9da7","#9c755f","#bab0ac","#6a8fc7","#d37295",
            "#8cd17d","#e8b04b","#7f7f7f","#bcbd22","#17becf","#9467bd"]
  };
}
chart.on("click", function(p){
  if (!drill && mode === "sectors" && p.data.sector) { drill = p.name; render(); }
});
function setTab(id){
  cur = id; drill = null;
  document.querySelectorAll(".tab").forEach(function(el){
    el.classList.toggle("active", el.dataset.id === id); });
  render();
}
TABS.forEach(function(t){
  var b = document.createElement("button");
  b.className = "tab" + (t.id === cur ? " active" : "");
  b.textContent = t.label; b.dataset.id = t.id;
  b.onclick = function(){ setTab(t.id); };
  document.getElementById("tabs").appendChild(b);
});
document.getElementById("m-sectors").onclick = function(){
  mode = "sectors"; drill = null;
  this.classList.add("active");
  document.getElementById("m-stocks").classList.remove("active"); render(); };
document.getElementById("m-stocks").onclick = function(){
  mode = "stocks"; drill = null;
  this.classList.add("active");
  document.getElementById("m-sectors").classList.remove("active"); render(); };
document.getElementById("back").onclick = function(){ drill = null; render(); };
window.addEventListener("resize", function(){ chart.resize(); });
render();
</script>
</body>
</html>
"""
