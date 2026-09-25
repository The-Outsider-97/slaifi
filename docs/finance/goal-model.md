# Goal Model

SLAIFI separates **targets**, **constraints**, and **preferences**.

Targets describe desired outcomes, such as a 10% annual return or $150 weekly income. They are not predictions or guarantees.

Constraints are hard limits supplied by the user, such as maximum drawdown, position weight, sector exposure, leverage, short exposure, or allowed/prohibited asset classes.

Preferences are soft inputs such as DCA amount, cash reserve, dividend preference, or preferred asset classes.

## Income feasibility arithmetic

`annual_income_target = periodic_target * periods_per_year`

Current explicit conversion factors are 52 weekly, 12 monthly, 4 quarterly, and 1 annual.

When capital is positive:

`required_yield = annual_income_target / available_capital`

When an assumed yield is supplied:

`required_capital = annual_income_target / assumed_yield`

`expected_income = available_capital * assumed_yield`

The result is labelled `FEASIBLE_UNDER_ASSUMPTIONS`, `NOT_FEASIBLE_UNDER_ASSUMPTIONS`, or `UNDETERMINED`. These labels assess arithmetic compatibility with the supplied assumption, not probability of investment success.
