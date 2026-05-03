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
    """【穴場分析用】1位のスコアとランクイン総数を取得"""
    url = f"https://www.showroom-live.com/api/regular_gift_ranking/{g_id}"
    # ランクインルーム数を知るため count:100 で取得
    params = {'ymd': ymd, 'period': period, 'page': 1, 'count': 100}
    detail = fetch_json(url, params)
    if not detail: return None
    
    ranking = detail.get('ranking_list', [])
    unit_point = points_map.get(g_id, 0)
    top_score = ranking[0]['score'] if ranking else 0
    total_rooms = len(ranking)
    
    # 1位になるための最小コスト (現在1位の個数 + 1) * 単価
    cost_to_no1 = (top_score + 1) * unit_point
    
    return {
        "name": detail.get('gift_name'),
        "point": unit_point,
        "img": detail.get('gift_image', ''),
        "top_score": top_score,
        "cost": cost_to_no1,
        "total_ranked": total_rooms,
        "id": g_id
    }

# --- メイン UI ---
st.markdown(
    "<h1 style='font-size:28px; text-align:left; color:#1f2937;'>🎤 SHOWROOM ギフトランキング・ダッシュボード</h1>",
    unsafe_allow_html=True
)

with st.sidebar:
    mode = st.radio("表示モード", ["ルーム分析", "穴場ギフト発掘"], index=0)
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
    is_authorized = (auth_key == "mksp") or (room_id_input in get_allowed_rooms())

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

        # 共通でマスター取得
        with st.spinner('ギフト情報を取得中...'):
            master = get_gift_master()
            points_map = get_room_gift_points(room_id_input)

        if mode == "ルーム分析":
            with st.spinner(f'{target_label}のデータを確認中...'):
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
                    summary_df.columns = ["順位", "ギフト名", "ポイント単価", "獲得数", "上の順位まで", "下の順位まで"]
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    st.divider()
                    for item in results:
                        with st.container():
                            col1, col2, col3 = st.columns([1, 4, 2])
                            with col1: st.image(item['img'], width=80)
                            with col2:
                                st.subheader(item['name'])
                                st.write(f"ポイント単価: **{item['point']:,}** ｜ 獲得数: **{item['score']:,} 個**")
                            with col3:
                                st.metric("順位", f"{item['rank']}位")
                                if item['up'] is not None: st.write(f"🔼 あと **{item['up']:,}** 個")
                                elif item['rank'] == 1: st.write("🏆 **現在1位**")
                                if item['down'] is not None: st.write(f"🔽 あと **{item['down']:,}** 個")
                            st.divider()
                else:
                    st.warning(f"{target_label}で100位以内に入っているギフトがありません。")

        else:
            # 穴場ギフト発掘モード
            with st.spinner('全ギフトのコスト計算中...'):
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
                anaba_results.sort(key=lambda x: x['cost'])
                
                st.success(f"✅ {target_label} の穴場ギフトランキング（1位奪取コストの低い順）")
                
                st.markdown("##### 📈 穴場ギフトランキング")
                
                # サマリーテーブル
                ana_df = pd.DataFrame(anaba_results)
                
                # ルーム数に基づいたフラグ立て
                def get_room_label(count):
                    if count == 0: return "💎 該当ルームなし"
                    if count <= 10: return "✨ 10ルーム以下"
                    if count <= 25: return "🔍 25ルーム以下"
                    return f"{count}ルーム"

                ana_df['注目度'] = ana_df['total_ranked'].apply(get_room_label)
                
                disp_df = ana_df[['注目度', 'name', 'point', 'top_score', 'cost']].copy()
                disp_df.columns = ["ランクイン数", "ギフト名", "ポイント単価", "1位の獲得数", "1位奪取必要pt"]
                st.dataframe(disp_df, use_container_width=True, hide_index=True)
                
                st.divider()
                st.subheader("🏁 穴場ギフトサーチ 全リスト")
                
                # スキャンした全ギフトを表示
                for item in anaba_results:
                    with st.container():
                        c1, c2, c3 = st.columns([1, 4, 2])
                        with c1: st.image(item['img'], width=70)
                        with c2:
                            st.markdown(f"**{item['name']}**")
                            st.caption(f"ポイント単価: {item['point']} ｜ ランクイン数: {item['total_ranked']}ルーム")
                            # st.write(f"ポイント単価: **{item['point']:,}** ｜ 獲得数: **{item['score']:,} 個**")
                            if item['total_ranked'] == 0:
                                st.write("🎁 現在、獲得しているルームはありません。")
                        with c3:
                            st.write(f"1位奪取必要pt: **{item['cost']:,} pt**")
                            if item['top_score'] > 0:
                                st.caption(f"（1位が {item['top_score']}個 獲得中）")
                            else:
                                st.caption("（1個投げれば1位）")
                    st.divider()