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
    """全ギフトのIDをページネーションして取得"""
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
    """個別APIのレスポンスからギフト名とランキングを抽出"""
    url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': today, 'period': period_type, 'page': 1, 'count': 100}
    detail = fetch_json(url, params)
    
    if not detail or 'ranking_list' not in detail:
        return None
    
    # 【最重要】APIが返した gift_name をそのまま取得し、一切加工しない
    raw_gift_name = detail.get('gift_name') 
    gift_image = detail.get('gift_image', '')
    ranking = detail['ranking_list']
    
    # 指定されたルームのランクイン情報を確認
    my_entry = next((r for r in ranking if r['room']['room_id'] == int(room_id)), None)
    
    if my_entry:
        my_score = my_entry['score']
        my_rank = my_entry['rank']
        
        # 必要な情報だけを詰めたクリーンな辞書を作成
        res = {
            "order": original_index,
            "img": gift_image,
            "display_name": raw_gift_name, # ここに日本語名がそのまま入ります
            "rank": my_rank,
            "score": my_score,
            "diff_up": None,
            "diff_down": None
        }
        
        # 順位差分の計算（自分よりスコアが上の最小値 / 下の最大値を探す）
        higher_scores = [r['score'] for r in ranking if r['score'] > my_score]
        if higher_scores:
            res["diff_up"] = min(higher_scores) - my_score + 1
            
        lower_scores = [r['score'] for r in ranking if r['score'] < my_score]
        if lower_scores:
            res["diff_down"] = my_score - max(lower_scores)
            
        return res
    return None

# --- UI部 ---
st.title("📊 ギフトランキング・ダッシュボード")

with st.sidebar:
    room_input = st.text_input("Room IDを入力", value="512751")
    period_label = st.radio("集計期間", ["日間", "週間", "月間"], horizontal=True)
    period_val = {"日間": 1, "週間": 2, "月間": 3}[period_label]
    update_btn = st.button("状況を更新する", type="primary")

if update_btn and room_input:
    ymd = datetime.now().strftime('%Y%m%d')
    
    with st.spinner('全ギフトをスキャン中...'):
        master_list = get_all_gift_ids()
    
    if master_list:
        results = []
        p_bar = st.progress(0)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            tasks = {
                executor.submit(process_gift, g['gift_id'], room_input, period_val, ymd, i): i 
                for i, g in enumerate(master_list)
            }
            for i, future in enumerate(as_completed(tasks)):
                data = future.result()
                if data:
                    results.append(data)
                p_bar.progress((i + 1) / len(master_list))
        
        p_bar.empty()

        if results:
            # 公式の並び順（order）でソートして表示
            results.sort(key=lambda x: x['order'])
            
            for item in results:
                with st.container():
                    c1, c2, c3 = st.columns([1, 4, 2])
                    with c1:
                        st.image(item['img'], width=80)
                    with c2:
                        # APIの値をそのまま流し込み
                        st.subheader(item['display_name'])
                        st.write(f"現在の個数: **{item['score']:,} 個**")
                    with c3:
                        st.metric("現在の順位", f"{item['rank']}位")
                        
                        if item['diff_up'] is not None:
                            st.write(f"🔼 **上の順位**まであと **{item['diff_up']:,}** 個")
                        elif item['rank'] == 1:
                            st.write("🏆 **現在1位です！**")
                        
                        if item['diff_down'] is not None:
                            st.write(f"🔽 **下の順位**まであと **{item['diff_down']:,}** 個")
                    st.divider()
        else:
            st.warning("ランクイン情報が見つかりませんでした。")