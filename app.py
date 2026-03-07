import streamlit as st
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ページ設定
st.set_page_config(page_title="SHOWROOMギフトランキング", layout="wide")

def fetch_json(url, params=None):
    try:
        # 日本語のレスポンスを強制するため、言語設定ヘッダーを追加
        headers = {"Accept-Language": "ja"}
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        return res.json()
    except:
        return None

def get_gift_master():
    """全ギフトのIDを収集"""
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

def get_gift_status(g_id, room_id, period, ymd, order):
    """個別APIからギフト情報を取得"""
    url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': ymd, 'period': period, 'page': 1, 'count': 100}
    detail = fetch_json(url, params)
    
    if not detail or 'ranking_list' not in detail:
        return None
    
    raw_name = detail.get('gift_name') 
    img_url = detail.get('gift_image', '')
    ranking = detail['ranking_list']
    
    # 自ルームの特定
    me = next((r for r in ranking if r['room']['room_id'] == int(room_id)), None)
    
    if me:
        score = me['score']
        rank = me['rank']
        
        higher = [r['score'] for r in ranking if r['score'] > score]
        diff_up = (min(higher) - score + 1) if higher else None
        
        lower = [r['score'] for r in ranking if r['score'] < score]
        diff_down = (score - max(lower)) if lower else None

        return {
            "order": order,
            "name": raw_name,
            "img": img_url,
            "rank": rank,
            "score": score,
            "up": diff_up,
            "down": diff_down
        }
    return None

# --- メイン UI ---
st.title("📊 ギフトランキング・ダッシュボード")

with st.sidebar:
    room_id = st.text_input("Room ID", value="512751")
    period_txt = st.radio("期間", ["日間", "週間", "月間"], horizontal=True)
    period_map = {"日間": 1, "週間": 2, "月間": 3}
    run = st.button("状況を更新する", type="primary")

if run and room_id:
    # --- ymdパラメータの計算ロジック修正 ---
    now = datetime.now()
    p_val = period_map[period_txt]
    
    if p_val == 1: # 日間
        target_ymd = now.strftime('%Y%m%d')
    elif p_val == 2: # 週間 (今週の月曜日)
        monday = now - timedelta(days=now.weekday())
        target_ymd = monday.strftime('%Y%m%d')
    elif p_val == 3: # 月間 (今月の1日)
        first_day = now.replace(day=1)
        target_ymd = first_day.strftime('%Y%m%d')
    # ---------------------------------------
    
    with st.spinner(f'{period_txt}のギフト一覧を取得中...'):
        master = get_gift_master()
    
    if master:
        results = []
        bar = st.progress(0)
        
        with ThreadPoolExecutor(max_workers=10) as exe:
            futures = {
                exe.submit(get_gift_status, g['gift_id'], room_id, p_val, target_ymd, i): i 
                for i, g in enumerate(master)
            }
            for i, f in enumerate(as_completed(futures)):
                res = f.result()
                if res:
                    results.append(res)
                bar.progress((i + 1) / len(master))
        
        bar.empty()

        if results:
            results.sort(key=lambda x: x['order'])
            
            for item in results:
                with st.container():
                    col1, col2, col3 = st.columns([1, 4, 2])
                    with col1:
                        st.image(item['img'], width=80)
                    with col2:
                        st.subheader(item['name'])
                        st.write(f"現在の個数: **{item['score']:,} 個**")
                    with col3:
                        st.metric("現在の順位", f"{item['rank']}位")
                        
                        if item['up'] is not None:
                            st.write(f"🔼 **上の順位**まであと **{item['up']:,}** 個")
                        elif item['rank'] == 1:
                            st.write("🏆 **現在1位です！**")
                        
                        if item['down'] is not None:
                            st.write(f"🔽 **下の順位**まであと **{item['down']:,}** 個")
                    st.divider()
        else:
            st.warning(f"{period_txt}ランキングで100位以内に入っているギフトがありません。")