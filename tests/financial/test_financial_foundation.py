from datetime import UTC,datetime,timedelta
from decimal import Decimal
import math,statistics
import pytest
from slaifi.core.exceptions import FinancialCalculationError,InsufficientDataError,ValidationError
from slaifi.core.types import CurrencyCode,percent_to_rate,rate_to_percent
from slaifi.domain.assets import AssetClass,AssetId
from slaifi.domain.goals import FeasibilityStatus,IncomePeriod,IncomeTarget,ReturnTarget,RiskConstraints
from slaifi.domain.market import MarketSnapshot,OHLCVBar,PriceQuote
from slaifi.domain.portfolio import CashFlow,CashFlowKind,Portfolio,Trade,TradeSide
from slaifi.engines.features import drawdown_series,rolling_mean,rolling_returns,rolling_volatility,simple_returns,volume_changes
from slaifi.engines.goals import annualize_income_target,evaluate_income_goal,evaluate_return_goal
from slaifi.engines.portfolio import build_positions,cash_balance,portfolio_weights,value_portfolio
from slaifi.engines.risk import concentration_hhi,correlation_matrix,downside_deviation,historical_volatility,maximum_drawdown,pearson_correlation,sharpe_ratio,sortino_ratio
from slaifi.engines.technical import atr,ema,momentum,rsi,sma

USD=CurrencyCode("USD"); ASSET=AssetId("ABC",AssetClass.EQUITY,"NYSE",USD)

def _trade(identifier:str,side:TradeSide,quantity:str,price:str,fee:str="0")->Trade:
    return Trade(identifier,ASSET,side,Decimal(quantity),Decimal(price),Decimal(fee),datetime(2026,1,int(identifier[-1]),tzinfo=UTC),USD)

def _bar(day:int,high:str,low:str,close:str)->OHLCVBar:
    start=datetime(2026,1,day,tzinfo=UTC); return OHLCVBar(ASSET,start,start+timedelta(days=1),Decimal(close),Decimal(high),Decimal(low),Decimal(close),Decimal("100"))

def test_rate_convention_and_asset_identity()->None:
    assert percent_to_rate(10)==pytest.approx(.10); assert rate_to_percent(.10)==pytest.approx(10)
    assert AssetId("abc",exchange="NYSE") != AssetId("abc",exchange="NASDAQ")

def test_market_invariants()->None:
    with pytest.raises(ValidationError): PriceQuote(ASSET,Decimal("0"),USD,datetime.now(UTC),"test")
    with pytest.raises(ValidationError): PriceQuote(ASSET,Decimal("1"),USD,datetime(2026,1,1),"test")
    with pytest.raises(ValidationError): OHLCVBar(ASSET,datetime(2026,1,1,tzinfo=UTC),datetime(2026,1,2,tzinfo=UTC),Decimal("10"),Decimal("10"),Decimal("9"),Decimal("11"),Decimal("1"))
    quote=PriceQuote(ASSET,Decimal("10"),USD,datetime(2026,1,2,tzinfo=UTC),"test")
    with pytest.raises(ValidationError): MarketSnapshot(datetime(2026,1,2,tzinfo=UTC),(quote,quote))

def test_goal_constraints_do_not_conflict()->None:
    with pytest.raises(ValidationError): RiskConstraints(allowed_asset_classes=frozenset({AssetClass.EQUITY}),prohibited_asset_classes=frozenset({AssetClass.EQUITY}))

def test_feature_reference_cases()->None:
    assert simple_returns([100,110,99]) == (None,pytest.approx(.1),pytest.approx(-.1))
    assert rolling_returns([100,110,121],2) == (None,None,pytest.approx(.21))
    assert rolling_mean([1,2,3,4],3) == (None,None,2,3)
    expected=statistics.stdev([.1,-.1,.1])*math.sqrt(4)
    assert rolling_volatility([100,110,99,108.9],3,periods_per_year=4)[-1] == pytest.approx(expected)
    assert drawdown_series([100,120,90,96]) == pytest.approx((0,0,-.25,-.2))
    assert volume_changes([0,10,20]) == (None,None,1)

def test_feature_edges()->None:
    with pytest.raises(ValidationError): simple_returns([100,float("nan")])
    with pytest.raises(InsufficientDataError): rolling_returns([100,101],2)

def test_technical_reference_cases()->None:
    assert sma([1,2,3,4],3)==(None,None,2,3); assert ema([1,2,3,4],3)==(None,None,2,3)
    assert momentum([100,110,121],2)==(None,None,pytest.approx(.21)); assert rsi([1,2,3,4],3)[-1]==pytest.approx(100); assert rsi([2,2,2,2],3)[-1]==pytest.approx(50)
    assert atr([_bar(1,"11","9","10"),_bar(2,"13","10","12"),_bar(3,"14","11","13")],2)==(None,pytest.approx(2.5),pytest.approx(2.75))
    with pytest.raises(ValidationError): atr([_bar(2,"13","10","12"),_bar(1,"11","9","10")],2)

def test_portfolio_reference_accounting()->None:
    positions=build_positions([_trade("T1",TradeSide.BUY,"10","10","1"),_trade("T2",TradeSide.BUY,"10","20","1"),_trade("T3",TradeSide.SELL,"5","30","1")]); position=positions[0]
    assert position.quantity==Decimal("15"); assert position.average_cost==Decimal("15.10"); assert position.realized_pnl==Decimal("73.50")
    with pytest.raises(FinancialCalculationError): build_positions([_trade("T1",TradeSide.BUY,"1","10"),_trade("T2",TradeSide.SELL,"2","10")])

def test_portfolio_cash_weights_and_value()->None:
    other=AssetId("XYZ",AssetClass.EQUITY,"NYSE",USD); other_trade=Trade("T2",other,TradeSide.BUY,Decimal("1"),Decimal("20"),Decimal("0"),datetime(2026,1,2,tzinfo=UTC),USD)
    portfolio=Portfolio("P1","Reference",USD,(_trade("T1",TradeSide.BUY,"2","10"),other_trade),(CashFlow("F1",CashFlowKind.CONTRIBUTION,Decimal("100"),datetime(2026,1,1,tzinfo=UTC),USD),))
    assert cash_balance(portfolio)==Decimal("60"); positions=build_positions(portfolio.trades); prices={ASSET:Decimal("15"),other:Decimal("30")}; weights=portfolio_weights(positions,prices); assert weights[ASSET]==pytest.approx(.5)
    snapshot=value_portfolio(portfolio,prices,as_of=datetime(2026,1,3,tzinfo=UTC)); assert snapshot.total_value==Decimal("120")

def test_risk_reference_cases()->None:
    returns=[.10,-.05,.02,-.01]
    assert historical_volatility(returns,periods_per_year=12)==pytest.approx(statistics.stdev(returns)*math.sqrt(12))
    expected_down=math.sqrt((.05**2+.01**2)/4)*math.sqrt(12); assert downside_deviation(returns,periods_per_year=12)==pytest.approx(expected_down)
    assert maximum_drawdown([100,120,90,96])==pytest.approx(-.25)
    assert sharpe_ratio(returns,periods_per_year=12)==pytest.approx(statistics.mean(returns)/statistics.stdev(returns)*math.sqrt(12))
    assert sortino_ratio(returns,periods_per_year=12)==pytest.approx(statistics.mean(returns)*12/expected_down)
    assert pearson_correlation([1,2,3],[2,4,6])==pytest.approx(1); assert correlation_matrix({"A":[1,2,3],"B":[3,2,1]}).values[0][1]==pytest.approx(-1); assert concentration_hhi([.5,.5])==pytest.approx(.5)

def test_risk_undefined_cases_raise()->None:
    with pytest.raises(FinancialCalculationError): sharpe_ratio([.01,.01,.01],periods_per_year=12)
    with pytest.raises(FinancialCalculationError): pearson_correlation([1,1,1],[1,2,3])

def test_goal_feasibility_reference()->None:
    target=IncomeTarget(Decimal("150"),IncomePeriod.WEEKLY); assert annualize_income_target(target)==Decimal("7800")
    result=evaluate_income_goal(target,available_capital=Decimal("50000"),assumed_annual_yield_rate=.05); assert result.required_yield_rate==pytest.approx(.156); assert result.required_capital_at_assumed_yield==Decimal("156000"); assert result.annual_income_shortfall==Decimal("5300.00"); assert result.status is FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
    return_result=evaluate_return_goal(ReturnTarget(.10),assumed_annual_return_rate=.08); assert return_result.annual_rate_gap==pytest.approx(-.02)
