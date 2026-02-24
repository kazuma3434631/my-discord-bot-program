import discord
from discord.ext import commands
from discord import app_commands
import os
import re
from collections import defaultdict
import datetime
from keep_alive import keep_alive

# --- 1. 権限（Intents）の設定 ---
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 

# --- 2. 設定 ---
NEW_LOG_CHANNEL_ID = 1475867868724854814
WELCOME_CHANNEL_ID = 1475484575114330162
TICKET_CATEGORY_ID = 1475853559399452752

# スパム対策用の一時メモリ
last_messages = defaultdict(list)

# --- 3. UIクラス (省略なし) ---
class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="本当に閉じる", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        channel = await guild.create_text_channel(name=f"{ticket_type}-{user.display_name}", overwrites=overwrites, category=category)
        await interaction.response.send_message(f"チケット作成: {channel.mention}", ephemeral=True)
        embed = discord.Embed(title=f"【{ticket_type}】", description=f"{user.mention} さん、内容を記入してください。", color=color)
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

# --- 4. Bot本体 ---
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
    log = bot.get_channel(NEW_LOG_CHANNEL_ID)
    if log: await log.send("✅ 防衛システム（スパム・連投対策）稼働開始")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    # --- 荒らし対策ロジック ---
    user_id = message.author.id
    now = datetime.datetime.now()
    
    # 1. 大量メンション検知 (5人以上)
    if len(message.mentions) >= 5:
        await message.delete()
        await message.channel.send(f"{message.author.mention} 大量メンションは禁止です。", delete_after=5)
        return

    # 2. 連投検知 (5秒以内に3回同じ内容)
    user_msgs = last_messages[user_id]
    user_msgs.append({"content": message.content, "time": now})
    
    # 5秒より前の古いログを削除
    last_messages[user_id] = [m for m in user_msgs if (now - m["time"]).total_seconds() < 5]
    
    if len(last_messages[user_id]) >= 3:
        # 直近3件がすべて同じ内容かチェック
        contents = [m["content"] for m in last_messages[user_id][-3:]]
        if len(set(contents)) == 1:
            await message.delete()
            await message.channel.send(f"{message.author.mention} 連投（スパム）はやめてください。", delete_after=5)
            return

    # --- メッセージリンク展開機能 (既存) ---
    pattern = r"https://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)"
    extract = re.search(pattern, message.content)
    if extract:
        g_id, c_id, m_id = map(int, extract.groups())
        if message.guild.id == g_id:
            try:
                channel = bot.get_channel(c_id)
                f_msg = await channel.fetch_message(m_id)
                emb = discord.Embed(description=f_msg.content, color=discord.Color.light_grey(), timestamp=f_msg.created_at)
                emb.set_author(name=f_msg.author.display_name, icon_url=f_msg.author.display_avatar.url)
                if f_msg.attachments: emb.set_image(url=f_msg.attachments[0].url)
                await message.reply(embed=emb, mention_author=False)
            except: pass

    await bot.process_commands(message)

# メッセージ削除ログ (既存)
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    log = bot.get_channel(NEW_LOG_CHANNEL_ID)
    if log:
        emb = discord.Embed(title="🗑 削除ログ", color=discord.Color.red(), timestamp=message.created_at)
        emb.add_field(name="人", value=message.author.mention)
        emb.add_field(name="内容", value=message.content or "（なし）")
        await log.send(embed=emb)

# --- スラッシュコマンド (省略なし) ---
@bot.tree.command(name="ticket_setup")
async def ticket_setup(interaction: discord.Interaction):
    embed = discord.Embed(title="📩 お問い合わせ", description="ボタンを選択してください", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("設置完了", ephemeral=True)

@bot.tree.command(name="clear")
async def clear(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    def check(m): return True if user is None else m.author == user
    deleted = await interaction.channel.purge(limit=amount, check=check)
    await interaction.followup.send(f"✅ {len(deleted)}件削除", ephemeral=True)

@bot.tree.command(name="say")
async def say(interaction: discord.Interaction, message: str):
    sent = await interaction.channel.send(message)
    await interaction.response.send_message(f"ID: `{sent.id}`", ephemeral=True)

@bot.tree.command(name="edit")
async def edit(interaction: discord.Interaction, message_id: str, new_text: str):
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        await msg.edit(content=new_text)
        await interaction.response.send_message("✅ 修正完了", ephemeral=True)
    except: await interaction.response.send_message("❌ 失敗", ephemeral=True)

# 実行
keep_alive()
TOKEN = os.getenv('DISCORD_TOKEN')
bot.run(TOKEN)
