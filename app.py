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
    # ギフト一覧APIから取得した日本語名を保持
    jp_gift_name = g_data.get('gift_name', '不明なギフト')
    g_id = g_data['gift_id']
    g_img = g_data['gift_image']
    
    detail_url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': today, 'period': period_type, 'page': 1, 'count': 100}
    detail = fetch_json(detail_url, params)
    
    if not detail or 'ranking_list' not in detail:
        return None
    
    ranking = detail['ranking_list']
    # 自分のルームを特定
    my_entry = next((r for r in ranking if r['room']['room_id'] == int(room_id)), None)
    
    if my_entry:
        my_score = my_entry['score']
        my_rank = my_entry['rank']
        
        status = {
            "original_index": original_index,
            "icon": g_img,
            "name": jp_gift_name, # 固定した日本語名を使用
            "rank": my_rank,
            "score": my_score,
            "diff_up": None,
            "diff_down": None
        }
        
        # --- 「上の順位」までの個数 ---
        # 自分よりスコアが高い人たちの中で、一番スコアが低い人（＝すぐ上の順位）を探す
        higher_scores = [r['score'] for r in ranking if r['score'] > my_score]
        if higher_scores:
            target_upper_score = min(higher_scores)
            status["diff_up"] = target_upper_score - my_score + 1
        
        # --- 「下の順位」までの個数 ---
        # 自分よりスコアが低い人たちの中で、一番スコアが高い人（＝すぐ下の順位）を探す
        lower_scores = [r['score'] for r in ranking if r['score'] < my_score]
        if lower_scores:
            target_lower_score = max(lower_scores)
            status["diff_down"] = my_score - target_lower_score
                
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
    with st.spinner('ギフトリストを取得中...'):
        gift_list = get_all_gift_list()
    
    if gift_list:
        my_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 安定性を考慮し並列数を8に設定
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(process_gift, g, target_room, period_map[period], today, i): i for i, g in enumerate(gift_list)}
            for i, future in enumerate(as_completed(futures)):
                res = future.result()
                if res: my_results.append(res)
                progress_bar.progress((i + 1) / len(gift_list))
                status_text.text(f"解析中... {i+1} / {len(gift_list)}")
        
        status_text.empty()
        progress_bar.empty()

        if my_results:
            # ギフト一覧APIの並び順で表示
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
                        
                        # 上の順位への案内
                        if item['diff_up'] is not None:
                            st.write(f"🔼 **上の順位**まであと **{item['diff_up']:,}** 個")
                        elif item['rank'] == 1:
                            st.write("🏆 **現在1位です！**")
                        else:
                            # 1位ではないが、自分より上のスコアが100位以内にいない場合
                            st.write("🔼 **上の順位**は100位圏外です")
                        
                        # 下の順位との差
                        if item['diff_down'] is not None:
                            st.write(f"🔽 **下の順位**まであと **{item['diff_down']:,}** 個")
                        else:
                            st.write("🔽 **下の順位**は100位圏外です")
                    st.divider()
        else:
            st.warning("ランクインしているギフトが見つかりませんでした。")