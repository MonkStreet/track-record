# Methodology

Version 1.0. In force from 1 October 2026.
These rules govern every portfolio in this repository. They change only under section 9.
All times are New York time (America/New_York).

## 1. Selection

A company is in the portfolio if it meets all four conditions when we choose:

| Condition | Rule |
|---|---|
| Listing | NYSE or Nasdaq |
| Size | Market cap of $300M or more |
| Score | MonkScore of 90 or more |
| Trading | An adjusted close on at least one of the last 5 US trading days before the formation day |

MonkScore ranks each company against a peer group: companies in the same industry and region.
So the portfolio holds about the top 10% of US companies.

The input is the live score data on [app.monk.st](https://app.monk.st) when we choose.
There is no ranking, no limit on the number of names and no tie-break. The number of names changes from quarter to quarter.

## 2. Seal and reveal

We choose a portfolio on each formation day: 1 January, 1 April, 1 July and 1 October, after that day's scores publish.
We publish the seal before the 9:30 open of the first US trading day of the quarter.

| When | We publish |
|---|---|
| Formation day (seal) | `seals/YYYY-QN.seal`: one line with the SHA-256 fingerprint of `picks/YYYY-QN.csv`, the formation date, the number of names, and the model and methodology versions |
| | `seals/YYYY-QN.seal.ots`: an OpenTimestamps proof that the seal existed that day |
| | A GitHub release with the tag `YYYY-QN`. It attaches the `.seal` file and its `.ots` proof. |
| Next formation day (reveal) | `picks/YYYY-QN.csv`, byte for byte the sealed file. The release is marked as revealed. |

The pick file stays private until the reveal. Before we publish it, we check it against its seal.

We seal only if the portfolio has 150 to 600 names. Outside this band, we stop and find the cause.

If publication fails, we fix the cause and then seal with the scores of that time.
We never skip a quarter. Entry (section 3) uses the actual release time.

### Pick file

The pick file has one row for each company, sorted by `ticker`.
The file holds scores and identifiers only: no prices, no market caps and no other financial values.

| Column | Contents |
|---|---|
| `ticker` | `EXCHANGE:SYMBOL` when we choose |
| `isin` | Durable identifier. Tickers get reused; ISINs do not. |
| `company_name` | Name when we choose |
| `sector` | Sector |
| `industry` | Industry |
| `monkscore` | MonkScore when we choose (90-100) |
| `model_version` | Model version in force (section 8) |
| `methodology_version` | Version of this document |
| `status` | `live`: chosen before entry |

## 3. Entry, holding period, exit

| Step | Rule |
|---|---|
| Entry | The official 9:30 open of the first US trading day of the quarter. This is the first open after the seal. |
| Hold | We add nothing, sell nothing early and do not rebalance. |
| Exit | The official 16:00 close of the last US trading day of the quarter. |

Only one portfolio is open at a time. The next portfolio enters at the next open, so the windows do not overlap.
The return from that last close to the next open is not in the record.

Example: a seal on Thursday 1 October 2026 enters at the 9:30 open of Thursday 1 October 2026.
It exits at the 16:00 close of Thursday 31 December 2026, the last trading day of the quarter.
1 January 2027 is a holiday. So the next portfolio enters at the 9:30 open of Monday 4 January 2027.

## 4. Returns

All prices are opens and closes in USD from a commercial market-data vendor, adjusted for splits and dividends. We do not deduct transaction costs.
We do not model spread or market impact.

| Figure | Rule |
|---|---|
| Name return | Exit close / entry open - 1 |
| Portfolio return | The mean of the name returns (equal weight at entry) |
| Excess | Portfolio return - benchmark return |
| Growth of $1 | The quarterly returns, compounded one quarter after the other. The same for the benchmark. |

| Event during the hold | Treatment | `status` |
|---|---|---|
| None | Entry open to exit close | `held` |
| Split or cash dividend | Included in the adjusted prices | `held` |
| Other event, and the name still trades (for example a spin-off) | The vendor's adjusted series as it is | `held` |
| No price at the exit (merger, going private, delisting, a halt, or a gap in the vendor data) | Last available adjusted close, then cash at 0% until exit | `trading ceased` |
| No open on the entry day (a halt or a gap in the vendor data) | Cash at 0% until the first available adjusted open in the window, then held from that open | `late entry` |
| Confirmed bankruptcy, or delisting with no payout | Value of zero. The reason is in the results file. | `zero: <reason>` |
| Ticker change | Tracked through the ISIN. The pick file does not change. | `held` |

A gap in the vendor data is never valued at zero.

## 5. Benchmark

The benchmark is the S&P 500 equal-weighted index, over the same window.
We measure it through RSP, an ETF that tracks it. RSP gets the same price rules as a pick.

Why equal weight: the portfolio gives each company the same weight, and so does the benchmark.
An index weighted by company size lets a few very large companies drive it.
Against such an index, a gap mixes two effects: picking skill and company size. Against an equal-weight index, the gap shows mostly picking skill.
Some size difference remains: the portfolio goes down to $300M, and the benchmark holds only S&P 500 companies.

## 6. Results

| File | When | Contents |
|---|---|---|
| `results/interim.csv` | Each month, replaced | The open portfolio, marked to market and labelled `INTERIM`. These figures are not final. |
| `results/YYYY-QN.csv` | At close | One row for each pick, then the benchmark (RSP): `ticker`, `isin`, `entry_date`, `entry_open`, `exit_date`, `exit_close`, `total_return`, `status` |
| `results/summary.csv` | At close, one new row | `portfolio`, `chosen`, `revealed`, `entry_date`, `exit_date`, `names`, `return`, `rsp_return`, `excess_vs_rsp`, `cumulative_growth_of_1`, `cumulative_rsp` |
| `results/equity.svg` | At close, replaced | Growth of $1 for the record and the benchmark, one point for each closed quarter |

At each reveal, we also publish a short note on the portfolio: `notes/YYYY-QN.md`.

`scripts/evaluate.py` makes every number in these files and in the README, from the committed files only.
A number that it does not make is not official.

We report results. We make no statistical claims.

## 7. Integrity

- These files never change after commit: `picks/`, `seals/*.seal` and `results/YYYY-QN.csv`.
- `results/summary.csv` only gets new rows.
- A `.seal.ots` proof changes once: we complete it when Bitcoin confirms it, a few hours after the seal.
- We correct errors in new commits and log them in [ERRATA.md](ERRATA.md): what was wrong, what changed, and why.
- An error in a closed portfolio gives a new results file. The old file stays.
- We never force-push or rebase.

## 8. Model versions

Each pick file shows the model version in force. [CHANGELOG.md](CHANGELOG.md) lists each model release.
A new model applies only to later portfolios. It never restates a published portfolio.

## 9. Rule changes

A rule change:

- gets a new methodology version, a stated reason and a [CHANGELOG.md](CHANGELOG.md) entry;
- applies only to portfolios chosen after it;
- is announced on X at least one calendar month before the first portfolio that it affects.

If a change alters the measurement, old and new portfolios are reported as separate series.

## 10. Disclaimers

This is a model record. It measures the MonkScore signal under fixed rules.
It is not a fund, not a portfolio recommendation and not a personal trading record.
Some picks will lose, and some will fail. Nothing here is investment advice or a solicitation.
MonkStreet is not a registered investment adviser. Speak to a licensed adviser before you invest.
Past performance does not indicate future results. Full disclaimer: [monk.st/disclaimer](https://www.monk.st/disclaimer).
