import asyncio
import json
import logging
import math

from fastapi import FastAPI, HTTPException, Request
from pybit.unified_trading import HTTP
from fastapi.templating import Jinja2Templates

current_buy_price_degen = 0

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
        symbol = body.get("symbol")

        logger.info(f"Received signal for {symbol}")

        await process_signal(symbol)
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
    global current_buy_price_degen
    try:
        session.place_order(
            category="spot", symbol=symbol, side='buy', orderType="Market", qty=amount)
        current_buy_price_degen = get_current_price(symbol)
    except Exception as e:
        logger.error(f"Error in open_position: {str(e)}")
        raise

def close_position(symbol, amount):
    global current_buy_price_degen
    print(current_buy_price_degen)
    try:
        session.place_order(
            category="spot", symbol=symbol, side='sell', orderType="Market", qty=amount)
        current_buy_price_degen = 0
        print(f"Current buy price for DEGENUSDT: {current_buy_price_degen}")
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        raise

async def process_signal(symbol):
    global current_buy_price_degen
    try:
        usdt_balance = get_wallet_balance("USDT")
        if usdt_balance > 3:
            rounded_down = math.floor(usdt_balance)
            open_position(symbol, rounded_down)
            current_buy_price_degen = get_current_price(symbol)
        else:
            logger.info(f"Insufficient USDT balance to open a Buy position for {symbol}")

    except Exception as e:
        logger.error(f"Error in process_signal: {str(e)}")
        raise


async def check_price():
    global current_buy_price_degen
    initial_stop_loss_threshold_percent = -0.65
    sell_threshold_increments = [0.5, 1.0, 1.3, 1.6, 1.9, 2.1, 2.4, 2.7, 3.0, 3.3, 3.6, 4.0]
    stop_loss_threshold_percent = initial_stop_loss_threshold_percent
    current_threshold_index = -1

    while True:
        if current_buy_price_degen > 0:
            current_price_degen = get_current_price("DEGENUSDT")
            price_change_percent_degen = (current_price_degen - current_buy_price_degen) / current_buy_price_degen * 100
            print(f'Bought at: {current_price_degen} // Current Price: {current_buy_price_degen} // %-Change:  {price_change_percent_degen}')
            for i in range(len(sell_threshold_increments)):
                if price_change_percent_degen >= sell_threshold_increments[i] and i > current_threshold_index:
                    current_threshold_index = i
                    stop_loss_threshold_percent = sell_threshold_increments[i] - 0.5
                    logger.info(
                        f"Price increased by {price_change_percent_degen:.2f}% for DEGENUSDT. Setting sell threshold to {stop_loss_threshold_percent:.2f}%.")
                    break

            if price_change_percent_degen >= 4.0 or price_change_percent_degen <= stop_loss_threshold_percent:
                logger.info(f"Price reached {price_change_percent_degen:.2f}% for DEGENUSDT. Selling all DEGEN.")
                symbol_balance_degen = get_wallet_balance("DEGEN")
                if symbol_balance_degen > 10:
                    symbol_balance_degen = math.floor(symbol_balance_degen)
                    close_position("DEGENUSDT", symbol_balance_degen)

        await asyncio.sleep(0.08)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_price())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)