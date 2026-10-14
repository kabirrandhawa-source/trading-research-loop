"""One-shot desk status: everything the head of the desk needs before answering. Read-only.

    .venv/bin/python -m desk.status          # human-readable
    .venv/bin/python -m desk.status --json   # for agents
"""
import argparse
import json
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS = ["daily", "pm-stream", "pm-recorder", "pm-archive"]


def section(fn):
    try:
        return fn()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}


def jobs():
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout.splitlines()
    res = {}
    for j in JOBS:
        line = next((l for l in out if l.endswith(f"trading-loop.{j}")), None)
        if not line:
            res[j] = "NOT LOADED"
            continue
        pid, status, _ = line.split("\t")
        res[j] = f"running (pid {pid})" if pid != "-" else f"loaded, idle (last exit {status})"
    return res


def recorders():
    pm = ROOT / "data" / "pm"
    out = {}
    stream = sorted(pm.glob("stream-????-??-??.db"))
    if stream:
        c = sqlite3.connect(stream[-1])
        cut = time.time() - 3600
        out["stream_last_hour"] = {t: c.execute(f"SELECT COUNT(*) FROM {t} WHERE ts > ?", (cut,)).fetchone()[0]
                                   for t in ("ws_tob", "ws_trades", "index_values")}
        last = c.execute("SELECT MAX(ts) FROM ws_tob").fetchone()[0]
        out["stream_last_write_s_ago"] = round(time.time() - last) if last else None
    out["archived_days"] = len(list(pm.glob("*.db.xz")))
    out["data_pm_gb"] = round(sum(f.stat().st_size for f in pm.glob("*") if f.is_file()) / 1e9, 2)
    log = ROOT / "logs" / "pm_stream.log"
    if log.exists():
        lines = log.read_text().splitlines()
        out["stream_log_tail"] = lines[-3:]
        out["stream_reconnects_today"] = sum("connected;" in l and l.startswith(datetime.now().strftime("%Y-%m-%d"))
                                             for l in lines)
    return out


def ledger_state():
    import ledger
    conn = ledger.connect()
    rows = conn.execute("SELECT id, status, market, idea, variations_tried, sealed_used_at FROM hypotheses ORDER BY id").fetchall()
    return {
        "by_status": dict(conn.execute("SELECT status, COUNT(*) FROM hypotheses GROUP BY status").fetchall()),
        "hypotheses": [{"id": r[0], "status": r[1], "market": r[2], "idea": r[3][:110], "variations": r[4]} for r in rows],
        "waiting_for_your_sealed_test_decision": [r[0] for r in rows if r[1] == "passed_backtest" and not r[5]],
        "papers_read": conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
    }


def paper_account():
    import broker
    c = broker.paper_client()
    a = c.get_account()
    return {"equity": round(float(a.equity), 2), "day_change": round(float(a.equity) - float(a.last_equity), 2),
            "positions": [{"symbol": p.symbol, "qty": float(p.qty), "unrealized_pl": round(float(p.unrealized_pl), 2)}
                          for p in c.get_all_positions()]}


def latest_files():
    j = ROOT / "journal"
    pick = lambda pat: (sorted(j.glob(pat))[-1].name if list(j.glob(pat)) else None)
    return {"daily_summary": pick("summary-*.md"), "weekly_review": pick("review-*.md"), "morning_brief": pick("brief-*.md")}


def recent_alerts(hours=24):
    cut = time.time() - hours * 3600
    out = []
    for f in sorted((ROOT / "journal").glob("*.jsonl"))[-2:]:
        for line in f.read_text().splitlines():
            e = json.loads(line)
            if e.get("event") == "alert" and datetime.fromisoformat(e["timestamp"]).timestamp() > cut:
                out.append(f"{e['timestamp'][11:16]} UTC [{e.get('priority')}] {e.get('title')}")
    return out[-10:]


def git_state():
    run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"last_commit": run("log", "--oneline", "-1"), "uncommitted_files": len(run("status", "--short").splitlines()),
            "sync": run("status", "-sb").splitlines()[0] if run("status", "-sb") else None}


def status():
    return {"as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "jobs": section(jobs), "recorders": section(recorders), "ledger": section(ledger_state),
            "paper_account": section(paper_account), "latest": section(latest_files),
            "alerts_last_24h": section(recent_alerts), "git": section(git_state),
            "free_disk_gb": round(shutil.disk_usage(ROOT).free / 1e9, 1)}


def render(s):
    L = [f"DESK STATUS  {s['as_of']}", ""]
    L.append("Jobs: " + ", ".join(f"{k} {v}" for k, v in s["jobs"].items()) if "error" not in s["jobs"] else f"Jobs: {s['jobs']}")
    r = s["recorders"]
    if "error" not in r:
        L.append(f"Stream: {r.get('stream_last_hour')} in the last hour; last write {r.get('stream_last_write_s_ago')}s ago; "
                 f"{r.get('stream_reconnects_today', 0)} connects today; data {r['data_pm_gb']} GB, {r['archived_days']} days archived")
    led = s["ledger"]
    if "error" not in led:
        L.append(f"Ledger: {led['by_status']}, {led['papers_read']} papers read")
        for h in led["hypotheses"]:
            L.append(f"  #{h['id']} {h['status']:16} {h['market'][:28]:28} {h['idea'][:70]}")
        if led["waiting_for_your_sealed_test_decision"]:
            L.append(f"  >>> WAITING FOR YOUR DECISION: hypotheses {led['waiting_for_your_sealed_test_decision']}")
    pa = s["paper_account"]
    L.append(f"Paper account: {pa}" if "error" in pa else f"Paper account: ${pa['equity']:,.2f} ({pa['day_change']:+,.2f} today), {len(pa['positions'])} positions")
    L.append(f"Latest: {s['latest']}")
    L.append(f"Alerts (24h): {s['alerts_last_24h'] or 'none'}")
    L.append(f"Git: {s['git']}")
    L.append(f"Free disk: {s['free_disk_gb']} GB")
    return "\n".join(L)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    s = status()
    print(json.dumps(s, indent=2, default=str) if a.json else render(s))
