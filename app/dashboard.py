# -*- coding: utf-8 -*-
"""
用户情感分析大屏（pyecharts 版）
--------------------------------
用 pyecharts 生成图表配置，再拼装成一页 1920x1080 的可视化大屏。

用法：
    python dashboard.py            # 生成 dashboard.html
    python dashboard.py --open     # 生成后自动用浏览器打开

数据目录：./data
    - 聊天密度月分布.csv
    - 聊天密度小时分布.csv
    - 聊天词语频次数据.csv
    - 情感分布.csv
    - 情感分析结果.csv   (id,time,records,sentiment_score,sentiment_label)
"""

import json
import re
import sys
import time
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, HeatMap, Line, Pie, WordCloud
from pyecharts.commons.utils import JsCode

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
CACHE = DATA / "_metrics.json"
OUT = BASE / "dashboard.html"

# ---------------------------------------------------------------- 配色
CYAN = "#22d3ee"
BLUE = "#38bdf8"
AMBER = "#fbbf24"
PURPLE = "#a78bfa"
GREEN = "#34d399"
ROSE = "#fb7185"
MUTED = "#8aa4c8"
GRID_LINE = "rgba(120,170,220,0.10)"
AXIS_LINE = "rgba(120,170,220,0.30)"
FONT = "Microsoft YaHei, PingFang SC, Helvetica Neue, sans-serif"

SENTI_COLOR = {"负面": ROSE, "中性": BLUE, "正面": GREEN}

# 客服场景主题词表（规则命中，命中数最高者为该条归属主题）
TOPIC_RULES = {
    "物流配送": ["快递", "物流", "发货", "到货", "签收", "配送", "运费", "包裹", "顺丰", "发货时间", "派送"],
    "售后退换": ["退货", "退款", "换货", "售后", "退换", "质量", "坏了", "破损", "维修", "保修", "漏发", "少发"],
    "优惠活动": ["优惠券", "满减", "活动", "折扣", "便宜", "会员", "红包", "秒杀", "促销", "优惠", "叠加"],
    "商品咨询": ["尺码", "颜色", "材质", "规格", "库存", "有货", "型号", "保质期", "洗面奶", "运动鞋", "适合", "成分"],
    "订单支付": ["订单", "支付", "付款", "下单", "取消", "收货人", "发票", "金额", "改地址", "备注"],
    "催单情绪": ["急", "尽快", "在线等", "麻烦", "服了", "投诉", "催", "为什么", "一直", "到底", "怎么回事"],
}
TOPIC_COLOR = {
    "物流配送": "#38bdf8",
    "售后退换": "#fb7185",
    "优惠活动": "#fbbf24",
    "商品咨询": "#a78bfa",
    "订单支付": "#34d399",
    "催单情绪": "#f97316",
}
WORD_PALETTE = ["#22d3ee", "#38bdf8", "#60a5fa", "#a78bfa", "#fbbf24", "#34d399", "#f472b6", "#e2f3ff"]


# ---------------------------------------------------------------- 数据
def read_csv(name):
    return pd.read_csv(DATA / name, encoding="utf-8-sig")


def build_metrics():
    df = read_csv("情感分析结果.csv")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df["hour"] = df["time"].dt.hour
    df["month"] = df["time"].dt.month
    df["weekday"] = df["time"].dt.weekday

    # 主题归属：关键词命中计数取最大，全不命中归入“其他咨询”
    text = df["records"].fillna("").astype(str)
    scores = pd.DataFrame({t: text.str.count("|".join(map(re.escape, kws))) for t, kws in TOPIC_RULES.items()})
    best = scores.idxmax(axis=1)
    df["topic"] = best.where(scores.max(axis=1) > 0, "其他咨询")

    hour_csv = read_csv("聊天密度小时分布.csv")
    word_csv = read_csv("聊天词语频次数据.csv").head(100)
    senti_csv = read_csv("情感分布.csv")

    total = int(len(df))
    days = int(df["time"].dt.date.nunique())
    senti_counts = {r["情感"]: int(r["数量"]) for _, r in senti_csv.iterrows()}
    senti_total = sum(senti_counts.values()) or 1

    # 按真实「年-月」聚合，避免把两年同名月份合并
    df["ym"] = df["time"].dt.to_period("M")
    month_index = sorted(df["ym"].unique())
    month_labels = [f"{p.year % 100:02d}-{p.month:02d}" for p in month_index]
    month_values = [int((df["ym"] == p).sum()) for p in month_index]

    topic_month = df.pivot_table(index="ym", columns="topic", values="id", aggfunc="count").fillna(0)
    topic_month = topic_month.reindex(month_index, fill_value=0)
    for t in TOPIC_RULES:
        if t not in topic_month.columns:
            topic_month[t] = 0

    ts = pd.crosstab(df["topic"], df["sentiment_label"], normalize="index") * 100
    topic_senti = {}
    for t in ts.index:
        topic_senti[t] = {
            "负面": round(float(ts.loc[t].get("负面 (差评)", ts.loc[t].get("负面", 0))), 1),
            "中性": round(float(ts.loc[t].get("中性", 0)), 1),
            "正面": round(float(ts.loc[t].get("正面 (好评)", ts.loc[t].get("正面", 0))), 1),
        }

    heat = df.pivot_table(index="weekday", columns="hour", values="id", aggfunc="count").fillna(0)
    heat = heat.reindex(index=range(7), columns=range(24), fill_value=0)

    hour_volume = [int(v) for v in hour_csv["消息数量"].tolist()]
    peak_hour_idx = hour_volume.index(max(hour_volume))

    metrics = {
        "total": total,
        "days": days,
        "daily": round(total / days) if days else 0,
        "avg_score": round(float(df["sentiment_score"].mean()), 3),
        "negative_rate": round(senti_counts.get("负面", 0) / senti_total * 100, 1),
        "peak_hour": f"{peak_hour_idx:02d}:00",
        "peak_value": max(hour_volume),
        "months": month_labels,
        "month_values": month_values,
        "hours": [f"{h:02d}" for h in range(24)],
        "hour_values": hour_volume,
        "words": [[str(w), int(c)] for w, c in zip(word_csv["词语"], word_csv["次数"])],
        "senti": senti_counts,
        "senti_total": senti_total,
        "topic_month": {t: [int(v) for v in topic_month[t].tolist()] for t in TOPIC_RULES},
        "topic_senti": topic_senti,
        "topic_count": {str(k): int(v) for k, v in df["topic"].value_counts().items()},
        "heat": [[h, w, int(heat.loc[w, h])] for w in range(7) for h in range(24)],
        "heat_max": int(heat.values.max()),
        "heat_p95": max(1, int(np.percentile(heat.values, 95))),
        "time_range": f"{df['time'].min():%Y-%m-%d} ~ {df['time'].max():%Y-%m-%d}",
    }
    return metrics


def load_metrics(force=False):
    src = DATA / "情感分析结果.csv"
    if not force and CACHE.exists() and CACHE.stat().st_mtime > src.stat().st_mtime:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    m = build_metrics()
    CACHE.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


# ---------------------------------------------------------------- 图表
AXIS_LABEL = opts.LabelOpts(color=MUTED, font_size=11, font_family=FONT)
SPLIT_LINE = opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color=GRID_LINE, type_="dashed"))
AXIS_LINE_OPT = opts.AxisLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color=AXIS_LINE))


def polish(option: dict, grid=None, axis_tooltip=False):
    """统一注入深色主题细节（pyecharts 导出的 option 再加工）"""
    option["textStyle"] = {"fontFamily": FONT, "color": MUTED}
    option["animationDuration"] = 900
    option["animationEasing"] = "cubicOut"
    option["tooltip"] = {
        "trigger": "axis" if axis_tooltip else "item",
        "backgroundColor": "rgba(6,18,34,0.94)",
        "borderColor": "rgba(56,189,248,0.35)",
        "borderWidth": 1,
        "padding": [8, 12],
        "textStyle": {"color": "#e2f3ff", "fontSize": 12, "fontFamily": FONT},
        "axisPointer": {"type": "line", "lineStyle": {"color": "rgba(34,211,238,0.55)", "type": "dashed"}},
    }
    if grid:
        option["grid"] = grid
    return option


def chart_month(m):
    x = m["months"]
    y = m["month_values"]
    grad = (
        "new echarts.graphic.LinearGradient(0,0,0,1,["
        "{offset:0,color:'rgba(34,211,238,0.72)'},{offset:0.45,color:'rgba(56,189,248,0.26)'},"
        "{offset:1,color:'rgba(56,189,248,0.01)'}])"
    )
    c = Line()
    c.add_xaxis(x)
    c.add_yaxis(
        "消息量",
        y,
        is_smooth=True,
        symbol="circle",
        symbol_size=7,
        label_opts=opts.LabelOpts(is_show=False),
        linestyle_opts=opts.LineStyleOpts(width=2.6, color=CYAN),
        itemstyle_opts=opts.ItemStyleOpts(color="#062033", border_color=CYAN, border_width=2),
        areastyle_opts=opts.AreaStyleOpts(opacity=1, color=JsCode(grad)),
        markpoint_opts=opts.MarkPointOpts(
            data=[opts.MarkPointItem(type_="max", name="峰值")],
            symbol="pin",
            symbol_size=42,
            itemstyle_opts=opts.ItemStyleOpts(color=AMBER),
            label_opts=opts.LabelOpts(color="#0a1626", font_size=10, font_weight="bold", formatter="{c}"),
        ),
        markline_opts=opts.MarkLineOpts(
            data=[opts.MarkLineItem(type_="average", name="月均")],
            linestyle_opts=opts.LineStyleOpts(color="rgba(251,191,36,0.55)", type_="dashed", width=1),
            label_opts=opts.LabelOpts(color=AMBER, font_size=10, position="insideEndBottom", formatter=JsCode("function(p){return '月均 ' + Math.round(p.value);}")),
        ),
    )
    c.set_global_opts(
        xaxis_opts=opts.AxisOpts(
            type_="category",
            boundary_gap=False,
            axislabel_opts=AXIS_LABEL,
            axisline_opts=AXIS_LINE_OPT,
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(is_show=False),
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            axislabel_opts=opts.LabelOpts(color=MUTED, font_size=10, font_family=FONT),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=SPLIT_LINE,
        ),
    )
    return polish(json.loads(c.dump_options_with_quotes()), {"left": 6, "right": 24, "top": 46, "bottom": 4, "containLabel": True}, True)


def chart_hour(m):
    x = m["hours"]
    y = m["hour_values"]
    peak = max(y)

    color_js = JsCode(
        """function(p){
            var isPeak = p.value >= %d;
            return new echarts.graphic.LinearGradient(0,0,0,1, isPeak
                ? [{offset:0,color:'#fde68a'},{offset:1,color:'rgba(251,191,36,0.35)'}]
                : [{offset:0,color:'#5eead4'},{offset:1,color:'rgba(34,211,238,0.42)'}]);
        }""" % peak
    )
    c = Bar()
    c.add_xaxis([f"{h}时" for h in x])
    c.add_yaxis(
        "消息量",
        y,
        bar_width="52%",
        category_gap="40%",
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(color=color_js, border_radius=[3, 3, 0, 0]),
    )
    c.set_global_opts(
        legend_opts=opts.LegendOpts(is_show=False),
        xaxis_opts=opts.AxisOpts(
            type_="category",
            axislabel_opts=opts.LabelOpts(color=MUTED, font_size=9, font_family=FONT, interval=1, rotate=0),
            axisline_opts=AXIS_LINE_OPT,
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(is_show=False),
        ),
        yaxis_opts=opts.AxisOpts(
            type_="value",
            axislabel_opts=opts.LabelOpts(color=MUTED, font_size=10, font_family=FONT),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=SPLIT_LINE,
        ),
    )
    return polish(json.loads(c.dump_options_with_quotes()), {"left": 6, "right": 16, "top": 22, "bottom": 4, "containLabel": True}, True)


def chart_words(m):
    data = m["words"]
    c = WordCloud()
    c.add(
        "高频词",
        [(w, v) for w, v in data],
        word_size_range=[13, 56],
        word_gap=4,
        shape="circle",
        rotate_step=0,
        pos_left="4%",
        pos_right="4%",
        pos_top="4%",
        pos_bottom="4%",
    )
    opt = json.loads(c.dump_options_with_quotes())
    # 按词频排名分配颜色，最高频最亮
    series = opt["series"][0]
    series["rotationRange"] = [0, 0]
    series["gridSize"] = 6
    series["drawOutOfBound"] = False
    series["textStyle"] = {"fontFamily": FONT, "fontWeight": "600"}
    for i, item in enumerate(series["data"]):
        color = WORD_PALETTE[0] if i < 3 else WORD_PALETTE[min(len(WORD_PALETTE) - 1, 1 + i % 7)]
        item["textStyle"] = {
            "color": color,
            "textShadowColor": "rgba(34,211,238,0.45)",
            "textShadowBlur": 10 if i < 10 else 4,
        }
    opt["tooltip"] = {
        "backgroundColor": "rgba(6,18,34,0.94)",
        "borderColor": "rgba(56,189,248,0.35)",
        "textStyle": {"color": "#e2f3ff", "fontSize": 12, "fontFamily": FONT},
    }
    opt["textStyle"] = {"fontFamily": FONT}
    return opt


def chart_topic(m):
    ts = m["topic_senti"]
    cnt = m["topic_count"]
    order = sorted(ts, key=lambda t: ts[t]["负面"])        # 横向条形：负面率低的在下方
    color_js = JsCode(
        """function(p){
            return new echarts.graphic.LinearGradient(0,0,1,0,[
                {offset:0,color:'rgba(251,113,133,0.22)'},{offset:1,color:'#fb7185'}]);
        }"""
    )
    c = Bar()
    c.add_xaxis([f"{t}  {cnt.get(t, 0):,}" for t in order])
    c.add_yaxis(
        "负面占比",
        [ts[t]["负面"] for t in order],
        bar_width="46%",
        label_opts=opts.LabelOpts(
            is_show=True, position="right", color="#ffd7de",
            font_size=12, font_weight="bold", font_family=FONT, formatter="{c}%",
        ),
        itemstyle_opts=opts.ItemStyleOpts(color=color_js, border_radius=[0, 3, 3, 0]),
    )
    c.reversal_axis()
    c.set_global_opts(
        legend_opts=opts.LegendOpts(is_show=False),
        xaxis_opts=opts.AxisOpts(
            type_="value",
            max_=100,
            axislabel_opts=opts.LabelOpts(color=MUTED, font_size=10, font_family=FONT, formatter="{value}%"),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=SPLIT_LINE,
        ),
        yaxis_opts=opts.AxisOpts(
            type_="category",
            axislabel_opts=opts.LabelOpts(color="#cfe4f7", font_size=11, font_family=FONT),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
            splitline_opts=opts.SplitLineOpts(is_show=False),
        ),
    )
    opt = json.loads(c.dump_options_with_quotes())
    for a in opt["yAxis"] if isinstance(opt["yAxis"], list) else [opt["yAxis"]]:
        a["inverse"] = True
    return polish(opt, {"left": 6, "right": 44, "top": 16, "bottom": 4, "containLabel": True}, True)


def chart_senti(m):
    order = ["负面", "中性", "正面"]
    total = m["senti_total"] or 1
    c = Pie()
    c.add(
        "",
        [(k, m["senti"].get(k, 0)) for k in order],
        radius=["52%", "74%"],
        center=["35%", "52%"],
        label_opts=opts.LabelOpts(is_show=False),
        label_line_opts=opts.PieLabelLineOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(border_color="rgba(5,14,28,0.92)", border_width=3),
    )
    c.set_global_opts(
        legend_opts=opts.LegendOpts(is_show=False),
        tooltip_opts=opts.TooltipOpts(
            trigger="item",
            formatter="{b}：{c} 条（{d}%）",
            background_color="rgba(6,18,34,0.94)",
            border_color="rgba(56,189,248,0.35)",
            textstyle_opts=opts.TextStyleOpts(color="#e2f3ff", font_size=12),
        ),
    )
    opt = json.loads(c.dump_options_with_quotes())
    for s_ in opt["series"]:
        for item in s_["data"]:
            item["itemStyle"] = {
                "color": SENTI_COLOR[item["name"]],
                "borderColor": "rgba(5,14,28,0.92)",
                "borderWidth": 3,
                "shadowColor": "rgba(34,211,238,0.25)",
                "shadowBlur": 18,
            }
    opt["tooltip"] = {
        "trigger": "item",
        "formatter": "{b}：{c} 条（{d}%）",
        "backgroundColor": "rgba(6,18,34,0.94)",
        "borderColor": "rgba(56,189,248,0.35)",
        "borderWidth": 1,
        "textStyle": {"color": "#e2f3ff", "fontSize": 12, "fontFamily": FONT},
    }
    opt["textStyle"] = {"fontFamily": FONT}
    return opt


def chart_heat(m):
    c = HeatMap()
    c.add_xaxis([f"{h}" for h in range(24)])
    week = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    c.add_yaxis(
        "消息密度",
        week,
        [[d[0], d[1], d[2]] for d in m["heat"]],
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(border_color="rgba(5,14,28,0.85)", border_width=1.5),
    )
    c.set_global_opts(
        legend_opts=opts.LegendOpts(is_show=False),
        xaxis_opts=opts.AxisOpts(
            type_="category",
            splitarea_opts=opts.SplitAreaOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color=MUTED, font_size=9, font_family=FONT, interval=2),
            axisline_opts=AXIS_LINE_OPT,
            axistick_opts=opts.AxisTickOpts(is_show=False),
        ),
        yaxis_opts=opts.AxisOpts(
            type_="category",
            splitarea_opts=opts.SplitAreaOpts(is_show=False),
            axislabel_opts=opts.LabelOpts(color=MUTED, font_size=10, font_family=FONT),
            axisline_opts=opts.AxisLineOpts(is_show=False),
            axistick_opts=opts.AxisTickOpts(is_show=False),
        ),
        visualmap_opts=opts.VisualMapOpts(
            is_show=False,
            min_=0,
            max_=m["heat_p95"],
            range_color=["#0a1a2e", "#0f3d5c", "#117a8b", "#22d3ee", "#fbbf24"],
        ),
    )
    opt = json.loads(c.dump_options_with_quotes())
    for axis in ("xAxis", "yAxis"):
        seq = opt[axis] if isinstance(opt[axis], list) else [opt[axis]]
        for a in seq:
            a["splitArea"] = {"show": False}
    for a in opt["yAxis"] if isinstance(opt["yAxis"], list) else [opt["yAxis"]]:
        a["inverse"] = True
    return polish(opt, {"left": 6, "right": 12, "top": 12, "bottom": 6, "containLabel": True})


# ---------------------------------------------------------------- 页面
TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>用户情感分析大屏</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:100%;height:100%;background:#03080f;overflow:hidden;
    font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#cfe4f7}
  #stage{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
  #screen{width:1920px;height:1080px;position:relative;transform-origin:center center;overflow:hidden;
    background:
      radial-gradient(1100px 620px at 50% -12%, rgba(34,120,200,0.28), transparent 68%),
      radial-gradient(760px 520px at 8% 106%, rgba(14,116,144,0.22), transparent 70%),
      radial-gradient(760px 520px at 96% 96%, rgba(59,130,246,0.16), transparent 70%),
      linear-gradient(180deg,#050d1a 0%,#040a14 55%,#03080f 100%);
  }
  #screen::before{content:"";position:absolute;inset:0;pointer-events:none;
    background-image:linear-gradient(rgba(90,150,210,0.055) 1px,transparent 1px),
                     linear-gradient(90deg,rgba(90,150,210,0.055) 1px,transparent 1px);
    background-size:48px 48px;mask-image:radial-gradient(circle at 50% 40%,#000 30%,transparent 88%)}
  #screen::after{content:"";position:absolute;inset:0;pointer-events:none;
    background:repeating-linear-gradient(180deg,rgba(255,255,255,0.014) 0 1px,transparent 1px 3px)}

  header{position:relative;height:92px;display:flex;align-items:center;justify-content:space-between;padding:0 34px;
    background:linear-gradient(180deg,rgba(10,32,58,0.75),rgba(6,18,34,0))}
  header::after{content:"";position:absolute;left:34px;right:34px;bottom:8px;height:1px;
    background:linear-gradient(90deg,transparent,rgba(56,189,248,0.5),rgba(56,189,248,0.12),transparent)}
  .brand{display:flex;align-items:center;gap:12px;width:420px}
  .brand .mark{width:10px;height:30px;border-radius:2px;
    background:linear-gradient(180deg,#22d3ee,#3b82f6);box-shadow:0 0 18px rgba(34,211,238,0.7)}
  .brand b{display:block;font-size:15px;letter-spacing:3px;color:#e8f6ff;font-weight:600}
  .brand span{display:block;font-size:10px;letter-spacing:2.4px;color:#4f7ba3;margin-top:4px}
  .title{text-align:center;flex:1}
  .title h1{font-size:34px;letter-spacing:8px;font-weight:700;
    background:linear-gradient(180deg,#ffffff 18%,#7fd8f0 62%,#2b9fd6 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent;
    text-shadow:0 0 34px rgba(34,211,238,0.35)}
  .title p{font-size:10px;letter-spacing:5px;color:#40688e;margin-top:6px}
  .hright{width:420px;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
  .clock{font-size:26px;font-weight:600;letter-spacing:2px;color:#eaf7ff;
    font-variant-numeric:tabular-nums;text-shadow:0 0 18px rgba(34,211,238,0.45)}
  .date{font-size:11px;letter-spacing:1.6px;color:#5f88b0}

  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;padding:6px 34px 0}
  .kpi{position:relative;height:96px;padding:14px 16px;border-radius:6px;overflow:hidden;
    background:linear-gradient(150deg,rgba(16,44,76,0.85),rgba(7,19,36,0.72));
    border:1px solid rgba(56,189,248,0.16);box-shadow:inset 0 1px 0 rgba(255,255,255,0.05)}
  .kpi::before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:2px;
    background:linear-gradient(180deg,#22d3ee,rgba(34,211,238,0))}
  .kpi .lbl{font-size:11px;letter-spacing:1.4px;color:#7fa0c4}
  .kpi .val{margin-top:8px;font-size:30px;font-weight:700;color:#f2fbff;line-height:1;
    font-variant-numeric:tabular-nums;text-shadow:0 0 22px rgba(34,211,238,0.4)}
  .kpi .val i{font-style:normal;font-size:13px;color:#7fd8f0;margin-left:4px;font-weight:500}
  .kpi .en{position:absolute;right:14px;bottom:10px;font-size:9px;letter-spacing:1.6px;color:#2e5478}

  .grid{position:absolute;left:34px;right:34px;top:212px;bottom:56px;
    display:grid;grid-template-columns:466px 1fr 466px;gap:16px}
  .col{display:grid;grid-template-rows:1fr 1fr;gap:16px;min-height:0}
  .panel{position:relative;border-radius:6px;padding:0 6px 6px;min-height:0;display:flex;flex-direction:column;
    background:linear-gradient(160deg,rgba(13,34,60,0.78),rgba(6,17,33,0.66));
    border:1px solid rgba(56,189,248,0.15);
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.05),0 10px 30px rgba(2,8,18,0.45);
    backdrop-filter:blur(3px);animation:rise .75s both}
  @keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
  .screen.static .panel{animation:none}
  .panel::before,.panel::after{content:"";position:absolute;width:14px;height:14px;pointer-events:none}
  .panel::before{left:-1px;top:-1px;border-left:2px solid #22d3ee;border-top:2px solid #22d3ee;border-top-left-radius:5px}
  .panel::after{right:-1px;bottom:-1px;border-right:2px solid rgba(34,211,238,0.75);border-bottom:2px solid rgba(34,211,238,0.75);border-bottom-right-radius:5px}
  .p-hd{height:44px;display:flex;align-items:center;gap:9px;padding:0 10px}
  .p-hd i{width:3px;height:14px;border-radius:2px;background:linear-gradient(180deg,#22d3ee,#1d4ed8);
    box-shadow:0 0 10px rgba(34,211,238,0.8)}
  .p-hd h3{font-size:15px;font-weight:600;color:#e6f4ff;letter-spacing:1px}
  .p-hd em{font-size:9px;letter-spacing:1.8px;color:#3f6b92;font-style:normal;margin-left:auto}
  .chart{flex:1;min-height:0;width:100%}
  .senti-wrap{position:relative;flex:1;min-height:0}
  .senti-wrap .chart{position:absolute;inset:0}
  .senti-mid{position:absolute;left:34%;top:52%;transform:translate(-50%,-50%);text-align:center;pointer-events:none}
  .senti-mid b{display:block;font-size:27px;font-weight:700;color:#f2fbff;font-variant-numeric:tabular-nums;
    text-shadow:0 0 22px rgba(34,211,238,0.45);letter-spacing:1px}
  .senti-mid span{display:block;margin-top:5px;font-size:11px;letter-spacing:2px;color:#6f9dc4}
  .senti-legend{position:absolute;right:10px;top:50%;transform:translateY(-50%);width:150px;
    display:flex;flex-direction:column;gap:14px}
  .senti-legend .li{display:flex;align-items:baseline;gap:8px;font-size:12px;color:#bcd8ee}
  .senti-legend .dot{width:8px;height:8px;border-radius:2px;flex:none;transform:translateY(-1px)}
  .senti-legend .nm{flex:1;letter-spacing:1px}
  .senti-legend .pc{font-size:15px;font-weight:700;color:#eaf7ff;font-variant-numeric:tabular-nums}
  .senti-legend .ct{display:block;font-size:10px;color:#5f88b0;margin-top:2px;letter-spacing:.5px}
  .foot{position:absolute;left:34px;right:34px;bottom:16px;display:flex;justify-content:space-between;
    font-size:10.5px;letter-spacing:1px;color:#3c668c}
  .foot b{color:#6f9dc4;font-weight:500}
</style>
</head>
<body>
<div id="stage"><div id="screen">
  <header>
    <div class="brand"><div class="mark"></div>
      <div><b>CHAT ANALYTICS</b><span>DIFY WORKFLOW · NLP PIPELINE</span></div>
    </div>
    <div class="title"><h1>用户情感分析大屏</h1><p>USER SENTIMENT &amp; CONVERSATION INSIGHT</p></div>
    <div class="hright"><div class="clock" id="clock">--:--:--</div><div class="date" id="date"></div></div>
  </header>

  <section class="kpis">
    <div class="kpi"><div class="lbl">消息总量</div><div class="val" data-num="__TOTAL_RAW__">0<i>条</i></div><div class="en">TOTAL MESSAGES</div></div>
    <div class="kpi"><div class="lbl">覆盖天数</div><div class="val" data-num="__DAYS__">0<i>天</i></div><div class="en">ACTIVE DAYS</div></div>
    <div class="kpi"><div class="lbl">日均消息</div><div class="val" data-num="__DAILY__">0<i>条</i></div><div class="en">DAILY AVERAGE</div></div>
    <div class="kpi"><div class="lbl">峰值时段</div><div class="val">__PEAK_HOUR__<i>__PEAK_VALUE__ 条</i></div><div class="en">PEAK HOUR</div></div>
    <div class="kpi"><div class="lbl">负面情绪占比</div><div class="val" data-num="__NEG_RATE__" data-dec="1">0<i>%</i></div><div class="en">NEGATIVE RATIO</div></div>
    <div class="kpi"><div class="lbl">平均情感得分</div><div class="val" data-num="__AVG_SCORE__" data-dec="3">0</div><div class="en">AVG SENTIMENT</div></div>
  </section>

  <div class="grid">
    <div class="col">
      <section class="panel" style="animation-delay:.05s">
        <div class="p-hd"><i></i><h3>各月聊天趋势</h3><em>MONTHLY VOLUME</em></div>
        <div class="chart" id="c-month"></div>
      </section>
      <section class="panel" style="animation-delay:.15s">
        <div class="p-hd"><i></i><h3>24 小时活跃分布</h3><em>HOURLY ACTIVITY</em></div>
        <div class="chart" id="c-hour"></div>
      </section>
    </div>

    <div class="col">
      <section class="panel" style="animation-delay:.1s">
        <div class="p-hd"><i></i><h3>聊天内容高频词</h3><em>TOP 100 KEYWORDS</em></div>
        <div class="chart" id="c-words"></div>
      </section>
      <section class="panel" style="animation-delay:.2s">
        <div class="p-hd"><i></i><h3>各主题负面情绪占比</h3><em>NEGATIVE RATE BY TOPIC</em></div>
        <div class="chart" id="c-topic"></div>
      </section>
    </div>

    <div class="col">
      <section class="panel" style="animation-delay:.08s">
        <div class="p-hd"><i></i><h3>用户情感构成</h3><em>SENTIMENT MIX</em></div>
        <div class="senti-wrap">
          <div class="chart" id="c-senti"></div>
          <div class="senti-mid"><b>__SENTI_TOTAL__</b><span>情感样本总量</span></div>
          <div class="senti-legend">__SENTI_LEGEND__</div>
        </div>
      </section>
      <section class="panel" style="animation-delay:.18s">
        <div class="p-hd"><i></i><h3>周内 × 时段 消息热力</h3><em>WEEKDAY × HOUR</em></div>
        <div class="chart" id="c-heat"></div>
      </section>
    </div>
  </div>

  <div class="foot">
    <div>数据口径：<b>__RANGE__</b> · 共 <b>__TOTAL__</b> 条会话记录 · 情感判定阈值 0.4 / 0.6（SnowNLP）</div>
    <div>主题口径：关键词规则归类 · 图表引擎 pyecharts + ECharts 5</div>
  </div>
</div></div>

<script id="chart-data" type="application/json">__CHARTS__</script>
<script src="vendor/echarts.min.js"></script>
<script src="vendor/echarts-wordcloud.min.js"></script>
<script>
function revive(k, v){
  if (typeof v === 'string' && /^\s*(function\s*\(|new\s+echarts\.)/.test(v)) {
    try { return (0, eval)('(' + v + ')'); } catch(e) { return v; }
  }
  return v;
}
const CHARTS = JSON.parse(document.getElementById('chart-data').textContent, revive);

function fit(){
  const s = Math.min(window.innerWidth/1920, window.innerHeight/1080);
  document.getElementById('screen').style.transform = 'scale('+s+')';
}
window.addEventListener('resize', fit); fit();

const insts = [];
function mount(id, option){
  const el = document.getElementById(id);
  if(!el || !option) return;
  const ins = echarts.init(el, null, {renderer:'canvas'});
  ins.setOption(option);
  insts.push(ins);
}
Object.keys(CHARTS).forEach(k => mount(k, CHARTS[k]));

function clock(){
  const d = new Date();
  const p = n => String(n).padStart(2,'0');
  document.getElementById('clock').textContent = p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds());
  const wk = ['周日','周一','周二','周三','周四','周五','周六'][d.getDay()];
  document.getElementById('date').textContent = d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'  '+wk;
}
clock(); setInterval(clock, 1000);

function countUp(el){
  const target = parseFloat(el.dataset.num || '0');
  const dec = parseInt(el.dataset.dec || '0', 10);
  const unit = el.querySelector('i');
  const unitHTML = unit ? unit.outerHTML : '';
  const t0 = performance.now(), dur = 1300;
  function step(t){
    const k = Math.min(1, (t - t0)/dur);
    const e = 1 - Math.pow(1 - k, 3);
    const v = target * e;
    const txt = dec ? v.toFixed(dec) : Math.round(v).toLocaleString('en-US');
    el.innerHTML = txt + unitHTML;
    if(k < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
if (location.hash === '#static') {
  document.getElementById('screen').classList.add('static');
  document.querySelectorAll('.kpi .val[data-num]').forEach(el => {
    const dec = parseInt(el.dataset.dec || '0', 10);
    const unit = el.querySelector('i');
    const unitHTML = unit ? unit.outerHTML : '';
    const v = parseFloat(el.dataset.num || '0');
    el.innerHTML = (dec ? v.toFixed(dec) : v.toLocaleString('en-US')) + unitHTML;
  });
} else {
  document.querySelectorAll('.kpi .val[data-num]').forEach(countUp);
}
</script>
</body>
</html>
"""


def senti_legend(m):
    total = m["senti_total"] or 1
    rows = []
    for k in ["负面", "中性", "正面"]:
        v = m["senti"].get(k, 0)
        rows.append(
            f'<div class="li"><span class="dot" style="background:{SENTI_COLOR[k]};'
            f'box-shadow:0 0 10px {SENTI_COLOR[k]}"></span>'
            f'<span class="nm">{k}</span><span class="pc">{v / total * 100:.1f}%'
            f'<span class="ct">{v:,} 条</span></span></div>'
        )
    return "".join(rows)


def render(m, charts):
    html = TPL
    repl = {
        "__TOTAL__": f"{m['total']:,}",
        "__TOTAL_RAW__": str(m['total']),
        "__DAYS__": f"{m['days']:,}",
        "__DAILY__": f"{m['daily']:,}",
        "__PEAK_HOUR__": m["peak_hour"],
        "__PEAK_VALUE__": f"{m['peak_value']:,}",
        "__NEG_RATE__": str(m["negative_rate"]),
        "__AVG_SCORE__": str(m["avg_score"]),
        "__RANGE__": m["time_range"],
        "__SENTI_TOTAL__": f"{m['senti_total']:,}",
        "__SENTI_LEGEND__": senti_legend(m),
        "__CHARTS__": json.dumps(charts, ensure_ascii=False).replace("</", "<\\/"),
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    # 把依赖库内联进 HTML，产出可直接双击 / 上传的单文件
    for tag, path in (
        ('<script src="vendor/echarts.min.js"></script>', BASE / "vendor" / "echarts.min.js"),
        ('<script src="vendor/echarts-wordcloud.min.js"></script>', BASE / "vendor" / "echarts-wordcloud.min.js"),
    ):
        if tag in html and path.exists():
            js = path.read_text(encoding="utf-8", errors="ignore").replace("</script", "<\\/script")
            html = html.replace(tag, f"<script>{js}</script>")
    OUT.write_text(html, encoding="utf-8")
    return OUT


def main():
    t0 = time.time()
    m = load_metrics(force="--refresh" in sys.argv)
    charts = {
        "c-month": chart_month(m),
        "c-hour": chart_hour(m),
        "c-words": chart_words(m),
        "c-topic": chart_topic(m),
        "c-senti": chart_senti(m),
        "c-heat": chart_heat(m),
    }
    out = render(m, charts)
    print(f"消息总量 {m['total']:,} · 覆盖 {m['days']} 天 · 负面 {m['negative_rate']}% · 峰值 {m['peak_hour']}")
    print(f"已生成 {out}  ({time.time() - t0:.1f}s, {out.stat().st_size/1024:.0f} KB)")
    if "--open" in sys.argv:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
