# Import necessary libraries
import MetaTrader5 as mt5
import pandas as pd
from time import sleep
from datetime import datetime
import pytz
import os
# --- User Configuration (Update these values) ---
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M15
LOT_SIZE = 0.01  # Initial lot size
MAGIC_NUMBER = 123456
RISK_PERCENT = 5 # Risk 1% of the account balance per trade
STOP_LOSS_PIPS = 3000 # 30 pips for 5-digit brokers (300 points)
TAKE_PROFIT_PIPS = 6000 # 60 pips for 5-digit brokers (600 points)

# Loss percentage threshold to close a losing position automatically
# For example, 5% means the position will be closed if its loss
# is more than 5% of the account balance.
CUT_LOSS_THRESHOLD_PERCENT = 10

def clear_terminal():
    # Check if the operating system is Windows ('nt')
    os.system('cls' if os.name == 'nt' else 'clear') 


def log_to_file(message):
    """
    Appends a timestamped message to the log.txt file.
    
    :param message: The string message to be logged.
    """
    with open("log.txt", "a") as log_file:
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        log_file.write(f"{timestamp} {message}\n")
    print(message)

# --- Function Definitions ---

def connect_to_mt5():
    """Establishes a connection to the MetaTrader 5 terminal."""
    if not mt5.initialize():
        log_to_file(f"initialize() failed, error code={mt5.last_error()}")
        return False
    log_to_file("Connected to MetaTrader 5 successfully!")
    return True

def get_historical_data(symbol, timeframe, count):
    """
    Fetches historical OHLC (Open, High, Low, Close) data.

    :param symbol: The trading instrument symbol (e.g., "EURUSD").
    :param timeframe: The timeframe constant (e.g., mt5.TIMEFRAME_M15).
    :param count: The number of bars to fetch.
    :return: A Pandas DataFrame with the historical data.
    """
    utc_tz = pytz.timezone('Etc/UTC')
    now = datetime.now(utc_tz)
    
    rates = mt5.copy_rates_from(symbol, timeframe, now, count + 200)
    
    if rates is None or len(rates) == 0:
        log_to_file(f"Failed to get rates for {symbol}, error code={mt5.last_error()}")
        return None
        
    rates_frame = pd.DataFrame(rates)
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
    rates_frame = rates_frame.set_index('time')
    return rates_frame

def get_current_price(symbol):
    """
    Gets the current Bid and Ask prices for a symbol.

    :param symbol: The trading instrument symbol.
    :return: A tuple of (bid_price, ask_price) or (None, None) on failure.
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        return tick.bid, tick.ask
    return None, None

def get_lot_size(symbol, sl_pips, risk_percent):
    """
    Calculates the lot size based on a fixed risk percentage of the account balance.
    
    :param symbol: The trading instrument symbol.
    :param sl_pips: The stop loss distance in pips.
    :param risk_percent: The percentage of the account balance to risk.
    :return: The calculated lot size.
    """
    account_info = mt5.account_info()
    if not account_info:
        log_to_file(f"Failed to get account info, error code={mt5.last_error()}")
        return 0
    balance = account_info.balance
    
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        log_to_file(f"Failed to get symbol info, error code={mt5.last_error()}")
        return 0
    
    point = symbol_info.point
    
    risk_amount = balance * (risk_percent / 100)
    
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size
    
    if tick_size == 0:
        log_to_file("Tick size is zero, cannot calculate lot size.")
        return 0

    lot_value_per_pip = tick_value / point * mt5.symbol_info(symbol).volume_min
    
    if lot_value_per_pip == 0:
        log_to_file("Lot value per pip is zero, cannot calculate lot size.")
        return 0
        
    lot_size = risk_amount / (sl_pips * lot_value_per_pip)
    
    lot_size = round(lot_size, len(str(mt5.symbol_info(symbol).volume_step).split('.')[-1]))
    
    if lot_size < symbol_info.volume_min:
        lot_size = symbol_info.volume_min
    elif lot_size > symbol_info.volume_max:
        lot_size = symbol_info.volume_max
        
    log_to_file(f"Calculated lot size: {lot_size}")
    return lot_size

def get_positions(symbol):
    """
    Gets the currently open positions for a given symbol.
    
    :param symbol: The trading instrument symbol.
    :return: A list of position objects.
    """
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        log_to_file(f"No positions on {symbol}, error code={mt5.last_error()}")
        return []
    return list(positions)

def get_pending_orders(symbol):
    """
    Gets pending orders for a given symbol.
    
    :param symbol: The trading instrument symbol.
    :return: A list of order objects.
    """
    orders = mt5.orders_get(symbol=symbol)
    if orders is None:
        log_to_file(f"No pending orders on {symbol}, error code={mt5.last_error()}")
        return []
    return list(orders)

def close_position(position_ticket, volume=None):
    """
    Closes an existing position either partially or fully.
    
    :param position_ticket: The ticket number of the position to close.
    :param volume: The volume to close. If None, the entire position is closed.
    """
    position = mt5.positions_get(ticket=position_ticket)[0]
    
    if volume is None:
        volume_to_close = position.volume
    else:
        volume_to_close = volume
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": position.ticket,
        "symbol": position.symbol,
        "volume": volume_to_close,
        "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "deviation": 20,
        "magic": MAGIC_NUMBER
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_to_file(f"Position close failed: {result.retcode}, comment: {result.comment}")
    else:
        log_to_file(f"Position {position.ticket} closed successfully with volume {volume_to_close}.")

def place_order(symbol, order_type, lot, sl_pips, tp_pips):
    """
    Places a market order with a stop-loss and take-profit.

    :param symbol: The trading instrument symbol.
    :param order_type: The order type (mt5.ORDER_TYPE_BUY or mt5.ORDER_TYPE_SELL).
    :param lot: The lot size.
    :param sl_pips: The stop loss distance in pips.
    :param tp_pips: The take profit distance in pips.
    """
    point = mt5.symbol_info(symbol).point
    price_info = mt5.symbol_info_tick(symbol)
    if price_info is None:
        log_to_file("Failed to get tick information.")
        return
        
    if order_type == mt5.ORDER_TYPE_BUY:
        price = price_info.ask
        sl = price - sl_pips * point
        tp = price + tp_pips * point
    else: # ORDER_TYPE_SELL
        price = price_info.bid
        sl = price + sl_pips * point
        tp = price - tp_pips * point
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Python Algo",
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_to_file(f"Order failed: {result.retcode}, comment: {result.comment}")
        log_to_file(f"Request: {request}")
    else:
        log_to_file(f"Order placed successfully! Ticket: {result.order}")

def check_for_signals(data):
    """
    Analyzes historical data to generate trading signals based on a 
    Moving Average Crossover strategy.

    :param data: A Pandas DataFrame with OHLC data.
    :return: "BUY", "SELL", or "HOLD".
    """
    data['SMA_short'] = data['close'].rolling(window=20).mean()
    data['SMA_long'] = data['close'].rolling(window=50).mean()
    
    data.dropna(inplace=True)
    
    if len(data) < 2:
        return "HOLD"
    
    last_row = data.iloc[-1]
    prev_row = data.iloc[-2]
    
    if last_row['SMA_short'] > last_row['SMA_long'] and prev_row['SMA_short'] <= prev_row['SMA_long']:
        return "BUY"
    
    if last_row['SMA_short'] < last_row['SMA_long'] and prev_row['SMA_short'] >= prev_row['SMA_long']:
        return "SELL"
        
    return "HOLD"

def get_account_status():
    """
    Logs the current account status including margin and margin level.
    """
    account_info = mt5.account_info()
    if account_info:
        log_to_file("--- Account Status ---")
        log_to_file(f"Account Balance: {account_info.balance:.2f}")
        log_to_file(f"Account Equity: {account_info.equity:.2f}")
        log_to_file(f"Used Margin: {account_info.margin:.2f}")
        log_to_file(f"Free Margin: {account_info.margin_free:.2f}")
        if account_info.margin > 0:
            margin_level = (account_info.equity / account_info.margin) * 100
            log_to_file(f"Margin Level: {margin_level:.2f}%")
        else:
            log_to_file("Margin Level: N/A (No margin used)")
        log_to_file("----------------------")
    else:
        log_to_file(f"Failed to get account info, error code={mt5.last_error()}")

def modify_sl_tp(position_ticket, new_sl, new_tp):
    """
    Modifies the Stop Loss and Take Profit of an existing position.
    
    :param position_ticket: The ticket number of the position.
    :param new_sl: The new Stop Loss price.
    :param new_tp: The new Take Profit price.
    """
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position_ticket,
        "sl": new_sl,
        "tp": new_tp,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log_to_file(f"SL/TP modification failed for ticket {position_ticket}: {result.retcode}, comment: {result.comment}")
    else:
        log_to_file(f"SL/TP successfully modified for ticket {position_ticket}.")


def manage_positions():
    """
    Analyzes and manages all open positions.
    """
    positions = get_positions(SYMBOL)
    account_info = mt5.account_info()
    
    if not account_info:
        log_to_file("Cannot manage positions, failed to get account info.")
        return
        
    balance = account_info.balance
    
    if len(positions) == 0:
        log_to_file("No positions to manage.")
        return

    log_to_file(f"Managing {len(positions)} open position(s)...")

    for position in positions:
        log_to_file(f"--- Analyzing Position Ticket: {position.ticket} ---")
        
        # Check if position has SL/TP, and set it if not
        if position.sl == 0.0 or position.tp == 0.0:
            log_to_file(f"Position {position.ticket} has no SL/TP. Setting them now.")
            point = mt5.symbol_info(position.symbol).point
            current_price_bid, current_price_ask = get_current_price(position.symbol)
            
            if current_price_bid is None:
                continue

            if position.type == mt5.ORDER_TYPE_BUY:
                new_sl = current_price_ask - STOP_LOSS_PIPS * point
                new_tp = current_price_ask + TAKE_PROFIT_PIPS * point
            else:
                new_sl = current_price_bid + STOP_LOSS_PIPS * point
                new_tp = current_price_bid - TAKE_PROFIT_PIPS * point
            
            modify_sl_tp(position.ticket, new_sl, new_tp)

        # Analysis and correction logic
        current_pl = position.profit
        
        # Close position if loss is too high
        loss_percent = (abs(current_pl) / balance) * 100
        if current_pl < 0 and loss_percent > CUT_LOSS_THRESHOLD_PERCENT:
            log_to_file(f"Position {position.ticket} has a loss of {current_pl:.2f} ({loss_percent:.2f}% of balance). Cutting loss.")
            close_position(position.ticket)
            
        log_to_file(f"Position {position.ticket} current profit/loss: {current_pl:.2f}")

def main_loop():
    """The main trading loop that runs the bot."""
    if not connect_to_mt5():
        return
    
    while True:
        try:
            clear_terminal()
            log_to_file("\n" + "=" * 50)
            log_to_file(f"New Loop Start at {datetime.now()}")
            get_account_status()
            log_to_file("Checking for signals...")
            
            # Fetch data and get signal
            data = get_historical_data(SYMBOL, TIMEFRAME, 200)
            if data is None:
                sleep(60) # Wait a minute before retrying
                continue
                
            signal = check_for_signals(data)
            
            # Get current positions and pending orders
            positions = get_positions(SYMBOL)
            pending_orders = get_pending_orders(SYMBOL)
            
            # Trading Logic
            if signal == "BUY":
                if len(positions) == 0:
                    log_to_file("BUY Signal detected. Placing new BUY order.")
                    calculated_lot = get_lot_size(SYMBOL, STOP_LOSS_PIPS, RISK_PERCENT)
                    if calculated_lot > 0:
                        place_order(SYMBOL, mt5.ORDER_TYPE_BUY, calculated_lot, STOP_LOSS_PIPS, TAKE_PROFIT_PIPS)
                elif positions[0].type == mt5.ORDER_TYPE_SELL:
                    log_to_file("BUY Signal detected. Closing existing SELL position.")
                    close_position(positions[0].ticket)
            
            elif signal == "SELL":
                if len(positions) == 0:
                    log_to_file("SELL Signal detected. Placing new SELL order.")
                    calculated_lot = get_lot_size(SYMBOL, STOP_LOSS_PIPS, RISK_PERCENT)
                    if calculated_lot > 0:
                        place_order(SYMBOL, mt5.ORDER_TYPE_SELL, calculated_lot, STOP_LOSS_PIPS, TAKE_PROFIT_PIPS)
                elif positions[0].type == mt5.ORDER_TYPE_BUY:
                    log_to_file("SELL Signal detected. Closing existing BUY position.")
                    close_position(positions[0].ticket)
            
            else:
                log_to_file("No active trading signal. Holding current state.")
            
            # Call the position and pending order management functions
            manage_positions()
            
            if len(pending_orders) > 0:
                log_to_file("--- Pending Orders ---")
                for order in pending_orders:
                    log_to_file(f"Order Ticket: {order.ticket}, Symbol: {order.symbol}, Type: {order. type}, Price: {order.price_open}, Time: {datetime.fromtimestamp(order.time_setup)}")
                log_to_file("----------------------")
            
            log_to_file("Waiting for the next loop...")
            sleep(300)

        except Exception as e:
            log_to_file(f"An error occurred: {e}")
            sleep(60)
            
# --- Main execution block ---
if __name__ == "__main__":
    main_loop()
