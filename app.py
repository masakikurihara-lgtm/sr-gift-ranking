import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# レイアウト設定
st.set_page_config(page_title="SHOWROOMギフト状況一覧", layout="wide")

def fetch_json(url, params=None):
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        return res.json()
    except:
        return None

def get_my_status(room_id, period_type):
    # 1. 全ギフトの基本情報を取得
    list_url = "https://www.showroom-live.com/api/regular_gift_ranking/?page=1"
    base_data = fetch_json(list_url)
    if not base_data: return []

    today = datetime.now().strftime('%Y%m%d')
    my_results = []

    # 2. 各ギフトごとに詳細ランキングをチェック
    for g in base_data.get('regular_gift_ranking_list', []):
        g_id = g['gift_id']
        g_name = g['gift_name']
        g_img = g['gift_image']
        
        detail_url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
        params = {'ymd': today, 'period': period_type, 'page': 1, 'count': 100}
        detail = fetch_json(detail_url, params)
        
        if not detail: continue
        
        ranking = detail.get('ranking_list', [])
        
        # 自分の順位を探す
        my_idx = next((i for i, r in enumerate(ranking) if r['room']['room_id'] == int(room_id)), None)
        
        if my_idx is not None:
            me = ranking[my_idx]
            status = {
                "icon": g_img,
                "name": g_name,
                "rank": me['rank'],
                "score": me['score'],
                "diff_up": 0,
                "diff_down": 0
            }
            # ランクアップ（1つ上）との差
            if my_idx > 0:
                status["diff_up"] = ranking[my_idx - 1]['score'] - me['score'] + 1
            # ランク維持（1つ下）との差
            if my_idx < len(ranking) - 1:
                status["diff_down"] = me['score'] - ranking[my_idx + 1]['score']
            
            my_results.append(status)
            
    return my_results

# --- UI部 ---
st.title("📊 ギフトランキング・ダッシュボード")

with st.sidebar:
    target_room = st.text_input("Room IDを入力", placeholder="例: 123456")
    period = st.radio("集計期間", ["日間", "週間", "月間"], horizontal=True)
    period_map = {"日間": 1, "週間": 2, "月間": 3}
    start_btn = st.button("状況を更新する", type="primary")

if start_btn and target_room:
    with st.spinner('各ギフトのランキングを解析中...'):
        data = get_my_status(target_room, period_map[period])
        
    if data:
        # スマホでも見やすいカード形式で表示
        for item in data:
            with st.container():
                col1, col2, col3 = st.columns([1, 4, 2])
                with col1:
                    st.image(item['icon'], width=60)
                with col2:
                    st.subheader(f"{item['name']}")
                    st.write(f"現在のスコア: **{item['score']:,}**")
                with col3:
                    st.metric("現在の順位", f"{item['rank']}位")
                    if item['diff_up'] > 0:
                        st.caption(f"🔼 次の順位まであと **{item['diff_up']:,}** 個")
                    if item['diff_down'] > 0:
                        st.caption(f"🔽 下の順位まであと **{item['diff_down']:,}** 個")
                st.divider()
    else:
        st.warning("100位以内にランクインしているギフトが見つかりませんでした。")