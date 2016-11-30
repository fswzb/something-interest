from pymongo import MongoClient
import pymongo
import numpy as np
import logging

logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                datefmt='%b %d %Y %H:%M:%S',
                filename='/home/daiab/log/quantlog.log',
                filemode='w')
logger = logging.getLogger(__name__)

class ReadDB:
    def __init__(self, datahandle):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.collection = self.client.quant.uqer
        self.datahandle = datahandle

    def updateStockCode(self, stockCodeList):
        self.stockCodeList = stockCodeList
        self.totalNum = len(stockCodeList)


    def readOneStockData(self, code):
        dbData = self.collection.find({"ticker": code, "isOpen": 1}).sort("tradeDate", pymongo.ASCENDING)
        data = []
        for dataDict in list(dbData):
            tmp = []
            """过滤掉异常数据"""
            if dataDict["openPrice"] < 0.001:
                continue
            if dataDict["closePrice"] < 0.001:
                continue
            if dataDict["highestPrice"] < 0.001:
                continue
            if dataDict["lowestPrice"] < 0.001:
                continue
            if dataDict["actPreClosePrice"] < 0.001:
                continue
            tmp.append(dataDict["openPrice"])
            tmp.append(dataDict["closePrice"])
            tmp.append(dataDict["highestPrice"])
            tmp.append(dataDict["lowestPrice"])
            tmp.append(dataDict["actPreClosePrice"])
            data.append(tmp)
            # print(tmp)
        count = len(data)
        logger.info("stock code == %s, count == %d", code, count)
        self.datahandle.formatDataDim(np.array(data))


    def destory(self):
        self.client.close()

if __name__=='__main__':
    pass
    # readData = ReadDB()
    # logger.info("data from db %s", readData.readOneStockData())
    # print(readData.readOneStockData())