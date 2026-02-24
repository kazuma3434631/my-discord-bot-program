import discord
from discord.ext import commands
from discord import app_commands
import os
from keep_alive import keep_alive

# --- 1. 権限（Intents）の設定 ---
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True

# --- 2. 設定 ---
LOG_CHANNEL_ID = 1475491103225417738
WELCOME_CHANNEL_ID = 1475484575114330162
TICKET_CATEGORY_ID = 1475853559399452752

# --- 3. チケット機能用のUIクラス ---

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="本当に閉じる", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("チャンネルを削除します...", ephemeral=True)
        await interaction.channel.delete()

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("このチケットを閉じてもよろしいですか？", view=ConfirmCloseView(), ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def create_ticket_logic(self, interaction: discord.Interaction, ticket_type: str, color: discord.Color):
        guild = interaction.guild
        user = interaction.user
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        category = guild.get_channel(TICKET_CATEGORY_ID)
        channel = await guild.create_text_channel(
            name=f"{ticket_type}-{user.display_name}",
            overwrites=overwrites,
            category=category
        )
        
        await interaction.response.send_message(f"{ticket_type}用チケットを作成しました: {channel.mention}", ephemeral=True)
        
        embed = discord.Embed(
            title=f"【{ticket_type}】お問い合わせ",
            description=f"{user.mention} さん、お問い合わせ内容を詳しく記入してください。\n解決したら下のボタンで閉じてください。",
            color=color
        )
        await channel.send(embed=embed, view=CloseTicketView())

    @discord.ui.button(label="🚨 通報", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(interaction, "通報", discord.Color.red())

    @discord.ui.button(label="❓ 質問", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(interaction, "質問", discord.Color.blue())

    @discord.ui.button(label="💡 提案", style=discord.ButtonStyle.success, custom_id="ticket_suggest")
    async def suggest_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(interaction, "提案", discord.Color.green())

# --- 4. Botクラスの定義 ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='/', intents=intents)

    async def setup_hook(self):
        self.add_view(TicketView())
        self.add_view(CloseTicketView())
        self.add_view(ConfirmCloseView())
        await self.tree.sync()

bot = MyBot()

# --- 5. イベント処理 ---

@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user.name}')
    # --- 修正：ここに以前あったギルド判定(退出)のコードを削除しました ---
    
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send("botが起動しました")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.display_name}さん、こんにちは！「{member.guild.name}」へようこそ！")

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        await channel.send(f"{member.display_name}さん、さようなら…バイ…バイ…")

# --- 6. スラッシュコマンド ---

@bot.tree.command(name="ticket_setup", description="【管理者専用】チケット窓口を設置します")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📩 お問い合わせ・サポート窓口",
        description="用途に合わせて下のボタンを押してください。\n\n🚨 **通報** / ❓ **質問** / 💡 **提案**",
        color=discord.Color.blue()
    )
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("窓口を設置しました", ephemeral=True)

@bot.tree.command(name="clear", description="【管理者専用】メッセージを一括削除します")
@app_commands.describe(amount="削除件数", user="特定の人を指定（任意）")
@app_commands.checks.has_permissions(administrator=True, manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    def check_condition(m):
        return True if user is None else m.author == user
    deleted = await interaction.channel.purge(limit=amount, check=check_condition)
    await interaction.followup.send(f"✅ {len(deleted)}件のメッセージを削除しました", ephemeral=True)

@bot.tree.command(name="say", description="【管理者専用】Botに喋らせます")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, message: str):
    sent = await interaction.channel.send(message)
    await interaction.response.send_message(f"送信完了！ 修正用ID: `{sent.id}`", ephemeral=True)

@bot.tree.command(name="edit", description="【管理者専用】Botのメッセージを書き換えます")
@app_commands.checks.has_permissions(administrator=True)
async def edit(interaction: discord.Interaction, message_id: str, new_text: str):
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        if msg.author == bot.user:
            await msg.edit(content=new_text)
            await interaction.response.send_message("✅ 修正しました", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 私のメッセージではありません", ephemeral=True)
    except:
        await interaction.response.send_message("❌ メッセージが見つかりませんでした", ephemeral=True)

@bot.tree.command(name="ping", description="Botの応答速度を確認します")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency * 1000)}ms", ephemeral=True)

# --- 7. 実行 ---
keep_alive()
TOKEN = os.getenv('DISCORD_TOKEN')
bot.run(TOKEN)
