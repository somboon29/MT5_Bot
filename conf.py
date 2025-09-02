
# conf
SYMBOL = "XAUUSDm"
LOT_SIZE = 0.01  # Initial lot size
MAGIC_NUMBER = 123456
RISK_PERCENT = 5   # Risk 1% of the account balance per trade
STOP_LOSS_PIPS = 300  # 30 pips for 5-digit brokers (300 points)
TAKE_PROFIT_PIPS = 600 # 60 pips for 5-digit brokers (600 points)

# Loss percentage threshold to close a losing position automatically
# For example, 5% means the position will be closed if its loss
# is more than 5% of the account balance.
CUT_LOSS_THRESHOLD_PERCENT = 20