import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import threading
import os
import json
import matplotlib
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
    app.run(host='0.0.0.0', port=8080)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MomotetsuBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました！")

bot = MomotetsuBot()

# ==========================================
# 2. データの読み書きシステム（より確実に改良）
# ==========================================
DATA_FILE = "momotetsu_data.json"

def load_data():
    """データを確実にファイルから読み込む"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except Exception as e:
            print(f"データ読み込みエラー: {e}")
    return {"players": {}, "matches": []}

def save_data(data):
    """データを確実にファイルへ書き込む"""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno()) # ディスクに完全に書き込みを強制
    except Exception as e:
        print(f"データ保存エラー: {e}")

# ==========================================
# 3. コマンドの実装
# ==========================================

# ----- コマンド①：試合結果の入力 -----
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
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    # 最新データを読み込み
    data = load_data()
    
    players = [p1, p2, p3, p4]
    goals = [p1_goals, p2_goals, p3_goals, p4_goals]
    total_goals = sum(goals)
    base_points = [60, 20, -20, -60]
    
    old_rates = []
    for p in players:
        p_id = str(p.id)
        if p_id not in data["players"]:
            data["players"][p_id] = {"name": p.display_name, "rate": 1500, "history": [1500]}
        old_rates.append(data["players"][p_id]["rate"])
        
    avg_rate = sum(old_rates) / 4
    
    rate_changes = []
    new_rates = []
    for i in range(4):
        p_id = str(players[i].id)
        my_rate = old_rates[i]
        my_goals = goals[i]
        
        # レート計算（四捨五入）
        change = base_points[i] + 2*(4 * my_goals - total_goals) + ((avg_rate - my_rate) / 20)
        change = round(change, 1)
        rate_changes.append(change)
        
        data["players"][p_id]["rate"] = round(my_rate + change, 1)
        data["players"][p_id]["name"] = players[i].display_name
        data["players"][p_id]["history"].append(data["players"][p_id]["rate"])
        new_rates.append(data["players"][p_id]["rate"])

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
    
    # データを即座に保存
    save_data(data)

    embed = discord.Embed(title=f"🎲 桃鉄対戦結果 (試合ID: {match_id})", color=0x3498db)
    embed.description = f"**部屋の平均レート:** {round(avg_rate, 1)}\n**総ゴール数:** {total_goals}回"
    
    medals = ["🥇 1位", "🥈 2位", "🥉 3位", "💀 4位"]
    for i in range(4):
        sign = "+" if rate_changes[i] >= 0 else ""
        embed.add_field(
            name=f"{medals[i]}: {players[i].display_name}",
            value=f"ゴール: {goals[i]}回\nレート: {old_rates[i]} ➔ **{new_rates[i]}** ({sign}{rate_changes[i]})",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)


# ----- コマンド②：詳細ステータス確認 -----
@bot.tree.command(name="rate", description="指定したメンバー（または自分）の詳細戦績とレート推移グラフを表示します")
@app_commands.describe(member="戦績を見たいメンバー（省略すると自分）")
async def rate(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    user_id = str(target.id)
    
    # コマンド実行時に最新データをロード
    data = load_data()

    if user_id not in data["players"] or len(data["players"][user_id]["history"]) <= 1:
        await interaction.response.send_message(f"🔍 {target.display_name} さんの対戦データはまだ登録されていません。（初期値: 1500）", ephemeral=False)
        return

    p_data = data["players"][user_id]
    current_rate = p_data["rate"]
    history = p_data["history"]
    match_count = len(history) - 1

    all_players = sorted(data["players"].items(), key=lambda x: x[1]["rate"], reverse=True)
    rank = 1
    for item_id, item_data in all_players:
        if item_id == user_id:
            break
        rank += 1
    total_players = len(data["players"])

    total_change = current_rate - 1500
    avg_gain = round(total_change / match_count, 2)
    sign = "+" if avg_gain >= 0 else ""

    await interaction.response.defer()

    plt.figure(figsize=(6, 3.5))
    plt.plot(history, marker='o', color='#3498db', linewidth=2, markersize=5)
    plt.title(f"Rate History", fontsize=12) # タイトルの文字化けを防ぐため固定文字に
    plt.xlabel("Matches", fontsize=10)
    plt.ylabel("Rating", fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=150)
    img_buf.seek(0)
    plt.close()

    file = discord.File(img_buf, filename="rate_history.png")
    embed = discord.Embed(title=f"📊 {target.display_name} さんの個人戦績", color=0x2ecc71)
    embed.add_field(name="🏆 現在の順位", value=f"`{rank}位` / {total_players}人中", inline=True)
    embed.add_field(name="⭐ 現在のレート", value=f"`{current_rate}`", inline=True)
    embed.add_field(name="🎮 合計試合回数", value=f"`{match_count}回`", inline=True)
    embed.add_field(name="📈 平均獲得ポイント", value=f"`{sign}{avg_gain} pt` / 試合", inline=False)
    embed.set_image(url="attachment://rate_history.png")

    await interaction.followup.send(embed=embed, file=file)


# ----- コマンド③：レートランキング表 -----
@bot.tree.command(name="ranking", description="サーバー全体のレートランキングを表示します")
async def ranking(interaction: discord.Interaction):
    # 最新データをロード
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
        if i >= 20:
            rank_text += "...以降は省略..."
            break

    embed.description = rank_text
    await interaction.response.send_message(embed=embed)


# ----- コマンド④：直近10試合の取り消しメニュー -----
class CancelSelect(discord.ui.Select):
    def __init__(self, matches):
        options = []
        for m in reversed(matches[-10:]):
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
        
        match_idx = -1
        for idx, m in enumerate(data["matches"]):
            if m["match_id"] == target_id:
                match_idx = idx
                break
                
        if match_idx == -1:
            await interaction.response.send_message("❌ 指定された試合データが見つかりませんでした。", ephemeral=True)
            return
            
        match_to_del = data["matches"][match_idx]
        
        for item in match_to_del["details"]:
            p_id = item["id"]
            if p_id in data["players"]:
                if len(data["players"][p_id]["history"]) > 1:
                    data["players"][p_id]["history"].pop()
                data["players"][p_id]["rate"] = data["players"][p_id]["history"][-1]

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
    await interaction.response.send_message("🔄 **試合結果の取り消しメニュー**\n以下のリストから削除したい試合を選んでください。", view=view, ephemeral=True)

# ==========================================
# 4. ボットの起動処理
# ==========================================
@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name}")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が環境変数に設定されていません。")