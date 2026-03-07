import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="SHOWROOMギフトランキング", layout="wide")

def fetch_json(url, params=None):
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        return res.json()
    except:
        return None

def get_all_gift_list():
    """全ページのギフト一覧を取得する（ページネーション対応）"""
    all_gifts = []
    page = 1
    while True:
        url = f"https://www.showroom-live.com/api/regular_gift_ranking/?page={page}"
        data = fetch_json(url)
        if not data or not data.get('regular_gift_ranking_list'):
            break
        
        all_gifts.extend(data['regular_gift_ranking_list'])
        
        if data.get('next_page') is None:
            break
        page = data['next_page']
    return all_gifts

def process_gift(g_data, room_id, period_type, today, original_index):
    """個別ランキングを解析。original_indexを持たせてソート可能にする"""
    g_id = g_data['gift_id']
    g_name = g_data['gift_name'] # API取得の日本語名
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
            "original_index": original_index,
            "icon": g_img,
            "name": g_name,
            "rank": me['rank'],
            "score": me['score'],
            "diff_up": None,
            "diff_down": None
        }
        
        # 2位以下なら上の順位との差を計算
        if my_idx > 0:
            diff = ranking[my_idx - 1]['score'] - me['score'] + 1
            if diff > 0:
                status["diff_up"] = diff
        
        # 下に誰かいたら差を計算
        if my_idx < len(ranking) - 1:
            diff = me['score'] - ranking[my_idx + 1]['score']
            status["diff_down"] = diff
            
        return status
    return None

# --- UI ---
st.title("📊 ギフトランキング・ダッシュボード")

with st.sidebar:
    target_room = st.text_input("Room IDを入力", value="512751")
    period = st.radio("集計期間", ["日間", "週間", "月間"], horizontal=True)
    period_map = {"日間": 1, "週間": 2, "月間": 3}
    start_btn = st.button("状況を更新する", type="primary")

if start_btn and target_room:
    today = datetime.now().strftime('%Y%m%d')
    
    with st.spinner('全ギフトリストを取得中...'):
        gift_list = get_all_gift_list()
    
    if gift_list:
        my_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 並列リクエスト（max_workersはサーバー負荷を見て5-10程度）
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                executor.submit(process_gift, g, target_room, period_map[period], today, i): i 
                for i, g in enumerate(gift_list)
            }
            
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res:
                    my_results.append(res)
                
                progress = (i + 1) / len(gift_list)
                progress_bar.progress(progress)
                status_text.text(f"解析中... {i+1} / {len(gift_list)}")
        
        status_text.empty()
        progress_bar.empty()

        if my_results:
            # 元のギフト一覧の並び順（original_index）でソート
            my_results = sorted(my_results, key=lambda x: x['original_index'])
            
            for item in my_results:
                with st.container():
                    col1, col2, col3 = st.columns([1, 4, 2])
                    with col1:
                        st.image(item['icon'], width=80)
                    with col2:
                        st.subheader(item['name'])
                        st.write(f"現在の個数: **{item['score']:,} 個**")
                    with col3:
                        st.metric("現在の順位", f"{item['rank']}位")
                        
                        if item['diff_up'] is not None:
                            st.write(f"🔼 **上の順位**まであと **{item['diff_up']:,}** 個")
                        elif item['rank'] == 1:
                            st.write("🏆 **現在1位です！**")
                        
                        if item['diff_down'] is not None:
                            # スコア差が0なら同着と表示
                            if item['diff_down'] == 0:
                                st.write("🔽 **下の順位**と同着です")
                            else:
                                st.write(f"🔽 **下の順位**まであと **{item['diff_down']:,}** 個")
                    st.divider()
        else:
            st.warning("ランクインしているギフトが見つかりませんでした。")