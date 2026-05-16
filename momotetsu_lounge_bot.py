import os
from flask import Flask
import threading
import os
import discord
from discord.ext import commands
from discord import app_commands
import json
import os

# --- データの保存用設定 ---
# 簡易的なデータベースとしてJSONファイルを使用します
DATA_FILE = "lounge_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "matches": 0}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_or_create_user(data, user_id, name):
    user_id_str = str(user_id)
    if user_id_str not in data["users"]:
        data["users"][user_id_str] = {
            "name": name,
            "rate": 1000,  # 初期レート値
            "games": 0,
            "goals": 0
        }
    return data["users"][user_id_str]

# --- Discord ボットの設定 ---
class MomotetsuLoungeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # スラッシュコマンドをDiscordに同期します
        await self.tree.sync()
        print("スラッシュコマンドの同期が完了しました。")

bot = MomotetsuLoungeBot()

@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name} (ID: {bot.user.id})")
    print("------")

# --- コマンド1: レート確認 ---
@bot.tree.command(name="profile", description="自分の現在のレートとスタッツを確認します。")
async def profile(interaction: discord.Interaction, ユーザー: discord.Member = None):
    target_user = ユーザー or interaction.user
    data = load_data()
    user_data = get_or_create_user(data, target_user.id, target_user.display_name)
    
    embed = discord.Embed(
        title=f"🏆 {target_user.display_name} の成績",
        color=discord.Color.gold()
    )
    embed.add_field(name="現在のレート", value=f"📈 **{user_data['rate']} pt**", inline=False)
    embed.add_field(name="対戦回数", value=f"🎮 {user_data['games']} 回", inline=True)
    embed.add_field(name="総ゴール数", value=f"🎯 {user_data['goals']} 回", inline=True)
    
    await interaction.response.send_message(embed=embed)

# --- コマンド2: 結果入力 (ゼロサム自動計算搭載) ---
@bot.tree.command(name="report", description="【管理者・ホスト用】3年決戦の対戦結果を入力・反映します。")
@app_commands.describe(
    位1="1位のプレイヤー", ゴール1="1位のゴール数 (最大3)",
    位2="2位のプレイヤー", ゴール2="2位のゴール数 (最大3)",
    位3="3位のプレイヤー", ゴール3="3位のゴール数 (最大3)",
    位4="4位のプレイヤー", ゴール4="4位のゴール数 (最大3)"
)
async def report(
    interaction: discord.Interaction, 
    位1: discord.Member, ゴール1: int,
    位2: discord.Member, ゴール2: int,
    位3: discord.Member, ゴール3: int,
    位4: discord.Member, ゴール4: int
):
    # 重複チェック
    players = [位1, 位2, 位3, 位4]
    if len(set(players)) < 4:
        await interaction.response.send_message("❌ エラー: プレイヤーが重複しています。4人全員別の人を指定してください。", ephemeral=True)
        return

    # ゴール数の上限キャップ（1人最大3回までルール）
    g1 = min(max(0, ゴール1), 3)
    g2 = min(max(0, ゴール2), 3)
    g3 = min(max(0, ゴール3), 3)
    g4 = min(max(0, ゴール4), 3)
    
    # 総ゴール数の計算
    total_goals = g1 + g2 + g3 + g4
    
    # 基本の順位ポイント
    base_points = [30, 10, -10, -30]
    
    # ゼロサム計算ロジック：最終スコア ＝ 基本順位pt － 総ゴール数 ＋ (自分のゴール数 × 4)
    score1 = base_points[0] - total_goals + (g1 * 4)
    score2 = base_points[1] - total_goals + (g2 * 4)
    score3 = base_points[2] - total_goals + (g3 * 4)
    score4 = base_points[3] - total_goals + (g4 * 4)
    
    # データの更新
    data = load_data()
    data["matches"] += 1
    match_num = data["matches"]
    
    p1_data = get_or_create_user(data, 位1.id, 位1.display_name)
    p2_data = get_or_create_user(data, 位2.id, 位2.display_name)
    p3_data = get_or_create_user(data, 位3.id, 位3.display_name)
    p4_data = get_or_create_user(data, 位4.id, 位4.display_name)
    
    # レート・スタッツ反映
    p1_data["rate"] += score1
    p1_data["games"] += 1
    p1_data["goals"] += g1
    
    p2_data["rate"] += score2
    p2_data["games"] += 1
    p2_data["goals"] += g2
    
    p3_data["rate"] += score3
    p3_data["games"] += 1
    p3_data["goals"] += g3
    
    p4_data["rate"] += score4
    p4_data["games"] += 1
    p4_data["goals"] += g4
    
    save_data(data)
    
    # 結果発表Embedの作成
    embed = discord.Embed(
        title=f"🎲 試合結果反映 [#Match-{match_num}]",
        description="1ゴール4点ルールのゼロサム計算が適用されました。",
        color=discord.Color.green()
    )
    embed.add_field(name=f"🥇 1位: {位1.display_name}", value=f"ゴール: {g1}回 | レート変動: **{'+' if score1 >= 0 else ''}{score1}** → 現在: `{p1_data['rate']} pt`", inline=False)
    embed.add_field(name=f"🥈 2位: {位2.display_name}", value=f"ゴール: {g2}回 | レート変動: **{'+' if score2 >= 0 else ''}{score2}** → 現在: `{p2_data['rate']} pt`", inline=False)
    embed.add_field(name=f"🥉 3位: {位3.display_name}", value=f"ゴール: {g3}回 | レート変動: **{'+' if score3 >= 0 else ''}{score3}** → 現在: `{p3_data['rate']} pt`", inline=False)
    embed.add_field(name=f"🏅 4位: {位4.display_name}", value=f"ゴール: {g4}回 | レート変動: **{'+' if score4 >= 0 else ''}{score4}** → 現在: `{p4_data['rate']} pt`", inline=False)
    
    # ゼロサム検証の表示
    checksum = score1 + score2 + score3 + score4
    embed.set_footer(text=f"システムチェック: 総増減 {checksum} pt (ゼロサム完全補正)")
    
    await interaction.response.send_message(embed=embed)

# --- コマンド3: ランキング表示 ---
@bot.tree.command(name="leaderboard", description="現在のラウンジレート上位10名を表示します。")
async def leaderboard(interaction: discord.Interaction):
    data = load_data()
    # レートの高い順にソート
    sorted_users = sorted(data["users"].items(), key=lambda x: x[1]["rate"], reverse=True)
    
    if not sorted_users:
        await interaction.response.send_message("まだデータが登録されていません。", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="🏆 桃鉄ラウンジ 総合ランキング",
        color=discord.Color.blue()
    )
    
    rank_text = ""
    for i, (user_id, u_data) in enumerate(sorted_users[:10], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`#{i}`"
        rank_text += f"{medal} {u_data['name']} : {u_data['rate']} pt ({u_data['games']}戦 {u_data['goals']}G)\n"
        
    embed.description = rank_text
    await interaction.response.send_message(embed=embed)

# ⭕ 変更後（このように書き換えてください）
    TOKEN = os.environ.get(DISCORD_BOT_TOKEN)

# サーバーを24時間維持するためのダミーWebサーバー
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    # Renderが指定するポート番号を取得（デフォルトは8080）
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# バックグラウンドでWebサーバーを起動
threading.Thread(target=run_web).start()
bot.run(TOKEN)
