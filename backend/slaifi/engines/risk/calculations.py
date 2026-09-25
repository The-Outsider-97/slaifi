"""Reference statistical risk calculations with explicit annualization inputs."""
import math,statistics
from collections.abc import Mapping,Sequence
from slaifi.core.exceptions import FinancialCalculationError,ValidationError
from slaifi.domain.risk import CorrelationMatrix,RiskStatistics
from slaifi.engines._validation import finite_series,positive_series

def periodic_rate_from_annual(annual_rate:float,periods_per_year:int)->float:
    if periods_per_year<=0: raise ValidationError("periods_per_year must be positive")
    if not math.isfinite(annual_rate) or annual_rate<=-1: raise ValidationError("annual_rate must be finite and greater than -1")
    return (1+annual_rate)**(1/periods_per_year)-1

def historical_volatility(returns:Sequence[float],*,periods_per_year:int)->float:
    data=finite_series(returns,minimum=2,name="returns")
    if periods_per_year<=0: raise ValidationError("periods_per_year must be positive")
    return statistics.stdev(data)*math.sqrt(periods_per_year)

def downside_deviation(returns:Sequence[float],*,periods_per_year:int,target_annual_rate:float=0.0)->float:
    data=finite_series(returns,minimum=1,name="returns"); target=periodic_rate_from_annual(target_annual_rate,periods_per_year)
    return math.sqrt(sum(min(value-target,0.0)**2 for value in data)/len(data))*math.sqrt(periods_per_year)

def maximum_drawdown(values:Sequence[float])->float:
    data=positive_series(values,minimum=1,name="equity values"); peak=data[0]; worst=0.0
    for value in data: peak=max(peak,value); worst=min(worst,value/peak-1.0)
    return worst

def sharpe_ratio(returns:Sequence[float],*,periods_per_year:int,risk_free_annual_rate:float=0.0)->float:
    data=finite_series(returns,minimum=2,name="returns"); rf=periodic_rate_from_annual(risk_free_annual_rate,periods_per_year); vol=statistics.stdev(data)
    if vol==0: raise FinancialCalculationError("Sharpe ratio is undefined for zero volatility")
    return statistics.mean(value-rf for value in data)/vol*math.sqrt(periods_per_year)

def sortino_ratio(returns:Sequence[float],*,periods_per_year:int,target_annual_rate:float=0.0)->float:
    data=finite_series(returns,minimum=1,name="returns"); target=periodic_rate_from_annual(target_annual_rate,periods_per_year); downside=downside_deviation(data,periods_per_year=periods_per_year,target_annual_rate=target_annual_rate)
    if downside==0: raise FinancialCalculationError("Sortino ratio is undefined with zero downside deviation")
    return statistics.mean(value-target for value in data)*periods_per_year/downside

def pearson_correlation(left:Sequence[float],right:Sequence[float])->float:
    if len(left)!=len(right): raise ValidationError("correlation series must have equal length")
    x=finite_series(left,minimum=2,name="left correlation series"); y=finite_series(right,minimum=2,name="right correlation series"); mx=statistics.mean(x); my=statistics.mean(y)
    numerator=sum((a-mx)*(b-my) for a,b in zip(x,y)); denominator=math.sqrt(sum((a-mx)**2 for a in x)*sum((b-my)**2 for b in y))
    if denominator==0: raise FinancialCalculationError("correlation is undefined for a constant series")
    return max(-1.0,min(1.0,numerator/denominator))

def correlation_matrix(series:Mapping[str,Sequence[float]])->CorrelationMatrix:
    labels=tuple(series.keys())
    if not labels: raise ValidationError("correlation matrix requires at least one series")
    if len({len(series[label]) for label in labels})!=1: raise ValidationError("all correlation series must have equal length")
    validated={label:finite_series(series[label],minimum=2,name=label) for label in labels}
    for label,values in validated.items():
        if statistics.pstdev(values)==0: raise FinancialCalculationError(f"correlation is undefined for constant series {label}")
    rows=[]
    for left in labels: rows.append(tuple(1.0 if left==right else pearson_correlation(validated[left],validated[right]) for right in labels))
    return CorrelationMatrix(labels,tuple(rows))

def concentration_hhi(weights:Sequence[float])->float:
    data=finite_series(weights,minimum=1,name="weights")
    if any(weight<0 for weight in data): raise ValidationError("concentration weights cannot be negative")
    total=sum(data)
    if total<=0: raise FinancialCalculationError("concentration is undefined when total weight is zero")
    return sum((weight/total)**2 for weight in data)

def calculate_risk_statistics(returns:Sequence[float],equity_values:Sequence[float],*,periods_per_year:int,risk_free_annual_rate:float=0.0,target_annual_rate:float=0.0,weights:Sequence[float]|None=None)->RiskStatistics:
    data=finite_series(returns,minimum=2,name="returns"); volatility=historical_volatility(data,periods_per_year=periods_per_year); downside=downside_deviation(data,periods_per_year=periods_per_year,target_annual_rate=target_annual_rate)
    try: sharpe=sharpe_ratio(data,periods_per_year=periods_per_year,risk_free_annual_rate=risk_free_annual_rate)
    except FinancialCalculationError: sharpe=None
    try: sortino=sortino_ratio(data,periods_per_year=periods_per_year,target_annual_rate=target_annual_rate)
    except FinancialCalculationError: sortino=None
    return RiskStatistics(len(data),periods_per_year,volatility,downside,maximum_drawdown(equity_values),sharpe,sortino,concentration_hhi(weights) if weights is not None else None)
