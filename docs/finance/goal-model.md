# Goal Model — Design Contract

A financial goal converts user intent into measurable targets and constraints. It does not promise the target can be achieved.

Examples include target annual return, target periodic income, investment horizon, contribution/DCA amount, maximum drawdown, volatility tolerance, cash reserve, position/sector limits, permitted asset classes, leverage/short limits, and trading frequency.

The Goal Engine must be able to report infeasibility. For example, if desired portfolio income is incompatible with available capital and accepted risk, the system should quantify the gap rather than inventing a strategy that appears to satisfy the target.
