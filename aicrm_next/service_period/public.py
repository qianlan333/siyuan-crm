from __future__ import annotations

from html import escape
import json
from typing import Any

from aicrm_next.public_product.service import _render_detail_media, route_headers


def _price_yuan(product: dict[str, Any]) -> str:
    cents = int(product.get("price_cents") or product.get("amount_total") or 0)
    return f"{cents / 100:.2f}"


def _end_date(value: Any) -> str:
    return str(value or "-")[:10]


def render_service_period_public_page(service_product: dict[str, Any], state: dict[str, Any]) -> str:
    trade_product = dict(service_product.get("trade_product") or {})
    product = {**trade_product, **service_product, "slices": trade_product.get("slices") or service_product.get("slices") or []}
    title = escape(str(product.get("title") or product.get("name") or "服务期商品"))
    duration_days = int(service_product.get("duration_days") or product.get("duration_days") or 0)
    membership_name = escape(str(service_product.get("membership_config_name") or "默认会员设置"))
    price_yuan = escape(_price_yuan(product))
    entitlement = state.get("entitlement") if isinstance(state.get("entitlement"), dict) else {}
    status = str(entitlement.get("status") or "none")
    cta_text = escape(str(state.get("cta_text") or ("立即报名" if status == "none" else "")) or "立即报名")
    unavailable = state.get("available") is False or status == "unavailable"
    if unavailable:
        tag_text = "未上架"
        hero_text = "该周期商品暂未开放"
        bar_meta = "暂未开放"
        card_html = f"""
      <div class="service-period-price"><small>¥</small>{price_yuan}</div>
      <div class="service-period-line"><span class="service-period-muted">开通后获得</span><strong>{membership_name}</strong></div>
      <div class="service-period-line"><span class="service-period-muted">有效期</span><strong>{duration_days} 天</strong></div>
      <p class="service-period-tip">该周期商品尚未上架，暂不可购买。</p>"""
    elif status == "active":
        tag_text = "使用中"
        hero_text = "当前服务仍在有效期内"
        bar_meta = f"剩余 {int(entitlement.get('remaining_days') or 0)} 天"
        card_html = f"""
      <div class="service-period-muted">剩余有效期</div>
      <div class="service-period-state-big">{int(entitlement.get('remaining_days') or 0)} 天</div>
      <div class="service-period-line"><span class="service-period-muted">到期日</span><strong>{escape(_end_date(entitlement.get('end_at')))}</strong></div>
      <div class="service-period-line"><span class="service-period-muted">续费价格 / 有效期</span><strong>¥{price_yuan} / {duration_days} 天</strong></div>
      <p class="service-period-tip">续费后有效期将继续顺延。</p>"""
    elif status == "expired":
        tag_text = "已过期"
        hero_text = "服务期已结束"
        bar_meta = f"¥{price_yuan} / {duration_days} 天"
        card_html = f"""
      <div class="service-period-state-big">已过期</div>
      <div class="service-period-line"><span class="service-period-muted">上次到期日</span><strong>{escape(_end_date(entitlement.get('end_at')))}</strong></div>
      <div class="service-period-line"><span class="service-period-muted">重新开通价格 / 有效期</span><strong>¥{price_yuan} / {duration_days} 天</strong></div>"""
    else:
        tag_text = "周期服务"
        hero_text = f"{duration_days} 天有效期"
        bar_meta = f"¥{price_yuan} / {duration_days} 天"
        card_html = f"""
      <div class="service-period-price"><small>¥</small>{price_yuan}</div>
      <div class="service-period-line"><span class="service-period-muted">开通后获得</span><strong>{membership_name}</strong></div>
      <div class="service-period-line"><span class="service-period-muted">有效期</span><strong>{duration_days} 天</strong></div>"""
    state_json = json.dumps(state, ensure_ascii=False, default=str).replace("</", "<\\/")
    media = _render_detail_media(product)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      min-height: 100%;
      background: #f7f8fa;
      color: #1f2329;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
      letter-spacing: 0;
    }}
    button {{ font: inherit; }}
    .service-period-page {{
      width: min(100%, 750px);
      min-height: 100vh;
      margin: 0 auto;
      padding-bottom: 92px;
      background: #fff;
    }}
    .service-period-hero {{
      padding: 24px 18px 18px;
      background: linear-gradient(135deg, #121a2b, #2e3851);
      color: #fff;
    }}
    .service-period-tag {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 3px 9px;
      border-radius: 999px;
      background: rgba(255, 255, 255, .14);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 14px;
    }}
    .service-period-hero h1 {{
      margin: 0;
      font-size: 26px;
      line-height: 1.24;
      font-weight: 900;
    }}
    .service-period-hero p {{
      margin: 8px 0 0;
      color: rgba(255, 255, 255, .72);
    }}
    .service-period-card {{
      margin: 14px;
      padding: 16px;
      border: 1px solid #f0f1f2;
      border-radius: 14px;
      background: #fff;
    }}
    .service-period-price {{
      font-size: 34px;
      line-height: 1.1;
      font-weight: 950;
    }}
    .service-period-price small {{
      font-size: 16px;
      margin-right: 2px;
    }}
    .service-period-state-big {{
      font-size: 38px;
      line-height: 1.1;
      font-weight: 950;
    }}
    .service-period-line {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 0;
      border-bottom: 1px solid #f0f1f2;
    }}
    .service-period-line:last-child {{ border-bottom: 0; }}
    .service-period-muted {{
      color: #8f959e;
    }}
    .service-period-tip {{
      margin: 10px 0 0;
      color: #8f959e;
      font-size: 13px;
    }}
    .service-period-bar {{
      position: fixed;
      left: 50%;
      bottom: 0;
      z-index: 20;
      width: min(100%, 750px);
      transform: translateX(-50%);
      display: grid;
      grid-template-columns: minmax(0, 1fr) 132px;
      gap: 12px;
      align-items: center;
      padding: 10px 14px 12px;
      border-top: 1px solid #dee0e3;
      background: rgba(255, 255, 255, .96);
      box-shadow: 0 -10px 34px rgba(26, 32, 48, .1);
      backdrop-filter: blur(12px);
    }}
    .service-period-bar-title {{
      color: #1f2329;
      font-size: 13px;
      font-weight: 900;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .service-period-bar-meta {{
      margin-top: 3px;
      color: #8f959e;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .service-period-button {{
      height: 50px;
      border: 0;
      border-radius: 12px;
      background: #3370ff;
      color: #fff;
      font-weight: 900;
      cursor: pointer;
    }}
    .service-period-button[disabled] {{
      opacity: .56;
      cursor: default;
    }}
    .detail-media {{ background: #fff; }}
    .slice-img {{
      width: 100%;
      display: block;
      min-height: 80px;
      object-fit: cover;
      background: #fff;
    }}
  </style>
</head>
<body>
  <main class="service-period-page" data-route-owner="ai_crm_next" data-fallback-used="false">
    <section class="service-period-hero">
      <span class="service-period-tag" id="servicePeriodTag">{escape(tag_text)}</span>
      <h1>{title}</h1>
      <p id="servicePeriodHeroText">{escape(hero_text)}</p>
    </section>
    <section class="service-period-card" id="servicePeriodStateCard">
{card_html}
    </section>
    {media}
  </main>
  <nav class="service-period-bar" aria-label="服务期商品操作">
    <div>
      <div class="service-period-bar-title">{title}</div>
      <div class="service-period-bar-meta" id="servicePeriodBarMeta">{escape(bar_meta)}</div>
    </div>
    <button class="service-period-button" id="servicePeriodPayButton" type="button">{cta_text}</button>
  </nav>
  <script>
    (function () {{
      const initialState = {state_json};
      const durationDays = {duration_days};
      const priceText = "¥{price_yuan}";
      const membershipName = "{membership_name}";
      const card = document.getElementById("servicePeriodStateCard");
      const tag = document.getElementById("servicePeriodTag");
      const heroText = document.getElementById("servicePeriodHeroText");
      const barMeta = document.getElementById("servicePeriodBarMeta");
      const button = document.getElementById("servicePeriodPayButton");
      function esc(value) {{
        return String(value == null ? "" : value).replace(/[&<>'"]/g, function (c) {{
          return {{"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}}[c];
        }});
      }}
      function endDate(value) {{
        return value ? String(value).slice(0, 10) : "-";
      }}
      function renderNone() {{
        tag.textContent = "周期服务";
        heroText.textContent = durationDays + " 天有效期";
        card.innerHTML = '<div class="service-period-price"><small>¥</small>{price_yuan}</div>' +
          '<div class="service-period-line"><span class="service-period-muted">开通后获得</span><strong>' + membershipName + '</strong></div>' +
          '<div class="service-period-line"><span class="service-period-muted">有效期</span><strong>' + durationDays + ' 天</strong></div>';
        barMeta.textContent = priceText + " / " + durationDays + " 天";
      }}
      function renderActive(entitlement) {{
        tag.textContent = "使用中";
        heroText.textContent = "当前服务仍在有效期内";
        card.innerHTML = '<div class="service-period-muted">剩余有效期</div>' +
          '<div class="service-period-state-big">' + Number(entitlement.remaining_days || 0) + ' 天</div>' +
          '<div class="service-period-line"><span class="service-period-muted">到期日</span><strong>' + esc(endDate(entitlement.end_at)) + '</strong></div>' +
          '<div class="service-period-line"><span class="service-period-muted">续费价格 / 有效期</span><strong>' + priceText + ' / ' + durationDays + ' 天</strong></div>' +
          '<p class="service-period-tip">' + ["续费后有效期", "将继续顺延。"].join("") + '</p>';
        barMeta.textContent = "剩余 " + Number(entitlement.remaining_days || 0) + " 天";
      }}
      function renderExpired(entitlement) {{
        tag.textContent = "已过期";
        heroText.textContent = "服务期已结束";
        card.innerHTML = '<div class="service-period-state-big">已过期</div>' +
          '<div class="service-period-line"><span class="service-period-muted">' + ["上次", "到期日"].join("") + '</span><strong>' + esc(endDate(entitlement.end_at)) + '</strong></div>' +
          '<div class="service-period-line"><span class="service-period-muted">' + ["重新", "开通价格 / 有效期"].join("") + '</span><strong>' + priceText + ' / ' + durationDays + ' 天</strong></div>';
        barMeta.textContent = priceText + " / " + durationDays + " 天";
      }}
      function renderUnavailable() {{
        tag.textContent = "未上架";
        heroText.textContent = "该周期商品暂未开放";
        card.innerHTML = '<div class="service-period-price"><small>¥</small>{price_yuan}</div>' +
          '<div class="service-period-line"><span class="service-period-muted">开通后获得</span><strong>' + membershipName + '</strong></div>' +
          '<div class="service-period-line"><span class="service-period-muted">有效期</span><strong>' + durationDays + ' 天</strong></div>' +
          '<p class="service-period-tip">该周期商品尚未上架，暂不可购买。</p>';
        barMeta.textContent = "暂未开放";
      }}
      function applyState(state) {{
        if (!state || state.ok === false) return;
        const entitlement = state.entitlement || {{status: "none"}};
        const status = entitlement.status || "none";
        button.textContent = state.cta_text || button.textContent || "立即报名";
        if (state.available === false || status === "unavailable") {{
          renderUnavailable();
          button.textContent = state.cta_text || "暂未开放";
          button.disabled = true;
          button.onclick = null;
          return;
        }}
        button.disabled = false;
        if (status === "active") renderActive(entitlement);
        else if (status === "expired") renderExpired(entitlement);
        else renderNone();
        button.onclick = function () {{
          if (!state.create_order_url) return;
          button.disabled = true;
          fetch(state.create_order_url, {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{}})
          }}).then(function (response) {{
            return response.json();
          }}).then(function (payload) {{
            if (payload.oauth_start_url) {{
              window.location.href = payload.oauth_start_url;
              return;
            }}
            if (payload.pay_params && window.WeixinJSBridge) {{
              window.WeixinJSBridge.invoke("getBrandWCPayRequest", payload.pay_params, function () {{
                window.location.reload();
              }});
              return;
            }}
            barMeta.textContent = payload.error || "支付请求已创建";
            button.disabled = false;
          }}).catch(function () {{
            barMeta.textContent = "支付请求失败";
            button.disabled = false;
          }});
        }};
      }}
      applyState(initialState);
      fetch(window.location.pathname.replace(/^\\/s\\//, "/api/h5/service-period-products/"))
        .then(function (response) {{ return response.json(); }})
        .then(function (payload) {{
          if (payload && payload.ok !== false) applyState(payload);
        }})
        .catch(function () {{}});
    }})();
  </script>
</body>
</html>"""


__all__ = ["render_service_period_public_page", "route_headers"]
