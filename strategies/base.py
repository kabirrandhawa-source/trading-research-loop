"""The one shape every strategy follows, so the backtester and paper trader can run any of them.

Files are named <name>_v<N>.py. Any change to the rules means a new file with a new
VERSION, and each new version backtested counts as one more variation in the ledger.
"""


class Strategy:
    NAME = "base"
    VERSION = "0"
    HYPOTHESIS = ""          # one line, copied from the research memo
    HYPOTHESIS_ID = None     # id in memory/ledger.db

    # Risk limits (percent). The engine applies these on every bar.
    stop_loss_pct = 5.0      # cut the loss
    take_profit_pct = None   # take profit (None = rely on exit())
    max_position_pct = 10.0  # position sizing cap, % of equity

    warmup = 0               # bars of history needed before entry() is called

    def fit(self, train_bars):
        """Optional: choose parameters on a training window (walk-forward). Default: nothing."""

    def entry(self, bars):
        """Entry rule. bars holds history up to and including the current bar only.
        Return 1 to go long, -1 to go short, 0 to do nothing."""
        raise NotImplementedError

    def exit(self, bars, position):
        """Exit rule beyond stop/target. position: {"side", "entry_price", "bars_held"}.
        Return True to close."""
        return False

    def size(self, equity, price):
        """Position sizing: number of shares."""
        return int(equity * self.max_position_pct / 100 // price)
