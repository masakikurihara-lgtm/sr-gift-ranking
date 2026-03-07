import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# レイアウト設定
st.set_page_config(page_title="SHOWROOMギフト状況一覧", layout="wide")

def fetch_json(url, params=None):
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        return res.json()
    except:
        return None

def process_gift(g_data, room_id, period_type, today):
    """各ギフトのランキングを個別に取得・解析する関数（並列実行用）"""
    g_id = g_data['gift_id']
    g_name = g_data['gift_name'] # 日本語名
    g_img = g_data['gift_image']
    
    detail_url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': today, 'period': period_type, 'page': 1, 'count': 100}
    detail = fetch_json(detail_url, params)
    
    if not detail:
        return None
    
    ranking = detail.get('ranking_list', [])
    my_idx = next((i for i, r in enumerate(ranking) if r['room']['room_id'] == int(room_id)), None)
    
    if my_idx is not None:
        me = ranking[my_idx]
        status = {
            "icon": g_img,
            "name": g_name,
            "rank": me['rank'],
            "score": me['score'],
            "diff_up": None,
            "diff_down": None
        }
        
        # 上の順位（rank-1）との差：自分が2位以下の時
        if my_idx > 0:
            status["diff_up"] = ranking[my_idx - 1]['score'] - me['score'] + 1
        
        # 下の順位（rank+1）との差：自分の下に誰かいる時
        if my_idx < len(ranking) - 1:
            status["diff_down"] = me['score'] - ranking[my_idx + 1]['score']
            
        return status
    return None

def get_my_status_parallel(room_id, period_type):
    # 1. 全ギフトの基本情報を取得
    list_url = "https://www.showroom-live.com/api/regular_gift_ranking/?page=1"
    base_data = fetch_json(list_url)
    if not base_data: return []

    today = datetime.now().strftime('%Y%m%d')
    gift_list = base_data.get('regular_gift_ranking_list', [])
    my_results = []

    # 2. 並列実行とプログレスバーの管理
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_gift, g, room_id, period_type, today): g for g in gift_list}
        
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            if result:
                my_results.append(result)
            
            # 進捗を更新
            progress = (i + 1) / len(gift_list)
            progress_bar.progress(progress)
            status_text.text(f"解析中... ({i+1}/{len(gift_list)} アイテム完了)")

    status_text.empty()
    progress_bar.empty()
    return my_results

# --- UI部 ---
st.title("📊 ギフトランキング・ダッシュボード")

with st.sidebar:
    target_room = st.text_input("Room IDを入力", placeholder="例: 123456", value="512751")
    period = st.radio("集計期間", ["日間", "週間", "月間"], horizontal=True)
    period_map = {"日間": 1, "週間": 2, "月間": 3}
    start_btn = st.button("状況を更新する", type="primary")

if start_btn and target_room:
    data = get_my_status_parallel(target_room, period_map[period])
    
    if data:
        # 順位順にソートして表示
        data = sorted(data, key=lambda x: x['rank'])
        
        for item in data:
            with st.container():
                col1, col2, col3 = st.columns([1, 4, 2])
                with col1:
                    st.image(item['icon'], width=80)
                with col2:
                    # 日本語名を表示
                    st.subheader(item['name'])
                    # 「現在の個数」表記に変更
                    st.write(f"現在の個数: **{item['score']:,} 個**")
                with col3:
                    st.metric("現在の順位", f"{item['rank']}位")
                    
                    # 上の順位（2位以下の時に表示）
                    if item['diff_up'] is not None:
                        st.write(f"🔼 **上の順位**まであと **{item['diff_up']:,}** 個")
                    
                    # 下の順位（ランク維持の指標）
                    if item['diff_down'] is not None:
                        st.write(f"🔽 **下の順位**まであと **{item['diff_down']:,}** 個")
                st.divider()
    else:
        st.warning("100位以内にランクインしているギフトが見つかりませんでした。")