from collections.abc import Sequence


def relative_return(
    stock_closes: Sequence[float], index_closes: Sequence[float], lookback: int = 20
) -> float | None:
    if lookback < 1 or len(stock_closes) <= lookback or len(index_closes) <= lookback:
        return None
    stock_start = float(stock_closes[-lookback - 1])
    index_start = float(index_closes[-lookback - 1])
    if stock_start <= 0 or index_start <= 0:
        return None
    stock_return = float(stock_closes[-1]) / stock_start - 1.0
    index_return = float(index_closes[-1]) / index_start - 1.0
    return stock_return - index_return
