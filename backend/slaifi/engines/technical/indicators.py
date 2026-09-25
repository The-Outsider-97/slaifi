"""Limited initial technical-analysis indicator set."""
from dataclasses import dataclass
from collections.abc import Sequence
from slaifi.core.exceptions import InsufficientDataError, ValidationError
from slaifi.domain.market import OHLCVBar
from slaifi.engines._validation import chronological_bars, positive_series
from slaifi.engines.features import rolling_mean
AlignedSeries=tuple[float|None,...]

@dataclass(frozen=True,slots=True)
class MACDResult:
    macd_line: AlignedSeries
    signal_line: AlignedSeries
    histogram: AlignedSeries

def sma(values: Sequence[float], window: int)->AlignedSeries: return rolling_mean(values,window)

def ema(values: Sequence[float], span: int)->AlignedSeries:
    if span<=0: raise ValidationError("span must be positive")
    data=positive_series(values,minimum=span,name="values"); alpha=2.0/(span+1); seed=sum(data[:span])/span
    out:list[float|None]=[None]*(span-1)+[seed]; previous=seed
    for value in data[span:]: previous=alpha*value+(1-alpha)*previous; out.append(previous)
    return tuple(out)

def momentum(prices: Sequence[float], period: int)->AlignedSeries:
    if period<=0: raise ValidationError("period must be positive")
    data=positive_series(prices,minimum=period+1,name="prices")
    return (*([None]*period),*(data[i]/data[i-period]-1.0 for i in range(period,len(data))))

def _rsi_value(gain: float,loss: float)->float:
    if loss==0: return 50.0 if gain==0 else 100.0
    rs=gain/loss; return 100.0-(100.0/(1.0+rs))

def rsi(prices: Sequence[float], period: int=14)->AlignedSeries:
    if period<=0: raise ValidationError("period must be positive")
    data=positive_series(prices,minimum=period+1,name="prices"); changes=[data[i]-data[i-1] for i in range(1,len(data))]
    gains=[max(x,0.0) for x in changes]; losses=[max(-x,0.0) for x in changes]
    avg_gain=sum(gains[:period])/period; avg_loss=sum(losses[:period])/period; out:list[float|None]=[None]*period+[_rsi_value(avg_gain,avg_loss)]
    for gain,loss in zip(gains[period:],losses[period:]):
        avg_gain=((period-1)*avg_gain+gain)/period; avg_loss=((period-1)*avg_loss+loss)/period; out.append(_rsi_value(avg_gain,avg_loss))
    return tuple(out)

def _ema_signed(values: Sequence[float],span: int)->AlignedSeries:
    if len(values)<span: raise InsufficientDataError(f"EMA requires at least {span} observations")
    alpha=2.0/(span+1); seed=sum(values[:span])/span; out:list[float|None]=[None]*(span-1)+[seed]; previous=seed
    for value in values[span:]: previous=alpha*value+(1-alpha)*previous; out.append(previous)
    return tuple(out)

def macd(prices: Sequence[float],*,fast_span:int=12,slow_span:int=26,signal_span:int=9)->MACDResult:
    if not 0<fast_span<slow_span: raise ValidationError("MACD requires 0 < fast_span < slow_span")
    if signal_span<=0: raise ValidationError("signal_span must be positive")
    data=positive_series(prices,minimum=slow_span+signal_span-1,name="prices"); fast=ema(data,fast_span); slow=ema(data,slow_span)
    line:list[float|None]=[]; valid:list[float]=[]; indices:list[int]=[]
    for i,(a,b) in enumerate(zip(fast,slow)):
        if a is None or b is None: line.append(None)
        else: value=a-b; line.append(value); valid.append(value); indices.append(i)
    sig_valid=_ema_signed(valid,signal_span); sig:list[float|None]=[None]*len(data)
    for i,value in zip(indices,sig_valid): sig[i]=value
    hist=tuple(None if a is None or b is None else a-b for a,b in zip(line,sig))
    return MACDResult(tuple(line),tuple(sig),hist)

def atr(bars: Sequence[OHLCVBar],period:int=14)->AlignedSeries:
    if period<=0: raise ValidationError("period must be positive")
    data=chronological_bars(bars,minimum=period); trs=[]; previous=None
    for bar in data:
        high=float(bar.high); low=float(bar.low); close=float(bar.close)
        trs.append(high-low if previous is None else max(high-low,abs(high-previous),abs(low-previous))); previous=close
    seed=sum(trs[:period])/period; out:list[float|None]=[None]*(period-1)+[seed]; previous_atr=seed
    for tr in trs[period:]: previous_atr=((period-1)*previous_atr+tr)/period; out.append(previous_atr)
    return tuple(out)
