# 微信内 H5 JSAPI 支付上线清单

本文只覆盖当前 CRM 的「微信生态内 H5 支付」路径：用户在微信内打开 H5 页面，通过公众号 OAuth 拿到 `openid`，后端调用微信支付 JSAPI 下单，前端拉起微信支付。

不覆盖小程序支付，也不覆盖微信外浏览器 H5 支付。

## 1. 微信后台要准备

### 公众号

- 已认证服务号。
- 记录公众号 `AppID` 和 `AppSecret`。
- 公众号网页授权域名配置为 CRM H5 域名，例如 `crm.example.com`。
- OAuth 授权回调会使用：
  - `/api/h5/wechat/oauth/callback`
  - `/api/h5/wechat-pay/oauth/callback`

### 微信支付商户平台

- 已开通微信支付商户号 `mchid`。
- 商户号已经绑定上面的公众号 `AppID`。
- 产品权限开通 JSAPI 支付。
- APIv3 密钥已设置，必须保存 32 字节原文。
- 已下载商户 API 证书，服务器需要保存私钥 PEM。
- 已准备微信支付平台证书 PEM 或微信支付平台公钥 PEM，用于支付通知验签。
- 支付通知地址配置为：
  - `https://<你的CRM域名>/api/h5/wechat-pay/notify`

### 虚拟商品类目

- 按实际售卖内容选择经营类目。
- 准备商品页面、价格、服务说明、售后/退款说明截图。
- 如果类目涉及网文、音视频、游戏、直播、区块链等，按微信支付要求补额外资质。

## 2. CRM 需要配置

推荐先在生产环境变量或配置中心写入：

```bash
WECHAT_MP_APP_ID=公众号AppID
WECHAT_MP_APP_SECRET=公众号AppSecret
WECHAT_MP_OAUTH_SCOPE=snsapi_base

WECHAT_PAY_ENABLED=true
WECHAT_PAY_APP_ID=公众号AppID
WECHAT_PAY_MCH_ID=商户号
WECHAT_PAY_API_V3_KEY=32字节APIv3密钥
WECHAT_PAY_PRIVATE_KEY_PATH=/home/ubuntu/certs/wechat_pay_apiclient_key.pem
WECHAT_PAY_CERT_SERIAL_NO=商户API证书序列号
WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH=/home/ubuntu/certs/wechat_pay_platform_cert.pem
WECHAT_PAY_PLATFORM_CERT_SERIAL_NO=微信支付平台证书序列号
WECHAT_PAY_NOTIFY_URL=https://<你的CRM域名>/api/h5/wechat-pay/notify
WECHAT_PAY_API_BASE=https://api.mch.weixin.qq.com
WECHAT_PAY_TIMEOUT_SECONDS=10
```

虚拟商品必须走服务端白名单，不能让前端传金额：

```json
{
  "products": [
    {
      "product_code": "assessment_report_v1",
      "name": "AI 测评报告",
      "description": "AI 测评报告",
      "amount_total": 9900,
      "currency": "CNY",
      "success_url": "/s/example/submitted",
      "enabled": true
    }
  ]
}
```

将上面的 JSON 写入 `WECHAT_PAY_PRODUCT_CATALOG_JSON`。

## 3. 当前已提供的 CRM 路由

- `GET /pay/<product_code>`：微信内 H5 结账页。
- `GET /api/h5/wechat-pay/oauth/start?return_url=/pay/<product_code>`：支付页 OAuth 起点。
- `GET /api/h5/wechat-pay/oauth/callback`：支付页 OAuth 回调。
- `GET /api/h5/wechat-pay/products/<product_code>`：读取商品配置。
- `POST /api/h5/wechat-pay/jsapi/orders`：创建 JSAPI 支付订单。
- `GET /api/h5/wechat-pay/orders/<out_trade_no>?refresh=1`：查询订单状态，可主动查微信支付。
- `POST /api/h5/wechat-pay/notify`：微信支付异步通知。

## 4. 上线验证

1. 打开 `https://<域名>/pay/<product_code>`，必须在微信内打开。
2. 首次打开应进入微信授权。
3. 授权后返回支付页，金额必须来自服务端商品目录。
4. 点击确认支付，应拉起微信支付。
5. 支付完成后，`wechat_pay_orders.status` 应变为 `paid`。
6. `wechat_pay_order_events` 应产生 `notify` 或 `query` 记录。
7. 前端最终展示支付成功或跳转到商品配置里的 `success_url`。

## 5. 常见故障

- `openid_required`：没有完成公众号 OAuth，检查网页授权域名、AppID/AppSecret、回调 URL。
- `wechat_pay_disabled`：`WECHAT_PAY_ENABLED` 未开启。
- `product_not_configured`：`WECHAT_PAY_PRODUCT_CATALOG_JSON` 没有这个 `product_code`。
- `missing WeChat Pay config`：商户号、私钥路径、证书序列号等基础配置缺失。
- `invalid WeChat Pay notify signature`：平台公钥或平台证书序列号不匹配。
- 支付成功但页面未立刻成功：等通知或使用订单状态接口 `refresh=1` 主动查单。

## 6. 官方参考

- JSAPI 支付产品介绍：https://pay.wechatpay.cn/doc/v3/merchant/4012062524
- JSAPI 下单：https://pay.wechatpay.cn/doc/v3/merchant/4012791856
- JSAPI 调起支付：https://pay.wechatpay.cn/doc/v3/merchant/4012791857
- 支付通知：https://pay.wechatpay.cn/doc/v3/merchant/4012075249
