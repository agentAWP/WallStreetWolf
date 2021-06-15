###############################################
#          Import some packages               #
###############################################
from flask import Flask, render_template
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import *
from dominate.tags import col, img
from flask import Flask, request, render_template, session, url_for,make_response
from functools import wraps
import json
import yfinance as yf
import pandas as pd
from pandas_datareader import data as pdr
import requests,datetime,re,time
import numpy as np
from bs4 import BeautifulSoup as soup
from urllib.request import Request, urlopen

# pd.set_option('display.max_colwidth', 20)

###############################################
#          Define flask app                   #
###############################################
app = Flask(__name__)
Bootstrap(app)


class Stock():
    def __init__(self,symbol,histData):
        self.symbol = symbol
        self.data = {}
        try:
            self.data["fiftyTwoWeekLow"] = float(self.stock52WeekRange()[0])
            self.data["fiftyTwoWeekHigh"] = float(self.stock52WeekRange()[1])
        except:
            self.data["fiftyTwoWeekHigh"] = 1000
            self.data["fiftyTwoWeekLow"] = 2
        self.funda = self.finvizFundamentals()
        #self.stock = pdr.get_data_yahoo(symbol,threads=True,progress=True)
        self.stock=histData
        if len(self.stock) > 0:
            self.close = self.stock["Close"][-1]
            self.open = self.stock["Open"][-1]
            self.high = self.stock["High"][-1]
            self.low = self.stock["Low"][-1]
            self.max = self.stock["Close"].max()
            self.volume = self.stock["Volume"][-1]
            try:
                self.dailyPercentChange = round(pd.Series([self.stock["Close"][-2],self.stock["Close"][-1]]).pct_change()[1]*100,2)
            except:
                self.dailyPercentChange = 0

    def stock52WeekRange(self):
        url = "https://finance.yahoo.com/quote/" + self.symbol.upper()
        # print (url)
        try:
            a = pd.read_html(url)
            priceInfo = a[0]
            priceInfo=priceInfo.set_index(priceInfo.columns[0])
            priceInfo=priceInfo.rename_axis("Price Information")
            marketInfo = a[1]
            marketInfo=marketInfo.set_index(marketInfo.columns[0])
            marketInfo=marketInfo.rename_axis("Price Information")
            range = priceInfo[1]["52 Week Range"].split("-")
            low = range[0]
            high = range[1]
            if (",") in low:
                low = low.replace(",","")
            if (",") in high:
                high = high.replace(",","")
            return low,high
        except:
            print ("Could not find 52 Week range from Yahoo!")

    def simpleMovingAverage(self,period):
        #Usage - stock.simpleMovingAverage(period)
        return self.stock.iloc[:,self.stock.columns.get_loc("Close")].rolling(window=period).mean()

    def percentChangeSeries(self,period):

        #RemovingIndexes and comparing
        s = pd.Series([self.stock.iloc[:,self.stock.columns.get_loc("Close")][-1*(period+1):-1].reset_index(drop=True),self.stock.iloc[:,self.stock.columns.get_loc("Close")][-1*(period):].reset_index(drop=True)]).pct_change()[1]*100

        #Adding Index back
        s.index = self.stock.iloc[:,self.stock.columns.get_loc("Close")][-1*(period):].index
        return s

    def finvizFundamentals(self):
        try:
            url = "https://finviz.com/quote.ashx?t=" + self.symbol.lower()
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            webpage = urlopen(req).read()
            html = soup(webpage, "html.parser")
            fundamentals = pd.read_html(str(html), attrs = {'class': 'snapshot-table2'})[0]
            finVizRatios, funda = {}, {}

            for x in range(0,len(fundamentals.iloc[0,:])):
                funda[fundamentals.iloc[x,0]] = fundamentals.iloc[x,1]
                funda[fundamentals.iloc[x,2]] = fundamentals.iloc[x,3]
                funda[fundamentals.iloc[x,4]] = fundamentals.iloc[x,5]
                funda[fundamentals.iloc[x,6]] = fundamentals.iloc[x,7]
                funda[fundamentals.iloc[x,8]] = fundamentals.iloc[x,9]
                funda[fundamentals.iloc[x,10]] = fundamentals.iloc[x,11]
            for m in ("Index","Market Cap","Book/sh","Cash/sh","Dividend","Dividend %","Recom","P/E","Forward P/E","PEG","P/S","P/B","P/C","P/FCF","Quick Ratio","Current Ratio","Debt/Eq","LT Debt/Eq","EPS (ttm)","EPS next Q","EPS next Y","EPS next 5Y","ROA","ROE","ROI","Target Price","Rel Volume","Avg Volume","Volume","Volatility"):
                finVizRatios[m]=funda[m]
            return finVizRatios
        except:
            return "COULD NOT LOAD FINVIZ FUNDAMENTALS"

#Takes a stock ticker
# or stock ticker list as input
def getStocks(assets):
    if isinstance(assets,str):
        stocks = Stock(assets,pdr.get_data_yahoo(assets,threads=100,progress=False))
    if isinstance(assets,list):
        data,stocks = {},{}
        if len(assets) == 1:
            data[assets[0]] = pdr.get_data_yahoo(assets,threads=100,progress=False,group_by="tickers")
        else:
            data = pdr.get_data_yahoo(assets,threads=100,progress=False,group_by="tickers")
        for x in assets:
            stocks[x.upper()] = Stock(x.upper(),data[x.upper()])
    return stocks

# US Industry Sectors, their stockTickers:weight
def industrySectors():
    df = pd.read_html("./templates/S&P500Market.html")[0]
    df.set_index(["S&P 500 Index Sectors"],inplace=True)
    return df

# Return a list of all ETF holdings
# Using Zacks Website
def zacksETFHoldings(ticker):
    stockList =[]
    if isinstance(ticker,str):
        keys = [ticker]
    elif isinstance(ticker,list):
        keys = ticker
    url = "https://www.zacks.com/funds/etf/{}/holding"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"}
    with requests.Session() as req:
        req.headers.update(headers)
        for key in keys:
            r = req.get(url.format(key))
            stockList = re.findall(r'etf\\\/(.*?)\\', r.text)
    etfStocks = []
    for x in stockList:
        a = x.replace(".","-")
        etfStocks.append(a)
    return etfStocks

# Returns ETF Holdings that crossed their <period> Day SMA TODAY
def etfHoldingsCrossedBelowSMA(ticker,period):
    allStocks = getStocks(zacksETFHoldings(ticker)[:10])

    allStocksbelowDaySMA = []
    for x in allStocks:
        ticker = allStocks[x]
        if len(ticker.stock) > 0:
            if len(ticker.stock["Close"]) >= 2:
                smaToday = ticker.simpleMovingAverage(period)[-1]
                smaYest = ticker.simpleMovingAverage(period)[-2]
                if ticker.stock["Close"][-2] > smaYest:
                    if ticker.stock["Close"][-1] < smaToday:
                        print ("\n" + ticker.symbol + " crossed below their " + str(period) + " day moving average TODAY.\nClose Price:" + str(ticker.close) + "\n" + str(period) + "DaySMA: " + str(smaToday) + "\n")
                        allStocksbelowDaySMA.append(ticker.symbol)
        return allStocksbelowDaySMA

# Returns ETF Holdings above/below their <period> Day SMA
def etfHoldingsAboveBelowSMA(ticker,period):
    if isinstance(ticker,str):
        allStocks = getStocks(zacksETFHoldings(ticker)[:3])
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    elif isinstance(ticker,dict):
        allStocks = ticker
    above,below = [],[]
    for x in allStocks:
        ticker = allStocks[x]
        if len(ticker.stock) > 0:
            if len(ticker.stock["Close"]) >= 2:
                smaToday = ticker.simpleMovingAverage(period)[-1]
                if ticker.close > smaToday:
                    above.append(ticker.symbol + " at price $" + str(ticker.close) + " is " + str(round(100*(ticker.close-smaToday)/ticker.close,2)) + "% above its " + str(period) + " day SMA: $" + str(smaToday) )
                if ticker.close < smaToday:
                    below.append(ticker.symbol + " at price $" + str(ticker.close) + " is " + str(round(100*(smaToday-ticker.close)/smaToday,2)) + "% below its " + str(period) + " day SMA: $" + str(smaToday) )

    print ("\n\nThere are " + str(len(above)) + " stocks above their " + str(period) + " SMA in the ETF\n")
    print ("------------------------------------------------")
    print(*above, sep = "\n")
    print ("------------------------------------------------")
    print ("\n\nThere are " + str(len(below)) + " stocks below their " + str(period) + " SMA in the ETF\n")
    print(*below, sep = "\n")
    return above,below

# Returns ETF Holdings deviation from its 52W High/Low and allTimeHigh
def etfHoldingsfiftyTwoWeekHighLowChange(ticker):
    holdingsFiftyTwoWeekHighLowChange = {}
    if isinstance(ticker,str):
        allStocks = getStocks(zacksETFHoldings(ticker)[:3])
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker[:3])
    elif isinstance(ticker,dict):
        allStocks = ticker
    # print ("GOING IN FOR LOOP")
    print (allStocks)
    print ("\n\n")
    for x in allStocks:
        ticker = allStocks[x]
        print (type(ticker.data["fiftyTwoWeekLow"]),type(ticker.data["fiftyTwoWeekHigh"]))
        holdingsFiftyTwoWeekHighLowChange[ticker.symbol] = []
        print("\n" + x + ": $" + str(ticker.close))
        holdingsFiftyTwoWeekHighLowChange[ticker.symbol].append("\n" + x + ": $" + str(ticker.close))
        holdingsFiftyTwoWeekHighLowChange[ticker.symbol].append("52 Day High (Intraday) is: " + str(ticker.data["fiftyTwoWeekHigh"]) + ". Percent Change from 52W High is: " + str(round(100*(ticker.data["fiftyTwoWeekHigh"]-ticker.close)/ticker.data["fiftyTwoWeekHigh"],2)) + "%")
        holdingsFiftyTwoWeekHighLowChange[ticker.symbol].append("52 Day Low (Intraday) is: " + str(ticker.data["fiftyTwoWeekLow"]) + ". Percent Change from 52W Low is: " + str(round(-100*(ticker.data["fiftyTwoWeekLow"]-ticker.close)/ticker.data["fiftyTwoWeekLow"],2))+ "%")
        columnNames = list(ticker.stock["Close"].isin([ticker.max])[ticker.stock["Close"].isin([ticker.max]) == True].index)[0].date()
        holdingsFiftyTwoWeekHighLowChange[ticker.symbol].append(ticker.symbol +" ($" + str(round(ticker.close,2)) + ") is currently " + str(round(100* (ticker.max-ticker.close)/ticker.max,2)) + "% below All Time High. All time high (closingPrice) ($" + str(round(ticker.max,2)) + ") was " + str((columnNames-datetime.date.today()).days) + " days ago on " + str(columnNames))
    return holdingsFiftyTwoWeekHighLowChange

# Returns ETF Holdings that closed lower
def etfHoldingsClosedLower(ticker):
    if isinstance(ticker,str):
        allStocks = getStocks(zacksETFHoldings(ticker)[:3])
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker[:3])
    elif isinstance(ticker,dict):
        allStocks = ticker
    print ("\n\nThe following stock/stocks closed lower today\n")
    stocksClosedLower = {}
    for x in allStocks:
        if allStocks[x].dailyPercentChange < -20:
            stocksClosedLower[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " entered bear market giving up " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
        elif allStocks[x].dailyPercentChange < -10:
            stocksClosedLower[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " went into recession losing " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
        elif allStocks[x].dailyPercentChange < 0:
            stocksClosedLower[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " dropped by " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
    print ("\n\n")
    return stocksClosedLower

# Returns ETF Holdings that closed higher
def etfHoldingsClosedHigher(ticker):
    if isinstance(ticker,str):
        allStocks = getStocks(zacksETFHoldings(ticker)[:3])
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    elif isinstance(ticker,dict):
        allStocks = ticker
    print ("\n\nThe following stock/stocks closed higher today\n")
    stocksClosedHigher = {}
    for x in allStocks:
        if allStocks[x].dailyPercentChange > 99:
            stocksClosedHigher[stocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " went to the moon with " + str(round(allStocks[x].dailyPercentChange,3)) + "% jump today.")
        elif allStocks[x].dailyPercentChange > 50 :
            stocksClosedHigher[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " saw a significant upside of " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
        elif allStocks[x].dailyPercentChange > 20:
            stocksClosedHigher[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " gained about " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
        elif allStocks[x].dailyPercentChange > 10:
            stocksClosedHigher[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " saw a move of " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
        elif allStocks[x].dailyPercentChange > 0:
            stocksClosedHigher[allStocks[x].symbol] = allStocks[x].dailyPercentChange
            print (allStocks[x].symbol + " increased by " + str(round(allStocks[x].dailyPercentChange,3)) + "% today.")
    print ("\n\n")
    return stocksClosedHigher


# Return if Stock closed lower
def stockClosedLower(ticker):
    if isinstance(ticker,str):
        stocks ={}
        stocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        stocks = getStocks(ticker)
    print ("\n\nThe following stock/stocks closed lower today\n")
    stocksClosedLower = {}
    for x in stocks:
        if stocks[x].dailyPercentChange < -20:
            stocksClosedLower[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " entered bear market giving up " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
        elif stocks[x].dailyPercentChange < -10:
            stocksClosedLower[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " went into recession losing " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
        elif stocks[x].dailyPercentChange < 0:
            stocksClosedLower[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " dropped by " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
    print ("\n\n")
    if len(stocksClosedLower) == 0:
        print ("NONE")
    return stocksClosedLower

# Return if Stock closed higher
def stocksClosedHigher(ticker):
    if isinstance(ticker,str):
        stocks ={}
        stocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        stocks = getStocks(ticker)
    print ("\n\nThe following stock/stocks closed higher today\n")
    stocksClosedHigher = {}
    for x in stocks:
        if stocks[x].dailyPercentChange > 99:
            stocksClosedHigher[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " went to the moon with " + str(round(stocks[x].dailyPercentChange,3)) + "% jump today.")
        elif stocks[x].dailyPercentChange > 50 :
            stocksClosedHigher[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " saw a significant upside of " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
        elif stocks[x].dailyPercentChange > 20:
            stocksClosedHigher[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " gained about " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
        elif stocks[x].dailyPercentChange > 10:
            stocksClosedHigher[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " saw a move of " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
        elif stocks[x].dailyPercentChange > 0:
            stocksClosedHigher[stocks[x].symbol] = stocks[x].dailyPercentChange
            print (stocks[x].symbol + " increased by " + str(round(stocks[x].dailyPercentChange,3)) + "% today.")
    print ("\n\n")
    if len(stocksClosedHigher) == 0:
        print ("NONE")
    return stocksClosedHigher

# Returns if the Stock is above/below is <period> SMA
def stocksAboveBelowSMA(ticker,period):
    if isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    if isinstance(ticker,list):
        allStocks = getStocks(ticker)
    if isinstance (ticker,Stock):
        allStocks={}
        allStocks[ticker.symbol]=ticker
    for x in allStocks:
        if len(allStocks[x].stock) > 0:
            if len(allStocks[x].stock["Close"]) >= 2:
                smaToday = allStocks[x].simpleMovingAverage(period)[-1]
                if allStocks[x].close > smaToday:
                    # print (allStocks[x].symbol + " at price $" + str(round(allStocks[x].close,3)) + " is " + str(round(100*(allStocks[x].close-smaToday)/allStocks[x].close,2)) + "% above its " + str(period) + " day SMA: $" + str(round(smaToday,2)))
                    return allStocks[x].symbol + " is " + str(round(100*(allStocks[x].close-smaToday)/allStocks[x].close,2)) + "% above its " + str(period) + " day SMA: $" + str(round(smaToday,2))
                elif allStocks[x].close < smaToday:
                    # print (allStocks[x].symbol + " at price $" + str(round(allStocks[x].close,3)) + " is " + str(round(100*(smaToday-allStocks[x].close)/smaToday,2)) + "% below its " + str(period) + " day SMA: $" + str(round(smaToday,2)))
                    return allStocks[x].symbol + " is " + str(round(100*(smaToday-allStocks[x].close)/smaToday,2)) + "% below its " + str(period) + " day SMA: $" + str(round(smaToday,2))

# Returns Stock deviation from its 52W High/Low and allTimeHigh
def stocksfiftyTwoWeekHighLowChange(ticker):
    if isinstance(ticker,Stock):
        allStocks = {}
        allStocks[ticker.symbol] = ticker
    elif isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    fiftyTwoWeekHighLowChange = []
    for x in allStocks:
        ticker = allStocks[x]
        print("\n" + x + ": $" + str(ticker.close))
        fiftyTwoWeekHighLowChange.append("52 Day High (Intraday) is: " + str(ticker.data["fiftyTwoWeekHigh"]) + ". Percent Change from 52W High is: " + str(round(100*(ticker.data["fiftyTwoWeekHigh"]-ticker.close)/ticker.data["fiftyTwoWeekHigh"],2)) + "%")
        fiftyTwoWeekHighLowChange.append("52 Day Low (Intraday) is: " + str(ticker.data["fiftyTwoWeekLow"]) + ". Percent Change from 52W Low is: " + str(round(-100*(ticker.data["fiftyTwoWeekLow"]-ticker.close)/ticker.data["fiftyTwoWeekLow"],2))+ "%")
        columnNames = list(ticker.stock["Close"].isin([ticker.max])[ticker.stock["Close"].isin([ticker.max]) == True].index)[0].date()
        fiftyTwoWeekHighLowChange.append(ticker.symbol + " is currently " + str(round(100* (ticker.max-ticker.close)/ticker.max,2)) + "% below All Time High. All time high (closingPrice) ($" + str(round(ticker.max,2)) + ") was " + str((columnNames-datetime.date.today()).days) + " days ago on " + str(columnNames))

    return fiftyTwoWeekHighLowChange

# Helps you understand price movement over a period of time
def percentChangePeriod(ticker):
    percentChangeDict = {}
    if isinstance(ticker,Stock):
        allStocks = {}
        allStocks[ticker.symbol] = ticker
    elif isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    # print(allStocks)
    for x in allStocks:
        ticker = allStocks[x]
        print ("\n" + ticker.symbol + " current price: $" + str(ticker.close))
        for period in (7,30,180,365):
            print (str(period) + " days ago price was : $" + str(ticker.stock["Close"][-period:][0]))
            print (str(period) + " Day Percent Change is " + str(-100*(ticker.stock["Close"][-period:][0]-ticker.close)/ticker.stock["Close"][-period:][0]))
            print ("\n")
            percentChangeDict[period] = -100*(ticker.stock["Close"][-period:][0]-ticker.close)/ticker.stock["Close"][-period:][0]
    return percentChangeDict

#Returns SMA Indicators for ETFs
def etfSMAMovement(etf):
    etfSMA = {}
    if isinstance(etf,str):
        allStocks = {}
        allStocks[etf] = getStocks(etf)
    if isinstance(etf,list):
        allStocks = getStocks(etf)
    if isinstance (etf,Stock):
        allStocks={}
        allStocks[etf.symbol]=etf
    for etf in allStocks:
        sma = {}
        a = allStocks[etf]
        for x in (20,50,100,200):
            if a.simpleMovingAverage(x)[-1] > a.close:
                sma[x] = a.symbol + " is " + str(round(100*(a.simpleMovingAverage(x)[-1]-a.close)/a.close)) + "% lower than its " + str(x) + " day SMA: " + str(a.simpleMovingAverage(x)[-1])
            elif a.simpleMovingAverage(x)[-1] < a.close:
                sma[x] = a.symbol + " is " + str(round(100*(a.close - a.simpleMovingAverage(x)[-1])/a.close)) + "% higher than its " + str(x) + " day SMA: " + str(a.simpleMovingAverage(x)[-1])
            elif a.simpleMovingAverage(x)[-1] == a.close:
                sma[x] = a.symbol + " is at its " + str(x) + " day SMA"
        etfSMA[etf] = sma
    return etfSMA

def emaIndicators(ticker):
    if isinstance(ticker,Stock):
        allStocks = {}
        allStocks[ticker.symbol] = ticker
    elif isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    ema = {}
    for x in allStocks:
        ticker = allStocks[x]
        for period in (20,50,100,200):
            r = requests.get("https://fmpcloud.io/api/v3/technical_indicator/daily/" + x + "?period="+ str(period) + "&type=ema&apikey=3a733d55d7e383c10eecc99e5f915307")
            if not r.json() or r.status_code != 200:
                return "EMA indicators not available"
            else:
                ema[period] = r.json()[0]["ema"]
        return ema

def dcfValue(ticker):
    if isinstance(ticker,Stock):
        allStocks = {}
        allStocks[ticker.symbol] = ticker
    elif isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    for x in allStocks:
        ticker = allStocks[x]
        r = requests.get("https://fmpcloud.io/api/v3/discounted-cash-flow/" + x.upper() + "?apikey=3a733d55d7e383c10eecc99e5f915307")
        if not r.json() or r.status_code != 200:
            return "Not enough data for Discounted Cash Flow Value"
        else:
            return "Discounted Cash Flow Value is " + str(r.json()[0]["dcf"])

# This is not being used currently. Instead the Zacks web scraper is being used
def finacialRatiosMetrics(ticker):
    if isinstance(ticker,Stock):
        allStocks = {}
        allStocks[ticker.symbol] = ticker
    elif isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    elif isinstance(ticker,list):
        allStocks = getStocks(ticker)
    finRatiosDict = {}
    for x in allStocks:
        ticker = allStocks[x]
        r = requests.get("https://financialmodelingprep.com/api/v3/ratios-ttm/" + x + "?apikey=308ce961a124eb43de86045c7340dac1",headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"})
        if not r.json() or r.status_code !=200:
            return "ERROR"
        else:
            for x in ("dividendYielPercentageTTM","peRatioTTM","pegRatioTTM","currentRatioTTM","quickRatioTTM","returnOnAssetsTTM","returnOnEquityTTM","returnOnCapitalEmployedTTM","ebtPerEbitTTM","ebitPerRevenueTTM","debtRatioTTM","debtEquityRatioTTM","operatingCashFlowPerShareTTM","freeCashFlowPerShareTTM","cashPerShareTTM","priceToBookRatioTTM","priceToSalesRatioTTM","priceEarningsRatioTTM","priceToFreeCashFlowsRatioTTM","priceToOperatingCashFlowsRatioTTM","priceCashFlowRatioTTM","priceEarningsToGrowthRatioTTM","priceSalesRatioTTM","enterpriseValueMultipleTTM","priceFairValueTTM"):
                finRatiosDict[x] = r.json()[0][x]
    return finRatiosDict

def yahooStats(ticker):
    url = "https://finance.yahoo.com/quote/"+ ticker + "/key-statistics?p=" + ticker
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urlopen(req,timeout=5)
    try:
        if resp.getcode() == 200:
            webpage = resp.read()
            html = soup(webpage, "html.parser")
            fundamentals = pd.read_html(str(html))
            yahooStats = {}
            yahooStats["ValuationMeasures"] = fundamentals[0].set_index(fundamentals[0].columns[0]).rename_axis("Valuation Measures").rename(columns={"As of Date: 3/4/2021Current":"Current"})
            yahooStats["StockPriceHistory"] = fundamentals[1].set_index(fundamentals[1].columns[0]).rename_axis("Stock Price History").rename(columns={1:""})
        return yahooStats
    except:
        return {"error":"Could not load yahooStats. Ticker should be an individual stock and not ETF/Index Fund"}

def lazyFAmarketState():
    url = "https://www.lazyfa.com/"
    a = pd.read_html(url)
    topGainers = a[0]
    topGainers=topGainers.set_index(topGainers.columns[0])
    topGainers=topGainers.rename_axis("TOP GAINERS")
    # print (topGainers)
    topLosers = a[1]
    topLosers=topLosers.set_index(topLosers.columns[0])
    topLosers=topLosers.rename_axis("TOP LOSERS")
    # print (topLosers)
    highestVolume = a[2]
    highestVolume=highestVolume.set_index(highestVolume.columns[0])
    highestVolume=highestVolume.rename_axis("HIGHEST VOLUME")
    # print (highestVolume)
    sectorPerformance = a[3]
    sectorPerformance=sectorPerformance.set_index(sectorPerformance.columns[0])
    sectorPerformance=sectorPerformance.rename_axis("SECTOR PERFORMANCE")
    sectorPerformance=sectorPerformance.drop(columns=["Time"])
    # print (sectorPerformance)
    return {"topGainers":topGainers,"topLosers":topLosers,"highestVolume":highestVolume,"sectorPerformance":sectorPerformance}

def etfDBHoldings(ticker):
    topHoldingsbyWeight = {}
    url = "https://etfdb.com/etf/" + ticker.upper() + "/#holdings"
    a = pd.read_html(url)
    t = a[2].set_index(a[2].columns[0])["% Assets"]
    for x in t.index:
        if isinstance(x,str):
            if "%" in t[x]:
                topHoldingsbyWeight[x.replace(".","-")]=t[x]
    # print (topHoldingsbyWeight)
    return topHoldingsbyWeight

def finVizMarketScreener():
    print ("************** S&P 500 **************\n\n")
    gspc = {}

    # {SMA : No. of Stocks}
    stocksCrossedAboveSMA = {}
    for x in (20,50,200):
        smaURL = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,idx_sp500,ta_sma"+ str(x) + "_pca&ft=4&o=change"
        req = Request(smaURL, headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        html = soup(webpage, "html.parser")
        screenResults = pd.read_html(str(html))
        if len(screenResults[8]) >= 2:
            stocksCrossedAboveSMA[x] = int(screenResults[7][0][0].split(":")[1].split("#")[0])
        else:
            stocksCrossedAboveSMA[x] = 0
    gspc["stocksCrossedAboveSMA"] = stocksCrossedAboveSMA


    # {SMA : No. of Stocks}
    stocksCrossedBelowSMA = {}
    for x in (20,50,200):
        smaURL = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,idx_sp500,ta_sma"+ str(x) + "_pcb&ft=4&o=change"
        req = Request(smaURL, headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        html = soup(webpage, "html.parser")
        screenResults = pd.read_html(str(html))
        if len(screenResults[8]) >= 5:
            stocksCrossedBelowSMA[x] = int(screenResults[7][0][0].split(":")[1].split("#")[0])
        else:
            stocksCrossedBelowSMA[x] = 0
    gspc["stocksCrossedBelowSMA"] = stocksCrossedBelowSMA


    print ("------------------------------------------------")

    # {Percent : No. Of Stocks}
    stocks52WHighPercentGap = {}
    flag = False
    for x in (5,10,15,20,30,40,50,60,70,80,90):
        if not flag:
            url = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,idx_sp500,ta_highlow52w_b" + str(x) + "h&ft=4&o=change"
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            webpage = urlopen(req).read()
            html = soup(webpage, "html.parser")
            screenResults = pd.read_html(str(html))
            stocks52WHighPercentGap[x] = int(screenResults[7][0][0].split(":")[1].split("#")[0])
            if stocks52WHighPercentGap[x] == 0:
                flag = True
        else:
            continue
    gspc["stocks52WHighPercentGap"] = stocks52WHighPercentGap

    # {Percent : No. Of Stocks}
    stocks52WLowPercentGap = {}
    flag = False
    for x in (5,10,15,20,30,40,50,60,70,80,90,100):
        if not flag:
            url = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,idx_sp500,ta_highlow52w_a" + str(x) + "h&ft=4&o=change"
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            webpage = urlopen(req).read()
            html = soup(webpage, "html.parser")
            screenResults = pd.read_html(str(html))
            stocks52WLowPercentGap[x] = int(screenResults[7][0][0].split(":")[1].split("#")[0])
            if stocks52WHighPercentGap[x] == 0:
                flag = True
        else:
            continue
    gspc["stocks52WLowPercentGap"] = stocks52WLowPercentGap

    # print ("------------------------------------------------")

    # # {Percent : DataFrame}
    stocksClosingUpToday = {}
    for x in (5,10,20):
        upURL = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,ta_change_u" + str(x) + "&ft=4&o=change"
        req = Request(upURL, headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        html = soup(webpage, "html.parser")
        screenResults = pd.read_html(str(html))
        if len(screenResults[8]) >= 2:
            stocksClosingUpToday[x] = screenResults[8]
            stocksClosingUpToday[x] = stocksClosingUpToday[x].drop(columns=0)
            stocksClosingUpToday[x] = stocksClosingUpToday[x].drop(columns=5)
            stocksClosingUpToday[x] = stocksClosingUpToday[x].set_index(stocksClosingUpToday[x].columns[0])
            stocksClosingUpToday[x] = stocksClosingUpToday[x].rename_axis("Stocks Closing " + str(x)+ "% Up Today")
            stocksClosingUpToday[x] = stocksClosingUpToday[x].rename(columns={2:"Company",3:"Sector",4:"Industry",6:"Market Cap",7:"P/E",8:"Price",9:"Change",10:"Volume"})
        else:
            stocksClosingUpToday[x] = 0

    # # {Percent : DataFrame}
    stocksClosingDownToday = {}
    for x in (5,10,20):
        downURL = "https://finviz.com/screener.ashx?v=111&f=cap_largeover,ta_change_d" + str(x) + "&ft=4&o=change"
        req = Request(downURL, headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        html = soup(webpage, "html.parser")
        screenResults = pd.read_html(str(html))
        if len(screenResults[8]) >= 2:
            stocksClosingDownToday[x] = screenResults[8]
            stocksClosingDownToday[x] = stocksClosingDownToday[x].drop(columns=0)
            stocksClosingDownToday[x] = stocksClosingDownToday[x].drop(columns=5)
            stocksClosingDownToday[x] = stocksClosingDownToday[x].set_index(stocksClosingDownToday[x].columns[0])
            stocksClosingDownToday[x]= stocksClosingDownToday[x].rename_axis("Stocks Closing " + str(x)+ "% Down Today")
            stocksClosingDownToday[x] = stocksClosingDownToday[x].rename(columns={2:"Company",3:"Sector",4:"Industry",6:"Market Cap",7:"P/E",8:"Price",9:"Change",10:"Volume"})
        else:
            stocksClosingDownToday[x] = 0
    #
    # print ("------------------------------------------------")
    #
    # {up : No. of Stocks}
    closingUpURL = "https://finviz.com/screener.ashx?v=111&f=idx_sp500,ta_change_u&ft=4&o=change"
    req = Request(closingUpURL, headers={'User-Agent': 'Mozilla/5.0'})
    webpage = urlopen(req).read()
    html = soup(webpage, "html.parser")
    screenResults = pd.read_html(str(html))
    stocksClosingUpToday["up"] = int(screenResults[7][0][0].split(":")[1].split("#")[0])

    # {down : No. of Stocks}
    closingDownURL = "https://finviz.com/screener.ashx?v=111&f=idx_sp500,ta_change_d&ft=4&o=change"
    req = Request(closingDownURL, headers={'User-Agent': 'Mozilla/5.0'})
    webpage = urlopen(req).read()
    html = soup(webpage, "html.parser")
    screenResults = pd.read_html(str(html))
    stocksClosingDownToday["down"] = int(screenResults[7][0][0].split(":")[1].split("#")[0])
    #
    gspc["stocksClosingUpToday"] = stocksClosingUpToday
    gspc["stocksClosingDownToday"] = stocksClosingDownToday
    #
    # print ("------------------------------------------------")

    return gspc

def stockanalysisFundamentals(ticker):
    incomeStatement, balanceSheet, cashFlowStatement, companyRatios = {}, {}, {}, {}
    # Income Statement
    tickerURL = "https://stockanalysis.com/stocks/"+ ticker + "/financials/"
    r = requests.get(tickerURL,headers = {"User-Agent":"Mozilla"})
    a = pd.read_html(r.text)
    a[0] = a[0].drop(["Unnamed: 1"], axis = 1)
    a[0] = a[0].set_index(a[0].columns[0])
    incomeStatement = a[0]

    # Balance Sheet Statement
    tickerURL = "https://stockanalysis.com/stocks/"+ ticker + "/financials/balance-sheet/"
    r = requests.get(tickerURL,headers={"User-Agent":"Mozilla"})
    b = pd.read_html(r.text)
    b[0] = b[0].drop(["Unnamed: 1"], axis = 1)
    b[0] = b[0].set_index(b[0].columns[0])
    balanceSheet = b[0]

    #Cash Flow Statement
    tickerURL = "https://stockanalysis.com/stocks/"+ ticker + "/financials/cash-flow-statement/"
    r = requests.get(tickerURL,headers={"User-Agent":"Mozilla"})
    c = pd.read_html(r.text)
    c[0] = c[0].drop(["Unnamed: 1"], axis = 1)
    c[0] = c[0].set_index(c[0].columns[0])
    cashFlowStatement = c[0]


    #Company Ratios
    tickerURL = "https://stockanalysis.com/stocks/"+ ticker + "/financials/ratios/"
    r = requests.get(tickerURL,headers={"User-Agent":"Mozilla"})
    d = pd.read_html(r.text)
    d[0] = d[0].drop(["Unnamed: 1"], axis = 1)
    d[0] = d[0].set_index(d[0].columns[0])
    companyRatios = d[0]
    return {"incomeStatement":incomeStatement,"balanceSheet":balanceSheet,"cashFlowStatement":cashFlowStatement,"companyRatios":companyRatios}

def askFinny(etfs):
    etfComparison = {}
    url = "https://www.askfinny.com/compare/" + etfs[0] + "-vs-" + etfs[1]
    a = pd.read_html(url)
    etfComparison["overall"] = a[0].rename(columns={"Unnamed: 0":"Metric"})
    etfComparison["overall"] = etfComparison["overall"].set_index(etfComparison["overall"].columns[0])
    etfComparison[etfs[0]] = a[1].rename(columns={"Unnamed: 0":"Date","Unnamed: 1":"Returns"})
    etfComparison[etfs[0]] = etfComparison[etfs[0]].set_index(etfComparison[etfs[0]].columns[0])
    etfComparison[etfs[1]] = a[3].rename(columns={"Unnamed: 0":"Date","Unnamed: 1":"Returns"})
    etfComparison[etfs[1]] = etfComparison[etfs[1]].set_index(etfComparison[etfs[1]].columns[0])
    return etfComparison

def priceMovementFinViz(tickers):
    stockData = {}
    for ticker in tickers:
        if "-" in ticker:
            ticker = ticker.replace("-",".")
        priceData = {}
        url = "https://finviz.com/quote.ashx?t=" + ticker
        r = requests.get(url,headers = {"User-Agent":"Mozilla"})
        if r.status_code == 200:
            a = pd.read_html(r.text)
            stock = a[5].to_dict()
            priceData["currentPrice"] = stock[11][10]
            priceData["dailyPercentChange"] = stock[11][11]
            priceRange = stock[9][5]
            priceData["52WLow"] = priceRange.split("-")[0]
            priceData["52WLowPercentChange"] = stock[9][7]
            priceData["52WHigh"] = priceRange.split("-")[1]
            priceData["52WHighPercentChange"] = stock[9][6]

            stockData[ticker] = pd.DataFrame.from_dict(priceData,orient="index").rename(columns={0:"price"})

    return stockData

def stockETFExposure(ticker):
    url = "https://etfdb.com/stock/"+ticker+"/"
    a = pd.read_html(url)
    a = a[0].set_index(a[0].columns[0])
    return a

def finVizStockScreener(tickers):
    stockScreenResults = {}
    screens = {"overivew":112,"valuation": 122, "financial":162,"performance":142,"technical":172}
    for tab in screens:
        url = "https://finviz.com/screener.ashx?v=" + str(screens[tab]) + "&t="
        for x in tickers:
            url += x + ","
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        html = soup(webpage, "html.parser")
        stockScreenResults[tab] = pd.read_html(str(html))[6]
        stockScreenResults[tab] = stockScreenResults[tab].drop(columns=0)
        stockScreenResults[tab] = stockScreenResults[tab].set_index(stockScreenResults[tab].columns[0])
        stockScreenResults[tab] = stockScreenResults[tab].rename_axis(tab)
    return stockScreenResults

def filingsSEC(ticker):
    secFilings = {}
    if isinstance(ticker,str):
        allStocks = {}
        allStocks[ticker] = getStocks(ticker)
    if isinstance(ticker,list):
        allStocks = getStocks(ticker)
    if isinstance (ticker,Stock):
        allStocks={}
        allStocks[ticker.symbol]=ticker
    for stock in allStocks:
        url = "https://whalewisdom.com/stock/" + stock
        try:
            a = pd.read_html(url)
            secTable = a[1]
            secTable = secTable.set_index(secTable.columns[0])
            # print (secTable.head(secTable.shape[0] -2))
            secFilings[stock] = secTable.head(secTable.shape[0] -2)
        except:
            secFilings[stock] = "No SEC filings found"
    return secFilings

#From StockTA.com
def techAnalysis(ticker):
    ticker = ticker.replace("-",".")
    techAnalysisMetrics = {}
    url = "http://www.stockta.com/cgi-bin/analysis.pl?symb=" + ticker  +"&cobrand=&mode=stock"
    a = pd.read_html(url)
    dailyData = a[5]
    dailyData = dailyData.set_index(dailyData.columns[0]) 
    dailyData = dailyData.drop(labels="Symbol",axis=0)
    dailyData = dailyData.rename(columns={1:"Last Trade",2:"Date",3:"Percent Change",4:"Open",5:"High",6:"Low",7:"Volume"})
    dailyData.index.names = ["Daily Data"]
    techAnalysisMetrics["dailyData"] = ["Daily Price Movement for " + ticker,dailyData]
    overallAnalysis = a[6]
    overallAnalysis = overallAnalysis.drop(labels=0,axis=0)
    overallAnalysis = overallAnalysis.set_index(overallAnalysis.columns[0])
    overallAnalysis = overallAnalysis.rename(columns={1:"Overall",2:"Short Term (30D)",3:"Intermediate Term (60D)",4:"Long Term (120D)"})
    overallAnalysis.index.names = ["Overall Analysis"]
    techAnalysisMetrics["overallAnalysis"] = ["Quick Overview.",overallAnalysis]
    supportResistanceAnalysis = a[9]
    supportResistanceAnalysis = supportResistanceAnalysis.set_index(supportResistanceAnalysis.columns[0])
    supportResistanceAnalysis = supportResistanceAnalysis.drop(labels="Type",axis=0)
    supportResistanceAnalysis = supportResistanceAnalysis.rename(columns={1:"Value",2:"Confluence"})
    supportResistanceAnalysis = supportResistanceAnalysis.drop(labels="Confluence",axis=1)
    supportResistanceAnalysis.index.names = ["Support and Resistance Price Points"]
    techAnalysisMetrics["supportResistanceAnalysis"] = ["Technical analysts use support and resistance levels to identify price points on a chart where the probabilities favor a pause or reversal of a prevailing trend.\nSupport occurs where a downtrend is expected to pause due to a concentration of demand.\nResistance occurs where an uptrend is expected to pause temporarily, due to a concentration of supply.\nConfluence refers to the strength of the support/resistance level.",supportResistanceAnalysis]
    chartIndicators = a[11]
    chartIndicators = chartIndicators.set_index(chartIndicators.columns[0])
    chartIndicators = chartIndicators.drop(labels="Ind.",axis=0)
    chartIndicators = chartIndicators.rename(columns={1:"Short Term (30D)",2:"Intermediate Term (60D)",3:"Long Term (120D)"})
    chartIndicators.index.names = ["Technical Indicators"]
    techAnalysisMetrics["chartIndicators"] = ["Quick Snapshot of Technical Indicators.\nBu=Bullish N=Neutral, Be=Bearish.",chartIndicators]
    techMetrics = ["fib","macd","ema","rsi","tdd","stoch"]
    for x in techMetrics:
        url = "http://www.stockta.com/cgi-bin/analysis.pl?symb="+ ticker + "&table=" + x + "&mode=table"
        if x == "fib":
            fib = pd.read_html(url)[6]
            fib = fib.rename(columns={0:"TimeFrame",1:"Trend",2:"38.2%",3:"50%",4:"61.8%"})
            fib = fib.set_index(fib.columns[0])
            fib = fib.drop(["Time Frame"],axis=0)
            fib.index.names = ["Fibonacci"]
            techAnalysisMetrics["fib"] = ["Fibonacci analysis evaluates the short term (30 days) intermediate term (60 days) and long term trends (120 days) and retracements.\nStocks that retrace 38.2% or less of a trend will usually continue the trend.\nRetracements exceeding 61.8% indicate a reversal.",fib]
        if x == "macd":
            macd = pd.read_html(url)[6]
            macd = macd.drop(labels=0,axis=0)
            macd = macd.rename(columns={0:"",1:"Fast MACD",2:"Slow MACD",3:"Slow v/s Fast"})
            macd = macd.set_index(macd.columns[0])
            macd.index.names = ["MACD"]
            techAnalysisMetrics["macd"] = ["The MACD analysis compares the MACD to the signal MACD line and their relationship to zero for any stock or commodity.\nThe MACD is calculated by subtracting the 26 day[slow MACD] expotential moving average (EMA) from the 12 day EMA [fast MACD].\nNegative MACD is SELL Signal. Positive MACD is BUY Signal.",macd]
            macdTrend = pd.read_html(url)[7]
            macdTrend = macdTrend.drop(labels=0,axis=0)
            macdTrend = macdTrend.rename(columns={0:"",1:"Short Term (30D)",2:"Intermediate Term (60D)",3:"Long Term (120D)"})
            macdTrend = macdTrend.set_index(macdTrend.columns[0])
            macdTrend.index.names = ["MACD Trends"]
            techAnalysisMetrics["macdTrend"] = ["Compares the three most recent price high and lows for MACD trends.\nHigher Index Trend > Lower Index Trend is a SELL Signal. Lower Index Trend > Higher Index Trend is a BUY Signal.",macdTrend]
        if x == "ema":
            ema = pd.read_html(url)[6]
            ema = ema.set_index(ema.columns[0])
            ema = ema.rename(columns={1:"5 day EMA",2:"13 day EMA",3:"20 day EMA",4:"50 Day EMA"})
            ema = ema.drop(["Last Trade"],axis=0)
            ema.index.names = ["Exponential Moving Averages"]
            techAnalysisMetrics["ema"] = ["The Exponential Moving Average (EMA) is similar to a simple moving average (average price over a set period) but it utilizes a weighting factor that exponentially declines from the most recent data point (recent prices are weighted higher than oid prices).\nThe respective EMA's will give bullish signals when trading above trailing EMA's and below the current price and vice versa.",ema]
        if x == "rsi":
            rsi = pd.read_html(url)[6]
            rsi = rsi.rename(columns={1:"RSI"})
            rsi = rsi.set_index(rsi.columns[0])
            rsi.index.names = ["Relative Strength Index"]
            techAnalysisMetrics["rsi"] = ["The relative strength index (RSI) is a momentum osciallator that is able to measure the velocity and magnitude of stock price changes.\nMomentum is calculated as the ratio of positive price changes to negative price changes.\nThe RSI analysis compares the current RSI against neutral(50), oversold (30) and overbought (70) conditions.",rsi]
        if x == "tdd":
            tdd = pd.read_html(url)[6]
            tdd = tdd.rename(columns={1:"TDD"})
            tdd = tdd.set_index(tdd.columns[0])
            tdd.index.names = ["Three Day Displaced"]
            techAnalysisMetrics["tdd"] = ["The Three Day Displaced (TDD) analysis compares the current price to the three day displaced (TDD) moving averge of the stock.\nThe three day displaced moving average is calculated using the three day average three days ago (or the average price 4,5 and 6 trading sessions ago).\nThe TDD average usually used as a trailling tight stop.\nStocks trading above the TDD are bullish and stocks trading below are considered bearish",tdd]
        if x == "stoch":
            stoch = pd.read_html(url)[6]
            stoch = stoch.rename(columns={1:"Stochastic Score"})
            stoch = stoch.set_index(stoch.columns[0])
            stoch.index.names = ["Stochastic Oscillator"]
            techAnalysisMetrics["stoch"] = ["A stochastic oscillator is a momentum indicator comparing a particular closing price of a security to a range of its prices over a certain period of time.\nTraditionally, readings over 80 are considered in the overbought range, and readings under 20 are considered oversold.",stoch]
    print ("**********************")
    for info in techAnalysisMetrics:
        print (techAnalysisMetrics[info][1].index.name)
    print ("**********************")
    return techAnalysisMetrics

#From financhill.com
def techSignals(ticker):
    ticker = ticker.replace("-",".")
    signalsTech = {}
    try:
        url = "https://financhill.com/stock-price-chart/" + ticker +"-technical-analysis"

        signals = pd.read_html(url)
        signalSMAEMA = signals[0]
        signalSMAEMA = signalSMAEMA.set_index(signalSMAEMA.columns[0])
        # signalSMAEMA.index.names = ["SMA and EMA"]
        signalSMAEMA.index.names = [""]
        signalSMAEMA.columns = ["Level","Buy or Sell"]
        signalsTech["SMA and EMA"] = signalSMAEMA

        signalRSIMACD = signals[1]
        signalRSIMACD = signalRSIMACD.set_index(signalRSIMACD.columns[0])
        # signalRSIMACD.index.names = ["RSI + MACD"]
        signalRSIMACD.index.names = [""]
        signalRSIMACD.columns = ["Level","Buy or Sell"]
        signalRSIMACD = signalRSIMACD.drop(labels="Chaikin Money Flow:",axis=0)
        signalsTech["RSI and MACD"] = signalRSIMACD

        signalBB = signals[2]
        signalBB = signalBB.set_index(signalBB.columns[0])
        # signalBB.index.names = ["Bollinger Bands"]
        signalBB.index.names = [""]
        signalBB.columns = ["Level","Buy or Sell"]
        signalsTech["Bollinger Bands"] = signalBB
    except:
        signalsTech["error"] = pd.DataFrame({'ERROR':  ['Technial Analysis Not Found']})
    return signalsTech

#Returns Major Recent Stock Activity from Super Investors (Dataroma.com)
def stockOwnership(ticker):
    ticker = ticker.replace("-",".")
    try:
        tickerOwnershipURL = "https://www.dataroma.com/m/stock.php?sym="+ ticker
        tickerOwnership = pd.read_html(tickerOwnershipURL)[2]
        tickerOwnership = tickerOwnership.set_index(tickerOwnership.columns[1])
        tickerOwnership = tickerOwnership.drop(tickerOwnership.columns[0],axis=1)
        return tickerOwnership
    except:
        x = {'ERROR':  ['No Data Found in Dataroma.com']}
        return pd.DataFrame(x)
def recentStockActivity(ticker):
    ticker = ticker.replace("-",".")
    try:
        recentActivityURL = "https://www.dataroma.com/m/activity.php?sym="+ ticker + "&typ=a"
        recentActivity = pd.read_html(recentActivityURL)[1]
        recentActivity = recentActivity.replace(to_replace=r'&nbsp', value='', regex=True)
        recentActivity = recentActivity.drop([recentActivity.columns[0],recentActivity.columns[5]],axis=1)
        recentActivity = recentActivity.set_index(recentActivity.columns[0])
        return recentActivity
    except:
        x = {'ERROR':  ['No Data Found in Dataroma.com']}
        return pd.DataFrame(x)


#CryptoMarket -- Data from CoingGecko API
def cryptoData():
    r = requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false")
    cryptoMarket = r.json()
    cryptoTickers = {}
    for x in cryptoMarket:
        if x["symbol"] in [
            "btc", 
            "eth",
            "bnb",
            "usdt",
            "ada",
            "doge",
            "xrp",
            "dot",
            "usdc",
            "icp",
            "uni",
            "link",
            "bch",
            "ltc",
            "matic",
            "sol",
            "xlm",
            "theta",
            "busd",
            "vet"
        ]:
            cryptoTickers[x["symbol"]] = {
                "Market Cap Rank"           : x["market_cap_rank"],
                "Current Price"             : x["current_price"],
                "Market Cap"                : x["market_cap"],
                "All Time High"             : x["ath"],
                "24H High"                  : x["high_24h"],
                "24H Low"                   : x["low_24h"],
                "24H Market Cap Change %"   : x["market_cap_change_percentage_24h"],
                "All Time High Change %"    : x["ath_change_percentage"],
                "24H Price Change %"        : x["price_change_percentage_24h"]
                }
    cryptoTable = pd.DataFrame.from_dict(cryptoTickers,orient="index")
    cryptoTable = cryptoTable.reset_index()
    cryptoTable = cryptoTable.set_index(cryptoTable.columns[1])
    cryptoTable = cryptoTable.rename(columns = {"index":"Ticker"})
    return cryptoTable


# print ("------------------------------------------------------------------------------------")


###############################################
#      Define navbar                          #
###############################################
topbar = Navbar(
                View('Home', 'home'),
                View('Stocks', 'stocks'),
                View('Fundamental', 'fundamentals'),
                View('ETFs', 'etf'),
                View('Markets', 'markets'),
                View('S&P500 Sector Holdings', 'sectorTopTenHoldings'),
                View('Company Financials', 'companyFinancialsComparison'),
                View('FinViz Stock Screener', 'finVizStockScreen'),
                View('CryptoCurrencies',"cryptoHoldings"),
                View("Value Investing Metrics and Ratios","valueinvesting")
                )

# registers the "top" menubar
nav = Nav()
nav.register_element('top', topbar)

###############################################
#          Render Home page                   #
###############################################
@app.route('/')
def home():
    return render_template("home.html")

###############################################
#          Render Stocks page                 #
###############################################
@app.route("/stocks/")
def stocks():
    return render_template("stocks.html")

###############################################
#          Render Stocks Data page            #
###############################################
@app.route("/stockData/",methods = ["GET","POST"])
def stockData():
    values = [request.form["symbol"].upper()]
    allStocks = getStocks(values)
    stockSECFilings = filingsSEC(values)
    stockPortfolioManagerActivity,stockMajorOwnership,dcfTool = {},{},{}
    tickerTASignals,tickerTA,smaDeviation,percentChange, fiftyTwoWeekHighLowChange,finViz, dcf, ema, finRatios, stockETF= {}, {}, {}, {}, {}, {}, {},{},{},{}
    for x in values:
        stockETF[x] = stockETFExposure(x)
        tickerTA[x] = techAnalysis(x)
        tickerTASignals[x] = techSignals(x)
        stockPortfolioManagerActivity[x] = recentStockActivity(x)
        stockMajorOwnership[x] = stockOwnership(x)
    for stock in allStocks:
        ticker = allStocks[stock]
        a = {}
        try:
            url = "https://dcftool.com/analysis/" + ticker.symbol
            dcfAnalysis = pd.read_html(url)
            dcfTool[ticker.symbol] = dcfAnalysis[0].set_index(dcfAnalysis[0].columns[0]).rename(columns={1:ticker.symbol})
        except:
            dcfTool[ticker.symbol] = pd.DataFrame.from_dict({"DCF for " + ticker.symbol + " not found at dcftool.com"})
        for period in (20,50,100,200):
            a[period] = stocksAboveBelowSMA(ticker,period)
        smaDeviation[stock] = a
        fiftyTwoWeekHighLowChange[stock] = stocksfiftyTwoWeekHighLowChange(ticker)
        percentChange[stock] = percentChangePeriod(ticker)
        dcf[stock] = dcfValue(ticker)
        ema[stock] = emaIndicators(ticker)

    return render_template("stockData.html",stockMajorOwnership=stockMajorOwnership,stockPortfolioManagerActivity=stockPortfolioManagerActivity,tickerTASignals=tickerTASignals,tickerTA=tickerTA,stockSECFilings=stockSECFilings,stockETF=stockETF,dcfTool=dcfTool,allStocks=allStocks,fiftyTwoWeekHighLowChange=fiftyTwoWeekHighLowChange,percentChange=percentChange,dcf=dcf,ema=ema,smaDeviation=smaDeviation)

###############################################
#          Render Fundamentals page           #
###############################################
@app.route("/fundamentals/")
def fundamentals():
    return render_template("fundamentals.html")
###############################################
#          Render Fundametal Results page     #
###############################################
@app.route("/fundaResult/",methods = ["GET","POST"])
def fundaResult():
    tickers = [request.form["symbol"].upper()]
    values = tickers
    stockStatements = {}
    allStocks = getStocks(values)
    yahooFunda,finViz = {},{}
    for ticker in tickers:
        if ("-") in ticker:
            ticker = ticker.replace("-",".")
            stockStatements[ticker] = stockanalysisFundamentals(ticker)
        else:
            stockStatements[ticker] = stockanalysisFundamentals(ticker)
    for stock in allStocks:
        ticker = allStocks[stock]
        finViz[stock] = ticker.finvizFundamentals()
        yahooFunda[ticker.symbol] = yahooStats(ticker.symbol)
        if "error" in yahooFunda[ticker.symbol]:
            print ("YES")
        # finRatios[stock] = finacialRatiosMetrics(ticker)
    return render_template("fundaResult.html",finRatios=finViz,yahooFunda=yahooFunda,stockStatements=stockStatements)

###############################################
#          Render ETF page                    #
###############################################
@app.route("/etf/")
def etf():
    return render_template("etf.html")
###############################################
#          Render ETF Results page            #
###############################################
@app.route("/etfResult/",methods = ["GET","POST"])
def etfResult():
    values = [request.form["symbol"].upper()]
    allETFs = getStocks(values)

    #Initialize Variables
    etfComparison,etfTickers,etfHoldings,etfHoldings2 = {},{},{},{}
    etfTopTenHoldings,etfStocksLower,etfStocksHigher = {}, {}, {}
    etfSMA = {}
    topTenHoldings =[]

    #Calculates Price Movement and 52WRange for Top Ten holdings
    for x in values:
        etfHoldings2[x] = etfDBHoldings(x)
        topTenHoldings = list(etfHoldings2[x].keys())[:10]
        stockData = priceMovementFinViz(topTenHoldings)
        etfTopTenHoldings[x] = stockData
        

    #ETF SMA movement
    etfSMA = etfSMAMovement(values)

    etfTA, etfTASignals = {},{}
    #Calculate Technical Analysis
    for x in values:
        etfTA[x] = techAnalysis(x)
        etfTASignals[x] = techSignals(x)

        
    # Find all Holdings and thier Weight in the portfolio
    for x in values:
        r = requests.get("https://financialmodelingprep.com/api/v3/etf-holder/" + x + "?apikey=308ce961a124eb43de86045c7340dac1",headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0"})
        if r.json():
            for m in r.json():
                if m["weightPercentage"] != None:
                    if m["asset"] != None:
                        etfTickers[m["asset"].replace(".","-")] = m["weightPercentage"]
            etfHoldings[x] = dict((sorted(etfTickers.items(), key=lambda item: item[1],reverse=True)))
            etfTickers = {}
        else:
            etfHoldings[x] = {"No Stock information available": "Could not find weight data"}


    return render_template("etfResult.html",etfTASignals=etfTASignals,etfTA=etfTA,etfSMA=etfSMA,etfTopTenHoldings=etfTopTenHoldings,stockData=stockData,etfHoldings=etfHoldings,allETFs=allETFs)


###############################################
#    Render S&P500 page                       #
###############################################
@app.route("/markets/")
def markets():
    return render_template("markets.html")
###############################################
#    Render S&P500 Result Page                #
###############################################
@app.route("/marketData/",methods = ["GET","POST"])
def marketData():
    sectors = industrySectors()
    marketMovement = lazyFAmarketState()
    finVizMarketScreen = finVizMarketScreener()
    return render_template("marketData.html",sectors = sectors,marketMovement=marketMovement,finVizMarketScreen=finVizMarketScreen)

###############################################
#    Render Sector Top Ten Holdings page      #
###############################################

@app.route("/sectorTopTenHoldings/",methods = ["GET"])
def sectorTopTenHoldings():
    allSectorsHoldingsByWeights = {}
    sectorList = industrySectors().iloc[:, 0].index.tolist()
    sectorHoldings = industrySectors()["Vanguard Sector ETF"].values.tolist()

    for x in range(0,len(sectorList)):
        allSectorsHoldingsByWeights[sectorList[x]] = pd.DataFrame.from_dict(etfDBHoldings(sectorHoldings[x]),orient="index",columns=[sectorHoldings[x]])
    return render_template("sectorTopTenHoldings.html",allSectorsHoldingsByWeights=allSectorsHoldingsByWeights)

###############################################
#    Render Company Financial Comparison page #
###############################################
@app.route("/companyFinancialsComparison/")
def companyFinancialsComparison():
    return render_template("companyFinancialsComparison.html")
###############################################
#   Render Company Financial Comparison       #
#          Results                            #
###############################################
@app.route("/companyFinancialsComparisonResult/",methods = ["GET","POST"])
def companyFinancialsComparisonResult():
    tickers = [request.form["symbol"].upper()]
    stockStatements = {}
    for ticker in tickers:
        stockStatements[ticker] = stockanalysisFundamentals(ticker)
    return render_template("companyFinancialsComparisonResult.html",stockStatements=stockStatements,tickers=tickers)


###############################################
#    Render FinViz Stock Screener Page        #
###############################################
@app.route("/finVizStockScreen/")
def finVizStockScreen():
    return render_template("finVizStockScreen.html")

###############################################
#    Render FinViz Stock Screener Result Page #
###############################################
@app.route("/finVizStockScreenerResult/",methods = ["GET","POST"])
def finVizStockScreenerResult():
    inputs = request.form.getlist('input_text[]')
    tickers = [x.upper() for x in inputs]
    stockScreenResults = finVizStockScreener(tickers)
    return render_template("finVizStockScreenResult.html",stockScreenResults=stockScreenResults)

###############################################
#    Render CryptoMarketData #
###############################################
@app.route("/cryptoHoldings/",methods = ["GET"])
def cryptoHoldings():
    cryptosByMarketCap = cryptoData()
    return render_template("cryptoHoldings.html",cryptosByMarketCap=cryptosByMarketCap)

@app.route("/valueinvesting/",methods = ["GET"])
def valueinvesting():
    return render_template("The Complete Value Investing Cheat Sheet.html")

###############################################
#             Init our app                    #
###############################################
nav.init_app(app)


###############################################
#                Run app                      #
###############################################
if __name__ == '__main__':
    # run app in debug mode on port 5000
    yf.pdr_override() # <== that's all it takes :-)
    app.run(debug=True, port=5000)
