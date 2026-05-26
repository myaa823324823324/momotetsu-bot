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
from datetime import datetime, timedelta

# ==========================================
# 1. ボットとFlaskの初期設定 (UptimeRobot対応)
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
# 2. ロール（役職）の自動付与設定＆テストモード初期値
# ==========================================
# ✨ Kami8さんに提供していただいた実際のロールIDをすべて直接反映済みです！
ROLE_IDS = {
    "マスター": 1508651248470065303,
    "サファイア": 1508654559596384356,
    "ダイヤモンド": 1508654495956078763,
    "プラチナ": 1508651115569217606,
    "ゴールド": 1508650605021761616,
    "シルバー": 1508653796065022064,
    "ブロンズ": 1508650771514785862,
    "アイアン": 1508650670092451890
}

# グローバル変数でテストモードの状態を管理 (初期値はTrue = テストモードON)
IS_TEST_MODE = True

def get_title_and_rank(rate):
    """レートから称号の名前を決定する"""
    if rate >= 2000: return "マスター"
    elif rate >= 1900: return "サファイア"
    elif rate >= 1800: return "ダイヤモンド"
    elif rate >= 1700: return "プラチナ"
    elif rate >= 1600: return "ゴールド"
    elif rate >= 1500: return "シルバー"
    elif rate >= 1400: return "ブロンズ"
    else: return "アイアン"

async def update_member_roles(member, rate):
    """レートに応じてロールを自動で付け替える関数"""
    current_title = get_title_and_rank(rate)
    
    all_title_roles = {}
    for title, r_id in ROLE_IDS.items():
        if r_id != 0:
            role = member.guild.get_role(r_id)
            if role: all_title_roles[title] = role
            
    if not all_title_roles:
        return 
        
    target_role = all_title_roles.get(current_title)
    roles_to_remove = [role for title, role in all_title_roles.items() if title != current_title and role in member.roles]
    
    try:
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove)
        if target_role and target_role not in member.roles:
            await member.add_roles(target_role)
    except Exception as e:
        print(f"ロール付与エラー ({member.display_name}): {e}")

# ==========================================
# 3. データの読み書きシステム ＆ 期限切れストライク自動削除
# ==========================================
DATA_FILE = "momotetsu_data.json"

def clean_expired_strikes(data):
    """1ヶ月（30日）が経過した古いストライクを自動で消去する関数"""
    now = datetime.now()
    updated = False
    
    if "players" not in data:
        return data, updated

    for p_id, p_data in data["players"].items():
        if "strike_details" in p_data and p_data["strike_details"]:
            valid_strikes = []
            for strike in p_data["strike_details"]:
                try:
                    strike_time = datetime.strptime(strike["timestamp"], "%Y-%m-%d %H:%M:%S")
                    if now - strike_time < timedelta(days=30):
                        valid_strikes.append(strike)
                    else:
                        updated = True
                except Exception:
                    valid_strikes.append(strike)
            
            p_data["strike_details"] = valid_strikes
            p_data["strikes"] = len(valid_strikes)
            
            if "strike_reasons" in p_data:
                p_data["strike_reasons"] = [s["reason"] for s in valid_strikes]
                
    return data, updated

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    data, was_cleaned = clean_expired_strikes(data)
                    if was_cleaned:
                        save_data_raw(data)
                    return data
        except Exception as e:
            print(f"データ読み込みエラー: {e}")
    return {"players": {}, "matches": []}

def save_data_raw(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        print(f"データ保存エラー: {e}")

def save_data(data):
    data, _ = clean_expired_strikes(data)
    save_data_raw(data)

# ==========================================
# 4. イベント処理（暴言等のチャット制限）
# ==========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    data = load_data()
    author_id = str(message.author.id)

    if author_id in data["players"] and data["players"][author_id].get("is_muted", False):
        if not message.content.startswith('/') and not message.content.startswith('!'):
            try:
                await message.delete()
                return
            except Exception as e:
                print(f"メッセージ削除失敗: {e}")

    await bot.process_commands(message)

# ==========================================
# 5. コマンドの実装
# ==========================================

# ----- コマンド①：試合結果の入力 -----
@bot.tree.command(name="result", description="桃鉄の対戦結果を入力してレートを計算します")
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

    data = load_data()
    players = [p1, p2, p3, p4]
    goals = [p1_goals, p2_goals, p3_goals, p4_goals]
    total_goals = sum(goals)
    base_points = [30, 10, -10, -30]
    
    for p in players:
        p_id = str(p.id)
        if p_id in data["players"] and data["players"][p_id].get("strikes", 0) >= 3:
            await interaction.response.send_message(
                f"⚠️ 登録エラー: {p.display_name} さんはストライクが3つ溜まっているため、現在ラウンジの試合に参加（登録）できません。", 
                ephemeral=True
            )
            return

    old_rates = []
    for p in players:
        p_id = str(p.id)
        if p_id in data["players"]:
            old_rates.append(data["players"][p_id]["rate"])
        else:
            old_rates.append(1500)
        
    avg_rate = sum(old_rates) / 4
    
    rate_changes = []
    new_rates = []
    for i in range(4):
        my_rate = old_rates[i]
        
        # 計算式によって算出された変動値
        change = base_points[i] + (4 * goals[i] - total_goals) + ((avg_rate - my_rate) / 20)
        change = round(change, 1)
        
        # 🛡️ 0未満（マイナス）にならないための安全制限
        calculated_rate = my_rate + change
        if calculated_rate < 0:
            calculated_rate = 0.0
            change = round(0.0 - my_rate, 1) # 変動幅も実際の数値に合わせる
            
        rate_changes.append(change)
        new_rates.append(round(calculated_rate, 1))

    for i in range(4):
        p_id = str(players[i].id)
        if p_id not in data["players"]:
            data["players"][p_id] = {
                "name": players[i].display_name, "rate": 1500, "history": [1500],
                "total_matches": 0, "total_goals": 0, "total_ranks": [0, 0, 0, 0], "max_rate": 1500,
                "strikes": 0, "strike_reasons": [], "strike_details": [], "is_muted": False
            }
        
        data["players"][p_id]["rate"] = new_rates[i]
        data["players"][p_id]["name"] = players[i].display_name
        data["players"][p_id]["history"].append(new_rates[i])
        data["players"][p_id]["total_matches"] += 1
        data["players"][p_id]["total_goals"] += goals[i]
        data["players"][p_id]["total_ranks"][i] += 1
        if new_rates[i] > data["players"][p_id].get("max_rate", 1500):
            data["players"][p_id]["max_rate"] = new_rates[i]

    match_id = len(data["matches"]) + 1
    match_record = {
        "match_id": match_id, "date": datetime.now().strftime("%m/%d %H:%M"),
        "details": [
            {"id": str(p1.id), "name": p1.display_name, "change": rate_changes[0], "goals": p1_goals, "rank": 1},
            {"id": str(p2.id), "name": p2.display_name, "change": rate_changes[1], "goals": p2_goals, "rank": 2},
            {"id": str(p3.id), "name": p3.display_name, "change": rate_changes[2], "goals": p3_goals, "rank": 3},
            {"id": str(p4.id), "name": p4.display_name, "change": rate_changes[3], "goals": p4_goals, "rank": 4}
        ]
    }
    data["matches"].append(match_record)
    save_data(data)

    if not IS_TEST_MODE:
        for i in range(4):
            await update_member_roles(players[i], new_rates[i])

    title_text = f"🧪 桃鉄対戦結果 [テスト試合ID: {len(data['matches'])}]" if IS_TEST_MODE else f"🎲 桃鉄対戦結果 (試合ID: {len(data['matches'])})"
    embed = discord.Embed(title=title_text, color=0xe74c3c if IS_TEST_MODE else 0x3498db)
    
    if IS_TEST_MODE:
        embed.description = f"⚠️ 現在テストモード運用中です。本番開始時にこのデータはリセットされます。\n**部屋の平均レート:** {round(avg_rate, 1)} | **総ゴール数:** {total_goals}回"
    else:
        embed.description = f"**部屋の平均レート:** {round(avg_rate, 1)}\n**総ゴール数:** {total_goals}回"
    
    medals = ["🥇 1位", "🥈 2位", "🥉 3位", "💀 4位"]
    for i in range(4):
        sign = "+" if rate_changes[i] >= 0 else ""
        title_tag = get_title_and_rank(new_rates[i])
        embed.add_field(
            name=f"{medals[i]}: {players[i].display_name}【{title_tag}】",
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
    data = load_data()

    if user_id not in data["players"] or len(data["players"][user_id]["history"]) <= 1:
        mode_str = "テスト" if IS_TEST_MODE else "本番"
        await interaction.response.send_message(f"🔍 {target.display_name} さんの{mode_str}対戦データはまだ登録されていません。（初期値: 1500）", ephemeral=False)
        return

    p_data = data["players"][user_id]
    current_rate = p_data["rate"]
    history = p_data["history"]
    match_count = p_data.get("total_matches", len(history) - 1)

    all_players = sorted(data["players"].items(), key=lambda x: x[1]["rate"], reverse=True)
    rank = 1
    for item_id, item_data in all_players:
        if item_id == user_id:
            break
        rank += 1
    total_players = len(data["players"])

    total_goals = p_data.get("total_goals", 0)
    avg_goals = round(total_goals / match_count, 1) if match_count > 0 else 0
    max_rate = p_data.get("max_rate", current_rate)
    title_tag = get_title_and_rank(current_rate)

    ranks = p_data.get("total_ranks", [0, 0, 0, 0])
    sum_ranks = (ranks[0]*1) + (ranks[1]*2) + (ranks[2]*3) + (ranks[3]*4)
    avg_rank = round(sum_ranks / match_count, 2) if match_count > 0 else 0

    await interaction.response.defer()

    plt.figure(figsize=(6, 3.5))
    plt.plot(history, marker='o', color='#e74c3c' if IS_TEST_MODE else '#3498db', linewidth=2, markersize=5)
    plt.title(f"Rate History {'(Test Mode)' if IS_TEST_MODE else ''}", fontsize=12)
    plt.xlabel("Matches", fontsize=10)
    plt.ylabel("Rating", fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()

    img_buf = io.BytesIO()
    plt.savefig(img_buf, format='png', dpi=150)
    img_buf.seek(0)
    plt.close()

    file = discord.File(img_buf, filename="rate_history.png")
    
    title_prefix = "🧪 [テストデータ]" if IS_TEST_MODE else "📊"
    embed = discord.Embed(title=f"{title_prefix} {target.display_name} さんの個人戦績", color=0xe74c3c if IS_TEST_MODE else 0x2ecc71)
    embed.add_field(name="👑 現在の称号", value=f"`【{title_tag}】`", inline=False)
    embed.add_field(name="🏆 現在の順位", value=f"`{rank}位` / {total_players}人中", inline=True)
    embed.add_field(name="⭐ 現在のレート", value=f"`{current_rate}` (最高: `{max_rate}`)", inline=True)
    embed.add_field(name="🎮 合計試合回数", value=f"`{match_count}回`", inline=True)
    embed.add_field(name="🎲 平均順位", value=f"`{avg_rank} 位`", inline=True)
    embed.add_field(name="⚽ 平均ゴール数", value=f"`{avg_goals} 回` / 試合", inline=True)
    
    strikes = p_data.get("strikes", 0)
    strike_str = "🟢 なし" if strikes == 0 else f"⚠️ {strikes} / 3 つ蓄積中\n(1ヶ月で自動消去)"
    if strikes >= 3: strike_str = "🚨 3つ蓄積（試合参加不可）"
    embed.add_field(name="🛡️ ストライク状態", value=f"`{strike_str}`", inline=True)
    
    embed.add_field(name="📈 順位内訳", value=f"1位:`{ranks[0]}回` | 2位:`{ranks[1]}回` | 3位:`{ranks[2]}回` | 4位:`{ranks[3]}回`", inline=False)
    embed.set_image(url="attachment://rate_history.png")

    await interaction.followup.send(embed=embed, file=file)


# ----- コマンド③：レートランキング表 -----
@bot.tree.command(name="ranking", description="サーバー全体のレートランキングを表示します")
async def ranking(interaction: discord.Interaction):
    data = load_data()
    if not data["players"]:
        mode_str = "テスト" if IS_TEST_MODE else "本番"
        await interaction.response.send_message(f"📭 まだ{mode_str}データが登録されていません。", ephemeral=True)
        return

    sorted_players = sorted(data["players"].items(), key=lambda x: x[1]["rate"], reverse=True)
    title_str = "🏆 桃鉄ラウンジ レートランキング [テスト期間中]" if IS_TEST_MODE else "🏆 桃鉄ラウンジ レートランキング"
    embed = discord.Embed(title=title_str, color=0xe74c3c if IS_TEST_MODE else 0xf1c40f)
    rank_text = ""
    if IS_TEST_MODE:
        rank_text += "⚠️ これはテスト用の順位です。本番移行時にリセットされます。\n\n"
        
    for i, (u_id, u_data) in enumerate(sorted_players, 1):
        matches = u_data.get("total_matches", len(u_data.get("history", [1500])) - 1)
        title_tag = get_title_and_rank(u_data['rate'])
        rank_text += f"**{i}位**: {u_data['name']} (`{u_data['rate']}`)【{title_tag}】 - {matches}戦\n"
        if i >= 20:
            rank_text += "...以降は省略..."
            break

    embed.description = rank_text
    await interaction.response.send_message(embed=embed)


# ----- コマンド④：ストライク（警告）の付与 -----
@bot.tree.command(name="strike", description="【管理者専用】ルール違反をしたメンバーにストライク（警告）を1つ付与します（1ヶ月で自動消去）")
@app_commands.describe(member="警告するメンバー", reason="警告の理由（遅刻、無断欠席、暴言など）")
async def strike(interaction: discord.Interaction, member: discord.Member, reason: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    p_id = str(member.id)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_short = datetime.now().strftime("%m/%d")

    if p_id not in data["players"]:
        data["players"][p_id] = {
            "name": member.display_name, "rate": 1500, "history": [1500],
            "total_matches": 0, "total_goals": 0, "total_ranks": [0, 0, 0, 0], "max_rate": 1500,
            "strikes": 0, "strike_reasons": [], "strike_details": [], "is_muted": False
        }

    if "strike_details" not in data["players"][p_id]:
        data["players"][p_id]["strike_details"] = []

    new_strike = {
        "timestamp": now_str,
        "reason": f"[{date_short}] {reason}"
    }
    data["players"][p_id]["strike_details"].append(new_strike)
    data["players"][p_id]["strikes"] = len(data["players"][p_id]["strike_details"])
    data["players"][p_id]["strike_reasons"].append(f"[{date_short}] {reason}")
    
    current_strikes = data["players"][p_id]["strikes"]
    save_data(data)

    embed = discord.Embed(title="🛡️ ストライク（警告）処置通知", color=0xe74c3c)
    embed.description = f"{member.mention} さんにストライクを1つ付与しました。\n\n**理由:** {reason}\n**現在の蓄積数:** `{current_strikes} / 3` つ\n⏱️ *この警告は今から30日後に自動的に消滅（時効）します。*"
    
    if current_strikes >= 3:
        embed.description += "\n\n🚨 **ストライクが3つに達したため、ラウンジの試合への参加（結果登録）が自動的にブロックされました。**"

    await interaction.response.send_message(embed=embed)


# ----- コマンド⑤：ストライクの解除（手動） -----
@bot.tree.command(name="unstrike", description="【管理者専用】メンバーの直近のストライクを手動で1つ減らします")
@app_commands.describe(member="解除するメンバー")
async def unstrike(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    p_id = str(member.id)

    if p_id not in data["players"] or not data["players"][p_id].get("strike_details", []):
        await interaction.response.send_message(f"❌ {member.display_name} さんは有効なストライクを持っていません。", ephemeral=True)
        return

    data["players"][p_id]["strike_details"].pop()
    data["players"][p_id]["strikes"] = len(data["players"][p_id]["strike_details"])
    
    if "strike_reasons" in data["players"][p_id] and data["players"][p_id]["strike_reasons"]:
        data["players"][p_id]["strike_reasons"].pop()
        
    current_strikes = data["players"][p_id]["strikes"]
    save_data(data)

    await interaction.response.send_message(f"✅ {member.mention} さんのストライクを手動で1つ解除しました。（現在: `{current_strikes} / 3`）")


# ----- コマンド⑥：チャット制限（ミュート）の切り替え -----
@bot.tree.command(name="mute_player", description="【管理者専用】暴言を吐いた人の通常チャットを禁止し、ボット操作のみに制限します")
@app_commands.describe(member="制限・解除するメンバー")
async def mute_player(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    p_id = str(member.id)

    if p_id not in data["players"]:
        data["players"][p_id] = {
            "name": member.display_name, "rate": 1500, "history": [1500],
            "total_matches": 0, "total_goals": 0, "total_ranks": [0, 0, 0, 0], "max_rate": 1500,
            "strikes": 0, "strike_reasons": [], "strike_details": [], "is_muted": False
        }

    current_status = data["players"][p_id].get("is_muted", False)
    data["players"][p_id]["is_muted"] = not current_status
    save_data(data)

    if data["players"][p_id]["is_muted"]:
        msg = f"🤐 {member.mention} さんの**一般チャット発言を制限**しました。\n今後は通常の文章は自動削除されますが、ボット用の各種コマンドのみ通常通り実行可能です。"
        color = 0xe67e22
    else:
        msg = f"😇 {member.mention} さんのチャット制限を解除し、通常の会話を許可しました。"
        color = 0x2ecc71

    embed = discord.Embed(title="🤐 チャット制限（個別ミュート）通知", description=msg, color=color)
    await interaction.response.send_message(embed=embed)


# ----- コマンド⑦：試合結果の取り消し -----
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
        
        for rank_idx, item in enumerate(match_to_del["details"]):
            p_id = item["id"]
            if p_id in data["players"]:
                p_data = data["players"][p_id]
                if len(p_data["history"]) > 1:
                    p_data["history"].pop()
                p_data["rate"] = p_data["history"][-1]
                
                p_data["total_matches"] = max(0, p_data.get("total_matches", 1) - 1)
                p_data["total_goals"] = max(0, p_data.get("total_goals", item["goals"]) - item["goals"])
                if "total_ranks" in p_data:
                    p_data["total_ranks"][rank_idx] = max(0, p_data["total_ranks"][rank_idx] - 1)

        data["matches"].pop(match_idx)
        save_data(data)
        await interaction.response.send_message(f"✅ 試合ID: {target_id} の結果を取り消し、全員のレートとスタッツを巻き戻しました！", ephemeral=True)

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


# ----- コマンド⑧：テストモード切り替え -----
@bot.tree.command(name="toggle_test_mode", description="【管理者専用】テストモードのON/OFFを切り替えます（OFF移行時にデータ自動消去）")
async def toggle_test_mode(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    global IS_TEST_MODE
    IS_TEST_MODE = not IS_TEST_MODE
    
    if not IS_TEST_MODE:
        data = load_data()
        for p_id in data["players"]:
            p_data = data["players"][p_id]
            p_data["rate"] = 1500
            p_data["history"] = [1500]
            p_data["total_matches"] = 0
            p_data["total_goals"] = 0
            p_data["total_ranks"] = [0, 0, 0, 0]
            p_data["max_rate"] = 1500
            p_data["strikes"] = 0
            p_data["strike_reasons"] = []
            p_data["strike_details"] = []
            p_data["is_muted"] = False
        
        data["matches"] = []
        save_data(data)
        
        status_text = "🟢 OFF (本番稼働開始！)\n\n✨ **【自動データお掃除完了】** テスト期間中のデータ、ランキング、ペナルティ履歴を含むすべてのデータを完全にリセットしました！ここから本番がスタートします。"
        color = 0x2ecc71
    else:
        status_text = "🔴 ON (テストモードに戻りました)"
        color = 0xe74c3c
    
    embed = discord.Embed(title="⚙️ モード切り替え ＆ データ処理通知", description=status_text, color=color)
    await interaction.response.send_message(embed=embed)


# ----- コマンド⑨：シーズンリセット -----
@bot.tree.command(name="season_reset", description="【管理者専用】現在のシーズンを終了し、全員のレートや統計をリセットします")
async def season_reset(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ このコマンドは管理者しか使用できません。", ephemeral=True)
        return

    data = load_data()
    if not data["players"]:
        await interaction.response.send_message("📭 リセットするプレイヤーデータがありません。", ephemeral=True)
        return

    for p_id in data["players"]:
        p_data = data["players"][p_id]
        p_data["rate"] = 1500
        p_data["history"] = [1500]
        p_data["total_matches"] = 0
        p_data["total_goals"] = 0
        p_data["total_ranks"] = [0, 0, 0, 0]

    data["matches"] = []
    save_data(data)

    await interaction.response.send_message("🏁 **シーズンリセットが完了しました！**\n全員の本番レートが `1500` に戻り、新しいシーズンがスタートしました！")


# ==========================================
# 6. ボットの起動処理
# ==========================================
@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name}")

def start_flask():
    threading.Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    start_flask()
    
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_BOT_TOKEN not found.")