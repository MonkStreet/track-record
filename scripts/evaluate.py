"""Make every number of the track record from the committed files.

    python scripts/evaluate.py                 check: recompute everything, compare with the files
    python scripts/evaluate.py --write         rewrite results/summary.csv, results/equity.svg and the README results
    python scripts/evaluate.py --close 2026-Q4 --prices <file.csv> --revealed 2027-01-01
                                               write results/2026-Q4.csv and results/2026-Q4.sp500ew.csv, then --write

Inputs: picks/*.csv, seals/*.seal, benchmarks/*.sp500.csv, results/<portfolio>.csv and
results/<portfolio>.sp500ew.csv (both frozen at close).
Python standard library only. No network: the script never calls a price vendor.

THE BENCHMARK (methodology 1.1) is the S&P 500 Equal Weight Total Return, built from its members: every S&P 500
member of the formation day, in benchmarks/<portfolio>.sp500.csv (the Wikipedia page "List of S&P 500 companies" as it
stood at the start of that day, with the page's version number), each priced with the same rules as a pick and
written to results/<portfolio>.sp500ew.csv. Its return is the mean of the members' returns. From 2027-Q1 the seal line
also holds sp500=<SHA-256 of the member file> sp500_rev=<version number>, and the member file must match it.
results/<portfolio>.csv holds the picks only.

The prices file of --close has the columns group, ticker, isin, entry_date, entry_open, exit_date, exit_close, status.
group is pick (one row per pick, by ISIN) or sp500ew (one row per member, ticker = the member's symbol).
The window (entry day, exit day) is the one shared by every held row.

A portfolio SEALED LATE (its formation-day seal was missed and a human sealed it later in the same
quarter) has a seal line ending in "sealed=late entry_date=<date>". Its entry is that day's open, the
first open after its GitHub release; its formation= is the day it was chosen. Its results must enter
on that day, the chain allows that later entry, and the README table marks the row "sealed late".

Rounding: each return is rounded to 6 decimals when it is written. The chained values use the
written (rounded) returns, so anyone can check them from results/summary.csv alone.
"""

import argparse
import csv
import hashlib
import io
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABEL = "S&P 500 equal weight"
GROUPS = ("pick", "sp500ew")
RESULT_COLUMNS = ["ticker", "isin", "entry_date", "entry_open", "exit_date", "exit_close", "total_return", "status"]
PRICE_COLUMNS = ["group"] + [c for c in RESULT_COLUMNS if c != "total_return"]
SUMMARY_COLUMNS = ["portfolio", "chosen", "revealed", "entry_date", "exit_date", "names", "return", "sp500ew_names",
                   "sp500ew_return", "excess_vs_sp500ew", "cumulative_growth_of_1", "cumulative_sp500ew"]
MEMBER_COLUMNS = ["symbol", "security", "cik", "wikipedia_revision"]
SP500_ROWS = (480, 520)  # the S&P 500 has about 503 lines (some companies have two share classes)
STATUSES = ("held", "trading ceased", "late entry")  # and "zero: <reason>"
START, END = "<!-- results:start -->", "<!-- results:end -->"


class EvaluationError(Exception):
    pass


def r6(x):
    return "%.6f" % round(x + 0.0, 6)


def quarter_shift(label, by):
    y, q = int(label[:4]), int(label[-1])
    i = y * 4 + q - 1 + by
    return "%d-Q%d" % (i // 4, i % 4 + 1)


def quarter_start_plus_week(day):
    return day[:8] + "07"


SEAL_LATE = re.compile(r" sealed=late entry_date=(\d{4}-\d{2}-\d{2})\n?$")


def formation_of(label):
    return "%s-%02d-01" % (label[:4], (int(label[-1]) - 1) * 3 + 1)


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---- one portfolio --------------------------------------------------------------------------

def member_return(row, exit_date):
    """Total return of one row: adjusted exit close / adjusted entry open - 1. Applies the corporate-action statuses."""
    status = row["status"]
    if status.startswith("zero:"):
        if not status[5:].strip():
            raise EvaluationError("%s: a zero needs a reason (zero: <reason>)" % row["ticker"])
        return -1.0  # confirmed bankruptcy or delisting with no payout
    if status not in STATUSES:
        raise EvaluationError("%s: unknown status %r" % (row["ticker"], status))
    try:
        entry, exit_ = float(row["entry_open"]), float(row["exit_close"])
    except (TypeError, ValueError):
        raise EvaluationError("%s: missing entry open or exit close" % row["ticker"])
    if entry <= 0 or exit_ <= 0:
        raise EvaluationError("%s: a price is not positive" % row["ticker"])
    if status in ("held", "late entry") and row["exit_date"] != exit_date:
        raise EvaluationError("%s: exit date %s is not the portfolio exit %s" % (row["ticker"], row["exit_date"], exit_date))
    if status == "trading ceased" and not (row["entry_date"] <= row["exit_date"] < exit_date):
        raise EvaluationError("%s: last trading day %s is not inside the window" % (row["ticker"], row["exit_date"]))
    if row["entry_date"] > row["exit_date"]:
        raise EvaluationError("%s: entry %s is after exit %s" % (row["ticker"], row["entry_date"], row["exit_date"]))
    # trading ceased: the last available close, then cash at 0% until exit.
    # late entry: cash at 0% until the first available open. Both use the same formula.
    return exit_ / entry - 1.0


def from_series(ticker, isin, series, entry_date, exit_date, zero_reason=None):
    """One price row from a daily series {date: (adjusted open, adjusted close)}, by METHODOLOGY section 4.
    A gap in the data is never a zero: a zero needs a confirmed reason."""
    row = {"ticker": ticker, "isin": isin, "entry_date": "", "entry_open": "", "exit_date": "", "exit_close": ""}
    if zero_reason:
        row["status"] = "zero: " + zero_reason
        return row
    days = sorted(d for d in series if entry_date <= d <= exit_date)
    opens = [d for d in days if series[d][0] not in (None, "")]
    if not opens:
        raise EvaluationError("%s: no open in the window. Find the price, or give a confirmed zero reason." % ticker)
    entry = opens[0]
    closes = [d for d in days if d >= entry and series[d][1] not in (None, "")]
    last = closes[-1]
    row.update(entry_date=entry, entry_open=str(series[entry][0]), exit_date=last, exit_close=str(series[last][1]))
    row["status"] = "trading ceased" if last < exit_date else ("late entry" if entry > entry_date else "held")
    return row


def window_of(rows, what):
    """(entry_date, exit_date): the days shared by every held row. A held row on other days is an error."""
    days = set((r["entry_date"], r["exit_date"]) for r in rows if r["status"] == "held")
    if len(days) != 1:
        raise EvaluationError("%s: the held rows must share one entry day and one exit day, found %s"
                              % (what, ", ".join("%s..%s" % d for d in sorted(days)) or "none"))
    return days.pop()


def build_results(picks, prices, members):
    """picks: rows of picks/<Q>.csv. prices: PRICE_COLUMNS rows. members: rows of benchmarks/<Q>.sp500.csv.
    Returns (results, sp500ew): the frozen rows of results/<Q>.csv (one per pick, pick-file order) and of
    results/<Q>.sp500ew.csv (one per member, member-file order)."""
    groups = {g: [] for g in GROUPS}
    for p in prices:
        g = p.get("group", "")
        if g not in GROUPS:
            raise EvaluationError("%s: unknown group %r (pick or sp500ew)" % (p.get("ticker"), g))
        groups[g].append(p)
    entry_date, exit_date = window_of(prices, "prices")

    def keyed(rows, key, what):
        out = {}
        for p in rows:
            if p[key] in out:
                raise EvaluationError("%s: two %s price rows" % (p[key], what))
            out[p[key]] = p
        return out

    def same_set(have, want, what):
        missing = [w for w in want if w not in have]
        if missing:
            raise EvaluationError("no %s price row for: %s" % (what, ", ".join(missing[:10])))
        extra = sorted(set(have) - set(want))
        if extra:
            raise EvaluationError("%s price rows for names not in the list: %s" % (what, ", ".join(extra[:10])))

    def frozen(p):
        ret = member_return(p, exit_date)  # checks the status first
        late = p["status"] in ("late entry", "trading ceased") and p["entry_date"] > entry_date
        if not p["status"].startswith("zero:") and p["entry_date"] != entry_date and not late:
            raise EvaluationError("%s: entry date %s is not the portfolio entry %s" % (p["ticker"], p["entry_date"], entry_date))
        row = {c: p.get(c, "") for c in RESULT_COLUMNS}
        row["total_return"] = r6(ret)
        return row

    by_isin = keyed(groups["pick"], "isin", "pick")
    same_set(by_isin, [x["isin"] for x in picks], "pick")
    by_sym = keyed(groups["sp500ew"], "ticker", "S&P 500 member")
    same_set(by_sym, [m["symbol"] for m in members], "S&P 500 member")
    return [frozen(by_isin[x["isin"]]) for x in picks], [frozen(by_sym[m["symbol"]]) for m in members]


def mean_return(rows, label, what, exit_date):
    if not rows:
        raise EvaluationError("%s: no %s rows" % (label, what))
    for r in rows:  # the committed returns must follow from the committed closes
        if r["total_return"] != r6(member_return(r, exit_date)):
            raise EvaluationError("%s %s %s: total_return does not follow from its closes" % (label, what, r["ticker"]))
    return sum(float(r["total_return"]) for r in rows) / len(rows)


def summarize(label, results, ew, chosen, revealed):
    """One summary row without the chained columns. results: results/<Q>.csv rows; ew: results/<Q>.sp500ew.csv rows."""
    entry_date, exit_date = window_of(results + ew, label)
    ret = mean_return(results, label, "pick", exit_date)
    ewr = mean_return(ew, label, "S&P 500 member", exit_date)
    return {"portfolio": label, "chosen": chosen, "revealed": revealed, "entry_date": entry_date, "exit_date": exit_date,
            "names": str(len(results)), "return": r6(ret), "sp500ew_names": str(len(ew)), "sp500ew_return": r6(ewr),
            "excess_vs_sp500ew": r6(float(r6(ret)) - float(r6(ewr)))}


def chain(rows, late=None):
    """Add the cumulative columns. Portfolios do not overlap, so values compound quarter after quarter.
    Each portfolio exits at the last close of its quarter and the next one enters at the first open
    of the next quarter: after the previous exit, and within a week of the formation day.
    late: {portfolio: entry_date} of the portfolios sealed late. Such a portfolio enters on its sealed
    entry day, which may be any day of its quarter (cash at 0% from the formation day until then)."""
    late = late or {}
    rows = sorted(rows, key=lambda r: r["portfolio"])
    g = ew = 1.0
    prev = None
    for r in rows:
        if prev is not None:
            if r["portfolio"] != quarter_shift(prev["portfolio"], 1):
                raise EvaluationError("%s does not follow %s: a quarter is missing" % (r["portfolio"], prev["portfolio"]))
            f = formation_of(r["portfolio"])
            if r["portfolio"] in late:  # sealed late: any day of its own quarter
                ok = prev["exit_date"] < f <= r["entry_date"] < formation_of(quarter_shift(r["portfolio"], 1))
            else:
                ok = prev["exit_date"] < f <= r["entry_date"] <= quarter_start_plus_week(f)
            if not ok:
                raise EvaluationError("%s enters on %s, but %s exits on %s: the chain has a gap or an overlap"
                                      % (r["portfolio"], r["entry_date"], prev["portfolio"], prev["exit_date"]))
        g = float(r6(g * (1 + float(r["return"]))))
        ew = float(r6(ew * (1 + float(r["sp500ew_return"]))))
        r["cumulative_growth_of_1"], r["cumulative_sp500ew"] = r6(g), r6(ew)
        prev = r
    return rows


# ---- files ----------------------------------------------------------------------------------

def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_csv(rows, columns):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


def seal_labels(root):
    d = os.path.join(root, "seals")
    return [m.group(1) for m in (re.match(r"^(\d{4}-Q[1-4])\.seal$", f) for f in (sorted(os.listdir(d)) if os.path.isdir(d) else [])) if m]


def seal_fields(root, label):
    """The key=value fields of a seal line."""
    return dict(re.findall(r"(\w+)=(\S+)", read_text(os.path.join(root, "seals", label + ".seal"))))


def seals(root):
    return {label: seal_fields(root, label)["formation"] for label in seal_labels(root)}


def late_entries(root):
    """{portfolio: entry_date} of the portfolios sealed late, from their seal lines."""
    out = {}
    d = os.path.join(root, "seals")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = re.match(r"^(\d{4}-Q[1-4])\.seal$", f)
        if m:
            text = read_text(os.path.join(d, f))
            if "sealed=late" in text or "entry_date=" in text:
                x = SEAL_LATE.search(text)
                if not x:
                    raise EvaluationError("%s: a late seal needs \"sealed=late entry_date=<date>\" at the end of its line" % m.group(1))
                out[m.group(1)] = x.group(1)
    return out


def members_of(root, label):
    """benchmarks/<Q>.sp500.csv, checked: its columns, about 500 members, no symbol twice, one page version number,
    and, for a seal made under methodology 1.1 or later (from 2027-Q1), the sp500= and sp500_rev= of the seal."""
    path = os.path.join(root, "benchmarks", label + ".sp500.csv")
    if not os.path.exists(path):
        raise EvaluationError("%s: no benchmarks/%s.sp500.csv (the S&P 500 members of the formation day)" % (label, label))
    rows = read_csv(path)
    if not rows or list(rows[0].keys()) != MEMBER_COLUMNS:
        raise EvaluationError("benchmarks/%s.sp500.csv: the columns must be %s" % (label, ",".join(MEMBER_COLUMNS)))
    if not SP500_ROWS[0] <= len(rows) <= SP500_ROWS[1]:
        raise EvaluationError("benchmarks/%s.sp500.csv: %d members, not %d to %d" % (label, len(rows), SP500_ROWS[0], SP500_ROWS[1]))
    syms = [r["symbol"] for r in rows]
    if len(set(syms)) != len(syms) or not all(syms):
        raise EvaluationError("benchmarks/%s.sp500.csv: a symbol is empty or listed twice" % label)
    revs = set(r["wikipedia_revision"] for r in rows)
    rev = revs.pop() if len(revs) == 1 else ""
    if not re.match(r"^\d+$", rev):
        raise EvaluationError("benchmarks/%s.sp500.csv: one page version number on every row" % label)
    f = seal_fields(root, label) if os.path.exists(os.path.join(root, "seals", label + ".seal")) else {}
    if f and f.get("methodology") != "1.0":
        if sha256_file(path) != f.get("sp500"):
            raise EvaluationError("benchmarks/%s.sp500.csv does not match the sp500= fingerprint of its seal" % label)
        if f.get("sp500_rev") != rev:
            raise EvaluationError("benchmarks/%s.sp500.csv is page version %s, the seal says %s" % (label, rev, f.get("sp500_rev")))
    return rows


def chosen_cell(chosen, label, late):
    return "%s, sealed late (entry %s)" % (chosen, late[label]) if label in late else chosen


def fingerprint_cell(root, label):
    """First 8 characters of the seal's SHA-256, linked to the seal file."""
    path = os.path.join(root, "seals", label + ".seal")
    if not os.path.exists(path):
        return "-"
    m = re.search(r"sha256=([0-9a-f]{64})", read_text(path))
    if not m:
        raise EvaluationError("%s: seal has no sha256" % label)
    return "[`%s`](seals/%s.seal)" % (m.group(1)[:8], label)


def closed_labels(root):
    d = os.path.join(root, "results")
    return sorted(f[:-4] for f in (os.listdir(d) if os.path.isdir(d) else []) if re.match(r"^\d{4}-Q[1-4]\.csv$", f))


def compute_summary(root, revealed):
    """revealed: {label: date}. Taken from the committed summary, or given by --close."""
    chosen = seals(root)
    late = late_entries(root)
    closed = closed_labels(root)
    for label in seal_labels(root):  # from 2027-Q1 the member list is published with the seal and must match it
        if label not in closed and seal_fields(root, label).get("methodology") != "1.0":
            members_of(root, label)
    rows = []
    for label in closed:
        if label not in revealed:
            raise EvaluationError("%s: no reveal date" % label)
        ew_path = os.path.join(root, "results", label + ".sp500ew.csv")
        if not os.path.exists(ew_path):
            raise EvaluationError("%s: results/%s.sp500ew.csv is missing" % (label, label))
        ew = read_csv(ew_path)
        if [r["ticker"] for r in ew] != [m["symbol"] for m in members_of(root, label)]:
            raise EvaluationError("%s: results/%s.sp500ew.csv does not list the members of benchmarks/%s.sp500.csv" % (label, label, label))
        row = summarize(label, read_csv(os.path.join(root, "results", label + ".csv")), ew, chosen.get(label, ""), revealed[label])
        if label in late and row["entry_date"] != late[label]:
            raise EvaluationError("%s was sealed late with entry %s, but its results enter on %s" % (label, late[label], row["entry_date"]))
        rows.append(row)
    return chain(rows, late)


def pct(x):
    return "%+.2f%%" % (float(x) * 100)


def results_block(summary, root):
    header = ["| Portfolio | Chosen | Fingerprint | Revealed | Return | %s | Excess | Note |" % LABEL, "|---|---|---|---|---|---|---|---|"]
    lines = []
    late = late_entries(root)
    for r in summary:
        note = "notes/%s.md" % r["portfolio"]
        lines.append("| [%s](results/%s.csv) | %s | %s | %s | %s | %s | %s | %s |" % (
            r["portfolio"], r["portfolio"], chosen_cell(r["chosen"], r["portfolio"], late), fingerprint_cell(root, r["portfolio"]), r["revealed"], pct(r["return"]),
            pct(r["sp500ew_return"]), pct(r["excess_vs_sp500ew"]),
            "[note](%s)" % note if os.path.exists(os.path.join(root, note)) else "-"))
    closed = set(r["portfolio"] for r in summary)
    for label, chosen in sorted(seals(root).items()):
        if label in closed:
            continue  # an open quarter shows no figures (METHODOLOGY section 6)
        lines.append("| %s | %s | %s | due %s | - | - | - | - |" % (label, chosen_cell(chosen, label, late), fingerprint_cell(root, label), formation_of(quarter_shift(label, 1))))
    # Newest first: the open quarter, then the latest closed one. Rows sort by portfolio label.
    lines = header + sorted(lines, key=lambda l: l.split("|")[1].strip().strip("[").split("]")[0], reverse=True)
    lines.append("")
    if summary:
        last = summary[-1]
        lines.append("Since launch: $1 in the record is now $%.2f. In the %s: $%.2f." % (
            float(last["cumulative_growth_of_1"]), LABEL, float(last["cumulative_sp500ew"])))
        lines.append("")
        lines.append("![Growth of $1: the MonkScore 90+ record and the S&P 500 equal weight, one point for each closed quarter](results/equity.svg)")
    else:
        lines.append("Since launch: no portfolio has closed yet.")
    return "\n".join(lines)


# ---- the equity curve -----------------------------------------------------------------------

SVG_W, SVG_H = 720, 360
SVG_LEFT, SVG_RIGHT, SVG_TOP, SVG_BOTTOM = 72, 64, 56, 56
RECORD_COLOR, BENCH_COLOR = "#2a78d6", "#eb6834"


def nice_step(span):
    for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0):
        if span / step <= 6:
            return step
    return 20.0


def equity_svg(summary):
    """Growth of $1: the record and the S&P 500 equal weight. One point per closed quarter, from 1.00.
    Plain SVG: no script, no external font. The same summary always gives the same bytes."""
    labels = ["Start"] + [r["portfolio"] for r in summary]
    record = [1.0] + [float(r["cumulative_growth_of_1"]) for r in summary]
    bench = [1.0] + [float(r["cumulative_sp500ew"]) for r in summary]
    step = nice_step(max(record + bench) - min(record + bench) or 0.1)
    lo = math.floor(min(record + bench) / step + 1e-9) * step
    hi = math.ceil(max(record + bench) / step - 1e-9) * step
    if hi - lo < step:
        lo, hi = lo - step, hi + step
    pw, ph = SVG_W - SVG_LEFT - SVG_RIGHT, SVG_H - SVG_TOP - SVG_BOTTOM
    n = len(labels)

    def x(i):
        return SVG_LEFT + (pw * i / (n - 1) if n > 1 else pw / 2)

    def y(v):
        return SVG_TOP + ph * (hi - v) / (hi - lo)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="sans-serif" font-size="12" role="img" aria-labelledby="t">' % (SVG_W, SVG_H, SVG_W, SVG_H),
           '<title id="t">Growth of $1: MonkScore 90+ record and S&amp;P 500 equal weight, by closed quarter</title>',
           '<rect width="%d" height="%d" fill="#fcfcfb"/>' % (SVG_W, SVG_H)]
    ticks = int(round((hi - lo) / step))
    for k in range(ticks + 1):
        v = lo + k * step
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>'
                   % (SVG_LEFT, y(v), SVG_LEFT + pw, y(v), "#52514e" if abs(v - 1.0) < 1e-9 else "#e4e3df"))
        out.append('<text x="%d" y="%.1f" text-anchor="end" fill="#52514e">$%.2f</text>' % (SVG_LEFT - 8, y(v) + 4, v))
    for i, label in enumerate(labels):
        out.append('<text x="%.1f" y="%d" text-anchor="middle" fill="#52514e">%s</text>' % (x(i), SVG_TOP + ph + 20, label))
    out.append('<text x="%.1f" y="%d" text-anchor="middle" fill="#0b0b0b">End of quarter</text>'
               % (SVG_LEFT + pw / 2, SVG_H - 12))
    out.append('<text x="16" y="%.1f" text-anchor="middle" fill="#0b0b0b" transform="rotate(-90 16 %.1f)">Growth of $1</text>'
               % (SVG_TOP + ph / 2, SVG_TOP + ph / 2))
    for values, color, dash in ((bench, BENCH_COLOR, ' stroke-dasharray="6 4"'), (record, RECORD_COLOR, "")):
        pts = " ".join("%.1f,%.1f" % (x(i), y(v)) for i, v in enumerate(values))
        out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"%s/>' % (pts, color, dash))
        for i, v in enumerate(values):
            out.append('<circle cx="%.1f" cy="%.1f" r="4" fill="%s" stroke="#fcfcfb" stroke-width="2"/>' % (x(i), y(v), color))
        out.append('<text x="%.1f" y="%.1f" fill="#0b0b0b">$%.2f</text>' % (x(n - 1) + 10, y(values[-1]) + 4, values[-1]))
    for k, (color, dash, name) in enumerate(((RECORD_COLOR, "", "MonkScore 90+ record"),
                                            (BENCH_COLOR, ' stroke-dasharray="6 4"', "S&amp;P 500 equal weight"))):
        lx, ly = SVG_LEFT + k * 220, 24
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2"%s/>' % (lx, ly, lx + 24, ly, color, dash))
        out.append('<text x="%d" y="%d" fill="#0b0b0b">%s</text>' % (lx + 30, ly + 4, name))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def readme_with(root, block):
    text = read_text(os.path.join(root, "README.md"))
    a, b = text.find(START), text.find(END)
    if a < 0 or b < a:
        raise EvaluationError("README.md has no results markers")
    return text[:a + len(START)] + "\n" + block + "\n" + text[b:]


def committed_revealed(root):
    p = os.path.join(root, "results", "summary.csv")
    return ({r["portfolio"]: r["revealed"] for r in read_csv(p)}, read_csv(p)) if os.path.exists(p) else ({}, [])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make every number of the track record from the committed files.")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--close")
    ap.add_argument("--prices")
    ap.add_argument("--revealed")
    ap.add_argument("--root", default=ROOT)
    a = ap.parse_args(argv)
    root = a.root
    revealed, old = committed_revealed(root)
    try:
        if a.close:
            if not (a.prices and a.revealed):
                raise EvaluationError("--close needs --prices and --revealed")
            outs = [os.path.join(root, "results", a.close + x) for x in (".csv", ".sp500ew.csv")]
            for out in outs:
                if os.path.exists(out):
                    raise EvaluationError("results/%s exists. A closed report never changes." % os.path.basename(out))
            built = build_results(read_csv(os.path.join(root, "picks", a.close + ".csv")), read_csv(a.prices), members_of(root, a.close))
            os.makedirs(os.path.dirname(outs[0]), exist_ok=True)
            for out, rows in zip(outs, built):
                with open(out, "w", newline="", encoding="utf-8") as f:
                    f.write(to_csv(rows, RESULT_COLUMNS))
            revealed[a.close] = a.revealed
            a.write = True
        summary = compute_summary(root, revealed)
        for o, n in zip(old, summary):  # summary.csv is append-only
            if any(o[c] != n[c] for c in SUMMARY_COLUMNS):
                raise EvaluationError("results/summary.csv row %s would change. It is append-only." % o["portfolio"])
        summary_text = to_csv(summary, SUMMARY_COLUMNS)
        readme = readme_with(root, results_block(summary, root))
        svg_path = os.path.join(root, "results", "equity.svg")
        svg = equity_svg(summary) if summary else None
        if a.write:
            if summary:
                with open(os.path.join(root, "results", "summary.csv"), "w", newline="", encoding="utf-8") as f:
                    f.write(summary_text)
                with open(svg_path, "w", newline="", encoding="utf-8") as f:
                    f.write(svg)
            with open(os.path.join(root, "README.md"), "w", newline="", encoding="utf-8") as f:
                f.write(readme)
            print("evaluate.py: wrote %d closed portfolio(s)." % len(summary))
            return 0
        bad = []
        sp = os.path.join(root, "results", "summary.csv")
        if (read_text(sp) if os.path.exists(sp) else (summary_text if not summary else "")) != summary_text:
            bad.append("results/summary.csv")
        if svg is not None and (read_text(svg_path) if os.path.exists(svg_path) else None) != svg:
            bad.append("results/equity.svg")
        if read_text(os.path.join(root, "README.md")) != readme:
            bad.append("README.md results")
        if bad:
            print("evaluate.py: MISMATCH in " + ", ".join(bad))
            return 1
        print("evaluate.py: OK. %d closed portfolio(s); every number matches the committed files." % len(summary))
        return 0
    except EvaluationError as e:
        print("evaluate.py: " + str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
