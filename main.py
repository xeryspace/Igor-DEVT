import asyncio
import json
import logging
import math

from fastapi import FastAPI, HTTPException, Request
from pybit.unified_trading import HTTP
from fastapi.templating import Jinja2Templates

current_buy_price_xeta = 0

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
        side = body.get("action")

        print(f"Received {side} signal for {symbol}")

        if side == "buy":
            await process_buy_signal(symbol)
        elif side == "sell":
            await process_sell_signal(symbol)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid side: {side}")

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
    global current_buy_price_xeta
    try:
        session.place_order(
            category="spot", symbol=symbol, side='buy', orderType="Market", qty=amount)
        current_buy_price_xeta = get_current_price(symbol)
    except Exception as e:
        logger.error(f"Error in open_position: {str(e)}")
        raise

def close_position(symbol, amount):
    global current_buy_price_xeta
    print(current_buy_price_xeta)
    try:
        session.place_order(
            category="spot", symbol=symbol, side='sell', orderType="Market", qty=amount)
        current_buy_price_xeta = 0
        print(f"Current buy price for XETAUSDT: {current_buy_price_xeta}")
    except Exception as e:
        logger.error(f"Error in close_position: {str(e)}")
        raise

async def process_buy_signal(symbol):
    global current_buy_price_xeta
    try:
        usdt_balance = get_wallet_balance("USDT")
        if usdt_balance >= 10:
            open_position(symbol, 10)
            current_buy_price_xeta = get_current_price(symbol)
        else:
            print(f"Insufficient USDT balance to open a Buy position for {symbol}")

    except Exception as e:
        logger.error(f"Error in process_buy_signal: {str(e)}")
        raise

async def process_sell_signal(symbol):
    try:
        symbol_balance_xeta = get_wallet_balance("XETA")
        if symbol_balance_xeta > 10:
            symbol_balance_xeta = math.floor(symbol_balance_xeta)
            close_position("XETAUSDT", symbol_balance_xeta)
            global current_buy_price_xeta
            current_buy_price_xeta = 0  # Reset the buy price to 0 after selling
        else:
            print(f"Insufficient XETA balance to close position for {symbol}")

    except Exception as e:
        logger.error(f"Error in process_sell_signal: {str(e)}")
        raise


async def check_price():
    global current_buy_price_xeta
    take_profit_threshold_percent = 1.5
    stop_loss_threshold_percent = -1.5
    print("Waiting for Action")
    while True:
        if current_buy_price_xeta > 0:
            current_price_xeta = get_current_price("XETAUSDT")
            price_change_percent_xeta = (current_price_xeta - current_buy_price_xeta) / current_buy_price_xeta * 100
            print(f'Buyprice: {current_buy_price_xeta} // Current Price: {current_price_xeta} // %-Change: {price_change_percent_xeta}')

            if price_change_percent_xeta >= take_profit_threshold_percent:
                print(f"Price increased by {price_change_percent_xeta:.2f}% for XETAUSDT. Selling all XETA.")
                await process_sell_signal("XETAUSDT")

            elif price_change_percent_xeta <= stop_loss_threshold_percent:
                print(f"Price decreased by {price_change_percent_xeta:.2f}% for XETAUSDT. Selling all XETA.")
                await process_sell_signal("XETAUSDT")

        await asyncio.sleep(0.08)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_price())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)