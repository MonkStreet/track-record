# MonkScore Track Record

[MonkStreet](https://monk.st) rates stocks with a score from 0 to 100, called MonkScore. This page shows, quarter by quarter, how the highest-rated stocks really did.

## The short version

### What is this?

Every quarter, we take all US stocks with a MonkScore of 90 or more. We treat them as one portfolio. At the end of the quarter, we publish how that portfolio did, next to the S&P 500 equal-weight. The table under "Results" is the track record.

### Where is this quarter's list?

Subscribers see it on [MonkStreet](https://monk.st) from the first morning of the quarter. Everyone else sees it here when the quarter ends, together with its result. Until then, this page shows only its fingerprint.

### Why not publish it now?

Our subscribers pay to see these stocks first. If we posted them here on day one, they would pay for something that is free.

### Then how do I know you did not change the list later?

Before the quarter starts, we publish a fingerprint of the list here. A fingerprint is a short code made from the list. It does not show the stocks. But if we change even one letter of the list later, the code no longer matches. When we publish the list, you can check it against the fingerprint from day one.

### So, do I have to believe you?

No. Each result comes from a list that we lock before the quarter starts. "How you can check us", further down, shows how to check it.

### How do I see the current list?

Subscribe at [monk.st](https://monk.st). Or come back here when the quarter ends.

## Results

Each row is one portfolio. "Return" is the average return of its stocks, from the first open of the quarter to the last close, before costs. "Excess" is that return minus the S&P 500 equal-weight over the same days. The top row is the current quarter: its list is sealed, so it shows only the fingerprint until the quarter ends. Open a quarter to see every stock and its prices, or read its note to see what drove the result.

<!-- results:start -->
| Portfolio | Chosen | Fingerprint | Revealed | Return | S&P 500 equal-weight | Excess | Note |
|---|---|---|---|---|---|---|---|
| 2026-Q4 | 2026-10-01 | [`53415ce3`](seals/2026-Q4.seal) | due 2027-01-01 | - | - | - | - |

Since launch: no portfolio has closed yet.
<!-- results:end -->

[`scripts/evaluate.py`](scripts/evaluate.py) calculates every number above from the files in this repository. You can run it yourself.

## A note from the founder

Hi, I'm Alberto, the founder of MonkStreet.

I don't trust track records, and you shouldn't either. A backtest can always look good, because it is made with hindsight. So this record only shows portfolios that were locked before the market opened. Good quarters and bad ones stay on this page.

You can check the list, the date and the arithmetic without us. Until reveal day, you cannot check that MonkScore was applied as written. Subscribers can, on the morning of the seal. And if MonkScore stops working, this page will show it first.

Alberto Echevarría  
The Investing Monk  
1 October 2026

Conflict of interest: MonkStreet sells access to these lists, and I may hold some of these stocks.

## How each quarter works

| When | What happens |
|---|---|
| First day of the quarter, early morning | We choose the portfolio: every stock that meets the rule that day. Subscribers see it on [MonkStreet](https://monk.st). |
| First day of the quarter, before 9:30 | We publish the fingerprint here. |
| First trading day of the quarter, 9:30 | The portfolio starts at each stock's opening price. |
| Last trading day of the quarter, 16:00 | The portfolio ends at each stock's closing price. |
| First day of the next quarter | We publish the list and the result here. Anyone can check the list against the fingerprint. |

All times are New York time. When the first day of a quarter is a market holiday, such as 1 January, the portfolio starts at the open of the next trading day.

The rule: every NYSE and Nasdaq stock with a MonkScore of 90 or more and a market value of $300M or more. The full rules are in [METHODOLOGY.md](METHODOLOGY.md).

## How you can check us

Below is each way a track record can be faked, why it does not work here, and how to check it.

| A dishonest record could... | This record cannot, because... | Check it |
|---|---|---|
| Choose the winners after the quarter | The fingerprint of the list is public before the quarter starts. At the end, the list must match it exactly. | [Check the list](#check-the-list) |
| Say a fingerprint is older than it is | An OpenTimestamps proof records the fingerprint in the Bitcoin blockchain. The GitHub release of the quarter attaches the seal and the proof. | [Check the date](#check-the-date) |
| Remove a bad quarter | We only add results. Copies outside our control can keep the old files. | [Check for deletions](#check-for-deletions) |
| Change the rules after a bad quarter | Methodology 1.0 sets the rules. A change applies only to later portfolios, and we announce it one month before. | [METHODOLOGY.md](METHODOLOGY.md) section 9 and [CHANGELOG.md](CHANGELOG.md) |
| Leave out companies that collapsed | Each company stays in its portfolio until the end of the quarter. | [Corporate actions](#corporate-actions) |
| Use a price that nobody could get | Each portfolio starts at the 9:30 open after the fingerprint is public. | [Check the prices and the numbers](#check-the-prices-and-the-numbers) |
| Use an easy benchmark | The S&P 500 equal-weight gives each company the same weight, as our portfolio does. | [METHODOLOGY.md](METHODOLOGY.md) section 5 |
| Choose companies by hand | The list has every company that meets the rule on that day. | On the first day of the quarter, subscribers can make the same list on [app.monk.st](https://app.monk.st) |
| Make up the numbers | All numbers come from the files in this repository and one public script. | [Check the prices and the numbers](#check-the-prices-and-the-numbers) |

### Check the list

The fingerprint is the SHA-256 hash of the pick file. SHA-256 is a standard method. Nobody can work out the stocks from the hash.

Hash the raw file from this repository. Download the raw file from GitHub, or use a clone. Never hash a copy that a spreadsheet saved again. Changed line endings and re-sorted rows are the usual ways an honest file fails the check.

Run one of these commands. Replace `2026-Q4` with the quarter you check.

| System | Command |
|---|---|
| Linux | `sha256sum picks/2026-Q4.csv` |
| macOS | `shasum -a 256 picks/2026-Q4.csv` |
| Windows (PowerShell) | `Get-FileHash -Algorithm SHA256 picks\2026-Q4.csv` |
| Windows (Command Prompt) | `certutil -hashfile picks\2026-Q4.csv SHA256` |

The result must equal the `sha256=` value in `seals/2026-Q4.seal`. PowerShell prints the hash in capital letters. The letters are the same.

### Check the date

The date proof is the OpenTimestamps proof, `seals/<quarter>.seal.ots`. It records the seal in the Bitcoin blockchain. Nobody can change that record, and that includes us.

Each quarter also has a GitHub release with the tag `<quarter>`, on the Releases page. The release attaches `<quarter>.seal` and `<quarter>.seal.ots`. GitHub sets the release time. We cannot set it to an earlier time.

To check a proof:

1. Install the free client: `pip install opentimestamps-client`.
2. Put the `.seal` file and its `.seal.ots` file in the same folder.
3. Run `ots verify seals/2026-Q4.seal.ots`. This needs a Bitcoin node. Without one, run `ots --no-bitcoin verify seals/2026-Q4.seal.ots`. It names a Bitcoin block that you can look up in any block explorer.

Or drag the `.ots` file and the `.seal` file onto [opentimestamps.org](https://opentimestamps.org).

A new proof is complete a few hours after the seal, when Bitcoin confirms it.

Git commit times are not a date proof. Anyone can set the time of a commit, and the owner of a repository can rewrite its history. Use the proof and the release.

### Check for deletions

Run this command in a clone:

```
git log --diff-filter=D --oneline -- picks/ seals/ results/
```

It must show nothing. Public archives, such as [Software Heritage](https://www.softwareheritage.org), also copy public repositories. A deletion shows if someone already cloned or archived the repository.

### Check the prices and the numbers

`results/<quarter>.csv` holds the entry open and the exit close of each name, in the columns `entry_open` and `exit_close`. The columns `entry_date` and `exit_date` give the day of each price. The prices come from a commercial market-data vendor and are dividend-adjusted. Every price is public. You can check any name against any free price source.

[`scripts/evaluate.py`](scripts/evaluate.py) uses only the files in this repository. It never calls a price vendor. Run it in a clone:

```
python scripts/evaluate.py
```

It calculates every return, the table, the since-launch line and the chart again, and compares them with the committed files. It prints `OK`, or the name of each file that differs.

### Corporate actions

Inspect the `status` column in `results/<quarter>.csv`.

| Event | What we do | `status` |
|---|---|---|
| Dividend | We reinvest it: the prices are dividend-adjusted. | `held` |
| Cash takeover | The last close before the delisting, then cash at 0% to the end of the quarter. | `trading ceased` |
| Halt to the end of the quarter | The last close before the halt, then cash at 0%. | `trading ceased` |
| No open on the first day | Cash at 0% until the first open, then the stock from that open. | `late entry` |
| Confirmed bankruptcy, or delisting with no payout | A value of zero. Only these events give a zero. | `zero: <reason>` |

The full rules are in [METHODOLOGY.md](METHODOLOGY.md) section 4.

## What this record cannot tell you

- A few quarters prove little. The result of one quarter is mostly chance. Look at the trend over years.
- Real returns are lower. We do not deduct trading costs or taxes. Also, it is difficult to buy about 350 companies in equal amounts.
- It is not advice. It shows how one rating did in the past. It does not tell you what to buy.

## Found a problem?

Write to [methodology@monk.st](mailto:methodology@monk.st). We correct errors in public. We record each correction in [ERRATA.md](ERRATA.md), and the old version stays in the history.

---

Not investment advice. Read the [disclaimers](METHODOLOGY.md#10-disclaimers).
