"""1提案 = 1枚のスライド画像として描画する。

Discord はネイティブでスライドを扱えないため、コンサル資料風の HTML を
組み立てて Playwright でスクリーンショットし、PNG バイト列にして返す。
"""
import html

from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 1280, 720

SLOT_LABEL = {"request": "指名枠", "continuation": "継続枠", "exploration": "探索枠"}
SLOT_COLOR = {"request": "#2563eb", "continuation": "#059669", "exploration": "#d97706"}


def _e(s):
    return html.escape(str(s)) if s is not None else ""


def _build_html(c, rej=None):
    slot = c.get("slot", "")
    accent = SLOT_COLOR.get(slot, "#334155")
    label = SLOT_LABEL.get(slot, slot)

    interpretation_html = ""
    if c.get("interpretation"):
        interpretation_html = f"""
        <div class="interpretation">解釈: {_e(c['interpretation'])}</div>
        """

    rej_html = f'<div class="rej">前回傾向: {_e(rej)}</div>' if rej else ""

    url_html = f'<div class="url">{_e(c["url"])}</div>' if c.get("url") else ""

    return f"""
    <html>
    <head>
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{
        width: {WIDTH}px; height: {HEIGHT}px;
        font-family: "Hiragino Sans", "Noto Sans JP", "Yu Gothic", sans-serif;
        background: #ffffff;
        color: #1e293b;
        display: flex;
        flex-direction: column;
      }}
      .bar {{
        height: 10px;
        background: {accent};
      }}
      .header {{
        padding: 36px 56px 0 56px;
      }}
      .badge {{
        display: inline-block;
        font-size: 20px;
        font-weight: 700;
        color: #ffffff;
        background: {accent};
        padding: 6px 18px;
        border-radius: 6px;
        letter-spacing: 2px;
      }}
      .rej {{
        margin-top: 14px;
        font-size: 16px;
        color: #64748b;
      }}
      .title {{
        margin-top: 18px;
        font-size: 44px;
        font-weight: 800;
        line-height: 1.3;
        color: #0f172a;
      }}
      .interpretation {{
        margin-top: 12px;
        font-size: 18px;
        color: #64748b;
        border-left: 4px solid #cbd5e1;
        padding-left: 14px;
      }}
      .body {{
        flex: 1;
        padding: 24px 56px;
        display: flex;
        flex-direction: column;
        gap: 26px;
        justify-content: center;
      }}
      .section-label {{
        font-size: 15px;
        font-weight: 700;
        color: {accent};
        letter-spacing: 3px;
        margin-bottom: 8px;
      }}
      .what {{
        font-size: 26px;
        line-height: 1.5;
        color: #1e293b;
      }}
      .why {{
        font-size: 30px;
        font-weight: 700;
        line-height: 1.5;
        color: #0f172a;
      }}
      .footer {{
        padding: 24px 56px 40px 56px;
        display: flex;
        gap: 32px;
        align-items: center;
        border-top: 1px solid #e2e8f0;
        font-size: 20px;
        color: #475569;
      }}
      .url {{
        font-size: 16px;
        color: #94a3b8;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
    </style>
    </head>
    <body>
      <div class="bar"></div>
      <div class="header">
        <span class="badge">{_e(label)}</span>
        {rej_html}
        <div class="title">{_e(c.get('title', ''))}</div>
        {interpretation_html}
      </div>
      <div class="body">
        <div>
          <div class="section-label">WHAT</div>
          <div class="what">{_e(c.get('what', ''))}</div>
        </div>
        <div>
          <div class="section-label">WHY</div>
          <div class="why">→ {_e(c.get('why', ''))}</div>
        </div>
      </div>
      <div class="footer">
        <div>⏱ {_e(c.get('minutes', 0))}分</div>
        <div>💰 ¥{_e(c.get('cost_jpy', 0))}</div>
        {url_html}
      </div>
    </body>
    </html>
    """


def render_card_image(c, rej=None):
    """1提案カードを 16:9 の PNG スライド画像として描画し、バイト列を返す。"""
    doc = _build_html(c, rej)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.set_content(doc)
        png = page.screenshot()
        browser.close()
    return png
