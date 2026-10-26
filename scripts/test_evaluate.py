"""Tests for evaluate.py on a planted example. Run: python scripts/test_evaluate.py"""

import hashlib
import os
import shutil
import tempfile
import unittest

import evaluate as E

PICKS = [{"ticker": "NYSE:AAA", "isin": "US0000000001"}, {"ticker": "NASDAQ:BBB", "isin": "US0000000002"},
         {"ticker": "NYSE:CCC", "isin": "US0000000003"}, {"ticker": "NYSE:DDD", "isin": "US0000000004"}]
REV = "1249000000"
MEMBERS = [{"symbol": "M%03d" % i, "security": "Member %d" % i, "cik": "%010d" % (i + 1), "wikipedia_revision": REV}
           for i in range(500)]


def price(ticker, isin, entry, exit_, status="held", entry_date="2026-10-01", exit_date="2026-12-31", group="pick"):
    return {"group": group, "ticker": ticker, "isin": isin, "entry_date": entry_date, "entry_open": entry,
            "exit_date": exit_date, "exit_close": exit_, "status": status}


def member_prices(entry_date="2026-10-01"):
    return [price(m["symbol"], "", "100", "102", entry_date=entry_date, group="sp500ew") for m in MEMBERS]  # +2% each


def prices():
    return [price("NYSE:AAA", "US0000000001", "100", "110"),                       # +10%
            price("NASDAQ:BBB", "US0000000002", "50", "45"),                        # -10%
            price("NYSE:CCC", "US0000000003", "20", "25", "trading ceased", exit_date="2026-11-16"),  # +25%, then cash
            price("NYSE:DDD", "US0000000004", "", "", "zero: bankruptcy, no payout", "", ""),  # -100%
            ] + member_prices()


def members_text(members=None, columns=None):
    return E.to_csv(MEMBERS if members is None else members, columns or E.MEMBER_COLUMNS)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


class OnePortfolio(unittest.TestCase):
    def test_green_returns(self):
        rows, ew = E.build_results(PICKS, prices(), MEMBERS)
        self.assertEqual([r["total_return"] for r in rows], ["0.100000", "-0.100000", "0.250000", "-1.000000"])
        self.assertEqual((len(ew), set(r["total_return"] for r in ew)), (500, {"0.020000"}))
        s = E.summarize("2026-Q4", rows, ew, "2026-10-01", "2027-01-01")
        self.assertEqual((s["return"], s["sp500ew_return"], s["excess_vs_sp500ew"], s["names"], s["sp500ew_names"]),
                         ("-0.187500", "0.020000", "-0.207500", "4", "500"))
        self.assertEqual((s["entry_date"], s["exit_date"]), ("2026-10-01", "2026-12-31"))

    def test_green_one_benchmark_only(self):
        self.assertEqual([c for c in E.SUMMARY_COLUMNS if "sp500" in c],
                         ["sp500ew_names", "sp500ew_return", "excess_vs_sp500ew", "cumulative_sp500ew"])
        self.assertNotIn("benchmark", E.STATUSES)

    def test_green_delisted_name_uses_last_close_then_cash(self):
        rows, _ = E.build_results(PICKS, prices(), MEMBERS)
        ccc = rows[2]
        self.assertEqual((ccc["status"], ccc["exit_date"], ccc["total_return"]), ("trading ceased", "2026-11-16", "0.250000"))

    def test_green_a_member_that_stops_trading_is_priced_like_a_pick(self):
        p = prices()
        p[4].update(status="trading ceased", exit_date="2026-11-02", exit_close="90")
        _, ew = E.build_results(PICKS, p, MEMBERS)
        self.assertEqual((ew[0]["status"], ew[0]["total_return"]), ("trading ceased", "-0.100000"))

    def test_red_a_zero_without_a_reason(self):
        p = prices()
        p[3]["status"] = "zero: "
        with self.assertRaisesRegex(E.EvaluationError, "needs a reason"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_an_unknown_group(self):
        p = prices()
        p[4]["group"] = "sp500tr"
        with self.assertRaisesRegex(E.EvaluationError, "unknown group"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_the_old_no_price_status_is_refused(self):
        p = prices()
        p[3]["status"] = "no price"
        with self.assertRaisesRegex(E.EvaluationError, "unknown status"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_missing_exit_price(self):
        p = prices()
        p[0]["exit_close"] = ""
        with self.assertRaisesRegex(E.EvaluationError, "missing entry open or exit close"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_held_rows_on_different_days(self):
        p = prices()
        p[1]["exit_date"] = "2026-12-01"
        with self.assertRaisesRegex(E.EvaluationError, "share one entry day and one exit day"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_a_late_entry_that_exits_early(self):
        p = prices()
        p[1].update(status="late entry", entry_date="2026-10-02", exit_date="2026-12-01")
        with self.assertRaisesRegex(E.EvaluationError, "not the portfolio exit"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_delisting_date_outside_the_window(self):
        p = prices()
        p[2]["exit_date"] = "2027-02-01"
        with self.assertRaisesRegex(E.EvaluationError, "not inside the window"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_a_pick_without_a_price_row(self):
        with self.assertRaisesRegex(E.EvaluationError, "no pick price row"):
            E.build_results(PICKS, prices()[1:], MEMBERS)

    def test_red_a_member_without_a_price_row(self):
        with self.assertRaisesRegex(E.EvaluationError, "no S&P 500 member price row for: M499"):
            E.build_results(PICKS, prices()[:-1], MEMBERS)

    def test_red_a_price_row_for_a_name_not_in_the_member_list(self):
        p = prices() + [price("XTRA", "", "100", "102", group="sp500ew")]
        with self.assertRaisesRegex(E.EvaluationError, "not in the list: XTRA"):
            E.build_results(PICKS, p, MEMBERS)

    def test_red_a_return_that_does_not_follow_from_its_closes(self):
        rows, ew = E.build_results(PICKS, prices(), MEMBERS)
        ew[7]["total_return"] = "0.200000"
        with self.assertRaisesRegex(E.EvaluationError, "does not follow"):
            E.summarize("2026-Q4", rows, ew, "2026-10-01", "2027-01-01")


class MemberList(unittest.TestCase):
    """benchmarks/<Q>.sp500.csv: the S&P 500 members of the formation day."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def members(self, text):
        write(self.root, "benchmarks/2027-Q1.sp500.csv", text)

    def seal(self, extra="", methodology="1.1"):
        write(self.root, "seals/2027-Q1.seal", "sha256=%s file=picks/2027-Q1.csv formation=2027-01-01 names=4 model=3.11.0 "
              "methodology=%s%s\n" % ("0" * 64, methodology, extra))

    def fields(self, text):
        return " sp500=%s sp500_rev=%s" % (hashlib.sha256(text.encode("utf-8")).hexdigest(), REV)

    def test_green_a_good_list_that_matches_its_seal(self):
        t = members_text()
        self.members(t)
        self.seal(self.fields(t))
        self.assertEqual(len(E.members_of(self.root, "2027-Q1")), 500)

    def test_green_a_1_0_seal_names_no_list(self):
        self.members(members_text())
        self.seal(methodology="1.0")
        self.assertEqual(len(E.members_of(self.root, "2027-Q1")), 500)

    def test_red_no_list(self):
        with self.assertRaisesRegex(E.EvaluationError, "no benchmarks/2027-Q1.sp500.csv"):
            E.members_of(self.root, "2027-Q1")

    def test_red_wrong_columns(self):
        self.members(members_text(columns=["symbol", "security", "cik"]))
        with self.assertRaisesRegex(E.EvaluationError, "the columns must be"):
            E.members_of(self.root, "2027-Q1")

    def test_red_too_few_members(self):
        self.members(members_text(MEMBERS[:400]))
        with self.assertRaisesRegex(E.EvaluationError, "400 members, not 480 to 520"):
            E.members_of(self.root, "2027-Q1")

    def test_red_a_symbol_listed_twice(self):
        self.members(members_text(MEMBERS[:499] + [MEMBERS[0]]))
        with self.assertRaisesRegex(E.EvaluationError, "listed twice"):
            E.members_of(self.root, "2027-Q1")

    def test_red_two_page_versions(self):
        m = [dict(x) for x in MEMBERS]
        m[3]["wikipedia_revision"] = "1249000001"
        self.members(members_text(m))
        with self.assertRaisesRegex(E.EvaluationError, "one page version number"):
            E.members_of(self.root, "2027-Q1")

    def test_red_a_1_1_seal_without_the_list_fingerprint(self):
        self.members(members_text())
        self.seal()
        with self.assertRaisesRegex(E.EvaluationError, "sp500= fingerprint"):
            E.members_of(self.root, "2027-Q1")

    def test_red_a_list_changed_after_its_seal(self):
        t = members_text()
        self.seal(self.fields(t))
        self.members(t.replace("Member 7,", "Member Seven,"))
        with self.assertRaisesRegex(E.EvaluationError, "sp500= fingerprint"):
            E.members_of(self.root, "2027-Q1")

    def test_red_a_seal_with_another_page_version(self):
        t = members_text()
        self.members(t)
        self.seal(self.fields(t).replace(REV, "1249000009"))
        with self.assertRaisesRegex(E.EvaluationError, "page version 1249000000, the seal says 1249000009"):
            E.members_of(self.root, "2027-Q1")

    def test_red_an_open_1_1_quarter_whose_list_is_missing(self):
        self.seal(self.fields(members_text()))
        write(self.root, "README.md", "x\n%s\n%s\n" % (E.START, E.END))
        self.assertEqual(E.main(["--root", self.root, "--write"]), 1)


SERIES = {"2026-10-01": ("100", "101"), "2026-10-02": ("101", "102"), "2026-11-02": ("103", "104"),
          "2026-12-30": ("108", "109"), "2026-12-31": ("109", "110")}


class FromSeries(unittest.TestCase):
    def test_green_a_full_series_is_held(self):
        r = E.from_series("NYSE:AAA", "US1", SERIES, "2026-10-01", "2026-12-31")
        self.assertEqual((r["status"], r["entry_open"], r["exit_close"]), ("held", "100", "110"))

    def test_red_a_mid_quarter_gap_is_valued_at_the_last_close_not_zero(self):
        s = {d: v for d, v in SERIES.items() if d < "2026-11-03"}  # no data after 2026-11-02
        r = E.from_series("NYSE:AAA", "US1", s, "2026-10-01", "2026-12-31")
        self.assertEqual((r["status"], r["exit_date"], r["exit_close"]), ("trading ceased", "2026-11-02", "104"))
        self.assertEqual(E.r6(E.member_return(r, "2026-12-31")), "0.040000")

    def test_green_a_gap_on_the_entry_day_enters_at_the_first_open(self):
        s = {d: v for d, v in SERIES.items() if d != "2026-10-01"}
        r = E.from_series("NYSE:AAA", "US1", s, "2026-10-01", "2026-12-31")
        self.assertEqual((r["status"], r["entry_date"], r["entry_open"]), ("late entry", "2026-10-02", "101"))

    def test_red_no_price_in_the_window_is_not_a_silent_zero(self):
        with self.assertRaisesRegex(E.EvaluationError, "confirmed zero reason"):
            E.from_series("NYSE:AAA", "US1", {}, "2026-10-01", "2026-12-31")

    def test_green_a_confirmed_zero_keeps_its_reason(self):
        r = E.from_series("NYSE:AAA", "US1", {}, "2026-10-01", "2026-12-31", "bankruptcy, no payout")
        self.assertEqual(r["status"], "zero: bankruptcy, no payout")


def summary_row(label, entry, exit_, ret, ew):
    return {"portfolio": label, "entry_date": entry, "exit_date": exit_, "return": ret, "sp500ew_return": ew}


class Chain(unittest.TestCase):
    def test_green_chaining(self):
        rows = E.chain([summary_row("2026-Q4", "2026-10-01", "2026-12-31", "0.100000", "0.020000"),
                        summary_row("2027-Q1", "2027-01-04", "2027-03-31", "-0.050000", "0.010000")])
        self.assertEqual([(r["cumulative_growth_of_1"], r["cumulative_sp500ew"]) for r in rows],
                         [("1.100000", "1.020000"), ("1.045000", "1.030200")])

    def test_red_a_gap_between_portfolios(self):
        with self.assertRaisesRegex(E.EvaluationError, "gap or an overlap"):
            E.chain([summary_row("2026-Q4", "2026-10-01", "2026-12-31", "0.1", "0"),
                     summary_row("2027-Q1", "2027-01-11", "2027-03-31", "0.1", "0")])

    def test_red_an_overlap_between_portfolios(self):
        with self.assertRaisesRegex(E.EvaluationError, "gap or an overlap"):
            E.chain([summary_row("2026-Q4", "2026-10-01", "2027-01-04", "0.1", "0"),
                     summary_row("2027-Q1", "2027-01-04", "2027-03-31", "0.1", "0")])

    def test_red_a_missing_quarter(self):
        with self.assertRaisesRegex(E.EvaluationError, "quarter is missing"):
            E.chain([summary_row("2026-Q4", "2026-10-01", "2026-12-31", "0.1", "0"),
                     summary_row("2027-Q2", "2027-04-01", "2027-06-30", "0.1", "0")])

    def test_red_wrong_chaining_in_a_committed_summary_is_found(self):
        root = tempfile.mkdtemp()
        try:
            write(root, "picks/2026-Q4.csv", "ticker,isin\n" + "".join("%s,%s\n" % (p["ticker"], p["isin"]) for p in PICKS))
            write(root, "seals/2026-Q4.seal", "sha256=%s file=picks/2026-Q4.csv formation=2026-10-01 names=4 model=3.9.17 methodology=1.0\n" % ("0" * 64))
            write(root, "README.md", "x\n%s\n%s\n" % (E.START, E.END))
            write(root, "benchmarks/2026-Q4.sp500.csv", members_text())  # 2026-Q4: published at the reveal, its seal names no list
            p = write(root, "prices.csv", E.to_csv(prices(), E.PRICE_COLUMNS))
            self.assertEqual(E.main(["--root", root, "--close", "2026-Q4", "--prices", p, "--revealed", "2027-01-01"]), 0)
            self.assertEqual(len(E.read_csv(os.path.join(root, "results", "2026-Q4.sp500ew.csv"))), 500)
            self.assertEqual(len(E.read_csv(os.path.join(root, "results", "2026-Q4.csv"))), 4)  # the picks only
            self.assertEqual(E.main(["--root", root, "--close", "2026-Q4", "--prices", p, "--revealed", "2027-01-01"]), 1)  # frozen
            self.assertEqual(E.main(["--root", root]), 0)  # GREEN: the files agree
            sp = os.path.join(root, "results", "summary.csv")
            text = E.read_text(sp)
            with open(sp, "w", encoding="utf-8") as f:
                f.write(text.replace("0.812500", "0.900000"))  # plant a wrong cumulative value
            self.assertEqual(E.main(["--root", root]), 1)  # RED
            readme = E.read_text(os.path.join(root, "README.md"))
            self.assertIn("Since launch: $1 in the record is now $0.81. In the S&P 500 equal weight: $1.02.", readme)
            self.assertIn("| +2.00% | -20.75% | - |", readme)  # no note yet: no link
            self.assertIn("| Return | S&P 500 equal weight | Excess | Note |", readme)
            with open(sp, "w", encoding="utf-8") as f:
                f.write(text)  # restore the correct summary
            self.assertEqual(E.main(["--root", root]), 0)
            ewp = os.path.join(root, "results", "2026-Q4.sp500ew.csv")
            ew = E.read_text(ewp)
            write(root, "results/2026-Q4.sp500ew.csv", ew.replace("M003,", "M999,"))
            self.assertEqual(E.main(["--root", root]), 1)  # RED: the member results no longer list the member file
            write(root, "results/2026-Q4.sp500ew.csv", ew)
            os.makedirs(os.path.join(root, "notes"))
            with open(os.path.join(root, "notes", "2026-Q4.md"), "w", encoding="utf-8") as f:
                f.write("# 2026-Q4 note")
            self.assertEqual(E.main(["--root", root]), 1)  # RED: the README misses the new note link
            self.assertEqual(E.main(["--root", root, "--write"]), 0)
            self.assertIn("| [note](notes/2026-Q4.md) |", E.read_text(os.path.join(root, "README.md")))  # GREEN
            svg_path = os.path.join(root, "results", "equity.svg")
            svg = E.read_text(svg_path)
            with open(svg_path, "w", encoding="utf-8", newline="") as f:
                f.write(svg.replace("#2a78d6", "#000000", 1))  # plant an edited chart
            self.assertEqual(E.main(["--root", root]), 1)  # RED: the chart no longer matches the summary
            os.remove(svg_path)
            self.assertEqual(E.main(["--root", root]), 1)  # RED: the chart is missing
            self.assertEqual(E.main(["--root", root, "--write"]), 0)
            self.assertEqual(E.read_text(svg_path), svg)  # GREEN: the same files give the same bytes
            os.remove(ewp)
            self.assertEqual(E.main(["--root", root]), 1)  # RED: the member results are missing
        finally:
            shutil.rmtree(root)


SHA = "0" * 64
ON_TIME = "sha256=%s file=picks/2026-Q4.csv formation=2026-10-01 names=4 model=3.9.17 methodology=1.0\n" % SHA
LATE = "sha256=%s file=picks/2026-Q4.csv formation=2026-10-07 names=4 model=3.9.17 methodology=1.0 sealed=late entry_date=2026-10-08\n" % SHA


def late_prices(entry="2026-10-08"):
    return [price("NYSE:AAA", "US0000000001", "100", "110", entry_date=entry),
            price("NASDAQ:BBB", "US0000000002", "50", "45", entry_date=entry),
            price("NYSE:CCC", "US0000000003", "20", "25", entry_date=entry),
            price("NYSE:DDD", "US0000000004", "10", "12", entry_date=entry)] + member_prices(entry)


class SealedLate(unittest.TestCase):
    """A portfolio sealed late by a human (its formation-day seal was missed) enters on its sealed entry day."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        write(self.root, "picks/2026-Q4.csv", "ticker,isin\n" + "".join("%s,%s\n" % (p["ticker"], p["isin"]) for p in PICKS))
        write(self.root, "README.md", "x\n%s\n%s\n" % (E.START, E.END))
        write(self.root, "benchmarks/2026-Q4.sp500.csv", members_text())

    def tearDown(self):
        shutil.rmtree(self.root)

    def seal(self, text):
        write(self.root, "seals/2026-Q4.seal", text)

    def close(self, rows):
        p = write(self.root, "prices.csv", E.to_csv(rows, E.PRICE_COLUMNS))
        return E.main(["--root", self.root, "--close", "2026-Q4", "--prices", p, "--revealed", "2027-01-01"])

    def readme(self):
        return E.read_text(os.path.join(self.root, "README.md"))

    def test_green_the_late_entry_is_read_from_the_seal(self):
        self.seal(LATE)
        self.assertEqual(E.late_entries(self.root), {"2026-Q4": "2026-10-08"})
        self.seal(ON_TIME)
        self.assertEqual(E.late_entries(self.root), {})

    def test_green_an_open_late_portfolio_is_marked_sealed_late(self):
        self.seal(LATE)
        self.assertEqual(E.main(["--root", self.root, "--write"]), 0)
        self.assertIn("| 2026-Q4 | 2026-10-07, sealed late (entry 2026-10-08) | [`00000000`](seals/2026-Q4.seal) | due 2027-01-01 | - | - | - | - |", self.readme())  # an open quarter shows no figures

    def test_green_a_closed_late_portfolio_enters_on_its_day_and_is_marked(self):
        self.seal(LATE)
        self.assertEqual(self.close(late_prices()), 0)
        self.assertEqual(E.main(["--root", self.root]), 0)  # the check agrees
        self.assertIn("| [2026-Q4](results/2026-Q4.csv) | 2026-10-07, sealed late (entry 2026-10-08) |", self.readme())
        s = E.read_csv(os.path.join(self.root, "results", "summary.csv"))[0]
        self.assertEqual((s["chosen"], s["entry_date"]), ("2026-10-07", "2026-10-08"))

    def test_green_an_on_time_portfolio_is_not_marked(self):
        self.seal(ON_TIME)
        self.assertEqual(self.close(late_prices("2026-10-01")), 0)
        self.assertNotIn("sealed late", self.readme())

    def test_red_a_late_portfolio_whose_results_enter_on_another_day(self):
        self.seal(LATE)
        self.assertEqual(self.close(late_prices("2026-10-01")), 1)  # the quarter's first open, not the sealed entry
        self.assertFalse(os.path.exists(os.path.join(self.root, "results", "summary.csv")))

    def test_red_a_malformed_late_seal(self):
        self.seal(ON_TIME.strip() + " entry_date=2026-10-08\n")  # no sealed=late
        self.assertEqual(E.main(["--root", self.root, "--write"]), 1)

    def test_green_the_chain_allows_a_late_entry_in_its_own_quarter(self):
        rows = E.chain([summary_row("2026-Q4", "2026-10-01", "2026-12-31", "0.1", "0"),
                        summary_row("2027-Q1", "2027-02-16", "2027-03-31", "0.1", "0")], {"2027-Q1": "2027-02-16"})
        self.assertEqual(rows[1]["cumulative_growth_of_1"], "1.210000")

    def test_red_the_same_late_entry_without_a_late_seal_is_a_gap(self):
        with self.assertRaisesRegex(E.EvaluationError, "gap or an overlap"):
            E.chain([summary_row("2026-Q4", "2026-10-01", "2026-12-31", "0.1", "0"),
                     summary_row("2027-Q1", "2027-02-16", "2027-03-31", "0.1", "0")])

    def test_red_a_late_entry_outside_its_quarter(self):
        with self.assertRaisesRegex(E.EvaluationError, "gap or an overlap"):
            E.chain([summary_row("2026-Q4", "2026-10-01", "2026-12-31", "0.1", "0"),
                     summary_row("2027-Q1", "2027-04-01", "2027-06-30", "0.1", "0")], {"2027-Q1": "2027-04-01"})


def chain_of(values):
    """Summary rows with given (record, benchmark) growth values, one per quarter from 2026-Q1."""
    return [{"portfolio": "2026-Q%d" % (i + 1), "cumulative_growth_of_1": E.r6(g), "cumulative_sp500ew": E.r6(b)}
            for i, (g, b) in enumerate(values)]


class EquityCurve(unittest.TestCase):
    def test_green_one_point_per_quarter_from_one_dollar(self):
        svg = E.equity_svg(chain_of([(0.965283, 1.002791), (1.128302, 1.112480), (1.105335, 1.092729)]))
        self.assertEqual(svg.count("<polyline"), 2)  # the record and the benchmark
        self.assertEqual(svg.count("<circle"), 8)  # 1.00 plus three quarters, for each line
        for text in ("Start", "2026-Q1", "2026-Q3", "Growth of $1", "End of quarter", "MonkScore 90+ record",
                     "S&amp;P 500 equal weight", "$1.11", "$1.09"):
            self.assertIn(text, svg)
        first = [p.split(",") for p in svg.split('<polyline points="')[2].split('"')[0].split()]
        self.assertTrue(float(first[1][1]) > float(first[0][1]))  # the down quarter (Q1) goes down the page

    def test_green_deterministic_and_self_contained(self):
        rows = chain_of([(1.1, 1.02), (1.045, 1.0302)])
        self.assertEqual(E.equity_svg(rows), E.equity_svg(rows))
        svg = E.equity_svg(rows)
        for banned in ("<script", "http://fonts", "https://", "@import", "href="):
            self.assertNotIn(banned, svg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
