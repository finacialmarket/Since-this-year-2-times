CONFIG = {
    "trade_size": 0.01,        # Lot size
    "stop_loss_pips": 20,      # Stop loss in pips
    "timeframe": "15",         # Candle timeframe in minutes
    "symbols": {
        "EURUSD": {"trend_ema": 150, "entry_ema": 20},
        "GBPUSD": {"trend_ema": 150, "entry_ema": 20},
        # Add more symbols as needed
    }
}
