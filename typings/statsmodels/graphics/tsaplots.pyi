from pandas import Series
from matplotlib.figure import Figure

def plot_acf(x: Series, *, lags: int) -> Figure: ...