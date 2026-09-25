"""Deterministic goal arithmetic; targets remain targets, not forecasts."""
from decimal import Decimal
from math import isfinite
from slaifi.core.exceptions import ValidationError
from slaifi.domain.goals import FeasibilityStatus,IncomeGoalEvaluation,IncomePeriod,IncomeTarget,ReturnGoalEvaluation,ReturnTarget
_PERIODS_PER_YEAR={IncomePeriod.WEEKLY:Decimal("52"),IncomePeriod.MONTHLY:Decimal("12"),IncomePeriod.QUARTERLY:Decimal("4"),IncomePeriod.ANNUAL:Decimal("1")}

def annualize_income_target(target:IncomeTarget)->Decimal: return target.amount*_PERIODS_PER_YEAR[target.period]

def evaluate_income_goal(target:IncomeTarget,*,available_capital:Decimal,assumed_annual_yield_rate:float|None=None,current_expected_annual_income:Decimal|None=None)->IncomeGoalEvaluation:
    if available_capital<0: raise ValidationError("available_capital cannot be negative")
    if current_expected_annual_income is not None and current_expected_annual_income<0: raise ValidationError("current_expected_annual_income cannot be negative")
    if assumed_annual_yield_rate is not None and (not isfinite(assumed_annual_yield_rate) or assumed_annual_yield_rate<0): raise ValidationError("assumed_annual_yield_rate must be finite and non-negative")
    annual=annualize_income_target(target); required=float(annual/available_capital) if available_capital>0 else None; required_capital=None
    if assumed_annual_yield_rate is not None and assumed_annual_yield_rate>0: required_capital=annual/Decimal(str(assumed_annual_yield_rate))
    expected=current_expected_annual_income
    if expected is None and assumed_annual_yield_rate is not None: expected=available_capital*Decimal(str(assumed_annual_yield_rate))
    if expected is None: shortfall=None; status=FeasibilityStatus.UNDETERMINED
    else:
        shortfall=max(annual-expected,Decimal("0")); status=FeasibilityStatus.FEASIBLE_UNDER_ASSUMPTIONS if expected>=annual else FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
    return IncomeGoalEvaluation(annual,available_capital,required,assumed_annual_yield_rate,required_capital,expected,shortfall,status)

def evaluate_return_goal(target:ReturnTarget,*,assumed_annual_return_rate:float|None=None)->ReturnGoalEvaluation:
    if assumed_annual_return_rate is None: return ReturnGoalEvaluation(target.annual_rate,None,None,FeasibilityStatus.UNDETERMINED)
    if not isfinite(assumed_annual_return_rate) or assumed_annual_return_rate<=-1: raise ValidationError("assumed_annual_return_rate must be finite and greater than -1")
    gap=assumed_annual_return_rate-target.annual_rate; status=FeasibilityStatus.FEASIBLE_UNDER_ASSUMPTIONS if gap>=0 else FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
    return ReturnGoalEvaluation(target.annual_rate,assumed_annual_return_rate,gap,status)
