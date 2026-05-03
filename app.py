import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil.relativedelta import relativedelta

# ページ設定
st.set_page_config(page_title="SHOWROOM ギフトランキング・ダッシュボード", layout="wide")

ROOM_LIST_URL = "https://mksoul-pro.com/showroom/file/room_list.csv"

def fetch_json(url, params=None):
    try:
        headers = {"Accept-Language": "ja"}
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        return res.json()
    except:
        return None

def get_allowed_rooms():
    try:
        df_rooms = pd.read_csv(ROOM_LIST_URL)
        return df_rooms.iloc[:, 0].astype(str).tolist()
    except:
        return []

def get_gift_master():
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

def get_room_gift_points(room_id):
    url = f"https://www.showroom-live.com/api/live/gift_list?room_id={room_id}"
    data = fetch_json(url)
    points_map = {}
    if data:
        for category_list in data.values():
            if isinstance(category_list, list):
                for gift in category_list:
                    g_id = gift.get("gift_id")
                    pt = gift.get("point")
                    if g_id is not None and pt is not None:
                        points_map[g_id] = pt
    return points_map

def get_gift_status(g_id, room_id, period, ymd, order, points_map):
    url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': ymd, 'period': period, 'page': 1, 'count': 100}
    detail = fetch_json(url, params)
    if not detail or 'ranking_list' not in detail:
        return None
    raw_name = detail.get('gift_name') 
    img_url = detail.get('gift_image', '')
    ranking = detail['ranking_list']
    me = next((r for r in ranking if r['room']['room_id'] == int(room_id)), None)
    if me:
        score = me['score']
        rank = me['rank']
        room_name = me['room'].get('room_name', 'Unknown')
        unit_point = points_map.get(g_id, 0)
        higher = [r['score'] for r in ranking if r['score'] > score]
        diff_up = (min(higher) - score + 1) if higher else None
        lower = [r['score'] for r in ranking if r['score'] < score]
        diff_down = (score - max(lower)) if lower else None
        return {
            "order": order, "name": raw_name, "point": unit_point, "img": img_url,
            "rank": rank, "score": score, "up": diff_up, "down": diff_down, "room_name": room_name
        }
    return None

def get_anaba_status(g_id, period, ymd, points_map):
    """【新規】1位奪取の難易度を分析"""
    url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    params = {'ymd': ymd, 'period': period, 'page': 1, 'count': 1}
    detail = fetch_json(url, params)
    if not detail: return None
    
    ranking = detail.get('ranking_list', [])
    unit_point = points_map.get(g_id, 0)
    top_score = ranking[0]['score'] if ranking else 0
    
    # 1位になるための最小コスト (現在1位の個数 + 1) * 単価
    cost_to_no1 = (top_score + 1) * unit_point
    
    return {
        "name": detail.get('gift_name'),
        "point": unit_point,
        "img": detail.get('gift_image', ''),
        "top_score": top_score,
        "cost": cost_to_no1,
        "total_ranked": len(ranking),
        "id": g_id
    }

# --- メイン UI ---
st.markdown(
    "<h1 style='font-size:28px; text-align:left; color:#1f2937;'>🎤 SHOWROOM ギフトランキング・ダッシュボード</h1>",
    unsafe_allow_html=True
)

with st.sidebar:
    # 既存の導線と分けるためのモード選択
    mode = st.radio("表示モード", ["ルーム分析", "1位狙い（穴場発掘）"], index=0)
    st.divider()
    
    room_id_input = st.text_input("Room ID", value="354607")
    auth_key = st.text_input("認証キー", type="password")
    
    col_p, col_t = st.columns(2)
    with col_p:
        period_txt = st.radio("期間", ["日間", "週間", "月間"])
    with col_t:
        target_txt = st.radio("対象", ["今回", "前回"])
        
    period_map = {"日間": 1, "週間": 2, "月間": 3}
    run = st.button("確認する", type="primary")

if run and room_id_input:
    is_authorized = False
    if auth_key == "mksp":
        is_authorized = True
    else:
        allowed_rooms = get_allowed_rooms()
        if room_id_input in allowed_rooms:
            is_authorized = True

    if not is_authorized:
        st.error("認証されていないルームIDです。")
    else:
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst)
        p_val = period_map[period_txt]
        
        if target_txt == "今回":
            calc_base = now
        else:
            if p_val == 1: calc_base = now - timedelta(days=1)
            elif p_val == 2: calc_base = now - timedelta(days=7)
            else: calc_base = now - relativedelta(months=1)

        if p_val == 1: target_ymd = calc_base.strftime('%Y%m%d')
        elif p_val == 2: target_ymd = (calc_base - timedelta(days=calc_base.weekday())).strftime('%Y%m%d')
        else: target_ymd = calc_base.replace(day=1).strftime('%Y%m%d')
        
        target_label = f"{period_txt}（{target_txt}）"

        # ルーム分析（既存機能）
        if mode == "ルーム分析":
            with st.spinner(f'{target_label}のデータを確認中...'):
                master = get_gift_master()
                points_map = get_room_gift_points(room_id_input)
            
            if master:
                results = []
                bar = st.progress(0)
                with ThreadPoolExecutor(max_workers=10) as exe:
                    futures = {exe.submit(get_gift_status, g['gift_id'], room_id_input, p_val, target_ymd, i, points_map): i for i, g in enumerate(master)}
                    for i, f in enumerate(as_completed(futures)):
                        res = f.result()
                        if res: results.append(res)
                        bar.progress((i + 1) / len(master))
                bar.empty()

                if results:
                    results.sort(key=lambda x: x['order'])
                    display_name = results[0]['room_name']
                    profile_url = f"https://www.showroom-live.com/room/profile?room_id={room_id_input}"
                    st.info(f"🔗 [**{display_name}** ({room_id_input})]({profile_url}) の{target_label}状況")
                    st.markdown("##### 📈 ランクイン状況一覧")
                    df = pd.DataFrame(results)
                    summary_df = df[["rank", "name", "point", "score", "up", "down"]].copy()
                    summary_df.columns = ["順位", "ギフト名", "ポイント", "獲得数", "上の順位まで", "下の順位まで"]
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    st.divider()
                    for item in results:
                        with st.container():
                            col1, col2, col3 = st.columns([1, 4, 2])
                            with col1: st.image(item['img'], width=80)
                            with col2:
                                st.subheader(item['name'])
                                st.write(f"ポイント: **{item['point']:,}** ｜ 獲得数: **{item['score']:,} 個**")
                            with col3:
                                st.metric("順位", f"{item['rank']}位")
                                if item['up'] is not None: st.write(f"🔼 あと **{item['up']:,}** 個")
                                elif item['rank'] == 1: st.write("🏆 **現在1位**")
                                if item['down'] is not None: st.write(f"🔽 あと **{item['down']:,}** 個")
                            st.divider()
                else:
                    st.warning(f"{target_label}で100位以内に入っているギフトがありません。")

        # 穴場発掘（新規追加機能）
        else:
            with st.spinner('全ギフトのランキング状況をスキャン中...'):
                master = get_gift_master()
                points_map = get_room_gift_points(room_id_input)
                anaba_results = []
                bar = st.progress(0)
                with ThreadPoolExecutor(max_workers=20) as exe:
                    futures = {exe.submit(get_anaba_status, g['gift_id'], p_val, target_ymd, points_map): i for i, g in enumerate(master)}
                    for i, f in enumerate(as_completed(futures)):
                        res = f.result()
                        if res: anaba_results.append(res)
                        bar.progress((i + 1) / len(master))
                bar.empty()

            if anaba_results:
                # 1位奪取コストが低い順にソート
                anaba_results.sort(key=lambda x: x['cost'])
                
                st.success(f"✅ {target_label} の穴場ギフト（1位の狙いやすさ順）")
                
                # サマリーテーブル表示
                ana_df = pd.DataFrame(anaba_results)
                ana_df['状況'] = ana_df['top_score'].apply(lambda x: "🏆 未獲得(0人)" if x == 0 else ("⭐ 少数狙い目" if x <= 3 else "👥 競合あり"))
                
                disp_df = ana_df[['状況', 'name', 'point', 'top_score', 'cost']].copy()
                disp_df.columns = ["状況", "ギフト名", "単価", "1位の獲得数", "1位奪取コスト(pt)"]
                st.dataframe(disp_df, use_container_width=True, hide_index=True)
                
                st.divider()
                st.subheader("🏁 1位奪取コスト 詳細リスト")
                for item in anaba_results[:50]: # 上位50件を表示
                    with st.container():
                        c1, c2, c3 = st.columns([1, 4, 2])
                        with c1: st.image(item['img'], width=70)
                        with c2:
                            st.markdown(f"**{item['name']}**")
                            st.caption(f"単価: {item['point']}pt / 現在の1位獲得数: {item['top_score']}個")
                        with c3:
                            if item['top_score'] == 0:
                                st.write("💎 **空席（1個で1位）**")
                                st.write(f"コスト: **{item['point']} pt**")
                            else:
                                st.write(f"コスト: **{item['cost']:,} pt**")
                                st.caption(f"あと {item['top_score']+1}個")
                    st.divider()