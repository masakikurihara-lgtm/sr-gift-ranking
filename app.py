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

def get_all_gift_ids():
    """全ページのギフトIDと日本語名を収集"""
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

def process_gift(g_id, room_id, period_type, today, original_index):
    """個別APIを叩き、JSON内の gift_name をそのまま取得する"""
    detail_url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': today, 'period': period_type, 'page': 1, 'count': 100}
    detail = fetch_json(detail_url, params)
    
    if not detail or 'ranking_list' not in detail:
        return None
    
    # JSONからギフト名を直接取得（これが一番確実です）
    gift_name_from_json = detail.get('gift_name', '不明なギフト')
    gift_image = detail.get('gift_image', '')
    ranking = detail['ranking_list']
    
    # 自分のルームを特定
    my_entry = next((r for r in ranking if r['room']['room_id'] == int(room_id)), None)
    
    if my_entry:
        my_score = my_entry['score']
        my_rank = my_entry['rank']
        
        status = {
            "original_index": original_index,
            "icon": gift_image,
            "name": gift_name_from_json, # JSONの値をそのまま使用
            "rank": my_rank,
            "score": my_score,
            "diff_up": None,
            "diff_down": None
        }
        
        # 上の順位（自分よりスコアが高い人の中で最小のスコア）との差
        higher_scores = [r['score'] for r in ranking if r['score'] > my_score]
        if higher_scores:
            status["diff_up"] = min(higher_scores) - my_score + 1
        
        # 下の順位（自分よりスコアが低い人の中で最大のスコア）との差
        lower_scores = [r['score'] for r in ranking if r['score'] < my_score]
        if lower_scores:
            status["diff_down"] = my_score - max(lower_scores)
                
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
        gift_list = get_all_gift_ids()
    
    if gift_list:
        my_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 137件程度のAPI通信を並列化（10並列）
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(process_gift, g['gift_id'], target_room, period_map[period], today, i): i 
                for i, g in enumerate(gift_list)
            }
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res: my_results.append(res)
                progress_bar.progress((i + 1) / len(gift_list))
                status_text.text(f"解析中... {i+1} / {len(gift_list)}")
        
        status_text.empty()
        progress_bar.empty()

        if my_results:
            # 取得したギフトを元の表示順でソート
            my_results = sorted(my_results, key=lambda x: x['original_index'])
            
            for item in my_results:
                with st.container():
                    col1, col2, col3 = st.columns([1, 4, 2])
                    with col1:
                        st.image(item['icon'], width=80)
                    with col2:
                        st.subheader(item['name']) # APIの gift_name をそのまま表示
                        st.write(f"現在の個数: **{item['score']:,} 個**")
                    with col3:
                        st.metric("現在の順位", f"{item['rank']}位")
                        
                        if item['diff_up'] is not None:
                            st.write(f"🔼 **上の順位**まであと **{item['diff_up']:,}** 個")
                        elif item['rank'] == 1:
                            st.write("🏆 **現在1位です！**")
                        
                        if item['diff_down'] is not None:
                            st.write(f"🔽 **下の順位**まであと **{item['diff_down']:,}** 個")
                    st.divider()
        else:
            st.warning("100位以内にランクインしているギフトは見つかりませんでした。")