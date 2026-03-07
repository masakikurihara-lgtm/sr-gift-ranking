import streamlit as st
import requests
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
    """全ページのギフト一覧を正確に取得"""
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
    g_id = g_data['gift_id']
    g_name = g_data.get('gift_name', '不明なギフト')
    g_img = g_data['gift_image']
    
    detail_url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': today, 'period': period_type, 'page': 1, 'count': 100}
    detail = fetch_json(detail_url, params)
    
    if not detail or 'ranking_list' not in detail:
        return None
    
    ranking = detail['ranking_list']
    my_idx = next((i for i, r in enumerate(ranking) if r['room']['room_id'] == int(room_id)), None)
    
    if my_idx is not None:
        me = ranking[my_idx]
        my_score = me['score']
        my_rank = me['rank']
        
        status = {
            "original_index": original_index,
            "icon": g_img,
            "name": g_name,
            "rank": my_rank,
            "score": my_score,
            "diff_up": None,
            "diff_down": None,
            "is_top_tie": False # 同着1位判定用
        }
        
        # 上の順位との差（自分よりスコアが「高い」人を探す）
        # 単に my_idx > 0 ではなく、スコアの差があるかを見る
        higher_person = next((r for r in ranking if r['score'] > my_score), None)
        if higher_person:
            status["diff_up"] = higher_person['score'] - my_score + 1
        elif my_rank == 1:
            status["is_top_tie"] = True
            
        # 下の順位との差（自分よりスコアが「低い」人を探す）
        lower_person = next((r for r in ranking if r['score'] < my_score), None)
        if lower_person:
            status["diff_down"] = my_score - lower_person['score']
        else:
            # 自分の下に人はいるが全員同スコアの場合
            if len(ranking) > my_idx + 1:
                status["diff_down"] = 0 
                
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
    with st.spinner('全ギフトリスト（137件）を取得中...'):
        gift_list = get_all_gift_list()
    
    if gift_list:
        my_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_gift, g, target_room, period_map[period], today, i): i for i, g in enumerate(gift_list)}
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res: my_results.append(res)
                progress_bar.progress((i + 1) / len(gift_list))
                status_text.text(f"解析中... {i+1} / {len(gift_list)}")
        
        status_text.empty()
        progress_bar.empty()

        if my_results:
            # 公式一覧と同じ並び順でソート
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
                        
                        # 1位かつ自分より高いスコアがいない場合
                        if item['rank'] == 1 and item['diff_up'] is None:
                            st.write("🏆 **現在1位です！**")
                        elif item['diff_up'] is not None:
                            st.write(f"🔼 **上の順位**まであと **{item['diff_up']:,}** 個")
                        
                        # 下の順位との差
                        if item['diff_down'] is not None:
                            if item['diff_down'] == 0:
                                st.write("🔽 **下の順位**と同着です")
                            else:
                                st.write(f"🔽 **下の順位**まであと **{item['diff_down']:,}** 個")
                    st.divider()
        else:
            st.warning("ランクインしているギフトが見つかりませんでした。")