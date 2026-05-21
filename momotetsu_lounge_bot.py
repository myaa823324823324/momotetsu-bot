import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import threading
import os
import json
import matplotlib
# グラフを画面なしの環境（Render）で安全に生成するための設定
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
from datetime import datetime

# ==========================================
# 1. ボットとFlaskの初期設定
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Momotetsu Bot is running!"

def run_flask():
    # ポートのぶつかり合いを避けるため、Flaskは8080番で起動
    app.run(host='0.0.0.0', port=8080)

# ボットの権限設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MomotetsuBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # スラッシュコマンドをDiscordに登録
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")

bot = MomotetsuBot()

# ==========================================
# 2. データの読み書きシステム（永続保存用）
# ==========================================
DATA_FILE = "momotetsu_data.json"

def load_data():
    """データをファイルから読み込む"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # 初期データ構造
    return {"players": {}, "matches": []}

def save_data(data):
    """データをファイルに書き込む"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ==========================================
# 3. 4大コマンドの実装
# ==========================================

# ----- コマンド①：【管理者用】試合結果の入力 -----
@bot.tree.command(name="result", description="【管理者用】桃鉄の対戦結果を入力してレートを更新します")
@app_commands.describe(
    p1="1位のプレイヤー", p1_goals="1位のゴール数",
    p2="2位のプレイヤー", p2_goals="2位のゴール数",
    p3="3位のプレイヤー", p3_goals="3位のゴール数",
    p4="4位のプレイヤー", p4_goals="4位のゴール数"
)
async def result(
    interaction: discord.Interaction, 
    p1: discord.Member, p1_goals: int,
    p2: discord.Member, p2_goals: int,
    p3: discord.Member, p3_goals: int,
    p4: discord.Member, p4_goals: int
):
    # 管理者権限チェック
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    players = [p1, p2, p3, p4]
    goals = [p1_goals, p2_goals, p3_goals, p4_goals]
    total_goals = sum(goals)
    
    # 資産ポイント（ベース）
    base_points = [60, 20, -20, -60]
    
    # 1. プレイヤーの現在のレートを取得（未登録なら1500からスタート）
    old_rates = []
    for p in players:
        p_id = str(p.id)
        if p_id not in data["players"]:
            data["players"][p_id] = {"name": p.display_name, "rate": 1500, "history": [1500]}
        old_rates.append(data["players"][p_id]["rate"])
        
    # 2. 部屋の平均レートを計算
    avg_rate = sum(old_rates) / 4
    
    # 3. 各プレイヤーのレート変動を新数式で計算
    rate_changes = []
    new_rates = []
    for i in range(4):
        p_id = str(players[i].id)
        my_rate = old_rates[i]
        my_goals = goals[i]
        
        # ⭐ Kami8さんの完全ゼロサム対応 新・桃鉄イロレーティング数式
        change = base_points[i] + (4 * my_goals - total_goals) + ((avg_rate - my_rate) / 20)
        change = round(change, 1) # 小数点第1位までに丸める
        
        rate_changes.append(change)
        
        # データの更新
        data["players"][p_id]["rate"] = round(my_rate + change, 1)
        data["players"][p_id]["name"] = players[i].display_name
        data["players"][p_id]["history"].append(data["players"][p_id]["rate"])
        new_rates.append(data["players"][p_id]["rate"])

    # 4. 試合IDを生成して履歴に保存（直近10試合の修正用）
    match_id = len(data["matches"]) + 1
    match_record = {
        "match_id": match_id,
        "date": datetime.now().strftime("%m/%d %H:%M"),
        "details": [
            {"id": str(p1.id), "name": p1.display_name, "change": rate_changes[0], "goals": p1_goals, "rank": 1},
            {"id": str(p2.id), "name": p2.display_name, "change": rate_changes[1], "goals": p2_goals, "rank": 2},
            {"id": str(p3.id), "name": p3.display_name, "change": rate_changes[2], "goals": p3_goals, "rank": 3},
            {"id": str(p4.id), "name": p4.display_name, "change": rate_changes[3], "goals": p4_goals, "rank": 4}
        ]
    }
    data["matches"].append(match_record)
    save_data(data)

    # 結果を綺麗にEmbed（埋め込み）で出力
    embed = discord.Embed(title=f"🎲 桃鉄対戦結果 (試合ID: {match_id})", color=0x3498db)
    embed.description = f"**部屋の平均レート:** {round(avg_rate, 1)}\n**総ゴール数:** {total_goals}回"
    
    medals = ["🥇 1位", "🥈 2位", "🥉 3位", "👎 4位"]
    for i in range(4):
        sign = "+" if rate_changes[i] >= 0 else ""
        embed.add_field(
            name=f"{medals[i]}: {players[i].display_name}",
            value=f"ゴール: {goals[i]}回\nレート: {old_rates[i]} ➔ **{new_rates[i]}** ({sign}{rate_changes[i]})",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)


# ----- コマンド②：【全員用】グラフ付き詳細ステータス確認 -----
@bot.tree.command(name="rate", description="指定したメンバー（または自分）の詳細戦績とレート推移グラフを表示します")
@app_commands.describe(member="戦績を見たいメンバー（省略すると自分）")
async def rate(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    user_id = str(target.id)
    data = load_data()

    # 登録がない場合
    if user_id not in data["players"] or len(data["players"][user_id]["history"]) <= 1:
        await interaction.response.send_message(f"🔍 {target.display_name} さんの対戦データはまだ登録されていません。（初期値: 1500）", ephemeral=False)
        return

    p_data = data["players"][user_id]
    current_rate = p_data["rate"]
    history = p_data["history"]
    match_count = len(history) - 1 # 初期値(1500)の分を引く

    # 1. 全体の中で何番目のRankか計算
    all_players = sorted(data["players"].items(), key=lambda x: x[1]["rate"], reverse=True)
    rank = 1
    for item_id, item_data in all_players:
        if item_id == user_id:
            break
        rank += 1
    total_players = len(data["players"])

    # 2. 平均獲得ポイントの計算
    total_change = current_rate - 1500
    avg_gain = round(total_change / match_count, 2)
    sign = "+" if avg_gain >= 0 else ""

    # 先にテキストメッセージを送信（応答待ち対策）
    await interaction.response.defer()

    # 3. matplotlibで折れ線グラフを自動生成
    plt.figure(figsize=(6, 3.5))
    plt.plot(history, marker='o', color='#3498db', linewidth=2, markersize=5)
    plt.title(f"{target.display_name} - Rate History", fontsize=12)
    plt.xlabel("Matches", fontsize=10)
    plt.ylabel("Rating", fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    # グラフ画像をバイナリデータとしてメモリに保存
    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=150)
    img_buf.seek(0)
    plt.close()

    # Embedと画像をセットにして送信
    file = discord.File(img_buf, filename="rate_history.png")
    embed = discord.Embed(title=f"📊 {target.display_name} さんの個人戦績", color=0x2ecc71)
    embed.add_field(name="🏆 現在の順位", value=f"`{rank}位` / {total_players}人中", inline=True)
    embed.add_field(name="⭐ 現在のレート", value=f"`{current_rate}`", inline=True)
    embed.add_field(name="🎮 合計試合回数", value=f"`{match_count}回`", inline=True)
    embed.add_field(name="📈 平均獲得ポイント", value=f"`{sign}{avg_gain} pt` / 試合", inline=False)
    embed.set_image(url="attachment://rate_history.png")

    await interaction.followup.send(embed=embed, file=file)


# ----- コマンド③：【管理者用】全体のレートランキング表 -----
@bot.tree.command(name="ranking", description="【管理者専用】サーバー全体のレートランキングを表示します")
async def ranking(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    if not data["players"]:
        await interaction.response.send_message("📭 まだ登録されているデータがありません。", ephemeral=True)
        return

    sorted_players = sorted(data["players"].items(), key=lambda x: x[1]["rate"], reverse=True)
    
    embed = discord.Embed(title="🏆 桃鉄ラウンジ レートランキング", color=0xf1c40f)
    rank_text = ""
    
    for i, (u_id, u_data) in enumerate(sorted_players, 1):
        matches = len(u_data.get("history", [1500])) - 1
        rank_text += f"**{i}位**: {u_data['name']} (`{u_data['rate']}`) - {matches}戦\n"
        if i >= 20: # 最大20人まで表示
            rank_text += "...以降は省略..."
            break

    embed.description = rank_text
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ----- コマンド④：【管理者用】直近10試合から選んで削除するセレクトメニュー -----
class CancelSelect(discord.ui.Select):
    def __init__(self, matches):
        options = []
        # 直近の試合から最大10件をメニュー化
        for m in reversed(matches[-10:]):
            # メニューに表示するテキストを生成
            details = m["details"]
            summary = f"ID:{m['match_id']} | 1位:{details[0]['name']} 2位:{details[1]['name']}"
            options.append(discord.SelectOption(label=summary, description=f"登録日時: {m['date']}", value=str(m["match_id"])))
            
        super().__init__(placeholder="取り消したい試合を選択してください...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
            return

        target_id = int(self.values[0])
        data = load_data()
        
        # 該当する試合を探す
        match_idx = -1
        for idx, m in enumerate(data["matches"]):
            if m["match_id"] == target_id:
                match_idx = idx
                break
                
        if match_idx == -1:
            await interaction.response.send_message("❌ 指定された試合データが見つかりませんでした。", ephemeral=True)
            return
            
        match_to_del = data["matches"][match_idx]
        
        # レートの巻き戻し処理
        for item in match_to_del["details"]:
            p_id = item["id"]
            if p_id in data["players"]:
                # 直近の履歴を1つ消す
                if len(data["players"][p_id]["history"]) > 1:
                    data["players"][p_id]["history"].pop()
                # 現在のレートを履歴の最後の値に巻き戻す
                data["players"][p_id]["rate"] = data["players"][p_id]["history"][-1]

        # 試合の履歴リストから削除
        data["matches"].pop(match_idx)
        save_data(data)
        
        await interaction.response.send_message(f"✅ 試合ID: {target_id} の結果を取り消し、全員のレートを1試合分巻き戻しました！", ephemeral=True)

class CancelView(discord.ui.View):
    def __init__(self, matches):
        super().__init__(timeout=60)
        self.add_item(CancelSelect(matches))

@bot.tree.command(name="cancel_match", description="【管理者専用】直近10試合の中から選択して結果を取り消します")
async def cancel_match(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    if not data["matches"]:
        await interaction.response.send_message("📭 取り消せる試合データがありません。", ephemeral=True)
        return

    view = CancelView(data["matches"])
    await interaction.response.send_message("🔄 **試合結果の取り消しメニュー**\n以下のリストから削除したい試合を選んでください。選択すると即座に巻き戻されます。", view=view, ephemeral=True)

# ==========================================
# 4. ボットの起動処理
# ==========================================
@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name}")

if __name__ == "__main__":
    # Flask用のスレッドを開始
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Discordボットの起動トークン
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が環境変数に設定されていません。")