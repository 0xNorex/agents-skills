# 市场数据（Step 0 执行面）

查得到就查；查不到标「未验证」。禁止用训练记忆填价格、funding、清算、TVL。

用户口述的数字先当口述，能复核就复核。

## 查法

新闻、价格页面和 API 文档沿用宿主的搜索/抓取路由；确认公开 API 后可用下列只读请求。数字附来源与时间；端点变化先查官方文档，不猜。

## 价格 / funding / OI（公开，无需 key）

USDT-M：[Binance futures market data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api)

```bash
# mark / index / lastFundingRate
curl -sS "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"

# funding 历史
curl -sS "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=10"

# 持仓量
curl -sS "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"
```

现货价格：`https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT`

## 清算图

[Coinglass](https://docs.coinglass.com/reference/endpoint-overview) 要 `CG-API-KEY`（`https://open-api-v4.coinglass.com`）。环境里没有 key → 清算图标「未验证」，决策卡降级，不编热力图。

## TVL / 协议基本面

[DefiLlama API](https://defillama.com/docs/api)：`https://api.llama.fi/tvl/{protocol}` 、`https://api.llama.fi/protocol/{protocol}`。Pro 端点没 key 就不要用。

## 完成标准

- 用到的每个数字：有来源 URL，或已标「未验证」/「用户口述」
- 缺清算图或资金量时：不给具体仓位，只给视角分析（主文件降级规则）
