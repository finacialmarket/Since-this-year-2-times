import time
import os
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
import requests
import traceback
from config import CONFIG

# Load secrets from .env
load_dotenv()
MT5_LOGIN = int(os.getenv("MT5_LOGIN"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Connect to MT5
if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    print(f"MT5 Initialization failed: {mt5.last_error()}")
    quit()
print("Connected to MT5 successfully!")

# Telegram helper
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print(f"Telegram error: {e}")

# Track open trades and stop-loss hits
open_trades = {}
stop_loss_hit = {}

# Fetch candles
def get_candles(symbol, timeframe, n=100):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, n*int(timeframe))
    df = pd.DataFrame(rates)
    df['close'] = df['close'].astype(float)
    return df

# EMA calculation
def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# Check trade signal
def check_signal(symbol, trend_period, entry_period):
    df = get_candles(symbol, CONFIG["timeframe"], n=200)
    df['trend_ema'] = calculate_ema(df['close'], trend_period)
    df['entry_ema'] = calculate_ema(df['close'], entry_period)

    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]

    # Determine trend
    if last_candle['close'] > last_candle['trend_ema']:
        trend = "long"
    elif last_candle['close'] < last_candle['trend_ema']:
        trend = "short"
    else:
        trend = None

    # Entry/Exit logic
    signal = None
    if trend == "long":
        if prev_candle['close'] <= prev_candle['entry_ema'] and last_candle['close'] > last_candle['entry_ema']:
            signal = "BUY"
    elif trend == "short":
        if prev_candle['close'] >= prev_candle['entry_ema'] and last_candle['close'] < last_candle['entry_ema']:
            signal = "SELL"

    return signal, trend

# Place order
def place_order(symbol, side):
    lot = CONFIG["trade_size"]
    price = mt5.symbol_info_tick(symbol).ask if side=="BUY" else mt5.symbol_info_tick(symbol).bid
    deviation = 10

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": deviation,
        "magic": 123456,
        "comment": "MarketWatchBot",
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        send_telegram(f"❌ Order failed: {symbol} {side} → {result.retcode}")
    else:
        open_trades[symbol] = side
        stop_loss_hit[symbol] = False
        send_telegram(f"✅ Order placed: {symbol} {side}")

# Check stop-loss
def check_stop_loss(symbol, side):
    tick = mt5.symbol_info_tick(symbol)
    entry_price = tick.ask if side=="BUY" else tick.bid
    sl_price = entry_price - CONFIG["stop_loss_pips"]*0.0001 if side=="BUY" else entry_price + CONFIG["stop_loss_pips"]*0.0001
    if side=="BUY" and tick.bid <= sl_price:
        return True
    elif side=="SELL" and tick.ask >= sl_price:
        return True
    return False

# Main loop
def main():
    send_telegram("🤖 Market Watch Bot Started!")
    while True:
        try:
            for symbol, emaperiods in CONFIG["symbols"].items():
                signal, trend = check_signal(symbol, emaperiods["trend_ema"], emaperiods["entry_ema"])

                # Stop-loss re-entry
                if stop_loss_hit.get(symbol):
                    if trend=="long" and signal=="BUY":
                        place_order(symbol, signal)
                    elif trend=="short" and signal=="SELL":
                        place_order(symbol, signal)
                    continue

                # New trade entry
                if signal and symbol not in open_trades:
                    place_order(symbol, signal)

                # Check stop-loss
                if symbol in open_trades:
                    if check_stop_loss(symbol, open_trades[symbol]):
                        send_telegram(f"⚠ Stop-loss hit for {symbol} {open_trades[symbol]}")
                        stop_loss_hit[symbol] = True
                        del open_trades[symbol]

            time.sleep(60)

        except Exception as e:
            send_telegram(f"❌ Error:\n{traceback.format_exc()}")
            time.sleep(5)

if __name__=="__main__":
    main()
