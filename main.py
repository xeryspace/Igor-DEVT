import asyncio
import json
import logging
import math

from fastapi import FastAPI, HTTPException, Request
from pybit.unified_trading import HTTP
from fastapi.templating import Jinja2Templates

current_buy_price_devt = 0

api_key = 'z7lPTNi7HuXNVWQzfi'
api_secret = 'N06FiDfVYbcTVMvjp4d2ume1VSlLZIpJ6KCR'
session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "name": "my-app", "version": "Hello world! From FastAPI running on Uvicorn. Eriks App"})

@app.post("/webhook")
async def handle_webhook(request: Request):
    try:
        query_params = dict(request.query_params)
        passphrase = query_params.get("passphrase", "")
        if passphrase != "Armjansk12!!":
            raise HTTPException(status_code=403, detail="Invalid passphrase")

        body = await request.json()
        symbol = body.get("symbol")  # Get the symbol 'DEVTUSDT'
        action = body.get("action")

        if action not in ['buy', 'sell']:
            return {"status": "ignored", "reason": f"Invalid action: {action}"}

        logger.info(f"Received {action} action for {symbol}")

        await process_signal(symbol, action)
        return {"status": "success", "data": "Position updated"}

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON format in the alert message: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON format in the alert message")
    except Exception as e:
        logger.error(f"Error in handle_webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def get_wallet_balance(symbol):
    try:
        wallet_balance = session.get_wallet_balance(
            category="spot",
            accountType="UNIFIED"
        )
        if wallet_balance['result']:
            coin_list = wallet_balance['result']['list'][0]['coin']
            for coin in coin_list:
                if coin['coin'] == symbol:
                    usdt_wallet_balance = coin['walletBalance']
                    return float(usdt_wallet_balance)
        return 0.0

    except Exception as e:
        logger.error(f"Error in get_wallet_balance: {str(e)}")
        raise

def get_current_price(symbol):
    try:
        ticker = session.get_tickers(category="spot", symbol=symbol)
        if ticker['result']:
            last_price = float(ticker['result']['list'][0]['lastPrice'])
            return last_price
        else:
            raise Exception(f"Failed to retrieve current price for {symbol}")
    except Exception as e:
        logger.error(f"Error in get_current_price: {str(e)}")
        raise

def open_position(symbol, amount):
    global current_buy_price_devt
    try:
        session.place_order(
            category="spot", symbol=symbol, side='buy', orderType="Market", qty=amount)
        current_buy_price_devt = get_current_price(symbol)
    except Exception as e:
        logger.error(f"Error in open_position: {str(e)}")
        raise

def close_position(symbol, amount):
    global current_buy_price_devt
    print(current_buy_price_devt)
    try:
        session.place_order(
            category="spot", symbol=symbol, side='sell', orderType="Market", qty=amount)
        current_buy_price_devt = 0
        print(f"Current buy price for DEVTUSDT: {current_buy_price_devt}")
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        raise

async def process_signal(symbol, action):
    global current_buy_price_devt
    try:
        if action == "buy":
            usdt_balance = get_wallet_balance("USDT")
            if usdt_balance > 3:
                rounded_down = math.floor(usdt_balance)
                open_position(symbol, rounded_down)
                current_buy_price_devt = get_current_price(symbol)
            else:
                logger.info(f"Insufficient USDT balance to open a Buy position for {symbol}")

        elif action == "sell":
            symbol_balance = get_wallet_balance("DEVT")
            if symbol_balance > 10:
                symbol_balance = math.floor(symbol_balance)
                logger.info(f"Closing {symbol} position with quantity: {symbol_balance}")
                close_position(symbol, symbol_balance)
                current_buy_price_devt = 0
            else:
                logger.info(f"DEVT balance is not above 10. No position to close.")

        else:
            logger.info(f"Invalid action: {action}")

    except Exception as e:
        logger.error(f"Error in process_signal: {str(e)}")
        raise

async def check_price():
    global current_buy_price_devt
    target_profit_percent = 2
    initial_sell_threshold_percent = 1.3
    stop_loss_threshold_percent_scenario1 = 0.8
    stop_loss_threshold_percent_scenario2 = 0.5
    profit_threshold_increment = 0.2
    sell_threshold_increment = 0.2

    while True:
        if current_buy_price_devt > 0:
            current_price_devt = get_current_price("DEVTUSDT")
            price_change_percent_devt = (current_price_devt - current_buy_price_devt) / current_buy_price_devt * 100
            sell_threshold_percent_devt = initial_sell_threshold_percent

            if price_change_percent_devt <= -stop_loss_threshold_percent_scenario1:
                logger.info(f"Scenario 1: Price dropped below {stop_loss_threshold_percent_scenario1}% for DEVTUSDT. Selling all DEVT.")
                symbol_balance_devt = get_wallet_balance("DEVT")
                if symbol_balance_devt > 10:
                    symbol_balance_devt = math.floor(symbol_balance_devt)
                    close_position("DEVTUSDT", symbol_balance_devt)
            elif price_change_percent_devt >= initial_sell_threshold_percent:
                logger.info(f"Price increased by {price_change_percent_devt:.2f}% for DEVTUSDT. Monitoring for sell threshold.")
                while True:
                    current_price_devt = get_current_price("DEVTUSDT")
                    price_change_percent_devt = (current_price_devt - current_buy_price_devt) / current_buy_price_devt * 100

                    if price_change_percent_devt >= target_profit_percent:
                        target_profit_percent += profit_threshold_increment
                        sell_threshold_percent_devt += sell_threshold_increment
                        logger.info(f"Profit threshold increased to {target_profit_percent:.2f}% and sell threshold increased to {sell_threshold_percent_devt:.2f}% for DEVTUSDT.")

                    if price_change_percent_devt <= -stop_loss_threshold_percent_scenario2:
                        logger.info(f"Scenario 2: Price dropped below {stop_loss_threshold_percent_scenario2}% for DEVTUSDT. Selling all DEVT.")
                        symbol_balance_devt = get_wallet_balance("DEVT")
                        if symbol_balance_devt > 10:
                            symbol_balance_devt = math.floor(symbol_balance_devt)
                            close_position("DEVTUSDT", symbol_balance_devt)
                        break
                    await asyncio.sleep(0.1)

        await asyncio.sleep(0.1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_price())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)